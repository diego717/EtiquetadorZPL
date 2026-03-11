// API host/port resolution for local and remote clients
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
