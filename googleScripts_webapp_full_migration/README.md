# Migracion full backend a Web App/API

Esta carpeta prepara una migracion grande: mover el backend sensible a Cuenta A
y ejecutar acciones pesadas desde un Web App.

No toca los scripts originales. Usar primero una copia de la planilla.

## Que se migra

En Cuenta A:

- credenciales Odoo
- login Odoo
- RPC Odoo
- sincronizacion de fabricacion
- sincronizacion de ventas
- reparaciones operativas
- reconstruccion de enlaces
- estado/cache de sincronizacion

En Cuenta B / planilla:

- menu visual
- sidebars
- botones
- seleccion activa
- llamadas HTTP al Web App

## Importante

Cuenta A debe tener acceso de editor a la planilla de prueba, porque el Web App
abre la planilla con:

```js
SpreadsheetApp.openById(spreadsheetId)
```

Si Cuenta A no tiene acceso a la planilla, `sheetAccessCheck` va a fallar.

## Archivos

- `server_src/`: pegar todos estos `.gs` en el proyecto Web App de Cuenta A.
- `sheet_client_src/00_full_backend_client.gs`: pegar en el Apps Script de la
  planilla de prueba de Cuenta B.

## Paso 1: servidor en Cuenta A

1. Crear un proyecto Apps Script nuevo o usar uno de prueba:
   `EtiquetadorZPL_FullBackend`.
2. Pegar todos los archivos de `server_src/`.
3. Guardar.
4. Ejecutar:

```js
setupApiToken
```

5. Copiar el token del log.
6. Configurar Odoo de una de estas formas:
   - ejecutar `setupOdooConfigManual` despues de editar sus valores;
   - o migrar desde la planilla con `migrarOdooConfigLocalAFullApi`.
7. Ejecutar:

```js
autorizarUrlFetchServidor
```

8. Autorizar permisos.

## Paso 2: desplegar Web App

1. `Deploy > New deployment`.
2. Tipo: `Web app`.
3. Execute as: `Me`.
4. Who has access: `Anyone`.
5. Deploy.
6. Copiar la URL del Web App.

## Paso 3: permisos sobre la planilla

Compartir la planilla de prueba con la Cuenta A como editor.

Esto es obligatorio para que el servidor pueda abrir y escribir la planilla por
ID.

## Paso 4: cliente en la planilla

En el Apps Script vinculado a la planilla de prueba:

1. Pegar `sheet_client_src/00_full_backend_client.gs`.
2. Guardar.
3. Ejecutar:

```js
configurarEtiquetadorFullApi
```

4. Pegar URL del Web App y token.
5. Ejecutar:

```js
installNeoApiMenu
```

6. Recargar la planilla si queres ver el menu.

Opcional: para que el menu aparezca siempre, agregar esta linea al `onOpen`
actual de la planilla:

```js
installNeoApiMenu();
```

## Paso 5: pruebas en orden

Desde el menu `Neo API`, probar en este orden:

1. `Probar API`
2. `Probar acceso a planilla`
3. `Probar login Odoo`
4. `Probar lectura Odoo`
5. `Sincronizar FABRICACION`
6. `Sincronizar VENTAS NEO`
7. `Sincronizar todas`

No empezar por sincronizacion. Primero validar que Cuenta A ve la planilla y
Odoo.

## Acciones disponibles

El servidor acepta estas acciones:

- `ping`
- `serverInfo`
- `odooConfigCheck`
- `odooConfigSet`
- `odooLoginCheck`
- `odooDataProbe`
- `sheetAccessCheck`
- `syncManufacturing`
- `syncSales`
- `syncAll`
- `resetSyncState`
- `repairExistingSalesHiddenMetadata`
- `repairDeliveryDaysFormulas`
- `repairManufacturingDateValues`
- `repairSalesIngressDateValues`
- `repairSalesDeliveryDateValues`
- `repairOperationalCheckboxes`
- `rebuildLinks`

No hay endpoint generico para ejecutar cualquier metodo de Odoo.

## Si falla

### `Falta spreadsheetId`

El cliente no esta enviando el ID de la planilla. Usar
`00_full_backend_client.gs` actualizado.

### `No se pudo obtener la planilla activa`

Alguna funcion aun no esta usando `getApiSpreadsheet_`. Avisar con la accion
que fallo.

### Error de permisos sobre la planilla

Compartir la planilla con Cuenta A como editor.

### Error Odoo

Probar primero `Probar login Odoo` y `Probar lectura Odoo`.

## Corte de emergencia

Si algo sale mal, no hay que borrar nada:

1. Dejar de usar el menu `Neo API`.
2. Usar el menu original `Neo`.
3. Quitar `installNeoApiMenu();` del `onOpen` si lo agregaste.

Los scripts originales no se modifican por esta carpeta.
