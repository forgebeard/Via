(function () {
  /* --- Ops flash auto-dismiss --- */
  var flash = document.getElementById("ops-flash");
  if (flash) {
    setTimeout(function () {
      flash.classList.add("ops-flash--dismissed");
      setTimeout(function () { flash.remove(); }, 400);
    }, 10000);
  }

  /* --- Bot status polling --- */
  var dot = document.getElementById("bot-status-dot");
  var text = document.getElementById("bot-status-text");

  if (dot && text) {
    function updateStatus(data) {
      dot.className = "bot-status-dot";
      if (data.status === "alive") {
        dot.classList.add("bot-status-dot--alive");
      } else if (data.status === "warning") {
        dot.classList.add("bot-status-dot--warning");
      } else if (data.status === "dead") {
        dot.classList.add("bot-status-dot--dead");
      } else {
        dot.classList.add("bot-status-dot--unknown");
      }
      text.textContent = data.message || "Неизвестно";
    }

    function fetchStatus() {
      fetch("/api/bot/status")
        .then(function (r) { return r.json(); })
        .then(updateStatus)
        .catch(function () {
          dot.className = "bot-status-dot bot-status-dot--unknown";
          text.textContent = "Не удалось загрузить статус";
        });
    }

    fetchStatus();
    setInterval(fetchStatus, 30000);
  }
})();