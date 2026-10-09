// Encabezado fijo para tablas dentro de .table-scroll[data-sticky-head].
//
// La caja .table-scroll necesita scroll horizontal propio, y eso impide que un
// `position: sticky` del <thead> se pegue a la pantalla. Por eso se agrega arriba
// de la caja una copia del encabezado (mismos anchos de columna) que si queda pegada
// arriba mientras la tabla esta visible, y que acompania el scroll horizontal.
// En reposo la copia queda superpuesta exacto sobre el encabezado original.
(function () {
    function enhance(scroll) {
        if (scroll.dataset.stickyHeadReady) return;
        const table = scroll.querySelector(':scope > table');
        const head = table && table.querySelector(':scope > thead');
        if (!head) return;
        scroll.dataset.stickyHeadReady = '1';

        const wrap = document.createElement('div');
        wrap.className = 'sticky-wrap';
        const bar = document.createElement('div');
        bar.className = 'head-bar';
        bar.setAttribute('aria-hidden', 'true');
        const cloneTable = document.createElement('table');
        const clone = document.createElement('thead');
        cloneTable.appendChild(clone);
        bar.appendChild(cloneTable);
        scroll.parentNode.insertBefore(wrap, scroll);
        wrap.appendChild(bar);
        wrap.appendChild(scroll);

        function sync() {
            clone.innerHTML = head.innerHTML;
            const headHeight = head.getBoundingClientRect().height;
            // Oculta (pestania cerrada): se vuelve a sincronizar cuando se muestre.
            if (!headHeight) return;
            const widths = [...head.querySelectorAll('th')].map(th => th.getBoundingClientRect().width);
            clone.querySelectorAll('th').forEach((th, i) => {
                th.style.width = th.style.minWidth = th.style.maxWidth = `${widths[i]}px`;
            });
            cloneTable.style.width = `${table.getBoundingClientRect().width}px`;
            // +1: el borde superior de la caja de la tabla.
            bar.style.marginBottom = `-${headHeight + 1}px`;
            bar.scrollLeft = scroll.scrollLeft;
        }

        scroll.addEventListener('scroll', () => { bar.scrollLeft = scroll.scrollLeft; }, { passive: true });
        // Cambios de filas (anchos de columna) y pestanias que se muestran disparan un resize.
        new ResizeObserver(sync).observe(table);
        // Paginas que reescriben el encabezado (por ejemplo al cambiar de vista).
        new MutationObserver(sync).observe(head, { childList: true, subtree: true, characterData: true });
        sync();
    }

    function init() {
        document.querySelectorAll('.table-scroll[data-sticky-head]').forEach(enhance);
    }

    window.enableStickyHeads = init;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
