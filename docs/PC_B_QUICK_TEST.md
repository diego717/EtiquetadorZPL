# PC B Quick Test (sin IDE)

Objetivo: probar todo en la PC que tiene la impresora USB, sin usar IDE.

## Opcion A (desde esta PC A)

1. Ejecutar `build_pc_b_test_package.bat`.
2. Copiar `release\pc_b_test` a la PC B.

## Opcion B (manual)

Copiar a PC B:

- carpetas: `api`, `src`, `web`, `config`, `poppler`
- archivos:
  - `requirements.txt`
  - `start_api_simple.py`
  - `start_api_server.bat`
  - `restart_api_server.bat`
  - `install_runtime_pc_b.bat`
  - `start_public_web_quick.bat`

## En PC B (primera vez)

1. Ejecutar `install_runtime_pc_b.bat`.
2. Verificar:
   - `http://localhost:8002/web/config.html#administrado`
   - `http://localhost:8002/web/cloud.html`
3. (Opcional) Ejecutar `enable_autostart_pc_b.bat` como Administrador para iniciar API al logon.

## Publicar para acceso remoto (prueba rapida)

1. Ejecutar `start_public_web_quick.bat`.
2. Copiar URL `https://*.trycloudflare.com`.
3. Abrir:
   - `/web/cloud.html`
   - `/web/config.html#administrado`

## Notas

- Esto es para prueba rapida.
- Para produccion, usar instalador completo (Setup.exe) y tunnel fijo con dominio.
