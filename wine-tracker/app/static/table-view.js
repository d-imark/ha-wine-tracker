// Table View - renders the wine grid as a sortable <table> alternative to the
// card layout. Reads card.dataset for its data (no separate data source) and
// is rebuilt from scratch every time render() runs, mirroring the previous
// inline implementation in index.html.
(function () {
  'use strict';

  var T = window.T || {};

  // Catalogue order IS display order. Every key is a card.dataset key.
  var COLUMNS = [
    { key: 'year',            group: 'wine',    label: 'table_col_year',      numeric: true, minWidth: 80 },
    { key: 'region',          group: 'wine',    label: 'table_col_region',                   minWidth: 150 },
    { key: 'country',         group: 'wine',    label: 'label_country',                      minWidth: 130 },
    { key: 'grape',           group: 'wine',    label: 'table_col_grape',                    minWidth: 150 },
    { key: 'winery',          group: 'wine',    label: 'label_winery',                       minWidth: 150 },
    { key: 'drink_until',     group: 'wine',    label: 'label_drink_until',   numeric: true, minWidth: 100 },
    { key: 'age_years',       group: 'spirits', label: 'label_age',           numeric: true, minWidth: 90 },
    { key: 'cask',            group: 'spirits', label: 'label_casks',                        minWidth: 170 },
    { key: 'bottler',         group: 'spirits', label: 'label_bottler',                      minWidth: 150 },
    { key: 'price',           group: 'price',   label: 'table_col_price_own', numeric: true, minWidth: 110 },
    { key: 'ai_price',        group: 'price',   label: 'label_ai_price',      numeric: true, minWidth: 110 },
    { key: 'price_effective', group: 'price',   label: 'table_col_price_eff', numeric: true, minWidth: 110 },
    { key: 'quantity',        group: 'general', label: 'table_col_quantity',  numeric: true, minWidth: 70 },
    { key: 'rating',          group: 'general', label: 'label_rating',        numeric: true, minWidth: 90 },
    { key: 'vivino_rating',   group: 'general', label: 'vivino_rating_label', numeric: true, minWidth: 90 },
    { key: 'alcohol_pct',     group: 'general', label: 'label_alcohol_pct',   numeric: true, minWidth: 90 },
    { key: 'location',        group: 'general', label: 'label_location',                     minWidth: 130 },
    { key: 'bottle_format',   group: 'general', label: 'label_bottle_format', numeric: true, minWidth: 100 },
    { key: 'purchased_at',    group: 'general', label: 'label_purchased_at',                 minWidth: 120 }
  ];
  // The winery is a catalogue entry like any other - so the picker and the stored
  // selection need no special case - but render() pulls it out and draws it as a
  // small line above the name instead of a column. It costs no extra width that
  // way and stays pinned together with the name.
  var WINERY_KEY = 'winery';
  var GROUP_ORDER = ['wine', 'spirits', 'price', 'general'];
  var GROUP_LABEL = { wine: 'colgrp_wine', spirits: 'colgrp_spirits',
                      price: 'colgrp_price', general: 'colgrp_general' };

  var DEFAULTS = {
    cellar: ['winery', 'year', 'region', 'grape', 'price_effective', 'quantity'],
    bar:    ['winery', 'age_years', 'alcohol_pct', 'cask', 'price_effective', 'quantity']
  };

  // The alcohol column used to be the spirits-only 'abv'. Rename it in what
  // this browser stored, so a chosen column or sort does not silently vanish.
  (function migrateAbvKey() {
    try {
      ['cellar', 'bar'].forEach(function (area) {
        var key = 'wineTableCols.' + area;
        var list = JSON.parse(localStorage.getItem(key));
        if (!Array.isArray(list) || list.indexOf('abv') === -1) return;
        list = list.map(function (k) { return k === 'abv' ? 'alcohol_pct' : k; });
        localStorage.setItem(key, JSON.stringify(list));
      });
      if (localStorage.getItem('wineTableSortCol') === 'abv') {
        localStorage.setItem('wineTableSortCol', 'alcohol_pct');
      }
    } catch (e) {}
  })();


  function areaKey() {
    return (window._area === 'bar') ? 'bar' : 'cellar';
  }

  function chosenColumns() {
    var area = areaKey();
    var stored = null;
    try { stored = JSON.parse(localStorage.getItem('wineTableCols.' + area)); } catch (e) {}
    if (!Array.isArray(stored)) stored = DEFAULTS[area];
    var want = {};
    stored.forEach(function (k) { want[k] = true; });
    // Filtering the catalogue (rather than mapping the stored list) keeps
    // catalogue order and silently drops keys that no longer exist, so removing
    // a column later cannot break someone's stored selection.
    return COLUMNS.filter(function (c) { return want[c.key]; });
  }

  function setChosenColumns(keys) {
    try {
      localStorage.setItem('wineTableCols.' + areaKey(), JSON.stringify(keys));
    } catch (e) {}
    render();
  }

  function resetColumns() {
    try { localStorage.removeItem('wineTableCols.' + areaKey()); } catch (e) {}
    render();
    openPicker();   // re-render the checkboxes to match
  }

  function drinkIcon(d) {
    if (!d.drink_until) return '';
    var yr = new Date().getFullYear();
    var until = parseInt(d.drink_until, 10);
    if (until < yr) return ' <i class="mdi mdi-alert" style="color:#e74c3c;font-size:.75rem"></i>';
    if (until === yr) return ' <i class="mdi mdi-alert" style="color:#e67e22;font-size:.75rem"></i>';
    return ' <i class="mdi mdi-check-circle" style="color:#27ae60;font-size:.75rem"></i>';
  }

  // Returns an escaped HTML string so the caller never has to guess whether to escape.
  function cellHtml(d, col) {
    if (col.key === 'grape') {
      var list = [];
      try { list = JSON.parse(d.grapes || '[]'); } catch (e) {}
      return escapeHtml(grapeLead(list) || d.grape || '');
    }
    if (col.key === 'drink_until') {
      return escapeHtml(d.drink_until || '') + drinkIcon(d);
    }
    if (col.key === 'year') {
      return escapeHtml(d.year || '') + drinkIcon(d);
    }
    if (col.group === 'price') {
      var v = d[col.key];
      return v ? escapeHtml(CURRENCY + ' ' + Number(v).toFixed(2)) : '';
    }
    return escapeHtml(d[col.key] || '');
  }

  // The name column holds two values, so its header holds two sort targets - laid
  // out exactly like the cells below it (winery small on top, name beneath).
  // The <th> itself must NOT be sortable in that case, or a click on a span would
  // bubble up and sort twice.
  function nameHeaderHtml(showWinery) {
    var arrow = ' <i class="mdi mdi-swap-vertical"></i>';
    var nameLabel = escapeHtml(T.table_col_name || 'Name');
    if (!showWinery) {
      return '<th class="wine-table-sortable wine-table-col-name col-name" data-sort="name">'
        + nameLabel + arrow + '</th>';
    }
    return '<th class="wine-table-col-name col-name">'
      + '<span class="cell-clip cell-sub wine-table-sortable" data-sort="winery">'
      + escapeHtml(T.label_winery || 'Winery') + arrow + '</span>'
      + '<span class="cell-clip wine-table-sortable" data-sort="name">'
      + nameLabel + arrow + '</span></th>';
  }

  function isNumericKey(key) {
    if (key === 'type' || key === 'name') return false;
    var match = COLUMNS.filter(function (c) { return c.key === key; })[0];
    return !!(match && match.numeric);
  }

  function render() {
    remove();
    var grid = document.getElementById('wineGrid');
    var cards = Array.from(grid.querySelectorAll('.card'));
    if (!cards.length) return;

    var chosen = chosenColumns();
    // The winery is rendered as a line above the name instead of a column of its
    // own, so it is taken out of the set the cell loops walk.
    var showWinery = chosen.some(function (c) { return c.key === WINERY_KEY; });
    var cols = chosen.filter(function (c) { return c.key !== WINERY_KEY; });

    var scroll = document.createElement('div');
    scroll.className = 'wine-table-scroll';

    var table = document.createElement('table');
    table.id = 'wineTable';
    table.className = 'wine-table';

    // Header
    var thead = '<thead><tr>'
      + '<th class="wine-table-sortable wine-table-type col-type" data-sort="type"><i class="mdi mdi-swap-vertical"></i></th>'
      + nameHeaderHtml(showWinery);
    cols.forEach(function (col) {
      thead += '<th class="wine-table-sortable col-' + col.key
        + (col.numeric ? ' wine-table-right' : '')
        + '" data-sort="' + col.key
        + '" style="min-width:' + col.minWidth + 'px">'
        + escapeHtml(T[col.label] || col.key)
        + ' <i class="mdi mdi-swap-vertical"></i></th>';
    });
    thead += '</tr></thead>';

    // Body
    var tbody = '<tbody>';
    cards.forEach(function (card) {
      var d = card.dataset;
      var hidden = card.style.display === 'none' ? ' style="display:none"' : '';
      var typeCls = d.type ? d.type.toLowerCase().replace(/é/g,'e').replace(/ö/g,'oe') : '';
      var typeDot = d.type ? '<span class="type-dot type-dot-' + escapeHtml(typeCls) + '"></span>' : '';
      tbody += '<tr class="wine-table-row' + (parseInt(d.quantity) === 0 ? ' empty' : '') + '" data-card-id="' + d.id + '" onclick="viewWineById(\'' + d.id + '\')"' + hidden + '>'
        + '<td class="wine-table-type col-type">' + typeDot + '</td>'
        // The name is wrapped so its width can be capped: max-width does not
        // apply to table cells under table-layout: auto, but it does to a block
        // inside one. See .cell-clip in style.css.
        + '<td class="wine-table-name col-name">'
        + (showWinery && d.winery
            ? '<span class="cell-clip cell-sub">' + escapeHtml(d.winery) + '</span>' : '')
        + '<span class="cell-clip">' + escapeHtml(d.name) + '</span></td>';
      cols.forEach(function (col) {
        // The quantity cell opens the same -/+ popover as the card badge.
        var readonly = typeof AUTH_READONLY !== 'undefined' && AUTH_READONLY;
        var qtyClick = (col.key === 'quantity' && !readonly)
          ? ' onclick="openQtyPopover(this, event)"' : '';
        tbody += '<td class="col-' + col.key
          + (col.numeric ? ' wine-table-right' : '') + '"' + qtyClick + '>'
          + cellHtml(d, col) + '</td>';
      });
      tbody += '</tr>';
    });
    tbody += '</tbody>';
    table.innerHTML = thead + tbody;

    scroll.appendChild(table);
    // Give the name room while the table sits at its start, and hand that room
    // to the data columns once the user scrolls sideways. Toggled on a threshold
    // rather than continuously: the width change reflows the table, and doing
    // that on every scroll event would judder.
    scroll.addEventListener('scroll', function () {
      var on = scroll.scrollLeft > 4;
      if (on !== scroll.classList.contains('scrolled')) {
        scroll.classList.toggle('scrolled', on);
      }
    }, { passive: true });

    grid.appendChild(scroll);
    // Only now that a table exists is the picker meaningful. render() returns
    // early when there are no cards, leaving remove()'s hidden state in place.
    syncHeaderButton(true);

    // Sort click handlers - persist in localStorage
    var saved = savedSort();
    sortDir = {};
    if (saved.col) sortDir[saved.col] = saved.asc;

    table.querySelectorAll('.wine-table-sortable').forEach(function(th) {
      th.addEventListener('click', function() {
        var key = th.dataset.sort;
        var asc = !(sortDir[key] || false);
        if (searchActive) columnPickedDuringSearch = true;
        sortTableBy(key, asc);
      });
    });

    applyOrder();
  }

  // ── Row order ──────────────────────────────────────────────────────────
  // Rows follow the saved column sort. While a search is active they follow
  // the cards instead, which index.html ranks by relevance - until the user
  // picks a column. Clearing the search returns to the saved column.
  var sortDir = {};
  var searchActive = false;
  var columnPickedDuringSearch = false;

  function savedSort() {
    var s = { col: '', asc: false };
    try {
      s.col = localStorage.getItem('wineTableSortCol') || '';
      s.asc = localStorage.getItem('wineTableSortAsc') === 'true';
    } catch (e) {}
    return s;
  }

  function setSortIcons(table, key, asc) {
    table.querySelectorAll('.wine-table-sortable .mdi').forEach(function(icon) {
      icon.className = 'mdi mdi-swap-vertical';
      icon.style.opacity = '.5';
    });
    var activeTh = key && table.querySelector('[data-sort="' + key + '"] .mdi');
    if (activeTh) {
      activeTh.className = 'mdi ' + (asc ? 'mdi-chevron-up' : 'mdi-chevron-down');
      activeTh.style.opacity = '1';
    }
  }

  function sortTableBy(key, asc) {
    var table = document.getElementById('wineTable');
    if (!table) return;
    sortDir[key] = asc;
    try {
      localStorage.setItem('wineTableSortCol', key);
      localStorage.setItem('wineTableSortAsc', String(asc));
    } catch (e) {}
    var rows = Array.from(table.querySelectorAll('tbody tr'));
    var numeric = isNumericKey(key);
    rows.sort(function(a, b) {
      var aCard = document.querySelector('.card[data-id="' + a.dataset.cardId + '"]');
      var bCard = document.querySelector('.card[data-id="' + b.dataset.cardId + '"]');
      if (!aCard || !bCard) return 0;
      var aVal = aCard.dataset[key] || '';
      var bVal = bCard.dataset[key] || '';
      if (numeric) {
        aVal = parseFloat(aVal) || 0;
        bVal = parseFloat(bVal) || 0;
        return asc ? aVal - bVal : bVal - aVal;
      }
      return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    });
    var tbodyEl = table.querySelector('tbody');
    rows.forEach(function(r) { tbodyEl.appendChild(r); });
    setSortIcons(table, key, asc);
  }

  function followCards() {
    var table = document.getElementById('wineTable');
    if (!table) return;
    var tbodyEl = table.querySelector('tbody');
    var rows = {};
    tbodyEl.querySelectorAll('tr').forEach(function(r) { rows[r.dataset.cardId] = r; });
    document.querySelectorAll('#wineGrid .card').forEach(function(card) {
      var row = rows[card.dataset.id];
      if (row) tbodyEl.appendChild(row);
    });
    setSortIcons(table, '', false);
  }

  function applyOrder() {
    var saved = savedSort();
    if ((searchActive && !columnPickedDuringSearch) || !saved.col) followCards();
    else sortTableBy(saved.col, saved.asc);
  }

  // Called by applyFilters() in index.html after it has ranked the cards.
  function syncSearch(active) {
    if (!active && !searchActive) return;
    if (!active) columnPickedDuringSearch = false;
    searchActive = active;
    if (active && columnPickedDuringSearch) return;
    applyOrder();
  }

  function remove() {
    syncHeaderButton(false);
    var tbl = document.getElementById('wineTable');
    if (tbl) {
      var scroll = tbl.closest('.wine-table-scroll');
      if (scroll) { scroll.remove(); } else { tbl.remove(); }
    }
  }

  function openPicker() {
    var chosen = {};
    chosenColumns().forEach(function (c) { chosen[c.key] = true; });
    var html = '';
    GROUP_ORDER.forEach(function (g) {
      html += '<div class="colpick-group"><div class="colpick-group-label">'
        + escapeHtml(T[GROUP_LABEL[g]] || g) + '</div>';
      COLUMNS.filter(function (c) { return c.group === g; }).forEach(function (c) {
        html += '<label class="colpick-opt"><input type="checkbox" value="' + c.key + '"'
          + (chosen[c.key] ? ' checked' : '')
          + ' onchange="TableView.togglePicked()"> '
          + escapeHtml(T[c.label] || c.key) + '</label>';
      });
      html += '</div>';
    });
    document.getElementById('colPickerBody').innerHTML = html;
    openModal('colPickerModal');
  }

  function togglePicked() {
    var keys = [];
    document.querySelectorAll('#colPickerBody input[type=checkbox]').forEach(function (cb) {
      if (cb.checked) keys.push(cb.value);
    });
    setChosenColumns(keys);
  }

  // The picker's entry point sits in the page header next to the filter button,
  // so it has to appear and disappear with the table view itself.
  function syncHeaderButton(on) {
    var btn = document.getElementById('colPickerBtn');
    if (btn) btn.hidden = !on;
  }

  window.TableView = {
    render: render,
    remove: remove,
    openPicker: openPicker,
    togglePicked: togglePicked,
    resetColumns: resetColumns,
    syncSearch: syncSearch,
  };
})();
