Reading Progress + Active Heading Breadcrumb Widget
Add a floating reading-progress widget to individual post pages. It displays the post title and a live breadcrumb of the current heading hierarchy as the user scrolls, with a thin progress bar.
Visual structure
Stacked layout:

Post title — centered, small caps, serif (matches existing post title styling).
Active H2 — left-aligned, indented one level.
Active H3 (if any) — left-aligned, indented two levels.
Active H4 (if any) — left-aligned, indented three levels.
Progress bar — thin (2–3px), full width of the widget, fills left-to-right as the user scrolls through the article body.

Only the heading levels present in the current section render. If the user is under an H2 with no active H3, only the title and H2 show. Transitions between states should be a subtle fade/slide — no jumpy reflows.
Behavior

Track scroll position through the article body only (from article start to end, excluding header/footer/comments).
Use IntersectionObserver on the article's H2/H3/H4 headings to determine the active hierarchy. When an H3 becomes active, its parent H2 remains shown above it. Same for H4 → H3 → H2.
Tune rootMargin so headings activate when near the top of the viewport (e.g., "-15% 0px -75% 0px").
Progress bar updates via requestAnimationFrame, throttled.
Widget appears once the user scrolls past the real (inline) post title, hides when they scroll past the end of the article.

Placement
Desktop — primary approach (open to change): fixed, top-center of viewport, below any sticky nav. Constrained max-width (roughly 600–720px). Subtle background (matches site background with slight elevation — soft shadow or hairline border), not a hard card.
Desktop — alternative to evaluate: floating widget pinned to the left of the main content column, vertically anchored (e.g., top third of viewport, fixed position). Only appears at the same breakpoint where sidenotes appear on this site — below that breakpoint it falls back to the mobile layout. Width sized to fit in the left margin alongside content without overlapping. Inspect the existing sidenote implementation to match its breakpoint and positioning conventions.
Pick whichever fits better after reviewing the site — flag the tradeoff in the integration notes rather than silently choosing.
Mobile: fixed to the bottom of the viewport, full width minus small side gutters, with safe-area inset padding for devices with home indicators. Same stacked layout but with tighter spacing and slightly smaller type. Progress bar sits at the top edge of the widget (closest to content) rather than the bottom, so it visually connects to the article above. Ensure it doesn't overlap tap targets or obscure the last line of content — add bottom padding to the article equal to the widget's height.
Styling

Match the site's existing theme: same serif for the title (small caps as shown), same body font for the headings, same text color hierarchy (active-most heading is darkest, ancestors slightly muted — or the reverse, whichever matches site conventions).
Progress bar uses the site's accent color; track is a faint neutral.
Respect light/dark mode.
Minimalist: no icons, no percentages, no numbers, no close button. The hierarchy and the bar are the entire UI.

Accessibility & robustness

Progress bar has role="progressbar" with aria-valuenow, aria-valuemin="0", aria-valuemax="100".
Widget is aria-hidden="true" — it's a visual aid; the real headings remain in the document flow for screen readers.
Respect prefers-reduced-motion: disable fade/slide transitions.
Progressive enhancement: if JS fails, widget never renders; the post is unaffected.
No new dependencies if avoidable. Match whatever the site already uses (vanilla JS or existing framework).

Deliverables

Component/module code.
Scoped CSS (avoid bleeding into the rest of the site).
Integration notes: where to mount, which selectors it depends on (article container, post title, heading levels, sidenote breakpoint if using the left-rail variant), and config knobs (rootMargin, hide/show thresholds, max-width, mobile widget height).
Before writing code, inspect the existing post template, sidenote component, and breakpoint conventions to confirm selectors and layout. Flag anything ambiguous — especially the desktop placement decision — rather than guessing.