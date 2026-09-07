"""
Script para construir instalador con PyInstaller + Inno Setup.

Incluye fallback automatico cuando falla la incrustacion de icono
por bloqueo/permiso en Windows (CopyIcons / WinError 5).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_inno_setup():
    """Verificar si Inno Setup esta instalado"""
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]

    for path in inno_paths:
        if Path(path).exists():
            return path

    return None


def create_icon_first():
    """Crear icono si no existe"""
    if not Path("etiquetador_icon.ico").exists():
        print("0. Creando icono...")
        try:
            exec(open("create_icon.py").read())
            if Path("etiquetador_icon.ico").exists():
                print("OK: Icono creado")
                # Habilitar icono en Inno Setup
                with open("EtiquetadorZPL_Simple.iss", "r", encoding="utf-8") as f:
                    content = f.read()
                content = content.replace("; SetupIconFile=etiquetador_icon.ico", "SetupIconFile=etiquetador_icon.ico")
                with open("EtiquetadorZPL_Simple.iss", "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                print("AVISO: No se pudo crear icono")
        except Exception as e:
            print(f"AVISO: No se pudo crear icono: {e}")


def _run_checked(command, description):
    """Ejecuta comando y retorna CompletedProcess."""
    print(description)
    return subprocess.run(command, capture_output=True, text=True)


def _copy_with_powershell(src_path: Path, dst_path: Path) -> bool:
    """
    Copia usando PowerShell (suele estar permitido aun cuando Python tiene
    restricciones para escribir .exe en Escritorio/Documentos).
    """
    src = str(src_path.resolve())
    dst = str(dst_path.resolve())
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Copy-Item -LiteralPath '{src}' -Destination '{dst}' -Force",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _print_tail(label, text, max_lines=80):
    """Imprime cola de logs para no inundar consola."""
    if not text:
        return
    lines = text.splitlines()
    tail = lines[-max_lines:]
    print(label)
    print("\n".join(tail))


def _cleanup_previous_build():
    """Limpia outputs previos y termina procesos tipicos que bloquean el exe."""
    # Intentar cerrar ejecutable previo si esta corriendo
    for proc_name in ("EtqRuntime.exe",):
        subprocess.run(
            ["taskkill", "/F", "/IM", proc_name],
            capture_output=True,
            text=True,
        )

    for dir_name in ("build", "dist"):
        path = Path(dir_name)
        if path.exists():
            shutil.rmtree(path, ignore_errors=False)
            print(f"Limpiado: {dir_name}/")


def _build_with_spec(spec_path: str, dist_dir: Path, work_dir: Path):
    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        spec_path,
    ]
    return _run_checked(cmd, f"Ejecutando PyInstaller con {spec_path}...")


def _looks_like_copyicons_lock(stderr_text: str) -> bool:
    text = (stderr_text or "").lower()
    return (
        "copyicons" in text
        and ("winerror 5" in text or "acceso denegado" in text or "access is denied" in text)
    )


def _build_without_embedded_icon_fallback(dist_dir: Path, work_dir: Path):
    """
    Genera un spec temporal sin icono embebido para sortear bloqueos de recursos.
    """
    original_spec = Path("EtiquetadorZPL_Complete.spec")
    if not original_spec.exists():
        return None

    content = original_spec.read_text(encoding="utf-8")
    if "icon='etiquetador_icon.ico'" in content:
        patched = content.replace("icon='etiquetador_icon.ico'", "icon=None")
    elif 'icon="etiquetador_icon.ico"' in content:
        patched = content.replace('icon="etiquetador_icon.ico"', "icon=None")
    else:
        # Si no encuentra la linea, no forzar patch.
        return None

    temp_spec = Path("EtiquetadorZPL_Complete_no_icon.spec")
    try:
        temp_spec.write_text(patched, encoding="utf-8")
        print("Reintentando build sin icono embebido (fallback)...")
        return _build_with_spec(str(temp_spec), dist_dir=dist_dir, work_dir=work_dir)
    finally:
        try:
            if temp_spec.exists():
                temp_spec.unlink()
        except Exception:
            pass


def build_executable_first():
    """Construir ejecutable con PyInstaller primero"""
    print("1. Construyendo ejecutable con PyInstaller...")

    # Verificar que existe el spec file
    if not Path("EtiquetadorZPL_Complete.spec").exists():
        print("ERROR: No se encontro EtiquetadorZPL_Complete.spec")
        return False

    # Verificar que existe el launcher
    if not Path("launcher_modern.py").exists():
        print("ERROR: No se encontro launcher_modern.py")
        return False

    try:
        print("Verificando dependencias de build...")
        pip_cmds = [
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        ]
        for cmd in pip_cmds:
            result = _run_checked(cmd, f"Ejecutando: {' '.join(cmd)}")
            if result.returncode != 0:
                _print_tail("ERROR pip stderr:", result.stderr)
                return False

        _cleanup_previous_build()

        temp_root = Path(tempfile.gettempdir()) / "EtiquetadorZPL_build"
        temp_dist = temp_root / "dist"
        temp_work = temp_root / "work"
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
        temp_dist.mkdir(parents=True, exist_ok=True)
        temp_work.mkdir(parents=True, exist_ok=True)

        primary = _build_with_spec(
            "EtiquetadorZPL_Complete.spec",
            dist_dir=temp_dist,
            work_dir=temp_work,
        )
        final_result = primary
        used_icon_fallback = False

        if primary.returncode != 0 and _looks_like_copyicons_lock(primary.stderr):
            fallback = _build_without_embedded_icon_fallback(dist_dir=temp_dist, work_dir=temp_work)
            if fallback is not None:
                final_result = fallback
                used_icon_fallback = fallback.returncode == 0

        built_exe = temp_dist / "EtqRuntime.exe"
        if final_result.returncode == 0 and built_exe.exists():
            # Copiar artefacto final a ./dist con PowerShell para evitar bloqueos de escritura de Python.
            final_dist_dir = Path("dist")
            final_dist_dir.mkdir(parents=True, exist_ok=True)
            final_exe = final_dist_dir / "EtqRuntime.exe"
            if final_exe.exists():
                try:
                    final_exe.unlink()
                except Exception:
                    pass
            copied = _copy_with_powershell(built_exe, final_exe)
            if not copied or not final_exe.exists():
                print("ERROR: No se pudo copiar el ejecutable final a dist/")
                return False

            size_mb = final_exe.stat().st_size / (1024 * 1024)
            print(f"OK: Ejecutable creado: dist/EtqRuntime.exe ({size_mb:.1f} MB)")
            if used_icon_fallback:
                print("AVISO: Se uso fallback sin icono embebido por bloqueo de recursos en Windows.")
            return True

        print("ERROR: Error creando ejecutable.")
        _print_tail("STDERR (cola):", final_result.stderr)
        if final_result is not primary:
            _print_tail("STDERR primer intento (cola):", primary.stderr)
        return False

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def build_installer():
    """Construir instalador con Inno Setup"""
    print("3. Construyendo instalador con Inno Setup...")

    # Verificar Inno Setup
    iscc_path = check_inno_setup()
    if not iscc_path:
        print("ERROR: Inno Setup no encontrado")
        print("Descarga e instala desde: https://jrsoftware.org/isinfo.php")
        return False

    print(f"OK: Inno Setup encontrado: {iscc_path}")

    # Verificar que existe el ejecutable
    if not Path("dist/EtqRuntime.exe").exists():
        print("ERROR: No se encontro dist/EtqRuntime.exe")
        return False

    # Construir instalador
    try:
        # Compilar instalador en carpeta temporal para evitar bloqueos de escritura.
        temp_out_dir = Path(tempfile.gettempdir()) / "EtiquetadorZPL_build" / "installer_out"
        temp_out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [iscc_path, f"/O{temp_out_dir}", "EtiquetadorZPL_Simple.iss"]
        result = _run_checked(cmd, "Ejecutando Inno Setup...")

        if result.returncode == 0:
            print("OK: Instalador creado exitosamente")

            temp_installer_path = temp_out_dir / "EtiquetadorZPL_Setup.exe"
            if not temp_installer_path.exists():
                print("ERROR: Inno Setup finalizo, pero no se encontro el setup temporal.")
                return False

            installer_dir = Path("installer")
            installer_dir.mkdir(parents=True, exist_ok=True)
            installer_path = installer_dir / "EtiquetadorZPL_Setup.exe"
            if installer_path.exists():
                try:
                    installer_path.unlink()
                except Exception:
                    pass

            copied = _copy_with_powershell(temp_installer_path, installer_path)
            if not copied or not installer_path.exists():
                print("ERROR: No se pudo copiar el instalador final a installer/")
                return False

            size_mb = installer_path.stat().st_size / (1024 * 1024)
            print(f"Instalador: {installer_path} ({size_mb:.1f} MB)")
            return True

            print("AVISO: Instalador creado pero no encontrado en ubicacion esperada")
            return True

        print("ERROR: Error creando instalador:")
        _print_tail("STDERR (cola):", result.stderr)
        return False

    except Exception as e:
        print(f"ERROR: Error ejecutando Inno Setup: {e}")
        return False


def create_build_info():
    """Crear informacion de build"""
    build_info = f"""
=== EtiquetadorZPL - Informacion de Build ===

Fecha: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Version: 1.0

Archivos generados:
- dist/EtqRuntime.exe (Ejecutable principal)
- installer/EtiquetadorZPL_Setup.exe (Instalador)

Caracteristicas del instalador:
- Instalacion automatica
- Creacion de accesos directos
- Configuracion de carpetas de trabajo
- Inicio automatico (opcional)
- Desinstalador incluido
- Registro en Windows

Para distribuir:
1. Enviar archivo: installer/EtiquetadorZPL_Setup.exe
2. Usuario ejecuta el instalador
3. Seguir asistente de instalacion

Tamano aproximado: 40-60 MB
Requisitos: Windows 10/11 (64-bit)
"""

    with open("BUILD_INFO.txt", "w", encoding="utf-8") as f:
        f.write(build_info)

    print("INFO: Informacion de build guardada: BUILD_INFO.txt")


def verify_before_build():
    """Verificar paths antes del build"""
    print("0. Verificando paths y archivos...")
    try:
        from verify_paths import verify_paths

        if not verify_paths():
            print("ERROR: Faltan archivos criticos")
            return False
        print("OK: Todos los archivos verificados")
        return True
    except Exception as e:
        print(f"AVISO: No se pudo ejecutar verificacion: {e}")
        return True  # Continuar si no se puede verificar


def main():
    """Funcion principal"""
    print("=== Constructor de Instalador EtiquetadorZPL ===")
    print("Usando: PyInstaller + Inno Setup")
    print()

    # Paso 0: Verificar paths
    if not verify_before_build():
        return False

    print()

    # Paso 1: Crear icono
    create_icon_first()

    # Paso 2: Construir ejecutable
    if not build_executable_first():
        print("ERROR: Fallo la construccion del ejecutable")
        return False

    print()

    # Paso 3: Construir instalador
    if not build_installer():
        print("ERROR: Fallo la construccion del instalador")
        return False

    print()

    # Paso 4: Crear informacion
    create_build_info()

    print()
    print("EXITO: Proceso completado exitosamente!")
    print()
    print("Archivos listos para distribucion:")
    print("   - installer/EtiquetadorZPL_Setup.exe")
    print()
    print("Para distribuir:")
    print("   1. Envia el archivo EtiquetadorZPL_Setup.exe")
    print("   2. El usuario lo ejecuta como administrador")
    print("   3. Sigue el asistente de instalacion")

    return True


if __name__ == "__main__":
    success = main()
    try:
        input("\nPresiona Enter para continuar...")
    except EOFError:
        # Entorno no interactivo (CI/automatizacion)
        pass

    if success:
        # Abrir carpeta de salida cuando hay shell interactivo Windows.
        try:
            os.startfile("installer")
        except Exception:
            pass




