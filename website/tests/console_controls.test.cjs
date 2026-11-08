// Shared console controls, with a hand-written DOM and mocked timers.
const {test, mock, beforeEach, afterEach} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/console-controls.js'), 'utf8');

function load(extra = {}) {
    const active = new Set();
    const ctx = vm.createContext({
        setTimeout: (fn, ms) => { const id = setTimeout(() => { active.delete(id); fn(); }, ms); active.add(id); return id; },
        clearTimeout: id => { active.delete(id); clearTimeout(id); },
        Date,
        Console: {tr: (key, vars) => vars ? `${key}:${Object.values(vars).join(',')}` : key},
        document: {addEventListener() {}},
        ...extra,
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    return {Console: ctx.Console, active, ctx};
}
function makeButton() {
    const attrs = new Map();
    return {getAttribute: n => attrs.has(n) ? attrs.get(n) : null, setAttribute: (n, v) => attrs.set(n, String(v)), removeAttribute: n => attrs.delete(n)};
}
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; }
const flush = () => new Promise(resolve => setImmediate(resolve));

beforeEach(() => mock.timers.enable({apis: ['setTimeout', 'Date']}));
afterEach(() => mock.timers.reset());

test('a fast task never shows the spinner', async () => {
    const {Console} = load(), button = makeButton(), done = deferred();
    const run = Console.busy(button, () => done.promise);
    assert.equal(button.getAttribute('aria-disabled'), 'true');
    mock.timers.tick(149);
    done.resolve('ok');
    assert.equal(await run, 'ok');
    assert.equal(button.getAttribute('aria-busy'), null);
    assert.equal(button.getAttribute('aria-disabled'), null);
});

test('a shown spinner stays at least 300ms', async () => {
    const {Console} = load(), button = makeButton(), done = deferred();
    const run = Console.busy(button, () => done.promise);
    mock.timers.tick(150);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    done.resolve('ok');
    await flush();
    mock.timers.tick(299);
    await flush();
    assert.equal(button.getAttribute('aria-busy'), 'true');
    mock.timers.tick(1);
    assert.equal(await run, 'ok');
    assert.equal(button.getAttribute('aria-busy'), null);
});

test('a second call while busy does not run the task', async () => {
    const {Console} = load(), button = makeButton(), done = deferred();
    let calls = 0;
    const first = Console.busy(button, () => done.promise);
    assert.equal(await Console.busy(button, async () => { calls++; }), undefined);
    assert.equal(calls, 0);
    done.resolve();
    await first;
});

test('a failing task rejects and still restores the button', async () => {
    const {Console} = load(), button = makeButton();
    await assert.rejects(Console.busy(button, async () => { throw new Error('nope'); }), /nope/);
    assert.equal(button.getAttribute('aria-disabled'), null);
});

test('the button can be used again after a task ends', async () => {
    const {Console} = load(), button = makeButton();
    await Console.busy(button, async () => {});
    assert.equal(await Console.busy(button, async () => 'again'), 'again');
});

test('a button that was already aria-disabled stays that way', async () => {
    const {Console} = load(), button = makeButton();
    button.setAttribute('aria-disabled', 'false');
    await Console.busy(button, async () => {});
    assert.equal(button.getAttribute('aria-disabled'), 'false');
});

test('a button removed from the page mid-task is harmless', async () => {
    const {Console, active} = load(), done = deferred();
    const detached = makeButton();
    const run = Console.busy(detached, () => done.promise);
    done.resolve('gone');
    assert.equal(await run, 'gone');
    assert.equal(active.size, 0);
});
