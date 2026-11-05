// Built with Remotion - https://remotion.pro/license
import { z } from "zod";

export const VIDEO_JOB_IDS = ["titles", "product-ui", "devices", "code", "process", "data", "logos", "gallery", "testimonials", "cta", "backgrounds", "cursors"] as const;
export const VIDEO_LANGUAGE_IDS = ["product-ui", "kinetic-poster", "glass", "editorial", "isometric", "photo-collage", "hand-drawn", "pixel-terminal", "neo-brutal", "aura"] as const;
export const videoJobSchema = z.enum(VIDEO_JOB_IDS);
export const videoLanguageSchema = z.enum(VIDEO_LANGUAGE_IDS);
export type VideoJob = z.infer<typeof videoJobSchema>;
export type VideoLanguage = z.infer<typeof videoLanguageSchema>;
export const VIDEO_JOBS: readonly { id: VideoJob; label: string; description: string }[] = [
  { id: "titles", label: "Titles and phrases", description: "Introduce an idea through moving typography." },
  { id: "product-ui", label: "Interface in action", description: "Demonstrate an action and its result inside a product." },
  { id: "devices", label: "Devices", description: "Present screens inside phones, computers and other devices." },
  { id: "code", label: "Code and terminal", description: "Explain commands, code changes and developer workflows." },
  { id: "process", label: "Process and agents", description: "Show connected steps, routing and parallel work." },
  { id: "data", label: "Numbers and data", description: "Make a quantity, comparison or trend visible." },
  { id: "logos", label: "Logos and partners", description: "Introduce a mark, partner or integration." },
  { id: "gallery", label: "Galleries and collections", description: "Present a collection of images, cards or outputs." },
  { id: "testimonials", label: "Testimonials", description: "Present a quote and its source." },
  { id: "cta", label: "Finale and CTA", description: "Close a video with a next step." },
  { id: "backgrounds", label: "Backgrounds and transitions", description: "Create an atmosphere or connect two scenes." },
  { id: "cursors", label: "Cursors", description: "Show clicks, drags, selections and pointers moving through an interface." },
];
export const VIDEO_LANGUAGES: readonly { id: VideoLanguage; label: string; description: string }[] = [
  { id: "product-ui", label: "Product UI", description: "Interface surfaces, direct actions and visible product evidence." },
  { id: "kinetic-poster", label: "Kinetic poster", description: "Large type and graphic composition driven by motion." },
  { id: "glass", label: "Glass", description: "Translucent layers, reflected light and depth." },
  { id: "editorial", label: "Editorial", description: "Paper, rules, folios and serif typography." },
  { id: "isometric", label: "Isometric", description: "Orthographic depth, extruded planes and spatial assembly." },
  { id: "photo-collage", label: "Photo / collage", description: "Photography, cutouts and assembled image fragments." },
  { id: "hand-drawn", label: "Hand-drawn", description: "Drawn lines, imperfect marks and tactile annotations." },
  { id: "pixel-terminal", label: "Pixel / terminal", description: "Monospace grids, discrete steps and terminal structure." },
  { id: "neo-brutal", label: "Neo-brutal", description: "Hard edges, explicit outlines and physical offset shadows." },
  { id: "aura", label: "Aura", description: "Light fields, soft atmosphere and continuous organic motion." },
];

/** Compatibility for older remote manifests. First-party blocks use the explicit curation registry. */
export function getVideoClassification(input: string | { category?: string; job?: unknown; language?: unknown }): { job: VideoJob; language: VideoLanguage } {
  const value = typeof input === "string" ? { category: input } : input;
  const category = value.category ?? "";
  const prefix = category.split("/")[0];
  const job: VideoJob = VIDEO_JOB_IDS.includes(category as VideoJob) ? category as VideoJob
    : prefix === "text" || prefix === "captions" ? "titles"
    : category === "ui/cursor" || prefix === "cursor" || prefix === "cursors" ? "cursors"
    : prefix === "ui" ? "product-ui"
    : prefix === "device" || prefix === "devices" ? "devices"
    : category === "data/code" || prefix === "code" ? "code"
    : prefix === "workflow" || prefix === "diagram" || prefix === "process" ? "process"
    : prefix === "data" || prefix === "data-output" ? "data"
    : prefix === "logo" || prefix === "logos" ? "logos"
    : prefix === "gallery" || prefix === "media" ? "gallery"
    : prefix === "testimonial" ? "testimonials"
    : prefix === "cta" ? "cta"
    : prefix === "background" || prefix === "transition" || prefix === "overlay-fx" ? "backgrounds" : "titles";
  const language: VideoLanguage = category === "data/code" || prefix === "code" ? "pixel-terminal"
    : job === "backgrounds" ? "aura" : job === "titles" ? "kinetic-poster" : "product-ui";
  return { job: videoJobSchema.safeParse(value.job).success ? value.job as VideoJob : job, language: videoLanguageSchema.safeParse(value.language).success ? value.language as VideoLanguage : language };
}
