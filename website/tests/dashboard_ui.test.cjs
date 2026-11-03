// Exercise draft/save lifecycle without production requests or a browser dependency.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/dashboard-ui.js'), 'utf8');
const flatten = (node, prefix = '') => Object.entries(node).reduce((out, [k, v]) =>
    Object.assign(out, typeof v === 'object' ? flatten(v, prefix + k + '.') : {[prefix + k]: v}), {});
const strings = flatten(JSON.parse(fs.readFileSync(path.join(__dirname, '../i18n/zh.json'), 'utf8')));

function fixture() {
    const nodes = new Map(), events = {}, docEvents = {};
    function element(id = '') {
        const classes = new Set();
        const el = {
            id, fields: [], lists: [], children: [], dataset: {}, hidden: false, inert: false, disabled: false, textContent: '', dispatched: [],
            classList: {
                add(c) { classes.add(c); }, remove(c) { classes.delete(c); },
                toggle(c, on) { if (on === undefined) on = !classes.has(c); if (on) classes.add(c); else classes.delete(c); },
                contains(c) { return classes.has(c); },
            },
            setAttribute(k, v) { this[k] = v; },
            removeAttribute(k) { delete this[k]; },
            append(child) { this.children.push(child); },
            replaceChildren(...kids) { this.children = kids; },
            before(child) { nodes.set(child.id, child); },
            remove() { nodes.delete(this.id); },
            dispatchEvent(e) { this.dispatched.push(e.type); },
            addEventListener() {},
            querySelector(s) { return s === '.save-bar' ? this.bar : this.hint; },
            querySelectorAll(s) { return s === '[data-tags]' ? this.lists : s === '.chip' ? this.chips || [] : this.fields; },
        };
        if (id) nodes.set(id, el);
        return el;
    }
    function field(props) { return {type: 'text', value: '', matches: () => false, dispatched: [], dispatchEvent(e) { this.dispatched.push(e.type); }, ...props}; }
    function root(id) {
        const el = element(id);
        el.hint = element(); el.bar = element();
        el.fields = [field({id: 'title', value: 'original'})];
        return el;
    }
    const a = root('a'), b = root('b');
    for (const id of ['unsaved-bar', 'unsaved-save', 'unsaved-reset', 'unsaved-error', 'unsaved-text']) element(id);
    element('console-strings').textContent = JSON.stringify(strings);
    const ctx = vm.createContext({
        document: {
            getElementById: id => nodes.get(id),
            createElement: () => element(),
            createTextNode: text => ({textContent: text}),
            addEventListener: (name, callback) => { (docEvents[name] ||= []).push(callback); },
            dispatchEvent() {},
            querySelector: () => null,
        },
        addEventListener: (name, callback) => { events[name] = callback; },
        confirm: () => { throw Error('window.confirm must not be used for console pages'); },
        setTimeout: () => 1, clearTimeout() {},
        Event: class { constructor(type) { this.type = type; } },
    });
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    const ui = ctx.DashboardUI;
    ui.clean(a); ui.clean(b);
    function unload() {
        const e = {prevented: false, preventDefault() { this.prevented = true; }};
        events.beforeunload(e);
        return e;
    }
    function key(props) {
        const e = {key: 's', ctrlKey: true, metaKey: false, isComposing: false, prevented: false, preventDefault() { this.prevented = true; }, ...props};
        docEvents.keydown.forEach(fn => fn(e));
        return e;
    }
    const bar = nodes.get('unsaved-bar');
    return {ui, a, b, bar, ctx, nodes, unload, key, field};
}

test('editing/reverting fields and tags updates draft and departure warnings', () => {
    const {ui, a, bar, unload} = fixture();
    const list = {id: 'words', chips: [], querySelectorAll() { return this.chips; }};
    a.lists.push(list); ui.clean(a);
    assert.equal(unload().prevented, false);
    a.fields[0].value = 'new'; ui.changed(a);
    assert.equal(ui.dirty(a), true);
    assert.equal(bar.classList.contains('is-open'), true);
    assert.equal(unload().prevented, true);
    a.fields[0].value = 'original'; ui.changed(a);
    assert.equal(ui.dirty(a), false);
    list.chips.push({dataset: {value: 'word'}}); ui.changed(a);
    assert.equal(ui.dirty(a), true);
    list.chips.pop(); ui.changed(a);
    assert.equal(bar.classList.contains('is-open'), false);
});

test('checkboxes/files are tracked; ignored controls do not create drafts', () => {
    const {ui, a} = fixture();
    a.fields.push({id:'toggle',type:'checkbox',checked:false,matches:()=>false});
    a.fields.push({id:'image',type:'file',files:[],matches:()=>false});
    a.fields.push({id:'filter',type:'text',value:'',matches:()=>true});
    ui.clean(a);
    a.fields[3].value = 'search'; assert.equal(ui.dirty(a), false);
    a.fields[1].checked = true; assert.equal(ui.dirty(a), true);
    ui.clean(a);
    a.fields[2].files = [{name:'avatar.png',size:42,lastModified:1}];
    assert.equal(ui.dirty(a), true);
});

test('leaving with unsaved input shakes the bar instead of confirming', () => {
    const {ui, a, bar} = fixture();
    assert.equal(ui.confirmSwitch(a), true);
    a.fields[0].value = 'draft';
    assert.equal(ui.confirmSwitch(a), false);
    assert.equal(bar.classList.contains('is-shaking'), true);
    assert.equal(a.fields[0].value, 'draft');
    assert.equal(ui.dirty(a), true);
});

test('inline settings drafts still ask once before leaving', () => {
    const {ui, a, b, ctx} = fixture(); let prompts = 0;
    a.dataset.draftInline = ''; b.dataset.draftInline = '';
    a.fields[0].value = 'one'; b.fields[0].value = 'two';
    ctx.confirm = () => { prompts++; return false; };
    assert.equal(ui.confirmLeave([a, b]), false); assert.equal(prompts, 1);
});

test('reset restores saved values and fires change', () => {
    const {ui, a, field} = fixture();
    const box = field({id: 'on', type: 'checkbox', checked: true});
    a.fields.push(box); ui.clean(a);
    a.fields[0].value = 'edited'; box.checked = false; ui.changed(a);
    ui.reset(a);
    assert.equal(a.fields[0].value, 'original');
    assert.equal(box.checked, true);
    assert.ok(box.dispatched.includes('change'));
    assert.equal(ui.dirty(a), false);
});

test('reset restores unnamed checkboxes one by one', () => {
    const {ui, a, field} = fixture();
    const boxes = [true, true, true, false].map(checked => field({type: 'checkbox', checked, id: '', name: '', className: ''}));
    a.fields.push(...boxes); ui.clean(a);
    boxes[0].checked = false; ui.changed(a);
    ui.reset(a);
    assert.deepEqual(boxes.map(b => b.checked), [true, true, true, false]);
    assert.equal(ui.dirty(a), false);
});

test('bar opens when dirty and closes when changed back', () => {
    const {ui, a, bar} = fixture();
    a.fields[0].value = 'x'; ui.changed(a);
    assert.equal(bar.classList.contains('is-open'), true);
    a.fields[0].value = 'original'; ui.changed(a);
    assert.equal(bar.classList.contains('is-open'), false);
});

test('ctrl+s prevents default always and saves only when dirty', async () => {
    const {ui, a, key} = fixture();
    let saves = 0; ui.onSave(a, async () => { saves++; });
    assert.equal(key({}).prevented, true); assert.equal(saves, 0);
    a.fields[0].value = 'x'; ui.changed(a);
    assert.equal(key({isComposing: true}).prevented, true); assert.equal(saves, 0);
    key({metaKey: true, ctrlKey: false, key: 'S'});
    await new Promise(r => setImmediate(r));
    assert.equal(saves, 1);
});

test('reset and save are disabled while saving', async () => {
    const {ui, a, nodes} = fixture();
    let finish; ui.onSave(a, () => new Promise(r => { finish = r; }));
    a.fields[0].value = 'x'; ui.changed(a);
    const pending = ui.save();
    assert.equal(nodes.get('unsaved-save').disabled, true);
    assert.equal(nodes.get('unsaved-reset').disabled, true);
    finish(); await pending;
    assert.equal(ui.dirty(a), false);
    a.fields[0].value = 'again'; ui.changed(a);
    assert.equal(nodes.get('unsaved-save').disabled, false);
    assert.equal(nodes.get('unsaved-reset').disabled, false);
});

test('save failure keeps bar open with reason', async () => {
    const {ui, a, bar, nodes} = fixture();
    ui.onSave(a, async () => { throw Error('频道不存在'); });
    a.fields[0].value = 'x'; ui.changed(a);
    await ui.save();
    assert.equal(bar.classList.contains('is-open'), true);
    assert.match(nodes.get('unsaved-error').textContent, /频道不存在/);
    assert.equal(nodes.get('unsaved-error').hidden, false);
    assert.equal(a.fields[0].value, 'x');
});

test('saving prevents duplicate submissions and departure even on a clean form', async () => {
    const {ui, a, unload} = fixture();
    let finish, calls = 0;
    const saving = ui.saving(a, () => new Promise(resolve => { calls++; finish = resolve; }));
    assert.equal(a.inert, true);
    assert.equal(a['aria-busy'], 'true');
    assert.equal(unload().prevented, true);
    assert.equal(ui.confirmSwitch(a), false);
    await ui.saving(a, () => { calls++; });
    assert.equal(calls, 1);
    finish(); await saving;
    assert.equal(a.inert, false);
    assert.equal(a['aria-busy'], undefined);
    assert.equal(unload().prevented, false);
});

test('failed save restores controls, preserves input and allows retry', async () => {
    const {ui, a} = fixture();
    a.fields[0].value = 'keep me';
    await assert.rejects(ui.saving(a, async () => { throw Error('offline'); }), /offline/);
    assert.equal(a.inert, false);
    assert.equal(a.fields[0].value, 'keep me');
    assert.equal(ui.dirty(a), true);
    await ui.saving(a, async () => ui.clean(a));
    assert.equal(ui.dirty(a), false);
});

test('saving one section never clears another section; cleared fields are the new baseline', async () => {
    const {ui, a, b, bar, unload} = fixture();
    a.fields[0].value = 'announcement'; b.fields[0].value = 'another draft';
    await ui.saving(a, async () => { a.fields[0].value = ''; ui.clean(a); });
    assert.equal(ui.dirty(a), false);
    assert.equal(ui.dirty(b), true);
    assert.equal(bar.classList.contains('is-open'), true);
    assert.equal(unload().prevented, true);
});

test('unread settings stay inert after failure; retry establishes a clean baseline', async () => {
    const {ui, a, nodes} = fixture();
    a.classList.toggle('page', true);
    const retry = () => ui.loading('a', async () => { a.fields[0].value = 'loaded'; }, retry);
    await ui.loading('a', async () => { throw Error('network'); }, retry);
    assert.equal(a.inert, true);
    const feedback = nodes.get('a-load-feedback');
    assert.equal(feedback.dataset.forModule, 'a');
    assert.equal(feedback.hidden, true);
    await feedback.children[1].onclick();
    assert.equal(nodes.has('a-load-feedback'), false);
    assert.equal(a.inert, false);
    assert.equal(ui.dirty(a), false);
});

test('failed post-save refresh cannot re-enable an unread form', async () => {
    const {ui, a} = fixture();
    await ui.saving(a, () => ui.loading('a', async () => { throw Error('offline'); }, () => {}));
    assert.equal(a.inert, true);
    await ui.loading('a', async () => {}, () => {});
    assert.equal(a.inert, false);
});

function panels(ui, a, field) {
    const one = field({id: 'one', value: 'x'}), two = field({id: 'two', value: 'y'});
    a.fields.push(one, two);
    ui.clean(a);
    const panel = members => ({contains: f => members.includes(f), querySelectorAll: () => []});
    return {one, two, first: panel([one]), second: panel([two])};
}

test('changedWithin only reports fields inside the container', () => {
    const {ui, a, field} = fixture();
    const {one, first, second} = panels(ui, a, field);
    assert.equal(ui.changedWithin(a, first), false);
    one.value = 'changed';
    assert.equal(ui.changedWithin(a, first), true);
    assert.equal(ui.changedWithin(a, second), false);
});

test('reset and clean clear every tab', () => {
    const {ui, a, field} = fixture();
    const {one, two, first, second} = panels(ui, a, field);
    one.value = 'changed'; ui.changed(a);
    ui.reset(a);
    assert.equal(ui.changedWithin(a, first), false);
    two.value = 'changed'; ui.changed(a);
    ui.clean(a);
    assert.equal(ui.changedWithin(a, second), false);
});
