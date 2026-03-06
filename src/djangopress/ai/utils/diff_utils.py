"""Utilities for detecting which sections changed between two HTML revisions."""
import re


def extract_sections(html):
    """Extract data-section blocks from HTML.

    Returns a dict mapping section name -> full section HTML.
    """
    sections = {}
    for match in re.finditer(
        r'<section[^>]*data-section="([^"]+)"[^>]*>.*?</section>',
        html,
        re.DOTALL,
    ):
        sections[match.group(1)] = match.group(0)
    return sections


def compute_section_changes(old_html, new_html):
    """Compare two HTML strings and return (added, removed, modified) section names."""
    old_sections = extract_sections(old_html)
    new_sections = extract_sections(new_html)

    old_keys = set(old_sections)
    new_keys = set(new_sections)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(
        k for k in old_keys & new_keys
        if old_sections[k] != new_sections[k]
    )
    return added, removed, modified


def build_change_summary(added, removed, modified):
    """Build a human-readable one-line summary of section changes."""
    parts = []
    if modified:
        parts.append(f"Modified sections: {', '.join(modified)}")
    if added:
        parts.append(f"Added sections: {', '.join(added)}")
    if removed:
        parts.append(f"Removed sections: {', '.join(removed)}")
    return '. '.join(parts) if parts else 'Minor changes applied'
