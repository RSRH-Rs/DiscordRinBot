// Moderation page: recent cases, with Console stubbed and the real Chinese copy.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const flatten = (node, prefix = '') => Object.entries(node).reduce((out, [k, v]) =>
    Object.assign(out, typeof v === 'object' ? flatten(v, prefix + k + '.') : {[prefix + k]: v}), {});
const strings = flatten(JSON.parse(fs.readFileSync(path.join(__dirname, '../i18n/zh.json'), 'utf8')));
const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/moderation.js'), 'utf8');

async function render(cases) {
    const nodes = {};
    const node = id => (nodes[id] ||= {id, value: '', innerHTML: '', dispatchEvent() {}});
    let def;
    const ctx = vm.createContext({
        document: {getElementById: node},
        Event: class { constructor(type) { this.type = type; } },
        Console: {
            tr: (k, v = {}) => Object.entries(v).reduce((s, [a, b]) => s.replaceAll('{' + a + '}', b), strings[k] ?? k),
            escapeHtml: s => String(s).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`),
            module: d => { def = d; },
            api: async url => (url.endsWith('/cases') ? cases : {}),
            channels: async () => [],
            channelOptions() {},
        },
    });
    vm.runInContext(source, ctx);
    await def.load();
    return nodes['mod-cases'].innerHTML;
}

test('cases show their type in Chinese', async () => {
    const html = await render([
        {case_no: 1, action: 'warn', user_name: 'A', mod_name: 'B', reason: 'spam', created_at: 1793750000},
        {case_no: 2, action: 'nuke', user_name: 'A', mod_name: 'B', reason: 'x', created_at: 1793750000},
    ]);
    assert.match(html, /class="chip chip--static chip--warn">#1 警告</);
    assert.match(html, /class="chip chip--static chip--other">#2 其他</);
    assert.doesNotMatch(html, />#1 warn</);
});
