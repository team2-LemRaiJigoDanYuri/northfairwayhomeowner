document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const desktopSidebarToggle = document.getElementById('desktopSidebarToggle');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item[data-tab]');
    const tabContents = document.querySelectorAll('.tab-content');
    const pageTitle = document.getElementById('pageTitle');

    const setSidebarOpen = (open) => {
        if (!sidebar) return;
        sidebar.classList.toggle('open', open);
        document.body.classList.toggle('sidebar-open', open);
        if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };

    const syncDesktopToggle = () => {
        if (!desktopSidebarToggle) return;
        const collapsed = document.body.classList.contains('sidebar-collapsed');
        desktopSidebarToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        desktopSidebarToggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        desktopSidebarToggle.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        const icon = desktopSidebarToggle.querySelector('i');
        if (icon) icon.className = collapsed ? 'fa-solid fa-angles-right' : 'fa-solid fa-angles-left';
    };
    if (sidebarToggle) sidebarToggle.addEventListener('click', () => setSidebarOpen(!sidebar.classList.contains('open')));
    if (desktopSidebarToggle) desktopSidebarToggle.addEventListener('click', () => {
        if (window.innerWidth < 1024) return;
        const collapsed = document.body.classList.toggle('sidebar-collapsed');
        sessionStorage.setItem('nfhSidebarCollapsed', collapsed ? '1' : '0');
        syncDesktopToggle();
    });
    if (window.innerWidth >= 1024 && sessionStorage.getItem('nfhSidebarCollapsed') === '1') document.body.classList.add('sidebar-collapsed');
    syncDesktopToggle();
    if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && window.innerWidth < 1024 && sidebar?.classList.contains('open')) {
            setSidebarOpen(false);
            sidebarToggle?.focus();
        }
    });

    navItems.forEach((item, index) => {
        item.style.setProperty('--nav-order', index);
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const target = item.getAttribute('data-tab');
            navItems.forEach(i => i.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            item.classList.add('active');
            const tc = document.getElementById(target);
            if (tc) { tc.classList.add('active'); tc.scrollTop = 0; }
            if (pageTitle) pageTitle.textContent = item.querySelector('span').textContent;
            if (window.innerWidth < 1024) setSidebarOpen(false);
        });
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth >= 1024) setSidebarOpen(false);
        syncDesktopToggle();
    }, { passive: true });

    document.querySelectorAll('[data-activity-time]').forEach(el => {
        const raw = (el.dataset.activityTime || '').trim();
        const parsed = new Date(raw.replace(' ', 'T'));
        if (!Number.isNaN(parsed.getTime())) el.textContent = parsed.toLocaleString('en-US', {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}).replace(',', ' •');
    });

    requestAnimationFrame(() => document.body.classList.add('navigation-ready'));

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', () => openModal('logoutModal'));
});

function openModal(id){ const m=document.getElementById(id); if(m) m.classList.add('show'); }
function closeModal(id){ const m=document.getElementById(id); if(m) m.classList.remove('show'); }
function escapeHtml(s){ if(!s) return ''; return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;"); }

// Professional in-system confirmation, toast, and inline validation utilities.
let activeConfirmResolve = null;
let activeConfirmTrigger = null;

function showToast(message, type='info', timeout=4200){
    const container=document.getElementById('toastContainer');
    if(!container || !message) return;
    const toast=document.createElement('div');
    toast.className=`system-toast toast-${type}`;
    const icon={success:'✓',error:'!',warning:'!',info:'i'}[type] || 'i';
    toast.innerHTML=`<span class="toast-icon" aria-hidden="true">${icon}</span><div class="toast-message"></div><button type="button" class="toast-close" aria-label="Dismiss notification">×</button>`;
    toast.querySelector('.toast-message').textContent=message;
    toast.querySelector('.toast-close').addEventListener('click',()=>dismissToast(toast));
    container.appendChild(toast);
    requestAnimationFrame(()=>toast.classList.add('show'));
    if(timeout) setTimeout(()=>dismissToast(toast),timeout);
}
function dismissToast(toast){
    if(!toast || toast.dataset.closing==='true') return;
    toast.dataset.closing='true'; toast.classList.remove('show');
    setTimeout(()=>toast.remove(),220);
}

function showConfirmModal({title='Confirm Action',message='',confirmText='Confirm',type='primary',context=[]}={}){
    const modal=document.getElementById('systemConfirmModal');
    if(!modal) return Promise.resolve(false);
    activeConfirmTrigger=document.activeElement;
    document.getElementById('systemConfirmTitle').textContent=title;
    document.getElementById('systemConfirmMessage').textContent=message;
    const contextWrap=document.getElementById('systemConfirmContext');
    contextWrap.innerHTML='';
    (context||[]).filter(item=>item && item.value!==undefined && item.value!=='').forEach(item=>{
        const row=document.createElement('div'); row.className='confirm-context-row';
        const label=document.createElement('span'); label.textContent=item.label;
        const value=document.createElement('strong'); value.textContent=String(item.value);
        row.append(label,value); contextWrap.appendChild(row);
    });
    contextWrap.hidden=!contextWrap.children.length;
    const confirmBtn=document.getElementById('systemConfirmButton');
    confirmBtn.textContent=confirmText;
    confirmBtn.className=`btn confirm-primary confirm-${type}`;
    modal.classList.add('show');
    confirmBtn.disabled=false;
    setTimeout(()=>confirmBtn.focus(),0);
    return new Promise(resolve=>{ activeConfirmResolve=resolve; });
}
function closeSystemConfirm(result=false){
    const modal=document.getElementById('systemConfirmModal');
    if(modal) modal.classList.remove('show');
    const resolver=activeConfirmResolve; activeConfirmResolve=null;
    if(resolver) resolver(Boolean(result));
    setTimeout(()=>activeConfirmTrigger?.focus?.(),0);
}
function confirmSystemAction(){ closeSystemConfirm(true); }

function clearInlineError(input){
    if(!input) return;
    input.classList.remove('field-invalid');
    const error=input.closest('.form-group')?.querySelector('.inline-validation-message');
    if(error) error.remove();
}
function showInlineError(input,message){
    if(!input){ showToast(message,'warning'); return; }
    clearInlineError(input); input.classList.add('field-invalid');
    const group=input.closest('.form-group') || input.parentElement;
    const error=document.createElement('div'); error.className='inline-validation-message'; error.setAttribute('role','alert'); error.textContent=message;
    group.appendChild(error); input.focus();
    input.addEventListener('input',()=>clearInlineError(input),{once:true});
}

function mirrorSubmitter(form, submitter){
    if (!form || !submitter || !submitter.name) return;
    let actionMirror=form.querySelector('input[data-submit-action-mirror="true"]');
    if(!actionMirror){ actionMirror=document.createElement('input'); actionMirror.type='hidden'; actionMirror.dataset.submitActionMirror='true'; form.appendChild(actionMirror); }
    actionMirror.name=submitter.name; actionMirror.value=submitter.value;
}
function lockWorkflowSubmit(form, submitter){
    if (!form || form.dataset.submitting === 'true') return false;
    mirrorSubmitter(form,submitter);
    form.dataset.submitting='true';
    form.querySelectorAll('button[type="submit"]').forEach(btn=>{btn.disabled=true;});
    if(submitter){ submitter.dataset.originalText=submitter.textContent; submitter.textContent='Processing…'; }
    return true;
}

async function validateCheckForm(event){
    event.preventDefault();
    const form=event.currentTarget, submitter=event.submitter;
    if(form.dataset.confirmed==='true') return false;
    const action=submitter ? submitter.value : null;
    const remarks=document.getElementById('checkFormRemarks');
    if(action==='correction' && !remarks.value.trim()){
        showInlineError(remarks,'Please provide the correction reason before returning this request.');
        return false;
    }
    clearInlineError(remarks);
    const reqId=document.getElementById('modalReqId')?.textContent || '';
    const isCorrection=action==='correction';
    const ok=await showConfirmModal({
        title:isCorrection ? 'Return Request for Correction' : 'Confirm Request Review',
        message:isCorrection ? 'Return this request to the homeowner for correction using the remarks you provided?' : 'Mark this request as Checked and forward it to the President for approval?',
        confirmText:isCorrection ? 'Return for Correction' : 'Mark as Checked',
        type:isCorrection ? 'warning' : 'primary',
        context:[{label:'Request ID',value:reqId}]
    });
    if(!ok) return false;
    if(!lockWorkflowSubmit(form,submitter)) return false;
    form.submit();
    return false;
}

async function submitPreviewAction(event, legacyMessage){
    event.preventDefault();
    const form=event.currentTarget, submitter=event.submitter;
    if(!submitter) return false;
    const action=(submitter.value || submitter.textContent || '').trim().toLowerCase();
    const reqId=document.getElementById('previewReqId')?.textContent || form.closest('tr')?.querySelector('code')?.textContent || '';
    let title='Confirm Action', message=legacyMessage || 'Confirm this action?', confirmText=submitter.textContent.trim(), type='primary';
    if(action==='approve'){title='Approve Request';message='Approve this request and continue it through the existing workflow?';confirmText='Approve Request';}
    else if(action==='reject'){title='Reject Request';message='Record a rejection decision for this request?';confirmText='Reject Request';type='danger';}
    else if((submitter.textContent||'').toLowerCase().includes('paid')){title='Confirm Payment';message='Confirm that payment has been received and coordinated by the Treasurer?';confirmText='Mark as Paid';}
    const ok=await showConfirmModal({title,message,confirmText,type,context:[{label:'Request ID',value:reqId}]});
    if(!ok) return false;
    if(!lockWorkflowSubmit(form,submitter)) return false;
    form.submit();
    return false;
}
// Automatically calculates the total amount due (Monthly Due x Missing Months)
function calculateAdjustment() {
    const monthlyDue = parseFloat(document.getElementById('adjMonthlyDue').value) || 0;
    const missingMonths = parseInt(document.getElementById('adjMissing').value, 10) || 0;
    const proposedField = document.getElementById('adjProposed');

    if (missingMonths > 0) {
        const total = (monthlyDue * missingMonths).toFixed(2);
        proposedField.value = total;
    } else {
        proposedField.value = '';
    }
}

async function submitAdjustment(){
    const userInput=document.getElementById('adjUserId');
    const monthsInput=document.getElementById('adjMissing');
    const userId=userInput.value;
    const missingMonths=monthsInput.value;
    const proposed=document.getElementById('adjProposed').value;
    clearInlineError(userInput); clearInlineError(monthsInput);
    if(!userId){ showInlineError(userInput,'Please select a homeowner from the dropdown list.'); return; }
    if(!missingMonths || parseInt(missingMonths,10)<=0){ showInlineError(monthsInput,'Please enter a valid number of missing months.'); return; }
    const homeowner=userInput.options[userInput.selectedIndex]?.text || 'Selected homeowner';
    const ok=await showConfirmModal({
        title:'Apply Missing Dues Adjustment',
        message:'Apply this missing dues adjustment and notify the homeowner?',
        confirmText:'Apply Adjustment',
        type:'primary',
        context:[{label:'Homeowner',value:homeowner},{label:'Missing Months',value:missingMonths},{label:'Total',value:proposed ? `₱${Number(proposed).toFixed(2)}` : ''}]
    });
    if(!ok) return;
    fetch('/api/treasurer/submit-adjustment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        user_id:userId,monthly_due:document.getElementById('adjMonthlyDue').value,missing_months:missingMonths,
        proposed_adjustment:proposed,reason:document.getElementById('adjReason').value
    })})
    .then(async r=>{const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.message||'Unable to apply adjustment.'); return d;})
    .then(d=>{ if(d.status==='success'){showToast(d.message||'Adjustment applied.','success');setTimeout(()=>location.reload(),700);} else showToast(d.message||'Unable to apply adjustment.','error'); })
    .catch(e=>showToast(e.message||'Unable to apply adjustment.','error'));
}

function parseRequestDetails(raw){
    if (!raw) return {};
    if (typeof raw === 'object') return raw;
    try { return JSON.parse(raw); } catch (_) { return { notes: String(raw) }; }
}

function humanizeKey(key){
    const known = {
        fullName:'Full Name', blockNum:'Block Number', lotNum:'Lot Number', blockLot:'Block / Lot',
        vehicleModel:'Vehicle Model', vehicleColor:'Vehicle Color', plateNumber:'Plate Number',
        vModel:'Vehicle Model', vColor:'Vehicle Color', vPlate:'Plate Number', vType:'Vehicle Type',
        moveDate:'Moving Date', tenantName:'Tenant Name', contactNumber:'Contact Number',
        purpose:'Purpose', address:'Address', relationship:'Relationship', remarks:'Remarks'
    };
    if (known[key]) return known[key];
    return String(key).replace(/_/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2').replace(/\b\w/g,c=>c.toUpperCase());
}

function formatSubmittedDate(value){
    if (!value || String(value).includes('%Y-') || String(value).includes('%H:')) return 'Date unavailable';
    const normalized=String(value).replace(' ','T');
    const d=new Date(normalized);
    if (Number.isNaN(d.getTime())) return escapeHtml(String(value));
    return d.toLocaleString('en-PH',{year:'numeric',month:'long',day:'numeric',hour:'numeric',minute:'2-digit'}).replace(' at ', ' • ');
}

function renderDetailValue(value){
    if (value === null || value === undefined || value === '') return '<span class="detail-empty">Not provided</span>';
    if (Array.isArray(value)) {
        if (!value.length) return '<span class="detail-empty">None</span>';
        return `<div class="nested-detail-list">${value.map((item,index)=>{
            if (item && typeof item === 'object') {
                return `<div class="nested-detail-card"><div class="nested-detail-title">Item ${index+1}</div>${Object.entries(item).map(([k,v])=>`<div class="detail-row compact"><span>${escapeHtml(humanizeKey(k))}</span><strong>${escapeHtml(String(v ?? ''))}</strong></div>`).join('')}</div>`;
            }
            return `<div class="detail-chip">${escapeHtml(String(item))}</div>`;
        }).join('')}</div>`;
    }
    if (typeof value === 'object') {
        return `<div class="nested-detail-card">${Object.entries(value).map(([k,v])=>`<div class="detail-row compact"><span>${escapeHtml(humanizeKey(k))}</span><strong>${escapeHtml(String(v ?? ''))}</strong></div>`).join('')}</div>`;
    }
    return escapeHtml(String(value));
}

function buildRequestReviewHTML(req){
    const parsed=parseRequestDetails(req.details);
    const detailEntries=Object.entries(parsed).filter(([k])=>!['fullName','blockNum','lotNum'].includes(k));
    const fullName=parsed.fullName || req.homeowner || 'Not provided';
    const block=parsed.blockNum || parsed.block || '';
    const lot=parsed.lotNum || parsed.lot || '';
    const homeownerMeta=[block ? `Block ${escapeHtml(String(block))}` : '', lot ? `Lot ${escapeHtml(String(lot))}` : ''].filter(Boolean).join(' • ');
    const attachment=req.attachment ? `<a class="btn btn-sm btn-secondary btn-with-icon" href="/static/uploads/${encodeURIComponent(req.attachment)}" target="_blank" rel="noopener"><span aria-hidden="true">↗</span> View Attachment</a>` : '<span class="detail-empty">No attachment</span>';
    const pdf=`<a class="btn btn-sm btn-primary btn-with-icon" href="/requests/${encodeURIComponent(req.id)}/pdf" target="_blank" rel="noopener"><span aria-hidden="true">⇩</span> Download PDF</a>`;
    return `
      <section class="review-section request-summary-section">
        <div class="request-summary-top">
          <div><span class="review-kicker">${escapeHtml(req.category || 'Request')}</span><h4>${escapeHtml(req.request_type || 'Request')}</h4><div class="submitted-meta">Submitted ${formatSubmittedDate(req.date_submitted)}</div></div>
          <div class="review-status-stack"><span class="status-pill status-${String(req.status||'').replace(/ /g,'-').toLowerCase()}">${escapeHtml(req.status||'')}</span><span class="pay-pill pay-${String(req.payment_status||'').toLowerCase()}">${escapeHtml(req.payment_status||'')}</span></div>
        </div>
      </section>
      <section class="review-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">⌂</span><div><h4>Homeowner Information</h4><p>Registered requester information</p></div></div>
        <div class="detail-grid">
          <div class="detail-field"><span>Full Name</span><strong>${escapeHtml(String(fullName))}</strong>${homeownerMeta ? `<small>${homeownerMeta}</small>`:''}</div>
          <div class="detail-field"><span>Request ID</span><strong>${escapeHtml(req.id)}</strong></div>
        </div>
      </section>
      <section class="review-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">▤</span><div><h4>Request Information</h4><p>Classification and processing details</p></div></div>
        <div class="detail-grid four-up">
          <div class="detail-field"><span>Request Type</span><strong>${escapeHtml(req.request_type||'')}</strong></div>
          <div class="detail-field"><span>Category</span><strong>${escapeHtml(req.category||'')}</strong></div>
          <div class="detail-field"><span>Fee</span><strong>₱${Number(req.fee||0).toFixed(2)}</strong></div>
        </div>
      </section>
      <section class="review-section dues-review-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">₱</span><div><h4>Monthly Dues Status</h4></div></div>
        <div class="detail-grid four-up">
          <div class="detail-field"><span>Status</span><strong>${req.dues && req.dues.unpaid_months > 0 ? 'Outstanding Dues' : 'Clear'}</strong></div>
          <div class="detail-field"><span>Outstanding Months</span><strong>${Number(req.dues?.unpaid_months || 0)}</strong></div>
          <div class="detail-field"><span>Outstanding Balance</span><strong>₱${Number(req.dues?.outstanding_balance || 0).toFixed(2)}</strong></div>
          <div class="detail-field"><span>Unpaid Periods</span><strong>${req.dues?.unpaid_periods?.length ? req.dues.unpaid_periods.map(escapeHtml).join(', ') : 'None'}</strong></div>
        </div>
      </section>
      <section class="review-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">≡</span><div><h4>Request Details</h4><p>Information submitted with this request</p></div></div>
        <div class="request-detail-list">${detailEntries.length ? detailEntries.map(([k,v])=>`<div class="detail-row"><span>${escapeHtml(humanizeKey(k))}</span><div>${renderDetailValue(v)}</div></div>`).join('') : '<div class="empty-review-state">No additional request details were provided.</div>'}</div>
      </section>
      <section class="review-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">✎</span><div><h4>Officer Remarks</h4><p>Current remarks associated with the request</p></div></div>
        <div class="remarks-display">${req.remarks ? escapeHtml(req.remarks) : '<span class="detail-empty">No officer remarks yet.</span>'}</div>
      </section>
      <section class="review-section review-resource-section">
        <div class="section-heading-row"><span class="section-icon" aria-hidden="true">↧</span><div><h4>Files & Documents</h4><p>Supporting file and generated request document</p></div></div>
        <div class="resource-actions">${attachment}${pdf}</div>
      </section>`;
}

const SECRETARY_FIRST_REQUEST_TYPES = new Set([
    'Certificate of Improvement',
    'Proof of Residency',
    'Move-in Gate Pass',
    'Move-out Gate Pass',
    'Certificate of Membership'
]);
const TREASURER_FIRST_REQUEST_TYPES = new Set(['Gate Pass']);
const SHARED_INITIAL_CHECK_REQUEST_TYPES = new Set([
    'Vehicle Sticker Application',
    'Renters/Tenants Information Form'
]);

function canCurrentRoleInitialCheck(req){
    if(!req) return false;
    if(CURRENT_ROLE==='Admin') return true;
    const type=req.request_type || '';
    if(SECRETARY_FIRST_REQUEST_TYPES.has(type)) return CURRENT_ROLE==='Secretary';
    if(TREASURER_FIRST_REQUEST_TYPES.has(type)) return CURRENT_ROLE==='Treasurer';
    if(SHARED_INITIAL_CHECK_REQUEST_TYPES.has(type)){
        if(!['Secretary','Treasurer'].includes(CURRENT_ROLE)) return false;
        if(['Secretary','Treasurer'].includes(req.assigned_officer)) return req.assigned_officer===CURRENT_ROLE;
        return true;
    }
    return CURRENT_ROLE==='Secretary';
}

function configureSecretaryActions(req){
    const correctionBtn=document.getElementById('returnCorrectionBtn');
    const checkedBtn=document.getElementById('markCheckedBtn');
    const hint=document.getElementById('checkActionHint');
    const permitted=canCurrentRoleInitialCheck(req);
    const actionable=permitted && ['Submitted','Under Review'].includes(req.status);
    if (correctionBtn) correctionBtn.hidden=!actionable;
    if (checkedBtn) checkedBtn.hidden=!actionable;
    if (hint) {
        if(actionable){
            const checker=CURRENT_ROLE==='Treasurer' ? 'Treasurer' : 'Secretary';
            hint.textContent=`${checker} checking: return for correction with remarks, or mark the request as checked and forward it for Executive approval.`;
        } else if(req.status==='For Correction') {
            hint.textContent='This request is waiting for the homeowner to submit the required correction.';
        } else if(!permitted) {
            hint.textContent=`${CURRENT_ROLE} is not the authorized initial checker for this request type.`;
        } else {
            hint.textContent='No checking action is available for the current request status.';
        }
    }
}

function buildPreviewActionArea(req){
    const close=`<button type="button" class="btn btn-secondary" onclick="closeModal('requestPreviewModal')">Close</button>`;
    const id=encodeURIComponent(req.id);

    if (['President','Vice President','Board Director'].includes(CURRENT_ROLE) && req.status==='Pending Executive Approval') {
        return `<div class="footer-context"><span class="footer-label">Executive Decision</span><span class="footer-hint">Review all information before recording the decision.</span></div>
        <div class="preview-workflow-form president-preview-form">
            ${close}
            <button type="button" class="btn btn-danger" onclick="closeModal('requestPreviewModal');openExecutiveReject('${req.id}')">Reject</button>
            <form action="/officer/president_action/${id}" method="POST" class="inline-form" onsubmit="return submitPreviewAction(event, 'Approve this request?')"><button type="submit" name="action" value="approve" class="btn btn-success" ${req.dues && req.dues.unpaid_months > 0 ? 'disabled title="Approval blocked: homeowner has outstanding monthly dues"' : ''}>Approve</button></form>
        </div>`;
    }

    if ((CURRENT_ROLE==='Treasurer' || CURRENT_ROLE==='Admin') && req.status==='Approved' && req.payment_status==='Unpaid') {
        return `<div class="footer-context"><span class="footer-label">Payment Action</span><span class="footer-hint">Payment can only be recorded after the request has been approved.</span></div>
        <form class="preview-workflow-form" action="/officer/update_payment/${id}" method="POST" onsubmit="return submitPreviewAction(event, 'Confirm this payment has been received and coordinated by the Treasurer?')">
            ${close}
            <button type="submit" class="btn btn-success">Mark as Paid</button>
        </form>`;
    }

    return `<div class="footer-context"><span class="footer-label">Request Status</span><span class="footer-hint">No workflow action is available for this role and status.</span></div><div class="footer-actions">${close}</div>`;
}

function openCheckModal(reqId){
    const details=document.getElementById('modalReqDetails');
    const form=document.getElementById('checkForm');
    const req=typeof ALL_REQUESTS!=='undefined' ? ALL_REQUESTS.find(r=>r.id===reqId) : null;
    if (!req) return;
    form.dataset.submitting='false';
    form.querySelectorAll('button[type="submit"]').forEach(btn=>{btn.disabled=false;if(btn.dataset.originalText){btn.textContent=btn.dataset.originalText;delete btn.dataset.originalText;}});
    document.getElementById('modalReqId').textContent=reqId;
    document.getElementById('modalRequestTitle').textContent=req.request_type || 'Request Details';
    document.getElementById('checkFormRemarks').value='';
    form.action=`/officer/check_request/${encodeURIComponent(reqId)}`;
    details.innerHTML=buildRequestReviewHTML(req);
    configureSecretaryActions(req);
    openModal('checkModal');
}

function openRequestPreview(reqId){
    const req=typeof ALL_REQUESTS!=='undefined' ? ALL_REQUESTS.find(r=>r.id===reqId) : null;
    if (!req) return;
    document.getElementById('previewReqId').textContent=reqId;
    document.getElementById('previewRequestTitle').textContent=req.request_type || 'Request Details';
    document.getElementById('previewReqDetails').innerHTML=buildRequestReviewHTML(req);
    document.getElementById('previewActionArea').innerHTML=buildPreviewActionArea(req);
    openModal('requestPreviewModal');
}



function initSystemFeedback(){
    (window.SERVER_FLASH_MESSAGES || []).forEach(item=>showToast(item.message,item.category==='success'?'success':item.category==='error'?'error':item.category==='warning'?'warning':'info'));
    document.getElementById('systemConfirmCancel')?.addEventListener('click',()=>closeSystemConfirm(false));
    document.getElementById('systemConfirmButton')?.addEventListener('click',confirmSystemAction);
    document.getElementById('systemConfirmModal')?.addEventListener('click',e=>{if(e.target===e.currentTarget) closeSystemConfirm(false);});
    document.addEventListener('keydown',e=>{if(e.key==='Escape' && document.getElementById('systemConfirmModal')?.classList.contains('show')){e.preventDefault();closeSystemConfirm(false);}});
    document.querySelectorAll('form[data-system-confirm]').forEach(form=>form.addEventListener('submit',async e=>{
        if(form.dataset.confirmed==='true') return;
        e.preventDefault();
        const submitter=e.submitter;
        const ok=await showConfirmModal({title:form.dataset.confirmTitle||'Confirm Action',message:form.dataset.systemConfirm,confirmText:form.dataset.confirmText||submitter?.textContent?.trim()||'Confirm',type:form.dataset.confirmType||'primary'});
        if(!ok) return;
        mirrorSubmitter(form,submitter);
        form.dataset.confirmed='true';
        form.submit();
    }));
}
document.addEventListener('DOMContentLoaded',initSystemFeedback);

// Lightweight role-aware live metrics. Keeps the existing Flask/MySQL architecture.
async function refreshLiveMetrics(){
  try{
    const res=await fetch('/api/live-metrics',{headers:{'Accept':'application/json'},cache:'no-store'});
    if(!res.ok)return; const data=await res.json(); if(data.status!=='success')return;
    document.querySelectorAll('[data-metric]').forEach(el=>{
      const key=el.dataset.metric; if(!(key in data.metrics))return;
      const next=el.dataset.currency==='true' ? `₱${Number(data.metrics[key]||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}` : String(data.metrics[key]);
      if(el.textContent.trim()!==next){el.textContent=next;el.classList.remove('metric-updated');void el.offsetWidth;el.classList.add('metric-updated');}
    });
  }catch(e){console.debug('Live metrics unavailable',e);}
}
refreshLiveMetrics(); setInterval(refreshLiveMetrics,10000);

function toggleAccountMenu(btn){const menu=btn.parentElement.querySelector('.account-dropdown');const opening=menu.hasAttribute('hidden');document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''));if(opening){menu.removeAttribute('hidden');btn.setAttribute('aria-expanded','true')}else{btn.setAttribute('aria-expanded','false')}}
function openAccountProfile(){document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''));openModal('accountProfileModal')}
document.addEventListener('click',e=>{if(!e.target.closest('.account-menu-wrap'))document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''))});

document.addEventListener('click', (event) => {
  const jump=event.target.closest('[data-tab-jump]'); if(!jump)return;
  const target=jump.dataset.tabJump; const nav=document.querySelector(`.sidebar .nav-item[data-tab="${target}"]`);
  if(nav){nav.click(); window.scrollTo({top:0,behavior:'smooth'});}
});

async function settleMonthlyDues(){
    const select=document.getElementById('duesClearHomeowner');
    const userId=select ? select.value : '';
    if(!userId){ showToast('Please select a homeowner first.','error'); return; }
    if(!window.confirm('Confirm that this homeowner has settled all currently outstanding monthly dues?')) return;
    try{
        const res=await fetch('/api/treasurer/settle-dues',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId})});
        const data=await res.json();
        if(!res.ok || data.status!=='success'){ showToast(data.message || 'Unable to update monthly dues.','error'); return; }
        showToast(data.message,'success');
        setTimeout(()=>window.location.reload(),700);
    }catch(err){ showToast('Connection error while updating monthly dues.','error'); }
}

function openExecutiveReject(reqId){
    const modal=document.getElementById('executiveRejectModal');
    const form=document.getElementById('executiveRejectForm');
    const req=typeof ALL_REQUESTS!=='undefined' ? ALL_REQUESTS.find(r=>r.id===reqId) : null;
    if(!modal||!form||!req){showToast('Unable to open the rejection form.','error');return;}
    form.action='/officer/president_action/'+encodeURIComponent(reqId);
    form.querySelectorAll('input[name="rejection_reason"]').forEach(r=>{r.checked=false;});
    const details=document.getElementById('executiveRejectDetails'); if(details){details.value='';details.required=false;}
    const group=document.getElementById('executiveRejectDetailsGroup'); if(group)group.hidden=true;
    const error=document.getElementById('executiveRejectError'); if(error){error.hidden=true;error.textContent='';}
    document.getElementById('executiveRejectReqId').textContent=req.id;
    document.getElementById('executiveRejectHomeowner').textContent=req.homeowner||'—';
    document.getElementById('executiveRejectType').textContent=req.request_type||'—';
    openModal('executiveRejectModal');
}
function toggleExecutiveRejectDetails(){
    const selected=document.querySelector('#executiveRejectForm input[name="rejection_reason"]:checked');
    const group=document.getElementById('executiveRejectDetailsGroup');
    const details=document.getElementById('executiveRejectDetails');
    const other=selected?.value==='Other';
    if(group)group.hidden=!other; if(details)details.required=other;
    const error=document.getElementById('executiveRejectError'); if(error){error.hidden=true;error.textContent='';}
}
function initExecutiveRejectForm(){
    const form=document.getElementById('executiveRejectForm'); if(!form)return;
    form.querySelectorAll('input[name="rejection_reason"]').forEach(r=>r.addEventListener('change',toggleExecutiveRejectDetails));
    form.addEventListener('submit',e=>{
        const selected=form.querySelector('input[name="rejection_reason"]:checked');
        const details=document.getElementById('executiveRejectDetails');
        const error=document.getElementById('executiveRejectError');
        let message='';
        if(!selected) message='Please select a rejection reason.';
        else if(selected.value==='Other' && !details.value.trim()) message='Please enter the reason for rejection.';
        if(message){e.preventDefault();error.textContent=message;error.hidden=false;return;}
        error.hidden=true;
    });
}
document.addEventListener('DOMContentLoaded',initExecutiveRejectForm);
window.openExecutiveReject=openExecutiveReject;window.toggleExecutiveRejectDetails=toggleExecutiveRejectDetails;
