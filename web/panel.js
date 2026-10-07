// Helpers compartidos de las paginas de tablero. Requiere config.js (getApiPort).
const PANEL_THEME_KEY = 'etiquetador_ui_theme';
try {
    if (localStorage.getItem(PANEL_THEME_KEY) === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
} catch (e) { /* sin localStorage: tema oscuro */ }

let panelApiBase = '';

async function panelApiBaseUrl() {
    if (!panelApiBase) {
        const port = await getApiPort();
        panelApiBase = `${window.location.protocol}//${window.location.hostname}:${port}`;
    }
    return panelApiBase;
}

async function panelApi(path, options) {
    const base = await panelApiBaseUrl();
    const response = await fetch(`${base}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
}

function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

const panelNumber = new Intl.NumberFormat('es-UY', { maximumFractionDigits: 0 });
const CURRENCY_SYMBOLS = { UYU: '$', USD: 'US$' };

function money(amount, currency = 'UYU', decimals = 0) {
    const symbol = CURRENCY_SYMBOLS[currency] || currency;
    const formatted = Number(amount || 0).toLocaleString('es-UY', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    return `${symbol} ${formatted}`;
}

function shortDate(value) {
    if (!value) return '';
    const text = String(value).slice(0, 10);
    const [y, m, d] = text.split('-');
    return d ? `${d}/${m}/${y}` : text;
}

function timeAgo(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '';
    const minutes = Math.round((Date.now() - parsed.getTime()) / 60000);
    if (minutes < 1) return 'recien';
    if (minutes < 60) return `hace ${minutes} min`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `hace ${hours} h`;
    return `hace ${Math.round(hours / 24)} d`;
}

function panelCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function panelToggleTheme(button) {
    const next = panelCurrentTheme() === 'light' ? 'dark' : 'light';
    const apply = () => {
        if (next === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
        try { localStorage.setItem(PANEL_THEME_KEY, next); } catch (e) { /* sin localStorage */ }
        if (button) button.textContent = next === 'light' ? 'Tema oscuro' : 'Tema claro';
    };
    // La animacion del cambio de tema vive en theme-fx.js (opcional por pagina).
    if (window.ThemeFx) window.ThemeFx.run(apply, button);
    else apply();
}

// Fechas "YYYY-MM-DD HH:MM:SS" de SQLite (CURRENT_TIMESTAMP) vienen en UTC sin zona.
function sqliteUtcToLocal(value) {
    if (!value) return '';
    const parsed = new Date(String(value).replace(' ', 'T') + 'Z');
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}
