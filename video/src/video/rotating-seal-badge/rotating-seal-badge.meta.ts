// Built with Remotion - https://remotion.pro/license
export const meta = {
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
      "key": "logo",
      "type": "image",
      "role": "logo"
    },
    {
      "key": "text",
      "type": "text",
      "maxChars": 64,
      "lines": 1,
      "role": "eyebrow"
    },
    {
      "key": "action",
      "type": "text",
      "maxChars": 24,
      "lines": 2,
      "role": "cta"
    },
    {
      "key": "destination",
      "type": "text",
      "maxChars": 32,
      "lines": 2,
      "role": "subline"
    }
  ],
  "brand": {
    "primary": "colors.primary",
    "secondary": "colors.secondary",
    "color": "colors.text",
    "background": "colors.background",
    "fontFamily": "fonts.display"
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
    "sourceUrl": "21st first-party (a ring of typography brakes and stamps around a logo and action invitation, 2026-10-09)"
  },
  "defaults": {
    "logo": "",
    "text": "MADE TO MOVE · READY TO MAKE ·",
    "action": "Explore more",
    "destination": "Your next chapter",
    "primary": "#A3E635",
    "secondary": "#22D3EE",
    "color": "#F9FAFB",
    "background": "#111827",
    "fontFamily": "DM Sans"
  },
  "fields": [
    {
      "key": "logo",
      "label": "Logo",
      "type": "asset",
      "role": "logo"
    },
    {
      "key": "text",
      "label": "Text",
      "type": "text",
      "max": 64,
      "role": "eyebrow"
    },
    {
      "key": "action",
      "label": "Action",
      "type": "text",
      "max": 24,
      "role": "cta"
    },
    {
      "key": "destination",
      "label": "Destination",
      "type": "text",
      "max": 32,
      "role": "subline"
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
      "brand": "fonts.display"
    }
  ],
  "name": "Spinning Seal Invitation",
  "catalogGates": {
    "schema": "21st.video-catalog-gates/2",
    "ref": "rotating-seal-badge",
    "bundleSha256": "5240fd58d0d48d059303fa3e91e69b018da50745e4e84682252998be2889668a",
    "sourceSnapshot": {
      "sha256": "be113857ae041533797b125ad6f1737614716f34c43f0c6f645addc012f77824",
      "files": 1926
    },
    "renderedAt": "2026-10-09T19:01:25.090Z",
    "samples": [
      {
        "aspect": "16:9",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-paper.png",
        "sha256": "6fdf75a2eb71d2c45037baf98ad02ad7f823a7446e31fd638a8252fc20ee6cab"
      },
      {
        "aspect": "16:9",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-night.png",
        "sha256": "3515c4509989294d6788ce12ed37d7f84fc3425113b7dfc641140944a8f755ad"
      },
      {
        "aspect": "16:9",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-color.png",
        "sha256": "018f3e877bb910123639dbc5c8bec5c861140fdbdfef8087bc3e44b428294c47"
      },
      {
        "aspect": "9:16",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-paper.png",
        "sha256": "674de1d559dadc4dca693f0ecfdf4d5645a18431513ccdf9ab1af7efeefd16c3"
      },
      {
        "aspect": "9:16",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-night.png",
        "sha256": "b990fbbeb378dcfffc48799b4b597b7a06b6d11d958478a1d7f5962419eee1db"
      },
      {
        "aspect": "9:16",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-color.png",
        "sha256": "8060ef40d12fa5dad00eab3d1edf8d8a39a174e3f381a3308d933193a86dae13"
      },
      {
        "aspect": "1:1",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-paper.png",
        "sha256": "23b7f64d8829a582875ccdda7d701865aa364d963f7e3c659137784a256649b5"
      },
      {
        "aspect": "1:1",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-night.png",
        "sha256": "d46a352b50d8ce07ea957acfc8e093bb4789ecb67a217f561a7b2f0ccc9a36ba"
      },
      {
        "aspect": "1:1",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-color.png",
        "sha256": "7ba87b1dbb88d7cbd2a55f5e65ad8ac19c00a391bacf79057690996ca7c169de"
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
          "rotating-seal-badge--16x9",
          "rotating-seal-badge--9x16",
          "rotating-seal-badge--1x1"
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
            "paperNight": 39.867160373263886,
            "paperColor": 32.708984375,
            "region": {
              "left": 562,
              "top": 67,
              "width": 796,
              "height": 896
            },
            "canvas": {
              "width": 1920,
              "height": 1080
            }
          },
          {
            "aspect": "9:16",
            "pass": true,
            "paperNight": 38.513156467013886,
            "paperColor": 28.10888671875,
            "region": {
              "left": 117,
              "top": 384,
              "width": 846,
              "height": 1255
            },
            "canvas": {
              "width": 1080,
              "height": 1920
            }
          },
          {
            "aspect": "1:1",
            "pass": true,
            "paperNight": 39.86626519097222,
            "paperColor": 32.702853732638886,
            "region": {
              "left": 142,
              "top": 67,
              "width": 796,
              "height": 896
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
            "occupancy": 0.4874583578287283,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "16:9",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.4863702811371463,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "16:9",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.48256201271660937,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "9:16",
            "brand": "paper",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.7256555689405393,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "9:16",
            "brand": "night",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.7227645108969515,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "9:16",
            "brand": "color",
            "pass": true,
            "minFont": 57.599999999999994,
            "occupancy": 0.7152477599836232,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "1:1",
            "brand": "paper",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.8665926361399614,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "1:1",
            "brand": "night",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.864658277577149,
            "bad": [],
            "measured": 3
          },
          {
            "aspect": "1:1",
            "brand": "color",
            "pass": true,
            "minFont": 19.439999999999998,
            "occupancy": 0.8578880226073056,
            "bad": [],
            "measured": 3
          }
        ]
      },
      "motion": {
        "pass": true,
        "averageChannelDifference": 9.822916666666666,
        "frames": [
          18,
          120,
          179
        ],
        "elastic": [
          {
            "aspect": "16:9",
            "duration": 140,
            "averageChannelDifference": 9.997612847222221,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 16,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-140-frame-16.png",
                "sha256": "b9916035284f5836a8080521636b54c7fe16cd49aa247833642d8910d206d551",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-140-frame-120.png",
                "sha256": "c61530bc3df5f06900b67cda09bb12b36ddca03203f389af8d2b7f00221584b5",
                "alphaMass": 587520
              },
              {
                "frame": 123,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-140-frame-123.png",
                "sha256": "c27d9d100ee8dd112468ee71553d47cdde1cf898373924daa4c48d56dc4c8dc7",
                "alphaMass": 587520
              },
              {
                "frame": 139,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-140-frame-139.png",
                "sha256": "c95882cdc4a183967bd1a6a8413a984ab45bf09939696f314fdbe89955e73259",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "16:9",
            "duration": 600,
            "averageChannelDifference": 9.82302517361111,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-600-frame-18.png",
                "sha256": "b7b8cfc72d70fcd1e03fd6dd47a9c54fc8cb62b73fb7e9b6b5e299e7f2db9b65",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-600-frame-120.png",
                "sha256": "c61530bc3df5f06900b67cda09bb12b36ddca03203f389af8d2b7f00221584b5",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-600-frame-528.png",
                "sha256": "7bea950eae6b05f4f4c70bcc39fd2d018b232e694835b4fe21170e7aa7daab99",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/16x9-duration-600-frame-599.png",
                "sha256": "7bea950eae6b05f4f4c70bcc39fd2d018b232e694835b4fe21170e7aa7daab99",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 140,
            "averageChannelDifference": 14.14431423611111,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 16,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-140-frame-16.png",
                "sha256": "e91adef7620e61eac02163e60a6f4415a2bc9a9db20f7ef9f4b52ce4db380444",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-140-frame-120.png",
                "sha256": "9663b185ed508786e53de36e8b64de01c5c1dac69ca45b8a04236152f16553e1",
                "alphaMass": 587520
              },
              {
                "frame": 123,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-140-frame-123.png",
                "sha256": "2e37726f9c16017174c95e1a9232c3e0e46e10a0b8b3b41590c230bd7a2cb1da",
                "alphaMass": 587520
              },
              {
                "frame": 139,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-140-frame-139.png",
                "sha256": "153dfeff0a70011ac45b4adb0739c7826b6070722f55e7023f2aaeb3b01134dd",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 600,
            "averageChannelDifference": 13.947265625,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-600-frame-18.png",
                "sha256": "e8f428b808864234f49a26482edc691ed80c3ed0a2bcdc16ee6da29356731bcc",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-600-frame-120.png",
                "sha256": "9663b185ed508786e53de36e8b64de01c5c1dac69ca45b8a04236152f16553e1",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-600-frame-528.png",
                "sha256": "416aa9c9542d2fef3d5acd56959dbd57ab2963f574616a6dd430b657e710219c",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/9x16-duration-600-frame-599.png",
                "sha256": "416aa9c9542d2fef3d5acd56959dbd57ab2963f574616a6dd430b657e710219c",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 140,
            "averageChannelDifference": 15.428819444444445,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 16,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-140-frame-16.png",
                "sha256": "2a121a340038b298c8a155922b9170aeb3eb2a21b5c7575ae7eb6cd3f5fd56b1",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-140-frame-120.png",
                "sha256": "fc48bcd2b78ac4265a685ac3e61820dc7160ee407b4e660fa2cd9f2205be22b2",
                "alphaMass": 587520
              },
              {
                "frame": 123,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-140-frame-123.png",
                "sha256": "47434910778302340bd0b0c81ddc8ff2fc55c9952c585aae722423c8531a7a37",
                "alphaMass": 587520
              },
              {
                "frame": 139,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-140-frame-139.png",
                "sha256": "2210ab6fad4a60bf745c8d3056fc75587e29ba3ed258831dcbf7d03aacd40f01",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 600,
            "averageChannelDifference": 15.220703125,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-600-frame-18.png",
                "sha256": "06ba94788cfb3a5c4166b522ce55cc41a16435ad4bd2cbbc19167c43f547ff39",
                "alphaMass": 587520
              },
              {
                "frame": 120,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-600-frame-120.png",
                "sha256": "fc48bcd2b78ac4265a685ac3e61820dc7160ee407b4e660fa2cd9f2205be22b2",
                "alphaMass": 587520
              },
              {
                "frame": 528,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-600-frame-528.png",
                "sha256": "d392278b35b75bc5cd25fa50dadd7f90f088ce0b50724ce3c9cdf24fe370b5f8",
                "alphaMass": 587520
              },
              {
                "frame": 599,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/creative/resume-20261009T183430Z/gates/rotating-seal-badge/1x1-duration-600-frame-599.png",
                "sha256": "d392278b35b75bc5cd25fa50dadd7f90f088ce0b50724ce3c9cdf24fe370b5f8",
                "alphaMass": 587520
              }
            ]
          }
        ],
        "note": "Measured motion and final alpha retention at min/max in all three formats; sampled frames do not certify full playback."
      },
      "semantic": {
        "pass": true,
        "recognizedJob": "cta",
        "titleMatches": true,
        "noBakedHeading": true,
        "brandAdherence": true,
        "languageAdherence": true,
        "note": "1. TitleMatches: The visible subject is a central seal with bold, oversized type reading 'MADE TO MOVE · READY TO MAKE ·' in a circular arrangement, implying a seal or badge. The chronological samples (images 2-4) show the seal rotating and elements assembling/replacing, clearly evoking the idea of a 'spinning seal.' This direct, motion-centric presentation supports the claimed \"Spinning Seal Invitation\" title.\n\n2. noBakedHeading: There is no decorative category, block-title, or language label visually baked into the design—only editable content ('Explore more', 'Your next chapter') and the seal's circular messaging, which is part of the graphic and not a category label or unrelated heading.\n\n3. BrandAdherence: Images 5-7 display the poster across three distinct palettes matching the supplied hex codes (light/cream with green/black, dark/purple, green/blue). The seal's form, text, and interactive button remain fully legible and consistently shaped; only colors and contrast shift according to palette, without unexplained fixed block colors. Shape consistency and material clarity are preserved across rebrands.\n\n4. LanguageAdherence: All palettes and motion samples retain oversized type, bold letterforms, cut graphic shapes, and a clear hierarchy fitting the supplied language card description. The motion samples show type/mask-based movement as noted in the language ('type and masks carry the movement', verbs like assemble, replace, slide), and there are no indications of forbidden motifs (no frosted glass, browser chrome, or floating ambient cards). The numerals and body type maintain the sans, tabular, and accent roles as described, including in color and placement."
      },
      "duplicates": {
        "pass": true,
        "threshold": 0.97,
        "required": 7,
        "compared": 7,
        "matches": []
      }
    },
    "pass": true,
    "humanSelection": {
      "selected": true,
      "bundleSha256": "5240fd58d0d48d059303fa3e91e69b018da50745e4e84682252998be2889668a",
      "selectedBy": "Owner-authorized continuation, executed by Codex",
      "at": "2026-10-09T19:04:23.069Z",
      "basis": "Resumed the owner's request to publish craft blocks that pass catalog gates and the blind creativity jury"
    },
    "creativityReview": {
      "ref": "rotating-seal-badge",
      "vsPositive": 0.7083333333333334,
      "vsNegative": 0.9583333333333334,
      "fakeVotes": 0.125,
      "perModel": {
        "claude": {
          "vsPositive": 0.75,
          "vsNegative": 1
        },
        "gpt": {
          "vsPositive": 0.75,
          "vsNegative": 0.875
        },
        "gemini": {
          "vsPositive": 0.625,
          "vsNegative": 1
        }
      },
      "errors": 0,
      "calls": 48,
      "complete": true,
      "framesSha256": "1a00d261fe0f88b9d3bb44d04225e7ca741ef4ddeb25f55ac56776cf7fa6ce68",
      "bundleSha256": "5240fd58d0d48d059303fa3e91e69b018da50745e4e84682252998be2889668a",
      "pass": true
    }
  },
  "renditions": {
    "16:9": {
      "poster": "https://cdn.21st.dev/video-previews/rotating-seal-badge/16x9/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/rotating-seal-badge/16x9/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/rotating-seal-badge/16x9/detail.mp4",
      "bg": "#111827",
      "posterFrame": 120,
      "size": [
        1920,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "f9612b67e0a4ff1bd743a928427bd98dedc609482d3492d1325c43a6ef568af0",
        "loop": "bb766e35f63e0728ba40949d95cd72ae25dc86302284cdcf4f25ac4b29f3ad2e",
        "detail": "4e6ced05691e56e5952b6b604593fc134817b812e40fb08f5766bc7f8d5b5710"
      }
    },
    "9:16": {
      "poster": "https://cdn.21st.dev/video-previews/rotating-seal-badge/9x16/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/rotating-seal-badge/9x16/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/rotating-seal-badge/9x16/detail.mp4",
      "bg": "#111827",
      "posterFrame": 120,
      "size": [
        1080,
        1920
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "4c5a0ae47d2845431211341c6ade837af3ecc258eaf211fbbc6a9116eedaf892",
        "loop": "0ac8ffb9ae117376192eb796a0a5c7cbe268934c4eed6044c5a0e46f6003d717",
        "detail": "4623475c190eb9d1e34d282dc50cfe513bb379e2dc67def8799fb8607380f361"
      }
    },
    "1:1": {
      "poster": "https://cdn.21st.dev/video-previews/rotating-seal-badge/1x1/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/rotating-seal-badge/1x1/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/rotating-seal-badge/1x1/detail.mp4",
      "bg": "#111827",
      "posterFrame": 120,
      "size": [
        1080,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "fe9b6d815c7629c95b037acf851cf06127be0df2521326e69d5facb92389752d",
        "loop": "4ec765175e5fe834599c3d61eb8300c56eec6a2dd15f6b3550fcbba219e0163c",
        "detail": "13b88409da648bdf4433ed56a4ed98e286cba0e30d84e5aa5f1e74e299de1f1b"
      }
    }
  },
  "bundle": {
    "url": "https://cdn.21st.dev/video-bundles/5240fd58d0d48d059303fa3e91e69b018da50745e4e84682252998be2889668a/index.mjs",
    "sha256": "5240fd58d0d48d059303fa3e91e69b018da50745e4e84682252998be2889668a",
    "bytes": 161611,
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
    "at": "2026-10-09T19:28:34.910Z",
    "kit": "0.1.0",
    "licenseKeyPresent": false
  }
};
