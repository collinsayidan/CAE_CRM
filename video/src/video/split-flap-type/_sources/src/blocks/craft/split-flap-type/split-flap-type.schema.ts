// Built with Remotion - https://remotion.pro/license
import {z} from "zod";
import {zColor} from "../../../kit/z";
export const NAME="Split Flap Headline";
export const schema=z.object({text:z.string().max(32),primary:zColor(),secondary:zColor(),color:zColor(),background:zColor(),fontFamily:z.string(),seed:z.number().int()});
export const defaults: z.infer<typeof schema>={text:"Make it happen",primary:"#E5C07B",secondary:"#61AFEF",color:"#F5EDDC",background:"#171B21",fontFamily:"IBM Plex Mono",seed:53};
