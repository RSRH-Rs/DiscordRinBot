// Leveling page: reward rows, sorting, warnings, validation and what gets saved.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/leveling.js'), 'utf8');
const plain = value => value && JSON.parse(JSON.stringify(value));

function element(tag = 'div') {
    const classes = new Set();
    const node = {
        tag, children: [], parent: null, listeners: {}, dataset: {}, style: {}, attrs: {}, hidden: false, disabled: false,
        value: '', className: '', textContent: '', innerHTML: '', moves: 0,
        classList: {toggle(name, on) { if (on) classes.add(name); else classes.delete(name); }, contains: name => classes.has(name)},
        append(...kids) {
            for (const kid of kids) {
                if (kid.parent) {
                    if (kid.parent === node) node.moves++;
                    kid.parent.children.splice(kid.parent.children.indexOf(kid), 1);
                }
                kid.parent = node;
                node.children.push(kid);
            }
        },
        replaceChildren(...kids) { node.children.forEach(kid => { kid.parent = null; }); node.children = []; node.append(...kids); },
        remove() { node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null; },
        setAttribute(key, value) { node.attrs[key] = value; },
        addEventListener(type, fn) { (node.listeners[type] ||= []).push(fn); },
        fire(type, event = {}) { (node.listeners[type] || []).forEach(fn => fn(event)); },
        focus() { node.focused = true; },
        scrollIntoView() { node.scrolled = true; },
        contains(other) { for (let at = other; at; at = at.parent) if (at === node) return true; return false; },
    };
    return node;
}

const ROLES = [{id: '1', name: 'one', color: 16711680}, {id: '2', name: 'two', color: 0}, {id: '3', name: 'three', color: 255}];
const CHANNELS = [{id: '77', name: 'news'}];
const CONFIG = {enabled: true, notify_mode: 'here', notify_channel: '0', rewards: [], blocked_roles: {}, can_manage_roles: true};

async function page(config = {}, {roles = ROLES, channels = CHANNELS} = {}) {
    const ids = ['lv-enabled', 'lv-mode', 'lv-channel-row', 'lv-channel', 'lv-channel-error', 'lv-no-permission', 'lv-empty', 'lv-rewards', 'lv-add', 'lv-limit', 'lb-list', 'panel-leveling-settings', 'pg-leveling'];
    const nodes = Object.fromEntries(ids.map(id => [id, element()]));
    const listeners = {}, posts = [], gone = [], dependencies = {count: 0};
    let def;
    const options = (select, list, selected) => {
        select.list = list;
        select.value = list.some(item => String(item.id) === String(selected)) ? String(selected) : '0';
    };
    const ctx = vm.createContext({
        setTimeout,
        document: {
            activeElement: null,
            getElementById: id => nodes[id],
            createElement: element,
            addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
        },
        Console: {
            tr: key => key, escapeHtml: value => String(value),
            channels: async () => { if (channels instanceof Error) throw channels; return channels; },
            roles: async () => { if (roles instanceof Error) throw roles; return roles; },
            dependencies: () => { dependencies.count++; },
            api: async (url, method, body) => {
                if (method === 'POST') { posts.push(plain(body)); return {ok: true}; }
                return url === '/leveling' ? {...CONFIG, ...config} : [];
            },
            module: d => { def = d; }, channelOptions: options, roleOptions: options, go: (...args) => gone.push(args),
        },
        DashboardUI: {changed() {}},
        DashboardExtras: {enhanceSelects() {}, refreshSelects() { dependencies.refreshed = true; }},
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    if (def) await def.load();
    const rows = () => nodes['lv-rewards'].children.map(node => ({
        node, level: node.children[0].children[0], dot: node.children[1], select: node.children[2], remove: node.children[3], note: node.children[4],
    }));
    return {R: ctx.LevelRewards, nodes, rows, posts, gone, save: () => def.save(), reset: () => def.reset(), dependencies, levels: () => rows().map(row => row.level.value),
        fire: type => (listeners[type] || []).forEach(fn => fn({}))};
}
const rewards = (...pairs) => pairs.map(([level, role_id]) => ({level, role_id}));
const later = () => new Promise(resolve => setTimeout(resolve, 0));

test('nextLevel starts at 5 and adds 5 up to the cap', async () => {
    const {R} = await page();
    assert.equal(R.nextLevel([]), 5);
    assert.equal(R.nextLevel([5, 20]), 25);
    assert.equal(R.nextLevel([997]), 999);
});

test('warningKey names the reason', async () => {
    const {R} = await page();
    assert.equal(R.warningKey('1', {1: 'above'}), 'leveling.warn.above');
    assert.equal(R.warningKey('2', {2: 'managed'}), 'leveling.warn.managed');
    assert.equal(R.warningKey('3', {}), null);
});

const form = (rows, extra = {}) => ({enabled: true, mode: 'here', channel: '0', channelLost: false, rows, ...extra});
const row = (level, role, lost = false) => ({level, role, lost});

test('problems flags duplicates on the later row only', async () => {
    const {R} = await page();
    assert.deepEqual(plain(R.problems(form([row('5', '1'), row('5', '2')]))), [{index: 1, key: 'leveling.error.duplicate_level'}]);
    assert.deepEqual(plain(R.problems(form([row('5', '1'), row('6', '1')]))), [{index: 1, key: 'leveling.error.duplicate_role'}]);
});

test('problems covers empty role, range and missing channel', async () => {
    const {R} = await page();
    assert.deepEqual(plain(R.problems(form([row('5', '0')]))), [{index: 0, key: 'leveling.error.need_role'}]);
    for (const level of ['', '0', '1000', '1.5']) {
        assert.deepEqual(plain(R.problems(form([row(level, '1')]))), [{index: 0, key: 'leveling.error.level_range'}], level);
    }
    assert.deepEqual(plain(R.problems(form([], {mode: 'channel'}))), [{index: 'channel', key: 'leveling.error.need_channel'}]);
    assert.deepEqual(plain(R.problems(form([], {mode: 'channel', channel: '77'}))), []);
});

test('problems reports deleted roles while on', async () => {
    const {R} = await page();
    assert.deepEqual(plain(R.problems(form([row('5', '0', true)]))), [{index: 0, key: 'leveling.warn.deleted'}]);
});

test('off skips lost resources', async () => {
    const {R} = await page();
    assert.deepEqual(plain(R.problems(form([row('5', '0', true)], {enabled: false, mode: 'channel', channelLost: true}))), []);
    assert.deepEqual(plain(R.problems(form([row('5', '0')], {enabled: false}))), [{index: 0, key: 'leveling.error.need_role'}]);
});

test('load renders rows in order with the role colour', async () => {
    const {rows, levels} = await page({rewards: rewards([5, '1'], [20, '2'])});
    assert.deepEqual(plain(levels()), ['5', '20']);
    assert.equal(rows()[0].select.value, '1');
    assert.equal(rows()[0].dot.style.background, '#ff0000');
    assert.equal(rows()[1].dot.style.background, '');
});

test('a role colour keeps its leading zeros', async () => {
    const {rows} = await page({rewards: rewards([5, '3'])});
    assert.equal(rows()[0].dot.style.background, '#0000ff');
});

test('rows get positional names', async () => {
    const {rows} = await page({rewards: rewards([5, '1'], [20, '2'])});
    assert.equal(rows()[0].level.name, 'lv-level-0');
    assert.equal(rows()[1].select.name, 'lv-role-1');
    rows()[0].level.value = '30';
    rows()[0].level.fire('blur');
    assert.equal(rows()[0].level.value, '20');
    assert.equal(rows()[0].level.name, 'lv-level-0');
    rows()[0].remove.fire('click');
    assert.equal(rows()[0].level.name, 'lv-level-0');
    assert.equal(rows()[0].level.value, '30');
});

test('sort runs on blur not on input', async () => {
    const {rows, levels} = await page({rewards: rewards([5, '1'], [20, '2'])});
    rows()[0].level.value = '30';
    rows()[0].level.fire('input');
    assert.deepEqual(plain(levels()), ['30', '20']);
    rows()[0].level.fire('blur');
    assert.deepEqual(plain(levels()), ['20', '30']);
});

test('sort leaves the DOM alone when the order is right', async () => {
    const {nodes, rows} = await page({rewards: rewards([5, '1'], [20, '2'])});
    rows()[0].level.fire('blur');
    assert.equal(nodes['lv-rewards'].moves, 0);
});

test('sort waits for the pointer', async () => {
    const {rows, levels, fire} = await page({rewards: rewards([5, '1'], [20, '2'])});
    rows()[0].level.value = '30';
    fire('pointerdown');
    rows()[0].level.fire('blur');
    assert.deepEqual(plain(levels()), ['30', '20']);
    fire('pointerup');
    assert.deepEqual(plain(levels()), ['30', '20']);
    await later();
    assert.deepEqual(plain(levels()), ['20', '30']);
});

test('a blur towards another row waits for the tap to land', async () => {
    const {rows, levels} = await page({rewards: rewards([5, '1'], [10, '2'], [20, '3'])});
    const first = rows()[0], target = rows()[1];
    first.level.value = '15';
    first.level.fire('blur', {relatedTarget: target.remove});
    assert.deepEqual(plain(levels()), ['15', '10', '20']);
    target.remove.fire('click');
    assert.deepEqual(plain(levels()), ['15', '20']);
    await later();
    assert.deepEqual(plain(levels()), ['15', '20']);
    assert.equal(rows()[0].select.value, '1');
});

test('a blur towards another row still sorts afterwards', async () => {
    const {rows, levels} = await page({rewards: rewards([5, '1'], [10, '2'])});
    rows()[0].level.value = '30';
    rows()[0].level.fire('blur', {relatedTarget: rows()[1].select});
    assert.deepEqual(plain(levels()), ['30', '10']);
    await later();
    assert.deepEqual(plain(levels()), ['10', '30']);
});

test('a blur leaving the list sorts at once', async () => {
    const {rows, levels, nodes} = await page({rewards: rewards([5, '1'], [10, '2'])});
    rows()[0].level.value = '30';
    rows()[0].level.fire('blur', {relatedTarget: nodes['lv-add']});
    assert.deepEqual(plain(levels()), ['10', '30']);
});

test('add row uses nextLevel and stops at twenty', async () => {
    const list = Array.from({length: 19}, (_, i) => [i + 1, String(i + 100)]);
    const {nodes, rows, levels} = await page({rewards: rewards(...list)}, {roles: list.map(([, id]) => ({id, name: id, color: 0}))});
    nodes['lv-add'].fire('click');
    assert.equal(levels()[19], '24');
    assert.equal(rows()[19].select.value, '0');
    assert.equal(rows()[19].level.focused, true);
    assert.equal(nodes['lv-add'].disabled, true);
    assert.equal(nodes['lv-limit'].hidden, false);
    rows()[0].remove.fire('click');
    assert.equal(nodes['lv-add'].disabled, false);
    assert.equal(nodes['lv-limit'].hidden, true);
});

test('add stays disabled while the master switch is off', async () => {
    const {nodes} = await page({enabled: false});
    assert.equal(nodes['lv-add'].disabled, true);
    nodes['lv-enabled'].checked = true;
    nodes['lv-enabled'].fire('change');
    assert.equal(nodes['lv-add'].disabled, false);
});

test('empty state follows the row count', async () => {
    const {nodes, rows} = await page();
    assert.equal(nodes['lv-empty'].hidden, false);
    nodes['lv-add'].fire('click');
    assert.equal(nodes['lv-empty'].hidden, true);
    rows()[0].remove.fire('click');
    assert.equal(nodes['lv-empty'].hidden, false);
});

test('picking a blocked role warns at once', async () => {
    const {rows} = await page({rewards: rewards([5, '1']), blocked_roles: {2: 'above', 3: 'managed'}});
    assert.equal(rows()[0].note.hidden, true);
    rows()[0].select.value = '2';
    rows()[0].select.fire('change');
    assert.equal(rows()[0].note.hidden, false);
    assert.equal(rows()[0].note.textContent, 'leveling.warn.above');
    assert.equal(rows()[0].note.classList.contains('lv-note--bad'), false);
    rows()[0].select.value = '3';
    rows()[0].select.fire('change');
    assert.equal(rows()[0].note.textContent, 'leveling.warn.managed');
});

test('deleted role shows the bad note until another is picked', async () => {
    const {rows} = await page({rewards: rewards([5, '404'])});
    assert.equal(rows()[0].select.value, '0');
    assert.equal(rows()[0].note.textContent, 'leveling.warn.deleted');
    assert.equal(rows()[0].note.classList.contains('lv-note--bad'), true);
    rows()[0].select.value = '1';
    rows()[0].select.fire('change');
    assert.equal(rows()[0].note.hidden, true);
});

test('discord down keeps saved roles', async () => {
    const {rows, nodes} = await page({rewards: rewards([5, '404']), notify_mode: 'channel', notify_channel: '88', can_manage_roles: null}, {roles: [], channels: []});
    assert.equal(rows()[0].select.value, '404');
    assert.equal(rows()[0].note.hidden, true);
    assert.equal(nodes['lv-no-permission'].hidden, true);
    assert.equal(nodes['lv-channel'].value, '88');
});

test('a failed channel read still renders the page', async () => {
    const {rows, nodes, save, posts} = await page({rewards: rewards([5, '1']), notify_mode: 'channel', notify_channel: '88', can_manage_roles: null}, {channels: new Error('502')});
    assert.equal(rows().length, 1);
    assert.equal(nodes['lv-channel'].value, '88');
    assert.equal(nodes['lv-channel'].list[0].name, 'leveling.unknown_channel');
    nodes['lv-enabled'].checked = false;
    nodes['lv-enabled'].fire('change');
    await save();
    assert.equal(posts[0].enabled, false);
    assert.equal(posts[0].notify_channel, '88');
});

test('a failed channel read alone is not a deleted channel', async () => {
    const {nodes, save, posts} = await page({notify_mode: 'channel', notify_channel: '88'}, {channels: new Error('502')});
    assert.equal(nodes['lv-channel'].value, '88');
    await save();
    assert.equal(posts[0].notify_channel, '88');
});

test('an empty role list is not read as every role deleted', async () => {
    const {rows} = await page({rewards: rewards([5, '1'], [9, '2'])}, {roles: []});
    assert.equal(rows()[0].select.value, '1');
    assert.equal(rows()[0].note.hidden, true);
    assert.equal(rows()[1].select.value, '2');
});

test('a failed role read is treated the same', async () => {
    const {rows} = await page({rewards: rewards([5, '1'])}, {roles: new Error('500')});
    assert.equal(rows()[0].select.value, '1');
    assert.equal(rows()[0].note.hidden, true);
});

test('no permission shows the banner', async () => {
    const {nodes} = await page({can_manage_roles: false});
    assert.equal(nodes['lv-no-permission'].hidden, false);
});

test('channel row follows the mode', async () => {
    const {nodes, save, posts} = await page({notify_mode: 'channel', notify_channel: '77'});
    assert.equal(nodes['lv-channel-row'].hidden, false);
    nodes['lv-mode'].value = 'off';
    nodes['lv-mode'].fire('change');
    assert.equal(nodes['lv-channel-row'].hidden, true);
    await save();
    assert.equal(posts[0].notify_channel, '0');
});

test('save posts sorted rows', async () => {
    const {rows, save, posts} = await page({rewards: rewards([5, '1'], [20, '2'])});
    rows()[0].level.value = '30';
    await save();
    assert.deepEqual(posts, [{enabled: true, notify_mode: 'here', notify_channel: '0', rewards: [{level: 20, role_id: '2'}, {level: 30, role_id: '1'}]}]);
});

test('save refuses problems and marks the row', async () => {
    const {rows, save, posts} = await page({rewards: rewards([5, '1'], [6, '2'])});
    rows()[1].level.value = '5';
    await assert.rejects(save(), {message: 'leveling.error.fix_first'});
    assert.equal(posts.length, 0);
    assert.equal(rows()[1].note.textContent, 'leveling.error.duplicate_level');
    assert.equal(rows()[1].note.classList.contains('lv-note--bad'), true);
    assert.equal(rows()[1].node.scrolled, true);
    rows()[1].level.value = '6';
    rows()[1].level.fire('input');
    assert.equal(rows()[1].note.hidden, true);
});

test('save reveals the settings tab when an error is hidden', async () => {
    const {nodes, save, gone} = await page({notify_mode: 'channel'});
    await assert.rejects(save());
    assert.equal(gone.length, 0);
    assert.equal(nodes['lv-channel-error'].textContent, 'leveling.error.need_channel');
    assert.equal(nodes['lv-channel-error'].hidden, false);
    nodes['panel-leveling-settings'].hidden = true;
    await assert.rejects(save());
    assert.deepEqual(plain(gone), [['leveling', 'settings']]);
});

test('save off keeps lost ids', async () => {
    const {save, posts} = await page({enabled: false, rewards: rewards([5, '404']), notify_mode: 'channel', notify_channel: '88'});
    await save();
    assert.deepEqual(posts, [{enabled: false, notify_mode: 'channel', notify_channel: '88', rewards: [{level: 5, role_id: '404'}]}]);
});

test('turning the page on again asks for the lost role', async () => {
    const {nodes, save, posts} = await page({enabled: false, rewards: rewards([5, '404'])});
    nodes['lv-enabled'].checked = true;
    nodes['lv-enabled'].fire('change');
    await assert.rejects(save(), {message: 'leveling.error.fix_first'});
    assert.equal(posts.length, 0);
});

test('reset rebuilds the saved rows after a sort', async () => {
    const {rows, levels, reset, dependencies} = await page({rewards: rewards([5, '1'], [10, '2'], [20, '3'])});
    rows()[0].level.value = '15';
    rows()[0].level.fire('blur');
    assert.deepEqual(plain(levels()), ['10', '15', '20']);
    reset();
    assert.deepEqual(plain(levels()), ['5', '10', '20']);
    assert.deepEqual(rows().map(row => row.select.value), ['1', '2', '3']);
    assert.equal(dependencies.count > 0, true);
    assert.equal(dependencies.refreshed, true);
});

test('reset drops added rows and brings back removed ones', async () => {
    const {nodes, rows, levels, reset} = await page({rewards: rewards([5, '1'], [10, '2'])});
    nodes['lv-add'].fire('click');
    rows()[0].remove.fire('click');
    assert.deepEqual(plain(levels()), ['10', '15']);
    reset();
    assert.deepEqual(plain(levels()), ['5', '10']);
    assert.deepEqual(rows().map(row => row.select.value), ['1', '2']);
    assert.equal(nodes['lv-limit'].hidden, true);
});

test('reset restores the switch, the mode and a replaced deleted role', async () => {
    const {nodes, rows, reset, save, posts} = await page({rewards: rewards([5, '404'])});
    rows()[0].select.value = '1';
    rows()[0].select.fire('change');
    nodes['lv-enabled'].checked = false;
    nodes['lv-mode'].value = 'off';
    reset();
    assert.equal(nodes['lv-enabled'].checked, true);
    assert.equal(nodes['lv-mode'].value, 'here');
    assert.equal(rows()[0].note.textContent, 'leveling.warn.deleted');
    nodes['lv-enabled'].checked = false;
    await save();
    assert.equal(posts[0].rewards[0].role_id, '404');
});

test('reset clears errors from a refused save', async () => {
    const {nodes, rows, save, reset} = await page({rewards: rewards([5, '1'])});
    nodes['lv-add'].fire('click');
    await assert.rejects(save());
    reset();
    assert.equal(rows().length, 1);
    assert.equal(rows()[0].note.hidden, true);
});

test('reset after a save returns to what was saved', async () => {
    const {rows, levels, save, reset} = await page({rewards: rewards([5, '1'])});
    rows()[0].level.value = '8';
    await save();
    rows()[0].level.value = '9';
    reset();
    assert.deepEqual(plain(levels()), ['8']);
});
