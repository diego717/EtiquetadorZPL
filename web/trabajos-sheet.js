// Planilla elegida en Trabajos y Precargadas. Si el servidor tiene varias, cada
// dispositivo recuerda la suya; ?sheet=<id> en el enlace la fija (sirve para dejar
// un acceso directo por planilla). Requiere panel.js.
const SHEET_STORAGE_KEY = 'trabajos_planilla';

let currentSheetId = (() => {
    const fromUrl = new URLSearchParams(window.location.search).get('sheet');
    if (fromUrl) {
        try { localStorage.setItem(SHEET_STORAGE_KEY, fromUrl); } catch (e) { /* sin localStorage */ }
        return fromUrl;
    }
    try { return localStorage.getItem(SHEET_STORAGE_KEY) || ''; } catch (e) { return ''; }
})();

function withSheet(path) {
    if (!currentSheetId) return path;
    return `${path}${path.includes('?') ? '&' : '?'}sheet=${encodeURIComponent(currentSheetId)}`;
}

function rememberSheet(id) {
    currentSheetId = id;
    try { localStorage.setItem(SHEET_STORAGE_KEY, id); } catch (e) { /* sin localStorage */ }
}

// Muestra el selector solo si hay mas de una planilla. Se espera antes de la primera
// carga: si la planilla recordada ya no existe, se vuelve a la primera.
async function initSheetPicker(onChange) {
    let sheets = [];
    try {
        sheets = (await panelApi('/api/trabajos/sheets')).items || [];
    } catch (e) {
        return;
    }
    if (currentSheetId && !sheets.some(sheet => sheet.id === currentSheetId)) {
        rememberSheet(sheets.length ? sheets[0].id : '');
    }
    const holder = document.getElementById('sheet-picker');
    if (!holder || sheets.length < 2) return;
    holder.innerHTML = `<label class="field">Planilla
        <select id="sheet-select">${sheets.map(sheet => `<option value="${esc(sheet.id)}">${esc(sheet.name)}</option>`).join('')}</select>
    </label>`;
    holder.hidden = false;
    const select = document.getElementById('sheet-select');
    select.value = currentSheetId || sheets[0].id;
    select.addEventListener('change', () => {
        rememberSheet(select.value);
        onChange(select.value);
    });
}
