# Manual de usuario — Recortador de fotos Profesional

## 1. Para qué sirve

Esta edición permite preparar fotografías para credenciales, revisar un lote, vincular fotos con planillas Excel y exportar archivos finales de manera controlada. Todo el procesamiento ocurre localmente en la computadora.

## 2. Flujo de trabajo recomendado

1. En la barra superior, elegí **Agregar fotos**, **Agregar carpeta** o seleccioná un PDF.
2. Elegí un formato de encuadre y pulsá **Detectar y encuadrar todas**.
3. Revisá las fotos con advertencias. Podés arrastrar el recuadro, acercar, rotar o ajustar luz individualmente.
4. En **Profesional**, ejecutá **Analizar lote y actualizar excepciones**.
5. Usá **Ver sólo excepciones** para concentrarte en las fotos que necesitan atención.
6. Configurá la carpeta, formato, dimensiones y nombre de salida en **Salida**.
7. Pulsá **Validar antes de exportar** y resolvé las observaciones importantes.
8. Exportá una foto o todo el lote. Se generará también un registro CSV de la exportación.

## 3. Pestaña Editar

- **Alejar / Acercar**: cambia el tamaño del recorte sin alterar la imagen original.
- **Rotar**: rota solamente la foto de trabajo. Usá después la detección automática si querés recalcular el rostro.
- **Detectar y encuadrar esta foto**: busca el rostro y aplica el encuadre según la relación de aspecto seleccionada.
- **Brillo, contraste y Auto luz**: se aplican a la foto seleccionada.
- **Margen para cabello**: agrega aire por encima de la cabeza.
- **Alinear ojos**: intenta mantener los ojos a una altura constante dentro del recorte.
- **Deshacer**: recupera acciones registradas de la foto actual. La lista muestra `✎` cuando una foto fue ajustada manualmente.
- **Rehacer**: está disponible en la pestaña **Profesional** y recupera la última acción deshecha de la foto actual.

## 4. Pestaña Salida

Aquí se define el resultado final:

- Carpeta de destino.
- Formato: JPG, PNG, WEBP, TIFF o BMP.
- Nombre de archivo con `{nombre}`, `{sufijo}` y `{fecha}`.
- Tamaño final en píxeles, completado automáticamente según la relación y editable si necesitás otra resolución.
- Preset reutilizable para relación, ojos, cabello, formato, dimensiones y plantilla de nombre.

Si dos archivos terminarían con el mismo nombre, la aplicación conserva ambos agregando un número al segundo archivo.

## 5. Pestaña Avanzado

### Fondo natural

Permite suavizar o aclarar el fondo mediante una máscara de bordes difuminados. La vista previa se actualiza en pantalla y el archivo original nunca se modifica. Es una ayuda visual; revisá especialmente cabellos sueltos, manos y prendas con fondos parecidos.

### Control de calidad

Detecta posibles problemas de foco, luz, contraste, rostro pequeño, ojos no detectados y duplicados. Es una advertencia, no una decisión automática: una foto marcada debe revisarse antes de descartarse.

### Tarjeta y datos

Podés importar un CSV con columnas `archivo`, `nombre` y `cargo`. Al elegir **Tarjeta simple**, los datos se integran durante la exportación.

## 6. Pestaña Excel

1. Cargá primero las fotos.
2. Elegí **Seleccionar planilla Excel**.
3. Seleccioná la columna de nombre y, si corresponde, la de apellido.
4. Usá **Comparar y crear reporte CSV** para ver faltantes y fotos sin registro.
5. Usá **Crear Excel con rutas de fotos** para generar una copia de la planilla con las columnas de ruta, archivo y estado.

Las coincidencias ignoran tildes, mayúsculas, espacios, guiones y el orden nombre/apellido. También admite un nombre adicional en el archivo, por ejemplo `Bell Enriquez` puede vincularse con `Bell Mary Enriquez.jpeg`. Cuando hay más de una coincidencia posible, queda marcada para revisión y no se asigna una ruta de forma arbitraria.

## 7. Pestaña Profesional

### Buscar y revisar

- **Filtrar** busca parte del nombre de archivo dentro de las fotos cargadas.
- **Ver sólo excepciones** muestra fotos con problemas de encuadre, detección o control de calidad.
- **Limpiar filtros** vuelve a mostrar todo el lote.

### Validación y hoja de revisión

- **Validar antes de exportar** revisa fotos pendientes, carpeta de destino, plantilla de nombre, color de tarjeta y posibles nombres duplicados.
- **Generar hoja PDF de revisión** crea una hoja de contacto con las fotos y su estado. Sirve para solicitar una aprobación antes de imprimir.

### Automatización y tarjeta institucional

- **Auto luz sólo en fotos oscuras** corrige únicamente imágenes con brillo bajo; no modifica las que ya tienen una exposición normal.
- **Título para tarjeta**, **Color institucional** y **Elegir logo opcional** personalizan la tarjeta simple. El color debe escribirse como hexadecimal, por ejemplo `#0C5E91`. El logo se conserva en su ubicación original y se incorpora sólo al exportar la tarjeta.

### Registro de lote

Cada exportación genera un archivo `registro_lote_FECHA_HORA.csv` dentro de la carpeta de salida. Incluye fecha, archivo origen, archivo exportado y estado. Es útil para controlar entregas y repetir un trabajo.

## 8. Privacidad

La aplicación procesa las imágenes en la PC. La opción **Limpiar datos locales de esta sesión** borra de memoria los datos CSV/Excel, rutas recordadas y caché de la sesión. No elimina fotografías, PDFs, Excel, CSV ni archivos exportados.

Para evitar conservar carpetas utilizadas entre sesiones, usá esta opción al terminar un lote sensible.

## 9. Recomendaciones

- Conservá siempre las fotos originales en otra carpeta.
- Analizá el lote antes de exportar y revisá las excepciones.
- Para credenciales, definí primero el tamaño final y hacé una impresión de prueba.
- Usá el PDF de revisión cuando el lote requiera aprobación de otra persona.
- Si una coincidencia de Excel es ambigua, corregí el nombre del archivo o de la planilla en lugar de elegir una ruta manualmente.
