// Built with Remotion - https://remotion.pro/license
import { defineVideoMeta } from "../../../kit/spec";

export const meta = defineVideoMeta({
  spec: "21st.video/1",
  kind: "scene",
  category: "product-ui/craft",
  job: "product-ui",
  language: "product-ui",
  mechanic: ["assemble"],
  energy: "default",
  tags: ["screenshot", "product ui", "website", "tiles", "grid", "assemble", "reveal", "launch"],
  engines: { remotion: ">=4.0.479 <5" },
  timing: {
    fps: 30,
    duration: { default: 180, min: 150, max: 600 },
    stretch: "hold",
    phases: { in: 146, out: 0 },
    // land: the last (center) tile touches down; weld: gutters fully closed.
    markers: { settled: 146, land: 74, weld: 110 },
    beats: [0, 12, 74, 92, 110, 146],
  },
  layout: { aspects: ["16:9", "9:16", "1:1"], mode: "responsive", fill: "frame", safeArea: "action", transparent: true, backdrop: ["background"] },
  slots: [
    { key: "image", type: "image", role: "screenshot" },
    { key: "logo", type: "image", role: "logo" },
    { key: "caption", type: "text", maxChars: 40, lines: 2, role: "caption" },
  ],
  brand: { color: "colors.text", accent: "colors.primary", secondary: "colors.secondary", background: "colors.background", fontFamily: "fonts.heading" },
  motionBeats: [
    { target: "tile", prop: "drop", from: "above", settledBy: 80, easing: "spring" },
    { target: "gutter", prop: "width", settledBy: 110, easing: "ease" },
    { target: "caption", prop: "y", from: "below", settledBy: 140, easing: "spring" },
  ],
  render: { deterministic: true, clientRenderable: true, webgl: false, requiresGpu: false },
  preview: { poster: { marker: "settled" }, hover: [0, 180] },
  provenance: { origin: "own", license: "MIT", sourceUrl: "21st first-party (screenshot cut into nine tiles that land and weld into one picture, 2026-10-08)" },
});
