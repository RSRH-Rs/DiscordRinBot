// Overview summaries and quick toggles with stubbed Console/DashboardUI.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/overview.js'), 'utf8');
const channels = [{id: '7', name: 'welcome'}, {id: '8', name: 'mod-log'}];

function node(props = {}) {
    const classes = new Set();
    return {hidden: false, disabled: false, checked: false, attrs: {}, dataset: {}, textContent: '', children: [], handlers: {},
        classList: {toggle(c, on) { if (on) classes.add(c); else classes.delete(c); }, contains: c => classes.has(c)},
        setAttribute(k, v) { this.attrs[k] = String(v); }, append(...kids) { this.children.push(...kids); },
        replaceChildren(...kids) { this.children = kids; }, addEventListener(type, fn) { this.handlers[type] = fn; },
        closest: () => null, ...props};
}
function card(slug, toggle) {
    const parts = {summary: node({dataset: {blurb: slug + ' blurb'}}), state: node(), input: toggle ? node({disabled: true, dataset: {toggle: slug}}) : null};
    return Object.assign(node({dataset: {row: slug}}), {parts,
        querySelector: sel => sel === '[data-summary]' ? parts.summary : sel === '[data-state]' ? parts.state : sel === 'input[data-toggle]' ? parts.input : null});
}
function overview({dirty = false, api, nodes = {}, cards = [], checkup = null} = {}) {
    const calls = {api: [], invalidate: [], toast: [], refresh: 0};
    const listeners = {};
    const Console = {
        tr: (key, vars) => vars ? key + JSON.stringify(vars) : key,
        channelName: (id, list) => list.find(c => c.id === String(id))?.name ?? null,
        api: async (...args) => {
            calls.api.push(args);
            if (args[0] === '/checkup') { if (checkup instanceof Error) throw checkup; if (checkup) return checkup; }
            return api ? api(...args) : {ok: true, config_state: 'enabled'};
        },
        invalidate: slug => calls.invalidate.push(slug),
        toast: (...args) => calls.toast.push(args),
        refreshModules: () => { calls.refresh++; },
        channels: async () => channels,
        stateLabel: () => 'state',
        commands: async () => [],
    };
    const ctx = vm.createContext({document: {
        addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
        getElementById: id => nodes[id] || null,
        querySelector: sel => cards.find(c => sel === `[data-row="${c.dataset.row}"]`) || null,
        querySelectorAll: sel => sel === 'input[data-toggle]' ? cards.map(c => c.parts.input).filter(Boolean) : [],
        createElement: tag => node({tagName: tag}),
    }, Console, DashboardUI: {dirty: () => dirty}});
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    const fire = (type, detail) => (listeners[type] || []).forEach(fn => fn({detail}));
    return {Overview: ctx.Overview, calls, fire};
}
const plain = value => value && JSON.parse(JSON.stringify(value));

test('summaryText describes real config and flags what is missing', () => {
    const {Overview} = overview();
    const s = (slug, summary) => plain(Overview.summaryText(slug, summary, channels));
    assert.deepEqual(s('welcome', {welcome_channel: 0, farewell_channel: 0, auto_roles_count: 0}), {text: 'overview.welcome.unset', warn: true});
    assert.deepEqual(s('welcome', {welcome_channel: 7, farewell_channel: 0, auto_roles_count: 2}),
        {text: 'overview.sends_to{"channel":"welcome"} · overview.welcome.roles{"n":2}', warn: false});
    assert.deepEqual(s('botlog', {channel_id: 0}), {text: 'overview.log.unset', warn: true});
    assert.deepEqual(s('serverlog', {channel_id: 5}), {text: 'overview.channel_deleted', warn: true});
    assert.deepEqual(s('automod', {log_channel: 0, rules_on: 3}), {text: 'overview.automod.rules{"n":3}', warn: false});
    assert.deepEqual(s('roles', {panels: 2}), {text: 'overview.roles.panels{"n":2}', warn: false});
    assert.deepEqual(s('giveaway', {active: 0}), {text: 'overview.giveaway.none', warn: false});
    assert.equal(s('music', null), null);
});

test('an unknown channel list falls back to the blurb instead of claiming deletion', () => {
    const {Overview} = overview();
    assert.equal(Overview.summaryText('serverlog', {channel_id: 5}, null), null);
    assert.equal(Overview.summaryText('welcome', {welcome_channel: 7, auto_roles_count: 0}, null), null);
    assert.deepEqual(plain(Overview.summaryText('roles', {panels: 1}, null)), {text: 'overview.roles.panels{"n":1}', warn: false});
});

test('toggle is blocked while the module page has unsaved changes', async () => {
    const {Overview, calls} = overview({dirty: true});
    const input = {checked: false, disabled: false, dataset: {}, closest: () => ({setAttribute() {}, removeAttribute() {}})};
    assert.equal(await Overview.toggle('welcome', false, input), false);
    assert.equal(calls.api.length, 0);
    assert.equal(input.checked, true);
    assert.equal(calls.toast[0][0], 'overview.toggle_blocked');
});

test('toggle failure restores the switch and says why', async () => {
    const {Overview, calls} = overview({api: async () => { throw Error('500'); }});
    const input = {checked: true, disabled: false, dataset: {}, closest: () => ({setAttribute() {}, removeAttribute() {}})};
    assert.equal(await Overview.toggle('automod', true, input), false);
    assert.equal(input.checked, false);
    assert.equal(input.disabled, false);
    assert.match(calls.toast[0][0], /overview.toggle_failed/);
    assert.deepEqual(calls.invalidate, []);
});

test('toggle success posts enabled-only and invalidates the module page', async () => {
    const {Overview, calls} = overview();
    const input = {checked: false, disabled: false, dataset: {}, closest: () => ({setAttribute() {}, removeAttribute() {}})};
    assert.equal(await Overview.toggle('serverlog', false, input), true);
    assert.deepEqual(plain(calls.api[0]), ['/modules/serverlog/enabled', 'POST', {enabled: false}]);
    assert.deepEqual(calls.invalidate, ['serverlog']);
    assert.equal(calls.refresh, 1);
    assert.equal(input.checked, false);
});

test('join duration reads naturally', () => {
    const {Overview} = overview();
    const ago = days => new Date(Date.now() - days * 86400000).toISOString();
    assert.equal(Overview.joinDuration(ago(0.5)), 'overview.duration.today');
    assert.equal(Overview.joinDuration(ago(12)), 'overview.duration.days{"n":12}');
    assert.equal(Overview.joinDuration(ago(400)), 'overview.duration.years_months{"y":1,"m":1}');
});

test('attention lists warned modules in order, at most three', () => {
    const {Overview} = overview();
    const modules = [{slug: 'roles', summary: {panels: 2}}, {slug: 'welcome', summary: {welcome_channel: 0, farewell_channel: 0, auto_roles_count: 0}},
        {slug: 'botlog', summary: {channel_id: 0}}, {slug: 'serverlog', summary: {channel_id: 0}}, {slug: 'automod', summary: {log_channel: 99, rules_on: 1}}];
    assert.deepEqual(plain(Overview.attention(modules, channels)).map(a => a.slug), ['welcome', 'botlog', 'serverlog']);
    assert.equal(plain(Overview.attention(modules, channels))[1].text, 'overview.log.unset');
});

test('attention skips modules when the channel list is unknown', () => {
    const {Overview} = overview();
    assert.deepEqual(plain(Overview.attention([{slug: 'serverlog', summary: {channel_id: 5}}, {slug: 'automod', summary: {log_channel: 9, rules_on: 1}}], null)), []);
});

function overviewPage() {
    const nodes = {'pg-overview': node(), 'ov-attention': node({hidden: true}), 'ov-modules': node(), 'ov-error': node({hidden: true}), 'ov-retry': node(), 'ov-headline': node(), 'ov-facts': node()};
    nodes['ov-modules'].setAttribute('aria-busy', 'true');
    const cards = [card('welcome', true), card('roles', false)];
    return {nodes, cards};
}
const modulesData = enabled => ({modules: [{slug: 'welcome', summary: {welcome_channel: 7, farewell_channel: 0, auto_roles_count: 0, enabled}}, {slug: 'roles', summary: {panels: 1}}]});

test('switches stay disabled until the first render, then follow data', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview} = overview({nodes, cards});
    assert.equal(cards[0].parts.input.disabled, true);
    await Overview.render(modulesData(1));
    assert.equal(cards[0].parts.input.disabled, false);
    assert.equal(cards[0].parts.input.checked, true);
    assert.equal(nodes['ov-modules'].attrs['aria-busy'], 'false');
    assert.equal(cards[0].classList.contains('is-on'), true);
    await Overview.render(modulesData(0));
    assert.equal(cards[0].parts.input.checked, false);
    assert.equal(cards[0].classList.contains('is-on'), false);
    assert.equal(cards[1].classList.contains('is-on'), true);
});

test('module summaries carry their full text as a tooltip', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview} = overview({nodes, cards});
    await Overview.render(modulesData(1));
    const summary = cards[0].parts.summary;
    assert.ok(summary.textContent);
    assert.equal(summary.title, summary.textContent);
});

test('a toggle in flight is not overwritten by render', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview} = overview({nodes, cards});
    cards[0].parts.input.checked = true;
    cards[0].parts.input.disabled = false;
    cards[0].parts.input.dataset.busy = '1';
    await Overview.render(modulesData(0));
    assert.equal(cards[0].parts.input.checked, true);
});

test('attention notices are rendered with a link to the module', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview} = overview({nodes, cards});
    await Overview.render({modules: [{slug: 'botlog', summary: {channel_id: 0}}]});
    assert.equal(nodes['ov-attention'].hidden, false);
    const link = nodes['ov-attention'].children[0].children.find(c => c.tagName === 'a');
    assert.equal(link.dataset.mod, 'botlog');
    await Overview.render({modules: [{slug: 'roles', summary: {panels: 1}}]});
    assert.equal(nodes['ov-attention'].hidden, true);
});

test('first load failure shows retry; retry refreshes', async () => {
    const {nodes, cards} = overviewPage();
    const {calls, fire} = overview({nodes, cards});
    fire('DOMContentLoaded');
    fire('console:modules-failed', Error('500'));
    assert.equal(nodes['ov-error'].hidden, false);
    assert.equal(nodes['ov-modules'].hidden, true);
    nodes['ov-retry'].handlers.click();
    assert.equal(nodes['ov-error'].hidden, true);
    assert.equal(nodes['ov-modules'].hidden, false);
    assert.equal(calls.refresh, 1);
});

test('a later failure keeps the cards that already loaded', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview, fire} = overview({nodes, cards});
    fire('DOMContentLoaded');
    await Overview.render(modulesData(1));
    fire('console:modules-failed', Error('500'));
    assert.equal(nodes['ov-error'].hidden, true);
    assert.equal(nodes['ov-modules'].hidden, false);
});

test('a successful poll after a failed first load brings the cards back', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview, fire} = overview({nodes, cards});
    fire('DOMContentLoaded');
    fire('console:modules-failed', Error('500'));
    await Overview.render(modulesData(1));
    assert.equal(nodes['ov-error'].hidden, true);
    assert.equal(nodes['ov-modules'].hidden, false);
});


const problem = perm => ({code: 'missing_perm', perm, lose: 'x'});
const NOTICES = [{slug: 'welcome', text: 'a'}, {slug: 'botlog', text: 'b'}, {slug: 'serverlog', text: 'c'}];

test('mergeChecks puts blockers first and caps at three', () => {
    const {Overview} = overview();
    const merged = plain(Overview.mergeChecks({available: true, blockers: [problem('A')], warnings: [problem('B')]}, NOTICES));
    assert.equal(merged.length, 3);
    assert.deepEqual(merged.map(n => n.text), ['overview.missing_perm{"perm":"A","lose":"x"}', 'overview.missing_perm{"perm":"B","lose":"x"}', 'a']);
    assert.deepEqual(merged.slice(0, 2).map(n => n.href), ['/permissions', '/permissions']);
    assert.equal(merged[2].slug, 'welcome');
});

test('mergeChecks ignores unavailable checkups', () => {
    const {Overview} = overview();
    assert.deepEqual(plain(Overview.mergeChecks({available: false, blockers: [problem('A')], warnings: []}, NOTICES)), NOTICES);
    assert.deepEqual(plain(Overview.mergeChecks(null, NOTICES)), NOTICES);
});

test('render shows checkup notices linking to the permissions page', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview, calls} = overview({nodes, cards, checkup: {available: true, blockers: [problem('Send Messages')], warnings: []}});
    await Overview.render({modules: [{slug: 'roles', summary: {panels: 1}}]});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(nodes['ov-attention'].hidden, false);
    const [label, link] = nodes['ov-attention'].children[0].children;
    assert.equal(link.href, '/permissions');
    assert.equal(link.textContent, 'overview.attention_go');
    assert.equal(label.textContent, 'overview.missing_perm{"perm":"Send Messages","lose":"x"}');
    await Overview.render({modules: [{slug: 'roles', summary: {panels: 1}}]});
    assert.equal(calls.api.filter(c => c[0] === '/checkup').length, 1);
});

test('render skips the checkup when the request fails', async () => {
    const {nodes, cards} = overviewPage();
    const {Overview} = overview({nodes, cards, checkup: new Error('502')});
    await Overview.render({modules: [{slug: 'botlog', summary: {channel_id: 0}}]});
    assert.equal(nodes['ov-attention'].children.length, 1);
    assert.equal(nodes['ov-attention'].children[0].children[1].dataset.mod, 'botlog');
});

test('module rows update while the checkup is still pending', async () => {
    const {nodes, cards} = overviewPage();
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const {Overview} = overview({nodes, cards, api: async path => path === '/checkup' ? gate : {ok: true}});
    await Overview.render(modulesData(1));
    assert.equal(cards[0].parts.input.checked, true);
    assert.equal(nodes['ov-modules'].hidden, false);
    assert.equal(nodes['ov-attention'].hidden, true);
    release({available: true, blockers: [problem('Send Messages')], warnings: []});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(nodes['ov-attention'].hidden, false);
    assert.equal(nodes['ov-attention'].children[0].children[1].href, '/permissions');
});
