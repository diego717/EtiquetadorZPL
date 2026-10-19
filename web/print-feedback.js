// Avisos de impresion compartidos (Trabajos, Precargadas): pasos con ruedita mientras
// el servidor trabaja, resultado claro al terminar y un aviso flotante que se ve aunque
// el cuadro se haya cerrado antes de que termine.

function showToast(message, tone = 'ok', ms = 6000) {
    let stack = document.getElementById('toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.id = 'toast-stack';
        stack.className = 'toast-stack';
        stack.setAttribute('aria-live', 'polite');
        document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${tone}`;
    toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    toast.innerHTML = `<span class="toast-icon" aria-hidden="true">${tone === 'error' ? '!' : '✓'}</span><span>${esc(message)}</span>`;
    toast.addEventListener('click', () => toast.remove());
    stack.appendChild(toast);
    setTimeout(() => toast.remove(), ms);
}

// Traduce los errores tecnicos a algo que se pueda resolver desde el taller.
function friendlyPrintError(error) {
    const text = String((error && error.message) || error || '');
    if (/failed to fetch|networkerror|load failed/i.test(text)) {
        return 'No hay conexion con la PC del taller. Revisa el wifi y proba de nuevo.';
    }
    if (/playwright|driver|chromium|browser/i.test(text)) {
        return 'El servidor no pudo preparar el documento. Proba de nuevo; si se repite, reinicia el servidor.';
    }
    if (/no se pudo enviar a|no se pudo imprimir en/i.test(text)) {
        return `${text}. Revisa que la impresora este prendida, con papel y conectada.`;
    }
    if (/actualiza la lista/i.test(text)) {
        return `${text} (la planilla cambio desde que abriste la pantalla).`;
    }
    return text || 'Error desconocido';
}

function renderProgress(statusEl, step, seconds) {
    statusEl.className = 'print-status busy';
    statusEl.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${esc(step)}</span><span class="elapsed">${seconds} s</span>`;
}

function renderResult(statusEl, message, tone) {
    statusEl.className = `print-status ${tone}`;
    statusEl.innerHTML = `<span class="result-icon" aria-hidden="true">${tone === 'error' ? '!' : '✓'}</span><span>${esc(message)}</span>`;
}

/**
 * Ejecuta un pedido largo mostrando el avance.
 * steps: textos que se van mostrando (cada `stepMs`), siguiendo lo que hace el servidor.
 * task: funcion async que hace el pedido. success(result) devuelve el texto de exito.
 * Devuelve el resultado, o null si fallo (el error ya se mostro).
 */
async function runWithProgress({ button, busyLabel = 'Imprimiendo...', status, steps, stepMs = 2500, task, success, toastOnSuccess = true }) {
    const dialog = button.closest('dialog');
    const actionButtons = dialog
        ? [...dialog.querySelectorAll('.dialog-actions button:not([data-close])')]
        : [button];
    const originalLabel = button.textContent;
    const started = Date.now();
    let stepIndex = 0;

    actionButtons.forEach(b => { b.disabled = true; });
    button.classList.add('is-busy');
    button.textContent = busyLabel;
    renderProgress(status, steps[0], 0);
    const timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - started) / 1000);
        stepIndex = Math.min(steps.length - 1, Math.floor((Date.now() - started) / stepMs));
        renderProgress(status, steps[stepIndex], elapsed);
    }, 500);

    try {
        const result = await task();
        const message = success(result);
        renderResult(status, message, 'ok');
        if (navigator.vibrate) navigator.vibrate(60);
        // Con el cuadro abierto ya se ve el recuadro verde; el aviso flotante es para
        // cuando se cerro antes de que terminara.
        if (toastOnSuccess && (!dialog || !dialog.open)) showToast(message, 'ok');
        return result;
    } catch (error) {
        const message = friendlyPrintError(error);
        renderResult(status, message, 'error');
        // Si el cuadro ya se cerro, el aviso flotante es lo unico que se ve.
        if (!dialog || !dialog.open) showToast(message, 'error', 9000);
        return null;
    } finally {
        clearInterval(timer);
        actionButtons.forEach(b => { b.disabled = false; });
        button.classList.remove('is-busy');
        button.textContent = originalLabel;
    }
}
