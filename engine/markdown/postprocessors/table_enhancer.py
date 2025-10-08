# engine/markdown/postprocessors/table_enhancer.py
"""
Postprocessor that enhances tables with proper wrapper structure.

This postprocessor:
- Wraps tables in nested divs for proper styling and scrolling
- Supports optional size classes from Pandoc fenced divs (table-small, width-full)
- Supports optional sortable flag from Pandoc fenced divs
- Ensures proper table structure (thead, tbody)

Expected structure:
    Pandoc markdown (default - no size class):
        | Col 1 | Col 2 |
        |-------|-------|
        | A     | B     |

    Output (default):
        <div class="table-wrapper block">
            <div class="table-scroll-wrapper">
                <table>
                    <thead>...</thead>
                    <tbody>...</tbody>
                </table>
            </div>
        </div>

    With explicit size:
        ::: {.table-small}
        | Col 1 | Col 2 |
        |-------|-------|
        | A     | B     |
        :::

    Output with size class:
        <div class="table-wrapper table-small block">
            <div class="table-scroll-wrapper">
                <table>...</table>
            </div>
        </div>

    With sortable flag:
        ::: {.sortable}
        | Col 1 | Col 2 |
        |-------|-------|
        | A     | B     |
        :::

    Output with sortable:
        <div class="table-wrapper block">
            <div class="table-scroll-wrapper">
                <table data-sortable="true">...</table>
            </div>
        </div>
"""

from bs4 import BeautifulSoup, Tag, NavigableString


def _extract_table_attributes(table: Tag) -> dict:
    """
    Extract table attributes from table element or parent Pandoc fenced div.

    Checks for:
    - Size classes: table-small, width-full
    - Float classes: float-left, float-right
    - Sortable flag: sortable

    Args:
        table: BeautifulSoup Tag representing a table element

    Returns:
        Dictionary with keys: size_class, float_classes, sortable
    """
    attributes = {
        'size_class': None,
        'float_classes': [],
        'sortable': False
    }

    # Check table classes
    table_classes = table.get("class", [])
    if isinstance(table_classes, str):
        table_classes = table_classes.split()

    # Check for size class on table
    if "table-small" in table_classes:
        attributes['size_class'] = "table-small"
    elif "width-full" in table_classes:
        attributes['size_class'] = "width-full"

    # Check for sortable on table
    if "sortable" in table_classes:
        attributes['sortable'] = True

    # Check parent div for explicit classes (from Pandoc fenced div)
    parent = table.parent
    if parent and parent.name == "div":
        parent_classes = parent.get("class", [])
        if isinstance(parent_classes, str):
            parent_classes = parent_classes.split()

        # Extract size class from parent if not already found
        if not attributes['size_class']:
            if "table-small" in parent_classes:
                attributes['size_class'] = "table-small"
            elif "width-full" in parent_classes:
                attributes['size_class'] = "width-full"

        # Extract float classes from parent
        for cls in parent_classes:
            if cls in ["float-left", "float-right"]:
                attributes['float_classes'].append(cls)

        # Check for sortable in parent
        if "sortable" in parent_classes:
            attributes['sortable'] = True

    return attributes


def _ensure_table_structure(table: Tag) -> None:
    """
    Ensure table has proper thead/tbody structure.

    Pandoc usually handles this, but we verify and fix if needed.

    Args:
        table: BeautifulSoup Tag representing a table element
    """
    # Check if we have thead and tbody
    has_thead = table.find("thead") is not None
    has_tbody = table.find("tbody") is not None

    # If we have both, structure is fine
    if has_thead and has_tbody:
        return

    # If we have tbody but no thead, that's fine (tables without headers)
    if has_tbody and not has_thead:
        return

    # If we have thead but no tbody, wrap remaining rows in tbody
    if has_thead and not has_tbody:
        thead = table.find("thead")
        rows = table.find_all("tr", recursive=False)

        # Find rows that are not in thead
        tbody_rows = []
        for row in rows:
            if row.parent == table and row not in thead.find_all("tr"):
                tbody_rows.append(row)

        if tbody_rows:
            # Create tbody and move rows into it
            tbody = table.new_tag("tbody")
            for row in tbody_rows:
                row.extract()
                tbody.append(row)
            table.append(tbody)


def _wrap_table(soup: BeautifulSoup, table: Tag, attributes: dict) -> Tag:
    """
    Wrap table in nested div structure.

    Default structure (no size class):
        <div class="table-wrapper block">
            <div class="table-scroll-wrapper">
                <table>...</table>
            </div>
        </div>

    With size class:
        <div class="table-wrapper table-small block">
            <div class="table-scroll-wrapper">
                <table>...</table>
            </div>
        </div>

    Args:
        soup: BeautifulSoup instance
        table: Table element to wrap
        attributes: Dictionary with size_class, float_classes, sortable

    Returns:
        The outer wrapper div
    """
    # Check if table is already wrapped (avoid double-wrapping)
    parent = table.parent
    if parent and parent.name == "div":
        parent_classes = parent.get("class", [])
        if isinstance(parent_classes, str):
            parent_classes = parent_classes.split()
        # If parent already has table-wrapper class, it's already wrapped
        if "table-wrapper" in parent_classes:
            return parent

    # Check for Pandoc fenced div wrapper
    pandoc_wrapper = None
    if parent and parent.name == "div":
        parent_classes = parent.get("class", [])
        if isinstance(parent_classes, str):
            parent_classes = parent_classes.split()

        # Check if parent has any table-related classes
        has_table_classes = any(
            cls in parent_classes
            for cls in ["table-small", "width-full", "float-left", "float-right", "sortable"]
        )

        # If parent has table-related classes, it's a Pandoc wrapper
        if has_table_classes:
            pandoc_wrapper = parent

    # Create outer wrapper
    outer_wrapper = soup.new_tag("div")
    wrapper_classes = ["table-wrapper"]

    # Add size class if specified
    if attributes['size_class']:
        wrapper_classes.append(attributes['size_class'])

    # Add float classes if they exist
    wrapper_classes.extend(attributes['float_classes'])

    # Always add block class last
    wrapper_classes.append("block")

    outer_wrapper["class"] = wrapper_classes

    # Create inner scroll wrapper
    inner_wrapper = soup.new_tag("div")
    inner_wrapper["class"] = ["table-scroll-wrapper"]

    # Add sortable attribute to table if specified
    if attributes['sortable']:
        table['data-sortable'] = "true"

    # Build the structure
    if pandoc_wrapper:
        # Replace Pandoc wrapper with our new structure
        pandoc_wrapper.insert_before(outer_wrapper)
        table.extract()
        inner_wrapper.append(table)
        outer_wrapper.append(inner_wrapper)
        pandoc_wrapper.extract()
    else:
        # Insert outer wrapper before table
        table.insert_before(outer_wrapper)
        # Extract table and add to inner wrapper
        table.extract()
        inner_wrapper.append(table)
        # Add inner wrapper to outer wrapper
        outer_wrapper.append(inner_wrapper)

    return outer_wrapper


def table_enhancer(html: str, context: dict) -> str:
    """
    Enhance tables with proper wrapper structure.

    This postprocessor:
    - Wraps tables in .table-wrapper and .table-scroll-wrapper divs
    - Extracts optional size classes from Pandoc fenced divs (table-small, width-full)
    - Extracts optional sortable flag from Pandoc fenced divs
    - Ensures proper thead/tbody structure
    - Default: no size class, just "table-wrapper block"

    Args:
        html: HTML string to process
        context: Context dictionary (unused but required for postprocessor signature)

    Returns:
        Processed HTML with enhanced tables
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all tables
    tables = soup.find_all("table")

    for table in tables:
        # Ensure proper structure
        _ensure_table_structure(table)

        # Extract attributes from fenced div or table classes
        attributes = _extract_table_attributes(table)

        # Wrap table
        _wrap_table(soup, table, attributes)

    return str(soup)


def table_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for table_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return table_enhancer(html, context)
