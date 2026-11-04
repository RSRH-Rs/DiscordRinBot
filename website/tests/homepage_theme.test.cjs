// Homepage boot script: runs the inline script from index.html against a fake document and storage.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const script = html.match(/<script>(try\{var t=localStorage\.getItem\('rin-theme'\).*?)<\/script>/)[1];

function boot(saved) {
    const metas = [{content: '#F7F7F8', media: '(prefers-color-scheme: light)'}, {content: '#17171B', media: '(prefers-color-scheme: dark)'}];
    const root = {dataset: {}};
    vm.runInContext(script, vm.createContext({
        localStorage: {getItem: key => (key === 'rin-theme' ? saved : null)},
        document: {documentElement: root, querySelectorAll: selector => (selector === 'meta[name="theme-color"]' ? metas : [])},
    }));
    return {theme: root.dataset.theme, colours: metas.map(m => m.content)};
}

test('a manual night choice paints the address bar with the night background', () => {
    assert.deepEqual(boot('dark'), {theme: 'dark', colours: ['#17171B', '#17171B']});
});

test('a manual day choice paints the address bar with the day background', () => {
    assert.deepEqual(boot('light'), {theme: 'light', colours: ['#F7F7F8', '#F7F7F8']});
});

test('with no saved choice the address bar keeps following the system', () => {
    assert.deepEqual(boot(null), {theme: undefined, colours: ['#F7F7F8', '#17171B']});
    assert.deepEqual(boot('sepia'), {theme: undefined, colours: ['#F7F7F8', '#17171B']});
});
