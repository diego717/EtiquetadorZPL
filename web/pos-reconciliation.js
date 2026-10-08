// ---- Conciliacion de pagos (TotalNet POS y Mercado Libre) ----
let posJournals = [];
let posJournalMap = {};
let posRoundingAccounts = [];
let posSyncResult = null;
let posPaymentOperators = [];
let posPaymentOperatorFeatureReady = false;
let posPendingInvoices = [];
let posPaymentHistory = [];
let mercadoLibrePaymentOptionsLoaded = false;
const PAYMENT_SOURCE_STORAGE_KEY = 'etiquetador_payment_source';
const PAYMENT_SOURCE_LABELS = { totalnet: 'TotalNet', mercadolibre: 'Mercado Libre' };

function setPaymentSource(source, persist = true) {
    const selected = source === 'mercadolibre' ? 'mercadolibre' : 'totalnet';
    document.querySelectorAll('[data-pay-source]').forEach((tab) => {
        const active = tab.dataset.paySource === selected;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('[data-pay-source-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.paySourcePanel !== selected;
    });
    if (persist) {
        try {
            localStorage.setItem(PAYMENT_SOURCE_STORAGE_KEY, selected);
        } catch (e) {
            // Ignorar si localStorage no esta disponible.
        }
    }
    if (selected === 'mercadolibre' && !mercadoLibrePaymentOptionsLoaded) {
        mercadoLibrePaymentOptionsLoaded = true;
        loadMercadoLibrePaymentOptions().catch(() => {
            mercadoLibrePaymentOptionsLoaded = false;
        });
    }
}

function initPaymentSource() {
    let stored = null;
    try {
        stored = localStorage.getItem(PAYMENT_SOURCE_STORAGE_KEY);
    } catch (e) {
        stored = null;
    }
    setPaymentSource(stored, false);
}

function paymentHistorySource(item) {
    return item.source === 'mercadolibre' ? 'mercadolibre' : 'totalnet';
}

async function loadTotalNetConfig() {
    const config = await fetchAPI('/api/totalnet/config');
    if (!config) return;
    document.getElementById('totalnet-enabled').checked = !!config.enabled;
    document.getElementById('totalnet-client-id').value = config.client_id || '';
    document.getElementById('totalnet-token-url').value = config.token_url || '';
    document.getElementById('totalnet-api-base-url').value = config.api_base_url || 'https://apis.vnet.uy/adx-conecta';
    document.getElementById('totalnet-comercio').value = config.comercio || '';
    document.getElementById('totalnet-sucursal').value = config.sucursal || '';
    document.getElementById('totalnet-status').textContent = config.configured ? 'Configurado' : 'Falta configurar';
}

async function saveTotalNetConfig() {
    const config = {
        enabled: document.getElementById('totalnet-enabled').checked,
        client_id: document.getElementById('totalnet-client-id').value.trim(),
        client_secret: document.getElementById('totalnet-client-secret').value.trim(),
        token_url: document.getElementById('totalnet-token-url').value.trim(),
        api_base_url: document.getElementById('totalnet-api-base-url').value.trim(),
        comercio: document.getElementById('totalnet-comercio').value.trim(),
        sucursal: document.getElementById('totalnet-sucursal').value.trim()
    };
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/totalnet/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (response.ok) {
            document.getElementById('totalnet-client-secret').value = '';
            await loadTotalNetConfig();
            alert('OK: Configuracion TotalNet guardada');
        } else {
            const result = await response.json().catch(() => ({}));
            alert(`Error guardando TotalNet: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function testTotalNetConnection() {
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/totalnet/session/test`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert(result.message || (
                result.api_no_results
                    ? 'OK: OAuth2 y API TotalNet respondieron. No hubo cupones para la fecha de prueba.'
                    : 'OK: Conexion a TotalNet exitosa'
            ));
        } else {
            alert(`Error de conexion TotalNet: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function checkTotalNetSettlementInfo() {
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/totalnet/info`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert(`Respuesta de TotalNet /info (fechas con liquidacion disponible):\n\n${JSON.stringify(result, null, 2)}`);
        } else {
            alert(`Error consultando /info de TotalNet: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

function renderJournalMapTable() {
    const body = document.getElementById('pos-journal-map-body');
    const entries = Object.entries(posJournalMap);
    if (entries.length === 0) {
        body.innerHTML = '<tr><td colspan="3" class="empty-cell">Sin mapeos</td></tr>';
        return;
    }
    body.innerHTML = entries.map(([sello, journalId]) => {
        const journal = posJournals.find(j => String(j.id) === String(journalId));
        const journalName = journal ? journal.name : `#${journalId}`;
        return `<tr><td>${sello}</td><td>${journalName}</td>` +
            `<td><button class="btn danger" onclick="removeJournalMapping('${sello}')">Quitar</button></td></tr>`;
    }).join('');
}

async function loadPosJournals() {
    const response = await fetchAPI('/api/pos-reconciliation/journals');
    posJournals = (response && response.items) || [];
    const mappingSelect = document.getElementById('pos-journal-map-journal');
    mappingSelect.innerHTML = posJournals.length
        ? posJournals.map(j => `<option value="${j.id}">${j.name}</option>`).join('')
        : '<option value="">Sin diarios (revisa la config de Odoo)</option>';
    const paymentSelect = document.getElementById('pos-payment-journal');
    if (paymentSelect) {
        const previousValue = paymentSelect.value;
        paymentSelect.replaceChildren();
        paymentSelect.add(new Option('Usar mapeo configurado por sello', ''));
        posJournals.forEach(journal => {
            paymentSelect.add(new Option(journal.name, String(journal.id)));
        });
        if (posJournals.some(journal => String(journal.id) === previousValue)) {
            paymentSelect.value = previousValue;
        }
        paymentSelect.disabled = posJournals.length === 0;
        paymentSelect.onchange = () => {
            const status = document.getElementById('pos-payment-journal-status');
            if (!status) return;
            const selected = posJournals.find(journal => String(journal.id) === paymentSelect.value);
            status.textContent = selected
                ? `Diario elegido: ${selected.name}.`
                : 'Se usará el mapeo configurado por sello.';
        };
    }
}

async function loadPosRoundingAccounts() {
    const response = await fetchAPI('/api/pos-reconciliation/rounding-accounts');
    posRoundingAccounts = (response && response.items) || [];
    const select = document.getElementById('pos-rounding-account');
    if (!select) return;
    select.replaceChildren();
    select.add(new Option('Selecciona la cuenta de redondeo', ''));
    posRoundingAccounts.forEach(account => {
        select.add(new Option(`${account.code || ''} - ${account.name}`.replace(/^ - /, ''), String(account.id)));
    });
    const suggested = posRoundingAccounts.find(
        account => normalizePosJournalText(account.name) === 'redondeos'
    );
    if (suggested) select.value = String(suggested.id);
    select.disabled = posRoundingAccounts.length === 0;
}

function mappedPosJournalId(sello) {
    const normalizedSello = String(sello || '').trim().toLowerCase();
    const entry = Object.entries(posJournalMap).find(
        ([key]) => String(key || '').trim().toLowerCase() === normalizedSello
    );
    const value = entry ? parseInt(entry[1], 10) : 0;
    return Number.isInteger(value) && value > 0 ? value : null;
}

function normalizePosJournalText(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
}

function suggestPosJournalId(cupon) {
    const mappedId = mappedPosJournalId(cupon?.sello);
    if (mappedId) return mappedId;

    let brand = normalizePosJournalText(cupon?.sello);
    if (brand === 'mastercard') brand = 'master';
    const product = normalizePosJournalText(cupon?.producto);
    const currency = posCurrencyCode(cupon?.moneda);
    if (!brand || !product) return null;

    const currencyMarker = currency === 'UYU' ? 'm/n' : (currency === 'USD' ? 'm/e' : '');
    const candidates = posJournals.filter(journal => {
        const name = normalizePosJournalText(journal.name);
        return name.includes(brand) && name.includes(product) &&
            (!currencyMarker || name.includes(currencyMarker));
    });
    return candidates.length === 1 ? Number(candidates[0].id) : null;
}

function suggestPaymentJournalForResult(result) {
    const select = document.getElementById('pos-payment-journal');
    const status = document.getElementById('pos-payment-journal-status');
    if (!select || !status || select.value) return;

    const journalIds = [...new Set((result.matches_unicos || [])
        .filter(match => match.can_confirm === true)
        .map(match => Number(match.suggested_journal_id || suggestPosJournalId(match.cupon)))
        .filter(id => Number.isInteger(id) && id > 0))];
    if (journalIds.length !== 1) {
        status.textContent = 'Elige el diario antes de confirmar.';
        return;
    }
    const journal = posJournals.find(item => Number(item.id) === journalIds[0]);
    if (!journal) return;
    select.value = String(journal.id);
    status.textContent = `Sugerido por sello, producto y moneda: ${journal.name}.`;
}

function renderPosPaymentOperators() {
    const select = document.getElementById('pos-payment-operator');
    const status = document.getElementById('pos-payment-operator-status');
    if (!select || !status) return;

    const previousValue = select.value;
    select.replaceChildren();
    if (!posPaymentOperatorFeatureReady) {
        select.add(new Option('Reinicia la API para habilitar la seleccion', ''));
        select.disabled = true;
        status.textContent = 'La API activa todavia no permite elegir usuario.';
        return;
    }

    const validOperators = posPaymentOperators.filter(
        item => item && item.app_username && item.odoo_username && item.has_password === true
    );
    select.add(new Option('Selecciona quien registra el pago', ''));
    validOperators.forEach(item => {
        select.add(new Option(
            `${item.app_username} - ${item.odoo_username}`,
            item.app_username
        ));
    });
    if (validOperators.some(item => String(item.app_username) === previousValue)) {
        select.value = previousValue;
    }
    select.disabled = validOperators.length === 0;
    status.textContent = validOperators.length
        ? 'La seleccion se usara para autenticar y auditar el pago.'
        : 'Carga al menos un usuario Odoo por operador.';
}

async function loadPosPaymentOperators() {
    posPaymentOperatorFeatureReady = false;
    posPaymentOperators = [];
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/operators`);
        const result = await response.json().catch(() => ({}));
        if (response.ok && result.selection_required === true) {
            posPaymentOperatorFeatureReady = true;
            posPaymentOperators = Array.isArray(result.items) ? result.items : [];
        }
    } catch (error) {
        posPaymentOperatorFeatureReady = false;
    }
    renderPosPaymentOperators();
    renderPosAutoOperators();
}

function addJournalMapping() {
    const sello = document.getElementById('pos-journal-map-sello').value.trim();
    const journalId = document.getElementById('pos-journal-map-journal').value;
    if (!sello || !journalId) {
        alert('Completa sello y diario');
        return;
    }
    posJournalMap[sello] = journalId;
    document.getElementById('pos-journal-map-sello').value = '';
    renderJournalMapTable();
}

function removeJournalMapping(sello) {
    delete posJournalMap[sello];
    renderJournalMapTable();
}

async function loadPosReconciliationConfig() {
    const config = await fetchAPI('/api/pos-reconciliation/config');
    if (!config) return;
    posJournalMap = config.journal_map || {};
    document.getElementById('pos-amount-tolerance').value = config.amount_tolerance ?? 0.01;
    document.getElementById('pos-date-window').value = config.date_window_days ?? 2;
    document.getElementById('pos-auto-enabled').checked = !!config.auto_sync_enabled;
    document.getElementById('pos-auto-notify').checked = config.auto_sync_notify_desktop !== false;
    document.getElementById('pos-auto-interval').value = config.auto_sync_interval_minutes ?? 60;
    document.getElementById('pos-auto-lookback').value = config.auto_sync_lookback_days ?? 7;
    document.getElementById('pos-auto-register').checked = !!config.auto_register_deterministic;
    posAutoOperator = String(config.auto_register_operator || '');
    renderJournalMapTable();
    renderPosAutoOperators();
}

// ---- Conciliacion POS automatica (worker en segundo plano) ----
let posAutoOperator = '';
let posAutoStatusTimer = null;

function renderPosAutoOperators() {
    const select = document.getElementById('pos-auto-operator');
    if (!select) return;
    const current = select.value || posAutoOperator;
    select.replaceChildren();
    select.add(new Option('Sin operador (no registra pagos)', ''));
    posPaymentOperators
        .filter(item => item && item.app_username && item.odoo_username && item.has_password === true)
        .forEach(item => select.add(new Option(`${item.app_username} - ${item.odoo_username}`, item.app_username)));
    if ([...select.options].some(option => option.value === current)) {
        select.value = current;
    }
}

function formatPosAutoTime(value) {
    if (!value) return '';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function renderPosAutoStatus(status) {
    const banner = document.getElementById('pos-auto-banner');
    const title = document.getElementById('pos-auto-banner-title');
    const detail = document.getElementById('pos-auto-banner-detail');
    const loadBtn = document.getElementById('pos-auto-load-btn');
    const runBtn = document.getElementById('pos-auto-run-btn');
    if (!banner) return;
    if (!status) {
        banner.dataset.state = 'error';
        title.textContent = 'Conciliacion automatica no disponible';
        detail.textContent = 'Reinicia la API para habilitarla.';
        loadBtn.disabled = true;
        return;
    }
    const summary = status.last_summary || {};
    const ready = Number(summary.listos_para_revisar || 0);
    const ambiguous = Number(summary.ambiguos || 0);
    const registered = Number(summary.registrados_automaticamente || 0);
    runBtn.disabled = !!status.cycle_in_progress;
    loadBtn.disabled = !status.has_proposal;
    if (status.cycle_in_progress) {
        banner.dataset.state = 'idle';
        title.textContent = 'Sincronizando en segundo plano...';
    } else if (status.last_error) {
        banner.dataset.state = 'error';
        title.textContent = `Ultima sincronizacion automatica fallo: ${status.last_error}`;
    } else if (ready + ambiguous > 0) {
        banner.dataset.state = 'ready';
        title.textContent = `${ready} pagos listos para revisar` + (ambiguous ? ` · ${ambiguous} ambiguos` : '');
    } else if (status.has_proposal) {
        banner.dataset.state = 'idle';
        title.textContent = 'No hay pagos pendientes de revisar';
    } else {
        banner.dataset.state = 'idle';
        title.textContent = status.enabled ? 'Conciliacion automatica activa' : 'Conciliacion automatica apagada';
    }
    const parts = [];
    if (summary.date_from) parts.push(`Ventas ${summary.date_from} a ${summary.date_to}`);
    if (status.last_cycle_finished_at) parts.push(`actualizado ${formatPosAutoTime(status.last_cycle_finished_at)}`);
    if (registered) parts.push(`${registered} registrados automaticamente`);
    if (Number(summary.sin_match || 0)) parts.push(`${summary.sin_match} sin match`);
    if (Number(summary.con_diferencia || 0)) parts.push(`${summary.con_diferencia} con diferencia de importe`);
    parts.push(status.enabled ? `cada ${status.interval_minutes} min` : 'solo manual');
    detail.textContent = parts.join(' · ');

    const events = document.getElementById('pos-auto-events');
    const items = (status.recent_events || []).slice().reverse();
    events.innerHTML = items.length
        ? items.map(event => `<li><time>${escapePosHtml(formatPosAutoTime(event.at))}</time>${escapePosHtml(event.message)}</li>`).join('')
        : '<li class="odoo-muted">Sin actividad</li>';
}

async function loadPosAutoStatus() {
    renderPosAutoStatus(await fetchAPI('/api/pos-reconciliation/auto/status'));
}

async function runPosAutoNow() {
    const runBtn = document.getElementById('pos-auto-run-btn');
    runBtn.disabled = true;
    document.getElementById('pos-auto-banner-title').textContent = 'Sincronizando en segundo plano...';
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/auto/run-once`, { method: 'POST' });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(`Error en la sincronizacion: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
    await loadPosAutoStatus();
}

async function loadPosAutoProposal() {
    const proposal = await fetchAPI('/api/pos-reconciliation/auto/proposal');
    if (!proposal) {
        alert('No hay una propuesta automatica disponible todavia');
        return;
    }
    document.getElementById('pos-sync-date-from').value = proposal.date_from;
    document.getElementById('pos-sync-date-to').value = proposal.date_to;
    document.getElementById('pos-confirm-summary').textContent = '';
    await loadPosPendingInvoices(proposal.date_from, proposal.date_to);
    posSyncResult = proposal;
    suggestPaymentJournalForResult(proposal);
    const matches = proposal.matches_unicos || [];
    const summary = document.getElementById('pos-sync-summary');
    summary.textContent = `Propuesta automatica: ${matches.filter(m => m.can_confirm === true).length} confirmables, ` +
        `${(proposal.ambiguos || []).length} ambiguos, ${(proposal.sin_match || []).length} sin match. ` +
        'Revisa y confirma abajo.';
    summary.classList.remove('is-empty');
    renderPosResults();
    document.getElementById('pos-matches-body')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function savePosAutoConfig() {
    const status = document.getElementById('pos-auto-config-status');
    const config = {
        auto_sync_enabled: document.getElementById('pos-auto-enabled').checked,
        auto_sync_notify_desktop: document.getElementById('pos-auto-notify').checked,
        auto_sync_interval_minutes: parseInt(document.getElementById('pos-auto-interval').value, 10) || 60,
        auto_sync_lookback_days: parseInt(document.getElementById('pos-auto-lookback').value, 10) || 7,
        auto_register_deterministic: document.getElementById('pos-auto-register').checked,
        auto_register_operator: document.getElementById('pos-auto-operator').value
    };
    if (config.auto_register_deterministic && !(await uiConfirm({
        tone: 'danger',
        title: 'Registro automatico de pagos',
        message: 'Se registraran pagos en Odoo sin confirmacion solo cuando la coincidencia sea inequivoca. Los casos ambiguos o con diferencia siguen esperando revision.',
        confirmText: 'Activar'
    }))) {
        return;
    }
    status.className = 'pos-inline-message';
    status.textContent = 'Guardando...';
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            status.className = 'pos-inline-message error';
            status.textContent = result.detail || `Error ${response.status}`;
            return;
        }
        posAutoOperator = String(result.auto_register_operator || '');
        status.className = 'pos-inline-message success';
        status.textContent = 'Guardado';
        await loadPosAutoStatus();
    } catch (error) {
        status.className = 'pos-inline-message error';
        status.textContent = `Error de conexion: ${error.message}`;
    }
}

async function savePosReconciliationConfig() {
    const config = {
        amount_tolerance: parseFloat(document.getElementById('pos-amount-tolerance').value) || 0,
        date_window_days: parseInt(document.getElementById('pos-date-window').value, 10) || 0,
        journal_map: posJournalMap
    };
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (response.ok) {
            alert('OK: Configuracion de conciliacion guardada');
        } else {
            alert(`Error guardando configuracion: ${response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

function posCuponLabel(cupon) {
    const ticket = cupon.ticket ?? '-';
    const auth = cupon.autorizacion ?? '-';
    return `${escapePosHtml(ticket)} / ${escapePosHtml(auth)}`;
}

function escapePosHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function posPaymentDateIso(value) {
    const text = String(value || '').trim();
    const localMatch = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (localMatch) {
        return `${localMatch[3]}-${localMatch[2]}-${localMatch[1]}`;
    }
    const isoMatch = text.match(/^(\d{4}-\d{2}-\d{2})/);
    return isoMatch ? isoMatch[1] : text;
}

function posPaymentCoupon(cupon) {
    return {
        ...cupon,
        fecha: posPaymentDateIso(cupon?.fecha)
    };
}

function posCurrencyCode(value) {
    const text = String(value || '').trim().toUpperCase();
    if (!text) return '';
    if (text === '858') return 'UYU';
    if (text === '840') return 'USD';
    if (text === '978') return 'EUR';
    if (text.includes('USD') || text.includes('DOLAR')) return 'USD';
    if (text.includes('UYU') || text.includes('PESO') || text.includes('URUGUAY')) return 'UYU';
    if (text.includes('EUR') || text.includes('EURO')) return 'EUR';
    return /^[A-Z]{3}$/.test(text) ? text : '';
}

function formatPosAmount(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return value ?? '-';
    return new Intl.NumberFormat('es-UY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(number);
}

function formatPosCurrency(value) {
    return posCurrencyCode(value) || String(value || '-');
}

function formatPosAmountWithCurrency(value, currency) {
    return `${formatPosAmount(value)} ${formatPosCurrency(currency)}`;
}

function formatPosHistoryDateTime(value) {
    const text = String(value || '').trim();
    if (!text) return '-';
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return text;
    return new Intl.DateTimeFormat('es-UY', {
        dateStyle: 'short',
        timeStyle: 'short'
    }).format(parsed);
}

function posHistorySearchText(item) {
    const coupon = item.cupon || {};
    return [
        item.invoice_name,
        item.invoice_id,
        item.payment_id,
        item.cupon_id,
        item.operator_app_username,
        item.actor_odoo_username,
        coupon.ticket,
        coupon.autorizacion,
        coupon.numero_factura,
        coupon.sello,
        PAYMENT_SOURCE_LABELS[paymentHistorySource(item)],
        item.mercadolibre?.reference,
        ...(item.mercadolibre?.order_ids || []),
        item.mercadolibre?.payment_reference,
        item.mercadolibre?.buyer
    ].map(value => String(value || '').toLowerCase()).join(' ');
}

function renderPosHistory() {
    const body = document.getElementById('pos-history-body');
    const summary = document.getElementById('pos-history-summary');
    if (!body || !summary) return;
    const search = document.getElementById('pos-history-search')?.value.trim().toLowerCase() || '';
    const dateFrom = document.getElementById('pos-history-date-from')?.value || '';
    const dateTo = document.getElementById('pos-history-date-to')?.value || '';
    const state = document.getElementById('pos-history-state')?.value || 'ok';
    const sourceFilter = document.getElementById('pos-history-source')?.value || 'all';
    const filtered = posPaymentHistory.filter(item => {
        const paymentDate = posPaymentDateIso(item.cupon?.fecha || item.mercadolibre?.payment_date)
            || String(item.registered_at || '').slice(0, 10);
        if (sourceFilter !== 'all' && paymentHistorySource(item) !== sourceFilter) return false;
        if (search && !posHistorySearchText(item).includes(search)) return false;
        if (dateFrom && paymentDate && paymentDate < dateFrom) return false;
        if (dateTo && paymentDate && paymentDate > dateTo) return false;
        if (state === 'ok' && item.ok !== true) return false;
        if (state === 'error' && item.ok === true) return false;
        return true;
    });

    body.innerHTML = filtered.length ? filtered.map(item => {
        const coupon = item.cupon || {};
        const sale = item.mercadolibre || {};
        const source = paymentHistorySource(item);
        const invoiceLabel = item.invoice_name || (item.invoice_id ? `Factura #${item.invoice_id}` : '-');
        const statusLabel = item.ok === true ? 'Registrado' : 'Error';
        const statusTitle = item.ok === true
            ? (item.warning || 'Pago registrado correctamente')
            : (item.error || 'No se pudo registrar');
        const odooActions = [];
        if (item.invoice_url) {
            odooActions.push(`<a class="btn secondary" href="${escapePosHtml(item.invoice_url)}" target="_blank" rel="noopener noreferrer" aria-label="Abrir ${escapePosHtml(invoiceLabel)} en Odoo">Factura</a>`);
        }
        if (item.payment_url) {
            odooActions.push(`<a class="btn secondary" href="${escapePosHtml(item.payment_url)}" target="_blank" rel="noopener noreferrer" aria-label="Abrir pago ${escapePosHtml(item.payment_id)} en Odoo">Pago</a>`);
        }
        return `<tr>
            <td class="pos-money">${escapePosHtml(formatPosHistoryDateTime(item.registered_at))}</td>
            <td><span class="pay-source-badge" data-source="${source}">${escapePosHtml(PAYMENT_SOURCE_LABELS[source])}</span></td>
            ${source === 'mercadolibre' ? `
            <td class="pos-money">${escapePosHtml(sale.payment_date || '-')}</td>
            <td title="${escapePosHtml(sale.order_ids?.length ? `Ordenes: ${sale.order_ids.join(', ')}` : '')}">${escapePosHtml(sale.reference || '-')}${sale.buyer ? `<br><span class="odoo-muted">${escapePosHtml(sale.buyer)}</span>` : ''}</td>
            <td class="pos-money">${sale.amount !== undefined && sale.amount !== null ? escapePosHtml(formatPosAmountWithCurrency(sale.amount, sale.currency)) : '-'}</td>` : `
            <td class="pos-money">${escapePosHtml(coupon.fecha || '-')}</td>
            <td>${coupon.ticket || coupon.autorizacion ? posCuponLabel(coupon) : escapePosHtml(item.cupon_id || '-')}</td>
            <td class="pos-money">${coupon.importe !== undefined ? escapePosHtml(formatPosAmountWithCurrency(coupon.importe, coupon.moneda)) : '-'}</td>`}
            <td>${escapePosHtml(invoiceLabel)}</td>
            <td>${escapePosHtml(item.actor_odoo_username || item.operator_app_username || '-')}</td>
            <td><span class="pos-history-status" title="${escapePosHtml(statusTitle)}">${statusLabel}</span></td>
            <td><div class="pos-history-actions">${odooActions.join('') || '<span class="odoo-muted">Sin enlace</span>'}</div></td>
        </tr>`;
    }).join('') : '<tr><td colspan="9" class="empty-cell">No hay pagos que coincidan con los filtros</td></tr>';
    summary.textContent = `${filtered.length} de ${posPaymentHistory.length} registro(s)`;
}

async function loadPosHistory() {
    const summary = document.getElementById('pos-history-summary');
    if (summary) {
        summary.className = 'pos-inline-message';
        summary.textContent = 'Cargando historial...';
    }
    try {
        const result = await fetchAPI('/api/pos-reconciliation/history');
        posPaymentHistory = Array.isArray(result?.items) ? result.items : [];
        renderPosHistory();
    } catch (error) {
        posPaymentHistory = [];
        renderPosHistory();
        if (summary) {
            summary.className = 'pos-inline-message error';
            summary.textContent = `No se pudo cargar el historial: ${error.message}`;
        }
    }
}

function clearPosHistoryFilters() {
    document.getElementById('pos-history-search').value = '';
    document.getElementById('pos-history-date-from').value = '';
    document.getElementById('pos-history-date-to').value = '';
    document.getElementById('pos-history-state').value = 'ok';
    document.getElementById('pos-history-source').value = 'all';
    renderPosHistory();
}

function renderPosPendingInvoices() {
    const body = document.getElementById('pos-pending-invoices-body');
    if (!body) return;
    body.innerHTML = posPendingInvoices.length ? posPendingInvoices.map((invoice, idx) => `
        <tr>
            <td>${escapePosHtml(invoice.invoice_date || '-')}</td>
            <td>${escapePosHtml(invoice.name || invoice.invoice_id || '-')}</td>
            <td>${escapePosHtml(invoice.partner || '-')}</td>
            <td class="pos-money">${formatPosAmount(invoice.amount_residual ?? invoice.amount_total)}</td>
            <td>${escapePosHtml(formatPosCurrency(invoice.currency))}</td>
            <td>${escapePosHtml(invoice.invoice_origin || '-')}</td>
            <td><button class="btn secondary" onclick="prefillManualPosTicket(${idx})">Cargar ticket</button></td>
        </tr>`).join('') :
        '<tr><td colspan="7" class="empty-cell">No hay facturas a contado pendientes en el rango</td></tr>';
}

async function loadPosPendingInvoices(dateFrom, dateTo) {
    const status = document.getElementById('pos-pending-invoices-status');
    if (!dateFrom || !dateTo) {
        if (status) {
            status.className = 'pos-inline-message error';
            status.textContent = 'Completa fecha desde y fecha hasta.';
        }
        return false;
    }
    if (status) {
        status.className = 'pos-inline-message';
        status.textContent = 'Consultando facturas pendientes en Odoo...';
    }
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/pending-invoices`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_from: dateFrom, date_to: dateTo })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || `HTTP ${response.status}`);
        }
        posPendingInvoices = Array.isArray(result.items) ? result.items : [];
        renderPosPendingInvoices();
        if (status) {
            status.className = 'pos-inline-message success';
            status.textContent = `${posPendingInvoices.length} factura(s) pendiente(s) obtenida(s) directamente desde Odoo.`;
        }
        return true;
    } catch (error) {
        posPendingInvoices = [];
        renderPosPendingInvoices();
        if (status) {
            status.className = 'pos-inline-message error';
            status.textContent = `No se pudo consultar Odoo: ${error.message}`;
        }
        return false;
    }
}

function loadPosPendingInvoicesFromRange() {
    return loadPosPendingInvoices(
        document.getElementById('pos-sync-date-from').value,
        document.getElementById('pos-sync-date-to').value
    );
}

function prefillManualPosTicket(index) {
    const invoice = posPendingInvoices[index];
    if (!invoice) return;
    const numberMatches = String(invoice.name || '').match(/\d+/g);
    document.getElementById('pos-manual-date').value = invoice.invoice_date || '';
    document.getElementById('pos-manual-invoice').value = numberMatches?.at(-1) || '';
    document.getElementById('pos-manual-amount').value = Number(invoice.rounded_amount ?? invoice.amount_total).toFixed(2);
    document.getElementById('pos-manual-currency').value = posCurrencyCode(invoice.currency) || 'UYU';
    const panel = document.getElementById('pos-manual-panel');
    panel.open = true;
    panel.scrollIntoView({ block: 'start' });
    document.getElementById('pos-manual-ticket').focus();
    const status = document.getElementById('pos-manual-status');
    status.className = 'pos-inline-message';
    status.textContent = `Factura ${invoice.name || invoice.invoice_id} preparada. Completa los datos impresos en el ticket.`;
}

async function matchManualPosTicket() {
    const status = document.getElementById('pos-manual-status');
    const payload = {
        transaction_date: document.getElementById('pos-manual-date').value,
        invoice_number: document.getElementById('pos-manual-invoice').value.trim(),
        amount: Number(document.getElementById('pos-manual-amount').value),
        currency: document.getElementById('pos-manual-currency').value,
        ticket: document.getElementById('pos-manual-ticket').value.trim(),
        authorization: document.getElementById('pos-manual-authorization').value.trim(),
        brand: document.getElementById('pos-manual-brand').value,
        product: document.getElementById('pos-manual-product').value,
        batch: document.getElementById('pos-manual-batch').value.trim(),
        terminal: document.getElementById('pos-manual-terminal').value.trim(),
        last_four: document.getElementById('pos-manual-last-four').value.trim()
    };
    if (!payload.transaction_date || !payload.invoice_number || !Number.isFinite(payload.amount) || payload.amount <= 0 || !payload.ticket || !payload.authorization) {
        status.className = 'pos-inline-message error';
        status.textContent = 'Completa fecha, factura, importe, ticket y autorizacion.';
        return;
    }
    status.className = 'pos-inline-message';
    status.textContent = 'Buscando la factura a contado en Odoo...';
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/manual-match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
        posSyncResult = result;
        suggestPaymentJournalForResult(result);
        renderPosResults();
        const match = (result.matches_unicos || [])[0];
        status.className = match ? 'pos-inline-message success' : 'pos-inline-message error';
        status.textContent = match
            ? `Se encontro ${match.invoice.name}. Revisa la coincidencia y confirma abajo cuando estes seguro.`
            : `No se encontro en Odoo una factura a contado N.º ${payload.invoice_number} dentro de la ventana configurada.`;
        document.getElementById('pos-sync-summary').textContent = match
            ? 'Ticket manual preparado para revision'
            : 'Ticket manual sin coincidencia';
    } catch (error) {
        status.className = 'pos-inline-message error';
        status.textContent = `No se pudo buscar el ticket manual: ${error.message}`;
    }
}

function posPaymentStateLabel(value) {
    const labels = {
        not_paid: 'Pendiente',
        partial: 'Pago parcial',
        in_payment: 'En proceso de pago',
        paid: 'Pagada',
        reversed: 'Revertida'
    };
    return labels[String(value || '')] || String(value || 'Estado desconocido');
}

function posAmountsEqual(left, right) {
    const leftNumber = Number(left);
    const rightNumber = Number(right);
    return Number.isFinite(leftNumber) && Number.isFinite(rightNumber) &&
        Math.round((leftNumber - rightNumber) * 100) === 0;
}

function posMatchDetail(match) {
    const coupon = match.cupon || {};
    const invoice = match.invoice || {};
    const criterion = match.matched_by === 'numero_factura_totalnet'
        ? `N.º factura TotalNet ${coupon.numero_factura || '-'}`
        : 'Importe, moneda y fecha';
    if (match.amount_matches === false) {
        const difference = Number(match.amount_difference);
        const differenceText = Number.isFinite(difference)
            ? `${difference >= 0 ? '+' : ''}${formatPosAmount(difference)}`
            : '-';
        const roundingLabel = match.rounding_matches === true
            ? 'Confirmable usando la cuenta de redondeo'
            : 'No confirmable';
        return `<span class="pos-warn-text">${criterion}<br>` +
            `${roundingLabel}: Odoo ${formatPosAmountWithCurrency(invoice.amount_total, invoice.currency)}, ` +
            `TotalNet ${formatPosAmountWithCurrency(coupon.importe, coupon.moneda)}, ` +
            `diferencia ${differenceText} ${formatPosCurrency(coupon.moneda)}</span>`;
    }
    if (match.currency_matches === false) {
        return `<span class="pos-warn-text">${criterion}<br>No confirmable: las monedas no coinciden</span>`;
    }
    return criterion;
}

function renderPosResults() {
    const matchesBody = document.getElementById('pos-matches-body');
    const ambiguousBody = document.getElementById('pos-ambiguous-body');
    const nomatchBody = document.getElementById('pos-nomatch-body');

    if (!posSyncResult) return;

    const matches = posSyncResult.matches_unicos || [];
    matchesBody.innerHTML = matches.length ? matches.map((m, idx) => {
        const canRegister = m.can_confirm === true;
        const blockedReason = m.amount_matches === false
            ? 'El importe de TotalNet no coincide con el total de Odoo'
            : 'La factura no admite registrar este pago';
        return `
        <tr>
            <td>${canRegister ? `<input type="checkbox" class="pos-match-checkbox" data-idx="${idx}" checked>` : `<span title="${blockedReason}">-</span>`}</td>
            <td>${m.cupon.fecha || '-'}</td>
            <td>${formatPosAmount(m.cupon.importe)}</td>
            <td>${formatPosCurrency(m.cupon.moneda)}</td>
            <td>${posCuponLabel(m.cupon)}</td>
            <td>${m.cupon.sello || '-'}</td>
            <td>${m.invoice.name || m.invoice.invoice_id} (${m.invoice.partner || ''}) - ${posPaymentStateLabel(m.invoice.payment_state)}</td>
            <td>${posMatchDetail(m)}</td>
        </tr>`;
    }).join('') : '<tr><td colspan="8" class="empty-cell">Sin coincidencias</td></tr>';

    const ambiguous = posSyncResult.ambiguos || [];
    ambiguousBody.innerHTML = ambiguous.length ? ambiguous.map((a, idx) => {
        if (!a.cupon) {
            const cuponesTxt = (a.cupones_grupo || []).map(c => posCuponLabel(c)).join(', ');
            return `<tr>
                <td></td><td colspan="5">Agrupación recibida de una API anterior (${cuponesTxt}). Está deshabilitada y no se puede confirmar.</td>
                <td>${(a.candidates[0] || {}).name || ''}</td>
            </tr>`;
        }
        const candidateCanRegister = c => c.can_register_payment === true && posAmountsEqual(c.amount_total, a.cupon.importe);
        const canRegister = a.can_confirm !== false && a.candidates.some(candidateCanRegister);
        const options = a.candidates.map(c => `<option value="${c.invoice_id}" data-name="${c.name || ''}" ${candidateCanRegister(c) ? '' : 'disabled'}>${c.name || c.invoice_id} (${c.partner || ''}) - ${formatPosAmountWithCurrency(c.amount_total, c.currency)} - ${c.invoice_date || '-'} - ${posPaymentStateLabel(c.payment_state)}${posAmountsEqual(c.amount_total, a.cupon.importe) ? '' : ' - IMPORTE DISTINTO'}</option>`).join('');
        return `<tr>
            <td>${canRegister ? `<input type="checkbox" class="pos-ambiguous-checkbox" data-idx="${idx}">` : '<span title="Las facturas candidatas ya tienen pago registrado">-</span>'}</td>
            <td>${a.cupon.fecha || '-'}</td>
            <td>${formatPosAmount(a.cupon.importe)}</td>
            <td>${formatPosCurrency(a.cupon.moneda)}</td>
            <td>${posCuponLabel(a.cupon)}</td>
            <td>${a.cupon.sello || '-'}</td>
            <td><select class="pos-ambiguous-select" data-idx="${idx}">${options}</select></td>
        </tr>`;
    }).join('') : '<tr><td colspan="7" class="empty-cell">Sin ambiguos</td></tr>';

    const sinMatch = posSyncResult.sin_match || [];
    nomatchBody.innerHTML = sinMatch.length ? sinMatch.map((s, idx) => {
        const candidates = s.amount_candidates || [];
        const candidateCanRegister = c => c.can_register_payment === true && posAmountsEqual(c.amount_total, s.cupon.importe);
        const options = candidates.map(c =>
            `<option value="${c.invoice_id}" data-name="${c.name || ''}" ${candidateCanRegister(c) ? '' : 'disabled'}>` +
            `${c.name || c.invoice_id} (${c.partner || ''}) - ${formatPosAmountWithCurrency(c.amount_total, c.currency)} - ${c.invoice_date || '-'} - ${posPaymentStateLabel(c.payment_state)}${posAmountsEqual(c.amount_total, s.cupon.importe) ? '' : ' - IMPORTE DISTINTO'}</option>`
        ).join('');
        const canRegister = candidates.some(candidateCanRegister);
        return `<tr>
            <td>${canRegister ? `<input type="checkbox" class="pos-manual-checkbox" data-idx="${idx}">` : ''}</td>
            <td>${s.cupon.fecha || '-'}</td>
            <td>${formatPosAmount(s.cupon.importe)}</td>
            <td>${formatPosCurrency(s.cupon.moneda)}</td>
            <td>${posCuponLabel(s.cupon)}</td>
            <td>${s.cupon.sello || '-'}</td>
            <td>${candidates.length ? `<select class="pos-manual-select" data-idx="${idx}">${options}</select>` : `<span>${s.invoice_number_searched ? `No se encontró en Odoo la factura N.º ${s.invoice_number_searched}` : 'Sin factura con ese importe'}</span>`}</td>
        </tr>`;
    }).join('') : '<tr><td colspan="7" class="empty-cell">Sin filas</td></tr>';
}

function isTotalNetNoResultsError(detail) {
    const text = String(detail || '').toLowerCase();
    return text.includes('totalnet devolvio 404') && text.includes('no se encontraron resultados');
}

function emptyPosSyncResult(dateFrom, dateTo) {
    return {
        matching_version: null,
        date_from: dateFrom,
        date_to: dateTo,
        settlement_date_from: null,
        settlement_date_to: null,
        total_cupones: 0,
        total_facturas_contado: 0,
        total_facturas_pendientes_contado: 0,
        matches_unicos: [],
        ambiguos: [],
        sin_match: []
    };
}

function mergePosSyncResult(target, source) {
    const sourceVersion = Number(source.matching_version || 0);
    target.matching_version = target.matching_version === null
        ? sourceVersion
        : Math.min(target.matching_version, sourceVersion);
    if (source.settlement_date_from && (!target.settlement_date_from || source.settlement_date_from < target.settlement_date_from)) {
        target.settlement_date_from = source.settlement_date_from;
    }
    if (source.settlement_date_to && (!target.settlement_date_to || source.settlement_date_to > target.settlement_date_to)) {
        target.settlement_date_to = source.settlement_date_to;
    }
    target.total_cupones += Number(source.total_cupones || 0);
    target.total_facturas_contado += Number(
        source.total_facturas_contado ?? source.total_facturas_pendientes ?? 0
    );
    target.total_facturas_pendientes_contado += Number(
        source.total_facturas_pendientes_contado ?? source.total_facturas_pendientes ?? 0
    );
    target.matches_unicos.push(...(source.matches_unicos || []));
    target.ambiguos.push(...(source.ambiguos || []));
    target.sin_match.push(...(source.sin_match || []));
}

async function requestPosSync(apiBase, dateFrom, dateTo) {
    const response = await fetch(`${apiBase}/api/pos-reconciliation/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo })
    });
    const result = await response.json();
    return { response, result };
}

async function retryPosSyncDayByDay(apiBase, dateFrom, dateTo, summary) {
    const merged = emptyPosSyncResult(dateFrom, dateTo);
    const current = new Date(`${dateFrom}T00:00:00Z`);
    const last = new Date(`${dateTo}T00:00:00Z`);
    let processedDays = 0;

    while (current <= last) {
        const day = current.toISOString().slice(0, 10);
        processedDays += 1;
        summary.textContent = `Sincronizando dia ${processedDays}: ${day}...`;
        const { response, result } = await requestPosSync(apiBase, day, day);
        if (response.ok) {
            mergePosSyncResult(merged, result);
        } else if (!isTotalNetNoResultsError(result.detail)) {
            throw new Error(result.detail || `HTTP ${response.status}`);
        }
        current.setUTCDate(current.getUTCDate() + 1);
    }
    return merged;
}

async function syncPosReconciliation(options = {}) {
    const preservePaymentContext = options.preservePaymentContext === true;
    const preserveConfirmSummary = options.preserveConfirmSummary === true;
    const dateFrom = document.getElementById('pos-sync-date-from').value;
    const dateTo = document.getElementById('pos-sync-date-to').value;
    if (!dateFrom || !dateTo) {
        alert('Completa fecha desde y hasta');
        return;
    }
    const today = new Date();
    const todayLocal = [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, '0'),
        String(today.getDate()).padStart(2, '0')
    ].join('-');
    if (dateFrom > dateTo) {
        alert('La fecha desde no puede ser posterior a la fecha hasta');
        return;
    }
    if (dateTo >= todayLocal) {
        alert('TotalNet permite consultar solamente hasta el día de ayer');
        return;
    }
    const summary = document.getElementById('pos-sync-summary');
    if (!preserveConfirmSummary) {
        document.getElementById('pos-confirm-summary').textContent = '';
    }
    const paymentJournalSelect = document.getElementById('pos-payment-journal');
    const paymentJournalStatus = document.getElementById('pos-payment-journal-status');
    if (!preservePaymentContext) {
        if (paymentJournalSelect) paymentJournalSelect.value = '';
        if (paymentJournalStatus) paymentJournalStatus.textContent = '';
    }
    summary.textContent = 'Sincronizando...';
    try {
        await loadPosPendingInvoices(dateFrom, dateTo);
        summary.textContent = 'Odoo actualizado. Consultando TotalNet...';
        const apiBase = await ensureApiPort();
        let { response, result } = await requestPosSync(apiBase, dateFrom, dateTo);
        if (!response.ok) {
            if (isTotalNetNoResultsError(result.detail)) {
                result = await retryPosSyncDayByDay(apiBase, dateFrom, dateTo, summary);
            } else {
                summary.textContent = `Odoo visible. TotalNet no respondio: ${result.detail || response.status}`;
                alert(`Error sincronizando: ${result.detail || response.status}`);
                return;
            }
        }
        if (Number(result.matching_version || 0) < 4) {
            posSyncResult = null;
            summary.textContent = 'API desactualizada: reiniciar';
            alert('La API abierta todavía usa la conciliación anterior. Cierra la ventana de la API, vuelve a iniciarla y luego presiona Sincronizar.');
            return;
        }
        posSyncResult = result;
        suggestPaymentJournalForResult(result);
        const resultMatches = result.matches_unicos || [];
        const confirmableCount = resultMatches.filter(match => match.can_confirm === true).length;
        const differenceCount = resultMatches.filter(match => match.amount_matches === false).length;
        const settlementNote = result.settlement_date_to
            ? ` · TotalNet liquidacion consultada hasta ${result.settlement_date_to} (ventas sin liquidar todavia no apareceran hasta volver a sincronizar mas adelante)`
            : '';
        summary.textContent = `${result.total_cupones} cupones, ${result.total_facturas_contado ?? 0} facturas a contado ` +
            `(${result.total_facturas_pendientes_contado ?? 0} pendientes), ${resultMatches.length} coincidencias ` +
            `(${confirmableCount} confirmables, ${differenceCount} con diferencia), ${(result.ambiguos || []).length} ambiguos` +
            settlementNote;
        summary.classList.remove('is-empty');
        renderPosResults();
    } catch (error) {
        summary.textContent = `Odoo visible si respondio. Error TotalNet: ${error.message}`;
        alert(`Error de conexion: ${error.message}`);
    }
}

function clearPosReconciliationResults(message) {
    posSyncResult = null;
    document.getElementById('pos-matches-body').innerHTML = `<tr><td colspan="8" class="empty-cell">${escapePosHtml(message)}</td></tr>`;
    document.getElementById('pos-ambiguous-body').innerHTML = '<tr><td colspan="7" class="empty-cell">Sin ambiguos</td></tr>';
    document.getElementById('pos-nomatch-body').innerHTML = '<tr><td colspan="7" class="empty-cell">Sin filas</td></tr>';
}

async function confirmPosReconciliation() {
    if (!posSyncResult) {
        alert('Primero sincroniza');
        return;
    }
    if (!posPaymentOperatorFeatureReady) {
        alert('La API activa no permite elegir el usuario Odoo. Reinicia la API antes de registrar pagos.');
        return;
    }
    const operatorSelect = document.getElementById('pos-payment-operator');
    const operatorAppUsername = String(operatorSelect?.value || '').trim();
    if (!operatorAppUsername) {
        alert('Selecciona quien registrara el pago en Odoo');
        operatorSelect?.focus();
        return;
    }
    const journalSelect = document.getElementById('pos-payment-journal');
    const selectedJournalValue = parseInt(journalSelect?.value || '', 10);
    const selectedJournalId = Number.isInteger(selectedJournalValue) && selectedJournalValue > 0
        ? selectedJournalValue
        : null;
    const roundToInteger = document.getElementById('pos-round-payment')?.checked === true;
    const roundingAccountValue = parseInt(document.getElementById('pos-rounding-account')?.value || '', 10);
    const roundingAccountId = Number.isInteger(roundingAccountValue) && roundingAccountValue > 0
        ? roundingAccountValue
        : null;
    const attachReceiptPdf = document.getElementById('pos-attach-receipt-pdf')?.checked !== false;
    const confirmingManualTicket = posSyncResult.source === 'manual_ticket';
    const items = [];

    document.querySelectorAll('.pos-match-checkbox:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.idx, 10);
        const match = posSyncResult.matches_unicos[idx];
        items.push({
            cupon: posPaymentCoupon(match.cupon),
            invoice_id: match.invoice.invoice_id,
            invoice_name: match.invoice.name || '',
            journal_id: selectedJournalId || match.suggested_journal_id || suggestPosJournalId(match.cupon),
            round_to_integer: roundToInteger,
            rounding_account_id: roundingAccountId,
            attach_receipt_pdf: attachReceiptPdf,
            memo: match.suggested_memo || ''
        });
    });

    document.querySelectorAll('.pos-ambiguous-checkbox:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.idx, 10);
        const ambiguous = posSyncResult.ambiguos[idx];
        const select = document.querySelector(`.pos-ambiguous-select[data-idx="${idx}"]`);
        if (!select || !select.value) return;
        const selectedOption = select.options[select.selectedIndex];
        items.push({
            cupon: posPaymentCoupon(ambiguous.cupon),
            invoice_id: parseInt(select.value, 10),
            invoice_name: selectedOption.dataset.name || '',
            journal_id: selectedJournalId || suggestPosJournalId(ambiguous.cupon),
            round_to_integer: roundToInteger,
            rounding_account_id: roundingAccountId,
            attach_receipt_pdf: attachReceiptPdf,
            memo: ''
        });
    });

    document.querySelectorAll('.pos-manual-checkbox:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.idx, 10);
        const row = posSyncResult.sin_match[idx];
        const select = document.querySelector(`.pos-manual-select[data-idx="${idx}"]`);
        if (!row || !select || !select.value) return;
        const candidate = (row.amount_candidates || []).find(
            item => String(item.invoice_id) === String(select.value)
        );
        if (!candidate) return;
        items.push({
            cupon: posPaymentCoupon(row.cupon),
            invoice_id: parseInt(select.value, 10),
            invoice_name: candidate.name || '',
            journal_id: selectedJournalId || suggestPosJournalId(row.cupon),
            round_to_integer: roundToInteger,
            rounding_account_id: roundingAccountId,
            attach_receipt_pdf: attachReceiptPdf,
            memo: ''
        });
    });

    if (items.length === 0) {
        alert('No hay filas seleccionadas');
        return;
    }
    const missingJournalItems = items.filter(item => !item.journal_id);
    if (missingJournalItems.length > 0) {
        const sellos = [...new Set(missingJournalItems.map(item => item.cupon.sello || 'sin sello'))].join(', ');
        alert(`Falta elegir el diario contable para: ${sellos}. Selecciónalo en "Diario para los pagos seleccionados" antes de confirmar.`);
        journalSelect?.focus();
        return;
    }
    if (roundToInteger && !roundingAccountId) {
        alert('Selecciona la cuenta contable donde se registrarán las diferencias de redondeo.');
        document.getElementById('pos-rounding-account')?.focus();
        return;
    }

    const selectedOperatorLabel = operatorSelect.options[operatorSelect.selectedIndex]?.text || operatorAppUsername;
    if (!(await uiConfirm({
        tone: 'danger',
        title: 'Registrar pagos en Odoo',
        message: `Se registraran ${items.length} pago(s) reales en Odoo como ${selectedOperatorLabel}. ¿Continuar?`,
        confirmText: 'Registrar pagos'
    }))) {
        return;
    }

    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/pos-reconciliation/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operator_app_username: operatorAppUsername,
                items
            })
        });
        const result = await response.json();
        if (!response.ok) {
            const detail = result.detail || `HTTP ${response.status}`;
            document.getElementById('pos-confirm-summary').textContent = `No se registraron pagos: ${detail}`;
            alert(`Error registrando pagos: ${detail}`);
            return;
        }
        const ok = (result.items || []).filter(r => r.ok).length;
        const failed = (result.items || []).filter(r => !r.ok);
        const warnings = (result.items || []).filter(r => r.ok && r.warning);
        const actor = result.operator?.odoo_username || selectedOperatorLabel;
        document.getElementById('pos-confirm-summary').textContent =
            `${ok} pagos registrados en Odoo como ${actor}. ${failed.length} con error.` +
            (failed.length ? ' ' + failed.map(f => f.error).join(' | ') : '') +
            (warnings.length ? ` ${warnings.length} advertencia(s): ` + warnings.map(item => item.warning).join(' | ') : '');
        if (confirmingManualTicket && ok > 0) {
            clearPosReconciliationResults('El ticket manual ya fue procesado. Puedes cargar otro comprobante.');
            await loadPosPendingInvoicesFromRange();
        } else {
            await syncPosReconciliation({
                preservePaymentContext: true,
                preserveConfirmSummary: true
            });
        }
        await loadPosHistory();
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

// Cargar configuraciones al iniciar
(() => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const today = new Date();
    const maxPosDate = [
        yesterday.getFullYear(),
        String(yesterday.getMonth() + 1).padStart(2, '0'),
        String(yesterday.getDate()).padStart(2, '0')
    ].join('-');
    const todayPosDate = [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, '0'),
        String(today.getDate()).padStart(2, '0')
    ].join('-');
    const fromInput = document.getElementById('pos-sync-date-from');
    const toInput = document.getElementById('pos-sync-date-to');
    fromInput?.setAttribute('max', maxPosDate);
    toInput?.setAttribute('max', maxPosDate);
    if (fromInput && !fromInput.value) fromInput.value = maxPosDate;
    if (toInput && !toInput.value) toInput.value = maxPosDate;
    const manualDate = document.getElementById('pos-manual-date');
    manualDate?.setAttribute('max', todayPosDate);
    if (manualDate && !manualDate.value) manualDate.value = maxPosDate;
})();
