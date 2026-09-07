# Estado actual Corel: `open_only` + `open_and_prepare`

## Resumen

La integracion local con `CorelDRAW` ya tiene dos modos soportados desde `POST /api/client-assets/open-in-corel`:

- `open_only`
- `open_and_prepare`

La impresion automatica todavia no forma parte de esta fase.

## Lo que ya esta implementado

- apertura del `.cdr` seleccionado desde `client-assets`
- visibilidad interactiva de `CorelDRAW`
- intento `best effort` de traer Corel al frente
- boton `Abrir en Corel` en el modal documentado
- boton `Abrir y preparar` en el modal documentado
- perfiles de preparacion configurables por PC en `corel_prepare_profiles`
- soporte `macro-first` opcional via `corel_macro`, con fallback al ajuste actual por COM

## Modos soportados

### `open_only`

Payload:

```json
{
  "item_id": "abc123",
  "mode": "open_only"
}
```

Comportamiento:

- abre el archivo en `CorelDRAW`
- no aplica perfil de trabajo
- deja el documento abierto para revision manual

### `open_and_prepare`

Payload:

```json
{
  "item_id": "abc123",
  "mode": "open_and_prepare",
  "profile_id": "tarjetas_plasticas"
}
```

Comportamiento:

- abre el archivo en `CorelDRAW`
- intenta aplicar el perfil elegido
- si `corel_macro.enabled=true`, intenta ejecutar una macro propia de CorelDRAW pasando `profile_id`
- si la macro falla y `fallback_to_python_prepare=true`, vuelve al ajuste normal via COM
- deja el documento abierto para revision e impresion manual
- si algun ajuste no se puede aplicar por COM, responde exito con `warnings`

## Perfiles de preparacion

La configuracion vive en la API local, no en Google Sheets.

Estructura:

```json
{
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

`corel_macro` sirve para mover a VBA/GMS la parte mas sensible a version, driver o flujo operativo real de Corel 24.

Para reducir prueba y error, la API intenta varias formas de invocacion COM y, si `project_name` viene vacio, prueba automaticamente `GlobalMacros.gms` y `GlobalMacros`.
Tambien puede usar `profile_entrypoints` para llamar macros sin parametros por perfil, que suele ser la opcion mas estable en Corel 24.
Para laminadas, el modelo recomendado es `A/B`: misma presentacion y distinto destino de impresion.

Cada perfil puede intentar aplicar:

- `printer_name`
- `paper_name`
- `orientation`
- `print_profile_name`

`notes` queda solo como referencia operativa.

## Flujo esperado

1. El usuario abre el modal en Google Sheets.
2. Busca el cliente y selecciona el `.cdr`.
3. Si solo quiere revisar el archivo, usa `Abrir en Corel`.
4. Si quiere dejarlo preconfigurado, elige un perfil y usa `Abrir y preparar`.
5. La API abre el documento, intenta macro si esta habilitada y luego fallback por COM si hace falta.
6. Devuelve `warnings` si algun ajuste no pudo fijarse por completo.
7. El operador revisa e imprime manualmente desde Corel.

## Punto de arranque recomendado para Corel 24

Si vamos por el caso `Python -> abre CDR -> llama macro`, el siguiente paso practico ya no es tocar el modal sino definir y probar la macro dentro de Corel con uno de los dos perfiles.

Referencia sugerida:

- [COREL_CLIENT_ASSETS_PREPARE.bas](/abs/path/C:/Users/Usuario/Desktop/EtiquetadorZPL/docs/COREL_CLIENT_ASSETS_PREPARE.bas)

Ese modulo sirve como base para:

- recibir `profile_id`
- separar la logica de `tarjetas_plasticas`, `tarjetas_laminar_tinta_a` y `tarjetas_laminar_tinta_b`
- hacer pruebas manuales dentro de Corel 24 antes de endurecer la automatizacion
- habilitar una prueba visible con `SHOW_TEST_MESSAGE = True`

## Lo que no entra todavia

- impresion automatica
- disparar `Print` desde el modal
- cerrar Corel automaticamente
- guardar cambios sobre el archivo original

## Siguiente fase natural

Si esta etapa resulta estable en `CorelDRAW 24`, el siguiente paso recomendable es una fase de `impresion guiada`, por ejemplo:

- validar que el perfil correcto quedo aplicado
- mostrar resumen de preparacion en el modal
- ofrecer un disparo controlado de impresion con confirmacion explicita

No se recomienda saltar directo a impresion automatica sin validar antes que los perfiles se aplican de forma consistente en la PC real.
