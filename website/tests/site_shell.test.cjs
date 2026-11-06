// Public site shell: language switch, page attribute strings and the rin:lang event.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/site.js'), 'utf8');

function page({blocked = false, lang = 'zh'} = {}) {
    const store = new Map();
    const attrs = {lang, 'data-lang': lang};
    const events = [];
    const meta = {attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }};
    const toggle = {attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener() {}};
    const i18n = {textContent: JSON.stringify({
        zh: {title: '指令大全', description: '中文描述', toggle: 'Switch to English'},
        en: {title: 'Commands', description: 'English description', toggle: '切换到中文'},
    })};
    const root = {
        getAttribute: k => attrs[k], setAttribute: (k, v) => { attrs[k] = v; },
        set lang(v) { attrs.lang = v; }, get lang() { return attrs.lang; },
    };
    const document = {
        documentElement: root, title: '',
        getElementById: id => ({'attr-i18n': i18n, 'lang-toggle': toggle, nav: null})[id] ?? null,
        querySelector: sel => sel === 'meta[name="description"]' ? meta : null,
        querySelectorAll: () => [],
        dispatchEvent: e => events.push(e),
        addEventListener() {},
    };
    const localStorage = {
        getItem: k => { if (blocked) throw new Error('blocked'); return store.get(k) ?? null; },
        setItem: (k, v) => { if (blocked) throw new Error('blocked'); store.set(k, v); },
    };
    class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } }
    const ctx = vm.createContext({document, localStorage, CustomEvent, addEventListener() {}, scrollY: 0});
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    return {ctx, attrs, store, events, meta, toggle, document};
}

test('switching to english updates the page, storage and attribute strings', () => {
    const p = page();
    p.ctx.RinSite.setLang('en');
    assert.equal(p.attrs['data-lang'], 'en');
    assert.equal(p.attrs.lang, 'en');
    assert.equal(p.store.get('rinbot_lang'), 'en');
    assert.equal(p.document.title, 'Commands');
    assert.equal(p.meta.attrs.content, 'English description');
    assert.equal(p.toggle.attrs['aria-label'], '切换到中文');
});

test('every switch announces itself once with the new language', () => {
    const p = page();
    p.ctx.RinSite.setLang('en');
    assert.equal(p.events.length, 1);
    assert.equal(p.events[0].type, 'rin:lang');
    assert.equal(p.events[0].detail.lang, 'en');
});

test('blocked storage still switches the language', () => {
    const p = page({blocked: true});
    p.ctx.RinSite.setLang('en');
    assert.equal(p.attrs['data-lang'], 'en');
    assert.equal(p.document.title, 'Commands');
});

test('the old global name keeps working', () => {
    const p = page();
    assert.equal(p.ctx.rinSetLang, p.ctx.RinSite.setLang);
});
