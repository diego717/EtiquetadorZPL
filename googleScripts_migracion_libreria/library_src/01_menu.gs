function onOpen() {
  const ui = SpreadsheetApp.getUi();

  ui.createMenu("⚙️ Neo")
// Funciones de sincronización
    .addSubMenu(
      ui.createMenu("🔄 SINCRONIZACIÓN")
      .addItem("🔄 Sincronizar FABRICACION", "syncOdooManufacturingOrders")
      .addItem("🔄 Sincronizar VENTAS NEO", "syncOdooSalesOrdersNeo")
      .addItem("🔃 Sincronizar todas", "syncAllOrders")
    )
    // Exit
    
    // Funciones de Trabajos
    .addSubMenu(
      ui.createMenu("📄 TRABAJOS")
        .addItem("🎫 Etiqueta de ORDEN", "generarEtiquetasSeleccionadasPDF")
        .addItem("🛠️ Orden para TALLER", "solicitarImagenYGenerarPDF")
        .addItem("📦 Etiqueta de PRODUCTO", "generarEtiquetasTrabajosPDF")
    )
    // Funciones de Impresión
    .addSubMenu(
      ui.createMenu("🏷️ IMPRESION")
      .addItem("💳 Etiqueta de TARJETA", "generarEtiquetasProductosPDF")
      .addItem("📸 Imprimir TARJETA", "showImageSidebar")
    )
    // Funciones Herramientas
    .addSubMenu(
      ui.createMenu("🧰 HERRAMIENTAS")
      .addItem("🔖 Etiqueta PRODUCTOS", "EtiquetaParaProductos")
      .addItem("🔖 Etiqueta PRECARGADA", "abrirVisorPDFs")
      .addSeparator()
      .addItem("🔖 Planillas y Txt", "abrirVisorPlanillas")
      .addSeparator()
      .addItem("🧮 NeoCalculo", "showSidebar")
    )
    /**
    // Funciones Planillas
    .addSubMenu(
      ui.createMenu("🧰 PLANILLAS")
      .addItem("🔖 Sin asignar", "doNothing")
      .addSeparator()
      .addItem("🔖 Sin asignar", "abrirVisorPlanillas")
    )
    */
    .addToUi();
}

function doNothing() {
  // Función vacía para los encabezados/separadores de texto del menú
}

// 🔽 Sincronizar fabricacion y NEO en paralelo

async function runWithRetries(fn, maxRetries = 3, name = "función") {
  let attempt = 0;
  while (attempt < maxRetries) {
    try {
      attempt++;
      await fn();
      console.log(`✅ ${name} completada en intento ${attempt}`);
      return; // si funciona, salimos
    } catch (error) {
      console.warn(`⚠️ ${name} falló en intento ${attempt}:`, error);
      if (attempt >= maxRetries) {
        console.error(`❌ ${name} falló definitivamente tras ${maxRetries} intentos`);
      }
    }
  }
}
async function syncAllOrders() {
  const tasks = [
    { name: "syncOdooManufacturingOrders", fn: syncOdooManufacturingOrders },
    { name: "syncOdooSalesOrdersNeo", fn: syncOdooSalesOrdersNeo }
  ];

  const results = await Promise.allSettled(
    tasks.map(t => runWithRetries(t.fn, 3, t.name)) // 🔽 aquí defines el número de reintentos
  );
  results.forEach((result, index) => {
    const task = tasks[index];
    if (result.status === "fulfilled") {
      console.log(`✅ ${task.name} finalizó correctamente`);
    } else {
      console.error(`❌ ${task.name} no pudo completarse:`, result.reason);
    }
  });
}

/**
 * Requiere un activador instalable "Al editarse".
 */
function crearEnlaceAlEditar(e) {
  if (!e || !e.range) return;

  const sheet = e.range.getSheet();
  if (sheet.getName() !== CFG.SHEET_NAME) return;
  if (e.range.getColumn() !== CFG.ORDER_COL) return;
  if (e.range.getRow() < CFG.FIRST_DATA_ROW) return;

  applyLinkToCell_(
    sheet.getRange(e.range.getRow(), CFG.ORDER_COL),
    sheet.getRange(e.range.getRow(), CFG.LINK_COL)
  );
}

function diagnoseActiveRowOrder() {
  const sheet = getTargetSheet_();
  const cell = sheet.getActiveCell();
  if (!cell) return;

  const value = cleanString_(cell.getDisplayValue());
  const cfg = getOdooCfg_();

  try {
    const record = findAnythingInOdoo_(cfg, value);

    if (record) {
      sheet
        .getRange(cell.getRow(), CFG.LINK_COL)
        .setNote(
          `DIAGNOSTICO:\nModelo: ${record.model}\nNombre: ${record.name}`
        );

      SpreadsheetApp.getActive().toast(`Match: ${record.name}`);
    } else {
      SpreadsheetApp.getActive().toast("No se encontro nada.");
    }
  } catch (err) {
    SpreadsheetApp.getUi().alert("Error: " + err.message);
  }
}

function diagnoseNeoSaleOrder() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Diagnostico orden NEO",
    "Ingresa numero o nombre de orden de venta (ej: 790, S000790, SO790).",
    ui.ButtonSet.OK_CANCEL
  );

  if (response.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  const lookupValue = cleanString_(response.getResponseText());

  if (!lookupValue) {
    ui.alert("No ingresaste ninguna orden.");
    return;
  }

  try {
    const report = buildNeoSaleOrderDiagnosisReport_(lookupValue);
    ui.alert(report);
  } catch (err) {
    ui.alert("Error al diagnosticar la orden NEO: " + err.message);
  }
}

function forceImportNeoSaleOrder() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Importar orden NEO puntual",
    "Ingresa numero o nombre de orden de venta (ej: 790, S000790, SO790).",
    ui.ButtonSet.OK_CANCEL
  );

  if (response.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  const lookupValue = cleanString_(response.getResponseText());

  if (!lookupValue) {
    ui.alert("No ingresaste ninguna orden.");
    return;
  }

  try {
    const result = importSpecificNeoSaleOrder_(lookupValue);
    ui.alert(`Importacion NEO\n\n${result.message}`);
  } catch (err) {
    ui.alert("Error al importar la orden NEO: " + err.message);
  }
}

function installOdooSalesAutoSyncTrigger() {
  const functionName = getSalesAutoSyncTriggerFunctionName_();
  const intervalMinutes =
    Number(SALES_CFG.AUTO_SYNC_EVERY_MINUTES) || 5;

  if (hasInstalledTrigger_(functionName) !== true) {
    ScriptApp.newTrigger(functionName)
      .timeBased()
      .everyMinutes(intervalMinutes)
      .create();
  }

  const result = syncOdooSalesOrdersNeo();

  showSpreadsheetToast_(
    `Sync automatica NEO activa cada ${intervalMinutes} min. ` +
      `Nuevas: ${result.inserted || 0} | ` +
      `Actualizadas: ${result.updated || 0} | ` +
      `Quitadas: ${result.removed || 0}`
  );
}

function removeOdooSalesAutoSyncTrigger() {
  const removed = removeTriggersByFunction_(
    getSalesAutoSyncTriggerFunctionName_()
  );

  showSpreadsheetToast_(
    removed > 0
      ? "Sincronizacion automatica NEO desactivada."
      : "No habia una sincronizacion automatica NEO activa."
  );
}

function installSalesFinalizationNotificationTriggerFromMenu() {
  installSalesFinalizationNotificationTrigger();
  showSpreadsheetToast_("Aviso de venta finalizada activado.");
}

function removeSalesFinalizationNotificationTriggerFromMenu() {
  removeSalesFinalizationNotificationTrigger();
  showSpreadsheetToast_("Aviso de venta finalizada desactivado.");
}

function removeTriggersByFunction_(functionName) {
  let removed = 0;

  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction() !== functionName) {
      continue;
    }

    ScriptApp.deleteTrigger(trigger);
    removed++;
  }

  return removed;
}
