/**
 * Caché de la ejecución en curso: credenciales, UID e ids fijos de Odoo.
 *
 * Ninguno de estos valores cambia mientras corre el script, pero antes se
 * volvían a pedir en cada fila o en cada notificación. Se vacía sola al
 * terminar la ejecución, así que un cambio en Odoo se toma en la corrida
 * siguiente.
 */
var ODOO_RUNTIME_CACHE = {
  cfg: null,
  uid: 0,
  modelIds: {},
  todoActivityTypeId: 0,
};

/**
 * Inicia sesión en Odoo y devuelve el UID del usuario.
 */
function odooLogin_(cfg) {
  const response = rpc_(cfg.url, {
    jsonrpc: "2.0",
    method: "call",
    params: {
      service: "common",
      method: "login",
      args: [cfg.db, cfg.user, cfg.apiKey],
    },
    id: 1,
  });

  const uid = response.result;

  if (!uid) {
    throw new Error(
      "No se pudo iniciar sesión en Odoo. Revisá usuario, base de datos y API key."
    );
  }

  return uid;
}

/**
 * Ejecuta un método de un modelo de Odoo mediante execute_kw.
 */
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
        kwargs || {},
      ],
    },
    id: 2,
  });

  return response.result || [];
}

/**
 * Realiza una llamada JSON-RPC a Odoo.
 */
function rpc_(baseUrl, payload) {
  const response = UrlFetchApp.fetch(`${baseUrl}/jsonrpc`, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const responseCode = response.getResponseCode();
  const body = response.getContentText();

  if (responseCode >= 400) {
    throw new Error(
      `HTTP ${responseCode} al llamar a Odoo: ${body}`
    );
  }

  let data;

  try {
    data = JSON.parse(body);
  } catch (err) {
    throw new Error(
      `Odoo devolvió una respuesta que no es JSON válido: ${body}`
    );
  }

  if (data.error) {
    throw new Error(
      `Error RPC de Odoo: ${JSON.stringify(data.error)}`
    );
  }

  return data;
}

/**
 * Lee la configuración de Odoo desde las propiedades del script.
 *
 * Las credenciales no cambian durante una ejecución, así que se leen una sola
 * vez: antes rebuildLinks() y applyLinkToCell_() disparaban un
 * PropertiesService.getProperties() por cada fila procesada.
 */
function getOdooCfg_() {
  if (!ODOO_RUNTIME_CACHE.cfg) {
    const properties =
      PropertiesService.getScriptProperties().getProperties();

    ODOO_RUNTIME_CACHE.cfg = {
      url: cleanString_(properties.ODOO_URL).replace(/\/+$/, ""),
      cids: cleanString_(properties.ODOO_CIDS) || "1",
      db: cleanString_(properties.ODOO_DB),
      user: cleanString_(properties.ODOO_USER),
      apiKey: cleanString_(properties.ODOO_API_KEY),
    };
  }

  return ODOO_RUNTIME_CACHE.cfg;
}

/**
 * Comprueba que estén definidas todas las credenciales necesarias.
 */
function isOdooConfigReady_(cfg) {
  return Boolean(
    cfg &&
      cfg.url &&
      cfg.db &&
      cfg.user &&
      cfg.apiKey
  );
}

/**
 * ============================================================================
 * SESIÓN Y METADATOS CACHEADOS
 * ============================================================================
 */

/**
 * Devuelve el UID reutilizando el login de la ejecución en curso.
 *
 * Antes cada postSales*InternalNote_ hacía su propio odooLogin_, así que una
 * sincronización que finalizaba N trabajos abría N sesiones JSON-RPC.
 */
function getOdooUid_(cfg) {
  if (!ODOO_RUNTIME_CACHE.uid) {
    ODOO_RUNTIME_CACHE.uid = odooLogin_(cfg);
  }

  return ODOO_RUNTIME_CACHE.uid;
}

/**
 * ============================================================================
 * ACTIVIDADES INTERNAS (mail.activity)
 * ============================================================================
 *
 * NOTA IMPORTANTE:
 * Este flujo crea/actualiza solo actividades internas de Odoo.
 * No debe enviar correos ni usar plantillas de email. Si en el futuro se
 * agrega chatter o correo, debe ser por una ruta separada.
 */

/**
 * Escapa texto para insertarlo en el HTML de una nota de actividad.
 */
function escapeOdooHtml_(value) {
  return cleanString_(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Arma el HTML de la nota de una actividad.
 *
 * fields es una lista de pares [etiqueta, valor]; los valores vacios se
 * omiten. Cada modulo decide que campos manda y en que orden.
 */
function buildOdooActivityNoteHtml_(fields, emptyNoteHtml) {
  const noteLines = [];

  for (const field of fields || []) {
    const label = field[0];
    const value = field[1];

    if (cleanString_(value)) {
      noteLines.push(`<b>${label}:</b> ${escapeOdooHtml_(value)}`);
    }
  }

  return noteLines.length
    ? `<p>${noteLines.join("<br/>")}</p>`
    : emptyNoteHtml;
}

/**
 * Crea o actualiza una actividad "To Do" sobre un registro de Odoo.
 *
 * Si ya existe una actividad con el mismo modelo, registro, usuario, tipo y
 * resumen, la reescribe en lugar de duplicarla.
 *
 * options: { model, resId, userId, summary, noteHtml, missingMetadataError }
 * Devuelve true si creo o actualizo la actividad; false si los ids no eran
 * validos.
 */
function scheduleOdooTodoActivity_(cfg, uid, options) {
  const resId = Number(options && options.resId);
  const userId = Number(options && options.userId);

  if (
    !Number.isInteger(resId) ||
    resId <= 0 ||
    !Number.isInteger(userId) ||
    userId <= 0
  ) {
    return false;
  }

  const modelId = getOdooModelId_(cfg, uid, options.model);
  const activityTypeId = getOdooTodoActivityTypeId_(cfg, uid);

  if (!modelId || !activityTypeId) {
    throw new Error(
      options.missingMetadataError ||
        "No se pudo resolver el modelo o el tipo de actividad."
    );
  }

  const summary = options.summary;
  const existingActivities =
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "search_read",
      [[
        ["res_model_id", "=", modelId],
        ["res_id", "=", resId],
        ["user_id", "=", userId],
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
    date_deadline: nowUtcString_().slice(0, 10),
    note: options.noteHtml,
    res_id: resId,
    res_model_id: modelId,
    summary,
    user_id: userId,
  };

  if (existingActivities.length) {
    executeKw_(
      cfg,
      uid,
      "mail.activity",
      "write",
      [[Number(existingActivities[0].id)], activityValues]
    );
    return true;
  }

  executeKw_(
    cfg,
    uid,
    "mail.activity",
    "create",
    [activityValues]
  );
  return true;
}

/**
 * El tipo de actividad "To Do" es el mismo para toda la base y no cambia
 * durante la ejecución: se resuelve una vez y se reutiliza.
 */
function getOdooTodoActivityTypeId_(cfg, uid) {
  if (!ODOO_RUNTIME_CACHE.todoActivityTypeId) {
    ODOO_RUNTIME_CACHE.todoActivityTypeId = fetchOdooTodoActivityTypeId_(
      cfg,
      uid
    );
  }

  return ODOO_RUNTIME_CACHE.todoActivityTypeId;
}

function fetchOdooTodoActivityTypeId_(cfg, uid) {
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

/**
 * Resuelve el id de un modelo en ir.model, una sola vez por ejecución.
 */
function getOdooModelId_(cfg, uid, model) {
  const modelName = cleanString_(model);

  if (!modelName) {
    return 0;
  }

  if (ODOO_RUNTIME_CACHE.modelIds[modelName]) {
    return ODOO_RUNTIME_CACHE.modelIds[modelName];
  }

  const models =
    executeKw_(
      cfg,
      uid,
      "ir.model",
      "search_read",
      [[["model", "=", modelName]]],
      {
        fields: ["id"],
        limit: 1,
      }
    ) || [];

  const modelId = models.length ? Number(models[0].id) || 0 : 0;

  if (modelId) {
    ODOO_RUNTIME_CACHE.modelIds[modelName] = modelId;
  }

  return modelId;
}