(() => {
  const TAB_ID = "tab-rules";
  const PROTECTED_AXES = new Set(["status", "version", "priority"]);
  const FLOATING_PANEL_ATTR = "data-routing-rules-floating-panel";
  const PANEL_MARGIN = 6;
  const VIEWPORT_PADDING = 8;
  const MIN_PANEL_HEIGHT = 120;
  const MAX_PANEL_HEIGHT = 320;
  const panelByWrapper = new WeakMap();
  let openWrapper = null;
  let repositionRaf = null;

  function formIdFromGroup(group) {
    const fid = (group.getAttribute("data-for-form") || "").trim();
    return fid || null;
  }

  function wireSelectToForm(select, formId) {
    if (formId) {
      select.setAttribute("form", formId);
    } else {
      select.removeAttribute("form");
    }
  }

  function cloneSlot(axis) {
    const tpl = document.getElementById(`routing-rules-tpl-${axis}`);
    if (!tpl || !tpl.content) return null;
    return tpl.content.firstElementChild ? tpl.content.firstElementChild.cloneNode(true) : null;
  }

  function cleanEmptySelects(form) {
    const fid = form.id || "";
    const q = "select.routing-rules__axis-select";
    const inside = form.querySelectorAll(q);
    const linked = fid
      ? document.querySelectorAll(`${q}[form="${fid.replace(/"/g, "")}"]`)
      : [];
    const seen = new Set();
    [...inside, ...linked].forEach((sel) => {
      if (seen.has(sel)) return;
      seen.add(sel);
      if (!sel.dataset.axisName) {
        sel.dataset.axisName = sel.name || "";
      }
      const original = sel.dataset.axisName;
      if (!original) return;
      if ((sel.value || "").trim() === "") {
        sel.removeAttribute("name");
      } else {
        sel.setAttribute("name", original);
      }
    });
  }

  function bindForms(tab) {
    tab.querySelectorAll("form.routing-rules__policy-form").forEach((form) => {
      if (form.dataset.routingRulesBound === "1") return;
      form.dataset.routingRulesBound = "1";
      form.addEventListener(
        "submit",
        () => cleanEmptySelects(form),
        { capture: true },
      );
    });
  }

  function selectedOptionText(select) {
    const opt = select.options[select.selectedIndex];
    if (!opt) return "";
    return (opt.textContent || "").trim();
  }

  function updateTriggerLabel(wrapper) {
    const sel = wrapper.querySelector("select");
    const label = wrapper.querySelector(".routing-rules__dd-label");
    if (!sel || !label) return;
    label.textContent = selectedOptionText(sel) || "—";
  }

  function getClauseGroup(select) {
    return select ? select.closest(".routing-rules__clause-group") : null;
  }

  function getTakenValues(group, exceptSelect) {
    const taken = new Set();
    if (!group) return taken;
    group.querySelectorAll(".routing-rules__slots select.routing-rules__axis-select").forEach((sel) => {
      if (sel === exceptSelect) return;
      const value = (sel.value || "").trim();
      if (value) taken.add(value);
    });
    return taken;
  }

  function scheduleReposition() {
    if (repositionRaf !== null) return;
    repositionRaf = window.requestAnimationFrame(() => {
      repositionRaf = null;
      positionOpenPanel();
    });
  }

  function positionOpenPanel() {
    if (!openWrapper) return;
    const panel = panelByWrapper.get(openWrapper);
    const trigger = openWrapper.querySelector(".routing-rules__dd-trigger");
    if (!panel || !trigger) return;
    const rect = trigger.getBoundingClientRect();

    const maxWidth = Math.max(220, window.innerWidth - VIEWPORT_PADDING * 2);
    panel.style.minWidth = `${Math.round(rect.width)}px`;
    panel.style.maxWidth = `${Math.round(maxWidth)}px`;
    panel.style.width = "max-content";

    const panelWidth = Math.min(panel.offsetWidth || rect.width, maxWidth);
    const left = Math.max(
      VIEWPORT_PADDING,
      Math.min(rect.left, window.innerWidth - panelWidth - VIEWPORT_PADDING),
    );

    const availableBelow = Math.max(0, window.innerHeight - rect.bottom - PANEL_MARGIN - VIEWPORT_PADDING);
    const availableAbove = Math.max(0, rect.top - PANEL_MARGIN - VIEWPORT_PADDING);
    const openUp = availableBelow < MIN_PANEL_HEIGHT && availableAbove > availableBelow;
    const space = openUp ? availableAbove : availableBelow;
    const panelHeight = Math.max(MIN_PANEL_HEIGHT, Math.min(MAX_PANEL_HEIGHT, space || MAX_PANEL_HEIGHT));
    panel.style.maxHeight = `${Math.round(panelHeight)}px`;

    const measuredHeight = Math.min(panel.scrollHeight + 2, panelHeight);
    const top = openUp
      ? Math.max(VIEWPORT_PADDING, rect.top - measuredHeight - PANEL_MARGIN)
      : Math.min(window.innerHeight - measuredHeight - VIEWPORT_PADDING, rect.bottom + PANEL_MARGIN);

    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
  }

  function refreshOpenPanelsInGroup(group) {
    if (!group) return;
    group.querySelectorAll(".routing-rules__dd.is-open").forEach((wrapper) => {
      const oldPanel = panelByWrapper.get(wrapper);
      if (oldPanel) oldPanel.remove();
      const panel = buildPanel(wrapper);
      if (!panel) return;
      panelByWrapper.set(wrapper, panel);
      document.body.appendChild(panel);
      openWrapper = wrapper;
      scheduleReposition();
    });
  }

  function closeDropdown(wrapper) {
    if (!wrapper) return;
    wrapper.classList.remove("is-open");
    const trigger = wrapper.querySelector(".routing-rules__dd-trigger");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    const panel = panelByWrapper.get(wrapper) || wrapper.querySelector(".routing-rules__dd-panel");
    if (panel) panel.remove();
    panelByWrapper.delete(wrapper);
    if (openWrapper === wrapper) openWrapper = null;
  }

  function closeAllPanels(except) {
    document.querySelectorAll(".routing-rules__dd").forEach((w) => {
      if (w === except) return;
      closeDropdown(w);
    });
  }

  function buildPanel(wrapper) {
    const sel = wrapper.querySelector("select");
    if (!sel) return null;
    const panel = document.createElement("div");
    panel.className = "routing-rules__dd-panel routing-rules__dd-panel--floating";
    panel.setAttribute("role", "listbox");
    panel.setAttribute(FLOATING_PANEL_ATTR, "1");
    const group = getClauseGroup(sel);
    const taken = sel.classList.contains("routing-rules__axis-select")
      ? getTakenValues(group, sel)
      : new Set();
    Array.from(sel.options).forEach((opt, idx) => {
      const value = (opt.value || "").trim();
      if (value && taken.has(value) && value !== (sel.value || "").trim()) return;
      const item = document.createElement("button");
      item.type = "button";
      item.className = "routing-rules__dd-item";
      item.setAttribute("role", "option");
      item.dataset.value = opt.value;
      item.textContent = (opt.textContent || "").trim();
      if (idx === sel.selectedIndex) item.classList.add("is-selected");
      item.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        updateTriggerLabel(wrapper);
        closeDropdown(wrapper);
        refreshOpenPanelsInGroup(group);
      });
      panel.appendChild(item);
    });
    return panel;
  }

  function mountCustomSelect(sel) {
    if (!sel || sel.dataset.routingRulesDd === "1") return;
    sel.dataset.routingRulesDd = "1";
    const wrapper = document.createElement("span");
    wrapper.className = "routing-rules__dd";
    sel.parentNode.insertBefore(wrapper, sel);
    wrapper.appendChild(sel);

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "routing-rules__dd-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute(
      "aria-label",
      sel.getAttribute("aria-label") || "Выбор значения",
    );

    const labelSpan = document.createElement("span");
    labelSpan.className = "routing-rules__dd-label";
    labelSpan.textContent = selectedOptionText(sel) || "—";
    trigger.appendChild(labelSpan);

    const chevron = document.createElement("span");
    chevron.className = "routing-rules__dd-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "▾";
    trigger.appendChild(chevron);

    wrapper.appendChild(trigger);

    trigger.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const isOpen = wrapper.classList.contains("is-open");
      closeAllPanels(wrapper);
      if (isOpen) {
        closeDropdown(wrapper);
        return;
      }
      const panel = buildPanel(wrapper);
      if (!panel) return;
      panelByWrapper.set(wrapper, panel);
      document.body.appendChild(panel);
      wrapper.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      openWrapper = wrapper;
      scheduleReposition();
    });

    sel.addEventListener("change", () => {
      updateTriggerLabel(wrapper);
      refreshOpenPanelsInGroup(getClauseGroup(sel));
    });
  }

  function mountAllInTab(tab) {
    tab
      .querySelectorAll("select.routing-rules__axis-select, select.routing-rules__notify-select")
      .forEach((sel) => mountCustomSelect(sel));
  }

  function ensureSlotInGroup(group) {
    const slots = group.querySelector(".routing-rules__slots");
    if (!slots) return;
    if (slots.querySelector(".routing-rules__slot")) return;
    const axis = (group.getAttribute("data-axis") || "").trim();
    if (!axis) return;
    const node = cloneSlot(axis);
    if (!node) return;
    const formId = formIdFromGroup(group);
    const sel = node.querySelector("select");
    if (sel) wireSelectToForm(sel, formId);
    slots.appendChild(node);
    if (sel) mountCustomSelect(sel);
    refreshOpenPanelsInGroup(group);
  }

  function onAddClick(tab, ev) {
    const btn = ev.target.closest(".routing-rules__add-slot");
    if (!btn || !tab.contains(btn)) return;
    ev.preventDefault();
    const axis = btn.getAttribute("data-axis");
    if (!axis) return;
    const group = btn.closest(".routing-rules__clause-group");
    if (!group) return;
    const slots = group.querySelector(".routing-rules__slots");
    if (!slots) return;
    const node = cloneSlot(axis);
    if (!node) return;
    const formId = formIdFromGroup(group);
    const sel = node.querySelector("select");
    if (sel) wireSelectToForm(sel, formId);
    slots.appendChild(node);
    if (sel) mountCustomSelect(sel);
    refreshOpenPanelsInGroup(group);
  }

  function onRemoveClick(tab, ev) {
    const btn = ev.target.closest(".routing-rules__rm");
    if (!btn || !tab.contains(btn)) return;
    ev.preventDefault();
    const slot = btn.closest(".routing-rules__slot");
    if (!slot || !tab.contains(slot)) return;
    const group = slot.closest(".routing-rules__clause-group");
    slot.remove();
    if (group && PROTECTED_AXES.has((group.getAttribute("data-axis") || "").trim())) {
      ensureSlotInGroup(group);
    }
    refreshOpenPanelsInGroup(group);
  }

  function onDocumentClick(ev) {
    if (ev.target.closest(".routing-rules__dd")) return;
    if (ev.target.closest(`[${FLOATING_PANEL_ATTR}]`)) return;
    closeAllPanels(null);
  }

  function bindInlineDeletes(tab) {
    if (typeof window.bindInlineDelete !== "function") return;
    tab.querySelectorAll("form[data-inline-delete-form]").forEach((form) => {
      if (form.dataset.routingRulesDeleteBound === "1") return;
      form.dataset.routingRulesDeleteBound = "1";
      window.bindInlineDelete(form, "правило");
    });
  }

  function init(tab) {
    if (!tab || tab.dataset.routingRulesInit === "1") return;
    tab.dataset.routingRulesInit = "1";
    bindForms(tab);
    mountAllInTab(tab);
    bindInlineDeletes(tab);
    tab.addEventListener("click", (ev) => {
      onAddClick(tab, ev);
      onRemoveClick(tab, ev);
    });
    document.addEventListener("click", onDocumentClick);
    window.addEventListener("scroll", scheduleReposition, true);
    window.addEventListener("resize", scheduleReposition);
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") closeAllPanels(null);
    });
  }

  function tryInit() {
    const tab = document.getElementById(TAB_ID);
    if (tab) init(tab);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryInit);
  } else {
    tryInit();
  }

  window.addEventListener("via-settings-tab", (ev) => {
    const detail = ev && ev.detail;
    if (detail && detail.tab === "rules") tryInit();
  });
})();
