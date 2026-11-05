import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import boxes from "../public/shots/boxes.json";
import { BrandBackground } from "./theme";
import { Caption } from "./Cards";
import { Box, Cursor, Highlight, Patch, Screen, Shot } from "./Screen";

const B = boxes as unknown as Record<string, Record<string, Box> & { viewport: { width: number; height: number } }>;
const VP = { width: 1920, height: 1080 };
const WIN = { x: 96, y: 40, width: 1728 };  // the app window on a 1920×1080 frame
const clamp = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
const pad = (b: Box, p: number): Box => ({ x: b.x - p, y: b.y - p, width: b.width + p * 2, height: b.height + p * 2 });

type SceneProps = { d: number; caption: string };

const Frame: React.FC<{ children: React.ReactNode; caption: string; d: number }> = ({ children, caption, d }) => (
  <AbsoluteFill>
    <BrandBackground />
    {children}
    <Caption text={caption} until={d} bottom={64} />
  </AbsoluteFill>
);

export const Dashboard: React.FC<SceneProps> = ({ d, caption }) => {
  const shots: Shot[] = [{ at: 0, zoom: 1 }, { at: d * 0.35, focus: B.dashboard.track, zoom: 1.12 },
    { at: d * 0.75, focus: pad(B.dashboard.stats, 20), zoom: 1.14 }, { at: d, focus: pad(B.dashboard.stats, 20), zoom: 1.17 }];
  return (
    <Frame caption={caption} d={d}>
      <Screen src="shots/dashboard.png" viewport={VP} shots={shots} {...WIN}>
        <Highlight box={B.dashboard.track} from={d * 0.3} until={d * 0.62} pad={6} />
      </Screen>
    </Frame>
  );
};

export const WebForm: React.FC<SceneProps> = ({ d, caption }) => {
  const half = Math.round(d * 0.5);
  const act = { x: 600, y: 440, width: 1060, height: 400 };
  return (
    <Frame caption={caption} d={d}>
      <Sequence durationInFrames={half + 8}>
        <Screen src="shots/webform.png" viewport={VP} shots={[{ at: 0, focus: B.webform.card, zoom: 1.25 },
          { at: half, focus: B.webform.message, zoom: 1.45 }]} {...WIN} sample={false}>
          <Highlight box={B.webform.message} from={half * 0.35} pad={6} color="#1e5bd6" />
        </Screen>
      </Sequence>
      <Sequence from={half}>
        <FadeIn>
          <Screen src="shots/contact.png" viewport={VP} shots={[{ at: 0, focus: act, zoom: 1.2 }, { at: d - half, focus: act, zoom: 1.32 }]} {...WIN}>
            <Highlight box={{ x: 640, y: 680, width: 920, height: 80 }} from={12} pad={4} />
          </Screen>
        </FadeIn>
      </Sequence>
    </Frame>
  );
};

const FadeIn: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  return <div style={{ position: "absolute", inset: 0, opacity: interpolate(frame, [0, 10], [0, 1], clamp) }}>{children}</div>;
};

// The deals board: the cursor lifts a deal from one stage and drops it in the next.
export const Pipeline: React.FC<SceneProps> = ({ d, caption }) => {
  const frame = useCurrentFrame();
  const card = B["pipeline-before"].card, target = B["pipeline-after"].card, toCol = B["pipeline-after"].target;
  const grab = Math.round(d * 0.3), drop = Math.round(d * 0.62);
  const lifted = frame >= grab && frame < drop + 6;
  const t = interpolate(frame, [grab, drop], [0, 1], clamp);
  const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  const lift = interpolate(frame, [grab, grab + 6, drop - 4, drop + 4], [0, 1, 1, 0], clamp);
  const pos = { x: card.x + (target.x - card.x) * ease, y: card.y + (target.y - card.y) * ease - lift * 10 };
  const focus = { x: 260, y: 230, width: 680, height: 420 };
  const grabPoint = { x: card.x + card.width * 0.45, y: card.y + card.height * 0.4 };
  return (
    <Frame caption={caption} d={d}>
      <Screen src={frame < grab ? "shots/pipeline-before.png" : "shots/pipeline-after.png"} viewport={VP}
        shots={[{ at: 0, zoom: 1 }, { at: grab - 6, focus, zoom: 1.55 }, { at: d, focus, zoom: 1.62 }]} {...WIN}>
        {/* Until the drop, the target column still looks as it did before the move. */}
        {frame >= grab && frame < drop + 4 && <Patch src="shots/pipeline-before.png" viewport={VP}
          from={{ x: toCol.x - 4, y: toCol.y - 4, width: toCol.width + 8, height: toCol.height + 8 }} to={{ x: toCol.x - 4, y: toCol.y - 4 }}
          style={{ borderRadius: 0 }} />}
        {lifted && <Patch src="shots/pipeline-before.png" viewport={VP} from={card} to={pos} lift={lift} />}
        <Cursor appear={grab - 30} clicks={[grab, drop]} path={[
          { at: grab - 30, x: grabPoint.x + 160, y: grabPoint.y + 180 }, { at: grab, ...grabPoint },
          { at: drop, x: grabPoint.x + (target.x - card.x), y: grabPoint.y + (target.y - card.y) },
          { at: d, x: grabPoint.x + (target.x - card.x) + 60, y: grabPoint.y + 120 }]} />
        <Highlight box={target} from={drop + 4} pad={8} color="#1f8f5f" />
      </Screen>
    </Frame>
  );
};

// A quote, signed online: the customer clicks Accept and sign, and the signature lands.
export const Quote: React.FC<SceneProps> = ({ d, caption }) => {
  const frame = useCurrentFrame();
  const click = Math.round(d * 0.4);
  const accept = B["quote-sign"].accept, sign = B["quote-sign"].sign;
  const signed = { x: 530, y: 790, width: 720, height: 100 };
  return (
    <Frame caption={caption} d={d}>
      {frame < click + 6 ? (
        <Screen src="shots/quote-sign.png" viewport={VP} shots={[{ at: 0, focus: pad(sign, 120), zoom: 1.35 }, { at: click, focus: pad(accept, 160), zoom: 1.5 }]} {...WIN}>
          <Cursor appear={4} clicks={[click]} path={[{ at: 4, x: sign.x + 500, y: sign.y - 40 }, { at: click - 2, x: accept.x + accept.width * 0.5, y: accept.y + accept.height * 0.55 }]} />
        </Screen>
      ) : (
        <FadeIn>
          <Screen src="shots/quote-accepted.png" viewport={VP} shots={[{ at: 0, focus: signed, zoom: 1.5 },
            { at: d - click, focus: { x: 480, y: 80, width: 860, height: 820 }, zoom: 1.12 }]} {...WIN}>
            <Highlight box={signed} from={8} pad={6} color="#1f8f5f" until={Math.round((d - click) * 0.55)} />
            <Highlight box={{ x: 495, y: 96, width: 790, height: 60 }} from={Math.round((d - click) * 0.6)} pad={4} color="#1f8f5f" />
          </Screen>
        </FadeIn>
      )}
    </Frame>
  );
};

export const Invoice: React.FC<SceneProps> = ({ d, caption }) => {
  const vat = { x: 305, y: 600, width: 760, height: 180 };
  return (
    <Frame caption={caption} d={d}>
      <Screen src="shots/invoice.png" viewport={VP} shots={[{ at: 0, focus: B.invoice.doc, zoom: 1.05 },
        { at: d * 0.45, focus: vat, zoom: 1.75 }, { at: d * 0.8, focus: { x: 230, y: 110, width: 900, height: 420 }, zoom: 1.4 }, { at: d, focus: { x: 230, y: 110, width: 900, height: 420 }, zoom: 1.45 }]} {...WIN}>
        <Highlight box={{ x: 610, y: 627, width: 455, height: 24 }} from={d * 0.35} until={d * 0.62} pad={6} />
        <Highlight box={B.invoice.status} from={d * 0.75} pad={6} color="#1f8f5f" />
      </Screen>
    </Frame>
  );
};

export const Ticket: React.FC<SceneProps> = ({ d, caption }) => (
  <Frame caption={caption} d={d}>
    <Screen src="shots/ticket.png" viewport={VP} shots={[{ at: 0, focus: { x: 260, y: 80, width: 1360, height: 300 }, zoom: 1.15 },
      { at: d * 0.5, focus: B.ticket.sla, zoom: 1.6 }, { at: d, focus: B.ticket.sla, zoom: 1.68 }]} {...WIN}>
      <Highlight box={B.ticket.sla} from={d * 0.4} pad={6} />
    </Screen>
  </Frame>
);

export const PHONE = { viewport: { width: 430, height: 932 }, boxes: B };
