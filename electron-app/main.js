const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let apiProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: path.join(__dirname, 'assets', 'icon.png')
  });

  mainWindow.loadFile('index.html');
  
  // Abrir DevTools en desarrollo
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }
}

// Iniciar API FastAPI
function startAPI() {
  const apiPath = path.join(__dirname, 'start_api.py');
  apiProcess = spawn('python', [apiPath], {
    cwd: __dirname
  });
  
  apiProcess.stdout.on('data', (data) => {
    console.log(`API: ${data}`);
    mainWindow.webContents.send('api-log', data.toString());
  });
  
  apiProcess.stderr.on('data', (data) => {
    console.error(`API Error: ${data}`);
    mainWindow.webContents.send('api-error', data.toString());
  });
  
  console.log('Iniciando API FastAPI...');
}

// IPC handlers
ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.filePaths[0];
});

app.whenReady().then(() => {
  createWindow();
  startAPI();
  
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (apiProcess) {
    apiProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});