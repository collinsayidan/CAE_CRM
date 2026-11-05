// Builds the launch film's sound effects from scratch (no samples, so nothing to license).
// Run: node scripts/make-sfx.mjs   → writes WAVs to public/sfx/
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SR = 48000;
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "sfx");
mkdirSync(OUT, { recursive: true });

// Seeded noise, so every run gives the same sounds.
let seed = 1;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
const buf = s => [new Float32Array(Math.round(s * SR)), new Float32Array(Math.round(s * SR))];

// Chamberlin state-variable band-pass whose centre can move per sample.
const svf = () => { let lo = 0, bp = 0; return (x, fc, q = 0.7) => {
  const f = 2 * Math.sin(Math.PI * Math.min(fc, SR / 6) / SR); const hp = x - lo - q * bp; bp += f * hp; lo += f * bp; return { lo, bp, hp }; }; };

function save(name, [L, R], gain = 0.9) {
  let peak = 0; for (let i = 0; i < L.length; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  const g = peak ? gain / peak : 1, n = L.length, b = Buffer.alloc(44 + n * 4);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 4, 4); b.write("WAVEfmt ", 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
  b.writeUInt16LE(2, 22); b.writeUInt32LE(SR, 24); b.writeUInt32LE(SR * 4, 28); b.writeUInt16LE(4, 32); b.writeUInt16LE(16, 34);
  b.write("data", 36); b.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    // 2ms fade at each end so nothing clicks.
    const e = Math.min(1, i / 96, (n - 1 - i) / 96);
    b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, L[i] * g * e)) * 32767), 44 + i * 4);
    b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, R[i] * g * e)) * 32767), 46 + i * 4);
  }
  writeFileSync(join(OUT, `${name}.wav`), b); console.log(`sfx/${name}.wav  ${(n / SR).toFixed(2)}s`);
}

// Air moving past: band-passed noise sweeping up then down, panning left to right.
{ const s = 0.7, [L, R] = buf(s), fl = svf(), fr = svf();
  for (let i = 0; i < L.length; i++) { const t = i / L.length, env = Math.sin(Math.PI * Math.pow(t, 0.7)) ** 2;
    const fc = 300 + 2600 * Math.sin(Math.PI * t); const pan = t;
    L[i] = fl(rnd(), fc, 0.9).bp * env * (1 - pan * 0.6); R[i] = fr(rnd(), fc * 1.03, 0.9).bp * env * (0.4 + pan * 0.6); }
  save("whoosh", [L, R], 0.8); }

// A cinematic low hit: falling sub, a short crack on top, and a long dark tail.
{ const s = 2.4, [L, R] = buf(s), f1 = svf(), f2 = svf(); let ph = 0;
  for (let i = 0; i < L.length; i++) { const t = i / SR; ph += 2 * Math.PI * (38 + 34 * Math.exp(-t * 6)) / SR;
    const sub = Math.sin(ph) * Math.exp(-t * 1.6);
    const crack = f1(rnd(), 2200, 0.6).bp * Math.exp(-t * 40) * 0.8;
    const tail = f2(rnd(), 380, 1.2).lo * Math.exp(-t * 1.4) * 0.35;
    L[i] = sub + crack + tail; R[i] = sub + crack * 0.9 + tail * 1.1; }
  save("hit", [L, R], 0.95); }

// A rising swell into a moment: noise and a climbing tone that build, then stop dead.
{ const s = 2.2, [L, R] = buf(s), fl = svf(), fr = svf(); let ph = 0;
  for (let i = 0; i < L.length; i++) { const t = i / L.length; const env = Math.pow(t, 2.4);
    const fc = 250 + 5000 * Math.pow(t, 2); ph += 2 * Math.PI * (180 + 900 * Math.pow(t, 2)) / SR;
    const tone = (Math.sin(ph) + 0.4 * Math.sin(ph * 2.01)) * 0.25;
    L[i] = (fl(rnd(), fc, 0.8).bp + tone) * env; R[i] = (fr(rnd(), fc * 1.05, 0.8).bp + tone) * env; }
  save("riser", [L, R], 0.8); }

// A crisp UI click.
{ const s = 0.09, [L, R] = buf(s), f = svf();
  for (let i = 0; i < L.length; i++) { const t = i / SR;
    const v = f(rnd(), 4200, 0.5).bp * Math.exp(-t * 900) + Math.sin(2 * Math.PI * 1900 * t) * Math.exp(-t * 160) * 0.5;
    L[i] = v; R[i] = v; }
  save("click", [L, R], 0.7); }

// A soft pop for the chips that name what happened.
{ const s = 0.22, [L, R] = buf(s); let ph = 0;
  for (let i = 0; i < L.length; i++) { const t = i / SR; ph += 2 * Math.PI * (520 + 520 * (1 - Math.exp(-t * 40))) / SR;
    const v = Math.sin(ph) * Math.exp(-t * 26) * Math.min(1, t * 400); L[i] = v; R[i] = v; }
  save("pop", [L, R], 0.6); }

// A tiny tick, for each day on the calendar strip.
{ const s = 0.06, [L, R] = buf(s);
  for (let i = 0; i < L.length; i++) { const t = i / SR; const v = Math.sin(2 * Math.PI * 3100 * t) * Math.exp(-t * 140); L[i] = v; R[i] = v; }
  save("tick", [L, R], 0.5); }

// A card landing in its new column.
{ const s = 0.35, [L, R] = buf(s), f = svf(); let ph = 0;
  for (let i = 0; i < L.length; i++) { const t = i / SR; ph += 2 * Math.PI * (95 + 80 * Math.exp(-t * 30)) / SR;
    const v = Math.sin(ph) * Math.exp(-t * 14) + f(rnd(), 900, 0.7).bp * Math.exp(-t * 60) * 0.5; L[i] = v; R[i] = v; }
  save("thud", [L, R], 0.8); }

// A two-note "done" chime, bell-like: quote signed, invoice paid.
{ const s = 1.8, [L, R] = buf(s);
  const bell = (t, f0) => t < 0 ? 0 : [1, 2.76, 5.4].reduce((a, m, k) => a + Math.sin(2 * Math.PI * f0 * m * t) * Math.exp(-t * (2.2 + k * 3)) / (k + 1), 0) * Math.min(1, t * 600);
  for (let i = 0; i < L.length; i++) { const t = i / SR; const a = bell(t, 784), b = bell(t - 0.11, 1175);
    L[i] = a + b * 0.8; R[i] = a * 0.8 + b; }
  save("chime", [L, R], 0.6); }

// Sparkle as the logo catches the light.
{ const s = 2.4, [L, R] = buf(s); const parts = Array.from({ length: 14 }, (_, k) => ({ f: 2400 + k * 410 + rnd() * 120, at: Math.abs(rnd()) * 0.9, p: rnd() }));
  for (let i = 0; i < L.length; i++) { const t = i / SR; let l = 0, r = 0;
    for (const q of parts) { const u = t - q.at; if (u < 0) continue; const v = Math.sin(2 * Math.PI * q.f * u) * Math.exp(-u * 3) * Math.min(1, u * 40);
      l += v * (1 - q.p) / 2; r += v * (1 + q.p) / 2; }
    L[i] = l; R[i] = r; }
  save("shimmer", [L, R], 0.45); }
