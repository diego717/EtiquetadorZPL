// API host/port resolution for local and remote clients

// Sesion para usar la app desde fuera de la oficina (por el tunel de Cloudflare el servidor
// pide login; desde la PC o la red local, no). Mismas claves que login.html y cloud.html.
const SESSION_TOKEN_KEY = 'cloud_access_token';

function getSessionToken() {
    try {
        return localStorage.getItem(SESSION_TOKEN_KEY) || '';
    } catch (e) {
        return '';
    }
}

function clearSessionToken() {
    try {
        localStorage.removeItem(SESSION_TOKEN_KEY);
    } catch (e) {
        // Sin almacenamiento no hay nada que borrar.
    }
}

function redirectToLogin() {
    const page = window.location.pathname.split('/').pop() || 'config.html';
    const next = `${page}${window.location.search}${window.location.hash}`;
    window.location.href = `login.html?next=${encodeURIComponent(next)}`;
}

(function installSessionFetch() {
    if (typeof window.fetch !== 'function' || window.__sessionFetchInstalled) return;
    window.__sessionFetchInstalled = true;
    const nativeFetch = window.fetch.bind(window);
    let redirecting = false;

    const isOwnApi = (input) => {
        try {
            const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
            return url.origin === window.location.origin && url.pathname.startsWith('/api');
        } catch (e) {
            return false;
        }
    };

    window.fetch = async (input, init = {}) => {
        const ownApi = isOwnApi(input);
        const token = ownApi ? getSessionToken() : '';
        if (token) {
            const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
            if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
            init = { ...init, headers };
        }
        const response = await nativeFetch(input, init);
        if (ownApi && response.status === 401 && response.headers.get('X-Login-Required') === '1' && !redirecting) {
            redirecting = true;
            clearSessionToken();
            redirectToLogin();
        }
        return response;
    };
})();

const CURRENT_PROTOCOL = window.location.protocol || 'http:';
const CURRENT_HOSTNAME = window.location.hostname || 'localhost';
const CURRENT_ORIGIN = (window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';

async function getApiPort() {
    // 1) Read api_port from the same web origin
    try {
        const response = await fetch('/api_port.txt');
        if (response.ok) {
            const port = parseInt(await response.text(), 10);
            if (port && port > 1000) {
                return port;
            }
        }
    } catch (e) {
        // keep probing
    }

    // 2) If this origin already serves /api/status, keep current port
    if (CURRENT_ORIGIN) {
        try {
            const response = await fetch(`${CURRENT_ORIGIN}/api/status`, { method: 'GET' });
            if (response.ok) {
                const currentPort = parseInt(window.location.port || '0', 10);
                if (currentPort > 0) {
                    return currentPort;
                }
            }
        } catch (e) {
            // keep probing
        }
    }

    // 3) Probe common ports on the current hostname (not localhost fixed)
    const ports = [8002, 8003, 8004, 8005, 8001, 8000];
    for (const port of ports) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);

            const response = await fetch(`${CURRENT_PROTOCOL}//${CURRENT_HOSTNAME}:${port}/api/status`, {
                method: 'GET',
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            if (response.ok) {
                console.log(`API found at ${CURRENT_HOSTNAME}:${port}`);
                return port;
            }
        } catch (e) {
            continue;
        }
    }

    console.warn('No API port detected, using 8002');
    return 8002;
}

// API base config
let API_BASE = CURRENT_ORIGIN || `${CURRENT_PROTOCOL}//${CURRENT_HOSTNAME}:8002`;
let API_PORT_DETECTED = Boolean(CURRENT_ORIGIN);

async function ensureApiPort() {
    if (!API_PORT_DETECTED) {
        const port = await getApiPort();
        API_BASE = `${CURRENT_PROTOCOL}//${CURRENT_HOSTNAME}:${port}`;
        API_PORT_DETECTED = true;
        console.log('API configured at:', API_BASE);
    }
    return API_BASE;
}
