/* IMSERV - Theme Manager */
(function () {
  const html = document.documentElement;
  const themeVersion = 'imserv-json-theme-v1';
  if (localStorage.getItem('imserv-theme-version') !== themeVersion) {
    localStorage.setItem('imserv-theme', 'light');
    localStorage.setItem('imserv-theme-version', themeVersion);
  }
  const stored = localStorage.getItem('imserv-theme') || 'light';
  html.setAttribute('data-theme', stored);

  window.toggleTheme = function () {
    const current = html.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('imserv-theme', next);
    window.IMSERV?.applyChartTheme?.(next);

    const icon = document.getElementById('theme-icon');
    if (icon && window.IMSERV?.setElementIcon) {
      delete icon.dataset.iconReady;
      IMSERV.setElementIcon(icon, next === 'dark' ? 'moon' : 'sun');
    } else if (icon) {
      icon.textContent = next === 'dark' ? 'Dark' : 'Light';
    }
  };
})();
