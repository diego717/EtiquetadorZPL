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
        rect: 'Rectángulo', ellipse: 'Elipse', line: 'Línea', path: 'Trazado',
    };
    const TYPE_ICONS = { text: 'T', photo: '◪', image: '▣', qr: '▦', barcode: '┃┃', rect: '□', ellipse: '○', line: '─', path: '✒' };
    const DEFAULTS = {
        text: {
            text: 'Texto', font: 'sans', size: 12, bold: false, italic: false, underline: false, uppercase: false,
            color: '#17202b', align: 'left', valign: 'middle', fit: 'shrink', line_height: 1.15, padding: 0,
            fill: null, stroke_color: null, stroke_width: 0, radius: 0,
        },
        photo: { shape: 'rect', radius: 3, stroke_color: null, stroke_width: 0, image_fit: 'cover', grayscale: false },
        image: { asset: null, image_fit: 'contain', radius: 0, stroke_color: null, stroke_width: 0, grayscale: false, recolor: null },
        qr: { value: '{Archivo}', color: '#000000', background: '#ffffff', ecc: 'M' },
        barcode: { value: '{Nro}', symbology: 'code128', show_text: true, color: '#000000', background: null },
        rect: { fill: '#176b87', gradient: null, stroke_color: null, stroke_width: 0, radius: 0, dash: 'solid' },
        ellipse: { fill: '#176b87', gradient: null, stroke_color: null, stroke_width: 0, dash: 'solid' },
        line: { stroke_color: '#17202b', stroke_width: 1, dash: 'solid', line_cap: 'butt' },
        path: {
            paths: [], fill: '#176b87', gradient: null, fill_rule: 'evenodd', stroke_color: null, stroke_width: 0,
            dash: 'solid', line_cap: 'round', line_join: 'round', preset: null,
        },
    };
    const NEW_SIZES_MM = {
        text: [40, 8], photo: [24, 32], image: [20, 12], qr: [16, 16], barcode: [36, 12],
        rect: [30, 14], ellipse: [16, 16], line: [36, 2], path: [20, 20],
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

    // ------------------------------------------------------------------ //
    // Geometría vectorial (trazados Bézier en fracciones de la caja)
    // ------------------------------------------------------------------ //

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const DASH_PATTERNS = { dash: [4, 2], dot: [1, 1.5], dashdot: [4, 2, 1, 2] };
    const DASH_OPTIONS = [['solid', 'Continua'], ['dash', 'Rayas'], ['dot', 'Puntos'], ['dashdot', 'Raya y punto']];
    const CAP_OPTIONS = [['butt', 'Recto'], ['round', 'Redondeado'], ['square', 'Cuadrado']];
    const JOIN_OPTIONS = [['miter', 'En punta'], ['round', 'Redondeada'], ['bevel', 'Biselada']];
    let svgUid = 0;

    function svgNode(tag, attributes = {}, children = []) {
        const node = document.createElementNS(SVG_NS, tag);
        Object.entries(attributes).forEach(([key, value]) => {
            if (value === undefined || value === null || value === false) return;
            node.setAttribute(key, String(value));
        });
        children.forEach((child) => { if (child) node.append(child); });
        return node;
    }

    const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

    function subSegments(sub) {
        const nodes = sub.nodes || [];
        const count = sub.closed && nodes.length > 1 ? nodes.length : nodes.length - 1;
        const result = [];
        for (let index = 0; index < count; index += 1) {
            const start = nodes[index];
            const end = nodes[(index + 1) % nodes.length];
            const curved = start.o || end.i;
            result.push({ index, p0: start.p, c1: curved ? (start.o || start.p) : null, c2: curved ? (end.i || end.p) : null, p3: end.p });
        }
        return result;
    }

    function cubicAt(p0, c1, c2, p3, t) {
        const u = 1 - t;
        const a = u * u * u; const b = 3 * u * u * t; const c = 3 * u * t * t; const d = t * t * t;
        return [a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]];
    }

    function pathData(paths, sx = 1, sy = 1) {
        const f = (point) => `${(point[0] * sx).toFixed(3)} ${(point[1] * sy).toFixed(3)}`;
        return paths.map((sub) => {
            if (!sub.nodes?.length) return '';
            let d = `M${f(sub.nodes[0].p)}`;
            subSegments(sub).forEach((segment) => {
                d += segment.c1 ? `C${f(segment.c1)} ${f(segment.c2)} ${f(segment.p3)}` : `L${f(segment.p3)}`;
            });
            return sub.closed ? `${d}Z` : d;
        }).join('');
    }

    function flattenSub(sub, steps = 24) {
        const nodes = sub.nodes || [];
        if (!nodes.length) return [];
        const points = [nodes[0].p];
        subSegments(sub).forEach((segment) => {
            if (!segment.c1) { points.push(segment.p3); return; }
            for (let step = 1; step <= steps; step += 1) points.push(cubicAt(segment.p0, segment.c1, segment.c2, segment.p3, step / steps));
        });
        return points;
    }

    function pathsBounds(paths) {
        let left = Infinity; let top = Infinity; let right = -Infinity; let bottom = -Infinity;
        paths.forEach((sub) => flattenSub(sub).forEach(([x, y]) => {
            left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
        }));
        return Number.isFinite(left) ? { left, top, right, bottom } : null;
    }

    function mapPaths(paths, transform) {
        return paths.map((sub) => ({
            closed: Boolean(sub.closed),
            nodes: sub.nodes.map((entry) => ({
                p: transform(entry.p), i: entry.i ? transform(entry.i) : null, o: entry.o ? transform(entry.o) : null,
                ...(entry.s ? { s: true } : {}),
            })),
        }));
    }

    function fitUnit(paths, minSize = 0.2) {
        // Normaliza trazados (en mm) a la caja que los contiene: devuelve fracciones 0..1 y la caja.
        const bounds = pathsBounds(paths);
        if (!bounds) return null;
        let width = bounds.right - bounds.left;
        let height = bounds.bottom - bounds.top;
        let { left, top } = bounds;
        if (width < minSize) { left -= (minSize - width) / 2; width = minSize; }
        if (height < minSize) { top -= (minSize - height) / 2; height = minSize; }
        const round = (value) => Math.round(value * 1e6) / 1e6;
        return { paths: mapPaths(paths, ([x, y]) => [round((x - left) / width), round((y - top) / height)]), box: { left, top, width, height } };
    }

    const polyline = (points) => [{ closed: true, nodes: points.map((p) => ({ p, i: null, o: null })) }];

    function regularPolygon(sides) {
        const count = clamp(Math.round(sides), 3, 24);
        return polyline(Array.from({ length: count }, (_, index) => {
            const angle = -Math.PI / 2 + index * 2 * Math.PI / count;
            return [0.5 + 0.5 * Math.cos(angle), 0.5 + 0.5 * Math.sin(angle)];
        }));
    }

    function starShape(points, inner) {
        const count = clamp(Math.round(points), 3, 40);
        return polyline(Array.from({ length: count * 2 }, (_, index) => {
            const radius = index % 2 === 0 ? 0.5 : 0.5 * clamp(inner, 0.05, 0.95);
            const angle = -Math.PI / 2 + index * Math.PI / count;
            return [0.5 + radius * Math.cos(angle), 0.5 + radius * Math.sin(angle)];
        }));
    }

    const SHAPE_PRESETS = [
        { id: 'triangle', label: 'Triángulo', size: [20, 18], build: () => polyline([[0.5, 0], [1, 1], [0, 1]]) },
        { id: 'diamond', label: 'Rombo', size: [18, 22], build: () => polyline([[0.5, 0], [1, 0.5], [0.5, 1], [0, 0.5]]) },
        { id: 'polygon', label: 'Polígono', size: [20, 20], params: { sides: 6 }, build: ({ sides }) => regularPolygon(sides) },
        { id: 'star', label: 'Estrella', size: [20, 20], params: { points: 5, inner: 0.45 }, build: ({ points, inner }) => starShape(points, inner) },
        { id: 'arrow', label: 'Flecha', size: [30, 14], build: () => polyline([[0, 0.3], [0.62, 0.3], [0.62, 0], [1, 0.5], [0.62, 1], [0.62, 0.7], [0, 0.7]]) },
        { id: 'chevron', label: 'Galón', size: [24, 14], build: () => polyline([[0, 0], [0.72, 0], [1, 0.5], [0.72, 1], [0, 1], [0.28, 0.5]]) },
        { id: 'ribbon', label: 'Cinta', size: [40, 10], build: () => polyline([[0, 0], [1, 0], [0.9, 0.5], [1, 1], [0, 1], [0.1, 0.5]]) },
        { id: 'cut', label: 'Esquina cortada', size: [30, 14], build: () => polyline([[0, 0], [0.82, 0], [1, 0.3], [1, 1], [0, 1]]) },
        { id: 'cross', label: 'Cruz', size: [18, 18], build: () => polyline([[0.34, 0], [0.66, 0], [0.66, 0.34], [1, 0.34], [1, 0.66], [0.66, 0.66], [0.66, 1], [0.34, 1], [0.34, 0.66], [0, 0.66], [0, 0.34], [0.34, 0.34]]) },
        {
            id: 'wave', label: 'Banda con onda', size: [60, 14], build: () => [{ closed: true, nodes: [
                { p: [0, 0], i: null, o: null }, { p: [1, 0], i: null, o: null },
                { p: [1, 0.7], i: null, o: [0.83, 1.05] },
                { p: [0.5, 0.7], i: [0.67, 1.05], o: [0.33, 0.35], s: true },
                { p: [0, 0.7], i: [0.17, 0.35], o: null },
            ] }],
        },
        {
            id: 'shield', label: 'Escudo', size: [18, 22], build: () => [{ closed: true, nodes: [
                { p: [0, 0], i: null, o: null }, { p: [1, 0], i: null, o: null },
                { p: [1, 0.45], i: null, o: [1, 0.78] },
                { p: [0.5, 1], i: [0.88, 0.9], o: [0.12, 0.9], s: true },
                { p: [0, 0.45], i: [0, 0.78], o: null },
            ] }],
        },
        {
            id: 'heart', label: 'Corazón', size: [20, 18], build: () => [{ closed: true, nodes: [
                { p: [0.5, 0.22], i: [0.3, -0.08], o: [0.7, -0.08] },
                { p: [0.5, 1], i: [1.12, 0.42], o: [-0.12, 0.42] },
            ] }],
        },
        {
            id: 'bubble', label: 'Globo de diálogo', size: [30, 20], build: () => [{ closed: true, nodes: [
                { p: [0.1, 0], i: [0, 0], o: null }, { p: [0.9, 0], i: null, o: [1, 0] },
                { p: [1, 0.15], i: [1, 0.05], o: null }, { p: [1, 0.6], i: null, o: [1, 0.7] },
                { p: [0.9, 0.75], i: [1, 0.75], o: null }, { p: [0.42, 0.75], i: null, o: null },
                { p: [0.2, 1], i: null, o: null }, { p: [0.26, 0.75], i: null, o: null },
                { p: [0.1, 0.75], i: null, o: [0, 0.75] }, { p: [0, 0.6], i: [0, 0.7], o: null },
                { p: [0, 0.15], i: null, o: [0, 0.05] },
            ] }],
        },
    ];

    function presetPaths(preset, params) {
        return fitUnit(preset.build({ ...(preset.params || {}), ...(params || {}) }), 0.001).paths;
    }

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

    const MAG_TRACK_LIMITS = { 1: 76, 2: 37, 3: 104 };

    function defaultMagstripe() {
        return { enabled: false, side: 'back', track1: '', track2: '', track3: '' };
    }

    function normalizeMagTrack(track, value) {
        let text = String(value || '').trim();
        if (track === 1) { text = text.toUpperCase(); if (text.startsWith('%')) text = text.slice(1); }
        else if (text.startsWith(';')) text = text.slice(1);
        if (text.endsWith('?')) text = text.slice(0, -1);
        return text;
    }

    function magTrackError(track, value) {
        // Mismas reglas ISO 7811 que el servidor.
        if (!value) return null;
        if (value.length > MAG_TRACK_LIMITS[track]) return `${value.length} caracteres, admite hasta ${MAG_TRACK_LIMITS[track]}`;
        const invalid = [...new Set([...value].filter((char) => (track === 1
            ? char.charCodeAt(0) < 0x20 || char.charCodeAt(0) > 0x5f || char === '%' || char === '?'
            : !/[0-9=]/.test(char))))];
        if (invalid.length) return `caracteres no admitidos: ${invalid.slice(0, 6).map((char) => (char === ' ' ? 'espacio' : char)).join(' ')}${track === 1 ? ' (sin acentos ni ñ)' : ' (sólo números y =)'}`;
        return null;
    }

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
            handTool: false,
            spaceHeld: false,
            snapGrid: true,
            smartGuides: true,
            showSafe: true,
            pristine: true,
            cropping: null,
            pen: null,
            nodeEdit: null,
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
                    const size = { cover: 'cover', stretch: '100% 100%' }[item.image_fit] || 'contain';
                    if (url && item.recolor) {
                        // Logo de un solo color: la imagen se usa como máscara sobre el color elegido.
                        const tint = h('div', { class: 'cd-recolor', style: { background: item.recolor } });
                        ['maskImage', 'webkitMaskImage'].forEach((key) => { tint.style[key] = `url("${url}")`; });
                        ['maskSize', 'webkitMaskSize'].forEach((key) => { tint.style[key] = size; });
                        content.append(tint);
                    } else if (url) content.style.backgroundImage = `url("${url}")`;
                    else content.append(h('span', { class: 'cd-placeholder', text: 'IMAGEN' }));
                    content.style.backgroundSize = size;
                    if (item.grayscale && !item.recolor) content.style.filter = 'grayscale(1)';
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
                case 'line':
                case 'path':
                    content.classList.add('cd-vector');
                    content.append(vectorContent(item, boxPx, ptToPx));
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
            // Con zoom manual el lienzo tiene margen para llevar cualquier borde de la tarjeta al centro.
            const manual = state.zoomMode !== 'fit';
            el.shell.style.padding = manual ? `${Math.round(el.shell.clientHeight * 0.45)}px ${Math.round(el.shell.clientWidth * 0.45)}px` : '';
            el.shell.classList.toggle('cd-free', manual);
            $('cd-zoom-value').value = `${Math.round(pxPerMm / 3.7795 * 100)}%`;
            $('cd-zoom-fit').classList.toggle('active', !manual);
            const mm = (value) => value.toLocaleString('es-UY', { maximumFractionDigits: 2 });
            $('cd-size-note').textContent = `${mm(design().width_mm)} × ${mm(design().height_mm)} mm${design().double_sided ? ' · doble faz' : ''}`;
            renderMagGuide(pxPerMm);
            const safe = el.stage.querySelector('.cd-safe');
            safe.hidden = !state.showSafe;
            safe.style.inset = `${SAFE_MARGIN_MM * pxPerMm}px`;
            safe.style.borderRadius = `${Math.max(0, CARD_CORNER_MM - SAFE_MARGIN_MM / 2) * pxPerMm}px`;
        }

        function renderMagGuide(pxPerMm) {
            // Zona aproximada de la banda (ISO 7811: unos 4,5 a 16,5 mm desde el borde largo).
            let guide = el.stage.querySelector(':scope > .cd-magband');
            const mag = design().magstripe;
            if (!mag?.enabled || mag.side !== state.side) { guide?.remove(); return; }
            if (!guide) {
                guide = h('div', { class: 'cd-magband' }, [h('span', { text: 'Banda magnética (zona aproximada: evitá textos y códigos)' })]);
                el.stage.append(guide);
            }
            const portrait = design().height_mm > design().width_mm;
            Object.assign(guide.style, portrait
                ? { top: '0', bottom: '0', left: 'auto', right: `${4.5 * pxPerMm}px`, width: `${12 * pxPerMm}px`, height: 'auto' }
                : { left: '0', right: '0', top: `${4.5 * pxPerMm}px`, bottom: 'auto', height: `${12 * pxPerMm}px`, width: 'auto' });
            guide.classList.toggle('vertical', portrait);
        }

        function renderStage() {
            if (el.modal.hidden) return;
            layoutStage();
            renderSide(el.stage, side(), { photo: host.getCurrentPhoto(), interactive: true });
            renderSelection();
            renderVectorOverlay();
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
                if (items.length === 1 && !item.locked && state.cropping !== item.id && state.nodeEdit?.id !== item.id) {
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
            if (state.nodeEdit && (additive || ids.length !== 1 || ids[0] !== state.nodeEdit.id)) { state.nodeEdit = null; removeModeBanner(); }
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
                if (state.pen) return penPointerDown(event);
                if (state.nodeEdit && nodeEditPointerDown(event)) return undefined;
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
            el.stage.addEventListener('pointermove', (event) => {
                if (!state.pen) return;
                const point = stageMm(event).p;
                const last = state.pen.nodes[state.pen.nodes.length - 1];
                state.pen.cursor = event.shiftKey && last ? constrain45(last.p, point) : point;
                renderVectorOverlay();
            });
            el.stage.addEventListener('dblclick', (event) => {
                if (state.pen) { finishPen(false); return; }
                if (state.nodeEdit) return;
                const node = event.target.closest('.cd-element');
                const item = node && findElement(node.dataset.id);
                if (!item) return;
                if (item.type === 'photo') { enterCropMode(item); return; }
                if (item.type === 'path') { enterNodeEdit(item); return; }
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
                if (!event.ctrlKey && !event.altKey) return;
                // Ctrl+rueda (o pellizco en el panel táctil) acerca hacia el puntero.
                event.preventDefault();
                const delta = clamp(event.deltaMode === 1 ? event.deltaY * 33 : event.deltaY, -240, 240);
                zoomTo((state.pxPerMm || fitPxPerMm()) * Math.exp(-delta * 0.0022), event);
            }, { passive: false });
            el.shell.addEventListener('pointerdown', (event) => {
                const onBackground = event.target === el.shell;
                const panning = event.button === 1 || (event.button === 0 && (state.handTool || state.spaceHeld || onBackground));
                if (!panning) return;
                event.preventDefault();
                event.stopPropagation();
                startPan(event);
            }, true);
            el.shell.addEventListener('auxclick', (event) => { if (event.button === 1) event.preventDefault(); });
            new ResizeObserver(() => { if (!el.modal.hidden) renderStage(); }).observe(el.shell);
        }

        const MIN_PX_PER_MM = 0.8;
        const MAX_PX_PER_MM = 60;

        function zoomTo(pxPerMm, anchor = null) {
            // Mantiene fijo en pantalla el punto de la tarjeta bajo el puntero (o el centro del visor).
            const shellRect = el.shell.getBoundingClientRect();
            const before = el.stage.getBoundingClientRect();
            const x = anchor ? anchor.clientX : shellRect.left + shellRect.width / 2;
            const y = anchor ? anchor.clientY : shellRect.top + shellRect.height / 2;
            const k = before.width / design().width_mm || 1;
            const mmX = (x - before.left) / k;
            const mmY = (y - before.top) / k;
            state.zoomMode = 'manual';
            state.pxPerMm = clamp(pxPerMm, MIN_PX_PER_MM, MAX_PX_PER_MM);
            renderStage();
            const after = el.stage.getBoundingClientRect();
            el.shell.scrollLeft += after.left + mmX * state.pxPerMm - x;
            el.shell.scrollTop += after.top + mmY * state.pxPerMm - y;
        }

        function setZoom(pxPerMm) {
            zoomTo(pxPerMm);
        }

        function zoomFit() {
            state.zoomMode = 'fit';
            renderStage();
            el.shell.scrollLeft = 0;
            el.shell.scrollTop = 0;
        }

        function zoomToSelection() {
            const items = selectedElements();
            if (!items.length) { zoomFit(); return; }
            const bounds = boundsOf(items);
            const widthMm = Math.max(2, bounds.width * design().width_mm);
            const heightMm = Math.max(2, bounds.height * design().height_mm);
            const shellRect = el.shell.getBoundingClientRect();
            state.zoomMode = 'manual';
            state.pxPerMm = clamp(Math.min(shellRect.width * 0.7 / widthMm, shellRect.height * 0.7 / heightMm), MIN_PX_PER_MM, MAX_PX_PER_MM);
            renderStage();
            const stageRect = el.stage.getBoundingClientRect();
            const centerX = stageRect.left + (bounds.left + bounds.width / 2) * stageRect.width;
            const centerY = stageRect.top + (bounds.top + bounds.height / 2) * stageRect.height;
            el.shell.scrollLeft += centerX - (shellRect.left + shellRect.width / 2);
            el.shell.scrollTop += centerY - (shellRect.top + shellRect.height / 2);
        }

        function startPan(event) {
            if (state.zoomMode === 'fit') zoomTo(state.pxPerMm || fitPxPerMm());
            const start = { x: event.clientX, y: event.clientY, left: el.shell.scrollLeft, top: el.shell.scrollTop };
            el.shell.classList.add('cd-panning');
            const onMove = (moveEvent) => {
                el.shell.scrollLeft = start.left - (moveEvent.clientX - start.x);
                el.shell.scrollTop = start.top - (moveEvent.clientY - start.y);
            };
            const onUp = () => {
                el.shell.classList.remove('cd-panning');
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
        }

        function setHandTool(active) {
            state.handTool = active;
            if (active && state.pen) cancelPen();
            el.shell.classList.toggle('cd-hand', state.handTool || state.spaceHeld);
            $('cd-tool-hand').classList.toggle('active', state.handTool);
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
            const title = { text: 'Texto', photo: 'Fotografía', image: 'Imagen', qr: 'Código QR', barcode: 'Código de barras', rect: 'Forma', ellipse: 'Forma', line: 'Línea', path: 'Trazado' }[item.type];
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
                if (item.type === 'image') {
                    children.push(control('Pintar de un color', colorInput(item.recolor, (value) => { item.recolor = value; }, { optional: true }), {
                        wide: true, note: 'Para logos SVG o PNG con fondo transparente, por ejemplo en blanco sobre una banda.',
                    }));
                }
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
            } else if (item.type === 'rect' || item.type === 'ellipse' || item.type === 'path') {
                children.push(presetControls(item), ...fillControls(item), strokeControls(item));
                if (item.type === 'rect') children.push(control('Radio esquinas pt', numberInput(item.radius || 0, { min: 0, max: 200, step: 0.5 }, (value) => { item.radius = value; })));
                if (item.type === 'path') {
                    children.push(control('Superposiciones', selectInput([['evenodd', 'Dejan hueco (par-impar)'], ['nonzero', 'Se rellenan (distinto de cero)']], item.fill_rule || 'evenodd', (value) => { item.fill_rule = value; }), { wide: true }));
                }
            } else if (item.type === 'line') {
                children.push(strokeControls(item));
            }
            if (CONVERTIBLE.includes(item.type)) {
                children.push(h('button', {
                    class: 'btn secondary compact wide', type: 'button', text: '✒ Convertir a curvas (Ctrl+Q)', disabled: item.locked,
                    title: 'Lo transforma en un trazado con nodos editables, como en Corel', onclick: () => convertToCurves([item]),
                }));
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

        function magstripeSection() {
            const mag = design().magstripe || (design().magstripe = defaultMagstripe());
            const enabled = h('input', { type: 'checkbox', checked: Boolean(mag.enabled) });
            enabled.addEventListener('change', () => change(() => { mag.enabled = enabled.checked; }));
            const children = [
                h('div', { class: 'cd-section-title', text: 'Banda magnética' }),
                h('label', { class: 'designer-check' }, [enabled, h('span', { text: 'Codificar la banda al imprimir' })]),
            ];
            if (mag.enabled) {
                const values = valuesFor(host.getCurrentPhoto());
                children.push(control('La banda está en', selectInput([['back', 'El dorso'], ['front', 'El frente']], mag.side, (value) => { mag.side = value; }), { wide: true }));
                [1, 2, 3].forEach((track) => {
                    const key = `track${track}`;
                    const input = h('input', { type: 'text', maxlength: 200, placeholder: track === 1 ? 'Ej.: {Apellido}^{Nombre}' : 'Ej.: {Legajo}' });
                    input.value = mag[key] || '';
                    const preview = h('small', { class: 'cd-mag-preview' });
                    const refresh = () => {
                        const data = normalizeMagTrack(track, resolveFields(mag[key], values));
                        const error = magTrackError(track, data);
                        preview.className = `cd-mag-preview${error ? ' error' : ''}`;
                        preview.textContent = !mag[key]?.trim() ? 'Sin usar' : error ? `⚠ ${error}` : `Esta credencial: ${data || '(vacío)'}`;
                    };
                    bindLive(input, () => { mag[key] = input.value; refresh(); });
                    refresh();
                    children.push(
                        h('div', { class: 'cd-label-row' }, [
                            h('span', { text: `Pista ${track} · ${track === 1 ? 'letras y números, hasta 76' : track === 2 ? 'números, hasta 37' : 'números, hasta 104'}` }),
                            fieldPicker((token) => insertAtCursor(input, token, (value) => { mag[key] = value; refresh(); })),
                        ]),
                        input,
                        preview,
                    );
                });
                children.push(h('small', { class: 'cd-hint', text: 'Los centinelas (% ; ?) los agrega la impresora. La pista 1 va en mayúsculas sin acentos; ^ separa campos. Elegí la marca y los comandos en Imprimir…' }));
            }
            return h('section', { class: 'cd-section' }, children);
        }

        function sidePropertiesSection() {
            const current = side();
            const options = [['', 'Sin imagen'], ...state.assets.map((asset) => [asset.asset_id, asset.filename])];
            const colors = new Set();
            ['front', 'back'].forEach((key) => {
                colors.add(design()[key].background_color);
                design()[key].elements.forEach((item) => {
                    ['color', 'fill', 'stroke_color', 'background', 'recolor'].forEach((prop) => { if (item[prop]) colors.add(item[prop].toLowerCase()); });
                    if (item.gradient) { colors.add(item.gradient.start.toLowerCase()); colors.add(item.gradient.end.toLowerCase()); }
                });
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
                magstripeSection(),
                h('section', { class: 'cd-section' }, [
                    h('div', { class: 'cd-section-title', text: 'Reemplazar color en todo el diseño' }),
                    h('div', { class: 'cd-grid2' }, [control('Color actual', from), control('Nuevo color', to)]),
                    h('button', {
                        class: 'btn secondary compact wide', type: 'button', text: 'Reemplazar',
                        onclick: () => change(() => ['front', 'back'].forEach((key) => {
                            const sideData = design()[key];
                            if (sideData.background_color.toLowerCase() === from.value) sideData.background_color = to.value;
                            sideData.elements.forEach((item) => {
                                ['color', 'fill', 'stroke_color', 'background', 'recolor'].forEach((prop) => { if (item[prop] && item[prop].toLowerCase() === from.value) item[prop] = to.value; });
                                if (item.gradient) ['start', 'end'].forEach((prop) => { if (item.gradient[prop].toLowerCase() === from.value) item.gradient[prop] = to.value; });
                            });
                        })),
                    }),
                ]),
                h('section', { class: 'cd-section cd-shortcuts' }, [
                    h('div', { class: 'cd-section-title', text: 'Atajos' }),
                    h('p', { class: 'field-note', text: 'Clic + Mayús: selección múltiple · Arrastrar en vacío: seleccionar área · Flechas: mover 0,5 mm (Mayús: 5 mm) · Ctrl+D duplicar · Ctrl+C / Ctrl+V · Supr eliminar · Ctrl+Z / Ctrl+Y · Alt al arrastrar: sin imán · Ctrl+rueda: zoom hacia el puntero · Espacio o rueda apretada + arrastrar: mover la vista · H: mano · Ctrl+0: encajar · Ctrl+1: 1:1 · Mayús+2: zoom a la selección · P: pluma · Ctrl+Q: convertir a curvas · doble clic en un trazado: editar nodos' }),
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
            el.properties.replaceChildren(...[
                h('section', { class: 'cd-section' }, [control('Nombre del objeto', name, { wide: true })]),
                item.type === 'photo' ? framingSection(item) : null,
                typeSection(item),
                item.type === 'path' ? nodeSection(item) : null,
                geometrySection(item),
                conditionSection(item),
                h('section', { class: 'cd-section' }, [h('div', { class: 'cd-button-row' }, [
                    h('button', { class: 'btn secondary compact', type: 'button', text: item.locked ? '🔒 Desbloquear' : '🔓 Bloquear', onclick: () => change(() => { item.locked = !item.locked; }) }),
                    h('button', { class: 'btn secondary compact', type: 'button', text: '⧉ Duplicar', onclick: duplicateSelected }),
                    h('button', { class: 'btn secondary compact danger-outline', type: 'button', text: '🗑 Eliminar', disabled: item.locked, onclick: removeSelected }),
                ])]),
            ].filter(Boolean));
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
            $('cd-tool-pen')?.classList.toggle('active', Boolean(state.pen));
            $('cd-undo').disabled = !state.history.length;
            $('cd-redo').disabled = !state.future.length;
            const hasSelection = state.selected.length > 0;
            document.querySelectorAll('[data-cd-needs-selection]').forEach((button) => { button.disabled = !hasSelection; });
            document.querySelectorAll('[data-cd-needs-multi]').forEach((button) => { button.disabled = state.selected.length < Number(button.dataset.cdNeedsMulti); });
        }


        // ------------------------------ formas vectoriales ------------------------------ //

        function vectorContent(item, boxPx, ptToPx) {
            const { w, h } = boxPx;
            const strokePx = item.type === 'line'
                ? (item.stroke_width || 1) * ptToPx
                : (item.stroke_color ? (item.stroke_width || 0) * ptToPx : 0);
            const strokeColor = item.type === 'line' ? (item.stroke_color || '#17202b') : item.stroke_color;
            const root = svgNode('svg', { class: 'cd-svg', width: w, height: h, viewBox: `0 0 ${w} ${h}`, overflow: 'visible' });
            const defs = svgNode('defs');
            root.append(defs);
            const fillPaint = () => {
                const gradient = item.gradient;
                if (!gradient) return item.fill || 'none';
                const id = `cdg${svgUid += 1}`;
                const stops = [svgNode('stop', { offset: 0, 'stop-color': gradient.start }), svgNode('stop', { offset: 1, 'stop-color': gradient.end })];
                if (gradient.kind === 'radial') {
                    const ratio = h / Math.max(w, 1e-6);
                    defs.append(svgNode('radialGradient', {
                        id, gradientUnits: 'userSpaceOnUse', cx: w / 2, cy: h / 2, r: w / 2,
                        gradientTransform: `translate(${w / 2} ${h / 2}) scale(1 ${ratio}) translate(${-w / 2} ${-h / 2})`,
                    }, stops));
                } else {
                    const angle = (gradient.angle || 0) * Math.PI / 180;
                    const dx = Math.cos(angle); const dy = Math.sin(angle);
                    const extent = Math.abs(w * dx) + Math.abs(h * dy);
                    defs.append(svgNode('linearGradient', {
                        id, gradientUnits: 'userSpaceOnUse',
                        x1: w / 2 - dx * extent / 2, y1: h / 2 - dy * extent / 2, x2: w / 2 + dx * extent / 2, y2: h / 2 + dy * extent / 2,
                    }, stops));
                }
                return `url(#${id})`;
            };
            const stroke = strokePx > 0 && strokeColor ? {
                stroke: strokeColor, 'stroke-width': strokePx, 'stroke-linecap': item.line_cap || 'butt',
                'stroke-linejoin': item.line_join || 'miter', 'stroke-miterlimit': 10,
                'stroke-dasharray': DASH_PATTERNS[item.dash] ? DASH_PATTERNS[item.dash].map((value) => value * strokePx).join(' ') : null,
                fill: 'none',
            } : null;
            const hasFill = Boolean(item.fill || item.gradient);
            if (item.type === 'rect' || item.type === 'ellipse') {
                const radius = item.type === 'rect' ? Math.min((item.radius || 0) * ptToPx, w / 2, h / 2) : 0;
                const inset = stroke ? strokePx / 2 : 0;
                const shape = (pad, attrs) => (item.type === 'ellipse'
                    ? svgNode('ellipse', { cx: w / 2, cy: h / 2, rx: Math.max(0.1, w / 2 - pad), ry: Math.max(0.1, h / 2 - pad), ...attrs })
                    : svgNode('rect', { x: pad, y: pad, width: Math.max(0.1, w - pad * 2), height: Math.max(0.1, h - pad * 2), rx: Math.max(0, radius - pad), ...attrs }));
                if (hasFill) root.append(shape(0, { fill: fillPaint() }));
                if (stroke) root.append(shape(inset, stroke));
            } else if (item.type === 'line') {
                if (stroke) root.append(svgNode('line', { x1: 0, y1: h / 2, x2: w, y2: h / 2, ...stroke }));
            } else {
                const fill = hasFill ? fillPaint() : 'none';
                root.append(svgNode('path', { d: pathData(item.paths || [], w, h), ...(stroke || {}), fill, 'fill-rule': item.fill_rule || 'evenodd' }));
            }
            return root;
        }

        const mmW = () => design().width_mm;
        const mmH = () => design().height_mm;

        function stageMm(event) {
            const point = stagePoint(event);
            return { p: [point.x * mmW(), point.y * mmH()], rect: point.rect, k: point.rect.width / mmW() };
        }

        function itemFrame(item) {
            const W = mmW(); const H = mmH();
            return { w: item.w * W, h: item.h * H, cx: (item.x + item.w / 2) * W, cy: (item.y + item.h / 2) * H, a: (item.rotation || 0) * Math.PI / 180 };
        }

        function localToCard(frame, [x, y]) {
            const dx = x - frame.w / 2; const dy = y - frame.h / 2;
            const cos = Math.cos(frame.a); const sin = Math.sin(frame.a);
            return [frame.cx + dx * cos - dy * sin, frame.cy + dx * sin + dy * cos];
        }

        function cardToLocal(frame, [x, y]) {
            const dx = x - frame.cx; const dy = y - frame.cy;
            const cos = Math.cos(frame.a); const sin = Math.sin(frame.a);
            return [dx * cos + dy * sin + frame.w / 2, -dx * sin + dy * cos + frame.h / 2];
        }

        function absolutePaths(item) {
            const frame = itemFrame(item);
            return mapPaths(item.paths || [], ([u, v]) => localToCard(frame, [u * frame.w, v * frame.h]));
        }

        function pathFromAbsolute(paths, props = {}) {
            const fit = fitUnit(paths);
            if (!fit) return null;
            const { left, top, width, height } = fit.box;
            return makeElement('path', { x: left / mmW(), y: top / mmH(), w: width / mmW(), h: height / mmH(), rotation: 0, paths: fit.paths, ...props });
        }

        function refitPath(item) {
            // Ajusta la caja al trazado editado sin moverlo en la tarjeta (respeta el giro).
            const frame = itemFrame(item);
            const fit = fitUnit(mapPaths(item.paths, ([u, v]) => [u * frame.w, v * frame.h]));
            if (!fit) return;
            const { left, top, width, height } = fit.box;
            const ox = left + width / 2 - frame.w / 2;
            const oy = top + height / 2 - frame.h / 2;
            const cos = Math.cos(frame.a); const sin = Math.sin(frame.a);
            const cx = frame.cx + ox * cos - oy * sin;
            const cy = frame.cy + ox * sin + oy * cos;
            item.paths = fit.paths;
            item.w = width / mmW();
            item.h = height / mmH();
            item.x = (cx - width / 2) / mmW();
            item.y = (cy - height / 2) / mmH();
        }

        function styleFrom(item) {
            const keep = { opacity: item.opacity ?? 1, condition: item.condition ? clone(item.condition) : null };
            if (['path', 'rect', 'ellipse'].includes(item.type)) {
                if (!item.fill && !item.gradient && item.type === 'path') return { ...keep, fill: item.stroke_color || '#17202b', stroke_color: null, stroke_width: 0 };
                return {
                    ...keep, fill: item.fill || null, gradient: item.gradient ? clone(item.gradient) : null, stroke_color: item.stroke_color || null,
                    stroke_width: item.stroke_width || 0, dash: item.dash || 'solid', line_join: item.line_join || 'round', line_cap: item.line_cap || 'round',
                };
            }
            if (item.type === 'line') return { ...keep, fill: item.stroke_color || '#17202b', stroke_color: null, stroke_width: 0 };
            return { ...keep, fill: item.color || '#17202b', stroke_color: null, stroke_width: 0 };
        }

        function showModeBanner(text, buttons) {
            removeModeBanner();
            el.shell.parentElement.append(h('div', { class: 'cd-crop-banner cd-mode-banner' }, [
                h('span', { text }),
                ...buttons.map(([label, action, secondary]) => h('button', { class: `btn compact${secondary ? ' secondary' : ''}`, type: 'button', text: label, onclick: action })),
            ]));
        }

        function removeModeBanner() {
            el.shell.parentElement.querySelectorAll('.cd-mode-banner').forEach((node) => node.remove());
        }

        function overlayRoot() {
            let root = el.stage.querySelector(':scope > .cd-vector-overlay');
            if (!root) {
                root = svgNode('svg', { class: 'cd-vector-overlay' });
                el.stage.append(root);
            }
            return root;
        }

        function renderVectorOverlay() {
            const root = overlayRoot();
            root.replaceChildren();
            const active = Boolean(state.pen || state.nodeEdit);
            root.classList.toggle('active', active);
            if (!active) return;
            const width = el.stage.clientWidth;
            const height = el.stage.clientHeight;
            if (!width) return;
            const k = width / mmW();
            root.setAttribute('viewBox', `0 0 ${width} ${height}`);
            root.setAttribute('width', width);
            root.setAttribute('height', height);
            const handle = (node, which, toPx, key) => {
                if (!node[which]) return;
                const a = toPx(node.p); const b = toPx(node[which]);
                root.append(svgNode('line', { class: 'cd-ov-arm', x1: a[0], y1: a[1], x2: b[0], y2: b[1] }));
                root.append(svgNode('circle', { class: 'cd-ov-handle', cx: b[0], cy: b[1], r: 4.5, 'data-role': 'handle', 'data-key': key, 'data-which': which }));
            };
            const square = (point, attrs) => svgNode('rect', { x: point[0] - 4.5, y: point[1] - 4.5, width: 9, height: 9, ...attrs });
            if (state.pen) {
                const toPx = ([x, y]) => [x * k, y * k];
                const nodes = state.pen.nodes;
                if (!nodes.length) return;
                const scaled = mapPaths([{ closed: false, nodes }], toPx);
                root.append(svgNode('path', { class: 'cd-ov-path', d: pathData(scaled) }));
                const last = nodes[nodes.length - 1];
                if (state.pen.cursor && !state.pen.dragging) {
                    const from = toPx(last.p); const to = toPx(state.pen.cursor);
                    const c1 = last.o ? toPx(last.o) : from;
                    root.append(svgNode('path', { class: 'cd-ov-rubber', d: `M${from[0]} ${from[1]}C${c1[0]} ${c1[1]} ${to[0]} ${to[1]} ${to[0]} ${to[1]}` }));
                }
                handle(last, 'i', toPx, '');
                handle(last, 'o', toPx, '');
                nodes.forEach((entry, index) => root.append(square(toPx(entry.p), { class: `cd-ov-node${index === 0 ? ' first' : ''}` })));
                return;
            }
            const item = findElement(state.nodeEdit.id);
            if (!item) return;
            const frame = itemFrame(item);
            const toPx = ([u, v]) => { const [x, y] = localToCard(frame, [u * frame.w, v * frame.h]); return [x * k, y * k]; };
            const scaled = mapPaths(item.paths, toPx);
            const d = pathData(scaled);
            root.append(svgNode('path', { class: 'cd-ov-hit', d, 'data-role': 'segment' }));
            root.append(svgNode('path', { class: 'cd-ov-path', d }));
            item.paths.forEach((sub, si) => sub.nodes.forEach((entry, ni) => {
                const key = `${si}:${ni}`;
                if (!state.nodeEdit.sel.has(key)) return;
                handle(entry, 'i', toPx, key);
                handle(entry, 'o', toPx, key);
            }));
            item.paths.forEach((sub, si) => sub.nodes.forEach((entry, ni) => {
                const key = `${si}:${ni}`;
                const point = toPx(entry.p);
                const attrs = { class: `cd-ov-node${state.nodeEdit.sel.has(key) ? ' selected' : ''}${entry.s ? ' smooth' : ''}`, 'data-role': 'node', 'data-key': key };
                root.append(entry.s ? svgNode('circle', { cx: point[0], cy: point[1], r: 5, ...attrs }) : square(point, attrs));
            }));
        }

        // ---- pluma ----

        function startPen() {
            if (state.cropping) exitCropMode({ quiet: true });
            if (state.nodeEdit) exitNodeEdit();
            state.pen = { nodes: [], cursor: null, dragging: false };
            state.selected = [];
            el.stage.classList.add('cd-pen-mode');
            showModeBanner('Pluma: clic = nodo en punta · arrastrar = curva · Mayús = ángulos de 45° · clic en el primer nodo cierra la forma · Enter o doble clic termina · Retroceso borra el último nodo', [
                ['Terminar', () => finishPen(false)], ['Cancelar', cancelPen, true],
            ]);
            render();
        }

        function cancelPen() {
            state.pen = null;
            el.stage.classList.remove('cd-pen-mode');
            removeModeBanner();
            renderVectorOverlay();
            updateToolbar();
        }

        function constrain45(from, to) {
            const dx = to[0] - from[0]; const dy = to[1] - from[1];
            const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
            const length = Math.hypot(dx, dy);
            return [from[0] + Math.cos(angle) * length, from[1] + Math.sin(angle) * length];
        }

        function penPointerDown(event) {
            const pen = state.pen;
            const start = stageMm(event);
            const last = pen.nodes[pen.nodes.length - 1];
            const p = event.shiftKey && last ? constrain45(last.p, start.p) : start.p;
            if (pen.nodes.length >= 2 && dist(p, pen.nodes[0].p) * start.k < 9) { finishPen(true); return; }
            if (last && dist(p, last.p) * start.k < 3) return;
            const entry = { p, i: null, o: null };
            pen.nodes.push(entry);
            pen.dragging = true;
            const onMove = (moveEvent) => {
                const point = stageMm(moveEvent);
                const dx = point.p[0] - p[0]; const dy = point.p[1] - p[1];
                if (Math.hypot(dx, dy) * point.k < 7) { entry.i = null; entry.o = null; delete entry.s; }
                else { entry.o = [p[0] + dx, p[1] + dy]; entry.i = [p[0] - dx, p[1] - dy]; entry.s = true; }
                renderVectorOverlay();
            };
            const onUp = () => {
                pen.dragging = false;
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
                renderVectorOverlay();
            };
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
            renderVectorOverlay();
        }

        function finishPen(closed) {
            const pen = state.pen;
            if (!pen) return;
            const nodes = pen.nodes;
            cancelPen();
            if (nodes.length < 2) { host.setStatus('El trazado necesita al menos dos nodos.', 'error'); render(); return; }
            const style = closed
                ? { fill: '#176b87', stroke_color: null, stroke_width: 0 }
                : { fill: null, stroke_color: '#17202b', stroke_width: 1, line_cap: 'round', line_join: 'round' };
            const item = pathFromAbsolute([{ closed, nodes }], style);
            if (!item) return;
            change(() => elements().push(item));
            select([item.id]);
            host.setStatus('Trazado creado. Doble clic sobre él para editar los nodos.');
        }

        // ---- edición de nodos ----

        async function enterNodeEdit(item) {
            if (!item || item.locked) return;
            let target = item;
            if (item.type !== 'path') {
                const created = await convertToCurves([item], { quiet: true });
                if (created.length !== 1) { if (created.length) host.setStatus('El objeto quedó en varias piezas: elegí una para editar sus nodos.'); return; }
                [target] = created;
            }
            if (state.cropping) exitCropMode({ quiet: true });
            if (state.pen) cancelPen();
            if (target.preset) change(() => { target.preset = null; }, { panel: false });
            state.nodeEdit = { id: target.id, sel: new Set() };
            state.selected = [target.id];
            showModeBanner('Nodos: arrastrá nodos o manejadores · clic sobre la línea agrega un nodo · Mayús suma a la selección · Alt quiebra el manejador · Supr borra · Enter o Esc termina', [
                ['Terminar', () => exitNodeEdit()],
            ]);
            render();
        }

        function exitNodeEdit() {
            if (!state.nodeEdit) return;
            state.nodeEdit = null;
            removeModeBanner();
            render();
        }

        function nodeEditTarget() {
            const item = state.nodeEdit && findElement(state.nodeEdit.id);
            if (!item || item.type !== 'path') { if (state.nodeEdit) exitNodeEdit(); return null; }
            return item;
        }

        function selectedNodes(item) {
            return [...state.nodeEdit.sel].map((key) => {
                const [si, ni] = key.split(':').map(Number);
                const node = item.paths[si]?.nodes[ni];
                return node ? { si, ni, node, key } : null;
            }).filter(Boolean);
        }

        function splitSegment(item, si, index, t) {
            const sub = item.paths[si];
            const start = sub.nodes[index];
            const endIndex = (index + 1) % sub.nodes.length;
            const end = sub.nodes[endIndex];
            let created;
            if (!start.o && !end.i) {
                created = { p: lerp(start.p, end.p, t), i: null, o: null };
            } else {
                const p0 = start.p; const c1 = start.o || start.p; const c2 = end.i || end.p; const p3 = end.p;
                const q0 = lerp(p0, c1, t); const q1 = lerp(c1, c2, t); const q2 = lerp(c2, p3, t);
                const r0 = lerp(q0, q1, t); const r1 = lerp(q1, q2, t);
                created = { p: lerp(r0, r1, t), i: r0, o: r1, s: true };
                start.o = q0;
                end.i = q2;
            }
            sub.nodes.splice(index + 1, 0, created);
            return `${si}:${index + 1}`;
        }

        function nodeEditPointerDown(event) {
            const item = nodeEditTarget();
            if (!item) return false;
            const role = event.target.dataset?.role;
            const frame = itemFrame(item);
            const toUnit = (pointerEvent) => {
                const [x, y] = cardToLocal(frame, stageMm(pointerEvent).p);
                return [x / frame.w, y / frame.h];
            };
            const toMm = ([u, v]) => [u * frame.w, v * frame.h];
            const fromMm = ([x, y]) => [x / frame.w, y / frame.h];
            const drag = (onMove) => {
                const before = snapshot();
                let moved = false;
                const move = (moveEvent) => { moved = true; onMove(moveEvent); renderStage(); };
                const up = () => {
                    window.removeEventListener('pointermove', move);
                    window.removeEventListener('pointerup', up);
                    if (moved) refitPath(item);
                    commit(before);
                    render();
                };
                window.addEventListener('pointermove', move);
                window.addEventListener('pointerup', up);
            };
            if (role === 'node') {
                const key = event.target.dataset.key;
                const sel = state.nodeEdit.sel;
                if (event.shiftKey) { if (sel.has(key)) sel.delete(key); else sel.add(key); } else if (!sel.has(key)) state.nodeEdit.sel = new Set([key]);
                renderVectorOverlay();
                const start = toUnit(event);
                const originals = selectedNodes(item).map((entry) => ({ node: entry.node, copy: clone(entry.node) }));
                drag((moveEvent) => {
                    const now = toUnit(moveEvent);
                    const du = now[0] - start[0]; const dv = now[1] - start[1];
                    const shift = (point) => (point ? [point[0] + du, point[1] + dv] : null);
                    originals.forEach(({ node, copy }) => { node.p = shift(copy.p); node.i = shift(copy.i); node.o = shift(copy.o); });
                });
                return true;
            }
            if (role === 'handle') {
                const [si, ni] = event.target.dataset.key.split(':').map(Number);
                const which = event.target.dataset.which;
                const other = which === 'i' ? 'o' : 'i';
                const node = item.paths[si].nodes[ni];
                drag((moveEvent) => {
                    node[which] = toUnit(moveEvent);
                    if (moveEvent.altKey) { delete node.s; return; }
                    if (node.s && node[other]) {
                        // Nodo suave: el manejador opuesto sigue la dirección y conserva su largo.
                        const center = toMm(node.p);
                        const moved = toMm(node[which]);
                        const length = dist(center, toMm(node[other]));
                        const span = dist(center, moved) || 1;
                        node[other] = fromMm([center[0] - (moved[0] - center[0]) / span * length, center[1] - (moved[1] - center[1]) / span * length]);
                    }
                });
                return true;
            }
            if (role === 'segment') {
                const point = stageMm(event);
                const k = point.k;
                const target = [point.p[0] * k, point.p[1] * k];
                let best = null;
                item.paths.forEach((sub, si) => subSegments(sub).forEach((segment) => {
                    for (let step = 1; step < 64; step += 1) {
                        const t = step / 64;
                        const unit = segment.c1 ? cubicAt(segment.p0, segment.c1, segment.c2, segment.p3, t) : lerp(segment.p0, segment.p3, t);
                        const [x, y] = localToCard(frame, toMm(unit));
                        const gap = Math.hypot(x * k - target[0], y * k - target[1]);
                        if (!best || gap < best.gap) best = { gap, si, index: segment.index, t };
                    }
                }));
                if (best && best.gap < 10) {
                    const before = snapshot();
                    const key = splitSegment(item, best.si, best.index, best.t);
                    state.nodeEdit.sel = new Set([key]);
                    commit(before);
                    render();
                }
                return true;
            }
            const node = event.target.closest('.cd-element');
            if (node?.dataset.id === item.id || event.target.closest('.cd-vector-overlay')) {
                state.nodeEdit.sel = new Set();
                renderVectorOverlay();
                return true;
            }
            exitNodeEdit();
            return false;
        }

        function editNodes(mutator, message) {
            const item = nodeEditTarget();
            if (!item) return;
            const chosen = selectedNodes(item);
            if (!chosen.length && message) { host.setStatus(message, 'error'); return; }
            change(() => { mutator(item, chosen); refitPath(item); }, { panel: true });
        }

        function deleteNodes() {
            editNodes((item, chosen) => {
                const doomed = new Set(chosen.map((entry) => entry.key));
                item.paths = item.paths.map((sub, si) => ({ ...sub, nodes: sub.nodes.filter((_node, ni) => !doomed.has(`${si}:${ni}`)) }))
                    .filter((sub) => sub.nodes.length >= 2);
                state.nodeEdit.sel = new Set();
            }, 'Elegí los nodos a borrar.');
            const item = nodeEditTarget();
            if (item && !item.paths.length) {
                exitNodeEdit();
                change(() => { side().elements = elements().filter((entry) => entry.id !== item.id); });
                state.selected = [];
                render();
            }
        }

        function setNodesSmooth(smooth) {
            editNodes((item, chosen) => chosen.forEach(({ node }) => {
                if (!smooth) { delete node.s; return; }
                node.s = true;
                const frame = itemFrame(item);
                const toMm = ([u, v]) => [u * frame.w, v * frame.h];
                const fromMm = ([x, y]) => [x / frame.w, y / frame.h];
                const center = toMm(node.p);
                const into = node.i ? toMm(node.i) : null;
                const out = node.o ? toMm(node.o) : null;
                if (!into && !out) return;
                const direction = into && out ? [out[0] - into[0], out[1] - into[1]] : out ? [out[0] - center[0], out[1] - center[1]] : [center[0] - into[0], center[1] - into[1]];
                const span = Math.hypot(...direction) || 1;
                const unit = [direction[0] / span, direction[1] / span];
                const lengthOut = out ? dist(center, out) : dist(center, into);
                const lengthIn = into ? dist(center, into) : dist(center, out);
                node.o = fromMm([center[0] + unit[0] * lengthOut, center[1] + unit[1] * lengthOut]);
                node.i = fromMm([center[0] - unit[0] * lengthIn, center[1] - unit[1] * lengthIn]);
            }), 'Elegí uno o más nodos.');
        }

        function setSegmentsKind(curve) {
            editNodes((item, chosen) => chosen.forEach(({ si, ni, node }) => {
                const nodes = item.paths[si].nodes;
                const closed = item.paths[si].closed;
                const prev = ni > 0 ? nodes[ni - 1] : (closed ? nodes[nodes.length - 1] : null);
                const next = ni < nodes.length - 1 ? nodes[ni + 1] : (closed ? nodes[0] : null);
                if (!curve) {
                    node.i = null; node.o = null; delete node.s;
                    if (prev) prev.o = null;
                    if (next) next.i = null;
                    return;
                }
                if (next && !node.o && !next.i) { node.o = lerp(node.p, next.p, 1 / 3); next.i = lerp(next.p, node.p, 1 / 3); }
                if (prev && !node.i && !prev.o) { node.i = lerp(node.p, prev.p, 1 / 3); prev.o = lerp(prev.p, node.p, 1 / 3); }
            }), 'Elegí uno o más nodos.');
        }

        function toggleClosed() {
            editNodes((item, chosen) => {
                const subs = chosen.length ? [...new Set(chosen.map((entry) => entry.si))] : item.paths.map((_sub, si) => si);
                subs.forEach((si) => { item.paths[si].closed = !item.paths[si].closed; });
            });
        }

        function nudgeNodes(dx, dy) {
            editNodes((item, chosen) => {
                const frame = itemFrame(item);
                const cos = Math.cos(frame.a); const sin = Math.sin(frame.a);
                const du = (dx * cos + dy * sin) / frame.w;
                const dv = (-dx * sin + dy * cos) / frame.h;
                const shift = (point) => (point ? [point[0] + du, point[1] + dv] : null);
                chosen.forEach(({ node }) => { node.p = shift(node.p); node.i = shift(node.i); node.o = shift(node.o); });
            });
        }

        function nodeSection(item) {
            const count = item.paths.reduce((total, sub) => total + sub.nodes.length, 0);
            const editing = state.nodeEdit?.id === item.id;
            const children = [
                h('div', { class: 'cd-section-title', text: 'Nodos' }),
                h('p', { class: 'field-note', text: `${count} nodo${count === 1 ? '' : 's'} · ${item.paths.length} subtrazado${item.paths.length === 1 ? '' : 's'}${editing ? ` · ${state.nodeEdit.sel.size} elegido${state.nodeEdit.sel.size === 1 ? '' : 's'}` : ''}` }),
            ];
            if (!editing) {
                children.push(h('button', { class: 'btn secondary compact wide', type: 'button', text: '✎ Editar nodos (doble clic)', disabled: item.locked, onclick: () => enterNodeEdit(item) }));
            } else {
                const button = (text, title, action) => h('button', { class: 'btn secondary compact', type: 'button', text, title, onclick: action });
                children.push(
                    h('div', { class: 'cd-button-row' }, [
                        button('◇ Punta', 'Nodo en punta: los manejadores se mueven por separado', () => setNodesSmooth(false)),
                        button('● Suave', 'Nodo suave: manejadores alineados', () => setNodesSmooth(true)),
                    ]),
                    h('div', { class: 'cd-button-row' }, [
                        button('╱ A recta', 'Convierte en recta los tramos de los nodos elegidos', () => setSegmentsKind(false)),
                        button('⌒ A curva', 'Convierte en curva los tramos de los nodos elegidos', () => setSegmentsKind(true)),
                    ]),
                    h('div', { class: 'cd-button-row' }, [
                        button('⊂⊃ Abrir/cerrar', 'Abre o cierra el subtrazado', toggleClosed),
                        button('🗑 Borrar nodo', 'Supr', deleteNodes),
                    ]),
                    h('button', { class: 'btn compact wide', type: 'button', text: 'Terminar edición', onclick: () => exitNodeEdit() }),
                );
            }
            return h('section', { class: 'cd-section' }, children);
        }

        // ---- convertir, combinar y operaciones ----

        async function vectorApi(path, body) {
            const response = await host.api(`/vector/${path}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ width_mm: mmW(), height_mm: mmH(), values: valuesFor(host.getCurrentPhoto()), ...body }),
            });
            return response.json();
        }

        const CONVERTIBLE = ['text', 'qr', 'barcode', 'rect', 'ellipse', 'line'];

        async function convertToCurves(items = selectedElements(), { quiet = false, select: reselect = true } = {}) {
            const sources = items.filter((item) => !item.locked && CONVERTIBLE.includes(item.type));
            if (!sources.length) {
                if (!quiet) host.setStatus(items.some((item) => item.type === 'path') ? 'Ya es un trazado: doble clic para editar los nodos.' : 'Las fotos e imágenes no se convierten a curvas. Usá textos, códigos o formas.', 'error');
                return [];
            }
            const variable = sources.filter((item) => /\{[^{}]+\}/.test(`${item.text || ''}${item.value || ''}`));
            if (variable.length && !window.confirm('Hay textos o códigos con campos variables. Al convertirlos a curvas quedan fijos con los datos de esta credencial. ¿Continuar?')) return [];
            host.setBusy(true);
            try {
                const data = await vectorApi('outline', { elements: sources });
                const created = [];
                change(() => data.results.forEach((result) => {
                    const index = elements().findIndex((entry) => entry.id === result.source);
                    if (index < 0) return;
                    const made = result.elements.map((props) => makeElement('path', { ...props, id: newId(), preset: null }));
                    elements().splice(index, 1, ...made);
                    created.push(...made);
                }));
                if (reselect) select(created.map((entry) => entry.id));
                if (!quiet) host.setStatus(`Convertido a curvas: ${created.length} trazado${created.length === 1 ? '' : 's'}. Doble clic para editar los nodos.`);
                return created;
            } catch (error) {
                host.setStatus(error.message, 'error');
                return [];
            } finally {
                host.setBusy(false);
            }
        }

        const orderedSelection = () => elements().filter((item) => state.selected.includes(item.id));

        async function booleanOperation(operation) {
            const items = orderedSelection().filter((item) => !item.hidden);
            if (items.length < 2) return host.setStatus('Seleccioná al menos dos formas.', 'error');
            if (items.some((item) => item.locked)) return host.setStatus('Hay objetos bloqueados en la selección.', 'error');
            if (items.some((item) => item.type === 'photo' || item.type === 'image')) return host.setStatus('Las fotos e imágenes no se pueden combinar: usá formas, trazados o textos.', 'error');
            host.setBusy(true);
            try {
                const data = await vectorApi('boolean', { operation, elements: items });
                const base = items[0];
                const result = makeElement('path', { ...data.element, ...styleFrom(base), name: '' });
                change(() => {
                    const list = elements();
                    const ids = new Set(items.map((item) => item.id));
                    if (operation === 'intersection') {
                        list.splice(list.indexOf(items[items.length - 1]) + 1, 0, result);
                    } else {
                        const index = list.indexOf(base);
                        const kept = list.filter((item, position) => !ids.has(item.id) || position === index);
                        kept.splice(kept.indexOf(base), 1, result);
                        side().elements = kept;
                    }
                });
                select([result.id]);
                const labels = { union: 'Formas soldadas', difference: 'Forma de abajo recortada: las de arriba se usaron como molde', intersection: 'Intersección creada (los originales quedan debajo)', xor: 'Superposición excluida' };
                host.setStatus(`${labels[operation]}. Doble clic para editar los nodos.`);
            } catch (error) {
                host.setStatus(error.message, 'error');
            } finally {
                host.setBusy(false);
            }
        }

        async function pathsFromSelection() {
            // Convierte a curvas lo que haga falta y devuelve los trazados de la selección en orden.
            const ids = orderedSelection().filter((item) => !item.locked).map((item) => item.id);
            const pending = ids.map(findElement).filter((item) => item.type !== 'path');
            let createdIds = new Set();
            if (pending.length) {
                const created = await convertToCurves(pending, { quiet: true, select: false });
                if (!created.length) return null;
                createdIds = new Set(created.map((item) => item.id));
            }
            return elements().filter((item) => createdIds.has(item.id) || (ids.includes(item.id) && item.type === 'path'));
        }

        async function combineSelection() {
            if (orderedSelection().length < 2) return host.setStatus('Seleccioná al menos dos objetos para combinar.', 'error');
            const items = await pathsFromSelection();
            if (!items || items.length < 2) return;
            const base = items[0];
            const merged = items.flatMap((item) => absolutePaths(item));
            const result = pathFromAbsolute(merged, { ...styleFrom(base), fill_rule: 'evenodd' });
            if (!result) return;
            change(() => {
                const ids = new Set(items.map((item) => item.id));
                const list = elements();
                const index = list.indexOf(base);
                const kept = list.filter((item, position) => !ids.has(item.id) || position === index);
                kept.splice(kept.indexOf(base), 1, result);
                side().elements = kept;
            });
            select([result.id]);
            host.setStatus('Objetos combinados en un solo trazado: donde se superponen quedan huecos.');
        }

        function breakApart() {
            const item = selectedElements()[0];
            if (!item || item.type !== 'path' || item.paths.length < 2) return host.setStatus('Elegí un trazado con varias partes para separarlo.', 'error');
            const style = { fill: item.fill, gradient: item.gradient ? clone(item.gradient) : null, stroke_color: item.stroke_color, stroke_width: item.stroke_width, dash: item.dash, line_cap: item.line_cap, line_join: item.line_join, opacity: item.opacity, condition: item.condition ? clone(item.condition) : null };
            const parts = absolutePaths(item).map((sub) => pathFromAbsolute([sub], clone(style))).filter(Boolean);
            change(() => { elements().splice(elements().indexOf(item), 1, ...parts); });
            select(parts.map((part) => part.id));
            host.setStatus(`Trazado separado en ${parts.length} partes.`);
        }

        function flipSelection(axis) {
            const items = selectedElements().filter((item) => !item.locked);
            const paths = items.filter((item) => item.type === 'path');
            if (!paths.length) return host.setStatus('Voltear se aplica a trazados y formas convertidas a curvas.', 'error');
            change(() => paths.forEach((item) => {
                item.paths = mapPaths(item.paths, ([u, v]) => (axis === 'x' ? [1 - u, v] : [u, 1 - v]));
                item.rotation = -(item.rotation || 0);
                if (item.gradient?.kind === 'linear') item.gradient.angle = axis === 'x' ? 180 - (item.gradient.angle || 0) : -(item.gradient.angle || 0);
            }));
        }

        function insertShape(presetId) {
            const preset = SHAPE_PRESETS.find((entry) => entry.id === presetId);
            if (!preset) return;
            const [widthMm, heightMm] = preset.size;
            const w = Math.min(0.9, widthMm / mmW());
            const height = Math.min(0.9, heightMm / mmH());
            const offset = (elements().length % 6) * 0.02;
            const item = makeElement('path', {
                name: preset.label, x: clamp(0.5 - w / 2 + offset, 0, 1 - w), y: clamp(0.5 - height / 2 + offset, 0, 1 - height), w, h: height,
                paths: presetPaths(preset), preset: preset.params ? { kind: preset.id, ...preset.params } : null,
                fill: $('cd-template-color')?.value || '#176b87',
            });
            change(() => elements().push(item));
            select([item.id]);
        }

        // ---- controles del panel ----

        function fillControls(item) {
            const mode = item.gradient ? item.gradient.kind : (item.fill ? 'solid' : 'none');
            const nodes = [control('Relleno', selectInput([['none', 'Sin relleno'], ['solid', 'Color liso'], ['linear', 'Degradado lineal'], ['radial', 'Degradado radial']], mode, (value) => {
                const current = item.gradient;
                if (value === 'none') { item.fill = null; item.gradient = null; }
                else if (value === 'solid') { item.fill = item.fill || current?.start || '#176b87'; item.gradient = null; }
                else item.gradient = { kind: value, start: current?.start || item.fill || '#176b87', end: current?.end || '#8c63ed', angle: current?.angle ?? 0 };
                renderProperties();
            }), { wide: true })];
            if (mode === 'solid') nodes.push(control('Color', colorInput(item.fill, (value) => { item.fill = value; })));
            if (item.gradient) {
                nodes.push(h('div', { class: 'cd-grid2' }, [
                    control('Desde', colorInput(item.gradient.start, (value) => { item.gradient.start = value; })),
                    control('Hasta', colorInput(item.gradient.end, (value) => { item.gradient.end = value; })),
                    item.gradient.kind === 'linear' ? control('Ángulo °', numberInput(item.gradient.angle || 0, { min: -360, max: 360, step: 15 }, (value) => { item.gradient.angle = value; })) : null,
                    h('button', {
                        class: 'btn secondary compact', type: 'button', text: '⇄ Invertir', title: 'Intercambia los colores',
                        onclick: () => change(() => { [item.gradient.start, item.gradient.end] = [item.gradient.end, item.gradient.start]; }),
                    }),
                ]));
                nodes.push(h('small', { class: 'cd-hint', text: 'En el PDF vectorial los degradados se insertan como imagen a la resolución elegida.' }));
            }
            return nodes;
        }

        function strokeControls(item) {
            const isLine = item.type === 'line';
            const grid = [
                isLine
                    ? control('Color', colorInput(item.stroke_color || '#17202b', (value) => { item.stroke_color = value; }))
                    : control('Contorno', colorInput(item.stroke_color, (value) => { item.stroke_color = value; }, { optional: true })),
                control(isLine ? 'Grosor pt' : 'Grosor contorno pt', numberInput(item.stroke_width || (isLine ? 1 : 0), { min: isLine ? 0.1 : 0, max: 40, step: 0.25 }, (value) => { item.stroke_width = value; })),
                control('Tipo de línea', selectInput(DASH_OPTIONS, item.dash || 'solid', (value) => { item.dash = value; })),
            ];
            if (item.type === 'path' || isLine) grid.push(control('Extremos', selectInput(CAP_OPTIONS, item.line_cap || 'butt', (value) => { item.line_cap = value; })));
            if (item.type === 'path') grid.push(control('Esquinas', selectInput(JOIN_OPTIONS, item.line_join || 'miter', (value) => { item.line_join = value; })));
            return h('div', { class: 'cd-grid2' }, grid);
        }

        function presetControls(item) {
            const preset = item.preset && SHAPE_PRESETS.find((entry) => entry.id === item.preset.kind);
            if (!preset?.params) return null;
            const regenerate = () => { item.paths = presetPaths(preset, item.preset); };
            const fields = [];
            if ('points' in preset.params) {
                fields.push(control('Puntas', numberInput(item.preset.points, { min: 3, max: 40, step: 1 }, (value) => { item.preset.points = Math.round(value); regenerate(); })));
                fields.push(control('Profundidad %', numberInput((1 - item.preset.inner) * 100, { min: 5, max: 95, step: 5 }, (value) => { item.preset.inner = 1 - value / 100; regenerate(); })));
            }
            if ('sides' in preset.params) fields.push(control('Lados', numberInput(item.preset.sides, { min: 3, max: 24, step: 1 }, (value) => { item.preset.sides = Math.round(value); regenerate(); })));
            return h('div', { class: 'cd-grid2' }, fields);
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

        const exportState = { printers: [], checkTimer: null, checkToken: 0, lastCheck: null, magProfiles: [] };

        async function loadMagProfiles() {
            if (exportState.magProfiles.length) return;
            try {
                exportState.magProfiles = (await (await host.api('/magstripe/profiles')).json()).profiles || [];
            } catch (_) { exportState.magProfiles = []; }
            const select = $('cx-mag-profile');
            select.replaceChildren(...exportState.magProfiles.map((profile) => h('option', { value: profile.id, text: profile.label })));
        }

        function magCommandInputs() {
            return [1, 2, 3].map((track) => [$(`cx-mag-start-${track}`), $(`cx-mag-end-${track}`)]);
        }

        function applyMagProfile(profileId, saved = null) {
            const profile = exportState.magProfiles.find((item) => item.id === profileId) || exportState.magProfiles[0];
            if (!profile) return;
            $('cx-mag-profile').value = profile.id;
            magCommandInputs().forEach(([start, end], index) => {
                start.value = saved?.start?.[index] ?? profile.start[index];
                end.value = saved?.end?.[index] ?? profile.end[index];
            });
            $('cx-mag-note').textContent = profile.note;
        }

        function updateMagOptions() {
            const wrap = $('cx-mag');
            const visible = isPrinting() && Boolean(design().magstripe?.enabled);
            wrap.hidden = !visible;
            if (!visible || !exportState.magProfiles.length) return;
            const printerName = $('cx-printer').value;
            if (wrap.dataset.printer === printerName) return;
            wrap.dataset.printer = printerName;
            let saved = null;
            try { saved = JSON.parse(readSetting(`fotos.mag.${printerName}`, 'null')); } catch (_) { saved = null; }
            if (saved?.profile) { applyMagProfile(saved.profile, saved); return; }
            const printer = exportState.printers.find((item) => item.name === printerName);
            const text = `${printerName} ${printer?.driver || ''}`;
            const detected = exportState.magProfiles.find((profile) => profile.id !== 'custom' && new RegExp(profile.pattern, 'i').test(text));
            applyMagProfile(detected?.id || 'magicard');
        }

        function magPayload() {
            if ($('cx-mag').hidden || !$('cx-encode').checked) return { encode: false };
            const commands = magCommandInputs();
            const payload = { encode: true, mag_start: commands.map(([start]) => start.value), mag_end: commands.map(([, end]) => end.value) };
            writeSetting(`fotos.mag.${$('cx-printer').value}`, JSON.stringify({ profile: $('cx-mag-profile').value, start: payload.mag_start, end: payload.mag_end }));
            return payload;
        }
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
            updateMagOptions();
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
            updateMagOptions();
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
                    body: JSON.stringify({ design: design(), items: photos.map((photo) => host.exportItem(photo)), sides: $('cx-sides').value, upscale: host.photoOptions().upscale }),
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
            $('cx-vector').checked = readSetting('fotos.cardVector', '1') !== '0';
            loadMagProfiles().then(() => { $('cx-mag').dataset.printer = ''; updateMagOptions(); });
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
            const magnetic = magPayload();
            if (magnetic.encode && readSetting('fotos.magConfirmed', '') !== printer && !window.confirm(`Se va a codificar la banda magnética con los comandos de “${$('cx-mag-profile').selectedOptions[0]?.textContent || 'la impresora'}”.\n\nLa primera vez hacé una sola tarjeta de prueba: si el controlador no tiene activada la codificación por comandos de texto, los datos se imprimen sobre la tarjeta en lugar de grabarse.\n\n¿Continuar?`)) return;
            if (magnetic.encode) writeSetting('fotos.magConfirmed', printer);
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
                        rotate_back: $('cx-rotate-back').checked, ...magnetic, ...host.photoOptions(),
                    }),
                });
                const result = await response.json();
                host.onPrinted(result.printed);
                host.setStatus(`Enviadas ${result.cards} tarjeta${result.cards === 1 ? '' : 's'} a ${result.printer} (${result.pages} página${result.pages === 1 ? '' : 's'})${result.encoded ? ` · banda magnética en ${result.encoded}` : ''}. Revisá la cola de Windows si no empieza a imprimir.`, 'ok', 100);
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
                vector: $('cx-vector').checked,
                filename_pattern: $('cx-pattern').value.trim() || '{Archivo}',
            };
            writeSetting('fotos.cardVector', output.vector ? '1' : '0');
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
            if (!typing && event.key === ' ') {
                event.preventDefault();
                if (!state.spaceHeld) { state.spaceHeld = true; setHandTool(state.handTool); }
                return;
            }
            if (mod && !typing && ['+', '=', 'Add'].includes(event.key)) { event.preventDefault(); setZoom((state.pxPerMm || fitPxPerMm()) * 1.25); return; }
            if (mod && !typing && ['-', 'Subtract'].includes(event.key)) { event.preventDefault(); setZoom((state.pxPerMm || fitPxPerMm()) / 1.25); return; }
            if (mod && !typing && event.key === '0') { event.preventDefault(); zoomFit(); return; }
            if (mod && !typing && event.key === '1') { event.preventDefault(); setZoom(3.7795); return; }
            if (!mod && !typing && event.shiftKey && event.code === 'Digit2') { event.preventDefault(); zoomToSelection(); return; }
            if (!mod && !typing && key === 'h' && !state.cropping) { event.preventDefault(); setHandTool(!state.handTool); return; }
            if (state.pen && !typing) {
                if (event.key === 'Enter') { event.preventDefault(); finishPen(false); return; }
                if (event.key === 'Escape') { event.preventDefault(); if (state.pen.nodes.length >= 2) finishPen(false); else cancelPen(); return; }
                if (event.key === 'Backspace' || event.key === 'Delete') { event.preventDefault(); state.pen.nodes.pop(); renderVectorOverlay(); return; }
                return;
            }
            if (state.nodeEdit && !typing) {
                const pans = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
                if (event.key === 'Escape' || event.key === 'Enter') { event.preventDefault(); exitNodeEdit(); return; }
                if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteNodes(); return; }
                if (pans[event.key] && state.nodeEdit.sel.size) { event.preventDefault(); nudgeNodes(...pans[event.key].map((value) => value * (event.shiftKey ? 1 : 0.1))); return; }
            }
            if (mod && key === 'q' && !typing) { event.preventDefault(); convertToCurves(); return; }
            if (!mod && !typing && key === 'p' && !state.cropping) { event.preventDefault(); setHandTool(false); startPen(); return; }
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
            if (state.pen) cancelPen();
            if (state.nodeEdit) exitNodeEdit();
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
            $('cd-tool-pen').addEventListener('click', () => (state.pen ? cancelPen() : startPen()));
            const shapeInsert = $('cd-insert-shape');
            shapeInsert.replaceChildren(h('option', { value: '', text: 'Formas…' }), ...SHAPE_PRESETS.map((preset) => h('option', { value: preset.id, text: preset.label })));
            shapeInsert.addEventListener('change', () => { if (shapeInsert.value) insertShape(shapeInsert.value); shapeInsert.value = ''; });
            document.querySelectorAll('[data-cd-boolean]').forEach((button) => button.addEventListener('click', () => booleanOperation(button.dataset.cdBoolean)));
            $('cd-combine').addEventListener('click', combineSelection);
            $('cd-break').addEventListener('click', breakApart);
            $('cd-to-curves').addEventListener('click', () => convertToCurves());
            $('cd-flip-x').addEventListener('click', () => flipSelection('x'));
            $('cd-flip-y').addEventListener('click', () => flipSelection('y'));
            $('cd-delete').addEventListener('click', removeSelected);
            document.querySelectorAll('[data-cd-side]').forEach((button) => button.addEventListener('click', () => {
                exitCropMode({ quiet: true });
                if (state.pen) cancelPen();
                state.nodeEdit = null;
                removeModeBanner();
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
            $('cd-zoom-in').addEventListener('click', () => setZoom((state.pxPerMm || fitPxPerMm()) * 1.25));
            $('cd-zoom-out').addEventListener('click', () => setZoom((state.pxPerMm || fitPxPerMm()) / 1.25));
            $('cd-zoom-fit').addEventListener('click', zoomFit);
            $('cd-zoom-real').addEventListener('click', () => setZoom(3.7795));
            $('cd-zoom-selection').addEventListener('click', zoomToSelection);
            $('cd-zoom-value').addEventListener('dblclick', zoomFit);
            $('cd-tool-hand').addEventListener('click', () => setHandTool(!state.handTool));
            document.addEventListener('keyup', (event) => {
                if (event.key === ' ' && state.spaceHeld) { state.spaceHeld = false; setHandTool(state.handTool); }
            });
            window.addEventListener('blur', () => { if (state.spaceHeld) { state.spaceHeld = false; setHandTool(state.handTool); } });
            el.modal.addEventListener('pointerdown', (event) => { if (event.target === el.modal) close(); });
            // Exportación
            $('cx-close').addEventListener('click', () => { el.exportModal.hidden = true; });
            $('cx-cancel').addEventListener('click', () => { el.exportModal.hidden = true; });
            $('cx-run').addEventListener('click', runExport);
            el.exportModal.addEventListener('pointerdown', (event) => { if (event.target === el.exportModal) el.exportModal.hidden = true; });
            el.exportModal.querySelectorAll('input, select').forEach((input) => input.addEventListener('change', updateExportSummary));
            el.exportModal.querySelectorAll('input[type="number"]').forEach((input) => input.addEventListener('input', updateExportSummary));
            $('cx-printer').addEventListener('change', updatePrinterStatus);
            $('cx-mag-profile').addEventListener('change', () => applyMagProfile($('cx-mag-profile').value));
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
                magstripe: { ...defaultMagstripe(), ...(raw?.magstripe || {}) },
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
                version: 2, width_mm: 85.6, height_mm: 53.98, double_sided: false, magstripe: defaultMagstripe(),
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
