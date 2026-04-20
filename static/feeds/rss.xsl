<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:atom="http://www.w3.org/2005/Atom"
                xmlns="http://www.w3.org/1999/xhtml">
  <xsl:output method="html"
              doctype-system="about:legacy-compat"
              encoding="UTF-8"
              indent="yes"/>

  <xsl:template match="/rss">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="channel/title"/> — Web feed</title>
        <meta name="robots" content="noindex"/>
        <style>
          <xsl:call-template name="feed-css"/>
        </style>
      </head>
      <body>
        <main class="feed-shell">
          <header class="feed-head">
            <p class="feed-kicker">
              <span class="feed-icon" aria-hidden="true">&#x1F4E1;</span>
              Web feed · RSS 2.0
            </p>
            <h1><xsl:value-of select="channel/title"/></h1>
            <p class="feed-desc"><xsl:value-of select="channel/description"/></p>
          </header>

          <section class="feed-card">
            <h2>Subscribe to this feed</h2>
            <p>
              This page is an RSS feed. Paste its URL into a feed reader
              (Feedly, NetNewsWire, Inoreader, Miniflux, or any app that
              understands RSS) and new posts will appear there automatically.
            </p>
            <div class="feed-url-row">
              <code class="feed-url" id="feed-url"><xsl:value-of select="channel/atom:link[@rel='self']/@href"/></code>
              <button type="button" class="feed-copy" id="feed-copy">Copy URL</button>
            </div>
            <p class="feed-browse">
              Looking for other feeds? See <a href="/feeds/">all feeds on this site</a>.
            </p>
          </section>

          <section class="feed-items">
            <h2>Recent items (<xsl:value-of select="count(channel/item)"/>)</h2>
            <ul>
              <xsl:for-each select="channel/item">
                <li class="feed-item">
                  <a class="feed-item__title" href="{link}">
                    <xsl:value-of select="title"/>
                  </a>
                  <p class="feed-item__meta">
                    <time><xsl:value-of select="pubDate"/></time>
                  </p>
                </li>
              </xsl:for-each>
            </ul>
          </section>

          <footer class="feed-foot">
            <p>
              <a href="{channel/link}">&#x2190; Back to <xsl:value-of select="channel/title"/></a>
            </p>
          </footer>
        </main>

        <script>
          (function () {
            var btn = document.getElementById('feed-copy');
            var code = document.getElementById('feed-url');
            if (!btn || !code) return;
            var url = code.textContent || window.location.href;
            btn.addEventListener('click', function () {
              if (navigator.clipboard &amp;&amp; navigator.clipboard.writeText) {
                navigator.clipboard.writeText(url).then(function () { flash(btn); });
              } else {
                var range = document.createRange();
                range.selectNode(code);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
                try { document.execCommand('copy'); flash(btn); } catch (e) {}
                window.getSelection().removeAllRanges();
              }
            });
            function flash(b) {
              var orig = b.textContent;
              b.textContent = 'Copied!';
              setTimeout(function () { b.textContent = orig; }, 1500);
            }
          })();
        </script>
      </body>
    </html>
  </xsl:template>

  <xsl:template name="feed-css">
    :root {
      --fg: #1a1a1a;
      --fg-muted: #555;
      --bg: #fafafa;
      --card: #ffffff;
      --hair: #e4e4e4;
      --accent: #b24d00;
      --link: #0a58ca;
      --link-hover: #083c8c;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --fg: #e8e8e8;
        --fg-muted: #a0a0a0;
        --bg: #161616;
        --card: #1e1e1e;
        --hair: #333;
        --accent: #ff8a34;
        --link: #8ab4f8;
        --link-hover: #b3ceff;
      }
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; line-height: 1.55; }
    a { color: var(--link); text-decoration: none; }
    a:hover { color: var(--link-hover); text-decoration: underline; }
    .feed-shell { max-width: 720px; margin: 2.5rem auto 4rem; padding: 0 1.25rem; }
    .feed-head { border-bottom: 1px solid var(--hair); padding-bottom: 1.25rem; margin-bottom: 1.5rem; }
    .feed-kicker { margin: 0 0 0.5rem; color: var(--accent); font-size: 0.8rem; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600; }
    .feed-icon { margin-right: 0.25rem; }
    .feed-head h1 { margin: 0 0 0.5rem; font-size: 1.9rem; line-height: 1.15; color: var(--fg); }
    .feed-desc { margin: 0; color: var(--fg-muted); }
    .feed-card { background: var(--card); border: 1px solid var(--hair); border-left: 4px solid var(--accent); border-radius: 6px; padding: 1.25rem 1.5rem; margin-bottom: 2rem; }
    .feed-card h2 { margin: 0 0 0.5rem; font-size: 1.05rem; }
    .feed-card p { margin: 0 0 1rem; color: var(--fg-muted); }
    .feed-url-row { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; }
    .feed-url { flex: 1 1 auto; min-width: 0; overflow-x: auto; white-space: nowrap; background: var(--bg); border: 1px solid var(--hair); padding: 0.4rem 0.6rem; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; color: var(--fg); }
    .feed-copy { background: var(--accent); color: #fff; border: 0; padding: 0.4rem 0.9rem; border-radius: 4px; font: inherit; font-weight: 600; cursor: pointer; }
    .feed-copy:hover { filter: brightness(0.95); }
    .feed-browse { margin-top: 0.25rem; margin-bottom: 0; font-size: 0.9rem; }
    .feed-items h2 { font-size: 1.1rem; border-bottom: 1px solid var(--hair); padding-bottom: 0.35rem; margin-bottom: 1rem; }
    .feed-items ul { list-style: none; padding: 0; margin: 0; }
    .feed-item { padding: 0.85rem 0; border-bottom: 1px solid var(--hair); }
    .feed-item:last-child { border-bottom: 0; }
    .feed-item__title { display: block; font-weight: 600; font-size: 1.05rem; line-height: 1.35; margin-bottom: 0.2rem; color: var(--fg); }
    .feed-item__title:hover { color: var(--link); }
    .feed-item__meta { margin: 0; font-size: 0.8rem; color: var(--fg-muted); }
    .feed-foot { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--hair); font-size: 0.9rem; color: var(--fg-muted); }
  </xsl:template>
</xsl:stylesheet>
