# Recortador de fotos para credenciales

Programa independiente y local para preparar fotos de identificación por lote.

## Abrirlo

Hacé doble clic en `start_recortador_fotos.bat`, o ejecutá:

```powershell
python recortador_fotos.py
```

Si falta alguna librería, instalá las dependencias una vez con:

```powershell
python -m pip install -r requirements.txt
```

## Uso rápido

1. Elegí **Agregar fotos** o **Agregar carpeta**.
2. Seleccioná la relación de aspecto para la tarjeta (la predeterminada es 3:4).
3. Presioná **Detectar y encuadrar todas**.
4. Revisá las fotos de la lista. Arrastrá el marco blanco para mover el recorte y usá `+ Acercar` o `− Alejar` cuando sea necesario.
5. Si hace falta, usá los controles individuales de brillo, contraste, **Auto luz** y margen superior para cabello.
6. Dejá activada **Alinear ojos en todo el lote** para mantener los ojos a una altura común. El 40% desde arriba es el valor predeterminado.
7. Elegí la carpeta destino, el formato de salida y, si querés, un sufijo como `_credencial`.
8. Presioná **Exportar todas**.

Un punto lleno junto al archivo indica que se detectó un rostro. Un círculo vacío significa que se usó un encuadre centrado y conviene revisarlo manualmente.

Las imágenes nunca salen de la computadora: la detección y la exportación se realizan localmente.

Por defecto se mantiene el nombre original de cada foto. El sufijo es opcional y se escribe exactamente como se indique; por ejemplo, `ana.jpg` con `_credencial` pasa a ser `ana_credencial.jpg`.

## Crear un ejecutable opcional

Ejecutá `build_recortador_fotos.bat`. El programa quedará en `dist\\RecortadorFotos.exe`.
