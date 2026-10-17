"""Small server-rendered SVGs. The interactive revenue chart is drawn in static/app.js."""

from markupsafe import Markup


def ring(pct, size=132, stroke=12, label=None):
    """Full progress ring; pct may exceed 100, the arc caps at a full turn."""
    r = (size - stroke) / 2
    shown = max(0.0, min(100.0, pct))
    return Markup(
        f'<svg class="ring" viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'aria-label="{label or f"{pct:.0f}%"}">'
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" class="ring-track" stroke-width="{stroke}"/>'
        + (f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" class="ring-fill" stroke-width="{stroke}" '
           f'pathLength="100" stroke-dasharray="{shown:.1f} 100" transform="rotate(-90 {size / 2} {size / 2})"/>'
           if shown > 0 else "")  # a zero-length round-capped arc would still draw a dot
        + '</svg>'
    )


def sparkline(values, width=120, height=32):
    """Tiny trend line for a stat; values are any numbers."""
    if len(values) < 2:
        return Markup("")
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(width * i / (len(values) - 1), height - 3 - (height - 6) * (v - lo) / span) for i, v in enumerate(values)]
    d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    last_x, last_y = pts[-1]
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
        f'<path d="{d}"/><circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.6"/></svg>'
    )
