// Built with Remotion - https://remotion.pro/license
import { defineVideoMeta } from "../../../kit/spec";

export const meta = defineVideoMeta({
  spec: "21st.video/1",
  kind: "background",
  category: "backgrounds/craft",
  job: "backgrounds",
  language: "aura",
  mechanic: ["ripple"],
  energy: "calm",
  tags: ["background", "dots", "dot grid", "ripple", "waves", "interference", "rhythm", "beat", "drops", "water", "perspective", "headline", "ambient", "glow"],
  engines: { remotion: ">=4.0.479 <5" },
  timing: {
    fps: 30,
    duration: { default: 180, min: 150, max: 1800 },
    stretch: "hold",
    phases: { in: 140, out: 0 },
    markers: { settled: 140, wake: 0, first: 14, build: 50, last: 108, headline: 112 },
    // One drop per beat (18 frames = 100 bpm), a held breath, then the last drop under the headline.
    beats: [14, 32, 50, 68, 86, 108, 140],
  },
  layout: { aspects: ["16:9", "9:16", "1:1"], mode: "responsive", fill: "frame", safeArea: "action", transparent: true, backdrop: ["background"] },
  slots: [{ key: "headline", type: "text", maxChars: 60, lines: 2, role: "headline" }],
  brand: {
    color: "colors.text",
    primary: "colors.primary",
    secondary: "colors.secondary",
    background: "colors.background",
    fontFamily: "fonts.heading",
  },
  motionBeats: [
    { target: "field", prop: "opacity", from: "0", settledBy: 14, easing: "ease" },
    { target: "drops", prop: "ripple", from: "calm", settledBy: 108, easing: "linear" },
    { target: "headline", prop: "y", from: "below", settledBy: 140, easing: "spring" },
  ],
  render: { deterministic: true, clientRenderable: true, webgl: false, requiresGpu: false },
  preview: { poster: { marker: "settled" }, hover: [0, 180] },
  provenance: { origin: "own", license: "MIT", sourceUrl: "21st first-party (drops land on the beat in a perspective dot field and their ripples interfere, 2026-10-08)" },
});
