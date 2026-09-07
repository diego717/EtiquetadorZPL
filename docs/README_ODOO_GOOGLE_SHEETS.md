# Conexión Google Sheets con Odoo

Manual técnico y operativo de la integración entre la planilla de producción y Odoo.

> Estado documentado: 23 de junio de 2026. 
## Objetivo

La integración mantiene la pestaña `TRABAJOS` sincronizada con:

- Órdenes de fabricación de Odoo (`mrp.production`).
- Órdenes de venta con fecha de producción (`sale.order`).
- Notas y mensajes del chatter (`mail.message`).
- Enlaces directos desde la planilla hacia cada registro de Odoo.

La planilla funciona como tablero operativo. Odoo continúa siendo la fuente principal de las órdenes.

## Estructura del proyecto

El código de Apps Script se divide en los siguientes archivos:

| Archivo | Responsabilidad |
| --- | --- |
| `00_Config.gs` | Configuración general, columnas, estados, modelos y responsables permitidos. |
| `01_Menu.gs` | Menú Odoo, diagnósticos y acciones manuales. |
| `02_OdooConexion.gs` | Autenticación y llamadas JSON-RPC a Odoo. |
| `03_Enlaces.gs` | Búsqueda de órdenes y creación de hipervínculos. |
| `04_Fabricacion.gs` | Sincronización de órdenes de fabricación. |
| `05_Chatter.gs` | Lectura e interpretación de notas del chatter. |
| `06_VentasNEO.gs` | Sincronización de órdenes de venta. Conserva el nombre histórico por compatibilidad. |
| `07_Utilidades.gs` | Fechas, cantidades, filas libres, propiedades e identificadores. |
| `08_AutomatizacionesHoja.gs` | Edición automática, ordenamiento y envío al histórico. |

Todos los archivos pertenecen al mismo proyecto de Apps Script y pueden llamar funciones ubicadas en otros archivos.

## Configuración de Odoo

Las credenciales no deben escribirse directamente en el código. Deben cargarse en **Configuración del proyecto → Propiedades del script**.

| Propiedad | Contenido |
| --- | --- |
| `ODOO_URL` | Dirección base de Odoo, sin `/jsonrpc` al final. |
| `ODOO_DB` | Nombre de la base de datos. |
| `ODOO_USER` | Usuario utilizado por la integración. |
| `ODOO_API_KEY` | Clave API del usuario. |
| `ODOO_CIDS` | Identificador de compañía; por defecto `1`. |

La conexión utiliza JSON-RPC mediante estas funciones:

- `getOdooCfg_()` obtiene las propiedades.
- `odooLogin_()` inicia sesión y obtiene el `uid`.
- `executeKw_()` ejecuta métodos sobre modelos de Odoo.
- `rpc_()` realiza la petición HTTP y controla errores.

## Instalación inicial en una planilla nueva

Cuando se copia este proyecto a otra planilla, conviene hacer una puesta en
marcha inicial para que enlaces, fórmulas, sincronizaciones e IDs internos
queden alineados desde el principio.

### Requisitos previos

1. La pestaña operativa debe llamarse `TRABAJOS`.
2. Deben existir al menos estas columnas:
   - `A`: responsable
   - `B`: orden
   - `C`: enlace a Odoo
   - `H`: entrega
   - `I`: estado
   - `K`: fila nueva
   - `L`: días para entrega
   - `R`: ID interno de fabricación
3. Deben cargarse las propiedades del script:
   - `ODOO_URL`
   - `ODOO_DB`
   - `ODOO_USER`
   - `ODOO_API_KEY`
   - `ODOO_CIDS`

### Orden recomendado de primera ejecución

1. Ejecutar `onOpen()`.
   Esto crea el menú `Odoo` en la planilla.

2. Ejecutar `backfillManufacturingIds()`.
   Esto completa la columna `R` para órdenes de fabricación ya visibles.
   Es importante para que luego el sistema pueda detectar y limpiar
   fabricaciones eliminadas en Odoo.

3. Ejecutar `repairExistingSalesHiddenMetadata()` si la planilla ya tenía filas de ventas
   antes de instalar las columnas `S`, `T`, `U` y `V`.
   Esto intenta completar:
   - `S`: `sale.order.id`
   - `T`: `sale.order.line.id`
   - `U`: origen (`VENTA`)
   - `V`: timestamp ancla cuando una fila de venta pasa manualmente a `Aprobar`

4. Ejecutar `repairDeliveryDaysFormulas()` solo si la columna `L` no tiene
   correctamente la fórmula de días restantes.

5. Ejecutar `syncOdooManufacturingOrders()`.

6. Ejecutar `syncOdooSalesOrdersNeo()`.

### Triggers recomendados

- Crear un trigger instalable `Al editarse` para `crearEnlaceAlEditar`.
- Crear un trigger instalable `Al editarse` para `notificarVentaNeoFinalizadaAlEditar` si se quiere publicar una nota interna en Odoo cuando una fila de venta pase a `Finalizado`.
- Ejecutar `installOdooSalesAutoSyncTrigger()` si se desea sincronización
  automática de ventas.

### Verificación rápida

Después de la instalación inicial debería cumplirse lo siguiente:

- El menú `Odoo` aparece al abrir la planilla.
- La columna `R` contiene IDs de fabricación.
- La columna `K` usa checkbox y no texto `TRUE`.
- La columna `L` calcula correctamente los días de entrega.
- La columna `C` abre el registro correcto en Odoo.

### Chequeo de instalación

La función `checkOdooSheetSetup()` revisa la preparación de la planilla y del
proyecto sin modificar datos. Sirve para validar de una sola vez:

- la pestaña `TRABAJOS`
- las propiedades de Odoo
- la presencia de `R`, `S`, `T`, `U` y `V`
- el checkbox de nuevas filas
- la fórmula de la columna `L`
- los triggers instalados de edición y sync automática

Conviene ejecutarla después de clonar el proyecto a una nueva planilla o
después de una refactorización importante.

## Registro de sincronización

La hoja `LOG_SYNC` se crea automáticamente cuando las sincronizaciones escriben
su primer evento.

Guarda una traza simple con:

- fecha y hora
- módulo (`FABRICACION` o `VENTAS`)
- acción (`sync_start`, `insert`, `update`, `delete`, `skip`, `sync_end`)
- orden o referencia
- ID de Odoo
- origen de la fila
- detalle breve del evento

Sirve para diagnosticar qué ocurrió en una sincronización sin depender de los
logs de ejecución de Apps Script.

Internamente, los eventos se acumulan en memoria y se escriben en bloque al
final de cada sincronización, para reducir llamadas repetidas a la hoja.

Si querés abrirla o limpiarla desde el menú `Odoo`, agregá estas acciones al
`onOpen()` del proyecto:

```javascript
.addItem("Abrir LOG_SYNC", "openSyncLogSheet")
.addItem("Limpiar LOG_SYNC", "clearSyncLogSheet")
.addItem("Chequeo de instalación", "checkOdooSheetSetup")
.addItem("Backfill fabricación", "backfillManufacturingIds")
.addItem("Backfill ventas", "repairExistingSalesHiddenMetadata")
```

## Pestaña y columnas

La pestaña sincronizada se llama `TRABAJOS` y los datos comienzan en la fila 4.

| Columna | Uso principal |
| --- | --- |
| A | Responsable reconocido. |
| B | Número o nombre de orden. |
| C | Enlace directo al registro de Odoo. |
| D | Nombre del trabajo cargado en la planilla. |
| E | Producto y referencia. |
| F | Cantidad. |
| G | Fecha de ingreso o inicio. |
| H | Fecha de entrega detectada en el chatter. |
| I | Estado operativo. |
| J | Fecha de finalización. |
| K | Casilla que identifica una fila nueva. |
| O | Prioridad auxiliar utilizada para ordenar. |
| R | ID interno de la orden de fabricación en Odoo. Puede mantenerse oculta. |
| S | ID interno de `sale.order`. Puede mantenerse oculta. |
| T | ID interno de `sale.order.line`. Puede mantenerse oculta. |
| U | Origen de la fila: `FABRICACION` o `VENTA`. Puede mantenerse oculta. |
| V | Timestamp ancla de `Aprobar` para ventas. Puede mantenerse oculta. |

El código conserva formatos y validaciones de datos siempre que limpia contenidos con `clearContent()` en lugar de eliminar físicamente filas.

## Órdenes de fabricación

La función principal es:

```javascript
syncOdooManufacturingOrders()
```

### Comportamiento

1. Consulta órdenes modificadas recientemente en `mrp.production`.
2. Procesa estados productivos configurados y también `cancel`.
3. Omite órdenes parciales cuyo nombre termina en `-número`.
4. Normaliza el número de orden para compararlo con la columna B.
5. Actualiza una fila existente o utiliza la primera fila disponible.
6. Obtiene producto, cantidad, responsable, fecha y estado.
7. Marca la columna K cuando se crea una fila nueva.
8. Ordena la tabla después de completar toda la sincronización.

### Órdenes canceladas

Cuando una fabricación pasa a `cancel`, la sincronización debe limpiar su fila para impedir que continúe apareciendo como trabajo pendiente.

La búsqueda debe utilizar `write_date`, no solamente `create_date`. De esta manera puede detectar la cancelación de una orden creada hace varios meses.

### Órdenes eliminadas de Odoo

La columna R conserva el ID de `mrp.production`. En cada sincronización se
consultan en lote los IDs visibles. Si un ID deja de existir, el script realiza
una segunda consulta inmediata y limpia la fila si vuelve a estar ausente. De
esta forma alcanza con una sola sincronización sin perder la doble comprobación.

Después de instalar esta función debe ejecutarse una sola vez:

```javascript
backfillManufacturingIds()
```

Esto completa la columna R para las órdenes que ya estaban en la planilla. El
ordenamiento realinea R por número de orden porque la tabla de prioridades ocupa
P:Q y no forma parte del rango ordenado A:O.

### Coincidencia con ventas

Ventas y fabricaciones pueden compartir el mismo número. El mapa de fabricación debe considerar los números ya presentes en la columna B, aunque la fila se haya originado desde una venta.

No debe limitarse exclusivamente a filas cuyo enlace contenga `mrp.production`, porque eso puede crear duplicados visuales entre una venta y su fabricación relacionada.

## Órdenes de venta

La función principal es:

```javascript
syncOdooSalesOrdersNeo()
```

La ejecución interna protegida por bloqueo es:

```javascript
syncOdooSalesOrdersNeoUnlocked_()
```

### Comportamiento

1. Consulta órdenes modificadas en `sale.order`.
2. También detecta órdenes cuyos mensajes del chatter cambiaron.
3. Detecta cambios recientes en `sale.order.line`, incluso cuando el `sale.order` padre no modificó su `write_date`.
4. Obtiene las líneas desde `sale.order.line`.
5. Conserva únicamente las líneas reales de producto cuyo `plazo de entrega` por línea sea mayor a `0`.
6. Omite secciones, notas, líneas sin producto y líneas con `customer_lead = 0`.
7. Crea una fila por cada producto encontrado.
8. Marca cada fila nueva en la columna K.
9. Actualiza filas existentes sin volver a insertarlas.
10. Ordena la tabla al terminar la sincronización.

### Criterio de producción por línea

La integración ya no depende del prefijo `NEO` para decidir si una línea debe
aparecer en la planilla.

La regla pasa a ser:

- Si la línea de `sale.order.line` tiene `plazo de entrega` mayor a `0`, se incorpora.
- Si la línea tiene `plazo de entrega = 0`, no se incorpora.

Esto permite usar el propio dato de la línea como marca operativa de “va a producción”
sin modificar el estado general de la orden.

### Requisito de fecha

La orden de venta se incorpora cuando existe una fecha reconocible en sus notas del chatter.

Si la nota contiene solamente una fecha, la orden igualmente puede incorporarse y utiliza el estado predeterminado:

```text
Empezar
```

Los formatos admitidos incluyen ejemplos como:

- `24/06/2026`
- `24-06-2026`
- `24 jun`
- `Fecha: 24 jun`
- `Entrega: 24 junio`

### Responsable

La sincronización debe consultar los campos:

```javascript
"user_id"
"create_uid"
```

Se utiliza primero `user_id` y, si está vacío, `create_uid`.

`findResponsible_()` transforma nombres como `Marcelo Rodriguez` en `Marcelo`, siempre que el nombre esté incluido en `VALID_RESPONSIBLES`. El valor resultante se escribe en la columna A y debe coincidir exactamente con una opción del menú desplegable.

### Filtro opcional por creador

Para reducir la cantidad de ordenes leidas desde Odoo, ventas puede limitar la
sincronizacion a determinados creadores de `sale.order`.

Se admiten estas propiedades del script:

- `ODOO_SALES_ALLOWED_CREATE_UIDS`
- `ODOO_SALES_ALLOWED_CREATE_UID_NAMES`

Uso recomendado:

- `ODOO_SALES_ALLOWED_CREATE_UIDS`: lista separada por comas con IDs internos de `res.users`. Ejemplo: `14,27`
- `ODOO_SALES_ALLOWED_CREATE_UID_NAMES`: lista separada por comas con nombres o fragmentos de nombre. Ejemplo: `Marcelo, Valentina`

Si alguna de estas propiedades existe, la consulta principal de ventas agrega un
filtro por `create_uid` antes de traer las ordenes. Si no se configura nada, el
comportamiento sigue siendo el mismo de siempre.

### Ventas canceladas

Las órdenes canceladas no deben excluirse de la consulta principal por `write_date`, porque el script necesita recibirlas para poder eliminarlas de la planilla.

Cuando `order.state` es `cancel`:

1. Se localizan todas las filas de esa venta.
2. Se limpian sus contenidos y notas.
3. Se desmarca la casilla de fila nueva.
4. Se eliminan sus identificadores de las propiedades internas.
5. Se vuelve a ordenar la tabla.

Las consultas auxiliares de órdenes recientes sí pueden continuar excluyendo canceladas para evitar importar órdenes históricas que nunca estuvieron visibles.

## Lectura del chatter

El módulo `05_Chatter.gs` consulta `mail.message` para fabricación y ventas.

El contenido HTML se convierte a texto mediante:

- `normalizeMessageBody_()`
- `decodeHtmlEntities_()`
- `normalizeNoteLine_()`

Después se buscan fechas y estados con:

- `extractLatestManufacturingNote_()`
- `parseManufacturingNote_()`
- `extractLatestSalesNote_()`
- `parseSalesPlanningNote_()`

## Estados de la planilla

Los estados principales se convierten de la siguiente manera:

| Estado Odoo | Estado en la planilla |
| --- | --- |
| `confirmed` | `Empezar` |
| `draft` | `Empezar` |
| `progress` | `Procesando` |
| `to_close` | `Procesando` |
| `done` | `Finalizado` |
| `cancel` | La fila se elimina de la vista operativa. |

También se reconocen estados directos como `Pausado`, `Cotizar`, `Muestra`, `Aprobar` y `Archivar`.

## Ordenamiento

La función responsable es:

```javascript
ejecutarOrdenadoAutomatico()
```

La prioridad se obtiene de la tabla `P4:Q12` y se escribe temporalmente en la columna O. Después se ordena por:

1. Prioridad de la columna O, descendente.
2. Producto de la columna E, ascendente.
3. Nombre del trabajo de la columna D, ascendente.

Los cambios realizados mediante Apps Script no disparan `onEdit`. Por ese motivo, fabricación y ventas deben llamar explícitamente a `ejecutarOrdenadoAutomatico()` después de insertar, actualizar o quitar filas.

## Hipervínculos

La columna C contiene un texto enriquecido con enlace hacia Odoo.

La búsqueda intenta primero coincidencias exactas y luego coincidencias flexibles sobre:

- `mrp.production`
- `sale.order`

Si no encuentra una coincidencia exacta, genera un enlace hacia la búsqueda de Odoo.

## Menú Odoo

`onOpen()` crea el menú **Odoo** al abrir la planilla.

Incluye acciones para:

- Reconstruir hipervínculos.
- Diagnosticar la fila seleccionada.
- Diagnosticar una orden de venta.
- Importar una venta puntual.
- Sincronizar fabricación.
- Sincronizar ventas.
- Activar o desactivar la sincronización automática.

El proyecto debe abrirse desde **Extensiones → Apps Script** dentro de la planilla. `onOpen()` no debe ejecutarse manualmente desde un proyecto independiente.

## Activadores

### Edición

El `onEdit(e)` simple debe ejecutar únicamente automatizaciones locales:

```javascript
function onEdit(e) {
  automatizacionEditar(e);
}
```

`crearEnlaceAlEditar()` utiliza la conexión con Odoo y debe tener un activador
instalable independiente de tipo **Al editarse**. No debe llamarse desde el
`onEdit` simple porque los activadores simples no pueden utilizar servicios que
requieren autorización, como `UrlFetchApp`.

### Sincronización automática de ventas

`installOdooSalesAutoSyncTrigger()` crea un activador cada cinco minutos para:

```javascript
syncOdooSalesOrdersNeo()
```

`removeOdooSalesAutoSyncTrigger()` elimina ese activador.

## Propiedades internas

El script mantiene información de sincronización mediante propiedades:

| Propiedad | Uso |
| --- | --- |
| `ODOO_LAST_SYNC_UTC` | Última sincronización de fabricación. |
| `ODOO_IMPORTED_IDS` | IDs de fabricación procesados. |
| `ODOO_SALES_LAST_SYNC_UTC` | Última sincronización de ventas. |
| `ODOO_SALES_LINE_LAST_SYNC_UTC` | Última revisión de cambios en líneas de ventas. |
| `ODOO_SALES_IMPORTED_IDS` | IDs de ventas procesadas. |
| `ODOO_SALES_SKIPPED_NO_NOTE_IDS` | Ventas omitidas por no tener una fecha válida. |

`resetSyncState()` elimina estas propiedades. Debe utilizarse con precaución porque obliga al script a revisar nuevamente órdenes recientes.

## Operación recomendada

1. Confirmar que las propiedades de Odoo estén configuradas.
2. Abrir nuevamente la planilla para cargar el menú.
3. Ejecutar una sincronización manual de fabricación.
4. Ejecutar una sincronización manual de ventas.
5. Verificar órdenes, responsables, productos, fechas y estados.
6. Confirmar que las filas nuevas estén marcadas en la columna K.
7. Confirmar que la tabla quede ordenada.
8. Activar la sincronización automática de ventas cuando las pruebas sean correctas.

## Pruebas recomendadas

- Crear una fabricación confirmada y comprobar su incorporación.
- Cancelar esa fabricación y comprobar que su fila se limpie.
- Crear una venta con un único producto.
- Crear una venta con varios productos y comprobar una fila por producto.
- Agregar una nota que contenga solamente una fecha.
- Verificar que una venta sin fecha no se importe.
- Confirmar que `user_id` seleccione el responsable correcto en la columna A.
- Cancelar una venta y comprobar que desaparezcan todas sus líneas.
- Confirmar que una venta y una fabricación relacionadas no generen filas duplicadas.
- Comprobar que la casilla K se marque únicamente para filas nuevas.
- Confirmar que el ordenamiento se ejecute después de cada sincronización.

## Estado actual y verificaciones pendientes

La refactorización contempla todas las funciones descritas. No obstante, como los cambios se copiaron manualmente en Apps Script, deben verificarse específicamente estos puntos en el proyecto activo:

- Que ventas llame a `ejecutarOrdenadoAutomatico()` al finalizar.
- Que las consultas de ventas incluyan `user_id` y `create_uid`.
- Que `writeSalesOrderLineRow_()` escriba `matchedResponsible` en la columna A.
- Que la consulta principal de ventas permita recibir órdenes canceladas.
- Que la rama `state === "cancel"` limpie todas las filas de la venta.
- Que el mapa de fabricación no se haya limitado únicamente a enlaces `mrp.production`.
- Que no existan dos funciones globales llamadas `onEdit`.

## Seguridad

- No compartir la clave API en el código, capturas o documentación.
- Utilizar un usuario de Odoo con los permisos mínimos necesarios.
- Mantener las credenciales únicamente en Propiedades del script.
- Revisar los registros de ejecución cuando una sincronización falle.
