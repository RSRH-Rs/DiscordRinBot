/* Console vertical rhythm checker (spec: docs/superpowers/specs/2026-11-08-ui-polish-design.md §7).
   Use it like align-audit.js: paste into the browser console on a console page, or pass it to the preview's JS tool. It walks
   every page, or every settings panel, and resolves to {width, skipped, problems}, where each code lists what it found:
   H  page head to the next block is not 24px          S  section to section is not 32px
   T  section title to its list is not 8px             N  notice to the content below is not 16px
   A  list to its actions is not 16px                  R  actions to the text below are not 24px */
(async () => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const box = el => el.getBoundingClientRect();
    const shown = el => { const r = box(el); return r.width > 1 && r.height > 1 && !el.closest('[hidden], .sr-only'); };
    const name = el => (el.id ? '#' + el.id : el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''));
    const next = el => { let sibling = el.nextElementSibling; while (sibling && !shown(sibling)) sibling = sibling.nextElementSibling; return sibling; };
    const problems = {H: [], S: [], T: [], N: [], A: [], R: []};
    const RULES = [
        ['H', '.page-head', 24, null],
        ['S', '.section', 32, '.section'],
        ['T', '.section-title, .section-hint, .section-head', 8, '.list, .case-list, .lb-list'],
        ['N', '.note', 16, null],
        ['A', '.list', 16, '.actions'],
        ['R', '.actions', 24, '.section-hint'],
    ];

    function audit(root, where) {
        for (const [code, from, want, to] of RULES) {
            root.querySelectorAll(from).forEach(a => {
                const b = shown(a) && next(a);
                if (!b || b.matches('.master-hint') || (to && !b.matches(to))) return;
                const gap = Math.round(box(b).top - box(a).bottom);
                const line = `${where}: ${name(a)} to ${name(b)} is ${gap}, wants ${want}`;
                if (gap !== want && !problems[code].includes(line)) problems[code].push(line);
            });
        }
    }

    const skipped = [];
    const pages = [...document.querySelectorAll('.page[data-slug]')];
    const panels = [...document.querySelectorAll('[data-settings-panel]')];
    for (const page of pages) {
        const tabs = [...page.querySelectorAll('[role="tab"][data-tab]')].map(tab => tab.dataset.tab);
        for (const tab of tabs.length ? tabs : [null]) {
            const where = page.dataset.slug + (tab ? '/' + tab : '');
            location.hash = where;
            await sleep(400);
            if (!page.classList.contains('is-active')) { skipped.push(where); continue; }
            audit(page, where);
        }
    }
    for (const panel of panels) {
        location.hash = panel.dataset.settingsPanel;
        await sleep(400);
        if (panel.hidden) { skipped.push('settings/' + panel.dataset.settingsPanel); continue; }
        audit(panel, 'settings/' + panel.dataset.settingsPanel);
    }
    if (!pages.length && !panels.length) audit(document.querySelector('.content') || document.body, location.pathname);
    return {width: innerWidth, skipped, problems};
})()
