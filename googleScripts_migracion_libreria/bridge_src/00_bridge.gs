/**
 * Bridge for the spreadsheet-bound Apps Script project.
 *
 * Keep this file in the spreadsheet project and move the real implementation
 * to the EtiquetadorZPL library. The library identifier must be exactly:
 *
 *   EtiquetadorZPL
 */

function abrirVisorPDFs() {
  return EtiquetadorZPL.abrirVisorPDFs.apply(EtiquetadorZPL, arguments);
}

function abrirVisorPlanillas() {
  return EtiquetadorZPL.abrirVisorPlanillas.apply(EtiquetadorZPL, arguments);
}

function automatizacionEditar() {
  return EtiquetadorZPL.automatizacionEditar.apply(EtiquetadorZPL, arguments);
}

function backfillManufacturingIds() {
  return EtiquetadorZPL.backfillManufacturingIds.apply(EtiquetadorZPL, arguments);
}

function buildCandidatesForModel() {
  return EtiquetadorZPL.buildCandidatesForModel.apply(EtiquetadorZPL, arguments);
}

function buscarImagenOdooPorCodigo() {
  return EtiquetadorZPL.buscarImagenOdooPorCodigo.apply(EtiquetadorZPL, arguments);
}

function calcularServer() {
  return EtiquetadorZPL.calcularServer.apply(EtiquetadorZPL, arguments);
}

function checkOdooSheetSetup() {
  return EtiquetadorZPL.checkOdooSheetSetup.apply(EtiquetadorZPL, arguments);
}

function clearSyncLogSheet() {
  return EtiquetadorZPL.clearSyncLogSheet.apply(EtiquetadorZPL, arguments);
}

function clienteStock() {
  return EtiquetadorZPL.clienteStock.apply(EtiquetadorZPL, arguments);
}

function crearEnlaceAlEditar() {
  return EtiquetadorZPL.crearEnlaceAlEditar.apply(EtiquetadorZPL, arguments);
}

function diagnoseActiveRowOrder() {
  return EtiquetadorZPL.diagnoseActiveRowOrder.apply(EtiquetadorZPL, arguments);
}

function diagnoseAutoSyncHealth() {
  return EtiquetadorZPL.diagnoseAutoSyncHealth.apply(EtiquetadorZPL, arguments);
}

function diagnoseNeoSaleOrder() {
  return EtiquetadorZPL.diagnoseNeoSaleOrder.apply(EtiquetadorZPL, arguments);
}

function diagnoseSalesApprovalActivityForRow() {
  return EtiquetadorZPL.diagnoseSalesApprovalActivityForRow.apply(EtiquetadorZPL, arguments);
}

function diagnoseSalesDeliverySourceForOrder() {
  return EtiquetadorZPL.diagnoseSalesDeliverySourceForOrder.apply(EtiquetadorZPL, arguments);
}

function diagnoseSalesFinalizationActivityForRow() {
  return EtiquetadorZPL.diagnoseSalesFinalizationActivityForRow.apply(EtiquetadorZPL, arguments);
}

function doNothing() {
  return EtiquetadorZPL.doNothing.apply(EtiquetadorZPL, arguments);
}

function ejecutarOrdenadoAutomatico() {
  return EtiquetadorZPL.ejecutarOrdenadoAutomatico.apply(EtiquetadorZPL, arguments);
}

function escapeHtml() {
  return EtiquetadorZPL.escapeHtml.apply(EtiquetadorZPL, arguments);
}

function EtiquetaParaProductos() {
  return EtiquetadorZPL.EtiquetaParaProductos.apply(EtiquetadorZPL, arguments);
}

function forceCreateSalesApprovalActivityForRow() {
  return EtiquetadorZPL.forceCreateSalesApprovalActivityForRow.apply(EtiquetadorZPL, arguments);
}

function forceCreateSalesFinalizationActivityForRow() {
  return EtiquetadorZPL.forceCreateSalesFinalizationActivityForRow.apply(EtiquetadorZPL, arguments);
}

function forceImportNeoSaleOrder() {
  return EtiquetadorZPL.forceImportNeoSaleOrder.apply(EtiquetadorZPL, arguments);
}

function forceResyncSalesDeliveryFromChatterForOrder() {
  return EtiquetadorZPL.forceResyncSalesDeliveryFromChatterForOrder.apply(EtiquetadorZPL, arguments);
}

function forceResyncSalesDeliveryFromChatterForRow() {
  return EtiquetadorZPL.forceResyncSalesDeliveryFromChatterForRow.apply(EtiquetadorZPL, arguments);
}

function formatearFechaEntrega() {
  return EtiquetadorZPL.formatearFechaEntrega.apply(EtiquetadorZPL, arguments);
}

function generarEtiquetasProductosPDF() {
  return EtiquetadorZPL.generarEtiquetasProductosPDF.apply(EtiquetadorZPL, arguments);
}

function generarEtiquetasSeleccionadasPDF() {
  return EtiquetadorZPL.generarEtiquetasSeleccionadasPDF.apply(EtiquetadorZPL, arguments);
}

function generarEtiquetasTrabajosPDF() {
  return EtiquetadorZPL.generarEtiquetasTrabajosPDF.apply(EtiquetadorZPL, arguments);
}

function generarPDFDesdeSeleccion() {
  return EtiquetadorZPL.generarPDFDesdeSeleccion.apply(EtiquetadorZPL, arguments);
}

function generarPDFDesdeSidebar() {
  return EtiquetadorZPL.generarPDFDesdeSidebar.apply(EtiquetadorZPL, arguments);
}

function generarPDFProductosDesdeSidebar() {
  return EtiquetadorZPL.generarPDFProductosDesdeSidebar.apply(EtiquetadorZPL, arguments);
}

function getSidebarHtml() {
  return EtiquetadorZPL.getSidebarHtml.apply(EtiquetadorZPL, arguments);
}

function installOdooLinkEditTrigger() {
  return EtiquetadorZPL.installOdooLinkEditTrigger.apply(EtiquetadorZPL, arguments);
}

function installOdooManufacturingAutoSyncTrigger() {
  return EtiquetadorZPL.installOdooManufacturingAutoSyncTrigger.apply(EtiquetadorZPL, arguments);
}

function installOdooOperationalTriggers() {
  return EtiquetadorZPL.installOdooOperationalTriggers.apply(EtiquetadorZPL, arguments);
}

function installOdooSalesAutoSyncTrigger() {
  return EtiquetadorZPL.installOdooSalesAutoSyncTrigger.apply(EtiquetadorZPL, arguments);
}

function installSalesFinalizationNotificationTrigger() {
  return EtiquetadorZPL.installSalesFinalizationNotificationTrigger.apply(EtiquetadorZPL, arguments);
}

function installSalesFinalizationNotificationTriggerFromMenu() {
  return EtiquetadorZPL.installSalesFinalizationNotificationTriggerFromMenu.apply(EtiquetadorZPL, arguments);
}

function installSalesHiddenMetadataRepairTrigger() {
  return EtiquetadorZPL.installSalesHiddenMetadataRepairTrigger.apply(EtiquetadorZPL, arguments);
}

function moverFinalizadosAHistorico() {
  return EtiquetadorZPL.moverFinalizadosAHistorico.apply(EtiquetadorZPL, arguments);
}

function notificarVentaNeoFinalizadaAlEditar() {
  return EtiquetadorZPL.notificarVentaNeoFinalizadaAlEditar.apply(EtiquetadorZPL, arguments);
}

function obtenerBase64PdfDrive() {
  return EtiquetadorZPL.obtenerBase64PdfDrive.apply(EtiquetadorZPL, arguments);
}

function obtenerBase64PDFDrive() {
  return EtiquetadorZPL.obtenerBase64PDFDrive.apply(EtiquetadorZPL, arguments);
}

function obtenerDatosEtiquetas() {
  return EtiquetadorZPL.obtenerDatosEtiquetas.apply(EtiquetadorZPL, arguments);
}

function obtenerDatosFilaActiva() {
  return EtiquetadorZPL.obtenerDatosFilaActiva.apply(EtiquetadorZPL, arguments);
}

function obtenerInfoTarjetaSeleccionada() {
  return EtiquetadorZPL.obtenerInfoTarjetaSeleccionada.apply(EtiquetadorZPL, arguments);
}

function obtenerListaPDFs() {
  return EtiquetadorZPL.obtenerListaPDFs.apply(EtiquetadorZPL, arguments);
}

function obtenerListaPlanillas() {
  return EtiquetadorZPL.obtenerListaPlanillas.apply(EtiquetadorZPL, arguments);
}

function obtenerResumenSeleccion() {
  return EtiquetadorZPL.obtenerResumenSeleccion.apply(EtiquetadorZPL, arguments);
}

function onEdit() {
  return EtiquetadorZPL.onEdit.apply(EtiquetadorZPL, arguments);
}

function onOpen() {
  return EtiquetadorZPL.onOpen.apply(EtiquetadorZPL, arguments);
}

function openSyncLogSheet() {
  return EtiquetadorZPL.openSyncLogSheet.apply(EtiquetadorZPL, arguments);
}

function procesarEtiquetasA4() {
  return EtiquetadorZPL.procesarEtiquetasA4.apply(EtiquetadorZPL, arguments);
}

function promptDiagnoseSalesDeliverySourceForOrder() {
  return EtiquetadorZPL.promptDiagnoseSalesDeliverySourceForOrder.apply(EtiquetadorZPL, arguments);
}

function promptResyncSalesDeliveryFromChatterForOrder() {
  return EtiquetadorZPL.promptResyncSalesDeliveryFromChatterForOrder.apply(EtiquetadorZPL, arguments);
}

function rebuildLinks() {
  return EtiquetadorZPL.rebuildLinks.apply(EtiquetadorZPL, arguments);
}

function removeOdooLinkEditTrigger() {
  return EtiquetadorZPL.removeOdooLinkEditTrigger.apply(EtiquetadorZPL, arguments);
}

function removeOdooManufacturingAutoSyncTrigger() {
  return EtiquetadorZPL.removeOdooManufacturingAutoSyncTrigger.apply(EtiquetadorZPL, arguments);
}

function removeOdooSalesAutoSyncTrigger() {
  return EtiquetadorZPL.removeOdooSalesAutoSyncTrigger.apply(EtiquetadorZPL, arguments);
}

function removeSalesFinalizationNotificationTrigger() {
  return EtiquetadorZPL.removeSalesFinalizationNotificationTrigger.apply(EtiquetadorZPL, arguments);
}

function removeSalesFinalizationNotificationTriggerFromMenu() {
  return EtiquetadorZPL.removeSalesFinalizationNotificationTriggerFromMenu.apply(EtiquetadorZPL, arguments);
}

function removeSalesHiddenMetadataRepairTrigger() {
  return EtiquetadorZPL.removeSalesHiddenMetadataRepairTrigger.apply(EtiquetadorZPL, arguments);
}

function repairDeliveryDaysFormulas() {
  return EtiquetadorZPL.repairDeliveryDaysFormulas.apply(EtiquetadorZPL, arguments);
}

function repairExistingSalesHiddenMetadata() {
  return EtiquetadorZPL.repairExistingSalesHiddenMetadata.apply(EtiquetadorZPL, arguments);
}

function repairManufacturingDateValues() {
  return EtiquetadorZPL.repairManufacturingDateValues.apply(EtiquetadorZPL, arguments);
}

function repairOperationalCheckboxes() {
  return EtiquetadorZPL.repairOperationalCheckboxes.apply(EtiquetadorZPL, arguments);
}

function repairSalesDeliveryDateValues() {
  return EtiquetadorZPL.repairSalesDeliveryDateValues.apply(EtiquetadorZPL, arguments);
}

function repairSalesIngressDateValues() {
  return EtiquetadorZPL.repairSalesIngressDateValues.apply(EtiquetadorZPL, arguments);
}

function resetSyncState() {
  return EtiquetadorZPL.resetSyncState.apply(EtiquetadorZPL, arguments);
}

function runDailySalesHiddenMetadataRepair() {
  return EtiquetadorZPL.runDailySalesHiddenMetadataRepair.apply(EtiquetadorZPL, arguments);
}

function runWithRetries() {
  return EtiquetadorZPL.runWithRetries.apply(EtiquetadorZPL, arguments);
}

function sanitizarHTML_Unico() {
  return EtiquetadorZPL.sanitizarHTML_Unico.apply(EtiquetadorZPL, arguments);
}

function showImageSidebar() {
  return EtiquetadorZPL.showImageSidebar.apply(EtiquetadorZPL, arguments);
}

function showSidebar() {
  return EtiquetadorZPL.showSidebar.apply(EtiquetadorZPL, arguments);
}

function solicitarImagenYGenerarPDF() {
  return EtiquetadorZPL.solicitarImagenYGenerarPDF.apply(EtiquetadorZPL, arguments);
}

function syncAllOrders() {
  return EtiquetadorZPL.syncAllOrders.apply(EtiquetadorZPL, arguments);
}

function syncOdooManufacturingOrders() {
  return EtiquetadorZPL.syncOdooManufacturingOrders.apply(EtiquetadorZPL, arguments);
}

function syncOdooSalesOrdersNeo() {
  return EtiquetadorZPL.syncOdooSalesOrdersNeo.apply(EtiquetadorZPL, arguments);
}

function testSheetAccess() {
  return EtiquetadorZPL.testSheetAccess.apply(EtiquetadorZPL, arguments);
}

function testSyncLogWrite() {
  return EtiquetadorZPL.testSyncLogWrite.apply(EtiquetadorZPL, arguments);
}
