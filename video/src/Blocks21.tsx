// The 21st.dev Video blocks (src/video/*), set up in CAE CRM's colours and typeface.
// Each block reads its own frame, so a negative Sequence start skips its build-up when a slot is short.
import React from "react";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Component as SplitFlap } from "./video/split-flap-type/split-flap-type";
import { Component as TiledReveal } from "./video/puzzle-grid-reveal/puzzle-grid-reveal";
import { Component as DotField } from "./video/dot-field-drops/dot-field-drops";
import { Component as Seal } from "./video/rotating-seal-badge/rotating-seal-badge";
import { BrandBackground, C } from "./theme";

const FONT_NAME = "Plus Jakarta Sans";

// "ONE CRM FOR / UK BUSINESS" flaps into place over about 3.7 seconds.
export const FlapTitle: React.FC<{ text?: string }> = ({ text = "One CRM for UK business" }) => (
  <SplitFlap text={text} primary={C.yellow} secondary={C.coralBright} color={C.white} background={C.blue}
    fontFamily={FONT_NAME} seed={53} />
);

// The dashboard dropped in as nine tiles that weld into one picture.
export const TiledDashboard: React.FC<{ caption: string }> = ({ caption }) => (
  <TiledReveal image={staticFile("shots/dashboard.png")} focus="top" logo="" caption={caption}
    color={C.white} accent={C.yellow} secondary={C.coralBright} background={C.blue} fontFamily={FONT_NAME} seed={7} />
);

// Rippling dots on brand blue, used behind text cards.
export const DotBackdrop: React.FC = () => (
  <DotField headline="" color={C.white} primary={C.yellow} secondary={C.coralBright} background={C.blue}
    fontFamily={FONT_NAME} seed={12} spacing={1} grain={false} />
);

// The closing seal on plain brand blue (the dot field fights the ring text): offer on the ring, logo and button inside, web address underneath.
export const SealEndCard: React.FC<{ skip?: number }> = ({ skip = 0 }) => (
  <AbsoluteFill>
    <BrandBackground tone="blue" />
    <Sequence from={-skip}>
      <Seal logo={staticFile("brand/cae-crm-logo-on-dark.svg")}
        text="14 DAYS FREE · £15 PER USER A MONTH · NO CARD NEEDED ·"
        action="Start free trial" destination="cae.collinalitics.co.uk"
        primary={C.yellow} secondary={C.coralBright} color={C.white} background="transparent" fontFamily={FONT_NAME} />
    </Sequence>
  </AbsoluteFill>
);
