// Panel de tareas de despacho: filtros, detalle y reintentos.

let dispatchTasks = [];
let dispatchTasksRaw = [];
let dispatchStats = null;
let dispatchRefreshInProgress = false;
let dispatchBulkRetryInProgress = false;
const dispatchExpandedTaskIds = new Set();

function decodeDispatchToken(token) {
    try {
        return decodeURIComponent(String(token || ''));
    } catch (error) {
        return String(token || '');
    }
}

function toPrettyJson(value) {
    if (value === null || value === undefined) {
        return '-';
    }
    if (typeof value === 'string') {
        return value;
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch (error) {
        return String(value);
    }
}

function buildDispatchDetailText(task) {
    const lines = [
        `Task ID: ${task?.id || '-'}`,
        `Idempotency: ${task?.idempotency_key || '-'}`,
        `Estado: ${dispatchStatusLabel(task?.status)}`,
        `Origen: ${task?.source || '-'}`,
        `Entidad: ${task?.entity_id || '-'}`,
        `Accion: ${task?.action || '-'}`,
        `Intentos: ${Number(task?.attempt_count || 0)}/${Number(task?.max_attempts || 0)}`,
        `Creada: ${formatTime(task?.created_at || '')}`,
        `Actualizada: ${formatTime(task?.updated_at || '')}`,
        `Ultimo intento: ${formatTime(task?.last_attempt_at || '')}`,
        `Proximo retry: ${formatTime(task?.next_retry_at || '')}`,
        `Completada: ${formatTime(task?.completed_at || '')}`,
        '',
        'Last Error:',
        toPrettyJson(task?.last_error),
        '',
        'Request Payload:',
        toPrettyJson(task?.request_payload),
        '',
        'Result Payload:',
        toPrettyJson(task?.result_payload)
    ];
    return lines.join('\n');
}

function dispatchStatusLabel(status) {
    const normalized = String(status || '').trim().toLowerCase();
    if (normalized === 'pending') return 'Pendiente';
    if (normalized === 'processing') return 'En proceso';
    if (normalized === 'completed') return 'Completada';
    if (normalized === 'failed') return 'Fallida';
    return normalized || 'Desconocido';
}

function dispatchStatusClass(status) {
    const normalized = String(status || '').trim().toLowerCase();
    if (normalized === 'completed') return 'completed';
    if (normalized === 'failed') return 'failed';
    if (normalized === 'processing') return 'processing';
    if (normalized === 'pending') return 'pending';
    return '';
}

function renderDispatchStats() {
    const container = document.getElementById('dispatch-stats');
    if (!container) return;
    const counts = (dispatchStats && dispatchStats.counts) || {};
    const total = Number((dispatchStats && dispatchStats.total) || 0);
    const pending = Number(counts.pending || 0);
    const processing = Number(counts.processing || 0);
    const completed = Number(counts.completed || 0);
    const failed = Number(counts.failed || 0);

    if (total <= 0) {
        container.innerHTML = '<span class="status">Sin tareas registradas</span>';
        return;
    }

    container.innerHTML = `
        <span class="status">Total: ${total}</span>
        <span class="status pending">Pendientes: ${pending}</span>
        <span class="status processing">En proceso: ${processing}</span>
        <span class="status completed">Completadas: ${completed}</span>
        <span class="status failed">Fallidas: ${failed}</span>
    `;
}

function isDispatchAutoRefreshEnabled() {
    const checkbox = document.getElementById('dispatch-auto-refresh');
    return !checkbox || checkbox.checked === true;
}

function applyDispatchClientFilter(tasks) {
    const query = (document.getElementById('dispatch-query')?.value || '').trim().toLowerCase();
    if (!query) {
        return Array.isArray(tasks) ? tasks.slice() : [];
    }
    const base = Array.isArray(tasks) ? tasks : [];
    return base.filter((task) => {
        const haystack = [
            task && task.id,
            task && task.entity_id,
            task && task.action,
            task && task.source
        ]
            .map((v) => String(v || '').toLowerCase())
            .join(' ');
        return haystack.includes(query);
    });
}

function getVisibleFailedDispatchTaskIds() {
    return (dispatchTasks || [])
        .filter((task) => String(task?.status || '').toLowerCase() === 'failed')
        .map((task) => String(task?.id || '').trim())
        .filter(Boolean);
}

function toggleDispatchTaskDetail(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
        return;
    }
    if (dispatchExpandedTaskIds.has(safeTaskId)) {
        dispatchExpandedTaskIds.delete(safeTaskId);
    } else {
        dispatchExpandedTaskIds.add(safeTaskId);
    }
    renderDispatchTasks();
}

async function copyDispatchTaskId(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
        return;
    }
    try {
        await navigator.clipboard.writeText(safeTaskId);
        alert(`Task ID copiado: ${safeTaskId}`);
    } catch (error) {
        try {
            const textarea = document.createElement('textarea');
            textarea.value = safeTaskId;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            alert(`Task ID copiado: ${safeTaskId}`);
        } catch (fallbackError) {
            alert(`No se pudo copiar el Task ID: ${safeTaskId}`);
        }
    }
}

function updateDispatchBulkRetryButton() {
    const button = document.getElementById('dispatch-retry-failed-btn');
    if (!button) return;
    const failedCount = getVisibleFailedDispatchTaskIds().length;
    button.disabled = dispatchBulkRetryInProgress || failedCount === 0;
    button.textContent = failedCount > 0
        ? `Reintentar fallidas visibles (${failedCount})`
        : 'Reintentar fallidas visibles';
}

function renderDispatchTasks() {
    const tbody = document.getElementById('dispatch-tasks-body');
    const summary = document.getElementById('dispatch-summary');
    if (!tbody || !summary) return;
    dispatchTasks = applyDispatchClientFilter(dispatchTasksRaw);

    if (!dispatchTasks.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No hay tareas para los filtros actuales</td></tr>';
        summary.textContent = 'Sin datos';
        summary.classList.add('is-empty');
        updateDispatchBulkRetryButton();
        return;
    }

    if (dispatchTasksRaw.length !== dispatchTasks.length) {
        summary.textContent = `${dispatchTasks.length} visibles de ${dispatchTasksRaw.length}`;
    } else {
        summary.textContent = `${dispatchTasks.length} tareas`;
    }
    summary.classList.remove('is-empty');

    tbody.innerHTML = dispatchTasks.map((task) => {
        const status = String(task.status || '').trim().toLowerCase();
        const canRetry = status === 'failed';
        const entityId = task.entity_id || '-';
        const action = task.action || '-';
        const source = task.source || '-';
        const lastError = task.last_error ? compactErrorText(task.last_error, 160) : '';
        const attempts = `${Number(task.attempt_count || 0)}/${Number(task.max_attempts || 0)}`;
        const when = formatTime(task.updated_at || task.created_at || '');
        const taskId = String(task.id || '');
        const taskToken = encodeURIComponent(taskId);
        const isExpanded = dispatchExpandedTaskIds.has(taskId);
        const detailBlock = lastError
            ? `<div class="dispatch-error">${escapeHtml(lastError)}</div>`
            : '<span class="muted">Sin error</span>';
        const detailRow = isExpanded
            ? `
            <tr class="dispatch-detail-row">
                <td colspan="8">
                    <div class="dispatch-detail-wrap">
                        <pre class="dispatch-detail-pre">${escapeHtml(buildDispatchDetailText(task))}</pre>
                    </div>
                </td>
            </tr>
            `
            : '';
        return `
            <tr>
                <td>${escapeHtml(when)}</td>
                <td>${escapeHtml(source)}</td>
                <td>
                    <span class="mono-id">${escapeHtml(entityId)}</span>
                    <div class="dispatch-id">${escapeHtml(taskId || '-')}</div>
                </td>
                <td>${escapeHtml(action)}</td>
                <td><span class="status ${dispatchStatusClass(status)}">${escapeHtml(dispatchStatusLabel(status))}</span></td>
                <td>${escapeHtml(attempts)}</td>
                <td>${detailBlock}</td>
                <td>
                    <div class="dispatch-actions">
                        <button class="btn sm secondary dispatch-copy-id-btn" data-task-token="${escapeHtml(taskToken)}">Copiar ID</button>
                        <button class="btn sm secondary dispatch-detail-btn" data-task-token="${escapeHtml(taskToken)}">${isExpanded ? 'Ocultar' : 'Detalle'}</button>
                        ${canRetry && taskId
                            ? `<button class="btn sm dispatch-retry-btn" data-task-token="${escapeHtml(taskToken)}">Reintentar</button>`
                            : ''
                        }
                    </div>
                </td>
            </tr>
        ${detailRow}
        `;
    }).join('');

    tbody.querySelectorAll('.dispatch-retry-btn').forEach((btn) => {
        btn.addEventListener('click', () => retryDispatchTask(decodeDispatchToken(btn.getAttribute('data-task-token') || '')));
    });
    tbody.querySelectorAll('.dispatch-copy-id-btn').forEach((btn) => {
        btn.addEventListener('click', () => copyDispatchTaskId(decodeDispatchToken(btn.getAttribute('data-task-token') || '')));
    });
    tbody.querySelectorAll('.dispatch-detail-btn').forEach((btn) => {
        btn.addEventListener('click', () => toggleDispatchTaskDetail(decodeDispatchToken(btn.getAttribute('data-task-token') || '')));
    });
    updateDispatchBulkRetryButton();
}

function getDispatchPanelFilters() {
    const source = (document.getElementById('dispatch-source-filter')?.value || '').trim();
    const status = (document.getElementById('dispatch-status-filter')?.value || '').trim();
    const rawLimit = parseInt(document.getElementById('dispatch-limit')?.value || '30', 10);
    const limit = Number.isFinite(rawLimit) ? Math.min(200, Math.max(5, rawLimit)) : 30;
    return { source, status, limit };
}

async function refreshDispatchPanel(options = {}) {
    const silent = Boolean(options.silent);
    if (dispatchRefreshInProgress) return;
    dispatchRefreshInProgress = true;
    const refreshBtn = document.getElementById('dispatch-refresh-btn');
    const summary = document.getElementById('dispatch-summary');
    if (refreshBtn) refreshBtn.disabled = true;
    if (summary && dispatchTasks.length === 0) {
        summary.textContent = 'Actualizando...';
        summary.classList.remove('is-empty');
    }

    try {
        const apiBase = await ensureApiPort();
        const { source, status, limit } = getDispatchPanelFilters();

        const taskParams = new URLSearchParams();
        taskParams.set('limit', String(limit));
        if (source) taskParams.set('source', source);
        if (status) taskParams.set('status', status);

        const statsParams = new URLSearchParams();
        if (source) statsParams.set('source', source);
        const statsQuery = statsParams.toString();

        const [tasksResponse, statsResponse] = await Promise.all([
            fetch(`${apiBase}/api/dispatch/tasks?${taskParams.toString()}`),
            fetch(`${apiBase}/api/dispatch/stats${statsQuery ? `?${statsQuery}` : ''}`)
        ]);

        const tasksPayload = await tasksResponse.json().catch(() => ({}));
        const statsPayload = await statsResponse.json().catch(() => ({}));

        if (tasksResponse.ok) {
            dispatchTasksRaw = Array.isArray(tasksPayload.items) ? tasksPayload.items : [];
        } else {
            dispatchTasksRaw = [];
            if (!silent) {
                alert(`Error cargando tareas de dispatch: ${tasksPayload.detail || tasksResponse.status}`);
            }
        }

        if (statsResponse.ok) {
            dispatchStats = statsPayload || null;
        } else {
            dispatchStats = null;
        }
    } catch (error) {
        dispatchTasksRaw = [];
        dispatchStats = null;
        if (!silent) {
            alert(`Error de conexion en cola de despacho: ${error.message}`);
        }
    } finally {
        renderDispatchStats();
        renderDispatchTasks();
        if (refreshBtn) refreshBtn.disabled = false;
        dispatchRefreshInProgress = false;
    }
}

async function retryDispatchTask(taskId) {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) return;
    if (!(await uiConfirm({
        title: 'Reencolar tarea',
        message: `Reencolar tarea ${safeTaskId}?`,
        confirmText: 'Reencolar'
    }))) {
        return;
    }
    try {
        const apiBase = await ensureApiPort();
        const response = await fetch(`${apiBase}/api/dispatch/tasks/${encodeURIComponent(safeTaskId)}/retry`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reset_attempts: true,
                clear_result: false
            })
        });
        const result = await response.json().catch(() => ({}));
        if (response.ok) {
            await refreshDispatchPanel({ silent: true });
            alert(`Tarea ${safeTaskId} reencolada`);
        } else {
            alert(`No se pudo reintentar ${safeTaskId}: ${result.detail || response.status}`);
        }
    } catch (error) {
        alert(`Error de conexion reintentando tarea: ${error.message}`);
    }
}

async function retryFailedVisibleDispatchTasks() {
    if (dispatchBulkRetryInProgress) {
        return;
    }
    const taskIds = getVisibleFailedDispatchTaskIds();
    if (!taskIds.length) {
        alert('No hay tareas fallidas visibles para reintentar.');
        return;
    }
    if (!(await uiConfirm({
        title: 'Reintentar tareas',
        message: `Se reintentaran ${taskIds.length} tareas fallidas visibles. Continuar?`,
        confirmText: 'Reintentar'
    }))) {
        return;
    }
    dispatchBulkRetryInProgress = true;
    updateDispatchBulkRetryButton();
    let okCount = 0;
    let failCount = 0;
    try {
        const apiBase = await ensureApiPort();
        for (const taskId of taskIds) {
            try {
                const response = await fetch(`${apiBase}/api/dispatch/tasks/${encodeURIComponent(taskId)}/retry`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        reset_attempts: true,
                        clear_result: false
                    })
                });
                if (response.ok) {
                    okCount += 1;
                } else {
                    failCount += 1;
                }
            } catch (error) {
                failCount += 1;
            }
        }
        await refreshDispatchPanel({ silent: true });
        alert(`Reintentos finalizados. OK=${okCount} | Error=${failCount}`);
    } catch (error) {
        alert(`Error durante reintentos masivos: ${error.message}`);
    } finally {
        dispatchBulkRetryInProgress = false;
        updateDispatchBulkRetryButton();
    }
}
