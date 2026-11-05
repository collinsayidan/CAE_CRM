// Built with Remotion - https://remotion.pro/license
export const meta = {
  "spec": "21st.video/1",
  "kind": "scene",
  "category": "product-ui/craft",
  "job": "product-ui",
  "language": "product-ui",
  "mechanic": [
    "assemble"
  ],
  "energy": "default",
  "tags": [
    "screenshot",
    "product ui",
    "website",
    "tiles",
    "grid",
    "assemble",
    "reveal",
    "launch"
  ],
  "engines": {
    "remotion": ">=4.0.479 <5"
  },
  "timing": {
    "fps": 30,
    "duration": {
      "default": 180,
      "min": 150,
      "max": 600
    },
    "stretch": "hold",
    "phases": {
      "in": 146,
      "out": 0
    },
    "markers": {
      "settled": 146,
      "land": 74,
      "weld": 110
    },
    "beats": [
      0,
      12,
      74,
      92,
      110,
      146
    ],
    "loop": false
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
      "key": "image",
      "type": "image",
      "role": "screenshot"
    },
    {
      "key": "logo",
      "type": "image",
      "role": "logo"
    },
    {
      "key": "caption",
      "type": "text",
      "maxChars": 40,
      "lines": 2,
      "role": "caption"
    }
  ],
  "brand": {
    "color": "colors.text",
    "accent": "colors.primary",
    "secondary": "colors.secondary",
    "background": "colors.background",
    "fontFamily": "fonts.heading"
  },
  "motionBeats": [
    {
      "target": "tile",
      "prop": "drop",
      "from": "above",
      "settledBy": 80,
      "easing": "spring"
    },
    {
      "target": "gutter",
      "prop": "width",
      "settledBy": 110,
      "easing": "ease"
    },
    {
      "target": "caption",
      "prop": "y",
      "from": "below",
      "settledBy": 140,
      "easing": "spring"
    }
  ],
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
    "sourceUrl": "21st first-party (screenshot cut into nine tiles that land and weld into one picture, 2026-10-08)"
  },
  "defaults": {
    "image": "",
    "focus": "center",
    "logo": "",
    "caption": "See the full picture",
    "color": "#F4F6FB",
    "accent": "#FF7AB6",
    "secondary": "#7CC6FE",
    "background": "#0F1420",
    "fontFamily": "Geist",
    "seed": 7
  },
  "fields": [
    {
      "key": "image",
      "label": "Image",
      "type": "asset",
      "role": "screenshot"
    },
    {
      "key": "focus",
      "label": "Focus",
      "type": "select",
      "options": [
        "center",
        "top"
      ]
    },
    {
      "key": "logo",
      "label": "Logo",
      "type": "asset",
      "role": "logo"
    },
    {
      "key": "caption",
      "label": "Caption",
      "type": "text",
      "max": 40,
      "role": "caption"
    },
    {
      "key": "color",
      "label": "Color",
      "type": "color",
      "brand": "colors.text"
    },
    {
      "key": "accent",
      "label": "Accent",
      "type": "color",
      "brand": "colors.primary"
    },
    {
      "key": "secondary",
      "label": "Secondary",
      "type": "color",
      "brand": "colors.secondary"
    },
    {
      "key": "background",
      "label": "Background",
      "type": "color",
      "brand": "colors.background",
      "backdrop": true
    },
    {
      "key": "fontFamily",
      "label": "Font family",
      "type": "font",
      "brand": "fonts.heading"
    },
    {
      "key": "seed",
      "label": "Seed",
      "type": "number",
      "step": 1,
      "min": 1,
      "max": 99
    }
  ],
  "name": "Tiled Screenshot Reveal",
  "catalogGates": {
    "schema": "21st.video-catalog-gates/2",
    "ref": "puzzle-grid-reveal",
    "bundleSha256": "565846aca42111fb0ddd3d0dd9adfa8ee0525f5f064660fed275bec9eaa11a09",
    "sourceSnapshot": {
      "sha256": "ade5a01d4641fd068192eed79974774977f5294a073659ffd767e9f0122d76ab",
      "files": 1800
    },
    "renderedAt": "2026-10-09T08:00:14.607Z",
    "samples": [
      {
        "aspect": "16:9",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-paper.png",
        "sha256": "5a1c6ce7a3874fb09ff799fa2fff1527c3eda4930c4dbd47aedc09ffef813221"
      },
      {
        "aspect": "16:9",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-night.png",
        "sha256": "f0cf42ea71d88471a02bfc3f3ce14997db3e51dad966d6f13526c42284e4d114"
      },
      {
        "aspect": "16:9",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-color.png",
        "sha256": "3ba7653eb558e0a58d23f18101e340922e0f3822a10c430e009e9319a884a47d"
      },
      {
        "aspect": "9:16",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-paper.png",
        "sha256": "5ff70bf409479fba695d74eec6b6303358c9781352eea89e31a15886412934b9"
      },
      {
        "aspect": "9:16",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-night.png",
        "sha256": "6ce6fd5fd92d302900ccd66f227e30c2ec879434459ccfa5cfb86125024b19ef"
      },
      {
        "aspect": "9:16",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-color.png",
        "sha256": "f1cab299ad7f74a6b605d4677ccff71acb3b7425ee732f2d17494060ccb40416"
      },
      {
        "aspect": "1:1",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-paper.png",
        "sha256": "1edaca11780611bed91ca0a3ecb928a133134d51902e6b888a48e38421ac5bbb"
      },
      {
        "aspect": "1:1",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-night.png",
        "sha256": "7372aa007a34f02d8aa8ca871a6e1125f9f29adccdd0a61dda7317bcd18658e5"
      },
      {
        "aspect": "1:1",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-color.png",
        "sha256": "0ad9b73593f74848736c2dd713287287aaea7fc16a1ff58c165bd628a3b505f0"
      }
    ],
    "gates": {
      "contract": {
        "pass": true,
        "errors": [],
        "transparency": [
          {
            "aspect": "16:9",
            "brand": "paper",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "16:9",
            "brand": "night",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "16:9",
            "brand": "color",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "9:16",
            "brand": "paper",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "9:16",
            "brand": "night",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "9:16",
            "brand": "color",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "1:1",
            "brand": "paper",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "1:1",
            "brand": "night",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          },
          {
            "aspect": "1:1",
            "brand": "color",
            "corners": [
              0,
              0,
              0,
              0
            ],
            "pass": true
          }
        ]
      },
      "formats": {
        "pass": true,
        "rendered": [
          "puzzle-grid-reveal--16x9",
          "puzzle-grid-reveal--9x16",
          "puzzle-grid-reveal--1x1"
        ]
      },
      "brand": {
        "pass": true,
        "sourcePaintLiterals": [],
        "sourceFontLiterals": [],
        "samples": [
          {
            "aspect": "16:9",
            "pass": true,
            "paperNight": 29.78073459201389,
            "paperColor": 12.15451388888889,
            "region": {
              "left": 117,
              "top": 0,
              "width": 1686,
              "height": 1015
            },
            "canvas": {
              "width": 1920,
              "height": 1080
            }
          },
          {
            "aspect": "9:16",
            "pass": true,
            "paperNight": 27.78729926215278,
            "paperColor": 12.265543619791666,
            "region": {
              "left": 0,
              "top": 343,
              "width": 1080,
              "height": 1017
            },
            "canvas": {
              "width": 1080,
              "height": 1920
            }
          },
          {
            "aspect": "1:1",
            "pass": true,
            "paperNight": 29.527235243055557,
            "paperColor": 12.326958550347221,
            "region": {
              "left": 0,
              "top": 55,
              "width": 1080,
              "height": 854
            },
            "canvas": {
              "width": 1080,
              "height": 1080
            }
          }
        ],
        "note": "Measured three rebrands over their actual subject union; contract checks color bindings. Visual brand adherence needs semantic review."
      },
      "readability": {
        "pass": true,
        "probes": [
          {
            "aspect": "16:9",
            "brand": "paper",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.9916042034097592,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "16:9",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 1.1696072622721931,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "16:9",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.9916042034097592,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "9:16",
            "brand": "paper",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.6835199357520788,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "9:16",
            "brand": "night",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.7506909013605444,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "9:16",
            "brand": "color",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.6827817932728648,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "1:1",
            "brand": "paper",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 1.0209330645838584,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "1:1",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 1.1206643151087599,
            "bad": [],
            "measured": 1
          },
          {
            "aspect": "1:1",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 1.0209330645838584,
            "bad": [],
            "measured": 1
          }
        ]
      },
      "motion": {
        "pass": true,
        "averageChannelDifference": 37.1826171875,
        "frames": [
          21,
          146,
          179
        ],
        "elastic": [
          {
            "aspect": "16:9",
            "duration": 150,
            "averageChannelDifference": 39.951931423611114,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-150-frame-18.png",
                "sha256": "c0954d0ec9e213e6f96f277d655a92c075019d6fba9eccf7847f604b9ee98196",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-150-frame-146.png",
                "sha256": "5b46043fdd40877a4509678a708c4ac54a69a0d8ff2659423d306b7f9cacad51",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-150-frame-132.png",
                "sha256": "0b98d0933958ba469de7b412d86329425bf53daa7102dcc36cc62cc59c569d6d",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-150-frame-149.png",
                "sha256": "89b76c51d65db7b6552a497fe88fc1d7bcd38bfc38feea395e7947a318df9da2",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "16:9",
            "duration": 600,
            "averageChannelDifference": 37.1826171875,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-600-frame-21.png",
                "sha256": "31495d3ac31dd0d1db5b8d857774264acb682483291d05d6ee84fc675af11334",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-600-frame-146.png",
                "sha256": "5b46043fdd40877a4509678a708c4ac54a69a0d8ff2659423d306b7f9cacad51",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-600-frame-528.png",
                "sha256": "0cd51e14a6cf7f17a301a010e73c469be3d1a9b89dc24ac9bb0b568465e9104b",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/16x9-duration-600-frame-599.png",
                "sha256": "0cd51e14a6cf7f17a301a010e73c469be3d1a9b89dc24ac9bb0b568465e9104b",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 150,
            "averageChannelDifference": 38.117947048611114,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-150-frame-18.png",
                "sha256": "d5cc4f2f3b6e987be261ddece469972538128386a84bbe92cba4e9f456dcd79b",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-150-frame-146.png",
                "sha256": "cff95b22e12eeeb4ed96008b7d6b2ffd10630d833a75610b7fd726a7f3d18f51",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-150-frame-132.png",
                "sha256": "e375728648a3ef089223b9ecdcdaa5d9428c7772a1d7e92b83d195db579ec5e2",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-150-frame-149.png",
                "sha256": "807ab98382bfe13dba92356fcdf27cbb362905ee29f76f16f9651531ed8e6b26",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 600,
            "averageChannelDifference": 35.403103298611114,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-600-frame-21.png",
                "sha256": "94252c2001f1d26c571a0c7d7345b8884eb86f1e01e3fbf48961e70404707f74",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-600-frame-146.png",
                "sha256": "cff95b22e12eeeb4ed96008b7d6b2ffd10630d833a75610b7fd726a7f3d18f51",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-600-frame-528.png",
                "sha256": "0ab7389a24964b2ec0d96795f5e327bc07e636ab3d8b693de768985e37ce3e12",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/9x16-duration-600-frame-599.png",
                "sha256": "0ab7389a24964b2ec0d96795f5e327bc07e636ab3d8b693de768985e37ce3e12",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 150,
            "averageChannelDifference": 47.79991319444444,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-150-frame-18.png",
                "sha256": "bade3b8ee274311713b4fcf1b90515e240c34c99bac2abc9d46c11c142d248bf",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-150-frame-146.png",
                "sha256": "6ffe1720936a12b5dc85c273079d5c8be4f7f05aedc77ece6728689b755f05a8",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-150-frame-132.png",
                "sha256": "6b9bc6ca78370e9582c74e5994b85565512e4201034914de710d11cc2408ffb3",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-150-frame-149.png",
                "sha256": "36ba7da291e383798de849dadb8a2f0dbf03cd2de14ad7eb2a230fe448f831fb",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 600,
            "averageChannelDifference": 44.54112413194444,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-600-frame-21.png",
                "sha256": "a498ddc59432a3479208b44b5130f854b49bc2d1f284628ee9e2010a9720712d",
                "alphaMass": 587520
              },
              {
                "frame": 146,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-600-frame-146.png",
                "sha256": "6ffe1720936a12b5dc85c273079d5c8be4f7f05aedc77ece6728689b755f05a8",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-600-frame-528.png",
                "sha256": "1a4637c861098dbc2f3f323daacd48c83f3d943ff15de0291463c5193ed918d3",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-094607/puzzle-grid-reveal/1x1-duration-600-frame-599.png",
                "sha256": "1a4637c861098dbc2f3f323daacd48c83f3d943ff15de0291463c5193ed918d3",
                "alphaMass": 587520
              }
            ]
          }
        ],
        "note": "Measured motion and final alpha retention at min/max in all three formats; sampled frames do not certify full playback."
      },
      "semantic": {
        "pass": true,
        "recognizedJob": "product-ui",
        "titleMatches": true,
        "noBakedHeading": true,
        "brandAdherence": true,
        "languageAdherence": true,
        "note": "1. TitleMatches: The progression from image 2 (a set of tiles with a card revealing itself) to images 3 and 4 (a full interface is revealed and clarified) supports the 'Tiled Screenshot Reveal' title. The composition and sampled motion match the claimed effect, showing an interface being revealed in segments or tiles before the full image. 2. NoBakedHeading: There is no evidence of a decorative block title or category label baked into the composition; all visible text ('See the full picture') is legitimate named-slot content. 3. BrandAdherence: Images 5 through 7 show the same poster in three distinctly colored palettes matching the provided swatches. All are legible, with text, accents, and surfaces adjusting appropriately across light, dark, and colored backgrounds. There are no unexplained fixed block colors, and shape/material is preserved. 4. LanguageAdherence: Materials, interface style, color roles, and visible type roles remain consistent with the language card's direction (flat surfaces, restrained elevation, sans display/body, palette use). All rebrands and motion samples respect these conventions throughout, confirming adherence to the provided language card."
      },
      "duplicates": {
        "pass": true,
        "threshold": 0.97,
        "required": 56,
        "compared": 56,
        "matches": []
      }
    },
    "pass": true,
    "humanSelection": {
      "selected": true,
      "bundleSha256": "565846aca42111fb0ddd3d0dd9adfa8ee0525f5f064660fed275bec9eaa11a09",
      "selectedBy": "serafim (repo owner): publish every craft block that passes the gates and the creativity jury (2026-10-08)",
      "at": "2026-10-09T08:05:06.547Z",
      "basis": "Craft harness: passed the creativity jury against owner-liked anchors"
    }
  },
  "renditions": {
    "16:9": {
      "poster": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/16x9/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/16x9/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/16x9/detail.mp4",
      "bg": "#0b0e17",
      "posterFrame": 146,
      "size": [
        1920,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "2b5f0520ea41a2d1b362f19c0d4a084f89087946898e5e098d48707396fcc4dc",
        "loop": "2cd07cbb581b426bd64fbce6af19fc61ca58ae0ac58d3955f5b24b8f39ba710e",
        "detail": "c3234163bb42d87e384c926e9b5fc2dcbc695a743b0903667b42b3d755e069ec"
      }
    },
    "9:16": {
      "poster": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/9x16/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/9x16/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/9x16/detail.mp4",
      "bg": "#0b0e17",
      "posterFrame": 146,
      "size": [
        1080,
        1920
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "941003e89cccb91f2bc6c3dc15599ddab76620a369d2e7002b06313eca12e3c7",
        "loop": "ac367e5aee7a74b54486ef5615815900597663123314e4bdec6a7f30d35bd33a",
        "detail": "59cbfe598234817f316a2ab73a5619588f8f01b82f7f392cae7da277712049eb"
      }
    },
    "1:1": {
      "poster": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/1x1/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/1x1/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/puzzle-grid-reveal/1x1/detail.mp4",
      "bg": "#0b0e17",
      "posterFrame": 146,
      "size": [
        1080,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "402f0bf2dd85c50d13242ff045632973ba7b751a8edfe79c8bef0f0be5f00dc7",
        "loop": "e84c214456a37287475683ebc871a7d567b81eab6d0f80b4b60c0922e0e67f75",
        "detail": "59b3b7ab03cebaa1eb1312bac760a7df1797572229d41c74b49d50d562611e96"
      }
    }
  },
  "bundle": {
    "url": "https://cdn.21st.dev/video-bundles/565846aca42111fb0ddd3d0dd9adfa8ee0525f5f064660fed275bec9eaa11a09/index.mjs",
    "sha256": "565846aca42111fb0ddd3d0dd9adfa8ee0525f5f064660fed275bec9eaa11a09",
    "bytes": 172256,
    "externals": [
      "react",
      "react/jsx-runtime",
      "remotion",
      "remotion/no-react",
      "zod"
    ],
    "versions": {
      "kit": "0.1.0",
      "remotion": "4.0.533",
      "react": "19.2.1"
    }
  },
  "gates": {
    "16:9": {
      "speed": true,
      "determinism": true,
      "flat": true,
      "overflow": true
    },
    "9:16": {
      "speed": true,
      "determinism": true,
      "flat": true,
      "overflow": true
    },
    "1:1": {
      "speed": true,
      "determinism": true,
      "flat": true,
      "overflow": true
    }
  },
  "intake": {
    "at": "2026-10-09T09:03:23.436Z",
    "kit": "0.1.0",
    "licenseKeyPresent": false
  }
};
