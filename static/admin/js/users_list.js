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
});