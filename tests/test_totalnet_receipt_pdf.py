import sys
import unittest
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from totalnet_receipt_pdf import (  # noqa: E402
    build_totalnet_receipt_filename,
    generate_totalnet_transaction_pdf,
)


class TestTotalNetReceiptPDF(unittest.TestCase):
    @staticmethod
    def _coupon():
        return {
            "cupon_id": 931583957,
            "numero_factura": 30277,
            "ticket": 775,
            "autorizacion": "173868",
            "lote": 375,
            "producto": "DEBITO",
            "moneda": "UYU",
            "importe": 1292.02,
            "propina": 0,
            "cuotas": 1,
            "sello": "MASTERCARD",
            "bin": "223138",
            "ultimos_4_digitos": "5878",
            "terminal": "30983093",
            "fecha_liquidacion": "13/08/2026",
            "importe_devolucion_impuesto": 21.18,
            "devolucion_impuesto": 6,
            "total_pagado": 1270.84,
            "forma_pago": "Transferencia",
            "banco_acreditacion": "BANCO DE LA REPUBLICA",
            "fecha_pago": "14/08/2026",
        }

    def test_pdf_contains_structured_totalnet_transaction_details(self):
        pdf_bytes = generate_totalnet_transaction_pdf(self._coupon())

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()

        self.assertIn("Detalle de la transacción", text)
        self.assertIn("30277", text)
        self.assertIn("173868", text)
        self.assertIn("5878", text)
        self.assertIn("1.292,02", text)
        self.assertIn("1.270,84", text)
        self.assertIn("BANCO DE LA REPUBLICA", text)

    def test_filename_is_unique_per_coupon(self):
        self.assertEqual(
            build_totalnet_receipt_filename(self._coupon()),
            "TotalNet_Fact_30277_Ticket_775_Cupon_931583957.pdf",
        )


if __name__ == "__main__":
    unittest.main()
