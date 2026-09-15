# Endpoints de productos Odoo

Estos endpoints reutilizan la configuracion de Odoo guardada por la API local
en `/api/odoo/config`.

## Listado JSON

```http
GET /api/odoo/products
```

Parametros:

| Parametro | Default | Uso |
| --- | --- | --- |
| `search` | vacio | Busca por nombre, display name, referencia interna o codigo de barras. |
| `limit` | `200` | Cantidad maxima de productos. Rango: 1 a 1000. |
| `offset` | `0` | Desplazamiento para paginar. |
| `active_only` | `true` | Si es `true`, omite productos archivados. |
| `inventory_only` | `true` | Si es `true`, omite servicios usando `detailed_type` o `type`. |
| `include_stock` | `true` | Si es `true`, incluye cantidades calculadas por Odoo cuando existen. |

Ejemplo:

```http
GET /api/odoo/products?search=ETI&limit=100&include_stock=true
```

Respuesta:

```json
{
  "items": [
    {
      "id": 55,
      "default_code": "ETI-001",
      "barcode": "779000000001",
      "name": "[ETI-001] Etiqueta Premium",
      "list_price": 120.5,
      "qty_available": 9,
      "uom": "Units",
      "category": "Etiquetas",
      "active": true,
      "type": "product"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0,
  "has_more": false
}
```

## Exportacion CSV

```http
GET /api/odoo/products/export
```

Usa los mismos filtros que el listado JSON y devuelve `productos_odoo.csv`
con columnas pensadas para etiquetas: referencia interna, codigo de barras,
nombre, precio, stock, unidad y categoria.

En la exportacion, `limit` funciona como maximo total de filas a exportar:
por defecto `5000`, con tope `20000`. Internamente la API pagina Odoo en
bloques de hasta `1000` productos.
