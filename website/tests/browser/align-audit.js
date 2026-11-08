/* Console alignment checker (spec: docs/superpowers/specs/2026-11-03-console-alignment-design.md §8).
   Paste into the browser console on a console page, or pass it to the preview's JS tool. On a server page it walks every
   page and tab; on the settings page every panel; elsewhere it checks the page once. Run it with no unsaved edits: a page
   the draft guard keeps closed is listed in `skipped`, not checked. It resolves to {width, theme, skipped, problems},
   where each problem code lists what it found:
   A  controls in one grid row with different tops or heights        B  field text not left-aligned
   C  a control whose height is not --control-h                     D  side-by-side controls off one centre line
   E  a block off the content's left edge (.row--sub may sit 16px in) F  a right-hand row control off the row's right edge
   I  a dependent row without .row--sub, or a .row--sub not 16px in   N  number text clipped or under its unit
   O  something past the viewport's right edge                       S  a segmented control with unequal or wrapped options */
(async () => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const box = el => el.getBoundingClientRect();
    const shown = el => { const r = box(el); return r.width > 1 && r.height > 1 && !el.closest('[hidden], .sr-only'); };
    const name = el => (el.id ? '#' + el.id : el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''));
    const near = (a, b, tolerance = 1) => Math.abs(a - b) <= tolerance;
    const controlH = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--control-h')) || 40;
    const CONTROL = '.input, .select, .select-trigger, .num-field, .num, .seg, .btn, .emoji-trigger';
    const isControl = el => el.matches(CONTROL) && !el.matches('.btn--text, .btn--icon, .num-field .num') && el.type !== 'file';
    const problems = {A: [], B: [], C: [], D: [], E: [], F: [], I: [], N: [], O: [], S: []};
    const add = (code, where, text) => { const line = `${where}: ${text}`; if (!problems[code].includes(line)) problems[code].push(line); };
    const canvas = document.createElement('canvas').getContext('2d');
    const textWidth = (text, el) => { const s = getComputedStyle(el); canvas.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`; return canvas.measureText(text).width; };
    // Same-line groups: children whose vertical ranges overlap sit on one line of a wrapping flex row.
    const lines = kids => {
        const groups = [];
        for (const kid of kids) {
            const r = box(kid), group = groups.find(g => g.some(other => { const o = box(other); return r.top < o.bottom && o.top < r.bottom; }));
            group ? group.push(kid) : groups.push([kid]);
        }
        return groups;
    };

    function audit(root, where) {
        const head = [...root.querySelectorAll('.page-head')].find(shown);
        const left = Math.round(box(head || root).left);
        const masters = new Set([...document.querySelectorAll('.tog--head input')].map(input => input.id));
        const h = controlH();
        // A: controls in one grid row
        root.querySelectorAll('*').forEach(grid => {
            if (!shown(grid) || getComputedStyle(grid).display !== 'grid' || grid.children.length < 2) return;
            const rows = new Map();
            [...grid.children].filter(shown).forEach(kid => { const top = Math.round(box(kid).top); rows.set(top, [...(rows.get(top) || []), kid]); });
            rows.forEach(kids => {
                const controls = kids.map(kid => [kid, ...kid.querySelectorAll(CONTROL)].find(el => shown(el) && isControl(el))).filter(Boolean);
                if (controls.length < 2) return;
                const tops = controls.map(c => Math.round(box(c).top)), heights = controls.map(c => Math.round(box(c).height));
                if (new Set(tops).size > 1 || new Set(heights).size > 1) add('A', where, `${controls.map(name).join(' | ')} tops=${tops} heights=${heights}`);
            });
        });
        root.querySelectorAll('input, select, textarea').forEach(field => {
            if (!shown(field) || ['checkbox', 'radio', 'file', 'range', 'color'].includes(field.type)) return;
            const align = getComputedStyle(field).textAlign;
            if (align !== 'left' && align !== 'start') add('B', where, `${name(field)} ${align}`);
        });
        root.querySelectorAll(CONTROL).forEach(control => {
            if (!shown(control) || !isControl(control)) return;
            const height = box(control).height;
            if (!near(height, h, 0.5)) add('C', where, `${name(control)} ${Math.round(height * 10) / 10} vs ${h}`);
        });
        root.querySelectorAll('.row-control, .actions, .seg-custom, .chip-add').forEach(group => {
            for (const line of lines([...group.children].filter(shown))) {
                if (line.length < 2) continue;
                const mids = line.map(kid => box(kid).top + box(kid).height / 2);
                if (Math.max(...mids) - Math.min(...mids) > 1) add('D', where, `${line.map(name).join(' + ')} mids=${mids.map(Math.round)}`);
            }
        });
        root.querySelectorAll('.section > *, .list > *, .row--block > *, .page > *, .tab-panel > *, .editor-form > *, .content--column > *').forEach(block => {
            if (!shown(block)) return;
            const sub = block.closest('.row--sub') ? 16 : 0, at = Math.round(box(block).left);
            if (!near(at, left + sub)) add('E', where, `${name(block)} at ${at} vs ${left + sub}`);
        });
        root.querySelectorAll('.row:not(.row--block) > .row-control').forEach(control => {
            if (!shown(control)) return;
            const row = control.closest('.row'), at = Math.round(box(control).right), edge = Math.round(box(row).right);
            if (!near(at, edge)) add('F', where, `${row.querySelector('.row-title')?.textContent.trim()} ${at} vs ${edge}`);
        });
        root.querySelectorAll('.page-head .tog--head .tog-track').forEach(track => {
            if (!shown(track)) return;
            const at = Math.round(box(track).right), edge = Math.round(box(track.closest('.page-head')).right);
            if (!near(at, edge)) add('F', where, `master switch ${at} vs ${edge}`);
        });
        root.querySelectorAll('[data-depends-on]').forEach(row => {
            if (!shown(row) || !row.matches('.row')) return;
            const title = row.querySelector('.row-title')?.textContent.trim();
            if (!masters.has(row.dataset.dependsOn) && !row.classList.contains('row--sub')) add('I', where, `${title} depends on ${row.dataset.dependsOn} but is not .row--sub`);
        });
        root.querySelectorAll('.row--sub').forEach(row => {
            if (!shown(row)) return;
            const list = row.parentElement, inset = Math.round(box(row).left - box(list).left);
            if (inset !== 16) add('I', where, `${row.querySelector('.row-title')?.textContent.trim()} is ${inset}px in`);
        });
        root.querySelectorAll('input[type=number]').forEach(input => {
            if (!shown(input)) return;
            const s = getComputedStyle(input), r = box(input);
            const textRight = r.left + parseFloat(s.borderLeftWidth) + parseFloat(s.paddingLeft) + textWidth(input.value, input);
            const unit = input.closest('.num-field')?.querySelector('.num-unit');
            const limit = unit ? box(unit).left - 2 : r.right - parseFloat(s.borderRightWidth) - parseFloat(s.paddingRight);
            if (textRight > limit) add('N', where, `${name(input)} "${input.value}" ends at ${Math.round(textRight)}, room until ${Math.round(limit)}`);
        });
        const width = document.documentElement.clientWidth;
        for (const el of root.querySelectorAll('*')) {
            if (!shown(el) || el.closest('.sidebar, .unsaved-bar, .toast, .palette-scrim, .select-popup, .emoji-picker')) continue;
            if (box(el).right <= width + 1) continue;
            let clipped = false;
            for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) if (getComputedStyle(up).overflowX !== 'visible') { clipped = true; break; }
            if (!clipped) add('O', where, `${name(el)} right=${Math.round(box(el).right)} > ${width}`);
        }
        if (document.documentElement.scrollWidth > width) add('O', where, `page scrolls sideways (${document.documentElement.scrollWidth} > ${width})`);
        root.querySelectorAll('.seg').forEach(seg => {
            const options = [...seg.children].filter(el => el.matches('.seg-option') && shown(el));
            if (options.length < 2) return;
            const widths = options.map(o => box(o).width), tops = options.map(o => Math.round(box(o).top));
            if (Math.max(...widths) - Math.min(...widths) > 1) add('S', where, `${seg.getAttribute('aria-label') || name(seg)} widths=${widths.map(Math.round)}`);
            if (new Set(tops).size > 1) add('S', where, `${seg.getAttribute('aria-label') || name(seg)} wraps onto ${new Set(tops).size} lines`);
            for (const option of options) {
                const range = document.createRange(), s = getComputedStyle(option);
                range.selectNodeContents(option);
                const room = box(option).width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - parseFloat(s.borderLeftWidth);
                if (range.getBoundingClientRect().width > room + 0.5) add('S', where, `"${option.textContent}" needs ${Math.round(range.getBoundingClientRect().width)}px, has ${Math.round(room)}px`);
            }
        });
    }

    const pages = [...document.querySelectorAll('.page[data-slug]')];
    const panels = [...document.querySelectorAll('[data-settings-panel]')];
    const skipped = [];
    // Popups and added rows only exist after a click, so open them once at the end: a role row, its emoji picker and
    // the channel picker. The added row is removed again afterwards; a popup that did not open is listed in `skipped`.
    async function auditPopups() {
        const page = document.getElementById('pg-roles');
        location.hash = 'roles';
        await sleep(400);
        if (!page?.classList.contains('is-active')) { skipped.push('roles/popups'); return; }
        const close = () => { document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); page.querySelector('.page-head').click(); };
        // Popups load and position themselves asynchronously; wait up to 2s for one to appear or to go away.
        const until = async (find, want = true) => { for (let i = 0; i < 20; i++) { const found = find(); if (!!found === want) return found; await sleep(100); } return find(); };
        const open = selector => [...document.querySelectorAll(selector)].find(shown);
        document.getElementById('rr-add').click();
        await sleep(200);
        const row = page.querySelector('.rr-row');
        if (row) {
            audit(row, 'roles/role-row');
            const last = row.lastElementChild;
            if (!near(box(last).right, box(row).right)) add('F', 'roles/role-row', `${name(last)} ends at ${Math.round(box(last).right)}, row at ${Math.round(box(row).right)}`);
            row.querySelector('.emoji-trigger')?.click();
            const picker = await until(() => open('.emoji-picker')); await sleep(200);
            if (picker) {
                audit(picker, 'roles/emoji-picker');
                const tabs = picker.querySelector('.ep-tabs'), s = getComputedStyle(picker);
                const inner = box(picker).width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - parseFloat(s.borderLeftWidth) - parseFloat(s.borderRightWidth);
                if (tabs && !near(box(tabs).width, inner)) add('S', 'roles/emoji-picker', `tabs ${Math.round(box(tabs).width)}px wide in a ${Math.round(inner)}px picker`);
            } else skipped.push('roles/emoji-picker');
            close();
            await until(() => open('.emoji-picker'), false);
        } else skipped.push('roles/role-row');
        // The longest list is the one that overflows its popup, which is where a shrinking field shows.
        const longest = [...page.querySelectorAll('.search-select')].sort((a, b) => (b.querySelector('select')?.options.length || 0) - (a.querySelector('select')?.options.length || 0))[0];
        longest?.querySelector('.select-trigger')?.click();
        const popup = await until(() => open('.select-popup')); await sleep(200);
        if (popup) audit(popup, 'roles/select-popup'); else skipped.push('roles/select-popup');
        close();
        await until(() => open('.select-popup'), false);
        row?.lastElementChild.click();
        document.getElementById('unsaved-reset')?.click();
        await sleep(200);
    }
    if (pages.length) {
        for (const page of pages) {
            const tabs = [...page.querySelectorAll('[role="tab"][data-tab]')].map(tab => tab.dataset.tab);
            for (const tab of tabs.length ? tabs : [null]) {
                const where = page.dataset.slug + (tab ? '/' + tab : '');
                location.hash = where;
                await sleep(400);
                // A draft guard can refuse the hash change; a hidden page would pass every check, so report it instead.
                if (!page.classList.contains('is-active')) { skipped.push(where); continue; }
                audit(page, where);
            }
        }
        if (document.getElementById('rr-add')) await auditPopups();
    } else if (panels.length) {
        for (const panel of panels) {
            location.hash = panel.dataset.settingsPanel;
            await sleep(400);
            if (panel.hidden) { skipped.push('settings/' + panel.dataset.settingsPanel); continue; }
            audit(panel, 'settings/' + panel.dataset.settingsPanel);
        }
    } else {
        audit(document.querySelector('.content') || document.body, location.pathname);
    }
    return {width: innerWidth, theme: document.documentElement.dataset.theme || 'system', skipped, problems};
})()
