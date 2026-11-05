import React from "react";
import { AbsoluteFill, Audio, Composition, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Caption, Fade, Rise } from "./Cards";
import { DotBackdrop, FlapTitle, SealEndCard, TiledDashboard } from "./Blocks21";
import { Film, LAUNCH_15V, LAUNCH_30, LAUNCH_60, SOUND_15V, SOUND_30, SOUND_60, frames } from "./launch/Film";

import { Dashboard, Invoice, PHONE, Pipeline, Quote, Ticket, WebForm } from "./Scenes";
import { Highlight, Screen } from "./Screen";
import { BrandBackground, C, FONT, useBrandFont } from "./theme";

const FPS = 30;
const OVERLAP = 12;  // frames each scene cross-dissolves into the next

type Part = { seconds: number; render: (d: number) => React.ReactNode };

// Lays scenes end to end, each overlapping the next by a short dissolve.
const Timeline: React.FC<{ parts: Part[]; music: string }> = ({ parts, music }) => {
  useBrandFont();
  const { durationInFrames } = useVideoConfig();
  let start = 0;
  return (
    <AbsoluteFill style={{ background: C.canvas, fontFamily: FONT }}>
      {parts.map((p, i) => {
        const d = Math.round(p.seconds * FPS) + (i < parts.length - 1 ? OVERLAP : 0);
        const el = (
          <Sequence key={i} from={start} durationInFrames={d}>
            <Fade duration={d} inFrames={i ? OVERLAP : 0} outFrames={i < parts.length - 1 ? OVERLAP : 0}>{p.render(d)}</Fade>
          </Sequence>
        );
        start += Math.round(p.seconds * FPS);
        return el;
      })}
      <Audio src={staticFile(music)} volume={f => interpolate(f, [0, 15, durationInFrames - 30, durationInFrames], [0, 0.55, 0.55, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
    </AbsoluteFill>
  );
};

const total = (parts: Part[]) => Math.round(parts.reduce((s, p) => s + p.seconds, 0) * FPS);

const WALK_60: Part[] = [
  { seconds: 5, render: () => <FlapTitle /> },
  { seconds: 5, render: () => <TiledDashboard caption="Sales, service and invoicing together" /> },
  { seconds: 7, render: d => <Dashboard d={d} caption="See the month at a glance." /> },
  { seconds: 8, render: d => <WebForm d={d} caption="Website enquiries arrive as leads." /> },
  { seconds: 8, render: d => <Pipeline d={d} caption="Move deals through your pipeline." /> },
  { seconds: 7, render: d => <Quote d={d} caption="Customers sign quotes online." /> },
  { seconds: 8, render: d => <Invoice d={d} caption="VAT invoices, card payments and reminders." /> },
  { seconds: 7, render: d => <Ticket d={d} caption="Service deadlines that skip bank holidays." /> },
  { seconds: 5, render: () => <SealEndCard /> },
];

const WALK_30: Part[] = [
  { seconds: 4, render: () => <FlapTitle /> },
  { seconds: 5, render: d => <Dashboard d={d} caption="See the month at a glance." /> },
  { seconds: 6, render: d => <Pipeline d={d} caption="Move deals through your pipeline." /> },
  { seconds: 5, render: d => <Invoice d={d} caption="VAT invoices, card payments and reminders." /> },
  { seconds: 5, render: d => <Ticket d={d} caption="Service deadlines that skip bank holidays." /> },
  { seconds: 5, render: () => <SealEndCard /> },
];

// ---- The 15-second phone ad (9:16) ----------------------------------------------------------------------------

const PHONE_W = 760;
const PhoneScene: React.FC<{ src: string; caption: string; d: number; focus?: { x: number; y: number; width: number; height: number };
  zoom?: number; highlight?: { x: number; y: number; width: number; height: number } }> = ({ src, caption, d, focus, zoom = 1.12, highlight }) => {
  const h = PHONE.viewport.height * (PHONE_W / PHONE.viewport.width);
  return (
    <AbsoluteFill>
      <BrandBackground />
      <Caption text={caption} until={d} top={120} size={caption.length > 28 ? 50 : 58} width={1000} />
      {/* A simple phone: a dark rim around the real phone-width screen. */}
      <div style={{ position: "absolute", left: (1080 - PHONE_W) / 2 - 18, top: 330 - 18, width: PHONE_W + 36, height: h + 36,
        borderRadius: 86, background: C.ink, boxShadow: "0 50px 120px rgba(20,28,56,.35)" }} />
      <Screen src={src} viewport={PHONE.viewport} x={(1080 - PHONE_W) / 2} y={330} width={PHONE_W} radius={70}
        shots={[{ at: 0, zoom: 1, focus }, { at: d, focus, zoom }]}>
        {highlight && <Highlight box={highlight} from={d * 0.35} pad={6} />}
      </Screen>
    </AbsoluteFill>
  );
};

const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const words = ["Sales,", "support", "and invoicing", "in three", "different apps?"];
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <DotBackdrop />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 90px", gap: 6 }}>
        {words.map((w, i) => (
          <Rise key={w} delay={i * 6} distance={60}>
            <div style={{ color: i >= 3 ? C.yellow : C.white, fontWeight: 800, fontSize: 124, letterSpacing: "-0.04em", lineHeight: 1.02 }}>{w}</div>
          </Rise>
        ))}
        <div style={{ height: 14, width: interpolate(frame, [30, 60], [0, 420], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          background: C.coralBright, borderRadius: 999, marginTop: 30 }} />
      </div>
    </AbsoluteFill>
  );
};

const mb = PHONE.boxes;
const AD_15: Part[] = [
  { seconds: 2.5, render: () => <Hook /> },
  { seconds: 3, render: d => <PhoneScene d={d} src="shots/m-pipeline.png" caption="One place for your deals." focus={mb["m-pipeline"].card} zoom={1.08} /> },
  { seconds: 3, render: d => <PhoneScene d={d} src="shots/m-quote-accepted.png" caption="Quotes signed online." zoom={1.06}
      highlight={{ x: 16, y: 96, width: 398, height: 100 }} /> },
  { seconds: 3, render: d => <PhoneScene d={d} src="shots/m-ticket.png" caption="Support with UK service levels." focus={mb["m-ticket"].sla} zoom={1.1}
      highlight={mb["m-ticket"].sla} /> },
  { seconds: 3.5, render: () => <SealEndCard skip={40} /> },
];

export const Root: React.FC = () => (
  <>
    <Composition id="Launch60" component={() => <Film parts={LAUNCH_60} {...SOUND_60} />}
      durationInFrames={frames(LAUNCH_60)} fps={FPS} width={1920} height={1080} />
    <Composition id="Launch30" component={() => <Film parts={LAUNCH_30} {...SOUND_30} />}
      durationInFrames={frames(LAUNCH_30)} fps={FPS} width={1920} height={1080} />
    <Composition id="Launch15Vertical" component={() => <Film parts={LAUNCH_15V} {...SOUND_15V} />}
      durationInFrames={frames(LAUNCH_15V)} fps={FPS} width={1080} height={1920} />
    <Composition id="Walkthrough60" component={() => <Timeline parts={WALK_60} music="music/bed-60.wav" />}
      durationInFrames={total(WALK_60)} fps={FPS} width={1920} height={1080} />
    <Composition id="Walkthrough30" component={() => <Timeline parts={WALK_30} music="music/bed-30.wav" />}
      durationInFrames={total(WALK_30)} fps={FPS} width={1920} height={1080} />
    <Composition id="Ad15Vertical" component={() => <Timeline parts={AD_15} music="music/bed-15.wav" />}
      durationInFrames={total(AD_15)} fps={FPS} width={1080} height={1920} />
  </>
);
