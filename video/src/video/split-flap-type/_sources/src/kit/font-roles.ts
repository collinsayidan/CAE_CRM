// Built with Remotion - https://remotion.pro/license
// Pure typography role selection. Font loading lives in brand-fonts.ts.
export type FontClass = "sans" | "serif" | "mono" | "accent" | "handwritten";
export type BrandFontRoles = { heading: string; body: string; display?: string; numerals?: string; serif?: string; mono?: string; accent?: string };
export type FontRoleRules = { display?: FontClass; body?: FontClass; numerals?: FontClass | "oldstyle" | "tabular" };
const SERIFS = new Set(["Instrument Serif", "Libre Baskerville", "DM Serif Display", "Lora"]);
const MONOS = new Set(["Geist Mono", "IBM Plex Mono", "Space Mono"]);
const ACCENTS = new Set(["Bebas Neue", "Bricolage Grotesque", "Caveat"]);
const HANDWRITTEN = new Set(["Caveat"]);
const matches = (name: string | undefined, kind: FontClass) => !!name && (kind === "serif" ? SERIFS.has(name) : kind === "mono" ? MONOS.has(name) : kind === "accent" ? ACCENTS.has(name) : kind === "handwritten" ? HANDWRITTEN.has(name) : !SERIFS.has(name) && !MONOS.has(name) && !HANDWRITTEN.has(name));
export function resolveFontRoles(fonts: BrandFontRoles, rules: FontRoleRules = {}) {
  const choose = (requested: string | undefined, kind: FontClass, fallback: string) => {
    if (matches(requested, kind)) return requested!;
    const configured = kind === "sans" ? fonts.heading : kind === "handwritten" ? fonts.accent : fonts[kind];
    return matches(configured, kind) ? configured! : fallback;
  };
  const defaults: Record<FontClass, string> = { sans: matches(fonts.heading,"sans") ? fonts.heading : "Inter", serif: "Instrument Serif", mono: "Geist Mono", accent: "Bebas Neue", handwritten: "Caveat" };
  const role = (name: string | undefined, kind: FontRoleRules["numerals"], legacy: string) => {
    if (kind === "tabular") return [name, fonts.body, fonts.heading, fonts.mono].find((family) => matches(family,"sans") || matches(family,"mono")) || "Inter";
    return kind ? choose(name, kind === "oldstyle" ? "serif" : kind, defaults[kind === "oldstyle" ? "serif" : kind]) : name || legacy;
  };
  return { display: role(fonts.display ?? fonts.heading, rules.display, fonts.heading), body: role(fonts.body, rules.body, fonts.body), numerals: role(fonts.numerals, rules.numerals, fonts.body) };
}
