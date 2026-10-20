"""Small server-rendered charts. The interactive revenue chart is drawn in static/app.js."""

from markupsafe import Markup, escape


def sparkline(values, width=240, height=38):
    """Thin trend line that stretches to its card's width."""
    if len(values) < 2:
        return Markup("")
    values = [float(v) for v in values]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(width * i / (len(values) - 1), height - 2 - (height - 6) * (v - lo) / span) for i, v in enumerate(values)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">'
        f'<path class="spark-line" d="{line}"/></svg>'
    )


def stacked_bar(segments, label):
    """One bar split by share. segments: list of (value, css colour, title)."""
    total = sum(float(v) for v, _, _ in segments)
    parts = [f'<div class="stack-bar" role="img" aria-label="{escape(label)}">']
    for value, colour, title in segments:
        if total and float(value) > 0:
            parts.append(f'<i style="flex: {float(value) / total:.4f}; background: {colour}" title="{escape(title)}"></i>')
    parts.append("</div>")
    return Markup("".join(parts))
