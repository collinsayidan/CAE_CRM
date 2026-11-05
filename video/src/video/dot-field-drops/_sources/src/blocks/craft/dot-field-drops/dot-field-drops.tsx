// Built with Remotion - https://remotion.pro/license
import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import type { z } from "zod";
import { band, brandFontStack, easeInOut, easeOut, fitFontSize, luminance, springSnap, useLayout, withAlpha } from "../../../kit/index";
import { waitForBrandFonts } from "../../../kit/brand-fonts";
import { rng } from "../_lib/noise";
import type { schema } from "./dot-field-drops.schema";

type Props = z.infer<typeof schema>;

const TAU = Math.PI * 2;

// Timeline (frames at 30 fps). One drop per beat (18 frames = 100 bpm), a held breath, the last drop.
const BEATS = [14, 32, 50, 68, 86];
const BEAT_AMP = [0.8, 0.85, 0.9, 0.95, 1];
const LAST = 108;
const LAST_AMP = 1.55;
const HEAD = 112; // headline lifts on the last drop's first crest
const AMBIENT = 160; // after the settle the field keeps time with softer drops
const AMBIENT_EVERY = 36;
const AMBIENT_AMP = 0.55;
const FALL = 10; // frames a pebble takes to fall

// Waves, in world units (1 unit = one dot step).
const SPEED = 0.85;
const K = TAU / 6.4;
const FRONT = 2.4;
const TRAIL = 13;
const DAMP = 90;

// Dot buckets: color level x alpha level, so ~10k dots draw in a few dozen fills.
const NC = 25;
const ALPHAS = [0.14, 0.28, 0.44, 0.6, 0.8, 1];
const NA = ALPHAS.length;
const LH = 1.15;
const HEAD_SPRING = { damping: 11, stiffness: 120, mass: 0.8 } as const;

const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' seed='23' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.55'/></svg>\")";

type Drop = { t0: number; x: number; z: number; amp: number; big: boolean; seed: number };

type Field = {
  n: number;
  wx: Float32Array;
  wz: Float32Array;
  sx: Float32Array; // resting screen x
  sy: Float32Array; // resting screen y
  sp: Float32Array; // px per world unit at the dot's depth
  mul: Float32Array; // fog x headline calm
  delay: Float32Array; // wake-in delay (far rows first)
  cx: number;
  yh: number;
  a: number;
  F: number;
  zNear: number;
  zTop: number;
  ty: number; // headline centre
  blockW: number;
  blockH: number;
  size: number;
  impactX: number;
  impactY: number;
};

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

function ctx2d(c: HTMLCanvasElement): CanvasRenderingContext2D {
  // Software canvas: GPU promotion makes blur non bit-identical between renders.
  return c.getContext("2d", { willReadFrequently: true })!;
}

function sized(ref: React.MutableRefObject<HTMLCanvasElement | null>, w: number, h: number): HTMLCanvasElement {
  if (!ref.current) ref.current = document.createElement("canvas");
  if (ref.current.width !== w) ref.current.width = w;
  if (ref.current.height !== h) ref.current.height = h;
  return ref.current;
}

function reset(c: CanvasRenderingContext2D) {
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.globalCompositeOperation = "source-over";
  c.globalAlpha = 1;
  c.filter = "none";
}

function rgbOf(color: string): [number, number, number] | null {
  let hex = /^#([0-9a-f]{3,8})$/i.exec(color)?.[1];
  if (!hex) return null;
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  if (hex.length !== 6 && hex.length !== 8) return null;
  const n = parseInt(hex.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Mix two brand colors (hex); non-hex colors fall back to the nearer end. */
function mix(a: string, b: string, t: number): string {
  const ra = rgbOf(a);
  const rb = rgbOf(b);
  const k = clamp01(t);
  if (!ra || !rb) return k < 0.5 ? a : b;
  const c = [0, 1, 2].map((i) => Math.round(ra[i]! + (rb[i]! - ra[i]!) * k));
  return `#${((1 << 24) | (c[0]! << 16) | (c[1]! << 8) | c[2]!).toString(16).slice(1)}`;
}

/** Sum of damped ring packets (leading crest, trailing wake), plus a faint breathing swell. */
function makeWave(active: { x: number; z: number; R: number; A: number }[], f: number) {
  return (x: number, z: number, out: Float32Array) => {
    const p1 = 0.31 * x + 0.9 + f * 0.045;
    const p2 = 0.27 * z - f * 0.035;
    const s1 = Math.sin(p1);
    const s2 = Math.sin(p2);
    let h = 0.09 * s1 * s2;
    let gx = 0.09 * 0.31 * Math.cos(p1) * s2;
    let gz = 0.09 * 0.27 * s1 * Math.cos(p2);
    for (let i = 0; i < active.length; i++) {
      const s = active[i]!;
      const dx = x - s.x;
      const dz = z - s.z;
      const r = Math.sqrt(dx * dx + dz * dz) + 1e-4;
      const phi = r - s.R;
      if (phi > FRONT * 3.2 || phi < -TRAIL * 5) continue;
      const e = phi > 0 ? Math.exp(-(phi / FRONT) * (phi / FRONT)) : Math.exp(phi / TRAIL);
      const amp = (s.A * e) / Math.sqrt(1 + r / 14);
      if (amp < 0.004) continue;
      const ph = K * phi;
      const c = Math.cos(ph);
      const g = -amp * K * Math.sin(ph);
      h += amp * c;
      gx += (g * dx) / r;
      gz += (g * dz) / r;
    }
    out[0] = h;
    out[1] = gx;
    out[2] = gz;
  };
}

/**
 * A dot field seen in gentle perspective, like still water at dusk. On every beat a
 * pebble falls into it: the dots lift into damped rings that run outward and cross,
 * crests glowing in the primary color and troughs sinking into the secondary. After a
 * held breath the last, heaviest drop lands right under the headline, which rises on
 * its first crest and keeps floating on the swell while softer drops keep time.
 */
export const Component: React.FC<Props> = ({ headline, color, primary, secondary, background, fontFamily, seed, spacing, grain }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { width: W, height: H, unit, aspect } = useLayout();
  const family = brandFontStack(fontFamily);
  const transparent = background === "transparent";
  const dark = transparent ? luminance(color) > 0.45 : luminance(background) < 0.4;
  const text = headline.trim();
  const portrait = aspect === "9:16";
  const wide = aspect === "16:9";

  const [handle] = useState(() => delayRender("dot-field-drops: font"));
  const released = useRef(false);
  useLayoutEffect(() => {
    waitForBrandFonts()
      .then(() => document.fonts.load(`600 100px ${family}`, text || "Aa"))
      .then(() => document.fonts.ready)
      .then(() => {
        if (!released.current) {
          released.current = true;
          continueRender(handle);
        }
      })
      .catch(cancelRender);
  }, [family, handle, text]);

  // ---- Layout + the dot field (static per size) ---------------------------------
  const field = useMemo<Field>(() => {
    const cx = W / 2;
    const boxW = W * (portrait ? 0.84 : wide ? 0.72 : 0.8);
    const max = H * (portrait ? 0.068 : wide ? 0.13 : 0.11);
    const min = H * (portrait ? 0.031 : 0.02);
    const size = text ? fitFontSize({ chars: text.length, boxW, boxH: H * (portrait ? 0.26 : 0.3), lines: 2, charEm: 0.53, lineHeight: LH, max, min }) : 0;
    const lines = text ? (text.length * size * 0.53 > boxW * 0.98 ? 2 : 1) : 0;
    const blockH = lines * size * LH;
    const ty = H * (portrait ? 0.37 : wide ? 0.4 : 0.39);
    const impactY = Math.min(H * 0.8, (text ? ty + blockH / 2 : H * 0.42) + unit * (portrait ? 13 : 10));

    // Perspective plane: rows as far apart as columns at the bottom edge, horizon above the frame.
    const sN = unit * (portrait ? 2.8 : 2.6) * spacing;
    const q = portrait ? 2.05 : wide ? 1.85 : 1.95;
    const zNear = H / (sN * (1 - 1 / q));
    const a = sN * zNear * zNear;
    const F = sN * zNear;
    const yh = H - a / zNear;
    const zTop = zNear * q;
    const z0 = Math.floor(zNear * 0.95);
    const z1 = Math.ceil(zTop * 1.04);
    const wxs: number[] = [];
    const wzs: number[] = [];
    for (let zz = z0; zz <= z1; zz++) {
      const xm = Math.ceil(((W / 2 + sN * 2) * zz) / F);
      for (let xx = -xm; xx <= xm; xx++) {
        wxs.push(xx);
        wzs.push(zz);
      }
    }
    const n = wxs.length;
    const wx = Float32Array.from(wxs);
    const wz = Float32Array.from(wzs);
    const sx = new Float32Array(n);
    const sy = new Float32Array(n);
    const sp = new Float32Array(n);
    const mul = new Float32Array(n);
    const delay = new Float32Array(n);
    const hw = (boxW * 0.62) / 2;
    const hh = Math.max(blockH * 0.75, unit * 4);
    for (let i = 0; i < n; i++) {
      const zz = wz[i]!;
      sx[i] = cx + (F * wx[i]!) / zz;
      sy[i] = yh + a / zz;
      sp[i] = F / zz;
      const depth = clamp01((zz - zNear) / (zTop - zNear));
      const fog = 1 - 0.5 * depth * depth;
      const ex = (sx[i]! - cx) / hw;
      const ey = (sy[i]! - ty) / hh;
      const calm = text ? 1 - 0.6 * Math.exp(-(ex * ex + ey * ey) * 1.4) : 1;
      mul[i] = fog * calm;
      delay[i] = depth * 5 + (Math.abs(sx[i]! - cx) / W) * 3;
    }
    return { n, wx, wz, sx, sy, sp, mul, delay, cx, yh, a, F, zNear, zTop, ty, blockW: boxW, blockH, size, impactX: cx, impactY };
  }, [W, H, unit, portrait, wide, spacing, text]);

  // ---- Drops: seeded landing points, kept apart so their rings cross mid-frame ---
  const drops = useMemo<Drop[]>(() => {
    const { cx, yh, a, F, impactX, impactY } = field;
    const toWorld = (px: number, py: number) => {
      const zz = a / Math.max(1, py - yh);
      return { x: ((px - cx) * zz) / F, z: zz };
    };
    const r = rng(`dot-field-drops-${seed}`);
    const last = toWorld(impactX, impactY);
    const out: Drop[] = [];
    const pts: { x: number; z: number }[] = [last];
    const pick = (minD: number) => {
      let best = toWorld(W * 0.5, H * 0.5);
      let bestD = -1;
      for (let tries = 0; tries < 40; tries++) {
        const px = W * (0.1 + 0.8 * r());
        const py = H * (0.16 + 0.76 * r());
        const p = toWorld(px, py);
        let d = Infinity;
        for (const o of pts) d = Math.min(d, Math.hypot(o.x - p.x, o.z - p.z));
        if (d > minD) return p;
        if (d > bestD) {
          bestD = d;
          best = p;
        }
      }
      return best;
    };
    BEATS.forEach((t0, i) => {
      // Alternate sides of the frame so successive rings meet in the middle.
      let p = pick(16);
      if ((i % 2 === 0) === p.x > last.x) p = { x: last.x - (p.x - last.x), z: p.z };
      pts.push(p);
      out.push({ t0, x: p.x, z: p.z, amp: BEAT_AMP[i]!, big: false, seed: i });
    });
    out.push({ t0: LAST, x: last.x, z: last.z, amp: LAST_AMP, big: true, seed: 99 });
    for (let t0 = AMBIENT, i = 0; t0 < 1800; t0 += AMBIENT_EVERY, i++) {
      const p = pick(12);
      pts.push(p);
      if (pts.length > 4) pts.splice(1, 1);
      out.push({ t0, x: p.x, z: p.z, amp: AMBIENT_AMP, big: false, seed: 200 + i });
    }
    return out;
  }, [field, seed, W, H]);

  // ---- Palette (per brand, not per frame) --------------------------------------
  const palette = useMemo(() => {
    const ink = color;
    const base = dark ? 0.34 : 0.3;
    const dots: string[] = [];
    const glow: (string | null)[] = [];
    for (let ci = 0; ci < NC; ci++) {
      const t = -1 + (2 * ci) / (NC - 1);
      let col: string;
      let al: number;
      if (t < 0) {
        col = dark ? mix(mix(ink, secondary, Math.min(1, -t * 2.2)), ink, Math.max(0, -t - 0.6) * 0.5) : mix(ink, secondary, Math.min(1, -t * 2.2));
        al = base + 0.66 * Math.min(1, -t * 1.8);
      } else if (t < 0.72) {
        col = mix(ink, primary, Math.min(1, t / 0.45));
        al = base + 0.7 * Math.min(1, t * 2);
      } else {
        col = dark ? mix(primary, ink, ((t - 0.72) / 0.28) * 0.55) : mix(primary, ink, ((t - 0.72) / 0.28) * 0.12);
        al = 1;
      }
      for (let ai = 0; ai < NA; ai++) dots.push(withAlpha(col, Math.min(1, al) * ALPHAS[ai]!));
      const g = Math.abs(t) - 0.2;
      glow.push(g > 0 ? withAlpha(t > 0 ? primary : secondary, Math.min(1, g * (dark ? 0.72 : 0.75) * (t > 0 ? 1 : 1.1))) : null);
    }
    return { dots, glow };
  }, [color, primary, secondary, dark]);

  const ref = useRef<HTMLCanvasElement>(null);
  const glowRef = useRef<HTMLCanvasElement | null>(null);
  const blurRef = useRef<HTMLCanvasElement | null>(null);
  const vigRef = useRef<HTMLCanvasElement | null>(null);
  const vigKey = useRef("");
  const bufRef = useRef<{ x: Float32Array; y: Float32Array; r: Float32Array; b: Int16Array; t: Float32Array; order: Int32Array } | null>(null);

  // Active ring sources this frame (shared by the canvas and the floating headline).
  const active = useMemo(() => {
    const list: { x: number; z: number; R: number; A: number }[] = [];
    for (const d of drops) {
      const age = frame - d.t0;
      if (age < 0 || age > 190) continue;
      const A = d.amp * Math.exp(-age / DAMP) * clamp01(age / 2 + 0.35);
      if (A < 0.02) continue;
      list.push({ x: d.x, z: d.z, R: age * SPEED, A });
    }
    return list;
  }, [drops, frame]);
  const wave = useMemo(() => makeWave(active, frame), [active, frame]);

  useLayoutEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const f = frame;
    const { n, wx, wz, sx, sy, sp, mul, delay, cx, yh, a, F } = field;
    if (!bufRef.current || bufRef.current.x.length !== n) {
      bufRef.current = { x: new Float32Array(n), y: new Float32Array(n), r: new Float32Array(n), b: new Int16Array(n), t: new Float32Array(n), order: new Int32Array(n) };
    }
    const B = bufRef.current;
    const tmp = new Float32Array(3);
    const lift = 0.85;
    const counts = new Int32Array(NC * NA + 1);

    // ---- Per dot: height, slope light, level, size --------------------------------
    for (let i = 0; i < n; i++) {
      const appear = 0.55 + 0.45 * easeOut((f - delay[i]!) / 10);
      if (appear <= 0.01) {
        B.b[i] = NC * NA;
        counts[NC * NA]!++;
        continue;
      }
      wave(wx[i]!, wz[i]!, tmp);
      const h = tmp[0]!;
      const light = (tmp[1]! * 0.42 - tmp[2]! * 0.9) * 0.7;
      const t = Math.max(-1, Math.min(1, h * 1.25 + light * 0.55));
      const s = sp[i]!;
      B.x[i] = sx[i]!;
      B.y[i] = sy[i]! - h * lift * s - (1 - appear) * s * 1.5;
      B.r[i] = Math.max(0.6, s * 0.16 * (1 + 1.1 * Math.max(0, t) + 0.25 * Math.max(0, -t)) * (0.4 + 0.6 * appear));
      B.t[i] = t;
      const ci = Math.round(((t + 1) / 2) * (NC - 1));
      const am = mul[i]! * appear * (1 + 0.5 * Math.max(0, t));
      let ai = 0;
      for (let k = 0; k < NA; k++) if (am >= ALPHAS[k]! * 0.92) ai = k;
      const bi = ci * NA + ai;
      B.b[i] = bi;
      counts[bi]!++;
    }
    const starts = new Int32Array(NC * NA + 2);
    for (let k = 0; k <= NC * NA; k++) starts[k + 1] = starts[k]! + counts[k]!;
    const fill = starts.slice();
    for (let i = 0; i < n; i++) B.order[fill[B.b[i]!]!++] = i;

    // ---- Light layer: aura pools + glowing crests (quarter res, blurred) ----------
    const gw = Math.max(2, Math.round(W / 4));
    const gh = Math.max(2, Math.round(H / 4));
    const gl = ctx2d(sized(glowRef, gw, gh));
    reset(gl);
    gl.clearRect(0, 0, gw, gh);
    const auraIn = easeInOut(f / 40);
    const drift = Math.sin((f / 300) * TAU);
    const pool = (px: number, py: number, rad: number, squash: number, col: string, al: number) => {
      if (al <= 0.002 || rad <= 0) return;
      gl.save();
      gl.translate(px / 4, py / 4);
      gl.scale(1, squash);
      const g = gl.createRadialGradient(0, 0, 0, 0, 0, rad / 4);
      g.addColorStop(0, withAlpha(col, al));
      g.addColorStop(0.5, withAlpha(col, al * 0.4));
      g.addColorStop(1, withAlpha(col, 0));
      gl.fillStyle = g;
      gl.fillRect(-rad / 4, -rad / 4, rad / 2, rad / 2);
      gl.restore();
    };
    const big = Math.max(W, H);
    pool(W * (0.16 + 0.04 * drift), H * 0.12, big * 0.62, 0.7, secondary, (dark ? 0.2 : 0.14) * auraIn);
    pool(W * (0.86 - 0.04 * drift), H * 0.95, big * 0.58, 0.7, primary, (dark ? 0.18 : 0.12) * auraIn);
    for (const d of drops) {
      const age = f - d.t0;
      if (age < 0 || age > 150) continue;
      const pz = d.z;
      const px = cx + (F * d.x) / pz;
      const py = yh + a / pz;
      const s = F / pz;
      const squash = a / (F * pz);
      const k = d.amp * Math.exp(-age / 45) * easeOut(age / 6);
      pool(px, py, s * (8 + age * SPEED * 1.15), squash, primary, (dark ? 0.22 : 0.2) * k);
    }
    // Crests (and deep troughs) as soft light.
    for (let ci = 0; ci < NC; ci++) {
      const col = palette.glow[ci];
      if (!col) continue;
      gl.fillStyle = col;
      gl.beginPath();
      for (let ai = 0; ai < NA; ai++) {
        const bi = ci * NA + ai;
        for (let j = starts[bi]!; j < starts[bi + 1]!; j++) {
          const i = B.order[j]!;
          const rr = (B.r[i]! * 2.6) / 4;
          const x = B.x[i]! / 4;
          const y = B.y[i]! / 4;
          gl.moveTo(x + rr, y);
          gl.arc(x, y, rr, 0, TAU);
        }
      }
      gl.fill();
    }
    const bl = ctx2d(sized(blurRef, gw, gh));
    reset(bl);
    bl.clearRect(0, 0, gw, gh);
    bl.filter = `blur(${Math.max(1, Math.round(unit * 0.45))}px)`;
    bl.drawImage(sized(glowRef, gw, gh), 0, 0);
    bl.filter = "none";

    // ---- Composite -----------------------------------------------------------------
    const ctx = ctx2d(canvas);
    reset(ctx);
    ctx.clearRect(0, 0, W, H);
    if (!transparent) {
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, W, H);
    }
    ctx.imageSmoothingEnabled = true;
    // Additive light only over an opaque backdrop; a transparent layer keeps plain alpha.
    ctx.globalCompositeOperation = dark && !transparent ? "lighter" : "source-over";
    ctx.globalAlpha = transparent ? 0.7 : 1;
    ctx.drawImage(sized(blurRef, gw, gh), 0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";

    // Dots, dimmest buckets first so bright crests sit on top.
    for (let ci = 0; ci < NC; ci++) {
      for (let ai = 0; ai < NA; ai++) {
        const bi = ci * NA + ai;
        const s0 = starts[bi]!;
        const s1 = starts[bi + 1]!;
        if (s1 <= s0) continue;
        ctx.fillStyle = palette.dots[bi]!;
        ctx.beginPath();
        for (let j = s0; j < s1; j++) {
          const i = B.order[j]!;
          const x = B.x[i]!;
          const y = B.y[i]!;
          const rr = B.r[i]!;
          ctx.moveTo(x + rr, y);
          ctx.arc(x, y, rr, 0, TAU);
        }
        ctx.fill();
      }
    }

    // Pebbles: fall, flash, splash.
    for (const d of drops) {
      const age = f - d.t0;
      if (age < -FALL || age > 26) continue;
      const pz = d.z;
      const s = F / pz;
      const px = cx + (F * d.x) / pz;
      const py = yh + a / pz;
      const squash = a / (F * pz);
      const size = s * (d.big ? 0.42 : 0.3);
      if (age < 0) {
        const p = (age + FALL) / FALL;
        const hgt = (d.big ? 22 : 15) * (1 - p * p) * s;
        const y = py - hgt;
        const vel = 2 * p * (d.big ? 22 : 15) * s / FALL;
        const tail = Math.min(vel * 2.2, s * 9);
        const g = ctx.createLinearGradient(px, y - tail, px, y);
        g.addColorStop(0, withAlpha(primary, 0));
        g.addColorStop(1, withAlpha(primary, 0.55 * easeOut(p * 3)));
        ctx.strokeStyle = g;
        ctx.lineWidth = size * 1.1;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(px, y - tail);
        ctx.lineTo(px, y);
        ctx.stroke();
        ctx.fillStyle = primary;
        ctx.beginPath();
        ctx.arc(px, y, size, 0, TAU);
        ctx.fill();
        if (dark) {
          ctx.fillStyle = withAlpha(color, 0.85);
          ctx.beginPath();
          ctx.arc(px, y, size * 0.45, 0, TAU);
          ctx.fill();
        }
        continue;
      }
      // Impact flash: a flattened ring of light on the surface.
      const fl = Math.pow(1 - clamp01(age / 18), 2);
      if (fl > 0) {
        ctx.save();
        ctx.translate(px, py);
        ctx.scale(1, squash);
        const rad = s * (2.5 + age * 1.2) * (d.big ? 1.4 : 1);
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rad);
        g.addColorStop(0, withAlpha(dark ? mix(primary, color, 0.5) : primary, (dark ? 0.75 : 0.45) * fl));
        g.addColorStop(0.35, withAlpha(primary, (dark ? 0.35 : 0.22) * fl));
        g.addColorStop(1, withAlpha(primary, 0));
        ctx.fillStyle = g;
        ctx.fillRect(-rad, -rad, rad * 2, rad * 2);
        ctx.restore();
        // Crisp shock ring at the leading crest.
        const R = s * (1 + age * SPEED);
        ctx.strokeStyle = withAlpha(primary, (dark ? 0.6 : 0.5) * fl);
        ctx.lineWidth = Math.max(1, s * 0.1);
        ctx.beginPath();
        ctx.ellipse(px, py, R, R * squash, 0, 0, TAU);
        ctx.stroke();
      }
      // Splash droplets on ballistic arcs.
      const r = rng(`dfd-splash-${seed}-${d.seed}`);
      const count = d.big ? 14 : 8;
      for (let k = 0; k < count; k++) {
        const th = (k / count) * TAU + r() * 0.6;
        const vr = (0.25 + r() * 0.35) * (d.big ? 1.3 : 1);
        const vy = (0.9 + r() * 0.9) * (d.big ? 1.35 : 1);
        const gr = 0.13;
        const tl = (2 * vy) / gr;
        if (age > tl) continue;
        const hx = d.x + Math.cos(th) * vr * age;
        const hz = d.z + Math.sin(th) * vr * age;
        const hy = vy * age - (gr * age * age) / 2;
        const ss = F / hz;
        const x = cx + (F * hx) / hz;
        const y = yh + a / hz - hy * ss * lift;
        const fade = 1 - Math.pow(age / tl, 3);
        ctx.fillStyle = withAlpha(dark && k % 3 === 0 ? mix(primary, color, 0.6) : primary, 0.95 * fade);
        ctx.beginPath();
        ctx.arc(x, y, ss * (0.12 + r() * 0.1) * (d.big ? 1.25 : 1), 0, TAU);
        ctx.fill();
      }
    }

    if (!transparent) {
      // Vignette lets the far field melt into the brand background.
      const vc = sized(vigRef, W, H);
      if (vigKey.current !== `${W}x${H}-${background}`) {
        vigKey.current = `${W}x${H}-${background}`;
        const vg = ctx2d(vc);
        reset(vg);
        vg.clearRect(0, 0, W, H);
        const v = vg.createRadialGradient(cx, H * 0.55, Math.min(W, H) * 0.32, cx, H * 0.55, Math.hypot(W, H) * 0.56);
        v.addColorStop(0, withAlpha(background, 0));
        v.addColorStop(1, withAlpha(background, 0.62));
        vg.fillStyle = v;
        vg.fillRect(0, 0, W, H);
        const top = vg.createLinearGradient(0, 0, 0, H * 0.22);
        top.addColorStop(0, withAlpha(background, 0.55));
        top.addColorStop(1, withAlpha(background, 0));
        vg.fillStyle = top;
        vg.fillRect(0, 0, W, H * 0.22);
      }
      ctx.drawImage(vc, 0, 0);
    } else {
      // Layer mode: fade to nothing well before the corners.
      ctx.save();
      ctx.globalCompositeOperation = "destination-in";
      ctx.translate(cx, H / 2);
      ctx.scale(W / 2, H / 2);
      const m = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      m.addColorStop(0, withAlpha(primary, 1));
      m.addColorStop(0.55, withAlpha(primary, 1));
      m.addColorStop(0.97, withAlpha(primary, 0));
      m.addColorStop(1, withAlpha(primary, 0));
      ctx.fillStyle = m;
      ctx.fillRect(-1.2, -1.2, 2.4, 2.4);
      ctx.restore();
    }
  }, [field, drops, palette, wave, frame, W, H, unit, color, primary, secondary, background, dark, transparent, seed]);

  // ---- Headline: rises on the last drop's crest, then floats on the swell ---------
  const words = text ? text.split(/\s+/) : [];
  const probe = new Float32Array(3);
  const wordStyle = (i: number): React.CSSProperties => {
    const t0 = HEAD + i * 3;
    const s = springSnap(frame, fps, t0, HEAD_SPRING);
    const op = band(frame, t0, t0 + 9);
    const blur = (1 - clamp01((frame - t0) / 10)) * unit * 0.8;
    // Bob with the water under the word (rounded: held frames stay pixel-identical).
    const u = words.length > 1 ? i / (words.length - 1) - 0.5 : 0;
    const px = field.cx + u * Math.min(field.blockW, text.length * field.size * 0.53) * 0.8;
    const zz = field.a / Math.max(1, field.ty + field.blockH * 0.6 - field.yh);
    wave(((px - field.cx) * zz) / field.F, zz, probe);
    const bob = Math.round(-probe[0]! * unit * 0.55 * clamp01((frame - HEAD) / 20));
    const y = Math.round((1 - s) * unit * 6) + bob;
    return {
      display: "inline-block",
      opacity: op,
      transform: `translateY(${y}px)`,
      filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : undefined,
    };
  };
  const halo = transparent ? undefined : `0 0 ${Math.round(unit * 2.6)}px ${withAlpha(background, 0.9)}`;

  return (
    <AbsoluteFill style={{ background: transparent ? undefined : background }}>
      <canvas ref={ref} width={W} height={H} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }} />
      {text ? (
        <div
          style={{
            position: "absolute",
            left: (W - field.blockW) / 2,
            width: field.blockW,
            top: field.ty - field.blockH / 2,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div
            data-21st-slot="headline"
            style={{
              fontFamily: family,
              fontWeight: 600,
              fontSize: field.size,
              lineHeight: LH,
              letterSpacing: "-0.035em",
              textAlign: "center",
              color,
              textShadow: halo,
              maxWidth: "100%",
              overflowWrap: "anywhere",
              textWrap: "balance",
            }}
          >
            {words.map((w, i) => (
              <React.Fragment key={i}>
                <span style={wordStyle(i)}>{w}</span>
                {i < words.length - 1 ? " " : null}
              </React.Fragment>
            ))}
          </div>
        </div>
      ) : null}
      {grain && !transparent ? <AbsoluteFill style={{ backgroundImage: GRAIN, opacity: dark ? 0.07 : 0.06, mixBlendMode: "overlay", pointerEvents: "none" }} /> : null}
    </AbsoluteFill>
  );
};
