(function () {
  var form = document.getElementById("settings-form");
  if (!form) return;

  var catalogStatus = document.getElementById("catalog-save-status");
  var persistTimer = null;

  /* --- Masked inputs highlight --- */
  function markMaskedInputs() {
    form.querySelectorAll('input[name^="secret_"]').forEach(function (input) {
      if (input.value && input.value.indexOf('••••') !== -1) {
        input.classList.add('is-masked');
      } else {
        input.classList.remove('is-masked');
      }
    });
  }
  markMaskedInputs();

  /* --- Toggle visibility (глазки) --- */
  initToggleVisibility();

  /* --- Catalog auto-save --- */
  function persistCatalog() {
    var fd = new FormData();
    var csrf = form.querySelector('input[name="csrf_token"]');
    fd.append("csrf_token", csrf ? csrf.value : "");
    fd.append("catalog_notify_json", document.getElementById("catalog_notify_json").value || "[]");
    fd.append("catalog_versions_json", document.getElementById("catalog_versions_json").value || "[]");
    if (catalogStatus) catalogStatus.textContent = "Сохранение справочника...";
    fetch("/onboarding/catalog/save", {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    }).then(function (resp) {
      if (!resp.ok) throw new Error("catalog_save_failed");
      if (catalogStatus) catalogStatus.textContent = "Справочник сохранен.";
    }).catch(function () {
      if (catalogStatus) catalogStatus.textContent = "Ошибка сохранения справочника.";
    });
  }

  function queuePersist() {
    if (persistTimer) clearTimeout(persistTimer);
    persistTimer = setTimeout(persistCatalog, 400);
  }

  /* --- Init catalog editors --- */
  createCatalogEditor({
    kind: "notify",
    listId: "notify-list",
    addInputId: "notify-add-input",
    addBtnId: "notify-add",
    hiddenId: "catalog_notify_json",
    onSync: queuePersist
  });
  createCatalogEditor({
    kind: "simple",
    listId: "versions-list",
    addInputId: "versions-add-input",
    addBtnId: "versions-add",
    hiddenId: "catalog_versions_json",
    onSync: queuePersist
  });

  /* --- Form submit (save) --- */
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    fetch("/onboarding/save", {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: { Accept: "text/html" }
    }).then(function (resp) {
      if (resp.redirected) {
        window.location.href = resp.url;
      } else {
        showToast("Изменения сохранены", false);
      }
    }).catch(function () {
      showToast("Ошибка при сохранении", true);
    });
  });

  /* --- Check access --- */
  (function () {
    var btn = document.getElementById("check-access-btn");
    var status = document.getElementById("check-access-status");
    if (!btn || !status) return;

    btn.addEventListener("click", function () {
      status.textContent = "Проверка...";
      btn.disabled = true;
      var fd = new FormData(form);
      fetch("/onboarding/check", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (resp) {
        return resp.json().catch(function () { return {}; });
      }).then(function (data) {
        if (!Array.isArray(data.checks)) {
          status.textContent = "Не удалось выполнить проверку.";
          return;
        }
        var lines = data.checks.map(function (item) {
          return (item && item.message) ? String(item.message) : "";
        }).filter(Boolean);
        status.textContent = lines.join(" ");
      }).catch(function () {
        status.textContent = "Ошибка сети при проверке.";
      }).finally(function () {
        btn.disabled = false;
      });
    });
  })();

  /* --- Regenerate DB credentials --- */
  (function () {
    var btn = document.getElementById("regenerate-db-credentials");
    var status = document.getElementById("db-regenerate-status");
    var dbPasswordInput = document.getElementById("db_password");
    var masterKeyInput = document.getElementById("master_key");
    if (!btn || !status) return;

    btn.addEventListener("click", function () {
      if (!confirm(
        "Сгенерировать новые credentials?\n\n" +
        "После этого необходимо перезапустить контейнеры:\n" +
        "docker compose restart postgres bot admin\n\n" +
        "Продолжить?"
      )) return;

      status.textContent = "Генерация...";
      btn.disabled = true;

      var fd = new FormData();
      var csrfInput = form.querySelector('input[name="csrf_token"]');
      fd.append("csrf_token", csrfInput ? csrfInput.value : "");
      fd.append("regenerate_password", "1");
      fd.append("regenerate_key", "1");

      fetch("/settings/db-config/regenerate", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (resp) {
        return resp.json();
      }).then(function (data) {
        if (data.ok) {
          status.textContent = data.message;
          if (dbPasswordInput && data.new_postgres_password) {
            dbPasswordInput.value = data.new_postgres_password;
            dbPasswordInput.type = "text";
          }
          if (masterKeyInput && data.new_app_master_key) {
            masterKeyInput.value = data.new_app_master_key;
            masterKeyInput.type = "text";
          }
        } else {
          status.textContent = "Ошибка: " + (data.detail || "Неизвестная ошибка");
        }
      }).catch(function () {
        status.textContent = "Ошибка сети.";
      }).finally(function () {
        btn.disabled = false;
      });
    });
  })();
})();