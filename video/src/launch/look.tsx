// The launch film's look: a near-black stage lit by the product, film grain, and big type that builds word by word.
import React from "react";
import { AbsoluteFill, Audio, Easing, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, FONT } from "../theme";

export const D = {
  night: "#04060c",
  deep: "#0a1024",
  ink: "#f5f7ff",
  dim: "rgba(225,232,255,.62)",
  blue: C.blue,
  glow: "#3d7bff",
  yellow: C.yellow,
  coral: C.coralBright,
};

export const clamp = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
export const out = Easing.bezier(0.16, 1, 0.3, 1);       // fast start, long soft landing
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);
export const ramp = (f: number, a: number, b: number, ease = out) => interpolate(f, [a, b], [0, 1], { ...clamp, easing: ease });

// The stage: deep black with a pool of blue light that can breathe and move.
export const Stage: React.FC<{ light?: number; x?: number; y?: number; children?: React.ReactNode }> =
  ({ light = 1, x = 50, y = 62, children }) => (
    <AbsoluteFill style={{ background: D.night, overflow: "hidden" }}>
      <AbsoluteFill style={{ opacity: light,
        background: `radial-gradient(55% 45% at ${x}% ${y}%, rgba(61,123,255,.34), rgba(30,91,214,.10) 45%, transparent 72%)` }} />
      <AbsoluteFill style={{ opacity: light * 0.6,
        background: `radial-gradient(30% 20% at ${x}% ${y + 18}%, rgba(255,95,61,.10), transparent 70%)` }} />
      {children}
      <Grain />
      <AbsoluteFill style={{ pointerEvents: "none", background: "radial-gradient(120% 90% at 50% 50%, transparent 55%, rgba(0,0,0,.55))" }} />
    </AbsoluteFill>
  );

// Moving film grain keeps big dark areas from banding and gives the picture texture.
export const Grain: React.FC<{ opacity?: number }> = ({ opacity = 0.07 }) => {
  const f = useCurrentFrame();
  const seed = f % 8;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity, mixBlendMode: "overlay",
      backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' seed='${seed}' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")` }} />
  );
};

// A headline whose words arrive one after another: each rises out of a soft blur into sharp focus.
export const Words: React.FC<{
  text: string; at?: number; gap?: number; size?: number; color?: string; weight?: number;
  accent?: string[]; accentColor?: string; align?: "center" | "left"; width?: number; until?: number; lineHeight?: number;
}> = ({ text, at = 0, gap = 4, size = 120, color = D.ink, weight = 800, accent = [], accentColor = D.yellow,
  align = "center", width = 1600, until, lineHeight = 1.02 }) => {
  const f = useCurrentFrame();
  const leave = until === undefined ? 0 : ramp(f, until - 10, until, inOut);
  return (
    <div style={{ fontFamily: FONT, fontWeight: weight, fontSize: size, lineHeight, letterSpacing: "-0.045em",
      color, textAlign: align, maxWidth: width, display: "flex", flexWrap: "wrap",
      justifyContent: align === "center" ? "center" : "flex-start", columnGap: size * 0.26,
      opacity: 1 - leave, transform: `translateY(${-leave * 30}px)`, filter: leave ? `blur(${leave * 12}px)` : undefined }}>
      {text.split(" ").map((w, i) => {
        const t = ramp(f, at + i * gap, at + i * gap + 16);
        const clean = w.replace(/[.,?!]/g, "");
        return (
          <span key={i} style={{ display: "inline-block", opacity: t, color: accent.includes(clean) ? accentColor : undefined,
            transform: `translateY(${(1 - t) * size * 0.35}px) scale(${0.96 + t * 0.04})`, filter: `blur(${(1 - t) * 14}px)` }}>{w}</span>
        );
      })}
    </div>
  );
};

// The small label over a chapter headline: "01  Sales".
export const Kicker: React.FC<{ n: string; label: string; at?: number; size?: number }> = ({ n, label, at = 0, size = 34 }) => {
  const f = useCurrentFrame();
  const t = ramp(f, at, at + 18);
  const line = ramp(f, at + 4, at + 30);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 22, fontFamily: FONT, fontWeight: 700, fontSize: size,
      letterSpacing: "0.18em", textTransform: "uppercase", color: D.dim, opacity: t, transform: `translateY(${(1 - t) * 14}px)` }}>
      <span style={{ color: D.yellow }}>{n}</span>
      <span style={{ width: 80 * line, height: 2, background: "rgba(255,255,255,.35)" }} />
      <span>{label}</span>
    </div>
  );
};

// A white flash that bridges two shots on a hit.
export const Flash: React.FC<{ at: number; length?: number; strength?: number }> = ({ at, length = 10, strength = 0.85 }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [at - 2, at, at + length], [0, strength, 0], clamp);
  return o > 0 ? <AbsoluteFill style={{ background: "#eaf0ff", opacity: o, mixBlendMode: "screen" }} /> : null;
};

// Fades a whole shot in from and out to black.
export const Dip: React.FC<{ d: number; inF?: number; outF?: number; children: React.ReactNode }> = ({ d, inF = 8, outF = 8, children }) => {
  const f = useCurrentFrame();
  const o = Math.min(inF ? ramp(f, 0, inF, inOut) : 1, outF ? 1 - ramp(f, d - outF, d, inOut) : 1);
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

// A sound effect from public/sfx, played at a frame of the scene it sits in.
export const Sfx: React.FC<{ name: string; at?: number; volume?: number }> = ({ name, at = 0, volume = 1 }) => (
  <Sequence from={Math.round(at)} layout="none"><Audio src={staticFile(`sfx/${name}.wav`)} volume={volume} /></Sequence>
);

// A frosted chip that pops next to the product to name what just happened.
export const Chip: React.FC<{ text: string; at: number; tone?: "ok" | "blue" | "yellow"; size?: number; style?: React.CSSProperties }> =
  ({ text, at, tone = "ok", size = 30, style }) => {
    const f = useCurrentFrame();
    const t = ramp(f, at, at + 14);
    const dot = tone === "ok" ? "#3ddc97" : tone === "yellow" ? D.yellow : D.glow;
    return (
      <div style={{ position: "absolute", display: "flex", alignItems: "center", gap: 14, padding: `${size * 0.5}px ${size * 0.85}px`,
        borderRadius: 999, background: "rgba(14,20,40,.72)", border: "1px solid rgba(255,255,255,.16)", backdropFilter: "blur(14px)",
        boxShadow: "0 20px 60px rgba(0,0,0,.45)", fontFamily: FONT, fontWeight: 700, fontSize: size, color: D.ink, whiteSpace: "nowrap",
        opacity: t, transform: `translateY(${(1 - t) * 24}px) scale(${0.9 + t * 0.1})`, ...style }}>
        <span style={{ width: size * 0.4, height: size * 0.4, borderRadius: "50%", background: dot, boxShadow: `0 0 18px ${dot}` }} />
        {text}
        <Sfx name="pop" at={at} volume={0.5} />
      </div>
    );
  };
