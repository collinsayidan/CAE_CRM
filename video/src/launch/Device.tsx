// Product in space: the app's screen as a floating glass slab, and a phone, both posed in 3D.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Screen, Shot } from "../Screen";
import { clamp, inOut } from "./look";

export type Pose = { at: number; rx?: number; ry?: number; rz?: number; x?: number; y?: number; z?: number; s?: number };

// Interpolates a pose between keyframes, eased in and out.
const posed = (f: number, poses: Pose[]) => {
  const keys = ["rx", "ry", "rz", "x", "y", "z", "s"] as const;
  const at = poses.map(p => p.at);
  const v: Record<string, number> = {};
  for (const k of keys) {
    const vals = poses.map(p => p[k] ?? (k === "s" ? 1 : 0));
    v[k] = poses.length === 1 ? vals[0] : interpolate(f, at, vals, { ...clamp, easing: inOut });
  }
  return v;
};

// The desktop app as a floating slab. width/height are its size on a 1920×1080 frame; poses move it in 3D.
export const Slab: React.FC<{
  src: string; shots: Shot[]; poses: Pose[]; width?: number; glow?: number; children?: React.ReactNode; sample?: boolean;
}> = ({ src, shots, poses, width = 1500, glow = 1, children, sample = true }) => {
  const f = useCurrentFrame();
  const p = posed(f, poses);
  const height = width * 9 / 16;
  return (
    <AbsoluteFill style={{ perspective: 2400, perspectiveOrigin: "50% 45%" }}>
      {/* Light thrown on the floor under the screen. */}
      <div style={{ position: "absolute", left: 960 - width * 0.55 + p.x, top: 540 + height * 0.42 + p.y, width: width * 1.1, height: 260,
        background: "radial-gradient(50% 50% at 50% 40%, rgba(61,123,255,.45), transparent 70%)", filter: "blur(30px)",
        opacity: glow, transform: `scale(${p.s})` }} />
      <div style={{ position: "absolute", left: 960 - width / 2, top: 540 - height / 2, width, height, transformStyle: "preserve-3d",
        transform: `translate3d(${p.x}px, ${p.y}px, ${p.z}px) rotateX(${p.rx}deg) rotateY(${p.ry}deg) rotateZ(${p.rz}deg) scale(${p.s})` }}>
        <div style={{ position: "absolute", inset: -10, borderRadius: 34, background: "linear-gradient(160deg, #2a3350, #0b1022 60%)",
          boxShadow: `0 60px 160px rgba(0,0,0,.7), 0 0 ${140 * glow}px rgba(61,123,255,${0.35 * glow})` }} />
        <Screen src={src} viewport={{ width: 1920, height: 1080 }} shots={shots} x={0} y={0} width={width} radius={24} sample={sample}>
          {children}
        </Screen>
        {/* A soft sheen across the glass. */}
        <div style={{ position: "absolute", inset: 0, borderRadius: 24, pointerEvents: "none",
          background: "linear-gradient(115deg, rgba(255,255,255,.14) 0%, rgba(255,255,255,0) 32%, rgba(255,255,255,0) 70%, rgba(255,255,255,.05) 100%)" }} />
      </div>
    </AbsoluteFill>
  );
};

// A phone with a real phone-width screenshot, posed in 3D. cx/cy is its centre on the frame.
export const Phone: React.FC<{ src: string; poses: Pose[]; cx?: number; cy?: number; width?: number; shots?: Shot[]; children?: React.ReactNode }> =
  ({ src, poses, cx = 960, cy = 540, width = 400, shots, children }) => {
    const f = useCurrentFrame();
    const p = posed(f, poses);
    const vp = { width: 430, height: 932 };
    const height = width * vp.height / vp.width;
    const rim = width * 0.045;
    return (
      <div style={{ position: "absolute", left: cx - width / 2, top: cy - height / 2, width, height, transformStyle: "preserve-3d",
        transform: `translate3d(${p.x}px, ${p.y}px, ${p.z}px) rotateX(${p.rx}deg) rotateY(${p.ry}deg) rotateZ(${p.rz}deg) scale(${p.s})` }}>
        <div style={{ position: "absolute", inset: -rim, borderRadius: width * 0.17, background: "linear-gradient(150deg, #3a4260, #0c0f1c 55%, #1b2138)",
          boxShadow: "0 50px 120px rgba(0,0,0,.65), 0 0 90px rgba(61,123,255,.28), inset 0 0 0 2px rgba(255,255,255,.08)" }} />
        <Screen src={src} viewport={vp} shots={shots ?? [{ at: 0, zoom: 1 }]} x={0} y={0} width={width} radius={width * 0.13} sample={false}>
          {children}
        </Screen>
        <div style={{ position: "absolute", left: width / 2 - width * 0.14, top: width * 0.035, width: width * 0.28, height: width * 0.07,
          borderRadius: 999, background: "#05070d" }} />
        <div style={{ position: "absolute", inset: 0, borderRadius: width * 0.13, pointerEvents: "none",
          background: "linear-gradient(120deg, rgba(255,255,255,.16), rgba(255,255,255,0) 35%)" }} />
      </div>
    );
  };
