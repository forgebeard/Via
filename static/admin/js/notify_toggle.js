/**
 * Показывает/скрывает блок кастомных уведомлений
 * в зависимости от выбранного radio[name="notify_preset"].
 *
 * Использование: initNotifyToggle('notify_custom_box')
 */
function initNotifyToggle(boxId) {
  var radios = Array.from(document.querySelectorAll('input[name="notify_preset"]'));
  var box = document.getElementById(boxId);
  if (!box || !radios.length) return;

  function refresh() {
    var current = radios.find(function (r) { return r.checked; });
    box.style.display = current && current.value === 'custom' ? 'block' : 'none';
  }

  radios.forEach(function (r) { r.addEventListener('change', refresh); });
  refresh();
}