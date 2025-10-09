# engine/markdown/postprocessors/mathjax_config.py
"""
Postprocessor that adds MathJax configuration for LaTeX packages.

This postprocessor:
- Adds MathJax configuration script to enable LaTeX packages like xfrac
- The configuration must be added before any MathJax script tags
"""

from bs4 import BeautifulSoup


def mathjax_config_injector(html: str, context: dict) -> str:
    """
    Inject MathJax configuration script for LaTeX extensions.

    This adds configuration for MathJax to load the xfrac package and other
    LaTeX extensions needed for advanced math typesetting.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)

    Returns:
        Processed HTML with MathJax configuration
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check if there's already a MathJax config or script
    # We want to ensure we don't duplicate configs
    existing_config = soup.find("script", string=lambda s: s and "MathJax" in s and "xfrac" in s)
    if existing_config:
        return str(soup)

    # Create the MathJax configuration script
    config_script = soup.new_tag("script")
    config_script.string = """
window.MathJax = {
  loader: {
    load: ['[tex]/xfrac']
  },
  tex: {
    packages: {'[+]': ['xfrac']},
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
  },
  startup: {
    ready: () => {
      MathJax.startup.defaultReady();
    }
  }
};
"""

    # Try to insert at the beginning of the document
    # Look for the first element in the soup (usually the root)
    if soup.contents:
        # Insert as the first item
        soup.insert(0, config_script)
    else:
        # If empty, just append
        soup.append(config_script)

    return str(soup)


def mathjax_config_injector_default(html: str, context: dict) -> str:
    """
    Default configuration for mathjax_config_injector.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return mathjax_config_injector(html, context)
