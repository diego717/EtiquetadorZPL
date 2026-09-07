# Busqueda local de CDR con preview y comparacion en Google Sheets

## Objetivo

Usar la API local de `EtiquetadorZPL` en la PC que tenga acceso a los `.cdr` para:

- buscar archivos `.cdr` de forma recursiva dentro de una carpeta raiz
- filtrar solo archivos cuyo nombre contenga `credito`
- devolver variantes ordenadas por relevancia
- generar preview del `.cdr` con `CorelDRAW` o con miniatura embebida como fallback
- mostrar esos datos en un modal de Google Sheets junto a una imagen guia buscada en Drive

## Como funciona la busqueda

La API ya no depende de encontrar una carpeta exacta del cliente.

Para `GET /api/client-assets/search?client_name=...` ahora:

- recorre toda `root_folder`
- toma solo `.cdr`
- exige que el nombre del archivo contenga `credito_keyword`
- soporta texto de Sheets como nombre completo o abreviatura
- usa scoring por:
  - sigla
  - nombre completo normalizado
  - tokens del nombre
  - coincidencia por carpeta como pista secundaria

## Endpoints

- `GET /api/client-assets/config`
- `POST /api/client-assets/config`
- `POST /api/client-assets/config/reload`
- `GET /api/client-assets/search?client_name=ACME`
- `GET /api/client-assets/preview/{item_id}`
- `POST /api/client-assets/open-in-corel`
- `POST /api/client-assets/prewarm-previews`

Por defecto la API corre en:

```text
http://127.0.0.1:8003
```

## Configuracion inicial

Ejemplo:

```json
{
  "enabled": true,
  "root_folder": "D:\\Clientes",
  "use_alphabetical_buckets": true,
  "search_strategy": "recursive_filename",
  "preview_cache_dir": "",
  "credito_keyword": "credito",
  "corel_enabled": true,
  "corel_visible": false,
  "corel_open_visible": true,
  "corel_bring_to_front": true,
  "embedded_thumbnail_fallback": true,
  "preview_width": 1200,
  "preview_height": 0,
  "preview_dpi": 120,
  "max_files_per_client": 100,
  "corel_macro": {
    "enabled": false,
    "project_name": "GlobalMacros.gms",
    "module_name": "ClientAssetsPrepare",
    "entrypoint": "PrepareClientAsset",
    "profile_entrypoints": {
      "tarjetas_plasticas": "PrepareTarjetasPlasticas",
      "tarjetas_laminar_tinta_a": "PrepareTarjetasLaminarTintaA",
      "tarjetas_laminar_tinta_b": "PrepareTarjetasLaminarTintaB"
    },
    "fallback_to_python_prepare": true,
    "debug_enabled": true
  },
  "corel_prepare_profiles": {
    "tarjetas_plasticas": {
      "label": "Tarjetas plasticas",
      "printer_name": "",
      "paper_name": "",
      "orientation": "",
      "print_profile_name": "",
      "notes": ""
    },
    "tarjetas_laminar_tinta_a": {
      "label": "Tarjetas para laminar / tinta - Impresora A",
      "printer_name": "",
      "paper_name": "A4",
      "orientation": "portrait",
      "print_profile_name": "",
      "notes": "Misma preparacion de laminadas; cambia solo la impresora."
    },
    "tarjetas_laminar_tinta_b": {
      "label": "Tarjetas para laminar / tinta - Impresora B",
      "printer_name": "",
      "paper_name": "A4",
      "orientation": "portrait",
      "print_profile_name": "",
      "notes": "Completar con el nombre real de la impresora B."
    }
  }
}
```

Campos nuevos importantes:

- `search_strategy`: hoy usar `recursive_filename`
- `embedded_thumbnail_fallback`: si falla `CorelDRAW`, intenta sacar miniatura embebida del `.cdr`
- `corel_open_visible`: para apertura interactiva en Corel, dejar la app visible
- `corel_bring_to_front`: intenta traer la ventana de Corel al frente al abrir el archivo
- `corel_macro`: habilita ejecucion de una macro propia de CorelDRAW antes del fallback por COM
- `corel_macro.debug_enabled`: agrega al error el detalle de los intentos COM usados para invocar la macro
- `corel_prepare_profiles`: perfiles de trabajo usados por `open_and_prepare`
- para laminadas, conviene tener dos perfiles separados `A/B` con la misma preparacion y distinto nombre de impresora
- `preview_width` y `preview_dpi`: bajarlos ayuda a que la preview cargue mas rapido

## Respuesta de busqueda

Cada item devuelto incluye:

- `name`
- `relative_path`
- `absolute_path`
- `contains_credito`
- `match_reason`
- `modified_at`
- `preview_url`

La respuesta general incluye:

- `client_name`
- `folder_path`
- `matched_directories`
- `match_count`
- `search_mode`
- `warnings`
- `items`

## Notas sobre preview

Orden de resolucion:

1. exportacion local via `CorelDRAW` por automatizacion COM
2. si falla y `embedded_thumbnail_fallback=true`, intenta extraer miniatura del `.cdr`

Requisitos para el mejor resultado:

- `CorelDRAW` instalado en esa misma PC
- `pywin32` instalado
- `Pillow` instalado para fallback de miniatura

## Apertura interactiva en Corel

Nuevo endpoint:

```text
POST /api/client-assets/open-in-corel
```

Payload base:

```json
{
  "item_id": "abc123",
  "mode": "open_only"
}
```

Payload para preparacion:

```json
{
  "item_id": "abc123",
  "mode": "open_and_prepare",
  "profile_id": "tarjetas_plasticas"
}
```

Comportamiento actual:

- abre el `.cdr` seleccionado en `CorelDRAW`
- deja Corel visible si `corel_open_visible=true`
- intenta traer la ventana al frente si `corel_bring_to_front=true`
- soporta `open_and_prepare` con perfiles configurados en `corel_prepare_profiles`
- si `corel_macro.enabled=true`, intenta primero ejecutar una macro de CorelDRAW
- intenta aplicar impresora, papel, orientacion y perfil de impresion como `best effort`
- no imprime, no guarda y no cierra Corel automaticamente

Si Corel se abre pero no se puede poner al frente o no soporta algun ajuste del perfil, la API responde exito con `warnings`.

## Macro opcional de CorelDRAW para `open_and_prepare`

Si quieres encapsular la logica real de preparacion dentro de Corel 24, la API local ya puede intentar una macro primero y usar el fallback por COM solo si falla.

Configuracion:

```json
{
  "corel_macro": {
    "enabled": true,
    "project_name": "GlobalMacros.gms",
    "module_name": "ClientAssetsPrepare",
    "entrypoint": "PrepareClientAsset",
    "profile_entrypoints": {
      "tarjetas_plasticas": "PrepareTarjetasPlasticas",
      "tarjetas_laminar_tinta_a": "PrepareTarjetasLaminarTintaA",
      "tarjetas_laminar_tinta_b": "PrepareTarjetasLaminarTintaB"
    },
    "fallback_to_python_prepare": true,
    "debug_enabled": true
  }
}
```

Notas:

- `project_name`: opcional; dejar vacio si la macro vive en el proyecto por defecto de GMS
- si lo conoces, en Corel 24 conviene probar primero `GlobalMacros.gms`
- aun con `project_name` vacio, la API prueba automaticamente `GlobalMacros.gms` y `GlobalMacros`
- `module_name`: nombre del modulo VBA/GMS dentro de Corel
- `entrypoint`: procedimiento base que recibe `profile_id`
- `profile_entrypoints`: opcional pero recomendado; permite usar macros sin parametros por perfil
- `fallback_to_python_prepare`: si la macro falla, la API vuelve al intento actual via COM
- `debug_enabled`: hace que el error incluya los metodos y argumentos COM que Python intento usar

Referencia:

- ejemplo de modulo: [COREL_CLIENT_ASSETS_PREPARE.bas](/abs/path/C:/Users/Usuario/Desktop/EtiquetadorZPL/docs/COREL_CLIENT_ASSETS_PREPARE.bas)
- guia resumida: [COREL_OPEN_PREP_PLAN.md](/abs/path/C:/Users/Usuario/Desktop/EtiquetadorZPL/docs/COREL_OPEN_PREP_PLAN.md)

Pasos practicos sugeridos en Corel 24:

1. abrir el editor de macros/VBA de CorelDRAW
2. importar el modulo `COREL_CLIENT_ASSETS_PREPARE.bas`
3. si quieres validar solo la invocacion, poner `SHOW_TEST_MESSAGE = True`
4. probar manualmente `PrepareTarjetasPlasticas`, `PrepareTarjetasLaminarTintaA` o `PrepareTarjetasLaminarTintaB` con un documento abierto
5. si esos wrappers funcionan, la API puede llamarlos sin pasar parametros
6. completar dentro del modulo los nombres reales de impresora, papel o propiedades que tu instalacion soporte
7. cuando la macro funcione sola dentro de Corel, activar `corel_macro.enabled=true` en la API local

## Recomendacion de validacion

1. ejecutar `configure_client_assets_api.bat`
2. revisar `root_folder`
3. iniciar `start_client_assets_api.bat`
4. abrir en navegador:

```text
http://127.0.0.1:8003/api/client-assets/search?client_name=IAC
```

5. probar una preview:

```text
http://127.0.0.1:8003/docs#/client-assets
```

Cuando eso funcione, recien ahi conectar el modal de Google Sheets.

## Integracion con Sheets

La UI recomendada esta en:

```text
docs/GOOGLE_SHEETS_IMPRESION_LOCAL_MODAL.md
```

Ese modal:

- toma el cliente desde la columna `F`
- usa ese mismo valor para buscar `.cdr` en la API local
- usa ese mismo valor para buscar imagenes guia en Drive
- si ya existe un `onEdit(e)` en Apps Script, reutiliza ese flujo y no agrega otro
- permite acotar la busqueda de Drive configurando `DRIVE_GUIDE_FOLDER_ID` en `Code.gs`
- si hay varias imagenes en Drive, las lista para elegir
- muestra `JPG guia` y `preview CDR` lado a lado
- permite disparar `Abrir en Corel` para el `.cdr` seleccionado
- precalienta en segundo plano las primeras previews devueltas por la API para acelerar los clicks
- deja elegir la variante correcta sin salir de Google Sheets

## Configuracion de la carpeta de Drive

La carpeta de Drive donde estan los JPG guia no se configura en la API local.

Se configura en el archivo `Code.gs` de Apps Script, en esta linea:

```javascript
const DRIVE_GUIDE_FOLDER_ID = '';
```

Hay que reemplazar el valor vacio por el `ID` de la carpeta de Drive.

Ejemplo:

```javascript
const DRIVE_GUIDE_FOLDER_ID = '1AbCdEfGhIjKlMnOpQrStUvWxYz';
```

Si se deja vacio, la busqueda de imagenes se hace en Drive sin limitar a una carpeta puntual.

## Build portable

Para generar un paquete facil de mover a otra PC:

1. ejecutar `build_client_assets_api.bat`
2. buscar la salida en:

```text
release\ClientAssetsAPI_Package
release\ClientAssetsAPI_Package.zip
```

Ese paquete incluye:

- `EtiquetadorZPL_ClientAssets_API.exe`
- `configure_client_assets_api.bat`
- `start_client_assets_api.bat`
- configuracion ejemplo
- documentacion de uso
