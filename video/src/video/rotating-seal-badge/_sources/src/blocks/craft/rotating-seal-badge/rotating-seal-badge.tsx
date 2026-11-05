// Built with Remotion - https://remotion.pro/license
import React, { useId } from "react";
import type { z } from "zod";
import { AbsoluteFill, Img, useCurrentFrame } from "remotion";
import { brandFontStack, fitFontSize, useLayout, withAlpha } from "../../../kit/index";
import { SAMPLE_LOGO } from "../_lib/samples";
import type { schema } from "./rotating-seal-badge.schema";

const smooth = (x: number) => { const t = Math.max(0, Math.min(1, x)); return t * t * (3 - 2 * t); };
export const Component: React.FC<z.infer<typeof schema>> = ({ logo, text, action, destination, primary, secondary, color, background, fontFamily }) => {
  const f = useCurrentFrame();
  const { width: w, height: h, portrait } = useLayout();
  const s = Math.min(w, h), cx = w / 2, cy = h * (portrait ? .42 : .43);
  const id = useId().replace(/:/g, ""), family = brandFontStack(fontFamily);
  const ease = smooth(f / 86), press = Math.max(0, f - 88);
  const pulse = f < 88 ? 0 : Math.sin(press * .25) * Math.exp(-press / 8);
  const r = s * (portrait ? .34 : .32), scale = 1 + (1 - ease) * .65 - pulse * .035;
  const angle = (1 - ease) * 210 - 12 * (1 - smooth((f - 86) / 24));
  const fs = h * (portrait ? .032 : .036);
  const points = Array.from({ length: 160 }, (_, i) => {
    const a = i / 160 * Math.PI * 2;
    const rad = r * (1.13 + .017 * Math.cos(a * 40));
    return `${cx + Math.cos(a) * rad},${cy + Math.sin(a) * rad}`;
  }).join(" ");
  const inner = r * .75;
  const buttonW = s * .49, buttonH = s * .15;
  const actionFont = fitFontSize({ chars: action.length, boxW: buttonW * .73, boxH: buttonH * .84, lines: 2, max: h * (portrait ? .034 : .034), min: h * (portrait ? .03 : .019), lineHeight: 1.2 });
  const destinationFont = fitFontSize({ chars: destination.length, boxW: w * .72, boxH: h * .12, lines: portrait ? 2 : 1, max: h * (portrait ? .037 : .035), min: h * (portrait ? .031 : .019), lineHeight: 1.25 });
  const contentIn = smooth((f - 55) / 28);
  return <AbsoluteFill style={{ background: background === "transparent" ? undefined : background, fontFamily: family, color }}>
    <svg width={w} height={h} style={{ position: "absolute", inset: 0 }}>
      <defs><path id={`${id}ring`} d={`M${cx},${cy - r} A${r},${r} 0 1 1 ${cx - .01},${cy - r}`} /></defs>
      <g transform={`translate(${cx} ${cy}) scale(${scale}) rotate(${angle}) translate(${-cx} ${-cy})`} opacity={smooth(f / 12)}>
        <polygon points={points} fill={withAlpha(primary, .055)} stroke={primary} strokeWidth={s * .0024} />
        <circle cx={cx} cy={cy} r={inner} fill="none" stroke={withAlpha(primary, .7)} strokeWidth={s * .002} />
        <text data-21st-slot="text" fill={color} fontFamily={family} fontSize={fs} fontWeight={600} textLength={r * Math.PI * 2 * .96} lengthAdjust="spacingAndGlyphs">
          <textPath href={`#${id}ring`} startOffset="2%">{text}</textPath>
        </text>
      </g>
      {f >= 88 && f < 113 && <circle cx={cx} cy={cy} r={r * (1.16 + press * .007)} fill="none" stroke={withAlpha(secondary, .65 * (1 - press / 25))} strokeWidth={s * .003} />}
    </svg>
    <Img src={logo || SAMPLE_LOGO} style={{ position: "absolute", left: cx - s * .14, top: cy - s * .23, width: s * .28, height: s * .25, objectFit: "contain", opacity: contentIn, transform: `scale(${.88 + .12 * contentIn})` }} />
    <div style={{ position: "absolute", left: cx - buttonW / 2, top: cy + s * .06, width: buttonW, minHeight: buttonH, boxSizing: "border-box", padding: `${s * .012}px ${s * .022}px`, display: "flex", alignItems: "center", justifyContent: "center", gap: s * .015, borderRadius: s * .08, border: `${s * .0025}px solid ${primary}`, background: withAlpha(primary, .09), opacity: contentIn, transform: `scale(${1 - pulse * .02})` }}>
      <div data-21st-slot="action" style={{ flex: 1, textAlign: "center", fontSize: actionFont, lineHeight: 1.2, fontWeight: 600, overflowWrap: "anywhere" }}>{action}</div>
      <svg width={s * .05} height={s * .05} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}><path d="M5 12h14m-6-6 6 6-6 6" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </div>
    {destination && <div data-21st-slot="destination" style={{ position: "absolute", left: w * .14, top: h * (portrait ? .81 : .85), width: w * .72, textAlign: "center", fontSize: destinationFont, lineHeight: 1.25, opacity: smooth((f - 98) / 22), color }}>{destination}</div>}
  </AbsoluteFill>;
};
