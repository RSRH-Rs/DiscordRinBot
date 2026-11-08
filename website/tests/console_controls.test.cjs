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

// A small DOM for the bubble: nodes know their children, and listeners are kept per target so tests can fire them.
function makeDom({innerHeight = 800, innerWidth = 1200, rect = {top: 100, bottom: 140, left: 300, right: 400}, size = {width: 240, height: 100}} = {}) {
    const bags = {doc: {}, win: {}};
    const on = bag => (type, fn) => { (bag[type] ||= []).push(fn); };
    const off = bag => (type, fn) => { bag[type] = (bag[type] || []).filter(f => f !== fn); };
    const make = tag => {
        const attrs = new Map(), handlers = {};
        const node = {
            tag, className: '', textContent: '', style: {}, children: [], parent: null, handlers,
            append(...kids) { kids.forEach(kid => { kid.parent = node; node.children.push(kid); }); },
            remove() { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null; },
            setAttribute: (n, v) => attrs.set(n, String(v)), getAttribute: n => attrs.has(n) ? attrs.get(n) : null,
            addEventListener: (type, fn) => { handlers[type] = fn; },
            focus() { document.activeElement = node; },
            click() { node.onclick?.(); },
            contains(other) { for (let n = other; n; n = n.parent) if (n === node) return true; return false; },
            getBoundingClientRect: () => size,
        };
        return node;
    };
    const document = {activeElement: null, body: make('body'), createElement: make, addEventListener: on(bags.doc), removeEventListener: off(bags.doc)};
    const anchor = make('button');
    anchor.getBoundingClientRect = () => rect;
    const fire = (where, type, event = {}) => (bags[where][type] || []).slice().forEach(fn => fn(event));
    const extra = {document, innerHeight, innerWidth, addEventListener: on(bags.win), removeEventListener: off(bags.win)};
    return {document, anchor, fire, extra, bubble: () => document.body.children.at(-1), parts: () => { const b = document.body.children.at(-1); return {cancel: b.children[1].children[0], ok: b.children[1].children[1]}; }};
}
const ASK = {message: 'Sure?', action: 'Do it'};

test('the action button resolves true and returns focus', async () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    const answer = Console.confirm(dom.anchor, ASK);
    dom.parts().ok.click();
    assert.equal(await answer, true);
    assert.equal(dom.document.activeElement, dom.anchor);
    assert.equal(dom.document.body.children.length, 0);
});

test('the action button is named after the action and shows danger', () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, {...ASK, danger: true});
    assert.equal(dom.parts().ok.textContent, 'Do it');
    assert.match(dom.parts().ok.className, /btn--danger/);
});

for (const [name, dismiss] of [
    ['cancel', dom => dom.parts().cancel.click()],
    ['Escape', dom => dom.bubble().handlers.keydown({key: 'Escape', preventDefault() {}})],
    ['an outside click', dom => dom.fire('doc', 'mousedown', {target: {parent: null}})],
]) {
    test(`${name} resolves false`, async () => {
        const dom = makeDom(), {Console} = load(dom.extra);
        const answer = Console.confirm(dom.anchor, ASK);
        dismiss(dom);
        assert.equal(await answer, false);
        assert.equal(dom.document.body.children.length, 0);
    });
}

test('a click inside the bubble does not dismiss it', () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, ASK);
    dom.fire('doc', 'mousedown', {target: dom.parts().ok});
    assert.equal(dom.document.body.children.length, 1);
});

test('opening a second bubble cancels the first', async () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    const first = Console.confirm(dom.anchor, ASK);
    Console.confirm(dom.anchor, ASK);
    assert.equal(await first, false);
    assert.equal(dom.document.body.children.length, 1);
});

for (const type of ['scroll', 'resize']) {
    test(`${type} cancels the bubble`, async () => {
        const dom = makeDom(), {Console} = load(dom.extra);
        const answer = Console.confirm(dom.anchor, ASK);
        dom.fire('win', type);
        assert.equal(await answer, false);
    });
}

test('focus starts on cancel and Tab stays inside', () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, ASK);
    const {cancel, ok} = dom.parts(), key = {key: 'Tab', preventDefault() {}};
    assert.equal(dom.bubble().getAttribute('role'), 'alertdialog');
    assert.equal(dom.document.activeElement, cancel);
    dom.bubble().handlers.keydown(key);
    assert.equal(dom.document.activeElement, ok);
    dom.bubble().handlers.keydown(key);
    assert.equal(dom.document.activeElement, cancel);
});

test('sits below the anchor, right-aligned, when there is room', () => {
    const dom = makeDom(), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, ASK);
    assert.equal(dom.bubble().style.top, '148px');
    assert.equal(dom.bubble().style.left, '160px');
});

test('flips above the anchor when there is no room below', () => {
    const dom = makeDom({innerHeight: 200, rect: {top: 150, bottom: 190, left: 300, right: 400}}), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, ASK);
    assert.equal(dom.bubble().style.top, '42px');
    assert.equal(dom.bubble().getAttribute('data-side'), 'top');
});

test('never runs off the left edge of a narrow screen', () => {
    const dom = makeDom({innerWidth: 320, rect: {top: 100, bottom: 140, left: 8, right: 100}}), {Console} = load(dom.extra);
    Console.confirm(dom.anchor, ASK);
    assert.equal(dom.bubble().style.left, '16px');
});
