// Built with Remotion - https://remotion.pro/license
import { z } from "zod";
import { zColor } from "../../../kit/z";

export const NAME = "Tiled Screenshot Reveal";

export const schema = z.object({
  /** Screenshot or artwork cut into nine tiles. Empty shows a neutral sample page. */
  image: z.string(),
  /** Which part of the image stays in view when it is cropped to the grid. */
  focus: z.enum(["center", "top"]),
  /** Optional logo, set next to the caption. */
  logo: z.string(),
  /** One short line under the finished picture. Empty hides it. */
  caption: z.string().max(40),
  /** Caption and hairlines. */
  color: zColor(),
  /** Landing light and weld glow. */
  accent: zColor(),
  /** Second color of the glow. */
  secondary: zColor(),
  background: zColor(),
  fontFamily: z.string(),
  /** Changes the order the tiles land in. */
  seed: z.number().int().min(1).max(99),
});

export const defaults: z.infer<typeof schema> = {
  image: "",
  focus: "center",
  logo: "",
  caption: "See the full picture",
  color: "#F4F6FB",
  accent: "#FF7AB6",
  secondary: "#7CC6FE",
  background: "#0F1420",
  fontFamily: "Geist",
  seed: 7,
};
