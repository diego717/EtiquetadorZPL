function rebuildLinks() {
  const sheet = getTargetSheet_();
  const lastRow = sheet.getLastRow();

  for (let row = CFG.FIRST_DATA_ROW; row <= lastRow; row++) {
    applyLinkToCell_(
      sheet.getRange(row, CFG.ORDER_COL),
      sheet.getRange(row, CFG.LINK_COL)
    );
  }

  showSpreadsheetToast_("Hipervínculos reconstruidos.");
}

/**
 * Busca la orden en Odoo y aplica el enlace correspondiente.
 */
function applyLinkToCell_(sourceCell, targetCell) {
  const text = cleanString_(sourceCell.getDisplayValue());

  if (!text) {
    targetCell.clearContent().clearNote();
    return;
  }

  const cfg = getOdooCfg_();
  let result = null;

  try {
    result = findAnythingInOdoo_(cfg, text);
  } catch (err) {
    Logger.log(
      `Error buscando "${text}" en Odoo: ${err.message || err}`
    );
  }

  const url = result
    ? buildRecordUrl_(cfg, result.id, result.model)
    : buildListUrl_(cfg, text);

  targetCell.setRichTextValue(
    buildLinkedRichText_(text, url)
  );

  targetCell.setNote(
    result
      ? `OK: Encontrado en ${getModelLabel_(result.model)} (${result.name})`
      : "No se encontró coincidencia exacta. El enlace abre la búsqueda."
  );
}

/**
 * Construye un texto enriquecido con hipervínculo.
 */
function buildLinkedRichText_(text, url) {
  const normalizedText = cleanString_(text);

  if (!normalizedText) {
    throw new Error(
      "No se puede crear un hipervínculo sin texto."
    );
  }

  return SpreadsheetApp.newRichTextValue()
    .setText(normalizedText)
    .setLinkUrl(0, normalizedText.length, url)
    .setTextStyle(0, normalizedText.length, LINK_STYLE)
    .build();
}

/**
 * Busca primero en fabricación y después en ventas.
 */
function findAnythingInOdoo_(cfg, value) {
  if (!isOdooConfigReady_(cfg)) {
    return null;
  }

  const uid = getOdooUid_(cfg);
  const models = [
    ODOO_MODELS.manufacturing,
    ODOO_MODELS.sales,
  ];

  for (const model of models) {
    const exactRecord = searchOdooRecordByCandidates_(
      cfg,
      uid,
      model,
      value
    );

    if (exactRecord) {
      return exactRecord;
    }

    const flexibleRecord = searchOdooRecordByLike_(
      cfg,
      uid,
      model,
      value
    );

    if (flexibleRecord) {
      return flexibleRecord;
    }
  }

  return null;
}

/**
 * Busca por las diferentes variantes posibles del número de orden.
 */
function searchOdooRecordByCandidates_(
  cfg,
  uid,
  model,
  value
) {
  const candidates = buildCandidatesForModel(
    value,
    model
  );

  for (const candidate of candidates) {
    const records = executeKw_(
      cfg,
      uid,
      model,
      "search_read",
      [[["name", "=", candidate]]],
      {
        fields: ["id", "name"],
        limit: 1,
      }
    );

    if (records.length > 0) {
      return toRecordRef_(records[0], model);
    }
  }

  return null;
}

/**
 * Realiza una búsqueda flexible cuando no existe coincidencia exacta.
 */
function searchOdooRecordByLike_(
  cfg,
  uid,
  model,
  value
) {
  const searchValue = cleanString_(value);

  if (!searchValue) {
    return null;
  }

  const records = executeKw_(
    cfg,
    uid,
    model,
    "search_read",
    [[["name", "ilike", searchValue]]],
    {
      fields: ["id", "name"],
      limit: 1,
      order: "id desc",
    }
  );

  return records.length > 0
    ? toRecordRef_(records[0], model)
    : null;
}

/**
 * Normaliza una respuesta de Odoo para usarla como referencia.
 */
function toRecordRef_(record, model) {
  return {
    id: record.id,
    name: cleanString_(record.name),
    model,
  };
}

/**
 * Genera las variantes posibles del número según el modelo.
 */
function buildCandidatesForModel(value, model) {
  const candidates = [];
  const seen = new Set();

  const pushCandidate = (candidate) => {
    const text = cleanString_(candidate);

    if (!text || seen.has(text)) {
      return;
    }

    seen.add(text);
    candidates.push(text);
  };

  const originalValue = cleanString_(value);
  const digits = extractTrailingDigits_(originalValue);

  pushCandidate(originalValue);

  if (!digits) {
    return candidates;
  }

  const prefixes =
    model === ODOO_MODELS.sales
      ? ["S", "SO"]
      : ["MO", "CC/MO/"];

  for (const prefix of prefixes) {
    pushCandidate(prefix + digits);
  }

  let paddedDigits = digits;

  while (paddedDigits.length < 5) {
    paddedDigits = `0${paddedDigits}`;

    for (const prefix of prefixes) {
      pushCandidate(prefix + paddedDigits);
    }
  }

  return candidates;
}

/**
 * Construye el enlace directo al formulario de un registro.
 */
function buildRecordUrl_(cfg, id, model) {
  return (
    `${cfg.url}/web#id=${encodeURIComponent(id)}` +
    `&model=${encodeURIComponent(model)}` +
    `&view_type=form` +
    `&cids=${encodeURIComponent(cfg.cids)}`
  );
}

/**
 * Construye un enlace a la lista de ventas con el valor buscado.
 */
function buildListUrl_(cfg, searchValue) {
  return (
    `${cfg.url}/web#model=${encodeURIComponent(ODOO_MODELS.sales)}` +
    `&view_type=list` +
    `&cids=${encodeURIComponent(cfg.cids)}` +
    `&search=${encodeURIComponent(searchValue)}`
  );
}

function getModelLabel_(model) {
  return model === ODOO_MODELS.sales
    ? "Ventas"
    : "Fabricación";
}