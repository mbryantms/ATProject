(function () {
  const SCROLL_OFFSET = 80; // px
  const SUPPRESS_MS = 400; // how long to hide hover UI for headers

  // Helper: smooth-scroll to a hash target with offset
  function smoothScrollToHash(hash) {
    if (!hash || !hash.startsWith('#')) return;
    const el = document.getElementById(hash.slice(1));
    if (!el) return;

    const y = el.getBoundingClientRect().top + window.pageYOffset - SCROLL_OFFSET;
    window.scrollTo({ top: y, behavior: 'smooth' });

    // Update the URL hash without causing a jump
    history.replaceState(null, '', hash);
  }

  // Helper: copy absolute URL of the hash to clipboard, with fallback
  function copyLink(hash, feedbackEl) {
    const url = new URL(hash, window.location.href).toString();

    function showFeedback() {
      if (feedbackEl) {
        feedbackEl.classList.add('clicked');
        setTimeout(() => feedbackEl.classList.remove('clicked'), 220);
      }
    }

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(showFeedback, () => {
        fallbackCopy(url);
        showFeedback();
      });
    } else {
      fallbackCopy(url);
      showFeedback();
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch (e) {
      console.error('Failed to copy link:', e);
    }
    document.body.removeChild(ta);
  }

  // Helper: temporarily suppress header hover UI after interaction
  function suppressHoverUI(ms = SUPPRESS_MS) {
    const root = document.documentElement;
    root.classList.add('suppress-header-hover');
    setTimeout(() => root.classList.remove('suppress-header-hover'), ms);
  }

  // Delegate clicks on heading elements
  document.addEventListener(
    'click',
    function (e) {
      // Handle copy-section-link button clicks
      const btn = e.target.closest('.copy-section-link-button');
      if (btn) {
        e.preventDefault();
        e.stopPropagation();
        const heading = btn.closest('.heading');
        const anchor = heading?.querySelector('a[href^="#"]');
        const hash = anchor?.getAttribute('href') || '';
        if (hash) copyLink(hash, btn);
        return;
      }

      // Handle heading anchor clicks (smooth scroll)
      const heading = e.target.closest('.heading');
      if (!heading) return;
      const anchor = e.target.closest('a[href^="#"]');
      if (!anchor || !heading.contains(anchor)) return;

      e.preventDefault();
      suppressHoverUI();
      smoothScrollToHash(anchor.getAttribute('href'));
      anchor.blur?.();
    },
    { passive: false },
  );

  // Handle page load with a hash (smooth scroll into view)
  if (location.hash) {
    window.addEventListener('load', () => smoothScrollToHash(location.hash));
  }
})();
