# CAE CRM videos

Walkthrough and ad videos for CAE CRM, built with [Remotion](https://www.remotion.dev) from real screens of the app.

| Video | Composition | Size |
|---|---|---|
| 60-second walkthrough | `Walkthrough60` | 1920×1080 |
| 30-second walkthrough | `Walkthrough30` | 1920×1080 |
| 15-second phone ad | `Ad15Vertical` | 1080×1920 |

## How it's made

1. **Filming copy.** `run_film.py` (kept with the session scratch files) starts CAE CRM on a throwaway SQLite file
   with the sample businesses and a test admin, "Alex Morgan". It never touches the live database. The demo
   workspace can't be used, because it blocks sending quotes.
2. **Capture.** `capture/capture.mjs` signs in, walks the story (web form, deal move, quote signed, invoice paid,
   new ticket) and saves 2× screenshots plus the position of each thing the video points at, in
   `public/shots/boxes.json`. It refuses to run against anything but localhost.
3. **Music.** `music/compose.py` writes an original instrumental bed in three lengths. It's composed in code, so
   there is no licence to clear. It can be swapped for any licensed track in `public/music/`.
4. **Edit.** `src/` holds the scenes: camera moves, cursor, highlights, captions, and the brand and end cards in the
   app's own colours and font (Plus Jakarta Sans, SIL Open Font Licence, `public/fonts/OFL.txt`).

## Commands

```bash
npm install
FILM_LOGIN=<path to film-login.txt> node capture/capture.mjs
python music/compose.py
npx remotion studio src/index.ts
npx remotion render src/index.ts Walkthrough60 out/cae-crm-walkthrough-60s.mp4 --codec=h264 --crf=18
```

## Rules for anything shown

- Made-up businesses only, and a "Sample data" tag on every app screen.
- Only claims the homepage already makes, at the live price.
- No customer quotes, ratings or logos until there are real ones with permission.

## 21st.dev Video blocks

Four blocks from 21st.dev live in `src/video/` and are set up in brand colours in `src/Blocks21.tsx`:

- Split Flap Headline (`split-flap-type`): opening title in both walkthroughs.
- Tiled Screenshot Reveal (`puzzle-grid-reveal`): the dashboard reveal in the 60s walkthrough.
- Dot Field Ripples (`dot-field-drops`): background behind the 15s ad's opening line.
- Spinning Seal Invitation (`rotating-seal-badge`): end card in all three videos.

Each block's `_sources/src/kit/brand-fonts.ts` has an added loader for Plus Jakarta Sans. The blocks need `zod@3` and `@remotion/google-fonts` (installed).

To fetch a block again, download its registry JSON with your own 21st API key into `21st-blocks/` (git-ignored). The JSON embeds the key, so strip it before sharing.

Licence: 21st says the blocks are "Built with Remotion". Rendering commercially may need a Remotion company licence (see https://remotion.pro/license).
