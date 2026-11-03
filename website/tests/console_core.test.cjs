// Console core helpers with stubbed DashboardUI/DashboardExtras and no browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/console-core.js'), 'utf8');

function core({dirty = false, fetchImpl, nodes = {}} = {}) {
    const calls = {shake: 0, fetch: []};
    const ctx = vm.createContext({
        document: {addEventListener() {}, querySelectorAll: () => [{id: 'pg-welcome'}], getElementById: id => nodes[id] || null},
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

test('switcher links are guarded by the draft check', () => {
    const blocked = core({dirty: true});
    const link = {dataset: {}, href: '/dashboard'};
    const event = {target: {closest: sel => sel === '#switcher-pop a' ? link : null}, prevented: false, preventDefault() { this.prevented = true; }};
    blocked.Console.leaveClick(event);
    assert.equal(event.prevented, true);
    assert.equal(blocked.calls.confirm, 1);
});

test('invite links open a new tab without the draft check', () => {
    const blocked = core({dirty: true});
    const link = {dataset: {}, href: 'https://discord.com/oauth2/authorize', target: '_blank'};
    const event = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
    blocked.Console.leaveClick(event);
    assert.equal(event.prevented, false);
    assert.equal(blocked.calls.confirm, undefined);
});

test('switching server while a page has unsaved changes is blocked', () => {
    const blocked = core({dirty: true});
    const link = {dataset: {guild: '456'}, href: '/dashboard/server/456'};
    const event = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
    blocked.Console.leaveClick(event);
    assert.equal(event.prevented, true);
    assert.equal(blocked.calls.confirm, 1);
    const free = core({dirty: false});
    const pass = {target: {closest: () => link}, prevented: false, preventDefault() { this.prevented = true; }};
    free.Console.leaveClick(pass);
    assert.equal(pass.prevented, false);
});

test('the brand row back to the homepage is guarded by the draft check', () => {
    const blocked = core({dirty: true});
    const link = {dataset: {}, href: '/'};
    const event = {target: {closest: sel => sel === 'a.brand-row' ? link : null}, prevented: false, preventDefault() { this.prevented = true; }};
    blocked.Console.leaveClick(event);
    assert.equal(event.prevented, true);
    assert.equal(blocked.calls.confirm, 1);
    assert.equal(link.href, '/');
});

test('setTitles writes the hidden heading, the mobile bar and the tab title', () => {
    const nodes = {'page-title': {textContent: ''}, 'topbar-title': {textContent: ''}};
    const {Console} = core({nodes});
    Console.setTitles('自动审核');
    assert.equal(nodes['page-title'].textContent, '自动审核');
    assert.equal(nodes['topbar-title'].textContent, '自动审核');
});

test('setTitles works on pages without the hidden heading', () => {
    const {Console} = core();
    assert.doesNotThrow(() => Console.setTitles('我的服务器'));
});

test('selectTab shows one panel and marks its tab', () => {
    const panel = id => ({dataset: {panel: id}, hidden: false});
    const tab = id => ({dataset: {tab: id}, attrs: {}, tabIndex: 0, setAttribute(k, v) { this.attrs[k] = v; }});
    const panelsList = ['message', 'card', 'farewell'].map(panel), tabsList = ['message', 'card', 'farewell'].map(tab);
    const emojiButton = {dataset: {tab: 'custom'}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }};
    const page = {querySelectorAll: sel => sel === '[data-panel]' ? panelsList : sel === '[role="tab"][data-tab]' ? tabsList : sel === '[data-tab]' ? [...tabsList, emojiButton] : []};
    const {Console} = core({nodes: {'pg-welcome': page}});
    assert.equal(Console.selectTab('welcome', 'card'), 'card');
    assert.deepEqual(panelsList.map(p => p.hidden), [true, false, true]);
    assert.deepEqual(tabsList.map(t => t.attrs['aria-selected']), ['false', 'true', 'false']);
    assert.deepEqual(tabsList.map(t => t.tabIndex), [-1, 0, -1]);
    assert.deepEqual(emojiButton.attrs, {});
    assert.equal(Console.selectTab('welcome', 'nope'), 'message');
    assert.equal(Console.selectTab('music', null), null);
});

test('master hint shows while the master switch is off', () => {
    const source = {checked: false, closest: () => null, listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; }};
    const hint = {hidden: true};
    const row = {dataset: {dependsOn: 'w-enabled'}, setAttribute() {}, querySelectorAll: () => []};
    const {Console} = core({nodes: {'w-enabled': source}});
    const root = {querySelectorAll: sel => sel === '[data-depends-on]' ? [row] : sel === '[data-master-hint]' ? [Object.assign(hint, {dataset: {masterHint: 'w-enabled'}})] : []};
    Console.dependencies(root);
    assert.equal(hint.hidden, false);
    source.checked = true;
    Console.dependencies(root);
    assert.equal(hint.hidden, true);
});
