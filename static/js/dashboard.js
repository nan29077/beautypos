/**
 * ADPAY Dashboard — Enhanced Role-based SPA
 */

let currentUser = null;
let currentPage = 'home';
let adFeatureFlags = { ad_order_mgmt_enabled: false, ad_blog_enabled: false, ad_place_traffic_enabled: false, ad_shorts_enabled: false };
let adPricing = {
    blog_unit_price: 0,
    place_traffic_unit_price: 0,
    shorts_distribution_unit_price: 0,
    shorts_duration_prices: {},
};
const roleMobileQuery = window.matchMedia('(max-width: 767.98px)');
let mobileEnhanceObserver = null;
let mobileEnhanceScheduled = false;
let adminMetricTargets = [];

// ─── 저장·실패 알림 (토스트) ────────────────────────────────
// 인라인 alert 박스는 카드 안쪽에 있어서, 화면 아래쪽 버튼을 눌렀을 때
// 결과가 스크롤 밖에 뜨는 일이 있었다. 눈에 띄는 알림은 이 토스트가 맡는다.
function showToast(message, ok = true) {
    let host = document.getElementById('adpayToastHost');
    if (!host) {
        host = document.createElement('div');
        host.id = 'adpayToastHost';
        host.setAttribute('aria-live', 'polite');
        host.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:2050;'
            + 'display:flex;flex-direction:column;gap:.5rem;max-width:min(92vw,26rem);pointer-events:none';
        document.body.appendChild(host);
    }
    const el = document.createElement('div');
    el.className = `alert alert-${ok ? 'success' : 'danger'} shadow d-flex align-items-start gap-2 py-2 px-3 mb-0`;
    el.style.cssText = 'pointer-events:auto;opacity:0;transform:translateY(-.4rem);transition:opacity .25s,transform .25s';
    el.innerHTML = `<i class="fas fa-${ok ? 'circle-check' : 'circle-exclamation'} mt-1"></i>`
        + `<div class="small flex-grow-1">${escapeHtml(String(message == null ? '' : message))}</div>`;
    el.onclick = () => el.remove();
    host.appendChild(el);
    requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'none'; });
    // 실패는 읽을 시간이 더 필요하다.
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(-.4rem)';
        setTimeout(() => el.remove(), 300);
    }, ok ? 2800 : 6000);
}

// 저장 버튼이 눌린 동안 스피너를 보여준다. 되돌리는 함수를 돌려준다.
function busyButton(id, label = '저장 중...') {
    const btn = document.getElementById(id);
    if (!btn) return () => {};
    const original = btn.innerHTML;
    const wasDisabled = btn.disabled;
    btn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i>${escapeHtml(label)}`;
    return () => { btn.disabled = wasDisabled; btn.innerHTML = original; };
}

function adpayLoadingMarkup(message = '') {
    return `<div class="adpay-loading" role="status" aria-live="polite">
        <div>
            <div class="adpay-loading-logo">
                <strong><span>AD</span>PAY</strong>
                <small>결제와 마케팅을 하나로</small>
            </div>
            ${message ? `<p class="adpay-loading-message">${escapeHtml(message)}</p>` : ''}
        </div>
    </div>`;
}

function finishAppBoot() {
    document.body.classList.remove('app-booting');
    document.getElementById('appBootLoader')?.remove();
}

const mobilePageMeta = {
    home: ['대시보드', 'fas fa-home'],
    'admin-merchants': ['가맹점 리스트', 'fas fa-store'],
    'admin-pg': ['PG 설정', 'fas fa-network-wired'],
    'admin-terminals': ['단말기 관리', 'fas fa-tablet-alt'],
    'admin-transactions': ['전체 결제 내역', 'fas fa-receipt'],
    'admin-ongi': ['온기 QR 결제', 'fas fa-qrcode'],
    'admin-settlements': ['정산 관리', 'fas fa-calculator'],
    'admin-fee-settings': ['수수료 기본 설정', 'fas fa-sliders-h'],
    'admin-fee-policies': ['가맹점별 수수료', 'fas fa-percentage'],
    'admin-commission-visibility': ['수수료 표시 설정', 'fas fa-eye'],
    'admin-payouts': ['출금요청 관리', 'fas fa-money-bill-wave'],
    'admin-adorders': ['광고주문 관리', 'fas fa-bullhorn'],
    'admin-metrics': ['광고 분석 관리', 'fas fa-chart-bar'],
    'admin-ad-executions': ['광고 실행 현황', 'fas fa-tasks'],
    'admin-plans': ['플랜 관리', 'fas fa-layer-group'],
    'admin-sales-managers': ['영업관리자 관리', 'fas fa-user-tie'],
    'admin-sales-assign': ['영업관리자 연결', 'fas fa-handshake'],
    'admin-users': ['사용자 목록', 'fas fa-users-cog'],
    'admin-ai-settings': ['AI 설정', 'fas fa-robot'],
    'admin-rewardpop': ['리워드팝 연동', 'fas fa-plug'],
    'admin-ad-keywords': ['광고 키워드 승인', 'fas fa-key'],
    'admin-ad-dispatch': ['광고 자동 집행', 'fas fa-paper-plane'],
    'admin-ad-credits': ['광고비 크레딧', 'fas fa-wallet'],
    'sales-merchants': ['담당 가맹점', 'fas fa-store'],
    'sales-commission': ['커미션 현황', 'fas fa-coins'],
    'sales-payouts': ['출금요청', 'fas fa-money-bill-wave'],
    'sales-payout-history': ['출금내역', 'fas fa-history'],
    'owner-transactions': ['결제 내역', 'fas fa-receipt'],
    'owner-staff': ['직원 관리', 'fas fa-users'],
    'owner-staff-sales': ['직원별 매출', 'fas fa-chart-bar'],
    'owner-settlement': ['정산 분배', 'fas fa-coins'],
    'owner-settlements': ['정산 내역', 'fas fa-file-invoice-dollar'],
    'owner-payouts': ['출금 요청', 'fas fa-money-bill-wave'],
    'owner-daily-summary': ['일별 결제내역', 'fas fa-calendar-day'],
    'owner-receipt-review': ['영수증 리뷰', 'fas fa-qrcode'],
    'owner-analysis': ['광고 분석', 'fas fa-chart-line'],
    'owner-adorders': ['광고 주문 내역', 'fas fa-bullhorn'],
    'owner-adorder-new': ['새 광고 주문', 'fas fa-plus-circle'],
    'owner-ad-settings': ['광고 설정', 'fas fa-sliders'],
    'owner-ad-credit': ['광고비', 'fas fa-wallet'],
    crm: ['매장 관리', 'fas fa-user-friends'],
    'owner-info': ['매장 정보', 'fas fa-store'],
    'designer-transactions': ['결제 내역', 'fas fa-receipt'],
    'designer-monthly': ['월별 통계', 'fas fa-calendar-alt'],
    'designer-settlement': ['정산 분배', 'fas fa-coins'],
    'designer-profile': ['내 정보', 'fas fa-id-badge']
};

/** 뷰티 업종 여부. business_type이 없는 구계정은 beauty로 간주. */
function isBeautyBusiness() {
    if (!currentUser) return true;
    const bt = currentUser.business_type;
    return !bt || bt === 'beauty';
}

function isPageAllowedForCurrentRole(page) {
    if (!currentUser || page === 'home') return page === 'home';
    if (currentUser.role === 'admin') return page.startsWith('admin-');
    if (currentUser.role === 'sales') return page.startsWith('sales-');
    if (currentUser.role === 'owner') return ownerMobilePages().includes(page);
    if (currentUser.role === 'designer') {
        const allowed = ['designer-transactions', 'designer-monthly', 'designer-settlement', 'designer-profile'];
        if (isBeautyBusiness()) allowed.push('crm');
        return allowed.includes(page);
    }
    return false;
}

// ─── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const token = getToken();
    if (!token) { window.location.href = '/static/login.html'; return; }
    try {
        currentUser = await apiGet('/api/auth/me');
        if (!currentUser) return;
        localStorage.setItem('user', JSON.stringify(currentUser));
    } catch {
        logout(); return;
    }
    // 사장님인 경우 매장 정보를 미리 로드하여 이름 표기에 사용
    if (currentUser.role === 'owner') {
        try {
            ownerMerchantInfo = await apiGet('/api/owner/merchant-info');
        } catch(e) { ownerMerchantInfo = null; }
    }
    // 광고 기능 플래그 로드 (사장님 계정에서 사이드바 메뉴 표시 제어)
    if (currentUser.role === 'owner') {
        try {
            adFeatureFlags = await apiGet('/api/feature-flags');
        } catch(e) { adFeatureFlags = { ad_order_mgmt_enabled: false, ad_blog_enabled: false, ad_place_traffic_enabled: false, ad_shorts_enabled: false }; }
    }

    const displayName = (currentUser.role === 'owner' && ownerMerchantInfo)
        ? ownerDisplayName(currentUser, ownerMerchantInfo.name)
        : currentUser.name;
    document.getElementById('sidebarUserName').textContent = displayName;
    const roleEl = document.getElementById('sidebarRole');
    roleEl.textContent = roleLabel(currentUser.role);
    roleEl.className = `user-role role-${currentUser.role}`;
    // top-bar removed; safely skip topBarUser/topBarAvatar updates
    const topBarUserEl = document.getElementById('topBarUser');
    if (topBarUserEl) topBarUserEl.textContent = `${displayName} (${roleLabel(currentUser.role)})`;
    const topBarAvatarEl = document.getElementById('topBarAvatar');
    if (topBarAvatarEl) topBarAvatarEl.textContent = displayName.charAt(0) === '*' ? displayName.charAt(3) : displayName.charAt(0);

    buildSidebar();
    setupRoleMobileUI();
    const requestedPage = location.hash.replace(/^#/, '');
    navigate(isPageAllowedForCurrentRole(requestedPage) ? requestedPage : 'home', { replaceHistory: true });
    requestAnimationFrame(finishAppBoot);
});

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

// URL 을 HTML 속성(src/href/onclick)에 안전하게 넣기 위한 헬퍼.
// http/https/상대경로/data:image 스킴만 허용하고 (javascript: 등 차단),
// 따옴표류 문자를 제거해 속성/인라인 JS 문자열 탈출을 막는다.
function safeUrl(value) {
    const url = String(value ?? '').trim().replace(/['"\\<>`]/g, '');
    if (/^(https?:\/\/|\/(?!\/)|data:image\/)/i.test(url)) return escapeHtml(url);
    return '';
}

// 인라인 이벤트 핸들러(onclick="fn('...')") 의 작은따옴표 문자열 안에 값을 넣기 위한 헬퍼.
// HTML 속성값은 JS 파싱 전에 엔티티가 먼저 복원되므로, JS 이스케이프를 먼저 하고
// 그 결과를 HTML 이스케이프해야 속성/문자열 양쪽을 모두 탈출할 수 없다.
function escapeJsAttr(value) {
    return escapeHtml(
        String(value ?? '')
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/\r?\n/g, ' ')
    );
}

function roleLabel(r) {
    return {admin:'최고관리자', sales:'영업관리자', owner:'사장님', designer:'직원'}[r] || r;
}

/**
 * 사장님 역할의 경우 매장명으로 표기 (풀네임, 마스킹 없음)
 */
function ownerDisplayName(user, merchantName) {
    if (user.role === 'owner' && merchantName) {
        return merchantName + '님';
    }
    return user.name;
}

let ownerMerchantInfo = null; // 사장님의 매장 정보 캐시

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.toggle('show');
    const open = sidebar.classList.contains('show');
    if (overlay) overlay.classList.toggle('show', open);
    // 사이드바가 열려 있는 동안 뒤 화면이 같이 스크롤되지 않게 한다.
    document.body.classList.toggle('sidebar-open', open);
}

function resetFormModalFooter(showSave = true) {
    const footer = document.getElementById('formModalFooter');
    if (!footer) return null;
    footer.innerHTML = `
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>
        <button type="button" class="btn btn-primary" id="formModalSave">저장</button>`;
    const save = document.getElementById('formModalSave');
    save.style.display = showSave ? '' : 'none';
    return save;
}

function showChangePasswordModal() {
    // 모바일 메뉴 시트에서 열었을 수 있으므로 먼저 닫는다.
    if (typeof closeMobileMenu === 'function') closeMobileMenu();
    document.getElementById('formModalTitle').textContent = '비밀번호 변경';
    document.getElementById('formModalBody').innerHTML = `
        <div class="mb-3">
            <label class="form-label">현재 비밀번호</label>
            <input type="password" class="form-control" id="pwCurrent" autocomplete="current-password">
        </div>
        <div class="mb-3">
            <label class="form-label">새 비밀번호</label>
            <input type="password" class="form-control" id="pwNew" placeholder="6자 이상" autocomplete="new-password">
        </div>
        <div class="mb-0">
            <label class="form-label">새 비밀번호 확인</label>
            <input type="password" class="form-control" id="pwNewConfirm" autocomplete="new-password">
        </div>`;
    const save = resetFormModalFooter();
    save.textContent = '변경';
    save.onclick = async () => {
        const current = document.getElementById('pwCurrent').value;
        const next = document.getElementById('pwNew').value;
        const nextConfirm = document.getElementById('pwNewConfirm').value;
        if (!current || !next) { alert('현재 비밀번호와 새 비밀번호를 입력하세요'); return; }
        if (next.length < 6) { alert('새 비밀번호는 6자 이상이어야 합니다'); return; }
        if (next !== nextConfirm) { alert('새 비밀번호가 서로 일치하지 않습니다'); return; }
        try {
            await apiPost('/api/auth/change-password', { current_password: current, new_password: next });
            bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
            alert('비밀번호가 변경되었습니다. 다음 로그인부터 새 비밀번호를 사용하세요.');
        } catch (e) {
            alert(e.message);
        }
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

function adStatusOptions(allowedStatuses, includePlaceholder = true) {
    const labels = {
        requested: '요청됨',
        reviewing: '검토중',
        running: '집행중',
        done: '완료',
        rejected: '반려'
    };
    const allowed = allowedStatuses || [];
    return `${includePlaceholder ? '<option value="" selected disabled>다음 상태</option>' : ''}${
        allowed.map(status => `<option value="${status}">${labels[status] || status}</option>`).join('')
    }`;
}

/** 광고 주문 유형(blog / place_traffic / shorts)의 배지 색과 표시명. */
function adOrderTypeMeta(type) {
    const map = {
        blog: { label: '블로그', color: 'info' },
        place_traffic: { label: '플레이스', color: 'secondary' },
        shorts: { label: '쇼츠', color: 'danger' },
    };
    return map[type] || { label: type || '-', color: 'secondary' };
}

function adOrderTypeBadge(type) {
    const meta = adOrderTypeMeta(type);
    return `<span class="badge bg-${meta.color}">${meta.label}</span>`;
}

/** 뷰포트가 모바일 폭인지 (역할과 무관). */
function isMobileViewport() {
    const forcedMobile = new URLSearchParams(location.search).get('view') === 'mobile';
    return forcedMobile || roleMobileQuery.matches;
}

/** 사장님/직원 전용 모바일 앱 셸(하단 탭·시트)을 쓰는 상태인지. */
function isRoleMobile() {
    if (!currentUser || !['owner', 'designer'].includes(currentUser.role)) return false;
    return isMobileViewport();
}

/** 최고관리자/영업관리자: 사이드바(햄버거) 유지 + 페이지 내용만 모바일 최적화. */
function isAdminMobile() {
    if (!currentUser || !['admin', 'sales'].includes(currentUser.role)) return false;
    return isMobileViewport();
}

function ownerMobilePages() {
    const needsStaff = ownerMerchantInfo ? ownerMerchantInfo.needs_staff_management : true;
    const pages = ['home', 'owner-transactions'];
    if (needsStaff) {
        pages.push('owner-staff', 'owner-staff-sales', 'owner-settlement');
    }
    pages.push('owner-settlements', 'owner-payouts',
               'owner-receipt-review', 'owner-analysis', 'owner-ad-settings',
               'owner-ad-credit');
    if (adFeatureFlags.ad_order_mgmt_enabled) {
        pages.push('owner-adorders', 'owner-adorder-new');
    }
    if (isBeautyBusiness()) pages.push('crm');
    pages.push('owner-info');
    return pages;
}

function roleMobilePages() {
    if (currentUser.role === 'owner') return ownerMobilePages();
    const designerPages = ['home', 'designer-transactions', 'designer-monthly', 'designer-settlement', 'designer-profile'];
    if (isBeautyBusiness()) designerPages.splice(designerPages.indexOf('designer-profile'), 0, 'crm');
    return designerPages;
}

function setupRoleMobileUI() {
    document.body.classList.toggle('role-mobile-ui', isRoleMobile());
    document.body.classList.toggle('admin-mobile-ui', isAdminMobile());
    document.body.dataset.role = currentUser.role;
    if (!isRoleMobile() && !isAdminMobile()) {
        mobileEnhanceObserver?.disconnect();
        mobileEnhanceObserver = null;
        return;
    }

    if (isRoleMobile()) {
        const roleLabelEl = document.getElementById('mobileRoleLabel');
        if (roleLabelEl) {
            const merchantName = currentUser.role === 'owner' && ownerMerchantInfo?.name;
            roleLabelEl.textContent = merchantName || (currentUser.role === 'designer' ? `${currentUser.name} 직원` : 'ADPAY');
        }
        buildMobileNavigation();
    }
    if (isAdminMobile()) updateAdminMobileHeader(currentPage);
    // 표를 카드형으로 바꾸는 후처리는 관리자·영업 화면에도 동일하게 적용한다.
    observeRoleMobileContent();
}

function observeRoleMobileContent() {
    const container = document.getElementById('pageContent');
    mobileEnhanceObserver?.disconnect();
    mobileEnhanceObserver = new MutationObserver(() => {
        if (mobileEnhanceScheduled) return;
        mobileEnhanceScheduled = true;
        // requestAnimationFrame 은 탭이 화면에 보이지 않으면 멈추므로,
        // 백그라운드에서 그려진 표가 카드 전환 없이 남지 않도록 타이머를 쓴다.
        setTimeout(() => {
            mobileEnhanceScheduled = false;
            enhanceRoleMobilePage(container);
        }, 0);
    });
    mobileEnhanceObserver.observe(container, { childList: true, subtree: true });
}

function buildMobileNavigation() {
    if (!isRoleMobile()) return;
    const pages = roleMobilePages();
    const bottomPages = currentUser.role === 'owner'
        ? ['home', 'owner-transactions', pages.includes('owner-staff') ? 'owner-staff' : 'owner-analysis', ...(isBeautyBusiness() ? ['crm'] : ['owner-settlements'])]
        : ['home', 'designer-transactions', 'designer-monthly', ...(isBeautyBusiness() ? ['crm'] : ['designer-profile'])];
    const nav = document.getElementById('mobileBottomNav');
    nav.innerHTML = bottomPages.map(page => {
        const [label, icon] = mobilePageMeta[page];
        return `<button type="button" data-mobile-page="${page}" onclick="navigate('${page}')">
            <i class="${icon}"></i><span>${label}</span>
        </button>`;
    }).join('') + `<button type="button" data-mobile-action="more" onclick="openMobileMenu()">
        <i class="fas fa-ellipsis-h"></i><span>전체</span>
    </button>`;

    const grid = document.getElementById('mobileMenuGrid');
    grid.innerHTML = pages.filter(page => page !== 'home').map(page => {
        const [label, icon] = mobilePageMeta[page];
        return `<button type="button" data-mobile-page="${page}" onclick="navigate('${page}')">
            <span class="role-mobile-menu-icon"><i class="${icon}"></i></span>
            <span>${label}</span>
        </button>`;
    }).join('');
    updateMobileNavigation(currentPage);
}

function openMobileMenu() {
    if (!isRoleMobile()) return;
    const sheet = document.getElementById('mobileMenuSheet');
    sheet.classList.add('show');
    sheet.setAttribute('aria-hidden', 'false');
    document.getElementById('mobileSheetBackdrop').classList.add('show');
    document.body.classList.add('mobile-menu-open');
}

function closeMobileMenu() {
    const sheet = document.getElementById('mobileMenuSheet');
    if (!sheet) return;
    sheet.classList.remove('show');
    sheet.setAttribute('aria-hidden', 'true');
    document.getElementById('mobileSheetBackdrop')?.classList.remove('show');
    document.body.classList.remove('mobile-menu-open');
}

function updateMobileNavigation(page) {
    if (!isRoleMobile()) return;
    const title = mobilePageMeta[page]?.[0] || 'ADPAY';
    const titleEl = document.getElementById('mobilePageTitle');
    if (titleEl) titleEl.textContent = title;
    document.querySelectorAll('[data-mobile-page]').forEach(el => {
        const active = el.dataset.mobilePage === page;
        el.classList.toggle('active', active);
        if (active) el.setAttribute('aria-current', 'page');
        else el.removeAttribute('aria-current');
    });
    const moreButton = document.querySelector('[data-mobile-action="more"]');
    if (moreButton) {
        const primaryPages = [...document.querySelectorAll('#mobileBottomNav [data-mobile-page]')].map(el => el.dataset.mobilePage);
        moreButton.classList.toggle('active', !primaryPages.includes(page));
    }
}

function updateAdminMobileHeader(page) {
    if (!isAdminMobile()) return;
    const roleEl = document.getElementById('adminMobileRoleLabel');
    const titleEl = document.getElementById('adminMobilePageTitle');
    if (roleEl) roleEl.textContent = currentUser.role === 'admin' ? '최고관리자' : '영업관리자';
    if (titleEl) titleEl.textContent = mobilePageMeta[page]?.[0] || '관리자 메뉴';
}

function enhanceRoleMobilePage(container) {
    if (!container || (!isRoleMobile() && !isAdminMobile())) return;
    container.querySelectorAll('.table').forEach(table => {
        if (table.classList.contains('mobile-keep-table')) return;
        const labels = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
        if (!labels.length) return;
        table.classList.add('mobile-card-table');
        table.querySelectorAll('tbody tr').forEach(row => {
            [...row.children].forEach((cell, index) => {
                if (cell.tagName === 'TD') cell.dataset.label = labels[index] || '';
            });
        });
    });
    container.querySelectorAll('.table-responsive').forEach(wrapper => {
        wrapper.setAttribute('tabindex', '0');
        wrapper.setAttribute('role', 'region');
        wrapper.setAttribute('aria-label', '목록');
    });
    enhanceAdminMobilePage(container);
}

function enhanceAdminMobilePage(container) {
    if (!container || !isAdminMobile()) return;
    container.classList.add('admin-mobile-content');

    container.querySelectorAll('.card').forEach(card => card.classList.add('admin-mobile-card'));
    container.querySelectorAll('.card-header').forEach(header => header.classList.add('admin-mobile-card-header'));
    container.querySelectorAll('.nav-tabs, .nav-pills').forEach(nav => nav.classList.add('admin-mobile-tabs'));

    container.querySelectorAll('.row').forEach(row => {
        const directFields = [...row.children].filter(child =>
            child.matches('[class*="col-"]') && child.querySelector('input, select, textarea')
        );
        const directCards = [...row.children].filter(child =>
            child.matches('[class*="col-"]') && child.querySelector(':scope > .card')
        );
        if (directFields.length >= 2) row.classList.add('admin-mobile-filter-grid');
        const summaryCardsOnly = directCards.length >= 2
            && directCards.length === row.children.length
            && directCards.every(child => child.querySelector(':scope > .card.text-center, :scope > .kpi-card'));
        if (summaryCardsOnly) {
            row.classList.add('admin-mobile-summary-grid');
        }
    });

    container.querySelectorAll('.d-flex').forEach(group => {
        const controls = group.querySelectorAll(':scope > .btn, :scope > select, :scope > input');
        if (group.querySelector(':scope > .btn') && controls.length >= 2) {
            group.classList.add('admin-mobile-action-group');
        }
    });

    container.querySelectorAll('.mobile-card-table tbody tr').forEach(row => {
        if (row.dataset.mobileDetailsReady === 'true') return;
        const cells = [...row.children].filter(cell => cell.tagName === 'TD' && !cell.hasAttribute('colspan'));
        cells.forEach(cell => {
            if ((cell.dataset.label || '').replace(/\s+/g, '') === 'ID') {
                cell.classList.add('admin-mobile-id-cell');
            }
        });
        if (cells.length <= 7) {
            row.dataset.mobileDetailsReady = 'true';
            return;
        }

        const detailCells = cells.filter((cell, index) => {
            const hasControl = Boolean(cell.querySelector('button, select, input, textarea'));
            return index >= 5 && !hasControl;
        });
        if (detailCells.length) {
            detailCells.forEach(cell => cell.classList.add('admin-mobile-row-detail'));
            const toggleCell = document.createElement('td');
            toggleCell.className = 'admin-mobile-detail-toggle-cell';
            toggleCell.dataset.label = '';
            toggleCell.innerHTML = `<button type="button" class="admin-mobile-detail-toggle" aria-expanded="false" onclick="toggleAdminMobileRowDetails(this)">
                <span>상세 보기</span><i class="fas fa-chevron-down"></i>
            </button>`;
            row.appendChild(toggleCell);
        }
        row.dataset.mobileDetailsReady = 'true';
    });
}

function toggleAdminMobileRowDetails(button) {
    const row = button.closest('tr');
    if (!row) return;
    const open = row.classList.toggle('admin-mobile-detail-open');
    button.setAttribute('aria-expanded', String(open));
    button.querySelector('span').textContent = open ? '간단히 보기' : '상세 보기';
}

// 모달 내용은 #pageContent 밖에서 그려지므로 pageContent 옵저버가 보지 못한다.
// 모달이 열려 있는 동안만 따로 감시해 표를 카드로 바꾼다. (내용이 열린 뒤 채워지는 모달도 있다)
let mobileModalObserver = null;

document.addEventListener('shown.bs.modal', event => {
    const modal = event.target;
    enhanceRoleMobilePage(modal);
    mobileModalObserver?.disconnect();
    mobileModalObserver = null;
    if (!isRoleMobile() && !isAdminMobile()) return;
    // childList 만 감시한다. enhance 는 속성만 바꾸므로 스스로를 다시 트리거하지 않는다.
    mobileModalObserver = new MutationObserver(() => enhanceRoleMobilePage(modal));
    mobileModalObserver.observe(modal, { childList: true, subtree: true });
});

document.addEventListener('hidden.bs.modal', () => {
    mobileModalObserver?.disconnect();
    mobileModalObserver = null;
});

roleMobileQuery.addEventListener?.('change', () => {
    if (!currentUser) return;
    setupRoleMobileUI();
    enhanceRoleMobilePage(document.getElementById('pageContent'));
});

// 모바일에서 사이드바가 열려 있으면 ESC 로 닫는다.
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (document.getElementById('sidebar')?.classList.contains('show')) toggleSidebar();
});

window.addEventListener('popstate', event => {
    // state 가 없으면 앱 히스토리 밖으로 나간 것 — 로그인 페이지로 빠지지 않도록 막는다.
    if (!event.state) {
        history.pushState({ page: currentPage || 'home' }, '', `#${currentPage || 'home'}`);
        return;
    }
    const page = event.state.page || location.hash.replace(/^#/, '') || 'home';
    if (page !== currentPage && isPageAllowedForCurrentRole(page)) navigate(page, { skipHistory: true });
});

// ─── Enhanced Sidebar ────────────────────────────────────────
function buildSidebar() {
    const nav = document.getElementById('sidebarNav');
    const role = currentUser.role;
    let html = `<a class="nav-link active" href="#" data-page="home"><i class="fas fa-tachometer-alt"></i>대시보드</a>`;

    if (role === 'admin') {
        html += `
        <div class="nav-section"><i class="fas fa-store me-1" style="font-size:.6rem"></i>ADPAY 가맹점</div>
        <a class="nav-link" href="#" data-page="admin-merchants"><i class="fas fa-store"></i>가맹점 리스트</a>
        <a class="nav-link" href="#" data-page="admin-pg"><i class="fas fa-network-wired"></i>PG 설정</a>
        <a class="nav-link" href="#" data-page="admin-terminals"><i class="fas fa-tablet-alt"></i>단말기 관리</a>
        <div class="nav-section"><i class="fas fa-won-sign me-1" style="font-size:.6rem"></i>결제 · 정산</div>
        <a class="nav-link" href="#" data-page="admin-transactions"><i class="fas fa-receipt"></i>전체 결제 내역</a>
        <a class="nav-link" href="#" data-page="admin-ongi"><i class="fas fa-qrcode"></i>온기 QR 결제</a>
        <a class="nav-link" href="#" data-page="admin-settlements"><i class="fas fa-calculator"></i>정산 관리</a>
        <a class="nav-link" href="#" data-page="admin-fee-settings"><i class="fas fa-sliders-h"></i>수수료 기본 설정</a>
        <a class="nav-link" href="#" data-page="admin-fee-policies"><i class="fas fa-percentage"></i>가맹점별 수수료</a>
        <a class="nav-link" href="#" data-page="admin-commission-visibility"><i class="fas fa-eye"></i>수수료 표시 설정</a>
        <a class="nav-link" href="#" data-page="admin-payouts"><i class="fas fa-money-bill-wave"></i>출금요청 관리</a>
        <a class="nav-link" href="#" data-page="admin-ad-credits"><i class="fas fa-wallet"></i>광고비 크레딧</a>
        <div class="nav-section"><i class="fas fa-bullhorn me-1" style="font-size:.6rem"></i>광고 · 마케팅</div>
        <a class="nav-link" href="#" data-page="admin-adorders"><i class="fas fa-bullhorn"></i>광고주문 관리</a>
        <a class="nav-link" href="#" data-page="admin-metrics"><i class="fas fa-chart-bar"></i>광고 분석 관리</a>
        <a class="nav-link" href="#" data-page="admin-ad-executions"><i class="fas fa-tasks"></i>광고 실행 현황</a>
        <a class="nav-link" href="#" data-page="admin-ad-keywords"><i class="fas fa-key"></i>광고 키워드 승인</a>
        <a class="nav-link" href="#" data-page="admin-ad-dispatch"><i class="fas fa-paper-plane"></i>광고 자동 집행</a>
        <div class="nav-section"><i class="fas fa-layer-group me-1" style="font-size:.6rem"></i>플랜</div>
        <a class="nav-link" href="#" data-page="admin-plans"><i class="fas fa-layer-group"></i>플랜 관리</a>
        <div class="nav-section"><i class="fas fa-user-tie me-1" style="font-size:.6rem"></i>ADPAY 영업 · 인력</div>
        <a class="nav-link" href="#" data-page="admin-sales-managers"><i class="fas fa-user-tie"></i>영업관리자 관리</a>
        <a class="nav-link" href="#" data-page="admin-sales-assign"><i class="fas fa-handshake"></i>영업관리자 연결</a>
        <a class="nav-link" href="#" data-page="admin-users"><i class="fas fa-users-cog"></i>사용자 목록</a>
        <div class="nav-section"><i class="fas fa-gear me-1" style="font-size:.6rem"></i>시스템 설정</div>
        <a class="nav-link" href="#" data-page="admin-ai-settings"><i class="fas fa-robot"></i>AI 설정</a>
        <a class="nav-link" href="#" data-page="admin-rewardpop"><i class="fas fa-plug"></i>리워드팝 연동</a>`;
    } else if (role === 'sales') {
        html += `
        <div class="nav-section">영업 관리</div>
        <a class="nav-link" href="#" data-page="sales-merchants"><i class="fas fa-store"></i>담당 가맹점</a>
        <a class="nav-link" href="#" data-page="sales-commission"><i class="fas fa-coins"></i>커미션 현황</a>
        <div class="nav-section">출금</div>
        <a class="nav-link" href="#" data-page="sales-payouts"><i class="fas fa-money-bill-wave"></i>출금요청</a>
        <a class="nav-link" href="#" data-page="sales-payout-history"><i class="fas fa-history"></i>출금내역</a>`;
    } else if (role === 'owner') {
        const needsStaff = ownerMerchantInfo ? ownerMerchantInfo.needs_staff_management : true;
        const masterOn = adFeatureFlags.ad_order_mgmt_enabled;
        const blogOn = adFeatureFlags.ad_blog_enabled;
        const placeOn = adFeatureFlags.ad_place_traffic_enabled;
        html += `
        <div class="nav-section">매장 관리</div>
        <a class="nav-link" href="#" data-page="owner-transactions"><i class="fas fa-receipt"></i>결제 내역</a>`;
        if (needsStaff) {
            html += `
        <a class="nav-link" href="#" data-page="owner-staff"><i class="fas fa-users"></i>직원 관리</a>
        <a class="nav-link" href="#" data-page="owner-staff-sales"><i class="fas fa-chart-bar"></i>직원별 매출</a>
        <a class="nav-link" href="#" data-page="owner-settlement"><i class="fas fa-coins"></i>정산 분배</a>`;
        }
        html += `
        <!-- 정산·출금 메뉴: 단말기 앱 이관으로 임시 비활성화 (코드 보존)
        <div class="nav-section">정산 · 출금</div>
        <a class="nav-link" href="#" data-page="owner-settlements"><i class="fas fa-file-invoice-dollar"></i>정산 내역</a>
        <a class="nav-link" href="#" data-page="owner-payouts"><i class="fas fa-money-bill-wave"></i>출금 요청</a>
        -->
        <div class="nav-section">리뷰 관리</div>
        <a class="nav-link" href="#" data-page="owner-receipt-review"><i class="fas fa-qrcode"></i>영수증 리뷰관리</a>
        <div class="nav-section">광고/마케팅</div>
        <a class="nav-link" href="#" data-page="owner-analysis"><i class="fas fa-chart-line"></i>광고 분석</a>
        <a class="nav-link" href="#" data-page="owner-ad-settings"><i class="fas fa-sliders"></i>광고 설정</a>
        <a class="nav-link" href="#" data-page="owner-ad-credit"><i class="fas fa-wallet"></i>광고비</a>`;
        if (masterOn) {
            html += `
        <a class="nav-link" href="#" data-page="owner-adorders"><i class="fas fa-bullhorn"></i>내 광고 주문</a>
        <a class="nav-link" href="#" data-page="owner-adorder-new"><i class="fas fa-plus-circle"></i>새 광고 주문</a>`;
        }
        if (isBeautyBusiness()) {
            html += `
        <div class="nav-section">고객관리 프로그램</div>
        <a class="nav-link" href="#" data-page="crm"><i class="fas fa-user-friends"></i>고객관리 프로그램</a>`;
        }
        html += `
        <div class="nav-section">설정</div>
        <a class="nav-link" href="#" data-page="owner-info"><i class="fas fa-cog"></i>매장 정보</a>`;
    } else if (role === 'designer') {
        html += `
        <div class="nav-section">내 매출</div>
        <a class="nav-link" href="#" data-page="designer-transactions"><i class="fas fa-receipt"></i>결제 내역</a>
        <a class="nav-link" href="#" data-page="designer-monthly"><i class="fas fa-calendar-alt"></i>월별 통계</a>
        <a class="nav-link" href="#" data-page="designer-settlement"><i class="fas fa-coins"></i>정산 분배</a>`;
        if (isBeautyBusiness()) {
            html += `
        <div class="nav-section">고객관리 프로그램</div>
        <a class="nav-link" href="#" data-page="crm"><i class="fas fa-user-friends"></i>고객관리 프로그램</a>`;
        }
        html += `
        <div class="nav-section">정보</div>
        <a class="nav-link" href="#" data-page="designer-profile"><i class="fas fa-id-badge"></i>내 정보</a>`;
    }

    nav.innerHTML = html;
    nav.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const page = link.dataset.page;
            if (page) navigate(page);
        });
    });
}

function navigate(page, options = {}) {
    currentPage = page;
    document.body.dataset.page = page;
    document.querySelectorAll('#sidebarNav .nav-link').forEach(l => {
        l.classList.toggle('active', l.dataset.page === page);
    });
    document.getElementById('sidebar').classList.remove('show');
    const overlay = document.getElementById('sidebarOverlay');
    if (overlay) overlay.classList.remove('show');
    document.body.classList.remove('sidebar-open');
    closeMobileMenu();
    updateMobileNavigation(page);
    updateAdminMobileHeader(page);
    if (!options.skipHistory) {
        const url = `${location.pathname}${location.search}#${page}`;
        if (options.replaceHistory) history.replaceState({ page }, '', url);
        else if (location.hash !== `#${page}`) history.pushState({ page }, '', url);
    }
    loadPage(page);
}

// ─── Page Router ───────────────────────────────────────────
async function loadPage(page) {
    const c = document.getElementById('pageContent');
    const t = document.getElementById('pageTitle') || { textContent: '' };
    c.innerHTML = adpayLoadingMarkup();

    try {
        switch(page) {
            case 'home': await loadHomePage(c, t); break;
            // Admin
            case 'admin-merchants': await loadAdminMerchants(c, t); break;
            case 'admin-pg': await loadAdminPG(c, t); break;
            case 'admin-terminals': await loadAdminTerminals(c, t); break;
            case 'admin-transactions': await loadAdminTransactions(c, t); break;
            case 'admin-ongi': await loadAdminOngi(c, t); break;
            case 'admin-settlements': await loadAdminSettlements(c, t); break;
            case 'admin-fee-settings': await loadAdminFeeSettings(c, t); break;
            case 'admin-fee-policies': await loadAdminFeePolicies(c, t); break;
            case 'admin-commission-visibility': await loadAdminCommissionVisibility(c, t); break;
            case 'admin-payouts': await loadAdminPayouts(c, t); break;
            case 'admin-adorders': await loadAdminAdOrders(c, t); break;
            case 'admin-metrics': await loadAdminMetrics(c, t); break;
            case 'admin-plans': await loadAdminPlans(c, t); break;
            case 'admin-ad-executions': await loadAdminAdExecutions(c, t); break;
            case 'admin-sales-managers': await loadAdminSalesManagers(c, t); break;
            case 'admin-sales-assign': await loadAdminSalesAssign(c, t); break;
            case 'admin-users': await loadAdminUsers(c, t); break;
            case 'admin-ai-settings': await loadAdminAiSettings(c, t); break;
            case 'admin-rewardpop': await loadAdminRewardpop(c, t); break;
            case 'admin-ad-keywords': await loadAdminAdKeywords(c, t); break;
            case 'admin-ad-dispatch': await loadAdminAdDispatch(c, t); break;
            case 'admin-ad-credits': await loadAdminAdCredits(c, t); break;
            // Sales
            case 'sales-merchants': await loadSalesMerchants(c, t); break;
            case 'sales-commission': await loadSalesCommission(c, t); break;
            case 'sales-payouts': await loadSalesPayouts(c, t); break;
            case 'sales-payout-history': await loadSalesPayoutHistory(c, t); break;
            // Owner
            case 'owner-transactions': await loadOwnerTransactions(c, t); break;
            case 'owner-staff': await loadOwnerStaff(c, t); break;
            case 'owner-staff-sales': await loadOwnerStaffSales(c, t); break;
            case 'owner-settlement': await loadOwnerSettlement(c, t); break;
            case 'owner-settlements': await loadOwnerSettlements(c, t); break;
            case 'owner-payouts': await loadOwnerPayouts(c, t); break;
            case 'owner-daily-summary': await loadOwnerTransactions(c, t, 'daily'); break;
            case 'owner-analysis': await loadOwnerAnalysis(c, t); break;
            case 'owner-adorders': await loadOwnerAdOrders(c, t); break;
            case 'owner-adorder-new': await loadOwnerAdOrderNew(c, t); break;
            case 'owner-ad-settings': await loadOwnerAdSettings(c, t); break;
            case 'owner-ad-credit': await loadOwnerAdCredit(c, t); break;
            case 'owner-info': await loadOwnerInfo(c, t); break;
            case 'owner-receipt-review': await loadOwnerReceiptReview(c, t); break;
            case 'owner-crm':
            case 'crm':
                if (!isBeautyBusiness()) {
                    c.innerHTML = '<div class="alert alert-warning mt-3"><i class="fas fa-lock me-2"></i>이 메뉴는 고객관리 업종 전용입니다.</div>';
                } else {
                    await loadCRM(c, t);
                }
                break;
            // Designer
            case 'designer-transactions': await loadDesignerTransactions(c, t); break;
            case 'designer-monthly': await loadDesignerMonthly(c, t); break;
            case 'designer-settlement': await loadDesignerSettlement(c, t); break;
            case 'designer-profile': await loadDesignerProfile(c, t); break;
            default: c.innerHTML = '<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2"></i>페이지를 찾을 수 없습니다.</div>';
        }
        enhanceRoleMobilePage(c);
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${escapeHtml(e.message)}</div>`;
    }
}

// ─── Home Dashboard ────────────────────────────────────────
async function loadHomePage(c, t) {
    t.textContent = '대시보드';
    const role = currentUser.role;
    let stats, html = '';

    if (role === 'admin') {
        stats = await apiGet('/api/admin/stats/landing');
        const todayDiff = stats.yesterday_sales > 0 ? ((stats.today_sales - stats.yesterday_sales) / stats.yesterday_sales * 100).toFixed(1) : 0;
        const todayArrow = todayDiff >= 0 ? 'up' : 'down';
        const todayColor = todayDiff >= 0 ? 'success' : 'danger';
        const weeklyLabels = (stats.weekly_data||[]).map(d => d.date + '(' + d.day + ')');
        const weeklyValues = (stats.weekly_data||[]).map(d => d.sales);

        html = `
        <!-- 메인 KPI -->
        <div class="row g-3 mb-4">
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm"><div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div class="kpi-icon bg-success bg-opacity-10 text-success"><i class="fas fa-won-sign"></i></div>
                        <span class="badge bg-${todayColor} bg-opacity-10 text-${todayColor}" style="font-size:.65rem">
                            <i class="fas fa-arrow-${todayArrow} me-1"></i>${Math.abs(todayDiff)}%
                        </span>
                    </div>
                    <div class="kpi-value">${formatMoney(stats.today_sales)}</div>
                    <div class="kpi-label">오늘 매출 <span class="text-muted" style="font-size:.65rem">(${stats.today_txn_count}건)</span></div>
                </div></div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm"><div class="card-body">
                    <div class="kpi-icon bg-info bg-opacity-10 text-info mb-2"><i class="fas fa-calendar"></i></div>
                    <div class="kpi-value">${formatMoney(stats.month_sales)}</div>
                    <div class="kpi-label">이번달 매출</div>
                </div></div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm"><div class="card-body">
                    <div class="kpi-icon bg-primary bg-opacity-10 text-primary mb-2"><i class="fas fa-store"></i></div>
                    <div class="kpi-value">${stats.total_merchants}</div>
                    <div class="kpi-label">총 가맹점</div>
                </div></div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm"><div class="card-body">
                    <div class="kpi-icon bg-warning bg-opacity-10 text-warning mb-2"><i class="fas fa-won-sign"></i></div>
                    <div class="kpi-value">${formatMoney(stats.total_volume)}</div>
                    <div class="kpi-label">누적 총 매출</div>
                </div></div>
            </div>
        </div>

        <!-- 서브 KPI: 운영 현황 -->
        <div class="row g-2 mb-4">
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold text-primary">${stats.total_users}</div><small class="text-muted" style="font-size:.7rem">사용자</small>
                </div></div>
            </div>
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold text-success">${stats.total_transactions}</div><small class="text-muted" style="font-size:.7rem">결제건</small>
                </div></div>
            </div>
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold text-danger">${stats.pending_payouts}</div><small class="text-muted" style="font-size:.7rem">대기 출금</small>
                </div></div>
            </div>
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold text-warning">${stats.pending_ad_orders}</div><small class="text-muted" style="font-size:.7rem">대기 광고</small>
                </div></div>
            </div>
        </div>

        <!-- 차트 + 최근결제 -->
        <div class="row g-3 mb-4">
            <div class="col-lg-8">
                <div class="card data-card shadow-sm" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-chart-bar text-primary me-2"></i>최근 7일 매출</h5></div>
                    <div class="card-body" style="height:220px"><canvas id="adminWeeklyChart"></canvas></div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0"><i class="fas fa-clock text-info me-2"></i>최근 결제</h5>
                        <a href="#" onclick="navigate('admin-transactions')" class="small text-primary text-decoration-none">전체 →</a>
                    </div>
                    <div class="card-body p-0 mobile-unclip" style="max-height:220px;overflow-y:auto">
                        <div class="list-group list-group-flush">
                            ${(stats.recent_transactions||[]).map(tx => `
                            <div class="list-group-item d-flex justify-content-between align-items-center px-3 py-2" style="font-size:.82rem">
                                <div><div class="fw-bold">${formatMoney(tx.amount)}</div><small class="text-muted">${escapeHtml(tx.merchant_name)}</small></div>
                                <div class="text-end"><span class="badge bg-secondary bg-opacity-10 text-secondary">${escapeHtml(tx.card_brand||'-')}</span><br><small class="text-muted">${formatDate(tx.created_at)}</small></div>
                            </div>`).join('') || '<div class="p-3 text-muted text-center">결제 내역 없음</div>'}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 빠른 바로가기 -->
        <div class="row g-3 mb-4">
            <div class="col-12">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-th-large text-primary me-2"></i>빠른 바로가기</h5></div>
                    <div class="card-body">
                        <div class="row g-2">
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-merchants')" class="btn btn-outline-primary w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-store"></i>가맹점</a></div>
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-transactions')" class="btn btn-outline-success w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-receipt"></i>결제내역</a></div>
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-payouts')" class="btn btn-outline-danger w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-money-bill-wave"></i>출금요청<span class="badge bg-danger ms-1" style="font-size:.6rem">${stats.pending_payouts}</span></a></div>
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-adorders')" class="btn btn-outline-warning w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-bullhorn"></i>광고주문<span class="badge bg-warning text-dark ms-1" style="font-size:.6rem">${stats.pending_ad_orders}</span></a></div>
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-settlements')" class="btn btn-outline-secondary w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-calculator"></i>정산</a></div>
                            <div class="col-4 col-lg-4"><a href="#" onclick="navigate('admin-users')" class="btn btn-outline-dark w-100 py-2 d-flex flex-column align-items-center gap-1" style="border-radius:10px;font-size:.78rem"><i class="fas fa-users-cog"></i>사용자</a></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 월별 추이 + TOP 가맹점 -->
        <div class="row g-3 mb-4">
            <div class="col-lg-7">
                <div class="card data-card shadow-sm" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-chart-line text-success me-2"></i>월별 매출 추이</h5></div>
                    <div class="card-body" style="height:220px"><canvas id="adminMonthlyTrend"></canvas></div>
                </div>
            </div>
            <div class="col-lg-5">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-trophy text-warning me-2"></i>이번달 TOP 가맹점</h5></div>
                    <div class="card-body p-0 mobile-unclip" style="max-height:220px;overflow-y:auto">
                        <div class="list-group list-group-flush" id="topMerchantsList"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 알림/최근활동 + 시스템정보 -->
        <div class="row g-3 mb-4">
            <div class="col-lg-8">
                <div class="card data-card shadow-sm" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-bell text-danger me-2"></i>알림 & 최근 활동</h5></div>
                    <div class="card-body p-0 mobile-unclip" id="adminAlertActivity" style="max-height:260px;overflow-y:auto"></div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-server me-2"></i>시스템 정보</h5></div>
                    <div class="card-body">
                        <ul class="list-unstyled mb-0" style="font-size:.88rem">
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">역할</span><span class="badge bg-danger">최고관리자</span></li>
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이메일</span><span class="fw-bold" style="font-size:.78rem">${escapeHtml(currentUser.email)}</span></li>
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">신규가입</span><span class="fw-bold text-primary" id="newUsersMonth">-</span></li>
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">상태</span><span class="badge bg-success">활성</span></li>
                            <li class="d-flex justify-content-between"><span class="text-muted">버전</span><span class="fw-bold">v1.3.0</span></li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>`;

        // 주간 차트 렌더링
        setTimeout(() => {
            const ctx = document.getElementById('adminWeeklyChart');
            if (ctx && typeof Chart !== 'undefined') {
                const prev = Chart.getChart(ctx);
                if (prev) prev.destroy();
                new Chart(ctx, {
                    type: 'bar', data: { labels: weeklyLabels, datasets: [{ label:'매출(원)', data: weeklyValues, backgroundColor:'rgba(14,165,233,.4)', borderColor:'#0ea5e9', borderWidth:1, borderRadius:6 }] },
                    options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>formatMoney(c.raw)+'원'}}}, scales:{y:{beginAtZero:true,ticks:{callback:v=>v>=10000?(v/10000)+'만':v.toLocaleString()}},x:{grid:{display:false}}} }
                });
            }
        }, 100);

        // Enhanced stats (알림, 월별 추이, TOP 가맹점 등)
        try {
            const enhanced = await apiGet('/api/admin/stats/enhanced');

            // 월별 추이 차트
            setTimeout(() => {
                const mCtx = document.getElementById('adminMonthlyTrend');
                if (mCtx && typeof Chart !== 'undefined') {
                    const prevM = Chart.getChart(mCtx);
                    if (prevM) prevM.destroy();
                    new Chart(mCtx, {
                        type: 'line',
                        data: {
                            labels: enhanced.monthly_trend.map(m => m.label),
                            datasets: [{
                                label: '매출(원)', data: enhanced.monthly_trend.map(m => m.sales),
                                borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,.1)',
                                fill: true, tension: .3, borderWidth: 2, pointRadius: 4,
                            }]
                        },
                        options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>formatMoney(c.raw)+'원'}}}, scales:{y:{beginAtZero:true,ticks:{callback:v=>v>=10000?(v/10000)+'만':v.toLocaleString(),font:{size:10}}},x:{grid:{display:false}}} }
                    });
                }
            }, 200);

            // TOP 가맹점
            const topEl = document.getElementById('topMerchantsList');
            if (topEl) {
                if (enhanced.top_merchants.length === 0) {
                    topEl.innerHTML = '<div class="p-3 text-center text-muted">이번달 매출 데이터 없음</div>';
                } else {
                    topEl.innerHTML = enhanced.top_merchants.slice(0,7).map((m, i) => `
                        <div class="list-group-item d-flex justify-content-between align-items-center px-3 py-2">
                            <div class="d-flex align-items-center gap-2">
                                <span class="badge ${i<3?'bg-warning text-dark':'bg-light text-muted'} rounded-circle" style="width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:.72rem">${i+1}</span>
                                <span class="fw-bold" style="font-size:.85rem">${escapeHtml(m.name)}</span>
                            </div>
                            <div class="text-end">
                                <div class="fw-bold text-success" style="font-size:.82rem">${formatMoney(m.sales)}</div>
                                <small class="text-muted">${m.count}건</small>
                            </div>
                        </div>
                    `).join('');
                }
            }

            // 알림 & 최근활동
            const actEl = document.getElementById('adminAlertActivity');
            if (actEl) {
                let alertHtml = '';
                // 알림
                if (enhanced.alerts.length > 0) {
                    alertHtml += enhanced.alerts.map(a => `
                        <div class="list-group-item list-group-item-${a.type} d-flex align-items-center gap-2 px-3 py-2 border-0" style="cursor:pointer" onclick="navigate('${escapeJsAttr(a.link)}')">
                            <i class="fas fa-${a.icon}"></i>
                            <span style="font-size:.85rem">${escapeHtml(a.text)}</span>
                            <i class="fas fa-chevron-right ms-auto" style="font-size:.7rem;opacity:.5"></i>
                        </div>
                    `).join('');
                }
                // 최근 활동
                alertHtml += '<div class="px-3 py-2 bg-light border-bottom"><small class="fw-bold text-muted"><i class="fas fa-history me-1"></i>최근 활동</small></div>';
                alertHtml += (enhanced.recent_activities || []).slice(0,10).map(a => `
                    <div class="list-group-item d-flex align-items-start gap-2 px-3 py-2 border-0">
                        <div class="mt-1"><i class="fas fa-${a.icon} text-${a.color}" style="font-size:.75rem"></i></div>
                        <div class="flex-grow-1">
                            <div style="font-size:.82rem">${escapeHtml(a.text)}</div>
                            <small class="text-muted">${formatDate(a.created_at)} · <span class="badge bg-${a.status==='pending'?'warning':a.status==='paid'||a.status==='approved'||a.status==='done'?'success':a.status==='rejected'?'danger':'secondary'}" style="font-size:.65rem">${a.status}</span></small>
                        </div>
                    </div>
                `).join('') || '<div class="p-3 text-center text-muted">활동 내역 없음</div>';
                actEl.innerHTML = alertHtml;
            }

            // 신규 사용자
            const newEl = document.getElementById('newUsersMonth');
            if (newEl) newEl.textContent = (enhanced.new_users_month || 0) + '명';
        } catch(e) { console.log('Enhanced stats load error:', e); }
    } else if (role === 'sales') {
        stats = await apiGet('/api/sales/dashboard-stats');
        html = `
        <div class="row g-3 mb-4">
            ${kpiCard('담당 가맹점', stats.merchant_count, 'store', 'primary')}
            ${kpiCard('오늘 매출', formatMoney(stats.today_sales), 'won-sign', 'success')}
            ${kpiCard('이번달 매출', formatMoney(stats.month_sales), 'calendar', 'info')}
            ${kpiCard('누적 커미션', stats.show_commission===false?'비공개':formatMoney(stats.total_commission), 'coins', 'warning')}
        </div>
        <div class="row g-3">
            <div class="col-md-6">
                <div class="card data-card"><div class="card-header"><h5>빠른 바로가기</h5></div><div class="card-body">
                    <div class="d-grid gap-2">
                        <a href="#" onclick="navigate('sales-merchants')" class="btn btn-outline-primary py-2"><i class="fas fa-store me-2"></i>담당 가맹점 현황</a>
                        <a href="#" onclick="navigate('sales-payouts')" class="btn btn-outline-warning py-2"><i class="fas fa-money-bill-wave me-2"></i>출금요청</a>
                        <a href="#" onclick="navigate('sales-commission')" class="btn btn-outline-success py-2"><i class="fas fa-coins me-2"></i>커미션 현황</a>
                    </div>
                </div></div>
            </div>
            <div class="col-md-6">
                <div class="card data-card h-100"><div class="card-header"><h5>내 정보</h5></div><div class="card-body">
                    <ul class="list-unstyled mb-0">
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이름</span><span class="fw-bold">${escapeHtml(currentUser.name)}</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">역할</span><span class="badge bg-info">영업관리자</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">대기 출금</span><span class="fw-bold">${stats.pending_payouts || 0}건</span></li>
                        ${stats.referral_code ? `
                        <li class="mt-3 pt-2 border-top">
                            <div class="text-muted small mb-1"><i class="fas fa-tag me-1"></i>내 추천 코드</div>
                            <div class="d-flex align-items-center gap-2">
                                <code class="fs-6 text-info fw-bold">${escapeHtml(stats.referral_code)}</code>
                                <button class="btn btn-sm btn-outline-info" onclick="copySalesRefLink('${location.origin}/static/login.html?ref=${encodeURIComponent(stats.referral_code)}', this)" title="추천 링크 복사">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                            <small class="text-muted d-block mt-1">사장님께 추천 링크를 전달하면 가맹점이 자동 연결됩니다.</small>
                        </li>` : ''}
                    </ul>
                </div></div>
            </div>
        </div>`;
    } else if (role === 'owner') {
        stats = await apiGet('/api/owner/dashboard-stats');

        // 전일/전월 대비 변동률
        const todayDiff = stats.yesterday_sales > 0 ? ((stats.today_sales - stats.yesterday_sales) / stats.yesterday_sales * 100).toFixed(1) : 0;
        const monthDiff = stats.last_month_sales > 0 ? ((stats.month_sales - stats.last_month_sales) / stats.last_month_sales * 100).toFixed(1) : 0;
        const todayArrow = todayDiff >= 0 ? 'up' : 'down';
        const todayColor = todayDiff >= 0 ? 'success' : 'danger';
        const monthArrow = monthDiff >= 0 ? 'up' : 'down';
        const monthColor = monthDiff >= 0 ? 'success' : 'danger';

        // 주간 차트 데이터
        const weeklyLabels = (stats.weekly_data || []).map(d => d.date + '(' + d.day + ')');
        const weeklyValues = (stats.weekly_data || []).map(d => d.sales);
        const maxWeekly = Math.max(...weeklyValues, 1);
        const weeklyScaleMax = Math.max(100000, Math.ceil(maxWeekly / 100000) * 100000);

        // 직원 매출 순위
        const staffRanking = stats.staff_sales_today || [];
        const maxStaffSales = staffRanking.length > 0 ? Math.max(...staffRanking.map(s => s.sales), 1) : 1;

        // 최근 결제
        const recentTxns = stats.recent_transactions || [];

        html = `
        <!-- 매장 정보 배너 -->
        <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#0d1b2a 0%,#1b3a5c 60%,#0ea5e9 100%);">
            <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
                <div class="d-flex align-items-center gap-3">
                    <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;">
                        <i class="fas fa-store text-white"></i>
                    </div>
                    <div>
                        <h5 class="mb-0 text-white fw-bold">${escapeHtml(stats.merchant_name)}</h5>
                        <small class="text-white-50">${escapeHtml(stats.category || '')} ${stats.address ? '· ' + escapeHtml(stats.address) : ''}</small>
                    </div>
                </div>
                <div class="d-flex gap-2">
                    <a href="#" onclick="navigate('owner-info')" class="btn btn-sm btn-outline-light px-3" style="border-radius:20px;font-size:.8rem;"><i class="fas fa-cog me-1"></i>매장정보</a>
                </div>
            </div>
        </div>

        <!-- KPI 카드 (전일/전월 비교 포함) -->
        <div class="row g-3 mb-4">
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div class="kpi-icon bg-success bg-opacity-10 text-success"><i class="fas fa-won-sign"></i></div>
                            <span class="badge bg-${todayColor} bg-opacity-10 text-${todayColor}" style="font-size:.7rem;">
                                <i class="fas fa-arrow-${todayArrow} me-1"></i>${Math.abs(todayDiff)}%
                            </span>
                        </div>
                        <div class="kpi-value">${formatMoney(stats.today_sales)}</div>
                        <div class="kpi-label">오늘 매출 <span class="text-muted" style="font-size:.7rem;">(${stats.today_txn_count}건)</span></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div class="kpi-icon bg-info bg-opacity-10 text-info"><i class="fas fa-calendar"></i></div>
                            <span class="badge bg-${monthColor} bg-opacity-10 text-${monthColor}" style="font-size:.7rem;">
                                <i class="fas fa-arrow-${monthArrow} me-1"></i>${Math.abs(monthDiff)}%
                            </span>
                        </div>
                        <div class="kpi-value">${formatMoney(stats.month_sales)}</div>
                        <div class="kpi-label">이번달 매출</div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div class="kpi-icon bg-primary bg-opacity-10 text-primary"><i class="fas fa-receipt"></i></div>
                        </div>
                        <div class="kpi-value">${stats.total_transactions.toLocaleString()}</div>
                        <div class="kpi-label">총 결제건수</div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="card kpi-card shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div class="kpi-icon bg-warning bg-opacity-10 text-warning"><i class="fas fa-users"></i></div>
                        </div>
                        <div class="kpi-value">${stats.active_staff}</div>
                        <div class="kpi-label">활성 직원</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row g-3 mb-4">
            <!-- 주간 매출 차트 -->
            <div class="col-lg-8">
                <div class="card data-card shadow-sm" style="border-radius:14px;">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5><i class="fas fa-chart-bar text-primary me-2"></i>최근 7일 매출</h5>
                    </div>
                    <div class="card-body">
                        <canvas id="ownerWeeklyChart" height="220"></canvas>
                    </div>
                </div>
            </div>

            <!-- 직원 오늘 매출 순위 -->
            <div class="col-lg-4">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px;">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5><i class="fas fa-trophy text-warning me-2"></i>오늘 직원 매출</h5>
                        <a href="#" onclick="navigate('owner-staff-sales')" class="text-primary small text-decoration-none">전체보기 →</a>
                    </div>
                    <div class="card-body py-2">
                        ${staffRanking.length > 0 ? staffRanking.map((s, idx) => {
                            const barWidth = maxStaffSales > 0 ? (s.sales / maxStaffSales * 100) : 0;
                            const medals = ['🥇','🥈','🥉'];
                            const medal = idx < 3 ? medals[idx] : `<span class="text-muted fw-bold" style="font-size:.8rem;">${idx+1}</span>`;
                            return `
                            <div class="d-flex align-items-center gap-2 mb-2 py-1">
                                <span style="width:24px;text-align:center;">${medal}</span>
                                <span class="fw-bold" style="width:60px;font-size:.85rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(s.name)}</span>
                                <div class="flex-grow-1">
                                    <div style="height:18px;background:#f0f2f5;border-radius:9px;overflow:hidden;">
                                        <div style="width:${barWidth}%;height:100%;background:linear-gradient(90deg,#0ea5e9,#38bdf8);border-radius:9px;transition:width .5s;"></div>
                                    </div>
                                </div>
                                <span class="fw-bold" style="font-size:.8rem;min-width:70px;text-align:right;">${formatMoney(s.sales)}</span>
                            </div>`;
                        }).join('') : `
                        <div class="text-center py-4 text-muted">
                            <i class="fas fa-user-clock fa-2x mb-2 d-block opacity-25"></i>
                            <small>오늘 매출 기록이 없습니다</small>
                        </div>`}
                    </div>
                </div>
            </div>
        </div>

        <div class="row g-3 mb-4">
            <!-- 최근 결제 내역 -->
            <div class="col-lg-7">
                <div class="card data-card shadow-sm" style="border-radius:14px;">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5><i class="fas fa-clock text-info me-2"></i>최근 결제</h5>
                        <a href="#" onclick="navigate('owner-transactions')" class="text-primary small text-decoration-none">전체보기 →</a>
                    </div>
                    <div class="card-body p-0">
                        ${recentTxns.length > 0 ? `
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead><tr>
                                    <th style="padding-left:1.2rem;">금액</th>
                                    <th>직원</th>
                                    <th>카드사</th>
                                    <th>일시</th>
                                </tr></thead>
                                <tbody>
                                    ${recentTxns.map(tx => `
                                    <tr>
                                        <td style="padding-left:1.2rem;" class="fw-bold">${formatMoney(tx.amount)}</td>
                                        <td>${escapeHtml(tx.staff_name) || '<span class="text-muted">사장님</span>'}</td>
                                        <td><span class="badge bg-secondary bg-opacity-10 text-secondary">${escapeHtml(tx.card_brand || '-')}</span></td>
                                        <td class="text-muted" style="font-size:.8rem;">${formatDate(tx.created_at)}</td>
                                    </tr>`).join('')}
                                </tbody>
                            </table>
                        </div>` : `
                        <div class="text-center py-4 text-muted">
                            <i class="fas fa-inbox fa-2x mb-2 d-block opacity-25"></i>
                            <small>아직 결제 내역이 없습니다</small>
                        </div>`}
                    </div>
                </div>
            </div>

            <!-- 빠른 바로가기 -->
            <div class="col-lg-5">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px;">
                    <div class="card-header"><h5><i class="fas fa-th-large text-primary me-2"></i>빠른 바로가기</h5></div>
                    <div class="card-body">
                        <div class="row g-2">
                            <div class="col-6"><a href="#" onclick="navigate('owner-transactions')" class="btn btn-outline-primary w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-receipt fs-5"></i>결제내역</a></div>
                            <div class="col-6"><a href="#" onclick="navigate('owner-staff')" class="btn btn-outline-success w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-users fs-5"></i>직원관리</a></div>
                            <div class="col-6"><a href="#" onclick="navigate('owner-staff-sales')" class="btn btn-outline-warning w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-chart-bar fs-5"></i>직원매출</a></div>
                            <div class="col-6"><a href="#" onclick="navigate('owner-daily-summary')" class="btn btn-outline-info w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-calendar-day fs-5"></i>일별요약</a></div>
                            <div class="col-6"><a href="#" onclick="navigate('owner-receipt-review')" class="btn btn-outline-danger w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-star fs-5"></i>영수증리뷰</a></div>
                            <div class="col-6"><a href="#" onclick="navigate('owner-analysis')" class="btn btn-outline-dark w-100 py-3 d-flex flex-column align-items-center gap-1" style="border-radius:12px;font-size:.85rem;"><i class="fas fa-chart-line fs-5"></i>광고분석</a></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 월별 결제 캘린더 -->
        <div class="row g-3 mb-4">
            <div class="col-12">
                <div class="card data-card shadow-sm" style="border-radius:14px;">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5><i class="fas fa-calendar-alt text-info me-2"></i>월별 결제 캘린더</h5>
                        <div class="d-flex align-items-center gap-2">
                            <button class="btn btn-sm btn-outline-secondary" id="dashCalPrev"><i class="fas fa-chevron-left"></i></button>
                            <span class="fw-bold" id="dashCalTitle" style="min-width:110px;text-align:center;font-size:.9rem;"></span>
                            <button class="btn btn-sm btn-outline-secondary" id="dashCalNext"><i class="fas fa-chevron-right"></i></button>
                        </div>
                    </div>
                    <div class="card-body p-2 p-md-3">
                        <div id="dashCalendarGrid"></div>
                        <div id="dashCalMonthTotal" class="text-center mt-2"></div>
                    </div>
                </div>
            </div>
        </div>`;

        // 차트 렌더링은 DOM 삽입 이후 실행
        setTimeout(() => {
            const ctx = document.getElementById('ownerWeeklyChart');
            if (ctx) {
                if (typeof Chart !== 'undefined') {
                    const prev = Chart.getChart(ctx);
                    if (prev) prev.destroy();
                }
                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: weeklyLabels,
                        datasets: [{
                            label: '매출 (원)',
                            data: weeklyValues,
                            backgroundColor: weeklyValues.map((v, i) => i === weeklyValues.length - 1 ? 'rgba(14,165,233,.85)' : 'rgba(14,165,233,.35)'),
                            borderColor: weeklyValues.map((v, i) => i === weeklyValues.length - 1 ? '#0ea5e9' : 'rgba(14,165,233,.5)'),
                            borderWidth: 1,
                            borderRadius: 7,
                            borderSkipped: false,
                            barPercentage: .72,
                            categoryPercentage: .78,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => formatMoney(ctx.raw) + '원'
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: weeklyScaleMax,
                                ticks: {
                                    stepSize: 100000,
                                    precision: 0,
                                    callback: (v) => Number(v) / 100000,
                                    font: { size: 10 },
                                    color: '#64748b',
                                },
                                title: {
                                    display: true,
                                    text: '단위: 100,000원',
                                    color: '#64748b',
                                    font: { size: 10, weight: '600' }
                                },
                                grid: { color: 'rgba(15,76,129,.08)' }
                            },
                            x: {
                                ticks: { font: { size: 11 } },
                                grid: { display: false }
                            }
                        }
                    }
                });
            }
        }, 100);

        // 대시보드 캘린더 렌더링
        setTimeout(() => {
            const dashCalGrid = document.getElementById('dashCalendarGrid');
            if (!dashCalGrid) return;
            const now2 = new Date();
            let dcYear = now2.getFullYear(), dcMonth = now2.getMonth() + 1;

            async function renderDashCal() {
                document.getElementById('dashCalTitle').textContent = `${dcYear}년 ${dcMonth}월`;
                dashCalGrid.innerHTML = adpayLoadingMarkup();
                try {
                    const data = await apiGet(`/api/owner/calendar-monthly?year=${dcYear}&month=${dcMonth}`);
                    const dailyMap = {};
                    let mTotal = 0, mCount = 0;
                    (data.days || []).forEach(d => { dailyMap[d.date] = d; mTotal += d.total; mCount += d.count; });
                    document.getElementById('dashCalMonthTotal').innerHTML = `<span class="badge bg-info bg-opacity-10 text-info px-3 py-2" style="font-size:.85rem;">월 합계: <strong>${formatMoney(mTotal)}</strong> (${mCount}건)</span>`;

                    const firstDay = new Date(dcYear, dcMonth-1, 1).getDay();
                    const daysInMonth = new Date(dcYear, dcMonth, 0).getDate();
                    const todayStr2 = now2.getFullYear() + '-' + String(now2.getMonth()+1).padStart(2,'0') + '-' + String(now2.getDate()).padStart(2,'0');

                    let h = '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;">';
                    ['일','월','화','수','목','금','토'].forEach((d,i) => {
                        h += `<div style="text-align:center;font-weight:700;font-size:.72rem;padding:5px 2px;color:${i===0?'#dc3545':i===6?'#0d6efd':'#6c757d'}">${d}</div>`;
                    });
                    for (let i = 0; i < firstDay; i++) h += '<div></div>';
                    for (let d = 1; d <= daysInMonth; d++) {
                        const ds = `${dcYear}-${String(dcMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
                        const dd = dailyMap[ds];
                        const isT = ds === todayStr2;
                        const dow = new Date(dcYear, dcMonth-1, d).getDay();
                        const tc = dow === 0 ? '#dc3545' : dow === 6 ? '#0d6efd' : '#333';
                        const has = dd && dd.total > 0;
                        h += `<div onclick="showDailyDetail('${ds}')" style="cursor:pointer;border:1px solid ${isT?'#0d6efd':'#e9ecef'};border-radius:6px;padding:3px;min-height:52px;background:${isT?'rgba(13,110,253,.05)':'#fff'};transition:all .15s;" onmouseover="this.style.boxShadow='0 2px 8px rgba(0,0,0,.1)'" onmouseout="this.style.boxShadow='none'">
                            <div style="font-size:.72rem;font-weight:${isT?'800':'600'};color:${tc}">${d}</div>
                            ${has ? `<div style="font-size:.6rem;font-weight:700;color:#0d6efd;margin-top:1px;">${dd.total >= 10000 ? Math.round(dd.total/10000) + '만' : formatMoney(dd.total)}</div><div style="font-size:.55rem;color:#6c757d">${dd.count}건</div>` : ''}
                        </div>`;
                    }
                    h += '</div>';
                    dashCalGrid.innerHTML = h;
                } catch (e) {
                    dashCalGrid.innerHTML = '<div class="text-muted text-center py-2 small">캘린더를 불러올 수 없습니다</div>';
                }
            }

            document.getElementById('dashCalPrev').onclick = () => { dcMonth--; if (dcMonth < 1) { dcMonth = 12; dcYear--; } renderDashCal(); };
            document.getElementById('dashCalNext').onclick = () => { dcMonth++; if (dcMonth > 12) { dcMonth = 1; dcYear++; } renderDashCal(); };
            renderDashCal();
        }, 200);
    } else if (role === 'designer') {
        stats = await apiGet('/api/designer/dashboard-stats');
        html = `
        <div class="row g-3 mb-4">
            ${kpiCard('오늘 매출', formatMoney(stats.today_sales), 'won-sign', 'success')}
            ${kpiCard('이번달 매출', formatMoney(stats.month_sales), 'calendar', 'info')}
            ${kpiCard('총 결제건수', stats.total_transactions, 'receipt', 'primary')}
            ${kpiCard('총 매출', formatMoney(stats.total_sales), 'coins', 'warning')}
        </div>
        <div class="row g-3">
            <div class="col-12">
                <div class="card data-card mb-3"><div class="card-body text-center py-3">
                    <span class="text-muted">직원:</span> <strong>${escapeHtml(stats.staff_name)}</strong>
                    <span class="badge bg-secondary ms-2">코드: ${escapeHtml(stats.staff_code)}</span>
                </div></div>
            </div>
            <div class="col-md-6">
                <div class="card data-card"><div class="card-header"><h5>빠른 바로가기</h5></div><div class="card-body">
                    <div class="d-grid gap-2">
                        <a href="#" onclick="navigate('designer-transactions')" class="btn btn-outline-primary py-2"><i class="fas fa-receipt me-2"></i>결제 내역 보기</a>
                        <a href="#" onclick="navigate('designer-monthly')" class="btn btn-outline-info py-2"><i class="fas fa-calendar-alt me-2"></i>월별 통계</a>
                    </div>
                </div></div>
            </div>
            <div class="col-md-6">
                <div class="card data-card h-100"><div class="card-header"><h5>내 정보</h5></div><div class="card-body">
                    <ul class="list-unstyled mb-0">
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이름</span><span class="fw-bold">${escapeHtml(stats.staff_name)}</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">직원코드</span><code>${escapeHtml(stats.staff_code)}</code></li>
                        <li class="d-flex justify-content-between"><span class="text-muted">이번달 건수</span><span class="fw-bold">${stats.total_transactions}건</span></li>
                    </ul>
                </div></div>
            </div>
        </div>`;
    }
    c.innerHTML = html;
}

function kpiCard(label, value, icon, color) {
    return `<div class="col-lg-3 col-md-6 col-6"><div class="card kpi-card shadow-sm">
        <div class="card-body"><div class="d-flex align-items-center">
            <div class="kpi-icon bg-${color} bg-opacity-10 me-3"><i class="fas fa-${icon} text-${color}"></i></div>
            <div><div class="kpi-value">${value}</div><div class="kpi-label">${label}</div></div>
        </div></div></div></div>`;
}

// ═══════════════════════════════════════════════════════════
// ADMIN PAGES
// ═══════════════════════════════════════════════════════════

async function loadAdminMerchants(c, t) {
    t.textContent = '가맹점 관리';
    const merchants = await apiGet('/api/admin/merchants');
    let rows = merchants.map(m => `<tr>
        <td>${m.id}</td><td class="fw-bold">${escapeHtml(m.name)}</td><td>${escapeHtml(m.business_no||'-')}</td>
        <td>${escapeHtml(m.address||'-')}</td><td>${escapeHtml(m.phone||'-')}</td>
        <td>${m.is_active?'<span class="badge bg-success">활성</span>':'<span class="badge bg-danger">비활성</span>'}</td>
        <td class="text-nowrap">
            <button class="btn btn-sm btn-outline-primary me-1" onclick="showPGConfig(${m.id})"><i class="fas fa-cog"></i> PG</button>
            <button class="btn btn-sm btn-outline-success" onclick="showMerchantAdStatus(${m.id}, '${escapeHtml(m.name).replace(/'/g,"\\'")}')"><i class="fas fa-chart-bar"></i> 광고 현황</button>
        </td>
    </tr>`).join('');
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">가맹점 목록</h5>
        <button class="btn btn-primary btn-sm" onclick="showNewMerchantForm()"><i class="fas fa-plus me-1"></i>새 가맹점</button>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover">
            <thead><tr><th>ID</th><th>이름</th><th>사업자번호</th><th>주소</th><th>연락처</th><th>상태</th><th>액션</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="7" class="text-center text-muted py-4">데이터 없음</td></tr>'}</tbody>
        </table></div>
    </div></div>`;
}

async function showNewMerchantForm() {
    resetFormModalFooter(true);
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '새 가맹점 등록';

    // 가맹점 소유자는 사장님 계정이어야 하고, 한 계정이 두 가맹점을 가질 수 없다.
    // 대상 계정을 직접 골라 등록 실패를 미리 막는다.
    let owners = [];
    try {
        owners = (await apiGet('/api/admin/users?role=owner')).filter(u => u.is_active && !u.merchant_name);
    } catch (e) { owners = []; }

    const ownerField = owners.length
        ? `<select class="form-select" id="fMerchOwner">
             ${owners.map(u => `<option value="${u.id}">${escapeHtml(u.name)} (${escapeHtml(u.email)})</option>`).join('')}
           </select>`
        : `<div class="alert alert-warning py-2 mb-0 small">
             <i class="fas fa-triangle-exclamation me-1"></i>가맹점을 배정할 수 있는 사장님 계정이 없습니다.
             사장님이 먼저 회원가입해야 합니다.
           </div>`;

    body.innerHTML = `
    <div class="row g-3">
        <div class="col-md-6"><label class="form-label">가맹점 이름</label><input class="form-control" id="fMerchName"></div>
        <div class="col-md-6"><label class="form-label">소유자(사장님) 계정</label>${ownerField}</div>
        <div class="col-md-6"><label class="form-label">사업자번호</label><input class="form-control" id="fMerchBiz"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="fMerchPhone"></div>
        <div class="col-12"><label class="form-label">주소</label><input class="form-control" id="fMerchAddr"></div>
        <div class="col-12"><div id="fMerchResult"></div></div>
    </div>`;

    const saveBtn = document.getElementById('formModalSave');
    saveBtn.disabled = !owners.length;
    saveBtn.onclick = async () => {
        const result = document.getElementById('fMerchResult');
        result.innerHTML = '';
        try {
            await apiPost('/api/admin/merchants', {
                name: document.getElementById('fMerchName').value,
                owner_user_id: parseInt(document.getElementById('fMerchOwner').value, 10),
                business_no: document.getElementById('fMerchBiz').value,
                address: document.getElementById('fMerchAddr').value,
                phone: document.getElementById('fMerchPhone').value,
            });
            bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
            navigate('admin-merchants');
        } catch (e) {
            result.innerHTML = `<div class="alert alert-danger py-2 mb-0 small">${escapeHtml(e.message)}</div>`;
        }
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

async function loadAdminPG(c, t) {
    t.textContent = 'PG 설정';
    const merchants = await apiGet('/api/admin/merchants');
    const providers = await apiGet('/api/admin/pg-providers');
    let provOpts = providers.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.code)})</option>`).join('');
    let merchOpts = merchants.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    c.innerHTML = `<div class="row g-4">
        <div class="col-md-5">
            <div class="card data-card"><div class="card-header"><h5>PG 연동 등록</h5></div><div class="card-body">
                <div class="mb-3"><label class="form-label">가맹점</label><select class="form-select" id="pgMerchant" onchange="loadPGConfigs()">${merchOpts}</select></div>
                <div class="mb-3"><label class="form-label">PG사</label><select class="form-select" id="pgProvider">${provOpts}</select></div>
                <div class="mb-3"><label class="form-label">MID</label><input class="form-control" id="pgMid"></div>
                <div class="mb-3"><label class="form-label">SECRET</label><input class="form-control" id="pgSecret" type="password"></div>
                <button class="btn btn-primary w-100" onclick="savePGConfig()"><i class="fas fa-save me-1"></i>등록</button>
                <div id="pgSaveResult" class="mt-2"></div>
            </div></div>
        </div>
        <div class="col-md-7">
            <div class="card data-card"><div class="card-header"><h5>등록된 PG 설정</h5></div><div class="card-body">
                <div id="pgConfigList"><p class="text-muted">가맹점을 선택하세요</p></div>
            </div></div>
        </div>
    </div>`;
    if (merchants.length > 0) loadPGConfigs();
}

async function loadPGConfigs() {
    const mid = document.getElementById('pgMerchant').value;
    const configs = await apiGet(`/api/admin/merchants/${mid}/pg-configs`);
    const el = document.getElementById('pgConfigList');
    if (configs.length === 0) { el.innerHTML = '<p class="text-muted text-center py-3">등록된 PG 없음</p>'; return; }
    el.innerHTML = `<div class="table-responsive"><table class="table table-sm"><thead><tr><th>PG사</th><th>MID</th><th>SECRET</th><th>상태</th><th>테스트</th></tr></thead><tbody>
    ${configs.map(cfg => `<tr>
        <td class="fw-bold">${escapeHtml(cfg.provider_name)}</td><td><code>${escapeHtml(cfg.mid)}</code></td><td>${escapeHtml(cfg.secret_masked)}</td>
        <td>${statusBadge(cfg.status)}</td>
        <td><button class="btn btn-sm btn-outline-warning" onclick="testPG(${mid},${cfg.id})"><i class="fas fa-vial"></i></button>
            <span id="pgTestResult${cfg.id}"></span></td>
    </tr>`).join('')}</tbody></table></div>`;
}

async function savePGConfig() {
    const mid = document.getElementById('pgMerchant').value;
    try {
        await apiPost(`/api/admin/merchants/${mid}/pg-config`, { provider_id: parseInt(document.getElementById('pgProvider').value), mid: document.getElementById('pgMid').value, secret: document.getElementById('pgSecret').value });
        document.getElementById('pgSaveResult').innerHTML = '<span class="text-success"><i class="fas fa-check-circle"></i> 등록 성공</span>';
        loadPGConfigs();
    } catch (e) { document.getElementById('pgSaveResult').innerHTML = `<span class="text-danger">${escapeHtml(e.message)}</span>`; }
}

async function testPG(mid, configId) {
    const el = document.getElementById(`pgTestResult${configId}`);
    el.innerHTML = '<span class="spinner-border spinner-border-sm text-warning"></span>';
    try {
        const res = await apiPost(`/api/admin/merchants/${mid}/pg-test?config_id=${configId}`, {});
        el.innerHTML = res.success ? `<span class="text-success ms-1"><i class="fas fa-check-circle"></i></span>` : `<span class="text-danger ms-1"><i class="fas fa-times-circle"></i></span>`;
        loadPGConfigs();
    } catch (e) { el.innerHTML = `<span class="text-danger ms-1">${escapeHtml(e.message)}</span>`; }
}

async function showPGConfig(mid) { navigate('admin-pg'); setTimeout(() => { const sel = document.getElementById('pgMerchant'); if (sel) { sel.value = mid; loadPGConfigs(); } }, 500); }

async function loadAdminTerminals(c, t) {
    t.textContent = '단말기 관리';
    const terminals = await apiGet('/api/admin/terminals');
    const activeCnt = terminals.filter(d => d.is_active).length;
    const usedCnt = terminals.filter(d => d.transaction_count > 0).length;

    const rows = terminals.map(d => `<tr>
        <td>${d.id}</td>
        <td class="fw-bold">${escapeHtml(d.merchant_name)}</td>
        <td><code>${escapeHtml(d.terminal_serial)}</code></td>
        <td>${d.transaction_count.toLocaleString()}건</td>
        <td>${d.last_transaction_at ? formatDate(d.last_transaction_at) : '<span class="text-muted">거래 없음</span>'}</td>
        <td style="font-size:.82rem">${escapeHtml(d.memo || '-')}</td>
        <td>${d.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-danger">비활성</span>'}</td>
    </tr>`).join('');

    c.innerHTML = `
    <div class="row g-3 mb-3">
        <div class="col-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-primary">${terminals.length}</div><small class="text-muted">전체 단말기</small>
        </div></div></div>
        <div class="col-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-success">${activeCnt}</div><small class="text-muted">활성</small>
        </div></div></div>
        <div class="col-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-info">${usedCnt}</div><small class="text-muted">거래 발생</small>
        </div></div></div>
    </div>
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-tablet-alt me-2"></i>단말기 목록</h5>
        <span class="badge bg-secondary" style="font-size:.68rem"><i class="fas fa-lock me-1"></i>API 키는 해시로만 보관되어 조회할 수 없습니다</span>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm align-middle">
            <thead><tr><th>ID</th><th>가맹점</th><th>시리얼</th><th>누적 결제</th><th>최근 결제</th><th>메모</th><th>상태</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="7" class="text-center text-muted py-4">등록된 단말기가 없습니다</td></tr>'}</tbody>
        </table></div>
    </div></div>`;
}

async function loadAdminTransactions(c, t) {
    t.textContent = '전체 결제 내역';
    const merchants = await apiGet('/api/admin/merchants');
    let merchOpts = '<option value="">전체 가맹점</option>' + merchants.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');

    c.innerHTML = `
    <div class="card data-card mb-3">
        <div class="card-body py-2 px-3">
            <div class="row g-2 align-items-end">
                <div class="col-md-3"><label class="form-label small mb-1">가맹점</label><select class="form-select form-select-sm" id="txFilterMerch">${merchOpts}</select></div>
                <div class="col-md-2"><label class="form-label small mb-1">시작일</label><input type="date" class="form-control form-control-sm" id="txFilterFrom"></div>
                <div class="col-md-2"><label class="form-label small mb-1">종료일</label><input type="date" class="form-control form-control-sm" id="txFilterTo"></div>
                <div class="col-md-2"><label class="form-label small mb-1">정렬</label><select class="form-select form-select-sm" id="txFilterLimit"><option value="50">50건</option><option value="100" selected>100건</option><option value="200">200건</option><option value="500">500건</option></select></div>
                <div class="col-md-3 d-flex gap-1">
                    <button class="btn btn-primary btn-sm flex-fill" onclick="reloadAdminTransactions()"><i class="fas fa-search me-1"></i>조회</button>
                    <button class="btn btn-outline-secondary btn-sm" onclick="resetTxFilters()"><i class="fas fa-undo"></i></button>
                </div>
            </div>
        </div>
    </div>
    <div class="row g-3 mb-3" id="txSummaryRow"></div>
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-receipt me-2"></i>결제 내역</h5>
        <span class="badge bg-primary" id="txCountBadge">-</span>
    </div><div class="card-body" id="txTableBody">${adpayLoadingMarkup()}</div></div>`;

    reloadAdminTransactions();
}

async function reloadAdminTransactions() {
    const mid = document.getElementById('txFilterMerch')?.value || '';
    const from = document.getElementById('txFilterFrom')?.value || '';
    const to = document.getElementById('txFilterTo')?.value || '';
    const limit = document.getElementById('txFilterLimit')?.value || '100';

    let url = `/api/admin/transactions?limit=${limit}`;
    if (mid) url += `&merchant_id=${mid}`;
    if (from) url += `&date_from=${from}`;
    if (to) url += `&date_to=${to}`;

    try {
        const data = await apiGet(url);
        const txns = data.transactions || data;
        const totalCount = data.total_count || txns.length;
        const totalAmount = data.total_amount || 0;

        document.getElementById('txCountBadge').textContent = `${totalCount}건`;

        // Summary cards
        document.getElementById('txSummaryRow').innerHTML = `
            <div class="col-md-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-primary">${totalCount.toLocaleString()}</div><small class="text-muted">조회 건수</small>
            </div></div></div>
            <div class="col-md-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-success">${formatMoney(totalAmount)}</div><small class="text-muted">합계 금액</small>
            </div></div></div>
            <div class="col-md-4"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-info">${totalCount > 0 ? formatMoney(Math.round(totalAmount/totalCount)) : '0'}</div><small class="text-muted">평균 결제액</small>
            </div></div></div>`;

        document.getElementById('txTableBody').innerHTML = `
            <div class="table-responsive"><table class="table table-hover table-sm">
                <thead><tr><th>ID</th><th>가맹점</th><th>금액</th><th>할부</th><th>카드</th><th>직원</th><th>승인번호</th><th>결제일시</th></tr></thead>
                <tbody>${txns.length ? txns.map(tx => `<tr>
                    <td>${tx.id}</td><td>${escapeHtml(tx.merchant_name || tx.merchant_id)}</td><td class="fw-bold">${formatMoney(tx.amount)}</td>
                    <td>${tx.installment_months||'일시불'}</td><td>${escapeHtml(tx.card_brand||'-')}</td>
                    <td>${escapeHtml(tx.staff_name)||'<span class="text-muted">사장님</span>'}</td><td><code>${escapeHtml(tx.approval_code||'-')}</code></td>
                    <td>${formatDate(tx.created_at)}</td>
                </tr>`).join('') : '<tr><td colspan="8" class="text-center text-muted py-4">조건에 맞는 결제 내역이 없습니다</td></tr>'}</tbody>
            </table></div>`;
    } catch(e) {
        document.getElementById('txTableBody').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function resetTxFilters() {
    document.getElementById('txFilterMerch').value = '';
    document.getElementById('txFilterFrom').value = '';
    document.getElementById('txFilterTo').value = '';
    document.getElementById('txFilterLimit').value = '100';
    reloadAdminTransactions();
}

async function loadAdminSettlements(c, t) {
    t.textContent = '정산 관리';
    const merchants = await apiGet('/api/admin/merchants');
    const settlements = await apiGet('/api/admin/settlements');
    let merchOpts = merchants.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    c.innerHTML = `<div class="row g-4">
        <div class="col-md-5">
            <div class="card data-card"><div class="card-header"><h5>정산 계산</h5></div><div class="card-body">
                <div class="mb-3"><label class="form-label">가맹점</label><select class="form-select" id="settleMerch">${merchOpts}</select></div>
                <div class="mb-3"><label class="form-label">시작일</label><input type="date" class="form-control" id="settleStart"></div>
                <div class="mb-3"><label class="form-label">종료일</label><input type="date" class="form-control" id="settleEnd"></div>
                <button class="btn btn-primary w-100" onclick="calcSettlement()"><i class="fas fa-calculator me-1"></i>정산 계산</button>
                <div id="settleResult" class="mt-3"></div>
            </div></div>
        </div>
        <div class="col-md-7">
            <div class="card data-card"><div class="card-header"><h5>정산 내역</h5></div><div class="card-body">
                <div class="table-responsive"><table class="table table-sm">
                    <thead><tr><th>ID</th><th>가맹점</th><th>기간</th><th>총매출</th>
                        <th>PG수수료<br><small class="text-muted fw-normal">(부가세 포함)</small></th>
                        <th>커미션</th><th>순매출</th></tr></thead>
                    <tbody>${settlements.map(s => `<tr>
                        <td>${s.id}</td><td class="fw-bold">${escapeHtml(s.merchant_name || s.merchant_id)}</td>
                        <td>${s.period_start.split(' ')[0]} ~ ${s.period_end.split(' ')[0]}</td>
                        <td>${formatMoney(s.gross_amount)}</td><td class="text-danger">${formatMoney(s.pg_fee_amount)}</td>
                        <td class="text-danger">${formatMoney(s.commission_amount)}</td><td class="fw-bold text-primary">${formatMoney(s.net_amount)}</td>
                    </tr>`).join('') || '<tr><td colspan="7" class="text-muted text-center py-3">없음</td></tr>'}</tbody>
                </table></div>
            </div></div>
        </div>
    </div>`;
}

async function calcSettlement() {
    const mid = document.getElementById('settleMerch').value;
    const start = document.getElementById('settleStart').value;
    const end = document.getElementById('settleEnd').value;
    if (!start || !end) { alert('기간을 선택하세요'); return; }
    try {
        const res = await apiPost(`/api/admin/settlements/calculate?merchant_id=${mid}&period_start=${start}&period_end=${end}`, {});
        const rateNote = res.pg_fee_rate != null
            ? `<br><small class="text-muted">PG수수료율 ${fmtRateExclVat(res.pg_fee_rate)} → 실제 적용 ${(((res.pg_fee_rate_with_vat ?? applyVat(res.pg_fee_rate)))*100).toFixed(2)}% (수수료 금액은 부가세 포함)</small>`
            : '';
        document.getElementById('settleResult').innerHTML = `<div class="alert alert-success"><strong>정산 완료!</strong><br>총매출: ${formatMoney(res.gross_amount)} | PG수수료: ${formatMoney(res.pg_fee_amount)}<br>커미션: ${formatMoney(res.commission_amount)} | 순매출: <strong>${formatMoney(res.net_amount)}</strong> | ${res.transactions_count}건${rateNote}</div>`;
        navigate('admin-settlements');
    } catch (e) { document.getElementById('settleResult').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}

// ─── 수수료 기본 설정 (전역/가맹점별/영업관리자별) ──────────

// 부가세(VAT 10%) — 저장/입력되는 수수료율은 부가세 별도 기준이며,
// 실제 적용 수수료율은 입력값 × 1.1 이다. (백엔드 settlement_service.apply_vat 와 동일)
const VAT_MULTIPLIER = 1.1;
const VAT_NOTICE = '입력값은 부가세 별도 기준이며, 실제 적용율은 입력값 × 1.1입니다.';

/** 부가세 별도 수수료율 → 실제 적용 수수료율 */
function applyVat(rate) { return (Number(rate) || 0) * VAT_MULTIPLIER; }

/** '3.00% (부가세 별도)' */
function fmtRateExclVat(rate) { return `${((Number(rate) || 0) * 100).toFixed(2)}% (부가세 별도)`; }

/** '3.00% (부가세 별도) → 실제 적용: 3.30%' */
function fmtRateWithVat(rate) {
    return `${fmtRateExclVat(rate)} → 실제 적용: ${(applyVat(rate) * 100).toFixed(2)}%`;
}

async function loadAdminFeeSettings(c, t) {
    t.textContent = '수수료 기본 설정';

    const [settings, merchants, salesManagers] = await Promise.all([
        apiGet('/api/admin/fee-settings'),
        apiGet('/api/admin/merchants'),
        apiGet('/api/admin/sales-managers'),
    ]);

    const pRate = ((settings.merchant_fee_rate - settings.pg_fee_rate) * 100).toFixed(2);
    const cRate = (settings.company_profit_rate * 100).toFixed(2);
    const sim = settings.simulation;

    c.innerHTML = `
    <!-- 수수료 체계 안내 -->
    <div class="alert alert-info mb-3">
        <i class="fas fa-info-circle me-2"></i><strong>새 수수료 구조:</strong>
        가맹점 부과 수수료 − PG 비용 = 플랫폼 수익 / 플랫폼 수익 − 영업 커미션 = 회사 순수익
    </div>

    <!-- 부가세 안내 -->
    <div class="alert alert-warning mb-3">
        <i class="fas fa-percent me-2"></i><strong>부가세(VAT 10%) 별도:</strong>
        ${VAT_NOTICE}
        <div class="small mt-1">
            예) 가맹점 수수료 ${fmtRateWithVat(settings.merchant_fee_rate)}
            &nbsp;/&nbsp; PG 수수료 ${fmtRateWithVat(settings.pg_fee_rate)}
        </div>
        <div class="small text-muted mt-1">
            영업 커미션율은 부가세 적용 대상이 아니며 입력값이 그대로 적용됩니다.
        </div>
    </div>

    <!-- 전역 기본 수수료 설정 -->
    <div class="card data-card mb-3">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-globe me-2"></i>전역 기본 수수료 설정</h5></div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-md-4">
                    <label class="form-label fw-bold">가맹점 부과 수수료율 <span class="text-danger">*</span>
                        <span class="badge bg-warning text-dark ms-1">부가세 별도</span>
                    </label>
                    <div class="input-group">
                        <input type="number" class="form-control" id="gs_merchant_fee"
                            value="${(settings.merchant_fee_rate*100).toFixed(2)}" step="0.1" min="0" max="30"
                            oninput="updateFeePreview()">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted d-block">가맹점이 내는 총 수수료</small>
                    <small class="text-primary fw-bold" id="gs_merchant_fee_vat">${fmtRateWithVat(settings.merchant_fee_rate)}</small>
                </div>
                <div class="col-md-4">
                    <label class="form-label fw-bold">PG사 수수료율 <span class="text-danger">*</span>
                        <span class="badge bg-warning text-dark ms-1">부가세 별도</span>
                    </label>
                    <div class="input-group">
                        <input type="number" class="form-control" id="gs_pg_fee"
                            value="${(settings.pg_fee_rate*100).toFixed(2)}" step="0.1" min="0" max="30"
                            oninput="updateFeePreview()">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted d-block">PG사에 내는 실비용</small>
                    <small class="text-primary fw-bold" id="gs_pg_fee_vat">${fmtRateWithVat(settings.pg_fee_rate)}</small>
                </div>
                <div class="col-md-4">
                    <label class="form-label fw-bold">영업 커미션율 <span class="text-danger">*</span></label>
                    <div class="input-group">
                        <input type="number" class="form-control" id="gs_sales_comm"
                            value="${(settings.sales_commission_rate*100).toFixed(2)}" step="0.1" min="0" max="30"
                            oninput="updateFeePreview()">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted d-block">플랫폼 수익 중 영업관리자 몫</small>
                    <small class="text-muted">부가세 미적용 (입력값 그대로 적용)</small>
                </div>
            </div>
            <div class="alert alert-light border small mt-2 mb-0">
                <i class="fas fa-info-circle text-primary me-1"></i>${VAT_NOTICE}
                <div class="mt-1">
                    <i class="fas fa-user-slash text-secondary me-1"></i>영업관리자가 배정되지 않은 가맹점은
                    <strong>영업 커미션 0%</strong>가 적용되며, 플랫폼 수익 전액이 회사 순수익이 됩니다.
                    <span class="text-muted">(위 영업 커미션율은 배정된 가맹점에만 적용)</span>
                </div>
            </div>
            <!-- 자동계산 미리보기 -->
            <div class="row g-2 mt-2 align-items-center">
                <div class="col-auto">
                    <span class="badge bg-secondary fs-6" id="gs_platform_rate">${pRate}%</span>
                    <small class="text-muted ms-1">플랫폼 수익률</small>
                </div>
                <div class="col-auto">
                    <i class="fas fa-arrow-right text-muted"></i>
                </div>
                <div class="col-auto">
                    <span class="badge bg-success fs-6" id="gs_company_rate">${cRate}%</span>
                    <small class="text-muted ms-1">회사 순수익률 (자동계산)</small>
                </div>
            </div>
            <!-- 시뮬레이션 -->
            <div class="mt-3 p-3 bg-light rounded">
                <div class="fw-bold mb-2">💡 10,000원 결제 시뮬레이션
                    <span class="badge bg-secondary ms-1">수수료 금액은 부가세 포함</span>
                </div>
                <div class="row g-2 text-center" id="gs_simulation">
                    ${_feeSimRow(sim)}
                </div>
                <small class="text-muted d-block mt-2">
                    가맹점 수수료 ${fmtRateWithVat(settings.merchant_fee_rate)}
                    &nbsp;·&nbsp; PG 비용 ${fmtRateWithVat(settings.pg_fee_rate)}
                </small>
            </div>
            <div class="mt-3">
                <button class="btn btn-primary" onclick="saveGlobalFeeSettings()">
                    <i class="fas fa-save me-1"></i>전역 설정 저장
                </button>
            </div>
        </div>
    </div>

    <!-- 가맹점별 수수료 오버라이드 -->
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-store me-2"></i>가맹점별 수수료 오버라이드</h5>
            <small class="text-muted">설정 없으면 전역값 사용</small>
        </div>
        <div class="card-body">
            <div class="alert alert-light border small">
                <i class="fas fa-percent text-warning me-1"></i>${VAT_NOTICE}
            </div>
            <div class="table-responsive">
                <table class="table table-sm align-middle">
                    <thead class="table-light">
                        <tr>
                            <th>가맹점</th>
                            <th>가맹점 수수료율 <small class="text-muted fw-normal">(부가세 별도)</small></th>
                            <th>PG 비용율 <small class="text-muted fw-normal">(부가세 별도)</small></th>
                            <th>실제 적용율</th>
                            <th>오버라이드 여부</th>
                            <th>작업</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${merchants.map(m => `<tr>
                            <td><span class="fw-bold">${escapeHtml(m.name)}</span></td>
                            <td>
                                <div class="input-group input-group-sm" style="width:120px">
                                    <input type="number" class="form-control" id="mfr_${m.id}"
                                        placeholder="전역 ${(settings.merchant_fee_rate*100).toFixed(1)}%"
                                        step="0.1" min="0" max="30"
                                        oninput="updateMerchantFeeVatHint(${m.id})">
                                    <span class="input-group-text">%</span>
                                </div>
                            </td>
                            <td>
                                <div class="input-group input-group-sm" style="width:120px">
                                    <input type="number" class="form-control" id="pgr_${m.id}"
                                        placeholder="전역 ${(settings.pg_fee_rate*100).toFixed(1)}%"
                                        step="0.1" min="0" max="30"
                                        oninput="updateMerchantFeeVatHint(${m.id})">
                                    <span class="input-group-text">%</span>
                                </div>
                            </td>
                            <td><small class="text-primary fw-bold" id="vat_hint_${m.id}">확인 중...</small></td>
                            <td><span class="badge bg-secondary" id="ovr_badge_${m.id}">확인 중...</span></td>
                            <td>
                                <button class="btn btn-sm btn-primary me-1" onclick="saveMerchantFeeOverride(${m.id})">
                                    <i class="fas fa-save"></i> 저장
                                </button>
                                <button class="btn btn-sm btn-outline-secondary" onclick="resetMerchantFeeOverride(${m.id})">
                                    초기화
                                </button>
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 영업관리자별 커미션 오버라이드 -->
    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-user-tie me-2"></i>영업관리자별 커미션 오버라이드</h5>
            <small class="text-muted">설정 없으면 전역값 사용</small>
        </div>
        <div class="card-body">
            ${salesManagers.length === 0
                ? '<p class="text-muted">등록된 영업관리자가 없습니다.</p>'
                : `<div class="table-responsive"><table class="table table-sm align-middle">
                    <thead class="table-light">
                        <tr><th>담당자</th><th>커미션율 오버라이드</th><th>오버라이드 여부</th><th>작업</th></tr>
                    </thead>
                    <tbody>
                        ${salesManagers.map(u => `<tr>
                            <td><span class="fw-bold">${escapeHtml(u.name)}</span><br><small class="text-muted">${escapeHtml(u.email)}</small></td>
                            <td>
                                <div class="input-group input-group-sm" style="width:130px">
                                    <input type="number" class="form-control" id="scr_${u.id}"
                                        placeholder="전역 ${(settings.sales_commission_rate*100).toFixed(1)}%"
                                        step="0.1" min="0" max="30">
                                    <span class="input-group-text">%</span>
                                </div>
                            </td>
                            <td><span class="badge bg-secondary" id="scr_badge_${u.id}">확인 중...</span></td>
                            <td>
                                <button class="btn btn-sm btn-primary me-1" onclick="saveSalesCommissionOverride(${u.id})">
                                    <i class="fas fa-save"></i> 저장
                                </button>
                                <button class="btn btn-sm btn-outline-secondary" onclick="resetSalesCommissionOverride(${u.id})">
                                    초기화
                                </button>
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table></div>`}
        </div>
    </div>`;

    // 오버라이드 현황 비동기 로드
    merchants.forEach(m => _loadMerchantFeeOverride(m.id));
    salesManagers.forEach(u => _loadSalesCommissionOverride(u.id));
}

function _feeSimRow(sim) {
    const items = [
        { label: '결제액', val: sim.sample_amount, cls: 'text-dark' },
        { label: '가맹점 수수료 (VAT 포함)', val: `-${sim.merchant_fee}`, cls: 'text-danger' },
        { label: 'PG 비용 (VAT 포함)', val: `-${sim.pg_cost}`, cls: 'text-warning' },
        { label: '플랫폼 수익', val: sim.platform_income, cls: 'text-primary' },
        { label: '영업 커미션', val: `-${sim.sales_commission}`, cls: 'text-secondary' },
        { label: '회사 순수익', val: sim.company_profit, cls: 'text-success fw-bold' },
        { label: '가맹점 수령', val: sim.net_payout, cls: 'text-info fw-bold' },
    ];
    return items.map(i => `
        <div class="col">
            <div class="p-2 bg-white rounded border">
                <div class="${i.cls}">${typeof i.val === 'number' ? i.val.toLocaleString() : i.val}원</div>
                <small class="text-muted">${i.label}</small>
            </div>
        </div>`).join('');
}

function updateFeePreview() {
    const mfr = parseFloat(document.getElementById('gs_merchant_fee')?.value || 0) / 100;
    const pgr = parseFloat(document.getElementById('gs_pg_fee')?.value || 0) / 100;
    const scr = parseFloat(document.getElementById('gs_sales_comm')?.value || 0) / 100;
    // 플랫폼/회사 수익률은 기존과 동일하게 부가세 별도 기준으로 표시한다.
    const platform = mfr - pgr;
    const company = platform - scr;
    const pEl = document.getElementById('gs_platform_rate');
    const cEl = document.getElementById('gs_company_rate');
    if (pEl) pEl.textContent = (platform * 100).toFixed(2) + '%';
    if (cEl) {
        cEl.textContent = (company * 100).toFixed(2) + '%';
        cEl.className = company < 0 ? 'badge bg-danger fs-6' : 'badge bg-success fs-6';
    }
    // 부가세 별도 → 실제 적용율 미리보기
    const mfrVatEl = document.getElementById('gs_merchant_fee_vat');
    const pgrVatEl = document.getElementById('gs_pg_fee_vat');
    if (mfrVatEl) mfrVatEl.textContent = fmtRateWithVat(mfr);
    if (pgrVatEl) pgrVatEl.textContent = fmtRateWithVat(pgr);
}

async function saveGlobalFeeSettings() {
    const mfr = parseFloat(document.getElementById('gs_merchant_fee').value) / 100;
    const pgr = parseFloat(document.getElementById('gs_pg_fee').value) / 100;
    const scr = parseFloat(document.getElementById('gs_sales_comm').value) / 100;
    if (isNaN(mfr) || isNaN(pgr) || isNaN(scr)) { alert('모든 수수료율을 입력해주세요.'); return; }
    const platform = mfr - pgr;
    if (scr > platform + 0.00001) {
        alert(`영업 커미션율(${(scr*100).toFixed(2)}%)이 플랫폼 수익률(${(platform*100).toFixed(2)}%)을 초과합니다.`);
        return;
    }
    try {
        await apiPut('/api/admin/fee-settings', {
            merchant_fee_rate: mfr, pg_fee_rate: pgr, sales_commission_rate: scr,
        });
        alert('전역 수수료 설정이 저장되었습니다.\n\n'
            + `가맹점 수수료: ${fmtRateWithVat(mfr)}\n`
            + `PG 수수료: ${fmtRateWithVat(pgr)}\n`
            + `영업 커미션: ${(scr*100).toFixed(2)}% (부가세 미적용)`);
        navigate('admin-fee-settings');
    } catch(e) { alert('저장 실패: ' + e.message); }
}

/** 가맹점별 오버라이드 행의 "실제 적용율" 힌트를 갱신한다 (입력값 × 1.1). */
function updateMerchantFeeVatHint(mid, effective) {
    const hint = document.getElementById(`vat_hint_${mid}`);
    if (!hint) return;
    const mfrVal = document.getElementById(`mfr_${mid}`)?.value;
    const pgrVal = document.getElementById(`pgr_${mid}`)?.value;
    // 입력값이 있으면 입력값 기준, 없으면 서버가 알려준 유효 수수료율(전역 포함) 기준
    const mfr = mfrVal ? parseFloat(mfrVal) / 100 : effective?.merchant_fee_rate;
    const pgr = pgrVal ? parseFloat(pgrVal) / 100 : effective?.pg_fee_rate;
    if (mfr == null && pgr == null) { hint.textContent = '-'; return; }
    const parts = [];
    if (mfr != null) parts.push(`가맹점 ${(applyVat(mfr)*100).toFixed(2)}%`);
    if (pgr != null) parts.push(`PG ${(applyVat(pgr)*100).toFixed(2)}%`);
    hint.textContent = parts.join(' / ');
    hint.title = VAT_NOTICE;
}

async function _loadMerchantFeeOverride(mid) {
    try {
        const data = await apiGet(`/api/admin/merchants/${mid}/fee-override`);
        const badge = document.getElementById(`ovr_badge_${mid}`);
        if (!badge) return;
        if (data.has_override) {
            badge.className = 'badge bg-warning text-dark';
            badge.textContent = '개별 설정';
            const mfrEl = document.getElementById(`mfr_${mid}`);
            const pgrEl = document.getElementById(`pgr_${mid}`);
            if (mfrEl && data.merchant_fee_rate != null) mfrEl.value = (data.merchant_fee_rate * 100).toFixed(2);
            if (pgrEl && data.pg_fee_rate != null) pgrEl.value = (data.pg_fee_rate * 100).toFixed(2);
        } else {
            badge.className = 'badge bg-secondary';
            badge.textContent = '전역 사용';
        }
        // 실제 적용율(부가세 포함) 힌트 — 입력값이 없으면 유효 수수료율 기준으로 표시
        updateMerchantFeeVatHint(mid, {
            merchant_fee_rate: data.effective_merchant_fee_rate,
            pg_fee_rate: data.effective_pg_fee_rate,
        });
    } catch(_) {}
}

async function saveMerchantFeeOverride(mid) {
    const mfrVal = document.getElementById(`mfr_${mid}`).value;
    const pgrVal = document.getElementById(`pgr_${mid}`).value;
    const body = {};
    if (mfrVal) body.merchant_fee_rate = parseFloat(mfrVal) / 100;
    if (pgrVal) body.pg_fee_rate = parseFloat(pgrVal) / 100;
    if (!Object.keys(body).length) { alert('변경할 수수료율을 입력해주세요.'); return; }
    try {
        const res = await apiPut(`/api/admin/merchants/${mid}/fee-override`, body);
        const applied = [
            res.merchant_fee_rate != null ? `가맹점 ${fmtRateWithVat(res.merchant_fee_rate)}` : null,
            res.pg_fee_rate != null ? `PG ${fmtRateWithVat(res.pg_fee_rate)}` : null,
        ].filter(Boolean).join('\n');
        alert(`가맹점 수수료 오버라이드가 저장되었습니다.\n\n${applied}`);
        _loadMerchantFeeOverride(mid);
    } catch(e) { alert('저장 실패: ' + e.message); }
}

async function resetMerchantFeeOverride(mid) {
    if (!confirm('이 가맹점의 수수료 오버라이드를 삭제하고 전역값을 사용하시겠습니까?')) return;
    try {
        await apiPut(`/api/admin/merchants/${mid}/fee-override`, {});
        document.getElementById(`mfr_${mid}`).value = '';
        document.getElementById(`pgr_${mid}`).value = '';
        _loadMerchantFeeOverride(mid);
    } catch(e) { alert('초기화 실패: ' + e.message); }
}

async function _loadSalesCommissionOverride(uid) {
    try {
        const data = await apiGet(`/api/admin/sales/${uid}/commission-override`);
        const badge = document.getElementById(`scr_badge_${uid}`);
        if (!badge) return;
        if (data.has_override) {
            badge.className = 'badge bg-warning text-dark';
            badge.textContent = '개별 설정';
            const scrEl = document.getElementById(`scr_${uid}`);
            if (scrEl && data.commission_rate != null) scrEl.value = (data.commission_rate * 100).toFixed(2);
        } else {
            badge.className = 'badge bg-secondary';
            badge.textContent = '전역 사용';
        }
    } catch(_) {}
}

async function saveSalesCommissionOverride(uid) {
    const val = document.getElementById(`scr_${uid}`).value;
    if (!val) { alert('커미션율을 입력해주세요.'); return; }
    const rate = parseFloat(val) / 100;
    try {
        await apiPut(`/api/admin/sales/${uid}/commission-override`, { commission_rate: rate });
        alert('영업관리자 커미션 오버라이드가 저장되었습니다.');
        _loadSalesCommissionOverride(uid);
    } catch(e) { alert('저장 실패: ' + e.message); }
}

async function resetSalesCommissionOverride(uid) {
    if (!confirm('이 영업관리자의 커미션 오버라이드를 삭제하고 전역값을 사용하시겠습니까?')) return;
    try {
        await apiPut(`/api/admin/sales/${uid}/commission-override`, { commission_rate: null });
        document.getElementById(`scr_${uid}`).value = '';
        _loadSalesCommissionOverride(uid);
    } catch(e) { alert('초기화 실패: ' + e.message); }
}

// ─────────────────────────────────────────────────────────────

async function loadAdminFeePolicies(c, t) {
    t.textContent = '수수료 정책';

    // 통합 수수료 현황 API (가맹점 + 수수료 + 영업관리자 한번에)
    const overview = await apiGet('/api/admin/fee-policy-overview');
    const salesManagers = await apiGet('/api/admin/sales-managers');

    const salesOpts = salesManagers.map(u => `<option value="${u.id}">${escapeHtml(u.name)} (${escapeHtml(u.email)})</option>`).join('');

    // 통계 요약
    const totalMerchants = overview.length;
    const withSales = overview.filter(o => o.has_sales_manager).length;
    const withoutSales = totalMerchants - withSales;
    const customFee = overview.filter(o => o.has_fee_policy).length;

    let rows = overview.map(o => {
        const salesBadge = o.has_sales_manager
            ? `<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">
                <i class="fas fa-user-tie me-1"></i>${escapeHtml(o.sales_manager_name)}
                <span class="ms-1 fw-bold">${o.commission_rate_pct}%</span>
               </span>`
            : `<span class="badge bg-secondary bg-opacity-10 text-secondary">미배정</span>`;

        const simBreakdown = o.has_sales_manager
            ? `<small class="d-block text-muted">PG ${o.sim_pg_fee.toLocaleString()}원 = ADPAY ${o.sim_platform.toLocaleString()}원 + 영업 <span class="text-primary fw-bold">${o.sim_commission.toLocaleString()}원</span></small>`
            : `<small class="d-block text-muted">PG ${o.sim_pg_fee.toLocaleString()}원 = ADPAY ${o.sim_platform.toLocaleString()}원 (영업 미배정)</small>`;

        return `<tr>
            <td>${o.merchant_id}</td>
            <td>
                <div class="fw-bold">${escapeHtml(o.merchant_name)}</div>
                ${o.category ? `<small class="text-muted">${escapeHtml(o.category)}</small>` : ''}
            </td>
            <td class="text-muted">${(o.pg_fee_rate_excl_vat_pct ?? o.pg_fee_rate_pct).toFixed(2)}%
                <small class="d-block text-muted">부가세 별도</small></td>
            <td class="fw-bold text-primary">${(o.pg_fee_rate_with_vat_pct ?? applyVat(o.pg_fee_rate) * 100).toFixed(2)}%
                <small class="d-block text-muted fw-normal">부가세 포함 (× 1.1)</small></td>
            <td>${salesBadge}</td>
            <td>
                <div>10,000원 → <strong class="text-success">${o.sim_net.toLocaleString()}원</strong></div>
                ${simBreakdown}
            </td>
            <td>
                <div class="d-flex gap-1">
                    <div class="input-group input-group-sm" style="width:150px">
                        <input type="number" class="form-control" id="feeRate${o.merchant_id}" value="${o.pg_fee_rate_pct}"
                            step="0.1" min="0" max="10" oninput="updateFeePolicyVatHint(${o.merchant_id})">
                        <span class="input-group-text">%</span>
                        <button class="btn btn-primary" onclick="saveFeePolicy(${o.merchant_id})" title="수수료 저장"><i class="fas fa-save"></i></button>
                    </div>
                </div>
                <small class="text-primary fw-bold" id="feeRateVat${o.merchant_id}">${fmtRateWithVat(o.pg_fee_rate)}</small>
            </td>
            <td>
                ${o.has_sales_manager
                    ? `<div class="d-flex gap-1 align-items-center">
                        <div class="input-group input-group-sm" style="width:140px">
                            <input type="number" class="form-control" id="commRate${o.merchant_id}" value="${o.commission_rate_pct}" step="0.1" min="0" max="3.5">
                            <span class="input-group-text">%</span>
                            <button class="btn btn-success" onclick="updateSalesCommission(${o.assignment_id}, ${o.merchant_id})" title="커미션 저장"><i class="fas fa-save"></i></button>
                        </div>
                        <button class="btn btn-sm btn-outline-danger" onclick="removeSalesFromPolicy(${o.assignment_id})" title="영업관리자 해제"><i class="fas fa-unlink"></i></button>
                       </div>`
                    : `<button class="btn btn-sm btn-outline-primary" onclick="showAssignSalesModal(${o.merchant_id}, '${escapeJsAttr(o.merchant_name)}')">
                        <i class="fas fa-user-plus me-1"></i>배정
                       </button>`
                }
            </td>
        </tr>`;
    }).join('');

    c.innerHTML = `
    <!-- 수수료 체계 안내 -->
    <div class="alert alert-info mb-3">
        <div class="d-flex align-items-start">
            <i class="fas fa-info-circle me-3 mt-1 fs-5"></i>
            <div>
                <h6 class="fw-bold mb-1">수수료 체계 안내</h6>
                <ul class="mb-0 small">
                    <li><strong>부가세(VAT 10%) 별도:</strong> ${VAT_NOTICE}
                        <small class="text-muted">(예: 5.00% (부가세 별도) = 실제 5.50% 적용)</small></li>
                    <li><strong>PG 수수료:</strong> 결제 금액 × 설정 수수료율 × 1.1 <strong>(부가세 포함 금액)</strong></li>
                    <li><strong>구성:</strong> PG 수수료 = <strong>영업 몫</strong> + <strong>ADPAY 플랫폼 몫</strong>
                        <small class="text-muted">(영업 몫 = 결제액 × 영업관리자 커미션율, 부가세 미적용)</small></li>
                    <li><strong>분배가능액:</strong> 결제액 − PG 수수료 → 사장님 ↔ 직원 분배율(share_rate)로 분배</li>
                    <li><strong>정산 예시:</strong> 10,000원 결제, PG 5.00% (부가세 별도) / 영업 1%
                        → 실제 적용 5.50% → PG수수료 <strong>550원</strong>(영업 100원 + ADPAY 450원)
                        → 분배가능액 <strong>9,450원</strong></li>
                    <li><strong>영업관리자 수익:</strong> PG 수수료 내에서 배정 (이 페이지에서 직접 관리 가능)</li>
                </ul>
            </div>
        </div>
    </div>

    <!-- 요약 통계 -->
    <div class="row g-3 mb-3">
        <div class="col-md-3">
            <div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
                <div class="fs-3 fw-bold text-primary">${totalMerchants}</div>
                <small class="text-muted">전체 가맹점</small>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
                <div class="fs-3 fw-bold text-success">${withSales}</div>
                <small class="text-muted">영업관리자 배정</small>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
                <div class="fs-3 fw-bold text-warning">${withoutSales}</div>
                <small class="text-muted">영업관리자 미배정</small>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
                <div class="fs-3 fw-bold text-info">${customFee}</div>
                <small class="text-muted">커스텀 수수료</small>
            </div></div>
        </div>
    </div>

    <!-- 메인 테이블 -->
    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-percentage me-2"></i>가맹점별 수수료 · 영업관리자 통합 관리</h5>
            <div>
                <button class="btn btn-sm btn-outline-secondary me-1" onclick="navigate('admin-sales-assign')"><i class="fas fa-handshake me-1"></i>영업관리자 연결 관리</button>
            </div>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover table-sm align-middle">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            <th>가맹점</th>
                            <th>설정 수수료율<br><small class="text-muted">(부가세 별도)</small></th>
                            <th>실제 적용 수수료율<br><small class="text-muted">(부가세 포함)</small></th>
                            <th>영업관리자</th>
                            <th>정산 시뮬레이션<br><small class="text-muted">(1만원 기준, 부가세 포함)</small></th>
                            <th>PG 수수료 변경<br><small class="text-muted">(부가세 별도 입력)</small></th>
                            <th>영업관리자 커미션</th>
                        </tr>
                    </thead>
                    <tbody>${rows || '<tr><td colspan="8" class="text-muted text-center py-3">등록된 가맹점이 없습니다.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 영업관리자 배정 모달 -->
    <div class="modal fade" id="assignSalesModal" tabindex="-1">
        <div class="modal-dialog modal-sm">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-user-plus me-2"></i>영업관리자 배정</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p class="small text-muted mb-2">가맹점: <strong id="assignModalMerchantName"></strong></p>
                    <input type="hidden" id="assignModalMerchantId">
                    <div class="mb-3">
                        <label class="form-label fw-bold">영업관리자</label>
                        <select class="form-select" id="assignModalSales">${salesOpts || '<option disabled>영업관리자 없음</option>'}</select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label fw-bold">커미션율 (VAT별도)</label>
                        <div class="input-group">
                            <input type="number" class="form-control" id="assignModalRate" value="1.0" step="0.1" min="0">
                            <span class="input-group-text">%</span>
                        </div>
                        <small class="text-muted">최고관리자가 설정한 플랫폼 수익률 이내</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">메모</label>
                        <input class="form-control" id="assignModalMemo" placeholder="선택사항">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
                    <button type="button" class="btn btn-primary" onclick="confirmAssignSales()"><i class="fas fa-link me-1"></i>배정</button>
                </div>
            </div>
        </div>
    </div>`;
}

/** 수수료 정책 페이지의 PG 수수료 입력 옆 "실제 적용율" 힌트 갱신 */
function updateFeePolicyVatHint(merchantId) {
    const el = document.getElementById(`feeRateVat${merchantId}`);
    const input = document.getElementById(`feeRate${merchantId}`);
    if (!el || !input) return;
    const rate = parseFloat(input.value);
    el.textContent = isNaN(rate) ? '-' : fmtRateWithVat(rate / 100);
    el.title = VAT_NOTICE;
}

async function saveFeePolicy(merchantId) {
    try {
        const rate = parseFloat(document.getElementById(`feeRate${merchantId}`).value) / 100;
        if (rate < 0 || rate > 0.1) { alert('수수료율은 0~10% 범위에서 설정해주세요.'); return; }
        const result = await apiPost(`/api/admin/merchants/${merchantId}/fee-policy`, { pg_fee_rate: rate });
        alert(`수수료 정책 저장 완료!\nPG 수수료: ${fmtRateWithVat(rate)}\n${result.example}`);
        navigate('admin-fee-policies');
    } catch (e) { alert('저장 실패: ' + e.message); }
}

// ─── 수수료정책 페이지 내 영업관리자 관리 함수들 ──

function showAssignSalesModal(merchantId, merchantName) {
    document.getElementById('assignModalMerchantId').value = merchantId;
    document.getElementById('assignModalMerchantName').textContent = merchantName;
    document.getElementById('assignModalRate').value = '1.0';
    document.getElementById('assignModalMemo').value = '';
    new bootstrap.Modal(document.getElementById('assignSalesModal')).show();
}

async function confirmAssignSales() {
    try {
        const merchantId = parseInt(document.getElementById('assignModalMerchantId').value);
        const salesId = parseInt(document.getElementById('assignModalSales').value);
        const rate = parseFloat(document.getElementById('assignModalRate').value) / 100;
        const memo = document.getElementById('assignModalMemo').value;

        if (!salesId) { alert('영업관리자를 선택해주세요.'); return; }
        if (rate < 0) { alert('커미션율은 0% 이상으로 설정해주세요.'); return; }

        await apiPost('/api/admin/sales-assignments', {
            merchant_id: merchantId,
            sales_manager_user_id: salesId,
            commission_rate: rate,
            memo: memo || null,
        });

        bootstrap.Modal.getInstance(document.getElementById('assignSalesModal')).hide();
        alert('영업관리자 배정 완료!');
        navigate('admin-fee-policies');
    } catch (e) { alert('배정 실패: ' + e.message); }
}

async function updateSalesCommission(assignmentId, merchantId) {
    try {
        const rate = parseFloat(document.getElementById(`commRate${merchantId}`).value) / 100;
        if (rate < 0) { alert('커미션율은 0% 이상으로 설정해주세요.'); return; }
        await apiPut(`/api/admin/sales-assignments/${assignmentId}`, { commission_rate: rate });
        alert(`커미션율 저장 완료! (${(rate*100).toFixed(2)}%)`);
        navigate('admin-fee-policies');
    } catch (e) { alert('저장 실패: ' + e.message); }
}

async function removeSalesFromPolicy(assignmentId) {
    if (!confirm('이 가맹점의 영업관리자 배정을 해제하시겠습니까?')) return;
    try {
        await api(`/api/admin/sales-assignments/${assignmentId}`, { method: 'DELETE' });
        navigate('admin-fee-policies');
    } catch (e) { alert('해제 실패: ' + e.message); }
}

async function loadAdminPayouts(c, t) {
    t.textContent = '출금요청 관리';
    const payouts = await apiGet('/api/admin/payout-requests');
    const pendingCnt = payouts.filter(p => p.status === 'pending').length;
    const approvedCnt = payouts.filter(p => p.status === 'approved').length;
    const totalAmount = payouts.filter(p => p.status === 'pending').reduce((s,p) => s + p.amount, 0);

    c.innerHTML = `
    <div class="row g-3 mb-3">
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-warning">${pendingCnt}</div><small class="text-muted">대기중</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-success">${approvedCnt}</div><small class="text-muted">승인완료</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-danger">${formatMoney(totalAmount)}</div><small class="text-muted">대기 금액</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-primary">${payouts.length}</div><small class="text-muted">전체 건수</small>
        </div></div></div>
    </div>
    ${payouts.length === 0 ? `
    <div class="card data-card">
        <div class="card-body text-center py-5">
            <i class="fas fa-inbox fa-3x mb-3 text-muted" style="opacity:.3"></i>
            <p class="text-muted mb-0">출금요청 내역이 없습니다</p>
        </div>
    </div>` : `
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-money-bill-wave me-2"></i>출금요청 목록</h5>
        <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary active" onclick="filterPayoutStatus('all',this)">전체</button>
            <button class="btn btn-outline-warning" onclick="filterPayoutStatus('pending',this)">대기</button>
            <button class="btn btn-outline-success" onclick="filterPayoutStatus('approved',this)">승인</button>
            <button class="btn btn-outline-danger" onclick="filterPayoutStatus('rejected',this)">반려</button>
        </div>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm" id="payoutTable">
            <thead><tr><th>ID</th><th>요청자</th><th>역할</th><th>금액</th><th>가용잔액</th><th>은행정보</th><th>메모</th><th>상태</th><th>요청일</th><th>액션</th></tr></thead>
            <tbody>${payouts.map(p => `<tr data-status="${p.status}">
                <td>${p.id}</td><td class="fw-bold">${escapeHtml(p.requester_name) || '-'}</td><td><span class="badge bg-${p.role==='sales'?'info':p.role==='owner'?'primary':'secondary'}">${roleLabel(p.role)}</span></td>
                <td class="fw-bold">${formatMoney(p.amount)}</td>
                <td class="${(p.available_balance ?? 0) < p.amount ? 'text-danger fw-bold' : 'text-muted'}" style="font-size:.85rem">${formatMoney(p.available_balance ?? 0)}</td>
                <td style="font-size:.82rem">${escapeHtml(p.bank_info)||'-'}</td><td style="font-size:.82rem">${escapeHtml(p.memo)||'-'}</td>
                <td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td>
                <td>${p.status==='pending'?`<button class="btn btn-sm btn-success me-1" onclick="handlePayout(${p.id},'approve')"><i class="fas fa-check"></i></button><button class="btn btn-sm btn-danger" onclick="handlePayout(${p.id},'reject')"><i class="fas fa-times"></i></button>`:'-'}</td>
            </tr>`).join('')}</tbody>
        </table></div>
    </div></div>`}`;
}

function filterPayoutStatus(status, btn) {
    document.querySelectorAll('.btn-group .btn').forEach(b => { if (b.parentElement === btn.parentElement) b.classList.remove('active'); });
    btn.classList.add('active');
    document.querySelectorAll('#payoutTable tbody tr').forEach(row => {
        row.style.display = (status === 'all' || row.dataset.status === status) ? '' : 'none';
    });
}

async function handlePayout(id, action) { await apiPost(`/api/admin/payout-requests/${id}/${action}`, {}); navigate('admin-payouts'); }

async function loadAdminAdOrders(c, t) {
    t.textContent = '광고주문 관리';
    const [orders, flags, pricing] = await Promise.all([
        apiGet('/api/admin/ad/orders'),
        apiGet('/api/admin/ad-feature-flags'),
        apiGet('/api/admin/ad-pricing'),
    ]);
    const pending = orders.filter(o => o.status === 'requested' || o.status === 'reviewing').length;
    const running = orders.filter(o => o.status === 'running').length;
    const done = orders.filter(o => o.status === 'done').length;
    const masterOn = flags.ad_order_mgmt_enabled;
    const blogOn = flags.ad_blog_enabled;
    const placeOn = flags.ad_place_traffic_enabled;
    const shortsOn = flags.ad_shorts_enabled;

    c.innerHTML = `
    <!-- 광고 기능 스위치 -->
    <div class="card border-0 shadow-sm mb-4 ad-feature-control-card" style="border-radius:14px;overflow:hidden">
        <div class="card-header py-2 px-4" style="background:linear-gradient(135deg,#1b3a5c,#2c5f8a)">
            <div class="d-flex align-items-center gap-2">
                <i class="fas fa-sliders-h text-white"></i>
                <h6 class="mb-0 text-white fw-bold">광고 기능 스위치</h6>
                <span class="ms-auto badge ad-feature-header-note" style="background:rgba(255,255,255,.15);color:#fff;font-size:.68rem"><i class="fas fa-info-circle me-1"></i>사장님 계정에 표시될 광고 메뉴를 제어합니다</span>
            </div>
        </div>
        <div class="card-body py-3 px-4">
            <!-- 마스터 스위치: 광고 주문 관리 -->
            <div class="d-flex align-items-center justify-content-between p-3 rounded-3 mb-3 ad-feature-switch-row ad-feature-master-row" id="masterSwitchCard" style="background:${masterOn ? 'linear-gradient(135deg,rgba(34,197,94,.06),rgba(34,197,94,.14))' : '#f8f9fa'};border:2px solid ${masterOn ? 'rgba(34,197,94,.35)' : '#ddd'};transition:all .3s">
                <div class="d-flex align-items-center gap-3">
                    <div class="ad-feature-switch-icon" id="masterSwitchIcon" style="width:46px;height:46px;border-radius:13px;background:${masterOn ? 'linear-gradient(135deg,#22c55e,#4ade80)' : '#aaa'};display:flex;align-items:center;justify-content:center;transition:all .3s;box-shadow:${masterOn ? '0 4px 12px rgba(34,197,94,.25)' : 'none'}">
                        <i class="fas fa-bullhorn text-white" style="font-size:1.15rem"></i>
                    </div>
                    <div>
                        <div class="fw-bold" style="font-size:1rem">광고 주문 관리</div>
                        <div class="ad-feature-description" style="font-size:.74rem;color:#888"><span class="ad-feature-desktop-copy">ON: 사장님 계정에 "광고 주문 내역" / "새 광고 주문" 메뉴 표시<br>OFF: 해당 메뉴 숨김 (광고 분석은 항상 표시)</span><span class="ad-feature-mobile-copy">사장님의 광고 주문 메뉴 전체를 켜거나 끕니다.</span></div>
                    </div>
                </div>
                <div class="form-check form-switch mb-0" style="padding-left:0">
                    <input class="form-check-input ad-feature-toggle" type="checkbox" role="switch" id="switchAdOrderMgmt" ${masterOn ? 'checked' : ''} onchange="toggleAdFeature('ad_order_mgmt_enabled', this.checked)" style="width:52px;height:26px;cursor:pointer">
                </div>
            </div>
            <!-- 하위 스위치: 블로그 / 플레이스 -->
            <div id="subSwitchPanel" style="opacity:${masterOn ? '1' : '.45'};pointer-events:${masterOn ? 'auto' : 'none'};transition:all .3s">
                <div class="d-flex align-items-center gap-2 mb-2 ad-feature-subintro" style="font-size:.76rem;color:#999">
                    <i class="fas fa-level-down-alt"></i>
                    <span>광고 주문 관리가 <strong>ON</strong>일 때 아래 스위치로 세부 기능을 제어합니다. OFF된 기능은 새 광고 주문 탭에서 숨겨집니다.</span>
                </div>
                <div class="row g-3 ad-feature-grid">
                    <div class="col-md-6">
                        <div class="d-flex align-items-center justify-content-between p-3 rounded-3 ad-feature-switch-row" id="blogSwitchCard" style="background:${blogOn ? 'linear-gradient(135deg,rgba(14,165,233,.06),rgba(14,165,233,.12))' : '#f8f9fa'};border:1px solid ${blogOn ? 'rgba(14,165,233,.2)' : '#eee'};transition:all .3s">
                            <div class="d-flex align-items-center gap-3">
                                <div class="ad-feature-switch-icon" id="blogSwitchIcon" style="width:42px;height:42px;border-radius:12px;background:${blogOn ? 'linear-gradient(135deg,#0ea5e9,#38bdf8)' : '#ccc'};display:flex;align-items:center;justify-content:center;transition:all .3s">
                                    <i class="fas fa-pen-nib text-white"></i>
                                </div>
                                <div>
                                    <div class="fw-bold" style="font-size:.92rem">블로그 배포</div>
                                    <div class="ad-feature-description" style="font-size:.72rem;color:#888">블로그 주문 탭 표시</div>
                                </div>
                            </div>
                            <div class="form-check form-switch mb-0" style="padding-left:0">
                                <input class="form-check-input ad-feature-toggle" type="checkbox" role="switch" id="switchBlogAd" ${blogOn ? 'checked' : ''} onchange="toggleAdFeature('ad_blog_enabled', this.checked)" style="width:48px;height:24px;cursor:pointer">
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="d-flex align-items-center justify-content-between p-3 rounded-3 ad-feature-switch-row" id="placeSwitchCard" style="background:${placeOn ? 'linear-gradient(135deg,rgba(139,92,246,.06),rgba(139,92,246,.12))' : '#f8f9fa'};border:1px solid ${placeOn ? 'rgba(139,92,246,.2)' : '#eee'};transition:all .3s">
                            <div class="d-flex align-items-center gap-3">
                                <div class="ad-feature-switch-icon" id="placeSwitchIcon" style="width:42px;height:42px;border-radius:12px;background:${placeOn ? 'linear-gradient(135deg,#8b5cf6,#a78bfa)' : '#ccc'};display:flex;align-items:center;justify-content:center;transition:all .3s">
                                    <i class="fas fa-map-marker-alt text-white"></i>
                                </div>
                                <div>
                                    <div class="fw-bold" style="font-size:.92rem">플레이스 방문</div>
                                    <div class="ad-feature-description" style="font-size:.72rem;color:#888">플레이스 주문 탭 표시</div>
                                </div>
                            </div>
                            <div class="form-check form-switch mb-0" style="padding-left:0">
                                <input class="form-check-input ad-feature-toggle" type="checkbox" role="switch" id="switchPlaceAd" ${placeOn ? 'checked' : ''} onchange="toggleAdFeature('ad_place_traffic_enabled', this.checked)" style="width:48px;height:24px;cursor:pointer">
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="d-flex align-items-center justify-content-between p-3 rounded-3 ad-feature-switch-row" id="shortsSwitchCard" style="background:${shortsOn ? 'linear-gradient(135deg,rgba(220,38,38,.06),rgba(220,38,38,.12))' : '#f8f9fa'};border:1px solid ${shortsOn ? 'rgba(220,38,38,.2)' : '#eee'};transition:all .3s">
                            <div class="d-flex align-items-center gap-3">
                                <div class="ad-feature-switch-icon" id="shortsSwitchIcon" style="width:42px;height:42px;border-radius:12px;background:${shortsOn ? 'linear-gradient(135deg,#dc2626,#f87171)' : '#ccc'};display:flex;align-items:center;justify-content:center;transition:all .3s">
                                    <i class="fas fa-film text-white"></i>
                                </div>
                                <div>
                                    <div class="fw-bold" style="font-size:.92rem">쇼츠 배포</div>
                                    <div class="ad-feature-description" style="font-size:.72rem;color:#888">쇼츠 주문 탭 표시</div>
                                </div>
                            </div>
                            <div class="form-check form-switch mb-0" style="padding-left:0">
                                <input class="form-check-input ad-feature-toggle" type="checkbox" role="switch" id="switchShortsAd" ${shortsOn ? 'checked' : ''} onchange="toggleAdFeature('ad_shorts_enabled', this.checked)" style="width:48px;height:24px;cursor:pointer">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="card data-card mb-4 ad-pricing-card">
        <div class="card-header d-flex align-items-center gap-2">
            <i class="fas fa-won-sign text-primary"></i>
            <div>
                <h5 class="mb-0">광고 상품 단가 설정</h5>
                <small class="text-muted">사장님의 새 광고 주문 화면과 예상 집행 예산에 즉시 반영됩니다.</small>
            </div>
        </div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-md-4">
                    <label class="form-label">블로그 배포 1건 단가</label>
                    <div class="input-group"><input type="number" min="0" step="100" class="form-control" id="adPriceBlog" value="${pricing.blog_unit_price}"><span class="input-group-text">원</span></div>
                </div>
                <div class="col-md-4">
                    <label class="form-label">플레이스 방문 1건 단가</label>
                    <div class="input-group"><input type="number" min="0" step="100" class="form-control" id="adPricePlace" value="${pricing.place_traffic_unit_price}"><span class="input-group-text">원</span></div>
                </div>
                <div class="col-md-4">
                    <label class="form-label">쇼츠 배포 1건 단가</label>
                    <div class="input-group"><input type="number" min="0" step="100" class="form-control" id="adPriceShortsDist" value="${pricing.shorts_distribution_unit_price}"><span class="input-group-text">원</span></div>
                </div>
                ${[
                    ['15s', '쇼츠 제작 15초 이하'],
                    ['30s', '쇼츠 제작 30초 이하'],
                    ['60s', '쇼츠 제작 60초 이하'],
                    ['90s', '쇼츠 제작 90초 이하'],
                ].map(([code, label]) => `<div class="col-md-3 col-6">
                    <label class="form-label">${label}</label>
                    <div class="input-group"><input type="number" min="0" step="100" class="form-control" id="adPriceShorts_${code}" value="${pricing.shorts_duration_prices?.[code] || 0}"><span class="input-group-text">원</span></div>
                </div>`).join('')}
            </div>
            <div class="d-flex flex-column flex-sm-row align-items-sm-center justify-content-between gap-2 mt-3">
                <small class="text-muted"><i class="fas fa-info-circle me-1"></i>단가는 공급가액 기준이며 부가세는 별도입니다. 주문 접수 시점의 단가가 주문에 저장됩니다.</small>
                <button type="button" class="btn btn-primary flex-shrink-0" id="saveAdPricingBtn" onclick="saveAdminAdPricing()"><i class="fas fa-save me-1"></i>단가 저장</button>
            </div>
            <div id="adPricingResult" class="mt-2"></div>
        </div>
    </div>

    <div class="row g-3 mb-3 ad-order-stats">
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center ad-order-stat-card" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-warning">${pending}</div><small class="text-muted">대기/검토</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center ad-order-stat-card" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-primary">${running}</div><small class="text-muted">집행중</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center ad-order-stat-card" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-success">${done}</div><small class="text-muted">완료</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center ad-order-stat-card" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-dark">${orders.length}</div><small class="text-muted">전체</small>
        </div></div></div>
    </div>
    <div class="card data-card ad-order-list-card"><div class="card-header d-flex justify-content-between align-items-center ad-order-list-header">
        <h5 class="mb-0"><i class="fas fa-bullhorn me-2"></i>광고주문 목록</h5>
        <div class="btn-group btn-group-sm ad-order-filters">
            <button class="btn btn-outline-secondary active ad-filter-btn" onclick="filterAdOrders('all',this)">전체</button>
            <button class="btn btn-outline-warning ad-filter-btn" onclick="filterAdOrders('pending',this)">대기</button>
            <button class="btn btn-outline-primary ad-filter-btn" onclick="filterAdOrders('running',this)">집행중</button>
            <button class="btn btn-outline-success ad-filter-btn" onclick="filterAdOrders('done',this)">완료</button>
        </div>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm" id="adOrdersTable">
            <thead><tr><th>ID</th><th>가맹점</th><th>유형</th><th>상태</th><th>요청자</th><th>요청일</th><th>관리메모</th><th>상세/집행</th></tr></thead>
            <tbody>${orders.map(o => `<tr data-status="${o.status}">
                <td>${o.id}</td><td>${escapeHtml(o.merchant_name)}</td>
                <td>${adOrderTypeBadge(o.type)}</td>
                <td>${statusBadge(o.status)}</td><td>${escapeHtml(o.creator_name)}</td><td>${formatDate(o.created_at)}</td>
                <td style="font-size:.78rem;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(o.admin_memo) || '-'}</td>
                <td><div class="ad-order-actions">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="showAdOrderDetail(${o.id})" title="상세보기"><i class="fas fa-eye"></i></button>
                    <select class="form-select form-select-sm d-inline-block" style="width:110px" id="adStatus${o.id}">
                        ${adStatusOptions(o.allowed_statuses)}
                    </select>
                    <button class="btn btn-sm btn-primary ms-1" onclick="executeAdOrder(${o.id})"><i class="fas fa-check"></i></button>
                </div></td>
            </tr>`).join('')}</tbody>
        </table></div>
    </div></div>`;
}

function adminAdPriceValue(id) {
    const value = parseInt(document.getElementById(id)?.value, 10);
    return Number.isFinite(value) ? Math.max(0, value) : 0;
}

async function saveAdminAdPricing() {
    const btn = document.getElementById('saveAdPricingBtn');
    const result = document.getElementById('adPricingResult');
    const payload = {
        blog_unit_price: adminAdPriceValue('adPriceBlog'),
        place_traffic_unit_price: adminAdPriceValue('adPricePlace'),
        shorts_distribution_unit_price: adminAdPriceValue('adPriceShortsDist'),
        shorts_duration_prices: {
            '15s': adminAdPriceValue('adPriceShorts_15s'),
            '30s': adminAdPriceValue('adPriceShorts_30s'),
            '60s': adminAdPriceValue('adPriceShorts_60s'),
            '90s': adminAdPriceValue('adPriceShorts_90s'),
        },
    };
    btn.disabled = true;
    try {
        const saved = await apiPut('/api/admin/ad-pricing', payload);
        adPricing = saved;
        result.innerHTML = '<div class="alert alert-success py-2 mb-0"><i class="fas fa-check-circle me-1"></i>광고 단가가 저장되었습니다.</div>';
    } catch (e) {
        result.innerHTML = `<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`;
    } finally {
        btn.disabled = false;
    }
}

async function toggleAdFeature(key, enabled) {
    try {
        await apiPut(`/api/admin/ad-feature-flags?${key}=${enabled}`, {});

        // 마스터 스위치 시각 업데이트
        if (key === 'ad_order_mgmt_enabled') {
            const masterCard = document.getElementById('masterSwitchCard');
            const masterIcon = document.getElementById('masterSwitchIcon');
            const subPanel = document.getElementById('subSwitchPanel');
            if (masterCard) {
                masterCard.style.background = enabled ? 'linear-gradient(135deg,rgba(34,197,94,.06),rgba(34,197,94,.14))' : '#f8f9fa';
                masterCard.style.borderColor = enabled ? 'rgba(34,197,94,.35)' : '#ddd';
            }
            if (masterIcon) {
                masterIcon.style.background = enabled ? 'linear-gradient(135deg,#22c55e,#4ade80)' : '#aaa';
                masterIcon.style.boxShadow = enabled ? '0 4px 12px rgba(34,197,94,.25)' : 'none';
            }
            if (subPanel) {
                subPanel.style.opacity = enabled ? '1' : '.45';
                subPanel.style.pointerEvents = enabled ? 'auto' : 'none';
            }
        }

        // 하위 스위치(블로그/플레이스/쇼츠) 시각 업데이트
        const subSwitchStyles = {
            ad_blog_enabled: { card: 'blogSwitchCard', icon: 'blogSwitchIcon', base: '14,165,233', from: '#0ea5e9', to: '#38bdf8' },
            ad_place_traffic_enabled: { card: 'placeSwitchCard', icon: 'placeSwitchIcon', base: '139,92,246', from: '#8b5cf6', to: '#a78bfa' },
            ad_shorts_enabled: { card: 'shortsSwitchCard', icon: 'shortsSwitchIcon', base: '220,38,38', from: '#dc2626', to: '#f87171' },
        };
        const style = subSwitchStyles[key];
        if (style) {
            const cardEl = document.getElementById(style.card);
            const iconEl = document.getElementById(style.icon);
            if (cardEl) {
                cardEl.style.background = enabled ? `linear-gradient(135deg,rgba(${style.base},.06),rgba(${style.base},.12))` : '#f8f9fa';
                cardEl.style.borderColor = enabled ? `rgba(${style.base},.2)` : '#eee';
            }
            if (iconEl) iconEl.style.background = enabled ? `linear-gradient(135deg,${style.from},${style.to})` : '#ccc';
        }
    } catch(e) {
        alert('설정 변경 실패: ' + e.message);
        // 실패 시 토글 복원
        const elMap = { ad_order_mgmt_enabled: 'switchAdOrderMgmt', ad_blog_enabled: 'switchBlogAd', ad_place_traffic_enabled: 'switchPlaceAd', ad_shorts_enabled: 'switchShortsAd' };
        const el = document.getElementById(elMap[key]);
        if (el) el.checked = !enabled;
    }
}

function filterAdOrders(status, btn) {
    document.querySelectorAll('.ad-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#adOrdersTable tbody tr').forEach(row => {
        if (status === 'all') { row.style.display = ''; return; }
        if (status === 'pending') {
            row.style.display = (row.dataset.status === 'requested' || row.dataset.status === 'reviewing') ? '' : 'none';
        } else {
            row.style.display = row.dataset.status === status ? '' : 'none';
        }
    });
}

const SHORTS_PLATFORM_LABELS = { youtube: 'YouTube', instagram: 'Instagram', tiktok: 'TikTok', facebook: 'Facebook' };

/** 최고관리자 광고주문 상세: 쇼츠 주문 섹션 마크업. */
function shortsAdminDetailHtml(d) {
    const won = v => Math.floor(Number(v || 0)).toLocaleString() + '원';
    const list = v => (v && v.length) ? escapeHtml(v.join(', ')) : '-';
    const text = v => v ? escapeHtml(String(v)) : '-';
    const yesNo = v => v ? '<span class="text-danger fw-semibold">예</span>' : '아니오';

    const platformText = Object.entries(d.platform_counts || {})
        .map(([code, n]) => `${SHORTS_PLATFORM_LABELS[code] || code} ${n}건`).join(', ') || '-';
    const categoryText = Object.entries(d.brief_categories || {})
        .map(([code, name]) => `${SHORTS_PLATFORM_LABELS[code] || code}: ${name}`).join(' / ') || '-';
    const safety = [
        d.brand_no_competitor ? '경쟁사 언급 금지' : null,
        d.brand_no_adult ? '성인 콘텐츠 금지' : null,
        d.brand_no_violence ? '폭력적 콘텐츠 금지' : null,
        d.brand_no_political ? '정치적 콘텐츠 금지' : null,
    ].filter(Boolean);

    const cell = (label, value) => `<div class="col-md-6"><label class="small text-muted">${label}</label><div>${value}</div></div>`;

    return `
    <div class="border rounded p-3 mb-3" style="background:#f8f9fa">
        <h6 class="fw-bold mb-2"><i class="fas fa-film me-1 text-danger"></i>쇼츠 배포 상세</h6>
        <div class="row g-2">
            ${cell('캠페인 제목', `<span class="fw-bold">${text(d.campaign_name)}</span>`)}
            ${cell('캠페인 유형', `<span class="fw-bold">${text(d.campaign_type_label)}</span>`)}
            ${cell('브랜드(매장)명', text(d.brand_name))}
            ${cell('업종', text(d.industry))}
            ${cell('웹사이트 / 플레이스', text(d.website_url))}
            ${cell('희망 일정', `${text(d.start_date)} ~ ${text(d.end_date)}`)}
            ${cell('배포 건수', `${d.distribution_count || 0}건`)}
            ${cell('영상제작 건수', `${d.video_production_count || 0}건 (${text(d.video_duration_label)})`)}
            ${cell('플랫폼별 배포', escapeHtml(platformText))}
            ${cell('타겟 키워드', list(d.target_keywords))}
            ${cell('참고 링크', list(d.reference_links))}
            ${cell('영상 URL', text(d.uploaded_video_url))}
            <div class="col-12"><label class="small text-muted">캠페인 설명</label><div style="font-size:.85rem;white-space:pre-line">${text(d.description)}</div></div>
        </div>
        <hr class="my-3">
        <div class="fw-bold mb-2" style="font-size:.88rem"><i class="fas fa-clapperboard me-1 text-danger"></i>영상 브리프</div>
        <div class="row g-2">
            ${cell('제품 / 서비스명', text(d.brief_product_name))}
            ${cell('플랫폼별 카테고리', escapeHtml(categoryText))}
            ${cell('톤앤매너', text(d.brief_tone))}
            ${cell('영상 스타일', text(d.brief_style))}
            ${cell('타겟 소비자층', text(d.brief_target_audience))}
            ${cell('추천 해시태그', list(d.brief_hashtags))}
            <div class="col-12"><label class="small text-muted">상세 설명</label><div style="font-size:.85rem;white-space:pre-line">${text(d.brief_product_detail)}</div></div>
            <div class="col-12"><label class="small text-muted">핵심 메시지</label><div style="font-size:.85rem;white-space:pre-line">${text(d.brief_key_messages)}</div></div>
            <div class="col-12"><label class="small text-muted">금지 사항</label><div style="font-size:.85rem;white-space:pre-line">${text(d.brief_avoid)}</div></div>
        </div>
        <hr class="my-3">
        <div class="fw-bold mb-2" style="font-size:.88rem"><i class="fas fa-user-check me-1 text-danger"></i>크리에이터 자격 · 브랜드 세이프티</div>
        <div class="row g-2">
            ${cell('최소 팔로워', text(d.creator_min_followers))}
            ${cell('선호 성별 / 연령대', `${text(d.creator_gender)} / ${text(d.creator_age_group)}`)}
            ${cell('금지 단어', text(d.brand_forbidden_words))}
            ${cell('세이프티 조건', safety.length ? escapeHtml(safety.join(', ')) : '-')}
            ${cell('UTM 링크 포함', yesNo(d.track_utm))}
            ${cell('할인코드 포함', yesNo(d.track_promo_code))}
            ${cell('목표 KPI', list(d.kpi_goals))}
            <div class="col-12"><label class="small text-muted">특이사항 / 추가 요구사항</label><div style="font-size:.85rem;white-space:pre-line">${text(d.creator_requirements)}</div></div>
        </div>
        <hr class="my-3">
        <div class="fw-bold mb-2" style="font-size:.88rem"><i class="fas fa-calculator me-1 text-danger"></i>예상 집행 비용 <span class="text-muted fw-normal" style="font-size:.74rem">(부가세 별도)</span></div>
        <div class="row g-2">
            ${cell('배포비', won(d.est_distribution_cost))}
            ${cell('영상제작비', won(d.est_production_cost))}
            <div class="col-12 d-flex justify-content-between fw-bold border-top pt-2">
                <span>합계</span><span class="text-danger">${won(d.est_total_cost)}</span>
            </div>
        </div>
    </div>`;
}

async function showAdOrderDetail(orderId) {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '광고주문 상세 #' + orderId;
    document.getElementById('formModalBody').innerHTML = adpayLoadingMarkup();
    document.getElementById('formModalFooter').innerHTML = '<button class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>';
    new bootstrap.Modal(modal).show();

    try {
        const o = await apiGet(`/api/admin/ad/orders/${orderId}`);
        let detailHtml = '';

        if (o.type === 'blog' && o.blog_detail) {
            const d = o.blog_detail;
            detailHtml = `
            <div class="border rounded p-3 mb-3" style="background:#f8f9fa">
                <h6 class="fw-bold mb-2"><i class="fas fa-pen-nib me-1 text-info"></i>블로그 광고 상세</h6>
                <div class="row g-2">
                    <div class="col-md-6"><label class="small text-muted">캠페인명</label><div class="fw-bold">${escapeHtml(d.campaign_name) || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">주소</label><div>${escapeHtml(d.address) || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">연락처</label><div>${escapeHtml(d.contact) || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">링크</label><div style="font-size:.82rem">${(d.links && d.links.length) ? escapeHtml(d.links.join(', ')) : '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">주요 키워드</label><div>${(d.main_keywords && d.main_keywords.length) ? escapeHtml(d.main_keywords.join(', ')) : '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">해시태그</label><div>${(d.hashtags && d.hashtags.length) ? escapeHtml(d.hashtags.join(', ')) : '-'}</div></div>
                    <div class="col-md-4"><label class="small text-muted">주문 건수</label><div class="fw-bold">${Number(d.order_count || 1).toLocaleString()}건</div></div>
                    <div class="col-md-4"><label class="small text-muted">주문 단가</label><div>${Number(d.unit_price || 0).toLocaleString()}원</div></div>
                    <div class="col-md-4"><label class="small text-muted">예상 집행 예산</label><div class="fw-bold text-primary">${Number(d.est_total_cost || 0).toLocaleString()}원</div></div>
                    <div class="col-12"><label class="small text-muted">설명</label><div style="font-size:.85rem;white-space:pre-line">${escapeHtml(d.description) || '-'}</div></div>
                    ${d.images && d.images.length > 0 ? `<div class="col-12"><label class="small text-muted">첨부 이미지 (${d.images.length}건)</label><div class="d-flex gap-1 flex-wrap">${d.images.map(img => `<span class="badge bg-light text-dark border">${escapeHtml(img.file_path)}</span>`).join('')}</div></div>` : ''}
                </div>
            </div>`;
        } else if (o.type === 'place_traffic' && o.place_traffic_detail) {
            const d = o.place_traffic_detail;
            detailHtml = `
            <div class="border rounded p-3 mb-3" style="background:#f8f9fa">
                <h6 class="fw-bold mb-2"><i class="fas fa-map-marker-alt me-1 text-secondary"></i>플레이스 방문 상세</h6>
                <div class="row g-2">
                    <div class="col-md-6"><label class="small text-muted">플레이스명/ID</label><div class="fw-bold">${escapeHtml(d.place_name_or_id) || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">검색 키워드</label><div>${(d.search_keywords && d.search_keywords.length) ? escapeHtml(d.search_keywords.join(', ')) : '-'}</div></div>
                    <div class="col-md-4"><label class="small text-muted">주문 건수</label><div class="fw-bold">${Number(d.order_count || 1).toLocaleString()}건</div></div>
                    <div class="col-md-4"><label class="small text-muted">주문 단가</label><div>${Number(d.unit_price || 0).toLocaleString()}원</div></div>
                    <div class="col-md-4"><label class="small text-muted">예상 집행 예산</label><div class="fw-bold text-primary">${Number(d.est_total_cost || 0).toLocaleString()}원</div></div>
                </div>
            </div>`;
        } else if (o.type === 'shorts' && o.shorts_detail) {
            detailHtml = shortsAdminDetailHtml(o.shorts_detail);
        }

        document.getElementById('formModalBody').innerHTML = `
        <div class="mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(14,165,233,.04),rgba(99,102,241,.04))">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                <div>
                    <div class="fw-bold">${escapeHtml(o.merchant_name)} ${adOrderTypeBadge(o.type)}</div>
                    <div class="text-muted" style="font-size:.82rem">요청자: ${escapeHtml(o.creator_name)} · 담당: ${escapeHtml(o.assigned_admin_name) || '미배정'}</div>
                </div>
                <div class="text-end">${statusBadge(o.status)}<br><small class="text-muted">${formatDate(o.created_at)}</small></div>
            </div>
        </div>
        ${detailHtml}
        <div class="border rounded p-3 mb-3">
            <h6 class="fw-bold mb-2"><i class="fas fa-tasks me-1 text-warning"></i>광고 집행 관리</h6>
            <div class="row g-2">
                <div class="col-md-6">
                    <label class="form-label small">상태 변경</label>
                    <select class="form-select form-select-sm" id="detailAdStatus">
                        ${adStatusOptions(o.allowed_statuses)}
                    </select>
                </div>
                <div class="col-md-6">
                    <label class="form-label small">관리 메모</label>
                    <input class="form-control form-control-sm" id="detailAdMemo" placeholder="메모 추가">
                </div>
                <div class="col-12">
                    <button class="btn btn-primary btn-sm" onclick="executeAdOrderFromDetail(${o.id})"><i class="fas fa-save me-1"></i>상태 저장 & 집행</button>
                </div>
            </div>
        </div>
        ${o.admin_memo ? `<div class="border rounded p-3"><h6 class="fw-bold small mb-1"><i class="fas fa-sticky-note me-1"></i>관리 메모 이력</h6><div style="font-size:.82rem;white-space:pre-line">${escapeHtml(o.admin_memo)}</div></div>` : ''}`;
    } catch(e) {
        document.getElementById('formModalBody').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

async function executeAdOrder(orderId) {
    const status = document.getElementById(`adStatus${orderId}`).value;
    if (!status) { alert('변경할 다음 상태를 선택해주세요'); return; }
    const memo = prompt('관리 메모 (선택사항):');
    try {
        await apiPut(`/api/admin/ad/orders/${orderId}/execute?status=${status}${memo ? '&admin_memo=' + encodeURIComponent(memo) : ''}`, {});
        navigate('admin-adorders');
    } catch(e) { alert('상태변경 실패: ' + e.message); }
}

async function executeAdOrderFromDetail(orderId) {
    const status = document.getElementById('detailAdStatus').value;
    if (!status) { alert('변경할 다음 상태를 선택해주세요'); return; }
    const memo = document.getElementById('detailAdMemo').value;
    try {
        await apiPut(`/api/admin/ad/orders/${orderId}/execute?status=${status}${memo ? '&admin_memo=' + encodeURIComponent(memo) : ''}`, {});
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        alert('광고주문 상태가 변경되었습니다');
        navigate('admin-adorders');
    } catch(e) { alert('상태변경 실패: ' + e.message); }
}

async function loadAdminMetrics(c, t) {
    t.textContent = '광고 분석 관리';
    const merchants = await apiGet('/api/admin/merchants');
    let opts = merchants.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    c.innerHTML = `
    <div class="workspace-hero mb-3">
        <div>
            <span class="workspace-eyebrow">AD ANALYTICS</span>
            <h2>매장별 광고 분석 데이터 관리</h2>
            <p>사장님이 등록한 우리 매장·경쟁업체를 같은 검색 키워드로 확인한 뒤 최신 지표를 기록합니다.</p>
        </div>
        <div class="workspace-hero-icon"><i class="fas fa-chart-line"></i></div>
    </div>
    <div class="alert alert-info">
        <i class="fas fa-circle-info me-2"></i>
        네이버 플레이스의 리뷰 수와 동일 키워드 검색 순위를 확인해 입력하세요. 같은 날짜 데이터는 새로 추가되지 않고 최신 값으로 갱신됩니다.
    </div>
    <div class="card data-card mb-3"><div class="card-header"><h5>분석 대상 선택</h5></div><div class="card-body">
        <div class="row g-3">
            <div class="col-md-5"><label class="form-label">가맹점</label><select class="form-select" id="metricMerch" onchange="loadAdminMetricTargets()">${opts || '<option value="">가맹점 없음</option>'}</select></div>
            <div class="col-md-7"><label class="form-label">우리 매장 / 경쟁업체</label><select class="form-select" id="metricTarget" onchange="selectAdminMetricTarget()"><option>가맹점을 먼저 선택하세요</option></select></div>
        </div>
        <div id="metricTargetStatus" class="mt-3"></div>
    </div></div>
    <div class="card data-card mb-3"><div class="card-header"><h5>확인 지표 입력</h5></div><div class="card-body">
        <div class="row g-3">
            <div class="col-md-4"><label class="form-label">공통 검색 키워드</label><input class="form-control" id="metricKeyword" placeholder="예: 지역명 + 업종명"></div>
            <div class="col-md-4"><label class="form-label">확인 날짜</label><input type="date" class="form-control" id="metricDate"></div>
            <div class="col-md-4"><label class="form-label">플레이스 순위</label><input type="number" min="1" class="form-control" id="metricRank" placeholder="검색 결과 순위"></div>
            <div class="col-md-4"><label class="form-label">블로그 리뷰 누적 수</label><input type="number" min="0" class="form-control" id="metricBlog" value="0"></div>
            <div class="col-md-4"><label class="form-label">방문자 리뷰 누적 수</label><input type="number" min="0" class="form-control" id="metricVisitor" value="0"></div>
            <div class="col-md-4 d-flex align-items-end"><button class="btn btn-primary w-100" id="metricSaveBtn" onclick="saveMetric()"><i class="fas fa-save me-1"></i>분석 데이터 저장</button></div>
        </div><div id="metricResult" class="mt-3"></div>
    </div></div>
    <div class="card data-card"><div class="card-header"><h5>최근 입력 기록</h5></div><div class="card-body" id="metricHistory"><div class="text-center text-muted py-3">분석 대상을 선택하세요.</div></div></div>`;
    const today = new Date();
    today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
    document.getElementById('metricDate').value = today.toISOString().slice(0, 10);
    if (merchants.length) await loadAdminMetricTargets();
}

async function loadAdminMetricTargets() {
    const merchantId = Number(document.getElementById('metricMerch')?.value);
    const targetSelect = document.getElementById('metricTarget');
    if (!merchantId || !targetSelect) return;
    targetSelect.innerHTML = '<option>불러오는 중...</option>';
    try {
        const data = await apiGet(`/api/admin/ad/analysis-targets?merchant_id=${merchantId}`);
        adminMetricTargets = data.targets || [];
        targetSelect.innerHTML = adminMetricTargets.length
            ? adminMetricTargets.map((target, index) => `<option value="${index}">${target.type === 'my' ? '우리 매장' : '경쟁업체'} · ${escapeHtml(target.name)}</option>`).join('')
            : '<option value="">사장님이 등록한 분석 대상이 없습니다</option>';
        document.getElementById('metricTargetStatus').innerHTML = adminMetricTargets.length
            ? `<div class="analysis-progress"><strong>${data.ready_count}/${adminMetricTargets.length}</strong><span>개 대상에 분석 데이터가 있습니다</span></div>`
            : '<div class="alert alert-warning mb-0">사장님 계정에서 우리 매장 프로필과 경쟁업체를 먼저 등록해야 합니다.</div>';
        selectAdminMetricTarget();
    } catch (e) {
        adminMetricTargets = [];
        targetSelect.innerHTML = '<option value="">대상을 불러오지 못했습니다</option>';
        document.getElementById('metricTargetStatus').innerHTML = `<div class="alert alert-danger mb-0">${escapeHtml(e.message)}</div>`;
    }
}

async function selectAdminMetricTarget() {
    const targetIndex = Number(document.getElementById('metricTarget')?.value);
    const target = adminMetricTargets[targetIndex];
    if (!target) {
        document.getElementById('metricHistory').innerHTML = '<div class="text-center text-muted py-3">등록된 분석 대상이 없습니다.</div>';
        return;
    }
    const latest = target.latest_metric;
    document.getElementById('metricKeyword').value = target.search_keyword || latest?.search_keyword || '';
    document.getElementById('metricBlog').value = latest?.blog_review_count ?? 0;
    document.getElementById('metricVisitor').value = latest?.visitor_review_count ?? 0;
    document.getElementById('metricRank').value = latest?.place_rank ?? '';
    await loadAdminMetricHistory();
}

async function loadAdminMetricHistory() {
    const merchantId = Number(document.getElementById('metricMerch')?.value);
    const target = adminMetricTargets[Number(document.getElementById('metricTarget')?.value)];
    const history = document.getElementById('metricHistory');
    if (!target || !history) return;
    try {
        const rows = await apiGet(`/api/admin/ad/metrics?merchant_id=${merchantId}&place_url=${encodeURIComponent(target.place_url)}`);
        history.innerHTML = rows.length ? `<div class="table-responsive"><table class="table table-sm align-middle mb-0">
            <thead><tr><th>날짜</th><th>키워드</th><th>블로그 리뷰</th><th>방문자 리뷰</th><th>순위</th></tr></thead>
            <tbody>${rows.map(row => `<tr><td>${row.date}</td><td>${escapeHtml(row.search_keyword || '-')}</td><td>${row.blog_review_count}</td><td>${row.visitor_review_count}</td><td>${formatRank(row.place_rank)}</td></tr>`).join('')}</tbody>
        </table></div>` : '<div class="text-center text-muted py-3">아직 입력된 데이터가 없습니다.</div>';
        enhanceRoleMobilePage(history);
    } catch (e) {
        history.innerHTML = `<div class="alert alert-danger mb-0">${escapeHtml(e.message)}</div>`;
    }
}

async function saveMetric() {
    const merchantId = Number(document.getElementById('metricMerch').value);
    const target = adminMetricTargets[Number(document.getElementById('metricTarget').value)];
    const date = document.getElementById('metricDate').value;
    const keyword = document.getElementById('metricKeyword').value.trim();
    const blog = Number(document.getElementById('metricBlog').value);
    const visitor = Number(document.getElementById('metricVisitor').value);
    const rankRaw = document.getElementById('metricRank').value;
    if (!target) { alert('분석 대상을 선택해주세요'); return; }
    if (!date) { alert('확인 날짜를 입력해주세요'); return; }
    if (!keyword) { alert('우리 매장과 경쟁업체에 공통으로 적용할 검색 키워드를 입력해주세요'); return; }
    if (blog < 0 || visitor < 0 || (rankRaw && Number(rankRaw) < 1)) { alert('리뷰 수와 순위를 올바르게 입력해주세요'); return; }
    const btn = document.getElementById('metricSaveBtn');
    btn.disabled = true;
    try {
        const result = await apiPost('/api/admin/ad/metrics', {
            merchant_id: merchantId,
            place_url: target.place_url,
            date,
            blog_review_count: blog,
            visitor_review_count: visitor,
            place_rank: rankRaw ? Number(rankRaw) : null,
            search_keyword: keyword,
            source: 'manual'
        });
        document.getElementById('metricResult').innerHTML = `<div class="alert alert-success">${result.updated ? '같은 날짜의 데이터를 갱신했습니다.' : '분석 데이터를 저장했습니다.'}</div>`;
        await loadAdminMetricTargets();
    } catch (e) {
        document.getElementById('metricResult').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    } finally {
        btn.disabled = false;
    }
}

async function loadAdminSalesAssign(c, t) {
    t.textContent = '영업관리자 연결';
    const [assigns, merchants, salesManagers] = await Promise.all([
        apiGet('/api/admin/sales-assignments'),
        apiGet('/api/admin/merchants'),
        apiGet('/api/admin/sales-managers'),
    ]);

    const merchantOpts = merchants.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    const salesOpts = salesManagers.map(u => `<option value="${u.id}">${escapeHtml(u.name)} (${escapeHtml(u.email)})</option>`).join('');

    c.innerHTML = `
    <div class="alert alert-warning mb-3" style="border-radius:12px;border:none;background:rgba(255,193,7,.08)">
        <div class="d-flex align-items-start">
            <i class="fas fa-handshake me-3 mt-1 fs-5"></i>
            <div>
                <h6 class="fw-bold mb-1">ADPAY 영업관리자 연결 안내</h6>
                <ul class="mb-0 small">
                    <li>영업대행사를 통해 가입한 가맹점은 <strong>최고관리자가 가맹점과 영업관리자를 연결</strong>합니다.</li>
                    <li>영업관리자 수익은 <strong>최고관리자가 설정한 플랫폼 수익률 이내</strong>에서 배정합니다.</li>
                    <li>예: 수익률 1.0% 설정 시, 10,000원 결제 → 영업관리자 수익 100원</li>
                </ul>
            </div>
        </div>
    </div>

    <!-- 새 연결 추가 폼 -->
    <div class="card data-card mb-3" style="border-radius:14px">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-plus-circle me-2"></i>새 영업관리자 연결</h5></div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-12 col-md-6">
                    <label class="form-label fw-bold">가맹점</label>
                    <select class="form-select" id="assignMerchant">${merchantOpts || '<option disabled>가맹점 없음</option>'}</select>
                </div>
                <div class="col-12 col-md-6">
                    <label class="form-label fw-bold">영업관리자</label>
                    <select class="form-select" id="assignSales">${salesOpts || '<option disabled>영업관리자 없음</option>'}</select>
                </div>
                <div class="col-6 col-md-4">
                    <label class="form-label fw-bold">수익률 (VAT별도)</label>
                    <div class="input-group">
                        <input type="number" class="form-control" id="assignRate" value="1.0" step="0.1" min="0" placeholder="1.0">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted">플랫폼 수익률 이내</small>
                </div>
                <div class="col-6 col-md-4">
                    <label class="form-label fw-bold">메모</label>
                    <input type="text" class="form-control" id="assignMemo" placeholder="배정 사유">
                </div>
                <div class="col-12 col-md-4 d-flex align-items-end">
                    <button class="btn btn-primary w-100" onclick="createSalesAssignment()" style="height:42px">
                        <i class="fas fa-link me-1"></i>연결
                    </button>
                </div>
            </div>
            <div id="assignResult" class="mt-2"></div>
        </div>
    </div>

    <!-- 기존 연결 목록 -->
    <div class="card data-card" style="border-radius:14px">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-list me-2"></i>영업관리자 연결 현황</h5>
            <span class="badge bg-primary">${assigns.length}건</span>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover table-sm align-middle">
                    <thead class="table-light"><tr><th>ID</th><th>가맹점</th><th>영업관리자</th><th>수익률</th><th>수익 예시</th><th>메모</th><th>상태</th><th>액션</th></tr></thead>
                    <tbody>${assigns.map(a => `<tr>
                        <td>${a.id}</td>
                        <td class="fw-bold">${escapeHtml(a.merchant_name) || '-'}</td>
                        <td><i class="fas fa-user-tie text-info me-1"></i>${escapeHtml(a.sales_manager_name) || '-'}</td>
                        <td class="fw-bold text-primary text-nowrap">${(a.commission_rate*100).toFixed(2)}%</td>
                        <td class="text-success fw-bold text-nowrap">${(10000 * a.commission_rate).toLocaleString('ko-KR', {maximumFractionDigits:0})}원</td>
                        <td class="text-muted small">${escapeHtml(a.memo) || '-'}</td>
                        <td>${a.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteSalesAssignment(${a.id})" title="연결 해제">
                                <i class="fas fa-unlink"></i>
                            </button>
                        </td>
                    </tr>`).join('') || '<tr><td colspan="8" class="text-muted text-center py-3">연결된 영업관리자가 없습니다.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>`;
}

async function createSalesAssignment() {
    try {
        const merchantId = parseInt(document.getElementById('assignMerchant').value);
        const salesId = parseInt(document.getElementById('assignSales').value);
        const rate = parseFloat(document.getElementById('assignRate').value) / 100;
        const memo = document.getElementById('assignMemo').value;

        if (!merchantId || !salesId) { alert('가맹점과 영업관리자를 선택해주세요.'); return; }
        if (rate < 0) { alert('수익률은 0% 이상으로 설정해주세요.'); return; }

        await apiPost('/api/admin/sales-assignments', {
            merchant_id: merchantId,
            sales_manager_user_id: salesId,
            commission_rate: rate,
            memo: memo || null,
        });

        const el = document.getElementById('assignResult');
        el.innerHTML = '<div class="alert alert-success py-2"><i class="fas fa-check-circle me-1"></i>영업관리자 연결 완료!</div>';
        setTimeout(() => navigate('admin-sales-assign'), 1000);
    } catch (e) {
        const el = document.getElementById('assignResult');
        el.innerHTML = `<div class="alert alert-danger py-2"><i class="fas fa-exclamation-circle me-1"></i>${escapeHtml(e.message)}</div>`;
    }
}

async function deleteSalesAssignment(id) {
    if (!confirm('이 영업관리자 연결을 해제하시겠습니까?')) return;
    try {
        await api(`/api/admin/sales-assignments/${id}`, { method: 'DELETE' });
        navigate('admin-sales-assign');
    } catch (e) { alert('해제 실패: ' + e.message); }
}

async function loadAdminUsers(c, t) {
    t.textContent = '사용자 목록';
    const users = await apiGet('/api/admin/users');

    const roleLabelMap = {admin:'최고관리자', sales:'영업관리자', owner:'사장님', designer:'직원'};
    const roleBadgeMap = {admin:'danger', sales:'info', owner:'primary', designer:'warning'};

    // 역할별 통계
    const roleCounts = {admin:0, sales:0, owner:0, designer:0};
    users.forEach(u => { if (roleCounts[u.role] !== undefined) roleCounts[u.role]++; });

    let rows = users.map(u => {
        const rLabel = roleLabelMap[u.role] || u.role;
        const rColor = roleBadgeMap[u.role] || 'secondary';
        let extra = '';
        if (u.role === 'owner' && u.merchant_name) extra = `<small class="text-muted d-block">${escapeHtml(u.merchant_name)}</small>`;
        if (u.role === 'sales' && u.assigned_merchant_count > 0) extra = `<small class="text-muted d-block">담당 ${u.assigned_merchant_count}개 가맹점</small>`;
        return `<tr>
            <td>${u.id}</td>
            <td><div class="fw-bold">${escapeHtml(u.name)}</div>${extra}</td>
            <td>${escapeHtml(u.email)}</td>
            <td><span class="badge bg-${rColor}">${rLabel}</span></td>
            <td>${escapeHtml(u.phone) || '-'}</td>
            <td>${u.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
            <td class="small">${formatDate(u.created_at)}</td>
            <td>
                <div class="d-flex gap-1">
                    <select class="form-select form-select-sm" style="width:110px" id="roleSelect${u.id}">
                        <option value="admin" ${u.role==='admin'?'selected':''}>최고관리자</option>
                        <option value="sales" ${u.role==='sales'?'selected':''}>영업관리자</option>
                        <option value="owner" ${u.role==='owner'?'selected':''}>사장님</option>
                        <option value="designer" ${u.role==='designer'?'selected':''}>직원</option>
                    </select>
                    <button class="btn btn-sm btn-primary" onclick="changeUserRole(${u.id})" title="역할 변경"><i class="fas fa-save"></i></button>
                    <button class="btn btn-sm btn-outline-${u.is_active?'warning':'success'}" onclick="toggleUserActive(${u.id})" title="${u.is_active?'활동정지':'활성화'}">
                        <i class="fas fa-${u.is_active?'ban':'check'} me-1"></i>${u.is_active?'활동정지':'활성화'}
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteUser(${u.id}, '${escapeHtml(u.name)}')" title="회원 삭제">
                        <i class="fas fa-trash me-1"></i>삭제
                    </button>
                </div>
            </td>
        </tr>`;
    }).join('');

    c.innerHTML = `
    <div class="row g-3 mb-3">
        <div class="col-md-3"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-3 fw-bold text-danger">${roleCounts.admin}</div><small class="text-muted">최고관리자</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-3 fw-bold text-info">${roleCounts.sales}</div><small class="text-muted">영업관리자</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-3 fw-bold text-primary">${roleCounts.owner}</div><small class="text-muted">사장님</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-3 fw-bold text-warning">${roleCounts.designer}</div><small class="text-muted">직원</small>
        </div></div></div>
    </div>
    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-users-cog me-2"></i>전체 사용자 목록</h5>
            <span class="badge bg-primary">${users.length}명</span>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover table-sm align-middle">
                    <thead class="table-light"><tr><th>ID</th><th>이름</th><th>이메일</th><th>역할</th><th>연락처</th><th>상태</th><th>가입일</th><th>관리</th></tr></thead>
                    <tbody>${rows || '<tr><td colspan="8" class="text-muted text-center py-3">사용자가 없습니다.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>`;
}

async function changeUserRole(uid) {
    const newRole = document.getElementById(`roleSelect${uid}`).value;
    if (!confirm(`이 사용자의 역할을 "${({admin:'최고관리자',sales:'영업관리자',owner:'사장님',designer:'직원'})[newRole]}"(으)로 변경하시겠습니까?`)) return;
    try {
        await apiPut(`/api/admin/users/${uid}/role?role=${newRole}`, {});
        navigate('admin-users');
    } catch (e) { alert('역할 변경 실패: ' + e.message); }
}

async function toggleUserActive(uid) {
    if (!confirm('이 사용자의 활동 상태를 변경하시겠습니까?\n(활성 → 활동정지 / 정지 → 활성화)')) return;
    try {
        await apiPut(`/api/admin/users/${uid}/toggle-active`, {});
        navigate('admin-users');
    } catch (e) { alert('상태 변경 실패: ' + e.message); }
}

async function deleteUser(uid, name) {
    if (!confirm(`[${name}] 회원을 완전히 삭제하시겠습니까?\n\n⚠️ 이 작업은 되돌릴 수 없습니다.`)) return;
    if (!confirm(`정말로 [${name}] 회원을 삭제합니다. 계속하시겠습니까?`)) return;
    try {
        await apiDelete(`/api/admin/users/${uid}`);
        alert(`[${name}] 회원이 삭제되었습니다.`);
        navigate('admin-users');
    } catch (e) { alert('삭제 실패: ' + e.message); }
}

// ─── 영업관리자 관리 (전담 페이지) ──────────────────────────

async function loadAdminSalesManagers(c, t) {
    t.textContent = '영업관리자 관리';
    const users = await apiGet('/api/admin/users?role=sales');
    const assigns = await apiGet('/api/admin/sales-assignments');

    // 영업관리자별 배정 가맹점 매핑
    const assignMap = {};
    assigns.forEach(a => {
        if (!assignMap[a.sales_manager_user_id]) assignMap[a.sales_manager_user_id] = [];
        assignMap[a.sales_manager_user_id].push(a);
    });

    function salesRefLink(code) {
        if (!code) return '-';
        return `${location.origin}/static/login.html?ref=${encodeURIComponent(code)}`;
    }

    let cards = users.map(u => {
        const myAssigns = assignMap[u.id] || [];
        const totalCommission = myAssigns.reduce((s, a) => s + a.commission_rate, 0);
        const refLink = salesRefLink(u.referral_code);
        const assignRows = myAssigns.map(a => `
            <tr>
                <td class="fw-bold">${escapeHtml(a.merchant_name || '-')}</td>
                <td class="text-primary fw-bold">${(a.commission_rate*100).toFixed(2)}%</td>
                <td>${(10000 * a.commission_rate).toLocaleString('ko-KR',{maximumFractionDigits:0})}원</td>
                <td>${a.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
            </tr>`).join('');

        return `
        <div class="col-md-6">
            <div class="card border-0 shadow-sm h-100">
                <div class="card-header bg-info bg-opacity-10 border-0 d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-0 fw-bold"><i class="fas fa-user-tie text-info me-2"></i>${escapeHtml(u.name)}</h6>
                        <small class="text-muted">${escapeHtml(u.email)}</small>
                    </div>
                    <div class="text-end">
                        ${u.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}
                    </div>
                </div>
                <div class="card-body">
                    <!-- 추천 코드 & 링크 -->
                    <div class="mb-3 p-2 bg-light rounded">
                        <div class="d-flex align-items-center gap-2 mb-1">
                            <i class="fas fa-tag text-info" style="width:16px"></i>
                            <span class="small text-muted">추천 코드</span>
                            <strong class="text-dark">${escapeHtml(u.referral_code || '-')}</strong>
                        </div>
                        ${u.referral_code ? `
                        <button class="btn btn-sm btn-outline-info w-100" onclick="copySalesRefLink('${escapeHtml(refLink)}', this)">
                            <i class="fas fa-copy me-1"></i>추천 링크 복사
                        </button>` : ''}
                    </div>
                    <div class="row g-2 mb-3 text-center">
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-primary">${myAssigns.length}</div><small class="text-muted">담당 가맹점</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-success">${myAssigns.filter(a=>a.is_active).length}</div><small class="text-muted">활성 배정</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-warning">${myAssigns.length > 0 ? (totalCommission*100/myAssigns.length).toFixed(1) : '0.0'}%</div><small class="text-muted">평균 커미션</small></div></div>
                    </div>
                    ${myAssigns.length > 0 ? `
                    <h6 class="small fw-bold text-muted mb-2"><i class="fas fa-store me-1"></i>담당 가맹점 현황</h6>
                    <div class="table-responsive">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="table-light"><tr><th>가맹점</th><th>커미션율</th><th>예시(1만원)</th><th>상태</th></tr></thead>
                            <tbody>${assignRows}</tbody>
                        </table>
                    </div>` : `
                    <div class="text-center py-3 text-muted">
                        <i class="fas fa-inbox d-block mb-1 opacity-50"></i>
                        <small>배정된 가맹점이 없습니다</small>
                    </div>`}
                    <div class="mt-3 d-flex gap-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="navigate('admin-sales-assign')" title="가맹점 연결"><i class="fas fa-link me-1"></i>가맹점 연결</button>
                        <button class="btn btn-sm btn-outline-${u.is_active?'danger':'success'}" onclick="toggleUserActive(${u.id})" title="${u.is_active?'비활성화':'활성화'}">
                            <i class="fas fa-${u.is_active?'ban':'check'} me-1"></i>${u.is_active?'비활성화':'활성화'}
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');

    c.innerHTML = `
    <!-- 새 영업관리자 추가 폼 -->
    <div class="card border-0 shadow-sm mb-3">
        <div class="card-header bg-info bg-opacity-10 border-0">
            <h6 class="mb-0 fw-bold"><i class="fas fa-user-plus text-info me-2"></i>새 영업관리자 계정 추가</h6>
        </div>
        <div class="card-body">
            <div class="row g-2 align-items-end">
                <div class="col-md-3">
                    <label class="form-label small fw-bold mb-1">이름</label>
                    <input type="text" class="form-control form-control-sm" id="newSalesName" placeholder="홍길동">
                </div>
                <div class="col-md-3">
                    <label class="form-label small fw-bold mb-1">이메일</label>
                    <input type="email" class="form-control form-control-sm" id="newSalesEmail" placeholder="sales@example.com">
                </div>
                <div class="col-md-3">
                    <label class="form-label small fw-bold mb-1">초기 비밀번호</label>
                    <input type="password" class="form-control form-control-sm" id="newSalesPassword" placeholder="6자 이상">
                </div>
                <div class="col-md-3">
                    <button class="btn btn-info btn-sm w-100 text-white" onclick="createSalesUser()">
                        <i class="fas fa-plus me-1"></i>계정 생성
                    </button>
                </div>
            </div>
            <div id="newSalesAlert" class="mt-2 d-none"></div>
        </div>
    </div>

    <!-- 통계 -->
    <div class="row g-3 mb-3">
        <div class="col-md-4"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-2 fw-bold text-info">${users.length}</div><small class="text-muted">전체 영업관리자</small>
        </div></div></div>
        <div class="col-md-4"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-2 fw-bold text-success">${users.filter(u=>u.is_active).length}</div><small class="text-muted">활성 영업관리자</small>
        </div></div></div>
        <div class="col-md-4"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-2 fw-bold text-primary">${assigns.length}</div><small class="text-muted">전체 가맹점 배정</small>
        </div></div></div>
    </div>

    <!-- 영업관리자 카드 목록 -->
    <div class="row g-3">
        ${cards || '<div class="col-12"><div class="text-center py-5 text-muted"><i class="fas fa-user-tie fa-3x mb-3 d-block opacity-50"></i><p>등록된 영업관리자가 없습니다.</p><small>위 폼에서 새 영업관리자를 추가하세요.</small></div></div>'}
    </div>`;
}

async function createSalesUser() {
    const name = document.getElementById('newSalesName').value.trim();
    const email = document.getElementById('newSalesEmail').value.trim();
    const password = document.getElementById('newSalesPassword').value;
    const alertEl = document.getElementById('newSalesAlert');

    if (!name || !email || !password) {
        alertEl.className = 'mt-2 alert alert-warning py-2 small';
        alertEl.textContent = '이름, 이메일, 비밀번호를 모두 입력하세요';
        alertEl.classList.remove('d-none');
        return;
    }
    try {
        const result = await apiPost('/api/admin/users/create-sales', { name, email, password });
        alertEl.className = 'mt-2 alert alert-success py-2 small';
        alertEl.innerHTML = `<i class="fas fa-check me-1"></i><strong>${escapeHtml(result.name)}</strong> 계정 생성 완료. 추천 코드: <strong>${escapeHtml(result.referral_code)}</strong>`;
        alertEl.classList.remove('d-none');
        document.getElementById('newSalesName').value = '';
        document.getElementById('newSalesEmail').value = '';
        document.getElementById('newSalesPassword').value = '';
        setTimeout(() => navigate('admin-sales-managers'), 1500);
    } catch(e) {
        alertEl.className = 'mt-2 alert alert-danger py-2 small';
        alertEl.textContent = '생성 실패: ' + e.message;
        alertEl.classList.remove('d-none');
    }
}

function copySalesRefLink(link, btn) {
    navigator.clipboard.writeText(link).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check me-1"></i>복사됨!';
        btn.classList.replace('btn-outline-info', 'btn-success');
        setTimeout(() => { btn.innerHTML = orig; btn.classList.replace('btn-success', 'btn-outline-info'); }, 2000);
    }).catch(() => {
        prompt('링크를 복사하세요:', link);
    });
}

// ═══════════════════════════════════════════════════════════
// SALES PAGES
// ═══════════════════════════════════════════════════════════

async function loadSalesMerchants(c, t) {
    t.textContent = '담당 가맹점';
    const merchants = await apiGet('/api/sales/merchants');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>담당 가맹점 현황</h5></div><div class="card-body">
        <div class="row g-3">${merchants.map(m => `
            <div class="col-md-6"><div class="card border shadow-sm"><div class="card-body">
                <h6 class="fw-bold"><i class="fas fa-store text-primary me-2"></i>${escapeHtml(m.name)}</h6>
                <p class="text-muted small mb-1">${escapeHtml(m.address||'')} | ${escapeHtml(m.phone||'')}</p>
                <p class="mb-2">커미션율: <strong class="text-primary">${(m.commission_rate*100).toFixed(1)}%</strong></p>
                <div class="d-flex gap-2 mb-2">
                    <select class="form-select form-select-sm" id="salesRange${m.id}"><option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option></select>
                    <button class="btn btn-sm btn-primary" onclick="loadSalesStats(${m.id})"><i class="fas fa-search"></i></button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="loadSalesBreakdown(${m.id})" title="사장님/직원 분배"><i class="fas fa-sitemap"></i></button>
                </div>
                <div id="salesStats${m.id}"></div>
            </div></div></div>
        `).join('') || '<div class="col-12"><p class="text-muted text-center py-3">배정된 가맹점이 없습니다.</p></div>'}</div>
    </div></div>`;
}

async function loadSalesStats(mid) {
    const range = document.getElementById(`salesRange${mid}`).value;
    const stats = await apiGet(`/api/sales/merchants/${mid}/stats?range=${range}`);
    const commHtml = stats.show_commission
        ? ` | 커미션 <strong class="text-primary">${formatMoney(stats.commission_amount)}</strong>`
        : ' | <span class="text-muted"><i class="fas fa-eye-slash"></i> 커미션 비공개</span>';
    const rateNote = stats.pg_fee_rate != null
        ? `<br><span class="text-muted">PG수수료율 ${fmtRateExclVat(stats.pg_fee_rate)} → 실제 적용 ${(((stats.pg_fee_rate_with_vat ?? applyVat(stats.pg_fee_rate)))*100).toFixed(2)}%</span>`
        : '';
    document.getElementById(`salesStats${mid}`).innerHTML = `<div class="bg-light rounded p-2 small">
        결제 <strong>${stats.transaction_count}건</strong> | 총매출 <strong>${formatMoney(stats.gross_amount)}</strong><br>
        PG수수료 ${formatMoney(stats.pg_fee)} <span class="text-muted">(부가세 포함)</span>${commHtml}${rateNote}
    </div>`;
}

async function loadSalesBreakdown(mid) {
    const range = document.getElementById(`salesRange${mid}`).value;
    const el = document.getElementById(`salesStats${mid}`);
    el.innerHTML = adpayLoadingMarkup();
    try {
        const data = await apiGet(`/api/sales/merchants/${mid}/breakdown?range=${range}`);
        el.innerHTML = renderSettlementBreakdown(data);
    } catch (e) { el.innerHTML = `<div class="alert alert-danger small">${escapeHtml(e.message)}</div>`; }
}

async function loadSalesCommission(c, t) {
    t.textContent = '커미션 현황';
    const stats = await apiGet('/api/sales/dashboard-stats');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>커미션 현황</h5></div><div class="card-body">
        <div class="row g-3 mb-4">
            <div class="col-md-4"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-primary">${stats.show_commission===false?'<i class="fas fa-eye-slash"></i>':formatMoney(stats.total_commission)}</div><div class="small text-muted">누적 커미션${stats.show_commission===false?' (비공개)':''}</div></div></div>
            <div class="col-md-4"><div class="bg-success bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-success">${formatMoney(stats.month_sales)}</div><div class="small text-muted">이번달 매출</div></div></div>
            <div class="col-md-4"><div class="bg-warning bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-warning">${stats.merchant_count}개</div><div class="small text-muted">담당 가맹점</div></div></div>
        </div>
        <p class="text-muted text-center">각 가맹점별 상세 커미션은 <a href="#" onclick="navigate('sales-merchants')">담당 가맹점</a> 메뉴에서 확인하세요.</p>
    </div></div>`;
}

async function loadSalesPayouts(c, t) {
    t.textContent = '출금요청';
    const payouts = await apiGet('/api/sales/payout-requests');
    c.innerHTML = `<div class="row g-4">
        <div class="col-md-5">
            <div class="card data-card"><div class="card-header"><h5>새 출금요청</h5></div><div class="card-body">
                <div class="mb-3"><label class="form-label">금액</label><input type="number" class="form-control" id="payoutAmt"></div>
                <div class="mb-3"><label class="form-label">은행정보</label><input class="form-control" id="payoutBank" placeholder="은행명 계좌번호 예금주"></div>
                <div class="mb-3"><label class="form-label">메모</label><textarea class="form-control" id="payoutMemo" rows="2"></textarea></div>
                <button class="btn btn-primary w-100" onclick="createPayout()"><i class="fas fa-paper-plane me-1"></i>요청</button>
                <div id="payoutResult" class="mt-2"></div>
            </div></div>
        </div>
        <div class="col-md-7">
            <div class="card data-card"><div class="card-header"><h5>출금요청 내역</h5></div><div class="card-body">
                <div class="table-responsive"><table class="table table-sm">
                    <thead><tr><th>ID</th><th>금액</th><th>은행정보</th><th>상태</th><th>요청일</th></tr></thead>
                    <tbody>${payouts.map(p => `<tr><td>${p.id}</td><td class="fw-bold">${formatMoney(p.amount)}</td><td>${escapeHtml(p.bank_info)||'-'}</td><td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td></tr>`).join('')}</tbody>
                </table></div>
            </div></div>
        </div>
    </div>`;
}

async function createPayout() {
    try {
        await apiPost('/api/sales/payout-requests', { amount: parseFloat(document.getElementById('payoutAmt').value), bank_info: document.getElementById('payoutBank').value, memo: document.getElementById('payoutMemo').value });
        document.getElementById('payoutResult').innerHTML = '<span class="text-success"><i class="fas fa-check-circle"></i> 요청 완료!</span>';
        navigate('sales-payouts');
    } catch (e) { document.getElementById('payoutResult').innerHTML = `<span class="text-danger">${escapeHtml(e.message)}</span>`; }
}

async function loadSalesPayoutHistory(c, t) {
    t.textContent = '출금내역';
    const payouts = await apiGet('/api/sales/payout-requests');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>전체 출금내역</h5></div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm">
            <thead><tr><th>ID</th><th>금액</th><th>은행정보</th><th>상태</th><th>요청일</th></tr></thead>
            <tbody>${payouts.map(p => `<tr><td>${p.id}</td><td class="fw-bold">${formatMoney(p.amount)}</td><td>${escapeHtml(p.bank_info)||'-'}</td><td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td></tr>`).join('') || '<tr><td colspan="5" class="text-muted text-center py-3">없음</td></tr>'}</tbody>
        </table></div></div></div>`;
}

// ═══════════════════════════════════════════════════════════
// OWNER PAGES
// ═══════════════════════════════════════════════════════════

async function loadOwnerTransactions(c, t, initialTab = 'general') {
    t.textContent = '결제 내역';
    c.innerHTML = `
    <div class="owner-payment-page">
        <div class="owner-payment-tabs" role="tablist" aria-label="결제 내역 보기">
            <button type="button" class="owner-payment-tab" role="tab" data-payment-tab="general"
                onclick="activateOwnerPaymentTab('general')">
                <span class="owner-payment-tab-icon"><i class="fas fa-receipt"></i></span>
                <span><strong>일반 결제내역</strong><small>건별 승인 내역을 확인해요</small></span>
            </button>
            <button type="button" class="owner-payment-tab" role="tab" data-payment-tab="daily"
                onclick="activateOwnerPaymentTab('daily')">
                <span class="owner-payment-tab-icon"><i class="fas fa-calendar-day"></i></span>
                <span><strong>일별 결제내역</strong><small>날짜별 매출을 한눈에 봐요</small></span>
            </button>
        </div>
        <div id="ownerPaymentTabPanel" class="owner-payment-tab-panel" role="tabpanel"></div>
    </div>`;
    await activateOwnerPaymentTab(initialTab);
}

async function activateOwnerPaymentTab(tab = 'general') {
    const selectedTab = tab === 'daily' ? 'daily' : 'general';
    document.querySelectorAll('.owner-payment-tab').forEach(button => {
        const isActive = button.dataset.paymentTab === selectedTab;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-selected', String(isActive));
        button.tabIndex = isActive ? 0 : -1;
    });

    const panel = document.getElementById('ownerPaymentTabPanel');
    if (!panel) return;
    panel.innerHTML = adpayLoadingMarkup();
    if (selectedTab === 'daily') {
        await loadOwnerDailySummary(panel, { textContent: '' });
    } else {
        await renderOwnerTransactionList(panel);
    }
}

async function renderOwnerTransactionList(c) {
    c.innerHTML = `<div class="card data-card owner-payment-list-card"><div class="card-header d-flex justify-content-between align-items-center">
        <div><h5 class="mb-1">일반 결제내역</h5><small class="text-muted">승인된 결제를 건별로 확인할 수 있어요.</small></div>
        <select class="form-select form-select-sm" style="width:120px" id="ownerTxRange" onchange="reloadOwnerTx()">
            <option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option>
        </select>
    </div><div class="card-body">
        <div id="ownerTxBody">${adpayLoadingMarkup()}</div>
    </div></div>`;
    reloadOwnerTx();
}

async function reloadOwnerTx() {
    const rangeSelect = document.getElementById('ownerTxRange');
    const body = document.getElementById('ownerTxBody');
    if (!rangeSelect || !body) return;
    const range = rangeSelect.value;
    const txns = await apiGet(`/api/owner/transactions?range=${range}`);
    const total = txns.reduce((s, tx) => s + tx.amount, 0);
    if (!document.getElementById('ownerTxBody')) return;
    body.innerHTML = `
    <div class="d-flex justify-content-between mb-3">
        <span>합계: <strong class="text-primary">${formatMoney(total)}</strong> (${txns.length}건)</span>
    </div>
    <div class="table-responsive"><table class="table table-hover table-sm">
        <thead><tr><th>ID</th><th>금액</th><th>할부</th><th>카드</th><th>직원</th><th>승인번호</th><th>일시</th></tr></thead>
        <tbody>${txns.map(tx => `<tr>
            <td>${tx.id}</td><td class="fw-bold">${formatMoney(tx.amount)}</td>
            <td>${tx.installment_months||'일시불'}</td><td>${escapeHtml(tx.card_brand||'-')}</td>
            <td>${escapeHtml(tx.staff_name)||'<span class="text-muted">사장님</span>'}</td><td><code>${escapeHtml(tx.approval_code||'-')}</code></td>
            <td>${formatDate(tx.created_at)}</td>
        </tr>`).join('')}</tbody>
    </table></div>`;
}

async function loadOwnerStaff(c, t) {
    t.textContent = '직원 관리';
    const staff = await apiGet('/api/owner/staff');
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h5 class="mb-0">직원 계정 목록</h5>
        <div class="d-flex gap-2 staff-mgmt-header-btns">
            <button class="btn btn-primary btn-sm" onclick="showNewDesignerForm()"><i class="fas fa-user-plus me-1"></i>직원 계정 등록</button>
            <button class="btn btn-outline-secondary btn-sm" onclick="showNewStaffForm()"><i class="fas fa-plus me-1"></i>직원 추가(계정 없음)</button>
        </div>
    </div><div class="card-body">
        <div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
            <strong>직원 계정 등록</strong>은 로그인 계정을 만들어 우리 매장 소속으로 귀속시킵니다(직원은 직접 회원가입 불가). <strong>분배율</strong>은 결제액에서 PG·영업수수료를 뺀 <strong>분배가능액 중 직원 몫</strong> 비율이며, 나머지는 사장님 몫입니다.</div>
        <div class="table-responsive"><table class="table table-hover align-middle staff-mgmt-table">
            <thead><tr><th>ID</th><th>이름</th><th>코드</th><th>직원 분배율</th><th>상태</th><th>액션</th></tr></thead>
            <tbody>${staff.map(s => `<tr>
                <td data-label="ID">${s.id}</td><td class="fw-bold" data-label="이름">${escapeHtml(s.name)}</td><td data-label="코드"><code>${escapeHtml(s.staff_code)}</code></td>
                <td data-label="분배율" style="max-width:200px">
                    <div class="input-group input-group-sm">
                        <input type="number" class="form-control" id="share_${s.id}" value="${Math.round((s.share_rate??0.5)*100)}" min="0" max="100" step="1" style="max-width:80px">
                        <span class="input-group-text">%</span>
                        <button class="btn btn-outline-success" onclick="saveStaffShareRate(${s.id})" title="분배율 저장"><i class="fas fa-save"></i></button>
                    </div>
                    <small class="text-muted">사장님 몫 <span id="ownerShare_${s.id}">${100-Math.round((s.share_rate??0.5)*100)}</span>%</small>
                </td>
                <td data-label="상태">${s.is_active?'<span class="badge bg-success">활성</span>':'<span class="badge bg-danger">비활성</span>'}</td>
                <td data-label="액션"><button class="btn btn-sm btn-outline-${s.is_active?'danger':'success'}" onclick="toggleStaff(${s.id},${!s.is_active})">${s.is_active?'비활성화':'활성화'}</button></td>
            </tr>`).join('')}</tbody>
        </table></div></div></div>`;
    // 입력 시 사장님 몫 즉시 반영
    staff.forEach(s => {
        const inp = document.getElementById(`share_${s.id}`);
        if (inp) inp.addEventListener('input', () => {
            const v = Math.max(0, Math.min(100, parseInt(inp.value) || 0));
            const os = document.getElementById(`ownerShare_${s.id}`);
            if (os) os.textContent = 100 - v;
        });
    });
}

async function saveStaffShareRate(sid) {
    const inp = document.getElementById(`share_${sid}`);
    const pct = Math.max(0, Math.min(100, parseInt(inp.value) || 0));
    try {
        await apiPut(`/api/owner/staff/${sid}`, { share_rate: pct / 100 });
        alert(`분배율 저장 완료!\n직원 ${pct}% / 사장님 ${100-pct}%`);
    } catch (e) { alert('저장 실패: ' + e.message); }
}

async function showNewStaffForm() {
    resetFormModalFooter(true);
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '직원 추가';
    body.innerHTML = `<div class="row g-3">
        <div class="col-md-6"><label class="form-label">이름</label><input class="form-control" id="fStaffName"></div>
        <div class="col-md-6"><label class="form-label">직원 코드</label><input class="form-control" id="fStaffCode" placeholder="단말기 입력용 번호"></div>
        <div class="col-md-6"><label class="form-label">직원 분배율 (%)</label><input class="form-control" id="fStaffShare" type="number" value="50" min="0" max="100" step="1"><small class="text-muted">분배가능액 중 직원 몫</small></div>
        <div class="col-md-6"><label class="form-label">User ID (선택)</label><input class="form-control" id="fStaffUser" type="number" placeholder="시스템 계정 연결 시"></div>
    </div>`;
    document.getElementById('formModalSave').onclick = async () => {
        const pct = Math.max(0, Math.min(100, parseInt(document.getElementById('fStaffShare').value) || 50));
        await apiPost('/api/owner/staff', { name: document.getElementById('fStaffName').value, staff_code: document.getElementById('fStaffCode').value, user_id: parseInt(document.getElementById('fStaffUser').value) || null, share_rate: pct / 100 });
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        navigate('owner-staff');
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

async function toggleStaff(sid, active) { await apiPut(`/api/owner/staff/${sid}`, { is_active: active }); navigate('owner-staff'); }

async function showNewDesignerForm() {
    resetFormModalFooter(true);
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '직원 계정 등록';
    body.innerHTML = `<div class="row g-3">
        <div class="col-12"><div class="alert alert-info py-2 mb-1 small"><i class="fas fa-id-card-clip me-1"></i>직원 로그인 계정을 생성하고 <strong>우리 매장 소속</strong>으로 등록합니다.</div></div>
        <div class="col-md-6"><label class="form-label">이름 <span class="text-danger">*</span></label><input class="form-control" id="fDsgName"></div>
        <div class="col-md-6"><label class="form-label">직원 코드 <span class="text-danger">*</span></label><input class="form-control" id="fDsgCode" placeholder="단말기 입력용 번호"></div>
        <div class="col-md-6"><label class="form-label">이메일(로그인 ID) <span class="text-danger">*</span></label><input class="form-control" id="fDsgEmail" type="email" placeholder="designer@example.com"></div>
        <div class="col-md-6"><label class="form-label">비밀번호 <span class="text-danger">*</span></label><input class="form-control" id="fDsgPw" type="text" placeholder="6자 이상"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="fDsgPhone" placeholder="010-0000-0000"></div>
        <div class="col-md-6"><label class="form-label">직원 분배율 (%)</label><input class="form-control" id="fDsgShare" type="number" value="50" min="0" max="100" step="1"></div>
        <div class="col-12"><div id="fDsgResult"></div></div>
    </div>`;
    document.getElementById('formModalSave').onclick = async () => {
        const name = document.getElementById('fDsgName').value.trim();
        const code = document.getElementById('fDsgCode').value.trim();
        const email = document.getElementById('fDsgEmail').value.trim();
        const pw = document.getElementById('fDsgPw').value;
        const phone = document.getElementById('fDsgPhone').value.trim();
        const pct = Math.max(0, Math.min(100, parseInt(document.getElementById('fDsgShare').value) || 50));
        const result = document.getElementById('fDsgResult');
        if (!name || !code || !email || !pw) { result.innerHTML = `<div class="alert alert-warning py-2 mb-0">이름·코드·이메일·비밀번호는 필수입니다.</div>`; return; }
        if (pw.length < 6) { result.innerHTML = `<div class="alert alert-warning py-2 mb-0">비밀번호는 6자 이상이어야 합니다.</div>`; return; }
        try {
            const res = await apiPost('/api/owner/designers', { name, staff_code: code, email, password: pw, phone: phone || null, share_rate: pct / 100 });
            bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
            alert(res.message || '직원 계정이 등록되었습니다.');
            navigate('owner-staff');
        } catch (e) { result.innerHTML = `<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

// ─── 정산 분배 (직원/사장님) ─────────────────────────────
function rangeSelectHtml(id, current) {
    const opts = [['month','이번달'],['week','이번주'],['day','오늘'],['all','전체']];
    return `<select class="form-select form-select-sm" id="${id}" style="max-width:140px">${opts.map(([v,l])=>`<option value="${v}" ${v===current?'selected':''}>${l}</option>`).join('')}</select>`;
}

/**
 * 정산 화면용 수수료율 안내 — 저장된 수수료율은 부가세 별도이고, 금액은 × 1.1 적용된 값이다.
 * data 에 *_with_vat 필드가 없으면(구버전 응답) 별도 값에서 직접 환산한다.
 */
function feeRateVatNote(data) {
    const mfr = data.merchant_fee_rate, pgr = data.pg_fee_rate;
    if (mfr == null && pgr == null) return '';
    const parts = [];
    if (mfr != null) parts.push(`가맹점 수수료 ${fmtRateExclVat(mfr)} → 실제 ${(((data.merchant_fee_rate_with_vat ?? applyVat(mfr)))*100).toFixed(2)}%`);
    if (pgr != null) parts.push(`PG 수수료 ${fmtRateExclVat(pgr)} → 실제 ${(((data.pg_fee_rate_with_vat ?? applyVat(pgr)))*100).toFixed(2)}%`);
    return `<div class="alert alert-light border small py-2 mb-3">
        <i class="fas fa-percent text-warning me-1"></i>${parts.join(' &nbsp;·&nbsp; ')}
        <span class="text-muted d-block mt-1">수수료 금액은 부가세(VAT 10%)가 포함된 실제 적용율 기준입니다.</span>
    </div>`;
}

function renderSettlementBreakdown(data) {
    const showComm = data.show_sales_commission;
    const feeRateNote = feeRateVatNote(data);
    const commRow = showComm
        ? `<div class="col-6 col-md-3"><div class="bg-warning bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-warning">${formatMoney(data.sales_commission)}</div><small class="text-muted">영업수수료${data.sales_commission_rate!=null?` (${(data.sales_commission_rate*100).toFixed(1)}%)`:''}</small></div></div>`
        : '';
    const colClass = showComm ? 'col-6 col-md-3' : 'col-6 col-md-4';
    const designerRows = (data.designers||[]).map(d => `<tr>
        <td class="fw-bold">${escapeHtml(d.name)}</td>
        <td><code>${escapeHtml(d.staff_code)}</code></td>
        <td class="text-end">${formatMoney(d.gross)}<br><small class="text-muted">${d.count}건</small></td>
        <td class="text-end text-secondary">-${formatMoney(d.pg_fee)}</td>
        ${showComm ? `<td class="text-end text-secondary">-${formatMoney(d.sales_commission||0)}</td>` : ''}
        <td class="text-end fw-bold">${formatMoney(d.distributable)}</td>
        <td class="text-center"><span class="badge bg-primary">${Math.round((d.share_rate||0)*100)}%</span></td>
        <td class="text-end fw-bold text-primary">${formatMoney(d.designer_amount)}</td>
        <td class="text-end text-success">${formatMoney(d.owner_amount)}</td>
    </tr>`).join('');
    const unassigned = data.unassigned && data.unassigned.count > 0
        ? `<tr class="table-light"><td class="fw-bold">미귀속</td><td>-</td>
            <td class="text-end">${formatMoney(data.unassigned.gross)}<br><small class="text-muted">${data.unassigned.count}건</small></td>
            <td colspan="${showComm?2:1}"></td>
            <td class="text-end fw-bold">${formatMoney(data.unassigned.distributable)}</td>
            <td class="text-center">-</td><td class="text-end">-</td>
            <td class="text-end text-success">${formatMoney(data.unassigned.owner_amount)}</td></tr>`
        : '';
    return `
    <div class="row g-2 mb-3">
        <div class="${colClass}"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(data.gross)}</div><small class="text-muted">총 결제액</small></div></div>
        <div class="${colClass}"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold text-secondary">${formatMoney(data.pg_fee)}</div><small class="text-muted">PG 수수료 <span class="text-nowrap">(부가세 포함)</span></small></div></div>
        ${commRow}
        <div class="${colClass}"><div class="bg-primary bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-primary">${formatMoney(data.distributable)}</div><small class="text-muted">분배가능액</small></div></div>
    </div>
    ${feeRateNote}
    <div class="row g-2 mb-3">
        <div class="col-6"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-5 fw-bold text-primary">${formatMoney(data.designer_total)}</div><small class="text-muted">직원 분배 합계</small></div></div>
        <div class="col-6"><div class="bg-success bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-5 fw-bold text-success">${formatMoney(data.owner_amount)}</div><small class="text-muted">사장님 몫</small></div></div>
    </div>
    <div class="table-responsive"><table class="table table-sm table-hover align-middle">
        <thead class="table-light"><tr>
            <th>직원</th><th>코드</th><th class="text-end">매출</th>
            <th class="text-end">PG<br><small class="text-muted fw-normal">(부가세 포함)</small></th>
            ${showComm?'<th class="text-end">영업</th>':''}
            <th class="text-end">분배가능</th><th class="text-center">분배율</th>
            <th class="text-end">직원 몫</th><th class="text-end">사장님 몫</th>
        </tr></thead>
        <tbody>${designerRows || `<tr><td colspan="9" class="text-center text-muted py-3">데이터 없음</td></tr>`}${unassigned}</tbody>
    </table></div>
    ${!showComm ? '<small class="text-muted"><i class="fas fa-eye-slash me-1"></i>영업수수료 항목은 관리자 설정에 의해 표시되지 않습니다.</small>' : ''}`;
}

async function loadOwnerSettlement(c, t) {
    t.textContent = '정산 분배';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">직원 정산 분배</h5>${rangeSelectHtml('ownerSettleRange','month')}
    </div><div class="card-body" id="ownerSettleBody">${adpayLoadingMarkup()}</div></div>`;
    const render = async () => {
        const range = document.getElementById('ownerSettleRange').value;
        const body = document.getElementById('ownerSettleBody');
        body.innerHTML = adpayLoadingMarkup();
        try {
            const data = await apiGet(`/api/owner/settlement-breakdown?range=${range}`);
            body.innerHTML = renderSettlementBreakdown(data);
        } catch (e) { body.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
    };
    document.getElementById('ownerSettleRange').addEventListener('change', render);
    render();
}

// ─── 정산 내역 / 출금요청 (사장님) ────────────────────────────

async function loadOwnerSettlements(c, t) {
    t.textContent = '정산 내역';
    const rows = await apiGet('/api/owner/settlements');
    const showComm = rows.length ? rows[0].show_sales_commission : true;
    const totalNet = rows.reduce((s, r) => s + r.net_amount, 0);
    const period = r => `${formatDate(r.period_start).split(' ')[0]} ~ ${formatDate(r.period_end).split(' ')[0]}`;

    c.innerHTML = `
    <div class="row g-3 mb-3">
        <div class="col-6 col-md-4"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-5 fw-bold text-primary">${formatMoney(totalNet)}</div><small class="text-muted">누적 실지급액</small></div></div>
        <div class="col-6 col-md-4"><div class="bg-light rounded-3 p-3 text-center"><div class="fs-5 fw-bold">${rows.length}건</div><small class="text-muted">확정된 정산</small></div></div>
    </div>
    <div class="card data-card"><div class="card-header"><h5 class="mb-0"><i class="fas fa-file-invoice-dollar me-2"></i>확정 정산 내역</h5></div>
    <div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm align-middle">
            <thead class="table-light"><tr>
                <th>정산기간</th><th class="text-end">총 결제액</th>
                <th class="text-end">PG 수수료<br><small class="text-muted fw-normal">(부가세 포함)</small></th>
                ${showComm ? '<th class="text-end">영업수수료</th>' : ''}
                <th class="text-end">실지급액</th><th>확정일</th>
            </tr></thead>
            <tbody>${rows.map(r => `<tr>
                <td class="fw-bold">${period(r)}</td>
                <td class="text-end">${formatMoney(r.gross_amount)}</td>
                <td class="text-end text-secondary">-${formatMoney(r.pg_fee_amount)}</td>
                ${showComm ? `<td class="text-end text-secondary">${formatMoney(r.commission_amount || 0)}</td>` : ''}
                <td class="text-end fw-bold text-primary">${formatMoney(r.net_amount)}</td>
                <td>${formatDate(r.created_at)}</td>
            </tr>`).join('') || `<tr><td colspan="${showComm ? 6 : 5}" class="text-center text-muted py-4">아직 확정된 정산이 없습니다. 최고관리자가 정산을 계산하면 이곳에 표시됩니다.</td></tr>`}</tbody>
        </table></div>
        <small class="text-muted d-block"><i class="fas fa-percent me-1"></i>수수료 금액은 부가세(VAT 10%)가 포함된 실제 적용율 기준입니다. (설정된 수수료율은 부가세 별도)</small>
        ${!showComm ? '<small class="text-muted"><i class="fas fa-eye-slash me-1"></i>영업수수료 항목은 관리자 설정에 의해 표시되지 않습니다.</small>' : ''}
    </div></div>`;
}

async function loadOwnerPayouts(c, t) {
    t.textContent = '출금 요청';
    const payouts = await apiGet('/api/owner/payout-requests');
    const pendingSum = payouts.filter(p => p.status === 'pending').reduce((s, p) => s + p.amount, 0);

    c.innerHTML = `<div class="row g-4">
        <div class="col-md-5">
            <div class="card data-card"><div class="card-header"><h5 class="mb-0"><i class="fas fa-money-bill-wave me-2"></i>새 출금요청</h5></div><div class="card-body">
                <div class="mb-3"><label class="form-label fw-bold">금액</label><input type="number" min="1" class="form-control" id="ownerPayoutAmt" placeholder="예: 500000"></div>
                <div class="mb-3"><label class="form-label fw-bold">입금 계좌</label><input class="form-control" id="ownerPayoutBank" placeholder="은행명 계좌번호 예금주"></div>
                <div class="mb-3"><label class="form-label fw-bold">메모</label><textarea class="form-control" id="ownerPayoutMemo" rows="2" placeholder="선택 입력"></textarea></div>
                <button class="btn btn-primary w-100" onclick="createOwnerPayout()"><i class="fas fa-paper-plane me-1"></i>출금 요청</button>
                <div id="ownerPayoutResult" class="mt-2"></div>
                <div class="alert alert-light border small mt-3 mb-0"><i class="fas fa-info-circle text-primary me-1"></i>요청은 최고관리자 승인 후 지급됩니다.</div>
            </div></div>
        </div>
        <div class="col-md-7">
            <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">요청 내역</h5>
                <span class="badge bg-warning">대기 ${formatMoney(pendingSum)}</span>
            </div><div class="card-body">
                <div class="table-responsive"><table class="table table-sm table-hover align-middle">
                    <thead class="table-light"><tr><th>ID</th><th class="text-end">금액</th><th>입금 계좌</th><th>상태</th><th>요청일</th></tr></thead>
                    <tbody>${payouts.map(p => `<tr>
                        <td>${p.id}</td><td class="text-end fw-bold">${formatMoney(p.amount)}</td>
                        <td>${escapeHtml(p.bank_info || '-')}</td>
                        <td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td>
                    </tr>`).join('') || '<tr><td colspan="5" class="text-center text-muted py-4">출금요청 내역이 없습니다</td></tr>'}</tbody>
                </table></div>
            </div></div>
        </div>
    </div>`;
}

async function createOwnerPayout() {
    const el = document.getElementById('ownerPayoutResult');
    const amount = parseFloat(document.getElementById('ownerPayoutAmt').value);
    if (!amount || amount <= 0) {
        el.innerHTML = '<span class="text-danger">출금 금액을 입력해주세요.</span>';
        return;
    }
    try {
        await apiPost('/api/owner/payout-requests', {
            amount,
            bank_info: document.getElementById('ownerPayoutBank').value,
            memo: document.getElementById('ownerPayoutMemo').value,
        });
        navigate('owner-payouts');
    } catch (e) { el.innerHTML = `<span class="text-danger">${escapeHtml(e.message)}</span>`; }
}

async function loadDesignerSettlement(c, t) {
    t.textContent = '정산 분배';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">내 정산 분배</h5>${rangeSelectHtml('dsgSettleRange','month')}
    </div><div class="card-body" id="dsgSettleBody">${adpayLoadingMarkup()}</div></div>`;
    const render = async () => {
        const range = document.getElementById('dsgSettleRange').value;
        const body = document.getElementById('dsgSettleBody');
        body.innerHTML = adpayLoadingMarkup();
        try {
            const d = await apiGet(`/api/designer/settlement?range=${range}`);
            const showComm = d.show_sales_commission;
            body.innerHTML = `
            <div class="row g-2 mb-3">
                <div class="col-6 col-md-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(d.gross)}</div><small class="text-muted">내 매출 (${d.count}건)</small></div></div>
                <div class="col-6 col-md-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold text-secondary">${formatMoney(d.pg_fee)}</div><small class="text-muted">PG 수수료 <span class="text-nowrap">(부가세 포함)</span></small></div></div>
                ${showComm?`<div class="col-6 col-md-3"><div class="bg-warning bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-warning">${formatMoney(d.sales_commission)}</div><small class="text-muted">영업수수료${d.sales_commission_rate!=null?` (${(d.sales_commission_rate*100).toFixed(1)}%)`:''}</small></div></div>`:''}
                <div class="col-6 col-md-3"><div class="bg-primary bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-primary">${formatMoney(d.distributable)}</div><small class="text-muted">분배가능액</small></div></div>
            </div>
            ${feeRateVatNote(d)}
            <div class="row g-2">
                <div class="col-6"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-primary">${formatMoney(d.designer_amount)}</div><small class="text-muted">내 몫 (분배율 ${Math.round((d.share_rate||0)*100)}%)</small></div></div>
                <div class="col-6"><div class="bg-light rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-success">${formatMoney(d.owner_amount)}</div><small class="text-muted">사장님 몫</small></div></div>
            </div>
            ${!showComm?'<small class="text-muted mt-2 d-block"><i class="fas fa-eye-slash me-1"></i>영업수수료 항목은 관리자 설정에 의해 표시되지 않습니다.</small>':''}`;
        } catch (e) { body.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
    };
    document.getElementById('dsgSettleRange').addEventListener('change', render);
    render();
}

async function loadAdminCommissionVisibility(c, t) {
    t.textContent = '수수료 표시 설정';
    const v = await apiGet('/api/admin/commission-visibility');
    const row = (key, label, desc, on, disabled) => `
        <div class="d-flex justify-content-between align-items-center py-3 border-bottom">
            <div><div class="fw-bold">${label}</div><small class="text-muted">${desc}</small></div>
            <div class="form-check form-switch fs-5">
                <input class="form-check-input" type="checkbox" id="cv_${key}" ${on?'checked':''} ${disabled?'disabled':''} onchange="saveCommissionVisibility('${key}', this.checked)">
            </div>
        </div>`;
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5 class="mb-0"><i class="fas fa-eye me-2"></i>영업수수료 표시 설정</h5></div>
    <div class="card-body">
        <div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
            각 역할이 자기 <strong>하위 단계의 영업수수료</strong>를 볼 수 있는지 설정합니다. OFF 로 두면 해당 역할에게 영업수수료 금액이 표시되지 않습니다. (최고관리자는 항상 표시)</div>
        ${row('admin','최고관리자','전체 영업수수료 항상 조회', true, true)}
        ${row('sales','딜러(영업관리자)','담당 가맹점의 커미션·하위 분배 표시', v.sales, false)}
        ${row('owner','사장님','정산 분배에서 영업수수료 항목 표시', v.owner, false)}
        ${row('designer','직원','내 정산에서 영업수수료 항목 표시', v.designer, false)}
    </div></div>`;
}

async function saveCommissionVisibility(role, enabled) {
    try {
        await apiPut('/api/admin/commission-visibility', { [role]: enabled });
    } catch (e) {
        alert('저장 실패: ' + e.message);
        const cb = document.getElementById(`cv_${role}`);
        if (cb) cb.checked = !enabled;
    }
}

async function loadOwnerStaffSales(c, t) {
    t.textContent = '직원별 매출';
    const staff = await apiGet('/api/owner/staff');
    if (!staff.length) {
        c.innerHTML = `<div class="empty-state"><i class="fas fa-user-plus"></i><h3>등록된 직원이 없습니다</h3><p>직원을 먼저 등록하면 직원별 결제와 매출을 조회할 수 있습니다.</p><button class="btn btn-primary" onclick="navigate('owner-staff')">직원 등록하기</button></div>`;
        return;
    }
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>직원별 매출 조회</h5></div><div class="card-body">
        <div class="row g-3 mb-3">
            <div class="col-md-4"><label class="form-label">직원</label><select class="form-select" id="staffSalesSel">${staff.map(s=>`<option value="${s.id}">${escapeHtml(s.name)} (코드:${escapeHtml(s.staff_code)})</option>`).join('')}</select></div>
            <div class="col-md-4"><label class="form-label">기간</label><select class="form-select" id="staffSalesRange"><option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option></select></div>
            <div class="col-md-4 d-flex align-items-end"><button class="btn btn-primary w-100" onclick="loadStaffSalesData()"><i class="fas fa-search me-1"></i>조회</button></div>
        </div><div id="staffSalesResult"></div>
    </div></div>`;
    await loadStaffSalesData();
}

async function loadStaffSalesData() {
    const sid = document.getElementById('staffSalesSel').value;
    const range = document.getElementById('staffSalesRange').value;
    const result = document.getElementById('staffSalesResult');
    result.innerHTML = adpayLoadingMarkup();
    try {
        const data = await apiGet(`/api/owner/staff/${sid}/sales?range=${range}`);
        result.innerHTML = `
        <div class="metric-summary mb-3">
            <div><span>직원</span><strong>${escapeHtml(data.staff_name)}</strong></div>
            <div><span>결제 건수</span><strong>${data.count}건</strong></div>
            <div><span>총 매출</span><strong class="text-primary">${formatMoney(data.total_amount)}</strong></div>
        </div>
        ${data.transactions.length ? `<div class="table-responsive"><table class="table table-sm staff-sales-tx-table">
            <thead><tr><th>ID</th><th>금액</th><th>승인일</th><th>등록일</th></tr></thead>
            <tbody>${data.transactions.map(tx=>`<tr><td data-label="ID">${tx.id}</td><td class="fw-bold" data-label="금액">${formatMoney(tx.amount)}</td><td data-label="승인일">${formatDate(tx.approved_at)}</td><td data-label="등록일">${formatDate(tx.created_at)}</td></tr>`).join('')}</tbody>
        </table></div>` : '<div class="empty-state compact"><i class="fas fa-receipt"></i><p>선택한 기간에 결제 내역이 없습니다.</p></div>'}`;
    } catch (e) {
        result.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

async function loadOwnerDailySummary(c, t) {
    if (t) t.textContent = '일별 결제내역';
    const now = new Date();
    let calYear = now.getFullYear();
    let calMonth = now.getMonth() + 1;

    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-calendar-alt text-info me-2"></i>일별 결제내역</h5>
        <div class="d-flex align-items-center gap-2">
            <button class="btn btn-sm btn-outline-secondary" id="calPrev"><i class="fas fa-chevron-left"></i></button>
            <span class="fw-bold" id="calTitle" style="min-width:120px;text-align:center;">${calYear}년 ${calMonth}월</span>
            <button class="btn btn-sm btn-outline-secondary" id="calNext"><i class="fas fa-chevron-right"></i></button>
        </div>
    </div><div class="card-body p-2 p-md-3">
        <div id="calendarGrid"></div>
        <div id="calMonthTotal" class="text-center mt-2"></div>
    </div></div>`;

    async function renderCalendar() {
        document.getElementById('calTitle').textContent = `${calYear}년 ${calMonth}월`;
        const grid = document.getElementById('calendarGrid');
        grid.innerHTML = adpayLoadingMarkup();
        try {
            const data = await apiGet(`/api/owner/calendar-monthly?year=${calYear}&month=${calMonth}`);
            const dailyMap = {};
            let monthTotal = 0, monthCount = 0;
            (data.days || []).forEach(d => { dailyMap[d.date] = d; monthTotal += d.total; monthCount += d.count; });
            document.getElementById('calMonthTotal').innerHTML = `<span class="badge bg-primary bg-opacity-10 text-primary px-3 py-2" style="font-size:.85rem;">월 합계: <strong>${formatMoney(monthTotal)}</strong> (${monthCount}건)</span>`;

            const firstDay = new Date(calYear, calMonth - 1, 1).getDay(); // 0=Sun
            const daysInMonth = new Date(calYear, calMonth, 0).getDate();
            const today = new Date();
            const todayStr = today.getFullYear() + '-' + String(today.getMonth()+1).padStart(2,'0') + '-' + String(today.getDate()).padStart(2,'0');

            let html = '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;">';
            // Header
            ['일','월','화','수','목','금','토'].forEach((d,i) => {
                html += `<div style="text-align:center;font-weight:700;font-size:.75rem;padding:6px 2px;color:${i===0?'#dc3545':i===6?'#0d6efd':'#6c757d'}">${d}</div>`;
            });
            // Empty cells
            for (let i = 0; i < firstDay; i++) html += '<div></div>';
            // Days
            for (let d = 1; d <= daysInMonth; d++) {
                const dateStr = `${calYear}-${String(calMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
                const dayData = dailyMap[dateStr];
                const isToday = dateStr === todayStr;
                const dayOfWeek = new Date(calYear, calMonth-1, d).getDay();
                const textColor = dayOfWeek === 0 ? '#dc3545' : dayOfWeek === 6 ? '#0d6efd' : '#333';
                const hasSales = dayData && dayData.total > 0;
                html += `<div onclick="showDailyDetail('${dateStr}')" style="cursor:pointer;border:1px solid ${isToday?'#0d6efd':'#e9ecef'};border-radius:8px;padding:4px;min-height:60px;background:${isToday?'rgba(13,110,253,.05)':'#fff'};transition:all .15s;" onmouseover="this.style.boxShadow='0 2px 8px rgba(0,0,0,.1)'" onmouseout="this.style.boxShadow='none'">
                    <div style="font-size:.78rem;font-weight:${isToday?'800':'600'};color:${textColor}">${d}</div>
                    ${hasSales ? `<div style="font-size:.65rem;font-weight:700;color:#0d6efd;margin-top:2px;">${dayData.total >= 10000 ? Math.round(dayData.total/10000) + '만' : formatMoney(dayData.total)}</div><div style="font-size:.6rem;color:#6c757d">${dayData.count}건</div>` : ''}
                </div>`;
            }
            html += '</div>';
            grid.innerHTML = html;
        } catch (e) {
            grid.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
        }
    }

    document.getElementById('calPrev').onclick = () => { calMonth--; if (calMonth < 1) { calMonth = 12; calYear--; } renderCalendar(); };
    document.getElementById('calNext').onclick = () => { calMonth++; if (calMonth > 12) { calMonth = 1; calYear++; } renderCalendar(); };
    renderCalendar();
}

// 날짜 클릭 시 상세 결제내역 팝업
async function showDailyDetail(dateStr) {
    resetFormModalFooter(false);
    const modalEl = document.getElementById('formModal');
    const titleEl = document.getElementById('formModalTitle');
    const bodyEl = document.getElementById('formModalBody');
    const saveBtn = document.getElementById('formModalSave');
    saveBtn.style.display = 'none';

    titleEl.innerHTML = `<i class="fas fa-calendar-day text-info me-2"></i>${dateStr} 결제내역`;
    bodyEl.innerHTML = adpayLoadingMarkup('불러오는 중...');
    new bootstrap.Modal(modalEl).show();

    try {
        const data = await apiGet(`/api/owner/calendar-daily?date=${dateStr}`);
        if (data.transactions.length === 0) {
            bodyEl.innerHTML = `<div class="text-center py-4 text-muted"><i class="fas fa-inbox fa-2x mb-2 d-block opacity-50"></i><p>이 날짜에 결제 내역이 없습니다</p></div>`;
        } else {
            bodyEl.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-3 p-2 rounded" style="background:#f0f7ff">
                    <span class="fw-bold"><i class="fas fa-won-sign text-primary me-1"></i>합계: ${formatMoney(data.total)}</span>
                    <span class="badge bg-primary">${data.count}건</span>
                </div>
                <div class="table-responsive"><table class="table table-sm table-hover mb-0">
                    <thead class="table-light"><tr><th>금액</th><th>카드</th><th>직원</th><th>승인번호</th><th>시간</th></tr></thead>
                    <tbody>${data.transactions.map(tx => `<tr>
                        <td class="fw-bold">${formatMoney(tx.amount)}</td>
                        <td>${escapeHtml(tx.card_brand||'-')}</td>
                        <td>${escapeHtml(tx.staff_name)||'<span class="text-muted">사장님</span>'}</td>
                        <td><code>${escapeHtml(tx.approval_code||'-')}</code></td>
                        <td class="text-muted" style="font-size:.8rem;">${tx.created_at ? tx.created_at.split(' ')[1]?.substring(0,5) || formatDate(tx.created_at) : '-'}</td>
                    </tr>`).join('')}</tbody>
                </table></div>`;
        }
    } catch (e) {
        bodyEl.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
    saveBtn.style.display = 'none';
}

async function loadOwnerAnalysis(c, t) {
    t.textContent = '광고 분석';
    c.innerHTML = `
    <div class="owner-analysis-page">
    <!-- 헤더 -->
    <div class="analysis-page-header d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div class="analysis-page-title">
            <h5 class="fw-bold mb-0"><i class="fas fa-store text-primary me-2"></i>우리 매장 광고 현황</h5>
            <small class="text-muted">네이버 플레이스 순위와 리뷰가 어떻게 달라졌는지 확인하세요</small>
        </div>
        <div class="analysis-page-actions d-flex gap-2 align-items-center">
            <button class="btn btn-sm btn-primary" onclick="fetchAnalysisNow()" id="fetchNowBtn">
                <i class="fas fa-rotate me-1"></i>광고 분석하기
            </button>
            <button class="btn btn-sm btn-outline-secondary" onclick="toggleManagePanel()">
                <i class="fas fa-gear me-1"></i>광고 분석설정
            </button>
        </div>
    </div>

    <!-- 자동 수집 상태 -->
    <div id="collectStatus" class="mb-2"></div>

    <!-- 자동 수집 안내 -->
    <div class="analysis-notice mb-3">
        <span class="analysis-notice-icon">📅</span>
        <span><strong>순위는 매일 오후 2시에 자동으로 업데이트 됩니다.</strong>
            <small><span class="rank-update-copy-desktop">업데이트 전에 실시간으로 바로 확인하려면 <strong>광고분석하기</strong> 버튼을 눌러 주세요.</span><span class="rank-update-copy-mobile">실시간 확인은 <strong>광고분석하기</strong> 버튼을 눌러 주세요.</span></small></span>
    </div>

    <!-- 상단 요약 카드 — 항상 보임 -->
    <div id="analysisToday" class="mb-3"></div>

    <!-- 탭 네비게이션 -->
    <div class="analysis-tab-wrap mb-3">
        <div class="analysis-tab-nav" role="tablist" aria-label="광고 분석 상세 메뉴">
            <button type="button" class="analysis-tab-btn active" data-tab="compare" role="tab" aria-selected="true">
                <i class="fas fa-scale-balanced me-1"></i>경쟁 매장
            </button>
            <button type="button" class="analysis-tab-btn" data-tab="trend" role="tab" aria-selected="false">
                <i class="fas fa-chart-line me-1"></i>변화 흐름
            </button>
            <button type="button" class="analysis-tab-btn" data-tab="detail" role="tab" aria-selected="false">
                <i class="fas fa-calendar-days me-1"></i>날짜별 기록
            </button>
        </div>
    </div>

    <!-- 탭 패널 -->
    <div class="analysis-tab-content">
        <div id="tab-compare" class="analysis-tab-pane" role="tabpanel">
            <div class="analysis-tab-guide"><i class="fas fa-store"></i><span><strong>우리 매장과 주변 매장을 비교해요</strong><small>초록색은 우리 매장이 앞선 항목, 빨간색은 보완할 항목입니다.</small></span></div>
            <div id="analysisCompare"></div>
        </div>
        <div id="tab-trend" class="analysis-tab-pane" role="tabpanel" style="display:none">
            <div class="analysis-tab-guide"><i class="fas fa-arrow-trend-up"></i><span><strong>순위와 리뷰가 어떻게 달라졌는지 확인해요</strong><small>그래프 아래에서 날짜별 실제 수치와 전날 대비 변화를 볼 수 있습니다.</small></span></div>
            <div id="analysisTrend"></div>
        </div>
        <div id="tab-detail" class="analysis-tab-pane" role="tabpanel" style="display:none">
            <div class="analysis-tab-guide"><i class="fas fa-calendar-check"></i><span><strong>수집된 날짜별 기록을 한눈에 확인해요</strong><small>우리 매장과 경쟁업체의 순위·리뷰 기록을 각각 확인할 수 있습니다.</small></span></div>
            <div id="analysisDetail"></div>
        </div>
    </div>

    <!-- 하단 액션 -->
    <div class="analysis-bottom-actions text-center mt-3">
        <button class="btn btn-outline-primary me-2" onclick="navigate('owner-adorder-new')"><i class="fas fa-bullhorn me-1"></i>광고 주문하기</button>
        <button class="btn btn-outline-secondary" onclick="navigate('owner-adorders')"><i class="fas fa-list me-1"></i>주문 내역 보기</button>
    </div>
    </div>`;

    // onclick 속성은 Bootstrap이 nav[role=tablist] 자식에서 초기화하므로
    // data-tab + addEventListener(이벤트 위임) 방식으로 클릭을 처리한다
    c.querySelector('.analysis-tab-nav')?.addEventListener('click', e => {
        const btn = e.target.closest('.analysis-tab-btn');
        if (btn) switchAnalysisTab(btn.dataset.tab, btn);
    });

    renderAnalysisSettingsModal();
    loadAnalysisOverview();
    reloadAnalysis();
    loadAnalysisTrend();
}

// ─── 오늘 현황 / 경쟁업체 비교 ───────────────────────────────

// ── 1) 오늘 우리 매장 현황 + 2) 경쟁업체 비교 ──
// 사장님이 보시는 화면이라 숫자보다 "어떻게 달라졌는지"를 먼저 보여준다.

// 지표 정의 (higherIsBetter=false 인 순위는 숫자가 작을수록 좋음)
const COMPARE_METRICS = [
    { key: 'rank', label: '플레이스 순위', icon: 'fa-trophy', color: 'warning', higherIsBetter: false, unit: '단계' },
    { key: 'blog', label: '블로그 리뷰', icon: 'fa-blog', color: 'info', higherIsBetter: true, unit: '개' },
    { key: 'visitor', label: '방문자 리뷰', icon: 'fa-users', color: 'success', higherIsBetter: true, unit: '개' },
];

// 변화량을 사장님 눈높이의 문장으로 바꾼다. (change 는 양수면 '좋아짐')
function changeSentence(metricKey, change, label) {
    const base = label || '어제';
    if (change === null || change === undefined) return `${base} 자료가 없어 비교할 수 없어요`;
    if (change === 0) return `${base}와 같아요`;
    if (metricKey === 'rank') {
        return change > 0 ? `${base}보다 ${change}단계 올랐어요` : `${base}보다 ${Math.abs(change)}단계 내려갔어요`;
    }
    return change > 0 ? `${base}보다 ${change}개 늘었어요` : `${base}보다 ${Math.abs(change)}개 줄었어요`;
}

function changeArrow(change) {
    if (change === null || change === undefined || change === 0) {
        return '<span class="text-muted">─</span>';
    }
    return change > 0
        ? '<span class="text-success">▲</span>'
        : '<span class="text-danger">▼</span>';
}

// 값 표기 (순위는 "34위", 리뷰는 숫자)
function metricValueText(metricKey, value) {
    if (value === null || value === undefined) return '-';
    return metricKey === 'rank' ? formatRank(value) : value.toLocaleString();
}

// 우리 값이 전체(우리+경쟁업체) 중 몇 위인지 계산
function standingAmong(metricKey, mineValue, competitorValues, higherIsBetter) {
    if (mineValue === null || mineValue === undefined) return null;
    const values = [mineValue, ...competitorValues.filter(v => v !== null && v !== undefined)];
    const sorted = [...values].sort((a, b) => higherIsBetter ? b - a : a - b);
    return { place: sorted.indexOf(mineValue) + 1, total: values.length };
}

let analysisOverviewPeriod = 'day';

async function loadAnalysisOverview(period) {
    const todayBox = document.getElementById('analysisToday');
    const compareBox = document.getElementById('analysisCompare');
    if (!todayBox || !compareBox) return;
    if (period) analysisOverviewPeriod = period;

    const spinner = `<div class="card border-0 shadow-sm"><div class="card-body">${adpayLoadingMarkup()}</div></div>`;
    todayBox.innerHTML = spinner;
    compareBox.innerHTML = '';

    try {
        const d = await apiGet(`/api/owner/ad/analysis/overview?period=${analysisOverviewPeriod}`);
        renderTodayStatus(todayBox, d);
        renderCompareTable(compareBox, d);
    } catch (e) {
        todayBox.innerHTML = `<div class="alert alert-warning py-2 mb-0 small"><i class="fas fa-exclamation-triangle me-1"></i>${escapeHtml(e.message)}</div>`;
    }
}

// ── 1) 오늘 우리 매장 현황 — 큰 숫자 카드 3개 ──
function renderTodayStatus(box, d) {
    const m = d.my_place;
    if (!m) {
        box.innerHTML = `<div class="card border-0 shadow-sm analysis-empty"><div class="card-body analysis-empty-body text-center py-4">
            <i class="fas fa-store fa-2x text-muted mb-2 d-block opacity-50"></i>
            <p class="mb-1 fw-bold">아직 우리 매장이 등록되지 않았어요</p>
            <p class="text-muted small mb-3"><strong>광고 분석설정</strong> 버튼을 눌러 네이버 플레이스 주소와 검색어를 등록해 주세요.</p>
            <button class="btn btn-sm btn-primary" onclick="toggleManagePanel()"><i class="fas fa-gear me-1"></i>광고 분석설정 열기</button>
        </div></div>`;
        return;
    }

    // 좋아진 지표 개수로 전체 분위기를 판단한다.
    const changes = [m.rank_change, m.blog_change, m.visitor_change].filter(v => v !== null && v !== undefined);
    const better = changes.filter(v => v > 0).length;
    const worse = changes.filter(v => v < 0).length;
    let mood, moodIcon, moodClass;
    if (!changes.length) { mood = '비교할 어제 자료가 아직 없어요'; moodIcon = 'circle-info'; moodClass = 'secondary'; }
    else if (better > worse) { mood = '잘 되고 있어요'; moodIcon = 'face-smile'; moodClass = 'success'; }
    else if (worse > better) { mood = '주의가 필요해요'; moodIcon = 'triangle-exclamation'; moodClass = 'danger'; }
    else { mood = '어제와 비슷해요'; moodIcon = 'face-meh'; moodClass = 'secondary'; }

    const label = d.period_label || '어제';
    const cards = COMPARE_METRICS.map(metric => {
        const value = m[metric.key];
        const change = m[metric.key + '_change'];
        return `<div class="col-md-4">
            <div class="card border-0 shadow-sm h-100">
                <div class="card-body text-center py-3">
                    <div class="text-muted small mb-1"><i class="fas ${metric.icon} text-${metric.color} me-1"></i>${metric.label}</div>
                    <div class="fw-bold" style="font-size:2.1rem;line-height:1.15">${metricValueText(metric.key, value)}</div>
                    <div class="mt-1" style="font-size:.86rem">
                        ${changeArrow(change)} <span class="${change > 0 ? 'text-success' : (change < 0 ? 'text-danger' : 'text-muted')}">${changeSentence(metric.key, change, label)}</span>
                    </div>
                    ${metric.key === 'rank' ? rankRefreshGuide(true) : ''}
                </div>
            </div>
        </div>`;
    }).join('');

    const p = analysisOverviewPeriod;
    box.innerHTML = `<div class="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
            <h6 class="fw-bold mb-0"><i class="fas fa-calendar-day text-primary me-2"></i>오늘 우리 매장 (${escapeHtml(m.name)}) 현황
                <small class="text-muted fw-normal ms-1">${m.date}</small></h6>
            <div class="d-flex gap-2 align-items-center flex-wrap">
                <span class="badge bg-${moodClass} bg-opacity-10 text-${moodClass} border border-${moodClass} border-opacity-25">
                    <i class="fas fa-${moodIcon} me-1"></i>${mood}</span>
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn ${p === 'day' ? 'btn-primary' : 'btn-outline-primary'}" onclick="loadAnalysisOverview('day')">어제와 비교</button>
                    <button type="button" class="btn ${p === 'week' ? 'btn-primary' : 'btn-outline-primary'}" onclick="loadAnalysisOverview('week')">지난주와 비교</button>
                </div>
            </div>
        </div>
        <div class="row g-3">${cards}</div>`;
}

// ── 2) 경쟁업체 비교 — 우리 매장 + 경쟁업체를 한 표에 나란히 ──
function renderCompareTable(box, d) {
    const m = d.my_place;
    const label = d.period_label || '어제';
    const comps = (d.competitors || []).filter(c => c.has_data);
    const pending = (d.competitors || []).filter(c => !c.has_data);

    if (!m) { box.innerHTML = ''; return; }
    if (comps.length === 0) {
        box.innerHTML = `<div class="card border-0 shadow-sm"><div class="card-body text-center py-4">
            <i class="fas fa-users fa-2x text-muted mb-2 d-block opacity-50"></i>
            <p class="mb-1 fw-bold">비교할 경쟁업체가 없어요</p>
            <p class="text-muted small mb-3">근처 매장을 등록하면 우리 매장과 나란히 비교해 드려요. (최대 ${MAX_COMPETITORS}곳)</p>
            <button class="btn btn-sm btn-outline-primary" onclick="toggleManagePanel()"><i class="fas fa-plus me-1"></i>경쟁업체 등록하기</button>
        </div></div>`;
        return;
    }

    // 우리 기준 우열 판정 — 앞서면 'ahead', 뒤지면 'behind', 같으면 'tie'
    const verdictOf = (metric, mine, value) => {
        if (value === null || value === undefined || mine === null || mine === undefined) return null;
        if (mine === value) return 'tie';
        return (metric.higherIsBetter ? mine > value : mine < value) ? 'ahead' : 'behind';
    };

    // 표 머리글 — 등록된 경쟁업체 수만큼 열이 늘어난다.
    const head = `<tr>
        <th class="cmp-metric-col">구분</th>
        <th class="text-center cmp-col-mine">우리 매장<div class="cmp-col-sub">(${escapeHtml(m.name)})</div></th>
        ${comps.map((c, i) => `<th class="text-center cmp-col-rival ${i % 2 ? 'cmp-col-alt' : ''}">경쟁업체<div class="cmp-col-sub">(${escapeHtml(c.name)})</div></th>`).join('')}
    </tr>`;

    const standings = {};
    const rows = COMPARE_METRICS.map(metric => {
        const mine = m[metric.key];
        const theirs = comps.map(c => c[metric.key]);
        standings[metric.key] = standingAmong(metric.key, mine, theirs, metric.higherIsBetter);

        const cells = comps.map((c, i) => {
            const value = c[metric.key];
            const verdict = verdictOf(metric, mine, value);
            const alt = i % 2 ? 'cmp-col-alt' : '';
            if (!verdict) {
                return `<td class="text-center text-muted ${alt}">${metricValueText(metric.key, value)}</td>`;
            }
            // 좌측 컬러 바 + 옅은 배경으로 우열을 표시한다.
            const mark = verdict === 'tie' ? '' : (verdict === 'ahead'
                ? '<i class="fas fa-caret-up text-success ms-1"></i>'
                : '<i class="fas fa-caret-down text-danger ms-1"></i>');
            return `<td class="text-center ${alt} cmp-cell cmp-${verdict}">${metricValueText(metric.key, value)}${mark}</td>`;
        }).join('');

        return `<tr>
            <td class="fw-bold cmp-metric-col"><i class="fas ${metric.icon} text-${metric.color} me-1"></i>${metric.label}</td>
            <td class="text-center fw-bold cmp-col-mine">${metricValueText(metric.key, mine)}</td>
            ${cells}
        </tr>`;
    }).join('');

    // 모바일용 카드 — 좁은 화면에서는 표 대신 업체별 카드를 보여준다.
    const changeKey = { rank: 'comp_rank_change', blog: 'comp_blog_change', visitor: 'comp_visitor_change' };
    const mobileCard = (name, sub, data, isMine) => {
        const items = COMPARE_METRICS.map(metric => {
            const value = data[metric.key];
            const change = isMine ? data[metric.key + '_change'] : data[changeKey[metric.key]];
            const verdict = isMine ? null : verdictOf(metric, m[metric.key], value);
            const valueClass = verdict === 'ahead' ? 'text-success' : (verdict === 'behind' ? 'text-danger' : '');
            return `<div class="cmp-card-item">
                <div class="cmp-card-metric">${metric.label}</div>
                <div class="cmp-card-value ${valueClass}">${metricValueText(metric.key, value)}</div>
                <div class="cmp-card-change">${changeArrow(change)} ${changeSentence(metric.key, change, label)}</div>
            </div>`;
        }).join('');
        const wins = isMine ? 0 : COMPARE_METRICS.filter(metric => verdictOf(metric, m[metric.key], data[metric.key]) === 'ahead').length;
        const losses = isMine ? 0 : COMPARE_METRICS.filter(metric => verdictOf(metric, m[metric.key], data[metric.key]) === 'behind').length;
        const tone = isMine ? 'mine' : (wins > losses ? 'ahead' : (losses > wins ? 'behind' : 'even'));
        const badge = isMine
            ? '<span class="badge bg-primary">우리 매장</span>'
            : (tone === 'ahead' ? '<span class="badge bg-success">우세</span>'
                : (tone === 'behind' ? '<span class="badge bg-danger">열세</span>' : '<span class="badge bg-secondary">대등</span>'));
        return `<div class="cmp-card cmp-card-${tone}">
            <div class="cmp-card-head">
                <span class="cmp-card-name">${escapeHtml(name)}<small>${escapeHtml(sub)}</small></span>${badge}
            </div>
            <div class="cmp-card-body">${items}</div>
        </div>`;
    };
    const mobileCards = mobileCard(`우리 매장 (${m.name})`, '우리 매장', m, true)
        + comps.map(c => mobileCard(`경쟁업체 (${c.name})`, '경쟁업체', c, false)).join('');

    // 종합 분석 — "경쟁업체 2곳 중 블로그 리뷰는 1위" 처럼 순위로 표현
    const parts = COMPARE_METRICS
        .filter(metric => standings[metric.key])
        .map(metric => `${metric.label}는 ${standings[metric.key].place}위`);
    const summaryText = parts.length
        ? `경쟁업체 ${comps.length}곳 중 ${parts.join(', ')}입니다.`
        : '비교할 수 있는 자료가 아직 부족해요.';
    const firstCount = COMPARE_METRICS.filter(metric => standings[metric.key] && standings[metric.key].place === 1).length;
    const summaryClass = firstCount >= 2 ? 'success' : (firstCount === 0 ? 'danger' : 'primary');

    const pendingNote = pending.length
        ? `<div class="text-muted mt-2" style="font-size:.78rem"><i class="fas fa-circle-info me-1"></i>
             ${pending.map(c => escapeHtml(c.name)).join(', ')} 는 아직 자료가 없어요. 위 <strong>광고 분석하기</strong>를 눌러주세요.</div>`
        : '';

    box.innerHTML = `<div class="card border-0 shadow-sm">
        <div class="card-header bg-white border-0 d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h6 class="mb-0 fw-bold"><i class="fas fa-scale-balanced text-primary me-2"></i>경쟁업체와 비교
                <span class="badge bg-secondary ms-1">${comps.length}곳</span></h6>
            <small class="text-muted"><span class="badge bg-success bg-opacity-25 text-success">초록</span> 우리가 앞섬 ·
                <span class="badge bg-danger bg-opacity-25 text-danger">빨강</span> 우리가 뒤짐</small>
        </div>
        <div class="card-body pt-2">
            <div class="alert alert-${summaryClass} bg-${summaryClass} bg-opacity-10 border-0 py-2 px-3 mb-3">
                <i class="fas fa-lightbulb text-warning me-2"></i><span class="fw-bold small">${escapeHtml(summaryText)}</span>
            </div>
            ${rankRefreshGuide()}
            <div class="table-responsive cmp-desktop">
                <table class="table table-bordered align-middle mb-0 text-nowrap cmp-table">
                    <thead>${head}</thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="cmp-mobile">${mobileCards}</div>
            ${pendingNote}
        </div>
    </div>`;
}

// ─── 네이버 플레이스 자동 수집 ───────────────────────────────

let analysisTrendCharts = {};   // metric -> Chart 인스턴스 (지연 생성)
let analysisTrendData = null;   // { labels, series }

const TREND_CANVAS_ID = { blog: 'trendBlog', visitor: 'trendVisitor', rank: 'trendRank' };
const TREND_PALETTE = ['#6366f1', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899'];

function destroyAnalysisTrendCharts() {
    // 인스턴스를 명시적으로 정리해 캔버스/이벤트 핸들러 누수를 막는다.
    Object.values(analysisTrendCharts).forEach(ch => { try { ch.destroy(); } catch (e) {} });
    analysisTrendCharts = {};
}

// 보이는 탭의 차트만 그린다. 이미 만들어져 있으면 재사용한다.
function renderTrendChart(metric) {
    if (!analysisTrendData || analysisTrendCharts[metric]) return;
    const canvas = document.getElementById(TREND_CANVAS_ID[metric]);
    if (!canvas || typeof Chart === 'undefined') return;

    const { labels, series } = analysisTrendData;
    const COMP_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#8b5cf6', '#f97316'];
    const datasets = series.map((s, i) => {
        const isMine = s.kind === 'my';
        const compIdx = series.filter((x, j) => x.kind !== 'my' && j < i).length;
        const compColor = COMP_COLORS[compIdx % COMP_COLORS.length];
        return {
            label: `${isMine ? '우리 매장' : '경쟁업체'} (${s.label})`,
            data: s[metric],
            borderColor: isMine ? '#2563eb' : compColor,
            backgroundColor: isMine ? 'rgba(37,99,235,.1)' : compColor + '18',
            borderWidth: isMine ? 4 : 2,
            borderDash: isMine ? [] : [5, 4],
            tension: .3,
            spanGaps: true,
            pointRadius: isMine ? 6 : 3,
            pointHoverRadius: isMine ? 10 : 6,
            pointBackgroundColor: isMine ? '#2563eb' : compColor,
            pointBorderColor: '#fff',
            pointBorderWidth: isMine ? 2 : 1.5,
        };
    });
    // 애니메이션을 끄면 렌더 직후 1초간 이어지던 캔버스 재도색이 사라진다.
    const options = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        animations: { colors: false, x: false, y: false },
        transitions: { active: { animation: { duration: 0 } }, resize: { animation: { duration: 0 } } },
        hover: { animationDuration: 0 },
        plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
        scales: { x: { ticks: { font: { size: 9 }, maxTicksLimit: 8 } }, y: { ticks: { font: { size: 9 } } } },
    };
    if (metric === 'rank') {
        options.scales = {
            ...options.scales,
            y: {
                ...options.scales.y, reverse: true,
                ticks: { ...options.scales.y.ticks, precision: 0, callback: v => v >= RANK_OUT_OF_RANGE ? '200+' : v + '위' },
            },
        };
    }
    analysisTrendCharts[metric] = new Chart(canvas, { type: 'line', data: { labels, datasets }, options });
}

function renderTrendSummary(metric) {
    if (!analysisTrendData) return '';
    const { series = [] } = analysisTrendData;
    const myData = series.find(s => s.kind === 'my');
    if (!myData) return '';
    const values = (myData[metric] || []).filter(v => v !== null && v !== undefined);
    if (!values.length) return '';
    const isRank = metric === 'rank';
    const best = isRank ? Math.min(...values) : Math.max(...values);
    const avg = Math.round(values.reduce((a, b) => a + b, 0) / values.length);
    const last = values[values.length - 1];
    const prev = values.length > 1 ? values[values.length - 2] : null;
    const rawChange = prev !== null ? (isRank ? prev - last : last - prev) : null;
    const arrow = rawChange === null ? '─' : (rawChange > 0 ? '<span class="text-success">▲</span>' : (rawChange < 0 ? '<span class="text-danger">▼</span>' : '─'));
    const absChange = rawChange !== null && rawChange !== 0 ? ` ${Math.abs(rawChange).toLocaleString('ko-KR')}` : '';
    const fmt = v => isRank ? v + '위' : v.toLocaleString('ko-KR') + '개';
    if (!isRank) {
        const first = values[0];
        const periodChange = last - first;
        const periodText = periodChange === 0
            ? '변화 없음'
            : `${periodChange > 0 ? '+' : '-'}${Math.abs(periodChange).toLocaleString('ko-KR')}개`;
        return `<div class="stat-mini-cards">
            <div class="stat-mini-card"><div class="label">기간 시작</div><div class="value">${fmt(first)}</div></div>
            <div class="stat-mini-card"><div class="label">현재 리뷰</div><div class="value">${fmt(last)}</div></div>
            <div class="stat-mini-card"><div class="label">기간 동안</div><div class="value ${periodChange > 0 ? 'text-success' : (periodChange < 0 ? 'text-danger' : '')}">${periodText}</div></div>
        </div>`;
    }
    return `<div class="stat-mini-cards">
        <div class="stat-mini-card">
            <div class="label">기간 최고</div>
            <div class="value">${fmt(best)}</div>
        </div>
        <div class="stat-mini-card">
            <div class="label">기간 평균</div>
            <div class="value">${fmt(avg)}</div>
        </div>
        <div class="stat-mini-card">
            <div class="label">현재 순위</div>
            <div class="value">${fmt(last)} ${arrow}${absChange}</div>
        </div>
    </div>`;
}

function renderTrendHistoryTable(metric) {
    if (!analysisTrendData) return '';
    const { dates = [], series = [] } = analysisTrendData;
    const visibleSeries = series.filter(s => (s[metric] || []).some(value => value !== null && value !== undefined));
    if (!dates.length || !visibleSeries.length) return '<p class="text-muted small mt-2 mb-0">표시할 날짜별 기록이 없어요.</p>';

    const metricLabel = { rank: '순위', blog: '블로그 리뷰', visitor: '방문자 리뷰' }[metric];
    const valueText = value => {
        if (value === null || value === undefined) return '-';
        return metric === 'rank' ? formatRank(value) : Number(value).toLocaleString('ko-KR') + '개';
    };
    const changeText = (values, index) => {
        const current = values[index];
        const previous = index > 0 ? values[index - 1] : null;
        if (current === null || current === undefined || previous === null || previous === undefined) {
            return '<span class="trend-change is-neutral">변화 -</span>';
        }
        const change = metric === 'rank' ? previous - current : current - previous;
        if (change === 0) return '<span class="trend-change is-neutral">전날과 같음</span>';
        const better = change > 0;
        const amount = Math.abs(change).toLocaleString('ko-KR');
        const wording = metric === 'rank'
            ? `전날보다 ${amount}위 ${better ? '상승' : '하락'}`
            : `전날보다 ${amount}개 ${better ? '증가' : '감소'}`;
        return `<span class="trend-change ${better ? 'is-up' : 'is-down'}">${better ? '▲' : '▼'} ${wording}</span>`;
    };
    const header = visibleSeries.map(s => `<th scope="col">${s.kind === 'my' ? '우리 매장' : '경쟁업체'}<small>(${escapeHtml(s.label)})</small></th>`).join('');
    const rows = dates.map((date, index) => {
        const cells = visibleSeries.map(s => `<td><strong>${valueText((s[metric] || [])[index])}</strong>${changeText(s[metric] || [], index)}</td>`).join('');
        return `<tr><th scope="row">${escapeHtml(date)}</th>${cells}</tr>`;
    }).reverse().join('');
    const mobileRows = dates.map((date, index) => {
        const stores = visibleSeries.map(s => {
            const value = (s[metric] || [])[index];
            return `<div class="trend-day-store ${s.kind === 'my' ? 'is-mine' : ''}">
                <div class="trend-day-store-head"><span>${s.kind === 'my' ? '우리 매장' : '경쟁업체'} (${escapeHtml(s.label)})</span><small>${s.kind === 'my' ? '우리 매장' : '경쟁 매장'}</small></div>
                <strong>${valueText(value)}</strong>
                ${changeText(s[metric] || [], index)}
            </div>`;
        }).join('');
        return `<article class="trend-day-card"><time datetime="${escapeHtml(date)}">${escapeHtml(date)}</time><div class="trend-day-stores">${stores}</div></article>`;
    }).reverse().join('');

    return `<div class="trend-history">
        <div class="trend-history-head">
            <strong><i class="fas fa-table-list me-1"></i>${metricLabel} 일자별 변화</strong>
            <span>전일 대비 변화량 · 최신 일자 우선</span>
        </div>
        <div class="table-responsive trend-history-desktop">
            <table class="table table-sm align-middle mb-0 mobile-keep-table trend-history-table">
                <thead><tr><th scope="col">날짜</th>${header}</tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        <div class="trend-history-mobile">${mobileRows}</div>
    </div>`;
}

// 리뷰 수 차트는 기본으로 펼쳐 두며, 필요할 때만 접을 수 있다.
function toggleReviewTrend() {
    const body = document.getElementById('reviewTrendBody');
    const caret = document.getElementById('reviewTrendCaret');
    const toggle = document.getElementById('reviewTrendToggle');
    if (!body) return;
    const opening = body.style.display === 'none';
    body.style.display = opening ? '' : 'none';
    if (caret) {
        caret.classList.toggle('fa-chevron-right', !opening);
        caret.classList.toggle('fa-chevron-down', opening);
    }
    if (toggle) {
        toggle.innerHTML = `<i class="fas fa-chevron-${opening ? 'down' : 'right'} me-1" id="reviewTrendCaret"></i>`
            + (opening ? '리뷰 수 변화 접기' : '리뷰 수 변화도 보기');
    }
    if (!opening) return;
    // 펼쳐진 뒤에 그려야 캔버스 크기가 정확하다.
    ['blog', 'visitor'].forEach(metric => {
        renderTrendChart(metric);
        const chart = analysisTrendCharts[metric];
        if (chart) { try { chart.resize(); } catch (e) {} }
    });
}

function renderCollectStatus(status) {
    const box = document.getElementById('collectStatus');
    if (!box || !status) return;
    const hasToday = status.has_today_data;
    // 서버가 이미 KST 문자열로 내려주므로 시간대 변환을 하지 않는다 (분 단위까지만 표시).
    const last = status.last_collected_at
        ? status.last_collected_at.replace('T', ' ').slice(0, 16)
        : (localStorage.getItem('lastAnalysisAt') || null);
    box.innerHTML = `<div class="d-flex align-items-center gap-2 flex-wrap small">
        <span class="badge ${hasToday ? 'bg-success' : 'bg-secondary'}">
            <i class="fas fa-${hasToday ? 'circle-check' : 'circle-minus'} me-1"></i>${hasToday ? '오늘 데이터 있음' : '오늘 데이터 없음'}
        </span>
        ${status.today_count ? `<span class="text-muted">오늘 ${status.today_count}건 수집</span>` : ''}
        <span class="text-muted"><i class="fas fa-clock me-1"></i>마지막 수집: ${last ? escapeHtml(last) : '없음'}</span>
        ${status.last_keyword ? `<span class="text-muted"><i class="fas fa-magnifying-glass me-1"></i>${escapeHtml(status.last_keyword)}</span>` : ''}
    </div>`;
}

// 한 프레임 양보 — 긴 작업 사이에 브라우저가 화면을 그릴 틈을 준다.
// 백그라운드 탭에서는 rAF 가 멈추므로 타이머로도 반드시 진행되게 한다.
function nextFrame() {
    return new Promise(resolve => {
        let settled = false;
        const finish = () => { if (!settled) { settled = true; resolve(); } };
        try { requestAnimationFrame(finish); } catch (e) { /* rAF 미지원 시 타이머로 진행 */ }
        setTimeout(finish, 32);
    });
}

let analysisFetchInFlight = false;

async function fetchAnalysisNow() {
    const btn = document.getElementById('fetchNowBtn');
    if (!btn) return;
    if (analysisFetchInFlight) return;  // 연타로 요청이 중첩되지 않게 한다
    analysisFetchInFlight = true;
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>수집중...';
    const box = document.getElementById('collectStatus');
    if (box) box.innerHTML = '<div class="small text-muted"><i class="fas fa-spinner fa-spin me-1"></i>네이버 플레이스에서 순위와 리뷰를 확인하고 있습니다...</div>';

    try {
        const res = await apiPost('/api/owner/ad/fetch-now?force=true', {});
        renderCollectStatus(res.collection_status);
        const failed = (res.results || []).filter(r => !r.ok);
        let msg = `수집 완료 — ${res.collected}건 저장 (${res.elapsed_seconds}초)`;
        if (failed.length) msg += `\n실패 ${failed.length}건: ` + failed.map(f => `${f.label}(${f.error || '알 수 없음'})`).join(', ');

        // 갱신 사이사이에 한 프레임씩 양보해 화면이 멈춘 것처럼 보이지 않게 한다.
        await loadAnalysisOverview();
        await nextFrame();
        await reloadAnalysis();
        await nextFrame();
        await loadAnalysisTrend();
        await nextFrame();
        // 수집 완료 시각을 localStorage에 저장하고 collectStatus를 강제 갱신
        // (후속 API 호출이 구 데이터를 반환해 덮어쓰는 경우를 방지)
        const _d = new Date(), _p = n => String(n).padStart(2, '0');
        const _kst = new Date(_d.getTime() + (540 + _d.getTimezoneOffset()) * 60000);
        const _nowStr = `${_kst.getFullYear()}-${_p(_kst.getMonth()+1)}-${_p(_kst.getDate())} ${_p(_kst.getHours())}:${_p(_kst.getMinutes())}`;
        localStorage.setItem('lastAnalysisAt', _nowStr);
        renderCollectStatus({ ...res.collection_status, last_collected_at: _nowStr });
        // 결과를 Bootstrap 모달로 표시 (alert는 메인 스레드 차단)
        const resultBody = document.getElementById('analysisResultBody');
        const resultModalEl = document.getElementById('analysisResultModal');
        if (resultBody && resultModalEl) {
            const hasFail = failed.length > 0;
            resultBody.innerHTML = `<div class="text-center py-2">
                <i class="fas fa-${hasFail ? 'exclamation-circle text-warning' : 'circle-check text-success'} fa-2x mb-3 d-block"></i>
                <p class="fw-bold mb-1">${res.collected}건 저장 완료</p>
                <p class="text-muted small mb-0"><i class="fas fa-clock me-1"></i>소요 시간: ${res.elapsed_seconds}초</p>
                ${hasFail ? `<div class="alert alert-warning mt-3 mb-0 small text-start"><i class="fas fa-triangle-exclamation me-1"></i>실패 ${failed.length}건: ${failed.map(f => escapeHtml(f.label) + '(' + escapeHtml(f.error || '알 수 없음') + ')').join(', ')}</div>` : ''}
            </div>`;
            new bootstrap.Modal(resultModalEl).show();
        } else {
            alert(msg);
        }
    } catch (e) {
        if (box) box.innerHTML = `<div class="alert alert-danger py-2 mb-0 small"><i class="fas fa-exclamation-circle me-1"></i>${escapeHtml(e.message)}</div>`;
    } finally {
        analysisFetchInFlight = false;
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

async function loadAnalysisTrend(days) {
    const box = document.getElementById('analysisTrend');
    if (!box) return;
    const period = days || parseInt(document.getElementById('trendDays')?.value || '30', 10);
    try {
        const data = await apiGet(`/api/owner/ad/analysis/history?days=${period}`);
        renderCollectStatus(data.collection_status);

        const series = (data.series || []).filter(s => (s.blog || []).some(v => v !== null) || (s.rank || []).some(v => v !== null));
        if (series.length === 0) {
            box.innerHTML = `<div class="card border-0 shadow-sm"><div class="card-body text-center text-muted py-4">
                <i class="fas fa-chart-line fa-2x mb-2 d-block opacity-50"></i>
                <p class="mb-1">아직 보여드릴 변화가 없어요</p>
                <small>위 <strong>광고 분석하기</strong> 버튼을 누르면 오늘 자료부터 쌓입니다</small>
            </div></div>`;
            destroyAnalysisTrendCharts();
            analysisTrendData = null;
            return;
        }

        const dates = data.dates || [];
        const labels = dates.map(d => d.slice(5));
        destroyAnalysisTrendCharts();
        analysisTrendData = { labels, dates, series };
        // 순위와 리뷰 추이를 3개 별도 카드로 나누어 보여준다.
        box.innerHTML = `<div class="d-flex flex-column" style="gap:16px">
            <div class="d-flex justify-content-end mb-1">
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn ${period === 7 ? 'btn-primary' : 'btn-outline-primary'}" onclick="loadAnalysisTrend(7)">최근 7일</button>
                    <button type="button" class="btn ${period === 30 ? 'btn-primary' : 'btn-outline-primary'}" onclick="loadAnalysisTrend(30)">최근 30일</button>
                </div>
            </div>

            <div class="card border-0 shadow-sm trend-metric-card trend-rank-card">
                <div class="card-header">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-trophy me-2" style="color:#3b82f6"></i>플레이스 순위 변화</h6>
                    <span class="badge trend-period-badge" style="background:#3b82f620;color:#3b82f6">${period}일간 · 위로 갈수록 높은 순위</span>
                </div>
                <div class="card-body pt-2">
                    ${rankRefreshGuide()}
                    <p class="trend-card-help"><i class="fas fa-circle-info"></i>순위 숫자가 작을수록 검색 결과에서 더 위에 노출됩니다.</p>
                    <div class="trend-pane" data-metric="rank"><div style="height:240px"><canvas id="trendRank"></canvas></div></div>
                    ${renderTrendSummary('rank')}
                    ${renderTrendHistoryTable('rank')}
                </div>
            </div>

            <div class="card border-0 shadow-sm trend-metric-card trend-blog-card">
                <div class="card-header">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-blog me-2" style="color:#10b981"></i>블로그 리뷰 변화</h6>
                    <span class="badge trend-period-badge" style="background:#10b98120;color:#10b981">${period}일간</span>
                </div>
                <div class="card-body pt-2">
                    <p class="trend-card-help"><i class="fas fa-circle-info"></i>네이버 블로그에 등록된 우리 매장 리뷰 수의 변화를 보여줍니다.</p>
                    <div class="trend-pane" data-metric="blog"><div style="height:200px"><canvas id="trendBlog"></canvas></div></div>
                    ${renderTrendSummary('blog')}
                    ${renderTrendHistoryTable('blog')}
                </div>
            </div>

            <div class="card border-0 shadow-sm trend-metric-card trend-visitor-card">
                <div class="card-header">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-users me-2" style="color:#8b5cf6"></i>방문자 리뷰 변화</h6>
                    <span class="badge trend-period-badge" style="background:#8b5cf620;color:#8b5cf6">${period}일간</span>
                </div>
                <div class="card-body pt-2">
                    <p class="trend-card-help"><i class="fas fa-circle-info"></i>매장을 실제 이용한 방문자가 남긴 리뷰 수의 변화를 보여줍니다.</p>
                    <div class="trend-pane" data-metric="visitor"><div style="height:200px"><canvas id="trendVisitor"></canvas></div></div>
                    ${renderTrendSummary('visitor')}
                    ${renderTrendHistoryTable('visitor')}
                </div>
            </div>
        </div>`;

        ['rank', 'blog', 'visitor'].forEach(renderTrendChart);
    } catch (e) {
        box.innerHTML = `<div class="alert alert-warning py-2 mb-0 small"><i class="fas fa-exclamation-triangle me-1"></i>트렌드 로딩 실패: ${escapeHtml(e.message)}</div>`;
    }
}

function renderAnalysisSettingsModal() {
    const body = document.getElementById('analysisSettingsBody');
    if (!body) return;
    body.innerHTML = `
        <div class="analysis-settings-intro">
            <span><i class="fas fa-lightbulb"></i></span>
            <div><strong>우리 매장과 주변 매장을 등록해 주세요</strong><small>네이버 플레이스 순위와 리뷰 변화를 매일 비교해서 보여드려요.</small></div>
        </div>
        <div class="row g-3 analysis-settings-grid">
            <div class="col-md-6">
                <section class="analysis-settings-section is-mine">
                    <div class="analysis-settings-section-head">
                        <span><i class="fas fa-store"></i></span>
                        <div><h6>우리 매장</h6><small>순위를 확인할 기준 매장</small></div>
                    </div>
                    <p>네이버 지도에서 우리 매장 페이지 주소를 복사해 붙여넣고, 손님이 검색할 만한 단어를 적어주세요.</p>
                    <label class="form-label" for="newProfileUrl">네이버 플레이스 주소</label>
                    <div class="input-group mb-3">
                        <input class="form-control" id="newProfileUrl" placeholder="https://naver.me/..." inputmode="url">
                        <button class="btn btn-primary analysis-settings-add-btn" id="addProfileBtn" type="button" onclick="addPlaceProfile()" aria-label="우리 매장 등록"><i class="fas fa-plus me-1"></i><span>등록</span></button>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-5"><label class="form-label" for="newProfileNick">매장 별칭</label><input class="form-control" id="newProfileNick" placeholder="예: 홍대점"></div>
                        <div class="col-7"><label class="form-label" for="newProfileKeyword">주요 검색어</label><input class="form-control" id="newProfileKeyword" placeholder="예: 지역명 + 업종명"></div>
                    </div>
                    <div id="profileList" class="analysis-settings-list"></div>
                </section>
            </div>
            <div class="col-md-6">
                <section class="analysis-settings-section is-competitor">
                    <div class="analysis-settings-section-head">
                        <span><i class="fas fa-store-alt"></i></span>
                        <div><h6>경쟁 매장</h6><small>비교할 주변 매장 · 최대 ${MAX_COMPETITORS}곳</small></div>
                    </div>
                    <p>비교하고 싶은 근처 매장을 등록하면 순위와 리뷰를 우리 매장과 나란히 보여드려요.</p>
                    <label class="form-label" for="newCompUrl">경쟁 매장 정보</label>
                    <div class="input-group analysis-competitor-inputs mb-3">
                        <input class="form-control" id="newCompUrl" placeholder="네이버 플레이스 URL" inputmode="url">
                        <input class="form-control" id="newCompMemo" placeholder="업체명">
                        <button class="btn btn-primary analysis-settings-add-btn" id="addCompetitorBtn" type="button" onclick="addCompetitor()" aria-label="경쟁 매장 등록"><i class="fas fa-plus me-1"></i><span>등록</span></button>
                    </div>
                    <div id="competitorList" class="analysis-settings-list"></div>
                </section>
            </div>
        </div>`;
}

function toggleManagePanel() {
    const modalEl = document.getElementById('analysisSettingsModal');
    if (!modalEl || !window.bootstrap) return;
    renderAnalysisSettingsModal();
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    if (modalEl.classList.contains('show')) {
        modal.hide();
        return;
    }
    modal.show();
    loadManageLists();
}

function switchAnalysisTab(tabName, btnEl) {
    document.querySelectorAll('.analysis-tab-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
    });
    if (btnEl) {
        btnEl.classList.add('active');
        btnEl.setAttribute('aria-selected', 'true');
    }
    document.querySelectorAll('.analysis-tab-pane').forEach(p => { p.style.display = 'none'; });
    const pane = document.getElementById('tab-' + tabName);
    if (pane) pane.style.display = '';

    // 숨겨진 상태에서 생성된 차트는 크기 0이므로 탭 진입 시 리사이즈
    if (tabName === 'trend') {
        requestAnimationFrame(() => {
            ['rank', 'blog', 'visitor'].forEach(metric => {
                if (!analysisTrendCharts[metric]) {
                    renderTrendChart(metric);
                } else {
                    try { analysisTrendCharts[metric].resize(); } catch (e) {}
                }
            });
        });
    }
}

async function loadManageLists() {
    try {
        const data = await apiGet('/api/owner/ad/analysis?range=all');
        // 프로필 목록
        let profileHtml = '';
        if (data.profiles && data.profiles.length > 0) {
            profileHtml = data.profiles.map(p => `<div class="analysis-target-chip">
                <span><strong>우리 매장 (${escapeHtml(p.actual_name||p.nickname||p.place_url)})</strong>${p.analysis_keyword ? `<small>${escapeHtml(p.analysis_keyword)}</small>` : '<small>검색어 미설정</small>'}</span>
                <button type="button" onclick="removePlaceProfile(${p.id})" aria-label="우리 매장 프로필 삭제"><i class="fas fa-times"></i></button>
            </div>`).join('');
        } else {
            profileHtml = '<small class="text-muted">등록된 프로필이 없습니다</small>';
        }
        document.getElementById('profileList').innerHTML = profileHtml;

        // 경쟁업체 목록 (최대 등록 개수 안내 포함)
        const compList = data.competitor_list || [];
        const maxComp = MAX_COMPETITORS;
        let compHtml = `<div class="small text-muted mb-1">등록 ${compList.length} / ${maxComp}개</div>`;
        if (compList.length > 0) {
            compHtml += compList.map(c => `<div class="analysis-target-chip competitor">
                <span><strong>경쟁업체 (${escapeHtml(c.actual_name||c.memo||c.place_url)})</strong><small>${escapeHtml(c.place_url)}</small></span>
                <button type="button" onclick="removeCompetitor(${c.id})" aria-label="경쟁업체 삭제"><i class="fas fa-times"></i></button>
            </div>`).join('');
        } else {
            compHtml += '<small class="text-muted">등록된 경쟁업체가 없습니다</small>';
        }
        if (compList.length >= maxComp) {
            compHtml += `<div class="small text-danger mt-1"><i class="fas fa-circle-info me-1"></i>최대 ${maxComp}개까지 등록할 수 있습니다</div>`;
        }
        document.getElementById('competitorList').innerHTML = compHtml;
    } catch (e) { console.error(e); }
}

async function collectNewPlaceName() {
    try {
        // 강제 재수집이 아니므로 오늘 수집한 기존 매장은 건너뛰고 새 URL만 확인한다.
        await apiPost('/api/owner/ad/fetch-now', {});
    } catch (e) {
        // 등록은 유지한다. 일시적인 네이버 조회 실패 시 입력한 별칭을 표시하고 다음 수집 때 보정한다.
        console.warn('새 플레이스의 실제 매장명을 바로 확인하지 못했습니다.', e);
    }
}

async function refreshAnalysisAfterTargetChange() {
    await Promise.all([
        loadManageLists(),
        reloadAnalysis(),
        loadAnalysisOverview(),
        loadAnalysisTrend(),
    ]);
}

async function addPlaceProfile() {
    const url = document.getElementById('newProfileUrl').value.trim();
    const nick = document.getElementById('newProfileNick').value.trim();
    const keyword = document.getElementById('newProfileKeyword').value.trim();
    if (!url) { alert('플레이스 URL을 입력하세요'); return; }
    if (!keyword) { alert('우리 매장과 경쟁업체를 비교할 공통 검색어를 입력하세요'); return; }
    const btn = document.getElementById('addProfileBtn');
    const original = btn?.innerHTML;
    try {
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i><span>확인 중</span>';
        }
        await apiPost('/api/owner/ad/place-profiles', { place_url: url, nickname: nick || null, analysis_keyword: keyword });
        await collectNewPlaceName();
        document.getElementById('newProfileUrl').value = '';
        document.getElementById('newProfileNick').value = '';
        document.getElementById('newProfileKeyword').value = '';
        await refreshAnalysisAfterTargetChange();
    } catch (e) {
        alert('등록 실패: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

async function addCompetitor() {
    const url = document.getElementById('newCompUrl').value.trim();
    const memo = document.getElementById('newCompMemo').value.trim();
    if (!url) { alert('경쟁업체 URL을 입력하세요'); return; }
    if (!memo) { alert('구분하기 쉬운 경쟁업체명을 입력하세요'); return; }
    const btn = document.getElementById('addCompetitorBtn');
    const original = btn?.innerHTML;
    try {
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i><span>확인 중</span>';
        }
        await apiPost('/api/owner/ad/competitors', { competitor_place_url: url, memo: memo || null });
        await collectNewPlaceName();
        document.getElementById('newCompUrl').value = '';
        document.getElementById('newCompMemo').value = '';
        await refreshAnalysisAfterTargetChange();
    } catch (e) {
        alert('등록 실패: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

async function removePlaceProfile(id) {
    if (!confirm('이 프로필을 삭제하시겠습니까?')) return;
    try {
        await api(`/api/owner/ad/place-profiles/${id}`, { method: 'DELETE' });
        loadManageLists();
        reloadAnalysis();
    } catch (e) { alert('삭제 실패: ' + e.message); }
}

async function removeCompetitor(id) {
    if (!confirm('이 경쟁업체를 삭제하시겠습니까?')) return;
    try {
        await api(`/api/owner/ad/competitors/${id}`, { method: 'DELETE' });
        loadManageLists();
        reloadAnalysis();
    } catch (e) { alert('삭제 실패: ' + e.message); }
}

// 순위 표기 — 200위까지 수집하며, 그 밖이면 "200위 밖"으로 표시
const RANK_OUT_OF_RANGE = 201;
// 경쟁업체 등록 상한 (서버 owner_routes.MAX_COMPETITORS 와 동일)
const MAX_COMPETITORS = 5;
function formatRank(value) {
    if (value === null || value === undefined || value === 0) return '-';
    return value >= RANK_OUT_OF_RANGE ? '200위 밖' : value + '위';
}

function rankRefreshGuide(compact = false) {
    return `<div class="rank-refresh-guide${compact ? ' is-compact' : ''}">
        <i class="fas fa-clock"></i>
        <span><strong>순위는 매일 오후 2시에 자동으로 업데이트 됩니다.</strong><small><span class="rank-update-copy-desktop">업데이트 전에 실시간으로 바로 확인하려면 <b>광고분석하기</b> 버튼을 눌러 주세요.</span><span class="rank-update-copy-mobile">실시간 확인은 <b>광고분석하기</b> 버튼을 눌러 주세요.</span></small></span>
    </div>`;
}

// ── 4) 날짜별 기록과 마케팅 추천 — 모든 영역을 기본으로 펼쳐 둔다 ──
// 이름은 기존 호출부(프로필/경쟁업체 추가·삭제 등)와의 호환을 위해 유지한다.
async function reloadAnalysis() {
    const box = document.getElementById('analysisDetail');
    if (!box) return;
    try {
        const range = document.getElementById('analysisRange')?.value || 'all';
        const detail = await apiGet(`/api/owner/ad/analysis?range=${range}`);
        renderCollectStatus(detail.collection_status);

        const buildRows = (items, typeLabel) => items.map(p => {
            const name = p.actual_name || p.nickname || p.memo || p.place_url;
            if (!p.data || p.data.length === 0) {
                return `<div class="mb-3"><strong class="small">${typeLabel} (${escapeHtml(name)})</strong>
                    <p class="text-muted small mb-0">기록이 없어요</p></div>`;
            }
            const rows = p.data.map(d => `<tr><td>${d.date}</td><td>${d.blog_review_count}</td><td>${d.visitor_review_count}</td><td>${formatRank(d.place_rank)}</td></tr>`).join('');
            return `<div class="mb-3"><strong class="small">${typeLabel} (${escapeHtml(name)})</strong>
                <div class="table-responsive"><table class="table table-sm table-hover mt-1 mb-0">
                    <thead class="table-light"><tr><th>날짜</th><th>블로그리뷰</th><th>방문자리뷰</th><th>순위</th></tr></thead>
                    <tbody>${rows}</tbody></table></div></div>`;
        }).join('');

        const myRows = detail.my_places.length ? buildRows(detail.my_places, '우리 매장') : '<p class="text-muted small mb-0">등록된 매장이 없어요</p>';
        const compRows = detail.competitors.length ? buildRows(detail.competitors, '경쟁업체') : '<p class="text-muted small mb-0">등록된 경쟁업체가 없어요</p>';

        box.innerHTML = `<div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-0 d-flex justify-content-between align-items-center flex-wrap gap-2">
                <h6 class="mb-0 fw-bold"><i class="fas fa-calendar-days text-primary me-2"></i>날짜별 상세 기록과 마케팅 추천</h6>
                <div>
                        <select class="form-select form-select-sm" style="width:120px" id="analysisRange" onchange="reloadAnalysis()">
                            <option value="all" ${range === 'all' ? 'selected' : ''}>전체 기간</option>
                            <option value="month" ${range === 'month' ? 'selected' : ''}>최근 1개월</option>
                            <option value="week" ${range === 'week' ? 'selected' : ''}>최근 1주</option>
                            <option value="day" ${range === 'day' ? 'selected' : ''}>어제부터</option>
                        </select>
                </div>
            </div>
            <div class="card-body pt-2" id="analysisDetailBody">
                    ${rankRefreshGuide()}
                    <div class="analysis-detail-grid">
                        <section class="analysis-detail-section">
                            <h6><i class="fas fa-store me-2"></i>우리 매장 일자별 기록</h6>
                            <div id="detailTabMy" class="analysis-scroll">${myRows}</div>
                        </section>
                        <section class="analysis-detail-section competitor">
                            <h6><i class="fas fa-users me-2"></i>경쟁업체 일자별 기록</h6>
                            <div id="detailTabComp" class="analysis-scroll">${compRows}</div>
                        </section>
                    </div>
                    <div class="border-top mt-3 pt-3">
                        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                            <h6 class="mb-0 fw-bold"><i class="fas fa-wand-magic-sparkles me-2" style="color:#6366f1"></i>무엇을 하면 좋을까요?</h6>
                            <button class="btn btn-sm btn-outline-primary" onclick="generateAIRecommendation()" id="aiRecommendBtn">
                                <i class="fas fa-magic me-1"></i>추천 받기
                            </button>
                        </div>
                        <div id="aiRecommendBody">
                            <p class="text-muted small mb-0"><strong>추천 받기</strong>를 누르면 경쟁업체와의 차이를 계산해 먼저 할 일을 알려드려요.</p>
                        </div>
                    </div>
            </div>
        </div>`;
    } catch (e) {
        box.innerHTML = `<div class="alert alert-danger py-2 mb-0 small"><i class="fas fa-exclamation-circle me-2"></i>${escapeHtml(e.message)}</div>`;
    }
}

// AI 마케팅 추천 생성
async function generateAIRecommendation() {
    const btn = document.getElementById('aiRecommendBtn');
    const body = document.getElementById('aiRecommendBody');
    if (!btn || !body) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>분석중...';
    body.innerHTML = adpayLoadingMarkup('우리 매장과 경쟁업체 지표 차이를 계산하고 있습니다...');

    // OpenAI 키가 등록돼 있으면 AI 추천을, 아니면 아래 규칙 기반 문구를 사용한다.
    try {
        const rec = await apiGet('/api/owner/ad/recommendation');
        if (rec.mode === 'ai' && rec.text) {
            body.innerHTML = `<div class="alert alert-primary bg-primary bg-opacity-10 border-0 mb-0">
                <div class="fw-bold small mb-1"><i class="fas fa-robot me-1"></i>AI 추천</div>
                <div class="small" style="white-space:pre-line">${escapeHtml(rec.text)}</div>
            </div>`;
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-magic me-1"></i>추천 받기';
            return;
        }
    } catch (e) {
        // 추천 API 실패는 무시하고 규칙 기반으로 진행한다.
        console.warn('AI 추천 조회 실패, 규칙 기반으로 대체합니다:', e.message);
    }

    try {
        const range = document.getElementById('analysisRange')?.value || 'all';
        const [summary, detail] = await Promise.all([
            apiGet(`/api/owner/ad/analysis/summary?range=${range}`),
            apiGet(`/api/owner/ad/analysis?range=${range}`)
        ]);

        // 데이터 수집
        const myPlaces = summary.my_places || [];
        const competitors = summary.competitors || [];

        if (myPlaces.length === 0) {
            body.innerHTML = '<div class="alert alert-warning mb-0"><i class="fas fa-exclamation-triangle me-1"></i>우리 매장 프로필을 먼저 등록해주세요.</div>';
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-magic me-1"></i>분석 받기';
            return;
        }

        // 분석 로직 - 우리매장 vs 경쟁업체 비교
        let myTotalBlog = 0, myTotalVisitor = 0, myBestRank = 999;
        let compTotalBlog = 0, compTotalVisitor = 0, compBestRank = 999;
        let myCount = 0, compCount = 0;

        myPlaces.forEach(p => {
            if (p.metrics) {
                myTotalBlog += p.metrics.latest_blog_reviews || 0;
                myTotalVisitor += p.metrics.latest_visitor_reviews || 0;
                if (p.metrics.latest_rank && p.metrics.latest_rank < myBestRank) myBestRank = p.metrics.latest_rank;
                myCount++;
            }
        });
        competitors.forEach(c => {
            if (c.metrics) {
                compTotalBlog += c.metrics.latest_blog_reviews || 0;
                compTotalVisitor += c.metrics.latest_visitor_reviews || 0;
                if (c.metrics.latest_rank && c.metrics.latest_rank < compBestRank) compBestRank = c.metrics.latest_rank;
                compCount++;
            }
        });

        if (myCount === 0 || compCount === 0) {
            const missing = myCount === 0 ? '우리 매장' : '경쟁업체';
            body.innerHTML = `<div class="alert alert-warning mb-0">
                <i class="fas fa-database me-2"></i>${missing}의 실제 분석 지표가 없습니다.
                최고관리자가 <strong>광고 분석 관리</strong>에서 같은 검색어 기준의 리뷰 수와 검색 순위를 입력한 뒤 다시 분석해주세요.
            </div>`;
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-magic me-1"></i>분석 받기';
            return;
        }

        const avgMyBlog = myCount > 0 ? Math.round(myTotalBlog / myCount) : 0;
        const avgMyVisitor = myCount > 0 ? Math.round(myTotalVisitor / myCount) : 0;
        const avgCompBlog = compCount > 0 ? Math.round(compTotalBlog / compCount) : 0;
        const avgCompVisitor = compCount > 0 ? Math.round(compTotalVisitor / compCount) : 0;

        // AI 추천 생성
        let recommendations = [];
        let overallScore = 0;
        let scoreMax = 0;

        // 1. 블로그 리뷰 분석
        scoreMax += 30;
        if (avgMyBlog < avgCompBlog) {
            const gap = avgCompBlog - avgMyBlog;
            overallScore += Math.max(0, 30 - gap * 2);
            recommendations.push({
                icon: 'fas fa-blog', color: '#3b82f6', category: '블로그 마케팅',
                status: 'warning',
                title: `블로그 리뷰 수가 경쟁업체보다 ${gap}건 적습니다`,
                desc: `경쟁업체 평균 ${avgCompBlog}건 vs 우리매장 ${avgMyBlog}건`,
                actions: [
                    '블로그 체험단을 운영하여 리뷰를 확보하세요',
                    '인스타그램/블로그 인플루언서 협업을 고려하세요',
                    '네이버 플레이스에 방문자 리뷰 이벤트를 진행하세요',
                    `목표: 최소 ${avgCompBlog}건 이상으로 블로그 리뷰를 늘리세요`
                ]
            });
        } else {
            overallScore += 30;
            recommendations.push({
                icon: 'fas fa-blog', color: '#10b981', category: '블로그 마케팅',
                status: 'good',
                title: '블로그 리뷰가 경쟁업체보다 우위에 있습니다!',
                desc: `우리매장 ${avgMyBlog}건 vs 경쟁업체 평균 ${avgCompBlog}건`,
                actions: ['현재 블로그 마케팅을 유지하면서 꾸준히 관리하세요', '양질의 콘텐츠 리뷰를 중점적으로 확보하세요']
            });
        }

        // 2. 방문자 리뷰 분석
        scoreMax += 30;
        if (avgMyVisitor < avgCompVisitor) {
            const gap = avgCompVisitor - avgMyVisitor;
            overallScore += Math.max(0, 30 - gap);
            recommendations.push({
                icon: 'fas fa-star', color: '#f59e0b', category: '방문자 리뷰',
                status: 'warning',
                title: `방문자 리뷰가 경쟁업체보다 ${gap}건 부족합니다`,
                desc: `경쟁업체 평균 ${avgCompVisitor}건 vs 우리매장 ${avgMyVisitor}건`,
                actions: [
                    '방문 고객에게 리뷰 작성을 적극 요청하세요',
                    '리뷰 작성 시 할인 쿠폰이나 소정의 혜택을 제공하세요',
                    'QR코드를 활용한 간편 리뷰 작성 시스템을 도입하세요',
                    '영수증 리뷰 이벤트를 활용하세요 (영수증 리뷰관리 메뉴 참고)'
                ]
            });
        } else {
            overallScore += 30;
            recommendations.push({
                icon: 'fas fa-star', color: '#10b981', category: '방문자 리뷰',
                status: 'good',
                title: '방문자 리뷰가 경쟁업체보다 많습니다!',
                desc: `우리매장 ${avgMyVisitor}건 vs 경쟁업체 평균 ${avgCompVisitor}건`,
                actions: ['리뷰 품질을 높여 신뢰도를 강화하세요', '부정적 리뷰에 대한 정중한 답변을 달아주세요']
            });
        }

        // 3. 순위 분석
        scoreMax += 20;
        if (myBestRank !== 999 && compBestRank !== 999) {
            if (myBestRank > compBestRank) {
                overallScore += Math.max(0, 20 - (myBestRank - compBestRank) * 3);
                recommendations.push({
                    icon: 'fas fa-trophy', color: '#ef4444', category: '플레이스 순위',
                    status: 'danger',
                    title: `순위가 경쟁업체보다 낮습니다 (${myBestRank}위 vs ${compBestRank}위)`,
                    desc: '플레이스 순위는 리뷰 수, 평점, 방문자 수에 영향을 받습니다',
                    actions: [
                        '플레이스 방문 광고를 통해 방문자 수를 늘리세요',
                        '매장 정보(사진, 메뉴, 영업시간 등)를 정확히 업데이트하세요',
                        '네이버/카카오 키워드 광고와 병행하세요',
                        '정기적인 소식글/이벤트 게시로 활성도를 높이세요'
                    ]
                });
            } else {
                overallScore += 20;
                recommendations.push({
                    icon: 'fas fa-trophy', color: '#10b981', category: '플레이스 순위',
                    status: 'good',
                    title: `순위가 경쟁업체보다 높습니다! (${myBestRank}위 vs ${compBestRank}위)`,
                    desc: '현재 검색 순위에서 우위를 유지하고 있습니다',
                    actions: ['현재 순위를 유지하기 위해 꾸준히 관리하세요']
                });
            }
        }

        // 4. 종합 추천
        scoreMax += 20;
        overallScore += 10; // base
        if (compCount === 0) {
            recommendations.push({
                icon: 'fas fa-binoculars', color: '#8b5cf6', category: '경쟁사 분석',
                status: 'info',
                title: '경쟁업체를 등록하면 더 정확한 분석이 가능합니다',
                desc: '상단 관리 버튼에서 경쟁업체를 추가해주세요',
                actions: ['주변 유사 업종 매장을 경쟁업체로 등록하세요', '최소 2~3개의 경쟁업체를 등록하면 비교 분석이 가능합니다']
            });
        } else {
            recommendations.push({
                icon: 'fas fa-lightbulb', color: '#8b5cf6', category: '종합 마케팅 전략',
                status: 'info',
                title: '추천 마케팅 실행 순서',
                desc: '가장 효과적인 순서대로 마케팅을 진행하세요',
                actions: [
                    '1단계: 매장 기본 정보 최신화 (사진, 메뉴, 영업시간)',
                    '2단계: 방문자 리뷰 확보 (현재 고객 활용)',
                    '3단계: 블로그 체험단 운영 (신규 고객 확보)',
                    '4단계: 플레이스 방문 광고 (순위 향상)',
                    '5단계: SNS 마케팅 병행 (브랜드 인지도 강화)'
                ]
            });
        }

        const scorePercent = scoreMax > 0 ? Math.round(overallScore / scoreMax * 100) : 0;
        const scoreColor = scorePercent >= 70 ? '#10b981' : scorePercent >= 40 ? '#f59e0b' : '#ef4444';
        const scoreLabel = scorePercent >= 70 ? '양호' : scorePercent >= 40 ? '개선 필요' : '위험';

        let recHtml = `
            <div class="text-center mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(99,102,241,.05),rgba(168,85,247,.05))">
                <div class="d-inline-flex align-items-center justify-content-center mb-2" style="width:80px;height:80px;border-radius:50%;border:4px solid ${scoreColor};">
                    <div><span class="fw-bold fs-4" style="color:${scoreColor}">${scorePercent}</span><small class="text-muted d-block" style="font-size:.65rem;">점</small></div>
                </div>
                <div class="fw-bold" style="color:${scoreColor}">${scoreLabel}</div>
                <small class="text-muted">경쟁업체 대비 마케팅 경쟁력 점수</small>
            </div>`;

        recommendations.forEach(r => {
            const statusBg = r.status === 'good' ? 'rgba(16,185,129,.08)' : r.status === 'danger' ? 'rgba(239,68,68,.08)' : r.status === 'warning' ? 'rgba(245,158,11,.08)' : 'rgba(99,102,241,.08)';
            const statusBorder = r.status === 'good' ? 'rgba(16,185,129,.2)' : r.status === 'danger' ? 'rgba(239,68,68,.2)' : r.status === 'warning' ? 'rgba(245,158,11,.2)' : 'rgba(99,102,241,.2)';
            recHtml += `<div class="mb-3 p-3 rounded-3" style="background:${statusBg};border:1px solid ${statusBorder}">
                <div class="d-flex align-items-center gap-2 mb-2">
                    <i class="${r.icon}" style="color:${r.color};font-size:1.1rem;"></i>
                    <span class="badge" style="background:${r.color};color:#fff;font-size:.7rem;">${r.category}</span>
                </div>
                <div class="fw-bold mb-1" style="font-size:.9rem;">${r.title}</div>
                <div class="text-muted small mb-2">${r.desc}</div>
                <ul class="mb-0 ps-3" style="font-size:.82rem;">
                    ${r.actions.map(a => `<li class="mb-1">${a}</li>`).join('')}
                </ul>
            </div>`;
        });

        body.innerHTML = recHtml;
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger mb-0"><i class="fas fa-exclamation-circle me-1"></i>${escapeHtml(e.message)}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-magic me-1"></i>다시 분석';
}

async function loadOwnerAdOrders(c, t) {
    t.textContent = '내 광고 주문';
    // 본문이 비어 있거나 예상과 다른 응답이 와도 페이지 전체가 죽지 않게 한다.
    const orders = (await apiGet('/api/owner/ad/orders')) || [];
    c.innerHTML = `<div class="workspace-hero mb-3">
        <div><span class="workspace-eyebrow">AD ORDERS</span><h2>내 광고 주문</h2><p>요청 후 최고관리자 검토와 집행을 거쳐 완료됩니다.</p></div>
        <button class="btn btn-light" onclick="navigate('owner-adorder-new')"><i class="fas fa-plus me-1"></i>새 주문</button>
    </div>
    <div class="process-steps mb-3">
        <div class="active"><span>1</span><strong>요청</strong></div><i class="fas fa-chevron-right"></i>
        <div><span>2</span><strong>관리자 검토</strong></div><i class="fas fa-chevron-right"></i>
        <div><span>3</span><strong>집행</strong></div><i class="fas fa-chevron-right"></i>
        <div><span>4</span><strong>완료</strong></div>
    </div>
    <div id="ownerAdExecBody" class="mb-3">${adpayLoadingMarkup()}</div>
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">광고 주문 목록</h5>
        <button class="btn btn-primary btn-sm" onclick="navigate('owner-adorder-new')"><i class="fas fa-plus me-1"></i>새 주문</button>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm">
            <thead><tr><th>ID</th><th>유형</th><th>상태</th><th>요약</th><th>관리자메모</th><th>날짜</th></tr></thead>
            <tbody>${orders.map(o => {
                let summary = '';
                if (o.blog_detail) summary = `${o.blog_detail.campaign_name} · ${o.blog_detail.order_count || 1}건 · ${Number(o.blog_detail.est_total_cost || 0).toLocaleString()}원`;
                if (o.place_traffic_detail) summary = `${o.place_traffic_detail.place_name_or_id} · ${o.place_traffic_detail.order_count || 1}건 · ${Number(o.place_traffic_detail.est_total_cost || 0).toLocaleString()}원`;
                if (o.shorts_detail) {
                    const d = o.shorts_detail;
                    const counts = [];
                    if (d.distribution_count) counts.push(`배포 ${d.distribution_count}건`);
                    if (d.video_production_count) counts.push(`제작 ${d.video_production_count}건`);
                    summary = `${d.campaign_name} (${d.campaign_type_label}${counts.length ? ' · ' + counts.join(' · ') : ''})`;
                }
                return `<tr><td>${o.id}</td><td>${adOrderTypeBadge(o.type)}</td><td>${statusBadge(o.status)}</td><td>${escapeHtml(summary)}</td><td>${escapeHtml(o.admin_memo||'-')}</td><td>${formatDate(o.created_at)}</td></tr>`;
            }).join('') || '<tr><td colspan="6" class="text-center text-muted py-5"><i class="fas fa-inbox d-block fs-3 mb-2 opacity-50"></i>광고 주문이 없습니다.</td></tr>'}</tbody>
        </table></div></div></div>`;
    loadOwnerAdExecutions();   // 집행 현황은 실패해도 주문 목록에 영향 없다
}

// 사장님용 광고 집행 현황 — 카드 버튼 클릭 시 모바일은 바텀시트, PC는 팝업으로 표시
let _ownerExecSummaryCache = null;

async function loadOwnerAdExecutions() {
    const body = document.getElementById('ownerAdExecBody');
    if (!body) return;
    try {
        const s = await apiGet('/api/owner/ad/executions/summary');
        _ownerExecSummaryCache = s;
        const m = s.merchant;

        if (!m) {
            body.innerHTML = '';
            return;
        }

        const items = m.items || [];
        const target = items.reduce((sum, it) => sum + (it.monthly_target || 0), 0);
        const done = items.reduce((sum, it) => sum + (it.month_total || 0), 0);

        if (target <= 0) {
            body.innerHTML = `
            <div class="card border-0 shadow-sm mb-2" style="border-radius:14px;overflow:hidden;">
                <div class="card-body py-3 px-4 d-flex align-items-center gap-3">
                    <div class="d-flex align-items-center justify-content-center flex-shrink-0" style="width:44px;height:44px;border-radius:50%;background:rgba(249,115,22,.1);">
                        <i class="fas fa-chart-bar" style="color:#f97316;font-size:1.1rem;"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="fw-bold" style="font-size:.95rem;">이번 달 광고 집행 현황</div>
                        <div class="text-muted small">집행 목표 미설정 (플랜 확인 필요)</div>
                    </div>
                </div>
            </div>`;
            return;
        }

        const pct = Math.round(done / target * 100);
        const barPct = Math.min(pct, 100);
        const barClr = pct >= 100 ? '#10b981' : pct >= 60 ? '#3b82f6' : '#f59e0b';
        const planBadgeClr = PLAN_ACCENTS[m.plan_code] || 'secondary';

        body.innerHTML = `
        <div class="card border-0 shadow-sm mb-2" style="border-radius:14px;overflow:hidden;cursor:pointer;"
             onclick="openOwnerExecPanel()" role="button" tabindex="0"
             onkeydown="if(event.key==='Enter')openOwnerExecPanel()">
            <div class="card-body py-3 px-4">
                <div class="d-flex align-items-center gap-3">
                    <div class="d-flex align-items-center justify-content-center flex-shrink-0"
                         style="width:52px;height:52px;border-radius:50%;background:${barClr}20;border:2px solid ${barClr}40;">
                        <span class="fw-bold" style="color:${barClr};font-size:1rem;">${pct}%</span>
                    </div>
                    <div class="flex-grow-1 min-width-0">
                        <div class="d-flex align-items-center gap-2 mb-1">
                            <span class="fw-bold" style="font-size:.95rem;">이번 달 광고 집행</span>
                            <span class="badge bg-${planBadgeClr}" style="font-size:.65rem;">${escapeHtml(m.plan_name)}</span>
                        </div>
                        <div class="progress mb-1" style="height:8px;border-radius:99px;background:#e5e7eb;">
                            <div class="progress-bar" role="progressbar"
                                 style="width:${barPct}%;background:${barClr};border-radius:99px;"
                                 aria-valuenow="${barPct}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                        <div class="text-muted" style="font-size:.78rem;">${done.toLocaleString()}건 집행 / 목표 ${target.toLocaleString()}건</div>
                    </div>
                    <i class="fas fa-chevron-right text-muted flex-shrink-0" style="font-size:.8rem;"></i>
                </div>
            </div>
        </div>
        <!-- 바텀시트 / 팝업 오버레이 -->
        <div id="execPanelOverlay" onclick="closeOwnerExecPanel()"
             style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1040;"></div>
        <!-- 바텀시트 (모바일) -->
        <div id="execPanelSheet"
             style="display:none;position:fixed;bottom:0;left:0;right:0;z-index:1050;background:#fff;
                    border-radius:20px 20px 0 0;padding:0;max-height:80vh;overflow-y:auto;
                    box-shadow:0 -4px 24px rgba(0,0,0,.15);">
            <div style="text-align:center;padding:12px 0 0;">
                <div style="width:40px;height:4px;border-radius:2px;background:#d1d5db;display:inline-block;"></div>
            </div>
            <div id="execPanelContent" style="padding:20px 20px 32px;"></div>
        </div>
        <!-- 팝업 (PC) -->
        <div id="execPanelModal"
             style="display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
                    z-index:1050;background:#fff;border-radius:16px;
                    box-shadow:0 20px 60px rgba(0,0,0,.2);width:min(480px,95vw);max-height:80vh;overflow-y:auto;">
            <div style="padding:20px 20px 24px;" id="execModalContent"></div>
        </div>`;

        // 패널 내용 채우기 (공유)
        _buildOwnerExecPanelContent(s, m, items, done, target, pct, barPct, barClr, planBadgeClr);

    } catch (e) {
        const body2 = document.getElementById('ownerAdExecBody');
        if (body2) body2.innerHTML = '';  // 오류 시 조용히 숨김
    }
}

function _buildOwnerExecPanelContent(s, m, items, done, target, pct, barPct, barClr, planBadgeClr) {
    const rows = items.map(it => {
        const iPct = it.monthly_target > 0 ? Math.round(it.month_total / it.monthly_target * 100) : 0;
        const iBarPct = Math.min(iPct, 100);
        const iClr = iPct >= 100 ? '#10b981' : iPct >= 60 ? '#3b82f6' : '#f59e0b';
        return `
        <div class="mb-3">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span style="font-size:.87rem;font-weight:600;">${escapeHtml(it.ad_type_label)}</span>
                <span style="font-size:.82rem;color:${iClr};font-weight:700;">${iPct}%</span>
            </div>
            <div style="height:7px;border-radius:99px;background:#e5e7eb;overflow:hidden;">
                <div style="height:100%;width:${iBarPct}%;background:${iClr};border-radius:99px;transition:width .4s;"></div>
            </div>
            <div style="font-size:.75rem;color:#9ca3af;margin-top:3px;">${it.month_total.toLocaleString()} / ${it.monthly_target.toLocaleString()}건</div>
        </div>`;
    }).join('');

    const html = `
    <div class="d-flex align-items-center gap-3 mb-4">
        <div style="width:56px;height:56px;border-radius:50%;background:${barClr}18;border:3px solid ${barClr}40;
                    display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <span style="font-weight:900;font-size:1.1rem;color:${barClr};">${pct}%</span>
        </div>
        <div>
            <div style="font-weight:700;font-size:1rem;">이번 달 광고 집행 현황</div>
            <div class="d-flex align-items-center gap-2 mt-1">
                <span class="badge bg-${planBadgeClr}" style="font-size:.7rem;">${escapeHtml(m.plan_name)}</span>
                <span style="font-size:.78rem;color:#9ca3af;">${s.month_start} ~ ${s.month_end}</span>
            </div>
        </div>
        <button onclick="closeOwnerExecPanel()" class="btn-close ms-auto" aria-label="닫기"></button>
    </div>
    <div style="height:12px;border-radius:99px;background:#e5e7eb;overflow:hidden;margin-bottom:8px;">
        <div style="height:100%;width:${barPct}%;background:${barClr};border-radius:99px;"></div>
    </div>
    <div style="font-size:.82rem;color:#6b7280;margin-bottom:24px;text-align:right;">
        전체 ${done.toLocaleString()}건 집행 / 목표 ${target.toLocaleString()}건
    </div>
    ${items.length > 1 ? `<div style="border-top:1px solid #f0f0f0;padding-top:16px;">${rows}</div>` : ''}`;

    const content1 = document.getElementById('execPanelContent');
    const content2 = document.getElementById('execModalContent');
    if (content1) content1.innerHTML = html;
    if (content2) content2.innerHTML = html;
}

function openOwnerExecPanel() {
    const isMobile = window.innerWidth < 768;
    document.getElementById('execPanelOverlay').style.display = 'block';
    if (isMobile) {
        const sheet = document.getElementById('execPanelSheet');
        sheet.style.display = 'block';
        sheet.style.transform = 'translateY(100%)';
        sheet.style.transition = 'transform .3s cubic-bezier(.32,.72,0,1)';
        requestAnimationFrame(() => { sheet.style.transform = 'translateY(0)'; });
    } else {
        const modal = document.getElementById('execPanelModal');
        modal.style.display = 'block';
        modal.style.opacity = '0';
        modal.style.transform = 'translate(-50%,-50%) scale(.95)';
        modal.style.transition = 'opacity .2s,transform .2s';
        requestAnimationFrame(() => {
            modal.style.opacity = '1';
            modal.style.transform = 'translate(-50%,-50%) scale(1)';
        });
    }
}

function closeOwnerExecPanel() {
    const isMobile = window.innerWidth < 768;
    document.getElementById('execPanelOverlay').style.display = 'none';
    if (isMobile) {
        const sheet = document.getElementById('execPanelSheet');
        sheet.style.transform = 'translateY(100%)';
        setTimeout(() => { sheet.style.display = 'none'; }, 300);
    } else {
        const modal = document.getElementById('execPanelModal');
        modal.style.opacity = '0';
        modal.style.transform = 'translate(-50%,-50%) scale(.95)';
        setTimeout(() => { modal.style.display = 'none'; }, 200);
    }
}

async function loadOwnerAdOrderNew(c, t) {
    t.textContent = '새 광고 주문';
    // 단가 최신 로드
    try { adPricing = await apiGet('/api/owner/ad/pricing'); } catch(e) {}

    // 탭: 블로그·플레이스는 항상 표시. 쇼츠는 준비 중 안내만.
    const tabsHtml = `<ul class="nav nav-tabs ad-order-tabs mb-4" id="adOrderTabs" role="tablist">
        <li class="nav-item" role="presentation">
            <button type="button" class="nav-link active" data-adtab="blog" role="tab" aria-selected="true" onclick="showAdTab('blog')">
                <i class="fas fa-blog"></i><span>블로그 배포</span>
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button type="button" class="nav-link" data-adtab="place" role="tab" aria-selected="false" onclick="showAdTab('place')">
                <i class="fas fa-map-marker-alt"></i><span>플레이스 방문</span>
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button type="button" class="nav-link" data-adtab="shorts" role="tab" aria-selected="false"
                onclick="alert('쇼츠 배포는 현재 준비 중입니다. 준비가 완료되면 안내드리겠습니다.')">
                <i class="fab fa-youtube"></i><span>쇼츠 배포 <span class="badge bg-secondary ms-1" style="font-size:.65rem">준비 중</span></span>
            </button>
        </li>
    </ul>`;

    const blogTabHtml = `<div id="adTabBlog">
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h5 class="mb-0"><i class="fas fa-blog text-info me-2"></i>블로그 배포 요청</h5>
        <button class="btn btn-sm btn-outline-secondary" onclick="loadBlogConfigToOrder()"><i class="fas fa-download me-1"></i>광고 설정 불러오기</button>
    </div><div class="card-body">
        <div id="blogLoadNotice" class="alert alert-info py-2 small mb-3" style="display:none"></div>
        <div class="row g-3">
            <div class="col-md-6"><label class="form-label">네이버 플레이스 URL</label><input class="form-control" id="blogPlaceUrl" maxlength="500" placeholder="https://m.place.naver.com/..."></div>
            <div class="col-md-6"><label class="form-label">플레이스명 / 매장명 <span class="text-danger">*</span></label><input class="form-control" id="blogCampaign" maxlength="300"></div>
            <div class="col-md-6"><label class="form-label">매장 주소</label><input class="form-control" id="blogAddr"></div>
            <div class="col-md-6"><label class="form-label">문의 연락처</label><input class="form-control" id="blogContact"></div>
            <div class="col-md-6"><label class="form-label">메인 키워드 <span class="text-danger">*</span></label><input class="form-control" id="blogKeywords" placeholder="쉼표로 구분 (최대 5개)"></div>
            <div class="col-md-6"><label class="form-label">작업 키워드</label><input class="form-control" id="blogWorkKeywords" placeholder="쉼표로 구분"></div>
            <div class="col-md-6"><label class="form-label">해시태그</label><input class="form-control" id="blogHashtags" placeholder="쉼표로 구분 (최대 5개)"></div>
            <div class="col-md-6"><label class="form-label">포스트 유형</label>
                <select class="form-select" id="blogPostType">
                    <option value="">선택 안 함</option>
                    <option value="INFO">정보성</option>
                    <option value="REVIEW">리뷰형</option>
                    <option value="FREE">자유형</option>
                </select>
            </div>
            <div class="col-md-6"><label class="form-label">추가 링크</label><input class="form-control" id="blogLinks" placeholder="예: 홈페이지 URL"></div>
            <div class="col-md-6"><label class="form-label">주문 건수 <span class="text-danger">*</span></label><div class="input-group"><input type="number" class="form-control" id="blogOrderCount" min="1" max="10000" value="1" oninput="updateSimpleAdEstimate('blog')"><span class="input-group-text">건</span></div></div>
            <div class="col-12"><label class="form-label">업체 소개</label><textarea class="form-control" id="blogDesc" rows="3"></textarea></div>
            <div class="col-12" id="blogEstimateBox">${simpleAdEstimateMarkup('blog', 1)}</div>
            <div class="col-12"><button class="btn btn-primary" id="blogSubmitBtn" onclick="submitBlogOrder()"><i class="fas fa-paper-plane me-1"></i>검토 요청하기</button></div>
        </div><div id="blogResult" class="mt-3"></div>
    </div></div>
    </div>`;

    const placeTabHtml = `<div id="adTabPlace" style="display:none">
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h5 class="mb-0"><i class="fas fa-map-marker-alt text-success me-2"></i>플레이스 방문 요청</h5>
        <button class="btn btn-sm btn-outline-secondary" onclick="loadPlaceConfigToOrder()"><i class="fas fa-download me-1"></i>광고 설정 불러오기</button>
    </div><div class="card-body">
        <div id="placeLoadNotice" class="alert alert-info py-2 small mb-3" style="display:none"></div>
        <div class="row g-3">
            <div class="col-md-6"><label class="form-label">플레이스명 또는 ID <span class="text-danger">*</span></label><input class="form-control" id="placeName" maxlength="300"></div>
            <div class="col-md-6"><label class="form-label">검색 키워드 (최대 3) <span class="text-danger">*</span></label><input class="form-control" id="placeKeywords" placeholder="쉼표로 구분"></div>
            <div class="col-md-6"><label class="form-label">미션 카테고리</label>
                <select class="form-select" id="placeMissionCategory">
                    <option value="VISIT">VISIT (플레이스 방문)</option>
                    <option value="SAVE">SAVE (플레이스 저장)</option>
                </select>
            </div>
            <div class="col-md-6"><label class="form-label">미션 액션</label>
                <select class="form-select" id="placeMissionAction">
                    <option value="WRITE_REVIEW">방문자 리뷰</option>
                    <option value="FIND_PATH">길찾기</option>
                    <option value="SPOT_CHECK">명소확인</option>
                    <option value="RANDOM_MISSION">랜덤 미션</option>
                    <option value="BUSINESS_HOURS">영업시간</option>
                    <option value="INTRODUCTION">소개</option>
                    <option value="WALK_COUNT">도보수</option>
                    <option value="BUS_STATION">정류장</option>
                    <option value="PLACE_SAVE">플레이스 저장(SAVE)</option>
                </select>
            </div>
            <div class="col-md-6"><label class="form-label">주문 건수 <span class="text-danger">*</span></label><div class="input-group"><input type="number" class="form-control" id="placeOrderCount" min="1" max="10000" value="1" oninput="updateSimpleAdEstimate('place')"><span class="input-group-text">건</span></div></div>
            <div class="col-12" id="placeEstimateBox">${simpleAdEstimateMarkup('place', 1)}</div>
            <div class="col-12"><button class="btn btn-success" id="placeSubmitBtn" onclick="submitPlaceOrder()"><i class="fas fa-paper-plane me-1"></i>검토 요청하기</button></div>
        </div><div id="placeResult" class="mt-3"></div>
    </div></div>
    </div>`;

    const shortsTabHtml = `<div id="adTabShorts" style="display:none">
    <div class="card data-card"><div class="card-body text-center py-5">
        <i class="fab fa-youtube text-danger" style="font-size:3rem"></i>
        <h5 class="mt-3 mb-2">쇼츠 배포는 준비 중입니다</h5>
        <p class="text-muted mb-0">준비가 완료되면 안내드리겠습니다.</p>
    </div></div>
    </div>`;

    c.innerHTML = `<div class="workspace-hero mb-3">
        <div><span class="workspace-eyebrow">NEW CAMPAIGN</span><h2>새 광고 주문</h2><p>필수 정보를 입력하면 관리자가 검토 후 집행 상태를 안내합니다.</p></div>
        <div class="workspace-hero-icon"><i class="fas fa-bullhorn"></i></div>
    </div>${tabsHtml}${blogTabHtml}${placeTabHtml}${shortsTabHtml}`;
}

function simpleAdEstimateData(type, count) {
    const unitPrice = type === 'blog'
        ? Number(adPricing.blog_unit_price || 0)
        : Number(adPricing.place_traffic_unit_price || 0);
    const safeCount = Math.min(10000, Math.max(1, parseInt(count, 10) || 1));
    return { unitPrice, count: safeCount, total: unitPrice * safeCount };
}

function simpleAdEstimateMarkup(type, count) {
    const est = simpleAdEstimateData(type, count);
    const label = type === 'blog' ? '블로그 배포' : '플레이스 방문';
    const unsetNotice = est.unitPrice === 0
        ? '<div class="text-warning mt-2" style="font-size:.78rem"><i class="fas fa-exclamation-triangle me-1"></i>관리자 단가가 아직 설정되지 않았습니다.</div>'
        : '';
    return `<div class="ad-budget-summary">
        <div class="d-flex align-items-center justify-content-between gap-2 mb-2">
            <strong><i class="fas fa-calculator me-1 text-primary"></i>광고 집행 예산</strong>
            <span class="badge bg-light text-dark">${label}</span>
        </div>
        <div class="d-flex justify-content-between ad-budget-line"><span>광고 단가</span><span>${est.unitPrice.toLocaleString()}원 × ${est.count.toLocaleString()}건</span></div>
        <div class="d-flex justify-content-between align-items-end mt-2 pt-2 border-top">
            <span class="fw-bold">예상 합계</span><strong class="ad-budget-total">${est.total.toLocaleString()}원</strong>
        </div>
        <div class="text-muted mt-1" style="font-size:.74rem">부가세 별도 · 주문 접수 시점의 단가로 저장됩니다.</div>
        ${unsetNotice}
    </div>`;
}

function updateSimpleAdEstimate(type) {
    const countId = type === 'blog' ? 'blogOrderCount' : 'placeOrderCount';
    const boxId = type === 'blog' ? 'blogEstimateBox' : 'placeEstimateBox';
    const count = document.getElementById(countId)?.value || 1;
    const box = document.getElementById(boxId);
    if (box) box.innerHTML = simpleAdEstimateMarkup(type, count);
}

function showAdTab(tab) {
    const panels = { blog: 'adTabBlog', place: 'adTabPlace', shorts: 'adTabShorts' };
    Object.entries(panels).forEach(([key, id]) => {
        const el = document.getElementById(id);
        if (el) el.style.display = (key === tab) ? '' : 'none';
    });
    document.querySelectorAll('#adOrderTabs .nav-link').forEach(el => {
        const isActive = el.dataset.adtab === tab;
        el.classList.toggle('active', isActive);
        el.setAttribute('aria-selected', String(isActive));
    });
}
async function loadBlogConfigToOrder() {
    try {
        const d = await apiGet('/api/owner/ad/blog-config');
        if (!d || !d.configured) {
            alert('광고 설정에 등록된 블로그 설정이 없습니다. 먼저 광고 설정 메뉴에서 등록해 주세요.');
            return;
        }
        const setVal = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
        setVal('blogPlaceUrl', d.blog_place_url || '');
        setVal('blogCampaign', d.blog_place_name || '');
        setVal('blogAddr', d.blog_store_address || '');
        setVal('blogContact', d.blog_store_phone || '');
        setVal('blogKeywords', d.blog_main_keyword || '');
        setVal('blogWorkKeywords', (d.blog_work_keywords || []).join(', '));
        setVal('blogHashtags', (d.blog_tags || []).join(', '));
        setVal('blogPostType', d.blog_post_type || '');
        setVal('blogLinks', d.blog_extra_link || '');
        const notice = document.getElementById('blogLoadNotice');
        if (notice) { notice.textContent = '광고 설정에서 불러왔습니다. 필요하면 수정 후 요청하세요.'; notice.style.display = ''; }
    } catch(e) { alert('불러오기 실패: ' + e.message); }
}

async function submitBlogOrder() {
    const campaign = document.getElementById('blogCampaign').value.trim();
    const kw = document.getElementById('blogKeywords').value.split(',').map(s=>s.trim()).filter(Boolean);
    const workKw = document.getElementById('blogWorkKeywords').value.split(',').map(s=>s.trim()).filter(Boolean);
    const links = document.getElementById('blogLinks').value.split(',').map(s=>s.trim()).filter(Boolean);
    const ht = document.getElementById('blogHashtags').value.split(',').map(s=>s.trim()).filter(Boolean);
    const orderCount = parseInt(document.getElementById('blogOrderCount').value, 10);
    if (campaign.length < 2) { alert('플레이스명/매장명을 2자 이상 입력해주세요'); return; }
    if (!kw.length || kw.length > 5) { alert('메인 키워드를 1~5개 입력해주세요'); return; }
    if (ht.length > 5) { alert('해시태그는 최대 5개까지 입력할 수 있습니다'); return; }
    if (!Number.isInteger(orderCount) || orderCount < 1 || orderCount > 10000) { alert('주문 건수를 1~10,000건으로 입력해주세요'); return; }
    const btn = document.getElementById('blogSubmitBtn');
    btn.disabled = true;
    try {
        const res = await apiPost('/api/owner/ad/blog-orders', {
            campaign_name: campaign,
            address: document.getElementById('blogAddr').value,
            contact: document.getElementById('blogContact').value,
            links,
            main_keywords: kw,
            hashtags: ht,
            description: document.getElementById('blogDesc').value,
            extra_image_link: document.getElementById('blogPlaceUrl').value.trim() || '',
            order_count: orderCount,
        });
        document.getElementById('blogResult').innerHTML = `<div class="alert alert-success">요청 #${res.id}이 접수되었습니다. 주문 내역으로 이동합니다.</div>`;
        setTimeout(() => navigate('owner-adorders'), 700);
    } catch(e) {
        btn.disabled = false;
        document.getElementById('blogResult').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════════
// 쇼츠(숏폼) 배포 주문 — 5단계 입력 폼
// 옵션/단가는 서버(/api/owner/ad/shorts-options)가 유일한 출처다.
// ═══════════════════════════════════════════════════════════

let shortsOptions = null;
let shortsStep = 1;

const SHORTS_STEP_LABELS = ['브랜드 정보', '캠페인 설정', '영상 브리프', '크리에이터 자격', '확인 & 제출'];
const SHORTS_INDUSTRIES = ['뷰티', '패션', '식품', 'IT', '금융', '교육', '게임', '생활용품', '기타'];
const SHORTS_CATEGORIES = [
    '엔터테인먼트 / 코미디', '뷰티 / 메이크업', '패션 / 스타일', '음식 / 먹방 / 요리',
    '피트니스 / 건강 / 다이어트', '게임', '여행 / 브이로그', '교육 / 정보 / 꿀팁',
    '반려동물', '음악 / 댄스', '스포츠', '테크 / IT / 리뷰', '라이프스타일',
    '육아 / 가족', '금융 / 재테크',
];
const SHORTS_TONES = [
    '재미있고 유쾌한 (밈/챌린지형)', '트렌디하고 세련된', '신뢰감 있고 전문적인',
    '따뜻하고 감성적인', '에너지틱하고 역동적인', '감각적이고 미니멀한',
    '자연스럽고 일상적인 (브이로그형)',
];
const SHORTS_STYLES = [
    '스토리텔링형 (서사 구조)', '튜토리얼 / 하우투형', '언박싱 / 리뷰형', '비교 / 랭킹형',
    '챌린지 / 참여 유도형', 'Q&A / 인터뷰형', '감성 영상 / 무드형', 'Before & After형',
];
const SHORTS_FOLLOWERS = ['상관없음', '1만+', '5만+', '10만+', '50만+', '100만+'];
const SHORTS_GENDERS = ['전체', '여성', '남성'];
const SHORTS_AGE_GROUPS = ['전체', '10대', '20대', '30대', '40대+'];
const SHORTS_KPIS = ['조회수', '좋아요', '댓글', '공유', '링크클릭', '전환수'];

function shortsVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function shortsChecked(id) {
    const el = document.getElementById(id);
    return !!(el && el.checked);
}

function shortsCsvList(id) {
    return shortsVal(id).split(',').map(s => s.trim()).filter(Boolean);
}

function shortsSelectHtml(id, options, placeholder) {
    return `<select class="form-select" id="${id}">
        <option value="">${placeholder || '선택 안함'}</option>
        ${options.map(o => `<option value="${escapeHtml(o)}">${escapeHtml(o)}</option>`).join('')}
    </select>`;
}

function shortsCampaignType() {
    return shortsVal('shortsCampaignType');
}

function shortsCampaignTypeMeta() {
    if (!shortsOptions) return null;
    return shortsOptions.campaign_types.find(t => t.code === shortsCampaignType()) || null;
}

function shortsSelectedPlatforms() {
    if (!shortsOptions) return [];
    return shortsOptions.platforms.filter(p => shortsChecked(`shortsPf_${p.code}`));
}

function shortsPlatformCounts() {
    const counts = {};
    shortsSelectedPlatforms().forEach(p => {
        const n = parseInt(shortsVal(`shortsPfCnt_${p.code}`), 10);
        if (n > 0) counts[p.code] = n;
    });
    return counts;
}

async function renderShortsOrderForm() {
    const host = document.getElementById('shortsFormHost');
    if (!host) return;
    try {
        if (!shortsOptions) shortsOptions = await apiGet('/api/owner/ad/shorts-options');
    } catch (e) {
        host.innerHTML = `<div class="alert alert-danger mb-0">쇼츠 주문 옵션을 불러오지 못했습니다: ${escapeHtml(e.message)}</div>`;
        return;
    }
    const opt = shortsOptions;

    host.innerHTML = `
    <div class="process-steps mb-3" id="shortsSteps">
        ${SHORTS_STEP_LABELS.map((label, i) => `
            <div data-step="${i + 1}"><span>${i + 1}</span><strong>${label}</strong></div>
            ${i < SHORTS_STEP_LABELS.length - 1 ? '<i class="fas fa-chevron-right"></i>' : ''}
        `).join('')}
    </div>

    <!-- 1) 브랜드 · 캠페인 기본 정보 -->
    <div class="card data-card shorts-step" data-step="1">
        <div class="card-header"><h5><i class="fas fa-store text-danger me-2"></i>브랜드 기본 정보</h5></div>
        <div class="card-body">
            <p class="text-muted" style="font-size:.85rem">매장(브랜드)과 캠페인의 기본 정보를 입력해 주세요.</p>
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">브랜드(매장)명</label>
                    <input class="form-control" id="shortsBrandName" maxlength="200" placeholder="비워두면 매장명이 사용됩니다"></div>
                <div class="col-md-6"><label class="form-label">업종</label>${shortsSelectHtml('shortsIndustry', SHORTS_INDUSTRIES)}</div>
                <div class="col-md-6"><label class="form-label">공식 웹사이트 / 플레이스 URL</label>
                    <input class="form-control" id="shortsWebsite" maxlength="500" placeholder="https://..."></div>
                <div class="col-md-6"><label class="form-label">캠페인 제목 <span class="text-danger">*</span></label>
                    <input class="form-control" id="shortsCampaignName" maxlength="300" placeholder="예: 2026 여름 신메뉴 홍보 캠페인"></div>
                <div class="col-12"><label class="form-label">캠페인 설명</label>
                    <textarea class="form-control" id="shortsDescription" rows="3" placeholder="캠페인 목적, 배경, 특이사항 등을 간략히 설명해 주세요."></textarea></div>
            </div>
        </div>
    </div>

    <!-- 2) 캠페인 설정 -->
    <div class="card data-card shorts-step" data-step="2" style="display:none">
        <div class="card-header"><h5><i class="fas fa-sliders-h text-danger me-2"></i>캠페인 설정</h5></div>
        <div class="card-body">
            <p class="text-muted" style="font-size:.85rem">캠페인 유형, 플랫폼, 배포 건수, 일정을 설정해 주세요.</p>
            <input type="hidden" id="shortsCampaignType" value="">
            <label class="form-label">캠페인 유형 <span class="text-danger">*</span></label>
            <div class="row g-2 mb-4">
                ${opt.campaign_types.map((t, i) => `
                <div class="col-md-6">
                    <button type="button" class="btn w-100 text-start shorts-type-btn" data-code="${t.code}"
                            onclick="shortsSelectCampaignType('${t.code}')"
                            style="border:1.5px solid #e5e7eb;border-radius:12px;padding:.85rem 1rem;background:#fff">
                        <div class="d-flex align-items-center gap-2 mb-1">
                            <span class="fw-bold" style="font-size:.92rem">${escapeHtml(t.label)}</span>
                            ${i === 0 ? '<span class="badge bg-danger" style="font-size:.62rem">인기</span>' : ''}
                        </div>
                        <div class="text-muted" style="font-size:.75rem;white-space:normal">${escapeHtml(t.description)}</div>
                    </button>
                </div>`).join('')}
            </div>

            <div class="row g-3">
                <div class="col-md-6 shorts-dist-field"><label class="form-label">배포 건수 <span class="text-danger">*</span></label>
                    <div class="input-group"><input type="number" class="form-control" id="shortsDistCount" min="1" max="${opt.max_count}" value="10" oninput="shortsUpdateEstimate()"><span class="input-group-text">건</span></div></div>
                <div class="col-md-6 shorts-prod-field"><label class="form-label">영상제작 건수 <span class="text-danger">*</span></label>
                    <div class="input-group"><input type="number" class="form-control" id="shortsProdCount" min="1" max="${opt.max_count}" value="10" oninput="shortsUpdateEstimate()"><span class="input-group-text">건</span></div></div>
            </div>

            <div class="shorts-prod-field mt-4">
                <input type="hidden" id="shortsDurationTier" value="">
                <label class="form-label">영상 길이 <span class="text-danger">*</span></label>
                <div class="row g-2">
                    ${opt.duration_tiers.map(t => `
                    <div class="col-6 col-md-3">
                        <button type="button" class="btn w-100 shorts-tier-btn" data-code="${t.code}"
                                onclick="shortsSelectDurationTier('${t.code}')"
                                style="border:1.5px solid #e5e7eb;border-radius:12px;padding:.7rem .5rem;background:#fff">
                            <div class="fw-bold" style="font-size:.86rem">${escapeHtml(t.label)}</div>
                            <div class="text-muted" style="font-size:.72rem">${t.unit_price.toLocaleString()}원/건</div>
                        </button>
                    </div>`).join('')}
                </div>
                <div class="form-text">선택한 영상 길이에 따라 제작비가 자동 계산됩니다. (부가세 별도)</div>
            </div>

            <div class="shorts-dist-field mt-4">
                <label class="form-label">플랫폼 선택 <span class="text-danger">*</span></label>
                <div class="row g-2">
                    ${opt.platforms.map(p => `
                    <div class="col-md-6">
                        <div class="d-flex align-items-center gap-2 p-2 rounded-3" style="border:1px solid #eee">
                            <div class="form-check mb-0">
                                <input class="form-check-input" type="checkbox" id="shortsPf_${p.code}" onchange="shortsTogglePlatform('${p.code}')">
                                <label class="form-check-label fw-semibold" for="shortsPf_${p.code}" style="font-size:.88rem">${escapeHtml(p.label)}</label>
                            </div>
                            <div class="input-group input-group-sm ms-auto" style="width:120px">
                                <input type="number" class="form-control" id="shortsPfCnt_${p.code}" min="0" max="${opt.max_count}" value="0" disabled oninput="shortsUpdateEstimate()">
                                <span class="input-group-text">건</span>
                            </div>
                        </div>
                    </div>`).join('')}
                </div>
                <div class="form-text" id="shortsPfSum"></div>
            </div>

            <div class="row g-3 mt-3">
                <div class="col-md-6"><label class="form-label">시작 희망일</label><input type="date" class="form-control" id="shortsStartDate"></div>
                <div class="col-md-6"><label class="form-label">종료 희망일</label><input type="date" class="form-control" id="shortsEndDate"></div>
                <div class="col-md-6"><label class="form-label">타겟 키워드 (쉼표 구분)</label><input class="form-control" id="shortsKeywords" placeholder="예: 신상, 할인"></div>
                <div class="col-md-6"><label class="form-label">참고 링크 (쉼표 구분)</label><input class="form-control" id="shortsRefLinks" placeholder="https://..."></div>
                <div class="col-12"><label class="form-label">영상 URL <span class="text-muted" style="font-size:.78rem">(자체 영상 / 기존 영상 기반 배포 시)</span></label>
                    <input class="form-control" id="shortsVideoUrl" placeholder="https://..."></div>
            </div>

            <div id="shortsEstimateBox" class="mt-4"></div>
        </div>
    </div>

    <!-- 3) 영상 브리프 -->
    <div class="card data-card shorts-step" data-step="3" style="display:none">
        <div class="card-header"><h5><i class="fas fa-clapperboard text-danger me-2"></i>영상 제작 브리프</h5></div>
        <div class="card-body">
            <p class="text-muted" style="font-size:.85rem">구체적일수록 완성도 높은 영상이 제작됩니다.</p>
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">제품 / 서비스명</label><input class="form-control" id="shortsProductName" maxlength="300"></div>
                <div class="col-12"><label class="form-label">상세 설명</label><textarea class="form-control" id="shortsProductDetail" rows="3"></textarea></div>
            </div>
            <hr class="my-4">
            <label class="form-label">플랫폼별 카테고리</label>
            <div class="row g-3" id="shortsCategoryHost"></div>
            <hr class="my-4">
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">톤앤매너</label>${shortsSelectHtml('shortsTone', SHORTS_TONES)}</div>
                <div class="col-md-6"><label class="form-label">영상 스타일</label>${shortsSelectHtml('shortsStyle', SHORTS_STYLES)}</div>
                <div class="col-12"><label class="form-label">타겟 소비자층</label><textarea class="form-control" id="shortsTargetAudience" rows="2" placeholder="예: 20~30대 직장인 여성"></textarea></div>
                <div class="col-12"><label class="form-label">반드시 포함할 내용 (핵심 메시지)</label><textarea class="form-control" id="shortsKeyMessages" rows="2"></textarea></div>
                <div class="col-12"><label class="form-label">포함하면 안 되는 내용 (금지 사항)</label><textarea class="form-control" id="shortsAvoid" rows="2"></textarea></div>
                <div class="col-12"><label class="form-label">추천 해시태그 (쉼표 구분)</label><input class="form-control" id="shortsHashtags" placeholder="예: 여름신상, 신메뉴"></div>
            </div>
        </div>
    </div>

    <!-- 4) 크리에이터 자격 · 브랜드 세이프티 -->
    <div class="card data-card shorts-step" data-step="4" style="display:none">
        <div class="card-header"><h5><i class="fas fa-user-check text-danger me-2"></i>크리에이터 자격 &amp; 브랜드 세이프티</h5></div>
        <div class="card-body">
            <p class="text-muted" style="font-size:.85rem">원하는 크리에이터 조건과 브랜드 안전 기준을 설정하세요.</p>
            <div class="row g-3">
                <div class="col-md-4"><label class="form-label">최소 팔로워 / 구독자</label>${shortsSelectHtml('shortsMinFollowers', SHORTS_FOLLOWERS, '상관없음')}</div>
                <div class="col-md-4"><label class="form-label">선호 크리에이터 성별</label>${shortsSelectHtml('shortsGender', SHORTS_GENDERS, '전체')}</div>
                <div class="col-md-4"><label class="form-label">선호 크리에이터 연령대</label>${shortsSelectHtml('shortsAgeGroup', SHORTS_AGE_GROUPS, '전체')}</div>
                <div class="col-12"><label class="form-label">특이사항 / 추가 요구사항</label><textarea class="form-control" id="shortsCreatorReq" rows="2"></textarea></div>
            </div>
            <hr class="my-4">
            <h6 class="fw-bold mb-3"><i class="fas fa-shield-halved text-warning me-1"></i>브랜드 세이프티</h6>
            <div class="row g-3">
                <div class="col-12"><label class="form-label">금지 단어 / 내용</label><input class="form-control" id="shortsForbiddenWords" placeholder="쉼표로 구분해 입력"></div>
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsNoCompetitor"><label class="form-check-label" for="shortsNoCompetitor">경쟁사 언급 금지</label></div></div>
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsNoAdult"><label class="form-check-label" for="shortsNoAdult">성인 콘텐츠 금지</label></div></div>
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsNoViolence"><label class="form-check-label" for="shortsNoViolence">폭력적 콘텐츠 금지</label></div></div>
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsNoPolitical"><label class="form-check-label" for="shortsNoPolitical">정치적 콘텐츠 금지</label></div></div>
            </div>
            <hr class="my-4">
            <h6 class="fw-bold mb-3"><i class="fas fa-chart-line text-success me-1"></i>성과 추적</h6>
            <div class="row g-3">
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsTrackUtm"><label class="form-check-label" for="shortsTrackUtm">UTM 링크 포함 요청</label></div></div>
                <div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" id="shortsTrackPromo"><label class="form-check-label" for="shortsTrackPromo">할인코드 포함 요청</label></div></div>
                <div class="col-12">
                    <label class="form-label">목표 KPI (복수 선택 가능)</label>
                    <div class="d-flex flex-wrap gap-3">
                        ${SHORTS_KPIS.map((k, i) => `<div class="form-check">
                            <input class="form-check-input shorts-kpi" type="checkbox" id="shortsKpi${i}" value="${escapeHtml(k)}">
                            <label class="form-check-label" for="shortsKpi${i}">${escapeHtml(k)}</label>
                        </div>`).join('')}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- 5) 확인 & 제출 -->
    <div class="card data-card shorts-step" data-step="5" style="display:none">
        <div class="card-header"><h5><i class="fas fa-clipboard-check text-danger me-2"></i>확인 &amp; 제출</h5></div>
        <div class="card-body">
            <p class="text-muted" style="font-size:.85rem">입력 내용을 확인하고 쇼츠 배포를 신청하세요.</p>
            <div id="shortsSummary"></div>
            <div class="border rounded-3 p-3 mt-3" style="background:#f8f9fa">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="shortsAgree">
                    <label class="form-check-label fw-semibold" for="shortsAgree">아래 사항에 모두 동의합니다</label>
                </div>
                <ul class="text-muted mb-0 mt-2" style="font-size:.78rem;padding-left:1.2rem">
                    <li>플랫폼 광고 정책을 준수하겠습니다.</li>
                    <li>저작권법 및 초상권 관련 법령을 준수하겠습니다.</li>
                    <li>표시·광고의 공정화에 관한 법률을 준수하겠습니다.</li>
                    <li>허위·과장 광고를 하지 않겠습니다.</li>
                </ul>
            </div>
        </div>
    </div>

    <div class="d-flex justify-content-between align-items-center mt-3">
        <button class="btn btn-outline-secondary" id="shortsPrevBtn" onclick="shortsGoStep(shortsStep - 1)"><i class="fas fa-chevron-left me-1"></i>이전</button>
        <div>
            <button class="btn btn-danger" id="shortsNextBtn" onclick="shortsGoStep(shortsStep + 1)">다음 단계<i class="fas fa-chevron-right ms-1"></i></button>
            <button class="btn btn-danger" id="shortsSubmitBtn" onclick="submitShortsOrder()" style="display:none"><i class="fas fa-paper-plane me-1"></i>쇼츠 배포 신청하기</button>
        </div>
    </div>
    <div id="shortsResult" class="mt-3"></div>`;

    shortsSelectCampaignType(opt.campaign_types[0].code);
    shortsSelectDurationTier(opt.duration_tiers[0].code);
    shortsStep = 1;
    shortsGoStep(1);
}

function shortsSelectCampaignType(code) {
    const el = document.getElementById('shortsCampaignType');
    if (!el) return;
    el.value = code;
    document.querySelectorAll('.shorts-type-btn').forEach(btn => {
        const on = btn.dataset.code === code;
        btn.style.borderColor = on ? '#dc2626' : '#e5e7eb';
        btn.style.background = on ? 'rgba(220,38,38,.05)' : '#fff';
        btn.style.boxShadow = on ? '0 2px 10px rgba(220,38,38,.12)' : 'none';
    });

    const meta = shortsCampaignTypeMeta();
    const showDist = !meta || meta.uses_distribution;
    const showProd = !meta || meta.uses_production;
    document.querySelectorAll('.shorts-dist-field').forEach(el2 => { el2.style.display = showDist ? '' : 'none'; });
    document.querySelectorAll('.shorts-prod-field').forEach(el2 => { el2.style.display = showProd ? '' : 'none'; });
    shortsUpdateEstimate();
}

function shortsSelectDurationTier(code) {
    const el = document.getElementById('shortsDurationTier');
    if (!el) return;
    el.value = code;
    document.querySelectorAll('.shorts-tier-btn').forEach(btn => {
        const on = btn.dataset.code === code;
        btn.style.borderColor = on ? '#dc2626' : '#e5e7eb';
        btn.style.background = on ? 'rgba(220,38,38,.05)' : '#fff';
    });
    shortsUpdateEstimate();
}

function shortsTogglePlatform(code) {
    const on = shortsChecked(`shortsPf_${code}`);
    const countEl = document.getElementById(`shortsPfCnt_${code}`);
    if (countEl) {
        countEl.disabled = !on;
        if (!on) countEl.value = 0;
        else if (parseInt(countEl.value, 10) < 1) {
            // 첫 선택 시 남은 배포 건수를 기본값으로 채워 준다
            const total = parseInt(shortsVal('shortsDistCount'), 10) || 0;
            const others = Object.entries(shortsPlatformCounts())
                .filter(([key]) => key !== code)
                .reduce((sum, [, n]) => sum + n, 0);
            countEl.value = Math.max(total - others, 0);
        }
    }
    shortsUpdateEstimate();
}

function shortsComputeEstimate() {
    const opt = shortsOptions;
    const meta = shortsCampaignTypeMeta();
    if (!opt || !meta) return null;
    const distCount = meta.uses_distribution ? (parseInt(shortsVal('shortsDistCount'), 10) || 0) : 0;
    const prodCount = meta.uses_production ? (parseInt(shortsVal('shortsProdCount'), 10) || 0) : 0;
    const tier = opt.duration_tiers.find(t => t.code === shortsVal('shortsDurationTier'));
    const prodUnit = meta.uses_production && tier ? tier.unit_price : 0;
    const distCost = distCount * opt.distribution_unit_price;
    const prodCost = prodCount * prodUnit;
    return {
        distCount, prodCount, prodUnit, distCost, prodCost,
        distUnit: opt.distribution_unit_price,
        tierLabel: tier ? tier.label : '-',
        total: distCost + prodCost,
    };
}

function shortsUpdateEstimate() {
    const est = shortsComputeEstimate();
    const box = document.getElementById('shortsEstimateBox');
    const meta = shortsCampaignTypeMeta();

    // 플랫폼별 합계 안내
    const sumEl = document.getElementById('shortsPfSum');
    if (sumEl && meta) {
        const counts = shortsPlatformCounts();
        const sum = Object.values(counts).reduce((a, b) => a + b, 0);
        const total = parseInt(shortsVal('shortsDistCount'), 10) || 0;
        if (!meta.uses_distribution) {
            sumEl.innerHTML = '';
        } else if (!Object.keys(counts).length) {
            sumEl.innerHTML = '<span class="text-muted">배포 플랫폼을 1개 이상 선택하세요.</span>';
        } else {
            sumEl.innerHTML = sum === total
                ? `합계 ${sum}건 · <span class="text-success fw-semibold">맞습니다</span>`
                : `합계 ${sum}건 · <span class="text-danger fw-semibold">전체 배포 건수(${total}건)와 다릅니다</span>`;
        }
    }

    if (!box || !est) return;
    const rows = [];
    if (meta.uses_distribution) rows.push([`배포 (${est.distCount}건 × ${est.distUnit.toLocaleString()}원)`, est.distCost]);
    if (meta.uses_production) rows.push([`영상제작 (${est.prodCount}건 × ${est.prodUnit.toLocaleString()}원)`, est.prodCost]);
    box.innerHTML = `
    <div class="border rounded-3 p-3" style="background:linear-gradient(135deg,rgba(220,38,38,.04),rgba(249,115,22,.04))">
        <div class="fw-bold mb-2" style="font-size:.92rem"><i class="fas fa-calculator me-1 text-danger"></i>예상 집행 비용</div>
        ${rows.map(([label, amount]) => `<div class="d-flex justify-content-between" style="font-size:.85rem">
            <span class="text-muted">${escapeHtml(label)}</span><span>${amount.toLocaleString()}원</span>
        </div>`).join('')}
        <hr class="my-2">
        <div class="d-flex justify-content-between fw-bold">
            <span>합계</span><span class="text-danger">${est.total.toLocaleString()}원</span>
        </div>
        <div class="text-muted mt-1" style="font-size:.74rem">부가세 별도 · 최종 금액은 관리자 검토 후 확정됩니다.</div>
    </div>`;
}

function shortsRenderCategorySelects() {
    const host = document.getElementById('shortsCategoryHost');
    if (!host || !shortsOptions) return;
    const meta = shortsCampaignTypeMeta();
    const platforms = (meta && meta.uses_distribution) ? shortsSelectedPlatforms() : shortsOptions.platforms;
    if (!platforms.length) {
        host.innerHTML = '<div class="col-12 text-muted" style="font-size:.85rem">배포 플랫폼을 선택하면 플랫폼별 카테고리를 지정할 수 있습니다.</div>';
        return;
    }
    // 이미 고른 값은 유지한다
    const previous = {};
    platforms.forEach(p => { previous[p.code] = shortsVal(`shortsCat_${p.code}`); });
    host.innerHTML = platforms.map(p => `
        <div class="col-md-6"><label class="form-label">${escapeHtml(p.label)} 카테고리</label>
            ${shortsSelectHtml(`shortsCat_${p.code}`, SHORTS_CATEGORIES)}
        </div>`).join('');
    platforms.forEach(p => {
        const el = document.getElementById(`shortsCat_${p.code}`);
        if (el && previous[p.code]) el.value = previous[p.code];
    });
}

function shortsValidateStep(step) {
    const meta = shortsCampaignTypeMeta();
    if (step === 1) {
        if (shortsVal('shortsCampaignName').length < 2) return '캠페인 제목을 2자 이상 입력해주세요';
        return null;
    }
    if (step === 2) {
        if (!meta) return '캠페인 유형을 선택해주세요';
        if (meta.uses_distribution) {
            const total = parseInt(shortsVal('shortsDistCount'), 10) || 0;
            if (total < 1) return '배포 건수를 1건 이상 입력해주세요';
            const counts = shortsPlatformCounts();
            if (!Object.keys(counts).length) return '배포 플랫폼을 1개 이상 선택하고 건수를 입력해주세요';
            const sum = Object.values(counts).reduce((a, b) => a + b, 0);
            if (sum !== total) return `플랫폼별 배포 건수의 합(${sum}건)이 전체 배포 건수(${total}건)와 일치해야 합니다`;
        }
        if (meta.uses_production) {
            if ((parseInt(shortsVal('shortsProdCount'), 10) || 0) < 1) return '영상제작 건수를 1건 이상 입력해주세요';
            if (!shortsVal('shortsDurationTier')) return '영상 길이를 선택해주세요';
        }
        if (shortsCampaignType() === 'existing_video_distribution' && !shortsVal('shortsVideoUrl')) {
            return '기존 영상 기반 배포는 영상 URL이 필요합니다';
        }
        const start = shortsVal('shortsStartDate');
        const end = shortsVal('shortsEndDate');
        if (start && end && end < start) return '종료 희망일은 시작 희망일 이후여야 합니다';
        return null;
    }
    return null;
}

function shortsGoStep(step) {
    const last = SHORTS_STEP_LABELS.length;
    if (step < 1 || step > last) return;

    // 앞으로 이동할 때만 현재 단계를 검증한다
    if (step > shortsStep) {
        for (let s = shortsStep; s < step; s++) {
            const error = shortsValidateStep(s);
            if (error) { alert(error); return; }
        }
    }
    shortsStep = step;

    document.querySelectorAll('.shorts-step').forEach(el => {
        el.style.display = (parseInt(el.dataset.step, 10) === step) ? '' : 'none';
    });
    document.querySelectorAll('#shortsSteps > div[data-step]').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.step, 10) <= step);
    });

    const prevBtn = document.getElementById('shortsPrevBtn');
    const nextBtn = document.getElementById('shortsNextBtn');
    const submitBtn = document.getElementById('shortsSubmitBtn');
    if (prevBtn) prevBtn.style.visibility = step === 1 ? 'hidden' : 'visible';
    if (nextBtn) nextBtn.style.display = step === last ? 'none' : '';
    if (submitBtn) submitBtn.style.display = step === last ? '' : 'none';

    if (step === 2) shortsUpdateEstimate();
    if (step === 3) shortsRenderCategorySelects();
    if (step === last) shortsRenderSummary();
}

function shortsRenderSummary() {
    const host = document.getElementById('shortsSummary');
    if (!host) return;
    const est = shortsComputeEstimate();
    const meta = shortsCampaignTypeMeta();
    const counts = shortsPlatformCounts();
    const platformText = Object.entries(counts)
        .map(([code, n]) => {
            const p = shortsOptions.platforms.find(x => x.code === code);
            return `${p ? p.label : code} ${n}건`;
        }).join(', ') || '-';

    const rows = [
        ['브랜드(매장)명', shortsVal('shortsBrandName') || '매장명 사용'],
        ['업종', shortsVal('shortsIndustry') || '-'],
        ['캠페인 제목', shortsVal('shortsCampaignName') || '-'],
        ['캠페인 유형', meta ? meta.label : '-'],
    ];
    if (meta && meta.uses_distribution) {
        rows.push(['플랫폼', platformText]);
        rows.push(['배포 건수', `${est.distCount}건`]);
    }
    if (meta && meta.uses_production) {
        rows.push(['영상제작 건수', `${est.prodCount}건`]);
        rows.push(['영상 길이', est.tierLabel]);
    }
    rows.push(['희망 일정', (shortsVal('shortsStartDate') || '-') + ' ~ ' + (shortsVal('shortsEndDate') || '-')]);
    rows.push(['최소 팔로워', shortsVal('shortsMinFollowers') || '상관없음']);

    const costRows = [];
    if (meta && meta.uses_distribution) costRows.push([`배포 (${est.distCount}건 × ${est.distUnit.toLocaleString()}원)`, est.distCost]);
    if (meta && meta.uses_production) costRows.push([`영상제작 (${est.prodCount}건 × ${est.prodUnit.toLocaleString()}원)`, est.prodCost]);

    host.innerHTML = `
    <div class="border rounded-3 p-3 mb-3">
        <h6 class="fw-bold mb-3"><i class="fas fa-list-check me-1 text-danger"></i>입력 내용 요약</h6>
        <div class="row g-2">
            ${rows.map(([label, value]) => `<div class="col-md-6 d-flex justify-content-between border-bottom pb-1" style="font-size:.85rem">
                <span class="text-muted">${escapeHtml(label)}</span><span class="fw-semibold text-end">${escapeHtml(String(value))}</span>
            </div>`).join('')}
        </div>
    </div>
    <div class="border rounded-3 p-3" style="background:linear-gradient(135deg,rgba(220,38,38,.04),rgba(249,115,22,.04))">
        <h6 class="fw-bold mb-3"><i class="fas fa-calculator me-1 text-danger"></i>예상 집행 비용</h6>
        ${costRows.map(([label, amount]) => `<div class="d-flex justify-content-between" style="font-size:.85rem">
            <span class="text-muted">${escapeHtml(label)}</span><span>${amount.toLocaleString()}원</span>
        </div>`).join('')}
        <hr class="my-2">
        <div class="d-flex justify-content-between fw-bold">
            <span>합계</span><span class="text-danger">${est ? est.total.toLocaleString() : 0}원</span>
        </div>
        <div class="text-muted mt-1" style="font-size:.74rem">부가세 별도 · 최종 금액은 관리자 검토 후 확정됩니다.</div>
    </div>`;
}

async function submitShortsOrder() {
    for (let s = 1; s <= SHORTS_STEP_LABELS.length; s++) {
        const error = shortsValidateStep(s);
        if (error) { shortsGoStep(s); alert(error); return; }
    }
    if (!shortsChecked('shortsAgree')) { alert('이용약관에 동의해주세요'); return; }

    const meta = shortsCampaignTypeMeta();
    const categories = {};
    shortsOptions.platforms.forEach(p => {
        const value = shortsVal(`shortsCat_${p.code}`);
        if (value) categories[p.code] = value;
    });
    const kpiGoals = Array.from(document.querySelectorAll('.shorts-kpi:checked')).map(el => el.value);

    const payload = {
        campaign_name: shortsVal('shortsCampaignName'),
        brand_name: shortsVal('shortsBrandName'),
        industry: shortsVal('shortsIndustry'),
        website_url: shortsVal('shortsWebsite'),
        description: shortsVal('shortsDescription'),

        campaign_type: shortsCampaignType(),
        distribution_count: meta.uses_distribution ? (parseInt(shortsVal('shortsDistCount'), 10) || 0) : 0,
        video_production_count: meta.uses_production ? (parseInt(shortsVal('shortsProdCount'), 10) || 0) : 0,
        video_duration_tier: meta.uses_production ? shortsVal('shortsDurationTier') : null,
        platform_counts: meta.uses_distribution ? shortsPlatformCounts() : {},
        start_date: shortsVal('shortsStartDate') || null,
        end_date: shortsVal('shortsEndDate') || null,
        target_keywords: shortsCsvList('shortsKeywords'),
        reference_links: shortsCsvList('shortsRefLinks'),
        uploaded_video_url: shortsVal('shortsVideoUrl'),

        brief_product_name: shortsVal('shortsProductName'),
        brief_product_detail: shortsVal('shortsProductDetail'),
        brief_categories: categories,
        brief_tone: shortsVal('shortsTone'),
        brief_style: shortsVal('shortsStyle'),
        brief_target_audience: shortsVal('shortsTargetAudience'),
        brief_key_messages: shortsVal('shortsKeyMessages'),
        brief_avoid: shortsVal('shortsAvoid'),
        brief_hashtags: shortsCsvList('shortsHashtags'),

        creator_min_followers: shortsVal('shortsMinFollowers'),
        creator_gender: shortsVal('shortsGender'),
        creator_age_group: shortsVal('shortsAgeGroup'),
        creator_requirements: shortsVal('shortsCreatorReq'),

        brand_forbidden_words: shortsVal('shortsForbiddenWords'),
        brand_no_competitor: shortsChecked('shortsNoCompetitor'),
        brand_no_adult: shortsChecked('shortsNoAdult'),
        brand_no_violence: shortsChecked('shortsNoViolence'),
        brand_no_political: shortsChecked('shortsNoPolitical'),

        track_utm: shortsChecked('shortsTrackUtm'),
        track_promo_code: shortsChecked('shortsTrackPromo'),
        kpi_goals: kpiGoals,
    };

    const btn = document.getElementById('shortsSubmitBtn');
    btn.disabled = true;
    try {
        const res = await apiPost('/api/owner/ad/shorts-orders', payload);
        document.getElementById('shortsResult').innerHTML = `<div class="alert alert-success">요청 #${res.id}이 접수되었습니다. 주문 내역으로 이동합니다.</div>`;
        setTimeout(() => navigate('owner-adorders'), 700);
    } catch (e) {
        btn.disabled = false;
        document.getElementById('shortsResult').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

async function loadPlaceConfigToOrder() {
    try {
        const d = await apiGet('/api/owner/ad/place-config');
        if (!d || !d.configured) {
            alert('광고 설정에 등록된 플레이스 방문 설정이 없습니다. 먼저 광고 설정 메뉴에서 등록해 주세요.');
            return;
        }
        const setVal = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
        setVal('placeMissionCategory', d.mission_category || 'VISIT');
        setVal('placeMissionAction', d.mission_action || 'WRITE_REVIEW');
        const notice = document.getElementById('placeLoadNotice');
        if (notice) { notice.textContent = '광고 설정에서 불러왔습니다. 플레이스명과 키워드를 확인 후 요청하세요.'; notice.style.display = ''; }
    } catch(e) { alert('불러오기 실패: ' + e.message); }
}

async function submitPlaceOrder() {
    const placeName = document.getElementById('placeName').value.trim();
    const kw = document.getElementById('placeKeywords').value.split(',').map(s=>s.trim()).filter(Boolean);
    const orderCount = parseInt(document.getElementById('placeOrderCount').value, 10);
    if (placeName.length < 2) { alert('플레이스명 또는 ID를 2자 이상 입력해주세요'); return; }
    if (!kw.length || kw.length > 3) { alert('검색 키워드를 1~3개 입력해주세요'); return; }
    if (!Number.isInteger(orderCount) || orderCount < 1 || orderCount > 10000) { alert('주문 건수를 1~10,000건으로 입력해주세요'); return; }
    const btn = document.getElementById('placeSubmitBtn');
    btn.disabled = true;
    try {
        const res = await apiPost('/api/owner/ad/place-traffic-orders', {
            place_name_or_id: placeName,
            search_keywords: kw,
            order_count: orderCount,
        });
        document.getElementById('placeResult').innerHTML = `<div class="alert alert-success">요청 #${res.id}이 접수되었습니다. 주문 내역으로 이동합니다.</div>`;
        setTimeout(() => navigate('owner-adorders'), 700);
    } catch(e) {
        btn.disabled = false;
        document.getElementById('placeResult').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function crmComingSoon(feature) {
    const msg = feature ? `${feature} 기능은 준비중입니다.` : '준비중인 기능입니다.';
    const existing = document.getElementById('crmToast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.id = 'crmToast';
    toast.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);background:#1f2937;color:#fff;padding:14px 24px;border-radius:12px;font-size:.92rem;font-weight:500;box-shadow:0 10px 30px rgba(0,0,0,.25);z-index:9999;display:flex;align-items:center;gap:10px;animation:crmToastIn .25s ease-out;';
    toast.innerHTML = `<i class="fas fa-tools" style="color:#fbbf24"></i><span>${msg}</span>`;
    document.body.appendChild(toast);
    if (!document.getElementById('crmToastStyle')) {
        const st = document.createElement('style');
        st.id = 'crmToastStyle';
        st.textContent = '@keyframes crmToastIn{from{opacity:0;transform:translate(-50%,-10px)}to{opacity:1;transform:translate(-50%,0)}}';
        document.head.appendChild(st);
    }
    setTimeout(() => { if (toast.parentNode) toast.remove(); }, 2200);
}

// ═══════════════════════════════════════════════════════════
// 고객관리 프로그램 (CRM) — 고도화 버전
// 사장님(owner): 매장 전체 / 직원(designer): 본인 고객·실적 위주
// 백엔드: /api/crm/*
// ═══════════════════════════════════════════════════════════

let crmTab = 'dashboard';
let crmStaffCache = [];
let crmServiceCache = [];
let crmMe = { is_designer:false, staff_id:null, role:'owner' };
let crmScope = 'auto';
let crmCalDate = null;
let crmCalView = 'day';

const CRM_GRADE_COLORS = { VIP:'#a855f7', GOLD:'#f59e0b', SILVER:'#94a3b8', BRONZE:'#b45309', NEW:'#10b981' };
const CRM_RESV_COLORS = { booked:'#f59e0b', confirmed:'#3b82f6', done:'#16a34a', cancelled:'#94a3b8', noshow:'#ef4444' };
let crmChartRefs = [];

function crmDebounce(fn, ms){ let h; return (...a)=>{ clearTimeout(h); h=setTimeout(()=>fn(...a),ms); }; }
function crmDestroyCharts(){ crmChartRefs.forEach(c=>{ try{c.destroy();}catch(e){} }); crmChartRefs=[]; }
function crmScopeQS(){ return crmMe.is_designer ? ('scope='+crmScope) : 'scope=all'; }

function crmNotify(msg, type){
    const colors={ok:'#16a34a',err:'#dc2626',info:'#1f2937'}; const icons={ok:'fa-circle-check',err:'fa-circle-exclamation',info:'fa-info-circle'};
    const t=type||'info'; const ex=document.getElementById('crmToast'); if(ex) ex.remove();
    const el=document.createElement('div'); el.id='crmToast';
    el.style.cssText=`position:fixed;top:24px;left:50%;transform:translateX(-50%);background:${colors[t]};color:#fff;padding:13px 22px;border-radius:12px;font-size:.9rem;font-weight:500;box-shadow:0 10px 30px rgba(0,0,0,.25);z-index:12000;display:flex;align-items:center;gap:10px`;
    el.innerHTML=`<i class="fas ${icons[t]}"></i><span>${msg}</span>`; document.body.appendChild(el);
    setTimeout(()=>{ if(el.parentNode) el.remove(); }, 2400);
}
function crmEnsureModal(){
    let el=document.getElementById('crmDynModal');
    if(!el){
        el=document.createElement('div'); el.className='modal fade'; el.id='crmDynModal'; el.tabIndex=-1;
        el.innerHTML=`<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content" style="border-radius:1rem;border:none">
            <div class="modal-header" style="border-bottom:1px solid #f3f4f6"><h5 class="modal-title fw-bold" id="crmDynTitle"></h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body" id="crmDynBody"></div>
            <div class="modal-footer" id="crmDynFooter" style="border-top:1px solid #f3f4f6"></div></div></div>`;
        document.body.appendChild(el);
    }
    return el;
}
function crmModal(title, body, footer){
    crmEnsureModal();
    document.getElementById('crmDynTitle').textContent=title;
    document.getElementById('crmDynBody').innerHTML=body;
    document.getElementById('crmDynFooter').innerHTML=footer||`<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>`;
    const m=bootstrap.Modal.getOrCreateInstance(document.getElementById('crmDynModal')); m.show(); return m;
}
function crmCloseModal(){ const m=bootstrap.Modal.getInstance(document.getElementById('crmDynModal')); if(m) m.hide(); }

function crmStaffOptions(selectedId){
    return `<option value="">미지정</option>`+crmStaffCache.map(s=>`<option value="${s.id}" ${s.id===selectedId?'selected':''}>${escapeHtml(s.name)}</option>`).join('');
}
function crmServiceSelect(id){
    return `<select class="form-select" id="${id}" onchange="crmFillServiceAmount(this)">
        <option value="">서비스 선택</option>
        ${crmServiceCache.map(s=>`<option value="${escapeHtml(s.name)}" data-price="${s.price}" data-dur="${s.duration_min}">${s.category?('['+escapeHtml(s.category)+'] '):''}${escapeHtml(s.name)} (${formatMoney(s.price)})</option>`).join('')}
    </select>`;
}
function crmFillServiceAmount(sel){
    const opt=sel.options[sel.selectedIndex]; if(!opt) return;
    const price=opt.getAttribute('data-price'); const dur=opt.getAttribute('data-dur');
    const a=document.getElementById('crmVisitAmount'); const n=document.getElementById('crmVisitService');
    const rn=document.getElementById('rfService'); const rd=document.getElementById('rfDur');
    if(price&&a) a.value=Math.round(parseFloat(price));
    if(opt.value&&n) n.value=opt.value;
    if(opt.value&&rn) rn.value=opt.value;
    if(dur&&rd) rd.value=dur;
}
function crmNowLocal(){ const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); return d.toISOString().slice(0,16); }
function crmDateOnly(s){ return s? formatDate(s).split(' ')[0] : '-'; }
function crmTagBadges(tags, auto){
    let html='';
    (tags||[]).forEach(t=>{ html+=`<span class="badge me-1" style="background:#eef2ff;color:#667eea;font-weight:500">#${escapeHtml(t)}</span>`; });
    (auto||[]).forEach(t=>{ html+=`<span class="badge me-1" style="background:#f1f5f9;color:#64748b;font-weight:500;border:1px dashed #cbd5e1">${escapeHtml(t)}</span>`; });
    return html||'<span class="text-muted">-</span>';
}
function crmResvStatusBadge(s, kr){
    const c=CRM_RESV_COLORS[s]||'#94a3b8';
    return `<span class="badge" style="background:${c}1a;color:${c};border:1px solid ${c}55">${kr||s}</span>`;
}

// ─── Loader & Tabs ─────────────────────────────────────────
async function loadCRM(c, t){
    t.textContent='고객관리 프로그램';
    try { crmMe = await apiGet('/api/crm/me'); } catch(e){ crmMe={is_designer:false,staff_id:null,role:'owner'}; }
    if(crmMe.is_designer && crmScope==='auto') crmScope='mine';
    try { crmStaffCache = await apiGet('/api/crm/staff?'+crmScopeQS()); } catch(e){ crmStaffCache=[]; }
    try { crmServiceCache = await apiGet('/api/crm/services'); } catch(e){ crmServiceCache=[]; }
    const tabs=[
        {id:'dashboard',icon:'fa-chart-bar',label:'홈'},
        {id:'customers',icon:'fa-users',label:'고객'},
        {id:'staff',icon:'fa-user-tie',label:'직원'},
        {id:'services',icon:'fa-list-check',label:'서비스'},
        {id:'messages',icon:'fa-comment-dots',label:'메시지'},
    ];
    if(!tabs.find(x=>x.id===crmTab)) crmTab='dashboard';
    const scopeToggle = crmMe.is_designer ? `
        <div class="btn-group btn-group-sm ms-auto" role="group" style="height:fit-content">
            <button class="btn ${crmScope==='mine'?'btn-primary':'btn-outline-primary'}" onclick="crmSetScope('mine')">내 고객</button>
            <button class="btn ${crmScope==='all'?'btn-primary':'btn-outline-primary'}" onclick="crmSetScope('all')">매장 전체</button>
        </div>` : '';
    c.innerHTML=`
        <div class="page-header mb-3 d-flex align-items-start flex-wrap gap-2">
            <div>
                <h2 class="fw-bold mb-1"><i class="fas fa-user-friends me-2" style="color:#667eea"></i>고객관리 프로그램</h2>
                <p class="text-muted mb-0">${escapeHtml(crmMe.merchant_name||'')} · 고객, 직원, 서비스 메뉴와 메시지를 간결하게 관리합니다${crmMe.is_designer?' <span class="badge bg-info ms-1">직원</span>':''}</p>
            </div>
            ${scopeToggle}
        </div>
        <div class="crm-tabbar-wrap mb-4" id="crmTabBarWrap">
            <div class="d-flex flex-wrap gap-1 p-1" style="background:#f3f4f6;border-radius:14px;width:fit-content;max-width:100%" id="crmTabBar">
                ${tabs.map(crmTabBtn).join('')}
            </div>
        </div>
        <div id="crmTabBody">${adpayLoadingMarkup()}</div>`;
    crmSwitchTab(crmTab);
}
function crmTabBtn(tb){
    const a=tb.id===crmTab;
    return `<button class="crm-tab btn${a?' crm-tab-active':''}" data-tab="${tb.id}" onclick="crmSwitchTab('${tb.id}')" style="border:none;border-radius:10px;padding:.5rem .95rem;font-size:.88rem;background:${a?'#fff':'transparent'};color:${a?'#667eea':'#6b7280'};font-weight:${a?'700':'500'};box-shadow:${a?'0 2px 8px rgba(102,126,234,.15)':'none'}"><i class="fas ${tb.icon} me-1"></i><span>${tb.label}</span></button>`;
}
function crmSetScope(s){ crmScope=s; loadCRM(document.getElementById('pageContent'), document.createElement('span')); }
function crmSwitchTab(tab){
    crmTab=tab; crmDestroyCharts();
    document.querySelectorAll('#crmTabBar .crm-tab').forEach(el=>{
        const a=el.dataset.tab===tab;
        el.classList.toggle('crm-tab-active',a);
        el.style.background=a?'#fff':'transparent'; el.style.color=a?'#667eea':'#6b7280';
        el.style.fontWeight=a?'700':'500'; el.style.boxShadow=a?'0 2px 8px rgba(102,126,234,.15)':'none';
    });
    const body=document.getElementById('crmTabBody'); if(!body) return;
    body.innerHTML = adpayLoadingMarkup();
    if(tab==='dashboard') crmRenderDashboard(body);
    else if(tab==='customers') crmRenderCustomers(body);
    else if(tab==='staff') crmRenderStaff(body);
    else if(tab==='messages') crmRenderMessages(body);
    else if(tab==='services') crmRenderServices(body);
}

// ─── Dashboard ─────────────────────────────────────────────
async function crmRenderDashboard(body){
    try{
        const [customers, staff, services, messages] = await Promise.all([
            apiGet('/api/crm/customers?'+crmScopeQS()),
            apiGet('/api/crm/staff?'+crmScopeQS()),
            apiGet('/api/crm/services'),
            apiGet('/api/crm/messages?limit=20')
        ]);
        const card=(icon,color,label,value,sub,tab)=>`<button class="crm-overview-card" onclick="crmSwitchTab('${tab}')">
            <span class="crm-overview-icon" style="background:${color}18;color:${color}"><i class="fas ${icon}"></i></span>
            <span><small>${label}</small><strong>${value}</strong><em>${sub}</em></span><i class="fas fa-chevron-right"></i>
        </button>`;
        const recentCustomers = customers.slice(0, 5);
        body.innerHTML=`
            <div class="crm-welcome mb-3">
                <div><span>ADPAY CRM</span><h3>${escapeHtml(crmMe.merchant_name || '우리 매장')} 고객관리</h3><p>필요한 고객관리 기능만 빠르게 사용할 수 있습니다.</p></div>
                <div class="crm-welcome-mark"><i class="fas fa-wand-magic-sparkles"></i></div>
            </div>
            <div class="crm-overview-grid mb-3">
                ${card('fa-user-group','#2563eb','관리 고객',customers.length+'명','고객 목록과 상세 메모','customers')}
                ${card('fa-users-gear','#7c3aed','활성 직원',staff.length+'명','담당 고객 연결','staff')}
                ${card('fa-list-check','#0f9f80','활성 서비스',services.filter(x=>x.is_active).length+'개','가격과 소요시간','services')}
                ${card('fa-comment-dots','#e87924','최근 메시지',messages.length+'건','템플릿과 발송 내역','messages')}
            </div>
            <div class="card data-card">
                <div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0"><i class="fas fa-clock-rotate-left me-2"></i>최근 등록 고객</h6><button class="btn btn-sm btn-outline-primary" onclick="crmSwitchTab('customers')">전체 고객</button></div>
                <div class="card-body p-0">${recentCustomers.length ? `<div class="crm-recent-list">${recentCustomers.map(customer=>`
                    <button onclick="crmCustomerDetail(${customer.id})">
                        <span class="crm-customer-avatar">${escapeHtml((customer.name||'?')[0])}</span>
                        <span><strong>${escapeHtml(customer.name)}</strong><small>${escapeHtml(customer.phone||'연락처 없음')} · ${escapeHtml(customer.assigned_staff_name||'담당 미지정')}</small></span>
                        <span class="badge bg-light text-dark">${escapeHtml(customer.grade||'NEW')}</span>
                    </button>`).join('')}</div>` : '<div class="empty-state compact"><i class="fas fa-user-plus"></i><p>등록된 고객이 없습니다.</p><button class="btn btn-primary btn-sm" onclick="crmSwitchTab(\'customers\')">첫 고객 등록</button></div>'}</div>
            </div>`;
    }catch(e){ body.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}

async function crmRenderStaff(body){
    try {
        crmStaffCache = await apiGet('/api/crm/staff?'+crmScopeQS());
        body.innerHTML = `
        <div class="card data-card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <div><h5 class="mb-1">직원관리</h5><small class="text-muted">고객 담당자를 확인하고 사장님 계정에서 직원 정보를 관리합니다.</small></div>
                ${crmMe.role === 'owner' ? '<button class="btn btn-primary btn-sm" onclick="navigate(\'owner-staff\')"><i class="fas fa-user-plus me-1"></i>직원 등록·수정</button>' : ''}
            </div>
            <div class="card-body">
                ${crmStaffCache.length ? `<div class="crm-staff-grid">${crmStaffCache.map(staff=>`
                    <div class="crm-staff-card">
                        <span class="crm-staff-avatar"><i class="fas fa-user"></i></span>
                        <div><strong>${escapeHtml(staff.name)}</strong><small>직원코드 ${escapeHtml(staff.staff_code || '-')}</small></div>
                        ${staff.is_me ? '<span class="badge bg-primary">내 계정</span>' : '<span class="status-dot" title="활성"></span>'}
                    </div>`).join('')}</div>` : '<div class="empty-state compact"><i class="fas fa-users"></i><p>활성 직원이 없습니다.</p></div>'}
            </div>
        </div>`;
    } catch(e) {
        body.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

// ─── Customers ─────────────────────────────────────────────
async function crmRenderCustomers(body){
    body.innerHTML=`
        <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <div class="d-flex gap-2 align-items-center flex-wrap">
                <div class="input-group input-group-sm" style="width:220px"><span class="input-group-text"><i class="fas fa-search"></i></span><input class="form-control" id="crmCustSearch" placeholder="이름·전화 검색"></div>
                <select class="form-select form-select-sm" id="crmCustGrade" style="width:120px"><option value="">전체 등급</option><option>VIP</option><option>GOLD</option><option>SILVER</option><option>BRONZE</option><option>NEW</option></select>
                <input class="form-control form-control-sm" id="crmCustTag" placeholder="태그" style="width:110px">
            </div>
            <button class="btn btn-primary btn-sm" onclick="crmCustomerForm()"><i class="fas fa-user-plus me-1"></i>고객 등록</button>
        </div><div class="card-body p-0" id="crmCustList">${adpayLoadingMarkup()}</div></div>`;
    const load=async()=>{
        const sv=document.getElementById('crmCustSearch').value.trim();
        const gr=document.getElementById('crmCustGrade').value;
        const tg=document.getElementById('crmCustTag').value.trim();
        const list=document.getElementById('crmCustList');
        try{
            let url='/api/crm/customers?'+crmScopeQS();
            if(sv) url+='&search='+encodeURIComponent(sv);
            if(gr) url+='&grade='+gr;
            if(tg) url+='&tag='+encodeURIComponent(tg);
            list.innerHTML=crmCustomerTable(await apiGet(url));
        }catch(e){ list.innerHTML=`<div class="alert alert-danger m-3">${escapeHtml(e.message)}</div>`; }
    };
    document.getElementById('crmCustSearch').addEventListener('input', crmDebounce(load,300));
    document.getElementById('crmCustGrade').addEventListener('change', load);
    document.getElementById('crmCustTag').addEventListener('input', crmDebounce(load,300));
    load();
}
function crmCustomerTable(data){
    if(!data.length) return `<div class="text-center text-muted py-5"><i class="fas fa-user-slash fa-2x mb-2 d-block opacity-50"></i>고객이 없습니다.</div>`;
    const rows=data.map(c=>{
        const gc=CRM_GRADE_COLORS[c.grade]||'#94a3b8';
        const due = c.next_expected_visit ? `<small class="text-muted d-block">예상재방문 ${c.next_expected_visit}</small>`:'';
        return `<tr style="cursor:pointer" onclick="crmCustomerDetail(${c.id})">
            <td><div class="d-flex align-items-center gap-2">
                <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.82rem">${escapeHtml((c.name||'?')[0])}</div>
                <div><div class="fw-bold">${escapeHtml(c.name)}${c.allergy_memo?' <i class="fas fa-triangle-exclamation text-warning" title="알레르기/주의"></i>':''}</div><small class="text-muted">${escapeHtml(c.phone)||'-'}</small></div>
            </div></td>
            <td><span class="badge" style="background:${gc};font-size:.7rem">${escapeHtml(c.grade)}</span></td>
            <td>${crmTagBadges(c.tags,c.auto_tags)}</td>
            <td class="text-center fw-bold">${c.visit_count}회${c.visit_cycle_days?`<small class="text-muted d-block">주기 ${c.visit_cycle_days}일</small>`:''}</td>
            <td class="text-end fw-bold">${formatMoney(c.total_spent)}<small class="text-muted d-block">객단가 ${formatMoney(c.avg_ticket)}</small></td>
            <td class="text-center">${c.points.toLocaleString()}P</td>
            <td><small class="text-muted">${c.last_visit?crmDateOnly(c.last_visit):'방문없음'}</small>${due}</td>
        </tr>`;
    }).join('');
    const cards=data.map(c=>{
        const gc=CRM_GRADE_COLORS[c.grade]||'#94a3b8';
        return `<button class="crm-cust-mobile-card" onclick="crmCustomerDetail(${c.id})">
            <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.92rem;flex-shrink:0">${escapeHtml((c.name||'?')[0])}</div>
            <div style="flex:1;min-width:0">
                <div class="d-flex align-items-center gap-1 flex-wrap">
                    <span class="fw-bold" style="font-size:.88rem">${escapeHtml(c.name)}</span>
                    <span class="badge" style="background:${gc};font-size:.62rem;padding:2px 6px">${escapeHtml(c.grade)}</span>
                    ${c.allergy_memo?'<i class="fas fa-triangle-exclamation text-warning" style="font-size:.68rem" title="알레르기/주의"></i>':''}
                </div>
                <div style="font-size:.74rem;color:#6b7280;margin-top:2px">${escapeHtml(c.phone||'-')} · ${c.visit_count}회 방문 · ${formatMoney(c.total_spent)}</div>
            </div>
            <i class="fas fa-chevron-right" style="color:#c8d3de;font-size:.72rem;flex-shrink:0"></i>
        </button>`;
    }).join('');
    return `<div class="crm-cust-table-wrap"><div class="table-responsive"><table class="table table-hover align-middle mb-0">
        <thead class="table-light"><tr><th>고객</th><th>등급</th><th>태그</th><th class="text-center">방문</th><th class="text-end">누적매출</th><th class="text-center">포인트</th><th>최근/예상</th></tr></thead>
        <tbody>${rows}</tbody></table></div></div>
    <div class="crm-cust-card-list">${cards}</div>`;
}
function crmCustomerForm(existing){
    const c=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">이름 <span class="text-danger">*</span></label><input class="form-control" id="cfName" value="${escapeHtml(c.name)||''}"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="cfPhone" value="${escapeHtml(c.phone)||''}" placeholder="010-0000-0000"></div>
        <div class="col-md-4"><label class="form-label">성별</label><select class="form-select" id="cfGender"><option value="" ${!c.gender?'selected':''}>선택</option><option value="female" ${c.gender==='female'?'selected':''}>여성</option><option value="male" ${c.gender==='male'?'selected':''}>남성</option></select></div>
        <div class="col-md-4"><label class="form-label">생일</label><input class="form-control" id="cfBirth" type="date" value="${c.birthday||''}"></div>
        <div class="col-md-4"><label class="form-label">기념일</label><input class="form-control" id="cfAnniv" type="date" value="${c.anniversary||''}"></div>
        <div class="col-md-6"><label class="form-label">담당 직원</label><select class="form-select" id="cfStaff">${crmStaffOptions(c.assigned_staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">선호 직원</label><select class="form-select" id="cfPrefStaff">${crmStaffOptions(c.preferred_staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">선호 서비스</label><input class="form-control" id="cfPrefSvc" list="cfSvcList" value="${escapeHtml(c.preferred_service)||''}"><datalist id="cfSvcList">${crmServiceCache.map(s=>`<option value="${escapeHtml(s.name)}">`).join('')}</datalist></div>
        <div class="col-md-6"><label class="form-label">사진 URL</label><input class="form-control" id="cfPhoto" value="${escapeHtml(c.photo_url)||''}" placeholder="https://..."></div>
        <div class="col-12"><label class="form-label">태그 <small class="text-muted">(콤마: 단골,VIP)</small></label><input class="form-control" id="cfTags" value="${escapeHtml((c.tags||[]).join(','))}"></div>
        <div class="col-md-6"><label class="form-label text-danger">알레르기/주의사항</label><textarea class="form-control" id="cfAllergy" rows="2">${escapeHtml(c.allergy_memo)||''}</textarea></div>
        <div class="col-md-6"><label class="form-label">모발 상태/이력</label><textarea class="form-control" id="cfHair" rows="2">${escapeHtml(c.hair_memo)||''}</textarea></div>
        <div class="col-12"><label class="form-label">일반 메모</label><textarea class="form-control" id="cfMemo" rows="2">${escapeHtml(c.memo)||''}</textarea></div>
        <div class="col-12"><div id="cfResult"></div></div>
    </div>`;
    const footer=`<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmCustomerSave(${isEdit?c.id:'null'})"><i class="fas fa-save me-1"></i>${isEdit?'수정':'등록'}</button>`;
    crmModal(isEdit?'고객 정보 수정':'고객 등록', body, footer);
}
async function crmCustomerSave(id){
    const name=document.getElementById('cfName').value.trim(); const res=document.getElementById('cfResult');
    if(!name){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">이름은 필수입니다.</div>`; return; }
    const payload={ name,
        phone:document.getElementById('cfPhone').value.trim()||null,
        gender:document.getElementById('cfGender').value||null,
        birthday:document.getElementById('cfBirth').value||null,
        anniversary:document.getElementById('cfAnniv').value||null,
        assigned_staff_id:parseInt(document.getElementById('cfStaff').value)||null,
        preferred_staff_id:parseInt(document.getElementById('cfPrefStaff').value)||null,
        preferred_service:document.getElementById('cfPrefSvc').value.trim()||null,
        photo_url:document.getElementById('cfPhoto').value.trim()||null,
        tags:document.getElementById('cfTags').value.split(',').map(s=>s.trim()).filter(Boolean),
        allergy_memo:document.getElementById('cfAllergy').value.trim()||null,
        hair_memo:document.getElementById('cfHair').value.trim()||null,
        memo:document.getElementById('cfMemo').value.trim()||null,
    };
    try{
        if(id) await apiPut(`/api/crm/customers/${id}`,payload); else await apiPost('/api/crm/customers',payload);
        crmCloseModal(); crmNotify(id?'수정되었습니다.':'고객이 등록되었습니다.','ok'); crmSwitchTab('customers');
    }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
async function crmCustomerDetail(id){
    try{
        const c=await apiGet(`/api/crm/customers/${id}`);
        const tl=await apiGet(`/api/crm/customers/${id}/timeline`);
        const gc=CRM_GRADE_COLORS[c.grade]||'#94a3b8';
        const profileRows=`
            <div class="row g-2 small">
                <div class="col-6"><span class="text-muted">생일</span> ${c.birthday||'-'}</div>
                <div class="col-6"><span class="text-muted">기념일</span> ${c.anniversary||'-'}</div>
                <div class="col-6"><span class="text-muted">담당</span> ${escapeHtml(c.assigned_staff_name)||'-'}</div>
                <div class="col-6"><span class="text-muted">선호</span> ${escapeHtml(c.preferred_staff_name)||'-'} / ${escapeHtml(c.preferred_service)||'-'}</div>
                <div class="col-6"><span class="text-muted">방문주기</span> ${c.visit_cycle_days?c.visit_cycle_days+'일':'-'}</div>
                <div class="col-6"><span class="text-muted">예상 재방문</span> ${c.next_expected_visit||'-'}</div>
            </div>`;
        const timelineHtml=(tl.items||[]).slice(0,40).map(it=>{
            const ic={visit:'fa-scissors',reservation:'fa-calendar-check',point:'fa-coins',message:'fa-comment-dots',coupon:'fa-ticket'}[it.type]||'fa-circle';
            const col={visit:'#16a34a',reservation:'#3b82f6',point:'#f59e0b',message:'#8b5cf6',coupon:'#ec4899'}[it.type]||'#94a3b8';
            let detail='';
            if(it.type==='visit') detail=`${escapeHtml(it.title)} · ${formatMoney(it.amount||0)} ${it.staff_name?'· '+escapeHtml(it.staff_name):''}`;
            else if(it.type==='reservation') detail=`${escapeHtml(it.title)} · ${escapeHtml(it.status_kr)||''}`;
            else if(it.type==='point') detail=`${escapeHtml(it.title)} · ${it.delta>=0?'+':''}${it.delta}P`;
            else if(it.type==='message') detail=`${escapeHtml(it.content||it.title)}`;
            else if(it.type==='coupon') detail=`${escapeHtml(it.title)} · ${escapeHtml(it.status)}`;
            return `<div class="d-flex gap-2 mb-2"><div style="width:26px;height:26px;border-radius:50%;background:${col}1a;color:${col};display:flex;align-items:center;justify-content:center;flex-shrink:0"><i class="fas ${ic}" style="font-size:.7rem"></i></div><div><div style="font-size:.85rem">${detail}</div><small class="text-muted">${formatDate(it.at)}</small></div></div>`;
        }).join('')||`<div class="text-muted text-center py-3">이력 없음</div>`;
        const body=`
            <div class="d-flex align-items-center gap-3 mb-3">
                <div style="width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.3rem;overflow:hidden">${safeUrl(c.photo_url)?`<img src="${safeUrl(c.photo_url)}" style="width:100%;height:100%;object-fit:cover">`:escapeHtml((c.name||'?')[0])}</div>
                <div><div class="d-flex align-items-center gap-2"><span class="fs-5 fw-bold">${escapeHtml(c.name)}</span><span class="badge" style="background:${gc}">${escapeHtml(c.grade)}</span></div><small class="text-muted">${escapeHtml(c.phone)||'-'}</small></div>
            </div>
            <div class="row g-2 mb-3">
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${c.visit_count}</div><small class="text-muted">방문</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(c.total_spent)}</div><small class="text-muted">누적</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(c.avg_ticket)}</div><small class="text-muted">객단가</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${c.points.toLocaleString()}P</div><small class="text-muted">포인트</small></div></div>
            </div>
            <div class="mb-2">${crmTagBadges(c.tags,c.auto_tags)}</div>
            ${c.allergy_memo?`<div class="alert alert-warning py-2 small mb-2"><i class="fas fa-triangle-exclamation me-1"></i><strong>주의:</strong> ${escapeHtml(c.allergy_memo)}</div>`:''}
            ${c.hair_memo?`<div class="alert alert-light border py-2 small mb-2"><i class="fas fa-comment me-1 text-info"></i>${escapeHtml(c.hair_memo)}</div>`:''}
            ${c.memo?`<div class="alert alert-light border py-2 small mb-2"><i class="fas fa-note-sticky me-1 text-warning"></i>${escapeHtml(c.memo)}</div>`:''}
            <div class="card mb-2"><div class="card-body py-2">${profileRows}</div></div>
            <ul class="nav nav-tabs mb-2" role="tablist">
                <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#cdTimeline">통합 타임라인</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#cdVisits">방문 이력</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#cdMessages">메시지</button></li>
            </ul>
            <div class="tab-content">
                <div class="tab-pane fade show active" id="cdTimeline" style="max-height:280px;overflow:auto">${timelineHtml}</div>
                <div class="tab-pane fade" id="cdVisits"><table class="table table-sm align-middle"><thead class="table-light"><tr><th>날짜</th><th>서비스</th><th>담당</th><th class="text-end">금액</th><th></th></tr></thead><tbody>${(c.visits||[]).map(v=>`<tr><td>${crmDateOnly(v.visit_date)}</td><td>${escapeHtml(v.service_name)||'-'}</td><td>${escapeHtml(v.staff_name)||'-'}</td><td class="text-end">${formatMoney(v.amount)}</td><td><button class="btn btn-sm btn-outline-danger border-0" onclick="crmDeleteVisit(${v.id},${id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">방문 이력 없음</td></tr>`}</tbody></table></div>
                <div class="tab-pane fade" id="cdMessages">
                    <div class="fw-bold small mb-1">메시지</div>
                    <table class="table table-sm align-middle"><tbody>${(c.messages||[]).map(m=>`<tr><td>${escapeHtml(m.channel)}</td><td>${escapeHtml(m.content)}</td><td class="text-muted text-nowrap">${crmDateOnly(m.sent_at)}</td></tr>`).join('')||`<tr><td class="text-center text-muted py-2">발송 내역 없음</td></tr>`}</tbody></table>
                </div>
            </div>`;
        const footer=`
            <button type="button" class="btn btn-outline-danger me-auto" onclick="crmDeleteCustomer(${id})"><i class="fas fa-trash"></i></button>
            <button type="button" class="btn btn-outline-secondary" onclick="crmMessageToCustomer(${id},'${escapeHtml((c.name||'').replace(/['"\\]/g,''))}')"><i class="fas fa-comment-dots me-1"></i>메시지</button>
            <button type="button" class="btn btn-outline-secondary" onclick="crmPointForm(${id})"><i class="fas fa-coins me-1"></i>포인트</button>
            <button type="button" class="btn btn-outline-primary" onclick='crmCustomerForm(${JSON.stringify(c).replace(/'/g,"&#39;")})'><i class="fas fa-pen me-1"></i>수정</button>
            <button type="button" class="btn btn-primary" onclick="crmVisitForm(${id})"><i class="fas fa-plus me-1"></i>방문</button>`;
        crmModal('고객 상세', body, footer);
    }catch(e){ crmNotify(e.message,'err'); }
}
async function crmDeleteCustomer(id){
    if(!confirm('이 고객과 모든 이력을 삭제할까요?')) return;
    try{ await apiDelete(`/api/crm/customers/${id}`); crmCloseModal(); crmNotify('삭제되었습니다.','ok'); crmSwitchTab('customers'); }catch(e){ crmNotify(e.message,'err'); }
}
function crmPointForm(id){
    const body=`<div class="row g-3"><div class="col-md-6"><label class="form-label">포인트 변동 <small class="text-muted">(사용은 음수)</small></label><input class="form-control" id="pfDelta" type="number" placeholder="예: 5000 / -3000"></div><div class="col-md-6"><label class="form-label">사유</label><input class="form-control" id="pfReason" placeholder="수기 적립/사용"></div><div class="col-12"><div id="pfResult"></div></div></div>`;
    crmModal('포인트 조정', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmPointSave(${id})">적용</button>`);
}
async function crmPointSave(id){
    const delta=parseInt(document.getElementById('pfDelta').value); const res=document.getElementById('pfResult');
    if(!delta){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">변동 포인트를 입력하세요.</div>`; return; }
    try{ const r=await apiPost(`/api/crm/customers/${id}/points`,{delta,reason:document.getElementById('pfReason').value.trim()||null}); crmCloseModal(); crmNotify(`적용됨 (잔액 ${r.points.toLocaleString()}P)`,'ok'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
function crmVisitForm(customerId){
    const custSelect = customerId? '' : `<div class="col-12"><label class="form-label">고객 <span class="text-danger">*</span></label><select class="form-select" id="crmVisitCustomer"><option value="">고객 선택</option></select></div>`;
    const body=`<div class="row g-3">
        ${custSelect}
        <div class="col-md-6"><label class="form-label">서비스 선택</label>${crmServiceSelect('crmVisitSvcSel')}</div>
        <div class="col-md-6"><label class="form-label">서비스명</label><input class="form-control" id="crmVisitService"></div>
        <div class="col-md-6"><label class="form-label">금액</label><input class="form-control" id="crmVisitAmount" type="number" value="0"></div>
        <div class="col-md-6"><label class="form-label">담당</label><select class="form-select" id="crmVisitStaff">${crmStaffOptions(crmMe.staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">방문일시</label><input class="form-control" id="crmVisitDate" type="datetime-local" value="${crmNowLocal()}"></div>
        <div class="col-md-6"><label class="form-label">메모</label><input class="form-control" id="crmVisitMemo"></div>
        <div class="col-12"><div id="crmVisitResult"></div></div>
    </div>`;
    crmModal('방문/이용 기록', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmVisitSave(${customerId||'null'})"><i class="fas fa-save me-1"></i>기록</button>`);
    if(!customerId) crmLoadCustomerSelect('crmVisitCustomer');
}
async function crmLoadCustomerSelect(selId){
    try{ const data=await apiGet('/api/crm/customers?scope=all'); const sel=document.getElementById(selId); if(sel) sel.innerHTML=`<option value="">고객 선택</option>`+data.map(c=>`<option value="${c.id}">${escapeHtml(c.name)} (${escapeHtml(c.phone)||'-'})</option>`).join(''); }catch(e){}
}
async function crmVisitSave(customerId){
    const res=document.getElementById('crmVisitResult');
    const cid=customerId||parseInt(document.getElementById('crmVisitCustomer').value);
    if(!cid){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">고객을 선택하세요.</div>`; return; }
    const payload={ customer_id:cid, service_name:document.getElementById('crmVisitService').value.trim()||null, amount:parseFloat(document.getElementById('crmVisitAmount').value)||0, staff_id:parseInt(document.getElementById('crmVisitStaff').value)||null, visit_date:document.getElementById('crmVisitDate').value||null, memo:document.getElementById('crmVisitMemo').value.trim()||null };
    try{ const r=await apiPost('/api/crm/visits',payload); crmCloseModal(); crmNotify(`방문 기록됨${r.points_earned?' (+'+r.points_earned+'P)':''}`,'ok'); crmSwitchTab(crmTab==='customers'?'customers':crmTab); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
async function crmDeleteVisit(vid, customerId){
    if(!confirm('이 방문 기록을 삭제할까요?')) return;
    try{ await apiDelete(`/api/crm/visits/${vid}`); crmNotify('삭제되었습니다.','ok'); crmCustomerDetail(customerId); }catch(e){ crmNotify(e.message,'err'); }
}

// ─── Reservations (목록 + 캘린더) ──────────────────────────
async function crmRenderReservations(body){
    if(!crmCalDate){ const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); crmCalDate=d.toISOString().slice(0,10); }
    body.innerHTML=`
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
            <div class="btn-group btn-group-sm">
                <button class="btn ${crmCalView==='day'?'btn-primary':'btn-outline-primary'}" onclick="crmSetCalView('day')">일</button>
                <button class="btn ${crmCalView==='week'?'btn-primary':'btn-outline-primary'}" onclick="crmSetCalView('week')">주</button>
                <button class="btn ${crmCalView==='list'?'btn-primary':'btn-outline-primary'}" onclick="crmSetCalView('list')">목록</button>
            </div>
            <div class="d-flex align-items-center gap-2">
                <button class="btn btn-sm btn-outline-secondary" onclick="crmCalMove(-1)"><i class="fas fa-chevron-left"></i></button>
                <input class="form-control form-control-sm" id="crmCalDate" type="date" value="${crmCalDate}" style="width:160px" onchange="crmCalSetDate(this.value)">
                <button class="btn btn-sm btn-outline-secondary" onclick="crmCalMove(1)"><i class="fas fa-chevron-right"></i></button>
                <button class="btn btn-sm btn-outline-secondary" onclick="crmCalToday()">오늘</button>
                <button class="btn btn-sm btn-primary" onclick="crmReservationForm()"><i class="fas fa-calendar-plus me-1"></i>예약 등록</button>
            </div>
        </div>
        <div id="crmResvBody">${adpayLoadingMarkup()}</div>`;
    crmLoadReservationView();
}
function crmSetCalView(v){ crmCalView=v; crmRenderReservations(document.getElementById('crmTabBody')); }
function crmCalSetDate(v){ crmCalDate=v; crmLoadReservationView(); }
function crmCalToday(){ const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); crmCalDate=d.toISOString().slice(0,10); const inp=document.getElementById('crmCalDate'); if(inp) inp.value=crmCalDate; crmLoadReservationView(); }
function crmCalMove(delta){ const step=crmCalView==='week'?7:1; const d=new Date(crmCalDate+'T00:00'); d.setDate(d.getDate()+step*delta); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); crmCalDate=d.toISOString().slice(0,10); const inp=document.getElementById('crmCalDate'); if(inp) inp.value=crmCalDate; crmLoadReservationView(); }
async function crmLoadReservationView(){
    const box=document.getElementById('crmResvBody'); if(!box) return;
    box.innerHTML = adpayLoadingMarkup();
    try{
        if(crmCalView==='list'){ const data=await apiGet(`/api/crm/reservations?${crmScopeQS()}`); box.innerHTML=crmReservationListTable(data); return; }
        const cal=await apiGet(`/api/crm/reservations/calendar?date=${crmCalDate}&view=${crmCalView}&${crmScopeQS()}`);
        box.innerHTML = crmCalView==='day' ? crmRenderDayCalendar(cal) : crmRenderWeekCalendar(cal);
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}
function crmReservationListTable(data){
    const rows=data.map(r=>`<tr>
        <td><small>${formatDate(r.reserved_at)}</small></td>
        <td class="fw-bold" ${r.customer_id?`style="cursor:pointer" onclick="crmCustomerDetail(${r.customer_id})"`:''}>${escapeHtml(r.customer_name)}</td>
        <td>${escapeHtml(r.service_name)||'-'}</td><td>${escapeHtml(r.staff_name)||'-'}</td><td>${crmResvStatusBadge(r.status,r.status_kr)}</td>
        <td class="text-end">${crmResvActions(r)}</td></tr>`).join('')||`<tr><td colspan="6" class="text-center text-muted py-4">예약이 없습니다.</td></tr>`;
    return `<div class="card data-card"><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>예약일시</th><th>고객</th><th>서비스</th><th>담당</th><th>상태</th><th class="text-end">관리</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
}
function crmResvActions(r){
    let h='';
    if(r.status==='booked') h+=`<button class="btn btn-sm btn-outline-primary border-0" title="확정" onclick="crmResvStatus(${r.id},'confirmed')"><i class="fas fa-check"></i></button>`;
    if(r.status==='booked'||r.status==='confirmed'){
        h+=`<button class="btn btn-sm btn-outline-success border-0" title="방문완료" onclick="crmResvStatus(${r.id},'done')"><i class="fas fa-flag-checkered"></i></button>`;
        h+=`<button class="btn btn-sm btn-outline-danger border-0" title="노쇼" onclick="crmResvStatus(${r.id},'noshow')"><i class="fas fa-user-xmark"></i></button>`;
        h+=`<button class="btn btn-sm btn-outline-secondary border-0" title="취소" onclick="crmResvStatus(${r.id},'cancelled')"><i class="fas fa-ban"></i></button>`;
        h+=`<button class="btn btn-sm btn-outline-info border-0" title="리마인더 발송" onclick="crmResvRemind(${r.id})"><i class="fas fa-paper-plane"></i></button>`;
    }
    h+=`<button class="btn btn-sm btn-outline-danger border-0" title="삭제" onclick="crmResvDelete(${r.id})"><i class="fas fa-trash"></i></button>`;
    return h;
}
function crmRenderDayCalendar(cal){
    const H=46, startH=9, endH=22; const hours=[];
    for(let h=startH;h<=endH;h++) hours.push(h);
    const staff=cal.staff.length?cal.staff:[{id:0,name:'전체'}];
    const colW=Math.max(140, Math.floor(760/staff.length));
    let header=`<div style="display:flex;border-bottom:2px solid #eef2ff"><div style="width:50px;flex-shrink:0"></div>${staff.map(s=>`<div style="flex:1;min-width:${colW}px;text-align:center;font-weight:700;padding:6px;color:#667eea">${escapeHtml(s.name)}</div>`).join('')}</div>`;
    let gridRows=hours.map(h=>`<div style="display:flex;height:${H}px;border-bottom:1px solid #f3f4f6"><div style="width:50px;flex-shrink:0;font-size:.72rem;color:#9ca3af;text-align:right;padding-right:6px">${h}:00</div>${staff.map(()=>`<div style="flex:1;min-width:${colW}px;border-left:1px solid #f8fafc"></div>`).join('')}</div>`).join('');
    let events=cal.events.map(ev=>{
        const dt=new Date(ev.reserved_at.replace(' ','T'));
        const sIdx=staff.findIndex(s=>s.id===ev.staff_id); const idx=sIdx<0?0:sIdx;
        const top=((dt.getHours()-startH)+dt.getMinutes()/60)*H;
        const hgt=Math.max(24,(ev.duration_min/60)*H-3);
        const col=CRM_RESV_COLORS[ev.status]||'#667eea';
        const left=50 + idx*colW;
        return `<div onclick="crmReservationDetail(${ev.id})" style="position:absolute;top:${top+34}px;left:${left+2}px;width:${colW-6}px;height:${hgt}px;background:${col}1a;border-left:3px solid ${col};border-radius:6px;padding:3px 6px;font-size:.72rem;overflow:hidden;cursor:pointer">
            <div class="fw-bold" style="color:${col}">${dt.getHours()}:${String(dt.getMinutes()).padStart(2,'0')} ${escapeHtml(ev.customer_name)}</div>
            <div class="text-muted text-truncate">${escapeHtml(ev.service_name)||''}</div></div>`;
    }).join('');
    return `<div class="card data-card"><div class="card-body" style="position:relative;overflow-x:auto"><div style="position:relative;min-width:${50+staff.length*colW}px">${header}${gridRows}${events}</div></div></div>`;
}
function crmRenderWeekCalendar(cal){
    const start=new Date(cal.start+'T00:00'); const days=[];
    const wd=['월','화','수','목','금','토','일'];
    for(let i=0;i<7;i++){ const d=new Date(start); d.setDate(d.getDate()+i); days.push(d); }
    const byDay={};
    cal.events.forEach(ev=>{ const k=ev.reserved_at.slice(0,10); (byDay[k]=byDay[k]||[]).push(ev); });
    const cols=days.map((d,i)=>{
        const k=d.toISOString().slice(0,10); const evs=(byDay[k]||[]).sort((a,b)=>a.reserved_at.localeCompare(b.reserved_at));
        const today = k===crmCalDate;
        return `<div style="flex:1;min-width:130px;border-left:1px solid #f3f4f6">
            <div style="text-align:center;padding:6px;font-weight:700;${today?'background:#eef2ff;color:#667eea':'color:#6b7280'};border-radius:8px 8px 0 0">${wd[i]} ${d.getMonth()+1}/${d.getDate()}</div>
            <div style="padding:4px;min-height:80px">${evs.map(ev=>{const col=CRM_RESV_COLORS[ev.status]||'#667eea'; const tt=ev.reserved_at.slice(11,16); return `<div onclick="crmReservationDetail(${ev.id})" style="background:${col}1a;border-left:3px solid ${col};border-radius:6px;padding:3px 5px;margin-bottom:4px;font-size:.72rem;cursor:pointer"><div class="fw-bold" style="color:${col}">${tt} ${escapeHtml(ev.customer_name)}</div><div class="text-muted text-truncate">${escapeHtml(ev.staff_name)||''} ${escapeHtml(ev.service_name)||''}</div></div>`;}).join('')||'<div class="text-muted text-center small py-2">-</div>'}</div>
        </div>`;
    }).join('');
    return `<div class="card data-card"><div class="card-body" style="overflow-x:auto"><div style="display:flex;min-width:910px">${cols}</div></div></div>`;
}
async function crmReservationDetail(id){
    try{
        const list=await apiGet(`/api/crm/reservations?${crmScopeQS()}`);
        const r=list.find(x=>x.id===id); if(!r){ crmNotify('예약을 찾을 수 없습니다','err'); return; }
        const body=`<div class="row g-2 small mb-3">
            <div class="col-6"><span class="text-muted">고객</span><div class="fw-bold">${escapeHtml(r.customer_name)}</div></div>
            <div class="col-6"><span class="text-muted">연락처</span><div>${escapeHtml(r.phone)||'-'}</div></div>
            <div class="col-6"><span class="text-muted">예약일시</span><div class="fw-bold">${formatDate(r.reserved_at)}</div></div>
            <div class="col-6"><span class="text-muted">소요</span><div>${r.duration_min||60}분</div></div>
            <div class="col-6"><span class="text-muted">서비스</span><div>${escapeHtml(r.service_name)||'-'}</div></div>
            <div class="col-6"><span class="text-muted">담당</span><div>${escapeHtml(r.staff_name)||'-'}</div></div>
            <div class="col-12"><span class="text-muted">상태</span> ${crmResvStatusBadge(r.status,r.status_kr)}</div>
            ${r.memo?`<div class="col-12"><span class="text-muted">메모</span><div>${escapeHtml(r.memo)}</div></div>`:''}
        </div><div class="d-flex flex-wrap gap-1">${crmResvActions(r)}</div>`;
        crmModal('예약 상세', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>`);
    }catch(e){ crmNotify(e.message,'err'); }
}
async function crmResvStatus(id, status){
    try{ await apiPut(`/api/crm/reservations/${id}`,{status}); crmNotify('상태가 변경되었습니다.','ok'); crmCloseModal(); crmLoadReservationView(); }catch(e){ crmNotify(e.message,'err'); }
}
async function crmResvDelete(id){
    if(!confirm('이 예약을 삭제할까요?')) return;
    try{ await apiDelete(`/api/crm/reservations/${id}`); crmNotify('삭제되었습니다.','ok'); crmCloseModal(); crmLoadReservationView(); }catch(e){ crmNotify(e.message,'err'); }
}
async function crmResvRemind(id){
    try{ const r=await apiPost(`/api/crm/reservations/${id}/remind`,{}); crmNotify('리마인더 발송(목업) 완료','ok'); }catch(e){ crmNotify(e.message,'err'); }
}
function crmReservationForm(){
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">회원 선택</label><select class="form-select" id="rfCustomer" onchange="crmResvCustChange()"><option value="">비회원(직접입력)</option></select></div>
        <div class="col-md-6"><label class="form-label">고객명 <span class="text-danger">*</span></label><input class="form-control" id="rfName"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="rfPhone"></div>
        <div class="col-md-6"><label class="form-label">예약일시 <span class="text-danger">*</span></label><input class="form-control" id="rfDate" type="datetime-local" value="${crmCalDate?crmCalDate+'T10:00':crmNowLocal()}"></div>
        <div class="col-md-6"><label class="form-label">서비스</label>${crmServiceSelect('rfSvcSel')}<input class="form-control mt-1" id="rfService" placeholder="서비스명"></div>
        <div class="col-md-3"><label class="form-label">소요(분)</label><input class="form-control" id="rfDur" type="number" value="60"></div>
        <div class="col-md-3"><label class="form-label">담당</label><select class="form-select" id="rfStaff">${crmStaffOptions(crmMe.staff_id)}</select></div>
        <div class="col-12"><label class="form-label">메모</label><input class="form-control" id="rfMemo"></div>
        <div class="col-12"><div id="rfResult"></div></div>
    </div>`;
    crmModal('예약 등록', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmReservationSave(false)"><i class="fas fa-save me-1"></i>예약 등록</button>`);
    crmLoadCustomerSelect('rfCustomer');
}
function crmResvCustChange(){
    const sel=document.getElementById('rfCustomer'); const opt=sel.options[sel.selectedIndex];
    if(sel.value){ const m=opt.textContent.match(/^(.*) \((.*)\)$/); if(m){ document.getElementById('rfName').value=m[1]; document.getElementById('rfPhone').value=m[2]==='-'?'':m[2]; } }
}
async function crmReservationSave(force){
    const res=document.getElementById('rfResult');
    const name=document.getElementById('rfName').value.trim(); const date=document.getElementById('rfDate').value;
    if(!name||!date){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">고객명과 예약일시는 필수입니다.</div>`; return; }
    const payload={ customer_id:parseInt(document.getElementById('rfCustomer').value)||null, customer_name:name, phone:document.getElementById('rfPhone').value.trim()||null, reserved_at:date, service_name:document.getElementById('rfService').value.trim()||null, duration_min:parseInt(document.getElementById('rfDur').value)||60, staff_id:parseInt(document.getElementById('rfStaff').value)||null, memo:document.getElementById('rfMemo').value.trim()||null, force:!!force };
    try{ await apiPost('/api/crm/reservations',payload); crmCloseModal(); crmNotify('예약이 등록되었습니다.','ok'); crmLoadReservationView(); }
    catch(e){
        if((e.message||'').includes('겹칩')){ if(confirm(e.message+'\n\n그래도 등록하시겠습니까?')){ crmReservationSave(true); return; } res.innerHTML=`<div class="alert alert-warning py-2 mb-0">${escapeHtml(e.message)}</div>`; }
        else res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`;
    }
}

// ─── Analytics ─────────────────────────────────────────────
function crmAnalyticsMoneyLabel(value) {
    const amount = Number(value) || 0;
    if (amount === 0) return '0원';
    if (Math.abs(amount) >= 100000000) {
        const eok = amount / 100000000;
        return `${Number.isInteger(eok) ? eok : eok.toFixed(1)}억원`;
    }
    if (Math.abs(amount) >= 10000) {
        const man = amount / 10000;
        return `${Number.isInteger(man) ? man : man.toFixed(1)}만원`;
    }
    if (Math.abs(amount) >= 1000) return `${Math.round(amount / 1000)}천원`;
    return `${amount.toLocaleString('ko-KR')}원`;
}

function crmAnalyticsChartOptions({ xTitle, yTitle, valueType = 'money' }) {
    const isMoney = valueType === 'money';
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
            legend: { display: false },
            tooltip: {
                displayColors: false,
                backgroundColor: 'rgba(15, 36, 62, .94)',
                padding: 12,
                titleFont: { size: 13, weight: '700' },
                bodyFont: { size: 13, weight: '600' },
                callbacks: {
                    label: context => isMoney
                        ? ` 매출액: ${formatMoney(Number(context.raw) || 0)}`
                        : ` 방문 건수: ${(Number(context.raw) || 0).toLocaleString('ko-KR')}건`
                }
            }
        },
        scales: {
            x: {
                title: { display: true, text: xTitle, color: '#52677a', font: { size: 12, weight: '700' } },
                ticks: { color: '#52677a', font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
                grid: { display: false }
            },
            y: {
                beginAtZero: true,
                title: { display: true, text: yTitle, color: '#52677a', font: { size: 12, weight: '700' } },
                ticks: {
                    color: '#52677a',
                    font: { size: 11, weight: '600' },
                    maxTicksLimit: 6,
                    precision: 0,
                    callback: value => isMoney ? crmAnalyticsMoneyLabel(value) : `${value}건`
                },
                grid: { color: 'rgba(113, 139, 163, .18)', drawTicks: false },
                border: { display: false }
            }
        }
    };
}

async function crmRenderAnalytics(body){
    body.innerHTML=`
        <div class="d-flex justify-content-end mb-3"><select class="form-select form-select-sm" id="crmAnRange" style="width:140px"><option value="week">이번주</option><option value="month" selected>이번달</option><option value="year">올해</option><option value="all">전체</option></select></div>
        <div id="crmAnBody">${adpayLoadingMarkup()}</div>`;
    const load=async()=>{
        crmDestroyCharts();
        const range=document.getElementById('crmAnRange').value; const box=document.getElementById('crmAnBody');
        try{
            const a=await apiGet(`/api/crm/stats/analytics?range=${range}&${crmScopeQS()}`);
            const kpi=(label,val,sub)=>`<div class="col-6 col-lg-3"><div class="card data-card h-100"><div class="card-body py-3 text-center"><div class="fs-4 fw-bold">${val}</div><small class="text-muted">${label}</small>${sub?`<div><small class="text-muted">${sub}</small></div>`:''}</div></div></div>`;
            const svcRows=(a.by_service||[]).slice(0,8).map(x=>`<tr><td class="fw-bold">${escapeHtml(x.name)}</td><td class="text-end">${x.count}건</td><td class="text-end">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="3" class="text-center text-muted py-3">데이터 없음</td></tr>`;
            const staffRows=(a.by_staff||[]).map(x=>`<tr><td class="fw-bold">${escapeHtml(x.staff_name)}</td><td class="text-end">${x.count}건</td><td class="text-end">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="3" class="text-center text-muted py-3">데이터 없음</td></tr>`;
            box.innerHTML=`
                <div class="row g-3 mb-3">
                    ${kpi('총 매출',formatMoney(a.total_revenue),a.total_visits+'건')}
                    ${kpi('객단가',formatMoney(a.avg_ticket))}
                    ${kpi('신규/재방문',a.new_count+' / '+a.revisit_count,'신규비율 '+a.new_ratio+'%')}
                    ${kpi('방문 수',a.total_visits+'건')}
                </div>
                <div class="row g-3">
                    <div class="col-lg-8"><div class="card data-card crm-analytics-chart-card"><div class="card-header crm-analytics-chart-head"><div><h6 class="mb-1">일별 매출 추이</h6><small>날짜마다 매출이 어떻게 달라졌는지 보여드려요.</small></div><span>세로 기준 · 매출액</span></div><div class="card-body"><div class="crm-analytics-chart crm-analytics-chart-wide"><canvas id="anDaily" aria-label="날짜별 매출액 그래프"></canvas></div><p class="crm-analytics-chart-help"><i class="fas fa-circle-info"></i>왼쪽 숫자는 매출액입니다. 선 위에 마우스를 올리면 정확한 금액을 볼 수 있어요.</p></div></div></div>
                    <div class="col-lg-4"><div class="card data-card"><div class="card-header"><h6 class="mb-0">신규 vs 재방문</h6></div><div class="card-body"><canvas id="anNew" height="110"></canvas></div></div></div>
                    <div class="col-lg-6"><div class="card data-card crm-analytics-chart-card"><div class="card-header crm-analytics-chart-head"><div><h6 class="mb-1">요일별 매출</h6><small>어떤 요일에 매출이 높은지 비교해요.</small></div><span>세로 기준 · 매출액</span></div><div class="card-body"><div class="crm-analytics-chart"><canvas id="anWeekday" aria-label="요일별 매출액 그래프"></canvas></div><p class="crm-analytics-chart-help"><i class="fas fa-circle-info"></i>막대가 높을수록 해당 요일의 매출이 많다는 뜻입니다.</p></div></div></div>
                    <div class="col-lg-6"><div class="card data-card crm-analytics-chart-card"><div class="card-header crm-analytics-chart-head"><div><h6 class="mb-1">시간대별 방문</h6><small>고객 방문이 몰리는 시간을 확인해요.</small></div><span>세로 기준 · 방문 건수</span></div><div class="card-body"><div class="crm-analytics-chart"><canvas id="anHour" aria-label="시간대별 방문 건수 그래프"></canvas></div><p class="crm-analytics-chart-help"><i class="fas fa-circle-info"></i>막대가 높을수록 해당 시간에 방문 고객이 많다는 뜻입니다.</p></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">서비스별 매출</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>서비스</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${svcRows}</tbody></table></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">직원별 매출</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>직원</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${staffRows}</tbody></table></div></div></div>
                </div>`;
            if(window.Chart){
                const dc=document.getElementById('anDaily'); if(dc) crmChartRefs.push(new Chart(dc,{type:'line',data:{labels:(a.daily||[]).map(d=>d.date.slice(5)),datasets:[{data:(a.daily||[]).map(d=>d.revenue),borderColor:'#0f6cbd',backgroundColor:'rgba(14,165,233,.12)',pointBackgroundColor:'#fff',pointBorderColor:'#0f6cbd',pointBorderWidth:2,pointRadius:3,pointHoverRadius:6,borderWidth:3,fill:true,tension:.3}]},options:crmAnalyticsChartOptions({xTitle:'결제 날짜',yTitle:'매출액 (원)'})}));
                const nc=document.getElementById('anNew'); if(nc) crmChartRefs.push(new Chart(nc,{type:'doughnut',data:{labels:['신규','재방문'],datasets:[{data:[a.new_count,a.revisit_count],backgroundColor:['#10b981','#667eea']}]},options:{plugins:{legend:{position:'bottom'}}}}));
                const wc=document.getElementById('anWeekday'); if(wc) crmChartRefs.push(new Chart(wc,{type:'bar',data:{labels:(a.by_weekday||[]).map(x=>x.label),datasets:[{data:(a.by_weekday||[]).map(x=>x.revenue),backgroundColor:'#0ea5e9',hoverBackgroundColor:'#0f6cbd',borderRadius:7,borderSkipped:false}]},options:crmAnalyticsChartOptions({xTitle:'요일',yTitle:'매출액 (원)'})}));
                const hc=document.getElementById('anHour'); if(hc) crmChartRefs.push(new Chart(hc,{type:'bar',data:{labels:(a.by_hour||[]).map(x=>x.hour+'시'),datasets:[{data:(a.by_hour||[]).map(x=>x.count),backgroundColor:'#2c5f8a',hoverBackgroundColor:'#0f6cbd',borderRadius:7,borderSkipped:false}]},options:crmAnalyticsChartOptions({xTitle:'방문 시간',yTitle:'방문 건수 (건)',valueType:'count'})}));
            }
        }catch(e){ box.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
    };
    document.getElementById('crmAnRange').addEventListener('change', load);
    load();
}

// ─── Marketing / Retention ─────────────────────────────────
async function crmRenderMarketing(body){
    body.innerHTML=`
        <ul class="nav nav-pills mb-3" id="mkPills">
            <li class="nav-item"><button class="nav-link active" onclick="crmMkTab(this,'revisit')">재방문 대상</button></li>
            <li class="nav-item"><button class="nav-link" onclick="crmMkTab(this,'birthday')">생일·기념일</button></li>
            <li class="nav-item"><button class="nav-link" onclick="crmMkTab(this,'coupons')">쿠폰</button></li>
        </ul>
        <div id="crmMkBody">${adpayLoadingMarkup()}</div>`;
    crmMkRender('revisit');
}
function crmMkTab(el,tab){ document.querySelectorAll('#mkPills .nav-link').forEach(x=>x.classList.remove('active')); el.classList.add('active'); crmMkRender(tab); }
async function crmMkRender(tab){
    const box=document.getElementById('crmMkBody'); box.innerHTML = adpayLoadingMarkup();
    try{
        if(tab==='revisit'){
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><div class="d-flex align-items-center gap-2"><span class="small text-muted">미방문 기준</span><select class="form-select form-select-sm" id="mkRevDays" style="width:120px"><option value="30">30일+</option><option value="60" selected>60일+</option><option value="90">90일+</option></select></div><button class="btn btn-sm btn-primary" onclick="crmSendCampaign('dormant')"><i class="fas fa-paper-plane me-1"></i>휴면 캠페인 발송</button></div><div class="card-body p-0" id="mkRevList"></div></div>`;
            const load=async()=>{ const days=document.getElementById('mkRevDays').value; const d=await apiGet(`/api/crm/revisit?days=${days}&${crmScopeQS()}`); document.getElementById('mkRevList').innerHTML=crmRevisitTable(d); };
            document.getElementById('mkRevDays').addEventListener('change', load); load();
        } else if(tab==='birthday'){
            const d=await apiGet('/api/crm/birthdays');
            const tbl=(arr,label)=>`<div class="card data-card mb-3"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">${label} (${arr.length}명)</h6>${arr.length?`<button class="btn btn-sm btn-primary" onclick="crmSendCampaign('birthday')"><i class="fas fa-cake-candles me-1"></i>축하 메시지</button>`:''}</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm table-hover align-middle mb-0"><thead class="table-light"><tr><th>일</th><th>고객</th><th>연락처</th><th>등급</th><th class="text-center">방문</th></tr></thead><tbody>${arr.map(c=>`<tr style="cursor:pointer" onclick="crmCustomerDetail(${c.id})"><td class="fw-bold">${c.event_day}일</td><td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.phone)||'-'}</td><td><span class="badge" style="background:${CRM_GRADE_COLORS[c.grade]}">${c.grade}</span></td><td class="text-center">${c.visit_count}회</td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">대상 없음</td></tr>`}</tbody></table></div></div></div>`;
            box.innerHTML=`<div class="alert alert-info border-0 small"><i class="fas fa-info-circle me-1"></i>이번 달 생일/기념일 고객입니다. 축하 메시지·쿠폰 발송 대상으로 활용하세요.</div>${tbl(d.birthdays,'🎂 이달 생일')}${tbl(d.anniversaries,'💝 이달 기념일')}`;
        } else if(tab==='coupons'){
            const d=await apiGet('/api/crm/coupons');
            const rows=d.map(cp=>`<tr><td class="fw-bold">${escapeHtml(cp.name)}</td><td>${escapeHtml(cp.customer_name)}</td><td>${cp.discount_type==='percent'?cp.value+'%':formatMoney(cp.value)}</td><td>${crmCouponStatusBadge(cp.status)}</td><td class="text-muted">${cp.expires_at||'-'}</td><td class="text-end">${cp.status==='issued'?`<button class="btn btn-sm btn-outline-success border-0" title="사용처리" onclick="crmCouponUse(${cp.id})"><i class="fas fa-check"></i></button>`:''}<button class="btn btn-sm btn-outline-danger border-0" onclick="crmCouponDelete(${cp.id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="6" class="text-center text-muted py-3">발급된 쿠폰이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">쿠폰 발급 현황</h6><div class="d-flex gap-2"><button class="btn btn-sm btn-outline-primary" onclick="crmCouponBulkForm()"><i class="fas fa-layer-group me-1"></i>세그먼트 일괄발급</button><button class="btn btn-sm btn-primary" onclick="crmCouponForm()"><i class="fas fa-plus me-1"></i>쿠폰 발급</button></div></div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>쿠폰명</th><th>고객</th><th>할인</th><th>상태</th><th>만료</th><th class="text-end">관리</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
        }
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}
function crmRevisitTable(d){
    const rows=(d.customers||[]).map(c=>`<tr><td class="fw-bold" style="cursor:pointer" onclick="crmCustomerDetail(${c.id})">${escapeHtml(c.name)}</td><td>${escapeHtml(c.phone)||'-'}</td><td><span class="badge" style="background:${CRM_GRADE_COLORS[c.grade]}">${c.grade}</span></td><td class="text-center">${c.visit_count}회</td><td class="text-center"><span class="badge bg-danger">${c.days_since_visit}일 전</span></td><td>${escapeHtml(c.assigned_staff_name)||'-'}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary border-0" onclick="crmMessageToCustomer(${c.id},'${escapeHtml((c.name||'').replace(/['"\\]/g,''))}')"><i class="fas fa-comment-dots"></i></button></td></tr>`).join('')||`<tr><td colspan="7" class="text-center text-muted py-3">대상 고객이 없습니다.</td></tr>`;
    return `<div class="alert alert-warning border-0 rounded-0 mb-0 small"><i class="fas fa-circle-info me-1"></i>마지막 방문 후 <strong>${d.days}일</strong> 이상 경과한 고객 <strong>${d.count}명</strong></div><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>고객</th><th>연락처</th><th>등급</th><th class="text-center">방문</th><th class="text-center">미방문</th><th>담당</th><th class="text-end">액션</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function crmCouponStatusBadge(s){ const c={issued:'#3b82f6',used:'#16a34a',expired:'#94a3b8'}[s]||'#94a3b8'; const kr={issued:'발급',used:'사용',expired:'만료'}[s]||s; return `<span class="badge" style="background:${c}1a;color:${c};border:1px solid ${c}55">${kr}</span>`; }
function crmCouponForm(customerId){
    const body=`<div class="row g-3">
        ${customerId?`<input type="hidden" id="cpCust" value="${customerId}">`:`<div class="col-12"><label class="form-label">고객 <small class="text-muted">(비우면 공통)</small></label><select class="form-select" id="cpCust"><option value="">공통 쿠폰</option></select></div>`}
        <div class="col-md-6"><label class="form-label">쿠폰명 <span class="text-danger">*</span></label><input class="form-control" id="cpName" placeholder="예: 재방문 1만원 할인"></div>
        <div class="col-md-3"><label class="form-label">할인유형</label><select class="form-select" id="cpType"><option value="amount">금액</option><option value="percent">%</option></select></div>
        <div class="col-md-3"><label class="form-label">값</label><input class="form-control" id="cpValue" type="number" value="10000"></div>
        <div class="col-md-6"><label class="form-label">만료일</label><input class="form-control" id="cpExp" type="date"></div>
        <div class="col-12"><div id="cpResult"></div></div>
    </div>`;
    crmModal('쿠폰 발급', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmCouponSave()">발급</button>`);
    if(!customerId) crmLoadCustomerSelect('cpCust');
}
async function crmCouponSave(){
    const res=document.getElementById('cpResult'); const name=document.getElementById('cpName').value.trim();
    if(!name){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">쿠폰명은 필수입니다.</div>`; return; }
    const payload={ customer_id:parseInt(document.getElementById('cpCust').value)||null, name, discount_type:document.getElementById('cpType').value, value:parseInt(document.getElementById('cpValue').value)||0, expires_at:document.getElementById('cpExp').value||null };
    try{ await apiPost('/api/crm/coupons',payload); crmCloseModal(); crmNotify('쿠폰이 발급되었습니다.','ok'); if(crmTab==='marketing') crmMkRender('coupons'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
function crmCouponBulkForm(){
    const body=`<div class="row g-3">
        <div class="col-12"><label class="form-label">대상 세그먼트</label><select class="form-select" id="cbSeg"><option value="dormant">휴면 고객(60일+)</option><option value="vip">VIP·GOLD 고객</option><option value="birthday">이달 생일 고객</option><option value="all">전체 고객</option></select></div>
        <div class="col-md-6"><label class="form-label">쿠폰명 <span class="text-danger">*</span></label><input class="form-control" id="cbName"></div>
        <div class="col-md-3"><label class="form-label">할인유형</label><select class="form-select" id="cbType"><option value="amount">금액</option><option value="percent">%</option></select></div>
        <div class="col-md-3"><label class="form-label">값</label><input class="form-control" id="cbValue" type="number" value="10000"></div>
        <div class="col-md-6"><label class="form-label">만료일</label><input class="form-control" id="cbExp" type="date"></div>
        <div class="col-12"><div id="cbResult"></div></div>
    </div>`;
    crmModal('세그먼트 일괄 쿠폰 발급', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmCouponBulkSave()">일괄 발급</button>`);
}
async function crmCouponBulkSave(){
    const res=document.getElementById('cbResult'); const name=document.getElementById('cbName').value.trim();
    if(!name){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">쿠폰명은 필수입니다.</div>`; return; }
    const payload={ segment:document.getElementById('cbSeg').value, name, discount_type:document.getElementById('cbType').value, value:parseInt(document.getElementById('cbValue').value)||0, expires_at:document.getElementById('cbExp').value||null };
    try{ const r=await apiPost('/api/crm/coupons/bulk',payload); crmCloseModal(); crmNotify(`${r.issued}명에게 쿠폰 발급 완료`,'ok'); crmMkRender('coupons'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
async function crmCouponUse(id){ try{ await apiPut(`/api/crm/coupons/${id}?status=used`,{}); crmNotify('사용 처리되었습니다.','ok'); crmMkRender('coupons'); }catch(e){ crmNotify(e.message,'err'); } }
async function crmCouponDelete(id){ if(!confirm('쿠폰을 삭제할까요?')) return; try{ await apiDelete(`/api/crm/coupons/${id}`); crmNotify('삭제되었습니다.','ok'); crmMkRender('coupons'); }catch(e){ crmNotify(e.message,'err'); } }
async function crmSendCampaign(segment){
    const tpls=await apiGet('/api/crm/message-templates');
    const cat = segment==='dormant'?'dormant':(segment==='birthday'?'birthday':null);
    const def = tpls.find(t=>t.category===cat) || tpls[0];
    crmMessageForm({segment, template_id:def?def.id:null, templates:tpls, title:(segment==='dormant'?'휴면 캠페인':'생일 축하')+' 발송'});
}

// ─── Messages ──────────────────────────────────────────────
async function crmRenderMessages(body){
    body.innerHTML=`
        <ul class="nav nav-pills mb-3" id="msgPills">
            <li class="nav-item"><button class="nav-link active" onclick="crmMsgTab(this,'send')">발송</button></li>
            <li class="nav-item"><button class="nav-link" onclick="crmMsgTab(this,'templates')">템플릿</button></li>
            <li class="nav-item"><button class="nav-link" onclick="crmMsgTab(this,'log')">발송 내역</button></li>
        </ul>
        <div id="crmMsgBody"></div>`;
    crmMsgRender('send');
}
function crmMsgTab(el,tab){ document.querySelectorAll('#msgPills .nav-link').forEach(x=>x.classList.remove('active')); el.classList.add('active'); crmMsgRender(tab); }
async function crmMsgRender(tab){
    const box=document.getElementById('crmMsgBody'); box.innerHTML = adpayLoadingMarkup();
    try{
        if(tab==='send'){
            box.innerHTML=`<div class="card data-card"><div class="card-body text-center py-5">
                <i class="fas fa-paper-plane fa-2x text-primary mb-3"></i>
                <h6>세그먼트 단체 발송</h6><p class="text-muted small">대상 세그먼트와 템플릿을 선택해 단체 메시지를 발송합니다. (목업 발송 — 실제 문자 미발송, 내역만 기록)</p>
                <button class="btn btn-primary" onclick="crmMessageForm({})"><i class="fas fa-comment-dots me-1"></i>메시지 작성</button>
                <div class="d-flex justify-content-center gap-2 mt-3 flex-wrap">
                    <button class="btn btn-outline-secondary btn-sm" onclick="crmSendCampaign('dormant')">휴면 캠페인</button>
                    <button class="btn btn-outline-secondary btn-sm" onclick="crmSendCampaign('birthday')">생일 축하</button>
                </div></div></div>`;
        } else if(tab==='templates'){
            const tpls=await apiGet('/api/crm/message-templates');
            const rows=tpls.map(t=>`<tr><td class="fw-bold">${escapeHtml(t.name)}</td><td><span class="badge bg-secondary">${escapeHtml(t.channel)}</span></td><td>${escapeHtml(t.category)||'-'}</td><td class="text-muted small">${escapeHtml(t.body)}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary border-0" onclick='crmTemplateForm(${JSON.stringify(t).replace(/'/g,"&#39;")})'><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-outline-danger border-0" onclick="crmTemplateDelete(${t.id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">템플릿이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">메시지 템플릿</h6><button class="btn btn-sm btn-primary" onclick="crmTemplateForm()"><i class="fas fa-plus me-1"></i>템플릿 추가</button></div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>이름</th><th>채널</th><th>분류</th><th>내용</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div><div class="card-footer small text-muted">치환변수: {고객명} {매장명} {포인트}</div></div>`;
        } else if(tab==='log'){
            const logs=await apiGet('/api/crm/messages');
            const rows=logs.map(m=>`<tr><td><small>${formatDate(m.sent_at)}</small></td><td>${escapeHtml(m.customer_name)}</td><td><span class="badge bg-secondary">${m.channel}</span></td><td class="small">${escapeHtml(m.content)}</td><td><span class="badge bg-light text-dark">${escapeHtml(m.campaign)||'-'}</span></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">발송 내역이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>발송시각</th><th>고객</th><th>채널</th><th>내용</th><th>캠페인</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
        }
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}
async function crmMessageForm(opts){
    opts=opts||{};
    const tpls=opts.templates||await apiGet('/api/crm/message-templates');
    const tplOpts=`<option value="">직접 입력</option>`+tpls.map(t=>`<option value="${t.id}" ${opts.template_id===t.id?'selected':''} data-body="${escapeHtml(t.body||'')}" data-ch="${escapeHtml(t.channel)}">${escapeHtml(t.name)}</option>`).join('');
    const segSel = opts.customer_id ? `<input type="hidden" id="smCust" value="${opts.customer_id}">` :
        `<div class="col-12"><label class="form-label">대상 세그먼트</label><select class="form-select" id="smSeg"><option value="all" ${opts.segment==='all'?'selected':''}>전체 고객</option><option value="dormant" ${opts.segment==='dormant'?'selected':''}>휴면 고객</option><option value="birthday" ${opts.segment==='birthday'?'selected':''}>이달 생일</option><option value="vip" ${opts.segment==='vip'?'selected':''}>VIP·GOLD</option></select></div>`;
    const body=`<div class="row g-3">
        ${segSel}
        <div class="col-md-6"><label class="form-label">템플릿</label><select class="form-select" id="smTpl" onchange="crmMsgTplChange()">${tplOpts}</select></div>
        <div class="col-md-6"><label class="form-label">채널</label><select class="form-select" id="smChannel"><option value="sms">SMS</option><option value="alimtalk">알림톡</option></select></div>
        <div class="col-12"><label class="form-label">내용 <small class="text-muted">({고객명} {매장명} {포인트})</small></label><textarea class="form-control" id="smBody" rows="3"></textarea></div>
        <div class="col-12"><div class="alert alert-info py-2 small mb-0"><i class="fas fa-info-circle me-1"></i>목업 발송입니다. 실제 문자는 발송되지 않고 발송 내역만 기록됩니다.</div></div>
        <div class="col-12"><div id="smResult"></div></div>
    </div>`;
    crmModal(opts.title||'메시지 발송', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmMessageSend(${opts.customer_id||'null'})"><i class="fas fa-paper-plane me-1"></i>발송</button>`);
    crmMsgTplChange();
}
function crmMsgTplChange(){
    const sel=document.getElementById('smTpl'); if(!sel) return; const opt=sel.options[sel.selectedIndex];
    if(sel.value){ const b=opt.getAttribute('data-body'); const ch=opt.getAttribute('data-ch'); if(b) document.getElementById('smBody').value=b.replace(/&quot;/g,'"'); if(ch) document.getElementById('smChannel').value=ch; }
}
async function crmMessageSend(customerId){
    const res=document.getElementById('smResult');
    const tplId=parseInt(document.getElementById('smTpl').value)||null;
    const content=document.getElementById('smBody').value.trim();
    const channel=document.getElementById('smChannel').value;
    if(!tplId && !content){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">내용을 입력하세요.</div>`; return; }
    const payload={ channel, template_id:tplId, content:content||null };
    if(customerId) payload.customer_ids=[customerId];
    else payload.segment=document.getElementById('smSeg').value;
    try{ const r=await apiPost('/api/crm/messages/send',payload); crmCloseModal(); crmNotify(`${r.sent}건 발송(목업) 완료`,'ok'); if(crmTab==='messages') crmMsgRender('log'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
function crmMessageToCustomer(id,name){ crmMessageForm({customer_id:id, title:`${name||'고객'} 메시지`}); }
function crmTemplateForm(existing){
    const t=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">템플릿명 <span class="text-danger">*</span></label><input class="form-control" id="tfName" value="${escapeHtml(t.name||'')}"></div>
        <div class="col-md-3"><label class="form-label">채널</label><select class="form-select" id="tfChannel"><option value="sms" ${t.channel==='sms'?'selected':''}>SMS</option><option value="alimtalk" ${t.channel==='alimtalk'?'selected':''}>알림톡</option></select></div>
        <div class="col-md-3"><label class="form-label">분류</label><input class="form-control" id="tfCat" value="${escapeHtml(t.category||'')}" placeholder="reminder 등"></div>
        <div class="col-12"><label class="form-label">내용 <small class="text-muted">({고객명} {매장명} {포인트})</small></label><textarea class="form-control" id="tfBody" rows="3">${escapeHtml(t.body||'')}</textarea></div>
        <div class="col-12"><div id="tfResult"></div></div>
    </div>`;
    crmModal(isEdit?'템플릿 수정':'템플릿 추가', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmTemplateSave(${isEdit?t.id:'null'})">${isEdit?'수정':'추가'}</button>`);
}
async function crmTemplateSave(id){
    const res=document.getElementById('tfResult'); const name=document.getElementById('tfName').value.trim(); const bodyv=document.getElementById('tfBody').value.trim();
    if(!name||!bodyv){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">이름과 내용은 필수입니다.</div>`; return; }
    const payload={ name, channel:document.getElementById('tfChannel').value, category:document.getElementById('tfCat').value.trim()||null, body:bodyv };
    try{ if(id) await apiPut(`/api/crm/message-templates/${id}`,payload); else await apiPost('/api/crm/message-templates',payload); crmCloseModal(); crmNotify('저장되었습니다.','ok'); crmMsgRender('templates'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
async function crmTemplateDelete(id){ if(!confirm('템플릿을 삭제할까요?')) return; try{ await apiDelete(`/api/crm/message-templates/${id}`); crmNotify('삭제되었습니다.','ok'); crmMsgRender('templates'); }catch(e){ crmNotify(e.message,'err'); } }

// ─── Services (서비스 메뉴 + 직원 단가) ──────────────────
async function crmRenderServices(body){
    try{
        const data=await apiGet('/api/crm/services');
        crmServiceCache = data;
        const canManage = crmMe.role === 'owner';
        const cats={};
        data.forEach(s=>{ (cats[s.category||'기타']=cats[s.category||'기타']||[]).push(s); });
        let sections='';
        Object.keys(cats).forEach(cat=>{
            const cards=cats[cat].map(s=>`<div class="crm-service-card">
                <div class="crm-service-main">
                    <span class="crm-service-icon"><i class="fas fa-scissors"></i></span>
                    <div><strong>${escapeHtml(s.name)}</strong><small>${s.duration_min}분 · ${s.is_active?'활성':'비활성'}</small></div>
                </div>
                <div class="crm-service-price">${formatMoney(s.price)}</div>
                ${canManage ? `<div class="crm-service-actions">
                    <button class="btn btn-sm btn-outline-info" title="직원별 단가" onclick="crmOpenServicePrice(${s.id})"><i class="fas fa-user-tag"></i></button>
                    <button class="btn btn-sm btn-outline-primary" title="수정" onclick="crmEditService(${s.id})"><i class="fas fa-pen"></i></button>
                    <button class="btn btn-sm btn-outline-danger" title="삭제" onclick="crmServiceDelete(${s.id})"><i class="fas fa-trash"></i></button>
                </div>` : ''}
            </div>`).join('');
            sections+=`<section class="crm-service-section"><h6 class="crm-svc-cat-hdr" onclick="this.closest('.crm-service-section').classList.toggle('crm-svc-collapsed')"><i class="fas fa-folder me-1"></i>${escapeHtml(cat)}<span class="crm-svc-badge ms-2">${cats[cat].length}</span><i class="fas fa-chevron-down crm-svc-arrow"></i></h6><div class="crm-service-grid">${cards}</div></section>`;
        });
        body.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><div><h6 class="mb-1">서비스관리</h6><small class="text-muted">${canManage?'서비스 메뉴의 가격과 소요시간을 관리합니다.':'매장에서 제공하는 서비스 메뉴를 확인합니다.'}</small></div>${canManage?'<button class="btn btn-sm btn-primary" onclick="crmServiceForm()"><i class="fas fa-plus me-1"></i>서비스 추가</button>':''}</div><div class="card-body">${sections||'<div class="empty-state compact"><i class="fas fa-list-check"></i><p>등록된 서비스가 없습니다.</p></div>'}</div></div>`;
    }catch(e){ body.innerHTML=`<div class="alert alert-danger">${escapeHtml(e.message)}</div>`; }
}
function crmEditService(id){ const service=crmServiceCache.find(item=>item.id===id); if(service) crmServiceForm(service); }
function crmOpenServicePrice(id){ const service=crmServiceCache.find(item=>item.id===id); if(service) crmServicePriceForm(id,service.name); }
function crmServiceForm(existing){
    const s=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">서비스명 <span class="text-danger">*</span></label><input class="form-control" id="sfName" value="${escapeHtml(s.name||'')}"></div>
        <div class="col-md-6"><label class="form-label">카테고리</label><input class="form-control" id="sfCat" list="sfCatList" value="${escapeHtml(s.category||'')}" placeholder="예) 기본/프리미엄/관리/추가"><datalist id="sfCatList"><option value="기본"><option value="프리미엄"><option value="관리"><option value="추가"><option value="기타"></datalist></div>
        <div class="col-md-6"><label class="form-label">가격</label><input class="form-control" id="sfPrice" type="number" value="${s.price!=null?s.price:0}"></div>
        <div class="col-md-6"><label class="form-label">소요(분)</label><input class="form-control" id="sfDur" type="number" value="${s.duration_min!=null?s.duration_min:60}"></div>
        ${isEdit?`<div class="col-12"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="sfActive" ${s.is_active!==false?'checked':''}><label class="form-check-label">활성</label></div></div>`:''}
        <div class="col-12"><div id="sfResult"></div></div>
    </div>`;
    crmModal(isEdit?'서비스 수정':'서비스 추가', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmServiceSave(${isEdit?s.id:'null'})">${isEdit?'수정':'추가'}</button>`);
}
async function crmServiceSave(id){
    const res=document.getElementById('sfResult'); const name=document.getElementById('sfName').value.trim();
    if(!name){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">서비스명은 필수입니다.</div>`; return; }
    const payload={ name, category:document.getElementById('sfCat').value.trim()||null, price:parseFloat(document.getElementById('sfPrice').value)||0, duration_min:parseInt(document.getElementById('sfDur').value)||60 };
    const act=document.getElementById('sfActive'); if(act) payload.is_active=act.checked;
    try{ if(id) await apiPut(`/api/crm/services/${id}`,payload); else await apiPost('/api/crm/services',payload); crmServiceCache=await apiGet('/api/crm/services'); crmCloseModal(); crmNotify('저장되었습니다.','ok'); crmSwitchTab('services'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${escapeHtml(e.message)}</div>`; }
}
async function crmServiceDelete(id){ if(!confirm('이 서비스를 삭제할까요?')) return; try{ await apiDelete(`/api/crm/services/${id}`); crmServiceCache=await apiGet('/api/crm/services'); crmNotify('삭제되었습니다.','ok'); crmSwitchTab('services'); }catch(e){ crmNotify(e.message,'err'); } }
async function crmServicePriceForm(sid,name){
    const prices=await apiGet(`/api/crm/services/${sid}/prices`);
    const priceMap={}; prices.forEach(p=>priceMap[p.staff_id]=p.price);
    const rows=crmStaffCache.map(st=>`<tr><td>${escapeHtml(st.name)}</td><td><div class="input-group input-group-sm"><input class="form-control" id="spp_${st.id}" type="number" value="${priceMap[st.id]!=null?priceMap[st.id]:''}" placeholder="기본가 사용"><button class="btn btn-outline-primary" onclick="crmServicePriceSave(${sid},${st.id})">저장</button></div></td></tr>`).join('');
    crmModal(`${name} — 직원별 단가`, `<table class="table align-middle"><thead class="table-light"><tr><th>직원</th><th>단가(원)</th></tr></thead><tbody>${rows||'<tr><td colspan=2 class="text-muted text-center">직원 없음</td></tr>'}</tbody></table><div class="small text-muted">비워두면 서비스 기본가가 적용됩니다.</div>`, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>`);
}
async function crmServicePriceSave(sid,staffId){
    const v=document.getElementById(`spp_${staffId}`).value;
    if(v==='') { crmNotify('값을 입력하세요','info'); return; }
    try{ await apiPost(`/api/crm/services/${sid}/prices`,{staff_id:staffId,price:parseFloat(v)||0}); crmNotify('단가 저장됨','ok'); }catch(e){ crmNotify(e.message,'err'); }
}

async function loadOwnerInfo(c, t) {
    t.textContent = '매장 정보';
    const info = await apiGet('/api/owner/merchant-info');
    const stats = await apiGet('/api/owner/dashboard-stats');

    const categories = [
        {value: '', label: '미설정'},
        {value: 'hair_salon', label: '미용실'},
        {value: 'nail_shop', label: '네일샵'},
        {value: 'waxing_shop', label: '왁싱샵'},
        {value: 'massage_shop', label: '마사지샵'},
        {value: 'restaurant', label: '식당'},
        {value: 'cafe', label: '카페'},
        {value: 'bakery', label: '베이커리'},
        {value: 'gym', label: '헬스장'},
        {value: 'other_staff', label: '기타(직원관리)'},
        {value: 'other', label: '기타'},
        {value: 'custom', label: '직접입력'},
    ];
    const catOptions = categories.map(ct =>
        `<option value="${ct.value}" ${info.category === ct.value ? 'selected' : ''}>${ct.label}</option>`
    ).join('');

    c.innerHTML = `
    <div class="row g-4">
        <div class="col-md-7">
            <div class="card data-card">
                <div class="card-header"><h5><i class="fas fa-store me-2"></i>매장 정보 수정</h5></div>
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label fw-bold">매장명</label>
                            <input class="form-control" id="infoName" value="${escapeHtml(info.name || '')}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">사업자번호</label>
                            <input class="form-control" id="infoBizNo" value="${escapeHtml(info.business_no || '')}">
                        </div>
                        <div class="col-12">
                            <label class="form-label fw-bold">주소</label>
                            <input class="form-control" id="infoAddr" value="${escapeHtml(info.address || '')}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">연락처</label>
                            <input class="form-control" id="infoPhone" value="${escapeHtml(info.phone || '')}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">분야 <span class="text-danger">*</span></label>
                            <select class="form-select" id="infoCategory" onchange="toggleCustomCategory()">
                                ${catOptions}
                            </select>
                        </div>
                        <div class="col-md-6" id="customCatWrap" style="display:${info.category === 'custom' ? '' : 'none'}">
                            <label class="form-label fw-bold">직접입력 분야명</label>
                            <input class="form-control" id="infoCategoryCustom" value="${info.category_custom || ''}" placeholder="예: 피부관리실">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">네이버 플레이스 URL</label>
                            <input class="form-control" id="infoPlaceUrl" value="${escapeHtml(info.place_url || '')}" placeholder="https://map.naver.com/...">
                        </div>
                        <div class="col-12">
                            <button class="btn btn-primary" onclick="saveMerchantInfo()"><i class="fas fa-save me-1"></i>매장 정보 저장</button>
                            <div id="infoSaveResult" class="mt-2"></div>
                        </div>
                    </div>
                    <div class="alert alert-info mt-3 mb-0">
                        <i class="fas fa-info-circle me-2"></i>
                        <strong>분야 설정 안내:</strong> 식당, 카페 등을 선택하면 <strong>직원관리</strong>와 <strong>직원별 매출</strong> 메뉴가 숨겨집니다.
                        직원별 매출 확인이 필요한 업종은 해당 메뉴가 표시됩니다.
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-5">
            <div class="card data-card h-100">
                <div class="card-header"><h5><i class="fas fa-chart-pie me-2"></i>매장 현황</h5></div>
                <div class="card-body">
                    <ul class="list-unstyled">
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">매장명</span><span class="fw-bold">${escapeHtml(info.name)}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">분야</span><span class="badge bg-primary">${escapeHtml(info.display_category)}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">활성 직원 수</span><span class="fw-bold">${stats.active_staff}명</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이번달 매출</span><span class="fw-bold text-primary">${formatMoney(stats.month_sales)}</span></li>
                        <li class="d-flex justify-content-between"><span class="text-muted">총 결제건수</span><span class="fw-bold">${stats.total_transactions}건</span></li>
                    </ul>
                </div>
            </div>
        </div>
    </div>`;
}

function toggleCustomCategory() {
    const sel = document.getElementById('infoCategory');
    document.getElementById('customCatWrap').style.display = sel.value === 'custom' ? '' : 'none';
}

async function saveMerchantInfo() {
    try {
        const params = new URLSearchParams();
        params.append('name', document.getElementById('infoName').value);
        params.append('business_no', document.getElementById('infoBizNo').value);
        params.append('address', document.getElementById('infoAddr').value);
        params.append('phone', document.getElementById('infoPhone').value);
        params.append('category', document.getElementById('infoCategory').value);
        params.append('category_custom', document.getElementById('infoCategoryCustom')?.value || '');
        params.append('place_url', document.getElementById('infoPlaceUrl').value);

        const res = await api(`/api/owner/merchant-info?${params.toString()}`, { method: 'PUT' });

        // 캐시 업데이트
        ownerMerchantInfo = await apiGet('/api/owner/merchant-info');

        document.getElementById('infoSaveResult').innerHTML = `
            <div class="alert alert-success py-2">
                <i class="fas fa-check-circle me-1"></i>매장 정보가 저장되었습니다.
                ${!res.needs_staff_management ? '<br><small>직원관리/직원별 매출 메뉴가 숨겨집니다.</small>' : ''}
            </div>`;

        // 사이드바 재구성 (분야 변경에 따른 메뉴 표시/숨김)
        buildSidebar();

        // 이름 변경 시 표시 업데이트
        const displayName = ownerDisplayName(currentUser, ownerMerchantInfo.name);
        document.getElementById('sidebarUserName').textContent = displayName;
        const topBarEl = document.getElementById('topBarUser');
        if (topBarEl) topBarEl.textContent = `${displayName} (${roleLabel(currentUser.role)})`;

    } catch (e) {
        document.getElementById('infoSaveResult').innerHTML = `<div class="alert alert-danger py-2">${escapeHtml(e.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════════
// OWNER - RECEIPT REVIEW MANAGEMENT
// ═══════════════════════════════════════════════════════════

async function loadOwnerReceiptReview(c, t) {
    t.textContent = '영수증 리뷰관리';

    let config;
    try {
        config = await apiGet('/api/owner/receipt-review/config');
    } catch(e) {
        config = { exists: false };
    }

    let reviews = [];
    if (config.exists) {
        try { reviews = await apiGet('/api/owner/receipt-review/list'); } catch(e) {}
    }

    const baseUrl = window.location.origin;
    const reviewUrl = config.exists ? `${baseUrl}${config.review_url}` : '';

    // 통계 계산
    const totalCount = reviews.length;
    const pendingCount = reviews.filter(r => r.status === 'pending').length;
    const approvedCount = reviews.filter(r => r.status === 'approved').length;
    const rejectedCount = reviews.filter(r => r.status === 'rejected').length;
    const completedCount = reviews.filter(r => r.review_completed).length;

    c.innerHTML = `
    ${!config.exists ? `
    <!-- 초기 설정 안내 -->
    <div class="card border-0 shadow-sm" style="border-radius:16px;">
        <div class="card-body text-center py-5">
            <div style="width:80px;height:80px;border-radius:50%;background:linear-gradient(135deg,#e0f2fe,#dbeafe);display:flex;align-items:center;justify-content:center;margin:0 auto 1.5rem;">
                <i class="fas fa-qrcode text-primary" style="font-size:2rem;"></i>
            </div>
            <h4 class="fw-bold mb-2">영수증 리뷰 시스템 시작하기</h4>
            <p class="text-muted mb-4" style="max-width:400px;margin:0 auto;">QR코드와 NFC 태그로 고객의 영수증 리뷰를 수집하고<br>플레이스 리뷰로 연결하세요.</p>
            <button class="btn btn-primary px-4 py-2" onclick="createReviewConfig()">
                <i class="fas fa-plus me-2"></i>리뷰 설정 생성
            </button>
        </div>
    </div>
    ` : `

    <!-- ── 리뷰 플로우 안내 ── -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:12px;overflow:hidden;">
        <div class="card-body p-0">
            <div class="d-none d-md-flex align-items-stretch text-center" style="min-height:72px;">
                <div class="flex-fill d-flex align-items-center justify-content-center gap-2 py-2 px-3" style="background:#e0f2fe;">
                    <i class="fas fa-qrcode text-primary"></i>
                    <div class="small"><div class="fw-bold text-primary">STEP 1</div><span class="text-muted" style="font-size:.75rem;">QR/NFC 스캔</span></div>
                </div>
                <div class="flex-fill d-flex align-items-center justify-content-center gap-2 py-2 px-3" style="background:#cffafe;">
                    <i class="fas fa-camera text-info"></i>
                    <div class="small"><div class="fw-bold text-info">STEP 2</div><span class="text-muted" style="font-size:.75rem;">영수증 촬영</span></div>
                </div>
                <div class="flex-fill d-flex align-items-center justify-content-center gap-2 py-2 px-3" style="background:#dcfce7;">
                    <i class="fas fa-pen text-success"></i>
                    <div class="small"><div class="fw-bold text-success">STEP 3</div><span class="text-muted" style="font-size:.75rem;">리뷰 작성</span></div>
                </div>
                <div class="flex-fill d-flex align-items-center justify-content-center gap-2 py-2 px-3" style="background:#fef3c7;">
                    <i class="fas fa-check-double text-warning"></i>
                    <div class="small"><div class="fw-bold text-warning">STEP 4</div><span class="text-muted" style="font-size:.75rem;">사장님 확인</span></div>
                </div>
                <div class="flex-fill d-flex align-items-center justify-content-center gap-2 py-2 px-3" style="background:#fee2e2;">
                    <i class="fas fa-map-marker-alt text-danger"></i>
                    <div class="small"><div class="fw-bold text-danger">STEP 5</div><span class="text-muted" style="font-size:.75rem;">플레이스 리뷰</span></div>
                </div>
            </div>
            <!-- 모바일용 플로우 -->
            <div class="d-md-none p-3">
                <div class="d-flex align-items-center justify-content-between">
                    <div class="text-center" style="flex:1;">
                        <div style="width:36px;height:36px;border-radius:50%;background:#e0f2fe;display:inline-flex;align-items:center;justify-content:center;"><i class="fas fa-qrcode text-primary" style="font-size:.8rem;"></i></div>
                        <div style="font-size:.6rem;" class="text-muted mt-1">스캔</div>
                    </div>
                    <i class="fas fa-chevron-right text-muted" style="font-size:.5rem;"></i>
                    <div class="text-center" style="flex:1;">
                        <div style="width:36px;height:36px;border-radius:50%;background:#cffafe;display:inline-flex;align-items:center;justify-content:center;"><i class="fas fa-camera text-info" style="font-size:.8rem;"></i></div>
                        <div style="font-size:.6rem;" class="text-muted mt-1">촬영</div>
                    </div>
                    <i class="fas fa-chevron-right text-muted" style="font-size:.5rem;"></i>
                    <div class="text-center" style="flex:1;">
                        <div style="width:36px;height:36px;border-radius:50%;background:#dcfce7;display:inline-flex;align-items:center;justify-content:center;"><i class="fas fa-pen text-success" style="font-size:.8rem;"></i></div>
                        <div style="font-size:.6rem;" class="text-muted mt-1">리뷰</div>
                    </div>
                    <i class="fas fa-chevron-right text-muted" style="font-size:.5rem;"></i>
                    <div class="text-center" style="flex:1;">
                        <div style="width:36px;height:36px;border-radius:50%;background:#fef3c7;display:inline-flex;align-items:center;justify-content:center;"><i class="fas fa-check-double text-warning" style="font-size:.8rem;"></i></div>
                        <div style="font-size:.6rem;" class="text-muted mt-1">확인</div>
                    </div>
                    <i class="fas fa-chevron-right text-muted" style="font-size:.5rem;"></i>
                    <div class="text-center" style="flex:1;">
                        <div style="width:36px;height:36px;border-radius:50%;background:#fee2e2;display:inline-flex;align-items:center;justify-content:center;"><i class="fas fa-map-marker-alt text-danger" style="font-size:.8rem;"></i></div>
                        <div style="font-size:.6rem;" class="text-muted mt-1">리뷰등록</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ── 통계 카드 ── -->
    <div class="row g-2 g-md-3 mb-4 review-stats-grid">
        <div class="col-6 col-lg-3">
            <div class="card border-0 shadow-sm text-center" style="border-radius:12px;border-top:3px solid #0d6efd!important;">
                <div class="card-body py-3">
                    <div class="fw-bold fs-3 text-primary">${totalCount}</div>
                    <div class="small text-muted">전체 리뷰</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-lg-3">
            <div class="card border-0 shadow-sm text-center" style="border-radius:12px;border-top:3px solid #ffc107!important;">
                <div class="card-body py-3">
                    <div class="fw-bold fs-3 text-warning">${pendingCount}</div>
                    <div class="small text-muted">확인 대기</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-lg-3">
            <div class="card border-0 shadow-sm text-center" style="border-radius:12px;border-top:3px solid #198754!important;">
                <div class="card-body py-3">
                    <div class="fw-bold fs-3 text-success">${approvedCount}</div>
                    <div class="small text-muted">승인 완료</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-lg-3">
            <div class="card border-0 shadow-sm text-center" style="border-radius:12px;border-top:3px solid #0dcaf0!important;">
                <div class="card-body py-3">
                    <div class="fw-bold fs-3 text-info">${completedCount}</div>
                    <div class="small text-muted">리뷰 완료</div>
                </div>
            </div>
        </div>
    </div>

    <div class="row g-3 g-lg-4">
        <!-- ── QR/NFC 설정 ── -->
        <div class="col-lg-5 review-qr-section">
            <div class="card border-0 shadow-sm" style="border-radius:12px;">
                <div class="card-header border-0 bg-white pt-3 px-4">
                    <h6 class="fw-bold mb-0"><i class="fas fa-qrcode text-primary me-2"></i>QR코드 / NFC 설정</h6>
                </div>
                <div class="card-body px-4 pb-4 pt-2">
                    <!-- QR코드 -->
                    <div class="text-center mb-3 p-3" style="background:#f8fafc;border-radius:12px;">
                        <img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(reviewUrl)}"
                             alt="QR Code" style="width:150px;height:150px;border-radius:8px;">
                        <p class="small text-muted mt-2 mb-0">고객이 스캔하면 리뷰 페이지로 이동합니다</p>
                    </div>

                    <!-- URL 복사 -->
                    <div class="mb-3">
                        <label class="form-label fw-bold small mb-1">리뷰 URL</label>
                        <div class="input-group input-group-sm">
                            <input class="form-control bg-light" id="reviewUrlInput" value="${escapeHtml(reviewUrl)}" readonly style="font-size:.8rem;">
                            <button class="btn btn-primary" onclick="copyReviewUrl()" title="복사"><i class="fas fa-copy"></i></button>
                        </div>
                    </div>

                    <!-- 플레이스 URL -->
                    <div class="mb-3">
                        <label class="form-label fw-bold small mb-1">플레이스 URL</label>
                        <input class="form-control form-control-sm" id="reviewPlaceUrl" value="${escapeHtml(config.place_url || '')}" placeholder="https://map.naver.com/...">
                    </div>

                    <!-- 환영 메시지 -->
                    <div class="mb-3">
                        <label class="form-label fw-bold small mb-1">환영 메시지</label>
                        <textarea class="form-control form-control-sm" id="reviewWelcomeMsg" rows="2" placeholder="방문해주셔서 감사합니다!">${escapeHtml(config.welcome_message || '')}</textarea>
                    </div>

                    <!-- 버튼 그룹 -->
                    <div class="d-grid gap-2">
                        <button class="btn btn-primary btn-sm" onclick="updateReviewConfig()"><i class="fas fa-save me-1"></i>설정 저장</button>
                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-secondary btn-sm flex-fill" onclick="printQRCode()"><i class="fas fa-print me-1"></i>QR 인쇄</button>
                            <button class="btn btn-outline-warning btn-sm flex-fill" onclick="regenerateToken()"><i class="fas fa-sync me-1"></i>토큰 재발급</button>
                        </div>
                    </div>
                    <div id="reviewConfigResult" class="mt-2"></div>
                </div>
            </div>

            <!-- NFC 안내 -->
            <div class="card border-0 shadow-sm mt-3" style="border-radius:12px;">
                <div class="card-body px-4 py-3">
                    <h6 class="fw-bold mb-2"><i class="fas fa-wifi text-success me-2"></i>NFC 태그 설정</h6>
                    <p class="small text-muted mb-2">NFC 태그에 아래 URL을 기록하세요:</p>
                    <code class="d-block bg-light p-2 rounded small mb-2" style="word-break:break-all;font-size:.75rem;">${escapeHtml(reviewUrl)}</code>
                    <div class="small text-muted">
                        <i class="fas fa-lightbulb text-warning me-1"></i>
                        NFC 라이터 앱으로 URL 기록 → 매장 카운터에 부착 → 고객 터치 시 자동 이동
                    </div>
                </div>
            </div>
        </div>

        <!-- ── 리뷰 목록 ── -->
        <div class="col-lg-7 review-list-section">
            <div class="card border-0 shadow-sm" style="border-radius:12px;">
                <div class="card-header border-0 bg-white d-flex justify-content-between align-items-center pt-3 px-3 px-md-4">
                    <h6 class="fw-bold mb-0" style="font-size:.9rem;"><i class="fas fa-list-alt text-primary me-2"></i>리뷰 목록</h6>
                    <div class="d-flex align-items-center gap-1 gap-md-2">
                        <select class="form-select form-select-sm" style="width:auto;font-size:.8rem;" id="reviewStatusFilter" onchange="filterReviews()">
                            <option value="all">전체 (${totalCount})</option>
                            <option value="pending">대기 (${pendingCount})</option>
                            <option value="approved">승인 (${approvedCount})</option>
                            <option value="rejected">반려 (${rejectedCount})</option>
                        </select>
                        <button class="btn btn-outline-primary btn-sm" onclick="navigate('owner-receipt-review')" title="새로고침"><i class="fas fa-redo"></i></button>
                    </div>
                </div>
                <div class="card-body px-4 pb-4 pt-2" id="reviewListBody" style="max-height:600px;overflow-y:auto;">
                    ${reviews.length > 0 ? renderReviewCards(reviews) : `
                    <div class="text-center py-5 text-muted">
                        <i class="fas fa-inbox fa-2x mb-2 d-block opacity-50"></i>
                        <p class="mb-1 fw-bold">아직 제출된 리뷰가 없습니다</p>
                        <small>고객이 QR코드를 스캔하여 영수증을 제출하면 여기에 표시됩니다</small>
                    </div>`}
                </div>
            </div>
        </div>
    </div>

    <!-- 리뷰 상세보기 모달 -->
    <div class="modal fade" id="reviewDetailModal" tabindex="-1">
        <div class="modal-dialog modal-lg modal-dialog-centered">
            <div class="modal-content" style="border-radius:16px;border:none;">
                <div class="modal-header border-0 pb-0">
                    <h5 class="modal-title fw-bold"><i class="fas fa-receipt text-primary me-2"></i>리뷰 상세</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body" id="reviewDetailBody"></div>
                <div class="modal-footer border-0" id="reviewDetailFooter"></div>
            </div>
        </div>
    </div>
    `}`;

    // 리뷰 데이터를 전역에 저장 (필터, 상세보기에서 사용)
    window._receiptReviews = reviews;
}

function renderReviewCards(reviews) {
    if (!reviews || reviews.length === 0) {
        return `<div class="text-center py-4 text-muted">
            <i class="fas fa-inbox fa-2x mb-2 d-block opacity-50"></i>
            <p class="mb-0">해당하는 리뷰가 없습니다</p>
        </div>`;
    }
    return reviews.map(r => {
        const imgUrl = safeUrl(r.receipt_image_url);
        const hasImage = !!imgUrl;
        const hasMemo = !!r.memo;
        const statusColor = r.status === 'approved' ? '#198754' : r.status === 'rejected' ? '#dc3545' : '#ffc107';
        return `
        <div class="border rounded-3 p-3 mb-2 position-relative"
             style="cursor:pointer;transition:all .15s;border-left:3px solid ${statusColor}!important;padding:.6rem!important;"
             onmouseover="this.style.boxShadow='0 2px 12px rgba(0,0,0,.08)';this.style.background='#fafbfc'"
             onmouseout="this.style.boxShadow='none';this.style.background=''"
             onclick="openReviewDetail(${r.id})">
            <div class="d-flex gap-3 align-items-start">
                <div class="flex-shrink-0" style="width:56px;height:56px;">
                    ${hasImage ? `
                        <img src="${imgUrl}" alt="영수증"
                             style="width:56px;height:56px;object-fit:cover;border-radius:8px;">
                    ` : `
                        <div style="width:56px;height:56px;border-radius:8px;background:#f1f5f9;display:flex;align-items:center;justify-content:center;">
                            <i class="fas fa-receipt text-muted"></i>
                        </div>
                    `}
                </div>
                <div class="flex-grow-1 min-w-0">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="fw-bold" style="font-size:.9rem;">${escapeHtml(r.customer_name) || '익명 고객'}</span>
                        <div class="d-flex align-items-center gap-1">
                            ${reviewStatusBadge(r.status)}
                            ${r.review_completed ? '<span class="badge bg-info bg-opacity-75" title="플레이스 리뷰 완료"><i class="fas fa-star"></i></span>' : ''}
                        </div>
                    </div>
                    ${hasMemo ? `<p class="mb-1 small text-dark" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;"><i class="fas fa-comment text-primary me-1" style="font-size:.7rem;"></i>${escapeHtml(r.memo)}</p>` : ''}
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="text-muted" style="font-size:.75rem;"><i class="fas fa-clock me-1"></i>${formatDate(r.created_at)}</span>
                        <div class="d-flex gap-1" onclick="event.stopPropagation();">
                            ${r.status === 'pending' ? `
                                <button class="btn btn-sm btn-success py-0 px-2" style="font-size:.75rem;" onclick="updateReviewStatus(${r.id},'approved')"><i class="fas fa-check me-1"></i>승인</button>
                                <button class="btn btn-sm btn-outline-danger py-0 px-2" style="font-size:.75rem;" onclick="updateReviewStatus(${r.id},'rejected')"><i class="fas fa-times me-1"></i>반려</button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');
}

function filterReviews() {
    const filter = document.getElementById('reviewStatusFilter').value;
    const reviews = window._receiptReviews || [];
    const filtered = filter === 'all' ? reviews : reviews.filter(r => r.status === filter);
    document.getElementById('reviewListBody').innerHTML = renderReviewCards(filtered);
}

function openReviewDetail(reviewId) {
    const reviews = window._receiptReviews || [];
    const r = reviews.find(rv => rv.id === reviewId);
    if (!r) return;

    const imgUrl = safeUrl(r.receipt_image_url);
    const hasImage = !!imgUrl;
    const body = document.getElementById('reviewDetailBody');
    const footer = document.getElementById('reviewDetailFooter');

    body.innerHTML = `
    <div class="row g-4">
        <!-- 영수증 이미지 -->
        <div class="col-md-5 text-center">
            ${hasImage ? `
                <div class="position-relative">
                    <img src="${imgUrl}" alt="영수증 이미지"
                         class="img-fluid rounded shadow-sm" style="max-height:400px;cursor:pointer;"
                         onclick="window.open('${imgUrl}','_blank')">
                    <div class="mt-2">
                        <a href="${imgUrl}" target="_blank" class="btn btn-sm btn-outline-primary">
                            <i class="fas fa-expand-alt me-1"></i>원본 보기
                        </a>
                    </div>
                </div>
            ` : `
                <div class="d-flex align-items-center justify-content-center rounded"
                     style="height:200px;background:#f8f9fa;border:2px dashed #dee2e6;">
                    <div class="text-center text-muted">
                        <i class="fas fa-image fa-3x mb-2 d-block opacity-25"></i>
                        <p class="mb-0 small">영수증 이미지 없음</p>
                    </div>
                </div>
            `}
        </div>

        <!-- 리뷰 상세 정보 -->
        <div class="col-md-7">
            <table class="table table-sm table-borderless">
                <tbody>
                    <tr>
                        <td class="text-muted fw-bold" style="width:100px;"><i class="fas fa-hashtag me-1"></i>리뷰 ID</td>
                        <td>${r.id}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-user me-1"></i>고객명</td>
                        <td>${escapeHtml(r.customer_name) || '<span class="text-muted fst-italic">미입력</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-phone me-1"></i>연락처</td>
                        <td>${escapeHtml(r.customer_phone) || '<span class="text-muted fst-italic">미입력</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-flag me-1"></i>상태</td>
                        <td>${reviewStatusBadge(r.status)}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-star me-1"></i>플레이스</td>
                        <td>${r.review_completed
                            ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>리뷰 작성 완료</span>'
                            : '<span class="badge bg-secondary"><i class="fas fa-clock me-1"></i>미작성</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-calendar me-1"></i>제출일시</td>
                        <td>${formatDate(r.created_at)}</td>
                    </tr>
                </tbody>
            </table>

            <!-- 한줄 리뷰(메모) -->
            <div class="mt-3">
                <label class="form-label fw-bold small"><i class="fas fa-comment-dots text-primary me-1"></i>고객 한줄 리뷰</label>
                <div class="bg-light rounded p-3 ${r.memo ? '' : 'text-muted fst-italic'}">
                    ${r.memo ? escapeHtml(r.memo) : '고객이 리뷰를 남기지 않았습니다.'}
                </div>
            </div>

            <!-- 관리자 메모 입력 -->
            <div class="mt-3">
                <label class="form-label fw-bold small"><i class="fas fa-sticky-note text-warning me-1"></i>관리자 메모 (내부용)</label>
                <textarea class="form-control form-control-sm" id="modalAdminMemo" rows="2"
                          placeholder="관리 참고용 메모를 입력하세요...">${escapeHtml(r.admin_memo) || ''}</textarea>
            </div>
        </div>
    </div>`;

    footer.innerHTML = `
        <div class="d-flex justify-content-between w-100 flex-wrap gap-2">
            <div>
                ${r.status !== 'approved' ? `<button class="btn btn-success btn-sm" onclick="updateReviewStatusFromModal(${r.id},'approved')"><i class="fas fa-check me-1"></i>승인</button>` : ''}
                ${r.status !== 'rejected' ? `<button class="btn btn-outline-danger btn-sm" onclick="updateReviewStatusFromModal(${r.id},'rejected')"><i class="fas fa-times me-1"></i>반려</button>` : ''}
                ${r.status !== 'pending' ? `<button class="btn btn-outline-warning btn-sm" onclick="updateReviewStatusFromModal(${r.id},'pending')"><i class="fas fa-undo me-1"></i>대기로 되돌리기</button>` : ''}
            </div>
            <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
        </div>`;

    const modal = new bootstrap.Modal(document.getElementById('reviewDetailModal'));
    modal.show();
}

async function updateReviewStatusFromModal(reviewId, newStatus) {
    try {
        const memo = document.getElementById('modalAdminMemo')?.value || '';
        await api(`/api/owner/receipt-review/${reviewId}/status?status=${newStatus}${memo ? '&memo=' + encodeURIComponent(memo) : ''}`, { method: 'PUT' });
        bootstrap.Modal.getInstance(document.getElementById('reviewDetailModal'))?.hide();
        navigate('owner-receipt-review');
    } catch(e) { alert('상태 변경 실패: ' + e.message); }
}

function reviewStatusBadge(s) {
    const map = {pending:'<span class="badge bg-warning">대기중</span>', approved:'<span class="badge bg-success">승인</span>', rejected:'<span class="badge bg-danger">반려</span>'};
    return map[s] || `<span class="badge bg-secondary">${s}</span>`;
}

async function createReviewConfig() {
    try {
        await apiPost('/api/owner/receipt-review/config', {});
        navigate('owner-receipt-review');
    } catch(e) { alert('설정 생성 실패: ' + e.message); }
}

async function updateReviewConfig() {
    try {
        const placeUrl = document.getElementById('reviewPlaceUrl').value;
        const welcomeMsg = document.getElementById('reviewWelcomeMsg').value;
        const params = new URLSearchParams();
        if (placeUrl) params.append('place_url', placeUrl);
        if (welcomeMsg) params.append('welcome_message', welcomeMsg);
        await apiPost(`/api/owner/receipt-review/config?${params.toString()}`, {});
        document.getElementById('reviewConfigResult').innerHTML = '<div class="alert alert-success py-1 small"><i class="fas fa-check me-1"></i>저장 완료</div>';
    } catch(e) {
        document.getElementById('reviewConfigResult').innerHTML = `<div class="alert alert-danger py-1 small">${escapeHtml(e.message)}</div>`;
    }
}

async function regenerateToken() {
    if (!confirm('토큰을 재발급하면 기존 QR코드/NFC 태그가 무효화됩니다. 계속하시겠습니까?')) return;
    try {
        await apiPost('/api/owner/receipt-review/config/regenerate-token', {});
        navigate('owner-receipt-review');
    } catch(e) { alert('토큰 재발급 실패: ' + e.message); }
}

function copyReviewUrl() {
    const input = document.getElementById('reviewUrlInput');
    input.select();
    navigator.clipboard.writeText(input.value).then(() => {
        alert('URL이 복사되었습니다!');
    });
}

function printQRCode() {
    const url = document.getElementById('reviewUrlInput').value;
    const merchantName = ownerMerchantInfo ? ownerMerchantInfo.name : 'ADPAY 매장';
    const printWin = window.open('', '_blank', 'width=400,height=600');
    printWin.document.write(`
        <html><head><title>QR코드 인쇄</title>
        <style>body{font-family:'Noto Sans KR',sans-serif;text-align:center;padding:40px;}
        .title{font-size:24px;font-weight:900;margin-bottom:10px;}
        .subtitle{font-size:14px;color:#666;margin-bottom:30px;}
        .qr-img{margin:20px auto;}
        .footer{margin-top:30px;font-size:12px;color:#999;}
        .scan-text{font-size:16px;font-weight:700;margin-top:20px;color:#1b3a5c;}
        </style></head><body>
        <div class="title">${merchantName}</div>
        <div class="subtitle">영수증 리뷰 이벤트</div>
        <img class="qr-img" src="https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(url)}">
        <div class="scan-text">📱 QR코드를 스캔해주세요</div>
        <p style="font-size:13px;color:#555;margin-top:10px;">영수증을 촬영하고<br>리뷰를 남겨주시면 감사하겠습니다!</p>
        <div class="footer">Powered by ADPAY</div>
        <script>setTimeout(()=>window.print(), 500);<\/script>
        </body></html>`);
}

async function updateReviewStatus(reviewId, newStatus) {
    try {
        await api(`/api/owner/receipt-review/${reviewId}/status?status=${newStatus}`, { method: 'PUT' });
        navigate('owner-receipt-review');
    } catch(e) { alert('상태 변경 실패: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════
// DESIGNER PAGES
// ═══════════════════════════════════════════════════════════

async function loadDesignerTransactions(c, t) {
    t.textContent = '내 결제 내역';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">내 결제 내역</h5>
        <select class="form-select form-select-sm" style="width:120px" id="designerRange" onchange="reloadDesignerTx()">
            <option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option>
        </select>
    </div><div class="card-body">
        <div id="designerTxBody">${adpayLoadingMarkup()}</div>
    </div></div>`;
    reloadDesignerTx();
}

async function reloadDesignerTx() {
    const range = document.getElementById('designerRange').value;
    const txns = await apiGet(`/api/designer/transactions?range=${range}`);
    const total = txns.reduce((s,tx)=>s+tx.amount, 0);
    document.getElementById('designerTxBody').innerHTML = `
    <div class="d-flex justify-content-between mb-3">
        <span>합계: <strong class="text-primary">${formatMoney(total)}</strong> (${txns.length}건)</span>
    </div>
    <div class="table-responsive"><table class="table table-hover table-sm">
        <thead><tr><th>ID</th><th>금액</th><th>할부</th><th>카드</th><th>승인번호</th><th>일시</th></tr></thead>
        <tbody>${txns.map(tx=>`<tr>
            <td>${tx.id}</td><td class="fw-bold">${formatMoney(tx.amount)}</td>
            <td>${tx.installment_months||'일시불'}</td><td>${escapeHtml(tx.card_brand||'-')}</td>
            <td><code>${escapeHtml(tx.approval_code||'-')}</code></td><td>${formatDate(tx.created_at)}</td>
        </tr>`).join('')}</tbody>
    </table></div>`;
}

async function loadDesignerMonthly(c, t) {
    t.textContent = '월별 통계';
    const stats = await apiGet('/api/designer/dashboard-stats');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>월별 매출 통계</h5></div><div class="card-body">
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="bg-success bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-success">${formatMoney(stats.today_sales)}</div><div class="small text-muted">오늘 매출</div></div></div>
            <div class="col-md-3"><div class="bg-info bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-info">${formatMoney(stats.month_sales)}</div><div class="small text-muted">이번달 매출</div></div></div>
            <div class="col-md-3"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-primary">${stats.total_transactions}건</div><div class="small text-muted">총 결제건수</div></div></div>
            <div class="col-md-3"><div class="bg-warning bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-warning">${formatMoney(stats.total_sales)}</div><div class="small text-muted">누적 매출</div></div></div>
        </div>
        <p class="text-muted text-center">상세 결제 내역은 <a href="#" onclick="navigate('designer-transactions')">결제 내역</a>에서 확인하세요.</p>
    </div></div>`;
}

async function loadDesignerProfile(c, t) {
    t.textContent = '내 정보';
    const stats = await apiGet('/api/designer/dashboard-stats');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>내 정보</h5></div><div class="card-body">
        <div class="text-center mb-4">
            <div class="d-inline-flex align-items-center justify-content-center bg-warning bg-opacity-10 rounded-circle" style="width:80px;height:80px;">
                <i class="fas fa-paint-brush fa-2x text-warning"></i>
            </div>
        </div>
        <ul class="list-unstyled" style="max-width:400px;margin:0 auto;">
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이름</span><span class="fw-bold">${escapeHtml(stats.staff_name)}</span></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">직원 코드</span><code class="fs-5">${escapeHtml(stats.staff_code)}</code></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">역할</span><span class="badge bg-warning">직원</span></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이번달 매출</span><span class="fw-bold text-primary">${formatMoney(stats.month_sales)}</span></li>
            <li class="d-flex justify-content-between"><span class="text-muted">총 결제건수</span><span class="fw-bold">${stats.total_transactions}건</span></li>
        </ul>
    </div></div>`;
}


// ─── API helpers for form ─────────────────────────────────
async function apiPostForm(url, formData) {
    const res = await fetch(url, { method: 'POST', headers: { 'Authorization': 'Bearer ' + getToken() }, body: formData });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Request failed'); }
    return res.json();
}
async function apiPutForm(url, formData) {
    const res = await fetch(url, { method: 'PUT', headers: { 'Authorization': 'Bearer ' + getToken() }, body: formData });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Request failed'); }
    return res.json();
}
// apiPost / apiDelete 는 api.js 의 구현을 그대로 쓴다.
// (여기서 다시 정의하면 api.js 의 401 → 자동 로그아웃 처리가 덮여 토큰 만료 시 화면이 멈춘다.)


// ─── AI 설정 (최고관리자) ────────────────────────────────────

async function loadAdminAiSettings(c, t) {
    t.textContent = 'AI 설정';
    c.innerHTML = `<div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-robot me-2"></i>OpenAI API 연동</h5>
            <span id="aiStatusBadge"><span class="badge bg-secondary">확인 중...</span></span>
        </div>
        <div class="card-body">
            <div id="aiNotice"></div>
            <label class="form-label fw-bold small">API 키</label>
            <div class="input-group mb-2">
                <span class="input-group-text"><i class="fas fa-key"></i></span>
                <input type="password" class="form-control" id="aiApiKey" placeholder="sk-..." autocomplete="off">
                <button class="btn btn-outline-secondary" type="button" onclick="toggleAiKeyVisible()" id="aiKeyEye" title="입력값 보기">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
            <div class="small text-muted mb-3" id="aiCurrentKey"></div>
            <div class="d-flex gap-2 flex-wrap">
                <button class="btn btn-primary btn-sm" onclick="saveAiApiKey()" id="aiSaveBtn"><i class="fas fa-floppy-disk me-1"></i>저장</button>
                <button class="btn btn-outline-primary btn-sm" onclick="testAiConnection()" id="aiTestBtn"><i class="fas fa-plug me-1"></i>연결 테스트</button>
                <button class="btn btn-outline-danger btn-sm" onclick="deleteAiApiKey()" id="aiDeleteBtn"><i class="fas fa-trash me-1"></i>삭제</button>
            </div>
            <div id="aiResult" class="mt-3"></div>
        </div>
    </div>`;
    await refreshAiSettings();
}

function renderAiState(data) {
    const configured = !!data.configured;
    document.getElementById('aiStatusBadge').innerHTML = configured
        ? '<span class="badge bg-success"><i class="fas fa-circle-check me-1"></i>연결됨</span>'
        : '<span class="badge bg-secondary"><i class="fas fa-circle-minus me-1"></i>미연결</span>';
    document.getElementById('aiCurrentKey').innerHTML = configured
        ? `현재 등록된 키: <code>${escapeHtml(data.masked_key || '')}</code>`
        : '등록된 키가 없습니다.';
    document.getElementById('aiNotice').innerHTML = configured
        ? ''
        : `<div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
             OpenAI API 키를 등록하면 광고 분석의 AI 마케팅 추천이 활성화됩니다.</div>`;
    document.getElementById('aiTestBtn').disabled = !configured;
    document.getElementById('aiDeleteBtn').disabled = !configured;
}

async function refreshAiSettings() {
    try {
        renderAiState(await apiGet('/api/admin/settings/ai'));
    } catch (e) {
        document.getElementById('aiResult').innerHTML =
            `<div class="alert alert-danger py-2 mb-0 small">${escapeHtml(e.message)}</div>`;
    }
}

function toggleAiKeyVisible() {
    const input = document.getElementById('aiApiKey');
    const icon = document.querySelector('#aiKeyEye i');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
}

function showAiResult(ok, message) {
    showToast(message, ok);
    const box = document.getElementById('aiResult');
    if (!box) return;
    box.innerHTML =
        `<div class="alert alert-${ok ? 'success' : 'danger'} py-2 mb-0 small">
            <i class="fas fa-${ok ? 'circle-check' : 'circle-exclamation'} me-1"></i>${escapeHtml(message)}</div>`;
}

async function saveAiApiKey() {
    const input = document.getElementById('aiApiKey');
    const key = input.value.trim();
    if (!key) { showAiResult(false, 'API 키를 입력해주세요.'); return; }
    const btn = document.getElementById('aiSaveBtn');
    btn.disabled = true;
    try {
        const res = await apiPost('/api/admin/settings/ai', { api_key: key });
        input.value = '';
        input.type = 'password';
        document.querySelector('#aiKeyEye i').className = 'fas fa-eye';
        renderAiState(res);
        showAiResult(true, '저장했습니다. 연결 테스트로 확인해보세요.');
    } catch (e) {
        showAiResult(false, e.message);
    } finally {
        btn.disabled = false;
    }
}

async function testAiConnection() {
    const btn = document.getElementById('aiTestBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>확인 중...';
    try {
        const res = await apiGet('/api/admin/settings/ai/status');
        showAiResult(res.ok, res.detail);
    } catch (e) {
        showAiResult(false, e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
        await refreshAiSettings();
    }
}

async function deleteAiApiKey() {
    if (!confirm('등록된 OpenAI API 키를 삭제하시겠습니까?\n삭제하면 AI 마케팅 추천이 비활성화됩니다.')) return;
    const btn = document.getElementById('aiDeleteBtn');
    btn.disabled = true;
    try {
        await apiDelete('/api/admin/settings/ai');
        showAiResult(true, '삭제했습니다.');
        await refreshAiSettings();
    } catch (e) {
        showAiResult(false, e.message);
        btn.disabled = false;
    }
}

// ─── 광고비 크레딧 (관리자 충전 / 매장 조회·환불) ───────────
const CREDIT_ENTRY_STYLE = {
    charge: ['success', 'plus'],
    use: ['secondary', 'minus'],
    reverse: ['info text-dark', 'rotate-left'],
    refund: ['warning text-dark', 'arrow-right-from-bracket'],
    adjust: ['dark', 'pen'],
};

function creditAmount(value) {
    const n = Number(value) || 0;
    const cls = n > 0 ? 'text-success' : (n < 0 ? 'text-danger' : 'text-muted');
    const sign = n > 0 ? '+' : '';
    return `<span class="${cls} fw-bold">${sign}${n.toLocaleString()}원</span>`;
}

function creditLedgerRows(ledger) {
    return (ledger || []).map(e => {
        const [cls] = CREDIT_ENTRY_STYLE[e.entry_type] || ['secondary'];
        return `<tr>
            <td class="small text-muted text-nowrap">${escapeHtml(e.created_at || '')}</td>
            <td><span class="badge bg-${cls}">${escapeHtml(e.entry_label)}</span></td>
            <td class="text-end">${creditAmount(e.amount)}</td>
            <td class="text-end">${Number(e.balance_after).toLocaleString()}원</td>
            <td class="small">${escapeHtml(e.memo || '-')}</td>
        </tr>`;
    }).join('');
}

const CREDIT_LEDGER_HEAD = '<thead><tr><th>일시</th><th>구분</th><th class="text-end">금액</th>'
    + '<th class="text-end">잔액</th><th>메모</th></tr></thead>';

// ── ADMIN: 광고비 크레딧 ────────────────────────────────────
async function loadAdminAdCredits(c, t) {
    t.textContent = '광고비 크레딧';
    c.innerHTML = adpayLoadingMarkup('잔액을 불러오는 중입니다');
    try {
        const [credits, refunds] = await Promise.all([
            apiGet('/api/admin/ad-credits'),
            apiGet('/api/admin/ad-credit-refunds'),
        ]);
        c.innerHTML = adminCreditMarkup(credits, refunds);
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function adminCreditMarkup(d, r) {
    const rows = (d.credits || []).map(m => `<tr>
        <td class="fw-bold">${escapeHtml(m.merchant_name)}</td>
        <td class="text-end">${Number(m.balance).toLocaleString()}원</td>
        <td>${m.balance_matches === false
            ? '<span class="badge bg-danger"><i class="fas fa-triangle-exclamation me-1"></i>원장과 불일치</span>'
            : '<span class="badge bg-light text-muted border">정상</span>'}</td>
        <td class="text-nowrap">
            <button class="btn btn-sm btn-primary me-1" onclick="showCreditCharge(${m.merchant_id}, '${escapeHtml(m.merchant_name)}')">
                <i class="fas fa-plus me-1"></i>충전</button>
            <button class="btn btn-sm btn-outline-secondary" onclick="showCreditLedger(${m.merchant_id}, '${escapeHtml(m.merchant_name)}')">
                <i class="fas fa-list"></i></button>
        </td>
    </tr>`).join('');

    const refundRows = (r.refunds || []).map(f => `<tr>
        <td class="fw-bold">${escapeHtml(f.merchant_name || '-')}</td>
        <td class="text-end fw-bold">${Number(f.amount).toLocaleString()}원</td>
        <td class="small">${escapeHtml(f.reason || '-')}</td>
        <td><span class="badge bg-${f.status === 'pending' ? 'warning text-dark' : (f.status === 'approved' ? 'success' : 'secondary')}">${escapeHtml(f.status_label)}</span>
            ${f.admin_memo ? `<div class="small text-muted mt-1">${escapeHtml(f.admin_memo)}</div>` : ''}</td>
        <td class="small text-muted">${escapeHtml(f.created_at || '')}</td>
        <td class="text-nowrap">${f.status === 'pending'
            ? `<button class="btn btn-sm btn-success me-1" onclick="processRefund(${f.id}, 'approve')"><i class="fas fa-check"></i></button>
               <button class="btn btn-sm btn-outline-danger" onclick="processRefund(${f.id}, 'reject')"><i class="fas fa-ban"></i></button>`
            : ''}</td>
    </tr>`).join('');

    return `
    <div class="row g-3 mb-3">
        ${kpiCard('전체 잔액', `${Number(d.total_balance).toLocaleString()}원`, 'fas fa-wallet', 'primary')}
        ${kpiCard('환불 대기', `${d.pending_refunds}건`, 'fas fa-arrow-right-from-bracket', d.pending_refunds ? 'warning' : 'secondary')}
    </div>

    <div class="card data-card mb-3">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-wallet me-2"></i>매장별 광고비 잔액</h5></div>
        <div class="card-body">
            <div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
                매장이 입금하면 여기서 충전을 반영합니다. 플랜 한도를 넘는 광고 주문은 이 잔액에서 차감되고,
                잔액이 모자라면 주문이 거절됩니다. 환불은 잔액이
                <b>${Number(d.min_refund_amount).toLocaleString()}원 이상</b>일 때 매장이 신청할 수 있습니다.</div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th class="text-end">잔액</th><th>원장 정합성</th><th>관리</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="4" class="text-center text-muted py-4">가맹점이 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>

    <div class="card data-card">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-arrow-right-from-bracket me-2"></i>환불 신청</h5></div>
        <div class="card-body">
            <div class="small text-muted mb-3">승인하면 <b>그 시점에 잔액에서 차감</b>됩니다. 송금을 마친 뒤 승인해 주세요.</div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th class="text-end">금액</th><th>사유</th><th>상태</th><th>신청일</th><th></th></tr></thead>
                <tbody>${refundRows || '<tr><td colspan="6" class="text-center text-muted py-4">환불 신청이 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>`;
}

function showCreditCharge(merchantId, merchantName) {
    resetFormModalFooter(false);
    document.getElementById('formModalBody').innerHTML = `
        <h6 class="fw-bold mb-3">${escapeHtml(merchantName)} 광고비 충전</h6>
        <label class="form-label small fw-bold">충전 금액</label>
        <div class="input-group mb-3">
            <input type="number" class="form-control" id="creditAmount" min="1" step="10000" placeholder="예) 500000">
            <span class="input-group-text">원</span>
        </div>
        <label class="form-label small fw-bold">메모</label>
        <input class="form-control mb-3" id="creditMemo" maxlength="200" placeholder="입금자명 · 입금일 등">
        <div id="creditResult"></div>
        <button class="btn btn-primary w-100" onclick="submitCreditCharge(${merchantId})">
            <i class="fas fa-plus me-1"></i>충전 반영</button>`;
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

async function submitCreditCharge(merchantId) {
    const amount = parseFloat(document.getElementById('creditAmount').value);
    if (!amount || amount <= 0) {
        document.getElementById('creditResult').innerHTML =
            '<div class="alert alert-danger py-2 small">충전 금액을 입력해주세요.</div>';
        return;
    }
    try {
        await apiPost(`/api/admin/merchants/${merchantId}/ad-credit/charge`, {
            amount, memo: document.getElementById('creditMemo').value.trim() || null,
        });
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        navigate('admin-ad-credits');
    } catch (e) {
        document.getElementById('creditResult').innerHTML =
            `<div class="alert alert-danger py-2 small">${escapeHtml(e.message)}</div>`;
    }
}

async function showCreditLedger(merchantId, merchantName) {
    resetFormModalFooter(false);
    document.getElementById('formModalBody').innerHTML = adpayLoadingMarkup('내역을 불러오는 중입니다');
    new bootstrap.Modal(document.getElementById('formModal')).show();
    try {
        const d = await apiGet(`/api/admin/merchants/${merchantId}/ad-credit`);
        document.getElementById('formModalBody').innerHTML = `
            <h6 class="fw-bold mb-1">${escapeHtml(merchantName)} 크레딧 원장</h6>
            <div class="mb-3 small">현재 잔액 <b>${Number(d.balance).toLocaleString()}원</b>
                ${d.balance_matches === false
                    ? `<span class="badge bg-danger ms-2">원장 합계 ${Number(d.ledger_total).toLocaleString()}원과 불일치</span>`
                    : ''}</div>
            <div class="table-responsive" style="max-height:55vh;overflow:auto">
                <table class="table table-sm table-hover align-middle">${CREDIT_LEDGER_HEAD}
                <tbody>${creditLedgerRows(d.ledger) || '<tr><td colspan="5" class="text-center text-muted py-4">내역이 없습니다</td></tr>'}</tbody>
                </table></div>`;
    } catch (e) {
        document.getElementById('formModalBody').innerHTML =
            `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

async function processRefund(refundId, action) {
    const isApprove = action === 'approve';
    const memo = prompt(isApprove
        ? '송금을 마치셨나요? 처리 메모를 남겨주세요 (선택)'
        : '반려 사유를 입력해주세요 (매장에 표시됩니다)');
    if (memo === null) return;
    if (isApprove && !confirm('승인하면 매장 잔액에서 즉시 차감됩니다.\n계속할까요?')) return;
    try {
        await apiPost(`/api/admin/ad-credit-refunds/${refundId}/${action}`, { memo });
        navigate('admin-ad-credits');
    } catch (e) { alert(e.message); }
}

// ── OWNER: 광고비 충전 ──────────────────────────────────────
async function loadOwnerAdCredit(c, t) {
    t.textContent = '광고비';
    c.innerHTML = adpayLoadingMarkup('잔액을 불러오는 중입니다');
    try {
        c.innerHTML = ownerCreditMarkup(await apiGet('/api/owner/ad/credit'));
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function ownerCreditMarkup(d) {
    const refundRows = (d.refunds || []).map(f => `<tr>
        <td class="small text-muted">${escapeHtml(f.created_at || '')}</td>
        <td class="text-end fw-bold">${Number(f.amount).toLocaleString()}원</td>
        <td><span class="badge bg-${f.status === 'pending' ? 'warning text-dark' : (f.status === 'approved' ? 'success' : 'secondary')}">${escapeHtml(f.status_label)}</span>
            ${f.admin_memo ? `<div class="small text-muted mt-1">${escapeHtml(f.admin_memo)}</div>` : ''}</td>
    </tr>`).join('');

    let refundBox;
    if (d.has_pending_refund) {
        refundBox = `<div class="alert alert-info small mb-0"><i class="fas fa-clock me-1"></i>
            환불 신청이 접수되어 처리를 기다리고 있습니다.</div>`;
    } else if (d.refundable) {
        refundBox = `<button class="btn btn-outline-warning btn-sm" onclick="requestCreditRefund()">
            <i class="fas fa-arrow-right-from-bracket me-1"></i>잔액 전액 환불 신청</button>`;
    } else {
        refundBox = `<div class="small text-muted"><i class="fas fa-circle-info me-1"></i>
            환불은 잔액이 <b>${Number(d.min_refund_amount).toLocaleString()}원 이상</b>일 때 신청할 수 있습니다.</div>`;
    }

    return `
    <div class="card data-card mb-3">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-wallet me-2"></i>광고비 잔액</h5></div>
        <div class="card-body">
            <div class="display-6 fw-bold mb-2">${Number(d.balance).toLocaleString()}<span class="fs-5 ms-1">원</span></div>
            <div class="alert alert-light border small">
                <i class="fas fa-info-circle text-primary me-1"></i>
                플랜에 포함된 집행량을 넘겨 광고를 더 주문할 때 이 잔액에서 차감됩니다.
                <b>충전은 관리자에게 입금 후 요청</b>해 주세요. 반영되면 아래 내역에 표시됩니다.
            </div>
            ${refundBox}
        </div>
    </div>

    <div class="card data-card mb-3">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-list me-2"></i>사용 내역</h5></div>
        <div class="card-body">
            <div class="table-responsive"><table class="table table-hover align-middle">${CREDIT_LEDGER_HEAD}
                <tbody>${creditLedgerRows(d.ledger) || '<tr><td colspan="5" class="text-center text-muted py-4">아직 내역이 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>

    ${(d.refunds || []).length ? `
    <div class="card data-card">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-arrow-right-from-bracket me-2"></i>환불 신청 이력</h5></div>
        <div class="card-body">
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>신청일</th><th class="text-end">금액</th><th>상태</th></tr></thead>
                <tbody>${refundRows}</tbody>
            </table></div>
        </div>
    </div>` : ''}`;
}

async function requestCreditRefund() {
    const reason = prompt('환불 사유를 입력해주세요 (선택)');
    if (reason === null) return;
    if (!confirm('남은 잔액 전액을 환불 신청합니다.\n계속할까요?')) return;
    try {
        await apiPost('/api/owner/ad/credit/refund', { reason });
        navigate('owner-ad-credit');
    } catch (e) { alert(e.message); }
}

// ─── ADMIN: 광고 자동 집행 ─────────────────────────────────
let dispatchDate = '';

const DISPATCH_STATUS_BADGE = {
    pending: ['secondary', 'clock'],
    dry_run: ['info text-dark', 'vial'],
    sent: ['primary', 'paper-plane'],
    running: ['primary', 'spinner'],
    done: ['success', 'circle-check'],
    stopped: ['dark', 'circle-stop'],
    failed: ['danger', 'circle-exclamation'],
    skipped: ['warning text-dark', 'pause'],
    manual_queued: ['secondary', 'hand'],
    manual_done: ['success', 'user-check'],
};

function dispatchStatusBadge(d) {
    const [cls, icon] = DISPATCH_STATUS_BADGE[d.status] || ['secondary', 'circle'];
    return `<span class="badge bg-${cls}"><i class="fas fa-${icon} me-1"></i>${escapeHtml(d.status_label)}</span>`;
}

function todayIso() {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`;
}

async function loadAdminAdDispatch(c, t) {
    t.textContent = '광고 자동 집행';
    c.innerHTML = adpayLoadingMarkup('집행 계획을 계산하는 중입니다');
    if (!dispatchDate) dispatchDate = todayIso();
    try {
        const qs = `?date=${encodeURIComponent(dispatchDate)}`;
        const [plan, history, manual] = await Promise.all([
            apiGet('/api/admin/ad-dispatch/preview' + qs),
            apiGet('/api/admin/ad-dispatch' + qs),
            apiGet('/api/admin/ad-dispatch/manual-queue' + qs),
        ]);
        c.innerHTML = dispatchMarkup(plan, history, manual);
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function dispatchMarkup(plan, history, manual) {
    const labels = plan.skip_reason_labels || {};
    const planRows = (plan.items || []).map(i => {
        const willRun = i.action === 'dispatch';
        return `<tr class="${willRun ? '' : 'text-muted'}">
            <td>${escapeHtml(i.merchant_name)}</td>
            <td><span class="badge bg-light text-dark border">${escapeHtml(i.ad_type_label)}</span></td>
            <td class="text-end">${i.target}</td>
            <td class="small">${i.keywords && i.keywords.length ? escapeHtml(i.keywords.join(', ')) : '-'}</td>
            <td class="text-end">${Number(i.unit_price).toLocaleString()}</td>
            <td class="text-end fw-bold">${willRun ? Number(i.est_cost).toLocaleString() : '-'}</td>
            <td>${willRun
                ? '<span class="badge bg-success"><i class="fas fa-play me-1"></i>집행 예정</span>'
                : `<span class="badge bg-warning text-dark"><i class="fas fa-pause me-1"></i>${escapeHtml(labels[i.skip_reason] || i.skip_reason || '보류')}</span>`}</td>
        </tr>`;
    }).join('');

    const actualCell = (d) => {
        if (d.reward_count == null && d.delivered_count == null) {
            return '<span class="text-muted small">미확인</span>';
        }
        const rewarded = Number(d.reward_count || 0).toLocaleString();
        const delivered = d.delivered_count == null ? null : Number(d.delivered_count).toLocaleString();
        return `<span class="fw-bold">${rewarded}</span>`
            + (delivered ? `<div class="small text-muted">요청반영 ${delivered}</div>` : '');
    };

    const histRows = (history.dispatches || []).map(d => `<tr>
        <td>${escapeHtml(d.merchant_name || '-')}</td>
        <td><span class="badge bg-light text-dark border">${escapeHtml(d.ad_type_label)}</span></td>
        <td class="text-end">${d.requested_count}</td>
        <td class="text-end">${actualCell(d)}</td>
        <td class="small">${escapeHtml(d.keyword || '-')}${
            d.keyword_count ? `<div class="text-muted">키워드 ${d.keyword_count}개</div>` : ''}</td>
        <td>${dispatchStatusBadge(d)}${d.dry_run ? ' <span class="badge bg-light text-dark border">미전송</span>' : ''}
            ${d.external_status ? `<div class="small text-muted mt-1">리워드팝: ${escapeHtml(d.external_status)}</div>` : ''}
            ${d.skip_reason ? `<div class="small text-muted mt-1">${escapeHtml(d.skip_reason_label)}</div>` : ''}
            ${d.error_message ? `<div class="small text-danger mt-1">${escapeHtml(d.error_message)}</div>` : ''}</td>
        <td class="small text-muted">${escapeHtml(d.external_order_id || '-')}</td>
        <td class="text-nowrap">
            ${d.retryable ? `<button class="btn btn-sm btn-outline-primary" onclick="retryDispatch(${d.id})"><i class="fas fa-rotate-right"></i></button>` : ''}
            ${d.request_json ? `<button class="btn btn-sm btn-outline-secondary ms-1" onclick="showDispatchRequest(${d.id})" title="보낼 요청 내용"><i class="fas fa-code"></i></button>` : ''}
        </td>
    </tr>`).join('');

    window._dispatchHistory = history.dispatches || [];

    const modeBanner = plan.dry_run
        ? `<div class="alert alert-info small mb-3"><i class="fas fa-vial me-1"></i>
             <b>드라이런 상태입니다.</b> 실행해도 리워드팝에 실제 주문이 나가지 않고,
             어떤 요청이 나갈지만 기록됩니다. 실집행하려면 리워드팝 연동 설정에서 드라이런을 끄세요.</div>`
        : `<div class="alert alert-warning small mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
             <b>실집행 상태입니다.</b> 실행하면 리워드팝에 실제 주문이 접수되고 포인트가 차감됩니다.</div>`;

    const offBanner = plan.integration_enabled ? '' :
        `<div class="alert alert-secondary small mb-3"><i class="fas fa-plug me-1"></i>
           리워드팝 연동이 꺼져 있어 모든 집행이 보류됩니다. 연동 설정에서 켜주세요.</div>`;

    // 리워드팝 공식 API는 플레이스 미션 전용이다. 오해를 줄이려고 화면에 못박아 둔다.
    const scopeNotice = `<div class="alert alert-light border small mb-3"><i class="fas fa-circle-info me-1"></i>
        <b>자동 전송 대상은 플레이스 방문 뿐입니다.</b>
        블로그 배포(클로 블로그)는 리워드팝에 상품과 단가는 있지만 <b>등록 API가 없어</b>
        자동 전송이 불가능합니다 &mdash; 아래 <b>블로그 수동 접수</b> 카드에서 오늘 접수할 수량을
        확인하고, 리워드팝 어드민에서 접수한 뒤 완료 처리해주세요. 완료 처리하면 진도표와
        기간 집계에 플레이스와 똑같이 반영됩니다.
        클로 플러스는 2026-09-01부터 신규 접수가 중단됐습니다.</div>`;

    const basisLabel = plan.balance_basis === 'supply_price' ? '리워드팝 공급 단가 기준'
        : plan.balance_basis === 'sale_price' ? 'ADPAY 판매 단가로 추정(공급 단가 조회 실패)'
        : '';
    let balanceBanner = '';
    if (plan.balance_error) {
        balanceBanner = `<div class="alert alert-warning small mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
            <b>포인트 잔액을 확인하지 못했습니다.</b> ${escapeHtml(plan.balance_error)}<br>
            잔액 점검 없이 진행됩니다 — 실행 전 리워드팝에서 잔액을 직접 확인해주세요.</div>`;
    } else if (plan.low_balance) {
        balanceBanner = `<div class="alert alert-danger small mb-3"><i class="fas fa-ban me-1"></i>
            <b>리워드팝 포인트가 부족해 오늘 집행이 전부 보류됐습니다.</b><br>
            필요 ${Number(plan.required_points || 0).toLocaleString()}P ·
            잔액 ${Number(plan.balance || 0).toLocaleString()}P
            ${basisLabel ? `<span class="text-muted">(${escapeHtml(basisLabel)})</span>` : ''}<br>
            포인트를 충전한 뒤 다시 실행하면 됩니다. 같은 건이 두 번 나가지는 않습니다.</div>`;
    } else if (plan.balance_checked && plan.required_points != null) {
        balanceBanner = `<div class="alert alert-light border small mb-3"><i class="fas fa-coins me-1"></i>
            리워드팝 잔액 ${Number(plan.balance || 0).toLocaleString()}P ·
            오늘 필요 ${Number(plan.required_points).toLocaleString()}P
            ${basisLabel ? `<span class="text-muted">(${escapeHtml(basisLabel)})</span>` : ''}</div>`;
    }

    return `
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-paper-plane me-2"></i>오늘 집행 계획</h5>
            <div class="d-flex gap-2 align-items-center">
                <input type="date" class="form-control form-control-sm" style="width:auto"
                    id="dispatchDate" value="${escapeHtml(plan.date)}" onchange="changeDispatchDate(this.value)">
            </div>
        </div>
        <div class="card-body">
            ${offBanner}${scopeNotice}${modeBanner}${balanceBanner}
            <div class="row g-3 mb-3">
                ${kpiCard('집행 예정', `${plan.dispatch_count}건`, 'fas fa-play', 'success')}
                ${kpiCard('총 집행 수량', `${Number(plan.total_count).toLocaleString()}`, 'fas fa-layer-group', 'primary')}
                ${kpiCard('예상 비용', `${Number(plan.est_total_cost).toLocaleString()}원`, 'fas fa-won-sign', 'warning')}
                ${plan.balance == null ? '' :
                    kpiCard('리워드팝 잔액', `${Number(plan.balance).toLocaleString()}P`, 'fas fa-coins',
                        plan.low_balance ? 'danger' : 'secondary')}
            </div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th>광고</th><th class="text-end">목표</th><th>키워드</th>
                    <th class="text-end">단가</th><th class="text-end">예상 비용</th><th>처리</th></tr></thead>
                <tbody>${planRows || '<tr><td colspan="7" class="text-center text-muted py-4">대상이 없습니다</td></tr>'}</tbody>
            </table></div>
            <div class="d-flex gap-2 flex-wrap mt-3">
                <button class="btn btn-outline-primary btn-sm" onclick="navigate('admin-ad-dispatch')">
                    <i class="fas fa-rotate me-1"></i>다시 계산</button>
                <button class="btn btn-info btn-sm text-dark" onclick="runDispatch(true)">
                    <i class="fas fa-vial me-1"></i>드라이런 실행</button>
                <button class="btn btn-primary btn-sm" onclick="runDispatch(false)" ${plan.integration_enabled ? '' : 'disabled'}>
                    <i class="fas fa-paper-plane me-1"></i>지금 집행</button>
                <button class="btn btn-outline-secondary btn-sm" onclick="refreshDispatchStatus()">
                    <i class="fas fa-arrows-rotate me-1"></i>상태 갱신</button>
            </div>
            <div id="dispatchResult" class="mt-3"></div>
        </div>
    </div>

    ${manualQueueMarkup(manual)}

    <div class="card data-card mb-3" id="dispatchReportCard">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-chart-column me-2"></i>기간별 집행·비용</h5>
            <div class="d-flex gap-2 align-items-center">
                <input type="date" class="form-control form-control-sm" style="width:auto" id="reportStart">
                <span class="text-muted small">~</span>
                <input type="date" class="form-control form-control-sm" style="width:auto" id="reportEnd">
                <button class="btn btn-sm btn-outline-primary" onclick="loadDispatchReport()">조회</button>
            </div>
        </div>
        <div class="card-body" id="dispatchReportBody">
            <div class="text-muted small">기간을 정하고 조회를 눌러주세요. 드라이런과 실패·보류는 실적에서 빠집니다.</div>
        </div>
    </div>

    <div class="card data-card">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-list-check me-2"></i>집행 기록 (${escapeHtml(history.date)})</h5></div>
        <div class="card-body">
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th>광고</th><th class="text-end">요청 수량</th>
                    <th class="text-end">실적립</th><th>키워드</th>
                    <th>상태</th><th>외부 주문번호</th><th></th></tr></thead>
                <tbody>${histRows || '<tr><td colspan="8" class="text-center text-muted py-4">기록이 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>`;
}

async function refreshDispatchStatus() {
    const box = document.getElementById('dispatchResult');
    box.innerHTML = '<div class="alert alert-secondary py-2 mb-0 small"><i class="fas fa-spinner fa-spin me-1"></i>상태를 확인하는 중...</div>';
    try {
        const r = await apiPost('/api/admin/ad-dispatch/refresh-status', { execution_date: dispatchDate });
        if (r.spec_missing) {
            box.innerHTML = `<div class="alert alert-warning py-2 mb-0 small">${escapeHtml(r.detail)}</div>`;
            return;
        }
        const summary = `확인 ${r.checked}건 · 갱신 ${r.updated}건 · 변화 없음 ${r.unchanged}건`;
        showToast(summary, true);
        box.innerHTML = `<div class="alert alert-success py-2 mb-0 small">${escapeHtml(summary)}</div>`;
        if (r.updated) setTimeout(() => navigate('admin-ad-dispatch'), 1200);
    } catch (e) {
        box.innerHTML = `<div class="alert alert-danger py-2 mb-0 small">${escapeHtml(e.message)}</div>`;
    }
}

async function loadDispatchReport() {
    const body = document.getElementById('dispatchReportBody');
    const start = document.getElementById('reportStart').value;
    const end = document.getElementById('reportEnd').value;
    body.innerHTML = adpayLoadingMarkup('집계하는 중입니다');
    try {
        const qs = [];
        if (start) qs.push(`start=${encodeURIComponent(start)}`);
        if (end) qs.push(`end=${encodeURIComponent(end)}`);
        const r = await apiGet('/api/admin/ad-dispatch/report' + (qs.length ? '?' + qs.join('&') : ''));
        body.innerHTML = dispatchReportMarkup(r);
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger mb-0">${escapeHtml(e.message)}</div>`;
    }
}

function dispatchReportMarkup(r) {
    const actual = (row) => row.measured
        ? `${Number(row.rewarded).toLocaleString()}`
        : '<span class="text-muted">미확인</span>';

    const typeRows = (r.by_ad_type || []).map(t => `<tr>
        <td><span class="badge bg-light text-dark border">${escapeHtml(t.ad_type_label)}</span></td>
        <td class="text-end">${Number(t.count).toLocaleString()}</td>
        <td class="text-end">${actual(t)}</td>
        <td class="text-end fw-bold">${Number(t.cost).toLocaleString()}원</td>
    </tr>`).join('');

    const merchantRows = (r.by_merchant || []).map(m => `<tr>
        <td>${escapeHtml(m.merchant_name)}</td>
        <td class="text-end">${Number(m.count).toLocaleString()}</td>
        <td class="text-end">${actual(m)}</td>
        <td class="text-end fw-bold">${Number(m.cost).toLocaleString()}원</td>
    </tr>`).join('');

    const problemRows = (r.problems || []).map(p => `
        <span class="badge bg-warning text-dark me-1 mb-1">${escapeHtml(p.label)} ${p.count}건</span>`).join('');

    return `
    <div class="row g-3 mb-3">
        ${kpiCard('요청 수량', `${Number(r.total_count).toLocaleString()}`, 'fas fa-layer-group', 'primary')}
        ${kpiCard('실적립 수량', `${Number(r.total_rewarded || 0).toLocaleString()}`, 'fas fa-circle-check', 'success')}
        ${kpiCard('집행 비용', `${Number(r.total_cost).toLocaleString()}원`, 'fas fa-won-sign', 'warning')}
        ${kpiCard('집행 건', `${Number(r.total_dispatches).toLocaleString()}건`, 'fas fa-paper-plane', 'secondary')}
    </div>
    <div class="small text-muted mb-3">${escapeHtml(r.start)} ~ ${escapeHtml(r.end)}</div>
    <div class="alert alert-light border small mb-3"><i class="fas fa-circle-info me-1"></i>
        <b>요청 수량</b>은 우리가 리워드팝에 보낸 수, <b>실적립 수량</b>은 리워드팝이 실제로 적립한 수입니다.
        상태 갱신을 받아온 ${Number(r.measured_dispatches || 0).toLocaleString()}건만 실적립에 잡히므로,
        방금 나간 건은 아직 0으로 보일 수 있습니다.
        ${r.stopped_dispatches ? `<br><b class="text-danger">중지된 집행 ${Number(r.stopped_dispatches).toLocaleString()}건</b>이 포함되어 있습니다.` : ''}</div>
    ${problemRows ? `<div class="mb-3"><div class="small fw-bold mb-1">나가지 못한 건</div>${problemRows}</div>` : ''}
    <div class="row g-3">
        <div class="col-lg-5">
            <div class="fw-bold small mb-2">광고 종류별</div>
            <div class="table-responsive"><table class="table table-sm table-hover align-middle">
                <thead><tr><th>광고</th><th class="text-end">요청</th><th class="text-end">실적립</th><th class="text-end">비용</th></tr></thead>
                <tbody>${typeRows || '<tr><td colspan="4" class="text-center text-muted py-3">집행 없음</td></tr>'}</tbody>
            </table></div>
        </div>
        <div class="col-lg-7">
            <div class="fw-bold small mb-2">가맹점별</div>
            <div class="table-responsive" style="max-height:40vh;overflow:auto">
                <table class="table table-sm table-hover align-middle">
                <thead><tr><th>가맹점</th><th class="text-end">요청</th><th class="text-end">실적립</th><th class="text-end">비용</th></tr></thead>
                <tbody>${merchantRows || '<tr><td colspan="4" class="text-center text-muted py-3">집행 없음</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>`;
}

function changeDispatchDate(value) {
    dispatchDate = value || todayIso();
    navigate('admin-ad-dispatch');
}

async function runDispatch(dryRun) {
    const label = dryRun ? '드라이런' : '실제 집행';
    if (!dryRun && !confirm('리워드팝에 실제 주문이 접수되고 포인트가 차감됩니다.\n계속할까요?')) return;
    const box = document.getElementById('dispatchResult');
    box.innerHTML = `<div class="alert alert-secondary py-2 mb-0 small"><i class="fas fa-spinner fa-spin me-1"></i>${label} 실행 중...</div>`;
    try {
        const res = await apiPost('/api/admin/ad-dispatch/run', {
            execution_date: dispatchDate,
            dry_run: dryRun,
        });
        const ok = res.failed_count === 0;
        const summary = `${label} 완료 — 전송 ${res.dispatched_count}건 · 실패 ${res.failed_count}건 · 보류 ${res.skipped_count}건`;
        showToast(summary, ok);
        if (res.low_balance) {
            showToast('리워드팝 포인트가 부족해 전부 보류됐습니다. 충전 후 다시 실행해주세요.', false);
        }
        box.innerHTML = `<div class="alert alert-${ok ? 'success' : 'warning'} py-2 mb-0 small">
            <i class="fas fa-circle-check me-1"></i>${escapeHtml(summary)}</div>`;
        setTimeout(() => navigate('admin-ad-dispatch'), 1200);
    } catch (e) {
        box.innerHTML = `<div class="alert alert-danger py-2 mb-0 small">${escapeHtml(e.message)}</div>`;
    }
}

async function retryDispatch(id) {
    if (!confirm('이 건을 다시 집행합니다. 실제 주문이 나갑니다.\n계속할까요?')) return;
    try {
        await apiPost(`/api/admin/ad-dispatch/${id}/retry`, {});
        navigate('admin-ad-dispatch');
    } catch (e) { alert(e.message); }
}

function showDispatchRequest(id) {
    const row = (window._dispatchHistory || []).find(d => d.id === id);
    if (!row) return;
    resetFormModalFooter(false);
    let pretty = row.request_json;
    try { pretty = JSON.stringify(JSON.parse(row.request_json), null, 2); } catch (e) { /* 원본 그대로 */ }
    document.getElementById('formModalBody').innerHTML = `
        <h6 class="fw-bold mb-2">리워드팝에 보낼 요청 내용</h6>
        <div class="small text-muted mb-2">리워드팝 공식 <code>POST /ads</code> (CreateAdDto) 규격 그대로 보낸 값입니다.</div>
        <pre class="bg-light border rounded p-3" style="font-size:.8rem;max-height:50vh;overflow:auto">${escapeHtml(pretty)}</pre>`;
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

// ─── 블로그 수동 접수 큐 ────────────────────────────────────
//
// 리워드팝에 블로그 등록 API 가 없어서 전송은 사람이 한다. 시스템은 최고관리자가
// 정한 월 목표를 일 단위로 쪼개 "오늘 몇 건" 만 알려주고, 완료 처리된 건만
// 진도표·집계에 실적으로 넣는다.

function manualProgressBar(item) {
    const monthly = Number(item.monthly_target || 0);
    if (monthly <= 0) return '<span class="text-muted small">월 목표 없음</span>';
    const done = Number(item.month_done || 0);
    const expected = Number(item.month_expected || 0);
    const pct = Math.min(100, Math.round(done / monthly * 100));
    // 오늘까지 쌓여 있어야 할 양보다 적으면 빨간색 — 밀린 걸 한눈에 보이게 한다
    const behind = done < expected;
    return `<div style="min-width:150px">
        <div class="progress" style="height:6px">
            <div class="progress-bar bg-${behind ? 'danger' : 'success'}" style="width:${pct}%"></div>
        </div>
        <div class="small ${behind ? 'text-danger' : 'text-muted'}" style="font-size:.72rem">
            이번 달 ${done.toLocaleString()} / ${monthly.toLocaleString()}건
            ${behind ? ` · 오늘까지 ${expected.toLocaleString()}건 필요` : ''}
        </div>
        <div class="text-muted" style="font-size:.68rem">${escapeHtml(item.daily_description || '')}</div>
    </div>`;
}

// 리워드팝 공급 단가(원가)와 마진. 단가를 못 읽었으면 그 사실을 그대로 보여준다
// — 빈칸으로 두면 "원가가 0원"으로 오해할 수 있다.
function manualCostCell(item) {
    const sale = `<div class="fw-bold">${Number(item.est_cost).toLocaleString()}원</div>`;
    if (item.supply_unit_price == null) {
        return sale + '<div class="small text-muted">원가 미확인</div>';
    }
    const points = Number(item.required_points || 0);
    const margin = Number(item.margin || 0);
    return sale + `<div class="small text-muted">원가 ${points.toLocaleString()}P</div>
        <div class="small ${margin < 0 ? 'text-danger fw-bold' : 'text-success'}">
            마진 ${margin.toLocaleString()}원${item.supply_ambiguous ? ' <i class="fas fa-triangle-exclamation" title="이 매체에 단가가 여러 개라 가장 높은 값으로 계산했습니다"></i>' : ''}</div>`;
}

function manualQueueMarkup(manual) {
    if (!manual) return '';
    const labels = manual.skip_reason_labels || {};
    window._manualQueue = manual.items || [];

    const rows = (manual.items || []).map(i => {
        const key = `${i.merchant_id}|${i.ad_type}`;
        let actionCell, statusCell;
        if (i.state === 'done') {
            statusCell = `<span class="badge bg-success"><i class="fas fa-user-check me-1"></i>접수 완료 ${Number(i.done_count).toLocaleString()}건</span>
                ${i.external_order_id ? `<div class="small text-muted mt-1">주문번호 ${escapeHtml(i.external_order_id)}</div>` : ''}
                ${i.note ? `<div class="small text-muted mt-1">${escapeHtml(i.note)}</div>` : ''}`;
            actionCell = `<button class="btn btn-sm btn-outline-secondary" onclick="openManualComplete('${key}')" title="수량·메모 수정"><i class="fas fa-pen"></i></button>
                <button class="btn btn-sm btn-outline-danger ms-1" onclick="revertManualDispatch('${key}')" title="완료 처리 되돌리기"><i class="fas fa-rotate-left"></i></button>`;
        } else if (i.state === 'skip') {
            statusCell = `<span class="badge bg-light text-dark border"><i class="fas fa-minus me-1"></i>${escapeHtml(labels[i.skip_reason] || i.skip_reason || '해당 없음')}</span>`;
            actionCell = '';
        } else {
            statusCell = '<span class="badge bg-warning text-dark"><i class="fas fa-hand me-1"></i>접수 대기</span>';
            actionCell = `<button class="btn btn-sm btn-primary" onclick="openManualComplete('${key}')">
                <i class="fas fa-check me-1"></i>접수 완료</button>`;
        }
        return `<tr class="${i.state === 'skip' ? 'text-muted' : ''}">
            <td>${escapeHtml(i.merchant_name)}
                ${i.place_code ? `<div class="small text-muted">플레이스 ${escapeHtml(String(i.place_code))}</div>` : ''}</td>
            <td>${manualProgressBar(i)}</td>
            <td class="text-end fw-bold">${Number(i.target).toLocaleString()}</td>
            <td class="small">${i.keywords && i.keywords.length ? escapeHtml(i.keywords.join(', ')) : '<span class="text-muted">-</span>'}</td>
            <td class="text-end">${manualCostCell(i)}</td>
            <td>${statusCell}</td>
            <td class="text-nowrap">${actionCell}</td>
        </tr>`;
    }).join('');

    return `
    <div class="card data-card mb-3" id="manualQueueCard">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-pen-nib me-2 text-info"></i>블로그 수동 접수 (${escapeHtml(manual.date)})</h5>
            <span class="badge bg-light text-dark border">${escapeHtml(manual.manual_reason_label || '수동 접수')}</span>
        </div>
        <div class="card-body">
            <div class="alert alert-info small mb-3"><i class="fas fa-circle-info me-1"></i>
                월 목표를 그 달의 날짜 수로 나눠 <b>오늘 접수할 수량</b>을 계산한 목록입니다
                (일별 합계는 월 목표와 정확히 일치합니다). 리워드팝 어드민에서 접수한 뒤
                <b>접수 완료</b>를 눌러주세요. 누른 건만 진도표와 기간 집계에 실적으로 들어갑니다.</div>
            ${manual.supply_price_error ? `<div class="alert alert-warning small mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
                <b>리워드팝 공급 단가(클로 블로그 원가)를 읽지 못했습니다.</b> ${escapeHtml(manual.supply_price_error)}<br>
                접수 목록과 수량은 그대로 유효합니다. 원가와 필요 포인트만 비어 있습니다.</div>` : ''}
            ${manual.unpriced_count ? `<div class="alert alert-warning small mb-3"><i class="fas fa-circle-question me-1"></i>
                ${manual.unpriced_count}건은 리워드팝 공급 단가에 <code>cloblog</code> 항목이 없어 원가를 계산하지 못했습니다.
                리워드팝 계정에 클로 블로그 단가가 설정돼 있는지 확인해주세요.</div>` : ''}
            <div class="row g-3 mb-3">
                ${kpiCard('오늘 접수할 매장', `${manual.todo_count}곳`, 'fas fa-hand', 'warning')}
                ${kpiCard('오늘 접수할 수량', `${Number(manual.todo_total).toLocaleString()}건`, 'fas fa-layer-group', 'primary')}
                ${kpiCard('예상 매출', `${Number(manual.todo_cost).toLocaleString()}원`, 'fas fa-won-sign', 'secondary')}
                ${manual.required_points == null
                    ? kpiCard('접수 완료', `${Number(manual.done_total).toLocaleString()}건`, 'fas fa-user-check', 'success')
                    : kpiCard('필요 포인트', `${Number(manual.required_points).toLocaleString()}P`, 'fas fa-coins', 'info')}
            </div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th>이번 달 진행</th><th class="text-end">오늘 접수</th>
                    <th>추천 키워드</th><th class="text-end">판매가 / 원가</th><th>상태</th><th></th></tr></thead>
                <tbody>${rows || '<tr><td colspan="7" class="text-center text-muted py-4">대상이 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>`;
}

function openManualComplete(key) {
    const item = (window._manualQueue || []).find(i => `${i.merchant_id}|${i.ad_type}` === key);
    if (!item) return;
    resetFormModalFooter(true);
    document.getElementById('formModalBody').innerHTML = `
        <h6 class="fw-bold mb-1">${escapeHtml(item.merchant_name)} · ${escapeHtml(item.ad_type_label)}</h6>
        <div class="small text-muted mb-3">리워드팝 어드민에서 접수를 마친 뒤 저장해주세요. 저장한 수량이 진도표에 실적으로 들어갑니다.</div>
        ${item.keywords && item.keywords.length ? `<div class="alert alert-light border small py-2">
            추천 키워드: <b>${escapeHtml(item.keywords.join(', '))}</b></div>` : ''}
        <div class="mb-3">
            <label class="form-label">접수 수량</label>
            <input type="number" min="1" class="form-control" id="manualCount"
                value="${item.state === 'done' ? item.done_count : item.target}">
            <div class="form-text">오늘 자동 배분된 목표는 ${Number(item.target).toLocaleString()}건입니다. 실제로 접수한 수량을 넣어주세요.</div>
        </div>
        <div class="mb-3">
            <label class="form-label">리워드팝 주문번호 <span class="text-muted small">(선택)</span></label>
            <input type="text" maxlength="100" class="form-control" id="manualOrderId"
                value="${escapeHtml(item.external_order_id || '')}" placeholder="나중에 대조할 수 있게 남겨두면 좋습니다">
        </div>
        <div class="mb-1">
            <label class="form-label">메모 <span class="text-muted small">(선택)</span></label>
            <input type="text" maxlength="300" class="form-control" id="manualNote"
                value="${escapeHtml(item.note || '')}">
        </div>`;
    const btn = document.getElementById('formModalSave');
    if (btn) btn.onclick = () => submitManualComplete(item.merchant_id, item.ad_type);
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

async function submitManualComplete(merchantId, adType) {
    const count = parseInt(document.getElementById('manualCount').value, 10);
    if (!count || count < 1) { showToast('접수 수량은 1건 이상이어야 합니다', false); return; }
    try {
        await apiPost('/api/admin/ad-dispatch/manual-queue/complete', {
            merchant_id: merchantId,
            ad_type: adType,
            execution_date: dispatchDate,
            count: count,
            external_order_id: document.getElementById('manualOrderId').value.trim() || null,
            note: document.getElementById('manualNote').value.trim() || null,
        });
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        showToast(`접수 완료로 기록했습니다 — ${count.toLocaleString()}건`, true);
        navigate('admin-ad-dispatch');
    } catch (e) { showToast(e.message, false); }
}

async function revertManualDispatch(key) {
    const item = (window._manualQueue || []).find(i => `${i.merchant_id}|${i.ad_type}` === key);
    if (!item) return;
    if (!confirm(`${item.merchant_name} 의 접수 완료 처리를 되돌립니다.\n진도표 실적에서 빠집니다. 계속할까요?`)) return;
    try {
        await apiPost('/api/admin/ad-dispatch/manual-queue/revert', {
            merchant_id: item.merchant_id,
            ad_type: item.ad_type,
            execution_date: dispatchDate,
        });
        showToast('완료 처리를 되돌렸습니다', true);
        navigate('admin-ad-dispatch');
    } catch (e) { showToast(e.message, false); }
}

// ─── 광고 집행 키워드 (관리자 승인 / 매장 등록) ─────────────
const KEYWORD_STATUS_BADGE = {
    pending: ['warning text-dark', 'clock', '승인 대기'],
    approved: ['success', 'circle-check', '승인됨'],
    rejected: ['danger', 'circle-xmark', '반려됨'],
};

function keywordStatusBadge(k) {
    const [cls, icon, label] = KEYWORD_STATUS_BADGE[k.status] || ['secondary', 'circle', k.status];
    return `<span class="badge bg-${cls}"><i class="fas fa-${icon} me-1"></i>${escapeHtml(label)}</span>`;
}

function keywordAdTypeOptions(adTypes, selected) {
    const opts = [`<option value="" ${selected ? '' : 'selected'}>모든 광고 공통</option>`];
    (adTypes || []).forEach(t => {
        opts.push(`<option value="${escapeHtml(t.code)}" ${selected === t.code ? 'selected' : ''}>${escapeHtml(t.label)}</option>`);
    });
    return opts.join('');
}

// ── ADMIN: 키워드 승인 ──────────────────────────────────────
let adminKeywordData = null;
let adminKeywordFilter = '';

async function loadAdminAdKeywords(c, t) {
    t.textContent = '광고 키워드 승인';
    c.innerHTML = adpayLoadingMarkup('키워드를 불러오는 중입니다');
    try {
        const [data, merchants] = await Promise.all([
            apiGet('/api/admin/ad-keywords' + (adminKeywordFilter ? `?status=${adminKeywordFilter}` : '')),
            apiGet('/api/admin/merchants'),
        ]);
        adminKeywordData = data;
        c.innerHTML = adminKeywordMarkup(data, merchants);
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function adminKeywordMarkup(d, merchants) {
    const filters = [['', '전체'], ['pending', '승인 대기'], ['approved', '승인됨'], ['rejected', '반려됨']]
        .map(([code, label]) => `<button class="btn btn-sm ${adminKeywordFilter === code ? 'btn-primary' : 'btn-outline-secondary'}"
            onclick="filterAdminKeywords('${code}')">${escapeHtml(label)}</button>`).join('');

    const rows = (d.keywords || []).map(k => `<tr>
        <td>${escapeHtml(k.merchant_name)}</td>
        <td class="fw-bold">${escapeHtml(k.keyword)}</td>
        <td><span class="badge bg-light text-dark border">${escapeHtml(k.ad_type_label)}</span></td>
        <td class="text-center">${k.priority}</td>
        <td>${keywordStatusBadge(k)}${k.reject_reason
            ? `<div class="small text-muted mt-1">${escapeHtml(k.reject_reason)}</div>` : ''}</td>
        <td class="small text-muted">${k.created_by_role === 'admin' ? '관리자' : '매장'}<br>${escapeHtml(k.created_at || '')}</td>
        <td class="text-nowrap">
            ${k.status !== 'approved' ? `<button class="btn btn-sm btn-success me-1" onclick="approveKeyword(${k.id})"><i class="fas fa-check"></i></button>` : ''}
            ${k.status !== 'rejected' ? `<button class="btn btn-sm btn-outline-warning me-1" onclick="rejectKeyword(${k.id})"><i class="fas fa-ban"></i></button>` : ''}
            <button class="btn btn-sm btn-outline-danger" onclick="deleteAdminKeyword(${k.id})"><i class="fas fa-trash"></i></button>
        </td>
    </tr>`).join('');

    const merchantOptions = (merchants || [])
        .filter(m => m.is_active)
        .map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');

    return `
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-key me-2"></i>매장 광고 키워드</h5>
            ${d.pending_count > 0
                ? `<span class="badge bg-warning text-dark">승인 대기 ${d.pending_count}건</span>`
                : '<span class="badge bg-success">대기 중인 승인 없음</span>'}
        </div>
        <div class="card-body">
            <div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
                매장이 등록한 키워드는 <b>승인해야 자동 집행에 쓰입니다.</b>
                승인된 키워드가 하나도 없는 매장은 그날 집행이 보류됩니다.</div>
            <div class="d-flex gap-2 mb-3 flex-wrap">${filters}</div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>가맹점</th><th>키워드</th><th>광고 종류</th><th class="text-center">순위</th><th>상태</th><th>등록</th><th>액션</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="7" class="text-center text-muted py-4">등록된 키워드가 없습니다</td></tr>'}</tbody>
            </table></div>
        </div>
    </div>

    <div class="card data-card">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-plus me-2"></i>관리자 직접 등록</h5></div>
        <div class="card-body">
            <div class="small text-muted mb-3">관리자가 등록한 키워드는 승인 절차 없이 바로 사용됩니다.</div>
            <div class="row g-2 align-items-end">
                <div class="col-md-4">
                    <label class="form-label small fw-bold">가맹점</label>
                    <select class="form-select" id="akMerchant">${merchantOptions}</select>
                </div>
                <div class="col-md-3">
                    <label class="form-label small fw-bold">키워드</label>
                    <input class="form-control" id="akKeyword" maxlength="60" placeholder="예) 지역명 + 업종명">
                </div>
                <div class="col-md-3">
                    <label class="form-label small fw-bold">광고 종류</label>
                    <select class="form-select" id="akAdType">${keywordAdTypeOptions(d.ad_types, '')}</select>
                </div>
                <div class="col-md-2">
                    <button class="btn btn-primary w-100" onclick="addAdminKeyword()"><i class="fas fa-plus me-1"></i>추가</button>
                </div>
            </div>
            <div id="akResult" class="mt-3"></div>
        </div>
    </div>`;
}

function filterAdminKeywords(status) {
    adminKeywordFilter = status;
    navigate('admin-ad-keywords');
}

function showKeywordResult(boxId, ok, message) {
    const box = document.getElementById(boxId);
    if (!box) return;
    box.innerHTML = `<div class="alert alert-${ok ? 'success' : 'danger'} py-2 mb-0 small">
        <i class="fas fa-${ok ? 'circle-check' : 'circle-exclamation'} me-1"></i>${escapeHtml(message)}</div>`;
}

async function addAdminKeyword() {
    const merchantId = document.getElementById('akMerchant').value;
    const keyword = document.getElementById('akKeyword').value.trim();
    if (!merchantId) { showKeywordResult('akResult', false, '가맹점을 선택해주세요.'); return; }
    if (!keyword) { showKeywordResult('akResult', false, '키워드를 입력해주세요.'); return; }
    try {
        await apiPost(`/api/admin/merchants/${merchantId}/ad-keywords`, {
            keyword,
            ad_type: document.getElementById('akAdType').value,
        });
        navigate('admin-ad-keywords');
    } catch (e) {
        showKeywordResult('akResult', false, e.message);
    }
}

async function approveKeyword(id) {
    try {
        await apiPost(`/api/admin/ad-keywords/${id}/approve`, {});
        navigate('admin-ad-keywords');
    } catch (e) { alert(e.message); }
}

async function rejectKeyword(id) {
    const reason = prompt('반려 사유를 입력해주세요 (매장에 그대로 보입니다)');
    if (reason === null) return;
    try {
        await apiPost(`/api/admin/ad-keywords/${id}/reject`, { reason });
        navigate('admin-ad-keywords');
    } catch (e) { alert(e.message); }
}

async function deleteAdminKeyword(id) {
    if (!confirm('이 키워드를 삭제하시겠습니까?')) return;
    try {
        await apiDelete(`/api/admin/ad-keywords/${id}`);
        navigate('admin-ad-keywords');
    } catch (e) { alert(e.message); }
}

// ── OWNER: 광고 설정 (플레이스 방문 키워드 + 블로그 설정) ─────────────
async function loadOwnerAdSettings(c, t) {
    t.textContent = '광고 설정';
    c.innerHTML = adpayLoadingMarkup('광고 설정을 불러오는 중입니다');
    try {
        const [kwData, blogData] = await Promise.all([
            apiGet('/api/owner/ad/keywords'),
            apiGet('/api/owner/ad/blog-config').catch(() => null),
        ]);
        c.innerHTML = ownerAdSettingsMarkup(kwData, blogData);
        // 블로그 기존 값 채우기
        if (blogData) fillBlogConfigForm(blogData);
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function ownerAdSettingsMarkup(kwData, blogData) {
    return `
    <ul class="nav nav-tabs mb-3" id="adSettingsTabs">
        <li class="nav-item">
            <button class="nav-link active" data-tab="place" onclick="switchAdSettingsTab('place')">
                <i class="fas fa-map-marker-alt me-1"></i>플레이스 방문
            </button>
        </li>
        <li class="nav-item">
            <button class="nav-link" data-tab="blog" onclick="switchAdSettingsTab('blog')">
                <i class="fas fa-blog me-1"></i>블로그 배포
            </button>
        </li>
    </ul>
    <div id="adSettingsTabPlace">${ownerKeywordMarkup(kwData)}</div>
    <div id="adSettingsTabBlog" style="display:none">${ownerBlogConfigMarkup(blogData)}</div>`;
}

function switchAdSettingsTab(tab) {
    ['place','blog'].forEach(k => {
        const panel = document.getElementById(`adSettingsTab${k.charAt(0).toUpperCase()+k.slice(1)}`);
        if (panel) panel.style.display = (k === tab) ? '' : 'none';
    });
    document.querySelectorAll('#adSettingsTabs .nav-link').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === tab);
    });
}

// ── 블로그 설정 3단계 마법사 ─────────────────────────────────
let _blogStep = 1;
const _BLOG_STEPS = 3;

function ownerBlogConfigMarkup(d) {
    return `
    <div class="card data-card">
        <div class="card-header">
            <h5 class="mb-0"><i class="fas fa-blog me-2"></i>블로그 자동 접수 설정</h5>
            <div class="small text-muted mt-1">설정된 정보로 매월 첫 평일에 블로그 배포가 자동 접수됩니다.</div>
        </div>
        <div class="card-body">
            <!-- 단계 인디케이터 -->
            <div class="d-flex align-items-center mb-4" id="blogStepIndicator">
                ${[1,2,3].map(i=>`
                <div class="d-flex flex-column align-items-center" style="flex:1">
                    <div id="blogStepCircle${i}" class="rounded-circle d-flex align-items-center justify-content-center fw-bold mb-1"
                         style="width:32px;height:32px;font-size:.85rem;background:${i===1?'#0d6efd':'#dee2e6'};color:${i===1?'#fff':'#6c757d'};transition:all .3s">
                        ${i}
                    </div>
                    <div class="small text-center" style="font-size:.72rem;color:${i===1?'#0d6efd':'#6c757d'}">${['매장 기본 정보','키워드 설정','포스팅 설정'][i-1]}</div>
                </div>
                ${i<3?`<div style="flex:1;height:2px;background:#dee2e6;margin-bottom:20px" id="blogStepLine${i}"></div>`:''}
                `).join('')}
            </div>

            <!-- Step 1: 매장 기본 정보 -->
            <div id="blogStep1">
                <div class="mb-3">
                    <label class="form-label fw-bold">네이버 플레이스 URL <span class="text-danger">*</span></label>
                    <input class="form-control" id="blogPlaceUrl" placeholder="https://m.place.naver.com/restaurant/..." maxlength="500">
                    <div class="form-text text-muted mt-1" style="font-size:.78rem">
                        <i class="fas fa-circle-info me-1 text-primary"></i>
                        네이버 지도 앱 또는 모바일 웹에서 업체 검색 후 업체 상세 페이지 URL을 복사하세요.<br>
                        예시: <code>https://m.place.naver.com/restaurant/1750900108/home</code><br>
                        <span class="text-danger">PC 네이버 지도 URL(map.naver.com)은 사용 불가합니다.</span>
                        반드시 <b>m.place.naver.com</b>으로 시작하는 모바일 URL을 입력해야 합니다.<br>
                        네이버 앱에서는 업체명 우측 공유 버튼을 눌러 링크를 복사하세요.
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">업체명 <span class="text-danger">*</span></label>
                    <input class="form-control" id="blogPlaceName" placeholder="예) 홍대 강남돈까스" maxlength="100">
                </div>
                <div class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label fw-bold">매장 주소 <span class="text-muted fw-normal">(선택)</span></label>
                        <input class="form-control" id="blogStoreAddress" placeholder="예) 서울시 마포구 홍익로..." maxlength="200">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-bold">대표번호 <span class="text-muted fw-normal">(선택)</span></label>
                        <input class="form-control" id="blogStorePhone" placeholder="예) 02-1234-5678" maxlength="30">
                    </div>
                </div>
                <div class="d-flex justify-content-end mt-4">
                    <button class="btn btn-primary" onclick="blogWizardNext(1)">다음 <i class="fas fa-arrow-right ms-1"></i></button>
                </div>
            </div>

            <!-- Step 2: 키워드 설정 -->
            <div id="blogStep2" style="display:none">
                <div class="mb-3">
                    <label class="form-label fw-bold">필수 키워드 <span class="text-danger">*</span></label>
                    <input class="form-control" id="blogMainKeyword" placeholder="예) 강남 맛집" maxlength="100">
                    <div class="form-text">블로그 포스팅에 반드시 포함되어야 하는 핵심 키워드 1개를 입력하세요.</div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">작업 키워드 <span class="text-danger">*</span> <span class="text-muted fw-normal small">(1~5개, 쉼표로 구분)</span></label>
                    <input class="form-control" id="blogWorkKeywords" placeholder="예) 홍대 돈까스, 돈까스 맛집, 점심 맛집">
                    <div class="form-text">포스팅에 활용할 키워드를 쉼표(,)로 구분해 입력하세요. 최대 5개까지 가능합니다.</div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">해시태그 <span class="text-danger">*</span> <span class="text-muted fw-normal small">(5개 이상, 쉼표로 구분)</span></label>
                    <input class="form-control" id="blogTags" placeholder="예) 홍대맛집, 강남돈까스, 점심추천, 서울맛집, 돈까스">
                    <div class="form-text"># 없이 태그명만 입력하세요. 최소 5개 이상 입력해야 합니다.</div>
                </div>
                <div class="d-flex justify-content-between mt-4">
                    <button class="btn btn-outline-secondary" onclick="blogWizardPrev(2)"><i class="fas fa-arrow-left me-1"></i>이전</button>
                    <button class="btn btn-primary" onclick="blogWizardNext(2)">다음 <i class="fas fa-arrow-right ms-1"></i></button>
                </div>
            </div>

            <!-- Step 3: 포스팅 설정 -->
            <div id="blogStep3" style="display:none">
                <div class="mb-4">
                    <label class="form-label fw-bold">포스팅 유형 <span class="text-danger">*</span></label>
                    <div class="row g-2 mt-1">
                        ${[['INFO','정보성 포스팅','매장 정보, 메뉴, 위치 등을 소개하는 정보 중심 글'],
                           ['REVIEW','리뷰 포스팅','실제 방문·이용 후기 형식의 리뷰 글'],
                           ['FREE','자유 형식','블로거 자율 형식으로 작성']].map(([code,label,desc])=>`
                        <div class="col-md-4">
                            <label class="d-block border rounded-3 p-3 cursor-pointer" style="cursor:pointer" onclick="selectBlogPostType('${code}')">
                                <input type="radio" name="blogPostType" value="${code}" id="blogPostType${code}" class="form-check-input me-2">
                                <span class="fw-bold">${label}</span>
                                <div class="small text-muted mt-1">${desc}</div>
                            </label>
                        </div>`).join('')}
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">추가 링크 <span class="text-muted fw-normal">(선택)</span></label>
                    <input class="form-control" id="blogExtraLink" placeholder="예) 인스타그램, 홈페이지 URL 등" maxlength="500">
                    <div class="form-text">포스팅에 함께 언급할 추가 링크가 있으면 입력하세요.</div>
                </div>
                <div id="blogConfigResult" class="mt-2"></div>
                <div class="d-flex justify-content-between mt-4">
                    <button class="btn btn-outline-secondary" onclick="blogWizardPrev(3)"><i class="fas fa-arrow-left me-1"></i>이전</button>
                    <button class="btn btn-success" onclick="saveBlogConfig()"><i class="fas fa-save me-1"></i>설정 저장</button>
                </div>
            </div>
        </div>
    </div>`;
}

function selectBlogPostType(code) {
    const el = document.getElementById(`blogPostType${code}`);
    if (el) el.checked = true;
}

function fillBlogConfigForm(d) {
    const set = (id, val) => { const el = document.getElementById(id); if (el && val) el.value = val; };
    set('blogPlaceUrl', d.blog_place_url);
    set('blogPlaceName', d.blog_place_name);
    set('blogStoreAddress', d.blog_store_address);
    set('blogStorePhone', d.blog_store_phone);
    set('blogMainKeyword', d.blog_main_keyword);
    set('blogExtraLink', d.blog_extra_link);
    if (d.blog_work_keywords && d.blog_work_keywords.length)
        set('blogWorkKeywords', d.blog_work_keywords.join(', '));
    if (d.blog_tags && d.blog_tags.length)
        set('blogTags', d.blog_tags.join(', '));
    if (d.blog_post_type) selectBlogPostType(d.blog_post_type);
}

function blogWizardNext(currentStep) {
    if (currentStep === 1) {
        const url = (document.getElementById('blogPlaceUrl')?.value || '').trim();
        const name = (document.getElementById('blogPlaceName')?.value || '').trim();
        if (!url) { alert('네이버 플레이스 URL을 입력해주세요.'); return; }
        if (!url.includes('m.place.naver.com')) { alert('m.place.naver.com으로 시작하는 모바일 URL을 입력해주세요.'); return; }
        if (!name) { alert('업체명을 입력해주세요.'); return; }
    }
    if (currentStep === 2) {
        const main = (document.getElementById('blogMainKeyword')?.value || '').trim();
        const work = (document.getElementById('blogWorkKeywords')?.value || '').split(',').map(s=>s.trim()).filter(Boolean);
        const tags = (document.getElementById('blogTags')?.value || '').split(',').map(s=>s.trim()).filter(Boolean);
        if (!main) { alert('필수 키워드를 입력해주세요.'); return; }
        if (!work.length || work.length > 5) { alert('작업 키워드를 1~5개 입력해주세요.'); return; }
        if (tags.length < 5) { alert('해시태그를 5개 이상 입력해주세요.'); return; }
    }
    document.getElementById(`blogStep${currentStep}`).style.display = 'none';
    document.getElementById(`blogStep${currentStep+1}`).style.display = '';
    _blogStep = currentStep + 1;
    updateBlogStepIndicator(_blogStep);
}

function blogWizardPrev(currentStep) {
    document.getElementById(`blogStep${currentStep}`).style.display = 'none';
    document.getElementById(`blogStep${currentStep-1}`).style.display = '';
    _blogStep = currentStep - 1;
    updateBlogStepIndicator(_blogStep);
}

function updateBlogStepIndicator(active) {
    [1,2,3].forEach(i => {
        const circle = document.getElementById(`blogStepCircle${i}`);
        if (!circle) return;
        if (i < active) {
            circle.style.background = '#198754'; circle.style.color = '#fff';
            circle.innerHTML = '<i class="fas fa-check" style="font-size:.7rem"></i>';
        } else if (i === active) {
            circle.style.background = '#0d6efd'; circle.style.color = '#fff';
            circle.innerHTML = String(i);
        } else {
            circle.style.background = '#dee2e6'; circle.style.color = '#6c757d';
            circle.innerHTML = String(i);
        }
        if (i < 3) {
            const line = document.getElementById(`blogStepLine${i}`);
            if (line) line.style.background = i < active ? '#198754' : '#dee2e6';
        }
    });
}

async function saveBlogConfig() {
    const postType = document.querySelector('input[name="blogPostType"]:checked')?.value;
    if (!postType) { alert('포스팅 유형을 선택해주세요.'); return; }
    const work = (document.getElementById('blogWorkKeywords')?.value || '').split(',').map(s=>s.trim()).filter(Boolean);
    const tags = (document.getElementById('blogTags')?.value || '').split(',').map(s=>s.trim()).filter(Boolean);
    const payload = {
        blog_place_url: document.getElementById('blogPlaceUrl')?.value.trim() || null,
        blog_place_name: document.getElementById('blogPlaceName')?.value.trim() || null,
        blog_main_keyword: document.getElementById('blogMainKeyword')?.value.trim() || null,
        blog_work_keywords: work,
        blog_tags: tags,
        blog_post_type: postType,
        blog_store_address: document.getElementById('blogStoreAddress')?.value.trim() || null,
        blog_store_phone: document.getElementById('blogStorePhone')?.value.trim() || null,
        blog_extra_link: document.getElementById('blogExtraLink')?.value.trim() || null,
    };
    const resultEl = document.getElementById('blogConfigResult');
    try {
        await apiPut('/api/owner/ad/blog-config', payload);
        if (resultEl) resultEl.innerHTML = '<div class="alert alert-success"><i class="fas fa-circle-check me-1"></i>블로그 설정이 저장되었습니다. 매월 첫 평일에 자동 접수됩니다.</div>';
    } catch(e) {
        if (resultEl) resultEl.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function ownerKeywordMarkup(d) {
    const rows = (d.keywords || []).map(k => `<tr class="${k.usable ? '' : 'text-muted'}">
        <td class="fw-bold">${escapeHtml(k.keyword)}</td>
        <td><span class="badge bg-light text-dark border">${escapeHtml(k.ad_type_label)}</span></td>
        <td>${keywordStatusBadge(k)}${k.reject_reason
            ? `<div class="small text-danger mt-1"><i class="fas fa-comment-dots me-1"></i>${escapeHtml(k.reject_reason)}</div>` : ''}</td>
        <td class="text-center">
            <div class="form-check form-switch d-inline-block">
                <input class="form-check-input" type="checkbox" ${k.is_active ? 'checked' : ''}
                    onchange="toggleMyKeyword(${k.id}, this.checked)">
            </div>
        </td>
        <td class="text-nowrap">
            <button class="btn btn-sm btn-outline-danger" onclick="deleteMyKeyword(${k.id})"><i class="fas fa-trash"></i></button>
        </td>
    </tr>`).join('');

    const blockedNotice = d.dispatch_blocked
        ? `<div class="alert alert-warning mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
             <b>승인된 키워드가 없어 광고 자동 집행이 보류됩니다.</b>
             키워드를 등록하면 관리자 승인 후 집행이 시작됩니다.</div>`
        : `<div class="alert alert-success mb-3 py-2 small"><i class="fas fa-circle-check me-1"></i>
             사용 중인 키워드 ${d.usable_count}개로 광고가 집행됩니다.</div>`;

    return `
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-key me-2"></i>내 광고 키워드</h5>
            ${d.pending_count > 0 ? `<span class="badge bg-warning text-dark">승인 대기 ${d.pending_count}건</span>` : ''}
        </div>
        <div class="card-body">
            ${blockedNotice}
            <div class="row g-2 align-items-end mb-3">
                <div class="col-md-9">
                    <label class="form-label small fw-bold">키워드</label>
                    <input class="form-control" id="okKeyword" maxlength="60" placeholder="예) 지역명 + 업종명">
                </div>
                <div class="col-md-3">
                    <button class="btn btn-primary w-100" onclick="addMyKeyword()"><i class="fas fa-plus me-1"></i>등록</button>
                </div>
            </div>
            <div id="okResult" class="mb-3"></div>
            <div class="table-responsive"><table class="table table-hover align-middle">
                <thead><tr><th>키워드</th><th>광고 종류</th><th>상태</th><th class="text-center">사용</th><th></th></tr></thead>
                <tbody>${rows || '<tr><td colspan="5" class="text-center text-muted py-4">등록된 키워드가 없습니다</td></tr>'}</tbody>
            </table></div>
            <div class="small text-muted mt-2">
                키워드는 최대 ${d.max_per_merchant}개까지 등록할 수 있습니다.
                등록·수정한 키워드는 관리자 승인 후 집행에 쓰입니다.
            </div>
        </div>
    </div>`;
}

async function addMyKeyword() {
    const keyword = document.getElementById('okKeyword').value.trim();
    if (!keyword) { showKeywordResult('okResult', false, '키워드를 입력해주세요.'); return; }
    try {
        await apiPost('/api/owner/ad/keywords', {
            keyword,
            ad_type: 'place_traffic',
        });
        navigate('owner-ad-settings');
    } catch (e) {
        showKeywordResult('okResult', false, e.message);
    }
}

async function toggleMyKeyword(id, isActive) {
    try {
        await apiPut(`/api/owner/ad/keywords/${id}`, { is_active: isActive });
        navigate('owner-ad-settings');
    } catch (e) { alert(e.message); }
}

async function deleteMyKeyword(id) {
    if (!confirm('이 키워드를 삭제하시겠습니까?')) return;
    try {
        await apiDelete(`/api/owner/ad/keywords/${id}`);
        navigate('owner-ad-settings');
    } catch (e) { alert(e.message); }
}

// ─── ADMIN: 리워드팝 연동 ──────────────────────────────────
let rewardpopState = null;

async function loadAdminRewardpop(c, t) {
    t.textContent = '리워드팝 연동';
    c.innerHTML = adpayLoadingMarkup('연동 정보를 불러오는 중입니다');
    try {
        rewardpopState = await apiGet('/api/admin/rewardpop/config');
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
        return;
    }
    c.innerHTML = rewardpopMarkup(rewardpopState);
}

function rewardpopStatusBadge(d) {
    if (!d.configured) return '<span class="badge bg-secondary"><i class="fas fa-circle-minus me-1"></i>미연결</span>';
    if (!d.enabled) return '<span class="badge bg-warning text-dark"><i class="fas fa-pause me-1"></i>사용 중지</span>';
    // 화면 저장값(settings.dry_run)이 아니라, 환경변수까지 반영한 실효값을 본다.
    // 서버에 REWARDPOP_DRY_RUN 이 걸려 있으면 화면만 꺼져 있고 실제로는 안 나간다.
    const dry = d.effective_dry_run !== undefined ? d.effective_dry_run : d.settings.dry_run;
    if (dry) {
        return `<span class="badge bg-info text-dark"><i class="fas fa-vial me-1"></i>드라이런${
            d.dry_run_forced_by_env ? ' (환경변수)' : ''}</span>`;
    }
    return '<span class="badge bg-success"><i class="fas fa-circle-check me-1"></i>연동 중</span>';
}

function rewardpopMarkup(d) {
    const s = d.settings || {};
    const styles = (d.auth_styles || []).map(o =>
        `<option value="${escapeHtml(o.code)}" ${s.auth_style === o.code ? 'selected' : ''}>${escapeHtml(o.label)}</option>`
    ).join('');
    const envNotice = d.dry_run_forced_by_env
        ? `<div class="alert alert-warning small mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
             <b>서버 환경변수 <code>REWARDPOP_DRY_RUN</code> 이 화면 설정을 덮어쓰고 있습니다.</b><br>
             현재 실효 상태는 <b>${d.effective_dry_run ? '드라이런(실제 주문 안 나감)' : '실집행'}</b> 입니다.
             아래 드라이런 스위치를 바꿔도 이 값이 우선합니다 — 바꾸려면 배포 설정에서 해당 환경변수를 지우세요.</div>`
        : '';
    const missing = (d.missing_paths || []);
    const missingNotice = missing.length
        ? `<div class="alert alert-warning small mb-3"><i class="fas fa-triangle-exclamation me-1"></i>
             <b>아직 설정되지 않은 경로:</b> ${escapeHtml(missing.join(' · '))}<br>
             리워드팝 API 문서를 확인한 뒤 아래 경로란에 입력해야 자동 집행이 동작합니다.</div>`
        : '';

    return `
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-plug me-2"></i>리워드팝 API 키</h5>
            <span id="rpStatusBadge">${rewardpopStatusBadge(d)}</span>
        </div>
        <div class="card-body">
            ${envNotice}${missingNotice}
            <label class="form-label fw-bold small">API 키</label>
            <div class="input-group mb-2">
                <span class="input-group-text"><i class="fas fa-key"></i></span>
                <input type="password" class="form-control" id="rpApiKey" placeholder="리워드팝 [API 관리] 에서 발급한 키" autocomplete="off">
                <button class="btn btn-outline-secondary" type="button" onclick="toggleRewardpopKeyVisible()" id="rpKeyEye" title="입력값 보기">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
            <div class="small text-muted mb-3" id="rpCurrentKey">${d.configured
                ? `현재 등록된 키: <code>${escapeHtml(d.masked_key || '')}</code>`
                : '등록된 키가 없습니다.'}</div>
            <div class="d-flex gap-2 flex-wrap">
                <button class="btn btn-primary btn-sm" onclick="saveRewardpopKey()" id="rpSaveKeyBtn"><i class="fas fa-floppy-disk me-1"></i>키 저장</button>
                <button class="btn btn-outline-primary btn-sm" onclick="testRewardpopConnection()" id="rpTestBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-plug me-1"></i>연결 테스트</button>
                <button class="btn btn-outline-success btn-sm" onclick="checkRewardpopBalance()" id="rpBalanceBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-coins me-1"></i>포인트 잔액</button>
                <button class="btn btn-outline-dark btn-sm" onclick="showRewardpopPrices()" id="rpPricesBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-tags me-1"></i>공급 단가</button>
                <button class="btn btn-outline-danger btn-sm" onclick="deleteRewardpopKey()" id="rpDeleteBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-trash me-1"></i>키 삭제</button>
            </div>
            <div id="rpResult" class="mt-3"></div>
        </div>
    </div>

    <div class="card data-card">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-sliders-h me-2"></i>연동 설정</h5></div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-md-6">
                    <label class="form-label small fw-bold">기준 URL</label>
                    <input class="form-control" id="rpBaseUrl" value="${escapeHtml(s.base_url || '')}" readonly>
                </div>
                <div class="col-md-6">
                    <label class="form-label small fw-bold">인증 방식</label>
                    <select class="form-select" id="rpAuthStyle" onchange="toggleRewardpopAuthFields()" disabled>${styles}</select>
                </div>
                <div class="col-md-6" id="rpAuthHeaderWrap">
                    <label class="form-label small fw-bold">인증 헤더 이름</label>
                    <input class="form-control" id="rpAuthHeader" value="${escapeHtml(s.auth_header || '')}" readonly>
                </div>
                <div class="col-md-6" id="rpAuthQueryWrap">
                    <label class="form-label small fw-bold">인증 쿼리 이름</label>
                    <input class="form-control" id="rpAuthQuery" value="${escapeHtml(s.auth_query || '')}" placeholder="api_key">
                </div>
            </div>

            <hr class="my-4">
            <div class="small text-muted mb-2"><i class="fas fa-circle-check me-1 text-success"></i>공식 OpenAPI 규격에 고정된 경로입니다. 상태 조회는 <code>GET /ads?groupId=...</code>를 사용합니다.</div>
            <div class="row g-3">
                <div class="col-md-4">
                    <label class="form-label small fw-bold">연결 확인 경로 (GET)</label>
                    <input class="form-control" id="rpPingPath" value="${escapeHtml(s.ping_path || '')}" readonly>
                </div>
                <div class="col-md-4">
                    <label class="form-label small fw-bold">잔액 조회 경로 (GET)</label>
                    <input class="form-control" id="rpBalancePath" value="${escapeHtml(s.balance_path || '')}" readonly>
                </div>
                <div class="col-md-4">
                    <label class="form-label small fw-bold">주문 생성 경로 (POST)</label>
                    <input class="form-control" id="rpOrderPath" value="${escapeHtml(s.order_path || '')}" readonly>
                </div>
                <div class="col-md-4">
                    <label class="form-label small fw-bold">상태 조회 경로 (GET)</label>
                    <input class="form-control" id="rpStatusPath" value="${escapeHtml(s.status_path || '')}" readonly>
                    <div class="form-text small">등록 응답의 groupId를 조회 파라미터로 전달합니다.</div>
                </div>
            </div>

            <hr class="my-4">
            <div class="row g-3 align-items-end">
                <div class="col-md-3">
                    <label class="form-label small fw-bold">자동 집행 시각 (KST)</label>
                    <div class="input-group">
                        <input type="number" min="0" max="23" class="form-control" id="rpHour" value="${planNumber(s.dispatch_hour, 14)}">
                        <span class="input-group-text">시</span>
                        <input type="number" min="0" max="59" class="form-control" id="rpMinute" value="${planNumber(s.dispatch_minute, 0)}">
                        <span class="input-group-text">분</span>
                    </div>
                </div>
                <div class="col-md-9">
                    <div class="form-check form-switch mb-2">
                        <input class="form-check-input" type="checkbox" id="rpDryRun" ${s.dry_run ? 'checked' : ''}>
                        <label class="form-check-label" for="rpDryRun">
                            <b>드라이런</b> — 실제 주문을 보내지 않고 요청 내용만 기록합니다. 처음 켤 때는 반드시 켜두세요.
                        </label>
                    </div>
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="rpEnabled" ${d.enabled ? 'checked' : ''} ${d.configured ? '' : 'disabled'}>
                        <label class="form-check-label" for="rpEnabled">
                            <b>연동 사용</b> — 꺼두면 자동 집행이 전혀 일어나지 않습니다.
                        </label>
                    </div>
                </div>
            </div>

            <div class="mt-4">
                <button class="btn btn-primary btn-sm" onclick="saveRewardpopSettings()" id="rpSaveBtn"><i class="fas fa-floppy-disk me-1"></i>설정 저장</button>
            </div>
        </div>
    </div>`;
}

function toggleRewardpopAuthFields() {
    const style = document.getElementById('rpAuthStyle').value;
    const headerWrap = document.getElementById('rpAuthHeaderWrap');
    const queryWrap = document.getElementById('rpAuthQueryWrap');
    if (headerWrap) headerWrap.style.display = style === 'header' ? '' : 'none';
    if (queryWrap) queryWrap.style.display = style === 'query' ? '' : 'none';
}

function toggleRewardpopKeyVisible() {
    const input = document.getElementById('rpApiKey');
    const icon = document.querySelector('#rpKeyEye i');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
}

function showRewardpopResult(ok, message) {
    showToast(message, ok);
    const box = document.getElementById('rpResult');
    if (!box) return;
    box.innerHTML = `<div class="alert alert-${ok ? 'success' : 'danger'} py-2 mb-0 small">
        <i class="fas fa-${ok ? 'circle-check' : 'circle-exclamation'} me-1"></i>${escapeHtml(message)}</div>`;
}

function applyRewardpopState(data) {
    rewardpopState = data;
    const badge = document.getElementById('rpStatusBadge');
    if (badge) badge.innerHTML = rewardpopStatusBadge(data);
    const cur = document.getElementById('rpCurrentKey');
    if (cur) cur.innerHTML = data.configured
        ? `현재 등록된 키: <code>${escapeHtml(data.masked_key || '')}</code>`
        : '등록된 키가 없습니다.';
    ['rpTestBtn', 'rpBalanceBtn', 'rpPricesBtn', 'rpDeleteBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = !data.configured;
    });
    const enabled = document.getElementById('rpEnabled');
    if (enabled) { enabled.disabled = !data.configured; enabled.checked = !!data.enabled; }
}

async function saveRewardpopKey() {
    const input = document.getElementById('rpApiKey');
    const key = input.value.trim();
    if (!key) { showRewardpopResult(false, 'API 키를 입력해주세요.'); return; }
    const restore = busyButton('rpSaveKeyBtn', '저장 중...');
    try {
        const res = await apiPost('/api/admin/rewardpop/api-key', { api_key: key });
        input.value = '';
        input.type = 'password';
        document.querySelector('#rpKeyEye i').className = 'fas fa-eye';
        applyRewardpopState(res);
        showRewardpopResult(true, '키를 저장했습니다. 연결 테스트로 확인해보세요.');
    } catch (e) {
        showRewardpopResult(false, e.message);
    } finally {
        restore();
    }
}

async function deleteRewardpopKey() {
    if (!confirm('등록된 리워드팝 API 키를 삭제하시겠습니까?\n삭제하면 광고 자동 집행이 중단됩니다.')) return;
    const btn = document.getElementById('rpDeleteBtn');
    btn.disabled = true;
    try {
        applyRewardpopState(await apiDelete('/api/admin/rewardpop/api-key'));
        showRewardpopResult(true, '키를 삭제했습니다.');
    } catch (e) {
        showRewardpopResult(false, e.message);
        btn.disabled = false;
    }
}

async function saveRewardpopSettings() {
    const restore = busyButton('rpSaveBtn', '저장 중...');
    try {
        const res = await apiPut('/api/admin/rewardpop/config', {
            base_url: document.getElementById('rpBaseUrl').value.trim(),
            auth_style: document.getElementById('rpAuthStyle').value,
            auth_header: document.getElementById('rpAuthHeader').value.trim(),
            auth_query: document.getElementById('rpAuthQuery').value.trim(),
            ping_path: document.getElementById('rpPingPath').value.trim(),
            balance_path: document.getElementById('rpBalancePath').value.trim(),
            order_path: document.getElementById('rpOrderPath').value.trim(),
            status_path: document.getElementById('rpStatusPath').value.trim(),
            dispatch_hour: Number(document.getElementById('rpHour').value),
            dispatch_minute: Number(document.getElementById('rpMinute').value),
            dry_run: document.getElementById('rpDryRun').checked,
            enabled: document.getElementById('rpEnabled').checked,
        });
        applyRewardpopState(res);
        showRewardpopResult(true, '설정을 저장했습니다.');
    } catch (e) {
        showRewardpopResult(false, e.message);
    } finally {
        restore();
    }
}

async function testRewardpopConnection() {
    const btn = document.getElementById('rpTestBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>확인 중...';
    try {
        const res = await apiGet('/api/admin/rewardpop/test');
        showRewardpopResult(res.ok, res.detail);
    } catch (e) {
        showRewardpopResult(false, e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

// 리워드팝이 우리에게 매기는 미션별 원가. 집행 전 포인트 소요액의 기준이자
// ADPAY 판매 단가와의 마진을 확인하는 자리다.
async function showRewardpopPrices() {
    const restore = busyButton('rpPricesBtn', '조회 중...');
    try {
        const res = await apiGet('/api/admin/rewardpop/prices');
        if (!res.ok) { showRewardpopResult(false, res.detail); return; }
        const rows = (res.prices || []).map(p => `<tr>
            <td class="small">${escapeHtml(p.mediaType || '-')}</td>
            <td class="small">${escapeHtml(p.missionCategory || '-')}</td>
            <td class="small">${escapeHtml(p.missionAction || '-')}</td>
            <td class="small">${escapeHtml([p.name, p.subName].filter(Boolean).join(' · ') || '-')}</td>
            <td class="text-end fw-bold">${p.unitPrice == null ? '<span class="text-muted">미설정</span>'
                : Number(p.unitPrice).toLocaleString() + '원'}</td>
        </tr>`).join('');
        resetFormModalFooter(false);
        document.getElementById('formModalTitle').textContent = '리워드팝 공급 단가 (원가)';
        document.getElementById('formModalBody').innerHTML = `
            <div class="small text-muted mb-2">
                집행 전 포인트 소요액을 이 단가로 계산합니다. 단가가 <b>미설정</b>인 미션은
                판매 단가로 대신 추정하므로, 실제 차감액과 다를 수 있습니다.</div>
            <div class="table-responsive"><table class="table table-sm table-hover align-middle">
                <thead><tr><th>매체</th><th>카테고리</th><th>액션</th><th>이름</th><th class="text-end">공급 단가</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="5" class="text-center text-muted py-3">단가 정보가 없습니다</td></tr>'}</tbody>
            </table></div>`;
        new bootstrap.Modal(document.getElementById('formModal')).show();
    } catch (e) {
        showRewardpopResult(false, e.message);
    } finally {
        restore();
    }
}

async function checkRewardpopBalance() {
    const btn = document.getElementById('rpBalanceBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>조회 중...';
    try {
        const res = await apiGet('/api/admin/rewardpop/balance');
        if (!res.ok) {
            showRewardpopResult(false, res.detail);
        } else if (res.balance === null || res.balance === undefined) {
            showRewardpopResult(false, '응답에서 잔액을 찾지 못했습니다. 응답 형태를 확인해야 합니다.');
        } else {
            showRewardpopResult(true, `현재 포인트 잔액: ${Number(res.balance).toLocaleString()}`);
        }
    } catch (e) {
        showRewardpopResult(false, e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

// ─── ADMIN: 플랜 관리 ──────────────────────────────────────
const AD_TYPE_META = [
    ['blog_review', '블로그 리뷰', 'fas fa-blog'],
    ['receipt_review', '영수증 리뷰', 'fas fa-receipt'],
    ['place_traffic', '플레이스 방문', 'fas fa-map-marker-alt'],
    ['shorts', '쇼츠', 'fas fa-video'],
];
const PLAN_ACCENTS = { basic: 'secondary', standard: 'primary', premium: 'warning' };

function planNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function planFeeWithVat(plan) {
    const exclusive = planNumber(plan?.merchant_fee_rate);
    return planNumber(plan?.merchant_fee_rate_with_vat, exclusive * 1.1);
}

function planDailyAverage(plan, code) {
    const supplied = Number(plan?.[`${code}_daily_average`]);
    if (Number.isFinite(supplied)) return supplied;
    const now = new Date();
    const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    return planNumber(plan?.[`${code}_monthly`]) / days;
}

function planDailyDescription(plan, code) {
    return plan?.[`${code}_daily_description`]
        || planTargetPreview(plan?.[`${code}_monthly`]);
}

async function loadAdminPlans(c, t) {
    t.textContent = '플랜 관리';

    const [plans, merchants, pricing] = await Promise.all([
        apiGet('/api/admin/plans'),
        apiGet('/api/admin/merchants'),
        // 목표 건수를 입력할 때 월 예상 비용을 바로 보여주기 위해 단가를 함께 읽는다.
        apiGet('/api/admin/ad-pricing').catch(() => ({})),
    ]);
    window._planPricing = pricing || {};
    window._planMerchantCount = merchants.length;

    if (!plans.length) {
        c.innerHTML = `<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2"></i>
            등록된 플랜이 없습니다. 서버를 재시작하면 기본 플랜 3종이 생성됩니다.</div>`;
        return;
    }

    // 가맹점별 현재 플랜을 병렬 조회 (조회 실패한 건은 미배정으로 표시)
    const assigned = await Promise.all(merchants.map(async m => {
        try {
            const info = await apiGet(`/api/admin/merchants/${m.id}/plan`);
            return { id: m.id, name: m.name, plan: info.plan, assigned_at: info.assigned_at };
        } catch {
            return { id: m.id, name: m.name, plan: null, assigned_at: null };
        }
    }));

    c.innerHTML = `
    <div class="alert alert-info mb-3">
        <i class="fas fa-info-circle me-2"></i><strong>플랜 관리:</strong>
        여기에 입력한 <strong>월 목표 건수가 그대로 매일 자동 집행되는 양</strong>이 됩니다.
        일별 목표는 해당 월의 날짜 수에 맞춰 자동 배분되며, <strong>0으로 두면 집행되지 않습니다.</strong>
        수수료율은 부가세 별도 기준이고, 신규 가맹점은 <strong>베이직</strong> 플랜으로 자동 배정됩니다.
    </div>

    <div class="row g-3 mb-4">
        ${plans.map(p => _planCard(p)).join('')}
    </div>

    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-store me-2"></i>가맹점 플랜 배정</h5>
            <small class="text-muted">가맹점 ${assigned.length}곳</small>
        </div>
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover align-middle">
                    <thead><tr>
                        <th>가맹점</th><th>현재 플랜</th><th>수수료율 (부가세 별도)</th><th>배정일</th><th style="min-width:220px">플랜 변경</th><th>개별 수량</th><th>리워드팝 설정</th>
                    </tr></thead>
                    <tbody>
                        ${assigned.map(m => `
                        <tr>
                            <td class="fw-bold">${escapeHtml(m.name)}</td>
                            <td><span class="badge bg-${PLAN_ACCENTS[m.plan?.code] || 'light text-dark'}">${escapeHtml(m.plan?.name || '미배정')}</span></td>
                            <td>${m.plan
                                ? `${planNumber(m.plan.merchant_fee_rate).toFixed(2)}% <small class="text-muted">+ VAT → ${planFeeWithVat(m.plan).toFixed(2)}%</small>`
                                : '-'}</td>
                            <td class="text-muted small">${m.assigned_at ? formatDate(m.assigned_at) : '-'}</td>
                            <td>
                                <div class="input-group input-group-sm">
                                    <select class="form-select" id="mp_sel_${m.id}" aria-label="${escapeHtml(m.name)} 플랜 선택">
                                        ${plans.map(p => `<option value="${p.id}" ${p.id === m.plan?.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                                    </select>
                                    <button class="btn btn-primary" onclick="assignMerchantPlan(${m.id})">
                                        <i class="fas fa-check me-1"></i>변경
                                    </button>
                                </div>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-outline-secondary" onclick="showAdOverrideModal(${m.id}, '${escapeHtml(m.name)}')">
                                    <i class="fas fa-sliders-h me-1"></i>개별 설정
                                </button>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-outline-primary" onclick="showAdConfigModal(${m.id}, '${escapeHtml(m.name)}')">
                                    <i class="fas fa-cog me-1"></i>리워드팝
                                </button>
                            </td>
                        </tr>`).join('') || '<tr><td colspan="7" class="text-center text-muted py-4">가맹점이 없습니다</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>`;
}

function _planCard(p) {
    const accent = PLAN_ACCENTS[p.code] || 'secondary';
    const headText = accent === 'warning' ? 'text-dark' : 'text-white';
    return `
    <div class="col-lg-4 col-md-6">
        <div class="card data-card h-100 border-${accent}">
            <div class="card-header bg-${accent} ${headText} d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="fas fa-layer-group me-2"></i>${escapeHtml(p.name)}</h5>
                <small class="text-uppercase opacity-75">${escapeHtml(p.code)}</small>
            </div>
            <div class="card-body">
                <label class="form-label fw-bold" for="plan_${p.id}_fee">가맹점 수수료율 <small class="text-primary">(부가세 별도)</small></label>
                <div class="input-group mb-1">
                    <input type="number" class="form-control" id="plan_${p.id}_fee"
                        value="${planNumber(p.merchant_fee_rate).toFixed(2)}" step="0.1" min="0" max="100"
                        oninput="updatePlanVatPreview(${p.id})">
                    <span class="input-group-text">%</span>
                </div>
                <div class="small text-muted mb-3" id="plan_${p.id}_fee_preview">
                    실제 적용 <strong class="text-primary">${planFeeWithVat(p).toFixed(2)}%</strong>
                    <span class="ms-1">(부가세 10% 포함)</span>
                </div>

                <div class="fw-bold mb-2 small text-muted">
                    <i class="fas fa-bullseye me-1"></i>광고 월 목표 건수
                </div>
                ${AD_TYPE_META.map(([code, label, icon]) => `
                <div class="row g-2 align-items-center mb-3">
                    <div class="col-5 small"><i class="${icon} me-1 text-muted"></i>${label}</div>
                    <div class="col-7">
                        <input type="number" class="form-control form-control-sm" id="plan_${p.id}_${code}_monthly"
                            value="${planNumber(p[code + '_monthly'])}" min="0" aria-label="${label} 월별 목표"
                            oninput="updatePlanTargetPreview(${p.id}, '${code}')">
                    </div>
                    <div class="col-12">
                        <div class="small text-muted text-end" id="plan_${p.id}_${code}_preview">
                            일별 자동 배분 · ${escapeHtml(planDailyDescription(p, code))}
                            <span class="ms-1">(하루 평균 ${planDailyAverage(p, code).toFixed(2)}건)</span>
                        </div>
                        <div class="small text-end" id="plan_${p.id}_${code}_cost">
                            ${planCostLine(code, p[code + '_monthly'])}
                        </div>
                    </div>
                </div>`).join('')}

                <button class="btn btn-${accent} w-100 mt-3" onclick="savePlan(${p.id})">
                    <i class="fas fa-save me-1"></i>${escapeHtml(p.name)} 저장
                </button>
            </div>
        </div>
    </div>`;
}

function updatePlanVatPreview(planId) {
    const value = parseFloat(document.getElementById(`plan_${planId}_fee`)?.value);
    const preview = document.getElementById(`plan_${planId}_fee_preview`);
    if (!preview) return;
    preview.innerHTML = Number.isFinite(value)
        ? `실제 적용 <strong class="text-primary">${(value * 1.1).toFixed(2)}%</strong><span class="ms-1">(부가세 10% 포함)</span>`
        : '수수료율을 입력해 주세요.';
}

// 광고 종류별 단가 키. 자동 집행 대상만 비용이 발생한다.
const PLAN_COST_KEYS = { blog_review: 'blog_unit_price', place_traffic: 'place_traffic_unit_price' };

function planUnitPrice(code) {
    const key = PLAN_COST_KEYS[code];
    return key ? planNumber(window._planPricing?.[key]) : 0;
}

function planCostLine(code, monthly) {
    const unit = planUnitPrice(code);
    if (!PLAN_COST_KEYS[code]) return '<span class="text-muted">외부 집행 대상 아님</span>';
    if (!unit) return '<span class="text-warning">단가 미설정 — 집행 보류됩니다</span>';
    const per = unit * Math.max(0, parseInt(monthly, 10) || 0);
    if (!per) return '<span class="text-muted">집행 없음</span>';
    const count = window._planMerchantCount || 0;
    return `매장당 월 <strong>${per.toLocaleString()}원</strong>`
        + (count ? ` · 가맹점 ${count}곳 전체 <strong>${(per * count).toLocaleString()}원</strong>` : '');
}

function planTargetPreview(monthlyValue) {
    const monthly = Math.max(0, parseInt(monthlyValue, 10) || 0);
    const now = new Date();
    const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    if (monthly === 0) return '월 목표 없음';
    if (monthly < days) return `약 ${Math.max(1, Math.round(days / monthly))}일마다 1건`;
    const low = Math.floor(monthly / days);
    const high = Math.ceil(monthly / days);
    return low === high ? `매일 ${low}건` : `일자별 ${low}~${high}건`;
}

function updatePlanTargetPreview(planId, code) {
    const input = document.getElementById(`plan_${planId}_${code}_monthly`);
    const preview = document.getElementById(`plan_${planId}_${code}_preview`);
    if (!input || !preview) return;
    const monthly = Math.max(0, parseInt(input.value, 10) || 0);
    const now = new Date();
    const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    preview.innerHTML = `일별 자동 배분 · ${planTargetPreview(monthly)}
        <span class="ms-1">(하루 평균 ${(monthly / days).toFixed(2)}건)</span>`;
    const cost = document.getElementById(`plan_${planId}_${code}_cost`);
    if (cost) cost.innerHTML = planCostLine(code, monthly);
}

async function savePlan(planId) {
    const body = { merchant_fee_rate: parseFloat(document.getElementById(`plan_${planId}_fee`).value) };
    for (const [code] of AD_TYPE_META) {
        body[`${code}_monthly`] = parseInt(document.getElementById(`plan_${planId}_${code}_monthly`).value, 10);
    }
    if (Object.values(body).some(v => isNaN(v))) { alert('모든 값을 입력해주세요.'); return; }

    try {
        const saved = await apiPut(`/api/admin/plans/${planId}`, body);
        alert(`${saved.name} 플랜이 저장되었습니다.\n수수료는 부가세 별도이며 광고 일별 목표는 월 목표에서 자동 배분됩니다.`);
        navigate('admin-plans');
    } catch (e) { alert('저장 실패: ' + e.message); }
}

async function assignMerchantPlan(merchantId) {
    const planId = parseInt(document.getElementById(`mp_sel_${merchantId}`).value, 10);
    if (isNaN(planId)) return;
    try {
        const res = await apiPut(`/api/admin/merchants/${merchantId}/plan`, { plan_id: planId });
        alert(`${res.merchant_name} → ${res.plan.name} 플랜으로 변경되었습니다.`);
        navigate('admin-plans');
    } catch (e) { alert('플랜 변경 실패: ' + e.message); }
}

async function showAdOverrideModal(merchantId, merchantName) {
    let info;
    try {
        info = await apiGet(`/api/admin/merchants/${merchantId}/ad-override`);
    } catch (e) {
        alert('오버라이드 정보 조회 실패: ' + e.message);
        return;
    }

    document.getElementById('formModalTitle').textContent = `${merchantName} — 광고 수량 개별 설정`;
    resetFormModalFooter(true);

    const rows = info.items.map(it => `
    <div class="row g-2 align-items-center mb-3">
        <div class="col-5 fw-bold small">${escapeHtml(it.ad_type_label)}</div>
        <div class="col-7">
            <div class="input-group input-group-sm">
                <input type="number" class="form-control" id="ov_${merchantId}_${it.ad_type}"
                    placeholder="플랜 기본값 (${it.plan_monthly}건)"
                    value="${it.monthly_override !== null && it.monthly_override !== undefined ? it.monthly_override : ''}"
                    min="0" aria-label="${escapeHtml(it.ad_type_label)} 월 목표">
                <span class="input-group-text">건/월</span>
            </div>
            <div class="small text-muted mt-1">플랜 기본값: ${it.plan_monthly}건/월 · 현재 적용: <strong>${it.effective_monthly}건/월</strong></div>
        </div>
    </div>`).join('');

    document.getElementById('formModalBody').innerHTML = `
    <div class="alert alert-info py-2 small mb-3">
        <i class="fas fa-info-circle me-1"></i>
        비워두면 <strong>${escapeHtml(info.plan_name || '미배정')} 플랜 기본값</strong>을 사용합니다.
        숫자를 입력하면 이 매장에만 해당 수량이 적용됩니다.
    </div>
    ${rows}
    <div id="ov_result"></div>`;

    const saveBtn = document.getElementById('formModalSave');
    saveBtn.onclick = async () => {
        const overrides = info.items.map(it => {
            const val = document.getElementById(`ov_${merchantId}_${it.ad_type}`)?.value?.trim();
            return {
                ad_type: it.ad_type,
                monthly_override: val === '' || val === null || val === undefined ? null : parseInt(val, 10),
            };
        });
        try {
            await apiPut(`/api/admin/merchants/${merchantId}/ad-override`, { overrides });
            bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
            navigate('admin-plans');
        } catch (e) {
            document.getElementById('ov_result').innerHTML =
                `<div class="alert alert-danger py-2 small mt-2">${escapeHtml(e.message)}</div>`;
        }
    };

    new bootstrap.Modal(document.getElementById('formModal')).show();
}

// ── ADMIN: 가맹점별 광고 현황 모달 (키워드 / 블로그 설정 / 집행 통계) ──────

async function showMerchantAdStatus(merchantId, merchantName) {
    document.getElementById('formModalTitle').textContent = `${merchantName} — 광고 현황`;
    resetFormModalFooter(false);
    const body = document.getElementById('formModalBody');
    body.innerHTML = adpayLoadingMarkup('광고 현황을 불러오는 중입니다');
    new bootstrap.Modal(document.getElementById('formModal')).show();

    try {
        const [kwRes, blogRes, statsRes] = await Promise.all([
            apiGet(`/api/admin/merchants/${merchantId}/keywords`).catch(() => ({ keywords: [] })),
            apiGet(`/api/admin/merchants/${merchantId}/blog-config`).catch(() => ({ configured: false })),
            apiGet(`/api/admin/merchants/${merchantId}/ad-dispatch-stats`).catch(() => ({ daily: [], monthly: [] })),
        ]);
        body.innerHTML = merchantAdStatusMarkup(kwRes, blogRes, statsRes);
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function merchantAdStatusMarkup(kwRes, blogRes, statsRes) {
    // ── 키워드 탭 ──
    const kwRows = (kwRes.keywords || []).map(k => {
        const badgeColor = k.status === 'approved' ? 'success' : k.status === 'rejected' ? 'danger' : 'warning';
        return `<tr>
            <td class="fw-bold">${escapeHtml(k.keyword)}</td>
            <td><span class="badge bg-light text-dark border">${escapeHtml(k.ad_type || '공통')}</span></td>
            <td><span class="badge bg-${badgeColor}">${escapeHtml(k.status_label || k.status)}</span>
                ${k.reject_reason ? `<div class="small text-danger mt-1">${escapeHtml(k.reject_reason)}</div>` : ''}</td>
            <td>${k.is_active ? '<span class="badge bg-success">사용</span>' : '<span class="badge bg-secondary">비사용</span>'}</td>
        </tr>`;
    }).join('');

    // ── 블로그 탭 ──
    const blogHtml = blogRes.configured ? `
        <table class="table table-sm">
            <tbody>
                <tr><th style="width:140px">플레이스 URL</th><td><a href="${escapeHtml(blogRes.blog_place_url||'')}" target="_blank" class="small">${escapeHtml(blogRes.blog_place_url||'-')}</a></td></tr>
                <tr><th>업체명</th><td>${escapeHtml(blogRes.blog_place_name||'-')}</td></tr>
                <tr><th>필수 키워드</th><td>${escapeHtml(blogRes.blog_main_keyword||'-')}</td></tr>
                <tr><th>작업 키워드</th><td>${escapeHtml((blogRes.blog_work_keywords||[]).join(', ')||'-')}</td></tr>
                <tr><th>해시태그</th><td>${escapeHtml((blogRes.blog_tags||[]).join(', ')||'-')}</td></tr>
                <tr><th>포스팅 유형</th><td>${escapeHtml(blogRes.blog_post_type||'-')}</td></tr>
                <tr><th>매장 주소</th><td>${escapeHtml(blogRes.blog_store_address||'-')}</td></tr>
                <tr><th>대표번호</th><td>${escapeHtml(blogRes.blog_store_phone||'-')}</td></tr>
                <tr><th>추가 링크</th><td>${escapeHtml(blogRes.blog_extra_link||'-')}</td></tr>
                <tr><th>일별 접수 건수</th><td>${blogRes.daily_workload != null ? blogRes.daily_workload + '건' : '-'}</td></tr>
            </tbody>
        </table>` : `<div class="alert alert-warning">블로그 설정이 등록되지 않았습니다.</div>`;

    // ── 집행 통계 탭 ──
    const adTypeLabel = t => ({ place_traffic: '플레이스 방문', blog_review: '블로그 배포' })[t] || t;

    // 월별 집계
    const monthlyMap = {};
    (statsRes.monthly || []).forEach(r => {
        if (!monthlyMap[r.month]) monthlyMap[r.month] = {};
        monthlyMap[r.month][r.ad_type] = (monthlyMap[r.month][r.ad_type] || 0) + r.count;
    });
    const monthlyRows = Object.keys(monthlyMap).sort().reverse().map(month => {
        const place = monthlyMap[month]['place_traffic'] || 0;
        const blog = monthlyMap[month]['blog_review'] || 0;
        return `<tr><td>${escapeHtml(month)}</td><td>${place.toLocaleString()}</td><td>${blog.toLocaleString()}</td></tr>`;
    }).join('');

    // 일별 집계 (최근 30일)
    const dailyMap = {};
    (statsRes.daily || []).forEach(r => {
        if (!dailyMap[r.date]) dailyMap[r.date] = {};
        dailyMap[r.date][r.ad_type] = (dailyMap[r.date][r.ad_type] || 0) + r.count;
    });
    const dailyRows = Object.keys(dailyMap).sort().reverse().slice(0, 30).map(date => {
        const place = dailyMap[date]['place_traffic'] || 0;
        const blog = dailyMap[date]['blog_review'] || 0;
        return `<tr><td>${escapeHtml(date)}</td><td>${place.toLocaleString()}</td><td>${blog.toLocaleString()}</td></tr>`;
    }).join('');

    return `
    <ul class="nav nav-tabs mb-3" id="merchantAdStatusTabs">
        <li class="nav-item"><button class="nav-link active" data-mstab="keywords" onclick="switchMerchantAdTab('keywords')"><i class="fas fa-key me-1"></i>플레이스 키워드</button></li>
        <li class="nav-item"><button class="nav-link" data-mstab="blog" onclick="switchMerchantAdTab('blog')"><i class="fas fa-blog me-1"></i>블로그 설정</button></li>
        <li class="nav-item"><button class="nav-link" data-mstab="stats" onclick="switchMerchantAdTab('stats')"><i class="fas fa-chart-bar me-1"></i>집행 현황</button></li>
    </ul>

    <div id="mstabKeywords">
        ${kwRows ? `<div class="table-responsive"><table class="table table-sm table-hover">
            <thead><tr><th>키워드</th><th>광고 종류</th><th>상태</th><th>사용</th></tr></thead>
            <tbody>${kwRows}</tbody>
        </table></div>` : '<div class="text-muted text-center py-3">등록된 키워드가 없습니다</div>'}
    </div>

    <div id="mstabBlog" style="display:none">${blogHtml}</div>

    <div id="mstabStats" style="display:none">
        <h6 class="fw-bold mb-2">월별 집행 현황</h6>
        ${monthlyRows ? `<div class="table-responsive mb-4"><table class="table table-sm table-hover">
            <thead><tr><th>월</th><th>플레이스 방문</th><th>블로그 배포</th></tr></thead>
            <tbody>${monthlyRows}</tbody>
        </table></div>` : '<div class="text-muted mb-4">집행 내역 없음</div>'}
        <h6 class="fw-bold mb-2">일별 집행 현황 <span class="text-muted fw-normal small">(최근 30일)</span></h6>
        ${dailyRows ? `<div class="table-responsive"><table class="table table-sm table-hover">
            <thead><tr><th>날짜</th><th>플레이스 방문</th><th>블로그 배포</th></tr></thead>
            <tbody>${dailyRows}</tbody>
        </table></div>` : '<div class="text-muted">집행 내역 없음</div>'}
    </div>`;
}

function switchMerchantAdTab(tab) {
    ['Keywords', 'Blog', 'Stats'].forEach(k => {
        const el = document.getElementById(`mstab${k}`);
        if (el) el.style.display = (k.toLowerCase() === tab) ? '' : 'none';
    });
    document.querySelectorAll('#merchantAdStatusTabs .nav-link').forEach(el => {
        el.classList.toggle('active', el.dataset.mstab === tab);
    });
}

async function showAdConfigModal(merchantId, merchantName) {
    let info;
    try {
        info = await apiGet(`/api/admin/merchants/${merchantId}/ad-config`);
    } catch (e) {
        alert('리워드팝 설정 조회 실패: ' + e.message);
        return;
    }

    document.getElementById('formModalTitle').textContent = `${merchantName} — 리워드팝 집행 설정`;
    resetFormModalFooter(true);

    const missionCatOptions = (info.options?.mission_categories || [])
        .map(c => `<option value="${c.code}">${escapeHtml(c.label)}</option>`).join('');
    const keywordModeOptions = (info.options?.keyword_modes || [])
        .map(c => `<option value="${c.code}">${escapeHtml(c.label)}</option>`).join('');
    const autoCountOptions = (info.options?.auto_count_options || [10, 30, 50])
        .map(n => `<option value="${n}">${n}개</option>`).join('');

    function missionActionOptions(category, selected) {
        const all = info.options?.mission_actions || {};
        const acts = all[category] || [];
        if (!acts.length) return '<option value="">카테고리를 먼저 선택하세요</option>';
        return acts.map(a => `<option value="${a.code}" ${a.code === selected ? 'selected' : ''}>${escapeHtml(a.label)}</option>`).join('');
    }

    const rows = info.items.map(it => `
    <div class="card mb-3 border-secondary">
        <div class="card-header py-2 fw-bold small">
            <i class="fas fa-ad me-1 text-primary"></i>${escapeHtml(it.ad_type_label)}
            ${it.configured ? '<span class="badge bg-success ms-2">설정됨</span>' : '<span class="badge bg-warning text-dark ms-2">미설정 (집행 건너뜀)</span>'}
        </div>
        <div class="card-body py-3">
            <div class="row g-2 mb-2">
                <div class="col-6">
                    <label class="form-label small fw-bold mb-1">미션 카테고리</label>
                    <select class="form-select form-select-sm" id="cfg_cat_${merchantId}_${it.ad_type}"
                        onchange="updateMissionActions(${merchantId}, '${it.ad_type}')">
                        <option value="">선택 안 함</option>
                        ${(info.options?.mission_categories || []).map(c =>
                            `<option value="${c.code}" ${c.code === it.mission_category ? 'selected' : ''}>${escapeHtml(c.label)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="col-6">
                    <label class="form-label small fw-bold mb-1">미션 액션</label>
                    <select class="form-select form-select-sm" id="cfg_act_${merchantId}_${it.ad_type}">
                        <option value="">선택 안 함</option>
                        ${missionActionOptions(it.mission_category, it.mission_action)}
                    </select>
                </div>
            </div>
            <div class="row g-2">
                <div class="col-6">
                    <label class="form-label small fw-bold mb-1">키워드 모드</label>
                    <select class="form-select form-select-sm" id="cfg_kwmode_${merchantId}_${it.ad_type}"
                        onchange="updateAutoCountVisibility(${merchantId}, '${it.ad_type}')">
                        ${(info.options?.keyword_modes || []).map(c =>
                            `<option value="${c.code}" ${c.code === it.keyword_mode ? 'selected' : ''}>${escapeHtml(c.label)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="col-6" id="cfg_autocnt_wrap_${merchantId}_${it.ad_type}" style="${it.keyword_mode === 'AUTO' ? '' : 'display:none'}">
                    <label class="form-label small fw-bold mb-1">자동 키워드 수</label>
                    <select class="form-select form-select-sm" id="cfg_autocnt_${merchantId}_${it.ad_type}">
                        ${[10, 30, 50].map(n =>
                            `<option value="${n}" ${n === it.auto_count ? 'selected' : ''}>${n}개</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
        </div>
    </div>`).join('');

    document.getElementById('formModalBody').innerHTML = `
    <div class="mb-3">
        <label class="form-label fw-bold">네이버 플레이스 코드</label>
        <input type="text" class="form-control" id="cfg_place_code_${merchantId}"
            placeholder="예: 1750900108 (URL 끝 숫자 또는 전체 URL 입력)"
            value="${escapeHtml(info.place_code || '')}">
        <div class="form-text">
            네이버 플레이스 URL 끝의 숫자만 입력하거나, 전체 URL을 붙여넣어도 됩니다.
        </div>
    </div>
    <hr>
    <div class="fw-bold mb-3 small text-muted">광고 타입별 집행 설정</div>
    ${rows}
    <div id="cfg_result_${merchantId}"></div>`;

    const saveBtn = document.getElementById('formModalSave');
    saveBtn.onclick = async () => {
        const place_code = document.getElementById(`cfg_place_code_${merchantId}`)?.value?.trim() || null;
        const configs = info.items.map(it => {
            const cat = document.getElementById(`cfg_cat_${merchantId}_${it.ad_type}`)?.value || null;
            const act = document.getElementById(`cfg_act_${merchantId}_${it.ad_type}`)?.value || null;
            const kwmode = document.getElementById(`cfg_kwmode_${merchantId}_${it.ad_type}`)?.value || 'MANUAL';
            const autocnt = kwmode === 'AUTO'
                ? parseInt(document.getElementById(`cfg_autocnt_${merchantId}_${it.ad_type}`)?.value, 10) || null
                : null;
            return {
                ad_type: it.ad_type,
                mission_category: cat || null,
                mission_action: act || null,
                keyword_mode: kwmode,
                auto_count: autocnt,
            };
        });
        try {
            await apiPut(`/api/admin/merchants/${merchantId}/ad-config`, { place_code, configs });
            bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
            navigate('admin-plans');
        } catch (e) {
            document.getElementById(`cfg_result_${merchantId}`).innerHTML =
                `<div class="alert alert-danger py-2 small mt-2">${escapeHtml(e.message)}</div>`;
        }
    };

    new bootstrap.Modal(document.getElementById('formModal')).show();
}

function updateMissionActions(merchantId, adType) {
    const catSel = document.getElementById(`cfg_cat_${merchantId}_${adType}`);
    const actSel = document.getElementById(`cfg_act_${merchantId}_${adType}`);
    if (!catSel || !actSel) return;
    const cat = catSel.value;
    const missionActionsMap = {
        VISIT: [
            { code: 'WRITE_REVIEW', label: '방문자 리뷰' },
            { code: 'FIND_PATH', label: '길찾기' },
            { code: 'SPOT_CHECK', label: '명소확인' },
            { code: 'RANDOM_MISSION', label: '랜덤 미션' },
            { code: 'BUSINESS_HOURS', label: '영업시간' },
            { code: 'INTRODUCTION', label: '소개' },
            { code: 'WALK_COUNT', label: '도보수' },
        ],
        SAVE: [{ code: 'PLACE_SAVE', label: '플레이스 저장' }],
    };
    const acts = missionActionsMap[cat] || [];
    actSel.innerHTML = '<option value="">선택 안 함</option>' +
        acts.map(a => `<option value="${a.code}">${escapeHtml(a.label)}</option>`).join('');
}

function updateAutoCountVisibility(merchantId, adType) {
    const kwmode = document.getElementById(`cfg_kwmode_${merchantId}_${adType}`)?.value;
    const wrap = document.getElementById(`cfg_autocnt_wrap_${merchantId}_${adType}`);
    if (wrap) wrap.style.display = kwmode === 'AUTO' ? '' : 'none';
}

// ─── ADMIN: 광고 실행 현황 ─────────────────────────────────
let adExecViewMode = null;   // 'table' | 'cards' (최초 진입 시 화면 폭에 맞춰 결정)

/** 광고 실행 현황 기본 보기: 모바일은 10열 표 대신 카드 목록으로 연다. */
function defaultAdExecView() {
    return isMobileViewport() ? 'cards' : 'table';
}
let adExecSummary = null;

async function loadAdminAdExecutions(c, t) {
    t.textContent = '광고 실행 현황';
    const today = new Date().toISOString().slice(0, 10);
    if (!adExecViewMode) adExecViewMode = defaultAdExecView();

    c.innerHTML = `
    <div class="card data-card mb-3">
        <div class="card-body">
            <div class="row g-2 align-items-end">
                <div class="col-auto">
                    <label class="form-label fw-bold mb-1" for="adexec_date">기준일</label>
                    <input type="date" class="form-control" id="adexec_date" value="${today}"
                        onchange="refreshAdExecutions()">
                </div>
                <div class="col-auto">
                    <label class="form-label fw-bold mb-1" for="adexec_merchant">가맹점</label>
                    <select class="form-select" id="adexec_merchant" onchange="refreshAdExecutions()">
                        <option value="">전체</option>
                    </select>
                </div>
                <div class="col-auto ms-auto">
                    <div class="btn-group" role="group" aria-label="보기 방식 전환">
                        <button type="button" class="btn btn-outline-primary ${adExecViewMode === 'table' ? 'active' : ''}"
                            id="adexec_view_table" onclick="setAdExecView('table')" title="테이블 보기" aria-label="테이블 보기">
                            <i class="fas fa-table"></i><span class="d-md-none ms-1">테이블</span>
                        </button>
                        <button type="button" class="btn btn-outline-primary ${adExecViewMode === 'cards' ? 'active' : ''}"
                            id="adexec_view_cards" onclick="setAdExecView('cards')" title="카드 리스트 보기" aria-label="카드 리스트 보기">
                            <i class="fas fa-th-large"></i><span class="d-md-none ms-1">카드</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div id="adexec_body">${adpayLoadingMarkup()}</div>`;

    // 가맹점 필터 채우기 (실패해도 전체 조회는 동작한다)
    try {
        const merchants = await apiGet('/api/admin/merchants');
        const sel = document.getElementById('adexec_merchant');
        merchants.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            sel.appendChild(opt);
        });
    } catch { /* 필터 없이 진행 */ }

    await refreshAdExecutions();
}

function setAdExecView(mode) {
    adExecViewMode = mode;
    document.getElementById('adexec_view_table')?.classList.toggle('active', mode === 'table');
    document.getElementById('adexec_view_cards')?.classList.toggle('active', mode === 'cards');
    renderAdExecutions();
}

async function refreshAdExecutions() {
    const body = document.getElementById('adexec_body');
    if (!body) return;
    body.innerHTML = adpayLoadingMarkup();
    const d = document.getElementById('adexec_date').value;
    const mid = document.getElementById('adexec_merchant').value;
    try {
        const qs = new URLSearchParams({ date: d });
        if (mid) qs.set('merchant_id', mid);
        adExecSummary = await apiGet(`/api/admin/ad-executions/summary?${qs}`);
        renderAdExecutions();
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${escapeHtml(e.message)}</div>`;
    }
}

function renderAdExecutions() {
    const body = document.getElementById('adexec_body');
    if (!body || !adExecSummary) return;
    const rows = adExecSummary.merchants;
    if (!rows.length) {
        body.innerHTML = '<div class="alert alert-light border text-center py-4"><i class="fas fa-inbox me-2"></i>표시할 가맹점이 없습니다.</div>';
        return;
    }
    body.innerHTML = adExecViewMode === 'cards' ? _adExecCards(rows) : _adExecTable(rows);
}

function _execStatus(it) {
    if (it.monthly_remaining < 0) return '<span class="badge bg-danger">월 목표 초과</span>';
    if (it.pace_remaining > 0) return `<span class="badge bg-warning text-dark">누적 목표 ${it.pace_remaining}건 부족</span>`;
    if (it.daily_target === 0 && it.monthly_remaining > 0) return '<span class="badge bg-light text-secondary border">오늘 목표 없음</span>';
    return '<span class="badge bg-success">달성</span>';
}

function _execInput(m, it) {
    return `<div class="input-group input-group-sm ad-exec-input">
        <input type="number" class="form-control" id="ex_${m.merchant_id}_${it.ad_type}" value="${it.today_executed}" min="0"
            aria-label="${escapeHtml(m.merchant_name)} ${escapeHtml(it.ad_type_label)} 오늘 집행 건수">
        <button class="btn btn-outline-primary" onclick="saveAdExecution(${m.merchant_id}, '${it.ad_type}')"
            title="집행 건수 저장" aria-label="집행 건수 저장"><i class="fas fa-save"></i><span class="d-md-none ms-1">저장</span></button>
    </div>`;
}

function _adExecTable(rows) {
    const body = rows.map(m => m.items.map((it, i) => `
        <tr class="${it.is_behind ? 'ad-exec-behind' : ''}">
            ${i === 0 ? `<td rowspan="${m.items.length}" class="fw-bold align-middle">${escapeHtml(m.merchant_name)}</td>
                         <td rowspan="${m.items.length}" class="align-middle"><span class="badge bg-${PLAN_ACCENTS[m.plan_code] || 'light text-dark'}">${escapeHtml(m.plan_name)}</span></td>` : ''}
            <td>${escapeHtml(it.ad_type_label)}</td>
            <td class="text-end">${it.daily_target.toLocaleString()}<small class="d-block text-muted">${escapeHtml(it.daily_description)}</small></td>
            <td class="text-end fw-bold">${it.today_executed.toLocaleString()}</td>
            <td class="text-end">${it.monthly_target.toLocaleString()}</td>
            <td class="text-end">${it.month_total.toLocaleString()}</td>
            <td class="text-end ${it.monthly_remaining < 0 ? 'text-danger fw-bold' : ''}">${it.monthly_remaining.toLocaleString()}</td>
            <td>${_execStatus(it)}</td>
            <td>${_execInput(m, it)}</td>
        </tr>`).join('')).join('');

    return `
    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-table me-2"></i>집행 현황 (${adExecSummary.date})</h5>
            <small class="text-muted">월 누적 기간 ${adExecSummary.month_start} ~ ${adExecSummary.month_end}</small>
        </div>
        <div class="card-body p-0">
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0 mobile-keep-table">
                    <thead><tr>
                        <th>가맹점</th><th>플랜</th><th>광고종류</th>
                        <th class="text-end">오늘 목표</th><th class="text-end">오늘 집행</th>
                        <th class="text-end">월 목표</th><th class="text-end">이번달 누적</th>
                        <th class="text-end">잔여</th><th>상태</th><th>집행 입력</th>
                    </tr></thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        </div>
    </div>`;
}

function _adExecCards(rows) {
    return `<div class="row g-3">${rows.map(m => `
        <div class="col-xl-6">
            <div class="card data-card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-store me-2"></i>${escapeHtml(m.merchant_name)}</h6>
                    <span class="badge bg-${PLAN_ACCENTS[m.plan_code] || 'light text-dark'}">${escapeHtml(m.plan_name)}</span>
                </div>
                <div class="card-body">
                    ${m.items.map(it => `
                    <div class="ad-exec-item ${it.is_behind ? 'ad-exec-behind' : ''}">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="fw-bold">${escapeHtml(it.ad_type_label)}</span>
                            ${_execStatus(it)}
                        </div>
                        <div class="d-flex flex-wrap gap-3 small text-muted mb-2">
                            <span>오늘 목표 <strong class="text-dark">${it.daily_target.toLocaleString()}</strong> <small>(${escapeHtml(it.daily_description)})</small></span>
                            <span>오늘 <strong class="text-dark">${it.today_executed.toLocaleString()}</strong></span>
                            <span>월 목표 <strong class="text-dark">${it.monthly_target.toLocaleString()}</strong></span>
                            <span>월 누적 <strong class="text-dark">${it.month_total.toLocaleString()}</strong></span>
                            <span>잔여 <strong class="${it.monthly_remaining < 0 ? 'text-danger' : 'text-dark'}">${it.monthly_remaining.toLocaleString()}</strong></span>
                        </div>
                        ${_execInput(m, it)}
                    </div>`).join('')}
                </div>
            </div>
        </div>`).join('')}</div>`;
}

async function saveAdExecution(merchantId, adType) {
    const input = document.getElementById(`ex_${merchantId}_${adType}`);
    const count = parseInt(input.value, 10);
    if (isNaN(count) || count < 0) { alert('0 이상의 숫자를 입력해주세요.'); return; }
    try {
        await apiPost('/api/admin/ad-executions', {
            merchant_id: merchantId,
            ad_type: adType,
            executed_count: count,
            execution_date: document.getElementById('adexec_date').value,
        });
        await refreshAdExecutions();   // 잔여 건수 즉시 갱신
    } catch (e) { alert('저장 실패: ' + e.message); }
}

// ─── ADMIN: 온기(ONGI) QR 결제 ─────────────────────────────
let ongiState = null;
let ongiTxPage = 1;
let ongiTxLastPage = 1;

async function loadAdminOngi(c, t) {
    t.textContent = '온기 QR 결제';
    c.innerHTML = adpayLoadingMarkup('온기 연동 정보를 불러오는 중입니다');
    try {
        ongiState = await apiGet('/api/admin/ongi/config');
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
        return;
    }
    c.innerHTML = ongiPageMarkup(ongiState);
    // 미연결이면 설정을 펼쳐 키 입력을 안내하고, 연결됐으면 바로 내역을 보여준다
    toggleOngiSettings(!ongiState.configured);
    if (ongiState.configured) {
        loadOngiQrOptions();
        reloadOngiTransactions(1);
    }
}

function ongiStatusBadge(d) {
    if (!d.configured) return '<span class="badge bg-secondary"><i class="fas fa-circle-minus me-1"></i>미연결</span>';
    if (!d.enabled) return '<span class="badge bg-warning text-dark"><i class="fas fa-pause me-1"></i>동기화 중지</span>';
    return '<span class="badge bg-success"><i class="fas fa-circle-check me-1"></i>연동 중</span>';
}

function ongiLastSyncText(d) {
    return d.last_synced_at ? d.last_synced_at.replace('T', ' ') : '아직 없음';
}

function ongiPageMarkup(d) {
    const s = d.settings || {};
    return `
    <div class="card data-card mb-3">
        <div class="card-body py-2 px-3">
            <div class="row g-2 align-items-end">
                <div class="col-md-2"><label class="form-label small mb-1">시작일</label><input type="date" class="form-control form-control-sm" id="ongiFilterFrom"></div>
                <div class="col-md-2"><label class="form-label small mb-1">종료일</label><input type="date" class="form-control form-control-sm" id="ongiFilterTo"></div>
                <div class="col-md-2"><label class="form-label small mb-1">상태</label>
                    <select class="form-select form-select-sm" id="ongiFilterStatus">
                        <option value="">전체</option><option value="완료">완료</option><option value="취소">취소</option>
                    </select></div>
                <div class="col-md-2"><label class="form-label small mb-1">QR</label>
                    <select class="form-select form-select-sm" id="ongiFilterQr"><option value="">전체 QR</option></select></div>
                <div class="col-md-2"><label class="form-label small mb-1">검색</label>
                    <input class="form-control form-control-sm" id="ongiFilterSearch" placeholder="결제자 / 주문번호"></div>
                <div class="col-md-2 d-flex gap-1">
                    <button class="btn btn-primary btn-sm flex-fill" onclick="reloadOngiTransactions(1)" ${d.configured ? '' : 'disabled'} id="ongiSearchBtn"><i class="fas fa-search me-1"></i>조회</button>
                    <button class="btn btn-outline-secondary btn-sm" onclick="resetOngiFilters()" title="필터 초기화"><i class="fas fa-undo"></i></button>
                </div>
            </div>
        </div>
    </div>
    <div class="row g-3 mb-3" id="ongiSummaryRow"></div>
    <div class="card data-card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <h5 class="mb-0"><i class="fas fa-qrcode me-2"></i>온기 QR 결제 내역</h5>
            <div class="d-flex align-items-center gap-2">
                <span class="badge bg-primary" id="ongiCountBadge">-</span>
                <button class="btn btn-outline-primary btn-sm" onclick="runOngiSync()" id="ongiSyncBtn" ${d.configured ? '' : 'disabled'}>
                    <i class="fas fa-rotate me-1"></i>지금 동기화</button>
            </div>
        </div>
        <div class="card-body" id="ongiTableBody">${d.configured
            ? adpayLoadingMarkup()
            : '<div class="alert alert-info mb-0"><i class="fas fa-info-circle me-1"></i>아래 <b>연동 설정</b>에서 온기 API 키를 먼저 등록해주세요.</div>'}</div>
        <div class="card-footer py-2 d-flex justify-content-between align-items-center" id="ongiPagerRow" style="display:none!important"></div>
    </div>

    <div class="card data-card">
        <div class="card-header d-flex justify-content-between align-items-center" style="cursor:pointer" onclick="toggleOngiSettings()">
            <h5 class="mb-0"><i class="fas fa-plug me-2"></i>연동 설정 <span id="ongiStatusBadge" class="ms-2">${ongiStatusBadge(d)}</span></h5>
            <i class="fas fa-chevron-down" id="ongiSettingsChevron"></i>
        </div>
        <div class="card-body" id="ongiSettingsBody" style="display:none">
            <label class="form-label fw-bold small">API 키</label>
            <div class="input-group mb-2">
                <span class="input-group-text"><i class="fas fa-key"></i></span>
                <input type="password" class="form-control" id="ongiApiKey" placeholder="온기 관리자에게 발급받은 API 키" autocomplete="off">
                <button class="btn btn-outline-secondary" type="button" onclick="toggleOngiKeyVisible()" id="ongiKeyEye" title="입력값 보기"><i class="fas fa-eye"></i></button>
            </div>
            <div class="small text-muted mb-3" id="ongiCurrentKey">${d.configured
                ? `현재 등록된 키: <code>${escapeHtml(d.masked_key || '')}</code>`
                : '등록된 키가 없습니다.'}</div>
            <div class="d-flex gap-2 flex-wrap mb-3">
                <button class="btn btn-primary btn-sm" onclick="saveOngiKey()"><i class="fas fa-floppy-disk me-1"></i>키 저장</button>
                <button class="btn btn-outline-primary btn-sm" onclick="testOngiConnection()" id="ongiTestBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-plug me-1"></i>연결 테스트</button>
                <button class="btn btn-outline-danger btn-sm" onclick="deleteOngiKey()" id="ongiDeleteBtn" ${d.configured ? '' : 'disabled'}><i class="fas fa-trash me-1"></i>키 삭제</button>
            </div>

            <hr class="my-3">
            <div class="row g-3">
                <div class="col-md-4">
                    <label class="form-label small fw-bold">API MID (선택)</label>
                    <input class="form-control" id="ongiApiMid" value="${escapeHtml(s.api_mid || '')}" placeholder="가맹점 식별 강화용, 비우면 미사용">
                </div>
                <div class="col-md-4">
                    <label class="form-label small fw-bold">동기화 주기 (분)</label>
                    <input type="number" min="1" max="1440" class="form-control" id="ongiSyncInterval" value="${planNumber(s.sync_interval_minutes, 10)}">
                </div>
                <div class="col-md-4">
                    <label class="form-label small fw-bold">되짚어 받는 기간 (일)</label>
                    <input type="number" min="1" max="90" class="form-control" id="ongiLookback" value="${planNumber(s.sync_lookback_days, 3)}">
                    <div class="form-text small">노티 유실·사후 취소를 흡수하기 위해 최근 며칠을 매번 다시 받습니다.</div>
                </div>
            </div>
            <div class="form-check form-switch mt-3">
                <input class="form-check-input" type="checkbox" id="ongiEnabled" ${d.enabled ? 'checked' : ''} ${d.configured ? '' : 'disabled'}>
                <label class="form-check-label" for="ongiEnabled"><b>연동 사용</b> — 꺼두면 자동 동기화가 일어나지 않습니다.</label>
            </div>
            <div class="mt-3">
                <button class="btn btn-primary btn-sm" id="ongiSaveBtn" onclick="saveOngiSettings()"><i class="fas fa-floppy-disk me-1"></i>설정 저장</button>
            </div>

            <hr class="my-3">
            <label class="form-label fw-bold small">결제 노티 시크릿 (선택)</label>
            <div class="input-group mb-1">
                <span class="input-group-text"><i class="fas fa-shield-halved"></i></span>
                <input type="password" class="form-control" id="ongiNotifySecret" placeholder="ongi_nt_… (온기 관리자 콘솔에서 발급)" autocomplete="off">
                <button class="btn btn-outline-primary" type="button" onclick="saveOngiNotifySecret()">저장</button>
                <button class="btn btn-outline-danger" type="button" onclick="deleteOngiNotifySecret()" id="ongiSecretDeleteBtn" ${d.notify_secret_configured ? '' : 'disabled'}>삭제</button>
            </div>
            <div class="small text-muted mb-2" id="ongiSecretStatus">${d.notify_secret_configured
                ? '시크릿이 등록되어 있습니다. 결제 노티(웹훅) 수신 시 서명을 검증합니다.'
                : '등록된 시크릿이 없습니다. 웹훅을 쓰지 않으면 비워둬도 됩니다.'}</div>
            <div id="ongiResult" class="mt-3"></div>
        </div>
    </div>`;
}

function toggleOngiSettings(forceOpen) {
    const body = document.getElementById('ongiSettingsBody');
    const chevron = document.getElementById('ongiSettingsChevron');
    if (!body) return;
    const open = forceOpen !== undefined ? forceOpen : body.style.display === 'none';
    body.style.display = open ? '' : 'none';
    if (chevron) chevron.className = open ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
}

function toggleOngiKeyVisible() {
    const input = document.getElementById('ongiApiKey');
    const icon = document.querySelector('#ongiKeyEye i');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
}

function showOngiResult(ok, message) {
    showToast(message, ok);
    const box = document.getElementById('ongiResult');
    if (!box) return;
    box.innerHTML = `<div class="alert alert-${ok ? 'success' : 'danger'} py-2 mb-0 small">
        <i class="fas fa-${ok ? 'circle-check' : 'circle-exclamation'} me-1"></i>${escapeHtml(message)}</div>`;
}

function applyOngiState(data) {
    ongiState = data;
    const badge = document.getElementById('ongiStatusBadge');
    if (badge) badge.innerHTML = ongiStatusBadge(data);
    const cur = document.getElementById('ongiCurrentKey');
    if (cur) cur.innerHTML = data.configured
        ? `현재 등록된 키: <code>${escapeHtml(data.masked_key || '')}</code>`
        : '등록된 키가 없습니다.';
    ['ongiTestBtn', 'ongiDeleteBtn', 'ongiSyncBtn', 'ongiSearchBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = !data.configured;
    });
    const enabled = document.getElementById('ongiEnabled');
    if (enabled) { enabled.disabled = !data.configured; enabled.checked = !!data.enabled; }
    const secretBtn = document.getElementById('ongiSecretDeleteBtn');
    if (secretBtn) secretBtn.disabled = !data.notify_secret_configured;
    const secretStatus = document.getElementById('ongiSecretStatus');
    if (secretStatus) secretStatus.textContent = data.notify_secret_configured
        ? '시크릿이 등록되어 있습니다. 결제 노티(웹훅) 수신 시 서명을 검증합니다.'
        : '등록된 시크릿이 없습니다. 웹훅을 쓰지 않으면 비워둬도 됩니다.';
}

async function saveOngiKey() {
    const key = (document.getElementById('ongiApiKey').value || '').trim();
    if (!key) { showOngiResult(false, 'API 키를 입력해주세요.'); return; }
    try {
        const res = await apiPost('/api/admin/ongi/api-key', { api_key: key });
        document.getElementById('ongiApiKey').value = '';
        applyOngiState(res);
        showOngiResult(true, '키를 저장했습니다. 연결 테스트로 확인해보세요.');
    } catch (e) { showOngiResult(false, e.message); }
}

async function deleteOngiKey() {
    if (!confirm('등록된 온기 API 키를 삭제할까요? 자동 동기화가 중단됩니다.')) return;
    try {
        applyOngiState(await apiDelete('/api/admin/ongi/api-key'));
        showOngiResult(true, '키를 삭제했습니다.');
    } catch (e) { showOngiResult(false, e.message); }
}

async function testOngiConnection() {
    const btn = document.getElementById('ongiTestBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>확인 중...';
    try {
        const res = await apiGet('/api/admin/ongi/test');
        showOngiResult(res.ok, res.detail + (res.total_payments != null ? ` (전체 결제 ${Number(res.total_payments).toLocaleString()}건)` : ''));
    } catch (e) { showOngiResult(false, e.message); }
    finally { btn.disabled = false; btn.innerHTML = original; }
}

async function saveOngiSettings() {
    const restore = busyButton('ongiSaveBtn', '저장 중...');
    try {
        const res = await apiPut('/api/admin/ongi/config', {
            api_mid: document.getElementById('ongiApiMid').value.trim(),
            sync_interval_minutes: parseInt(document.getElementById('ongiSyncInterval').value, 10) || 10,
            sync_lookback_days: parseInt(document.getElementById('ongiLookback').value, 10) || 3,
            enabled: document.getElementById('ongiEnabled').checked,
        });
        applyOngiState(res);
        showOngiResult(true, '설정을 저장했습니다.');
    } catch (e) { showOngiResult(false, e.message); }
    finally { restore(); }
}

async function saveOngiNotifySecret() {
    const secret = (document.getElementById('ongiNotifySecret').value || '').trim();
    if (!secret) { showOngiResult(false, '시크릿 키를 입력해주세요.'); return; }
    try {
        const res = await apiPost('/api/admin/ongi/notify-secret', { secret });
        document.getElementById('ongiNotifySecret').value = '';
        applyOngiState(res);
        showOngiResult(true, '노티 시크릿을 저장했습니다.');
    } catch (e) { showOngiResult(false, e.message); }
}

async function deleteOngiNotifySecret() {
    if (!confirm('등록된 노티 시크릿을 삭제할까요?')) return;
    try {
        applyOngiState(await apiDelete('/api/admin/ongi/notify-secret'));
        showOngiResult(true, '노티 시크릿을 삭제했습니다.');
    } catch (e) { showOngiResult(false, e.message); }
}

async function runOngiSync() {
    const btn = document.getElementById('ongiSyncBtn');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>동기화 중...';
    try {
        const res = await apiPost('/api/admin/ongi/sync', {});
        if (res.skipped) {
            const reasons = {
                integration_off: '연동이 꺼져 있어 동기화하지 않았습니다. 연동 설정에서 켜주세요.',
                ongi_error: `온기 호출 실패: ${res.detail || ''}`,
            };
            showOngiResult(false, reasons[res.reason] || `동기화를 건너뛰었습니다 (${res.reason})`);
        } else {
            showOngiResult(true, `동기화 완료 — 조회 ${res.fetched}건, 신규 ${res.created}건, 갱신 ${res.updated}건`);
        }
        await reloadOngiTransactions(1);
    } catch (e) { showOngiResult(false, e.message); }
    finally { btn.disabled = false; btn.innerHTML = original; }
}

async function loadOngiQrOptions() {
    // 온기 서버에서 QR 목록을 받아 필터를 채운다. 실패해도 화면은 계속 동작한다.
    try {
        const res = await apiGet('/api/admin/ongi/qrs?limit=100');
        const sel = document.getElementById('ongiFilterQr');
        if (!sel || !res.items) return;
        sel.innerHTML = '<option value="">전체 QR</option>' + res.items.map(q =>
            `<option value="${q.id}">${escapeHtml(q.name || `QR #${q.id}`)}</option>`).join('');
    } catch (e) { /* QR 이름 없이도 조회는 가능하다 */ }
}

function ongiTxStatusBadge(status) {
    if (status === '완료') return '<span class="badge bg-success">완료</span>';
    if (status === '취소') return '<span class="badge bg-danger">취소</span>';
    return `<span class="badge bg-secondary">${escapeHtml(status || '-')}</span>`;
}

async function reloadOngiTransactions(page) {
    ongiTxPage = page || 1;
    const from = document.getElementById('ongiFilterFrom')?.value || '';
    const to = document.getElementById('ongiFilterTo')?.value || '';
    const status = document.getElementById('ongiFilterStatus')?.value || '';
    const qrId = document.getElementById('ongiFilterQr')?.value || '';
    const search = document.getElementById('ongiFilterSearch')?.value.trim() || '';

    let url = `/api/admin/ongi/transactions?page=${ongiTxPage}&limit=20`;
    if (from) url += `&start_date=${from}`;
    if (to) url += `&end_date=${to}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (qrId) url += `&qr_id=${qrId}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    const body = document.getElementById('ongiTableBody');
    try {
        const data = await apiGet(url);
        const items = data.items || [];
        const pg = data.pagination || {};
        const sum = data.summary || {};
        ongiTxLastPage = pg.last_page || 1;

        document.getElementById('ongiCountBadge').textContent = `${(pg.total || 0).toLocaleString()}건`;
        document.getElementById('ongiSummaryRow').innerHTML = `
            <div class="col-md-3 col-6"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-primary">${(sum.completed_count || 0).toLocaleString()}</div><small class="text-muted">완료 건수</small>
            </div></div></div>
            <div class="col-md-3 col-6"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-success">${formatMoney(sum.completed_amount || 0)}</div><small class="text-muted">완료 금액</small>
            </div></div></div>
            <div class="col-md-3 col-6"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-5 fw-bold text-danger">${(sum.cancelled_count || 0).toLocaleString()}</div><small class="text-muted">취소 건수</small>
            </div></div></div>
            <div class="col-md-3 col-6"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
                <div class="fs-6 fw-bold text-info" style="line-height:2">${escapeHtml(ongiLastSyncText(ongiState || {}))}</div><small class="text-muted">마지막 자동 동기화</small>
            </div></div></div>`;

        body.innerHTML = `
            <div class="table-responsive"><table class="table table-hover table-sm">
                <thead><tr><th>결제일시</th><th>결제자</th><th>금액</th><th>상태</th><th>결제수단</th><th>구분</th><th>QR</th><th>주문번호</th><th>승인번호</th></tr></thead>
                <tbody>${items.length ? items.map(tx => `<tr>
                    <td class="text-nowrap">${escapeHtml(tx.paid_at || '-')}</td>
                    <td>${escapeHtml(tx.member_name || '-')}</td>
                    <td class="fw-bold ${tx.status === '취소' ? 'text-decoration-line-through text-muted' : ''}">${formatMoney(tx.pay_price != null ? tx.pay_price : tx.amount)}</td>
                    <td>${ongiTxStatusBadge(tx.status)}</td>
                    <td>${escapeHtml(tx.payment_type || '-')}</td>
                    <td>${escapeHtml(tx.division || '-')}</td>
                    <td>${escapeHtml(tx.qr_name || (tx.qr_id != null ? `QR #${tx.qr_id}` : '-'))}</td>
                    <td>${tx.order_code ? `<code>${escapeHtml(tx.order_code)}</code>` : '-'}</td>
                    <td>${tx.auth_no ? `<code>${escapeHtml(tx.auth_no)}</code>` : '-'}</td>
                </tr>`).join('') : `<tr><td colspan="9" class="text-center text-muted py-4">조건에 맞는 결제 내역이 없습니다.<br>
                    <small>아직 동기화 전이라면 우측 상단 <b>지금 동기화</b>를 눌러주세요.</small></td></tr>`}</tbody>
            </table></div>`;

        const pager = document.getElementById('ongiPagerRow');
        if (pager) {
            if ((pg.total || 0) > (pg.per_page || 20)) {
                pager.style.setProperty('display', 'flex', 'important');
                pager.innerHTML = `
                    <button class="btn btn-outline-secondary btn-sm" onclick="reloadOngiTransactions(${ongiTxPage - 1})" ${ongiTxPage <= 1 ? 'disabled' : ''}><i class="fas fa-chevron-left"></i></button>
                    <span class="small text-muted">${ongiTxPage} / ${ongiTxLastPage} 페이지</span>
                    <button class="btn btn-outline-secondary btn-sm" onclick="reloadOngiTransactions(${ongiTxPage + 1})" ${ongiTxPage >= ongiTxLastPage ? 'disabled' : ''}><i class="fas fa-chevron-right"></i></button>`;
            } else {
                pager.style.setProperty('display', 'none', 'important');
            }
        }
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

function resetOngiFilters() {
    ['ongiFilterFrom', 'ongiFilterTo', 'ongiFilterStatus', 'ongiFilterQr', 'ongiFilterSearch'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    if (ongiState && ongiState.configured) reloadOngiTransactions(1);
}
