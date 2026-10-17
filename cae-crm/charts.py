"""Server-rendered inline SVG charts, so the dashboard needs no JavaScript library."""

from markupsafe import Markup, escape

from ukfmt import money, money_short


def _smooth_path(pts, floor):
    """Catmull-Rom spline through pts, converted to cubic Bezier segments."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(floor, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(floor, p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def revenue_chart(series, target, width=1000, height=320):
    """series: list of (label, pence). Draws won revenue against a dashed target."""
    left, right, top, bottom = 64, 16, 16, 36
    plot_w, plot_h = width - left - right, height - top - bottom
    step = 5_000_000  # gridline every £50K
    peak = max([v for _, v in series] + [target]) * 1.15
    y_max = max(step, -(-int(peak) // step) * step)

    def x(i):
        return left + plot_w * i / max(1, len(series) - 1)

    def y(v):
        return top + plot_h * (1 - v / y_max)

    floor = y(0)
    pts = [(x(i), y(v)) for i, (_, v) in enumerate(series)]
    line = _smooth_path(pts, floor)
    area = f"{line} L{pts[-1][0]:.1f},{floor:.1f} L{pts[0][0]:.1f},{floor:.1f} Z"

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Won revenue by month against target">',
             '<defs><linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="var(--accent)" stop-opacity=".28"/>'
             '<stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>']
    grid_lines = 4
    for g in range(grid_lines + 1):
        v = y_max * g / grid_lines
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="axis" x="{left - 10}" y="{y(v) + 4:.1f}" text-anchor="end">{money_short(v)}</text>')
    parts.append(f'<path d="{area}" fill="url(#revFill)"/>')
    parts.append(f'<line class="target" x1="{left}" x2="{width - right}" y1="{y(target):.1f}" y2="{y(target):.1f}"/>')
    parts.append(f'<path class="line" d="{line}"/>')
    label_every = 1 if len(series) <= 6 else 2
    for i, ((label, v), (px, py)) in enumerate(zip(series, pts)):
        hit = "hit" if v >= target else ""
        parts.append(f'<g class="pt {hit}"><circle cx="{px:.1f}" cy="{py:.1f}" r="5"/>'
                     f'<title>{escape(label)}: {money(v)}</title></g>')
        if i % label_every == 0 or i == len(series) - 1:
            parts.append(f'<text class="axis" x="{px:.1f}" y="{height - 10}" text-anchor="middle">{escape(label)}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


def gauge(pct, size=200):
    """Half-ring progress gauge; pct may exceed 100."""
    r, stroke = size * 0.4, size * 0.09
    cx, cy = size / 2, size * 0.52
    arc = f"M{cx - r:.1f},{cy:.1f} A{r:.1f},{r:.1f} 0 0 1 {cx + r:.1f},{cy:.1f}"
    shown = max(0, min(100, pct))
    return Markup(
        f'<svg class="gauge" viewBox="0 0 {size} {size * 0.58:.0f}" role="img" aria-label="{pct:.0f}% of quota">'
        f'<path d="{arc}" pathLength="100" class="gauge-track" stroke-width="{stroke:.1f}"/>'
        f'<path d="{arc}" pathLength="100" class="gauge-fill" stroke-width="{stroke:.1f}" '
        f'stroke-dasharray="{shown:.1f} 100"/></svg>'
    )
