// Automod page: out-of-range durations and switch-dependent rows, using the real console core.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = name => fs.readFileSync(path.join(__dirname, '../static/js/', name), 'utf8');
const flatten = (node, prefix = '') => Object.entries(node).reduce((out, [k, v]) =>
    Object.assign(out, typeof v === 'object' ? flatten(v, prefix + k + '.') : {[prefix + k]: v}), {});
const strings = flatten(JSON.parse(fs.readFileSync(path.join(__dirname, '../i18n/zh.json'), 'utf8')));

function page(config) {
    const nodes = {};
    const node = (id, props = {}) => (nodes[id] = {id, value: '', checked: false, dispatched: [], listeners: {},
        dispatchEvent(e) { this.dispatched.push(e.type); (this.listeners[e.type] || []).forEach(fn => fn(e)); },
        addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
        replaceChildren(...kids) { this.children = kids; }, querySelectorAll: () => [], ...props});
    for (const id of ['am-enabled', 'am-spam', 'am-bw', 'am-link', 'am-caps', 'am-repeat']) node(id, {type: 'checkbox'});
    for (const id of ['am-log', 'am-st', 'am-si', 'am-ct', 'am-rt', 'am-bw-new', 'am-wl-new']) node(id);
    node('am-mute', {type: 'number', min: '60', max: '86400'});
    node('am-bw-tags'); node('am-wl-tags');
    let module;
    const requests = [];
    const ctx = vm.createContext({
        document: {getElementById: id => nodes[id], addEventListener() {}, querySelectorAll: () => []},
        DashboardUI: {tr: (k, v = {}) => Object.entries(v).reduce((s, [a, b]) => s.replaceAll('{' + a + '}', b), strings[k] ?? k),
            renderTags: (list, values) => { list.values = values; }, onSave() {}, changed() {}},
        Option: class { constructor(text, value) { this.text = text; this.value = value; } },
        Event: class { constructor(type) { this.type = type; } },
        fetch: async url => ({ok: true, json: async () => url.endsWith('/automod') ? config : []}),
        GID: '1',
    });
    ctx.window = ctx;
    vm.runInContext(read('console-core.js'), ctx);
    const realModule = ctx.Console.module;
    ctx.Console.module = def => { module = def; };
    ctx.Console.api = async (path, method, body) => { requests.push([path, method, body]); return path === '/automod' ? config : []; };
    vm.runInContext(read('modules/automod.js'), ctx);
    void realModule;
    return {ctx, nodes, module: () => module, requests};
}

test('out-of-range stored duration is shown as is and blocks save with the allowed range', async () => {
    const {nodes, module, requests} = page({enabled: 1, mute_duration: 100000, badwords: ['a'], link_whitelist: []});
    await module().load();
    assert.equal(nodes['am-mute'].value, '100000');
    assert.ok(nodes['am-mute'].dispatched.includes('change'));
    await assert.rejects(module().save(), /1 分钟.*1 天/);
    assert.equal(requests.filter(r => r[1] === 'POST').length, 0);
});

test('a disabled out-of-range duration does not block saving', async () => {
    const {nodes, module, requests} = page({enabled: 1, mute_duration: 100000, badwords: [], link_whitelist: []});
    await module().load();
    nodes['am-mute'].disabled = true;
    await module().save();
    assert.equal(requests.filter(r => r[1] === 'POST').length, 1);
});

test('save sends tags from the chip lists and numeric fields', async () => {
    const {nodes, module, requests} = page({enabled: 1, mute_duration: 300, badwords: [], link_whitelist: []});
    await module().load();
    nodes['am-bw-tags'].querySelectorAll = () => [{dataset: {value: '坏词'}}];
    nodes['am-st'].value = '6';
    await module().save();
    const body = requests.find(r => r[1] === 'POST')[2];
    assert.deepEqual(JSON.parse(JSON.stringify(body.badwords)), ['坏词']);
    assert.equal(body.spam_threshold, 6);
    assert.equal(body.mute_duration, 300);
});

test('master switch disables dependent rows and their controls', () => {
    const {ctx, nodes} = page({});
    const control = {disabled: false};
    const row = {dataset: {dependsOn: 'am-enabled'}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, querySelectorAll: () => [control]};
    nodes['am-enabled'].closest = () => null;
    const root = {querySelectorAll: () => [row]};
    nodes['am-enabled'].checked = false;
    ctx.Console.dependencies(root);
    assert.equal(row.attrs['aria-disabled'], 'true');
    assert.equal(control.disabled, true);
    nodes['am-enabled'].checked = true;
    ctx.Console.dependencies(root);
    assert.equal(row.attrs['aria-disabled'], 'false');
    assert.equal(control.disabled, false);
});
