"""PRISMA 2020 flow diagram generator — pure SVG output, no external dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape


@dataclass
class PRISMAData:
    """Input data for PRISMA 2020 flow diagram generation."""

    databases_searched: list[str] = field(default_factory=list)
    total_identified: int = 0
    other_sources: int = 0
    duplicates_removed: int = 0
    records_screened: int = 0
    records_excluded: int = 0
    full_text_assessed: int = 0
    full_text_excluded: int = 0
    exclusion_reasons: dict[str, int] | None = None  # reason -> count
    studies_included: int = 0
    uncertain_count: int = 0


# ---------------------------------------------------------------------------
# SVG drawing primitives
# ---------------------------------------------------------------------------

_SVG_NS = "http://www.w3.org/2000/svg"

# Colours
_CLR_SECTION_BG = "#2563eb"
_CLR_SECTION_TEXT = "#ffffff"
_CLR_BOX_FILL = "#f8fafc"
_CLR_BOX_BORDER = "#94a3b8"
_CLR_EXCL_FILL = "#fef3c7"
_CLR_EXCL_BORDER = "#f59e0b"
_CLR_TEXT = "#1e293b"
_CLR_ARROW = "#64748b"
_CLR_UNCERTAIN_FILL = "#ede9fe"
_CLR_UNCERTAIN_BORDER = "#8b5cf6"

# Layout constants
_MAIN_BOX_W = 300
_SIDE_BOX_W = 240
_BOX_RX = 6
_LINE_HEIGHT = 18
_PADDING_X = 16
_PADDING_Y = 12
_SECTION_H = 30
_GAP_Y = 40
_GAP_X = 60
_FONT_BODY = 13
_FONT_SUB = 11
_FONT_HEADER = 15
_ARROW_SIZE = 7


def _text_lines(label: str, count: int, sub_items: list[str] | None = None) -> list[str]:
    """Build the text lines for a box."""
    lines = [f"{escape(label)}"]
    if count >= 0:
        lines[0] += f" (n={count})"
    if sub_items:
        for item in sub_items:
            lines.append(f"  {escape(item)}")
    return lines


def _box_height(n_lines: int) -> int:
    """Calculate box height based on number of text lines."""
    return _PADDING_Y * 2 + n_lines * _LINE_HEIGHT + 4


def _render_box(
    x: int,
    y: int,
    w: int,
    lines: list[str],
    *,
    fill: str = _CLR_BOX_FILL,
    border: str = _CLR_BOX_BORDER,
    bold_first: bool = True,
) -> tuple[str, int]:
    """Render a rounded-rectangle box with text.  Returns (svg_fragment, height)."""
    h = _box_height(len(lines))
    parts: list[str] = []
    # Drop shadow
    parts.append(
        f'<rect x="{x + 2}" y="{y + 2}" width="{w}" height="{h}" rx="{_BOX_RX}" fill="#e2e8f0" opacity="0.4"/>'
    )
    # Box
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
        f'rx="{_BOX_RX}" fill="{fill}" stroke="{border}" stroke-width="1.5"/>'
    )
    # Text
    ty = y + _PADDING_Y + _FONT_BODY
    for i, line in enumerate(lines):
        weight = "bold" if (bold_first and i == 0) else "normal"
        font_size = _FONT_BODY if i == 0 else _FONT_SUB
        parts.append(
            f'<text x="{x + _PADDING_X}" y="{ty}" '
            f'font-family="system-ui, Arial, sans-serif" font-size="{font_size}" '
            f'fill="{_CLR_TEXT}" font-weight="{weight}">{line}</text>'
        )
        ty += _LINE_HEIGHT
    return "\n".join(parts), h


def _render_section_header(x: int, y: int, w: int, label: str) -> str:
    """Render a coloured section header bar."""
    parts: list[str] = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{_SECTION_H}" rx="{_BOX_RX}" fill="{_CLR_SECTION_BG}"/>',
        f'<text x="{x + _PADDING_X}" y="{y + _SECTION_H // 2 + 5}" '
        f'font-family="system-ui, Arial, sans-serif" font-size="{_FONT_HEADER}" '
        f'fill="{_CLR_SECTION_TEXT}" font-weight="bold">{escape(label)}</text>',
    ]
    return "\n".join(parts)


def _render_arrow_down(x: int, y1: int, y2: int) -> str:
    """Vertical arrow from (x, y1) to (x, y2)."""
    a = _ARROW_SIZE
    return (
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - a}" '
        f'stroke="{_CLR_ARROW}" stroke-width="1.5"/>\n'
        f'<polygon points="{x},{y2} {x - a},{y2 - a} {x + a},{y2 - a}" '
        f'fill="{_CLR_ARROW}"/>'
    )


def _render_arrow_right(x1: int, y: int, x2: int) -> str:
    """Horizontal arrow from (x1, y) to (x2, y)."""
    a = _ARROW_SIZE
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2 - a}" y2="{y}" '
        f'stroke="{_CLR_ARROW}" stroke-width="1.5"/>\n'
        f'<polygon points="{x2},{y} {x2 - a},{y - a} {x2 - a},{y + a}" '
        f'fill="{_CLR_ARROW}"/>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_prisma_svg(data: PRISMAData, width: int = 800, height: int = 900) -> str:
    """Generate a PRISMA 2020 flow diagram as an SVG string.

    The diagram uses a simplified single-column layout (centre main flow with
    right-side exclusion boxes) which is the most commonly used PRISMA 2020
    variant for journal publications.

    Returns a complete SVG document as a string.
    """
    fragments: list[str] = []
    main_x = 40
    side_x = main_x + _MAIN_BOX_W + _GAP_X
    cursor_y = 20

    # ── IDENTIFICATION section ──────────────────────────────────────
    total_width = side_x + _SIDE_BOX_W + 40
    fragments.append(_render_section_header(main_x, cursor_y, total_width - main_x - 40, "Identification"))
    cursor_y += _SECTION_H + 16

    # Box 1 — Records identified
    db_sub: list[str] = []
    if data.databases_searched:
        for db in data.databases_searched:
            db_sub.append(escape(db))
    if data.other_sources:
        db_sub.append(f"Other sources (n={data.other_sources})")
    id_lines = _text_lines("Records identified from databases", data.total_identified, db_sub)
    box_svg, box_h = _render_box(main_x, cursor_y, _MAIN_BOX_W, id_lines)
    fragments.append(box_svg)
    box1_bottom = cursor_y + box_h
    cursor_y = box1_bottom + _GAP_Y

    # Arrow down to dedup box
    arrow_x = main_x + _MAIN_BOX_W // 2
    fragments.append(_render_arrow_down(arrow_x, box1_bottom, cursor_y))

    # ── Box 2 — After duplicates removed ────────────────────────────
    after_dedup = data.total_identified - data.duplicates_removed + data.other_sources
    if after_dedup < 0:
        after_dedup = data.records_screened if data.records_screened else 0
    dedup_lines = _text_lines("Records after duplicates removed", after_dedup)
    box_svg, box_h = _render_box(main_x, cursor_y, _MAIN_BOX_W, dedup_lines)
    fragments.append(box_svg)
    box2_cy = cursor_y + box_h // 2
    box2_bottom = cursor_y + box_h

    # Side box — Duplicates removed
    dup_lines = _text_lines("Duplicates removed", data.duplicates_removed)
    side_svg, side_h = _render_box(
        side_x,
        cursor_y,
        _SIDE_BOX_W,
        dup_lines,
        fill=_CLR_EXCL_FILL,
        border=_CLR_EXCL_BORDER,
    )
    fragments.append(side_svg)
    # Arrow right
    fragments.append(_render_arrow_right(main_x + _MAIN_BOX_W, box2_cy, side_x))
    cursor_y = box2_bottom + _GAP_Y

    # ── SCREENING section ──────────────────────────────────────────
    fragments.append(_render_section_header(main_x, cursor_y, total_width - main_x - 40, "Screening"))
    cursor_y += _SECTION_H + 16

    # Arrow down
    fragments.append(_render_arrow_down(arrow_x, cursor_y - 16, cursor_y))

    # Box 3 — Records screened
    screened_lines = _text_lines("Records screened", data.records_screened)
    box_svg, box_h = _render_box(main_x, cursor_y, _MAIN_BOX_W, screened_lines)
    fragments.append(box_svg)
    box3_cy = cursor_y + box_h // 2
    box3_bottom = cursor_y + box_h

    # Side box — Records excluded at screening
    excl_screen_lines = _text_lines("Records excluded", data.records_excluded)
    side_svg, side_h = _render_box(
        side_x,
        cursor_y,
        _SIDE_BOX_W,
        excl_screen_lines,
        fill=_CLR_EXCL_FILL,
        border=_CLR_EXCL_BORDER,
    )
    fragments.append(side_svg)
    fragments.append(_render_arrow_right(main_x + _MAIN_BOX_W, box3_cy, side_x))
    cursor_y = box3_bottom + _GAP_Y

    # Arrow down
    fragments.append(_render_arrow_down(arrow_x, cursor_y - _GAP_Y + box_h, cursor_y))

    # Box 4 — Full-text assessed for eligibility
    ft_lines = _text_lines("Full-text articles assessed for eligibility", data.full_text_assessed)
    box_svg, box_h = _render_box(main_x, cursor_y, _MAIN_BOX_W, ft_lines)
    fragments.append(box_svg)
    box4_cy = cursor_y + box_h // 2
    box4_bottom = cursor_y + box_h

    # Side box — Full-text excluded (with reasons)
    reason_sub: list[str] = []
    if data.exclusion_reasons:
        for reason, cnt in data.exclusion_reasons.items():
            reason_sub.append(f"{escape(reason)} (n={cnt})")
    ft_excl_lines = _text_lines("Full-text articles excluded", data.full_text_excluded, reason_sub)
    side_svg, side_h = _render_box(
        side_x,
        cursor_y,
        _SIDE_BOX_W,
        ft_excl_lines,
        fill=_CLR_EXCL_FILL,
        border=_CLR_EXCL_BORDER,
    )
    fragments.append(side_svg)
    fragments.append(_render_arrow_right(main_x + _MAIN_BOX_W, box4_cy, side_x))
    side_bottom = cursor_y + side_h
    cursor_y = max(box4_bottom, side_bottom) + _GAP_Y

    # ── INCLUDED section ────────────────────────────────────────────
    fragments.append(_render_section_header(main_x, cursor_y, total_width - main_x - 40, "Included"))
    cursor_y += _SECTION_H + 16

    # Arrow down
    fragments.append(_render_arrow_down(arrow_x, cursor_y - 16, cursor_y))

    # Box 5 — Studies included
    incl_lines = _text_lines("Studies included in synthesis", data.studies_included)
    box_svg, box_h = _render_box(main_x, cursor_y, _MAIN_BOX_W, incl_lines)
    fragments.append(box_svg)
    box5_bottom = cursor_y + box_h
    cursor_y = box5_bottom

    # Optional: Uncertain box
    if data.uncertain_count > 0:
        cursor_y += _GAP_Y // 2
        fragments.append(_render_arrow_down(arrow_x, box5_bottom, cursor_y))
        unc_lines = _text_lines("Studies with uncertain status", data.uncertain_count)
        unc_svg, unc_h = _render_box(
            main_x,
            cursor_y,
            _MAIN_BOX_W,
            unc_lines,
            fill=_CLR_UNCERTAIN_FILL,
            border=_CLR_UNCERTAIN_BORDER,
        )
        fragments.append(unc_svg)
        cursor_y += unc_h

    # ── Assemble SVG ────────────────────────────────────────────────
    final_height = cursor_y + 30
    computed_width = max(width, total_width)

    svg_body = "\n".join(fragments)
    svg = (
        f'<svg xmlns="{_SVG_NS}" width="{computed_width}" height="{final_height}" '
        f'viewBox="0 0 {computed_width} {final_height}" '
        f'style="background:#ffffff">\n'
        f"  <style>\n"
        f"    text {{ user-select: text; }}\n"
        f"  </style>\n"
        f"  <!-- PRISMA 2020 Flow Diagram -->\n"
        f"  <!-- Generated by Evidentia -->\n"
        f"{svg_body}\n"
        f"</svg>"
    )
    return svg


def generate_prisma_png_bytes(data: PRISMAData) -> bytes | None:
    """Try to convert SVG to PNG using cairosvg if available.

    Returns PNG bytes, or ``None`` if *cairosvg* is not installed.
    """
    try:
        import cairosvg  # type: ignore[import-untyped]

        svg = generate_prisma_svg(data)
        return cairosvg.svg2png(bytestring=svg.encode("utf-8"))  # type: ignore[no-any-return]
    except ImportError:
        return None
