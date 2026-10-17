"""Small server-rendered SVGs. The interactive revenue chart is drawn in static/app.js."""

from markupsafe import Markup, escape


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


def sparkline(values, width=240, height=38):
    """Small filled trend line that stretches to its card's width."""
    if len(values) < 2:
        return Markup("")
    values = [float(v) for v in values]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(width * i / (len(values) - 1), height - 2 - (height - 6) * (v - lo) / span) for i, v in enumerate(values)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">'
        f'<path class="spark-area" d="{line} L{width},{height} L0,{height} Z"/>'
        f'<path class="spark-line" d="{line}"/></svg>'
    )


def donut(segments, size=150, stroke=18):
    """Ring split into segments. segments: list of (label, value, css colour, title)."""
    total = sum(float(v) for _, v, _, _ in segments) or 1
    r = (size - stroke) / 2 - 3
    c = size / 2
    gap = 0.8 if sum(1 for _, v, _, _ in segments if v) > 1 else 0  # small gap between segments, in % of the ring
    parts = [f'<svg class="donut" viewBox="0 0 {size} {size}" role="img" aria-label="Pipeline value by stage">'
             f'<circle cx="{c}" cy="{c}" r="{r}" class="ring-track" stroke-width="{stroke}"/>']
    offset = 0.0
    for label, value, colour, title in segments:
        pct = float(value) / total * 100
        if pct <= 0:
            continue
        length = max(pct - gap, 0.4)
        parts.append(f'<circle class="seg" cx="{c}" cy="{c}" r="{r}" stroke="{colour}" stroke-width="{stroke}" '
                     f'pathLength="100" stroke-dasharray="{length:.2f} {100 - length:.2f}" '
                     f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {c} {c})">'
                     f'<title>{escape(title)}</title></circle>')
        offset += pct
    parts.append("</svg>")
    return Markup("".join(parts))
