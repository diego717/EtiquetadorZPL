// Animacion al cambiar de tema (claro/oscuro). Usa la View Transitions API: el navegador
// saca una foto de la pantalla con el tema viejo, la pone encima del tema nuevo y aca
// se anima esa foto (recortes, giros, filtros). Si el navegador no la soporta, o el
// sistema pide reducir movimiento, el tema cambia al instante.
//
// Uso: ThemeFx.run(() => { ...aplicar el tema... }, botonQueSeToco);
(function () {
    const SETTINGS_KEY = 'etiquetador_ui_theme_fx';
    const DEFAULTS = { effect: 'ola', duration: 1100 };
    const OLD = '::view-transition-old(root)';

    const EFFECT_LIST = [
        { id: 'ninguno', label: 'Sin efecto', group: '' },
        { id: 'aleatorio', label: 'Uno distinto cada vez', group: '' },
        { id: 'ola', label: 'Ola', group: 'Pintura' },
        { id: 'chorreado', label: 'Ola con chorreado', group: 'Pintura' },
        { id: 'desague', label: 'Desagüe', group: 'Pintura' },
        { id: 'tv', label: 'TV vieja', group: 'Raros' },
        { id: 'agujero', label: 'Agujero negro', group: 'Raros' },
        { id: 'glitch', label: 'Glitch', group: 'Raros' },
        { id: 'persiana', label: 'Persiana', group: 'Raros' },
        { id: 'bisagra', label: 'Se cae la página', group: 'Raros' },
    ];

    function getSettings() {
        let stored = {};
        try { stored = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {}; } catch (e) { stored = {}; }
        const effect = EFFECT_LIST.some(e => e.id === stored.effect) ? stored.effect : DEFAULTS.effect;
        const duration = Number(stored.duration);
        return {
            effect,
            duration: Number.isFinite(duration) ? Math.min(3000, Math.max(300, duration)) : DEFAULTS.duration,
        };
    }

    function saveSettings(settings) {
        const merged = { ...getSettings(), ...settings };
        try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged)); } catch (e) { /* sin localStorage */ }
        return merged;
    }

    function isSupported() {
        return typeof document.startViewTransition === 'function'
            && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    // La foto del tema viejo queda arriba y se anima; el tema nuevo espera debajo.
    let styleInjected = false;
    function injectStyle() {
        if (styleInjected) return;
        styleInjected = true;
        const style = document.createElement('style');
        style.textContent = `
            ::view-transition-old(root), ::view-transition-new(root) { animation: none; mix-blend-mode: normal; }
            ::view-transition-old(root) { z-index: 2; }
            ::view-transition-new(root) { z-index: 1; }`;
        document.head.appendChild(style);
    }

    // ---- Pintura: borde de liquido que baja ----
    // Cada variante devuelve, para un instante t (0..1), la altura y(x) del borde:
    // por debajo sigue la pintura (tema viejo), por encima ya se ve el tema nuevo.

    const easeIn = t => t * t;

    function makePaintShape(variant, W, H) {
        const amp = Math.min(26, H * 0.03);
        const k = (2 * Math.PI) / Math.max(260, W / 2.6);
        const travel = H + amp * 4;
        const level = t => -amp * 2 + easeIn(t) * travel;
        const wave = (x, t) => amp * (0.65 * Math.sin(k * x + t * 4 * Math.PI)
                                   + 0.35 * Math.sin(2.3 * k * x - t * 5.5 * Math.PI));

        if (variant === 'chorreado') {
            // Restos de pintura pegados al "vidrio" que bajan mas lento que el nivel.
            const drips = [];
            const count = Math.max(4, Math.round(W / 120));
            for (let i = 0; i < count; i++) {
                drips.push({
                    x: (i + 0.2 + Math.random() * 0.6) * (W / count),
                    w: 5 + Math.random() * 7,
                    maxLen: H * (0.06 + Math.random() * 0.28),
                    delay: Math.random() * 0.25,
                });
            }
            return (x, t) => {
                const surface = level(t) + wave(x, t);
                let y = surface;
                for (const d of drips) {
                    const dx = Math.abs(x - d.x);
                    const local = Math.max(0, (t - d.delay) / (1 - d.delay));
                    const length = Math.min(surface + amp * 2, d.maxLen * Math.pow(Math.sin(Math.PI * local), 0.8));
                    if (length <= 1) continue;
                    const tip = surface - length;
                    const r = d.w * 1.35;
                    // Hilo de pintura que termina en una gota redonda.
                    if (dx < d.w) y = Math.min(y, tip + r);
                    if (dx < r) y = Math.min(y, tip + r - Math.sqrt(r * r - dx * dx));
                    // Ensanche suave donde la gota se une con la superficie.
                    const fillet = Math.min(length, 18) * Math.exp(-((dx / (d.w * 2.2)) ** 2));
                    y = Math.min(y, surface - fillet);
                }
                return y;
            };
        }

        if (variant === 'desague') {
            // La pintura se va por un agujero en el centro: se forma un embudo que se hunde.
            const cx = W / 2;
            return (x, t) => {
                const funnelW = W * (0.16 - 0.08 * t);
                const depth = easeIn(Math.min(1, t * 1.4)) * H * 0.45;
                const calm = 1 - 0.6 * t;
                return level(t) + wave(x, t) * calm + depth * Math.exp(-(((x - cx) / funnelW) ** 2));
            };
        }

        return (x, t) => level(t) + wave(x, t);
    }

    function paintKeyframes(variant) {
        const W = window.innerWidth;
        const H = window.innerHeight;
        const shape = makePaintShape(variant, W, H);
        const step = Math.max(3, W / 400);
        const xs = [];
        for (let x = 0; x < W; x += step) xs.push(x);
        xs.push(W);

        // Margen extra abajo y a la derecha por si la foto es algo mas grande que la ventana.
        const far = Math.max(W, H) * 2;
        const frames = [];
        const total = 60;
        for (let f = 0; f <= total; f++) {
            const t = f / total;
            const pts = xs.map(x => {
                const y = Math.max(-4, Math.min(far, shape(x, t)));
                return `${x.toFixed(1)}px ${y.toFixed(1)}px`;
            });
            const lastY = pts[pts.length - 1].split(' ')[1];
            pts.push(`${far}px ${lastY}`, `${far}px ${far}px`, `0px ${far}px`);
            frames.push({ clipPath: `polygon(${pts.join(',')})` });
        }
        return frames;
    }

    // ---- Efectos raros ----

    // Recorte formado por franjas horizontales contiguas. Cada franja tiene su borde
    // izquierdo (L) y derecho (R); con L === R la franja queda invisible.
    function bandsPolygon(bands) {
        const right = [];
        const left = [];
        for (const b of bands) {
            right.push(`${b.R.toFixed(1)}px ${b.y0.toFixed(1)}px`, `${b.R.toFixed(1)}px ${b.y1.toFixed(1)}px`);
            left.unshift(`${b.L.toFixed(1)}px ${b.y1.toFixed(1)}px`, `${b.L.toFixed(1)}px ${b.y0.toFixed(1)}px`);
        }
        return `polygon(${right.concat(left).join(',')})`;
    }

    const EFFECTS = {
        // Se apaga como un televisor de tubo: se aplasta en una linea, luego un punto.
        tv() {
            const o = { transformOrigin: '50% 50%' };
            return { easing: 'linear', keyframes: [
                { ...o, offset: 0, easing: 'cubic-bezier(.6,0,.9,.6)', transform: 'scale(1, 1)', filter: 'brightness(1) contrast(1)', opacity: 1 },
                { ...o, offset: 0.35, transform: 'scale(1.04, 0.006)', filter: 'brightness(4) contrast(1.4)', opacity: 1 },
                { ...o, offset: 0.5, easing: 'cubic-bezier(.6,0,.9,.6)', transform: 'scale(1.04, 0.006)', filter: 'brightness(5) contrast(1.4)', opacity: 1 },
                { ...o, offset: 0.78, transform: 'scale(0.004, 0.006)', filter: 'brightness(6) contrast(1.4)', opacity: 1 },
                { ...o, offset: 1, transform: 'scale(0.004, 0.006)', filter: 'brightness(6) contrast(1.4)', opacity: 0 },
            ] };
        },

        // La pantalla gira en espiral y la chupa el boton que se toco.
        agujero(origin) {
            const o = { transformOrigin: `${origin.x}px ${origin.y}px` };
            return { easing: 'cubic-bezier(.55,0,.85,.4)', keyframes: [
                { ...o, transform: 'rotate(0deg) scale(1)', filter: 'blur(0px) brightness(1)', borderRadius: '0%' },
                { ...o, offset: 0.5, transform: 'rotate(140deg) scale(.55)', filter: 'blur(0.5px) brightness(1.1)', borderRadius: '30%' },
                { ...o, transform: 'rotate(900deg) scale(0)', filter: 'blur(6px) brightness(3)', borderRadius: '50%' },
            ] };
        },

        // Franjas que saltan de costado, cambian de color y van desapareciendo.
        glitch() {
            const W = window.innerWidth;
            const H = window.innerHeight;
            const far = Math.max(W, H) * 2;
            const count = 18;
            const frames = [];
            const steps = 26;
            for (let f = 0; f <= steps; f++) {
                const p = f / steps;
                const cuts = Array.from({ length: count - 1 }, () => Math.random() * H).sort((a, b) => a - b);
                const edges = [-4, ...cuts, far];
                const bands = [];
                for (let i = 0; i < count; i++) {
                    const visible = f < steps && Math.random() > Math.pow(p, 1.4);
                    const big = Math.random() < 0.3;
                    const dx = f === 0 ? 0 : (Math.random() - 0.5) * W * (big ? 0.18 : 0.02) * (0.3 + p);
                    bands.push(visible
                        ? { y0: edges[i], y1: edges[i + 1], L: dx, R: far + dx }
                        : { y0: edges[i], y1: edges[i + 1], L: far, R: far });
                }
                const loud = f > 0 && Math.random() < 0.45;
                frames.push({
                    offset: p,
                    easing: 'steps(1, end)',
                    clipPath: bandsPolygon(bands),
                    transform: f === 0 ? 'translate(0px, 0px)' : `translate(${((Math.random() - 0.5) * 24).toFixed(1)}px, ${((Math.random() - 0.5) * 6).toFixed(1)}px)`,
                    filter: loud
                        ? `hue-rotate(${Math.round(Math.random() * 360)}deg) saturate(3) contrast(1.6) invert(${Math.random() < 0.25 ? 1 : 0})`
                        : 'hue-rotate(0deg) saturate(1) contrast(1) invert(0)',
                });
            }
            return { easing: 'linear', keyframes: frames };
        },

        // Tablillas que se cierran una tras otra de arriba hacia abajo.
        persiana() {
            const W = window.innerWidth;
            const H = window.innerHeight;
            const far = Math.max(W, H) * 2;
            const slats = 12;
            const h = H / slats;
            const stagger = 0.05;
            const frames = [];
            const steps = 40;
            for (let f = 0; f <= steps; f++) {
                const t = f / steps;
                const bands = [];
                for (let i = 0; i < slats; i++) {
                    const local = Math.min(1, Math.max(0, (t - i * stagger) / (1 - (slats - 1) * stagger)));
                    const half = (h / 2) * (1 - easeIn(local));
                    const mid = i * h + h / 2;
                    const top = i === 0 ? -4 : i * h;
                    const bottom = i === slats - 1 ? far : (i + 1) * h;
                    // Hueco arriba, tablilla visible al medio, hueco abajo.
                    bands.push({ y0: top, y1: mid - half, L: far, R: far });
                    bands.push({ y0: mid - half, y1: mid + half, L: half > 0 ? 0 : far, R: far });
                    bands.push({ y0: mid + half, y1: bottom, L: far, R: far });
                }
                frames.push({ clipPath: bandsPolygon(bands) });
            }
            return { easing: 'linear', keyframes: frames };
        },

        // Se suelta de un clavo, se balancea colgada de la esquina y se cae.
        bisagra() {
            const H = window.innerHeight;
            const o = { transformOrigin: '0px 0px' };
            const k = (offset, y, deg, easing, opacity = 1) =>
                ({ ...o, offset, easing, opacity, transform: `translateY(${y}px) rotate(${deg}deg)` });
            return { easing: 'linear', keyframes: [
                k(0, 0, 0, 'ease-in-out'),
                k(0.2, 0, 80, 'ease-in-out'),
                k(0.4, 0, 60, 'ease-in-out'),
                k(0.55, 0, 76, 'ease-in-out'),
                k(0.68, 0, 66, 'ease-in'),
                k(1, H * 1.4, 70, 'linear', 0.9),
            ] };
        },
    };

    function resolveEffect(effect) {
        if (effect !== 'aleatorio') return effect;
        const pool = EFFECT_LIST.filter(e => e.group).map(e => e.id);
        return pool[Math.floor(Math.random() * pool.length)];
    }

    function buildAnimation(effect, originEl) {
        if (EFFECTS[effect]) {
            let origin = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
            if (originEl && originEl.getBoundingClientRect) {
                const r = originEl.getBoundingClientRect();
                origin = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
            }
            return EFFECTS[effect](origin);
        }
        return { easing: 'linear', keyframes: paintKeyframes(effect) };
    }

    // Aplica el tema con la animacion elegida. `apply` debe cambiar el tema de forma
    // sincronica; `options` permite forzar efecto/duracion (para el boton "Probar").
    function run(apply, originEl, options) {
        const settings = { ...getSettings(), ...(options || {}) };
        const effect = resolveEffect(settings.effect);
        if (effect === 'ninguno' || !isSupported()) {
            apply();
            return;
        }
        injectStyle();
        const { keyframes, easing } = buildAnimation(effect, originEl);
        const transition = document.startViewTransition(apply);
        transition.ready.then(() => {
            const anim = document.documentElement.animate(keyframes, {
                duration: settings.duration,
                easing,
                fill: 'forwards',
                pseudoElement: OLD,
            });
            // Sin esto la animacion terminada queda colgada del documento y se suma
            // a la del proximo cambio de tema, que arranca trabado.
            transition.finished.finally(() => anim.cancel());
        }).catch(() => { /* transicion cancelada: el tema ya quedo aplicado */ });
    }

    window.ThemeFx = { EFFECT_LIST, getSettings, saveSettings, isSupported, run };
})();
