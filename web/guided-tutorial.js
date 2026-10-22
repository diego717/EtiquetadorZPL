(function () {
    'use strict';

    let layer = null;
    let menu = null;
    let activeTour = null;
    let activeIndex = 0;
    let activeTarget = null;
    let returnFocus = null;
    let updateFrame = null;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function ensureLayer() {
        if (layer) return layer;

        layer = element('div', 'guided-tour-layer');
        layer.hidden = true;
        layer.innerHTML = `
            <div class="guided-tour-shade guided-tour-shade-top"></div>
            <div class="guided-tour-shade guided-tour-shade-right"></div>
            <div class="guided-tour-shade guided-tour-shade-bottom"></div>
            <div class="guided-tour-shade guided-tour-shade-left"></div>
            <div class="guided-tour-spotlight" aria-hidden="true"></div>
            <section class="guided-tour-popover" role="dialog" aria-modal="true" aria-labelledby="guided-tour-title" aria-describedby="guided-tour-text" tabindex="-1">
                <div class="guided-tour-topline">
                    <span class="guided-tour-counter"></span>
                    <button type="button" class="guided-tour-close" aria-label="Cerrar tutorial">&times;</button>
                </div>
                <h2 id="guided-tour-title"></h2>
                <p id="guided-tour-text"></p>
                <div class="guided-tour-actions">
                    <button type="button" class="btn secondary guided-tour-back">Anterior</button>
                    <button type="button" class="btn guided-tour-next">Siguiente</button>
                </div>
            </section>`;
        document.body.appendChild(layer);

        layer.querySelector('.guided-tour-close').addEventListener('click', closeTour);
        layer.querySelector('.guided-tour-back').addEventListener('click', previousStep);
        layer.querySelector('.guided-tour-next').addEventListener('click', nextStep);
        layer.querySelectorAll('.guided-tour-shade').forEach((shade) => {
            shade.addEventListener('click', () => {});
        });
        return layer;
    }

    function ensureMenu() {
        if (menu) return menu;
        menu = element('div', 'guided-tour-menu-backdrop');
        menu.hidden = true;
        menu.innerHTML = `
            <section class="guided-tour-menu" role="dialog" aria-modal="true" aria-labelledby="guided-tour-menu-title">
                <div class="guided-tour-menu-head">
                    <div>
                        <span class="guided-tour-eyebrow">Ayuda paso a paso</span>
                        <h2 id="guided-tour-menu-title"></h2>
                    </div>
                    <button type="button" class="guided-tour-close" aria-label="Cerrar ayuda">&times;</button>
                </div>
                <p class="guided-tour-menu-intro"></p>
                <div class="guided-tour-topic-list"></div>
                <p class="guided-tour-keyboard-hint">Durante el recorrido podes usar las flechas del teclado. Esc lo cierra.</p>
            </section>`;
        document.body.appendChild(menu);
        menu.querySelector('.guided-tour-close').addEventListener('click', closeMenu);
        menu.addEventListener('mousedown', (event) => {
            if (event.target === menu) closeMenu();
        });
        return menu;
    }

    function openMenu(options) {
        closeTour(false);
        const dialog = ensureMenu();
        returnFocus = document.activeElement;
        dialog.querySelector('#guided-tour-menu-title').textContent = options.title;
        dialog.querySelector('.guided-tour-menu-intro').textContent = options.intro || '';
        const list = dialog.querySelector('.guided-tour-topic-list');
        list.innerHTML = '';
        options.topics.forEach((topic, index) => {
            const button = element('button', 'guided-tour-topic');
            button.type = 'button';
            button.innerHTML = `
                <span class="guided-tour-topic-number">${String(index + 1).padStart(2, '0')}</span>
                <span class="guided-tour-topic-copy"><strong></strong><small></small></span>
                <span class="guided-tour-topic-arrow" aria-hidden="true">&rarr;</span>`;
            button.querySelector('strong').textContent = topic.title;
            button.querySelector('small').textContent = topic.description;
            button.addEventListener('click', () => options.onSelect(topic.id));
            list.appendChild(button);
        });
        dialog.hidden = false;
        document.body.classList.add('guided-tour-modal-open');
        requestAnimationFrame(() => list.querySelector('button')?.focus());
    }

    function closeMenu(restoreFocus = true) {
        if (!menu || menu.hidden) return;
        menu.hidden = true;
        document.body.classList.remove('guided-tour-modal-open');
        if (restoreFocus) returnFocus?.focus?.();
    }

    function start(tour) {
        if (!tour || !Array.isArray(tour.steps) || !tour.steps.length) return;
        closeMenu(false);
        activeTour = tour;
        activeIndex = 0;
        activeTarget = null;
        ensureLayer().hidden = false;
        document.body.classList.add('guided-tour-active');
        showStep();
    }

    function resolveTarget(step) {
        if (!step.target) return null;
        if (typeof step.target === 'function') return step.target();
        return document.querySelector(step.target);
    }

    function showStep() {
        if (!activeTour) return;
        const step = activeTour.steps[activeIndex];
        if (typeof step.beforeShow === 'function') step.beforeShow();
        activeTarget = resolveTarget(step);

        const popover = layer.querySelector('.guided-tour-popover');
        layer.querySelector('.guided-tour-counter').textContent = `${activeTour.title} · ${activeIndex + 1} de ${activeTour.steps.length}`;
        layer.querySelector('#guided-tour-title').textContent = step.title;
        layer.querySelector('#guided-tour-text').textContent = step.text;
        layer.querySelector('.guided-tour-back').disabled = activeIndex === 0;
        layer.querySelector('.guided-tour-next').textContent = activeIndex === activeTour.steps.length - 1 ? 'Terminar' : 'Siguiente';
        popover.dataset.placement = step.placement || 'auto';

        if (activeTarget) {
            activeTarget.scrollIntoView({
                behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
                block: 'center',
                inline: 'nearest'
            });
        }
        requestAnimationFrame(() => requestAnimationFrame(() => {
            positionTour();
            popover.focus({ preventScroll: true });
        }));
    }

    function targetRect() {
        if (!activeTarget) {
            const width = Math.min(520, window.innerWidth - 32);
            return {
                left: (window.innerWidth - width) / 2,
                right: (window.innerWidth + width) / 2,
                top: Math.max(90, window.innerHeight * 0.25),
                bottom: Math.max(91, window.innerHeight * 0.25 + 1),
                width,
                height: 1
            };
        }
        const raw = activeTarget.getBoundingClientRect();
        const pad = 9;
        const left = Math.max(8, raw.left - pad);
        const right = Math.min(window.innerWidth - 8, raw.right + pad);
        const top = Math.max(8, raw.top - pad);
        const bottom = Math.min(window.innerHeight - 8, raw.bottom + pad);
        return { left, right, top, bottom, width: Math.max(1, right - left), height: Math.max(1, bottom - top) };
    }

    function setRect(node, left, top, width, height) {
        node.style.left = `${Math.max(0, left)}px`;
        node.style.top = `${Math.max(0, top)}px`;
        node.style.width = `${Math.max(0, width)}px`;
        node.style.height = `${Math.max(0, height)}px`;
    }

    function positionTour() {
        if (!activeTour || !layer || layer.hidden) return;
        const rect = targetRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        setRect(layer.querySelector('.guided-tour-shade-top'), 0, 0, viewportWidth, rect.top);
        setRect(layer.querySelector('.guided-tour-shade-right'), rect.right, rect.top, viewportWidth - rect.right, rect.height);
        setRect(layer.querySelector('.guided-tour-shade-bottom'), 0, rect.bottom, viewportWidth, viewportHeight - rect.bottom);
        setRect(layer.querySelector('.guided-tour-shade-left'), 0, rect.top, rect.left, rect.height);
        setRect(layer.querySelector('.guided-tour-spotlight'), rect.left, rect.top, rect.width, rect.height);

        const popover = layer.querySelector('.guided-tour-popover');
        const gap = 16;
        const margin = 12;
        const popWidth = popover.offsetWidth;
        const popHeight = popover.offsetHeight;
        const desired = popover.dataset.placement;
        let left = Math.min(Math.max(margin, rect.left), viewportWidth - popWidth - margin);
        let top;
        let placement;

        const fitsBelow = rect.bottom + gap + popHeight <= viewportHeight - margin;
        const fitsAbove = rect.top - gap - popHeight >= margin;
        if ((desired === 'bottom' && fitsBelow) || (desired === 'auto' && fitsBelow)) {
            top = rect.bottom + gap;
            placement = 'bottom';
        } else if ((desired === 'top' && fitsAbove) || fitsAbove) {
            top = rect.top - popHeight - gap;
            placement = 'top';
        } else {
            top = Math.min(Math.max(margin, viewportHeight - popHeight - margin), Math.max(margin, rect.top + 12));
            left = Math.min(viewportWidth - popWidth - margin, Math.max(margin, (viewportWidth - popWidth) / 2));
            placement = 'floating';
        }
        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
        popover.dataset.actualPlacement = placement;
    }

    function schedulePosition() {
        if (updateFrame) cancelAnimationFrame(updateFrame);
        updateFrame = requestAnimationFrame(positionTour);
    }

    function previousStep() {
        if (!activeTour || activeIndex === 0) return;
        activeIndex -= 1;
        showStep();
    }

    function nextStep() {
        if (!activeTour) return;
        if (activeIndex >= activeTour.steps.length - 1) {
            closeTour();
            return;
        }
        activeIndex += 1;
        showStep();
    }

    function closeTour(restoreFocus = true) {
        if (!activeTour) return;
        const finishedTour = activeTour;
        activeTour = null;
        activeTarget = null;
        if (layer) layer.hidden = true;
        document.body.classList.remove('guided-tour-active');
        if (typeof finishedTour.onClose === 'function') finishedTour.onClose();
        if (restoreFocus) returnFocus?.focus?.();
    }

    document.addEventListener('keydown', (event) => {
        if (menu && !menu.hidden && event.key === 'Escape') {
            event.preventDefault();
            closeMenu();
            return;
        }
        if (!activeTour) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeTour();
        } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            nextStep();
        } else if (event.key === 'ArrowLeft') {
            event.preventDefault();
            previousStep();
        }
    });
    window.addEventListener('resize', schedulePosition);
    window.addEventListener('scroll', schedulePosition, true);

    window.GuidedTutorial = { openMenu, start, close: closeTour };
})();
