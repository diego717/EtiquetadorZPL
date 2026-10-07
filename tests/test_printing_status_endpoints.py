import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import printing_status_endpoints as endpoints


def _fake_win32print(printers):
    module = types.SimpleNamespace()

    def open_printer(name):
        if name not in printers:
            raise Exception("(1801, 'OpenPrinter', 'El nombre de la impresora no es valido.')")
        return name

    module.OpenPrinter = open_printer
    module.GetPrinter = lambda handle, level: printers[handle]
    module.ClosePrinter = lambda handle: None
    return module


class _FakeDb:
    def __init__(self, jobs):
        self.jobs = jobs
        self.updated = []

    def get_recent_jobs(self, limit, status=None):
        return [job for job in self.jobs if job["status"] == status]

    def update_job_status(self, job_id, status, message=None):
        self.updated.append((job_id, status))
        return True


class TestPrintingStatus(unittest.TestCase):
    def test_host_is_read_from_standard_tcp_ports(self):
        self.assertEqual(endpoints._host_from_port("192.168.54.223_3"), "192.168.54.223")
        self.assertEqual(endpoints._host_from_port("IP_10.0.0.5"), "10.0.0.5")
        self.assertEqual(endpoints._host_from_port("USB001"), "")
        self.assertEqual(endpoints._host_from_port("EP9CE7BA:WF-C5790 SERIES"), "")

    def test_windows_flags_become_readable_problems(self):
        fake = _fake_win32print({
            "Godex": {"Status": 0x10 | 0x1, "Attributes": 0, "cJobs": 2, "pPortName": "192.168.1.9"},
            "Epson": {"Status": 0, "Attributes": 0x400, "cJobs": 0, "pPortName": "USB001"},
        })
        with patch.dict(sys.modules, {"win32print": fake}):
            godex = endpoints._printer_status("Godex")
            epson = endpoints._printer_status("Epson")
            missing = endpoints._printer_status("Otra")
        self.assertEqual(godex["problems"], ["Sin papel", "En pausa"])
        self.assertEqual(godex["jobs"], 2)
        self.assertEqual(godex["host"], "192.168.1.9")
        self.assertEqual(epson["problems"], ["Desconectada"])
        self.assertFalse(missing["installed"])
        self.assertEqual(missing["error"], "No esta instalada en esta PC")

    def test_unreachable_network_printer_is_an_error_even_if_windows_says_ready(self):
        fake = _fake_win32print({"Godex": {"Status": 0, "Attributes": 0, "cJobs": 0, "pPortName": "192.168.1.9"}})
        with patch.dict(sys.modules, {"win32print": fake}), patch.object(
            endpoints, "_configured_printers", lambda: [{"name": "Godex", "roles": ["Etiqueta"]}]
        ), patch.object(endpoints, "_network_reachable", lambda host: False):
            result = asyncio.run(endpoints.key_printers())
        self.assertEqual(result["items"][0]["state"], "error")
        self.assertFalse(result["items"][0]["network_reachable"])

    def test_only_old_unfinished_jobs_are_stale_using_utc_timestamps(self):
        now = datetime.now(timezone.utc)
        fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")
        db = _FakeDb([
            {"id": 1, "status": "processing", "created_at": fmt(now - timedelta(hours=5)), "filename": "a", "printer": "p"},
            {"id": 2, "status": "processing", "created_at": fmt(now - timedelta(minutes=5)), "filename": "b", "printer": "p"},
            {"id": 3, "status": "pending", "created_at": fmt(now - timedelta(days=40)), "filename": "c", "printer": "p"},
        ])
        with patch.dict(sys.modules, {"database": types.SimpleNamespace(db=db)}):
            stale = asyncio.run(endpoints.stale_jobs())
            closed = asyncio.run(endpoints.close_stale_jobs())
        self.assertEqual([job["id"] for job in stale["items"]], [1, 3])
        self.assertEqual(closed["closed"], 2)
        self.assertEqual(db.updated, [(1, "failed"), (3, "failed")])


if __name__ == "__main__":
    unittest.main()
