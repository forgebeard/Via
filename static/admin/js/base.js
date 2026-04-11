(function () {
  // --- Theme Toggle ---
  var html = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  var icon = document.getElementById("theme-icon");
  var STORAGE_KEY = "via-admin-theme";

  function applyTheme(theme) {
    if (theme === "light") {
      html.classList.add("theme-light");
      if (icon) {
        icon.className = "fa-solid fa-sun";
      }
    } else {
      html.classList.remove("theme-light");
      if (icon) {
        icon.className = "fa-solid fa-moon";
      }
    }
  }

  var savedTheme = localStorage.getItem(STORAGE_KEY);
  if (savedTheme) {
    applyTheme(savedTheme);
  }

  if (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var isLight = html.classList.contains("theme-light");
      var newTheme = isLight ? "dark" : "light";
      localStorage.setItem(STORAGE_KEY, newTheme);
      applyTheme(newTheme);
    });
  }

  // --- HTMX CSRF ---
  document.body.addEventListener("htmx:configRequest", function (event) {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      event.detail.headers["X-CSRF-Token"] = meta.content;
    }
  });

  // --- Sidebar ---
  var sidebar = document.getElementById("app-sidebar");
  var backdrop = document.getElementById("sidebar-backdrop");
  var toggle = document.getElementById("sidebar-toggle");

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("show");
  }
  function openSidebar() {
    if (sidebar) sidebar.classList.add("open");
    if (backdrop) backdrop.classList.add("show");
  }

  if (toggle && sidebar && backdrop) {
    toggle.addEventListener("click", function () {
      if (sidebar.classList.contains("open")) closeSidebar();
      else openSidebar();
    });
    backdrop.addEventListener("click", closeSidebar);
  }

  // --- User dropdown menu ---
  var ut = document.getElementById("user-trigger");
  var dd = document.getElementById("user-dropdown");
  var uw = document.getElementById("user-menu-wrap");

  if (ut && dd && uw) {
    function menuItems() {
      return Array.prototype.slice.call(dd.querySelectorAll('a[role="menuitem"]'));
    }
    function openUserMenu() {
      dd.classList.add("open");
      ut.setAttribute("aria-expanded", "true");
      var items = menuItems();
      if (items.length) {
        requestAnimationFrame(function () { items[0].focus(); });
      }
    }
    function closeUserMenu(focusTrigger) {
      dd.classList.remove("open");
      ut.setAttribute("aria-expanded", "false");
      if (focusTrigger) ut.focus();
    }
    function toggleUserMenu(e) {
      e.stopPropagation();
      if (dd.classList.contains("open")) closeUserMenu(true);
      else openUserMenu();
    }

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (dd.classList.contains("open")) {
        e.preventDefault();
        closeUserMenu(true);
        return;
      }
      closeSidebar();
    });

    ut.addEventListener("click", toggleUserMenu);
    ut.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleUserMenu(e);
        return;
      }
      if (!dd.classList.contains("open")) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          openUserMenu();
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        menuItems()[0].focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        var its = menuItems();
        if (its.length) its[its.length - 1].focus();
      }
    });

    dd.addEventListener("keydown", function (e) {
      var items = menuItems();
      if (!items.length) return;
      var i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        items[i < 0 ? 0 : (i + 1) % items.length].focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        items[i < 0 ? items.length - 1 : (i - 1 + items.length) % items.length].focus();
      } else if (e.key === "Home") {
        e.preventDefault();
        items[0].focus();
      } else if (e.key === "End") {
        e.preventDefault();
        items[items.length - 1].focus();
      }
    });

    document.addEventListener("click", function () {
      if (!dd.classList.contains("open")) return;
      var focusInside = dd.contains(document.activeElement);
      closeUserMenu(false);
      if (focusInside) ut.focus();
    });

    uw.addEventListener("click", function (e) { e.stopPropagation(); });
  } else {
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSidebar();
    });
  }
})();