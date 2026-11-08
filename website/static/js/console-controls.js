/* Controls shared by console pages: a button's busy state and the confirm bubble. Loaded after console-core.js, adds to window.Console. */
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

            const at = anchor.getBoundingClientRect(), size = box.getBoundingClientRect();
            const below = at.bottom + GAP + size.height <= window.innerHeight - GAP, above = at.top - GAP - size.height >= GAP;
            box.style.left = `${Math.max(EDGE, Math.min(at.right, window.innerWidth - EDGE) - size.width)}px`;
            if (below || !above) box.style.top = `${at.bottom + GAP}px`;
            else { box.style.top = `${at.top - GAP - size.height}px`; box.setAttribute('data-side', 'top'); }

            cancel.focus({preventScroll: true});
            // Registered last: the click that opened the bubble must not close it, and focusing must not count as a scroll.
            document.addEventListener('mousedown', outside, true);
            window.addEventListener('scroll', away, true);
            window.addEventListener('resize', away);
        });
    }

    Object.assign(window.Console, {busy, confirm});
})();
