(function () {
  const SCROLL_OFFSET = 80; // px
  const SUPPRESS_MS = 400;  // how long to hide hover UI for headers

  // Helper: smooth-scroll to a hash target with offset
  function smoothScrollToHash(hash) {
    if (!hash || !hash.startsWith('#')) return;
    const el = document.getElementById(hash.slice(1));
    if (!el) return;

    const y = el.getBoundingClientRect().top + window.pageYOffset - SCROLL_OFFSET;
    window.scrollTo({top: y, behavior: 'smooth'});

    // Update the URL hash without causing a jump
    history.replaceState(null, '', hash);
  }

  // Helper: copy absolute URL of the hash to clipboard
  function copyLink(hash, iconEl) {
    const url = new URL(hash, window.location.href).toString();
    (navigator.clipboard?.writeText?.(url) ?? Promise.reject())
      .catch(() => {
        // Fallback for browsers without clipboard API
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand('copy');
        } catch (e) {
          // Log error if copy fails
          console.error("Failed to copy link using fallback:", e);
        }
        document.body.removeChild(ta);
      })
      .finally(() => {
        // Flip animation feedback
        if (iconEl) {
          iconEl.classList.add('copied');
          setTimeout(() => iconEl.classList.remove('copied'), 220);
        }
      });
  }

  // Helper: temporarily suppress header hover UI after interaction
  function suppressHoverUI(ms = SUPPRESS_MS) {
    const root = document.documentElement;
    root.classList.add('suppress-header-hover');
    setTimeout(() => root.classList.remove('suppress-header-hover'), ms);
  }

  // 1) Inject a real clickable icon element into each anchor
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('a.anchor-link.header-anchor').forEach(a => {
      // Avoid duplicating if re-run (e.g., via Turbolinks/HTMX)
      if (!a.querySelector('.hdr-link-icon')) {
        const icon = document.createElement('span');
        icon.className = 'hdr-link-icon';
        icon.setAttribute('aria-hidden', 'true');
        a.appendChild(icon);
      }
    });
  });


  // 2) Delegate clicks for anchor links
  document.addEventListener('click', function (e) {
    const a = e.target.closest('a.anchor-link.header-anchor');
    if (!a) return;

    const hash = a.getAttribute('href') || '';
    const icon = e.target.closest('.hdr-link-icon'); // Check if the icon itself was clicked

    if (icon) {
      // If clicking the icon -> copy link
      e.preventDefault();
      e.stopPropagation(); // Prevent default anchor behavior and parent listeners
      copyLink(hash, icon);
      return;
    }

    // Otherwise clicking the header/anchor text -> smooth scroll
    e.preventDefault();
    suppressHoverUI(); // Briefly hide hover UI
    smoothScrollToHash(hash);
    a.blur?.(); // Remove focus-within styles, if any
  }, {passive: false});

  // 3) Handle page load with a hash (smooth scroll into view)
  if (location.hash) {
    // Delay to allow layout to settle (fonts, images)
    window.addEventListener('load', () => smoothScrollToHash(location.hash));
  }
})();
