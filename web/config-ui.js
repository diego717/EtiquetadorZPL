// Interfaz compartida: modal, toasts, tema y navegacion.

// ---- UI: modal de confirmacion y notificaciones (reemplazan alert/confirm del navegador) ----
const UI_ICONS = {
    print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 14h12v7H6z"/></svg>',
    danger: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>'
};
let uiModalResolve = null;
let uiModalReturnFocus = null;

function uiEscape(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function closeUiModal(result) {
    const backdrop = document.getElementById('ui-modal');
    if (!backdrop || backdrop.hidden) return;
    backdrop.classList.remove('is-open');
    setTimeout(() => { backdrop.hidden = true; }, 180);
    const resolve = uiModalResolve;
    uiModalResolve = null;
    if (uiModalReturnFocus && typeof uiModalReturnFocus.focus === 'function') {
        uiModalReturnFocus.focus();
    }
    if (resolve) resolve(result);
}

/**
 * Modal de confirmacion. Devuelve Promise<boolean>.
 * opts: { title, message, details: [[label, value]], confirmText, cancelText, tone: 'print'|'danger'|'info' }
 */
function uiConfirm(opts = {}) {
    const backdrop = document.getElementById('ui-modal');
    if (!backdrop) {
        return Promise.resolve(window.confirm(opts.message || opts.title || 'Confirmar?'));
    }
    if (uiModalResolve) closeUiModal(false);
    const tone = opts.tone || 'info';
    const modal = backdrop.querySelector('.ui-modal');
    modal.dataset.tone = tone;
    document.getElementById('ui-modal-icon').innerHTML = UI_ICONS[tone] || UI_ICONS.info;
    document.getElementById('ui-modal-title').textContent = opts.title || 'Confirmar';
    const messageEl = document.getElementById('ui-modal-message');
    messageEl.textContent = opts.message || '';
    messageEl.hidden = !opts.message;
    const detailsEl = document.getElementById('ui-modal-details');
    const details = Array.isArray(opts.details) ? opts.details : [];
    detailsEl.innerHTML = details
        .map(([label, value]) => `<dt>${uiEscape(label)}</dt><dd>${uiEscape(value)}</dd>`)
        .join('');
    detailsEl.hidden = details.length === 0;
    const warningsEl = document.getElementById('ui-modal-warnings');
    const warnings = Array.isArray(opts.warnings) ? opts.warnings.filter(Boolean) : [];
    if (warningsEl) {
        warningsEl.innerHTML = warnings.map((text) => `<li>${uiEscape(text)}</li>`).join('');
        warningsEl.hidden = warnings.length === 0;
    }
    const okBtn = document.getElementById('ui-modal-ok');
    const cancelBtn = document.getElementById('ui-modal-cancel');
    okBtn.textContent = opts.confirmText || 'Confirmar';
    cancelBtn.textContent = opts.cancelText || 'Cancelar';
    okBtn.className = `btn ${tone === 'danger' ? 'danger' : tone === 'print' ? 'success' : ''}`.trim();
    uiModalReturnFocus = document.activeElement;
    backdrop.hidden = false;
    requestAnimationFrame(() => {
        backdrop.classList.add('is-open');
        (tone === 'danger' ? cancelBtn : okBtn).focus();
    });
    return new Promise((resolve) => { uiModalResolve = resolve; });
}

function uiToast(message, tone = 'info', opts = {}) {
    const container = document.getElementById('ui-toasts');
    const text = String(message ?? '');
    if (!container) {
        console.log(text);
        return;
    }
    const titles = { success: 'Listo', error: 'Error', info: 'Aviso' };
    const icons = { success: '✓', error: '!', info: 'i' };
    const duration = opts.duration || (tone === 'error' ? 12000 : tone === 'success' ? 5000 : 7000);
    const toast = document.createElement('div');
    toast.className = `ui-toast ${tone}`;
    toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    toast.innerHTML = `
        <span class="ui-toast-icon" aria-hidden="true">${icons[tone] || 'i'}</span>
        <div class="ui-toast-body"><strong>${uiEscape(opts.title || titles[tone] || 'Aviso')}</strong>${uiEscape(text)}</div>
        <button type="button" class="ui-toast-close" aria-label="Cerrar">&times;</button>
        <span class="ui-toast-timer" style="animation-duration:${duration}ms"></span>`;
    let timer = null;
    const dismiss = () => {
        if (toast.classList.contains('is-leaving')) return;
        clearTimeout(timer);
        toast.classList.add('is-leaving');
        setTimeout(() => toast.remove(), 230);
    };
    toast.querySelector('.ui-toast-close').addEventListener('click', dismiss);
    container.appendChild(toast);
    while (container.children.length > 4) container.firstElementChild.remove();
    timer = setTimeout(dismiss, duration);
}

// Los mensajes existentes usan alert(); se muestran como notificacion no bloqueante.
window.alert = (message) => {
    const text = String(message ?? '');
    let tone = 'info';
    if (/^\s*OK\b/i.test(text)) tone = 'success';
    else if (/error|fall[oó]|no se pudo/i.test(text)) tone = 'error';
    uiToast(text.replace(/^\s*OK:\s*/i, ''), tone);
};

document.addEventListener('keydown', (event) => {
    const backdrop = document.getElementById('ui-modal');
    if (!backdrop || backdrop.hidden) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        closeUiModal(false);
    } else if (event.key === 'Tab') {
        const focusables = [...backdrop.querySelectorAll('button:not([disabled])')];
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
});

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('ui-modal-ok')?.addEventListener('click', () => closeUiModal(true));
    document.getElementById('ui-modal-cancel')?.addEventListener('click', () => closeUiModal(false));
    document.getElementById('ui-modal')?.addEventListener('click', (event) => {
        if (event.target.id === 'ui-modal') closeUiModal(false);
    });
});

// Navegacion interna sin tocar el hash (el hash #administrado controla el auto-refresh).
function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

const ADMIN_ONLY_STORAGE_KEY = 'etiquetador_admin_only_mode';
const ADMINISTRADO_AUTO_REFRESH_STORAGE_KEY = 'etiquetador_administrado_auto_refresh';
const THEME_STORAGE_KEY = 'etiquetador_ui_theme';
const POS_ONLY_VIEW = new URLSearchParams(window.location.search).get('view') === 'pos';
const ADMIN_OPS_VIEW = new URLSearchParams(window.location.search).get('view') === 'administrado';
let adminOnlyMode = true;
let currentTheme = 'dark';

function updateThemeToggleButton() {
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    btn.textContent = currentTheme === 'light' ? 'Tema oscuro' : 'Tema claro';
    btn.setAttribute('aria-label', currentTheme === 'light' ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro');
}

function applyTheme(theme, persist = true) {
    currentTheme = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', currentTheme);
    updateThemeToggleButton();
    if (!persist) {
        return;
    }
    try {
        localStorage.setItem(THEME_STORAGE_KEY, currentTheme);
    } catch (e) {
        // Ignorar si localStorage no esta disponible.
    }
}

function initTheme() {
    let stored = null;
    try {
        stored = localStorage.getItem(THEME_STORAGE_KEY);
    } catch (e) {
        stored = null;
    }
    applyTheme(stored === 'light' ? 'light' : 'dark', false);
}

function initThemeFxControls() {
    const select = document.getElementById('theme-fx-effect');
    if (!select || !window.ThemeFx) return;
    const groups = new Map();
    ThemeFx.EFFECT_LIST.forEach((fx) => {
        const option = new Option(fx.label, fx.id);
        if (!fx.group) {
            select.appendChild(option);
            return;
        }
        if (!groups.has(fx.group)) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = fx.group;
            groups.set(fx.group, optgroup);
            select.appendChild(optgroup);
        }
        groups.get(fx.group).appendChild(option);
    });
    const settings = ThemeFx.getSettings();
    select.value = settings.effect;
    document.getElementById('theme-fx-duration').value = settings.duration;
    updateThemeFxLabels(settings);

    if (!ThemeFx.isSupported()) {
        const note = document.getElementById('theme-fx-note');
        note.textContent = typeof document.startViewTransition === 'function'
            ? 'El sistema tiene "reducir movimiento" activado: el tema cambia sin animacion.'
            : 'Este navegador no soporta la animacion: el tema cambia al instante.';
        note.hidden = false;
    }
}

function updateThemeFxLabels(settings) {
    document.getElementById('theme-fx-duration-label').textContent = `${(settings.duration / 1000).toFixed(1)} s`;
    document.getElementById('theme-fx-duration').disabled = settings.effect === 'ninguno';
}

function saveThemeFxSettings() {
    if (!window.ThemeFx) return;
    const settings = ThemeFx.saveSettings({
        effect: document.getElementById('theme-fx-effect').value,
        duration: Number(document.getElementById('theme-fx-duration').value),
    });
    updateThemeFxLabels(settings);
}

function toggleTheme(originEl) {
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    const apply = () => applyTheme(nextTheme, true);
    const button = originEl || document.getElementById('theme-toggle-btn');
    if (window.ThemeFx) window.ThemeFx.run(apply, button);
    else apply();
}

function applyAdminOnlyMode() {
    document.body.classList.toggle('admin-only', adminOnlyMode);
    const toggleBtn = document.getElementById('toggle-admin-view-btn');
    if (toggleBtn) {
        toggleBtn.textContent = adminOnlyMode ? 'Mostrar panel completo' : 'Mostrar solo Administrado';
    }
    if (!POS_ONLY_VIEW) {
        document.getElementById('page-title').textContent = adminOnlyMode
            ? 'Envios Administrado'
            : 'Configuracion EtiquetadorZPL';
        document.getElementById('page-subtitle').textContent = adminOnlyMode
            ? 'Sincroniza e imprime orden + etiqueta'
            : 'Panel de administracion del sistema';
    }
}

function initViewMode() {
    if (POS_ONLY_VIEW) {
        adminOnlyMode = false;
        document.body.classList.add('pos-only-view');
        applyAdminOnlyMode();
        document.getElementById('page-title').textContent = 'Conciliacion de pagos';
        document.getElementById('page-subtitle').textContent = 'Cobros de TotalNet y Mercado Libre contra facturas de Odoo, con un historial comun';
        document.getElementById('nav-config-link')?.classList.remove('active');
        document.getElementById('nav-pos-link')?.classList.add('active');
        return;
    }
    if (ADMIN_OPS_VIEW) {
        // Vista de envios por URL: siempre solo Administrado, sin tocar la preferencia guardada.
        adminOnlyMode = true;
        applyAdminOnlyMode();
        document.getElementById('nav-config-link')?.classList.remove('active');
        document.getElementById('nav-admin-link')?.classList.add('active');
        if (window.location.hash !== '#administrado') {
            window.location.hash = '#administrado';
        }
        return;
    }
    let stored = null;
    try {
        stored = localStorage.getItem(ADMIN_ONLY_STORAGE_KEY);
    } catch (e) {
        stored = null;
    }
    adminOnlyMode = stored === null ? true : stored === '1';
    applyAdminOnlyMode();
    if (adminOnlyMode && window.location.hash !== '#administrado') {
        window.location.hash = '#administrado';
    }
}

function toggleAdminOnlyMode() {
    if (POS_ONLY_VIEW) return;
    if (ADMIN_OPS_VIEW) {
        try {
            localStorage.setItem(ADMIN_ONLY_STORAGE_KEY, '0');
        } catch (e) {
            // Ignorar si localStorage no esta disponible.
        }
        window.location.href = 'config.html';
        return;
    }
    adminOnlyMode = !adminOnlyMode;
    try {
        localStorage.setItem(ADMIN_ONLY_STORAGE_KEY, adminOnlyMode ? '1' : '0');
    } catch (e) {
        // Ignorar si localStorage no esta disponible.
    }
    applyAdminOnlyMode();
    if (adminOnlyMode) {
        window.location.hash = '#administrado';
        focusSectionFromHash();
        autoSyncAdministradoIfNeeded(true);
    }
}

function focusSectionFromHash() {
    if (window.location.hash === '#mercadolibre') {
        const section = document.getElementById('mercadolibre-section');
        if (section) {
            section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            section.style.outline = '2px solid var(--accent-strong)';
            section.style.outlineOffset = '4px';
            setTimeout(() => {
                section.style.outline = '';
                section.style.outlineOffset = '';
            }, 2500);
        }
    }
    if (window.location.hash === '#administrado') {
        const section = document.getElementById('administrado-section');
        if (section) {
            section.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}
