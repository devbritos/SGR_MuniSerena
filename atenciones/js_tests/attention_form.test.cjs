const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, '../../templates/atenciones/_attention_form_script.js.html'), 'utf8');

function element() {
    return {
        dataset: {}, value: '', options: [], textContent: '', disabled: false,
        listeners: {}, attributes: {}, classes: new Set(['d-none']),
        classList: {
            add(name) { this.owner.classes.add(name); },
            remove(name) { this.owner.classes.delete(name); },
        },
        addEventListener(name, callback) { this.listeners[name] = callback; },
        setAttribute(name, value) { this.attributes[name] = value; },
        replaceChildren(...options) { this.options = options; this.value = ''; },
        add(option) { this.options.push(option); },
    };
}

function fixture(fetch) {
    const controls = {};
    for (const selector of ['[name="attention_type"]', '[name="sub_attention"]', '[data-subattention-status]', '[data-subattention-catalog]']) {
        controls[selector] = element();
        controls[selector].classList.owner = controls[selector];
    }
    controls['[data-subattention-catalog]'].textContent = JSON.stringify({'1': [{id: 11, name: 'Tipo uno'}], '2': [{id: 21, name: 'Apoyo familiar'}]});
    const form = {dataset: {}, querySelector: selector => controls[selector]};
    const document = {listeners: {}, forms: [], querySelectorAll() { return this.forms; }, addEventListener(name, callback) { this.listeners[name] = callback; }};
    const window = {};
    runInNewContext(source, {window, document, fetch, Option: function (text, value) { this.text = text; this.value = value; }});
    return {
        document, window, form, controls,
        type: controls['[name="attention_type"]'],
        sub: controls['[name="sub_attention"]'],
        mount() { window.sgrInitializeAttentionForms({querySelectorAll: () => [form]}); },
    };
}



test('modal inserted after page load loads the selected type and resets old options', async () => {
    const requests = [];
    const f = fixture(url => { requests.push(url); throw new Error('Unexpected network request'); });
    f.document.listeners.DOMContentLoaded();
    f.mount();
    assert.equal(f.sub.disabled, true);
    f.type.value = '2';
    await f.type.listeners.change();
    assert.deepEqual(requests, []);
    assert.equal(f.sub.options[1].text, 'Apoyo familiar');
    assert.equal(f.sub.options[1].value, 21);
    assert.equal(f.sub.disabled, false);
    f.type.value = '';
    await f.type.listeners.change();
    assert.equal(f.sub.options.length, 1);
    assert.equal(f.sub.disabled, true);
});

test('editing keeps the selected subattention and does not fetch again', () => {
    let requests = 0;
    const f = fixture(() => { requests++; });
    f.type.value = '2';
    f.sub.options = [{value: ''}, {value: '21'}];
    f.sub.value = '21';
    f.mount();
    f.mount();
    assert.equal(f.sub.value, '21');
    assert.equal(requests, 0);
});

test('switching types repeatedly updates immediately and removes the previous selection', () => {
    const f = fixture(() => { throw new Error('Unexpected network request'); });
    f.mount();
    f.type.value = '1';
    f.type.listeners.change();
    assert.equal(f.sub.options[1].value, 11);
    f.sub.value = '11';
    f.type.value = '2';
    f.type.listeners.change();
    assert.equal(f.sub.options.length, 2);
    assert.equal(f.sub.options[1].value, 21);
    assert.equal(f.sub.value, '');
    assert.equal(f.controls['[data-subattention-status]'].textContent, '');
});

test('empty catalogue explains why there are no selectable options', async () => {
    const f = fixture(() => { throw new Error('Unexpected network request'); });
    f.controls['[data-subattention-catalog]'].textContent = '{}';
    f.mount();
    f.type.value = '2';
    await f.type.listeners.change();
    assert.equal(f.sub.options.length, 1);
    assert.match(f.controls['[data-subattention-status]'].textContent, /no tiene subatenciones activas/);
});

test('page refresh initializes newly inserted forms', async () => {
    const f = fixture(() => { throw new Error('Unexpected network request'); });
    f.document.listeners.DOMContentLoaded();
    f.document.forms = [f.form];
    f.document.listeners['sgr:page-updated']();
    f.type.value = '2';
    await f.type.listeners.change();
    assert.equal(f.sub.options[1].value, 21);
});
