// Administrado: configuracion, sincronizacion, render e impresion.

let administradoConfig = {};
let administradoSales = [];
const ADMINISTRADO_FILTER_STORAGE_KEY = 'etiquetador_administrado_filter';
let administradoFilter = 'all';
try {
    administradoFilter = localStorage.getItem(ADMINISTRADO_FILTER_STORAGE_KEY) || 'all';
} catch (e) {
    administradoFilter = 'all';
}
const administradoOpenDetails = new Set();
let administradoLastSync = null;
let administradoSyncInProgress = false;
let administradoAutoSyncDone = false;
let administradoAutoRefreshTimer = null;
let administradoAutoRefreshEnabled = true;
const administradoPrintInFlight = new Set();
const ADMINISTRADO_AUTO_REFRESH_MS = 15000;

function isAdministradoHashActive() {
    return window.location.hash === '#administrado';
}

function updateAdministradoAutoRefreshToggle() {
    const checkbox = document.getElementById('adm-auto-refresh-toggle');
    if (!checkbox) {
        return;
    }
    checkbox.checked = administradoAutoRefreshEnabled === true;
}

function applyAdministradoAutoRefreshEnabled(enabled, persist = true) {
    administradoAutoRefreshEnabled = enabled !== false;
    updateAdministradoAutoRefreshToggle();
    if (administradoAutoRefreshEnabled) {
        startAdministradoAutoRefresh();
    } else {
        stopAdministradoAutoRefresh();
    }
    if (!persist) {
        return;
    }
    try {
        localStorage.setItem(
            ADMINISTRADO_AUTO_REFRESH_STORAGE_KEY,
            administradoAutoRefreshEnabled ? '1' : '0'
        );
    } catch (e) {
        // Ignorar si localStorage no esta disponible.
    }
}

function initAdministradoAutoRefreshSetting() {
    let stored = null;
    try {
        stored = localStorage.getItem(ADMINISTRADO_AUTO_REFRESH_STORAGE_KEY);
    } catch (e) {
        stored = null;
    }
    applyAdministradoAutoRefreshEnabled(stored === '0' ? false : true, false);
}

function toggleAdministradoAutoRefreshSetting() {
    const checkbox = document.getElementById('adm-auto-refresh-toggle');
    applyAdministradoAutoRefreshEnabled(checkbox ? checkbox.checked : true, true);
}

function canAutoRefreshAdministrado() {
    return (
        administradoAutoRefreshEnabled === true
        && isAdministradoHashActive()
        && document.hidden !== true
        && administradoSyncInProgress !== true
        && administradoPrintInFlight.size === 0
    );
}

function compactErrorText(value, maxLen = 220) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    if (!text) {
        return '-';
    }
    if (text.length <= maxLen) {
        return text;
    }
    return `${text.slice(0, Math.max(0, maxLen - 3))}...`;
}

async function autoSyncAdministradoIfNeeded(force = false) {
    if (!isAdministradoHashActive()) {
        return;
    }
    if (!force && administradoAutoSyncDone) {
        return;
    }
    await syncAdministradoSales({ silent: true });
    administradoAutoSyncDone = true;
}

async function autoRefreshAdministradoSales() {
    if (!canAutoRefreshAdministrado()) {
        return;
    }
    await syncAdministradoSales({ silent: true });
}

function startAdministradoAutoRefresh() {
    if (administradoAutoRefreshTimer) {
        return;
    }
    administradoAutoRefreshTimer = setInterval(() => {
        autoRefreshAdministradoSales();
    }, ADMINISTRADO_AUTO_REFRESH_MS);
}

function stopAdministradoAutoRefresh() {
    if (!administradoAutoRefreshTimer) {
        return;
    }
    clearInterval(administradoAutoRefreshTimer);
    administradoAutoRefreshTimer = null;
}

function updateAdministradoForm() {
    const config = administradoConfig || {};
    document.getElementById('adm-enabled').checked = config.enabled === true;
    document.getElementById('adm-sales-url').value = config.sales_url || 'https://www.administrado.net/seller/ventas3';
    document.getElementById('adm-default-copies').value = config.default_copies || 1;
    document.getElementById('adm-pdf-render-dpi').value = config.pdf_render_dpi || 300;
    document.getElementById('adm-auto-crop-pdf').checked = config.auto_crop_pdf !== false;
    document.getElementById('adm-raw-zpl-labels').checked = config.use_raw_zpl_for_labels !== false;
    document.getElementById('adm-cookie-header').value = '';

    const configured = config.configured === true;
    const status = document.getElementById('adm-configured-status');
    status.textContent = configured ? 'Configurado' : 'Pendiente';
    status.className = `status ${configured ? 'enabled' : 'disabled'}`;
    document.getElementById('adm-playwright-session').textContent = config.playwright_session ? 'Guardada' : 'No';
    document.getElementById('adm-config-path').textContent = config.config_path || '-';
    document.getElementById('adm-storage-path').textContent = config.storage_state_path || '-';
    document.getElementById('adm-last-error').textContent = compactErrorText(config.last_error);
}

async function loadAdministradoConfig() {
    const response = await fetchAPI('/api/administrado/config');
    administradoConfig = response || {};
    updateAdministradoForm();
}

async function saveAdministradoConfig() {
    const odooLabelPrimary = (document.getElementById('odoo-label-printer-primary')?.value || '').trim();
    const odooLabelFallback = (document.getElementById('odoo-label-printer-fallback')?.value || '').trim();
    const config = {
        enabled: document.getElementById('adm-enabled').checked,
        base_url: 'https://www.administrado.net',
        sales_url: document.getElementById('adm-sales-url').value.trim(),
        cookie_header: document.getElementById('adm-cookie-header').value.trim(),
        default_printer: (odooLabelPrimary || odooLabelFallback || (administradoConfig.default_printer || '')).trim(),
        default_copies: parseInt(document.getElementById('adm-default-copies').value, 10) || 1,
        pdf_render_dpi: parseInt(document.getElementById('adm-pdf-render-dpi').value, 10) || 300,
        auto_crop_pdf: document.getElementById('adm-auto-crop-pdf').checked,
        use_raw_zpl_for_labels: document.getElementById('adm-raw-zpl-labels').checked
    };

    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/administrado/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (response.ok) {
            administradoConfig = await response.json();
            await loadAdministradoConfig();
            alert('OK: Configuracion de Administrado guardada');
        } else {
            const error = await response.text();
            alert(`Error guardando Administrado: ${response.status}`);
            console.error(error);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function testAdministradoSession() {
    try {
        await saveAdministradoConfig();
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/administrado/session/test`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert(result.ok ? `Sesion valida (${result.status_code})` : `Sesion no valida. URL final: ${result.final_url}`);
        } else {
            alert(`Error probando sesion: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function importAdministradoCookies(browser) {
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/administrado/cookies/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ browser, profile: '' })
        });
        const result = await response.json();
        if (response.ok) {
            await loadAdministradoConfig();
            alert(`Cookies importadas desde ${result.browser} (${result.profile})`);
        } else {
            alert(`Error importando cookies: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function captureAdministradoPlaywrightSession() {
    try {
        const apiBase = await ensureApiPort();
        alert('Se abrira un navegador controlado. Inicia sesion en Administrado y espera a que la ventana se cierre sola.');
        const response = await fetch(`${apiBase}/api/administrado/playwright/capture-session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timeout_seconds: 600 })
        });
        const result = await response.json();
        if (response.ok) {
            await loadAdministradoConfig();
            alert('Sesion de Playwright guardada correctamente');
        } else {
            alert(`Error capturando sesion: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

function isAdministradoSalePrinted(sale) {
    return sale?.print_mode === 'reimprimir';
}

function setAdministradoFilter(filter) {
    administradoFilter = ['pending', 'printed', 'all'].includes(filter) ? filter : 'all';
    try {
        localStorage.setItem(ADMINISTRADO_FILTER_STORAGE_KEY, administradoFilter);
    } catch (e) {
        // Ignorar si localStorage no esta disponible.
    }
    renderAdministradoSales();
}

function toggleAdministradoRowDetails(envioId, open) {
    if (open) administradoOpenDetails.add(String(envioId));
    else administradoOpenDetails.delete(String(envioId));
}

function updateAdministradoFilterTabs() {
    const pending = administradoSales.filter((sale) => !isAdministradoSalePrinted(sale)).length;
    const counts = { pending, printed: administradoSales.length - pending, all: administradoSales.length };
    Object.entries(counts).forEach(([key, value]) => {
        const el = document.getElementById(`adm-count-${key}`);
        if (el) {
            el.textContent = value;
            el.classList.toggle('has-items', value > 0);
        }
    });
    document.querySelectorAll('[data-adm-filter]').forEach((tab) => {
        const active = tab.dataset.admFilter === administradoFilter;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
}

function renderAdministradoStockStatus(sale) {
    const stock = sale && sale.odoo_stock ? sale.odoo_stock : {};
    const code = String(stock.code || 'unknown').toLowerCase();
    const statusClass = {
        ready: 'ready',
        done: 'completed',
        partial: 'pending',
        waiting: 'pending',
        waiting_operation: 'processing',
        draft: 'not-ready',
        quotation: 'not-ready',
        no_picking: 'not-ready',
        order_missing: 'not-ready',
        cancelled: 'failed',
        error: 'failed',
        unavailable: '',
        unknown: ''
    }[code] || '';
    const label = escapeHtml(stock.label || 'Stock sin datos');
    const detail = escapeHtml(stock.detail || 'Sin informacion adicional.');
    const pickings = Array.isArray(stock.pickings) ? stock.pickings : [];
    const pickingNames = pickings
        .map((picking) => String(picking && picking.name || '').trim())
        .filter(Boolean)
        .slice(0, 2)
        .map(escapeHtml)
        .join(' · ');
    const shortages = (Array.isArray(stock.shortages) ? stock.shortages : [])
        .slice(0, 2)
        .map((item) => {
            const product = escapeHtml(item && item.product || 'Producto');
            const missing = Number(item && item.missing_qty || 0).toLocaleString();
            const uom = escapeHtml(item && item.uom || '');
            return `${product}: faltan ${missing}${uom ? ` ${uom}` : ''}`;
        })
        .join(' · ');
    return `<div class="stock-cell">
        <span class="status ${statusClass}">${label}</span>
        ${pickingNames ? `<span class="stock-picking">${pickingNames}</span>` : ''}
        <span class="stock-detail">${detail}</span>
        ${shortages ? `<span class="stock-shortage">${shortages}</span>` : ''}
    </div>`;
}

function renderAdministradoSaleStatus(sale) {
    if (sale._printing) {
        return `<span class="status processing is-printing">${sale._printing_label || 'Procesando...'}</span><br><small>No cierres esta ventana</small>`;
    }
    // La etiqueta pudo imprimirse directo en Administrado (sin pasar por la app):
    // en ese caso manda Administrado, no el historial local.
    const printedOutsideApp = isAdministradoSalePrinted(sale)
        && (!sale._last_print_result || sale._last_success === false);
    if (printedOutsideApp) {
        const lastAppAttempt = sale._last_print_result
            ? `<small>Ultimo intento desde la app: ${sale._last_print_result} (${formatTime(sale._last_print_at)})</small>`
            : '';
        return `<span class="status completed">Impresa en Administrado</span>
            <span class="status-time">Sin registro de impresion en esta app</span>
            <details class="row-details" ${administradoOpenDetails.has(String(sale.envio_id)) ? 'open' : ''} ontoggle="toggleAdministradoRowDetails('${sale.envio_id}', this.open)">
                <summary>Detalle</summary>
                <div>
                    <small>La etiqueta se imprimio fuera de la app, asi que la orden de Odoo no se imprimio ni se confirmo desde aca. Si hace falta, usa "Solo orden Odoo".</small>
                    ${lastAppAttempt ? `<br>${lastAppAttempt}` : ''}
                    ${sale._last_error ? `<br><small class="error-text">${compactErrorText(sale._last_error, 180)}</small>` : ''}
                </div>
            </details>`;
    }
    if (!sale._last_print_result) {
        return '<span class="status pending">Pendiente</span>';
    }
    const detailLines = [
        sale._last_print_actor ? `Usuario: ${sale._last_print_actor}` : '',
        sale._last_order_printer ? `Orden: ${sale._last_order_printer}` : '',
        sale._last_label_printer ? `Etiqueta: ${sale._last_label_printer}` : '',
        sale._last_confirm_state_before || sale._last_confirm_state_after
            ? `Estado Odoo: ${sale._last_confirm_state_before || '-'} -> ${sale._last_confirm_state_after || '-'}`
            : ''
    ].filter(Boolean);
    const detailOpen = administradoOpenDetails.has(String(sale.envio_id)) ? 'open' : '';
    return `<span class="status ${sale._last_success === false ? 'disabled' : 'enabled'}">${sale._last_print_result}</span>
        <span class="status-time">${formatTime(sale._last_print_at)}</span>
        ${sale._last_error ? `<small class="error-text">${compactErrorText(sale._last_error, 180)}</small>` : ''}
        ${detailLines.length
            ? `<details class="row-details" ${detailOpen} ontoggle="toggleAdministradoRowDetails('${sale.envio_id}', this.open)">
                   <summary>Detalle</summary>
                   <div>${detailLines.map((line) => `<small>${line}</small>`).join('<br>')}</div>
               </details>`
            : ''}`;
}

function renderAdministradoSales() {
    const tbody = document.getElementById('adm-sales-body');
    const summary = document.getElementById('adm-sync-summary');
    updateAdministradoFilterTabs();
    if (!administradoSales.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">Sincroniza para ver etiquetas detectadas</td></tr>';
        summary.textContent = 'Sin datos';
        summary.classList.add('is-empty');
        return;
    }
    summary.textContent = `${administradoSales.length} etiquetas detectadas`;
    summary.classList.remove('is-empty');
    // Pendientes primero, respetando el orden original dentro de cada grupo.
    const visibleSales = administradoSales
        .map((sale, index) => ({ sale, index }))
        .filter(({ sale }) => {
            if (administradoFilter === 'pending') return !isAdministradoSalePrinted(sale) || sale._printing;
            if (administradoFilter === 'printed') return isAdministradoSalePrinted(sale) || sale._printing;
            return true;
        })
        .sort((a, b) => (
            Number(isAdministradoSalePrinted(a.sale)) - Number(isAdministradoSalePrinted(b.sale))
            || a.index - b.index
        ))
        .map(({ sale }) => sale);
    if (!visibleSales.length) {
        const emptyText = administradoFilter === 'pending'
            ? 'No hay envios pendientes de imprimir.'
            : 'Todavia no hay envios impresos en esta lista.';
        tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">${emptyText}</td></tr>`;
        return;
    }
    tbody.innerHTML = visibleSales.map(sale => `
        <tr class="${isAdministradoSalePrinted(sale) ? 'is-printed' : 'is-pending'}">
            <td><span class="mono-id">${sale.envio_id}</span></td>
            <td>
                <span class="customer-name">${sale.customer_name || '-'}</span>
                <span class="customer-user">${sale.customer_username ? '@' + sale.customer_username : '-'}</span>
            </td>
            <td>${renderAdministradoStockStatus(sale)}</td>
            <td>
                <div class="action-stack">
                <button class="btn success sm" ${sale._printing ? 'disabled' : ''} onclick="printAdministradoShipment('${sale.envio_id}', 'both')">
                    ${sale.print_mode === 'reimprimir' ? 'Reimprimir orden + etiqueta' : 'Imprimir orden + etiqueta'}
                </button>
                ${sale.print_mode === 'reimprimir'
                    ? `
                        <button class="btn sm" ${sale._printing ? 'disabled' : ''} onclick="printAdministradoShipment('${sale.envio_id}', 'order_only')">Solo orden Odoo</button>
                        <button class="btn sm" ${sale._printing ? 'disabled' : ''} onclick="printAdministradoShipment('${sale.envio_id}', 'label_only')">Solo etiqueta</button>
                      `
                    : ''
                }
                <button type="button" class="btn-link-odoo" onclick="openOdooOrderForEnvio('${sale.envio_id}', this)">Abrir orden en Odoo ↗</button>
                </div>
            </td>
            <td class="status-cell">
                ${renderAdministradoSaleStatus(sale)}
            </td>
        </tr>
    `).join('');
}

function formatTime(value) {
    if (!value) return '-';
    try {
        return new Date(value).toLocaleString();
    } catch (error) {
        return String(value);
    }
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

async function syncAdministradoSales(options = {}) {
    const silent = Boolean(options.silent);
    if (administradoSyncInProgress) {
        return;
    }
    administradoSyncInProgress = true;
    const summary = document.getElementById('adm-sync-summary');
    const syncBtn = document.getElementById('adm-sync-btn');
    if (summary) {
        summary.textContent = 'Sincronizando...';
        summary.classList.remove('is-empty');
    }
    if (syncBtn) {
        syncBtn.disabled = true;
    }
    try {
        const apiBase = await ensureApiPort();
        const limit = parseInt(document.getElementById('adm-sync-limit').value, 10) || 20;
        const response = await fetch(`${apiBase}/api/administrado/sales/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit })
        });
        const result = await response.json();
        if (response.ok) {
            administradoSales = result.sales || [];
            administradoLastSync = { ok: true, at: new Date(), error: '' };
            renderAdministradoSales();
        } else {
            administradoSales = [];
            administradoLastSync = { ok: false, at: new Date(), error: String(result.detail || response.status) };
            renderAdministradoSales();
            if (!silent) {
                alert(`Error sincronizando Administrado: ${result.detail || response.status}`);
            }
        }
    } catch (error) {
        administradoSales = [];
        administradoLastSync = { ok: false, at: new Date(), error: String(error.message || 'Error de conexion') };
        renderAdministradoSales();
        if (!silent) {
            alert(`Error de conexion: ${error.message}`);
        }
    } finally {
        administradoSyncInProgress = false;
        if (syncBtn) {
            syncBtn.disabled = false;
        }
        renderHealthBar();
    }
}

async function printAdministradoLabel() {
    const envioId = document.getElementById('adm-test-envio-id').value.trim();
    if (!envioId) {
        alert('Ingresa un envio ID');
        return;
    }
    await printAdministradoShipment(envioId, 'label_only');
}

async function printAdministradoShipment(envioId, mode = 'both') {
    const safeEnvioId = String(envioId || '').trim();
    if (!safeEnvioId) {
        alert('Envio invalido');
        return;
    }
    if (administradoPrintInFlight.has(safeEnvioId)) {
        alert(`El envio ${safeEnvioId} ya se esta procesando. Espera unos segundos.`);
        return;
    }
    const modeTextMap = {
        both: 'Orden + etiqueta',
        label_only: 'Solo etiqueta',
        order_only: 'Solo orden Odoo'
    };
    const targetSale = administradoSales.find((sale) => String(sale.envio_id) === safeEnvioId);
    const printOperationId = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : `print-${Date.now()}-${Math.random().toString(16).slice(2)}`;

    try {
        const apiBase = await ensureApiPort();
        const selectedOrderPrinter = (
            (document.getElementById('odoo-order-printer-primary')?.value || '').trim()
        );
        const selectedLabelPrinter = (
            (document.getElementById('odoo-label-printer-primary')?.value || '').trim() ||
            (document.getElementById('odoo-label-printer-fallback')?.value || '').trim() ||
            (administradoConfig.default_printer || '').trim()
        );
        const appUsername = (localStorage.getItem('username') || '').trim();
        const modeText = modeTextMap[mode] || mode;

        const printDetails = [
            ['Envio', safeEnvioId],
            ['Accion', modeText]
        ];
        if (mode !== 'label_only') {
            printDetails.push(['Impresora orden', selectedOrderPrinter || '(default configurada)']);
        }
        if (mode !== 'order_only') {
            printDetails.push(['Impresora etiqueta', selectedLabelPrinter || '(default configurada)']);
        }
        printDetails.push(['Usuario app', appUsername || '-']);
        const printWarnings = [];
        if (mode !== 'label_only') {
            const odooActor = resolveOdooActorForPrint(appUsername);
            printDetails.push(['Usuario Odoo', odooActor.username || '(sin usuario)']);
            const stock = targetSale && targetSale.odoo_stock ? targetSale.odoo_stock : {};
            const stockCode = String(stock.code || 'unknown').toLowerCase();
            printDetails.push(['Stock / entrega', stock.label || 'Sin datos']);
            if (!['ready', 'done'].includes(stockCode)) {
                printWarnings.push(
                    `Odoo informa: ${stock.label || 'stock sin datos'}. ${stock.detail || ''}`.trim()
                );
            }
            if (odooConfig.confirm_order_on_print === true && odooActor.source !== 'mapped') {
                printWarnings.push(
                    odooActor.source === 'single'
                        ? `El operador no tiene usuario Odoo propio: la cotizacion se confirmara como ${odooActor.username}.`
                        : `El operador no tiene usuario Odoo mapeado: la cotizacion se confirmara con el usuario general (${odooActor.username || 'sin definir'}).`
                );
            }
            if (!selectedOrderPrinter) {
                printWarnings.push('No hay impresora de orden seleccionada: se usara la configurada en el servidor.');
            }
        }
        if (mode !== 'order_only' && !selectedLabelPrinter) {
            printWarnings.push('No hay impresora de etiqueta seleccionada: se usara la configurada en el servidor.');
        }
        if (!appUsername) {
            printWarnings.push('No hay operador identificado en esta PC (Usuario app vacio).');
        }
        const confirmed = await uiConfirm({
            tone: 'print',
            title: 'Confirmar impresion',
            message: 'Vas a enviar a imprimir:',
            details: printDetails,
            warnings: printWarnings,
            confirmText: printWarnings.length ? 'Imprimir igual' : 'Imprimir'
        });
        if (!confirmed) {
            return;
        }

        administradoPrintInFlight.add(safeEnvioId);
        if (targetSale) {
            targetSale._printing = true;
            targetSale._printing_label = `Procesando solicitud… (puede tardar) • ${modeText}`;
            renderAdministradoSales();
        }

        // Mensaje extra si el backend tarda (evita sensación de “se colgó”)
        setTimeout(() => {
            if (!administradoPrintInFlight.has(safeEnvioId)) return;
            if (targetSale) {
                targetSale._printing_label = `Enviando a impresoras y/o esperando Odoo… (no está colgado) • ${modeText}`;
                renderAdministradoSales();
            }
        }, 4500);

        const response = await fetch(`${apiBase}/api/administrado/shipments/print`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                envio_id: safeEnvioId,
                mode,
                operation_id: printOperationId,
                app_username: appUsername,
                order_printer: selectedOrderPrinter,
                label_printer: selectedLabelPrinter
            })
        });
        const result = await response.json();
        if (response.ok) {
            const orderPrinter = result.order_result && result.order_result.printer
                ? result.order_result.printer
                : '-';
            const labelPrinter = result.label_result && result.label_result.printer
                ? result.label_result.printer
                : '-';
            if (targetSale) {
                targetSale._last_print_at = new Date().toISOString();
                targetSale._last_print_result = modeText;
                targetSale._last_success = true;
                targetSale._last_print_actor = result.odoo_actor || appUsername || '';
                targetSale._last_order_printer = orderPrinter !== '-' ? orderPrinter : '';
                targetSale._last_label_printer = labelPrinter !== '-' ? labelPrinter : '';
                targetSale._last_error = '';
                const confirmResult = result.confirm_result || {};
                targetSale._last_confirm_state_before = confirmResult.state_before || '';
                targetSale._last_confirm_state_after = confirmResult.state_after || '';
                if (mode === 'both') {
                    targetSale.print_mode = 'reimprimir';
                }
                targetSale._printing = false;
                targetSale._printing_label = '';
                renderAdministradoSales();
            }

            const confirmInfo = result.confirm_result
                ? ` | Odoo: ${result.confirm_result.state_before || '-'} -> ${result.confirm_result.state_after || '-'}`
                : '';
            const noteResult = result.odoo_note_result || null;
            uiToast(
                [
                    `${modeText} enviado para ${safeEnvioId}`,
                    `Orden: ${orderPrinter} · Etiqueta: ${labelPrinter}`,
                    `Actor: ${result.odoo_actor || appUsername || '-'}${confirmInfo}`
                ].join('\n'),
                'success',
                { title: 'Impresion enviada', duration: 7000 }
            );
            if (noteResult && noteResult.success === false) {
                uiToast(
                    `La impresion fue correcta, pero no se pudo registrar la nota en Odoo: ${noteResult.error || 'sin detalle'}`,
                    'info',
                    { title: 'Registro Odoo pendiente', duration: 8000 }
                );
            }
        } else {
            if (targetSale) {
                targetSale._printing = false;
                targetSale._printing_label = '';
                targetSale._last_success = false;
                targetSale._last_print_result = `ERROR: ${modeText}`;
                targetSale._last_error = compactErrorText(result.detail || `HTTP ${response.status}`, 180);
                targetSale._last_print_at = new Date().toISOString();
                renderAdministradoSales();
            }
            alert(`Error imprimiendo envio: ${result.detail || response.status}`);
        }
    } catch (error) {
        const targetSale = administradoSales.find((sale) => String(sale.envio_id) === String(safeEnvioId));
        if (targetSale) {
            targetSale._printing = false;
            targetSale._printing_label = '';
            targetSale._last_success = false;
            targetSale._last_print_result = `ERROR: ${(modeTextMap[mode] || mode)}`;
            targetSale._last_error = compactErrorText(error.message || 'Error de conexion', 180);
            targetSale._last_print_at = new Date().toISOString();
            renderAdministradoSales();
        }
        alert(`Error de conexion: ${error.message}`);
    } finally {
        administradoPrintInFlight.delete(safeEnvioId);
    }
}

// ---- Usuario Odoo que usara el backend al imprimir (espejo de resolve_operator_auth) ----
function resolveOdooActorForPrint(appUsername) {
    const items = Array.isArray(odooOperatorUsers) ? odooOperatorUsers : [];
    const isValid = (item) => Boolean(String(item?.odoo_username || '').trim() && item?.has_password);
    const general = { username: String(odooConfig.username || '').trim(), source: 'general' };
    const key = String(appUsername || '').trim().toLowerCase();
    if (key) {
        const keyed = items.find((item) => String(item?.app_username || '').trim().toLowerCase() === key);
        if (keyed) {
            return isValid(keyed)
                ? { username: String(keyed.odoo_username).trim(), source: 'mapped' }
                : general;
        }
    }
    const valid = items.filter(isValid);
    if (valid.length === 1) {
        return { username: String(valid[0].odoo_username).trim(), source: 'single' };
    }
    return general;
}

// ---- Abrir la orden de venta de Odoo que corresponde al envio ----
const odooOrderUrlCache = new Map();

async function openOdooOrderForEnvio(envioId, button) {
    const id = String(envioId || '').trim();
    if (!id) return;
    // La pestaña se abre ya, dentro del clic: si se abre despues del fetch el navegador la bloquea.
    const tab = window.open('', '_blank');
    if (tab) {
        tab.opener = null;
        tab.document.title = 'Buscando orden en Odoo...';
        tab.document.body.innerHTML = '<p style="font-family:sans-serif;padding:24px;color:#444">Buscando la orden de venta en Odoo...</p>';
    }
    const navigate = (url) => {
        if (tab && !tab.closed) tab.location.replace(url);
        else window.open(url, '_blank', 'noopener');
    };
    const cached = odooOrderUrlCache.get(id);
    if (cached) {
        navigate(cached);
        return;
    }
    const originalText = button ? button.textContent : '';
    if (button) {
        button.disabled = true;
        button.textContent = 'Buscando en Odoo...';
    }
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/orders/find`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ envio_id: id, include_all_states: true })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || `HTTP ${response.status}`);
        }
        const order = result.order || null;
        // Si la API todavia no devuelve "url" (backend sin reiniciar), se arma con la URL configurada.
        const baseUrl = String(odooConfig.base_url || '').trim().replace(/\/+$/, '');
        const url = result.url
            || (order && baseUrl ? `${baseUrl}/web#id=${order.id}&model=sale.order&view_type=form` : '');
        if (!result.found || !url) {
            if (tab && !tab.closed) tab.close();
            uiToast(
                `No se encontro una orden de venta en Odoo para el envio ${id}.\n`
                + 'Revisa el prefijo de orden o el campo shipment en la configuracion de Odoo.',
                'info',
                { title: 'Orden no encontrada' }
            );
            return;
        }
        odooOrderUrlCache.set(id, url);
        navigate(url);
        if (order?.name) {
            uiToast(`Abriendo ${order.name} en Odoo.`, 'success', { duration: 3000 });
        }
    } catch (error) {
        if (tab && !tab.closed) tab.close();
        uiToast(`No se pudo buscar la orden en Odoo: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}
