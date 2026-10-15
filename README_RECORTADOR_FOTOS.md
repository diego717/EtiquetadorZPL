# Recortador de fotos para credenciales

## Nueva interfaz web

Con la API local iniciada, abrí `http://localhost:8002/web/fotos.html`. La
interfaz web permite cargar fotos o PDF, detectar rostros, ajustar el recorte,
vincular una planilla CSV/Excel, tratar fondos, generar tarjetas con logo y QR,
crear una hoja PDF de revisión y descargar el resultado por lote. Los proyectos
se pueden guardar y reabrir con sus originales y ajustes.

### Editor de credenciales

La pestaña **Tarjeta** abre un editor de diseño libre, con el mismo enfoque que
CardExchange Producer o Magicard TrustID:

- **Objetos ilimitados**: texto, foto de la persona, imágenes (logos, firmas,
  sellos), código QR, código de barras (Code 128, Code 39, EAN-13, EAN-8, UPC-A,
  ITF), rectángulo, elipse y línea.
- **Campos variables**: cualquier texto, QR o código puede combinar texto fijo y
  columnas de la planilla, por ejemplo `{Apellido}, {Nombre}` o `Legajo {Legajo}`.
  Además están `{Archivo}`, `{Nro}` (posición en el lote), `{Fecha}` y `{Año}`.
- **Propiedades por objeto**: posición y tamaño en milímetros, giro, opacidad,
  tipografía de Windows, tamaño en puntos, negrita, cursiva, subrayado,
  mayúsculas, alineación horizontal y vertical, ajuste automático (una línea o
  varias, achicando si no entra), fondo, contorno, bordes y radio.
- **Visibilidad condicional**: un objeto se imprime sólo si un campo es igual a,
  distinto de o contiene un valor, o si está vacío o completo (por ejemplo, una
  banda roja sólo para `Cargo = Gerencia`).
- **Frente y dorso**, tamaños CR80, CR79, CR100, gafetes A7/A6 o medida libre,
  orientación horizontal o vertical y plantillas listas.
- **Edición cómoda**: arrastrar, escalar desde ocho puntos, girar, selección
  múltiple y por área, guías inteligentes, imán a 1 mm, alinear y distribuir,
  orden de capas, bloquear y ocultar, copiar/pegar, duplicar y deshacer.
- **Datos por credencial**: el selector superior recorre las personas del lote y
  el panel *Datos de esta credencial* permite corregir los valores de cada una.
- **Vista exacta**: pide al servidor el mismo render que se usa al exportar.
- **Guardar diseño / Abrir diseño**: archivo `.credencial.json` con las imágenes
  incluidas, para reutilizarlo con otros lotes.

### Exportar credenciales

Desde el editor (**Exportar…**) o desde la pestaña Tarjeta se elige:

- Alcance: credencial actual, listado filtrado, sólo revisadas o todo el lote.
- Formato: PDF, PNG o JPG; caras: frente, dorso o ambas; 300 o 600 dpi.
- PDF de una credencial por página a tamaño real, o pliegos A4/Carta/Oficio con
  márgenes, separación, marcas de corte y dorso espejado para impresión dúplex.
- Nombre de archivo con campos, por ejemplo `{Apellido}_{Nombre}`.

Una sola imagen se descarga directa; varias, en un ZIP. Los proyectos guardados
con el diseñador anterior se convierten automáticamente al abrirlos.

### Imprimir en la impresora de tarjetas

Con **Imprimir…** (en el editor o en la pestaña Tarjeta) se elige *Impresora de
tarjetas* como destino. Se listan primero las impresoras de tarjetas instaladas
en Windows (Zebra, Magicard, Entrust/Datacard, Swiftpro, Evolis, Fargo) con su
estado. Cada cara se envía como una página por el controlador de la marca; en
doble faz el controlador las junta sobre la misma tarjeta. En cada trabajo se fija
la orientación y la doble faz, y la imagen cubre la página completa, de borde a
borde. Ribbon, panel negro (K), overlay y calidad se toman de las preferencias del
controlador. Si el dorso sale invertido, marcá **Girar el dorso 180°**.

Cada impresión queda marcada en la credencial (“Impresa ×2”), se guarda en el
proyecto y se registra en `%APPDATA%\EtiquetadorZPL\logs\credenciales_impresas.csv`.
El alcance **Las que no se imprimieron** permite retomar un lote a medias.

### Revisión previa

Antes de imprimir o exportar se revisa el alcance elegido con el mismo motor que
compone las tarjetas: datos faltantes, textos que no entran o se achicaron
demasiado, códigos de barras inválidos o demasiado finos, QR muy densos, imágenes
sin cargar, fotos con observaciones y credenciales ya impresas. Cada observación
abre esa credencial en el editor. Si hay errores, se pide confirmación antes de
imprimir.

### Encuadre de la foto dentro de la credencial

Al seleccionar la foto del diseño aparece **Encuadre de todas las fotos**: avisa si
la proporción del recorte no coincide con la caja y permite elegir el *tamaño del
rostro* y la *altura de los ojos* (con valores sugeridos distintos para cajas
circulares y rectangulares). Al soltar un control se previsualiza en la credencial
actual; **Encuadrar todas las fotos en esta caja** aplica la misma proporción y el
mismo encuadre facial a todo el lote. La detección de cada foto se recuerda, así
que reencuadrar es instantáneo; las fotos sin rostro detectado quedan centradas y
se informan. Esos valores también se usan en **Detectar y encuadrar todo** y se
guardan en el proyecto.

Para retocar una sola, doble clic sobre la foto (modo **Encuadre**): arrastrar
mueve la foto, la rueda acerca o aleja, y Enter termina.

En el listado, hacé clic en una foto y usá `↑`/`↓` para revisarlas una por una.
Las flechas mueven el recorte solamente cuando el foco está en el editor.

La versión avanzada de escritorio se mantiene temporalmente como respaldo hasta
comparar un lote real exportado por ambas interfaces. El criterio está documentado
en `docs/PLAN_RECORTADOR_WEB.md`.

Programa independiente y local para preparar fotos de identificación por lote.

## Abrirlo

Hacé doble clic en `start_recortador_fotos.bat`, o ejecutá:

```powershell
python recortador_fotos.py
```

Si falta alguna librería, instalá las dependencias una vez con:

```powershell
python -m pip install -r requirements.txt
```

## Uso rápido

1. Elegí **Agregar fotos** o **Agregar carpeta**.
2. Seleccioná la relación de aspecto para la tarjeta (la predeterminada es 3:4).
3. Presioná **Detectar y encuadrar todas**.
4. Revisá las fotos de la lista. Arrastrá el marco blanco para mover el recorte y usá `+ Acercar` o `− Alejar` cuando sea necesario.
5. Si hace falta, usá los controles individuales de brillo, contraste, **Auto luz** y margen superior para cabello.
6. Dejá activada **Alinear ojos en todo el lote** para mantener los ojos a una altura común. El 40% desde arriba es el valor predeterminado.
7. Elegí la carpeta destino, el formato de salida y, si querés, un sufijo como `_credencial`.
   La relación de aspecto completa automáticamente un tamaño final normalizado; podés editar ancho y alto si necesitás otra resolución.
8. Presioná **Exportar todas**.

Un punto lleno junto al archivo indica que se detectó un rostro. Un círculo vacío significa que se usó un encuadre centrado y conviene revisarlo manualmente.

Las imágenes nunca salen de la computadora: la detección y la exportación se realizan localmente.

Por defecto se mantiene el nombre original de cada foto. El sufijo es opcional y se escribe exactamente como se indique; por ejemplo, `ana.jpg` con `_credencial` pasa a ser `ana_credencial.jpg`.

## Detección de rostros

La detección usa **YuNet**, un modelo de red neuronal que viene con OpenCV. Comparado con el
detector anterior tolera mejor los anteojos, las cabezas rotadas y la luz lateral, y devuelve
directamente la posición de cada ojo, así que la alineación de ojos del lote se confirma en
muchas más fotos.

El modelo es un archivo local (`models/face_detection_yunet_2023mar.onnx`, licencia MIT de
Shiqi Yu; ver `models/README.md`). Va incluido dentro del ejecutable y **no se descarga nada al
usarlo**: la aplicación sigue funcionando sin conexión y las imágenes nunca salen de la
computadora.

Si el modelo faltara o la versión de OpenCV fuera anterior a la 4.5.4, el programa vuelve solo
al detector clásico y lo avisa en la barra de estado al terminar el encuadre automático. No se
interrumpe el trabajo.

Para comparar ambos detectores sobre tus propias fotos:

```powershell
python tests\test_recortador_deteccion.py --compare C:\ruta\a\fotos
```

## Crear un ejecutable opcional

Ejecutá `build_recortador_fotos.bat`. El programa quedará en `dist\\RecortadorFotos.exe`.
