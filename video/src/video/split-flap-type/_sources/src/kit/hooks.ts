// Built with Remotion - https://remotion.pro/license
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { Aspect, VideoMeta } from "./spec";

export type Layout = {
  width: number;
  height: number;
  /** 1% of the short side. Size everything in units so blocks reflow across aspects. */
  unit: number;
  aspect: Aspect;
  portrait: boolean;
};

export function useLayout(): Layout {
  const { width, height } = useVideoConfig();
  const ratio = width / height;
  const aspect: Aspect = ratio > 1.2 ? "16:9" : ratio < 0.83 ? "9:16" : "1:1";
  return { width, height, unit: Math.min(width, height) / 100, aspect, portrait: height > width };
}

export type ClipPhase = "in" | "hold" | "out";

/**
 * Where the current frame sits in the clip: entering, holding or leaving.
 * Duration comes from the parent <Sequence>, so blocks stretch with `hold`.
 * Phases shrink proportionally when the clip is shorter than in + out.
 */
export function useClipPhases(timing: Pick<VideoMeta["timing"], "phases">): {
  phase: ClipPhase;
  progress: number;
  frame: number;
  durationInFrames: number;
  /** Frame at which the "out" phase starts. */
  outStart: number;
} {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const total = timing.phases.in + timing.phases.out;
  const scale = total > durationInFrames ? durationInFrames / total : 1;
  const inLen = Math.floor(timing.phases.in * scale);
  const outLen = Math.floor(timing.phases.out * scale);
  const outStart = durationInFrames - outLen;
  if (frame < inLen) return { phase: "in", progress: frame / Math.max(1, inLen), frame, durationInFrames, outStart };
  if (frame >= outStart && outLen > 0)
    return { phase: "out", progress: (frame - outStart) / outLen, frame, durationInFrames, outStart };
  return { phase: "hold", progress: (frame - inLen) / Math.max(1, outStart - inLen), frame, durationInFrames, outStart };
}

/**
 * Largest font size (px) that fits `chars` characters into a box of
 * `boxW` x `boxH` over at most `lines` lines. `charEm` is the font's average
 * glyph width in em (Geist/Inter ~0.5-0.56 at 500-600 weight), `lineHeight` in em.
 * Blocks size text with this instead of overflow:hidden, so twice-as-long copy
 * shrinks instead of spilling out of the region (gate: text overflow).
 */
export function fitFontSize(opts: {
  chars: number;
  boxW: number;
  boxH: number;
  lines?: number;
  charEm?: number;
  lineHeight?: number;
  max: number;
  min?: number;
}): number {
  const { chars, boxW, boxH, lines = 1, charEm = 0.55, lineHeight = 1.1, max, min = 4 } = opts;
  const perLine = Math.max(1, Math.ceil(Math.max(1, chars) / lines));
  // Wrapping is never perfectly balanced: leave ~18% slack per line when wrapping.
  const slack = lines > 1 ? 1.18 : 1.02;
  const byWidth = boxW / (perLine * charEm * slack);
  const byHeight = boxH / (lines * lineHeight);
  return Math.max(min, Math.min(max, byWidth, byHeight));
}

/**
 * Enter/exit factors for a clip: `enter` 0->1 over the in phase (linear; shape
 * it with springs/eases), `exit` 0->1 over the out phase. Blocks combine them
 * so every element both arrives and leaves (gate: enter + exit).
 */
export function useEnterExit(timing: Pick<VideoMeta["timing"], "phases">): {
  frame: number;
  durationInFrames: number;
  outStart: number;
  exit: number;
} {
  const { frame, outStart, durationInFrames } = useClipPhases(timing);
  const exit = durationInFrames > outStart ? Math.max(0, Math.min(1, (frame - outStart) / (durationInFrames - outStart))) : 0;
  return { frame, durationInFrames, outStart, exit };
}
