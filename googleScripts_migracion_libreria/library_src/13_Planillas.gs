// ==========================================
// SCRIPT COMPLETO: Visor de Planillas, Textos y PDF
// ==========================================

function abrirVisorPlanillas() {
  const htmlContent = `
    <!DOCTYPE html>
    <html>
      <head>
        <base target="_top">
        <style>
          * { box-sizing: border-box; }
          body { font-family: Arial, sans-serif; margin: 0; padding: 10px; color: #333; background-color: #fcfcfc; }
          
          .card-main { background: #f6fdf8; border: 1px solid #0f9d58; border-radius: 8px; padding: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
          h3 { margin-top: 0; font-size: 14px; color: #0b8043; border-bottom: 2px solid #0f9d58; padding-bottom: 6px; margin-bottom: 10px; }
          
          #contenedor-lista { 
            border: 1px solid #ceead6; 
            border-radius: 4px; 
            height: calc(100vh - 85px); 
            overflow-y: auto; 
            overflow-x: auto; 
            padding: 6px;
            background: #ffffff; 
          }
          
          .grupo-card {
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            margin-bottom: 10px;
            background-color: #f8f9fa;
            overflow-x: auto;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
          }
          
          .grupo-titulo {
            font-size: 12px;
            font-weight: bold;
            color: #1e8e3e;
            background-color: #e6f4ea;
            padding: 6px 8px;
            border-bottom: 1px solid #ceead6;
            white-space: nowrap;
          }
          
          .grupo-archivos {
            display: flex;
            flex-direction: column;
          }
          
          .item-planilla { 
            display: flex;
            align-items: center;
            padding: 6px 8px; 
            border-bottom: 1px solid #f1f3f4; 
            cursor: pointer; 
            color: #333; 
            text-decoration: none;
            transition: background-color 0.2s;
            background-color: #ffffff;
            width: max-content;
            min-width: 100%;
          }
          .item-planilla:hover { background-color: #f1f8f3; }
          .item-planilla:last-child { border-bottom: none; }
          
          .icono { margin-right: 6px; font-size: 14px; flex-shrink: 0; }
          
          .linea-principal {
            font-size: 11px;
            font-weight: 500;
            white-space: nowrap;
            display: inline-block;
          }
          
          #cargando { text-align: center; padding: 20px 10px; color: #0b8043; font-size: 13px; font-weight: bold; }
        </style>
      </head>
      <body>
        <div class="card-main">
          <h3>Planillas, Txt y PDF</h3>
          <div id="contenedor-lista">
            <div id="cargando">Cargando archivos desde Google Drive...</div>
          </div>
        </div>

        <script>
          document.addEventListener('DOMContentLoaded', function() {
            google.script.run
              .withSuccessHandler(mostrarArchivos)
              .withFailureHandler(mostrarError)
              .obtenerListaPlanillas();
          });

          function mostrarArchivos(grupos) {
            const contenedor = document.getElementById('contenedor-lista');
            contenedor.innerHTML = '';

            if (!grupos || grupos.length === 0) {
              contenedor.innerHTML = '<div id="cargando">No se encontraron planillas, textos ni PDF.</div>';
              return;
            }

            grupos.forEach(grupo => {
              const divGrupo = document.createElement('div');
              divGrupo.className = 'grupo-card';

              const divTitulo = document.createElement('div');
              divTitulo.className = 'grupo-titulo';
              divTitulo.textContent = '📂 ' + grupo.titulo;
              divGrupo.appendChild(divTitulo);

              const divArchivos = document.createElement('div');
              divArchivos.className = 'grupo-archivos';

              grupo.archivos.forEach(archivo => {
                const enlace = document.createElement('a');
                enlace.className = 'item-planilla';
                enlace.href = archivo.url;
                enlace.target = '_blank';
                
                let icono;
                if (archivo.tipo === 'txt') {
                  icono = '📝';
                } else if (archivo.tipo === 'sheet') {
                  icono = '📊';
                } else if (archivo.tipo === 'pdf') {
                  icono = '📄';
                }
                
                enlace.innerHTML = '<span class="icono">' + icono + '</span>' +
                                   '<span class="linea-principal">' + archivo.nombre + '</span>';
                
                divArchivos.appendChild(enlace);
              });

              divGrupo.appendChild(divArchivos);
              contenedor.appendChild(divGrupo);
            });
          }

          function mostrarError(err) {
            const contenedor = document.getElementById('contenedor-lista');
            const mensaje = err && err.message ? err.message : err;
            contenedor.innerHTML = '<div id="cargando" style="color:#c0392b;">Error: ' + mensaje + '</div>';
          }
        </script>
      </body>
    </html>
  `;

  const htmlOutput = HtmlService.createHtmlOutput(htmlContent).setTitle('Gestor de Archivos');
  SpreadsheetApp.getUi().showSidebar(htmlOutput);
}

function obtenerListaPlanillas() {
  const FOLDER_PLANILLAS_ID = "16dhOQwCNqaMygJLnuHhqsWjBmKeyzj2k";
  
  try {
    const folder = DriveApp.getFolderById(FOLDER_PLANILLAS_ID);
    const listaTemporal = [];

    // 1. Obtener Google Sheets
    const filesSheets = folder.getFilesByType(MimeType.GOOGLE_SHEETS);
    while (filesSheets.hasNext()) {
      const file = filesSheets.next();
      listaTemporal.push({
        nombre: file.getName(),
        url: file.getUrl(),
        tipo: 'sheet'
      });
    }

    // 2. Obtener archivos de texto (.txt)
    const filesTxt = folder.getFilesByType(MimeType.PLAIN_TEXT);
    while (filesTxt.hasNext()) {
      const file = filesTxt.next();
      listaTemporal.push({
        nombre: file.getName(),
        url: file.getUrl(),
        tipo: 'txt'
      });
    }

    // 3. Obtener archivos PDF
    const filesPdf = folder.getFilesByType(MimeType.PDF);
    while (filesPdf.hasNext()) {
      const file = filesPdf.next();
      listaTemporal.push({
        nombre: file.getName(),
        url: file.getUrl(),
        tipo: 'pdf'
      });
    }

    // 4. Agrupar por la PRIMERA PALABRA del nombre del archivo
    const mapaGrupos = {};
    listaTemporal.forEach(archivo => {
      let primeraPalabra = archivo.nombre.trim().split(/\s+/)[0].toUpperCase();
      
      if (!mapaGrupos[primeraPalabra]) {
        mapaGrupos[primeraPalabra] = [];
      }
      mapaGrupos[primeraPalabra].push(archivo);
    });

    // 5. Convertir a Array y ordenar los archivos dentro de cada grupo por nombre completo (A-Z)
    const gruposOrdenados = Object.keys(mapaGrupos).map(nombreGrupo => {
      const archivos = mapaGrupos[nombreGrupo].sort((a, b) => 
        a.nombre.localeCompare(b.nombre, undefined, { numeric: true, sensitivity: 'base' })
      );

      return {
        titulo: nombreGrupo,
        archivos: archivos
      };
    });

    // Orden alfabético A-Z por título de grupo
    gruposOrdenados.sort((a, b) => 
      a.titulo.localeCompare(b.titulo, undefined, { numeric: true, sensitivity: 'base' })
    );

    return gruposOrdenados;
  } catch (error) {
    throw new Error('Error al acceder a la carpeta: ' + error.message);
  }
}
