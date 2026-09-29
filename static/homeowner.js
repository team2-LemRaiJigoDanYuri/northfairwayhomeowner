document.addEventListener('DOMContentLoaded', () => {
    fetchUserData();
    setupTabNavigation();
    setupProfileForm();
    setupModalListeners();
    setupRequestButtons();
});

let currentUserProfile = {};
let currentRequestFee = "₱50.00";
let currentRequestTitle = "";
let currentRequestCategory = "";
let requestToCancelId = null;
let systemFees = {};

function showToastNotification(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type}`;
    const iconClass = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-circle-xmark' : 'fa-circle-info');

    toast.innerHTML = `
        <i class="fa-solid ${iconClass}"></i>
        <div class="toast-content">${escapeHtml(message)}</div>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.classList.add('toast-show'), 10);
    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

window.showToastNotification = showToastNotification;

// Unified Template Generator retaining full forms & auto-fill bindings
function getTemplateHTML(formId, profile) {
    const fullName = `${profile.first_name || ''} ${profile.last_name || ''}`.trim();
    const phone = profile.mobile || '';
    const block = profile.block || '';
    const lot = profile.lot || '';
    const blockLot = (block || lot) ? `${block} ${lot}`.trim() : '';
    const todayISO = new Date().toISOString().split('T')[0];

    const fourWheelFee = systemFees['Vehicle Sticker (4 Wheels)'] ? systemFees['Vehicle Sticker (4 Wheels)'].toFixed(2) : '200.00';
    const otherWheelFee = systemFees['Vehicle Sticker (2/3 Wheels)'] ? systemFees['Vehicle Sticker (2/3 Wheels)'].toFixed(2) : '100.00';
    const officialDue = systemFees['Monthly Dues'] ? systemFees['Monthly Dues'].toFixed(2) : '100.00';

    const templates = {
        'gate-pass': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required placeholder="Full Name"></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required placeholder="e.g. Blk 1"></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required placeholder="e.g. Lot 12"></div>
            </div>
            <div class="form-section-title">List of Materials</div>
            <div class="form-group full-width">
                <textarea name="materialsList" placeholder="Enter descriptive list of materials items matching load delivery records..."></textarea>
            </div>
        `,
        'proof-residency': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required placeholder="Full Name"></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required placeholder="Blk"></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required placeholder="Lot"></div>
            </div>
            <div class="form-group full-width">
                <label>Verified Owner <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-user-shield"></i><input type="text" name="verifiedOwner" value="${escapeHtml(fullName)}" required placeholder="Verified Owner Name"></div>
            </div>
            <div class="form-group full-width">
                <label>Date of Issuance Request <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-calendar"></i><input type="date" name="issuanceDate" value="${todayISO}" required></div>
            </div>
        `,
        'cert-improvement': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required></div>
            </div>
            <div class="form-group full-width">
                <label>Date <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-calendar"></i><input type="date" name="requestDate" value="${todayISO}" required></div>
            </div>
        `,
        'cert-membership': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required placeholder="Blk"></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required placeholder="Lot"></div>
            </div>
            <div class="form-group full-width">
                <label>Application Date (Auto-Generated)</label>
                <div class="input-wrapper"><i class="fa-regular fa-calendar"></i><input type="date" name="applicationDate" value="${todayISO}" readonly style="background-color: #e2e8f0; cursor: not-allowed;"></div>
            </div>
        `,
        'move-in': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required></div>
            </div>
            <div class="form-group full-width">
                <label>Move-in Date <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-calendar-check"></i><input type="date" name="moveInDate" required></div>
            </div>
            <div class="legal-sworn-box">
                <strong>Notice:</strong> This certifies that the registered owner/tenant is allowed to bring the needed items inside the subdivision for legal occupancy transfers.
            </div>
        `,
        'move-out': `
            <div class="form-group full-width">
                <label>Full Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group">
                <label>Block Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-layer-group"></i><input type="text" name="blockNum" value="${escapeHtml(block)}" required></div>
            </div>
            <div class="form-group">
                <label>Lot Number <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-house-user"></i><input type="text" name="lotNum" value="${escapeHtml(lot)}" required></div>
            </div>
            <div class="form-group full-width">
                <label>Move-out Date <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-calendar-minus"></i><input type="date" name="moveOutDate" required></div>
            </div>
            <div class="legal-sworn-box">
                <strong>Notice:</strong> Outgoing parties are strictly cleared to carry listed personal belongings outside subdivision bounds upon validation of complete accounts resolution.
            </div>
        `,
        'vehicle-sticker': `
            <div class="form-section-title">Applicant Profile</div>
            <div class="form-group">
                <label>Applicant's Name <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="applicantName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group">
                <label>Block and Lot <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-map-pin"></i><input type="text" name="blockLot" value="${escapeHtml(blockLot)}" required></div>
            </div>
            <div class="form-group">
                <label>Cellphone No. <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-mobile-screen"></i><input type="tel" name="phoneNum" value="${escapeHtml(phone)}" required></div>
            </div>
            <div class="form-group">
                <label>Email Address <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-envelope"></i><input type="email" name="emailAddr" value="${escapeHtml(profile.email || '')}" required></div>
            </div>

            <div class="form-section-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>Registered Vehicles</span>
                <button type="button" class="btn-save" style="padding: 4px 12px; font-size: 0.75rem;" onclick="addVehicleRow()"><i class="fa-solid fa-plus"></i> Add Vehicle</button>
            </div>

            <div id="vehicleContainer">
                <div class="due-item" style="flex-direction: column; align-items: stretch; gap: 10px; margin-bottom: 12px; background: var(--input-bg);" data-vehicle-index="0">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed var(--border-color); padding-bottom: 6px;">
                        <strong>Vehicle #1</strong>
                    </div>
                    <div class="modal-form">
                        <div class="form-group">
                            <label>Vehicle Type <span>*</span></label>
                            <div class="input-wrapper">
                                <select name="vType_0" onchange="recalculateVehiclePricing()" required>
                                    <option value="4 Wheels">4 Wheels (₱${fourWheelFee})</option>
                                    <option value="2/3 Wheels">2/3 Wheels (₱${otherWheelFee})</option>
                                    <option value="E-bike">E-bike (₱${otherWheelFee})</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Plate Number <span>*</span></label>
                            <div class="input-wrapper"><input type="text" name="vPlate_0" placeholder="e.g. ABC 1234" required></div>
                        </div>
                        <div class="form-group">
                            <label>Vehicle Model / Year <span>*</span></label>
                            <div class="input-wrapper"><input type="text" name="vModel_0" placeholder="e.g. Vios 2022" minlength="4" title="At least 4 characters" required></div>
                        </div>
                        <div class="form-group">
                            <label>Vehicle Color <span>*</span></label>
                            <div class="input-wrapper"><input type="text" name="vColor_0" placeholder="e.g. Black" pattern="[A-Za-z\s\-]+" title="Letters only" required></div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        'tenant-form': `
            <div class="form-group">
                <label>Full Name (Head of Renter/Tenant) <span>*</span></label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="fullName" value="${escapeHtml(fullName)}" required></div>
            </div>
            <div class="form-group triple-split">
                <div><label>Gender</label><input type="text" name="gender" value="${escapeHtml(profile.gender || '')}" style="background:var(--input-bg); border:none; padding:8px; border-radius:6px; width:100%;"></div>
                <div><label>Age</label><input type="number" name="age" style="background:var(--input-bg); border:none; padding:8px; border-radius:6px; width:100%;"></div>
                <div><label>Birthdate</label><input type="date" name="dob" value="${escapeHtml(profile.dob || '')}" style="background:var(--input-bg); border:none; padding:8px; border-radius:6px; width:100%;"></div>
            </div>
            <div class="form-group">
                <label>Cellphone Number / Tel. # <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-phone"></i><input type="tel" name="phoneNum" value="${escapeHtml(phone)}" required></div>
            </div>
            <div class="form-group">
                <label>Occupation</label>
                <div class="input-wrapper"><i class="fa-solid fa-briefcase"></i><input type="text" name="occupation"></div>
            </div>
            <div class="form-group">
                <label>Civil Status</label>
                <div class="input-wrapper"><i class="fa-solid fa-heart"></i><input type="text" name="civilStatus" value="${escapeHtml(profile.civil_status || 'Single')}" placeholder="Single / Married"></div>
            </div>
            <div class="form-group">
                <label>Spouse Full Name (If Applicable)</label>
                <div class="input-wrapper"><i class="fa-regular fa-user"></i><input type="text" name="spouseName"></div>
            </div>
            <div class="form-group full-width">
                <label>Spouse Cellphone / Tel. No.</label>
                <div class="input-wrapper"><i class="fa-solid fa-phone"></i><input type="tel" name="spousePhone"></div>
            </div>
            <div class="form-group full-width">
                <label>Previous Address <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-history"></i><input type="text" name="previousAddress" required></div>
            </div>
            <div class="form-group full-width">
                <label>Address of Unit to be Rented <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-map-marker-alt"></i><input type="text" name="rentedAddress" value="${escapeHtml(blockLot)}" required></div>
            </div>
            <div class="form-group">
                <label>Name of Unit Owner <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-user-tie"></i><input type="text" name="ownerName" required></div>
            </div>
            <div class="form-group">
                <label>Owner Contact # <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-phone-volume"></i><input type="text" name="ownerPhone" required></div>
            </div>
            <div class="form-group">
                <label>Emergency Contact Person <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-ambulance"></i><input type="text" name="emergencyName" value="${escapeHtml(profile.emergency?.name || '')}" required></div>
            </div>
            <div class="form-group">
                <label>Emergency Contact # <span>*</span></label>
                <div class="input-wrapper"><i class="fa-solid fa-phone"></i><input type="text" name="emergencyPhone" value="${escapeHtml(profile.emergency?.number || '')}" required></div>
            </div>

            <div class="form-section-title">Oath of Renter / Tenant</div>
            <div class="legal-sworn-box">
                I promise to abide by all subdivision rules, regulations, and policies set by the Homeowner's Association (HOA) and the local Authorities.<br><br>
                I shall maintain peace, Cleanliness and order within the premises and shall not engage in any activities that may disturb or endanger other residents.<br><br>
                I shall respect the rights and privacy of my neighbors and the community.<br><br>
                I shall ensure that all my Guest and household members also to comply with the subdivision's rules.<br><br>
                I understand that violations of subdivision policies may result in sanctions, which may prevent me from availing any Privileges, Documents, or Requirements from the subdivision.
            </div>
            <div class="form-group full-width checkbox-group" style="margin-top:15px;">
                <input type="checkbox" id="oathAgreement" name="oathAgreed" required>
                <label for="oathAgreement"><strong>I solemnly accept the terms of the Tenant Oath.</strong> <span>*</span></label>
            </div>
        `
    };

    return templates[formId] || templates['gate-pass'];
}

// Metadata lookup for each request type (title -> category/formId/desc), used for the
// resubmission flow so the correct form template can be reopened.
const REQUEST_META = {
    'Gate Pass': { formId: 'gate-pass', category: 'Document Request', desc: 'Materials verification and tracking clearances.' },
    'Proof of Residency': { formId: 'proof-residency', category: 'Document Request', desc: 'Verified subdivision residency status.' },
    'Certificate of Improvement': { formId: 'cert-improvement', category: 'Document Request', desc: 'Unit modification intent.' },
    'Certificate of Membership': { formId: 'cert-membership', category: 'Document Request', desc: 'Updated membership profiles.' },
    'Move-in Gate Pass': { formId: 'move-in', category: 'Property & Moving', desc: 'Residential move-in.' },
    'Move-out Gate Pass': { formId: 'move-out', category: 'Property & Moving', desc: 'Secure transfer extraction.' },
    'Vehicle Sticker Application': { formId: 'vehicle-sticker', category: 'Vehicle Services', desc: 'Windshield tags.' },
    'Renters/Tenants Information Form': { formId: 'tenant-form', category: 'Tenant Services', desc: 'Non-owner tracking logs.' }
};

// Fetch User Data
async function fetchUserData() {
    try {
        const response = await fetch('/api/user-data');
        if (!response.ok) {
            window.location.href = '/';
            return;
        }

        const data = await response.json();
        if (data.status === 'success') {
            currentUserProfile = data.user || {};
            systemFees = data.fees || {};
            populateUserData(data.user);
            populateDashboardData(data.dashboard);
            updateFeeBadges(data.fees);
            renderMyRequestsView(data.dashboard.requests || []);
        }
    } catch (err) {
        console.error('Failed to load user data:', err);
    }
}

// "My Requests" view — grouped by category, with correction workflow support
function renderMyRequestsView(requests) {
    const container = document.getElementById('myRequestsContainer');
    if (!container) return;

    if (!requests.length) {
        container.innerHTML = '<div class="section-box"><p class="empty-placeholder">You have not submitted any requests yet.</p></div>';
        return;
    }

    const groups = {};
    requests.forEach(r => {
        const cat = r.category || 'Document Request';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(r);
    });

    let html = '';
    Object.keys(groups).forEach(category => {
        html += `<div class="section-box"><div class="section-header"><h2>${escapeHtml(category)}</h2></div>`;
        html += `<table><thead><tr><th>ID</th><th>Request</th><th>Submitted</th><th>Fee</th><th>Payment</th><th>Status</th><th>Action</th></tr></thead><tbody>`;
        groups[category].forEach(r => {
            const isCompleted = ['Approved', 'Paid and Approved', 'Completed'].includes(r.status);
            const canCancel = ['Submitted', 'Under Review', 'For Correction'].includes(r.status);
            let actionButtons = '';
            if (r.status === 'For Correction') {
                actionButtons += `<button class="btn-submit" style="padding:3px 10px;font-size:0.75rem;width:auto;" onclick="openResubmitModal('${escapeHtml(r.id)}')">Update &amp; Resubmit</button> `;
            }
            if (canCancel) {
                actionButtons += `<button class="btn-cancel-req" style="padding:2px 8px; font-size:0.75rem; background:#d9534f; color:#fff; border:none; border-radius:4px; cursor:pointer;" onclick="promptCancelRequest('${escapeHtml(r.id)}')">Cancel</button> `;
            }
            actionButtons += `<button class="btn-concern" type="button" onclick="openConcernModal('${escapeHtml(r.id)}','${escapeHtml(r.type || r.title)}')">Report Concern</button> `;
            actionButtons += `<a href="/requests/${encodeURIComponent(r.id)}/pdf" target="_blank" class="request-pdf-link">PDF</a>`;

            html += `<tr>
                <td><strong>${escapeHtml(r.id)}</strong></td>
                <td>${escapeHtml(r.type || r.title)}</td>
                <td>${escapeHtml(r.date)}</td>
                <td>${escapeHtml(r.fee)}</td>
                <td><span class="status-badge ${r.payment_status === 'Paid' ? 'status-completed' : 'status-pending'}">${escapeHtml(r.payment_status || 'Unpaid')}</span></td>
                <td><span class="status-badge ${r.status === 'Cancelled' ? 'status-cancelled' : (isCompleted ? 'status-completed' : 'status-pending')}">${escapeHtml(r.status)}</span></td>
                <td>${actionButtons}</td>
            </tr>`;
            if (r.status === 'For Correction') {
                html += `<tr><td colspan="7" style="background:#FFF3E0;padding:10px 14px;font-size:0.8rem;">
                    <strong>What needs correction:</strong> ${escapeHtml(r.remarks || 'No remarks provided.')}<br>
                    <strong>What to do:</strong> Review the remarks above, click "Update &amp; Resubmit", correct the highlighted information, and submit again for review.
                </td></tr>`;
            }
        });
        html += `</tbody></table></div>`;
    });

    container.innerHTML = html;
}

function openResubmitModal(requestId) {
    fetch('/api/user-data').then(r => r.json()).then(data => {
        const req = (data.dashboard.requests || []).find(r => r.id === requestId);
        if (!req) {
            showToastNotification('Request not found.', 'error');
            return;
        }
        const meta = REQUEST_META[req.type] || { formId: 'gate-pass', category: 'Document Request', desc: '' };
        let details = {};
        try { details = JSON.parse(req.details || '{}'); } catch (err) { details = {}; }

        currentRequestTitle = req.type;
        currentRequestCategory = meta.category;
        currentRequestFee = req.fee;
        resubmitTargetId = requestId;
        resubmitFormId = meta.formId;

        openRequestModal(req.type, meta.category, meta.desc, meta.formId, req.fee, details);
    }).catch(() => showToastNotification('Failed to load request for editing.', 'error'));
}

function updateFeeBadges(fees) {
    if (!fees) return;
    document.querySelectorAll('.btn-request').forEach(btn => {
        const title = btn.getAttribute('data-title');
        if (title === 'Vehicle Sticker Application') return;
        if (fees[title]) {
            const formatted = `₱${parseFloat(fees[title]).toFixed(2)}`;
            btn.setAttribute('data-fee', formatted);
            const cardInfo = btn.closest('.request-card')?.querySelector('.price-badge');
            if (cardInfo) {
                cardInfo.textContent = formatted;
            }
        }
    });
}

function populateUserData(user) {
    if (!user) return;

    const suffixText = (user.suffix && user.suffix !== 'N/A') ? ` ${user.suffix}` : '';
    const fullName = `${user.first_name || ''} ${user.last_name || ''}${suffixText}`.trim() || 'User';

    document.querySelectorAll('.shared-user-name').forEach(el => el.textContent = fullName);
    document.querySelectorAll('.shared-first-name').forEach(el => el.textContent = user.first_name || 'User');

    setSpanText('firstName', user.first_name);
    setSpanText('middleName', user.middle_name || 'N/A');
    setSpanText('lastName', user.last_name);
    setSpanText('suffix', user.suffix || 'N/A');
    setSpanText('gender', user.gender || 'NA');
    setSpanText('dob', user.dob || 'N/A');
    setSpanText('civilStatus', user.civil_status || 'Single');
    setSpanText('subdivision', 'North Fairway Homes');
    setSpanText('block', user.block || 'Not Specified');
    setSpanText('lot', user.lot || 'Not Specified');
    setSpanText('email', user.email);
    setSpanText('mobile', user.mobile);
    setSpanText('household', user.household || '1');
    setSpanText('dateJoined', user.date_joined || '2018-06-14');

    setInputValue('firstName', user.first_name);
    setInputValue('middleName', user.middle_name);
    setInputValue('lastName', user.last_name);
    setInputValue('suffix', user.suffix);
    setInputValue('gender', user.gender || 'NA');
    setInputValue('dob', user.dob);
    setInputValue('civilStatus', user.civil_status || 'Single');
    setInputValue('block', user.block);
    setInputValue('lot', user.lot);
    setInputValue('email', user.email);
    setInputValue('mobile', user.mobile);
    setInputValue('household', user.household);

    const sidebarName = document.getElementById('sidebar-display-name');
    if (sidebarName) sidebarName.textContent = fullName;

    const sidebarId = document.getElementById('sidebar-homeowner-id');
    if (sidebarId) sidebarId.textContent = `Homeowner ID: ${user.id || '-'}`;

    const settingsAvatar = document.getElementById('settingsAvatarLetter');
    if (settingsAvatar && user.first_name) {
        settingsAvatar.textContent = user.first_name.charAt(0).toUpperCase();
    }

    if (user.emergency) {
        setInputElementVal('em-name', user.emergency.name);
        setInputElementVal('em-number', user.emergency.number);
        setSelectVal('em-relationship', user.emergency.relationship);
    }

    if (user.email_notifications !== undefined) setToggleChecked('toggle-email', user.email_notifications);
    else if (user.preferences) setToggleChecked('toggle-email', user.preferences.email);

    if (user.sms_notifications !== undefined) setToggleChecked('toggle-sms', user.sms_notifications);
    else if (user.preferences) setToggleChecked('toggle-sms', user.preferences.sms);

    if (user.profile_image) {
        updateAvatarDisplay(user.profile_image);
    }
}

function populateDashboardData(dash) {
    if (!dash) return;

    const reqCountEl = document.getElementById('activeRequestsCount');
    if (reqCountEl) reqCountEl.textContent = dash.active_requests ?? 0;

    const badgeEl = document.getElementById('bellBadge');
    if (badgeEl) badgeEl.textContent = dash.unread_alerts ?? 0;

    const duesEl = document.getElementById('outstandingDuesCount');
    if (duesEl) duesEl.textContent = (dash.outstanding_dues || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const missingBox = document.getElementById('missingDuesBox');
    const missingText = document.getElementById('missingDuesText');
    if (missingBox && missingText) {
        if (dash.missing_dues_count > 0) {
            missingBox.style.display = 'block';
            missingText.textContent = `You have ${dash.missing_dues_count} unpaid monthly due(s) totaling ₱${Number(dash.missing_dues_total || 0).toFixed(2)}. Oldest unpaid due: ${dash.oldest_unpaid_due || 'N/A'}. Outstanding period: ${dash.outstanding_period || 'N/A'}. Executive approval is unavailable until these dues are cleared by the Treasurer.`;
        } else {
            missingBox.style.display = 'none';
        }
    }

    const tbody = document.getElementById('requestTableBody');
    if (tbody) {
        if (!dash.requests || dash.requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-placeholder">No recent requests found</td></tr>';
        } else {
            tbody.innerHTML = dash.requests.map(r => {
                const canCancel = ['Submitted', 'Pending', 'Under Review', 'For Correction'].includes(r.status);
                const actionBtn = canCancel
                    ? `<button class="btn-cancel-req" style="padding:2px 8px; font-size:0.75rem; background:#d9534f; color:#fff; border:none; border-radius:4px; cursor:pointer;" onclick="promptCancelRequest('${escapeHtml(r.id)}')">Cancel</button>`
                    : '-';

                const isCompleted = ['Approved', 'Paid and Approved', 'Completed'].includes(r.status);

                return `
                    <tr>
                        <td><strong>${escapeHtml(r.id)}</strong></td>
                        <td>${escapeHtml(r.type || r.title)}</td>
                        <td>${escapeHtml(r.date)}</td>
                        <td><strong>${escapeHtml(r.fee)}</strong></td>
                        <td><span class="status-badge ${r.payment_status === 'Paid' ? 'status-completed' : 'status-pending'}">${escapeHtml(r.payment_status || 'Unpaid')}</span></td>
                        <td><span class="status-badge ${r.status === 'Cancelled' ? 'status-cancelled' : (isCompleted ? 'status-completed' : 'status-pending')}">${escapeHtml(r.status)}</span></td>
                        <td>${actionBtn}</td>
                    </tr>
                `;
            }).join('');
        }
    }
}

// Tab Navigation Controls
function setupTabNavigation() {
    document.querySelectorAll('.nav-links a').forEach((link, index) => {
        link.style.setProperty('--nav-order', index);
        link.addEventListener('click', () => {
            const tabTarget = link.id.replace('nav-', '');
            switchTab(tabTarget);
        });
    });
    const menuButton = document.querySelector('.mobile-menu-button');
    if (menuButton) {
        menuButton.setAttribute('aria-controls', 'globalSidebar');
        menuButton.setAttribute('aria-expanded', 'false');
    }
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && document.body.classList.contains('mobile-nav-open')) {
            closeMobileNavigation();
            menuButton?.focus();
        }
    });
    const homeSidebarCollapse = document.getElementById('homeSidebarCollapse');
    if (homeSidebarCollapse) {
        if (sessionStorage.getItem('nfhHomeSidebarCollapsed') === '1' && window.innerWidth >= 1121) document.body.classList.add('home-sidebar-collapsed');
        const syncHomeCollapseButton = () => {
            const collapsed = document.body.classList.contains('home-sidebar-collapsed');
            homeSidebarCollapse.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
            homeSidebarCollapse.title = collapsed ? 'Expand navigation' : 'Collapse navigation';
            const icon = homeSidebarCollapse.querySelector('i');
            if (icon) icon.className = collapsed ? 'fa-solid fa-angles-right' : 'fa-solid fa-angles-left';
        };
        homeSidebarCollapse.addEventListener('click', () => {
            if (window.innerWidth < 1121) return;
            const collapsed = document.body.classList.toggle('home-sidebar-collapsed');
            sessionStorage.setItem('nfhHomeSidebarCollapsed', collapsed ? '1' : '0');
            syncHomeCollapseButton();
        });
        window.addEventListener('resize', () => { if (window.innerWidth < 1121) document.body.classList.remove('home-sidebar-collapsed'); else if (sessionStorage.getItem('nfhHomeSidebarCollapsed') === '1') document.body.classList.add('home-sidebar-collapsed'); syncHomeCollapseButton(); }, {passive:true});
        syncHomeCollapseButton();
    }

    requestAnimationFrame(() => document.body.classList.add('navigation-ready'));
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-links a').forEach(link => link.classList.remove('active'));

    const targetTab = document.getElementById(tabId);
    if (targetTab) {
        targetTab.classList.add('active');
        targetTab.scrollTop = 0;
    }

    const activeNav = document.getElementById(`nav-${tabId}`);
    if (activeNav) activeNav.classList.add('active');

    closeMobileNavigation();

    if (tabId === 'dashboard-view') {
        fetchUserData();
    }
}

function setHomeownerNavigation(open) {
    document.body.classList.toggle('mobile-nav-open', open);
    const menuButton = document.querySelector('.mobile-menu-button');
    if (menuButton) menuButton.setAttribute('aria-expanded', open ? 'true' : 'false');
}
function openMobileNavigation() { setHomeownerNavigation(true); }
function closeMobileNavigation() { setHomeownerNavigation(false); }

// Profile Form Management
function setupProfileForm() {
    const btnEdit = document.getElementById('btnEditProfile');
    const btnCancel = document.getElementById('btnCancel');
    const profileForm = document.getElementById('profileForm');

    if (btnEdit) btnEdit.addEventListener('click', () => document.body.classList.add('is-editing'));
    if (btnCancel) btnCancel.addEventListener('click', () => document.body.classList.remove('is-editing'));

    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const saveBtn = document.getElementById('btn-save-profile');
            if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving...'; }

            const payload = {
                first_name: getInputValue('firstName'),
                middle_name: getInputValue('middleName'),
                last_name: getInputValue('lastName'),
                suffix: getInputValue('suffix'),
                gender: getInputValue('gender'),
                dob: getInputValue('dob'),
                civil_status: getInputValue('civilStatus'),
                block: getInputValue('block'),
                lot: getInputValue('lot'),
                email: getInputValue('email'),
                mobile: getInputValue('mobile'),
                household: getInputValue('household')
            };

            try {
                const response = await fetch('/api/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const result = await response.json();
                if (result.status === 'success') {
                    showToastNotification('Profile updated successfully.', 'success');
                    document.body.classList.remove('is-editing');
                    await fetchUserData();
                } else {
                    showToastNotification(result.message || 'Profile update failed.', 'error');
                }
            } catch (err) {
                console.error('Error updating profile:', err);
                showToastNotification('An error occurred while saving profile.', 'error');
            } finally {
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
            }
        });
    }
}

function updateAvatarDisplay(imageUrl) {
    const imgPreview = document.getElementById('profileImagePreview');
    const defaultIcon = document.getElementById('defaultAvatarIcon');
    const topAvatar = document.getElementById('topBarAvatar');

    if (imgPreview) {
        imgPreview.src = imageUrl;
        imgPreview.style.display = 'block';
    }
    if (defaultIcon) defaultIcon.style.display = 'none';

    if (topAvatar) {
        topAvatar.style.backgroundImage = `url('${imageUrl}')`;
        topAvatar.style.backgroundSize = 'cover';
        topAvatar.style.backgroundPosition = 'center';
    }
}

// Settings Actions
function toggleEdit(section) {
    if (section === 'emergency') {
        const emName = document.getElementById('em-name');
        const emNum = document.getElementById('em-number');
        const emRel = document.getElementById('em-relationship');
        const actionsDiv = document.getElementById('emergency-actions');

        const isDisabled = emName.disabled;
        emName.disabled = !isDisabled;
        emNum.disabled = !isDisabled;
        emRel.disabled = !isDisabled;

        if (isDisabled) {
            emName.focus();
            actionsDiv.innerHTML = `
                <button class="save-btn" onclick="saveEmergencySettings()">Save</button>
                <button class="cancel-btn" onclick="toggleEdit('emergency')">Cancel</button>
            `;
        } else {
            actionsDiv.innerHTML = `<button class="edit-link" onclick="toggleEdit('emergency')">Edit</button>`;
        }
    } else if (section === 'security') {
        const secCurrent = document.getElementById('sec-current');
        const secNew = document.getElementById('sec-new');
        const secConfirm = document.getElementById('sec-confirm');
        const actionsDiv = document.getElementById('security-actions');

        const isDisabled = secCurrent.disabled;
        secCurrent.disabled = !isDisabled;
        secNew.disabled = !isDisabled;
        secConfirm.disabled = !isDisabled;

        if (isDisabled) {
            secCurrent.focus();
            actionsDiv.innerHTML = `
                <button class="save-btn" onclick="saveSecuritySettings()">Save</button>
                <button class="cancel-btn" onclick="toggleEdit('security')">Cancel</button>
            `;
        } else {
            secCurrent.value = '';
            secNew.value = '';
            secConfirm.value = '';
            actionsDiv.innerHTML = `<button class="edit-link" onclick="toggleEdit('security')">Edit</button>`;
        }
    }
}

async function saveEmergencySettings() {
    const name = document.getElementById('em-name').value.trim();
    const number = document.getElementById('em-number').value.trim();
    const relationship = document.getElementById('em-relationship').value;

    if (!name || !number || !relationship) {
        showToastNotification('All emergency contact fields are required.', 'error');
        return;
    }

    try {
        const response = await fetch('/api/settings/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                emergency: { name, number, relationship }
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showToastNotification('Emergency contact saved successfully.', 'success');
            toggleEdit('emergency');
            await fetchUserData();
        } else {
            showToastNotification(result.message || 'Failed to save emergency contact.', 'error');
        }
    } catch (err) {
        console.error('Error saving emergency contact:', err);
        showToastNotification('Server connection error.', 'error');
    }
}

async function saveSecuritySettings() {
    const currentPassword = document.getElementById('sec-current').value;
    const newPassword = document.getElementById('sec-new').value;
    const confirmPassword = document.getElementById('sec-confirm').value;

    if (!currentPassword || !newPassword || !confirmPassword) {
        showToastNotification('All password fields are required.', 'error');
        return;
    }

    if (newPassword !== confirmPassword) {
        showToastNotification('New password and confirmation do not match.', 'error');
        return;
    }

    try {
        const response = await fetch('/api/settings/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showToastNotification('Password changed successfully.', 'success');
            toggleEdit('security');
        } else {
            showToastNotification(result.message || 'Failed to change password.', 'error');
        }
    } catch (err) {
        console.error('Error changing password:', err);
        showToastNotification('Server connection error.', 'error');
    }
}

async function handleToggleChange(prefType) {
    const preferencesPayload = {
        email: document.getElementById('toggle-email').checked,
        sms: document.getElementById('toggle-sms').checked
    };

    try {
        await fetch('/api/settings/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preferences: preferencesPayload })
        });
        showToastNotification(`${prefType} preference updated.`, 'success');
    } catch (err) {
        console.error('Preference update error:', err);
        showToastNotification('Failed to update preference.', 'error');
    }
}

// Vehicle Dynamic Pricing Calculation
function addVehicleRow() {
    const container = document.getElementById('vehicleContainer');
    if (!container) return;

    const currentCount = container.children.length;
    const newIndex = currentCount;

    const fourWheelFee = systemFees['Vehicle Sticker (4 Wheels)'] ? systemFees['Vehicle Sticker (4 Wheels)'].toFixed(2) : '200.00';
    const otherWheelFee = systemFees['Vehicle Sticker (2/3 Wheels)'] ? systemFees['Vehicle Sticker (2/3 Wheels)'].toFixed(2) : '100.00';

    const rowDiv = document.createElement('div');
    rowDiv.className = 'due-item';
    rowDiv.style.cssText = 'flex-direction: column; align-items: stretch; gap: 10px; margin-bottom: 12px; background: var(--input-bg);';
    rowDiv.setAttribute('data-vehicle-index', newIndex);

    rowDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed var(--border-color); padding-bottom: 6px;">
            <strong>Vehicle #${newIndex + 1}</strong>
            <button type="button" class="btn-cancel" style="padding: 2px 8px; font-size: 0.75rem; color: var(--error-color); border-color: var(--error-color);" onclick="removeVehicleRow(this)"><i class="fa-solid fa-trash"></i> Remove</button>
        </div>
        <div class="modal-form">
            <div class="form-group">
                <label>Vehicle Type <span>*</span></label>
                <div class="input-wrapper">
                    <select name="vType_${newIndex}" onchange="recalculateVehiclePricing()" required>
                        <option value="4 Wheels">4 Wheels (₱${fourWheelFee})</option>
                        <option value="2/3 Wheels">2/3 Wheels (₱${otherWheelFee})</option>
                        <option value="E-bike">E-bike (₱${otherWheelFee})</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label>Plate Number <span>*</span></label>
                <div class="input-wrapper"><input type="text" name="vPlate_${newIndex}" placeholder="e.g. ABC 1234" required></div>
            </div>
            <div class="form-group">
                <label>Vehicle Model / Year <span>*</span></label>
                <div class="input-wrapper"><input type="text" name="vModel_${newIndex}" placeholder="e.g. Vios 2022" minlength="4" title="At least 4 characters" required></div>
            </div>
            <div class="form-group">
                <label>Vehicle Color <span>*</span></label>
                <div class="input-wrapper"><input type="text" name="vColor_${newIndex}" placeholder="e.g. Black" pattern="[A-Za-z\s\-]+" title="Letters only" required></div>
            </div>
        </div>
    `;

    container.appendChild(rowDiv);
    recalculateVehiclePricing();
}

function removeVehicleRow(buttonEl) {
    const rowBox = buttonEl.closest('.due-item');
    if (rowBox) {
        rowBox.remove();
        recalculateVehiclePricing();
    }
}

function recalculateVehiclePricing() {
    const feeEl = document.getElementById('modalFeeText');
    if (!feeEl) return;

    const fourWheelPrice = systemFees['Vehicle Sticker (4 Wheels)'] || 200.00;
    const otherWheelPrice = systemFees['Vehicle Sticker (2/3 Wheels)'] || 100.00;

    let total = 0.0;
    const selects = document.querySelectorAll('#vehicleContainer select');
    selects.forEach(sel => {
        const val = sel.value;
        total += (val === '4 Wheels') ? fourWheelPrice : otherWheelPrice;
    });

    currentRequestFee = `₱${total.toFixed(2)}`;
    feeEl.textContent = currentRequestFee;
}

// Overlay Setup
// Vehicle field validation (Requirement: Vehicle Model >= 4 chars, Vehicle Color letters only)
const VEHICLE_COLOR_RE = /^[A-Za-z\s\-]+$/;

function validateVehicleRowsClientSide() {
    const rows = document.querySelectorAll('#vehicleContainer .due-item');
    if (!rows.length) return 'At least one vehicle is required.';
    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const model = (row.querySelector('input[name^="vModel_"]')?.value || '').trim();
        const color = (row.querySelector('input[name^="vColor_"]')?.value || '').trim();
        const plate = (row.querySelector('input[name^="vPlate_"]')?.value || '').trim();
        if (!plate) return `Vehicle #${i + 1}: Plate number is required.`;
        if (model.length < 4) return `Vehicle #${i + 1}: Vehicle Model must be at least 4 characters.`;
        if (!color || !VEHICLE_COLOR_RE.test(color)) return `Vehicle #${i + 1}: Vehicle Color must contain letters only (no numbers or special characters).`;
    }
    return null;
}

function setupRequestButtons() {
    document.querySelectorAll('.btn-request').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const title = btn.getAttribute('data-title') || 'Document Request';
            const category = btn.getAttribute('data-category') || 'Document Request';
            const desc = btn.getAttribute('data-desc') || '';
            const formId = btn.getAttribute('data-form-id') || 'gate-pass';
            const fee = btn.getAttribute('data-fee') || "₱50.00";

            currentRequestFee = fee;
            currentRequestTitle = title;
            currentRequestCategory = category;
            resubmitTargetId = null;

            openRequestModal(title, category, desc, formId, fee);
        });
    });
}

let resubmitTargetId = null;
let resubmitFormId = null;

function openRequestModal(title, category, desc, formId, fee, prefillDetails) {
    const titleEl = document.getElementById('modalTitle');
    const descEl = document.getElementById('modalDesc');
    const metaServiceEl = document.getElementById('metaService');
    const feeEl = document.getElementById('modalFeeText');
    const submitBtn = document.getElementById('btn-submit-request');

    if (titleEl) titleEl.textContent = title;
    if (descEl) descEl.textContent = desc;
    if (metaServiceEl) metaServiceEl.textContent = title;
    if (feeEl) feeEl.textContent = fee;

    const container = document.getElementById('dynamicFormFieldsContainer');
    if (container) {
        container.innerHTML = getTemplateHTML(formId, currentUserProfile);
    }

    if (formId === 'vehicle-sticker') {
        recalculateVehiclePricing();
        if (prefillDetails && Array.isArray(prefillDetails.vehicles)) {
            const vc = document.getElementById('vehicleContainer');
            if (vc) vc.innerHTML = '';
            prefillDetails.vehicles.forEach((v, idx) => {
                addVehicleRow();
                const row = document.querySelectorAll('#vehicleContainer .due-item')[idx];
                if (row) {
                    const typeSel = row.querySelector('select[name^="vType_"]');
                    const plateInp = row.querySelector('input[name^="vPlate_"]');
                    const modelInp = row.querySelector('input[name^="vModel_"]');
                    const colorInp = row.querySelector('input[name^="vColor_"]');
                    if (typeSel) typeSel.value = v.type || '4 Wheels';
                    if (plateInp) plateInp.value = v.plate || '';
                    if (modelInp) modelInp.value = v.model || '';
                    if (colorInp) colorInp.value = v.color || '';
                }
            });
            recalculateVehiclePricing();
        }
    } else if (prefillDetails) {
        // Generic prefill: match stored detail keys to input/select/textarea "name" attributes.
        Object.entries(prefillDetails).forEach(([key, val]) => {
            const field = container ? container.querySelector(`[name="${key}"]`) : null;
            if (field && field.type !== 'checkbox') field.value = val;
            if (field && field.type === 'checkbox') field.checked = Boolean(val);
        });
    }

    if (submitBtn) {
        const label = resubmitTargetId ? 'Resubmit Request' : 'Submit Document Request';
        submitBtn.innerHTML = `<i class="fa-regular fa-paper-plane"></i><span>${label}</span>`;
    }

    const modal = document.getElementById('requestModal');
    if (modal) modal.classList.add('active');
}

function closeRequestModal() {
    const modal = document.getElementById('requestModal');
    if (modal) modal.classList.remove('active');
    const form = document.getElementById('submissionForm');
    if (form) form.reset();
    resubmitTargetId = null;
    resubmitFormId = null;
}

function setupModalListeners() {
    const closeBtn = document.getElementById('closeRequestModalBtn');
    const cancelBtn = document.getElementById('cancelRequestModalBtn');
    const requestModal = document.getElementById('requestModal');
    const generalModal = document.getElementById('generalModal');
    const confirmCancelBtn = document.getElementById('btn-confirm-cancel-request');

    if (closeBtn) closeBtn.addEventListener('click', closeRequestModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeRequestModal);
    if (confirmCancelBtn) confirmCancelBtn.addEventListener('click', executeRequestCancellation);

    window.addEventListener('click', (e) => {
        if (e.target === requestModal) closeRequestModal();
        if (e.target === generalModal) closeGeneralModal();
        if (e.target === document.getElementById('cancelConfirmModal')) closeCancelConfirmModal();
    });
}

// Request Processing
async function handleRequestSubmit(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('btn-submit-request');
    const originalBtnText = submitBtn ? submitBtn.textContent : 'Submit Document Request';

    const form = e.target;
    const formDataObj = {};
    const formData = new FormData(form);

    if (currentRequestTitle.includes('Vehicle')) {
        const validationError = validateVehicleRowsClientSide();
        if (validationError) {
            showToastNotification(validationError, 'error');
            return;
        }
        const vehicles = [];
        const rows = document.querySelectorAll('#vehicleContainer .due-item');
        rows.forEach((row) => {
            vehicles.push({
                type: row.querySelector(`select[name^="vType_"]`)?.value || '4 Wheels',
                plate: row.querySelector(`input[name^="vPlate_"]`)?.value || '',
                model: row.querySelector(`input[name^="vModel_"]`)?.value || '',
                color: row.querySelector(`input[name^="vColor_"]`)?.value || ''
            });
        });
        formDataObj.vehicles = vehicles;
    }

    formData.forEach((value, key) => {
        if (!key.startsWith('vType_') && !key.startsWith('vPlate_') && !key.startsWith('vModel_') && !key.startsWith('vColor_')) {
            formDataObj[key] = value;
        }
    });

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = resubmitTargetId ? 'Resubmitting...' : 'Submitting...';
    }

    try {
        const isResubmit = Boolean(resubmitTargetId);
        const endpoint = isResubmit ? '/api/requests/resubmit' : '/api/requests/submit';
        const payload = isResubmit
            ? { request_id: resubmitTargetId, formData: formDataObj }
            : {
                title: currentRequestTitle,
                category: currentRequestCategory,
                formData: formDataObj
            };

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.status === 'success') {
            closeRequestModal();
            showToastNotification(result.message || 'Request submitted successfully!', 'success');
            await fetchUserData();
            switchTab(isResubmit ? 'myrequests-view' : 'dashboard-view');
        } else {
            showToastNotification(result.message || 'Submission failed.', 'error');
        }
    } catch (err) {
        console.error('Error submitting request:', err);
        showToastNotification('An error occurred while connecting to the server.', 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<i class="fa-regular fa-paper-plane"></i><span>${escapeHtml(originalBtnText)}</span>`;
        }
    }
}

// Cancellation Handling with reason support
function promptCancelRequest(requestId) {
    requestToCancelId = requestId;
    const reasonInput = document.getElementById('cancelReasonInput');
    if (reasonInput) reasonInput.value = '';
    const modal = document.getElementById('cancelConfirmModal');
    if (modal) modal.classList.add('active');
}

function closeCancelConfirmModal() {
    requestToCancelId = null;
    const modal = document.getElementById('cancelConfirmModal');
    if (modal) modal.classList.remove('active');
}

async function executeRequestCancellation() {
    if (!requestToCancelId) return;

    const confirmBtn = document.getElementById('btn-confirm-cancel-request');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Cancelling...';
    }

    const reason = document.getElementById('cancelReasonInput')?.value || '';

    try {
        const response = await fetch('/api/requests/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: requestToCancelId,
                reason: reason
            })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            closeCancelConfirmModal();
            closeGeneralModal();
            showToastNotification(result.message || 'Request cancelled successfully.', 'info');
            await fetchUserData();
        } else {
            showToastNotification(result.message || 'Failed to cancel request.', 'error');
        }
    } catch (err) {
        console.error('Error cancelling request:', err);
        showToastNotification('Connection error while cancelling request.', 'error');
    } finally {
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm Cancellation';
        }
    }
}

// Helper Functions
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setSpanText(fieldName, val) {
    const span = document.querySelector(`span[data-field="${fieldName}"]`);
    if (span) span.textContent = val || '-';
}

function setInputValue(fieldName, val) {
    const input = document.querySelector(`[name="${fieldName}"]`);
    if (input) input.value = val || '';
}

function getInputValue(fieldName) {
    const input = document.querySelector(`[name="${fieldName}"]`);
    return input ? input.value : '';
}

function setInputElementVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val || '';
}

function setSelectVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val || 'Spouse';
}

function setToggleChecked(id, isChecked) {
    const toggle = document.getElementById(id);
    if (toggle) toggle.checked = Boolean(isChecked);
}

// Unified Section Modal with direct Treasurer instructions and Financial tables
async function openSectionModal(title) {
    const titleEl = document.getElementById('generalModalTitle');
    const bodyEl = document.getElementById('generalModalBody');

    if (titleEl) titleEl.textContent = title;

    // Online payment instructions notice
    if (title.includes('Contact Treasurer') || title.includes('Online Payment')) {
        bodyEl.innerHTML = `
            <div style="font-size:0.92rem;line-height:1.7;color:var(--text-dark);">
                <strong>Want to pay online?</strong><br><br>
                The NFH System does <strong>not</strong> process online payments directly. If you want to make an online payment or bank/e-wallet transfer, please contact the <strong>Treasurer directly</strong> for the official payment instructions and coordination.<br><br>
                Your payment will only be recorded in the NFH System after it has been personally confirmed and recorded by the Treasurer.
            </div>`;
        document.getElementById('generalModal').classList.add('active');
        return;
    }

    // Missing Monthly Dues detail view
    if (title === 'Missing Monthly Dues Detail') {
        try {
            const res = await fetch('/api/user-data');
            const data = await res.json();
            const missing = data.dashboard.missing_dues || [];
            if (!missing.length) {
                bodyEl.innerHTML = '<div class="empty-placeholder">No missing monthly dues on record.</div>';
            } else {
                bodyEl.innerHTML = `
                    <p style="font-size:0.9rem;margin-bottom:12px;">Outstanding dues: <strong>₱${Number(data.dashboard.missing_dues_total || 0).toFixed(2)}</strong> across ${missing.length} month(s). Oldest unpaid due: <strong>${escapeHtml(data.dashboard.oldest_unpaid_due || 'N/A')}</strong>. Outstanding period: <strong>${escapeHtml(data.dashboard.outstanding_period || 'N/A')}</strong>. Please settle with the Treasurer before Executive approval can proceed.</p>
                    <table><thead><tr><th>Month</th><th>Amount</th></tr></thead><tbody>
                        ${missing.map(m => `<tr><td>${escapeHtml(m.due_month)}</td><td>${escapeHtml(m.amount)}</td></tr>`).join('')}
                    </tbody></table>`;
            }
        } catch (err) {
            bodyEl.innerHTML = '<div class="empty-placeholder">Failed to load missing dues.</div>';
        }
        document.getElementById('generalModal').classList.add('active');
        return;
    }

    try {
        const response = await fetch('/api/user-data');
        const data = await response.json();
        const userRequests = data.dashboard.requests || [];
        const userAlerts = data.dashboard.alerts || [];

        if (title.includes('Request')) {
            if (userRequests.length === 0) {
                bodyEl.innerHTML = `<div class="empty-placeholder">No request records available.</div>`;
            } else {
                let html = `<table><thead><tr><th>ID</th><th>Type</th><th>Submitted</th><th>Fee</th><th>Payment Status</th><th>Status</th><th>Action</th></tr></thead><tbody>`;
                userRequests.forEach(r => {
                    const canCancel = ['Submitted', 'Pending', 'Under Review', 'For Correction'].includes(r.status);
                    let actionBtn = canCancel
                        ? `<button class="btn-cancel-req" style="padding:2px 8px; font-size:0.75rem; background:#d9534f; color:#fff; border:none; border-radius:4px; cursor:pointer;" onclick="promptCancelRequest('${escapeHtml(r.id)}')">Cancel</button>`
                        : '';
                    if (r.status === 'For Correction') {
                        actionBtn = `<button class="btn-submit" style="padding:2px 8px;font-size:0.75rem;width:auto;" onclick="closeGeneralModal();openResubmitModal('${escapeHtml(r.id)}')">Resubmit</button> ` + actionBtn;
                    }
                    actionBtn += ` <a href="/requests/${encodeURIComponent(r.id)}/pdf" target="_blank" style="font-size:0.75rem;">PDF</a>`;

                    const isCompleted = ['Approved', 'Paid and Approved', 'Completed'].includes(r.status);

                    html += `<tr>
                        <td><strong>${escapeHtml(r.id)}</strong></td>
                        <td>${escapeHtml(r.type || r.title)}</td>
                        <td>${escapeHtml(r.date)}</td>
                        <td>${escapeHtml(r.fee)}</td>
                        <td><span class="status-badge ${r.payment_status === 'Paid' ? 'status-completed' : 'status-pending'}">${escapeHtml(r.payment_status || 'Unpaid')}</span></td>
                        <td><span class="status-badge ${r.status === 'Cancelled' ? 'status-cancelled' : (isCompleted ? 'status-completed' : 'status-pending')}">${escapeHtml(r.status)}</span></td>
                        <td>${actionBtn}</td>
                    </tr>`;
                });
                html += `</tbody></table>`;
                bodyEl.innerHTML = html;
            }
        } else if (title.includes('Due') || title.includes('Outstanding')) {
            const unpaidRequests = userRequests.filter(r => r.payment_status === 'Unpaid' && r.status !== 'Rejected' && r.status !== 'Cancelled');
            if (unpaidRequests.length === 0) {
                bodyEl.innerHTML = `<div class="empty-placeholder">No outstanding dues pending payment.</div>`;
            } else {
                let html = `<div style="display:flex; flex-direction:column; gap:10px;">`;
                unpaidRequests.forEach(d => {
                    html += `<div class="due-item"><div><strong>${escapeHtml(d.type || d.title)} (${escapeHtml(d.id)})</strong><br><small>Submitted on ${escapeHtml(d.date)}</small></div><div class="due-amount">${escapeHtml(d.fee)}</div></div>`;
                });
                html += `</div>`;
                bodyEl.innerHTML = html;
            }
        } else if (title.includes('Notification') || title.includes('Alert')) {
            if (userAlerts.length === 0) {
                bodyEl.innerHTML = `<div class="empty-placeholder">No alerts to display.</div>`;
            } else {
                let html = `<div class="notif-list">`;
                userAlerts.forEach(a => {
                    html += `<div class="notif-item ${a.unread ? 'unread' : ''}">
                        <div class="notif-icon"><i class="fa-regular fa-bell"></i></div>
                        <div class="notif-content"><span class="notif-message">${escapeHtml(a.text)}</span><span class="notif-time">${escapeHtml(a.time)}</span></div>
                        <span class="notif-state" aria-label="${a.unread ? 'Unread' : 'Read'}"></span>
                    </div>`;
                });
                html += `</div>`;
                bodyEl.innerHTML = html;

                await fetch('/api/alerts/read', { method: 'POST' });
                fetchUserData();
            }
        }
    } catch (err) {
        console.error('Error fetching modal details:', err);
    }

    const modal = document.getElementById('generalModal');
    if (modal) modal.classList.add('active');
}

function closeGeneralModal() {
    const modal = document.getElementById('generalModal');
    if (modal) modal.classList.remove('active');
}

function handleSignOut() {
    const modal = document.getElementById('homeownerLogoutModal');
    if (modal) modal.classList.add('active');
}

function closeHomeownerLogoutModal() {
    const modal = document.getElementById('homeownerLogoutModal');
    if (modal) modal.classList.remove('active');
}

async function confirmHomeownerSignOut() {
    const button = document.querySelector('.logout-confirm-btn');
    if (button) { button.disabled = true; button.textContent = 'Signing Out...'; }
    try {
        const response = await fetch('/api/logout', { method: 'POST' });
        const result = await response.json();
        closeHomeownerLogoutModal();
        showToastNotification(result.message || 'Logged out successfully.', 'info');
        setTimeout(() => { window.location.href = '/'; }, 450);
    } catch (err) {
        console.error('Signout error:', err);
        window.location.href = '/';
    } finally {
        if (button) { button.disabled = false; button.textContent = 'Sign Out'; }
    }
}

function toggleHomeAccountMenu(btn){const menu=btn.closest('.home-account-menu')?.querySelector('.home-account-dropdown');if(!menu)return;const opening=menu.hasAttribute('hidden');if(opening){menu.removeAttribute('hidden');btn.setAttribute('aria-expanded','true')}else{menu.setAttribute('hidden','');btn.setAttribute('aria-expanded','false')}}
function closeHomeAccountMenu(){document.querySelector('.home-account-dropdown')?.setAttribute('hidden','');document.querySelector('.home-account-button')?.setAttribute('aria-expanded','false')}
document.addEventListener('click',e=>{if(!e.target.closest('.home-account-menu'))closeHomeAccountMenu()});
fetch('/api/user-data',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():null).then(d=>{const u=d?.user||d?.user_data||d;if(u?.email){const el=document.getElementById('homeAccountEmail');if(el)el.textContent=u.email}}).catch(()=>{});


// Password controls: icon-only eye toggle and icon-only Caps Lock indicator.
(function initPasswordUsability(){
  const EYE_OPEN = '<svg class="eye-icon eye-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.7"/></svg>';
  const EYE_CLOSED = '<svg class="eye-icon eye-closed" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 6.2A9.7 9.7 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-3.1 3.8M6.2 6.2C3.8 8 2.5 12 2.5 12s3.5 6 9.5 6a9.8 9.8 0 0 0 3.2-.5"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  function setup(){
    document.querySelectorAll('[data-toggle-password]').forEach(function(btn){
      if(btn.dataset.passwordReady) return;
      btn.dataset.passwordReady='1';
      btn.innerHTML=EYE_OPEN;
      btn.addEventListener('click', function(){
        var input=document.getElementById(btn.dataset.togglePassword);
        if(!input) return;
        var reveal=input.type==='password';
        input.type=reveal?'text':'password';
        btn.innerHTML=reveal?EYE_CLOSED:EYE_OPEN;
        btn.setAttribute('aria-label', reveal?'Hide password':'Show password');
        btn.title=reveal?'Hide password':'Show password';
        input.focus({preventScroll:true});
      });
    });
    document.querySelectorAll('.password-field input').forEach(function(input){
      if(input.dataset.capsReady) return;
      input.dataset.capsReady='1';
      var field=input.closest('.password-field');
      if(!field) return;
      var icon=document.createElement('span');
      icon.className='caps-lock-icon';
      icon.setAttribute('aria-label','Caps Lock is on');
      icon.title='Caps Lock is on';
      icon.textContent='⇪';
      icon.hidden=true;
      field.appendChild(icon);
      function caps(e){ if(e.getModifierState) icon.hidden=!e.getModifierState('CapsLock'); }
      input.addEventListener('keydown',caps);
      input.addEventListener('keyup',caps);
      input.addEventListener('focus',function(e){ if(e.getModifierState) caps(e); });
      input.addEventListener('blur',function(){ icon.hidden=true; });
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',setup); else setup();
})();


let activeConcernRequestId = null;
function openConcernModal(requestId, requestType){
  activeConcernRequestId=requestId;
  document.getElementById('concernRequestId').textContent=requestId;
  document.getElementById('concernRequestType').textContent=requestType;
  document.getElementById('concernMessage').value='';
  const modal=document.getElementById('concernModal'); modal.classList.add('active'); modal.setAttribute('aria-hidden','false');
  fetch('/api/requests/concerns').then(r=>r.json()).then(data=>{
    const list=document.getElementById('existingConcernList');
    const rows=(data.concerns||[]).filter(c=>c.request_id===requestId);
    list.innerHTML=rows.length?'<h4>Previous concerns</h4>'+rows.map(c=>`<div class="concern-history-item"><strong>${escapeHtml(c.status)}</strong><p>${escapeHtml(c.concern_text)}</p>${c.response_text?`<div class="concern-response"><strong>${escapeHtml(c.assigned_role)} response</strong><p>${escapeHtml(c.response_text)}</p></div>`:''}</div>`).join(''):'';
  });
}
function closeConcernModal(){const m=document.getElementById('concernModal');m.classList.remove('active');m.setAttribute('aria-hidden','true');activeConcernRequestId=null;}
async function submitConcern(){
 const message=document.getElementById('concernMessage').value.trim();
 if(message.length<5){showToastNotification('Please enter a clear concern.','error');return;}
 const res=await fetch('/api/requests/concern',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:activeConcernRequestId,message})});
 const data=await res.json(); showToastNotification(data.message||'Concern submitted.',data.status==='success'?'success':'error'); if(data.status==='success') closeConcernModal();
}
window.openConcernModal=openConcernModal; window.closeConcernModal=closeConcernModal; window.submitConcern=submitConcern;
