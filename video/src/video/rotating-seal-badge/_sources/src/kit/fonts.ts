// Built with Remotion - https://remotion.pro/license
import { loadFont as loadGeist } from "@remotion/google-fonts/Geist";
import { loadFont as loadGeistMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadInstrumentSerif } from "@remotion/google-fonts/InstrumentSerif";

// OFL fonts only, weights and subsets always explicit (required in Remotion 5).
const sans = loadGeist("normal", { weights: ["300", "400", "500", "600"], subsets: ["latin"] });
const mono = loadGeistMono("normal", { weights: ["400", "500"], subsets: ["latin"] });
const serif = loadInstrumentSerif("italic", { weights: ["400"], subsets: ["latin"] });
export const SANS = sans.fontFamily;
export const MONO = mono.fontFamily;
export const SERIF = serif.fontFamily;
export const FONT_READY = Promise.all([sans.waitUntilDone(), mono.waitUntilDone(), serif.waitUntilDone()]);
