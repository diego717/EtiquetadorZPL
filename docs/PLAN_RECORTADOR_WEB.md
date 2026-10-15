# Plan del recortador web

## Objetivo

Integrar el recortador de fotos en la plataforma local sin reescribir el motor
de detección ni enviar imágenes a servicios externos.

## Arquitectura

- La interfaz vive en `web/fotos.html`, con Canvas nativo y el tema compartido.
- FastAPI administra sesiones temporales, vistas previas, detección y exportación.
- `face_detection.py` sigue siendo la única implementación de detección facial.
- `src/photo_crop_service.py` concentra las operaciones de imagen que no dependen
  de una interfaz gráfica.
- Los originales se conservan durante ocho horas como máximo y nunca se exponen
  mediante rutas del sistema de archivos.

## Etapa 1 - MVP integrado (implementada)

- Carga de fotos individuales y carpetas.
- Lote con búsqueda y filtro de revisión.
- Detección YuNet / MediaPipe / Haar y encuadre automático.
- Recorte arrastrable, zoom, rotación, brillo y contraste.
- Proporciones y resoluciones de credencial.
- Control de calidad básico.
- Marcado manual de fotos revisadas.
- Exportación JPG, PNG o WEBP en un ZIP con registro CSV.
- Límites de archivos, nombres seguros y validación de origen.

## Etapa 2 - Paridad profesional (implementada)

- Importación de PDF y planillas Excel.
- Coincidencia de nombres y reporte de faltantes.
- Procesamiento de fondo.
- Diseñador de tarjetas, logos y QR.
- Editor modal de credenciales con plantillas, capas posicionables, propiedades,
  orientación horizontal/vertical, fondos y deshacer/rehacer.
- Catálogo de fuentes de Windows, controles tipográficos contextuales, bloqueo de
  objetos, zona segura, centrado y zoom del lienzo.
- Hoja PDF de revisión.
- Guardado y reapertura de proyectos.
- Navegación rápida del listado con `↑`/`↓`, sin alterar accidentalmente el recorte.

## Etapa 3 - Editor libre de credenciales (implementada)

- `web/card-designer.js` reemplaza al diseñador de seis objetos fijos por un modelo
  de objetos libres (texto, foto, imagen, QR, código de barras, formas) con frente
  y dorso, tamaños en milímetros y medidas tipográficas en puntos.
- `src/card_renderer.py` compone cada cara a cualquier resolución y arma los PDF
  (tamaño real o pliegos con marcas de corte y dorso espejado).
- Campos combinables `{Campo}`, visibilidad condicional y datos editables por
  credencial.
- Endpoints `cards/preview` y `cards/export`, vistas `qr.svg` y `barcode.svg`, y
  almacén de imágenes por sesión (`assets`). El proyecto pasa a la versión 3 y
  sigue abriendo proyectos de la versión 2.

## Criterio para retirar la aplicación de escritorio

La versión desktop debe mantenerse como respaldo hasta completar la etapa 2 y
comparar al menos un lote real exportado por ambas interfaces. Después de esa
validación se puede dejar una sola interfaz y conservar el motor Python común.
