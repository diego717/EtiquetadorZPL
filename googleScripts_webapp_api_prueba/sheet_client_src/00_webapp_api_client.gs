/**
 * Cliente de prueba para llamar al Web App API desde la planilla.
 *
 * Este codigo va en el Apps Script vinculado a la planilla de la Cuenta B.
 * Primero configurar URL y token ejecutando:
 *
 *   configurarEtiquetadorApi()
 *
 * Despues probar:
 *
 *   probarEtiquetadorApiPing()
 */

const ETIQUETADOR_API_URL_PROPERTY = "ETIQUETADOR_API_URL";
const ETIQUETADOR_API_TOKEN_PROPERTY = "ETIQUETADOR_API_TOKEN";

function configurarEtiquetadorApi() {
  const ui = SpreadsheetApp.getUi();

  const urlResponse = ui.prompt(
    "Configurar API EtiquetadorZPL",
    "Pegá la URL del Web App de Cuenta A.",
    ui.ButtonSet.OK_CANCEL
  );

  if (urlResponse.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  const tokenResponse = ui.prompt(
    "Configurar API EtiquetadorZPL",
    "Pegá el token generado por setupApiToken().",
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
    [ETIQUETADOR_API_URL_PROPERTY]: url,
    [ETIQUETADOR_API_TOKEN_PROPERTY]: token
  });

  ui.alert("API configurada. Ahora ejecutá probarEtiquetadorApiPing().");
}

function configurarEtiquetadorApiManual() {
  const url = "PEGAR_URL_DEL_WEB_APP";
  const token = "PEGAR_TOKEN_GENERADO_EN_CUENTA_A";

  if (url.indexOf("PEGAR_") === 0 || token.indexOf("PEGAR_") === 0) {
    throw new Error("Editá configurarEtiquetadorApiManual() con URL y token reales.");
  }

  PropertiesService.getScriptProperties().setProperties({
    [ETIQUETADOR_API_URL_PROPERTY]: url,
    [ETIQUETADOR_API_TOKEN_PROPERTY]: token
  });

  Logger.log("API configurada manualmente.");
}

function probarEtiquetadorApiPing() {
  const response = llamarEtiquetadorApi_("ping", {
    spreadsheetId: SpreadsheetApp.getActiveSpreadsheet().getId(),
    spreadsheetName: SpreadsheetApp.getActiveSpreadsheet().getName()
  });

  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function probarEtiquetadorApiEcho() {
  const response = llamarEtiquetadorApi_("echo", {
    message: "Hola desde la planilla",
    now: new Date().toISOString()
  });

  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function probarEtiquetadorApiServerInfo() {
  const response = llamarEtiquetadorApi_("serverInfo", {});
  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function probarOdooConfigCheck() {
  const response = llamarEtiquetadorApi_("odooConfigCheck", {});
  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function migrarOdooConfigLocalAApi() {
  const props = PropertiesService.getScriptProperties();
  const ui = SpreadsheetApp.getUi();
  const config = {
    ODOO_URL: props.getProperty("ODOO_URL") || "",
    ODOO_DB: props.getProperty("ODOO_DB") || "",
    ODOO_USER: props.getProperty("ODOO_USER") || "",
    ODOO_API_KEY: props.getProperty("ODOO_API_KEY") || "",
    ODOO_CIDS: props.getProperty("ODOO_CIDS") || "1"
  };

  const missing = Object.keys(config).filter(function(key) {
    return key !== "ODOO_CIDS" && !String(config[key] || "").trim();
  });

  if (missing.length) {
    throw new Error(
      "La planilla no tiene estas propiedades Odoo: " + missing.join(", ")
    );
  }

  const confirm = ui.alert(
    "Migrar configuracion Odoo",
    "Se enviara ODOO_URL, ODOO_DB, ODOO_USER y ODOO_API_KEY al Web App de Cuenta A. Continuar?",
    ui.ButtonSet.OK_CANCEL
  );

  if (confirm !== ui.Button.OK) {
    return;
  }

  const response = llamarEtiquetadorApi_("odooConfigSet", config);
  ui.alert(JSON.stringify(response, null, 2));
}

function probarOdooLoginCheck() {
  const response = llamarEtiquetadorApi_("odooLoginCheck", {});
  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function probarOdooDataProbe() {
  const response = llamarEtiquetadorApi_("odooDataProbe", {});
  SpreadsheetApp.getUi().alert(JSON.stringify(response, null, 2));
}

function llamarEtiquetadorApi_(action, payload) {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty(ETIQUETADOR_API_URL_PROPERTY);
  const token = props.getProperty(ETIQUETADOR_API_TOKEN_PROPERTY);

  if (!url || !token) {
    throw new Error(
      "API no configurada. Ejecutá configurarEtiquetadorApi() primero."
    );
  }

  const httpResponse = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      token: token,
      action: action,
      payload: payload || {}
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

function limpiarConfiguracionEtiquetadorApi() {
  const props = PropertiesService.getScriptProperties();
  props.deleteProperty(ETIQUETADOR_API_URL_PROPERTY);
  props.deleteProperty(ETIQUETADOR_API_TOKEN_PROPERTY);
  SpreadsheetApp.getUi().alert("Configuracion de API eliminada.");
}
