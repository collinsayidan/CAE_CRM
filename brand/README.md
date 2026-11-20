# CAE CRM brand

The CAE CRM logo is **Stages**: two nested "C"s closing on a point, a sales pipeline narrowing to a won deal. The original logo artwork is kept in this folder and in `cae-crm/static/brand/`.

## Company colours

The CRM interface follows the parent company website, [Collinalitics](https://www.collinalitics.co.uk/), whose design tokens are defined in `collinalitics-official-website/app/globals.css`.

| Colour | Hex | Interface use |
| --- | --- | --- |
| Navy | `#0E2240` | Sidebar, dark panels and sign-in backdrop |
| Teal | `#0B7E7C` | Primary buttons, charts and accents |
| Dark teal | `#0A716F` | Readable links and text on light or tinted surfaces |
| Cyan | `#19CECA` | Highlights and focus indicators on dark backgrounds |
| White | `#FFFFFF` | Light-mode cards and panels |
| Light background | `#F5F7FA` | Light-mode workspace canvas |
| Ink | `#0D1B2E` | Main text on light surfaces |

The shared palette lives in `cae-crm/static/brand.css`, loaded after the base styles. Dark mode uses navy surfaces and lighter teal/cyan text. Bright cyan is not suitable for normal text on white. Keep normal text at a contrast ratio of at least 4.5:1. Status indicators retain green, amber and red, with text labels.

The original coral logo remains an individual product mark; its colours do not define the interface palette.

## Logo files

| File | Use |
| --- | --- |
| `cae-crm-icon.svg` | App icon on its original tile |
| `cae-crm-mark.svg` | Mark on light backgrounds |
| `cae-crm-mark-on-dark.svg` | Mark on dark backgrounds |
| `cae-crm-logo.svg` | Full logo on light backgrounds |
| `cae-crm-logo-on-dark.svg` | Full logo on dark backgrounds |
| `favicon.ico` | Browser tab icon |
| `png/` | PNG exports of the marks and logos |

The full logos use Plus Jakarta Sans with letters converted to paths. Leave clear space around the logo, preserve its proportions and use the icon alone below 24px.
