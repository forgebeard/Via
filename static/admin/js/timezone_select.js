(function () {
  function initTimezoneSelect(config) {
    var zones = Array.isArray(config && config.zones) ? config.zones.slice() : [];
    var searchId = (config && config.searchId) || "";
    var selectId = (config && config.selectId) || "";
    var defaultLimit = Number((config && config.defaultLimit) || 30);
    var filterLimit = Number((config && config.filterLimit) || 50);
    var search = document.getElementById(searchId);
    var select = document.getElementById(selectId);
    if (!search || !select || !zones.length) return;

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function renderOptions(query) {
      var q = String(query || "").trim().toLowerCase();
      var currentValue = String(select.value || "").trim();
      var filtered = q
        ? zones.filter(function (zone) { return zone.toLowerCase().includes(q); }).slice(0, filterLimit)
        : zones.slice(0, defaultLimit);
      if (!filtered.length && currentValue) filtered = [currentValue];
      if (currentValue && filtered.indexOf(currentValue) < 0) filtered.unshift(currentValue);
      select.innerHTML = filtered
        .map(function (zone) {
          var selected = zone === currentValue ? " selected" : "";
          return '<option value="' + escapeHtml(zone) + '"' + selected + ">" + escapeHtml(zone) + "</option>";
        })
        .join("");
    }

    search.addEventListener("input", function () {
      renderOptions(search.value);
    });
    renderOptions("");
  }

  window.initTimezoneSelect = initTimezoneSelect;
})();
