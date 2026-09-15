/** ----------------------- GENERACIÓN DE ETIQUETAS EN TIEMPO REAL ----------------------- */

/**
 * Función principal para abrir la barra lateral (Sidebar).
 */
function EtiquetaParaProductos() {
  var ui = SpreadsheetApp.getUi();
  var htmlOutput = HtmlService.createHtmlOutput(obtenerHtmlSidebarManual_())
      .setTitle('Generar Etiqueta')
      .setWidth(320);

  ui.showSidebar(htmlOutput);
}

/**
 * Extrae todos los productos y códigos de la hoja ETIQUETAS para la búsqueda en tiempo real.
 */
function obtenerDatosEtiquetas() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("ETIQUETAS");
  if (!sheet) {
    throw new Error('No se encontró la hoja "ETIQUETAS".');
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 4) {
    return [];
  }

  // Obtenemos las columnas G (7) y H (8) desde la fila 4
  var data = sheet.getRange(4, 7, lastRow - 3, 2).getValues();
  var catalogo = [];

  for (var i = 0; i < data.length; i++) {
    var valProducto = String(data[i][0] || "").trim(); // Columna G
    var valCodigo = String(data[i][1] || "").trim();   // Columna H
    
    if (valProducto || valCodigo) {
      catalogo.push({
        producto: valProducto,
        codigo: valCodigo
      });
    }
  }

  return catalogo;
}

/**
 * Recibe el ítem seleccionado desde el Sidebar y genera el PDF.
 */
function generarPDFDesdeSeleccion(datos) {
  if (!datos || (!datos.producto && !datos.codigo)) {
    throw new Error('No se recibieron datos válidos para generar la etiqueta.');
  }

  var codigoPuro = datos.codigo;
  var codigoConCorchetes = codigoPuro ? "[" + codigoPuro + "]" : "";
  var descripcion = datos.producto;
  var codigoBarras = codigoPuro ? "*" + codigoPuro + "*" : "";
  
  var htmlEtiquetas = `
    <div class="pagina-etiqueta">
      <div class="barcode">${codigoBarras}</div>
      <div class="codigo">${codigoConCorchetes}</div>
      <div class="descripcion">${descripcion}</div>
    </div>
  `;

  var htmlCompleto = `
  <html>
    <head>
      <link href="https://fonts.googleapis.com/css?family=Libre+Barcode+39" rel="stylesheet">
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
          padding: 1mm 2mm;
          overflow: hidden;
          text-align: center;
          display: flex;
          flex-direction: column;
          justify-content: flex-start;
          align-items: center;
        }
        .pagina-etiqueta:last-of-type {
          page-break-after: auto;
        }
        
        .barcode {
          font-family: 'Libre Barcode 39', cursive;
          font-size: 32pt;
          line-height: 0.7; 
          font-weight: normal;
          margin-top: 0mm;
          margin-bottom: 1mm;
          color: #000;
          width: 100%;
        }
        
        .codigo {
          font-size: 13pt;
          font-weight: bold;
          line-height: 1;
          letter-spacing: 0.5px;
          margin-bottom: 1mm;
        }
        
        .descripcion {
          font-size: 10.5pt;
          font-weight: bold;
          line-height: 1.1;
          text-transform: uppercase;
          width: 100%;
          word-wrap: break-word;
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
 * Interfaz HTML del Sidebar con estilo NeoCálculo y buscador dinámico.
 */
function obtenerHtmlSidebarManual_() {
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
          display: flex;
          flex-direction: column;
          height: 95vh;
        }
        .form-group {
          margin-bottom: 12px;
        }
        label {
          display: block;
          font-size: 11px;
          font-weight: bold;
          margin-bottom: 4px;
          color: #d35400;
          text-transform: uppercase;
          letter-spacing: 0.2px;
        }
        input[type="text"] {
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
        input:focus {
          border-color: #e67e00;
          box-shadow: 0 0 3px rgba(230, 126, 0, 0.3);
        }
        
        .resultados-wrapper {
          flex-grow: 1;
          display: flex;
          flex-direction: column;
          margin-bottom: 10px;
          min-height: 0; 
        }
        #lista-resultados {
          flex-grow: 1;
          border: 1px solid #e0e0e0;
          border-radius: 6px;
          background: #fff;
          overflow-y: auto;
          margin: 0;
          padding: 0;
          list-style: none;
        }
        .resultado-item {
          padding: 8px 10px;
          border-bottom: 1px solid #f0f0f0;
          cursor: pointer;
          transition: background 0.1s;
        }
        .resultado-item:last-child {
          border-bottom: none;
        }
        .resultado-item:hover {
          background-color: #fef5e7;
        }
        .resultado-item.seleccionado {
          background-color: #fce3b5;
          border-left: 3px solid #e67e00;
        }
        .res-cod {
          font-size: 11px;
          font-weight: bold;
          color: #d35400;
          display: block;
        }
        .res-prod {
          font-size: 12px;
          color: #333;
          display: block;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
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
          box-shadow: 0 2px 4px rgba(230, 126, 0, 0.2);
          transition: all 0.2s ease;
        }
        .btn-principal:hover:not(:disabled) {
          background: linear-gradient(to bottom, #e67e00, #d35400);
        }
        .btn-principal:disabled {
          background: #e0e0e0;
          color: #a0a0a0;
          box-shadow: none;
          cursor: not-allowed;
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
        
        <div class="form-group">
          <label for="producto">Buscar por Producto</label>
          <input type="text" id="producto" placeholder="Ej: Nombre del Producto" disabled>
        </div>

        <div class="form-group">
          <label for="codigo">Buscar por Código</label>
          <input type="text" id="codigo" placeholder="Ej: COD123" disabled>
        </div>

        <div class="resultados-wrapper">
          <label>Resultados (Selecciona uno)</label>
          <ul id="lista-resultados">
            <li style="padding: 10px; font-size: 12px; color: #888; text-align: center;">Cargando base de datos...</li>
          </ul>
        </div>

        <button type="button" id="btn-submit" class="btn-principal" disabled>Generar PDF</button>
        <div id="mensaje-status"></div>

      </div>

      <script>
        let baseDatos = [];
        let itemSeleccionado = null;
        
        const inputProd = document.getElementById('producto');
        const inputCod = document.getElementById('codigo');
        const listaResultados = document.getElementById('lista-resultados');
        const btnSubmit = document.getElementById('btn-submit');
        const statusMsg = document.getElementById('mensaje-status');

        window.onload = function() {
          google.script.run
            .withSuccessHandler(function(datos) {
              baseDatos = datos;
              inputProd.disabled = false;
              inputCod.disabled = false;
              listaResultados.innerHTML = '<li style="padding: 10px; font-size: 12px; color: #888; text-align: center;">Escribe para buscar...</li>';
            })
            .withFailureHandler(function(err) {
              listaResultados.innerHTML = '<li style="padding: 10px; color: #c0392b;">Error al cargar datos.</li>';
            })
            .obtenerDatosEtiquetas();
        };

        inputProd.addEventListener('input', filtrarResultados);
        inputCod.addEventListener('input', filtrarResultados);

        function filtrarResultados() {
          const qProd = inputProd.value.trim().toLowerCase();
          const qCod = inputCod.value.trim().toLowerCase();
          
          itemSeleccionado = null; 
          btnSubmit.disabled = true;

          if (!qProd && !qCod) {
            listaResultados.innerHTML = '<li style="padding: 10px; font-size: 12px; color: #888; text-align: center;">Escribe para buscar...</li>';
            return;
          }

          const resultados = baseDatos.filter(item => {
            const matchProd = item.producto.toLowerCase().includes(qProd);
            const matchCod = item.codigo.toLowerCase().includes(qCod);
            
            if (qProd && qCod) return matchProd && matchCod;
            if (qProd) return matchProd;
            if (qCod) return matchCod;
            return false;
          });

          renderizarLista(resultados);
        }

        function renderizarLista(resultados) {
          listaResultados.innerHTML = '';
          
          if (resultados.length === 0) {
            listaResultados.innerHTML = '<li style="padding: 10px; font-size: 12px; color: #c0392b; text-align: center;">No hay coincidencias</li>';
            return;
          }

          resultados.forEach((item) => {
            const li = document.createElement('li');
            li.className = 'resultado-item';
            li.innerHTML = \`
              <span class="res-cod">\${item.codigo || '-'}</span>
              <span class="res-prod">\${item.producto || '-'}</span>
            \`;
            
            li.onclick = () => seleccionarItem(item, li);
            listaResultados.appendChild(li);
          });
        }

        function seleccionarItem(item, elementoLi) {
          const items = listaResultados.getElementsByClassName('resultado-item');
          for (let i = 0; i < items.length; i++) {
            items[i].classList.remove('seleccionado');
          }
          
          elementoLi.classList.add('seleccionado');
          itemSeleccionado = item;
          btnSubmit.disabled = false;
        }

        btnSubmit.addEventListener('click', function() {
          if (!itemSeleccionado) return;

          btnSubmit.disabled = true;
          statusMsg.innerHTML = '<p class="status-msg">Generando PDF...</p>';

          google.script.run
            .withSuccessHandler(function(pdfBase64) {
              btnSubmit.disabled = false;
              statusMsg.innerHTML = '';
              
              const byteCharacters = atob(pdfBase64);
              const byteNumbers = new Array(byteCharacters.length);
              for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
              }
              const byteArray = new Uint8Array(byteNumbers);
              const blob = new Blob([byteArray], {type: 'application/pdf'});
              const blobUrl = URL.createObjectURL(blob);
              
              window.open(blobUrl, '_blank');
            })
            .withFailureHandler(function(err) {
              btnSubmit.disabled = false;
              statusMsg.innerHTML = '<p class="status-msg" style="color:#c0392b;">' + err.message + '</p>';
            })
            .generarPDFDesdeSeleccion(itemSeleccionado);
        });
      </script>
    </body>
  </html>
  `;
}