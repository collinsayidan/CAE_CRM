// Built with Remotion - https://remotion.pro/license
import { z } from "zod";

/**
 * Color prop. Same description brand as @remotion/zod-types' zColor (so
 * Remotion Studio shows its color picker), but built on our zod 3 instance:
 * @remotion/zod-types 4.0.533 targets zod 4 and its types don't mix with ours.
 */
export const zColor = () =>
  z
    .string()
    .regex(/^(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|rgba?\([^)]{3,40}\)|transparent)$/, "Invalid color")
    .describe("__remotion-color");
