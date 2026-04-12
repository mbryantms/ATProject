# Bibliography & Citations Reference

This post serves as both a working example and complete documentation of the bibliography and citation system. Every citation syntax variant, locator type, and rendering behavior is demonstrated with real sources. The references section at the bottom of this post is auto-generated from the citations used throughout the text.

## Prerequisites: Creating the Sources

Before this post will render correctly, the following sources must exist in **Admin > Engine > Sources**. You can create them manually or import them from Zotero. For each source, leave the **Citation key** blank and it will auto-generate from the author, year, and title.

**Source 1 — Journal Article:**

- Title: *The Neural Basis of Decision Making Under Uncertainty*
- Type: Journal Article
- Authors: `[{"family": "Chen", "given": "Wei"}, {"family": "Nakamura", "given": "Yuki"}]`
- Issued date: `{"date-parts": [[2024, 6, 15]]}`
- Container title: Nature Neuroscience
- Volume: 27
- Issue: 6
- Page: 1042-1058
- DOI: 10.1038/s41593-024-01632-4
- URL: https://doi.org/10.1038/s41593-024-01632-4

**Source 2 — Book:**

- Title: *Thinking in Systems: A Primer*
- Type: Book
- Authors: `[{"family": "Meadows", "given": "Donella H."}]`
- Editors: `[{"family": "Wright", "given": "Diana"}]`
- Issued date: `{"date-parts": [[2008]]}`
- Publisher: Chelsea Green Publishing
- Publisher place: White River Junction, VT
- ISBN: 978-1603580557

**Source 3 — Book Chapter:**

- Title: *Bayesian Approaches to Clinical Trials*
- Type: Book Chapter
- Authors: `[{"family": "Spiegelhalter", "given": "David J."}, {"family": "Freedman", "given": "Laurence S."}, {"family": "Parmar", "given": "Mahesh K. B."}]`
- Issued date: `{"date-parts": [[1994]]}`
- Container title: Bayesian Statistics 5
- Publisher: Oxford University Press
- Page: 357-386
- Editors: `[{"family": "Bernardo", "given": "José M."}]`

**Source 4 — Web Page:**

- Title: *Attention Is All You Need: A Retrospective*
- Type: Web Page
- Authors: `[{"family": "Vaswani", "given": "Ashish"}, {"family": "Shazeer", "given": "Noam"}, {"family": "Parmar", "given": "Niki"}]`
- Issued date: `{"date-parts": [[2023, 12, 4]]}`
- Container title: Google Research Blog
- URL: https://research.google/blog/attention-is-all-you-need
- Accessed date: `{"date-parts": [[2025, 3, 10]]}`

**Source 5 — Conference Paper:**

- Title: *Scaling Laws for Neural Language Models*
- Type: Conference Paper
- Authors: `[{"family": "Kaplan", "given": "Jared"}, {"family": "McCandlish", "given": "Sam"}, {"family": "Henighan", "given": "Tom"}, {"family": "Brown", "given": "Tom B."}]`
- Issued date: `{"date-parts": [[2020]]}`
- Container title: Proceedings of the International Conference on Machine Learning
- Publisher: PMLR
- DOI: 10.48550/arXiv.2001.08361

**Source 6 — Report (Institutional Author):**

- Title: *Global Risks Report 2024*
- Type: Report
- Authors: `[{"literal": "World Economic Forum"}]`
- Issued date: `{"date-parts": [[2024, 1]]}`
- Publisher: World Economic Forum
- Publisher place: Geneva
- URL: https://www.weforum.org/publications/global-risks-report-2024

**Source 7 — Thesis:**

- Title: *Emergent Complexity in Multi-Agent Reinforcement Learning Environments*
- Type: Thesis
- Authors: `[{"family": "Okonkwo", "given": "Adaeze"}]`
- Issued date: `{"date-parts": [[2023]]}`
- Publisher: Massachusetts Institute of Technology
- Publisher place: Cambridge, MA

---

## Basic Parenthetical Citations

The simplest and most common citation form places the reference in parentheses at the end of a clause or sentence. Write `[@key]` where `key` is the source's citation key.

Recent work in computational neuroscience has revealed unexpected parallels between artificial and biological neural networks, suggesting that the optimization landscapes explored by gradient descent may share structural features with those navigated by synaptic plasticity [@chen2024neural]. This finding builds on decades of systems-level thinking about feedback loops and emergent behavior in complex adaptive systems [@meadows2008thinking].

The conference paper that introduced scaling laws for neural language models has since become one of the most cited works in the field [@kaplan2020scaling]. Meanwhile, institutional reports continue to highlight the intersection of technological risk and global governance [@worldeconomicforum2024global].

Multiple sources can confirm a point when placed together. The convergence of Bayesian methods and modern machine learning represents one of the most productive cross-pollinations in recent scientific history [@spiegelhalter1994bayesian]. Doctoral work has further extended these ideas into multi-agent settings [@okonkwo2023emergent].

---

## Page and Location References

When citing a specific passage, add a locator after the key, separated by a comma. The system recognizes standard locator prefixes and formats them according to the active citation style.

### Page Numbers

Single page references use `p.` and page ranges use `pp.`:

The authors define their core framework in the methods section, establishing the experimental protocol that all subsequent analyses depend on [@chen2024neural, p. 1045]. The results across all three experimental conditions are summarized in a single comprehensive table [@chen2024neural, pp. 1050-1054]. The distinction between leverage points in systems is perhaps Meadows' most lasting contribution to the field [@meadows2008thinking, pp. 145-165].

### Chapter References

Use `ch.` or `chap.` for chapter-level references:

The opening chapter provides an accessible introduction to the concept of stocks and flows that requires no mathematical background [@meadows2008thinking, ch. 1]. Later chapters build on this foundation with increasingly sophisticated models of system dynamics [@meadows2008thinking, ch. 5].

### Section References

Use `sec.` for section-level references:

The discussion of prior elicitation is particularly relevant for practitioners working with limited historical data [@spiegelhalter1994bayesian, sec. 3].

### Volume References

Use `vol.` for multi-volume works:

The broader series covers the full history of the Bayesian statistics conference proceedings, with each volume representing a biennial meeting [@spiegelhalter1994bayesian, vol. 5].

### Figure References

Use `fig.` for specific figures:

The attention heatmap visualization demonstrates how the model allocates computational resources across input tokens [@vaswani2023attention, fig. 2].

### Paragraph References

Use `para.` for paragraph-level precision:

The retrospective opens with a personal anecdote about the moment the team realized their architecture would generalize beyond machine translation [@vaswani2023attention, para. 3].

### Line and Note References

Use `l.` for line references and `n.` for notes:

The footnote on experimental methodology deserves close reading, as it contains a crucial caveat about the generalizability of the results [@chen2024neural, n. 14].

---

## Narrative (In-Text) Citations

When the author's name is part of the sentence structure, use a bare `@key` without brackets. The author name appears in the running text with only the year parenthesized.

@chen2024neural demonstrate that prefrontal cortical activity during uncertain decision tasks follows a pattern strikingly similar to the attention mechanisms used in transformer architectures. Their work extends the theoretical framework first articulated by @meadows2008thinking, who argued that complex systems exhibit universal structural patterns regardless of their substrate.

The seminal paper by @vaswani2023attention has fundamentally reshaped how researchers think about sequence modeling. Building on this foundation, @kaplan2020scaling established the empirical laws governing how language model performance improves with scale. More recently, @okonkwo2023emergent has shown that these scaling relationships extend to multi-agent environments, where emergent behaviors arise from the interaction of individually simple policies.

Institutional perspectives complement individual research contributions. @worldeconomicforum2024global identifies artificial intelligence governance as one of the five critical risk vectors for the coming decade, drawing on survey data from over 1,400 global leaders.

---

## Suppress-Author Citations

When you have already named the author in your sentence and want only the year in parentheses, use `[-@key]`. This avoids the redundancy of writing "Chen (Chen & Nakamura, 2024)."

Chen and Nakamura's landmark study [-@chen2024neural] built on three years of preliminary data collection across twelve research sites. Meadows [-@meadows2008thinking] had anticipated many of these systemic dynamics decades earlier, though her work predated the computational tools needed to verify them empirically. The World Economic Forum [-@worldeconomicforum2024global] has increasingly emphasized the need for adaptive governance frameworks that can respond to rapidly evolving technological landscapes.

---

## Multi-Source Citations

Cite multiple sources in a single bracketed reference by separating them with semicolons. The citation processor sorts them according to the active style's rules (typically alphabetical by author or chronological).

The relationship between neural architecture and cognitive function has been explored from multiple complementary perspectives [@chen2024neural; @kaplan2020scaling; @okonkwo2023emergent]. Systems thinking provides a meta-framework for understanding how these individual findings connect to form a coherent picture of intelligence, whether biological or artificial [@meadows2008thinking; @spiegelhalter1994bayesian].

Multi-source citations can also include locators on individual sources. The experimental methodology draws on established Bayesian frameworks [@spiegelhalter1994bayesian, pp. 360-370; @chen2024neural, sec. 2] while the theoretical interpretation follows the systems dynamics tradition [@meadows2008thinking, ch. 3; @worldeconomicforum2024global].

---

## Unresolved Citations

If a citation key does not match any source in the library, it renders as a visible error marker rather than failing silently. This makes typos and missing sources easy to spot during editing.

Some researchers have explored alternative architectures that avoid attention entirely [@nonexistent2024paper]. This reference will render as a red `[??nonexistent2024paper]` error marker because no source with that key exists. Check the spelling of the key, or create the missing source in **Admin > Engine > Sources** before publishing.

---

## Citations with Footnotes

Citations and footnotes use completely separate systems and do not interfere with each other. You can use both freely in the same post. The bibliography section appears before the footnotes section in the rendered output.

The interplay between theoretical frameworks and empirical validation represents one of the enduring challenges of interdisciplinary research [@chen2024neural; @meadows2008thinking].[^methodology] Some scholars argue that this tension is itself productive, forcing researchers to articulate their assumptions more precisely than they otherwise would [@spiegelhalter1994bayesian].[^bayesian-debate]

[^methodology]: The methodological challenges of cross-disciplinary work are well documented but rarely addressed systematically. Each field brings its own standards of evidence, its own conventions for statistical significance, and its own norms around replication.

[^bayesian-debate]: The Bayesian vs. frequentist debate has generated enormous heat over the past century, but the practical convergence between the two frameworks in applied settings is far more notable than their philosophical divergence.

---

## Citations in Blockquotes

Citations work within blockquotes, preserving the same syntax and rendering behavior:

> The fundamental insight of systems thinking is that the behavior of a system cannot be understood by examining its parts in isolation. The relationships between the parts — the feedback loops, the delays, the nonlinearities — are what generate the system's characteristic behavior over time [@meadows2008thinking, pp. 12-13].

> > Even nested blockquotes support citations. As the scaling laws research demonstrates, the predictable relationship between compute, data, and model performance holds across multiple orders of magnitude [@kaplan2020scaling].

---

## How the System Works

### Rendering Pipeline

When you save a post, the following happens automatically:

1. The **citation escaper** preprocessor converts all `[@key]` syntax into placeholder tokens before Pandoc processes the markdown. This prevents Pandoc from interpreting or corrupting the citation syntax.

2. Pandoc converts the rest of the markdown to HTML as normal.

3. The **citation renderer** postprocessor finds all placeholder tokens, batch-queries the Source table for matching keys, sends the resolved CSL-JSON data to **citeproc-js** (running as a Node.js subprocess) for formatting, and replaces each placeholder with a styled inline citation link.

4. A **bibliography section** is automatically appended at the end of the content, listing all cited sources formatted according to the active citation style. Only sources actually referenced with `[@key]` appear — you cannot manually add sources to the bibliography.

5. **PostCitation** records are synced in the database, tracking which sources are cited in which posts and in what order. These records power the "Cited Sources" inline in the post admin and enable queries like "which posts cite this source?"

### Citation Keys

Every source has a unique citation key — the identifier you use in `[@key]`. Keys are auto-generated from the first author's family name, the year, and the first significant word of the title. For example:

- Chen & Nakamura (2024), "The Neural Basis of Decision Making..." → `chen2024neural`
- Meadows (2008), "Thinking in Systems..." → `meadows2008thinking`
- World Economic Forum (2024), "Global Risks Report..." → `worldeconomicforum2024global`

When two sources would produce the same key, a letter suffix is appended: `smith2024a`, `smith2024b`. Once a key is set, treat it as permanent — changing it will break all posts that reference it.

### Citation Styles

The site has a default citation style set in **Admin > Site Settings > Bibliography**. Individual posts can override this with a different style in the **Organization & Taxonomy** section of the post admin.

Available styles include: `apa`, `mla` (or `modern-language-association`), `chicago` (or `chicago-author-date`), `chicago-notes` (or `chicago-notes-bibliography`), `ieee`, `harvard` (or `harvard-cite-them-right`), `vancouver`, `nature`.

Short names like `mla` and `chicago` are aliased to their full CSL filenames automatically.

### Tooltips and Navigation

On desktop, hovering over any inline citation shows a tooltip with the full formatted reference. Clicking the citation scrolls to its entry in the bibliography section with a brief highlight animation. On mobile, tapping a citation shows the tooltip; tapping elsewhere dismisses it.

### Zotero Integration

Sources can be imported from a Zotero library via **Admin > Management Commands** or the scheduled sync task. The sync only imports top-level items (actual sources) — child items like PDF attachments and notes are handled separately. PDFs attached to Zotero items are automatically downloaded and stored as the source's archived file.

To set up Zotero sync: go to **Admin > Site Settings > Zotero Integration**, enter your numeric user ID (from zotero.org/settings/keys), select the library type, and paste your API key.

### Auto-Populating Metadata

In the Source admin, the bulk actions **"Fetch metadata from DOI"** and **"Fetch metadata from URL"** query external APIs (CrossRef for DOIs, OpenGraph/meta tags for URLs) and fill in any empty fields on the selected sources. This is a one-way fill — existing data is never overwritten.

### Link Rot Detection

The bulk action **"Check URLs for availability"** sends HTTP HEAD requests to each source's URL and records the result. Broken URLs are automatically checked against the Wayback Machine for archived snapshots. URL health status is visible in the source list as a colored badge: green (OK), yellow (redirect), red (broken), purple (archived), gray (unchecked).

### Archived Files

Sources can have an attached file (PDF, HTML, EPUB) uploaded in the **File Archive** section of the source admin. When a source has an archived file, a `[PDF]` link appears next to its bibliography entry, linking directly to the stored copy. Files are stored in R2 via the same storage backend used for media assets.

---

## Complete Syntax Reference

| Syntax | Description | Example Output |
|--------|-------------|---------------|
| `[@key]` | Parenthetical citation | (Chen & Nakamura, 2024) |
| `[@key, p. 42]` | With single page | (Chen & Nakamura, 2024, p. 42) |
| `[@key, pp. 42-56]` | With page range | (Chen & Nakamura, 2024, pp. 42-56) |
| `[@key, ch. 3]` | With chapter | (Meadows, 2008, ch. 3) |
| `[@key, sec. 2]` | With section | (Spiegelhalter et al., 1994, sec. 2) |
| `[@key, vol. 5]` | With volume | (Spiegelhalter et al., 1994, vol. 5) |
| `[@key, fig. 2]` | With figure | (Vaswani et al., 2023, fig. 2) |
| `[@key, para. 3]` | With paragraph | (Vaswani et al., 2023, para. 3) |
| `[@key, n. 14]` | With note | (Chen & Nakamura, 2024, n. 14) |
| `[@key, l. 7]` | With line | (Okonkwo, 2023, l. 7) |
| `@key` | Narrative citation | Chen & Nakamura (2024) |
| `[-@key]` | Suppress author | (2024) |
| `[@key1; @key2]` | Multiple sources | (Chen & Nakamura, 2024; Meadows, 2008) |
| `[@key1, p. 5; @key2, ch. 3]` | Multiple with locators | (Chen & Nakamura, 2024, p. 5; Meadows, 2008, ch. 3) |
| `[@nonexistent]` | Unresolved reference | [??nonexistent] |
