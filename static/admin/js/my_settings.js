(function () {
  /* --- Notify preset toggle --- */
  initNotifyToggle('notify_custom_box');

  /* --- Timezone select --- */
  var container = document.getElementById('timezone-data');
  if (container) {
    try {
      var zones = JSON.parse(container.textContent);
      initTimezoneSelect({
        searchId: 'timezone_search_me',
        selectId: 'timezone_name',
        zones: zones,
        defaultLimit: 30,
        filterLimit: 50
      });
    } catch (e) {
      console.error('my_settings: failed to parse timezone data', e);
    }
  }
})();