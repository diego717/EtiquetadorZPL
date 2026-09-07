/**
 * ============================================================================
 * SINCRONIZACIÓN DE ÓRDENES DE VENTA
 * ============================================================================
 *
 * Dependencias externas:
 * - CFG, SALES_CFG y ODOO_MODELS.
 * - Funciones de conexión, chatter, enlaces y utilidades compartidas.
 * - markRowAsNew_() y clearNewRowMarker_().
 * - ejecutarOrdenadoAutomatico().
 */

function isSalesSheetRow_(sheet, row) {
  const linkCell = sheet.getRange(row, CFG.LINK_COL);
  const url = cleanString_(getCellLinkUrl_(linkCell)).toLowerCase();

  if (url.indexOf("model=sale.order") !== -1) {
    return true;
  }

  const note = cleanString_(safeGetNote_(linkCell)).toLowerCase();
  return (
    note.indexOf("ok: venta") !== -1 ||
    note.indexOf("venta neo") !== -1 ||
    note.indexOf("sale.order") !== -1
  );
}

function getExistingSalesOrderRowsMap_(sheet, sheetSnapshot) {
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet === sheet
      ? sheetSnapshot
      : null;
  const availableRows = snapshot
    ? snapshot.rowCount
    : Math.max(0, sheet.getMaxRows() - CFG.FIRST_DATA_ROW + 1);
  const rowCount = Math.min(SALES_CFG.MAX_ORDER_SCAN_ROWS, availableRows);
  const map = new Map();

  if (!rowCount) return map;

  const orderValues = snapshot
    ? snapshot.orderValues
    : sheet
        .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
        .getDisplayValues();
  const salesSnapshotFlags = snapshot
    ? snapshot.salesSnapshotFlags
    : getSalesSnapshotFlagsForSheet_(sheet, rowCount);
  const markerValues = snapshot
    ? snapshot.markerValues
    : sheet
        .getRange(
          CFG.FIRST_DATA_ROW,
          CFG.NEW_ROW_CHECKBOX_COL,
          rowCount,
          1
        )
        .getValues();

  for (let index = 0; index < rowCount; index++) {
    const orderKey = normalizeOrderNumberKey_(orderValues[index][0]);
    if (!orderKey) continue;

    if (!salesSnapshotFlags[index]) {
      continue;
    }

    if (!map.has(orderKey)) {
      map.set(orderKey, []);
    }

    map.get(orderKey).push(CFG.FIRST_DATA_ROW + index);
  }

  for (const rows of map.values()) {
    rows.sort((leftRow, rightRow) => {
      const leftIndex = leftRow - CFG.FIRST_DATA_ROW;
      const rightIndex = rightRow - CFG.FIRST_DATA_ROW;
      const leftIsNew = markerValues[leftIndex][0] === true ? 1 : 0;
      const rightIsNew = markerValues[rightIndex][0] === true ? 1 : 0;
      return leftIsNew - rightIsNew || leftRow - rightRow;
    });
  }

  return map;
}

function isSalesRowSnapshot_(richTextValue, noteValue, formulaValue, displayValue) {
  const url = getSalesSnapshotUrl_(
    richTextValue,
    formulaValue,
    displayValue
  ).toLowerCase();

  if (url.indexOf("model=sale.order") !== -1) {
    return true;
  }

  const note = cleanString_(noteValue).toLowerCase();
  return (
    note.indexOf("ok: venta") !== -1 ||
    note.indexOf("venta neo") !== -1 ||
    note.indexOf("sale.order") !== -1
  );
}

function getSalesSnapshotUrl_(richTextValue, formulaValue, displayValue) {
  try {
    if (richTextValue) {
      const directUrl = cleanString_(richTextValue.getLinkUrl());
      if (directUrl) return directUrl;

      const runs = richTextValue.getRuns ? richTextValue.getRuns() : [];
      for (const run of runs) {
        const runUrl = cleanString_(run.getLinkUrl && run.getLinkUrl());
        if (runUrl) return runUrl;
      }
    }
  } catch (err) {}

  const formula = cleanString_(formulaValue);
  const formulaMatch = formula.match(/HYPERLINK\(\s*"([^"]+)"/i);
  if (formulaMatch && formulaMatch[1]) {
    return cleanString_(formulaMatch[1]);
  }

  const displayMatch = cleanString_(displayValue).match(
    /https?:\/\/[^\s'"]+/i
  );
  return displayMatch && displayMatch[0]
    ? cleanString_(displayMatch[0])
    : "";
}

function getIncompleteSalesOrderKeys_(sheet, existingSalesRowsMap, sheetSnapshot) {
  const keys = new Set();
  const allRows = [];

  for (const rows of existingSalesRowsMap.values()) {
    allRows.push(...rows);
  }

  if (!allRows.length) return keys;

  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet === sheet
      ? sheetSnapshot
      : null;
  const firstRow = snapshot ? CFG.FIRST_DATA_ROW : Math.min(...allRows);
  const values = snapshot
    ? snapshot.deliveryStateValues
    : sheet
        .getRange(
          firstRow,
          8,
          Math.max(...allRows) - firstRow + 1,
          2
        )
        .getDisplayValues();

  for (const [orderKey, rows] of existingSalesRowsMap.entries()) {
    for (const row of rows) {
      const rowValues = values[row - firstRow];
      const deliveryDate = cleanString_(rowValues[0]);
      const state = cleanString_(rowValues[1]);

      if (!deliveryDate || !state) {
        keys.add(orderKey);
        break;
      }
    }
  }

  return keys;
}

function clearSalesOrderRows_(sheet, rows) {
  for (const row of rows) {
    // Limpia los datos operativos sin borrar la fórmula de la columna L.
    sheet.getRange(row, 1, 1, 10).clearContent();
    sheet.getRange(row, CFG.LINK_COL).clearNote();
    clearNewRowMarker_(sheet, row);

    // Columna M: segunda casilla. Columnas N:O: observación y prioridad.
    const secondaryCheckboxColumn =
      typeof getSecondaryOperationalCheckboxColumn_ === "function"
        ? getSecondaryOperationalCheckboxColumn_(sheet)
        : 0;
    if (secondaryCheckboxColumn) {
      sheet.getRange(row, secondaryCheckboxColumn).uncheck();
    }
    sheet.getRange(row, 14, 1, 2).clearContent();
    clearSalesSyncMetadataForRow_(sheet, row);
  }
}

function clearSalesFinalizationNotificationKeysForRows_(
  sheet,
  rows,
  notifiedKeys
) {
  let didChange = false;

  for (const row of rows || []) {
    const context = getSalesFinalizationContextFromRow_(sheet, row);
    const notificationKey = buildSalesFinalizationNotificationKey_(context);

    if (!notificationKey || !notifiedKeys.has(notificationKey)) {
      continue;
    }

    notifiedKeys.delete(notificationKey);
    didChange = true;
  }

  return didChange;
}

function clearSalesApprovalNotificationKeysForRows_(
  sheet,
  rows,
  notifiedKeys
) {
  let didChange = false;

  for (const row of rows || []) {
    const context = getSalesFinalizationContextFromRow_(sheet, row);
    const notificationKey = buildSalesApprovalNotificationKey_(context);

    if (!notificationKey || !notifiedKeys.has(notificationKey)) {
      continue;
    }

    notifiedKeys.delete(notificationKey);
    didChange = true;
  }

  return didChange;
}

function clearSalesPausedNotificationKeysForRows_(
  sheet,
  rows,
  notifiedKeys
) {
  let didChange = false;

  for (const row of rows || []) {
    const context = getSalesFinalizationContextFromRow_(sheet, row);
    const notificationKey = buildSalesPausedNotificationKey_(context);

    if (!notificationKey || !notifiedKeys.has(notificationKey)) {
      continue;
    }

    notifiedKeys.delete(notificationKey);
    didChange = true;
  }

  return didChange;
}

function ensureDeliveryDaysFormula_(sheet, row, forceWrite) {
  const formulaCell = sheet.getRange(row, 12);
  if (!forceWrite && formulaCell.getFormula()) return;

  formulaCell.setFormula(
    `=IF(H${row}=""; ""; ` +
      `IFERROR(` +
      `IF(INT(H${row})=TODAY(); "HOY"; INT(H${row})-TODAY()); ` +
      `IFERROR(` +
      `IF(DATEVALUE(H${row})=TODAY(); "HOY"; DATEVALUE(H${row})-TODAY()); ` +
      `""` +
      `)` +
      `)` +
      `)`
  );
}

/**
 * Reparación manual: instala la fórmula de días restantes en toda la columna L.
 * Puede ejecutarse desde el editor de Apps Script cuando existan huecos.
 */
function repairDeliveryDaysFormulas() {
  const sheet = getTargetSheet_();
  const rowCount = sheet.getMaxRows() - CFG.FIRST_DATA_ROW + 1;

  if (rowCount <= 0) return;

  const formulas = Array.from(
    { length: rowCount },
    (_, index) => {
      const row = CFG.FIRST_DATA_ROW + index;
      return [
        `=IF(H${row}=""; ""; ` +
          `IFERROR(` +
          `IF(INT(H${row})=TODAY(); "HOY"; INT(H${row})-TODAY()); ` +
          `IFERROR(` +
          `IF(DATEVALUE(H${row})=TODAY(); "HOY"; DATEVALUE(H${row})-TODAY()); ` +
          `""` +
          `)` +
          `)` +
          `)`,
      ];
    }
  );

  sheet
    .getRange(CFG.FIRST_DATA_ROW, 12, rowCount, 1)
    .setFormulas(formulas);

  showSpreadsheetToast_(
    `Fórmulas de entrega reparadas en ${rowCount} filas.`
  );
}

function repairSalesDeliveryDateValues() {
  const sheet = getTargetSheet_();
  const snapshot = buildSalesSheetSnapshot_(sheet);
  let repairedRows = 0;

  if (!snapshot.rowCount) {
    showSpreadsheetToast_("No hay filas de ventas para reparar.");
    return {
      repairedRows: 0,
      message: "No hay filas de ventas para reparar.",
    };
  }

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (!snapshot.salesSnapshotFlags[index]) continue;

    const row = CFG.FIRST_DATA_ROW + index;
    const deliveryCell = sheet.getRange(row, 8);
    const currentValue = deliveryCell.getValue();
    if (currentValue instanceof Date && !Number.isNaN(currentValue.getTime())) {
      deliveryCell.setNumberFormat("d-mmm");
      const syncMetadata = getSalesSyncMetadataForRow_(sheet, row);
      setSalesSyncMetadataForRow_(sheet, row, {
        approvalAnchor: syncMetadata.approvalAnchor,
        acceptedMessageId: syncMetadata.acceptedMessageId,
        acceptedMessageDate: syncMetadata.acceptedMessageDate,
        acceptedState: syncMetadata.acceptedState,
        canonicalDeliveryDate: formatSalesCanonicalDate_(currentValue),
      });
      continue;
    }

    const parsedDate = parseSalesSheetDateValue_(
      snapshot.deliveryStateValues[index][0]
    );
    if (!parsedDate) continue;

    deliveryCell.setValue(parsedDate);
    deliveryCell.setNumberFormat("d-mmm");
    const syncMetadata = getSalesSyncMetadataForRow_(sheet, row);
    setSalesSyncMetadataForRow_(sheet, row, {
      approvalAnchor: syncMetadata.approvalAnchor,
      acceptedMessageId: syncMetadata.acceptedMessageId,
      acceptedMessageDate: syncMetadata.acceptedMessageDate,
      acceptedState: syncMetadata.acceptedState,
      canonicalDeliveryDate: formatSalesCanonicalDate_(parsedDate),
    });
    repairedRows++;
  }

  const message =
    repairedRows > 0
      ? `Fechas de entrega reparadas en ${repairedRows} fila(s) de ventas.`
      : "No se encontraron fechas de entrega de ventas para reparar.";

  showSpreadsheetToast_(message);

  return {
    repairedRows,
    message,
  };
}

/**
 * Convierte las fechas de ingreso que hayan quedado como texto (por ejemplo,
 * "3-Aug") a valores Date. La validación de Google Sheets solo acepta valores
 * de fecha reales, aunque el texto tenga una apariencia de fecha válida.
 */
function repairSalesIngressDateValues() {
  const sheet = getTargetSheet_();
  const snapshot = buildSalesSheetSnapshot_(sheet);
  let repairedRows = 0;

  if (!snapshot.rowCount) {
    showSpreadsheetToast_("No hay filas de ventas para reparar.");
    return {
      repairedRows: 0,
      message: "No hay filas de ventas para reparar.",
    };
  }

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (!snapshot.salesSnapshotFlags[index]) continue;

    const row = CFG.FIRST_DATA_ROW + index;
    const ingressCell = sheet.getRange(row, 7);
    const currentValue = ingressCell.getValue();

    if (currentValue instanceof Date && !Number.isNaN(currentValue.getTime())) {
      ingressCell.setNumberFormat("d-mmm");
      continue;
    }

    const parsedDate = parseSalesSheetDateValue_(
      ingressCell.getDisplayValue()
    );
    if (!parsedDate) continue;

    ingressCell.setValue(parsedDate);
    ingressCell.setNumberFormat("d-mmm");
    repairedRows++;
  }

  const message =
    repairedRows > 0
      ? `Fechas de ingreso reparadas en ${repairedRows} fila(s) de ventas.`
      : "No se encontraron fechas de ingreso de ventas para reparar.";

  showSpreadsheetToast_(message);

  return {
    repairedRows,
    message,
  };
}

function repairSalesResponsibleValues() {
  const sheet = getTargetSheet_();
  const snapshot = buildSalesSheetSnapshot_(sheet);

  if (!snapshot.rowCount) {
    const message = "No hay filas de ventas para recalcular pedido por.";
    showSpreadsheetToast_(message);
    return {
      processedRows: 0,
      updatedRows: 0,
      message,
    };
  }

  const rowsBySaleOrderId = new Map();

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (!snapshot.salesSnapshotFlags[index]) continue;

    const row = CFG.FIRST_DATA_ROW + index;
    const metadataValues = snapshot.metadataValues[index];
    const saleOrderId =
      cleanString_(metadataValues[1]) ||
      extractSaleOrderIdFromUrl_(
        getSalesSnapshotUrl_(
          null,
          "",
          sheet.getRange(row, CFG.LINK_COL).getDisplayValue()
        )
      );

    if (!saleOrderId) continue;

    if (!rowsBySaleOrderId.has(saleOrderId)) {
      rowsBySaleOrderId.set(saleOrderId, []);
    }

    rowsBySaleOrderId.get(saleOrderId).push(row);
  }

  if (!rowsBySaleOrderId.size) {
    const message =
      "No se encontraron filas activas de ventas con sale.order.id para recalcular pedido por.";
    showSpreadsheetToast_(message);
    return {
      processedRows: 0,
      updatedRows: 0,
      message,
    };
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  const uid = odooLogin_(cfg);
  const saleOrderIds = Array.from(rowsBySaleOrderId.keys())
    .map((saleOrderId) => Number(saleOrderId))
    .filter((saleOrderId) => Number.isInteger(saleOrderId) && saleOrderId > 0);
  const ordersById = new Map();

  for (const saleOrderIdsChunk of chunkValues_(saleOrderIds, 80)) {
    const orders =
      executeKw_(
        cfg,
        uid,
        ODOO_MODELS.sales,
        "search_read",
        [[["id", "in", saleOrderIdsChunk]]],
        {
          fields: getSalesOrderFields_(),
          order: "id asc",
        }
      ) || [];

    for (const order of orders) {
      ordersById.set(cleanString_(order.id), order);
    }
  }

  const latestNotesByOrderId = fetchLatestSalesNotesMap_(cfg, uid, saleOrderIds);
  let processedRows = 0;
  let updatedRows = 0;

  for (const [saleOrderId, rows] of rowsBySaleOrderId.entries()) {
    const order = ordersById.get(saleOrderId);
    if (!order) continue;

    const noteInfo =
      latestNotesByOrderId.get(saleOrderId) ||
      extractLatestSalesNoteSafely_(cfg, uid, Number(saleOrderId));
    const matchedResponsible = resolveSalesResponsible_(order, noteInfo);
    if (!matchedResponsible) continue;

    for (const row of rows) {
      processedRows++;
      const currentResponsible = cleanString_(
        sheet.getRange(row, 1).getDisplayValue()
      );

      if (
        normalizeSalesComparableText_(currentResponsible) ===
        normalizeSalesComparableText_(matchedResponsible)
      ) {
        continue;
      }

      sheet.getRange(row, 1).setValue(matchedResponsible);
      updatedRows++;
    }
  }

  const message =
    `Pedido por recalculado en ventas. ` +
    `Filas revisadas: ${processedRows} | Actualizadas: ${updatedRows}`;
  showSpreadsheetToast_(message);

  return {
    processedRows,
    updatedRows,
    message,
  };
}

function findExistingSalesLineRow_(
  sheet,
  rows,
  usedRows,
  saleLineId,
  lineCode,
  lineIdentityByRow
) {
  const expectedSaleLineId = cleanString_(saleLineId);
  const expectedCode = cleanString_(lineCode).toUpperCase();

  if (expectedSaleLineId) {
    for (const row of rows) {
      if (usedRows.has(row)) continue;

      const existingSaleLineId = cleanString_(
        lineIdentityByRow && lineIdentityByRow.has(row)
          ? lineIdentityByRow.get(row).saleLineId
          : ""
      );
      if (existingSaleLineId === expectedSaleLineId) {
        return row;
      }
    }
  }

  if (expectedCode) {
    for (const row of rows) {
      if (usedRows.has(row)) continue;

      const existingCode = cleanString_(
        lineIdentityByRow && lineIdentityByRow.has(row)
          ? lineIdentityByRow.get(row).lineCode
          : getSalesLineCodeFromRow_(sheet, row)
      ).toUpperCase();
      if (existingCode === expectedCode) {
        return row;
      }
    }
  }

  if (!expectedSaleLineId && !expectedCode) {
    for (const row of rows) {
      if (!usedRows.has(row)) return row;
    }
  }

  // Evita reutilizar "la primera fila libre" cuando no coincide ni la linea ni el codigo.
  // En ventas esto puede mezclar contexto y disparar actividades sobre la orden incorrecta.
  return null;
}

function getSalesLineIdColumn_() {
  return getManufacturingIdColumn_() + 2;
}

function buildSalesLineIdentityMapForRows_(sheet, rows) {
  const identityMap = new Map();
  const normalizedRows = Array.from(
    new Set(
      (rows || [])
        .map((row) => Number(row))
        .filter((row) => Number.isInteger(row) && row >= CFG.FIRST_DATA_ROW)
    )
  ).sort((left, right) => left - right);

  if (!normalizedRows.length) return identityMap;

  const firstRow = normalizedRows[0];
  const lastRow = normalizedRows[normalizedRows.length - 1];
  const rowCount = lastRow - firstRow + 1;
  const notes = sheet
    .getRange(firstRow, CFG.LINK_COL, rowCount, 1)
    .getNotes();
  const productDisplayValues = sheet
    .getRange(firstRow, 5, rowCount, 1)
    .getDisplayValues();
  const saleLineIdValues = sheet
    .getRange(firstRow, getSalesLineIdColumn_(), rowCount, 1)
    .getDisplayValues();

  for (const row of rows) {
    const numericRow = Number(row);
    if (!Number.isInteger(numericRow) || numericRow < firstRow || numericRow > lastRow) {
      continue;
    }

    const index = numericRow - firstRow;
    identityMap.set(numericRow, {
      lineCode: extractSalesLineCodeFromSnapshot_(
        notes[index][0],
        productDisplayValues[index][0]
      ),
      saleLineId: cleanString_(saleLineIdValues[index][0]),
    });
  }

  return identityMap;
}

function extractSalesLineCodeFromSnapshot_(noteValue, productDisplayValue) {
  const note = cleanString_(noteValue);
  const noteMatch = note.match(/Producto:\s*([^|\n]+)/i);

  if (noteMatch && noteMatch[1]) {
    return cleanString_(noteMatch[1]);
  }

  return extractBracketedReference_(productDisplayValue);
}

function buildSalesLineCodeMapForRows_(sheet, rows) {
  const codeMap = new Map();
  const normalizedRows = Array.from(
    new Set(
      (rows || [])
        .map((row) => Number(row))
        .filter((row) => Number.isInteger(row) && row >= CFG.FIRST_DATA_ROW)
    )
  ).sort((left, right) => left - right);

  if (!normalizedRows.length) return codeMap;

  const firstRow = normalizedRows[0];
  const lastRow = normalizedRows[normalizedRows.length - 1];
  const rowCount = lastRow - firstRow + 1;
  const notes = sheet
    .getRange(firstRow, CFG.LINK_COL, rowCount, 1)
    .getNotes();
  const productDisplayValues = sheet
    .getRange(firstRow, 5, rowCount, 1)
    .getDisplayValues();

  for (const row of normalizedRows) {
    const index = row - firstRow;
    codeMap.set(
      row,
      extractSalesLineCodeFromSnapshot_(
        notes[index][0],
        productDisplayValues[index][0]
      )
    );
  }

  return codeMap;
}

function getSalesLineCodeFromRow_(sheet, row) {
  return extractSalesLineCodeFromSnapshot_(
    safeGetNote_(sheet.getRange(row, CFG.LINK_COL)),
    sheet.getRange(row, 5).getDisplayValue()
  );
}

function isSalesContextRow_(sheet, row, context) {
  if (cleanString_(context && context.origin).toUpperCase() === "VENTA") {
    return true;
  }

  return Boolean(
    sheet &&
    Number.isInteger(Number(row)) &&
    Number(row) >= CFG.FIRST_DATA_ROW &&
    isSalesSheetRow_(sheet, Number(row))
  );
}

function resolveSalesResponsible_(order, noteInfo) {
  return (
    findResponsible_(noteInfo && noteInfo.authorName) ||
    findResponsible_(getMany2oneName_(order.user_id)) ||
    findResponsible_(getMany2oneName_(order.create_uid))
  );
}

function parseSalesSheetDateValue_(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return new Date(
      value.getFullYear(),
      value.getMonth(),
      value.getDate()
    );
  }

  const rawValue = cleanString_(value);
  if (!rawValue) return null;

  let parts = rawValue.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (parts) {
    const parsedDate = new Date(
      Number(parts[3]),
      Number(parts[2]) - 1,
      Number(parts[1])
    );
    return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
  }

  parts = rawValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (parts) {
    const parsedDate = new Date(
      Number(parts[1]),
      Number(parts[2]) - 1,
      Number(parts[3])
    );
    return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
  }

  parts = rawValue.match(/^(\d{1,2})\s*[-\/]\s*([A-Za-z.]{3,})$/);
  if (parts) {
    const monthIndex = getSalesMonthIndexFromLabel_(parts[2]);
    if (monthIndex !== -1) {
      const parsedDate = new Date(
        new Date().getFullYear(),
        monthIndex,
        Number(parts[1])
      );
      return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
    }
  }

  const fallbackDate = new Date(rawValue);
  if (!Number.isNaN(fallbackDate.getTime())) {
    return new Date(
      fallbackDate.getFullYear(),
      fallbackDate.getMonth(),
      fallbackDate.getDate()
    );
  }

  return null;
}

function getSalesMonthIndexFromLabel_(value) {
  const normalizedValue = cleanString_(value)
    .toLowerCase()
    .replace(/\./g, "");

  const monthIndexByLabel = {
    ene: 0,
    enero: 0,
    jan: 0,
    january: 0,
    feb: 1,
    febrero: 1,
    february: 1,
    mar: 2,
    marzo: 2,
    march: 2,
    abr: 3,
    abril: 3,
    apr: 3,
    april: 3,
    may: 4,
    mayo: 4,
    jun: 5,
    junio: 5,
    june: 5,
    jul: 6,
    julio: 6,
    july: 6,
    ago: 7,
    agosto: 7,
    aug: 7,
    august: 7,
    sep: 8,
    sept: 8,
    septiembre: 8,
    september: 8,
    oct: 9,
    octubre: 9,
    october: 9,
    nov: 10,
    noviembre: 10,
    november: 10,
    dic: 11,
    diciembre: 11,
    dec: 11,
    december: 11,
  };

  return Object.prototype.hasOwnProperty.call(monthIndexByLabel, normalizedValue)
    ? monthIndexByLabel[normalizedValue]
    : -1;
}

function formatSalesDateForLog_(value) {
  const parsedDate = parseSalesSheetDateValue_(value);
  if (!parsedDate) {
    return cleanString_(value);
  }

  return Utilities.formatDate(
    parsedDate,
    Session.getScriptTimeZone(),
    "d-MMM"
  );
}

function normalizeSalesComparableText_(value) {
  return cleanString_(value).replace(/\s+/g, " ").trim();
}

function normalizeSalesComparableDateDisplay_(value) {
  const parsedDate = parseSalesSheetDateValue_(value);
  if (!parsedDate) {
    return normalizeSalesComparableText_(value);
  }

  return Utilities.formatDate(
    parsedDate,
    Session.getScriptTimeZone(),
    "yyyy-MM-dd"
  );
}

function normalizeSalesComparableQuantity_(value) {
  if (typeof value === "number" && !Number.isNaN(value)) {
    return String(Number(value));
  }

  const rawValue = cleanString_(value).replace(/\s+/g, "");
  if (!rawValue) return "";

  let normalizedValue = rawValue;

  if (/^-?\d{1,3}(\.\d{3})*(,\d+)?$/.test(rawValue)) {
    normalizedValue = rawValue.replace(/\./g, "").replace(",", ".");
  } else if (/^-?\d{1,3}(,\d{3})*(\.\d+)?$/.test(rawValue)) {
    normalizedValue = rawValue.replace(/,/g, "");
  } else if (/^-?\d+(,\d+)?$/.test(rawValue)) {
    normalizedValue = rawValue.replace(",", ".");
  }

  const parsedNumber = Number(normalizedValue);
  return Number.isNaN(parsedNumber) ? rawValue : String(parsedNumber);
}

function getSalesOrderFields_() {
  return [
    "id",
    "name",
    "partner_id",
    "create_date",
    "write_date",
    "date_order",
    "state",
    "user_id",
    "create_uid",
  ];
}

function parseCsvList_(rawValue) {
  return cleanString_(rawValue)
    .split(",")
    .map((value) => cleanString_(value))
    .filter(Boolean);
}

function normalizeComparableUtcString_(value) {
  return cleanString_(value)
    .replace("T", " ")
    .replace(/(\.\d+)?Z$/i, "")
    .trim();
}

function isUtcStringAfter_(candidateValue, referenceValue) {
  const candidate = normalizeComparableUtcString_(candidateValue);
  const reference = normalizeComparableUtcString_(referenceValue);

  if (!candidate || !reference) return false;
  return candidate > reference;
}

function formatSalesChatterMessageDateForSheet_(value) {
  const rawValue = cleanString_(value);
  if (!rawValue) return "";

  const normalizedValue = rawValue.replace("T", " ");
  const parts = normalizedValue.match(
    /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?$/
  );

  if (parts) {
    const parsedDate = new Date(
      Number(parts[1]),
      Number(parts[2]) - 1,
      Number(parts[3]),
      Number(parts[4] || 0),
      Number(parts[5] || 0),
      Number(parts[6] || 0)
    );

    if (!Number.isNaN(parsedDate.getTime())) {
      return Utilities.formatDate(
        parsedDate,
        Session.getScriptTimeZone(),
        "d-MMM"
      );
    }
  }

  const fallbackDate = new Date(rawValue);
  if (Number.isNaN(fallbackDate.getTime())) return "";

  return Utilities.formatDate(
    fallbackDate,
    Session.getScriptTimeZone(),
    "d-MMM"
  );
}

function logSalesSyncStage_(stageLabel, startedAtMs, extraMessage) {
  const elapsedMs = Math.max(0, Date.now() - Number(startedAtMs || 0));
  const suffix = cleanString_(extraMessage);
  logDebug_(
    `[VENTAS_SYNC] ${stageLabel} | ${elapsedMs} ms` +
      (suffix ? ` | ${suffix}` : "")
  );
}

function buildSalesManualStateAnchorKey_(data) {
  if (!data) return "";

  const saleLineId = cleanString_(data.saleLineId);
  if (saleLineId) {
    return `line:${saleLineId}`;
  }

  const saleOrderId = cleanString_(data.saleOrderId || data.saleId);
  const lineCode = cleanString_(data.lineCode).toUpperCase();

  if (!saleOrderId || !lineCode) return "";
  return `sale:${saleOrderId}|code:${lineCode}`;
}

function getSalesManualStateAnchors_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    "ODOO_SALES_MANUAL_STATE_ANCHORS"
  );

  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (err) {
    return {};
  }
}

function saveSalesManualStateAnchors_(anchors) {
  PropertiesService.getScriptProperties().setProperty(
    "ODOO_SALES_MANUAL_STATE_ANCHORS",
    JSON.stringify(anchors || {})
  );
}

function setSalesManualStateAnchor_(data, anchorUtcString) {
  const key = buildSalesManualStateAnchorKey_(data);
  if (!key) return "";

  const anchors = getSalesManualStateAnchors_();
  anchors[key] = cleanString_(anchorUtcString) || nowUtcString_();
  saveSalesManualStateAnchors_(anchors);
  return key;
}

function getSalesManualStateAnchor_(data) {
  const key = buildSalesManualStateAnchorKey_(data);
  if (!key) return "";

  const anchors = getSalesManualStateAnchors_();
  return cleanString_(anchors[key]);
}

function clearSalesManualStateAnchor_(data) {
  const key = buildSalesManualStateAnchorKey_(data);
  if (!key) return;

  const anchors = getSalesManualStateAnchors_();
  if (!Object.prototype.hasOwnProperty.call(anchors, key)) return;

  delete anchors[key];
  saveSalesManualStateAnchors_(anchors);
}

function getSalesApprovalStateAnchorColumn_() {
  return getManufacturingIdColumn_() + 4;
}

function getSalesAcceptedMessageIdColumn_() {
  return getManufacturingIdColumn_() + 5;
}

function getSalesAcceptedMessageDateColumn_() {
  return getManufacturingIdColumn_() + 6;
}

function getSalesAcceptedStateColumn_() {
  return getManufacturingIdColumn_() + 7;
}

function getSalesCanonicalDeliveryDateColumn_() {
  return getManufacturingIdColumn_() + 8;
}

function getSalesApprovalStateAnchorForRow_(sheet, row) {
  const anchorColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < anchorColumn ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return "";
  }

  return cleanString_(sheet.getRange(Number(row), anchorColumn).getDisplayValue());
}

function setSalesApprovalStateAnchorForRow_(sheet, row, anchorUtcString) {
  const anchorColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < anchorColumn ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return "";
  }

  const value = cleanString_(anchorUtcString) || nowUtcString_();
  sheet.getRange(Number(row), anchorColumn).setValue(value);
  return value;
}

function clearSalesApprovalStateAnchorForRow_(sheet, row) {
  const anchorColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < anchorColumn ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return;
  }

  sheet.getRange(Number(row), anchorColumn).clearContent();
}

function getSalesSyncMetadataForRow_(sheet, row) {
  const startColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < startColumn + 4 ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return {
      approvalAnchor: "",
      acceptedMessageId: "",
      acceptedMessageDate: "",
      acceptedState: "",
      canonicalDeliveryDate: "",
    };
  }

  const values = sheet
    .getRange(Number(row), startColumn, 1, 5)
    .getDisplayValues()[0];

  return {
    approvalAnchor: cleanString_(values[0]),
    acceptedMessageId: cleanString_(values[1]),
    acceptedMessageDate: cleanString_(values[2]),
    acceptedState: cleanString_(values[3]),
    canonicalDeliveryDate: cleanString_(values[4]),
  };
}

function setSalesSyncMetadataForRow_(sheet, row, data) {
  const startColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < startColumn + 4 ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return;
  }

  const current = getSalesSyncMetadataForRow_(sheet, row);

  sheet
    .getRange(Number(row), startColumn, 1, 5)
    .setValues([[
      cleanString_(data && data.approvalAnchor) || current.approvalAnchor,
      cleanString_(data && data.acceptedMessageId) || "",
      cleanString_(data && data.acceptedMessageDate) || "",
      cleanString_(data && data.acceptedState) || "",
      cleanString_(data && data.canonicalDeliveryDate) || "",
    ]]);
}

function clearSalesSyncMetadataForRow_(sheet, row) {
  const startColumn = getSalesApprovalStateAnchorColumn_();

  if (
    !sheet ||
    sheet.getMaxColumns() < startColumn + 4 ||
    !Number.isInteger(Number(row)) ||
    Number(row) < CFG.FIRST_DATA_ROW
  ) {
    return;
  }

  sheet.getRange(Number(row), startColumn, 1, 5).clearContent();
}

function clearSalesAcceptedSyncMetadataForRow_(sheet, row) {
  const current = getSalesSyncMetadataForRow_(sheet, row);

  setSalesSyncMetadataForRow_(sheet, row, {
    approvalAnchor: current.approvalAnchor,
    acceptedMessageId: "",
    acceptedMessageDate: "",
    acceptedState: "",
    canonicalDeliveryDate: "",
  });
}

function formatSalesCanonicalDate_(value) {
  const parsedDate = parseSalesSheetDateValue_(value);
  if (!parsedDate) return "";

  return Utilities.formatDate(
    parsedDate,
    Session.getScriptTimeZone(),
    "yyyy-MM-dd"
  );
}

function isSalesMessageNewerThanAccepted_(
  incomingMessageDate,
  incomingMessageId,
  acceptedMessageDate,
  acceptedMessageId
) {
  const normalizedIncomingDate = cleanString_(incomingMessageDate);
  const normalizedAcceptedDate = cleanString_(acceptedMessageDate);
  const normalizedIncomingId = cleanString_(incomingMessageId);
  const normalizedAcceptedId = cleanString_(acceptedMessageId);

  if (!normalizedAcceptedDate && !normalizedAcceptedId) {
    return true;
  }

  if (normalizedIncomingDate && normalizedAcceptedDate) {
    if (isUtcStringAfter_(normalizedIncomingDate, normalizedAcceptedDate)) {
      return true;
    }

    if (isUtcStringAfter_(normalizedAcceptedDate, normalizedIncomingDate)) {
      return false;
    }
  }

  if (normalizedIncomingId && normalizedAcceptedId) {
    const incomingNumericId = Number(normalizedIncomingId);
    const acceptedNumericId = Number(normalizedAcceptedId);

    if (
      Number.isInteger(incomingNumericId) &&
      Number.isInteger(acceptedNumericId)
    ) {
      return incomingNumericId > acceptedNumericId;
    }

    return normalizedIncomingId > normalizedAcceptedId;
  }

  return !normalizedAcceptedDate && !normalizedAcceptedId;
}

function getJobsHistorySheet_() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  return spreadsheet
    ? spreadsheet.getSheetByName("TRABAJOS HISTORICO")
    : null;
}

function getSalesHistoryRowKeysCacheProperty_() {
  return "ODOO_SALES_HISTORY_ROW_KEYS_CACHE_PAYLOAD_V2";
}

function getSalesHistoryRowKeysCacheServiceKey_() {
  return "ODOO_SALES_HISTORY_ROW_KEYS_CACHE_PAYLOAD_V2";
}

function clearSalesHistoryRowKeysCache_() {
  const properties = PropertiesService.getScriptProperties();
  properties.deleteProperty(getSalesHistoryRowKeysCacheProperty_());

  try {
    CacheService.getScriptCache().remove(
      getSalesHistoryRowKeysCacheServiceKey_()
    );
  } catch (err) {}
}

function buildSalesHistoryRowKeysCacheSignature_(historySheet, rowCount) {
  if (!historySheet || !rowCount) return "empty";

  const sampleCount = Math.min(5, rowCount);
  const sampleOrderValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, sampleCount, 1)
    .getDisplayValues()
    .map((row) => cleanString_(row[0]));
  const sampleMetadataValues = historySheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      getManufacturingIdColumn_(),
      sampleCount,
      4
    )
    .getDisplayValues()
    .map((row) => [
      cleanString_(row[1]),
      cleanString_(row[2]),
      cleanString_(row[3]),
    ]);

  return JSON.stringify({
    rowCount,
    sampleOrderValues,
    sampleMetadataValues,
  });
}

function parseSalesHistoryRowKeysCachePayload_(rawValue) {
  try {
    const parsed = JSON.parse(rawValue);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (err) {
    return null;
  }
}

function getCachedSalesHistoryRowKeys_(cacheSignature) {
  if (!cacheSignature) {
    return { keySet: null, source: "missing_signature" };
  }

  const cacheSources = [];

  try {
    cacheSources.push({
      source: "script_cache",
      raw: CacheService.getScriptCache().get(
        getSalesHistoryRowKeysCacheServiceKey_()
      ),
    });
  } catch (err) {}

  cacheSources.push({
    source: "script_properties",
    raw: PropertiesService.getScriptProperties().getProperty(
      getSalesHistoryRowKeysCacheProperty_()
    ),
  });

  for (const cacheSource of cacheSources) {
    if (!cacheSource.raw) continue;

    const payload = parseSalesHistoryRowKeysCachePayload_(cacheSource.raw);
    if (!payload) continue;
    if (cleanString_(payload.signature) !== cacheSignature) continue;
    if (!Array.isArray(payload.keys)) continue;

    return {
      keySet: new Set(payload.keys),
      source: cacheSource.source,
    };
  }

  return { keySet: null, source: "miss" };
}

function saveCachedSalesHistoryRowKeys_(cacheSignature, archivedKeys) {
  const payload = JSON.stringify({
    signature: cleanString_(cacheSignature),
    keys: Array.from(archivedKeys || []),
  });

  PropertiesService.getScriptProperties().setProperty(
    getSalesHistoryRowKeysCacheProperty_(),
    payload
  );

  try {
    CacheService.getScriptCache().put(
      getSalesHistoryRowKeysCacheServiceKey_(),
      payload,
      21600
    );
  } catch (err) {}
}

function getSheetOperationalRowCount_(sheet) {
  if (!sheet) return 0;

  const lastRow =
    typeof getOperationalLastRow_ === "function"
      ? getOperationalLastRow_(sheet)
      : sheet.getLastRow();

  return Math.max(0, lastRow - CFG.FIRST_DATA_ROW + 1);
}

function buildSalesSheetSnapshot_(sheet) {
  const rowCount = getSheetOperationalRowCount_(sheet);

  if (!sheet || !rowCount) {
    return {
      sheet,
      rowCount: 0,
      orderValues: [],
      deliveryStateValues: [],
      metadataValues: [],
      markerValues: [],
      salesSnapshotFlags: [],
    };
  }

  return {
    sheet,
    rowCount,
    orderValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
      .getDisplayValues(),
    deliveryStateValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, 8, rowCount, 2)
      .getDisplayValues(),
    metadataValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, getManufacturingIdColumn_(), rowCount, 4)
      .getDisplayValues(),
    markerValues: sheet
      .getRange(
        CFG.FIRST_DATA_ROW,
        CFG.NEW_ROW_CHECKBOX_COL,
        rowCount,
        1
      )
      .getValues(),
    salesSnapshotFlags: getSalesSnapshotFlagsForSheet_(sheet, rowCount),
  };
}

function buildSalesHistoryRowKeysFromValues_(
  orderName,
  saleOrderId,
  saleLineId
) {
  const keys = [];
  const normalizedSaleLineId = cleanString_(saleLineId);
  const normalizedSaleOrderId = cleanString_(saleOrderId);
  const orderKey = normalizeOrderNumberKey_(orderName);

  if (normalizedSaleLineId) {
    keys.push(`line:${normalizedSaleLineId}`);
  } else if (normalizedSaleOrderId && orderKey) {
    keys.push(`sale:${normalizedSaleOrderId}|order:${orderKey}`);
  } else if (orderKey) {
    keys.push(`order:${orderKey}`);
  }

  return keys;
}

function getSalesSnapshotFlagsForSheet_(sheet, rowCount) {
  if (!sheet || !rowCount) return [];

  const linkRange = sheet.getRange(
    CFG.FIRST_DATA_ROW,
    CFG.LINK_COL,
    rowCount,
    1
  );
  const richTextValues = linkRange.getRichTextValues();
  const notes = linkRange.getNotes();
  const formulas = linkRange.getFormulas();
  const displayValues = linkRange.getDisplayValues();

  return richTextValues.map((rowValue, index) =>
    isSalesRowSnapshot_(
      rowValue[0],
      notes[index][0],
      formulas[index][0],
      displayValues[index][0]
    )
  );
}

function getRowsWithoutOriginIndexes_(metadataValues) {
  const indexes = [];

  for (let index = 0; index < (metadataValues || []).length; index++) {
    if (!cleanString_(metadataValues[index][3])) {
      indexes.push(index);
    }
  }

  return indexes;
}

function getSalesSnapshotFlagsForRowIndexes_(sheet, rowIndexes) {
  const flags = {};
  const normalizedIndexes = Array.from(
    new Set(
      (rowIndexes || [])
        .map((index) => Number(index))
        .filter((index) => Number.isInteger(index) && index >= 0)
    )
  ).sort((left, right) => left - right);

  if (!sheet || !normalizedIndexes.length) return flags;

  const indexGroups = [];
  let currentGroup = [normalizedIndexes[0]];

  for (let index = 1; index < normalizedIndexes.length; index++) {
    const currentIndex = normalizedIndexes[index];
    const previousIndex = normalizedIndexes[index - 1];

    if (currentIndex === previousIndex + 1) {
      currentGroup.push(currentIndex);
      continue;
    }

    indexGroups.push(currentGroup);
    currentGroup = [currentIndex];
  }

  indexGroups.push(currentGroup);

  for (const group of indexGroups) {
    const firstIndex = group[0];
    const lastIndex = group[group.length - 1];
    const startRow = CFG.FIRST_DATA_ROW + firstIndex;
    const rowCount = lastIndex - firstIndex + 1;
    const linkRange = sheet.getRange(startRow, CFG.LINK_COL, rowCount, 1);
    const richTextValues = linkRange.getRichTextValues();
    const notes = linkRange.getNotes();
    const formulas = linkRange.getFormulas();
    const displayValues = linkRange.getDisplayValues();

    for (let offset = 0; offset < rowCount; offset++) {
      flags[firstIndex + offset] = isSalesRowSnapshot_(
        richTextValues[offset][0],
        notes[offset][0],
        formulas[offset][0],
        displayValues[offset][0]
      );
    }
  }

  return flags;
}

function buildActiveArchivedSalesIndex_(sheetSnapshot) {
  const archivedRowKeys = new Set();
  const rowsByOrderKey = new Map();
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet
      ? sheetSnapshot
      : buildSalesSheetSnapshot_(getTargetSheet_());

  if (!snapshot.rowCount) {
    return {
      rowKeys: archivedRowKeys,
      rowsByOrderKey,
      rowCount: 0,
    };
  }

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (cleanString_(snapshot.deliveryStateValues[index][1]) !== "Archivar") {
      continue;
    }

    const origin = cleanString_(snapshot.metadataValues[index][3]).toUpperCase();

    if (origin && origin !== "VENTA") continue;
    if (!origin && !snapshot.salesSnapshotFlags[index]) continue;

    const orderName = snapshot.orderValues[index][0];
    const saleOrderId = snapshot.metadataValues[index][1];
    const saleLineId = snapshot.metadataValues[index][2];

    for (const key of buildSalesHistoryRowKeysFromValues_(
      orderName,
      saleOrderId,
      saleLineId
    )) {
      archivedRowKeys.add(key);
    }

    const orderKey = normalizeOrderNumberKey_(orderName);
    if (!orderKey) continue;

    if (!rowsByOrderKey.has(orderKey)) {
      rowsByOrderKey.set(orderKey, new Set());
    }

    rowsByOrderKey.get(orderKey).add(CFG.FIRST_DATA_ROW + index);
  }

  return {
    rowKeys: archivedRowKeys,
    rowsByOrderKey,
    rowCount: snapshot.rowCount,
  };
}

function getSalesHistoryRowKeys_() {
  const startedAtMs = Date.now();
  const historySheet = getJobsHistorySheet_();
  const rowCount = getSheetOperationalRowCount_(historySheet);

  if (!historySheet || !rowCount) {
    clearSalesHistoryRowKeysCache_();
    logSalesSyncStage_(
      "historico_ventas_claves",
      startedAtMs,
      "Sin hoja historica o sin filas operativas."
    );
    return new Set();
  }

  // La exclusion de archivados debe priorizar consistencia sobre cache:
  // si el historico cambia sin alterar la firma muestreada, una cache vieja
  // puede reimportar ventas ya archivadas.
  clearSalesHistoryRowKeysCache_();
  logSalesSyncStage_(
    "historico_ventas_claves_cache",
    startedAtMs,
    "cache_bypass_por_consistencia"
  );

  const archivedKeys = new Set();

  const orderValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
    .getDisplayValues();
  const metadataValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, getManufacturingIdColumn_(), rowCount, 4)
    .getDisplayValues();
  const rowsWithoutOrigin = getRowsWithoutOriginIndexes_(metadataValues);
  const salesSnapshotFlagsByIndex = getSalesSnapshotFlagsForRowIndexes_(
    historySheet,
    rowsWithoutOrigin
  );

  for (let index = 0; index < rowCount; index++) {
    const origin = cleanString_(metadataValues[index][3]).toUpperCase();
    if (origin && origin !== "VENTA") continue;
    if (!origin && !salesSnapshotFlagsByIndex[index]) continue;

    for (const key of buildSalesHistoryRowKeysFromValues_(
      orderValues[index][0],
      metadataValues[index][1],
      metadataValues[index][2]
    )) {
      archivedKeys.add(key);
    }
  }

  logSalesSyncStage_(
    "historico_ventas_claves",
    startedAtMs,
    `Filas revisadas=${rowCount}; claves=${archivedKeys.size}`
  );
  return archivedKeys;
}

function getActiveArchivedSalesRowKeys_(sheetSnapshot, archivedSalesIndex) {
  const startedAtMs = Date.now();
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet
      ? sheetSnapshot
      : buildSalesSheetSnapshot_(getTargetSheet_());
  const activeArchivedSalesIndex =
    archivedSalesIndex || buildActiveArchivedSalesIndex_(snapshot);

  if (!snapshot.sheet || !snapshot.rowCount) {
    logSalesSyncStage_(
      "activos_archivados_ventas",
      startedAtMs,
      "Sin hoja activa o sin filas operativas."
    );
    return activeArchivedSalesIndex.rowKeys;
  }

  logSalesSyncStage_(
    "activos_archivados_ventas",
    startedAtMs,
    `Filas revisadas=${activeArchivedSalesIndex.rowCount}; claves=${activeArchivedSalesIndex.rowKeys.size}`
  );
  return activeArchivedSalesIndex.rowKeys;
}

function getArchivedSalesRowKeys_(sheetSnapshot, archivedSalesIndex) {
  const archivedKeys = getSalesHistoryRowKeys_();

  for (const key of getActiveArchivedSalesRowKeys_(
    sheetSnapshot,
    archivedSalesIndex
  )) {
    archivedKeys.add(key);
  }

  return archivedKeys;
}

function isArchivedSalesRowKey_(archivedKeys, data) {
  const saleLineId = cleanString_(data && data.saleLineId);
  if (saleLineId && archivedKeys.has(`line:${saleLineId}`)) {
    return true;
  }

  const saleOrderId = cleanString_(
    data && (data.saleOrderId || data.saleId)
  );
  const orderKey = normalizeOrderNumberKey_(data && data.orderName);

  if (
    saleOrderId &&
    orderKey &&
    archivedKeys.has(`sale:${saleOrderId}|order:${orderKey}`)
  ) {
    return true;
  }

  return orderKey ? archivedKeys.has(`order:${orderKey}`) : false;
}

function buildSalesManualStateAnchorDiagnosisForRow_(sheet, row) {
  if (!sheet) {
    return "Diagnóstico ancla manual\n\nNo se encontró la hoja.";
  }

  if (row < CFG.FIRST_DATA_ROW) {
    return (
      "Diagnóstico ancla manual\n\n" +
      `La fila ${row} no pertenece al área operativa.`
    );
  }

  const context = getSalesFinalizationContextFromRow_(sheet, row);
  const anchorKey = buildSalesManualStateAnchorKey_(context);
  const anchorUtcString = getSalesManualStateAnchor_(context);
  const currentState = cleanString_(
    sheet.getRange(row, CFG.STATE_COL).getDisplayValue()
  );
  const orderName = cleanString_(
    sheet.getRange(row, CFG.ORDER_COL).getDisplayValue()
  );

  return (
    "Diagnóstico ancla manual\n\n" +
    `Fila: ${row}\n` +
    `Origen: ${cleanString_(context.origin) || "(vacío)"}\n` +
    `Orden: ${orderName || "(vacía)"}\n` +
    `Producto: ${cleanString_(context.productName) || "(vacío)"}\n` +
    `Estado actual: ${currentState || "(vacío)"}\n` +
    `sale.order.id: ${cleanString_(context.saleOrderId) || "(vacío)"}\n` +
    `sale.order.line.id: ${cleanString_(context.saleLineId) || "(vacío)"}\n` +
    `Código línea: ${cleanString_(context.lineCode) || "(vacío)"}\n` +
    `Clave ancla: ${anchorKey || "(sin clave)"}\n` +
    (
      anchorUtcString
        ? `Ancla manual activa desde: ${anchorUtcString}`
        : "Ancla manual: no activa"
    )
  );
}

function parseNumericCsvList_(rawValue) {
  return parseCsvList_(rawValue)
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value > 0);
}

function getSalesCreatorFilterConfig_() {
  const properties = PropertiesService.getScriptProperties();
  const allowedCreatorIds = parseNumericCsvList_(
    properties.getProperty("ODOO_SALES_ALLOWED_CREATE_UIDS")
  );
  const allowedCreatorNames = parseCsvList_(
    properties.getProperty("ODOO_SALES_ALLOWED_CREATE_UID_NAMES")
  );

  return {
    allowedCreatorIds,
    allowedCreatorNames,
    isConfigured:
      allowedCreatorIds.length > 0 || allowedCreatorNames.length > 0,
  };
}

function resolveSalesCreatorFilter_(cfg, uid) {
  const filterConfig = getSalesCreatorFilterConfig_();
  const resolvedIds = new Set(filterConfig.allowedCreatorIds);

  for (const creatorName of filterConfig.allowedCreatorNames) {
    const users =
      executeKw_(
        cfg,
        uid,
        "res.users",
        "search_read",
        [[["name", "ilike", creatorName]]],
        {
          fields: ["id", "name"],
          order: "id asc",
          limit: 20,
        }
      ) || [];

    for (const user of users) {
      const numericId = Number(user.id);
      if (Number.isInteger(numericId) && numericId > 0) {
        resolvedIds.add(numericId);
      }
    }
  }

  return {
    isConfigured: filterConfig.isConfigured,
    creatorIds: Array.from(resolvedIds).sort((left, right) => left - right),
  };
}

function withSalesCreatorFilterDomain_(baseDomain, salesCreatorFilter) {
  const domain = (baseDomain || []).map((clause) =>
    Array.isArray(clause) ? clause.slice() : clause
  );

  if (!salesCreatorFilter || !salesCreatorFilter.isConfigured) {
    return domain;
  }

  if (!salesCreatorFilter.creatorIds.length) {
    domain.push(["id", "=", 0]);
    return domain;
  }

  domain.push(["create_uid", "in", salesCreatorFilter.creatorIds]);
  return domain;
}

/**
 * Punto de entrada con bloqueo para evitar ejecuciones simultáneas.
 */
function syncOdooSalesOrdersNeo() {
  const lock = LockService.getScriptLock();

  if (!lock.tryLock(1000)) {
    logDebug_(
      "Sincronización de ventas omitida: ya existe otra ejecución activa."
    );
    return {
      inserted: 0,
      updated: 0,
      removed: 0,
      skippedLocked: true,
    };
  }

  try {
    return syncOdooSalesOrdersNeoUnlocked_();
  } finally {
    lock.releaseLock();
  }
}

function syncOdooSalesOrdersNeoUnlocked_() {
  const syncStartedAtMs = Date.now();
  const sheet = getTargetSheet_();
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  if (typeof appendSyncLog_ === "function") {
    appendSyncLog_({
      module: "VENTAS",
      action: "sync_start",
      origin: "VENTA",
      details: "Inicio de sincronizacion de ventas.",
    });
  }

  logSalesSyncStage_(
    "inicio",
    syncStartedAtMs,
    "Preparando sincronizacion de ventas NEO."
  );
  const uid = odooLogin_(cfg);
  logSalesSyncStage_(
    "login_odoo",
    syncStartedAtMs,
    `uid=${cleanString_(uid)}`
  );
  const properties = PropertiesService.getScriptProperties();
  const importedIds = getSalesImportedIds_();
  const skippedIds = getSalesSkippedIds_();
  const skippedWriteDateById = getSalesSkippedWriteDates_();
  const salesFinalizationNotifiedKeys = getSalesFinalizationNotifiedKeys_();
  const salesApprovalNotifiedKeys = getSalesApprovalNotifiedKeys_();
  const salesPausedNotifiedKeys = getSalesPausedNotifiedKeys_();
  const activeSheetSnapshot = buildSalesSheetSnapshot_(sheet);
  logSalesSyncStage_(
    "snapshot_hoja_activa",
    syncStartedAtMs,
    `filas=${activeSheetSnapshot.rowCount}`
  );
  const existingSalesRowsMap = getExistingSalesOrderRowsMap_(
    sheet,
    activeSheetSnapshot
  );
  logSalesSyncStage_(
    "mapa_filas_existentes",
    syncStartedAtMs,
    `ordenes=${existingSalesRowsMap.size}`
  );
  const incompleteOrderKeys = getIncompleteSalesOrderKeys_(
    sheet,
    existingSalesRowsMap,
    activeSheetSnapshot
  );
  logSalesSyncStage_(
    "ordenes_incompletas",
    syncStartedAtMs,
    `claves=${incompleteOrderKeys.size}`
  );
  const activeArchivedSalesIndex = buildActiveArchivedSalesIndex_(
    activeSheetSnapshot
  );
  const archivedSalesRowKeys = getArchivedSalesRowKeys_(
    activeSheetSnapshot,
    activeArchivedSalesIndex
  );
  logSalesSyncStage_(
    "claves_archivadas",
    syncStartedAtMs,
    `claves=${archivedSalesRowKeys.size}`
  );
  const syncStartedAt = nowUtcString_();
  const lastSync = properties.getProperty(SALES_CFG.LAST_SYNC_PROPERTY);
  const fromDate = lastSync
    ? shiftUtcString_(lastSync, -SALES_CFG.SYNC_OVERLAP_MINUTES)
    : daysAgoUtcString_(SALES_CFG.INITIAL_LOOKBACK_DAYS);
  const salesCreatorFilter = resolveSalesCreatorFilter_(cfg, uid);

  if (salesCreatorFilter.isConfigured) {
    logDebug_(
      salesCreatorFilter.creatorIds.length
        ? `Filtro ventas por create_uid activo: ${salesCreatorFilter.creatorIds.join(", ")}`
        : "Filtro ventas por create_uid activo, pero no resolvio usuarios."
    );
  }

  const orders = fetchChangedSalesOrders_(
    cfg,
    uid,
    fromDate,
    skippedIds,
    skippedWriteDateById,
    existingSalesRowsMap,
    incompleteOrderKeys,
    salesCreatorFilter
  );
  logSalesSyncStage_(
    "ordenes_cambiadas",
    syncStartedAtMs,
    `ordenes=${orders.length}; fromDate=${fromDate}`
  );

  orders.sort((leftOrder, rightOrder) => {
    const leftKey = normalizeOrderNumberKey_(leftOrder.name);
    const rightKey = normalizeOrderNumberKey_(rightOrder.name);
    const leftPriority = incompleteOrderKeys.has(leftKey) ? 0 : 1;
    const rightPriority = incompleteOrderKeys.has(rightKey) ? 0 : 1;
    return leftPriority - rightPriority;
  });

  const productLinesByOrderId = fetchSaleOrderProductLinesMap_(
    cfg,
    uid,
    orders.map((order) => order.id)
  );
  const orderIdsWithProductLines = orders
    .map((order) => cleanString_(order.id))
    .filter((orderId) => {
      const productLines = productLinesByOrderId.get(orderId) || [];
      return productLines.length > 0;
    });
  logSalesSyncStage_(
    "lineas_precargadas",
    syncStartedAtMs,
    `ordenes=${productLinesByOrderId.size}; con_lineas=${orderIdsWithProductLines.length}`
  );
  const latestNotesByOrderId = fetchLatestSalesNotesMap_(
    cfg,
    uid,
    orderIdsWithProductLines
  );
  logSalesSyncStage_(
    "notas_precargadas",
    syncStartedAtMs,
    `ordenes_con_nota=${latestNotesByOrderId.size}`
  );

  let inserted = 0;
  let updated = 0;
  let unchanged = 0;
  let removed = 0;
  let needsAutoSort = false;
  let nextRow = getFirstAvailableRow_(sheet);
  let processedOrders = 0;
  let salesFinalizationNotificationsChanged = false;
  let salesApprovalNotificationsChanged = false;
  let salesPausedNotificationsChanged = false;

  for (const order of orders) {
    processedOrders++;
    const saleId = cleanString_(order.id);
    const orderName = cleanString_(order.name);
    const orderKey = normalizeOrderNumberKey_(orderName);
    const archivedRowsForOrder =
      orderKey && activeArchivedSalesIndex.rowsByOrderKey.has(orderKey)
        ? activeArchivedSalesIndex.rowsByOrderKey.get(orderKey)
        : null;

    if (!saleId || !orderName) continue;

    const existingRows =
      orderKey && existingSalesRowsMap.has(orderKey)
        ? existingSalesRowsMap
            .get(orderKey)
            .filter(
              (row) => !archivedRowsForOrder || !archivedRowsForOrder.has(row)
            )
        : [];

    if (cleanString_(order.state).toLowerCase() === "cancel") {
      if (existingRows.length) {
        if (
          clearSalesFinalizationNotificationKeysForRows_(
            sheet,
            existingRows,
            salesFinalizationNotifiedKeys
          )
        ) {
          salesFinalizationNotificationsChanged = true;
        }
        if (
          clearSalesApprovalNotificationKeysForRows_(
            sheet,
            existingRows,
            salesApprovalNotifiedKeys
          )
        ) {
          salesApprovalNotificationsChanged = true;
        }
        if (
          clearSalesPausedNotificationKeysForRows_(
            sheet,
            existingRows,
            salesPausedNotifiedKeys
          )
        ) {
          salesPausedNotificationsChanged = true;
        }

        clearSalesOrderRows_(sheet, existingRows);
        removed += existingRows.length;
        needsAutoSort = true;
        existingSalesRowsMap.delete(orderKey);
        nextRow = getFirstAvailableRow_(sheet);
      }

      importedIds.delete(saleId);
      skippedIds.delete(saleId);
      clearSalesSkippedWriteDate_(skippedWriteDateById, saleId);
      logDebug_(`Orden de venta cancelada y eliminada: ${orderName}`);
      continue;
    }

    const productLines = productLinesByOrderId.get(saleId) || [];

    if (!productLines.length) {
      if (existingRows.length) {
        if (
          clearSalesFinalizationNotificationKeysForRows_(
            sheet,
            existingRows,
            salesFinalizationNotifiedKeys
          )
        ) {
          salesFinalizationNotificationsChanged = true;
        }
        if (
          clearSalesApprovalNotificationKeysForRows_(
            sheet,
            existingRows,
            salesApprovalNotifiedKeys
          )
        ) {
          salesApprovalNotificationsChanged = true;
        }
        if (
          clearSalesPausedNotificationKeysForRows_(
            sheet,
            existingRows,
            salesPausedNotifiedKeys
          )
        ) {
          salesPausedNotificationsChanged = true;
        }

        clearSalesOrderRows_(sheet, existingRows);
        removed += existingRows.length;
        needsAutoSort = true;
        existingSalesRowsMap.delete(orderKey);
        nextRow = getFirstAvailableRow_(sheet);
      }

      importedIds.delete(saleId);
      skippedIds.add(saleId);
      setSalesSkippedWriteDate_(
        skippedWriteDateById,
        saleId,
        order.write_date
      );
      logDebug_(`Orden sin líneas de producto válidas: ${orderName}`);
      continue;
    }

    const numericSaleId = Number(saleId);
    const noteInfo =
      latestNotesByOrderId.get(saleId) ||
      (
        Number.isInteger(numericSaleId) && numericSaleId > 0
          ? extractLatestSalesNoteSafely_(cfg, uid, numericSaleId)
          : {
              date: "",
              state: "",
              sourceMessageDate: "",
              sourceMessageId: "",
              authorName: "",
            }
      );

    if (!noteInfo.date) {
      if (existingRows.length) {
        if (
          clearSalesFinalizationNotificationKeysForRows_(
            sheet,
            existingRows,
            salesFinalizationNotifiedKeys
          )
        ) {
          salesFinalizationNotificationsChanged = true;
        }
        if (
          clearSalesApprovalNotificationKeysForRows_(
            sheet,
            existingRows,
            salesApprovalNotifiedKeys
          )
        ) {
          salesApprovalNotificationsChanged = true;
        }
        if (
          clearSalesPausedNotificationKeysForRows_(
            sheet,
            existingRows,
            salesPausedNotifiedKeys
          )
        ) {
          salesPausedNotificationsChanged = true;
        }

        clearSalesOrderRows_(sheet, existingRows);
        removed += existingRows.length;
        needsAutoSort = true;
        existingSalesRowsMap.delete(orderKey);
        nextRow = getFirstAvailableRow_(sheet);
      }

      importedIds.delete(saleId);
      skippedIds.add(saleId);
      setSalesSkippedWriteDate_(
        skippedWriteDateById,
        saleId,
        order.write_date
      );
      logDebug_(
        `Orden omitida porque no tiene una fecha reconocible: ${orderName}`
      );
      continue;
    }

    skippedIds.delete(saleId);
    clearSalesSkippedWriteDate_(skippedWriteDateById, saleId);

    const matchedResponsible = resolveSalesResponsible_(order, noteInfo);
    const customerName = getMany2oneName_(order.partner_id);
    const orderDateFormatted = formatDateForSheet_(
      order.date_order || order.create_date
    );
    const existingLineIdentitiesByRow = buildSalesLineIdentityMapForRows_(
      sheet,
      existingRows
    );
    const usedRows = new Set();
    let processedLineCount = 0;

    const clearedArchivedRows = new Set();

    for (const line of productLines) {
      const isArchivedLine = isArchivedSalesRowKey_(
        archivedSalesRowKeys,
        {
          saleId,
          saleLineId: line.lineId,
          lineCode: line.code,
          orderName,
        }
      );

      let targetRow = findExistingSalesLineRow_(
        sheet,
        existingRows,
        usedRows,
        line.lineId,
        line.code,
        existingLineIdentitiesByRow
      );
      const isExistingRow = Boolean(targetRow);

      // Una venta que ya está en TRABAJOS HISTORICO no debe volver a la hoja
      // operativa aunque tenga una nota nueva o se haya modificado una línea
      // en Odoo. Si una ejecución anterior ya la reingresó, se limpia aquí.
      if (isArchivedLine) {
        if (targetRow && !clearedArchivedRows.has(targetRow)) {
          const archivedRowContext = getSalesFinalizationContextFromRow_(
            sheet,
            targetRow
          );
          if (
            clearSalesFinalizationNotificationKeysForRows_(
              sheet,
              [targetRow],
              salesFinalizationNotifiedKeys,
              new Map([[targetRow, archivedRowContext]])
            )
          ) {
            salesFinalizationNotificationsChanged = true;
          }
          if (
            clearSalesApprovalNotificationKeysForRows_(
              sheet,
              [targetRow],
              salesApprovalNotifiedKeys,
              new Map([[targetRow, archivedRowContext]])
            )
          ) {
            salesApprovalNotificationsChanged = true;
          }
          if (
            clearSalesPausedNotificationKeysForRows_(
              sheet,
              [targetRow],
              salesPausedNotifiedKeys,
              new Map([[targetRow, archivedRowContext]])
            )
          ) {
            salesPausedNotificationsChanged = true;
          }

          clearSalesOrderRows_(sheet, [targetRow]);
          clearedArchivedRows.add(targetRow);
          const rowIndex = existingRows.indexOf(targetRow);
          if (rowIndex !== -1) existingRows.splice(rowIndex, 1);
          removed++;
          needsAutoSort = true;
        }

        logDebug_(
          `Orden de venta omitida por estar en histórico: ${orderName} | línea=${line.lineId}`
        );
        continue;
      }

      if (!targetRow) {
        nextRow = findNextAvailableRowFrom_(sheet, nextRow);

        if (!nextRow) {
          Logger.log(
            `No hay fila libre para la orden ${orderName} (id=${saleId})`
          );
          break;
        }

        targetRow = nextRow;
        nextRow++;
      }

      const writeResult = writeSalesOrderLineRow_(sheet, targetRow, {
        cfg,
        saleId,
        saleLineId: line.lineId,
        orderName,
        matchedResponsible,
        customerName,
        description: line.description,
        quantity: line.quantity,
        lineCode: line.code,
        orderDateFormatted,
        noteDateFormatted: noteInfo.date,
        noteSourceMessageDate: noteInfo.sourceMessageDate,
        noteSourceMessageId: noteInfo.sourceMessageId,
        noteState: noteInfo.state,
        defaultState: SALES_CFG.DEFAULT_STATE_WHEN_NOTE_HAS_DATE,
        currentState: order.state,
        isExistingRow,
      });

      if (!isExistingRow) {
        markRowAsNew_(sheet, targetRow);
        inserted++;
        needsAutoSort = true;
        existingRows.push(targetRow);
        if (typeof appendSyncLog_ === "function") {
          appendSyncLog_({
            module: "VENTAS",
            action: "insert",
            order: orderName,
            odooId: saleId,
            origin: "VENTA",
            details:
              buildSalesWriteChangeSummary_(targetRow, writeResult) +
              "",
          });
        }
      } else {
        if (writeResult && writeResult.hasVisibleChanges) {
          updated++;
          if (typeof appendSyncLog_ === "function") {
            appendSyncLog_({
              module: "VENTAS",
              action: "update",
              order: orderName,
              odooId: saleId,
              origin: "VENTA",
              details: buildSalesWriteChangeSummary_(
                targetRow,
                writeResult
              ),
            });
          }
        } else {
          unchanged++;
        }
        if (writeResult && writeResult.requiresResort) {
          needsAutoSort = true;
        }
        if (
          writeResult &&
          syncSalesFinalizationNotificationForRow_(
            sheet,
            targetRow,
            writeResult.previousStateValue,
            writeResult.resultingStateValue,
            salesFinalizationNotifiedKeys
          )
        ) {
          salesFinalizationNotificationsChanged = true;
        }
        if (
          writeResult &&
          syncSalesApprovalNotificationForRow_(
            sheet,
            targetRow,
            writeResult.previousStateValue,
            writeResult.resultingStateValue,
            salesApprovalNotifiedKeys
          )
        ) {
          salesApprovalNotificationsChanged = true;
        }
        if (
          writeResult &&
          syncSalesPausedNotificationForRow_(
            sheet,
            targetRow,
            writeResult.previousStateValue,
            writeResult.resultingStateValue,
            salesPausedNotifiedKeys
          )
        ) {
          salesPausedNotificationsChanged = true;
        }
      }

      usedRows.add(targetRow);
      processedLineCount++;
    }

    if (processedLineCount > 0) {
      importedIds.add(saleId);
    }

    if (processedLineCount === productLines.length) {
      const obsoleteRows = existingRows.filter(
        (existingRow) => !usedRows.has(existingRow)
      );

      if (obsoleteRows.length) {
        if (
          clearSalesFinalizationNotificationKeysForRows_(
            sheet,
            obsoleteRows,
            salesFinalizationNotifiedKeys
          )
        ) {
          salesFinalizationNotificationsChanged = true;
        }
        if (
          clearSalesApprovalNotificationKeysForRows_(
            sheet,
            obsoleteRows,
            salesApprovalNotifiedKeys
          )
        ) {
          salesApprovalNotificationsChanged = true;
        }
        if (
          clearSalesPausedNotificationKeysForRows_(
            sheet,
            obsoleteRows,
            salesPausedNotifiedKeys
          )
        ) {
          salesPausedNotificationsChanged = true;
        }

        clearSalesOrderRows_(sheet, obsoleteRows);
        removed += obsoleteRows.length;
        needsAutoSort = true;
        nextRow = getFirstAvailableRow_(sheet);
      }

      if (orderKey) {
        existingSalesRowsMap.set(
          orderKey,
          Array.from(usedRows).sort((left, right) => left - right)
        );
      }
    } else if (orderKey && existingRows.length) {
      existingSalesRowsMap.set(orderKey, existingRows);
    }

    if (
      processedOrders === orders.length ||
      processedOrders % 25 === 0
    ) {
      logSalesSyncStage_(
        "procesando_ordenes",
        syncStartedAtMs,
        `procesadas=${processedOrders}/${orders.length}; nuevas=${inserted}; actualizadas=${updated}; quitadas=${removed}`
      );
    }
  }

  saveSalesImportedIds_(importedIds);
  saveSalesSkippedIds_(skippedIds);
  saveSalesSkippedWriteDates_(skippedWriteDateById);
  if (salesFinalizationNotificationsChanged) {
    saveSalesFinalizationNotifiedKeys_(salesFinalizationNotifiedKeys);
  }
  if (salesApprovalNotificationsChanged) {
    saveSalesApprovalNotifiedKeys_(salesApprovalNotifiedKeys);
  }
  if (salesPausedNotificationsChanged) {
    saveSalesPausedNotifiedKeys_(salesPausedNotifiedKeys);
  }
  properties.setProperty(SALES_CFG.LAST_SYNC_PROPERTY, syncStartedAt);
  logSalesSyncStage_(
    "propiedades_guardadas",
    syncStartedAtMs,
    `importadas=${importedIds.size}; omitidas=${skippedIds.size}`
  );

  if (needsAutoSort) {
    SpreadsheetApp.flush();
    ejecutarOrdenadoAutomatico();
    logSalesSyncStage_(
      "ordenado_automatico",
      syncStartedAtMs,
      `nuevas=${inserted}; actualizadas=${updated}; quitadas=${removed}`
    );
  } else if (inserted > 0 || updated > 0 || removed > 0) {
    logSalesSyncStage_(
      "ordenado_automatico_omitido",
      syncStartedAtMs,
      `nuevas=${inserted}; actualizadas=${updated}; quitadas=${removed}`
    );
  }

  showSpreadsheetToast_(
    `Sync ventas OK. Nuevas: ${inserted} | ` +
      `Actualizadas: ${updated} | Sin cambios: ${unchanged} | Quitadas: ${removed}`
  );
  if (typeof appendSyncLog_ === "function") {
    appendSyncLog_({
      module: "VENTAS",
      action: "sync_end",
      origin: "VENTA",
      details:
        `Nuevas=${inserted}; Actualizadas=${updated}; ` +
        `SinCambios=${unchanged}; Quitadas=${removed}.`,
    });
  }
  if (typeof flushSyncLogBuffer_ === "function") {
    flushSyncLogBuffer_();
  }
  logSalesSyncStage_(
    "fin",
    syncStartedAtMs,
    `nuevas=${inserted}; actualizadas=${updated}; quitadas=${removed}`
  );

  return { inserted, updated, removed };
}

function fetchChangedSalesOrders_(
  cfg,
  uid,
  fromDate,
  skippedIds,
  skippedWriteDateById,
  existingSalesRowsMap,
  incompleteOrderKeys,
  salesCreatorFilter
) {
  const orderFields = getSalesOrderFields_();
  const orders =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.sales,
      "search_read",
      [[
        ...withSalesCreatorFilterDomain_(
          [["write_date", ">=", fromDate]],
          salesCreatorFilter
        ),
      ]],
      {
        fields: orderFields,
        order: "write_date asc, id asc",
      }
    ) || [];
  const ordersById = new Map();

  for (const order of orders) {
    if (
      shouldSkipSalesOrderReprocessing_(
        order,
        skippedIds,
        skippedWriteDateById,
        existingSalesRowsMap,
        incompleteOrderKeys
      )
    ) {
      continue;
    }

    ordersById.set(String(order.id), order);
  }

  const messages =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.chatter,
      "search_read",
      [[
        ["model", "=", ODOO_MODELS.sales],
        ["date", ">=", fromDate],
        ["res_id", "!=", false],
      ]],
      {
        fields: ["res_id"],
        order: "date desc, id desc",
        limit: 1000,
      }
    ) || [];
  const missingOrderIds = [];
  const seenOrderIds = new Set();

  for (const message of messages) {
    const orderId = Number(message.res_id);
    if (!Number.isInteger(orderId) || orderId <= 0) continue;

    const orderIdKey = String(orderId);
    if (ordersById.has(orderIdKey) || seenOrderIds.has(orderIdKey)) {
      continue;
    }

    seenOrderIds.add(orderIdKey);
    missingOrderIds.push(orderId);
  }

  if (missingOrderIds.length) {
    const messagedOrders =
      executeKw_(
        cfg,
        uid,
        ODOO_MODELS.sales,
        "search_read",
        [[
          ...withSalesCreatorFilterDomain_(
            [
              ["id", "in", missingOrderIds],
              ["state", "!=", "cancel"],
            ],
            salesCreatorFilter
          ),
        ]],
        {
          fields: orderFields,
          order: "id asc",
        }
      ) || [];

    for (const order of messagedOrders) {
      ordersById.set(String(order.id), order);
    }
  }

  const recentOrders =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.sales,
      "search_read",
      [[
        ...withSalesCreatorFilterDomain_(
          [
            [
              "create_date",
              ">=",
              daysAgoUtcString_(SALES_CFG.INITIAL_LOOKBACK_DAYS),
            ],
            ["state", "!=", "cancel"],
          ],
          salesCreatorFilter
        ),
      ]],
      {
        fields: orderFields,
        order: "create_date asc, id asc",
      }
    ) || [];

  for (const order of recentOrders) {
    const saleId = cleanString_(order.id);
    if (!saleId || ordersById.has(saleId)) continue;

    const orderKey = normalizeOrderNumberKey_(order.name);
    const hasVisibleRows = Boolean(
      orderKey && existingSalesRowsMap.has(orderKey)
    );
    const needsReview = Boolean(
      orderKey && incompleteOrderKeys.has(orderKey)
    );
    const wasSkippedWithoutNote = skippedIds.has(saleId);
    const shouldSkipReprocessing = shouldSkipSalesOrderReprocessing_(
      order,
      skippedIds,
      skippedWriteDateById,
      existingSalesRowsMap,
      incompleteOrderKeys
    );

    if (
      !shouldSkipReprocessing &&
      (needsReview || (!hasVisibleRows && !wasSkippedWithoutNote))
    ) {
      ordersById.set(saleId, order);
    }
  }

  return Array.from(ordersById.values());
}

/**
 * ============================================================================
 * IMPORTACIÓN Y DIAGNÓSTICO PUNTUAL
 * ============================================================================
 */

function importSpecificNeoSaleOrder_(lookupValue) {
  const sheet = getTargetSheet_();
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    return {
      inserted: 0,
      message: "La configuración de Odoo no está completa.",
    };
  }

  const uid = odooLogin_(cfg);
  const order = findSaleOrderForDiagnosis_(cfg, uid, lookupValue);

  if (!order) {
    return {
      inserted: 0,
      message: `No se encontró la orden ${lookupValue}.`,
    };
  }

  if (cleanString_(order.state).toLowerCase() === "cancel") {
    return {
      inserted: 0,
      message: `La orden ${order.name} está cancelada.`,
    };
  }

  const orderKey = normalizeOrderNumberKey_(order.name);
  const existingOrderKeys = getExistingSheetOrderKeys_(sheet);

  if (orderKey && hasOrderKeyInSet_(existingOrderKeys, orderKey)) {
    return {
      inserted: 0,
      message: `La orden ${order.name} ya existe en la planilla.`,
    };
  }

  const activeSheetSnapshot = buildSalesSheetSnapshot_(sheet);
  const archivedSalesRowKeys = getArchivedSalesRowKeys_(
    activeSheetSnapshot,
    buildActiveArchivedSalesIndex_(activeSheetSnapshot)
  );
  if (
    isArchivedSalesRowKey_(archivedSalesRowKeys, {
      saleOrderId: cleanString_(order.id),
      orderName: order.name,
    })
  ) {
    return {
      inserted: 0,
      message: `La orden ${order.name} ya está en el histórico y no se reimportará automáticamente.`,
    };
  }

  const productLines = fetchSaleOrderProductLines_(cfg, uid, order.id);

  if (!productLines.length) {
    return {
      inserted: 0,
      message: `La orden ${order.name} no tiene líneas de producto válidas.`,
    };
  }

  const numericSaleId = Number(cleanString_(order.id));
  const noteInfo =
    Number.isInteger(numericSaleId) && numericSaleId > 0
      ? extractLatestSalesNoteSafely_(cfg, uid, numericSaleId)
      : {
          date: "",
          state: "",
          sourceMessageDate: "",
          sourceMessageId: "",
          authorName: "",
        };

  if (!noteInfo.date) {
    return {
      inserted: 0,
      message: `La orden ${order.name} no tiene una fecha reconocible en sus notas.`,
    };
  }

  const importedIds = getSalesImportedIds_();
  const matchedResponsible = resolveSalesResponsible_(order, noteInfo);
  const customerName = getMany2oneName_(order.partner_id);
  const orderDateFormatted = formatDateForSheet_(
    order.date_order || order.create_date
  );
  let nextRow = getFirstAvailableRow_(sheet);
  let inserted = 0;
  const insertedRows = [];

  for (const line of productLines) {
    nextRow = findNextAvailableRowFrom_(sheet, nextRow);

    if (!nextRow) {
      return {
        inserted,
        message: `No hay fila libre para importar ${order.name}.`,
      };
    }

    writeSalesOrderLineRow_(sheet, nextRow, {
      cfg,
      saleId: cleanString_(order.id),
      saleLineId: line.lineId,
      orderName: cleanString_(order.name),
      matchedResponsible,
      customerName,
      description: line.description,
      quantity: line.quantity,
      lineCode: line.code,
      orderDateFormatted,
      noteDateFormatted: noteInfo.date,
      noteSourceMessageDate: noteInfo.sourceMessageDate,
      noteSourceMessageId: noteInfo.sourceMessageId,
      noteState: noteInfo.state,
      defaultState: SALES_CFG.DEFAULT_STATE_WHEN_NOTE_HAS_DATE,
      currentState: order.state,
      isExistingRow: false,
    });

    markRowAsNew_(sheet, nextRow);
    insertedRows.push(nextRow);
    nextRow++;
    inserted++;
  }

  importedIds.add(String(order.id));
  saveSalesImportedIds_(importedIds);

  if (inserted > 0) {
    SpreadsheetApp.flush();
    ejecutarOrdenadoAutomatico();
  }

  return {
    inserted,
    message:
      `Se importó ${order.name} con ${inserted} fila(s) en: ` +
      `${insertedRows.join(", ")}.`,
  };
}

function repairExistingSalesHiddenMetadata() {
  const sheet = getTargetSheet_();
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  const existingSalesRowsMap = getExistingSalesOrderRowsMap_(sheet);
  if (!existingSalesRowsMap.size) {
    showSpreadsheetToast_(
      "No se encontraron filas de ventas NEO para reparar."
    );
    return {
      processedOrders: 0,
      foundOrders: 0,
      updatedRows: 0,
      matchedRows: 0,
      fallbackRows: 0,
      missingOrders: [],
    };
  }

  const uid = odooLogin_(cfg);
  const resolvedOrders = [];
  const missingOrders = [];

  for (const [orderKey, rows] of existingSalesRowsMap.entries()) {
    const orderName = cleanString_(
      sheet.getRange(rows[0], CFG.ORDER_COL).getDisplayValue()
    );
    const lookupValue = orderName || orderKey;
    if (!lookupValue) continue;

    const order = findSaleOrderForDiagnosis_(cfg, uid, lookupValue);
    if (!order) {
      missingOrders.push(lookupValue);
      continue;
    }

    resolvedOrders.push({
      order,
      orderKey,
      rows: rows.slice(),
    });
  }

  const productLinesByOrderId = fetchSaleOrderProductLinesMap_(
    cfg,
    uid,
    resolvedOrders.map((entry) => entry.order.id)
  );

  let updatedRows = 0;
  let matchedRows = 0;
  let fallbackRows = 0;

  for (const entry of resolvedOrders) {
    const saleId = cleanString_(entry.order.id);
    const productLines = productLinesByOrderId.get(saleId) || [];
    const existingLineIdentitiesByRow = buildSalesLineIdentityMapForRows_(
      sheet,
      entry.rows
    );
    const usedRows = new Set();

    for (const line of productLines) {
      const targetRow = findExistingSalesLineRow_(
        sheet,
        entry.rows,
        usedRows,
        line.lineId,
        line.code,
        existingLineIdentitiesByRow
      );
      if (!targetRow) continue;

      setSalesRowHiddenMetadata_(sheet, targetRow, saleId, line.lineId);
      usedRows.add(targetRow);
      updatedRows++;
      matchedRows++;
    }

    for (const row of entry.rows) {
      if (usedRows.has(row)) continue;

      setSalesRowHiddenMetadata_(sheet, row, saleId, "");
      updatedRows++;
      fallbackRows++;
    }
  }

  SpreadsheetApp.flush();

  const message =
    `Metadatos ventas reparados. ` +
    `Órdenes: ${resolvedOrders.length}/${existingSalesRowsMap.size} | ` +
    `Filas: ${updatedRows} | ` +
    `Coincidencias: ${matchedRows} | ` +
    `Fallback: ${fallbackRows}`;

  showSpreadsheetToast_(message);

  return {
    processedOrders: existingSalesRowsMap.size,
    foundOrders: resolvedOrders.length,
    updatedRows,
    matchedRows,
    fallbackRows,
    missingOrders,
  };
}

function buildNeoSaleOrderDiagnosisReport_(lookupValue) {
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    return (
      "Diagnóstico de venta\n\n" +
      "La configuración de Odoo no está completa."
    );
  }

  const uid = odooLogin_(cfg);
  const order = findSaleOrderForDiagnosis_(cfg, uid, lookupValue);

  if (!order) {
    return (
      "Diagnóstico de venta\n\n" +
      `No se encontró una orden para: ${lookupValue}`
    );
  }

  const lines = fetchSaleOrderProductLines_(cfg, uid, order.id);
  const numericSaleId = Number(cleanString_(order.id));
  const noteInfo =
    Number.isInteger(numericSaleId) && numericSaleId > 0
      ? extractLatestSalesNoteSafely_(cfg, uid, numericSaleId)
      : { date: "", state: "", authorName: "" };
  const properties = PropertiesService.getScriptProperties();
  const importedIds = getSalesImportedIds_();
  const existingOrderKeys = getExistingSheetOrderKeys_(getTargetSheet_());
  const orderKey = normalizeOrderNumberKey_(order.name);
  const lastSync = properties.getProperty(SALES_CFG.LAST_SYNC_PROPERTY);
  const fromDate = lastSync
    ? shiftUtcString_(lastSync, -SALES_CFG.SYNC_OVERLAP_MINUTES)
    : "";
  const matchedResponsible = resolveSalesResponsible_(order, noteInfo);
  const checks = [];

  checks.push(`Orden encontrada: ${order.name} (id=${order.id})`);
  checks.push(`Estado Odoo: ${cleanString_(order.state) || "(vacío)"}`);
  checks.push(
    `Fecha creación: ${cleanString_(order.create_date) || "(vacía)"}`
  );
  checks.push(
    `Última modificación: ${cleanString_(order.write_date) || "(vacía)"}`
  );
  checks.push(
    `Cliente: ${getMany2oneName_(order.partner_id) || "(vacío)"}`
  );
  checks.push(
    `Responsable detectado: ${matchedResponsible || "no reconocido"}`
  );
  checks.push(
    `Autor nota con fecha: ${cleanString_(noteInfo.authorName) || "no reconocido"}`
  );
  checks.push(`Fecha detectada en nota: ${noteInfo.date || "no detectada"}`);
  checks.push(
    `Estado detectado en nota: ` +
      `${
        noteInfo.state ||
        `no detectado; se usará ${SALES_CFG.DEFAULT_STATE_WHEN_NOTE_HAS_DATE}`
      }`
  );
  checks.push(
    noteInfo.date
      ? "La nota cumple el requisito de importación."
      : "La nota no tiene una fecha reconocible."
  );
  checks.push(`Última sync ventas: ${lastSync || "no inicializada"}`);

  if (fromDate) {
    checks.push(`Ventana actual desde: ${fromDate}`);
  }

  checks.push(
    importedIds.has(String(order.id))
      ? "Ya figura en ODOO_SALES_IMPORTED_IDS."
      : "No figura como importada."
  );
  checks.push(
    orderKey && hasOrderKeyInSet_(existingOrderKeys, orderKey)
      ? `Ya existe una orden con clave ${orderKey} en la planilla.`
      : "No aparece duplicada en la planilla."
  );
  checks.push(
    cleanString_(order.state).toLowerCase() === "cancel"
      ? "La orden está cancelada."
      : "La orden no está cancelada."
  );

  if (!lines.length) {
    checks.push("No se detectaron líneas de producto válidas.");
  } else {
    checks.push(`Se detectaron ${lines.length} línea(s) de producto.`);
    for (const line of lines) {
      checks.push(
        `- ${line.code} | ${line.description} | cant=${line.quantity}`
      );
    }
  }

  if (
    lastSync &&
    cleanString_(order.write_date) &&
    cleanString_(order.write_date) < fromDate
  ) {
    checks.push(
      "La orden quedó fuera de la ventana por fecha de modificación."
    );
  }

  return "Diagnóstico de venta\n\n" + checks.join("\n");
}

function findSaleOrderForDiagnosis_(cfg, uid, lookupValue) {
  const exact = searchSaleOrderByCandidates_(cfg, uid, lookupValue);
  if (exact) return exact;

  const records = executeKw_(
    cfg,
    uid,
    ODOO_MODELS.sales,
    "search_read",
    [[['name', 'ilike', lookupValue]]],
    {
      fields: getSalesOrderFields_(),
      limit: 1,
      order: "id desc",
    }
  );

  return records && records.length ? records[0] : null;
}

function searchSaleOrderByCandidates_(cfg, uid, lookupValue) {
  const candidates = buildCandidatesForModel(
    lookupValue,
    ODOO_MODELS.sales
  );

  for (const candidate of candidates) {
    const records = executeKw_(
      cfg,
      uid,
      ODOO_MODELS.sales,
      "search_read",
      [[['name', '=', candidate]]],
      {
        fields: getSalesOrderFields_(),
        limit: 1,
      }
    );

    if (records && records.length) {
      return records[0];
    }
  }

  return null;
}

/**
 * ============================================================================
 * PRODUCTOS Y LÍNEAS
 * ============================================================================
 */

function fetchSaleOrderProductLines_(cfg, uid, orderId) {
  const lines =
    executeKw_(
      cfg,
      uid,
      "sale.order.line",
      "search_read",
      [[
        ["order_id", "=", orderId],
        ["display_type", "=", false],
        ["product_id", "!=", false],
        ["customer_lead", ">", 0],
        ["product_uom_qty", ">", 0],
      ]],
      {
        fields: [
          "id",
          "name",
          "product_id",
          "product_uom_qty",
          "customer_lead",
          "display_type",
        ],
        order: "id asc",
      }
    ) || [];
  const productCodeMap = fetchProductCodesByLines_(cfg, uid, lines);
  const productLines = [];

  for (const line of lines) {
    if (line.display_type) continue;

    const productId = getMany2oneId_(line.product_id);
    if (!productId) continue;

    if (!isSaleOrderLineForProduction_(line)) continue;

    const quantity = normalizeQuantity_(line.product_uom_qty);
    if (quantity === null || quantity <= 0) continue;

    productLines.push({
      code:
        extractProductCode_(line, productCodeMap) ||
        `LINE-${cleanString_(line.id)}`,
      description: extractProductDescription_(line.name),
      quantity,
      lineId: cleanString_(line.id),
    });
  }

  return productLines;
}

function chunkValues_(values, chunkSize) {
  const chunks = [];
  const safeChunkSize = Math.max(1, Number(chunkSize) || 1);

  for (let index = 0; index < values.length; index += safeChunkSize) {
    chunks.push(values.slice(index, index + safeChunkSize));
  }

  return chunks;
}

function fetchSaleOrderProductLinesMap_(cfg, uid, orderIds) {
  const normalizedOrderIds = Array.from(
    new Set(
      (orderIds || [])
        .map((orderId) => Number(orderId))
        .filter((orderId) => Number.isInteger(orderId) && orderId > 0)
    )
  );
  const linesByOrderId = new Map();

  for (const orderId of normalizedOrderIds) {
    linesByOrderId.set(String(orderId), []);
  }

  if (!normalizedOrderIds.length) {
    return linesByOrderId;
  }

  const allLines = [];

  for (const orderIdsChunk of chunkValues_(normalizedOrderIds, 80)) {
    const chunkLines =
      executeKw_(
        cfg,
        uid,
        "sale.order.line",
        "search_read",
        [[
          ["order_id", "in", orderIdsChunk],
          ["display_type", "=", false],
          ["product_id", "!=", false],
          ["customer_lead", ">", 0],
          ["product_uom_qty", ">", 0],
        ]],
        {
          fields: [
            "id",
            "order_id",
            "name",
            "product_id",
            "product_uom_qty",
            "customer_lead",
            "display_type",
          ],
          order: "order_id asc, id asc",
        }
      ) || [];

    allLines.push(...chunkLines);
  }

  const productCodeMap = fetchProductCodesByLines_(cfg, uid, allLines);

  for (const line of allLines) {
    if (line.display_type) continue;

    const orderId = getMany2oneId_(line.order_id);
    const productId = getMany2oneId_(line.product_id);
    if (!orderId || !productId) continue;

    if (!isSaleOrderLineForProduction_(line)) continue;

    const quantity = normalizeQuantity_(line.product_uom_qty);
    if (quantity === null || quantity <= 0) continue;

    const orderIdKey = String(orderId);
    if (!linesByOrderId.has(orderIdKey)) {
      linesByOrderId.set(orderIdKey, []);
    }

    linesByOrderId.get(orderIdKey).push({
      code:
        extractProductCode_(line, productCodeMap) ||
        `LINE-${cleanString_(line.id)}`,
      description: extractProductDescription_(line.name),
      quantity,
      lineId: cleanString_(line.id),
    });
  }

  logDebug_(
    `Precarga de lineas de venta: ${normalizedOrderIds.length} orden(es), ${allLines.length} linea(s) leidas.`
  );

  return linesByOrderId;
}

function parseSalesNoteInfoFromMessage_(message) {
  const rawBody =
    message && Object.prototype.hasOwnProperty.call(message, "body")
      ? message.body
      : "";
  const rawSubject =
    message && Object.prototype.hasOwnProperty.call(message, "subject")
      ? message.subject
      : "";
  const authorName = getMany2oneName_(
    message && Object.prototype.hasOwnProperty.call(message, "author_id")
      ? message.author_id
      : ""
  );
  const bodyText =
    typeof normalizeMessageBody_ === "function"
      ? normalizeMessageBody_(rawBody)
      : cleanString_(rawBody);

  if (
    !bodyText ||
    isAutomatedSalesNotificationMessage_(bodyText, rawSubject) ||
    typeof parseSalesPlanningNote_ !== "function"
  ) {
    return {
      date: "",
      state: "",
      sourceMessageDate: "",
      sourceMessageId: "",
      authorName: "",
      };
  }

  const parsed = parseSalesPlanningNote_(rawBody);
  const fallbackParsed = buildFallbackSalesPlanningNote_(bodyText, rawSubject);
  const resolvedDate =
    cleanString_(parsed && parsed.date) || cleanString_(fallbackParsed.date);
  const resolvedState =
    cleanString_(parsed && parsed.state) || cleanString_(fallbackParsed.state);

  return resolvedDate || resolvedState
    ? {
        date: resolvedDate,
        state: resolvedState,
        sourceMessageDate: cleanString_(message.date),
        sourceMessageId: cleanString_(message.id),
        authorName: cleanString_(authorName),
      }
    : {
        date: "",
        state: "",
        sourceMessageDate: "",
        sourceMessageId: "",
        authorName: "",
      };
}

function buildFallbackSalesPlanningNote_(bodyText, subjectText) {
  const combinedText = [
    cleanString_(bodyText),
    cleanString_(subjectText),
  ]
    .filter(Boolean)
    .join("\n");

  return {
    date: extractFallbackSalesPlanningDate_(combinedText),
    state: extractFallbackSalesPlanningState_(combinedText),
  };
}

function extractFallbackSalesPlanningDate_(textValue) {
  const text = cleanString_(textValue);
  if (!text) return "";

  const patterns = [
    /(?:^|\b)(\d{1,2}\/\d{1,2}\/\d{4})(?:\b|$)/i,
    /(?:^|\b)(\d{4}-\d{2}-\d{2})(?:\b|$)/i,
    /(?:^|\b)(\d{1,2}\s*[-\/]\s*[A-Za-z.]{3,})(?:\b|$)/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match || !match[1]) continue;

    const parsedDate = parseSalesSheetDateValue_(match[1]);
    if (!parsedDate) continue;

    return Utilities.formatDate(
      parsedDate,
      Session.getScriptTimeZone(),
      "dd/MM/yyyy"
    );
  }

  return "";
}

function extractFallbackSalesPlanningState_(textValue) {
  const normalizedText = cleanString_(textValue)
    .toLowerCase()
    .replace(/\s+/g, " ");

  if (!normalizedText) return "";

  const states = [
    "cotizar",
    "muestra",
    "empezar",
    "aprobar",
    "pausado",
    "archivar",
    "procesando",
    "finalizado",
  ];

  for (const state of states) {
    const pattern = new RegExp(`(?:^|\\b)${state}(?:\\b|$)`, "i");
    if (pattern.test(normalizedText)) {
      return state.charAt(0).toUpperCase() + state.slice(1);
    }
  }

  return "";
}

function isAutomatedSalesNotificationMessage_(bodyText, subjectText) {
  const normalizedBody = cleanString_(bodyText).toLowerCase();
  const normalizedSubject = cleanString_(subjectText).toLowerCase();
  const combinedText = `${normalizedSubject}\n${normalizedBody}`;
  const looksLikeSalesStateTrackingMessage =
    combinedText.indexOf("(estado)") !== -1 &&
    (
      combinedText.indexOf("cotizacion") !== -1 ||
      combinedText.indexOf("cotización") !== -1 ||
      combinedText.indexOf("quotation") !== -1 ||
      combinedText.indexOf("sale order") !== -1 ||
      combinedText.indexOf("sales order") !== -1 ||
      combinedText.indexOf("pedido de venta") !== -1 ||
      combinedText.indexOf("orden de venta") !== -1 ||
      combinedText.indexOf("presupuesto") !== -1 ||
      combinedText.indexOf("presupuesto enviado") !== -1 ||
      combinedText.indexOf("presupuesto confirmado") !== -1 ||
      combinedText.indexOf("cotizacion enviada") !== -1 ||
      combinedText.indexOf("cotización enviada") !== -1
    );
  const looksLikeActivityNotification =
    combinedText.indexOf("actividad") !== -1 ||
    combinedText.indexOf("activity") !== -1 ||
    combinedText.indexOf("to do") !== -1 ||
    combinedText.indexOf("recordatorio") !== -1 ||
    combinedText.indexOf("fecha limite") !== -1 ||
    combinedText.indexOf("fecha límite") !== -1 ||
    combinedText.indexOf("due date") !== -1 ||
    combinedText.indexOf("deadline") !== -1 ||
    combinedText.indexOf("assigned to") !== -1 ||
    combinedText.indexOf("asignado a") !== -1;
  const looksLikeQuoteConfirmationMessage =
    combinedText.indexOf("cotizacion confirmada") !== -1 ||
    combinedText.indexOf("cotización confirmada") !== -1 ||
    combinedText.indexOf("presupuesto confirmado") !== -1 ||
    combinedText.indexOf("quotation confirmed") !== -1 ||
    combinedText.indexOf("quotation sent") !== -1 ||
    combinedText.indexOf("sales order") !== -1 ||
    combinedText.indexOf("sale order") !== -1 ||
    combinedText.indexOf("pedido de venta") !== -1 ||
    combinedText.indexOf("orden de venta") !== -1;

  if (!combinedText.trim()) return false;

  return (
    looksLikeSalesStateTrackingMessage ||
    looksLikeActivityNotification ||
    looksLikeQuoteConfirmationMessage ||
    combinedText.indexOf("correo electronico hecho") !== -1 ||
    combinedText.indexOf("correo electrónico hecho") !== -1 ||
    combinedText.indexOf("nota original:") !== -1 ||
    combinedText.indexOf("desde planilla") !== -1 ||
    combinedText.indexOf("tipo de actividad") !== -1 ||
    combinedText.indexOf("asignada a") !== -1 ||
    combinedText.indexOf("vence el") !== -1 ||
    combinedText.indexOf("actividades planeadas") !== -1 ||
    (
      (
        combinedText.indexOf("trabajo finalizado") !== -1 ||
        combinedText.indexOf("trabajo pausado") !== -1 ||
        combinedText.indexOf("trabajo por aprobar") !== -1
      ) &&
      (
        combinedText.indexOf("correo electrónico") !== -1 ||
        combinedText.indexOf("correo electronico") !== -1 ||
        combinedText.indexOf("tipo de actividad") !== -1
      )
    )
  );
}

function fetchLatestSalesNotesMap_(cfg, uid, orderIds) {
  const normalizedOrderIds = Array.from(
    new Set(
      (orderIds || [])
        .map((orderId) => Number(orderId))
        .filter((orderId) => Number.isInteger(orderId) && orderId > 0)
    )
  );
  const notesByOrderId = new Map();

  if (!normalizedOrderIds.length) {
    return notesByOrderId;
  }

  if (typeof parseSalesPlanningNote_ !== "function") {
    logDebug_(
      "Precarga de notas de venta omitida: parseSalesPlanningNote_ no disponible."
    );
    return notesByOrderId;
  }

  let fetchedMessages = 0;

  for (const orderIdsChunk of chunkValues_(normalizedOrderIds, 80)) {
    let offset = 0;
    const pageSize = 200;

    while (notesByOrderId.size < normalizedOrderIds.length) {
      const messages =
        executeKw_(
          cfg,
          uid,
          ODOO_MODELS.chatter,
          "search_read",
          [[
            ["model", "=", ODOO_MODELS.sales],
            ["res_id", "in", orderIdsChunk],
          ]],
          {
            fields: ["id", "res_id", "date", "subject", "body", "author_id"],
            order: "date desc, id desc",
            limit: pageSize,
            offset,
          }
        ) || [];

      if (!messages.length) break;

      fetchedMessages += messages.length;

      for (const message of messages) {
        const orderId = Number(message.res_id);
        if (!Number.isInteger(orderId) || orderId <= 0) continue;

        const orderIdKey = String(orderId);
        if (notesByOrderId.has(orderIdKey)) continue;

        const parsed = parseSalesNoteInfoFromMessage_(message);
        if (!parsed.date) continue;

        notesByOrderId.set(orderIdKey, {
          date: parsed.date,
          state: parsed.state,
          sourceMessageDate: cleanString_(message.date),
          sourceMessageId: cleanString_(message.id),
          authorName: cleanString_(parsed.authorName),
        });
      }

      if (messages.length < pageSize) break;
      if (orderIdsChunk.every((orderId) => notesByOrderId.has(String(orderId)))) {
        break;
      }

      offset += messages.length;
    }
  }

  logDebug_(
    `Precarga de notas de venta: ${notesByOrderId.size}/${normalizedOrderIds.length} orden(es) resueltas con ${fetchedMessages} mensaje(s).`
  );

  return notesByOrderId;
}

function extractLatestSalesNoteSafely_(cfg, uid, saleOrderId) {
  const numericSaleOrderId = Number(saleOrderId);
  if (!Number.isInteger(numericSaleOrderId) || numericSaleOrderId <= 0) {
    return {
      date: "",
      state: "",
      sourceMessageDate: "",
      sourceMessageId: "",
      authorName: "",
    };
  }

  if (typeof parseSalesPlanningNote_ !== "function") {
    logDebug_(
      `Lectura segura de nota de venta omitida para ${numericSaleOrderId}: parseSalesPlanningNote_ no disponible.`
    );
    return {
      date: "",
      state: "",
      sourceMessageDate: "",
      sourceMessageId: "",
      authorName: "",
    };
  }

  let offset = 0;
  const pageSize = 200;

  while (true) {
    const messages =
      executeKw_(
        cfg,
        uid,
        ODOO_MODELS.chatter,
        "search_read",
        [[
          ["model", "=", ODOO_MODELS.sales],
          ["res_id", "=", numericSaleOrderId],
        ]],
        {
          fields: ["id", "res_id", "date", "subject", "body", "author_id"],
          order: "date desc, id desc",
          limit: pageSize,
          offset,
        }
      ) || [];

    if (!messages.length) {
      return {
        date: "",
        state: "",
        sourceMessageDate: "",
        sourceMessageId: "",
        authorName: "",
      };
    }

    for (const message of messages) {
      const parsed = parseSalesNoteInfoFromMessage_(message);
      if (parsed.date) {
        return parsed;
      }
    }

    if (messages.length < pageSize) {
      return {
        date: "",
        state: "",
        sourceMessageDate: "",
        sourceMessageId: "",
        authorName: "",
      };
    }

    offset += messages.length;
  }
}

function isSaleOrderLineForProduction_(line) {
  const leadDays = normalizeQuantity_(line.customer_lead);
  return leadDays !== null && leadDays > 0;
}

function fetchProductCodesByLines_(cfg, uid, lines) {
  const productIds = [];
  const seen = new Set();

  for (const line of lines) {
    const productId = getMany2oneId_(line.product_id);
    if (!productId || seen.has(productId)) continue;

    seen.add(productId);
    productIds.push(productId);
  }

  if (!productIds.length) return new Map();

  const products =
    executeKw_(
      cfg,
      uid,
      "product.product",
      "search_read",
      [[['id', 'in', productIds]]],
      {
        fields: ["id", "default_code"],
        limit: productIds.length,
      }
    ) || [];
  const codeMap = new Map();

  for (const product of products) {
    codeMap.set(String(product.id), cleanString_(product.default_code));
  }

  return codeMap;
}

function extractProductCode_(line, productCodeMap) {
  const productId = getMany2oneId_(line.product_id);
  const defaultCode =
    productCodeMap && productId
      ? cleanString_(productCodeMap.get(String(productId)))
      : "";

  if (defaultCode) return defaultCode;

  return (
    extractBracketedReference_(getMany2oneName_(line.product_id)) ||
    extractBracketedReference_(line.name)
  );
}

function extractBracketedReference_(value) {
  const text = cleanString_(value);
  const match = text.match(/^\[([^\]]+)\]/);
  return match && match[1] ? cleanString_(match[1]) : "";
}

function extractProductDescription_(value) {
  const text = cleanString_(value);
  if (!text) return "";

  const stripped = text.replace(/^\[[^\]]+\]\s*/, "").trim();
  return stripped || text;
}

function getSalesStateRank_(stateValue) {
  const state = cleanString_(stateValue);
  const ranks = {
    Cotizar: 0,
    Muestra: 0,
    Aprobar: 0,
    Pausado: 0,
    Archivar: 0,
    Empezar: 1,
    Procesando: 2,
    Finalizado: 3,
  };

  return Object.prototype.hasOwnProperty.call(ranks, state)
    ? ranks[state]
    : null;
}

function shouldAdvanceSalesState_(existingStateValue, candidateStateValue) {
  const candidateRank = getSalesStateRank_(candidateStateValue);
  if (candidateRank === null) return false;

  const existingState = cleanString_(existingStateValue);
  if (!existingState) return true;

  const existingRank = getSalesStateRank_(existingState);
  if (existingRank === null) return false;

  return candidateRank > existingRank;
}

function shouldAllowSalesPeerStateChange_(
  existingStateValue,
  candidateStateValue
) {
  const existingState = cleanString_(existingStateValue);
  const candidateState = cleanString_(candidateStateValue);

  if (candidateState !== "Archivar") {
    return false;
  }

  return existingState === "Pausado" || existingState === "Aprobar";
}

function shouldProtectSalesStateFromImplicitFallback_(
  existingStateValue
) {
  const existingState = cleanString_(existingStateValue);

  return (
    existingState === "Pausado" ||
    existingState === "Archivar" ||
    existingState === "Finalizado"
  );
}

function isSalesReopenedState_(stateValue) {
  const state = cleanString_(stateValue);
  return state === "Cotizar" || state === "Muestra";
}

function isSalesSellerManagedState_(stateValue) {
  const state = cleanString_(stateValue);
  return (
    state === "Cotizar" ||
    state === "Muestra" ||
    state === "Empezar"
  );
}

function canSalesSellerApplyStateFromSync_(
  existingStateValue,
  candidateStateValue,
  allowFromApproval
) {
  const existingState = cleanString_(existingStateValue);
  const candidateState = cleanString_(candidateStateValue);

  if (!isSalesSellerManagedState_(candidateState)) {
    return false;
  }

  if (!existingState) {
    return true;
  }

  if (existingState === "Aprobar") {
    return Boolean(allowFromApproval);
  }

  return isSalesSellerManagedState_(existingState);
}

/**
 * ============================================================================
 * ESCRITURA
 * ============================================================================
 */

function writeSalesOrderLineRow_(sheet, row, data) {
  const detailValues = sheet.getRange(row, 4, 1, 7).getDisplayValues()[0];
  const originalDeliveryCellValue = sheet.getRange(row, 8).getValue();
  const existingResponsible = cleanString_(
    sheet.getRange(row, 1).getDisplayValue()
  );
  const originalResponsibleValue = existingResponsible;
  const existingCustomerName = cleanString_(detailValues[0]);
  const originalCustomerValue = cleanString_(detailValues[0]);
  const originalProductValue = cleanString_(detailValues[1]);
  const originalQuantityValue = cleanString_(detailValues[2]);
  const originalIngressValue = cleanString_(detailValues[3]);
  const originalDeliveryValue = cleanString_(detailValues[4]);
  const originalDeliveryCanonicalValue = formatSalesCanonicalDate_(
    originalDeliveryCellValue || detailValues[4]
  );
  const originalStateValue = cleanString_(detailValues[5]);
  const parsedOrderDateValue = parseSalesSheetDateValue_(
    data.orderDateFormatted
  );
  const parsedNoteDateValue = parseSalesSheetDateValue_(
    data.noteDateFormatted
  );
  let resultingResponsibleValue = existingResponsible;

  if (
    data.matchedResponsible &&
    normalizeSalesComparableText_(data.matchedResponsible) !==
      normalizeSalesComparableText_(existingResponsible)
  ) {
    sheet.getRange(row, 1).setValue(data.matchedResponsible);
    resultingResponsibleValue = cleanString_(data.matchedResponsible);
  }

  sheet.getRange(row, CFG.ORDER_COL).setValue(data.orderName);
  sheet.getRange(row, CFG.LINK_COL).setRichTextValue(
    buildLinkedRichText_(
      data.orderName,
      buildRecordUrl_(data.cfg, data.saleId, ODOO_MODELS.sales)
    )
  );
  detailValues[0] = cleanString_(data.customerName) || existingCustomerName;
  detailValues[1] = data.description || "";
  detailValues[2] = data.quantity;
  // La columna G tiene validación de fecha. Nunca escribir un texto como
  // "3-Aug": aunque se vea como fecha, Sheets lo considera inválido.
  detailValues[3] = parsedOrderDateValue || data.orderDateFormatted || "";

  const existingStateValue = cleanString_(detailValues[5]);
  const explicitNoteState = mapAnyStateToSheetValue_(data.noteState);
  const defaultState = mapAnyStateToSheetValue_(data.defaultState);
  const odooState = mapAnyStateToSheetValue_(data.currentState);
  const syncMetadata = getSalesSyncMetadataForRow_(sheet, row);
  const approvalStateAnchor =
    existingStateValue === "Aprobar"
      ? syncMetadata.approvalAnchor
      : "";
  const acceptedMessageId = syncMetadata.acceptedMessageId;
  const acceptedMessageDate = syncMetadata.acceptedMessageDate;
  const acceptedState = syncMetadata.acceptedState;
  const canonicalDeliveryDate = syncMetadata.canonicalDeliveryDate;
  const parsedCanonicalDeliveryDate = parseSalesSheetDateValue_(
    canonicalDeliveryDate
  );
  const noteIsAfterApprovalStateAnchor =
    approvalStateAnchor &&
    isUtcStringAfter_(
      data.noteSourceMessageDate,
      approvalStateAnchor
    );
  const manualStateAnchor = getSalesManualStateAnchor_({
    saleId: data.saleId,
    saleLineId: data.saleLineId,
    lineCode: data.lineCode,
  });
  const noteIsAfterManualStateAnchor =
    manualStateAnchor &&
    isUtcStringAfter_(
      data.noteSourceMessageDate,
      manualStateAnchor
    );
  const sellerCanRetakeFromApproval =
    existingStateValue === "Aprobar" &&
    approvalStateAnchor &&
    noteIsAfterApprovalStateAnchor;
  const approvalStateAnchorBlocksSync =
    approvalStateAnchor && !noteIsAfterApprovalStateAnchor;
  const acceptedMessageBlocksSync =
    cleanString_(data.noteSourceMessageDate) &&
    !isSalesMessageNewerThanAccepted_(
      data.noteSourceMessageDate,
      data.noteSourceMessageId,
      acceptedMessageDate,
      acceptedMessageId
    );
  const canApplyNoteState =
    (!manualStateAnchor || noteIsAfterManualStateAnchor) &&
    !approvalStateAnchorBlocksSync &&
    !acceptedMessageBlocksSync;
  const canApplyNoteDate =
    Boolean(parsedNoteDateValue) && !acceptedMessageBlocksSync;
  const shouldProtectImplicitFallback =
    data.isExistingRow &&
    (
      acceptedMessageBlocksSync ||
      approvalStateAnchorBlocksSync ||
      (
        !noteIsAfterManualStateAnchor &&
        !explicitNoteState &&
        shouldProtectSalesStateFromImplicitFallback_(
          existingStateValue
        )
      )
    );
  const canApplyExplicitSellerState =
    explicitNoteState &&
    canApplyNoteState &&
    canSalesSellerApplyStateFromSync_(
      existingStateValue,
      explicitNoteState,
      sellerCanRetakeFromApproval
    );
  const canApplyDefaultSellerState =
    defaultState &&
    canApplyNoteState &&
    data.noteDateFormatted &&
    !shouldProtectImplicitFallback &&
    canSalesSellerApplyStateFromSync_(
      existingStateValue,
      defaultState,
      sellerCanRetakeFromApproval
    );
  const canApplyOdooSellerState =
    !manualStateAnchor &&
    !shouldProtectImplicitFallback &&
    canSalesSellerApplyStateFromSync_(
      existingStateValue,
      odooState,
      false
    );
  let shouldMarkRowForMovement = false;

  if (sellerCanRetakeFromApproval) {
    clearSalesManualStateAnchor_({
      saleId: data.saleId,
      saleLineId: data.saleLineId,
      lineCode: data.lineCode,
    });
  }

  if (
    sellerCanRetakeFromApproval &&
    isSalesReopenedState_(explicitNoteState)
  ) {
    const reopenedAtFormatted = formatSalesChatterMessageDateForSheet_(
      data.noteSourceMessageDate
    );

    if (reopenedAtFormatted) {
      detailValues[3] = reopenedAtFormatted;
    }

    detailValues[6] = "";
    shouldMarkRowForMovement = true;
  }

  if (
    canApplyNoteDate
  ) {
    detailValues[4] = parsedNoteDateValue;
  } else if (parsedCanonicalDeliveryDate) {
    detailValues[4] = parsedCanonicalDeliveryDate;
  }

  if (
    canApplyExplicitSellerState
  ) {
    detailValues[5] = explicitNoteState;
    if (
      sellerCanRetakeFromApproval &&
      explicitNoteState !== existingStateValue
    ) {
      shouldMarkRowForMovement = true;
    }
  } else if (
    canApplyDefaultSellerState
  ) {
    detailValues[5] = defaultState;
    if (
      sellerCanRetakeFromApproval &&
      defaultState !== existingStateValue
    ) {
      shouldMarkRowForMovement = true;
    }
  } else if (
    canApplyOdooSellerState
  ) {
    detailValues[5] = odooState;
  } else if (!existingStateValue) {
    const initialState =
      canSalesSellerApplyStateFromSync_("", explicitNoteState, false)
        ? explicitNoteState
        : canSalesSellerApplyStateFromSync_("", defaultState, false)
          ? defaultState
          : canSalesSellerApplyStateFromSync_("", odooState, false)
            ? odooState
            : "";
    if (initialState) detailValues[5] = initialState;
  }

  sheet.getRange(row, 4, 1, 7).setValues([detailValues]);

  if (parsedOrderDateValue) {
    sheet.getRange(row, 7).setNumberFormat("d-mmm");
  }

  if (parsedNoteDateValue || parsedCanonicalDeliveryDate) {
    sheet.getRange(row, 8).setNumberFormat("d-mmm");
  }

  if (shouldMarkRowForMovement) {
    markRowAsNew_(sheet, row);
  }

  sheet.getRange(row, CFG.LINK_COL).setNote(
    `OK: Venta (${data.orderName}) | Producto: ${data.lineCode}`
  );

  setSalesRowHiddenMetadata_(
    sheet,
    row,
    data.saleId,
    data.saleLineId
  );
  setSalesSyncMetadataForRow_(sheet, row, {
    approvalAnchor: syncMetadata.approvalAnchor,
    acceptedMessageId:
      (canApplyNoteDate || canApplyNoteState) &&
      cleanString_(data.noteSourceMessageDate) &&
      (parsedNoteDateValue || explicitNoteState || defaultState)
        ? cleanString_(data.noteSourceMessageId)
        : acceptedMessageId,
    acceptedMessageDate:
      (canApplyNoteDate || canApplyNoteState) &&
      cleanString_(data.noteSourceMessageDate) &&
      (parsedNoteDateValue || explicitNoteState || defaultState)
        ? cleanString_(data.noteSourceMessageDate)
        : acceptedMessageDate,
    acceptedState:
      canApplyNoteState &&
      cleanString_(data.noteSourceMessageDate) &&
      (parsedNoteDateValue || explicitNoteState || defaultState)
        ? cleanString_(detailValues[5]) || acceptedState
        : acceptedState,
    canonicalDeliveryDate:
      canApplyNoteDate && parsedNoteDateValue
        ? formatSalesCanonicalDate_(parsedNoteDateValue)
        : canonicalDeliveryDate,
  });

  ensureDeliveryDaysFormula_(sheet, row, !data.isExistingRow);

  const resultingCustomerValue = cleanString_(detailValues[0]);
  const resultingProductValue = cleanString_(detailValues[1]);
  const resultingQuantityValue = cleanString_(detailValues[2]);
  const resultingIngressValue = cleanString_(detailValues[3]);
  const resultingDeliveryValue = formatSalesDateForLog_(detailValues[4]);
  const resultingDeliveryCanonicalValue = formatSalesCanonicalDate_(
    detailValues[4]
  );
  const resultingStateValue = cleanString_(detailValues[5]);
  const hasVisibleChanges =
    normalizeSalesComparableText_(resultingResponsibleValue) !==
      normalizeSalesComparableText_(originalResponsibleValue) ||
    normalizeSalesComparableText_(resultingCustomerValue) !==
      normalizeSalesComparableText_(originalCustomerValue) ||
    normalizeSalesComparableText_(resultingProductValue) !==
      normalizeSalesComparableText_(originalProductValue) ||
    normalizeSalesComparableQuantity_(resultingQuantityValue) !==
      normalizeSalesComparableQuantity_(originalQuantityValue) ||
    normalizeSalesComparableDateDisplay_(resultingIngressValue) !==
      normalizeSalesComparableDateDisplay_(originalIngressValue) ||
    resultingDeliveryCanonicalValue !== originalDeliveryCanonicalValue ||
    normalizeSalesComparableText_(resultingStateValue) !==
      normalizeSalesComparableText_(originalStateValue);

  return {
    previousResponsibleValue: originalResponsibleValue,
    resultingResponsibleValue,
    previousCustomerValue: originalCustomerValue,
    resultingCustomerValue,
    previousProductValue: originalProductValue,
    resultingProductValue,
    previousQuantityValue: originalQuantityValue,
    resultingQuantityValue,
    previousIngressValue: originalIngressValue,
    resultingIngressValue,
    previousDeliveryValue: formatSalesDateForLog_(
      originalDeliveryCellValue || originalDeliveryValue
    ),
    resultingDeliveryValue,
    previousStateValue: originalStateValue,
    resultingStateValue,
    hasVisibleChanges,
    requiresResort:
      shouldMarkRowForMovement ||
      normalizeSalesComparableText_(resultingCustomerValue) !==
        normalizeSalesComparableText_(originalCustomerValue) ||
      normalizeSalesComparableText_(resultingProductValue) !==
        normalizeSalesComparableText_(originalProductValue) ||
      normalizeSalesComparableText_(resultingStateValue) !==
        normalizeSalesComparableText_(originalStateValue),
  };
}

function buildSalesWriteChangeSummary_(row, writeResult) {
  if (!writeResult) {
    return `Fila ${row}.`;
  }

  const changes = [];

  if (
    cleanString_(writeResult.previousResponsibleValue) !==
    cleanString_(writeResult.resultingResponsibleValue)
  ) {
    changes.push(
      `pedido por: ${cleanString_(writeResult.previousResponsibleValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingResponsibleValue) || "(vacio)"}`
    );
  }

  if (
    cleanString_(writeResult.previousCustomerValue) !==
    cleanString_(writeResult.resultingCustomerValue)
  ) {
    changes.push(
      `cliente: ${cleanString_(writeResult.previousCustomerValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingCustomerValue) || "(vacio)"}`
    );
  }

  if (
    cleanString_(writeResult.previousProductValue) !==
    cleanString_(writeResult.resultingProductValue)
  ) {
    changes.push(
      `producto: ${cleanString_(writeResult.previousProductValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingProductValue) || "(vacio)"}`
    );
  }

  if (
    normalizeSalesComparableQuantity_(writeResult.previousQuantityValue) !==
    normalizeSalesComparableQuantity_(writeResult.resultingQuantityValue)
  ) {
    changes.push(
      `cantidad: ${cleanString_(writeResult.previousQuantityValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingQuantityValue) || "(vacio)"}`
    );
  }

  if (
    normalizeSalesComparableDateDisplay_(writeResult.previousIngressValue) !==
    normalizeSalesComparableDateDisplay_(writeResult.resultingIngressValue)
  ) {
    changes.push(
      `ingreso: ${cleanString_(writeResult.previousIngressValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingIngressValue) || "(vacio)"}`
    );
  }

  if (
    cleanString_(writeResult.previousDeliveryValue) !==
    cleanString_(writeResult.resultingDeliveryValue)
  ) {
    changes.push(
      `entrega: ${cleanString_(writeResult.previousDeliveryValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingDeliveryValue) || "(vacio)"}`
    );
  }

  if (
    cleanString_(writeResult.previousStateValue) !==
    cleanString_(writeResult.resultingStateValue)
  ) {
    changes.push(
      `estado: ${cleanString_(writeResult.previousStateValue) || "(vacio)"} -> ` +
        `${cleanString_(writeResult.resultingStateValue) || "(vacio)"}`
    );
  }

  if (!changes.length) {
    return `Fila ${row}. Sin cambios visibles.`;
  }

  return `Fila ${row}. ${changes.join(" | ")}.`;
}

function syncSalesFinalizationNotificationForRow_(
  sheet,
  row,
  previousStateValue,
  currentStateValue,
  notifiedKeys
) {
  const previousState = cleanString_(previousStateValue).toLowerCase();
  const currentState = cleanString_(currentStateValue).toLowerCase();
  const context = getSalesFinalizationContextFromRow_(sheet, row);

  if (!isSalesContextRow_(sheet, row, context)) {
    return false;
  }

  const notificationKey = buildSalesFinalizationNotificationKey_(context);
  if (!notificationKey) return false;

  if (currentState !== "finalizado") {
    if (!notifiedKeys.has(notificationKey)) {
      return false;
    }

    notifiedKeys.delete(notificationKey);
    return true;
  }

  if (previousState === "finalizado" || notifiedKeys.has(notificationKey)) {
    return false;
  }

  if (!cleanString_(context.saleOrderId)) {
    logDebug_(
      `Notificacion automatica de venta omitida en fila ${row}: falta sale.order.id.`
    );
    return false;
  }

  postSalesFinalizationInternalNote_(context);
  notifiedKeys.add(notificationKey);
  return true;
}

function syncSalesApprovalNotificationForRow_(
  sheet,
  row,
  previousStateValue,
  currentStateValue,
  notifiedKeys
) {
  const previousState = cleanString_(previousStateValue).toLowerCase();
  const currentState = cleanString_(currentStateValue).toLowerCase();
  const context = getSalesFinalizationContextFromRow_(sheet, row);

  if (!isSalesContextRow_(sheet, row, context)) {
    return false;
  }

  const notificationKey = buildSalesApprovalNotificationKey_(context);
  if (!notificationKey) return false;

  if (currentState !== "aprobar") {
    if (!notifiedKeys.has(notificationKey)) {
      return false;
    }

    notifiedKeys.delete(notificationKey);
    return true;
  }

  if (notifiedKeys.has(notificationKey) || previousState === "aprobar") {
    return false;
  }

  if (!cleanString_(context.saleOrderId)) {
    logDebug_(
      `Notificacion automatica de aprobacion omitida en fila ${row}: falta sale.order.id.`
    );
    return false;
  }

  postSalesApprovalInternalNote_(context);
  notifiedKeys.add(notificationKey);
  return true;
}

function syncSalesPausedNotificationForRow_(
  sheet,
  row,
  previousStateValue,
  currentStateValue,
  notifiedKeys
) {
  const previousState = cleanString_(previousStateValue).toLowerCase();
  const currentState = cleanString_(currentStateValue).toLowerCase();
  const context = getSalesFinalizationContextFromRow_(sheet, row);

  if (!isSalesContextRow_(sheet, row, context)) {
    return false;
  }

  const notificationKey = buildSalesPausedNotificationKey_(context);
  if (!notificationKey) return false;

  if (currentState !== "pausado") {
    if (!notifiedKeys.has(notificationKey)) {
      return false;
    }

    notifiedKeys.delete(notificationKey);
    return true;
  }

  if (notifiedKeys.has(notificationKey) || previousState === "pausado") {
    return false;
  }

  if (!cleanString_(context.saleOrderId)) {
    logDebug_(
      `Notificacion automatica de pausado omitida en fila ${row}: falta sale.order.id.`
    );
    return false;
  }

  postSalesPausedInternalNote_(context);
  notifiedKeys.add(notificationKey);
  return true;
}

function setSalesRowHiddenMetadata_(sheet, row, saleId, saleLineId) {
  const metadataValues = [[
    "",
    cleanString_(saleId),
    cleanString_(saleLineId),
    "VENTA",
  ]];
  sheet
    .getRange(row, getManufacturingIdColumn_(), 1, 4)
    .setValues(metadataValues);
}

function extractSaleOrderIdFromUrl_(urlValue) {
  const url = cleanString_(urlValue);

  if (!url || url.indexOf("model=sale.order") === -1) {
    return "";
  }

  const match = url.match(/(?:#|[?&])id=(\d+)/i);
  return match && match[1] ? cleanString_(match[1]) : "";
}

function getSalesFinalizationContextFromRow_(sheet, row) {
  const metadataValues = sheet
    .getRange(row, getManufacturingIdColumn_(), 1, 4)
    .getDisplayValues()[0];
  const saleOrderId =
    cleanString_(metadataValues[1]) ||
    extractSaleOrderIdFromUrl_(
      getCellLinkUrl_(sheet.getRange(row, CFG.LINK_COL))
    );

  return {
    row,
    saleOrderId,
    saleLineId: cleanString_(metadataValues[2]),
    origin: cleanString_(metadataValues[3]),
    orderName: cleanString_(
      sheet.getRange(row, CFG.ORDER_COL).getDisplayValue()
    ),
    customerName: cleanString_(
      sheet.getRange(row, 4).getDisplayValue()
    ),
    productName: cleanString_(
      sheet.getRange(row, 5).getDisplayValue()
    ),
    lineCode: getSalesLineCodeFromRow_(sheet, row),
    quantity: cleanString_(
      sheet.getRange(row, 6).getDisplayValue()
    ),
  };
}

function buildSalesFinalizationNotificationKey_(context) {
  if (!context) return "";

  if (cleanString_(context.saleLineId)) {
    return `line:${cleanString_(context.saleLineId)}`;
  }

  const saleOrderId = cleanString_(context.saleOrderId);
  const productName = cleanString_(context.productName).toUpperCase();
  if (!saleOrderId || !productName) return "";

  return `sale:${saleOrderId}|product:${productName}`;
}

function buildSalesApprovalNotificationKey_(context) {
  if (!context) return "";

  if (cleanString_(context.saleLineId)) {
    return `approve:line:${cleanString_(context.saleLineId)}`;
  }

  const saleOrderId = cleanString_(context.saleOrderId);
  const productName = cleanString_(context.productName).toUpperCase();
  if (!saleOrderId || !productName) return "";

  return `approve:sale:${saleOrderId}|product:${productName}`;
}

function buildSalesPausedNotificationKey_(context) {
  if (!context) return "";

  if (cleanString_(context.saleLineId)) {
    return `paused:line:${cleanString_(context.saleLineId)}`;
  }

  const saleOrderId = cleanString_(context.saleOrderId);
  const productName = cleanString_(context.productName).toUpperCase();
  if (!saleOrderId || !productName) return "";

  return `paused:sale:${saleOrderId}|product:${productName}`;
}

function getSalesFinalizationNotifiedKeys_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    "ODOO_SALES_FINALIZATION_NOTIFIED_KEYS"
  );
  return parseStoredIdSet_(raw);
}

function saveSalesFinalizationNotifiedKeys_(keySet) {
  PropertiesService.getScriptProperties().setProperty(
    "ODOO_SALES_FINALIZATION_NOTIFIED_KEYS",
    JSON.stringify(Array.from(keySet))
  );
}

function getSalesApprovalNotifiedKeys_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    "ODOO_SALES_APPROVAL_NOTIFIED_KEYS"
  );
  return parseStoredIdSet_(raw);
}

function saveSalesApprovalNotifiedKeys_(keySet) {
  PropertiesService.getScriptProperties().setProperty(
    "ODOO_SALES_APPROVAL_NOTIFIED_KEYS",
    JSON.stringify(Array.from(keySet))
  );
}

function getSalesPausedNotifiedKeys_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    "ODOO_SALES_PAUSED_NOTIFIED_KEYS"
  );
  return parseStoredIdSet_(raw);
}

function saveSalesPausedNotifiedKeys_(keySet) {
  PropertiesService.getScriptProperties().setProperty(
    "ODOO_SALES_PAUSED_NOTIFIED_KEYS",
    JSON.stringify(Array.from(keySet))
  );
}

function postSalesFinalizationInternalNoteLegacy_(context) {
  const saleOrderId = Number(cleanString_(context && context.saleOrderId));
  if (!Number.isInteger(saleOrderId) || saleOrderId <= 0) {
    throw new Error("No se pudo resolver sale.order.id para la notificación.");
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  const uid = odooLogin_(cfg);
const bodyLines = [
  "Trabajo finalizado desde planilla",
  `Orden: ${cleanString_(context.orderName)}`,
  `Producto finalizado: ${cleanString_(context.productName)}`,
];

if (cleanString_(context.quantity)) {
  bodyLines.push(`Cantidad: ${cleanString_(context.quantity)}`);
}

if (cleanString_(context.customerName)) {
  bodyLines.push(`Cliente: ${cleanString_(context.customerName)}`);
}

executeKw_(
  cfg,
  uid,
  ODOO_MODELS.sales,
  "message_post",
  [[saleOrderId]],
  {
    body: bodyLines.join("\n"),
    message_type: "comment",
    subtype_xmlid: "mail.mt_note",
  }
);
}

/**
 * ============================================================================
 * PROPIEDADES DE VENTAS
 * ============================================================================
 */

function getSalesNotificationTarget_(cfg, uid, saleOrderId) {
  const numericSaleOrderId = Number(saleOrderId);
  if (!Number.isInteger(numericSaleOrderId) || numericSaleOrderId <= 0) {
    return {
      userId: 0,
      partnerIds: [],
      displayName: "",
    };
  }

  const orders =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.sales,
      "read",
      [[numericSaleOrderId]],
      {
        fields: ["user_id"],
      }
    ) || [];
  const salesUserId =
    orders.length > 0 ? getMany2oneId_(orders[0].user_id) : 0;

  if (!salesUserId) {
    return {
      userId: 0,
      partnerIds: [],
      displayName: "",
    };
  }

  const users =
    executeKw_(
      cfg,
      uid,
      "res.users",
      "read",
      [[salesUserId]],
      {
        fields: ["partner_id"],
      }
    ) || [];
  const partnerId =
    users.length > 0 ? getMany2oneId_(users[0].partner_id) : 0;
  const displayName =
    orders.length > 0
      ? cleanString_(getMany2oneName_(orders[0].user_id))
      : "";

  return {
    userId: salesUserId,
    partnerIds: partnerId ? [partnerId] : [],
    displayName,
  };
}

function ensureSalesNotificationFollowers_(cfg, uid, saleOrderId, partnerIds) {
  const numericSaleOrderId = Number(saleOrderId);
  if (!Number.isInteger(numericSaleOrderId) || numericSaleOrderId <= 0) {
    return;
  }

  const normalizedPartnerIds = (partnerIds || [])
    .map((partnerId) => Number(partnerId))
    .filter((partnerId) => Number.isInteger(partnerId) && partnerId > 0);

  if (!normalizedPartnerIds.length) return;

  executeKw_(
    cfg,
    uid,
    ODOO_MODELS.sales,
    "message_subscribe",
    [[numericSaleOrderId], normalizedPartnerIds]
  );
}

function escapeSalesNotificationHtml_(value) {
  return cleanString_(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getSalesModelId_(cfg, uid) {
  const models =
    executeKw_(
      cfg,
      uid,
      "ir.model",
      "search_read",
      [[["model", "=", ODOO_MODELS.sales]]],
      {
        fields: ["id"],
        limit: 1,
      }
    ) || [];

  return models.length ? Number(models[0].id) || 0 : 0;
}

function getSalesTodoActivityTypeId_(cfg, uid) {
  let xmlIdResolved = 0;

  try {
    const xmlIds =
      executeKw_(
        cfg,
        uid,
        "ir.model.data",
        "search_read",
        [[
          ["module", "=", "mail"],
          ["name", "=", "mail_activity_data_todo"],
        ]],
        {
          fields: ["res_id"],
          limit: 1,
        }
      ) || [];

    xmlIdResolved =
      xmlIds.length ? Number(xmlIds[0].res_id) || 0 : 0;
  } catch (err) {
    logDebug_(
      "No se pudo leer ir.model.data para mail_activity_data_todo. Se usa fallback por nombre/tipo."
    );
  }

  if (xmlIdResolved) return xmlIdResolved;

  const todoTypes =
    executeKw_(
      cfg,
      uid,
      "mail.activity.type",
      "search_read",
      [[
        ["name", "ilike", "To Do"],
      ]],
      {
        fields: ["id", "name"],
        order: "id asc",
        limit: 5,
      }
    ) || [];

  if (todoTypes.length) {
    return Number(todoTypes[0].id) || 0;
  }

  const fallbackTypes =
    executeKw_(
      cfg,
      uid,
      "mail.activity.type",
      "search_read",
      [[]],
      {
        fields: ["id"],
        order: "id asc",
        limit: 1,
      }
    ) || [];

  return fallbackTypes.length
    ? Number(fallbackTypes[0].id) || 0
    : 0;
}

function buildSalesFinalizationActivityNoteHtml_(context) {
  const noteLines = [];

  if (cleanString_(context.orderName)) {
    noteLines.push(
      `<b>Orden:</b> ${escapeSalesNotificationHtml_(context.orderName)}`
    );
  }

  if (cleanString_(context.lineCode)) {
    noteLines.push(
      `<b>Codigo:</b> ${escapeSalesNotificationHtml_(context.lineCode)}`
    );
  }

  if (cleanString_(context.productName)) {
    noteLines.push(
      `<b>Producto:</b> ${escapeSalesNotificationHtml_(context.productName)}`
    );
  }

  if (cleanString_(context.quantity)) {
    noteLines.push(
      `<b>Cantidad:</b> ${escapeSalesNotificationHtml_(context.quantity)}`
    );
  }

  return noteLines.length
    ? `<p>${noteLines.join("<br/>")}</p>`
    : "<p>Trabajo finalizado.</p>";
}

function buildSalesApprovalActivityNoteHtml_(context) {
  const noteLines = [];

  if (cleanString_(context.orderName)) {
    noteLines.push(
      `<b>Orden:</b> ${escapeSalesNotificationHtml_(context.orderName)}`
    );
  }

  if (cleanString_(context.lineCode)) {
    noteLines.push(
      `<b>Codigo:</b> ${escapeSalesNotificationHtml_(context.lineCode)}`
    );
  }

  if (cleanString_(context.productName)) {
    noteLines.push(
      `<b>Producto:</b> ${escapeSalesNotificationHtml_(context.productName)}`
    );
  }

  if (cleanString_(context.quantity)) {
    noteLines.push(
      `<b>Cantidad:</b> ${escapeSalesNotificationHtml_(context.quantity)}`
    );
  }

  return noteLines.length
    ? `<p>${noteLines.join("<br/>")}</p>`
    : "<p>Trabajo pendiente de aprobacion.</p>";
}

function buildSalesPausedActivityNoteHtml_(context) {
  const noteLines = [];

  if (cleanString_(context.orderName)) {
    noteLines.push(
      `<b>Orden:</b> ${escapeSalesNotificationHtml_(context.orderName)}`
    );
  }

  if (cleanString_(context.lineCode)) {
    noteLines.push(
      `<b>Codigo:</b> ${escapeSalesNotificationHtml_(context.lineCode)}`
    );
  }

  if (cleanString_(context.productName)) {
    noteLines.push(
      `<b>Producto:</b> ${escapeSalesNotificationHtml_(context.productName)}`
    );
  }

  if (cleanString_(context.quantity)) {
    noteLines.push(
      `<b>Cantidad:</b> ${escapeSalesNotificationHtml_(context.quantity)}`
    );
  }

  return noteLines.length
    ? `<p>${noteLines.join("<br/>")}</p>`
    : "<p>Trabajo pausado.</p>";
}

function buildSalesActivityItemLabel_(context) {
  if (!context) return "";

  const lineCode = cleanString_(context.lineCode);
  const productName = cleanString_(context.productName);
  const saleLineId = cleanString_(context.saleLineId);
  const baseLabel =
    lineCode && productName
      ? `${lineCode} - ${productName}`
      : lineCode || productName;

  if (saleLineId && baseLabel) {
    return `${baseLabel} (#${saleLineId})`;
  }

  if (saleLineId) {
    return `Linea #${saleLineId}`;
  }

  return baseLabel;
}

function buildSalesActivitySummary_(baseSummary, context) {
  const normalizedBaseSummary = cleanString_(baseSummary);
  const itemLabel = buildSalesActivityItemLabel_(context);

  return itemLabel
    ? `${normalizedBaseSummary}: ${itemLabel}`
    : normalizedBaseSummary;
}

/**
 * NOTA IMPORTANTE:
 * Este flujo crea/actualiza solo actividades internas de Odoo.
 * No debe enviar correos ni usar plantillas de email.
 */
function scheduleSalesFinalizationActivity_(
  cfg,
  uid,
  saleOrderId,
  salesUserId,
  context
) {
  const numericSaleOrderId = Number(saleOrderId);
  const numericSalesUserId = Number(salesUserId);

  if (
    !Number.isInteger(numericSaleOrderId) ||
    numericSaleOrderId <= 0 ||
    !Number.isInteger(numericSalesUserId) ||
    numericSalesUserId <= 0
  ) {
    return;
  }

  const modelId = getSalesModelId_(cfg, uid);
  const activityTypeId = getSalesTodoActivityTypeId_(cfg, uid);
  if (!modelId || !activityTypeId) {
    throw new Error(
      "No se pudo resolver el modelo o el tipo de actividad de ventas."
    );
  }

  const today = nowUtcString_().slice(0, 10);
  const summary = buildSalesActivitySummary_(
    "Trabajo finalizado",
    context
  );
  const existingActivities =
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "search_read",
      [[
        ["res_model_id", "=", modelId],
        ["res_id", "=", numericSaleOrderId],
        ["user_id", "=", numericSalesUserId],
        ["activity_type_id", "=", activityTypeId],
        ["summary", "=", summary],
      ]],
      {
        fields: ["id"],
        limit: 1,
        order: "id desc",
      }
    ) || [];

  const activityValues = {
    activity_type_id: activityTypeId,
    date_deadline: today,
    note: buildSalesFinalizationActivityNoteHtml_(context),
    res_id: numericSaleOrderId,
    res_model_id: modelId,
    summary,
    user_id: numericSalesUserId,
  };

  if (existingActivities.length) {
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "write",
      [[Number(existingActivities[0].id)], activityValues]
    );
    return;
  }

  executeKw_(
    cfg,
    uid,
    "mail.activity",
    "create",
    [activityValues]
  );
}

function scheduleSalesApprovalActivity_(
  cfg,
  uid,
  saleOrderId,
  salesUserId,
  context
) {
  const numericSaleOrderId = Number(saleOrderId);
  const numericSalesUserId = Number(salesUserId);

  if (
    !Number.isInteger(numericSaleOrderId) ||
    numericSaleOrderId <= 0 ||
    !Number.isInteger(numericSalesUserId) ||
    numericSalesUserId <= 0
  ) {
    return;
  }

  const modelId = getSalesModelId_(cfg, uid);
  const activityTypeId = getSalesTodoActivityTypeId_(cfg, uid);
  if (!modelId || !activityTypeId) {
    throw new Error(
      "No se pudo resolver el modelo o el tipo de actividad de ventas."
    );
  }

  const today = nowUtcString_().slice(0, 10);
  const summary = buildSalesActivitySummary_(
    "Trabajo por aprobar",
    context
  );
  const existingActivities =
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "search_read",
      [[
        ["res_model_id", "=", modelId],
        ["res_id", "=", numericSaleOrderId],
        ["user_id", "=", numericSalesUserId],
        ["activity_type_id", "=", activityTypeId],
        ["summary", "=", summary],
      ]],
      {
        fields: ["id"],
        limit: 1,
        order: "id desc",
      }
    ) || [];

  const activityValues = {
    activity_type_id: activityTypeId,
    date_deadline: today,
    note: buildSalesApprovalActivityNoteHtml_(context),
    res_id: numericSaleOrderId,
    res_model_id: modelId,
    summary,
    user_id: numericSalesUserId,
  };

  if (existingActivities.length) {
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "write",
      [[Number(existingActivities[0].id)], activityValues]
    );
    return;
  }

  executeKw_(
    cfg,
    uid,
    "mail.activity",
    "create",
    [activityValues]
  );
}

function scheduleSalesPausedActivity_(
  cfg,
  uid,
  saleOrderId,
  salesUserId,
  context
) {
  const numericSaleOrderId = Number(saleOrderId);
  const numericSalesUserId = Number(salesUserId);

  if (
    !Number.isInteger(numericSaleOrderId) ||
    numericSaleOrderId <= 0 ||
    !Number.isInteger(numericSalesUserId) ||
    numericSalesUserId <= 0
  ) {
    return;
  }

  const modelId = getSalesModelId_(cfg, uid);
  const activityTypeId = getSalesTodoActivityTypeId_(cfg, uid);
  if (!modelId || !activityTypeId) {
    throw new Error(
      "No se pudo resolver el modelo o el tipo de actividad de ventas."
    );
  }

  const today = nowUtcString_().slice(0, 10);
  const summary = buildSalesActivitySummary_(
    "Trabajo pausado",
    context
  );
  const existingActivities =
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "search_read",
      [[
        ["res_model_id", "=", modelId],
        ["res_id", "=", numericSaleOrderId],
        ["user_id", "=", numericSalesUserId],
        ["activity_type_id", "=", activityTypeId],
        ["summary", "=", summary],
      ]],
      {
        fields: ["id"],
        limit: 1,
        order: "id desc",
      }
    ) || [];

  const activityValues = {
    activity_type_id: activityTypeId,
    date_deadline: today,
    note: buildSalesPausedActivityNoteHtml_(context),
    res_id: numericSaleOrderId,
    res_model_id: modelId,
    summary,
    user_id: numericSalesUserId,
  };

  if (existingActivities.length) {
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "write",
      [[Number(existingActivities[0].id)], activityValues]
    );
    return;
  }

  executeKw_(
    cfg,
    uid,
    "mail.activity",
    "create",
    [activityValues]
  );
}

/**
 * Mantener este flujo limitado a notificaciones internas.
 * Si en el futuro se agrega chatter o correo, debe ser por una ruta separada.
 */
function postSalesFinalizationInternalNote_(context) {
  const saleOrderId = Number(cleanString_(context && context.saleOrderId));
  if (!Number.isInteger(saleOrderId) || saleOrderId <= 0) {
    throw new Error("No se pudo resolver sale.order.id para la notificacion.");
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    saleOrderId
  );
  scheduleSalesFinalizationActivity_(
    cfg,
    uid,
    saleOrderId,
    notificationTarget.userId,
    context
  );
}

function postSalesApprovalInternalNote_(context) {
  const saleOrderId = Number(cleanString_(context && context.saleOrderId));
  if (!Number.isInteger(saleOrderId) || saleOrderId <= 0) {
    throw new Error("No se pudo resolver sale.order.id para la notificacion.");
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    saleOrderId
  );
  scheduleSalesApprovalActivity_(
    cfg,
    uid,
    saleOrderId,
    notificationTarget.userId,
    context
  );
}

function postSalesPausedInternalNote_(context) {
  const saleOrderId = Number(cleanString_(context && context.saleOrderId));
  if (!Number.isInteger(saleOrderId) || saleOrderId <= 0) {
    throw new Error("No se pudo resolver sale.order.id para la notificacion.");
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    saleOrderId
  );
  scheduleSalesPausedActivity_(
    cfg,
    uid,
    saleOrderId,
    notificationTarget.userId,
    context
  );
}

function buildSalesApprovalActivityDiagnosisForRow_(sheet, row) {
  const numericRow = Number(row);

  if (!sheet) {
    return "Diagnostico aprobacion venta\n\nNo se encontro la hoja.";
  }

  if (!Number.isInteger(numericRow) || numericRow < CFG.FIRST_DATA_ROW) {
    return (
      "Diagnostico aprobacion venta\n\n" +
      `La fila ${row} no pertenece al area operativa.`
    );
  }

  const context = getSalesFinalizationContextFromRow_(sheet, numericRow);
  const stateValue = cleanString_(
    sheet.getRange(numericRow, CFG.STATE_COL).getDisplayValue()
  );
  const approvalKey = buildSalesApprovalNotificationKey_(context);
  const approvalNotifiedKeys = getSalesApprovalNotifiedKeys_();
  const cfg = getOdooCfg_();
  const lines = [
    "Diagnostico aprobacion venta",
    "",
    `Fila: ${numericRow}`,
    `Origen: ${cleanString_(context.origin) || "(vacio)"}`,
    `Estado actual: ${stateValue || "(vacio)"}`,
    `Orden: ${cleanString_(context.orderName) || "(vacia)"}`,
    `Producto: ${cleanString_(context.productName) || "(vacio)"}`,
    `Cantidad: ${cleanString_(context.quantity) || "(vacia)"}`,
    `sale.order.id: ${cleanString_(context.saleOrderId) || "(vacio)"}`,
    `sale.order.line.id: ${cleanString_(context.saleLineId) || "(vacio)"}`,
    `Clave aprobacion: ${approvalKey || "(sin clave)"}`,
    (
      approvalKey && approvalNotifiedKeys.has(approvalKey)
        ? "Clave marcada como notificada: si"
        : "Clave marcada como notificada: no"
    ),
  ];

  if (cleanString_(context.origin).toUpperCase() !== "VENTA") {
    lines.push("La fila no es de origen VENTA.");
    return lines.join("\n");
  }

  if (!isOdooConfigReady_(cfg)) {
    lines.push("La configuracion de Odoo no esta completa.");
    return lines.join("\n");
  }

  if (!cleanString_(context.saleOrderId)) {
    lines.push("Falta sale.order.id, no se puede crear la actividad.");
    return lines.join("\n");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    context.saleOrderId
  );

  lines.push(
    `Vendedor asignado: ${notificationTarget.displayName || "(sin nombre)"}`
  );
  lines.push(
    `sales user id: ${cleanString_(notificationTarget.userId) || "(vacio)"}`
  );

  if (cleanString_(stateValue).toLowerCase() !== "aprobar") {
    lines.push("La fila no esta actualmente en Aprobar.");
  }

  if (!notificationTarget.userId) {
    lines.push("La orden no tiene vendedor asignado en user_id.");
  } else {
    lines.push("La actividad se puede crear para ese vendedor.");
  }

  return lines.join("\n");
}

function diagnoseSalesApprovalActivityForRow(row) {
  const sheet = getTargetSheet_();
  const targetRow = resolveSalesActivityTargetRow_(row);
  const report = buildSalesApprovalActivityDiagnosisForRow_(
    sheet,
    targetRow
  );

  try {
    SpreadsheetApp.getUi().alert(report);
  } catch (err) {
    Logger.log(report);
  }

  return report;
}

function forceCreateSalesApprovalActivityForRow(row) {
  const numericRow = resolveSalesActivityTargetRow_(row);
  const sheet = getTargetSheet_();

  const context = getSalesFinalizationContextFromRow_(sheet, numericRow);
  const stateValue = cleanString_(
    sheet.getRange(numericRow, CFG.STATE_COL).getDisplayValue()
  );

  if (cleanString_(context.origin).toUpperCase() !== "VENTA") {
    throw new Error(`La fila ${numericRow} no es de origen VENTA.`);
  }

  if (!cleanString_(context.saleOrderId)) {
    throw new Error(
      `La fila ${numericRow} no tiene sale.order.id para crear la actividad.`
    );
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    context.saleOrderId
  );

  if (!notificationTarget.userId) {
    throw new Error(
      `La orden ${context.orderName || context.saleOrderId} no tiene vendedor asignado.`
    );
  }

  scheduleSalesApprovalActivity_(
    cfg,
    uid,
    context.saleOrderId,
    notificationTarget.userId,
    context
  );

  const approvalKey = buildSalesApprovalNotificationKey_(context);
  if (approvalKey && cleanString_(stateValue).toLowerCase() === "aprobar") {
    const approvalNotifiedKeys = getSalesApprovalNotifiedKeys_();
    if (!approvalNotifiedKeys.has(approvalKey)) {
      approvalNotifiedKeys.add(approvalKey);
      saveSalesApprovalNotifiedKeys_(approvalNotifiedKeys);
    }
  }

  const message =
    `Actividad de aprobacion creada/actualizada para fila ${numericRow}. ` +
    `Orden: ${cleanString_(context.orderName) || context.saleOrderId}. ` +
    `Vendedor: ${notificationTarget.displayName || notificationTarget.userId}.`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    row: numericRow,
    saleOrderId: cleanString_(context.saleOrderId),
    orderName: cleanString_(context.orderName),
    sellerUserId: Number(notificationTarget.userId) || 0,
    sellerName: cleanString_(notificationTarget.displayName),
    state: stateValue,
    approvalKey,
    message,
  };
}

function resolveSalesActivityTargetRow_(row) {
  const numericRow = Number(row);

  if (Number.isInteger(numericRow) && numericRow >= CFG.FIRST_DATA_ROW) {
    return numericRow;
  }

  const sheet = getTargetSheet_();
  const activeRange = sheet ? sheet.getActiveRange() : null;
  const activeRow = activeRange ? Number(activeRange.getRow()) : 0;

  if (Number.isInteger(activeRow) && activeRow >= CFG.FIRST_DATA_ROW) {
    return activeRow;
  }

  throw new Error(
    `Indicá una fila válida desde ${CFG.FIRST_DATA_ROW} o seleccioná una fila operativa antes de ejecutar la función.`
  );
}

function forceResyncSalesDeliveryFromChatterForRow(row) {
  const numericRow = resolveSalesActivityTargetRow_(row);
  const sheet = getTargetSheet_();

  if (!sheet) {
    throw new Error("No se encontró la hoja de trabajos.");
  }

  clearSalesAcceptedSyncMetadataForRow_(sheet, numericRow);
  sheet.getRange(numericRow, 8).clearContent();

  const message =
    `Fila ${numericRow} preparada para releer entrega desde chatter. ` +
    `Ejecutá luego syncOdooSalesOrdersNeo().`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    row: numericRow,
    message,
  };
}

function resolveSalesOrderKeyForManualRepair_(sheet, lookupValue) {
  const normalizedLookupValue = cleanString_(lookupValue);

  if (normalizedLookupValue) {
    return normalizeOrderNumberKey_(normalizedLookupValue);
  }

  let targetRow = 0;

  try {
    targetRow = resolveSalesActivityTargetRow_();
  } catch (err) {
    throw new Error(
      "Indicá el número de orden, por ejemplo " +
      '`forceResyncSalesDeliveryFromChatterForOrder("S56708")` ' +
      "o ejecutala teniendo seleccionada una fila operativa de esa venta."
    );
  }

  return normalizeOrderNumberKey_(
    sheet.getRange(targetRow, CFG.ORDER_COL).getDisplayValue()
  );
}

function forceResyncSalesDeliveryFromChatterForOrder(lookupValue) {
  const sheet = getTargetSheet_();
  const providedLookupValue =
    typeof lookupValue !== "undefined" && lookupValue !== null
      ? lookupValue
      : arguments.length
        ? arguments[0]
        : "";

  if (!sheet) {
    throw new Error("No se encontró la hoja de trabajos.");
  }

  const orderKey = resolveSalesOrderKeyForManualRepair_(
    sheet,
    providedLookupValue
  );
  if (!orderKey) {
    throw new Error(
      "No se pudo resolver la orden. Indicá el número o seleccioná una fila de esa venta."
    );
  }

  const snapshot = buildSalesSheetSnapshot_(sheet);
  const existingRowsMap = getExistingSalesOrderRowsMap_(sheet, snapshot);
  const rows = existingRowsMap.has(orderKey)
    ? existingRowsMap.get(orderKey).slice().sort((left, right) => left - right)
    : [];

  if (!rows.length) {
    throw new Error(
      `No se encontraron filas activas para la orden ${cleanString_(providedLookupValue) || orderKey}.`
    );
  }

  for (const row of rows) {
    clearSalesAcceptedSyncMetadataForRow_(sheet, row);
    sheet.getRange(row, 8).clearContent();
  }

  const orderName = cleanString_(
    sheet.getRange(rows[0], CFG.ORDER_COL).getDisplayValue()
  ) || orderKey;
  const message =
    `Orden ${orderName} preparada para releer entrega desde chatter. ` +
    `Filas: ${rows.join(", ")}. Ejecutá luego syncOdooSalesOrdersNeo().`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    orderKey,
    orderName,
    rows,
    message,
  };
}

function promptResyncSalesDeliveryFromChatterForOrder() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Releer entrega de venta",
    'Ingresá el número de orden, por ejemplo "S56708". ' +
      "También podés dejarlo vacío si antes seleccionás una fila de esa venta.",
    ui.ButtonSet.OK_CANCEL
  );

  if (response.getSelectedButton() !== ui.Button.OK) {
    return {
      ok: false,
      cancelled: true,
      message: "Operación cancelada por el usuario.",
    };
  }

  const lookupValue = cleanString_(response.getResponseText());

  try {
    const result = forceResyncSalesDeliveryFromChatterForOrder(lookupValue);
    ui.alert(
      "Relectura preparada",
      `${result.message}\n\nDespués ejecutá syncOdooSalesOrdersNeo().`,
      ui.ButtonSet.OK
    );
    return result;
  } catch (err) {
    const message =
      err && err.message
        ? err.message
        : "No se pudo preparar la relectura de entrega.";
    ui.alert("Releer entrega de venta", message, ui.ButtonSet.OK);
    return {
      ok: false,
      message,
    };
  }
}

function diagnoseSalesDeliverySourceForOrder(lookupValue) {
  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const normalizedLookupValue = cleanString_(lookupValue);
  if (!normalizedLookupValue) {
    throw new Error("Indicá un número de orden para diagnosticar.");
  }

  const uid = odooLogin_(cfg);
  const order = findSaleOrderForDiagnosis_(cfg, uid, normalizedLookupValue);

  if (!order) {
    throw new Error(`No se encontró la orden ${normalizedLookupValue}.`);
  }

  const messages =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.chatter,
      "search_read",
      [[
        ["model", "=", ODOO_MODELS.sales],
        ["res_id", "=", Number(order.id)],
      ]],
      {
        fields: ["id", "date", "subject", "body", "author_id"],
        order: "date desc, id desc",
        limit: 12,
      }
    ) || [];

  const lines = [
    `Diagnostico entrega venta: ${cleanString_(order.name)}`,
    `sale.order.id: ${cleanString_(order.id)}`,
    "",
  ];

  if (!messages.length) {
    lines.push("No se encontraron mensajes en el chatter.");
  }

  for (const message of messages) {
    const rawBody =
      message && Object.prototype.hasOwnProperty.call(message, "body")
        ? message.body
        : "";
    const rawSubject =
      message && Object.prototype.hasOwnProperty.call(message, "subject")
        ? message.subject
        : "";
    const bodyText =
      typeof normalizeMessageBody_ === "function"
        ? normalizeMessageBody_(rawBody)
        : cleanString_(rawBody);
    const isAutomated = isAutomatedSalesNotificationMessage_(
      bodyText,
      rawSubject
    );
    const parsed =
      typeof parseSalesPlanningNote_ === "function"
        ? parseSalesPlanningNote_(rawBody)
        : { date: "", state: "" };
    const authorName = getMany2oneName_(message.author_id);
    const preview = cleanString_(bodyText).replace(/\s+/g, " ").slice(0, 140);

    lines.push(
      [
        `id=${cleanString_(message.id)}`,
        `fecha_msg=${cleanString_(message.date) || "(vacia)"}`,
        `autor=${cleanString_(authorName) || "(vacio)"}`,
        `auto=${isAutomated ? "si" : "no"}`,
        `fecha_parseada=${cleanString_(parsed && parsed.date) || "(ninguna)"}`,
        `estado_parseado=${cleanString_(parsed && parsed.state) || "(ninguno)"}`,
        `subject=${cleanString_(rawSubject) || "(vacio)"}`,
        `body=${preview || "(vacio)"}`,
      ].join(" | ")
    );
  }

  const report = lines.join("\n");

  try {
    SpreadsheetApp.getUi().alert(report);
  } catch (err) {
    Logger.log(report);
  }

  return report;
}

function promptDiagnoseSalesDeliverySourceForOrder() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Diagnosticar entrega de venta",
    'Ingresá el número de orden, por ejemplo "S56708".',
    ui.ButtonSet.OK_CANCEL
  );

  if (response.getSelectedButton() !== ui.Button.OK) {
    return {
      ok: false,
      cancelled: true,
      message: "Operación cancelada por el usuario.",
    };
  }

  const lookupValue = cleanString_(response.getResponseText());
  return diagnoseSalesDeliverySourceForOrder(lookupValue);
}

function buildSalesFinalizationActivityDiagnosisForRow_(sheet, row) {
  const numericRow = Number(row);

  if (!sheet) {
    return "Diagnostico actividad venta\n\nNo se encontro la hoja.";
  }

  if (!Number.isInteger(numericRow) || numericRow < CFG.FIRST_DATA_ROW) {
    return (
      "Diagnostico actividad venta\n\n" +
      `La fila ${row} no pertenece al area operativa.`
    );
  }

  const context = getSalesFinalizationContextFromRow_(sheet, numericRow);
  const stateValue = cleanString_(
    sheet.getRange(numericRow, CFG.STATE_COL).getDisplayValue()
  );
  const notificationKey = buildSalesFinalizationNotificationKey_(context);
  const notifiedKeys = getSalesFinalizationNotifiedKeys_();
  const cfg = getOdooCfg_();
  const lines = [
    "Diagnostico actividad venta",
    "",
    `Fila: ${numericRow}`,
    `Origen: ${cleanString_(context.origin) || "(vacio)"}`,
    `Estado actual: ${stateValue || "(vacio)"}`,
    `Orden: ${cleanString_(context.orderName) || "(vacia)"}`,
    `Producto: ${cleanString_(context.productName) || "(vacio)"}`,
    `Cantidad: ${cleanString_(context.quantity) || "(vacia)"}`,
    `sale.order.id: ${cleanString_(context.saleOrderId) || "(vacio)"}`,
    `sale.order.line.id: ${cleanString_(context.saleLineId) || "(vacio)"}`,
    `Clave notificacion: ${notificationKey || "(sin clave)"}`,
    (
      notificationKey && notifiedKeys.has(notificationKey)
        ? "Clave marcada como notificada: si"
        : "Clave marcada como notificada: no"
    ),
  ];

  if (cleanString_(context.origin).toUpperCase() !== "VENTA") {
    lines.push("La fila no es de origen VENTA.");
    return lines.join("\n");
  }

  if (!isOdooConfigReady_(cfg)) {
    lines.push("La configuracion de Odoo no esta completa.");
    return lines.join("\n");
  }

  if (!cleanString_(context.saleOrderId)) {
    lines.push("Falta sale.order.id, no se puede crear la actividad.");
    return lines.join("\n");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    context.saleOrderId
  );

  lines.push(
    `Vendedor asignado: ${notificationTarget.displayName || "(sin nombre)"}`
  );
  lines.push(
    `sales user id: ${cleanString_(notificationTarget.userId) || "(vacio)"}`
  );

  if (!notificationTarget.userId) {
    lines.push("La orden no tiene vendedor asignado en user_id.");
  } else {
    lines.push("La actividad se puede crear para ese vendedor.");
  }

  return lines.join("\n");
}

function diagnoseSalesFinalizationActivityForRow(row) {
  const sheet = getTargetSheet_();
  const targetRow = resolveSalesActivityTargetRow_(row);
  const report = buildSalesFinalizationActivityDiagnosisForRow_(
    sheet,
    targetRow
  );

  try {
    SpreadsheetApp.getUi().alert(report);
  } catch (err) {
    Logger.log(report);
  }

  return report;
}

function forceCreateSalesFinalizationActivityForRow(row) {
  const numericRow = resolveSalesActivityTargetRow_(row);
  const sheet = getTargetSheet_();

  const context = getSalesFinalizationContextFromRow_(sheet, numericRow);
  const stateValue = cleanString_(
    sheet.getRange(numericRow, CFG.STATE_COL).getDisplayValue()
  );

  if (cleanString_(context.origin).toUpperCase() !== "VENTA") {
    throw new Error(`La fila ${numericRow} no es de origen VENTA.`);
  }

  if (!cleanString_(context.saleOrderId)) {
    throw new Error(
      `La fila ${numericRow} no tiene sale.order.id para crear la actividad.`
    );
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getSalesNotificationTarget_(
    cfg,
    uid,
    context.saleOrderId
  );

  if (!notificationTarget.userId) {
    throw new Error(
      `La orden ${context.orderName || context.saleOrderId} no tiene vendedor asignado.`
    );
  }

  scheduleSalesFinalizationActivity_(
    cfg,
    uid,
    context.saleOrderId,
    notificationTarget.userId,
    context
  );

  const notificationKey = buildSalesFinalizationNotificationKey_(context);
  if (notificationKey && cleanString_(stateValue).toLowerCase() === "finalizado") {
    const notifiedKeys = getSalesFinalizationNotifiedKeys_();
    if (!notifiedKeys.has(notificationKey)) {
      notifiedKeys.add(notificationKey);
      saveSalesFinalizationNotifiedKeys_(notifiedKeys);
    }
  }

  const message =
    `Actividad de venta creada/actualizada para fila ${numericRow}. ` +
    `Orden: ${cleanString_(context.orderName) || context.saleOrderId}. ` +
    `Vendedor: ${notificationTarget.displayName || notificationTarget.userId}.`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    row: numericRow,
    saleOrderId: cleanString_(context.saleOrderId),
    orderName: cleanString_(context.orderName),
    sellerUserId: Number(notificationTarget.userId) || 0,
    sellerName: cleanString_(notificationTarget.displayName),
    state: stateValue,
    notificationKey,
    message,
  };
}

function getSalesImportedIds_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    SALES_CFG.IMPORTED_IDS_PROPERTY
  );
  return parseStoredIdSet_(raw);
}

function getSalesSkippedWriteDateProperty_() {
  return "ODOO_SALES_SKIPPED_WRITE_DATES";
}

function getSalesSkippedWriteDates_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    getSalesSkippedWriteDateProperty_()
  );

  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (err) {
    return {};
  }
}

function saveSalesSkippedWriteDates_(data) {
  PropertiesService.getScriptProperties().setProperty(
    getSalesSkippedWriteDateProperty_(),
    JSON.stringify(data || {})
  );
}

function setSalesSkippedWriteDate_(data, saleId, writeDate) {
  const normalizedSaleId = cleanString_(saleId);
  if (!normalizedSaleId) return;

  data[normalizedSaleId] = cleanString_(writeDate) || nowUtcString_();
}

function clearSalesSkippedWriteDate_(data, saleId) {
  const normalizedSaleId = cleanString_(saleId);
  if (!normalizedSaleId) return;

  if (!Object.prototype.hasOwnProperty.call(data, normalizedSaleId)) {
    return;
  }

  delete data[normalizedSaleId];
}

function shouldSkipSalesOrderReprocessing_(
  order,
  skippedIds,
  skippedWriteDateById,
  existingSalesRowsMap,
  incompleteOrderKeys
) {
  const saleId = cleanString_(order && order.id);
  if (!saleId || !skippedIds || !skippedIds.has(saleId)) {
    return false;
  }

  const orderKey = normalizeOrderNumberKey_(order && order.name);
  if (orderKey && existingSalesRowsMap && existingSalesRowsMap.has(orderKey)) {
    return false;
  }

  if (orderKey && incompleteOrderKeys && incompleteOrderKeys.has(orderKey)) {
    return false;
  }

  const skippedWriteDate = cleanString_(
    skippedWriteDateById && skippedWriteDateById[saleId]
  );
  const currentWriteDate = cleanString_(order && order.write_date);

  if (!skippedWriteDate || !currentWriteDate) {
    return false;
  }

  return !isUtcStringAfter_(currentWriteDate, skippedWriteDate);
}

function saveSalesImportedIds_(idSet) {
  PropertiesService.getScriptProperties().setProperty(
    SALES_CFG.IMPORTED_IDS_PROPERTY,
    JSON.stringify(Array.from(idSet))
  );
}

function getSalesSkippedIds_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    SALES_CFG.SKIPPED_IDS_PROPERTY
  );
  return parseStoredIdSet_(raw);
}

function saveSalesSkippedIds_(idSet) {
  PropertiesService.getScriptProperties().setProperty(
    SALES_CFG.SKIPPED_IDS_PROPERTY,
    JSON.stringify(Array.from(idSet))
  );
}
