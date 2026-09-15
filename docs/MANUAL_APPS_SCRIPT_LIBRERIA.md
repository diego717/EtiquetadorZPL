# Manual para probar Google Apps Script como libreria

Este manual explica como probar una libreria de Google Apps Script para el
proyecto de la planilla, usando como base la carpeta `googleScripts`.

La idea es dejar la mayor parte del codigo en un proyecto Apps Script separado
y protegido. En la planilla queda un codigo minimo, con funciones puente
(`wrappers`) que llaman a la libreria.

## Objetivo

- Que la logica principal no quede editable dentro del Apps Script vinculado a
  la planilla.
- Que la planilla pueda seguir usando menus, triggers y automatizaciones.
- Que se pueda probar primero sin romper la planilla actual.

## Limitaciones importantes

- Una libreria evita que otros modifiquen el codigo si no tienen permiso de
  editor sobre el proyecto de la libreria.
- No es una forma perfecta de ocultar secretos. Google recomienda compartir la
  libreria con al menos permiso de lectura para los usuarios que la usen.
- Los menus y triggers de la planilla necesitan funciones locales. Por eso se
  deja un archivo puente en la planilla.
- Las librerias pueden agregar algo de demora, sobre todo en sidebars o flujos
  con muchas llamadas cortas a `google.script.run`.

Fuentes oficiales:

- https://developers.google.com/apps-script/guides/libraries
- https://developers.google.com/apps-script/concepts/deployments
- https://developers.google.com/apps-script/guides/triggers
- https://developers.google.com/apps-script/guides/support/best-practices

## Estrategia recomendada

No conviene mover todo de una sola vez.

Orden recomendado:

1. Crear una libreria nueva con una funcion simple de prueba.
2. Conectar esa libreria desde una copia de la planilla.
3. Probar un wrapper local.
4. Mover los archivos de `googleScripts` a la libreria.
5. Dejar en la planilla solo wrappers para menus y triggers.
6. Crear una version estable de la libreria.
7. Actualizar la planilla para usar esa version.

## Paso 1: hacer una copia de seguridad

Antes de tocar la planilla real:

1. Abrir la planilla de Google Sheets.
2. Ir a `Archivo > Hacer una copia`.
3. Nombrarla, por ejemplo: `EtiquetadorZPL - prueba libreria`.
4. Trabajar siempre primero sobre esa copia.

Tambien conviene guardar una copia del Apps Script actual:

1. En la planilla, ir a `Extensiones > Apps Script`.
2. Copiar todo el codigo actual a un archivo de respaldo o conservarlo en este
   repo dentro de `googleScripts`.

## Paso 2: crear el proyecto de libreria

1. Entrar a https://script.google.com.
2. Crear un proyecto nuevo.
3. Nombrarlo, por ejemplo: `EtiquetadorZPL_Library`.
4. Crear un archivo `Code.gs`.
5. Pegar esta funcion de prueba:

```js
function ping() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const name = spreadsheet ? spreadsheet.getName() : "sin planilla activa";
  return "Libreria conectada correctamente: " + name;
}
```

6. Guardar el proyecto.

## Paso 3: crear una version de la libreria

En el proyecto `EtiquetadorZPL_Library`:

1. Ir a `Implementar > Nueva implementacion`.
2. En el engranaje de tipo de implementacion, elegir `Biblioteca` si aparece.
3. Completar una descripcion, por ejemplo: `v1 prueba ping`.
4. Implementar.

Si la interfaz muestra primero `Versiones`:

1. Ir a `Archivo > Gestionar versiones` o `Implementar > Gestionar implementaciones`,
   segun la interfaz disponible.
2. Crear una version nueva.
3. Usar esa version como version de la libreria.

Luego obtener el ID del script:

1. Ir a `Configuracion del proyecto`.
2. Copiar el `ID de secuencia de comandos`.

Ese ID es el que se agrega desde la planilla.

## Paso 4: agregar la libreria a la planilla de prueba

En la copia de la planilla:

1. Ir a `Extensiones > Apps Script`.
2. En el panel izquierdo, entrar a `Bibliotecas`.
3. Pegar el ID del script de la libreria.
4. Elegir una version, por ejemplo `1`.
5. Definir el identificador. Recomendado:

```text
EtiquetadorZPL
```

6. Guardar.

El identificador es el nombre con el que la planilla va a llamar a la libreria:

```js
EtiquetadorZPL.ping()
```

## Paso 5: probar un wrapper local

En el Apps Script vinculado a la planilla de prueba, crear un archivo llamado
`00_bridge.gs` o similar.

Pegar:

```js
function probarLibreria() {
  const msg = EtiquetadorZPL.ping();
  SpreadsheetApp.getUi().alert(msg);
}
```

Despues:

1. Guardar.
2. Ejecutar `probarLibreria` desde el editor.
3. Aceptar permisos si Google los solicita.
4. Confirmar que aparece una alerta con el nombre de la planilla.

Si esto funciona, la libreria ya esta conectada.

## Paso 6: probar el menu desde la libreria

En la libreria, agregar esta funcion:

```js
function onOpen(e) {
  SpreadsheetApp.getUi()
    .createMenu("Neo Lib")
    .addItem("Probar libreria", "probarLibreria")
    .addToUi();
}
```

Crear una nueva version de la libreria:

1. Guardar cambios.
2. Crear version nueva, por ejemplo `v2 prueba menu`.
3. En la planilla, ir a `Bibliotecas`.
4. Cambiar la version de la libreria a la nueva version.
5. Guardar.

En la planilla, dejar este wrapper local:

```js
function onOpen(e) {
  EtiquetadorZPL.onOpen(e);
}
```

Cerrar y volver a abrir la planilla. Deberia aparecer el menu `Neo Lib`.

Nota: el item del menu llama a `probarLibreria`, que debe existir localmente en
la planilla. Esto es normal: los items de menu necesitan nombres de funciones
del proyecto vinculado a la planilla.

## Paso 7: migrar el codigo real a la libreria

Cuando la prueba simple funcione, mover a la libreria el contenido de estos
archivos:

- `googleScripts/00_config.txt`
- `googleScripts/01_menu.txt`
- `googleScripts/02_OdooConexion.txt`
- `googleScripts/03_Enlaces.txt`
- `googleScripts/04_Fabricacion.txt`
- `googleScripts/05_Chatter.txt`
- `googleScripts/06_VentasNeo.txt`
- `googleScripts/07_utilidades.txt`
- `googleScripts/08_automatizaciones.txt`
- `googleScripts/09_EtiquetaOrden.txt`
- `googleScripts/09_EtiquetaProducto.txt`
- `googleScripts/09_EtiquetasManuales.txt`
- `googleScripts/09_EtiquetasPrecargadas.txt`
- `googleScripts/09_EtiquetaTarjeta.txt`
- `googleScripts/10_HojaTrabajo.txt`
- `googleScripts/11_ImprimirTarjeta.txt`
- `googleScripts/11_PestañaImpresion.txt`
- `googleScripts/12_NeoCalculo.txt`
- `googleScripts/13_Planillas.txt`

Recomendacion practica:

- Crear en la libreria archivos `.gs` con los mismos nombres, por ejemplo
  `00_config.gs`, `01_menu.gs`, etc.
- Copiar el contenido de cada `.txt` dentro del `.gs` correspondiente.
- Mantener todos esos archivos juntos dentro del proyecto de libreria.

## Paso 8: dejar solo wrappers en la planilla

En la planilla de prueba, borrar el codigo completo anterior solo despues de
confirmar que ya esta copiado en la libreria.

Dejar un archivo puente parecido a este:

```js
function onOpen(e) {
  return EtiquetadorZPL.onOpen(e);
}

function onEdit(e) {
  return EtiquetadorZPL.onEdit(e);
}

function syncOdooManufacturingOrders() {
  return EtiquetadorZPL.syncOdooManufacturingOrders();
}

function syncOdooSalesOrdersNeo() {
  return EtiquetadorZPL.syncOdooSalesOrdersNeo();
}

function syncAllOrders() {
  return EtiquetadorZPL.syncAllOrders();
}

function generarEtiquetasSeleccionadasPDF() {
  return EtiquetadorZPL.generarEtiquetasSeleccionadasPDF();
}

function solicitarImagenYGenerarPDF() {
  return EtiquetadorZPL.solicitarImagenYGenerarPDF();
}

function generarEtiquetasTrabajosPDF() {
  return EtiquetadorZPL.generarEtiquetasTrabajosPDF();
}

function generarEtiquetasProductosPDF() {
  return EtiquetadorZPL.generarEtiquetasProductosPDF();
}

function showImageSidebar() {
  return EtiquetadorZPL.showImageSidebar();
}

function EtiquetaParaProductos() {
  return EtiquetadorZPL.EtiquetaParaProductos();
}

function abrirVisorPDFs() {
  return EtiquetadorZPL.abrirVisorPDFs();
}

function abrirVisorPlanillas() {
  return EtiquetadorZPL.abrirVisorPlanillas();
}

function showSidebar() {
  return EtiquetadorZPL.showSidebar();
}

function crearEnlaceAlEditar(e) {
  return EtiquetadorZPL.crearEnlaceAlEditar(e);
}

function notificarVentaNeoFinalizadaAlEditar(e) {
  return EtiquetadorZPL.notificarVentaNeoFinalizadaAlEditar(e);
}

function automatizacionEditar(e) {
  return EtiquetadorZPL.automatizacionEditar(e);
}

function installOdooSalesAutoSyncTrigger() {
  return EtiquetadorZPL.installOdooSalesAutoSyncTrigger();
}

function removeOdooSalesAutoSyncTrigger() {
  return EtiquetadorZPL.removeOdooSalesAutoSyncTrigger();
}

function installOdooManufacturingAutoSyncTrigger() {
  return EtiquetadorZPL.installOdooManufacturingAutoSyncTrigger();
}

function removeOdooManufacturingAutoSyncTrigger() {
  return EtiquetadorZPL.removeOdooManufacturingAutoSyncTrigger();
}

function installOdooLinkEditTrigger() {
  return EtiquetadorZPL.installOdooLinkEditTrigger();
}

function removeOdooLinkEditTrigger() {
  return EtiquetadorZPL.removeOdooLinkEditTrigger();
}

function installSalesFinalizationNotificationTrigger() {
  return EtiquetadorZPL.installSalesFinalizationNotificationTrigger();
}

function removeSalesFinalizationNotificationTrigger() {
  return EtiquetadorZPL.removeSalesFinalizationNotificationTrigger();
}

function installSalesHiddenMetadataRepairTrigger() {
  return EtiquetadorZPL.installSalesHiddenMetadataRepairTrigger();
}

function removeSalesHiddenMetadataRepairTrigger() {
  return EtiquetadorZPL.removeSalesHiddenMetadataRepairTrigger();
}

function installOdooOperationalTriggers() {
  return EtiquetadorZPL.installOdooOperationalTriggers();
}
```

Puede haber mas funciones publicas usadas manualmente desde el editor. Si una
funcion se ejecuta desde menu, boton, trigger o manualmente desde Apps Script,
conviene crearle wrapper local.

## Paso 9: probar flujos principales

En la planilla de prueba:

1. Abrir la planilla y confirmar que aparece el menu `Neo`.
2. Ejecutar `Sincronizar FABRICACION`.
3. Ejecutar `Sincronizar VENTAS NEO`.
4. Probar una etiqueta simple.
5. Editar una fila de `TRABAJOS` para validar `onEdit`.
6. Revisar `Ejecuciones` en Apps Script para ver errores.
7. Revisar que los triggers instalables existan en `Desencadenadores`.

Si aparece un error del tipo:

```text
TypeError: EtiquetadorZPL.nombreFuncion is not a function
```

Significa que esa funcion no esta publica en la libreria, no existe con ese
nombre o la planilla esta usando una version vieja de la libreria.

Solucion:

1. Revisar que la funcion exista en la libreria.
2. Crear una nueva version de la libreria.
3. Actualizar la version usada por la planilla.
4. Guardar y probar de nuevo.

## Paso 10: publicar cambios futuros

Cada vez que se modifique la libreria:

1. Guardar cambios en el proyecto de libreria.
2. Crear una version nueva.
3. En la planilla, abrir `Bibliotecas`.
4. Cambiar la version usada.
5. Guardar.
6. Probar.

Evitar usar la version `HEAD` o `Desarrollo` en la planilla real. Para la
planilla real conviene usar siempre una version numerada estable.

## Paso 11: permisos recomendados

Proyecto de libreria:

- Propietario/editor: solo quien mantiene el codigo.
- Lectores: usuarios o cuentas que necesiten ejecutar la libreria.

Planilla:

- Editores normales pueden seguir usando la planilla.
- Si entran a `Extensiones > Apps Script`, podran ver/modificar los wrappers
  locales, pero no modificar la libreria si no tienen permiso de editor.

Si hay claves sensibles de Odoo, no conviene dejarlas hardcodeadas en la
libreria ni en la planilla. Mejor usar:

- `PropertiesService`
- una hoja de configuracion protegida
- o un backend propio que guarde las credenciales fuera de Apps Script

## Rollback rapido

Si algo falla:

1. En la planilla, abrir `Extensiones > Apps Script`.
2. Quitar o comentar los wrappers.
3. Restaurar el codigo completo anterior desde `googleScripts`.
4. Guardar.
5. Recargar la planilla.

Otra opcion:

1. Mantener una copia de la planilla original sin libreria.
2. Si la prueba falla, volver a esa copia y seguir usando el sistema anterior.

## Checklist antes de pasar a produccion

- La copia de prueba abre el menu correctamente.
- `syncOdooManufacturingOrders` funciona.
- `syncOdooSalesOrdersNeo` funciona.
- `syncAllOrders` funciona.
- `onEdit` no rompe ediciones normales.
- Los triggers instalables fueron recreados.
- Las etiquetas PDF siguen generando.
- Los sidebars abren correctamente.
- La version de la libreria es numerada, no `HEAD`.
- La planilla real tiene backup.
- El proyecto de libreria no da permiso de editor a usuarios que no deban
  modificar el codigo.

## Recomendacion final

Para este proyecto, lo mas seguro es hacer la primera prueba solo con `ping`,
despues mover `01_menu` y una funcion simple, y finalmente mover todos los
archivos de `googleScripts`.

Cuando todo funcione, la planilla real deberia quedar con un archivo puente
pequeno y la logica completa viviendo en `EtiquetadorZPL_Library`.
