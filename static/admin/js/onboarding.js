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
      // Добавляем CSRF токен
      var csrf = form.querySelector('input[name="csrf_token"]');
      fd.set("csrf_token", csrf ? csrf.value : "");
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

  /* --- Daily report schedule (cycle_settings via /api/bot/content) --- */
  (function () {
    var enabled = document.getElementById("daily_report_enabled");
    var timeInput = document.getElementById("daily_report_time");
    var saveBtn = document.getElementById("daily_report_schedule_save");
    var status = document.getElementById("daily_report_schedule_status");
    if (!enabled || !timeInput || !saveBtn || !status) return;

    function csrfTok() {
      var csrfInput = form.querySelector('input[name="csrf_token"]');
      return csrfInput ? csrfInput.value : "";
    }

    function pad2(n) {
      return n < 10 ? "0" + n : String(n);
    }

    function parseTime(value) {
      var raw = String(value || "").trim();
      var m = raw.match(/^([0-1]\d|2[0-3]):([0-5]\d)$/);
      if (!m) return null;
      return { hour: parseInt(m[1], 10), minute: parseInt(m[2], 10) };
    }

    function normalizeTime(value, fallbackHour, fallbackMinute) {
      var parsed = parseTime(value);
      if (parsed) return parsed;
      return {
        hour: Math.max(0, Math.min(23, parseInt(fallbackHour, 10) || 9)),
        minute: Math.max(0, Math.min(59, parseInt(fallbackMinute, 10) || 0))
      };
    }

    function loadSchedule() {
      status.textContent = "Загрузка расписания…";
      fetch("/api/bot/content", {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (resp) {
        if (!resp.ok) throw new Error("load_failed");
        return resp.json();
      }).then(function (data) {
        var s = (data && data.settings) || {};
        enabled.checked = !!s.daily_report_enabled;
        var parsed = normalizeTime("", s.daily_report_hour, s.daily_report_minute);
        timeInput.value = pad2(parsed.hour) + ":" + pad2(parsed.minute);
        status.textContent = "";
      }).catch(function () {
        status.textContent = "Не удалось загрузить расписание.";
      });
    }

    saveBtn.addEventListener("click", function () {
      var parsed = parseTime(timeInput.value);
      if (!parsed) {
        status.textContent = "Введите время в формате ЧЧ:ММ.";
        return;
      }
      timeInput.value = pad2(parsed.hour) + ":" + pad2(parsed.minute);
      status.textContent = "Сохранение…";
      var fd = new FormData();
      fd.append("csrf_token", csrfTok());
      fd.append("daily_report_enabled", enabled.checked ? "true" : "false");
      fd.append("daily_report_hour", String(parsed.hour));
      fd.append("daily_report_minute", String(parsed.minute));
      fetch("/api/bot/content", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (resp) {
        if (!resp.ok) throw new Error("save_failed");
        return resp.json();
      }).then(function (d) {
        if (d && d.ok) {
          status.textContent = "Расписание сохранено.";
          showToast("Расписание утреннего отчёта сохранено", false);
        } else {
          status.textContent = "Ошибка сохранения.";
        }
      }).catch(function () {
        status.textContent = "Ошибка сети при сохранении.";
      });
    });

    window.addEventListener("via-settings-tab", function (ev) {
      if (ev.detail && ev.detail.tab === "notifications") loadSchedule();
    });
    if (window.location.hash === "#notifications") loadSchedule();
  })();

  /* --- Journal engine Jinja2 templates (notification_templates) --- */
  (function () {
    var root = document.getElementById("tpl-v2-fields");
    var statusEl = document.getElementById("tpl-v2-status");
    if (!root || !statusEl) return;
    var tplScope = document.getElementById("tab-notifications") || document;
    void document.getElementById("daily-report-template-root");
    void document.getElementById("daily-report-template-missing");

    function csrfToken() {
      var csrfInput = form.querySelector('input[name="csrf_token"]');
      return csrfInput ? csrfInput.value : "";
    }

    function loadV2() {
      statusEl.textContent = "Загрузка шаблонов v2…";
      var editorNames = {};
      var bootEl = document.getElementById("block-editor-bootstrap");
      if (bootEl && bootEl.textContent) {
        try {
          var bt = JSON.parse(bootEl.textContent);
          (bt.editor_template_names || []).forEach(function (n) {
            editorNames[n] = true;
          });
        } catch (ignore) {}
      }
      var dailyRoot = document.getElementById("daily-report-template-root");
      var dailyMissing = document.getElementById("daily-report-template-missing");
      fetch("/api/bot/notification-templates", {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (resp) {
        if (!resp.ok) throw new Error("load_failed");
        return resp.json();
      }).then(function (data) {
        tplScope.querySelectorAll(".block-editor-root").forEach(function (el) {
          if (el._blockEditor && typeof el._blockEditor.destroy === "function") {
            el._blockEditor.destroy();
          }
          el._blockEditor = null;
        });
        root.innerHTML = "";
        if (dailyRoot) dailyRoot.innerHTML = "";
        var hadDailyTpl = false;
        (data.templates || []).forEach(function (tpl) {
          var displayLabel = tpl.display_name || tpl.name;
          var isDailyTemplate = tpl.name === "tpl_daily_report";
          var isEditorTemplate = !!editorNames[tpl.name];
          var wrap = document.createElement("div");
          wrap.className = isDailyTemplate ? "daily-report__editor-wrap" : "service-bubble tpl-v2-template-card";
          if (!isDailyTemplate && !isEditorTemplate) {
            var title = document.createElement("div");
            title.className = "card-title tpl-v2-card__title";
            title.textContent = displayLabel;
            wrap.appendChild(title);
          }
          if (isEditorTemplate) {
            if (!isDailyTemplate) {
              var head = document.createElement("div");
              head.className = "daily-report__head";
              var headTitle = document.createElement("div");
              headTitle.className = "card-title";
              headTitle.textContent = displayLabel;
              head.appendChild(headTitle);
              var switchLabel = document.createElement("label");
              switchLabel.className = "switch daily-report__head-switch";
              var switchId = "tpl_v2_enabled_" + tpl.name.replace(/[^a-zA-Z0-9_-]/g, "_");
              switchLabel.setAttribute("for", switchId);
              switchLabel.innerHTML =
                '<input type="checkbox" id="' +
                switchId +
                '" class="tpl-v2-template-switch" data-template-name="' +
                tpl.name +
                '" aria-label="Переключить шаблон"/>' +
                '<span class="switch-ui" aria-hidden="true"></span>';
              head.appendChild(switchLabel);
              wrap.appendChild(head);
            }
            var bed = document.createElement("div");
            bed.className = "block-editor-root";
            bed.setAttribute("data-template-name", tpl.name);
            wrap.appendChild(bed);
            if (typeof window.BlockEditor === "function") {
              var editor = new window.BlockEditor(bed, tpl.name);
              bed._blockEditor = editor;
              editor.init().catch(function (err) {
                console.error("BlockEditor init failed", err);
                bed.innerHTML = "<p class=\"error\">Не удалось загрузить конструктор</p>";
              }).finally(function () {
                var tplSwitch = wrap.querySelector('.tpl-v2-template-switch[data-template-name="' + tpl.name + '"]');
                if (!tplSwitch || !bed._blockEditor) return;
                tplSwitch.checked = !!bed._blockEditor.templateEnabled;
                tplSwitch.addEventListener("change", function () {
                  if (bed._blockEditor && typeof bed._blockEditor.onTemplateToggle === "function") {
                    bed._blockEditor.onTemplateToggle(!!tplSwitch.checked);
                  }
                });
              });
            } else {
              bed.innerHTML = "<p class=\"error\">Конструктор блоков не загружен</p>";
            }
          } else {
            var lab = document.createElement("label");
            wrap.appendChild(lab);
            var ta = document.createElement("textarea");
            ta.className = "tpl-v2-html";
            ta.setAttribute("data-name", tpl.name);
            ta.rows = 6;
            ta.value = (tpl.override_html != null && tpl.override_html !== "")
              ? tpl.override_html
              : (tpl.default_html || "");
            wrap.appendChild(ta);
            var footer = document.createElement("div");
            footer.className = "block-editor__footer tpl-v2-card__footer";
            var st = document.createElement("span");
            st.className = "block-editor__status";
            footer.appendChild(st);
            var actions = document.createElement("div");
            actions.className = "block-editor__footer-actions";
            ["Сохранить", "Сбросить", "Предпросмотр"].forEach(function (label, idx) {
              var b = document.createElement("button");
              b.type = "button";
              b.textContent = label;
              b.className = idx === 0 ? "btn btn-primary" : "btn btn-ghost";
              if (idx === 0) {
                b.classList.add("tpl-v2-save");
                b.setAttribute("data-action", "save");
              }
              if (idx === 1) {
                b.classList.add("tpl-v2-reset");
                b.setAttribute("data-action", "reset");
              }
              if (idx === 2) b.classList.add("tpl-v2-preview");
              b.setAttribute("data-name", tpl.name);
              b.setAttribute("data-display-label", displayLabel);
              actions.appendChild(b);
            });
            footer.appendChild(actions);
            wrap.appendChild(footer);
            var pre = document.createElement("pre");
            pre.className = "tpl-v2-preview-out muted tpl-v2-preview-pre";
            pre.setAttribute("data-name", tpl.name);
            wrap.appendChild(pre);
          }
          var mount = root;
          if (isDailyTemplate && dailyRoot) {
            mount = dailyRoot;
            hadDailyTpl = true;
          }
          mount.appendChild(wrap);
        });
        if (dailyMissing) {
          if (hadDailyTpl || !dailyRoot) {
            dailyMissing.classList.add("is-hidden");
          } else {
            dailyMissing.classList.remove("is-hidden");
          }
        }
        tplScope.querySelectorAll(".tpl-v2-save").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var name = btn.getAttribute("data-name");
            var label = btn.getAttribute("data-display-label") || name;
            var ta = tplScope.querySelector('.tpl-v2-html[data-name="' + name + '"]');
            var fd = new FormData();
            fd.append("csrf_token", csrfToken());
            fd.append("body_html", ta ? ta.value : "");
            fd.append("body_plain", "");
            statusEl.textContent = "Сохранение " + label + "…";
            fetch("/api/bot/notification-templates/" + encodeURIComponent(name), {
              method: "PUT",
              body: fd,
              credentials: "same-origin",
              headers: { Accept: "application/json" }
            }).then(function (resp) {
              if (!resp.ok) throw new Error("save_failed");
              statusEl.textContent = "Сохранено: " + label;
              showToast("Шаблон " + label + " сохранён", false);
            }).catch(function () {
              statusEl.textContent = "Ошибка сохранения " + label;
            });
          });
        });
        tplScope.querySelectorAll(".tpl-v2-reset").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var name = btn.getAttribute("data-name");
            var label = btn.getAttribute("data-display-label") || name;
            var fd = new FormData();
            fd.append("csrf_token", csrfToken());
            fetch("/api/bot/notification-templates/" + encodeURIComponent(name) + "/reset", {
              method: "POST",
              body: fd,
              credentials: "same-origin",
              headers: { Accept: "application/json" }
            }).then(function (resp) {
              if (!resp.ok) throw new Error("reset_failed");
              loadV2();
            }).catch(function () {
              statusEl.textContent = "Ошибка сброса " + label;
            });
          });
        });
        tplScope.querySelectorAll(".tpl-v2-preview").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var name = btn.getAttribute("data-name");
            var ta = tplScope.querySelector('.tpl-v2-html[data-name="' + name + '"]');
            var pre = tplScope.querySelector('.tpl-v2-preview-out[data-name="' + name + '"]');
            fetch("/api/bot/notification-templates/preview", {
              method: "POST",
              credentials: "same-origin",
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken(),
                Accept: "application/json"
              },
              body: JSON.stringify({ name: name, body_html: ta ? ta.value : "" })
            }).then(function (resp) { return resp.json(); }).then(function (d) {
              if (pre) pre.textContent = (d && d.html) ? String(d.html) : "";
            }).catch(function () {
              if (pre) pre.textContent = "Ошибка предпросмотра";
            });
          });
        });
        statusEl.textContent = "";
      }).catch(function () {
        statusEl.textContent = "Не удалось загрузить шаблоны v2.";
      });
    }

    window.addEventListener("via-settings-tab", function (ev) {
      if (ev.detail && ev.detail.tab === "notifications") loadV2();
    });
    if (window.location.hash === "#notifications") loadV2();
  })();
})();