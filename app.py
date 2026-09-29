import os
import re
import random
import string
import json
import time
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import pymysql
import pymysql.cursors

from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key_nfh')

# Helper to safely parse integer environment variables with fallbacks
def _safe_int_env(env_var, default_val):
    val = os.getenv(env_var)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return default_val

# ---------------------------------------------------------------------------
# Session inactivity security
# ---------------------------------------------------------------------------
# Production defaults: 30 minutes of inactivity with a warning during the
# final 5 minutes. Environment overrides are intentionally limited to timing
# values so local testing can use shorter intervals without changing code.
SESSION_INACTIVITY_MINUTES = max(1, _safe_int_env('SESSION_INACTIVITY_MINUTES', 30))
SESSION_WARNING_MINUTES = max(1, _safe_int_env('SESSION_WARNING_MINUTES', 5))
if SESSION_WARNING_MINUTES >= SESSION_INACTIVITY_MINUTES:
    SESSION_WARNING_MINUTES = max(1, SESSION_INACTIVITY_MINUTES - 1)

SESSION_INACTIVITY_SECONDS = SESSION_INACTIVITY_MINUTES * 60
SESSION_WARNING_SECONDS = SESSION_WARNING_MINUTES * 60
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=SESSION_INACTIVITY_SECONDS)
app.config['SESSION_REFRESH_EACH_REQUEST'] = False

# Endpoints that run automatically in the background and therefore must never
# extend an authenticated session.
SESSION_BACKGROUND_ENDPOINTS = {'live_metrics'}


UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

EXECUTIVE_ROLES = ['President', 'Vice President', 'Board Director']
OFFICER_ROLES = ['Secretary', 'Treasurer', *EXECUTIVE_ROLES, 'Admin']
HOA_NAME = "NORTH FAIRWAY HOMES HOMEOWNERS ASSOCIATION INC."
HOA_ADDRESS = "Sitio Pastol, Brgy. Muzon West, City of San Jose del Monte, Bulacan 3023"
HOA_REG = "HLURB Registration Number: NTR-20986-R | TIN No: 486-778-923-000"

# ---------------------------------------------------------------------------
# Request-type-specific approval routing
# ---------------------------------------------------------------------------
# Keep these names aligned with the request titles currently emitted by the
# Homeowner request forms. These sets are the single backend source of truth
# for who may perform the initial checking stage.
SECRETARY_FIRST_REQUEST_TYPES = {
    'Certificate of Improvement',
    'Proof of Residency',
    'Move-in Gate Pass',
    'Move-out Gate Pass',
    'Certificate of Membership',
}
TREASURER_FIRST_REQUEST_TYPES = {
    'Gate Pass',
}
SHARED_INITIAL_CHECK_REQUEST_TYPES = {
    'Vehicle Sticker Application',
    'Renters/Tenants Information Form',
}


def initial_checker_roles(request_type):
    if request_type in SECRETARY_FIRST_REQUEST_TYPES:
        return {'Secretary'}
    if request_type in TREASURER_FIRST_REQUEST_TYPES:
        return {'Treasurer'}
    if request_type in SHARED_INITIAL_CHECK_REQUEST_TYPES:
        return {'Secretary', 'Treasurer'}
    # Preserve legacy behavior for any older/unknown request title: Secretary
    # remains the default initial reviewer rather than leaving the request stuck.
    return {'Secretary'}


def role_can_initial_check(role, request_type, assigned_officer=None):
    if role == 'Admin':
        return True
    allowed = initial_checker_roles(request_type)
    if role not in allowed:
        return False
    # Shared request types can initially be seen by either authorized officer.
    # Once one officer has acted (for example, before a correction/resubmission),
    # keep that request with the same checker so it does not bounce between roles.
    if request_type in SHARED_INITIAL_CHECK_REQUEST_TYPES and assigned_officer in {'Secretary', 'Treasurer'}:
        return role == assigned_officer
    return True


def request_is_check_actionable(req, role):
    return (
        req.get('status') in {'Submitted', 'Under Review'} and
        role_can_initial_check(role, req.get('request_type'), req.get('assigned_officer'))
    )



# ---------------------------------------------------------------------------
# Inactivity enforcement and shared UI configuration
# ---------------------------------------------------------------------------
def _session_expired_response():
    session.clear()
    if request.path.startswith('/api/') or request.headers.get('Accept', '').lower().find('application/json') >= 0:
        response = jsonify({
            'status': 'error',
            'message': 'Your session expired after 30 minutes of inactivity. Please sign in again.',
            'session_expired': True,
        })
        response.status_code = 401
        response.headers['X-Session-Expired'] = '1'
        return response
    return redirect(url_for('register_page', session='expired'))


@app.before_request
def enforce_session_inactivity():
    """Expire authenticated sessions after 30 minutes without real activity.

    Automatic live-metric polling is checked for expiration but intentionally
    does not refresh last_activity. Normal page/API actions do refresh it, so
    server-side enforcement still works when JavaScript is unavailable.
    """
    if request.endpoint == 'static' or 'user_id' not in session:
        return None

    now = time.time()
    last_activity = float(session.get('last_activity', now))
    if now - last_activity >= SESSION_INACTIVITY_SECONDS:
        return _session_expired_response()

    if request.endpoint not in SESSION_BACKGROUND_ENDPOINTS and request.endpoint != 'session_keepalive':
        session['last_activity'] = now
        session.permanent = True
        session.modified = True
    return None


@app.context_processor
def inject_session_timeout_config():
    return {
        'session_timeout_seconds': SESSION_INACTIVITY_SECONDS,
        'session_warning_seconds': SESSION_WARNING_SECONDS,
    }


@app.route('/api/session/keepalive', methods=['POST'])
def session_keepalive():
    if 'user_id' not in session:
        response = jsonify({'status': 'error', 'message': 'Unauthorized', 'session_expired': True})
        response.status_code = 401
        response.headers['X-Session-Expired'] = '1'
        return response
    now = time.time()
    session['last_activity'] = now
    session.permanent = True
    session.modified = True
    return jsonify({
        'status': 'success',
        'expires_in': SESSION_INACTIVITY_SECONDS,
        'server_time': int(now),
    })


# ---------------------------------------------------------------------------
# Jinja filter
# ---------------------------------------------------------------------------
@app.template_filter('format_details')
def format_details(details):
    if not details:
        return 'None'
    try:
        parsed = json.loads(details) if isinstance(details, str) else details
        if isinstance(parsed, dict):
            items = []
            for k, v in parsed.items():
                if k == 'vehicles' and isinstance(v, list):
                    items.append(f"Vehicles: {len(v)}")
                else:
                    items.append(f"{k.replace('_', ' ').title()}: {v}")
            return ', '.join(items)
    except Exception:
        pass
    return str(details)


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DB', 'nfhsystem')
DB_PORT = _safe_int_env('MYSQL_PORT', 3306)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = _safe_int_env('MAIL_PORT', 587)
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or os.getenv('MAIL_USERNAME')

mail = Mail(app)

VERIFICATION_CODES = {}
RESET_CODES = {}


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
        port=DB_PORT, cursorclass=pymysql.cursors.DictCursor, autocommit=True
    )


def now_str():
    """NFH convention: DD/MM/YYYY - HH:MM"""
    return datetime.now().strftime('%d/%m/%Y - %H:%M')


def dues_summary(cursor, user_id):
    """Return a compact, read-only summary of a homeowner's unpaid monthly dues."""
    cursor.execute("""SELECT COUNT(*) AS unpaid_months, COALESCE(SUM(amount),0) AS outstanding_balance,
                              MIN(due_month) AS oldest_unpaid_due
                       FROM monthly_dues WHERE user_id=%s AND status='Unpaid'""", (user_id,))
    row = cursor.fetchone() or {}
    cursor.execute("""SELECT due_month, amount FROM monthly_dues
                       WHERE user_id=%s AND status='Unpaid' ORDER BY due_month ASC""", (user_id,))
    unpaid_rows = cursor.fetchall() or []
    count = int(row.get('unpaid_months') or 0)
    oldest = row.get('oldest_unpaid_due')
    if count <= 0 or not oldest:
        period = 'Clear'
    else:
        today = datetime.now().date().replace(day=1)
        if isinstance(oldest, datetime): oldest = oldest.date()
        months = max(1, (today.year-oldest.year)*12 + today.month-oldest.month + 1)
        years, rem = divmod(months, 12)
        parts=[]
        if years: parts.append(f"{years} year{'s' if years != 1 else ''}")
        if rem: parts.append(f"{rem} month{'s' if rem != 1 else ''}")
        period = ' and '.join(parts) or '1 month'
    return {
        'unpaid_months': count,
        'outstanding_balance': float(row.get('outstanding_balance') or 0),
        'oldest_unpaid_due': oldest.strftime('%B %Y') if oldest else None,
        'unpaid_periods': [r['due_month'].strftime('%B %Y') if hasattr(r.get('due_month'), 'strftime') else str(r.get('due_month')) for r in unpaid_rows],
        'outstanding_period': period,
        'dues_status': 'Outstanding' if count else 'Clear'
    }


def format_pdf_datetime(value):
    """Human-readable presentation for database datetimes used in PDFs."""
    if not value:
        return ''
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S'):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            return text
    return dt.strftime('%B %d, %Y • %I:%M %p').replace(' 0', ' ')


def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


# ---------------------------------------------------------------------------
# Validation helpers (also enforced server-side so URL/API bypass is blocked)
# ---------------------------------------------------------------------------
COLOR_RE = re.compile(r'^[A-Za-z\s\-]+$')


def validate_vehicle_list(vehicles):
    """Returns an error message string, or None if all vehicles are valid."""
    if not vehicles:
        return 'At least one vehicle is required.'
    for idx, v in enumerate(vehicles, start=1):
        model = (v.get('model') or '').strip()
        color = (v.get('color') or '').strip()
        plate = (v.get('plate') or '').strip()
        if not plate:
            return f'Vehicle #{idx}: Plate number is required.'
        if len(model) < 4:
            return f'Vehicle #{idx}: Vehicle Model must be at least 4 characters.'
        if not color or not COLOR_RE.match(color):
            return f'Vehicle #{idx}: Vehicle Color must contain letters only.'
    return None


# ---------------------------------------------------------------------------
# HOA settings (key/value store) — used for Treasurer contact info
# ---------------------------------------------------------------------------
def get_settings(keys=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if keys:
                fmt = ','.join(['%s'] * len(keys))
                cursor.execute(f"SELECT setting_key, setting_value FROM hoa_settings WHERE setting_key IN ({fmt})", tuple(keys))
            else:
                cursor.execute("SELECT setting_key, setting_value FROM hoa_settings")
            rows = cursor.fetchall()
        return {r['setting_key']: r['setting_value'] for r in rows}
    finally:
        conn.close()


def set_setting(key, value, updated_by=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO hoa_settings (setting_key, setting_value, updated_by)
                              VALUES (%s,%s,%s)
                              ON DUPLICATE KEY UPDATE setting_value=%s, updated_by=%s""",
                           (key, value, updated_by, value, updated_by))
    finally:
        conn.close()


def get_treasurer_contact():
    s = get_settings(['treasurer_name', 'treasurer_phone', 'treasurer_email', 'treasurer_office_hours'])
    return {
        'name': s.get('treasurer_name') or 'Office of the Treasurer',
        'phone': s.get('treasurer_phone') or 'N/A',
        'email': s.get('treasurer_email') or 'N/A',
        'office_hours': s.get('treasurer_office_hours') or 'N/A',
    }


# ---------------------------------------------------------------------------
# Audit + notifications
# ---------------------------------------------------------------------------
def log_audit_action(username, role, action, item, prev_val=None, new_val=None):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_logs (username, role, action, item, prev_val, new_val)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, role, action, item,
                  str(prev_val) if prev_val is not None else None,
                  str(new_val) if new_val is not None else None))
        conn.close()
    except Exception as e:
        print(f"Audit log error: {e}")


def create_alert(user_id, text):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO alerts (user_id, text) VALUES (%s, %s)", (user_id, text))
        conn.close()
    except Exception as e:
        print(f"Alert insert error: {e}")


def notification_already_sent(dedupe_key):
    if not dedupe_key:
        return False
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM notification_log WHERE dedupe_key=%s", (dedupe_key,))
            row = cursor.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def send_alert_and_email(user_id, subject, body, related_type=None, related_id=None, dedupe_key=None, important=True):
    """Persist the in-app notification and send the matching workflow email.

    Workflow mail deliberately uses the same initialized Flask-Mail ``mail``
    object and ``Message`` path as the already-working registration-code mail.
    Business actions are committed by their routes before this helper runs, so
    SMTP failure can never roll back an HOA decision.
    """
    user = None
    email_sent = False
    email_error = None
    in_app_exists = False
    email_already_sent = False

    # Dedupe channels independently. An earlier in-app notification (or an
    # earlier FAILED email attempt) must never prevent a later legitimate SMTP
    # attempt. Only a previously successful Email/Sent row suppresses mail.
    if dedupe_key:
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""SELECT channel, status FROM notification_log
                                  WHERE dedupe_key=%s""", (dedupe_key,))
                prior = cursor.fetchall()
            conn.close()
            in_app_exists = any(r.get('channel') == 'In-App' and r.get('status') == 'Sent' for r in prior)
            email_already_sent = any(r.get('channel') == 'Email' and r.get('status') == 'Sent' for r in prior)
        except Exception as exc:
            app.logger.warning('[EMAIL] Dedupe lookup failed for %s: %s', related_id, exc)

    if not in_app_exists:
        create_alert(user_id, f"{subject}: {body}")

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Registered email is the only field required for critical workflow
            # delivery. Older live NFH databases may not yet have the optional
            # email_notifications preference column; verification mail works on
            # those databases because it also depends only on the email address.
            cursor.execute("SELECT email FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
        conn.close()

        # Important workflow events always email. This intentionally avoids
        # making correction/approval/rejection delivery depend on an optional
        # preference column that may be absent in an upgraded database.
        should_email = bool(important)
        recipient = (user.get('email') or '').strip() if user else ''

        if email_already_sent:
            email_sent = True
            email_error = 'already_sent'
        elif recipient and should_email:
            # Match the proven registration verification path: construct a
            # Flask-Mail Message and call the SAME global mail.send(). Do not
            # add a second mail object or frontend recipient source.
            if not app.config.get('MAIL_USERNAME'):
                email_error = 'Mail sender is not configured.'
                app.logger.warning('[EMAIL FAILURE] %s for %s: MAIL_USERNAME is not configured', subject, related_id)
            else:
                try:
                    msg = Message(subject, recipients=[recipient])
                    msg.body = body
                    mail.send(msg)
                    email_sent = True
                    app.logger.info('[EMAIL SUCCESS] %s for %s sent to registered homeowner email %s',
                                    subject, related_id, recipient)
                    print(f"[EMAIL SUCCESS] {subject} for {related_id} sent to {recipient}")
                except Exception as exc:
                    email_error = f'{type(exc).__name__}: {exc}'
                    app.logger.warning('[EMAIL FAILURE] %s for %s to %s: %s',
                                       subject, related_id, recipient, email_error)
                    print(f"[EMAIL FAILURE] {subject} for {related_id} to {recipient}: {email_error}")
        elif not recipient:
            email_error = 'No registered homeowner email address is available.'
            app.logger.warning('[EMAIL FAILURE] %s for %s: homeowner has no registered email', subject, related_id)
        else:
            email_error = 'Email notifications are disabled for this account.'
    except Exception as exc:
        email_error = f'{type(exc).__name__}: {exc}'
        app.logger.warning('[EMAIL FAILURE] Recipient lookup for user_id=%s related_id=%s: %s',
                           user_id, related_id, email_error)

    # Record only channel attempts that were not already successfully logged.
    # Logging errors do not change the already-completed workflow action.
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if not email_already_sent:
                cursor.execute("""INSERT INTO notification_log
                    (user_id, channel, subject, body, recipient, related_type, related_id, dedupe_key, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                               (user_id, 'Email', subject, body,
                                user.get('email') if user else None,
                                related_type, related_id, dedupe_key,
                                'Sent' if email_sent else 'Failed'))
            if not in_app_exists:
                cursor.execute("""INSERT INTO notification_log
                    (user_id, channel, subject, body, related_type, related_id, dedupe_key, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                               (user_id, 'In-App', subject, body,
                                related_type, related_id, dedupe_key, 'Sent'))
        conn.close()
    except Exception as exc:
        app.logger.warning('Notification log insert failed for user_id=%s related_id=%s: %s',
                           user_id, related_id, exc)

    return {'created': not in_app_exists, 'email_sent': email_sent,
            'reason': email_error, 'recipient': user.get('email') if user else None}


def _set_login_session(user):
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['full_name'] = f"{user['first_name']} {user['last_name']}".strip()
    session['role'] = user['role']
    session['email'] = user.get('email', '')
    session['last_activity'] = time.time()
    session.permanent = True


def _role_home_url(role):
    if role in ['Secretary', 'Treasurer', *EXECUTIVE_ROLES]:
        return url_for('officer')
    if role == 'Admin':
        return url_for('admin')
    return url_for('homeowner')


# Prevent stale login/protected HTML from being restored as a usable page via browser cache.
# Static assets keep their normal caching behavior.
@app.after_request
def set_auth_page_cache_headers(response):
    if request.endpoint in {'index', 'register_page', 'homeowner', 'officer', 'admin', 'logout'}:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ===========================================================================
# PAGE ROUTES
# ===========================================================================
@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role', 'Homeowner')
        if role == 'Homeowner':
            return redirect(url_for('homeowner'))
        elif role in ['Secretary', 'Treasurer', *EXECUTIVE_ROLES]:
            return redirect(url_for('officer'))
        elif role == 'Admin':
            return redirect(url_for('admin'))
    return render_template('index.html')


@app.route('/register')
def register_page():
    if 'user_id' in session:
        role = session.get('role', 'Homeowner')
        if role == 'Homeowner':
            return redirect(url_for('homeowner'))
        elif role in ['Secretary', 'Treasurer', *EXECUTIVE_ROLES]:
            return redirect(url_for('officer'))
        elif role == 'Admin':
            return redirect(url_for('admin'))
    return render_template('register.html')


@app.route('/home')
def homeowner():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    if session.get('role') != 'Homeowner':
        return redirect(url_for('index'))
    return render_template('homeowner.html', treasurer=get_treasurer_contact())



# ---------------------------------------------------------------------------
# Officer route (queries homeowners for Treasurer dropdown)
# ---------------------------------------------------------------------------
@app.route('/officer')
def officer():
    if 'user_id' not in session or session.get('role') not in OFFICER_ROLES:
        return redirect(url_for('index'))

    role = session.get('role', 'Secretary')
    username = session.get('username')

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Fetch active homeowners for dropdown selection
            cursor.execute("""
                SELECT id, first_name, last_name, username,
                       CONCAT(first_name, ' ', last_name) AS full_name
                FROM users 
                WHERE role = 'Homeowner' AND status = 'Active'
                ORDER BY last_name ASC, first_name ASC
            """)
            homeowners = cursor.fetchall()

            # Fetch active standard pricing configuration
            cursor.execute("SELECT item_name, amount, proposed_amount, status FROM fees ORDER BY item_name ASC")
            fees_rows = cursor.fetchall()
            fees = {
                row['item_name']: {
                    'amount': float(row['amount']),
                    'proposed_amount': float(row['proposed_amount']) if row.get('proposed_amount') is not None else None,
                    'status': row['status']
                } for row in fees_rows
            }

            # Fetch official fixed monthly due amount from active fees (defaults to 100.00 if missing)
            official_monthly_due = fees.get('Monthly Dues', {}).get('amount', 100.00)

            cursor.execute("""
                SELECT r.id, CONCAT(u.first_name,' ',u.last_name) AS homeowner, r.request_type,
                       r.category, r.submission_type,
                       r.assigned_officer, r.status, r.payment_status, r.fee, r.details, r.attachment, r.remarks,
                       DATE_FORMAT(r.date_submitted,'%Y-%m-%d %H:%i') AS date_submitted,
                       DATE_FORMAT(r.last_updated,'%Y-%m-%d %H:%i') AS last_updated,
                       r.user_id
                FROM requests r JOIN users u ON r.user_id=u.id
                ORDER BY r.date_submitted DESC
            """)
            all_requests = cursor.fetchall()
            for _req in all_requests:
                _req['dues'] = dues_summary(cursor, _req['user_id'])

            active_requests = [r for r in all_requests if r['status'] != 'Cancelled']

            # Role queues are driven by request type + current database status.
            # `checking_requests` is the actionable initial-review queue; payment
            # processing remains a separate Approved/Unpaid Treasurer stage.
            checking_requests = [r for r in active_requests if request_is_check_actionable(r, role)]
            if role == 'Secretary':
                assigned_requests = checking_requests
            elif role == 'Treasurer':
                assigned_requests = [r for r in active_requests if r['status'] == 'Approved' and r['payment_status'] == 'Unpaid']
            elif role in EXECUTIVE_ROLES:
                assigned_requests = [r for r in active_requests if r['status'] == 'Pending Executive Approval']
            else:
                assigned_requests = active_requests

            cursor.execute("SELECT id, CONCAT(first_name,' ',last_name) AS full_name, username, email, mobile, role, status, created_at FROM users WHERE id=%s", (session['user_id'],))
            current_user = cursor.fetchone()

            if role in EXECUTIVE_ROLES:
                cursor.execute("SELECT * FROM audit_logs WHERE role IN ('President','Vice President','Board Director') ORDER BY timestamp ASC")
            else:
                cursor.execute("SELECT * FROM audit_logs WHERE role=%s OR username=%s ORDER BY timestamp ASC", (role, username))
            audits_rows = cursor.fetchall()

            concerns = []
            if role in ('Secretary','Treasurer'):
                cursor.execute("""SELECT c.*, r.request_type, r.assigned_officer,
                                  CONCAT(u.first_name,' ',u.last_name) AS homeowner
                           FROM request_concerns c
                           JOIN requests r ON r.id=c.request_id
                           JOIN users u ON u.id=c.user_id
                           WHERE c.assigned_role=%s
                           ORDER BY c.updated_at DESC""", (role,))
                concerns = cursor.fetchall()

            executive_history = []
            if role in EXECUTIVE_ROLES:
                cursor.execute("""SELECT r.id, r.request_type, r.status, r.executive_decision_reason,
                                  r.executive_decision_details, r.executive_decided_by,
                                  r.executive_decided_role, r.executive_decided_at,
                                  CONCAT(u.first_name,' ',u.last_name) AS homeowner
                           FROM requests r JOIN users u ON u.id=r.user_id
                           WHERE r.executive_decided_at IS NOT NULL
                           ORDER BY r.executive_decided_at DESC LIMIT 50""")
                executive_history = cursor.fetchall()

            financial_adjustments = []
            if role in ['Treasurer', 'Admin']:
                cursor.execute("SELECT * FROM financial_adjustments ORDER BY created_at DESC")
                financial_adjustments = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Officer Route Error: {e}")
        return render_template('officer.html', role=role, requests=[], assigned_requests=[], checking_requests=[],
                               fees={}, audits=[], financial_adjustments=[], homeowners=[],
                               official_monthly_due=100.00, treasurer=get_treasurer_contact(), current_user=None, concerns=[], executive_history=[])

    if 'full_name' not in session:
        session['full_name'] = username

    return render_template('officer.html', role=role, requests=all_requests,
                           assigned_requests=assigned_requests, checking_requests=checking_requests, fees=fees,
                           audits=audits_rows, financial_adjustments=financial_adjustments,
                           homeowners=homeowners, official_monthly_due=official_monthly_due,
                           treasurer=get_treasurer_contact(), current_user=current_user, concerns=concerns, executive_history=executive_history)


# ---------------------------------------------------------------------------
# Admin route
# ---------------------------------------------------------------------------
@app.route('/admin')
def admin():
    if 'user_id' not in session or session.get('role') != 'Admin':
        flash('Unauthorized access. Admin privileges required.', 'error')
        return redirect(url_for('index'))

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role='Homeowner'")
            total_homeowners = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) AS total FROM requests")
            total_requests = cursor.fetchone()['total']
            cursor.execute(
                "SELECT COUNT(*) AS total FROM requests WHERE status IN ('Submitted','Under Review','Checked','For Correction')")
            pending_requests = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) AS total FROM requests WHERE status='Pending Executive Approval'")
            pending_executive = cursor.fetchone()['total']
            cursor.execute(
                "SELECT COUNT(*) AS total FROM users WHERE role IN ('Secretary','Treasurer','President','Vice President','Board Director') AND status='Active'")
            active_officers = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) AS total FROM fees WHERE status='Pending Executive Approval'")
            pending_fee_changes = cursor.fetchone()['total']

            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp ASC")
            audits_rows = cursor.fetchall()

            cursor.execute("""
                SELECT id, CONCAT(first_name,' ',last_name) AS full_name, username, email, mobile, role, status, created_at
                FROM users WHERE role IN ('Secretary','Treasurer','President','Vice President','Board Director') ORDER BY created_at DESC
            """)
            officers = cursor.fetchall()

            cursor.execute("""
                SELECT r.id, CONCAT(u.first_name,' ',u.last_name) AS homeowner, r.request_type, r.category,
                       r.submission_type, r.assigned_officer, r.status, r.payment_status,
                       DATE_FORMAT(r.date_submitted,'%Y-%m-%d %H:%i') AS date_submitted,
                       DATE_FORMAT(r.last_updated,'%Y-%m-%d %H:%i') AS last_updated
                FROM requests r JOIN users u ON r.user_id=u.id ORDER BY r.date_submitted DESC
            """)
            requests_list = cursor.fetchall()

            cursor.execute("SELECT item_name, amount, proposed_amount, status FROM fees ORDER BY item_name ASC")
            fees_rows = cursor.fetchall()
            fees = {
                row['item_name']: {
                    'amount': float(row['amount']),
                    'proposed_amount': float(row['proposed_amount']) if row.get(
                        'proposed_amount') is not None else None,
                    'status': row['status']
                } for row in fees_rows
            }

            cursor.execute("SELECT * FROM requests WHERE status='Cancelled' ORDER BY last_updated DESC")
            cancellations = cursor.fetchall()
            cursor.execute("SELECT * FROM financial_adjustments ORDER BY created_at DESC")
            financial_adjustments = cursor.fetchall()
            cursor.execute("SELECT * FROM notification_log ORDER BY sent_at DESC LIMIT 200")
            notifications_log = cursor.fetchall()
            cursor.execute("SELECT id, CONCAT(first_name,' ',last_name) AS full_name, username, email, mobile, role, status, created_at FROM users WHERE id=%s", (session['user_id'],))
            current_user = cursor.fetchone()

        conn.close()
    except Exception as e:
        print(f"Admin Route Error: {e}")
        return render_template('admin.html',
                               metrics={'total_homeowners': 0, 'total_requests': 0, 'pending_requests': 0,
                                        'pending_executive': 0, 'active_officers': 0, 'pending_fee_changes': 0},
                               audits=[], officers=[], requests=[], fees={}, cancellations=[],
                               financial_adjustments=[], notifications_log=[], current_user=None)

    if 'full_name' not in session:
        session['full_name'] = session.get('username', 'System Admin')

    metrics = {
        'total_homeowners': total_homeowners, 'total_requests': total_requests,
        'pending_requests': pending_requests, 'pending_executive': pending_executive,
        'active_officers': active_officers, 'pending_fee_changes': pending_fee_changes
    }

    return render_template('admin.html', metrics=metrics, audits=audits_rows,
                           officers=officers, requests=requests_list, fees=fees,
                           cancellations=cancellations, financial_adjustments=financial_adjustments,
                           notifications_log=notifications_log, current_user=current_user)


# ===========================================================================
# OFFICER WORKFLOW ENDPOINTS
# ===========================================================================
@app.route('/officer/check_request/<req_id>', methods=['POST'])
def check_request(req_id):
    if 'user_id' not in session or session.get('role') not in ['Secretary', 'Treasurer', 'Admin']:
        return redirect(url_for('index'))

    role = session.get('role')
    action = request.form.get('action')
    remarks = request.form.get('remarks', '').strip()

    # Only the two existing initial-check workflow actions are valid. Reject a
    # missing/unknown action instead of silently storing the intermediate
    # 'Checked' status, because the Executive queue is keyed to
    # 'Pending Executive Approval'.
    if action not in ('check', 'correction'):
        flash('Invalid request review action. Please try again.', 'error')
        return redirect(url_for('officer'))

    # Requirement: Officer Remarks are REQUIRED when returning a request for correction.
    if action == 'correction' and not remarks:
        flash('Officer Remarks are required when returning a request for correction.', 'error')
        return redirect(url_for('officer'))

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, request_type, user_id, assigned_officer FROM requests WHERE id=%s", (req_id,))
            prev_req = cursor.fetchone()
            if not prev_req:
                conn.close()
                return redirect(url_for('officer'))
            prev_status = prev_req['status']
            if prev_status == 'Cancelled':
                conn.close()
                flash('Cannot process a cancelled request.', 'error')
                return redirect(url_for('officer'))
            if prev_status not in ('Submitted', 'Under Review'):
                conn.close()
                flash('This request is no longer available for initial officer checking.', 'error')
                return redirect(url_for('officer'))

            if not role_can_initial_check(role, prev_req['request_type'], prev_req.get('assigned_officer')):
                conn.close()
                flash(f'{role} is not authorized to perform the initial checking for {prev_req["request_type"]}.', 'error')
                return redirect(url_for('officer'))

            # A successful authorized check is the handoff to the Executive.
            # Correction retains the actual checker so resubmission returns to
            # the correct Secretary/Treasurer workflow for shared request types.
            new_status = 'Pending Executive Approval' if action == 'check' else 'For Correction'
            checker = role if role in {'Secretary', 'Treasurer'} else prev_req.get('assigned_officer')

            cursor.execute("UPDATE requests SET status=%s, remarks=%s, assigned_officer=%s WHERE id=%s AND status IN ('Submitted','Under Review')",
                           (new_status, remarks, checker, req_id))
            if cursor.rowcount != 1:
                conn.close()
                flash('This request was already processed by another officer. Refresh the queue to see its current status.', 'warning')
                return redirect(url_for('officer'))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'),
                         f'Request {action.title()}', req_id, prev_status, new_status)

        correction_delivery = None
        if new_status == 'For Correction':
            # Fetch the homeowner name for a clear, professional correction email.
            homeowner_name = 'Homeowner'
            try:
                c2 = get_db_connection()
                with c2.cursor() as cursor:
                    cursor.execute("SELECT first_name, last_name FROM users WHERE id=%s", (prev_req['user_id'],))
                    homeowner = cursor.fetchone()
                c2.close()
                if homeowner:
                    homeowner_name = f"{homeowner.get('first_name') or ''} {homeowner.get('last_name') or ''}".strip() or 'Homeowner'
            except Exception as exc:
                app.logger.warning('Could not resolve homeowner name for correction email %s: %s', req_id, exc)

            officer_name = session.get('full_name') or session.get('username') or 'HOA Officer'
            officer_label = role if role in {'Secretary', 'Treasurer'} else 'HOA Officer'
            subject = f'NFH-HOA Request Requires Correction — {req_id}'
            body = (
                f"Dear {homeowner_name},\n\n"
                f"Your {prev_req['request_type']} request ({req_id}) has been returned for correction by the {officer_label}.\n\n"
                f"Status: For Correction\n"
                f"Officer Remarks: {remarks}\n\n"
                "Please sign in to the NFH-HOA system to review the remarks, make the necessary corrections, "
                "and resubmit your request. Your existing request ID will be retained.\n\n"
                "Thank you,\nNorth Fairway Homes Homeowners' Association"
            )
            # A unique correction cycle begins only when an authorized officer
            # performs this POST action. Refreshing/viewing the request cannot resend it.
            correction_delivery = send_alert_and_email(
                prev_req['user_id'], subject, body,
                related_type='request', related_id=req_id,
                dedupe_key=f"correction-{req_id}-{prev_status}-{int(time.time())}")

        flash(f'Request {req_id} updated to {new_status}.', 'success')
        if correction_delivery and not correction_delivery.get('email_sent'):
            flash('The homeowner was notified in the system, but the correction email could not be delivered. Please check the email/SMTP configuration.', 'warning')
    except Exception as e:
        flash(f'Error updating request: {str(e)}', 'error')
    return redirect(url_for('officer'))


@app.route('/officer/update_payment/<req_id>', methods=['POST'])
def update_payment(req_id):
    """Simple 'Mark as Paid' action (Treasurer/Admin). A request can only be
    marked Paid once it has already been Approved (Requirement: Payment
    Restriction). This replaces the old detailed Payment Recording feature."""
    if 'user_id' not in session or session.get('role') not in ['Treasurer', 'Admin']:
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, payment_status, request_type, user_id FROM requests WHERE id=%s", (req_id,))
            req = cursor.fetchone()
            if not req:
                conn.close()
                flash('Request not found.', 'error')
                return redirect(url_for('officer'))
            if req['payment_status'] == 'Paid':
                conn.close()
                flash('Payment already recorded for this request.', 'info')
                return redirect(url_for('officer'))
            if req['status'] != 'Approved':
                conn.close()
                flash('A request cannot be marked as Paid unless it has been Approved.', 'error')
                return redirect(url_for('officer'))

            cursor.execute("UPDATE requests SET payment_status='Paid', status='Paid and Approved' WHERE id=%s", (req_id,))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'), 'Mark Payment as Paid',
                         req_id, 'Unpaid', 'Paid')
        send_alert_and_email(
            req['user_id'], 'Your Request Has Been Paid and Approved',
            f"Your request for {req['request_type']} has been successfully paid and approved. "
            f"You may now proceed to claim/receive the corresponding hardcopy document.",
            related_type='request', related_id=req_id, dedupe_key=f'paid-approved-{req_id}')
        flash(f'Request {req_id} marked as Paid.', 'success')
    except Exception as e:
        flash(f'Error updating payment status: {str(e)}', 'error')
    return redirect(url_for('officer'))


@app.route('/officer/propose_fee', methods=['POST'])
def propose_fee():
    if 'user_id' not in session or session.get('role') not in ['Treasurer', 'Admin']:
        return redirect(url_for('index'))
    fee_name = request.form.get('fee_name')
    amount = request.form.get('amount')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT amount FROM fees WHERE item_name=%s", (fee_name,))
            row = cursor.fetchone()
            prev = float(row['amount']) if row else None
            cursor.execute("UPDATE fees SET proposed_amount=%s, status='Pending Executive Approval' WHERE item_name=%s",
                           (amount, fee_name))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'), 'Propose Fee Update', fee_name, prev, amount)
        flash(f'Proposed fee for {fee_name} submitted for Executive approval.', 'success')
    except Exception as e:
        flash(f'Error proposing fee update: {str(e)}', 'error')
    return redirect(url_for('officer'))


@app.route('/officer/update-treasurer-contact', methods=['POST'])
def update_treasurer_contact():
    if 'user_id' not in session or session.get('role') not in ['Treasurer', 'Admin']:
        return redirect(url_for('index'))
    name = request.form.get('treasurer_name', '').strip()
    phone = request.form.get('treasurer_phone', '').strip()
    email = request.form.get('treasurer_email', '').strip()
    office_hours = request.form.get('treasurer_office_hours', '').strip()
    if not name or not phone:
        flash('Treasurer name and contact number are required.', 'error')
        return redirect(url_for('officer'))
    try:
        who = session.get('username')
        set_setting('treasurer_name', name, who)
        set_setting('treasurer_phone', phone, who)
        set_setting('treasurer_email', email, who)
        set_setting('treasurer_office_hours', office_hours, who)
        log_audit_action(who, session.get('role'), 'Update Treasurer Contact Info', 'hoa_settings', None, name)
        flash('Treasurer contact information updated.', 'success')
    except Exception as e:
        flash(f'Error updating contact information: {str(e)}', 'error')
    return redirect(url_for('officer'))


@app.route('/officer/president_action/<req_id>', methods=['POST'])
def president_action(req_id):
    if 'user_id' not in session or session.get('role') not in EXECUTIVE_ROLES + ['Admin']:
        return redirect(url_for('index'))
    action = request.form.get('action')
    reason = (request.form.get('rejection_reason') or '').strip()
    details = (request.form.get('rejection_details') or '').strip()
    if action not in ('approve', 'reject'):
        flash('Invalid Executive decision. Please try again.', 'error')
        return redirect(url_for('officer'))
    if action == 'reject' and reason not in ('Outstanding Dues', 'Other'):
        flash('Select a valid rejection reason.', 'error')
        return redirect(url_for('officer'))
    if action == 'reject' and reason == 'Other' and not details:
        flash('Please provide the reason for rejection.', 'error')
        return redirect(url_for('officer'))
    new_status = 'Approved' if action == 'approve' else 'Rejected'
    mail_result = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""SELECT r.status, r.payment_status, r.request_type, r.user_id,
                                      CONCAT(u.first_name,' ',u.last_name) AS homeowner
                       FROM requests r JOIN users u ON u.id=r.user_id WHERE r.id=%s""", (req_id,))
            req = cursor.fetchone()
            if not req or req['status'] != 'Pending Executive Approval':
                conn.close(); flash('This request has already been decided. Refresh the page to view the latest status.', 'error'); return redirect(url_for('officer'))
            dues = dues_summary(cursor, req['user_id'])
            if action == 'approve' and dues['unpaid_months'] > 0:
                create_alert(req['user_id'], f"Executive approval for request {req_id} is blocked because your account has outstanding monthly dues.")
                conn.close(); flash('Approval is blocked because this homeowner has outstanding monthly dues.', 'error'); return redirect(url_for('officer'))
            if action == 'reject' and reason == 'Outstanding Dues' and dues['unpaid_months'] <= 0:
                conn.close(); flash('This homeowner currently has no outstanding monthly dues. Choose Other if there is another rejection reason.', 'error'); return redirect(url_for('officer'))
            prev_status=req['status']
            decision_note = details if reason == 'Other' else reason if action == 'reject' else None
            cursor.execute("""UPDATE requests SET status=%s, remarks=%s,
                                      executive_decision_reason=%s, executive_decision_details=%s,
                                      executive_decided_by=%s, executive_decided_role=%s, executive_decided_at=NOW()
                                      WHERE id=%s""",
                           (new_status, decision_note, reason if action=='reject' else None,
                            details if action=='reject' else None, session.get('full_name') or session.get('username'),
                            session.get('role'), req_id))
        conn.close()
        if action == 'approve':
            mail_result = send_approval_email(
                req_id, req['request_type'], req['user_id'],
                session.get('full_name') or session.get('username') or 'HOA Executive',
                session.get('role') or 'Executive'
            )
        else:
            reason_text = reason + (f"\nDetails: {details}" if details else '')
            body=(f"Dear {req['homeowner']},\n\nYour {req['request_type']} request ({req_id}) has been rejected.\n\n"
                  f"Reason: {reason_text}\n\nThis decision was recorded by {session.get('full_name') or session.get('username')}, {session.get('role')}.\n\n"
                  f"Please review your NFH-HOA account and the information shown in the system.\n\nThank you,\nNorth Fairway Homes Homeowners' Association")
            mail_result=send_alert_and_email(req['user_id'], f"NFH-HOA Request Rejected — {req_id}", body,
                                             related_type='request', related_id=req_id, dedupe_key=f'rejection-{req_id}')
        log_audit_action(session.get('username'), session.get('role'), f'Executive Decision ({action.title()})', req_id,
                         prev_status, f"{new_status}" + (f" — {reason}: {details}" if action=='reject' and details else f" — {reason}" if action=='reject' else ''))
        flash('Request approved successfully.' if action == 'approve' else 'Request rejected successfully.', 'success')
        if mail_result and not mail_result.get('email_sent'):
            event_label = 'approval' if action == 'approve' else 'rejection'
            flash(f'The {event_label} was saved and the in-app notification was created, but the email could not be delivered.', 'warning')
    except Exception as e:
        print(f'Executive decision error for {req_id}: {e}')
        flash('Unable to record the Executive decision. Please try again.', 'error')
    return redirect(url_for('officer'))


@app.route('/officer/president_fee_action', methods=['POST'])
def president_fee_action():
    if 'user_id' not in session or session.get('role') not in EXECUTIVE_ROLES + ['Admin']:
        return redirect(url_for('index'))
    fee_name = request.form.get('fee_name')
    action = request.form.get('action')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT amount, proposed_amount FROM fees WHERE item_name=%s", (fee_name,))
            fee = cursor.fetchone()
            if action == 'approve' and fee and fee['proposed_amount']:
                cursor.execute(
                    "UPDATE fees SET amount=proposed_amount, proposed_amount=NULL, status='Active' WHERE item_name=%s",
                    (fee_name,))
                log_audit_action(session.get('username'), session.get('role'), 'Approve Fee Update', fee_name,
                                 fee['amount'], fee['proposed_amount'])
                flash(f'Fee update for {fee_name} approved and activated.', 'success')
            else:
                cursor.execute("UPDATE fees SET proposed_amount=NULL, status='Active' WHERE item_name=%s", (fee_name,))
                log_audit_action(session.get('username'), session.get('role'), 'Reject Fee Update', fee_name,
                                 fee['proposed_amount'], 'Rejected')
                flash(f'Fee proposal for {fee_name} rejected.', 'info')
        conn.close()
    except Exception as e:
        flash(f'Error processing fee approval: {str(e)}', 'error')
    return redirect(url_for('officer'))


# ===========================================================================
# OWNER APIS
# ===========================================================================


# ===========================================================================
# ROLE-AWARE LIVE DASHBOARD METRICS (lightweight polling endpoint)
# ===========================================================================
@app.route('/api/live-metrics', methods=['GET'])
def live_metrics():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    role = session.get('role')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            def count(sql, params=()):
                cursor.execute(sql, params)
                return int(cursor.fetchone()['total'] or 0)

            if role == 'Admin':
                metrics = {
                    'total_homeowners': count("SELECT COUNT(*) total FROM users WHERE role='Homeowner'"),
                    'total_requests': count("SELECT COUNT(*) total FROM requests"),
                    'pending_requests': count("SELECT COUNT(*) total FROM requests WHERE status IN ('Submitted','Under Review','Checked','For Correction')"),
                    'pending_executive': count("SELECT COUNT(*) total FROM requests WHERE status='Pending Executive Approval'"),
                    'active_officers': count("SELECT COUNT(*) total FROM users WHERE role IN ('Secretary','Treasurer','President','Vice President','Board Director') AND status='Active'"),
                    'pending_fee_changes': count("SELECT COUNT(*) total FROM fees WHERE status='Pending Executive Approval'"),
                    'approved_requests': count("SELECT COUNT(*) total FROM requests WHERE status IN ('Approved','Paid and Approved')"),
                    'paid_requests': count("SELECT COUNT(*) total FROM requests WHERE payment_status='Paid'"),
                    'missing_dues': count("SELECT COUNT(*) total FROM monthly_dues WHERE status='Unpaid'"),
                }
            elif role == 'Secretary':
                metrics = {
                    'pending_requests': count("SELECT COUNT(*) total FROM requests WHERE status IN ('Submitted','Under Review') AND request_type IN ('Certificate of Improvement','Proof of Residency','Move-in Gate Pass','Move-out Gate Pass','Certificate of Membership','Vehicle Sticker Application','Renters/Tenants Information Form') AND (request_type NOT IN ('Vehicle Sticker Application','Renters/Tenants Information Form') OR assigned_officer IS NULL OR assigned_officer='Secretary')"),
                    'for_correction': count("SELECT COUNT(*) total FROM requests WHERE status='For Correction' AND request_type IN ('Certificate of Improvement','Proof of Residency','Move-in Gate Pass','Move-out Gate Pass','Certificate of Membership','Vehicle Sticker Application','Renters/Tenants Information Form') AND (request_type NOT IN ('Vehicle Sticker Application','Renters/Tenants Information Form') OR assigned_officer='Secretary')"),
                    'checked_requests': count("SELECT COUNT(*) total FROM requests WHERE status='Checked'"),
                    'pending_executive': count("SELECT COUNT(*) total FROM requests WHERE status='Pending Executive Approval'"),
                    'recent_submitted': count("SELECT COUNT(*) total FROM requests WHERE status='Submitted' AND date_submitted >= NOW() - INTERVAL 7 DAY"),
                }
            elif role in EXECUTIVE_ROLES:
                metrics = {
                    'pending_request_approvals': count("SELECT COUNT(*) total FROM requests WHERE status='Pending Executive Approval'"),
                    'pending_fee_approvals': count("SELECT COUNT(*) total FROM fees WHERE status='Pending Executive Approval'"),
                    'recently_approved': count("SELECT COUNT(*) total FROM requests WHERE status IN ('Approved','Paid and Approved') AND last_updated >= NOW() - INTERVAL 7 DAY"),
                    'for_correction': count("SELECT COUNT(*) total FROM requests WHERE status='For Correction'"),
                }
            elif role == 'Treasurer':
                cursor.execute("SELECT COALESCE(SUM(amount),0) total FROM monthly_dues WHERE status='Unpaid'")
                outstanding = float(cursor.fetchone()['total'] or 0)
                metrics = {
                    'requests_for_checking': count("SELECT COUNT(*) total FROM requests WHERE status IN ('Submitted','Under Review') AND request_type IN ('Gate Pass','Vehicle Sticker Application','Renters/Tenants Information Form') AND (request_type='Gate Pass' OR assigned_officer IS NULL OR assigned_officer='Treasurer')"),
                    'approved_unpaid': count("SELECT COUNT(*) total FROM requests WHERE status='Approved' AND payment_status='Unpaid'"),
                    'paid_requests': count("SELECT COUNT(*) total FROM requests WHERE payment_status='Paid'"),
                    'missing_dues': count("SELECT COUNT(*) total FROM monthly_dues WHERE status='Unpaid'"),
                    'outstanding_dues_total': outstanding,
                    'recently_paid': count("SELECT COUNT(*) total FROM requests WHERE payment_status='Paid' AND last_updated >= NOW() - INTERVAL 7 DAY"),
                }
            else:
                metrics = {}
        conn.close()
        return jsonify({'status':'success','role':role,'metrics':metrics,'updated_at':datetime.now().strftime('%H:%M:%S')})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500

@app.route('/api/user-data', methods=['GET'])
def get_user_data():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
            cursor.execute("SELECT item_name, amount FROM fees WHERE status='Active'")
            fees_rows = cursor.fetchall()
            fees_dict = {f['item_name']: float(f['amount']) for f in fees_rows}
            cursor.execute("SELECT * FROM requests WHERE user_id=%s ORDER BY date_submitted DESC", (user_id,))
            requests_rows = cursor.fetchall()
            cursor.execute("SELECT * FROM alerts WHERE user_id=%s ORDER BY time DESC", (user_id,))
            alerts_rows = cursor.fetchall()
            cursor.execute("""SELECT * FROM monthly_dues WHERE user_id=%s AND status='Unpaid'
                              ORDER BY due_month ASC""", (user_id,))
            missing_dues_rows = cursor.fetchall()
        conn.close()

        if user:
            user.pop('password_hash', None)
            if user.get('profile_image'):
                user['profile_image'] = f"/static/uploads/{os.path.basename(user['profile_image'])}"
            if user.get('dob'):
                user['dob'] = user['dob'].strftime('%Y-%m-%d')
            if user.get('date_joined'):
                user['date_joined'] = user['date_joined'].strftime('%Y-%m-%d')
            user['emergency'] = {
                'name': user.get('emergency_contact_name'),
                'number': user.get('emergency_contact_number'),
                'relationship': user.get('emergency_contact_relationship'),
            }

        req_list, active_count, outstanding_dues = [], 0, 0.0
        for r in requests_rows:
            status = r['status']
            payment_status = r['payment_status']
            fee_val = float(r['fee'])
            if status in ['Submitted', 'Under Review', 'Checked', 'Pending Executive Approval', 'For Correction']:
                active_count += 1
            if payment_status == 'Unpaid' and status not in ['Rejected', 'Cancelled']:
                outstanding_dues += fee_val
            req_list.append({
                'id': r['id'], 'type': r['request_type'], 'title': r['request_type'],
                'category': r.get('category') or 'Document Request',
                'date': r['date_submitted'].strftime('%Y-%m-%d %H:%M') if r.get('date_submitted') else '',
                'fee': f"₱{fee_val:.2f}", 'payment_status': payment_status, 'status': status,
                'remarks': r.get('remarks') or '', 'details': r.get('details') or '{}'
            })

        alert_list = [{'id': a['id'], 'text': a['text'],
                       'time': a['time'].strftime('%Y-%m-%d %H:%M') if a.get('time') else '',
                       'unread': bool(a['unread'])} for a in alerts_rows]
        unread_alerts_count = sum(1 for a in alert_list if a['unread'])

        missing_dues_total = sum(float(m['amount']) for m in missing_dues_rows)
        monthly_dues_summary = dues_summary(get_db_connection().cursor(), user_id) if False else None
        if missing_dues_rows:
            oldest = missing_dues_rows[0].get('due_month')
            today = datetime.now().date().replace(day=1)
            if isinstance(oldest, datetime): oldest = oldest.date()
            months_elapsed = max(1, (today.year-oldest.year)*12 + today.month-oldest.month + 1) if oldest else len(missing_dues_rows)
            years, rem = divmod(months_elapsed, 12)
            period_parts = ([f"{years} year{'s' if years != 1 else ''}"] if years else []) + ([f"{rem} month{'s' if rem != 1 else ''}"] if rem else [])
            outstanding_period = ' and '.join(period_parts) or '1 month'
            oldest_unpaid_due = oldest.strftime('%B %Y') if oldest else None
        else:
            outstanding_period = 'Clear'
            oldest_unpaid_due = None
        missing_dues_list = [{
            'due_month': m['due_month'].strftime('%Y-%m') if m.get('due_month') else '',
            'amount': f"₱{float(m['amount']):.2f}"
        } for m in missing_dues_rows]

        return jsonify({'status': 'success', 'user': user, 'fees': fees_dict, 'dashboard': {
            'active_requests': active_count, 'outstanding_dues': outstanding_dues,
            'unread_alerts': unread_alerts_count, 'requests': req_list, 'alerts': alert_list,
            'missing_dues_count': len(missing_dues_rows), 'missing_dues_total': missing_dues_total,
            'oldest_unpaid_due': oldest_unpaid_due, 'outstanding_period': outstanding_period,
            'dues_status': 'Outstanding' if missing_dues_rows else 'Clear', 'missing_dues': missing_dues_list
        }, 'treasurer': get_treasurer_contact()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""UPDATE users SET
                first_name=%s, middle_name=%s, last_name=%s, suffix=%s,
                gender=%s, dob=%s, civil_status=%s, block=%s, lot=%s,
                email=%s, mobile=%s, household=%s WHERE id=%s""",
                           (data.get('first_name'), data.get('middle_name'), data.get('last_name'),
                            data.get('suffix'), data.get('gender'), data.get('dob') or None,
                            data.get('civil_status'), data.get('block'), data.get('lot'),
                            data.get('email'), data.get('mobile'), data.get('household', 1), user_id))
        conn.close()
        return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/profile/photo', methods=['POST'])
def upload_profile_photo():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded.'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'status': 'error', 'message': 'No file selected.'}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'status': 'error', 'message': 'File too large. Maximum 5MB.'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'status': 'error', 'message': 'Invalid format. Only JPG, JPEG, PNG allowed.'}), 400

    filename = secure_filename(f"{session['user_id']}_{int(time.time())}.{ext}")
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    image_url = f"/static/uploads/{filename}"
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET profile_image=%s WHERE id=%s", (image_url, session['user_id']))
        conn.close()
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'success', 'message': 'Profile picture updated.', 'image_url': image_url})


@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if 'emergency' in data:
                em = data['emergency']
                cursor.execute("""UPDATE users SET
                    emergency_contact_name=%s, emergency_contact_number=%s,
                    emergency_contact_relationship=%s WHERE id=%s""",
                               (em.get('name'), em.get('number'), em.get('relationship'), user_id))
            if 'preferences' in data:
                cursor.execute("""UPDATE users SET email_notifications=%s, sms_notifications=%s
                                  WHERE id=%s""",
                               (1 if data['preferences'].get('email') else 0,
                                1 if data['preferences'].get('sms') else 0, user_id))
        conn.close()
        return jsonify({'status': 'success', 'message': 'Settings updated.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/settings/password', methods=['POST'])
def update_password():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    if not all([data.get('current_password'), data.get('new_password')]):
        return jsonify({'status': 'error', 'message': 'All fields required.'}), 400
    if len(data.get('new_password','')) < 8:
        return jsonify({'status': 'error', 'message': 'New password must be at least 8 characters.'}), 400
    if data['new_password'] != data.get('confirm_password'):
        return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT password_hash FROM users WHERE id=%s", (session['user_id'],))
            u = cursor.fetchone()
            if not u or not check_password_hash(u['password_hash'], data['current_password']):
                conn.close()
                return jsonify({'status': 'error', 'message': 'Current password incorrect.'}), 400
            cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                           (generate_password_hash(data['new_password'], method='pbkdf2:sha256'), session['user_id']))
        conn.close()
        return jsonify({'status': 'success', 'message': 'Password changed successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ---------------------------------------------------------------------------
# Submit request
# ---------------------------------------------------------------------------
VALID_CATEGORIES = ['Document Request', 'Property & Moving', 'Vehicle Services', 'Tenant Services']


@app.route('/api/requests/submit', methods=['POST'])
def submit_request():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    title = data.get('title', 'Document Request')
    form_data = data.get('formData', {})
    category = data.get('category') if data.get('category') in VALID_CATEGORIES else 'Document Request'
    submission_type = 'Query'  # legacy DB compatibility; no longer exposed as a homeowner classification
    user_id = session['user_id']

    # Server-side validation for Vehicle Sticker requests (cannot be bypassed via direct API calls)
    if 'Vehicle' in title:
        err = validate_vehicle_list(form_data.get('vehicles', []))
        if err:
            return jsonify({'status': 'error', 'message': err}), 400

    req_id = f"REQ-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT amount FROM fees WHERE item_name=%s AND status='Active'", (title,))
            fee_row = cursor.fetchone()
            fee_amount = float(fee_row['amount']) if fee_row else 50.00
            if 'Vehicle' in title and 'vehicles' in form_data:
                cursor.execute("SELECT item_name, amount FROM fees WHERE status='Active'")
                all_fees = {f['item_name']: float(f['amount']) for f in cursor.fetchall()}
                p4 = all_fees.get('Vehicle Sticker (4 Wheels)', 200.0)
                p2 = all_fees.get('Vehicle Sticker (2/3 Wheels)', 100.0)
                fee_amount = sum(p4 if v.get('type') == '4 Wheels' else p2 for v in form_data.get('vehicles', []))

            cursor.execute("""INSERT INTO requests
                (id, user_id, request_type, category, submission_type, fee, details, status, payment_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'Submitted','Unpaid')""",
                           (req_id, user_id, title, category, submission_type, fee_amount, json.dumps(form_data)))
        conn.close()

        log_audit_action(session.get('username'), session.get('role'), 'Submit Request', title, None, req_id)
        return jsonify({'status': 'success', 'message': f'Request {req_id} submitted successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/requests/concern', methods=['POST'])
def submit_request_concern():
    if 'user_id' not in session or session.get('role') != 'Homeowner':
        return jsonify({'status':'error','message':'Unauthorized'}), 401
    data=request.get_json() or {}; req_id=(data.get('request_id') or '').strip(); message=(data.get('message') or '').strip()
    if not req_id or len(message) < 5:
        return jsonify({'status':'error','message':'Please enter a clear concern.'}), 400
    try:
        conn=get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT request_type, assigned_officer FROM requests WHERE id=%s AND user_id=%s", (req_id,session['user_id']))
            req=cursor.fetchone()
            if not req: conn.close(); return jsonify({'status':'error','message':'Request not found.'}),404
            assigned=req.get('assigned_officer') if req.get('assigned_officer') in ('Secretary','Treasurer') else sorted(initial_checker_roles(req['request_type']))[0]
            if assigned not in ('Secretary','Treasurer'): assigned='Secretary'
            cursor.execute("""INSERT INTO request_concerns (request_id,user_id,assigned_role,concern_text,status)
                              VALUES (%s,%s,%s,%s,'Open')""",(req_id,session['user_id'],assigned,message))
        conn.close()
        log_audit_action(session.get('username'),'Homeowner','Request Concern Submitted',req_id,None,f'Assigned to {assigned}')
        return jsonify({'status':'success','message':f'Your concern for {req_id} was submitted to the {assigned}.'})
    except Exception as e: return jsonify({'status':'error','message':str(e)}),500

@app.route('/api/requests/concerns', methods=['GET'])
def homeowner_concerns():
    if 'user_id' not in session or session.get('role') != 'Homeowner': return jsonify({'status':'error'}),401
    conn=get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""SELECT id,request_id,assigned_role,concern_text,response_text,status,
                          DATE_FORMAT(created_at,'%%Y-%%m-%%d %%H:%%i') created_at,
                          DATE_FORMAT(responded_at,'%%Y-%%m-%%d %%H:%%i') responded_at
                          FROM request_concerns WHERE user_id=%s ORDER BY updated_at DESC""",(session['user_id'],))
        rows=cursor.fetchall()
    conn.close(); return jsonify({'status':'success','concerns':rows})

@app.route('/officer/concerns/<int:concern_id>/respond', methods=['POST'])
def respond_request_concern(concern_id):
    if 'user_id' not in session or session.get('role') not in ('Secretary','Treasurer'):
        return redirect(url_for('index'))
    response=(request.form.get('response') or '').strip()
    if not response: flash('Please enter a response to the homeowner.', 'error'); return redirect(url_for('officer'))
    try:
        conn=get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM request_concerns WHERE id=%s AND assigned_role=%s",(concern_id,session['role']))
            c=cursor.fetchone()
            if not c: conn.close(); flash('Concern not found or not assigned to your role.','error'); return redirect(url_for('officer'))
            cursor.execute("UPDATE request_concerns SET response_text=%s,status='Resolved',responded_by=%s,responded_at=NOW() WHERE id=%s",
                           (response,session.get('full_name') or session.get('username'),concern_id))
        conn.close()
        # Resolve request/homeowner context server-side for the notification email.
        homeowner_name = 'Homeowner'
        request_type = 'Request'
        try:
            nconn = get_db_connection()
            with nconn.cursor() as cursor:
                cursor.execute("""SELECT r.request_type, CONCAT(u.first_name,' ',u.last_name) AS homeowner
                                  FROM requests r JOIN users u ON u.id=r.user_id
                                  WHERE r.id=%s AND u.id=%s""", (c['request_id'], c['user_id']))
                nctx = cursor.fetchone()
            nconn.close()
            if nctx:
                homeowner_name = nctx.get('homeowner') or homeowner_name
                request_type = nctx.get('request_type') or request_type
        except Exception as exc:
            app.logger.warning('Could not resolve concern email context for concern_id=%s: %s', concern_id, exc)
        responder = session.get('full_name') or session.get('username') or session['role']
        body=(f"Dear {homeowner_name},\n\nYour concern regarding {request_type} request {c['request_id']} has received a response.\n\n"
              f"Officer Response: {response}\n\nResponded by: {responder}\nPosition: {session['role']}\n\n"
              "Please sign in to the NFH-HOA Homeowner Portal to review the related request and response.\n\n"
              "Thank you,\nNorth Fairway Homes Homeowners' Association")
        result=send_alert_and_email(c['user_id'],f"NFH-HOA Concern Response — {c['request_id']}",body,'request_concern',str(concern_id),f'concern-response-{concern_id}')
        log_audit_action(session.get('username'),session.get('role'),'Request Concern Resolved',c['request_id'],'Open','Resolved')
        flash('Response saved and the homeowner was notified.','success')
        if not result.get('email_sent'): flash('The response was saved, but email delivery was unavailable.','warning')
    except Exception as e: flash(f'Error responding to concern: {e}','error')
    return redirect(url_for('officer'))

@app.route('/api/requests/resubmit', methods=['POST'])
def resubmit_request():
    """Homeowner updates and resubmits a request that was returned 'For
    Correction', moving it back into the review queue."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    request_id = data.get('request_id')
    form_data = data.get('formData', {})
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, request_type FROM requests WHERE id=%s AND user_id=%s",
                           (request_id, user_id))
            req = cursor.fetchone()
            if not req:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Request not found.'}), 404
            if req['status'] != 'For Correction':
                conn.close()
                return jsonify({'status': 'error', 'message': 'Only requests marked "For Correction" can be resubmitted.'}), 400

            if 'Vehicle' in req['request_type']:
                err = validate_vehicle_list(form_data.get('vehicles', []))
                if err:
                    conn.close()
                    return jsonify({'status': 'error', 'message': err}), 400

            cursor.execute("""UPDATE requests SET details=%s, status='Submitted', remarks=NULL
                              WHERE id=%s""", (json.dumps(form_data), request_id))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'), 'Resubmit Request',
                         request_id, 'For Correction', 'Submitted')
        return jsonify({'status': 'success', 'message': f'Request {request_id} resubmitted for review.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ---------------------------------------------------------------------------
# Cancel request
# ---------------------------------------------------------------------------
@app.route('/api/requests/cancel', methods=['POST'])
def cancel_request():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json() or {}
    request_id = data.get('request_id')
    reason = (data.get('reason') or '').strip()
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, request_type FROM requests WHERE id=%s AND user_id=%s",
                           (request_id, user_id))
            req = cursor.fetchone()
            if not req:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Request not found.'}), 404
            if req['status'] not in ['Submitted', 'Under Review', 'For Correction']:
                conn.close()
                return jsonify({'status': 'error', 'message': 'This request can no longer be cancelled.'}), 400
            cursor.execute("""UPDATE requests SET status='Cancelled', cancellation_reason=%s, cancelled_by=%s
                              WHERE id=%s""", (reason, session.get('username'), request_id))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'), 'Cancel Request',
                         request_id, req['status'], 'Cancelled')
        return jsonify({'status': 'success', 'message': 'Request cancelled successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/alerts/read', methods=['POST'])
def read_alerts():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE alerts SET unread=0 WHERE user_id=%s", (session['user_id'],))
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'status': 'success', 'message': 'Logged out successfully.'})


# ===========================================================================
# TREASURER — MISSING MONTHLY DUES (applied directly; no Executive approval)
# ===========================================================================
@app.route('/api/treasurer/submit-adjustment', methods=['POST'])
def treasurer_submit_adjustment():
    if 'user_id' not in session or session.get('role') not in ['Treasurer', 'Admin']:
        return jsonify({'status': 'error', 'message': 'Permission denied.'}), 403
    data = request.get_json() or {}
    user_id = data.get('user_id')
    monthly_due = float(data.get('monthly_due') or 0)
    missing_months = int(data.get('missing_months') or 0)
    proposed = float(data.get('proposed_adjustment') or 0)
    reason = data.get('reason') or ''

    if not user_id:
        return jsonify({'status': 'error', 'message': 'Please select a homeowner.'}), 400
    if missing_months <= 0:
        return jsonify({'status': 'error', 'message': 'Missing months must be at least 1.'}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, CONCAT(first_name,' ',last_name) AS name FROM users WHERE id=%s", (user_id,))
            u = cursor.fetchone()
            if not u:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Homeowner not found.'}), 404

            cursor.execute("""INSERT INTO financial_adjustments
                (user_id, homeowner_name, monthly_due, missing_months, proposed_adjustment,
                 previous_balance, new_balance, reason, submitted_by, status, decided_by, decided_at)
                VALUES (%s,%s,%s,%s,%s,0.00,%s,%s,%s,'Applied',%s,%s)""",
                           (user_id, u['name'], monthly_due, missing_months, proposed,
                            proposed, reason, session.get('username'), session.get('username'), datetime.now()))
            adj_id = cursor.lastrowid

            # Create the individual missing-month ledger entries
            month_cursor = datetime.now().date().replace(day=1)
            for i in range(missing_months):
                due_month = (month_cursor.replace(day=1) - timedelta(days=30 * i))
                cursor.execute("""INSERT INTO monthly_dues (user_id, due_month, amount, status)
                                  VALUES (%s,%s,%s,'Unpaid')""", (user_id, due_month, monthly_due))
        conn.close()

        log_audit_action(session.get('username'), session.get('role'),
                         'Missing Dues Adjustment Applied', f'Adjustment-{adj_id}', None, proposed)

        # Requirement: clear, informative missing-dues notification for the homeowner.
        treasurer = get_treasurer_contact()
        send_alert_and_email(
            user_id, 'Missing Monthly Dues Notice',
            f"Our records show {missing_months} missing monthly due(s) at ₱{monthly_due:.2f} each, "
            f"totaling ₱{proposed:.2f}.\n\n"
            f"Reason on file: {reason or 'N/A'}\n\n"
            f"Please settle this balance with the Treasurer ({treasurer['name']}, {treasurer['phone']}, "
            f"{treasurer['email']}) at your earliest convenience.",
            related_type='financial_adjustment', related_id=str(adj_id),
            dedupe_key=f'missing-dues-{adj_id}')

        return jsonify({'status': 'success', 'message': 'Missing dues adjustment applied and homeowner notified.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ===========================================================================
# TREASURER — CLEAR / SETTLE MONTHLY DUES
# ===========================================================================
@app.route('/api/treasurer/settle-dues', methods=['POST'])
def treasurer_settle_dues():
    if 'user_id' not in session or session.get('role') not in ['Treasurer', 'Admin']:
        return jsonify({'status': 'error', 'message': 'Permission denied.'}), 403
    data = request.get_json() or {}
    homeowner_id = data.get('user_id')
    if not homeowner_id:
        return jsonify({'status': 'error', 'message': 'Please select a homeowner.'}), 400
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT CONCAT(first_name,' ',last_name) AS name FROM users WHERE id=%s AND role='Homeowner'", (homeowner_id,))
            homeowner = cursor.fetchone()
            if not homeowner:
                conn.close(); return jsonify({'status':'error','message':'Homeowner not found.'}), 404
            before = dues_summary(cursor, homeowner_id)
            if before['unpaid_months'] == 0:
                conn.close(); return jsonify({'status':'error','message':'This homeowner has no unpaid monthly dues.'}), 400
            cursor.execute("UPDATE monthly_dues SET status='Paid' WHERE user_id=%s AND status='Unpaid'", (homeowner_id,))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'), 'Monthly Dues Cleared', homeowner['name'],
                         f"{before['unpaid_months']} unpaid month(s), ₱{before['outstanding_balance']:.2f}", 'Paid')
        send_alert_and_email(homeowner_id, 'Monthly Dues Cleared',
            'Your outstanding monthly dues have been marked as paid by the Treasurer. Requests awaiting Executive review may now proceed for approval.',
            related_type='monthly_dues', related_id=str(homeowner_id), dedupe_key=f"dues-cleared-{homeowner_id}-{int(time.time())}")
        return jsonify({'status':'success','message':'Outstanding monthly dues marked as paid.'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500


# ===========================================================================
# ADMIN ACCOUNT MANAGEMENT
# ===========================================================================
@app.route('/create-officer', methods=['POST'])
def create_officer():
    if 'user_id' not in session or session.get('role') != 'Admin':
        return redirect(url_for('index'))
    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'Secretary')

    if not all([full_name, username, email, phone, password, role]):
        flash('Full Name, Username, Email, Phone Number, Password, and Role are all required.', 'error')
        return redirect(url_for('admin'))
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(url_for('admin'))
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        flash('Please enter a valid email address.', 'error')
        return redirect(url_for('admin'))
    if not re.match(r'^09\d{9}$', phone):
        flash('Phone number must contain 11 digits and start with 09.', 'error')
        return redirect(url_for('admin'))
    if role not in ['Secretary', 'Treasurer', 'President', 'Vice President', 'Board Director']:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('admin'))

    name_parts = full_name.split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else 'Officer'
    pwd_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
            if cursor.fetchone():
                conn.close()
                flash('Username or email already exists.', 'error')
                return redirect(url_for('admin'))

            cursor.execute("""INSERT INTO users
                (first_name, last_name, username, email, mobile, password_hash, role, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'Active')""",
                           (first_name, last_name, username, email, phone, pwd_hash, role))
        conn.close()
        log_audit_action(session.get('username'), session.get('role'),
                         'Create Officer Account', username, None, role)
        flash(f'Officer account {username} created successfully.', 'success')
    except pymysql.IntegrityError:
        flash('Username or email already exists.', 'error')
    except Exception as e:
        flash(f'Error creating officer: {str(e)}', 'error')
    return redirect(url_for('admin'))


@app.route('/edit-officer/<int:officer_id>', methods=['POST'])
def edit_officer(officer_id):
    if 'user_id' not in session or session.get('role') != 'Admin':
        return redirect(url_for('index'))
    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', '').strip()
    if not all([full_name, username, email, phone, role]) or role not in ['Secretary','Treasurer','President','Vice President','Board Director']:
        flash('Provide valid officer information and an allowed officer role.', 'error')
        return redirect(url_for('admin') + '#officers')
    if not re.match(r'^09\d{9}$', phone):
        flash('Phone number must contain 11 digits and start with 09.', 'error')
        return redirect(url_for('admin') + '#officers')
    parts = full_name.split(' ', 1); first = parts[0]; last = parts[1] if len(parts)>1 else 'Officer'
    try:
        conn=get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id=%s AND role IN ('Secretary','Treasurer','President','Vice President','Board Director')", (officer_id,))
            old=cursor.fetchone()
            if not old:
                conn.close(); flash('Officer account not found.', 'error'); return redirect(url_for('admin')+'#officers')
            cursor.execute("SELECT id FROM users WHERE id<>%s AND (LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s))", (officer_id,username,email))
            if cursor.fetchone():
                conn.close(); flash('Username or email already belongs to another account.', 'error'); return redirect(url_for('admin')+'#officers')
            cursor.execute("UPDATE users SET first_name=%s,last_name=%s,username=%s,email=%s,mobile=%s,role=%s WHERE id=%s",
                           (first,last,username,email,phone,role,officer_id))
        conn.close()
        log_audit_action(session.get('username'), 'Admin', 'Edit Officer Account', username,
                         f"{old['username']} | {old['email']} | {old['mobile']} | {old['role']}",
                         f"{username} | {email} | {phone} | {role}")
        flash(f'Officer account {username} updated successfully.', 'success')
    except pymysql.IntegrityError:
        flash('Username or email already exists.', 'error')
    except Exception as e:
        flash(f'Error updating officer: {e}', 'error')
    return redirect(url_for('admin') + '#officers')


@app.route('/toggle-officer-status/<int:officer_id>', methods=['POST'])
def toggle_officer_status(officer_id):
    if 'user_id' not in session or session.get('role') != 'Admin':
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT username, status FROM users WHERE id=%s", (officer_id,))
            off = cursor.fetchone()
            if off:
                new_status = 'Inactive' if off['status'] == 'Active' else 'Active'
                cursor.execute("UPDATE users SET status=%s WHERE id=%s", (new_status, officer_id))
                log_audit_action(session.get('username'), session.get('role'),
                                 'Toggle Officer Status', off['username'], off['status'], new_status)
                flash(f'Status for {off["username"]} updated to {new_status}.', 'success')
        conn.close()
    except Exception as e:
        flash(f'Error updating officer status: {str(e)}', 'error')
    return redirect(url_for('admin'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ===========================================================================
# AUTHENTICATION APIS
# ===========================================================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password required.'}), 400
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s)",
                           (username, username))
            user = cursor.fetchone()
        conn.close()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'status': 'error', 'message': 'Invalid username or password.'}), 401
        if user['status'] != 'Active':
            return jsonify({'status': 'error', 'message': 'Your account is suspended or inactive.'}), 403
        _set_login_session(user)
        redirect_url = _role_home_url(user['role'])
        log_audit_action(user['username'], user['role'], 'User Login', user['username'])
        return jsonify({'status': 'success', 'redirect': redirect_url})
    except Exception as e:
        app.logger.exception('Login failed due to an internal error')
        return jsonify({'status': 'error', 'message': 'Unable to sign in right now. Please try again.'}), 500


@app.route('/api/send-registration-code', methods=['POST'])
def send_reg_code():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'status': 'error', 'message': 'Email address required.'}), 400
    code = generate_code()
    VERIFICATION_CODES[email] = code
    if not app.config.get('MAIL_USERNAME'):
        # Email is not configured — this is expected in local/dev setups.
        # Print the code to the console AND return it in the response so
        # whoever is testing can actually see it.
        print(f"[DEV MODE — email not configured] Registration code for {email}: {code}")
        return jsonify({'status': 'success',
                        'message': f'Email is not configured on this server. Your verification code is: {code}'})
    try:
        msg = Message('Northfairway HOA - Email Verification Code', recipients=[email])
        msg.body = f"Your verification code is: {code}\n\nThis code will expire shortly."
        mail.send(msg)
        return jsonify({'status': 'success', 'message': 'Verification code sent successfully.'})
    except Exception as e:
        print(f"[Mail send failed] Registration code for {email}: {code} (error: {e})")
        return jsonify({'status': 'error', 'message': 'Email delivery failed. Please verify the server email configuration and try again.'}), 503


@app.route('/api/verify-registration-code', methods=['POST'])
def verify_reg_code():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    if VERIFICATION_CODES.get(email) == code:
        return jsonify({'status': 'success', 'message': 'Email verified.'})
    return jsonify({'status': 'error', 'message': 'Invalid verification code.'}), 400


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    username = data.get('username', '').strip()
    mobile = data.get('phone', '').strip()
    password = data.get('password', '')
    if not all([first_name, last_name, email, username, mobile, password]):
        return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
    if len(password) < 8:
        return jsonify({'status': 'error', 'message': 'Password must be at least 8 characters.'}), 400
    if not re.match(r'^09\d{9}$', mobile):
        return jsonify({'status': 'error', 'message': 'Phone number must contain 11 digits and start with 09.'}), 400
    pwd_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO users
                (first_name, last_name, email, username, mobile, password_hash, role)
                VALUES (%s,%s,%s,%s,%s,%s,'Homeowner')""",
                           (first_name, last_name, email, username, mobile, pwd_hash))
        conn.close()
        VERIFICATION_CODES.pop(email, None)
        return jsonify({'status': 'success', 'message': 'Account created successfully! Please sign in.'})
    except pymysql.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Username or email already exists.'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500


@app.route('/api/forgot-password/send-code', methods=['POST'])
def forgot_send_code():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
    conn.close()
    if not user:
        return jsonify({'status': 'error', 'message': 'Email address not found.'}), 404
    code = generate_code()
    RESET_CODES[email] = code
    if not app.config.get('MAIL_USERNAME'):
        print(f"[DEV MODE — email not configured] Password reset code for {email}: {code}")
        return jsonify({'status': 'success',
                        'message': f'Email is not configured on this server. Your reset code is: {code}'})
    try:
        msg = Message('Northfairway HOA - Password Reset Code', recipients=[email])
        msg.body = f"Your password reset code is: {code}"
        mail.send(msg)
        return jsonify({'status': 'success', 'message': 'Reset code sent to email.'})
    except Exception as e:
        print(f"[Mail send failed] Password reset code for {email}: {code} (error: {e})")
        return jsonify({'status': 'error', 'message': 'Email delivery failed. Please verify the server email configuration and try again.'}), 503


@app.route('/api/forgot-password/reset', methods=['POST'])
def forgot_reset_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    new_password = data.get('new_password', '')
    if RESET_CODES.get(email) != code:
        return jsonify({'status': 'error', 'message': 'Invalid or expired reset code.'}), 400
    pwd_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET password_hash=%s WHERE email=%s", (pwd_hash, email))
        conn.close()
        RESET_CODES.pop(email, None)
        return jsonify({'status': 'success', 'message': 'Password reset successful. You can now log in.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Database error: {str(e)}'}), 500


# ===========================================================================
# APPROVAL EMAIL
# ===========================================================================
def send_approval_email(req_id, req_type, user_id, executive_name=None, executive_role=None):
    """Notify the request owner after a committed Executive approval."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT email, CONCAT(first_name,' ',last_name) AS name FROM users WHERE id=%s", (user_id,))
            u = cursor.fetchone()
        conn.close()
        if not u:
            app.logger.warning('[EMAIL FAILURE] Approval %s: homeowner user record not found', req_id)
            return {'created': False, 'email_sent': False, 'reason': 'Homeowner account not found.'}

        subject = f"NFH-HOA Request Approved — {req_id}"
        actor = executive_name or 'Authorized Executive'
        position = executive_role or 'Executive'
        body = (
            f"Dear {u['name']},\n\n"
            f"Your {req_type} request ({req_id}) has been approved.\n\n"
            f"Request ID: {req_id}\n"
            f"Request Type: {req_type}\n"
            f"Status: Approved\n\n"
            f"Approved by: {actor}\n"
            f"Position: {position}\n\n"
            "If payment is required for this request, please review the NFH-HOA Homeowner Portal "
            "for the next payment step. The NFH-HOA system does not process online payments directly.\n\n"
            "Thank you,\nNorth Fairway Homes Homeowners' Association"
        )
        return send_alert_and_email(
            user_id, subject, body, related_type='request', related_id=req_id,
            dedupe_key=f'approval-{req_id}', important=True
        )
    except Exception as e:
        app.logger.warning('[EMAIL FAILURE] Approval email helper for %s: %s: %s', req_id, type(e).__name__, e)
        return {'created': False, 'email_sent': False, 'reason': f'{type(e).__name__}: {e}'}



# ===========================================================================
# PDF GENERATION (individual requests + admin reports)
# ===========================================================================
def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='NFHTitle', fontSize=13, leading=16, alignment=TA_CENTER, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='NFHSub', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.HexColor('#444444')))
    styles.add(ParagraphStyle(name='NFHHeading', fontSize=11, leading=14, fontName='Helvetica-Bold',
                              textColor=colors.HexColor('#1B4332'), spaceBefore=10, spaceAfter=4))
    styles.add(ParagraphStyle(name='NFHBody', fontSize=9.5, leading=13))
    styles.add(ParagraphStyle(name='NFHRight', fontSize=8.5, leading=11, alignment=TA_RIGHT))
    return styles


def _pdf_letterhead(elements, styles, doc_title):
    elements.append(Paragraph(HOA_NAME, styles['NFHTitle']))
    elements.append(Paragraph(HOA_ADDRESS, styles['NFHSub']))
    elements.append(Paragraph(HOA_REG, styles['NFHSub']))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1B4332')))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(doc_title, styles['NFHHeading']))


def _kv_table(pairs, col_widths=(1.8 * inch, 4.4 * inch)):
    rows = [[Paragraph(f"<b>{k}</b>", getSampleStyleSheet()['Normal']), Paragraph(str(v), getSampleStyleSheet()['Normal'])]
            for k, v in pairs]
    t = Table(rows, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#DDDDDD')),
    ]))
    return t


def _response_pdf(buffer, filename):
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


REQUEST_TYPE_FIELD_LABELS = {
    'fullName': 'Full Name', 'blockNum': 'Block Number', 'lotNum': 'Lot Number',
    'materialsList': 'List of Materials',
    'verifiedOwner': 'Verified Owner', 'issuanceDate': 'Date of Issuance Request',
    'requestDate': 'Date', 'applicationDate': 'Application Date',
    'moveInDate': 'Move-in Date', 'moveOutDate': 'Move-out Date',
    'applicantName': "Applicant's Name", 'blockLot': 'Block and Lot',
    'phoneNum': 'Cellphone No.', 'emailAddr': 'Email Address',
}


def generate_request_pdf(req):
    """Builds a PDF document tailored to the request's type."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    styles = _pdf_styles()
    elements = []

    req_type = req['request_type']
    _pdf_letterhead(elements, styles, f"{req_type} — Request Form")

    try:
        details = json.loads(req.get('details') or '{}')
    except Exception:
        details = {}

    elements.append(_kv_table([
        ('Request ID', req['id']),
        ('Homeowner', req['homeowner']),
        ('Category', req.get('category') or 'Document Request'),
        ('Date Submitted', format_pdf_datetime(req.get('date_submitted'))),
        ('Status', req['status']),
        ('Payment Status', req['payment_status']),
        ('Fee', f"₱{float(req['fee']):.2f}"),
    ]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph('Request Details', styles['NFHHeading']))

    if req_type == 'Vehicle Sticker Application' and 'vehicles' in details:
        top_pairs = [(REQUEST_TYPE_FIELD_LABELS.get(k, k), v) for k, v in details.items() if k != 'vehicles']
        if top_pairs:
            elements.append(_kv_table(top_pairs))
            elements.append(Spacer(1, 8))
        veh_rows = [['#', 'Type', 'Plate No.', 'Model / Year', 'Color']]
        for i, v in enumerate(details.get('vehicles', []), start=1):
            veh_rows.append([str(i), v.get('type', ''), v.get('plate', ''), v.get('model', ''), v.get('color', '')])
        vt = Table(veh_rows, colWidths=[0.3 * inch, 1.2 * inch, 1.4 * inch, 1.7 * inch, 1.4 * inch])
        vt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2EBE2')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ]))
        elements.append(vt)
    elif details:
        pairs = [(REQUEST_TYPE_FIELD_LABELS.get(k, k.replace('_', ' ').title()), v)
                 for k, v in details.items() if k not in ('oathAgreed',)]
        elements.append(_kv_table(pairs))
    else:
        elements.append(Paragraph('No additional details recorded.', styles['NFHBody']))

    if req.get('remarks'):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph('Officer Remarks', styles['NFHHeading']))
        elements.append(Paragraph(req['remarks'], styles['NFHBody']))

    elements.append(Spacer(1, 24))
    elements.append(Paragraph(f"Generated on {now_str()} — For official HOA processing use only.", styles['NFHSub']))

    doc.build(elements)
    safe_id = re.sub(r'[^A-Za-z0-9_\-]', '_', req['id'])
    return buffer, f"NFH_{safe_id}.pdf"


@app.route('/requests/<req_id>/pdf')
def request_pdf(req_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""SELECT r.*, CONCAT(u.first_name,' ',u.last_name) AS homeowner
                              FROM requests r JOIN users u ON r.user_id=u.id WHERE r.id=%s""", (req_id,))
            req = cursor.fetchone()
        conn.close()
        if not req:
            flash('Request not found.', 'error')
            return redirect(url_for('index'))
        role = session.get('role')
        if role == 'Homeowner' and req['user_id'] != session.get('user_id'):
            flash('You are not authorized to view this document.', 'error')
            return redirect(url_for('homeowner'))
        if role not in ['Homeowner'] + OFFICER_ROLES:
            return redirect(url_for('index'))

        buffer, filename = generate_request_pdf(req)
        log_audit_action(session.get('username'), session.get('role'), 'Download Request PDF', req_id)
        return _response_pdf(buffer, filename)
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Admin PDF reports (with filters)
# ---------------------------------------------------------------------------
def _require_admin():
    return 'user_id' in session and session.get('role') == 'Admin'


def _filters_paragraph(styles, filters):
    active = [f"{k}: {v}" for k, v in filters.items() if v]
    text = 'Filters applied: ' + (', '.join(active) if active else 'None (showing all records)')
    return Paragraph(text, styles['NFHSub'])


@app.route('/admin/reports/audit-trail/pdf')
def report_audit_trail_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    username = request.args.get('username', '')
    role = request.args.get('role', '')
    action = request.args.get('action', '')

    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    if date_from:
        query += " AND timestamp >= %s"; params.append(date_from + ' 00:00:00')
    if date_to:
        query += " AND timestamp <= %s"; params.append(date_to + ' 23:59:59')
    if username:
        query += " AND username LIKE %s"; params.append(f"%{username}%")
    if role:
        query += " AND role = %s"; params.append(role)
    if action:
        query += " AND action LIKE %s"; params.append(f"%{action}%")
    query += " ORDER BY timestamp ASC"

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = _pdf_styles()
    elements = []
    _pdf_letterhead(elements, styles, 'Audit Trail Report')
    elements.append(_filters_paragraph(styles, {
        'Date From': date_from, 'Date To': date_to, 'User': username, 'Role': role, 'Action': action}))
    elements.append(Spacer(1, 10))

    table_rows = [['Timestamp', 'User', 'Role', 'Action', 'Item', 'Previous', 'New']]
    for r in rows:
        table_rows.append([format_pdf_datetime(r['timestamp']), r['username'] or '-', r['role'] or '-', r['action'],
                           r['item'] or '-', (r['prev_val'] or '-')[:20], (r['new_val'] or '-')[:20]])
    if len(table_rows) == 1:
        table_rows.append(['No matching records', '', '', '', '', '', ''])
    t = Table(table_rows, repeatRows=1, colWidths=[1.1 * inch, 0.9 * inch, 0.7 * inch, 1.2 * inch, 1.0 * inch, 0.8 * inch, 0.8 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(f"Generated on {now_str()} by {session.get('username')}.", styles['NFHSub']))
    doc.build(elements)
    log_audit_action(session.get('username'), session.get('role'), 'Generate Audit Trail PDF', 'audit_logs')
    return _response_pdf(buffer, 'NFH_Audit_Trail_Report.pdf')


@app.route('/admin/reports/requests/pdf')
def report_requests_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')
    req_type = request.args.get('request_type', '')
    payment_status = request.args.get('payment_status', '')

    query = """SELECT r.*, CONCAT(u.first_name,' ',u.last_name) AS homeowner FROM requests r
               JOIN users u ON r.user_id = u.id WHERE 1=1"""
    params = []
    if date_from:
        query += " AND r.date_submitted >= %s"; params.append(date_from + ' 00:00:00')
    if date_to:
        query += " AND r.date_submitted <= %s"; params.append(date_to + ' 23:59:59')
    if status:
        query += " AND r.status = %s"; params.append(status)
    if req_type:
        query += " AND r.request_type = %s"; params.append(req_type)
    if payment_status:
        query += " AND r.payment_status = %s"; params.append(payment_status)
    query += " ORDER BY r.date_submitted DESC"

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = _pdf_styles()
    elements = []
    _pdf_letterhead(elements, styles, 'Requests Report')
    elements.append(_filters_paragraph(styles, {
        'Date From': date_from, 'Date To': date_to, 'Status': status,
        'Type': req_type, 'Payment': payment_status}))
    elements.append(Spacer(1, 10))

    table_rows = [['ID', 'Homeowner', 'Type', 'Status', 'Payment', 'Submitted']]
    for r in rows:
        table_rows.append([r['id'], r['homeowner'], r['request_type'], r['status'], r['payment_status'],
                           format_pdf_datetime(r['date_submitted'])])
    if len(table_rows) == 1:
        table_rows.append(['No matching records', '', '', '', '', ''])
    t = Table(table_rows, repeatRows=1, colWidths=[1.3 * inch, 1.3 * inch, 1.5 * inch, 1.1 * inch, 0.8 * inch, 1.1 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
    ]))
    elements.append(t)
    doc.build(elements)
    log_audit_action(session.get('username'), session.get('role'), 'Generate Requests PDF', 'requests')
    return _response_pdf(buffer, 'NFH_Requests_Report.pdf')


@app.route('/admin/reports/vehicle-stickers/pdf')
def report_vehicle_stickers_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')

    query = """SELECT r.*, CONCAT(u.first_name,' ',u.last_name) AS homeowner FROM requests r
               JOIN users u ON r.user_id = u.id WHERE r.request_type = 'Vehicle Sticker Application'"""
    params = []
    if date_from:
        query += " AND r.date_submitted >= %s"; params.append(date_from + ' 00:00:00')
    if date_to:
        query += " AND r.date_submitted <= %s"; params.append(date_to + ' 23:59:59')
    if status:
        query += " AND r.status = %s"; params.append(status)
    query += " ORDER BY r.date_submitted DESC"

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = _pdf_styles()
    elements = []
    _pdf_letterhead(elements, styles, 'Vehicle Stickers Report')
    elements.append(_filters_paragraph(styles, {'Date From': date_from, 'Date To': date_to, 'Status': status}))
    elements.append(Spacer(1, 10))

    table_rows = [['Req ID', 'Homeowner', 'Plate No.', 'Type', 'Model/Year', 'Color', 'Status']]
    for r in rows:
        try:
            details = json.loads(r.get('details') or '{}')
        except Exception:
            details = {}
        vehicles = details.get('vehicles', [])
        if not vehicles:
            table_rows.append([r['id'], r['homeowner'], '-', '-', '-', '-', r['status']])
        for v in vehicles:
            table_rows.append([r['id'], r['homeowner'], v.get('plate', ''), v.get('type', ''),
                               v.get('model', ''), v.get('color', ''), r['status']])
    if len(table_rows) == 1:
        table_rows.append(['No matching records', '', '', '', '', '', ''])
    t = Table(table_rows, repeatRows=1, colWidths=[1.1 * inch, 1.2 * inch, 0.9 * inch, 0.9 * inch, 1.1 * inch, 0.8 * inch, 0.9 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
    ]))
    elements.append(t)
    doc.build(elements)
    log_audit_action(session.get('username'), session.get('role'), 'Generate Vehicle Stickers PDF', 'requests')
    return _response_pdf(buffer, 'NFH_Vehicle_Stickers_Report.pdf')


@app.route('/admin/reports/adjustments/pdf')
def report_adjustments_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = "SELECT * FROM financial_adjustments WHERE 1=1"
    params = []
    if date_from:
        query += " AND created_at >= %s"; params.append(date_from + ' 00:00:00')
    if date_to:
        query += " AND created_at <= %s"; params.append(date_to + ' 23:59:59')
    query += " ORDER BY created_at DESC"

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = _pdf_styles()
    elements = []
    _pdf_letterhead(elements, styles, 'Missing Monthly Dues Report')
    elements.append(_filters_paragraph(styles, {'Date From': date_from, 'Date To': date_to}))
    elements.append(Spacer(1, 10))

    table_rows = [['ID', 'Homeowner', 'Monthly Due', 'Missing Months', 'Total', 'Submitted By', 'Date']]
    for r in rows:
        table_rows.append([r['id'], r['homeowner_name'], f"₱{float(r['monthly_due']):.2f}",
                           r['missing_months'], f"₱{float(r['proposed_adjustment']):.2f}",
                           r['submitted_by'], str(r['created_at'])])
    if len(table_rows) == 1:
        table_rows.append(['No matching records', '', '', '', '', '', ''])
    t = Table(table_rows, repeatRows=1, colWidths=[0.5 * inch, 1.3 * inch, 0.9 * inch, 0.9 * inch, 0.8 * inch, 1.0 * inch, 1.1 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
    ]))
    elements.append(t)
    doc.build(elements)
    log_audit_action(session.get('username'), session.get('role'), 'Generate Missing Dues PDF', 'financial_adjustments')
    return _response_pdf(buffer, 'NFH_Missing_Dues_Report.pdf')



@app.route('/admin/reports/officers/pdf')
def report_officers_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    role = request.args.get('role', '')
    status = request.args.get('status', '')

    query = "SELECT * FROM users WHERE role IN ('Secretary','Treasurer','President','Vice President','Board Director')"
    params = []
    if role:
        query += " AND role = %s"; params.append(role)
    if status:
        query += " AND status = %s"; params.append(status)
    query += " ORDER BY created_at DESC"

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = _pdf_styles()
    elements = []
    _pdf_letterhead(elements, styles, 'Officer / User Records Report')
    elements.append(_filters_paragraph(styles, {'Role': role, 'Status': status}))
    elements.append(Spacer(1, 10))

    table_rows = [['ID', 'Full Name', 'Username', 'Email', 'Phone', 'Role', 'Status']]
    for r in rows:
        table_rows.append([r['id'], f"{r['first_name']} {r['last_name']}", r['username'],
                           r['email'], r['mobile'], r['role'], r['status']])
    if len(table_rows) == 1:
        table_rows.append(['No matching records', '', '', '', '', '', ''])
    t = Table(table_rows, repeatRows=1, colWidths=[0.4 * inch, 1.3 * inch, 1.0 * inch, 1.5 * inch, 0.9 * inch, 0.8 * inch, 0.7 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
    ]))
    elements.append(t)
    doc.build(elements)
    log_audit_action(session.get('username'), session.get('role'), 'Generate Officer Records PDF', 'users')
    return _response_pdf(buffer, 'NFH_Officer_Records_Report.pdf')


# ===========================================================================
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
