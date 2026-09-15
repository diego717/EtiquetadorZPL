/**
 * Cliente full backend para la planilla de Cuenta B.
 *
 * Pegar en el Apps Script vinculado a la planilla de prueba. Este archivo
 * expone installNeoApiMenu() para agregar un menu "Neo API" con acciones
 * remotas en Cuenta A.
 */

const ETIQUETADOR_FULL_API_URL_PROPERTY = "ETIQUETADOR_FULL_API_URL";
const ETIQUETADOR_FULL_API_TOKEN_PROPERTY = "ETIQUETADOR_FULL_API_TOKEN";

function installNeoApiMenu() {
  const ui = SpreadsheetApp.getUi();

  ui.createMenu("Neo API")
    .addItem("Probar API", "apiFullPing")
    .addItem("Probar acceso a planilla", "apiSheetAccessCheck")
    .addSeparator()
    .addItem("Probar login Odoo", "apiOdooLoginCheck")
    .addItem("Probar lectura Odoo", "apiOdooDataProbe")
    .addSeparator()
    .addItem("Sincronizar FABRICACION", "apiSyncManufacturing")
    .addItem("Sincronizar VENTAS NEO", "apiSyncSales")
    .addItem("Sincronizar todas", "apiSyncAll")
    .addSeparator()
    .addItem("Reparar metadata ventas", "apiRepairExistingSalesHiddenMetadata")
    .addItem("Reparar formulas dias", "apiRepairDeliveryDaysFormulas")
    .addItem("Reparar fechas fabricacion", "apiRepairManufacturingDateValues")
    .addItem("Reparar fechas ventas", "apiRepairSalesDateValues")
    .addItem("Reparar checkboxes", "apiRepairOperationalCheckboxes")
    .addSeparator()
    .addItem("Reconstruir enlaces", "apiRebuildLinks")
    .addItem("Resetear estado sync", "apiResetSyncState")
    .addSeparator()
    .addItem("Configurar API", "configurarEtiquetadorFullApi")
    .addToUi();
}

function configurarEtiquetadorFullApi() {
  const ui = SpreadsheetApp.getUi();
  const urlResponse = ui.prompt(
    "Configurar Neo API",
    "Pega la URL del Web App full backend de Cuenta A.",
    ui.ButtonSet.OK_CANCEL
  );

  if (urlResponse.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  const tokenResponse = ui.prompt(
    "Configurar Neo API",
    "Pega el token generado por setupApiToken().",
    ui.ButtonSet.OK_CANCEL
  );

  if (tokenResponse.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  const url = String(urlResponse.getResponseText() || "").trim();
  const token = String(tokenResponse.getResponseText() || "").trim();

  if (!url || !token) {
    ui.alert("URL y token son obligatorios.");
    return;
  }

  PropertiesService.getScriptProperties().setProperties({
    [ETIQUETADOR_FULL_API_URL_PROPERTY]: url,
    [ETIQUETADOR_FULL_API_TOKEN_PROPERTY]: token
  });

  ui.alert("Neo API configurada.");
}

function apiFullPing() {
  showApiResult_("Probar API", llamarEtiquetadorFullApi_("ping", {}));
}

function apiSheetAccessCheck() {
  showApiResult_(
    "Acceso a planilla",
    llamarEtiquetadorFullApi_("sheetAccessCheck", {})
  );
}

function apiOdooLoginCheck() {
  showApiResult_("Login Odoo", llamarEtiquetadorFullApi_("odooLoginCheck", {}));
}

function apiOdooDataProbe() {
  showApiResult_("Lectura Odoo", llamarEtiquetadorFullApi_("odooDataProbe", {}));
}

function apiSyncManufacturing() {
  showApiResult_(
    "Sincronizar fabricacion",
    llamarEtiquetadorFullApi_("syncManufacturing", {})
  );
}

function apiSyncSales() {
  showApiResult_(
    "Sincronizar ventas",
    llamarEtiquetadorFullApi_("syncSales", {})
  );
}

function apiSyncAll() {
  showApiResult_("Sincronizar todas", llamarEtiquetadorFullApi_("syncAll", {}));
}

function apiResetSyncState() {
  showApiResult_(
    "Resetear estado sync",
    llamarEtiquetadorFullApi_("resetSyncState", {})
  );
}

function apiRepairExistingSalesHiddenMetadata() {
  showApiResult_(
    "Reparar metadata ventas",
    llamarEtiquetadorFullApi_("repairExistingSalesHiddenMetadata", {})
  );
}

function apiRepairDeliveryDaysFormulas() {
  showApiResult_(
    "Reparar formulas dias",
    llamarEtiquetadorFullApi_("repairDeliveryDaysFormulas", {})
  );
}

function apiRepairManufacturingDateValues() {
  showApiResult_(
    "Reparar fechas fabricacion",
    llamarEtiquetadorFullApi_("repairManufacturingDateValues", {})
  );
}

function apiRepairSalesDateValues() {
  showApiResult_(
    "Reparar fechas ventas",
    llamarEtiquetadorFullApi_("repairSalesIngressDateValues", {})
  );
  showApiResult_(
    "Reparar fechas entrega ventas",
    llamarEtiquetadorFullApi_("repairSalesDeliveryDateValues", {})
  );
}

function apiRepairOperationalCheckboxes() {
  showApiResult_(
    "Reparar checkboxes",
    llamarEtiquetadorFullApi_("repairOperationalCheckboxes", {})
  );
}

function apiRebuildLinks() {
  showApiResult_(
    "Reconstruir enlaces",
    llamarEtiquetadorFullApi_("rebuildLinks", {})
  );
}

function migrarOdooConfigLocalAFullApi() {
  const props = PropertiesService.getScriptProperties();
  const config = {
    ODOO_URL: props.getProperty("ODOO_URL") || "",
    ODOO_DB: props.getProperty("ODOO_DB") || "",
    ODOO_USER: props.getProperty("ODOO_USER") || "",
    ODOO_API_KEY: props.getProperty("ODOO_API_KEY") || "",
    ODOO_CIDS: props.getProperty("ODOO_CIDS") || "1"
  };

  showApiResult_(
    "Migrar config Odoo",
    llamarEtiquetadorFullApi_("odooConfigSet", config)
  );
}

function llamarEtiquetadorFullApi_(action, payload) {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty(ETIQUETADOR_FULL_API_URL_PROPERTY);
  const token = props.getProperty(ETIQUETADOR_FULL_API_TOKEN_PROPERTY);

  if (!url || !token) {
    throw new Error("Neo API no configurada. Ejecuta configurarEtiquetadorFullApi().");
  }

  const requestPayload = payload || {};
  requestPayload.spreadsheetId = SpreadsheetApp.getActiveSpreadsheet().getId();

  const httpResponse = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      token: token,
      action: action,
      payload: requestPayload
    }),
    muteHttpExceptions: true,
    followRedirects: true,
    validateHttpsCertificates: true
  });

  const text = httpResponse.getContentText();
  let parsed;

  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(
      "La API no devolvio JSON. HTTP " +
        httpResponse.getResponseCode() +
        ": " +
        text.slice(0, 500)
    );
  }

  if (!parsed.ok) {
    throw new Error(parsed.error || "Error desconocido en API.");
  }

  return parsed;
}

function showApiResult_(title, response) {
  SpreadsheetApp.getUi().alert(title, JSON.stringify(response, null, 2), SpreadsheetApp.getUi().ButtonSet.OK);
}
