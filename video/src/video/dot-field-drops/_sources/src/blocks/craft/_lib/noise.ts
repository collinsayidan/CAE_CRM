// Built with Remotion - https://remotion.pro/license
// Deterministic noise and randomness for craft blocks. Same seed, same frame,
// same pixels on every render worker.

/** Mulberry32: small seeded PRNG. `rng(seed)()` returns 0..1. */
export function rng(seed: number | string): () => number {
  let a = typeof seed === "number" ? seed >>> 0 : hashString(seed);
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
  return h;
}

const GRAD3 = [[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]] as const;

/** Seeded 3D simplex noise, range about -1..1. Use time as the third axis for smooth motion. */
export function simplex3(seed: number | string = 1) {
  const r = rng(seed);
  const p = new Uint8Array(512);
  const base = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [base[i], base[j]] = [base[j]!, base[i]!]; }
  for (let i = 0; i < 512; i++) p[i] = base[i & 255]!;
  const F3 = 1 / 3, G3 = 1 / 6;
  return (x: number, y: number, z: number): number => {
    const s = (x + y + z) * F3;
    const i = Math.floor(x + s), j = Math.floor(y + s), k = Math.floor(z + s);
    const t = (i + j + k) * G3;
    const x0 = x - (i - t), y0 = y - (j - t), z0 = z - (k - t);
    let i1, j1, k1, i2, j2, k2;
    if (x0 >= y0) {
      if (y0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
      else if (x0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 0; k2 = 1; }
      else { i1 = 0; j1 = 0; k1 = 1; i2 = 1; j2 = 0; k2 = 1; }
    } else {
      if (y0 < z0) { i1 = 0; j1 = 0; k1 = 1; i2 = 0; j2 = 1; k2 = 1; }
      else if (x0 < z0) { i1 = 0; j1 = 1; k1 = 0; i2 = 0; j2 = 1; k2 = 1; }
      else { i1 = 0; j1 = 1; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
    }
    const pts = [[x0, y0, z0, 0, 0, 0], [x0 - i1 + G3, y0 - j1 + G3, z0 - k1 + G3, i1, j1, k1], [x0 - i2 + 2 * G3, y0 - j2 + 2 * G3, z0 - k2 + 2 * G3, i2, j2, k2], [x0 - 1 + 3 * G3, y0 - 1 + 3 * G3, z0 - 1 + 3 * G3, 1, 1, 1]] as const;
    let n = 0;
    for (const [dx, dy, dz, a, b, c] of pts) {
      let tt = 0.6 - dx * dx - dy * dy - dz * dz;
      if (tt < 0) continue;
      const g = GRAD3[p[(i + a + p[(j + b + p[(k + c) & 255]!) & 255]!) & 255]! % 12]!;
      tt *= tt;
      n += tt * tt * (g[0] * dx + g[1] * dy + g[2] * dz);
    }
    return 32 * n;
  };
}

/** Fractal sum of simplex octaves. */
export function fbm3(noise: (x: number, y: number, z: number) => number, x: number, y: number, z: number, octaves = 4): number {
  let sum = 0, amp = 0.5, f = 1;
  for (let o = 0; o < octaves; o++) { sum += amp * noise(x * f, y * f, z * f); f *= 2; amp *= 0.5; }
  return sum;
}

/** Loop-safe time: a point on a circle, so noise(x, y, cos, sin) style sampling closes the loop. */
export function loopCircle(frame: number, duration: number, radius = 1): [number, number] {
  const a = (frame / duration) * Math.PI * 2;
  return [Math.cos(a) * radius, Math.sin(a) * radius];
}
