/* Controls shared by console pages: a button's busy state, the confirm bubble, the character-limit ring and countdown text. Loaded after console-core.js, adds to window.Console. */
(() => {
    const SPINNER_DELAY = 150, SPINNER_MIN = 300;
    const working = new WeakSet();
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

    // Runs task while the button shows it is working. The button stays focusable, and keeps its width because the label
    // stays in place. A task that ends within SPINNER_DELAY never shows the spinner; a spinner that did appear stays long
    // enough to read. A click while busy is ignored and resolves to undefined.
    async function busy(button, task) {
        if (working.has(button)) return undefined;
        working.add(button);
        const before = button.getAttribute('aria-disabled');
        button.setAttribute('aria-disabled', 'true');
        let shownAt = 0;
        const timer = setTimeout(() => { shownAt = Date.now(); button.setAttribute('aria-busy', 'true'); }, SPINNER_DELAY);
        try {
            return await task();
        } finally {
            clearTimeout(timer);
            if (shownAt) await wait(Math.max(0, SPINNER_MIN - (Date.now() - shownAt)));
            button.removeAttribute('aria-busy');
            if (before === null) button.removeAttribute('aria-disabled'); else button.setAttribute('aria-disabled', before);
            working.delete(button);
        }
    }

    let openBubble = null;
    const GAP = 8, EDGE = 16;

    // Asks beside the button that triggered it. Resolves true for the action; anything else (cancel, Escape, a click
    // elsewhere, scrolling the anchor away, opening another bubble) resolves false. Focus goes back to the anchor.
    function confirm(anchor, {message, action, danger = false}) {
        openBubble?.(false);
        return new Promise(resolve => {
            const box = document.createElement('div'), text = document.createElement('p'), row = document.createElement('div');
            const cancel = document.createElement('button'), ok = document.createElement('button');
            box.className = 'confirm-pop'; box.setAttribute('role', 'alertdialog'); box.setAttribute('aria-label', message);
            // Clicking the text would otherwise send focus to the page, out of reach of the key handling below.
            box.tabIndex = -1;
            text.className = 'confirm-text'; text.textContent = message;
            row.className = 'confirm-actions';
            cancel.type = 'button'; cancel.className = 'btn btn--text btn--sm'; cancel.textContent = Console.tr('common.cancel');
            ok.type = 'button'; ok.className = `btn btn--sm ${danger ? 'btn--danger' : 'btn--primary'}`; ok.textContent = action;
            row.append(cancel, ok); box.append(text, row); document.body.append(box);

            const outside = event => { if (!box.contains(event.target)) close(false); };
            const away = () => close(false);
            function close(value) {
                document.removeEventListener('mousedown', outside, true);
                window.removeEventListener('scroll', away, true);
                window.removeEventListener('resize', away);
                box.remove();
                openBubble = null;
                anchor.focus?.();
                resolve(value);
            }
            openBubble = close;
            cancel.onclick = () => close(false);
            ok.onclick = () => close(true);
            box.addEventListener('keydown', event => {
                if (event.key === 'Escape') { event.preventDefault(); close(false); }
                if (event.key === 'Tab') { event.preventDefault(); (document.activeElement === cancel ? ok : cancel).focus(); }
            });

            // offsetWidth/Height ignore the entry scale, which getBoundingClientRect would measure mid-animation.
            const at = anchor.getBoundingClientRect(), width = box.offsetWidth, height = box.offsetHeight;
            const below = at.bottom + GAP + height <= window.innerHeight - GAP, above = at.top - GAP - height >= GAP;
            box.style.left = `${Math.max(EDGE, Math.min(at.right, window.innerWidth - EDGE) - width)}px`;
            if (below || !above) box.style.top = `${at.bottom + GAP}px`;
            else { box.style.top = `${at.top - GAP - height}px`; box.setAttribute('data-side', 'top'); }

            cancel.focus({preventScroll: true});
            // Registered last: the click that opened the bubble must not close it, and focusing must not count as a scroll.
            document.addEventListener('mousedown', outside, true);
            window.addEventListener('scroll', away, true);
            window.addEventListener('resize', away);
        });
    }

    const LIMIT_SHOWS_AT = .7;
    const limitState = (length, max) => ({show: length >= max * LIMIT_SHOWS_AT, remaining: Math.max(0, max - length), full: length >= max, ratio: Math.min(1, length / max)});

    // value.length and maxlength both count UTF-16 units, so an emoji uses up the same two slots in each.
    function attachLimit(input) {
        const max = input.maxLength;
        if (!(max > 0)) return;
        const field = document.createElement('span'), meter = document.createElement('span'), ring = document.createElement('span');
        const count = document.createElement('span'), status = document.createElement('span');
        field.className = input.tagName === 'TEXTAREA' ? 'limit-field limit-field--area' : 'limit-field';
        meter.className = 'limit-meter'; meter.setAttribute('aria-hidden', 'true');
        ring.className = 'limit-ring';
        ring.innerHTML = '<svg width="20" height="20" viewBox="0 0 20 20"><circle class="limit-track" cx="10" cy="10" r="8"/><circle class="limit-fill" cx="10" cy="10" r="8"/></svg>';
        status.className = 'sr-only'; status.setAttribute('role', 'status');
        meter.append(ring, count);
        input.before(field);
        field.append(input, meter, status);
        let announced = false;
        const update = () => {
            const state = limitState(input.value.length, max);
            field.classList.toggle('is-shown', state.show);
            field.classList.toggle('is-full', state.full);
            field.style.setProperty('--limit', String(state.ratio));
            count.textContent = String(state.remaining);
            if (state.full && !announced) { announced = true; status.textContent = Console.tr('common.limit_reached', {n: max}); }
            if (!state.full && announced) { announced = false; status.textContent = ''; }
        };
        input.addEventListener('input', update);
        // Values the page fills in on load fire no input event; the ring only matters once the field is in use.
        input.addEventListener('focus', update);
    }
    const initLimits = (root = document) => root.querySelectorAll('[data-limit]').forEach(attachLimit);
    document.addEventListener('DOMContentLoaded', () => initLimits());

    // What to show with this many seconds left, and how soon (ms) the text next changes; 0 means it no longer does.
    function countdown(seconds) {
        const left = Math.floor(seconds);
        if (left <= 0) return {text: Console.tr('giveaway.drawing'), every: 0};
        const days = Math.floor(left / 86400), hours = Math.floor(left / 3600), minutes = Math.floor(left / 60);
        if (days) return {text: Console.tr('giveaway.left_days', {d: days, h: hours % 24}), every: 60000};
        if (hours) return {text: Console.tr('giveaway.left_hours', {h: hours, m: minutes % 60}), every: 60000};
        return {text: Console.tr('giveaway.left_minutes', {m: minutes, s: String(left % 60).padStart(2, '0')}), every: 1000};
    }

    const isBusy = button => working.has(button);

    Object.assign(window.Console, {busy, isBusy, confirm, limitState, initLimits, countdown});
})();
