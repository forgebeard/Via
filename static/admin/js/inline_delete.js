/**
 * Инлайн-подтверждение удаления.
 * Использование: bindInlineDelete(formElement, 'группу')
 */
function bindInlineDelete(form, entityLabel) {
  var deleteBtn = form.querySelector('button[type="submit"]');
  if (!deleteBtn) return;

  form.addEventListener('submit', function (e) {
    if (form.dataset.confirmed === '1') return;
    e.preventDefault();
    if (form.dataset.confirming === '1') return;
    form.dataset.confirming = '1';
    deleteBtn.style.display = 'none';

    var confirmWrap = document.createElement('span');
    confirmWrap.className = 'inline-delete-confirm';

    var ask = document.createElement('span');
    ask.className = 'muted';
    ask.textContent = 'Удалить ' + entityLabel + '?';

    var yesBtn = document.createElement('button');
    yesBtn.type = 'button';
    yesBtn.className = 'btn btn-danger btn-small';
    yesBtn.textContent = 'Удалить';

    var noBtn = document.createElement('button');
    noBtn.type = 'button';
    noBtn.className = 'btn btn-ghost btn-small';
    noBtn.textContent = 'Отмена';

    yesBtn.addEventListener('click', function () {
      form.dataset.confirmed = '1';
      form.submit();
    });
    noBtn.addEventListener('click', function () {
      delete form.dataset.confirming;
      confirmWrap.remove();
      deleteBtn.style.display = '';
    });

    confirmWrap.appendChild(ask);
    confirmWrap.appendChild(yesBtn);
    confirmWrap.appendChild(noBtn);
    deleteBtn.insertAdjacentElement('afterend', confirmWrap);
  });
}