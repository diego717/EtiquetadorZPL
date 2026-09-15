/**
 * EtiquetadorZPL full backend Web App.
 *
 * Este archivo vive en Cuenta A junto con todos los modulos .gs del proyecto.
 * La planilla de Cuenta B llama acciones cerradas por HTTP y envia su
 * spreadsheetId. El servidor abre esa planilla con SpreadsheetApp.openById().
 */

const API_TOKEN_PROPERTY = "ETIQUETADOR_API_TOKEN";
const API_NAME = "EtiquetadorZPL Full Backend API";
const ODOO_CONFIG_KEYS = [
  "ODOO_URL",
  "ODOO_DB",
  "ODOO_USER",
  "ODOO_API_KEY",
  "ODOO_CIDS"
];
const ODOO_SAMPLE_LIMIT = 3;

var WEBAPP_RUNTIME_CONTEXT = {
  spreadsheetId: ""
};

function setupApiToken() {
  const token = Utilities.getUuid() + "-" + Utilities.getUuid();
  PropertiesService.getScriptProperties().setProperty(API_TOKEN_PROPERTY, token);
  Logger.log("API token creado: " + token);
  return token;
}

function setupOdooConfigManual() {
  const config = {
    ODOO_URL: "PEGAR_URL_ODOO",
    ODOO_DB: "PEGAR_BASE_DE_DATOS",
    ODOO_USER: "PEGAR_USUARIO_ODOO",
    ODOO_API_KEY: "PEGAR_API_KEY_ODOO",
    ODOO_CIDS: "1"
  };
  const pending = Object.keys(config).filter(function(key) {
    return String(config[key] || "").indexOf("PEGAR_") === 0;
  });

  if (pending.length) {
    throw new Error(
      "Editar setupOdooConfigManual() antes de ejecutar. Pendiente: " +
        pending.join(", ")
    );
  }

  PropertiesService.getScriptProperties().setProperties(config);
  Logger.log("Configuracion Odoo guardada para: " + maskUrl_(config.ODOO_URL));
}

function autorizarUrlFetchServidor() {
  const response = UrlFetchApp.fetch("https://www.google.com", {
    muteHttpExceptions: true
  });
  Logger.log("UrlFetch servidor autorizado. HTTP " + response.getResponseCode());
}

function doGet(e) {
  return json_({
    ok: true,
    service: API_NAME,
    message: "API online. Usar POST para acciones.",
    now: new Date().toISOString()
  });
}

function doPost(e) {
  const startedAt = Date.now();

  try {
    const request = parseRequest_(e);
    assertAuthorized_(request.token);

    const payload = request.payload || {};
    setWebAppRuntimeContext_(payload);
    const result = routeAction_(request.action, payload);

    return json_({
      ok: true,
      action: request.action,
      result: sanitizeApiResult_(result),
      elapsedMs: Date.now() - startedAt
    });
  } catch (err) {
    return json_({
      ok: false,
      error: err && err.message ? err.message : String(err),
      elapsedMs: Date.now() - startedAt
    });
  }
}

function routeAction_(action, payload) {
  switch (action) {
    case "ping":
      return {
        pong: true,
        message: "API full backend funcionando desde Cuenta A",
        now: new Date().toISOString()
      };

    case "serverInfo":
      return {
        service: API_NAME,
        timeZone: Session.getScriptTimeZone(),
        effectiveUser: getSafeEmail_(Session.getEffectiveUser()),
        activeUser: getSafeEmail_(Session.getActiveUser())
      };

    case "odooConfigCheck":
      return getOdooConfigStatus_();

    case "odooConfigSet":
      return setOdooConfigFromPayload_(payload);

    case "odooLoginCheck":
      return getOdooLoginStatus_();

    case "odooDataProbe":
      return getOdooDataProbe_();

    case "sheetAccessCheck":
      requireSpreadsheetContext_();
      return getSheetAccessStatus_();

    case "syncManufacturing":
      requireSpreadsheetContext_();
      return syncOdooManufacturingOrders();

    case "syncSales":
      requireSpreadsheetContext_();
      return syncOdooSalesOrdersNeo();

    case "syncAll":
      requireSpreadsheetContext_();
      return {
        manufacturing: syncOdooManufacturingOrders(),
        sales: syncOdooSalesOrdersNeo()
      };

    case "resetSyncState":
      requireSpreadsheetContext_();
      resetSyncState();
      return { reset: true };

    case "repairExistingSalesHiddenMetadata":
      requireSpreadsheetContext_();
      return repairExistingSalesHiddenMetadata();

    case "repairDeliveryDaysFormulas":
      requireSpreadsheetContext_();
      return repairDeliveryDaysFormulas();

    case "repairManufacturingDateValues":
      requireSpreadsheetContext_();
      return repairManufacturingDateValues();

    case "repairSalesIngressDateValues":
      requireSpreadsheetContext_();
      return repairSalesIngressDateValues();

    case "repairSalesDeliveryDateValues":
      requireSpreadsheetContext_();
      return repairSalesDeliveryDateValues();

    case "repairOperationalCheckboxes":
      requireSpreadsheetContext_();
      return repairOperationalCheckboxes();

    case "rebuildLinks":
      requireSpreadsheetContext_();
      return rebuildLinks();

    default:
      throw new Error("Accion no permitida: " + action);
  }
}

function parseRequest_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error("Request vacio. Enviar JSON por POST.");
  }

  try {
    return JSON.parse(e.postData.contents);
  } catch (err) {
    throw new Error("JSON invalido: " + err.message);
  }
}

function assertAuthorized_(token) {
  const expectedToken =
    PropertiesService.getScriptProperties().getProperty(API_TOKEN_PROPERTY);

  if (!expectedToken) {
    throw new Error("API token no configurado. Ejecutar setupApiToken().");
  }

  if (!token || token !== expectedToken) {
    throw new Error("No autorizado.");
  }
}

function setWebAppRuntimeContext_(payload) {
  WEBAPP_RUNTIME_CONTEXT = {
    spreadsheetId: cleanString_(payload && payload.spreadsheetId)
  };
}

function requireSpreadsheetContext_() {
  if (!WEBAPP_RUNTIME_CONTEXT || !WEBAPP_RUNTIME_CONTEXT.spreadsheetId) {
    throw new Error("Falta spreadsheetId en payload.");
  }
}

function getSheetAccessStatus_() {
  const spreadsheet = getApiSpreadsheet_();
  const sheet = getTargetSheet_();

  return {
    spreadsheetId: maskText_(spreadsheet.getId()),
    spreadsheetName: spreadsheet.getName(),
    targetSheet: sheet.getName(),
    lastRow: sheet.getLastRow(),
    firstAvailableRow: getFirstAvailableRow_(sheet)
  };
}

function getOdooConfigStatus_() {
  const properties = PropertiesService.getScriptProperties().getProperties();
  const missing = [];
  const present = {};

  for (const key of ODOO_CONFIG_KEYS) {
    const hasValue = Boolean(cleanString_(properties[key]));
    present[key] = hasValue;

    if (!hasValue && key !== "ODOO_CIDS") {
      missing.push(key);
    }
  }

  return {
    configured: missing.length === 0,
    missing: missing,
    present: present,
    preview: {
      url: maskUrl_(properties.ODOO_URL),
      db: maskText_(properties.ODOO_DB),
      user: maskEmail_(properties.ODOO_USER),
      cids: cleanString_(properties.ODOO_CIDS) || "1",
      apiKey: properties.ODOO_API_KEY ? "********" : ""
    }
  };
}

function setOdooConfigFromPayload_(payload) {
  const config = {
    ODOO_URL: cleanString_(payload.ODOO_URL),
    ODOO_DB: cleanString_(payload.ODOO_DB),
    ODOO_USER: cleanString_(payload.ODOO_USER),
    ODOO_API_KEY: cleanString_(payload.ODOO_API_KEY),
    ODOO_CIDS: cleanString_(payload.ODOO_CIDS) || "1"
  };
  const missing = [];

  ["ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY"].forEach(function(key) {
    if (!config[key]) {
      missing.push(key);
    }
  });

  if (missing.length) {
    throw new Error("No se guardo Odoo config. Faltan: " + missing.join(", "));
  }

  PropertiesService.getScriptProperties().setProperties(config);
  return {
    saved: true,
    preview: getOdooConfigStatus_().preview
  };
}

function getOdooLoginStatus_() {
  const cfg = getOdooCfg_();
  assertOdooConfigReadyForApi_(cfg);

  const uid = odooLogin_(cfg);
  const userRecords = executeKw_(
    cfg,
    uid,
    "res.users",
    "read",
    [[uid]],
    { fields: ["name", "login", "company_id", "company_ids"] }
  );
  const userRecord = userRecords && userRecords.length ? userRecords[0] : {};

  return {
    loginOk: true,
    uidPresent: Boolean(uid),
    uidMasked: maskText_(uid),
    odoo: getOdooConfigStatus_().preview,
    user: {
      name: maskText_(userRecord.name),
      login: maskEmail_(userRecord.login),
      company: maskMany2one_(userRecord.company_id),
      companyCount: Array.isArray(userRecord.company_ids)
        ? userRecord.company_ids.length
        : 0
    }
  };
}

function getOdooDataProbe_() {
  const cfg = getOdooCfg_();
  assertOdooConfigReadyForApi_(cfg);
  const uid = odooLogin_(cfg);

  return {
    loginOk: Boolean(uid),
    sales: probeOdooModel_(cfg, uid, {
      model: "sale.order",
      label: "Ventas",
      fields: ["name", "state", "write_date"],
      order: "write_date desc"
    }),
    manufacturing: probeOdooModel_(cfg, uid, {
      model: "mrp.production",
      label: "Fabricacion",
      fields: ["name", "origin", "state", "write_date"],
      order: "write_date desc"
    })
  };
}

function probeOdooModel_(cfg, uid, options) {
  try {
    const domain = [];
    const count = executeKw_(cfg, uid, options.model, "search_count", [domain], {});
    const records = executeKw_(
      cfg,
      uid,
      options.model,
      "search_read",
      [domain],
      {
        fields: options.fields,
        limit: ODOO_SAMPLE_LIMIT,
        order: options.order
      }
    );

    return {
      ok: true,
      model: options.model,
      label: options.label,
      count: count,
      sampleLimit: ODOO_SAMPLE_LIMIT,
      sample: (records || []).map(maskOdooRecord_)
    };
  } catch (err) {
    return {
      ok: false,
      model: options.model,
      label: options.label,
      error: err && err.message ? err.message : String(err)
    };
  }
}

function assertOdooConfigReadyForApi_(cfg) {
  if (!isOdooConfigReady_(cfg)) {
    const status = getOdooConfigStatus_();
    throw new Error(
      "Configuracion Odoo incompleta. Faltan: " + status.missing.join(", ")
    );
  }
}

function json_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function sanitizeApiResult_(value) {
  if (value === undefined) {
    return null;
  }

  return value;
}

function getSafeEmail_(user) {
  try {
    return user && user.getEmail ? user.getEmail() : "";
  } catch (err) {
    return "";
  }
}

function maskOdooRecord_(record) {
  const masked = {};

  Object.keys(record || {}).forEach(function(key) {
    const value = record[key];

    if (key === "id") {
      masked[key] = maskText_(value);
    } else if (key === "write_date") {
      masked[key] = value || "";
    } else if (Array.isArray(value)) {
      masked[key] = maskMany2one_(value);
    } else {
      masked[key] = maskText_(value);
    }
  });

  return masked;
}

function maskUrl_(value) {
  const text = cleanString_(value).replace(/\/+$/, "");
  if (!text) return "";

  const match = text.match(/^(https?:\/\/[^\/?#]+)/i);
  return match ? match[1] : maskText_(text);
}

function maskEmail_(value) {
  const text = cleanString_(value);
  const parts = text.split("@");

  if (parts.length !== 2) {
    return maskText_(text);
  }

  return maskText_(parts[0]) + "@" + parts[1];
}

function maskMany2one_(value) {
  if (!Array.isArray(value)) {
    return "";
  }

  return [maskText_(value[0]), maskText_(value[1])];
}

function maskText_(value) {
  const text = cleanString_(value);
  if (!text) return "";
  if (text.length <= 3) return "***";
  return text.slice(0, 2) + "***" + text.slice(-1);
}
