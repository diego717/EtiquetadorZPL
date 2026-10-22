(function () {
    'use strict';

    const topics = [
        { id: 'daily', title: 'Flujo diario de envios', description: 'Sincronizar, revisar stock y elegir que imprimir.' },
        { id: 'print', title: 'Imprimir un envio', description: 'Orden + etiqueta, reimpresiones y opciones parciales.' },
        { id: 'filters', title: 'Usar filtros y estados', description: 'Separar pendientes, impresos y todos los envios.' },
        { id: 'delivery', title: 'Validar entrega en Odoo', description: 'Cuando corresponde confirmar la salida de mercaderia.' },
        { id: 'setup', title: 'Configurar Administrado', description: 'Sesion, URL de ventas, copias y diagnostico.' }
    ];

    let advancedBeforeTour = false;

    function openAdvanced() {
        const details = document.getElementById('adm-advanced-panel');
        if (details) details.open = true;
    }

    function firstSaleActions() {
        return document.querySelector('#adm-sales-body .action-stack')
            || document.querySelector('#adm-sales-table');
    }

    function firstSalePrintButton() {
        return document.querySelector('#adm-sales-body .action-stack .btn.success')
            || firstSaleActions();
    }

    function rememberView() {
        advancedBeforeTour = document.getElementById('adm-advanced-panel')?.open === true;
    }

    function restoreView() {
        const details = document.getElementById('adm-advanced-panel');
        if (details) details.open = advancedBeforeTour;
    }

    const tours = {
        daily: {
            title: 'Flujo diario de envios',
            steps: [
                {
                    target: '#administrado-section > .card-head',
                    title: 'Que resuelve esta pantalla',
                    text: 'Administrado trae los envios con etiqueta detectada, consulta el estado de stock en Odoo y permite imprimir la orden y la etiqueta desde un mismo lugar.'
                },
                {
                    target: '#adm-sync-toolbar',
                    title: 'Sincroniza los envios',
                    text: 'Pulsa “Sincronizar desde Administrado” para actualizar la lista. El limite indica cuantos envios recientes traer. Auto-actualizar repite la consulta en segundo plano.'
                },
                {
                    target: '#adm-filter-tabs',
                    title: 'Filtra lo que queres revisar',
                    text: 'Pendientes muestra lo que aun no se imprimio desde la app; Impresos muestra lo ya procesado; Todos combina ambos grupos.'
                },
                {
                    target: '#adm-sales-table',
                    title: 'Lee el estado antes de imprimir',
                    text: 'La tabla muestra envio, cliente y stock/entrega. Si falta mercaderia o la orden esta en un estado inesperado, el detalle lo explica antes de enviar la impresion.'
                },
                {
                    target: '#adm-tools',
                    title: 'Herramientas rapidas',
                    text: 'Desde aca podes probar la impresion de una etiqueta con un ID concreto. La impresion normal se hace desde la accion de cada fila.'
                }
            ],
            onClose: restoreView
        },
        print: {
            title: 'Imprimir un envio',
            steps: [
                {
                    target: '#adm-sales-table',
                    title: 'Busca la fila del envio',
                    text: 'Primero sincroniza y localiza el envio. La accion principal imprime orden + etiqueta; el texto cambia a Reimprimir cuando ya fue procesado.'
                },
                {
                    target: firstSaleActions,
                    title: 'Las acciones dependen del estado',
                    text: 'En cada envio real podes elegir orden + etiqueta. Si ya fue procesado, aparecen tambien Solo orden Odoo y Solo etiqueta. Validar entrega aparece cuando Odoo permite avanzar el despacho.'
                },
                {
                    target: firstSalePrintButton,
                    title: 'La impresion siempre pide confirmacion',
                    text: 'Al pulsar una accion, la app muestra impresoras, usuario Odoo, estado de stock y advertencias. Solo despues de confirmar envia el trabajo a las impresoras.'
                },
                {
                    target: '#adm-sales-body',
                    title: 'Comprueba el resultado',
                    text: 'El estado de cada fila indica si se imprimio, que impresora uso y si Odoo cambio de estado. Abre Detalle para ver esa informacion.'
                }
            ],
            onClose: restoreView
        },
        filters: {
            title: 'Filtros y estados',
            steps: [
                {
                    target: '#adm-filter-tabs',
                    title: 'Tres vistas para ordenar el trabajo',
                    text: 'Pendientes es la bandeja de trabajo, Impresos sirve para consultar reimpresiones y Todos permite buscar sin ocultar ningun envio.'
                },
                {
                    target: '#adm-count-pending',
                    title: 'Los contadores se actualizan solos',
                    text: 'Cada contador refleja la ultima sincronizacion. Un numero resaltado indica que hay elementos en esa vista.'
                },
                {
                    target: '#adm-sync-summary',
                    title: 'Resumen de la sincronizacion',
                    text: 'Este indicador muestra cuantos envios se detectaron y deja visible si la consulta no devolvio datos o encontro un problema.'
                }
            ],
            onClose: restoreView
        },
        delivery: {
            title: 'Validar entrega en Odoo',
            steps: [
                {
                    target: '#adm-sales-table',
                    title: 'Valida solo cuando corresponda',
                    text: 'La accion Validar entrega aparece en las filas cuyo estado de Odoo permite avanzar el despacho. Si no aparece, primero revisa stock y estado de la orden.'
                },
                {
                    target: firstSaleActions,
                    title: 'Que hace esta accion',
                    text: 'Confirma la cotizacion si hace falta, reserva mercaderia y valida los movimientos PICK, PACK y OUT en orden. La confirmacion advierte que la salida de stock no se deshace desde aca.'
                },
                {
                    target: '#adm-sales-body',
                    title: 'Revisa el resultado',
                    text: 'Despues de validar, la tabla se sincroniza de nuevo y el estado de stock queda actualizado. Si falta stock en un paso, el aviso indica hasta donde llego.'
                }
            ],
            onClose: restoreView
        },
        setup: {
            title: 'Configurar Administrado',
            steps: [
                {
                    target: '#adm-advanced-panel',
                    title: 'Abri la configuracion avanzada',
                    text: 'Este panel se usa para configurar la sesion de Administrado y diagnosticar problemas. Los cambios no se aplican hasta pulsar Guardar Administrado.',
                    beforeShow: openAdvanced
                },
                {
                    target: '#adm-sales-url',
                    title: 'URL y formato de impresion',
                    text: 'Revisa la URL de ventas, las copias por defecto y el DPI usado al convertir PDFs. Recortar PDF suele ayudar cuando el documento trae margenes innecesarios.'
                },
                {
                    target: '#adm-cookie-header',
                    title: 'Sesion de Administrado',
                    text: 'Pega el header Cookie completo del navegador o usa una de las opciones para importar/capturar la sesion. Tratala como una credencial: no la compartas ni la publiques.'
                },
                {
                    target: '#adm-advanced-panel .btn-row',
                    title: 'Guarda y prueba',
                    text: 'Guarda la configuracion y luego usa Probar sesion. El diagnostico de la derecha muestra la sesion detectada, las rutas usadas y el ultimo error.'
                },
                {
                    target: '#adm-advanced-panel .status-block',
                    title: 'Diagnostico tecnico',
                    text: 'Si algo falla, copia el ultimo error y revisa si la sesion Playwright sigue vigente antes de volver a sincronizar.'
                }
            ],
            onClose: restoreView
        }
    };

    function startTopic(id) {
        const tour = tours[id];
        if (!tour) return;
        rememberView();
        window.GuidedTutorial.start(tour);
    }

    window.openAdministradoTutorial = function () {
        if (!window.GuidedTutorial) return;
        window.GuidedTutorial.openMenu({
            title: 'Como usar Envios Administrado',
            intro: 'Elegi una tarea y segui el recorrido. El tutorial solo explica la pantalla: no sincroniza, no imprime y no cambia la configuracion.',
            topics,
            onSelect: startTopic
        });
    };

    window.openAppTutorial = function () {
        if (document.body.classList.contains('pos-only-view')) {
            window.openPosTutorial?.();
        } else if (document.body.classList.contains('admin-only')) {
            window.openAdministradoTutorial();
        }
    };
})();
