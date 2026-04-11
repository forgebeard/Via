(function () {
  /* --- Highlight row after redirect --- */
  var row = document.getElementById('highlight-group-row');
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(function () {
      row.classList.remove('is-highlighted-row');
    }, 2200);

    var url = new URL(window.location.href);
    if (url.searchParams.has('highlight_group_id')) {
      url.searchParams.delete('highlight_group_id');
      window.history.replaceState({}, '', url.pathname + (url.search || ''));
    }
  }

  /* --- Inline delete for each group --- */
  Array.from(document.querySelectorAll('form[data-inline-delete-form]')).forEach(function (form) {
    bindInlineDelete(form, 'группу');
  });
})();