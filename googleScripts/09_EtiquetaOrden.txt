function generarEtiquetasSeleccionadasPDF() {
  var hoja = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  
  // =========================================================================
  // 1. CAPTURA DE TODAS LAS SELECCIONES (JUNTAS O SEPARADAS CON CTRL/CMD)
  // =========================================================================
  var rangosSeleccionados = hoja.getActiveRangeList().getRanges();
  
  var htmlEtiquetas = "";
  var huboEtiquetasValidas = false;

  // =========================================================================
  // 2. BUCLE: RECORRE CADA GRUPO SELECCIONADO Y SUS FILAS
  // =========================================================================
  for (var r = 0; r < rangosSeleccionados.length; r++) {
    var rango = rangosSeleccionados[r];
    var filaInicio = rango.getRow();
    var totalFilas = rango.getNumRows();
    
    // OPTIMIZACIÓN: Obtenemos todos los datos del rango seleccionado a la vez.
    // Leemos desde la Columna B (2) hasta la F (6), lo que equivale a 5 columnas.
    var datos = hoja.getRange(filaInicio, 2, totalFilas, 5).getDisplayValues();
    
    for (var i = 0; i < totalFilas; i++) {
      var filaActual = filaInicio + i;

      // PREVENCIÓN: Si la fila está oculta por un filtro o por el usuario, la ignoramos
      if (hoja.isRowHiddenByFilter(filaActual) || hoja.isRowHiddenByUser(filaActual)) {
        continue;
      }

      // Extracción de datos desde el array (índice 0 = Col B, 2 = Col D, 3 = Col E, 4 = Col F)
      var orden = datos[i][0];
      var cliente = datos[i][2];
      var producto = datos[i][3];
      var cantidad = datos[i][4];

      // Si la celda de la orden está vacía, la ignora
      if (!orden || orden.toString().trim() === "") {
        continue;
      }
      
      huboEtiquetasValidas = true;

      // Acumula el HTML de cada etiqueta
      htmlEtiquetas += `
      <div class="pagina-etiqueta">
        <div class="contenedor">
          <div class="orden">${orden}</div>
          <div class="datos">
            
            <div class="bloque">
              <div class="titulo">Cliente:</div>
              <div class="valor">${cliente}</div>
            </div>
            
            <div class="bloque">
              <div class="titulo">Producto:</div>
              <div class="valor">${producto}</div>
            </div>
            
            <div class="bloque">
              <div class="titulo">Cantidad:</div>
              <div class="valor">${cantidad}</div>
            </div>
            
          </div>
        </div>
      </div>
      `;
    }
  }

  // Si se seleccionaron celdas vacías sin datos útiles, avisa y cancela
  if (!huboEtiquetasValidas) {
    SpreadsheetApp.getUi().alert("Aviso: No se encontraron filas válidas y visibles con número de orden en tu selección.");
    return;
  }

  // =========================================================================
  // 3. ENSAMBLADO HTML 
  // =========================================================================
  var htmlCompleto = `
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="utf-8">
      <style>
        @page { size: 88mm 28mm; margin: 0; }
        
        html, body { 
          margin: 0; 
          padding: 0; 
          width: 88mm; 
          height: 28mm; 
          font-family: Arial, sans-serif; 
        }
        
        * { box-sizing: border-box; }
        
        /* Cada etiqueta ocupa exactamente el tamaño impreso */
        .pagina-etiqueta {
          width: 88mm;
          height: 28mm;
          padding: 1.5mm 2mm; 
          display: flex;
          align-items: center;    
          justify-content: center; 
          page-break-after: always;
        }
        
        .pagina-etiqueta:last-of-type {
          page-break-after: auto;
        }
        
        /* Contenedor principal */
        .contenedor { 
          display: flex; 
          width: 100%;
          height: 100%; 
          align-items: center; 
        }
        
        /* Columna vertical de la Orden */
        .orden {
          writing-mode: vertical-rl;
          transform: rotate(180deg);
          font-size: 18pt; 
          font-weight: bold;
          text-align: center;
          flex-shrink: 0;
          margin-right: 2.5mm;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        /* Bloque de datos */
        .datos {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: space-between; 
          height: 100%;
        }
        
        /* Adaptación dinámica */
        .bloque { 
          display: flex;
          flex-direction: column;
          justify-content: center;
        }
        
        .titulo { 
          font-size: 6pt; 
          font-weight: normal; 
          color: #333; 
          margin: 0; 
          line-height: 1; 
        }
        
        .valor { 
          font-size: 8.5pt; 
          font-weight: bold; 
          margin: 0; 
          line-height: 1.1; 
          word-break: break-word; 
        }
      </style>
    </head>
    <body>
      ${htmlEtiquetas}
    </body>
  </html>
  `;

  // =========================================================================
  // 4. APERTURA DIRECTA DEL DIÁLOGO DE IMPRESIÓN
  // =========================================================================
  var htmlBase64 = Utilities.base64Encode(htmlCompleto, Utilities.Charset.UTF_8);
  
  var uiHtml = `
  <!DOCTYPE html>
  <html>
  <head>
    <meta charset="utf-8">
    <style>
      body { font-family: Arial, sans-serif; text-align: center; margin: 0; padding-top: 15px; background: #f9f9f9; }
      iframe { display: none; }
    </style>
  </head>
  <body>
    <div>Abriendo diálogo de impresión...</div>
    
    <iframe id="printFrame"></iframe>

    <script>
      window.onload = function() {
        var base64Str = "${htmlBase64}";
        
        var binString = atob(base64Str);
        var bytes = Uint8Array.from(binString, (m) => m.codePointAt(0));
        var htmlContent = new TextDecoder().decode(bytes);
        
        var iframe = document.getElementById('printFrame');
        var pri = iframe.contentWindow || iframe.contentDocument;
        
        pri.document.open();
        pri.document.write(htmlContent);
        pri.document.close();
        
        setTimeout(function() {
          pri.focus();
          pri.print();
          
          setTimeout(function() {
            google.script.host.close();
          }, 1000);
        }, 500);
      };
    </script>
  </body>
  </html>
  `;
  
  var ui = HtmlService.createHtmlOutput(uiHtml).setWidth(300).setHeight(70);
  SpreadsheetApp.getUi().showModalDialog(ui, "Imprimiendo Etiquetas");
}