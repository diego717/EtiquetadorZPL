function getImpresionVariantPreviewConfig_() {
  return {
    sheetName: "IMPRESION",
    firstDataRow: 8,
    headerRow: 3,
    linkColumn: 2,
    clientColumn: 6,
    orderColumn: 7,
    variantLookupColumn: 37,
    variantDataStartColumn: 9,
    variantDataEndColumn: 37,
    cacheTtlSeconds: 21600,
    persistentCacheFolderName: "Odoo Preview Tarjetas Cache",
  };
}

function showImpresionVariantPreviewSidebar() {
  const template = HtmlService.createTemplateFromFile(
    "impresion_variant_preview"
  );
  template.pollIntervalMs = 500;

  SpreadsheetApp.getUi().showSidebar(
    template
      .evaluate()
      .setTitle("Preview tarjeta")
  );
}

function getImpresionVariantPreviewSelectionData() {
  const summary = getImpresionVariantPreviewSelectionSummary();
  if (!summary || !summary.ok) {
    return summary;
  }

  const previewData = getImpresionVariantPreviewAsset_(
    summary.recordUrl,
    summary.variantLookupValue
  );

  return Object.assign({}, summary, {
    variantDisplayName: previewData
      ? cleanString_(previewData.displayName)
      : summary.variantDisplayName,
    variantDefaultCode: previewData
      ? cleanString_(previewData.defaultCode)
      : summary.variantDefaultCode,
    imageSrc: previewData ? cleanString_(previewData.imageSrc) : "",
    imageSource: previewData ? cleanString_(previewData.source) : "",
    message: previewData && previewData.imageSrc
      ? ""
      : summary.message,
  });
}

function getImpresionVariantPreviewSelectionSummary() {
  const cfg = getImpresionVariantPreviewConfig_();
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = spreadsheet ? spreadsheet.getActiveSheet() : null;
  const activeRange = sheet ? sheet.getActiveRange() : null;

  if (!sheet || !activeRange) {
    return {
      ok: false,
      reason: "no_selection",
      message: "No hay una seleccion activa.",
    };
  }

  if (cleanString_(sheet.getName()).toUpperCase() !== cfg.sheetName) {
    return {
      ok: false,
      reason: "wrong_sheet",
      message: 'Parate en la hoja "IMPRESION" para ver la preview.',
      sheetName: cleanString_(sheet.getName()),
    };
  }

  const row = Number(activeRange.getRow());
  const activeColumn = Number(activeRange.getColumn());
  if (!Number.isInteger(row) || row < cfg.firstDataRow) {
    return {
      ok: false,
      reason: "header_row",
      message: "Selecciona una fila operativa de IMPRESION.",
      row,
    };
  }

  const clientName = cleanString_(
    sheet.getRange(row, cfg.clientColumn).getDisplayValue()
  );
  const orderValue = cleanString_(
    sheet.getRange(row, cfg.orderColumn).getDisplayValue()
  );
  const recordUrl = getImpresionPreviewRecordUrlForRow_(sheet, row);
  const variantLookupValue = resolveImpresionVariantLookupValue_(
    sheet,
    row,
    activeColumn
  );

  if (!clientName && !variantLookupValue && !recordUrl) {
    return {
      ok: false,
      reason: "empty_row",
      message: "La fila seleccionada no tiene cliente, variante ni link.",
      row,
    };
  }

  return {
    ok: true,
    row,
    clientName,
    orderValue,
    recordUrl,
    variantLookupValue,
    variantDisplayName: variantLookupValue || "",
    variantDefaultCode: variantLookupValue || "",
    previewKey: buildImpresionVariantPreviewSelectionKey_(
      recordUrl,
      variantLookupValue
    ),
    message:
      recordUrl
        ? "Cargando preview desde cache/Odoo..."
        : variantLookupValue
          ? `Cargando preview para ${variantLookupValue}...`
          : "No se pudo resolver la variante de la fila.",
  };
}

function getImpresionVariantPreviewAsset(recordUrl, variantLookupValue) {
  const previewData = getImpresionVariantPreviewAsset_(
    recordUrl,
    variantLookupValue
  );

  if (!previewData) {
    return {
      ok: false,
      imageSrc: "",
      imageSource: "",
      variantDisplayName: cleanString_(variantLookupValue),
      variantDefaultCode: cleanString_(variantLookupValue),
      message:
        cleanString_(recordUrl)
          ? "No se encontro imagen para el producto enlazado en la columna B."
          : cleanString_(variantLookupValue)
            ? `No se encontro imagen para la variante ${variantLookupValue}.`
            : "No se pudo resolver la variante de la fila.",
    };
  }

  return {
    ok: true,
    imageSrc: cleanString_(previewData.imageSrc),
    imageSource: cleanString_(previewData.source),
    variantDisplayName: cleanString_(previewData.displayName),
    variantDefaultCode: cleanString_(previewData.defaultCode),
    message: "",
  };
}

function getImpresionVariantPreviewAsset_(recordUrl, variantLookupValue) {
  return (
    getImpresionVariantPreviewDataByRecordUrl_(recordUrl) ||
    (
      variantLookupValue
        ? getImpresionVariantPreviewDataByLookup_(variantLookupValue)
        : null
    )
  );
}

function buildImpresionVariantPreviewSelectionKey_(recordUrl, variantLookupValue) {
  return [
    cleanString_(recordUrl),
    cleanString_(variantLookupValue),
  ].join("|");
}

function getImpresionPreviewRecordUrlForRow_(sheet, row) {
  const cfg = getImpresionVariantPreviewConfig_();
  const cell = sheet.getRange(row, cfg.linkColumn);

  return extractImpresionPreviewUrlFromCell_(cell);
}

function extractImpresionPreviewUrlFromCell_(cell) {
  if (!cell) return "";

  try {
    const richTextValue = cell.getRichTextValue();
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

  const formula = cleanString_(cell.getFormula());
  const formulaMatch = formula.match(/HYPERLINK\(\s*"([^"]+)"/i);
  if (formulaMatch && formulaMatch[1]) {
    return cleanString_(formulaMatch[1]);
  }

  const displayValue = cleanString_(cell.getDisplayValue());
  const displayMatch = displayValue.match(/https?:\/\/[^\s'"]+/i);
  return displayMatch && displayMatch[0]
    ? cleanString_(displayMatch[0])
    : "";
}

function resolveImpresionVariantLookupValue_(sheet, row, activeColumn) {
  const cfg = getImpresionVariantPreviewConfig_();
  const directValue = cleanString_(
    sheet.getRange(row, cfg.variantLookupColumn).getDisplayValue()
  );
  const directCandidates = buildImpresionVariantLookupCandidates_(directValue);

  if (directCandidates.length) {
    return directCandidates[0];
  }

  if (
    Number.isInteger(activeColumn) &&
    activeColumn >= cfg.variantDataStartColumn &&
    activeColumn <= cfg.variantDataEndColumn
  ) {
    const activeColumnCandidates = getImpresionVariantCandidatesForColumn_(
      sheet,
      row,
      activeColumn
    );
    if (activeColumnCandidates.length) {
      return activeColumnCandidates[0];
    }
  }

  const inferredCandidates = getImpresionVariantCandidatesFromRow_(
    sheet,
    row
  );
  if (inferredCandidates.length) {
    return inferredCandidates[0];
  }

  const rowValues = sheet
    .getRange(row, 1, 1, Math.min(sheet.getLastColumn(), 12))
    .getDisplayValues()[0];

  for (const value of rowValues) {
    const candidates = buildImpresionVariantLookupCandidates_(value);
    if (candidates.length) {
      return candidates[0];
    }
  }

  return "";
}

function getImpresionVariantCandidatesForColumn_(sheet, row, column) {
  const cfg = getImpresionVariantPreviewConfig_();
  if (
    !sheet ||
    !Number.isInteger(column) ||
    column < cfg.variantDataStartColumn ||
    column > cfg.variantDataEndColumn
  ) {
    return [];
  }

  const headerValue = cleanString_(
    sheet.getRange(cfg.headerRow, column).getDisplayValue()
  );
  const rowValue = cleanString_(
    sheet.getRange(row, column).getDisplayValue()
  );

  if (!rowValue || rowValue === "0" || rowValue === "0.000" || rowValue === "-") {
    return [];
  }

  return buildImpresionVariantLookupCandidates_(headerValue);
}

function getImpresionVariantCandidatesFromRow_(sheet, row) {
  const cfg = getImpresionVariantPreviewConfig_();
  if (!sheet) return [];

  const lastColumn = Math.min(sheet.getLastColumn(), cfg.variantDataEndColumn);
  const firstColumn = Math.min(cfg.variantDataStartColumn, lastColumn);
  if (lastColumn < firstColumn) return [];

  const columnCount = lastColumn - firstColumn + 1;
  const headerValues = sheet
    .getRange(cfg.headerRow, firstColumn, 1, columnCount)
    .getDisplayValues()[0];
  const rowValues = sheet
    .getRange(row, firstColumn, 1, columnCount)
    .getDisplayValues()[0];

  for (let index = 0; index < rowValues.length; index++) {
    const rowValue = cleanString_(rowValues[index]);
    if (!rowValue || rowValue === "0" || rowValue === "0.000" || rowValue === "-") {
      continue;
    }

    const candidates = buildImpresionVariantLookupCandidates_(
      headerValues[index]
    );
    if (candidates.length) {
      return candidates;
    }
  }

  return [];
}

function buildImpresionVariantLookupCandidates_(value) {
  const rawValue = cleanString_(value);
  if (!rawValue) return [];

  const normalizedValue = rawValue.replace(/\s+/g, " ").trim();
  const compactValue = normalizedValue.replace(/\s+/g, "");
  const lineValues = rawValue
    .split(/\r?\n/)
    .map((part) => cleanString_(part).replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const bracketMatch = normalizedValue.match(/\[([^\]]+)\]/);
  const tokenValues = normalizedValue
    .split(/[|,/]/)
    .map((part) => cleanString_(part).replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const candidates = [];

  function pushCandidate(candidateValue) {
    const normalizedCandidate = cleanString_(candidateValue)
      .replace(/\s+/g, " ")
      .trim();
    if (!normalizedCandidate) return;
    if (!/[A-Za-z]{2,}\d|\d[A-Za-z]{2,}|NEO/i.test(normalizedCandidate)) {
      return;
    }
    if (candidates.indexOf(normalizedCandidate) === -1) {
      candidates.push(normalizedCandidate);
    }
  }

  pushCandidate(normalizedValue);
  pushCandidate(compactValue);

  for (const lineValue of lineValues) {
    pushCandidate(lineValue);
  }

  if (bracketMatch && bracketMatch[1]) {
    pushCandidate(bracketMatch[1]);
  }

  for (const tokenValue of tokenValues) {
    pushCandidate(tokenValue);
  }

  return candidates;
}

function getImpresionVariantPreviewDataByLookup_(lookupValue) {
  const cacheKey = buildImpresionVariantPreviewCacheKey_(lookupValue);
  const cached = getCachedImpresionVariantPreviewData_(cacheKey);
  if (cached) {
    return cached;
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    return null;
  }

  const uid = odooLogin_(cfg);
  const candidates = buildImpresionVariantLookupCandidates_(lookupValue);
  const product = fetchImpresionVariantRecordByCandidates_(
    cfg,
    uid,
    candidates
  );

  if (!product) {
    return null;
  }

  const imageBase64 = resolveImpresionVariantImageBase64_(
    cfg,
    uid,
    product
  );
  if (!imageBase64) {
    return null;
  }

  const payload = {
    defaultCode: cleanString_(product.default_code),
    displayName: cleanString_(product.display_name) || cleanString_(product.name),
    imageSrc: `data:image/png;base64,${imageBase64}`,
    productId: cleanString_(product.id),
    source: "odoo_variant",
  };

  saveCachedImpresionVariantPreviewData_(cacheKey, payload);
  return payload;
}

function getImpresionVariantPreviewDataByRecordUrl_(recordUrl) {
  const normalizedUrl = cleanString_(recordUrl);
  if (!normalizedUrl) return null;

  const cacheKey = buildImpresionVariantPreviewCacheKey_(
    `URL|${normalizedUrl}`
  );
  const cached = getCachedImpresionVariantPreviewData_(cacheKey);
  if (cached) {
    return cached;
  }

  const target = parseImpresionPreviewRecordTarget_(normalizedUrl);
  if (!target.model || !target.id) {
    return null;
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    return null;
  }

  const uid = odooLogin_(cfg);
  let payload = null;

  if (target.model === "product.product") {
    const products =
      executeKw_(
        cfg,
        uid,
        "product.product",
        "read",
        [[target.id]],
        {
          fields: [
            "id",
            "name",
            "display_name",
            "default_code",
            "product_tmpl_id",
            "image_128",
            "image_256",
            "image_512",
          ],
        }
      ) || [];

    if (!products.length) return null;

    const imageBase64 = resolveImpresionVariantImageBase64_(
      cfg,
      uid,
      products[0]
    );
    if (!imageBase64) return null;

    payload = {
      defaultCode: cleanString_(products[0].default_code),
      displayName:
        cleanString_(products[0].display_name) || cleanString_(products[0].name),
      imageSrc: `data:image/png;base64,${imageBase64}`,
      productId: cleanString_(products[0].id),
      source: "odoo_variant_link",
    };
  } else if (target.model === "product.template") {
    const templates =
      executeKw_(
        cfg,
        uid,
        "product.template",
        "read",
        [[target.id]],
        {
          fields: [
            "id",
            "name",
            "default_code",
            "image_128",
            "image_256",
            "image_512",
          ],
        }
      ) || [];

    if (!templates.length) return null;

    const imageBase64 =
      cleanString_(templates[0].image_256) ||
      cleanString_(templates[0].image_512) ||
      cleanString_(templates[0].image_128);
    if (!imageBase64) return null;

    payload = {
      defaultCode: cleanString_(templates[0].default_code),
      displayName: cleanString_(templates[0].name),
      imageSrc: `data:image/png;base64,${imageBase64}`,
      productId: cleanString_(templates[0].id),
      source: "odoo_template_link",
    };
  }

  if (!payload) return null;

  saveCachedImpresionVariantPreviewData_(cacheKey, payload);
  return payload;
}

function parseImpresionPreviewRecordTarget_(urlValue) {
  const url = cleanString_(urlValue);
  if (!url) {
    return { model: "", id: 0 };
  }

  const modelMatch =
    url.match(/[?#&]model=([^&#]+)/i) ||
    url.match(/\/web\/image\?model=([^&#]+)/i);
  const idMatch =
    url.match(/[?#&]id=(\d+)/i) ||
    url.match(/\/web\/image\?(?:[^#]*&)?id=(\d+)/i);

  return {
    model: modelMatch && modelMatch[1] ? cleanString_(modelMatch[1]) : "",
    id: idMatch && idMatch[1] ? Number(idMatch[1]) || 0 : 0,
  };
}

function buildImpresionVariantPreviewCacheKey_(lookupValue) {
  return (
    "IMPRESION_VARIANT_PREVIEW_V1|" +
    cleanString_(lookupValue).replace(/\s+/g, " ").trim().toUpperCase()
  );
}

function getCachedImpresionVariantPreviewData_(cacheKey) {
  if (!cacheKey) return null;

  try {
    const raw = CacheService.getScriptCache().get(cacheKey);
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    }
  } catch (err) {
  }

  const persistentPayload = getPersistentImpresionVariantPreviewData_(cacheKey);
  if (!persistentPayload) return null;

  try {
    CacheService.getScriptCache().put(
      cacheKey,
      JSON.stringify(persistentPayload),
      getImpresionVariantPreviewConfig_().cacheTtlSeconds
    );
  } catch (cacheErr) {}

  return persistentPayload;
}

function saveCachedImpresionVariantPreviewData_(cacheKey, payload) {
  if (!cacheKey || !payload) return;

  try {
    const raw = JSON.stringify(payload);
    if (raw.length > 95000) return;

    CacheService.getScriptCache().put(
      cacheKey,
      raw,
      getImpresionVariantPreviewConfig_().cacheTtlSeconds
    );
  } catch (err) {}

  savePersistentImpresionVariantPreviewData_(cacheKey, payload);
}

function fetchImpresionVariantRecordByCandidates_(cfg, uid, candidates) {
  const fields = [
    "id",
    "name",
    "display_name",
    "default_code",
    "product_tmpl_id",
    "image_128",
    "image_256",
    "image_512",
  ];

  for (const candidate of candidates || []) {
    const exactMatches =
      executeKw_(
        cfg,
        uid,
        "product.product",
        "search_read",
        [[["default_code", "=", candidate]]],
        {
          fields,
          limit: 1,
          order: "id asc",
        }
      ) || [];

    if (exactMatches.length) {
      return exactMatches[0];
    }
  }

  for (const candidate of candidates || []) {
    const ilikeMatches =
      executeKw_(
        cfg,
        uid,
        "product.product",
        "search_read",
        [[["default_code", "ilike", candidate]]],
        {
          fields,
          limit: 5,
          order: "id asc",
        }
      ) || [];

    const normalizedCandidate = normalizeAutomationText_(candidate);
    const exactNormalized = ilikeMatches.find(
      (record) =>
        normalizeAutomationText_(record.default_code) === normalizedCandidate
    );

    if (exactNormalized) {
      return exactNormalized;
    }

    if (ilikeMatches.length) {
      return ilikeMatches[0];
    }
  }

  return null;
}

function resolveImpresionVariantImageBase64_(cfg, uid, product) {
  const directImage =
    cleanString_(product && product.image_256) ||
    cleanString_(product && product.image_512) ||
    cleanString_(product && product.image_128);

  if (directImage) {
    return directImage;
  }

  const templateId = getMany2oneId_(product && product.product_tmpl_id);
  if (!templateId) return "";

  const templates =
    executeKw_(
      cfg,
      uid,
      "product.template",
      "read",
      [[templateId]],
      {
        fields: ["image_128", "image_256", "image_512"],
      }
    ) || [];

  if (!templates.length) return "";

  return (
    cleanString_(templates[0].image_256) ||
    cleanString_(templates[0].image_512) ||
    cleanString_(templates[0].image_128)
  );
}

function getPersistentImpresionVariantPreviewData_(cacheKey) {
  const folder = getImpresionVariantPreviewCacheFolder_();
  if (!folder) return null;

  const fileName = buildImpresionVariantPreviewPersistentFileName_(cacheKey);
  const files = folder.getFilesByName(fileName);
  if (!files.hasNext()) return null;

  const file = files.next();
  const metadata = parseImpresionVariantPreviewPersistentMetadata_(
    file.getDescription()
  );
  if (!metadata) return null;

  try {
    const blob = file.getBlob();
    const imageBase64 = Utilities.base64Encode(blob.getBytes());
    const mimeType =
      cleanString_(metadata.mimeType) ||
      cleanString_(blob.getContentType()) ||
      "image/png";

    return {
      defaultCode: cleanString_(metadata.defaultCode),
      displayName: cleanString_(metadata.displayName),
      imageSrc: `data:${mimeType};base64,${imageBase64}`,
      productId: cleanString_(metadata.productId),
      source: cleanString_(metadata.source) || "drive_persistent_cache",
      cachedAt: cleanString_(metadata.cachedAt),
      persistentCache: true,
    };
  } catch (err) {
    return null;
  }
}

function savePersistentImpresionVariantPreviewData_(cacheKey, payload) {
  const imageSrc = cleanString_(payload && payload.imageSrc);
  if (!cacheKey || !imageSrc) return;

  const parsedImage = parseImpresionVariantPreviewDataUrl_(imageSrc);
  if (!parsedImage.base64Data) return;

  const folder = getImpresionVariantPreviewCacheFolder_();
  if (!folder) return;

  const fileName = buildImpresionVariantPreviewPersistentFileName_(cacheKey);
  const existingFiles = folder.getFilesByName(fileName);
  while (existingFiles.hasNext()) {
    existingFiles.next().setTrashed(true);
  }

  try {
    const blob = Utilities.newBlob(
      Utilities.base64Decode(parsedImage.base64Data),
      parsedImage.mimeType || "image/png",
      fileName
    );
    const file = folder.createFile(blob);
    file.setDescription(
      JSON.stringify({
        cacheKey,
        defaultCode: cleanString_(payload.defaultCode),
        displayName: cleanString_(payload.displayName),
        productId: cleanString_(payload.productId),
        source: cleanString_(payload.source),
        mimeType: parsedImage.mimeType || "image/png",
        cachedAt: nowUtcString_(),
      })
    );
  } catch (err) {}
}

function parseImpresionVariantPreviewDataUrl_(dataUrl) {
  const rawValue = cleanString_(dataUrl);
  const match = rawValue.match(/^data:([^;]+);base64,(.+)$/i);

  return {
    mimeType: match && match[1] ? cleanString_(match[1]) : "",
    base64Data: match && match[2] ? cleanString_(match[2]) : "",
  };
}

function getImpresionVariantPreviewCacheFolder_() {
  const folderName =
    cleanString_(getImpresionVariantPreviewConfig_().persistentCacheFolderName) ||
    "Odoo Preview Tarjetas Cache";
  const folders = DriveApp.getFoldersByName(folderName);

  if (folders.hasNext()) {
    return folders.next();
  }

  try {
    return DriveApp.createFolder(folderName);
  } catch (err) {
    return null;
  }
}

function initImpresionVariantPreviewCacheFolder() {
  const folder = getImpresionVariantPreviewCacheFolder_();
  if (!folder) {
    throw new Error(
      "No se pudo crear o resolver la carpeta de caché de previews."
    );
  }

  const message =
    `Carpeta de caché lista: ${folder.getName()} ` +
    `(id=${folder.getId()})`;

  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  Logger.log(message);

  return {
    ok: true,
    folderId: folder.getId(),
    folderName: folder.getName(),
    message,
  };
}

function buildImpresionVariantPreviewPersistentFileName_(cacheKey) {
  return `preview_${buildImpresionVariantPreviewCacheDigest_(cacheKey)}.png`;
}

function buildImpresionVariantPreviewCacheDigest_(value) {
  const digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.MD5,
    cleanString_(value)
  );

  return digest
    .map((byte) => {
      const normalizedByte = byte < 0 ? byte + 256 : byte;
      return (`0${normalizedByte.toString(16)}`).slice(-2);
    })
    .join("");
}

function parseImpresionVariantPreviewPersistentMetadata_(rawValue) {
  const normalizedRawValue = cleanString_(rawValue);
  if (!normalizedRawValue) return null;

  try {
    const parsed = JSON.parse(normalizedRawValue);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (err) {
    return null;
  }
}

function clearImpresionVariantPreviewPersistentCache() {
  const folder = getImpresionVariantPreviewCacheFolder_();
  if (!folder) {
    return {
      deletedFiles: 0,
      message: "No se encontró la carpeta de caché de previews.",
    };
  }

  let deletedFiles = 0;
  const files = folder.getFiles();
  while (files.hasNext()) {
    files.next().setTrashed(true);
    deletedFiles++;
  }

  const message =
    `Caché persistente de previews limpiada. Archivos eliminados: ${deletedFiles}.`;
  try {
    showSpreadsheetToast_(message);
  } catch (err) {}

  return {
    deletedFiles,
    message,
  };
}
