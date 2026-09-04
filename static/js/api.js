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
// 로그아웃 진행 중 플래그 — 페이지 이동 직전 비동기 응답 에러창을 억제한다.
let _loggingOut = false;

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
        if (!newToken) { if (!_loggingOut) logout(); return null; }
        res = await send();
        if (res.status === 401) { if (!_loggingOut) logout(); return null; }
    }
    return parseApiResponse(res);
}

/** FastAPI 의 detail 을 사람이 읽을 수 있는 한 줄로 만든다.
 *
 * 422(Query pattern / 타입 검증 실패)는 detail 이 객체 배열로 오므로 그대로 문자열로
 * 만들면 "[object Object]" 가 되어 무엇이 틀렸는지 알 수 없다.
 */
function formatApiDetail(detail) {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map(item => {
            if (typeof item === 'string') return item;
            const loc = Array.isArray(item?.loc)
                ? item.loc.filter(part => part !== 'body' && part !== 'query' && part !== 'path')
                : [];
            const msg = item?.msg || '입력값이 올바르지 않습니다';
            return loc.length ? `${loc.join('.')}: ${msg}` : msg;
        }).filter(Boolean).join(', ');
    }
    if (typeof detail === 'object') return detail.msg || detail.message || '';
    return String(detail);
}

/** 응답 본문을 안전하게 해석한다.
 *
 * 이전에는 res.ok 확인 전에 res.json() 을 무조건 호출했다. 서버가 JSON 이 아닌 본문
 * (500 의 text/plain "Internal Server Error", 프록시의 502/504 HTML, 빈 본문 등)을
 * 주면 그 자리에서 파싱이 터졌고, WebKit(사파리)은 그 예외 메시지를
 * "The string did not match the expected pattern." 으로 낸다. 그래서 실제 원인인
 * HTTP 오류가 정규식/패턴 오류처럼 보였다. 본문은 텍스트로 먼저 받고 파싱은 시도만 해,
 * 어떤 응답이 와도 원인을 알 수 있는 메시지를 던진다.
 */
async function parseApiResponse(res) {
    let raw = '';
    try { raw = await res.text(); } catch { raw = ''; }

    let data = null;
    if (raw) {
        try { data = JSON.parse(raw); } catch { data = null; }
    }

    if (!res.ok) {
        if (_loggingOut) throw new Error('로그아웃 중');
        const detail = data ? formatApiDetail(data.detail) : '';
        throw new Error(detail || `서버 오류가 발생했습니다 (HTTP ${res.status})`);
    }
    // 본문이 없는 정상 응답(204 등)은 null 로 돌려준다.
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
    _loggingOut = true;
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
