// Theme system: named themes × light/dark mode
var THEME_MODES = ['system', 'dark', 'light'];

// Theme definitions with preview colors [bg-dark, accent, gold]
var THEMES = [
  { key: 'homeassistant', colors: ['#111111', '#009ac7', '#ff9800'] },
  { key: 'classic',   colors: ['#1a0a0f', '#c0392b', '#d4a843'] },
  { key: 'vineyard',  colors: ['#0f1a12', '#4caf50', '#c9a84c'] },
  { key: 'champagne', colors: ['#1a1508', '#c9a84c', '#d4a843'] },
  { key: 'slate',     colors: ['#12151c', '#5c7cfa', '#c9a84c'] },
  { key: 'burgundy',  colors: ['#180a1c', '#ab47bc', '#d4a843'] }
];

function getSystemPreference() {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function applyTheme(mode) {
  var effective = mode === 'system' ? getSystemPreference() : mode;
  document.documentElement.classList.toggle('light', effective === 'light');
  if (typeof window._onThemeApplied === 'function') window._onThemeApplied();
}

function applyThemeName(name) {
  if (!name || name === 'classic') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', name);
  }
}

function setThemeName(name) {
  localStorage.setItem('wine-theme-name', name);
  applyThemeName(name);
  updateThemeDropdown();
}

function setThemeMode(mode) {
  localStorage.setItem('wine-theme', mode);
  applyTheme(mode);
  updateThemeSegmented();
}

function cycleTheme() {
  var current = localStorage.getItem('wine-theme') || 'system';
  var idx = THEME_MODES.indexOf(current);
  var next = THEME_MODES[(idx + 1) % THEME_MODES.length];
  setThemeMode(next);
}

function updateThemeSegmented() {
  var current = localStorage.getItem('wine-theme') || 'system';
  document.querySelectorAll('input[name="themeMode"]').forEach(function(r) {
    r.checked = (r.value === current);
  });
}

function updateThemeDropdown() {
  var current = localStorage.getItem('wine-theme-name') || 'homeassistant';
  // Update button display
  var btn = document.querySelector('.theme-dropdown-btn');
  if (btn) {
    var t = THEMES.find(function(t) { return t.key === current; }) || THEMES[0];
    var label = btn.querySelector('.dd-label');
    var dots = btn.querySelector('.theme-dots');
    if (label) label.textContent = getThemeLabel(current);
    if (dots) dots.innerHTML = t.colors.map(function(c) {
      return '<span class="theme-dot" style="background:' + c + '"></span>';
    }).join('');
  }
  // Update list items
  document.querySelectorAll('.theme-dropdown-item').forEach(function(item) {
    var isActive = item.dataset.theme === current;
    item.classList.toggle('active', isActive);
    var check = item.querySelector('.dd-check');
    if (check) check.style.display = isActive ? '' : 'none';
  });
}

function getThemeLabel(key) {
  // Try to get translated label from DOM data attribute, fallback to capitalized key
  var el = document.querySelector('[data-theme-labels]');
  if (el) {
    try {
      var labels = JSON.parse(el.dataset.themeLabels);
      if (labels[key]) return labels[key];
    } catch(e) {}
  }
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function toggleThemeDropdown(e) {
  if (e) e.stopPropagation();
  var dd = document.querySelector('.theme-dropdown');
  if (!dd) return;
  dd.classList.toggle('open');
  if (dd.classList.contains('open')) {
    var btn = dd.querySelector('.theme-dropdown-btn');
    var list = dd.querySelector('.theme-dropdown-list');
    if (btn && list) {
      var r = btn.getBoundingClientRect();
      list.style.top = (r.bottom + 4) + 'px';
      list.style.left = r.left + 'px';
      list.style.width = r.width + 'px';
    }
  }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
  var dd = document.querySelector('.theme-dropdown');
  if (dd && !dd.contains(e.target)) dd.classList.remove('open');
});

// ── Chat recording toggle ────────────────────────────────────────────────────
function toggleChatRecording(enabled) {
  localStorage.setItem('chatRecording', enabled ? '1' : '0');
  if (typeof _updateChatHistoryButtons === 'function') _updateChatHistoryButtons();
}

function initChatRecordingToggle() {
  var el = document.getElementById('chatRecordingToggle');
  if (el) el.checked = localStorage.getItem('chatRecording') !== '0'; // default ON
  var el2 = document.getElementById('chatEditWinesToggle');
  if (el2) el2.checked = localStorage.getItem('chatEditWines') === '1'; // default OFF
}

function toggleChatEditWines(enabled) {
  localStorage.setItem('chatEditWines', enabled ? '1' : '0');
}

// ── Settings modal tabs ──────────────────────────────────────────────────────

function switchSettingsTab(name) {
  document.querySelectorAll('#settingsModal .settings-tab').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  document.querySelectorAll('#settingsModal .settings-section[data-settings-tab]').forEach(function(sec) {
    sec.style.display = sec.dataset.settingsTab === name ? '' : 'none';
  });
  try { localStorage.setItem('wineSettingsTab', name); } catch (e) {}
  if (name === 'ai') _aiEnsureLoaded();
}

// ── AI settings (settings modal) ─────────────────────────────────────────────
// Reads and writes /api/ai-settings. API keys are write-only: the server only
// says whether one is stored, so an empty key field keeps the stored key.

var _aiSettings = null;
var _aiModelCache = {};
var _modelDdTarget = null;
var _aiLoadStarted = false;

// Loaded only once the AI tab is actually shown: the model list is fetched
// from the provider, and that must not happen on every page view.
function _aiEnsureLoaded() {
  if (_aiLoadStarted || !document.getElementById('aiProviderSelect')) return;
  var modal = document.getElementById('settingsModal');
  if (!modal || !modal.classList.contains('open')) return;
  _aiLoadStarted = true;
  aiSettingsLoad();
}

// Pages open the modal with their own openModal(); watch for it instead of
// patching five of them.
document.addEventListener('DOMContentLoaded', function() {
  var modal = document.getElementById('settingsModal');
  if (!modal || !window.MutationObserver) return;
  new MutationObserver(function() {
    if (!modal.classList.contains('open')) { closeModelDd(); return; }
    var active = modal.querySelector('.settings-tab.active');
    if (active && active.dataset.tab === 'ai') _aiEnsureLoaded();
  }).observe(modal, { attributes: true, attributeFilter: ['class'] });
});

function _aiStatus(msg, kind) {
  var el = document.getElementById('aiSettingsStatus');
  if (!el) return;
  el.textContent = msg || '';
  el.className = 'ai-status' + (kind ? ' ' + kind : '');
}

function _aiBusy(busy) {
  ['aiTestBtn', 'aiSaveBtn'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.disabled = busy;
  });
}

function aiSettingsLoad() {
  fetch(_ingressPrefix() + '/api/ai-settings')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) return;
      _aiSettings = data;
      document.getElementById('aiProviderSelect').value = data.settings.ai_provider || 'none';
      document.getElementById('aiChatModelInput').value = data.settings.chat_model || '';
      document.getElementById('aiHostInput').value = data.settings.ollama_host || '';
      document.getElementById('aiWebSearchToggle').checked = data.settings.openai_web_search !== false;
      document.getElementById('aiOverridesHint').style.display = data.overrides.length ? '' : 'none';
      aiSettingsProviderChanged();
    })
    .catch(function() {});
}

function aiSettingsProviderChanged() {
  var p = document.getElementById('aiProviderSelect').value;
  document.getElementById('aiProviderFields').style.display = p === 'none' ? 'none' : '';
  document.getElementById('aiTestBtn').style.display = p === 'none' ? 'none' : '';
  if (p === 'none' || !_aiSettings) return;
  document.getElementById('aiKeyRow').style.display = p === 'ollama' ? 'none' : '';
  document.getElementById('aiHostRow').style.display = p === 'ollama' ? '' : 'none';
  document.getElementById('aiWebSearchRow').style.display = p === 'openai' ? '' : 'none';
  document.getElementById('aiModelInput').value = _aiSettings.settings[p + '_model'] || '';
  // The chat model names a model of one provider: on another provider it
  // would break the sommelier, so it only comes back with the stored provider.
  document.getElementById('aiChatModelInput').value =
    p === _aiSettings.settings.ai_provider ? (_aiSettings.settings.chat_model || '') : '';
  var keyInput = document.getElementById('aiApiKeyInput');
  keyInput.value = '';
  keyInput.placeholder = _aiSettings.keys[p + '_api_key'] ? T.ai_key_stored : T.ai_key_placeholder;
  _aiLoadModelList(p);
}

function _aiSetModelButtons(hasModels) {
  ['aiModelDdBtn', 'aiChatModelDdBtn'].forEach(function(id) {
    var b = document.getElementById(id);
    if (b) b.style.display = hasModels ? '' : 'none';
  });
  // The fields stay free text: the list is capped and filtered, so a model
  // missing from it must still be typeable.
}

function _aiLoadModelList(provider) {
  closeModelDd();
  if (_aiModelCache[provider]) {
    _aiSetModelButtons(_aiModelCache[provider].length > 0);
    return;
  }
  _aiSetModelButtons(false);
  fetch(_ingressPrefix() + '/api/ai-settings/models?provider=' + encodeURIComponent(provider))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok || !data.models) return;
      _aiModelCache[provider] = data.models;
      if (document.getElementById('aiProviderSelect').value === provider) {
        _aiSetModelButtons(data.models.length > 0);
      }
    })
    .catch(function() {});
}

function toggleModelDd(inputId, ev) {
  if (ev) ev.stopPropagation();
  var dd = document.getElementById('aiModelDd');
  if (!dd) return;
  if (_modelDdTarget === inputId && dd.style.display === 'block') { closeModelDd(); return; }
  var provider = document.getElementById('aiProviderSelect').value;
  var models = _aiModelCache[provider] || [];
  if (!models.length) { closeModelDd(); return; }
  _modelDdTarget = inputId;
  var input = document.getElementById(inputId);
  var current = input.value.trim();
  var html = '';
  if (models.length > 20) {
    html += '<input type="text" class="model-dd-filter" oninput="filterModelDd(this)" onclick="event.stopPropagation()">';
  }
  // The chat model may be empty (= same model as for the labels).
  if (inputId === 'aiChatModelInput') {
    html += '<div class="model-dd-item' + (current === '' ? ' active' : '') + '" data-model="" tabindex="0" role="button">&mdash;</div>';
  }
  html += models.map(function(m) {
    var esc = m.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    return '<div class="model-dd-item' + (m === current ? ' active' : '') + '" data-model="' + esc + '" tabindex="0" role="button">' + esc + '</div>';
  }).join('');
  dd.innerHTML = html;
  var r = input.getBoundingClientRect();
  dd.style.display = 'block';
  dd.style.left = r.left + 'px';
  dd.style.width = r.width + 'px';
  var ddHeight = Math.min(260, dd.scrollHeight);
  var top = r.bottom + 4;
  if (top + ddHeight > window.innerHeight - 8) top = Math.max(8, r.top - ddHeight - 4);
  dd.style.top = top + 'px';
  var filter = dd.querySelector('.model-dd-filter');
  if (filter) filter.focus();
  var active = dd.querySelector('.model-dd-item.active');
  if (active) active.scrollIntoView({ block: 'center' });
}

function filterModelDd(filterInput) {
  var q = filterInput.value.trim().toLowerCase();
  document.querySelectorAll('#aiModelDd .model-dd-item').forEach(function(item) {
    item.style.display = !q || item.dataset.model.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
  });
}

function closeModelDd() {
  var dd = document.getElementById('aiModelDd');
  if (dd) dd.style.display = 'none';
  _modelDdTarget = null;
}

document.addEventListener('click', function(e) {
  var dd = document.getElementById('aiModelDd');
  if (!dd || dd.style.display !== 'block') return;
  var item = e.target.closest('.model-dd-item');
  if (item && dd.contains(item)) {
    var input = document.getElementById(_modelDdTarget);
    if (input) input.value = item.dataset.model;
    closeModelDd();
    return;
  }
  if (!dd.contains(e.target)) closeModelDd();
});

// The list is fixed-positioned: any scroll would leave it floating elsewhere.
window.addEventListener('scroll', function(e) {
  var dd = document.getElementById('aiModelDd');
  if (!dd || dd.style.display !== 'block') return;
  if (e.target === dd) return;
  closeModelDd();
}, true);

function _aiPost(path, payload) {
  return fetch(_ingressPrefix() + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: payload === undefined ? undefined : JSON.stringify(payload)
  }).then(function(r) { return r.json(); });
}

function _aiFormPayload() {
  var p = document.getElementById('aiProviderSelect').value;
  var payload = {
    ai_provider: p,
    chat_model: document.getElementById('aiChatModelInput').value
  };
  if (p !== 'none') {
    payload[p + '_model'] = document.getElementById('aiModelInput').value;
    if (p === 'ollama') payload.ollama_host = document.getElementById('aiHostInput').value;
    if (p === 'openai') payload.openai_web_search = document.getElementById('aiWebSearchToggle').checked;
    var key = document.getElementById('aiApiKeyInput').value.trim();
    if (key) payload[p + '_api_key'] = key;
  }
  return payload;
}

// Saves, then reloads the page - which AI buttons a page shows depends on it.
function aiSettingsSave() {
  var payload = _aiFormPayload();
  _aiStatus('…');
  _aiBusy(true);
  _aiPost('/api/ai-settings', payload)
    .then(function(data) {
      if (!data.ok) { _aiStatus(T.ai_save_failed, 'error'); _aiBusy(false); return; }
      _aiStatus(T.ai_saved, 'ok');
      location.reload();
    })
    .catch(function() { _aiStatus(T.ai_save_failed, 'error'); _aiBusy(false); });
}

// Tests what is in the form WITHOUT saving it: a failed try with another
// provider must not replace a working setup.
function aiSettingsTest() {
  _aiStatus(T.ai_testing);
  _aiBusy(true);
  _aiPost('/api/ai-settings/test', _aiFormPayload())
    .then(function(data) {
      _aiStatus(data.ok ? T.ai_test_ok : T.ai_test_failed + ': ' + (data.error || ''),
                data.ok ? 'ok' : 'error');
      _aiBusy(false);
    })
    .catch(function() { _aiStatus(T.ai_test_failed, 'error'); _aiBusy(false); });
}

// Drops every app override so the add-on configuration applies again. Asks the
// server which ones exist rather than trusting the list from page load.
function aiSettingsResetOverrides() {
  _aiBusy(true);
  fetch(_ingressPrefix() + '/api/ai-settings')
    .then(function(r) { return r.json(); })
    .then(function(current) {
      var payload = {};
      (current.overrides || []).forEach(function(k) { payload[k] = null; });
      return _aiPost('/api/ai-settings', payload);
    })
    .then(function(data) {
      if (!data.ok) { _aiStatus(T.ai_save_failed, 'error'); _aiBusy(false); return; }
      location.reload();
    })
    .catch(function() { _aiStatus(T.ai_save_failed, 'error'); _aiBusy(false); });
}

// Reopens on the last tab - unless that tab is gone (the sommelier tab only
// exists while AI is configured), then on the first one.
function initSettingsTabs() {
  var tabs = document.querySelectorAll('#settingsModal .settings-tab');
  if (!tabs.length) return;
  var saved = null;
  try { saved = localStorage.getItem('wineSettingsTab'); } catch (e) {}
  var valid = Array.prototype.some.call(tabs, function(b) { return b.dataset.tab === saved; });
  switchSettingsTab(valid ? saved : tabs[0].dataset.tab);
}

function _ingressPrefix() {
  // The settings modal renders the ingress path onto the export button; not
  // every page that includes the modal sets window.INGRESS.
  var btn = document.getElementById('exportBackupBtn');
  if (btn) return btn.getAttribute('data-base') || '';
  return window.INGRESS || '';
}

// ── Data: Export ──────────────────────────────────────────────────────────────
// A plain link makes the HA companion app's webview render the ZIP as text.
// Fetch it instead: hand it to the share sheet inside the app, download it as a
// blob elsewhere, and fall back to plain navigation if the fetch fails.
function exportBackup() {
  var btn = document.getElementById('exportBackupBtn');
  var url = _ingressPrefix() + '/export';
  if (btn) btn.disabled = true;
  fetch(url)
    .then(function(r) {
      if (!r.ok) throw new Error('export failed');
      var dispo = r.headers.get('Content-Disposition') || '';
      var match = dispo.match(/filename="?([^";]+)"?/);
      var name = match ? match[1] : 'wine-tracker-export.zip';
      return r.blob().then(function(blob) { return { blob: blob, name: name }; });
    })
    .then(function(res) {
      var embedded = document.body.classList.contains('embedded');
      if (embedded && navigator.canShare) {
        var file = new File([res.blob], res.name, { type: 'application/zip' });
        if (navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file] }).catch(function() {});
        }
      }
      var objUrl = URL.createObjectURL(res.blob);
      var a = document.createElement('a');
      a.href = objUrl;
      a.download = res.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function() { URL.revokeObjectURL(objUrl); }, 10000);
    })
    .catch(function() { window.location.href = url; })
    .finally(function() { if (btn) btn.disabled = false; });
}

// ── Data: Import ──────────────────────────────────────────────────────────────
// Remember the token returned by /import/preview so confirmImport() can commit.
var _importToken = null;

function _showImportError(msg) {
  var el = document.getElementById('importError');
  if (!el) { alert(msg); return; }
  el.textContent = msg;
  el.style.display = 'block';
}

function _clearImportError() {
  var el = document.getElementById('importError');
  if (el) { el.textContent = ''; el.style.display = 'none'; }
}

function handleImportFile(input) {
  var file = input && input.files && input.files[0];
  if (!file) return;

  var fd = new FormData();
  fd.append('file', file);

  // Close settings, prepare preview modal.
  if (typeof closeModal === 'function') closeModal('settingsModal');
  _clearImportError();
  openModal('importPreviewModal');

  fetch(_ingressPrefix() + '/import/preview', {
      method: 'POST',
      body: fd,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, body: j }; }); })
    .then(function(res) {
      if (!res.ok || !res.body.ok) {
        _showImportError(res.body.error || 'Import fehlgeschlagen');
        return;
      }
      _importToken = res.body.token;
      _renderImportPreview(res.body);
    })
    .catch(function(err) {
      _showImportError(String(err));
    })
    .finally(function() { input.value = ''; });
}

function _renderImportPreview(data) {
  var c = data.counts || {};
  document.getElementById('importCountNew').textContent = c.new || 0;
  document.getElementById('importCountDup').textContent = c.duplicates || 0;
  document.getElementById('importCountTotal').textContent = c.total || 0;
  document.getElementById('importNewCountInline').textContent = c.new || 0;
  document.getElementById('importDupCountInline').textContent = c.duplicates || 0;

  var newList = document.getElementById('importNewList');
  newList.innerHTML = '';
  (data.new || []).forEach(function(item) {
    var li = document.createElement('li');
    li.textContent = item.label;
    newList.appendChild(li);
  });

  var dupList = document.getElementById('importDupList');
  dupList.innerHTML = '';
  (data.duplicates || []).forEach(function(item) {
    var li = document.createElement('li');
    li.textContent = item.label;
    dupList.appendChild(li);
  });

  // If no duplicates, hide strategy block (nothing to choose).
  var hasDups = (c.duplicates || 0) > 0;
  var block = document.getElementById('importStrategyBlock');
  if (block) block.style.display = hasDups ? '' : 'none';
}

function confirmImport() {
  if (!_importToken) {
    _showImportError('Kein Import vorbereitet');
    return;
  }
  var strategyEl = document.querySelector('input[name="importStrategy"]:checked');
  var strategy = strategyEl ? strategyEl.value : 'skip';

  var btn = document.getElementById('importConfirmBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  _clearImportError();

  fetch(_ingressPrefix() + '/import/commit', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ token: _importToken, strategy: strategy }),
  })
    .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, body: j }; }); })
    .then(function(res) {
      if (!res.ok || !res.body.ok) {
        _showImportError(res.body.error || 'Import fehlgeschlagen');
        return;
      }
      // Success - reload so the new wines appear.
      closeModal('importPreviewModal');
      location.reload();
    })
    .catch(function(err) { _showImportError(String(err)); })
    .finally(function() {
      if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute('data-label') || 'Import'; }
    });
}

// Apply theme name on load (mode is handled by inline script + OS listener)
(function() {
  var name = localStorage.getItem('wine-theme-name') || 'homeassistant';
  applyThemeName(name);
})();

// OS theme change listener
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', function() {
  if ((localStorage.getItem('wine-theme') || 'system') === 'system') applyTheme('system');
});

// Initialize UI controls when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  updateThemeSegmented();
  updateThemeDropdown();
  initSettingsTabs();
});

// ── Area (cellar / bar) ──────────────────────────────────────────────────────
// The area is a property of the whole app, not of a single page: the cellar and
// the bar are separate collections, so the list AND the statistics follow it.
// Remembered so navigating between pages does not silently drop you back into
// the cellar. Pages that are area-aware set window._areaPath.
function wtCurrentArea() {
  var m = /[?&]area=([^&]+)/.exec(window.location.search);
  if (m) return decodeURIComponent(m[1]) === 'bar' ? 'bar' : 'cellar';
  try { return localStorage.getItem('wt_area') === 'bar' ? 'bar' : 'cellar'; } catch (e) {}
  return 'cellar';
}

function setArea(area) {
  area = (area === 'bar') ? 'bar' : 'cellar';
  try { localStorage.setItem('wt_area', area); } catch (e) {}
  var path = window._areaPath || '/';
  window.location.href = (window.INGRESS || '') + path + '?area=' + encodeURIComponent(area);
}

// A plain visit without ?area= restores the remembered area, so the switch does
// not appear to reset itself when moving from the list to the statistics.
(function() {
  if (window.location.search.indexOf('area=') !== -1) return;
  if (!window._areaPath) return;
  var saved = null;
  try { saved = localStorage.getItem('wt_area'); } catch (e) {}
  if (saved === 'bar') setArea('bar');
})();
