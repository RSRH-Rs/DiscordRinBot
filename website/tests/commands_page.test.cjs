// Commands page helpers: search, highlight, examples per language, Discord box slots, arrow keys and hashes.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/commands.js'), 'utf8');

const ctx = vm.createContext({document: {getElementById: () => null}});
ctx.window = ctx;
vm.runInContext(source, ctx);
const C = ctx.RinCommands;

const ban = {name: 'ban', zh: '封禁一名成员', en: 'Ban a member', params: [
    {name: 'member', required: true, en: 'The member', zh: '成员', zh_desc: '要封禁的成员'},
    {name: 'duration', required: false, en: 'How long', zh: '时长', zh_desc: '封禁多久'},
    {name: 'reason', required: false, en: 'Why', zh: '原因', zh_desc: '原因'}],
    examples: ['/ban @小明 7d 刷屏', '/ban 123 spam']};

test('search is literal and ignores a leading slash', () => {
    assert.equal(C.matches(ban, '/BAN'), true);
    assert.equal(C.matches(ban, '时长'), true);
    assert.equal(C.matches(ban, 'how long'), true);
    assert.equal(C.matches(ban, '('), false);
    assert.equal(C.matches(ban, ''), true);
});

test('highlight escapes markup', () => {
    assert.equal(C.highlight('<b>ban</b>', 'ban'), '&lt;b&gt;<mark>ban</mark>&lt;/b&gt;');
    assert.equal(C.highlight('a\\b', '\\'), 'a<mark>\\</mark>b');
    assert.equal(C.highlight('Ban a member', 'BAN'), '<mark>Ban</mark> a member');
    assert.equal(C.highlight('no match', 'xyz'), 'no match');
});

test('english hides chinese examples', () => {
    assert.deepEqual([...C.examplesFor(ban, 'en')], ['/ban 123 spam']);
    assert.equal(C.examplesFor(ban, 'zh').length, 2);
});

test('slots show required plus the focused optional', () => {
    assert.deepEqual([...C.slotsFor(ban, 0).shown.map(p => p.name)], ['member']);
    assert.equal(C.slotsFor(ban, 0).rest, 2);
    assert.deepEqual([...C.slotsFor(ban, 2).shown.map(p => p.name)], ['member', 'reason']);
    assert.equal(C.slotsFor(ban, 2).rest, 1);
    assert.deepEqual([...C.slotsFor({params: []}, 0).shown.map(p => p.name)], []);
});

test('arrow keys clamp and hashes are safe', () => {
    assert.equal(C.step(['a', 'b'], 'b', 1), 'b');
    assert.equal(C.step(['a', 'b'], 'b', -1), 'a');
    assert.equal(C.step(['a', 'b'], null, 1), 'a');
    assert.equal(C.step([], 'a', -1), null);
    assert.equal(C.idFromHash('#ban', ['ban']), 'ban');
    assert.equal(C.idFromHash('#automod-whitelist-add', ['automod-whitelist-add']), 'automod-whitelist-add');
    for (const h of ['#nope', '#%zz', '', '#', '#ban%20']) assert.equal(C.idFromHash(h, ['ban']), null);
});

test('a command needing several permissions names all of them', () => {
    const labels = {ban_members: ['封禁成员', 'Ban Members'], manage_messages: ['管理消息', 'Manage Messages']};
    assert.equal(C.permText(['ban_members', 'manage_messages'], labels, 'zh'), '封禁成员、管理消息');
    assert.equal(C.permText(['ban_members', 'manage_messages'], labels, 'en'), 'Ban Members, Manage Messages');
    assert.equal(C.permText([], labels, 'zh'), null);
});
