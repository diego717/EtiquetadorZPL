/**
 * ============================================================================
 * SINCRONIZACIÓN DE ÓRDENES DE FABRICACIÓN
 * ============================================================================
 *
 * La columna R guarda el ID interno de mrp.production.
 * Una fabricación ausente se consulta dos veces dentro de la misma
 * sincronización antes de que su fila sea limpiada.
 */

function getManufacturingIdColumn_() {
  return CFG.MFG_ID_COL || 18;
}

function buildArchivedManufacturingRowKeys_(odooId, orderKeys) {
  const keys = [];

  if (cleanString_(odooId)) {
    keys.push(`id:${cleanString_(odooId)}`);
  }

  for (const orderKey of orderKeys || []) {
    if (orderKey) {
      keys.push(`order:${orderKey}`);
    }
  }

  return keys;
}

function stripManufacturingPartialSuffix_(value) {
  const text = cleanString_(value);
  if (!text) return "";

  return cleanString_(text.replace(/-\d{3}\s*$/i, ""));
}

function resolveManufacturingPendingQuantity_(record) {
  const plannedQuantity = normalizeQuantity_(record && record.product_qty);
  if (plannedQuantity === null) return null;

  const producedQuantity = normalizeQuantity_(record && record.qty_produced);
  if (producedQuantity === null) {
    return plannedQuantity;
  }

  return Math.max(0, plannedQuantity - producedQuantity);
}

function extractManufacturingReferenceFromNote_(noteValue) {
  const note = cleanString_(noteValue);
  const match = note.match(/MO:\s*([^|\n]+)/i);
  return match && match[1] ? cleanString_(match[1]) : "";
}

function isManufacturingRowSnapshot_(
  richTextValue,
  noteValue,
  formulaValue,
  displayValue
) {
  const url = getManufacturingSnapshotUrl_(
    richTextValue,
    noteValue,
    formulaValue,
    displayValue
  ).toLowerCase();

  if (url.indexOf("model=mrp.production") !== -1) return true;

  const note = cleanString_(noteValue).toLowerCase();
  return (
    note.indexOf("fabric") !== -1 ||
    note.indexOf("mrp.production") !== -1
  );
}

function getManufacturingHistoryRowKeysCacheProperty_() {
  return "ODOO_MFG_HISTORY_ROW_KEYS_CACHE_PAYLOAD_V1";
}

function getManufacturingHistoryRowKeysCacheServiceKey_() {
  return "ODOO_MFG_HISTORY_ROW_KEYS_CACHE_PAYLOAD_V1";
}

function clearManufacturingHistoryRowKeysCache_() {
  const properties = PropertiesService.getScriptProperties();
  properties.deleteProperty(getManufacturingHistoryRowKeysCacheProperty_());

  try {
    CacheService.getScriptCache().remove(
      getManufacturingHistoryRowKeysCacheServiceKey_()
    );
  } catch (err) {}
}

function buildManufacturingHistoryRowKeysCacheSignature_(historySheet, rowCount) {
  if (!historySheet || !rowCount) return "empty";

  const sampleCount = Math.min(5, rowCount);
  const sampleOrderValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, sampleCount, 1)
    .getDisplayValues()
    .map((row) => cleanString_(row[0]));
  const sampleLinkNotes = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.LINK_COL, sampleCount, 1)
    .getNotes()
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
      cleanString_(row[0]),
      cleanString_(row[1]),
      cleanString_(row[2]),
      cleanString_(row[3]),
    ]);

  return JSON.stringify({
    rowCount,
    sampleOrderValues,
    sampleLinkNotes,
    sampleMetadataValues,
  });
}

function parseManufacturingHistoryRowKeysCachePayload_(rawValue) {
  try {
    const parsed = JSON.parse(rawValue);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (err) {
    return null;
  }
}

function getCachedManufacturingHistoryRowKeys_(cacheSignature) {
  if (!cacheSignature) {
    return { keySet: null, source: "missing_signature" };
  }

  const cacheSources = [];

  try {
    cacheSources.push({
      source: "script_cache",
      raw: CacheService.getScriptCache().get(
        getManufacturingHistoryRowKeysCacheServiceKey_()
      ),
    });
  } catch (err) {}

  cacheSources.push({
    source: "script_properties",
    raw: PropertiesService.getScriptProperties().getProperty(
      getManufacturingHistoryRowKeysCacheProperty_()
    ),
  });

  for (const cacheSource of cacheSources) {
    if (!cacheSource.raw) continue;

    const payload = parseManufacturingHistoryRowKeysCachePayload_(
      cacheSource.raw
    );
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

function saveCachedManufacturingHistoryRowKeys_(cacheSignature, archivedKeys) {
  const payload = JSON.stringify({
    signature: cleanString_(cacheSignature),
    keys: Array.from(archivedKeys || []),
  });

  PropertiesService.getScriptProperties().setProperty(
    getManufacturingHistoryRowKeysCacheProperty_(),
    payload
  );

  try {
    CacheService.getScriptCache().put(
      getManufacturingHistoryRowKeysCacheServiceKey_(),
      payload,
      21600
    );
  } catch (err) {}
}

function getManufacturingSnapshotFlagsForSheet_(sheet, rowCount) {
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
    isManufacturingRowSnapshot_(
      rowValue[0],
      notes[index][0],
      formulas[index][0],
      displayValues[index][0]
    )
  );
}

function buildManufacturingSheetSnapshot_(sheet) {
  const rowCount = getSheetOperationalRowCount_(sheet);

  if (!sheet || !rowCount) {
    return {
      sheet,
      rowCount: 0,
      orderValues: [],
      linkNoteValues: [],
      stateValues: [],
      metadataValues: [],
      manufacturingSnapshotFlags: [],
    };
  }

  return {
    sheet,
    rowCount,
    orderValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
      .getDisplayValues(),
    linkNoteValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, CFG.LINK_COL, rowCount, 1)
      .getNotes(),
    stateValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, CFG.STATE_COL, rowCount, 1)
      .getDisplayValues(),
    metadataValues: sheet
      .getRange(CFG.FIRST_DATA_ROW, getManufacturingIdColumn_(), rowCount, 4)
      .getDisplayValues(),
    manufacturingSnapshotFlags: getManufacturingSnapshotFlagsForSheet_(
      sheet,
      rowCount
    ),
  };
}

/**
 * Convierte las fechas de inicio y entrega de fabricación que hayan quedado
 * como texto a valores Date reales. Así cumplen la validación de fecha de
 * la planilla y se siguen viendo como "3-ago" o "22-jul".
 */
function repairManufacturingDateValues() {
  const sheet = getTargetSheet_();
  const snapshot = buildManufacturingSheetSnapshot_(sheet);
  let repairedCells = 0;

  if (!snapshot.rowCount) {
    showSpreadsheetToast_("No hay filas de fabricación para reparar.");
    return {
      repairedCells: 0,
      message: "No hay filas de fabricación para reparar.",
    };
  }

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (!snapshot.manufacturingSnapshotFlags[index]) continue;

    const row = CFG.FIRST_DATA_ROW + index;
    for (const column of [7, 8]) {
      const dateCell = sheet.getRange(row, column);
      const currentValue = dateCell.getValue();

      if (currentValue instanceof Date && !Number.isNaN(currentValue.getTime())) {
        dateCell.setNumberFormat("d-mmm");
        continue;
      }

      const parsedDate = parseSalesSheetDateValue_(
        dateCell.getDisplayValue()
      );
      if (!parsedDate) continue;

      dateCell.setValue(parsedDate);
      dateCell.setNumberFormat("d-mmm");
      repairedCells++;
    }
  }

  const message =
    repairedCells > 0
      ? `Fechas de fabricación reparadas en ${repairedCells} celda(s).`
      : "No se encontraron fechas de fabricación para reparar.";

  showSpreadsheetToast_(message);

  return {
    repairedCells,
    message,
  };
}

function getManufacturingRowsWithoutOriginIndexes_(metadataValues) {
  const indexes = [];

  for (let index = 0; index < (metadataValues || []).length; index++) {
    if (!cleanString_(metadataValues[index][3])) {
      indexes.push(index);
    }
  }

  return indexes;
}

function getManufacturingSnapshotFlagsForRowIndexes_(sheet, rowIndexes) {
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
      flags[firstIndex + offset] = isManufacturingRowSnapshot_(
        richTextValues[offset][0],
        notes[offset][0],
        formulas[offset][0],
        displayValues[offset][0]
      );
    }
  }

  return flags;
}

function buildActiveArchivedManufacturingIndex_(sheetSnapshot) {
  const archivedRowKeys = new Set();
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet
      ? sheetSnapshot
      : buildManufacturingSheetSnapshot_(getTargetSheet_());

  if (!snapshot.rowCount) {
    return {
      rowKeys: archivedRowKeys,
      rowCount: 0,
    };
  }

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (cleanString_(snapshot.stateValues[index][0]) !== "Archivar") continue;

    const origin = cleanString_(snapshot.metadataValues[index][3]).toUpperCase();
    if (origin && origin !== "FABRICACION") continue;
    if (!origin && !snapshot.manufacturingSnapshotFlags[index]) continue;

    const odooId = cleanString_(snapshot.metadataValues[index][0]);
    const orderKeys = buildManufacturingOrderKeys_(
      extractManufacturingReferenceFromNote_(
        snapshot.linkNoteValues[index][0]
      ),
      cleanString_(snapshot.orderValues[index][0])
    );

    for (const key of buildArchivedManufacturingRowKeys_(odooId, orderKeys)) {
      archivedRowKeys.add(key);
    }
  }

  return {
    rowKeys: archivedRowKeys,
    rowCount: snapshot.rowCount,
  };
}

function getExistingManufacturingOrderRowMap_(sheet, sheetSnapshot) {
  const map = new Map();
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet === sheet
      ? sheetSnapshot
      : buildManufacturingSheetSnapshot_(sheet);

  if (!snapshot.rowCount) return map;

  for (let index = 0; index < snapshot.rowCount; index++) {
    if (cleanString_(snapshot.stateValues[index][0]) === "Archivar") continue;

    const origin = cleanString_(snapshot.metadataValues[index][3]).toUpperCase();
    if (origin && origin !== "FABRICACION") continue;
    if (!origin && !snapshot.manufacturingSnapshotFlags[index]) continue;

    const row = CFG.FIRST_DATA_ROW + index;
    const orderKeys = buildManufacturingOrderKeys_(
      extractManufacturingReferenceFromNote_(
        snapshot.linkNoteValues[index][0]
      ),
      cleanString_(snapshot.orderValues[index][0])
    );

    for (const key of orderKeys) {
      if (!map.has(key)) {
        map.set(key, row);
      }
    }
  }

  return map;
}

function getManufacturingHistoryRowKeys_() {
  const archivedKeys = new Set();
  const historySheet = getJobsHistorySheet_();
  const rowCount = getSheetOperationalRowCount_(historySheet);

  if (!historySheet || !rowCount) {
    clearManufacturingHistoryRowKeysCache_();
    return archivedKeys;
  }

  const cacheSignature = buildManufacturingHistoryRowKeysCacheSignature_(
    historySheet,
    rowCount
  );
  const cachedHistoryRowKeys = getCachedManufacturingHistoryRowKeys_(
    cacheSignature
  );
  if (cachedHistoryRowKeys.keySet) {
    return cachedHistoryRowKeys.keySet;
  }

  const metadataValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, getManufacturingIdColumn_(), rowCount, 4)
    .getDisplayValues();
  const orderValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, rowCount, 1)
    .getDisplayValues();
  const linkNoteValues = historySheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.LINK_COL, rowCount, 1)
    .getNotes();
  const rowsWithoutOrigin = getManufacturingRowsWithoutOriginIndexes_(
    metadataValues
  );
  const manufacturingSnapshotFlagsByIndex =
    getManufacturingSnapshotFlagsForRowIndexes_(historySheet, rowsWithoutOrigin);

  for (let index = 0; index < rowCount; index++) {
    const origin = cleanString_(metadataValues[index][3]).toUpperCase();
    if (origin && origin !== "FABRICACION") continue;
    if (!origin && !manufacturingSnapshotFlagsByIndex[index]) continue;

    const odooId = cleanString_(metadataValues[index][0]);
    const orderKeys = buildManufacturingOrderKeys_(
      extractManufacturingReferenceFromNote_(linkNoteValues[index][0]),
      cleanString_(orderValues[index][0])
    );

    for (const key of buildArchivedManufacturingRowKeys_(odooId, orderKeys)) {
      archivedKeys.add(key);
    }
  }

  saveCachedManufacturingHistoryRowKeys_(cacheSignature, archivedKeys);
  return archivedKeys;
}

function getActiveArchivedManufacturingRowKeys_(
  sheetSnapshot,
  archivedManufacturingIndex
) {
  const snapshot =
    sheetSnapshot && sheetSnapshot.sheet
      ? sheetSnapshot
      : buildManufacturingSheetSnapshot_(getTargetSheet_());
  const activeArchivedManufacturingIndex =
    archivedManufacturingIndex || buildActiveArchivedManufacturingIndex_(snapshot);

  if (!snapshot.sheet || !snapshot.rowCount) {
    return activeArchivedManufacturingIndex.rowKeys;
  }

  return activeArchivedManufacturingIndex.rowKeys;
}

function getArchivedManufacturingRowKeys_(sheetSnapshot, archivedManufacturingIndex) {
  const archivedKeys = getManufacturingHistoryRowKeys_();

  for (const key of getActiveArchivedManufacturingRowKeys_(
    sheetSnapshot,
    archivedManufacturingIndex
  )) {
    archivedKeys.add(key);
  }

  return archivedKeys;
}

function isArchivedManufacturingRow_(archivedKeys, odooId, orderKeys) {
  for (const key of buildArchivedManufacturingRowKeys_(odooId, orderKeys)) {
    if (archivedKeys.has(key)) {
      return true;
    }
  }

  return false;
}

function syncOdooManufacturingOrders() {
  const sheet = getTargetSheet_();
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  appendSyncLog_({
    module: "FABRICACION",
    action: "sync_start",
    details: "Inicio de sincronización de fabricación.",
  });

  const uid = odooLogin_(cfg);
  const properties = PropertiesService.getScriptProperties();
  const importedIds = getImportedIds_();
  const manufacturingFinalizationNotifiedKeys =
    getManufacturingFinalizationNotifiedKeys_();
  const reconciliation = reconcileDeletedManufacturingOrders_(
    sheet,
    cfg,
    uid,
    manufacturingFinalizationNotifiedKeys
  );
  const activeSheetSnapshot = buildManufacturingSheetSnapshot_(sheet);
  const activeArchivedManufacturingIndex =
    buildActiveArchivedManufacturingIndex_(activeSheetSnapshot);
  const archivedManufacturingRowKeys = getArchivedManufacturingRowKeys_(
    activeSheetSnapshot,
    activeArchivedManufacturingIndex
  );

  for (const deletedId of reconciliation.deletedIds) {
    importedIds.delete(deletedId);
  }

  const existingOrderRowMap = getExistingManufacturingOrderRowMap_(
    sheet,
    activeSheetSnapshot
  );
  const fromDate = daysAgoUtcString_(MFG_CFG.LOOKBACK_DAYS);
  const synchronizedStates = MFG_CFG.ALLOWED_STATES.concat(["cancel"]);
  const records =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.manufacturing,
      "search_read",
      [[
        ["write_date", ">=", fromDate],
        ["state", "in", synchronizedStates],
      ]],
      {
        fields: [
          "id",
          "name",
          "origin",
          "product_id",
          "product_qty",
          "qty_produced",
          "create_date",
          "write_date",
          "date_start",
          "state",
          "user_id",
        ],
        order: "write_date asc, id asc",
      }
    ) || [];
  const salesOrderNamesByOrigin = fetchSalesOrderNamesByManufacturingOrigins_(
    cfg,
    uid,
    records
  );
  const noteCandidateIds = records
    .filter((record) => {
      const odooId = Number(cleanString_(record && record.id));
      return (
        Number.isInteger(odooId) &&
        odooId > 0 &&
        cleanString_(record && record.state).toLowerCase() !== "cancel"
      );
    })
    .map((record) => Number(record.id));
  const latestNotesByManufacturingId = fetchLatestManufacturingNotesMap_(
    cfg,
    uid,
    noteCandidateIds
  );

  let inserted = 0;
  let updated = 0;
  let unchanged = 0;
  let removed = reconciliation.removedRows;
  let needsAutoSort = reconciliation.removedRows > 0;
  let nextRow = getFirstAvailableRow_(sheet);
  let manufacturingFinalizationNotificationsChanged = Boolean(
    reconciliation.notificationsChanged
  );

  for (const record of records) {
    const odooId = cleanString_(record.id);
    const rawOrderName = cleanString_(record.name);
    const displayOrder = resolveManufacturingDisplayOrder_(
      record,
      salesOrderNamesByOrigin
    );
    const orderKeys = buildManufacturingOrderKeys_(
      rawOrderName,
      displayOrder
    );
    const currentState = cleanString_(record.state).toLowerCase();

    if (!odooId) {
      continue;
    }

    // Una orden que coincide con el histórico se deja reingresar (por
    // ejemplo, cuando el chatter recibe una nota nueva de fecha/estado),
    // pero se reingresa con la fecha del día, no con record.date_start,
    // que puede quedar viejo para ítems genéricos/recurrentes.
    const isReactivatedFromArchive = isArchivedManufacturingRow_(
      archivedManufacturingRowKeys,
      odooId,
      orderKeys
    );

    const existingRow = findExistingManufacturingRow_(
      existingOrderRowMap,
      orderKeys
    );

    if (currentState === "cancel") {
      if (existingRow) {
        if (
          clearManufacturingFinalizationNotificationKeysForRows_(
            sheet,
            [existingRow],
            manufacturingFinalizationNotifiedKeys
          )
        ) {
          manufacturingFinalizationNotificationsChanged = true;
        }
        clearManufacturingRow_(sheet, existingRow);
        removeManufacturingRowKeys_(existingOrderRowMap, orderKeys);
        removed++;
        needsAutoSort = true;
        nextRow = getFirstAvailableRow_(sheet);
        appendSyncLog_({
          module: "FABRICACION",
          action: "delete",
          order: displayOrder,
          odooId,
          origin: "FABRICACION",
          details: "Orden cancelada eliminada de la planilla.",
        });
      }

      importedIds.delete(odooId);
      continue;
    }

    const productName = getMany2oneName_(record.product_id);
    const quantity = resolveManufacturingPendingQuantity_(record);

    if (!productName || quantity === null) {
      logDebug_(
        `Fabricación omitida por datos incompletos: ` +
          `id=${odooId} producto=${productName} cantidad=${quantity}`
      );
      appendSyncLog_({
        module: "FABRICACION",
        action: "skip",
        order: displayOrder,
        odooId,
        origin: "FABRICACION",
        details: "Datos incompletos para importar fabricación.",
      });
      continue;
    }

    const wasExisting = Boolean(existingRow);
    let targetRow = existingRow;

    if (!targetRow) {
      targetRow = findNextAvailableManufacturingRowFrom_(sheet, nextRow);
      if (targetRow) {
        nextRow = targetRow + 1;
      }
    }

    if (!targetRow) {
      Logger.log(
        `No hay fila libre para la fabricación ${displayOrder} (id=${odooId})`
      );
      appendSyncLog_({
        module: "FABRICACION",
        action: "skip",
        order: displayOrder,
        odooId,
        origin: "FABRICACION",
        details: "No hay fila libre en la planilla.",
      });
      continue;
    }

    const numericId = Number(odooId);
    const noteInfo =
      latestNotesByManufacturingId.has(odooId)
        ? latestNotesByManufacturingId.get(odooId)
        : typeof parseManufacturingNote_ === "function"
          ? { date: "", state: "", customerName: "" }
          : Number.isInteger(numericId) && numericId > 0
            ? extractLatestManufacturingNote_(cfg, uid, numericId)
            : { date: "", state: "", customerName: "" };

    const writeResult = writeManufacturingRow_(sheet, targetRow, {
      cfg,
      odooId,
      displayOrder,
      rawOrderName,
      matchedResponsible: findResponsible_(
        getMany2oneName_(record.user_id)
      ),
      productName,
      quantity,
      startDateFormatted:
        isReactivatedFromArchive && !wasExisting
          ? formatDateForSheet_(new Date())
          : formatDateForSheet_(record.date_start),
      noteDateFormatted: noteInfo.date,
      noteState: noteInfo.state,
      customerName: noteInfo.customerName,
      currentState: record.state,
    });

    if (!wasExisting) {
      markRowAsNew_(sheet, targetRow);
      inserted++;
      needsAutoSort = true;
      appendSyncLog_({
        module: "FABRICACION",
        action: "insert",
        order: displayOrder,
        odooId,
        origin: "FABRICACION",
        details:
          `Fila ${targetRow} creada. ` +
          `reactivatedFromHistory=${isReactivatedFromArchive}`,
      });
    } else {
      if (writeResult && writeResult.hasVisibleChanges) {
        updated++;
      } else {
        unchanged++;
      }
      if (writeResult && writeResult.requiresResort) {
        needsAutoSort = true;
      }
      if (writeResult && writeResult.hasVisibleChanges) {
        appendSyncLog_({
          module: "FABRICACION",
          action: "update",
          order: displayOrder,
          odooId,
          origin: "FABRICACION",
          details: `Fila ${targetRow} actualizada.`,
        });
      }
    }

    importedIds.add(odooId);

    setManufacturingRowKeys_(existingOrderRowMap, orderKeys, targetRow);
  }

  saveImportedIds_(importedIds);
  if (manufacturingFinalizationNotificationsChanged) {
    saveManufacturingFinalizationNotifiedKeys_(
      manufacturingFinalizationNotifiedKeys
    );
  }
  properties.setProperty(MFG_CFG.LAST_SYNC_PROPERTY, nowUtcString_());

  if (needsAutoSort) {
    SpreadsheetApp.flush();
    ejecutarOrdenadoAutomatico();
  }

  showSpreadsheetToast_(
    `Sincronización fabricación OK. Nuevas: ${inserted} | ` +
      `Actualizadas: ${updated} | Sin cambios: ${unchanged} | Eliminadas: ${removed}`
  );

  appendSyncLog_({
    module: "FABRICACION",
    action: "sync_end",
    details:
      `Nuevas=${inserted}; Actualizadas=${updated}; ` +
      `SinCambios=${unchanged}; Eliminadas=${removed}.`,
  });
  flushSyncLogBuffer_();

  return { inserted, updated, removed };
}

function chunkManufacturingValues_(values, chunkSize) {
  const chunks = [];
  const safeChunkSize = Math.max(1, Number(chunkSize) || 1);

  for (let index = 0; index < values.length; index += safeChunkSize) {
    chunks.push(values.slice(index, index + safeChunkSize));
  }

  return chunks;
}

function parseManufacturingNoteInfoFromMessage_(message) {
  const rawBody =
    message && Object.prototype.hasOwnProperty.call(message, "body")
      ? message.body
      : "";
  const bodyText =
    typeof normalizeMessageBody_ === "function"
      ? normalizeMessageBody_(rawBody)
      : cleanString_(rawBody);

  if (!bodyText || typeof parseManufacturingNote_ !== "function") {
    return { date: "", state: "", customerName: "" };
  }

  const parsed = parseManufacturingNote_(rawBody);
  return parsed && (parsed.date || parsed.state || parsed.customerName)
    ? {
        date: cleanString_(parsed.date),
        state: cleanString_(parsed.state),
        customerName: cleanString_(parsed.customerName),
      }
    : { date: "", state: "", customerName: "" };
}

function fetchLatestManufacturingNotesMap_(cfg, uid, manufacturingIds) {
  const normalizedManufacturingIds = Array.from(
    new Set(
      (manufacturingIds || [])
        .map((manufacturingId) => Number(manufacturingId))
        .filter(
          (manufacturingId) =>
            Number.isInteger(manufacturingId) && manufacturingId > 0
        )
    )
  );
  const notesByManufacturingId = new Map();
  const latestDetectedStateByManufacturingId = new Map();
  const latestDetectedCustomerByManufacturingId = new Map();

  if (!normalizedManufacturingIds.length) {
    return notesByManufacturingId;
  }

  if (typeof parseManufacturingNote_ !== "function") {
    return notesByManufacturingId;
  }

  for (const idsChunk of chunkManufacturingValues_(normalizedManufacturingIds, 80)) {
    let offset = 0;
    const pageSize = 200;
    const unresolvedIds = new Set(idsChunk.map((id) => String(id)));

    while (unresolvedIds.size > 0) {
      const messages =
        executeKw_(
          cfg,
          uid,
          ODOO_MODELS.chatter,
          "search_read",
          [[
            ["model", "=", ODOO_MODELS.manufacturing],
            ["res_id", "in", idsChunk],
          ]],
          {
            fields: ["id", "res_id", "date", "subject", "body"],
            order: "date desc, id desc",
            limit: pageSize,
            offset,
          }
        ) || [];

      if (!messages.length) break;

      for (const message of messages) {
        const manufacturingId = Number(message.res_id);
        if (!Number.isInteger(manufacturingId) || manufacturingId <= 0) {
          continue;
        }

        const manufacturingIdKey = String(manufacturingId);
        if (notesByManufacturingId.has(manufacturingIdKey)) continue;

        const parsed = parseManufacturingNoteInfoFromMessage_(message);

        if (
          parsed.state &&
          !latestDetectedStateByManufacturingId.has(manufacturingIdKey)
        ) {
          latestDetectedStateByManufacturingId.set(
            manufacturingIdKey,
            parsed.state
          );
        }

        if (
          parsed.customerName &&
          !latestDetectedCustomerByManufacturingId.has(manufacturingIdKey)
        ) {
          latestDetectedCustomerByManufacturingId.set(
            manufacturingIdKey,
            parsed.customerName
          );
        }

        if (!parsed.date) continue;

        notesByManufacturingId.set(manufacturingIdKey, {
          date: parsed.date,
          state:
            parsed.state ||
            latestDetectedStateByManufacturingId.get(manufacturingIdKey) ||
            "",
          customerName:
            parsed.customerName ||
            latestDetectedCustomerByManufacturingId.get(
              manufacturingIdKey
            ) ||
            "",
        });
        unresolvedIds.delete(manufacturingIdKey);
      }

      if (messages.length < pageSize) break;
      offset += messages.length;
    }
  }

  return notesByManufacturingId;
}

function getManufacturingStateRank_(stateValue) {
  const state = cleanString_(stateValue);
  const ranks = {
    Cotizar: 0,
    Muestra: 0,
    Aprobar: 0,
    Archivar: 0,
    Empezar: 1,
    Procesando: 2,
    Finalizado: 3,
  };

  return Object.prototype.hasOwnProperty.call(ranks, state)
    ? ranks[state]
    : null;
}

function shouldAdvanceManufacturingState_(
  existingStateValue,
  candidateStateValue
) {
  const candidateRank = getManufacturingStateRank_(candidateStateValue);
  if (candidateRank === null) return false;

  const existingState = cleanString_(existingStateValue);
  if (!existingState) return true;

  const existingRank = getManufacturingStateRank_(existingState);
  if (existingRank === null) return false;

  return candidateRank > existingRank;
}

function findNextAvailableManufacturingRowFrom_(sheet, nextRow) {
  if (typeof findNextAvailableRowFrom_ === "function") {
    return findNextAvailableRowFrom_(sheet, nextRow);
  }

  return getFirstAvailableRow_(sheet);
}

function writeManufacturingRow_(sheet, row, data) {
  const detailValues = sheet.getRange(row, 1, 1, 9).getDisplayValues()[0];
  const originalResponsibleValue = cleanString_(detailValues[0]);
  const originalOrderValue = cleanString_(detailValues[1]);
  const originalCustomerValue = cleanString_(detailValues[3]);
  const originalProductValue = cleanString_(detailValues[4]);
  const originalQuantityValue = cleanString_(detailValues[5]);
  const originalStartDateValue = cleanString_(detailValues[6]);
  const originalNoteDateValue = cleanString_(detailValues[7]);
  const originalStateValue = cleanString_(detailValues[8]);
  const parsedStartDateValue = parseSalesSheetDateValue_(
    data.startDateFormatted
  );
  const parsedNoteDateValue = parseSalesSheetDateValue_(
    data.noteDateFormatted
  );
  const stateValue = mapManufacturingStateToSheetValue_(
    data.noteState || data.currentState
  );
  const resolvedStateValue =
    shouldAdvanceManufacturingState_(originalStateValue, stateValue) ||
    !originalStateValue
      ? stateValue || originalStateValue
      : originalStateValue;
  const rowValues = [[
    data.matchedResponsible || originalResponsibleValue,
    data.displayOrder || "",
    data.displayOrder || "",
    data.customerName || originalCustomerValue,
    data.productName || originalProductValue,
    data.quantity,
    parsedStartDateValue || data.startDateFormatted || "",
    parsedNoteDateValue || data.noteDateFormatted || originalNoteDateValue,
    resolvedStateValue || "",
  ]];

  sheet.getRange(row, 1, 1, 9).setValues(rowValues);

  if (parsedStartDateValue) {
    sheet.getRange(row, 7).setNumberFormat("d-mmm");
  }

  if (parsedNoteDateValue) {
    sheet.getRange(row, 8).setNumberFormat("d-mmm");
  }

  sheet.getRange(row, CFG.LINK_COL).setRichTextValue(
    buildLinkedRichText_(
      data.displayOrder,
      buildRecordUrl_(
        data.cfg,
        data.odooId,
        ODOO_MODELS.manufacturing
      )
    )
  );
  sheet.getRange(row, CFG.LINK_COL).setNote(
    `OK: Fabricacion (${data.displayOrder}) | MO: ${data.rawOrderName || data.displayOrder}`
  );

  const metadataValues = [[
    String(data.odooId),
    "",
    "",
    "FABRICACION",
  ]];
  sheet
    .getRange(row, getManufacturingIdColumn_(), 1, 4)
    .setValues(metadataValues);
  ensureDeliveryDaysFormula_(sheet, row);

  const resultingResponsibleValue = cleanString_(rowValues[0][0]);
  const resultingOrderValue = cleanString_(rowValues[0][1]);
  const resultingCustomerValue = cleanString_(rowValues[0][3]);
  const resultingProductValue = cleanString_(rowValues[0][4]);
  const resultingQuantityValue = cleanString_(rowValues[0][5]);
  const resultingStartDateValue = cleanString_(rowValues[0][6]);
  const resultingNoteDateValue = cleanString_(rowValues[0][7]);
  const resultingStateValue = cleanString_(rowValues[0][8]);
  const hasVisibleChanges =
    normalizeSalesComparableText_(resultingResponsibleValue) !==
      normalizeSalesComparableText_(originalResponsibleValue) ||
    normalizeSalesComparableText_(resultingOrderValue) !==
      normalizeSalesComparableText_(originalOrderValue) ||
    normalizeSalesComparableText_(resultingCustomerValue) !==
      normalizeSalesComparableText_(originalCustomerValue) ||
    normalizeSalesComparableText_(resultingProductValue) !==
      normalizeSalesComparableText_(originalProductValue) ||
    normalizeSalesComparableQuantity_(resultingQuantityValue) !==
      normalizeSalesComparableQuantity_(originalQuantityValue) ||
    normalizeSalesComparableDateDisplay_(resultingStartDateValue) !==
      normalizeSalesComparableDateDisplay_(originalStartDateValue) ||
    normalizeSalesComparableDateDisplay_(resultingNoteDateValue) !==
      normalizeSalesComparableDateDisplay_(originalNoteDateValue) ||
    normalizeSalesComparableText_(resultingStateValue) !==
      normalizeSalesComparableText_(originalStateValue);

  return {
    previousStateValue: originalStateValue,
    resultingStateValue,
    hasVisibleChanges,
    requiresResort:
      normalizeSalesComparableText_(resultingResponsibleValue) !==
        normalizeSalesComparableText_(originalResponsibleValue) ||
      normalizeSalesComparableText_(resultingOrderValue) !==
        normalizeSalesComparableText_(originalOrderValue) ||
      normalizeSalesComparableText_(resultingCustomerValue) !==
        normalizeSalesComparableText_(originalCustomerValue) ||
      normalizeSalesComparableText_(resultingProductValue) !==
        normalizeSalesComparableText_(originalProductValue) ||
      normalizeSalesComparableText_(resultingStateValue) !==
        normalizeSalesComparableText_(originalStateValue),
  };
}

function reconcileDeletedManufacturingOrders_(
  sheet,
  cfg,
  uid,
  notifiedKeys
) {
  const scanRows = getConfiguredScanRowCount_(
    sheet,
    MFG_CFG.MAX_SCAN_ROWS
  );
  const result = {
    removedRows: 0,
    deletedIds: new Set(),
    notificationsChanged: false,
  };

  if (!scanRows) return result;

  const idValues = sheet
    .getRange(
      CFG.FIRST_DATA_ROW,
      getManufacturingIdColumn_(),
      scanRows,
      1
    )
    .getDisplayValues();
  const orderValues = sheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, scanRows, 1)
    .getDisplayValues();
  const rowsById = new Map();
  const orderKeysById = new Map();

  for (let index = 0; index < idValues.length; index++) {
    const id = cleanString_(idValues[index][0]);
    if (!/^\d+$/.test(id)) continue;

    if (!rowsById.has(id)) rowsById.set(id, []);
    rowsById.get(id).push(CFG.FIRST_DATA_ROW + index);

    if (!orderKeysById.has(id)) {
      orderKeysById.set(
        id,
        buildManufacturingOrderKeys_(
          cleanString_(orderValues[index][0]),
          cleanString_(orderValues[index][0])
        )
      );
    }
  }

  if (!rowsById.size) return result;

  const ids = Array.from(rowsById.keys()).map(Number);
  const firstExistingIds = fetchExistingManufacturingIds_(cfg, uid, ids);
  const potentiallyDeletedIds = ids.filter(
    (id) => !firstExistingIds.has(String(id))
  );

  if (!potentiallyDeletedIds.length) return result;

  // Segunda comprobación inmediata dentro de la misma sincronización.
  const secondExistingIds = fetchExistingManufacturingIds_(
    cfg,
    uid,
    potentiallyDeletedIds
  );
  const requiredOrderKeys = new Set();

  for (const id of potentiallyDeletedIds) {
    for (const orderKey of orderKeysById.get(String(id)) || []) {
      requiredOrderKeys.add(orderKey);
    }
  }

  const activeManufacturingIdByOrderKey = requiredOrderKeys.size
    ? fetchManufacturingIdsByOrderKey_(cfg, uid, requiredOrderKeys)
    : new Map();

  for (const [id, rows] of rowsById.entries()) {
    if (firstExistingIds.has(id) || secondExistingIds.has(id)) continue;

    const hasReplacementOrder = (orderKeysById.get(id) || []).some(
      (orderKey) => {
        const replacementId = cleanString_(
          activeManufacturingIdByOrderKey.get(orderKey)
        );
        return replacementId && replacementId !== id;
      }
    );

    if (hasReplacementOrder) {
      continue;
    }

    if (
      notifiedKeys &&
      clearManufacturingFinalizationNotificationKeysForRows_(
        sheet,
        rows,
        notifiedKeys
      )
    ) {
      result.notificationsChanged = true;
    }

    for (const row of rows) {
      clearManufacturingRow_(sheet, row);
      result.removedRows++;
    }

    result.deletedIds.add(id);
  }

  return result;
}

function fetchExistingManufacturingIds_(cfg, uid, ids) {
  if (!ids.length) return new Set();

  const records =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.manufacturing,
      "search_read",
      [[["id", "in", ids]]],
      { fields: ["id"], limit: ids.length }
    ) || [];

  return new Set(records.map((record) => String(record.id)));
}

function clearManufacturingRow_(sheet, row) {
  sheet.getRange(row, 1, 1, 10).clearContent();
  sheet.getRange(row, 14, 1, 8).clearContent();
  sheet.getRange(row, CFG.LINK_COL).clearNote();
  sheet.getRange(row, CFG.NEW_ROW_CHECKBOX_COL).setValue(false);
  if (typeof getSecondaryOperationalCheckboxColumn_ === "function") {
    const secondaryCheckboxColumn = getSecondaryOperationalCheckboxColumn_(sheet);
    if (secondaryCheckboxColumn) {
      sheet.getRange(row, secondaryCheckboxColumn).setValue(false);
    }
  }
  ensureDeliveryDaysFormula_(sheet, row);
}

/**
 * Ejecutar una vez después de instalar la columna R.
 * Completa IDs de filas existentes comparando su número con Odoo.
 */
function backfillManufacturingIds() {
  const sheet = getTargetSheet_();
  const cfg = getOdooCfg_();

  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuración de Odoo no está completa.");
  }

  const uid = odooLogin_(cfg);
  const scanRows = getConfiguredScanRowCount_(
    sheet,
    MFG_CFG.MAX_SCAN_ROWS
  );
  if (!scanRows) return;

  const orderValues = sheet
    .getRange(CFG.FIRST_DATA_ROW, CFG.ORDER_COL, scanRows, 1)
    .getDisplayValues();
  const linkRange = sheet.getRange(
    CFG.FIRST_DATA_ROW,
    CFG.LINK_COL,
    scanRows,
    1
  );
  const richTextValues = linkRange.getRichTextValues();
  const notes = linkRange.getNotes();
  const formulas = linkRange.getFormulas();
  const linkDisplayValues = linkRange.getDisplayValues();
  const idRange = sheet.getRange(
    CFG.FIRST_DATA_ROW,
    getManufacturingIdColumn_(),
    scanRows,
    1
  );
  const idValues = idRange.getValues();
  const requiredKeys = new Set();
  let updated = 0;

  // Primero recupera el ID desde el enlace. Esto funciona incluso si la
  // fabricación ya fue eliminada de Odoo.
  for (let index = 0; index < orderValues.length; index++) {
    if (cleanString_(idValues[index][0])) continue;

    const linkUrl = getManufacturingSnapshotUrl_(
      richTextValues[index][0],
      notes[index][0],
      formulas[index][0],
      linkDisplayValues[index][0]
    );
    const linkedId = extractManufacturingIdFromLink_(linkUrl);

    if (linkedId) {
      idValues[index][0] = linkedId;
      updated++;
    }
  }

  for (let index = 0; index < orderValues.length; index++) {
    if (cleanString_(idValues[index][0])) continue;

    const key = normalizeOrderNumberKey_(orderValues[index][0]);
    if (key) requiredKeys.add(key);
  }

  if (!requiredKeys.size) {
    idRange.setValues(idValues);
    SpreadsheetApp.flush();
    ejecutarOrdenadoAutomatico();
    showSpreadsheetToast_(`IDs de fabricación completados: ${updated}.`);
    return;
  }

  const idByOrderKey = fetchManufacturingIdsByOrderKey_(
    cfg,
    uid,
    requiredKeys
  );
  for (let index = 0; index < orderValues.length; index++) {
    if (cleanString_(idValues[index][0])) continue;

    const key = normalizeOrderNumberKey_(orderValues[index][0]);
    if (!key || !idByOrderKey.has(key)) continue;

    idValues[index][0] = idByOrderKey.get(key);
    updated++;
  }

  idRange.setValues(idValues);
  SpreadsheetApp.flush();
  ejecutarOrdenadoAutomatico();
  showSpreadsheetToast_(`IDs de fabricación completados: ${updated}.`);
}

function extractManufacturingIdFromLink_(urlValue) {
  const url = cleanString_(urlValue);

  if (!url || url.indexOf("model=mrp.production") === -1) {
    return "";
  }

  const match = url.match(/(?:#|[?&])id=(\d+)/i);
  return match && match[1] ? match[1] : "";
}

function getManufacturingSnapshotUrl_(
  richTextValue,
  noteValue,
  formulaValue,
  displayValue
) {
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
  if (displayMatch && displayMatch[0]) {
    return cleanString_(displayMatch[0]);
  }

  const noteMatch = cleanString_(noteValue).match(/https?:\/\/[^\s'"]+/i);
  return noteMatch && noteMatch[0] ? cleanString_(noteMatch[0]) : "";
}

function fetchManufacturingIdsByOrderKey_(cfg, uid, requiredKeys) {
  const map = new Map();
  const batchSize = 500;
  const maximumRecords = 5000;
  let offset = 0;

  while (offset < maximumRecords && map.size < requiredKeys.size) {
    const records =
      executeKw_(
        cfg,
        uid,
        ODOO_MODELS.manufacturing,
        "search_read",
        [[
          ["state", "!=", "cancel"],
        ]],
        {
          fields: ["id", "name", "origin"],
          order: "id desc",
          limit: batchSize,
          offset,
        }
    ) || [];

    for (const record of records) {
      const keys = buildManufacturingOrderKeys_(
        cleanString_(record.name),
        cleanString_(record.origin)
      );
      for (const key of keys) {
        if (requiredKeys.has(key) && !map.has(key)) {
          map.set(key, String(record.id));
        }
      }
    }

    if (records.length < batchSize) break;
    offset += records.length;
  }

  return map;
}

function findResponsible_(responsibleName) {
  const normalizedName = cleanString_(responsibleName).toLowerCase();
  if (!normalizedName) return "";

  for (const candidate of VALID_RESPONSIBLES) {
    if (normalizedName.includes(candidate.toLowerCase())) {
      return candidate;
    }
  }

  return "";
}

function fetchSalesOrderNamesByManufacturingOrigins_(cfg, uid, records) {
  const origins = Array.from(
    new Set(
      (records || [])
        .map((record) => cleanString_(record && record.origin))
        .filter((origin) => origin && !isPartialManufacturingOrder_(origin))
    )
  );

  if (!origins.length) return new Map();

  const salesOrders =
    executeKw_(
      cfg,
      uid,
      ODOO_MODELS.sales,
      "search_read",
      [[["name", "in", origins]]],
      {
        fields: ["name"],
        limit: origins.length,
      }
    ) || [];
  const map = new Map();

  for (const order of salesOrders) {
    const orderName = cleanString_(order.name);
    if (orderName) {
      map.set(orderName, orderName);
    }
  }

  return map;
}

function resolveManufacturingDisplayOrder_(record, salesOrderNamesByOrigin) {
  const origin = cleanString_(record && record.origin);
  if (
    origin &&
    salesOrderNamesByOrigin &&
    salesOrderNamesByOrigin.has(origin)
  ) {
    return salesOrderNamesByOrigin.get(origin);
  }

  const rawOrderName = cleanString_(record && record.name);
  const normalizedRawOrderName =
    stripManufacturingPartialSuffix_(rawOrderName) || rawOrderName;
  const orderNumberForSheet = parseOrderNumberForSheet_(normalizedRawOrderName);
  return orderNumberForSheet !== ""
    ? String(orderNumberForSheet)
    : normalizedRawOrderName;
}

function buildManufacturingOrderKeys_(rawOrderName, displayOrder) {
  const keys = [];
  const seen = new Set();
  const primaryValues = [
    stripManufacturingPartialSuffix_(rawOrderName),
    rawOrderName,
  ];
  let hasPrimaryKey = false;

  for (const value of primaryValues) {
    const key = normalizeOrderNumberKey_(value);
    if (!key || seen.has(key)) continue;

    seen.add(key);
    keys.push(key);
    hasPrimaryKey = true;
  }

  if (!hasPrimaryKey) {
    for (const value of [
      stripManufacturingPartialSuffix_(displayOrder),
      displayOrder,
    ]) {
      const key = normalizeOrderNumberKey_(value);
      if (!key || seen.has(key)) continue;

      seen.add(key);
      keys.push(key);
    }
  }

  return keys;
}

function findExistingManufacturingRow_(existingOrderRowMap, orderKeys) {
  for (const key of orderKeys) {
    if (existingOrderRowMap.has(key)) {
      return existingOrderRowMap.get(key);
    }
  }

  return null;
}

function removeManufacturingRowKeys_(existingOrderRowMap, orderKeys) {
  for (const key of orderKeys) {
    existingOrderRowMap.delete(key);
  }
}

function setManufacturingRowKeys_(existingOrderRowMap, orderKeys, targetRow) {
  for (const key of orderKeys) {
    existingOrderRowMap.set(key, targetRow);
  }
}

function resolveTargetRow_(sheet, existingOrderRowMap, orderNumberKey) {
  if (orderNumberKey && existingOrderRowMap.has(orderNumberKey)) {
    return existingOrderRowMap.get(orderNumberKey);
  }

  return getFirstAvailableRow_(sheet);
}

function isManufacturingSheetRow_(sheet, row) {
  const linkCell = sheet.getRange(row, CFG.LINK_COL);
  const url = cleanString_(getCellLinkUrl_(linkCell)).toLowerCase();

  if (url.indexOf("model=mrp.production") !== -1) return true;

  const note = cleanString_(safeGetNote_(linkCell)).toLowerCase();
  return (
    note.indexOf("fabric") !== -1 ||
    note.indexOf("mrp.production") !== -1
  );
}

function isManufacturingContextRow_(sheet, row, context) {
  if (cleanString_(context && context.origin).toUpperCase() === "FABRICACION") {
    return true;
  }

  return Boolean(
    sheet &&
    Number.isInteger(Number(row)) &&
    Number(row) >= CFG.FIRST_DATA_ROW &&
    isManufacturingSheetRow_(sheet, Number(row))
  );
}

function getManufacturingFinalizationContextFromRow_(sheet, row) {
  const metadataValues = sheet
    .getRange(row, getManufacturingIdColumn_(), 1, 4)
    .getDisplayValues()[0];
  const manufacturingId =
    cleanString_(metadataValues[0]) ||
    extractManufacturingIdFromLink_(
      getCellLinkUrl_(sheet.getRange(row, CFG.LINK_COL))
    );

  return {
    row,
    manufacturingId,
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
    quantity: cleanString_(
      sheet.getRange(row, 6).getDisplayValue()
    ),
  };
}

function buildManufacturingFinalizationNotificationKey_(context) {
  if (!context) return "";

  const manufacturingId = cleanString_(context.manufacturingId);
  if (manufacturingId) {
    return `mfg:${manufacturingId}`;
  }

  const orderKey = normalizeOrderNumberKey_(context.orderName);
  const productName = cleanString_(context.productName).toUpperCase();
  if (!orderKey || !productName) return "";

  return `mfg:order:${orderKey}|product:${productName}`;
}

function getManufacturingFinalizationNotifiedKeys_() {
  const raw = PropertiesService.getScriptProperties().getProperty(
    "ODOO_MFG_FINALIZATION_NOTIFIED_KEYS"
  );
  return parseStoredIdSet_(raw);
}

function saveManufacturingFinalizationNotifiedKeys_(keySet) {
  PropertiesService.getScriptProperties().setProperty(
    "ODOO_MFG_FINALIZATION_NOTIFIED_KEYS",
    JSON.stringify(Array.from(keySet))
  );
}

function clearManufacturingFinalizationNotificationKeysForRows_(
  sheet,
  rows,
  notifiedKeys
) {
  let didChange = false;

  for (const row of rows || []) {
    const context = getManufacturingFinalizationContextFromRow_(sheet, row);
    const notificationKey =
      buildManufacturingFinalizationNotificationKey_(context);

    if (!notificationKey || !notifiedKeys.has(notificationKey)) {
      continue;
    }

    notifiedKeys.delete(notificationKey);
    didChange = true;
  }

  return didChange;
}

function getManufacturingNotificationTarget_(cfg, uid, manufacturingId) {
  const numericManufacturingId = Number(manufacturingId);
  if (
    !Number.isInteger(numericManufacturingId) ||
    numericManufacturingId <= 0
  ) {
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
      ODOO_MODELS.manufacturing,
      "read",
      [[numericManufacturingId]],
      {
        fields: ["user_id"],
      }
    ) || [];
  const manufacturingUserId =
    orders.length > 0 ? getMany2oneId_(orders[0].user_id) : 0;

  if (!manufacturingUserId) {
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
      [[manufacturingUserId]],
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
    userId: manufacturingUserId,
    partnerIds: partnerId ? [partnerId] : [],
    displayName,
  };
}

function escapeManufacturingNotificationHtml_(value) {
  return cleanString_(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getManufacturingModelId_(cfg, uid) {
  const models =
    executeKw_(
      cfg,
      uid,
      "ir.model",
      "search_read",
      [[["model", "=", ODOO_MODELS.manufacturing]]],
      {
        fields: ["id"],
        limit: 1,
      }
    ) || [];

  return models.length ? Number(models[0].id) || 0 : 0;
}

function getManufacturingTodoActivityTypeId_(cfg, uid) {
  if (typeof getSalesTodoActivityTypeId_ === "function") {
    return getSalesTodoActivityTypeId_(cfg, uid);
  }

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
  } catch (err) {}

  if (xmlIdResolved) return xmlIdResolved;

  const todoTypes =
    executeKw_(
      cfg,
      uid,
      "mail.activity.type",
      "search_read",
      [[["name", "ilike", "To Do"]]],
      {
        fields: ["id"],
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

function buildManufacturingFinalizationActivityNoteHtml_(context) {
  const noteLines = [];

  if (cleanString_(context.orderName)) {
    noteLines.push(
      `<b>Orden:</b> ${escapeManufacturingNotificationHtml_(context.orderName)}`
    );
  }

  if (cleanString_(context.productName)) {
    noteLines.push(
      `<b>Producto:</b> ${escapeManufacturingNotificationHtml_(context.productName)}`
    );
  }

  if (cleanString_(context.quantity)) {
    noteLines.push(
      `<b>Cantidad:</b> ${escapeManufacturingNotificationHtml_(context.quantity)}`
    );
  }

  if (cleanString_(context.customerName)) {
    noteLines.push(
      `<b>Cliente:</b> ${escapeManufacturingNotificationHtml_(context.customerName)}`
    );
  }

  return noteLines.length
    ? `<p>${noteLines.join("<br/>")}</p>`
    : "<p>Trabajo de fabricacion finalizado.</p>";
}

function buildManufacturingActivityItemLabel_(context) {
  if (!context) return "";

  const orderName = cleanString_(context.orderName);
  const productName = cleanString_(context.productName);

  return orderName && productName
    ? `${orderName} - ${productName}`
    : orderName || productName;
}

function buildManufacturingActivitySummary_(baseSummary, context) {
  const normalizedBaseSummary = cleanString_(baseSummary);
  const itemLabel = buildManufacturingActivityItemLabel_(context);

  return itemLabel
    ? `${normalizedBaseSummary}: ${itemLabel}`
    : normalizedBaseSummary;
}

function scheduleManufacturingFinalizationActivity_(
  cfg,
  uid,
  manufacturingId,
  manufacturingUserId,
  context
) {
  const numericManufacturingId = Number(manufacturingId);
  const numericManufacturingUserId = Number(manufacturingUserId);

  if (
    !Number.isInteger(numericManufacturingId) ||
    numericManufacturingId <= 0 ||
    !Number.isInteger(numericManufacturingUserId) ||
    numericManufacturingUserId <= 0
  ) {
    return false;
  }

  const modelId = getManufacturingModelId_(cfg, uid);
  const activityTypeId = getManufacturingTodoActivityTypeId_(cfg, uid);
  if (!modelId || !activityTypeId) {
    throw new Error(
      "No se pudo resolver el modelo o el tipo de actividad de fabricacion."
    );
  }

  const today = nowUtcString_().slice(0, 10);
  const summary = buildManufacturingActivitySummary_(
    "Trabajo de fabricacion finalizado",
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
        ["res_id", "=", numericManufacturingId],
        ["user_id", "=", numericManufacturingUserId],
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
    note: buildManufacturingFinalizationActivityNoteHtml_(context),
    res_id: numericManufacturingId,
    res_model_id: modelId,
    summary,
    user_id: numericManufacturingUserId,
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

function postManufacturingFinalizationInternalNote_(context) {
  const manufacturingId = Number(cleanString_(context && context.manufacturingId));
  if (!Number.isInteger(manufacturingId) || manufacturingId <= 0) {
    throw new Error("No se pudo resolver mrp.production.id para la notificacion.");
  }

  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("La configuracion de Odoo no esta completa.");
  }

  const uid = odooLogin_(cfg);
  const notificationTarget = getManufacturingNotificationTarget_(
    cfg,
    uid,
    manufacturingId
  );

  if (!notificationTarget.userId) {
    logDebug_(
      `Notificacion automatica de fabricacion omitida para ${cleanString_(context.orderName) || manufacturingId}: falta user_id asignado.`
    );
    return false;
  }

  return scheduleManufacturingFinalizationActivity_(
    cfg,
    uid,
    manufacturingId,
    notificationTarget.userId,
    context
  );
}

function syncManufacturingFinalizationNotificationForRow_(
  sheet,
  row,
  previousStateValue,
  currentStateValue,
  notifiedKeys
) {
  const previousState = cleanString_(previousStateValue).toLowerCase();
  const currentState = cleanString_(currentStateValue).toLowerCase();
  const context = getManufacturingFinalizationContextFromRow_(sheet, row);

  if (!isManufacturingContextRow_(sheet, row, context)) {
    return false;
  }

  const notificationKey =
    buildManufacturingFinalizationNotificationKey_(context);
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

  if (!cleanString_(context.manufacturingId)) {
    logDebug_(
      `Notificacion automatica de fabricacion omitida en fila ${row}: falta mrp.production.id.`
    );
    return false;
  }

  if (!postManufacturingFinalizationInternalNote_(context)) {
    return false;
  }

  notifiedKeys.add(notificationKey);
  return true;
}
