// Code.gs - NeoCalculo completo (todo en un solo archivo .gs)

/**
 * Muestra la barra lateral con la UI embebida
 */
function showSidebar() {
  const html = HtmlService.createHtmlOutput(getSidebarHtml())
    .setTitle('NeoCalculo');
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * HTML embebido para la barra lateral
 */
function getSidebarHtml() {
  return `
  <!DOCTYPE html>
  <html>
    <head>
      <base target="_top">
      <meta charset="utf-8">
      <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 0; padding: 12px; color: #333; background-color: #fcfcfc; }
        .card { background: #fffbf5; border: 1px solid #f39c12; border-radius: 8px; padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        label { display: block; font-size: 12px; color: #d35400; font-weight: bold; margin-top: 8px; }
        input, select { width: 100%; padding: 6px 8px; margin-top: 4px; border-radius: 4px; border: 1px solid #fdebd0; box-sizing: border-box; font-size: 13px; background: #ffffff; color: #333; }
        input:focus, select:focus { outline: none; border-color: #f39c12; background-color: #fff; }
        input[type="radio"] { width: auto; margin: 0 4px 0 0; cursor: pointer; }
        button { width: 100%; padding: 10px; border-radius: 4px; border: 0; background: #f39c12; color: white; font-weight: bold; font-size: 13px; margin-top: 10px; cursor: pointer; transition: background-color 0.2s; }
        button:hover { background: #d35400; }
        #resultado { white-space: pre-wrap; color: #333; font-weight: bold; margin-top: 10px; min-height: 48px; line-height: 1.5; font-size: 13px; background: #fdebd0; padding: 8px; border-radius: 4px; border: 1px solid #f39c12; }
        canvas { width: 100%; border: 1px solid #fdebd0; background: white; display: block; margin-top: 8px; border-radius: 4px; }
        .row { display: flex; gap: 8px; }
        .col { flex: 1; }
        .inline-label { font-size: 12px; color: #d35400; font-weight: bold; margin-bottom: 4px; display: block; }
        
        /* Contenedor horizontal para la orientación */
        .radio-group { display: flex; gap: 16px; align-items: center; margin-top: 6px; }
        .radio-option { display: inline-flex; align-items: center; font-size: 13px; color: #333; margin: 0; cursor: pointer; font-weight: normal; }
      </style>
    </head>
    <body>
      <div class="card">
        <label>ACTIVIDAD A EJECUTAR</label>
        <select id="actividad">
          <option>Cartelería Spectar (Plancha)</option>
          <option>Laminado (A4)</option>
          <option>Fotocopia (A3+)</option>
        </select>

        <div class="row">
          <div class="col">
            <label>Alto pieza (mm)</label>
            <input id="alto" type="number" value="200" min="0">
          </div>
          <div class="col">
            <label>Ancho pieza (mm)</label>
            <input id="ancho" type="number" value="150" min="0">
          </div>
        </div>

        <div class="row">
          <div class="col">
            <label>Cantidad total piezas</label>
            <input id="cantidad" type="number" value="50" min="1">
          </div>
          <div class="col">
            <label>Margen hoja (mm)</label>
            <input id="margen" type="number" value="0" min="0">
          </div>
        </div>

        <div class="row">
          <div class="col">
            <label>Calle vertical (mm)</label>
            <input id="calle_v" type="number" value="0" min="0">
          </div>
          <div class="col">
            <label>Calle horizontal (mm)</label>
            <input id="calle_h" type="number" value="0" min="0">
          </div>
        </div>

        <!-- Espesor y Costo en la misma línea -->
        <div class="row">
          <div class="col">
            <span class="inline-label">Espesor del material</span>
            <select id="espesor">
              <option>2.0 mm</option>
              <option>1.5 mm</option>
              <option>0.9 mm</option>
            </select>
          </div>
          <div class="col">
            <span class="inline-label">Costo base ($)</span>
            <input id="costo" type="number" value="2100" min="0">
          </div>
        </div>

        <!-- Orientación en una sola línea -->
        <label>Orientación de la Hoja</label>
        <div class="radio-group">
          <label class="radio-option"><input type="radio" name="orient" value="Vertical" checked> Vertical</label>
          <label class="radio-option"><input type="radio" name="orient" value="Horizontal"> Horizontal</label>
        </div>

        <button id="btnCalcular">Calcular Producción</button>

        <div id="resultado">Realice un cálculo para ver los costos.</div>
      </div>

      <div class="card">
        <label>Esquema de distribución</label>
        <canvas id="canvas" width="600" height="750"></canvas>
      </div>

      <script>
        const actividadEl = document.getElementById('actividad');
        const espesorEl = document.getElementById('espesor');
        const altoEl = document.getElementById('alto');
        const anchoEl = document.getElementById('ancho');
        const cantidadEl = document.getElementById('cantidad');
        const margenEl = document.getElementById('margen');
        const calleVEl = document.getElementById('calle_v');
        const calleHEl = document.getElementById('calle_h');
        const costoEl = document.getElementById('costo');
        const resultadoEl = document.getElementById('resultado');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');

        function getOrientacion() {
          const radios = document.getElementsByName('orient');
          for (const r of radios) if (r.checked) return r.value;
          return 'Vertical';
        }

        function actualizarDefaults() {
          const act = actividadEl.value;

          /**************************************************************
           *   BLOQUE UI 1: CARTELERÍA SPECTAR
           **************************************************************/
          if (act === 'Cartelería Spectar (Plancha)') {
            espesorEl.parentElement.style.display = 'block';
            espesorEl.value = '2.0 mm';
            altoEl.value = 200;
            anchoEl.value = 150;
            cantidadEl.value = 50;
            costoEl.value = 2100;
            margenEl.value = 0;
            calleVEl.value = 0;
            calleHEl.value = 0;
          } 
          /**************************************************************
           *   BLOQUE UI 2: LAMINADO (A4)
           **************************************************************/
          else if (act === 'Laminado (A4)') {
            espesorEl.parentElement.style.display = 'none';
            altoEl.value = 85;
            anchoEl.value = 54;
            cantidadEl.value = 100;
            costoEl.value = 400;
            margenEl.value = 5;
            calleVEl.value = 0;
            calleHEl.value = 0;
          } 
          /**************************************************************
           *   BLOQUE UI 3: FOTOCOPIA (A3+)
           **************************************************************/
          else if (act === 'Fotocopia (A3+)') {
            espesorEl.parentElement.style.display = 'none';
            altoEl.value = 100;
            anchoEl.value = 100;
            cantidadEl.value = 50;
            costoEl.value = 800;
            margenEl.value = 10;
            calleVEl.value = 5;
            calleHEl.value = 5;
          }
        }

        actividadEl.addEventListener('change', actualizarDefaults);
        actualizarDefaults();

        document.getElementById('btnCalcular').addEventListener('click', () => {
          const payload = {
            actividad: actividadEl.value,
            alto: altoEl.value,
            ancho: anchoEl.value,
            cantidad: cantidadEl.value,
            costo: costoEl.value,
            espesor: espesorEl.value,
            margen: margenEl.value,
            calle_v: calleVEl.value,
            calle_h: calleHEl.value,
            orientacion: getOrientacion()
          };
          resultadoEl.textContent = 'Calculando...';
          google.script.run.withSuccessHandler(onResultado).calcularServer(payload);
        });

        let ultimoDatos = null;

        function onResultado(res) {
          if (!res) {
            resultadoEl.textContent = 'Error inesperado.';
            return;
          }
          if (res.error) {
            resultadoEl.textContent = 'Error: ' + res.error;
            ultimoDatos = null;
            clearCanvas();
            return;
          }
          resultadoEl.textContent = res.resultado_texto;
          ultimoDatos = res.datos;
          drawEsquema(ultimoDatos);
        }

        function clearCanvas() {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        function drawEsquema(datos) {
          clearCanvas();
          const canvas_w = canvas.width;
          const canvas_h = canvas.height;

          const escala = Math.min((canvas_w - 60) / datos.hoja_w, (canvas_h - 60) / datos.hoja_h);
          const offset_x = (canvas_w - (datos.hoja_w * escala)) / 2;
          const offset_y = (canvas_h - (datos.hoja_h * escala)) / 2;

          // Fondo hoja
          ctx.fillStyle = '#fffbf5';
          ctx.fillRect(offset_x, offset_y, datos.hoja_w * escala, datos.hoja_h * escala);
          ctx.strokeStyle = '#f39c12';
          ctx.lineWidth = 2;
          ctx.strokeRect(offset_x, offset_y, datos.hoja_w * escala, datos.hoja_h * escala);

          // Margen perimetral interactivo
          if (datos.margen > 0) {
            const margen_escala = datos.margen * escala;
            ctx.strokeStyle = '#d35400';
            ctx.setLineDash([4,4]);
            ctx.strokeRect(offset_x + margen_escala, offset_y + margen_escala, datos.hoja_w*escala - margen_escala*2, datos.hoja_h*escala - margen_escala*2);
            ctx.setLineDash([]);
          }

          const start_x = offset_x + datos.margen * escala;
          const start_y = offset_y + datos.margen * escala;

          for (let i = 0; i < datos.num_vert; i++) {
            for (let j = 0; j < datos.num_horiz; j++) {
              // Posición considerando la pieza más su respectiva calle
              const x1 = start_x + j * (datos.acredit_w + datos.calle_h) * escala;
              const y1 = start_y + i * (datos.acredit_h + datos.calle_v) * escala;
              const w = datos.acredit_w * escala;
              const h = datos.acredit_h * escala;

              ctx.fillStyle = '#fdebd0';
              ctx.strokeStyle = '#f39c12';
              ctx.lineWidth = 1;
              ctx.fillRect(x1, y1, w, h);
              ctx.strokeRect(x1, y1, w, h);
            }
          }
        }
      </script>
    </body>
  </html>
  `;
}

/**
 * calcularServer(data)
 */
function calcularServer(data) {
  try {
    const PRECIOS_SPECTAR = {
      "2.0 mm": 2100.0,
      "1.5 mm": 1800.0,
      "0.9 mm": 1450.0
    };

    const actividad = String(data.actividad || '');
    const cantidad = Math.max(1, parseInt(data.cantidad || 1, 10));
    let costo_base = Number(data.costo || 0);
    const orientacion = String(data.orientacion || 'Vertical');
    
    const alto_real = Number(data.alto || 0);
    const ancho_real = Number(data.ancho || 0);

    const margen = (data.margen === '' || data.margen === undefined) ? 0.0 : Number(data.margen);
    const calle_v = (data.calle_v === '' || data.calle_v === undefined) ? 0.0 : Number(data.calle_v);
    const calle_h = (data.calle_h === '' || data.calle_h === undefined) ? 0.0 : Number(data.calle_h);

    if (actividad === 'Cartelería Spectar (Plancha)') {
      if (data.espesor && PRECIOS_SPECTAR[data.espesor]) {
        costo_base = PRECIOS_SPECTAR[data.espesor];
      }
    }

    let hoja_w, hoja_h, texto_unidad, texto_pieza, actividad_tipo;

    /****************************************************************************************
     *     BLOQUE 1: CARTELERÍA SPECTAR (PLANCHA)
     ****************************************************************************************/
    if (actividad === 'Cartelería Spectar (Plancha)') {
      if (orientacion === 'Vertical') {
        hoja_w = 1000; hoja_h = 2000;
      } else {
        hoja_w = 2000; hoja_h = 1000;
      }
      texto_unidad = 'Planchas';
      texto_pieza = 'pieza';
      actividad_tipo = 'SPECTAR';
    } 
    /**************************************************************************************** 
     *     BLOQUE 2: LAMINADO (A4)
     ****************************************************************************************/
    else if (actividad === 'Laminado (A4)') {
      if (orientacion === 'Vertical') {
        hoja_w = 210; hoja_h = 297;
      } else {
        hoja_w = 297; hoja_h = 210;
      }
      texto_unidad = 'Hojas A4';
      texto_pieza = 'pieza laminada';
      actividad_tipo = 'A4';
    } 
    /**************************************************************************************** 
     *     BLOQUE 3: FOTOCOPIA (A3+)
     ****************************************************************************************/
    else if (actividad === 'Fotocopia (A3+)') {
      if (orientacion === 'Vertical') {
        hoja_w = 330; hoja_h = 480;
      } else {
        hoja_w = 480; hoja_h = 330;
      }
      texto_unidad = 'Hojas A3+';
      texto_pieza = 'copia';
      actividad_tipo = 'A3+';
    }

    const ancho_util = hoja_w - (margen * 0);
    const alto_util = hoja_h - (margen * 0);

    let num_horiz = Math.floor((ancho_util + calle_h) / (ancho_real + calle_h));
    let num_vert = Math.floor((alto_util + calle_v) / (alto_real + calle_v));

    num_horiz = Math.max(0, num_horiz);
    num_vert = Math.max(0, num_vert);
    const total_por_hoja = num_horiz * num_vert;

    if (total_por_hoja === 0) {
      return { error: 'Las piezas son demasiado grandes para la hoja y márgenes actuales.' };
    }

    let ocupado_w = 0;
    let ocupado_h = 0;
    
    if (num_horiz > 0) {
      ocupado_w = (num_horiz * ancho_real) + ((num_horiz - 1) * calle_h);
    }
    if (num_vert > 0) {
      ocupado_h = (num_vert * alto_real) + ((num_vert - 1) * calle_v);
    }
    
    const sobrante_derecho = hoja_w - margen - ocupado_w;
    const sobrante_inferior = hoja_h - margen - ocupado_h;

    const hojas = Math.ceil(cantidad / total_por_hoja);
    const costo_unitario = (costo_base * hojas) / cantidad;

    const resultado_texto =
      `• Piezas por ${texto_unidad.toLowerCase()}: ${total_por_hoja}\n` +
      `• ${texto_unidad} necesarias: ${hojas}\n` +
      `• Costo unitario por ${texto_pieza}: $${costo_unitario.toFixed(2)}\n` +
      `• Margen restante en la hoja:\n` +
      `    Lado derecho: ${sobrante_derecho.toFixed(1)} mm\n` + 
      `    Lado inferior: ${sobrante_inferior.toFixed(1)} mm`;

    const datos = {
      actividad: actividad,
      hoja_w: hoja_w,
      hoja_h: hoja_h,
      acredit_w: ancho_real,
      acredit_h: alto_real,
      num_horiz: num_horiz,
      num_vert: num_vert,
      orientacion: orientacion,
      margen: margen,
      calle_v: calle_v,
      calle_h: calle_h,
      actividad_tipo: actividad_tipo
    };

    return { resultado_texto: resultado_texto, datos: datos };
  } catch (e) {
    return { error: 'Error en el cálculo: ' + (e && e.message ? e.message : String(e)) };
  }
}