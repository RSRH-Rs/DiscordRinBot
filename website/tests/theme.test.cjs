// Appearance switch: day / follow system / night, with storage that may be blocked.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/theme.js'), 'utf8');

function page({blocked = false, stored = null} = {}) {
    const store = new Map(stored === null ? [] : [['rin-theme', stored]]);
    const listeners = {};
    const button = value => ({dataset: {themeSet: value}, attrs: {}, handlers: {},
        setAttribute(k, v) { this.attrs[k] = String(v); }, addEventListener(type, fn) { this.handlers[type] = fn; }});
    const buttons = [button('light'), button(''), button('dark')];
    const root = {dataset: {}};
    const ctx = vm.createContext({
        document: {documentElement: root, querySelectorAll: sel => sel === '[data-theme-set]' ? buttons : [],
            addEventListener(type, fn) { listeners[type] = fn; }},
        localStorage: {
            getItem(k) { if (blocked) throw Error('blocked'); return store.has(k) ? store.get(k) : null; },
            setItem(k, v) { if (blocked) throw Error('blocked'); store.set(k, v); },
        },
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    listeners.DOMContentLoaded?.();
    return {Theme: ctx.Theme, root, buttons, store};
}
const pressed = buttons => buttons.map(b => b.attrs['aria-pressed']);

test('set("dark") writes the attribute, storage and pressed state', () => {
    const {Theme, root, buttons, store} = page();
    Theme.set('dark');
    assert.equal(root.dataset.theme, 'dark');
    assert.equal(store.get('rin-theme'), 'dark');
    assert.deepEqual(pressed(buttons), ['false', 'false', 'true']);
});

test('set("") follows the system and clears storage', () => {
    const {Theme, root, buttons, store} = page({stored: 'dark'});
    Theme.set('');
    assert.equal('theme' in root.dataset, false);
    assert.equal(store.get('rin-theme'), '');
    assert.deepEqual(pressed(buttons), ['false', 'true', 'false']);
});

test('buttons start pressed according to the stored choice', () => {
    const {buttons} = page({stored: 'light'});
    assert.deepEqual(pressed(buttons), ['true', 'false', 'false']);
});

test('blocked storage never breaks switching', () => {
    const {Theme, root, buttons} = page({blocked: true});
    assert.equal(Theme.get(), '');
    assert.deepEqual(pressed(buttons), ['false', 'true', 'false']);
    Theme.set('dark');
    assert.equal(root.dataset.theme, 'dark');
});

test('clicking a button switches theme', () => {
    const {root, buttons} = page();
    buttons[0].handlers.click();
    assert.equal(root.dataset.theme, 'light');
});
