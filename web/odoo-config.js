// Odoo: conexion, usuarios, impresoras y automatizacion.

let odooConfig = {};
let odooOperatorUsers = [];
let odooAutomationStatus = {};
let odooStatusTimer = null;

function mergeUniqueStrings(arrays) {
    const seen = new Set();
    const result = [];
    for (const arr of arrays) {
        for (const value of arr || []) {
            const text = String(value || '').trim();
            if (!text) continue;
            if (seen.has(text)) continue;
            seen.add(text);
            result.push(text);
        }
    }
    return result;
}

function setSelectOptions(selectId, options, selectedValue = '', emptyLabel = '(Sin seleccionar)') {
    const select = document.getElementById(selectId);
    if (!select) return;
    const normalizedSelected = String(selectedValue || '').trim();
    const list = Array.isArray(options) ? options : [];
    const html = [`<option value="">${emptyLabel}</option>`];
    for (const option of list) {
        const safe = String(option || '').trim();
        if (!safe) continue;
        html.push(`<option value="${safe}" ${safe === normalizedSelected ? 'selected' : ''}>${safe}</option>`);
    }
    if (normalizedSelected && !list.includes(normalizedSelected)) {
        html.push(`<option value="${normalizedSelected}" selected>${normalizedSelected}</option>`);
    }
    select.innerHTML = html.join('');
}

function updateOdooForm() {
    const config = odooConfig || {};
    document.getElementById('odoo-enabled').checked = config.enabled === true;
    document.getElementById('odoo-auto-enabled').checked = config.automation_enabled === true;
    document.getElementById('odoo-interval').value = config.automation_interval_seconds || 60;
    document.getElementById('odoo-url').value = config.base_url || '';
    document.getElementById('odoo-db').value = config.database || '';
    document.getElementById('odoo-user').value = config.username || '';
    document.getElementById('odoo-password').value = '';
    document.getElementById('odoo-report-name').value = config.report_name || 'sale.report_saleorder';
    document.getElementById('odoo-order-prefix').value = config.order_prefix || 'ML ';
    document.getElementById('odoo-shipment-field').value = config.shipment_field || '';
    document.getElementById('odoo-order-states').value = config.allowed_order_states || 'draft,sent,sale';
    document.getElementById('odoo-sync-limit').value = config.automation_sync_limit || 20;
    const orderToLabelDelay = Number(config.automation_order_to_label_delay_seconds);
    document.getElementById('odoo-order-label-delay').value = Number.isFinite(orderToLabelDelay) ? orderToLabelDelay : 1;
    document.getElementById('odoo-include-reprint').checked = config.automation_include_reprint === true;
    document.getElementById('odoo-confirm-on-print').checked = config.confirm_order_on_print === true;
    document.getElementById('odoo-order-copies').value = config.default_order_copies || 1;
    document.getElementById('odoo-force-order-grayscale').checked = config.force_order_grayscale === true;
    document.getElementById('odoo-label-copies').value = config.default_label_copies || 1;
    document.getElementById('odoo-config-path').textContent = config.config_path || '-';
    updateOdooAutomationStatusForm();
}

function renderOdooOperatorUsers() {
    const tbody = document.getElementById('odoo-operator-users-body');
    const items = Array.isArray(odooOperatorUsers) ? odooOperatorUsers : [];
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">Sin usuarios cargados</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((item) => {
        const appUser = item.app_username || '';
        const encodedAppUser = encodeURIComponent(appUser);
        return `
        <tr>
            <td><span class="mono-id">${appUser || '-'}</span></td>
            <td>${item.odoo_username || '-'}</td>
            <td>${item.has_password ? 'Guardada' : 'No'}</td>
            <td><button class="btn danger sm" onclick="deleteOdooOperatorUser('${encodedAppUser}')">Eliminar</button></td>
        </tr>
    `;
    }).join('');
}

function resolveMappedOdooUser(appUsername) {
    const key = String(appUsername || '').trim().toLowerCase();
    if (!key) return '';
    const items = Array.isArray(odooOperatorUsers) ? odooOperatorUsers : [];
    const match = items.find(
        (item) => String(item?.app_username || '').trim().toLowerCase() === key
    );
    return String(match?.odoo_username || '').trim();
}

async function loadOdooOperatorUsers() {
    const response = await fetchAPI('/api/odoo/operator-users');
    odooOperatorUsers = (response && Array.isArray(response.items)) ? response.items : [];
    renderOdooOperatorUsers();
}

function updateOdooAutomationStatusForm() {
    const status = odooAutomationStatus || {};
    const running = status.running === true;
    document.getElementById('odoo-worker-running').textContent = running ? 'Si' : 'No';
    document.getElementById('odoo-processed-count').textContent = status.processed_count || 0;
    document.getElementById('odoo-last-cycle').textContent = status.last_cycle_finished_at || '-';
    const result = status.last_cycle_result || {};
    if (Object.keys(result).length) {
        const text = `checked=${result.checked || 0}, printed=${result.printed || 0}, errors=${result.errors || 0}`;
        document.getElementById('odoo-last-result').textContent = text;
    } else {
        document.getElementById('odoo-last-result').textContent = '-';
    }
    const recentProcessed = Array.isArray(status.recent_processed_envios) ? status.recent_processed_envios : [];
    if (recentProcessed.length) {
        document.getElementById('odoo-recent-processed').textContent = recentProcessed
            .slice(0, 10)
            .map(item => item.envio_id)
            .join(', ');
    } else {
        document.getElementById('odoo-recent-processed').textContent = '-';
    }
    document.getElementById('odoo-last-error').textContent = compactErrorText(status.last_error);
}

async function loadOdooPrinters() {
    const allData = await fetchAPI('/api/printers');
    const networkData = await fetchAPI('/api/printers/network');

    const allPrinters = mergeUniqueStrings([
        (allData && allData.printers) ? allData.printers : [],
        (networkData && networkData.printers) ? networkData.printers : []
    ]);
    const networkPrinters = mergeUniqueStrings([
        (networkData && networkData.printers) ? networkData.printers : [],
        allPrinters
    ]);

    setSelectOptions(
        'odoo-order-printer-primary',
        networkPrinters,
        odooConfig.default_order_printer || 'Expedicion',
        'Seleccionar impresora principal'
    );
    setSelectOptions(
        'odoo-order-printer-fallback',
        networkPrinters,
        odooConfig.fallback_order_printer || '',
        '(Sin impresora de respaldo)'
    );
    setSelectOptions(
        'odoo-label-printer-primary',
        allPrinters,
        odooConfig.default_label_printer || administradoConfig.default_printer || '',
        'Seleccionar impresora principal'
    );
    setSelectOptions(
        'odoo-label-printer-fallback',
        allPrinters,
        odooConfig.fallback_label_printer || '',
        '(Sin impresora de respaldo)'
    );
}

async function loadOdooConfig() {
    const response = await fetchAPI('/api/odoo/config');
    odooConfig = response || {};
    updateOdooForm();
    await loadOdooOperatorUsers();
    await loadOdooPrinters();
}

async function loadOdooAutomationStatus() {
    const response = await fetchAPI('/api/odoo/automation/status');
    odooAutomationStatus = response || {};
    updateOdooAutomationStatusForm();
}

async function saveOdooConfig() {
    const config = {
        enabled: document.getElementById('odoo-enabled').checked,
        automation_enabled: document.getElementById('odoo-auto-enabled').checked,
        automation_interval_seconds: parseInt(document.getElementById('odoo-interval').value, 10) || 60,
        base_url: document.getElementById('odoo-url').value.trim(),
        database: document.getElementById('odoo-db').value.trim(),
        username: document.getElementById('odoo-user').value.trim(),
        password: document.getElementById('odoo-password').value.trim(),
        report_name: document.getElementById('odoo-report-name').value.trim() || 'sale.report_saleorder',
        order_prefix: document.getElementById('odoo-order-prefix').value || 'ML ',
        shipment_field: document.getElementById('odoo-shipment-field').value.trim(),
        allowed_order_states: document.getElementById('odoo-order-states').value.trim() || 'draft,sent,sale',
        automation_sync_limit: parseInt(document.getElementById('odoo-sync-limit').value, 10) || 20,
        automation_order_to_label_delay_seconds: parseInt(document.getElementById('odoo-order-label-delay').value, 10) || 0,
        automation_include_reprint: document.getElementById('odoo-include-reprint').checked,
        confirm_order_on_print: document.getElementById('odoo-confirm-on-print').checked,
        default_order_printer: document.getElementById('odoo-order-printer-primary').value.trim(),
        fallback_order_printer: document.getElementById('odoo-order-printer-fallback').value.trim(),
        default_order_copies: parseInt(document.getElementById('odoo-order-copies').value, 10) || 1,
        force_order_grayscale: document.getElementById('odoo-force-order-grayscale').checked,
        default_label_printer: document.getElementById('odoo-label-printer-primary').value.trim(),
        fallback_label_printer: document.getElementById('odoo-label-printer-fallback').value.trim(),
        default_label_copies: parseInt(document.getElementById('odoo-label-copies').value, 10) || 1
    };

    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            odooConfig = await response.json();
            updateOdooForm();
            await loadOdooPrinters();
            alert('OK: Configuracion Odoo guardada');
        } else {
            const error = await response.text();
            alert(`Error guardando Odoo: ${response.status}`);
            console.error('Error Odoo config:', error);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function testOdooConnection() {
    try {
        const apiBase = await ensureApiPort();
        const config = {
            enabled: document.getElementById('odoo-enabled').checked,
            automation_enabled: document.getElementById('odoo-auto-enabled').checked,
            automation_interval_seconds: parseInt(document.getElementById('odoo-interval').value, 10) || 60,
            base_url: document.getElementById('odoo-url').value.trim(),
            database: document.getElementById('odoo-db').value.trim(),
            username: document.getElementById('odoo-user').value.trim(),
            password: document.getElementById('odoo-password').value.trim(),
            report_name: document.getElementById('odoo-report-name').value.trim() || 'sale.report_saleorder',
            order_prefix: document.getElementById('odoo-order-prefix').value || 'ML ',
            shipment_field: document.getElementById('odoo-shipment-field').value.trim(),
            allowed_order_states: document.getElementById('odoo-order-states').value.trim() || 'draft,sent,sale',
            automation_sync_limit: parseInt(document.getElementById('odoo-sync-limit').value, 10) || 20,
            automation_order_to_label_delay_seconds: parseInt(document.getElementById('odoo-order-label-delay').value, 10) || 0,
            automation_include_reprint: document.getElementById('odoo-include-reprint').checked,
            confirm_order_on_print: document.getElementById('odoo-confirm-on-print').checked,
            default_order_printer: document.getElementById('odoo-order-printer-primary').value.trim(),
            fallback_order_printer: document.getElementById('odoo-order-printer-fallback').value.trim(),
            default_order_copies: parseInt(document.getElementById('odoo-order-copies').value, 10) || 1,
            force_order_grayscale: document.getElementById('odoo-force-order-grayscale').checked,
            default_label_printer: document.getElementById('odoo-label-printer-primary').value.trim(),
            fallback_label_printer: document.getElementById('odoo-label-printer-fallback').value.trim(),
            default_label_copies: parseInt(document.getElementById('odoo-label-copies').value, 10) || 1
        };
        await fetch(`${apiBase}/api/odoo/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const response = await fetch(`${apiBase}/api/odoo/session/test`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert(`OK: Conectado a Odoo (uid=${result.uid})`);
            await loadOdooAutomationStatus();
        } else {
            alert(`Error Odoo: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function saveOdooOperatorUser() {
    try {
        const appUsername = document.getElementById('odoo-operator-app-username').value.trim();
        const odooUsername = document.getElementById('odoo-operator-odoo-username').value.trim();
        const odooPassword = document.getElementById('odoo-operator-odoo-password').value.trim();
        if (!appUsername || !odooUsername || !odooPassword) {
            alert('Completa usuario app, usuario Odoo y password Odoo');
            return;
        }
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/operator-users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                app_username: appUsername,
                odoo_username: odooUsername,
                odoo_password: odooPassword
            })
        });
        const result = await response.json();
        if (!response.ok) {
            alert(`Error guardando usuario Odoo: ${result.detail || response.status}`);
            return;
        }
        odooOperatorUsers = Array.isArray(result.items) ? result.items : [];
        renderOdooOperatorUsers();
        await loadPosPaymentOperators();
        document.getElementById('odoo-operator-odoo-password').value = '';
        alert('OK: Usuario Odoo por operador guardado');
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function deleteOdooOperatorUser(appUsername) {
    try {
        const safeUser = decodeURIComponent(String(appUsername || '').trim());
        if (!safeUser) return;
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/operator-users/${encodeURIComponent(safeUser)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (!response.ok) {
            alert(`Error eliminando usuario Odoo: ${result.detail || response.status}`);
            return;
        }
        odooOperatorUsers = Array.isArray(result.items) ? result.items : [];
        renderOdooOperatorUsers();
        await loadPosPaymentOperators();
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function runOdooAutomationOnce() {
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/automation/run-once`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert(`Ciclo ejecutado: checked=${result.checked || 0}, printed=${result.printed || 0}, errors=${result.errors || 0}`);
        } else {
            alert(`Error ejecutando ciclo: ${result.detail || response.status}`);
        }
        await loadOdooAutomationStatus();
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}

async function resetOdooAutomationProcessed() {
    if (!(await uiConfirm({
        tone: 'danger',
        title: 'Reset procesados',
        message: 'Reiniciar la memoria de envios procesados?',
        confirmText: 'Reiniciar'
    }))) {
        return;
    }
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/odoo/automation/reset-processed`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            alert('OK: Procesados reiniciados');
        } else {
            alert(`Error reiniciando procesados: ${result.detail || response.status}`);
        }
        await loadOdooAutomationStatus();
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
    }
}
