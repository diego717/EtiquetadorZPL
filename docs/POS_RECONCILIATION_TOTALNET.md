# Conciliación de pagos POS (TotalNet) — guía de implementación

**Este documento está pensado para implementarse en una computadora distinta a la que lo diseñó**, sin depender de haber visto la conversación original. Es un diseño, no código terminado: antes de programar cada paso hay puntos marcados como "confirmar" que hay que validar contra la documentación real de TotalNet.

## Contexto

EtiquetadorZPL (FastAPI + Python, corre local en cada PC) ya integra con Odoo por XML-RPC (`src/odoo_integration.py`) para imprimir órdenes de venta al despachar pedidos de Mercado Libre. Esto agrega una conciliación automática de los cobros hechos con tarjeta en el local (terminal TotalNet):

1. Trae las transacciones de tarjeta vía la **API oficial de TotalNet** (no hace falta descargar PDFs a mano ni scrapear el portal web).
2. Las cruza contra las facturas pendientes de cobro en Odoo.
3. Registra el pago en Odoo (`account.payment.register`, el mismo mecanismo que el botón "Registrar pago" de la interfaz de Odoo).

**Regla de oro del diseño: nunca se escribe en Odoo sin que un operador confirme**, salvo que haya una coincidencia 100% inequívoca. El objetivo es eliminar la carga manual repetitiva, no sacar al humano de la decisión final.

## Prerrequisitos

1. **Credenciales de TotalNet**: `client_id` + `client_secret` de la API "Totalnet API Comercios v2". **No pegarlas en ningún archivo del repo ni comitearlas.** Este mismo repo ya tuvo un incidente real de una API key de Odoo commiteada en texto plano en `CHANGELOG.md` — no repetirlo. Las credenciales van en un archivo de config local fuera del control de versiones (ver Paso 1).
2. **Documentación de la API**: `https://conecta.totalnet.uy/api-comercios-doc` (la página carga el contenido con JavaScript, hay que abrirla en un navegador normal). El spec OpenAPI crudo está en `https://conecta.totalnet.uy/adx-conecta/v2/openapi.json`. Antes de escribir código, confirmar ahí:
   - La **URL exacta del endpoint de token OAuth2** (no se confirmó durante el diseño — buscar la sección de seguridad/`securitySchemes` del spec, o preguntarle a soporte de TotalNet).
   - El **schema de request de `/cupones`** (`CuponesRequest` en la lista de Schemas de la doc) — para los nombres exactos de los parámetros de fecha/comercio/paginado. El código de ejemplo de este documento asume nombres de campo razonables (`fecha_desde`, `fecha_hasta`) pero **hay que confirmarlos contra el schema real antes de asumir que están bien**.
3. **Acceso al repo de EtiquetadorZPL** con su entorno Python configurado. El proyecto ya usa `httpx` como dependencia (se usa hoy en `src/odoo_integration.py` para la sesión web de Odoo), así que no hace falta instalar nada nuevo para el cliente HTTP.
4. Un **usuario/base de Odoo de prueba** (o al menos una factura de prueba en el Odoo real) contra la cual probar el registro de pago sin afectar datos productivos.

## Qué devuelve la API de TotalNet (confirmado contra la documentación real)

- **`POST /cupones`** y **`/cupones/{coupon_id}`** — lista/detalle de cada transacción individual ("cupón"). Campos relevantes del schema `CuponesResponse` (confirmados):
  - `transaccion.ticket` — el mismo número que imprime la terminal en el comprobante físico que se le da al cliente.
  - `transaccion.autorizacion` — código de aprobación bancario.
  - `transaccion.lote`, `transaccion.numero_factura`, `transaccion.terminal` — identificadores de la transacción del lado de TotalNet.
  - `transaccion.importe`, `transaccion.fecha_cupon`, `transaccion.moneda` — para matchear por monto/fecha contra Odoo.
  - `transaccion.sello` (Visa, MasterCard, Amex, Oca, Cabal, etc.) y `transaccion.producto` (ej. "Visa Débito") — para mapear automáticamente a qué diario contable de Odoo va cada pago.
  - `liquidacion.banco_acreditacion`, `liquidacion.fecha_pago`, `liquidacion.forma_de_pago`, `liquidacion.arancel`, `liquidacion.iva_arancel` — a qué banco y cuándo se acredita el dinero, y el costo del servicio ya descontado por transacción.
  - Paginado vía `query_name` + `page_number`.
- **`POST /liquidaciones`** y **`/liquidaciones/{liquidacion_id}`** — vista agregada por liquidación (probablemente con el desglose completo de ajustes tipo retenciones DGI / gastos administrativos, que no aparecen a nivel de cupón individual). No es imprescindible para el flujo principal de conciliar pagos contra facturas; solo haría falta si se quiere cuadrar el neto exacto depositado en el banco. Su schema exacto no se confirmó todavía.
- **`POST /info`** — fechas con liquidaciones disponibles.
- **Autenticación**: OAuth2 *client credentials*.

Esto reemplaza lo que hubiera sido necesario hacer con el PDF de liquidación que emite TotalNet (parsear una tabla con celdas mezcladas, páginas irrelevantes que descartar) o con scraping del portal web para conseguir el Ticket — todo eso ya viene junto y estructurado en `/cupones`.

## Arquitectura en un vistazo

```
[TotalNet API]  --POST /cupones-->  [src/totalnet_integration.py]
                                            |
                                            v
                          [src/pos_reconciliation.py]  <-- facturas pendientes --  [src/odoo_integration.py] (Odoo XML-RPC)
                                            |
                                            v
                       Propuesta de conciliación (único / ambiguo / sin match)
                                            |
                                            v
                      [web/config.html, pestaña nueva]  <-- operador revisa y confirma
                                            |
                                            v
                  [api/pos_reconciliation_endpoints.py] POST /confirm
                                            |
                                            v
          [src/odoo_integration.py] register_invoice_payment()  -->  Odoo (account.payment.register)
```

## Pasos de implementación

Cada paso es probable de forma aislada antes de seguir al siguiente — no conviene construir todo de una vez.

### Paso 1 — Config local + cliente OAuth2 de TotalNet

Archivo nuevo: `src/totalnet_integration.py`. Sigue el mismo patrón que `src/odoo_integration.py`: una clase con config persistida en JSON bajo `%APPDATA%/EtiquetadorZPL/`, un método de autenticación, y un singleton al final del módulo.

```python
"""
Integracion TotalNet (API REST, OAuth2 client_credentials) para conciliacion de pagos POS.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# TODO: confirmar contra el spec OpenAPI real (securitySchemes) o con soporte TotalNet.
TOTALNET_TOKEN_URL = "https://conecta.totalnet.uy/<CONFIRMAR>/oauth/token"
TOTALNET_API_BASE = "https://conecta.totalnet.uy/adx-conecta/v2"


class TotalNetIntegration:
    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @staticmethod
    def _resolve_config_path() -> Path:
        from config_manager import config_manager
        return Path(config_manager.get_config_directory()) / "totalnet_config.json"

    def _default_config(self) -> Dict[str, Any]:
        return {"enabled": False, "client_id": "", "client_secret": ""}

    def _load_config(self) -> Dict[str, Any]:
        config = self._default_config()
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as handle:
                config.update(json.load(handle))
        return config

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, ensure_ascii=True)
        return self.get_public_config()

    def get_public_config(self) -> Dict[str, Any]:
        safe = dict(self.config)
        if safe.get("client_secret"):
            safe["client_secret"] = "***"
        return safe

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        response = httpx.post(
            TOTALNET_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def get_cupones(self, date_from: str, date_to: str, page_number: int = 1) -> Dict[str, Any]:
        token = self._get_token()
        # OJO: confirmar nombres de campo reales contra el schema CuponesRequest.
        payload = {"fecha_desde": date_from, "fecha_hasta": date_to, "page_number": page_number}
        response = httpx.post(
            f"{TOTALNET_API_BASE}/cupones",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


totalnet_integration = TotalNetIntegration()
```

**Cómo probarlo antes de seguir**: un script suelto o una sesión interactiva que haga `totalnet_integration.save_config({"client_id": "...", "client_secret": "..."})` y después `totalnet_integration.get_cupones("2026-08-01", "2026-08-14")`, y revisar que devuelva JSON real (no un error 401/404). Si el token endpoint o los nombres de campo están mal, va a fallar acá — resolverlo antes de tocar el resto.

### Paso 2 — Endpoint de prueba en la API

Archivo nuevo: `api/totalnet_endpoints.py`, mismo estilo que `api/odoo_endpoints.py` (Pydantic models, `asyncio.to_thread`, manejo de errores):

```python
from __future__ import annotations
import asyncio
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from totalnet_integration import totalnet_integration

router = APIRouter(prefix="/api/totalnet", tags=["totalnet"])


class TotalNetConfigRequest(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return totalnet_integration.get_public_config()


@router.post("/config")
async def save_config(config: TotalNetConfigRequest) -> Dict[str, Any]:
    payload = config.dict()
    if not payload.get("client_secret"):
        payload.pop("client_secret", None)
    return totalnet_integration.save_config(payload)


@router.get("/cupones/test")
async def test_cupones(date_from: str, date_to: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(totalnet_integration.get_cupones, date_from, date_to)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

Montarlo en `api/fastapi_real.py` junto a los demás routers (buscar donde están `odoo_router`, `administrado_router`, etc. — típicamente cada uno se importa con un `try/except` para que sea opcional si el módulo no está disponible).

**Cómo probarlo**: levantar la API local y pegarle a `GET /api/totalnet/cupones/test?date_from=2026-08-01&date_to=2026-08-14` desde el navegador o Postman/`curl`, con las credenciales ya guardadas vía `POST /api/totalnet/config`. Confirmar que devuelve cupones reales con los campos esperados (`transaccion.ticket`, `transaccion.autorizacion`, `transaccion.importe`, etc.).

### Paso 3 — Búsqueda de facturas pendientes en Odoo

En `src/odoo_integration.py`, extender el método existente `find_invoiced_sales` (línea ~377, ya busca sobre `account.move`) con un parámetro opcional, por ejemplo `only_pending: bool`, que agregue el filtro `invoice_payment_state in ('not_paid', 'partial')` — así trae solo lo que todavía espera cobro, sin duplicar la lógica de búsqueda que ya existe.

### Paso 4 — Motor de matching

Archivo nuevo: `src/pos_reconciliation.py`. Recibe la lista de cupones de TotalNet (Paso 1) y las facturas a contado de Odoo (Paso 3), y devuelve tres listas: `matches_unicos`, `ambiguos`, `sin_match`. Las facturas pagadas también se muestran para explicar la conciliación, pero no se pueden volver a pagar.

Lógica, en dos niveles:

1. **Número de factura (principal)**: cruzar `transaccion.numero_factura` de TotalNet contra el número final del comprobante Odoo. Si TotalNet informó un número y ese comprobante no existe en Odoo, queda en **sin match**; no se reemplaza por otra factura que casualmente tenga el mismo importe y una fecha cercana.
2. **Importe/moneda/fecha (fallback)**: se usa únicamente cuando TotalNet no informó número de factura. Si hay una sola candidata queda como coincidencia; si hay varias queda como **ambiguo**.

Las agrupaciones N-a-1 por suma de cupones están deshabilitadas: una suma coincidente no demuestra que los cupones pertenezcan a esa factura. Si no hay una coincidencia individual confiable queda en **sin match**.

Una coincidencia con diferencia entre el importe TotalNet y el total de Odoo se muestra con ambos valores y la diferencia, pero no puede confirmarse. El backend vuelve a validar importe y estado justo antes de crear el pago.

### Paso 5 — Registrar el pago en Odoo

En `src/odoo_integration.py`, nuevo método que reutiliza el mismo patrón de autenticación XML-RPC que ya usa `confirm_sale_order` (línea ~569):

```python
def register_invoice_payment(
    self,
    invoice_id: int,
    amount: float,
    payment_date: str,
    journal_id: int,
    memo: str,
    auth_override: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    runtime = self._build_runtime_config(auth_override)
    uid = self._authenticate(auth_override=auth_override)
    models = self._xmlrpc_models(runtime)
    db = runtime.get("database", "")
    password = runtime.get("password", "")

    wizard_id = models.execute_kw(
        db, uid, password,
        "account.payment.register", "create",
        [{"amount": amount, "payment_date": payment_date, "journal_id": journal_id, "communication": memo}],
        {"context": {"active_model": "account.move", "active_ids": [int(invoice_id)]}},
    )
    return models.execute_kw(
        db, uid, password,
        "account.payment.register", "action_create_payments",
        [[wizard_id]],
    )
```

Esto usa el wizard estándar de Odoo `account.payment.register` — el mismo mecanismo que la ventana "Registrar pago" de la interfaz de Odoo, confirmado con una captura de pantalla real durante el diseño (diario `Master BROU Aramid $`, campo Memo, etc.).

- El **`memo`** guarda el resumen estructurado disponible en TotalNet: factura, ticket, autorización, lote, sello/producto, últimos cuatro dígitos, terminal, importe, beneficio Ley 19.210 y total cobrado. La API no entrega una fotografía del comprobante.
- Si está activado **Adjuntar detalle TotalNet en PDF**, se genera un comprobante A4 con esos campos y se publica como nota interna con adjunto en la factura Odoo. El nombre incluye factura, ticket e ID de cupón; tanto el adjunto como la nota son idempotentes para evitar duplicados. Si el pago se crea pero falla el adjunto, el resultado se conserva como pago exitoso y se muestra una advertencia separada.
- El **`journal_id`** sale de mapear `transaccion.sello` (ej. "MasterCard") contra los diarios de Odoo (`Master BROU Aramid $`, `BROU M/N`, `Santander M/N`, etc. — ya existen varios diarios específicos por banco/marca en la instancia real). Este mapeo debe guardarse en config, no hardcodeado, porque puede haber más de un adquirente/marca de tarjeta.
- Si está activado **Redondear al peso**, se usa `ROUND_HALF_UP`: de 0,00 a 0,49 baja y de 0,50 a 0,99 sube. El pago se crea por el entero y Odoo marca la factura como totalmente pagada contabilizando la diferencia en la cuenta elegida mediante `payment_difference_handling="reconcile"` y `writeoff_account_id`.
- El redondeo sólo se admite cuando el importe TotalNet coincide con el total pendiente de Odoo sin redondear o con su entero esperado. Diferencias ajenas al redondeo (por ejemplo $9,00) permanecen bloqueadas. El beneficio Ley 19.210 se informa en el memo y no se trata como redondeo.

**Cómo probarlo**: contra una factura de prueba en Odoo, llamar este método a mano con datos de un cupón real y verificar en la interfaz de Odoo que el pago se creó bien, con el diario y memo correctos, y que la factura pasa a "Pagado"/"Pagado parcialmente".

### Paso 6 — Endpoints de conciliación + UI de revisión

`api/pos_reconciliation_endpoints.py` (nuevo router):
- `POST /sync` — llama a TotalNet + Odoo, corre el matching del Paso 4, y devuelve la propuesta de conciliación **sin escribir nada todavía**.
- `POST /confirm` — recibe qué filas confirmó el operador (con la factura elegida en los casos ambiguos) y recién ahí llama a `register_invoice_payment` por cada una.

#### Dónde va en el dashboard (`web/config.html`)

`web/config.html` **no es una app con pestañas/rutas separadas** — es una sola página larga con secciones en tarjetas (`<div class="card" id="...">`) que se muestran u ocultan según el modo. Confirmado leyendo el archivo real:

- Por defecto arranca en modo **"admin-only"** (`adminOnlyMode = true` en el JS, línea ~1444), que agrega la clase `admin-only` al `<body>`. La regla CSS `body.admin-only .admin-hide { display: none !important; }` (línea ~325) oculta todo lo que tenga la clase `admin-hide`. El botón "Mostrar panel completo" (`toggleAdminOnlyMode()`) saca ese modo y muestra todo.
- La sección **`id="administrado-section"`** (línea ~1118) es la única que **no** tiene `admin-hide` junto con `id="odoo-automation-section"` (línea ~1222, la de configuración/automatización Odoo+Administrado) — ambas quedan visibles siempre, porque son el flujo de despacho diario. En cambio `id="mercadolibre-section"` y las tarjetas de "Ventas listas para imprimir" de MercadoLibre sí tienen `admin-hide` — quedan ocultas hasta que alguien togglea el panel completo.

Para la conciliación de pagos POS, que es una tarea de contabilidad puntual (no algo que el operador de despacho necesite ver a diario), conviene agregarla **con la clase `admin-hide`**, siguiendo el mismo criterio que MercadoLibre — visible solo en el panel completo. Se agregaría como una tarjeta nueva, justo después de `odoo-automation-section` (que termina antes de la siguiente `<div class="card"`, buscar el cierre alrededor de la línea 1310-1390 según cómo vaya creciendo el archivo):

```html
<div class="card admin-hide" id="pos-reconciliation-section">
    <h2>Conciliacion de pagos POS (TotalNet)</h2>
    <p class="muted" style="margin-bottom: 12px;">
        Trae los cupones de TotalNet, los cruza contra facturas pendientes en Odoo y registra el pago tras confirmar.
    </p>
    <div class="form-group">
        <label>Fecha desde:</label>
        <input type="date" id="pos-sync-date-from">
    </div>
    <div class="form-group">
        <label>Fecha hasta:</label>
        <input type="date" id="pos-sync-date-to">
    </div>
    <button class="btn" onclick="syncPosReconciliation()">Sincronizar</button>
    <div class="table-scroll">
        <table class="table-clean">
            <thead>
                <tr>
                    <th></th>
                    <th>Fecha</th>
                    <th>Importe</th>
                    <th>Ticket / Autorizacion</th>
                    <th>Factura candidata</th>
                    <th>Estado</th>
                </tr>
            </thead>
            <tbody id="pos-reconciliation-body">
                <tr><td colspan="6">Sincroniza para ver cupones</td></tr>
            </tbody>
        </table>
    </div>
    <button class="btn success" onclick="confirmPosReconciliation()">Confirmar seleccionados</button>
</div>
```

Y en el bloque `<script>`, funciones `syncPosReconciliation()` / `confirmPosReconciliation()` que llaman a `/api/pos-reconciliation/sync` y `/api/pos-reconciliation/confirm`, siguiendo el mismo estilo que ya usan `syncAdministradoSales()` / `syncMercadoLibreSales()` (fetch + repintar la tabla, con un `<tbody id="...">` que se regenera con las filas de la respuesta, checkbox por fila para elegir qué confirmar, y un selector `<select>` en la columna "Factura candidata" para los casos ambiguos).

### Paso 7 — Estado/auditoría local

JSON en `%APPDATA%/EtiquetadorZPL/pos_reconciliation_state.json` (mismo patrón que `administrado_print_state.json` / `odoo_automation_state.json`): qué cupones ya se conciliaron, indexado por `transaccion.cupon_id` (identificador único que ya da la propia API) — para no duplicar pagos si se corre `/sync` dos veces sobre el mismo rango de fechas.

## Checklist de verificación end-to-end

- [ ] `totalnet_integration.get_cupones(...)` devuelve datos reales (Paso 1).
- [ ] El endpoint de prueba `/api/totalnet/cupones/test` funciona desde el navegador/Postman (Paso 2).
- [ ] La búsqueda de facturas pendientes en Odoo devuelve resultados esperados (Paso 3).
- [ ] Con datos de prueba, el matching clasifica bien los tres casos: único, ambiguo, sin match (Paso 4).
- [ ] `register_invoice_payment` contra una factura de prueba deja el pago bien registrado en Odoo, con diario y memo correctos (Paso 5).
- [ ] El flujo completo desde la pestaña nueva del dashboard: sincronizar, revisar, confirmar, y ver el pago reflejado en Odoo (Paso 6).
- [ ] Sincronizar el mismo rango de fechas dos veces no duplica pagos (Paso 7).

## Mejora opcional: capturar Autorización/Fact. en Odoo al momento de la venta

Confirmado con un comprobante físico real: el ticket que imprime la terminal trae, además del Ticket, la **Autorización** y el **No.Fact.** — ambos reaparecen tal cual en los cupones de la API (`transaccion.autorizacion`, `transaccion.numero_factura`). Si en algún momento se empieza a anotar ese número (6 dígitos) en Odoo al cargar la venta (ej. como referencia en la orden), el matching del Paso 4 se vuelve determinístico desde el primer nivel, sin depender nunca del matching por monto+fecha. Es un cambio de proceso menor, no bloquea construir la v1.

## Apéndice: plan B (si el acceso a la API de TotalNet no está disponible)

Si por algún motivo no se puede conseguir/usar el acceso a la API (esta guía asume que sí), la alternativa es un flujo manual basado en el PDF de liquidación que emite TotalNet:

- El PDF trae 5 páginas; solo la página 2 ("SOBRES Y CUPONES PRESENTADOS") tiene el detalle transaccional útil (fecha, importe, tarjeta enmascarada, Cód.Autor., Fact., Lote). Las demás páginas son un comprobante de retenciones DGI y una factura de TotalNet por su propio servicio — no aportan al matching.
- El PDF **no incluye el Ticket** (solo está en el comprobante físico y en el portal web de TotalNet) — pero si se captura Autorización o Fact. en Odoo (ver sección anterior), tampoco hace falta.
- Habría que parsear la tabla del PDF con una librería que entienda la estructura de grilla (ej. `pdfplumber`), no con texto plano + regex, porque el texto de celdas como "Lote" puede aparecer mezclado con el de la celda de tarjeta.
- El operador subiría el PDF manualmente a una pestaña del dashboard (no hay carpeta monitoreada ni scraping del portal en este plan B) y el resto del flujo (matching, revisión, confirmación, registro del pago) es idéntico al de la API — el Paso 4 en adelante de esta guía se reutiliza sin cambios, solo cambia de dónde vienen los "cupones" (parseados del PDF en vez de la respuesta de `/cupones`).

## Conciliación asistida en segundo plano

`src/pos_reconciliation_worker.py` corre dentro de la API local (se inicia en el `startup` de `api/fastapi_real.py`) y se configura desde la vista POS, en el panel **Conciliación automática en segundo plano**. Todo está apagado por defecto.

- **Sincronización periódica** (`auto_sync_enabled`, `auto_sync_interval_minutes` ≥ 15, `auto_sync_lookback_days`): cada intervalo corre la misma propuesta que el botón Sincronizar (`pos_reconciliation_service.build_sync_proposal`) sobre los últimos N días de venta hasta ayer, y la guarda en `pos_reconciliation_auto_state.json`. No escribe en Odoo.
- **Aviso**: el banner de la vista POS muestra cuántos pagos están listos para revisar y cuántos son ambiguos; "Revisar propuesta" carga esa propuesta en las tablas de siempre para confirmarla con el flujo manual. Con `auto_sync_notify_desktop` además sale una notificación de escritorio, una sola vez por cupón.
- **Registro automático opcional** (`auto_register_deterministic` + `auto_register_operator`): registra solo las coincidencias que pasan `pos_reconciliation.find_deterministic_matches`. Las condiciones son: número de factura informado por TotalNet, importe exacto sin redondeo, misma moneda, factura `not_paid` con saldo igual al total, diario resuelto por el mapeo por sello y ningún otro cupón del lote con ese número de factura. Todo lo demás (ambiguos, diferencias, fallback por importe/fecha y tickets manuales) sigue esperando confirmación. Los pagos automáticos quedan en el historial con `mode = automatico_deterministico` y el operador elegido, y `register_invoice_payment` vuelve a validar estado e importe en Odoo antes de crear cada pago.

Endpoints: `GET /api/pos-reconciliation/auto/status`, `GET /api/pos-reconciliation/auto/proposal`, `POST /api/pos-reconciliation/auto/run-once`. La configuración se guarda con el `POST /api/pos-reconciliation/config` de siempre.
