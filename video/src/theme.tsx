import React, { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

// The app's own palette and type (static/style.css): royal blue, coral for the one action that matters, yellow accents.
export const C = {
  blue: "#1e5bd6",
  blueDeep: "#1747ad",
  coral: "#d13f23",
  coralBright: "#ff5f3d",
  yellow: "#ffc93c",
  ink: "#141a33",
  muted: "#5b6480",
  canvas: "#f4f6fb",
  white: "#ffffff",
  ok: "#1f8f5f",
};

export const FONT = '"Plus Jakarta Sans", system-ui, sans-serif';

// Loads the app's font once, holding the render until it's ready so no frame shows a fallback face.
export const useBrandFont = () => {
  const [handle] = useState(() => delayRender("Loading Plus Jakarta Sans"));
  useEffect(() => {
    const face = new FontFace("Plus Jakarta Sans", `url(${staticFile("fonts/plus-jakarta-sans-latin-wght-normal.woff2")}) format("woff2")`,
      { weight: "200 800" });
    face.load().then(f => { document.fonts.add(f); continueRender(handle); }).catch(() => continueRender(handle));
  }, [handle]);
};

export const BrandBackground: React.FC<{ tone?: "blue" | "light" }> = ({ tone = "light" }) => (
  <div style={{
    position: "absolute", inset: 0,
    background: tone === "blue"
      ? `radial-gradient(60% 70% at 85% 10%, rgba(255,255,255,.16), transparent 70%), radial-gradient(50% 60% at 0% 100%, rgba(255,95,61,.22), transparent 70%), ${C.blue}`
      : `radial-gradient(50% 60% at 95% 0%, rgba(30,91,214,.14), transparent 70%), radial-gradient(45% 55% at 0% 100%, rgba(255,201,60,.18), transparent 70%), ${C.canvas}`,
  }} />
);
