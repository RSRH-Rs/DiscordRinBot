// Homepage hero widgets: line picking, rapid-poke detection, the pausable clock and the chat beat plan.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/home-widgets.js'), 'utf8');

function load() {
    // 没有 document：脚本只导出纯函数，不接 DOM
    const window = {};
    vm.runInNewContext(source, {window, performance: {now: () => 0}, setTimeout, clearTimeout});
    return window.RinHome;
}

test('nextLine never repeats the previous line', () => {
    const {nextLine} = load();
    for (const r of [0, 0.2, 0.5, 0.99]) {
        assert.notEqual(nextLine(4, 2, () => r), 2);
    }
    assert.equal(nextLine(1, 0, () => 0.7), 0);
    assert.equal(nextLine(3, -1, () => 0.99), 2);
});

test('five pokes within four seconds make Rin cross', () => {
    const {isRapid} = load();
    assert.equal(isRapid([0, 500, 1000, 1500], 1500), false);
    assert.equal(isRapid([0, 500, 1000, 1500, 2000], 2000), true);
    assert.equal(isRapid([0, 500, 1000, 1500, 5000], 5000), false);
});

test('the clock only counts time while nothing pauses it', () => {
    const {Clock} = load();
    let now = 0;
    const timers = [];
    const clock = new Clock(() => now, (fn) => timers.push(fn));
    let done = false;
    clock.wait(1000).then(() => { done = true; });
    const step = async (ms) => { now += ms; timers.splice(0).forEach(fn => fn()); await null; };
    return (async () => {
        await step(400);
        clock.pause('offscreen');
        await step(5000);
        assert.equal(done, false);
        assert.equal(clock.paused, true);
        clock.resume('offscreen');
        await step(500);
        assert.equal(done, false);
        await step(200);
        assert.equal(done, true);
    })();
});

test('two pause reasons need two resumes', () => {
    const {Clock} = load();
    const clock = new Clock(() => 0, () => {});
    clock.pause('button');
    clock.pause('hidden');
    clock.resume('hidden');
    assert.equal(clock.paused, true);
    clock.resume('button');
    assert.equal(clock.paused, false);
});

test('beats type before Rin speaks and delete the spam before her reply', () => {
    const {beats} = load();
    const plan = beats([{rin: false}, {rin: false, deleted: true}, {rin: true}]);
    assert.deepEqual([...plan.map(b => b.kind)], [  // 复制成本地数组：vm 里的数组原型不同
        'show', 'wait', 'show', 'wait', 'delete', 'wait', 'typing', 'show', 'wait',
    ]);
    const typing = plan.find(b => b.kind === 'typing');
    assert.ok(typing.ms >= 800);
    assert.equal(plan.filter(b => b.kind === 'show').map(b => b.index).join(), '0,1,2');
    assert.equal(plan.find(b => b.kind === 'delete').index, 1);
});
