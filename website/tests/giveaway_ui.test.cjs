// Giveaway list: running giveaways count down on one shared timer.
const {test, mock, beforeEach, afterEach} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = name => fs.readFileSync(path.join(__dirname, '../static/js', name), 'utf8');
const controls = read('console-controls.js'), giveaway = read('modules/giveaway.js');
const NOW = 1_000_000_000_000, NOW_S = NOW / 1000;

function fixture(list) {
    const active = new Set(), listeners = {};
    const box = {
        html: '', nodes: [],
        set innerHTML(value) { this.html = value; this.nodes = [...value.matchAll(/data-end="(\d+)"/g)].map(m => ({dataset: {end: m[1]}, textContent: ''})); },
        get innerHTML() { return this.html; },
        querySelectorAll() { return this.nodes; },
    };
    const stub = {value: '', dispatchEvent() {}, addEventListener() {}};
    let def;
    const document = {
        hidden: false,
        getElementById: id => id === 'gw-list' ? box : stub,
        querySelectorAll: () => [],
        addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    };
    const ctx = vm.createContext({
        setTimeout: (fn, ms) => { const id = setTimeout(() => { active.delete(id); fn(); }, ms); active.add(id); return id; },
        clearTimeout: id => { active.delete(id); clearTimeout(id); },
        Date, Event: class {}, document,
        Console: {
            tr: (key, vars) => vars ? `${key}:${Object.values(vars).join(',')}` : key, escapeHtml: s => String(s),
            api: async () => list, module: d => { def = d; }, channels: async () => [], roles: async () => [], channelOptions() {}, roleOptions() {},
        },
    });
    ctx.window = ctx;
    vm.runInContext(controls, ctx);
    vm.runInContext(giveaway, ctx);
    (listeners.DOMContentLoaded || []).forEach(fn => fn());
    return {box, active, document, load: () => def.load(), fire: type => (listeners[type] || []).forEach(fn => fn())};
}
const running = seconds => ({id: 1, prize: 'Nitro', end_time: NOW_S + seconds, ended: 0, winners_count: 1});

beforeEach(() => mock.timers.enable({apis: ['setTimeout', 'Date'], now: NOW}));
afterEach(() => mock.timers.reset());

test('passing zero shows drawing and stops the timer', async () => {
    const page = fixture([running(2)]);
    await page.load();
    assert.equal(page.box.nodes[0].textContent, 'giveaway.left_minutes:0,02');
    mock.timers.tick(1000);
    mock.timers.tick(1000);
    assert.equal(page.box.nodes[0].textContent, 'giveaway.drawing');
    assert.equal(page.active.size, 0);
});

test('reloading the list leaves one timer', async () => {
    const page = fixture([running(90)]);
    await page.load();
    await page.load();
    assert.equal(page.active.size, 1);
});

test('ended giveaways keep the end time', async () => {
    const page = fixture([{...running(-60), ended: 1}]);
    await page.load();
    assert.doesNotMatch(page.box.html, /data-end/);
    assert.equal(page.active.size, 0);
});

test('an empty list clears a running timer', async () => {
    const list = [running(90)];
    const page = fixture(list);
    await page.load();
    list.length = 0;
    await page.load();
    assert.equal(page.active.size, 0);
});

test('the timer stops while the tab is hidden and resumes after', async () => {
    const page = fixture([running(90)]);
    await page.load();
    page.document.hidden = true;
    mock.timers.tick(1000);
    assert.equal(page.active.size, 0);
    page.document.hidden = false;
    page.fire('visibilitychange');
    assert.equal(page.active.size, 1);
});
