/**
 * ADPAY API Helper
 */
const API_BASE = '';

function getToken() { return localStorage.getItem('access_token'); }
function getUser() {
    try { return JSON.parse(localStorage.getItem('user')); } catch { return null; }
}

// 동시에 여러 요청이 401을 받아도 refresh 는 한 번만 호출한다.
let _refreshInFlight = null;

function refreshAccessToken() {
    if (_refreshInFlight) return _refreshInFlight;
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return Promise.resolve(null);

    _refreshInFlight = fetch(API_BASE + '/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
    }).then(async res => {
        if (!res.ok) return null;
        const data = await res.json();
        if (!data || !data.access_token) return null;
        localStorage.setItem('access_token', data.access_token);
        return data.access_token;
    }).catch(() => null).finally(() => { _refreshInFlight = null; });

    return _refreshInFlight;
}

async function api(path, options = {}) {
    let sentToken = null;
    const send = () => {
        const token = getToken();
        sentToken = token;
        const headers = { ...(options.headers || {}) };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        if (!(options.body instanceof FormData)) {
            headers['Content-Type'] = headers['Content-Type'] || 'application/json';
        }
        return fetch(API_BASE + path, { ...options, headers });
    };

    let res = await send();
    if (res.status === 401) {
        // access_token 만료일 수 있으므로 refresh 후 한 번만 재시도한다.
        // 대시보드는 요청을 병렬로 던지므로, 그 사이 다른 요청이 이미 갱신해
        // 두었다면 refresh 를 다시 호출하지 않고 새 토큰으로 바로 재시도한다.
        const current = getToken();
        const newToken = (current && current !== sentToken)
            ? current
            : await refreshAccessToken();
        if (!newToken) { logout(); return null; }
        res = await send();
        if (res.status === 401) { logout(); return null; }
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'API Error');
    return data;
}

function apiGet(path) { return api(path); }
function apiPost(path, body) {
    return api(path, { method: 'POST', body: JSON.stringify(body) });
}
function apiPut(path, body) {
    return api(path, { method: 'PUT', body: JSON.stringify(body) });
}
function apiDelete(path) {
    return api(path, { method: 'DELETE' });
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = '/static/login.html';
}

function formatMoney(v) {
    return '₩' + Math.floor(v || 0).toLocaleString();
}

function formatDate(d) {
    if (!d || d === 'None') return '-';
    // DB 는 naive UTC 문자열로 반환한다. 공백을 T 로 교체하고 Z 접미사를 붙여
    // JS Date 가 UTC 로 파싱하도록 강제한 뒤 KST(Asia/Seoul)로 표시한다.
    const s = String(d).replace(' ', 'T');
    const iso = /[Zz]$|[+-]\d{2}:\d{2}$/.test(s) ? s : s + 'Z';
    return new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

function statusBadge(status) {
    const colors = {
        requested: 'warning', reviewing: 'info', running: 'primary',
        done: 'success', rejected: 'danger',
        pending: 'warning', approved: 'success',
        connected: 'secondary', tested: 'success', disabled: 'danger',
    };
    const labels = {
        requested: '요청됨', reviewing: '검토중', running: '집행중',
        done: '완료', rejected: '반려',
        pending: '대기', approved: '승인', rejected: '거절',
        connected: '연결됨', tested: '테스트 완료', disabled: '비활성',
    };
    const c = colors[status] || 'secondary';
    const l = labels[status] || status;
    return `<span class="badge bg-${c}">${l}</span>`;
}
