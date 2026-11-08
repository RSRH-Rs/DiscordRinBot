// Ctrl K settings search: entries come from the page structure; IME composition never triggers it.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/command-palette.js'), 'utf8');

function el(props = {}) {
    const classes = new Set();
    return {hidden: false, attrs: {}, dataset: {}, children: [], handlers: {}, value: '',
        classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c)},
        setAttribute(k, v) { this.attrs[k] = String(v); }, replaceChildren(...kids) { this.children = kids; }, append(...kids) { this.children.push(...kids); },
        addEventListener(type, fn) { this.handlers[type] = fn; }, focus() { this.focused = true; }, ...props};
}
function automodPage() {
    const rowBox = el({scrollIntoView() { this.scrolled = true; }});
    const rowTitle = text => ({textContent: text, closest: sel => sel === '[data-panel]' ? {dataset: {panel: 'words'}} : sel === '.row' ? rowBox : null});
    const titles = [rowTitle(' 违禁词列表 '), rowTitle('违禁词')];
    const tabs = [{dataset: {tab: 'rules', label: '规则'}}, {dataset: {tab: 'words', label: '违禁词'}}];
    const emojiButton = {dataset: {tab: 'custom'}};
    const page = {dataset: {slug: 'automod', title: '自动审核', group: '管理与安全'},
        querySelectorAll: sel => sel === '[role="tab"][data-tab]' ? tabs : sel === '[data-tab]' ? [...tabs, emojiButton] : sel === '.row-title' ? titles : []};
    const overview = {dataset: {slug: 'overview', title: '概览', group: ''}, querySelectorAll: () => []};
    return {pages: [overview, page], rowBox};
}
function palette({go = () => true} = {}) {
    const listeners = {}, timers = [], calls = {go: [], drawer: []};
    const {pages, rowBox} = automodPage();
    const nodes = {palette: el({hidden: true}), 'palette-input': el(), 'palette-list': el(), 'palette-btn': el()};
    const ctx = vm.createContext({
        document: {getElementById: id => nodes[id] || null, querySelectorAll: sel => sel === '.page[data-slug]' ? pages : [],
            addEventListener(type, fn) { (listeners[type] ||= []).push(fn); }, createElement: tag => el({tagName: tag}), activeElement: null},
        DashboardUI: {tr: key => ({'nav.overview': '概览', 'palette.empty': '没有找到'})[key] || key, closeSidebar: (...args) => calls.drawer.push(args)},
        DashboardExtras: {matches: (text, query) => text.toLowerCase().includes(query.trim().toLowerCase())},
        Console: {go: (slug, tab, options) => { calls.go.push([slug, tab]); calls.goOptions = options; return go(slug, tab); }},
        setTimeout: (fn, ms) => { timers.push([fn, ms]); return timers.length; },
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    (listeners.DOMContentLoaded || []).forEach(fn => fn());
    const key = props => {
        const e = {key: 'k', ctrlKey: false, metaKey: false, altKey: false, isComposing: false, prevented: false, preventDefault() { this.prevented = true; }, ...props};
        (listeners.keydown || []).forEach(fn => fn(e));
        return e;
    };
    return {Palette: ctx.CommandPalette, nodes, pages, rowBox, timers, calls, key};
}
const plain = value => JSON.parse(JSON.stringify(value, (k, v) => k === 'row' ? (v ? 'row' : null) : v));

test('collect builds page, tab and row entries without duplicates', () => {
    const {Palette, pages} = palette();
    const entries = plain(Palette.collect(pages));
    assert.deepEqual(entries.map(e => e.label), ['概览', '自动审核', '自动审核 › 规则', '自动审核 › 违禁词', '自动审核 › 违禁词列表']);
    assert.deepEqual(entries[0], {label: '概览', where: '概览', slug: 'overview', tab: null, row: null});
    assert.deepEqual(entries[4], {label: '自动审核 › 违禁词列表', where: '管理与安全', slug: 'automod', tab: 'words', row: 'row'});
});

test('filter finds 违禁 and caps at the limit', () => {
    const {Palette, pages} = palette();
    const entries = Palette.collect(pages);
    assert.deepEqual(plain(Palette.filter(entries, ' 违禁 ').map(e => e.label)), ['自动审核 › 违禁词', '自动审核 › 违禁词列表']);
    assert.equal(Palette.filter(entries, '', 2).length, 2);
    assert.equal(Palette.filter(entries, '管理与安全').length, 4);
});

test('jumping from the palette skips the page animation', () => {
    const {Palette, pages, calls} = palette();
    Palette.jump(Palette.collect(pages)[0]);
    assert.equal(calls.goOptions.instant, true);
});

test('the shortcut hint matches the platform', () => {
    const {Palette} = palette();
    assert.equal(Palette.shortcutLabel('MacIntel'), '⌘K');
    assert.equal(Palette.shortcutLabel('iPad'), '⌘K');
    assert.equal(Palette.shortcutLabel('Win32'), 'Ctrl K');
});

test('Ctrl K opens and closes; during IME composition it does nothing', () => {
    const {nodes, key} = palette();
    const composing = key({ctrlKey: true, isComposing: true});
    assert.equal(nodes.palette.hidden, true);
    assert.equal(composing.prevented, false);
    assert.equal(key({ctrlKey: true}).prevented, true);
    assert.equal(nodes.palette.hidden, false);
    assert.equal(nodes['palette-input'].focused, true);
    key({metaKey: true});
    assert.equal(nodes.palette.hidden, true);
});

test('Enter during composition does not jump', () => {
    const {nodes, calls, key} = palette();
    key({ctrlKey: true});
    nodes['palette-input'].value = '违禁';
    nodes['palette-input'].handlers.input();
    key({key: 'Enter', isComposing: true});
    assert.deepEqual(calls.go, []);
    assert.equal(nodes.palette.hidden, false);
    key({key: 'ArrowDown'});
    key({key: 'Enter'});
    assert.deepEqual(plain(calls.go), [['automod', 'words']]);
    assert.equal(nodes.palette.hidden, true);
});

test('jump navigates to the tab and flashes the row', () => {
    const {Palette, pages, rowBox, timers, calls} = palette();
    const entry = Palette.collect(pages).find(e => e.label.endsWith('违禁词列表'));
    assert.equal(Palette.jump(entry), true);
    assert.deepEqual(plain(calls.go), [['automod', 'words']]);
    assert.equal(rowBox.scrolled, true);
    assert.equal(rowBox.classList.contains('is-flash'), true);
    assert.equal(timers[0][1], 1000);
    assert.deepEqual(plain(calls.drawer), [[false]]);
    timers[0][0]();
    assert.equal(rowBox.classList.contains('is-flash'), false);
});

test('jump stops when navigation is blocked', () => {
    const {Palette, pages, rowBox} = palette({go: () => false});
    const entry = Palette.collect(pages).find(e => e.label.endsWith('违禁词列表'));
    assert.equal(Palette.jump(entry), false);
    assert.equal(rowBox.scrolled, undefined);
    assert.equal(rowBox.classList.contains('is-flash'), false);
});
