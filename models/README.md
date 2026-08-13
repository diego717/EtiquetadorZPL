# Modelos vendorizados

## `face_detection_yunet_2023mar.onnx`

Detector de rostros YuNet, usado por `face_detection.py` para el recortador de fotos.

| | |
|---|---|
| Origen | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| Commit upstream | `f12e12798e8314f7c074a6656816c048dcc95b7a` (2023-06-06) |
| Descargado el | 2026-08-13 |
| Tamaño | 232.589 bytes |
| sha256 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| Licencia | MIT — Copyright (c) 2020 Shiqi Yu. Texto completo en `LICENSE-yunet.txt` |
| Requiere | OpenCV con `cv2.FaceDetectorYN` (>= 4.5.4) |

Se usa la variante float, **no** la `_int8`: el ahorro de ~90 KB es irrelevante frente a un
ejecutable de ~111 MB y la cuantización cuesta precisión.

El archivo se distribuye dentro del ejecutable (ver `datas` en los `.spec`). El recortador lo
lee del disco local y **nunca hace una descarga en runtime**: la aplicación sigue funcionando
completamente offline, como indica `README_RECORTADOR_FOTOS.md`.

Para verificar la integridad:

```powershell
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('models/face_detection_yunet_2023mar.onnx').read_bytes()).hexdigest())"
```
