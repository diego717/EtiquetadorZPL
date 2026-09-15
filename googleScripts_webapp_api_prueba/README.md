# Prueba Web App/API para EtiquetadorZPL

Esta prueba valida si una planilla de Cuenta B puede usar funciones alojadas en
un Apps Script de Cuenta A sin ver el codigo del servidor.

La primera version solo prueba comunicacion:

- `ping`
- `echo`
- `serverInfo`

No toca Odoo todavia.

## Estructura

- `server_src/Code.gs`: pegar en un proyecto Apps Script independiente de
  Cuenta A.
- `sheet_client_src/00_webapp_api_client.gs`: pegar en el Apps Script vinculado
  a la planilla de prueba de Cuenta B.

## Parte A: servidor en Cuenta A

1. Entrar con Cuenta A a https://script.google.com.
2. Crear un proyecto nuevo.
3. Nombrarlo, por ejemplo: `EtiquetadorZPL_WebAPI`.
4. Pegar el contenido de `server_src/Code.gs`.
5. Guardar.
6. En el selector de funciones, elegir `setupApiToken`.
7. Ejecutar `setupApiToken`.
8. Autorizar permisos si Google lo pide.
9. Abrir `Registro de ejecucion` o `Executions`.
10. Copiar el token mostrado en el log.

## Parte B: desplegar como Web App

En el proyecto `EtiquetadorZPL_WebAPI`:

1. Click en `Deploy` / `Implementar`.
2. `New deployment` / `Nueva implementacion`.
3. En tipo, elegir `Web app`.
4. Description: `v1 prueba api`.
5. Execute as: `Me` / `Yo`.
6. Who has access: `Anyone` / `Cualquiera`.
7. Deploy / Implementar.
8. Copiar la URL del Web App.

Importante: para llamar desde `UrlFetchApp` de otra planilla, la opcion mas
simple es `Anyone`. La seguridad de esta prueba queda en el token.

No compartas el proyecto Apps Script del servidor con Cuenta B si queres que
Cuenta B no vea el codigo.

## Parte C: cliente en la planilla de Cuenta B

1. Abrir la planilla de prueba con Cuenta B.
2. Ir a `Extensiones > Apps Script`.
3. Crear un archivo, por ejemplo `00_webapp_api_client.gs`.
4. Pegar el contenido de `sheet_client_src/00_webapp_api_client.gs`.
5. Guardar.
6. Ejecutar `configurarEtiquetadorApi`.
7. Pegar la URL del Web App.
8. Pegar el token.
9. Ejecutar `probarEtiquetadorApiPing`.

Importante: este archivo cliente debe estar en el Apps Script abierto desde la
planilla (`Extensiones > Apps Script`). Si se pega en un proyecto independiente,
`SpreadsheetApp.getUi()` va a fallar con:

```text
Cannot call SpreadsheetApp.getUi() from this context.
```

Si no queres usar prompts, editar `configurarEtiquetadorApiManual()` con la URL
y el token reales, ejecutar esa funcion y despues ejecutar
`probarEtiquetadorApiPing`.

Si funciona, deberias ver un JSON con:

```json
{
  "ok": true,
  "action": "ping",
  "result": {
    "pong": true
  }
}
```

## Pruebas adicionales

Ejecutar:

- `probarEtiquetadorApiEcho`
- `probarEtiquetadorApiServerInfo`

`serverInfo` sirve para confirmar que el servidor corre bajo Cuenta A cuando el
Web App se desplego con `Execute as: Me`.

## Errores comunes

### La API no devolvio JSON

Probablemente el Web App no esta publicado como `Anyone`, o la URL no es la URL
de despliegue correcta.

### No autorizado

El token pegado en Cuenta B no coincide con el token generado en Cuenta A.

### API token no configurado

Falto ejecutar `setupApiToken` en el proyecto servidor de Cuenta A.

### Accion no permitida

La llamada llego bien, pero el servidor no tiene esa accion en `routeAction_`.

## Seguridad real de esta prueba

Esta prueba oculta el codigo del servidor porque Cuenta B no necesita acceso al
proyecto Apps Script de Cuenta A.

Pero si Cuenta B puede editar el Apps Script de la planilla, podria leer la URL
y el token guardados en propiedades o usarlos desde codigo local. Por eso:

- Sirve para ocultar implementacion y credenciales del servidor.
- No impide que un editor malicioso de la planilla intente llamar endpoints
  permitidos.
- Para produccion conviene validar acciones, datos permitidos y limites en el
  servidor.

## Siguiente paso si la prueba funciona

## Prueba 2: validar configuracion Odoo en Cuenta A

Esta prueba todavia no inicia sesion en Odoo. Solo confirma que las
credenciales estan guardadas en el servidor de Cuenta A y que Cuenta B puede
consultar el estado sin ver los valores completos.

### 1. Configurar Odoo en el servidor

En el proyecto `EtiquetadorZPL_WebAPI` de Cuenta A:

1. Abrir `Code.gs`.
2. Buscar `setupOdooConfigManual`.
3. Reemplazar estos valores:

```js
const config = {
  ODOO_URL: "PEGAR_URL_ODOO",
  ODOO_DB: "PEGAR_BASE_DE_DATOS",
  ODOO_USER: "PEGAR_USUARIO_ODOO",
  ODOO_API_KEY: "PEGAR_API_KEY_ODOO",
  ODOO_CIDS: "1"
};
```

Ejemplo de formato:

```js
const config = {
  ODOO_URL: "https://tuempresa.odoo.com",
  ODOO_DB: "tu_base",
  ODOO_USER: "usuario@empresa.com",
  ODOO_API_KEY: "api_key_real",
  ODOO_CIDS: "1"
};
```

4. Guardar.
5. Ejecutar `setupOdooConfigManual`.
6. Verificar en el log que diga `Configuracion Odoo guardada`.

### 2. Publicar nueva version del Web App

Despues de agregar funciones nuevas al servidor:

1. Click en `Deploy` / `Implementar`.
2. `Manage deployments` / `Gestionar implementaciones`.
3. Editar el despliegue Web App existente.
4. En `Version`, elegir `New version` / `Nueva version`.
5. Descripcion: `v2 odoo config check`.
6. Guardar / Deploy.

Usar la misma URL del Web App si Google la mantiene. Si genera una URL nueva,
volver a ejecutar `configurarEtiquetadorApi` o actualizar
`configurarEtiquetadorApiManual` en la planilla.

### 3. Probar desde la planilla

En el Apps Script vinculado a la planilla de Cuenta B:

1. Actualizar el archivo cliente con la version nueva de
   `sheet_client_src/00_webapp_api_client.gs`.
2. Guardar.
3. Ejecutar `probarOdooConfigCheck`.

Si esta bien, deberias ver algo parecido a:

```json
{
  "ok": true,
  "action": "odooConfigCheck",
  "result": {
    "configured": true,
    "missing": [],
    "preview": {
      "url": "https://tuempresa.odoo.com",
      "db": "tu***e",
      "user": "us***o@empresa.com",
      "cids": "1",
      "apiKey": "********"
    }
  }
}
```

Si `configured` es `false`, revisar `missing`.

## Migrar configuracion Odoo local hacia Cuenta A

Si la planilla actual ya tiene `ODOO_URL`, `ODOO_DB`, `ODOO_USER` y
`ODOO_API_KEY` funcionando, la forma mas segura de evitar errores de tipeo es
copiar esas propiedades desde la planilla al Web App.

### 1. Actualizar servidor

En `EtiquetadorZPL_WebAPI` de Cuenta A:

1. Pegar la version nueva de `server_src/Code.gs`.
2. Guardar.
3. Desplegar nueva version del Web App.

### 2. Actualizar cliente

En el Apps Script vinculado a la planilla:

1. Pegar la version nueva de `sheet_client_src/00_webapp_api_client.gs`.
2. Guardar.
3. Ejecutar:

```js
migrarOdooConfigLocalAApi
```

La respuesta no muestra las credenciales completas. Solo devuelve una vista
enmascarada.

Despues ejecutar:

```js
probarOdooLoginCheck
```

## Prueba 3: login real contra Odoo

Esta prueba usa las credenciales guardadas en Cuenta A, inicia sesion contra
Odoo y devuelve datos enmascarados del usuario conectado.

### 1. Actualizar servidor

En el proyecto `EtiquetadorZPL_WebAPI` de Cuenta A:

1. Pegar la version nueva de `server_src/Code.gs`.
2. Guardar.
3. Ejecutar `autorizarUrlFetchServidor`.
4. Autorizar permisos si Google lo pide.
5. Desplegar una version nueva del Web App:
   - `Deploy > Manage deployments`
   - editar el Web App
   - `Version > New version`
   - descripcion: `v3 odoo login check`
   - guardar

### 2. Actualizar cliente

En el Apps Script vinculado a la planilla de Cuenta B:

1. Pegar la version nueva de `sheet_client_src/00_webapp_api_client.gs`.
2. Guardar.
3. Ejecutar `probarOdooLoginCheck`.

Si funciona, deberias ver:

```json
{
  "ok": true,
  "action": "odooLoginCheck",
  "result": {
    "loginOk": true,
    "uidPresent": true,
    "uidMasked": "***",
    "user": {
      "name": "No***e",
      "login": "us***o@empresa.com"
    }
  }
}
```

Si aparece este error dentro de la respuesta del Web App:

```text
You do not have permission to call UrlFetchApp.fetch
```

el permiso que falta esta en el servidor de Cuenta A, no en la planilla. Abrir
el proyecto `EtiquetadorZPL_WebAPI`, ejecutar `autorizarUrlFetchServidor`,
aceptar permisos y volver a desplegar una version nueva.

## Prueba 4: lectura controlada de datos Odoo desde Cuenta A

Esta prueba valida que Cuenta A ya puede leer datos de Odoo. No devuelve datos
completos: solo conteos y una muestra enmascarada.

En la planilla de Cuenta B, ejecutar:

```js
probarOdooDataProbe
```

El resultado esperado incluye:

- `sales.ok: true`
- `manufacturing.ok: true`
- `count` de cada modelo
- `sample` con valores enmascarados

Si un modelo falla, el resultado de ese modelo trae `ok: false` y un mensaje de
error acotado.

## Siguiente paso si la prueba 4 funciona

Migrar acciones reales, una por una. Evitar un endpoint generico que permita
ejecutar cualquier metodo de Odoo desde Cuenta B.

Ejemplo de accion segura:

```js
case "salesSyncPreview":
  return getSalesSyncPreview_(payload);
```

Conviene mover al servidor:

- credenciales de Odoo;
- login a Odoo;
- consultas RPC;
- creacion de actividades/notas.

La planilla puede seguir encargandose de menus, sidebars, seleccion activa y
escritura visual.
