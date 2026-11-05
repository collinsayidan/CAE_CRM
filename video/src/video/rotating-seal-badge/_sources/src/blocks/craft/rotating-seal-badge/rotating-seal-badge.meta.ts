// Built with Remotion - https://remotion.pro/license
import { defineVideoMeta } from "../../../kit/spec";
export const meta = defineVideoMeta({
  "spec": "21st.video/1",
  "kind": "scene",
  "category": "cta/craft",
  "job": "cta",
  "language": "kinetic-poster",
  "mechanic": [
    "stamp"
  ],
  "tags": [
    "cta",
    "invitation",
    "seal",
    "badge",
    "stamp",
    "circle",
    "typography",
    "logo"
  ],
  "engines": {
    "remotion": ">=4.0.479 <5"
  },
  "timing": {
    "fps": 30,
    "duration": {
      "default": 180,
      "min": 140,
      "max": 600
    },
    "stretch": "hold",
    "phases": {
      "in": 120,
      "out": 0
    },
    "markers": {
      "settled": 120,
      "tighten": 55,
      "stamp": 88
    },
    "beats": [
      0,
      20,
      55,
      88,
      120
    ]
  },
  "layout": {
    "aspects": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "mode": "responsive",
    "fill": "frame",
    "safeArea": "action",
    "transparent": true,
    "backdrop": [
      "background"
    ]
  },
  "slots": [
    {
      "key": "logo",
      "type": "image",
      "role": "logo"
    },
    {
      "key": "text",
      "type": "text",
      "role": "eyebrow",
      "maxChars": 64,
      "lines": 1
    },
    {
      "key": "action",
      "type": "text",
      "role": "cta",
      "maxChars": 24,
      "lines": 2
    },
    {
      "key": "destination",
      "type": "text",
      "role": "subline",
      "maxChars": 32,
      "lines": 2
    }
  ],
  "brand": {
    "primary": "colors.primary",
    "secondary": "colors.secondary",
    "color": "colors.text",
    "background": "colors.background",
    "fontFamily": "fonts.display"
  },
  "render": {
    "deterministic": true,
    "clientRenderable": true,
    "webgl": false,
    "requiresGpu": false
  },
  "preview": {
    "poster": {
      "marker": "settled"
    },
    "hover": [
      0,
      180
    ]
  },
  "provenance": {
    "origin": "own",
    "license": "MIT",
    "sourceUrl": "21st first-party (a ring of typography brakes and stamps around a logo and action invitation, 2026-10-09)"
  }
});
