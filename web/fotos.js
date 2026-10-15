(() => {
    'use strict';

    const API = '/api/photo-crop';
    const IMAGE_EXTENSIONS = /\.(jpe?g|png|webp|bmp|tiff?)$/i;
    const state = {
        sessionId: null,
        photos: [],
        currentId: null,
        ratio: 0.75,
        filterReview: false,
        search: '',
        busy: false,
        dragging: false,
        lastPointer: null,
        view: null,
        data: { filename: '', headers: [], rows: [], primary: '', secondary: '' },
        systemFonts: [],
        // Encuadre automático: null = criterio de foto carné (margen para el pelo).
        framing: { faceFill: null, eyePosition: 40 },
    };
    let designer = null;

    const $ = (id) => document.getElementById(id);
    const elements = {
        fileInput: $('file-input'), folderInput: $('folder-input'), photoList: $('photo-list'),
        canvas: $('photo-canvas'), canvasShell: $('canvas-shell'), canvasEmpty: $('canvas-empty'),
        canvasLoading: $('canvas-loading'), title: $('photo-title'), meta: $('photo-meta'),
        badges: $('editor-badges'), summary: $('batch-summary'), reviewCount: $('review-count'),
        quality: $('quality-content'), brightness: $('brightness-range'), contrast: $('contrast-range'),
        brightnessValue: $('brightness-value'), contrastValue: $('contrast-value'), aspect: $('aspect-select'),
        outputWidth: $('output-width'), outputHeight: $('output-height'), format: $('output-format'),
        suffix: $('output-suffix'), status: $('status-text'), statusLed: $('status-led'),
        progress: $('progress-bar'), exportButton: $('export-btn'), exportTop: $('export-top-btn'),
        detectAll: $('detect-all-btn'), search: $('photo-search'), reviewOnly: $('review-only'),
        pdfInput: $('pdf-input'), dataInput: $('data-input'), projectInput: $('project-input'),
        backgroundMode: $('background-mode'), backgroundStrength: $('background-strength'),
        backgroundStrengthValue: $('background-strength-value'), matchPrimary: $('match-field-primary'),
        matchSecondary: $('match-field-secondary'), matchButton: $('match-data-btn'), dataNote: $('data-file-note'),
        matchReport: $('match-report'), cardEnabled: $('card-enabled'),
        reviewPdf: $('review-pdf-btn'), saveProject: $('save-project-btn'),
        cardMiniFront: $('card-mini-front'), cardMiniBack: $('card-mini-back'),
    };
    const ctx = elements.canvas.getContext('2d');

    function currentPhoto() {
        return state.photos.find((photo) => photo.id === state.currentId) || null;
    }

    function effectiveSize(photo) {
        return photo.rotation % 180 === 0
            ? { width: photo.width, height: photo.height }
            : { width: photo.height, height: photo.width };
    }

    function centeredCrop(width, height, ratio = state.ratio) {
        let cropWidth;
        let cropHeight;
        if (width / height > ratio) {
            cropHeight = height;
            cropWidth = cropHeight * ratio;
        } else {
            cropWidth = width;
            cropHeight = cropWidth / ratio;
        }
        const left = (width - cropWidth) / 2;
        const top = (height - cropHeight) / 2;
        return [left, top, left + cropWidth, top + cropHeight];
    }

    function makePhoto(data, saved = {}) {
        const defaults = {
            crop: centeredCrop(data.width, data.height), brightness: 1, contrast: 1,
            rotation: 0, detected: false, faceFound: false, faceBox: null, eyeLine: null,
            issues: [], approved: false, manual: false, metadata: {}, matchStatus: '',
            printCount: 0, lastPrinted: null,
        };
        return { ...defaults, ...saved, ...data, image: null };
    }

    function clampCrop(photo, crop) {
        const size = effectiveSize(photo);
        let [left, top, right, bottom] = crop.map(Number);
        const width = Math.min(size.width, Math.max(1, right - left));
        const height = Math.min(size.height, Math.max(1, bottom - top));
        left = Math.min(Math.max(0, left), size.width - width);
        top = Math.min(Math.max(0, top), size.height - height);
        return [left, top, left + width, top + height];
    }

    function cropAround(photo, centerX, centerY, width, height) {
        const size = effectiveSize(photo);
        const maxWidth = Math.min(size.width, size.height * state.ratio);
        width = Math.min(Math.max(60, width), maxWidth);
        height = width / state.ratio;
        if (height > size.height) {
            height = size.height;
            width = height * state.ratio;
        }
        return clampCrop(photo, [centerX - width / 2, centerY - height / 2, centerX + width / 2, centerY + height / 2]);
    }

    async function api(path, options = {}) {
        const response = await fetch(`${API}${path}`, options);
        if (!response.ok) {
            let message = `Error ${response.status}`;
            try {
                const payload = await response.json();
                if (Array.isArray(payload.detail)) {
                    message = payload.detail.map((item) => `${(item.loc || []).slice(-1)[0] || 'dato'}: ${item.msg}`).join(' · ');
                } else {
                    message = payload.detail || message;
                }
            } catch (_) { /* respuesta no JSON */ }
            throw new Error(message);
        }
        return response;
    }

    function setStatus(message, kind = 'ok', progress = null) {
        elements.status.textContent = message;
        elements.statusLed.className = `status-led${kind === 'busy' ? ' busy' : kind === 'error' ? ' error' : ''}`;
        if (progress !== null) elements.progress.style.width = `${Math.max(0, Math.min(100, progress))}%`;
    }

    function setBusy(value) {
        state.busy = value;
        document.querySelectorAll('button').forEach((button) => {
            if (button.id !== 'theme-btn') button.disabled = value || (button.dataset.requiresPhotos === 'true' && !state.photos.length);
        });
        elements.detectAll.disabled = value || !state.photos.length;
        elements.exportButton.disabled = value || !state.photos.length;
        elements.exportTop.disabled = value || !state.photos.length;
        elements.reviewPdf.disabled = value || !state.photos.length;
        elements.saveProject.disabled = value || !state.photos.length;
        elements.matchButton.disabled = value || !state.data.rows.length || !elements.matchPrimary.value;
        if (!value) designer?.refresh();
    }

    async function ensureSession() {
        if (state.sessionId) return state.sessionId;
        const response = await api('/sessions', { method: 'POST' });
        const data = await response.json();
        state.sessionId = data.session_id;
        return state.sessionId;
    }

    function requiresReview(photo) {
        return !photo.approved && (!photo.detected || (photo.issues && photo.issues.length > 0));
    }

    function visiblePhotos() {
        const query = state.search.toLocaleLowerCase('es');
        return state.photos.filter((photo) => {
            const matchesSearch = !query || photo.filename.toLocaleLowerCase('es').includes(query);
            return matchesSearch && (!state.filterReview || requiresReview(photo));
        });
    }

    function photoStatus(photo) {
        if (photo.approved) return ['approved', 'Revisada'];
        if (!photo.detected) return ['review', 'Pendiente de analizar'];
        if (photo.issues?.length) return ['review', photo.issues[0]];
        return ['ready', photo.manual ? 'Ajustada manualmente' : 'Lista para exportar'];
    }

    function updateSummary() {
        const review = state.photos.filter(requiresReview).length;
        const ready = state.photos.length - review;
        elements.summary.textContent = `${state.photos.length} foto${state.photos.length === 1 ? '' : 's'} · ${ready} lista${ready === 1 ? '' : 's'}`;
        elements.reviewCount.textContent = review;
        elements.reviewCount.title = `${review} requieren revisión`;
        elements.detectAll.disabled = state.busy || !state.photos.length;
        elements.exportButton.disabled = state.busy || !state.photos.length;
        elements.exportTop.disabled = state.busy || !state.photos.length;
        elements.reviewPdf.disabled = state.busy || !state.photos.length;
        elements.saveProject.disabled = state.busy || !state.photos.length;
    }

    function renderList() {
        const visible = visiblePhotos();
        elements.photoList.replaceChildren();
        if (!visible.length) {
            const empty = document.createElement('div');
            empty.className = 'list-empty';
            empty.innerHTML = state.photos.length
                ? '<div class="empty-icon">✓</div><strong>No hay coincidencias</strong><span>Probá limpiar el filtro de revisión o la búsqueda.</span>'
                : '<div class="empty-icon">▧</div><strong>El lote está vacío</strong><span>Agregá fotos o una carpeta para comenzar.</span>';
            elements.photoList.append(empty);
            updateSummary();
            return;
        }
        visible.forEach((photo) => {
            const [statusClass, statusText] = photoStatus(photo);
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `photo-item${photo.id === state.currentId ? ' active' : ''}`;
            button.dataset.id = photo.id;
            button.setAttribute('aria-selected', String(photo.id === state.currentId));
            button.tabIndex = photo.id === state.currentId ? 0 : -1;
            const thumb = document.createElement('img');
            thumb.className = 'photo-thumb';
            thumb.src = photo.preview_url;
            thumb.alt = '';
            const copy = document.createElement('span');
            copy.className = 'photo-copy';
            const strong = document.createElement('strong');
            strong.textContent = photo.filename;
            const detail = document.createElement('span');
            detail.textContent = photo.printCount
                ? `${statusText} · Impresa${photo.printCount > 1 ? ` ×${photo.printCount}` : ''}`
                : statusText;
            if (photo.lastPrinted) detail.title = `Última impresión: ${new Date(photo.lastPrinted).toLocaleString('es-UY')}`;
            copy.append(strong, detail);
            const dot = document.createElement('span');
            dot.className = `photo-state-dot ${statusClass}`;
            button.append(thumb, copy, dot);
            button.addEventListener('click', () => selectPhoto(photo.id, { focusList: true }));
            elements.photoList.append(button);
        });
        updateSummary();
    }

    function loadPreview(photo) {
        if (photo.image?.complete) return Promise.resolve(photo.image);
        elements.canvasLoading.hidden = false;
        return new Promise((resolve, reject) => {
            const image = photo.image || new Image();
            photo.image = image;
            image.onload = () => { elements.canvasLoading.hidden = true; resolve(image); };
            image.onerror = () => { elements.canvasLoading.hidden = true; reject(new Error('No se pudo cargar la vista previa')); };
            if (!image.src) image.src = photo.preview_url;
        });
    }

    function focusPhotoInList(photoId) {
        requestAnimationFrame(() => {
            const button = elements.photoList.querySelector(`.photo-item[data-id="${CSS.escape(photoId)}"]`);
            if (!button) return;
            button.focus({ preventScroll: true });
            button.scrollIntoView({ block: 'nearest' });
        });
    }

    async function selectPhoto(photoId, { focusList = false } = {}) {
        state.currentId = photoId;
        const photo = currentPhoto();
        renderList();
        if (focusList) focusPhotoInList(photoId);
        if (!photo) return draw();
        elements.title.textContent = photo.filename;
        const size = effectiveSize(photo);
        elements.meta.textContent = `${size.width} × ${size.height} px · ${(photo.size / 1024 / 1024).toFixed(1)} MB`;
        elements.brightness.value = Math.round(photo.brightness * 100);
        elements.contrast.value = Math.round(photo.contrast * 100);
        elements.brightnessValue.value = `${elements.brightness.value}%`;
        elements.contrastValue.value = `${elements.contrast.value}%`;
        $('approve-current-btn').textContent = photo.approved ? '↶ Reabrir revisión' : '✓ Marcar revisada';
        renderQuality(photo);
        renderBadges(photo);
        designer?.onPhotoChanged();
        elements.canvasEmpty.hidden = true;
        try {
            await loadPreview(photo);
            draw();
            renderCardMini();
            designer?.onPhotoChanged();
        } catch (error) {
            setStatus(error.message, 'error');
        }
    }

    function renderBadges(photo) {
        const badges = [];
        if (photo.faceFound) badges.push(`<span class="mini-badge good">Rostro · ${escapeHtml(photo.engine || 'detectado')}</span>`);
        else if (photo.detected) badges.push('<span class="mini-badge warn">Sin rostro</span>');
        if (photo.manual) badges.push('<span class="mini-badge">Ajuste manual</span>');
        if (photo.matchStatus === 'matched') badges.push('<span class="mini-badge good">Datos vinculados</span>');
        else if (state.data.rows.length) badges.push('<span class="mini-badge warn">Sin datos</span>');
        elements.badges.innerHTML = badges.join('');
    }

    function renderQuality(photo) {
        if (!photo.detected) {
            elements.quality.className = 'quality-empty';
            elements.quality.textContent = 'Todavía no se analizó esta foto.';
            return;
        }
        if (!photo.issues?.length) {
            elements.quality.className = 'quality-good';
            elements.quality.innerHTML = '<span>✓</span><span>No se detectaron observaciones.</span>';
            return;
        }
        elements.quality.className = '';
        const list = document.createElement('ul');
        list.className = 'quality-list';
        photo.issues.forEach((issue) => {
            const item = document.createElement('li');
            item.textContent = issue;
            list.append(item);
        });
        elements.quality.replaceChildren(list);
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = String(value);
        return div.innerHTML;
    }

    function resizeCanvas() {
        const rect = elements.canvasShell.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const width = Math.max(1, Math.round(rect.width));
        const height = Math.max(1, Math.round(rect.height));
        if (elements.canvas.width !== Math.round(width * dpr) || elements.canvas.height !== Math.round(height * dpr)) {
            elements.canvas.width = Math.round(width * dpr);
            elements.canvas.height = Math.round(height * dpr);
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        draw(width, height);
    }

    function draw(givenWidth = null, givenHeight = null) {
        const rect = elements.canvasShell.getBoundingClientRect();
        const width = givenWidth || Math.max(1, rect.width);
        const height = givenHeight || Math.max(1, rect.height);
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#06101c';
        ctx.fillRect(0, 0, width, height);
        const photo = currentPhoto();
        if (!photo?.image?.complete) {
            state.view = null;
            elements.canvasEmpty.hidden = Boolean(photo);
            return;
        }
        const size = effectiveSize(photo);
        const margin = 24;
        const scale = Math.min((width - margin * 2) / size.width, (height - margin * 2) / size.height);
        const drawWidth = size.width * scale;
        const drawHeight = size.height * scale;
        const originX = (width - drawWidth) / 2;
        const originY = (height - drawHeight) / 2;
        state.view = { scale, originX, originY, width: drawWidth, height: drawHeight };

        ctx.save();
        ctx.beginPath();
        ctx.rect(originX, originY, drawWidth, drawHeight);
        ctx.clip();
        ctx.filter = `brightness(${photo.brightness}) contrast(${photo.contrast})`;
        ctx.translate(originX + drawWidth / 2, originY + drawHeight / 2);
        ctx.rotate(photo.rotation * Math.PI / 180);
        ctx.drawImage(photo.image, -photo.width * scale / 2, -photo.height * scale / 2, photo.width * scale, photo.height * scale);
        ctx.restore();
        ctx.filter = 'none';

        const [left, top, right, bottom] = photo.crop;
        const x = originX + left * scale;
        const y = originY + top * scale;
        const cropWidth = (right - left) * scale;
        const cropHeight = (bottom - top) * scale;
        ctx.save();
        ctx.fillStyle = 'rgba(2, 8, 16, .68)';
        ctx.beginPath();
        ctx.rect(originX, originY, drawWidth, drawHeight);
        ctx.rect(x, y, cropWidth, cropHeight);
        ctx.fill('evenodd');
        ctx.strokeStyle = '#f8fbff';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, cropWidth, cropHeight);
        ctx.strokeStyle = 'rgba(80, 222, 207, .78)';
        ctx.lineWidth = 1;
        for (let index = 1; index < 3; index += 1) {
            ctx.beginPath();
            ctx.moveTo(x + cropWidth * index / 3, y);
            ctx.lineTo(x + cropWidth * index / 3, y + cropHeight);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, y + cropHeight * index / 3);
            ctx.lineTo(x + cropWidth, y + cropHeight * index / 3);
            ctx.stroke();
        }
        const handle = 13;
        ctx.strokeStyle = '#50decf';
        ctx.lineWidth = 4;
        [[x, y, 1, 1], [x + cropWidth, y, -1, 1], [x, y + cropHeight, 1, -1], [x + cropWidth, y + cropHeight, -1, -1]].forEach(([hx, hy, sx, sy]) => {
            ctx.beginPath();
            ctx.moveTo(hx, hy + sy * handle);
            ctx.lineTo(hx, hy);
            ctx.lineTo(hx + sx * handle, hy);
            ctx.stroke();
        });
        if (photo.eyeLine !== null && photo.eyeLine !== undefined && photo.rotation === 0) {
            const eyeY = originY + photo.eyeLine * scale;
            if (eyeY >= y && eyeY <= y + cropHeight) {
                ctx.setLineDash([6, 5]);
                ctx.strokeStyle = 'rgba(246, 196, 83, .9)';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(x, eyeY);
                ctx.lineTo(x + cropWidth, eyeY);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
        ctx.restore();
    }

    function canvasPoint(event) {
        const rect = elements.canvas.getBoundingClientRect();
        return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function pointInsideCrop(point, photo) {
        if (!state.view) return false;
        const [left, top, right, bottom] = photo.crop;
        const { scale, originX, originY } = state.view;
        return point.x >= originX + left * scale && point.x <= originX + right * scale
            && point.y >= originY + top * scale && point.y <= originY + bottom * scale;
    }

    function moveCrop(photo, deltaX, deltaY) {
        const [left, top, right, bottom] = photo.crop;
        photo.crop = clampCrop(photo, [left + deltaX, top + deltaY, right + deltaX, bottom + deltaY]);
        photo.manual = true;
        photo.approved = false;
        renderBadges(photo);
        draw();
    }

    function scaleCrop(factor) {
        const photo = currentPhoto();
        if (!photo) return;
        const [left, top, right, bottom] = photo.crop;
        const centerX = (left + right) / 2;
        const centerY = (top + bottom) / 2;
        photo.crop = cropAround(photo, centerX, centerY, (right - left) * factor, (bottom - top) * factor);
        photo.manual = true;
        photo.approved = false;
        renderList();
        renderBadges(photo);
        draw();
    }

    function rotateCurrent(clockwise) {
        const photo = currentPhoto();
        if (!photo) return;
        const oldSize = effectiveSize(photo);
        const [left, top, right, bottom] = photo.crop;
        if (clockwise) {
            photo.crop = [oldSize.height - bottom, left, oldSize.height - top, right];
            photo.rotation = (photo.rotation + 90) % 360;
        } else {
            photo.crop = [top, oldSize.width - right, bottom, oldSize.width - left];
            photo.rotation = (photo.rotation + 270) % 360;
        }
        photo.crop = clampCrop(photo, photo.crop);
        photo.manual = true;
        photo.approved = false;
        const newSize = effectiveSize(photo);
        elements.meta.textContent = `${newSize.width} × ${newSize.height} px · ${(photo.size / 1024 / 1024).toFixed(1)} MB`;
        renderList();
        renderBadges(photo);
        draw();
    }

    function ensureAspectOption(ratio) {
        const value = String(Math.round(Number(ratio) * 10000) / 10000);
        const existing = [...elements.aspect.options].find((option) => Math.abs(Number(option.value) - Number(value)) < 0.0005);
        if (existing) return existing.value;
        const option = document.createElement('option');
        option.value = value;
        option.dataset.size = `${Math.round(800 * Number(value))}x800`;
        option.textContent = `${Number(value).toLocaleString('es-UY', { maximumFractionDigits: 3 })} · caja de la credencial`;
        elements.aspect.append(option);
        return option.value;
    }

    async function setAspectRatio(ratio, { redetect = false } = {}) {
        elements.aspect.value = ensureAspectOption(ratio);
        changeRatio();
        if (redetect && state.photos.length) await detect();
        else setStatus('Proporción del recorte ajustada a la caja de la foto. Revisá los encuadres o volvé a detectar rostros.');
    }

    function adjustPhotoCrop(photo, { dx = 0, dy = 0, scale = 1 } = {}) {
        const [left, top, right, bottom] = photo.crop;
        photo.crop = cropAround(photo, (left + right) / 2 + dx, (top + bottom) / 2 + dy, (right - left) * scale, (bottom - top) * scale);
        photo.manual = true;
        photo.approved = false;
        if (photo.id === state.currentId) draw();
        return photo.crop;
    }

    function changeRatio() {
        state.ratio = Number(elements.aspect.value);
        const option = elements.aspect.selectedOptions[0];
        const [width, height] = option.dataset.size.split('x');
        elements.outputWidth.value = width;
        elements.outputHeight.value = height;
        state.photos.forEach((photo) => {
            const [left, top, right, bottom] = photo.crop;
            const centerX = (left + right) / 2;
            const centerY = (top + bottom) / 2;
            const currentArea = Math.max(1, (right - left) * (bottom - top));
            let newWidth = Math.sqrt(currentArea * state.ratio);
            let newHeight = newWidth / state.ratio;
            const size = effectiveSize(photo);
            const fit = Math.min(1, size.width / newWidth, size.height / newHeight);
            newWidth *= fit;
            newHeight *= fit;
            photo.crop = clampCrop(photo, [centerX - newWidth / 2, centerY - newHeight / 2, centerX + newWidth / 2, centerY + newHeight / 2]);
            photo.manual = true;
            photo.approved = false;
        });
        renderList();
        draw();
    }

    async function uploadFiles(fileList) {
        const files = Array.from(fileList).filter((file) => IMAGE_EXTENSIONS.test(file.name));
        if (!files.length) return setStatus('No se encontraron imágenes compatibles.', 'error');
        if (state.photos.length + files.length > 250) return setStatus('El lote admite hasta 250 fotos.', 'error');
        setBusy(true);
        setStatus(`Preparando ${files.length} foto${files.length === 1 ? '' : 's'}…`, 'busy', 0);
        let uploaded = 0;
        let failed = 0;
        try {
            const sessionId = await ensureSession();
            for (const file of files) {
                try {
                    const response = await api(`/sessions/${sessionId}/photos?filename=${encodeURIComponent(file.name)}`, {
                        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
                    });
                    const data = await response.json();
                    const photo = makePhoto(data);
                    state.photos.push(photo);
                    uploaded += 1;
                    if (!state.currentId) await selectPhoto(photo.id);
                    else renderList();
                } catch (error) {
                    failed += 1;
                    console.error(error);
                }
                setStatus(`Cargando foto ${uploaded + failed} de ${files.length}…`, 'busy', ((uploaded + failed) / files.length) * 100);
            }
            setStatus(`${uploaded} foto${uploaded === 1 ? '' : 's'} agregada${uploaded === 1 ? '' : 's'}${failed ? ` · ${failed} no se pudieron cargar` : ''}.`, failed ? 'error' : 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally {
            setBusy(false);
            elements.fileInput.value = '';
            elements.folderInput.value = '';
            renderList();
        }
    }

    async function importPdf(file) {
        if (!file) return;
        setBusy(true);
        setStatus('Convirtiendo las páginas del PDF…', 'busy', 10);
        try {
            const sessionId = await ensureSession();
            const response = await api(`/sessions/${sessionId}/pdf?filename=${encodeURIComponent(file.name)}`, {
                method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file,
            });
            const data = await response.json();
            const wasEmpty = !state.photos.length;
            data.photos.forEach((photo) => state.photos.push(makePhoto(photo)));
            renderList();
            if (wasEmpty && state.photos.length) await selectPhoto(state.photos[0].id);
            setStatus(`PDF importado · ${data.pages} página${data.pages === 1 ? '' : 's'} agregada${data.pages === 1 ? '' : 's'}.`, 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally {
            elements.pdfInput.value = '';
            setBusy(false);
        }
    }

    function addSelectOptions(select, emptyLabel, selected = '') {
        select.replaceChildren();
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = emptyLabel;
        select.append(empty);
        state.data.headers.forEach((header) => {
            const option = document.createElement('option');
            option.value = header;
            option.textContent = header;
            select.append(option);
        });
        select.value = state.data.headers.includes(selected) ? selected : '';
    }

    function populateDataFields(primary = '', secondary = '') {
        addSelectOptions(elements.matchPrimary, 'Seleccionar columna', primary);
        addSelectOptions(elements.matchSecondary, 'Ninguno', secondary);
        elements.matchButton.disabled = state.busy || !state.data.rows.length || !elements.matchPrimary.value;
    }

    async function loadSystemFonts() {
        try {
            const response = await api('/fonts');
            const data = await response.json();
            state.systemFonts = data.fonts || [];
            designer?.refresh();
            renderCardMini();
        } catch (error) {
            console.error('No se pudo leer el catálogo de fuentes; se usarán las básicas.', error);
        }
    }

    async function importData(file) {
        if (!file) return;
        setBusy(true);
        setStatus('Leyendo la planilla…', 'busy', 20);
        try {
            const sessionId = await ensureSession();
            const response = await api(`/sessions/${sessionId}/data?filename=${encodeURIComponent(file.name)}`, {
                method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
            });
            const data = await response.json();
            state.data = { filename: data.filename, headers: data.headers, rows: data.rows, primary: '', secondary: '' };
            elements.dataNote.textContent = `${data.filename} · ${data.count} fila${data.count === 1 ? '' : 's'} · ${data.headers.length} columnas`;
            const likelyName = data.headers.find((header) => /^(nombre|name)$/i.test(header)) || data.headers.find((header) => /nombre/i.test(header)) || '';
            const likelySurname = data.headers.find((header) => /apellido/i.test(header)) || '';
            populateDataFields(likelyName, likelySurname);
            designer?.onDataChanged();
            elements.matchReport.className = 'match-report';
            elements.matchReport.innerHTML = '<strong>Planilla lista</strong><p>Elegí las columnas del nombre y vinculá los datos con las fotos.</p>';
            setStatus(`Planilla importada · ${data.count} registros.`, 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally {
            elements.dataInput.value = '';
            setBusy(false);
        }
    }

    function normalizedName(value) {
        return String(value || '')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ')
            .replace(/\b(pagina|page)\s*\d+\b/gi, ' ')
            .replace(/[^a-z0-9]+/gi, ' ').trim().toLocaleLowerCase('es');
    }

    function matchData() {
        const primary = elements.matchPrimary.value;
        const secondary = elements.matchSecondary.value;
        if (!primary) return setStatus('Elegí la columna principal del nombre.', 'error');
        state.data.primary = primary;
        state.data.secondary = secondary;
        const candidates = state.data.rows.map((row, index) => {
            const name = normalizedName(`${row[primary] || ''} ${secondary ? row[secondary] || '' : ''}`);
            return { row, index, name, tokens: new Set(name.split(' ').filter(Boolean)) };
        }).filter((item) => item.name);
        const used = new Set();
        let matched = 0;
        state.photos.forEach((photo) => {
            const photoName = normalizedName(photo.filename);
            const photoTokens = new Set(photoName.split(' ').filter(Boolean));
            let best = candidates.find((item) => !used.has(item.index) && item.name === photoName);
            if (!best) {
                const ranked = candidates.filter((item) => !used.has(item.index)).map((item) => {
                    const common = [...item.tokens].filter((token) => photoTokens.has(token)).length;
                    const coversName = item.tokens.size > 0 && [...item.tokens].every((token) => photoTokens.has(token));
                    return { item, score: coversName ? 10 + common : common / Math.max(item.tokens.size, photoTokens.size, 1) };
                }).filter((entry) => entry.score >= 10 || entry.score >= 0.75).sort((a, b) => b.score - a.score);
                best = ranked[0]?.item;
            }
            if (best) {
                used.add(best.index);
                photo.metadata = best.row;
                photo.matchStatus = 'matched';
                matched += 1;
            } else {
                photo.metadata = {};
                photo.matchStatus = 'unmatched';
            }
        });
        const missingPhotos = state.photos.filter((photo) => photo.matchStatus !== 'matched');
        const unusedRows = candidates.length - used.size;
        elements.matchReport.className = `match-report ${missingPhotos.length || unusedRows ? 'warn' : 'good'}`;
        const examples = missingPhotos.slice(0, 4).map((photo) => escapeHtml(photo.filename)).join(', ');
        elements.matchReport.innerHTML = `<strong>${matched} de ${state.photos.length} fotos vinculadas</strong><p>${missingPhotos.length} fotos sin datos · ${unusedRows} filas sin foto${examples ? ` · Revisar: ${examples}` : ''}</p>`;
        renderList();
        if (currentPhoto()) renderBadges(currentPhoto());
        designer?.onDataChanged();
        renderCardMini();
        setStatus(`Coincidencia terminada · ${matched} fotos vinculadas.`, missingPhotos.length ? 'error' : 'ok', 100);
    }

    function renderCardMini() {
        if (!designer) return;
        designer.renderMini(elements.cardMiniFront, 'front');
        elements.cardMiniBack.hidden = !designer.isDoubleSided();
        if (designer.isDoubleSided()) designer.renderMini(elements.cardMiniBack, 'back');
    }

    function exportItem(photo) {
        return {
            photo_id: photo.id, crop: photo.crop, brightness: photo.brightness,
            contrast: photo.contrast, rotation: photo.rotation, approved: photo.approved,
            issues: photo.issues || [], metadata: photo.metadata || {},
            sequence: state.photos.indexOf(photo) + 1,
        };
    }

    function photoOptions() {
        return {
            background_mode: elements.backgroundMode.value,
            background_strength: Number(elements.backgroundStrength.value),
        };
    }

    function exportPayload() {
        const width = Number(elements.outputWidth.value);
        const height = Number(elements.outputHeight.value);
        if (!Number.isInteger(width) || !Number.isInteger(height) || width < 64 || height < 64 || width > 6000 || height > 6000) {
            throw new Error('Revisá las dimensiones de salida.');
        }
        return {
            format: elements.format.value, width, height, suffix: elements.suffix.value,
            ...photoOptions(),
            card_design: elements.cardEnabled.checked ? designer.getDesign() : null,
            items: state.photos.map(exportItem),
        };
    }

    async function downloadResponse(response, fallbackName) {
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition') || '';
        const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        const plain = disposition.match(/filename="?([^";]+)"?/i);
        let filename = plain?.[1];
        try { if (encoded) filename = decodeURIComponent(encoded[1]); } catch (_) { /* nombre ASCII alternativo */ }
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename || fallbackName;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
    }

    async function createReviewPdf() {
        if (!state.photos.length || !state.sessionId) return;
        setBusy(true);
        setStatus('Generando la hoja PDF de revisión…', 'busy', 20);
        try {
            const response = await api(`/sessions/${state.sessionId}/review-pdf`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(exportPayload()),
            });
            await downloadResponse(response, 'revision_fotos.pdf');
            setStatus('Hoja PDF de revisión generada.', 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally { setBusy(false); }
    }

    function projectState() {
        const photos = {};
        state.photos.forEach((photo) => {
            photos[photo.id] = {
                crop: photo.crop, brightness: photo.brightness, contrast: photo.contrast,
                rotation: photo.rotation, detected: photo.detected, faceFound: photo.faceFound,
                faceBox: photo.faceBox, eyeLine: photo.eyeLine, issues: photo.issues,
                approved: photo.approved, manual: photo.manual, engine: photo.engine,
                metadata: photo.metadata || {}, matchStatus: photo.matchStatus || '',
                printCount: photo.printCount || 0, lastPrinted: photo.lastPrinted || null,
            };
        });
        return {
            photos,
            settings: {
                aspect: elements.aspect.value, width: elements.outputWidth.value, height: elements.outputHeight.value,
                format: elements.format.value, suffix: elements.suffix.value,
                backgroundMode: elements.backgroundMode.value, backgroundStrength: elements.backgroundStrength.value,
                cardEnabled: elements.cardEnabled.checked,
                cardDesign: designer.serialize(),
                framing: state.framing,
            },
            data: state.data,
        };
    }

    async function saveProject() {
        if (!state.photos.length || !state.sessionId) return;
        setBusy(true);
        setStatus('Guardando originales y ajustes…', 'busy', 15);
        try {
            const response = await api(`/sessions/${state.sessionId}/project`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state: projectState() }),
            });
            await downloadResponse(response, 'proyecto_fotos.recortador.zip');
            setStatus('Proyecto guardado.', 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally { setBusy(false); }
    }

    function restoreProjectSettings(saved = {}, resources = {}) {
        if (saved.aspect) { elements.aspect.value = ensureAspectOption(saved.aspect); state.ratio = Number(saved.aspect); }
        if (saved.width) elements.outputWidth.value = saved.width;
        if (saved.height) elements.outputHeight.value = saved.height;
        if (saved.format) elements.format.value = saved.format;
        elements.suffix.value = saved.suffix || '';
        elements.backgroundMode.value = saved.backgroundMode || 'original';
        elements.backgroundStrength.value = saved.backgroundStrength || 55;
        elements.backgroundStrengthValue.value = `${elements.backgroundStrength.value}%`;
        elements.cardEnabled.checked = Boolean(saved.cardEnabled);
        state.framing = { faceFill: saved.framing?.faceFill ?? null, eyePosition: saved.framing?.eyePosition ?? 40 };
        populateDataFields(state.data.primary, state.data.secondary);
        designer.restore(saved, resources);
    }

    async function openProject(file) {
        if (!file) return;
        if (state.photos.length && !window.confirm('¿Reemplazar el lote actual por el proyecto guardado?')) {
            elements.projectInput.value = '';
            return;
        }
        setBusy(true);
        setStatus('Abriendo el proyecto…', 'busy', 10);
        const previousSession = state.sessionId;
        try {
            const response = await api(`/projects?filename=${encodeURIComponent(file.name)}`, {
                method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
            });
            const data = await response.json();
            state.sessionId = data.session_id;
            state.data = data.state?.data || { filename: '', headers: [], rows: [], primary: '', secondary: '' };
            state.photos = data.photos.map((photo) => makePhoto(photo, photo.state || {}));
            state.currentId = null;
            const stamp = Date.now();
            restoreProjectSettings(data.state?.settings || {}, {
                assets: (data.assets || []).map((asset) => ({ ...asset, url: `${asset.url}?v=${stamp}` })),
                logoUrl: data.logo_url, backgroundUrl: data.card_background_url,
            });
            elements.dataNote.textContent = state.data.filename ? `${state.data.filename} · ${state.data.rows.length} filas` : 'Todavía no se importó una planilla.';
            renderList();
            if (state.photos.length) await selectPhoto(state.photos[0].id);
            setStatus(`Proyecto abierto · ${state.photos.length} fotos.`, 'ok', 100);
            if (previousSession) api(`/sessions/${previousSession}`, { method: 'DELETE' }).catch(() => {});
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally {
            elements.projectInput.value = '';
            setBusy(false);
        }
    }

    async function detect(photoIds = null, { quiet = false } = {}) {
        if (!state.photos.length || !state.sessionId) return null;
        setBusy(true);
        const count = photoIds?.length || state.photos.length;
        if (!quiet) setStatus(`Analizando ${count} foto${count === 1 ? '' : 's'}…`, 'busy', 10);
        try {
            const response = await api(`/sessions/${state.sessionId}/detect`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    photo_ids: photoIds, ratio: state.ratio, hair_margin: 0.20,
                    eye_position: state.framing.eyePosition, face_fill: state.framing.faceFill,
                }),
            });
            const data = await response.json();
            data.results.forEach((result) => {
                const photo = state.photos.find((item) => item.id === result.photo_id);
                if (!photo) return;
                photo.rotation = 0;
                photo.crop = result.crop;
                photo.detected = true;
                photo.faceFound = result.face_found;
                photo.faceBox = result.face_box;
                photo.eyeLine = result.eye_line;
                photo.engine = result.engine;
                photo.issues = result.issues || [];
                photo.approved = false;
                photo.manual = false;
            });
            const issues = data.results.filter((result) => result.issues?.length).length;
            if (!quiet) setStatus(`Análisis terminado · ${issues} foto${issues === 1 ? '' : 's'} para revisar${data.engine_note ? ` · ${data.engine_note}` : ''}`, 'ok', 100);
            renderList();
            if (currentPhoto()) {
                renderQuality(currentPhoto());
                renderBadges(currentPhoto());
                draw();
            }
            renderCardMini();
            return data.results;
        } catch (error) {
            setStatus(error.message, 'error', 0);
            return null;
        } finally {
            setBusy(false);
        }
    }

    async function autoFrame({ ratio, faceFill, eyePosition, photoIds = null, quiet = false }) {
        // Encuadra las fotos para la caja de la credencial usando la detección de rostros.
        state.framing = { faceFill, eyePosition };
        if (Math.abs(Number(ratio) - state.ratio) > 0.0005) {
            elements.aspect.value = ensureAspectOption(ratio);
            changeRatio();
        }
        const results = await detect(photoIds, { quiet: true });
        if (!results) return null;
        const missing = results.filter((result) => !result.face_found).length;
        if (!quiet) {
            setStatus(
                `${results.length} foto${results.length === 1 ? '' : 's'} encuadrada${results.length === 1 ? '' : 's'} en la caja`
                + (missing ? ` · ${missing} sin rostro detectado quedaron centradas` : ''),
                missing ? 'error' : 'ok', 100,
            );
        }
        return { count: results.length, missing };
    }

    function resetCurrent() {
        const photo = currentPhoto();
        if (!photo) return;
        photo.rotation = 0;
        photo.crop = centeredCrop(photo.width, photo.height);
        photo.brightness = 1;
        photo.contrast = 1;
        photo.manual = false;
        photo.approved = false;
        selectPhoto(photo.id);
        setStatus('Se restablecieron los ajustes de la foto.');
    }

    function approveCurrent() {
        const photo = currentPhoto();
        if (!photo) return;
        photo.approved = !photo.approved;
        $('approve-current-btn').textContent = photo.approved ? '↶ Reabrir revisión' : '✓ Marcar revisada';
        renderList();
        setStatus(photo.approved ? 'Foto marcada como revisada.' : 'La foto volvió a revisión.');
    }

    async function exportBatch() {
        if (!state.photos.length || !state.sessionId) return;
        setBusy(true);
        setStatus(`Preparando ${state.photos.length} fotos en alta calidad…`, 'busy', 15);
        try {
            const response = await api(`/sessions/${state.sessionId}/export`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(exportPayload()),
            });
            setStatus('Empaquetando el lote…', 'busy', 75);
            await downloadResponse(response, 'fotos_recortadas.zip');
            setStatus(`Lote exportado · ${state.photos.length} fotos y registro CSV.`, 'ok', 100);
        } catch (error) {
            setStatus(error.message, 'error', 0);
        } finally {
            setBusy(false);
        }
    }

    async function newBatch() {
        if (state.photos.length && !window.confirm('¿Vaciar el lote actual? Las fotos originales no se eliminarán.')) return;
        const oldSession = state.sessionId;
        state.sessionId = null;
        state.photos = [];
        state.currentId = null;
        state.view = null;
        state.data = { filename: '', headers: [], rows: [], primary: '', secondary: '' };
        state.framing = { faceFill: null, eyePosition: 40 };
        elements.title.textContent = 'Vista previa';
        elements.meta.textContent = 'Seleccioná una foto para editarla.';
        elements.badges.replaceChildren();
        elements.quality.className = 'quality-empty';
        elements.quality.textContent = 'Todavía no se analizó esta foto.';
        elements.canvasEmpty.hidden = false;
        elements.dataNote.textContent = 'Todavía no se importó una planilla.';
        elements.matchReport.className = 'match-report';
        elements.matchReport.innerHTML = '<strong>Sin coincidencias calculadas</strong><p>Importá una planilla y elegí las columnas que forman el nombre.</p>';
        populateDataFields();
        designer.reset();
        renderCardMini();
        renderList();
        setBusy(false);
        resizeCanvas();
        setStatus('Nuevo lote listo.');
        if (oldSession) {
            try { await api(`/sessions/${oldSession}`, { method: 'DELETE' }); } catch (_) { /* vence automaticamente */ }
        }
    }

    function bindEvents() {
        $('add-files-btn').addEventListener('click', () => elements.fileInput.click());
        $('add-folder-btn').addEventListener('click', () => elements.folderInput.click());
        $('add-pdf-btn').addEventListener('click', () => elements.pdfInput.click());
        $('import-data-btn').addEventListener('click', () => elements.dataInput.click());
        $('choose-data-btn').addEventListener('click', () => elements.dataInput.click());
        $('open-project-btn').addEventListener('click', () => elements.projectInput.click());
        elements.fileInput.addEventListener('change', () => uploadFiles(elements.fileInput.files));
        elements.folderInput.addEventListener('change', () => uploadFiles(elements.folderInput.files));
        elements.pdfInput.addEventListener('change', () => importPdf(elements.pdfInput.files[0]));
        elements.dataInput.addEventListener('change', () => importData(elements.dataInput.files[0]));
        elements.projectInput.addEventListener('change', () => openProject(elements.projectInput.files[0]));
        elements.detectAll.addEventListener('click', () => detect());
        $('detect-current-btn').addEventListener('click', () => currentPhoto() && detect([currentPhoto().id]));
        $('zoom-in-btn').addEventListener('click', () => scaleCrop(0.9));
        $('zoom-out-btn').addEventListener('click', () => scaleCrop(1.1));
        $('rotate-left-btn').addEventListener('click', () => rotateCurrent(false));
        $('rotate-right-btn').addEventListener('click', () => rotateCurrent(true));
        $('reset-current-btn').addEventListener('click', resetCurrent);
        $('approve-current-btn').addEventListener('click', approveCurrent);
        elements.aspect.addEventListener('change', changeRatio);
        elements.brightness.addEventListener('input', () => {
            const photo = currentPhoto();
            elements.brightnessValue.value = `${elements.brightness.value}%`;
            if (photo) { photo.brightness = Number(elements.brightness.value) / 100; photo.manual = true; draw(); }
        });
        elements.brightness.addEventListener('change', () => { if (currentPhoto()) { renderList(); renderBadges(currentPhoto()); } });
        elements.contrast.addEventListener('input', () => {
            const photo = currentPhoto();
            elements.contrastValue.value = `${elements.contrast.value}%`;
            if (photo) { photo.contrast = Number(elements.contrast.value) / 100; photo.manual = true; draw(); }
        });
        elements.contrast.addEventListener('change', () => { if (currentPhoto()) { renderList(); renderBadges(currentPhoto()); } });
        elements.search.addEventListener('input', () => { state.search = elements.search.value.trim(); renderList(); });
        elements.reviewOnly.addEventListener('change', () => { state.filterReview = elements.reviewOnly.checked; renderList(); });
        elements.matchPrimary.addEventListener('change', () => { elements.matchButton.disabled = state.busy || !elements.matchPrimary.value; });
        elements.matchButton.addEventListener('click', matchData);
        elements.backgroundStrength.addEventListener('input', () => { elements.backgroundStrengthValue.value = `${elements.backgroundStrength.value}%`; });
        $('open-card-designer-btn').addEventListener('click', () => designer.open());
        $('card-print-current-btn').addEventListener('click', () => designer.openExport('current', { print: true }));
        $('card-print-batch-btn').addEventListener('click', () => designer.openExport('all', { print: true }));
        $('card-export-current-btn').addEventListener('click', () => designer.openExport('current', { print: false }));
        $('card-export-batch-btn').addEventListener('click', () => designer.openExport('all', { print: false }));
        $('output-card-export-btn').addEventListener('click', () => designer.openExport('all'));
        elements.exportButton.addEventListener('click', exportBatch);
        elements.exportTop.addEventListener('click', exportBatch);
        elements.reviewPdf.addEventListener('click', createReviewPdf);
        elements.saveProject.addEventListener('click', saveProject);
        $('new-batch-btn').addEventListener('click', newBatch);
        $('theme-btn').addEventListener('click', () => {
            if (typeof window.panelToggleTheme === 'function') window.panelToggleTheme($('theme-btn'));
            setTimeout(draw, 0);
        });
        document.querySelectorAll('.control-tab').forEach((tab) => tab.addEventListener('click', () => {
            document.querySelectorAll('.control-tab').forEach((item) => item.classList.toggle('active', item === tab));
            document.querySelectorAll('.control-page').forEach((page) => page.classList.toggle('active', page.id === `tab-${tab.dataset.tab}`));
            if (tab.dataset.tab === 'card') requestAnimationFrame(renderCardMini);
        }));

        elements.canvas.addEventListener('pointerdown', (event) => {
            elements.canvas.focus({ preventScroll: true });
            const photo = currentPhoto();
            const point = canvasPoint(event);
            if (!photo || !pointInsideCrop(point, photo)) return;
            state.dragging = true;
            state.lastPointer = point;
            elements.canvas.classList.add('dragging');
            elements.canvas.setPointerCapture(event.pointerId);
        });
        elements.canvas.addEventListener('pointermove', (event) => {
            if (!state.dragging || !state.view) return;
            const photo = currentPhoto();
            const point = canvasPoint(event);
            moveCrop(photo, (point.x - state.lastPointer.x) / state.view.scale, (point.y - state.lastPointer.y) / state.view.scale);
            state.lastPointer = point;
        });
        const stopDragging = () => {
            if (state.dragging) renderList();
            state.dragging = false;
            state.lastPointer = null;
            elements.canvas.classList.remove('dragging');
        };
        elements.canvas.addEventListener('pointerup', stopDragging);
        elements.canvas.addEventListener('pointercancel', stopDragging);
        elements.canvas.addEventListener('wheel', (event) => {
            if (!currentPhoto()) return;
            event.preventDefault();
            scaleCrop(event.deltaY > 0 ? 1.06 : 0.94);
        }, { passive: false });
        document.addEventListener('keydown', (event) => {
            if (designer.isOpen()) return;
            const photo = currentPhoto();
            if (!photo || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
            const focusedListItem = document.activeElement?.closest?.('.photo-item');
            if (focusedListItem) {
                const visible = visiblePhotos();
                const currentIndex = visible.findIndex((item) => item.id === state.currentId);
                let targetIndex = currentIndex;
                if (event.key === 'ArrowDown') targetIndex = Math.min(visible.length - 1, currentIndex + 1);
                else if (event.key === 'ArrowUp') targetIndex = Math.max(0, currentIndex - 1);
                else if (event.key === 'Home') targetIndex = 0;
                else if (event.key === 'End') targetIndex = visible.length - 1;
                else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                    event.preventDefault();
                    return;
                } else return;
                event.preventDefault();
                if (visible[targetIndex]) selectPhoto(visible[targetIndex].id, { focusList: true });
                return;
            }
            if (document.activeElement !== elements.canvas) return;
            const step = event.shiftKey ? 10 : 2;
            const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
            if (moves[event.key]) {
                event.preventDefault();
                moveCrop(photo, ...moves[event.key]);
            } else if (event.key === '+' || event.key === '=') scaleCrop(0.94);
            else if (event.key === '-') scaleCrop(1.06);
        });
        new ResizeObserver(resizeCanvas).observe(elements.canvasShell);
        new ResizeObserver(() => renderCardMini()).observe(elements.cardMiniFront);
    }

    function initialize() {
        designer = window.CardDesigner.create({
            api, ensureSession, setStatus, setBusy, loadPreview, downloadResponse, exportItem, photoOptions,
            getPhotos: () => state.photos,
            getVisiblePhotos: visiblePhotos,
            getCurrentPhoto: currentPhoto,
            getHeaders: () => state.data.headers,
            getSystemFonts: () => state.systemFonts,
            selectPhoto: (photoId) => selectPhoto(photoId),
            onDesignChanged: renderCardMini,
            onRecordChanged: (photo) => { if (photo.id === state.currentId) renderBadges(photo); },
            getCropRatio: () => state.ratio,
            getFraming: () => ({ ...state.framing }),
            autoFrame,
            setAspectRatio,
            adjustCrop: adjustPhotoCrop,
            onCropCommitted: (photo) => { renderList(); if (photo.id === state.currentId) { renderBadges(photo); draw(); } renderCardMini(); },
            onPrinted: (printed) => {
                printed.forEach(({ photo_id: photoId, printed_at: printedAt }) => {
                    const photo = state.photos.find((item) => item.id === photoId);
                    if (!photo) return;
                    photo.printCount = (photo.printCount || 0) + 1;
                    photo.lastPrinted = printedAt;
                });
                renderList();
            },
        });
        bindEvents();
        const currentTheme = typeof window.panelCurrentTheme === 'function' ? window.panelCurrentTheme() : 'dark';
        $('theme-btn').textContent = currentTheme === 'light' ? 'Tema oscuro' : 'Tema claro';
        document.querySelectorAll('#detect-current-btn, #zoom-in-btn, #zoom-out-btn, #rotate-left-btn, #rotate-right-btn, #reset-current-btn, #approve-current-btn, #card-export-current-btn, #card-export-batch-btn, #card-print-current-btn, #card-print-batch-btn, #output-card-export-btn').forEach((button) => {
            button.dataset.requiresPhotos = 'true';
            button.disabled = true;
        });
        populateDataFields();
        designer.reset();
        renderCardMini();
        loadSystemFonts();
        renderList();
        resizeCanvas();
    }

    initialize();
})();
