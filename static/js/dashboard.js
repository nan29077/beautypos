/**
 * ADPAY Dashboard — Enhanced Role-based SPA
 */

let currentUser = null;
let currentPage = 'home';
let adFeatureFlags = { ad_order_mgmt_enabled: false, ad_blog_enabled: false, ad_place_traffic_enabled: false };

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
    // 원장님인 경우 매장 정보를 미리 로드하여 이름 표기에 사용
    if (currentUser.role === 'owner') {
        try {
            ownerMerchantInfo = await apiGet('/api/owner/merchant-info');
        } catch(e) { ownerMerchantInfo = null; }
    }
    // 임대인 프로필 로드
    if (currentUser.role === 'landlord') {
        try {
            landlordProfileInfo = await apiGet('/api/landlord/profile');
        } catch(e) { landlordProfileInfo = null; }
    }

    // 광고 기능 플래그 로드 (사장님 계정에서 사이드바 메뉴 표시 제어)
    if (currentUser.role === 'owner') {
        try {
            adFeatureFlags = await apiGet('/api/feature-flags');
        } catch(e) { adFeatureFlags = { ad_order_mgmt_enabled: false, ad_blog_enabled: false, ad_place_traffic_enabled: false }; }
    }

    const displayName = (currentUser.role === 'owner' && ownerMerchantInfo)
        ? ownerDisplayName(currentUser, ownerMerchantInfo.name)
        : (currentUser.role === 'landlord' && landlordProfileInfo && landlordProfileInfo.building_name)
        ? landlordProfileInfo.building_name + ' 임대인'
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

    // 원장님일 때 왼쪽 상단 브랜드 영역에 매장명 전체 표기
    if (currentUser.role === 'owner' && ownerMerchantInfo && ownerMerchantInfo.name) {
        const brandEl = document.getElementById('sidebarBrand');
        if (brandEl) brandEl.textContent = ownerMerchantInfo.name;
    }
    // 임대인일 때 브랜드를 방긋페이로 변경
    if (currentUser.role === 'landlord') {
        const brandEl = document.getElementById('sidebarBrand');
        if (brandEl) brandEl.textContent = '방긋페이';
        const mobileBrandEl = document.getElementById('mobileBrand');
        if (mobileBrandEl) mobileBrandEl.textContent = '방긋페이';
    }

    buildSidebar();
    navigate('home');
});

function roleLabel(r) {
    return {admin:'최고관리자', sales:'영업관리자', owner:'사장님(원장님)', designer:'직원(디자이너)', landlord:'임대인'}[r] || r;
}

/**
 * 원장님 역할의 경우 매장명으로 표기 (풀네임, 마스킹 없음)
 */
function ownerDisplayName(user, merchantName) {
    if (user.role === 'owner' && merchantName) {
        return merchantName + '님';
    }
    return user.name;
}

let ownerMerchantInfo = null; // 원장님의 매장 정보 캐시
let landlordProfileInfo = null; // 임대인의 프로필 정보 캐시

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.toggle('show');
    if (overlay) overlay.classList.toggle('show', sidebar.classList.contains('show'));
}

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
        <a class="nav-link" href="#" data-page="admin-settlements"><i class="fas fa-calculator"></i>정산 관리</a>
        <a class="nav-link" href="#" data-page="admin-fee-policies"><i class="fas fa-percentage"></i>수수료 정책</a>
        <a class="nav-link" href="#" data-page="admin-commission-visibility"><i class="fas fa-eye"></i>수수료 표시 설정</a>
        <a class="nav-link" href="#" data-page="admin-payouts"><i class="fas fa-money-bill-wave"></i>출금요청 관리</a>
        <div class="nav-section"><i class="fas fa-bullhorn me-1" style="font-size:.6rem"></i>광고 · 마케팅</div>
        <a class="nav-link" href="#" data-page="admin-adorders"><i class="fas fa-bullhorn"></i>광고주문 관리</a>
        <a class="nav-link" href="#" data-page="admin-metrics"><i class="fas fa-chart-bar"></i>광고 지표 입력</a>
        <div class="nav-section"><i class="fas fa-user-tie me-1" style="font-size:.6rem"></i>ADPAY 영업 · 인력</div>
        <a class="nav-link" href="#" data-page="admin-sales-managers"><i class="fas fa-user-tie"></i>영업관리자 관리</a>
        <a class="nav-link" href="#" data-page="admin-sales-assign"><i class="fas fa-handshake"></i>영업관리자 연결</a>
        <a class="nav-link" href="#" data-page="admin-users"><i class="fas fa-users-cog"></i>사용자 목록</a>`;
        // ─── 방긋페이 메뉴 (당분간 숨김) ──────────────
        // 복원 시 아래 블록 주석만 해제하면 됨.
        /*
        html += `
        <div class="nav-divider"></div>
        <div class="nav-section" style="color:#ff9f1c"><i class="fas fa-smile me-1" style="font-size:.6rem"></i>방긋페이</div>
        <a class="nav-link" href="#" data-page="admin-landlords"><i class="fas fa-building" style="color:#ff9f1c"></i>임대인 관리</a>
        <a class="nav-link" href="#" data-page="admin-tenants"><i class="fas fa-users" style="color:#ff9f1c"></i>임차인 현황</a>
        <a class="nav-link" href="#" data-page="admin-rent-payments"><i class="fas fa-money-check-alt" style="color:#ff9f1c"></i>월세 결제 내역</a>
        <a class="nav-link" href="#" data-page="admin-pg-landlord"><i class="fas fa-key" style="color:#ff9f1c"></i>PG 설정 (임대인)</a>
        <div class="nav-section" style="color:#ff9f1c"><i class="fas fa-user-tie me-1" style="font-size:.6rem"></i>방긋 영업</div>
        <a class="nav-link" href="#" data-page="admin-banggut-sales"><i class="fas fa-user-tie" style="color:#ff9f1c"></i>영업관리자 관리</a>
        <a class="nav-link" href="#" data-page="admin-banggut-sales-assign"><i class="fas fa-handshake" style="color:#ff9f1c"></i>영업관리자 연결</a>`;
        */
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
        <a class="nav-link" href="#" data-page="owner-daily-summary"><i class="fas fa-calendar-day"></i>일별 결제내역</a>
        <div class="nav-section">리뷰 관리</div>
        <a class="nav-link" href="#" data-page="owner-receipt-review"><i class="fas fa-qrcode"></i>영수증 리뷰관리</a>
        <div class="nav-section">광고/마케팅</div>
        <a class="nav-link" href="#" data-page="owner-analysis"><i class="fas fa-chart-line"></i>광고 분석</a>`;
        if (masterOn) {
            html += `
        <a class="nav-link" href="#" data-page="owner-adorders"><i class="fas fa-bullhorn"></i>내 광고 주문</a>
        <a class="nav-link" href="#" data-page="owner-adorder-new"><i class="fas fa-plus-circle"></i>새 광고 주문</a>`;
        }
        html += `
        <div class="nav-section">미용실 관리 프로그램</div>
        <a class="nav-link" href="#" data-page="crm"><i class="fas fa-user-friends"></i>미용실 관리 프로그램</a>
        <div class="nav-section">설정</div>
        <a class="nav-link" href="#" data-page="owner-info"><i class="fas fa-cog"></i>매장 정보</a>`;
    } else if (role === 'landlord') {
        html += `
        <div class="nav-section">임차인 관리</div>
        <a class="nav-link" href="#" data-page="landlord-tenants"><i class="fas fa-users"></i>임차인 목록</a>
        <a class="nav-link" href="#" data-page="landlord-qr"><i class="fas fa-qrcode"></i>QR코드 관리</a>
        <div class="nav-section">결제 관리</div>
        <a class="nav-link" href="#" data-page="landlord-payments"><i class="fas fa-credit-card"></i>결제 내역</a>
        <a class="nav-link" href="#" data-page="landlord-monthly"><i class="fas fa-chart-bar"></i>월별 수금 현황</a>
        <div class="nav-section">설정</div>
        <a class="nav-link" href="#" data-page="landlord-profile"><i class="fas fa-cog"></i>내 정보 관리</a>`;
    } else if (role === 'designer') {
        html += `
        <div class="nav-section">내 매출</div>
        <a class="nav-link" href="#" data-page="designer-transactions"><i class="fas fa-receipt"></i>결제 내역</a>
        <a class="nav-link" href="#" data-page="designer-monthly"><i class="fas fa-calendar-alt"></i>월별 통계</a>
        <a class="nav-link" href="#" data-page="designer-settlement"><i class="fas fa-coins"></i>정산 분배</a>
        <div class="nav-section">미용실 관리 프로그램</div>
        <a class="nav-link" href="#" data-page="crm"><i class="fas fa-user-friends"></i>미용실 관리 프로그램</a>
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

function navigate(page) {
    currentPage = page;
    document.querySelectorAll('#sidebarNav .nav-link').forEach(l => {
        l.classList.toggle('active', l.dataset.page === page);
    });
    document.getElementById('sidebar').classList.remove('show');
    const overlay = document.getElementById('sidebarOverlay');
    if (overlay) overlay.classList.remove('show');
    loadPage(page);
}

// ─── Page Router ───────────────────────────────────────────
async function loadPage(page) {
    const c = document.getElementById('pageContent');
    const t = document.getElementById('pageTitle') || { textContent: '' };
    c.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';

    try {
        switch(page) {
            case 'home': await loadHomePage(c, t); break;
            // Admin
            case 'admin-merchants': await loadAdminMerchants(c, t); break;
            case 'admin-pg': await loadAdminPG(c, t); break;
            case 'admin-terminals': await loadAdminTerminals(c, t); break;
            case 'admin-transactions': await loadAdminTransactions(c, t); break;
            case 'admin-settlements': await loadAdminSettlements(c, t); break;
            case 'admin-fee-policies': await loadAdminFeePolicies(c, t); break;
            case 'admin-commission-visibility': await loadAdminCommissionVisibility(c, t); break;
            case 'admin-payouts': await loadAdminPayouts(c, t); break;
            case 'admin-adorders': await loadAdminAdOrders(c, t); break;
            case 'admin-metrics': await loadAdminMetrics(c, t); break;
            case 'admin-sales-managers': await loadAdminSalesManagers(c, t); break;
            case 'admin-sales-assign': await loadAdminSalesAssign(c, t); break;
            case 'admin-users': await loadAdminUsers(c, t); break;
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
            case 'owner-daily-summary': await loadOwnerDailySummary(c, t); break;
            case 'owner-analysis': await loadOwnerAnalysis(c, t); break;
            case 'owner-adorders': await loadOwnerAdOrders(c, t); break;
            case 'owner-adorder-new': await loadOwnerAdOrderNew(c, t); break;
            case 'owner-info': await loadOwnerInfo(c, t); break;
            case 'owner-receipt-review': await loadOwnerReceiptReview(c, t); break;
            case 'owner-crm': await loadCRM(c, t); break;
            case 'crm': await loadCRM(c, t); break;
            // Designer
            case 'designer-transactions': await loadDesignerTransactions(c, t); break;
            case 'designer-monthly': await loadDesignerMonthly(c, t); break;
            case 'designer-settlement': await loadDesignerSettlement(c, t); break;
            case 'designer-profile': await loadDesignerProfile(c, t); break;
            // Landlord (방긋페이)
            case 'landlord-tenants': await loadLandlordTenants(c, t); break;
            case 'landlord-qr': await loadLandlordQR(c, t); break;
            case 'landlord-payments': await loadLandlordPayments(c, t); break;
            case 'landlord-monthly': await loadLandlordMonthly(c, t); break;
            case 'landlord-profile': await loadLandlordProfile(c, t); break;
            // Admin - BangGutPay
            case 'admin-landlords': await loadAdminLandlords(c, t); break;
            case 'admin-tenants': await loadAdminTenants(c, t); break;
            case 'admin-rent-payments': await loadAdminRentPayments(c, t); break;
            case 'admin-pg-landlord': await loadAdminPGLandlord(c, t); break;
            case 'admin-banggut-sales': await loadAdminBanggutSales(c, t); break;
            case 'admin-banggut-sales-assign': await loadAdminBanggutSalesAssign(c, t); break;
            default: c.innerHTML = '<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2"></i>페이지를 찾을 수 없습니다.</div>';
        }
    } catch (e) {
        c.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${e.message}</div>`;
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
            <!-- 방긋페이 KPI 카드 (당분간 숨김)
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px;border-left:3px solid #ff9f1c"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold" style="color:#ff9f1c">${stats.total_landlords}</div><small class="text-muted" style="font-size:.7rem">임대인</small>
                </div></div>
            </div>
            <div class="col-6 col-md-4 col-lg-2">
                <div class="card shadow-sm border-0" style="border-radius:12px;border-left:3px solid #ff6b35"><div class="card-body py-2 px-3 text-center">
                    <div class="fw-bold" style="color:#ff6b35">${stats.total_tenants}</div><small class="text-muted" style="font-size:.7rem">임차인</small>
                </div></div>
            </div>
            -->
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
                    <div class="card-body p-0" style="max-height:220px;overflow-y:auto">
                        <div class="list-group list-group-flush">
                            ${(stats.recent_transactions||[]).map(tx => `
                            <div class="list-group-item d-flex justify-content-between align-items-center px-3 py-2" style="font-size:.82rem">
                                <div><div class="fw-bold">${formatMoney(tx.amount)}</div><small class="text-muted">${tx.merchant_name}</small></div>
                                <div class="text-end"><span class="badge bg-secondary bg-opacity-10 text-secondary">${tx.card_brand||'-'}</span><br><small class="text-muted">${formatDate(tx.created_at)}</small></div>
                            </div>`).join('') || '<div class="p-3 text-muted text-center">결제 내역 없음</div>'}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 빠른 바로가기 (방긋페이 현황 카드는 당분간 숨김) -->
        <div class="row g-3 mb-4">
            <!--
            <div class="col-lg-4">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px;border-top:3px solid #ff9f1c">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-building me-2" style="color:#ff9f1c"></i>방긋페이 현황</h5></div>
                    <div class="card-body">
                        <div class="d-flex justify-content-between mb-2"><span class="text-muted">결제완료</span><strong class="text-success">${stats.rent_paid}건</strong></div>
                        <div class="d-flex justify-content-between mb-2"><span class="text-muted">대기/미납</span><strong class="text-danger">${stats.rent_pending}건</strong></div>
                        <div class="d-flex justify-content-between mb-3"><span class="text-muted">총 수금액</span><strong style="color:#ff9f1c">${formatMoney(stats.rent_total_amount)}</strong></div>
                        <hr>
                        <div class="d-grid gap-2">
                            <a href="#" onclick="navigate('admin-landlords')" class="btn btn-sm btn-outline-warning"><i class="fas fa-building me-1"></i>임대인 관리</a>
                            <a href="#" onclick="navigate('admin-rent-payments')" class="btn btn-sm btn-outline-warning"><i class="fas fa-money-check-alt me-1"></i>월세 결제</a>
                        </div>
                    </div>
                </div>
            </div>
            -->
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
                    <div class="card-body p-0" style="max-height:220px;overflow-y:auto">
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
                    <div class="card-body p-0" id="adminAlertActivity" style="max-height:260px;overflow-y:auto"></div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="card data-card shadow-sm h-100" style="border-radius:14px">
                    <div class="card-header"><h5 class="mb-0"><i class="fas fa-server me-2"></i>시스템 정보</h5></div>
                    <div class="card-body">
                        <ul class="list-unstyled mb-0" style="font-size:.88rem">
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">역할</span><span class="badge bg-danger">최고관리자</span></li>
                            <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이메일</span><span class="fw-bold" style="font-size:.78rem">${currentUser.email}</span></li>
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
                                <span class="fw-bold" style="font-size:.85rem">${m.name}</span>
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
                        <div class="list-group-item list-group-item-${a.type} d-flex align-items-center gap-2 px-3 py-2 border-0" style="cursor:pointer" onclick="navigate('${a.link}')">
                            <i class="fas fa-${a.icon}"></i>
                            <span style="font-size:.85rem">${a.text}</span>
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
                            <div style="font-size:.82rem">${a.text}</div>
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
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이름</span><span class="fw-bold">${currentUser.name}</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">역할</span><span class="badge bg-info">영업관리자</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">대기 출금</span><span class="fw-bold">${stats.pending_payouts || 0}건</span></li>
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
                        <h5 class="mb-0 text-white fw-bold">${stats.merchant_name}</h5>
                        <small class="text-white-50">${stats.category || ''} ${stats.address ? '· ' + stats.address : ''}</small>
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
                                <span class="fw-bold" style="width:60px;font-size:.85rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s.name}</span>
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
                                        <td>${tx.staff_name || '<span class="text-muted">사장님</span>'}</td>
                                        <td><span class="badge bg-secondary bg-opacity-10 text-secondary">${tx.card_brand || '-'}</span></td>
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
                            borderRadius: 6,
                            borderSkipped: false,
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
                                ticks: {
                                    callback: (v) => v >= 10000 ? (v/10000) + '만' : v.toLocaleString(),
                                    font: { size: 11 }
                                },
                                grid: { color: 'rgba(0,0,0,.04)' }
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
                dashCalGrid.innerHTML = '<div class="text-center py-2"><div class="spinner-border spinner-border-sm"></div></div>';
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
    } else if (role === 'landlord') {
        stats = await apiGet('/api/landlord/dashboard-stats');
        const collRate = stats.collection_rate || 0;
        const recentPayments = stats.recent_payments || [];
        const trend = stats.monthly_trend || [];

        html = `
        <!-- 건물 정보 배너 -->
        <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2d1b03 0%,#5a3408 50%,#ff9f1c 100%);">
            <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
                <div class="d-flex align-items-center gap-3">
                    <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;">
                        <i class="fas fa-building text-white"></i>
                    </div>
                    <div>
                        <div class="text-white fw-bold">${stats.building_name || '내 건물'}</div>
                        <div style="color:rgba(255,255,255,.65);font-size:.8rem;">${stats.address || ''}</div>
                    </div>
                </div>
                <span class="badge" style="background:rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:50px;font-size:.78rem;">
                    <i class="fas fa-smile me-1" style="color:#ff9f1c"></i>방긋페이
                </span>
            </div>
        </div>

        <!-- KPI Cards -->
        <div class="row g-3 mb-4">
            <div class="col-lg-3 col-md-6 col-6"><div class="card kpi-card shadow-sm">
                <div class="card-body"><div class="d-flex align-items-center">
                    <div class="kpi-icon bg-warning bg-opacity-10 me-3"><i class="fas fa-users text-warning"></i></div>
                    <div><div class="kpi-value">${stats.tenant_count || 0}명</div><div class="kpi-label">활성 임차인</div></div>
                </div></div></div></div>
            <div class="col-lg-3 col-md-6 col-6"><div class="card kpi-card shadow-sm">
                <div class="card-body"><div class="d-flex align-items-center">
                    <div class="kpi-icon bg-info bg-opacity-10 me-3"><i class="fas fa-won-sign text-info"></i></div>
                    <div><div class="kpi-value">${formatMoney(stats.total_monthly_rent)}</div><div class="kpi-label">월 예정 수금액</div></div>
                </div></div></div></div>
            <div class="col-lg-3 col-md-6 col-6"><div class="card kpi-card shadow-sm">
                <div class="card-body"><div class="d-flex align-items-center">
                    <div class="kpi-icon bg-success bg-opacity-10 me-3"><i class="fas fa-check-circle text-success"></i></div>
                    <div><div class="kpi-value">${formatMoney(stats.month_collected)}</div><div class="kpi-label">이번달 수금액</div></div>
                </div></div></div></div>
            <div class="col-lg-3 col-md-6 col-6"><div class="card kpi-card shadow-sm">
                <div class="card-body"><div class="d-flex align-items-center">
                    <div class="kpi-icon bg-primary bg-opacity-10 me-3"><i class="fas fa-percentage text-primary"></i></div>
                    <div><div class="kpi-value">${collRate}%</div><div class="kpi-label">수금률</div></div>
                </div></div></div></div>
        </div>

        <div class="row g-3 mb-4">
            <!-- 월별 수금 추이 차트 -->
            <div class="col-md-8">
                <div class="card data-card h-100"><div class="card-header"><h5><i class="fas fa-chart-area me-2" style="color:#ff9f1c"></i>월별 수금 추이</h5></div>
                <div class="card-body" style="min-height:250px;">
                    <canvas id="landlordTrendChart"></canvas>
                </div></div>
            </div>
            <!-- 최근 결제 -->
            <div class="col-md-4">
                <div class="card data-card h-100"><div class="card-header"><h5><i class="fas fa-history me-2 text-success"></i>최근 결제</h5></div>
                <div class="card-body p-0">
                    ${recentPayments.length === 0 ? '<div class="text-center text-muted py-4">결제 내역이 없습니다</div>' :
                    '<div class="list-group list-group-flush">' + recentPayments.map(p => `
                        <div class="list-group-item px-3 py-2 border-0" style="border-bottom:1px solid #f0f0f0 !important;">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <div class="fw-bold" style="font-size:.85rem">${p.tenant_name}</div>
                                    <div class="text-muted" style="font-size:.72rem">${p.unit} · ${p.payment_month}</div>
                                </div>
                                <div class="text-end">
                                    <div class="fw-bold" style="font-size:.85rem;color:#ff6b35">${formatMoney(p.amount)}</div>
                                    <span class="badge bg-${p.status === 'paid' ? 'success' : 'warning'}" style="font-size:.65rem">${p.status === 'paid' ? '완료' : '대기'}</span>
                                </div>
                            </div>
                        </div>
                    `).join('') + '</div>'}
                </div></div>
            </div>
        </div>

        <!-- 빠른 바로가기 -->
        <div class="row g-3">
            <div class="col-12">
                <div class="card data-card"><div class="card-header"><h5><i class="fas fa-bolt me-2 text-warning"></i>빠른 바로가기</h5></div>
                <div class="card-body">
                    <div class="row g-2">
                        <div class="col-md-2 col-4"><a href="#" onclick="navigate('landlord-tenants')" class="btn w-100 py-3" style="background:rgba(255,159,28,.08);border:1px solid rgba(255,159,28,.15);color:#ff9f1c;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-users d-block mb-1" style="font-size:1.2rem"></i>임차인 목록</a></div>
                        <div class="col-md-2 col-4"><a href="#" onclick="navigate('landlord-qr')" class="btn w-100 py-3" style="background:rgba(255,107,53,.08);border:1px solid rgba(255,107,53,.15);color:#ff6b35;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-qrcode d-block mb-1" style="font-size:1.2rem"></i>QR코드</a></div>
                        <div class="col-md-2 col-4"><a href="#" onclick="navigate('landlord-payments')" class="btn w-100 py-3" style="background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.15);color:#22c55e;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-credit-card d-block mb-1" style="font-size:1.2rem"></i>결제 내역</a></div>
                        <div class="col-md-2 col-4"><a href="#" onclick="navigate('landlord-monthly')" class="btn w-100 py-3" style="background:rgba(14,165,233,.08);border:1px solid rgba(14,165,233,.15);color:#0ea5e9;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-chart-bar d-block mb-1" style="font-size:1.2rem"></i>월별 현황</a></div>
                        <div class="col-md-2 col-4"><a href="#" onclick="navigate('landlord-profile')" class="btn w-100 py-3" style="background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.15);color:#8b5cf6;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-cog d-block mb-1" style="font-size:1.2rem"></i>내 정보</a></div>
                        <div class="col-md-2 col-4"><a href="/static/landing/banggut.html" class="btn w-100 py-3" style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);color:#999;border-radius:12px;font-size:.82rem;font-weight:600"><i class="fas fa-external-link-alt d-block mb-1" style="font-size:1.2rem"></i>방긋페이 소개</a></div>
                    </div>
                </div></div>
            </div>
        </div>`;

        // 차트 렌더링
        setTimeout(() => {
            const ctx = document.getElementById('landlordTrendChart');
            if (ctx && typeof Chart !== 'undefined') {
                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: trend.map(t => t.month),
                        datasets: [{
                            label: '수금액',
                            data: trend.map(t => t.amount),
                            backgroundColor: 'rgba(255,159,28,.5)',
                            borderColor: '#ff9f1c',
                            borderWidth: 1,
                            borderRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { callback: v => v >= 10000 ? (v/10000)+'만' : v.toLocaleString() } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }
        }, 100);
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
                    <span class="text-muted">직원:</span> <strong>${stats.staff_name}</strong> 
                    <span class="badge bg-secondary ms-2">코드: ${stats.staff_code}</span>
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
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">이름</span><span class="fw-bold">${stats.staff_name}</span></li>
                        <li class="mb-2 d-flex justify-content-between"><span class="text-muted">직원코드</span><code>${stats.staff_code}</code></li>
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
        <td>${m.id}</td><td class="fw-bold">${m.name}</td><td>${m.business_no||'-'}</td>
        <td>${m.address||'-'}</td><td>${m.phone||'-'}</td>
        <td>${m.is_active?'<span class="badge bg-success">활성</span>':'<span class="badge bg-danger">비활성</span>'}</td>
        <td><button class="btn btn-sm btn-outline-primary" onclick="showPGConfig(${m.id})"><i class="fas fa-cog"></i> PG</button></td>
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
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '새 가맹점 등록';
    body.innerHTML = `
    <div class="row g-3">
        <div class="col-md-6"><label class="form-label">가맹점 이름</label><input class="form-control" id="fMerchName"></div>
        <div class="col-md-6"><label class="form-label">소유자 User ID</label><input class="form-control" id="fMerchOwner" type="number"></div>
        <div class="col-md-6"><label class="form-label">사업자번호</label><input class="form-control" id="fMerchBiz"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="fMerchPhone"></div>
        <div class="col-12"><label class="form-label">주소</label><input class="form-control" id="fMerchAddr"></div>
    </div>`;
    document.getElementById('formModalSave').onclick = async () => {
        await apiPost('/api/admin/merchants', { name: document.getElementById('fMerchName').value, owner_user_id: parseInt(document.getElementById('fMerchOwner').value), business_no: document.getElementById('fMerchBiz').value, address: document.getElementById('fMerchAddr').value, phone: document.getElementById('fMerchPhone').value });
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        navigate('admin-merchants');
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

async function loadAdminPG(c, t) {
    t.textContent = 'PG 설정';
    const merchants = await apiGet('/api/admin/merchants');
    const providers = await apiGet('/api/admin/pg-providers');
    let provOpts = providers.map(p => `<option value="${p.id}">${p.name} (${p.code})</option>`).join('');
    let merchOpts = merchants.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
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
        <td class="fw-bold">${cfg.provider_name}</td><td><code>${cfg.mid}</code></td><td>${cfg.secret_masked}</td>
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
    } catch (e) { document.getElementById('pgSaveResult').innerHTML = `<span class="text-danger">${e.message}</span>`; }
}

async function testPG(mid, configId) {
    const el = document.getElementById(`pgTestResult${configId}`);
    el.innerHTML = '<span class="spinner-border spinner-border-sm text-warning"></span>';
    try {
        const res = await apiPost(`/api/admin/merchants/${mid}/pg-test?config_id=${configId}`, {});
        el.innerHTML = res.success ? `<span class="text-success ms-1"><i class="fas fa-check-circle"></i></span>` : `<span class="text-danger ms-1"><i class="fas fa-times-circle"></i></span>`;
        loadPGConfigs();
    } catch (e) { el.innerHTML = `<span class="text-danger ms-1">${e.message}</span>`; }
}

async function showPGConfig(mid) { navigate('admin-pg'); setTimeout(() => { const sel = document.getElementById('pgMerchant'); if (sel) { sel.value = mid; loadPGConfigs(); } }, 500); }

async function loadAdminTerminals(c, t) {
    t.textContent = '단말기 관리';
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>단말기 목록</h5></div><div class="card-body">
        <p class="text-muted text-center py-3"><i class="fas fa-tablet-alt fa-2x mb-2 d-block"></i>단말기 관리 페이지입니다. 현재 등록된 단말기는 관리자 API를 통해 조회 가능합니다.</p>
    </div></div>`;
}

async function loadAdminTransactions(c, t) {
    t.textContent = '전체 결제 내역';
    const merchants = await apiGet('/api/admin/merchants');
    let merchOpts = '<option value="">전체 가맹점</option>' + merchants.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
    
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
    </div><div class="card-body" id="txTableBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div></div>`;
    
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
                    <td>${tx.id}</td><td>${tx.merchant_name || tx.merchant_id}</td><td class="fw-bold">${formatMoney(tx.amount)}</td>
                    <td>${tx.installment_months||'일시불'}</td><td>${tx.card_brand||'-'}</td>
                    <td>${tx.staff_name||'<span class="text-muted">사장님</span>'}</td><td><code>${tx.approval_code||'-'}</code></td>
                    <td>${formatDate(tx.created_at)}</td>
                </tr>`).join('') : '<tr><td colspan="8" class="text-center text-muted py-4">조건에 맞는 결제 내역이 없습니다</td></tr>'}</tbody>
            </table></div>`;
    } catch(e) {
        document.getElementById('txTableBody').innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
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
    let merchOpts = merchants.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
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
                    <thead><tr><th>ID</th><th>가맹점</th><th>기간</th><th>총매출</th><th>PG수수료</th><th>커미션</th><th>순매출</th></tr></thead>
                    <tbody>${settlements.map(s => `<tr>
                        <td>${s.id}</td><td>${s.merchant_id}</td>
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
        document.getElementById('settleResult').innerHTML = `<div class="alert alert-success"><strong>정산 완료!</strong><br>총매출: ${formatMoney(res.gross_amount)} | PG수수료: ${formatMoney(res.pg_fee_amount)}<br>커미션: ${formatMoney(res.commission_amount)} | 순매출: <strong>${formatMoney(res.net_amount)}</strong> | ${res.transactions_count}건</div>`;
        navigate('admin-settlements');
    } catch (e) { document.getElementById('settleResult').innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
}

async function loadAdminFeePolicies(c, t) {
    t.textContent = '수수료 정책';

    // 통합 수수료 현황 API (가맹점 + 수수료 + 영업관리자 한번에)
    const overview = await apiGet('/api/admin/fee-policy-overview');
    const salesManagers = await apiGet('/api/admin/sales-managers');

    const salesOpts = salesManagers.map(u => `<option value="${u.id}">${u.name} (${u.email})</option>`).join('');

    // 통계 요약
    const totalMerchants = overview.length;
    const withSales = overview.filter(o => o.has_sales_manager).length;
    const withoutSales = totalMerchants - withSales;
    const customFee = overview.filter(o => o.has_fee_policy).length;

    let rows = overview.map(o => {
        const salesBadge = o.has_sales_manager
            ? `<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">
                <i class="fas fa-user-tie me-1"></i>${o.sales_manager_name}
                <span class="ms-1 fw-bold">${o.commission_rate_pct}%</span>
               </span>`
            : `<span class="badge bg-secondary bg-opacity-10 text-secondary">미배정</span>`;
        
        const simBreakdown = o.has_sales_manager
            ? `<small class="d-block text-muted">PG ${o.sim_pg_fee.toLocaleString()}원 = ADPAY ${o.sim_platform.toLocaleString()}원 + 영업 <span class="text-primary fw-bold">${o.sim_commission.toLocaleString()}원</span></small>`
            : `<small class="d-block text-muted">PG ${o.sim_pg_fee.toLocaleString()}원 = ADPAY ${o.sim_platform.toLocaleString()}원 (영업 미배정)</small>`;

        return `<tr>
            <td>${o.merchant_id}</td>
            <td>
                <div class="fw-bold">${o.merchant_name}</div>
                ${o.category ? `<small class="text-muted">${o.category}</small>` : ''}
            </td>
            <td class="text-muted">${(o.pg_fee_rate_excl_vat_pct ?? (o.pg_fee_rate_pct / 1.1)).toFixed(2)}%</td>
            <td class="fw-bold text-primary">${o.pg_fee_rate_pct}%</td>
            <td>${salesBadge}</td>
            <td>
                <div>10,000원 → <strong class="text-success">${o.sim_net.toLocaleString()}원</strong></div>
                ${simBreakdown}
            </td>
            <td>
                <div class="d-flex gap-1">
                    <div class="input-group input-group-sm" style="width:150px">
                        <input type="number" class="form-control" id="feeRate${o.merchant_id}" value="${o.pg_fee_rate_pct}" step="0.1" min="0" max="10">
                        <span class="input-group-text">%</span>
                        <button class="btn btn-primary" onclick="saveFeePolicy(${o.merchant_id})" title="수수료 저장"><i class="fas fa-save"></i></button>
                    </div>
                </div>
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
                    : `<button class="btn btn-sm btn-outline-primary" onclick="showAssignSalesModal(${o.merchant_id}, '${o.merchant_name.replace(/'/g, "\\'")}')">
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
                    <li><strong>PG 수수료:</strong> 결제 금액 × 가맹점별 설정 수수료율 <strong>(VAT 포함)</strong></li>
                    <li><strong>구성:</strong> PG 수수료 = <strong>영업 몫</strong> + <strong>ADPAY 플랫폼 몫</strong>
                        <small class="text-muted">(영업 몫 = 결제액 × 영업관리자 커미션율)</small></li>
                    <li><strong>분배가능액:</strong> 결제액 − PG 수수료 → 원장 ↔ 디자이너 분배율(share_rate)로 분배</li>
                    <li><strong>정산 예시:</strong> 10,000원 결제, PG 5% / 영업 1%
                        → PG수수료 <strong>500원</strong>(영업 100원 + ADPAY 400원)
                        → 분배가능액 <strong>9,500원</strong></li>
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
                            <th>수수료<br><small class="text-muted">(VAT 별도)</small></th>
                            <th>PG 수수료<br><small class="text-muted">(VAT 포함)</small></th>
                            <th>영업관리자</th>
                            <th>정산 시뮬레이션<br><small class="text-muted">(1만원 기준)</small></th>
                            <th>PG 수수료 변경<br><small class="text-muted">(VAT 포함)</small></th>
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
                            <input type="number" class="form-control" id="assignModalRate" value="1.0" step="0.1" min="0" max="3.5">
                            <span class="input-group-text">%</span>
                        </div>
                        <small class="text-muted">최대 3.5% (기본 수수료 내)</small>
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

async function saveFeePolicy(merchantId) {
    try {
        const rate = parseFloat(document.getElementById(`feeRate${merchantId}`).value) / 100;
        if (rate < 0 || rate > 0.1) { alert('수수료율은 0~10% 범위에서 설정해주세요.'); return; }
        const result = await apiPost(`/api/admin/merchants/${merchantId}/fee-policy`, { pg_fee_rate: rate });
        alert(`수수료 정책 저장 완료!\nPG 수수료(VAT 포함): ${(rate*100).toFixed(2)}%\n${result.example}`);
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
        if (rate < 0 || rate > 0.035) { alert('커미션율은 0~3.5% 범위에서 설정해주세요.'); return; }

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
        if (rate < 0 || rate > 0.035) { alert('커미션율은 0~3.5% 범위에서 설정해주세요.'); return; }
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
            <p class="text-muted mb-3">출금요청 내역이 없습니다</p>
            <button class="btn btn-outline-primary btn-sm" onclick="seedDummyPayouts()"><i class="fas fa-database me-1"></i>더미 데이터 생성</button>
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
            <thead><tr><th>ID</th><th>요청자</th><th>역할</th><th>금액</th><th>은행정보</th><th>메모</th><th>상태</th><th>요청일</th><th>액션</th></tr></thead>
            <tbody>${payouts.map(p => `<tr data-status="${p.status}">
                <td>${p.id}</td><td class="fw-bold">${p.requester_name || '-'}</td><td><span class="badge bg-${p.role==='sales'?'info':p.role==='owner'?'primary':'secondary'}">${roleLabel(p.role)}</span></td>
                <td class="fw-bold">${formatMoney(p.amount)}</td><td style="font-size:.82rem">${p.bank_info||'-'}</td><td style="font-size:.82rem">${p.memo||'-'}</td>
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

async function seedDummyPayouts() {
    if (!confirm('출금요청 더미 데이터를 생성하시겠습니까?')) return;
    try {
        const res = await apiPost('/api/admin/banggut/seed-payout-data', {});
        alert(res.message || '더미 데이터가 생성되었습니다');
        navigate('admin-payouts');
    } catch(e) { alert('생성 실패: ' + e.message); }
}

async function handlePayout(id, action) { await apiPost(`/api/admin/payout-requests/${id}/${action}`, {}); navigate('admin-payouts'); }

async function loadAdminAdOrders(c, t) {
    t.textContent = '광고주문 관리';
    const [orders, flags] = await Promise.all([
        apiGet('/api/admin/ad/orders'),
        apiGet('/api/admin/ad-feature-flags'),
    ]);
    const pending = orders.filter(o => o.status === 'requested' || o.status === 'reviewing').length;
    const running = orders.filter(o => o.status === 'running').length;
    const done = orders.filter(o => o.status === 'done').length;
    const masterOn = flags.ad_order_mgmt_enabled;
    const blogOn = flags.ad_blog_enabled;
    const placeOn = flags.ad_place_traffic_enabled;
    
    c.innerHTML = `
    <!-- 광고 기능 스위치 -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden">
        <div class="card-header py-2 px-4" style="background:linear-gradient(135deg,#1b3a5c,#2c5f8a)">
            <div class="d-flex align-items-center gap-2">
                <i class="fas fa-sliders-h text-white"></i>
                <h6 class="mb-0 text-white fw-bold">광고 기능 스위치</h6>
                <span class="ms-auto badge" style="background:rgba(255,255,255,.15);color:#fff;font-size:.68rem"><i class="fas fa-info-circle me-1"></i>사장님 계정에 표시될 광고 메뉴를 제어합니다</span>
            </div>
        </div>
        <div class="card-body py-3 px-4">
            <!-- 마스터 스위치: 광고 주문 관리 -->
            <div class="d-flex align-items-center justify-content-between p-3 rounded-3 mb-3" id="masterSwitchCard" style="background:${masterOn ? 'linear-gradient(135deg,rgba(34,197,94,.06),rgba(34,197,94,.14))' : '#f8f9fa'};border:2px solid ${masterOn ? 'rgba(34,197,94,.35)' : '#ddd'};transition:all .3s">
                <div class="d-flex align-items-center gap-3">
                    <div id="masterSwitchIcon" style="width:46px;height:46px;border-radius:13px;background:${masterOn ? 'linear-gradient(135deg,#22c55e,#4ade80)' : '#aaa'};display:flex;align-items:center;justify-content:center;transition:all .3s;box-shadow:${masterOn ? '0 4px 12px rgba(34,197,94,.25)' : 'none'}">
                        <i class="fas fa-bullhorn text-white" style="font-size:1.15rem"></i>
                    </div>
                    <div>
                        <div class="fw-bold" style="font-size:1rem">광고 주문 관리</div>
                        <div style="font-size:.74rem;color:#888">ON: 사장님 계정에 "내 광고 주문" / "새 광고 주문" 메뉴 표시<br>OFF: 해당 메뉴 숨김 (광고 분석은 항상 표시)</div>
                    </div>
                </div>
                <div class="form-check form-switch mb-0" style="padding-left:0">
                    <input class="form-check-input" type="checkbox" role="switch" id="switchAdOrderMgmt" ${masterOn ? 'checked' : ''} onchange="toggleAdFeature('ad_order_mgmt_enabled', this.checked)" style="width:52px;height:26px;cursor:pointer">
                </div>
            </div>
            <!-- 하위 스위치: 블로그 / 플레이스 -->
            <div id="subSwitchPanel" style="opacity:${masterOn ? '1' : '.45'};pointer-events:${masterOn ? 'auto' : 'none'};transition:all .3s">
                <div class="d-flex align-items-center gap-2 mb-2" style="font-size:.76rem;color:#999">
                    <i class="fas fa-level-down-alt"></i>
                    <span>광고 주문 관리가 <strong>ON</strong>일 때 아래 스위치로 세부 기능을 제어합니다. OFF된 기능은 새 광고 주문 탭에서 숨겨집니다.</span>
                </div>
                <div class="row g-3">
                    <div class="col-md-6">
                        <div class="d-flex align-items-center justify-content-between p-3 rounded-3" id="blogSwitchCard" style="background:${blogOn ? 'linear-gradient(135deg,rgba(14,165,233,.06),rgba(14,165,233,.12))' : '#f8f9fa'};border:1px solid ${blogOn ? 'rgba(14,165,233,.2)' : '#eee'};transition:all .3s">
                            <div class="d-flex align-items-center gap-3">
                                <div id="blogSwitchIcon" style="width:42px;height:42px;border-radius:12px;background:${blogOn ? 'linear-gradient(135deg,#0ea5e9,#38bdf8)' : '#ccc'};display:flex;align-items:center;justify-content:center;transition:all .3s">
                                    <i class="fas fa-pen-nib text-white"></i>
                                </div>
                                <div>
                                    <div class="fw-bold" style="font-size:.92rem">블로그 배포</div>
                                    <div style="font-size:.72rem;color:#888">새 광고 주문의 블로그 탭 제어</div>
                                </div>
                            </div>
                            <div class="form-check form-switch mb-0" style="padding-left:0">
                                <input class="form-check-input" type="checkbox" role="switch" id="switchBlogAd" ${blogOn ? 'checked' : ''} onchange="toggleAdFeature('ad_blog_enabled', this.checked)" style="width:48px;height:24px;cursor:pointer">
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="d-flex align-items-center justify-content-between p-3 rounded-3" id="placeSwitchCard" style="background:${placeOn ? 'linear-gradient(135deg,rgba(139,92,246,.06),rgba(139,92,246,.12))' : '#f8f9fa'};border:1px solid ${placeOn ? 'rgba(139,92,246,.2)' : '#eee'};transition:all .3s">
                            <div class="d-flex align-items-center gap-3">
                                <div id="placeSwitchIcon" style="width:42px;height:42px;border-radius:12px;background:${placeOn ? 'linear-gradient(135deg,#8b5cf6,#a78bfa)' : '#ccc'};display:flex;align-items:center;justify-content:center;transition:all .3s">
                                    <i class="fas fa-map-marker-alt text-white"></i>
                                </div>
                                <div>
                                    <div class="fw-bold" style="font-size:.92rem">플레이스 유입</div>
                                    <div style="font-size:.72rem;color:#888">새 광고 주문의 플레이스 탭 제어</div>
                                </div>
                            </div>
                            <div class="form-check form-switch mb-0" style="padding-left:0">
                                <input class="form-check-input" type="checkbox" role="switch" id="switchPlaceAd" ${placeOn ? 'checked' : ''} onchange="toggleAdFeature('ad_place_traffic_enabled', this.checked)" style="width:48px;height:24px;cursor:pointer">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="row g-3 mb-3">
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-warning">${pending}</div><small class="text-muted">대기/검토</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-primary">${running}</div><small class="text-muted">집행중</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-success">${done}</div><small class="text-muted">완료</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm text-center" style="border-radius:12px"><div class="card-body py-2">
            <div class="fs-4 fw-bold text-dark">${orders.length}</div><small class="text-muted">전체</small>
        </div></div></div>
    </div>
    <div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-bullhorn me-2"></i>광고주문 목록</h5>
        <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary active ad-filter-btn" onclick="filterAdOrders('all',this)">전체</button>
            <button class="btn btn-outline-warning ad-filter-btn" onclick="filterAdOrders('pending',this)">대기</button>
            <button class="btn btn-outline-primary ad-filter-btn" onclick="filterAdOrders('running',this)">집행중</button>
            <button class="btn btn-outline-success ad-filter-btn" onclick="filterAdOrders('done',this)">완료</button>
        </div>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm" id="adOrdersTable">
            <thead><tr><th>ID</th><th>가맹점</th><th>유형</th><th>상태</th><th>요청자</th><th>요청일</th><th>관리메모</th><th>상세/집행</th></tr></thead>
            <tbody>${orders.map(o => `<tr data-status="${o.status}">
                <td>${o.id}</td><td>${o.merchant_name}</td>
                <td><span class="badge bg-${o.type==='blog'?'info':'secondary'}">${o.type==='blog'?'블로그':'플레이스'}</span></td>
                <td>${statusBadge(o.status)}</td><td>${o.creator_name}</td><td>${formatDate(o.created_at)}</td>
                <td style="font-size:.78rem;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${o.admin_memo || '-'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="showAdOrderDetail(${o.id})" title="상세보기"><i class="fas fa-eye"></i></button>
                    <select class="form-select form-select-sm d-inline-block" style="width:100px" id="adStatus${o.id}">
                        <option value="requested" ${o.status==='requested'?'selected':''}>요청됨</option>
                        <option value="reviewing" ${o.status==='reviewing'?'selected':''}>검토중</option>
                        <option value="running" ${o.status==='running'?'selected':''}>집행중</option>
                        <option value="done" ${o.status==='done'?'selected':''}>완료</option>
                        <option value="rejected" ${o.status==='rejected'?'selected':''}>반려</option>
                    </select>
                    <button class="btn btn-sm btn-primary ms-1" onclick="executeAdOrder(${o.id})"><i class="fas fa-check"></i></button>
                </td>
            </tr>`).join('')}</tbody>
        </table></div>
    </div></div>`;
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
        
        // 하위 스위치(블로그/플레이스) 시각 업데이트
        if (key === 'ad_blog_enabled' || key === 'ad_place_traffic_enabled') {
            const isBlog = key === 'ad_blog_enabled';
            const cardEl = document.getElementById(isBlog ? 'blogSwitchCard' : 'placeSwitchCard');
            const iconEl = document.getElementById(isBlog ? 'blogSwitchIcon' : 'placeSwitchIcon');
            const colorBase = isBlog ? '14,165,233' : '139,92,246';
            const gradStart = isBlog ? '#0ea5e9' : '#8b5cf6';
            const gradEnd = isBlog ? '#38bdf8' : '#a78bfa';
            if (cardEl) {
                cardEl.style.background = enabled ? `linear-gradient(135deg,rgba(${colorBase},.06),rgba(${colorBase},.12))` : '#f8f9fa';
                cardEl.style.borderColor = enabled ? `rgba(${colorBase},.2)` : '#eee';
            }
            if (iconEl) iconEl.style.background = enabled ? `linear-gradient(135deg,${gradStart},${gradEnd})` : '#ccc';
        }
    } catch(e) { 
        alert('설정 변경 실패: ' + e.message);
        // 실패 시 토글 복원
        const elMap = { ad_order_mgmt_enabled: 'switchAdOrderMgmt', ad_blog_enabled: 'switchBlogAd', ad_place_traffic_enabled: 'switchPlaceAd' };
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

async function showAdOrderDetail(orderId) {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '광고주문 상세 #' + orderId;
    document.getElementById('formModalBody').innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
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
                    <div class="col-md-6"><label class="small text-muted">캠페인명</label><div class="fw-bold">${d.campaign_name || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">주소</label><div>${d.address || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">연락처</label><div>${d.contact || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">링크</label><div style="font-size:.82rem">${d.links || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">주요 키워드</label><div>${d.main_keywords || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">해시태그</label><div>${d.hashtags || '-'}</div></div>
                    <div class="col-12"><label class="small text-muted">설명</label><div style="font-size:.85rem;white-space:pre-line">${d.description || '-'}</div></div>
                    ${d.images && d.images.length > 0 ? `<div class="col-12"><label class="small text-muted">첨부 이미지 (${d.images.length}건)</label><div class="d-flex gap-1 flex-wrap">${d.images.map(img => `<span class="badge bg-light text-dark border">${img.file_path}</span>`).join('')}</div></div>` : ''}
                </div>
            </div>`;
        } else if (o.type === 'place_traffic' && o.place_traffic_detail) {
            const d = o.place_traffic_detail;
            detailHtml = `
            <div class="border rounded p-3 mb-3" style="background:#f8f9fa">
                <h6 class="fw-bold mb-2"><i class="fas fa-map-marker-alt me-1 text-secondary"></i>플레이스 트래픽 상세</h6>
                <div class="row g-2">
                    <div class="col-md-6"><label class="small text-muted">플레이스명/ID</label><div class="fw-bold">${d.place_name_or_id || '-'}</div></div>
                    <div class="col-md-6"><label class="small text-muted">검색 키워드</label><div>${d.search_keywords || '-'}</div></div>
                </div>
            </div>`;
        }
        
        document.getElementById('formModalBody').innerHTML = `
        <div class="mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(14,165,233,.04),rgba(99,102,241,.04))">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                <div>
                    <div class="fw-bold">${o.merchant_name} <span class="badge bg-${o.type==='blog'?'info':'secondary'} ms-1">${o.type==='blog'?'블로그':'플레이스'}</span></div>
                    <div class="text-muted" style="font-size:.82rem">요청자: ${o.creator_name} · 담당: ${o.assigned_admin_name || '미배정'}</div>
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
                        <option value="requested" ${o.status==='requested'?'selected':''}>요청됨</option>
                        <option value="reviewing" ${o.status==='reviewing'?'selected':''}>검토중</option>
                        <option value="running" ${o.status==='running'?'selected':''}>집행중</option>
                        <option value="done" ${o.status==='done'?'selected':''}>완료</option>
                        <option value="rejected" ${o.status==='rejected'?'selected':''}>반려</option>
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
        ${o.admin_memo ? `<div class="border rounded p-3"><h6 class="fw-bold small mb-1"><i class="fas fa-sticky-note me-1"></i>관리 메모 이력</h6><div style="font-size:.82rem;white-space:pre-line">${o.admin_memo}</div></div>` : ''}`;
    } catch(e) {
        document.getElementById('formModalBody').innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
}

async function executeAdOrder(orderId) {
    const status = document.getElementById(`adStatus${orderId}`).value;
    const memo = prompt('관리 메모 (선택사항):');
    try {
        await apiPut(`/api/admin/ad/orders/${orderId}/execute?status=${status}${memo ? '&admin_memo=' + encodeURIComponent(memo) : ''}`, {});
        navigate('admin-adorders');
    } catch(e) { alert('상태변경 실패: ' + e.message); }
}

async function executeAdOrderFromDetail(orderId) {
    const status = document.getElementById('detailAdStatus').value;
    const memo = document.getElementById('detailAdMemo').value;
    try {
        await apiPut(`/api/admin/ad/orders/${orderId}/execute?status=${status}${memo ? '&admin_memo=' + encodeURIComponent(memo) : ''}`, {});
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        alert('광고주문 상태가 변경되었습니다');
        navigate('admin-adorders');
    } catch(e) { alert('상태변경 실패: ' + e.message); }
}

async function loadAdminMetrics(c, t) {
    t.textContent = '광고 지표 입력';
    const merchants = await apiGet('/api/admin/merchants');
    let opts = merchants.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>광고 지표 등록</h5></div><div class="card-body">
        <div class="row g-3">
            <div class="col-md-4"><label class="form-label">가맹점</label><select class="form-select" id="metricMerch">${opts}</select></div>
            <div class="col-md-4"><label class="form-label">플레이스 URL</label><input class="form-control" id="metricUrl"></div>
            <div class="col-md-4"><label class="form-label">날짜</label><input type="date" class="form-control" id="metricDate"></div>
            <div class="col-md-3"><label class="form-label">블로그 리뷰</label><input type="number" class="form-control" id="metricBlog" value="0"></div>
            <div class="col-md-3"><label class="form-label">방문자 리뷰</label><input type="number" class="form-control" id="metricVisitor" value="0"></div>
            <div class="col-md-3"><label class="form-label">플레이스 순위</label><input type="number" class="form-control" id="metricRank"></div>
            <div class="col-md-3 d-flex align-items-end"><button class="btn btn-primary w-100" onclick="saveMetric()"><i class="fas fa-save me-1"></i>저장</button></div>
        </div><div id="metricResult" class="mt-3"></div>
    </div></div>`;
}

async function saveMetric() {
    try {
        await apiPost('/api/admin/ad/metrics', { merchant_id: parseInt(document.getElementById('metricMerch').value), place_url: document.getElementById('metricUrl').value, date: document.getElementById('metricDate').value, blog_review_count: parseInt(document.getElementById('metricBlog').value), visitor_review_count: parseInt(document.getElementById('metricVisitor').value), place_rank: parseInt(document.getElementById('metricRank').value) || null });
        document.getElementById('metricResult').innerHTML = '<div class="alert alert-success">저장 완료!</div>';
    } catch (e) { document.getElementById('metricResult').innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
}

async function loadAdminSalesAssign(c, t) {
    t.textContent = '영업관리자 연결';
    const [assigns, merchants, salesManagers] = await Promise.all([
        apiGet('/api/admin/sales-assignments'),
        apiGet('/api/admin/merchants'),
        apiGet('/api/admin/sales-managers'),
    ]);
    
    const merchantOpts = merchants.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
    const salesOpts = salesManagers.map(u => `<option value="${u.id}">${u.name} (${u.email})</option>`).join('');
    
    c.innerHTML = `
    <div class="alert alert-warning mb-3" style="border-radius:12px;border:none;background:rgba(255,193,7,.08)">
        <div class="d-flex align-items-start">
            <i class="fas fa-handshake me-3 mt-1 fs-5"></i>
            <div>
                <h6 class="fw-bold mb-1">ADPAY 영업관리자 연결 안내</h6>
                <ul class="mb-0 small">
                    <li>영업대행사를 통해 가입한 가맹점은 <strong>최고관리자가 가맹점과 영업관리자를 연결</strong>합니다.</li>
                    <li>영업관리자 수익은 <strong>기본 수수료 3.5% (VAT 별도) 내</strong>에서 배정합니다.</li>
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
                        <input type="number" class="form-control" id="assignRate" value="1.0" step="0.1" min="0" max="3.5" placeholder="1.0">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted">최대 3.5%</small>
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
                        <td class="fw-bold">${a.merchant_name || '-'}</td>
                        <td><i class="fas fa-user-tie text-info me-1"></i>${a.sales_manager_name || '-'}</td>
                        <td class="fw-bold text-primary text-nowrap">${(a.commission_rate*100).toFixed(2)}%</td>
                        <td class="text-success fw-bold text-nowrap">${(10000 * a.commission_rate).toLocaleString('ko-KR', {maximumFractionDigits:0})}원</td>
                        <td class="text-muted small">${a.memo || '-'}</td>
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
        if (rate < 0 || rate > 0.035) { alert('수익률은 0~3.5% 범위에서 설정해주세요.'); return; }
        
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
        el.innerHTML = `<div class="alert alert-danger py-2"><i class="fas fa-exclamation-circle me-1"></i>${e.message}</div>`;
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

    const roleLabelMap = {admin:'최고관리자', sales:'영업관리자', owner:'사장님(원장님)', designer:'직원(디자이너)'};
    const roleBadgeMap = {admin:'danger', sales:'info', owner:'primary', designer:'warning'};

    // 역할별 통계
    const roleCounts = {admin:0, sales:0, owner:0, designer:0};
    users.forEach(u => { if (roleCounts[u.role] !== undefined) roleCounts[u.role]++; });

    let rows = users.map(u => {
        const rLabel = roleLabelMap[u.role] || u.role;
        const rColor = roleBadgeMap[u.role] || 'secondary';
        let extra = '';
        if (u.role === 'owner' && u.merchant_name) extra = `<small class="text-muted d-block">${u.merchant_name}</small>`;
        if (u.role === 'sales' && u.assigned_merchant_count > 0) extra = `<small class="text-muted d-block">담당 ${u.assigned_merchant_count}개 가맹점</small>`;
        return `<tr>
            <td>${u.id}</td>
            <td><div class="fw-bold">${u.name}</div>${extra}</td>
            <td>${u.email}</td>
            <td><span class="badge bg-${rColor}">${rLabel}</span></td>
            <td>${u.phone || '-'}</td>
            <td>${u.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
            <td class="small">${formatDate(u.created_at)}</td>
            <td>
                <div class="d-flex gap-1">
                    <select class="form-select form-select-sm" style="width:110px" id="roleSelect${u.id}">
                        <option value="admin" ${u.role==='admin'?'selected':''}>최고관리자</option>
                        <option value="sales" ${u.role==='sales'?'selected':''}>영업관리자</option>
                        <option value="owner" ${u.role==='owner'?'selected':''}>사장님(원장님)</option>
                        <option value="designer" ${u.role==='designer'?'selected':''}>직원(디자이너)</option>
                    </select>
                    <button class="btn btn-sm btn-primary" onclick="changeUserRole(${u.id})" title="역할 변경"><i class="fas fa-save"></i></button>
                    <button class="btn btn-sm btn-outline-${u.is_active?'danger':'success'}" onclick="toggleUserActive(${u.id})" title="${u.is_active?'비활성화':'활성화'}">
                        <i class="fas fa-${u.is_active?'ban':'check'}"></i>
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
            <div class="fs-3 fw-bold text-primary">${roleCounts.owner}</div><small class="text-muted">사장님(원장님)</small>
        </div></div></div>
        <div class="col-md-3"><div class="card border-0 shadow-sm"><div class="card-body text-center py-3">
            <div class="fs-3 fw-bold text-warning">${roleCounts.designer}</div><small class="text-muted">직원(디자이너)</small>
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
    if (!confirm(`이 사용자의 역할을 "${({admin:'최고관리자',sales:'영업관리자',owner:'사장님(원장님)',designer:'직원(디자이너)'})[newRole]}"(으)로 변경하시겠습니까?`)) return;
    try {
        await apiPut(`/api/admin/users/${uid}/role?role=${newRole}`, {});
        navigate('admin-users');
    } catch (e) { alert('역할 변경 실패: ' + e.message); }
}

async function toggleUserActive(uid) {
    if (!confirm('이 사용자의 활성 상태를 변경하시겠습니까?')) return;
    try {
        await apiPut(`/api/admin/users/${uid}/toggle-active`, {});
        navigate('admin-users');
    } catch (e) { alert('상태 변경 실패: ' + e.message); }
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

    let cards = users.map(u => {
        const myAssigns = assignMap[u.id] || [];
        const totalCommission = myAssigns.reduce((s, a) => s + a.commission_rate, 0);
        const assignRows = myAssigns.map(a => `
            <tr>
                <td class="fw-bold">${a.merchant_name || '-'}</td>
                <td class="text-primary fw-bold">${(a.commission_rate*100).toFixed(2)}%</td>
                <td>${(10000 * a.commission_rate).toLocaleString('ko-KR',{maximumFractionDigits:0})}원</td>
                <td>${a.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
            </tr>`).join('');

        return `
        <div class="col-md-6">
            <div class="card border-0 shadow-sm h-100">
                <div class="card-header bg-info bg-opacity-10 border-0 d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-0 fw-bold"><i class="fas fa-user-tie text-info me-2"></i>${u.name}</h6>
                        <small class="text-muted">${u.email}</small>
                    </div>
                    <div class="text-end">
                        ${u.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}
                    </div>
                </div>
                <div class="card-body">
                    <div class="row g-2 mb-3 text-center">
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-primary">${myAssigns.length}</div><small class="text-muted">담당 가맹점</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-success">${myAssigns.filter(a=>a.is_active).length}</div><small class="text-muted">활성 배정</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-warning">${(totalCommission*100/Math.max(myAssigns.length,1)).toFixed(1)}%</div><small class="text-muted">평균 커미션</small></div></div>
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
    <div class="alert alert-info mb-3">
        <div class="d-flex align-items-start">
            <i class="fas fa-user-tie me-3 mt-1 fs-5"></i>
            <div>
                <h6 class="fw-bold mb-1">영업관리자 관리</h6>
                <ul class="mb-0 small">
                    <li>영업관리자 계정 현황과 담당 가맹점 배정 내역을 한눈에 확인합니다.</li>
                    <li>새 영업관리자 등록은 <strong>사용자 목록</strong>에서 역할을 변경하거나, 회원가입 시 영업관리자로 가입합니다.</li>
                    <li>가맹점 연결/커미션 설정은 <strong>영업관리자 연결</strong> 또는 <strong>수수료 정책</strong> 메뉴에서 가능합니다.</li>
                </ul>
            </div>
        </div>
    </div>
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
    <div class="row g-3">
        ${cards || '<div class="col-12"><div class="text-center py-5 text-muted"><i class="fas fa-user-tie fa-3x mb-3 d-block opacity-50"></i><p>등록된 영업관리자가 없습니다.</p><small>사용자 목록에서 역할을 "영업관리자"로 변경하거나, 회원가입 시 영업관리자로 등록하세요.</small></div></div>'}
    </div>`;
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
                <h6 class="fw-bold"><i class="fas fa-store text-primary me-2"></i>${m.name}</h6>
                <p class="text-muted small mb-1">${m.address||''} | ${m.phone||''}</p>
                <p class="mb-2">커미션율: <strong class="text-primary">${(m.commission_rate*100).toFixed(1)}%</strong></p>
                <div class="d-flex gap-2 mb-2">
                    <select class="form-select form-select-sm" id="salesRange${m.id}"><option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option></select>
                    <button class="btn btn-sm btn-primary" onclick="loadSalesStats(${m.id})"><i class="fas fa-search"></i></button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="loadSalesBreakdown(${m.id})" title="원장/디자이너 분배"><i class="fas fa-sitemap"></i></button>
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
    document.getElementById(`salesStats${mid}`).innerHTML = `<div class="bg-light rounded p-2 small">
        결제 <strong>${stats.transaction_count}건</strong> | 총매출 <strong>${formatMoney(stats.gross_amount)}</strong><br>
        PG수수료 ${formatMoney(stats.pg_fee)}${commHtml}
    </div>`;
}

async function loadSalesBreakdown(mid) {
    const range = document.getElementById(`salesRange${mid}`).value;
    const el = document.getElementById(`salesStats${mid}`);
    el.innerHTML = '<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-primary"></div></div>';
    try {
        const data = await apiGet(`/api/sales/merchants/${mid}/breakdown?range=${range}`);
        el.innerHTML = renderSettlementBreakdown(data);
    } catch (e) { el.innerHTML = `<div class="alert alert-danger small">${e.message}</div>`; }
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
                    <tbody>${payouts.map(p => `<tr><td>${p.id}</td><td class="fw-bold">${formatMoney(p.amount)}</td><td>${p.bank_info||'-'}</td><td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td></tr>`).join('')}</tbody>
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
    } catch (e) { document.getElementById('payoutResult').innerHTML = `<span class="text-danger">${e.message}</span>`; }
}

async function loadSalesPayoutHistory(c, t) {
    t.textContent = '출금내역';
    const payouts = await apiGet('/api/sales/payout-requests');
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>전체 출금내역</h5></div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm">
            <thead><tr><th>ID</th><th>금액</th><th>은행정보</th><th>상태</th><th>요청일</th></tr></thead>
            <tbody>${payouts.map(p => `<tr><td>${p.id}</td><td class="fw-bold">${formatMoney(p.amount)}</td><td>${p.bank_info||'-'}</td><td>${statusBadge(p.status)}</td><td>${formatDate(p.created_at)}</td></tr>`).join('') || '<tr><td colspan="5" class="text-muted text-center py-3">없음</td></tr>'}</tbody>
        </table></div></div></div>`;
}

// ═══════════════════════════════════════════════════════════
// OWNER PAGES
// ═══════════════════════════════════════════════════════════

async function loadOwnerTransactions(c, t) {
    t.textContent = '결제 내역';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">결제 내역</h5>
        <select class="form-select form-select-sm" style="width:120px" id="ownerTxRange" onchange="reloadOwnerTx()">
            <option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option>
        </select>
    </div><div class="card-body">
        <div id="ownerTxBody"><div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div></div>
    </div></div>`;
    reloadOwnerTx();
}

async function reloadOwnerTx() {
    const range = document.getElementById('ownerTxRange').value;
    const txns = await apiGet(`/api/owner/transactions?range=${range}`);
    const total = txns.reduce((s, tx) => s + tx.amount, 0);
    document.getElementById('ownerTxBody').innerHTML = `
    <div class="d-flex justify-content-between mb-3">
        <span>합계: <strong class="text-primary">${formatMoney(total)}</strong> (${txns.length}건)</span>
    </div>
    <div class="table-responsive"><table class="table table-hover table-sm">
        <thead><tr><th>ID</th><th>금액</th><th>할부</th><th>카드</th><th>직원</th><th>승인번호</th><th>일시</th></tr></thead>
        <tbody>${txns.map(tx => `<tr>
            <td>${tx.id}</td><td class="fw-bold">${formatMoney(tx.amount)}</td>
            <td>${tx.installment_months||'일시불'}</td><td>${tx.card_brand||'-'}</td>
            <td>${tx.staff_name||'<span class="text-muted">사장님</span>'}</td><td><code>${tx.approval_code||'-'}</code></td>
            <td>${formatDate(tx.created_at)}</td>
        </tr>`).join('')}</tbody>
    </table></div>`;
}

async function loadOwnerStaff(c, t) {
    t.textContent = '직원 관리';
    const staff = await apiGet('/api/owner/staff');
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h5 class="mb-0">직원 · 디자이너 목록</h5>
        <div class="d-flex gap-2">
            <button class="btn btn-primary btn-sm" onclick="showNewDesignerForm()"><i class="fas fa-user-plus me-1"></i>디자이너 계정 등록</button>
            <button class="btn btn-outline-secondary btn-sm" onclick="showNewStaffForm()"><i class="fas fa-plus me-1"></i>직원 추가(계정 없음)</button>
        </div>
    </div><div class="card-body">
        <div class="alert alert-light border small mb-3"><i class="fas fa-info-circle text-primary me-1"></i>
            <strong>디자이너 계정 등록</strong>은 로그인 계정을 만들어 우리 미용실 소속으로 귀속시킵니다(디자이너는 직접 회원가입 불가). <strong>분배율</strong>은 결제액에서 PG·영업수수료를 뺀 <strong>분배가능액 중 디자이너 몫</strong> 비율이며, 나머지는 원장(사장님) 몫입니다.</div>
        <div class="table-responsive"><table class="table table-hover align-middle">
            <thead><tr><th>ID</th><th>이름</th><th>코드</th><th>디자이너 분배율</th><th>상태</th><th>액션</th></tr></thead>
            <tbody>${staff.map(s => `<tr>
                <td>${s.id}</td><td class="fw-bold">${s.name}</td><td><code>${s.staff_code}</code></td>
                <td style="max-width:200px">
                    <div class="input-group input-group-sm">
                        <input type="number" class="form-control" id="share_${s.id}" value="${Math.round((s.share_rate??0.5)*100)}" min="0" max="100" step="1" style="max-width:80px">
                        <span class="input-group-text">%</span>
                        <button class="btn btn-outline-success" onclick="saveStaffShareRate(${s.id})" title="분배율 저장"><i class="fas fa-save"></i></button>
                    </div>
                    <small class="text-muted">원장 몫 <span id="ownerShare_${s.id}">${100-Math.round((s.share_rate??0.5)*100)}</span>%</small>
                </td>
                <td>${s.is_active?'<span class="badge bg-success">활성</span>':'<span class="badge bg-danger">비활성</span>'}</td>
                <td><button class="btn btn-sm btn-outline-${s.is_active?'danger':'success'}" onclick="toggleStaff(${s.id},${!s.is_active})">${s.is_active?'비활성화':'활성화'}</button></td>
            </tr>`).join('')}</tbody>
        </table></div></div></div>`;
    // 입력 시 원장 몫 즉시 반영
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
        alert(`분배율 저장 완료!\n디자이너 ${pct}% / 원장 ${100-pct}%`);
    } catch (e) { alert('저장 실패: ' + e.message); }
}

async function showNewStaffForm() {
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '직원 추가';
    body.innerHTML = `<div class="row g-3">
        <div class="col-md-6"><label class="form-label">이름</label><input class="form-control" id="fStaffName"></div>
        <div class="col-md-6"><label class="form-label">직원 코드</label><input class="form-control" id="fStaffCode" placeholder="단말기 입력용 번호"></div>
        <div class="col-md-6"><label class="form-label">디자이너 분배율 (%)</label><input class="form-control" id="fStaffShare" type="number" value="50" min="0" max="100" step="1"><small class="text-muted">분배가능액 중 디자이너 몫</small></div>
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
    const body = document.getElementById('formModalBody');
    document.getElementById('formModalTitle').textContent = '디자이너 계정 등록';
    body.innerHTML = `<div class="row g-3">
        <div class="col-12"><div class="alert alert-info py-2 mb-1 small"><i class="fas fa-id-card-clip me-1"></i>디자이너 로그인 계정을 생성하고 <strong>우리 미용실 소속</strong>으로 등록합니다.</div></div>
        <div class="col-md-6"><label class="form-label">이름 <span class="text-danger">*</span></label><input class="form-control" id="fDsgName"></div>
        <div class="col-md-6"><label class="form-label">직원 코드 <span class="text-danger">*</span></label><input class="form-control" id="fDsgCode" placeholder="단말기 입력용 번호"></div>
        <div class="col-md-6"><label class="form-label">이메일(로그인 ID) <span class="text-danger">*</span></label><input class="form-control" id="fDsgEmail" type="email" placeholder="designer@example.com"></div>
        <div class="col-md-6"><label class="form-label">비밀번호 <span class="text-danger">*</span></label><input class="form-control" id="fDsgPw" type="text" placeholder="6자 이상"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="fDsgPhone" placeholder="010-0000-0000"></div>
        <div class="col-md-6"><label class="form-label">디자이너 분배율 (%)</label><input class="form-control" id="fDsgShare" type="number" value="50" min="0" max="100" step="1"></div>
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
            alert(res.message || '디자이너 계정이 등록되었습니다.');
            navigate('owner-staff');
        } catch (e) { result.innerHTML = `<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
    };
    new bootstrap.Modal(document.getElementById('formModal')).show();
}

// ─── 정산 분배 (디자이너/원장) ─────────────────────────────
function rangeSelectHtml(id, current) {
    const opts = [['month','이번달'],['week','이번주'],['day','오늘'],['all','전체']];
    return `<select class="form-select form-select-sm" id="${id}" style="max-width:140px">${opts.map(([v,l])=>`<option value="${v}" ${v===current?'selected':''}>${l}</option>`).join('')}</select>`;
}

function renderSettlementBreakdown(data) {
    const showComm = data.show_sales_commission;
    const commRow = showComm
        ? `<div class="col-6 col-md-3"><div class="bg-warning bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-warning">${formatMoney(data.sales_commission)}</div><small class="text-muted">영업수수료${data.sales_commission_rate!=null?` (${(data.sales_commission_rate*100).toFixed(1)}%)`:''}</small></div></div>`
        : '';
    const colClass = showComm ? 'col-6 col-md-3' : 'col-6 col-md-4';
    const designerRows = (data.designers||[]).map(d => `<tr>
        <td class="fw-bold">${d.name}</td>
        <td><code>${d.staff_code}</code></td>
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
        <div class="${colClass}"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold text-secondary">${formatMoney(data.pg_fee)}</div><small class="text-muted">PG 수수료</small></div></div>
        ${commRow}
        <div class="${colClass}"><div class="bg-primary bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-primary">${formatMoney(data.distributable)}</div><small class="text-muted">분배가능액</small></div></div>
    </div>
    <div class="row g-2 mb-3">
        <div class="col-6"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-5 fw-bold text-primary">${formatMoney(data.designer_total)}</div><small class="text-muted">디자이너 분배 합계</small></div></div>
        <div class="col-6"><div class="bg-success bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-5 fw-bold text-success">${formatMoney(data.owner_amount)}</div><small class="text-muted">원장(사장님) 몫</small></div></div>
    </div>
    <div class="table-responsive"><table class="table table-sm table-hover align-middle">
        <thead class="table-light"><tr>
            <th>디자이너</th><th>코드</th><th class="text-end">매출</th><th class="text-end">PG</th>
            ${showComm?'<th class="text-end">영업</th>':''}
            <th class="text-end">분배가능</th><th class="text-center">분배율</th>
            <th class="text-end">디자이너 몫</th><th class="text-end">원장 몫</th>
        </tr></thead>
        <tbody>${designerRows || `<tr><td colspan="9" class="text-center text-muted py-3">데이터 없음</td></tr>`}${unassigned}</tbody>
    </table></div>
    ${!showComm ? '<small class="text-muted"><i class="fas fa-eye-slash me-1"></i>영업수수료 항목은 관리자 설정에 의해 표시되지 않습니다.</small>' : ''}`;
}

async function loadOwnerSettlement(c, t) {
    t.textContent = '정산 분배';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">디자이너 정산 분배</h5>${rangeSelectHtml('ownerSettleRange','month')}
    </div><div class="card-body" id="ownerSettleBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div></div>`;
    const render = async () => {
        const range = document.getElementById('ownerSettleRange').value;
        const body = document.getElementById('ownerSettleBody');
        body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
        try {
            const data = await apiGet(`/api/owner/settlement-breakdown?range=${range}`);
            body.innerHTML = renderSettlementBreakdown(data);
        } catch (e) { body.innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
    };
    document.getElementById('ownerSettleRange').addEventListener('change', render);
    render();
}

async function loadDesignerSettlement(c, t) {
    t.textContent = '정산 분배';
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">내 정산 분배</h5>${rangeSelectHtml('dsgSettleRange','month')}
    </div><div class="card-body" id="dsgSettleBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div></div>`;
    const render = async () => {
        const range = document.getElementById('dsgSettleRange').value;
        const body = document.getElementById('dsgSettleBody');
        body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
        try {
            const d = await apiGet(`/api/designer/settlement?range=${range}`);
            const showComm = d.show_sales_commission;
            body.innerHTML = `
            <div class="row g-2 mb-3">
                <div class="col-6 col-md-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(d.gross)}</div><small class="text-muted">내 매출 (${d.count}건)</small></div></div>
                <div class="col-6 col-md-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold text-secondary">${formatMoney(d.pg_fee)}</div><small class="text-muted">PG 수수료</small></div></div>
                ${showComm?`<div class="col-6 col-md-3"><div class="bg-warning bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-warning">${formatMoney(d.sales_commission)}</div><small class="text-muted">영업수수료${d.sales_commission_rate!=null?` (${(d.sales_commission_rate*100).toFixed(1)}%)`:''}</small></div></div>`:''}
                <div class="col-6 col-md-3"><div class="bg-primary bg-opacity-10 rounded-3 p-2 text-center"><div class="fw-bold text-primary">${formatMoney(d.distributable)}</div><small class="text-muted">분배가능액</small></div></div>
            </div>
            <div class="row g-2">
                <div class="col-6"><div class="bg-primary bg-opacity-10 rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-primary">${formatMoney(d.designer_amount)}</div><small class="text-muted">내 몫 (분배율 ${Math.round((d.share_rate||0)*100)}%)</small></div></div>
                <div class="col-6"><div class="bg-light rounded-3 p-3 text-center"><div class="fs-4 fw-bold text-success">${formatMoney(d.owner_amount)}</div><small class="text-muted">원장 몫</small></div></div>
            </div>
            ${!showComm?'<small class="text-muted mt-2 d-block"><i class="fas fa-eye-slash me-1"></i>영업수수료 항목은 관리자 설정에 의해 표시되지 않습니다.</small>':''}`;
        } catch (e) { body.innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
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
        ${row('owner','사장님(원장)','정산 분배에서 영업수수료 항목 표시', v.owner, false)}
        ${row('designer','디자이너','내 정산에서 영업수수료 항목 표시', v.designer, false)}
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
    c.innerHTML = `<div class="card data-card"><div class="card-header"><h5>직원별 매출 조회</h5></div><div class="card-body">
        <div class="row g-3 mb-3">
            <div class="col-md-4"><label class="form-label">직원</label><select class="form-select" id="staffSalesSel">${staff.map(s=>`<option value="${s.id}">${s.name} (코드:${s.staff_code})</option>`).join('')}</select></div>
            <div class="col-md-4"><label class="form-label">기간</label><select class="form-select" id="staffSalesRange"><option value="all">전체</option><option value="month">이번달</option><option value="week">이번주</option><option value="day">오늘</option></select></div>
            <div class="col-md-4 d-flex align-items-end"><button class="btn btn-primary w-100" onclick="loadStaffSalesData()"><i class="fas fa-search me-1"></i>조회</button></div>
        </div><div id="staffSalesResult"></div>
    </div></div>`;
}

async function loadStaffSalesData() {
    const sid = document.getElementById('staffSalesSel').value;
    const range = document.getElementById('staffSalesRange').value;
    const data = await apiGet(`/api/owner/staff/${sid}/sales?range=${range}`);
    document.getElementById('staffSalesResult').innerHTML = `
    <div class="alert alert-info"><strong>${data.staff_name}</strong> | 기간: ${data.range} | 건수: <strong>${data.count}</strong> | 합계: <strong>${formatMoney(data.total_amount)}</strong></div>
    <div class="table-responsive"><table class="table table-sm">
        <thead><tr><th>ID</th><th>금액</th><th>승인일</th><th>등록일</th></tr></thead>
        <tbody>${data.transactions.map(tx=>`<tr><td>${tx.id}</td><td class="fw-bold">${formatMoney(tx.amount)}</td><td>${formatDate(tx.approved_at)}</td><td>${formatDate(tx.created_at)}</td></tr>`).join('')}</tbody>
    </table></div>`;
}

async function loadOwnerDailySummary(c, t) {
    t.textContent = '일별 결제내역';
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
        grid.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>';
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
            grid.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
        }
    }

    document.getElementById('calPrev').onclick = () => { calMonth--; if (calMonth < 1) { calMonth = 12; calYear--; } renderCalendar(); };
    document.getElementById('calNext').onclick = () => { calMonth++; if (calMonth > 12) { calMonth = 1; calYear++; } renderCalendar(); };
    renderCalendar();
}

// 날짜 클릭 시 상세 결제내역 팝업
async function showDailyDetail(dateStr) {
    const modalEl = document.getElementById('formModal');
    const titleEl = document.getElementById('formModalTitle');
    const bodyEl = document.getElementById('formModalBody');
    const saveBtn = document.getElementById('formModalSave');
    saveBtn.style.display = 'none';

    titleEl.innerHTML = `<i class="fas fa-calendar-day text-info me-2"></i>${dateStr} 결제내역`;
    bodyEl.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> 로딩중...</div>';
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
                        <td>${tx.card_brand||'-'}</td>
                        <td>${tx.staff_name||'<span class="text-muted">사장님</span>'}</td>
                        <td><code>${tx.approval_code||'-'}</code></td>
                        <td class="text-muted" style="font-size:.8rem;">${tx.created_at ? tx.created_at.split(' ')[1]?.substring(0,5) || formatDate(tx.created_at) : '-'}</td>
                    </tr>`).join('')}</tbody>
                </table></div>`;
        }
    } catch (e) {
        bodyEl.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
    saveBtn.style.display = '';
}

async function loadOwnerAnalysis(c, t) {
    t.textContent = '광고 분석';
    c.innerHTML = `
    <!-- 헤더 + 기간 선택 + 관리 버튼 -->
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <h5 class="fw-bold mb-0"><i class="fas fa-chart-line text-primary me-2"></i>매장 vs 경쟁업체 비교 분석</h5>
            <small class="text-muted">플레이스 순위, 블로그/방문자 리뷰를 한눈에 비교하세요</small>
        </div>
        <div class="d-flex gap-2 align-items-center">
            <select class="form-select form-select-sm" style="width:110px" id="analysisRange" onchange="reloadAnalysis()">
                <option value="all">전체</option><option value="month">1개월</option><option value="week">1주</option><option value="day">1일</option>
            </select>
            <button class="btn btn-sm btn-outline-primary" onclick="toggleManagePanel()">
                <i class="fas fa-cog me-1"></i>관리
            </button>
        </div>
    </div>

    <!-- 관리 패널 (토글) -->
    <div id="managePanel" style="display:none" class="mb-3">
        <div class="card border-primary border-opacity-25">
            <div class="card-body">
                <div class="row g-3">
                    <div class="col-md-6">
                        <h6 class="fw-bold text-primary mb-2"><i class="fas fa-map-marker-alt me-1"></i>우리 매장 프로필 추가</h6>
                        <div class="input-group input-group-sm mb-2">
                            <input class="form-control" id="newProfileUrl" placeholder="네이버 플레이스 URL">
                            <input class="form-control" id="newProfileNick" placeholder="별칭 (예: 본점)" style="max-width:120px">
                            <button class="btn btn-primary" onclick="addPlaceProfile()"><i class="fas fa-plus"></i></button>
                        </div>
                        <div id="profileList"></div>
                    </div>
                    <div class="col-md-6">
                        <h6 class="fw-bold text-danger mb-2"><i class="fas fa-users me-1"></i>경쟁업체 추가</h6>
                        <div class="input-group input-group-sm mb-2">
                            <input class="form-control" id="newCompUrl" placeholder="경쟁업체 플레이스 URL">
                            <input class="form-control" id="newCompMemo" placeholder="업체명" style="max-width:120px">
                            <button class="btn btn-danger" onclick="addCompetitor()"><i class="fas fa-plus"></i></button>
                        </div>
                        <div id="competitorList"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- 비교 요약 대시보드 -->
    <div id="analysisSummary"><div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="text-muted mt-2">분석 데이터를 불러오는 중...</p></div></div>

    <!-- 상세 데이터 영역 -->
    <div id="analysisDetail" class="mt-3"></div>`;

    reloadAnalysis();
}

function toggleManagePanel() {
    const panel = document.getElementById('managePanel');
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
    if (panel.style.display !== 'none') loadManageLists();
}

async function loadManageLists() {
    try {
        const data = await apiGet('/api/owner/ad/analysis?range=all');
        // 프로필 목록
        let profileHtml = '';
        if (data.profiles && data.profiles.length > 0) {
            profileHtml = data.profiles.map(p => `<span class="badge bg-primary bg-opacity-10 text-primary me-1 mb-1 px-2 py-1">${p.nickname||p.place_url} <i class="fas fa-times ms-1" style="cursor:pointer" onclick="removePlaceProfile(${p.id})"></i></span>`).join('');
        } else {
            profileHtml = '<small class="text-muted">등록된 프로필이 없습니다</small>';
        }
        document.getElementById('profileList').innerHTML = profileHtml;

        // 경쟁업체 목록
        let compHtml = '';
        if (data.competitor_list && data.competitor_list.length > 0) {
            compHtml = data.competitor_list.map(c => `<span class="badge bg-danger bg-opacity-10 text-danger me-1 mb-1 px-2 py-1">${c.memo||c.place_url} <i class="fas fa-times ms-1" style="cursor:pointer" onclick="removeCompetitor(${c.id})"></i></span>`).join('');
        } else {
            compHtml = '<small class="text-muted">등록된 경쟁업체가 없습니다</small>';
        }
        document.getElementById('competitorList').innerHTML = compHtml;
    } catch (e) { console.error(e); }
}

async function addPlaceProfile() {
    const url = document.getElementById('newProfileUrl').value.trim();
    const nick = document.getElementById('newProfileNick').value.trim();
    if (!url) { alert('플레이스 URL을 입력하세요'); return; }
    try {
        await apiPost('/api/owner/ad/place-profiles', { place_url: url, nickname: nick || null });
        document.getElementById('newProfileUrl').value = '';
        document.getElementById('newProfileNick').value = '';
        loadManageLists();
        reloadAnalysis();
    } catch (e) { alert('등록 실패: ' + e.message); }
}

async function addCompetitor() {
    const url = document.getElementById('newCompUrl').value.trim();
    const memo = document.getElementById('newCompMemo').value.trim();
    if (!url) { alert('경쟁업체 URL을 입력하세요'); return; }
    try {
        await apiPost('/api/owner/ad/competitors', { competitor_place_url: url, memo: memo || null });
        document.getElementById('newCompUrl').value = '';
        document.getElementById('newCompMemo').value = '';
        loadManageLists();
        reloadAnalysis();
    } catch (e) { alert('등록 실패: ' + e.message); }
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

function trendIcon(value, reverse) {
    // reverse: 순위의 경우 값이 양수면 순위 상승(좋음)
    if (value === 0 || value === null || value === undefined) return '<span class="text-muted">-</span>';
    const isGood = reverse ? value > 0 : value > 0;
    const arrow = value > 0 ? '<i class="fas fa-arrow-up"></i>' : '<i class="fas fa-arrow-down"></i>';
    const cls = isGood ? 'text-success' : 'text-danger';
    return `<span class="${cls} small fw-bold">${arrow} ${Math.abs(value)}</span>`;
}

async function reloadAnalysis() {
    try {
        const range = document.getElementById('analysisRange').value;
        const summary = await apiGet(`/api/owner/ad/analysis/summary?range=${range}`);
        const detail = await apiGet(`/api/owner/ad/analysis?range=${range}`);
        
        const comp = summary.comparison;
        let summaryHtml = '';

        // ── 인사이트 카드 ──
        if (comp.insights && comp.insights.length > 0) {
            const insightCards = comp.insights.map(ins => {
                const icon = ins.type === 'positive' ? 'check-circle text-success' : ins.type === 'warning' ? 'exclamation-triangle text-warning' : 'info-circle text-info';
                const bg = ins.type === 'positive' ? 'success' : ins.type === 'warning' ? 'warning' : 'info';
                return `<div class="alert alert-${bg} bg-${bg} bg-opacity-10 border-0 py-2 px-3 mb-2">
                    <i class="fas fa-${icon} me-2"></i><span class="small">${ins.text}</span>
                </div>`;
            }).join('');
            summaryHtml += `<div class="mb-3">${insightCards}</div>`;
        }

        // ── 비교 요약 카드 ──
        summaryHtml += `<div class="row g-3 mb-4">
            <!-- 블로그 리뷰 비교 -->
            <div class="col-md-4">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body text-center">
                        <div class="mb-2"><i class="fas fa-blog text-info fs-4"></i></div>
                        <h6 class="text-muted small text-uppercase mb-3">블로그 리뷰</h6>
                        <div class="row">
                            <div class="col-6 border-end">
                                <div class="fs-3 fw-bold text-primary">${comp.my_avg_blog || 0}</div>
                                <small class="text-muted">우리 매장</small>
                            </div>
                            <div class="col-6">
                                <div class="fs-3 fw-bold text-danger">${comp.comp_avg_blog || 0}</div>
                                <small class="text-muted">경쟁업체</small>
                            </div>
                        </div>
                        ${comp.my_avg_blog !== 0 || comp.comp_avg_blog !== 0 ? `
                        <div class="mt-2">
                            <div class="progress" style="height:6px">
                                <div class="progress-bar bg-primary" style="width:${comp.my_avg_blog + comp.comp_avg_blog > 0 ? Math.round(comp.my_avg_blog / (comp.my_avg_blog + comp.comp_avg_blog) * 100) : 50}%"></div>
                                <div class="progress-bar bg-danger" style="width:${comp.my_avg_blog + comp.comp_avg_blog > 0 ? Math.round(comp.comp_avg_blog / (comp.my_avg_blog + comp.comp_avg_blog) * 100) : 50}%"></div>
                            </div>
                        </div>` : ''}
                    </div>
                </div>
            </div>
            <!-- 방문자 리뷰 비교 -->
            <div class="col-md-4">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body text-center">
                        <div class="mb-2"><i class="fas fa-users text-success fs-4"></i></div>
                        <h6 class="text-muted small text-uppercase mb-3">방문자 리뷰</h6>
                        <div class="row">
                            <div class="col-6 border-end">
                                <div class="fs-3 fw-bold text-primary">${comp.my_avg_visitor || 0}</div>
                                <small class="text-muted">우리 매장</small>
                            </div>
                            <div class="col-6">
                                <div class="fs-3 fw-bold text-danger">${comp.comp_avg_visitor || 0}</div>
                                <small class="text-muted">경쟁업체</small>
                            </div>
                        </div>
                        ${comp.my_avg_visitor !== 0 || comp.comp_avg_visitor !== 0 ? `
                        <div class="mt-2">
                            <div class="progress" style="height:6px">
                                <div class="progress-bar bg-primary" style="width:${comp.my_avg_visitor + comp.comp_avg_visitor > 0 ? Math.round(comp.my_avg_visitor / (comp.my_avg_visitor + comp.comp_avg_visitor) * 100) : 50}%"></div>
                                <div class="progress-bar bg-danger" style="width:${comp.my_avg_visitor + comp.comp_avg_visitor > 0 ? Math.round(comp.comp_avg_visitor / (comp.my_avg_visitor + comp.comp_avg_visitor) * 100) : 50}%"></div>
                            </div>
                        </div>` : ''}
                    </div>
                </div>
            </div>
            <!-- 플레이스 순위 비교 -->
            <div class="col-md-4">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body text-center">
                        <div class="mb-2"><i class="fas fa-trophy text-warning fs-4"></i></div>
                        <h6 class="text-muted small text-uppercase mb-3">플레이스 순위</h6>
                        <div class="row">
                            <div class="col-6 border-end">
                                <div class="fs-3 fw-bold text-primary">${comp.my_latest_rank ? comp.my_latest_rank + '위' : '-'}</div>
                                <small class="text-muted">우리 매장</small>
                            </div>
                            <div class="col-6">
                                <div class="fs-3 fw-bold text-danger">${comp.comp_latest_rank ? comp.comp_latest_rank + '위' : '-'}</div>
                                <small class="text-muted">경쟁업체</small>
                            </div>
                        </div>
                        ${comp.my_best_rank || comp.comp_best_rank ? `
                        <div class="mt-2 small text-muted">
                            최고순위: <span class="text-primary fw-bold">${comp.my_best_rank ? comp.my_best_rank + '위' : '-'}</span> vs 
                            <span class="text-danger fw-bold">${comp.comp_best_rank ? comp.comp_best_rank + '위' : '-'}</span>
                        </div>` : ''}
                    </div>
                </div>
            </div>
        </div>`;

        document.getElementById('analysisSummary').innerHTML = summaryHtml;

        // ── 상세 데이터 (우리 매장 + 경쟁업체 비교 테이블) ──
        let detailHtml = '';

        // 우리 매장 상세
        detailHtml += `<div class="card border-0 shadow-sm mb-3">
            <div class="card-header bg-primary bg-opacity-10 border-0 d-flex justify-content-between align-items-center">
                <h6 class="mb-0 fw-bold"><i class="fas fa-map-marker-alt text-primary me-2"></i>우리 매장 상세</h6>
                <span class="badge bg-primary">${summary.my_places.length}개 프로필</span>
            </div>
            <div class="card-body">`;

        if (summary.my_places.length === 0) {
            detailHtml += `<div class="text-center py-4 text-muted">
                <i class="fas fa-map-marker-alt fa-2x mb-2 d-block opacity-50"></i>
                <p class="mb-1">등록된 플레이스 프로필이 없습니다</p>
                <small>상단 <strong>관리</strong> 버튼을 눌러 프로필을 추가하세요</small>
            </div>`;
        } else {
            summary.my_places.forEach(place => {
                const m = place.metrics;
                detailHtml += `<div class="border rounded-3 p-3 mb-2">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0 fw-bold"><i class="fas fa-store text-primary me-1"></i>${place.nickname}</h6>
                        ${m ? `<small class="text-muted">최신: ${m.latest_date || '-'}</small>` : ''}
                    </div>`;
                if (m) {
                    detailHtml += `<div class="row g-2 text-center">
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-primary">${m.latest_blog_reviews}</div><small class="text-muted">블로그</small> ${trendIcon(m.blog_trend, false)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-success">${m.latest_visitor_reviews}</div><small class="text-muted">방문자</small> ${trendIcon(m.visitor_trend, false)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-warning">${m.latest_rank ? m.latest_rank + '위' : '-'}</div><small class="text-muted">순위</small> ${trendIcon(m.rank_trend, true)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-info">${m.data_count}</div><small class="text-muted">데이터</small></div></div>
                    </div>`;
                } else {
                    detailHtml += `<p class="text-muted small mb-0">수집된 데이터가 없습니다</p>`;
                }
                detailHtml += '</div>';
            });
        }
        detailHtml += '</div></div>';

        // 경쟁업체 상세
        detailHtml += `<div class="card border-0 shadow-sm mb-3">
            <div class="card-header bg-danger bg-opacity-10 border-0 d-flex justify-content-between align-items-center">
                <h6 class="mb-0 fw-bold"><i class="fas fa-users text-danger me-2"></i>경쟁업체 상세</h6>
                <span class="badge bg-danger">${summary.competitors.length}개 업체</span>
            </div>
            <div class="card-body">`;

        if (summary.competitors.length === 0) {
            detailHtml += `<div class="text-center py-4 text-muted">
                <i class="fas fa-users fa-2x mb-2 d-block opacity-50"></i>
                <p class="mb-1">등록된 경쟁업체가 없습니다</p>
                <small>상단 <strong>관리</strong> 버튼을 눌러 경쟁업체를 추가하세요</small>
            </div>`;
        } else {
            summary.competitors.forEach(comp_item => {
                const m = comp_item.metrics;
                detailHtml += `<div class="border rounded-3 p-3 mb-2">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0 fw-bold"><i class="fas fa-store text-danger me-1"></i>${comp_item.name}</h6>
                        ${m ? `<small class="text-muted">최신: ${m.latest_date || '-'}</small>` : ''}
                    </div>`;
                if (m) {
                    detailHtml += `<div class="row g-2 text-center">
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-primary">${m.latest_blog_reviews}</div><small class="text-muted">블로그</small> ${trendIcon(m.blog_trend, false)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-success">${m.latest_visitor_reviews}</div><small class="text-muted">방문자</small> ${trendIcon(m.visitor_trend, false)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-warning">${m.latest_rank ? m.latest_rank + '위' : '-'}</div><small class="text-muted">순위</small> ${trendIcon(m.rank_trend, true)}</div></div>
                        <div class="col-3"><div class="bg-light rounded p-2"><div class="fw-bold text-info">${m.data_count}</div><small class="text-muted">데이터</small></div></div>
                    </div>`;
                } else {
                    detailHtml += `<p class="text-muted small mb-0">수집된 데이터가 없습니다</p>`;
                }
                detailHtml += '</div>';
            });
        }
        detailHtml += '</div></div>';

        // 상세 데이터 테이블 (기존 원본 데이터 접근)
        if (detail.my_places.length > 0 || detail.competitors.length > 0) {
            detailHtml += `<div class="card border-0 shadow-sm">
                <div class="card-header bg-white border-0">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-table text-secondary me-2"></i>상세 데이터 기록</h6>
                </div>
                <div class="card-body">
                    <ul class="nav nav-tabs nav-fill mb-3" id="detailTabs">
                        <li class="nav-item"><a class="nav-link active small" href="#" onclick="event.preventDefault();switchDetailTab('my')" style="font-weight:700;border-width:3px;"><i class="fas fa-store me-1"></i>우리 매장</a></li>
                        <li class="nav-item"><a class="nav-link small" href="#" onclick="event.preventDefault();switchDetailTab('comp')" style="font-weight:700;border-width:3px;"><i class="fas fa-users me-1"></i>경쟁업체</a></li>
                    </ul>
                    <div id="detailTabMy">`;

            detail.my_places.forEach(p => {
                detailHtml += `<div class="mb-3"><strong class="small">${p.nickname||p.place_url}</strong>`;
                if (p.data.length > 0) {
                    detailHtml += `<div class="table-responsive"><table class="table table-sm table-hover mt-1 mb-0"><thead class="table-light"><tr><th>날짜</th><th>블로그리뷰</th><th>방문자리뷰</th><th>순위</th></tr></thead><tbody>`;
                    p.data.forEach(d => { detailHtml += `<tr><td>${d.date}</td><td>${d.blog_review_count}</td><td>${d.visitor_review_count}</td><td>${d.place_rank||'-'}</td></tr>`; });
                    detailHtml += '</tbody></table></div>';
                } else { detailHtml += '<p class="text-muted small">데이터 없음</p>'; }
                detailHtml += '</div>';
            });

            detailHtml += `</div><div id="detailTabComp" style="display:none">`;

            detail.competitors.forEach(p => {
                detailHtml += `<div class="mb-3"><strong class="small">${p.memo||p.place_url}</strong>`;
                if (p.data.length > 0) {
                    detailHtml += `<div class="table-responsive"><table class="table table-sm table-hover mt-1 mb-0"><thead class="table-light"><tr><th>날짜</th><th>블로그리뷰</th><th>방문자리뷰</th><th>순위</th></tr></thead><tbody>`;
                    p.data.forEach(d => { detailHtml += `<tr><td>${d.date}</td><td>${d.blog_review_count}</td><td>${d.visitor_review_count}</td><td>${d.place_rank||'-'}</td></tr>`; });
                    detailHtml += '</tbody></table></div>';
                } else { detailHtml += '<p class="text-muted small">데이터 없음</p>'; }
                detailHtml += '</div>';
            });

            detailHtml += '</div></div></div>';
        }

        // AI 마케팅 추천 섹션
        detailHtml += `<div class="card border-0 shadow-sm mb-3">
            <div class="card-header border-0" style="background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(168,85,247,.1))">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-0 fw-bold"><i class="fas fa-robot me-2" style="color:#6366f1"></i>AI 마케팅 추천</h6>
                    <button class="btn btn-sm btn-outline-primary" onclick="generateAIRecommendation()" id="aiRecommendBtn">
                        <i class="fas fa-magic me-1"></i>분석 받기
                    </button>
                </div>
                <small class="text-muted">경쟁업체 대비 우리 매장에 필요한 마케팅 전략을 AI가 추천합니다</small>
            </div>
            <div class="card-body" id="aiRecommendBody">
                <div class="text-center py-4 text-muted">
                    <i class="fas fa-lightbulb fa-2x mb-2 d-block" style="color:#fbbf24;opacity:.5"></i>
                    <p class="mb-1">상단 <strong>분석 받기</strong> 버튼을 클릭하면</p>
                    <p class="mb-0 small">경쟁업체와 비교하여 맞춤 마케팅 전략을 추천해드립니다</p>
                </div>
            </div>
        </div>`;

        // 하단 액션 버튼
        detailHtml += `<div class="text-center mt-3">
            <button class="btn btn-outline-primary me-2" onclick="navigate('owner-adorder-new')"><i class="fas fa-bullhorn me-1"></i>광고 주문하기</button>
            <button class="btn btn-outline-secondary" onclick="navigate('owner-adorders')"><i class="fas fa-list me-1"></i>주문 내역 보기</button>
        </div>`;

        document.getElementById('analysisDetail').innerHTML = detailHtml;

    } catch (e) {
        document.getElementById('analysisSummary').innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${e.message}</div>`;
    }
}

function switchDetailTab(tab) {
    document.getElementById('detailTabMy').style.display = tab === 'my' ? '' : 'none';
    document.getElementById('detailTabComp').style.display = tab === 'comp' ? '' : 'none';
    document.querySelectorAll('#detailTabs .nav-link').forEach((el, i) => {
        const isActive = (i === 0 && tab === 'my') || (i === 1 && tab === 'comp');
        el.classList.toggle('active', isActive);
        el.style.background = isActive ? '#0d6efd' : '';
        el.style.color = isActive ? '#fff' : '';
        el.style.borderColor = isActive ? '#0d6efd' : '';
    });
}

// AI 마케팅 추천 생성
async function generateAIRecommendation() {
    const btn = document.getElementById('aiRecommendBtn');
    const body = document.getElementById('aiRecommendBody');
    if (!btn || !body) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>분석중...';
    body.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted small">AI가 경쟁업체 데이터를 분석하고 있습니다...</p></div>';

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
                    desc: '플레이스 순위는 리뷰 수, 평점, 방문 트래픽에 영향을 받습니다',
                    actions: [
                        '플레이스 트래픽 광고를 통해 방문자 수를 늘리세요',
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
                    '3단계: 블로그 체험단 운영 (신규 고객 유입)',
                    '4단계: 플레이스 트래픽 광고 (순위 향상)',
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
        body.innerHTML = `<div class="alert alert-danger mb-0"><i class="fas fa-exclamation-circle me-1"></i>${e.message}</div>`;
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-magic me-1"></i>다시 분석';
}

async function loadOwnerAdOrders(c, t) {
    t.textContent = '내 광고 주문';
    const orders = await apiGet('/api/owner/ad/orders');
    c.innerHTML = `<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">광고 주문 목록</h5>
        <button class="btn btn-primary btn-sm" onclick="navigate('owner-adorder-new')"><i class="fas fa-plus me-1"></i>새 주문</button>
    </div><div class="card-body">
        <div class="table-responsive"><table class="table table-hover table-sm">
            <thead><tr><th>ID</th><th>유형</th><th>상태</th><th>요약</th><th>관리자메모</th><th>날짜</th></tr></thead>
            <tbody>${orders.map(o => {
                let summary = '';
                if (o.blog_detail) summary = o.blog_detail.campaign_name;
                if (o.place_traffic_detail) summary = o.place_traffic_detail.place_name_or_id;
                return `<tr><td>${o.id}</td><td><span class="badge bg-${o.type==='blog'?'info':'secondary'}">${o.type==='blog'?'블로그':'플레이스'}</span></td><td>${statusBadge(o.status)}</td><td>${summary}</td><td>${o.admin_memo||'-'}</td><td>${formatDate(o.created_at)}</td></tr>`;
            }).join('')}</tbody>
        </table></div></div></div>`;
}

async function loadOwnerAdOrderNew(c, t) {
    t.textContent = '새 광고 주문';
    // 플래그 최신 로드
    let flags = adFeatureFlags;
    try { flags = await apiGet('/api/feature-flags'); adFeatureFlags = flags; } catch(e) {}
    const blogOn = flags.ad_blog_enabled;
    const placeOn = flags.ad_place_traffic_enabled;

    // 둘 다 OFF면 안내 메시지
    if (!blogOn && !placeOn) {
        c.innerHTML = `<div class="card border-0 shadow-sm"><div class="card-body text-center py-5">
            <i class="fas fa-exclamation-triangle text-warning" style="font-size:3rem"></i>
            <h5 class="mt-3 mb-2">현재 사용 가능한 광고 주문 유형이 없습니다</h5>
            <p class="text-muted mb-0">관리자에게 문의하여 블로그 배포 또는 플레이스 유입 기능을 활성화해 주세요.</p>
        </div></div>`;
        return;
    }

    // 기본 탭: blogOn이면 blog, 아니면 place
    const defaultTab = blogOn ? 'blog' : 'place';
    let tabsHtml = '<ul class="nav nav-tabs mb-4" id="adOrderTabs">';
    if (blogOn) tabsHtml += `<li class="nav-item"><a class="nav-link ${defaultTab==='blog'?'active':''}" href="#" onclick="showAdTab('blog')"><i class="fas fa-blog me-1"></i>블로그 배포</a></li>`;
    if (placeOn) tabsHtml += `<li class="nav-item"><a class="nav-link ${defaultTab==='place'?'active':''}" href="#" onclick="showAdTab('place')"><i class="fas fa-map-marker-alt me-1"></i>플레이스 유입</a></li>`;
    tabsHtml += '</ul>';

    let bodyHtml = tabsHtml;
    if (blogOn) {
        bodyHtml += `<div id="adTabBlog" style="display:${defaultTab==='blog'?'':'none'}">
        <div class="card data-card"><div class="card-header"><h5><i class="fas fa-blog text-info me-2"></i>블로그 배포 요청</h5></div><div class="card-body">
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">캠페인 이름</label><input class="form-control" id="blogCampaign"></div>
                <div class="col-md-6"><label class="form-label">매장 주소</label><input class="form-control" id="blogAddr"></div>
                <div class="col-md-6"><label class="form-label">문의 연락처</label><input class="form-control" id="blogContact"></div>
                <div class="col-md-6"><label class="form-label">링크 (쉼표 구분)</label><input class="form-control" id="blogLinks"></div>
                <div class="col-md-6"><label class="form-label">메인 키워드 (최대 5)</label><input class="form-control" id="blogKeywords"></div>
                <div class="col-md-6"><label class="form-label">해시태그 (최대 5)</label><input class="form-control" id="blogHashtags"></div>
                <div class="col-12"><label class="form-label">업체 소개</label><textarea class="form-control" id="blogDesc" rows="3"></textarea></div>
                <div class="col-12"><button class="btn btn-primary" onclick="submitBlogOrder()"><i class="fas fa-paper-plane me-1"></i>블로그 주문 등록</button></div>
            </div><div id="blogResult" class="mt-3"></div>
        </div></div>
    </div>`;
    }
    if (placeOn) {
        bodyHtml += `<div id="adTabPlace" style="display:${defaultTab==='place'?'':'none'}">
        <div class="card data-card"><div class="card-header"><h5><i class="fas fa-map-marker-alt text-success me-2"></i>플레이스 유입 요청</h5></div><div class="card-body">
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">플레이스명 또는 ID</label><input class="form-control" id="placeName"></div>
                <div class="col-md-6"><label class="form-label">검색 키워드 (최대 3)</label><input class="form-control" id="placeKeywords"></div>
                <div class="col-12"><button class="btn btn-success" onclick="submitPlaceOrder()"><i class="fas fa-paper-plane me-1"></i>플레이스 주문 등록</button></div>
            </div><div id="placeResult" class="mt-3"></div>
        </div></div>
    </div>`;
    }
    c.innerHTML = bodyHtml;
}

function showAdTab(tab) {
    const blogEl = document.getElementById('adTabBlog');
    const placeEl = document.getElementById('adTabPlace');
    if (blogEl) blogEl.style.display = tab==='blog'?'':'none';
    if (placeEl) placeEl.style.display = tab==='place'?'':'none';
    document.querySelectorAll('#adOrderTabs .nav-link').forEach(el => {
        const isBlog = el.textContent.includes('블로그');
        const isPlace = el.textContent.includes('플레이스');
        el.classList.toggle('active', (isBlog && tab==='blog') || (isPlace && tab==='place'));
    });
}

async function submitBlogOrder() {
    try {
        const links = document.getElementById('blogLinks').value.split(',').map(s=>s.trim()).filter(Boolean);
        const kw = document.getElementById('blogKeywords').value.split(',').map(s=>s.trim()).filter(Boolean);
        const ht = document.getElementById('blogHashtags').value.split(',').map(s=>s.trim()).filter(Boolean);
        const res = await apiPost('/api/owner/ad/blog-orders', { campaign_name: document.getElementById('blogCampaign').value, address: document.getElementById('blogAddr').value, contact: document.getElementById('blogContact').value, links, main_keywords: kw, hashtags: ht, description: document.getElementById('blogDesc').value, extra_image_link: '' });
        document.getElementById('blogResult').innerHTML = `<div class="alert alert-success">주문 등록 완료! (ID: ${res.id})</div>`;
    } catch(e) { document.getElementById('blogResult').innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
}

async function submitPlaceOrder() {
    try {
        const kw = document.getElementById('placeKeywords').value.split(',').map(s=>s.trim()).filter(Boolean);
        const res = await apiPost('/api/owner/ad/place-traffic-orders', { place_name_or_id: document.getElementById('placeName').value, search_keywords: kw });
        document.getElementById('placeResult').innerHTML = `<div class="alert alert-success">주문 등록 완료! (ID: ${res.id})</div>`;
    } catch(e) { document.getElementById('placeResult').innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
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
// 미용실 관리 프로그램 (CRM) — 고도화 버전
// 원장(owner): 매장 전체 / 디자이너(designer): 본인 고객·실적 위주
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
    return `<option value="">미지정</option>`+crmStaffCache.map(s=>`<option value="${s.id}" ${s.id===selectedId?'selected':''}>${s.name}</option>`).join('');
}
function crmServiceSelect(id){
    return `<select class="form-select" id="${id}" onchange="crmFillServiceAmount(this)">
        <option value="">시술 선택</option>
        ${crmServiceCache.map(s=>`<option value="${s.name}" data-price="${s.price}" data-dur="${s.duration_min}">${s.category?('['+s.category+'] '):''}${s.name} (${formatMoney(s.price)})</option>`).join('')}
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
    (tags||[]).forEach(t=>{ html+=`<span class="badge me-1" style="background:#eef2ff;color:#667eea;font-weight:500">#${t}</span>`; });
    (auto||[]).forEach(t=>{ html+=`<span class="badge me-1" style="background:#f1f5f9;color:#64748b;font-weight:500;border:1px dashed #cbd5e1">${t}</span>`; });
    return html||'<span class="text-muted">-</span>';
}
function crmResvStatusBadge(s, kr){
    const c=CRM_RESV_COLORS[s]||'#94a3b8';
    return `<span class="badge" style="background:${c}1a;color:${c};border:1px solid ${c}55">${kr||s}</span>`;
}

// ─── Loader & Tabs ─────────────────────────────────────────
async function loadCRM(c, t){
    t.textContent='미용실 관리 프로그램';
    try { crmMe = await apiGet('/api/crm/me'); } catch(e){ crmMe={is_designer:false,staff_id:null,role:'owner'}; }
    if(crmMe.is_designer && crmScope==='auto') crmScope='mine';
    try { crmStaffCache = await apiGet('/api/crm/staff?'+crmScopeQS()); } catch(e){ crmStaffCache=[]; }
    try { crmServiceCache = await apiGet('/api/crm/services'); } catch(e){ crmServiceCache=[]; }
    const tabs=[
        {id:'dashboard',icon:'fa-gauge-high',label:'대시보드'},
        {id:'customers',icon:'fa-users',label:'고객'},
        {id:'reservations',icon:'fa-calendar-check',label:'예약'},
        {id:'analytics',icon:'fa-chart-pie',label:'매출·통계'},
        {id:'marketing',icon:'fa-bullhorn',label:'마케팅·리텐션'},
        {id:'messages',icon:'fa-comment-dots',label:'메시지'},
        {id:'services',icon:'fa-scissors',label:'시술 메뉴'},
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
                <h2 class="fw-bold mb-1"><i class="fas fa-user-friends me-2" style="color:#667eea"></i>미용실 관리 프로그램</h2>
                <p class="text-muted mb-0">${crmMe.merchant_name||''} · 고객·예약·매출·마케팅을 한 곳에서 관리하세요${crmMe.is_designer?' <span class="badge bg-info ms-1">디자이너</span>':''}</p>
            </div>
            ${scopeToggle}
        </div>
        <div class="d-flex flex-wrap gap-1 p-1 mb-4" style="background:#f3f4f6;border-radius:14px;width:fit-content;max-width:100%" id="crmTabBar">
            ${tabs.map(crmTabBtn).join('')}
        </div>
        <div id="crmTabBody"><div class="text-center py-5"><div class="spinner-border text-primary"></div></div></div>`;
    crmSwitchTab(crmTab);
}
function crmTabBtn(tb){
    const a=tb.id===crmTab;
    return `<button class="crm-tab btn" data-tab="${tb.id}" onclick="crmSwitchTab('${tb.id}')" style="border:none;border-radius:10px;padding:.5rem .95rem;font-size:.88rem;background:${a?'#fff':'transparent'};color:${a?'#667eea':'#6b7280'};font-weight:${a?'700':'500'};box-shadow:${a?'0 2px 8px rgba(102,126,234,.15)':'none'}"><i class="fas ${tb.icon} me-2"></i>${tb.label}</button>`;
}
function crmSetScope(s){ crmScope=s; loadCRM(document.getElementById('pageContent'), document.createElement('span')); }
function crmSwitchTab(tab){
    crmTab=tab; crmDestroyCharts();
    document.querySelectorAll('#crmTabBar .crm-tab').forEach(el=>{
        const a=el.dataset.tab===tab;
        el.style.background=a?'#fff':'transparent'; el.style.color=a?'#667eea':'#6b7280';
        el.style.fontWeight=a?'700':'500'; el.style.boxShadow=a?'0 2px 8px rgba(102,126,234,.15)':'none';
    });
    const body=document.getElementById('crmTabBody'); if(!body) return;
    body.innerHTML='<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';
    if(tab==='dashboard') crmRenderDashboard(body);
    else if(tab==='customers') crmRenderCustomers(body);
    else if(tab==='reservations') crmRenderReservations(body);
    else if(tab==='analytics') crmRenderAnalytics(body);
    else if(tab==='marketing') crmRenderMarketing(body);
    else if(tab==='messages') crmRenderMessages(body);
    else if(tab==='services') crmRenderServices(body);
}

// ─── Dashboard ─────────────────────────────────────────────
async function crmRenderDashboard(body){
    try{
        const s=await apiGet('/api/crm/stats?'+crmScopeQS());
        const card=(icon,color,label,value,sub)=>`<div class="col-6 col-lg-3"><div class="card data-card h-100"><div class="card-body py-3">
            <div class="d-flex align-items-center gap-2 mb-1"><span style="width:32px;height:32px;border-radius:9px;background:${color}1a;color:${color};display:flex;align-items:center;justify-content:center"><i class="fas ${icon}"></i></span><small class="text-muted">${label}</small></div>
            <div class="fs-4 fw-bold">${value}</div>${sub?`<small class="text-muted">${sub}</small>`:''}</div></div></div>`;
        const topRows=(s.top_services||[]).map((x,i)=>`<tr><td>${i+1}</td><td class="fw-bold">${x.name}</td><td class="text-end">${x.count}건</td><td class="text-end">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="4" class="text-center text-muted py-3">데이터 없음</td></tr>`;
        const staffRows=(s.staff_sales||[]).map(x=>`<tr><td class="fw-bold">${x.staff_name}</td><td class="text-end">${x.count}건</td><td class="text-end fw-bold text-primary">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="3" class="text-center text-muted py-3">데이터 없음</td></tr>`;
        body.innerHTML=`
            <div class="row g-3 mb-3">
                ${card('fa-calendar-day','#f59e0b','오늘 예약',s.reservations_today+'건','예정 '+s.reservations_upcoming+'건')}
                ${card('fa-won-sign','#16a34a','오늘 매출',formatMoney(s.revenue_today),s.visits_today+'건 방문')}
                ${card('fa-coins','#667eea','이번달 매출',formatMoney(s.revenue_month),'객단가 '+formatMoney(s.avg_ticket_month))}
                ${card('fa-user-plus','#0ea5e9','이번달 신규',s.new_this_month+'명','전체 '+s.total_customers+'명')}
            </div>
            <div class="row g-3 mb-3">
                ${card('fa-bell','#ef4444','재방문 대상',s.revisit_due+'명','30일+ 미방문')}
                ${card('fa-cake-candles','#ec4899','이달 생일',s.birthdays_this_month+'명','축하 메시지 보내기')}
                ${card('fa-clock','#8b5cf6','예정 예약',s.reservations_upcoming+'건','다가오는 예약')}
                ${card('fa-sack-dollar','#14b8a6','누적 매출',formatMoney(s.revenue_total),'CRM 기준')}
            </div>
            <div class="row g-3">
                <div class="col-lg-7"><div class="card data-card h-100"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0"><i class="fas fa-calendar-day me-2"></i>오늘의 예약</h6><button class="btn btn-sm btn-outline-primary" onclick="crmSwitchTab('reservations')">예약 관리</button></div><div class="card-body p-0" id="crmTodayResv"><div class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></div></div></div></div>
                <div class="col-lg-5">
                    <div class="card data-card"><div class="card-header"><h6 class="mb-0"><i class="fas fa-chart-line me-2"></i>월별 매출</h6></div><div class="card-body"><canvas id="crmDashChart" height="150"></canvas></div></div>
                    <div class="card data-card mt-3"><div class="card-header"><h6 class="mb-0"><i class="fas fa-crown me-2"></i>인기 시술 TOP5</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>#</th><th>시술</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${topRows}</tbody></table></div></div>
                </div>
            </div>
            ${!s.scope_mine?`<div class="card data-card mt-3"><div class="card-header"><h6 class="mb-0"><i class="fas fa-user-tie me-2"></i>디자이너별 매출 (이번달)</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>디자이너</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${staffRows}</tbody></table></div></div>`:''}`;
        const ctx=document.getElementById('crmDashChart');
        if(ctx&&window.Chart){ crmChartRefs.push(new Chart(ctx,{type:'bar',data:{labels:(s.monthly_revenue||[]).map(m=>m.month.slice(2)),datasets:[{data:(s.monthly_revenue||[]).map(m=>m.revenue),backgroundColor:'#667eea',borderRadius:6}]},options:{plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>(v/10000)+'만'}}}}})); }
        const today=new Date(); today.setMinutes(today.getMinutes()-today.getTimezoneOffset());
        const ds=today.toISOString().slice(0,10);
        const rsv=await apiGet(`/api/crm/reservations?date_from=${ds}T00:00&date_to=${ds}T23:59&`+crmScopeQS());
        const box=document.getElementById('crmTodayResv');
        if(box){ box.innerHTML = rsv.length? `<div class="table-responsive"><table class="table table-sm table-hover align-middle mb-0"><thead class="table-light"><tr><th>시간</th><th>고객</th><th>시술</th><th>담당</th><th>상태</th></tr></thead><tbody>${rsv.map(r=>`<tr style="cursor:pointer" onclick="crmReservationDetail(${r.id})"><td class="fw-bold">${(formatDate(r.reserved_at).split(' ')[1]||'')}</td><td>${r.customer_name}</td><td>${r.service_name||'-'}</td><td>${r.staff_name||'-'}</td><td>${crmResvStatusBadge(r.status,r.status_kr)}</td></tr>`).join('')}</tbody></table></div>` : `<div class="text-center text-muted py-4">오늘 예약이 없습니다.</div>`; }
    }catch(e){ body.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
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
        </div><div class="card-body p-0" id="crmCustList"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div></div>`;
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
        }catch(e){ list.innerHTML=`<div class="alert alert-danger m-3">${e.message}</div>`; }
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
                <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.82rem">${(c.name||'?')[0]}</div>
                <div><div class="fw-bold">${c.name}${c.allergy_memo?' <i class="fas fa-triangle-exclamation text-warning" title="알레르기/주의"></i>':''}</div><small class="text-muted">${c.phone||'-'}</small></div>
            </div></td>
            <td><span class="badge" style="background:${gc};font-size:.7rem">${c.grade}</span></td>
            <td>${crmTagBadges(c.tags,c.auto_tags)}</td>
            <td class="text-center fw-bold">${c.visit_count}회${c.visit_cycle_days?`<small class="text-muted d-block">주기 ${c.visit_cycle_days}일</small>`:''}</td>
            <td class="text-end fw-bold">${formatMoney(c.total_spent)}<small class="text-muted d-block">객단가 ${formatMoney(c.avg_ticket)}</small></td>
            <td class="text-center">${c.points.toLocaleString()}P</td>
            <td><small class="text-muted">${c.last_visit?crmDateOnly(c.last_visit):'방문없음'}</small>${due}</td>
        </tr>`;
    }).join('');
    return `<div class="table-responsive"><table class="table table-hover align-middle mb-0">
        <thead class="table-light"><tr><th>고객</th><th>등급</th><th>태그</th><th class="text-center">방문</th><th class="text-end">누적매출</th><th class="text-center">포인트</th><th>최근/예상</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
}
function crmCustomerForm(existing){
    const c=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">이름 <span class="text-danger">*</span></label><input class="form-control" id="cfName" value="${c.name||''}"></div>
        <div class="col-md-6"><label class="form-label">연락처</label><input class="form-control" id="cfPhone" value="${c.phone||''}" placeholder="010-0000-0000"></div>
        <div class="col-md-4"><label class="form-label">성별</label><select class="form-select" id="cfGender"><option value="" ${!c.gender?'selected':''}>선택</option><option value="female" ${c.gender==='female'?'selected':''}>여성</option><option value="male" ${c.gender==='male'?'selected':''}>남성</option></select></div>
        <div class="col-md-4"><label class="form-label">생일</label><input class="form-control" id="cfBirth" type="date" value="${c.birthday||''}"></div>
        <div class="col-md-4"><label class="form-label">기념일</label><input class="form-control" id="cfAnniv" type="date" value="${c.anniversary||''}"></div>
        <div class="col-md-6"><label class="form-label">담당 디자이너</label><select class="form-select" id="cfStaff">${crmStaffOptions(c.assigned_staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">선호 디자이너</label><select class="form-select" id="cfPrefStaff">${crmStaffOptions(c.preferred_staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">선호 시술</label><input class="form-control" id="cfPrefSvc" list="cfSvcList" value="${c.preferred_service||''}"><datalist id="cfSvcList">${crmServiceCache.map(s=>`<option value="${s.name}">`).join('')}</datalist></div>
        <div class="col-md-6"><label class="form-label">사진 URL</label><input class="form-control" id="cfPhoto" value="${c.photo_url||''}" placeholder="https://..."></div>
        <div class="col-12"><label class="form-label">태그 <small class="text-muted">(콤마: 단골,염색)</small></label><input class="form-control" id="cfTags" value="${(c.tags||[]).join(',')}"></div>
        <div class="col-md-6"><label class="form-label text-danger">알레르기/주의사항</label><textarea class="form-control" id="cfAllergy" rows="2">${c.allergy_memo||''}</textarea></div>
        <div class="col-md-6"><label class="form-label">모발 상태/이력</label><textarea class="form-control" id="cfHair" rows="2">${c.hair_memo||''}</textarea></div>
        <div class="col-12"><label class="form-label">일반 메모</label><textarea class="form-control" id="cfMemo" rows="2">${c.memo||''}</textarea></div>
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
    }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
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
                <div class="col-6"><span class="text-muted">담당</span> ${c.assigned_staff_name||'-'}</div>
                <div class="col-6"><span class="text-muted">선호</span> ${c.preferred_staff_name||'-'} / ${c.preferred_service||'-'}</div>
                <div class="col-6"><span class="text-muted">방문주기</span> ${c.visit_cycle_days?c.visit_cycle_days+'일':'-'}</div>
                <div class="col-6"><span class="text-muted">예상 재방문</span> ${c.next_expected_visit||'-'}</div>
            </div>`;
        const timelineHtml=(tl.items||[]).slice(0,40).map(it=>{
            const ic={visit:'fa-scissors',reservation:'fa-calendar-check',point:'fa-coins',message:'fa-comment-dots',coupon:'fa-ticket'}[it.type]||'fa-circle';
            const col={visit:'#16a34a',reservation:'#3b82f6',point:'#f59e0b',message:'#8b5cf6',coupon:'#ec4899'}[it.type]||'#94a3b8';
            let detail='';
            if(it.type==='visit') detail=`${it.title} · ${formatMoney(it.amount||0)} ${it.staff_name?'· '+it.staff_name:''}`;
            else if(it.type==='reservation') detail=`${it.title} · ${it.status_kr||''}`;
            else if(it.type==='point') detail=`${it.title} · ${it.delta>=0?'+':''}${it.delta}P`;
            else if(it.type==='message') detail=`${it.content||it.title}`;
            else if(it.type==='coupon') detail=`${it.title} · ${it.status}`;
            return `<div class="d-flex gap-2 mb-2"><div style="width:26px;height:26px;border-radius:50%;background:${col}1a;color:${col};display:flex;align-items:center;justify-content:center;flex-shrink:0"><i class="fas ${ic}" style="font-size:.7rem"></i></div><div><div style="font-size:.85rem">${detail}</div><small class="text-muted">${formatDate(it.at)}</small></div></div>`;
        }).join('')||`<div class="text-muted text-center py-3">이력 없음</div>`;
        const body=`
            <div class="d-flex align-items-center gap-3 mb-3">
                <div style="width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.3rem;overflow:hidden">${c.photo_url?`<img src="${c.photo_url}" style="width:100%;height:100%;object-fit:cover">`:(c.name||'?')[0]}</div>
                <div><div class="d-flex align-items-center gap-2"><span class="fs-5 fw-bold">${c.name}</span><span class="badge" style="background:${gc}">${c.grade}</span></div><small class="text-muted">${c.phone||'-'}</small></div>
            </div>
            <div class="row g-2 mb-3">
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${c.visit_count}</div><small class="text-muted">방문</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(c.total_spent)}</div><small class="text-muted">누적</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${formatMoney(c.avg_ticket)}</div><small class="text-muted">객단가</small></div></div>
                <div class="col-3"><div class="bg-light rounded-3 p-2 text-center"><div class="fw-bold">${c.points.toLocaleString()}P</div><small class="text-muted">포인트</small></div></div>
            </div>
            <div class="mb-2">${crmTagBadges(c.tags,c.auto_tags)}</div>
            ${c.allergy_memo?`<div class="alert alert-warning py-2 small mb-2"><i class="fas fa-triangle-exclamation me-1"></i><strong>주의:</strong> ${c.allergy_memo}</div>`:''}
            ${c.hair_memo?`<div class="alert alert-light border py-2 small mb-2"><i class="fas fa-comment me-1 text-info"></i>${c.hair_memo}</div>`:''}
            ${c.memo?`<div class="alert alert-light border py-2 small mb-2"><i class="fas fa-note-sticky me-1 text-warning"></i>${c.memo}</div>`:''}
            <div class="card mb-2"><div class="card-body py-2">${profileRows}</div></div>
            <ul class="nav nav-tabs mb-2" role="tablist">
                <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#cdTimeline">통합 타임라인</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#cdVisits">방문 이력</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#cdCoupons">쿠폰/메시지</button></li>
            </ul>
            <div class="tab-content">
                <div class="tab-pane fade show active" id="cdTimeline" style="max-height:280px;overflow:auto">${timelineHtml}</div>
                <div class="tab-pane fade" id="cdVisits"><table class="table table-sm align-middle"><thead class="table-light"><tr><th>날짜</th><th>시술</th><th>담당</th><th class="text-end">금액</th><th></th></tr></thead><tbody>${(c.visits||[]).map(v=>`<tr><td>${crmDateOnly(v.visit_date)}</td><td>${v.service_name||'-'}</td><td>${v.staff_name||'-'}</td><td class="text-end">${formatMoney(v.amount)}</td><td><button class="btn btn-sm btn-outline-danger border-0" onclick="crmDeleteVisit(${v.id},${id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">방문 이력 없음</td></tr>`}</tbody></table></div>
                <div class="tab-pane fade" id="cdCoupons">
                    <div class="fw-bold small mb-1">쿠폰</div>
                    <table class="table table-sm align-middle"><tbody>${(c.coupons||[]).map(cp=>`<tr><td>${cp.name}</td><td>${cp.discount_type==='percent'?cp.value+'%':formatMoney(cp.value)}</td><td>${cp.status}</td><td class="text-muted">${cp.expires_at||''}</td></tr>`).join('')||`<tr><td class="text-center text-muted py-2">쿠폰 없음</td></tr>`}</tbody></table>
                    <div class="fw-bold small mb-1 mt-2">메시지</div>
                    <table class="table table-sm align-middle"><tbody>${(c.messages||[]).map(m=>`<tr><td>${m.channel}</td><td>${m.content}</td><td class="text-muted text-nowrap">${crmDateOnly(m.sent_at)}</td></tr>`).join('')||`<tr><td class="text-center text-muted py-2">발송 내역 없음</td></tr>`}</tbody></table>
                </div>
            </div>`;
        const footer=`
            <button type="button" class="btn btn-outline-danger me-auto" onclick="crmDeleteCustomer(${id})"><i class="fas fa-trash"></i></button>
            <button type="button" class="btn btn-outline-secondary" onclick="crmMessageToCustomer(${id},'${(c.name||'').replace(/'/g,'')}')"><i class="fas fa-comment-dots me-1"></i>메시지</button>
            <button type="button" class="btn btn-outline-secondary" onclick="crmCouponForm(${id})"><i class="fas fa-ticket me-1"></i>쿠폰</button>
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
    try{ const r=await apiPost(`/api/crm/customers/${id}/points`,{delta,reason:document.getElementById('pfReason').value.trim()||null}); crmCloseModal(); crmNotify(`적용됨 (잔액 ${r.points.toLocaleString()}P)`,'ok'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
}
function crmVisitForm(customerId){
    const custSelect = customerId? '' : `<div class="col-12"><label class="form-label">고객 <span class="text-danger">*</span></label><select class="form-select" id="crmVisitCustomer"><option value="">고객 선택</option></select></div>`;
    const body=`<div class="row g-3">
        ${custSelect}
        <div class="col-md-6"><label class="form-label">시술 선택</label>${crmServiceSelect('crmVisitSvcSel')}</div>
        <div class="col-md-6"><label class="form-label">시술명</label><input class="form-control" id="crmVisitService"></div>
        <div class="col-md-6"><label class="form-label">금액</label><input class="form-control" id="crmVisitAmount" type="number" value="0"></div>
        <div class="col-md-6"><label class="form-label">담당</label><select class="form-select" id="crmVisitStaff">${crmStaffOptions(crmMe.staff_id)}</select></div>
        <div class="col-md-6"><label class="form-label">방문일시</label><input class="form-control" id="crmVisitDate" type="datetime-local" value="${crmNowLocal()}"></div>
        <div class="col-md-6"><label class="form-label">메모</label><input class="form-control" id="crmVisitMemo"></div>
        <div class="col-12"><div id="crmVisitResult"></div></div>
    </div>`;
    crmModal('방문/시술 기록', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmVisitSave(${customerId||'null'})"><i class="fas fa-save me-1"></i>기록</button>`);
    if(!customerId) crmLoadCustomerSelect('crmVisitCustomer');
}
async function crmLoadCustomerSelect(selId){
    try{ const data=await apiGet('/api/crm/customers?scope=all'); const sel=document.getElementById(selId); if(sel) sel.innerHTML=`<option value="">고객 선택</option>`+data.map(c=>`<option value="${c.id}">${c.name} (${c.phone||'-'})</option>`).join(''); }catch(e){}
}
async function crmVisitSave(customerId){
    const res=document.getElementById('crmVisitResult');
    const cid=customerId||parseInt(document.getElementById('crmVisitCustomer').value);
    if(!cid){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">고객을 선택하세요.</div>`; return; }
    const payload={ customer_id:cid, service_name:document.getElementById('crmVisitService').value.trim()||null, amount:parseFloat(document.getElementById('crmVisitAmount').value)||0, staff_id:parseInt(document.getElementById('crmVisitStaff').value)||null, visit_date:document.getElementById('crmVisitDate').value||null, memo:document.getElementById('crmVisitMemo').value.trim()||null };
    try{ const r=await apiPost('/api/crm/visits',payload); crmCloseModal(); crmNotify(`방문 기록됨${r.points_earned?' (+'+r.points_earned+'P)':''}`,'ok'); crmSwitchTab(crmTab==='customers'?'customers':crmTab); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
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
        <div id="crmResvBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div>`;
    crmLoadReservationView();
}
function crmSetCalView(v){ crmCalView=v; crmRenderReservations(document.getElementById('crmTabBody')); }
function crmCalSetDate(v){ crmCalDate=v; crmLoadReservationView(); }
function crmCalToday(){ const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); crmCalDate=d.toISOString().slice(0,10); const inp=document.getElementById('crmCalDate'); if(inp) inp.value=crmCalDate; crmLoadReservationView(); }
function crmCalMove(delta){ const step=crmCalView==='week'?7:1; const d=new Date(crmCalDate+'T00:00'); d.setDate(d.getDate()+step*delta); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); crmCalDate=d.toISOString().slice(0,10); const inp=document.getElementById('crmCalDate'); if(inp) inp.value=crmCalDate; crmLoadReservationView(); }
async function crmLoadReservationView(){
    const box=document.getElementById('crmResvBody'); if(!box) return;
    box.innerHTML='<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
    try{
        if(crmCalView==='list'){ const data=await apiGet(`/api/crm/reservations?${crmScopeQS()}`); box.innerHTML=crmReservationListTable(data); return; }
        const cal=await apiGet(`/api/crm/reservations/calendar?date=${crmCalDate}&view=${crmCalView}&${crmScopeQS()}`);
        box.innerHTML = crmCalView==='day' ? crmRenderDayCalendar(cal) : crmRenderWeekCalendar(cal);
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
}
function crmReservationListTable(data){
    const rows=data.map(r=>`<tr>
        <td><small>${formatDate(r.reserved_at)}</small></td>
        <td class="fw-bold" ${r.customer_id?`style="cursor:pointer" onclick="crmCustomerDetail(${r.customer_id})"`:''}>${r.customer_name}</td>
        <td>${r.service_name||'-'}</td><td>${r.staff_name||'-'}</td><td>${crmResvStatusBadge(r.status,r.status_kr)}</td>
        <td class="text-end">${crmResvActions(r)}</td></tr>`).join('')||`<tr><td colspan="6" class="text-center text-muted py-4">예약이 없습니다.</td></tr>`;
    return `<div class="card data-card"><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>예약일시</th><th>고객</th><th>시술</th><th>담당</th><th>상태</th><th class="text-end">관리</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
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
    let header=`<div style="display:flex;border-bottom:2px solid #eef2ff"><div style="width:50px;flex-shrink:0"></div>${staff.map(s=>`<div style="flex:1;min-width:${colW}px;text-align:center;font-weight:700;padding:6px;color:#667eea">${s.name}</div>`).join('')}</div>`;
    let gridRows=hours.map(h=>`<div style="display:flex;height:${H}px;border-bottom:1px solid #f3f4f6"><div style="width:50px;flex-shrink:0;font-size:.72rem;color:#9ca3af;text-align:right;padding-right:6px">${h}:00</div>${staff.map(()=>`<div style="flex:1;min-width:${colW}px;border-left:1px solid #f8fafc"></div>`).join('')}</div>`).join('');
    let events=cal.events.map(ev=>{
        const dt=new Date(ev.reserved_at.replace(' ','T'));
        const sIdx=staff.findIndex(s=>s.id===ev.staff_id); const idx=sIdx<0?0:sIdx;
        const top=((dt.getHours()-startH)+dt.getMinutes()/60)*H;
        const hgt=Math.max(24,(ev.duration_min/60)*H-3);
        const col=CRM_RESV_COLORS[ev.status]||'#667eea';
        const left=50 + idx*colW;
        return `<div onclick="crmReservationDetail(${ev.id})" style="position:absolute;top:${top+34}px;left:${left+2}px;width:${colW-6}px;height:${hgt}px;background:${col}1a;border-left:3px solid ${col};border-radius:6px;padding:3px 6px;font-size:.72rem;overflow:hidden;cursor:pointer">
            <div class="fw-bold" style="color:${col}">${dt.getHours()}:${String(dt.getMinutes()).padStart(2,'0')} ${ev.customer_name}</div>
            <div class="text-muted text-truncate">${ev.service_name||''}</div></div>`;
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
            <div style="padding:4px;min-height:80px">${evs.map(ev=>{const col=CRM_RESV_COLORS[ev.status]||'#667eea'; const tt=ev.reserved_at.slice(11,16); return `<div onclick="crmReservationDetail(${ev.id})" style="background:${col}1a;border-left:3px solid ${col};border-radius:6px;padding:3px 5px;margin-bottom:4px;font-size:.72rem;cursor:pointer"><div class="fw-bold" style="color:${col}">${tt} ${ev.customer_name}</div><div class="text-muted text-truncate">${ev.staff_name||''} ${ev.service_name||''}</div></div>`;}).join('')||'<div class="text-muted text-center small py-2">-</div>'}</div>
        </div>`;
    }).join('');
    return `<div class="card data-card"><div class="card-body" style="overflow-x:auto"><div style="display:flex;min-width:910px">${cols}</div></div></div>`;
}
async function crmReservationDetail(id){
    try{
        const list=await apiGet(`/api/crm/reservations?${crmScopeQS()}`);
        const r=list.find(x=>x.id===id); if(!r){ crmNotify('예약을 찾을 수 없습니다','err'); return; }
        const body=`<div class="row g-2 small mb-3">
            <div class="col-6"><span class="text-muted">고객</span><div class="fw-bold">${r.customer_name}</div></div>
            <div class="col-6"><span class="text-muted">연락처</span><div>${r.phone||'-'}</div></div>
            <div class="col-6"><span class="text-muted">예약일시</span><div class="fw-bold">${formatDate(r.reserved_at)}</div></div>
            <div class="col-6"><span class="text-muted">소요</span><div>${r.duration_min||60}분</div></div>
            <div class="col-6"><span class="text-muted">시술</span><div>${r.service_name||'-'}</div></div>
            <div class="col-6"><span class="text-muted">담당</span><div>${r.staff_name||'-'}</div></div>
            <div class="col-12"><span class="text-muted">상태</span> ${crmResvStatusBadge(r.status,r.status_kr)}</div>
            ${r.memo?`<div class="col-12"><span class="text-muted">메모</span><div>${r.memo}</div></div>`:''}
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
        <div class="col-md-6"><label class="form-label">시술</label>${crmServiceSelect('rfSvcSel')}<input class="form-control mt-1" id="rfService" placeholder="시술명"></div>
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
        if((e.message||'').includes('겹칩')){ if(confirm(e.message+'\n\n그래도 등록하시겠습니까?')){ crmReservationSave(true); return; } res.innerHTML=`<div class="alert alert-warning py-2 mb-0">${e.message}</div>`; }
        else res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`;
    }
}

// ─── Analytics ─────────────────────────────────────────────
async function crmRenderAnalytics(body){
    body.innerHTML=`
        <div class="d-flex justify-content-end mb-3"><select class="form-select form-select-sm" id="crmAnRange" style="width:140px"><option value="week">이번주</option><option value="month" selected>이번달</option><option value="year">올해</option><option value="all">전체</option></select></div>
        <div id="crmAnBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div>`;
    const load=async()=>{
        crmDestroyCharts();
        const range=document.getElementById('crmAnRange').value; const box=document.getElementById('crmAnBody');
        try{
            const a=await apiGet(`/api/crm/stats/analytics?range=${range}&${crmScopeQS()}`);
            const kpi=(label,val,sub)=>`<div class="col-6 col-lg-3"><div class="card data-card h-100"><div class="card-body py-3 text-center"><div class="fs-4 fw-bold">${val}</div><small class="text-muted">${label}</small>${sub?`<div><small class="text-muted">${sub}</small></div>`:''}</div></div></div>`;
            const svcRows=(a.by_service||[]).slice(0,8).map(x=>`<tr><td class="fw-bold">${x.name}</td><td class="text-end">${x.count}건</td><td class="text-end">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="3" class="text-center text-muted py-3">데이터 없음</td></tr>`;
            const staffRows=(a.by_staff||[]).map(x=>`<tr><td class="fw-bold">${x.staff_name}</td><td class="text-end">${x.count}건</td><td class="text-end">${formatMoney(x.revenue)}</td></tr>`).join('')||`<tr><td colspan="3" class="text-center text-muted py-3">데이터 없음</td></tr>`;
            box.innerHTML=`
                <div class="row g-3 mb-3">
                    ${kpi('총 매출',formatMoney(a.total_revenue),a.total_visits+'건')}
                    ${kpi('객단가',formatMoney(a.avg_ticket))}
                    ${kpi('신규/재방문',a.new_count+' / '+a.revisit_count,'신규비율 '+a.new_ratio+'%')}
                    ${kpi('방문 수',a.total_visits+'건')}
                </div>
                <div class="row g-3">
                    <div class="col-lg-8"><div class="card data-card"><div class="card-header"><h6 class="mb-0">일별 매출 추이</h6></div><div class="card-body"><canvas id="anDaily" height="110"></canvas></div></div></div>
                    <div class="col-lg-4"><div class="card data-card"><div class="card-header"><h6 class="mb-0">신규 vs 재방문</h6></div><div class="card-body"><canvas id="anNew" height="110"></canvas></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">요일별 매출</h6></div><div class="card-body"><canvas id="anWeekday" height="110"></canvas></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">시간대별 방문</h6></div><div class="card-body"><canvas id="anHour" height="110"></canvas></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">시술별 매출</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>시술</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${svcRows}</tbody></table></div></div></div>
                    <div class="col-lg-6"><div class="card data-card"><div class="card-header"><h6 class="mb-0">디자이너별 매출</h6></div><div class="card-body p-0"><table class="table table-sm mb-0 align-middle"><thead class="table-light"><tr><th>디자이너</th><th class="text-end">건수</th><th class="text-end">매출</th></tr></thead><tbody>${staffRows}</tbody></table></div></div></div>
                </div>`;
            if(window.Chart){
                const dc=document.getElementById('anDaily'); if(dc) crmChartRefs.push(new Chart(dc,{type:'line',data:{labels:(a.daily||[]).map(d=>d.date.slice(5)),datasets:[{data:(a.daily||[]).map(d=>d.revenue),borderColor:'#667eea',backgroundColor:'rgba(102,126,234,.1)',fill:true,tension:.3}]},options:{plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>(v/10000)+'만'}}}}}));
                const nc=document.getElementById('anNew'); if(nc) crmChartRefs.push(new Chart(nc,{type:'doughnut',data:{labels:['신규','재방문'],datasets:[{data:[a.new_count,a.revisit_count],backgroundColor:['#10b981','#667eea']}]},options:{plugins:{legend:{position:'bottom'}}}}));
                const wc=document.getElementById('anWeekday'); if(wc) crmChartRefs.push(new Chart(wc,{type:'bar',data:{labels:(a.by_weekday||[]).map(x=>x.label),datasets:[{data:(a.by_weekday||[]).map(x=>x.revenue),backgroundColor:'#f59e0b',borderRadius:5}]},options:{plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>(v/10000)+'만'}}}}}));
                const hc=document.getElementById('anHour'); if(hc) crmChartRefs.push(new Chart(hc,{type:'bar',data:{labels:(a.by_hour||[]).map(x=>x.hour+'시'),datasets:[{data:(a.by_hour||[]).map(x=>x.count),backgroundColor:'#8b5cf6',borderRadius:5}]},options:{plugins:{legend:{display:false}}}}));
            }
        }catch(e){ box.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
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
        <div id="crmMkBody"><div class="text-center py-4"><div class="spinner-border text-primary"></div></div></div>`;
    crmMkRender('revisit');
}
function crmMkTab(el,tab){ document.querySelectorAll('#mkPills .nav-link').forEach(x=>x.classList.remove('active')); el.classList.add('active'); crmMkRender(tab); }
async function crmMkRender(tab){
    const box=document.getElementById('crmMkBody'); box.innerHTML='<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
    try{
        if(tab==='revisit'){
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><div class="d-flex align-items-center gap-2"><span class="small text-muted">미방문 기준</span><select class="form-select form-select-sm" id="mkRevDays" style="width:120px"><option value="30">30일+</option><option value="60" selected>60일+</option><option value="90">90일+</option></select></div><button class="btn btn-sm btn-primary" onclick="crmSendCampaign('dormant')"><i class="fas fa-paper-plane me-1"></i>휴면 캠페인 발송</button></div><div class="card-body p-0" id="mkRevList"></div></div>`;
            const load=async()=>{ const days=document.getElementById('mkRevDays').value; const d=await apiGet(`/api/crm/revisit?days=${days}&${crmScopeQS()}`); document.getElementById('mkRevList').innerHTML=crmRevisitTable(d); };
            document.getElementById('mkRevDays').addEventListener('change', load); load();
        } else if(tab==='birthday'){
            const d=await apiGet('/api/crm/birthdays');
            const tbl=(arr,label)=>`<div class="card data-card mb-3"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">${label} (${arr.length}명)</h6>${arr.length?`<button class="btn btn-sm btn-primary" onclick="crmSendCampaign('birthday')"><i class="fas fa-cake-candles me-1"></i>축하 메시지</button>`:''}</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm table-hover align-middle mb-0"><thead class="table-light"><tr><th>일</th><th>고객</th><th>연락처</th><th>등급</th><th class="text-center">방문</th></tr></thead><tbody>${arr.map(c=>`<tr style="cursor:pointer" onclick="crmCustomerDetail(${c.id})"><td class="fw-bold">${c.event_day}일</td><td>${c.name}</td><td>${c.phone||'-'}</td><td><span class="badge" style="background:${CRM_GRADE_COLORS[c.grade]}">${c.grade}</span></td><td class="text-center">${c.visit_count}회</td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">대상 없음</td></tr>`}</tbody></table></div></div></div>`;
            box.innerHTML=`<div class="alert alert-info border-0 small"><i class="fas fa-info-circle me-1"></i>이번 달 생일/기념일 고객입니다. 축하 메시지·쿠폰 발송 대상으로 활용하세요.</div>${tbl(d.birthdays,'🎂 이달 생일')}${tbl(d.anniversaries,'💝 이달 기념일')}`;
        } else if(tab==='coupons'){
            const d=await apiGet('/api/crm/coupons');
            const rows=d.map(cp=>`<tr><td class="fw-bold">${cp.name}</td><td>${cp.customer_name}</td><td>${cp.discount_type==='percent'?cp.value+'%':formatMoney(cp.value)}</td><td>${crmCouponStatusBadge(cp.status)}</td><td class="text-muted">${cp.expires_at||'-'}</td><td class="text-end">${cp.status==='issued'?`<button class="btn btn-sm btn-outline-success border-0" title="사용처리" onclick="crmCouponUse(${cp.id})"><i class="fas fa-check"></i></button>`:''}<button class="btn btn-sm btn-outline-danger border-0" onclick="crmCouponDelete(${cp.id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="6" class="text-center text-muted py-3">발급된 쿠폰이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">쿠폰 발급 현황</h6><div class="d-flex gap-2"><button class="btn btn-sm btn-outline-primary" onclick="crmCouponBulkForm()"><i class="fas fa-layer-group me-1"></i>세그먼트 일괄발급</button><button class="btn btn-sm btn-primary" onclick="crmCouponForm()"><i class="fas fa-plus me-1"></i>쿠폰 발급</button></div></div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>쿠폰명</th><th>고객</th><th>할인</th><th>상태</th><th>만료</th><th class="text-end">관리</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
        }
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
}
function crmRevisitTable(d){
    const rows=(d.customers||[]).map(c=>`<tr><td class="fw-bold" style="cursor:pointer" onclick="crmCustomerDetail(${c.id})">${c.name}</td><td>${c.phone||'-'}</td><td><span class="badge" style="background:${CRM_GRADE_COLORS[c.grade]}">${c.grade}</span></td><td class="text-center">${c.visit_count}회</td><td class="text-center"><span class="badge bg-danger">${c.days_since_visit}일 전</span></td><td>${c.assigned_staff_name||'-'}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary border-0" onclick="crmMessageToCustomer(${c.id},'${(c.name||'').replace(/'/g,'')}')"><i class="fas fa-comment-dots"></i></button></td></tr>`).join('')||`<tr><td colspan="7" class="text-center text-muted py-3">대상 고객이 없습니다.</td></tr>`;
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
    try{ await apiPost('/api/crm/coupons',payload); crmCloseModal(); crmNotify('쿠폰이 발급되었습니다.','ok'); if(crmTab==='marketing') crmMkRender('coupons'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
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
    try{ const r=await apiPost('/api/crm/coupons/bulk',payload); crmCloseModal(); crmNotify(`${r.issued}명에게 쿠폰 발급 완료`,'ok'); crmMkRender('coupons'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
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
    const box=document.getElementById('crmMsgBody'); box.innerHTML='<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
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
            const rows=tpls.map(t=>`<tr><td class="fw-bold">${t.name}</td><td><span class="badge bg-secondary">${t.channel}</span></td><td>${t.category||'-'}</td><td class="text-muted small">${t.body}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary border-0" onclick='crmTemplateForm(${JSON.stringify(t).replace(/'/g,"&#39;")})'><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-outline-danger border-0" onclick="crmTemplateDelete(${t.id})"><i class="fas fa-trash"></i></button></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">템플릿이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">메시지 템플릿</h6><button class="btn btn-sm btn-primary" onclick="crmTemplateForm()"><i class="fas fa-plus me-1"></i>템플릿 추가</button></div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>이름</th><th>채널</th><th>분류</th><th>내용</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div><div class="card-footer small text-muted">치환변수: {고객명} {매장명} {포인트}</div></div>`;
        } else if(tab==='log'){
            const logs=await apiGet('/api/crm/messages');
            const rows=logs.map(m=>`<tr><td><small>${formatDate(m.sent_at)}</small></td><td>${m.customer_name}</td><td><span class="badge bg-secondary">${m.channel}</span></td><td class="small">${m.content}</td><td><span class="badge bg-light text-dark">${m.campaign||'-'}</span></td></tr>`).join('')||`<tr><td colspan="5" class="text-center text-muted py-3">발송 내역이 없습니다.</td></tr>`;
            box.innerHTML=`<div class="card data-card"><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="table-light"><tr><th>발송시각</th><th>고객</th><th>채널</th><th>내용</th><th>캠페인</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
        }
    }catch(e){ box.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
}
async function crmMessageForm(opts){
    opts=opts||{};
    const tpls=opts.templates||await apiGet('/api/crm/message-templates');
    const tplOpts=`<option value="">직접 입력</option>`+tpls.map(t=>`<option value="${t.id}" ${opts.template_id===t.id?'selected':''} data-body="${(t.body||'').replace(/"/g,'&quot;')}" data-ch="${t.channel}">${t.name}</option>`).join('');
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
    try{ const r=await apiPost('/api/crm/messages/send',payload); crmCloseModal(); crmNotify(`${r.sent}건 발송(목업) 완료`,'ok'); if(crmTab==='messages') crmMsgRender('log'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
}
function crmMessageToCustomer(id,name){ crmMessageForm({customer_id:id, title:`${name||'고객'} 메시지`}); }
function crmTemplateForm(existing){
    const t=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">템플릿명 <span class="text-danger">*</span></label><input class="form-control" id="tfName" value="${t.name||''}"></div>
        <div class="col-md-3"><label class="form-label">채널</label><select class="form-select" id="tfChannel"><option value="sms" ${t.channel==='sms'?'selected':''}>SMS</option><option value="alimtalk" ${t.channel==='alimtalk'?'selected':''}>알림톡</option></select></div>
        <div class="col-md-3"><label class="form-label">분류</label><input class="form-control" id="tfCat" value="${t.category||''}" placeholder="reminder 등"></div>
        <div class="col-12"><label class="form-label">내용 <small class="text-muted">({고객명} {매장명} {포인트})</small></label><textarea class="form-control" id="tfBody" rows="3">${t.body||''}</textarea></div>
        <div class="col-12"><div id="tfResult"></div></div>
    </div>`;
    crmModal(isEdit?'템플릿 수정':'템플릿 추가', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmTemplateSave(${isEdit?t.id:'null'})">${isEdit?'수정':'추가'}</button>`);
}
async function crmTemplateSave(id){
    const res=document.getElementById('tfResult'); const name=document.getElementById('tfName').value.trim(); const bodyv=document.getElementById('tfBody').value.trim();
    if(!name||!bodyv){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">이름과 내용은 필수입니다.</div>`; return; }
    const payload={ name, channel:document.getElementById('tfChannel').value, category:document.getElementById('tfCat').value.trim()||null, body:bodyv };
    try{ if(id) await apiPut(`/api/crm/message-templates/${id}`,payload); else await apiPost('/api/crm/message-templates',payload); crmCloseModal(); crmNotify('저장되었습니다.','ok'); crmMsgRender('templates'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
}
async function crmTemplateDelete(id){ if(!confirm('템플릿을 삭제할까요?')) return; try{ await apiDelete(`/api/crm/message-templates/${id}`); crmNotify('삭제되었습니다.','ok'); crmMsgRender('templates'); }catch(e){ crmNotify(e.message,'err'); } }

// ─── Services (시술 메뉴 + 디자이너 단가) ──────────────────
async function crmRenderServices(body){
    try{
        const data=await apiGet('/api/crm/services');
        const cats={};
        data.forEach(s=>{ (cats[s.category||'기타']=cats[s.category||'기타']||[]).push(s); });
        let sections='';
        Object.keys(cats).forEach(cat=>{
            const rows=cats[cat].map(s=>`<tr>
                <td class="fw-bold">${s.name}</td><td class="text-end">${formatMoney(s.price)}</td><td class="text-center">${s.duration_min}분</td>
                <td class="text-center">${s.is_active?'<span class="badge bg-success">활성</span>':'<span class="badge bg-secondary">비활성</span>'}</td>
                <td class="text-end"><button class="btn btn-sm btn-outline-info border-0" title="디자이너별 단가" onclick="crmServicePriceForm(${s.id},'${s.name.replace(/'/g,'')}')"><i class="fas fa-user-tag"></i></button><button class="btn btn-sm btn-outline-primary border-0" onclick='crmServiceForm(${JSON.stringify(s)})'><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-outline-danger border-0" onclick="crmServiceDelete(${s.id})"><i class="fas fa-trash"></i></button></td>
            </tr>`).join('');
            sections+=`<div class="mb-2"><div class="fw-bold text-muted small mb-1 px-1"><i class="fas fa-folder me-1"></i>${cat}</div><div class="table-responsive"><table class="table table-hover align-middle mb-0"><tbody>${rows}</tbody></table></div></div>`;
        });
        body.innerHTML=`<div class="card data-card"><div class="card-header d-flex justify-content-between align-items-center"><h6 class="mb-0">시술 메뉴</h6><button class="btn btn-sm btn-primary" onclick="crmServiceForm()"><i class="fas fa-plus me-1"></i>시술 추가</button></div><div class="card-body">${sections||'<div class="text-center text-muted py-4">등록된 시술이 없습니다.</div>'}</div></div>`;
    }catch(e){ body.innerHTML=`<div class="alert alert-danger">${e.message}</div>`; }
}
function crmServiceForm(existing){
    const s=existing||{}; const isEdit=!!(existing&&existing.id);
    const body=`<div class="row g-3">
        <div class="col-md-6"><label class="form-label">시술명 <span class="text-danger">*</span></label><input class="form-control" id="sfName" value="${s.name||''}"></div>
        <div class="col-md-6"><label class="form-label">카테고리</label><input class="form-control" id="sfCat" list="sfCatList" value="${s.category||''}" placeholder="컷/펌/염색/클리닉/스타일링"><datalist id="sfCatList"><option value="커트"><option value="펌"><option value="염색"><option value="클리닉"><option value="스타일링"></datalist></div>
        <div class="col-md-6"><label class="form-label">가격</label><input class="form-control" id="sfPrice" type="number" value="${s.price!=null?s.price:0}"></div>
        <div class="col-md-6"><label class="form-label">소요(분)</label><input class="form-control" id="sfDur" type="number" value="${s.duration_min!=null?s.duration_min:60}"></div>
        ${isEdit?`<div class="col-12"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="sfActive" ${s.is_active!==false?'checked':''}><label class="form-check-label">활성</label></div></div>`:''}
        <div class="col-12"><div id="sfResult"></div></div>
    </div>`;
    crmModal(isEdit?'시술 수정':'시술 추가', body, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button><button type="button" class="btn btn-primary" onclick="crmServiceSave(${isEdit?s.id:'null'})">${isEdit?'수정':'추가'}</button>`);
}
async function crmServiceSave(id){
    const res=document.getElementById('sfResult'); const name=document.getElementById('sfName').value.trim();
    if(!name){ res.innerHTML=`<div class="alert alert-warning py-2 mb-0">시술명은 필수입니다.</div>`; return; }
    const payload={ name, category:document.getElementById('sfCat').value.trim()||null, price:parseFloat(document.getElementById('sfPrice').value)||0, duration_min:parseInt(document.getElementById('sfDur').value)||60 };
    const act=document.getElementById('sfActive'); if(act) payload.is_active=act.checked;
    try{ if(id) await apiPut(`/api/crm/services/${id}`,payload); else await apiPost('/api/crm/services',payload); crmServiceCache=await apiGet('/api/crm/services'); crmCloseModal(); crmNotify('저장되었습니다.','ok'); crmSwitchTab('services'); }catch(e){ res.innerHTML=`<div class="alert alert-danger py-2 mb-0">${e.message}</div>`; }
}
async function crmServiceDelete(id){ if(!confirm('이 시술을 삭제할까요?')) return; try{ await apiDelete(`/api/crm/services/${id}`); crmServiceCache=await apiGet('/api/crm/services'); crmNotify('삭제되었습니다.','ok'); crmSwitchTab('services'); }catch(e){ crmNotify(e.message,'err'); } }
async function crmServicePriceForm(sid,name){
    const prices=await apiGet(`/api/crm/services/${sid}/prices`);
    const priceMap={}; prices.forEach(p=>priceMap[p.staff_id]=p.price);
    const rows=crmStaffCache.map(st=>`<tr><td>${st.name}</td><td><div class="input-group input-group-sm"><input class="form-control" id="spp_${st.id}" type="number" value="${priceMap[st.id]!=null?priceMap[st.id]:''}" placeholder="기본가 사용"><button class="btn btn-outline-primary" onclick="crmServicePriceSave(${sid},${st.id})">저장</button></div></td></tr>`).join('');
    crmModal(`${name} — 디자이너별 단가`, `<table class="table align-middle"><thead class="table-light"><tr><th>디자이너</th><th>단가(원)</th></tr></thead><tbody>${rows||'<tr><td colspan=2 class="text-muted text-center">디자이너 없음</td></tr>'}</tbody></table><div class="small text-muted">비워두면 시술 기본가가 적용됩니다.</div>`, `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>`);
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
                            <input class="form-control" id="infoName" value="${info.name || ''}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">사업자번호</label>
                            <input class="form-control" id="infoBizNo" value="${info.business_no || ''}">
                        </div>
                        <div class="col-12">
                            <label class="form-label fw-bold">주소</label>
                            <input class="form-control" id="infoAddr" value="${info.address || ''}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold">연락처</label>
                            <input class="form-control" id="infoPhone" value="${info.phone || ''}">
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
                            <input class="form-control" id="infoPlaceUrl" value="${info.place_url || ''}" placeholder="https://map.naver.com/...">
                        </div>
                        <div class="col-12">
                            <button class="btn btn-primary" onclick="saveMerchantInfo()"><i class="fas fa-save me-1"></i>매장 정보 저장</button>
                            <div id="infoSaveResult" class="mt-2"></div>
                        </div>
                    </div>
                    <div class="alert alert-info mt-3 mb-0">
                        <i class="fas fa-info-circle me-2"></i>
                        <strong>분야 설정 안내:</strong> 식당, 카페 등을 선택하면 <strong>직원관리</strong>와 <strong>직원별 매출</strong> 메뉴가 숨겨집니다.
                        미용실, 네일샵 등 직원별 매출 확인이 필요한 업종은 해당 메뉴가 표시됩니다.
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-5">
            <div class="card data-card h-100">
                <div class="card-header"><h5><i class="fas fa-chart-pie me-2"></i>매장 현황</h5></div>
                <div class="card-body">
                    <ul class="list-unstyled">
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">매장명</span><span class="fw-bold">${info.name}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">분야</span><span class="badge bg-primary">${info.display_category}</span></li>
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

        // 왼쪽 상단 브랜드명도 매장명으로 업데이트
        const brandEl = document.getElementById('sidebarBrand');
        if (brandEl && ownerMerchantInfo.name) brandEl.textContent = ownerMerchantInfo.name;
    } catch (e) {
        document.getElementById('infoSaveResult').innerHTML = `<div class="alert alert-danger py-2">${e.message}</div>`;
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
                            <input class="form-control bg-light" id="reviewUrlInput" value="${reviewUrl}" readonly style="font-size:.8rem;">
                            <button class="btn btn-primary" onclick="copyReviewUrl()" title="복사"><i class="fas fa-copy"></i></button>
                        </div>
                    </div>

                    <!-- 플레이스 URL -->
                    <div class="mb-3">
                        <label class="form-label fw-bold small mb-1">플레이스 URL</label>
                        <input class="form-control form-control-sm" id="reviewPlaceUrl" value="${config.place_url || ''}" placeholder="https://map.naver.com/...">
                    </div>

                    <!-- 환영 메시지 -->
                    <div class="mb-3">
                        <label class="form-label fw-bold small mb-1">환영 메시지</label>
                        <textarea class="form-control form-control-sm" id="reviewWelcomeMsg" rows="2" placeholder="방문해주셔서 감사합니다!">${config.welcome_message || ''}</textarea>
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
                    <code class="d-block bg-light p-2 rounded small mb-2" style="word-break:break-all;font-size:.75rem;">${reviewUrl}</code>
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
        const hasImage = !!r.receipt_image_url;
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
                        <img src="${r.receipt_image_url}" alt="영수증" 
                             style="width:56px;height:56px;object-fit:cover;border-radius:8px;">
                    ` : `
                        <div style="width:56px;height:56px;border-radius:8px;background:#f1f5f9;display:flex;align-items:center;justify-content:center;">
                            <i class="fas fa-receipt text-muted"></i>
                        </div>
                    `}
                </div>
                <div class="flex-grow-1 min-w-0">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="fw-bold" style="font-size:.9rem;">${r.customer_name || '익명 고객'}</span>
                        <div class="d-flex align-items-center gap-1">
                            ${reviewStatusBadge(r.status)}
                            ${r.review_completed ? '<span class="badge bg-info bg-opacity-75" title="플레이스 리뷰 완료"><i class="fas fa-star"></i></span>' : ''}
                        </div>
                    </div>
                    ${hasMemo ? `<p class="mb-1 small text-dark" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;"><i class="fas fa-comment text-primary me-1" style="font-size:.7rem;"></i>${r.memo}</p>` : ''}
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

    const hasImage = !!r.receipt_image_url;
    const body = document.getElementById('reviewDetailBody');
    const footer = document.getElementById('reviewDetailFooter');

    body.innerHTML = `
    <div class="row g-4">
        <!-- 영수증 이미지 -->
        <div class="col-md-5 text-center">
            ${hasImage ? `
                <div class="position-relative">
                    <img src="${r.receipt_image_url}" alt="영수증 이미지" 
                         class="img-fluid rounded shadow-sm" style="max-height:400px;cursor:pointer;" 
                         onclick="window.open('${r.receipt_image_url}','_blank')">
                    <div class="mt-2">
                        <a href="${r.receipt_image_url}" target="_blank" class="btn btn-sm btn-outline-primary">
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
                        <td>${r.customer_name || '<span class="text-muted fst-italic">미입력</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted fw-bold"><i class="fas fa-phone me-1"></i>연락처</td>
                        <td>${r.customer_phone || '<span class="text-muted fst-italic">미입력</span>'}</td>
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
                    ${r.memo ? r.memo : '고객이 리뷰를 남기지 않았습니다.'}
                </div>
            </div>

            <!-- 관리자 메모 입력 -->
            <div class="mt-3">
                <label class="form-label fw-bold small"><i class="fas fa-sticky-note text-warning me-1"></i>관리자 메모 (내부용)</label>
                <textarea class="form-control form-control-sm" id="modalAdminMemo" rows="2" 
                          placeholder="관리 참고용 메모를 입력하세요...">${r.admin_memo || ''}</textarea>
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
        document.getElementById('reviewConfigResult').innerHTML = `<div class="alert alert-danger py-1 small">${e.message}</div>`;
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
        <div id="designerTxBody"><div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div></div>
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
            <td>${tx.installment_months||'일시불'}</td><td>${tx.card_brand||'-'}</td>
            <td><code>${tx.approval_code||'-'}</code></td><td>${formatDate(tx.created_at)}</td>
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
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이름</span><span class="fw-bold">${stats.staff_name}</span></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">직원 코드</span><code class="fs-5">${stats.staff_code}</code></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">역할</span><span class="badge bg-warning">직원(디자이너)</span></li>
            <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이번달 매출</span><span class="fw-bold text-primary">${formatMoney(stats.month_sales)}</span></li>
            <li class="d-flex justify-content-between"><span class="text-muted">총 결제건수</span><span class="fw-bold">${stats.total_transactions}건</span></li>
        </ul>
    </div></div>`;
}


// ═══════════════════════════════════════════════════════════
// LANDLORD (방긋페이) PAGES — Enhanced v3
// ═══════════════════════════════════════════════════════════

const PROP_TYPE_KR = {apartment:'아파트', officetel:'오피스텔', commercial:'상가', villa:'빌라', other:'기타'};
const PROP_EMOJI = {apartment:'🏢', officetel:'🏠', commercial:'🏪', villa:'🏘️', other:'📋'};

// 임차인 목록 전역 캐시
let _landlordTenants = [];

async function loadLandlordTenants(c, t) {
    t.textContent = '임차인 목록';
    const tenants = await apiGet('/api/landlord/tenants');
    _landlordTenants = tenants;
    const active = tenants.filter(t => t.is_active);
    const paidCnt = active.filter(t => t.paid_this_month).length;
    const unpaidCnt = active.length - paidCnt;
    const totalRent = active.reduce((s,t) => s + t.monthly_rent, 0);

    c.innerHTML = `
    <!-- 요약 카드 -->
    <div class="row g-3 mb-4">
        ${kpiCard('전체 임차인', active.length + '명', 'users', 'warning')}
        ${kpiCard('이번달 납부', paidCnt + '명', 'check-circle', 'success')}
        ${kpiCard('미납', unpaidCnt + '명', 'exclamation-triangle', 'danger')}
        ${kpiCard('월 예정 수금', formatMoney(totalRent), 'won-sign', 'info')}
    </div>

    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <button class="btn btn-sm btn-outline-secondary me-1 tenant-filter active" onclick="filterTenants('all',this)">전체</button>
            <button class="btn btn-sm btn-outline-success me-1 tenant-filter" onclick="filterTenants('paid',this)">납부 완료</button>
            <button class="btn btn-sm btn-outline-warning tenant-filter" onclick="filterTenants('unpaid',this)">미납</button>
        </div>
        <button class="btn btn-sm text-white" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none;border-radius:8px;padding:8px 20px" onclick="showAddTenantModal()"><i class="fas fa-plus me-1"></i>임차인 등록</button>
    </div>
    <div class="card data-card"><div class="card-body p-0">
        <div class="table-responsive"><table class="table table-hover mb-0" id="tenantTable">
            <thead><tr><th></th><th>이름</th><th>임대물건</th><th>호수</th><th>월세</th><th>납부일</th><th>이번달</th><th>결제방식</th><th style="width:140px">관리</th></tr></thead>
            <tbody>
            ${tenants.map(tn => `
                <tr data-paid="${tn.paid_this_month}" data-active="${tn.is_active}" ${!tn.is_active ? 'class="table-secondary"' : ''}>
                    <td>${PROP_EMOJI[tn.property_type] || '📋'}</td>
                    <td class="fw-bold">${tn.name} ${!tn.is_active ? '<span class="badge bg-secondary ms-1">비활성</span>' : ''}</td>
                    <td><span class="badge bg-secondary" style="font-size:.72rem">${tn.property_type_kr}</span><br><span style="font-size:.82rem">${tn.property_name}</span></td>
                    <td class="fw-bold">${tn.unit_number}</td>
                    <td class="fw-bold" style="color:#ff6b35">${formatMoney(tn.monthly_rent)}</td>
                    <td>매월 ${tn.rent_due_day}일</td>
                    <td>${tn.paid_this_month ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>완료</span>' : '<span class="badge bg-warning text-dark"><i class="fas fa-clock me-1"></i>미납</span>'}</td>
                    <td>${tn.is_recurring ? '<span class="badge bg-info"><i class="fas fa-sync-alt me-1"></i>정기</span>' : '<span class="badge border text-muted">일반</span>'}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-info" title="결제내역" onclick="showTenantPaymentHistory(${tn.id},'${tn.name.replace(/'/g,"\\'")}','${tn.property_name.replace(/'/g,"\\'")} ${tn.unit_number}')"><i class="fas fa-credit-card"></i></button>
                            <button class="btn btn-outline-dark" title="QR" onclick="showTenantQR('${tn.qr_token}','${tn.property_name.replace(/'/g,"\\'")}','${tn.unit_number}','${tn.name.replace(/'/g,"\\'")}','${PROP_TYPE_KR[tn.property_type] || tn.property_type_kr}')"><i class="fas fa-qrcode"></i></button>
                            <button class="btn btn-outline-primary" title="수정" onclick="showEditTenantModal(${tn.id})"><i class="fas fa-edit"></i></button>
                            <button class="btn btn-outline-danger" title="${tn.is_active ? '비활성화' : '삭제'}" onclick="deleteTenant(${tn.id})"><i class="fas fa-ban"></i></button>
                        </div>
                    </td>
                </tr>
            `).join('')}
            </tbody>
        </table></div>
    </div></div>`;
}

function filterTenants(type, btn) {
    document.querySelectorAll('.tenant-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#tenantTable tbody tr').forEach(row => {
        if (type === 'all') { row.style.display = ''; return; }
        const paid = row.dataset.paid === 'true';
        row.style.display = (type === 'paid' && paid) || (type === 'unpaid' && !paid) ? '' : 'none';
    });
}

async function showEditTenantModal(tenantId) {
    const tn = _landlordTenants.find(t => t.id === tenantId);
    if (!tn) { alert('임차인 정보를 찾을 수 없습니다'); return; }
    
    // 프로필에서 등록된 임대물건명 목록 로드
    let propNames = [];
    try {
        const profile = await apiGet('/api/landlord/profile');
        propNames = profile.property_names || [];
    } catch(e) {}
    
    const propOptions = propNames.map(n => 
        `<option value="${n}" ${n === tn.property_name ? 'selected' : ''}>${n}</option>`
    ).join('');
    const isCustom = !propNames.includes(tn.property_name);
    
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '임차인 수정: ' + tn.name;
    document.getElementById('formModalBody').innerHTML = `
        <div class="row g-3">
            <div class="col-md-6"><label class="form-label fw-bold small">이름</label><input type="text" class="form-control" id="et_name" value="${tn.name}"></div>
            <div class="col-md-6"><label class="form-label fw-bold small">연락처</label><input type="text" class="form-control" id="et_phone" value="${tn.phone || ''}"></div>
            <div class="col-md-6">
                <label class="form-label fw-bold small">임대물건명</label>
                ${propNames.length > 0 ? `
                <select class="form-select" id="et_pname_select" onchange="if(this.value==='__custom__'){document.getElementById('et_pname_custom_wrap').style.display='block';}else{document.getElementById('et_pname_custom_wrap').style.display='none';}">
                    ${isCustom ? `<option value="${tn.property_name}" selected>${tn.property_name}</option>` : ''}
                    ${propOptions}
                    <option value="__custom__">✏️ 직접입력</option>
                </select>
                <div id="et_pname_custom_wrap" style="display:none;margin-top:4px">
                    <input type="text" class="form-control form-control-sm" id="et_pname_custom" placeholder="새 임대물건명">
                </div>` : `
                <input type="text" class="form-control" id="et_pname_direct" value="${tn.property_name}">
                `}
            </div>
            <div class="col-md-6"><label class="form-label fw-bold small">호수</label><input type="text" class="form-control" id="et_unit" value="${tn.unit_number}"></div>
            <div class="col-md-4"><label class="form-label fw-bold small">월세</label><input type="number" class="form-control" id="et_rent" value="${tn.monthly_rent}"></div>
            <div class="col-md-4"><label class="form-label fw-bold small">납부일</label><input type="number" class="form-control" id="et_due" value="${tn.rent_due_day}" min="1" max="31"></div>
            <div class="col-md-4"><label class="form-label fw-bold small">메모</label><input type="text" class="form-control" id="et_memo" value="${tn.memo || ''}"></div>
            <div class="col-12"><div class="form-check"><input type="checkbox" class="form-check-input" id="et_recurring" ${tn.is_recurring ? 'checked' : ''}><label class="form-check-label">정기결제</label></div></div>
        </div>`;
    document.getElementById('formModalFooter').innerHTML = `<button class="btn btn-secondary" data-bs-dismiss="modal">취소</button><button class="btn text-white" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none" onclick="updateTenant(${tn.id})">저장</button>`;
    new bootstrap.Modal(modal).show();
}

async function updateTenant(id) {
    const fd = new FormData();
    fd.append('name', document.getElementById('et_name').value);
    fd.append('phone', document.getElementById('et_phone').value);
    // 임대물건명
    let pname = '';
    const selectEl = document.getElementById('et_pname_select');
    const directEl = document.getElementById('et_pname_direct');
    if (selectEl) {
        pname = selectEl.value === '__custom__' 
            ? (document.getElementById('et_pname_custom')?.value || '').trim() 
            : selectEl.value;
    } else if (directEl) {
        pname = directEl.value.trim();
    }
    if (pname) fd.append('property_name', pname);
    const unit = document.getElementById('et_unit')?.value;
    if (unit) fd.append('unit_number', unit);
    fd.append('monthly_rent', document.getElementById('et_rent').value);
    fd.append('rent_due_day', document.getElementById('et_due').value);
    fd.append('memo', document.getElementById('et_memo').value);
    fd.append('is_recurring', document.getElementById('et_recurring').checked);
    try {
        await apiPutForm(`/api/landlord/tenants/${id}`, fd);
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        navigate('landlord-tenants');
    } catch (e) { alert('수정 실패: ' + e.message); }
}

async function loadLandlordQR(c, t) {
    t.textContent = 'QR코드 관리';
    const tenants = await apiGet('/api/landlord/tenants');
    const baseUrl = window.location.origin;
    const activeTenants = tenants.filter(t => t.is_active);

    c.innerHTML = `
    <!-- 안내 배너 -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2d1b03 0%,#5a3408 50%,#ff9f1c 100%);">
        <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
            <div class="d-flex align-items-center gap-3">
                <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;">
                    <i class="fas fa-qrcode text-white" style="font-size:1.2rem"></i>
                </div>
                <div>
                    <h5 class="mb-0 text-white fw-bold">결제 QR코드 관리</h5>
                    <small style="color:rgba(255,255,255,.7)">임차인별 전용 결제 QR코드 · 스캔 시 결제 페이지로 이동</small>
                </div>
            </div>
            <span class="badge" style="background:rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:50px;font-size:.78rem;">
                <i class="fas fa-check-circle me-1"></i>활성 QR ${activeTenants.length}개
            </span>
        </div>
    </div>

    <!-- PG 연동 안내 -->
    <div class="alert border-0 mb-4 py-3" style="background:linear-gradient(135deg,rgba(14,165,233,.05),rgba(14,165,233,.1));border-radius:12px">
        <div class="d-flex align-items-start gap-2">
            <i class="fas fa-shield-alt mt-1" style="color:#0ea5e9;font-size:1rem"></i>
            <div>
                <strong style="color:#0ea5e9">PG 결제 연동 안내</strong>
                <p class="mb-0 mt-1" style="font-size:.82rem;color:#666">
                    현재 QR코드는 <strong>결제 페이지 연결용</strong>으로 생성됩니다. 
                    PG사(결제대행사) 연동이 완료되면, 각 QR코드를 통해 <strong>실제 카드결제</strong>가 가능해집니다.
                    <br><span class="text-muted"><i class="fas fa-info-circle me-1"></i>정기결제 설정된 임차인은 매월 자동 결제가 진행됩니다.</span>
                </p>
            </div>
        </div>
    </div>

    <!-- QR 카드 그리드 -->
    ${activeTenants.length === 0 
        ? '<div class="text-center py-5"><i class="fas fa-qrcode fa-3x mb-3" style="color:#ddd"></i><h5 class="text-muted">등록된 활성 임차인이 없습니다</h5><p class="text-muted">임차인 목록에서 임차인을 등록하면 QR코드가 자동 생성됩니다.</p><a href="#" onclick="navigate(\'landlord-tenants\')" class="btn btn-sm text-white" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none;border-radius:8px"><i class="fas fa-plus me-1"></i>임차인 등록하기</a></div>'
        : `<div class="row g-3">
    ${activeTenants.map(t => {
        const payUrl = `${baseUrl}/pay/${t.qr_token}`;
        const qrImg = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(payUrl)}&color=1b3a5c&bgcolor=ffffff`;
        return `
        <div class="col-lg-4 col-md-6">
            <div class="card data-card text-center h-100" style="border-radius:16px;overflow:hidden">
                <div class="card-header py-2 px-3 d-flex justify-content-between align-items-center" style="background:linear-gradient(135deg,rgba(255,107,53,.04),rgba(255,159,28,.06))">
                    <div class="text-start">
                        <span style="font-size:1.1rem;margin-right:4px">${PROP_EMOJI[t.property_type] || '📋'}</span>
                        <strong style="font-size:.88rem">${t.property_name}</strong>
                        <span class="text-muted" style="font-size:.78rem">${t.unit_number}</span>
                    </div>
                    ${t.is_recurring ? '<span class="badge bg-info" style="font-size:.68rem"><i class="fas fa-sync-alt me-1"></i>정기결제</span>' : '<span class="badge bg-secondary" style="font-size:.68rem">일반결제</span>'}
                </div>
                <div class="card-body py-3">
                    <div class="mb-2">
                        <span class="fw-bold" style="font-size:.95rem">${t.name}</span>
                    </div>
                    <div class="mb-2">
                        <span class="text-muted" style="font-size:.78rem">월세</span>
                        <strong style="color:#ff6b35;font-size:1.05rem"> ${formatMoney(t.monthly_rent)}</strong>
                        <span class="text-muted" style="font-size:.72rem">· 매월 ${t.rent_due_day}일</span>
                    </div>
                    <!-- QR 코드 -->
                    <div class="position-relative d-inline-block mb-2">
                        <div style="padding:10px;background:#fff;border-radius:14px;border:2px solid #e8e8e8;display:inline-block">
                            <img src="${qrImg}" style="width:150px;height:150px;border-radius:8px" alt="결제 QR코드">
                        </div>
                        <div class="position-absolute" style="bottom:-5px;right:-5px;width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#ff6b35,#ff9f1c);display:flex;align-items:center;justify-content:center">
                            <i class="fas fa-credit-card text-white" style="font-size:.65rem"></i>
                        </div>
                    </div>
                    <!-- 결제 URL -->
                    <div class="input-group input-group-sm mb-2">
                        <input type="text" class="form-control text-center" value="${payUrl}" readonly style="font-size:.62rem;border-radius:6px 0 0 6px">
                        <button class="btn btn-outline-secondary" style="border-radius:0 6px 6px 0" onclick="navigator.clipboard.writeText('${payUrl}');this.innerHTML='<i class=\\'fas fa-check text-success\\'></i>';setTimeout(()=>this.innerHTML='<i class=\\'fas fa-copy\\'></i>',1500)"><i class="fas fa-copy"></i></button>
                    </div>
                    <!-- 상태 표시 -->
                    <div class="d-flex justify-content-center gap-1 mb-2" style="font-size:.72rem">
                        ${t.paid_this_month 
                            ? '<span class="badge bg-success py-1 px-2"><i class="fas fa-check me-1"></i>이번달 납부 완료</span>' 
                            : '<span class="badge bg-warning text-dark py-1 px-2"><i class="fas fa-clock me-1"></i>이번달 미납</span>'}
                    </div>
                    <!-- 버튼 -->
                    <div class="d-flex gap-1 justify-content-center">
                        <button class="btn btn-sm btn-outline-dark" onclick="showTenantQR('${t.qr_token}','${t.property_name.replace(/'/g,"\\'")}','${t.unit_number}','${t.name.replace(/'/g,"\\'")}','${PROP_TYPE_KR[t.property_type] || t.property_type_kr}')" title="상세보기"><i class="fas fa-expand me-1"></i>크게보기</button>
                        <button class="btn btn-sm btn-outline-secondary" onclick="window.print()" title="인쇄"><i class="fas fa-print"></i></button>
                        <button class="btn btn-sm btn-outline-warning" onclick="regenerateQR(${t.id})" title="재발급"><i class="fas fa-sync"></i></button>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('')}
    </div>`}`;
}

async function loadLandlordPayments(c, t) {
    t.textContent = '결제 내역';
    const [payments, tenants] = await Promise.all([
        apiGet('/api/landlord/payments'),
        apiGet('/api/landlord/tenants'),
    ]);
    const total = payments.reduce((s,p) => s + (p.status === 'paid' ? p.amount : 0), 0);
    const paidCnt = payments.filter(p => p.status === 'paid').length;

    // 임차인 옵션
    const tenantOpts = tenants.filter(tn => tn.is_active).map(tn =>
        `<option value="${tn.id}">${tn.name} (${tn.property_name} ${tn.unit_number})</option>`
    ).join('');
    // 결제월 고유값
    const months = [...new Set(payments.map(p => p.payment_month).filter(Boolean))].sort().reverse();
    const monthOpts = months.map(m => `<option value="${m}">${m}</option>`).join('');

    c.innerHTML = `
    <div class="row g-3 mb-4">
        ${kpiCard('전체 결제', payments.length + '건', 'receipt', 'primary')}
        ${kpiCard('결제 완료', paidCnt + '건', 'check-circle', 'success')}
        ${kpiCard('총 결제액', formatMoney(total), 'won-sign', 'warning')}
        ${kpiCard('평균 결제액', payments.length > 0 ? formatMoney(Math.round(total / Math.max(paidCnt,1))) : '₩0', 'calculator', 'info')}
    </div>

    <!-- 필터 영역 -->
    <div class="card data-card mb-4" style="border-radius:14px">
        <div class="card-header py-2"><h5 class="mb-0"><i class="fas fa-filter me-2 text-info"></i>결제내역 필터</h5></div>
        <div class="card-body">
            <div class="row g-2 align-items-end">
                <div class="col-6 col-md-3">
                    <label class="form-label small mb-1"><i class="fas fa-user me-1"></i>임차인</label>
                    <select class="form-select form-select-sm" id="llPayFilterTenant">
                        <option value="">전체 임차인</option>${tenantOpts}
                    </select>
                </div>
                <div class="col-6 col-md-2">
                    <label class="form-label small mb-1"><i class="fas fa-calendar me-1"></i>결제월</label>
                    <select class="form-select form-select-sm" id="llPayFilterMonth">
                        <option value="">전체</option>${monthOpts}
                    </select>
                </div>
                <div class="col-6 col-md-2">
                    <label class="form-label small mb-1">시작일</label>
                    <input type="date" class="form-control form-control-sm" id="llPayFilterFrom">
                </div>
                <div class="col-6 col-md-2">
                    <label class="form-label small mb-1">종료일</label>
                    <input type="date" class="form-control form-control-sm" id="llPayFilterTo">
                </div>
                <div class="col-6 col-md-2">
                    <label class="form-label small mb-1">상태</label>
                    <select class="form-select form-select-sm" id="llPayFilterStatus">
                        <option value="">전체</option>
                        <option value="paid">완료</option>
                        <option value="pending">대기</option>
                        <option value="overdue">연체</option>
                    </select>
                </div>
                <div class="col-6 col-md-1 d-flex gap-1">
                    <button class="btn btn-sm w-100" style="background:#ff9f1c;color:#fff;border:none" onclick="applyLandlordPayFilter()"><i class="fas fa-search"></i></button>
                    <button class="btn btn-sm btn-outline-secondary w-100" onclick="resetLandlordPayFilter()" title="초기화"><i class="fas fa-redo"></i></button>
                </div>
            </div>
        </div>
    </div>

    <!-- 요약 탭 -->
    <div class="mb-3">
        <ul class="nav nav-pills nav-fill" style="gap:4px">
            <li class="nav-item"><a class="nav-link active llpay-tab" href="#" onclick="switchLandlordPayTab('list',this)" style="font-size:.82rem;border-radius:8px"><i class="fas fa-list me-1"></i>상세내역</a></li>
            <li class="nav-item"><a class="nav-link llpay-tab" href="#" onclick="switchLandlordPayTab('monthly',this)" style="font-size:.82rem;border-radius:8px"><i class="fas fa-calendar-alt me-1"></i>월별 요약</a></li>
            <li class="nav-item"><a class="nav-link llpay-tab" href="#" onclick="switchLandlordPayTab('daily',this)" style="font-size:.82rem;border-radius:8px"><i class="fas fa-calendar-day me-1"></i>일별 요약</a></li>
            <li class="nav-item"><a class="nav-link llpay-tab" href="#" onclick="switchLandlordPayTab('tenant',this)" style="font-size:.82rem;border-radius:8px"><i class="fas fa-users me-1"></i>임차인별</a></li>
        </ul>
    </div>

    <div id="llPayTabContent">
        <!-- 상세내역 (기본) -->
        <div class="card data-card" id="llPayListView">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="fas fa-credit-card me-2" style="color:#ff9f1c"></i>결제 내역</h5>
                <span class="badge bg-secondary" id="llPayCount">${payments.length}건</span>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive"><table class="table table-hover mb-0" id="llPayTable">
                    <thead class="table-light"><tr><th>임차인</th><th>물건 정보</th><th>금액</th><th>결제월</th><th>결제방식</th><th>카드사</th><th>승인번호</th><th>상태</th><th>결제일</th></tr></thead>
                    <tbody id="llPayTableBody"></tbody>
                </table></div>
            </div>
        </div>
        <div class="card data-card d-none" id="llPaySummaryView">
            <div class="card-header"><h5 class="mb-0" id="llPaySummaryTitle"><i class="fas fa-chart-bar me-2" style="color:#ff9f1c"></i>요약</h5></div>
            <div class="card-body" id="llPaySummaryBody"></div>
        </div>
    </div>`;

    // 초기 렌더
    _landlordPaymentsCache = payments;
    _landlordTenantsCache = tenants;
    renderLandlordPayTable(payments);
}

let _landlordPaymentsCache = [];
let _landlordTenantsCache = [];

function renderLandlordPayTable(payments) {
    const tbody = document.getElementById('llPayTableBody');
    const countEl = document.getElementById('llPayCount');
    if (!tbody) return;
    if (countEl) countEl.textContent = payments.length + '건';
    if (payments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4"><i class="fas fa-inbox me-2"></i>결제 내역이 없습니다</td></tr>';
        return;
    }
    tbody.innerHTML = payments.map(p => `
        <tr>
            <td class="fw-bold">${p.tenant_name}</td>
            <td style="font-size:.82rem">${p.property_info}</td>
            <td class="fw-bold" style="color:#ff6b35">${formatMoney(p.amount)}</td>
            <td><span class="badge bg-light text-dark border">${p.payment_month}</span></td>
            <td>${p.payment_method === 'card_recurring' ? '<span class="badge bg-info"><i class="fas fa-sync-alt me-1"></i>정기</span>' : '<span class="badge bg-secondary">일반</span>'}</td>
            <td>${p.card_brand || '-'}</td>
            <td><code style="font-size:.72rem">${p.approval_code || '-'}</code></td>
            <td><span class="badge bg-${p.status === 'paid' ? 'success' : p.status === 'pending' ? 'warning' : 'danger'}"><i class="fas fa-${p.status === 'paid' ? 'check' : 'clock'} me-1"></i>${p.status === 'paid' ? '완료' : p.status === 'pending' ? '대기' : '연체'}</span></td>
            <td style="font-size:.78rem">${p.paid_at ? p.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
        </tr>
    `).join('');
}

async function applyLandlordPayFilter() {
    const tenantId = document.getElementById('llPayFilterTenant').value;
    const month = document.getElementById('llPayFilterMonth').value;
    const from = document.getElementById('llPayFilterFrom').value;
    const to = document.getElementById('llPayFilterTo').value;
    const status = document.getElementById('llPayFilterStatus').value;

    let qs = [];
    if (tenantId) qs.push('tenant_id=' + tenantId);
    if (month) qs.push('month=' + month);
    if (from) qs.push('date_from=' + from);
    if (to) qs.push('date_to=' + to);
    if (status) qs.push('status=' + status);

    try {
        const payments = await apiGet('/api/landlord/payments' + (qs.length ? '?' + qs.join('&') : ''));
        _landlordPaymentsCache = payments;
        // 현재 탭 확인
        const activeTab = document.querySelector('.llpay-tab.active');
        const tabName = activeTab ? activeTab.textContent.trim() : '';
        if (tabName.includes('월별')) renderLandlordPaySummary('month');
        else if (tabName.includes('일별')) renderLandlordPaySummary('day');
        else if (tabName.includes('임차인')) renderLandlordPayByTenant();
        else renderLandlordPayTable(payments);
    } catch(e) { alert('조회 실패: ' + e.message); }
}

function resetLandlordPayFilter() {
    document.getElementById('llPayFilterTenant').value = '';
    document.getElementById('llPayFilterMonth').value = '';
    document.getElementById('llPayFilterFrom').value = '';
    document.getElementById('llPayFilterTo').value = '';
    document.getElementById('llPayFilterStatus').value = '';
    applyLandlordPayFilter();
}

function switchLandlordPayTab(tab, el) {
    document.querySelectorAll('.llpay-tab').forEach(a => a.classList.remove('active'));
    el.classList.add('active');
    const listView = document.getElementById('llPayListView');
    const summaryView = document.getElementById('llPaySummaryView');
    if (tab === 'list') {
        listView.classList.remove('d-none'); summaryView.classList.add('d-none');
        renderLandlordPayTable(_landlordPaymentsCache);
    } else if (tab === 'monthly') {
        listView.classList.add('d-none'); summaryView.classList.remove('d-none');
        renderLandlordPaySummary('month');
    } else if (tab === 'daily') {
        listView.classList.add('d-none'); summaryView.classList.remove('d-none');
        renderLandlordPaySummary('day');
    } else if (tab === 'tenant') {
        listView.classList.add('d-none'); summaryView.classList.remove('d-none');
        renderLandlordPayByTenant();
    }
}

function renderLandlordPaySummary(groupBy) {
    const title = document.getElementById('llPaySummaryTitle');
    const body = document.getElementById('llPaySummaryBody');
    const payments = _landlordPaymentsCache.filter(p => p.status === 'paid');
    if (title) title.innerHTML = `<i class="fas fa-chart-bar me-2" style="color:#ff9f1c"></i>${groupBy === 'month' ? '월별' : '일별'} 결제 요약`;

    const summary = {};
    payments.forEach(p => {
        const key = groupBy === 'day' ? (p.paid_at ? p.paid_at.slice(0,10) : 'unknown') : (p.payment_month || 'unknown');
        if (!summary[key]) summary[key] = {period: key, count: 0, amount: 0};
        summary[key].count += 1;
        summary[key].amount += p.amount;
    });
    const sorted = Object.values(summary).sort((a,b) => b.period.localeCompare(a.period));
    const maxAmt = Math.max(...sorted.map(s => s.amount), 1);
    const totalAmt = sorted.reduce((s,r) => s + r.amount, 0);
    const totalCnt = sorted.reduce((s,r) => s + r.count, 0);

    body.innerHTML = `
    <div class="d-flex gap-3 mb-3 flex-wrap">
        <span class="badge px-3 py-2" style="background:#ff9f1c;font-size:.8rem">총 ${totalCnt}건</span>
        <span class="badge bg-success px-3 py-2" style="font-size:.8rem">총 ${formatMoney(totalAmt)}</span>
    </div>
    ${sorted.length === 0 ? '<p class="text-muted text-center py-3">데이터 없음</p>' : `
    <div class="table-responsive"><table class="table table-sm table-hover mb-0">
        <thead class="table-light"><tr><th>${groupBy === 'month' ? '결제월' : '결제일'}</th><th>건수</th><th>금액</th><th>비율</th></tr></thead>
        <tbody>${sorted.map(r => `
            <tr>
                <td class="fw-bold">${r.period}</td>
                <td>${r.count}건</td>
                <td class="fw-bold" style="color:#ff6b35">${formatMoney(r.amount)}</td>
                <td>
                    <div class="d-flex align-items-center gap-2">
                        <div style="flex:1;height:6px;background:#f0f0f0;border-radius:3px;overflow:hidden">
                            <div style="width:${Math.round(r.amount/maxAmt*100)}%;height:100%;background:linear-gradient(90deg,#ff6b35,#ff9f1c);border-radius:3px"></div>
                        </div>
                        <span style="font-size:.72rem;min-width:35px;text-align:right">${totalAmt>0?Math.round(r.amount/totalAmt*100):'0'}%</span>
                    </div>
                </td>
            </tr>
        `).join('')}</tbody>
    </table></div>`}`;
}

function renderLandlordPayByTenant() {
    const title = document.getElementById('llPaySummaryTitle');
    const body = document.getElementById('llPaySummaryBody');
    const payments = _landlordPaymentsCache;
    if (title) title.innerHTML = '<i class="fas fa-users me-2" style="color:#ff9f1c"></i>임차인별 결제 요약';

    const summary = {};
    payments.forEach(p => {
        const key = p.tenant_id || p.tenant_name;
        if (!summary[key]) summary[key] = {name: p.tenant_name, info: p.property_info, paid: 0, paidAmt: 0, pending: 0, total: 0};
        summary[key].total += 1;
        if (p.status === 'paid') { summary[key].paid += 1; summary[key].paidAmt += p.amount; }
        else summary[key].pending += 1;
    });
    const sorted = Object.values(summary).sort((a,b) => b.paidAmt - a.paidAmt);
    const totalAmt = sorted.reduce((s,r) => s + r.paidAmt, 0);

    body.innerHTML = `
    <div class="d-flex gap-3 mb-3 flex-wrap">
        <span class="badge px-3 py-2" style="background:#ff9f1c;font-size:.8rem">${sorted.length}명</span>
        <span class="badge bg-success px-3 py-2" style="font-size:.8rem">총 ${formatMoney(totalAmt)}</span>
    </div>
    ${sorted.length === 0 ? '<p class="text-muted text-center py-3">데이터 없음</p>' : `
    <div class="row g-3">${sorted.map(r => `
        <div class="col-md-6">
            <div class="card border shadow-sm h-100" style="border-radius:10px">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <div class="fw-bold">${r.name}</div>
                        <div class="fw-bold" style="color:#ff6b35">${formatMoney(r.paidAmt)}</div>
                    </div>
                    <div class="text-muted" style="font-size:.78rem">${r.info}</div>
                    <div class="d-flex gap-2 mt-1" style="font-size:.75rem">
                        <span class="badge bg-success">완료 ${r.paid}건</span>
                        ${r.pending > 0 ? `<span class="badge bg-warning text-dark">대기 ${r.pending}건</span>` : ''}
                        <span class="text-muted">총 ${r.total}건</span>
                    </div>
                </div>
            </div>
        </div>
    `).join('')}</div>`}`;
}

async function loadLandlordMonthly(c, t) {
    t.textContent = '월별 수금 현황';
    const stats = await apiGet('/api/landlord/dashboard-stats');
    const trend = stats.monthly_trend || [];
    const maxAmount = Math.max(...trend.map(t => t.amount), 1);

    c.innerHTML = `
    <div class="row g-3 mb-4">
        ${kpiCard('총 수금액', formatMoney(stats.total_collected), 'coins', 'warning')}
        ${kpiCard('이번달 수금', formatMoney(stats.month_collected), 'check-circle', 'success')}
        ${kpiCard('수금률', stats.collection_rate + '%', 'percentage', 'primary')}
        ${kpiCard('납부 완료', stats.month_paid_count + '건', 'receipt', 'info')}
    </div>
    
    <!-- 월별 납부 상태 조회 -->
    <div class="card data-card mb-4">
        <div class="card-header py-2"><h5 class="mb-0"><i class="fas fa-calendar-check me-2 text-success"></i>월별 임차인 납부 상태</h5></div>
        <div class="card-body">
            <div class="row g-2 mb-3 align-items-end">
                <div class="col-md-4">
                    <label class="form-label small mb-1">조회 월</label>
                    <input type="month" class="form-control form-control-sm" id="llMonthStatusMonth" value="${new Date().toISOString().slice(0,7)}">
                </div>
                <div class="col-md-3">
                    <button class="btn btn-sm btn-success" onclick="loadLandlordMonthlyStatus()"><i class="fas fa-search me-1"></i>납부 상태 조회</button>
                </div>
            </div>
            <div id="llMonthlyStatusResult"></div>
        </div>
    </div>
    
    <div class="row g-3">
        <div class="col-md-8">
            <div class="card data-card h-100">
                <div class="card-header"><h5><i class="fas fa-chart-bar me-2" style="color:#ff9f1c"></i>월별 수금 추이 (최근 6개월)</h5></div>
                <div class="card-body" style="height:320px"><canvas id="monthlyTrendChart2"></canvas></div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card data-card h-100">
                <div class="card-header"><h5><i class="fas fa-list-ol me-2 text-info"></i>월별 상세</h5></div>
                <div class="card-body p-0">
                    <div class="list-group list-group-flush">
                    ${trend.map(m => `
                        <div class="list-group-item d-flex justify-content-between align-items-center px-3 py-2">
                            <span class="fw-bold" style="font-size:.85rem">${m.month}</span>
                            <div class="d-flex align-items-center gap-2">
                                <div style="width:80px;height:6px;background:#f0f0f0;border-radius:3px;overflow:hidden">
                                    <div style="width:${Math.round(m.amount/maxAmount*100)}%;height:100%;background:linear-gradient(90deg,#ff6b35,#ff9f1c);border-radius:3px"></div>
                                </div>
                                <span class="fw-bold" style="font-size:.82rem;color:#ff6b35;min-width:70px;text-align:right">${formatMoney(m.amount)}</span>
                            </div>
                        </div>
                    `).join('')}
                    </div>
                </div>
            </div>
        </div>
    </div>`;
    setTimeout(() => {
        const ctx = document.getElementById('monthlyTrendChart2');
        if (ctx && typeof Chart !== 'undefined') {
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: trend.map(t => t.month),
                    datasets: [{label:'수금액', data: trend.map(t => t.amount), backgroundColor:'rgba(255,159,28,.5)', borderColor:'#ff9f1c', borderWidth:1, borderRadius:8}]
                },
                options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>'수금액: '+formatMoney(ctx.raw)}}}, scales:{y:{beginAtZero:true,ticks:{callback:v=>v>=10000?(v/10000)+'만':v.toLocaleString(),font:{size:11}},grid:{color:'rgba(0,0,0,.04)'}},x:{grid:{display:false},ticks:{font:{size:11}}}} }
            });
        }
    }, 100);
    
    // Auto-load current month status
    loadLandlordMonthlyStatus();
}

async function loadLandlordMonthlyStatus() {
    const month = document.getElementById('llMonthStatusMonth')?.value;
    if (!month) return;
    const el = document.getElementById('llMonthlyStatusResult');
    if (!el) return;
    el.innerHTML = '<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-warning"></div></div>';
    
    try {
        const data = await apiGet(`/api/landlord/monthly-status?month=${month}`);
        const paid = data.filter(d => d.status === 'paid').length;
        const unpaid = data.filter(d => d.status === 'unpaid').length;
        
        el.innerHTML = `
        <div class="mb-2 d-flex gap-3">
            <span class="badge bg-success px-3 py-2">납부 ${paid}명</span>
            <span class="badge bg-danger px-3 py-2">미납 ${unpaid}명</span>
            <span class="badge bg-secondary px-3 py-2">전체 ${data.length}명</span>
        </div>
        ${data.length === 0 ? '<p class="text-muted">해당 월의 데이터가 없습니다</p>' : `
        <div class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead class="table-light"><tr><th>임차인</th><th>물건</th><th>월세</th><th>납부상태</th><th>납부액</th><th>납부일</th></tr></thead>
                <tbody>
                ${data.map(d => `
                    <tr>
                        <td class="fw-bold">${d.tenant_name}</td>
                        <td style="font-size:.82rem">${d.property_info}</td>
                        <td style="color:#ff6b35">${formatMoney(d.monthly_rent)}</td>
                        <td><span class="badge bg-${d.status==='paid'?'success':'danger'}">${d.status==='paid'?'납부':'미납'}</span></td>
                        <td>${d.paid_amount > 0 ? formatMoney(d.paid_amount) : '-'}</td>
                        <td style="font-size:.78rem">${d.paid_at ? d.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
                    </tr>
                `).join('')}
                </tbody>
            </table>
        </div>`}`;
    } catch(e) { el.innerHTML = `<div class="alert alert-danger py-2">${e.message}</div>`; }
}

async function loadLandlordProfile(c, t) {
    t.textContent = '내 정보 관리';
    const p = await apiGet('/api/landlord/profile');
    const propNames = p.property_names || [];
    c.innerHTML = `
    <div class="row g-3">
        <div class="col-lg-7">
            <div class="card data-card mb-3">
                <div class="card-header"><h5 class="mb-0"><i class="fas fa-building me-2" style="color:#ff9f1c"></i>임대인 프로필</h5></div>
                <div class="card-body">
                    <form id="profileForm">
                        <div class="mb-3">
                            <label class="form-label fw-bold small">대표 건물명</label>
                            <input type="text" class="form-control" id="pf_building" value="${p.building_name || ''}" placeholder="대표 건물명 입력">
                            <small class="text-muted"><i class="fas fa-info-circle me-1"></i>대시보드에 표시되는 대표 건물명입니다</small>
                        </div>
                        <div class="mb-3"><label class="form-label fw-bold small">주소</label><input type="text" class="form-control" id="pf_address" value="${p.address || ''}" placeholder="예: 서울시 강남구 테헤란로 123"></div>
                        <div class="row g-3 mb-3">
                            <div class="col-md-6"><label class="form-label fw-bold small">전화번호</label><input type="text" class="form-control" id="pf_phone" value="${p.phone || ''}" placeholder="010-0000-0000"></div>
                            <div class="col-md-6"><label class="form-label fw-bold small">사업자번호</label><input type="text" class="form-control" id="pf_biz" value="${p.business_no || ''}" placeholder="000-00-00000"></div>
                        </div>
                        <div class="row g-3 mb-3">
                            <div class="col-md-4"><label class="form-label fw-bold small">은행명</label><input type="text" class="form-control" id="pf_bank" value="${p.bank_name || ''}"></div>
                            <div class="col-md-4"><label class="form-label fw-bold small">계좌번호</label><input type="text" class="form-control" id="pf_account" value="${p.bank_account || ''}"></div>
                            <div class="col-md-4"><label class="form-label fw-bold small">예금주</label><input type="text" class="form-control" id="pf_holder" value="${p.bank_holder || ''}"></div>
                        </div>
                        <button type="button" class="btn text-white w-100" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none;border-radius:8px" onclick="saveLandlordProfile()"><i class="fas fa-save me-2"></i>프로필 저장</button>
                    </form>
                </div>
            </div>

            <!-- 임대물건명 관리 -->
            <div class="card data-card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-home me-2" style="color:#ff6b35"></i>임대물건명 관리</h5>
                    <span class="badge" style="background:#ff9f1c;color:#fff">${propNames.length}건</span>
                </div>
                <div class="card-body">
                    <div class="alert border-0 py-2 px-3 mb-3" style="background:rgba(255,159,28,.06);border-radius:10px;font-size:.82rem">
                        <i class="fas fa-lightbulb me-1" style="color:#ff9f1c"></i>
                        <strong>임대물건명</strong>은 임차인 등록 시 자동으로 선택할 수 있도록 동기화됩니다.<br>
                        <span class="text-muted">예) <strong>강남센트럴상가</strong>, <strong>역삼오피스텔</strong>, <strong>서초타워빌딩</strong> 등</span>
                    </div>
                    <div class="d-flex gap-2 mb-3">
                        <input type="text" class="form-control form-control-sm" id="pf_new_property" placeholder="새 임대물건명 입력 (예: ***상가, **오피스텔 등)">
                        <button class="btn btn-sm text-white text-nowrap" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none;border-radius:8px;min-width:80px" onclick="addPropertyName()"><i class="fas fa-plus me-1"></i>추가</button>
                    </div>
                    <div id="propertyNamesList">
                        ${propNames.length === 0 
                            ? '<p class="text-muted text-center py-3" style="font-size:.85rem"><i class="fas fa-inbox me-2"></i>등록된 임대물건명이 없습니다</p>' 
                            : propNames.map(n => `
                            <div class="d-flex align-items-center justify-content-between py-2 px-3 mb-1 rounded" style="background:#f8f9fa">
                                <div><i class="fas fa-building me-2 text-muted"></i><span class="fw-bold" style="font-size:.88rem">${n}</span></div>
                                <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="deletePropertyName('${n.replace(/'/g,"\\'")}')" title="삭제"><i class="fas fa-times"></i></button>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>
        <div class="col-lg-5">
            <div class="card data-card h-100">
                <div class="card-header"><h5 class="mb-0"><i class="fas fa-info-circle me-2 text-info"></i>계정 정보</h5></div>
                <div class="card-body">
                    <ul class="list-unstyled mb-0">
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이름</span><span class="fw-bold">${currentUser.name}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이메일</span><span class="fw-bold">${currentUser.email}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">역할</span><span class="badge" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);color:#fff">임대인</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">대표 건물</span><span class="fw-bold">${p.building_name || '미등록'}</span></li>
                        <li class="mb-3 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">임대물건</span><span class="fw-bold">${propNames.length}건 등록</span></li>
                        <li class="d-flex justify-content-between"><span class="text-muted">상태</span><span class="badge bg-success">활성</span></li>
                    </ul>
                </div>
            </div>
        </div>
    </div>`;
}

// ─── Landlord helper functions ────────────────────────────

function showTenantQR(token, propName, unit, tenantName, propType) {
    const baseUrl = window.location.origin;
    const qrUrl = `${baseUrl}/pay/${token}`;
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = 'QR코드 상세';
    document.getElementById('formModalBody').innerHTML = `
        <div class="text-center">
            <span class="badge bg-secondary mb-2">${propType}</span>
            <h5>${propName} ${unit}</h5>
            <p class="text-muted mb-3">임차인: <strong>${tenantName}</strong></p>
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(qrUrl)}" style="width:220px;height:220px;border-radius:14px;border:3px solid #f0f0f0" class="mb-3">
            <div class="input-group mb-3"><input type="text" class="form-control" value="${qrUrl}" readonly id="qrUrlInput"><button class="btn btn-outline-secondary" onclick="navigator.clipboard.writeText(document.getElementById('qrUrlInput').value);this.innerHTML='<i class=\\'fas fa-check text-success\\'></i>';setTimeout(()=>this.innerHTML='<i class=\\'fas fa-copy\\'></i>',1500)"><i class="fas fa-copy"></i></button></div>
            <p class="text-muted" style="font-size:.75rem"><i class="fas fa-info-circle me-1"></i>임차인이 이 QR코드를 스캔하면 결제 페이지로 이동합니다</p>
        </div>`;
    document.getElementById('formModalFooter').innerHTML = `<button class="btn btn-outline-secondary" onclick="window.print()"><i class="fas fa-print me-1"></i>인쇄</button><button class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>`;
    new bootstrap.Modal(modal).show();
}

async function showAddTenantModal() {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '새 임차인 등록';
    
    // 프로필에서 등록된 임대물건명 목록 로드
    let propNames = [];
    try {
        const profile = await apiGet('/api/landlord/profile');
        propNames = profile.property_names || [];
    } catch(e) {}
    
    const propOptions = propNames.map(n => `<option value="${n}">${n}</option>`).join('');
    
    document.getElementById('formModalBody').innerHTML = `
        <div class="row g-3">
            <div class="col-md-6"><label class="form-label fw-bold small">임차인 이름 <span class="text-danger">*</span></label><input type="text" class="form-control" id="nt_name"></div>
            <div class="col-md-6"><label class="form-label fw-bold small">연락처</label><input type="text" class="form-control" id="nt_phone" placeholder="010-0000-0000"></div>
            <div class="col-md-6"><label class="form-label fw-bold small">물건 유형</label>
                <select class="form-select" id="nt_ptype"><option value="apartment">🏢 아파트</option><option value="officetel" selected>🏠 오피스텔</option><option value="commercial">🏪 상가</option><option value="villa">🏘️ 빌라</option><option value="other">📋 기타</option></select></div>
            <div class="col-md-6">
                <label class="form-label fw-bold small">임대물건명 <span class="text-danger">*</span></label>
                ${propNames.length > 0 ? `
                <div class="input-group">
                    <select class="form-select" id="nt_pname_select" onchange="if(this.value==='__custom__'){document.getElementById('nt_pname_custom_wrap').style.display='block';document.getElementById('nt_pname_custom').focus();}else{document.getElementById('nt_pname_custom_wrap').style.display='none';}">
                        <option value="">-- 임대물건 선택 --</option>
                        ${propOptions}
                        <option value="__custom__">✏️ 직접입력</option>
                    </select>
                </div>
                <div id="nt_pname_custom_wrap" style="display:none;margin-top:4px">
                    <input type="text" class="form-control form-control-sm" id="nt_pname_custom" placeholder="새 임대물건명 직접 입력">
                </div>` : `
                <input type="text" class="form-control" id="nt_pname_direct" placeholder="예: ***상가, **오피스텔 등">
                `}
                <small class="text-muted mt-1 d-block" style="font-size:.72rem"><i class="fas fa-info-circle me-1"></i>예) ***상가 **호, **오피스텔 **호 등으로 표기해 주세요</small>
            </div>
            <div class="col-md-4"><label class="form-label fw-bold small">호수 <span class="text-danger">*</span></label><input type="text" class="form-control" id="nt_unit" placeholder="예: 301호"></div>
            <div class="col-md-4"><label class="form-label fw-bold small">월세(원) <span class="text-danger">*</span></label><input type="number" class="form-control" id="nt_rent" placeholder="800000"></div>
            <div class="col-md-4"><label class="form-label fw-bold small">납부일</label><input type="number" class="form-control" id="nt_due" value="25" min="1" max="31"></div>
            <div class="col-12"><div class="form-check"><input type="checkbox" class="form-check-input" id="nt_recurring"><label class="form-check-label"><i class="fas fa-sync-alt me-1 text-info"></i>정기결제 설정 (매월 자동 결제)</label></div></div>
        </div>`;
    document.getElementById('formModalFooter').innerHTML = `<button class="btn btn-secondary" data-bs-dismiss="modal">취소</button><button class="btn text-white" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none" onclick="createTenant()"><i class="fas fa-plus me-1"></i>등록</button>`;
    new bootstrap.Modal(modal).show();
}

async function createTenant() {
    const name = document.getElementById('nt_name').value;
    // 임대물건명 가져오기 (select 또는 직접입력)
    let pname = '';
    const selectEl = document.getElementById('nt_pname_select');
    const directEl = document.getElementById('nt_pname_direct');
    if (selectEl) {
        if (selectEl.value === '__custom__') {
            pname = (document.getElementById('nt_pname_custom')?.value || '').trim();
        } else {
            pname = selectEl.value;
        }
    } else if (directEl) {
        pname = directEl.value.trim();
    }
    const unit = document.getElementById('nt_unit').value;
    const rent = document.getElementById('nt_rent').value;
    if (!name || !pname || !unit || !rent) { alert('필수 항목을 입력해주세요\n(이름, 임대물건명, 호수, 월세)'); return; }
    const fd = new FormData();
    fd.append('name', name);
    fd.append('phone', document.getElementById('nt_phone').value);
    fd.append('property_type', document.getElementById('nt_ptype').value);
    fd.append('property_name', pname);
    fd.append('unit_number', unit);
    fd.append('monthly_rent', rent);
    fd.append('rent_due_day', document.getElementById('nt_due').value);
    fd.append('is_recurring', document.getElementById('nt_recurring').checked);
    try {
        const res = await apiPostForm('/api/landlord/tenants', fd);
        bootstrap.Modal.getInstance(document.getElementById('formModal')).hide();
        alert(`임차인 등록 완료!\n임대물건: ${pname} ${unit}\nQR 토큰: ${res.qr_token}`);
        navigate('landlord-tenants');
    } catch (e) { alert('등록 실패: ' + e.message); }
}

async function deleteTenant(id) {
    if (!confirm('이 임차인을 비활성화하시겠습니까?')) return;
    await apiDelete(`/api/landlord/tenants/${id}`);
    navigate('landlord-tenants');
}

async function regenerateQR(tenantId) {
    if (!confirm('QR코드를 재발급하시겠습니까?\n기존 QR코드는 즉시 비활성화됩니다.')) return;
    const res = await apiPost(`/api/landlord/tenants/${tenantId}/regenerate-qr`);
    alert('QR코드가 재발급되었습니다.');
    navigate('landlord-qr');
}

async function saveLandlordProfile() {
    const fd = new FormData();
    fd.append('building_name', document.getElementById('pf_building').value);
    fd.append('address', document.getElementById('pf_address').value);
    fd.append('phone', document.getElementById('pf_phone').value);
    fd.append('business_no', document.getElementById('pf_biz').value);
    fd.append('bank_name', document.getElementById('pf_bank').value);
    fd.append('bank_account', document.getElementById('pf_account').value);
    fd.append('bank_holder', document.getElementById('pf_holder').value);
    try {
        await apiPutForm('/api/landlord/profile', fd);
        alert('프로필이 저장되었습니다');
        landlordProfileInfo = await apiGet('/api/landlord/profile');
        navigate('landlord-profile');
    } catch (e) { alert('저장 실패: ' + e.message); }
}

async function addPropertyName() {
    const input = document.getElementById('pf_new_property');
    const name = (input?.value || '').trim();
    if (!name) { alert('임대물건명을 입력해주세요'); input?.focus(); return; }
    try {
        const fd = new FormData();
        fd.append('name', name);
        await apiPostForm('/api/landlord/property-names', fd);
        navigate('landlord-profile');
    } catch(e) { alert('추가 실패: ' + e.message); }
}

async function deletePropertyName(name) {
    if (!confirm(`"${name}" 임대물건명을 삭제하시겠습니까?`)) return;
    try {
        await apiDelete('/api/landlord/property-names?name=' + encodeURIComponent(name));
        navigate('landlord-profile');
    } catch(e) { alert('삭제 실패: ' + e.message); }
}


// ─── Per-Tenant Payment History (Landlord) ────────────────

async function showTenantPaymentHistory(tenantId, tenantName, propertyInfo) {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '결제 내역: ' + tenantName;
    document.getElementById('formModalBody').innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div><p class="text-muted mt-2">결제 내역 조회 중...</p></div>';
    document.getElementById('formModalFooter').innerHTML = '<button class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>';
    new bootstrap.Modal(modal).show();

    try {
        const payments = await apiGet(`/api/landlord/payments?tenant_id=${tenantId}`);
        const total = payments.reduce((s,p) => s + (p.status === 'paid' ? p.amount : 0), 0);
        const paidCnt = payments.filter(p => p.status === 'paid').length;

        document.getElementById('formModalBody').innerHTML = `
            <div class="mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(255,107,53,.04),rgba(255,159,28,.06))">
                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <div class="fw-bold">${tenantName}</div>
                        <div class="text-muted" style="font-size:.82rem">${propertyInfo}</div>
                    </div>
                    <div class="text-end">
                        <div class="fw-bold" style="color:#ff6b35;font-size:1.1rem">${formatMoney(total)}</div>
                        <div class="text-muted" style="font-size:.78rem">결제 완료 ${paidCnt}건 / 전체 ${payments.length}건</div>
                    </div>
                </div>
            </div>
            ${payments.length === 0 ? '<div class="text-center text-muted py-4"><i class="fas fa-inbox fa-2x mb-2 d-block opacity-25"></i><p>결제 내역이 없습니다</p></div>' : `
            <div class="table-responsive">
                <table class="table table-hover table-sm mb-0">
                    <thead><tr><th>결제월</th><th>금액</th><th>방식</th><th>카드사</th><th>승인번호</th><th>상태</th><th>결제일</th></tr></thead>
                    <tbody>
                    ${payments.map(p => `
                        <tr>
                            <td><span class="badge bg-light text-dark border">${p.payment_month}</span></td>
                            <td class="fw-bold" style="color:#ff6b35">${formatMoney(p.amount)}</td>
                            <td>${p.payment_method === 'card_recurring' ? '<span class="badge bg-info">정기</span>' : '<span class="badge bg-secondary">일반</span>'}</td>
                            <td>${p.card_brand || '-'}</td>
                            <td><code style="font-size:.72rem">${p.approval_code || '-'}</code></td>
                            <td><span class="badge bg-${p.status === 'paid' ? 'success' : 'warning'}"><i class="fas fa-${p.status === 'paid' ? 'check' : 'clock'} me-1"></i>${p.status === 'paid' ? '완료' : '대기'}</span></td>
                            <td style="font-size:.78rem">${p.paid_at ? p.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
                        </tr>
                    `).join('')}
                    </tbody>
                </table>
            </div>`}`;
    } catch (e) {
        document.getElementById('formModalBody').innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${e.message}</div>`;
    }
}


// ═══════════════════════════════════════════════════════════
// ADMIN — 방긋페이 관리 PAGES (Enhanced v3)
// ═══════════════════════════════════════════════════════════

async function loadAdminLandlords(c, t) {
    t.textContent = '임대인 관리 (방긋페이)';
    const landlords = await apiGet('/api/admin/landlords');
    const totalTenants = landlords.reduce((s,l) => s + (l.tenant_count || 0), 0);
    const activeLandlords = landlords.filter(l => l.is_active).length;
    const totalRent = landlords.reduce((s,l) => s + (l.total_monthly_rent || 0), 0);

    c.innerHTML = `
    <!-- 배너 -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2d1b03 0%,#5a3408 50%,#ff9f1c 100%);">
        <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
            <div class="d-flex align-items-center gap-3">
                <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;">
                    <i class="fas fa-building text-white"></i>
                </div>
                <div>
                    <h5 class="mb-0 text-white fw-bold">방긋페이 임대인 관리</h5>
                    <small style="color:rgba(255,255,255,.65)">전체 임대인 현황 및 관리 대시보드</small>
                </div>
            </div>
            <span class="badge" style="background:rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:50px;font-size:.78rem;">
                <i class="fas fa-smile me-1" style="color:#ff9f1c"></i>Bang Good Pay
            </span>
        </div>
    </div>
    <!-- KPI -->
    <div class="row g-3 mb-4">
        ${kpiCard('전체 임대인', landlords.length + '명', 'building', 'warning')}
        ${kpiCard('활성 임대인', activeLandlords + '명', 'check-circle', 'success')}
        ${kpiCard('총 임차인', totalTenants + '명', 'users', 'info')}
        ${kpiCard('월 총 임대료', formatMoney(totalRent), 'won-sign', 'primary')}
    </div>
    <!-- 검색 -->
    <div class="card data-card mb-3">
        <div class="card-body py-2 px-3 d-flex align-items-center gap-2 flex-wrap">
            <div class="input-group input-group-sm" style="max-width:280px">
                <span class="input-group-text"><i class="fas fa-search"></i></span>
                <input type="text" class="form-control" placeholder="이름 / 건물명 / 이메일 검색" id="adminLandlordSearch" oninput="filterAdminLandlords()">
            </div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-secondary admin-ll-filter active" onclick="filterAdminLandlordStatus('all',this)">전체</button>
                <button class="btn btn-outline-success admin-ll-filter" onclick="filterAdminLandlordStatus('active',this)">활성</button>
                <button class="btn btn-outline-danger admin-ll-filter" onclick="filterAdminLandlordStatus('inactive',this)">비활성</button>
            </div>
            <span class="ms-auto text-muted" style="font-size:.78rem"><i class="fas fa-info-circle me-1"></i>총 ${landlords.length}명 등록</span>
        </div>
    </div>
    <!-- 테이블 -->
    <div class="card data-card">
        <div class="card-body p-0">
        <div class="table-responsive"><table class="table table-hover mb-0" id="adminLandlordTable">
            <thead><tr><th>이름</th><th>이메일</th><th>건물명</th><th>주소</th><th>전화번호</th><th>사업자번호</th><th>임차인</th><th>상태</th><th>등록일</th><th style="width:80px">관리</th></tr></thead>
            <tbody>
            ${landlords.length === 0 ? '<tr><td colspan="10" class="text-center text-muted py-4"><i class="fas fa-inbox me-2"></i>등록된 임대인이 없습니다</td></tr>' :
            landlords.map(l => `
                <tr data-name="${(l.name||'').toLowerCase()}" data-building="${(l.building_name||'').toLowerCase()}" data-email="${(l.email||'').toLowerCase()}" data-active="${l.is_active}">
                    <td class="fw-bold">${l.name}</td>
                    <td style="font-size:.82rem">${l.email}</td>
                    <td>${l.building_name || '<span class="text-muted">-</span>'}</td>
                    <td style="font-size:.8rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${l.address || ''}">${l.address || '-'}</td>
                    <td>${l.phone || '-'}</td>
                    <td style="font-size:.82rem">${l.business_no || '-'}</td>
                    <td><span class="badge bg-info fw-bold">${l.tenant_count || 0}명</span></td>
                    <td>${l.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-danger">비활성</span>'}</td>
                    <td style="font-size:.78rem">${l.created_at ? l.created_at.slice(0,10) : '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-dark" title="상세보기" onclick="showAdminLandlordDetail(${JSON.stringify(l).replace(/"/g,'&quot;')})"><i class="fas fa-eye"></i></button>
                    </td>
                </tr>
            `).join('')}
            </tbody>
        </table></div>
    </div></div>`;
}

function filterAdminLandlords() {
    const q = (document.getElementById('adminLandlordSearch').value || '').toLowerCase();
    document.querySelectorAll('#adminLandlordTable tbody tr').forEach(row => {
        if (!row.dataset.name) return;
        const match = row.dataset.name.includes(q) || row.dataset.building.includes(q) || row.dataset.email.includes(q);
        row.style.display = match ? '' : 'none';
    });
}
function filterAdminLandlordStatus(status, btn) {
    document.querySelectorAll('.admin-ll-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#adminLandlordTable tbody tr').forEach(row => {
        if (!row.dataset.active) return;
        if (status === 'all') { row.style.display = ''; return; }
        row.style.display = (status === 'active' && row.dataset.active === 'true') || (status === 'inactive' && row.dataset.active === 'false') ? '' : 'none';
    });
}
function showAdminLandlordDetail(l) {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '임대인 상세: ' + l.name;
    document.getElementById('formModalBody').innerHTML = `
        <div class="row g-3">
            <div class="col-md-6">
                <h6 class="fw-bold mb-3"><i class="fas fa-user me-2" style="color:#ff9f1c"></i>기본 정보</h6>
                <ul class="list-unstyled mb-0">
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이름</span><strong>${l.name}</strong></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">이메일</span><strong>${l.email}</strong></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">전화번호</span><strong>${l.phone || '-'}</strong></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">사업자번호</span><strong>${l.business_no || '-'}</strong></li>
                    <li class="d-flex justify-content-between"><span class="text-muted">등록일</span><strong>${l.created_at ? l.created_at.slice(0,10) : '-'}</strong></li>
                </ul>
            </div>
            <div class="col-md-6">
                <h6 class="fw-bold mb-3"><i class="fas fa-building me-2" style="color:#ff9f1c"></i>건물 정보</h6>
                <ul class="list-unstyled mb-0">
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">건물명</span><strong>${l.building_name || '-'}</strong></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">주소</span><strong style="font-size:.82rem;text-align:right;max-width:180px">${l.address || '-'}</strong></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">임차인 수</span><span class="badge bg-info">${l.tenant_count || 0}명</span></li>
                    <li class="mb-2 d-flex justify-content-between border-bottom pb-2"><span class="text-muted">월 총 임대료</span><strong style="color:#ff6b35">${formatMoney(l.total_monthly_rent || 0)}</strong></li>
                    <li class="d-flex justify-content-between"><span class="text-muted">상태</span>${l.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-danger">비활성</span>'}</li>
                </ul>
            </div>
        </div>
        <hr>
        <h6 class="fw-bold mb-3"><i class="fas fa-users me-2 text-info"></i>소속 임차인 목록</h6>
        <div id="landlordTenantsListArea"><div class="text-center py-3"><div class="spinner-border spinner-border-sm text-warning"></div></div></div>`;
    document.getElementById('formModalFooter').innerHTML = `<button class="btn btn-outline-secondary" data-bs-dismiss="modal">닫기</button>`;
    new bootstrap.Modal(modal).show();

    // 임차인 목록 비동기 로드
    loadLandlordTenantsForAdmin(l.id);
}

async function loadLandlordTenantsForAdmin(landlordId) {
    const area = document.getElementById('landlordTenantsListArea');
    try {
        const data = await apiGet(`/api/admin/banggut/landlord/${landlordId}/tenants`);
        const tenants = data.tenants || [];
        if (tenants.length === 0) {
            area.innerHTML = '<div class="text-center text-muted py-3"><i class="fas fa-inbox me-2"></i>등록된 임차인이 없습니다</div>';
            return;
        }
        area.innerHTML = `
        <div class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead class="table-light"><tr><th></th><th>이름</th><th>물건</th><th>호수</th><th>월세</th><th>이번달</th><th>총납부</th><th>관리</th></tr></thead>
                <tbody>
                ${tenants.map(tn => `
                    <tr>
                        <td>${PROP_EMOJI[tn.property_type] || '📋'}</td>
                        <td class="fw-bold">${tn.name} ${!tn.is_active ? '<span class="badge bg-secondary">비활성</span>' : ''}</td>
                        <td><span class="badge bg-secondary" style="font-size:.68rem">${tn.property_type_kr}</span> ${tn.property_name}</td>
                        <td class="fw-bold">${tn.unit_number}</td>
                        <td class="fw-bold" style="color:#ff6b35">${formatMoney(tn.monthly_rent)}</td>
                        <td>${tn.paid_this_month ? '<span class="badge bg-success">완료</span>' : '<span class="badge bg-warning text-dark">미납</span>'}</td>
                        <td style="font-size:.82rem">${formatMoney(tn.total_paid)} (${tn.pay_count}건)</td>
                        <td><button class="btn btn-sm btn-outline-info" onclick="showAdminTenantPayments(${tn.id},'${tn.name.replace(/'/g,"\\'")}','${tn.property_name.replace(/'/g,"\\'")} ${tn.unit_number}')" title="결제내역"><i class="fas fa-credit-card"></i></button></td>
                    </tr>
                `).join('')}
                </tbody>
            </table>
        </div>`;
    } catch (e) {
        area.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
}

async function showAdminTenantPayments(tenantId, tenantName, propertyInfo) {
    // 모달 안에 새 모달 대신 formModalBody를 교체
    const area = document.getElementById('landlordTenantsListArea');
    if (!area) return;
    area.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-info"></div></div>';
    try {
        const data = await apiGet(`/api/admin/banggut/tenant/${tenantId}/payments`);
        const payments = data.payments || [];
        const total = payments.reduce((s,p) => s + (p.status === 'paid' ? p.amount : 0), 0);
        area.innerHTML = `
        <div class="mb-2 d-flex justify-content-between align-items-center">
            <div>
                <button class="btn btn-sm btn-outline-secondary me-2" onclick="loadLandlordTenantsForAdmin(${data.tenant.landlord_name ? 'undefined' : 'undefined'})"><i class="fas fa-arrow-left me-1"></i>목록</button>
                <strong>${tenantName}</strong> <span class="text-muted">(${propertyInfo})</span>
            </div>
            <span class="fw-bold" style="color:#ff6b35">${formatMoney(total)} / ${payments.length}건</span>
        </div>
        ${payments.length === 0 ? '<div class="text-center text-muted py-3"><i class="fas fa-inbox me-2"></i>결제 내역이 없습니다</div>' : `
        <div class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead class="table-light"><tr><th>결제월</th><th>금액</th><th>방식</th><th>카드사</th><th>승인번호</th><th>상태</th><th>결제일</th></tr></thead>
                <tbody>
                ${payments.map(p => `
                    <tr>
                        <td><span class="badge bg-light text-dark border">${p.payment_month}</span></td>
                        <td class="fw-bold" style="color:#ff6b35">${formatMoney(p.amount)}</td>
                        <td>${p.payment_method === 'card_recurring' ? '<span class="badge bg-info">정기</span>' : '<span class="badge bg-secondary">일반</span>'}</td>
                        <td>${p.card_brand || '-'}</td>
                        <td><code style="font-size:.72rem">${p.approval_code || '-'}</code></td>
                        <td><span class="badge bg-${p.status === 'paid' ? 'success' : 'warning'}">${p.status === 'paid' ? '완료' : '대기'}</span></td>
                        <td style="font-size:.78rem">${p.paid_at ? p.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
                    </tr>
                `).join('')}
                </tbody>
            </table>
        </div>`}`;
    } catch (e) {
        area.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
}

async function loadAdminTenants(c, t) {
    t.textContent = '임차인 현황 (방긋페이)';
    const tenants = await apiGet('/api/admin/banggut/tenants');
    const activeTenants = tenants.filter(t => t.is_active);
    const paidCnt = activeTenants.filter(t => t.paid_this_month).length;
    const unpaidCnt = activeTenants.length - paidCnt;
    const totalRent = activeTenants.reduce((s,t) => s + t.monthly_rent, 0);
    const paidRate = activeTenants.length > 0 ? Math.round(paidCnt / activeTenants.length * 100) : 0;

    // 물건유형별 통계
    const typeStats = {};
    activeTenants.forEach(t => { typeStats[t.property_type_kr] = (typeStats[t.property_type_kr] || 0) + 1; });

    // 임대인별 그룹핑
    const landlordGroups = {};
    tenants.forEach(t => {
        if (!landlordGroups[t.landlord_name]) landlordGroups[t.landlord_name] = { total: 0, paid: 0, rent: 0 };
        landlordGroups[t.landlord_name].total++;
        if (t.paid_this_month) landlordGroups[t.landlord_name].paid++;
        if (t.is_active) landlordGroups[t.landlord_name].rent += t.monthly_rent;
    });

    c.innerHTML = `
    <div class="row g-3 mb-4">
        ${kpiCard('전체 임차인', tenants.length + '명', 'users', 'warning')}
        ${kpiCard('이번달 납부', paidCnt + '/' + activeTenants.length + '명', 'check-circle', 'success')}
        ${kpiCard('수금률', paidRate + '%', 'percentage', paidRate >= 80 ? 'success' : paidRate >= 50 ? 'warning' : 'danger')}
        ${kpiCard('월 총 임대료', formatMoney(totalRent), 'won-sign', 'info')}
    </div>
    <!-- 물건유형 분포 + 임대인별 현황 -->
    <div class="row g-3 mb-4">
        <div class="col-md-5">
            <div class="card data-card h-100">
                <div class="card-header py-2"><h6 class="mb-0"><i class="fas fa-chart-pie me-2 text-warning"></i>물건유형 분포</h6></div>
                <div class="card-body d-flex flex-wrap gap-2 align-items-center justify-content-center py-3">
                    ${Object.entries(typeStats).map(([type, cnt]) => `
                        <div class="text-center px-3 py-2" style="background:rgba(255,159,28,.06);border-radius:12px;min-width:90px">
                            <div style="font-size:1.5rem">${type === '아파트' ? '🏢' : type === '오피스텔' ? '🏠' : type === '상가' ? '🏪' : type === '빌라' ? '🏘️' : '📋'}</div>
                            <div class="fw-bold" style="font-size:.82rem">${type}</div>
                            <div class="fw-bold" style="color:#ff9f1c;font-size:1.1rem">${cnt}명</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
        <div class="col-md-7">
            <div class="card data-card h-100">
                <div class="card-header py-2"><h6 class="mb-0"><i class="fas fa-building me-2 text-info"></i>임대인별 현황</h6></div>
                <div class="card-body p-0">
                    <div class="table-responsive"><table class="table table-sm table-hover mb-0">
                        <thead class="table-light"><tr><th>임대인</th><th>전체</th><th>납부</th><th>수금률</th><th>월 임대료</th></tr></thead>
                        <tbody>
                        ${Object.entries(landlordGroups).map(([name, g]) => {
                            const rate = g.total > 0 ? Math.round(g.paid / g.total * 100) : 0;
                            return `<tr>
                                <td class="fw-bold">${name}</td>
                                <td>${g.total}명</td>
                                <td>${g.paid}명</td>
                                <td><div class="progress" style="height:6px;width:60px;display:inline-block;vertical-align:middle"><div class="progress-bar bg-${rate>=80?'success':rate>=50?'warning':'danger'}" style="width:${rate}%"></div></div> <span class="ms-1" style="font-size:.78rem">${rate}%</span></td>
                                <td style="color:#ff6b35;font-size:.85rem">${formatMoney(g.rent)}</td>
                            </tr>`;
                        }).join('')}
                        </tbody>
                    </table></div>
                </div>
            </div>
        </div>
    </div>
    <!-- 검색/필터 -->
    <div class="card data-card mb-3">
        <div class="card-body py-2 px-3 d-flex align-items-center gap-2 flex-wrap">
            <div class="input-group input-group-sm" style="max-width:250px">
                <span class="input-group-text"><i class="fas fa-search"></i></span>
                <input type="text" class="form-control" placeholder="임차인 / 임대인 검색" id="adminTenantSearch" oninput="filterAdminTenantTable()">
            </div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-secondary admin-tenant-filter active" onclick="filterAdminTenantStatus('all',this)">전체</button>
                <button class="btn btn-outline-success admin-tenant-filter" onclick="filterAdminTenantStatus('paid',this)">납부</button>
                <button class="btn btn-outline-warning admin-tenant-filter" onclick="filterAdminTenantStatus('unpaid',this)">미납</button>
            </div>
        </div>
    </div>
    <!-- 테이블 -->
    <div class="card data-card">
        <div class="card-body p-0">
        <div class="table-responsive"><table class="table table-hover mb-0" id="adminTenantTable">
            <thead><tr><th></th><th>임대인</th><th>임차인</th><th>물건</th><th>호수</th><th>월세</th><th>납부일</th><th>결제방식</th><th>이번달</th><th>상태</th><th>결제</th></tr></thead>
            <tbody>
            ${tenants.length === 0 ? '<tr><td colspan="11" class="text-center text-muted py-4"><i class="fas fa-inbox me-2"></i>등록된 임차인이 없습니다</td></tr>' :
            tenants.map(tn => `
                <tr data-name="${(tn.name||'').toLowerCase()}" data-landlord="${(tn.landlord_name||'').toLowerCase()}" data-paid="${tn.paid_this_month}" data-active="${tn.is_active}" ${!tn.is_active ? 'class="table-secondary"' : ''}>
                    <td>${PROP_EMOJI[tn.property_type] || '📋'}</td>
                    <td><span class="text-primary" style="cursor:pointer;text-decoration:underline" onclick="showAdminTenantPaymentsModal(${tn.id},'${(tn.name||'').replace(/'/g,"\\'")}','${(tn.property_name||'').replace(/'/g,"\\'")} ${tn.unit_number}','${(tn.landlord_name||'').replace(/'/g,"\\'")}')">${tn.landlord_name}</span></td>
                    <td class="fw-bold">${tn.name}</td>
                    <td><span class="badge bg-secondary" style="font-size:.68rem">${tn.property_type_kr}</span> ${tn.property_name}</td>
                    <td class="fw-bold">${tn.unit_number}</td>
                    <td class="fw-bold" style="color:#ff6b35">${formatMoney(tn.monthly_rent)}</td>
                    <td>매월 ${tn.rent_due_day}일</td>
                    <td>${tn.is_recurring ? '<span class="badge bg-info"><i class="fas fa-sync-alt me-1"></i>정기</span>' : '<span class="badge border text-muted">일반</span>'}</td>
                    <td>${tn.paid_this_month ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>완료</span>' : '<span class="badge bg-warning text-dark"><i class="fas fa-clock me-1"></i>미납</span>'}</td>
                    <td>${tn.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
                    <td><button class="btn btn-sm btn-outline-info" onclick="showAdminTenantPaymentsModal(${tn.id},'${(tn.name||'').replace(/'/g,"\\'")}','${(tn.property_name||'').replace(/'/g,"\\'")} ${tn.unit_number}','${(tn.landlord_name||'').replace(/'/g,"\\'")}')" title="결제내역"><i class="fas fa-credit-card"></i></button></td>
                </tr>
            `).join('')}
            </tbody>
        </table></div>
    </div></div>`;
}

// 관리자용 임차인별 결제내역 모달
async function showAdminTenantPaymentsModal(tenantId, tenantName, propertyInfo, landlordName) {
    const modal = document.getElementById('formModal');
    document.getElementById('formModalTitle').textContent = '결제 내역: ' + tenantName;
    document.getElementById('formModalBody').innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    document.getElementById('formModalFooter').innerHTML = '<button class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>';
    new bootstrap.Modal(modal).show();

    try {
        const data = await apiGet(`/api/admin/banggut/tenant/${tenantId}/payments`);
        const payments = data.payments || [];
        const total = payments.reduce((s,p) => s + (p.status === 'paid' ? p.amount : 0), 0);

        document.getElementById('formModalBody').innerHTML = `
            <div class="mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(255,107,53,.04),rgba(255,159,28,.06))">
                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <div class="fw-bold">${tenantName} <span class="text-muted fw-normal" style="font-size:.82rem">(${propertyInfo})</span></div>
                        <div class="text-muted" style="font-size:.82rem">임대인: <strong>${landlordName}</strong> · 월세: <strong style="color:#ff6b35">${formatMoney(data.tenant.monthly_rent)}</strong></div>
                    </div>
                    <div class="text-end">
                        <div class="fw-bold" style="color:#ff6b35;font-size:1.1rem">${formatMoney(total)}</div>
                        <div class="text-muted" style="font-size:.78rem">완료 ${payments.filter(p=>p.status==='paid').length}건 / 전체 ${payments.length}건</div>
                    </div>
                </div>
            </div>
            ${payments.length === 0 ? '<div class="text-center text-muted py-4"><i class="fas fa-inbox fa-2x mb-2 d-block opacity-25"></i><p>결제 내역이 없습니다</p></div>' : `
            <div class="table-responsive">
                <table class="table table-hover table-sm mb-0">
                    <thead><tr><th>결제월</th><th>금액</th><th>방식</th><th>카드사</th><th>승인번호</th><th>상태</th><th>결제일</th></tr></thead>
                    <tbody>
                    ${payments.map(p => `
                        <tr>
                            <td><span class="badge bg-light text-dark border">${p.payment_month}</span></td>
                            <td class="fw-bold" style="color:#ff6b35">${formatMoney(p.amount)}</td>
                            <td>${p.payment_method === 'card_recurring' ? '<span class="badge bg-info">정기</span>' : '<span class="badge bg-secondary">일반</span>'}</td>
                            <td>${p.card_brand || '-'}</td>
                            <td><code style="font-size:.72rem">${p.approval_code || '-'}</code></td>
                            <td><span class="badge bg-${p.status === 'paid' ? 'success' : 'warning'}">${p.status === 'paid' ? '완료' : '대기'}</span></td>
                            <td style="font-size:.78rem">${p.paid_at ? p.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
                        </tr>
                    `).join('')}
                    </tbody>
                </table>
            </div>`}`;
    } catch (e) {
        document.getElementById('formModalBody').innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
}

function filterAdminTenantTable() {
    const q = (document.getElementById('adminTenantSearch').value || '').toLowerCase();
    document.querySelectorAll('#adminTenantTable tbody tr').forEach(row => {
        if (!row.dataset.name) return;
        row.style.display = (row.dataset.name.includes(q) || row.dataset.landlord.includes(q)) ? '' : 'none';
    });
}
function filterAdminTenantStatus(status, btn) {
    document.querySelectorAll('.admin-tenant-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#adminTenantTable tbody tr').forEach(row => {
        if (status === 'all') { row.style.display = ''; return; }
        const paid = row.dataset.paid === 'true';
        row.style.display = (status === 'paid' && paid) || (status === 'unpaid' && !paid) ? '' : 'none';
    });
}

async function loadAdminRentPayments(c, t) {
    t.textContent = '월세 결제 내역 (방긋페이)';
    
    // Load initial data + landlords for filter + available months
    const [payments, landlords, months] = await Promise.all([
        apiGet('/api/admin/banggut/payments'),
        apiGet('/api/admin/landlords').catch(() => []),
        apiGet('/api/admin/banggut/payment-months').catch(() => []),
    ]);
    
    const total = payments.reduce((s,p) => s + (p.status === 'paid' ? p.amount : 0), 0);
    const paidCnt = payments.filter(p => p.status === 'paid').length;
    const pendingCnt = payments.filter(p => p.status === 'pending').length;

    // 월별 수금 그룹핑
    const monthlyData = {};
    payments.filter(p => p.status === 'paid').forEach(p => {
        const m = p.payment_month || 'N/A';
        monthlyData[m] = (monthlyData[m] || 0) + p.amount;
    });
    const sortedMonths = Object.keys(monthlyData).sort().slice(-6);

    // Landlord options
    const landlordOpts = '<option value="">전체 임대인</option>' + landlords.map(l => `<option value="${l.id}">${l.name} (${l.building_name || '-'})</option>`).join('');
    // Month options  
    const monthOpts = '<option value="">전체 월</option>' + months.map(m => `<option value="${m}">${m}</option>`).join('');

    c.innerHTML = `
    <div class="row g-3 mb-4">
        ${kpiCard('전체 결제', payments.length + '건', 'receipt', 'primary')}
        ${kpiCard('결제 완료', paidCnt + '건', 'check-circle', 'success')}
        ${kpiCard('총 수금액', formatMoney(total), 'won-sign', 'warning')}
        ${kpiCard('대기/미납', pendingCnt + '건', 'clock', 'danger')}
    </div>
    <!-- 월별 차트 -->
    <div class="row g-3 mb-4">
        <div class="col-md-8">
            <div class="card data-card h-100">
                <div class="card-header py-2"><h6 class="mb-0"><i class="fas fa-chart-bar me-2 text-warning"></i>월별 수금 추이</h6></div>
                <div class="card-body" style="height:240px"><canvas id="adminRentChart"></canvas></div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card data-card h-100">
                <div class="card-header py-2"><h6 class="mb-0"><i class="fas fa-list-ol me-2 text-info"></i>월별 상세</h6></div>
                <div class="card-body p-0">
                    <div class="list-group list-group-flush">
                    ${sortedMonths.map(m => `
                        <div class="list-group-item d-flex justify-content-between px-3 py-2">
                            <span style="font-size:.85rem">${m}</span>
                            <strong style="color:#ff6b35;font-size:.85rem">${formatMoney(monthlyData[m])}</strong>
                        </div>
                    `).join('') || '<div class="p-3 text-muted text-center">데이터 없음</div>'}
                    </div>
                </div>
            </div>
        </div>
    </div>
    <!-- 월별 납부상태 조회 -->
    <div class="card data-card mb-3">
        <div class="card-header py-2"><h6 class="mb-0"><i class="fas fa-calendar-check me-2 text-success"></i>월별 납부 상태 조회</h6></div>
        <div class="card-body">
            <div class="row g-2 align-items-end">
                <div class="col-md-3"><label class="form-label small mb-1">조회 월</label><input type="month" class="form-control form-control-sm" id="rentStatusMonth" value="${new Date().toISOString().slice(0,7)}"></div>
                <div class="col-md-3"><label class="form-label small mb-1">임대인 필터</label><select class="form-select form-select-sm" id="rentStatusLandlord"><option value="">전체 임대인</option>${landlords.map(l=>`<option value="${l.id}">${l.name}</option>`).join('')}</select></div>
                <div class="col-md-2"><button class="btn btn-sm btn-success w-100" onclick="loadMonthlyPaymentStatus()"><i class="fas fa-search me-1"></i>납부상태 조회</button></div>
            </div>
            <div id="monthlyStatusResult" class="mt-3"></div>
        </div>
    </div>
    <!-- 필터 + 검색 -->
    <div class="card data-card mb-3">
        <div class="card-body py-2 px-3 d-flex align-items-center gap-2 flex-wrap">
            <select class="form-select form-select-sm" style="max-width:200px" id="rentFilterLandlord" onchange="reloadRentPayments()">${landlordOpts}</select>
            <select class="form-select form-select-sm" style="max-width:150px" id="rentFilterMonth" onchange="reloadRentPayments()">${monthOpts}</select>
            <div class="input-group input-group-sm" style="max-width:220px">
                <span class="input-group-text"><i class="fas fa-search"></i></span>
                <input type="text" class="form-control" placeholder="임대인 / 임차인 검색" id="rentSearchInput" oninput="filterRentTable()">
            </div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-secondary active rent-status-filter" onclick="filterRentStatus('all',this)">전체</button>
                <button class="btn btn-outline-success rent-status-filter" onclick="filterRentStatus('paid',this)">완료</button>
                <button class="btn btn-outline-warning rent-status-filter" onclick="filterRentStatus('pending',this)">대기</button>
            </div>
            <span class="ms-auto text-muted" style="font-size:.78rem" id="rentPaymentCount">${payments.length}건</span>
        </div>
    </div>
    <!-- 테이블 -->
    <div class="card data-card">
        <div class="card-body p-0" id="rentPaymentTableBody"></div>
    </div>`;
    
    renderRentPaymentTable(payments);

    // 월별 차트
    setTimeout(() => {
        const ctx = document.getElementById('adminRentChart');
        if (ctx && typeof Chart !== 'undefined' && sortedMonths.length > 0) {
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: sortedMonths,
                    datasets: [{label:'수금액', data: sortedMonths.map(m => monthlyData[m] || 0), backgroundColor:'rgba(255,159,28,.5)', borderColor:'#ff9f1c', borderWidth:1, borderRadius:6}]
                },
                options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true,ticks:{callback:v=>v>=10000?(v/10000)+'만':v.toLocaleString()}},x:{grid:{display:false}}} }
            });
        }
    }, 100);
}

function renderRentPaymentTable(payments) {
    const el = document.getElementById('rentPaymentTableBody');
    if (!el) return;
    el.innerHTML = `
    <div class="table-responsive"><table class="table table-hover mb-0" id="adminPayTable">
        <thead><tr><th>임대인</th><th>임차인</th><th>물건 정보</th><th>금액</th><th>결제월</th><th>방식</th><th>카드사</th><th>승인번호</th><th>상태</th><th>결제일</th></tr></thead>
        <tbody>
        ${payments.length === 0 ? '<tr><td colspan="10" class="text-center text-muted py-4"><i class="fas fa-inbox me-2"></i>결제 내역이 없습니다</td></tr>' :
        payments.map(p => `
            <tr data-name="${(p.tenant_name||'').toLowerCase()}" data-landlord="${(p.landlord_name||'').toLowerCase()}" data-status="${p.status}">
                <td>${p.landlord_name}</td>
                <td class="fw-bold">${p.tenant_name}</td>
                <td style="font-size:.82rem">${p.property_info}</td>
                <td class="fw-bold" style="color:#ff6b35">${formatMoney(p.amount)}</td>
                <td><span class="badge bg-light text-dark border">${p.payment_month}</span></td>
                <td>${p.payment_method === 'card_recurring' ? '<span class="badge bg-info">정기</span>' : '<span class="badge bg-secondary">일반</span>'}</td>
                <td>${p.card_brand || '-'}</td>
                <td><code style="font-size:.72rem">${p.approval_code || '-'}</code></td>
                <td><span class="badge bg-${p.status === 'paid' ? 'success' : 'warning'}"><i class="fas fa-${p.status === 'paid' ? 'check' : 'clock'} me-1"></i>${p.status === 'paid' ? '완료' : '대기'}</span></td>
                <td style="font-size:.78rem">${p.paid_at ? p.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
            </tr>
        `).join('')}
        </tbody>
    </table></div>`;
}

async function reloadRentPayments() {
    const landlordId = document.getElementById('rentFilterLandlord')?.value || '';
    const month = document.getElementById('rentFilterMonth')?.value || '';
    let url = '/api/admin/banggut/payments?';
    if (landlordId) url += `landlord_id=${landlordId}&`;
    if (month) url += `month=${month}&`;
    try {
        const payments = await apiGet(url);
        document.getElementById('rentPaymentCount').textContent = payments.length + '건';
        renderRentPaymentTable(payments);
    } catch(e) { console.error(e); }
}

function filterRentTable() {
    const q = (document.getElementById('rentSearchInput')?.value || '').toLowerCase();
    document.querySelectorAll('#adminPayTable tbody tr[data-name]').forEach(r => {
        r.style.display = (r.dataset.name.includes(q) || r.dataset.landlord.includes(q)) ? '' : 'none';
    });
}

function filterRentStatus(status, btn) {
    document.querySelectorAll('.rent-status-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#adminPayTable tbody tr[data-status]').forEach(r => {
        r.style.display = (status === 'all' || r.dataset.status === status) ? '' : 'none';
    });
}

async function loadMonthlyPaymentStatus() {
    const month = document.getElementById('rentStatusMonth')?.value;
    const landlordId = document.getElementById('rentStatusLandlord')?.value || '';
    if (!month) { alert('조회할 월을 선택하세요'); return; }
    
    const el = document.getElementById('monthlyStatusResult');
    el.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-success"></div></div>';
    
    try {
        const data = await apiGet(`/api/admin/banggut/monthly-status?month=${month}`);
        const filtered = landlordId ? data.filter(d => d.landlord_user_id == landlordId) : data;
        const paid = filtered.filter(d => d.status === 'paid').length;
        const unpaid = filtered.filter(d => d.status === 'unpaid').length;
        
        el.innerHTML = `
        <div class="mb-2 d-flex gap-3">
            <span class="badge bg-success px-3 py-2">납부 ${paid}명</span>
            <span class="badge bg-danger px-3 py-2">미납 ${unpaid}명</span>
            <span class="badge bg-secondary px-3 py-2">전체 ${filtered.length}명</span>
        </div>
        <div class="table-responsive" style="max-height:300px;overflow-y:auto">
            <table class="table table-sm table-hover mb-0">
                <thead class="table-light sticky-top"><tr><th>임대인</th><th>임차인</th><th>물건</th><th>월세</th><th>납부상태</th><th>납부액</th><th>납부일</th></tr></thead>
                <tbody>
                ${filtered.map(d => `
                    <tr>
                        <td>${d.landlord_name}</td>
                        <td class="fw-bold">${d.tenant_name}</td>
                        <td style="font-size:.82rem">${d.property_info}</td>
                        <td style="color:#ff6b35">${formatMoney(d.monthly_rent)}</td>
                        <td><span class="badge bg-${d.status==='paid'?'success':d.status==='unpaid'?'danger':'warning'}">${d.status==='paid'?'납부':d.status==='unpaid'?'미납':'대기'}</span></td>
                        <td>${d.paid_amount > 0 ? formatMoney(d.paid_amount) : '-'}</td>
                        <td style="font-size:.78rem">${d.paid_at ? d.paid_at.slice(0,16).replace('T',' ') : '-'}</td>
                    </tr>
                `).join('')}
                </tbody>
            </table>
        </div>`;
    } catch(e) { el.innerHTML = `<div class="alert alert-danger">${e.message}</div>`; }
}

async function loadAdminPGLandlord(c, t) {
    t.textContent = 'PG 설정 — 소상공인 / 임대인 분리';
    
    // Load landlords list
    let landlords = [];
    try { landlords = await apiGet('/api/admin/landlords'); } catch(e) {}
    const landlordOpts = landlords.map(l => `<option value="${l.id}">${l.name} (${l.building_name || '건물명 미등록'})</option>`).join('');
    
    c.innerHTML = `
    <div class="alert border-0 mb-4" style="background:linear-gradient(135deg,rgba(14,165,233,.06),rgba(255,159,28,.06));border-radius:14px">
        <i class="fas fa-info-circle me-2 text-info"></i>
        소상공인(ADPAY)과 임대인(방긋페이)의 PG 키값은 <strong>별도로 관리</strong>됩니다. 먼저 임대인을 선택한 후 PG사를 설정하세요.
    </div>
    <div class="row g-3">
        <div class="col-md-6">
            <div class="card data-card h-100">
                <div class="card-header" style="background:linear-gradient(135deg,rgba(255,107,53,.04),rgba(255,159,28,.06))">
                    <h5 class="mb-0"><i class="fas fa-building me-2" style="color:#ff9f1c"></i>방긋페이 PG (임대인)</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3" style="font-size:.88rem">임대인 월세 결제 전용 PG 키값을 등록합니다.</p>
                    <form>
                        <div class="mb-3">
                            <label class="form-label fw-bold small"><i class="fas fa-user-tie me-1 text-warning"></i>임대인 선택 <span class="text-danger">*</span></label>
                            <select class="form-select" id="landlordSelect" onchange="onLandlordSelect()">
                                <option value="">-- 임대인을 먼저 선택하세요 --</option>
                                ${landlordOpts}
                            </select>
                            <div class="form-text" id="landlordSelectInfo"></div>
                        </div>
                        <div id="pgFormSection" style="display:none">
                            <div class="mb-3"><label class="form-label fw-bold small">PG사 선택</label><select class="form-select" id="landlordPgProvider"><option>선택하세요</option></select></div>
                            <div class="mb-3"><label class="form-label fw-bold small">MID (상점ID)</label><input type="text" class="form-control" id="landlordPgMid" placeholder="MID-LANDLORD-001"></div>
                            <div class="mb-3"><label class="form-label fw-bold small">SECRET KEY</label>
                                <div class="input-group">
                                    <input type="password" class="form-control" id="landlordPgSecret" placeholder="암호화되어 보관됩니다">
                                    <button type="button" class="btn btn-outline-secondary" onclick="const i=document.getElementById('landlordPgSecret');i.type=i.type==='password'?'text':'password'"><i class="fas fa-eye"></i></button>
                                </div>
                            </div>
                            <div class="mb-3"><label class="form-label fw-bold small">메모</label><input type="text" class="form-control" id="landlordPgMemo" placeholder="예: 방긋페이 실서비스용"></div>
                            <button type="button" class="btn text-white w-100" style="background:linear-gradient(135deg,#ff6b35,#ff9f1c);border:none;border-radius:8px" onclick="saveLandlordPG()"><i class="fas fa-save me-2"></i>방긋페이 PG 저장</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card data-card h-100">
                <div class="card-header" style="background:linear-gradient(135deg,rgba(14,165,233,.04),rgba(27,58,92,.06))">
                    <h5 class="mb-0"><i class="fas fa-store me-2" style="color:#0ea5e9"></i>ADPAY PG (소상공인)</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3" style="font-size:.88rem">소상공인 결제 전용 PG 키값은 별도 메뉴에서 관리합니다.</p>
                    <div class="alert alert-light border mb-3" style="border-radius:10px">
                        <div class="d-flex align-items-center gap-2">
                            <i class="fas fa-network-wired text-primary"></i>
                            <div>
                                <strong>ADPAY PG 설정</strong><br>
                                <a href="#" onclick="navigate('admin-pg')" class="small">PG 설정 페이지 바로가기 →</a>
                            </div>
                        </div>
                    </div>
                    <div class="text-center text-muted py-3">
                        <i class="fas fa-shield-alt fa-2x mb-2 d-block" style="color:#0ea5e9;opacity:.4"></i>
                        <span style="font-size:.82rem">소상공인 PG는 가맹점별로<br>개별 관리됩니다</span>
                    </div>
                </div>
            </div>
        </div>
    </div>`;
    try {
        const providers = await apiGet('/api/admin/pg-providers');
        const sel = document.getElementById('landlordPgProvider');
        if (sel && providers) {
            providers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                sel.appendChild(opt);
            });
        }
    } catch(e) {}
}

function onLandlordSelect() {
    const sel = document.getElementById('landlordSelect');
    const infoEl = document.getElementById('landlordSelectInfo');
    const formEl = document.getElementById('pgFormSection');
    if (sel.value) {
        const name = sel.options[sel.selectedIndex].text;
        infoEl.innerHTML = `<i class="fas fa-check-circle text-success me-1"></i> <strong>${name}</strong> 선택됨`;
        formEl.style.display = '';
    } else {
        infoEl.innerHTML = '';
        formEl.style.display = 'none';
    }
}

function saveLandlordPG() {
    const landlordId = document.getElementById('landlordSelect').value;
    if (!landlordId) { alert('임대인을 먼저 선택해주세요'); return; }
    const pgProvider = document.getElementById('landlordPgProvider').value;
    if (!pgProvider || pgProvider === '선택하세요') { alert('PG사를 선택해주세요'); return; }
    const mid = document.getElementById('landlordPgMid').value;
    if (!mid) { alert('MID를 입력해주세요'); return; }
    alert(`PG 등록이 완료되었습니다 (데모)\n임대인 ID: ${landlordId}\nPG사: ${pgProvider}\nMID: ${mid}`);
}

// ═══════════════════════════════════════════════════════════
// 방긋페이 영업관리자 관리 (Admin - Task 7)
// ═══════════════════════════════════════════════════════════

async function loadAdminBanggutSales(c, t) {
    t.textContent = '방긋페이 영업관리자';
    
    const [salesManagers, landlords, assigns] = await Promise.all([
        apiGet('/api/admin/sales-managers'),
        apiGet('/api/admin/landlords').catch(() => []),
        apiGet('/api/admin/sales-assignments'),
    ]);
    
    // 영업관리자별 커미션 현황 계산
    const assignMap = {};
    assigns.forEach(a => {
        if (!assignMap[a.sales_manager_user_id]) assignMap[a.sales_manager_user_id] = [];
        assignMap[a.sales_manager_user_id].push(a);
    });
    
    const totalManagers = salesManagers.length;
    const activeManagers = salesManagers.filter(s => s.is_active).length;
    const totalAssigned = assigns.filter(a => a.is_active).length;
    
    const landlordOpts = landlords.map(l => `<option value="${l.id}">${l.name} (${l.building_name || '-'})</option>`).join('');
    const salesOpts = salesManagers.map(s => `<option value="${s.id}">${s.name} (${s.email})</option>`).join('');
    
    c.innerHTML = `
    <!-- 배너 -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2d1b03 0%,#5a3408 50%,#ff9f1c 100%);">
        <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
            <div class="d-flex align-items-center gap-3">
                <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;">
                    <i class="fas fa-user-tie text-white"></i>
                </div>
                <div>
                    <h5 class="mb-0 text-white fw-bold">방긋페이 영업관리자</h5>
                    <small style="color:rgba(255,255,255,.65)">임대인 유치 영업관리자 및 수수료 관리</small>
                </div>
            </div>
            <span class="badge" style="background:rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:50px;font-size:.78rem;">
                <i class="fas fa-smile me-1" style="color:#ff9f1c"></i>Bang Good Pay
            </span>
        </div>
    </div>
    
    <!-- KPI -->
    <div class="row g-3 mb-4">
        ${kpiCard('전체 영업관리자', totalManagers + '명', 'user-tie', 'info')}
        ${kpiCard('활성 관리자', activeManagers + '명', 'check-circle', 'success')}
        ${kpiCard('배정 가맹점', totalAssigned + '건', 'handshake', 'primary')}
        ${kpiCard('임대인 수', landlords.length + '명', 'building', 'warning')}
    </div>
    
    <!-- 안내 -->
    <div class="alert border-0 mb-4" style="background:linear-gradient(135deg,rgba(255,107,53,.05),rgba(255,159,28,.06));border-radius:12px">
        <div class="d-flex align-items-start gap-2">
            <i class="fas fa-info-circle text-warning mt-1"></i>
            <div>
                <h6 class="fw-bold mb-1" style="font-size:.9rem">방긋페이 영업관리자 수수료 안내</h6>
                <ul class="mb-0 small text-muted">
                    <li>ADPAY의 영업관리자 구조와 동일하게, 방긋페이에도 영업관리자를 배정할 수 있습니다.</li>
                    <li>임대인 유치에 따른 수수료(커미션)는 <strong>기존 영업관리자 연결</strong> 메뉴에서 가맹점 단위로 관리됩니다.</li>
                    <li>방긋페이 수수료는 월세 결제 수수료(3.5%) 내에서 배분됩니다.</li>
                </ul>
            </div>
        </div>
    </div>
    
    <!-- 영업관리자 카드 -->
    <div class="row g-3 mb-4">
    ${salesManagers.length === 0 ? `
        <div class="col-12">
            <div class="card data-card"><div class="card-body text-center py-5">
                <i class="fas fa-user-tie fa-3x mb-3" style="color:#ff9f1c;opacity:.3"></i>
                <p class="text-muted mb-3">등록된 영업관리자가 없습니다</p>
                <p class="small text-muted">사용자 목록에서 역할을 '영업관리자'로 변경하여 추가하세요.</p>
                <button class="btn btn-outline-primary btn-sm" onclick="navigate('admin-users')"><i class="fas fa-users-cog me-1"></i>사용자 관리</button>
            </div></div>
        </div>` :
    salesManagers.map(s => {
        const myAssigns = assignMap[s.id] || [];
        const activeAssigns = myAssigns.filter(a => a.is_active);
        const totalCommission = myAssigns.reduce((sum, a) => sum + (a.commission_rate || 0), 0);
        const avgRate = activeAssigns.length > 0 ? (totalCommission / activeAssigns.length * 100).toFixed(1) : '0.0';
        
        return `
        <div class="col-md-6">
            <div class="card border-0 shadow-sm h-100" style="border-top:3px solid #ff9f1c">
                <div class="card-header bg-transparent d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-0 fw-bold"><i class="fas fa-user-tie me-2" style="color:#ff9f1c"></i>${s.name}</h6>
                        <small class="text-muted">${s.email}</small>
                    </div>
                    <div>${s.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</div>
                </div>
                <div class="card-body">
                    <div class="row g-2 mb-3 text-center">
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-primary">${activeAssigns.length}</div><small class="text-muted">담당 가맹점</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold text-success">${avgRate}%</div><small class="text-muted">평균 커미션</small></div></div>
                        <div class="col-4"><div class="bg-light rounded p-2"><div class="fs-5 fw-bold" style="color:#ff9f1c">${s.phone || '-'}</div><small class="text-muted">연락처</small></div></div>
                    </div>
                    ${activeAssigns.length > 0 ? `
                    <div class="table-responsive">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="table-light"><tr><th>가맹점</th><th>커미션율</th><th>상태</th></tr></thead>
                            <tbody>${activeAssigns.map(a => `
                                <tr>
                                    <td class="fw-bold">${a.merchant_name || '-'}</td>
                                    <td class="text-primary fw-bold">${(a.commission_rate*100).toFixed(2)}%</td>
                                    <td>${a.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
                                </tr>
                            `).join('')}</tbody>
                        </table>
                    </div>` : `
                    <div class="text-center py-3 text-muted">
                        <i class="fas fa-inbox d-block mb-1 opacity-50"></i>
                        <small>배정된 가맹점 없음</small>
                    </div>`}
                    <div class="mt-3 d-flex gap-2">
                        <button class="btn btn-sm btn-outline-warning" onclick="navigate('admin-banggut-sales-assign')"><i class="fas fa-link me-1"></i>임대인 연결</button>
                        <button class="btn btn-sm btn-outline-${s.is_active?'danger':'success'}" onclick="toggleUserActive(${s.id})">
                            <i class="fas fa-${s.is_active?'ban':'check'} me-1"></i>${s.is_active?'비활성화':'활성화'}
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('')}
    </div>
    
    <!-- 빠른 링크 -->
    <div class="card data-card" style="border-radius:14px">
        <div class="card-body">
            <div class="row g-2 text-center">
                <div class="col-6 col-md-3"><a href="#" onclick="navigate('admin-banggut-sales-assign')" class="btn btn-outline-warning w-100 py-2" style="border-radius:10px;font-size:.85rem"><i class="fas fa-handshake d-block mb-1"></i>임대인 연결</a></div>
                <div class="col-6 col-md-3"><a href="#" onclick="navigate('admin-landlords')" class="btn btn-outline-primary w-100 py-2" style="border-radius:10px;font-size:.85rem"><i class="fas fa-building d-block mb-1"></i>임대인 관리</a></div>
                <div class="col-6 col-md-3"><a href="#" onclick="navigate('admin-fee-policies')" class="btn btn-outline-success w-100 py-2" style="border-radius:10px;font-size:.85rem"><i class="fas fa-percentage d-block mb-1"></i>수수료 정책</a></div>
                <div class="col-6 col-md-3"><a href="#" onclick="navigate('admin-users')" class="btn btn-outline-dark w-100 py-2" style="border-radius:10px;font-size:.85rem"><i class="fas fa-users-cog d-block mb-1"></i>사용자 관리</a></div>
            </div>
        </div>
    </div>`;
}

// ─── 방긋페이 영업관리자 연결 (임대인 전용) ─────────────────
async function loadAdminBanggutSalesAssign(c, t) {
    t.textContent = '방긋페이 영업관리자 연결';
    const [landlords, salesManagers, assigns] = await Promise.all([
        apiGet('/api/admin/landlords').catch(() => []),
        apiGet('/api/admin/sales-managers'),
        apiGet('/api/admin/banggut/sales-assignments').catch(() => []),
    ]);
    
    const landlordOpts = landlords.map(l => `<option value="${l.id}">${l.name} (${l.building_name || '건물명 미등록'})</option>`).join('');
    const salesOpts = salesManagers.map(u => `<option value="${u.id}">${u.name} (${u.email})</option>`).join('');
    
    c.innerHTML = `
    <!-- 배너 -->
    <div class="card border-0 shadow-sm mb-4" style="border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2d1b03 0%,#5a3408 50%,#ff9f1c 100%)">
        <div class="card-body py-3 px-4 d-flex align-items-center justify-content-between flex-wrap gap-2">
            <div class="d-flex align-items-center gap-3">
                <div style="width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center">
                    <i class="fas fa-handshake text-white"></i>
                </div>
                <div>
                    <h5 class="mb-0 text-white fw-bold">방긋페이 영업관리자 연결</h5>
                    <small style="color:rgba(255,255,255,.65)">임대인 유치 영업관리자와 임대인을 연결합니다</small>
                </div>
            </div>
            <span class="badge" style="background:rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:50px;font-size:.78rem">
                <i class="fas fa-smile me-1" style="color:#ff9f1c"></i>Bang Good Pay
            </span>
        </div>
    </div>
    
    <!-- 안내 -->
    <div class="alert border-0 mb-4" style="background:rgba(255,159,28,.06);border-radius:12px">
        <div class="d-flex align-items-start gap-2">
            <i class="fas fa-info-circle text-warning mt-1"></i>
            <div>
                <h6 class="fw-bold mb-1" style="font-size:.9rem">방긋페이 임대인 연결 안내</h6>
                <ul class="mb-0 small text-muted">
                    <li>방긋페이에서 영업관리자가 유치한 <strong>임대인</strong>을 연결합니다.</li>
                    <li>ADPAY의 가맹점 연결과 별도로 운영되며, 수수료는 <strong>월세 결제 수수료(3.5%) 내</strong>에서 배분됩니다.</li>
                    <li>예: 수익률 1.0% 설정 시, 월세 100만원 결제 → 영업관리자 수익 10,000원</li>
                </ul>
            </div>
        </div>
    </div>
    
    <!-- 새 연결 추가 폼 -->
    <div class="card data-card mb-4" style="border-radius:14px;border-top:3px solid #ff9f1c">
        <div class="card-header"><h5 class="mb-0"><i class="fas fa-plus-circle me-2" style="color:#ff9f1c"></i>새 임대인 연결</h5></div>
        <div class="card-body">
            <div class="row g-3">
                <div class="col-12 col-md-6">
                    <label class="form-label fw-bold"><i class="fas fa-building me-1 text-warning"></i>임대인</label>
                    <select class="form-select" id="bgAssignLandlord">${landlordOpts || '<option disabled>임대인 없음</option>'}</select>
                </div>
                <div class="col-12 col-md-6">
                    <label class="form-label fw-bold"><i class="fas fa-user-tie me-1 text-info"></i>영업관리자</label>
                    <select class="form-select" id="bgAssignSales">${salesOpts || '<option disabled>영업관리자 없음</option>'}</select>
                </div>
                <div class="col-6 col-md-4">
                    <label class="form-label fw-bold">수익률 (VAT별도)</label>
                    <div class="input-group">
                        <input type="number" class="form-control" id="bgAssignRate" value="1.0" step="0.1" min="0" max="3.5" placeholder="1.0">
                        <span class="input-group-text">%</span>
                    </div>
                    <small class="text-muted">최대 3.5%</small>
                </div>
                <div class="col-6 col-md-4">
                    <label class="form-label fw-bold">메모</label>
                    <input type="text" class="form-control" id="bgAssignMemo" placeholder="배정 사유">
                </div>
                <div class="col-12 col-md-4 d-flex align-items-end">
                    <button class="btn w-100" style="height:42px;background:#ff9f1c;color:#fff;border:none" onclick="createBanggutSalesAssignment()">
                        <i class="fas fa-link me-1"></i>임대인 연결
                    </button>
                </div>
            </div>
            <div id="bgAssignResult" class="mt-2"></div>
        </div>
    </div>
    
    <!-- 연결 현황 -->
    <div class="card data-card" style="border-radius:14px">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-list me-2" style="color:#ff9f1c"></i>방긋페이 영업관리자 연결 현황</h5>
            <span class="badge" style="background:#ff9f1c">${assigns.length}건</span>
        </div>
        <div class="card-body">
            ${assigns.length > 0 ? `
            <div class="table-responsive">
                <table class="table table-hover table-sm align-middle">
                    <thead class="table-light"><tr><th>ID</th><th>임대인</th><th>건물명</th><th>영업관리자</th><th>수익률</th><th>수익 예시</th><th>메모</th><th>상태</th><th>액션</th></tr></thead>
                    <tbody>${assigns.map(a => `<tr>
                        <td>${a.id}</td>
                        <td class="fw-bold">${a.landlord_name || '-'}</td>
                        <td class="text-muted">${a.building_name || '-'}</td>
                        <td><i class="fas fa-user-tie text-info me-1"></i>${a.sales_manager_name || '-'}</td>
                        <td class="fw-bold text-nowrap" style="color:#ff9f1c">${(a.commission_rate*100).toFixed(2)}%</td>
                        <td class="text-success fw-bold text-nowrap">${(1000000 * a.commission_rate).toLocaleString('ko-KR', {maximumFractionDigits:0})}원</td>
                        <td class="text-muted small">${a.memo || '-'}</td>
                        <td>${a.is_active ? '<span class="badge bg-success">활성</span>' : '<span class="badge bg-secondary">비활성</span>'}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteBanggutSalesAssignment(${a.id})" title="연결 해제">
                                <i class="fas fa-unlink"></i>
                            </button>
                        </td>
                    </tr>`).join('')}</tbody>
                </table>
            </div>` : `
            <div class="text-center py-4 text-muted">
                <i class="fas fa-handshake fa-2x mb-2 d-block" style="opacity:.3;color:#ff9f1c"></i>
                <p class="mb-1">연결된 임대인이 없습니다</p>
                <small>위 폼에서 임대인과 영업관리자를 연결해 주세요.</small>
            </div>`}
        </div>
    </div>`;
}

async function createBanggutSalesAssignment() {
    try {
        const landlordId = parseInt(document.getElementById('bgAssignLandlord').value);
        const salesId = parseInt(document.getElementById('bgAssignSales').value);
        const rate = parseFloat(document.getElementById('bgAssignRate').value) / 100;
        const memo = document.getElementById('bgAssignMemo').value;
        
        if (!landlordId || !salesId) { alert('임대인과 영업관리자를 선택해주세요.'); return; }
        if (rate < 0 || rate > 0.035) { alert('수익률은 0~3.5% 범위에서 설정해주세요.'); return; }
        
        await apiPost('/api/admin/banggut/sales-assignments', {
            landlord_user_id: landlordId,
            sales_manager_user_id: salesId,
            commission_rate: rate,
            memo: memo || null,
        });
        
        const el = document.getElementById('bgAssignResult');
        el.innerHTML = '<div class="alert alert-success py-2"><i class="fas fa-check-circle me-1"></i>임대인 연결 완료!</div>';
        setTimeout(() => navigate('admin-banggut-sales-assign'), 1000);
    } catch (e) {
        const el = document.getElementById('bgAssignResult');
        el.innerHTML = `<div class="alert alert-danger py-2"><i class="fas fa-exclamation-circle me-1"></i>${e.message}</div>`;
    }
}

async function deleteBanggutSalesAssignment(id) {
    if (!confirm('이 방긋페이 영업관리자 연결을 해제하시겠습니까?')) return;
    try {
        await api(`/api/admin/banggut/sales-assignments/${id}`, { method: 'DELETE' });
        navigate('admin-banggut-sales-assign');
    } catch (e) { alert('해제 실패: ' + e.message); }
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
async function apiPost(url, data) {
    const opts = { method: 'POST', headers: { 'Authorization': 'Bearer ' + getToken() } };
    if (data) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(data); }
    const res = await fetch(url, opts);
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Request failed'); }
    return res.json();
}
async function apiDelete(url) {
    const res = await fetch(url, { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + getToken() } });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Request failed'); }
    return res.json();
}
