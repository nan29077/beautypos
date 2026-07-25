/**
 * ADPAY API Helper
 */
const API_BASE = '';

function getToken() { return localStorage.getItem('access_token'); }
function getUser() {
    try { return JSON.parse(localStorage.getItem('user')); } catch { return null; }
}

async function api(path, options = {}) {
    const token = getToken();
    const headers = options.headers || {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    const res = await fetch(API_BASE + path, { ...options, headers });
    if (res.status === 401) { logout(); return null; }
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
    return new Date(d).toLocaleString('ko-KR');
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
