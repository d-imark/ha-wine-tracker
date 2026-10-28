// Unit tests for static/search.js. Run by tests/test_search_js.py, or
// directly with `node --test tests/js/search.test.js`.
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const S = require(path.join(__dirname, '..', '..', 'app', 'static', 'search.js'));

function score(data, query) {
  return S.score(S.buildIndex(data), S.tokenize(query));
}

test('empty query matches everything', () => {
  assert.ok(score({ name: 'Barolo' }, '') > 0);
  assert.ok(score({ name: 'Barolo' }, '   ') > 0);
});

test('every word has to match somewhere', () => {
  const wine = { name: 'Pinot Noir', year: '2019', region: 'Burgund' };
  assert.ok(score(wine, 'pinot 2019') > 0);
  assert.ok(score(wine, '2019 burgund') > 0);
  assert.strictEqual(score(wine, 'pinot 2018'), 0);
});

test('accents and case are ignored both ways', () => {
  assert.ok(score({ region: 'Côtes du Rhône' }, 'cotes rhone') > 0);
  assert.ok(score({ grape: 'Grüner Veltliner' }, 'gruner') > 0);
  assert.ok(score({ name: 'Chateau Margaux' }, 'Château') > 0);
});

test('searches winery, country, location, grape list and spirit fields', () => {
  assert.ok(score({ name: 'X', winery: 'Gaja' }, 'gaja') > 0);
  assert.ok(score({ name: 'X', country: 'Italien' }, 'italien') > 0);
  assert.ok(score({ name: 'X', location: 'Regal B' }, 'regal') > 0);
  assert.ok(score({ name: 'X', grapes: JSON.stringify([{ name: 'Nebbiolo', pct: 100 }]) }, 'nebbiolo') > 0);
  assert.ok(score({ name: 'X', bottler: 'Signatory' }, 'signatory') > 0);
  assert.ok(score({ name: 'X', cask: 'Sherry Butt' }, 'sherry') > 0);
  assert.ok(score({ name: 'X', notes: 'Geburtstag' }, 'geburtstag') > 0);
  assert.ok(score({ name: 'X', description: 'Kirsche' }, 'kirsche') > 0);
});

test('a broken grapes attribute does not break the search', () => {
  assert.ok(score({ name: 'Barolo', grapes: '{not json' }, 'barolo') > 0);
});

test('a hit in the name outranks a hit in the notes', () => {
  const inName = score({ name: 'Merlot Reserve' }, 'merlot');
  const inNotes = score({ name: 'Hauswein', notes: 'wie ein Merlot' }, 'merlot');
  assert.ok(inName > inNotes);
});

test('a whole-word hit outranks a hit inside a word', () => {
  const whole = score({ name: 'Rosso' }, 'rosso');
  const inside = score({ name: 'Monterossol' }, 'rosso');
  assert.ok(whole > inside);
});

test('a word-start hit outranks a hit inside a word', () => {
  const start = score({ name: 'Sangiovese' }, 'sangio');
  const inside = score({ name: 'Brunello-xsangio' }, 'angio');
  assert.ok(start > inside);
});

test('more matching words rank higher', () => {
  const both = score({ name: 'Barolo', region: 'Piemont' }, 'barolo piemont');
  const nameOnly = score({ name: 'Barolo' }, 'barolo');
  assert.ok(both > nameOnly);
});

test('a single typo in a long word still finds the wine', () => {
  assert.ok(score({ grape: 'Chardonnay' }, 'chardonay') > 0);
  assert.ok(score({ name: 'Barolo' }, 'barollo') > 0);
  assert.ok(score({ grape: 'Sauvignon Blanc' }, 'sauvignion') > 0);
});

test('a typo while still typing is tolerated', () => {
  assert.ok(score({ grape: 'Gewürztraminer' }, 'gewurtz') > 0);
});

test('two typos are tolerated only in long words', () => {
  assert.ok(score({ grape: 'Gewürztraminer' }, 'gewurstraminr') > 0);
  assert.strictEqual(score({ name: 'Merlot' }, 'murlat'), 0);
});

test('short words and numbers are never fuzzy', () => {
  assert.strictEqual(score({ name: 'Rosé' }, 'rot'), 0);
  assert.strictEqual(score({ year: '2018' }, '2019'), 0);
});

test('free text is not searched fuzzy', () => {
  assert.strictEqual(score({ name: 'X', notes: 'Chardonnay-artig' }, 'chardonay'), 0);
});

test('an exact hit outranks a fuzzy hit', () => {
  const exact = score({ name: 'Barolo' }, 'barolo');
  const fuzzy = score({ name: 'Barollo' }, 'barolo');
  assert.ok(exact > fuzzy);
});

test('ß is matched by ss', () => {
  assert.ok(score({ name: 'Weißburgunder' }, 'weissburgunder') > 0);
});
