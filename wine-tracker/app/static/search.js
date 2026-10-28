// Search - scores a card's data-* attributes against the query typed into the
// header search field. Pure functions without DOM access, so the same file runs
// in the browser (window.WineSearch) and under Node for the unit tests.
//
// A card matches when every word of the query is found in at least one field.
// Each word scores by the best field it hits; the card's score is the sum, so
// index.html can both filter (score > 0) and rank (higher first) with it.
(function (root) {
  'use strict';

  // weight: how much a hit in this field counts.
  // fuzzy:  whether a near miss (typo) counts. Only short, name-like fields -
  //         in free text almost every word is a near miss of something.
  var FIELDS = [
    { key: 'name',        weight: 10, fuzzy: true },
    { key: 'winery',      weight: 8,  fuzzy: true },
    { key: 'grape',       weight: 5,  fuzzy: true },
    { key: 'region',      weight: 5,  fuzzy: true },
    { key: 'country',     weight: 5,  fuzzy: true },
    { key: 'year',        weight: 4 },
    { key: 'location',    weight: 3 },
    { key: 'bottler',     weight: 3 },
    { key: 'cask',        weight: 3 },
    { key: 'notes',       weight: 1 },
    { key: 'description', weight: 1 }
  ];

  var WORD_START_BONUS = 1.5;
  var WHOLE_WORD_BONUS = 2;
  // A typo hit has to stay below any exact hit in the same field.
  var FUZZY_FACTOR = 0.3;
  var FUZZY_MIN_LEN = 5;
  // Comparing against the start of a longer word lets a typo through while the
  // user is still typing, but at five letters that matches far too much.
  var FUZZY_PREFIX_MIN_LEN = 6;
  var FUZZY_TWO_TYPOS_LEN = 8;

  function normalize(s) {
    return String(s == null ? '' : s)
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/ß/g, 'ss');
  }

  function tokenize(query) {
    return normalize(query).split(/\s+/).filter(Boolean);
  }

  // Grape names live in two places: the old free-text column and the JSON list
  // of the grape editor. Both are searched as one field.
  function grapeText(data) {
    var names = [];
    try {
      (JSON.parse(data.grapes || '[]') || []).forEach(function (g) {
        if (g && g.name) names.push(g.name);
      });
    } catch (e) { /* a broken attribute must not break the search */ }
    return [data.grape || ''].concat(names).join(' ');
  }

  function buildIndex(data) {
    return FIELDS.map(function (f) {
      var text = normalize(f.key === 'grape' ? grapeText(data) : data[f.key]);
      return {
        weight: f.weight,
        fuzzy: !!f.fuzzy,
        text: text,
        words: f.fuzzy ? text.split(/[^a-z0-9]+/).filter(Boolean) : null
      };
    });
  }

  function isWordChar(c) {
    return !!c && /[a-z0-9]/.test(c);
  }

  // Optimal string alignment distance: Levenshtein plus swapped neighbours, so
  // "gewurtz" is one typo away from "gewurzt", not two. Gives up once the
  // distance exceeds max.
  function distance(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var prev2 = null, prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev.push(j);
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      var rowMin = i;
      for (j = 1; j <= b.length; j++) {
        var cost = a[i - 1] === b[j - 1] ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          v = Math.min(v, prev2[j - 2] + 1);
        }
        cur.push(v);
        if (v < rowMin) rowMin = v;
      }
      if (rowMin > max) return max + 1;
      prev2 = prev;
      prev = cur;
    }
    return prev[b.length];
  }

  function fuzzyHit(field, token) {
    if (!field.fuzzy || token.length < FUZZY_MIN_LEN || /\d/.test(token)) return false;
    var max = token.length >= FUZZY_TWO_TYPOS_LEN ? 2 : 1;
    return field.words.some(function (w) {
      if (distance(token, w, max) <= max) return true;
      return token.length >= FUZZY_PREFIX_MIN_LEN && w.length > token.length
        && distance(token, w.slice(0, token.length), max) <= max;
    });
  }

  function fieldScore(field, token) {
    var text = field.text;
    var best = 0;
    var at = text.indexOf(token);
    while (at !== -1) {
      var s = field.weight;
      if (!isWordChar(text[at - 1])) {
        s *= isWordChar(text[at + token.length]) ? WORD_START_BONUS : WHOLE_WORD_BONUS;
      }
      if (s > best) best = s;
      at = text.indexOf(token, at + 1);
    }
    if (!best && fuzzyHit(field, token)) best = field.weight * FUZZY_FACTOR;
    return best;
  }

  // 0 means no match. An empty query matches everything with the same score,
  // which leaves the default order alone.
  function score(index, tokens) {
    if (!tokens.length) return 1;
    var total = 0;
    for (var i = 0; i < tokens.length; i++) {
      var best = 0;
      for (var k = 0; k < index.length; k++) {
        var s = fieldScore(index[k], tokens[i]);
        if (s > best) best = s;
      }
      if (!best) return 0;
      total += best;
    }
    return total;
  }

  var api = { normalize: normalize, tokenize: tokenize, buildIndex: buildIndex, score: score };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.WineSearch = api;
})(this);
