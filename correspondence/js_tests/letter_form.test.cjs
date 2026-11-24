const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, '../../templates/correspondence/_letter_form_script.js.html'), 'utf8');

function fixture() {
    const delegation = {value: '1', listeners: {}, addEventListener(name, listener) { this.listeners[name] = listener; }};
    const responsible = {
        value: '11', options: [{value: ''}, {value: '11', text: 'Ana'}],
        replaceChildren(...options) { this.options = options; this.value = ''; },
        add(option) { this.options.push(option); },
    };
    const status = {textContent: ''};
    const catalog = {textContent: JSON.stringify({'1': [{id: 11, name: 'Ana'}], '2': [{id: 22, name: 'Luis'}]})};
    const elements = {'[name="delegation"]': delegation, '[name="responsible"]': responsible,
                      '[data-responsible-status]': status, '[data-responsible-catalog]': catalog};
    const form = {dataset: {}, listeners: {}, querySelector: selector => elements[selector],
                  addEventListener(name, listener) { this.listeners[name] = listener; }};
    const document = {forms: [], listeners: {}, querySelectorAll() { return this.forms; },
                      addEventListener(name, listener) { this.listeners[name] = listener; }};
    const window = {setTimeout: callback => callback()};
    runInNewContext(source, {document, window, Option: function (text, value) { this.text = text; this.value = String(value); },
        fetch() { throw new Error('Responsible selection must not make network requests'); }});
    return {delegation, responsible, status, catalog, document, form,
        mount() { window.sgrInitializeLetterForms({querySelectorAll: () => [form]}); }};
}

test('modal keeps existing responsible and updates immediately when delegation changes', () => {
    const f = fixture();
    f.document.listeners.DOMContentLoaded();
    f.mount();
    assert.equal(f.responsible.value, '11');
    f.delegation.value = '2';
    f.delegation.listeners.change();
    assert.equal(f.responsible.value, '');
    assert.equal(f.responsible.options.length, 2);
    assert.equal(f.responsible.options[1].value, '22');
    assert.equal(f.responsible.options[1].text, 'Luis');
    assert.equal(f.status.textContent, '');
});

test('clearing delegation removes choices from the previous delegation', () => {
    const f = fixture(); f.mount();
    f.delegation.value = ''; f.delegation.listeners.change();
    assert.equal(f.responsible.options.length, 1);
    assert.match(f.responsible.options[0].text, /primero una delegación/);
});

test('delegation without responsible people explains how to continue', () => {
    const f = fixture(); f.mount();
    f.delegation.value = '3'; f.delegation.listeners.change();
    assert.equal(f.responsible.options.length, 1);
    assert.match(f.status.textContent, /No hay funcionarios autorizados/);
});

test('new forms inserted during page refresh receive the same behavior', () => {
    const f = fixture();
    f.document.listeners.DOMContentLoaded();
    f.document.forms = [f.form];
    f.document.listeners['sgr:page-updated']();
    f.delegation.value = '2'; f.delegation.listeners.change();
    assert.equal(f.responsible.options[1].value, '22');
});
