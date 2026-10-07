# Cobranzas, ventas sin facturar y pagina "Hoy"

Las tres funciones solo **leen** Odoo. No registran cobros, no envian mensajes y no
modifican ordenes: el boton de WhatsApp abre `wa.me` con el texto armado y quien lo
envia es el operador.

## Cobranzas (`web/cobranzas.html`, pestaña "Cobranzas")

`src/receivables_monitor.py` arma un snapshot (`receivables_snapshot.json`) con:

- Facturas y notas de credito de cliente publicadas con `payment_state` `not_paid`/`partial`.
- Agrupacion por entidad comercial (`commercial_partner_id`), con antiguedad por
  vencimiento: por vencer, 1-30, 31-60, 61-90, 91-180, mas de 180 dias.
- Importes sumados en pesos con `amount_residual_signed` (convierte USD con el tipo
  de cambio de Odoo). El detalle, el mensaje y el estado de cuenta separan por moneda.
- Ultimo cobro de cada cliente (`account.payment` entrante de los ultimos 2 años,
  incluyendo contactos hijos).
- Contacto: celular/telefono/email de la entidad comercial o del contacto facturado.
  El link de WhatsApp solo aparece con un celular uruguayo valido (09X XXX XXX).

El **estado de cuenta en PDF** (`src/account_statement_pdf.py`, PyMuPDF) lista las
facturas abiertas con saldo y dias de atraso, y totales por moneda.

El mensaje de WhatsApp se edita en la configuracion de la pagina con las variables
`{cliente}`, `{empresa}`, `{cantidad}`, `{saldo}`, `{saldo_total}` y `{vencimiento}`.

## Sin facturar (pestaña "Sin facturar")

Ordenes `sale.order` confirmadas con `invoice_status = to invoice` y `amount_to_invoice > 0`.
Las que superan `stale_uninvoiced_days` (180 por defecto) se separan como
"antiguas": casi siempre hay que facturarlas o cancelarlas en Odoo para que dejen
de figurar.

## Hoy (`web/hoy.html`)

`GET /api/today/summary` junta en una llamada:

| Tarjeta | Fuente |
| --- | --- |
| Envios impresos hoy / fallidos | historial local de impresion (`administrado_print_state.json`) |
| Envios pendientes | boton "Consultar pendientes" (usa `POST /api/administrado/sales/sync`, scraping) |
| Pagos POS listos para revisar | estado del worker de conciliacion automatica |
| Stock en quiebre / bajo minimo | snapshot del monitor de reposicion |
| Cobranzas de la semana, mayores deudores | snapshot de cobranzas |
| Sin facturar | snapshot de cobranzas |
| Entregas y recepciones atrasadas, actividades | Odoo en vivo, cache de 2 minutos (`?refresh=true` la salta) |

Cada seccion falla por separado: si Odoo no responde, el resto de las tarjetas igual se muestra.

## Endpoints

| Endpoint | Uso |
| --- | --- |
| `POST /api/receivables/refresh` | Recalcula cobranzas y sin facturar desde Odoo. |
| `GET /api/receivables/clients` | `view` (`overdue`/`balance`/`all`), `min_days`, `search`, `limit`. |
| `GET /api/receivables/clients/{id}` | Facturas abiertas del cliente. |
| `GET /api/receivables/clients/{id}/statement.pdf` | Estado de cuenta. |
| `GET /api/receivables/clients-export` | CSV con los mismos filtros. |
| `GET /api/receivables/uninvoiced` | `view` (`recent`/`stale`/`all`), `search`. |
| `GET/POST /api/receivables/config` | Refresco automatico, dias para "antigua", empresa y mensaje. |
| `GET /api/today/summary` | Resumen de la pagina Hoy. |

## Identidad visual de los PDFs

El estado de cuenta y el detalle de transaccion TotalNet usan `src/company_branding.py`:

- **Origen**: la compania de Odoo (`res.company`): logo, color primario de documentos
  (`#af343c`), direccion, telefono, email, RUT y web. La tabla usa el verde del isologo
  (`#405c58`), que Odoo no guarda.
- **Cache**: 6 horas en memoria y una copia en disco (`branding_cache.json` +
  `branding_logo.bin`). Si Odoo no responde se usa la copia guardada y, si no hay,
  un estilo neutro sin logo. Generar un PDF nunca falla por el branding.
- **Logo**: se achica a 700 px de ancho (queda nitido impreso y cada PDF pesa ~35 KB
  en vez de ~120 KB) y se incrusta una sola vez por documento.
- **Forzar otros valores** sin tocar Odoo: crear `branding_config.json` en la carpeta
  de configuracion (`%APPDATA%/EtiquetadorZPL/`), por ejemplo
  `{"accent": "#af343c", "table": "#405c58", "logo_path": "C:/logos/aramid.png"}`.
  Tambien acepta `name`, `address`, `contact`, `website` y `vat`.
