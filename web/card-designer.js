/*
 * Editor de credenciales con objetos libres.
 *
 * El diseño se guarda como datos (fracciones de la tarjeta + medidas en puntos)
 * y el servidor lo vuelve a componer en alta resolución al exportar. Esta vista
 * reproduce el mismo algoritmo de ajuste de texto para que lo que se ve en
 * pantalla coincida con el archivo final; "Vista exacta" pide el render real.
 */
(() => {
    'use strict';

    const API = '/api/photo-crop';
    const PT_PER_MM = 72 / 25.4;
    const CARD_CORNER_MM = 3.18;
    const SAFE_MARGIN_MM = 3;
    const BUILTIN_FIELDS = ['Archivo', 'Nro', 'Fecha', 'Año'];
    const SIZE_PRESETS = [
        { id: 'cr80', label: 'CR80 · tarjeta estándar', w: 85.6, h: 53.98 },
        { id: 'cr79', label: 'CR79 · adhesiva', w: 84.1, h: 52.4 },
        { id: 'cr100', label: 'CR100 · grande', w: 98.5, h: 67 },
        { id: 'a7', label: 'Gafete A7', w: 105, h: 74 },
        { id: 'a6', label: 'Gafete A6 · eventos', w: 148, h: 105 },
        { id: 'custom', label: 'Personalizado' },
    ];
    const TYPE_LABELS = {
        text: 'Texto', photo: 'Foto', image: 'Imagen', qr: 'Código QR', barcode: 'Código de barras',
        rect: 'Rectángulo', ellipse: 'Elipse', line: 'Línea',
    };
    const TYPE_ICONS = { text: 'T', photo: '◪', image: '▣', qr: '▦', barcode: '┃┃', rect: '□', ellipse: '○', line: '─' };
    const DEFAULTS = {
        text: {
            text: 'Texto', font: 'sans', size: 12, bold: false, italic: false, underline: false, uppercase: false,
            color: '#17202b', align: 'left', valign: 'middle', fit: 'shrink', line_height: 1.15, padding: 0,
            fill: null, stroke_color: null, stroke_width: 0, radius: 0,
        },
        photo: { shape: 'rect', radius: 3, stroke_color: null, stroke_width: 0, image_fit: 'cover', grayscale: false },
        image: { asset: null, image_fit: 'contain', radius: 0, stroke_color: null, stroke_width: 0, grayscale: false },
        qr: { value: '{Archivo}', color: '#000000', background: '#ffffff', ecc: 'M' },
        barcode: { value: '{Nro}', symbology: 'code128', show_text: true, color: '#000000', background: null },
        rect: { fill: '#176b87', stroke_color: null, stroke_width: 0, radius: 0 },
        ellipse: { fill: '#176b87', stroke_color: null, stroke_width: 0 },
        line: { stroke_color: '#17202b', stroke_width: 1 },
    };
    const NEW_SIZES_MM = {
        text: [40, 8], photo: [24, 32], image: [20, 12], qr: [16, 16], barcode: [36, 12],
        rect: [30, 14], ellipse: [16, 16], line: [36, 2],
    };
    const BARCODE_TYPES = [
        ['code128', 'Code 128 · alfanumérico'], ['code39', 'Code 39'], ['ean13', 'EAN-13'],
        ['ean8', 'EAN-8'], ['upca', 'UPC-A'], ['itf', 'ITF · intercalado 2 de 5'],
    ];
    const CONDITION_OPS = [
        ['always', 'Siempre'], ['equals', 'Si el campo es igual a'], ['not_equals', 'Si el campo no es igual a'],
        ['contains', 'Si el campo contiene'], ['not_empty', 'Si el campo tiene dato'], ['empty', 'Si el campo está vacío'],
    ];

    const measureContext = document.createElement('canvas').getContext('2d');

    function barcodeLabel(symbology, value) {
        // Texto legible con el dígito verificador que agrega el servidor en EAN/UPC.
        const lengths = { ean13: 12, ean8: 7, upca: 11 };
        if (!lengths[symbology] || !/^\d+$/.test(value) || value.length !== lengths[symbology]) return value;
        const digits = [...value].map(Number).reverse();
        const sum = digits.reduce((total, digit, index) => total + digit * (index % 2 === 0 ? 3 : 1), 0);
        return `${value}${(10 - (sum % 10)) % 10}`;
    }
    const clone = (value) => JSON.parse(JSON.stringify(value));
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const newId = () => `e${Math.random().toString(36).slice(2, 10)}`;
    const $ = (id) => document.getElementById(id);

    function h(tag, attributes = {}, children = []) {
        const node = document.createElement(tag);
        Object.entries(attributes).forEach(([key, value]) => {
            if (value === undefined || value === null || value === false) return;
            if (key === 'class') node.className = value;
            else if (key === 'text') node.textContent = value;
            else if (key === 'style') Object.assign(node.style, value);
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else if (key in node && typeof value !== 'string') node[key] = value;
            else node.setAttribute(key, value === true ? '' : value);
        });
        (Array.isArray(children) ? children : [children]).forEach((child) => {
            if (child === null || child === undefined || child === false) return;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        });
        return node;
    }

    // ------------------------------------------------------------------ //
    // Modelo
    // ------------------------------------------------------------------ //

    function emptySide(color = '#ffffff') {
        return { background_color: color, background_image: null, elements: [] };
    }

    function makeElement(type, props = {}) {
        return {
            id: newId(), type, name: '', x: 0.1, y: 0.1, w: 0.3, h: 0.15, rotation: 0, opacity: 1,
            hidden: false, locked: false, condition: null, ...clone(DEFAULTS[type] || {}), ...props,
        };
    }

    function guessFields(headers) {
        const find = (...patterns) => headers.find((header) => patterns.some((pattern) => pattern.test(header))) || '';
        const first = find(/^nombres?$/i, /^name$/i, /nombre/i);
        const last = find(/apellido/i, /surname|last.?name/i);
        const full = find(/nombre.*apellido|apellido.*nombre|nombre completo|full.?name/i);
        const role = find(/cargo/i, /puesto/i, /funci[oó]n/i, /^rol$/i, /[aá]rea/i, /sector/i, /curso/i);
        const id = find(/legajo/i, /documento/i, /^c\.?i\.?$/i, /c[eé]dula/i, /dni/i, /^id$/i, /n[uú]mero/i, /matr[ií]cula/i);
        let name = '{Archivo}';
        if (full) name = `{${full}}`;
        else if (first && last && first !== last) name = `{${first}} {${last}}`;
        else if (first) name = `{${first}}`;
        return { name, role: role ? `{${role}}` : 'Cargo / función', id: id ? `{${id}}` : '{Nro}', idLabel: id || 'Nro' };
    }

    // Las plantillas se escriben en fracciones de la tarjeta (x, y, ancho, alto).
    const box = (x, y, w, h) => ({ x, y, w, h });
    const TEMPLATES = [
        {
            id: 'classic', label: 'Clásica', orientation: 'landscape', thumb: 'classic',
            build: ({ accent, logo, fields }) => ({
                background_color: '#ffffff', background_image: null, elements: [
                    makeElement('rect', { name: 'Encabezado', ...box(0, 0, 1, 0.18), fill: accent }),
                    makeElement('text', { name: 'Título', ...box(0.045, 0.025, 0.62, 0.13), text: 'NOMBRE DE LA EMPRESA', size: 11, bold: true, color: '#ffffff' }),
                    makeElement('image', { name: 'Logo', ...box(0.76, 0.02, 0.2, 0.14), asset: logo }),
                    makeElement('photo', { name: 'Foto', ...box(0.045, 0.255, 0.27, 0.69), radius: 3 }),
                    makeElement('text', { name: 'Nombre', ...box(0.36, 0.27, 0.6, 0.15), text: fields.name, size: 14, bold: true }),
                    makeElement('text', { name: 'Cargo', ...box(0.36, 0.43, 0.6, 0.1), text: fields.role, size: 9.5, color: '#5b6b7f' }),
                    makeElement('text', { name: 'Identificador', ...box(0.36, 0.6, 0.36, 0.08), text: `${fields.idLabel}: ${fields.id}`, size: 7.5, color: '#5b6b7f' }),
                    makeElement('qr', { name: 'QR', ...box(0.765, 0.6, 0.19, 0.3), value: fields.id }),
                    makeElement('rect', { name: 'Filete', ...box(0.36, 0.71, 0.36, 0.012), fill: accent }),
                ],
            }),
        },
        {
            id: 'sidebar', label: 'Banda lateral', orientation: 'landscape', thumb: 'sidebar',
            build: ({ accent, logo, fields }) => ({
                background_color: '#ffffff', background_image: null, elements: [
                    makeElement('rect', { name: 'Banda', ...box(0, 0, 0.33, 1), fill: accent }),
                    makeElement('image', { name: 'Logo', ...box(0.05, 0.06, 0.23, 0.16), asset: logo }),
                    makeElement('photo', { name: 'Foto', ...box(0.055, 0.28, 0.22, 0.6), radius: 2.5, stroke_color: '#ffffff', stroke_width: 1.5 }),
                    makeElement('text', { name: 'Título', ...box(0.38, 0.07, 0.58, 0.1), text: 'CREDENCIAL', size: 10, bold: true, color: accent }),
                    makeElement('text', { name: 'Nombre', ...box(0.38, 0.28, 0.58, 0.16), text: fields.name, size: 15, bold: true, fit: 'wrap_shrink' }),
                    makeElement('text', { name: 'Cargo', ...box(0.38, 0.45, 0.58, 0.1), text: fields.role, size: 10, color: '#5b6b7f' }),
                    makeElement('barcode', { name: 'Código', ...box(0.38, 0.66, 0.46, 0.24), value: fields.id }),
                ],
            }),
        },
        {
            id: 'minimal', label: 'Minimalista', orientation: 'landscape', thumb: 'minimal',
            build: ({ accent, logo, fields }) => ({
                background_color: '#f7f8fb', background_image: null, elements: [
                    makeElement('photo', { name: 'Foto', ...box(0.06, 0.16, 0.27, 0.43), shape: 'circle', stroke_color: accent, stroke_width: 1.5 }),
                    makeElement('image', { name: 'Logo', ...box(0.8, 0.07, 0.15, 0.13), asset: logo }),
                    makeElement('text', { name: 'Nombre', ...box(0.38, 0.27, 0.56, 0.14), text: fields.name, size: 14, bold: true }),
                    makeElement('text', { name: 'Cargo', ...box(0.38, 0.42, 0.56, 0.09), text: fields.role, size: 9.5, color: accent, uppercase: true }),
                    makeElement('text', { name: 'Identificador', ...box(0.06, 0.66, 0.27, 0.08), text: fields.id, size: 8, align: 'center', color: '#5b6b7f' }),
                    makeElement('qr', { name: 'QR', ...box(0.79, 0.56, 0.16, 0.26), value: fields.id, background: null }),
                    makeElement('rect', { name: 'Barra inferior', ...box(0, 0.94, 1, 0.06), fill: accent }),
                ],
            }),
        },
        {
            id: 'portrait', label: 'Vertical', orientation: 'portrait', thumb: 'portrait',
            build: ({ accent, logo, fields }) => ({
                background_color: '#ffffff', background_image: null, elements: [
                    makeElement('rect', { name: 'Encabezado', ...box(0, 0, 1, 0.14), fill: accent }),
                    makeElement('text', { name: 'Título', ...box(0.07, 0.03, 0.6, 0.08), text: 'EMPRESA', size: 11, bold: true, color: '#ffffff' }),
                    makeElement('image', { name: 'Logo', ...box(0.72, 0.02, 0.22, 0.1), asset: logo }),
                    makeElement('photo', { name: 'Foto', ...box(0.22, 0.18, 0.56, 0.4), radius: 3 }),
                    makeElement('text', { name: 'Nombre', ...box(0.06, 0.61, 0.88, 0.08), text: fields.name, size: 13, bold: true, align: 'center' }),
                    makeElement('text', { name: 'Cargo', ...box(0.06, 0.69, 0.88, 0.05), text: fields.role, size: 9, align: 'center', color: '#5b6b7f' }),
                    makeElement('qr', { name: 'QR', ...box(0.36, 0.77, 0.28, 0.177), value: fields.id }),
                    makeElement('rect', { name: 'Pie', ...box(0, 0.975, 1, 0.025), fill: accent }),
                ],
            }),
        },
        {
            id: 'event', label: 'Evento', orientation: 'portrait', thumb: 'event',
            build: ({ accent, logo, fields }) => ({
                background_color: '#ffffff', background_image: null, elements: [
                    makeElement('rect', { name: 'Fondo superior', ...box(0, 0, 1, 0.42), fill: accent }),
                    makeElement('image', { name: 'Logo', ...box(0.3, 0.035, 0.4, 0.09), asset: logo }),
                    makeElement('photo', { name: 'Foto', ...box(0.22, 0.16, 0.56, 0.353), shape: 'circle', stroke_color: '#ffffff', stroke_width: 3 }),
                    makeElement('text', { name: 'Nombre', ...box(0.06, 0.55, 0.88, 0.12), text: fields.name, size: 16, bold: true, align: 'center', fit: 'wrap_shrink' }),
                    makeElement('text', { name: 'Cargo', ...box(0.06, 0.67, 0.88, 0.05), text: fields.role, size: 9, align: 'center', color: '#5b6b7f' }),
                    makeElement('text', { name: 'Categoría', ...box(0.2, 0.75, 0.6, 0.065), text: 'VISITANTE', size: 10, bold: true, align: 'center', color: '#ffffff', fill: accent, radius: 6 }),
                    makeElement('barcode', { name: 'Código', ...box(0.12, 0.85, 0.76, 0.11), value: fields.id, show_text: false }),
                ],
            }),
        },
        {
            id: 'back', label: 'Dorso informativo', orientation: 'any', thumb: 'back',
            build: ({ accent, fields }) => ({
                background_color: '#ffffff', background_image: null, elements: [
                    makeElement('text', { name: 'Título dorso', ...box(0.06, 0.06, 0.88, 0.1), text: 'CONDICIONES DE USO', size: 9, bold: true, color: accent }),
                    makeElement('text', {
                        name: 'Leyenda', ...box(0.06, 0.18, 0.88, 0.3), size: 7.5, fit: 'wrap_shrink', valign: 'top', color: '#37475a',
                        text: 'Esta credencial es personal e intransferible y debe portarse en lugar visible. Si la encuentra, por favor devuélvala a la empresa.',
                    }),
                    makeElement('line', { name: 'Línea de firma', ...box(0.06, 0.66, 0.4, 0.02), stroke_color: '#37475a', stroke_width: 0.75 }),
                    makeElement('text', { name: 'Firma', ...box(0.06, 0.69, 0.4, 0.07), text: 'Firma', size: 7, color: '#5b6b7f' }),
                    makeElement('text', { name: 'Vencimiento', ...box(0.06, 0.82, 0.4, 0.08), text: 'Válida hasta 31/12/{Año}', size: 7.5, color: '#37475a' }),
                    makeElement('barcode', { name: 'Código', ...box(0.54, 0.6, 0.4, 0.3), value: fields.id }),
                ],
            }),
        },
        {
            id: 'blank', label: 'En blanco', orientation: 'any', thumb: 'blank',
            build: () => emptySide('#ffffff'),
        },
    ];

    // ------------------------------------------------------------------ //
    // Texto: mismo algoritmo que src/card_renderer.py
    // ------------------------------------------------------------------ //

    function textWidth(text, font) {
        measureContext.font = font;
        return text ? measureContext.measureText(text).width : 0;
    }

    function wrapLines(text, font, maxWidth) {
        const lines = [];
        text.split('\n').forEach((paragraph) => {
            let current = '';
            paragraph.split(' ').forEach((original) => {
                let word = original;
                const candidate = current ? `${current} ${word}` : word;
                if (textWidth(candidate, font) <= maxWidth) { current = candidate; return; }
                if (current) lines.push(current);
                current = '';
                while (textWidth(word, font) > maxWidth && word.length > 1) {
                    let cut = word.length;
                    while (cut > 1 && textWidth(word.slice(0, cut), font) > maxWidth) cut -= 1;
                    lines.push(word.slice(0, cut));
                    word = word.slice(cut);
                }
                current = word;
            });
            lines.push(current);
        });
        return lines;
    }

    function layoutText(text, element, family, sizePx, width, height) {
        const minimum = Math.max(1, sizePx * 0.15);
        const fit = element.fit || 'shrink';
        let size = sizePx;
        for (;;) {
            const font = `${element.italic ? 'italic ' : ''}${element.bold ? '700 ' : '400 '}${size}px ${family}`;
            const lines = fit === 'wrap' || fit === 'wrap_shrink' ? wrapLines(text, font, width) : text.split('\n');
            const lineHeight = size * (element.line_height || 1.15);
            const fitsWidth = lines.every((line) => textWidth(line, font) <= width + 0.5);
            const fitsHeight = lineHeight * lines.length <= height + 0.5;
            if (fit === 'none' || fit === 'wrap' || size <= minimum || (fitsWidth && fitsHeight)) {
                return { size, lines, lineHeight };
            }
            size = Math.max(minimum, size * 0.94);
        }
    }

    // ------------------------------------------------------------------ //
    // Fabrica del editor
    // ------------------------------------------------------------------ //

    function create(host) {
        const state = {
            design: null,
            customFields: [],
            assets: [],
            side: 'front',
            selected: [],
            history: [],
            future: [],
            pending: null,
            clipboard: [],
            pxPerMm: null,
            zoomMode: 'fit',
            snapGrid: true,
            smartGuides: true,
            showSafe: true,
            pristine: true,
            cropping: null,
            exactUrl: null,
            photoUrls: new Map(),
        };
        const el = {
            modal: $('card-designer-modal'), stage: $('cd-stage'), shell: $('cd-stage-shell'),
            properties: $('cd-properties'), recordData: $('cd-record-data'), layers: $('cd-layers'),
            assets: $('cd-assets'), templates: $('cd-templates'), record: $('cd-record'),
            exportModal: $('card-export-modal'), assetInput: $('cd-asset-input'), designInput: $('cd-design-input'),
            exact: $('cd-exact'),
        };
        let assetTarget = null;

        // ---------------------------- utilidades ---------------------------- //

        const design = () => state.design;
        const side = () => state.design[state.side];
        const elements = () => side().elements;
        const findElement = (id) => elements().find((item) => item.id === id);
        const selectedElements = () => state.selected.map(findElement).filter(Boolean);
        const cardRatio = () => design().width_mm / design().height_mm;

        function fieldNames() {
            const used = new Set();
            ['front', 'back'].forEach((key) => design()[key].elements.forEach((item) => {
                `${item.text || ''} ${item.value || ''}`.replace(/\{([^{}\n]{1,80})\}/g, (_match, name) => { used.add(name.trim()); return ''; });
                if (item.condition?.field) used.add(item.condition.field);
            }));
            const ordered = [...host.getHeaders(), ...state.customFields];
            used.forEach((name) => { if (!ordered.includes(name) && !BUILTIN_FIELDS.includes(name)) ordered.push(name); });
            return [...new Set(ordered)];
        }

        function valuesFor(photo) {
            const today = new Date();
            const photos = host.getPhotos();
            const index = photo ? photos.indexOf(photo) : -1;
            const values = {
                Archivo: photo ? photo.filename.replace(/\.[^.]+$/, '') : 'Nombre de ejemplo',
                Nro: index >= 0 ? String(index + 1) : '1',
                Fecha: today.toLocaleDateString('es-UY', { day: '2-digit', month: '2-digit', year: 'numeric' }),
                Año: String(today.getFullYear()),
            };
            Object.entries(photo?.metadata || {}).forEach(([key, value]) => { values[key] = value == null ? '' : String(value); });
            return values;
        }

        const resolveFields = (template, values) => String(template || '').replace(/\{([^{}\n]{1,80})\}/g, (_match, name) => values[name.trim()] ?? '');

        function conditionMatches(condition, values) {
            if (!condition || !condition.op || condition.op === 'always') return true;
            const current = String(values[condition.field] ?? '').trim().toLocaleLowerCase('es');
            const expected = String(condition.value ?? '').trim().toLocaleLowerCase('es');
            switch (condition.op) {
                case 'equals': return current === expected;
                case 'not_equals': return current !== expected;
                case 'contains': return current.includes(expected);
                case 'empty': return !current;
                case 'not_empty': return Boolean(current);
                default: return true;
            }
        }

        function fontCss(id) {
            if (id === 'serif') return 'Georgia, serif';
            if (id === 'mono') return 'Consolas, monospace';
            const font = host.getSystemFonts().find((item) => item.id === id);
            return font ? `"${font.css_family}", Arial, sans-serif` : 'Arial, sans-serif';
        }

        function assetUrl(id) {
            return state.assets.find((asset) => asset.asset_id === id)?.url || null;
        }

        function croppedPhotoUrl(photo) {
            const image = photo?.image;
            if (!image?.complete || !image.naturalWidth) return null;
            const key = JSON.stringify([photo.crop, photo.rotation, photo.brightness, photo.contrast, image.src]);
            const cached = state.photoUrls.get(photo.id);
            if (cached?.key === key) return cached.url;
            const scale = image.naturalWidth / photo.width;
            const [left, top, right, bottom] = photo.crop;
            const cropWidth = (right - left) * scale;
            const cropHeight = (bottom - top) * scale;
            const output = Math.min(1, 720 / Math.max(cropWidth, cropHeight));
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(cropWidth * output));
            canvas.height = Math.max(1, Math.round(cropHeight * output));
            const context = canvas.getContext('2d');
            const rotated = photo.rotation % 180 === 0
                ? { width: photo.width, height: photo.height } : { width: photo.height, height: photo.width };
            context.filter = `brightness(${photo.brightness}) contrast(${photo.contrast})`;
            context.scale(output, output);
            context.translate(-left * scale, -top * scale);
            context.translate(rotated.width * scale / 2, rotated.height * scale / 2);
            context.rotate(photo.rotation * Math.PI / 180);
            context.drawImage(image, -photo.width * scale / 2, -photo.height * scale / 2, photo.width * scale, photo.height * scale);
            const url = canvas.toDataURL('image/jpeg', 0.9);
            state.photoUrls.set(photo.id, { key, url });
            return url;
        }

        // ------------------------------ historial ------------------------------ //

        const snapshot = () => JSON.stringify({ design: state.design, customFields: state.customFields });

        function commit(before) {
            if (before === null || before === undefined) return;
            const now = snapshot();
            if (before === now) return;
            state.history.push(before);
            if (state.history.length > 80) state.history.shift();
            state.future = [];
            state.pristine = false;
            updateToolbar();
            host.onDesignChanged();
        }

        function change(mutator, { panel = true } = {}) {
            const before = snapshot();
            mutator();
            commit(before);
            render({ panel });
        }

        function restoreSnapshot(serialized) {
            const restored = JSON.parse(serialized);
            state.design = restored.design;
            state.customFields = restored.customFields || [];
            state.selected = state.selected.filter((id) => findElement(id));
            render();
            host.onDesignChanged();
        }

        function undo() {
            const previous = state.history.pop();
            if (!previous) return;
            state.future.push(snapshot());
            restoreSnapshot(previous);
        }

        function redo() {
            const next = state.future.pop();
            if (!next) return;
            state.history.push(snapshot());
            restoreSnapshot(next);
        }

        // --------------------------- render de caras --------------------------- //

        function elementContent(item, ctx) {
            const { values, ptToPx, photo, boxPx } = ctx;
            const content = h('div', { class: `cd-content cd-${item.type}` });
            const strokePx = (item.stroke_width || 0) * ptToPx;
            const applyFrame = (node, shape) => {
                if (shape === 'circle' || item.type === 'ellipse') node.style.borderRadius = '50%';
                else if (item.radius) node.style.borderRadius = `${item.radius * ptToPx}px`;
                if (item.stroke_color && strokePx > 0) node.style.boxShadow = `inset 0 0 0 ${strokePx}px ${item.stroke_color}`;
            };
            switch (item.type) {
                case 'text': {
                    let text = resolveFields(item.text, values);
                    if (item.uppercase) text = text.toLocaleUpperCase('es');
                    if (item.fill) content.style.background = item.fill;
                    if (item.radius) content.style.borderRadius = `${item.radius * ptToPx}px`;
                    const padding = (item.padding || 0) * ptToPx;
                    const family = fontCss(item.font);
                    const layout = layoutText(text, item, family, (item.size || 12) * ptToPx, Math.max(1, boxPx.w - padding * 2), Math.max(1, boxPx.h - padding * 2));
                    const block = h('div', {
                        class: 'cd-lines',
                        style: {
                            inset: `${padding}px`, justifyContent: { top: 'flex-start', bottom: 'flex-end' }[item.valign] || 'center',
                            textAlign: item.align || 'left', fontFamily: family, fontSize: `${layout.size}px`,
                            fontWeight: item.bold ? '700' : '400', fontStyle: item.italic ? 'italic' : 'normal',
                            color: item.color, textDecoration: item.underline ? 'underline' : 'none',
                        },
                    });
                    if (item.stroke_color && item.stroke_width) {
                        block.style.webkitTextStroke = `${strokePx * 2}px ${item.stroke_color}`;
                        block.style.paintOrder = 'stroke fill';
                    }
                    layout.lines.forEach((line) => block.append(h('div', { class: 'cd-line', style: { height: `${layout.lineHeight}px`, lineHeight: `${layout.lineHeight}px` }, text: line || '​' })));
                    content.append(block);
                    if (!text.trim() && !item.fill) content.classList.add('cd-empty-text');
                    break;
                }
                case 'photo': {
                    const url = croppedPhotoUrl(photo);
                    content.classList.add('cd-imagebox');
                    if (url) content.style.backgroundImage = `url("${url}")`;
                    else content.append(h('span', { class: 'cd-placeholder', text: photo ? 'Cargando…' : 'FOTO' }));
                    content.style.backgroundSize = { contain: 'contain', stretch: '100% 100%' }[item.image_fit] || 'cover';
                    if (item.grayscale) content.style.filter = 'grayscale(1)';
                    applyFrame(content, item.shape);
                    if (photo && !url) host.loadPreview(photo).then(() => render({ panel: false })).catch(() => {});
                    break;
                }
                case 'image': {
                    const url = assetUrl(item.asset);
                    content.classList.add('cd-imagebox');
                    if (url) content.style.backgroundImage = `url("${url}")`;
                    else content.append(h('span', { class: 'cd-placeholder', text: 'IMAGEN' }));
                    content.style.backgroundSize = { cover: 'cover', stretch: '100% 100%' }[item.image_fit] || 'contain';
                    if (item.grayscale) content.style.filter = 'grayscale(1)';
                    applyFrame(content);
                    break;
                }
                case 'qr':
                case 'barcode': {
                    const value = resolveFields(item.value, values).trim();
                    if (!value) { content.append(h('span', { class: 'cd-placeholder', text: 'SIN DATO' })); break; }
                    const params = new URLSearchParams({ value, color: item.color || '#000000' });
                    if (item.background) params.set('background', item.background);
                    if (item.type === 'qr') params.set('ecc', item.ecc || 'M');
                    else { params.set('symbology', item.symbology || 'code128'); params.set('show_text', 'false'); }
                    const image = h('img', { alt: '', draggable: false, src: `${API}/${item.type === 'qr' ? 'qr' : 'barcode'}.svg?${params}` });
                    image.addEventListener('error', () => content.replaceChildren(h('span', { class: 'cd-placeholder cd-invalid', text: 'Código inválido' })));
                    if (item.type === 'barcode' && item.show_text) {
                        // El texto va aparte para que no se deforme al estirar las barras (22 % del alto, como al exportar).
                        const textHeight = boxPx.h * 0.22;
                        if (item.background) content.style.background = item.background;
                        image.style.height = `${boxPx.h - textHeight}px`;
                        content.append(image, h('div', {
                            class: 'cd-barcode-text',
                            style: { height: `${textHeight}px`, fontSize: `${textHeight * 0.9}px`, lineHeight: `${textHeight}px`, color: item.color || '#000000' },
                            text: barcodeLabel(item.symbology || 'code128', value),
                        }));
                    } else {
                        content.append(image);
                    }
                    break;
                }
                case 'rect':
                case 'ellipse':
                    if (item.fill) content.style.background = item.fill;
                    applyFrame(content);
                    break;
                case 'line':
                    content.append(h('div', { class: 'cd-line-bar', style: { height: `${Math.max(1, (item.stroke_width || 1) * ptToPx)}px`, background: item.stroke_color || '#17202b' } }));
                    break;
                default:
                    break;
            }
            return content;
        }

        function renderSide(container, sideData, { photo = null, interactive = false } = {}) {
            const width = container.clientWidth;
            if (!width) return;
            const height = width / cardRatio();
            const pxPerMm = width / design().width_mm;
            const ptToPx = pxPerMm / PT_PER_MM;
            const values = valuesFor(photo);
            container.style.backgroundColor = sideData.background_color;
            const background = assetUrl(sideData.background_image);
            container.style.backgroundImage = background ? `url("${background}")` : '';
            container.style.borderRadius = `${CARD_CORNER_MM * pxPerMm}px`;
            if (!container._cdNodes) container._cdNodes = new Map();
            const nodes = container._cdNodes;
            const layer = container.querySelector(':scope > .cd-objects') || container.appendChild(h('div', { class: 'cd-objects' }));
            const seen = new Set();
            let position = 0;
            sideData.elements.forEach((item, index) => {
                seen.add(item.id);
                const visible = conditionMatches(item.condition, values);
                if ((!interactive && (!visible || item.hidden)) || (interactive && item.hidden)) {
                    nodes.get(item.id)?.remove();
                    nodes.delete(item.id);
                    return;
                }
                const boxPx = { w: item.w * width, h: item.h * height };
                const signature = JSON.stringify([item, values, Math.round(boxPx.w * 10), Math.round(boxPx.h * 10), item.type === 'photo' && photo ? [photo.crop, photo.rotation, photo.brightness, photo.contrast, Boolean(photo.image?.complete)] : '', item.type === 'image' ? assetUrl(item.asset) : '', item.font ? fontCss(item.font) : '']);
                let node = nodes.get(item.id);
                if (!node) {
                    node = h('div', { class: 'cd-element', 'data-id': item.id });
                    nodes.set(item.id, node);
                }
                if (node._signature !== signature) {
                    node.replaceChildren(elementContent(item, { values, ptToPx, photo, boxPx }));
                    node._signature = signature;
                }
                Object.assign(node.style, {
                    left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.w * 100}%`, height: `${item.h * 100}%`,
                    transform: item.rotation ? `rotate(${item.rotation}deg)` : '', opacity: String(item.opacity ?? 1), zIndex: String(index + 1),
                });
                node.classList.toggle('cd-conditional-off', interactive && !visible);
                node.classList.toggle('cd-locked', interactive && Boolean(item.locked));
                node.classList.toggle('cd-cropping', interactive && state.cropping === item.id);
                if (layer.children[position] !== node) layer.insertBefore(node, layer.children[position] || null);
                position += 1;
            });
            [...nodes.keys()].forEach((id) => { if (!seen.has(id)) { nodes.get(id).remove(); nodes.delete(id); } });
            [...layer.children].forEach((child) => { if (!seen.has(child.dataset.id)) child.remove(); });
        }

        // ---------------------------- escenario ---------------------------- //

        function fitPxPerMm() {
            const rect = el.shell.getBoundingClientRect();
            if (!rect.width || !rect.height) return 3;
            return Math.max(0.5, Math.min((rect.width - 64) / design().width_mm, (rect.height - 64) / design().height_mm));
        }

        function layoutStage() {
            const pxPerMm = state.zoomMode === 'fit' ? fitPxPerMm() : state.pxPerMm;
            state.pxPerMm = pxPerMm;
            el.stage.style.width = `${design().width_mm * pxPerMm}px`;
            el.stage.style.height = `${design().height_mm * pxPerMm}px`;
            $('cd-zoom-value').value = state.zoomMode === 'fit' ? 'Ajustar' : `${Math.round(pxPerMm / 3.7795 * 100)}%`;
            const mm = (value) => value.toLocaleString('es-UY', { maximumFractionDigits: 2 });
            $('cd-size-note').textContent = `${mm(design().width_mm)} × ${mm(design().height_mm)} mm${design().double_sided ? ' · doble faz' : ''}`;
            const safe = el.stage.querySelector('.cd-safe');
            safe.hidden = !state.showSafe;
            safe.style.inset = `${SAFE_MARGIN_MM * pxPerMm}px`;
            safe.style.borderRadius = `${Math.max(0, CARD_CORNER_MM - SAFE_MARGIN_MM / 2) * pxPerMm}px`;
        }

        function renderStage() {
            if (el.modal.hidden) return;
            layoutStage();
            renderSide(el.stage, side(), { photo: host.getCurrentPhoto(), interactive: true });
            renderSelection();
        }

        function renderSelection() {
            const overlay = el.stage.querySelector('.cd-selection');
            overlay.replaceChildren();
            const items = selectedElements();
            items.forEach((item) => {
                const frame = h('div', {
                    class: `cd-frame${item.locked ? ' locked' : ''}`,
                    style: {
                        left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.w * 100}%`, height: `${item.h * 100}%`,
                        transform: item.rotation ? `rotate(${item.rotation}deg)` : '',
                    },
                });
                if (items.length === 1 && !item.locked && state.cropping !== item.id) {
                    [[-1, -1], [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0]].forEach(([hx, hy]) => {
                        frame.append(h('i', { class: `cd-handle h${hx}${hy}`, 'data-hx': hx, 'data-hy': hy, style: { left: `${(hx + 1) * 50}%`, top: `${(hy + 1) * 50}%` } }));
                    });
                    frame.append(h('i', { class: 'cd-rotate', title: 'Girar (Mayús: de a 15°)' }));
                }
                overlay.append(frame);
            });
        }

        function render({ panel = true } = {}) {
            if (el.modal.hidden) return;
            renderStage();
            renderLayers();
            if (panel) { renderProperties(); renderRecordData(); renderSideTabs(); renderDocumentControls(); }
            updateToolbar();
        }

        // ------------------------------ selección ------------------------------ //

        function select(ids, { additive = false } = {}) {
            if (state.cropping && (additive || ids.length !== 1 || ids[0] !== state.cropping)) exitCropMode({ quiet: true });
            if (additive) {
                const set = new Set(state.selected);
                ids.forEach((id) => (set.has(id) ? set.delete(id) : set.add(id)));
                state.selected = [...set];
            } else {
                state.selected = [...ids];
            }
            render();
        }

        function stagePoint(event) {
            const rect = el.stage.getBoundingClientRect();
            return { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height, rect };
        }

        function boundsOf(items) {
            const left = Math.min(...items.map((item) => item.x));
            const top = Math.min(...items.map((item) => item.y));
            const right = Math.max(...items.map((item) => item.x + item.w));
            const bottom = Math.max(...items.map((item) => item.y + item.h));
            return { left, top, right, bottom, width: right - left, height: bottom - top };
        }

        function snapMove(moving, dx, dy, rect) {
            // Guías inteligentes contra la tarjeta y el resto de los objetos; si no hay guía, grilla de 1 mm.
            const bounds = boundsOf(moving.map((item) => ({ ...item, x: item._startX + dx, y: item._startY + dy })));
            const guides = [];
            let snappedX = false;
            let snappedY = false;
            if (state.smartGuides) {
                const threshold = { x: 6 / rect.width, y: 6 / rect.height };
                const others = elements().filter((item) => !moving.includes(item) && !item.hidden);
                const targetsX = [0, 0.5, 1, ...others.flatMap((item) => [item.x, item.x + item.w / 2, item.x + item.w])];
                const targetsY = [0, 0.5, 1, ...others.flatMap((item) => [item.y, item.y + item.h / 2, item.y + item.h])];
                const best = (edges, targets, limit) => {
                    let result = null;
                    edges.forEach((edge) => targets.forEach((target) => {
                        const distance = target - edge;
                        if (Math.abs(distance) <= limit && (!result || Math.abs(distance) < Math.abs(result.distance))) result = { distance, target };
                    }));
                    return result;
                };
                const snapX = best([bounds.left, bounds.left + bounds.width / 2, bounds.right], targetsX, threshold.x);
                const snapY = best([bounds.top, bounds.top + bounds.height / 2, bounds.bottom], targetsY, threshold.y);
                if (snapX) { dx += snapX.distance; snappedX = true; guides.push({ axis: 'x', at: snapX.target }); }
                if (snapY) { dy += snapY.distance; snappedY = true; guides.push({ axis: 'y', at: snapY.target }); }
            }
            if (state.snapGrid) {
                const gridX = 1 / design().width_mm;
                const gridY = 1 / design().height_mm;
                if (!snappedX) dx += Math.round(bounds.left / gridX) * gridX - bounds.left;
                if (!snappedY) dy += Math.round(bounds.top / gridY) * gridY - bounds.top;
            }
            return { dx, dy, guides };
        }

        function showGuides(guides) {
            el.stage.querySelectorAll('.cd-guide').forEach((node) => node.remove());
            guides.forEach((guide) => el.stage.append(h('div', {
                class: `cd-guide ${guide.axis}`,
                style: guide.axis === 'x' ? { left: `${guide.at * 100}%` } : { top: `${guide.at * 100}%` },
            })));
        }

        function startMove(event, item) {
            const additive = event.shiftKey || event.ctrlKey || event.metaKey;
            if (additive) { select([item.id], { additive: true }); return; }
            if (!state.selected.includes(item.id)) select([item.id]);
            const moving = selectedElements().filter((entry) => !entry.locked);
            if (!moving.length) return;
            const before = snapshot();
            const start = stagePoint(event);
            moving.forEach((entry) => { entry._startX = entry.x; entry._startY = entry.y; });
            let moved = false;
            const onMove = (moveEvent) => {
                const point = stagePoint(moveEvent);
                let dx = point.x - start.x;
                let dy = point.y - start.y;
                if (!moved && Math.hypot(dx * point.rect.width, dy * point.rect.height) < 3) return;
                moved = true;
                if (moveEvent.shiftKey) { if (Math.abs(dx * point.rect.width) > Math.abs(dy * point.rect.height)) dy = 0; else dx = 0; }
                const snapped = moveEvent.altKey ? { dx, dy, guides: [] } : snapMove(moving, dx, dy, point.rect);
                moving.forEach((entry) => { entry.x = entry._startX + snapped.dx; entry.y = entry._startY + snapped.dy; });
                showGuides(snapped.guides);
                renderStage();
            };
            const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
                moving.forEach((entry) => { delete entry._startX; delete entry._startY; });
                showGuides([]);
                if (moved) { commit(before); render(); }
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function startResize(event, item, hx, hy) {
            const before = snapshot();
            const rect = el.stage.getBoundingClientRect();
            const angle = (item.rotation || 0) * Math.PI / 180;
            const cos = Math.cos(angle);
            const sin = Math.sin(angle);
            const start = { x: event.clientX, y: event.clientY };
            const original = { cx: (item.x + item.w / 2) * rect.width, cy: (item.y + item.h / 2) * rect.height, w: item.w * rect.width, h: item.h * rect.height };
            const keepRatio = (item.type === 'qr' || (item.type === 'photo' && item.shape === 'circle') || item.type === 'ellipse') && hx && hy;
            const onMove = (moveEvent) => {
                const dx = moveEvent.clientX - start.x;
                const dy = moveEvent.clientY - start.y;
                const localX = dx * cos + dy * sin;
                const localY = -dx * sin + dy * cos;
                let width = hx ? Math.max(6, original.w + hx * localX) : original.w;
                let height = hy ? Math.max(4, original.h + hy * localY) : original.h;
                if ((moveEvent.shiftKey || keepRatio) && hx && hy) {
                    const factor = Math.max(width / original.w, height / original.h);
                    width = original.w * factor;
                    height = original.h * factor;
                }
                const shiftX = hx * (width - original.w) / 2;
                const shiftY = hy * (height - original.h) / 2;
                const cx = original.cx + shiftX * cos - shiftY * sin;
                const cy = original.cy + shiftX * sin + shiftY * cos;
                item.w = width / rect.width;
                item.h = height / rect.height;
                item.x = (cx - width / 2) / rect.width;
                item.y = (cy - height / 2) / rect.height;
                renderStage();
            };
            const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
                commit(before);
                render();
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function startRotate(event, item) {
            const before = snapshot();
            const rect = el.stage.getBoundingClientRect();
            const center = { x: rect.left + (item.x + item.w / 2) * rect.width, y: rect.top + (item.y + item.h / 2) * rect.height };
            const onMove = (moveEvent) => {
                let angle = Math.atan2(moveEvent.clientY - center.y, moveEvent.clientX - center.x) * 180 / Math.PI + 90;
                if (moveEvent.shiftKey) angle = Math.round(angle / 15) * 15;
                else if ([0, 90, 180, 270, 360, -90].some((stop) => Math.abs(angle - stop) < 3)) angle = Math.round(angle / 90) * 90;
                angle = ((angle + 180) % 360 + 360) % 360 - 180;
                item.rotation = Math.round(angle * 10) / 10;
                renderStage();
            };
            const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
                commit(before);
                render();
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function startMarquee(event) {
            const start = stagePoint(event);
            const additive = event.shiftKey || event.ctrlKey || event.metaKey;
            const initial = additive ? [...state.selected] : [];
            const marquee = h('div', { class: 'cd-marquee' });
            el.stage.append(marquee);
            let moved = false;
            const onMove = (moveEvent) => {
                const point = stagePoint(moveEvent);
                const left = Math.min(start.x, point.x);
                const top = Math.min(start.y, point.y);
                const right = Math.max(start.x, point.x);
                const bottom = Math.max(start.y, point.y);
                moved = moved || Math.hypot((right - left) * point.rect.width, (bottom - top) * point.rect.height) > 4;
                Object.assign(marquee.style, { left: `${left * 100}%`, top: `${top * 100}%`, width: `${(right - left) * 100}%`, height: `${(bottom - top) * 100}%` });
                const hits = elements().filter((item) => !item.hidden && item.x < right && item.x + item.w > left && item.y < bottom && item.y + item.h > top).map((item) => item.id);
                state.selected = [...new Set([...initial, ...hits])];
                renderSelection();
            };
            const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
                marquee.remove();
                if (!moved && !additive) state.selected = [];
                render();
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function bindStage() {
            el.stage.addEventListener('pointerdown', (event) => {
                if (event.button !== 0) return;
                event.preventDefault();
                el.stage.focus({ preventScroll: true });
                if (state.cropping) {
                    const croppingNode = event.target.closest('.cd-element');
                    const croppingItem = findElement(state.cropping);
                    if (croppingNode?.dataset.id === state.cropping && croppingItem) return startCropPan(event, croppingItem);
                    exitCropMode({ quiet: true });
                }
                const handle = event.target.closest('.cd-handle');
                const rotate = event.target.closest('.cd-rotate');
                const item = selectedElements()[0];
                if (handle && item) return startResize(event, item, Number(handle.dataset.hx), Number(handle.dataset.hy));
                if (rotate && item) return startRotate(event, item);
                const node = event.target.closest('.cd-element');
                const target = node ? findElement(node.dataset.id) : null;
                const insideSelection = selectedElements().find((entry) => {
                    const point = stagePoint(event);
                    return point.x >= entry.x && point.x <= entry.x + entry.w && point.y >= entry.y && point.y <= entry.y + entry.h;
                });
                if (target && !(insideSelection && !(event.shiftKey || event.ctrlKey || event.metaKey))) return startMove(event, target);
                if (insideSelection) return startMove(event, insideSelection);
                return startMarquee(event);
            });
            el.stage.addEventListener('dblclick', (event) => {
                const node = event.target.closest('.cd-element');
                const item = node && findElement(node.dataset.id);
                if (!item) return;
                if (item.type === 'photo') { enterCropMode(item); return; }
                select([item.id]);
                const target = item.type === 'text' ? $('cd-prop-text') : item.type === 'image' ? null : $('cd-prop-value');
                if (item.type === 'image') { assetTarget = item.id; el.assetInput.click(); }
                target?.focus();
                target?.select?.();
            });
            el.shell.addEventListener('wheel', (event) => {
                if (state.cropping && !event.ctrlKey) {
                    event.preventDefault();
                    cropZoom(event.deltaY > 0 ? 1.05 : 0.95);
                    return;
                }
                if (!event.ctrlKey) return;
                event.preventDefault();
                setZoom((state.pxPerMm || fitPxPerMm()) * (event.deltaY > 0 ? 0.9 : 1.1));
            }, { passive: false });
            new ResizeObserver(() => { if (!el.modal.hidden) renderStage(); }).observe(el.shell);
        }

        function setZoom(pxPerMm) {
            state.zoomMode = 'manual';
            state.pxPerMm = clamp(pxPerMm, 0.8, 30);
            renderStage();
        }

        // -------------------------- acciones de objetos -------------------------- //

        function insert(type, props = {}) {
            const [widthMm, heightMm] = NEW_SIZES_MM[type];
            const w = Math.min(0.9, widthMm / design().width_mm);
            const height = Math.min(0.9, heightMm / design().height_mm);
            const count = elements().length;
            const offset = (count % 6) * 0.02;
            const item = makeElement(type, { x: clamp(0.5 - w / 2 + offset, 0, 1 - w), y: clamp(0.5 - height / 2 + offset, 0, 1 - height), w, h: height, ...props });
            if (type === 'image' && !item.asset) item.asset = state.assets[0]?.asset_id || null;
            change(() => elements().push(item));
            select([item.id]);
            return item;
        }

        function removeSelected() {
            const ids = new Set(selectedElements().filter((item) => !item.locked).map((item) => item.id));
            if (!ids.size) return;
            change(() => { side().elements = elements().filter((item) => !ids.has(item.id)); });
            state.selected = [];
            render();
        }

        function duplicateSelected() {
            const copies = selectedElements().map((item) => ({ ...clone(item), id: newId(), x: item.x + 2 / design().width_mm, y: item.y + 2 / design().height_mm, locked: false }));
            if (!copies.length) return;
            change(() => elements().push(...copies));
            select(copies.map((item) => item.id));
        }

        function copySelected() {
            state.clipboard = clone(selectedElements());
            if (state.clipboard.length) host.setStatus(`${state.clipboard.length} objeto${state.clipboard.length === 1 ? '' : 's'} copiado${state.clipboard.length === 1 ? '' : 's'}.`);
        }

        function paste() {
            if (!state.clipboard.length) return;
            const copies = state.clipboard.map((item) => ({ ...clone(item), id: newId(), x: item.x + 2 / design().width_mm, y: item.y + 2 / design().height_mm }));
            state.clipboard = clone(copies);
            change(() => elements().push(...copies));
            select(copies.map((item) => item.id));
        }

        function reorder(mode) {
            const ids = new Set(state.selected);
            if (!ids.size) return;
            change(() => {
                const list = elements();
                const chosen = list.filter((item) => ids.has(item.id));
                const rest = list.filter((item) => !ids.has(item.id));
                if (mode === 'front') side().elements = [...rest, ...chosen];
                else if (mode === 'back') side().elements = [...chosen, ...rest];
                else {
                    const step = mode === 'forward' ? 1 : -1;
                    const indexes = list.map((item, index) => (ids.has(item.id) ? index : -1)).filter((index) => index >= 0);
                    (step > 0 ? indexes.reverse() : indexes).forEach((index) => {
                        const target = index + step;
                        if (target < 0 || target >= list.length || ids.has(list[target].id)) return;
                        [list[index], list[target]] = [list[target], list[index]];
                    });
                }
            });
        }

        function align(mode) {
            const items = selectedElements().filter((item) => !item.locked);
            if (!items.length) return;
            const reference = items.length > 1 ? boundsOf(items) : { left: 0, top: 0, right: 1, bottom: 1, width: 1, height: 1 };
            change(() => items.forEach((item) => {
                if (mode === 'left') item.x = reference.left;
                if (mode === 'hcenter') item.x = reference.left + (reference.width - item.w) / 2;
                if (mode === 'right') item.x = reference.right - item.w;
                if (mode === 'top') item.y = reference.top;
                if (mode === 'vcenter') item.y = reference.top + (reference.height - item.h) / 2;
                if (mode === 'bottom') item.y = reference.bottom - item.h;
            }));
        }

        function distribute(axis) {
            const items = selectedElements().filter((item) => !item.locked);
            if (items.length < 3) return host.setStatus('Seleccioná al menos tres objetos para distribuir.', 'error');
            const position = axis === 'x' ? 'x' : 'y';
            const size = axis === 'x' ? 'w' : 'h';
            const sorted = [...items].sort((a, b) => a[position] - b[position]);
            const first = sorted[0];
            const last = sorted[sorted.length - 1];
            const total = sorted.reduce((sum, item) => sum + item[size], 0);
            const gap = (last[position] + last[size] - first[position] - total) / (sorted.length - 1);
            change(() => {
                let cursor = first[position];
                sorted.forEach((item) => { item[position] = cursor; cursor += item[size] + gap; });
            });
        }

        function nudge(dx, dy) {
            const items = selectedElements().filter((item) => !item.locked);
            if (!items.length) return;
            change(() => items.forEach((item) => { item.x += dx / design().width_mm; item.y += dy / design().height_mm; }), { panel: false });
            renderProperties();
        }

        // ------------------------------ documento ------------------------------ //

        function resizeCard(widthMm, heightMm, { keepPhysical }) {
            const old = { w: design().width_mm, h: design().height_mm };
            if (!(widthMm >= 20 && widthMm <= 320 && heightMm >= 20 && heightMm <= 320)) return host.setStatus('El tamaño debe estar entre 20 y 320 mm.', 'error');
            change(() => {
                design().width_mm = Math.round(widthMm * 100) / 100;
                design().height_mm = Math.round(heightMm * 100) / 100;
                ['front', 'back'].forEach((key) => design()[key].elements.forEach((item) => {
                    if (keepPhysical) {
                        // Mantiene medidas físicas y la posición relativa del centro.
                        const cx = item.x + item.w / 2;
                        const cy = item.y + item.h / 2;
                        item.w = item.w * old.w / widthMm;
                        item.h = item.h * old.h / heightMm;
                        item.x = cx - item.w / 2;
                        item.y = cy - item.h / 2;
                    } else {
                        const factor = Math.min(widthMm / old.w, heightMm / old.h);
                        ['size', 'stroke_width', 'radius', 'padding'].forEach((key2) => { if (typeof item[key2] === 'number') item[key2] = Math.round(item[key2] * factor * 100) / 100; });
                    }
                }));
            });
        }

        function applyTemplate(template) {
            const sideHasContent = elements().length > 0;
            if (sideHasContent && !window.confirm(`¿Reemplazar los objetos del ${state.side === 'front' ? 'frente' : 'dorso'} por la plantilla “${template.label}”?`)) return;
            const accent = $('cd-template-color').value || '#176b87';
            const logo = state.assets.find((asset) => asset.asset_id === 'logo')?.asset_id || state.assets[0]?.asset_id || null;
            change(() => {
                if (template.orientation !== 'any') {
                    const isPortrait = design().height_mm > design().width_mm;
                    if ((template.orientation === 'portrait') !== isPortrait) {
                        [design().width_mm, design().height_mm] = [design().height_mm, design().width_mm];
                    }
                }
                state.design[state.side] = template.build({ accent, logo, fields: guessFields(host.getHeaders()) });
            });
            state.selected = [];
            render();
        }

        // ------------------------------ recursos ------------------------------ //

        async function uploadAsset(file) {
            if (!file) return null;
            host.setBusy(true);
            try {
                const sessionId = await host.ensureSession();
                const response = await host.api(`/sessions/${sessionId}/assets?filename=${encodeURIComponent(file.name)}`, {
                    method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
                });
                const asset = await response.json();
                state.assets.push(asset);
                host.setStatus(`Imagen “${asset.filename}” agregada al diseño.`);
                return asset;
            } catch (error) {
                host.setStatus(error.message, 'error');
                return null;
            } finally {
                host.setBusy(false);
            }
        }

        async function handleAssetInput() {
            const file = el.assetInput.files[0];
            el.assetInput.value = '';
            const asset = await uploadAsset(file);
            if (!asset) return;
            if (assetTarget === '__background__') {
                change(() => { side().background_image = asset.asset_id; });
            } else if (assetTarget && findElement(assetTarget)) {
                change(() => { findElement(assetTarget).asset = asset.asset_id; });
            } else if (assetTarget === '__insert__') {
                insert('image', { asset: asset.asset_id });
            } else {
                render();
            }
            assetTarget = null;
        }

        // --------------------------- paneles laterales --------------------------- //

        function renderTemplates() {
            el.templates.replaceChildren(...TEMPLATES.map((template) => h('button', {
                class: 'cd-template', type: 'button', title: template.label, onclick: () => applyTemplate(template),
            }, [h('span', { class: `cd-template-thumb ${template.thumb}` }), h('strong', { text: template.label })])));
        }

        function renderDocumentControls() {
            const preset = SIZE_PRESETS.find((item) => item.w && ((Math.abs(item.w - design().width_mm) < 0.05 && Math.abs(item.h - design().height_mm) < 0.05) || (Math.abs(item.h - design().width_mm) < 0.05 && Math.abs(item.w - design().height_mm) < 0.05)));
            $('cd-size-preset').value = preset?.id || 'custom';
            $('cd-width-mm').value = design().width_mm;
            $('cd-height-mm').value = design().height_mm;
            const portrait = design().height_mm > design().width_mm;
            $('cd-orient-landscape').classList.toggle('active', !portrait);
            $('cd-orient-portrait').classList.toggle('active', portrait);
            $('cd-double-sided').checked = design().double_sided;
            $('cd-snap').checked = state.snapGrid;
            $('cd-guides').checked = state.smartGuides;
            $('cd-safe').checked = state.showSafe;
        }

        function renderSideTabs() {
            document.querySelectorAll('[data-cd-side]').forEach((button) => {
                button.classList.toggle('active', button.dataset.cdSide === state.side);
                button.disabled = button.dataset.cdSide === 'back' && !design().double_sided;
            });
        }

        function renderAssets() {
            const items = state.assets.map((asset) => h('button', {
                class: 'cd-asset', type: 'button', title: `Insertar ${asset.filename}`, onclick: () => insert('image', { asset: asset.asset_id }),
            }, [h('img', { src: asset.url, alt: '' }), h('span', { text: asset.filename })]));
            if (!items.length) items.push(h('p', { class: 'field-note', text: 'Cargá logos, firmas, sellos o fondos para usarlos en cualquier cara.' }));
            el.assets.replaceChildren(...items);
        }

        function renderLayers() {
            const list = [...elements()].reverse();
            const rows = list.map((item) => {
                const label = item.name || (item.type === 'text' ? (item.text || 'Texto').slice(0, 28) : TYPE_LABELS[item.type]);
                return h('div', {
                    class: `cd-layer${state.selected.includes(item.id) ? ' selected' : ''}${item.hidden ? ' is-hidden' : ''}`,
                    onclick: (event) => select([item.id], { additive: event.shiftKey || event.ctrlKey || event.metaKey }),
                }, [
                    h('span', { class: 'cd-layer-icon', text: TYPE_ICONS[item.type] }),
                    h('span', { class: 'cd-layer-name', text: label, title: label }),
                    item.condition && item.condition.op !== 'always' ? h('span', { class: 'cd-layer-flag', title: 'Visible con condición', text: 'ƒ' }) : null,
                    h('button', {
                        type: 'button', class: `cd-layer-btn${item.hidden ? ' on' : ''}`, title: item.hidden ? 'Mostrar' : 'Ocultar', text: item.hidden ? '◌' : '◉',
                        onclick: (event) => { event.stopPropagation(); change(() => { item.hidden = !item.hidden; }); },
                    }),
                    h('button', {
                        type: 'button', class: `cd-layer-btn${item.locked ? ' on' : ''}`, title: item.locked ? 'Desbloquear' : 'Bloquear', text: item.locked ? '🔒' : '🔓',
                        onclick: (event) => { event.stopPropagation(); change(() => { item.locked = !item.locked; }); },
                    }),
                ]);
            });
            if (!rows.length) rows.push(h('p', { class: 'field-note', text: 'Esta cara no tiene objetos. Usá la barra Insertar o una plantilla.' }));
            el.layers.replaceChildren(...rows);
        }

        // ------------------------------ propiedades ------------------------------ //

        function control(label, input, { wide = false, note = null } = {}) {
            return h('div', { class: `cd-control${wide ? ' wide' : ''}` }, [h('span', { text: label }), input, note ? h('small', { text: note }) : null]);
        }

        function bindLive(input, apply, { event = 'input' } = {}) {
            input.addEventListener(event, () => { apply(input); state.pristine = false; renderStage(); renderLayers(); host.onDesignChanged(); });
            return input;
        }

        function numberInput(value, { min, max, step = 0.1 }, apply) {
            const input = h('input', { type: 'number', value: String(Math.round(value * 100) / 100), min, max, step });
            return bindLive(input, () => {
                const number = Number(input.value);
                if (Number.isFinite(number) && input.value !== '') apply(clamp(number, min ?? -Infinity, max ?? Infinity));
            });
        }

        function selectInput(options, value, apply) {
            const input = h('select', {}, options.map(([optionValue, label]) => h('option', { value: optionValue, text: label })));
            input.value = value ?? options[0][0];
            return bindLive(input, () => apply(input.value), { event: 'change' });
        }

        function colorInput(value, apply, { optional = false } = {}) {
            const picker = h('input', { type: 'color', value: value || '#ffffff' });
            const wrap = h('div', { class: 'cd-color' }, [picker]);
            if (optional) {
                const toggle = h('input', { type: 'checkbox', checked: Boolean(value), title: 'Usar color' });
                picker.disabled = !value;
                bindLive(toggle, () => { picker.disabled = !toggle.checked; apply(toggle.checked ? picker.value : null); }, { event: 'change' });
                wrap.prepend(toggle);
                bindLive(picker, () => { if (toggle.checked) apply(picker.value); });
            } else {
                bindLive(picker, () => apply(picker.value));
            }
            return wrap;
        }

        function toggleButton(label, title, active, apply) {
            const button = h('button', { type: 'button', class: `cd-toggle${active ? ' active' : ''}`, title, text: label });
            button.addEventListener('click', () => change(() => apply(!button.classList.contains('active')), { panel: true }));
            return button;
        }

        function fieldPicker(onPick) {
            const names = [...BUILTIN_FIELDS, ...fieldNames()];
            const input = h('select', { class: 'cd-field-picker', title: 'Insertar campo' }, [
                h('option', { value: '', text: '＋ Campo…' }),
                ...names.map((name) => h('option', { value: name, text: `{${name}}` })),
            ]);
            input.addEventListener('change', (event) => {
                event.stopPropagation();
                if (input.value) onPick(`{${input.value}}`);
                input.value = '';
            });
            return input;
        }

        function insertAtCursor(input, token, apply) {
            const start = input.selectionStart ?? input.value.length;
            const end = input.selectionEnd ?? input.value.length;
            const before = snapshot();
            input.value = `${input.value.slice(0, start)}${token}${input.value.slice(end)}`;
            apply(input.value);
            commit(before);
            renderStage();
            renderLayers();
            input.focus();
            input.setSelectionRange(start + token.length, start + token.length);
        }

        function fontControl(item) {
            const search = h('input', { type: 'search', placeholder: 'Buscar fuente…', class: 'cd-font-search' });
            const select = h('select', {});
            const fill = () => {
                const query = search.value.trim().toLocaleLowerCase('es');
                const fonts = [
                    { id: 'sans', label: 'Sans serif (Arial)', css_family: 'Arial' },
                    { id: 'serif', label: 'Serif (Georgia)', css_family: 'Georgia' },
                    { id: 'mono', label: 'Monoespaciada', css_family: 'Consolas' },
                    ...host.getSystemFonts(),
                ].filter((font) => !query || font.label.toLocaleLowerCase('es').includes(query) || font.id === item.font);
                select.replaceChildren(...fonts.slice(0, 400).map((font) => h('option', { value: font.id, text: font.label, style: { fontFamily: `"${font.css_family}", sans-serif` } })));
                select.value = item.font;
            };
            fill();
            search.addEventListener('input', fill);
            bindLive(select, () => { item.font = select.value; }, { event: 'change' });
            return h('div', { class: 'cd-font' }, [search, select]);
        }

        function geometrySection(item) {
            const W = design().width_mm;
            const H = design().height_mm;
            const disabled = item.locked;
            const grid = h('div', { class: 'cd-grid4' }, [
                control('X mm', numberInput(item.x * W, { step: 0.5 }, (value) => { item.x = value / W; })),
                control('Y mm', numberInput(item.y * H, { step: 0.5 }, (value) => { item.y = value / H; })),
                control('Ancho mm', numberInput(item.w * W, { min: 0.5, max: 400, step: 0.5 }, (value) => { item.w = value / W; })),
                control('Alto mm', numberInput(item.h * H, { min: 0.5, max: 400, step: 0.5 }, (value) => { item.h = value / H; })),
                control('Giro °', numberInput(item.rotation || 0, { min: -180, max: 180, step: 1 }, (value) => { item.rotation = value; })),
                control('Opacidad %', numberInput((item.opacity ?? 1) * 100, { min: 0, max: 100, step: 5 }, (value) => { item.opacity = value / 100; })),
            ]);
            grid.querySelectorAll('input').forEach((input) => { input.disabled = disabled; });
            return h('section', { class: 'cd-section' }, [
                h('div', { class: 'cd-section-title', text: 'Posición y tamaño' }),
                grid,
                h('div', { class: 'cd-button-row' }, [
                    h('button', { class: 'btn secondary compact', type: 'button', text: '↔ Centrar', disabled, onclick: () => change(() => { item.x = (1 - item.w) / 2; }) }),
                    h('button', { class: 'btn secondary compact', type: 'button', text: '↕ Centrar', disabled, onclick: () => change(() => { item.y = (1 - item.h) / 2; }) }),
                    h('button', { class: 'btn secondary compact', type: 'button', text: '⟲ 0°', disabled, onclick: () => change(() => { item.rotation = 0; }) }),
                ]),
            ]);
        }

        function frameControls(item, { shape = false } = {}) {
            return [
                shape ? control('Forma', selectInput([['rect', 'Rectangular'], ['circle', 'Circular / oval']], item.shape, (value) => { item.shape = value; renderProperties(); })) : null,
                item.shape === 'circle' && item.type === 'photo' ? null : control('Radio esquinas pt', numberInput(item.radius || 0, { min: 0, max: 200, step: 0.5 }, (value) => { item.radius = value; })),
                control('Borde', colorInput(item.stroke_color, (value) => { item.stroke_color = value; }, { optional: true })),
                control('Grosor borde pt', numberInput(item.stroke_width || 0, { min: 0, max: 40, step: 0.25 }, (value) => { item.stroke_width = value; })),
            ];
        }

        function typeSection(item) {
            const children = [];
            const title = { text: 'Texto', photo: 'Fotografía', image: 'Imagen', qr: 'Código QR', barcode: 'Código de barras', rect: 'Forma', ellipse: 'Forma', line: 'Línea' }[item.type];
            if (item.type === 'text') {
                const area = h('textarea', { id: 'cd-prop-text', rows: 3, maxlength: 1000, spellcheck: true });
                area.value = item.text;
                bindLive(area, () => { item.text = area.value; });
                children.push(
                    h('div', { class: 'cd-label-row' }, [h('span', { text: 'Contenido' }), fieldPicker((token) => insertAtCursor(area, token, (value) => { item.text = value; }))]),
                    area,
                    h('small', { class: 'cd-hint', text: 'Combiná texto fijo y campos: “{Nombre} {Apellido}”. Enter agrega una línea.' }),
                    control('Tipografía', fontControl(item), { wide: true }),
                    h('div', { class: 'cd-grid2' }, [
                        control('Tamaño pt', numberInput(item.size, { min: 2, max: 300, step: 0.5 }, (value) => { item.size = value; })),
                        control('Color', colorInput(item.color, (value) => { item.color = value; })),
                    ]),
                    h('div', { class: 'cd-toolbar-row' }, [
                        toggleButton('B', 'Negrita', item.bold, (value) => { item.bold = value; }),
                        toggleButton('I', 'Cursiva', item.italic, (value) => { item.italic = value; }),
                        toggleButton('U', 'Subrayado', item.underline, (value) => { item.underline = value; }),
                        toggleButton('AA', 'Mayúsculas', item.uppercase, (value) => { item.uppercase = value; }),
                        h('span', { class: 'cd-sep' }),
                        ...[['left', '⇤'], ['center', '↔'], ['right', '⇥']].map(([value, label]) => toggleButton(label, `Alinear ${value === 'left' ? 'a la izquierda' : value === 'center' ? 'al centro' : 'a la derecha'}`, item.align === value, () => { item.align = value; })),
                        h('span', { class: 'cd-sep' }),
                        ...[['top', '⤒'], ['middle', '≡'], ['bottom', '⤓']].map(([value, label]) => toggleButton(label, `Vertical: ${value === 'top' ? 'arriba' : value === 'middle' ? 'medio' : 'abajo'}`, item.valign === value, () => { item.valign = value; })),
                    ]),
                    control('Ajuste del texto', selectInput([
                        ['shrink', 'Una línea · achicar si no entra'], ['wrap_shrink', 'Varias líneas · achicar si no entra'],
                        ['wrap', 'Varias líneas · tamaño fijo'], ['none', 'Una línea · tamaño fijo'],
                    ], item.fit, (value) => { item.fit = value; }), { wide: true }),
                    h('div', { class: 'cd-grid2' }, [
                        control('Interlineado', numberInput(item.line_height || 1.15, { min: 0.6, max: 3, step: 0.05 }, (value) => { item.line_height = value; })),
                        control('Margen interno pt', numberInput(item.padding || 0, { min: 0, max: 50, step: 0.5 }, (value) => { item.padding = value; })),
                        control('Fondo', colorInput(item.fill, (value) => { item.fill = value; }, { optional: true })),
                        control('Radio fondo pt', numberInput(item.radius || 0, { min: 0, max: 200, step: 0.5 }, (value) => { item.radius = value; })),
                        control('Contorno', colorInput(item.stroke_color, (value) => { item.stroke_color = value; }, { optional: true })),
                        control('Grosor contorno pt', numberInput(item.stroke_width || 0, { min: 0, max: 10, step: 0.1 }, (value) => { item.stroke_width = value; })),
                    ]),
                );
            } else if (item.type === 'photo' || item.type === 'image') {
                if (item.type === 'image') {
                    const options = [['', 'Sin imagen'], ...state.assets.map((asset) => [asset.asset_id, asset.filename])];
                    children.push(control('Imagen', selectInput(options, item.asset || '', (value) => { item.asset = value || null; }), { wide: true }));
                    children.push(h('button', { class: 'btn secondary compact wide', type: 'button', text: 'Cargar otra imagen…', onclick: () => { assetTarget = item.id; el.assetInput.click(); } }));
                } else {
                    children.push(h('small', { class: 'cd-hint', text: 'Muestra la foto recortada de cada persona.' }));
                }
                children.push(h('div', { class: 'cd-grid2' }, [
                    control('Encaje', selectInput([['cover', 'Rellenar (recorta)'], ['contain', 'Contener completa'], ['stretch', 'Estirar']], item.image_fit, (value) => { item.image_fit = value; })),
                    ...frameControls(item, { shape: item.type === 'photo' }),
                ]));
                const gray = h('input', { type: 'checkbox', checked: Boolean(item.grayscale) });
                bindLive(gray, () => { item.grayscale = gray.checked; }, { event: 'change' });
                children.push(h('label', { class: 'designer-check' }, [gray, h('span', { text: 'Blanco y negro' })]));
            } else if (item.type === 'qr' || item.type === 'barcode') {
                const input = h('input', { id: 'cd-prop-value', type: 'text', maxlength: 1000 });
                input.value = item.value;
                bindLive(input, () => { item.value = input.value; });
                children.push(
                    h('div', { class: 'cd-label-row' }, [h('span', { text: 'Contenido' }), fieldPicker((token) => insertAtCursor(input, token, (value) => { item.value = value; }))]),
                    input,
                );
                if (item.type === 'barcode') {
                    children.push(control('Tipo', selectInput(BARCODE_TYPES, item.symbology, (value) => { item.symbology = value; }), { wide: true }));
                    if (['ean13', 'ean8', 'upca', 'itf'].includes(item.symbology)) children.push(h('small', { class: 'cd-hint', text: 'Este tipo admite sólo números (EAN-13: 12 dígitos, EAN-8: 7, UPC-A: 11).' }));
                    const showText = h('input', { type: 'checkbox', checked: Boolean(item.show_text) });
                    bindLive(showText, () => { item.show_text = showText.checked; }, { event: 'change' });
                    children.push(h('label', { class: 'designer-check' }, [showText, h('span', { text: 'Mostrar texto legible' })]));
                } else {
                    children.push(control('Corrección de errores', selectInput([['L', 'Baja · 7%'], ['M', 'Media · 15%'], ['Q', 'Alta · 25%'], ['H', 'Máxima · 30%']], item.ecc, (value) => { item.ecc = value; }), { wide: true }));
                }
                children.push(h('div', { class: 'cd-grid2' }, [
                    control('Color', colorInput(item.color, (value) => { item.color = value; })),
                    control('Fondo', colorInput(item.background, (value) => { item.background = value; }, { optional: true })),
                ]));
            } else if (item.type === 'rect' || item.type === 'ellipse') {
                children.push(h('div', { class: 'cd-grid2' }, [
                    control('Relleno', colorInput(item.fill, (value) => { item.fill = value; }, { optional: true })),
                    ...frameControls(item).filter((node) => node && !(item.type === 'ellipse' && node.textContent.startsWith('Radio'))),
                ]));
            } else if (item.type === 'line') {
                children.push(h('div', { class: 'cd-grid2' }, [
                    control('Color', colorInput(item.stroke_color, (value) => { item.stroke_color = value; })),
                    control('Grosor pt', numberInput(item.stroke_width || 1, { min: 0.1, max: 40, step: 0.25 }, (value) => { item.stroke_width = value; })),
                ]));
            }
            return h('section', { class: 'cd-section' }, [h('div', { class: 'cd-section-title', text: title }), ...children]);
        }

        function conditionSection(item) {
            const condition = item.condition || { op: 'always', field: '', value: '' };
            const update = (patch) => {
                const next = { ...condition, ...patch };
                item.condition = next.op === 'always' ? null : next;
            };
            const fields = [...BUILTIN_FIELDS, ...fieldNames()];
            const children = [control('Mostrar', selectInput(CONDITION_OPS, condition.op, (value) => { update({ op: value, field: condition.field || fields[fields.length - 1] || '' }); renderProperties(); }), { wide: true })];
            if (condition.op && condition.op !== 'always') {
                children.push(control('Campo', selectInput(fields.map((name) => [name, name]), condition.field, (value) => { update({ field: value }); condition.field = value; }), { wide: true }));
                if (!['empty', 'not_empty'].includes(condition.op)) {
                    const value = h('input', { type: 'text', maxlength: 200 });
                    value.value = condition.value || '';
                    bindLive(value, () => { update({ value: value.value }); condition.value = value.value; });
                    children.push(control('Valor', value, { wide: true }));
                }
                children.push(h('small', { class: 'cd-hint', text: 'En el editor los objetos que no se imprimen para esta persona se ven atenuados.' }));
            }
            return h('section', { class: 'cd-section' }, [h('div', { class: 'cd-section-title', text: 'Visibilidad condicional' }), ...children]);
        }

        function sidePropertiesSection() {
            const current = side();
            const options = [['', 'Sin imagen'], ...state.assets.map((asset) => [asset.asset_id, asset.filename])];
            const colors = new Set();
            ['front', 'back'].forEach((key) => {
                colors.add(design()[key].background_color);
                design()[key].elements.forEach((item) => ['color', 'fill', 'stroke_color', 'background'].forEach((prop) => { if (item[prop]) colors.add(item[prop].toLowerCase()); }));
            });
            const from = h('select', {}, [...colors].map((color) => h('option', { value: color, text: color, style: { background: color } })));
            const to = h('input', { type: 'color', value: '#176b87' });
            return [
                h('section', { class: 'cd-section' }, [
                    h('div', { class: 'cd-section-title', text: state.side === 'front' ? 'Fondo del frente' : 'Fondo del dorso' }),
                    h('div', { class: 'cd-grid2' }, [
                        control('Color', colorInput(current.background_color, (value) => { current.background_color = value; })),
                        control('Imagen', selectInput(options, current.background_image || '', (value) => { current.background_image = value || null; })),
                    ]),
                    h('button', { class: 'btn secondary compact wide', type: 'button', text: 'Cargar imagen de fondo…', onclick: () => { assetTarget = '__background__'; el.assetInput.click(); } }),
                    h('small', { class: 'cd-hint', text: 'La imagen se recorta para cubrir la tarjeta completa. Usá 1011×638 px (300 dpi) o más.' }),
                ]),
                h('section', { class: 'cd-section' }, [
                    h('div', { class: 'cd-section-title', text: 'Reemplazar color en todo el diseño' }),
                    h('div', { class: 'cd-grid2' }, [control('Color actual', from), control('Nuevo color', to)]),
                    h('button', {
                        class: 'btn secondary compact wide', type: 'button', text: 'Reemplazar',
                        onclick: () => change(() => ['front', 'back'].forEach((key) => {
                            const sideData = design()[key];
                            if (sideData.background_color.toLowerCase() === from.value) sideData.background_color = to.value;
                            sideData.elements.forEach((item) => ['color', 'fill', 'stroke_color', 'background'].forEach((prop) => { if (item[prop] && item[prop].toLowerCase() === from.value) item[prop] = to.value; }));
                        })),
                    }),
                ]),
                h('section', { class: 'cd-section cd-shortcuts' }, [
                    h('div', { class: 'cd-section-title', text: 'Atajos' }),
                    h('p', { class: 'field-note', text: 'Clic + Mayús: selección múltiple · Arrastrar en vacío: seleccionar área · Flechas: mover 0,5 mm (Mayús: 5 mm) · Ctrl+D duplicar · Ctrl+C / Ctrl+V · Supr eliminar · Ctrl+Z / Ctrl+Y · Alt al arrastrar: sin imán · Ctrl+rueda: zoom' }),
                ]),
            ];
        }

        function renderProperties() {
            const items = selectedElements();
            const title = $('cd-properties-title');
            if (!items.length) {
                title.textContent = state.side === 'front' ? 'Frente' : 'Dorso';
                el.properties.replaceChildren(...sidePropertiesSection());
                return;
            }
            if (items.length > 1) {
                title.textContent = `${items.length} objetos`;
                el.properties.replaceChildren(h('section', { class: 'cd-section' }, [
                    h('p', { class: 'field-note', text: 'Usá la barra superior para alinear, distribuir u ordenar la selección. Las flechas mueven todos los objetos juntos.' }),
                    control('Opacidad %', numberInput((items[0].opacity ?? 1) * 100, { min: 0, max: 100, step: 5 }, (value) => items.forEach((item) => { item.opacity = value / 100; })), { wide: true }),
                    h('div', { class: 'cd-button-row' }, [
                        h('button', { class: 'btn secondary compact', type: 'button', text: '🔒 Bloquear', onclick: () => change(() => items.forEach((item) => { item.locked = true; })) }),
                        h('button', { class: 'btn secondary compact', type: 'button', text: '🔓 Desbloquear', onclick: () => change(() => items.forEach((item) => { item.locked = false; })) }),
                    ]),
                ]));
                return;
            }
            const item = items[0];
            title.textContent = TYPE_LABELS[item.type];
            const name = h('input', { type: 'text', maxlength: 80, placeholder: TYPE_LABELS[item.type] });
            name.value = item.name || '';
            bindLive(name, () => { item.name = name.value; });
            el.properties.replaceChildren(
                h('section', { class: 'cd-section' }, [control('Nombre del objeto', name, { wide: true })]),
                item.type === 'photo' ? framingSection(item) : null,
                typeSection(item),
                geometrySection(item),
                conditionSection(item),
                h('section', { class: 'cd-section' }, [h('div', { class: 'cd-button-row' }, [
                    h('button', { class: 'btn secondary compact', type: 'button', text: item.locked ? '🔒 Desbloquear' : '🔓 Bloquear', onclick: () => change(() => { item.locked = !item.locked; }) }),
                    h('button', { class: 'btn secondary compact', type: 'button', text: '⧉ Duplicar', onclick: duplicateSelected }),
                    h('button', { class: 'btn secondary compact danger-outline', type: 'button', text: '🗑 Eliminar', disabled: item.locked, onclick: removeSelected }),
                ])]),
            );
        }

        function renderRecordData() {
            const photo = host.getCurrentPhoto();
            const fields = fieldNames();
            const children = [];
            if (!photo) {
                children.push(h('p', { class: 'field-note', text: 'Agregá fotos al lote para completar los datos de cada credencial.' }));
            } else {
                children.push(h('p', { class: 'field-note', text: `Datos de ${photo.filename}. Los cambios se aplican sólo a esta credencial.` }));
                fields.forEach((field) => {
                    const input = h('input', { type: 'text', maxlength: 500 });
                    input.value = photo.metadata?.[field] ?? '';
                    input.addEventListener('input', () => {
                        photo.metadata = { ...(photo.metadata || {}), [field]: input.value };
                        renderStage();
                        host.onRecordChanged(photo);
                    });
                    children.push(control(field, input, { wide: true }));
                });
                if (!fields.length) children.push(h('p', { class: 'field-note', text: 'Todavía no hay campos. Importá una planilla o creá un campo propio.' }));
            }
            children.push(h('button', {
                class: 'btn secondary compact wide', type: 'button', text: '＋ Nuevo campo', onclick: () => {
                    const name = (window.prompt('Nombre del nuevo campo (ej.: Legajo, Sector, Vencimiento):') || '').trim().replace(/[{}]/g, '');
                    if (!name) return;
                    if (fieldNames().includes(name) || BUILTIN_FIELDS.includes(name)) return host.setStatus('Ese campo ya existe.', 'error');
                    change(() => state.customFields.push(name));
                },
            }));
            el.recordData.replaceChildren(...children);
        }

        function renderRecordSelect() {
            const photos = host.getPhotos();
            const current = host.getCurrentPhoto();
            const fields = guessFields(host.getHeaders());
            el.record.replaceChildren(...(photos.length ? photos.map((photo, index) => {
                const label = resolveFields(fields.name, valuesFor(photo)).trim() || photo.filename;
                return h('option', { value: photo.id, text: `${index + 1}. ${label}` });
            }) : [h('option', { value: '', text: 'Sin fotos en el lote' })]));
            el.record.value = current?.id || '';
            el.record.disabled = !photos.length;
            $('cd-record-prev').disabled = !photos.length;
            $('cd-record-next').disabled = !photos.length;
        }

        function stepRecord(delta) {
            const photos = host.getPhotos();
            if (!photos.length) return;
            const index = photos.indexOf(host.getCurrentPhoto());
            const target = photos[(index + delta + photos.length) % photos.length];
            host.selectPhoto(target.id);
        }

        function updateToolbar() {
            $('cd-undo').disabled = !state.history.length;
            $('cd-redo').disabled = !state.future.length;
            const hasSelection = state.selected.length > 0;
            document.querySelectorAll('[data-cd-needs-selection]').forEach((button) => { button.disabled = !hasSelection; });
            document.querySelectorAll('[data-cd-needs-multi]').forEach((button) => { button.disabled = state.selected.length < Number(button.dataset.cdNeedsMulti); });
        }

        // --------------------------- encuadre de la foto --------------------------- //

        function enterCropMode(item) {
            const photo = host.getCurrentPhoto();
            if (!photo) return host.setStatus('Agregá fotos al lote para encuadrarlas.', 'error');
            state.cropping = item.id;
            state.selected = [item.id];
            el.shell.parentElement.querySelector('.cd-crop-banner')?.remove();
            el.shell.parentElement.append(h('div', { class: 'cd-crop-banner' }, [
                h('span', { text: `Encuadre de ${photo.filename}: arrastrá para mover · rueda para acercar o alejar · flechas para ajustar` }),
                h('button', { class: 'btn compact', type: 'button', text: 'Listo', onclick: () => exitCropMode() }),
            ]));
            render();
        }

        function exitCropMode({ quiet = false } = {}) {
            if (!state.cropping) return;
            state.cropping = null;
            el.shell.parentElement.querySelector('.cd-crop-banner')?.remove();
            const photo = host.getCurrentPhoto();
            if (photo) host.onCropCommitted(photo);
            if (!quiet) render();
        }

        function cropScale(item, rect, photo) {
            const width = item.w * rect.width;
            const height = item.h * rect.height;
            const cropWidth = photo.crop[2] - photo.crop[0];
            const cropHeight = photo.crop[3] - photo.crop[1];
            return item.image_fit === 'contain' ? Math.min(width / cropWidth, height / cropHeight) : Math.max(width / cropWidth, height / cropHeight);
        }

        let cropFrame = null;
        function refreshCropPreview() {
            if (cropFrame) return;
            cropFrame = requestAnimationFrame(() => { cropFrame = null; renderStage(); });
        }

        function startCropPan(event, item) {
            const photo = host.getCurrentPhoto();
            if (!photo) return;
            const rect = el.stage.getBoundingClientRect();
            const angle = (item.rotation || 0) * Math.PI / 180;
            let last = { x: event.clientX, y: event.clientY };
            const onMove = (moveEvent) => {
                const dx = moveEvent.clientX - last.x;
                const dy = moveEvent.clientY - last.y;
                last = { x: moveEvent.clientX, y: moveEvent.clientY };
                const localX = dx * Math.cos(angle) + dy * Math.sin(angle);
                const localY = -dx * Math.sin(angle) + dy * Math.cos(angle);
                const scale = cropScale(item, rect, photo);
                host.adjustCrop(photo, { dx: -localX / scale, dy: -localY / scale });
                refreshCropPreview();
            };
            const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function cropZoom(factor) {
            const photo = host.getCurrentPhoto();
            if (!photo) return;
            host.adjustCrop(photo, { scale: factor });
            refreshCropPreview();
        }

        function cropNudge(dx, dy) {
            const photo = host.getCurrentPhoto();
            if (!photo) return;
            const width = photo.crop[2] - photo.crop[0];
            host.adjustCrop(photo, { dx: dx * width * 0.02, dy: dy * width * 0.02 });
            refreshCropPreview();
        }

        function framingDefaults(item) {
            // Círculo: rostro más grande y centrado. Rectángulo: criterio de foto carné.
            return item.shape === 'circle' ? { fill: 0.56, eyes: 44 } : { fill: 0.6, eyes: 40 };
        }

        function framingSection(item) {
            const W = design().width_mm;
            const H = design().height_mm;
            const boxRatio = (item.w * W) / (item.h * H);
            const cropRatio = host.getCropRatio();
            const loss = 1 - Math.min(boxRatio / cropRatio, cropRatio / boxRatio);
            const defaults = framingDefaults(item);
            const fill = item.frame_fill ?? defaults.fill;
            const eyes = item.frame_eyes ?? defaults.eyes;
            const format = (value) => value.toLocaleString('es-UY', { maximumFractionDigits: 2 });
            const params = () => ({ ratio: boxRatio, faceFill: item.frame_fill ?? defaults.fill, eyePosition: item.frame_eyes ?? defaults.eyes });

            const preview = async () => {
                const photo = host.getCurrentPhoto();
                if (!photo) return;
                await host.autoFrame({ ...params(), photoIds: [photo.id], quiet: true });
                host.setStatus('Vista previa del encuadre en esta credencial. Aplicalo a todas cuando te convenza.');
                render();
            };
            const slider = (label, value, min, max, step, unit, apply) => {
                const output = h('output', { text: `${Math.round(value)}${unit}` });
                const input = h('input', { type: 'range', min, max, step, value: String(value) });
                input.addEventListener('input', () => { output.textContent = `${Math.round(Number(input.value))}${unit}`; });
                input.addEventListener('change', () => { apply(Number(input.value)); preview(); });
                return h('label', { class: 'cd-range' }, [h('span', {}, [label, output]), input]);
            };

            const nodes = [h('div', { class: 'cd-section-title', text: 'Encuadre de todas las fotos' })];
            if (loss >= 0.03 && item.image_fit !== 'stretch') {
                nodes.push(h('p', {
                    class: 'cd-ratio-warning',
                    text: `Las fotos están recortadas en proporción ${format(cropRatio)} y esta caja es ${format(boxRatio)}: ${item.image_fit === 'contain' ? 'quedan bandas vacías' : `se pierde un ${Math.round(loss * 100)} % de la foto`}.`,
                }));
            }
            nodes.push(
                slider('Tamaño del rostro', fill * 100, 30, 85, 1, ' %', (value) => { item.frame_fill = value / 100; }),
                slider('Altura de los ojos', eyes, 25, 60, 1, ' %', (value) => { item.frame_eyes = value; }),
                h('small', { class: 'cd-hint', text: 'Al soltar el control se previsualiza en la credencial actual. Más rostro = más cerca; ojos más abajo = más espacio sobre la cabeza.' }),
                h('button', {
                    class: 'btn magic compact wide', type: 'button', text: '✦ Encuadrar todas las fotos en esta caja',
                    onclick: async () => {
                        const manual = host.getPhotos().filter((photo) => photo.manual).length;
                        if (manual && !window.confirm(`${manual} foto${manual === 1 ? ' tiene' : 's tienen'} ajustes manuales que se van a reemplazar. ¿Continuar?`)) return;
                        exitCropMode({ quiet: true });
                        await host.autoFrame(params());
                        render();
                    },
                }),
                h('div', { class: 'cd-button-row' }, [
                    h('button', { class: 'btn secondary compact', type: 'button', text: '✥ Ajustar a mano esta', title: 'También con doble clic sobre la foto', onclick: () => enterCropMode(item) }),
                    h('button', {
                        class: 'btn secondary compact', type: 'button', text: 'Valores sugeridos',
                        onclick: () => { change(() => { delete item.frame_fill; delete item.frame_eyes; }); preview(); },
                    }),
                ]),
            );
            return h('section', { class: 'cd-section cd-framing' }, nodes);
        }

        // ------------------------------ vista exacta ------------------------------ //

        async function exactPreview() {
            host.setBusy(true);
            host.setStatus('Generando la vista exacta…', 'busy', 40);
            try {
                const sessionId = await host.ensureSession();
                const photo = host.getCurrentPhoto();
                const response = await host.api(`/sessions/${sessionId}/cards/preview`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ design: design(), item: photo ? host.exportItem(photo) : null, side: state.side, dpi: 200, ...host.photoOptions() }),
                });
                const blob = await response.blob();
                if (state.exactUrl) URL.revokeObjectURL(state.exactUrl);
                state.exactUrl = URL.createObjectURL(blob);
                el.exact.querySelector('img').src = state.exactUrl;
                el.exact.hidden = false;
                host.setStatus('Vista exacta generada: así sale en el PDF o la imagen.', 'ok', 100);
            } catch (error) {
                host.setStatus(error.message, 'error', 0);
            } finally {
                host.setBusy(false);
            }
        }

        // ------------------------- guardar / abrir diseño ------------------------- //

        async function saveDesignFile() {
            host.setBusy(true);
            try {
                const used = new Set();
                ['front', 'back'].forEach((key) => {
                    if (design()[key].background_image) used.add(design()[key].background_image);
                    design()[key].elements.forEach((item) => { if (item.asset) used.add(item.asset); });
                });
                const assets = [];
                for (const asset of state.assets.filter((entry) => used.has(entry.asset_id))) {
                    const blob = await (await fetch(asset.url)).blob();
                    const data = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(reader.result);
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    });
                    assets.push({ asset_id: asset.asset_id, filename: asset.filename, data });
                }
                const content = JSON.stringify({ kind: 'etiquetador-credencial', version: 2, design: design(), customFields: state.customFields, assets });
                const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
                const link = h('a', { href: url, download: 'diseño.credencial.json' });
                document.body.append(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(url), 5000);
                host.setStatus('Diseño guardado. Podés reutilizarlo en otros lotes.');
            } catch (error) {
                host.setStatus(`No se pudo guardar el diseño: ${error.message}`, 'error');
            } finally {
                host.setBusy(false);
            }
        }

        async function openDesignFile(file) {
            if (!file) return;
            if (file.size > 40 * 1024 * 1024) return host.setStatus('El archivo de diseño es demasiado grande.', 'error');
            try {
                const data = JSON.parse(await file.text());
                if (data.kind !== 'etiquetador-credencial' || !data.design?.front) throw new Error('El archivo no es un diseño de credencial');
                const before = snapshot();
                const mapping = {};
                for (const asset of data.assets || []) {
                    const blob = await (await fetch(asset.data)).blob();
                    const uploaded = await uploadAsset(new File([blob], asset.filename || 'imagen.png', { type: blob.type }));
                    if (uploaded) mapping[asset.asset_id] = uploaded.asset_id;
                }
                const next = normalizeDesign(data.design);
                ['front', 'back'].forEach((key) => {
                    if (next[key].background_image) next[key].background_image = mapping[next[key].background_image] || null;
                    next[key].elements.forEach((item) => { if (item.asset) item.asset = mapping[item.asset] || null; });
                });
                state.design = next;
                state.customFields = [...new Set([...state.customFields, ...(data.customFields || [])])];
                state.selected = [];
                if (!next.double_sided) state.side = 'front';
                commit(before);
                renderAssets();
                render();
                host.setStatus(`Diseño “${file.name}” cargado.`);
            } catch (error) {
                host.setStatus(error.message, 'error');
            } finally {
                el.designInput.value = '';
            }
        }

        // ------------------------- exportación e impresión ------------------------- //

        const exportState = { printers: [], checkTimer: null, checkToken: 0, lastCheck: null };
        const readSetting = (key, fallback) => { try { return window.localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } };
        const writeSetting = (key, value) => { try { window.localStorage.setItem(key, value); } catch (_) { /* almacenamiento no disponible */ } };

        function exportScopePhotos(scope) {
            const photos = host.getPhotos();
            if (scope === 'current') return host.getCurrentPhoto() ? [host.getCurrentPhoto()] : [];
            if (scope === 'visible') return host.getVisiblePhotos();
            if (scope === 'approved') return photos.filter((photo) => photo.approved);
            if (scope === 'unprinted') return photos.filter((photo) => !photo.printCount);
            return photos;
        }

        const exportScope = () => document.querySelector('input[name="cx-scope"]:checked')?.value || 'all';
        const isPrinting = () => $('cx-format').value === 'PRINT';

        function renderPrinterOptions() {
            const select = $('cx-printer');
            const showAll = $('cx-show-all-printers').checked;
            const printers = exportState.printers.filter((printer) => showAll || printer.card);
            const remembered = readSetting('fotos.cardPrinter', '');
            const groups = [['Impresoras de tarjetas', printers.filter((printer) => printer.card)], ['Otras impresoras', printers.filter((printer) => !printer.card)]];
            select.replaceChildren(...groups.filter(([, list]) => list.length).map(([label, list]) => h('optgroup', { label }, list.map((printer) => h('option', {
                value: printer.name, text: `${printer.name}${printer.ready ? '' : ' · sin conexión'}`,
            })))));
            if (!printers.length) select.append(h('option', { value: '', text: exportState.printers.length ? 'No se detectaron impresoras de tarjetas' : 'Cargando impresoras…' }));
            const preferred = printers.find((printer) => printer.name === remembered)
                || printers.find((printer) => printer.default && printer.card && printer.ready)
                || printers.find((printer) => printer.card && printer.ready)
                || printers[0];
            if (preferred) select.value = preferred.name;
            updatePrinterStatus();
        }

        function updatePrinterStatus() {
            const status = $('cx-printer-status');
            const printer = exportState.printers.find((item) => item.name === $('cx-printer').value);
            if (!printer) {
                status.className = 'cx-printer-status warn';
                status.textContent = exportState.printers.length ? 'Marcá “Mostrar todas las impresoras” si la tuya no aparece.' : '';
                return;
            }
            status.className = `cx-printer-status ${printer.ready && printer.status === 'Lista' ? 'ok' : 'warn'}`;
            status.textContent = `${printer.driver} · ${printer.status}${printer.status === 'Lista' ? '' : ' según Windows'}`;
        }

        async function loadPrinters(refresh = false) {
            try {
                const response = await host.api(`/card-printers${refresh ? '?refresh=true' : ''}`);
                exportState.printers = (await response.json()).printers || [];
            } catch (error) {
                exportState.printers = [];
                $('cx-printer-status').className = 'cx-printer-status warn';
                $('cx-printer-status').textContent = error.message;
            }
            renderPrinterOptions();
            updateExportSummary();
        }

        function updateExportSummary() {
            const scope = exportScope();
            const format = $('cx-format').value;
            const printing = format === 'PRINT';
            const sides = $('cx-sides').value;
            const count = exportScopePhotos(scope).length;
            const faces = count * (sides === 'both' ? 2 : 1);
            const isPdf = format === 'PDF';
            $('cx-printer-options').hidden = !printing;
            $('cx-file-options').hidden = printing;
            $('cx-pdf-options').hidden = !isPdf;
            $('cx-sheet-options').hidden = !isPdf || $('cx-layout').value !== 'sheet';
            $('cx-sides').querySelector('[value="back"]').disabled = !design().double_sided;
            $('cx-sides').querySelector('[value="both"]').disabled = !design().double_sided;
            if (!design().double_sided && sides !== 'front') $('cx-sides').value = 'front';
            let detail = '';
            if (printing) {
                const copies = clamp(Number($('cx-copies').value) || 1, 1, 10);
                const printer = $('cx-printer').value;
                detail = printer ? ` · ${count * copies} tarjeta${count * copies === 1 ? '' : 's'}${sides === 'both' ? ' en doble faz' : ''} a ${printer}` : ' · elegí una impresora';
            } else if (isPdf && $('cx-layout').value === 'sheet') {
                const sheet = { A4: [210, 297], LETTER: [215.9, 279.4], LEGAL: [215.9, 355.6] }[$('cx-sheet').value];
                const margin = Number($('cx-margin').value) || 0;
                const gap = Number($('cx-gap').value) || 0;
                const fit = (pageW, pageH) => [Math.floor((pageW - margin * 2 + gap) / (design().width_mm + gap)), Math.floor((pageH - margin * 2 + gap) / (design().height_mm + gap))];
                const [a, b] = fit(sheet[0], sheet[1]);
                const [c, d] = fit(sheet[1], sheet[0]);
                const perSheet = Math.max(a * b, c * d);
                detail = perSheet ? ` · ${perSheet} por hoja · ${Math.ceil(count / perSheet) * (sides === 'both' ? 2 : 1)} página(s)` : ' · no entra ninguna credencial con esos márgenes';
            } else if (isPdf) {
                detail = ` · ${faces} página(s) de ${design().width_mm} × ${design().height_mm} mm`;
            } else {
                detail = faces === 1 ? ' · un archivo de imagen' : ` · ${faces} imágenes en un ZIP`;
            }
            $('cx-summary').textContent = count ? `${count} credencial${count === 1 ? '' : 'es'}${detail}` : 'No hay credenciales con este alcance.';
            $('cx-run').disabled = !count || (printing && !$('cx-printer').value);
            $('cx-run').textContent = printing ? `Imprimir${count ? ` ${count}` : ''}` : 'Exportar';
            scheduleCheck();
        }

        function scheduleCheck() {
            clearTimeout(exportState.checkTimer);
            exportState.checkTimer = setTimeout(runCheck, 250);
        }

        function photoLabel(photo) {
            const fields = guessFields(host.getHeaders());
            const index = host.getPhotos().indexOf(photo) + 1;
            return `${index}. ${resolveFields(fields.name, valuesFor(photo)).trim() || photo.filename}`;
        }

        async function runCheck() {
            const photos = exportScopePhotos(exportScope());
            const box = $('cx-check');
            const list = $('cx-check-list');
            const title = $('cx-check-title');
            const token = ++exportState.checkToken;
            exportState.lastCheck = null;
            if (!photos.length) { box.className = 'cx-check'; title.textContent = 'Revisión previa'; list.replaceChildren(); return; }
            box.className = 'cx-check';
            title.textContent = `Revisando ${photos.length} credencial${photos.length === 1 ? '' : 'es'}…`;
            try {
                const sessionId = await host.ensureSession();
                const response = await host.api(`/sessions/${sessionId}/cards/check`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ design: design(), items: photos.map((photo) => host.exportItem(photo)), sides: $('cx-sides').value }),
                });
                const report = await response.json();
                if (token !== exportState.checkToken) return;
                const byId = new Map(report.results.map((result) => [result.photo_id, result.issues]));
                if (isPrinting()) {
                    photos.filter((photo) => photo.printCount).forEach((photo) => {
                        const issues = byId.get(photo.id) || [];
                        issues.push({ level: 'warning', element: 'Impresión', side: '', message: `ya se imprimió ${photo.printCount === 1 ? 'una vez' : `${photo.printCount} veces`}` });
                        byId.set(photo.id, issues);
                    });
                }
                const flagged = photos.filter((photo) => byId.has(photo.id));
                const errors = flagged.filter((photo) => byId.get(photo.id).some((issue) => issue.level === 'error')).length;
                box.className = `cx-check ${!flagged.length ? 'good' : errors ? 'error' : 'warn'}`;
                title.textContent = !flagged.length
                    ? `✓ ${photos.length === 1 ? 'La credencial está' : `Las ${photos.length} credenciales están`} en orden`
                    : `⚠ ${flagged.length} de ${photos.length} con observaciones${errors ? ` · ${errors} con errores` : ''}`;
                list.replaceChildren(...flagged.slice(0, 60).map((photo) => h('button', {
                    type: 'button', class: 'cx-check-item', title: 'Abrir esta credencial en el editor',
                    onclick: () => { el.exportModal.hidden = true; host.selectPhoto(photo.id); if (el.modal.hidden) open(); },
                }, [
                    h('strong', { text: photoLabel(photo) }),
                    ...byId.get(photo.id).map((issue) => h('span', { class: issue.level, text: `${issue.side ? `${issue.side} · ` : ''}${issue.element}: ${issue.message}` })),
                ])));
                if (flagged.length > 60) list.append(h('p', { class: 'field-note', text: `Y ${flagged.length - 60} más.` }));
                exportState.lastCheck = { flagged: flagged.length, errors };
            } catch (error) {
                if (token !== exportState.checkToken) return;
                box.className = 'cx-check warn';
                title.textContent = `No se pudo revisar: ${error.message}`;
                list.replaceChildren();
            }
        }

        function openExport(scope = 'all', { print = null } = {}) {
            if (!host.getPhotos().length) return host.setStatus('Agregá fotos al lote para exportar o imprimir credenciales.', 'error');
            const radio = document.querySelector(`input[name="cx-scope"][value="${scope}"]`);
            if (radio) radio.checked = true;
            if (print === true) $('cx-format').value = 'PRINT';
            else if (print === false || !exportState.opened) $('cx-format').value = readSetting('fotos.cardDestination', 'PDF');
            if (print === false && isPrinting()) $('cx-format').value = 'PDF';
            exportState.opened = true;
            el.exportModal.hidden = false;
            updateExportSummary();
            if (!exportState.printers.length) loadPrinters();
            $('cx-run').focus();
        }

        async function runPrint(photos) {
            const printer = $('cx-printer').value;
            const sides = $('cx-sides').value;
            const copies = clamp(Math.round(Number($('cx-copies').value) || 1), 1, 10);
            clearTimeout(exportState.checkTimer);
            await runCheck();
            const errors = exportState.lastCheck?.errors || 0;
            if (errors && !window.confirm(`La revisión encontró errores en ${errors} credencial${errors === 1 ? '' : 'es'} (por ejemplo, códigos inválidos o textos cortados). ¿Imprimir igual?`)) return;
            writeSetting('fotos.cardPrinter', printer);
            writeSetting('fotos.cardDestination', 'PRINT');
            el.exportModal.hidden = true;
            host.setBusy(true);
            host.setStatus(`Enviando ${photos.length * copies} tarjeta${photos.length * copies === 1 ? '' : 's'} a ${printer}…`, 'busy', 25);
            try {
                const sessionId = await host.ensureSession();
                const response = await host.api(`/sessions/${sessionId}/cards/print`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        design: design(), items: photos.map((photo) => host.exportItem(photo)), printer, sides, copies,
                        rotate_back: $('cx-rotate-back').checked, ...host.photoOptions(),
                    }),
                });
                const result = await response.json();
                host.onPrinted(result.printed);
                host.setStatus(`Enviadas ${result.cards} tarjeta${result.cards === 1 ? '' : 's'} a ${result.printer} (${result.pages} página${result.pages === 1 ? '' : 's'}). Revisá la cola de Windows si no empieza a imprimir.`, 'ok', 100);
            } catch (error) {
                host.setStatus(error.message, 'error', 0);
            } finally {
                host.setBusy(false);
            }
        }

        async function runExport() {
            const photos = exportScopePhotos(exportScope());
            if (!photos.length) return;
            if (isPrinting()) return runPrint(photos);
            const output = {
                format: $('cx-format').value, dpi: Number($('cx-dpi').value), sides: $('cx-sides').value,
                pdf_layout: $('cx-layout').value, sheet: $('cx-sheet').value,
                margin_mm: Number($('cx-margin').value) || 0, gap_mm: Number($('cx-gap').value) || 0,
                crop_marks: $('cx-marks').checked, duplex_mirror: $('cx-mirror').checked,
                filename_pattern: $('cx-pattern').value.trim() || '{Archivo}',
            };
            const faces = photos.length * (output.sides === 'both' ? 2 : 1);
            if (output.dpi > 300 && faces > 120) return host.setStatus('A 600 dpi se pueden exportar hasta 120 caras por vez. Usá 300 dpi o dividí el lote.', 'error');
            writeSetting('fotos.cardDestination', output.format);
            el.exportModal.hidden = true;
            host.setBusy(true);
            host.setStatus(`Componiendo ${faces} cara${faces === 1 ? '' : 's'} a ${output.dpi} dpi…`, 'busy', 20);
            try {
                const sessionId = await host.ensureSession();
                const response = await host.api(`/sessions/${sessionId}/cards/export`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ design: design(), items: photos.map((photo) => host.exportItem(photo)), output, ...host.photoOptions() }),
                });
                host.setStatus('Descargando…', 'busy', 85);
                await host.downloadResponse(response, output.format === 'PDF' ? 'credenciales.pdf' : 'credenciales.zip');
                host.setStatus(`Exportación lista · ${photos.length} credencial${photos.length === 1 ? '' : 'es'}.`, 'ok', 100);
            } catch (error) {
                host.setStatus(error.message, 'error', 0);
            } finally {
                host.setBusy(false);
            }
        }

        // ------------------------------ teclado ------------------------------ //

        function onKeyDown(event) {
            if (!el.exportModal.hidden) {
                if (event.key === 'Escape') { event.preventDefault(); el.exportModal.hidden = true; }
                return;
            }
            if (el.modal.hidden) return;
            const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName);
            const key = event.key.toLocaleLowerCase('es');
            const mod = event.ctrlKey || event.metaKey;
            if (mod && key === 'z' && !typing) { event.preventDefault(); if (event.shiftKey) redo(); else undo(); return; }
            if (mod && key === 'y' && !typing) { event.preventDefault(); redo(); return; }
            if (state.cropping && !typing) {
                const pans = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
                if (event.key === 'Escape' || event.key === 'Enter') { event.preventDefault(); exitCropMode(); return; }
                if (pans[event.key]) { event.preventDefault(); cropNudge(...pans[event.key].map((value) => value * (event.shiftKey ? 5 : 1))); return; }
                if (event.key === '+' || event.key === '=') { event.preventDefault(); cropZoom(0.95); return; }
                if (event.key === '-') { event.preventDefault(); cropZoom(1.05); return; }
            }
            if (event.key === 'Escape') {
                event.preventDefault();
                if (!el.exact.hidden) el.exact.hidden = true;
                else if (typing) document.activeElement.blur();
                else if (state.selected.length) select([]);
                else close();
                return;
            }
            if (typing) return;
            if (mod && key === 'a') { event.preventDefault(); select(elements().filter((item) => !item.hidden).map((item) => item.id)); return; }
            if (mod && key === 'd') { event.preventDefault(); duplicateSelected(); return; }
            if (mod && key === 'c') { copySelected(); return; }
            if (mod && key === 'v') { event.preventDefault(); paste(); return; }
            if (mod && event.key === ']') { event.preventDefault(); reorder(event.shiftKey ? 'front' : 'forward'); return; }
            if (mod && event.key === '[') { event.preventDefault(); reorder(event.shiftKey ? 'back' : 'backward'); return; }
            if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); removeSelected(); return; }
            const step = event.shiftKey ? 5 : 0.5;
            const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
            if (moves[event.key] && state.selected.length) { event.preventDefault(); nudge(...moves[event.key]); }
        }

        // ------------------------------ ciclo de vida ------------------------------ //

        function open() {
            el.modal.hidden = false;
            document.body.classList.add('designer-open');
            state.zoomMode = 'fit';
            renderRecordSelect();
            renderAssets();
            requestAnimationFrame(() => render());
        }

        function close() {
            exitCropMode({ quiet: true });
            el.modal.hidden = true;
            el.exact.hidden = true;
            document.body.classList.remove('designer-open');
            host.onDesignChanged();
        }

        function bindUi() {
            $('cd-close').addEventListener('click', close);
            $('cd-done').addEventListener('click', close);
            $('cd-undo').addEventListener('click', undo);
            $('cd-redo').addEventListener('click', redo);
            $('cd-exact-btn').addEventListener('click', exactPreview);
            el.exact.addEventListener('click', () => { el.exact.hidden = true; });
            $('cd-save-design').addEventListener('click', saveDesignFile);
            $('cd-open-design').addEventListener('click', () => el.designInput.click());
            el.designInput.addEventListener('change', () => openDesignFile(el.designInput.files[0]));
            $('cd-export-btn').addEventListener('click', () => openExport('all', { print: false }));
            $('cd-print-btn').addEventListener('click', () => openExport('current', { print: true }));
            $('cd-record-prev').addEventListener('click', () => stepRecord(-1));
            $('cd-record-next').addEventListener('click', () => stepRecord(1));
            el.record.addEventListener('change', () => { if (el.record.value) host.selectPhoto(el.record.value); });
            document.querySelectorAll('[data-cd-insert]').forEach((button) => button.addEventListener('click', () => {
                const type = button.dataset.cdInsert;
                if (type === 'image' && !state.assets.length) { assetTarget = '__insert__'; el.assetInput.click(); return; }
                insert(type);
            }));
            const fieldInsert = $('cd-insert-field');
            fieldInsert.addEventListener('focus', () => {
                fieldInsert.replaceChildren(h('option', { value: '', text: 'Campo…' }), ...[...BUILTIN_FIELDS, ...fieldNames()].map((name) => h('option', { value: name, text: name })));
            });
            fieldInsert.addEventListener('change', () => {
                if (fieldInsert.value) insert('text', { text: `{${fieldInsert.value}}`, name: fieldInsert.value });
                fieldInsert.value = '';
            });
            // Los controles del panel aplican en vivo y registran el historial al confirmar.
            el.properties.addEventListener('focusin', () => { state.pending = snapshot(); });
            el.properties.addEventListener('change', () => {
                if (state.pending) commit(state.pending);
                state.pending = snapshot();
            });
            $('cd-upload-asset').addEventListener('click', () => { assetTarget = null; el.assetInput.click(); });
            el.assetInput.addEventListener('change', async () => { await handleAssetInput(); renderAssets(); });
            document.querySelectorAll('[data-cd-align]').forEach((button) => button.addEventListener('click', () => align(button.dataset.cdAlign)));
            document.querySelectorAll('[data-cd-distribute]').forEach((button) => button.addEventListener('click', () => distribute(button.dataset.cdDistribute)));
            document.querySelectorAll('[data-cd-order]').forEach((button) => button.addEventListener('click', () => reorder(button.dataset.cdOrder)));
            $('cd-duplicate').addEventListener('click', duplicateSelected);
            $('cd-delete').addEventListener('click', removeSelected);
            document.querySelectorAll('[data-cd-side]').forEach((button) => button.addEventListener('click', () => {
                exitCropMode({ quiet: true });
                state.side = button.dataset.cdSide;
                state.selected = [];
                render();
            }));
            $('cd-size-preset').addEventListener('change', () => {
                const preset = SIZE_PRESETS.find((item) => item.id === $('cd-size-preset').value);
                if (!preset?.w) return;
                const portrait = design().height_mm > design().width_mm;
                resizeCard(portrait ? preset.h : preset.w, portrait ? preset.w : preset.h, { keepPhysical: false });
            });
            ['cd-width-mm', 'cd-height-mm'].forEach((id) => $(id).addEventListener('change', () => resizeCard(Number($('cd-width-mm').value), Number($('cd-height-mm').value), { keepPhysical: false })));
            $('cd-orient-landscape').addEventListener('click', () => { if (design().height_mm > design().width_mm) resizeCard(design().height_mm, design().width_mm, { keepPhysical: true }); });
            $('cd-orient-portrait').addEventListener('click', () => { if (design().width_mm > design().height_mm) resizeCard(design().height_mm, design().width_mm, { keepPhysical: true }); });
            $('cd-double-sided').addEventListener('change', () => {
                change(() => { design().double_sided = $('cd-double-sided').checked; });
                if (!design().double_sided && state.side === 'back') { state.side = 'front'; state.selected = []; }
                if (design().double_sided && !design().back.elements.length) host.setStatus('Dorso habilitado. Elegí la plantilla “Dorso informativo” o agregá objetos.');
                render();
            });
            $('cd-copy-front').addEventListener('click', () => {
                if (!design().double_sided) return;
                const source = state.side === 'front' ? 'front' : 'back';
                const target = source === 'front' ? 'back' : 'front';
                if (design()[target].elements.length && !window.confirm(`¿Reemplazar el ${target === 'back' ? 'dorso' : 'frente'} por una copia de esta cara?`)) return;
                change(() => { design()[target] = clone(design()[source]); design()[target].elements.forEach((item) => { item.id = newId(); }); });
            });
            $('cd-snap').addEventListener('change', () => { state.snapGrid = $('cd-snap').checked; });
            $('cd-guides').addEventListener('change', () => { state.smartGuides = $('cd-guides').checked; });
            $('cd-safe').addEventListener('change', () => { state.showSafe = $('cd-safe').checked; renderStage(); });
            $('cd-zoom-in').addEventListener('click', () => setZoom((state.pxPerMm || fitPxPerMm()) * 1.15));
            $('cd-zoom-out').addEventListener('click', () => setZoom((state.pxPerMm || fitPxPerMm()) / 1.15));
            $('cd-zoom-fit').addEventListener('click', () => { state.zoomMode = 'fit'; renderStage(); });
            $('cd-zoom-real').addEventListener('click', () => setZoom(3.7795));
            el.modal.addEventListener('pointerdown', (event) => { if (event.target === el.modal) close(); });
            // Exportación
            $('cx-close').addEventListener('click', () => { el.exportModal.hidden = true; });
            $('cx-cancel').addEventListener('click', () => { el.exportModal.hidden = true; });
            $('cx-run').addEventListener('click', runExport);
            el.exportModal.addEventListener('pointerdown', (event) => { if (event.target === el.exportModal) el.exportModal.hidden = true; });
            el.exportModal.querySelectorAll('input, select').forEach((input) => input.addEventListener('change', updateExportSummary));
            el.exportModal.querySelectorAll('input[type="number"]').forEach((input) => input.addEventListener('input', updateExportSummary));
            $('cx-printer').addEventListener('change', updatePrinterStatus);
            $('cx-printer-refresh').addEventListener('click', () => loadPrinters(true));
            $('cx-show-all-printers').addEventListener('change', renderPrinterOptions);
            $('cx-check-run').addEventListener('click', runCheck);
            document.addEventListener('keydown', onKeyDown);
            bindStage();
        }

        // ------------------------------ migración ------------------------------ //

        function normalizeDesign(raw) {
            const base = defaultDesign();
            const result = {
                version: 2,
                width_mm: Number(raw?.width_mm) || base.width_mm,
                height_mm: Number(raw?.height_mm) || base.height_mm,
                double_sided: Boolean(raw?.double_sided),
                front: { ...emptySide(), ...(raw?.front || {}) },
                back: { ...emptySide(), ...(raw?.back || {}) },
            };
            ['front', 'back'].forEach((key) => {
                result[key].elements = (result[key].elements || []).filter((item) => TYPE_LABELS[item.type]).map((item) => ({ ...makeElement(item.type), ...item, id: item.id || newId() }));
            });
            return result;
        }

        function migrateLegacy(settings, { logoUrl, backgroundUrl }) {
            // Proyectos guardados con el diseñador anterior (seis objetos fijos).
            const old = settings.cardDesigner || {};
            const portrait = old.orientation === 'portrait';
            const accent = settings.cardColor || '#176b87';
            const pxToPt = (px) => Math.round(px * 72 / 300 * 10) / 10;
            const positions = old.positions || {};
            const textColor = old.textColor || '#17202b';
            const font = old.fontFamily || 'sans';
            const elementsList = [];
            if (old.template === 'sidebar') elementsList.push(makeElement('rect', { name: 'Banda', x: 0, y: 0, w: portrait ? 0.12 : 0.34, h: 1, fill: accent }));
            else if (old.template === 'minimal') elementsList.push(makeElement('rect', { name: 'Barra inferior', x: 0, y: 0.975, w: 1, h: 0.025, fill: accent }));
            else elementsList.push(makeElement('rect', { name: 'Encabezado', x: 0, y: 0, w: 1, h: portrait ? 0.14 : 0.16, fill: accent }));
            const at = (key, fallback) => {
                const value = positions[key] || fallback;
                return { x: value[0], y: value[1], w: value[2], h: value[3] };
            };
            const textProps = (key, size) => ({
                font, size: pxToPt(size), bold: Boolean(old.bold?.[key] ?? key !== 'role'), uppercase: Boolean(old.uppercase?.[key]),
                align: old.alignments?.[key] || 'left',
            });
            const titleBox = at('title', [0.04, 0.05, 0.7, 0.1]);
            const onAccent = (old.template !== 'sidebar' && old.template !== 'minimal' && titleBox.y < 0.17) || (old.template === 'sidebar' && !portrait && titleBox.x < 0.34);
            elementsList.push(makeElement('text', { name: 'Título', ...titleBox, text: settings.cardTitle || 'CREDENCIAL', color: onAccent ? '#ffffff' : accent, ...textProps('title', old.titleSize || 42) }));
            if (old.showLogo !== false) elementsList.push(makeElement('image', { name: 'Logo', ...at('logo', [0.78, 0.035, 0.17, 0.13]), asset: logoUrl ? 'logo' : null }));
            if (old.showPhoto !== false) elementsList.push(makeElement('photo', { name: 'Foto', ...at('photo', [0.04, 0.26, 0.31, 0.68]), shape: old.photoShape === 'circle' ? 'circle' : 'rect', radius: old.photoShape === 'square' ? 0 : 3, stroke_color: '#dbe1e9', stroke_width: 0.7 }));
            elementsList.push(makeElement('text', { name: 'Nombre', ...at('name', [0.39, 0.3, 0.55, 0.13]), text: settings.cardNameField ? `{${settings.cardNameField}}` : '{Archivo}', color: textColor, ...textProps('name', old.nameSize || 52) }));
            if (settings.cardRoleField) elementsList.push(makeElement('text', { name: 'Cargo', ...at('role', [0.39, 0.44, 0.55, 0.08]), text: `{${settings.cardRoleField}}`, color: '#5b6b7f', ...textProps('role', old.roleSize || 31) }));
            if (old.showQr !== false) elementsList.push(makeElement('qr', { name: 'QR', ...at('qr', [0.74, 0.6, 0.2, 0.31]), value: settings.cardQrField ? `{${settings.cardQrField}}` : (settings.cardNameField ? `{${settings.cardNameField}}` : '{Archivo}'), background: null }));
            return {
                version: 2, width_mm: portrait ? 53.98 : 85.6, height_mm: portrait ? 85.6 : 53.98, double_sided: false,
                front: { background_color: old.backgroundColor || '#f9fafc', background_image: backgroundUrl ? 'card_background' : null, elements: elementsList },
                back: emptySide(),
            };
        }

        function defaultDesign() {
            const template = TEMPLATES[0];
            return {
                version: 2, width_mm: 85.6, height_mm: 53.98, double_sided: false,
                front: template.build({ accent: '#176b87', logo: state.assets.find((asset) => asset.asset_id === 'logo') ? 'logo' : null, fields: guessFields(host.getHeaders()) }),
                back: emptySide(),
            };
        }

        // ------------------------------ API pública ------------------------------ //

        function reset() {
            state.assets = [];
            state.customFields = [];
            state.design = defaultDesign();
            state.history = [];
            state.future = [];
            state.selected = [];
            state.side = 'front';
            state.pristine = true;
            state.photoUrls.clear();
            renderAssets();
            render();
        }

        function serialize() {
            return { version: 2, design: clone(design()), customFields: [...state.customFields] };
        }

        function restore(settings = {}, { assets = [], logoUrl = null, backgroundUrl = null } = {}) {
            state.assets = assets;
            state.photoUrls.clear();
            if (settings.cardDesign?.design) {
                state.design = normalizeDesign(settings.cardDesign.design);
                state.customFields = settings.cardDesign.customFields || [];
                state.pristine = false;
            } else if (settings.cardDesigner) {
                state.design = migrateLegacy(settings, { logoUrl, backgroundUrl });
                state.customFields = [];
                state.pristine = false;
            } else {
                state.design = defaultDesign();
                state.customFields = [];
                state.pristine = true;
            }
            state.history = [];
            state.future = [];
            state.selected = [];
            state.side = 'front';
            renderAssets();
            render();
        }

        function renderMini(container, sideKey = 'front') {
            if (!container) return;
            container.style.aspectRatio = `${design().width_mm} / ${design().height_mm}`;
            renderSide(container, design()[sideKey], { photo: host.getCurrentPhoto(), interactive: false });
        }

        function onDataChanged() {
            if (state.pristine) state.design = defaultDesign();
            render();
            host.onDesignChanged();
        }

        function onPhotoChanged() {
            if (el.modal.hidden) return;
            if (state.cropping) exitCropMode({ quiet: true });
            renderRecordSelect();
            renderRecordData();
            renderStage();
        }

        bindUi();
        renderTemplates();
        state.design = defaultDesign();

        return {
            open, close, reset, serialize, restore, renderMini, openExport, onDataChanged, onPhotoChanged,
            isOpen: () => !el.modal.hidden || !el.exportModal.hidden,
            getDesign: () => design(),
            isDoubleSided: () => design().double_sided,
            refresh: () => render(),
        };
    }

    window.CardDesigner = { create, layoutText, wrapLines };
})();
