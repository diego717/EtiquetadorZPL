import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import odoo_endpoints as endpoints


class _FakeOdooIntegration:
    def __init__(self):
        self.calls = []

    def list_products(
        self,
        search="",
        limit=200,
        offset=0,
        active_only=True,
        inventory_only=True,
        include_stock=True,
    ):
        self.calls.append(
            {
                "search": search,
                "limit": limit,
                "offset": offset,
                "active_only": active_only,
                "inventory_only": inventory_only,
                "include_stock": include_stock,
            }
        )
        return {
            "items": [
                {
                    "id": 55,
                    "default_code": "ETI-001",
                    "barcode": "779000000001",
                    "name": "[ETI-001] Etiqueta Premium",
                    "list_price": 120.5,
                    "qty_available": 9,
                    "virtual_available": 7,
                    "incoming_qty": 2,
                    "outgoing_qty": 4,
                    "uom": "Units",
                    "category": "Etiquetas",
                    "active": True,
                    "type": "product",
                }
            ],
            "total": 1,
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "filters": {},
        }

    def save_config(self, updates):
        self.saved_config = updates

    def humanize_exception(self, exc):
        return str(exc)


class TestOdooProductEndpoints(unittest.TestCase):
    def test_list_products_passes_query_options_to_integration(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake):
            result = asyncio.run(
                endpoints.list_products(
                    search="eti",
                    limit=50,
                    offset=10,
                    active_only=False,
                    inventory_only=True,
                    include_stock=False,
                )
            )

        self.assertEqual(result["items"][0]["default_code"], "ETI-001")
        self.assertEqual(
            fake.calls[0],
            {
                "search": "eti",
                "limit": 50,
                "offset": 10,
                "active_only": False,
                "inventory_only": True,
                "include_stock": False,
            },
        )

    def test_export_products_returns_csv_stream(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake):
            response = asyncio.run(endpoints.export_products(search="eti", limit=1000, offset=0))

        async def _read_body():
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        body = asyncio.run(_read_body()).decode("utf-8-sig")

        self.assertEqual(response.headers["content-disposition"], "attachment; filename=productos_odoo.csv")
        self.assertIn("default_code,barcode,name", body)
        self.assertIn("ETI-001,779000000001", body)


if __name__ == "__main__":
    unittest.main()
