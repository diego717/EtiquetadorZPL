// Mercado Libre: configuracion, OAuth, ventas e impresion.

let mercadoLibreConfig = {};
let mercadoLibreSales = [];
let mercadoLibrePayments = [];
let mercadoLibrePaymentJournals = [];
let mercadoLibrePaymentOperators = [];

function escapeMercadoLibreHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatMercadoLibreAmount(value, currency) {
    const amount = Number(value || 0);
    return `${new Intl.NumberFormat('es-UY', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)} ${currency || ''}`.trim();
}

function updateMercadoLibreForm() {
    const config = mercadoLibreConfig || {};

    document.getElementById('meli-enabled').checked = config.enabled === true;
    document.getElementById('meli-client-id').value = config.client_id && config.client_id !== '***' ? config.client_id : '';
    document.getElementById('meli-client-secret').value = '';
    document.getElementById('meli-redirect-uri').value = config.redirect_uri || 'http://localhost:8002/api/mercadolibre/oauth/callback';
    document.getElementById('meli-access-token').value = '';
    document.getElementById('meli-refresh-token').value = '';
    document.getElementById('meli-access-token').placeholder = config.has_access_token ? 'Guardado (dejar vacio para conservar)' : 'APP_USR-...';
    document.getElementById('meli-refresh-token').placeholder = config.has_refresh_token ? 'Guardado (dejar vacio para conservar)' : 'TG-...';
    document.getElementById('meli-expires-in').value = '';
    document.getElementById('meli-manual-user-id').value = config.user_id || '';
    document.getElementById('meli-default-printer').value = config.default_printer || '';
    document.getElementById('meli-default-copies').value = config.default_copies || 1;
    document.getElementById('meli-auto-print').checked = config.auto_print === true;

    const configured = config.configured === true;
    const authenticated = config.authenticated === true;

    const configuredStatus = document.getElementById('meli-configured-status');
    configuredStatus.textContent = configured ? 'Configurado' : 'Pendiente';
    configuredStatus.className = `status ${configured ? 'enabled' : 'disabled'}`;

    const authStatus = document.getElementById('meli-auth-status');
    authStatus.textContent = authenticated ? 'Autenticado' : 'Sin autenticar';
    authStatus.className = `status ${authenticated ? 'enabled' : 'disabled'}`;

    document.getElementById('meli-user-id').textContent = config.user_id || '-';
    document.getElementById('meli-nickname').textContent = config.nickname || '-';
    document.getElementById('meli-access-token-status').textContent = config.has_access_token ? 'Guardado' : 'Faltante';
    document.getElementById('meli-refresh-token-status').textContent = config.has_refresh_token ? 'Guardado' : 'Faltante';
    const expiresAt = Number(config.expires_at || 0);
    document.getElementById('meli-token-expiry').textContent = expiresAt > 0
        ? new Date(expiresAt * 1000).toLocaleString()
        : (config.has_access_token ? 'No informado' : '-');
    document.getElementById('meli-config-path').textContent = config.config_path || '-';
    document.getElementById('meli-last-error').textContent = compactErrorText(config.last_error);
}

async function loadMercadoLibreConfig() {
    const response = await fetchAPI('/api/mercadolibre/config');
    if (response) {
        mercadoLibreConfig = response;
    } else {
        mercadoLibreConfig = {};
    }
    updateMercadoLibreForm();
    await loadMercadoLibrePaymentOptions();
}

async function refreshMercadoLibreStatus() {
    await loadMercadoLibreConfig();
}

async function saveMercadoLibreConfig() {
    const expiresInText = document.getElementById('meli-expires-in').value.trim();
    const userIdText = document.getElementById('meli-manual-user-id').value.trim();
    const config = {
        enabled: document.getElementById('meli-enabled').checked,
        client_id: document.getElementById('meli-client-id').value.trim(),
        client_secret: document.getElementById('meli-client-secret').value.trim(),
        redirect_uri: document.getElementById('meli-redirect-uri').value.trim(),
        access_token: document.getElementById('meli-access-token').value.trim(),
        refresh_token: document.getElementById('meli-refresh-token').value.trim(),
        expires_in: expiresInText ? parseInt(expiresInText, 10) : null,
        user_id: userIdText ? parseInt(userIdText, 10) : null,
        default_printer: document.getElementById('meli-default-printer').value.trim(),
        default_copies: parseInt(document.getElementById('meli-default-copies').value, 10) || 1,
        auto_print: document.getElementById('meli-auto-print').checked,
        response_type: 'zpl2'
    };

    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/mercadolibre/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            mercadoLibreConfig = await response.json();
            updateMercadoLibreForm();
            if (config.access_token && mercadoLibreConfig.has_access_token !== true) {
                alert('La pantalla esta actualizada, pero la API sigue usando la version anterior. Reinicia EtiquetadorZPL y vuelve a guardar los tokens.');
            } else {
                alert('OK: Configuracion de Mercado Libre guardada');
            }
        } else {
            const error = await response.text();
            alert(`Error guardando Mercado Libre: ${response.status}`);
            console.error('Error Mercado Libre:', error);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function startMercadoLibreOAuth() {
    try {
        await saveMercadoLibreConfig();
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/mercadolibre/auth-url?state=web-config`);
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const data = await response.json();
        if (!data.auth_url) {
            throw new Error('La API no devolvio auth_url');
        }

        window.open(data.auth_url, '_blank');
    } catch (error) {
        alert(`Error iniciando OAuth: ${error.message}`);
    }
}

async function testMercadoLibrePrint() {
    const shipmentId = document.getElementById('meli-test-shipment-id').value.trim();
    if (!shipmentId) {
        alert('Ingresa un shipment ID');
        return;
    }
    const meliPrinter = document.getElementById('meli-default-printer').value.trim();
    const meliCopies = parseInt(document.getElementById('meli-default-copies').value, 10) || 1;
    const confirmed = await uiConfirm({
        tone: 'print',
        title: 'Confirmar impresion',
        message: 'Vas a enviar a imprimir la etiqueta de Mercado Libre:',
        details: [
            ['Shipment', shipmentId],
            ['Impresora', meliPrinter || '(default configurada)'],
            ['Copias', String(meliCopies)]
        ],
        confirmText: 'Imprimir'
    });
    if (!confirmed) {
        return;
    }

    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/mercadolibre/shipments/print`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shipment_id: shipmentId,
                printer: document.getElementById('meli-default-printer').value.trim(),
                copies: parseInt(document.getElementById('meli-default-copies').value, 10) || 1,
                response_type: 'zpl2'
            })
        });

        const result = await response.json();
        if (response.ok) {
            alert(`OK: Etiqueta enviada. Job ${result.print_job?.job_id || '-'}`);
        } else {
            alert(`Error imprimiendo shipment: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

function renderMercadoLibreSales() {
    const tbody = document.getElementById('meli-sales-body');
    const summary = document.getElementById('meli-sync-summary');

    if (!mercadoLibreSales.length) {
        tbody.innerHTML = '<tr><td colspan="7">Sincroniza para ver ventas</td></tr>';
        summary.textContent = 'Sin datos';
        summary.classList.add('is-empty');
        return;
    }

    const readyCount = mercadoLibreSales.filter(sale => sale.ready_to_print).length;
    summary.textContent = `${readyCount} listas de ${mercadoLibreSales.length} ventas revisadas`;
    summary.classList.remove('is-empty');

    tbody.innerHTML = mercadoLibreSales.map(sale => `
        <tr>
            <td>${sale.order_id || '-'}</td>
            <td>${sale.shipment_id || '-'}</td>
            <td>${sale.buyer || '-'}</td>
            <td>${sale.title || '-'}</td>
            <td>${sale.shipment_status || '-'} ${sale.shipment_substatus ? `(${sale.shipment_substatus})` : ''}</td>
            <td><span class="status ${sale.ready_to_print ? 'ready' : 'not-ready'}">${sale.ready_to_print ? 'Si' : 'No'}</span></td>
            <td>
                ${sale.ready_to_print ? `<button class="btn success" onclick="printSyncedShipment('${sale.shipment_id}')">Imprimir</button>` : (sale.error || '-')}
                ${sale.shipment_id ? `<br><button type="button" class="btn-link-odoo" onclick="openOdooOrderForEnvio('${sale.shipment_id}', this)">Abrir orden en Odoo ↗</button>` : ''}
            </td>
        </tr>
    `).join('');
}

async function syncMercadoLibreSales() {
    try {
        const apiBase = await ensureApiPort();
        const limit = parseInt(document.getElementById('meli-sync-limit').value, 10) || 20;
        const response = await fetch(`${apiBase}/api/mercadolibre/sales/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit })
        });

        const result = await response.json();
        if (response.ok) {
            mercadoLibreSales = result.sales || [];
            renderMercadoLibreSales();
        } else {
            mercadoLibreSales = [];
            renderMercadoLibreSales();
            alert(`Error sincronizando ventas: ${result.detail || response.status}`);
        }
    } catch (error) {
        mercadoLibreSales = [];
        renderMercadoLibreSales();
        alert(`Error de conexion: ${error.message}`);
    }
}

async function printSyncedShipment(shipmentId) {
    document.getElementById('meli-test-shipment-id').value = shipmentId;
    await testMercadoLibrePrint();
}

async function loadMercadoLibrePaymentOptions() {
    const operatorSelect = document.getElementById('meli-payment-operator');
    const journalSelect = document.getElementById('meli-payment-journal');
    if (!operatorSelect || !journalSelect) return;

    const previousOperator = operatorSelect.value;
    const previousJournal = journalSelect.value;
    const roundingSelect = document.getElementById('meli-payment-rounding-account');
    const previousRounding = roundingSelect?.value || '';
    const response = await fetchAPI('/api/mercadolibre/payments/options');
    mercadoLibrePaymentOperators = response?.operators || [];
    mercadoLibrePaymentJournals = response?.journals || [];

    operatorSelect.replaceChildren(new Option('Selecciona quien registra', ''));
    mercadoLibrePaymentOperators.forEach((operator) => {
        const label = operator.odoo_username
            ? `${operator.app_username} (${operator.odoo_username})`
            : operator.app_username;
        operatorSelect.add(new Option(label, operator.app_username));
    });
    operatorSelect.disabled = mercadoLibrePaymentOperators.length === 0;
    if (mercadoLibrePaymentOperators.some(item => item.app_username === previousOperator)) {
        operatorSelect.value = previousOperator;
    }

    journalSelect.replaceChildren(new Option('Selecciona el diario', ''));
    mercadoLibrePaymentJournals.forEach((journal) => {
        const currency = Array.isArray(journal.currency_id) ? journal.currency_id[1] : '';
        journalSelect.add(new Option(`${journal.name}${currency ? ` (${currency})` : ''}`, String(journal.id)));
    });
    journalSelect.disabled = mercadoLibrePaymentJournals.length === 0;
    if (mercadoLibrePaymentJournals.some(item => String(item.id) === previousJournal)) {
        journalSelect.value = previousJournal;
    } else {
        const mercadoPagoJournal = mercadoLibrePaymentJournals.find(item => /mercado\s*pago/i.test(item.name || ''));
        if (mercadoPagoJournal) journalSelect.value = String(mercadoPagoJournal.id);
    }

    if (!roundingSelect) return;
    const roundingAccounts = response?.rounding_accounts || [];
    roundingSelect.replaceChildren(new Option('Selecciona la cuenta de redondeo', ''));
    roundingAccounts.forEach((account) => {
        roundingSelect.add(new Option(`${account.code || ''} - ${account.name}`.replace(/^ - /, ''), String(account.id)));
    });
    roundingSelect.disabled = roundingAccounts.length === 0;
    if (roundingAccounts.some(item => String(item.id) === previousRounding)) {
        roundingSelect.value = previousRounding;
    } else {
        // Misma cuenta sugerida que Conciliacion POS.
        const suggested = roundingAccounts.find(item => /^redondeos$/i.test(
            String(item.name || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim()
        ));
        if (suggested) roundingSelect.value = String(suggested.id);
    }
}

function renderMercadoLibrePayments() {
    const tbody = document.getElementById('meli-payments-body');
    const summary = document.getElementById('meli-payment-summary');
    if (!tbody || !summary) return;

    if (!mercadoLibrePayments.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No hay pagos para mostrar</td></tr>';
        summary.textContent = 'Sin datos';
        summary.classList.add('is-empty');
        return;
    }

    const ready = mercadoLibrePayments.filter(item => item.can_register).length;
    const registered = mercadoLibrePayments.filter(item => item.registered).length;
    summary.textContent = `${ready} listos${registered ? ` · ${registered} registrados` : ''} de ${mercadoLibrePayments.length}`;
    summary.classList.remove('is-empty');

    tbody.innerHTML = mercadoLibrePayments.map((item) => {
        const orderId = escapeMercadoLibreHtml(item.order_id || '');
        const reference = escapeMercadoLibreHtml(item.reference || '');
        const orderTitle = escapeMercadoLibreHtml(item.pack_id
            ? `Pack ${item.pack_id} - ordenes: ${(item.order_ids || []).join(', ')}`
            : `Orden ${item.order_id || ''}`);
        const amountTitle = escapeMercadoLibreHtml(item.shipping_amount
            ? `Productos ${formatMercadoLibreAmount(item.products_amount, item.currency)} + envio ${formatMercadoLibreAmount(item.shipping_amount, item.currency)}`
            : '');
        const invoice = item.invoice || {};
        const invoiceName = escapeMercadoLibreHtml(invoice.name || '-');
        const paymentReference = escapeMercadoLibreHtml(item.payment_reference || '-');
        const registered = item.registered === true;
        const statusText = registered ? 'Registrado y adjuntado' : (item.can_register ? 'Listo para registrar' : (item.reason || 'No disponible'));
        const statusClass = registered ? 'completed' : (item.can_register ? 'ready' : 'pending');
        const paymentUrl = item.registration?.payment_url;
        const invoiceUrl = item.registration?.invoice_url;
        return `
            <tr>
                <td class="mono-id" title="${orderTitle}">${reference || orderId || '-'}</td>
                <td>${escapeMercadoLibreHtml(item.payment_date || '-')}</td>
                <td>${escapeMercadoLibreHtml(item.buyer || '-')}</td>
                <td title="${amountTitle}">${escapeMercadoLibreHtml(formatMercadoLibreAmount(item.amount, item.currency))}</td>
                <td class="mono-id">${paymentReference}</td>
                <td>${invoiceName}</td>
                <td><span class="status ${statusClass}" title="${escapeMercadoLibreHtml(statusText)}">${escapeMercadoLibreHtml(statusText)}</span></td>
                <td class="meli-payment-actions"><div class="meli-payment-actions-inner">
                    ${item.can_register ? `<button type="button" class="btn success sm" data-order-id="${orderId}" onclick="registerMercadoLibrePayment(this.dataset.orderId, this)">Registrar pago</button>` : ''}
                    ${paymentUrl ? `<a class="btn secondary sm" href="${escapeMercadoLibreHtml(paymentUrl)}" target="_blank" rel="noopener noreferrer">Abrir pago ↗</a>` : ''}
                    ${invoiceUrl ? `<a class="btn-link-odoo" href="${escapeMercadoLibreHtml(invoiceUrl)}" target="_blank" rel="noopener noreferrer">Factura ↗</a>` : ''}
                </div></td>
            </tr>
        `;
    }).join('');
}

async function syncMercadoLibrePayments() {
    const summary = document.getElementById('meli-payment-summary');
    if (summary) {
        summary.textContent = 'Buscando...';
        summary.classList.remove('is-empty');
    }
    try {
        await loadMercadoLibrePaymentOptions();
        const apiBase = await ensureApiPort();
        const limit = parseInt(document.getElementById('meli-payment-limit').value, 10) || 20;
        const response = await fetch(`${apiBase}/api/mercadolibre/payments/proposal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
        mercadoLibrePayments = result.items || [];
        renderMercadoLibrePayments();
    } catch (error) {
        mercadoLibrePayments = [];
        renderMercadoLibrePayments();
        alert(`Error buscando pagos de Mercado Libre: ${error.message}`);
    }
}

// ---- Broma al registrar pagos ----
// Tras la confirmacion real aparecen reconfirmaciones graciosas y una carga falsa, y recien
// despues se registra el pago. Cualquier "cancelar" corta todo sin registrar nada.
// Configuracion > Sistema: activar/desactivar y frecuencia (en cada pago o una vez por dia)
// se guardan en el servidor y valen para todos los equipos; "No mostrarla en este equipo"
// es local. Si no se puede consultar el servidor, la broma no se muestra.
const MELI_PRANK_STORAGE_KEY = 'etiquetador_meli_prank_day';
const MELI_PRANK_EXCLUDED_KEY = 'etiquetador_meli_prank_excluded';
const MELI_PRANK_CONFIRMATIONS = [
    {
        title: '¿Lo confirmás de verdad?',
        message: 'Mirá que esta es plata de verdad, no del Estanciero.',
        confirmText: 'Sí, confirmo',
        cancelText: 'Mejor no'
    },
    {
        title: 'Nivel de confianza insuficiente',
        message: 'El sistema detectó un 87 % de seguridad en tu clic. Para registrar pagos necesitamos llegar al 100 %.',
        confirmText: 'Subir al 100 %',
        cancelText: 'Me quedo en 87'
    },
    {
        title: 'Un momento...',
        message: 'Por culpa de la ruedita pasa esto.. que lastima..',
        confirmText: 'Seguir igual',
        cancelText: 'Pobre ruedita'
    },
    {
        title: 'Ahora sí, la posta',
        message: 'Prometemos que esta es la última pregunta. Palabra de sistema.',
        confirmText: 'Registrar de una vez',
        cancelText: 'Ya no confío en vos'
    }
];
const MELI_PRANK_LOADING_STEPS = [
    'Consultando con el contador...',
    'Pidiendo permiso a Mercado Libre...',
    'Contando los billetes...',
    'Despertando a Odoo...'
];

function meliPrankToday() {
    return new Date().toLocaleDateString('en-CA');
}

// Config global (servidor): { enabled, frequency: 'always' | 'daily' }.
async function fetchMercadoLibrePrankConfig() {
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/mercadolibre/pranks`);
        if (!response.ok) return { enabled: false, frequency: 'always', kind: 'confirmations' };
        const data = await response.json();
        return {
            enabled: data.enabled === true,
            frequency: data.frequency === 'daily' ? 'daily' : 'always',
            kind: ['dodge', 'both'].includes(data.kind) ? data.kind : 'confirmations',
        };
    } catch (e) {
        return { enabled: false, frequency: 'always', kind: 'confirmations' };
    }
}

function meliPrankStorageGet(key) {
    try {
        return localStorage.getItem(key);
    } catch (e) {
        return null;
    }
}

function meliPrankStorageSet(key, value) {
    try {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
    } catch (e) {
        // Sin localStorage: el equipo no puede excluirse ni llevar la cuenta diaria.
    }
}

// Exclusion por equipo (este navegador): para que no le salga a quien la configura.
function mercadoLibrePrankExcludedHere() {
    return meliPrankStorageGet(MELI_PRANK_EXCLUDED_KEY) === '1';
}

function mercadoLibrePrankUsedToday() {
    return meliPrankStorageGet(MELI_PRANK_STORAGE_KEY) === meliPrankToday();
}

async function shouldRunMercadoLibrePrank() {
    if (mercadoLibrePrankExcludedHere()) return null;
    const config = await fetchMercadoLibrePrankConfig();
    if (!config.enabled) return null;
    if (config.frequency === 'daily' && mercadoLibrePrankUsedToday()) return null;
    return config;
}

// Estado visible bajo la casilla. La exclusion y la cuenta diaria son de ESTE navegador.
function renderMercadoLibrePrankStatus(config) {
    const status = document.getElementById('meli-prank-status');
    const reset = document.getElementById('meli-prank-reset');
    if (!status) return;
    const excluded = mercadoLibrePrankExcludedHere();
    const usedToday = config.frequency === 'daily' && mercadoLibrePrankUsedToday();
    if (!config.enabled) {
        status.textContent = 'Desactivada: los pagos se registran normal en todos los equipos.';
    } else if (excluded) {
        status.textContent = 'Activa en los demas equipos. En este no sale.';
    } else if (usedToday) {
        status.textContent = 'Activa, pero en este equipo ya salio hoy: vuelve a salir manana.';
    } else {
        status.textContent = config.frequency === 'daily'
            ? 'Activa: sale en el primer pago del dia de cada equipo.'
            : 'Activa: sale en cada pago, en todos los equipos no excluidos.';
    }
    if (reset) reset.hidden = !(config.enabled && !excluded && usedToday);
}

function currentMercadoLibrePrankConfigFromForm() {
    return {
        enabled: document.getElementById('meli-prank-enabled')?.checked === true,
        frequency: document.getElementById('meli-prank-frequency')?.value === 'daily' ? 'daily' : 'always',
        kind: document.getElementById('meli-prank-kind')?.value || 'confirmations',
    };
}

async function loadMercadoLibrePrankSetting() {
    const config = await fetchMercadoLibrePrankConfig();
    const checkbox = document.getElementById('meli-prank-enabled');
    const frequency = document.getElementById('meli-prank-frequency');
    const kind = document.getElementById('meli-prank-kind');
    const excluded = document.getElementById('meli-prank-excluded');
    if (checkbox) checkbox.checked = config.enabled;
    if (frequency) frequency.value = config.frequency;
    if (kind) kind.value = config.kind;
    if (excluded) excluded.checked = mercadoLibrePrankExcludedHere();
    renderMercadoLibrePrankStatus(config);
}

function resetMercadoLibrePrankToday() {
    meliPrankStorageSet(MELI_PRANK_STORAGE_KEY, null);
    renderMercadoLibrePrankStatus(currentMercadoLibrePrankConfigFromForm());
    uiToast('Listo: en este equipo la broma sale en el proximo pago.', 'success');
}

function setMercadoLibrePrankExcluded(excluded) {
    meliPrankStorageSet(MELI_PRANK_EXCLUDED_KEY, excluded ? '1' : null);
    renderMercadoLibrePrankStatus(currentMercadoLibrePrankConfigFromForm());
    uiToast(excluded ? 'En este equipo la broma no va a salir.' : 'Este equipo vuelve a recibir la broma.', 'success');
}

async function postMercadoLibrePrankConfig(body) {
    const apiBase = await ensureApiPort();
    const response = await fetch(`${apiBase}/api/mercadolibre/pranks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function saveMercadoLibrePrankSetting(checkbox) {
    const enabled = checkbox.checked;
    try {
        const config = await postMercadoLibrePrankConfig({ enabled });
        uiToast(enabled ? 'Bromas activadas. Que la fuerza te acompañe.' : 'Bromas desactivadas.', 'success');
        renderMercadoLibrePrankStatus(config);
    } catch (error) {
        checkbox.checked = !enabled;
        uiToast(`No se pudo guardar: ${error.message}`, 'error');
    }
}

async function saveMercadoLibrePrankFrequency(select) {
    try {
        const config = await postMercadoLibrePrankConfig({ frequency: select.value });
        renderMercadoLibrePrankStatus(config);
        uiToast(select.value === 'daily' ? 'La broma sale una vez por dia por equipo.' : 'La broma sale en cada pago.', 'success');
    } catch (error) {
        uiToast(`No se pudo guardar: ${error.message}`, 'error');
        loadMercadoLibrePrankSetting();
    }
}

async function saveMercadoLibrePrankKind(select) {
    const labels = {
        confirmations: 'reconfirmaciones y carga falsa',
        dodge: 'el modal que se escapa',
        both: 'las dos bromas',
    };
    try {
        const config = await postMercadoLibrePrankConfig({ kind: select.value });
        renderMercadoLibrePrankStatus(config);
        uiToast(`Broma elegida: ${labels[select.value] || select.value}.`, 'success');
    } catch (error) {
        uiToast(`No se pudo guardar: ${error.message}`, 'error');
        loadMercadoLibrePrankSetting();
    }
}

function mercadoLibrePrankHas(prank, kind) {
    return Boolean(prank) && (prank.kind === kind || prank.kind === 'both');
}

// ---- Broma: el modal se escapa del puntero ----
// Solo mientras esta abierta la confirmacion real del pago. Se escapa MELI_PRANK_DODGE_MAX
// veces y despues se queda quieto; con teclado (Enter) siempre se puede confirmar.
const MELI_PRANK_DODGE_MAX = 4;
const MELI_PRANK_DODGE_LABELS = ['Registrar pago', 'Casi...', '¡Uy!', 'Por poco', 'Ok, ganaste'];

function startMercadoLibreModalDodge() {
    const modal = document.querySelector('#ui-modal .ui-modal');
    const okButton = document.getElementById('ui-modal-ok');
    if (!modal || !okButton) return () => {};
    let escapes = 0;
    let offsetX = 0;
    let offsetY = 0;
    const margin = 12;

    const dodge = () => {
        if (escapes >= MELI_PRANK_DODGE_MAX) return;
        escapes += 1;
        const rect = modal.getBoundingClientRect();
        // Posicion sin el desplazamiento actual, para calcular el rango que entra en pantalla.
        const baseLeft = rect.left - offsetX;
        const baseTop = rect.top - offsetY;
        const minX = margin - baseLeft;
        const maxX = window.innerWidth - margin - rect.width - baseLeft;
        const minY = margin - baseTop;
        const maxY = window.innerHeight - margin - rect.height - baseTop;
        let nextX = offsetX;
        let nextY = offsetY;
        // Elegir un destino que se aleje de donde esta (si la pantalla lo permite).
        for (let attempt = 0; attempt < 12; attempt += 1) {
            nextX = minX + Math.random() * Math.max(0, maxX - minX);
            nextY = minY + Math.random() * Math.max(0, maxY - minY);
            if (Math.hypot(nextX - offsetX, nextY - offsetY) > Math.min(220, rect.width / 2)) break;
        }
        offsetX = nextX;
        offsetY = nextY;
        modal.style.transition = 'transform .28s cubic-bezier(.2, .9, .3, 1.2)';
        modal.style.transform = `translate(${Math.round(offsetX)}px, ${Math.round(offsetY)}px)`;
        okButton.textContent = MELI_PRANK_DODGE_LABELS[Math.min(escapes, MELI_PRANK_DODGE_LABELS.length - 1)];
    };

    okButton.addEventListener('pointerenter', dodge);
    return () => {
        okButton.removeEventListener('pointerenter', dodge);
        // Esperar a que termine la animacion de cierre antes de devolverlo al centro.
        setTimeout(() => {
            modal.style.transform = '';
            modal.style.transition = '';
        }, 220);
    };
}

function markMercadoLibrePrankShown() {
    meliPrankStorageSet(MELI_PRANK_STORAGE_KEY, meliPrankToday());
}

const meliPrankPause = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function runMercadoLibrePrankConfirmations() {
    for (const step of MELI_PRANK_CONFIRMATIONS) {
        // El modal se oculta 180 ms despues de cerrarse: esperar para no pisar el siguiente.
        await meliPrankPause(260);
        const ok = await uiConfirm({ tone: 'info', ...step });
        if (!ok) return false;
    }
    await meliPrankPause(260);
    return true;
}

async function runMercadoLibrePrankLoading() {
    const backdrop = document.createElement('div');
    backdrop.className = 'ui-modal-backdrop meli-prank-backdrop';
    backdrop.innerHTML = `
        <div class="ui-modal meli-prank" role="status" aria-live="polite">
            <h2>Procesando pago</h2>
            <p class="ui-modal-message" id="meli-prank-step"></p>
            <div class="meli-prank-bar"><span id="meli-prank-progress"></span></div>
        </div>`;
    document.body.appendChild(backdrop);
    requestAnimationFrame(() => backdrop.classList.add('is-open'));
    const stepEl = backdrop.querySelector('#meli-prank-step');
    const progressEl = backdrop.querySelector('#meli-prank-progress');
    for (let i = 0; i < MELI_PRANK_LOADING_STEPS.length; i += 1) {
        stepEl.textContent = MELI_PRANK_LOADING_STEPS[i];
        progressEl.style.width = `${Math.round(((i + 1) / MELI_PRANK_LOADING_STEPS.length) * 100)}%`;
        await meliPrankPause(1100);
    }
    backdrop.classList.remove('is-open');
    await meliPrankPause(200);
    backdrop.remove();
}

async function registerMercadoLibrePayment(orderId, button) {
    const item = mercadoLibrePayments.find(row => String(row.order_id) === String(orderId));
    if (!item || !item.can_register) return;
    const operatorSelect = document.getElementById('meli-payment-operator');
    const journalSelect = document.getElementById('meli-payment-journal');
    if (!operatorSelect.value) {
        alert('Selecciona quien registrara el pago en Odoo');
        operatorSelect.focus();
        return;
    }
    if (!journalSelect.value) {
        alert('Selecciona el diario contable Mercado Pago');
        journalSelect.focus();
        return;
    }
    const roundingSelect = document.getElementById('meli-payment-rounding-account');
    const roundingAccountId = parseInt(roundingSelect?.value || '', 10) || null;
    const roundingDifference = Number(item.rounding_difference || 0);
    if (roundingDifference && !roundingAccountId) {
        alert('La factura difiere por redondeo: selecciona la cuenta de redondeo');
        roundingSelect?.focus();
        return;
    }

    const prank = await shouldRunMercadoLibrePrank();
    if (prank) markMercadoLibrePrankShown();
    const stopDodge = mercadoLibrePrankHas(prank, 'dodge') ? startMercadoLibreModalDodge() : null;
    const confirmed = await uiConfirm({
        tone: 'danger',
        title: 'Registrar pago de Mercado Libre',
        message: 'Se creara un pago real en Odoo y se adjuntara el comprobante PDF.',
        details: [
            ['Venta ML', item.pack_id ? `Pack ${item.pack_id}` : item.order_id],
            ['Factura', item.invoice?.name || item.invoice?.id || '-'],
            ['Productos', formatMercadoLibreAmount(item.products_amount ?? item.amount, item.currency)],
            ['Envio', formatMercadoLibreAmount(item.shipping_amount || 0, item.currency)],
            ['Importe a registrar', formatMercadoLibreAmount(item.amount, item.currency)],
            ...(roundingDifference ? [[
                'Redondeo',
                `${formatMercadoLibreAmount(roundingDifference, item.currency)} a ${roundingSelect.options[roundingSelect.selectedIndex]?.text || ''}`
            ]] : []),
            ['Pago ML', item.payment_reference || '-'],
            ['Operador', operatorSelect.options[operatorSelect.selectedIndex]?.text || operatorSelect.value],
            ['Diario', journalSelect.options[journalSelect.selectedIndex]?.text || journalSelect.value]
        ],
        confirmText: 'Registrar pago'
    });
    if (stopDodge) stopDodge();
    if (!confirmed) return;

    const withConfirmations = mercadoLibrePrankHas(prank, 'confirmations');
    if (withConfirmations && !(await runMercadoLibrePrankConfirmations())) return;

    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = 'Registrando...';
    try {
        if (withConfirmations) await runMercadoLibrePrankLoading();
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/mercadolibre/payments/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                order_id: item.order_id,
                journal_id: parseInt(journalSelect.value, 10),
                operator_app_username: operatorSelect.value,
                rounding_account_id: roundingAccountId
            })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);

        item.registered = true;
        item.can_register = false;
        item.registration = result;
        item.reason = result.attachment_ok
            ? 'Pago registrado con comprobante PDF'
            : (result.warning || 'Pago registrado sin comprobante');
        renderMercadoLibrePayments();
        if (typeof loadPosHistory === 'function') loadPosHistory();
        if (result.warning) {
            uiToast(result.warning, 'info', { title: 'Pago registrado con advertencia', duration: 9000 });
        } else {
            uiToast('Pago registrado en Odoo con el PDF adjunto.', 'success');
        }
        if (prank) {
            const prankMessage = prank.frequency === 'daily'
                ? 'Tranqui, era una broma. Por hoy los pagos se registran sin tanta pregunta.'
                : 'Tranqui, era una broma. El pago quedo registrado bien.';
            uiToast(prankMessage, 'info', {
                title: 'Te la creíste', duration: 9000
            });
        }
    } catch (error) {
        button.disabled = false;
        button.textContent = originalText;
        alert(`Error registrando pago de Mercado Libre: ${error.message}`);
    }
}
