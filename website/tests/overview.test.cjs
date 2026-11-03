// Overview summaries and quick toggles with stubbed Console/DashboardUI.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/overview.js'), 'utf8');
const channels = [{id: '7', name: 'welcome'}, {id: '8', name: 'mod-log'}];

function overview({dirty = false, api} = {}) {
    const calls = {api: [], invalidate: [], toast: [], refresh: 0};
    const Console = {
        tr: (key, vars) => vars ? key + JSON.stringify(vars) : key,
        channelName: (id, list) => list.find(c => c.id === String(id))?.name ?? null,
        api: async (...args) => { calls.api.push(args); return api ? api(...args) : {ok: true, config_state: 'enabled'}; },
        invalidate: slug => calls.invalidate.push(slug),
        toast: (...args) => calls.toast.push(args),
        refreshModules: () => { calls.refresh++; },
        channels: async () => channels,
    };
    const ctx = vm.createContext({document: {addEventListener() {}, getElementById: () => null, querySelectorAll: () => []},
        Console, DashboardUI: {dirty: () => dirty}});
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    return {Overview: ctx.Overview, calls};
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

test('toggle is blocked while the module page has unsaved changes', async () => {
    const {Overview, calls} = overview({dirty: true});
    const input = {checked: false, disabled: false, closest: () => ({setAttribute() {}, removeAttribute() {}})};
    assert.equal(await Overview.toggle('welcome', false, input), false);
    assert.equal(calls.api.length, 0);
    assert.equal(input.checked, true);
    assert.equal(calls.toast[0][0], 'overview.toggle_blocked');
});

test('toggle failure restores the switch and says why', async () => {
    const {Overview, calls} = overview({api: async () => { throw Error('500'); }});
    const input = {checked: true, disabled: false, closest: () => ({setAttribute() {}, removeAttribute() {}})};
    assert.equal(await Overview.toggle('automod', true, input), false);
    assert.equal(input.checked, false);
    assert.equal(input.disabled, false);
    assert.match(calls.toast[0][0], /overview.toggle_failed/);
    assert.deepEqual(calls.invalidate, []);
});

test('toggle success posts enabled-only and invalidates the module page', async () => {
    const {Overview, calls} = overview();
    const input = {checked: false, disabled: false, closest: () => ({setAttribute() {}, removeAttribute() {}})};
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
