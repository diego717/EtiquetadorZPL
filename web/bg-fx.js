// Animacion de fondo de la pagina. Dibuja en un canvas fijo que queda detras de todo el
// contenido (z-index -1) y no recibe clicks. La eleccion se guarda en este navegador y
// se aplica en todas las pestañas abiertas. Se apaga si el sistema pide reducir
// movimiento y se pausa cuando la pestaña no esta visible.
//
// Uso: incluir el script; arranca solo. BgFx.saveSettings({ effect, intensity }) la cambia.
(function () {
    const SETTINGS_KEY = 'etiquetador_ui_bg_fx';
    const DEFAULTS = { effect: 'ninguno', intensity: 1 };
    const GRID = 44; // mismo paso que la grilla de body::after en config.css

    const EFFECT_LIST = [
        { id: 'ninguno', label: 'Sin animacion', group: '' },
        { id: 'linterna-laser', label: 'Linterna + láser', group: '' },
        { id: 'linterna', label: 'Linterna sobre la grilla', group: 'Siguen al mouse' },
        { id: 'constelacion', label: 'Constelación', group: 'Siguen al mouse' },
        { id: 'ondas', label: 'Ondas al hacer click', group: 'Siguen al mouse' },
        { id: 'laser', label: 'Láser de escáner', group: 'De la app' },
        { id: 'etiquetas', label: 'Etiquetas flotando', group: 'De la app' },
        { id: 'impresora', label: 'Impresora fantasma', group: 'De la app' },
        { id: 'aurora', label: 'Aurora', group: 'Ambiente' },
    ];

    function getSettings() {
        let stored = {};
        try { stored = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {}; } catch (e) { stored = {}; }
        const effect = EFFECT_LIST.some(e => e.id === stored.effect) ? stored.effect : DEFAULTS.effect;
        const intensity = Number(stored.intensity);
        return {
            effect,
            intensity: Number.isFinite(intensity) ? Math.min(2, Math.max(0.3, intensity)) : DEFAULTS.intensity,
        };
    }

    function saveSettings(settings) {
        const merged = { ...getSettings(), ...settings };
        try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged)); } catch (e) { /* sin localStorage */ }
        apply(merged);
        return merged;
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    function isSupported() {
        return !reducedMotion.matches && !!document.createElement('canvas').getContext;
    }

    // ---- Utilidades ----

    const clamp01 = v => Math.min(1, Math.max(0, v));
    const easeInOut = t => (t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2);
    const easeOut = t => 1 - (1 - t) ** 3;
    const rand = (a, b) => a + Math.random() * (b - a);
    const rgba = (rgb, a) => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${Math.max(0, a).toFixed(3)})`;

    function parseColor(value, fallback) {
        const s = String(value || '').trim();
        let m = s.match(/^#([0-9a-f]{6})$/i);
        if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
        m = s.match(/^#([0-9a-f]{3})$/i);
        if (m) return [0, 1, 2].map(i => parseInt(m[1][i] + m[1][i], 16));
        m = s.match(/rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)/i);
        if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
        return fallback;
    }

    function readPalette() {
        const light = document.documentElement.getAttribute('data-theme') === 'light';
        const css = getComputedStyle(document.documentElement);
        return {
            light,
            accent: parseColor(css.getPropertyValue('--accent'), light ? [15, 143, 136] : [66, 208, 199]),
            warm: light ? [226, 110, 60] : [255, 117, 74],
            amber: light ? [214, 150, 40] : [255, 189, 89],
            blue: light ? [74, 128, 207] : [96, 150, 230],
            ink: light ? [40, 62, 96] : [190, 210, 235],
            laser: [255, 56, 64],
            // Los trazos se notan menos sobre fondo claro: se compensa un poco.
            boost: light ? 1.35 : 1,
        };
    }

    // Una etiqueta de envio dibujada en (0,0)-(w,h): contorno, renglones y codigo de barras.
    function makeLabelArt(w, h) {
        const bars = [];
        let x = 0;
        while (x < 1) {
            const bw = rand(0.006, 0.03);
            if (Math.random() < 0.55) bars.push([x, Math.min(bw, 1 - x)]);
            x += bw + rand(0.006, 0.02);
        }
        const lines = [rand(0.45, 0.75), rand(0.3, 0.6), rand(0.2, 0.45)];
        return { w, h, bars, lines };
    }

    function drawLabel(ctx, art, stroke, fill, paper) {
        const { w, h } = art;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(0, 0, w, h, Math.min(10, w * 0.06));
        else ctx.rect(0, 0, w, h);
        if (paper) { ctx.fillStyle = paper; ctx.fill(); }
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 1.2;
        ctx.stroke();
        ctx.fillStyle = fill;
        const pad = w * 0.1;
        art.lines.forEach((lw, i) => ctx.fillRect(pad, h * (0.14 + i * 0.1), (w - pad * 2) * lw, Math.max(2, h * 0.035)));
        const by = h * 0.5;
        const bh = h * 0.32;
        for (const [bx, bw] of art.bars) ctx.fillRect(pad + bx * (w - pad * 2), by, Math.max(1, bw * (w - pad * 2)), bh);
    }

    // ---- Estado del canvas ----

    let canvas = null;
    let ctx = null;
    let buf = null;   // canvas auxiliar para dibujar con mascara sin borrar lo demas
    let bctx = null;
    let W = 0;
    let H = 0;
    let dpr = 1;
    let palette = null;
    const gridPatterns = new Map();
    let settings = getSettings();
    let layers = [];
    let rafId = 0;
    let lastTs = 0;
    let clock = 0;
    const mouse = { x: -9999, y: -9999, sx: -9999, sy: -9999, inside: false, presence: 0, moved: 0 };

    function ensureCanvas() {
        if (canvas) return;
        canvas = document.createElement('canvas');
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;z-index:-1;pointer-events:none;';
        ctx = canvas.getContext('2d');
        gridPatterns.clear();
        buf = document.createElement('canvas');
        bctx = buf.getContext('2d');
        document.body.insertBefore(canvas, document.body.firstChild);
        resize();
    }

    function resize() {
        if (!canvas) return;
        dpr = Math.min(1.5, window.devicePixelRatio || 1);
        W = window.innerWidth;
        H = window.innerHeight;
        for (const c of [canvas, buf]) {
            c.width = Math.round(W * dpr);
            c.height = Math.round(H * dpr);
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        layers.forEach(l => l.resize && l.resize());
    }

    // Grilla del color pedido, como patron repetible.
    function getGridPattern(rgb, alpha) {
        const key = `${rgb.join(',')}|${alpha}`;
        if (gridPatterns.has(key)) return gridPatterns.get(key);
        const tile = document.createElement('canvas');
        tile.width = GRID;
        tile.height = GRID;
        const t = tile.getContext('2d');
        t.fillStyle = rgba(rgb, alpha);
        t.fillRect(0, 0, GRID, 1);
        t.fillRect(0, 0, 1, GRID);
        const pattern = ctx.createPattern(tile, 'repeat');
        gridPatterns.set(key, pattern);
        return pattern;
    }

    // Dibuja `paint` en el canvas auxiliar, lo recorta con `mask` y lo pega en el principal.
    function withMask(paint, mask) {
        bctx.save();
        bctx.setTransform(1, 0, 0, 1, 0, 0);
        bctx.clearRect(0, 0, buf.width, buf.height);
        bctx.restore();
        bctx.save();
        bctx.globalCompositeOperation = 'source-over';
        paint(bctx);
        bctx.globalCompositeOperation = 'destination-in';
        mask(bctx);
        bctx.restore();
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(buf, 0, 0);
        ctx.restore();
    }

    // ---- Capas ----
    // Cada capa recibe (dt, t, k): segundos desde el cuadro anterior, reloj y la intensidad.
    // Las capas con `overlay` se dibujan por encima del contenido (sin tomar clicks):
    // los recuadros tienen fondo con blur y detras de ellos no se verian.

    const LAYERS = {
        // La grilla se ilumina en un circulo suave alrededor del mouse.
        linterna() {
            return {
                overlay: true,
                draw(dt, t, k) {
                    if (mouse.presence < 0.01) return;
                    const R = 260;
                    const x = mouse.sx;
                    const y = mouse.sy;
                    const a = Math.min(1, 0.38 * k * palette.boost) * mouse.presence;
                    const glow = ctx.createRadialGradient(x, y, 0, x, y, R * 1.2);
                    glow.addColorStop(0, rgba(palette.accent, 0.07 * a));
                    glow.addColorStop(1, rgba(palette.accent, 0));
                    ctx.fillStyle = glow;
                    ctx.fillRect(x - R * 1.2, y - R * 1.2, R * 2.4, R * 2.4);
                    withMask(b => {
                        b.fillStyle = getGridPattern(palette.accent, 0.9);
                        b.fillRect(x - R, y - R, R * 2, R * 2);
                    }, b => {
                        const g = b.createRadialGradient(x, y, 0, x, y, R);
                        g.addColorStop(0, `rgba(0,0,0,${a})`);
                        g.addColorStop(0.45, `rgba(0,0,0,${a * 0.5})`);
                        g.addColorStop(1, 'rgba(0,0,0,0)');
                        b.fillStyle = g;
                        b.fillRect(0, 0, W, H);
                    });
                },
            };
        },

        // Cada tanto una linea roja barre la pantalla como un lector de codigo de barras.
        laser() {
            const period = 24;
            const sweep = 2.6;
            const firstAt = 2.5;
            return {
                draw(dt, t, k) {
                    if (t < firstAt) return;
                    const phase = (t - firstAt) % period;
                    if (phase > sweep) return;
                    const p = phase / sweep;
                    const y = easeInOut(p) * (H + 120) - 60;
                    const fade = Math.sin(Math.PI * p) ** 0.4;
                    const a = Math.min(1, k * palette.boost) * fade;

                    // Estela que queda arriba de la linea.
                    const trail = ctx.createLinearGradient(0, y - 150, 0, y);
                    trail.addColorStop(0, rgba(palette.laser, 0));
                    trail.addColorStop(1, rgba(palette.laser, 0.07 * a));
                    ctx.fillStyle = trail;
                    ctx.fillRect(0, y - 150, W, 150);

                    // La grilla se enciende al paso de la linea.
                    withMask(b => {
                        b.fillStyle = getGridPattern(palette.laser, 0.8);
                        b.fillRect(0, y - 110, W, 130);
                    }, b => {
                        const g = b.createLinearGradient(0, y - 110, 0, y + 20);
                        g.addColorStop(0, 'rgba(0,0,0,0)');
                        g.addColorStop(0.85, `rgba(0,0,0,${0.45 * a})`);
                        g.addColorStop(1, 'rgba(0,0,0,0)');
                        b.fillStyle = g;
                        b.fillRect(0, 0, W, H);
                    });

                    // La linea, mas intensa al centro y apagada en los bordes.
                    const line = ctx.createLinearGradient(0, 0, W, 0);
                    line.addColorStop(0, rgba(palette.laser, 0));
                    line.addColorStop(0.18, rgba(palette.laser, 0.55 * a));
                    line.addColorStop(0.82, rgba(palette.laser, 0.55 * a));
                    line.addColorStop(1, rgba(palette.laser, 0));
                    ctx.save();
                    ctx.shadowColor = rgba(palette.laser, 0.8 * a);
                    ctx.shadowBlur = 14;
                    ctx.fillStyle = line;
                    ctx.fillRect(0, y - 1, W, 2);
                    ctx.restore();
                },
            };
        },

        // Siluetas de etiquetas que caen lento, giradas, como papel en el aire.
        etiquetas() {
            let items = [];
            const spawn = (anywhere) => {
                const w = rand(90, 170);
                return {
                    art: makeLabelArt(w, w * rand(0.55, 0.75)),
                    x: rand(-40, W + 40),
                    y: anywhere ? rand(-150, H) : rand(-260, -160),
                    rot: rand(-0.6, 0.6),
                    vr: rand(-0.08, 0.08),
                    vy: rand(9, 20),
                    sway: rand(10, 30),
                    swaySpeed: rand(0.2, 0.45),
                    phase: rand(0, Math.PI * 2),
                };
            };
            const fill = () => { items = Array.from({ length: Math.round(4 + Math.min(W, 1600) / 260) }, () => spawn(true)); };
            fill();
            return {
                resize: fill,
                draw(dt, t, k) {
                    const a = Math.min(1, k) * palette.boost;
                    for (let i = 0; i < items.length; i++) {
                        const it = items[i];
                        it.y += it.vy * dt;
                        it.rot += it.vr * dt;
                        if (it.y > H + 200) items[i] = spawn(false);
                        const x = it.x + Math.sin(t * it.swaySpeed + it.phase) * it.sway;
                        ctx.save();
                        ctx.translate(x, it.y);
                        ctx.rotate(it.rot + Math.sin(t * it.swaySpeed * 1.3 + it.phase) * 0.12);
                        ctx.translate(-it.art.w / 2, -it.art.h / 2);
                        drawLabel(ctx, it.art, rgba(palette.ink, 0.11 * a), rgba(palette.ink, 0.07 * a), null);
                        ctx.restore();
                    }
                },
            };
        },

        // De vez en cuando una etiqueta sale "impresa" desde el borde de arriba y se esfuma.
        impresora() {
            const period = 18;
            const firstAt = 3;
            let cycle = -1;
            let job = null;
            return {
                draw(dt, t, k) {
                    if (t < firstAt) return;
                    const n = Math.floor((t - firstAt) / period);
                    const phase = (t - firstAt) % period;
                    if (n !== cycle) {
                        cycle = n;
                        const w = rand(170, 230);
                        job = { art: makeLabelArt(w, w * 0.62), x: rand(W * 0.08, W * 0.92 - w) };
                    }
                    const emerge = 4;
                    const hold = 3;
                    const leave = 1.6;
                    if (phase > emerge + hold + leave) return;
                    const { art } = job;
                    const a = Math.min(1, k) * palette.boost;
                    let shown = art.h;
                    let alpha = 1;
                    let drop = 0;
                    if (phase < emerge) {
                        // Sale a tirones, como una impresora termica.
                        const p = phase / emerge;
                        shown = art.h * easeOut(Math.floor(p * 22) / 22 * 0.3 + p * 0.7);
                    } else if (phase > emerge + hold) {
                        const p = (phase - emerge - hold) / leave;
                        alpha = 1 - p;
                        drop = easeInOut(p) * 26;
                    }
                    const slotFade = phase < emerge + hold ? 1 : alpha;
                    // Ranura de la impresora.
                    ctx.fillStyle = rgba(palette.ink, 0.12 * a * slotFade);
                    ctx.fillRect(job.x - 16, 0, art.w + 32, 4);
                    ctx.save();
                    ctx.beginPath();
                    ctx.rect(job.x - 4, 4, art.w + 8, H);
                    ctx.clip();
                    ctx.translate(job.x, 4 + shown - art.h + drop);
                    drawLabel(ctx, art,
                        rgba(palette.ink, 0.2 * a * alpha),
                        rgba(palette.ink, 0.14 * a * alpha),
                        rgba(palette.light ? [255, 255, 255] : palette.ink, (palette.light ? 0.35 : 0.035) * a * alpha));
                    ctx.restore();
                },
            };
        },

        // Puntitos que se mueven lento y se unen entre si y con el mouse.
        constelacion() {
            let pts = [];
            const fill = () => {
                const count = Math.round(Math.min(110, Math.max(28, (W * H) / 24000)));
                pts = Array.from({ length: count }, () => {
                    const ang = rand(0, Math.PI * 2);
                    const sp = rand(5, 14);
                    return { x: rand(0, W), y: rand(0, H), vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, r: rand(0.8, 1.8) };
                });
            };
            fill();
            const LINK = 140;
            const REACH = 190;
            return {
                overlay: true,
                resize: fill,
                draw(dt, t, k) {
                    const a = Math.min(1.4, k) * palette.boost;
                    const m = mouse.presence > 0.01;
                    for (const p of pts) {
                        // El mouse los atrae apenas.
                        if (m) {
                            const dx = mouse.sx - p.x;
                            const dy = mouse.sy - p.y;
                            const d = Math.hypot(dx, dy);
                            if (d < REACH && d > 1) {
                                p.x += (dx / d) * 10 * dt * mouse.presence;
                                p.y += (dy / d) * 10 * dt * mouse.presence;
                            }
                        }
                        p.x += p.vx * dt;
                        p.y += p.vy * dt;
                        if (p.x < -20) p.x = W + 20; else if (p.x > W + 20) p.x = -20;
                        if (p.y < -20) p.y = H + 20; else if (p.y > H + 20) p.y = -20;
                    }
                    ctx.lineWidth = 1;
                    for (let i = 0; i < pts.length; i++) {
                        const p = pts[i];
                        for (let j = i + 1; j < pts.length; j++) {
                            const q = pts[j];
                            const dx = p.x - q.x;
                            if (dx > LINK || dx < -LINK) continue;
                            const d = Math.hypot(dx, p.y - q.y);
                            if (d > LINK) continue;
                            ctx.strokeStyle = rgba(palette.ink, (1 - d / LINK) * 0.13 * a);
                            ctx.beginPath();
                            ctx.moveTo(p.x, p.y);
                            ctx.lineTo(q.x, q.y);
                            ctx.stroke();
                        }
                        if (m) {
                            const d = Math.hypot(p.x - mouse.sx, p.y - mouse.sy);
                            if (d < REACH) {
                                ctx.strokeStyle = rgba(palette.accent, (1 - d / REACH) * 0.45 * a * mouse.presence);
                                ctx.beginPath();
                                ctx.moveTo(p.x, p.y);
                                ctx.lineTo(mouse.sx, mouse.sy);
                                ctx.stroke();
                            }
                        }
                        ctx.fillStyle = rgba(palette.ink, 0.32 * a);
                        ctx.beginPath();
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fill();
                    }
                },
            };
        },

        // Cada click deja una onda que deforma la grilla como agua; a veces cae una gota sola.
        ondas() {
            const ripples = [];
            const LIFE = 2.8;
            const SPEED = 280;
            let nextDrop = rand(4, 8);
            const onDown = (e) => {
                if (ripples.length >= 5) ripples.shift();
                ripples.push({ x: e.clientX, y: e.clientY, born: clock, strength: 1 });
            };
            window.addEventListener('pointerdown', onDown, { passive: true });

            function drawRipple(rp, k) {
                const age = clock - rp.born;
                const life = clamp01(age / LIFE);
                const fade = (1 - life) ** 1.5;
                const r = age * SPEED;
                const a = Math.min(1, k * palette.boost) * rp.strength * fade;
                const amp = 9 * rp.strength * fade;
                const disp = (px, py) => {
                    const dx = px - rp.x;
                    const dy = py - rp.y;
                    const d = Math.hypot(dx, dy) || 1;
                    const s = (d - r) / 40;
                    const off = amp * Math.exp(-s * s) * Math.sin((d - r) / 13);
                    return [px + (dx / d) * off, py + (dy / d) * off];
                };
                const x0 = Math.floor((rp.x - r - 80) / GRID) * GRID;
                const x1 = rp.x + r + 80;
                const y0 = Math.floor((rp.y - r - 80) / GRID) * GRID;
                const y1 = rp.y + r + 80;
                withMask(b => {
                    b.strokeStyle = rgba(palette.accent, 0.9);
                    b.lineWidth = 1;
                    b.beginPath();
                    for (let gx = x0; gx <= x1; gx += GRID) {
                        for (let yy = y0; yy <= y1; yy += 10) {
                            const [px, py] = disp(gx + 0.5, yy);
                            if (yy === y0) b.moveTo(px, py); else b.lineTo(px, py);
                        }
                    }
                    for (let gy = y0; gy <= y1; gy += GRID) {
                        for (let xx = x0; xx <= x1; xx += 10) {
                            const [px, py] = disp(xx, gy + 0.5);
                            if (xx === x0) b.moveTo(px, py); else b.lineTo(px, py);
                        }
                    }
                    b.stroke();
                }, b => {
                    const inner = Math.max(0, r - 90);
                    const g = b.createRadialGradient(rp.x, rp.y, inner, rp.x, rp.y, r + 70);
                    g.addColorStop(0, 'rgba(0,0,0,0)');
                    g.addColorStop(0.55, `rgba(0,0,0,${0.4 * a})`);
                    g.addColorStop(1, 'rgba(0,0,0,0)');
                    b.fillStyle = g;
                    b.fillRect(0, 0, W, H);
                });
                ctx.lineWidth = 1.2;
                for (let i = 0; i < 3; i++) {
                    const rr = r - i * 26;
                    if (rr <= 0) continue;
                    ctx.strokeStyle = rgba(palette.accent, (0.22 - i * 0.06) * a);
                    ctx.beginPath();
                    ctx.arc(rp.x, rp.y, rr, 0, Math.PI * 2);
                    ctx.stroke();
                }
            }

            return {
                overlay: true,
                destroy() { window.removeEventListener('pointerdown', onDown); },
                draw(dt, t, k) {
                    nextDrop -= dt;
                    if (nextDrop <= 0) {
                        nextDrop = rand(9, 16);
                        ripples.push({ x: rand(W * 0.1, W * 0.9), y: rand(H * 0.1, H * 0.9), born: clock, strength: 0.55 });
                    }
                    for (let i = ripples.length - 1; i >= 0; i--) {
                        if (clock - ripples[i].born > LIFE) ripples.splice(i, 1);
                    }
                    ripples.forEach(rp => drawRipple(rp, k));
                },
            };
        },

        // Bandas de color que ondulan muy lento en la parte de arriba.
        aurora() {
            const small = document.createElement('canvas');
            const sctx = small.getContext('2d');
            const SCALE = 8;
            const bands = [
                { color: 'accent', base: 0.18, amp: 0.07, f: 1.6, s: 0.05, ph: 0, thick: 0.2 },
                { color: 'warm', base: 0.3, amp: 0.09, f: 1.1, s: -0.035, ph: 2, thick: 0.16 },
                { color: 'blue', base: 0.1, amp: 0.06, f: 2.3, s: 0.028, ph: 4, thick: 0.14 },
                { color: 'amber', base: 0.42, amp: 0.05, f: 1.4, s: 0.04, ph: 1, thick: 0.1 },
            ];
            const fit = () => {
                small.width = Math.max(16, Math.ceil(W / SCALE));
                small.height = Math.max(16, Math.ceil(H / SCALE));
            };
            fit();
            return {
                resize: fit,
                draw(dt, t, k) {
                    const sw = small.width;
                    const sh = small.height;
                    const a = Math.min(1.6, k) * (palette.light ? 0.75 : 1);
                    sctx.globalCompositeOperation = 'source-over';
                    sctx.clearRect(0, 0, sw, sh);
                    if ('filter' in sctx) sctx.filter = 'blur(3px)';
                    for (const bd of bands) {
                        const rgb = palette[bd.color];
                        const yAt = (x, off) => {
                            const u = x / sw;
                            return sh * (bd.base + off
                                + bd.amp * Math.sin(u * Math.PI * bd.f + t * bd.s * 6 + bd.ph)
                                + bd.amp * 0.5 * Math.sin(u * Math.PI * bd.f * 2.7 - t * bd.s * 9 + bd.ph * 1.7));
                        };
                        sctx.beginPath();
                        for (let x = 0; x <= sw; x += 2) {
                            const y = yAt(x, 0);
                            if (x === 0) sctx.moveTo(x, y); else sctx.lineTo(x, y);
                        }
                        for (let x = sw; x >= 0; x -= 2) {
                            const thick = bd.thick * (0.6 + 0.4 * Math.sin(x / sw * Math.PI * 3 + t * 0.15 + bd.ph));
                            sctx.lineTo(x, yAt(x, thick));
                        }
                        sctx.closePath();
                        const top = sh * (bd.base - bd.amp * 1.5);
                        const g = sctx.createLinearGradient(0, top, 0, top + sh * (bd.thick + bd.amp * 3));
                        g.addColorStop(0, rgba(rgb, 0));
                        g.addColorStop(0.45, rgba(rgb, 0.2 * a));
                        g.addColorStop(1, rgba(rgb, 0));
                        sctx.fillStyle = g;
                        sctx.fill();
                    }
                    if ('filter' in sctx) sctx.filter = 'none';
                    // Se desvanece hacia abajo para no ensuciar la parte de las tablas.
                    sctx.globalCompositeOperation = 'destination-in';
                    const fade = sctx.createLinearGradient(0, 0, 0, sh);
                    fade.addColorStop(0, 'rgba(0,0,0,1)');
                    fade.addColorStop(0.55, 'rgba(0,0,0,0.6)');
                    fade.addColorStop(1, 'rgba(0,0,0,0)');
                    sctx.fillStyle = fade;
                    sctx.fillRect(0, 0, sw, sh);
                    sctx.globalCompositeOperation = 'source-over';
                    ctx.save();
                    ctx.imageSmoothingEnabled = true;
                    ctx.imageSmoothingQuality = 'high';
                    ctx.drawImage(small, 0, 0, W, H);
                    ctx.restore();
                },
            };
        },
    };

    // ---- Bucle ----

    function frame(ts) {
        rafId = requestAnimationFrame(frame);
        const dt = lastTs ? Math.min(0.05, (ts - lastTs) / 1000) : 0;
        lastTs = ts;
        clock += dt;

        // El punto que sigue al mouse va un poco atrasado; aparece y se apaga suave.
        if (mouse.sx < -9000) { mouse.sx = mouse.x; mouse.sy = mouse.y; }
        const follow = 1 - Math.exp(-dt * 10);
        mouse.sx += (mouse.x - mouse.sx) * follow;
        mouse.sy += (mouse.y - mouse.sy) * follow;
        const idle = clock - mouse.moved;
        const target = mouse.inside ? (idle < 6 ? 1 : Math.max(0.35, 1 - (idle - 6) / 4)) : 0;
        mouse.presence += (target - mouse.presence) * (1 - Math.exp(-dt * (target > mouse.presence ? 6 : 2)));

        ctx.clearRect(0, 0, W, H);
        for (const layer of layers) layer.draw(dt, clock, settings.intensity);
    }

    function startLoop() {
        if (rafId || !layers.length || document.hidden) return;
        lastTs = 0;
        rafId = requestAnimationFrame(frame);
    }

    function stopLoop() {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = 0;
    }

    function apply(next) {
        settings = next || getSettings();
        stopLoop();
        layers.forEach(l => l.destroy && l.destroy());
        layers = [];
        if (settings.effect === 'ninguno' || !isSupported()) {
            if (canvas) {
                canvas.remove();
                canvas = null;
            }
            return;
        }
        ensureCanvas();
        palette = readPalette();
        clock = 0;
        const ids = settings.effect === 'linterna-laser' ? ['linterna', 'laser'] : [settings.effect];
        layers = ids.map(id => LAYERS[id]());
        canvas.style.zIndex = layers.some(l => l.overlay) ? '2147483000' : '-1';
        startLoop();
    }

    window.addEventListener('pointermove', (e) => {
        if (e.pointerType === 'touch') return;
        mouse.x = e.clientX;
        mouse.y = e.clientY;
        if (!mouse.inside && mouse.presence < 0.05) { mouse.sx = mouse.x; mouse.sy = mouse.y; }
        mouse.inside = true;
        mouse.moved = clock;
    }, { passive: true });
    document.addEventListener('mouseout', (e) => { if (!e.relatedTarget) mouse.inside = false; });
    window.addEventListener('blur', () => { mouse.inside = false; });
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', () => (document.hidden ? stopLoop() : startLoop()));
    if (reducedMotion.addEventListener) reducedMotion.addEventListener('change', () => apply(settings));
    // Otra pestaña cambio la eleccion.
    window.addEventListener('storage', (e) => { if (e.key === SETTINGS_KEY) apply(getSettings()); });
    // Cambio de tema claro/oscuro: se releen los colores.
    new MutationObserver(() => { if (canvas) palette = readPalette(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    if (document.body) apply(settings);
    else document.addEventListener('DOMContentLoaded', () => apply(settings));

    window.BgFx = { EFFECT_LIST, getSettings, saveSettings, isSupported };
})();
