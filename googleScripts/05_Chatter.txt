/**
 * ============================================================================
 * LECTURA Y PROCESAMIENTO DEL CHATTER DE ODOO
 * ============================================================================
 */

/**
 * Obtiene todos los mensajes asociados a una orden de fabricación.
 */
function fetchAllManufacturingChatterMessages_(
  cfg,
  uid,
  resId
) {
  return fetchAllChatterMessagesByModel_(
    cfg,
    uid,
    ODOO_MODELS.manufacturing,
    resId
  );
}

/**
 * Obtiene los mensajes de un registro, recorriendo todas las páginas.
 */
function fetchAllChatterMessagesByModel_(
  cfg,
  uid,
  model,
  resId
) {
  const messages = [];
  const limit = 100;
  let offset = 0;

  while (true) {
    const batch = executeKw_(
      cfg,
      uid,
      ODOO_MODELS.chatter,
      "search_read",
      [[
        ["model", "=", model],
        ["res_id", "=", resId],
      ]],
      {
        fields: [
          "id",
          "date",
          "body",
          "message_type",
        ],
        order: "date desc, id desc",
        limit,
        offset,
      }
    ) || [];

    messages.push(...batch);

    if (batch.length < limit) {
      break;
    }

    offset += batch.length;
  }

  return messages;
}

/**
 * ============================================================================
 * NOTAS DE FABRICACIÓN
 * ============================================================================
 */

/**
 * Obtiene la nota válida más reciente de una fabricación.
 *
 * SIN USO HOY: era el respaldo por registro de syncOdooManufacturingOrders_
 * cuando la precarga por lote no traía la nota, pero una guarda
 * "typeof ... === 'function'" (siempre verdadera en Apps Script) lo dejaba
 * inalcanzable. Ver la nota en 04_Fabricacion.txt, donde estaba la llamada.
 * Se conserva porque es la implementación que hace falta si se decide
 * reactivar ese respaldo.
 */
function extractLatestManufacturingNote_(
  cfg,
  uid,
  resId
) {
  try {
    const messages =
      fetchAllManufacturingChatterMessages_(
        cfg,
        uid,
        resId
      );

    logDebug_(
      `mail.message fabricación para ` +
        `odooId=${resId} => count=${messages.length}`
    );

    return extractManufacturingNoteFromMessages_(
      messages
    );
  } catch (err) {
    Logger.log(
      `Error leyendo mail.message para ` +
        `fabricación id=${resId}: ${err}`
    );

    return {
      date: "",
      dateValue: null,
      state: "",
      customerName: "",
    };
  }
}

/**
 * Recorre los mensajes de fabricación desde el más reciente.
 */
function extractManufacturingNoteFromMessages_(
  messages
) {
  let latestDetectedState = "";
  let latestDetectedCustomerName = "";

  for (const message of messages) {
    const parsed = parseManufacturingNote_(
      message.body
    );

    if (!parsed) continue;

    if (
      parsed.state &&
      !latestDetectedState
    ) {
      latestDetectedState = parsed.state;
    }

    if (
      parsed.customerName &&
      !latestDetectedCustomerName
    ) {
      latestDetectedCustomerName =
        parsed.customerName;
    }

    if (parsed.date) {
      return {
        date: parsed.date,
        dateValue: parsed.dateValue || null,
        state:
          parsed.state ||
          latestDetectedState,
        customerName:
          parsed.customerName ||
          latestDetectedCustomerName,
      };
    }
  }

  return {
    date: "",
    dateValue: null,
    state: latestDetectedState,
    customerName: latestDetectedCustomerName,
  };
}

/**
 * Las notas de fabricación requieren fecha y estado.
 */
function parseManufacturingNote_(body) {
  const text = normalizeMessageBody_(body);
  if (!text) return null;

  const lines = text
    .split(/\n+/)
    .map(normalizeNoteLine_)
    .filter((line) => line !== "");

  let parsedDate = null;
  let parsedState = "";
  let parsedCustomerName = "";

  for (const line of lines.slice(0, 8)) {
    if (!parsedDate) {
      const labeledDate =
        extractLabeledNoteValue_(
          line,
          [
            "fecha de entrega",
            "entrega",
            "fecha",
            "date",
          ]
        );

      const candidates = [
        labeledDate,
        line,
      ].filter(Boolean);

      for (const candidate of candidates) {
        parsedDate =
          tryParseDateString_(candidate);

        if (parsedDate) break;

        for (const regex of DATE_REGEXES) {
          const match = candidate.match(regex);

          if (match && match[1]) {
            parsedDate =
              tryParseDateString_(match[1]);

            if (parsedDate) break;
          }
        }

        if (parsedDate) break;
      }
    }

    if (!parsedState) {
      const stateCandidate =
        extractLabeledNoteValue_(
          line,
          ["estado", "state"]
        ) || line;

      parsedState =
        normalizeManufacturingState_(
          stateCandidate
        );
    }

    if (!parsedCustomerName) {
      parsedCustomerName =
        extractLabeledNoteValue_(
          line,
          [
            "cliente",
            "customer",
            "cliente final",
          ]
        ) || "";
    }

    if (
      parsedDate &&
      parsedState &&
      parsedCustomerName
    ) {
      break;
    }
  }

  if (
    !parsedDate &&
    !parsedState &&
    !parsedCustomerName
  ) {
    return null;
  }

  return {
    // date: solo para mostrar/comparar. Descarta el año, asi que NO debe
    // usarse para escribir en la planilla: usar dateValue.
    date: parsedDate
      ? Utilities.formatDate(
          parsedDate,
          Session.getScriptTimeZone(),
          "d-MMM"
        )
      : "",
    dateValue: parsedDate || null,
    state: parsedState || "",
    customerName: parsedCustomerName || "",
  };
}

/**
 * ============================================================================
 * NOTAS DE VENTAS
 *
 * La lectura del chatter de ventas vive en 06_VentasNeo.txt
 * (extractLatestSalesNoteSafely_ / fetchLatestSalesNotesMap_). Aqui queda
 * solamente el parser, que ambos caminos reutilizan.
 * ============================================================================
 */

/**
 * En ventas la fecha es obligatoria y el estado es opcional.
 */
function parseSalesPlanningNote_(body) {
  const text = normalizeMessageBody_(body);

  if (!text) {
    return null;
  }

  const lines = text
    .split(/\n+/)
    .map(normalizeNoteLine_)
    .filter((line) => line !== "");

  if (!lines.length) {
    return null;
  }

  let parsedDate = null;
  let parsedState = "";

  for (const line of lines.slice(0, 8)) {
    if (!parsedDate) {
      const labeledDate =
        extractLabeledNoteValue_(
          line,
          ["fecha", "date", "entrega"]
        );

      if (labeledDate) {
        parsedDate = tryParseDateString_(
          labeledDate
        );
      }

      if (!parsedDate) {
        for (const regex of DATE_REGEXES) {
          const match = line.match(regex);

          if (match && match[1]) {
            parsedDate = tryParseDateString_(
              match[1]
            );

            if (parsedDate) break;
          }
        }
      }
    }

    if (!parsedState) {
      const stateCandidate =
        extractLabeledNoteValue_(
          line,
          ["estado", "state"]
        ) || line;

      parsedState = mapAnyStateToSheetValue_(
        stateCandidate
      );
    }

    if (parsedDate && parsedState) {
      break;
    }
  }

  if (!parsedDate && !parsedState) {
    return null;
  }

  return {
    // date: solo para mostrar/comparar (descarta el año). Para escribir en la
    // planilla usar dateValue.
    date: parsedDate
      ? Utilities.formatDate(
          parsedDate,
          Session.getScriptTimeZone(),
          "d-MMM"
        )
      : "",
    dateValue: parsedDate || null,
    state: parsedState || "",
  };
}

/**
 * ============================================================================
 * NORMALIZACIÓN DE ESTADOS
 * ============================================================================
 */

/**
 * Normaliza los estados internos y sus alias.
 */
function normalizeManufacturingState_(value) {
  const text = cleanString_(value).toLowerCase();

  if (!text) {
    return "";
  }

  for (
    const [canonicalState, aliases]
    of Object.entries(
      MANUFACTURING_STATE_ALIASES
    )
  ) {
    if (text === canonicalState) {
      return canonicalState;
    }

    for (const alias of aliases) {
      if (
        text === alias ||
        text.indexOf(alias) !== -1
      ) {
        return canonicalState;
      }
    }
  }

  return "";
}

/**
 * Convierte un estado de Odoo al valor utilizado en la hoja.
 */
function mapManufacturingStateToSheetValue_(value) {
  const canonicalState =
    normalizeManufacturingState_(value) ||
    cleanString_(value).toLowerCase();

  return SHEET_STATE_LABELS[canonicalState] || "";
}

/**
 * Reconoce directamente estados escritos como aparecen en la hoja.
 */
function normalizeDirectSheetStateLabel_(value) {
  const text = cleanString_(value).toLowerCase();

  if (!text) {
    return "";
  }

  return SHEET_DIRECT_STATE_LABELS[text] || "";
}

/**
 * Intenta primero un estado directo y después un estado de Odoo.
 */
function mapAnyStateToSheetValue_(value) {
  return (
    normalizeDirectSheetStateLabel_(value) ||
    mapManufacturingStateToSheetValue_(value)
  );
}

/**
 * ============================================================================
 * NORMALIZACIÓN DEL CONTENIDO DE LAS NOTAS
 * ============================================================================
 */

/**
 * Extrae el valor de una línea con etiqueta.
 *
 * Ejemplos:
 * Fecha: 29/06/2026
 * Estado - Empezar
 */
function extractLabeledNoteValue_(line, labels) {
  const text = cleanString_(line);

  if (!text) {
    return "";
  }

  for (const label of labels) {
    const pattern = new RegExp(
      `^${label}\\s*[:\\-]?\\s*(.+)$`,
      "i"
    );

    const match = text.match(pattern);

    if (match && match[1]) {
      return cleanString_(match[1]);
    }
  }

  return "";
}

/**
 * Elimina viñetas y espacios innecesarios.
 */
function normalizeNoteLine_(line) {
  return cleanString_(
    String(line || "").replace(
      /^[•\-\*]\s*/,
      ""
    )
  );
}

/**
 * Convierte el HTML de Odoo en texto sencillo.
 */
function normalizeMessageBody_(body) {
  let text = String(body || "");

  if (!text) {
    return "";
  }

  text = text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(
      /<\/p>|<\/div>|<\/li>|<\/tr>/gi,
      "\n"
    )
    .replace(/<p[^>]*>/gi, "")
    .replace(/<div[^>]*>/gi, "")
    .replace(/<li[^>]*>/gi, "")
    .replace(/<tr[^>]*>/gi, "")
    .replace(/<td[^>]*>/gi, " ")
    .replace(/<[^>]+>/g, " ");

  text = decodeHtmlEntities_(text);

  return text
    .replace(/\r\n?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Decodifica las entidades HTML más habituales.
 */
function decodeHtmlEntities_(text) {
  return String(text || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}