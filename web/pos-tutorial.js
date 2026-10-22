(function () {
    'use strict';

    const topicList = [
        { id: 'totalnet', title: 'Conciliar cobros de TotalNet', description: 'Desde la sincronizacion hasta el registro del pago en Odoo.' },
        { id: 'automatic', title: 'Conciliacion automatica', description: 'Dejar propuestas listas y, opcionalmente, registrar casos inequivocos.' },
        { id: 'manual-ticket', title: 'Ticket TotalNet manual', description: 'Usar un comprobante fisico que todavia no aparece en la API.' },
        { id: 'manual-payment', title: 'Transferencia, Mercado Pago o caja', description: 'Registrar un cobro que no proviene de un ticket POS.' },
        { id: 'mercadolibre', title: 'Pagos de Mercado Libre', description: 'Buscar ventas pagadas, revisar su factura y registrarlas en Odoo.' },
        { id: 'history', title: 'Buscar pagos registrados', description: 'Consultar el historial comun y abrir los registros en Odoo.' }
    ];

    let sourceBeforeTour = 'totalnet';
    let detailsBeforeTour = [];

    function selectedSource() {
        return document.querySelector('[data-pay-source].is-active')?.dataset.paySource || 'totalnet';
    }

    function selectSource(source) {
        if (typeof window.setPaymentSource === 'function') window.setPaymentSource(source, false);
    }

    function openDetails(selector) {
        const details = document.querySelector(selector);
        if (details) details.open = true;
    }

    function rememberView() {
        sourceBeforeTour = selectedSource();
        detailsBeforeTour = [...document.querySelectorAll('#pos-reconciliation-section details')]
            .map((details) => ({ details, open: details.open }));
    }

    function restoreView() {
        selectSource(sourceBeforeTour);
        detailsBeforeTour.forEach(({ details, open }) => { details.open = open; });
    }

    const commonClose = () => restoreView();

    const tours = {
        totalnet: {
            title: 'Conciliacion TotalNet',
            steps: [
                {
                    target: '#pos-reconciliation-section > h2',
                    title: 'El circuito completo, sin registrar nada todavia',
                    text: 'La conciliacion compara cupones de TotalNet con facturas de Odoo. Sincronizar solo prepara una propuesta: el pago real se crea recien cuando confirmas al final.',
                    beforeShow: () => selectSource('totalnet')
                },
                {
                    target: '.pay-source-tabs',
                    title: 'Elegi el origen del cobro',
                    text: 'Usa TotalNet (POS) para los cupones de la terminal. La pestaña Mercado Libre tiene su propio recorrido y comparte el mismo historial.'
                },
                {
                    target: '#pos-totalnet-settings',
                    title: 'Configuracion inicial',
                    text: 'La primera vez, carga las credenciales de TotalNet y mapea cada sello de tarjeta con su diario contable de Odoo. Proba la conexion antes de conciliar.',
                    beforeShow: () => openDetails('#pos-totalnet-settings')
                },
                {
                    target: '#pos-sync-toolbar',
                    title: 'Selecciona el periodo y sincroniza',
                    text: 'Elige desde y hasta; TotalNet permite consultar como maximo hasta ayer. “Sincronizar” trae TotalNet y Odoo. “Actualizar solo Odoo” refresca las facturas aunque TotalNet no responda.'
                },
                {
                    target: '#pos-pending-invoices-table',
                    title: 'Revisa lo pendiente en Odoo',
                    text: 'Esta tabla muestra las facturas con saldo del periodo. Sirve para comprobar que la factura esperada existe antes de analizar los cruces.'
                },
                {
                    target: '#pos-matches-table',
                    title: 'Coincidencias listas',
                    text: 'Son cruces unicos. Las filas habilitadas aparecen seleccionadas; desmarca cualquier pago que no quieras registrar en esta tanda.'
                },
                {
                    target: '#pos-ambiguous-table',
                    title: 'Resolve los casos ambiguos',
                    text: 'Cuando hay mas de una factura posible, elegi la correcta en el desplegable y marca la fila. Si no estas seguro, dejala sin seleccionar.'
                },
                {
                    target: '#pos-nomatch-table',
                    title: 'Entende los casos sin coincidencia',
                    text: 'Aca quedan los cupones sin cruce directo. Si existe una factura del mismo importe podes elegirla manualmente; si no, el pago queda sin registrar para revisarlo.'
                },
                {
                    target: '#pos-confirm-options',
                    title: 'Define como se registraran',
                    text: 'Elegi el operador y el diario. Tambien podes controlar el redondeo y si se adjunta a la factura un PDF con el detalle del cupón.'
                },
                {
                    target: '#pos-confirm-actions',
                    title: 'Confirma solamente despues de revisar',
                    text: '“Confirmar seleccionados” muestra una ultima confirmacion y recien entonces crea pagos reales en Odoo. El resultado queda visible debajo y en el historial.'
                },
                {
                    target: '.pos-history-filters',
                    title: 'Comprueba el resultado',
                    text: 'El historial comun permite buscar por factura, ticket, venta u operador, filtrar por origen y abrir la factura o el pago en Odoo.'
                }
            ],
            onClose: commonClose
        },
        automatic: {
            title: 'Conciliacion automatica',
            steps: [
                {
                    target: '#pos-auto-banner',
                    title: 'Estado de la conciliacion automatica',
                    text: 'El banner informa si hay una propuesta lista. “Revisar propuesta” la carga en las tablas sin registrar pagos; “Sincronizar ahora” ejecuta una revision inmediata.',
                    beforeShow: () => selectSource('totalnet')
                },
                {
                    target: '#pos-auto-settings',
                    title: 'Programa la revision periodica',
                    text: 'Activa la sincronizacion, define cada cuantos minutos revisar y cuantos dias hacia atras incluir. Podes recibir un aviso de escritorio cuando haya novedades.',
                    beforeShow: () => openDetails('#pos-auto-settings')
                },
                {
                    target: '#pos-auto-register',
                    title: 'Registro automatico: opcion avanzada',
                    text: 'Si lo activas, solo se registran coincidencias inequivocas y con todos los controles cumplidos. Los ambiguos y las diferencias siempre esperan revision manual.'
                },
                {
                    target: '#pos-auto-operator',
                    title: 'Identifica al operador',
                    text: 'Selecciona con que usuario quedaran registrados los pagos automaticos y guarda la configuracion. La actividad reciente aparece al pie de este panel.'
                }
            ],
            onClose: commonClose
        },
        'manual-ticket': {
            title: 'Ticket TotalNet manual',
            steps: [
                {
                    target: '#pos-manual-panel',
                    title: 'Cuando usar este formulario',
                    text: 'Usalo si tenes el comprobante fisico pero el cupón todavia no aparece en la API de TotalNet. Buscar la factura no registra ningun pago.',
                    beforeShow: () => { selectSource('totalnet'); openDetails('#pos-manual-panel'); }
                },
                {
                    target: '#pos-manual-date',
                    title: 'Copia los datos del comprobante',
                    text: 'Completa fecha, numero de factura, importe, moneda, ticket, autorizacion, sello y producto. Lote, terminal y ultimos cuatro digitos son opcionales.'
                },
                {
                    target: '#pos-manual-panel .pos-manual-actions',
                    title: 'Busca primero; confirma despues',
                    text: '“Buscar factura en Odoo” prepara el cruce. Luego revisa la coincidencia, el operador y el diario en las tablas inferiores antes de confirmar el pago.'
                }
            ],
            onClose: commonClose
        },
        'manual-payment': {
            title: 'Cobro manual',
            steps: [
                {
                    target: '#pos-transfer-panel',
                    title: 'Cobros sin ticket POS',
                    text: 'Este panel sirve para transferencia, Mercado Pago o caja. Puede usarse con cualquier factura que tenga saldo, incluso facturas a credito.',
                    beforeShow: () => { selectSource('totalnet'); openDetails('#pos-transfer-panel'); }
                },
                {
                    target: '#pos-transfer-panel .pos-transfer-methods',
                    title: 'Selecciona el medio de cobro',
                    text: 'El formulario adapta la referencia, el comprobante y los diarios disponibles segun el medio que elijas.'
                },
                {
                    target: '#pos-transfer-invoice-search',
                    title: 'Busca y valida la factura',
                    text: 'Escribe el numero de factura y pulsa Buscar. El sistema muestra el cliente, la moneda y el saldo antes de habilitar el registro.'
                },
                {
                    target: '#pos-transfer-amount',
                    title: 'Completa el cobro',
                    text: 'Indica fecha, importe, diario, operador y referencia cuando corresponda. Podes adjuntar el comprobante para que quede guardado en Odoo.'
                },
                {
                    target: '#pos-transfer-submit',
                    title: 'Revisa el resumen final',
                    text: 'El boton se habilita al completar los datos obligatorios. Antes de crear el pago se muestra un resumen y se pide confirmacion.'
                }
            ],
            onClose: commonClose
        },
        mercadolibre: {
            title: 'Pagos de Mercado Libre',
            steps: [
                {
                    target: '.pay-source-tabs',
                    title: 'Cambia a Mercado Libre',
                    text: 'Esta pestaña cruza ventas pagadas de Mercado Libre contra la factura de Odoo asociada al pack.',
                    beforeShow: () => selectSource('mercadolibre')
                },
                {
                    target: '#meli-payment-toolbar',
                    title: 'Prepara la busqueda',
                    text: 'Elegi cuantas ventas traer, el operador, el diario y la cuenta de redondeo. “Buscar pagos” arma la propuesta sin registrar nada.'
                },
                {
                    target: '#meli-payments-body',
                    title: 'Revisa cada venta',
                    text: 'La tabla muestra el pago de Mercado Libre y la factura encontrada. Solo se habilitan los casos con una unica factura pendiente del importe y moneda esperados.'
                },
                {
                    target: '#meli-register-all',
                    title: 'Registra los casos listos',
                    text: 'Podes registrar de a uno desde la tabla o usar “Registrar todos los listos”. Siempre se solicita confirmacion antes de escribir en Odoo.'
                }
            ],
            onClose: commonClose
        },
        history: {
            title: 'Historial de pagos',
            steps: [
                {
                    target: '.pos-history-filters',
                    title: 'Un historial para todos los origenes',
                    text: 'Busca por factura, ticket, venta, comprador u operador. Tambien podes filtrar por periodo, fecha del pago, origen y estado.'
                },
                {
                    target: '#pos-history-body',
                    title: 'Consulta el detalle en Odoo',
                    text: 'Cada fila indica quien registro el pago y su resultado. Cuando estan disponibles, los accesos de la ultima columna abren la factura y el pago en Odoo.'
                }
            ],
            onClose: commonClose
        }
    };

    function startTopic(id) {
        const tour = tours[id];
        if (!tour) return;
        rememberView();
        window.GuidedTutorial.start(tour);
    }

    window.openPosTutorial = function () {
        if (!window.GuidedTutorial) return;
        window.GuidedTutorial.openMenu({
            title: 'Como usar Conciliacion de pagos',
            intro: 'Elegi la tarea que queres hacer. El tutorial te lleva hasta cada control y explica el proceso sin ejecutar acciones ni registrar pagos.',
            topics: topicList,
            onSelect: startTopic
        });
    };
})();
