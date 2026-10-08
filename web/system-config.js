// Configuracion del sistema: notificaciones, respaldos y mantenimiento.

let notificationConfig = {};
let backupConfig = {};

function updateNotificationForm() {
    const config = notificationConfig || {};
    console.log('Actualizando form notificaciones con:', config);

    document.getElementById('desktop-notifications').checked = config.desktop_enabled === true;
    document.getElementById('error-notifications').checked = config.notify_on_error === true;
    document.getElementById('success-notifications').checked = config.notify_on_success === true;
    document.getElementById('email-enabled').checked = config.email_enabled === true;

    const emailConfig = config.email_config || {};
    document.getElementById('smtp-server').value = emailConfig.smtp_server || '';
    document.getElementById('smtp-port').value = emailConfig.smtp_port || 587;
    document.getElementById('smtp-user').value = emailConfig.username || '';
    document.getElementById('to-emails').value = (emailConfig.to_emails || []).join(', ');

    const statusElement = document.getElementById('notification-status');
    if (statusElement) {
        const enabled = config.desktop_enabled === true;
        statusElement.textContent = enabled ? 'Habilitadas' : 'Deshabilitadas';
        statusElement.className = `status ${enabled ? 'enabled' : 'disabled'}`;
    }
}

function updateBackupForm() {
    const config = backupConfig || {};
    console.log('Actualizando form backup con:', config);

    document.getElementById('backup-enabled').checked = config.enabled === true;
    document.getElementById('daily-backup').checked = config.daily_backup === true;
    document.getElementById('weekly-backup').checked = config.weekly_backup === true;
    document.getElementById('keep-daily').value = config.keep_daily || 7;
    document.getElementById('keep-weekly').value = config.keep_weekly || 4;

    const statusElement = document.getElementById('backup-status');
    if (statusElement) {
        const enabled = config.enabled === true;
        statusElement.textContent = enabled ? 'Habilitado' : 'Deshabilitado';
        statusElement.className = `status ${enabled ? 'enabled' : 'disabled'}`;
    }
}

async function saveNotificationConfig() {
    const config = {
        desktop_enabled: document.getElementById('desktop-notifications').checked,
        notify_on_error: document.getElementById('error-notifications').checked,
        notify_on_success: document.getElementById('success-notifications').checked,
        email_enabled: document.getElementById('email-enabled').checked,
        email_config: {
            smtp_server: document.getElementById('smtp-server').value,
            smtp_port: parseInt(document.getElementById('smtp-port').value),
            username: document.getElementById('smtp-user').value,
            password: document.getElementById('smtp-password').value,
            to_emails: document.getElementById('to-emails').value.split(',').map(e => e.trim()).filter(e => e)
        }
    };

    try {
        const apiBase = await ensureApiPort();
        console.log('Guardando notificaciones en:', `${apiBase}/api/config/notifications`);

        const response = await fetch(`${apiBase}/api/config/notifications`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            const result = await response.json();
            alert('OK: Configuracion de notificaciones guardada');
            console.log('Guardado en:', result.path);
            notificationConfig = config;
            updateNotificationForm();
        } else {
            const error = await response.text();
            alert(`Error guardando configuracion: ${response.status}`);
            console.error('Error response:', error);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
        console.error('Connection error:', error);
    }
}

async function saveBackupConfig() {
    const config = {
        enabled: document.getElementById('backup-enabled').checked,
        daily_backup: document.getElementById('daily-backup').checked,
        weekly_backup: document.getElementById('weekly-backup').checked,
        keep_daily: parseInt(document.getElementById('keep-daily').value),
        keep_weekly: parseInt(document.getElementById('keep-weekly').value)
    };

    try {
        const apiBase = await ensureApiPort();
        console.log('Guardando backup en:', `${apiBase}/api/config/backup`);

        const response = await fetch(`${apiBase}/api/config/backup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            const result = await response.json();
            alert('OK: Configuracion de backup guardada');
            console.log('Guardado en:', result.path);
            backupConfig = config;
            updateBackupForm();
        } else {
            const error = await response.text();
            alert(`Error guardando configuracion: ${response.status}`);
            console.error('Error response:', error);
        }
    } catch (error) {
        alert(`Error de conexion: ${error.message}`);
        console.error('Connection error:', error);
    }
}

async function createManualBackup() {
    try {
        const response = await fetch(`${API_BASE}/api/backup/create`, { method: 'POST' });
        if (response.ok) {
            alert('OK: Backup manual creado');
            loadBackups();
        } else {
            alert('Error creando backup');
        }
    } catch (error) {
        alert('Error de conexion');
    }
}

async function loadBackups() {
    try {
        const backups = await fetchAPI('/api/backups');
        const backupList = document.getElementById('backup-list');

        if (backups && backups.length > 0) {
            backupList.innerHTML = backups.map(backup => `
                <div class="backup-item">
                    <div>
                        <strong>${backup.name}</strong><br>
                        <small>${backup.type} - ${new Date(backup.created_at).toLocaleString()}</small>
                    </div>
                    <div>
                        <button class="btn" onclick="restoreBackup('${backup.name}')">Restaurar</button>
                    </div>
                </div>
            `).join('');
        } else {
            backupList.innerHTML = '<p>No hay backups disponibles</p>';
        }
    } catch (error) {
        document.getElementById('backup-list').innerHTML = '<p>Error cargando backups</p>';
    }
}

async function restoreBackup(backupName) {
    if (!(await uiConfirm({
        tone: 'danger',
        title: 'Restaurar backup',
        message: `Restaurar backup "${backupName}"? Esto sobrescribira la configuracion actual.`,
        confirmText: 'Restaurar'
    }))) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/backup/restore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup_name: backupName })
        });

        if (response.ok) {
            alert('OK: Backup restaurado. Reinicia la aplicacion.');
        } else {
            alert('Error restaurando backup');
        }
    } catch (error) {
        alert('Error de conexion');
    }
}

async function testNotification() {
    try {
        const response = await fetch(`${API_BASE}/api/test-notification`, { method: 'POST' });
        if (response.ok) {
            alert('OK: Notificacion de prueba enviada');
        } else {
            alert('Error enviando notificacion');
        }
    } catch (error) {
        alert('Error de conexion');
    }
}

async function clearDatabase() {
    if (!(await uiConfirm({
        tone: 'danger',
        title: 'Limpiar base de datos',
        message: 'Limpiar toda la base de datos? Esta accion no se puede deshacer.',
        confirmText: 'Limpiar BD'
    }))) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/database/clear`, { method: 'POST' });
        if (response.ok) {
            alert('OK: Base de datos limpiada');
        } else {
            alert('Error limpiando base de datos');
        }
    } catch (error) {
        alert('Error de conexion');
    }
}
