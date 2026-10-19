# Recortador de fotos para credenciales

## Nueva interfaz web

Con la API local iniciada, abrí `http://localhost:8002/web/fotos.html`. La
interfaz web permite cargar fotos o PDF, detectar rostros, ajustar el recorte,
vincular una planilla CSV/Excel, tratar fondos, generar tarjetas con logo y QR,
crear una hoja PDF de revisión y descargar el resultado por lote. Los proyectos
se pueden guardar y reabrir con sus originales y ajustes.

### Mejora de imagen

En la pestaña **Editar**, la sección **Mejora de imagen** se aplica a todas las fotos al
exportar, imprimir y en la vista exacta del editor. El original nunca se modifica.

- **Mejora automática** (suave, normal o intensa): reduce ruido, corrige el balance de
  blancos usando los tonos neutros de la foto, levanta el contraste local y enfoca. No
  inventa rasgos.
- **Agrandar con IA las fotos de baja resolución**: si el recorte tiene menos píxeles de los
  que pide la caja de la foto a 300 dpi, se agranda con Real-ESRGAN (modelo local de 4,6 MB,
  sin conexión). El resultado se mezcla con un agrandado común para conservar la textura de
  la piel. Si falta más de tres veces la resolución, conviene pedir otra foto.
- **No mejorar esta foto** la deja como está.
- **Ver antes / después** muestra la comparación de la foto actual.

Debajo se indica la resolución del recorte. La revisión previa avisa de las fotos de baja
resolución. No se usan modelos de "restauración de rostros" (GFPGAN, CodeFormer) porque
inventan rasgos y pueden cambiar a la persona.

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

### Herramientas vectoriales (como en Corel)

- **Logos SVG**: cargá el logo exportado desde Corel o Illustrator en SVG (Archivo ›
  Exportar › SVG). Se dibuja a la resolución exacta de salida, así que nunca se
  pixela. Se respetan estilos, degradados y transparencias. Un logo en CDR, AI o EPS
  hay que exportarlo antes a SVG.
- **Pintar de un color**: en una imagen, pasa el logo (SVG o PNG con fondo
  transparente) a un solo color, por ejemplo blanco sobre una banda.
- **Pluma** (`P`): clic agrega un nodo en punta, arrastrar crea una curva Bézier,
  Mayús limita a 45°, clic en el primer nodo cierra la forma, y Enter o doble clic
  termina un trazado abierto.
- **Edición de nodos** (doble clic en un trazado): arrastrar nodos y manejadores,
  clic sobre la línea para agregar un nodo, Supr para borrarlo, Alt para quebrar un
  manejador. Desde el panel: nodo en punta o suave, tramo recto o curvo, y abrir o
  cerrar el trazado.
- **Formas**: triángulo, rombo, polígono y estrella (con lados, puntas y
  profundidad editables), flecha, galón, cinta, esquina cortada, cruz, banda con
  onda, escudo, corazón y globo de diálogo.
- **Relleno y contorno**: color liso, degradado lineal (con ángulo) o radial;
  contorno continuo, en rayas o en puntos, con extremos y esquinas rectos,
  redondeados o en punta.
- **Forma**: *Soldar*, *Recortar* (por ejemplo, un texto calado en una banda),
  *Intersectar*, *Excluir*, *Combinar* (las superposiciones quedan huecas),
  *Separar*, *Voltear* y **Convertir a curvas** (`Ctrl+Q`). Se pueden convertir
  textos, códigos QR y de barras, rectángulos, elipses y líneas. Un texto con
  campos queda fijo con los datos de la credencial actual.

### Exportar credenciales

Desde el editor (**Exportar…**) o desde la pestaña Tarjeta se elige:

- Alcance: credencial actual, listado filtrado, sólo revisadas o todo el lote.
- Formato: PDF, PNG o JPG; caras: frente, dorso o ambas; 300 o 600 dpi.
- PDF de una credencial por página a tamaño real, o pliegos A4/Carta/Oficio con
  márgenes, separación, marcas de corte y dorso espejado para impresión dúplex.
- Nombre de archivo con campos, por ejemplo `{Apellido}_{Nombre}`.
- **PDF vectorial** (activado por defecto): textos (en curvas, sin depender de
  las fuentes instaladas), formas, trazados, QR, códigos de barras y logos SVG van
  en vectores. Una imprenta puede ampliarlos sin perder calidad. Las fotos, las
  imágenes PNG/JPG y los degradados van como imagen a la resolución elegida.

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

### Banda magnética

En el editor, sin nada seleccionado, la sección **Banda magnética** activa la
codificación y define el dato de cada pista con campos, por ejemplo
`{Apellido}^{Nombre}` en la pista 1 o `{Legajo}` en la pista 2. Se valida con la norma
ISO 7811: la pista 1 admite hasta 76 letras mayúsculas sin acentos, números y signos
básicos; las pistas 2 y 3, sólo números y `=` (hasta 37 y 104). Los centinelas
`% ; ?` los agrega la impresora. Sobre la cara elegida se marca la zona aproximada de
la banda para no poner textos ni códigos encima.

Al imprimir, igual que CardExchange o TrustID, los datos viajan como texto con los
comandos de cada marca y el controlador los graba en la banda. Los comandos se
eligen solos según la impresora y se pueden editar:

| Marca | Comandos por defecto | Ajuste en el controlador |
| --- | --- | --- |
| Magicard | `~1`, `~2`, `~3` | Activar el procesamiento de macros |
| Entrust / Datacard (XPS) | `~1`, `~2`, `~3` | Escapes de texto para banda magnética |
| Zebra | `${1` … `}$` | Codificación magnética con macros (algunos controladores usan `~1=`) |
| Evolis | `\|1` … `\|` | Codificación por texto delimitado |
| Fargo | `~1`, `~2`, `~3` | Texto de codificación activado |
| Swiftpro | `~1`, `~2`, `~3` | A confirmar con una tarjeta de prueba |

La primera vez con cada impresora hacé **una sola tarjeta de prueba**: si el
controlador no tiene activada la codificación por texto, los datos se imprimen sobre
la tarjeta en lugar de grabarse. El registro de impresiones indica qué tarjetas se
codificaron.

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
