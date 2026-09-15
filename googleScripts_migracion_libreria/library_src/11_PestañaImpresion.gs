function clienteStock(e) {
  // Validar evento y edición de una sola celda
  if (!e || !e.range) return;
  const range = e.range;
  if (range.getNumRows() > 1 || range.getNumColumns() > 1) return;

  const sheet = range.getSheet();
  const row = range.getRow();
  const col = range.getColumn();
  const rawVal = typeof e.value === "undefined" ? "" : e.value;
  const val = rawVal === null ? "" : rawVal.toString();

  // Usar la fila base del proyecto si existe, si no, fallback a 6
  const firstDataRow = typeof CFG !== "undefined" && CFG.FIRST_DATA_ROW
    ? CFG.FIRST_DATA_ROW
    : 6;

  if (row < firstDataRow) return;

  // Columna G = 7
  if (col !== 7) return;

  // Caso: se elimina el cliente (celda vacía)
  if (!val || val.trim() === "") {
    sheet.getRange(row, 1, 1, 2).clearContent(); // A (Fecha) y B (ID)
    sheet.getRange(row, 4, 1, 2).clearContent(); // D (Ajuste) y E (U)
    return;
  }

  const clienteActual = val.toString().trim().toLowerCase();

  // Poner fecha en Columna A (y formatearla)
  sheet.getRange(row, 1).setValue(new Date()).setNumberFormat("dd/mm/yyyy");

  // Buscar última aparición previa del cliente en Columna G (desde firstDataRow hasta row-1)
  if (row > firstDataRow) {
    const numRowsToSearch = row - firstDataRow;
    if (numRowsToSearch > 0) {
      const clientesAnteriores = sheet
        .getRange(firstDataRow, 7, numRowsToSearch, 1)
        .getValues();
      let filaEncontrada = -1;

      for (let i = clientesAnteriores.length - 1; i >= 0; i--) {
        const cellVal = clientesAnteriores[i][0];
        const key = cellVal === null || typeof cellVal === "undefined"
          ? ""
          : cellVal.toString().trim().toLowerCase();
        if (key === clienteActual) {
          filaEncontrada = firstDataRow + i;
          break;
        }
      }

      if (filaEncontrada !== -1) {
        const idAnterior = sheet.getRange(filaEncontrada, 2).getValue(); // Col B
        const uAnterior = sheet.getRange(filaEncontrada, 5).getValue();  // Col E
        sheet.getRange(row, 2).setValue(idAnterior);
        sheet.getRange(row, 5).setValue(uAnterior);
      }
    }
  }
}

// Función auxiliar para escapar texto en HTML
function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}