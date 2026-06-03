/* SMJ - Theme Manager */
(function () {
  const html = document.documentElement;
  const themeVersion = 'SMJ-json-theme-v1';
  if (localStorage.getItem('SMJ-theme-version') !== themeVersion) {
    localStorage.setItem('SMJ-theme', 'dark');
    localStorage.setItem('SMJ-theme-version', themeVersion);
  }
  const stored = localStorage.getItem('SMJ-theme') || 'dark';
  html.setAttribute('data-theme', stored);

  window.toggleTheme = function () {
    const current = html.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('SMJ-theme', next);
    window.SMJ?.applyChartTheme?.(next);

    const icon = document.getElementById('theme-icon');
    if (icon && window.SMJ?.setElementIcon) {
      delete icon.dataset.iconReady;
      SMJ.setElementIcon(icon, next === 'dark' ? 'moon' : 'sun');
    } else if (icon) {
      icon.textContent = next === 'dark' ? 'Dark' : 'Light';
    }
  };
})();
