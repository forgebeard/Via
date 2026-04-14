/**
 * Парсинг пользователей из Redmine → Matrix.
 * Inline внутри пузыря, всегда видимый.
 */
(function () {
  'use strict';

  // DOM elements
  var startBtn = document.getElementById('parse-start');
  var createBtn = document.getElementById('parse-create');
  var targetUrlInput = document.getElementById('parse-target-url');
  var stepProgress = document.getElementById('parse-step-progress');
  var stepResults = document.getElementById('parse-step-results');
  var progressFill = document.getElementById('parse-progress-fill');
  var progressText = document.getElementById('parse-progress-text');
  var summaryDiv = document.getElementById('parse-summary');
  var selectAllCb = document.getElementById('parse-select-all');
  var selectAllHeader = document.getElementById('parse-select-all-header');
  var selectedCount = document.getElementById('parse-selected-count');
  var resultsBody = document.getElementById('parse-results-body');
  var parseReadyStatus = document.getElementById('parse-ready-status');

  var csrfToken = '';
  var lastScanData = null;

  // ── CSRF ──────────────────────────────────────────────────────

  function getCsrfToken() {
    if (csrfToken) return csrfToken;
    csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
    return csrfToken;
  }

  // ── Check if ready ───────────────────────────────────────────

  async function checkReady() {
    try {
      var r = await fetch('/api/users/scan-redmine/check');
      var data = await r.json();
      if (data.ready) {
        if (parseReadyStatus) {
          parseReadyStatus.textContent = '✅ Все параметры заполнены — можно начинать';
        }
      } else {
        if (parseReadyStatus) {
          parseReadyStatus.textContent = '⚠️ Заполните Параметры сервиса (Redmine + Matrix)';
        }
      }
    } catch (e) { /* ignore */ }
  }

  // ── Show steps ───────────────────────────────────────────────

  function showStep(step) {
    targetUrlInput.parentElement.style.display = step === 'url' ? '' : 'none';
    stepProgress.style.display = step === 'progress' ? '' : 'none';
    stepResults.style.display = step === 'results' ? '' : 'none';
  }

  function resetView() {
    showStep('url');
    targetUrlInput.value = '';
    lastScanData = null;
  }

  // ── Scan ────────────────────────────────────────────────────

  async function startScan() {
    var url = targetUrlInput.value.trim();
    if (!url) {
      targetUrlInput.focus();
      return;
    }

    console.log('[parse] Starting scan for:', url);

    showStep('progress');
    progressFill.style.width = '10%';
    progressText.textContent = 'Загрузка пользователей из Redmine...';

    var formData = new FormData();
    formData.append('target_url', url);
    formData.append('csrf_token', getCsrfToken());

    try {
      console.log('[parse] Sending fetch request...');
      var controller = new AbortController();
      // Без таймаута — сервер сам контролирует время

      var r = await fetch('/api/users/scan-redmine', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      console.log('[parse] Got response:', r.status);

      var data = await r.json();
      console.log('[parse] Response data:', data);

      if (!r.ok) {
        progressFill.style.width = '0%';
        resetView();
        if (typeof toast !== 'undefined') {
          toast.error(data.error || 'Ошибка сканирования');
        }
        return;
      }

      // Обновляем прогресс с количеством
      var total = data.total || 0;
      var found = data.found || 0;
      var existing = data.existing || 0;
      progressText.textContent = 'Найдено ' + total + ' сотрудников в Redmine. ' +
        'В Matrix сопоставлено: ' + found + ' из ' + total +
        (existing > 0 ? ' (уже в системе: ' + existing + ')' : '');
      progressFill.style.width = '95%';

      lastScanData = data;
      renderResults(data);
      showStep('results');
    } catch (e) {
      console.error('[parse] Error:', e);
      progressFill.style.width = '0%';
      resetView();
      if (typeof toast !== 'undefined') {
        if (e.name === 'AbortError') {
          toast.error('Превышено время ожидания (2 мин). Попробуйте ещё раз.');
        } else {
          toast.error('Ошибка сети: ' + e.message);
        }
      }
    }
  }

  // ── Render results ───────────────────────────────────────────

  function renderResults(data) {
    var matches = data.matches || [];
    summaryDiv.innerHTML =
      '<span class="found">✅ Найдено: ' + data.found + '</span>' +
      '<span class="existing">ℹ️ Уже в системе: ' + data.existing + '</span>' +
      '<span class="not-found">❌ Не найдено: ' + data.not_found + '</span>';

    resultsBody.innerHTML = '';
    matches.forEach(function (m, i) {
      var tr = document.createElement('tr');

      var statusText, statusClass;
      if (m.status === 'found') {
        statusText = '✅ Найден';
        statusClass = 'status-found';
      } else if (m.status === 'existing') {
        statusText = 'ℹ️ Уже в системе';
        statusClass = 'status-existing';
      } else {
        statusText = '❌ Не найден';
        statusClass = 'status-not-found';
      }

      var cbChecked = 'checked';
      var cbDisabled = '';

      tr.innerHTML =
        '<td><input type="checkbox" class="parse-cb" data-idx="' + i + '" ' + cbChecked + ' ' + cbDisabled + '/></td>' +
        '<td>' + escHtml(m.redmine_name) + '</td>' +
        '<td>' + m.redmine_id + '</td>' +
        '<td>' + escHtml(m.matrix_localpart || '—') + '</td>' +
        '<td class="' + statusClass + '">' + statusText + '</td>';

      resultsBody.appendChild(tr);
    });

    updateSelectedCount();
  }

  function escHtml(s) {
    var div = document.createElement('div');
    div.textContent = s || '';
    return div.innerHTML;
  }

  function updateSelectedCount() {
    var total = resultsBody.querySelectorAll('.parse-cb:not([disabled])').length;
    var checked = resultsBody.querySelectorAll('.parse-cb:checked:not([disabled])').length;
    selectedCount.textContent = 'Выбрано: ' + checked + ' из ' + total;
  }

  // ── Bulk create ──────────────────────────────────────────────

  async function bulkCreate() {
    console.log('[parse] bulkCreate called');
    console.log('[parse] lastScanData:', lastScanData);

    if (!lastScanData || !lastScanData.matches) {
      console.error('[parse] No scan data available!');
      if (typeof toast !== 'undefined') {
        toast.error('Нет данных для создания. Сначала выполните сканирование.');
      }
      return;
    }

    var selected = [];
    resultsBody.querySelectorAll('.parse-cb:checked').forEach(function (cb) {
      var idx = parseInt(cb.getAttribute('data-idx'), 10);
      console.log('[parse] Checkbox checked: idx=' + idx);
      if (lastScanData && lastScanData.matches[idx]) {
        var m = lastScanData.matches[idx];
        console.log('[parse] Adding user:', m.redmine_name, m.matrix_localpart, m.status);
        selected.push({
          redmine_id: m.redmine_id,
          redmine_name: m.redmine_name,
          matrix_localpart: m.matrix_localpart || '',
        });
      }
    });

    console.log('[parse] Selected users count:', selected.length);

    if (selected.length === 0) {
      console.warn('[parse] No users selected');
      if (typeof toast !== 'undefined') {
        toast.warning('Выберите хотя бы одного пользователя');
      }
      return;
    }

    createBtn.disabled = true;
    createBtn.textContent = 'Создаю...';

    try {
      console.log('[parse] Sending bulk-create request with', selected.length, 'users');
      var r = await fetch('/api/users/bulk-create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({
          users: selected,
          csrf_token: getCsrfToken(),
        }),
      });

      console.log('[parse] Bulk-create response status:', r.status);
      var data = await r.json();
      console.log('[parse] Bulk-create response data:', data);

      if (!r.ok) {
        if (typeof toast !== 'undefined') {
          toast.error(data.error || 'Ошибка создания');
        }
        return;
      }

      var msg = 'Создано: ' + data.total_created;
      if (data.total_skipped) msg += ', пропущено: ' + data.total_skipped;
      if (data.total_errors) msg += ', ошибок: ' + data.total_errors;

      if (typeof toast !== 'undefined') {
        toast.success(msg);
      }

      setTimeout(function () { window.location.href = '/users'; }, 500);
    } catch (e) {
      console.error('[parse] Bulk-create error:', e);
      if (typeof toast !== 'undefined') {
        toast.error('Ошибка сети: ' + e.message);
      }
    } finally {
      createBtn.disabled = false;
      createBtn.textContent = 'Создать выбранных';
    }
  }

  // ── Select all ───────────────────────────────────────────────

  function toggleSelectAll(checked) {
    resultsBody.querySelectorAll('.parse-cb:not([disabled])').forEach(function (cb) {
      cb.checked = checked;
    });
    updateSelectedCount();
  }

  // ── Event listeners ──────────────────────────────────────────

  if (!startBtn) {
    console.error('[parse] startBtn not found!');
  } else {
    console.log('[parse] startBtn found, attaching listener');
    startBtn.addEventListener('click', function () {
      console.log('[parse] startBtn clicked');
      startScan();
    });
  }
  if (createBtn) createBtn.addEventListener('click', bulkCreate);

  if (selectAllCb) {
    selectAllCb.addEventListener('change', function () {
      toggleSelectAll(this.checked);
      if (selectAllHeader) selectAllHeader.checked = this.checked;
    });
  }
  if (selectAllHeader) {
    selectAllHeader.addEventListener('change', function () {
      toggleSelectAll(this.checked);
      if (selectAllCb) selectAllCb.checked = this.checked;
    });
  }

  if (targetUrlInput) {
    targetUrlInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        startScan();
      }
    });
  }

  checkReady();
})();
