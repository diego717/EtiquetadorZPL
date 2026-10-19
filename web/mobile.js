// Ajustes para usar la app en el celular: tablas como tarjetas, barra inferior e instalacion.

// En pantalla chica cada fila se muestra como tarjeta y cada celda necesita el nombre de su
// columna. Las tablas se redibujan con innerHTML, asi que se completa en cada cambio.
function labelTableCells(root = document) {
    root.querySelectorAll('table').forEach((table) => {
        const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
        if (!headers.length) return;
        table.querySelectorAll('tbody tr').forEach((row) => {
            let column = 0;
            Array.from(row.cells).forEach((cell) => {
                if (!cell.hasAttribute('data-label') && headers[column]) {
                    cell.setAttribute('data-label', headers[column]);
                }
                column += cell.colSpan || 1;
            });
        });
    });
}

function watchTableBodies() {
    let scheduled = false;
    const observer = new MutationObserver(() => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
            scheduled = false;
            labelTableCells();
        });
    });
    document.querySelectorAll('tbody').forEach(tbody => observer.observe(tbody, { childList: true }));
    labelTableCells();
}

function initMobileTabbar() {
    const tabbar = document.getElementById('mobile-tabbar');
    if (!tabbar) return;
    const view = new URLSearchParams(window.location.search).get('view') || '';
    tabbar.querySelectorAll('[data-mobile-view]').forEach((link) => {
        const active = link.dataset.mobileView === view;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'page');
    });
    // "Salir" solo tiene sentido si se entro con usuario (desde fuera de la oficina).
    const logout = document.getElementById('mobile-logout');
    if (logout && typeof getSessionToken === 'function') logout.hidden = !getSessionToken();
}

function logoutMobileSession() {
    if (typeof clearSessionToken === 'function') clearSessionToken();
    if (typeof redirectToLogin === 'function') redirectToLogin();
}

function registerAppServiceWorker() {
    // Solo hay service worker en HTTPS (tunel) o en localhost; por IP de la red local no.
    if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
    navigator.serviceWorker.register('sw.js').catch(() => {
        // Sin service worker la app funciona igual; solo no se ofrece instalarla.
    });
}

document.addEventListener('DOMContentLoaded', () => {
    watchTableBodies();
    initMobileTabbar();
    registerAppServiceWorker();
});
