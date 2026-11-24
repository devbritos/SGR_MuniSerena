const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, '../../templates/components/_ui_preferences.js.html'), 'utf8');
const themeKey = 'sgr-navbar-inverted';
const pinKey = 'sgr-sidebar-pinned';

function boot({epoch = 'session-one', width = 1400, storage = new Map(), blocked = false, full = false} = {}) {
    const classes = new Set();
    const window = {innerWidth: width, localStorage: {
        getItem(key) { if (blocked) throw new Error('Storage blocked'); return storage.get(key) ?? null; },
        setItem(key, value) { if (blocked || full) throw new Error('Cannot write storage'); storage.set(key, value); },
    }};
    const document = {getElementById: () => ({textContent: JSON.stringify(epoch)}),
        body: {classList: {toggle(name, active) { if (active) classes.add(name); else classes.delete(name); }}}};
    runInNewContext(source, {window, document});
    return {classes, preferences: window.sgrUiPreferences, storage};
}

test('new login starts white and pinned even with old red and unpinned preferences', () => {
    const storage = new Map([[themeKey, 'false'], [pinKey, 'false']]);
    const page = boot({storage});
    assert.equal(page.classes.has('navbar-inverted'), true);
    assert.equal(page.classes.has('sidebar-pinned'), true);
});

test('explicit changes survive page navigation within the same login', () => {
    const first = boot();
    first.preferences.write(pinKey, false);
    first.preferences.write(themeKey, false);
    const next = boot({storage: first.storage});
    assert.equal(next.classes.has('sidebar-pinned'), false);
    assert.equal(next.classes.has('navbar-inverted'), false);
});

test('the next login restores defaults after a user unpinned or changed theme', () => {
    const first = boot(); first.preferences.write(pinKey, false); first.preferences.write(themeKey, false);
    const nextLogin = boot({storage: first.storage, epoch: 'session-two'});
    assert.equal(nextLogin.classes.has('sidebar-pinned'), true);
    assert.equal(nextLogin.classes.has('navbar-inverted'), true);
});

test('mobile stays slideable without overwriting the desktop pin preference', () => {
    const mobile = boot({width: 390});
    assert.equal(mobile.classes.has('sidebar-pinned'), false);
    assert.equal(mobile.classes.has('navbar-inverted'), true);
    assert.equal(mobile.preferences.read(pinKey), true);
    assert.equal(boot({storage: mobile.storage}).classes.has('sidebar-pinned'), true);
});

test('blocked storage keeps controls usable with in-memory choices', () => {
    const page = boot({blocked: true});
    assert.equal(page.classes.has('sidebar-pinned'), true);
    page.preferences.write(pinKey, false);
    assert.equal(page.preferences.read(pinKey), false);
});

test('storage quota failure cannot revive stale preferences at a new login', () => {
    const page = boot({storage: new Map([[pinKey, 'false'], [themeKey, 'false']]), full: true});
    assert.equal(page.classes.has('sidebar-pinned'), true);
    assert.equal(page.classes.has('navbar-inverted'), true);
});
