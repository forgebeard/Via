/**
 * Универсальный редактор справочника (drag-and-drop, inline edit, delete).
 *
 * createCatalogEditor({
 *   kind:       "notify" | "simple",
 *   listId:     "notify-list",
 *   addInputId: "notify-add-input",
 *   addBtnId:   "notify-add",
 *   hiddenId:   "catalog_notify_json",
 *   onSync:     function() {}          // вызывается после каждого изменения
 * })
 */
function createCatalogEditor(cfg) {
  var container = document.getElementById(cfg.listId);
  var addInput  = document.getElementById(cfg.addInputId);
  var addBtn    = document.getElementById(cfg.addBtnId);
  var hidden    = document.getElementById(cfg.hiddenId);
  if (!container || !addInput || !addBtn || !hidden) return;

  var list = _ceJsonSafe(hidden.value, []);
  var dragIndex = -1;
  var pendingDeleteIndex = -1;
  var editIndex = -1;
  var editValue = "";

  function readLabel(item) {
    return cfg.kind === "notify"
      ? String((item || {}).label || "")
      : String(item || "");
  }

  function writeItem(label, prev) {
    if (cfg.kind === "notify") {
      var used = new Set(list.map(function (it) { return String((it || {}).key || ""); }));
      if (prev && prev.key) used.delete(prev.key);
      return { key: (prev && prev.key) || _ceSlugify(label, used), label: label };
    }
    return label;
  }

  function sync(shouldPersist) {
    hidden.value = JSON.stringify(list);
    render();
    if (shouldPersist && typeof cfg.onSync === "function") cfg.onSync();
  }

  function commitAdd() {
    var value = String(addInput.value || "").trim();
    if (!value) return;
    list.push(writeItem(value, null));
    addInput.value = "";
    sync(true);
  }

  function saveEdit(index, prevItem) {
    var next = String(editValue || "").trim();
    if (!next) return;
    list[index] = writeItem(next, prevItem);
    editIndex = -1;
    editValue = "";
    sync(true);
  }

  function cancelEdit() {
    editIndex = -1;
    editValue = "";
    render();
  }

  function render() {
    container.innerHTML = "";
    list.forEach(function (item, index) {
      var label = readLabel(item);
      var row = document.createElement("div");
      row.className = "catalog-item";
      row.draggable = true;

      var content = document.createElement("div");
      content.className = "catalog-item__content";

      if (editIndex === index) {
        var editInput = document.createElement("input");
        editInput.type = "text";
        editInput.className = "catalog-item__input";
        editInput.value = editValue || label;
        editInput.addEventListener("input", function () { editValue = editInput.value; });
        editInput.addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); saveEdit(index, item); }
          else if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
        });
        content.appendChild(editInput);
        requestAnimationFrame(function () { editInput.focus(); editInput.select(); });
      } else {
        var text = document.createElement("span");
        text.className = "catalog-item__text";
        text.textContent = label;
        content.appendChild(text);
      }

      var actions = document.createElement("div");
      actions.className = "catalog-item__actions";

      if (editIndex === index) {
        actions.innerHTML =
          '<button type="button" class="btn btn-primary btn-small">Сохранить</button>' +
          '<button type="button" class="btn btn-ghost btn-small">Отмена</button>';
        actions.children[0].addEventListener("click", function () { saveEdit(index, item); });
        actions.children[1].addEventListener("click", cancelEdit);
      } else if (pendingDeleteIndex === index) {
        actions.innerHTML =
          '<button type="button" class="btn btn-danger btn-small">Удалить?</button>' +
          '<button type="button" class="btn btn-ghost btn-small">Отмена</button>';
        actions.children[0].addEventListener("click", function () {
          list.splice(index, 1);
          pendingDeleteIndex = -1;
          sync(true);
        });
        actions.children[1].addEventListener("click", function () {
          pendingDeleteIndex = -1;
          render();
        });
      } else {
        actions.innerHTML =
          '<button type="button" class="btn btn-ghost btn-small" title="Редактировать">✎</button>' +
          '<button type="button" class="btn btn-danger btn-small" title="Удалить">✕</button>';
        actions.children[0].addEventListener("click", function () {
          pendingDeleteIndex = -1;
          editIndex = index;
          editValue = label;
          render();
        });
        actions.children[1].addEventListener("click", function () {
          editIndex = -1;
          pendingDeleteIndex = index;
          render();
        });
      }

      row.appendChild(content);
      row.appendChild(actions);

      row.addEventListener("dragstart", function () { dragIndex = index; row.classList.add("is-drag"); });
      row.addEventListener("dragend", function () { row.classList.remove("is-drag"); dragIndex = -1; });
      row.addEventListener("dragover", function (e) { e.preventDefault(); });
      row.addEventListener("drop", function (e) {
        e.preventDefault();
        if (dragIndex < 0 || dragIndex >= list.length || dragIndex === index) return;
        var moved = list.splice(dragIndex, 1)[0];
        list.splice(index, 0, moved);
        pendingDeleteIndex = -1;
        editIndex = -1;
        sync(true);
      });

      container.appendChild(row);
    });
  }

  addBtn.addEventListener("click", commitAdd);
  addInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); commitAdd(); }
  });
  sync(false);
}

/* --- internal helpers --- */
function _ceJsonSafe(value, fallback) {
  try {
    var parsed = JSON.parse(value || "");
    return Array.isArray(parsed) ? parsed : fallback;
  } catch (e) { return fallback; }
}

function _ceSlugify(label, used) {
  var base = String(label || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  if (!base) base = "opt";
  var key = base;
  var i = 2;
  while (used.has(key)) { key = base + "_" + i; i += 1; }
  return key;
}