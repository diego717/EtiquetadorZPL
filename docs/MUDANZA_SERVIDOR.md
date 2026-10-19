# Mudar el servidor a otra PC

El servidor (API + web en el puerto 8002) corre en **una sola PC**. Al prenderla arranca solo
y, si se cae, se vuelve a levantar.

> **Nunca dejarlo corriendo en dos PCs a la vez.** La automatizacion de Odoo procesaria los
> mismos envios dos veces y las etiquetas saldrian duplicadas.

## Mudanza (una sola vez)

1. **En esta PC (la de desarrollo):** ejecutar `deploy_pc_b.bat`. Arma `release\pc_b_test`.
2. **En la PC vieja (la que hoy corre el servidor):** ejecutar
   `servidor_mudanza_exportar_y_desactivar.bat`.
   - Quita el inicio automatico y detiene el servidor.
   - Deja `EtiquetadorZPL_config_<PC>_<fecha>.zip` en el Escritorio, con la configuracion,
     las credenciales (Odoo, Mercado Libre, Totalnet) y la base de datos.
3. Copiar la carpeta `pc_b_test` a la PC nueva (pendrive o red) y **poner el ZIP adentro**.
4. **En la PC nueva:** instalar Python 3.10 si no esta
   (`winget install --id Python.Python.3.10 -e`) y ejecutar `servidor_instalar_o_actualizar.bat`.
   - Instala en `C:\EtiquetadorZPL`, con su propio Python en `.venv`.
   - Importa la configuracion del ZIP.
   - Abre el puerto 8002 en el firewall para la red local.
   - Pide la contrasena del usuario de Windows, para que el servidor arranque al prender la PC
     aunque nadie inicie sesion. Si se deja vacia, arranca cuando ese usuario inicia sesion.
5. Borrar el ZIP: tiene credenciales.

Desde las otras PCs se entra con `http://NOMBRE-DE-LA-PC:8002/web/`
(el instalador muestra las direcciones exactas).

## Actualizar el programa

Repetir los pasos 1, 3 y 4 **sin el ZIP**. La configuracion vive en `%APPDATA%\EtiquetadorZPL`
y no se toca. Las dependencias se reinstalan solo si cambio `requirements.txt`.

## Despues de mudar, revisar

- **Impresoras:** las USB tienen que estar conectadas e instaladas en la PC nueva, con el mismo
  nombre que en la configuracion. `verificar_pc_b.bat` lo chequea.
- **Administrado:** si usa las cookies del navegador, hay que iniciar sesion en Administrado
  desde Chrome en la PC nueva. Las cookies estan cifradas por usuario de Windows y no viajan.
- **Tipografias:** si algun diseno de tarjeta usa fuentes instaladas a mano, instalarlas tambien
  en la PC nueva.
- **Modo "al prender la PC":** el servidor corre sin escritorio. Si alguna impresora (sobre todo
  las de tarjetas) no imprime en ese modo, reinstalar dejando la contrasena vacia
  (modo "al iniciar sesion").

## Scripts

| Script | Para que |
|---|---|
| `servidor_instalar_o_actualizar.bat` | Instalar o actualizar en `C:\EtiquetadorZPL` |
| `servidor_mudanza_exportar_y_desactivar.bat` | PC vieja: apagar el servidor y exportar la configuracion |
| `servidor_importar_config.bat` | Importar un ZIP de configuracion (arrastrarlo sobre el .bat) |
| `servidor_desactivar.bat` | Quitar el inicio automatico y detener el servidor |
| `servidor_estado.bat` | Ver si esta corriendo y en que direccion |

Toda la logica esta en `scripts/servidor.ps1`. Logs en `%APPDATA%\EtiquetadorZPL\logs\`:
`supervisor.log`, `api_stdout.log` y `api_stderr.log`.
