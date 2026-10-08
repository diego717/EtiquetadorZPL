// Controlador de la pagina de configuracion: API, estado, salud y ciclo de vida.

async function fetchAPI(endpoint) {
    try {
        // Asegurar que tenemos el puerto correcto
        if (!API_BASE || API_BASE.includes('8003')) {
            const port = await getApiPort();
            API_BASE = `${window.location.protocol}//${window.location.hostname}:${port}`;
        }

        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error:', error);
        return null;
    }
}

async function loadConfigs() {
    try {
        // Asegurar que tenemos el puerto correcto
        if (!API_BASE || API_BASE.includes('8003')) {
            const port = await getApiPort();
            API_BASE = `${window.location.protocol}//${window.location.hostname}:${port}`;
        }

        // Cargar configuracion de notificaciones
        const notifResponse = await fetchAPI('/api/config/notifications');
        if (notifResponse && !notifResponse.error) {
            notificationConfig = notifResponse;
            console.log('Config notificaciones cargada:', notificationConfig);
        } else {
            // Usar configuracion por defecto
            notificationConfig = {
                desktop_enabled: true,
                notify_on_error: true,
                notify_on_success: false,
                email_enabled: false,
                email_config: {}
            };
            console.log('Usando config por defecto notificaciones');
        }
        updateNotificationForm();

        // Cargar configuracion de backup
        const backupResponse = await fetchAPI('/api/config/backup');
        if (backupResponse && !backupResponse.error) {
            backupConfig = backupResponse;
            console.log('Config backup cargada:', backupConfig);
        } else {
            // Usar configuracion por defecto
            backupConfig = {
                enabled: true,
                daily_backup: true,
                weekly_backup: true,
                keep_daily: 7,
                keep_weekly: 4
            };
            console.log('Usando config por defecto backup');
        }
        updateBackupForm();

        await loadMercadoLibreConfig();
        await loadAdministradoConfig();
        await autoSyncAdministradoIfNeeded();
        await loadOdooConfig();
        await loadOdooAutomationStatus();
        loadBackups();
    } catch (error) {
        console.error('Error cargando configuraciones:', error);
        // Cargar valores por defecto si hay error
        updateNotificationForm();
        updateBackupForm();
        updateMercadoLibreForm();
        updateAdministradoForm();
        updateOdooForm();
    }
}

// ---- Barra de salud ----
function setHealthItem(id, state, value, title = '') {
    const item = document.getElementById(id);
    if (!item) return;
    item.dataset.state = state;
    const valueEl = item.querySelector('.health-value');
    if (valueEl) valueEl.textContent = value;
    item.title = title || value;
}

function readSelectValue(id) {
    const select = document.getElementById(id);
    return select ? String(select.value || '').trim() : '';
}

function printersStillLoading() {
    const select = document.getElementById('odoo-order-printer-primary');
    return !select || /Cargando/i.test(select.options[0]?.textContent || '') && select.options.length <= 1;
}

function renderHealthBar() {
    if (!document.getElementById('health-bar')) return;

    const adm = administradoConfig || {};
    const admLoaded = Object.keys(adm).length > 0;
    if (administradoLastSync && !administradoLastSync.ok) {
        setHealthItem('health-adm', 'error', 'Error al sincronizar', administradoLastSync.error);
    } else if (administradoLastSync?.ok) {
        const time = administradoLastSync.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setHealthItem('health-adm', 'ok', `Sincronizado ${time}`, 'Ultima sincronizacion correcta');
    } else if (!admLoaded) {
        setHealthItem('health-adm', 'idle', 'Cargando...');
    } else if (adm.configured === false) {
        setHealthItem('health-adm', 'warn', 'Sin sesion guardada');
    } else if (adm.enabled === false) {
        setHealthItem('health-adm', 'warn', 'Integracion deshabilitada');
    } else {
        setHealthItem('health-adm', 'idle', 'Sin sincronizar');
    }

    const odoo = odooConfig || {};
    if (!Object.keys(odoo).length) {
        setHealthItem('health-odoo', 'idle', 'Cargando...');
    } else if (odoo.enabled !== true) {
        setHealthItem('health-odoo', 'warn', 'Deshabilitado');
    } else if (odoo.configured === false) {
        setHealthItem('health-odoo', 'warn', 'Datos incompletos');
    } else {
        setHealthItem('health-odoo', 'ok', 'Configurado', odoo.base_url || 'Configurado');
    }

    const status = odooAutomationStatus || {};
    if (!Object.keys(odoo).length || !Object.keys(status).length) {
        setHealthItem('health-worker', 'idle', 'Cargando...');
    } else if (odoo.automation_enabled !== true) {
        setHealthItem('health-worker', 'idle', 'Automatizacion apagada', 'La automatizacion en background esta deshabilitada; la impresion manual funciona igual');
    } else if (status.running === true) {
        if (status.last_error) {
            setHealthItem('health-worker', 'warn', 'Activo con errores', compactErrorText(status.last_error));
        } else {
            setHealthItem('health-worker', 'ok', 'Activo');
        }
    } else {
        setHealthItem('health-worker', 'error', 'Detenido', 'La automatizacion esta habilitada pero el worker no corre');
    }

    const orderPrinter = readSelectValue('odoo-order-printer-primary') || readSelectValue('odoo-order-printer-fallback');
    const labelPrinter = readSelectValue('odoo-label-printer-primary')
        || readSelectValue('odoo-label-printer-fallback')
        || String(adm.default_printer || '').trim();
    const printersTitle = `Orden: ${orderPrinter || '-'} | Etiqueta: ${labelPrinter || '-'}`;
    if (printersStillLoading()) {
        setHealthItem('health-printers', 'idle', 'Cargando...');
    } else if (!orderPrinter && !labelPrinter) {
        setHealthItem('health-printers', 'warn', 'Sin impresoras asignadas', printersTitle);
    } else if (!orderPrinter) {
        setHealthItem('health-printers', 'warn', 'Falta impresora de orden', printersTitle);
    } else if (!labelPrinter) {
        setHealthItem('health-printers', 'warn', 'Falta impresora de etiqueta', printersTitle);
    } else {
        setHealthItem('health-printers', 'ok', 'Orden y etiqueta asignadas', printersTitle);
    }

    const stubSummary = document.getElementById('odoo-config-stub-summary');
    if (stubSummary) {
        stubSummary.textContent = `Orden: ${orderPrinter || 'sin asignar'} · Etiqueta: ${labelPrinter || 'sin asignar'}. `
            + 'Oculta en esta vista para evitar cambios accidentales.';
    }
}

function focusHealthTarget(id) {
    const target = document.getElementById(id);
    if (!target) return;
    if (target.closest('#odoo-automation-section') && adminOnlyMode) {
        setOdooConfigVisibleInOpsView(true);
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target.classList.remove('flash-target');
    void target.offsetWidth;
    target.classList.add('flash-target');
}

// ---- Vista de envios: configuracion de Odoo plegada ----
function setOdooConfigVisibleInOpsView(visible) {
    document.body.classList.toggle('show-odoo-config', visible);
    const btn = document.getElementById('odoo-config-toggle-btn');
    if (btn) btn.textContent = visible ? 'Ocultar configuracion' : 'Mostrar configuracion';
}

function toggleOdooConfigInOpsView() {
    const visible = !document.body.classList.contains('show-odoo-config');
    setOdooConfigVisibleInOpsView(visible);
    if (visible) {
        document.getElementById('odoo-automation-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// ---- Cambios sin guardar ----
const DIRTY_SCOPES = {
    notif: { save: 'saveNotificationConfig', ids: ['desktop-notifications', 'error-notifications', 'success-notifications', 'email-enabled', 'smtp-server', 'smtp-port', 'smtp-user', 'smtp-password', 'to-emails'] },
    backup: { save: 'saveBackupConfig', ids: ['backup-enabled', 'daily-backup', 'weekly-backup', 'keep-daily', 'keep-weekly'] },
    meli: { save: 'saveMercadoLibreConfig', ids: ['meli-enabled', 'meli-client-id', 'meli-client-secret', 'meli-redirect-uri', 'meli-access-token', 'meli-refresh-token', 'meli-expires-in', 'meli-manual-user-id', 'meli-default-printer', 'meli-default-copies', 'meli-auto-print'] },
    adm: { save: 'saveAdministradoConfig', ids: ['adm-enabled', 'adm-sales-url', 'adm-default-copies', 'adm-pdf-render-dpi', 'adm-auto-crop-pdf', 'adm-raw-zpl-labels', 'adm-cookie-header'] },
    odoo: { save: 'saveOdooConfig', ids: ['odoo-enabled', 'odoo-auto-enabled', 'odoo-interval', 'odoo-url', 'odoo-db', 'odoo-user', 'odoo-password', 'odoo-report-name', 'odoo-order-prefix', 'odoo-shipment-field', 'odoo-order-states', 'odoo-sync-limit', 'odoo-order-label-delay', 'odoo-include-reprint', 'odoo-confirm-on-print', 'odoo-order-printer-primary', 'odoo-order-printer-fallback', 'odoo-order-copies', 'odoo-force-order-grayscale', 'odoo-label-printer-primary', 'odoo-label-printer-fallback', 'odoo-label-copies'] },
    totalnet: { save: 'saveTotalNetConfig', ids: ['totalnet-enabled', 'totalnet-client-id', 'totalnet-client-secret', 'totalnet-token-url', 'totalnet-api-base-url', 'totalnet-comercio', 'totalnet-sucursal'] }
};
const dirtySnapshots = {};
const dirtyState = {};

function readDirtyField(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    return el.type === 'checkbox' ? el.checked : el.value;
}

// onlyIds: al cargar las impresoras solo se toma la foto de esos selects,
// asi no se pisan cambios que el usuario ya este haciendo en otros campos.
function snapshotDirtyScope(key, onlyIds = null) {
    DIRTY_SCOPES[key].ids
        .filter((id) => !onlyIds || onlyIds.includes(id))
        .forEach((id) => { dirtySnapshots[id] = readDirtyField(id); });
    refreshDirtyScope(key);
}

function refreshDirtyScope(key) {
    const dirty = DIRTY_SCOPES[key].ids.some(
        (id) => id in dirtySnapshots && readDirtyField(id) !== dirtySnapshots[id]
    );
    dirtyState[key] = dirty;
    const badge = document.querySelector(`[data-dirty-badge="${key}"]`);
    if (badge) {
        badge.hidden = !dirty;
        (badge.closest('.odoo-panel') || badge.closest('.card'))?.classList.toggle('is-dirty', dirty);
    }
    document.querySelector(`button[onclick^="${DIRTY_SCOPES[key].save}("]`)?.classList.toggle('needs-save', dirty);
}

function hasUnsavedChanges() {
    return Object.values(dirtyState).some(Boolean);
}

function goToDirtySave(key) {
    const btn = document.querySelector(`button[onclick^="${DIRTY_SCOPES[key].save}("]`);
    if (!btn) return;
    const details = btn.closest('details');
    if (details) details.open = true;
    btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    btn.focus({ preventScroll: true });
}

function wrapWithSnapshot(fn, keys, onlyIds = null) {
    return function (...args) {
        const result = fn.apply(this, args);
        const after = () => {
            keys.forEach((key) => snapshotDirtyScope(key, onlyIds));
            renderHealthBar();
        };
        if (result && typeof result.then === 'function') {
            return result.then((value) => { after(); return value; });
        }
        after();
        return result;
    };
}

// Tomar la foto "guardada" cada vez que el formulario se llena desde el servidor.
updateNotificationForm = wrapWithSnapshot(updateNotificationForm, ['notif']);
updateBackupForm = wrapWithSnapshot(updateBackupForm, ['backup']);
updateMercadoLibreForm = wrapWithSnapshot(updateMercadoLibreForm, ['meli']);
updateAdministradoForm = wrapWithSnapshot(updateAdministradoForm, ['adm']);
const ODOO_PRINTER_FIELD_IDS = DIRTY_SCOPES.odoo.ids.filter((id) => /^odoo-(order|label)-printer-/.test(id));
updateOdooForm = wrapWithSnapshot(updateOdooForm, ['odoo'], DIRTY_SCOPES.odoo.ids.filter((id) => !ODOO_PRINTER_FIELD_IDS.includes(id)));
loadOdooPrinters = wrapWithSnapshot(loadOdooPrinters, ['odoo'], ODOO_PRINTER_FIELD_IDS);
loadTotalNetConfig = wrapWithSnapshot(loadTotalNetConfig, ['totalnet']);
updateOdooAutomationStatusForm = wrapWithSnapshot(updateOdooAutomationStatusForm, []);

['input', 'change'].forEach((type) => {
    document.addEventListener(type, (event) => {
        const id = event.target?.id;
        if (!id) return;
        Object.keys(DIRTY_SCOPES).forEach((key) => {
            if (DIRTY_SCOPES[key].ids.includes(id)) refreshDirtyScope(key);
        });
        if (/^odoo-(order|label)-printer-/.test(id)) renderHealthBar();
    });
});

document.querySelectorAll('[data-dirty-badge]').forEach((badge) => {
    badge.title = 'Ir al boton Guardar';
    badge.addEventListener('click', () => goToDirtySave(badge.dataset.dirtyBadge));
});
updateAdministradoFilterTabs();

initTheme();
initThemeFxControls();
initViewMode();
if (POS_ONLY_VIEW) {
    initPaymentSource();
    loadTotalNetConfig();
    loadPosReconciliationConfig();
    loadPosJournals();
    loadPosRoundingAccounts();
    loadPosPaymentOperators();
    loadPosPendingInvoicesFromRange();
    loadPosHistory();
    loadPosAutoStatus();
    posAutoStatusTimer = setInterval(loadPosAutoStatus, 60000);
} else {
    initAdministradoAutoRefreshSetting();
    focusSectionFromHash();
    loadConfigs();
    updateAdministradoAutoRefreshToggle();
    odooStatusTimer = setInterval(() => {
        loadOdooAutomationStatus();
    }, 15000);
}

window.addEventListener('hashchange', () => {
    if (!POS_ONLY_VIEW && adminOnlyMode && window.location.hash !== '#administrado') {
        window.location.hash = '#administrado';
        return;
    }
    focusSectionFromHash();
    if (!POS_ONLY_VIEW) autoSyncAdministradoIfNeeded(true);
});

window.addEventListener('visibilitychange', () => {
    if (!POS_ONLY_VIEW && !document.hidden) {
        autoRefreshAdministradoSales();
    }
});

window.addEventListener('beforeunload', (event) => {
    if (hasUnsavedChanges()) {
        // Si el usuario decide quedarse, los timers siguen corriendo.
        event.preventDefault();
        event.returnValue = '';
        return;
    }
    if (odooStatusTimer) {
        clearInterval(odooStatusTimer);
        odooStatusTimer = null;
    }
    stopAdministradoAutoRefresh();
});
