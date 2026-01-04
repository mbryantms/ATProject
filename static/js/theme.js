/**
 * Theme management module
 * Handles three-way toggle: auto/light/dark
 */

const Theme = {
  STORAGE_KEY: 'architextual-theme',
  VALID_THEMES: ['auto', 'light', 'dark'],

  /**
   * Get current theme from localStorage
   * @returns {string} 'auto', 'light', or 'dark'
   */
  get() {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      return this.VALID_THEMES.includes(stored) ? stored : 'auto';
    } catch (e) {
      return 'auto';
    }
  },

  /**
   * Set theme and update DOM
   * @param {string} theme - 'auto', 'light', or 'dark'
   */
  set(theme) {
    if (!this.VALID_THEMES.includes(theme)) {
      theme = 'auto';
    }
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(this.STORAGE_KEY, theme);
    } catch (e) {
      // localStorage not available
    }

    // Update color-scheme meta tag for native controls
    this.updateColorSchemeMeta(theme);
  },

  /**
   * Update the color-scheme meta tag
   * @param {string} theme - Current theme setting
   */
  updateColorSchemeMeta(theme) {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const colorScheme = theme === 'dark' ? 'dark' :
                        theme === 'light' ? 'light' :
                        (prefersDark ? 'dark' : 'light');

    let meta = document.querySelector('meta[name="color-scheme"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'color-scheme';
      document.head.appendChild(meta);
    }
    meta.content = colorScheme;
  },

  /**
   * Cycle through themes: auto -> light -> dark -> auto
   * @returns {string} The new theme
   */
  cycle() {
    const current = this.get();
    const nextIndex = (this.VALID_THEMES.indexOf(current) + 1) % this.VALID_THEMES.length;
    const next = this.VALID_THEMES[nextIndex];
    this.set(next);
    return next;
  },

  /**
   * Initialize theme system
   * - Sets up system preference change listener
   * - Binds toggle buttons
   */
  init() {
    // Listen for system preference changes (affects auto mode)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (this.get() === 'auto') {
        // Re-apply to update color-scheme meta
        this.set('auto');
      }
    });

    // Bind toggle buttons
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      btn.addEventListener('click', () => this.cycle());
    });
  }
};

// Initialize on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => Theme.init());
} else {
  Theme.init();
}

export default Theme;
