# Manual Corto para Cargar Ventas NEO

Esta guia esta pensada para vendedores, administrativos y usuarios que cargan
fechas o estados en Odoo.

El objetivo es simple: que la orden entre bien a la planilla de TRABAJOS.

## Regla general

Para que una venta se cargue correctamente en la planilla:

1. La linea que va a produccion debe tener plazo de entrega mayor a `0`.
2. Debe existir una nota en el chatter con una fecha reconocible.
3. Si corresponde, esa misma nota debe incluir el estado.

Si falta la fecha en el chatter, la orden no entra.

## Que debe hacer el usuario

### Paso 1: revisar la linea

La linea que queres que vaya a la planilla debe tener:

- producto real
- cantidad mayor a `0`
- plazo de entrega mayor a `0`

Si el plazo de entrega es `0`, esa linea no entra.

### Paso 2: dejar una nota en el chatter

La nota tiene que incluir una fecha valida.

Formatos recomendados:

- `24/06/2026`
- `24-06-2026`
- `24 jun`
- `Fecha: 24 jun`
- `Entrega: 24 junio`

### Paso 3: si hace falta, agregar el estado

Formato recomendado:

```text
Fecha: 24/06/2026
Estado: Empezar
```

Tambien sirve:

```text
Fecha: 24/06/2026
Estado: Muestra
```

## Estados que puede usar el vendedor en el chatter

- `Cotizar`
- `Muestra`
- `Empezar`

## Estados que maneja la planilla

- `Aprobar`
- `Procesando`
- `Finalizado`
- `Pausado`
- `Archivar`

## Regla de uso

Desde el chatter de ventas, el vendedor solo debe cargar:

- `Cotizar`
- `Muestra`
- `Empezar`

El resto de los estados no los debe poner en la nota del chatter porque son
estados operativos de la planilla.

## Como se reparte el control

- `Cotizar`, `Muestra` y `Empezar`: los define el vendedor desde el chatter.
- `Aprobar`: se define en la planilla cuando el trabajo queda esperando
  respuesta o validacion del cliente.
- `Procesando`, `Finalizado`, `Pausado` y `Archivar`: los maneja directamente
  quien trabaja en la planilla.

## Caso especial: vuelve desde Aprobar

Si una fila ya fue pasada a `Aprobar` en la planilla, el vendedor puede volver
desde el chatter a uno de estos 3 estados:

- `Cotizar`
- `Muestra`
- `Empezar`

Para que eso ocurra, tiene que dejar una nota nueva con fecha nueva.

## Como usar cada estado

### Cotizar

Usarlo cuando el trabajo todavia no debe entrar a produccion.

Ejemplo:

```text
Fecha: 24/06/2026
Estado: Cotizar
```

### Muestra

Usarlo cuando el trabajo esta en etapa de muestra o prueba.

Ejemplo:

```text
Fecha: 24/06/2026
Estado: Muestra
```

### Empezar

Usarlo cuando el trabajo ya esta listo para entrar al circuito productivo.

Recomendacion:

Si ya esta para empezar, conviene confirmar la cotizacion y pasarlo a orden de
venta. No dejarlo solo como presupuesto si ya va a produccion.

Ejemplo:

```text
Fecha: 24/06/2026
Estado: Empezar
```

## Estados operativos de planilla

### Aprobar

Se usa en la planilla cuando ya se envio muestra o propuesta y queda pendiente
la respuesta del cliente.

### Procesando

Se usa en la planilla cuando produccion ya esta trabajando el pedido.

### Finalizado

Se usa en la planilla cuando produccion termino el trabajo.

### Pausado

Se usa en la planilla cuando el trabajo queda detenido por algun motivo.

### Archivar

Se usa en la planilla cuando el trabajo ya no debe seguir visible en la parte
operativa.

## Caso importante: vuelve desde Aprobar

Si un trabajo estaba en `Aprobar` y el cliente pide otra muestra, otro ajuste o
una nueva cotizacion, no alcanza con cambiar solo el estado.

Hay que cargar una nota nueva con fecha nueva.

Ejemplo para nueva muestra:

```text
Fecha: 28/06/2026
Estado: Muestra
```

Ejemplo para nueva cotizacion:

```text
Fecha: 28/06/2026
Estado: Cotizar
```

Regla practica:

- si vuelve desde `Aprobar`, siempre debe llevar fecha nueva
- si vuelve desde `Aprobar`, solo puede volver a `Cotizar`, `Muestra` o
  `Empezar`
- los estados operativos posteriores se siguen manejando en la planilla

## Errores mas comunes

### La orden no aparece

Revisar:

- no tiene fecha reconocible en el chatter
- la linea tiene plazo de entrega `0`
- la linea no tiene cantidad valida
- se puso estado pero no fecha
- volvio desde `Aprobar` pero no se cargo fecha nueva

### El responsable aparece mal

Revisar:

- quien escribio la nota con fecha
- si `user_id` esta bien asignado

### Entra una linea y otra no

Normalmente pasa porque solo una de las lineas tiene plazo de entrega mayor a
`0`.

## Forma recomendada de trabajo

1. Crear o confirmar la venta.
2. Revisar que la linea correcta tenga plazo mayor a `0`.
3. Dejar una nota con fecha.
4. Si hace falta, agregar `Cotizar`, `Muestra` o `Empezar` en esa misma nota.
5. Si el trabajo vuelve desde `Aprobar`, cargar fecha nueva.
6. Si ya esta listo para producir, confirmarlo como orden de venta y usar
   `Empezar`.

## Plantilla sugerida

```text
Fecha: DD/MM/AAAA
Estado: Empezar
Observacion: texto opcional
```

## Checklist rapido

Antes de cerrar la carga:

- la linea correcta tiene plazo de entrega mayor a `0`
- la nota tiene fecha valida
- si hace falta, la nota tiene estado
- si la nota tiene estado, que sea `Cotizar`, `Muestra` o `Empezar`
- la nota la deja quien realmente confirma la fecha
- si vuelve desde `Aprobar`, se carga una fecha nueva

## Resumen

Si queres que una orden entre bien:

1. plazo de entrega mayor a `0`
2. nota con fecha
3. si hace falta, nota con estado
4. si vuelve desde `Aprobar`, fecha nueva
5. si ya va a produccion, conviene pasarla a orden de venta y usar `Empezar`
