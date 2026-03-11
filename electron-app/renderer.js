const { ipcRenderer } = require('electron');
const axios = require('axios');

const API_BASE = 'http://localhost:8002';
let currentTab = 0;
let monitoring = false;
let folders = [
    { active: false, path: '', printer: '', history: '', copies: 1, cropPdf: true },
    { active: false, path: '', printer: '', history: '', copies: 1, cropPdf: true },
    { active: false, path: '', printer: '', history: '', copies: 1, cropPdf: true }
];

// Inicializar la aplicación
document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    setupEventListeners();
    
    // Verificar API y cargar datos
    checkAPIAndLoad();
});

// Verificar si la API está corriendo
async function checkAPIAndLoad() {
    let attempts = 0;
    const maxAttempts = 10;
    
    while (attempts < maxAttempts) {
        try {
            logMessage(`Verificando API... intento ${attempts + 1}`);
            const response = await axios.get(`${API_BASE}/api/status`);
            if (response.data.status === 'running') {
                logMessage('✅ API conectada');
                loadConfig();
                loadPrinters();
                return;
            }
        } catch (error) {
            attempts++;
            if (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
        }
    }
    
    logMessage('❌ No se pudo conectar con la API');
}

function initializeUI() {
    const container = document.getElementById('folder-configs');
    
    folders.forEach((folder, index) => {
        const folderDiv = document.createElement('div');
        folderDiv.className = `folder-config ${index === 0 ? 'active' : ''}`;
        folderDiv.id = `folder-${index}`;
        
        folderDiv.innerHTML = `
            <div class="form-group inline">
                <input type="checkbox" id="active-${index}" ${folder.active ? 'checked' : ''}>
                <label for="active-${index}">Activa</label>
                
                <input type="checkbox" id="crop-${index}" ${folder.cropPdf ? 'checked' : ''}>
                <label for="crop-${index}">Recortar PDF automáticamente</label>
            </div>
            
            <div class="form-group">
                <label>Carpeta de monitoreo:</label>
                <div style="display: flex; gap: 10px;">
                    <input type="text" id="path-${index}" value="${folder.path}" readonly>
                    <button class="btn btn-info" onclick="selectFolder(${index})">Buscar</button>
                </div>
            </div>
            
            <div class="form-group">
                <label>Impresora:</label>
                <select id="printer-${index}">
                    <option value="">Seleccionar impresora...</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Carpeta de historial:</label>
                <div style="display: flex; gap: 10px;">
                    <input type="text" id="history-${index}" value="${folder.history}" readonly>
                    <button class="btn btn-info" onclick="selectHistoryFolder(${index})">Buscar</button>
                </div>
            </div>
            
            <div class="form-group">
                <label>Cantidad de copias (1-10):</label>
                <input type="number" id="copies-${index}" value="${folder.copies}" min="1" max="10">
            </div>
        `;
        
        container.appendChild(folderDiv);
    });
}

function setupEventListeners() {
    document.getElementById('start-btn').addEventListener('click', startMonitoring);
    document.getElementById('stop-btn').addEventListener('click', stopMonitoring);
    document.getElementById('save-btn').addEventListener('click', saveConfig);
    document.getElementById('reload-btn').addEventListener('click', loadConfig);
    document.getElementById('clear-log-btn').addEventListener('click', clearLog);
    
    // Event listeners para cambios en los formularios
    folders.forEach((_, index) => {
        document.getElementById(`active-${index}`).addEventListener('change', (e) => {
            folders[index].active = e.target.checked;
        });
        
        document.getElementById(`crop-${index}`).addEventListener('change', (e) => {
            folders[index].cropPdf = e.target.checked;
        });
        
        document.getElementById(`printer-${index}`).addEventListener('change', (e) => {
            folders[index].printer = e.target.value;
        });
        
        document.getElementById(`copies-${index}`).addEventListener('change', (e) => {
            folders[index].copies = parseInt(e.target.value) || 1;
        });
    });
}

function showTab(index) {
    // Actualizar botones de tab
    document.querySelectorAll('.tab-button').forEach((btn, i) => {
        btn.classList.toggle('active', i === index);
    });
    
    // Mostrar configuración correspondiente
    document.querySelectorAll('.folder-config').forEach((config, i) => {
        config.classList.toggle('active', i === index);
    });
    
    currentTab = index;
}

async function selectFolder(index) {
    try {
        const folderPath = await ipcRenderer.invoke('select-folder');
        if (folderPath) {
            folders[index].path = folderPath;
            document.getElementById(`path-${index}`).value = folderPath;
            
            // Sugerir carpeta de historial
            if (!folders[index].history) {
                const historyPath = folderPath + '/historial';
                folders[index].history = historyPath;
                document.getElementById(`history-${index}`).value = historyPath;
            }
            
            logMessage(`Carpeta ${index + 1} seleccionada: ${folderPath}`);
        }
    } catch (error) {
        logMessage(`Error seleccionando carpeta: ${error.message}`);
    }
}

async function selectHistoryFolder(index) {
    try {
        const folderPath = await ipcRenderer.invoke('select-folder');
        if (folderPath) {
            folders[index].history = folderPath;
            document.getElementById(`history-${index}`).value = folderPath;
            logMessage(`Carpeta de historial ${index + 1}: ${folderPath}`);
        }
    } catch (error) {
        logMessage(`Error seleccionando carpeta de historial: ${error.message}`);
    }
}

async function loadPrinters() {
    try {
        logMessage('Cargando impresoras...');
        const response = await axios.get(`${API_BASE}/api/printers`);
        const printers = response.data.printers || [];
        
        logMessage(`Impresoras recibidas: ${JSON.stringify(printers)}`);
        
        folders.forEach((_, index) => {
            const select = document.getElementById(`printer-${index}`);
            select.innerHTML = '<option value="">Seleccionar impresora...</option>';
            
            printers.forEach(printer => {
                const option = document.createElement('option');
                option.value = printer;
                option.textContent = printer;
                if (folders[index].printer === printer) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        });
        
        logMessage(`✅ ${printers.length} impresoras encontradas`);
    } catch (error) {
        logMessage(`❌ Error cargando impresoras: ${error.message}`);
        console.error('Error completo:', error);
    }
}

async function startMonitoring() {
    if (monitoring) return;
    
    try {
        // Obtener carpetas activas desde la UI
        const activeFolders = [];
        for (let i = 0; i < 3; i++) {
            const isActive = document.getElementById(`active-${i}`).checked;
            if (isActive) {
                activeFolders.push({
                    path: document.getElementById(`path-${i}`).value,
                    printer: document.getElementById(`printer-${i}`).value,
                    history: document.getElementById(`history-${i}`).value,
                    copies: parseInt(document.getElementById(`copies-${i}`).value) || 1,
                    cropPdf: document.getElementById(`crop-${i}`).checked
                });
            }
        }
        
        if (activeFolders.length === 0) {
            alert('Debe activar al menos una carpeta para monitorear');
            return;
        }
        
        logMessage(`Carpetas activas encontradas: ${activeFolders.length}`);
        
        // Validar cada carpeta activa
        for (let i = 0; i < folders.length; i++) {
            if (!folders[i].active) continue;
            
            if (!folders[i].path) {
                alert(`Carpeta ${i + 1}: Debe seleccionar una carpeta de monitoreo`);
                return;
            }
            
            if (!folders[i].printer) {
                alert(`Carpeta ${i + 1}: Debe seleccionar una impresora`);
                return;
            }
            
            if (!folders[i].history) {
                alert(`Carpeta ${i + 1}: Debe seleccionar una carpeta de historial`);
                return;
            }
        }
        
        // Preparar datos para monitoreo
        const monitoringData = { folders: activeFolders };
        
        logMessage(`Enviando datos de monitoreo: ${JSON.stringify(monitoringData)}`);
        
        // Iniciar monitoreo
        const response = await axios.post(`${API_BASE}/api/electron/start-monitoring`, monitoringData);
        
        if (response.data.success) {
            monitoring = true;
            updateUI();
            logMessage(`▶️ Monitoreo iniciado para ${activeFolders.length} carpeta(s)`);
        }
        
    } catch (error) {
        logMessage(`❌ Error iniciando monitoreo: ${error.message}`);
    }
}

async function stopMonitoring() {
    try {
        await axios.post(`${API_BASE}/api/electron/stop-monitoring`);
        monitoring = false;
        updateUI();
        logMessage('⏹️ Monitoreo detenido');
    } catch (error) {
        logMessage(`❌ Error deteniendo monitoreo: ${error.message}`);
    }
}

async function saveConfig() {
    try {
        const config = {
            folders: folders.map((folder, i) => ({
                active: folder.active,
                path: folder.path,
                printer: folder.printer,
                history: folder.history,
                copies: folder.copies,
                cropPdf: folder.cropPdf
            }))
        };
        
        const response = await axios.post(`${API_BASE}/api/electron/save-config`, config);
        
        if (response.data.success) {
            logMessage('💾 Configuración guardada');
            alert('Configuración guardada correctamente');
        }
    } catch (error) {
        logMessage(`❌ Error guardando configuración: ${error.message}`);
        alert(`Error guardando configuración: ${error.message}`);
    }
}

async function loadConfig() {
    try {
        logMessage('Cargando configuración...');
        const response = await axios.get(`${API_BASE}/api/electron/config`);
        const config = response.data;
        
        logMessage(`Configuración recibida: ${JSON.stringify(config)}`);
        
        if (config.folders) {
            config.folders.forEach((folder, i) => {
                if (i < folders.length) {
                    folders[i] = { ...folders[i], ...folder };
                    
                    // Actualizar UI
                    document.getElementById(`active-${i}`).checked = folder.active || false;
                    document.getElementById(`path-${i}`).value = folder.path || '';
                    document.getElementById(`history-${i}`).value = folder.history || '';
                    document.getElementById(`copies-${i}`).value = folder.copies || 1;
                    document.getElementById(`crop-${i}`).checked = folder.cropPdf !== false;
                    
                    logMessage(`Carpeta ${i+1} configurada: ${folder.path}`);
                }
            });
        }
        
        logMessage('🔄 Configuración cargada');
    } catch (error) {
        logMessage(`❌ Error cargando configuración: ${error.message}`);
        console.error('Error completo:', error);
    }
}

function updateUI() {
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const status = document.getElementById('status');
    
    if (monitoring) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        status.textContent = '▶️ Monitoreando';
        status.style.background = '#d4edda';
        status.style.color = '#155724';
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        status.textContent = '⏸️ Detenido';
        status.style.background = '#f8d7da';
        status.style.color = '#721c24';
    }
}

function logMessage(message) {
    const log = document.getElementById('log');
    const timestamp = new Date().toLocaleTimeString();
    log.textContent += `[${timestamp}] ${message}\n`;
    log.scrollTop = log.scrollHeight;
}

function clearLog() {
    document.getElementById('log').textContent = '';
}