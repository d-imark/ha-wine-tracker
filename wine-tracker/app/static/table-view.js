// Table View - renders the wine grid as a sortable <table> alternative to the
// card layout. Reads card.dataset for its data (no separate data source) and
// is rebuilt from scratch every time render() runs, mirroring the previous
// inline implementation in index.html.
(function () {
  'use strict';

  var T = window.T || {};

  function render() {
    var existing = document.getElementById('wineTable');
    if (existing) existing.remove();
    var grid = document.getElementById('wineGrid');
    var cards = Array.from(grid.querySelectorAll('.card'));
    if (!cards.length) return;

    var table = document.createElement('table');
    table.id = 'wineTable';
    table.className = 'wine-table';
    table.style.gridColumn = '1 / -1';

    // Header
    var thead = '<thead><tr>'
      + '<th class="wine-table-sortable wine-table-type col-type" data-sort="type"><i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-col-name col-name" data-sort="name">' + (T.table_col_name || 'Name') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-col-year col-year" data-sort="year">' + (T.table_col_year || 'Year') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-col-region col-region" data-sort="region">' + (T.table_col_region || 'Region') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-col-grape col-grape" data-sort="grape">' + (T.table_col_grape || 'Grape') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-right wine-table-col-price col-price" data-sort="price">' + (T.table_col_price || 'Price') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '<th class="wine-table-sortable wine-table-right wine-table-col-qty col-qty" data-sort="quantity">' + (T.table_col_quantity || 'Qty') + ' <i class="mdi mdi-swap-vertical"></i></th>'
      + '</tr></thead>';

    // Body
    var tbody = '<tbody>';
    cards.forEach(function(card) {
      var d = card.dataset;
      var hidden = card.style.display === 'none' ? ' style="display:none"' : '';
      var typeCls = d.type ? d.type.toLowerCase().replace(/é/g,'e').replace(/ö/g,'oe') : '';
      var typeLabel = d.type ? (T['wine_type_' + d.type] || d.type) : '';
      var typeDot = d.type ? '<span class="type-dot type-dot-' + escapeHtml(typeCls) + '"></span>' : '';
      var priceStr = d.price ? CURRENCY + ' ' + Number(d.price).toFixed(2) : '';
      var grapesList = [];
      try { grapesList = JSON.parse(d.grapes || '[]'); } catch (e) { grapesList = []; }
      var drinkIcon = '';
      if (d.drink_until) {
        var yr = new Date().getFullYear();
        var until = parseInt(d.drink_until);
        if (until < yr) drinkIcon = ' <i class="mdi mdi-alert" style="color:#e74c3c;font-size:.75rem" title="Past drink window"></i>';
        else if (until === yr) drinkIcon = ' <i class="mdi mdi-alert" style="color:#e67e22;font-size:.75rem" title="Last year to drink"></i>';
        else drinkIcon = ' <i class="mdi mdi-check-circle" style="color:#27ae60;font-size:.75rem" title="In drink window"></i>';
      }
      tbody += '<tr class="wine-table-row' + (parseInt(d.quantity) === 0 ? ' empty' : '') + '" data-card-id="' + d.id + '" onclick="viewWineById(\'' + d.id + '\')"' + hidden + '>'
        + '<td class="wine-table-type col-type">' + typeDot + '</td>'
        + '<td class="wine-table-name col-name">' + escapeHtml(d.name) + '</td>'
        + '<td class="col-year">' + escapeHtml(d.year || '') + drinkIcon + '</td>'
        + '<td class="col-region">' + escapeHtml(d.region || '') + '</td>'
        + '<td class="col-grape">' + escapeHtml(grapeLead(grapesList) || d.grape || '') + '</td>'
        + '<td class="wine-table-right col-price">' + escapeHtml(priceStr) + '</td>'
        + '<td class="wine-table-right col-qty">' + (d.quantity || '0') + '</td>'
        + '</tr>';
    });
    tbody += '</tbody>';
    table.innerHTML = thead + tbody;

    grid.appendChild(table);

    // Sort click handlers - persist in localStorage
    var savedSortCol = localStorage.getItem('wineTableSortCol') || '';
    var savedSortAsc = localStorage.getItem('wineTableSortAsc') === 'true';
    var sortDir = {};
    if (savedSortCol) sortDir[savedSortCol] = savedSortAsc;

    function sortTableBy(key, asc) {
      sortDir[key] = asc;
      localStorage.setItem('wineTableSortCol', key);
      localStorage.setItem('wineTableSortAsc', String(asc));
      var rows = Array.from(table.querySelectorAll('tbody tr'));
      rows.sort(function(a, b) {
        var aCard = document.querySelector('.card[data-id="' + a.dataset.cardId + '"]');
        var bCard = document.querySelector('.card[data-id="' + b.dataset.cardId + '"]');
        if (!aCard || !bCard) return 0;
        var aVal = aCard.dataset[key] || '';
        var bVal = bCard.dataset[key] || '';
        if (key === 'year' || key === 'price' || key === 'quantity') {
          aVal = parseFloat(aVal) || 0;
          bVal = parseFloat(bVal) || 0;
          return asc ? aVal - bVal : bVal - aVal;
        }
        return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      });
      var tbodyEl = table.querySelector('tbody');
      rows.forEach(function(r) { tbodyEl.appendChild(r); });
      // Update sort icons
      table.querySelectorAll('.wine-table-sortable .mdi').forEach(function(icon) {
        icon.className = 'mdi mdi-swap-vertical';
        icon.style.opacity = '.5';
      });
      var activeTh = table.querySelector('[data-sort="' + key + '"] .mdi');
      if (activeTh) {
        activeTh.className = 'mdi ' + (asc ? 'mdi-chevron-up' : 'mdi-chevron-down');
        activeTh.style.opacity = '1';
      }
    }

    table.querySelectorAll('.wine-table-sortable').forEach(function(th) {
      th.addEventListener('click', function() {
        var key = th.dataset.sort;
        var asc = !(sortDir[key] || false);
        sortTableBy(key, asc);
      });
    });

    // Apply saved sort on load
    if (savedSortCol) {
      sortTableBy(savedSortCol, savedSortAsc);
    }
  }

  function remove() {
    var tbl = document.getElementById('wineTable');
    if (tbl) tbl.remove();
  }

  window.TableView = {
    render: render,
    remove: remove,
  };
})();
