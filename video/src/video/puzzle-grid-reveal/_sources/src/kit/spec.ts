// Built with Remotion - https://remotion.pro/license
import { z } from "zod";
import { videoJobSchema, videoLanguageSchema } from "./catalog-taxonomy";
export * from "./catalog-taxonomy";
export * from "./font-roles";

/**
 * `21st.video/1`: the manifest every video block ships next to its component
 * and zod schema. JSON-serializable on purpose: intake stores it in
 * `demos.video_meta`, the MCP returns it to agents, the AI planner reads it.
 */

export const ASPECTS = ["16:9", "9:16", "1:1"] as const;
export const aspectSchema = z.enum(ASPECTS);
export type Aspect = z.infer<typeof aspectSchema>;

export const KINDS = ["element", "scene", "background", "transition", "captions", "overlay-fx", "template"] as const;
export const kindSchema = z.enum(KINDS);
export type VideoKind = z.infer<typeof kindSchema>;

export const videoLookSchema = z.object({
  id: z.string().min(1).max(64), name: z.string().min(1).max(80),
  description: z.string().max(240).optional(), props: z.record(z.unknown()),
  aspects: z.array(aspectSchema).min(1).optional(), poster: z.string().optional(),
});
export type VideoLook = z.infer<typeof videoLookSchema>;

const region = z.object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() });

export const videoMetaSchema = z.object({
  spec: z.literal("21st.video/1"),
  kind: kindSchema,
  category: z.string(),
  job: videoJobSchema.optional(),
  language: videoLanguageSchema.optional(),
  mechanic: z.array(z.string().min(1)).optional(),
  looks: z.array(videoLookSchema).max(4).optional(),
  energy: z.enum(["calm", "default", "punchy"]).optional(),
  requiresScreenshot: z.boolean().optional(),
  tags: z.array(z.string()),
  // Only our CLI checks this; npm does not enforce engines.remotion.
  engines: z.object({ remotion: z.string() }),
  timing: z.object({
    fps: z.number().int().positive(),
    duration: z.object({ default: z.number().int(), min: z.number().int(), max: z.number().int() }),
    stretch: z.enum(["hold", "scale", "loop"]),
    phases: z.object({ in: z.number().int().nonnegative(), out: z.number().int().nonnegative() }),
    markers: z.record(z.number().int()).default({}),
    beats: z.array(z.number().int()).default([]),
    loop: z.boolean().default(false),
  }),
  layout: z.object({
    aspects: z.array(aspectSchema).min(1),
    mode: z.enum(["responsive", "fixed"]),
    fill: z.enum(["frame", "region"]),
    defaultRegion: region.optional(),
    safeArea: z.enum(["title", "action", "none"]).default("action"),
    transparent: z.boolean(),
    /** Default region preset when used as a layer (see doc PRESETS). */
    preset: z.enum(["full", "center", "upper-third", "lower-third", "left-half", "right-half", "corner-tl", "corner-br"]).optional(),
    /** Props that paint the block's own full-frame background; hidden when the block is a layer. */
    backdrop: z.array(z.string()).default([]),
  }),
  slots: z
    .array(
      z.object({
        key: z.string(),
        type: z.enum(["text", "image", "video", "color", "list", "number"]),
        maxChars: z.number().int().optional(),
        lines: z.number().int().optional(),
        role: z.string().optional(),
      }),
    )
    .default([]),
  // prop key -> brand token path (colors.primary, fonts.heading, ...)
  brand: z.record(z.string()).default({}),
  motionBeats: z
    .array(
      z.object({
        target: z.string(),
        prop: z.string(),
        from: z.string().optional(),
        settledBy: z.number().int().optional(),
        easing: z.enum(["spring", "linear", "ease"]).optional(),
      }),
    )
    .default([]),
  // Gates set these, not people. Declared values are overwritten by intake.
  render: z.object({
    deterministic: z.boolean(),
    clientRenderable: z.boolean(),
    webgl: z.boolean(),
    requiresGpu: z.boolean(),
  }),
  preview: z.object({
    poster: z.object({ marker: z.string() }).or(z.object({ frame: z.number().int() })),
    hover: z.tuple([z.number().int(), z.number().int()]),
  }),
  provenance: z.object({
    origin: z.enum(["own", "curated-oss", "author", "generated"]),
    license: z.string(),
    sourceUrl: z.string().optional(),
    commitSha: z.string().optional(),
    copyrightNotice: z.string().optional(),
  }),
});

export type VideoMeta = z.infer<typeof videoMetaSchema>;
export type VideoMetaInput = z.input<typeof videoMetaSchema>;

export function defineVideoMeta(meta: VideoMetaInput): VideoMeta {
  return videoMetaSchema.parse(meta);
}

export const ASPECT_SIZE: Record<Aspect, { width: number; height: number }> = {
  "16:9": { width: 1920, height: 1080 },
  "9:16": { width: 1080, height: 1920 },
  "1:1": { width: 1080, height: 1080 },
};
