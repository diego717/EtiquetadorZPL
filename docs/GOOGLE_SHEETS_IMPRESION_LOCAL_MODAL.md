# Modal de Google Sheets para comparar JPG de Drive vs CDR

## Importante

Este modal se usa dentro de Google Sheets, pero la API local de `client-assets` debe correr en la misma PC donde se abre la planilla.

API local esperada:

```text
http://127.0.0.1:8003
```

## Estructura sugerida en la hoja

- columna `F`: cliente

En esta version el JPG guia ya no se toma desde un link en la fila.  
El script busca imagenes en Drive usando el nombre del cliente de la columna `F`.

## Apps Script `.gs`

Crear un archivo llamado `Code.gs` y pegar esto:

```javascript
const IMPRESION_SHEET = 'impresion';
const CLIENT_COLUMN = 6; // F
const FIRST_DATA_ROW_IMPRESION = 4;
const LOCAL_API_BASE = 'http://127.0.0.1:8003';
const MAX_DRIVE_GUIDE_CANDIDATES = 20;

// Opcional: si quieres limitar la busqueda a una carpeta de Drive, pega aqui el ID.
const DRIVE_GUIDE_FOLDER_ID = '';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Impresion')
    .addItem('Comparar guia Drive vs CDR', 'showSelectedClientCdrModal')
    .addItem('Abrir ultimo cliente editado', 'showLastEditedClientCdrModal')
    .addToUi();
}

function rememberLastEditedPrintClient_(e) {
  if (!e || !e.range) return;

  const range = e.range;
  const sheet = range.getSheet();

  if (sheet.getName() !== IMPRESION_SHEET) return;
  if (range.getNumRows() !== 1 || range.getNumColumns() !== 1) return;
  if (range.getColumn() !== CLIENT_COLUMN) return;
  if (range.getRow() < FIRST_DATA_ROW_IMPRESION) return;

  const clientName = String(sheet.getRange(range.getRow(), CLIENT_COLUMN).getDisplayValue() || '').trim();
  if (!clientName) return;

  PropertiesService.getUserProperties().setProperties({
    impresion_last_client_name: clientName,
    impresion_last_client_row: String(range.getRow())
  });
}

function showSelectedClientCdrModal() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  if (sheet.getName() !== IMPRESION_SHEET) {
    SpreadsheetApp.getUi().alert('Primero parate en la hoja "impresion".');
    return;
  }

  const row = sheet.getActiveRange().getRow();
  if (row < FIRST_DATA_ROW_IMPRESION) {
    SpreadsheetApp.getUi().alert('Selecciona una fila valida de la hoja "impresion".');
    return;
  }

  const clientName = String(sheet.getRange(row, CLIENT_COLUMN).getDisplayValue() || '').trim();
  if (!clientName) {
    SpreadsheetApp.getUi().alert('La columna cliente esta vacia en la fila seleccionada.');
    return;
  }

  openLocalClientCdrModal_(clientName, row);
}

function showLastEditedClientCdrModal() {
  const props = PropertiesService.getUserProperties();
  const clientName = String(props.getProperty('impresion_last_client_name') || '').trim();
  const row = String(props.getProperty('impresion_last_client_row') || '').trim();

  if (!clientName) {
    SpreadsheetApp.getUi().alert('Todavia no hay un cliente editado recientemente.');
    return;
  }

  openLocalClientCdrModal_(clientName, row);
}

function openLocalClientCdrModal_(clientName, row) {
  const template = HtmlService.createTemplateFromFile('cliente_cdr_modal');
  template.data = {
    clientName: clientName,
    baseClientName: clientName,
    initialSearchTerm: clientName,
    row: row || '',
    localApiBase: LOCAL_API_BASE,
    guideImages: buildGuideImagesPayload_(clientName)
  };

  const html = template.evaluate()
    .setWidth(1460)
    .setHeight(900);

  SpreadsheetApp.getUi().showModalDialog(html, 'Comparacion guia Drive vs CDR');
}

function buildGuideImagesPayload_(clientName) {
  const termInfo = buildSearchTerms_(clientName);
  const items = findDriveGuideCandidates_(termInfo);

  if (!items.length) {
    return {
      status: 'warning',
      message: 'No se encontraron imagenes guia en Drive para "' + clientName + '".',
      items: [],
      selectedId: ''
    };
  }

  return {
    status: 'ok',
    message: items.length === 1
      ? 'Se encontro 1 imagen guia en Drive.'
      : 'Se encontraron ' + items.length + ' imagenes guia en Drive.',
    items: items,
    selectedId: items[0].fileId
  };
}

function searchGuideImagesForModal(clientName) {
  const safeClientName = String(clientName || '').trim();
  if (!safeClientName) {
    return {
      status: 'warning',
      message: 'Escribe un nombre para buscar imagenes guia.',
      items: [],
      selectedId: ''
    };
  }

  return buildGuideImagesPayload_(safeClientName);
}

function findDriveGuideCandidates_(termInfo) {
  const candidates = [];
  const seen = {};
  const queries = buildDriveQueries_(termInfo);

  queries.forEach(function(queryInfo) {
    const iterator = DriveApp.searchFiles(queryInfo.query);
    while (iterator.hasNext()) {
      const file = iterator.next();
      const fileId = file.getId();
      if (seen[fileId]) continue;

      const fileName = String(file.getName() || '');
      const scoreInfo = scoreDriveCandidate_(fileName, termInfo);
      if (scoreInfo.score <= 0) continue;

      seen[fileId] = true;
      candidates.push({
        fileId: fileId,
        fileName: fileName,
        imageUrl: 'https://drive.google.com/thumbnail?id=' + encodeURIComponent(fileId) + '&sz=w1600',
        openUrl: 'https://drive.google.com/file/d/' + fileId + '/view',
        modifiedAt: file.getLastUpdated().toISOString(),
        matchReason: scoreInfo.reason,
        score: scoreInfo.score
      });

      if (candidates.length >= MAX_DRIVE_GUIDE_CANDIDATES) {
        break;
      }
    }
  });

  candidates.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    return String(b.modifiedAt).localeCompare(String(a.modifiedAt));
  });

  return candidates.slice(0, MAX_DRIVE_GUIDE_CANDIDATES);
}

function buildDriveQueries_(termInfo) {
  const baseParts = ["trashed = false", "(mimeType contains 'image/')"];
  if (DRIVE_GUIDE_FOLDER_ID) {
    baseParts.push("'" + DRIVE_GUIDE_FOLDER_ID.replace(/'/g, "\\'") + "' in parents");
  }

  const terms = [];
  if (termInfo.raw) terms.push({ value: termInfo.raw, reason: 'full_name' });
  if (termInfo.acronym && termInfo.acronym !== termInfo.raw) terms.push({ value: termInfo.acronym, reason: 'acronym' });
  (termInfo.tokens || []).forEach(function(token) {
    if (!terms.some(function(existing) { return existing.value === token; })) {
      terms.push({ value: token, reason: 'token' });
    }
  });

  return terms.map(function(term) {
    const escaped = term.value.replace(/'/g, "\\'");
    return {
      reason: term.reason,
      query: baseParts.concat(["title contains '" + escaped + "'"]).join(' and ')
    };
  });
}

function buildSearchTerms_(clientName) {
  const raw = normalizeTextWithSpaces_(clientName);
  const words = raw ? raw.split(' ') : [];
  const stopwords = { DE: true, DEL: true, LA: true, LAS: true, LOS: true, EL: true, Y: true, SA: true, SRL: true };
  const tokens = words.filter(function(word) {
    return word && word.length >= 3 && !stopwords[word];
  });
  const compact = words.join('');
  const acronym = tokens.length > 1 ? tokens.map(function(word) { return word[0]; }).join('') : '';

  return {
    raw: raw,
    compact: compact,
    acronym: acronym || (words.length === 1 && words[0].length <= 6 ? words[0] : ''),
    tokens: tokens.length ? tokens : words
  };
}

function scoreDriveCandidate_(fileName, termInfo) {
  const normalized = normalizeText_(fileName);
  if (!normalized) return { score: 0, reason: '' };

  if (termInfo.acronym && normalized.indexOf(termInfo.acronym) >= 0) {
    return { score: 400 + termInfo.acronym.length, reason: 'acronym' };
  }

  if (termInfo.compact && normalized.indexOf(termInfo.compact) >= 0) {
    return { score: 320 + termInfo.compact.length, reason: 'full_name' };
  }

  const tokenHits = (termInfo.tokens || []).filter(function(token) {
    return token && normalized.indexOf(token) >= 0;
  });
  if (tokenHits.length) {
    return {
      score: 220 + tokenHits.join('').length,
      reason: 'token'
    };
  }

  return { score: 0, reason: '' };
}

function normalizeText_(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
}

function normalizeTextWithSpaces_(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
```

## Integracion con un proyecto que ya tiene `onEdit(e)`

Si tu Apps Script ya usa `08_AutomatizacionesHoja_REVISADO.gs` o cualquier otro
`onEdit(e)` existente, **no agregues otro `onEdit`** para este modal.

En ese caso, en tu `Code.gs` del modal deja:

- `onOpen()`
- `showSelectedClientCdrModal()`
- `showLastEditedClientCdrModal()`
- `openLocalClientCdrModal_()`
- `buildGuideImagesPayload_()`
- `searchGuideImagesForModal()`
- helpers de Drive y normalizacion
- `rememberLastEditedPrintClient_(e)`

Y **borra** cualquier `function onEdit(e)` que hayas copiado desde esta guia.

Y llamala desde tu flujo actual de edicion.

### Cambio recomendado en `08_AutomatizacionesHoja_REVISADO.gs`

Pega esta funcion en el proyecto:

```javascript
function rememberLastEditedPrintClient_(e) {
  if (!e || !e.range) return;

  const range = e.range;
  const sheet = range.getSheet();

  if (sheet.getName() !== IMPRESION_SHEET) return;
  if (range.getNumRows() !== 1 || range.getNumColumns() !== 1) return;
  if (range.getColumn() !== CLIENT_COLUMN) return;
  if (range.getRow() < FIRST_DATA_ROW_IMPRESION) return;

  const clientName = String(sheet.getRange(range.getRow(), CLIENT_COLUMN).getDisplayValue() || '').trim();
  if (!clientName) return;

  PropertiesService.getUserProperties().setProperties({
    impresion_last_client_name: clientName,
    impresion_last_client_row: String(range.getRow())
  });
}
```

Luego, dentro de `handlePrintSheetEdit_(sheet, range)`, agrega esto al comienzo:

```javascript
function handlePrintSheetEdit_(sheet, range) {
  rememberLastEditedPrintClient_({
    range: range
  });

  // ...resto de la logica existente...
}
```

Si prefieres llamarla desde el `onEdit(e)` principal, tambien sirve:

```javascript
function onEdit(e) {
  automatizacionEditar(e);
  rememberLastEditedPrintClient_(e);
}
```

La primera opcion suele ser la mas segura si ya tienes automatizaciones de la
hoja `IMPRESION`.

### Resumen practico

Si ya usas `08_AutomatizacionesHoja_REVISADO.gs`:

1. No copies el `onEdit(e)` del modal.
2. Si ya lo copiaste, borrarlo.
3. Deja `rememberLastEditedPrintClient_(e)` en `Code.gs` o muévela al archivo de automatizaciones.
4. Llama a `rememberLastEditedPrintClient_({ range: range })` desde `handlePrintSheetEdit_(sheet, range)`.

Con eso el modal sigue funcionando y no se rompe el ordenado automatico.

## Apps Script `.html`

Crear un archivo HTML llamado `cliente_cdr_modal` y pegar esto:

```html
<!DOCTYPE html>
<html>
  <head>
    <base target="_top">
    <style>
      :root {
        --bg: #f4eadc;
        --panel: #fffaf2;
        --line: #d6891b;
        --ink: #24180b;
        --muted: #7b5a40;
        --accent: #ef8b12;
        --ok: #3d8b40;
        --warn: #a86911;
        --error: #b74f43;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        background: var(--bg);
        color: var(--ink);
        font-family: Arial, sans-serif;
      }

      .wrap {
        display: grid;
        grid-template-rows: auto 1fr;
        min-height: 100vh;
      }

      .topbar {
        padding: 16px 18px 0;
      }

      .content {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 360px;
        gap: 18px;
        padding: 18px;
        align-items: start;
      }

      .workspace {
        background: linear-gradient(180deg, rgba(255,250,242,0.96), rgba(255,246,233,0.92));
        border: 2px solid var(--line);
        border-radius: 18px;
        padding: 16px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
      }

      .workspace-header {
        border-bottom: 2px solid rgba(214,137,27,0.18);
        padding-bottom: 14px;
        margin-bottom: 16px;
      }

      .workspace-title {
        display: flex;
        justify-content: space-between;
        gap: 14px;
        align-items: flex-start;
        flex-wrap: wrap;
      }

      .workspace-title h2 {
        margin: 0;
        font-size: 24px;
      }

      .workspace-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(239, 139, 18, 0.12);
        color: #8b5411;
        border: 1px solid rgba(214,137,27,0.28);
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: bold;
      }

      .search-block {
        display: grid;
        gap: 8px;
        margin-top: 14px;
      }

      .compare-shell {
        background: rgba(255,255,255,0.55);
        border: 2px solid rgba(214,137,27,0.18);
        border-radius: 18px;
        padding: 14px;
      }

      .compare {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }

      .panel {
        background: var(--panel);
        border: 2px solid var(--line);
        border-radius: 14px;
        padding: 14px;
      }

      .compare-panel {
        background: rgba(255, 251, 244, 0.92);
      }

      .compare-panel .toolbar {
        justify-content: space-between;
      }

      .compare-title {
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: 0;
      }

      .compare-title strong {
        display: block;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .action-group {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }

      .sidebar {
        display: grid;
        gap: 16px;
        position: sticky;
        top: 18px;
      }

      .sidebar-panel {
        background: linear-gradient(180deg, rgba(255,250,242,0.98), rgba(255,246,233,0.95));
      }

      .sidebar-panel h3 {
        margin: 0 0 12px;
      }

      .sidebar-footer {
        margin-top: 14px;
        padding-top: 12px;
        border-top: 2px solid rgba(214,137,27,0.14);
      }

      .meta {
        color: var(--muted);
        font-size: 13px;
        margin: 6px 0 12px;
      }

      .banner {
        padding: 10px 12px;
        border-radius: 10px;
        margin-bottom: 10px;
      }

      .banner.ok {
        background: #e9f8e7;
        border: 2px solid #72b36c;
        color: var(--ok);
      }

      .banner.warning {
        background: #fff1cf;
        border: 2px solid #e0b24b;
        color: var(--warn);
      }

      .banner.error {
        background: #ffe2df;
        border: 2px solid #d35a4b;
        color: var(--error);
      }

      .toolbar {
        display: flex;
        gap: 10px;
        align-items: center;
        margin-bottom: 12px;
        flex-wrap: wrap;
      }

      .search-bar {
        display: grid;
        grid-template-columns: minmax(260px, 1fr) auto auto auto;
        gap: 10px;
        align-items: center;
        width: 100%;
      }

      .search-help {
        color: var(--muted);
        font-size: 12px;
        margin-top: 2px;
        line-height: 1.4;
      }

      button {
        border: 0;
        background: var(--accent);
        color: white;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: bold;
        cursor: pointer;
      }

      button[disabled] {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .preview {
        width: 100%;
        height: 520px;
        border: 2px solid var(--line);
        border-radius: 12px;
        background: white;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
      }

      .preview img {
        width: 100%;
        height: 100%;
        object-fit: contain;
      }

      .empty {
        color: var(--muted);
        font-style: italic;
        text-align: center;
        padding: 20px;
      }

      .list {
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-height: 320px;
        overflow: auto;
      }

      .list.large {
        max-height: 430px;
      }

      .item {
        background: white;
        border: 2px solid var(--line);
        border-radius: 12px;
        padding: 10px;
        cursor: pointer;
      }

      .item.active {
        outline: 3px solid #f1b860;
        background: #fff7eb;
      }

      .item-title {
        font-weight: bold;
        word-break: break-word;
      }

      .item-sub {
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
        word-break: break-word;
      }

      .badge {
        display: inline-block;
        margin-top: 8px;
        margin-right: 6px;
        background: #fff0cf;
        border: 1px solid #d7a13a;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 12px;
      }

      .search-input {
        width: 100%;
        border: 2px solid var(--line);
        border-radius: 10px;
        padding: 10px 12px;
        background: white;
        color: var(--ink);
        font-size: 14px;
      }

      .btn-secondary {
        background: #b8741d;
      }

      .inline-select {
        min-width: 230px;
        max-width: 260px;
      }

      @media (max-width: 900px) {
        .content {
          grid-template-columns: 1fr;
        }

        .search-bar {
          grid-template-columns: 1fr;
        }

        .compare {
          grid-template-columns: 1fr;
        }

        .sidebar {
          position: static;
        }
      }
    </style>
    <script>
      const data = <?!= JSON.stringify(data) ?>;
      const PREWARM_CDR_PREVIEWS = 8;
      const PREPARE_PROFILE_LABELS = {
        tarjetas_plasticas: 'Tarjetas plasticas',
        tarjetas_laminar_tinta_a: 'Tarjetas para laminar / tinta - Impresora A',
        tarjetas_laminar_tinta_b: 'Tarjetas para laminar / tinta - Impresora B'
      };
      let loaded = null;
      let currentSearchTerm = (data.initialSearchTerm || data.clientName || '').trim();
      let currentMatchMode = 'strict';
      let currentPrepareProfileId = '';
      let availablePrepareProfiles = [];
      let selectedItemId = '';
      let selectedGuideId = (data.guideImages && data.guideImages.selectedId) || '';
      let filterCreditoOnly = false;
      let openInCorelBusy = false;
      const requestedPrewarmSignatures = {};
      let currentGuideImages = data.guideImages || { status: 'warning', message: 'Sin imagen guia', items: [], selectedId: '' };

      function escapeHtml(text) {
        return String(text)
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#039;');
      }

      async function loadAssets() {
        const searchTerm = currentSearchTerm;
        if (!searchTerm) {
          loaded = null;
          renderMessages([], 'Escribe un nombre para buscar archivos CDR.');
          renderCdrPreview(null);
          renderCdrList([]);
          setLocalStatus('warning', 'Esperando termino de busqueda...');
          return;
        }

        setLocalStatus('warning', 'Consultando API local...');
        try {
          await loadLocalApiConfig();
          const url = data.localApiBase
            + '/api/client-assets/search?client_name=' + encodeURIComponent(searchTerm)
            + '&match_mode=' + encodeURIComponent(currentMatchMode);
          const response = await fetch(url);
          const payload = await response.json();

          if (!response.ok) {
            throw new Error(payload.detail || 'No se pudo consultar la API local.');
          }

          loaded = payload;
          setLocalStatus('ok', 'Conexion local OK');
          renderAll();
        } catch (error) {
          loaded = null;
          renderMessages([], String(error));
          renderCdrPreview(null);
          renderCdrList([]);
          setLocalStatus('error', 'No se pudo consultar la API local');
        }
      }

      function setLocalStatus(kind, text) {
        const el = document.getElementById('localStatus');
        el.className = 'banner ' + kind;
        el.textContent = text;
      }

      function renderGuideStatus() {
        const guide = currentGuideImages || {};
        const el = document.getElementById('guideStatus');
        el.className = 'banner ' + (guide.status || 'warning');
        el.textContent = guide.message || 'Sin imagen guia';
      }

      function renderMessages(warnings, errorText) {
        const el = document.getElementById('messages');
        const parts = [];

        if (errorText) {
          parts.push('<div class="banner error">' + escapeHtml(errorText) + '</div>');
        }

        (warnings || []).forEach(msg => {
          parts.push('<div class="banner warning">' + escapeHtml(msg) + '</div>');
        });

        el.innerHTML = parts.join('');
      }

      function setCorelActionStatus(kind, text) {
        const el = document.getElementById('corelActionStatus');
        if (!text) {
          el.innerHTML = '';
          return;
        }
        el.innerHTML = '<div class="banner ' + kind + '">' + escapeHtml(text) + '</div>';
      }

      function filteredItems() {
        if (!loaded || !loaded.items) return [];
        if (!filterCreditoOnly) return loaded.items;
        return loaded.items.filter(item => item.contains_credito);
      }

      function getSelectedGuide() {
        const guide = currentGuideImages || {};
        const items = guide.items || [];
        return items.find(item => item.fileId === selectedGuideId) || items[0] || null;
      }

      function syncSearchInput() {
        const input = document.getElementById('searchTermInput');
        if (input && input.value !== currentSearchTerm) {
          input.value = currentSearchTerm;
        }
      }

      function syncMatchModeInput() {
        const input = document.getElementById('matchModeInput');
        if (input && input.value !== currentMatchMode) {
          input.value = currentMatchMode;
        }
      }

      async function loadLocalApiConfig() {
        const response = await fetch(data.localApiBase + '/api/client-assets/config');
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || 'No se pudo cargar la configuracion local.');
        }

        syncPrepareProfiles(payload.corel_prepare_profiles || {});
      }

      function syncPrepareProfiles(rawProfiles) {
        availablePrepareProfiles = Object.entries(rawProfiles || {})
          .filter(entry => entry[1] && typeof entry[1] === 'object')
          .map(entry => {
            const profileId = String(entry[0] || '').trim();
            const profile = entry[1] || {};
            return {
              id: profileId,
              label: String(profile.label || PREPARE_PROFILE_LABELS[profileId] || profileId).trim()
            };
          });

        if (!availablePrepareProfiles.length) {
          currentPrepareProfileId = '';
          renderPrepareProfileOptions();
          return;
        }

        if (!availablePrepareProfiles.some(profile => profile.id === currentPrepareProfileId)) {
          currentPrepareProfileId = availablePrepareProfiles[0].id;
        }
        renderPrepareProfileOptions();
      }

      function renderPrepareProfileOptions() {
        const input = document.getElementById('prepareProfileInput');
        if (!input) return;

        if (!availablePrepareProfiles.length) {
          input.innerHTML = '<option value="">Sin perfiles configurados</option>';
          input.disabled = true;
          updateCorelActionButtons();
          return;
        }

        input.disabled = false;
        input.innerHTML = availablePrepareProfiles.map(profile => (
          '<option value="' + escapeHtml(profile.id) + '">' + escapeHtml(profile.label) + '</option>'
        )).join('');
        input.value = currentPrepareProfileId;
        updateCorelActionButtons();
      }

      function setGuideLoadingState() {
        currentGuideImages = {
          status: 'warning',
          message: 'Buscando imagenes guia en Drive...',
          items: [],
          selectedId: ''
        };
        selectedGuideId = '';
        renderGuideStatus();
        renderGuideList();
        renderGuidePreview();
      }

      function loadGuideImages(searchTerm) {
        const safeSearchTerm = String(searchTerm || '').trim();
        if (!safeSearchTerm) {
          currentGuideImages = {
            status: 'warning',
            message: 'Escribe un nombre para buscar imagenes guia.',
            items: [],
            selectedId: ''
          };
          selectedGuideId = '';
          renderGuideStatus();
          renderGuideList();
          renderGuidePreview();
          return;
        }

        setGuideLoadingState();
        google.script.run
          .withSuccessHandler(function(payload) {
            currentGuideImages = payload || { status: 'warning', message: 'Sin imagen guia', items: [], selectedId: '' };
            selectedGuideId = (currentGuideImages && currentGuideImages.selectedId) || '';
            renderGuideStatus();
            renderGuideList();
            renderGuidePreview();
          })
          .withFailureHandler(function(error) {
            currentGuideImages = {
              status: 'error',
              message: String((error && error.message) || error || 'No se pudieron buscar imagenes guia en Drive.'),
              items: [],
              selectedId: ''
            };
            selectedGuideId = '';
            renderGuideStatus();
            renderGuideList();
            renderGuidePreview();
          })
          .searchGuideImagesForModal(safeSearchTerm);
      }

      function runSearch(termOverride) {
        currentSearchTerm = String(termOverride || document.getElementById('searchTermInput').value || '').trim();
        currentMatchMode = String(document.getElementById('matchModeInput').value || 'strict').trim();
        syncSearchInput();
        syncMatchModeInput();
        selectedItemId = '';
        setCorelActionStatus('', '');
        loadGuideImages(currentSearchTerm);
        loadAssets();
      }

      function resetSearchTerm() {
        runSearch(data.baseClientName || data.clientName || '');
      }

      function handleSearchInputKeydown(event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          runSearch();
        }
      }

      function handleMatchModeChange() {
        currentMatchMode = String(document.getElementById('matchModeInput').value || 'strict').trim();
        runSearch();
      }

      function handlePrepareProfileChange() {
        currentPrepareProfileId = String(document.getElementById('prepareProfileInput').value || '').trim();
        updateCorelActionButtons();
      }

      function getSelectedCdrItem() {
        if (!loaded || !loaded.items) return null;
        return loaded.items.find(item => item.item_id === selectedItemId) || null;
      }

      function buildPreviewUrl(item) {
        return data.localApiBase + item.preview_url;
      }

      function prewarmCdrPreviews(items) {
        const itemIds = (items || [])
          .slice(0, PREWARM_CDR_PREVIEWS)
          .map(item => item.item_id)
          .filter(Boolean);

        if (!itemIds.length) return;

        const signature = itemIds.join('|');
        if (requestedPrewarmSignatures[signature]) return;
        requestedPrewarmSignatures[signature] = true;

        fetch(data.localApiBase + '/api/client-assets/prewarm-previews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            item_ids: itemIds,
            limit: PREWARM_CDR_PREVIEWS,
            force_refresh: false
          })
        }).catch(() => {});
      }

      function renderAll() {
        renderGuideStatus();
        renderGuideList();
        renderGuidePreview();

        if (!loaded) return;

        document.getElementById('clientName').textContent = loaded.client_name || currentSearchTerm || data.clientName;
        document.getElementById('rowInfo').textContent = data.row ? ('Fila: ' + data.row) : '';
        document.getElementById('baseClientName').textContent = data.baseClientName
          ? ('Cliente en celda: ' + data.baseClientName)
          : '';

        const directories = (loaded.matched_directories || []).join(' | ');
        document.getElementById('folderPath').textContent = directories || loaded.folder_path || 'Sin coincidencias';

        renderMessages(loaded.warnings || [], '');

        const items = filteredItems();
        prewarmCdrPreviews(items);
        renderCdrList(items);

        if (items.length === 0) {
          selectedItemId = '';
          renderCdrPreview(null);
          return;
        }

        const selected = items.find(x => x.item_id === selectedItemId) || items[0];
        selectedItemId = selected.item_id;
        renderCdrPreview(selected);
      }

      function renderGuideList() {
        const guide = currentGuideImages || {};
        const items = guide.items || [];
        const el = document.getElementById('guideList');

        if (!items.length) {
          el.innerHTML = '<div class="empty">No hay imagenes guia para este cliente.</div>';
          return;
        }

        el.innerHTML = items.map(item => {
          const activeClass = item.fileId === selectedGuideId ? ' active' : '';
          const matchReason = item.matchReason ? '<div class="badge">' + escapeHtml(item.matchReason) + '</div>' : '';
          return (
            '<div class="item' + activeClass + '" onclick="selectGuide(\'' + item.fileId + '\')">' +
              '<div class="item-title">' + escapeHtml(item.fileName) + '</div>' +
              '<div class="item-sub">' + escapeHtml(item.modifiedAt) + '</div>' +
              matchReason +
            '</div>'
          );
        }).join('');
      }

      function renderGuidePreview() {
        const guide = getSelectedGuide();
        const title = document.getElementById('guideTitle');
        const box = document.getElementById('guidePreview');
        const openLink = document.getElementById('openGuideLink');

        title.textContent = guide ? guide.fileName : 'JPG guia';
        if (!guide) {
          box.innerHTML = '<div class="empty">No hay JPG guia disponible para este cliente.</div>';
          openLink.style.display = 'none';
          return;
        }

        box.innerHTML = '<img src="' + guide.imageUrl + '" alt="' + escapeHtml(guide.fileName) + '">';
        openLink.href = guide.openUrl;
        openLink.style.display = 'inline-block';
      }

      function renderCdrList(items) {
        const el = document.getElementById('cdrList');

        if (!items.length) {
          el.innerHTML = '<div class="empty">No hay archivos CDR para mostrar.</div>';
          return;
        }

        el.innerHTML = items.map(item => {
          const activeClass = item.item_id === selectedItemId ? ' active' : '';
          const credito = item.contains_credito ? '<div class="badge">Credito</div>' : '';
          const matchReason = item.match_reason ? '<div class="badge">' + escapeHtml(item.match_reason) + '</div>' : '';
          return (
            '<div class="item' + activeClass + '" onclick="selectCdr(\'' + item.item_id + '\')">' +
              '<div class="item-title">' + escapeHtml(item.name) + '</div>' +
              '<div class="item-sub">' + escapeHtml(item.relative_path) + '</div>' +
              credito + matchReason +
            '</div>'
          );
        }).join('');
      }

      function renderCdrPreview(item) {
        const title = document.getElementById('cdrTitle');
        const box = document.getElementById('cdrPreview');
        const openLink = document.getElementById('openCdrPreviewLink');

        if (!item) {
          title.textContent = 'Preview CDR';
          box.innerHTML = '<div class="empty">No hay archivo seleccionado.</div>';
          openLink.style.display = 'none';
          updateCorelActionButtons();
          return;
        }

        title.textContent = item.name;
        const previewUrl = buildPreviewUrl(item);
        box.innerHTML = '<img src="' + previewUrl + '" alt="' + escapeHtml(item.name) + '">';
        openLink.href = previewUrl;
        openLink.style.display = 'inline-block';
        updateCorelActionButtons();
      }

      function updateCorelActionButtons() {
        const openCorelButton = document.getElementById('openInCorelButton');
        const openAndPrepareButton = document.getElementById('openAndPrepareButton');
        const hasItem = !!getSelectedCdrItem();

        if (openCorelButton) {
          openCorelButton.disabled = !hasItem || openInCorelBusy;
        }
        if (openAndPrepareButton) {
          openAndPrepareButton.disabled = !hasItem || openInCorelBusy || !currentPrepareProfileId;
        }
      }

      async function openSelectedCdrInCorel(mode) {
        const item = getSelectedCdrItem();
        if (!item || openInCorelBusy) return;

        const safeMode = String(mode || 'open_only');
        if (safeMode === 'open_and_prepare' && !currentPrepareProfileId) {
          setCorelActionStatus('error', 'Selecciona un perfil de preparacion antes de usar "Abrir y preparar".');
          return;
        }

        openInCorelBusy = true;
        updateCorelActionButtons();
        setCorelActionStatus('warning', safeMode === 'open_and_prepare' ? 'Abriendo y preparando archivo en CorelDRAW...' : 'Abriendo archivo en CorelDRAW...');

        try {
          const body = {
            item_id: item.item_id,
            mode: safeMode
          };
          if (safeMode === 'open_and_prepare') {
            body.profile_id = currentPrepareProfileId;
          }

          const response = await fetch(data.localApiBase + '/api/client-assets/open-in-corel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          });
          const payload = await response.json();

          if (!response.ok) {
            throw new Error(payload.detail || 'No se pudo abrir el archivo en CorelDRAW. Revisar si Corel esta instalado y disponible.');
          }

          const warningText = (payload.warnings || []).join(' ');
          const message = warningText ? (payload.message + ' ' + warningText) : payload.message;
          setCorelActionStatus(warningText ? 'warning' : 'ok', message || 'Archivo abierto en CorelDRAW.');
        } catch (error) {
          setCorelActionStatus(
            'error',
            String((error && error.message) || error || 'No se pudo abrir el archivo en CorelDRAW. Revisar si Corel esta instalado y disponible.')
          );
        } finally {
          openInCorelBusy = false;
          updateCorelActionButtons();
        }
      }

      function selectGuide(fileId) {
        selectedGuideId = fileId;
        renderGuideList();
        renderGuidePreview();
      }

      function selectCdr(itemId) {
        selectedItemId = itemId;
        renderAll();
      }

      function toggleCreditoOnly(checkbox) {
        filterCreditoOnly = checkbox.checked;
        selectedItemId = '';
        renderAll();
      }
    </script>
  </head>
  <body onload="runSearch(currentSearchTerm)">
    <div class="wrap">
      <div class="topbar">
        <div id="messages"></div>
        <div id="guideStatus" class="banner warning">Buscando imagenes guia en Drive...</div>
        <div id="localStatus" class="banner warning">Consultando API local...</div>
        <div id="corelActionStatus"></div>
      </div>

      <div class="content">
        <div class="workspace">
          <div class="workspace-header">
            <div class="workspace-title">
              <div>
                <h2 id="clientName"></h2>
                <div class="meta">
                  <div id="rowInfo"></div>
                  <div id="baseClientName"></div>
                  <div id="folderPath"></div>
                </div>
              </div>
              <div class="workspace-chip">Comparacion local Drive + CDR</div>
            </div>

            <div class="search-block">
              <div class="search-bar">
                <input id="searchTermInput" class="search-input" type="text" value="" placeholder="Buscar cliente, sigla o termino alternativo" onkeydown="handleSearchInputKeydown(event)">
                <select id="matchModeInput" class="search-input" onchange="handleMatchModeChange()">
                  <option value="strict">Busqueda estricta</option>
                  <option value="broad">Busqueda amplia</option>
                </select>
                <button type="button" onclick="runSearch()">Buscar</button>
                <button type="button" class="btn-secondary" onclick="resetSearchTerm()">Usar nombre de la celda</button>
              </div>
              <div class="toolbar" style="margin-bottom: 0;">
                <div class="search-help">Puedes cambiar el termino de busqueda sin cerrar el modal. `Estricta` prioriza coincidencias exactas y `amplia` abre el filtro si necesitas encontrar variantes.</div>
                <label>
                  <input type="checkbox" onchange="toggleCreditoOnly(this)">
                  Solo archivos con "credito"
                </label>
                <button onclick="runSearch()">Actualizar</button>
              </div>
            </div>
          </div>

          <div class="compare-shell">
            <div class="compare">
              <div class="panel compare-panel">
                <div class="toolbar">
                  <div class="compare-title">
                    <strong id="guideTitle">JPG guia</strong>
                  </div>
                  <div class="action-group">
                    <a id="openGuideLink" href="#" target="_blank" style="display:none;">
                      <button type="button">Abrir JPG</button>
                    </a>
                  </div>
                </div>
                <div class="preview" id="guidePreview">
                  <div class="empty">Esperando imagen guia...</div>
                </div>
              </div>

              <div class="panel compare-panel">
                <div class="toolbar">
                  <div class="compare-title">
                    <strong id="cdrTitle">Preview CDR</strong>
                  </div>
                  <div class="action-group">
                    <select id="prepareProfileInput" class="search-input inline-select" onchange="handlePrepareProfileChange()">
                      <option value="">Sin perfiles configurados</option>
                    </select>
                    <a id="openCdrPreviewLink" href="#" target="_blank" style="display:none;">
                      <button type="button">Abrir preview</button>
                    </a>
                    <button id="openInCorelButton" type="button" onclick="openSelectedCdrInCorel('open_only')" disabled>Abrir en Corel</button>
                    <button id="openAndPrepareButton" type="button" onclick="openSelectedCdrInCorel('open_and_prepare')" disabled>Abrir y preparar</button>
                  </div>
                </div>
                <div class="preview" id="cdrPreview">
                  <div class="empty">Esperando datos del CDR...</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="sidebar">
          <div class="panel sidebar-panel">
            <h3>Imagenes guia Drive</h3>
            <div id="guideList" class="list"></div>
          </div>

          <div class="panel sidebar-panel">
            <h3>Variantes CDR</h3>
            <div id="cdrList" class="list large"></div>
            <div class="sidebar-footer">
              <button onclick="google.script.host.close()">Cerrar</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
```

## Flujo recomendado para el usuario final

### Configuracion previa en Google Sheets

1. Abrir la planilla
2. Entrar a `Extensiones > Apps Script`
3. Crear el archivo `Code.gs` y pegar el bloque `.gs`
4. Crear el archivo `cliente_cdr_modal` y pegar el bloque `.html`
5. Buscar esta linea en `Code.gs`:

```javascript
const DRIVE_GUIDE_FOLDER_ID = '';
```

6. Reemplazar el valor vacio por el `ID` de la carpeta de Drive donde estan los JPG guia, por ejemplo:

```javascript
const DRIVE_GUIDE_FOLDER_ID = '1AbCdEfGhIjKlMnOpQrStUvWxYz';
```

7. Guardar el proyecto
8. Volver a abrir la planilla

### Configuracion previa en la PC con Corel

1. En la PC con `CorelDRAW` ejecutar `configure_client_assets_api.bat`
2. Configurar la carpeta raiz local
3. Configurar `corel_prepare_profiles` si se va a usar `Abrir y preparar`
4. Ejecutar `start_client_assets_api.bat`
5. Abrir la planilla en esa misma PC
6. En la hoja `impresion`, seleccionar la fila cuyo cliente este en la columna `F`
7. Usar el menu `Impresion > Comparar guia Drive vs CDR`

## Notas

- el cliente se toma desde la columna `F`
- la API local usa ese nombre para buscar el `.cdr`
- las imagenes guia se buscan en Drive por ese mismo nombre
- dentro del modal puedes escribir otro termino y volver a buscar sin cerrar la ventana
- si se quiere limitar la busqueda a una carpeta especifica de Drive, completar `DRIVE_GUIDE_FOLDER_ID`
- si hay varias coincidencias de imagen, se listan y se puede elegir cual comparar
- el preview del `.cdr` intenta `CorelDRAW` primero y miniatura embebida despues
- el selector de perfil se carga desde `GET /api/client-assets/config` usando `corel_prepare_profiles`
- el boton `Abrir en Corel` usa `POST /api/client-assets/open-in-corel` con `mode: open_only`
- el boton `Abrir y preparar` usa `POST /api/client-assets/open-in-corel` con `mode: open_and_prepare` y `profile_id`
- si quieres acotar la busqueda de imagenes, completar `DRIVE_GUIDE_FOLDER_ID`
