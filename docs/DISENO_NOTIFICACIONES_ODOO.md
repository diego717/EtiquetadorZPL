# Diseño del notificador de Odoo para Google Sheets

## Objetivo

Reemplazar el comportamiento de “último mensaje gana” por una cola persistente de notificaciones pendientes. El usuario podrá cerrar el modal sin perder avisos, abrir el registro relacionado en Odoo y marcar uno o todos los avisos como vistos localmente.

## Alcance confirmado

- Reunir en un único modal todas las notificaciones pendientes.
- Admitir mensajes asociados a cualquier modelo de Odoo.
- Mostrar autor, documento y cuerpo del mensaje.
- Ofrecer un enlace al formulario del registro mediante `model` y `res_id`.
- Permitir “Marcar como vista” individualmente y “Marcar todas como vistas”.
- Mantener los pendientes cuando se cierre el modal.
- No reabrir el modal por los mismos pendientes; reabrirlo únicamente cuando llegue un mensaje nuevo.
- Conservar hasta 30 pendientes por usuario de Google.
- No modificar el estado de lectura ni ningún registro en Odoo.

## Arquitectura

El estado se guardará en `PropertiesService.getUserProperties()` mediante propiedades exclusivas del notificador:

- `ODOO_NOTIFICATION_LAST_SCANNED_ID`: último mensaje examinado correctamente.
- `ODOO_NOTIFICATION_PENDING_IDS`: lista JSON de IDs pendientes, sin duplicados.

Solo se guardarán IDs, no cuerpos completos, para evitar los límites de tamaño de las propiedades. Los detalles se leerán desde `mail.message` al preparar el modal.

Las mutaciones de la cola se protegerán con un bloqueo por usuario para evitar carreras entre el sondeo y las acciones del modal.

## Flujo de consulta

1. El mini-widget consulta cada 15 segundos.
2. El servidor lee el cursor y la cola del usuario.
3. Busca todos los mensajes con ID posterior al cursor, en orden ascendente y por lotes.
4. Agrega los IDs nuevos sin duplicarlos y conserva los 30 más recientes.
5. Avanza el cursor solamente después de una consulta correcta.
6. Devuelve `hasNew` y la colección completa de pendientes.
7. El cliente abre el modal únicamente cuando `hasNew` es verdadero.

En la primera ejecución se conserva el comportamiento actual: se inicializa el cursor con el mensaje más reciente y no se importa el historial previo.

## Modal

Cada notificación se representará como una tarjeta con:

- autor;
- nombre del documento;
- cuerpo convertido a texto seguro;
- enlace “Abrir en Odoo”, si existen `model` y `res_id` válidos;
- acción “Marcar como vista”.

El pie incluirá “Marcar todas como vistas” y “Cerrar”. Cerrar no alterará la cola. El enlace se construirá reutilizando `buildRecordUrl_(cfg, resId, model)` y se abrirá en otra pestaña.

## Seguridad y fiabilidad

- Escapar todos los valores enviados al HTML, incluidas URLs y propiedades descriptivas.
- Convertir el cuerpo HTML de Odoo a texto legible antes de mostrarlo.
- No incluir credenciales ni claves de Odoo en el HTML del cliente.
- Si Odoo falla, no avanzar el cursor.
- Si un mensaje pendiente ya no existe, retirarlo de la cola.
- Si falta `model` o `res_id`, mostrar el aviso sin enlace.
- Deshabilitar temporalmente los botones durante las operaciones y conservar la tarjeta si el marcado falla.
- Informar cuando se hayan descartado avisos antiguos por superar el máximo de 30.

## Convivencia con la notificación en celda

`checkOdooMentionsToCell()` no compartirá el cursor del modal. Podrá conservarse con una propiedad propia, evitando que uno de los dos consumidores oculte mensajes al otro.

## Verificación prevista

- Inicialización sin importar mensajes históricos.
- Llegada de varios mensajes en una misma consulta.
- Cierre del modal sin marcar avisos.
- Reapertura solo cuando llegue un aviso nuevo.
- Marcado individual y marcado total.
- Enlaces para distintos modelos.
- Mensajes sin registro relacionado.
- Duplicados, mensajes eliminados y límite de 30.
- Fallo temporal de Odoo sin pérdida del cursor.
- Acciones simultáneas protegidas por bloqueo.

## Registro de decisiones

1. **Persistencia por IDs en `UserProperties`.** Se eligió sobre guardar mensajes completos o usar una hoja oculta porque es compacta, privada por usuario y suficiente para 30 avisos.
2. **Lectura local únicamente.** Marcar como vista modifica la cola del notificador, no Odoo.
3. **Enlaces genéricos.** Se usarán `model`, `res_id` y el helper existente `buildRecordUrl_()` para admitir cualquier tipo de documento.
4. **Modal no invasivo.** Cerrar conserva los pendientes, pero estos no provocan reaperturas repetidas; solo un mensaje nuevo vuelve a abrirlo.
5. **Límite de 30.** Se conservarán los mensajes más recientes y se avisará si hubo descartes.
6. **Cursores separados.** El modal y la celda no compartirán `ODOO_LAST_MSG_ID`.
7. **Contenido no confiable.** Todo valor procedente de Odoo se tratará como dato y se escapará antes de mostrarlo.

## Riesgos aceptados

- Un registro puede no abrir si fue eliminado o el usuario no posee permisos; Odoo gestionará ese caso.
- Si se acumulan más de 30 pendientes, se descartarán los más antiguos y se mostrará una advertencia.
- El estado es propio del usuario de Google, por lo que dos usuarios de la misma planilla tendrán colas independientes.
