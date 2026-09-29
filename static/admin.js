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
        const collapsed = document.body.classList.contains('sidebar-collapsed');
        if (!desktopSidebarToggle) return;
        desktopSidebarToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        desktopSidebarToggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        desktopSidebarToggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
        const icon = desktopSidebarToggle.querySelector('i');
        if (icon) icon.className = collapsed ? 'fa-solid fa-angles-right' : 'fa-solid fa-angles-left';
    };
    if (desktopSidebarToggle) desktopSidebarToggle.addEventListener('click', () => {
        if (window.innerWidth < 1024) return;
        const collapsed = document.body.classList.toggle('sidebar-collapsed');
        sessionStorage.setItem('nfhSidebarCollapsed', collapsed ? '1' : '0');
        syncDesktopToggle();
    });
    if (sidebarToggle) sidebarToggle.addEventListener('click', () => setSidebarOpen(!sidebar.classList.contains('open')));
    if (window.innerWidth >= 1024 && sessionStorage.getItem('nfhSidebarCollapsed') === '1') document.body.classList.add('sidebar-collapsed');
    syncDesktopToggle();
    if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && window.innerWidth <= 992 && sidebar?.classList.contains('open')) {
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
            if (window.innerWidth <= 992) setSidebarOpen(false);
        });
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth >= 1024) setSidebarOpen(false);
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

function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('show');
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('show');
}

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


// Professional in-system confirmations and toast feedback for Admin actions.
let adminConfirmResolve=null, adminConfirmTrigger=null;
function showToast(message,type='info',timeout=4200){const c=document.getElementById('toastContainer');if(!c||!message)return;const t=document.createElement('div');t.className=`system-toast toast-${type}`;const icon={success:'✓',error:'!',warning:'!',info:'i'}[type]||'i';t.innerHTML=`<span class="toast-icon">${icon}</span><div class="toast-message"></div><button class="toast-close" type="button" aria-label="Dismiss">×</button>`;t.querySelector('.toast-message').textContent=message;t.querySelector('.toast-close').onclick=()=>dismissToast(t);c.appendChild(t);requestAnimationFrame(()=>t.classList.add('show'));setTimeout(()=>dismissToast(t),timeout)}
function dismissToast(t){if(!t||t.dataset.closing)return;t.dataset.closing='1';t.classList.remove('show');setTimeout(()=>t.remove(),220)}
function showAdminConfirm({title,message,confirmText='Confirm',type='primary',context=[]}){const m=document.getElementById('systemConfirmModal');if(!m)return Promise.resolve(true);adminConfirmTrigger=document.activeElement;document.getElementById('systemConfirmTitle').textContent=title;document.getElementById('systemConfirmMessage').textContent=message;const x=document.getElementById('systemConfirmContext');x.innerHTML='';context.forEach(i=>{if(!i?.value)return;const r=document.createElement('div');r.className='confirm-context-row';r.innerHTML='<span></span><strong></strong>';r.children[0].textContent=i.label;r.children[1].textContent=i.value;x.appendChild(r)});x.hidden=!x.children.length;const b=document.getElementById('systemConfirmButton');b.textContent=confirmText;b.className=`btn confirm-primary confirm-${type}`;m.classList.add('show');setTimeout(()=>b.focus(),0);return new Promise(res=>adminConfirmResolve=res)}
function closeAdminConfirm(result=false){document.getElementById('systemConfirmModal')?.classList.remove('show');const r=adminConfirmResolve;adminConfirmResolve=null;if(r)r(result);setTimeout(()=>adminConfirmTrigger?.focus?.(),0)}
function initAdminFeedback(){(window.SERVER_FLASH_MESSAGES||[]).forEach(i=>showToast(i.message,i.category==='success'?'success':i.category==='error'?'error':i.category==='warning'?'warning':'info'));document.getElementById('systemConfirmCancel')?.addEventListener('click',()=>closeAdminConfirm(false));document.getElementById('systemConfirmButton')?.addEventListener('click',()=>closeAdminConfirm(true));document.getElementById('systemConfirmModal')?.addEventListener('click',e=>{if(e.target===e.currentTarget)closeAdminConfirm(false)});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('systemConfirmModal')?.classList.contains('show'))closeAdminConfirm(false)});document.querySelectorAll('form[data-system-confirm]').forEach(form=>form.addEventListener('submit',async e=>{if(form.dataset.confirmed==='true')return;e.preventDefault();const submitter=e.submitter;const ok=await showAdminConfirm({title:form.dataset.confirmTitle||'Confirm Action',message:form.dataset.systemConfirm,confirmText:form.dataset.confirmText||submitter?.textContent?.trim()||'Confirm',type:form.dataset.confirmType||'primary',context:[{label:form.dataset.contextLabel||'',value:form.dataset.contextValue||''}]});if(!ok)return;form.dataset.confirmed='true';form.submit()}));}
document.addEventListener('DOMContentLoaded',initAdminFeedback);


document.addEventListener('click', (event) => {
    const jump = event.target.closest('[data-tab-jump]');
    if (!jump) return;
    event.preventDefault();
    const target = jump.getAttribute('data-tab-jump');
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.getElementById(target)?.classList.add('active');
    document.querySelectorAll('.sidebar .nav-item[data-tab]').forEach(el => {
        const active = el.dataset.tab === target; el.classList.toggle('active', active);
        if (active && pageTitle) pageTitle.textContent = el.querySelector('span')?.textContent || 'Administrator';
    });
    window.scrollTo({top:0, behavior:'smooth'});
});

function toggleAccountMenu(btn){const menu=btn.parentElement.querySelector('.account-dropdown');const opening=menu.hasAttribute('hidden');document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''));if(opening){menu.removeAttribute('hidden');btn.setAttribute('aria-expanded','true')}else{btn.setAttribute('aria-expanded','false')}}
function openAccountProfile(){document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''));openModal('accountProfileModal')}
document.addEventListener('click',e=>{if(!e.target.closest('.account-menu-wrap'))document.querySelectorAll('.account-dropdown').forEach(m=>m.setAttribute('hidden',''))});


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
