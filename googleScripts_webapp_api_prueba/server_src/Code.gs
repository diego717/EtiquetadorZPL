/**
 * EtiquetadorZPL Web App API - prueba minima.
 *
 * Este codigo va en un proyecto Apps Script independiente de la Cuenta A.
 * Desplegar como Web App:
 * - Execute as: Me / Yo
 * - Who has access: Anyone / Cualquiera
 *
 * La proteccion de esta prueba es un token compartido. No compartas este
 * proyecto Apps Script con la Cuenta B si queres que no vea el codigo.
 */

const API_TOKEN_PROPERTY = "ETIQUETADOR_API_TOKEN";
const API_NAME = "EtiquetadorZPL Web API";
const ODOO_CONFIG_KEYS = [
  "ODOO_URL",
  "ODOO_DB",
  "ODOO_USER",
  "ODOO_API_KEY",
  "ODOO_CIDS"
];
const ODOO_SAMPLE_LIMIT = 3;

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

    const result = routeAction_(request.action, request.payload || {});

    return json_({
      ok: true,
      action: request.action,
      result: result,
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
        message: "API funcionando desde Cuenta A",
        now: new Date().toISOString()
      };

    case "echo":
      return {
        received: payload,
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

function json_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function getSafeEmail_(user) {
  try {
    return user && user.getEmail ? user.getEmail() : "";
  } catch (err) {
    return "";
  }
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
  assertOdooConfigReady_(cfg);

  const login = getOdooLoginResult_(cfg);
  const uid = login.uid;
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
    method: login.method,
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
  assertOdooConfigReady_(cfg);
  const uid = getOdooUid_(cfg);

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
    const count = executeKw_(
      cfg,
      uid,
      options.model,
      "search_count",
      [domain],
      {}
    );
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

function getOdooCfg_() {
  const properties = PropertiesService.getScriptProperties().getProperties();

  return {
    url: cleanString_(properties.ODOO_URL).replace(/\/+$/, ""),
    cids: cleanString_(properties.ODOO_CIDS) || "1",
    db: cleanString_(properties.ODOO_DB),
    user: cleanString_(properties.ODOO_USER),
    apiKey: cleanString_(properties.ODOO_API_KEY)
  };
}

function assertOdooConfigReady_(cfg) {
  if (!cfg || !cfg.url || !cfg.db || !cfg.user || !cfg.apiKey) {
    const status = getOdooConfigStatus_();
    throw new Error(
      "Configuracion Odoo incompleta. Faltan: " + status.missing.join(", ")
    );
  }
}

function getOdooUid_(cfg) {
  return getOdooLoginResult_(cfg).uid;
}

function getOdooLoginResult_(cfg) {
  const loginResponse = rpc_(cfg.url, {
    jsonrpc: "2.0",
    method: "call",
    params: {
      service: "common",
      method: "login",
      args: [cfg.db, cfg.user, cfg.apiKey]
    },
    id: 1
  });

  if (loginResponse.result) {
    return {
      uid: loginResponse.result,
      method: "login"
    };
  }

  const authenticateResponse = rpc_(cfg.url, {
    jsonrpc: "2.0",
    method: "call",
    params: {
      service: "common",
      method: "authenticate",
      args: [cfg.db, cfg.user, cfg.apiKey, {}]
    },
    id: 1
  });

  if (authenticateResponse.result) {
    return {
      uid: authenticateResponse.result,
      method: "authenticate"
    };
  }

  throw new Error(
    "No se pudo iniciar sesion en Odoo. Revisar ODOO_DB, ODOO_USER y ODOO_API_KEY en Cuenta A. " +
      "Config actual: " +
      JSON.stringify(getOdooConfigStatus_().preview)
  );
}

function executeKw_(cfg, uid, model, method, argsList, kwargs) {
  const response = rpc_(cfg.url, {
    jsonrpc: "2.0",
    method: "call",
    params: {
      service: "object",
      method: "execute_kw",
      args: [
        cfg.db,
        uid,
        cfg.apiKey,
        model,
        method,
        argsList || [],
        kwargs || {}
      ]
    },
    id: 2
  });

  return response.result;
}

function rpc_(baseUrl, payload) {
  const response = UrlFetchApp.fetch(baseUrl + "/jsonrpc", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const responseCode = response.getResponseCode();
  const body = response.getContentText();

  if (responseCode >= 400) {
    throw new Error("HTTP " + responseCode + " al llamar a Odoo.");
  }

  let data;

  try {
    data = JSON.parse(body);
  } catch (err) {
    throw new Error("Odoo devolvio una respuesta no JSON.");
  }

  if (data.error) {
    throw new Error("Error RPC de Odoo: " + getOdooSafeError_(data.error));
  }

  return data;
}

function getOdooSafeError_(error) {
  const message =
    error &&
    error.data &&
    error.data.message
      ? error.data.message
      : error && error.message
        ? error.message
        : "Error desconocido";

  return cleanString_(message).slice(0, 300);
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

function cleanString_(value) {
  return value === null || value === undefined ? "" : String(value).trim();
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
