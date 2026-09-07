# Resumen Rapido de Ventas NEO

## Para que una orden entre a la planilla

Tiene que cumplir estas 3 condiciones:

1. La linea que va a produccion debe tener plazo de entrega mayor a `0`.
2. Debe existir una nota en el chatter con una fecha valida.
3. Si corresponde, esa misma nota debe incluir el estado.

## Formato recomendado de nota

```text
Fecha: DD/MM/AAAA
Estado: Empezar
```

Ejemplos validos:

- `Fecha: 24/06/2026`
- `Entrega: 24 junio`
- `24 jun`

## Estados a usar

- `Cotizar`: lo define el vendedor en el chatter
- `Muestra`: lo define el vendedor en el chatter
- `Empezar`: lo define el vendedor en el chatter
- `Aprobar`: lo define la planilla
- `Procesando`: lo define la planilla
- `Finalizado`: lo define la planilla
- `Pausado`: lo define la planilla
- `Archivar`: lo define la planilla

## Regla clave

Desde el chatter de ventas, el vendedor solo debe usar:

- `Cotizar`
- `Muestra`
- `Empezar`

El resto de los estados se manejan directamente en la planilla.

## Regla importante

Si un trabajo estaba en `Aprobar` y vuelve para otra muestra o nueva
cotizacion, hay que cargar una nota nueva con fecha nueva.

Ejemplo:

```text
Fecha: 28/06/2026
Estado: Muestra
```

```text
Fecha: 28/06/2026
Estado: Cotizar
```

Tambien puede volver a:

```text
Fecha: 28/06/2026
Estado: Empezar
```

## Recomendacion comercial

Si el trabajo ya esta para arrancar, conviene confirmar la cotizacion y pasarlo
a orden de venta. Ahi el estado recomendado es:

```text
Fecha: 24/06/2026
Estado: Empezar
```

## Checklist rapido

Antes de cerrar la carga:

- la linea correcta tiene plazo mayor a `0`
- la nota tiene fecha
- si hace falta, la nota tiene estado
- si la nota tiene estado, que sea `Cotizar`, `Muestra` o `Empezar`
- si vuelve desde `Aprobar`, tiene fecha nueva
- si ya va a produccion, conviene pasarlo a orden de venta
