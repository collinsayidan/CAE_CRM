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


def donut(segments, figure, caption, label):
    """A ring split by share. segments: list of (value, css colour). The centre names the whole: a figure and a caption."""
    total = sum(float(v) for v, _ in segments)
    parts = [f'<svg class="donut" viewBox="0 0 42 42" role="img" aria-label="{escape(label)}">',
             '<circle class="donut-track" cx="21" cy="21" r="15.915"/>']
    start = 0.0
    shown = [(float(v), c) for v, c in segments if float(v) > 0]
    gap = 0.8 if len(shown) > 1 else 0
    for value, colour in shown:
        share = value / total * 100
        length = max(share - gap, 0.4)
        parts.append(f'<circle class="donut-seg" cx="21" cy="21" r="15.915" style="stroke: {colour}" '
                     f'stroke-dasharray="{length:.3f} {100 - length:.3f}" stroke-dashoffset="{25 - start:.3f}"/>')
        start += share
    parts.append(f'<text class="donut-figure" x="21" y="21.4" text-anchor="middle">{escape(figure)}</text>'
                 f'<text class="donut-caption" x="21" y="26" text-anchor="middle">{escape(caption)}</text></svg>')
    return Markup("".join(parts))
