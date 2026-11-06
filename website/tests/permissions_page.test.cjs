// Invite permissions page helpers: permission bits, the invite link and the list of what stops working.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/permissions.js'), 'utf8');

const ctx = vm.createContext({document: {getElementById: () => null}, URL});
ctx.window = ctx;
vm.runInContext(source, ctx);
const P = ctx.RinPermissions;

const all = [1, 2, 4, 7, 10, 11, 13, 14, 15, 16, 20, 21, 25, 28, 38, 40];
const base = 'https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands';

test('bits match the live invite', () => {
    assert.equal(P.bitsFor(all), 1374694796438n);
    assert.equal(P.bitsFor(all.filter(b => b !== 1 && b !== 7)), 1374694796438n - 2n - 128n);
    assert.equal(P.bitsFor([]), 0n);
});

test('invite link only changes the permissions value', () => {
    assert.equal(P.inviteHref(base, 1374694796438n), base);
    assert.match(P.inviteHref(base, 6n), /permissions=6&integration_type=0/);
    assert.match(P.inviteHref(base, 6n), /scope=bot\+applications\.commands$/);
});

test('missing keeps list order', () => {
    const perms = [{bit: 10}, {bit: 1}, {bit: 7}];
    assert.deepEqual([...P.missing(perms, new Set([7, 10])).map(p => p.bit)], [10, 7]);
    assert.equal(P.missing(perms, new Set()).length, 0);
});
