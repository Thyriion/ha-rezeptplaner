/* Theme adapter: reads the active Home Assistant theme variables from the
   parent window and writes them as --rp-ha-* custom properties on this
   iFrame's <html> element. Galaxy fallbacks are used when the parent is
   inaccessible or a value is missing. */
(function () {
  const root = document.documentElement;

  const REPLACEMENTS = {
    'primary-background-color': '#0d0e14',
    'secondary-background-color': '#1e2030',
  };

  const VARS = [
    { key: 'primary-background', sources: ['primary-background-color'], fallback: '#0d0e14', replaceTransparent: true },
    { key: 'secondary-background', sources: ['secondary-background-color'], fallback: '#1e2030', replaceTransparent: true },
    { key: 'card-background', sources: ['card-background-color', 'ha-card-background'], fallback: 'rgba(30, 32, 48, 0.75)' },
    { key: 'primary-color', sources: ['primary-color'], fallback: '#0b9e9e' },
    { key: 'accent-color', sources: ['accent-color'], fallback: '#9b7abf' },
    { key: 'primary-text', sources: ['primary-text-color'], fallback: '#e8eaf6' },
    { key: 'secondary-text', sources: ['secondary-text-color'], fallback: '#7a8aaa' },
    { key: 'disabled-text', sources: ['disabled-text-color'], fallback: '#2a3a4a' },
    { key: 'divider', sources: ['divider-color'], fallback: 'rgba(255,255,255,0.06)' },
    { key: 'success', sources: ['success-color'], fallback: '#0b9e9e' },
    { key: 'warning', sources: ['warning-color'], fallback: '#c8843a' },
    { key: 'error', sources: ['error-color'], fallback: '#9b3a3a' },
    { key: 'card-radius', sources: ['ha-card-border-radius'], fallback: '14px' },
    { key: 'card-shadow', sources: ['ha-card-box-shadow'], fallback: '0 4px 24px rgba(0,0,0,0.5)' },
  ];

  function pickValue(parentStyle, sources) {
    for (const source of sources) {
      const value = parentStyle.getPropertyValue('--' + source).trim();
      if (value) return value;
    }
    return '';
  }

  function normalize(entry, raw) {
    if (!raw) return entry.fallback;
    if (entry.replaceTransparent && raw.trim() === 'transparent') {
      return REPLACEMENTS[entry.sources[0]] || entry.fallback;
    }
    return raw.trim();
  }

  function applyFallbacks() {
    for (const entry of VARS) {
      root.style.setProperty('--rp-ha-' + entry.key, entry.fallback);
    }
  }

  function readFromParents(entry) {
    const parentDoc = window.parent.document;
    const roots = [
      parentDoc.documentElement,
      parentDoc.body,
      parentDoc.querySelector('home-assistant'),
    ].filter(Boolean);
    for (const parentRoot of roots) {
      const value = pickValue(window.parent.getComputedStyle(parentRoot), entry.sources);
      if (value) return value;
    }
    return '';
  }

  try {
    for (const entry of VARS) {
      const raw = readFromParents(entry);
      root.style.setProperty('--rp-ha-' + entry.key, normalize(entry, raw));
    }
  } catch (err) {
    // Parent window is inaccessible (cross-origin, direct access, etc.).
    applyFallbacks();
  }
})();
