// Exercise draft/save lifecycle without production requests or a browser dependency.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/dashboard-ui.js'), 'utf8');

function fixture() {
    const nodes = new Map(), events = {};
    function element(id = '') {
        const classes = new Set();
        const el = {
            id, fields: [], tags: [], children: [], dataset: {}, hidden: false, inert: false,
            classList: {
                toggle(c, on) { if (on) classes.add(c); else classes.delete(c); },
                contains(c) { return classes.has(c); },
            },
            setAttribute(k, v) { this[k] = v; },
            removeAttribute(k) { delete this[k]; },
            append(child) { this.children.push(child); },
            before(child) { nodes.set(child.id, child); },
            remove() { nodes.delete(this.id); },
            querySelector(s) { return s === '.save-bar' ? this.bar : this.hint; },
            querySelectorAll(s) { return s === '.tag-chip' ? this.tags : this.fields; },
        };
        if (id) nodes.set(id, el);
        return el;
    }
    function root(id) {
        const el = element(id);
        el.hint = element(); el.bar = element();
        el.fields = [{id: 'title', type: 'text', value: 'original', matches: () => false}];
        return el;
    }
    const a = root('a'), b = root('b'), notice = element('draft-notice');
    const ctx = vm.createContext({
        document: {
            getElementById: id => nodes.get(id),
            createElement: () => element(),
            createTextNode: text => ({textContent: text}),
            addEventListener() {},
        },
        addEventListener: (name, callback) => { events[name] = callback; },
        confirm: () => false,
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
    return {ui, a, b, notice, ctx, nodes, unload};
}

test('editing/reverting fields and tags updates draft and departure warnings', () => {
    const {ui, a, notice, unload} = fixture();
    assert.equal(unload().prevented, false);
    a.fields[0].value = 'new'; ui.changed(a);
    assert.equal(ui.dirty(a), true);
    assert.equal(notice.hidden, false);
    assert.equal(unload().prevented, true);
    a.fields[0].value = 'original'; ui.changed(a);
    assert.equal(ui.dirty(a), false);
    a.tags.push({firstChild: {textContent: 'word'}}); ui.changed(a);
    assert.equal(ui.dirty(a), true);
    a.tags.pop(); ui.changed(a);
    assert.equal(notice.hidden, true);
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

test('cancel/accept navigation leaves unsaved input intact', () => {
    const {ui, a, ctx} = fixture();
    assert.equal(ui.confirmSwitch(a), true);
    a.fields[0].value = 'draft';
    assert.equal(ui.confirmSwitch(a), false);
    ctx.confirm = () => true;
    assert.equal(ui.confirmSwitch(a), true);
    assert.equal(a.fields[0].value, 'draft');
    assert.equal(ui.dirty(a), true);
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
    const {ui, a, b, notice, unload} = fixture();
    a.fields[0].value = 'announcement'; b.fields[0].value = 'another draft';
    await ui.saving(a, async () => { a.fields[0].value = ''; ui.clean(a); });
    assert.equal(ui.dirty(a), false);
    assert.equal(ui.dirty(b), true);
    assert.equal(notice.hidden, false);
    assert.equal(unload().prevented, true);
});

test('unread settings stay inert after failure; retry establishes a clean baseline', async () => {
    const {ui, a, nodes} = fixture();
    a.classList.toggle('mod-page', true);
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
