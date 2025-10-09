# engine/markdown/postprocessors/date_enhancer.py
"""
Postprocessor that enhances dates with time-since subscripts and other formatting.

This postprocessor:
- Parses standalone years (distinguished from numbers by lack of commas)
- Parses YYYY-MM-DD formatted dates
- Adds subscripts showing time elapsed in colloquial format (e.g., "525ya")
- Future: Date ranges, historical eras, date formatting options
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString


def _years_ago_text(years: int, is_duration: bool = False) -> str:
    """
    Convert years to colloquial format with appropriate rounding.

    Args:
        years: Number of years
        is_duration: If True, format as duration (e.g., "5y" instead of "5ya")

    Returns:
        Formatted string like "5ya", "525ya", "5kya", etc.
        Or for durations: "5y", "525y", "5ky", etc.
    """
    suffix = "y" if is_duration else "ya"
    k_suffix = "ky" if is_duration else "kya"
    m_suffix = "my" if is_duration else "mya"

    if years < 10000:
        # Use exact year count for anything under 10,000 years
        return f"{years}{suffix}"
    elif years < 100000:
        # Express in thousands, round to nearest 100
        rounded = round(years / 100) * 100
        ky = rounded / 1000
        if ky == int(ky):
            return f"{int(ky)}{k_suffix}"
        return f"{ky:.1f}{k_suffix}"
    elif years < 1000000:
        # Express in thousands, round to nearest 1000
        rounded = round(years / 1000) * 1000
        ky = rounded / 1000
        return f"{int(ky)}{k_suffix}"
    else:
        # Express in millions
        rounded = round(years / 100000) * 100000
        my = rounded / 1000000
        if my == int(my):
            return f"{int(my)}{m_suffix}"
        return f"{my:.1f}{m_suffix}"


def _calculate_years_ago(year: int, month: int = 7, day: int = 1) -> int:
    """
    Calculate years ago from a given date.

    Args:
        year: Year (e.g., 1500)
        month: Month (1-12), defaults to 7 (July - middle of year)
        day: Day (1-31), defaults to 1

    Returns:
        Number of years ago (rounded)
    """
    now = datetime.now()
    date = datetime(year, month, day)
    days_diff = (now - date).days
    years = days_diff / 365.25
    return round(years)


def _calculate_date_range_duration(
    year1: int, month1: int, day1: int, year2: int, month2: int, day2: int
) -> int:
    """
    Calculate the duration in years between two dates.

    Args:
        year1: Start year
        month1: Start month
        day1: Start day
        year2: End year
        month2: End month
        day2: End day

    Returns:
        Number of years between the dates (rounded)
    """
    date1 = datetime(year1, month1, day1)
    date2 = datetime(year2, month2, day2)
    days_diff = (date2 - date1).days
    years = days_diff / 365.25
    return round(years)


def _add_years_ago_subscript(
    soup: BeautifulSoup,
    text_node: NavigableString,
    match_text: str,
    year: int,
    month: int = 7,
    day: int = 1,
) -> NavigableString:
    """
    Replace a date text with the same text plus a years-ago subscript.

    Args:
        soup: BeautifulSoup instance
        text_node: The text node containing the date
        match_text: The exact text to replace (e.g., "1500" or "2020-09-29")
        year: Year from the date
        month: Month from the date (defaults to 7 - July, middle of year)
        day: Day from the date (defaults to 1)

    Returns:
        The new text node containing the text after the match (for recursive processing)
    """
    years_ago = _calculate_years_ago(year, month, day)
    ya_text = _years_ago_text(years_ago)

    # Create subscript element
    sub = soup.new_tag("sub")
    sub.string = ya_text

    # Split the text node at the match
    text = str(text_node)
    parts = text.split(match_text, 1)

    if len(parts) != 2:
        return None

    # Create new nodes
    before = parts[0]
    after = parts[1]

    # Insert new nodes in order: before, match_text, subscript, after
    if before:
        text_node.insert_before(NavigableString(before))

    text_node.insert_before(NavigableString(match_text))
    text_node.insert_before(sub)

    new_after = None
    if after:
        new_after = NavigableString(after)
        text_node.insert_before(new_after)

    # Remove original text node
    text_node.extract()

    return new_after


def _add_date_range_subscript(
    soup: BeautifulSoup,
    text_node: NavigableString,
    match_text: str,
    start_year: int,
    end_year: int,
    start_month: int = 1,
    start_day: int = 1,
    end_month: int = 1,
    end_day: int = 1,
    hyphen_index: int = 0,
) -> NavigableString:
    """
    Replace a date range hyphen with a subsup element containing the hyphen and duration.
    Wraps the entire date range in a span with class "date-range" and title attribute.

    Args:
        soup: BeautifulSoup instance
        text_node: The text node containing the date range
        match_text: The exact text to replace (e.g., "1500-1600" or "2020-01-01-2020-12-31")
        start_year: Start year
        end_year: End year
        start_month: Start month (defaults to 1)
        start_day: Start day (defaults to 1)
        end_month: End month (defaults to 1)
        end_day: End day (defaults to 1)
        hyphen_index: Position of the range hyphen in match_text

    Returns:
        The new text node containing the text after the match (for recursive processing)
    """
    # Calculate duration in years and days
    date1 = datetime(start_year, start_month, start_day)
    date2 = datetime(end_year, end_month, end_day)
    days_diff = (date2 - date1).days
    duration_years = round(days_diff / 365.25)

    duration_text = _years_ago_text(duration_years, is_duration=True)

    # Create the outer date-range wrapper span
    date_range_span = soup.new_tag("span")
    date_range_span["class"] = ["date-range"]

    # Format the range for display
    if start_month == 1 and start_day == 1 and end_month == 1 and end_day == 1:
        # Year range format
        range_display = f"{start_year}–{end_year}"
    else:
        # Full date range format
        range_display = f"{start_year}-{start_month:02d}-{start_day:02d}–{end_year}-{end_month:02d}-{end_day:02d}"

    # Create title attribute
    years_word = "year" if duration_years == 1 else "years"
    days_word = "day" if days_diff == 1 else "days"
    date_range_span["title"] = f"The date range {range_display} lasted {duration_years} {years_word} ({days_diff:,} {days_word})."

    # Create the subsup wrapper span
    subsup_span = soup.new_tag("span")
    subsup_span["class"] = ["subsup"]

    # Create superscript with hyphen (convert to en dash)
    sup = soup.new_tag("sup")
    hyphen = match_text[hyphen_index]
    # Convert regular hyphen to en dash if needed
    display_hyphen = "–" if hyphen == "-" else hyphen
    sup.string = display_hyphen

    # Create subscript with duration
    sub = soup.new_tag("sub")
    sub.string = duration_text

    # Add sup and sub to subsup span
    subsup_span.append(sup)
    subsup_span.append(sub)

    # Split the text node at the match
    text = str(text_node)
    parts = text.split(match_text, 1)

    if len(parts) != 2:
        return None

    # Create new nodes
    before = parts[0]
    after = parts[1]

    # Split the match text at the hyphen
    before_hyphen = match_text[:hyphen_index]
    after_hyphen = match_text[hyphen_index + 1 :]

    # Build content inside the date-range span
    if before_hyphen:
        date_range_span.append(NavigableString(before_hyphen))

    date_range_span.append(subsup_span)

    if after_hyphen:
        date_range_span.append(NavigableString(after_hyphen))

    # Insert nodes in order: before, date_range_span, after
    if before:
        text_node.insert_before(NavigableString(before))

    text_node.insert_before(date_range_span)

    new_after = None
    if after:
        new_after = NavigableString(after)
        text_node.insert_before(new_after)

    # Remove original text node
    text_node.extract()

    return new_after


def _process_text_node(soup: BeautifulSoup, text_node: NavigableString) -> None:
    """
    Process a single text node to find and enhance dates.
    This function processes ALL dates in the text node by recursively processing
    the remaining text after each match.

    Args:
        soup: BeautifulSoup instance
        text_node: The text node to process
    """
    # Check if the node is still in the tree
    if not text_node.parent:
        return

    text = str(text_node)

    # Pattern for AD prefix dates: AD 99
    ad_pattern = r"\bAD\s+(\d{1,4})\b"

    # Pattern for BC/BCE suffix dates: 3000 BC or 3000 BCE
    bc_pattern = r"\b(\d{1,4})\s+(BC|BCE)\b"

    # Pattern for YYYY-MM-DD–YYYY-MM-DD date ranges (using en dash or hyphen)
    # Must be preceded by whitespace or start of string, followed by whitespace or end
    full_date_range_pattern = r"(?<!\S)(\d{4})-(\d{2})-(\d{2})([–-])(\d{4})-(\d{2})-(\d{2})(?!\S)"

    # Pattern for YYYY–YYYY year ranges (using en dash or hyphen)
    year_range_pattern = r"(?<!\d)(\d{4})([–-])(\d{4})(?!\d)"

    # Pattern for YYYY-MM-DD dates (single)
    # Must be preceded by whitespace or start of string, followed by whitespace or end
    date_pattern = r"(?<!\S)(\d{4})-(\d{2})-(\d{2})(?!\S)"

    # Pattern for standalone years (4 digits not followed by comma, not part of larger number)
    # Must not be preceded or followed by digits, hyphens, or commas (to avoid matching IDs)
    year_pattern = r"(?<!\d)(?<!-)(?<!,)(\d{4})(?!,)(?!-)(?!\d)"

    # First, check for AD dates (AD 99)
    ad_match = re.search(ad_pattern, text)
    if ad_match:
        year = int(ad_match.group(1))
        # AD dates are positive years
        new_after = _add_years_ago_subscript(soup, text_node, ad_match.group(0), year)
        if new_after:
            _process_text_node(soup, new_after)
        return

    # Then check for BC/BCE dates (3000 BC or 3000 BCE)
    bc_match = re.search(bc_pattern, text)
    if bc_match:
        year = int(bc_match.group(1))
        # BC/BCE dates are negative years - convert to years ago
        # BC 3000 = 3000 + current year years ago
        years_ago = year + datetime.now().year
        ya_text = _years_ago_text(years_ago)

        # Create subscript element
        sub = soup.new_tag("sub")
        sub.string = ya_text

        # Split and insert
        parts = str(text_node).split(bc_match.group(0), 1)
        if len(parts) == 2:
            new_after = None
            if parts[0]:
                text_node.insert_before(NavigableString(parts[0]))
            text_node.insert_before(NavigableString(bc_match.group(0)))
            text_node.insert_before(sub)
            if parts[1]:
                new_after = NavigableString(parts[1])
                text_node.insert_before(new_after)
            text_node.extract()
            # Process the remaining text
            if new_after:
                _process_text_node(soup, new_after)
        return

    # Then check for full date ranges (YYYY-MM-DD–YYYY-MM-DD)
    full_range_match = re.search(full_date_range_pattern, text)
    if full_range_match:
        start_year = int(full_range_match.group(1))
        start_month = int(full_range_match.group(2))
        start_day = int(full_range_match.group(3))
        hyphen = full_range_match.group(4)
        end_year = int(full_range_match.group(5))
        end_month = int(full_range_match.group(6))
        end_day = int(full_range_match.group(7))

        # Find the position of the range hyphen (the one between the dates)
        # This is the character between YYYY-MM-DD and YYYY-MM-DD
        hyphen_index = full_range_match.group(0).find(
            hyphen, len(f"{start_year}-{start_month:02d}-{start_day:02d}")
        )

        new_after = _add_date_range_subscript(
            soup,
            text_node,
            full_range_match.group(0),
            start_year,
            end_year,
            start_month,
            start_day,
            end_month,
            end_day,
            hyphen_index,
        )
        if new_after:
            _process_text_node(soup, new_after)
        return

    # Then check for year ranges (YYYY–YYYY)
    year_range_match = re.search(year_range_pattern, text)
    if year_range_match:
        start_year = int(year_range_match.group(1))
        hyphen = year_range_match.group(2)
        end_year = int(year_range_match.group(3))

        # Only process if both years look like dates (1000-2100 range)
        if 1000 <= start_year < 2100 and 1000 <= end_year < 2100:
            # Find hyphen position (it's after the first year)
            hyphen_index = len(str(start_year))

            new_after = _add_date_range_subscript(
                soup,
                text_node,
                year_range_match.group(0),
                start_year,
                end_year,
                hyphen_index=hyphen_index,
            )
            if new_after:
                _process_text_node(soup, new_after)
            return

    # Then check for single YYYY-MM-DD dates
    date_match = re.search(date_pattern, text)
    if date_match:
        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        # Only process if it's a historical date (before today and more than 5 years ago)
        date_obj = datetime(year, month, day)
        now = datetime.now()
        if date_obj.date() < now.date():
            years_ago = _calculate_years_ago(year, month, day)
            if years_ago >= 5:
                new_after = _add_years_ago_subscript(
                    soup, text_node, date_match.group(0), year, month, day
                )
                if new_after:
                    _process_text_node(soup, new_after)
            return

    # Finally check for standalone years
    year_match = re.search(year_pattern, text)
    if year_match:
        year = int(year_match.group(1))

        # Only process years that look like dates (e.g., 1000-2100 range)
        # and are before current year and more than 5 years ago
        if 1000 <= year < datetime.now().year:
            years_ago = _calculate_years_ago(year)
            if years_ago >= 5:
                new_after = _add_years_ago_subscript(soup, text_node, year_match.group(0), year)
                if new_after:
                    _process_text_node(soup, new_after)
            return


def date_enhancer(
    html: str,
    context: dict,
    enable_years_ago: bool = True,
    # Future options:
    # enable_date_ranges: bool = True,
    # enable_era_labels: bool = True,
) -> str:
    """
    Enhance dates with subscripts and formatting.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        enable_years_ago: Add years-ago subscripts to dates (default: True)

    Returns:
        Processed HTML with enhanced dates
    """
    if not enable_years_ago:
        return html

    soup = BeautifulSoup(html, "html.parser")

    # Process all text nodes
    # We need to be careful to only process actual text content, not code, URLs, etc.

    # Skip processing in these elements
    skip_elements = {"code", "pre", "script", "style", "kbd", "samp", "var"}

    # Find all text nodes that aren't in skip elements
    # Collect them first to avoid issues with modifying the tree during iteration
    text_nodes = []
    for element in soup.find_all(string=True):
        # Skip if parent is in skip list
        if element.parent and element.parent.name in skip_elements:
            continue

        # Skip if inside a link (URLs might contain year-like numbers)
        if element.find_parent("a"):
            continue

        # Collect this text node
        if isinstance(element, NavigableString) and element.strip():
            text_nodes.append(element)

    # Now process all collected text nodes
    for element in text_nodes:
        # Verify the element is still in the tree (it might have been removed by a previous processing)
        if element.parent:
            _process_text_node(soup, element)

    return str(soup)


def date_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for date_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return date_enhancer(
        html,
        context,
        enable_years_ago=True,
    )
