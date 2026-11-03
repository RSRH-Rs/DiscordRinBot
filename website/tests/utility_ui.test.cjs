// Command toggles page: grouping, labels, immediate saves and their failure handling.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/utility.js'), 'utf8');
const strings = {'cogs.Music': '音乐', 'utility.group_count': '{n} 条'};

function element(tag = 'div') {
    return {tag, children: [], attrs: {}, dataset: {}, classList: {add() {}, toggle() {}}, textContent: '', disabled: false, open: false,
        append(...kids) { this.children.push(...kids); }, replaceChildren(...kids) { this.children = kids; },
        setAttribute(k, v) { this.attrs[k] = v; }, querySelectorAll: () => [], addEventListener() {}};
}
function fixture(api) {
    const elements = {'util-commands': element(), 'command-search': {value: ''}, 'command-filter': {value: 'all'}, 'util-search-status': element(), 'util-summary': element()};
    const toasts = [];
    const ctx = vm.createContext({
        document: {getElementById: id => elements[id], createElement: element, addEventListener() {}},
        DashboardExtras: {matches: (s, q) => s.toLowerCase().includes(q.toLowerCase())},
        Console: {tr: (k, v = {}) => Object.entries(v).reduce((s, [a, b]) => s.replace('{' + a + '}', b), strings[k] ?? k),
            api: (...args) => api(...args), toast: (...args) => toasts.push(args), commands: async () => [], module() {}},
        addEventListener() {},
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    const T = ctx.CommandToggles;
    T.setData([{name: 'play', desc: 'music', cog: 'Music', enabled: true}, {name: 'skip', desc: 'music', cog: 'Music', enabled: true},
        {name: 'help', desc: 'help', cog: 'Netease', enabled: true, protected: true}]);
    const state = () => JSON.parse(JSON.stringify(T.data()));
    return {T, state, elements, toasts};
}

test('cog label uses the dictionary and falls back to the raw cog name', () => {
    const {T} = fixture(async () => ({ok: true}));
    assert.equal(T.cogLabel('Music'), '音乐');
    assert.equal(T.cogLabel('Netease'), 'Netease');
});

test('groups render open with their translated label', () => {
    const {T, elements} = fixture(async () => ({ok: true}));
    T.render();
    const groups = elements['util-commands'].children;
    assert.equal(groups.length, 2);
    assert.ok(groups.every(g => g.open === true));
    assert.match(groups[0].children[0].textContent, /^音乐/);
});

test('failed immediate toggle preserves prior state; retry succeeds', async () => {
    let fail = true;
    const {T, state, toasts} = fixture(async () => { if (fail) throw Error('503'); return {ok: true}; });
    await T.toggleCommand('play', false);
    assert.equal(state()[0].enabled, true);
    assert.equal(toasts.at(-1)[1], 'bad');
    fail = false;
    await T.toggleCommand('play', false);
    assert.equal(state()[0].enabled, false);
});

test('filtered bulk toggle affects only visible unprotected commands', async () => {
    const requests = [];
    const {T, state, elements} = fixture(async (...args) => { requests.push(args); return {ok: true}; });
    elements['command-search'].value = 'play';
    await T.toggleCategory('Music', false);
    assert.equal(state()[0].enabled, false); assert.equal(state()[1].enabled, true); assert.equal(state()[2].enabled, true);
    assert.equal(requests.length, 1); assert.equal(requests[0][2].name, 'play');
    await T.toggleCommand('help', false);
    assert.equal(requests.length, 1);
});

test('pending toggle blocks duplicates; application errors do not update local state', async () => {
    let finish, calls = 0;
    const {T, state} = fixture(() => new Promise(resolve => { calls++; finish = resolve; }));
    const first = T.toggleCommand('play', false);
    await T.toggleCommand('skip', false);
    assert.equal(calls, 1);
    finish({ok: false, error: 'denied'});
    await first;
    assert.ok(state().every(c => c.enabled));
});
