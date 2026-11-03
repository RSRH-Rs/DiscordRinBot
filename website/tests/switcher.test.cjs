// Sidebar server switcher: filtering and closing, with a stubbed DOM.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/server-switcher.js'), 'utf8');

function page() {
    const listeners = {};
    const node = (props = {}) => ({hidden: false, attrs: {}, handlers: {}, setAttribute(k, v) { this.attrs[k] = String(v); },
        addEventListener(type, fn) { this.handlers[type] = fn; }, focus() { this.focused = true; }, contains: () => false, ...props});
    const items = [['小凛的家', 'joined'], ['Gaming Hub', 'joined'], ['学习群', 'invite']].map(([name, group]) => node({dataset: {name, group}}));
    const groups = ['joined', 'invite'].map(g => node({dataset: {switcherGroup: g}}));
    const nodes = {'switcher-btn': node(), 'switcher-pop': node({hidden: true}), 'switcher-search': node({value: ''}), 'switcher-empty': node({hidden: true}), switcher: node()};
    const ctx = vm.createContext({
        document: {
            getElementById: id => nodes[id] || null,
            querySelectorAll: sel => sel === '[data-switcher-item]' ? items : sel === '[data-switcher-group]' ? groups : [],
            addEventListener(type, fn) { listeners[type] = fn; },
        },
        DashboardExtras: {matches: (text, query) => text.toLowerCase().includes(query.trim().toLowerCase())},
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    listeners.DOMContentLoaded?.();
    return {Switcher: ctx.ServerSwitcher, nodes, items, groups, listeners};
}

test('filter hides non-matching servers and reports the count', () => {
    const {Switcher, nodes, items, groups} = page();
    assert.equal(Switcher.filter('gam'), 1);
    assert.deepEqual(items.map(i => i.hidden), [true, false, true]);
    assert.deepEqual(groups.map(g => g.hidden), [false, true]);
    assert.equal(nodes['switcher-empty'].hidden, true);
    assert.equal(Switcher.filter('nothing'), 0);
    assert.equal(nodes['switcher-empty'].hidden, false);
    assert.equal(Switcher.filter(''), 3);
});

test('open resets the search and focuses it', () => {
    const {Switcher, nodes} = page();
    nodes['switcher-search'].value = 'old';
    Switcher.open();
    assert.equal(nodes['switcher-pop'].hidden, false);
    assert.equal(nodes['switcher-btn'].attrs['aria-expanded'], 'true');
    assert.equal(nodes['switcher-search'].value, '');
    assert.equal(nodes['switcher-search'].focused, true);
});

test('Escape and outside click close the popover', () => {
    const {Switcher, nodes, listeners} = page();
    Switcher.open();
    listeners.keydown({key: 'Escape'});
    assert.equal(nodes['switcher-pop'].hidden, true);
    assert.equal(nodes['switcher-btn'].focused, true);
    Switcher.open();
    listeners.click({target: {}});
    assert.equal(nodes['switcher-pop'].hidden, true);
    assert.equal(nodes['switcher-btn'].attrs['aria-expanded'], 'false');
});
