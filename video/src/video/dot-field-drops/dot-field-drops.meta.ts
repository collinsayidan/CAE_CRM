// Built with Remotion - https://remotion.pro/license
export const meta = {
  "spec": "21st.video/1",
  "kind": "background",
  "category": "backgrounds/craft",
  "job": "backgrounds",
  "language": "aura",
  "mechanic": [
    "ripple"
  ],
  "energy": "calm",
  "tags": [
    "background",
    "dots",
    "dot grid",
    "ripple",
    "waves",
    "interference",
    "rhythm",
    "beat",
    "drops",
    "water",
    "perspective",
    "headline",
    "ambient",
    "glow"
  ],
  "engines": {
    "remotion": ">=4.0.479 <5"
  },
  "timing": {
    "fps": 30,
    "duration": {
      "default": 180,
      "min": 150,
      "max": 1800
    },
    "stretch": "hold",
    "phases": {
      "in": 140,
      "out": 0
    },
    "markers": {
      "settled": 140,
      "wake": 0,
      "first": 14,
      "build": 50,
      "last": 108,
      "headline": 112
    },
    "beats": [
      14,
      32,
      50,
      68,
      86,
      108,
      140
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
      "key": "headline",
      "type": "text",
      "maxChars": 60,
      "lines": 2,
      "role": "headline"
    }
  ],
  "brand": {
    "color": "colors.text",
    "primary": "colors.primary",
    "secondary": "colors.secondary",
    "background": "colors.background",
    "fontFamily": "fonts.heading"
  },
  "motionBeats": [
    {
      "target": "field",
      "prop": "opacity",
      "from": "0",
      "settledBy": 14,
      "easing": "ease"
    },
    {
      "target": "drops",
      "prop": "ripple",
      "from": "calm",
      "settledBy": 108,
      "easing": "linear"
    },
    {
      "target": "headline",
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
    "sourceUrl": "21st first-party (drops land on the beat in a perspective dot field and their ripples interfere, 2026-10-08)"
  },
  "defaults": {
    "headline": "",
    "color": "#3D2C2E",
    "primary": "#E76F51",
    "secondary": "#2A9D8F",
    "background": "#FFF1E6",
    "fontFamily": "Bricolage Grotesque",
    "seed": 12,
    "spacing": 1,
    "grain": true
  },
  "fields": [
    {
      "key": "headline",
      "label": "Headline",
      "type": "text",
      "max": 60,
      "role": "headline"
    },
    {
      "key": "color",
      "label": "Color",
      "type": "color",
      "brand": "colors.text"
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
      "max": 999
    },
    {
      "key": "spacing",
      "label": "Spacing",
      "type": "number",
      "min": 0.7,
      "max": 1.5
    },
    {
      "key": "grain",
      "label": "Grain",
      "type": "boolean"
    }
  ],
  "name": "Dot Field Ripples",
  "catalogGates": {
    "schema": "21st.video-catalog-gates/2",
    "ref": "dot-field-drops",
    "bundleSha256": "2d17bb5ce16dbc44d0baf262396dcd6cb452486e0d2540a736ced13b8b02f2e5",
    "sourceSnapshot": {
      "sha256": "3912a1c1847b30436039691f198cd5d8e660dd1089f4139805bc21ce78e20cf0",
      "files": 1860
    },
    "renderedAt": "2026-10-09T13:21:03.221Z",
    "samples": [
      {
        "aspect": "16:9",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-paper.png",
        "sha256": "940048deff3e27668597a7f51d2113dcc0c19c274d80fd9795fd12dee95ff986"
      },
      {
        "aspect": "16:9",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-night.png",
        "sha256": "92f5ae56968aab191089ac57108b8620022bf83e558260087a3da544dd96ae4c"
      },
      {
        "aspect": "16:9",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-color.png",
        "sha256": "8c1f9b834531f2f966ff763731c22ecae9dfbd1a584c96ef7d207bcf6ed3e3b1"
      },
      {
        "aspect": "9:16",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-paper.png",
        "sha256": "41d8b449c94c76daefb3de7f3e7c0dcb0b305ebaf346ff0c7f4ad598e80c3eb2"
      },
      {
        "aspect": "9:16",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-night.png",
        "sha256": "8019cce187150b4bc95a6100a29dfa8df14ad571162e57f1c89b5ac2482d9f98"
      },
      {
        "aspect": "9:16",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-color.png",
        "sha256": "fecb71ed9816472155ca0db078c5fc5aca242c32f2e5b4fe4b8c794e54567e7a"
      },
      {
        "aspect": "1:1",
        "brand": "paper",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-paper.png",
        "sha256": "90610ced2407bd0be10ab13ae61070a35a6b6830cf7753963433c003282dae53"
      },
      {
        "aspect": "1:1",
        "brand": "night",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-night.png",
        "sha256": "b1848eaa52de7bfc44abfaa693cd59542c16317c9e707ff84ccae4105426a90f"
      },
      {
        "aspect": "1:1",
        "brand": "color",
        "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-color.png",
        "sha256": "18c535e519b5a386923b707084bc7695514c8e62673a192b99b8f7c308a7b672"
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
          "dot-field-drops--16x9",
          "dot-field-drops--9x16",
          "dot-field-drops--1x1"
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
            "paperNight": 25.21706814236111,
            "paperColor": 17.84738498263889,
            "region": {
              "left": 62,
              "top": 33,
              "width": 1800,
              "height": 1022
            },
            "canvas": {
              "width": 1920,
              "height": 1080
            }
          },
          {
            "aspect": "9:16",
            "pass": true,
            "paperNight": 27.902506510416668,
            "paperColor": 18.589219835069443,
            "region": {
              "left": 28,
              "top": 67,
              "width": 1028,
              "height": 1790
            },
            "canvas": {
              "width": 1080,
              "height": 1920
            }
          },
          {
            "aspect": "1:1",
            "pass": true,
            "paperNight": 27.495442708333332,
            "paperColor": 19.310384114583332,
            "region": {
              "left": 25,
              "top": 39,
              "width": 1030,
              "height": 1017
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
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "16:9",
            "brand": "night",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "16:9",
            "brand": "color",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "9:16",
            "brand": "paper",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "9:16",
            "brand": "night",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "9:16",
            "brand": "color",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "1:1",
            "brand": "paper",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "1:1",
            "brand": "night",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          },
          {
            "aspect": "1:1",
            "brand": "color",
            "pass": true,
            "errors": [
              "No measured content slots"
            ],
            "pending": true,
            "note": "Non-text block"
          }
        ]
      },
      "motion": {
        "pass": true,
        "averageChannelDifference": 13.420789930555555,
        "frames": [
          21,
          140,
          179
        ],
        "elastic": [
          {
            "aspect": "16:9",
            "duration": 150,
            "averageChannelDifference": 13.98752170138889,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-150-frame-18.png",
                "sha256": "a75dacd61d944398420c5424edd8f8584f2cd46fedba13e7bf27e7f11dc397f1",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-150-frame-140.png",
                "sha256": "0d97f20f57012f8ed38a8e5ddf46b88909a760d5e3b99c58f759b052b954da4c",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-150-frame-132.png",
                "sha256": "201eaa632d4c7f4c1c6b5ec1b0dab699df388ce59b33fc02e09068b41a5b0fac",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-150-frame-149.png",
                "sha256": "71be21d1a3a1d59494b2b865d8ab0cdbebc6c3a193a0f4b39ad6fa7251340340",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "16:9",
            "duration": 1800,
            "averageChannelDifference": 13.420789930555555,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-1800-frame-21.png",
                "sha256": "016b8d528de7cf76b46d3a9e8b47c90900bad58a9910f1ddca08119a9a66a0ca",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-1800-frame-140.png",
                "sha256": "0d97f20f57012f8ed38a8e5ddf46b88909a760d5e3b99c58f759b052b954da4c",
                "alphaMass": 587520
              },
              {
                "frame": 1584,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-1800-frame-1584.png",
                "sha256": "625ce7c30801f7596714446911969bfdc94797180aa4d7ddae9f0d7004fc9c2e",
                "alphaMass": 587520
              },
              {
                "frame": 1799,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/16x9-duration-1800-frame-1799.png",
                "sha256": "d7b3762c4dca597c221f25c0e2f6fd92d5a7deabb4adb888bb5c08d7d3cde460",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 150,
            "averageChannelDifference": 13.986979166666666,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-150-frame-18.png",
                "sha256": "4839b3dd1cc59e018e67faa76a4864be7676c54a105bcab20e574ebfae04f3b1",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-150-frame-140.png",
                "sha256": "da688a6e808a2343ae45d01396ffe8b8118633fede0b20505c5677427c480045",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-150-frame-132.png",
                "sha256": "acf8dffbefa791b8ff509f3355d6b16299743448fb219005a4578d6b6c72a467",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-150-frame-149.png",
                "sha256": "fb4e4aaa6f3fe3ffcf7d0ce35c8363299c5bd088e2a4f3de28d51ac26126d878",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "9:16",
            "duration": 1800,
            "averageChannelDifference": 13.346788194444445,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-1800-frame-21.png",
                "sha256": "088b5ecbc9da1cccaf12467686affb6463286f3c1fe1b5cbd7d91014e7caaab8",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-1800-frame-140.png",
                "sha256": "da688a6e808a2343ae45d01396ffe8b8118633fede0b20505c5677427c480045",
                "alphaMass": 587520
              },
              {
                "frame": 1584,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-1800-frame-1584.png",
                "sha256": "f1669ea267477e06397b264586b81ac22c5ad2f26f4a27d5323f1dbe7b96973c",
                "alphaMass": 587520
              },
              {
                "frame": 1799,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/9x16-duration-1800-frame-1799.png",
                "sha256": "cce6c593932fc6ff3f2b3b2cf2bf0c392a3fc24e975e522420b398cf3f3d9307",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 150,
            "averageChannelDifference": 18.455186631944443,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 18,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-150-frame-18.png",
                "sha256": "51e652cbf51696cd09dbb49c25c35bad7a87550421937181bed2d49766e3c7bd",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-150-frame-140.png",
                "sha256": "eca00bed1cfb79b86f38432732d6f3a7175ef37406f0e84c9776221f5e67ad6a",
                "alphaMass": 587520
              },
              {
                "frame": 132,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-150-frame-132.png",
                "sha256": "283d0c5ad79b8e1cdec3cd63c42a1c065fd11d6b4b521331b3e338b2ec719828",
                "alphaMass": 587520
              },
              {
                "frame": 149,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-150-frame-149.png",
                "sha256": "0a468d8c89e562b5fb1caade638c087fff2a8642f82d3d7cdc139a79e8d485bf",
                "alphaMass": 587520
              }
            ]
          },
          {
            "aspect": "1:1",
            "duration": 1800,
            "averageChannelDifference": 17.805013020833332,
            "retainedAlpha": 1,
            "pass": true,
            "samples": [
              {
                "frame": 21,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-1800-frame-21.png",
                "sha256": "8c3077861f76437771e563232b29e39b365cb07c5f6aa7f6ab2b0424a4aa8728",
                "alphaMass": 587520
              },
              {
                "frame": 140,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-1800-frame-140.png",
                "sha256": "eca00bed1cfb79b86f38432732d6f3a7175ef37406f0e84c9776221f5e67ad6a",
                "alphaMass": 587520
              },
              {
                "frame": 1584,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-1800-frame-1584.png",
                "sha256": "87fb2639ebcfe2fd8d4d9ef16f561881a0db0c11bc473fa16aaa2f84b9d2b4ed",
                "alphaMass": 587520
              },
              {
                "frame": 1799,
                "file": "/Users/m1/craft/pub/packages/video-kit/out/catalog-gates-craft-20261009-151704/dot-field-drops/1x1-duration-1800-frame-1799.png",
                "sha256": "86dea6ede2fce382f9d0d5bf793464274ce6079242056f833aa4c7122b994425",
                "alphaMass": 587520
              }
            ]
          }
        ],
        "note": "Measured motion and final alpha retention at min/max in all three formats; sampled frames do not certify full playback."
      },
      "semantic": {
        "pass": true,
        "recognizedJob": "backgrounds",
        "titleMatches": true,
        "noBakedHeading": true,
        "brandAdherence": true,
        "languageAdherence": true,
        "note": "1. TitleMatches: The visible subject is a field of regularly spaced dots with concentric ripple patterns—visually matching the concept described by 'Dot Field Ripples'. The motion samples (2-4) show spatial movement and transformation of these ripples across the dot field, visually demonstrating a ripple effect as the spatial center shifts, alternating between wide and compact circles on different sections of the canvas. These are concrete visual matches for the claimed title. \n\n2. NoBakedHeading: No prominent title, label, or decorative block-heading is embedded in any poster or sampled frame. The images are purely visual, with no overlaid or fixed decorative headings. \n\n3. BrandAdherence: Images five through seven display the same poster design with clearly different color palettes aligning with the three supplied palettes (blue/aqua on white, green/blue on navy, violet/olive on very pale green). The dot field and ripple forms remain crystal clear and legible across all backgrounds, and the colors visibly shift to suit the palettes. Shape, gradient, and material are consistent, and there is no unexplained fixed-color block. \n\n4. LanguageAdherence: The continuous dot fields with soft-graded color ripples closely match the language card’s direction of 'continuous soft light fields around a sharp isolated subject'. Atmosphere in the backgrounds and aura around the ripple center support 'diffused atmospheric gradients' and the subject (ring center) is always legible and visually settled. Across each palette and throughout the motion frames, the compositional and material language stays consistent with the brand roles and visual directives described."
      },
      "duplicates": {
        "pass": true,
        "threshold": 0.97,
        "required": 15,
        "compared": 15,
        "matches": []
      }
    },
    "pass": true,
    "humanSelection": {
      "selected": true,
      "bundleSha256": "2d17bb5ce16dbc44d0baf262396dcd6cb452486e0d2540a736ced13b8b02f2e5",
      "selectedBy": "serafim (repo owner): publish every craft block that passes the gates and the creativity jury (2026-10-08)",
      "at": "2026-10-09T13:22:28.496Z",
      "basis": "Craft harness: passed the creativity jury against owner-liked anchors"
    }
  },
  "renditions": {
    "16:9": {
      "poster": "https://cdn.21st.dev/video-previews/dot-field-drops/16x9/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/dot-field-drops/16x9/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/dot-field-drops/16x9/detail.mp4",
      "bg": "#fdf0e4",
      "posterFrame": 140,
      "size": [
        1920,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "4709b6ca7a5b69a10cf19121b9c05d0093732fe226459e8e745e13a8aefbcafb",
        "loop": "7a64f7a9b624a51e19a56ab2d2dc1efeb72ac6c3ee2e6f670677fd873b09f12f",
        "detail": "512e87844991995f28d6a62155f8c0b8dab139007530f01e6591fbc551f7ce44"
      }
    },
    "9:16": {
      "poster": "https://cdn.21st.dev/video-previews/dot-field-drops/9x16/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/dot-field-drops/9x16/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/dot-field-drops/9x16/detail.mp4",
      "bg": "#fef0e5",
      "posterFrame": 140,
      "size": [
        1080,
        1920
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "a3303b506fbbf73590b98b55609faaf139813ba65208740a029923d727f211a9",
        "loop": "53ab254fabffeb07651674a5c954cb58380af120baf359346579d76484d21721",
        "detail": "60a5a510c5cfc3597167afbfeddfb18eaa94ed8d1eff4013bd8ff3fe409d09cf"
      }
    },
    "1:1": {
      "poster": "https://cdn.21st.dev/video-previews/dot-field-drops/1x1/poster.jpg",
      "loop": "https://cdn.21st.dev/video-previews/dot-field-drops/1x1/loop.mp4",
      "detail": "https://cdn.21st.dev/video-previews/dot-field-drops/1x1/detail.mp4",
      "bg": "#fef0e5",
      "posterFrame": 140,
      "size": [
        1080,
        1080
      ],
      "durationInFrames": 180,
      "sha256": {
        "poster": "59991e55430667cb016084c8ca12c989dce55cdedc0b7a75a64b8e6e259de984",
        "loop": "7b9d57a0d7ce5357abc44e081b1f6ac20333287ac1f58b054ebc472bf3b04fdc",
        "detail": "3f9351638868236bfdcab724f2f29f39d6eb0f4f5843e035a79e217f7bede939"
      }
    }
  },
  "bundle": {
    "url": "https://cdn.21st.dev/video-bundles/2d17bb5ce16dbc44d0baf262396dcd6cb452486e0d2540a736ced13b8b02f2e5/index.mjs",
    "sha256": "2d17bb5ce16dbc44d0baf262396dcd6cb452486e0d2540a736ced13b8b02f2e5",
    "bytes": 171095,
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
    "at": "2026-10-09T13:33:59.961Z",
    "kit": "0.1.0",
    "licenseKeyPresent": false
  }
};
