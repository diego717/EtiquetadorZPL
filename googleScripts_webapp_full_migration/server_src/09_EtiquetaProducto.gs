/** ----------------------- GENERACIÓN DE ETIQUETAS EN SIDEBAR - HOJA TRABAJOS ----------------------- */

/**
 * Función principal para abrir la barra lateral (Sidebar) de generación de etiquetas.
 * Se debe ejecutar cuando el usuario está en la hoja "TRABAJOS".
 */
function generarEtiquetasTrabajosPDF() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var hojaActual = ss.getActiveSheet();
  var ui = SpreadsheetApp.getUi();

  // 1. Verificar que el usuario esté ubicado en la hoja "TRABAJOS"
  if (hojaActual.getName() !== "TRABAJOS") {
    ui.alert('Aviso: Debe estar ubicado en la hoja "TRABAJOS" para ejecutar esta función.');
    return;
  }

  // 2. Crear y mostrar la barra lateral con el tema NeoCalculo
  var htmlOutput = HtmlService.createHtmlOutput(obtenerHtmlSidebar_())
      .setTitle('NeoCalculo - Etiquetas')
      .setWidth(320);

  ui.showSidebar(htmlOutput);
}

/**
 * Obtiene la información de la fila activa en la Columna E (Columna 5).
 * Llamado desde el cliente HTML en el Sidebar.
 */
function obtenerDatosFilaActiva() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var hojaActual = ss.getActiveSheet();

  if (hojaActual.getName() !== "TRABAJOS") {
    throw new Error('Debe estar ubicado en la hoja "TRABAJOS".');
  }

  var filaActiva = hojaActual.getActiveCell().getRow();
  var textoColumnaE = hojaActual.getRange(filaActiva, 5).getValue();

  if (!textoColumnaE || textoColumnaE.toString().trim() === "") {
    throw new Error('La celda de la Columna E en la fila ' + filaActiva + ' está vacía.');
  }

  return {
    fila: filaActiva,
    texto: textoColumnaE.toString().trim()
  };
}

/**
 * Procesa los datos del formulario, construye las etiquetas en HTML/CSS 
 * y devuelve el PDF renderizado en formato Base64.
 */
function generarPDFDesdeSidebar(cantPorPaquete, cantEtiquetas) {
  var datos = obtenerDatosFilaActiva();
  var textoColumnaE = datos.texto;

  // Extraer lo que está entre corchetes [...] para la primera línea
  var codigo = "";
  var descripcion = textoColumnaE;

  var match = descripcion.match(/(\[[^\]]+\])/);
  if (match) {
    codigo = match[1]; // Extrae [CÓDIGO]
    descripcion = descripcion.replace(codigo, "").trim(); // Deja solo el resto del texto
  }

  // Construir HTML de las etiquetas
  var htmlEtiquetas = "";
  for (var p = 1; p <= cantEtiquetas; p++) {
    htmlEtiquetas += `
    <div class="pagina-etiqueta">
      <div class="codigo-box">${codigo}</div>
      <div class="descripcion-box">${descripcion}</div>
      <div class="cantidad-box">Cantidad: ${cantPorPaquete}</div>
    </div>
    `;
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
        
        /* Primera línea: Código entre corchetes */
        .codigo-box {
          text-align: center;
          font-size: 16pt;
          font-weight: bold;
          line-height: 1.1;
          margin-top: 0.5mm;
          margin-bottom: 1mm;
        }
        
        /* Líneas siguientes: Resto de la descripción */
        .descripcion-box {
          text-align: center;
          font-size: 14pt;
          font-weight: bold;
          line-height: 1.15;
          text-transform: uppercase;
          max-height: 12mm;
          overflow: hidden;
        }
        
        /* Recuadro inferior derecho: Cantidad por paquete */
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

  // Generar Blob PDF y devolver en Base64
  var pdfBlob = Utilities.newBlob(htmlCompleto, "text/html").getAs("application/pdf");
  return Utilities.base64Encode(pdfBlob.getBytes());
}

/**
 * Función interna que contiene la interfaz HTML/JS del Sidebar estilizado con el tema NeoCalculo.
 */
function obtenerHtmlSidebar_() {
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
          line-height: 1.4;
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
        <div class="info-box" id="info-fila">
          Cargando datos de la fila seleccionada...
        </div>

        <form id="etiquetas-form">
          <div class="form-group">
            <label for="cantPaquete">Unidades por paquete</label>
            <input type="number" id="cantPaquete" min="1" placeholder="0" required>
          </div>

          <div class="form-group">
            <label for="cantEtiquetas">Cantidad de etiquetas</label>
            <input type="number" id="cantEtiquetas" min="1" placeholder="0" required>
          </div>

          <button type="submit" id="btn-submit" class="btn-principal">Generar Etiquetas</button>
        </form>

        <div id="mensaje-status"></div>
      </div>

      <script>
        // Obtiene la información de la fila activa al cargar la barra lateral
        window.onload = function() {
          google.script.run
            .withSuccessHandler(function(datos) {
              document.getElementById('info-fila').innerHTML = 
                '<strong style="color:#d35400;">Fila ' + datos.fila + ' seleccionada:</strong><br>' + datos.texto;
            })
            .withFailureHandler(function(err) {
              var infoBox = document.getElementById('info-fila');
              infoBox.className = 'info-box error';
              infoBox.innerHTML = err.message;
              document.getElementById('btn-submit').disabled = true;
            })
            .obtenerDatosFilaActiva();
        };

        // Procesar formulario
        document.getElementById('etiquetas-form').addEventListener('submit', function(e) {
          e.preventDefault();

          var paquete = parseInt(document.getElementById('cantPaquete').value, 10);
          var etiquetas = parseInt(document.getElementById('cantEtiquetas').value, 10);
          var btn = document.getElementById('btn-submit');
          var status = document.getElementById('mensaje-status');

          btn.disabled = true;
          status.innerHTML = '<p class="status-msg">Generando PDF de etiquetas...</p>';

          google.script.run
            .withSuccessHandler(function(pdfBase64) {
              btn.disabled = false;
              status.innerHTML = '';
              
              // Abrir PDF en pestaña nueva mediante Blob URL
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
            .generarPDFDesdeSidebar(paquete, etiquetas);
        });
      </script>
    </body>
  </html>
  `;
}