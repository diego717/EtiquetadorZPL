import base64
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from client_assets_service import ClientAssetsService


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0xkAAAAASUVORK5CYII="
)


class TestClientAssetsService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.root_folder = self.temp_path / "clientes"
        self.root_folder.mkdir(parents=True, exist_ok=True)
        self.preview_cache = self.temp_path / "cache"

        client_folder = self.root_folder / "I" / "Instituto Antonio Carbajal"
        client_folder.mkdir(parents=True, exist_ok=True)

        self._write_file(client_folder / "IAC_credito_2025.cdr", "dummy cdr")
        self._write_file(client_folder / "credito_frente.cdr", "dummy cdr")
        self._write_file(client_folder / "IAC_otro.cdr", "dummy cdr")

        other_folder = self.root_folder / "O" / "Otro Cliente"
        other_folder.mkdir(parents=True, exist_ok=True)
        self._write_file(other_folder / "OTRO_credito.cdr", "dummy cdr")

        arcos_biomedical = self.root_folder / "A" / "Arcos Biomedical"
        arcos_biomedical.mkdir(parents=True, exist_ok=True)
        self._write_file(arcos_biomedical / "Tarjeta credito.cdr", "dummy cdr")

        arcos_industrial = self.root_folder / "A" / "Arcos Industrial"
        arcos_industrial.mkdir(parents=True, exist_ok=True)
        self._write_file(arcos_industrial / "Otro credito.cdr", "dummy cdr")

        self.service = ClientAssetsService()
        self.service.config_path = self.temp_path / "client_assets_config.json"
        self.service.config = {
            **self.service.config,
            "root_folder": str(self.root_folder),
            "preview_cache_dir": str(self.preview_cache),
            "credito_keyword": "credito",
            "corel_enabled": False,
            "embedded_thumbnail_fallback": True,
            "max_files_per_client": 100,
            "preview_width": 1200,
            "preview_height": 0,
            "preview_dpi": 120,
            "corel_macro": {
                "enabled": False,
                "project_name": "",
                "module_name": "ClientAssetsPrepare",
                "entrypoint": "PrepareClientAsset",
                "profile_entrypoints": {
                    "tarjetas_plasticas": "PrepareTarjetasPlasticas",
                    "tarjetas_laminar_tinta_a": "PrepareTarjetasLaminarTintaA",
                    "tarjetas_laminar_tinta_b": "PrepareTarjetasLaminarTintaB",
                },
                "fallback_to_python_prepare": True,
                "debug_enabled": True,
            },
            "corel_prepare_profiles": {
                "tarjetas_plasticas": {
                    "label": "Tarjetas plasticas",
                    "printer_name": "Printer PVC",
                    "paper_name": "PVC A4",
                    "orientation": "landscape",
                    "print_profile_name": "Perfil PVC",
                    "notes": "Perfil principal PVC",
                },
                "tarjetas_laminar_tinta_a": {
                    "label": "Tarjetas para laminar / tinta - Impresora A",
                    "printer_name": "Printer Tinta A",
                    "paper_name": "Lamina",
                    "orientation": "portrait",
                    "print_profile_name": "Perfil Tinta",
                    "notes": "",
                },
                "tarjetas_laminar_tinta_b": {
                    "label": "Tarjetas para laminar / tinta - Impresora B",
                    "printer_name": "Printer Tinta B",
                    "paper_name": "Lamina",
                    "orientation": "portrait",
                    "print_profile_name": "Perfil Tinta",
                    "notes": "",
                },
            },
        }

    def tearDown(self):
        self.service.shutdown()
        self.temp_dir.cleanup()

    def test_search_by_acronym_returns_credito_files_only(self):
        payload = self.service.search_client_assets("IAC")

        self.assertEqual(payload["search_mode"], "recursive_filename")
        self.assertEqual(payload["match_count"], 2)
        self.assertEqual(payload["warnings"], [])

        names = [item["name"] for item in payload["items"]]
        self.assertEqual(names, ["IAC_credito_2025.cdr", "credito_frente.cdr"])
        self.assertTrue(all(item["contains_credito"] for item in payload["items"]))
        self.assertEqual(payload["items"][0]["match_reason"], "acronym")
        self.assertEqual(payload["items"][1]["match_reason"], "path_hint")

    def test_search_by_full_name_matches_same_files(self):
        acronym_payload = self.service.search_client_assets("IAC")
        full_name_payload = self.service.search_client_assets("Instituto Antonio Carbajal")

        acronym_paths = {item["relative_path"] for item in acronym_payload["items"]}
        full_name_paths = {item["relative_path"] for item in full_name_payload["items"]}
        self.assertEqual(acronym_paths, full_name_paths)
        self.assertEqual(full_name_payload["match_count"], 2)
        self.assertTrue(
            any("Instituto Antonio Carbajal" in directory for directory in full_name_payload["matched_directories"])
        )

    def test_search_returns_warning_when_no_credito_match(self):
        payload = self.service.search_client_assets("Inexistente")

        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["match_count"], 0)
        self.assertTrue(payload["warnings"])

    def test_contains_credito_flag_depends_on_filename_even_when_keyword_filter_is_disabled(self):
        self.service.config["credito_keyword"] = ""

        payload = self.service.search_client_assets("IAC", match_mode="broad")

        items_by_name = {item["name"]: item for item in payload["items"]}
        self.assertIn("IAC_credito_2025.cdr", items_by_name)
        self.assertIn("IAC_otro.cdr", items_by_name)
        self.assertTrue(items_by_name["IAC_credito_2025.cdr"]["contains_credito"])
        self.assertFalse(items_by_name["IAC_otro.cdr"]["contains_credito"])

    def test_multiword_search_requires_more_than_single_partial_token_match(self):
        payload = self.service.search_client_assets("Arcos Biomedical")

        self.assertEqual(payload["match_mode"], "strict")
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual([item["relative_path"] for item in payload["items"]], [str(Path("A") / "Arcos Biomedical" / "Tarjeta credito.cdr")])
        self.assertEqual(payload["items"][0]["match_reason"], "path_hint")

    def test_broad_search_can_include_partial_token_matches(self):
        payload = self.service.search_client_assets("Arcos Biomedical", match_mode="broad")

        self.assertEqual(payload["match_mode"], "broad")
        self.assertEqual(payload["match_count"], 2)
        self.assertEqual(
            [item["relative_path"] for item in payload["items"]],
            [
                str(Path("A") / "Arcos Biomedical" / "Tarjeta credito.cdr"),
                str(Path("A") / "Arcos Industrial" / "Otro credito.cdr"),
            ],
        )

    def test_preview_falls_back_to_embedded_thumbnail(self):
        try:
            from PIL import Image  # noqa: F401
        except Exception:
            self.skipTest("Pillow no esta instalado en el entorno de pruebas.")

        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_thumb.cdr"
        self._write_cdr_zip_with_thumbnail(cdr_path)

        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        preview_path = self.service.get_preview_path(item_id, force_refresh=True)

        self.assertTrue(preview_path.exists())
        self.assertEqual(preview_path.suffix.lower(), ".png")

    def test_preview_error_reports_failed_stage_names(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)
        self.service.config["corel_enabled"] = True

        with patch.object(
            self.service,
            "_export_cdr_preview_with_corel",
            side_effect=RuntimeError("Corel no pudo abrir el documento"),
        ), patch.object(
            self.service,
            "_extract_embedded_thumbnail",
            side_effect=RuntimeError("El archivo no tiene thumbnail"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "corel_preview: Corel no pudo abrir el documento \\| embedded_thumbnail: El archivo no tiene thumbnail",
            ):
                self.service.get_preview_path(item_id, force_refresh=True)

    def test_export_preview_reuses_corel_session_and_passes_null_optional_com_args(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        second_cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "credito_frente.cdr"
        output_path = self.preview_cache / "preview.png"
        second_output_path = self.preview_cache / "preview-2.png"

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_constants = SimpleNamespace(
            cdrPNG=1,
            cdrCurrentPage=2,
            cdrRGBColorImage=3,
            cdrNormalAntiAliasing=4,
            cdrCompressionNone=5,
        )

        fake_export_filter = MagicMock()
        fake_export_filter.Finish.side_effect = lambda: output_path.write_bytes(PNG_1X1)
        second_export_filter = MagicMock()
        second_export_filter.Finish.side_effect = lambda: second_output_path.write_bytes(PNG_1X1)
        fake_doc = MagicMock()
        fake_doc.ExportBitmap.return_value = fake_export_filter
        second_doc = MagicMock()
        second_doc.ExportBitmap.return_value = second_export_filter
        fake_app = MagicMock()
        fake_app.OpenDocument.side_effect = [fake_doc, second_doc]
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_preview_automation",
            return_value=(fake_pythoncom, fake_client, fake_constants),
        ):
            self.service._export_cdr_preview_with_corel(cdr_path, output_path)
            self.service._export_cdr_preview_with_corel(second_cdr_path, second_output_path)
            self.service.shutdown()

        fake_client.gencache.EnsureDispatch.assert_called_once_with("CorelDRAW.Application")
        fake_doc.ExportBitmap.assert_called_once_with(
            str(output_path),
            fake_constants.cdrPNG,
            fake_constants.cdrCurrentPage,
            fake_constants.cdrRGBColorImage,
            1200,
            0,
            120,
            120,
            fake_constants.cdrNormalAntiAliasing,
            False,
            False,
            True,
            False,
            fake_constants.cdrCompressionNone,
            None,
            None,
        )
        second_doc.ExportBitmap.assert_called_once_with(
            str(second_output_path),
            fake_constants.cdrPNG,
            fake_constants.cdrCurrentPage,
            fake_constants.cdrRGBColorImage,
            1200,
            0,
            120,
            120,
            fake_constants.cdrNormalAntiAliasing,
            False,
            False,
            True,
            False,
            fake_constants.cdrCompressionNone,
            None,
            None,
        )
        self.assertEqual(fake_app.OpenDocument.call_count, 2)
        fake_pythoncom.CoInitialize.assert_called_once()
        fake_pythoncom.CoUninitialize.assert_called_once()
        fake_doc.Close.assert_called_once()
        second_doc.Close.assert_called_once()
        fake_app.Quit.assert_called_once()

    def test_open_in_corel_opens_document_and_keeps_app_running(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = MagicMock()
        fake_app = MagicMock()
        fake_app.OpenDocument.return_value = fake_doc
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None) as bring_mock, patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ) as reset_preview_mock:
            payload = self.service.open_in_corel(item_id)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "open_only")
        self.assertEqual(payload["file_name"], "IAC_credito_2025.cdr")
        self.assertEqual(payload["warnings"], [])
        fake_client.gencache.EnsureDispatch.assert_called_once_with("CorelDRAW.Application")
        self.assertTrue(fake_app.Visible)
        fake_app.OpenDocument.assert_called_once_with(str(cdr_path))
        fake_doc.Close.assert_not_called()
        fake_app.Quit.assert_not_called()
        fake_pythoncom.CoInitialize.assert_called_once()
        fake_pythoncom.CoUninitialize.assert_called_once()
        bring_mock.assert_called_once_with(cdr_path)
        reset_preview_mock.assert_called_once()

    def test_open_in_corel_returns_warning_when_foreground_fails(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = MagicMock()
        fake_app = MagicMock()
        fake_app.OpenDocument.return_value = fake_doc
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))
        warning = "El archivo se abrio, pero no se pudo traer CorelDRAW al frente automaticamente."

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=warning), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ):
            payload = self.service.open_in_corel(item_id)

        self.assertEqual(payload["warnings"], [warning])

    def test_open_and_prepare_in_corel_applies_selected_profile(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())

        class LockedPrintSettings:
            __slots__ = ("PrinterName", "PaperName", "Orientation", "PrintProfileName")

            def __init__(self):
                self.PrinterName = None
                self.PaperName = None
                self.Orientation = None
                self.PrintProfileName = None

        class LockedDoc:
            __slots__ = ("Activate", "Close", "PrintSettings")

            def __init__(self):
                self.Activate = MagicMock()
                self.Close = MagicMock()
                self.PrintSettings = LockedPrintSettings()

        class LockedApp:
            __slots__ = ("Visible", "OpenDocument", "Quit")

            def __init__(self, doc):
                self.Visible = False
                self.OpenDocument = MagicMock(return_value=doc)
                self.Quit = MagicMock()

        fake_doc = LockedDoc()
        fake_app = LockedApp(fake_doc)
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ):
            payload = self.service.open_in_corel(item_id, "open_and_prepare", "tarjetas_plasticas")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "open_and_prepare")
        self.assertEqual(payload["profile_id"], "tarjetas_plasticas")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["macro_result"]["status"], "disabled")
        self.assertEqual(payload["applied_settings"]["printer_name"]["value"], "Printer PVC")
        self.assertEqual(payload["applied_settings"]["paper_name"]["value"], "PVC A4")
        self.assertEqual(payload["applied_settings"]["orientation"]["value"], "landscape")
        self.assertEqual(payload["applied_settings"]["print_profile_name"]["value"], "Perfil PVC")
        self.assertEqual(payload["applied_settings"]["notes"], "Perfil principal PVC")
        self.assertEqual(fake_doc.PrintSettings.PrinterName, "Printer PVC")
        self.assertEqual(fake_doc.PrintSettings.PaperName, "PVC A4")
        self.assertEqual(fake_doc.PrintSettings.Orientation, "landscape")
        self.assertEqual(fake_doc.PrintSettings.PrintProfileName, "Perfil PVC")
        fake_doc.Close.assert_not_called()
        fake_app.Quit.assert_not_called()

    def test_open_and_prepare_requires_profile_id(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        with self.assertRaisesRegex(ValueError, "profile_id es obligatorio"):
            self.service.open_in_corel(item_id, "open_and_prepare")

    def test_open_and_prepare_rejects_unknown_profile(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        with self.assertRaisesRegex(ValueError, "No existe el perfil de preparacion solicitado"):
            self.service.open_in_corel(item_id, "open_and_prepare", "perfil_inexistente")

    def test_open_and_prepare_returns_warnings_when_profile_fields_cannot_be_applied(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        class LockedTarget:
            __slots__ = ()

        class LockedDoc:
            __slots__ = ("Activate", "Close", "PrintSettings")

            def __init__(self):
                self.Activate = MagicMock()
                self.Close = MagicMock()
                self.PrintSettings = LockedTarget()

        class LockedApp:
            __slots__ = ("Visible", "OpenDocument", "Quit", "PrintSettings")

            def __init__(self, doc):
                self.Visible = False
                self.OpenDocument = MagicMock(return_value=doc)
                self.Quit = MagicMock()
                self.PrintSettings = LockedTarget()

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = LockedDoc()
        fake_app = LockedApp(fake_doc)
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ):
            payload = self.service.open_in_corel(item_id, "open_and_prepare", "tarjetas_laminar_tinta_a")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile_id"], "tarjetas_laminar_tinta_a")
        self.assertEqual(payload["macro_result"]["status"], "disabled")
        self.assertEqual(payload["applied_settings"], {})
        self.assertTrue(any("printer_name" in warning for warning in payload["warnings"]))
        self.assertTrue(any("paper_name" in warning for warning in payload["warnings"]))
        self.assertTrue(any("orientation" in warning for warning in payload["warnings"]))
        self.assertTrue(any("print_profile_name" in warning for warning in payload["warnings"]))

    def test_open_in_corel_rejects_non_cdr_file(self):
        txt_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "nota.txt"
        self._write_file(txt_path, "not a cdr")
        relative_path = str(txt_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        with self.assertRaisesRegex(ValueError, "no es un \\.cdr"):
            self.service.open_in_corel(item_id)

    def test_open_in_corel_rejects_path_outside_root(self):
        item_id = self.service._encode_item_id("../fuera_credito.cdr")

        with self.assertRaisesRegex(ValueError, "Ruta fuera de la carpeta raiz configurada"):
            self.service.open_in_corel(item_id)

    def test_open_in_corel_fails_with_clear_message_when_automation_is_missing(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            side_effect=RuntimeError("No se pudo cargar pywin32/Corel automation."),
        ):
            with self.assertRaisesRegex(RuntimeError, "No se pudo cargar pywin32/Corel automation"):
                self.service.open_in_corel(item_id)

    def test_open_and_prepare_uses_corel_macro_when_enabled(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)
        self.service.config["corel_macro"]["enabled"] = True

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = MagicMock()
        fake_app = MagicMock()
        fake_app.OpenDocument.return_value = fake_doc
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))
        macro_payload = {
            "used": True,
            "status": "executed",
            "module_name": "ClientAssetsPrepare",
            "entrypoint": "PrepareClientAsset",
            "profile_id": "tarjetas_plasticas",
            "target": "application.RunMacro",
            "document": str(cdr_path),
        }

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ), patch.object(
            self.service,
            "_run_corel_prepare_macro",
            return_value=macro_payload,
        ) as macro_mock, patch.object(
            self.service,
            "_apply_corel_prepare_profile",
        ) as apply_prepare_mock:
            payload = self.service.open_in_corel(item_id, "open_and_prepare", "tarjetas_plasticas")

        self.assertEqual(payload["macro_result"], macro_payload)
        self.assertEqual(payload["applied_settings"], {})
        macro_mock.assert_called_once()
        apply_prepare_mock.assert_not_called()

    def test_open_and_prepare_falls_back_to_python_prepare_when_macro_fails(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)
        self.service.config["corel_macro"]["enabled"] = True
        self.service.config["corel_macro"]["fallback_to_python_prepare"] = True

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = MagicMock()
        fake_app = MagicMock()
        fake_app.OpenDocument.return_value = fake_doc
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ), patch.object(
            self.service,
            "_run_corel_prepare_macro",
            side_effect=RuntimeError("Macro no disponible"),
        ), patch.object(
            self.service,
            "_apply_corel_prepare_profile",
            return_value=({"printer_name": {"value": "Printer PVC", "target": "document.PrintSettings.PrinterName"}}, []),
        ) as apply_prepare_mock:
            payload = self.service.open_in_corel(item_id, "open_and_prepare", "tarjetas_plasticas")

        self.assertEqual(payload["macro_result"]["status"], "failed_fallback")
        self.assertTrue(any("fallback de preparacion via COM" in warning for warning in payload["warnings"]))
        self.assertIn("printer_name", payload["applied_settings"])
        apply_prepare_mock.assert_called_once()

    def test_open_and_prepare_fails_when_macro_fails_and_fallback_is_disabled(self):
        cdr_path = self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr"
        relative_path = str(cdr_path.resolve().relative_to(self.root_folder.resolve()))
        item_id = self.service._encode_item_id(relative_path)
        self.service.config["corel_macro"]["enabled"] = True
        self.service.config["corel_macro"]["fallback_to_python_prepare"] = False

        fake_pythoncom = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
        fake_doc = MagicMock()
        fake_app = MagicMock()
        fake_app.OpenDocument.return_value = fake_doc
        fake_client = SimpleNamespace(gencache=SimpleNamespace(EnsureDispatch=MagicMock(return_value=fake_app)))

        with patch.object(
            self.service,
            "_load_corel_open_automation",
            return_value=(fake_pythoncom, fake_client),
        ), patch.object(self.service, "_bring_corel_to_front", return_value=None), patch.object(
            self.service,
            "_reset_preview_corel_session_before_interactive_open",
            return_value=None,
        ), patch.object(
            self.service,
            "_run_corel_prepare_macro",
            side_effect=RuntimeError("Macro no disponible"),
        ), patch.object(
            self.service,
            "_apply_corel_prepare_profile",
        ) as apply_prepare_mock:
            with self.assertRaisesRegex(RuntimeError, "No se pudo ejecutar la macro de CorelDRAW"):
                self.service.open_in_corel(item_id, "open_and_prepare", "tarjetas_plasticas")

        apply_prepare_mock.assert_not_called()

    def test_save_config_preserves_nested_macro_defaults_on_partial_updates(self):
        payload = self.service.save_config({"corel_macro": {"enabled": True}})

        self.assertTrue(payload["corel_macro"]["enabled"])
        self.assertEqual(payload["corel_macro"]["module_name"], "ClientAssetsPrepare")
        self.assertEqual(payload["corel_macro"]["entrypoint"], "PrepareClientAsset")
        self.assertTrue(payload["corel_macro"]["fallback_to_python_prepare"])
        self.assertTrue(payload["corel_macro"]["debug_enabled"])

    def test_build_corel_macro_project_candidates_tries_common_globalmacros_variants(self):
        candidates = self.service._build_corel_macro_project_candidates("")

        self.assertEqual(candidates, ["GlobalMacros.gms", "GlobalMacros"])

    def test_build_corel_macro_call_candidates_includes_module_macro_format_for_gmsmanager(self):
        candidates = self.service._build_corel_macro_call_candidates(
            None,
            "GlobalMacros.gms",
            "ClientAssetsPrepare",
            "PrepareClientAsset",
            "tarjetas_laminar_tinta_a",
        )

        flattened = [(target, method, tuple(str(arg) for arg in args)) for target, method, args in candidates]
        self.assertIn(
            (
                "GMSManager",
                "RunMacro",
                ("ClientAssetsPrepare.PrepareClientAsset", "tarjetas_laminar_tinta_a"),
            ),
            flattened,
        )
        self.assertIn(
            (
                "GMSManager",
                "RunMacro",
                ("GlobalMacros.gms", "ClientAssetsPrepare.PrepareClientAsset", "tarjetas_laminar_tinta_a"),
            ),
            flattened,
        )

    def test_resolve_corel_macro_entrypoint_prefers_profile_specific_wrapper(self):
        entrypoint = self.service._resolve_corel_macro_entrypoint(
            "tarjetas_laminar_tinta_a",
            {
                "entrypoint": "PrepareClientAsset",
                "profile_entrypoints": {
                    "tarjetas_laminar_tinta_a": "PrepareTarjetasLaminarTintaA",
                },
            },
        )

        self.assertEqual(entrypoint, "PrepareTarjetasLaminarTintaA")

    def test_run_corel_prepare_macro_includes_debug_attempts_on_failure(self):
        fake_missing_gms = SimpleNamespace()
        fake_app = SimpleNamespace(GMSManager=fake_missing_gms)

        with self.assertRaisesRegex(RuntimeError, "intentos="):
            self.service._run_corel_prepare_macro(
                fake_app,
                "tarjetas_plasticas",
                self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr",
                {
                    "enabled": True,
                    "project_name": "",
                    "module_name": "ClientAssetsPrepare",
                    "entrypoint": "PrepareClientAsset",
                    "fallback_to_python_prepare": True,
                    "debug_enabled": True,
                },
            )

    def test_prewarm_previews_reports_cached_and_warmed_items(self):
        item_id_1 = self.service._encode_item_id(str((self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr").resolve().relative_to(self.root_folder.resolve())))
        item_id_2 = self.service._encode_item_id(str((self.root_folder / "I" / "Instituto Antonio Carbajal" / "credito_frente.cdr").resolve().relative_to(self.root_folder.resolve())))

        def fake_get_preview_path(item_id, force_refresh=False):
            path = self.preview_cache / f"{item_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG_1X1)
            return path

        cached_preview = self.preview_cache / f"{item_id_1}.png"
        cached_preview.parent.mkdir(parents=True, exist_ok=True)
        cached_preview.write_bytes(PNG_1X1)

        with patch.object(self.service, "_build_cache_path", side_effect=[cached_preview, self.preview_cache / f"{item_id_2}.png"]), patch.object(
            self.service,
            "get_preview_path",
            side_effect=fake_get_preview_path,
        ):
            payload = self.service.prewarm_previews([item_id_1, item_id_2], limit=8, force_refresh=False)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["processed_count"], 2)
        self.assertEqual(payload["cached_count"], 1)
        self.assertEqual(payload["warmed_count"], 1)
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual([item["status"] for item in payload["items"]], ["cached", "warmed"])

    def test_prewarm_previews_reports_failures_without_aborting_batch(self):
        item_id_1 = self.service._encode_item_id(str((self.root_folder / "I" / "Instituto Antonio Carbajal" / "IAC_credito_2025.cdr").resolve().relative_to(self.root_folder.resolve())))
        item_id_2 = self.service._encode_item_id(str((self.root_folder / "I" / "Instituto Antonio Carbajal" / "credito_frente.cdr").resolve().relative_to(self.root_folder.resolve())))

        def fake_get_preview_path(item_id, force_refresh=False):
            if item_id == item_id_1:
                raise RuntimeError("fallo preview")
            path = self.preview_cache / f"{item_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG_1X1)
            return path

        with patch.object(
            self.service,
            "get_preview_path",
            side_effect=fake_get_preview_path,
        ):
            payload = self.service.prewarm_previews([item_id_1, item_id_2], limit=8, force_refresh=False)

        self.assertEqual(payload["processed_count"], 2)
        self.assertEqual(payload["failed_count"], 1)
        self.assertEqual(payload["warmed_count"], 1)
        self.assertEqual(payload["items"][0]["status"], "failed")
        self.assertEqual(payload["items"][1]["status"], "warmed")

    def _write_file(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _write_cdr_zip_with_thumbnail(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("metadata/thumbnails/thumbnail.png", PNG_1X1)


if __name__ == "__main__":
    unittest.main()
