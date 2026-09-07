"""
Construye un paquete portable para la API local de Client Assets.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = PROJECT_ROOT / "release" / "ClientAssetsAPI_Package"
PACKAGE_NAME = "EtiquetadorZPL_ClientAssets_API"


def run_checked(command: list[str], description: str) -> subprocess.CompletedProcess[str]:
    print(description)
    result = subprocess.run(command, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Fallo el comando: {' '.join(command)}")
    return result


def ensure_build_dependencies() -> None:
    run_checked([sys.executable, "-m", "pip", "install", "pyinstaller"], "Instalando/verificando PyInstaller...")


def build_executable() -> Path:
    temp_root = Path(tempfile.gettempdir()) / "EtiquetadorZPL_ClientAssets_build"
    dist_dir = temp_root / "dist"
    work_dir = temp_root / "work"

    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    run_checked(
        [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "EtiquetadorZPL_ClientAssets_API.spec",
        ],
        "Construyendo ejecutable portable de Client Assets API...",
    )

    built_exe = dist_dir / f"{PACKAGE_NAME}.exe"
    if not built_exe.exists():
        raise RuntimeError("PyInstaller finalizo pero no se encontro el ejecutable esperado.")
    return built_exe


def prepare_package_dir() -> None:
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)


def copy_package_files(executable_path: Path) -> None:
    files_to_copy = [
        (executable_path, PACKAGE_DIR / f"{PACKAGE_NAME}.exe"),
        (PROJECT_ROOT / "start_client_assets_api.bat", PACKAGE_DIR / "start_client_assets_api.bat"),
        (PROJECT_ROOT / "configure_client_assets_api.bat", PACKAGE_DIR / "configure_client_assets_api.bat"),
        (PROJECT_ROOT / "config" / "client_assets_config.example.json", PACKAGE_DIR / "client_assets_config.example.json"),
        (PROJECT_ROOT / "docs" / "CLIENT_ASSETS_LOCAL_SETUP.md", PACKAGE_DIR / "CLIENT_ASSETS_LOCAL_SETUP.md"),
        (PROJECT_ROOT / "docs" / "GOOGLE_SHEETS_IMPRESION_LOCAL_MODAL.md", PACKAGE_DIR / "GOOGLE_SHEETS_IMPRESION_LOCAL_MODAL.md"),
    ]

    for source, target in files_to_copy:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_readme() -> None:
    readme = PACKAGE_DIR / "LEEME_PRIMERO.txt"
    readme.write_text(
        "\n".join(
            [
                "Client Assets API - Inicio rapido",
                "",
                "1. Ejecutar configure_client_assets_api.bat",
                "2. Configurar la carpeta raiz de clientes",
                "3. Ejecutar start_client_assets_api.bat",
                "4. Abrir http://127.0.0.1:8002/docs#/client-assets para probar",
                "",
                "Requisitos:",
                "- Windows",
                "- CorelDRAW instalado si quieres previews de .cdr",
                "",
                "La planilla de Google Sheets debe abrirse en esta misma PC",
                "para que el modal pueda consultar localhost.",
            ]
        ),
        encoding="utf-8",
    )


def create_zip() -> Path:
    zip_base = PROJECT_ROOT / "release" / "ClientAssetsAPI_Package"
    archive_path = shutil.make_archive(str(zip_base), "zip", root_dir=PACKAGE_DIR.parent, base_dir=PACKAGE_DIR.name)
    return Path(archive_path)


def main() -> None:
    print("=== Build Client Assets API ===")
    ensure_build_dependencies()
    executable = build_executable()
    prepare_package_dir()
    copy_package_files(executable)
    write_readme()
    zip_path = create_zip()

    exe_size_mb = (PACKAGE_DIR / f"{PACKAGE_NAME}.exe").stat().st_size / (1024 * 1024)
    print()
    print("Build completado.")
    print(f"Paquete: {PACKAGE_DIR}")
    print(f"ZIP: {zip_path}")
    print(f"EXE: {PACKAGE_DIR / f'{PACKAGE_NAME}.exe'} ({exe_size_mb:.1f} MB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise
