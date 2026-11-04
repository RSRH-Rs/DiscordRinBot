const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/welcome.js'), 'utf8');
const validationOnly = source.slice(0, source.indexOf('/* ── end validation ── */'));
const context = vm.createContext({
    window:{},
    URL:{createObjectURL(){return 'blob:test';}, revokeObjectURL(){}},
    Image:class {},
});
vm.runInContext(validationOnly, context);

test('welcome image picker enforces supported types and five megabytes', () => {
    assert.equal(context.welcomeImageFileError(null), '请先选择一张图片');
    assert.match(context.welcomeImageFileError({type:'text/plain', size:10}), /仅支持/);
    assert.match(
        context.welcomeImageFileError({type:'image/png', size:5 * 1024 * 1024 + 1}),
        /5 MB/
    );
    for (const type of ['image/png','image/jpeg','image/gif','image/webp']) {
        assert.equal(context.welcomeImageFileError({type, size:5 * 1024 * 1024}), '');
    }
});

test('picking an image names the file in the status line', async () => {
    const flatten = (tree, prefix = '') => Object.entries(tree).reduce((out, [k, v]) =>
        Object.assign(out, typeof v === 'object' ? flatten(v, prefix + k + '.') : {[prefix + k]: v}), {});
    const strings = flatten(JSON.parse(fs.readFileSync(path.join(__dirname, '../i18n/zh.json'), 'utf8')));
    const nodes = {};
    const node = id => (nodes[id] ||= {id, hidden: false, value: '', textContent: '', listeners: {}, src: '',
        addEventListener(type, fn) { this.listeners[type] = fn; }, removeAttribute() {}, setAttribute() {}, querySelectorAll: () => []});
    let ready;
    const ctx = vm.createContext({
        window: {}, GID: '1',
        URL: {createObjectURL() { return 'blob:cat'; }, revokeObjectURL() {}},
        Image: class { set src(value) { this.naturalWidth = this.naturalHeight = 100; setTimeout(() => this.onload()); } },
        document: {getElementById: node, addEventListener(type, fn) { if (type === 'DOMContentLoaded') ready = fn; }},
        Console: {tr: (k, v = {}) => Object.entries(v).reduce((s, [a, b]) => s.replaceAll('{' + a + '}', b), strings[k] ?? k),
            module() {}, toast() {}, api: async () => ({})},
        DashboardExtras: {matches: () => true},
    });
    vm.runInContext(source, ctx);
    node('pg-welcome');
    ready();
    await nodes['w-welcome-file'].listeners.change({target: {files: [{name: 'cat.png', type: 'image/png', size: 1000}], value: 'cat.png'}});
    assert.equal(nodes['w-welcome-image-state'].textContent, '已选择 cat.png，点「上传图片」才会生效');
});
