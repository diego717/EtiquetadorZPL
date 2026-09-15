/** ----------------------- GENERACIÓN DE ETIQUETAS EN SIDEBAR - HOJA IMPRESION ----------------------- */

/**
 * Función principal para abrir la barra lateral (Sidebar) de generación de etiquetas de tarjetas.
 */
function generarEtiquetasProductosPDF() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ui = SpreadsheetApp.getUi();

  // Crear y mostrar la barra lateral con título actualizado
  var htmlOutput = HtmlService.createHtmlOutput(obtenerHtmlSidebarProductos_())
      .setTitle('Etiquetas para Tarjetas')
      .setWidth(320);

  ui.showSidebar(htmlOutput);
}

/**
 * Obtiene la información de los rangos/filas seleccionados en la hoja.
 * Evalúa únicamente Cliente (Col G / 7) y Tarjetas Buenas (Col S / 19).
 */
function obtenerResumenSeleccion() {
  var hoja = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var rangosSeleccionados = hoja.getActiveRangeList().getRanges();
  
  var filasValidas = 0;
  var totalTarjetasAcumuladas = 0;
  var muestraCliente = "";
  var tieneTarjetasBuenas = false;

  for (var r = 0; r < rangosSeleccionados.length; r++) {
    var rango = rangosSeleccionados[r];
    var filaInicio = rango.getRow();
    var totalFilas = rango.getNumRows();

    for (var i = 0; i < totalFilas; i++) {
      var filaActual = filaInicio + i;
      var clienteTexto = hoja.getRange(filaActual, 7).getValue();
      
      if (!clienteTexto || clienteTexto.toString().trim() === "") {
        continue;
      }

      filasValidas++;
      if (!muestraCliente) {
        muestraCliente = clienteTexto.toString().trim();
      }

      // Evaluar EXCLUSIVAMENTE Columna S (19) = Tarjetas Buenas
      var tarjetasBuenas = hoja.getRange(filaActual, 19).getValue();
      var cantidadValida = Number(tarjetasBuenas);

      if (!isNaN(cantidadValida) && cantidadValida > 0) {
        totalTarjetasAcumuladas += cantidadValida;
        tieneTarjetasBuenas = true;
      }
    }
  }

  if (!muestraCliente) {
    throw new Error('Seleccione una fila que contenga la información del Cliente (Columna G).');
  }

  return {
    filasValidas: filasValidas,
    totalTarjetas: totalTarjetasAcumuladas,
    muestraCliente: muestraCliente,
    tieneTarjetasBuenas: tieneTarjetasBuenas
  };
}

/**
 * Procesa los rangos seleccionados y genera el PDF de las etiquetas.
 */
function generarPDFProductosDesdeSidebar(cantPorPaquete) {
  var hoja = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var rangosSeleccionados = hoja.getActiveRangeList().getRanges();
  var htmlEtiquetas = "";
  var huboEtiquetasValidas = false;

  for (var r = 0; r < rangosSeleccionados.length; r++) {
    var rango = rangosSeleccionados[r];
    var filaInicio = rango.getRow();
    var totalFilas = rango.getNumRows();

    for (var i = 0; i < totalFilas; i++) {
      var filaActual = filaInicio + i;

      var clienteTexto = hoja.getRange(filaActual, 7).getValue();
      var tarjetasBuenas = hoja.getRange(filaActual, 19).getValue();
      var totalTarjetas = Number(tarjetasBuenas);
      
      // Capturar valor de la columna E (índice 5) para la Ubicación
      var valorUbicacion = hoja.getRange(filaActual, 5).getValue();
      var ubicacionTexto = valorUbicacion ? valorUbicacion.toString().trim() : "-";

      // Si no hay cliente o la Columna S no tiene tarjetas buenas (> 0), ignorar
      if (!clienteTexto || clienteTexto.toString().trim() === "" || isNaN(totalTarjetas) || totalTarjetas <= 0) {
        continue;
      }

      huboEtiquetasValidas = true;

      // Extraer [CÓDIGO] y Descripción
      var codigo = "";
      var descripcion = clienteTexto.toString().trim();

      var match = descripcion.match(/(\[[^\]]+\])/);
      if (match) {
        codigo = match[1];
        descripcion = descripcion.replace(codigo, "").trim();
      }

      // Calcular paquetes
      var totalPaquetes = Math.ceil(totalTarjetas / cantPorPaquete);

      for (var p = 1; p <= totalPaquetes; p++) {
        var cantEtiqueta = cantPorPaquete;

        if (p === totalPaquetes && (totalTarjetas % cantPorPaquete !== 0)) {
          cantEtiqueta = totalTarjetas % cantPorPaquete;
        }

        htmlEtiquetas += `
        <div class="pagina-etiqueta">
          <div class="codigo-box">${codigo}</div>
          <div class="descripcion-box">${descripcion}</div>
          <div class="ubicacion-box">UB : ${ubicacionTexto}</div>
          <div class="cantidad-box">Cantidad: ${cantEtiqueta}</div>
        </div>
        `;
      }
    }
  }

  if (!huboEtiquetasValidas) {
    throw new Error('No hay tarjetas buenas registradas en la Columna S para la selección.');
  }

  // Estilos HTML / CSS optimizados para etiquetas de 88mm x 28mm
  var htmlCompleto = `
  <html>
    <head>
      <style>
        @page { 
          size: 88mm 28mm; 
          margin: 0mm; 
        }
        *, *::before, *::after {
          box-sizing: border-box;
        }
        body { 
          margin: 0; 
          padding: 0; 
          font-family: Arial, Helvetica, sans-serif; 
          color: #000000;
          background-color: #ffffff;
        }
        
        .pagina-etiqueta {
          width: 88mm;
          height: 28mm;
          position: relative;
          page-break-after: always;
          padding: 1.5mm 3mm;
          overflow: hidden;
        }
        .pagina-etiqueta:last-of-type {
          page-break-after: auto;
        }
        
        /* Código entre corchetes */
        .codigo-box {
          text-align: center;
          font-size: 14pt;
          font-weight: bold;
          line-height: 1.1;
          margin-top: 0.5mm;
          margin-bottom: 1mm;
        }
        
        /* Descripción principal */
        .descripcion-box {
          text-align: center;
          font-size: 12.5pt;
          font-weight: bold;
          line-height: 1.15;
          text-transform: uppercase;
          max-height: 12mm;
          overflow: hidden;
        }
        
        /* Ubicación en la esquina inferior izquierda (2pt más grande que cantidad) */
        .ubicacion-box {
          position: absolute;
          bottom: 1.5mm;
          left: 3mm;
          font-size: 12pt;
          font-weight: bold;
          text-align: left;
          background: #ffffff;
          padding-right: 2mm;
        }

        /* Cantidad en la esquina inferior derecha */
        .cantidad-box {
          position: absolute;
          bottom: 1.5mm;
          right: 3mm;
          font-size: 10pt;
          font-weight: bold;
          text-align: right;
          background: #ffffff;
          padding-left: 2mm;
        }
      </style>
    </head>
    <body>
      ${htmlEtiquetas}
    </body>
  </html>
  `;

  var pdfBlob = Utilities.newBlob(htmlCompleto, "text/html").getAs("application/pdf");
  return Utilities.base64Encode(pdfBlob.getBytes());
}

/**
 * HTML/JS del Sidebar con interfaz NeoCalculo.
 */
function obtenerHtmlSidebarProductos_() {
  return `
  <!DOCTYPE html>
  <html>
    <head>
      <base target="_top">
      <style>
        * {
          box-sizing: border-box;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        body {
          padding: 10px;
          margin: 0;
          background-color: #f8f9fa;
        }
        .card-container {
          background-color: #fffdfa;
          border: 1.5px solid #f39c12;
          border-radius: 10px;
          padding: 14px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        }
        .info-box {
          background-color: #fdf5e6;
          border: 1px solid #fce3b5;
          border-radius: 6px;
          padding: 10px;
          font-size: 12px;
          color: #2c3e50;
          margin-bottom: 14px;
          word-wrap: break-word;
          line-height: 1.5;
        }
        .tag-no-buenas {
          display: inline-block;
          color: #b03a2e;
          background-color: #fadbd8;
          padding: 1px 6px;
          border-radius: 4px;
          font-weight: 600;
          font-size: 11.5px;
        }
        .form-group {
          margin-bottom: 12px;
        }
        label {
          display: block;
          font-size: 12px;
          font-weight: bold;
          margin-bottom: 4px;
          color: #d35400;
          text-transform: uppercase;
          letter-spacing: 0.2px;
        }
        input[type="number"] {
          width: 100%;
          padding: 8px 10px;
          border: 1px solid #fce3b5;
          border-radius: 6px;
          font-size: 13px;
          color: #333;
          background-color: #ffffff;
          outline: none;
          transition: border-color 0.2s;
        }
        input[type="number"]:focus {
          border-color: #e67e00;
          box-shadow: 0 0 3px rgba(230, 126, 0, 0.3);
        }
        .btn-principal {
          width: 100%;
          background: linear-gradient(to bottom, #f39c12, #e67e00);
          color: white;
          border: none;
          padding: 11px;
          border-radius: 6px;
          font-weight: bold;
          cursor: pointer;
          font-size: 14px;
          margin-top: 6px;
          box-shadow: 0 2px 4px rgba(230, 126, 0, 0.2);
          transition: all 0.2s ease;
        }
        .btn-principal:hover {
          background: linear-gradient(to bottom, #e67e00, #d35400);
        }
        .btn-principal:disabled {
          background: #e0e0e0;
          color: #a0a0a0;
          box-shadow: none;
          cursor: not-allowed;
        }
        .error {
          color: #c0392b;
          background-color: #fadbd8;
          border-color: #f5b7b1;
        }
        .status-msg {
          font-size: 12px;
          color: #d35400;
          margin-top: 10px;
          text-align: center;
          font-weight: 500;
        }
      </style>
    </head>
    <body>

      <div class="card-container">
        <div class="info-box" id="info-seleccion">
          Cargando resumen de la selección...
        </div>

        <form id="etiquetas-form">
          <div class="form-group">
            <label for="cantPaquete">Cantidad por paquete</label>
            <input type="number" id="cantPaquete" min="1" placeholder="Ej: 250" required>
          </div>

          <button type="submit" id="btn-submit" class="btn-principal">Generar Etiquetas</button>
        </form>

        <div id="mensaje-status"></div>
      </div>

      <script>
        window.onload = function() {
          google.script.run
            .withSuccessHandler(function(resumen) {
              var textoExtra = resumen.filasValidas > 1 ? ' (' + resumen.filasValidas + ' filas)' : '';
              var cantTexto = resumen.tieneTarjetasBuenas 
                ? resumen.totalTarjetas 
                : '<span class="tag-no-buenas">No hay tarjetas buenas</span>';
              
              document.getElementById('info-seleccion').innerHTML = 
                '<strong style="color:#d35400;">Cliente:</strong> ' + resumen.muestraCliente + textoExtra + '<br>' +
                '<strong style="color:#d35400;">Total Tarjetas:</strong> ' + cantTexto;

              // Deshabilitar el botón si no hay tarjetas buenas
              if (!resumen.tieneTarjetasBuenas) {
                document.getElementById('btn-submit').disabled = true;
              }
            })
            .withFailureHandler(function(err) {
              var infoBox = document.getElementById('info-seleccion');
              infoBox.className = 'info-box error';
              infoBox.innerHTML = err.message;
              document.getElementById('btn-submit').disabled = true;
            })
            .obtenerResumenSeleccion();
        };

        document.getElementById('etiquetas-form').addEventListener('submit', function(e) {
          e.preventDefault();

          var paquete = parseInt(document.getElementById('cantPaquete').value, 10);
          var btn = document.getElementById('btn-submit');
          var status = document.getElementById('mensaje-status');

          btn.disabled = true;
          status.innerHTML = '<p class="status-msg">Generando PDF de etiquetas...</p>';

          google.script.run
            .withSuccessHandler(function(pdfBase64) {
              btn.disabled = false;
              status.innerHTML = '';
              
              var byteCharacters = atob(pdfBase64);
              var byteNumbers = new Array(byteCharacters.length);
              for (var i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
              }
              var byteArray = new Uint8Array(byteNumbers);
              var blob = new Blob([byteArray], {type: 'application/pdf'});
              var blobUrl = URL.createObjectURL(blob);
              
              window.open(blobUrl, '_blank');
            })
            .withFailureHandler(function(err) {
              btn.disabled = false;
              status.innerHTML = '<p class="status-msg" style="color:#c0392b;">' + err.message + '</p>';
            })
            .generarPDFProductosDesdeSidebar(paquete);
        });
      </script>
    </body>
  </html>
  `;
}