// Built with Remotion - https://remotion.pro/license
import { z } from "zod";
import { zColor } from "../../../kit/z";

export const NAME = "Dot Field Ripples";

export const schema = z.object({
  /** Optional line the last drop lands under. Empty (the default) leaves the field on its own. */
  headline: z.string().max(60),
  /** Text and the resting dots (30%). */
  color: zColor(),
  /** Wave crests and the drops. */
  primary: zColor(),
  /** Wave troughs. */
  secondary: zColor(),
  background: zColor(),
  /** Face of the headline. */
  fontFamily: z.string(),
  /** Where the drops land (any whole number gives a different rhythm map). */
  seed: z.number().int().min(1).max(999),
  /** Dot spacing: below 1 is a finer field, above 1 a bolder one. */
  spacing: z.number().min(0.7).max(1.5),
  grain: z.boolean(),
});

export const defaults: z.infer<typeof schema> = {
  headline: "",
  color: "#3D2C2E",
  primary: "#E76F51",
  secondary: "#2A9D8F",
  background: "#FFF1E6",
  fontFamily: "Bricolage Grotesque",
  seed: 12,
  spacing: 1,
  grain: true,
};
