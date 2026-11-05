// Built with Remotion - https://remotion.pro/license
import React,{useMemo} from "react";
import type {z} from "zod";
import {AbsoluteFill,useCurrentFrame} from "remotion";
import {brandFontStack,useLayout,withAlpha} from "../../../kit/index";
import {rng} from "../_lib/noise";
import type {schema} from "./split-flap-type.schema";
const ease=(x:number)=>{const t=Math.max(0,Math.min(1,x));return t*t*(3-2*t);};
export const Component: React.FC<z.infer<typeof schema>>=({text,primary,secondary,color,background,fontFamily,seed})=>{
 const f=Math.min(135,useCurrentFrame()),{width:w,height:h,portrait}=useLayout(),cols=portrait?6:12;
 const lines:string[]=[];for(const word of text.toUpperCase().trim().split(/\s+/)){let rest=word;while(rest.length>cols){lines.push(rest.slice(0,cols));rest=rest.slice(cols);}const last=lines.length-1;if(last<0||lines[last]!.length+rest.length+1>cols)lines.push(rest);else lines[last]+=` ${rest}`;}
 if(!lines.length)lines.push(" ");const count=Math.max(...lines.map(line=>line.length)),rows=lines.length,gap=Math.min(w,h)*.007,cw=(w*.84-gap*(count-1))/count,ch=Math.min((h*.70-gap*(rows-1))/rows,cw*(portrait?2.4:1.35)),font=Math.min(cw*1.18,ch*.68),left=(w-count*cw-(count-1)*gap)/2,top=(h-rows*ch-(rows-1)*gap)/2;
 const stops=useMemo(()=>{const random=rng(seed);return Array.from({length:40},()=>({cycles:5+Math.floor(random()*7),delay:Math.floor(random()*13)}));},[seed]);const chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
 const cardText=(char:string)=> char ? <span style={{position:"absolute",left:0,top:0,width:cw,height:ch,display:"flex",alignItems:"center",justifyContent:"center",fontFamily:brandFontStack(fontFamily),fontSize:font,lineHeight:1.2,fontWeight:600,color}}>{char}</span> : null;
 return <AbsoluteFill style={{background:background==="transparent"?undefined:background}}><div style={{position:"absolute",left,top,width:count*cw+(count-1)*gap,height:rows*ch+(rows-1)*gap,perspective:w*1.7,opacity:ease(f/14)}}>
 {lines.flatMap((line,row)=>Array.from(line).map((target,col)=>{const index=row*cols+col,stop=stops[index%stops.length]!,t=Math.max(0,(f-stop.delay)/8),cycle=Math.min(stop.cycles,Math.floor(t)),p=cycle>=stop.cycles?1:t%1,previous=cycle>=stop.cycles?target:chars[(cycle*7+index*3)%chars.length]!,next=cycle>=stop.cycles-1?target:chars[((cycle+1)*7+index*3)%chars.length]!,x=((count-line.length)*cw+(count-line.length)*gap)/2+col*(cw+gap);const panel=(topHalf:boolean,glyph:string,angle?:number)=> <div style={{position:"absolute",left:0,top:topHalf?0:ch/2,width:cw,height:ch/2,overflow:"hidden",background:`color-mix(in srgb, ${background==="transparent"?`rgb(from ${color} calc(255 - r) calc(255 - g) calc(255 - b))`:background} 88%, ${topHalf?primary:secondary})`,borderRadius:topHalf?`${cw*.05}px ${cw*.05}px 0 0`:`0 0 ${cw*.05}px ${cw*.05}px`,transform:angle===undefined?undefined:`rotateX(${angle}deg)`,transformOrigin:topHalf?"50% 100%":"50% 0%",backfaceVisibility:"hidden",boxShadow:angle===undefined?undefined:`0 ${ch*.025}px ${ch*.045}px ${withAlpha(background==="transparent"?primary:background,.4)}`}}><div style={{position:"absolute",left:0,top:topHalf?0:-ch/2,width:cw,height:ch}}>{cardText(glyph)}</div></div>;
 return <div data-21st-slot="text" key={`${row}-${col}`} style={{position:"absolute",left:x,top:row*(ch+gap),width:cw,height:ch,border:`${Math.max(1,cw*.01)}px solid ${withAlpha(color,.15)}`,borderRadius:cw*.05,boxShadow:`0 ${ch*.012}px ${ch*.035}px ${withAlpha(color,.07)}`,transformStyle:"preserve-3d"}}>
 {panel(true,cycle>=stop.cycles?"":next)}{panel(false,cycle>=stop.cycles?"":p>=.5?next:previous)}{cycle>=stop.cycles&&cardText(target)}{p<.5?panel(true,previous,-p*180):p<1?panel(false,next,180-p*180):null}
 <div style={{position:"absolute",left:0,right:0,top:ch/2,height:Math.max(1,ch*.012),background:withAlpha(background==="transparent"?primary:background,.8)}}/>
 {[0,1].map(side=><div key={side} style={{position:"absolute",left:side===0?-cw*.016:undefined,right:side===1?-cw*.016:undefined,top:ch*.46,width:cw*.03,height:ch*.08,borderRadius:cw*.02,background:withAlpha(color,.38)}}/>)}</div>;
 }))}</div></AbsoluteFill>;
};
