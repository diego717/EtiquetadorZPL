import io
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import photo_enhance as enhance
from test_card_designer import CardSessionCase, design


def portrait(size=(300, 400), cast=(0, 0, 0)):
    """Rostro sintético sobre fondo gris con ruido y, opcionalmente, una dominante de color."""
    rng = np.random.default_rng(3)
    image = Image.new("RGB", size, (150 + cast[0], 150 + cast[1], 150 + cast[2]))
    draw = ImageDraw.Draw(image)
    draw.ellipse((size[0] * 0.25, size[1] * 0.2, size[0] * 0.75, size[1] * 0.75), fill=(205 + cast[0], 160 + cast[1], 135 + cast[2]))
    draw.ellipse((size[0] * 0.38, size[1] * 0.4, size[0] * 0.45, size[1] * 0.45), fill=(40, 30, 30))
    draw.ellipse((size[0] * 0.55, size[1] * 0.4, size[0] * 0.62, size[1] * 0.45), fill=(40, 30, 30))
    noisy = np.asarray(image, np.int16) + rng.normal(0, 9, (size[1], size[0], 3)).astype(np.int16)
    return Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))


class EnhanceTests(unittest.TestCase):
    def test_auto_enhance_reduces_noise_and_color_cast(self):
        source = portrait(cast=(18, 4, -16))
        result = enhance.auto_enhance(source, "normal")
        self.assertEqual(result.size, source.size)
        background = lambda image: np.asarray(image, np.float32)[5:60, 5:60]  # noqa: E731
        self.assertLess(background(result).std(axis=(0, 1)).mean(), background(source).std(axis=(0, 1)).mean() * 0.7)
        cast_before = np.ptp(background(source).mean(axis=(0, 1)))
        cast_after = np.ptp(background(result).mean(axis=(0, 1)))
        self.assertLess(cast_after, cast_before * 0.7)
        self.assertIs(enhance.auto_enhance(source, "off"), source)

    def test_upscale_only_when_needed(self):
        self.assertFalse(enhance.needs_upscale((400, 500), (283, 378)))
        self.assertTrue(enhance.needs_upscale((120, 160), (283, 378)))
        self.assertGreater(enhance.missing_scale((60, 80), (283, 378)), enhance.TOO_SMALL)
        small = portrait((90, 120))
        result, used_ai = enhance.improve(small, (283, 378), level="soft", upscale=True)
        if enhance.model_path() is None:
            self.skipTest("modelo Real-ESRGAN no disponible")
        self.assertTrue(used_ai)
        self.assertGreaterEqual(result.width, 283)
        self.assertGreaterEqual(result.height, 378)
        large, used_ai = enhance.improve(portrait((600, 800)), (283, 378), level="soft", upscale=True)
        self.assertFalse(used_ai)
        self.assertLessEqual(large.width, round(283 * 1.25) + 2)


class EnhanceEndpointTests(CardSessionCase):
    def upload_small(self):
        output = io.BytesIO()
        portrait((90, 120)).save(output, "JPEG", quality=60)
        response = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/photos", params={"filename": "chica.jpg"},
            content=output.getvalue(), headers={"Content-Type": "image/jpeg"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_preview_check_and_export_use_enhancement(self):
        photo = self.upload_small()
        item = {"photo_id": photo["id"], "crop": [0, 0, 90, 120], "metadata": {"Nombre": "Ana"}}
        preview = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/enhance-preview", json={
            "item": item, "design": design(), "enhance": "normal", "upscale": True,
        })
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.headers["content-type"], "image/jpeg")
        if enhance.model_path() is not None:
            self.assertEqual(preview.headers["x-upscaled"], "1")
        check = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/check", json={
            "design": design(), "items": [item], "upscale": True,
        }).json()
        messages = [issue["message"] for result in check["results"] for issue in result["issues"]]
        self.assertTrue(any("baja resolución" in message for message in messages), messages)
        exported = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/export", json={
            "design": design(), "items": [item], "enhance": "strong", "upscale": True,
            "output": {"format": "PNG"},
        })
        self.assertEqual(exported.status_code, 200, exported.text)
        import photo_crop_endpoints

        record = photo_crop_endpoints.STORE.get(self.session_id).photos[photo["id"]]
        cached = len(record.enhance_cache)  # vista previa (normal) + exportación (intensa)
        self.assertEqual(cached, 2)
        again = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/cards/export", json={
            "design": design(), "items": [item], "enhance": "strong", "upscale": True, "output": {"format": "PNG"},
        })
        self.assertEqual(again.status_code, 200)
        self.assertEqual(len(record.enhance_cache), cached)  # reutiliza la foto ya mejorada

if __name__ == "__main__":
    unittest.main()
