// Built with Remotion - https://remotion.pro/license
import { interpolate, spring } from "remotion";

type SpringConfig = Parameters<typeof spring>[0]["config"];

// Apple-style springs: a touch of overshoot, quick settle. One thing moves at
// a time, ~400-600ms moves.
export const APPLE = { damping: 16, stiffness: 120, mass: 0.9 } as const;
export const APPLE_SOFT = { damping: 22, stiffness: 90, mass: 1 } as const;
export const APPLE_SNAPPY = { damping: 18, stiffness: 170, mass: 0.8 } as const;

/** interpolate with both ends clamped (the 99% case). */
export function ramp(f: number, inR: [number, number], outR: [number, number]): number {
  // Zero-length exit phases are an intentional hold. Staggered exits may start
  // after the clip end, so a reversed interval must also stay at its first value.
  if (inR[1] <= inR[0]) return f < inR[0] ? outR[0] : outR[1];
  return interpolate(f, inR, outR, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
}

/** Fade in over [inS,inE]; optionally back out over [outS,outE]. */
export function band(f: number, inS: number, inE: number, outS?: number, outE?: number): number {
  const fadeIn = ramp(f, [inS, inE], [0, 1]);
  if (outS == null || outE == null) return fadeIn;
  return Math.min(fadeIn, ramp(f, [outS, outE], [1, 0]));
}

/** 0->1 spring starting at `delay`, 0 before it. */
export function springIn(frame: number, fps: number, delay = 0, config: SpringConfig = APPLE): number {
  return spring({ frame: frame - delay, fps, config });
}

/** Spring-eased lerp from `from` to `to`, starting at `delay`. */
export function springLerp(
  frame: number,
  fps: number,
  from: number,
  to: number,
  delay = 0,
  config: SpringConfig = APPLE,
): number {
  return from + (to - from) * springIn(frame, fps, delay, config);
}

/** Spring-eased rise: starts `px` below and settles to 0. */
export function rise(f: number, fps: number, start: number, px = 18): number {
  return (1 - springIn(f, fps, start, APPLE)) * px;
}

/** Phase in [0,1) that closes exactly at `durationInFrames`, so loops are seamless. */
export function loopPhase(frame: number, durationInFrames: number, cycles = 1): number {
  return ((frame / durationInFrames) * cycles) % 1;
}

/** Cubic ease-out on a clamped 0..1 progress. */
export function easeOut(x: number): number {
  const t = Math.max(0, Math.min(1, x));
  return 1 - Math.pow(1 - t, 3);
}

/** Cubic ease-in-out on a clamped 0..1 progress. */
export function easeInOut(x: number): number {
  const t = Math.max(0, Math.min(1, x));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/** Exponential ease-out (fast start, long settle): counters, cursor glides. */
export function expoOut(x: number): number {
  const t = Math.max(0, Math.min(1, x));
  return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

/**
 * A color prop at some opacity. #rgb/#rrggbb/#rrggbbaa get an exact rgba();
 * rgb()/rgba()/named colors go through color-mix so they still work.
 */
export function withAlpha(color: string, a: number): string {
  const alpha = Math.max(0, Math.min(1, a));
  let hex = /^#([0-9a-f]{3,8})$/i.exec(color)?.[1];
  if (hex && hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  if (hex && (hex.length === 6 || hex.length === 8)) {
    const n = parseInt(hex.slice(0, 6), 16);
    const base = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${(alpha * base).toFixed(3)})`;
  }
  if (color === "transparent") return color;
  return `color-mix(in srgb, ${color} ${Math.round(alpha * 100)}%, transparent)`;
}

/** Relative luminance (0..1) of a hex color; 0 for anything else. Used to pick legible ink on an accent. */
export function luminance(color: string): number {
  let hex = /^#([0-9a-f]{3,8})$/i.exec(color)?.[1];
  if (!hex) return 0;
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const n = parseInt(hex.slice(0, 6), 16);
  const ch = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * ch((n >> 16) & 255) + 0.7152 * ch((n >> 8) & 255) + 0.0722 * ch(n & 255);
}

/** Black or white, whichever reads better on `bg`. */
export function inkOn(bg: string): string {
  return luminance(bg) > 0.45 ? "#0a0a0a" : "#ffffff";
}

/**
 * springIn that lands exactly on 1 once the residual wobble is invisible
 * (< 0.001). Held frames then carry no sub-pixel transforms, which GPU text
 * rasterization does not reproduce bit-for-bit (gate: determinism).
 */
export function springSnap(frame: number, fps: number, delay = 0, config: SpringConfig = APPLE): number {
  const s = springIn(frame, fps, delay, config);
  return Math.abs(1 - s) < 1e-3 ? 1 : s;
}
