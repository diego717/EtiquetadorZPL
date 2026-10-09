// Cache de datos del panel entre paginas.
//
// Al ir de una pagina a otra y volver, las consultas de lectura de la lista de abajo se
// responden con lo ultimo que se trajo en esta pestania del navegador, sin esperar a la API
// ni a Odoo. Se vuelve a consultar de verdad cuando:
//   - se recarga la pagina (F5 / Ctrl+F5): se borra toda la cache;
//   - se aprieta un boton que modifica datos (Actualizar, Confirmar, Guardar...): cualquier
//     POST/PUT/DELETE que no sea una lectura borra toda la cache;
//   - la misma consulta se repite dentro de la pagina (filtros, refresco automatico): solo la
//     primera de cada pagina sale de la cache, las siguientes van a la red y la renuevan;
//   - la consulta pide `refresh=true`;
//   - pasaron mas de MAX_AGE_MS.
// Las colas de impresion (Administrado, Mercado Libre) quedan afuera a proposito: mostrar una
// lista vieja podria llevar a reimprimir un envio que ya se imprimio desde otra PC.
// Se guarda en sessionStorage: es por pestania y se borra al cerrarla.
(function () {
    const PREFIX = 'panelcache:';
    const MAX_AGE_MS = 12 * 60 * 60 * 1000;
    const CACHEABLE = [
        ['GET', /^\/api\/today\/summary$/],
        ['GET', /^\/api\/receivables\/(clients|uninvoiced)(\/\d+)?$/],
        ['GET', /^\/api\/replenishment\/report$/],
        ['GET', /^\/api\/projection\/report$/],
        ['GET', /^\/api\/pos-reconciliation\/(history|journals|rounding-accounts|operators)$/],
        // Es POST pero solo lee facturas de Odoo.
        ['POST', /^\/api\/pos-reconciliation\/pending-invoices$/],
    ];
    // Lecturas que usan POST: no invalidan la cache.
    const READ_ONLY_POSTS = [
        /^\/api\/pos-reconciliation\/pending-invoices$/,
        /^\/api\/administrado\/sales\/sync$/,
        /^\/api\/mercadolibre\/sales\/sync$/,
        /^\/api\/mercadolibre\/payments\/(options|proposal)$/,
        /^\/api\/pos-reconciliation\/auto\/proposal$/,
    ];

    let storage = null;
    try {
        storage = window.sessionStorage;
        storage.setItem(`${PREFIX}probe`, '1');
        storage.removeItem(`${PREFIX}probe`);
    } catch (e) {
        storage = null;
    }
    if (!storage || !window.fetch) return;

    function keys() {
        const list = [];
        for (let i = 0; i < storage.length; i += 1) {
            const key = storage.key(i);
            if (key && key.startsWith(PREFIX)) list.push(key);
        }
        return list;
    }

    function clearAll() {
        keys().forEach(key => { try { storage.removeItem(key); } catch (e) { /* ignorar */ } });
    }

    const navigation = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
    if (navigation && navigation.type === 'reload') clearAll();

    const servedThisPage = new Set();
    const originalFetch = window.fetch.bind(window);

    function describe(input, init) {
        if (typeof input !== 'string' && !(input instanceof URL)) return null;
        let url;
        try {
            url = new URL(String(input), window.location.href);
        } catch (e) {
            return null;
        }
        if (!url.pathname.startsWith('/api/')) return null;
        const method = String((init && init.method) || 'GET').toUpperCase();
        const forceRefresh = ['true', '1'].includes(url.searchParams.get('refresh') || '');
        url.searchParams.delete('refresh');
        const body = init && typeof init.body === 'string' ? init.body : '';
        const cacheable = CACHEABLE.some(([m, re]) => m === method && re.test(url.pathname));
        const readOnly = method === 'GET' || method === 'HEAD' || READ_ONLY_POSTS.some(re => re.test(url.pathname));
        return {
            key: `${PREFIX}${method} ${url.pathname}${url.search}${body ? ` ${body}` : ''}`,
            cacheable: cacheable && !(init && init.body && !body),
            readOnly,
            forceRefresh,
        };
    }

    function store(key, entry) {
        const value = JSON.stringify(entry);
        for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
                storage.setItem(key, value);
                return;
            } catch (e) {
                // Sin lugar: se descarta lo mas viejo y se reintenta una vez.
                keys()
                    .map(k => { try { return [k, JSON.parse(storage.getItem(k)).at || 0]; } catch (err) { return [k, 0]; } })
                    .sort((a, b) => a[1] - b[1])
                    .slice(0, Math.max(1, Math.ceil(keys().length / 2)))
                    .forEach(([k]) => storage.removeItem(k));
            }
        }
    }

    window.fetch = async function (input, init) {
        const info = describe(input, init);
        if (!info) return originalFetch(input, init);

        if (!info.readOnly) {
            const response = await originalFetch(input, init);
            clearAll();
            return response;
        }
        if (!info.cacheable) return originalFetch(input, init);

        if (!info.forceRefresh && !servedThisPage.has(info.key)) {
            servedThisPage.add(info.key);
            try {
                const entry = JSON.parse(storage.getItem(info.key) || 'null');
                if (entry && Date.now() - entry.at < MAX_AGE_MS) {
                    return new Response(entry.body, { status: 200, headers: { 'Content-Type': entry.type || 'application/json' } });
                }
            } catch (e) {
                // Entrada corrupta: se consulta la red.
            }
        }
        servedThisPage.add(info.key);

        const response = await originalFetch(input, init);
        const type = response.headers.get('Content-Type') || '';
        if (response.ok && type.includes('json')) {
            response.clone().text().then(body => store(info.key, { at: Date.now(), type, body })).catch(() => {});
        }
        return response;
    };

    window.panelCache = { clear: clearAll };
})();
