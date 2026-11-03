// Console core helpers with stubbed DashboardUI/DashboardExtras and no browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/console-core.js'), 'utf8');

function core({dirty = false, fetchImpl} = {}) {
    const calls = {shake: 0, fetch: []};
    const ctx = vm.createContext({
        document: {addEventListener() {}, querySelectorAll: () => [{id: 'pg-welcome'}], getElementById: () => null},
        DashboardUI: {
            tr: (key, vars = {}) => key === 'common.request_failed' ? `请求失败 (${vars.status})` : key,
            dirty: () => dirty, shake: () => { calls.shake++; },
            confirmLeave: roots => { calls.confirm = (calls.confirm || 0) + 1; return !dirty; },
        },
        DashboardExtras: {},
        fetch: async (...args) => { calls.fetch.push(args); return fetchImpl ? fetchImpl(...args) : {ok: true, json: async () => []}; },
        GID: '123',
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    return {Console: ctx.Console, calls};
}

test('duration.split maps presets, exact units and rounds odd values to minutes', () => {
    const {Console} = core();
    const split = s => JSON.parse(JSON.stringify(Console.duration.split(s)));
    assert.deepEqual(split(300), {preset: 300, amount: 5, unit: 'minute'});
    assert.deepEqual(split(5400), {preset: null, amount: 90, unit: 'minute'});
    assert.deepEqual(split(7200), {preset: null, amount: 2, unit: 'hour'});
    assert.deepEqual(split(172800), {preset: null, amount: 2, unit: 'day'});
    assert.deepEqual(split(100000), {preset: null, amount: 1667, unit: 'minute'});
    assert.equal(Console.duration.join(3, 'hour'), 10800);
});

test('tr delegates to the shared dictionary lookup', () => {
    const {Console} = core();
    assert.equal(Console.tr('nope.key'), 'nope.key');
    assert.equal(Console.tr('common.request_failed', {status: 502}), '请求失败 (502)');
});

test('api throws the server error message, or the status when there is none', async () => {
    let body = {error: '坏了'};
    const {Console, calls} = core({fetchImpl: async () => ({ok: false, status: 500, json: async () => body})});
    await assert.rejects(Console.api('/welcome'), /坏了/);
    assert.equal(calls.fetch[0][0], '/api/guild/123/welcome');
    body = {};
    await assert.rejects(Console.api('/welcome', 'POST', {a: 1}), /请求失败 \(500\)/);
    assert.equal(calls.fetch[1][1].body, '{"a":1}');
});

test('channels() dedupes concurrent requests and caches the result', async () => {
    const {Console, calls} = core({fetchImpl: async () => ({ok: true, json: async () => [{id: '1', name: 'general'}]})});
    const [a, b] = await Promise.all([Console.channels(), Console.channels()]);
    assert.equal(calls.fetch.length, 1);
    assert.equal(a, b);
    await Console.channels();
    assert.equal(calls.fetch.length, 1);
    assert.equal(Console.channelName('1', a), 'general');
    assert.equal(Console.channelName('9', a), null);
});

test('home rail item and breadcrumb are guarded too', () => {
    const blocked = core({dirty: true});
    for (const link of [{dataset: {}, href: '/dashboard'}, {dataset: {}, href: '/dashboard#not-joined'}]) {
        const event = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
        blocked.Console.railClick(event);
        assert.equal(event.prevented, true);
    }
    assert.equal(blocked.calls.confirm, 2);
});

test('rail click while a page has unsaved changes is blocked', () => {
    const blocked = core({dirty: true});
    const link = {dataset: {guild: '456'}, href: '/dashboard/server/456'};
    const event = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
    blocked.Console.railClick(event);
    assert.equal(event.prevented, true);
    assert.equal(blocked.calls.confirm, 1);
    const free = core({dirty: false});
    const pass = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
    free.Console.railClick(pass);
    assert.equal(pass.prevented, false);
});
