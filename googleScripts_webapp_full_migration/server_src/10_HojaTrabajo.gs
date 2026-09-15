// ==========================================
// SCRIPT 1: Generador de Etiquetas A4 (Orden en Columna C) - VERSIÓN MÚLTIPLES IMÁGENES Y TEXTO
// ==========================================

function solicitarImagenYGenerarPDF() {
  var uiHtml = `
  <!DOCTYPE html>
  <html>
  <head>
    <meta charset="utf-8">
    <base target="_top">
    <style>
      * { box-sizing: border-box; }
      body { font-family: Arial, sans-serif; margin: 0; padding: 12px; color: #333; background-color: #fcfcfc; }
      .card { background: #fffbf5; border: 1px solid #f39c12; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
      h3 { margin-top: 0; font-size: 15px; color: #d35400; border-bottom: 2px solid #f39c12; padding-bottom: 6px; margin-bottom: 12px; }
      p { margin: 5px 0; font-size: 13px; }
      
      .campo-input { margin-top: 12px; }
      .campo-input label { font-size: 12px; font-weight: bold; color: #d35400; display: block; margin-bottom: 4px; }
      .campo-input input, .campo-input textarea { width: 100%; padding: 8px; border: 1px solid #f39c12; border-radius: 4px; font-size: 13px; font-family: Arial, sans-serif; }
      .campo-input textarea { resize: vertical; }

      #zona-pegado {
        border: 2px dashed #f39c12; padding: 20px 10px; text-align: center;
        background-color: #ffffff; color: #d35400; cursor: pointer;
        border-radius: 6px; font-weight: bold; margin-top: 15px; transition: all 0.2s ease;
        font-size: 13px;
      }
      #zona-pegado:focus { outline: none; border-color: #d35400; background-color: #fdebd0; }
      
      #contenedor-vistas-previas {
        display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px;
      }
      .vista-previa {
        max-width: 80px; max-height: 80px; border: 1px solid #fdebd0; border-radius: 4px; object-fit: contain;
      }
      
      .controles { margin-top: 15px; }
      button {
        display: block; width: 100%; background-color: #f39c12; color: white;
        border: none; padding: 10px; border-radius: 4px; cursor: pointer;
        font-size: 13px; font-weight: bold; text-align: center;
        transition: background-color 0.2s;
      }
      button:hover { background-color: #d35400; }
      button:disabled { background-color: #d5dbdb; color: #7f8c8d; cursor: not-allowed; }
    </style>
  </head>
  <body>
    <div class="card">
      <h3>Generador A4</h3>
      <p><b>1.</b> Selecciona celdas en la hoja.</p>
      <p><b>2.</b> Pega imagen/es (Ctrl+V) y/o agrega texto.</p>
      
      <div class="campo-input">
        <label for="cant-pack">Cantidad por Pack:</label>
        <input type="number" id="cant-pack" value="0" min="0" />
      </div>

      <div id="zona-pegado" contenteditable="true">Haz clic aquí y pega imagen/es (Ctrl+V)</div>
      
      <!-- Contenedor para mostrar múltiples imágenes -->
      <div id="contenedor-vistas-previas"></div>
      
      <div class="campo-input">
        <label for="texto-extra">Texto Adicional (Opcional):</label>
        <textarea id="texto-extra" rows="3" placeholder="Ingresa texto para mostrar debajo de las fotos..."></textarea>
      </div>
      
      <div class="controles">
        <button id="btn-generar" onclick="enviarAlServidor()">Generar PDF A4</button>
      </div>
    </div>

    <script>
      var imagenesB64 = []; // Arreglo para guardar múltiples imágenes
      
      document.getElementById('zona-pegado').addEventListener('paste', function(e) {
        e.preventDefault();
        var items = (e.clipboardData || e.originalEvent.clipboardData).items;
        var encontroImagen = false;
        
        for (var i = 0; i < items.length; i++) {
          if (items[i].type.indexOf('image') !== -1) {
            encontroImagen = true;
            var blob = items[i].getAsFile();
            var reader = new FileReader();
            reader.onload = function(event) {
              var b64 = event.target.result;
              imagenesB64.push(b64); // Guardar en el arreglo
              
              // Crear elemento visual para la vista previa
              var img = document.createElement('img');
              img.src = b64;
              img.className = 'vista-previa';
              document.getElementById('contenedor-vistas-previas').appendChild(img);
              
              // Actualizar el área de pegado
              var zona = document.getElementById('zona-pegado');
              zona.innerText = "¡Imagen pegada! (Puedes pegar más)";
              zona.style.borderColor = "#27ae60"; zona.style.backgroundColor = "#eafaf1"; zona.style.color = "#27ae60";
            };
            reader.readAsDataURL(blob);
          }
        }
        
        if (!encontroImagen) {
          // Si pegan texto puro por error en la zona de imagen, lo pasamos al textarea
          var textoPegado = (e.originalEvent || e).clipboardData.getData('text/plain');
          if (textoPegado) {
             var txtExtra = document.getElementById('texto-extra');
             txtExtra.value = txtExtra.value + (txtExtra.value ? " " : "") + textoPegado;
          }
        }
      });

      function enviarAlServidor() {
        var btn = document.getElementById('btn-generar');
        btn.disabled = true;
        btn.innerText = "Generando PDF...";

        var cantPackVal = document.getElementById('cant-pack').value;
        var cantPack = (cantPackVal !== "" && cantPackVal !== null) ? cantPackVal : 0;
        
        var textoExtra = document.getElementById('texto-extra').value;

        google.script.run
          .withSuccessHandler(function(pdfBase64) {
            btn.disabled = false;
            btn.innerText = "Generar PDF A4";

            if (!pdfBase64) {
              alert("No se encontraron filas con datos. Asegúrate de seleccionar una fila que contenga al menos un Producto o Cliente.");
              return;
            }
            
            var byteCharacters = atob(pdfBase64);
            var byteNumbers = new Array(byteCharacters.length);
            for (var i = 0; i < byteCharacters.length; i++) {
              byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            var byteArray = new Uint8Array(byteNumbers);
            var blob = new Blob([byteArray], {type: 'application/pdf'});
            var blobUrl = URL.createObjectURL(blob);
            
            var a = document.createElement('a');
            a.href = blobUrl;
            a.target = '_blank';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          })
          .withFailureHandler(function(err) {
            alert("Error al generar PDF: " + err.message);
            btn.disabled = false;
            btn.innerText = "Generar PDF A4";
          })
          // Pasamos el arreglo de imágenes y el texto extra
          .procesarEtiquetasA4(imagenesB64, cantPack, textoExtra);
      }
    </script>
  </body>
  </html>
  `;
  
  var ui = HtmlService.createHtmlOutput(uiHtml).setTitle("Generador de Etiquetas");
  SpreadsheetApp.getUi().showSidebar(ui);
}

function procesarEtiquetasA4(imagenesB64, cantPack, textoExtra) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var range = sheet.getActiveRange();
  if (!range) return null;
  
  var startRow = range.getRow();
  var numRows = range.getNumRows();
  var lastCol = sheet.getLastColumn();
  
  var fullData = sheet.getRange(startRow, 1, numRows, lastCol).getValues();

  var idxOrden     = 2;  // Columna C: Número de Orden
  var idxCliente   = 3;  // Columna D: Cliente
  var idxProducto  = 4;  // Columna E: Producto
  var idxCantidad  = 5;  // Columna F: Cantidad
  var idxEntrega   = 7;  // Columna H: Fecha de Entrega
  var idxNotas     = 9;  // Columna J: Notas/Especificaciones
  var idxPrioridad = 13; // Columna N: Prioridad

  var valCantPack  = (cantPack !== undefined && cantPack !== null && cantPack !== "") ? cantPack : 0;

  var htmlContent = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
    '@page { size: A4; margin: 8mm; } ' +
    '* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; box-sizing: border-box; } ' +
    'body { font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; color: #000; } ' +
    '.etiqueta { border: 2px solid #000000; padding: 15px; border-radius: 8px; page-break-inside: avoid; page-break-after: always; max-height: 275mm; overflow: hidden; } ' +
    '.tabla-header { width: 100%; border-collapse: collapse; margin-bottom: 12px; } ' +
    '.campo { margin-bottom: 10px; } ' +
    '.tabla-triple { width: 100%; border-collapse: collapse; margin-bottom: 10px; } ' +
    '.tabla-triple td { border: none !important; padding: 0 !important; vertical-align: top; } ' +
    '.lbl { font-size: 10px; font-weight: bold; color: #555555; text-transform: uppercase; margin-bottom: 2px; } ' +
    '.val { font-size: 20px; font-weight: bold; margin: 0; color: #000000; line-height: 1.1; } ' +
    
    // TABLA UNIFICADA CON COLUMNA DE TARJETAS DE 30MM Y SUBENCABEZADOS GRISES
    '.tabla-unificada { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 10px; } ' +
    '.tabla-unificada th, .tabla-unificada td { border: 1px solid #000000; height: 7mm; max-height: 7mm; padding: 0 4px; vertical-align: middle; box-sizing: border-box; } ' +
    '.tabla-unificada th { font-size: 12px; font-weight: bold; background-color: #f5f5f5; text-align: center; } ' +
    '.tabla-unificada td.cat-tarjeta { font-size: 11px; font-weight: bold; text-align: center; background-color: #f5f5f5; } ' +
    
    '.caja-notas { background-color: #333333; color: #ffffff; padding: 8px 12px; font-size: 13px; font-weight: bold; border-radius: 4px; margin-top: 8px; display: inline-block; } ' +
    
    // CONTENEDOR MULTIPLES IMÁGENES
    '.img-box { text-align: center; margin-top: 10px; font-size: 0; } ' +
    '.img-box img { display: inline-block; max-height: 140px; max-width: 48%; margin: 4px; object-fit: contain; vertical-align: top; border: 1px solid #ddd; border-radius: 4px;} ' +
    
    // TEXTO ADICIONAL
    '.texto-extra { margin-top: 10px; padding: 10px; font-size: 13px; font-weight: bold; color: #333; border-top: 1px dashed #ccc; text-align: center; white-space: pre-wrap; } ' +
    '</style></head><body>';

  var etiquetasGeneradas = 0;

  for (var i = 0; i < fullData.length; i++) {
    var fila = fullData[i];
    
    var valCliente = sanitizarHTML_Unico(fila[idxCliente]).trim();
    var valProducto = sanitizarHTML_Unico(fila[idxProducto]).trim();
    
    if (!valCliente && !valProducto) continue;
    if (valCliente.toLowerCase() === 'cliente' || valProducto.toLowerCase() === 'producto') continue;

    var orden     = fila[idxOrden];
    var cliente   = fila[idxCliente];
    var producto  = fila[idxProducto];
    var cantidad  = fila[idxCantidad];
    var entrega   = fila[idxEntrega];
    var notas     = fila[idxNotas];
    var prioRaw   = String(fila[idxPrioridad] !== null && fila[idxPrioridad] !== undefined ? fila[idxPrioridad] : "").trim();

    var fechaFormateada = formatearFechaEntrega(entrega);

    // Lógica de colores según prioridad
    var bgColor = "";
    var textColor = "#000000";
    var tieneColor = false;

    if (prioRaw.indexOf("1") !== -1) {
      bgColor = "#cc0000";   // Rojo
      textColor = "#ffffff"; // Texto Blanco
      tieneColor = true;
    } else if (prioRaw.indexOf("2") !== -1) {
      bgColor = "#f1c232";   // Amarillo
      textColor = "#000000"; // Texto Negro
      tieneColor = true;
    } else if (prioRaw.indexOf("3") !== -1) {
      bgColor = "#38761d";   // Verde
      textColor = "#ffffff"; // Texto Blanco
      tieneColor = true;
    }

    var styleTdBase = "padding: 8px 10px; -webkit-print-color-adjust: exact; print-color-adjust: exact;";
    var styleTdLeft = styleTdBase + " font-size: 14px; font-weight: bold; text-align: left;";
    var styleTdRight = styleTdBase + " font-size: 22px; font-weight: bold; text-align: right;";

    if (tieneColor) {
      styleTdLeft += " background-color: " + bgColor + "; color: " + textColor + ";";
      styleTdRight += " background-color: " + bgColor + "; color: " + textColor + ";";
    } else {
      styleTdLeft += " color: #444444; border-bottom: 2px solid #000000;";
      styleTdRight += " color: #000000; border-bottom: 2px solid #000000;";
    }

    htmlContent += '<div class="etiqueta">' +
      '<table class="tabla-header">' +
        '<tr>' +
          '<td style="' + styleTdLeft + '">ETIQUETA DE ENVÍO / PRODUCCIÓN</td>' +
          '<td style="' + styleTdRight + '">ORDEN: ' + sanitizarHTML_Unico(orden) + '</td>' +
        '</tr>' +
      '</table>' +

      '<div class="campo">' +
        '<div class="lbl">CLIENTE:</div>' +
        '<div class="val">' + sanitizarHTML_Unico(cliente) + '</div>' +
      '</div>' +

      '<div class="campo">' +
        '<div class="lbl">PRODUCTO:</div>' +
        '<div class="val">' + sanitizarHTML_Unico(producto) + '</div>' +
      '</div>' +

      '<table class="tabla-triple">' +
        '<tr>' +
          '<td style="width: 30%; text-align: left;">' +
            '<div class="lbl">CANTIDAD:</div>' +
            '<div class="val">' + sanitizarHTML_Unico(cantidad) + '</div>' +
          '</td>' +
          '<td style="width: 38%; text-align: center;">' +
            '<div class="lbl">CANTIDAD POR PACK:</div>' +
            '<div class="val">' + sanitizarHTML_Unico(valCantPack) + '</div>' +
          '</td>' +
          '<td style="width: 32%; text-align: right;">' +
            '<div class="lbl">FECHA DE ENTREGA:</div>' +
            '<div class="val">' + fechaFormateada + '</div>' +
          '</td>' +
        '</tr>' +
      '</table>' +

      // ESTRUCTURA UNIFICADA CON ANCHO FIJO DE 30MM EN TARJETAS
      '<table class="tabla-unificada">' +
        '<thead>' +
          '<tr>' +
            '<th>Etapa</th>' +
            '<th style="width: 35%;">Responsable</th>' +
            '<th style="width: 30mm;">Tarjetas</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>' +
          '<tr><td></td><td></td><td class="cat-tarjeta">Laminadas</td></tr>' +
          '<tr><td></td><td></td><td></td></tr>' +
          '<tr><td></td><td></td><td class="cat-tarjeta">Malas</td></tr>' +
          '<tr><td></td><td></td><td></td></tr>' +
          '<tr><td></td><td></td><td class="cat-tarjeta">Para completar</td></tr>' +
          '<tr><td></td><td></td><td></td></tr>' +
        '</tbody>' +
      '</table>';

    var notasSanitizadas = sanitizarHTML_Unico(notas);
    if (notasSanitizadas) {
      htmlContent += '<div class="caja-notas">' + notasSanitizadas + '</div>';
    }

    // MULTIPLES IMÁGENES
    if (imagenesB64 && imagenesB64.length > 0) {
      htmlContent += '<div class="img-box">';
      for (var j = 0; j < imagenesB64.length; j++) {
        htmlContent += '<img src="' + imagenesB64[j] + '" />';
      }
      htmlContent += '</div>';
    }

    // TEXTO EXTRA
    if (textoExtra && textoExtra.trim() !== "") {
      htmlContent += '<div class="texto-extra">' + sanitizarHTML_Unico(textoExtra.trim()) + '</div>';
    }

    htmlContent += '</div>';
    etiquetasGeneradas++;
  }

  htmlContent += '</body></html>';

  if (etiquetasGeneradas === 0) return null;

  var blob = HtmlService.createHtmlOutput(htmlContent).getBlob().getAs('application/pdf');
  return Utilities.base64Encode(blob.getBytes());
}

function formatearFechaEntrega(val) {
  if (val === null || val === undefined || String(val).trim() === "") {
    return "-- STOCK --";
  }

  var dias = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
  var meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

  var fecha;

  if (val instanceof Date) {
    fecha = val;
  } else {
    var strVal = String(val).trim();
    var partes = strVal.split(/[-/ ]+/);
    
    if (partes.length >= 2) {
      var diaNum = parseInt(partes[0], 10);
      var mesTxt = partes[1].toLowerCase();
      
      var mapaMeses = {
        'jan': 0, 'ene': 0, '1': 0, '01': 0,
        'feb': 1, '2': 1, '02': 1,
        'mar': 2, '3': 2, '03': 2,
        'apr': 3, 'abr': 3, '4': 3, '04': 3,
        'may': 4, '5': 4, '05': 4,
        'jun': 5, '6': 5, '06': 5,
        'jul': 6, '7': 6, '07': 6,
        'aug': 7, 'ago': 7, '8': 7, '08': 7,
        'sep': 8, 'set': 8, '9': 8, '09': 8,
        'oct': 9, '10': 9,
        'nov': 10, '11': 10,
        'dec': 11, 'dic': 11, '12': 11
      };
      
      var mesNum = mapaMeses[mesTxt];
      
      if (!isNaN(diaNum) && mesNum !== undefined) {
        var año = (partes.length >= 3 && !isNaN(parseInt(partes[2], 10))) 
                  ? parseInt(partes[2], 10) 
                  : new Date().getFullYear();
        if (año < 100) año += 2000;
        
        fecha = new Date(año, mesNum, diaNum);
      }
    }
    
    if (!fecha || isNaN(fecha.getTime())) {
      fecha = new Date(strVal);
    }
  }

  if (!fecha || isNaN(fecha.getTime())) {
    return sanitizarHTML_Unico(val);
  }

  var nombreDia = dias[fecha.getDay()];
  var numDia = fecha.getDate();
  var nombreMes = meses[fecha.getMonth()];

  return nombreDia + " " + numDia + " " + nombreMes;
}

function sanitizarHTML_Unico(val) {
  if (val === null || val === undefined) return '';
  var str = '';
  if (val instanceof Date) {
    str = Utilities.formatDate(val, Session.getScriptTimeZone(), "dd/MM/yyyy");
  } else {
    str = String(val);
  }
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}