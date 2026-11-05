// The CAE CRM launch film: a dark, product-lit story in chapters. Scenes take their length (d, in frames) so the
// 60s film, the 30s cut and the 15s vertical ad share them. Designed at 1920×1080 (1080×1920 for the ad); render
// with --scale=2 for 4K.
import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import boxes from "../../public/shots/boxes.json";
import { Box, Cursor, Highlight, Patch } from "../Screen";
import { FONT, useBrandFont } from "../theme";
import { Phone, Slab } from "./Device";
import { Chip, D, Dip, Flash, Kicker, Sfx, Stage, Words, clamp, inOut, ramp } from "./look";

const B = boxes as unknown as Record<string, Record<string, Box>>;
const VP = { width: 1920, height: 1080 };
const pad = (b: Box, p: number): Box => ({ x: b.x - p, y: b.y - p, width: b.width + p * 2, height: b.height + p * 2 });
type S = { d: number };

// ---- Opening ----------------------------------------------------------------------------------------------------

const PAINS = ["Leads in one app.", "Quotes in another.", "Invoices in a spreadsheet.", "Support in your inbox."];
const TABS = ["Leads", "Quotes", "Invoices", "Support"];

// The pain, one line per beat, while four scattered "apps" light up along the bottom.
export const ColdOpen: React.FC<S & { lines?: string[] }> = ({ d, lines = PAINS }) => {
  const f = useCurrentFrame();
  const seg = d / lines.length;
  const i = Math.min(lines.length - 1, Math.floor(f / seg));
  return (
    <Stage light={0.35} y={110}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <Sequence key={i} from={Math.round(i * seg)} layout="none">
          <Words text={lines[i]} size={132} gap={3} accent={["another", "spreadsheet", "inbox"]} accentColor={D.coral} />
        </Sequence>
        {lines.map((_, k) => <Sfx key={k} name="thud" at={k * seg} volume={0.45} />)}
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 110, display: "flex", justifyContent: "center", gap: 26 }}>
        {TABS.slice(0, lines.length).map((t, k) => {
          const on = ramp(f, k * seg, k * seg + 10);
          return (
            <div key={t} style={{ padding: "14px 30px", borderRadius: 14, fontFamily: FONT, fontWeight: 700, fontSize: 28, color: D.ink,
              border: "1px solid rgba(255,255,255,.18)", background: `rgba(255,95,61,${0.18 * on})`, opacity: 0.25 + on * 0.75,
              transform: `translateY(${(1 - on) * 16}px) rotate(${(k - 1.5) * 2 * on}deg)` }}>{t}</div>
          );
        })}
      </div>
    </Stage>
  );
};

// The turn: one quiet line, then a thin blue light opens in the dark.
export const Turn: React.FC<S> = ({ d }) => {
  const f = useCurrentFrame();
  const beam = ramp(f, d * 0.55, d, inOut);
  return (
    <Stage light={0.2}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <Words text="There's a better way." size={110} at={4} gap={5} until={d * 0.7} />
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 960 - 900 * beam, top: 600, width: 1800 * beam, height: 3, borderRadius: 3,
        background: `linear-gradient(90deg, transparent, ${D.glow}, #ffffff, ${D.glow}, transparent)`, boxShadow: `0 0 40px ${D.glow}`, opacity: beam }} />
    </Stage>
  );
};

// The reveal: the dashboard rises out of the light like a screen opening, and the name lands.
export const Reveal: React.FC<S & { flat?: boolean }> = ({ d }) => {
  const f = useCurrentFrame();
  const rise = Math.round(d * 0.42);
  return (
    <Stage light={0.4 + 0.6 * ramp(f, 0, rise)} y={70}>
      <Slab src="shots/dashboard.png" width={1500}
        shots={[{ at: 0, zoom: 1 }, { at: d, zoom: 1.06, focus: { x: 260, y: 180, width: 1640, height: 460 } }]}
        poses={[{ at: 0, rx: 72, y: 330, z: -500, s: 0.78 }, { at: rise, rx: 6, y: 120, z: 0, s: 0.8 }, { at: d, rx: 0, y: 105, z: 60, s: 0.82 }]} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 58, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
        <Words text="Meet CAE CRM." size={104} at={rise - 14} gap={4} accent={["CRM"]} accentColor={D.ink} />
        <Words text="The CRM built for UK business." size={40} weight={600} color={D.dim} at={rise + 8} gap={2} />
      </div>
      <Flash at={rise} length={14} strength={0.5} />
      <Sfx name="riser" at={rise - 66} volume={0.55} />
      <Sfx name="hit" at={rise} volume={0.6} />
    </Stage>
  );
};

// ---- Chapters ---------------------------------------------------------------------------------------------------

export const ChapterCard: React.FC<S & { n: string; label: string; title: string; accent: string[] }> = ({ d, n, label, title, accent }) => (
  <Stage light={0.45} y={58}>
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 34, flexDirection: "column" }}>
      <Kicker n={n} label={label} />
      <Words text={title} size={170} at={6} gap={5} accent={accent} until={d} />
    </AbsoluteFill>
    <Sfx name="hit" volume={0.3} />
  </Stage>
);

// Text on one side, the product floating on the other.
const Side: React.FC<{ n?: string; label?: string; title: string; sub?: string; accent?: string[]; side?: "left" | "right"; d: number }> =
  ({ n, label, title, sub, accent = [], side = "left", d }) => (
    <div style={{ position: "absolute", top: 0, bottom: 0, [side]: 120, width: 640, display: "flex", flexDirection: "column",
      justifyContent: "center", gap: 28 }}>
      {n && label && <Kicker n={n} label={label} size={26} />}
      <Words text={title} size={84} align="left" width={640} at={6} gap={4} accent={accent} until={d} />
      {sub && <Words text={sub} size={32} weight={600} color={D.dim} align="left" width={600} at={20} gap={2} until={d} />}
    </div>
  );

// Website enquiry → lead.
export const Enquiry: React.FC<S & { n?: string }> = ({ d, n }) => {
  const half = Math.round(d * 0.48);
  const pose = [{ at: 0, ry: -24, rx: 4, x: 330, s: 0.66, z: -120 }, { at: d, ry: -16, rx: 2, x: 300, s: 0.7, z: 0 }];
  return (
    <Stage light={0.9} x={66}>
      <Sequence durationInFrames={half + 6} layout="none">
        <Slab src="shots/webform.png" sample={false} poses={pose}
          shots={[{ at: 0, focus: B.webform.card, zoom: 1.35 }, { at: half, focus: B.webform.message, zoom: 1.6 }]}>
          <Highlight box={B.webform.message} from={half * 0.3} pad={6} color={D.glow} />
        </Slab>
      </Sequence>
      <Sfx name="whoosh" at={half - 8} volume={0.4} />
      <Sequence from={half} layout="none">
        <Dip d={d - half} inF={6} outF={0}>
          <Slab src="shots/contact.png" poses={pose.map(p => ({ ...p, at: p.at === 0 ? 0 : d - half }))}
            shots={[{ at: 0, focus: { x: 300, y: 200, width: 900, height: 560 }, zoom: 1.25 }, { at: d - half, focus: { x: 300, y: 200, width: 900, height: 560 }, zoom: 1.35 }]}>
            <Highlight box={pad(B.contact.lead, 6)} from={8} pad={4} color={D.yellow} />
          </Slab>
          <Chip text="New lead, from your website" at={14} style={{ right: 150, bottom: 150 }} />
        </Dip>
      </Sequence>
      <Side n={n} label="Sales" title="Enquiries become leads." accent={["leads"]} sub="Your website form drops each one straight into the CRM." d={d} />
    </Stage>
  );
};

// A deal lifted from one stage and dropped in the next.
export const Pipeline: React.FC<S & { n?: string }> = ({ d, n }) => {
  const f = useCurrentFrame();
  const card = B["pipeline-before"].card, target = B["pipeline-after"].card, toCol = B["pipeline-after"].target;
  const grab = Math.round(d * 0.3), drop = Math.round(d * 0.66);
  const t = ramp(f, grab, drop, inOut);
  const lift = interpolate(f, [grab, grab + 6, drop - 4, drop + 4], [0, 1, 1, 0], clamp);
  const pos = { x: card.x + (target.x - card.x) * t, y: card.y + (target.y - card.y) * t - lift * 10 };
  const focus = { x: 250, y: 250, width: 700, height: 420 };
  const gp = { x: card.x + card.width * 0.45, y: card.y + card.height * 0.4 };
  return (
    <Stage light={0.9} x={36}>
      <Slab src={f < grab ? "shots/pipeline-before.png" : "shots/pipeline-after.png"}
        poses={[{ at: 0, ry: 20, rx: 6, x: -300, s: 0.68, z: -100 }, { at: d, ry: 14, rx: 4, x: -290, s: 0.72 }]}
        shots={[{ at: 0, zoom: 1.2, focus }, { at: grab - 4, focus, zoom: 1.55 }, { at: d, focus, zoom: 1.62 }]}>
        {f >= grab && f < drop + 4 && <Patch src="shots/pipeline-before.png" viewport={VP}
          from={pad(toCol, 4)} to={{ x: toCol.x - 4, y: toCol.y - 4 }} style={{ borderRadius: 0 }} />}
        {f >= grab && f < drop + 6 && <Patch src="shots/pipeline-before.png" viewport={VP} from={card} to={pos} lift={lift} />}
        <Cursor appear={grab - 24} clicks={[grab, drop]} path={[
          { at: grab - 24, x: gp.x + 150, y: gp.y + 170 }, { at: grab, ...gp },
          { at: drop, x: gp.x + (target.x - card.x), y: gp.y + (target.y - card.y) },
          { at: d, x: gp.x + (target.x - card.x) + 60, y: gp.y + 120 }]} />
        <Highlight box={target} from={drop + 4} pad={8} color="#3ddc97" />
      </Slab>
      <Sfx name="click" at={grab} volume={0.6} />
      <Sfx name="thud" at={drop} volume={0.6} />
      <Chip text="Moved to the next stage" at={drop + 6} tone="ok" style={{ left: 640, bottom: 150 }} />
      <Side n={n} label="Sales" title="Drag a deal. Done." accent={["Done"]} sub="Your whole pipeline, stage by stage, on one board." side="right" d={d} />
    </Stage>
  );
};

// The customer signs the quote online.
export const Quote: React.FC<S & { n?: string }> = ({ d, n }) => {
  const f = useCurrentFrame();
  const click = Math.round(d * 0.42);
  const accept = B["quote-sign"].accept, sign = B["quote-sign"].sign;
  const pose = [{ at: 0, ry: -22, rx: 4, x: 320, s: 0.68, z: -100 }, { at: d, ry: -15, rx: 2, x: 300, s: 0.72 }];
  const signed = { x: 576, y: 862, width: 746, height: 82 };
  return (
    <Stage light={0.9} x={66}>
      {f < click + 4 ? (
        <Slab src="shots/quote-sign.png" sample={false} poses={pose}
          shots={[{ at: 0, focus: pad(sign, 140), zoom: 1.3 }, { at: click, focus: pad(accept, 170), zoom: 1.5 }]}>
          <Cursor appear={4} clicks={[click]} path={[{ at: 4, x: sign.x + 520, y: sign.y - 40 },
            { at: click - 2, x: accept.x + accept.width * 0.5, y: accept.y + accept.height * 0.55 }]} />
        </Slab>
      ) : (
        <Slab src="shots/quote-accepted.png" sample={false} poses={pose}
          shots={[{ at: click, focus: signed, zoom: 1.5 }, { at: d, focus: { x: 480, y: 80, width: 860, height: 820 }, zoom: 1.12 }]}>
          <Highlight box={signed} from={click + 6} pad={6} color="#3ddc97" />
        </Slab>
      )}
      <Flash at={click + 4} length={8} strength={0.35} />
      <Sfx name="click" at={click} volume={0.6} />
      <Sfx name="chime" at={click + 6} volume={0.5} />
      <Chip text="Accepted and signed" at={click + 10} style={{ right: 160, bottom: 140 }} />
      <Side n={n} label="Money" title="Quotes, signed online." accent={["signed"]} sub="Send a link. Your customer reads, accepts and signs." d={d} />
    </Stage>
  );
};

// A VAT invoice that lights up its VAT line, then shows as paid.
export const Invoice: React.FC<S & { n?: string }> = ({ d, n }) => {
  const vat = { x: 700, y: 625, width: 370, height: 30 };
  return (
    <Stage light={0.9} x={36}>
      <Slab src="shots/invoice.png" poses={[{ at: 0, ry: 20, rx: 5, x: -400, s: 0.66, z: -100 }, { at: d, ry: 13, rx: 3, x: -390, s: 0.7 }]}
        shots={[{ at: 0, focus: B.invoice.doc, zoom: 1.1 }, { at: d * 0.45, focus: pad(vat, 140), zoom: 1.85 },
          { at: d * 0.75, focus: { x: 240, y: 100, width: 880, height: 420 }, zoom: 1.45 }, { at: d, focus: { x: 240, y: 100, width: 880, height: 420 }, zoom: 1.5 }]}>
        <Highlight box={vat} from={d * 0.3} until={d * 0.62} pad={6} color={D.yellow} />
        <Highlight box={B.invoice.status} from={d * 0.72} pad={6} color="#3ddc97" />
      </Slab>
      <Chip text="VAT at 20%, worked out for you" at={d * 0.32} tone="yellow" style={{ left: 560, bottom: 210 }} />
      <Chip text="Paid" at={d * 0.74} style={{ left: 560, bottom: 120 }} />
      <Sfx name="chime" at={d * 0.74} volume={0.5} />
      <Side n={n} label="Money" title="Get paid faster." accent={["faster"]} sub="VAT invoices, card payments and reminders." side="right" d={d} />
    </Stage>
  );
};

// A ticket's service deadline, and why it's right: it skips the bank holiday.
export const Service: React.FC<S & { n?: string }> = ({ d, n }) => {
  const f = useCurrentFrame();
  const days = ["Fri", "Sat", "Sun", "Mon", "Tue"];
  const off = [false, true, true, true, false];   // the weekend, then a bank holiday Monday
  const jump = ramp(f, d * 0.5, d * 0.78, inOut);
  const tile = 150, gap = 16, left = 1180 - (days.length * (tile + gap)) / 2;
  return (
    <Stage light={0.9} x={60}>
      <Slab src="shots/ticket.png" poses={[{ at: 0, ry: -20, rx: 8, x: 300, y: -150, s: 0.6, z: -100 }, { at: d, ry: -14, rx: 5, x: 290, y: -150, s: 0.63 }]}
        shots={[{ at: 0, focus: { x: 260, y: 80, width: 1400, height: 320 }, zoom: 1.2 }, { at: d * 0.45, focus: B.ticket.sla, zoom: 1.7 }, { at: d, focus: B.ticket.sla, zoom: 1.75 }]}>
        <Highlight box={B.ticket.sla} from={d * 0.35} pad={6} color={D.yellow} />
      </Slab>
      {/* The deadline marker travels over the closed days to the next working day. */}
      <div style={{ position: "absolute", left, top: 760, display: "flex", gap }}>
        {days.map((day, k) => {
          const show = ramp(f, d * 0.2 + k * 4, d * 0.2 + k * 4 + 14);
          return (
            <div key={day} style={{ width: tile, height: 120, borderRadius: 20, fontFamily: FONT, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 6, opacity: show, transform: `translateY(${(1 - show) * 20}px)`,
              background: off[k] ? "rgba(255,255,255,.04)" : "rgba(61,123,255,.16)", border: `1px solid rgba(255,255,255,${off[k] ? 0.08 : 0.2})` }}>
              <span style={{ fontSize: 34, fontWeight: 800, color: off[k] ? "rgba(255,255,255,.35)" : D.ink }}>{day}</span>
              <span style={{ fontSize: 18, fontWeight: 600, color: off[k] ? D.coral : D.dim }}>{k === 3 ? "Bank holiday" : off[k] ? "Weekend" : "Working day"}</span>
            </div>
          );
        })}
        <div style={{ position: "absolute", top: -26, left: tile / 2 - 13 + jump * 4 * (tile + gap), width: 26, height: 26, borderRadius: "50%",
          background: D.yellow, boxShadow: `0 0 24px ${D.yellow}`, opacity: ramp(f, d * 0.3, d * 0.36),
          transform: `translateY(${-Math.sin(jump * Math.PI) * 60}px)` }} />
      </div>
      {days.map((_, k) => <Sfx key={k} name="tick" at={d * 0.2 + k * 4} volume={0.45} />)}
      <Sfx name="whoosh" at={d * 0.5} volume={0.3} />
      <Sfx name="thud" at={d * 0.78} volume={0.4} />
      <Side n={n} label="Service" title="Keep every promise." accent={["promise"]} sub="Service deadlines count UK working hours and skip bank holidays." d={d} />
    </Stage>
  );
};

// Three real phone screens fanned out in 3D.
export const Mobile: React.FC<S & { n?: string }> = ({ d, n }) => {
  const f = useCurrentFrame();
  const phones = [
    { src: "shots/m-pipeline.png", cx: 760, ry: 28, delay: 0 },
    { src: "shots/m-quote-accepted.png", cx: 1180, ry: 0, delay: 6 },
    { src: "shots/m-ticket.png", cx: 1600, ry: -28, delay: 12 },
  ];
  return (
    <Stage light={0.95} x={62} y={70}>
      <AbsoluteFill style={{ perspective: 2200 }}>
        {phones.map(p => {
          const r = ramp(f, p.delay, p.delay + 30);
          const drift = interpolate(f, [0, d], [0, -24], clamp);
          return <Phone key={p.src} src={p.src} cx={p.cx} cy={560} width={330}
            poses={[{ at: 0, ry: p.ry * 1.6, rx: 10, y: 500, s: 0.9 }, { at: 1, ry: p.ry * 1.6, rx: 10, y: 500 * (1 - r) + drift, s: 0.9 + r * 0.1 }]} />;
        })}
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 110, top: 0, bottom: 0, width: 420, display: "flex", flexDirection: "column", justifyContent: "center", gap: 26 }}>
        {n && <Kicker n={n} label="Mobile" size={26} />}
        <Words text="In your pocket." size={84} align="left" width={420} at={8} gap={4} accent={["pocket"]} until={d} />
        <Words text="Deals, quotes and tickets on your phone." size={30} weight={600} color={D.dim} align="left" width={400} at={20} gap={2} until={d} />
      </div>
    </Stage>
  );
};

// One word per beat over the screen it names, then "One place."
export const Montage: React.FC<S> = ({ d }) => {
  const f = useCurrentFrame();
  const items = [["Sales.", "shots/pipeline-after.png"], ["Quotes.", "shots/quote-accepted.png"], ["Invoices.", "shots/invoice.png"], ["Support.", "shots/ticket.png"]];
  const seg = Math.round((d * 0.7) / items.length);
  const k = Math.floor(f / seg);
  if (k < items.length) {
    const [word, src] = items[k];
    const lf = f - k * seg;
    return (
      <AbsoluteFill style={{ background: D.night }}>
        <Img src={staticFile(src)} style={{ position: "absolute", inset: -40, width: 2000, height: 1160, objectFit: "cover",
          filter: "blur(6px) brightness(.32) saturate(1.2)", transform: `scale(${1.08 + lf * 0.004})` }} />
        <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(4,6,12,.2), rgba(4,6,12,.75))" }} />
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 230, letterSpacing: "-0.05em", color: D.ink,
            transform: `scale(${1.12 - ramp(lf, 0, 10) * 0.12})`, filter: `blur(${(1 - ramp(lf, 0, 6)) * 10}px)` }}>{word}</div>
        </AbsoluteFill>
        <Flash at={0} length={6} strength={0.4} />
        <Sfx name="hit" volume={0.35} />
      </AbsoluteFill>
    );
  }
  return (
    <Stage light={ramp(f, items.length * seg, d)}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <Sequence from={items.length * seg} layout="none">
          <Words text="One place." size={220} gap={6} accent={["place"]} accentColor={D.yellow} />
          <Sfx name="hit" volume={0.55} />
        </Sequence>
      </AbsoluteFill>
    </Stage>
  );
};

// The offer: the logo in light, the price, where to go.
export const Offer: React.FC<S & { vertical?: boolean }> = ({ d, vertical }) => {
  const f = useCurrentFrame();
  const logo = ramp(f, 0, 24);
  const sweep = interpolate(f, [10, 40], [-30, 130], clamp);
  return (
    <Stage light={0.7 + 0.3 * logo} y={vertical ? 40 : 46}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: vertical ? 54 : 36, padding: 80 }}>
        <div style={{ position: "relative", opacity: logo, transform: `scale(${0.9 + logo * 0.1})`, filter: `blur(${(1 - logo) * 10}px)` }}>
          <Img src={staticFile("brand/cae-crm-logo-on-dark.svg")} style={{ height: vertical ? 130 : 110 }} />
          <div style={{ position: "absolute", inset: 0, mixBlendMode: "overlay",
            background: `linear-gradient(105deg, transparent ${sweep - 20}%, rgba(255,255,255,.9) ${sweep}%, transparent ${sweep + 20}%)` }} />
        </div>
        <Words text="14 days free." size={vertical ? 150 : 140} at={18} gap={4} accent={["free"]} accentColor={D.yellow} />
        <Words text="£15 per user a month. No card needed." size={vertical ? 46 : 44} weight={600} color={D.dim} at={30} gap={2} width={vertical ? 900 : 1600} />
        <div style={{ marginTop: 14, padding: vertical ? "30px 66px" : "24px 56px", borderRadius: 999, background: D.blue, fontFamily: FONT,
          fontWeight: 800, fontSize: vertical ? 46 : 38, color: "#fff", boxShadow: `0 0 60px rgba(61,123,255,.55), inset 0 1px 0 rgba(255,255,255,.25)`,
          opacity: ramp(f, 40, 56), transform: `scale(${0.92 + ramp(f, 40, 56) * 0.08})` }}>Start your free trial</div>
        <div style={{ fontFamily: FONT, fontWeight: 600, fontSize: vertical ? 40 : 32, color: D.ink, opacity: ramp(f, 50, 66) }}>cae.collinalitics.co.uk</div>
      </AbsoluteFill>
      <Sfx name="shimmer" at={6} volume={0.5} />
      <Sfx name="pop" at={40} volume={0.5} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: vertical ? 70 : 34, textAlign: "center", fontFamily: FONT,
        fontSize: vertical ? 24 : 18, color: "rgba(255,255,255,.38)", opacity: ramp(f, 50, 66) }}>
        Screens show sample data.
      </div>
    </Stage>
  );
};

// ---- The vertical ad's own scenes -----------------------------------------------------------------------------

export const VHook: React.FC<S> = ({ d }) => (
  <Stage light={0.35} y={100}>
    <AbsoluteFill style={{ justifyContent: "center", padding: "0 90px", gap: 14, flexDirection: "column" }}>
      {["Sales.", "Quotes.", "Invoices.", "Support."].map((w, i) => (
        <Words key={w} text={w} size={150} align="left" at={i * 8} gap={0} until={d} />
      ))}
      <div style={{ height: 30 }} />
      {[0, 8, 16, 24].map(t => <Sfx key={t} name="thud" at={t} volume={0.4} />)}
      <Words text="Four different apps?" size={84} align="left" at={36} gap={4} accent={["Four"]} accentColor={D.coral} until={d} width={900} />
    </AbsoluteFill>
  </Stage>
);

export const VPhone: React.FC<S & { src: string; title: string; accent?: string[]; chip?: string; rise?: boolean; focus?: Box; zoom?: number }> =
  ({ d, src, title, accent = [], chip, rise, focus, zoom = 1.06 }) => {
    const f = useCurrentFrame();
    const r = rise ? ramp(f, 0, 30) : 1;
    return (
      <Stage light={0.95} y={64}>
        <div style={{ position: "absolute", left: 80, right: 80, top: 150 }}>
          <Words text={title} size={92} at={4} gap={4} accent={accent} until={d} width={920} />
        </div>
        <AbsoluteFill style={{ perspective: 2200 }}>
          <Phone src={src} cx={540} cy={1180} width={600}
            shots={[{ at: 0, zoom: 1, focus }, { at: d, zoom, focus }]}
            poses={[{ at: 0, rx: 14, ry: -10, y: 700 * (1 - r), s: 0.94 }, { at: d, rx: 6, ry: 8, y: 700 * (1 - r) - 20, s: 1 }]} />
        </AbsoluteFill>
        {rise && <Sfx name="whoosh" volume={0.45} />}
        {chip && <Chip text={chip} at={d * 0.4} size={34} style={{ left: 0, right: 0, margin: "0 auto", width: "fit-content", bottom: 120 }} />}
      </Stage>
    );
  };

// ---- Timelines ------------------------------------------------------------------------------------------------

type Part = { frames: number; render: (d: number) => React.ReactNode };
const FPS_ = 30;

// Hard cuts between scenes, the way a launch film moves; the scenes handle their own light.
// A voiceover line: the file in public/vo, when it starts and how long it runs (frames).
export type Line = { src: string; at: number; len: number };

// The score is cut into sections: each plays the track from `offset` seconds ahead of film time, so the track's
// drop lands on the reveal and its ending lands on the offer. Offsets differ by whole bars (2s at 120 BPM), so the
// beat never stumbles at a join; joins crossfade over one beat.
export type Score = { src: string; sections: { from: number; offset: number }[] };
const XF = 8;

// Music sits under everything, and dips further while a voice line plays so the words stay clear.
const MUSIC = 0.8, UNDER_VOICE = 0.3, DUCK = 8;
const musicLevel = (f: number, total: number, voice: Line[]) => {
  const duck = voice.reduce((m, l) => Math.max(m, interpolate(f, [l.at - DUCK, l.at, l.at + l.len, l.at + l.len + DUCK * 2], [0, 1, 1, 0], clamp)), 0);
  const edges = interpolate(f, [0, 6, total - 45, total], [0, 1, 1, 0], clamp);
  return edges * (MUSIC - (MUSIC - UNDER_VOICE) * duck);
};

export const Film: React.FC<{ parts: Part[]; music?: string; score?: Score; voice?: Line[] }> = ({ parts, music, score, voice = [] }) => {
  useBrandFont();
  const { durationInFrames } = useVideoConfig();
  let at = 0;
  return (
    <AbsoluteFill style={{ background: D.night }}>
      {parts.map((p, i) => {
        const el = (
          <React.Fragment key={i}>
            <Sequence from={at} durationInFrames={p.frames}>{p.render(p.frames)}</Sequence>
            {/* A breath of air on each cut, landing just as the new shot appears. */}
            {i > 0 && <Sfx name="whoosh" at={at - 12} volume={0.22} />}
          </React.Fragment>
        );
        at += p.frames;
        return el;
      })}
      {music && !score && <Audio src={staticFile(music)} volume={f => musicLevel(f, durationInFrames, voice)} />}
      {score && score.sections.map((sec, k) => {
        const next = score.sections[k + 1];
        const start = Math.max(0, sec.from - XF), end = next ? next.from + XF : durationInFrames;
        return (
          <Sequence key={k} from={start} durationInFrames={end - start} layout="none">
            <Audio src={staticFile(score.src)} trimBefore={Math.round(start + sec.offset * FPS_)}
              volume={l => { const f = l + start;
                const fade = Math.min(k ? interpolate(f, [sec.from - XF, sec.from + XF], [0, 1], clamp) : 1,
                  next ? interpolate(f, [next.from - XF, next.from + XF], [1, 0], clamp) : 1);
                return fade * musicLevel(f, durationInFrames, voice); }} />
          </Sequence>
        );
      })}
      {voice.map(l => (
        <Sequence key={l.src} from={l.at} layout="none"><Audio src={staticFile(l.src)} volume={1} /></Sequence>
      ))}
    </AbsoluteFill>
  );
};

export const LAUNCH_60: Part[] = [
  { frames: 180, render: d => <ColdOpen d={d} /> },
  { frames: 90, render: d => <Turn d={d} /> },
  { frames: 180, render: d => <Reveal d={d} /> },
  { frames: 54, render: d => <ChapterCard d={d} n="01" label="Sales" title="Win more deals." accent={["deals"]} /> },
  { frames: 126, render: d => <Enquiry d={d} /> },
  { frames: 150, render: d => <Pipeline d={d} /> },
  { frames: 54, render: d => <ChapterCard d={d} n="02" label="Money" title="Get paid faster." accent={["faster"]} /> },
  { frames: 126, render: d => <Quote d={d} /> },
  { frames: 126, render: d => <Invoice d={d} /> },
  { frames: 54, render: d => <ChapterCard d={d} n="03" label="Service" title="Keep every promise." accent={["promise"]} /> },
  { frames: 186, render: d => <Service d={d} /> },
  { frames: 180, render: d => <Mobile d={d} n="04" /> },
  { frames: 150, render: d => <Montage d={d} /> },
  { frames: 144, render: d => <Offer d={d} /> },
];

export const LAUNCH_30: Part[] = [
  { frames: 90, render: d => <ColdOpen d={d} /> },
  { frames: 135, render: d => <Reveal d={d} /> },
  { frames: 135, render: d => <Pipeline d={d} n="01" /> },
  { frames: 105, render: d => <Quote d={d} n="02" /> },
  { frames: 105, render: d => <Invoice d={d} n="02" /> },
  { frames: 120, render: d => <Service d={d} n="03" /> },
  { frames: 90, render: d => <Mobile d={d} n="04" /> },
  { frames: 120, render: d => <Offer d={d} /> },
];

const MB = B as Record<string, Record<string, Box>>;
export const LAUNCH_15V: Part[] = [
  { frames: 75, render: d => <VHook d={d} /> },
  { frames: 75, render: d => <VPhone d={d} rise src="shots/m-pipeline.png" title="Meet CAE CRM." accent={["CRM"]} /> },
  { frames: 70, render: d => <VPhone d={d} src="shots/m-pipeline.png" title="Deals that move." accent={["move"]} focus={MB["m-pipeline"].card} zoom={1.25} chip="Your pipeline, anywhere" /> },
  { frames: 70, render: d => <VPhone d={d} src="shots/m-quote-accepted.png" title="Quotes signed online." accent={["signed"]} chip="Accepted and signed" /> },
  { frames: 70, render: d => <VPhone d={d} src="shots/m-ticket.png" title="Deadlines that skip bank holidays." accent={["bank", "holidays"]} focus={MB["m-ticket"].sla} zoom={1.3} /> },
  { frames: 90, render: d => <Offer d={d} vertical /> },
];

export const frames = (parts: Part[]) => parts.reduce((s, p) => s + p.frames, 0);

// ---- Sound: Imogen's voiceover and the score, placed per cut (frames at 30fps) ----------------------------------

const vo = (n: number, at: number, len: number): Line => ({ src: `vo/line-${String(n).padStart(2, "0")}.mp3`, at, len });
const SCORE = "music/launch-take-a.mp3";

export const SOUND_60 = {
  voice: [vo(1, 30, 100), vo(2, 186, 83), vo(3, 352, 133), vo(4, 512, 145), vo(5, 842, 203), vo(6, 1150, 152), vo(7, 1345, 66), vo(8, 1672, 100)],
  score: { src: SCORE, sections: [{ from: 0, offset: 4.5 }, { from: 1350, offset: 0.5 }] },
};
export const SOUND_30 = {
  voice: [vo(3, 150, 133), vo(9, 290, 56), vo(10, 372, 116), vo(6, 578, 152), vo(8, 790, 100)],
  score: { src: SCORE, sections: [{ from: 0, offset: 11.13 }, { from: 660, offset: 29.13 }] },
};
export const SOUND_15V = {
  voice: [vo(3, 82, 133), vo(8, 349, 100)],
  score: { src: SCORE, sections: [{ from: 0, offset: 13.53 }, { from: 270, offset: 43.53 }] },
};
