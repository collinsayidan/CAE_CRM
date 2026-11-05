import React from "react";
import { Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { BrandBackground, C, FONT } from "./theme";

const clamp = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
const ease = Easing.bezier(0.22, 1, 0.36, 1);

// Rises into place: used for every line of text.
export const Rise: React.FC<{ delay?: number; children: React.ReactNode; style?: React.CSSProperties; distance?: number }> =
  ({ delay = 0, children, style, distance = 36 }) => {
    const frame = useCurrentFrame();
    const t = interpolate(frame, [delay, delay + 18], [0, 1], { ...clamp, easing: ease });
    return <div style={{ opacity: t, transform: `translateY(${(1 - t) * distance}px)`, ...style }}>{children}</div>;
  };

// The caption under a screen: one short line in a white pill, with a coral marker.
export const Caption: React.FC<{ text: string; from?: number; until: number; size?: number; bottom?: number; top?: number; width?: number }> =
  ({ text, from = 6, until, size = 46, bottom, top, width }) => {
    const frame = useCurrentFrame();
    const show = interpolate(frame, [from, from + 16], [0, 1], { ...clamp, easing: ease });
    const hide = interpolate(frame, [until - 10, until], [1, 0], clamp);
    return (
      <div style={{ position: "absolute", left: 0, right: 0, bottom, top, display: "flex", justifyContent: "center",
        opacity: show * hide, transform: `translateY(${(1 - show) * 30}px)` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, maxWidth: width, padding: `${size * 0.42}px ${size * 0.8}px`,
          borderRadius: 999, background: C.white, boxShadow: "0 18px 50px rgba(20,28,56,.22)", fontFamily: FONT,
          fontWeight: 800, fontSize: size, letterSpacing: "-0.02em", color: C.ink, lineHeight: 1.15, textAlign: "center" }}>
          <span style={{ flex: "none", width: size * 0.32, height: size * 0.32, borderRadius: "50%", background: C.coralBright }} />
          {text}
        </div>
      </div>
    );
  };

// The coral logo, white wordmark on blue.
export const Logo: React.FC<{ height: number }> = ({ height }) => (
  <Img src={staticFile("brand/cae-crm-logo-on-dark.svg")} style={{ height }} />
);

export const BrandCard: React.FC<{ tagline: React.ReactNode; vertical?: boolean }> = ({ tagline, vertical }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  return (
    <div style={{ position: "absolute", inset: 0, fontFamily: FONT }}>
      <BrandBackground tone="blue" />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", gap: vertical ? 60 : 44, padding: vertical ? 80 : 120, textAlign: "center" }}>
        <div style={{ transform: `scale(${0.7 + pop * 0.3})`, opacity: pop }}><Logo height={vertical ? 120 : 96} /></div>
        <Rise delay={14}>
          <div style={{ color: C.white, fontWeight: 800, fontSize: vertical ? 92 : 78, lineHeight: 1.06, letterSpacing: "-0.035em",
            maxWidth: vertical ? 900 : 1300 }}>{tagline}</div>
        </Rise>
      </div>
    </div>
  );
};

// The closing card: the offer, the price and where to go.
export const EndCard: React.FC<{ vertical?: boolean; headline?: string; showPrice?: boolean }> =
  ({ vertical, headline = "Every feature included.", showPrice = true }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const pop = spring({ frame: frame - 34, fps, config: { damping: 12, stiffness: 140 } });
    return (
      <div style={{ position: "absolute", inset: 0, fontFamily: FONT }}>
        <BrandBackground tone="blue" />
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", gap: vertical ? 48 : 34, padding: 80, textAlign: "center", color: C.white }}>
          <Rise><Logo height={vertical ? 104 : 80} /></Rise>
          <Rise delay={8}>
            <div style={{ fontWeight: 800, fontSize: vertical ? 96 : 84, letterSpacing: "-0.035em", lineHeight: 1.05, maxWidth: vertical ? 900 : 1400 }}>
              {headline}</div>
          </Rise>
          {showPrice && <Rise delay={16}>
            <div style={{ fontWeight: 600, fontSize: vertical ? 44 : 38, color: "rgba(255,255,255,.86)" }}>
              £15 per user a month</div>
          </Rise>}
          <Rise delay={24}>
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap", justifyContent: "center", fontWeight: 700, fontSize: vertical ? 38 : 30 }}>
              {(showPrice ? ["14 days free", "No card needed"] : ["Every feature included", "No card needed"]).map(t => (
                <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 10, padding: "10px 22px", borderRadius: 999,
                  background: "rgba(255,255,255,.14)" }}>
                  <svg width="26" height="26" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke={C.yellow} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  {t}</span>))}
            </div>
          </Rise>
          <div style={{ transform: `scale(${Math.max(0, pop)})`, marginTop: 10, padding: vertical ? "30px 64px" : "24px 54px", borderRadius: 999,
            background: C.coral, fontWeight: 800, fontSize: vertical ? 46 : 36, boxShadow: "0 18px 40px rgba(0,0,0,.25)" }}>
            Start your free trial</div>
          <Rise delay={44}>
            <div style={{ fontWeight: 700, fontSize: vertical ? 40 : 32, color: "rgba(255,255,255,.9)" }}>cae.collinalitics.co.uk</div>
          </Rise>
        </div>
      </div>
    );
  };

// Fades a scene in and out at its edges, so consecutive scenes cross-dissolve where they overlap.
export const Fade: React.FC<{ duration: number; inFrames?: number; outFrames?: number; children: React.ReactNode }> =
  ({ duration, inFrames = 12, outFrames = 12, children }) => {
    const frame = useCurrentFrame();
    const o = Math.min(
      inFrames ? interpolate(frame, [0, inFrames], [0, 1], clamp) : 1,
      outFrames ? interpolate(frame, [duration - outFrames, duration], [1, 0], clamp) : 1);
    return <div style={{ position: "absolute", inset: 0, opacity: o }}>{children}</div>;
  };
