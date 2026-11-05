// Built with Remotion - https://remotion.pro/license
import { z } from "zod";
import { zColor } from "../../../kit/z";
export const NAME = "Spinning Seal Invitation";
export const schema = z.object({ logo: z.string(), text: z.string().min(4).max(64), action: z.string().max(24), destination: z.string().max(32), primary: zColor(), secondary: zColor(), color: zColor(), background: zColor(), fontFamily: z.string() });
export const defaults: z.infer<typeof schema> = { logo: "", text: "MADE TO MOVE · READY TO MAKE ·", action: "Explore more", destination: "Your next chapter", primary: "#A3E635", secondary: "#22D3EE", color: "#F9FAFB", background: "#111827", fontFamily: "DM Sans" };
