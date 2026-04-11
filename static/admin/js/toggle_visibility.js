/**
 * Инициализирует все кнопки .toggle-visibility на странице.
 * Переключает type=password ↔ text и подставляет data-real-value / data-masked-value.
 */
function initToggleVisibility() {
  document.querySelectorAll('.toggle-visibility').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var inputId = this.getAttribute('data-target');
      var input = document.getElementById(inputId);
      if (!input) return;

      var isPassword = input.type === 'password';
      if (isPassword) {
        var realValue = input.getAttribute('data-real-value');
        if (realValue) input.value = realValue;
        input.type = 'text';
      } else {
        var maskedValue = input.getAttribute('data-masked-value');
        if (maskedValue) input.value = maskedValue;
        input.type = 'password';
      }

      var icon = this.querySelector('i');
      if (icon) {
        icon.className = isPassword ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
      }
    });
  });
}