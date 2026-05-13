(function () {
  /* --- Ops flash auto-dismiss --- */
  var flash = document.getElementById("ops-flash");
  if (flash) {
    setTimeout(function () {
      flash.classList.add("ops-flash--dismissed");
      setTimeout(function () { flash.remove(); }, 400);
    }, 10000);
  }
})();