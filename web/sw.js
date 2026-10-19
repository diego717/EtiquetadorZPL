// Service worker minimo para que el celular ofrezca instalar la app.
// No guarda nada en cache: envios y pagos tienen que verse siempre en vivo, y sin
// conexion con la PC la app no puede hacer nada util.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {
    // Sin respondWith: el navegador resuelve cada pedido normalmente contra el servidor.
});
