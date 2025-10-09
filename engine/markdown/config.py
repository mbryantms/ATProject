from pathlib import Path


def get_pandoc_config():
    """
    Configuration for pypandoc/Pandoc markdown rendering.

    Pandoc has built-in support for most markdown features that were previously
    provided by python-markdown extensions. This configuration enables comparable
    functionality using Pandoc's native extensions.

    Note: Custom python-markdown extensions (header_attributes, paragraph_classes)
    will need to be implemented as Pandoc filters or postprocessors.
    """
    base_dir = Path(__file__).resolve().parent

    heading_filter = base_dir / "filters" / "heading_sectionizer.lua"

    return {
        "extra_args": [
            # Enable Pandoc markdown extensions (all in --from argument)
            "--from=markdown+autolink_bare_uris+strikeout+superscript+subscript+task_lists+smart+pipe_tables+grid_tables+definition_lists+footnotes+abbreviations+fenced_code_blocks+fenced_code_attributes+raw_html+header_attributes+implicit_header_references+fenced_code_attributes+fancy_lists+tex_math_dollars+smart+hard_line_breaks",
            # Code highlighting
            # "--syntax-highlighting=pygments",
            # Math rendering with MathJax
            "--mathjax",
            # TOC generation (can be enabled if needed)
            # "--toc",
            # "--toc-depth=6",
        ],
        # Pandoc filters can be added here (Python or Lua filters)
        "filters": [
            str(heading_filter),
        ],
    }
