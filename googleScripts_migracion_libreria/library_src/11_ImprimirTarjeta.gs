/**
 * ============================================================================
 * MENÚ Y BARRA LATERAL (FOTO ODOO Y PDF)
 * ============================================================================
 */

function showImageSidebar() {
  const html = HtmlService.createHtmlOutput(`
    <!DOCTYPE html>
    <html>
      <head>
        <base target="_top">
        <meta charset="utf-8">
        <style>
          * { box-sizing: border-box; }
          body { font-family: Arial, sans-serif; margin: 0; padding: 12px; color: #333; background-color: #fcfcfc; }
          .card { background: #fffbf5; border: 1px solid #f39c12; border-radius: 8px; padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
          label { display: block; font-size: 12px; color: #d35400; font-weight: bold; margin-top: 8px; margin-bottom: 4px; }
          button { width: 100%; padding: 10px; border-radius: 4px; border: 0; background: #f39c12; color: white; font-weight: bold; font-size: 13px; margin-top: 8px; cursor: pointer; transition: background-color 0.2s; }
          button:hover { background: #d35400; }
          button.secondary { background: #27ae60; color: white; }
          button.secondary:hover { background: #219653; }
          button:disabled { background: #bdc3c7; cursor: not-allowed; }
          #resultado { white-space: pre-wrap; font-size: 12px; color: #c0392b; margin-top: 8px; font-weight: bold; text-align: center; }
          .image-container { text-align: center; margin-top: 8px; background: white; border: 1px solid #fdebd0; border-radius: 4px; padding: 8px; min-height: 220px; display: flex; align-items: center; justify-content: center; }
          img { max-width: 100%; max-height: 320px; border-radius: 4px; object-fit: contain; }
          .placeholder { color: #888; font-style: italic; font-size: 12px; }
          .product-title { font-size: 13px; color: #333; font-weight: bold; margin-bottom: 6px; text-align: center; background: #fdebd0; padding: 8px; border-radius: 4px; border: 1px solid #f39c12; }
        </style>
      </head>
      <body>
        <div class="card">
          <button id="btnCargar" onclick="cargarFoto()">Actualizar / Cargar Foto</button>
        </div>

        <div class="card">
          <label>FOTO EN ODOO</label>
          <div id="lblProducto" class="product-title" style="display: none;"></div>
          <div class="image-container">
            <div id="imgPlaceholder" class="placeholder">Seleccione una celda con la tarjeta.</div>
            <img id="imgTarj" src="" style="display: none;" />
          </div>
          <button id="btnPdf" class="secondary" onclick="imprimirPdfDirecto()" style="display: none;">Imprimir PDF</button>
          <div id="resultado"></div>
        </div>

        <script>
          var currentProductData = null;

          function cargarFoto() {
            var btn = document.getElementById('btnCargar');
            var btnPdf = document.getElementById('btnPdf');
            var resDiv = document.getElementById('resultado');
            var imgEl = document.getElementById('imgTarj');
            var placeholderEl = document.getElementById('imgPlaceholder');
            var lblProducto = document.getElementById('lblProducto');

            btn.disabled = true;
            btn.textContent = 'Consultando Odoo...';
            resDiv.textContent = '';
            lblProducto.style.display = 'none';
            btnPdf.style.display = 'none';
            btnPdf.onclick = imprimirPdfDirecto;
            btnPdf.textContent = 'Imprimir PDF';
            btnPdf.disabled = false;
            currentProductData = null;

            google.script.run
              .withSuccessHandler(function(res) {
                btn.disabled = false;
                btn.textContent = 'Actualizar / Cargar Foto';

                if (!res || res.error) {
                  resDiv.style.color = '#c0392b';
                  resDiv.textContent = res ? res.error : 'Error: Respuesta vacía del servidor.';
                  imgEl.style.display = 'none';
                  placeholderEl.style.display = 'block';
                  placeholderEl.textContent = res ? res.error : 'Error.';
                  return;
                }

                if (!res.found) {
                  imgEl.style.display = 'none';
                  placeholderEl.style.display = 'block';
                  placeholderEl.textContent = res.message;
                  return;
                }

                currentProductData = res;

                if (res.productName) {
                  lblProducto.textContent = res.productName;
                  lblProducto.style.display = 'block';
                }

                if (res.image) {
                  imgEl.src = 'data:image/png;base64,' + res.image;
                  imgEl.style.display = 'block';
                  placeholderEl.style.display = 'none';
                }

                btnPdf.style.display = 'block';
              })
              .withFailureHandler(function(err) {
                btn.disabled = false;
                btn.textContent = 'Actualizar / Cargar Foto';
                resDiv.style.color = '#c0392b';
                resDiv.textContent = 'Error: ' + (err.message || err);
              })
              .obtenerInfoTarjetaSeleccionada();
          }

          // Construye el archivo localmente y lo abre para impresión nativa
          function procesarYAbrirPdf(base64Data) {
            var byteCharacters = atob(base64Data.replace(/\\s/g, ''));
            var byteNumbers = new Array(byteCharacters.length);
            for (var i = 0; i < byteCharacters.length; i++) {
              byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            var byteArray = new Uint8Array(byteNumbers);
            var blob = new Blob([byteArray], {type: 'application/pdf'});
            var blobUrl = URL.createObjectURL(blob);

            // Crea un enlace fantasma y lo clica para abrir la pestaña de impresión nativa
            var a = document.createElement('a');
            a.href = blobUrl;
            a.target = '_blank';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }

          function imprimirPdfDirecto() {
            if (!currentProductData) return;
            var btnPdf = document.getElementById('btnPdf');
            var resDiv = document.getElementById('resultado');

            btnPdf.disabled = true;
            btnPdf.textContent = 'Generando archivo de impresión...';
            resDiv.textContent = '';

            google.script.run
              .withSuccessHandler(function(pdfData) {
                if (pdfData && pdfData.base64) {
                  btnPdf.disabled = false;
                  btnPdf.textContent = 'IMPRIMIR PDF';
                  
                  // Evento manual por si el bloqueador de ventanas emergentes actúa
                  btnPdf.onclick = function() {
                    procesarYAbrirPdf(pdfData.base64);
                  };

                  // Intento de apertura automática
                  try {
                    procesarYAbrirPdf(pdfData.base64);
                    resDiv.style.color = '#27ae60';
                    resDiv.textContent = 'Listo. Si no se abrió, haz clic en IMPRIMIR PDF.';
                  } catch(e) {
                    resDiv.style.color = '#d35400';
                    resDiv.textContent = 'Bloqueado por el navegador. Haz clic en IMPRIMIR PDF para abrirlo.';
                  }

                } else {
                  btnPdf.disabled = false;
                  btnPdf.textContent = 'Imprimir PDF';
                  resDiv.style.color = '#c0392b';
                  resDiv.textContent = 'No se encontró el archivo PDF en Drive.';
                }
              })
              .withFailureHandler(function(err) {
                btnPdf.disabled = false;
                btnPdf.textContent = 'Imprimir PDF';
                resDiv.style.color = '#c0392b';
                resDiv.textContent = 'Error: ' + (err.message || err);
              })
              .obtenerBase64PdfDrive(currentProductData);
          }

          window.onload = function() {
            cargarFoto();
          };
        </script>
      </body>
    </html>
  `).setTitle('Impresión de tarjetas');

  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * ============================================================================
 * PROCESAMIENTO DE CELDA Y BÚSQUEDA EN ODOO
 * ============================================================================
 */

function obtenerInfoTarjetaSeleccionada() {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    const cell = sheet.getActiveCell();
    const value = String(cell.getValue() || '');

    if (!value) {
      return { error: 'La celda activa está vacía.' };
    }

    let codigo = value.trim();
    const match = value.match(/\[(.*?)\]/);
    if (match && match[1]) {
      codigo = match[1].trim();
    }

    const resultadoOdoo = buscarImagenOdooPorCodigo(codigo);

    return {
      celdaValor: value,
      codigoBuscado: codigo,
      ...resultadoOdoo
    };
  } catch (e) {
    return { error: 'Error al procesar: ' + e.message };
  }
}

function buscarImagenOdooPorCodigo(codigo) {
  const cfg = getOdooCfg_();
  if (!isOdooConfigReady_(cfg)) {
    throw new Error("Las credenciales de Odoo no están configuradas en las propiedades del script.");
  }

  const uid = getOdooUid_(cfg);

  let domain = [["default_code", "=", codigo]];
  let fields = ["id", "name", "default_code", "image_1920"];

  let products = executeKw_(cfg, uid, 'product.template', 'search_read', [domain], {
    "fields": fields,
    "limit": 1
  });

  if (!products || products.length === 0) {
    domain = [["name", "ilike", codigo]];
    products = executeKw_(cfg, uid, 'product.template', 'search_read', [domain], {
      "fields": fields,
      "limit": 1
    });
  }

  if (!products || products.length === 0) {
    return { found: false, message: `No se encontró el producto "${codigo}" en Odoo.` };
  }

  const product = products[0];
  if (!product.image_1920) {
    return { 
      found: true, 
      productName: product.name, 
      defaultCode: product.default_code, 
      image: null, 
      message: 'El producto existe en Odoo pero no tiene imagen cargada.' 
    };
  }

  return {
    found: true,
    productName: product.name,
    defaultCode: product.default_code,
    image: product.image_1920,
    message: ''
  };
}

/**
 * ============================================================================
 * BÚSQUEDA DE PDF EN CARPETA DE DRIVE
 * ============================================================================
 */

function obtenerBase64PdfDrive(data) {
  try {
    const folderId = '1NMevoHAjN5eHuHjPWCuR6PDJZFBQDEHZ';
    const folder = DriveApp.getFolderById(folderId);

    const terminosBusqueda = [];
    if (data.defaultCode) terminosBusqueda.push(data.defaultCode.toLowerCase());
    if (data.codigoBuscado && !terminosBusqueda.includes(data.codigoBuscado.toLowerCase())) {
      terminosBusqueda.push(data.codigoBuscado.toLowerCase());
    }
    if (data.productName) terminosBusqueda.push(data.productName.toLowerCase());

    const files = folder.getFilesByType(MimeType.PDF);
    let archivoEncontrado = null;

    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName().toLowerCase();

      for (let i = 0; i < terminosBusqueda.length; i++) {
        if (fileName.includes(terminosBusqueda[i])) {
          archivoEncontrado = file;
          break;
        }
      }
      if (archivoEncontrado) break;
    }

    if (archivoEncontrado) {
      const bytes = archivoEncontrado.getBlob().getBytes();
      const base64 = Utilities.base64Encode(bytes);
      
      // Se eliminó intencionalmente el .getUrl() de Drive. 
      // Solo devolvemos la base64 pura para forzar el visor nativo.
      return { 
        base64: base64, 
        fileName: archivoEncontrado.getName() 
      };
    }

    return null;
  } catch (e) {
    throw new Error('Error al leer el PDF de Drive: ' + e.message);
  }
}

/**
 * Conexion y API JSON-RPC de Odoo: odooLogin_, executeKw_, rpc_,
 * getOdooCfg_, isOdooConfigReady_ y cleanString_ vivian duplicadas aca
 * (copia identica) y en 02_OdooConexion.txt / 07_utilidades.txt. Se
 * eliminaron estas copias porque Apps Script no garantiza cual de las
 * dos definiciones queda activa cuando dos archivos declaran la misma
 * funcion en el mismo proyecto ("This project contains one or more
 * functions with the same name..."). Las versiones canonicas son las de
 * 02_OdooConexion.txt (conexion Odoo) y 07_utilidades.txt (cleanString_).
 */