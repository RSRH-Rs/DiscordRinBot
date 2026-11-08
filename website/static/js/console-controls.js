/* Controls shared by console pages: the busy state of a button. Loaded after console-core.js, adds to window.Console. */
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

    Object.assign(window.Console, {busy});
})();
