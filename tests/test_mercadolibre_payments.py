import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import mercadolibre_payment_service as service  # noqa: E402
from mercadolibre_payment_pdf import (  # noqa: E402
    build_mercadolibre_payment_filename,
    generate_mercadolibre_payment_pdf,
)


def _order(status="paid"):
    return {
        "id": 2000015420705457,
        "status": status,
        "date_created": "2026-10-07T10:00:00.000-03:00",
        "date_closed": "2026-10-07T10:03:00.000-03:00",
        "total_amount": 1154.0,
        "paid_amount": 1154.0,
        "currency_id": "UYU",
        "buyer": {"id": 44, "nickname": "comprador"},
        "shipping": {"id": 456789},
        "payments": [
            {
                "id": 99887766,
                "status": "approved",
                "transaction_amount": 1154.0,
                "payment_method_id": "account_money",
                "payment_type": "account_money",
                "installments": 1,
                "date_approved": "2026-10-07T10:03:00.000-03:00",
            }
        ],
        "order_items": [
            {"quantity": 2, "item": {"id": "MLU123", "title": "Etiquetas personalizadas"}}
        ],
    }


PACK_ID = 2000015420705457


def _pack_order(order_id=2000018868191948, product_amount=894.0, payment_id=99887766):
    order = _order()
    order.update({
        "id": order_id,
        "pack_id": PACK_ID,
        "total_amount": product_amount,
        "paid_amount": product_amount,
    })
    order["payments"] = [{**order["payments"][0], "id": payment_id, "transaction_amount": product_amount}]
    return order


class _FakeMercadoLibre:
    def __init__(self, order=None, orders=None, shipping_cost=0.0):
        self.orders = {str(item["id"]): item for item in (orders or [order or _order()])}
        self.shipping_cost = shipping_cost
        self.cost_calls = []

    def search_orders(self, limit=20, offset=0, status="paid"):
        return {
            "results": [
                {"id": item["id"], "pack_id": item.get("pack_id")} for item in self.orders.values()
            ]
        }

    def get_order(self, order_id):
        if str(order_id) not in self.orders:
            raise ValueError("orden inesperada")
        return dict(self.orders[str(order_id)])

    def get_pack(self, pack_id, use_cache=True):
        self.cache_flags = getattr(self, "cache_flags", []) + [("pack", use_cache)]
        return {
            "id": pack_id,
            "orders": [
                {"id": item["id"]} for item in self.orders.values()
                if str(item.get("pack_id")) == str(pack_id)
            ],
        }

    def get_shipment_costs(self, shipment_id, use_cache=True):
        self.cost_calls.append(shipment_id)
        self.cache_flags = getattr(self, "cache_flags", []) + [("costs", use_cache)]
        return {"receiver": {"cost": self.shipping_cost}}


class _FakeOdoo:
    def __init__(self, can_register=True, amount_due=None):
        self.can_register = can_register
        self.amount_due = amount_due
        self.payment_calls = []
        self.attachment_calls = []
        self.lookups = []

    def find_sale_invoice_for_reference(
        self, reference, amount, currency, auth_override=None, amount_tolerance=0.01
    ):
        self.lookups.append((reference, amount, currency))
        self.tolerances = getattr(self, "tolerances", []) + [amount_tolerance]
        if not self.can_register:
            return {"can_register": False, "reason": "Factura ya pagada", "invoice": None}
        return {
            "can_register": True,
            "reason": "",
            "sale_order": {"id": 80, "name": f"ML {reference}"},
            "invoice": {
                "id": 100,
                "name": "e-Ticket A-31028",
                "amount_due": amount if self.amount_due is None else self.amount_due,
                "currency_id": [46, currency],
                "invoice_payment_state": "not_paid",
            },
        }

    def register_invoice_payment(self, *args, **kwargs):
        self.payment_calls.append(args)
        self.payment_kwargs = kwargs
        return {"invoice_id": 100, "payment_id": 950, "payment_state": "in_payment"}

    def attach_pdf_to_payment(self, payment_id, filename, pdf_bytes, auth_override=None):
        self.attachment_calls.append((payment_id, filename, pdf_bytes, auth_override))
        return {"attachment_id": 700, "attachment_created": True, "filename": filename}

    def record_url(self, model, record_id):
        return f"https://odoo.test/web#id={record_id}&model={model}"


class TestMercadoLibrePaymentPDF(unittest.TestCase):
    def test_pdf_contains_order_payment_and_invoice_details(self):
        pdf_bytes = generate_mercadolibre_payment_pdf(_order(), "e-Ticket A-31028")

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()

        self.assertIn("Comprobante de pago Mercado Libre", text)
        self.assertIn("2000015420705457", text)
        self.assertIn("e-Ticket A-31028", text)
        self.assertIn("99887766", text)
        self.assertIn("1.154,00", text)
        self.assertIn("Etiquetas personalizadas", text)
        self.assertIn("Pagada", text)
        self.assertIn("Aprobado", text)
        self.assertIn("Dinero en cuenta de Mercado Pago", text)
        self.assertIn("07/10/2026 10:03", text)
        self.assertNotIn("account_money", text)
        self.assertNotIn("approved", text)

    def test_pdf_deduplicates_pack_payments_and_shows_every_product(self):
        order = _order()
        order.update({"pack_id": 2000015401940571, "order_ids": ["1", "2", "3"]})
        order["payments"] = [dict(order["payments"][0], id=pid) for pid in (11, 22, 33)]
        order["order_items"] = [
            {"quantity": 1, "item": {"title": f"Producto largo numero {n} para plastificar documentos A4"}}
            for n in range(1, 9)
        ]

        document = fitz.open(stream=generate_mercadolibre_payment_pdf(order, "e-Factura A-50976"), filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()

        self.assertEqual(text.count("Dinero en cuenta de Mercado Pago"), 1)
        self.assertEqual(text.count("Aprobado"), 1)
        self.assertIn("11, 22, 33", text)
        self.assertIn("Sin cuotas", text)
        for n in range(1, 9):
            self.assertIn(f"Producto largo numero {n}", text)

    def test_card_payment_shows_type_brand_and_installments(self):
        order = _order()
        order["payments"][0].update(
            {"payment_method_id": "visa", "payment_type": "credit_card", "installments": 3}
        )
        document = fitz.open(stream=generate_mercadolibre_payment_pdf(order), filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()

        self.assertIn("Tarjeta de crédito Visa", text)
        self.assertIn("3 cuotas", text)

    def test_filename_is_idempotent_per_order_and_payment(self):
        self.assertEqual(
            build_mercadolibre_payment_filename(_order()),
            "MercadoLibre_Orden_2000015420705457_Pago_99887766.pdf",
        )


class TestMercadoLibrePaymentService(unittest.TestCase):
    def test_proposal_only_enables_exact_pending_invoice(self):
        result = service.build_payment_proposal(_FakeMercadoLibre(), _FakeOdoo(), 20)

        self.assertEqual(result["ready_count"], 1)
        self.assertTrue(result["items"][0]["can_register"])
        self.assertEqual(result["items"][0]["invoice"]["name"], "e-Ticket A-31028")
        self.assertEqual(result["items"][0]["payment_reference"], "99887766")

    def test_register_creates_payment_then_attaches_pdf_to_that_payment(self):
        odoo = _FakeOdoo()
        auth = {"username": "vale@example.com", "password": "secret"}
        with patch.object(service, "get_branding", return_value=None):
            result = service.register_order_payment(
                _FakeMercadoLibre(),
                odoo,
                order_id="2000015420705457",
                journal_id=12,
                auth_override=auth,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["attachment_ok"])
        self.assertEqual(result["memo"], "e-Ticket A-31028 - 2000015420705457")
        self.assertEqual(odoo.payment_calls[0][0:5], (100, 1154.0, "2026-10-07", 12, result["memo"]))
        self.assertEqual(odoo.payment_calls[0][5], auth)
        self.assertTrue(odoo.payment_calls[0][6])
        payment_id, filename, pdf_bytes, attachment_auth = odoo.attachment_calls[0]
        self.assertEqual(payment_id, 950)
        self.assertEqual(filename, "MercadoLibre_Orden_2000015420705457_Pago_99887766.pdf")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(attachment_auth, auth)
        self.assertIn("model=account.payment", result["payment_url"])

    def test_register_revalidates_invoice_and_never_duplicates_paid_invoice(self):
        odoo = _FakeOdoo(can_register=False)
        with self.assertRaisesRegex(ValueError, "Factura ya pagada"):
            service.register_order_payment(
                _FakeMercadoLibre(),
                odoo,
                order_id="2000015420705457",
                journal_id=12,
                auth_override={"username": "vale@example.com", "password": "secret"},
            )

        self.assertEqual(odoo.payment_calls, [])
        self.assertEqual(odoo.attachment_calls, [])


    def test_pack_sale_uses_pack_id_and_adds_buyer_shipping(self):
        mercadolibre = _FakeMercadoLibre(orders=[_pack_order()], shipping_cost=260.0)
        odoo = _FakeOdoo(amount_due=1154.01)

        result = service.build_payment_proposal(mercadolibre, odoo, 20)

        item = result["items"][0]
        self.assertEqual(odoo.lookups, [("2000015420705457", 1154.0, "UYU")])
        self.assertEqual(item["order_id"], "2000018868191948")
        self.assertEqual(item["reference"], "2000015420705457")
        self.assertEqual(item["products_amount"], 894.0)
        self.assertEqual(item["shipping_amount"], 260.0)
        self.assertEqual(item["amount"], 1154.0)
        self.assertEqual(item["rounding_difference"], 0.01)
        self.assertTrue(item["can_register"])

    def test_single_order_paid_amount_with_shipping_is_not_counted_twice(self):
        # Orden suelta real: total_amount 363 (productos), paid_amount 532
        # (ya incluye el envio de 169). La factura Odoo es 532,01.
        order = _order()
        order.update({"total_amount": 363.0, "paid_amount": 532.0})
        order["payments"][0]["transaction_amount"] = 363.0
        mercadolibre = _FakeMercadoLibre(order=order, shipping_cost=169.0)
        odoo = _FakeOdoo(amount_due=532.01)

        item = service.build_payment_proposal(mercadolibre, odoo, 20)["items"][0]

        self.assertEqual(item["products_amount"], 363.0)
        self.assertEqual(item["shipping_amount"], 169.0)
        self.assertEqual(item["amount"], 532.0)
        self.assertEqual(item["rounding_difference"], 0.01)

    def test_proposal_reuses_complete_search_results_without_order_detail_calls(self):
        order = _order()

        class _SearchWithDetails(_FakeMercadoLibre):
            detail_calls = 0

            def search_orders(self, limit=20, offset=0, status="paid"):
                return {"results": [dict(order)]}

            def get_order(self, order_id):
                type(self).detail_calls += 1
                return super().get_order(order_id)

        mercadolibre = _SearchWithDetails(order=order, shipping_cost=0.0)
        result = service.build_payment_proposal(mercadolibre, _FakeOdoo(), 20)

        self.assertEqual(result["count"], 1)
        self.assertEqual(_SearchWithDetails.detail_calls, 0)

    def test_proposal_uses_cache_but_registration_reads_fresh_data(self):
        mercadolibre = _FakeMercadoLibre(orders=[_pack_order()], shipping_cost=260.0)
        service.build_payment_proposal(mercadolibre, _FakeOdoo(), 20)
        self.assertEqual(mercadolibre.cache_flags, [("pack", True), ("costs", True)])

        mercadolibre.cache_flags = []
        with patch.object(service, "get_branding", return_value=None):
            service.register_order_payment(
                mercadolibre,
                _FakeOdoo(),
                order_id="2000018868191948",
                journal_id=12,
                auth_override=None,
            )
        self.assertEqual(mercadolibre.cache_flags, [("pack", False), ("costs", False)])

    def test_pack_groups_all_orders_and_charges_shipping_once(self):
        orders = [
            _pack_order(2000018868191948, 500.0, 111),
            _pack_order(2000018868191949, 394.0, 222),
        ]
        mercadolibre = _FakeMercadoLibre(orders=orders, shipping_cost=260.0)
        odoo = _FakeOdoo()

        result = service.build_payment_proposal(mercadolibre, odoo, 20)

        self.assertEqual(result["count"], 1)
        item = result["items"][0]
        self.assertEqual(item["order_ids"], ["2000018868191948", "2000018868191949"])
        self.assertEqual(item["payment_reference"], "111, 222")
        self.assertEqual(item["amount"], 1154.0)
        self.assertEqual(len(mercadolibre.cost_calls), 1)

    def test_register_pack_writes_off_rounding_cent_to_rounding_account(self):
        mercadolibre = _FakeMercadoLibre(orders=[_pack_order()], shipping_cost=260.0)
        odoo = _FakeOdoo(amount_due=1154.01)
        with patch.object(service, "get_branding", return_value=None):
            result = service.register_order_payment(
                mercadolibre,
                odoo,
                order_id="2000018868191948",
                journal_id=12,
                auth_override=None,
                rounding_account_id=31,
            )

        self.assertEqual(result["memo"], "e-Ticket A-31028 - 2000015420705457")
        self.assertEqual(result["rounding_difference"], 0.01)
        self.assertEqual(odoo.payment_calls[0][1], 1154.0)
        self.assertEqual(odoo.payment_calls[0][7], 31)
        self.assertEqual(odoo.payment_kwargs["writeoff_label"], "Redondeo cobro Mercado Libre")
        _, filename, pdf_bytes, _ = odoo.attachment_calls[0]
        self.assertEqual(filename, "MercadoLibre_Orden_2000015420705457_Pago_99887766.pdf")
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()
        self.assertIn("2000018868191948", text)
        self.assertIn("260,00", text)
        self.assertIn("1.154,00", text)

    def test_tolerance_allows_one_cent_per_invoiced_line(self):
        # Caso e-Factura A-50975: 2 x 525,00 + envio 43,00 en ML; Odoo factura
        # 1.050,01 + 43,01 = 1.093,02 por el IVA recalculado en cada linea.
        order = _pack_order(product_amount=1050.0)
        odoo = _FakeOdoo(amount_due=1093.02)
        with patch.object(service, "get_branding", return_value=None):
            result = service.register_order_payment(
                _FakeMercadoLibre(orders=[order], shipping_cost=43.0),
                odoo,
                order_id=str(order["id"]),
                journal_id=12,
                auth_override=None,
                rounding_account_id=31,
            )

        self.assertEqual(odoo.tolerances, [0.02])
        self.assertEqual(result["rounding_difference"], 0.02)
        self.assertEqual(odoo.payment_calls[0][1], 1093.0)
        self.assertEqual(odoo.payment_calls[0][7], 31)

    def test_difference_above_line_tolerance_is_rejected(self):
        order = _pack_order(product_amount=1050.0)
        odoo = _FakeOdoo(amount_due=1093.03)
        with self.assertRaisesRegex(ValueError, "no coincide"):
            service.register_order_payment(
                _FakeMercadoLibre(orders=[order], shipping_cost=43.0),
                odoo,
                order_id=str(order["id"]),
                journal_id=12,
                auth_override=None,
                rounding_account_id=31,
            )
        self.assertEqual(odoo.payment_calls, [])

    def test_rounding_cent_requires_rounding_account(self):
        odoo = _FakeOdoo(amount_due=1154.01)
        with self.assertRaisesRegex(ValueError, "cuenta de redondeo"):
            service.register_order_payment(
                _FakeMercadoLibre(orders=[_pack_order()], shipping_cost=260.0),
                odoo,
                order_id="2000018868191948",
                journal_id=12,
                auth_override=None,
            )
        self.assertEqual(odoo.payment_calls, [])

    def test_exact_amount_does_not_use_rounding_account(self):
        odoo = _FakeOdoo()
        with patch.object(service, "get_branding", return_value=None):
            service.register_order_payment(
                _FakeMercadoLibre(orders=[_pack_order()], shipping_cost=260.0),
                odoo,
                order_id="2000018868191948",
                journal_id=12,
                auth_override=None,
                rounding_account_id=31,
            )
        self.assertIsNone(odoo.payment_calls[0][7])


if __name__ == "__main__":
    unittest.main()
