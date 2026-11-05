// Built with Remotion - https://remotion.pro/license
import { loadFont as loadDMSans } from "@remotion/google-fonts/DMSans";
import { loadFont as loadGeist } from "@remotion/google-fonts/Geist";
import { loadFont as loadIBMPlexSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadManrope } from "@remotion/google-fonts/Manrope";
import { loadFont as loadSpaceGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadInstrumentSerif } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as loadLibreBaskerville } from "@remotion/google-fonts/LibreBaskerville";
import { loadFont as loadDMSerifDisplay } from "@remotion/google-fonts/DMSerifDisplay";
import { loadFont as loadGeistMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadIBMPlexMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadSpaceMono } from "@remotion/google-fonts/SpaceMono";
import { loadFont as loadBebasNeue } from "@remotion/google-fonts/BebasNeue";
import { loadFont as loadBricolageGrotesque } from "@remotion/google-fonts/BricolageGrotesque";
import { loadFont as loadCaveat } from "@remotion/google-fonts/Caveat";
import { loadFont as loadPlusJakartaSans } from "@remotion/google-fonts/PlusJakartaSans";

/**
 * The OFL brand fonts the editor offers (BRAND_FONTS in doc/schema.ts).
 * Loaded on demand with explicit weights and subsets (required in Remotion 5).
 * Blocks receive the family name through brand bindings (fonts.heading/body)
 * and use it as a CSS font-family; the loader makes sure it's ready.
 */
const LOADERS: Record<string, () => { fontFamily: string; waitUntilDone: () => Promise<void> }> = {
  // CAE CRM: the app's own typeface.
  "Plus Jakarta Sans": () => loadPlusJakartaSans("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] }),
  Inter: () => loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  Manrope: () => loadManrope("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  "DM Sans": () => loadDMSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  "Space Grotesk": () => loadSpaceGrotesk("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  "IBM Plex Sans": () => loadIBMPlexSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  Geist: () => loadGeist("normal", { weights: ["300", "400", "500", "600"], subsets: ["latin"] }),
  "Instrument Serif": () => loadInstrumentSerif("normal", { weights: ["400"], subsets: ["latin"] }),
  "Libre Baskerville": () => loadLibreBaskerville("normal", { weights: ["400", "700"], subsets: ["latin"] }),
  "DM Serif Display": () => loadDMSerifDisplay("normal", { weights: ["400"], subsets: ["latin"] }),
  "Geist Mono": () => loadGeistMono("normal", { weights: ["400", "500", "600"], subsets: ["latin"] }),
  "IBM Plex Mono": () => loadIBMPlexMono("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  "Space Mono": () => loadSpaceMono("normal", { weights: ["400", "700"], subsets: ["latin"] }),
  "Bebas Neue": () => loadBebasNeue("normal", { weights: ["400"], subsets: ["latin"] }),
  "Bricolage Grotesque": () => loadBricolageGrotesque("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
  Caveat: () => loadCaveat("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }),
};

const loaded = new Map<string, string>();
const pending = new Map<string, Promise<void>>();

/** Returns the CSS font-family for a brand font name, loading it once. Unknown names fall back to Inter. */
export function loadBrandFont(name: string): string {
  const key = LOADERS[name] ? name : "Inter";
  const hit = loaded.get(key);
  if (hit) return hit;
  const font = LOADERS[key]!();
  const family = font.fontFamily;
  pending.set(key, font.waitUntilDone());
  loaded.set(key, family);
  return family;
}

/** Font bytes must register before native text measurements or canvas wrapping. */
export async function waitForBrandFonts(): Promise<void> {
  await Promise.all([...pending.values()]);
}

export function brandFontStack(name: string | undefined): string {
  const family = name ?? "Inter";
  const fallback = /Serif|Baskerville/.test(family) ? "Georgia, serif" : /Mono/.test(family) ? "monospace" : "Inter, system-ui, sans-serif";
  return `${loadBrandFont(family)}, ${fallback}`;
}
