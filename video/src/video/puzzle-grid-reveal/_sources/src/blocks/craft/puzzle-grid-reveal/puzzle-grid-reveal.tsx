// Built with Remotion - https://remotion.pro/license
import React, { useMemo } from "react";
import { AbsoluteFill, Img, spring, useVideoConfig } from "remotion";
import type { z } from "zod";
import { brandFontStack, easeInOut, easeOut, fitFontSize, luminance, ramp, springSnap, useEnterExit, useLayout, withAlpha } from "../../../kit/index";
import { rng } from "../_lib/noise";
import { SAMPLE_SCREENSHOT } from "../_lib/samples";
import type { schema } from "./puzzle-grid-reveal.schema";
import { meta } from "./puzzle-grid-reveal.meta";

const SETTLE = meta.timing.markers.settled ?? 146;
/** First tile leaves the sky, then one every STEP frames; the center tile waits a beat longer. */
const DROP0 = 12;
const STEP = 6;
const LAST_PAUSE = 12;
/** Gutters breathe out (anticipation), then weld shut. */
const WIDEN = [80, 92] as const;
const CLOSE = [92, meta.timing.markers.weld ?? 110] as const;
const WELD = CLOSE[1];
const DROP = { damping: 12, stiffness: 150, mass: 0.85 } as const;
const SOFT = { damping: 20, stiffness: 110, mass: 1 } as const;

const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' seed='4' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.6'/></svg>\")";

const px = (n: number) => `${n}px`;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp01 = (t: number) => Math.max(0, Math.min(1, t));
/** Quintic in-out: the gutters hesitate, then snap shut. */
const quintInOut = (x: number) => {
  const t = clamp01(x);
  return t < 0.5 ? 16 * t ** 5 : 1 - Math.pow(-2 * t + 2, 5) / 2;
};

/** The picture every tile is a window into: the user's image, or the shared sample page. */
const Picture: React.FC<{ w: number; h: number; src: string; focus: "center" | "top" }> = ({ w, h, src, focus }) => (
  <Img src={src} style={{ position: "absolute", inset: 0, width: px(w), height: px(h), objectFit: "cover", objectPosition: focus === "top" ? "50% 0%" : "50% 50%", display: "block" }} />
);

export const Component: React.FC<z.infer<typeof schema>> = ({ image, focus, logo, caption, color, accent, secondary, background, fontFamily, seed }) => {
  const { fps } = useVideoConfig();
  const { width: W, height: H, unit: u, aspect, portrait } = useLayout();
  const { frame: f } = useEnterExit(meta.timing);
  const transparent = background === "transparent";
  const dark = transparent ? luminance(color) > 0.45 : luminance(background) < 0.4;
  const font = brandFontStack(fontFamily);
  // Empty slot: the shared sample page, so the poster reads as a screenshot reveal.
  const src = image || SAMPLE_SCREENSHOT;

  // ---- Layout: a 4:3 picture (screenshots survive the crop) in every aspect, caption under it.
  const floor = portrait ? H * 0.031 : H * 0.019;
  const capText = caption.trim();
  const hasCap = capText.length > 0 || Boolean(logo);
  const gwRaw = aspect === "16:9" ? Math.min(W * 0.56, H * 0.7 * (4 / 3)) : aspect === "1:1" ? W * 0.76 : W * 0.9;
  // The sample page keeps its own 16:10 so nothing is cropped; user images use 4:3.
  const ratio = image ? 3 / 4 : 10 / 16;
  const gw = Math.round(gwRaw / 3) * 3;
  const gh = Math.round((gw * ratio) / 3) * 3;
  const cw = gw / 3;
  const ch = gh / 3;
  const capFs = Math.max(
    floor,
    fitFontSize({ chars: Array.from(capText).length + (logo ? 3 : 0), boxW: gw * (portrait ? 1 : 0.92), boxH: portrait ? H * 0.12 : H * 0.07, lines: portrait ? 2 : 1, charEm: 0.55, lineHeight: 1.2, max: u * (aspect === "16:9" ? 4.6 : aspect === "1:1" ? 5.2 : 7.4) }),
  );
  const capGap = u * (portrait ? 6 : 4.4);
  const capH = hasCap ? capGap + capFs * 1.2 * (portrait && Array.from(capText).length * 0.55 * capFs > gw ? 2 : 1) : 0;
  const gx = Math.round((W - gw) / 2);
  const gy = Math.round((H - gh - capH) / 2 - (portrait ? H * 0.015 : 0));
  const gap0 = Math.round(Math.min(cw, ch) * 0.075);
  const r0 = Math.min(cw, ch) * 0.075;
  const rFinal = u * (portrait ? 2.6 : 2);

  // ---- Seeded landing order: eight shuffled tiles, the center tile lands last and completes the pattern.
  const order = useMemo(() => {
    const r = rng(`puzzle-grid-${seed}`);
    const rest = [0, 1, 2, 3, 5, 6, 7, 8];
    for (let i = rest.length - 1; i > 0; i--) {
      const j = Math.floor(r() * (i + 1));
      [rest[i], rest[j]] = [rest[j]!, rest[i]!];
    }
    const seq = [...rest, 4];
    const start: number[] = new Array(9).fill(0);
    const tilt: number[] = new Array(9).fill(0);
    seq.forEach((cell, k) => {
      start[cell] = DROP0 + k * STEP + (k === 8 ? LAST_PAUSE : 0);
      tilt[cell] = (r() * 2 - 1) * 7;
    });
    return { start, tilt };
  }, [seed]);

  // ---- Gutters: breathe out, then weld.
  const widen = easeInOut(ramp(f, [WIDEN[0], WIDEN[1]], [0, 1]));
  const close = quintInOut(ramp(f, [CLOSE[0], CLOSE[1]], [0, 1]));
  const gap = gap0 * (1 + 0.22 * widen) * (1 - close);
  const merged = f >= WELD;

  // ---- Camera: a tilted, slightly distant table that flattens as the picture completes.
  const cam = easeInOut(ramp(f, [0, WELD], [0, 1]));
  const thunk = f >= WELD ? Math.sin(Math.min(1, (f - WELD) / 12) * Math.PI) * (1 - (f - WELD) / 12) : 0;
  const breathe = f >= WELD ? 0.035 * easeOut((f - WELD) / 150) : 0;
  const camScale = lerp(0.9, 1, cam) * (1 + 0.016 * Math.max(0, thunk));
  const camTiltX = lerp(14, 0, cam);
  const camRotZ = lerp(-2.5, 0, cam);
  const camT = f >= WELD + 12 ? "none" : `perspective(${px(Math.max(W, H) * 1.6)}) rotateX(${camTiltX.toFixed(3)}deg) rotateZ(${camRotZ.toFixed(3)}deg) scale(${camScale.toFixed(4)})`;

  // ---- Light.
  const weldFlash = f >= WELD - 8 ? (f < WELD ? easeOut((f - (WELD - 8)) / 8) : Math.max(0, 1 - (f - WELD) / 16)) : 0;
  const glowA = (dark ? 0.26 : 0.16) * (0.55 + 0.45 * easeOut(ramp(f, [0, WELD], [0, 1]))) + (dark ? 0.18 : 0.1) * weldFlash;
  // Literal black/white only as alpha highlights and shadows, built here, never inside style props.
  const INK = "#000000";
  const LIGHT = "#ffffff";
  const shadowInk = withAlpha(INK, dark ? 0.55 : 0.14);
  const vignette = withAlpha(dark ? INK : color, dark ? 0.35 : 0.05);
  const glossHi = withAlpha(LIGHT, 0.28);
  const hair = withAlpha(color, dark ? 0.1 : 0.12);
  const tileRing = withAlpha(dark ? LIGHT : color, dark ? 0.1 : 0.08);
  const seamCore = `color-mix(in oklch, ${accent} 55%, ${LIGHT})`;

  // ---- Caption.
  const capIn = springSnap(f, fps, WELD + 6, SOFT);
  const gloss = ramp(f, [WELD + 2, WELD + 34], [0, 1]);

  const picture = (scale: number) => (
    <div style={{ position: "absolute", left: 0, top: 0, width: px(gw), height: px(gh), transform: scale !== 1 ? `scale(${scale.toFixed(5)})` : undefined, transformOrigin: "50% 50%" }}>
      <Picture w={gw} h={gh} src={src} focus={focus} />
    </div>
  );

  return (
    <AbsoluteFill style={{ background: transparent ? "transparent" : background, overflow: "hidden" }}>
      {/* Brand glow pooled under the grid; fades to nothing well before the frame corners. */}
      <div
        style={{
          position: "absolute",
          left: px(gx + gw / 2 - gw * 0.95),
          top: px(gy + gh / 2 - gh * 0.95),
          width: px(gw * 1.9),
          height: px(gh * 1.9),
          background: `radial-gradient(closest-side, ${withAlpha(accent, glowA)} 0%, ${withAlpha(secondary, glowA * 0.6)} 42%, ${withAlpha(secondary, 0)} 100%)`,
          filter: `blur(${px(u * 2)})`,
        }}
      />
      {!transparent ? (
        <>
          <AbsoluteFill style={{ background: `radial-gradient(ellipse 75% 75% at 50% 46%, transparent 55%, ${vignette} 100%)` }} />
          <AbsoluteFill style={{ backgroundImage: GRAIN, opacity: dark ? 0.05 : 0.04, mixBlendMode: "overlay" }} />
        </>
      ) : null}

      <div style={{ position: "absolute", left: px(gx), top: px(gy), width: px(gw), height: px(gh), transform: camT, transformOrigin: "50% 60%" }}>
        {/* Empty slots, the grid waiting for its tiles. */}
        {!merged
          ? Array.from({ length: 9 }, (_, i) => {
              const c = i % 3;
              const r = Math.floor(i / 3);
              const appear = easeOut(ramp(f, [(c + r) * 2, (c + r) * 2 + 12], [0, 1]));
              const covered = ramp(f, [order.start[i]! + 4, order.start[i]! + 10], [1, 0]);
              const x = c * cw + (c - 1) * gap;
              const y = r * ch + (r - 1) * gap;
              return (
                <div
                  key={`slot-${i}`}
                  style={{
                    position: "absolute",
                    left: px(x),
                    top: px(y),
                    width: px(cw),
                    height: px(ch),
                    borderRadius: px(r0),
                    background: withAlpha(color, dark ? 0.035 : 0.04),
                    boxShadow: `inset 0 0 0 1px ${hair}`,
                    opacity: appear * (0.4 + 0.6 * covered),
                    transform: `scale(${(0.92 + 0.08 * appear).toFixed(4)})`,
                  }}
                />
              );
            })
          : null}

        {/* Light leaking through the cracks: as the gutters narrow, the seams glow before they shut. */}
        {!merged && close > 0.02 ? (
          <div
            style={{
              position: "absolute",
              left: px(-gap),
              top: px(-gap),
              width: px(gw + gap * 2),
              height: px(gh + gap * 2),
              borderRadius: px(r0),
              background: `radial-gradient(ellipse 60% 60% at 50% 50%, ${seamCore}, ${withAlpha(accent, 0.85)} 55%, ${withAlpha(secondary, 0.6)} 100%)`,
              opacity: ramp(close, [0.02, 0.45], [0, 1]),
            }}
          />
        ) : null}

        {/* Landing pings: a ring of accent light where each tile touches down. */}
        {!merged
          ? Array.from({ length: 9 }, (_, i) => {
              const t = (f - (order.start[i]! + 7)) / 16;
              if (t < 0 || t > 1) return null;
              const c = i % 3;
              const r = Math.floor(i / 3);
              const x = c * cw + (c - 1) * gap;
              const y = r * ch + (r - 1) * gap;
              const e = easeOut(t);
              return (
                <div
                  key={`ping-${i}`}
                  style={{
                    position: "absolute",
                    left: px(x),
                    top: px(y),
                    width: px(cw),
                    height: px(ch),
                    borderRadius: px(r0 * 1.4),
                    boxShadow: `0 0 0 ${px(Math.max(1.5, u * 0.25))} ${withAlpha(accent, 0.75 * (1 - t))}, 0 0 ${px(u * 3)} ${withAlpha(accent, 0.5 * (1 - t))}`,
                    transform: `scale(${(1 + 0.1 * e).toFixed(4)})`,
                  }}
                />
              );
            })
          : null}

        {/* The nine tiles. Each is a window onto its ninth of the picture. */}
        {!merged
          ? Array.from({ length: 9 }, (_, i) => {
              const c = i % 3;
              const r = Math.floor(i / 3);
              const st = order.start[i]!;
              if (f < st) return null;
              const s = spring({ frame: f - st, fps, config: DROP });
              const sn = Math.abs(1 - s) < 1e-3 ? 1 : s;
              const lift = 1 - sn; // 1 high in the air, 0 on the table, negative = squash
              const x = c * cw + (c - 1) * gap;
              const y = r * ch + (r - 1) * gap;
              const dx = (c - 1) * cw * 0.35 * lift;
              const dy = ((r - 1) * ch * 0.35 - ch * 0.25) * lift;
              const sc = 1 + 0.75 * lift;
              const op = clamp01((f - st) / 4);
              const air = Math.max(0, lift);
              const contact = ramp(f - st, [6, 9], [0, 1]) * ramp(f - st, [9, 20], [1, 0]);
              const outer = (cond: boolean) => px(cond ? lerp(r0, rFinal, close) : r0 * (1 - close));
              const tl = outer(r === 0 && c === 0);
              const tr = outer(r === 0 && c === 2);
              const br = outer(r === 2 && c === 2);
              const bl = outer(r === 2 && c === 0);
              return (
                <div
                  key={`tile-${i}`}
                  style={{
                    position: "absolute",
                    left: px(x),
                    top: px(y),
                    width: px(cw),
                    height: px(ch),
                    borderRadius: `${tl} ${tr} ${br} ${bl}`,
                    overflow: "hidden",
                    opacity: op,
                    transform: `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px) scale(${sc.toFixed(4)}) rotate(${(order.tilt[i]! * lift).toFixed(3)}deg)`,
                    boxShadow: `0 ${px(u * (0.6 + 7 * air))} ${px(u * (1.6 + 12 * air))} ${withAlpha(INK, (dark ? 0.5 : 0.14) * (1 - 0.6 * air) * (1 - close))}, inset 0 0 0 1px ${withAlpha(dark ? LIGHT : color, (dark ? 0.1 : 0.08) * (1 - close))}`,
                    zIndex: 10 + Math.round(air * 10),
                  }}
                >
                  <div style={{ position: "absolute", left: px(-c * cw), top: px(-r * ch), width: px(gw), height: px(gh) }}>{picture(1)}</div>
                  {/* Contact flash: the tile catches the light as it lands. */}
                  {contact > 0 ? <div style={{ position: "absolute", inset: 0, background: `linear-gradient(160deg, ${withAlpha(LIGHT, 0.32 * contact)}, ${withAlpha(accent, 0.18 * contact)})`, mixBlendMode: "screen" }} /> : null}
                </div>
              );
            })
          : null}

        {/* One picture: tiles swap for a single layer once the seams are shut (identical pixels, no hairlines). */}
        {merged ? (
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: px(rFinal),
              overflow: "hidden",
              boxShadow: `0 ${px(u * 2.4)} ${px(u * 7)} ${shadowInk}, 0 0 ${px(u * (4 + 6 * weldFlash))} ${withAlpha(accent, (dark ? 0.22 : 0.14) + 0.35 * weldFlash)}, inset 0 0 0 1px ${tileRing}`,
            }}
          >
            {picture(1 + breathe)}
            {/* Gloss sweep across the finished picture. */}
            {gloss > 0 && gloss < 1 ? (
              <div
                style={{
                  position: "absolute",
                  top: px(-gh * 0.2),
                  left: px(lerp(-gw * 0.6, gw * 1.2, easeInOut(gloss))),
                  width: px(gw * 0.4),
                  height: px(gh * 1.4),
                  transform: "rotate(18deg)",
                  background: `linear-gradient(90deg, transparent, ${glossHi} 50%, transparent)`,
                  mixBlendMode: "soft-light",
                }}
              />
            ) : null}
            <div style={{ position: "absolute", inset: 0, borderRadius: px(rFinal), boxShadow: `inset 0 0 0 1px ${tileRing}`, pointerEvents: "none" }} />
          </div>
        ) : null}

        {/* Weld light: the seams flare outward from the center as they close. */}
        {weldFlash > 0
          ? [
              { v: true, at: cw },
              { v: true, at: cw * 2 },
              { v: false, at: ch },
              { v: false, at: ch * 2 },
            ].map((s, k) => {
              const grow = easeOut(ramp(f, [WELD - 8, WELD + 4], [0, 1]));
              const thick = Math.max(2, u * 0.22);
              const len = (s.v ? gh : gw) * grow;
              return (
                <div
                  key={`seam-${k}`}
                  style={{
                    position: "absolute",
                    left: px(s.v ? s.at - thick / 2 : gw / 2 - len / 2),
                    top: px(s.v ? gh / 2 - len / 2 : s.at - thick / 2),
                    width: px(s.v ? thick : len),
                    height: px(s.v ? len : thick),
                    borderRadius: px(thick),
                    background: `linear-gradient(${s.v ? "180deg" : "90deg"}, transparent, ${seamCore} 30%, ${seamCore} 70%, transparent)`,
                    boxShadow: `0 0 ${px(u * 1.6)} ${withAlpha(accent, 0.9)}`,
                    opacity: weldFlash,
                    zIndex: 40,
                  }}
                />
              );
            })
          : null}
      </div>

      {/* Caption under the finished picture. */}
      {hasCap ? (
        <div
          style={{
            position: "absolute",
            left: px(gx - (portrait ? 0 : gw * 0.04)),
            width: px(gw * (portrait ? 1 : 1.08)),
            top: px(gy + gh + capGap),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: px(capFs * 0.5),
            opacity: clamp01(capIn * 1.4),
            transform: `translateY(${((1 - capIn) * u * 3).toFixed(2)}px)`,
            filter: capIn < 0.999 ? `blur(${((1 - capIn) * u * 0.8).toFixed(2)}px)` : undefined,
          }}
        >
          {logo ? <Img data-21st-slot="logo" src={logo} style={{ height: px(capFs * 1.1), maxWidth: px(gw * 0.3), objectFit: "contain", display: "block", flex: "none" }} /> : null}
          {capText ? (
            <div
              data-21st-slot="caption"
              style={{
                fontFamily: font,
                fontWeight: 600,
                fontSize: px(capFs),
                lineHeight: 1.2,
                letterSpacing: "-0.02em",
                color,
                textAlign: "center",
                minWidth: 0,
                overflowWrap: "break-word",
                textWrap: "balance",
              }}
            >
              {capText}
            </div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
