document.addEventListener('DOMContentLoaded', function () {
  var row = document.getElementById('highlight-user-row');
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(function () {
      row.classList.remove('is-highlighted-row');
    }, 2200);
    var url = new URL(window.location.href);
    if (url.searchParams.has('highlight_user_id')) {
      url.searchParams.delete('highlight_user_id');
      window.history.replaceState({}, '', url.pathname + (url.search || ''));
    }
  }

  Array.from(document.querySelectorAll('form[data-inline-delete-form]')).forEach(function (form) {
    bindInlineDelete(form, 'пользователя');
  });

  // ── Bulk delete logic ───────────────────────────────────────────
  var selectAllCb = document.getElementById('users-select-all');
  var userCbs = document.querySelectorAll('.user-cb');
  var bulkDeleteBtn = document.getElementById('bulk-delete-btn');

  function updateBulkBtn() {
    var checkedCount = document.querySelectorAll('.user-cb:checked').length;
    bulkDeleteBtn.disabled = checkedCount === 0;
    if (selectAllCb) {
      selectAllCb.checked = checkedCount === userCbs.length && userCbs.length > 0;
    }
  }

  if (selectAllCb) {
    selectAllCb.addEventListener('change', function () {
      userCbs.forEach(function (cb) {
        cb.checked = selectAllCb.checked;
      });
      updateBulkBtn();
    });
  }

  userCbs.forEach(function (cb) {
    cb.addEventListener('change', updateBulkBtn);
  });

  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener('click', function () {
      var selectedIds = [];
      userCbs.forEach(function (cb) {
        if (cb.checked) {
          selectedIds.push(cb.getAttribute('data-id'));
        }
      });

      if (selectedIds.length === 0) return;
      if (!confirm('Удалить выбранных пользователей (' + selectedIds.length + ' чел.)?')) return;

      var csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
      
      bulkDeleteBtn.disabled = true;
      bulkDeleteBtn.textContent = 'Удаляю...';

      var formData = new FormData();
      selectedIds.forEach(function (id) {
        formData.append('user_ids', id);
      });
      formData.append('csrf_token', csrfToken);

      fetch('/users/bulk-delete', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      })
      .then(function (r) {
        if (!r.ok) {
          // Сервер вернул ошибку (403, 500 и т.д.)
          return r.text().then(function (text) {
            // Пытаемся распарсить как JSON, иначе покажем текст
            try {
              return { success: false, error: JSON.parse(text).error || text };
            } catch (e) {
              return { success: false, error: 'Сервер вернул ошибку: ' + r.status + ' ' + text.substring(0, 100) };
            }
          });
        }
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          window.location.reload();
        } else {
          alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
          bulkDeleteBtn.disabled = false;
          bulkDeleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Удалить выбранных';
        }
      })
      .catch(function (e) {
        console.error('[bulk-delete] Network error:', e);
        alert('Ошибка сети: ' + e.message);
        bulkDeleteBtn.disabled = false;
        bulkDeleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Удалить выбранных';
      });
    });
  }
});