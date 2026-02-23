"""Unit tests for the LaTeX template system."""

from __future__ import annotations

from evidentia.writing.templates import (
    TEMPLATES,
    get_template,
    list_templates,
    render_template,
)


def test_list_templates_returns_all():
    """list_templates() returns metadata for every template."""
    templates = list_templates()
    assert len(templates) == len(TEMPLATES)
    for t in templates:
        assert "id" in t
        assert "name" in t
        assert "description" in t
        assert "category" in t


def test_get_template_by_id():
    """get_template() returns full template dict with preamble and skeleton."""
    tmpl = get_template("article")
    assert tmpl is not None
    assert tmpl["id"] == "article"
    assert "\\documentclass" in tmpl["preamble"]
    assert "document" in tmpl["skeleton"]


def test_get_template_not_found():
    """get_template() returns None for unknown template IDs."""
    assert get_template("does_not_exist") is None
    assert get_template("") is None


def test_render_template():
    """render_template() produces a full LaTeX document."""
    rendered = render_template("article")
    assert "\\documentclass" in rendered
    assert "\\begin{document}" in rendered
    assert "\\end{document}" in rendered


def test_render_template_with_title():
    """render_template() substitutes the title into the skeleton."""
    rendered = render_template("ieee_conference", title="My Research Paper")
    assert "My Research Paper" in rendered
    assert "\\documentclass" in rendered


def test_render_template_fallback():
    """render_template() with unknown ID falls back to 'article'."""
    rendered = render_template("nonexistent_template", title="Fallback Test")
    assert "\\documentclass" in rendered


def test_all_templates_render():
    """Every template in TEMPLATES can render without error."""
    for template_id in TEMPLATES:
        rendered = render_template(template_id, title="Test Title")
        assert "\\documentclass" in rendered, f"Template {template_id} missing \\documentclass"
