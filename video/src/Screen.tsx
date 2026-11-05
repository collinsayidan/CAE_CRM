import React, { createContext, useContext } from "react";
import { Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, FONT } from "./theme";

export type Box = { x: number; y: number; width: number; height: number };
// A camera keyframe: at this frame, frame this part of the screen (CSS pixels of the captured viewport).
export type Shot = { at: number; focus?: Box; zoom?: number };

const ease = Easing.bezier(0.65, 0, 0.35, 1);

type Mapper = { scale: number; map: (x: number, y: number) => [number, number] };
const ScreenSpace = createContext<Mapper>({ scale: 1, map: (x, y) => [x, y] });
export const useScreenSpace = () => useContext(ScreenSpace);

// Works out where the camera is between keyframes: a zoom and the point it centres on.
const camera = (frame: number, shots: Shot[], vw: number, vh: number) => {
  const pts = shots.map(s => {
    const f = s.focus ?? { x: 0, y: 0, width: vw, height: vh };
    return { at: s.at, cx: f.x + f.width / 2, cy: f.y + f.height / 2, zoom: s.zoom ?? 1 };
  });
  if (pts.length === 1) return pts[0];
  const at = pts.map(p => p.at);
  const opts = { easing: ease, extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
  return {
    cx: interpolate(frame, at, pts.map(p => p.cx), opts),
    cy: interpolate(frame, at, pts.map(p => p.cy), opts),
    zoom: interpolate(frame, at, pts.map(p => p.zoom), opts),
  };
};

// A captured screen in a rounded window, with a moving camera. Children are drawn in the screen's own pixel space
// (through useScreenSpace), so cursors and callouts stay locked to what they point at while the camera moves.
export const Screen: React.FC<{
  src: string; shots: Shot[]; viewport: { width: number; height: number };
  x: number; y: number; width: number; radius?: number; children?: React.ReactNode; sample?: boolean;
}> = ({ src, shots, viewport, x, y, width, radius = 26, children, sample = true }) => {
  const frame = useCurrentFrame();
  const base = width / viewport.width;
  const height = viewport.height * base;
  const cam = camera(frame, shots, viewport.width, viewport.height);
  const s = base * cam.zoom;
  // Centre the focus, but never show past the edge of the screen.
  const tx = Math.min(0, Math.max(width - viewport.width * s, width / 2 - cam.cx * s));
  const ty = Math.min(0, Math.max(height - viewport.height * s, height / 2 - cam.cy * s));
  const mapper: Mapper = { scale: s, map: (px, py) => [tx + px * s, ty + py * s] };
  return (
    <div style={{ position: "absolute", left: x, top: y, width, height, borderRadius: radius, overflow: "hidden",
      background: C.white, boxShadow: "0 2px 6px rgba(20,28,56,.06), 0 40px 90px rgba(20,28,56,.22)" }}>
      <Img src={staticFile(src)} style={{ position: "absolute", left: tx, top: ty,
        width: viewport.width * s, height: viewport.height * s }} />
      <ScreenSpace.Provider value={mapper}>{children}</ScreenSpace.Provider>
      {sample && <span style={{ position: "absolute", right: 18, bottom: 16, fontFamily: FONT, fontSize: Math.max(14, width / 90),
        fontWeight: 700, color: C.muted, background: "rgba(255,255,255,.92)", border: "1px solid #dfe3ee",
        padding: "4px 12px", borderRadius: 999 }}>Sample data</span>}
    </div>
  );
};

// A piece of another screenshot, placed in screen space: used to lift a deal card off the board.
export const Patch: React.FC<{ src: string; from: Box; to: { x: number; y: number }; viewport: { width: number; height: number };
  lift?: number; style?: React.CSSProperties }> = ({ src, from, to, viewport, lift = 0, style }) => {
  const { scale, map } = useScreenSpace();
  const [left, top] = map(to.x, to.y);
  return (
    <div style={{ position: "absolute", left, top, width: from.width * scale, height: from.height * scale, overflow: "hidden",
      borderRadius: 12 * scale, transform: `rotate(${lift * 2.5}deg) scale(${1 + lift * 0.04})`,
      boxShadow: lift ? `0 ${24 * lift}px ${50 * lift}px rgba(20,28,56,${0.28 * lift})` : "none", ...style }}>
      <Img src={staticFile(src)} style={{ position: "absolute", left: -from.x * scale, top: -from.y * scale,
        width: viewport.width * scale, height: viewport.height * scale }} />
    </div>
  );
};

// A soft cursor that glides between points and pulses when it clicks.
export const Cursor: React.FC<{ path: { at: number; x: number; y: number }[]; clicks?: number[]; appear?: number }> =
  ({ path, clicks = [], appear = 0 }) => {
    const frame = useCurrentFrame();
    const { map } = useScreenSpace();
    const opts = { easing: ease, extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
    const at = path.map(p => p.at);
    const px = path.length > 1 ? interpolate(frame, at, path.map(p => p.x), opts) : path[0].x;
    const py = path.length > 1 ? interpolate(frame, at, path.map(p => p.y), opts) : path[0].y;
    const [x, y] = map(px, py);
    const opacity = interpolate(frame, [appear, appear + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const press = clicks.reduce((v, c) => Math.max(v, interpolate(frame, [c, c + 4, c + 10], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })), 0);
    const ring = clicks.map(c => frame - c).filter(d => d >= 0 && d < 22)[0];
    return (
      <div style={{ position: "absolute", left: x, top: y, opacity, pointerEvents: "none" }}>
        {ring !== undefined && <div style={{ position: "absolute", left: -30, top: -30, width: 60, height: 60, borderRadius: "50%",
          border: `3px solid ${C.blue}`, opacity: 1 - ring / 22, transform: `scale(${0.4 + ring / 14})` }} />}
        <div style={{ position: "absolute", left: -22, top: -22, width: 44, height: 44, borderRadius: "50%",
          background: "rgba(30,91,214,.16)", transform: `scale(${1 + press * 0.3})` }} />
        <svg width="34" height="34" viewBox="0 0 24 24" style={{ position: "absolute", left: -4, top: -3, transform: `scale(${1 - press * 0.12})`,
          filter: "drop-shadow(0 3px 6px rgba(20,28,56,.35))" }}>
          <path d="M4 2.5 19.5 13l-7 1.2-3.6 6.3L4 2.5Z" fill={C.ink} stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      </div>
    );
  };

// A rounded highlight around a part of the screen, drawn in once it's needed.
export const Highlight: React.FC<{ box: Box; from: number; pad?: number; color?: string; until?: number }> =
  ({ box, from, pad = 10, color = C.coralBright, until }) => {
    const frame = useCurrentFrame();
    const { scale, map } = useScreenSpace();
    const [x, y] = map(box.x - pad, box.y - pad);
    const show = interpolate(frame, [from, from + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
    const hide = until ? interpolate(frame, [until, until + 10], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
    return (
      <div style={{ position: "absolute", left: x, top: y, width: (box.width + pad * 2) * scale, height: (box.height + pad * 2) * scale,
        borderRadius: 14 * scale, border: `${3.5}px solid ${color}`, boxShadow: `0 0 0 ${8 * show}px rgba(255,95,61,.14)`,
        opacity: show * hide, transform: `scale(${1.06 - show * 0.06})` }} />
    );
  };
