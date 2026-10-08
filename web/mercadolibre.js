// Mercado Libre: configuracion, OAuth, ventas e impresion.

let mercadoLibreConfig = {};
let mercadoLibreSales = [];

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
