import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import card_magstripe as mag
import photo_crop_endpoints
from test_card_designer import CardSessionCase, FakePrintJob, design


class MagstripeRulesTests(unittest.TestCase):
    def test_normalize_and_validate_iso_tracks(self):
        self.assertEqual(mag.normalize_track(1, " %perez^ana? "), "PEREZ^ANA")
        self.assertEqual(mag.normalize_track(2, ";1234=5678?"), "1234=5678")
        self.assertIsNone(mag.track_error(1, "PEREZ ANA 12-3"))
        self.assertIn("no admitidos", mag.track_error(1, "PÉREZ"))
        self.assertIn("no admitidos", mag.track_error(2, "12A4"))
        self.assertIn("hasta 37", mag.track_error(2, "1" * 38))
        self.assertIsNone(mag.track_error(3, "1" * 104))

    def test_profiles_and_strings(self):
        self.assertEqual(mag.detect_profile("Magicard Enduro3E").id, "magicard")
        self.assertEqual(mag.detect_profile("XPS Card Printer").id, "entrust")
        self.assertEqual(mag.detect_profile("Zebra ZXP Series 3 USB Card Printer").id, "zebra")
        self.assertEqual(mag.detect_profile("Swiftpro K30").id, "swiftpro")
        zebra = next(item for item in mag.public_profiles() if item["id"] == "zebra")
        self.assertEqual(zebra["start"], ["${1", "${2", "${3"])
        self.assertEqual(zebra["end"], ["}$", "}$", "}$"])
        strings = mag.encoding_strings({1: "ANA", 3: "123"}, ["~1", "~2", "~3"], ["", "", ""])
        self.assertEqual(strings, ["~1ANA", "~3123"])


class MagstripePrintTests(CardSessionCase):
    def mag_design(self, **tracks):
        card_design = design()
        card_design["magstripe"] = {"enabled": True, "side": "back", **tracks}
        return card_design

    def test_check_reports_track_problems(self):
        card_design = self.mag_design(track1="{Nombre} {Apellido}", track2="{Legajo}")
        response = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/check",
                                    json={"design": card_design, "items": self.items()})
        self.assertEqual(response.status_code, 200, response.text)
        messages = [issue["message"] for result in response.json()["results"] for issue in result["issues"]]
        # "Pérez" lleva tilde y el legajo "L0" tiene una letra: ambos son errores ISO.
        self.assertTrue(any("pista 1" in message and "no admitidos" in message for message in messages))
        self.assertTrue(any("pista 2" in message for message in messages))

    def test_print_sends_encoding_text_with_profile_commands(self):
        FakePrintJob.instances = []
        card_design = self.mag_design(track1="{Nombre}", track3="{Nro}000")
        with patch.object(photo_crop_endpoints.card_printing, "CardPrintJob", FakePrintJob), \
                patch.object(photo_crop_endpoints.card_printing, "append_print_log"):
            response = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/print", json={
                "design": card_design, "items": self.items()[:2], "printer": "Zebra ZXP Series 3",
                "encode": True, "mag_start": ["${1", "${2", "${3"], "mag_end": ["}$", "}$", "}$"],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["encoded"], 2)
        self.assertEqual(FakePrintJob.instances[0].encodings, [["${1PERSONA 0}$", "${31000}$"], ["${1PERSONA 1}$", "${32000}$"]])

    def test_print_rejects_invalid_track_data(self):
        card_design = self.mag_design(track2="{Nombre}")
        with patch.object(photo_crop_endpoints.card_printing, "CardPrintJob", FakePrintJob):
            response = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/print", json={
                "design": card_design, "items": self.items()[:1], "printer": "Magicard", "encode": True,
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("pista 2", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
