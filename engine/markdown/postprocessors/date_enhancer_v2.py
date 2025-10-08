# engine/markdown/postprocessors/date_enhancer_v2.py
"""
Markdown-syntax-based date enhancer postprocessor.

This version requires explicit markdown syntax to identify dates for enhancement,
giving authors precise control over which dates are processed.

Supported markdown syntaxes:
1. [2020-01-15]{.date-since} - Adds time-since subscript
2. [1500–1600]{.date-range} - Adds duration between dates
3. [1500–1600]{.date-range-since} - Adds both duration and time-since
4. [1500–1600]{.date-since} - Adds only time-since (from end date)

Supported date formats:
- ISO dates: 2020-09-29, 2025-09-28, 1986-12-22
- Year-month: 2020-01, 1986-12
- Year only: 1549, 1986, 673
- BC/BCE dates: 1500 BC, 984 BCE, 200,000 BC, 1.4 million BC
- AD prefix: AD 673
- Natural language: January 15, 2020, 15 January 2020, January 2020
- Date ranges: 1500–1600, 1970-01-01--2038-01-19, 2020 to 2021
- Range separators: – (en dash), — (em dash), -- (double hyphen), - (hyphen), to
"""

import re
from datetime import datetime
from dateutil import parser as date_parser

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


def _parse_date(date_string: str) -> datetime:
    """
    Parse a date string into a datetime object.

    Supports many common formats including:
    - ISO dates: 2020-09-29
    - Year only: 1500, 673
    - BC/BCE dates: 1500 BC, 984 BCE, 200,000 BC
    - AD prefix: AD 673
    - Large numbers: 1.4 million BC

    For dates missing month/day components, defaults to July 1 (middle of year).

    Args:
        date_string: Date string to parse

    Returns:
        datetime object (timezone-naive), with negative years for BC/BCE dates

    Raises:
        ValueError: If date cannot be parsed, or a special ValueError with format
                   "BC_DATE:year" for BC/BCE dates (to be handled by caller)
    """
    # Clean up the string
    date_string = date_string.strip()

    # Handle BC/BCE dates (including large numbers and decimals)
    bc_match = re.match(r'^([\d,]+(?:\.\d+)?)\s*(million|m)?\s*(BC|BCE)$', date_string, re.IGNORECASE)
    if bc_match:
        year_str = bc_match.group(1).replace(',', '')
        multiplier = bc_match.group(2)

        # Parse the year value
        year_value = float(year_str)

        # Apply multiplier if present
        if multiplier and multiplier.lower() in ('million', 'm'):
            year_value *= 1_000_000

        year = int(year_value)

        # BC/BCE dates: raise a special ValueError that the caller will catch
        # The caller will calculate: years_ago = BC_year + current_year
        # Example: 984 BCE in year 2025 = 984 + 2025 = 3009 years ago
        raise ValueError(f"BC_DATE:{year}")

    # Handle AD prefix dates (AD 673)
    ad_match = re.match(r'^AD\s+(\d+)$', date_string, re.IGNORECASE)
    if ad_match:
        year = int(ad_match.group(1))
        return datetime(year, 7, 1)

    # Try to parse with dateutil
    try:
        # Use dayfirst=False to prefer MM-DD-YYYY for ambiguous dates
        # Use default with July 1 for missing month/day (middle of year)
        # Year 1 is the default year - will be overridden by actual year in date string
        dt = date_parser.parse(date_string, default=datetime(1, 7, 1))

        # Convert to timezone-naive if timezone-aware
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)

        return dt
    except (ValueError, TypeError) as e:
        raise ValueError(f"Could not parse date: {date_string}") from e


def _calculate_years_between(date1: datetime, date2: datetime) -> int:
    """
    Calculate years between two dates.

    Args:
        date1: Start date
        date2: End date

    Returns:
        Number of years (rounded)
    """
    days_diff = (date2 - date1).days
    years = days_diff / 365.25
    return round(years)


def _calculate_years_ago(date: datetime) -> int:
    """
    Calculate years ago from a given date.

    Args:
        date: Past date

    Returns:
        Number of years ago (rounded)
    """
    now = datetime.now()
    return _calculate_years_between(date, now)


def _split_date_range(text: str) -> tuple[str, str, str, int]:
    """
    Split a date range text into start and end dates, finding the separator.

    Supports various separators: – (en dash), — (em dash), -- (double hyphen), - (hyphen), to, etc.

    Args:
        text: Date range text (e.g., "1500–1600", "2020--2021", or "Jan 2020 to Mar 2021")

    Returns:
        Tuple of (start_date_string, end_date_string, separator, separator_position)

    Raises:
        ValueError: If range cannot be split
    """
    # Try various separators (order matters - try more specific first)
    # Double hyphen before single hyphen to avoid matching ISO date hyphens
    # Special handling for ISO dates with -- separator
    separators = ['–', '—', '--', ' to ', ' - ']

    for sep in separators:
        if sep in text:
            pos = text.find(sep)
            parts = text.split(sep, 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip(), sep, pos

    # Try single hyphen, but be careful with ISO dates (YYYY-MM-DD)
    # Only split on hyphen if it's not part of an ISO date pattern
    # Strategy: Find hyphens that aren't surrounded by digits on both sides in a date-like pattern
    # Look for year-year patterns like "1500-1600" but not "2020-01-15"
    hyphen_pattern = r'^(\d{4})-(\d{4})$'  # Simple year-to-year range
    if re.match(hyphen_pattern, text):
        parts = text.split('-', 1)
        return parts[0].strip(), parts[1].strip(), '-', text.find('-')

    raise ValueError(f"Could not find date range separator in: {text}")


def _process_date_since(span: BeautifulSoup, soup: BeautifulSoup) -> None:
    """
    Process a .date-since span to add time-since subscript.

    Handles BC/BCE dates specially.

    Args:
        span: The span element with class="date-since"
        soup: BeautifulSoup instance
    """
    text = span.get_text()

    try:
        # Check if it's a date range (use end date for time-since)
        try:
            start_str, end_str, _, _ = _split_date_range(text)
            date_str = end_str
        except ValueError:
            # Not a range, parse as single date
            date_str = text

        # Try to parse the date
        try:
            date = _parse_date(date_str)
            years_ago = _calculate_years_ago(date)
        except ValueError as e:
            # Check if it's a BC date
            if str(e).startswith("BC_DATE:"):
                bc_year = int(str(e).split(":", 1)[1])
                # BC years ago = BC year + current year
                # Example: 984 BCE + 2025 AD = 3009 years ago
                # Example: 200,000 BC + 2025 AD = 202,025 years ago
                years_ago = bc_year + datetime.now().year
            else:
                raise

        ya_text = _years_ago_text(years_ago)

        # Create subscript
        sub = soup.new_tag("sub")
        sub.string = ya_text
        span.append(sub)

    except ValueError as e:
        # If parsing fails, leave the span unchanged
        if not str(e).startswith("BC_DATE:"):
            print(f"Warning: Could not parse date-since: {text} - {e}")


def _process_date_range(span: BeautifulSoup, soup: BeautifulSoup) -> None:
    """
    Process a .date-range span to add duration subscript.

    Converts the separator to an em dash and wraps it with duration in subsup.
    Adds a title attribute with human-readable description.

    Args:
        span: The span element with class="date-range"
        soup: BeautifulSoup instance
    """
    text = span.get_text()

    try:
        start_str, end_str, separator, sep_pos = _split_date_range(text)

        # Try to parse both dates, handling BC dates
        try:
            start_date = _parse_date(start_str)
            start_is_bc = False
        except ValueError as e:
            if str(e).startswith("BC_DATE:"):
                start_bc_year = int(str(e).split(":", 1)[1])
                start_is_bc = True
                start_date = None
            else:
                raise

        try:
            end_date = _parse_date(end_str)
            end_is_bc = False
        except ValueError as e:
            if str(e).startswith("BC_DATE:"):
                end_bc_year = int(str(e).split(":", 1)[1])
                end_is_bc = True
                end_date = None
            else:
                raise

        # Calculate duration based on date types
        if start_is_bc and end_is_bc:
            # Both BC: duration is difference between BC years
            duration_years = abs(start_bc_year - end_bc_year)
        elif start_is_bc and not end_is_bc:
            # BC to AD: add BC year + AD year (accounting for no year 0)
            duration_years = start_bc_year + end_date.year - 1
        elif not start_is_bc and not end_is_bc:
            # Both AD: normal calculation
            duration_years = _calculate_years_between(start_date, end_date)
        else:
            # AD to BC doesn't make sense
            raise ValueError("Date range cannot go from AD to BC")

        duration_text = _years_ago_text(duration_years, is_duration=True)

        # Build title attribute
        years_word = "year" if duration_years == 1 else "years"
        title = f"The date range {start_str}–{end_str} lasted {duration_years:,} {years_word}."
        span["title"] = title

        # Clear the span content
        span.clear()

        # Add start date
        span.append(NavigableString(start_str))

        # Create subsup wrapper for the separator and duration
        subsup = soup.new_tag("span")
        subsup["class"] = ["subsup"]

        # Create superscript with en dash (standard for date ranges)
        sup = soup.new_tag("sup")
        sup.string = "–"

        # Create subscript with duration
        sub = soup.new_tag("sub")
        sub.string = duration_text

        subsup.append(sup)
        subsup.append(sub)
        span.append(subsup)

        # Add end date
        span.append(NavigableString(end_str))

    except ValueError as e:
        print(f"Warning: Could not parse date-range: {text} - {e}")


def _process_date_range_since(span: BeautifulSoup, soup: BeautifulSoup) -> None:
    """
    Process a .date-range-since span to add both duration and time-since subscripts.

    Converts the separator to an em dash, adds duration, and adds time-since.
    Adds the 'date-range' class and a title attribute with human-readable description.

    Args:
        span: The span element with class="date-range-since"
        soup: BeautifulSoup instance
    """
    text = span.get_text()

    try:
        start_str, end_str, separator, sep_pos = _split_date_range(text)

        # Try to parse both dates, handling BC dates
        try:
            start_date = _parse_date(start_str)
            start_is_bc = False
        except ValueError as e:
            if str(e).startswith("BC_DATE:"):
                start_bc_year = int(str(e).split(":", 1)[1])
                start_is_bc = True
                start_date = None
            else:
                raise

        try:
            end_date = _parse_date(end_str)
            end_is_bc = False
        except ValueError as e:
            if str(e).startswith("BC_DATE:"):
                end_bc_year = int(str(e).split(":", 1)[1])
                end_is_bc = True
                end_date = None
            else:
                raise

        # Calculate duration based on date types
        if start_is_bc and end_is_bc:
            # Both BC: duration is difference between BC years
            duration_years = abs(start_bc_year - end_bc_year)
        elif start_is_bc and not end_is_bc:
            # BC to AD: add BC year + AD year (accounting for no year 0)
            duration_years = start_bc_year + end_date.year - 1
        elif not start_is_bc and not end_is_bc:
            # Both AD: normal calculation
            duration_years = _calculate_years_between(start_date, end_date)
        else:
            # AD to BC doesn't make sense
            raise ValueError("Date range cannot go from AD to BC")

        duration_text = _years_ago_text(duration_years, is_duration=True)

        # Calculate years ago
        if end_is_bc:
            # BC years ago = BC year + current year
            # Example: 984 BCE + 2025 AD = 3009 years ago
            years_ago = end_bc_year + datetime.now().year
        else:
            years_ago = _calculate_years_ago(end_date)
        ya_text = _years_ago_text(years_ago)

        # Add 'date-range' class alongside 'date-range-since'
        current_classes = span.get("class", [])
        if "date-range" not in current_classes:
            current_classes.append("date-range")
            span["class"] = current_classes

        # Build title attribute
        duration_word = "year" if duration_years == 1 else "years"
        ya_word = "year" if years_ago == 1 else "years"
        title = f"The date range {start_str}–{end_str} lasted {duration_years:,} {duration_word}, ending {years_ago:,} {ya_word} ago."
        span["title"] = title

        # Clear the span content
        span.clear()

        # Add start date
        span.append(NavigableString(start_str))

        # Create subsup wrapper for the separator and duration
        subsup = soup.new_tag("span")
        subsup["class"] = ["subsup"]

        # Create superscript with en dash (standard for date ranges)
        sup = soup.new_tag("sup")
        sup.string = "–"

        # Create subscript with duration
        sub_duration = soup.new_tag("sub")
        sub_duration.string = duration_text

        subsup.append(sup)
        subsup.append(sub_duration)
        span.append(subsup)

        # Add end date
        span.append(NavigableString(end_str))

        # Add time-since subscript
        sub_ya = soup.new_tag("sub")
        sub_ya.string = ya_text
        span.append(sub_ya)

    except ValueError as e:
        if not str(e).startswith("BC_DATE:"):
            print(f"Warning: Could not parse date-range-since: {text} - {e}")


def date_enhancer_v2(html: str, context: dict) -> str:
    """
    Process explicitly marked dates with markdown syntax.

    Supported classes:
    - .date-since: Adds time-since subscript
    - .date-range: Adds duration subscript between dates (em dash separator)
    - .date-range-since: Adds both duration and time-since (em dash separator)

    Args:
        html: HTML string to process
        context: Context dictionary (not used)

    Returns:
        Processed HTML with enhanced dates
    """
    soup = BeautifulSoup(html, "html.parser")

    # Process each type of date span

    # Process .date-range-since first (most complex)
    for span in soup.find_all("span", class_="date-range-since"):
        _process_date_range_since(span, soup)

    # Process .date-range (duration only)
    for span in soup.find_all("span", class_="date-range"):
        # Skip if already processed as date-range-since
        if "date-range-since" not in span.get("class", []):
            _process_date_range(span, soup)

    # Process .date-since (time-since only)
    for span in soup.find_all("span", class_="date-since"):
        # Skip if already processed as date-range or date-range-since
        if "date-range" not in span.get("class", []) and "date-range-since" not in span.get("class", []):
            _process_date_since(span, soup)

    return str(soup)


def date_enhancer_v2_default(html: str, context: dict) -> str:
    """
    Default configuration for date_enhancer_v2.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return date_enhancer_v2(html, context)
