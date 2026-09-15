/**
 * ============================================================================
 * UTILIDADES DE HOJA, DATOS, FECHAS E IDS
 * ============================================================================
 */

/**
 * Obtiene el enlace configurado en una celda.
 */
function getCellLinkUrl_(range) {
  try {
    const richText = range.getRichTextValue();

    if (richText) {
      const directUrl = cleanString_(
        richText.getLinkUrl()
      );

      if (directUrl) {
        return directUrl;
      }

      const runs = richText.getRuns
        ? richText.getRuns()
        : [];

      for (const run of runs) {
        const runUrl = cleanString_(
          run.getLinkUrl
            ? run.getLinkUrl()
            : ""
        );

        if (runUrl) {
          return runUrl;
        }
      }
    }
  } catch (err) {
    logDebug_(
      "No se pudo leer el RichText de la celda: " +
        err
    );
  }

  try {
    const formula = cleanString_(
      range.getFormula()
    );

    const formulaMatch = formula.match(
      /HYPERLINK\(\s*"([^"]+)"/i
    );

    if (formulaMatch && formulaMatch[1]) {
      return cleanString_(formulaMatch[1]);
    }
  } catch (err) {
    logDebug_(
      "No se pudo leer la fórmula de enlace: " +
        err
    );
  }

  try {
    const value = cleanString_(
      range.getValue()
    );

    const valueMatch = value.match(
      /https?:\/\/[^\s'"]+/i
    );

    if (valueMatch && valueMatch[0]) {
      return cleanString_(valueMatch[0]);
    }
  } catch (err) {
    logDebug_(
      "No se pudo leer el valor de enlace: " +
        err
    );
  }

  return "";
}

/**
 * Lee de forma segura la nota de una celda.
 */
function safeGetNote_(range) {
  try {
    return cleanString_(range.getNote());
  } catch (err) {
    return "";
  }
}

/**
 * Marca la casilla de una fila recién importada.
 */
function markRowAsNew_(sheet, row) {
  const checkboxCell = sheet.getRange(row, CFG.NEW_ROW_CHECKBOX_COL);

  if (isCheckboxCellConfigured_(checkboxCell)) {
    checkboxCell.check();
  }
}

function clearNewRowMarker_(sheet, row) {
  const checkboxCell = sheet.getRange(row, CFG.NEW_ROW_CHECKBOX_COL);

  if (isCheckboxCellConfigured_(checkboxCell)) {
    checkboxCell.uncheck();
  }
}
/**
 * Convierte diferentes nombres de fabricación
 * en una clave numérica comparable.
 */
function normalizeManufacturingExistenceKey_(
  value
) {
  const text = cleanString_(value);

  if (!text) {
    return "";
  }

  const baseText = text.replace(
    /-\d+$/,
    ""
  );

  const match = baseText.match(
    /(\d+)(?!.*\d)/
  );

  if (!match) {
    return "";
  }

  const number = Number(match[1]);

  return Number.isNaN(number)
    ? ""
    : String(number);
}

/**
 * ============================================================================
 * ESTADO DE SINCRONIZACIÓN
 * ============================================================================
 */

/**
 * ensureDeliveryDaysFormulasForActiveRows_ vive en 08_automatizaciones.txt
 * (recibe lastOperationalRow ya calculado con getOperationalLastRow_).
 * Esta copia usaba sheet.getLastRow(), que getOperationalLastRow_ evita
 * a proposito porque las formulas de la columna L pueden extenderse mas
 * alla de los trabajos reales. Se elimino para no duplicar la funcion.
 */

function resetSyncState() {
  const properties =
    PropertiesService.getScriptProperties();

  properties.deleteProperty(
    MFG_CFG.LAST_SYNC_PROPERTY
  );

  properties.deleteProperty(
    MFG_CFG.IMPORTED_IDS_PROPERTY
  );

  properties.deleteProperty(
    SALES_CFG.LAST_SYNC_PROPERTY
  );

  properties.deleteProperty(
    SALES_CFG.LINE_LAST_SYNC_PROPERTY
  );

  properties.deleteProperty(
    SALES_CFG.IMPORTED_IDS_PROPERTY
  );

  properties.deleteProperty(
    SALES_CFG.SKIPPED_IDS_PROPERTY
  );

  Logger.log(
    "Estado de sincronización reiniciado."
  );
}

function testSheetAccess() {
  const spreadsheet =
    getApiSpreadsheet_();

  const sheet = getTargetSheet_();

  Logger.log(
    "Archivo actual: " +
      spreadsheet.getName()
  );

  Logger.log(
    "Pestaña destino: " +
      sheet.getName()
  );

  Logger.log(
    "Primera fila disponible: " +
      getFirstAvailableRow_(sheet)
  );
}

function showSpreadsheetToast_(message) {
  try {
    const spreadsheet =
      getApiSpreadsheet_();

    if (spreadsheet) {
      spreadsheet.toast(message);
    }
  } catch (err) {
    Logger.log(message);
  }
}

/**
 * ============================================================================
 * ACCESO Y FILAS DE LA HOJA
 * ============================================================================
 */

function getTargetSheet_() {
  const spreadsheet =
    getApiSpreadsheet_();

  if (!spreadsheet) {
    throw new Error(
      "No se pudo obtener la planilla activa."
    );
  }

  const sheet = spreadsheet.getSheetByName(
    CFG.SHEET_NAME
  );

  if (!sheet) {
    throw new Error(
      "No existe la pestaña: " +
        CFG.SHEET_NAME
    );
  }

  return sheet;
}

function getApiSpreadsheet_() {
  if (
    typeof WEBAPP_RUNTIME_CONTEXT !== "undefined" &&
    WEBAPP_RUNTIME_CONTEXT &&
    WEBAPP_RUNTIME_CONTEXT.spreadsheetId
  ) {
    return SpreadsheetApp.openById(WEBAPP_RUNTIME_CONTEXT.spreadsheetId);
  }

  return SpreadsheetApp.getActiveSpreadsheet();
}

/**
 * Busca la primera fila vacía entre Orden y Estado.
 */
function getFirstAvailableRow_(sheet) {
  const scanWidth = getRowScanWidth_(sheet);

  const scanRows =
    getConfiguredScanRowCount_(
      sheet,
      MFG_CFG.MAX_SCAN_ROWS
    );

  if (!scanRows) {
    return null;
  }

  const values = sheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      CFG.ORDER_COL,
      scanRows,
      scanWidth
    )
    .getDisplayValues();

  for (let index = 0; index < values.length; index++) {
    const hasData = values[index].some(
      (cell) => cleanString_(cell) !== ""
    );

    if (!hasData) {
      return CFG.FIRST_DATA_ROW + index;
    }
  }

  return null;
}

/**
 * Busca una fila vacía a partir de una fila determinada.
 */
function findNextAvailableRowFrom_(
  sheet,
  startRow
) {
  if (
    !startRow ||
    startRow < CFG.FIRST_DATA_ROW ||
    startRow > sheet.getMaxRows()
  ) {
    return null;
  }

  const lastRow = Math.max(
    sheet.getLastRow(),
    startRow
  );

  const scanWidth = getRowScanWidth_(sheet);

  const values = sheet
    .getRange(
      startRow,
      CFG.ORDER_COL,
      Math.max(
        1,
        lastRow - startRow + 1
      ),
      scanWidth
    )
    .getDisplayValues();

  for (let index = 0; index < values.length; index++) {
    const hasData = values[index].some(
      (cell) => cleanString_(cell) !== ""
    );

    if (!hasData) {
      return startRow + index;
    }
  }

  return null;
}

/**
 * Cantidad de columnas analizadas para decidir
 * si una fila está libre.
 */
function getRowScanWidth_(sheet) {
  return Math.max(
    1,
    CFG.STATE_COL - CFG.ORDER_COL + 1
  );
}

function getConfiguredScanRowCount_(
  sheet,
  maximumRows
) {
  const availableRows = Math.max(
    0,
    sheet.getMaxRows() -
      CFG.FIRST_DATA_ROW +
      1
  );

  return Math.min(
    maximumRows,
    availableRows
  );
}

/**
 * getExistingManufacturingOrderRowMap_ vive en 04_Fabricacion.txt (filtra
 * filas en estado "Archivar" y valida origen antes de mapear). Esta copia
 * era un escaneo simple sin ese filtro; se elimino para no duplicar la
 * funcion.
 */

/**
 * Obtiene las claves de todas las órdenes visibles.
 */
function getExistingSheetOrderKeys_(sheet) {
  const scanRows =
    getConfiguredScanRowCount_(
      sheet,
      MFG_CFG.MAX_SCAN_ROWS
    );

  const keys = new Set();

  if (!scanRows) {
    return keys;
  }

  const values = sheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      CFG.ORDER_COL,
      scanRows,
      1
    )
    .getDisplayValues();

  for (const row of values) {
    addOrderKeysToSet_(keys, row[0]);
  }

  return keys;
}

function addOrderKeysToSet_(keys, value) {
  const normalizedKey =
    normalizeOrderNumberKey_(value);

  if (normalizedKey) {
    keys.add(normalizedKey);
  }

  const manufacturingKey =
    normalizeManufacturingExistenceKey_(
      value
    );

  if (manufacturingKey) {
    keys.add(manufacturingKey);
  }
}

function hasOrderKeyInSet_(keys, orderKey) {
  if (!orderKey) {
    return false;
  }

  return keys.has(String(orderKey));
}

/**
 * ============================================================================
 * IDS IMPORTADOS
 * ============================================================================
 */

function parseStoredIdSet_(raw) {
  const ids = new Set();

  if (!raw) {
    return ids;
  }

  try {
    const values = JSON.parse(raw);

    if (!Array.isArray(values)) {
      return ids;
    }

    for (const id of values) {
      ids.add(String(id));
    }
  } catch (err) {
    Logger.log(
      "No se pudieron leer los IDs guardados: " +
        err
    );
  }

  return ids;
}

function getImportedIds_() {
  const raw =
    PropertiesService
      .getScriptProperties()
      .getProperty(
        MFG_CFG.IMPORTED_IDS_PROPERTY
      );

  return parseStoredIdSet_(raw);
}

function saveImportedIds_(idSet) {
  PropertiesService
    .getScriptProperties()
    .setProperty(
      MFG_CFG.IMPORTED_IDS_PROPERTY,
      JSON.stringify(Array.from(idSet))
    );
}

/**
 * ============================================================================
 * MANY2ONE Y NÚMEROS DE ORDEN
 * ============================================================================
 */

function getMany2oneName_(value) {
  if (
    Array.isArray(value) &&
    value.length > 1
  ) {
    return cleanString_(value[1]);
  }

  return cleanString_(value);
}

function getMany2oneId_(value) {
  if (
    Array.isArray(value) &&
    value.length > 0
  ) {
    return cleanString_(value[0]);
  }

  return "";
}

function extractTrailingDigits_(value) {
  const text = cleanString_(value);

  if (!text) {
    return "";
  }

  const match = text.match(
    /(\d+)(?!.*\d)/
  );

  return match ? match[1] : "";
}

function parseOrderNumberForSheet_(value) {
  const digits = extractTrailingDigits_(value);

  if (!digits) {
    return "";
  }

  const number = Number(digits);

  return Number.isNaN(number)
    ? ""
    : number;
}

function normalizeOrderNumberKey_(value) {
  const digits = extractTrailingDigits_(value);

  if (!digits) {
    return "";
  }

  const number = Number(digits);

  return Number.isNaN(number)
    ? ""
    : String(number);
}

function isPartialManufacturingOrder_(value) {
  return /-\d+$/.test(
    cleanString_(value)
  );
}

/**
 * ============================================================================
 * CANTIDADES Y TEXTOS
 * ============================================================================
 */

function normalizeQuantity_(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  if (typeof value === "number") {
    return value;
  }

  let text = String(value)
    .trim()
    .replace(/\s/g, "");

  if (
    text.includes(",") &&
    text.includes(".")
  ) {
    text = text
      .replace(/\./g, "")
      .replace(",", ".");
  } else if (text.includes(",")) {
    text = text.replace(",", ".");
  }

  const number = parseFloat(text);

  if (Number.isNaN(number)) {
    throw new Error(
      "Cantidad inválida recibida desde Odoo: " +
        value
    );
  }

  return number;
}

function cleanString_(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return "";
  }

  return String(value).trim();
}

/**
 * ============================================================================
 * FECHAS
 * ============================================================================
 */

/**
 * Normaliza cualquier valor de fecha a un Date sin hora, conservando el año.
 *
 * Es la alternativa a formatDateForSheet_ cuando el destino es una celda: ese
 * formatea a "d-MMM", que descarta el año y obliga a reparsear el texto
 * despues. Ese round-trip era el origen de las fechas con año 2001.
 */
function toSheetDateValue_(dateValue) {
  if (!dateValue) {
    return null;
  }

  const dateObject =
    dateValue instanceof Date ? dateValue : new Date(dateValue);

  if (Number.isNaN(dateObject.getTime())) {
    return null;
  }

  return new Date(
    dateObject.getFullYear(),
    dateObject.getMonth(),
    dateObject.getDate()
  );
}

function formatDateForSheet_(dateValue) {
  if (!dateValue) {
    return "";
  }

  const dateObject = new Date(dateValue);

  if (Number.isNaN(dateObject.getTime())) {
    return "";
  }

  return Utilities.formatDate(
    dateObject,
    Session.getScriptTimeZone(),
    "d-MMM"
  );
}

function tryParseDateString_(raw) {
  if (!raw) {
    return null;
  }

  const normalizedRaw = String(raw)
    .replace(/\s+/g, " ")
    .trim();

  const dayMonthYear = normalizedRaw.match(
    /^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/
  );

  if (dayMonthYear) {
    const day = Number(dayMonthYear[1]);
    const month =
      Number(dayMonthYear[2]) - 1;

    const rawYear = Number(
      dayMonthYear[3]
    );

    const year =
      rawYear < 100
        ? 2000 + rawYear
        : rawYear;

    const date = new Date(
      year,
      month,
      day
    );

    if (
      !Number.isNaN(date.getTime()) &&
      date.getDate() === day &&
      date.getMonth() === month &&
      date.getFullYear() === year
    ) {
      return assertPlausibleSheetDate_(date);
    }

    return null;
  }

  // Acepta "24 ago", "24-ago", "24/Aug", "7-sept", "24-Aug 2026".
  // Antes solo aceptaba espacio, asi que las fechas que la planilla muestra
  // con guion ("24-ago") caian al fallback new Date(), donde V8 les asigna
  // silenciosamente el año 2001.
  const textDate = normalizedRaw.match(
    /^(\d{1,2})[\s\/\-]+([A-Za-z.]{3,})(?:[\s\/\-]+(\d{2,4}))?$/i
  );

  if (textDate) {
    const day = Number(textDate[1]);

    const monthKey = textDate[2]
      .toLowerCase()
      .replace(/\./g, "")
      .substring(0, 3);

    const month = MONTH_ALIASES[monthKey];

    if (month !== undefined) {
      const rawYear = textDate[3]
        ? Number(textDate[3])
        : new Date().getFullYear();

      const year =
        rawYear < 100
          ? 2000 + rawYear
          : rawYear;

      const date = new Date(
        year,
        month,
        day
      );

      if (
        !Number.isNaN(date.getTime()) &&
        date.getDate() === day &&
        date.getMonth() === month &&
        date.getFullYear() === year
      ) {
        return assertPlausibleSheetDate_(date);
      }
    }

    return null;
  }

  // Fallback a new Date() solo si el texto ya parece una fecha completa:
  // tiene año de 4 digitos Y algo mas ademas de digitos.
  //
  // new Date() no se puede usar a ciegas sobre texto arbitrario:
  //   new Date("24-Aug") -> 2001-08-24  (inventa el año 2001)
  //   new Date("1980")   -> 1979-12-31  (lo toma como año suelto)
  //   new Date("4910")   -> 4909-12-31  (un codigo de producto pasa por fecha)
  // Los dos ultimos son los que metian fechas absurdas en la planilla cuando
  // una linea de la nota era solo un numero.
  if (!/\d{4}/.test(normalizedRaw) || /^\d+$/.test(normalizedRaw)) {
    return null;
  }

  const fallbackDate = new Date(
    normalizedRaw
  );

  return Number.isNaN(fallbackDate.getTime())
    ? null
    : assertPlausibleSheetDate_(fallbackDate);
}

/**
 * Ultima red de seguridad: descarta fechas fuera de un rango razonable.
 *
 * Ningun trabajo de produccion tiene entrega en 1980 ni en 4910. Si algo asi
 * llega hasta aca es que se interpreto mal un texto que no era una fecha, y es
 * preferible dejar la celda vacia antes que escribir un valor absurdo que
 * despues rompe los calculos de la columna de dias.
 */
function assertPlausibleSheetDate_(dateObject) {
  if (!dateObject || Number.isNaN(dateObject.getTime())) {
    return null;
  }

  const year = dateObject.getFullYear();
  const currentYear = new Date().getFullYear();

  if (
    year < currentYear - SHEET_DATE_MAX_YEARS_BACK ||
    year > currentYear + SHEET_DATE_MAX_YEARS_AHEAD
  ) {
    logDebug_(
      `Fecha descartada por implausible (año ${year}): ${dateObject}`
    );
    return null;
  }

  return dateObject;
}

function nowUtcString_() {
  return Utilities.formatDate(
    new Date(),
    "UTC",
    "yyyy-MM-dd HH:mm:ss"
  );
}

function shiftUtcString_(
  utcString,
  minutes
) {
  const date = new Date(
    String(utcString)
      .replace(" ", "T") + "Z"
  );

  if (Number.isNaN(date.getTime())) {
    throw new Error(
      "Fecha UTC inválida: " +
        utcString
    );
  }

  date.setUTCMinutes(
    date.getUTCMinutes() + minutes
  );

  return Utilities.formatDate(
    date,
    "UTC",
    "yyyy-MM-dd HH:mm:ss"
  );
}

function daysAgoUtcString_(days) {
  const date = new Date();

  date.setUTCDate(
    date.getUTCDate() - days
  );

  return Utilities.formatDate(
    date,
    "UTC",
    "yyyy-MM-dd HH:mm:ss"
  );
}

/**
 * ============================================================================
 * LOGS
 * ============================================================================
 */

function logDebug_(message) {
  if (MFG_CFG.DEBUG_LOGS) {
    Logger.log(message);
  }
}
