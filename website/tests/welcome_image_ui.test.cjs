const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../static/js/server.js'), 'utf8');
const validationOnly = source.slice(0, source.indexOf('/* ── Navigation'));
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
