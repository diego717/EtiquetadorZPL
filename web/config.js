// Detectar puerto de la API automáticamente
async function getApiPort() {
    // Primero intentar leer el archivo de puerto
    try {
        const response = await fetch('/api_port.txt');
        if (response.ok) {
            const port = parseInt(await response.text());
            if (port && port > 1000) {
                return port;
            }
        }
    } catch (e) {
        // Continuar con detección manual
    }
    
    // Intentar puertos comunes
    const ports = [8003, 8002, 8004, 8005, 8001, 8000];
    
    for (const port of ports) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);
            
            const response = await fetch(`http://localhost:${port}/api/status`, { 
                method: 'GET',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                console.log(`API encontrada en puerto ${port}`);
                return port;
            }
        } catch (e) {
            continue;
        }
    }
    
    console.warn('No se pudo detectar puerto de API, usando 8003');
    return 8003; // fallback
}

// Configurar API base
let API_BASE = 'http://localhost:8003';
let API_PORT_DETECTED = false;

// Función para asegurar que tenemos el puerto correcto
async function ensureApiPort() {
    if (!API_PORT_DETECTED) {
        const port = await getApiPort();
        API_BASE = `http://localhost:${port}`;
        API_PORT_DETECTED = true;
        console.log('API configurada en:', API_BASE);
    }
    return API_BASE;
}