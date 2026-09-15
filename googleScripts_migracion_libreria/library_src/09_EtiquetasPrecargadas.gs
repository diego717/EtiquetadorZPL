// ==========================================
// SCRIPT 2: Visor de PDFs en Google Drive (Diseño en Dos Líneas)
// ==========================================

const FOLDER_ID = "1ETmJbVNtREYMWmLBDuChZRMCLVYIpsnB";

function abrirVisorPDFs() {
  const htmlContent = `
    <!DOCTYPE html>
    <html>
      <head>
        <base target="_top">
        <style>
          * { box-sizing: border-box; }
          body { font-family: Arial, sans-serif; margin: 0; padding: 12px; color: #333; background-color: #fcfcfc; }
          .card { background: #fffbf5; border: 1px solid #f39c12; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
          h3 { margin-top: 0; font-size: 15px; color: #d35400; border-bottom: 2px solid #f39c12; padding-bottom: 6px; margin-bottom: 12px; }
          #contenedor-lista { border: 1px solid #fdebd0; border-radius: 4px; height: calc(100vh - 150px); overflow-y: auto; margin-bottom: 12px; background: #ffffff; }
          
          .item-pdf { 
            padding: 10px 12px; 
            border-bottom: 1px solid #fdebd0; 
            cursor: pointer; 
            color: #333; 
            font-size: 12px; 
            word-break: break-word; 
          }
          .item-pdf:hover { background-color: #fdebd0; }
          .item-pdf.seleccionado { background-color: #f39c12; color: #ffffff; }
          .item-pdf.seleccionado .linea-secundaria { color: #fdfefe; }

          .linea-principal {
            font-weight: bold;
            font-size: 13px;
            display: block;
            margin-bottom: 2px;
          }
          .linea-secundaria {
            font-size: 11px;
            color: #666;
            display: block;
            line-height: 1.2;
          }
          
          .btn-imprimir {
            display: block; width: 100%; background-color: #f39c12; color: white;
            border: none; padding: 10px; border-radius: 4px; cursor: pointer;
            font-size: 13px; font-weight: bold; text-align: center; text-decoration: none;
            transition: background-color 0.2s;
          }
          .btn-imprimir:hover { background-color: #d35400; }
          .btn-imprimir:disabled { background-color: #d5dbdb; color: #7f8c8d; cursor: not-allowed; }
          
          #cargando { text-align: center; padding: 20px 10px; color: #7e5109; font-size: 13px; font-weight: bold; }
        </style>
      </head>
      <body>
        <div class="card">
          <h3>Gestor de Etiquetas</h3>
          <div id="contenedor-lista">
            <div id="cargando">Cargando archivos desde Google Drive...</div>
          </div>
          <div class="acciones">
            <button id="btnImprimir" class="btn-imprimir" disabled onclick="abrirPDFDirecto()">Selecciona un PDF</button>
          </div>
        </div>

        <script>
          let archivoSeleccionadoId = null;

          window.onload = function() {
            google.script.run
              .withSuccessHandler(mostrarArchivos)
              .withFailureHandler(mostrarError)
              .obtenerListaPDFs();
          };

          function mostrarArchivos(archivos) {
            const contenedor = document.getElementById('contenedor-lista');
            contenedor.innerHTML = '';

            if (archivos.length === 0) {
              contenedor.innerHTML = '<div id="cargando">No se encontraron archivos PDF.</div>';
              return;
            }

            archivos.forEach(archivo => {
              const div = document.createElement('div');
              div.className = 'item-pdf';
              
              // Separar el texto por el símbolo '#'
              if (archivo.nombre.includes('#')) {
                let partes = archivo.nombre.split('#');
                let parte1 = partes[0].trim();
                let parte2 = partes.slice(1).join('#').trim(); // Por si hay más de un '#'
                
                div.innerHTML = '<span class="linea-principal">' + parte1 + '</span>' +
                                '<span class="linea-secundaria">' + parte2 + '</span>';
              } else {
                div.innerHTML = '<span class="linea-principal">' + archivo.nombre + '</span>';
              }
              
              div.onclick = function() {
                document.querySelectorAll('.item-pdf').forEach(el => el.classList.remove('seleccionado'));
                div.classList.add('seleccionado');
                
                archivoSeleccionadoId = archivo.id;
                
                const btn = document.getElementById('btnImprimir');
                btn.textContent = 'Abrir e Imprimir PDF';
                btn.disabled = false;
              };
              contenedor.appendChild(div);
            });
          }

          function mostrarError(err) {
            document.getElementById('contenedor-lista').innerHTML = '<div id="cargando" style="color:#c0392b;">' + err.message + '</div>';
          }

          function abrirPDFDirecto() {
            if (!archivoSeleccionadoId) return;

            var btn = document.getElementById('btnImprimir');
            btn.disabled = true;
            btn.textContent = "Obteniendo archivo...";

            var nuevaPestana = window.open('', '_blank');
            nuevaPestana.document.write("<h3 style='font-family:sans-serif; padding:20px; color:#333;'>Cargando etiqueta desde Drive, por favor espera...</h3>");

            google.script.run
              .withSuccessHandler(function(pdfBase64) {
                var byteCharacters = atob(pdfBase64);
                var byteNumbers = new Array(byteCharacters.length);
                for (var i = 0; i < byteCharacters.length; i++) {
                  byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                var byteArray = new Uint8Array(byteNumbers);
                var blob = new Blob([byteArray], {type: 'application/pdf'});
                var blobUrl = URL.createObjectURL(blob);
                
                nuevaPestana.location.href = blobUrl;
                
                btn.disabled = false;
                btn.textContent = 'Abrir e Imprimir PDF';
              })
              .withFailureHandler(function(err) {
                nuevaPestana.close();
                alert("Error al abrir PDF: " + err.message);
                btn.disabled = false;
                btn.textContent = 'Abrir e Imprimir PDF';
              })
              .obtenerBase64PDFDrive(archivoSeleccionadoId);
          }
        </script>
      </body>
    </html>
  `;

  const htmlOutput = HtmlService.createHtmlOutput(htmlContent).setTitle('Impresión de Etiquetas');
  SpreadsheetApp.getUi().showSidebar(htmlOutput);
}

function obtenerListaPDFs() {
  try {
    const folder = DriveApp.getFolderById(FOLDER_ID);
    const files = folder.getFilesByType(MimeType.PDF);
    const pdfs = [];

    while (files.hasNext()) {
      const file = files.next();
      let nombreLimpio = file.getName().replace(/\.pdf$/i, '');
      pdfs.push({
        nombre: nombreLimpio,
        id: file.getId()
      });
    }

    pdfs.sort((a, b) => a.nombre.localeCompare(b.nombre, undefined, { numeric: true, sensitivity: 'base' }));
    return pdfs;
  } catch (error) {
    throw new Error('Error al acceder a la carpeta: ' + error.message);
  }
}

function obtenerBase64PDFDrive(fileId) {
  try {
    const file = DriveApp.getFileById(fileId);
    const blob = file.getBlob();
    return Utilities.base64Encode(blob.getBytes());
  } catch (e) {
    throw new Error('No se pudo leer el archivo de Drive: ' + e.message);
  }
}