(function () {
  /* --- Toast on return from save --- */
  var params = new URLSearchParams(window.location.search);
  if (params.get('saved') === '1') {
    if (typeof showToast === 'function') {
      showToast('Группа сохранена');
    }
    params.delete('saved');
    var newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    window.history.replaceState({}, '', newUrl);
  }

  /* --- Notify preset toggle --- */
  var notifyRadios = Array.from(document.querySelectorAll('input[name="notify_preset"]'));
  var notifyBox = document.getElementById('notify_custom_box_group');

  function refreshNotifyBox() {
    var current = notifyRadios.find(function (r) { return r.checked; });
    if (!notifyBox) return;
    notifyBox.style.display = current && current.value === 'custom' ? 'block' : 'none';
  }

  notifyRadios.forEach(function (r) {
    r.addEventListener('change', function () { refreshNotifyBox(); refreshSummary(); });
  });
  refreshNotifyBox();

  /* --- Version preset toggle --- */
  var versionRadios = Array.from(document.querySelectorAll('input[name="version_preset"]'));
  var versionBox = document.getElementById('group_versions_custom_box');
  var versionChoices = Array.from(document.querySelectorAll('input[name="version_values"]'));
  var hiddenVersionJson = document.getElementById('group_version_keys_json');
  var hiddenInitialKeys = document.getElementById('initial_version_keys');

  function refreshVersionBox() {
    var current = versionRadios.find(function (r) { return r.checked; });
    if (!versionBox) return;
    versionBox.style.display = current && current.value === 'custom' ? 'block' : 'none';
  }

  function syncVersions() {
    var current = versionRadios.find(function (r) { return r.checked; });
    var values = [];
    if (current && current.value === 'all') {
      values = versionChoices.map(function (c) { return c.value.trim(); }).filter(Boolean);
    } else {
      values = versionChoices.filter(function (c) { return c.checked; }).map(function (c) { return c.value.trim(); }).filter(Boolean);
    }
    if (hiddenVersionJson) hiddenVersionJson.value = JSON.stringify(values);
    if (hiddenInitialKeys) hiddenInitialKeys.value = values.join(', ');
    refreshSummary();
  }

  versionRadios.forEach(function (radio) {
    radio.addEventListener('change', function () { refreshVersionBox(); syncVersions(); });
  });
  versionChoices.forEach(function (choice) {
    choice.addEventListener('change', syncVersions);
  });
  refreshVersionBox();
  syncVersions();

  /* --- Summary helpers --- */
  function textOrDash(v) {
    var value = String(v || '').trim();
    return value || '—';
  }

  function selectedNotifyLabel() {
    var active = document.querySelector('input[name="notify_preset"]:checked');
    if (!active) return '—';
    if (active.value === 'all') return 'Все уведомления';
    var labels = Array.from(document.querySelectorAll('input[name="notify_values"]'))
      .filter(function (el) { return el.checked; })
      .map(function (el) { return String(el.parentElement && el.parentElement.textContent || '').trim(); })
      .filter(Boolean);
    return labels.length ? labels.join(', ') : '—';
  }

  function selectedVersionsLabel() {
    var active = document.querySelector('input[name="version_preset"]:checked');
    if (!active) return '—';
    if (active.value === 'all') return 'Все версии';
    var labels = Array.from(document.querySelectorAll('input[name="version_values"]'))
      .filter(function (el) { return el.checked; })
      .map(function (el) { return String(el.parentElement && el.parentElement.textContent || '').trim(); })
      .filter(Boolean);
    return labels.length ? labels.join(', ') : '—';
  }

  function selectedHours() {
    var from = document.getElementById('work_hours_from_group');
    var to = document.getElementById('work_hours_to_group');
    var fv = from ? String(from.value || '').trim() : '';
    var tv = to ? String(to.value || '').trim() : '';
    if (fv && tv) return fv + ' — ' + tv;
    return 'Не задано';
  }

  function dndLabel() {
    var dnd = document.getElementById('dnd_group');
    return dnd && dnd.checked ? 'Включено' : 'Выключено';
  }

  function setSummary(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    el.title = value && value !== '—' ? value : '';
  }

  /* fallback timezone из data-атрибута формы */
  var formRoot = document.querySelector('.user-form-root');
  var fallbackTz = formRoot ? (formRoot.getAttribute('data-bot-tz') || '') : '';

  function refreshSummary() {
    var nameEl = document.getElementById('name');
    var roomEl = document.getElementById('room_id');
    var tzEl = document.getElementById('timezone_name');
    setSummary('summary_group_name', textOrDash(nameEl ? nameEl.value : ''));
    setSummary('summary_group_room', textOrDash(roomEl ? roomEl.value : ''));
    setSummary('summary_group_tz', textOrDash(tzEl ? tzEl.value : fallbackTz));
    setSummary('summary_group_notify', selectedNotifyLabel());
    setSummary('summary_group_versions', selectedVersionsLabel());
    setSummary('summary_group_hours', selectedHours());
    setSummary('summary_group_dnd', dndLabel());
  }

  /* --- Bind summary listeners --- */
  ['name', 'room_id', 'timezone_name', 'work_hours_from_group', 'work_hours_to_group', 'dnd_group'].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    var evt = (id === 'dnd_group' || id === 'timezone_name') ? 'change' : 'input';
    el.addEventListener(evt, refreshSummary);
    if (evt !== 'change') el.addEventListener('change', refreshSummary);
  });

  Array.from(document.querySelectorAll('input[name="notify_preset"]')).forEach(function (el) {
    el.addEventListener('change', refreshSummary);
  });
  Array.from(document.querySelectorAll('input[name="notify_values"], input[name="version_values"], input[name="version_preset"]')).forEach(function (el) {
    el.addEventListener('change', refreshSummary);
  });

  refreshSummary();

  /* --- Кнопка «Отправить тестовое сообщение» --- */
  var testBtn = document.getElementById('group_test_message_btn');
  var statusEl = document.getElementById('group_test_status');

  if (testBtn && statusEl) {
    testBtn.addEventListener('click', async function () {
      var roomId = testBtn.getAttribute('data-room-id') || '';
      var inputRoomId = document.getElementById('room_id');
      if (inputRoomId && !roomId) {
        roomId = inputRoomId.value.trim();
      }

      if (!roomId) {
        statusEl.textContent = 'Укажите ID комнаты группы';
        return;
      }

      testBtn.disabled = true;
      testBtn.textContent = '⏳ Отправка…';
      statusEl.textContent = '';
      try {
        var csrfInput = document.querySelector('input[name="csrf_token"]');
        var csrf = csrfInput ? csrfInput.value : '';
        var body = new FormData();
        body.append('room_id', roomId);
        var r = await fetch('/groups/test-message', {
          method: 'POST',
          headers: { 'Accept': 'application/json', 'X-CSRF-Token': csrf },
          credentials: 'same-origin',
          body: body,
        });
        var data = await r.json().catch(function () { return {}; });
        if (data.ok) {
          statusEl.textContent = 'Сообщение доставлено';
        } else {
          statusEl.textContent = 'Не доставлено: ' + (data.error || 'неизвестная ошибка');
        }
      } catch (e) {
        statusEl.textContent = 'Не доставлено: ошибка сети';
      } finally {
        testBtn.disabled = false;
        testBtn.textContent = 'Отправить тестовое сообщение';
      }
    });
  }

  /* --- Form validation --- */
  var form = document.querySelector('.form');
  if (form) {
    form.addEventListener('submit', function (e) {
      var nameEl = document.getElementById('name');
      var roomEl = document.getElementById('room_id');
      var errors = [];

      if (nameEl && !nameEl.value.trim()) {
        errors.push('Укажите название группы');
        nameEl.style.borderColor = '#f87171';
      } else if (nameEl) {
        nameEl.style.borderColor = '';
      }

      if (roomEl && !roomEl.value.trim()) {
        errors.push('Укажите ID комнаты');
        roomEl.style.borderColor = '#f87171';
      } else if (roomEl && roomEl.value.trim() && !roomEl.value.trim().startsWith('!')) {
        errors.push('ID комнаты должен начинаться с «!»');
        roomEl.style.borderColor = '#f87171';
      } else if (roomEl) {
        roomEl.style.borderColor = '';
      }

      if (errors.length) {
        e.preventDefault();
        if (typeof showToast === 'function') {
          showToast(errors.join('. '), true);
        }
      }
    });
  }

  /* --- Time input auto-format (24h, HH:MM) with strict validation --- */
  var TIME_RE = /^[0-2]\d:[0-5]\d$/;

  function validateTime(val) {
    if (!val || val.length < 4) return true; // incomplete — don't error yet
    if (!TIME_RE.test(val)) return false;
    var h = parseInt(val.substring(0, 2), 10);
    return h >= 0 && h <= 23;
  }

  document.querySelectorAll('input[name="work_hours_from"], input[name="work_hours_to"]').forEach(function (el) {
    el.addEventListener('input', function () {
      var val = el.value.replace(/[^\d:]/g, '');
      if (val.length === 2 && !val.includes(':')) {
        val = val + ':';
      }
      if (val.length > 5) val = val.substring(0, 5);
      el.value = val;
      el.classList.toggle('is-invalid', !validateTime(val));
    });
    el.addEventListener('blur', function () {
      var val = el.value.trim();
      if (!val) return;
      var m = val.match(/^(\d{1,2}):(\d{2})$/);
      if (!m) {
        el.value = '';
        el.classList.add('is-invalid');
        return;
      }
      var h = parseInt(m[1], 10);
      var min = parseInt(m[2], 10);
      if (h > 23 || min > 59) {
        el.value = '';
        el.classList.add('is-invalid');
        return;
      }
      el.value = String(h).padStart(2, '0') + ':' + String(min).padStart(2, '0');
      el.classList.remove('is-invalid');
    });
  });
})();