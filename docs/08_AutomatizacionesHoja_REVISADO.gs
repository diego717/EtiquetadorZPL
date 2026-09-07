/** @OnlyCurrentDoc */

var SYNC_LOG_BUFFER = [];

/**
 * Automatizaciones locales que no requieren autorización.
 *
 * IMPORTANTE:
 * crearEnlaceAlEditar(e) utiliza Odoo/UrlFetchApp y debe conservar su propio
 * activador instalable "Al editarse". No debe llamarse desde este onEdit simple.
 */


function onEdit(e) {
  automatizacionEditar(e);
}

function notificarVentaNeoFinalizadaAlEditar(e) {
  if (!e || !e.range) return;

  const range = e.range;
  if (range.getNumRows() !== 1 || range.getNumColumns() !== 1) return;
  if (range.getRow() < CFG.FIRST_DATA_ROW) return;
  if (range.getColumn() !== CFG.STATE_COL) return;

  const sheet = range.getSheet();
  const sheetName = cleanString_(sheet.getName()).toUpperCase();
  if (sheetName !== CFG.SHEET_NAME.toUpperCase()) return;

  const currentState = cleanString_(range.getDisplayValue()).toLowerCase();
  const oldState = cleanString_(e.oldValue).toLowerCase();
  const row = range.getRow();

  applyJobsSheetStateSideEffectsForRow_(sheet, row, currentState);
  SpreadsheetApp.flush();
  logOperationalStateNotificationDebug_(
    sheet,
    row,
    oldState,
    currentState,
    "pre_notificacion"
  );

  const finalizationNotifiedKeys = getSalesFinalizationNotifiedKeys_();
  const approvalNotifiedKeys = getSalesApprovalNotifiedKeys_();
  const pausedNotifiedKeys = getSalesPausedNotifiedKeys_();
  const manufacturingFinalizationNotifiedKeys =
    typeof getManufacturingFinalizationNotifiedKeys_ === "function"
      ? getManufacturingFinalizationNotifiedKeys_()
      : new Set();
  let finalizationChanged = false;
  let approvalChanged = false;
  let pausedChanged = false;
  let manufacturingFinalizationChanged = false;

  finalizationChanged = syncSalesFinalizationNotificationForRow_(
    sheet,
    row,
    oldState,
    currentState,
    finalizationNotifiedKeys
  );
  approvalChanged = syncSalesApprovalNotificationForRow_(
    sheet,
    row,
    oldState,
    currentState,
    approvalNotifiedKeys
  );
  pausedChanged = syncSalesPausedNotificationForRow_(
    sheet,
    row,
    oldState,
    currentState,
    pausedNotifiedKeys
  );
  if (
    typeof syncManufacturingFinalizationNotificationForRow_ === "function"
  ) {
    manufacturingFinalizationChanged =
      syncManufacturingFinalizationNotificationForRow_(
        sheet,
        row,
        oldState,
        currentState,
        manufacturingFinalizationNotifiedKeys
      );
  }

  if (finalizationChanged) {
    saveSalesFinalizationNotifiedKeys_(finalizationNotifiedKeys);
  }

  if (approvalChanged) {
    saveSalesApprovalNotifiedKeys_(approvalNotifiedKeys);
  }

  if (pausedChanged) {
    saveSalesPausedNotifiedKeys_(pausedNotifiedKeys);
  }

  if (
    manufacturingFinalizationChanged &&
    typeof saveManufacturingFinalizationNotifiedKeys_ === "function"
  ) {
    saveManufacturingFinalizationNotifiedKeys_(
      manufacturingFinalizationNotifiedKeys
    );
  }

  logOperationalStateNotificationDebug_(
    sheet,
    row,
    oldState,
    currentState,
    "post_notificacion",
    {
      salesFinalized: finalizationChanged,
      salesApproval: approvalChanged,
      salesPaused: pausedChanged,
      manufacturingFinalized: manufacturingFinalizationChanged,
    }
  );

  ejecutarOrdenadoAutomatico();
}

function automatizacionEditar(e) {
  if (!e || !e.range) return;

  const range = e.range;
  const sheet = range.getSheet();
  const sheetName = cleanString_(sheet.getName()).toUpperCase();

  if (sheetName === CFG.SHEET_NAME.toUpperCase()) {
    handleJobsSheetEdit_(sheet, range);
    return;
  }

  if (sheetName === "IMPRESION") {
    handlePrintSheetEdit_(sheet, range);
  }
}

function handleJobsSheetEdit_(sheet, range) {
  const firstRow = Math.max(range.getRow(), CFG.FIRST_DATA_ROW);
  const lastRow = range.getLastRow();

  if (firstRow > lastRow) return;
  if (!rangeIncludesColumn_(range, CFG.STATE_COL)) return;

  const editedValues = range.getValues();
  const stateOffset = CFG.STATE_COL - range.getColumn();

  for (let row = firstRow; row <= lastRow; row++) {
    const value = editedValues[row - range.getRow()][stateOffset];
    const normalizedState = cleanString_(value).toLowerCase();
    applyJobsSheetStateSideEffectsForRow_(sheet, row, normalizedState);
  }
}

function applyJobsSheetStateSideEffectsForRow_(sheet, row, normalizedState) {
  const normalized = cleanString_(normalizedState).toLowerCase();

  if (normalized === "aprobar") {
    sheet.getRange(row, 8).clearContent();
  }

  if (
    normalized !== "aprobar" &&
    normalized !== "finalizado" &&
    normalized !== "pausado" &&
    normalized !== "archivar"
  ) {
    return;
  }

  const salesContext = getSalesFinalizationContextFromRow_(sheet, row);
  const isSalesRow =
    typeof isSalesContextRow_ === "function"
      ? isSalesContextRow_(sheet, row, salesContext)
      : cleanString_(salesContext.origin).toUpperCase() === "VENTA";

  if (!isSalesRow) return;

  const anchorUtcString = nowUtcString_();
  setSalesManualStateAnchor_(salesContext, anchorUtcString);
  if (
    normalized === "aprobar" &&
    typeof setSalesApprovalStateAnchorForRow_ === "function"
  ) {
    setSalesApprovalStateAnchorForRow_(
      sheet,
      row,
      anchorUtcString
    );
  }
}

function logOperationalStateNotificationDebug_(
  sheet,
  row,
  oldState,
  currentState,
  stage,
  extraData
) {
  if (typeof appendSyncLog_ !== "function" || !sheet || !row) {
    return;
  }

  try {
    const salesContext =
      typeof getSalesFinalizationContextFromRow_ === "function"
        ? getSalesFinalizationContextFromRow_(sheet, row)
        : null;
    const manufacturingContext =
      typeof getManufacturingFinalizationContextFromRow_ === "function"
        ? getManufacturingFinalizationContextFromRow_(sheet, row)
        : null;
    const salesOrigin = cleanString_(salesContext && salesContext.origin).toUpperCase();
    const manufacturingOrigin = cleanString_(
      manufacturingContext && manufacturingContext.origin
    ).toUpperCase();
    const details = [
      `stage=${cleanString_(stage)}`,
      `row=${row}`,
      `old=${cleanString_(oldState) || "(vacio)"}`,
      `current=${cleanString_(currentState) || "(vacio)"}`,
      `visible_order=${cleanString_(sheet.getRange(row, CFG.ORDER_COL).getDisplayValue()) || "(vacia)"}`,
      `visible_product=${cleanString_(sheet.getRange(row, 5).getDisplayValue()) || "(vacio)"}`,
      `visible_qty=${cleanString_(sheet.getRange(row, 6).getDisplayValue()) || "(vacio)"}`,
      `sales_origin=${salesOrigin || "(vacio)"}`,
      `sale_order_id=${cleanString_(salesContext && salesContext.saleOrderId) || "(vacio)"}`,
      `sale_line_id=${cleanString_(salesContext && salesContext.saleLineId) || "(vacio)"}`,
      `sale_line_code=${cleanString_(salesContext && salesContext.lineCode) || "(vacio)"}`,
      `mfg_origin=${manufacturingOrigin || "(vacio)"}`,
      `mfg_id=${cleanString_(manufacturingContext && manufacturingContext.manufacturingId) || "(vacio)"}`,
    ];

    if (extraData && typeof extraData === "object") {
      for (const key of Object.keys(extraData)) {
        details.push(`${key}=${cleanString_(extraData[key]) || "false"}`);
      }
    }

    appendSyncLog_({
      module: "ESTADOS",
      action: "edit_debug",
      order:
        cleanString_(sheet.getRange(row, CFG.ORDER_COL).getDisplayValue()) ||
        cleanString_(salesContext && salesContext.orderName) ||
        cleanString_(manufacturingContext && manufacturingContext.orderName),
      odooId:
        cleanString_(salesContext && salesContext.saleOrderId) ||
        cleanString_(manufacturingContext && manufacturingContext.manufacturingId),
      origin:
        salesOrigin ||
        manufacturingOrigin ||
        cleanString_(sheet.getName()).toUpperCase(),
      details: details.join(" | "),
    });

    if (typeof flushSyncLogBuffer_ === "function") {
      flushSyncLogBuffer_();
    }
  } catch (err) {
    try {
      appendSyncLog_({
        module: "ESTADOS",
        action: "edit_debug_error",
        order: cleanString_(sheet.getRange(row, CFG.ORDER_COL).getDisplayValue()),
        odooId: "",
        origin: cleanString_(sheet.getName()).toUpperCase(),
        details:
          `stage=${cleanString_(stage)} | row=${row} | ` +
          `error=${cleanString_(err && err.message) || "desconocido"}`,
      });
      if (typeof flushSyncLogBuffer_ === "function") {
        flushSyncLogBuffer_();
      }
    } catch (innerErr) {}
  }
}

function handlePrintSheetEdit_(sheet, range) {
  const clientColumn = 6;
  const firstDataRow = 8;

  if (!rangeIncludesColumn_(range, clientColumn)) return;

  const firstRow = Math.max(range.getRow(), firstDataRow);
  const lastRow = range.getLastRow();
  if (firstRow > lastRow) return;

  const editedValues = range.getValues();
  const clientOffset = clientColumn - range.getColumn();
  const previousClientValues = buildPreviousClientValuesMap_(
    sheet,
    firstRow - 1,
    firstDataRow
  );

  for (let row = firstRow; row <= lastRow; row++) {
    const clientValue = editedValues[row - range.getRow()][clientOffset];
    const clientKey = normalizeAutomationText_(clientValue);
    const dateCell = sheet.getRange(row, 1);
    const rememberedValueCell = sheet.getRange(row, 4);

    if (!clientKey) {
      dateCell.clearContent();
      rememberedValueCell.clearContent();
      continue;
    }

    if (!dateCell.getValue()) {
      dateCell.setValue(new Date()).setNumberFormat("dd/mm/yyyy");
    }

    rememberedValueCell.clearContent();

    if (previousClientValues.has(clientKey)) {
      rememberedValueCell.setValue(previousClientValues.get(clientKey));
    }

    const currentRememberedValue = rememberedValueCell.getValue();
    if (currentRememberedValue !== "") {
      previousClientValues.set(clientKey, currentRememberedValue);
    }
  }
}

function buildPreviousClientValuesMap_(sheet, lastHistoryRow, firstDataRow) {
  const map = new Map();
  if (lastHistoryRow < firstDataRow) return map;

  const values = sheet
    .getRange(
      firstDataRow,
      4,
      lastHistoryRow - firstDataRow + 1,
      3
    )
    .getValues();

  for (const rowValues of values) {
    const rememberedValue = rowValues[0];
    const clientKey = normalizeAutomationText_(rowValues[2]);

    if (clientKey && rememberedValue !== "") {
      map.set(clientKey, rememberedValue);
    }
  }

  return map;
}

function rangeIncludesColumn_(range, column) {
  return range.getColumn() <= column && range.getLastColumn() >= column;
}

function normalizeAutomationText_(value) {
  return cleanString_(value).toLowerCase();
}

function getAutomationSpreadsheet_() {
  const activeSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (activeSpreadsheet) {
    return activeSpreadsheet;
  }

  if (typeof getTargetSheet_ === "function") {
    const targetSheet = getTargetSheet_();
    if (targetSheet) {
      return targetSheet.getParent();
    }
  }

  return null;
}

/**
 * Recalcula prioridades, repara fórmulas faltantes y ordena TRABAJOS.
 */
function ejecutarOrdenadoAutomatico() {
  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) return;
  const sheet = spreadsheet.getSheetByName(CFG.SHEET_NAME);
  if (!sheet) return;

  SpreadsheetApp.flush();

  const lastOperationalRow = getOperationalLastRow_(sheet);
  if (lastOperationalRow < CFG.FIRST_DATA_ROW) return;

  ensureDeliveryDaysFormulasForActiveRows_(sheet, lastOperationalRow);

  const priorityMap = buildStatePriorityMap_(sheet);
  const rowCount = lastOperationalRow - CFG.FIRST_DATA_ROW + 1;
  const rowRange = sheet.getRange(CFG.FIRST_DATA_ROW, 1, rowCount, 14);
  const rowValues = rowRange.getValues();
  const rowDisplayValues = rowRange.getDisplayValues();
  const linkNotes = sheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.LINK_COL, rowCount, 1)
    .getNotes();
  const metadataRange = sheet.getRange(
    CFG.FIRST_DATA_ROW,
    getManufacturingIdColumn_(),
    rowCount,
    4
  );
  const metadataValues = metadataRange.getDisplayValues();
  const salesApprovalAnchorColumn =
    typeof getSalesApprovalStateAnchorColumn_ === "function"
      ? getSalesApprovalStateAnchorColumn_()
      : 0;
  const salesSyncMetadataValues =
    salesApprovalAnchorColumn &&
    sheet.getMaxColumns() >= salesApprovalAnchorColumn + 4
      ? sheet
          .getRange(
            CFG.FIRST_DATA_ROW,
            salesApprovalAnchorColumn,
            rowCount,
            5
          )
          .getDisplayValues()
      : [];
  const hiddenMetadataBySignature = captureHiddenMetadataByRowSignature_(
    rowDisplayValues,
    metadataValues,
    linkNotes,
    salesSyncMetadataValues
  );
  const priorityValues = rowValues.map((row) => [
    calculateRowPriority_(row, priorityMap),
  ]);

  sheet
    .getRange(CFG.FIRST_DATA_ROW, 15, rowCount, 1)
    .setValues(priorityValues);

  sheet
    .getRange(CFG.FIRST_DATA_ROW, 1, rowCount, 15)
    .sort([
      { column: 15, ascending: false },
      { column: 5, ascending: true },
      { column: 4, ascending: true },
    ]);

  restoreHiddenMetadataAfterSort_(
    sheet,
    rowCount,
    hiddenMetadataBySignature
  );

  SpreadsheetApp.flush();
}

function captureHiddenMetadataByRowSignature_(
  visibleRows,
  metadataRows,
  linkNotes,
  salesSyncMetadataValues
) {
  const map = new Map();
  const rowCount = Math.min(
    (visibleRows || []).length,
    (metadataRows || []).length
  );

  for (let index = 0; index < rowCount; index++) {
    const signature = buildRowMetadataSignature_(
      visibleRows[index],
      linkNotes && linkNotes[index] ? linkNotes[index][0] : ""
    );
    if (!signature) continue;

    if (!map.has(signature)) {
      map.set(signature, []);
    }

    map.get(signature).push({
      manufacturingId: cleanString_(metadataRows[index][0]),
      saleOrderId: cleanString_(metadataRows[index][1]),
      saleLineId: cleanString_(metadataRows[index][2]),
      origin: cleanString_(metadataRows[index][3]),
      salesApprovalAnchor:
        salesSyncMetadataValues && salesSyncMetadataValues[index]
          ? cleanString_(salesSyncMetadataValues[index][0])
          : "",
      salesAcceptedMessageId:
        salesSyncMetadataValues && salesSyncMetadataValues[index]
          ? cleanString_(salesSyncMetadataValues[index][1])
          : "",
      salesAcceptedMessageDate:
        salesSyncMetadataValues && salesSyncMetadataValues[index]
          ? cleanString_(salesSyncMetadataValues[index][2])
          : "",
      salesAcceptedState:
        salesSyncMetadataValues && salesSyncMetadataValues[index]
          ? cleanString_(salesSyncMetadataValues[index][3])
          : "",
      salesCanonicalDeliveryDate:
        salesSyncMetadataValues && salesSyncMetadataValues[index]
          ? cleanString_(salesSyncMetadataValues[index][4])
          : "",
    });
  }

  return map;
}

function restoreHiddenMetadataAfterSort_(sheet, rowCount, metadataBySignature) {
  const visibleRows = sheet
    .getRange(CFG.FIRST_DATA_ROW, 1, rowCount, 14)
    .getDisplayValues();
  const linkNotes = sheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.LINK_COL, rowCount, 1)
    .getNotes();
  const restoredValues = [];
  const restoredSalesSyncMetadataValues = [];

  for (let index = 0; index < visibleRows.length; index++) {
    const rowValues = visibleRows[index];
    const signature = buildRowMetadataSignature_(
      rowValues,
      linkNotes[index] ? linkNotes[index][0] : ""
    );
    const metadataQueue =
      signature && metadataBySignature.has(signature)
        ? metadataBySignature.get(signature)
        : null;
    const metadata =
      metadataQueue && metadataQueue.length ? metadataQueue.shift() : null;

    restoredValues.push([
      metadata ? metadata.manufacturingId : "",
      metadata ? metadata.saleOrderId : "",
      metadata ? metadata.saleLineId : "",
      metadata ? metadata.origin : "",
    ]);
    restoredSalesSyncMetadataValues.push([
      metadata ? cleanString_(metadata.salesApprovalAnchor) : "",
      metadata ? cleanString_(metadata.salesAcceptedMessageId) : "",
      metadata ? cleanString_(metadata.salesAcceptedMessageDate) : "",
      metadata ? cleanString_(metadata.salesAcceptedState) : "",
      metadata ? cleanString_(metadata.salesCanonicalDeliveryDate) : "",
    ]);
  }

  sheet
    .getRange(CFG.FIRST_DATA_ROW, getManufacturingIdColumn_(), rowCount, 4)
    .setValues(restoredValues);

  if (typeof getSalesApprovalStateAnchorColumn_ === "function") {
    const salesApprovalAnchorColumn = getSalesApprovalStateAnchorColumn_();
    if (
      salesApprovalAnchorColumn &&
      sheet.getMaxColumns() >= salesApprovalAnchorColumn + 4
    ) {
      sheet
        .getRange(
          CFG.FIRST_DATA_ROW,
          salesApprovalAnchorColumn,
          rowCount,
          5
        )
        .setValues(restoredSalesSyncMetadataValues);
    }
  }
}

function extractRowLineCodeFromNote_(noteValue) {
  const note = cleanString_(noteValue);
  const match = note.match(/Producto:\s*([^|\n]+)/i);
  return match && match[1]
    ? cleanString_(match[1]).toUpperCase()
    : "";
}

function extractRowOriginFromNote_(noteValue) {
  const note = cleanString_(noteValue).toUpperCase();

  if (note.indexOf("OK: VENTA") === 0) {
    return "VENTA";
  }

  if (note.indexOf("OK: FABRICACION") === 0) {
    return "FABRICACION";
  }

  return "";
}

function extractRowManufacturingReferenceFromNote_(noteValue) {
  const note = cleanString_(noteValue);
  const match = note.match(/MO:\s*([^|\n]+)/i);
  return match && match[1]
    ? cleanString_(match[1]).toUpperCase()
    : "";
}

function buildRowMetadataSignature_(rowValues, linkNoteValue) {
  const orderKey = normalizeOrderNumberKey_(rowValues[1]);
  const product = cleanString_(rowValues[4]).toUpperCase();
  const quantity = cleanString_(rowValues[5]);
  const ingress = cleanString_(rowValues[6]).toUpperCase();
  const lineCode = extractRowLineCodeFromNote_(linkNoteValue);
  const origin = extractRowOriginFromNote_(linkNoteValue);
  const manufacturingReference = extractRowManufacturingReferenceFromNote_(
    linkNoteValue
  );

  if (!orderKey && !product && !lineCode && !manufacturingReference) {
    return "";
  }

  return [
    origin,
    orderKey,
    product,
    quantity,
    ingress,
    lineCode,
    manufacturingReference,
  ].join("|");
}

function buildStatePriorityMap_(sheet) {
  const priorityTable = sheet.getRange("P4:Q12").getValues();
  const priorityMap = new Map();

  for (const row of priorityTable) {
    const state = normalizeAutomationText_(row[0]);
    if (state) {
      priorityMap.set(state, row[1]);
    }
  }

  return priorityMap;
}

function calculateRowPriority_(rowValues, priorityMap) {
  const jobName = cleanString_(rowValues[3]);
  const product = cleanString_(rowValues[4]);
  const state = normalizeAutomationText_(rowValues[8]);

  if (!jobName && !product) return -1;
  if (!state) return 0;
  return priorityMap.has(state) ? priorityMap.get(state) : 0;
}

/**
 * No utiliza getLastRow(), porque las fórmulas de L pueden extenderse más allá
 * de los trabajos reales. Busca contenido operativo en B:J y observaciones en N.
 */
function getOperationalLastRow_(sheet) {
  const availableRows = Math.max(
    0,
    sheet.getMaxRows() - CFG.FIRST_DATA_ROW + 1
  );
  if (!availableRows) return CFG.FIRST_DATA_ROW - 1;

  const primaryValues = sheet
    .getRange(CFG.FIRST_DATA_ROW, 2, availableRows, 9)
    .getDisplayValues();
  const observationValues = sheet
    .getRange(CFG.FIRST_DATA_ROW, 14, availableRows, 1)
    .getDisplayValues();

  for (let index = availableRows - 1; index >= 0; index--) {
    const hasPrimaryData = primaryValues[index].some(
      (value) => cleanString_(value) !== ""
    );
    const hasObservation = cleanString_(observationValues[index][0]) !== "";

    if (hasPrimaryData || hasObservation) {
      return CFG.FIRST_DATA_ROW + index;
    }
  }

  return CFG.FIRST_DATA_ROW - 1;
}

function ensureDeliveryDaysFormulasForActiveRows_(sheet, lastOperationalRow) {
  const rowCount = lastOperationalRow - CFG.FIRST_DATA_ROW + 1;
  if (rowCount <= 0) return;

  const orders = sheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
    .getDisplayValues();
  const formulaRange = sheet.getRange(
    CFG.FIRST_DATA_ROW,
    12,
    rowCount,
    1
  );
  const formulas = formulaRange.getFormulas();
  let changed = false;

  for (let index = 0; index < rowCount; index++) {
    const order = cleanString_(orders[index][0]);
    const existingFormula = cleanString_(formulas[index][0]);

    if (!order) continue;

    if (!existingFormula || existingFormula.indexOf("RC[") !== -1) {
      const row = CFG.FIRST_DATA_ROW + index;
      formulas[index][0] =
        `=IF(H${row}=""; ""; ` +
        `IFERROR(` +
        `IF(INT(H${row})=TODAY(); "HOY"; INT(H${row})-TODAY()); ` +
        `IFERROR(` +
        `IF(DATEVALUE(H${row})=TODAY(); "HOY"; DATEVALUE(H${row})-TODAY()); ` +
        `""` +
        `)` +
        `)` +
        `)`;
      changed = true;
    }
  }

  if (changed) {
    formulaRange.setFormulas(formulas);
    SpreadsheetApp.flush();
  }
}

/**
 * Mueve al histórico trabajos terminados o pendientes de aprobación vencidos.
 */
function moverFinalizadosAHistorico() {
  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) return;
  const sourceSheet = spreadsheet.getSheetByName(CFG.SHEET_NAME);
  const historySheet = spreadsheet.getSheetByName("TRABAJOS HISTORICO");

  if (!sourceSheet || !historySheet) return;

  const lastOperationalRow = getOperationalLastRow_(sourceSheet);
  if (lastOperationalRow < CFG.FIRST_DATA_ROW) return;

  const synchronizedColumnCount = 15;
  const rowCount = lastOperationalRow - CFG.FIRST_DATA_ROW + 1;
  const values = sourceSheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      1,
      rowCount,
      synchronizedColumnCount
    )
    .getValues();
  const manufacturingIds = sourceSheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      getManufacturingIdColumn_(),
      rowCount,
      4
    )
    .getValues();
  const now = Date.now();
  const oneDayMs = 24 * 60 * 60 * 1000;
  const thirtyDaysMs = 30 * oneDayMs;
  const rowsToMove = [];

  for (let index = 0; index < values.length; index++) {
    const rowValues = values[index];
    const state = normalizeAutomationText_(rowValues[8]);
    const completionDate = rowValues[9];
    const ingressDate = rowValues[6];
    let shouldMove = false;

    if (
      (state === "finalizado" || state === "archivar") &&
      completionDate instanceof Date &&
      now - completionDate.getTime() >= oneDayMs
    ) {
      shouldMove = true;
    }

    if (
      !shouldMove &&
      state === "aprobar" &&
      ingressDate instanceof Date &&
      now - ingressDate.getTime() >= thirtyDaysMs
    ) {
      shouldMove = true;
    }

    if (shouldMove) {
      rowsToMove.push({
        sourceRow: CFG.FIRST_DATA_ROW + index,
        values: rowValues,
        metadata: manufacturingIds[index],
      });
    }
  }

  if (!rowsToMove.length) return;

  historySheet.insertRowsBefore(CFG.FIRST_DATA_ROW, rowsToMove.length);
  historySheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      1,
      rowsToMove.length,
      synchronizedColumnCount
    )
    .setValues(rowsToMove.map((item) => item.values));
  historySheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      getManufacturingIdColumn_(),
      rowsToMove.length,
      4
    )
    .setValues(rowsToMove.map((item) => item.metadata));

  for (const item of rowsToMove) {
    clearOperationalRowPreservingFormula_(sourceSheet, item.sourceRow);
  }

  if (typeof clearSalesHistoryRowKeysCache_ === "function") {
    clearSalesHistoryRowKeysCache_();
  }

  ejecutarOrdenadoAutomatico();
  spreadsheet.toast(
    `Se movieron ${rowsToMove.length} fila(s) al histórico.`,
    "Sistema"
  );
}

function clearOperationalRowPreservingFormula_(sheet, row) {
  sheet.getRange(row, 1, 1, 10).clearContent().clearNote();
  clearNewRowMarker_(sheet, row);

  const secondaryCheckboxColumn = getSecondaryOperationalCheckboxColumn_(sheet);
  if (secondaryCheckboxColumn) {
    const secondaryCheckbox = sheet.getRange(row, secondaryCheckboxColumn);
    secondaryCheckbox.insertCheckboxes();
    secondaryCheckbox.uncheck();
  }

  sheet.getRange(row, 14, 1, 2).clearContent().clearNote();
  sheet.getRange(row, getManufacturingIdColumn_(), 1, 4).clearContent();
  if (typeof clearSalesSyncMetadataForRow_ === "function") {
    clearSalesSyncMetadataForRow_(sheet, row);
  }
  ensureDeliveryDaysFormula_(sheet, row);
}

/**
 * Revisa si la planilla y el proyecto quedaron listos para trabajar.
 * No modifica datos; solo informa faltantes.
 */
function checkOdooSheetSetup() {
  const spreadsheet = getAutomationSpreadsheet_();
  const issues = [];
  const notes = [];

  if (!spreadsheet) {
    return {
      ok: false,
      issues: ["No hay un spreadsheet activo."],
      notes: [],
    };
  }

  const sheet = spreadsheet.getSheetByName(CFG.SHEET_NAME);
  if (!sheet) {
    issues.push(`No existe la pestaña ${CFG.SHEET_NAME}.`);
  } else {
    notes.push(`Pestaña OK: ${sheet.getName()}`);

    if (sheet.getMaxColumns() < 26) {
      issues.push(
        "La planilla todavía no tiene columnas suficientes para R, S, T, U, V, W, X, Y y Z."
      );
    } else {
      notes.push("Columnas ocultas base OK: R, S, T, U, V, W, X, Y y Z.");
    }

    const firstDataRow = CFG.FIRST_DATA_ROW;
    const sampleOrder = cleanString_(
      sheet.getRange(firstDataRow, CFG.ORDER_COL).getDisplayValue()
    );

    if (sampleOrder) {
      const checkboxCell = sheet.getRange(firstDataRow, CFG.NEW_ROW_CHECKBOX_COL);
      if (!isCheckboxCellConfigured_(checkboxCell)) {
        issues.push(
          `La celda ${CFG.NEW_ROW_CHECKBOX_COL}${firstDataRow} no tiene checkbox configurado.`
        );
      } else {
        notes.push("Checkbox de nuevas filas OK.");
      }

      const deliveryFormulaCell = sheet.getRange(firstDataRow, 12);
      const deliveryFormula = cleanString_(deliveryFormulaCell.getFormula());
      if (!deliveryFormula) {
        issues.push(
          `La columna L no tiene fórmula en la fila ${firstDataRow}.`
        );
      } else if (deliveryFormula.indexOf("TODAY()") === -1) {
        issues.push(
          "La fórmula de la columna L no parece ser la de días restantes."
        );
      } else {
        notes.push("Fórmula de entrega OK en la primera fila operativa.");
      }
    } else {
      notes.push(
        "La primera fila operativa está vacía; no se pudo validar checkbox/fórmula de muestra."
      );
    }
  }

  const props = PropertiesService.getScriptProperties().getProperties();
  const requiredProps = [
    "ODOO_URL",
    "ODOO_DB",
    "ODOO_USER",
    "ODOO_API_KEY",
    "ODOO_CIDS",
  ];

  for (const propertyName of requiredProps) {
    if (!cleanString_(props[propertyName])) {
      issues.push(`Falta la propiedad ${propertyName}.`);
    }
  }

  if (issues.length === 0) {
    notes.push("Propiedades de Odoo OK.");
  }

  const triggerFunctions = [
    "crearEnlaceAlEditar",
    getSalesAutoSyncTriggerFunctionName_(),
    getManufacturingAutoSyncTriggerFunctionName_(),
    "notificarVentaNeoFinalizadaAlEditar",
  ];

  for (const functionName of triggerFunctions) {
    const triggerStatus = hasInstalledTrigger_(functionName);
    if (triggerStatus === true) {
      notes.push(`Trigger OK: ${functionName}`);
    } else if (triggerStatus === null) {
      notes.push(
        `No se pudo validar el trigger ${functionName} desde esta ejecución.`
      );
    } else {
      issues.push(`Falta el trigger instalado para ${functionName}.`);
    }
  }

  const statusLines = [];
  if (notes.length) {
    statusLines.push("OK:");
    for (const note of notes) statusLines.push(`- ${note}`);
  }
  if (issues.length) {
    statusLines.push("Pendiente:");
    for (const issue of issues) statusLines.push(`- ${issue}`);
  }

  const message =
    statusLines.length > 0
      ? statusLines.join("\n")
      : "No se encontraron elementos para revisar.";

  try {
    SpreadsheetApp.getUi().alert(`Chequeo de instalación\n\n${message}`);
  } catch (err) {
    Logger.log(`Chequeo de instalación\n\n${message}`);
  }

  return {
    ok: issues.length === 0,
    issues,
    notes,
  };
}

function diagnoseAutoSyncHealth() {
  const properties = PropertiesService.getScriptProperties();
  const allProps = properties.getProperties();
  const salesTriggerName = getSalesAutoSyncTriggerFunctionName_();
  const manufacturingTriggerName =
    getManufacturingAutoSyncTriggerFunctionName_();
  const triggerNames = [
    "crearEnlaceAlEditar",
    salesTriggerName,
    manufacturingTriggerName,
    "notificarVentaNeoFinalizadaAlEditar",
  ];
  const lines = ["Diagnostico sync Odoo", ""];
  const missing = [];

  lines.push("Propiedades");
  for (const propertyName of [
    "ODOO_URL",
    "ODOO_DB",
    "ODOO_USER",
    "ODOO_API_KEY",
    "ODOO_CIDS",
  ]) {
    const value = cleanString_(allProps[propertyName]);
    if (value) {
      lines.push(`- ${propertyName}: OK`);
    } else {
      lines.push(`- ${propertyName}: FALTA`);
      missing.push(propertyName);
    }
  }

  lines.push("");
  lines.push("Triggers");
  for (const triggerName of triggerNames) {
    const triggerStatus = hasInstalledTrigger_(triggerName);
    if (triggerStatus === true) {
      lines.push(`- ${triggerName}: OK`);
    } else if (triggerStatus === null) {
      lines.push(`- ${triggerName}: no se pudo validar`);
    } else {
      lines.push(`- ${triggerName}: FALTA`);
    }
  }

  lines.push("");
  lines.push("Ultimas sync");
  lines.push(
    `- Ventas: ${
      cleanString_(
        typeof SALES_CFG !== "undefined" && SALES_CFG
          ? allProps[SALES_CFG.LAST_SYNC_PROPERTY]
          : ""
      ) || "sin registro"
    }`
  );
  lines.push(
    `- Fabricacion: ${
      cleanString_(
        typeof MFG_CFG !== "undefined" && MFG_CFG
          ? allProps[MFG_CFG.LAST_SYNC_PROPERTY]
          : ""
      ) || "sin registro"
    }`
  );

  const spreadsheet = getAutomationSpreadsheet_();
  const jobsSheet = spreadsheet
    ? spreadsheet.getSheetByName(CFG.SHEET_NAME)
    : null;
  if (jobsSheet) {
    lines.push("");
    lines.push("Planilla");
    lines.push(`- Hoja: ${jobsSheet.getName()}`);
    lines.push(`- Max rows: ${jobsSheet.getMaxRows()}`);
    lines.push(`- Max cols: ${jobsSheet.getMaxColumns()}`);
    lines.push(
      `- Ultima fila operativa: ${getOperationalLastRow_(jobsSheet)}`
    );
  }

  const message = lines.join("\n");

  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log(message);
  }

  return {
    ok: missing.length === 0,
    missing,
    salesLastSync:
      typeof SALES_CFG !== "undefined" && SALES_CFG
        ? cleanString_(allProps[SALES_CFG.LAST_SYNC_PROPERTY])
        : "",
    manufacturingLastSync:
      typeof MFG_CFG !== "undefined" && MFG_CFG
        ? cleanString_(allProps[MFG_CFG.LAST_SYNC_PROPERTY])
        : "",
    triggerNames,
    message,
  };
}

function hasInstalledTrigger_(functionName) {
  try {
    for (const trigger of ScriptApp.getProjectTriggers()) {
      if (trigger.getHandlerFunction() === functionName) {
        return true;
      }
    }
  } catch (err) {
    return null;
  }

  return false;
}

function getSalesAutoSyncTriggerFunctionName_() {
  const configuredFunctionName =
    typeof SALES_CFG !== "undefined" && SALES_CFG
      ? cleanString_(SALES_CFG.AUTO_SYNC_FUNCTION)
      : "";

  return configuredFunctionName || "syncOdooSalesOrdersNeo";
}

function getManufacturingAutoSyncTriggerFunctionName_() {
  const configuredFunctionName =
    typeof MFG_CFG !== "undefined" && MFG_CFG
      ? cleanString_(MFG_CFG.AUTO_SYNC_FUNCTION)
      : "";

  return configuredFunctionName || "syncOdooManufacturingOrders";
}

function installOdooSalesAutoSyncTrigger() {
  const functionName = getSalesAutoSyncTriggerFunctionName_();
  if (hasInstalledTrigger_(functionName) === true) {
    return;
  }

  ScriptApp.newTrigger(functionName).timeBased().everyMinutes(5).create();
}

function installOdooManufacturingAutoSyncTrigger() {
  const functionName = getManufacturingAutoSyncTriggerFunctionName_();
  if (hasInstalledTrigger_(functionName) === true) {
    return;
  }

  ScriptApp.newTrigger(functionName).timeBased().everyMinutes(5).create();
}

function removeOdooSalesAutoSyncTrigger() {
  const functionName = getSalesAutoSyncTriggerFunctionName_();

  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction() === functionName) {
      ScriptApp.deleteTrigger(trigger);
    }
  }
}

function removeOdooManufacturingAutoSyncTrigger() {
  const functionName = getManufacturingAutoSyncTriggerFunctionName_();

  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction() === functionName) {
      ScriptApp.deleteTrigger(trigger);
    }
  }
}

function installSalesFinalizationNotificationTrigger() {
  if (hasInstalledTrigger_("notificarVentaNeoFinalizadaAlEditar") === true) {
    return;
  }

  ScriptApp.newTrigger("notificarVentaNeoFinalizadaAlEditar")
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();
}

function installOdooOperationalTriggers() {
  installOdooSalesAutoSyncTrigger();
  installOdooManufacturingAutoSyncTrigger();
  installSalesFinalizationNotificationTrigger();

  const message =
    "Triggers operativos instalados/verificados: " +
    `${getSalesAutoSyncTriggerFunctionName_()}, ` +
    `${getManufacturingAutoSyncTriggerFunctionName_()} y ` +
    "notificarVentaNeoFinalizadaAlEditar.";

  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log(message);
  }

  return {
    ok: true,
    message,
    triggers: [
      getSalesAutoSyncTriggerFunctionName_(),
      getManufacturingAutoSyncTriggerFunctionName_(),
      "notificarVentaNeoFinalizadaAlEditar",
    ],
  };
}

function removeSalesFinalizationNotificationTrigger() {
  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (
      trigger.getHandlerFunction() ===
      "notificarVentaNeoFinalizadaAlEditar"
    ) {
      ScriptApp.deleteTrigger(trigger);
    }
  }
}

function getSecondaryOperationalCheckboxColumn_(sheet) {
  const candidateColumn =
    typeof CFG !== "undefined" && CFG
      ? Number(CFG.SECONDARY_CHECKBOX_COL || 0)
      : 0;

  if (
    !sheet ||
    !Number.isInteger(candidateColumn) ||
    candidateColumn <= 0 ||
    sheet.getMaxColumns() < candidateColumn
  ) {
    return 0;
  }

  return isCheckboxCellConfigured_(
    sheet.getRange(CFG.FIRST_DATA_ROW, candidateColumn)
  )
    ? candidateColumn
    : 0;
}

function getOperationalCheckboxColumns_(sheet) {
  const columns = [CFG.NEW_ROW_CHECKBOX_COL];
  const secondaryColumn = getSecondaryOperationalCheckboxColumn_(sheet);

  if (secondaryColumn && secondaryColumn !== CFG.NEW_ROW_CHECKBOX_COL) {
    columns.push(secondaryColumn);
  }

  return columns;
}

function ensureOperationalCheckboxesForRow_(sheet, row) {
  const numericRow = Number(row);
  if (
    !sheet ||
    !Number.isInteger(numericRow) ||
    numericRow < CFG.FIRST_DATA_ROW
  ) {
    return;
  }

  const checkboxColumns = getOperationalCheckboxColumns_(sheet);

  for (const column of checkboxColumns) {
    const range = sheet.getRange(numericRow, column);
    range.clearContent();
    range.clearDataValidations();
    range.insertCheckboxes();
    range.uncheck();
  }
}

/**
 * Repara las columnas con checkboxes operativos cuando una copia de la planilla
 * conserva listas desplegables u otras validaciones incompatibles.
 */
function repairOperationalCheckboxes() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error("No hay un spreadsheet activo.");
  }

  const sheet = spreadsheet.getSheetByName(CFG.SHEET_NAME);
  if (!sheet) {
    throw new Error(`No existe la pestana ${CFG.SHEET_NAME}.`);
  }

  const rowCount = Math.max(0, sheet.getMaxRows() - CFG.FIRST_DATA_ROW + 1);
  if (!rowCount) {
    return {
      ok: true,
      repairedRows: 0,
      message: "No hay filas operativas para reparar.",
    };
  }

  const columnsToRepair = getOperationalCheckboxColumns_(sheet);
  let repairedCells = 0;

  for (const column of columnsToRepair) {
    const range = sheet.getRange(CFG.FIRST_DATA_ROW, column, rowCount, 1);
    const currentValues = range.getValues();
    const normalizedValues = currentValues.map((row) => {
      const value = row[0];
      const normalizedText = cleanString_(value).toLowerCase();
      const isChecked =
        value === true ||
        value === 1 ||
        normalizedText === "true" ||
        normalizedText === "verdadero" ||
        normalizedText === "si" ||
        normalizedText === "yes";
      return [isChecked];
    });

    range.clearContent();
    range.clearDataValidations();
    range.insertCheckboxes();
    range.setValues(normalizedValues);
    repairedCells += rowCount;
  }

  const message =
    `Checkboxes operativos reparados. ` +
    `Filas: ${rowCount} | Columnas: ${columnsToRepair.join(", ")}.`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    repairedRows: rowCount,
    repairedCells,
    columns: columnsToRepair,
    message,
  };
}

function isCheckboxCellConfigured_(range) {
  try {
    const validation = range.getDataValidation();
    return (
      validation &&
      validation.getCriteriaType() ===
        SpreadsheetApp.DataValidationCriteria.CHECKBOX
    );
  } catch (err) {
    return false;
  }
}

function appendSyncLog_(entry) {
  SYNC_LOG_BUFFER.push([
    nowUtcString_(),
    cleanString_(entry.module),
    cleanString_(entry.action),
    cleanString_(entry.order),
    cleanString_(entry.odooId),
    cleanString_(entry.origin),
    cleanString_(entry.details),
  ]);
}

function flushSyncLogBuffer_() {
  if (!SYNC_LOG_BUFFER.length) return;

  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) {
    SYNC_LOG_BUFFER = [];
    return;
  }

  const sheet = getOrCreateSyncLogSheet_(spreadsheet);
  const startRow = sheet.getLastRow() + 1;
  sheet
    .getRange(startRow, 1, SYNC_LOG_BUFFER.length, SYNC_LOG_BUFFER[0].length)
    .setValues(SYNC_LOG_BUFFER);
  SYNC_LOG_BUFFER = [];
}

function openSyncLogSheet() {
  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) return;

  const sheet = getOrCreateSyncLogSheet_(spreadsheet);
  spreadsheet.setActiveSheet(sheet);
}

function clearSyncLogSheet() {
  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) return;

  const sheet = getOrCreateSyncLogSheet_(spreadsheet);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;

  sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).clearContent();
  SYNC_LOG_BUFFER = [];
}

function testSyncLogWrite() {
  const spreadsheet = getAutomationSpreadsheet_();
  if (!spreadsheet) {
    throw new Error(
      "No se pudo resolver la planilla para escribir en LOG_SYNC."
    );
  }

  appendSyncLog_({
    module: "SISTEMA",
    action: "test_log",
    origin: CFG.SHEET_NAME,
    details: `Prueba manual de LOG_SYNC sobre ${spreadsheet.getName()}.`,
  });
  flushSyncLogBuffer_();

  const sheet = getOrCreateSyncLogSheet_(spreadsheet);
  const lastRow = sheet.getLastRow();
  const rowValues =
    lastRow > 1
      ? sheet.getRange(lastRow, 1, 1, 7).getDisplayValues()[0]
      : [];
  const message =
    lastRow > 1
      ? `LOG_SYNC OK en fila ${lastRow}: ${rowValues.join(" | ")}`
      : "No se pudo confirmar la escritura en LOG_SYNC.";

  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log(message);
  }

  return {
    ok: lastRow > 1,
    spreadsheetName: spreadsheet.getName(),
    logSheetName: sheet.getName(),
    lastRow,
    rowValues,
    message,
  };
}

function getOrCreateSyncLogSheet_(spreadsheet) {
  let sheet = spreadsheet.getSheetByName("LOG_SYNC");
  if (!sheet) {
    sheet = spreadsheet.insertSheet("LOG_SYNC");
  }

  const headers = [
    "Timestamp",
    "Modulo",
    "Accion",
    "Orden",
    "Odoo ID",
    "Origen",
    "Detalles",
  ];

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  const currentHeaders = headerRange.getDisplayValues()[0];
  const hasHeaders = headers.every(
    (header, index) => cleanString_(currentHeaders[index]) === header
  );

  if (!hasHeaders) {
    headerRange.setValues([headers]);
  }

  return sheet;
}
