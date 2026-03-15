"""Tests for runtime theme generation (app/theme.py)."""
from app.theme import palette_css


def test_palette_css_default_colors_returns_empty():
    """Default colors produce no CSS override (the CSS file already has them)."""
    assert palette_css("#F2F0E9", "#D9523C") == ""


def test_palette_css_custom_colors_returns_css():
    """Non-default colors produce a :root block with CSS variable overrides."""
    css = palette_css("#1a1a2e", "#e94560")
    assert ":root {" in css
    assert "--color-primary:" in css
    assert ".dark {" in css
