// Built with Remotion - https://remotion.pro/license
export const meta = {
  "spec": "21st.video/1",
  "kind": "scene",
  "category": "titles/craft",
  "job": "titles",
  "language": "isometric",
  "mechanic": [
    "flip"
  ],
  "tags": [
    "split-flap",
    "mechanical",
    "letters",
    "headline",
    "board",
    "hinge"
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
      "in": 135,
      "out": 0
    },
    "markers": {
      "settled": 135,
      "flips": 40,
      "lock": 110
    },
    "beats": [
      0,
      20,
      40,
      80,
      110,
      135
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
      "key": "text",
      "type": "text",
      "maxChars": 32,
      "lines": 7,
      "role": "headline"
    }
  ],
  "brand": {
    "primary": "colors.primary",
    "secondary": "colors.secondary",
    "color": "colors.text",
    "background": "colors.background",
    "fontFamily": "fonts.mono"
  },
  "motionBeats": [],
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
    "sourceUrl": "21st first-party (physical top and bottom split flaps cycle independently into the user headline, 2026-10-09)"
  },
  "defaults": {
    "text": "Make it happen",
    "primary": "#E5C07B",
    "secondary": "#61AFEF",
    "color": "#F5EDDC",
    "background": "#171B21",
    "fontFamily": "IBM Plex Mono",
    "seed": 53
  },
  "fields": [
    {
      "key": "text",
      "label": "Text",
      "type": "text",
      "max": 32,
      "role": "headline"
    },
    {
      "key": "primary",
      "label": "Primary",
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
      "key": "color",
      "label": "Color",
      "type": "color",
      "brand": "colors.text"
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
      "brand": "fonts.mono"
    },
    {
      "key": "seed",
      "label": "Seed",
      "type": "number",
      "step": 1
    }
  ],
  "name": "Split Flap Headline",
  "catalogGates": {
    "schema": "21st.video-catalog-gates/2",
    "ref": "split-flap-type",
    "bundleSha256": "87e366409b469a146b6aaecd46805f24c95e761eb0788d77ecb8e7615231a5ae",
    "sourceSnapshot": {
      "sha256": "40bd51d119bf7ee4ebdebf0c5a5cf3e861b724ade6d630e20d9914f0a4ce79bc",
      "files": 2022
    },
    "renderedAt": "2026-10-09T20:09:57.632Z",
    "samples": [
      {
        "aspect": "16:9",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-paper.png",
        "sha256": "2c0fe7745898bfde31b86683ff8cc28e6ea9d5a535745b647788d6cdaeb2435e"
      },
      {
        "aspect": "16:9",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-night.png",
        "sha256": "fcf115f14d24a2c45b212b4290c7649bdb8f3439083e5f005f264ae639dc8ce9"
      },
      {
        "aspect": "16:9",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-color.png",
        "sha256": "9a47eabf78e12ca36e37b3c064e6c73217d42b25b36f0862f5ef1a5aac783a27"
      },
      {
        "aspect": "9:16",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-paper.png",
        "sha256": "3f9d62c648ad3533b5a925710735f54a0dd707eb4c46b69da753f1727ad3730c"
      },
      {
        "aspect": "9:16",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-night.png",
        "sha256": "17ffa0ccac5cf93179621c457a54ee46798ea050900462eaf2d203c51c7f8649"
      },
      {
        "aspect": "9:16",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-color.png",
        "sha256": "9f4890f57613da26e56ad27da051a39ca7823d936b631d800b127a1abb25e040"
      },
      {
        "aspect": "1:1",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-paper.png",
        "sha256": "a5cec67193e4b795abe9f785d2efcd1328002d7aa4e90e13a6a180cfebea5b09"
      },
      {
        "aspect": "1:1",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-night.png",
        "sha256": "8dd3077b1eece4babac066dd6ec542e4f18ed3a4199cf205f15590dbe7cfa239"
      },
      {
        "aspect": "1:1",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-color.png",
        "sha256": "cf482409c32b82c352454760d286276658a3a0c4d6abad30eb2efbe42293b050"
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
          "split-flap-type--16x9",
          "split-flap-type--9x16",
          "split-flap-type--1x1"
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
            "paperNight": 129.96091037326389,
            "paperColor": 36.33485243055556,
            "region": {
              "left": 152,
              "top": 234,
              "width": 1616,
              "height": 616
            },
            "canvas": {
              "width": 1920,
              "height": 1080
            }
          },
          {
            "aspect": "9:16",
            "pass": true,
            "paperNight": 97.51803927951389,
            "paperColor": 27.495768229166668,
            "region": {
              "left": 85,
              "top": 431,
              "width": 910,
              "height": 1062
            },
            "canvas": {
              "width": 1080,
              "height": 1920
            }
          },
          {
            "aspect": "1:1",
            "pass": true,
            "paperNight": 130.62421332465277,
            "paperColor": 35.80726453993056,
            "region": {
              "left": 85,
              "top": 370,
              "width": 910,
              "height": 342
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
            "occupancy": 0.6803595923966296,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "16:9",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.6803595923966296,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "16:9",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.6803595923966296,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "9:16",
            "brand": "paper",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.660514495149912,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "9:16",
            "brand": "night",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.660514495149912,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "9:16",
            "brand": "color",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.660514495149912,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "1:1",
            "brand": "paper",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.37814765824025093,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "1:1",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.37814765824025093,
            "bad": [],
            "measured": 12
          },
          {
            "aspect": "1:1",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.37814765824025093,
            "bad": [],
            "measured": 12
          }
        ]
      },
      "motion": {
        "pass": true,
        "averageChannelDifference": 5.527452256944445,
        "frames": [
          20,
          135,
          179
        ],
        "elastic": [
          {
            "aspect": "16:9",
            "duration": 150,
            "averageChannelDifference": 5.210069444444445,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-150-frame-18.png",
                "sha256": "421adda4c91a8737b0b3e5ad4b4001a0234b56427ed2dffa21e3bf07eadc77c6",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-150-frame-135.png",
                "sha256": "bae47e8c6efa478a912ee6aa33a72a63f353e4bc0586d0bd965a2f2879de428b",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-150-frame-132.png",
                "sha256": "14439fc770d974a569394e5543e90efd3b4fc75a3b926dea86d86df5efb5a86c",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-150-frame-149.png",
                "sha256": "a4d530e72ecb473c3a00d7c3a70256f3d75b14dbbeaef13faf10af36c3200de4",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "16:9",
            "duration": 600,
            "averageChannelDifference": 5.527452256944445,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 20,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-600-frame-20.png",
                "sha256": "a8de91e974549101c86520dd81ece1d5494405a01c8ae70475437b9c6fa39361",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-600-frame-135.png",
                "sha256": "a1c2e1beb8e569c2031352c0d961b161a4c5e64cc65a210c73d3eac1763c46c4",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-600-frame-528.png",
                "sha256": "287ea7a9d1028be81d4cd42174e5cba159c38ace206f2916a12025b372fe0360",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/16x9-duration-600-frame-599.png",
                "sha256": "d2ed17b3c1fba689822c3b195934395983110c9a6f3d8c6bffc7a23e9129f058",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 150,
            "averageChannelDifference": 3.0873480902777777,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-150-frame-18.png",
                "sha256": "e35c8c07c0f8423e5529d37db8a05780bcbfddaa7a83fcf85b0a827788b3fb4d",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-150-frame-135.png",
                "sha256": "816eebfd67a64d25fa7bb17a448749aff60db04d824140bc122e80589d037a5f",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-150-frame-132.png",
                "sha256": "2f385d6a7e1531b87a426af3875c19811ba7e83f08b2ebe20308de490818f9a7",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-150-frame-149.png",
                "sha256": "7113d31eab3e069ccc3c28a5df8e2b90bae01d8c03989547ef79154a6e28fcac",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 600,
            "averageChannelDifference": 3.2106119791666665,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 20,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-600-frame-20.png",
                "sha256": "7255da7358931ca72d1ab6a3e15a2da0a895723e9a0936a4d5c204acf576125f",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-600-frame-135.png",
                "sha256": "98af413fbc213937ec5d3c5376595541d377821ceafd1c3f2444adb356ed5960",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-600-frame-528.png",
                "sha256": "60626326df76c9c43ee71d2f40f0ac8b4b68ed4b61bde6face3790671b183932",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/9x16-duration-600-frame-599.png",
                "sha256": "d142320d08ea316e77adea47e7580ea55eb11204685c26f1da2e6ab03883359e",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 150,
            "averageChannelDifference": 2.7051866319444446,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-150-frame-18.png",
                "sha256": "9010b510184583acaffe48f7ed79c70b02ee50e3b453a884f47682b304075d2e",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-150-frame-135.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-150-frame-132.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-150-frame-149.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 600,
            "averageChannelDifference": 2.8910590277777777,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 20,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-600-frame-20.png",
                "sha256": "5ee6e11716df1ae7711e6ea4b4fda58d974317a634998b8dfb107da7c87e29d6",
                "alphaMass": 587520
              },
              {
                "frame": 135,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-600-frame-135.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-600-frame-528.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T200541Z/gates/split-flap-type/1x1-duration-600-frame-599.png",
                "sha256": "55aa5471f0e9864929d1956070aeca45aad9263d03d7182bc6654adc6467cd1f",
                "alphaMass": 587520
              }
            ]
          }
        ],
        "note": "Measured motion and final alpha retention at min/max in all three formats; sampled frames do not certify full playback."
      },
      "semantic": {
        "pass": true,
        "recognizedJob": "titles",
        "titleMatches": true,
        "noBakedHeading": true,
        "brandAdherence": true,
        "languageAdherence": true,
        "note": "1. TitleMatches: All images depict a split-flap display, visually flipping between random combinations and ultimately settling on 'MAKE IT HAPPEN', supporting the 'Split Flap Headline' title. The motion samples (images 2-4) show plausible intermediate states: jumble, alternate characters, and resolution, matching the mechanical flipboard sequence. \n2. NoBakedHeading: No decorative title or unexplained label is visually embedded/baked in any of the posters; all text is part of the split-flap letter display itself and matches named-slot content.\n3. BrandAdherence: Three rebrand/poster variants (images 5-7) correctly redesign the display within provided palettes. Each preserves the split-flap shape, mechanics, and maintains clear legibility on distinct backgrounds, applying the right ink/ground roles per palette. No unexplained color blocks or palette mismatches are present.\n4. LanguageAdherence: The display’s structure (extruded block elements, shading, clear directional lighting and snap-to-ground), type roles (display sans, tabular numerals), and consistent mechanics (no UI mockup or floating overlays, no fake depth, no random tilt) are preserved across motion samples and palette variants, aligning with the supplied language card. The material and camera rules are upheld with clear parallel perspective and solid forms."
      },
      "duplicates": {
        "pass": true,
        "threshold": 0.97,
        "required": 66,
        "compared": 66,
        "matches": []
      }
    },
    "pass": true,
    "humanSelection": {
      "selected": true,
      "bundleSha256": "87e366409b469a146b6aaecd46805f24c95e761eb0788d77ecb8e7615231a5ae",
      "selectedBy": "Owner-authorized continuation, executed by Codex",
      "at": "2026-10-09T20:24:37.855Z",
      "basis": "Resumed the owner's request to publish craft blocks that pass catalog gates and the blind creativity jury"
    },
    "creativityReview": {
      "ref": "split-flap-type",
      "vsPositive": 1,
      "vsNegative": 1,
      "fakeVotes": 0,
      "perModel": {
        "claude": {
          "vsPositive": 1,
          "vsNegative": 1
        },
        "gpt": {
          "vsPositive": 1,
          "vsNegative": 1
        },
        "gemini": {
          "vsPositive": 1,
          "vsNegative": 1
        }
      },
      "errors": 0,
      "calls": 48,
      "complete": true,
      "framesSha256": "731df999757f7cab2a0ae147181dff5e67a3c81c71c58297874a4c310c654609",
      "bundleSha256": "87e366409b469a146b6aaecd46805f24c95e761eb0788d77ecb8e7615231a5ae",
      "pass": true
    }
  },
  "renditions": {
    "16:9": {
      "poster": "https://cdn.21st.dev/video-previews/split-flap-type/16x9/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/split-flap-type/16x9/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/split-flap-type/16x9/detail.mp4",
      "bg": "#171b21",
      "posterFrame": 135,
      "size": [
        1920,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "10eb80ec4f5f6c525ea57c55d2540cb6c6712dadf63b1d17da90e4a7ca2bb000",
        "loop": "274645f669bb526d8132fa13c91e2634a576708fcf00503b2f0a8de5e4a7cc68",
        "detail": "6c26759c11dec029454824d4432bcfa69ea90b34fa9c6a08dc22854be0aa34d4"
      }
    },
    "9:16": {
      "poster": "https://cdn.21st.dev/video-previews/split-flap-type/9x16/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/split-flap-type/9x16/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/split-flap-type/9x16/detail.mp4",
      "bg": "#171b21",
      "posterFrame": 135,
      "size": [
        1080,
        1920
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "8589e7810041322b7e075dbfefb0cc65ec74592bf54601d829b97818d9f1096b",
        "loop": "5c35a7d6bc67b0aa3808b0632e89f605a494af096741c844683ef08ab4ea02c3",
        "detail": "d560cd5313bc6f0e50838ce15dd46b6c6686812740c8d1e2922fcfa61027fb1f"
      }
    },
    "1:1": {
      "poster": "https://cdn.21st.dev/video-previews/split-flap-type/1x1/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/split-flap-type/1x1/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/split-flap-type/1x1/detail.mp4",
      "bg": "#171b21",
      "posterFrame": 135,
      "size": [
        1080,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "68200ab7112b77ebda577111c4c99401c730eddd1716bd151bde83256bb1e968",
        "loop": "ab5beb3a8496b8eacd20ee9fe109aaee46fdf574ca04ba24f2f84f5b194884ba",
        "detail": "02fdea4e1098d0b6f7c1c174a8c197edd2ff3186f72dbb456f70a4353a246d02"
      }
    }
  },
  "bundle": {
    "url": "https://cdn.21st.dev/video-bundles/87e366409b469a146b6aaecd46805f24c95e761eb0788d77ecb8e7615231a5ae/index.mjs",
    "sha256": "87e366409b469a146b6aaecd46805f24c95e761eb0788d77ecb8e7615231a5ae",
    "bytes": 161097,
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
    "at": "2026-10-09T20:37:55.404Z",
    "kit": "0.1.0",
    "licenseKeyPresent": false
  }
};
