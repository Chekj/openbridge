"""Output formatting utilities for mobile optimization."""

from __future__ import annotations

import re
from typing import Optional


def format_output(output: str, platform: str, max_length: Optional[int] = None) -> str:
    """Format output for specific platform.

    Args:
        output: Raw command output
        platform: Target platform (telegram, discord, etc.)
        max_length: Maximum length before truncation

    Returns:
        Formatted output string
    """
    # Remove ANSI escape codes
    output = strip_ansi(output)

    # Platform-specific formatting
    if platform == "telegram":
        max_length = max_length or 4000
        output = format_for_telegram(output, max_length)
    elif platform == "discord":
        max_length = max_length or 2000
        output = format_for_discord(output, max_length)
    else:
        max_length = max_length or 4000
        output = truncate_output(output, max_length)

    return output


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def truncate_output(output: str, max_length: int, suffix: str = "\n... (truncated)") -> str:
    """Truncate output to max length."""
    if len(output) <= max_length:
        return output

    available = max_length - len(suffix)
    return output[:available] + suffix


def format_for_telegram(output: str, max_length: int = 4000) -> str:
    """Format output for Telegram."""
    output = truncate_output(output, max_length - 8)  # Account for code block
    return f"```\n{output}\n```"


def format_for_discord(output: str, max_length: int = 2000) -> str:
    """Format output for Discord."""
    output = truncate_output(output, max_length - 8)
    return f"```\n{output}\n```"


def paginate_output(output: str, page_size: int = 4000) -> list[str]:
    """Split output into pages.

    Args:
        output: Output to paginate
        page_size: Maximum size per page

    Returns:
        List of page strings
    """
    if len(output) <= page_size:
        return [output]

    pages = []
    lines = output.split("\n")
    current_page = ""

    for line in lines:
        if len(current_page) + len(line) + 1 > page_size:
            if current_page:
                pages.append(current_page)
            current_page = line
        else:
            if current_page:
                current_page += "\n"
            current_page += line

    if current_page:
        pages.append(current_page)

    return pages
