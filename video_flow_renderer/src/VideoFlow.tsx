import React from "react";
import {Audio} from "@remotion/media";
import {
  AbsoluteFill,
  Composition,
  Easing,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {ProceduralMotionScene, ProceduralScene} from "./ProceduralMotionScene";

type Palette = {background: string; surface: string; text: string; muted: string; accents: string[]};

type Scene = {
  id: string;
  type: string;
  title: string;
  body: string;
  narration: string;
  domain?: string;
  visualVariant?: string;
  accent?: number;
  durationSeconds: number;
  audioFile?: string | null;
  visualBeats?: Array<{startRatio: number}>;
  motionPlan?: any;
};

type VideoFlowProps = {
  title: string;
  mode: "summary" | "full";
  fps: number;
  width: number;
  height: number;
  theme: string;
  visualLanguage?: {
    system: string;
    renderer: string;
    palette: Palette;
  };
  scenes: Scene[];
};

const INK = "#171717";
const PAPER = "#fbfaf5";
const MUTED = "#696761";
const CARD = "rgba(255,255,255,0.92)";
const DEFAULT_ACCENTS = ["#ff8a1f", "#ffd65a", "#8bd7e6", "#89c95d", "#ef4b43"];

const defaultProps: VideoFlowProps = {
  title: "Video Flow",
  mode: "summary",
  fps: 24,
  width: 1920,
  height: 1080,
  theme: "voice-flow",
  visualLanguage: {
    system: "notebook-sketch",
    renderer: "notebook-sketch-v1",
    palette: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: DEFAULT_ACCENTS},
  },
  scenes: [
    {
      id: "scene-001",
      type: "hook",
      title: "Ideas that move like ink",
      body: "Turn selected text and documents into a clear visual explanation.",
      narration: "Turn selected text and documents into a clear visual explanation.",
      durationSeconds: 5,
    },
  ],
};

const paletteEditions: Record<string, Palette> = {
  "voice-flow": {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: DEFAULT_ACCENTS},
  paper: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: DEFAULT_ACCENTS},
  midnight: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#3448a5", "#7f73d8", "#8bd7e6", "#ffd65a", "#ff8a1f"]},
  neon: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#f04fb6", "#42d7c8", "#8b6de9", "#ddeb48", "#ff8a1f"]},
  ocean: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#3aaed8", "#79d4d0", "#4f76c7", "#89c95d", "#ffd65a"]},
  forest: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#6fba62", "#9fd07f", "#d7a94d", "#79c9c3", "#ff8a1f"]},
  sunset: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#ff7b3f", "#ffbd55", "#ef6f87", "#8bd7e6", "#89c95d"]},
  mono: {background: PAPER, surface: CARD, text: INK, muted: MUTED, accents: ["#171717", "#5b5b5b", "#919191", "#c3c3c3", "#ededed"]},
};

const clamp = {extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const};
const at = (duration: number, ratio: number) => Math.max(1, Math.round(duration * ratio));
const beatAt = (scene: Scene, duration: number, index: number, fallback: number) => {
  return at(duration, scene.visualBeats?.[index]?.startRatio ?? fallback);
};

const reveal = (frame: number, start: number, duration: number) =>
  interpolate(frame, [start, start + duration], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const textLines = (body: string, limit = 4) => {
  const normalized = body.replace(/\s+/g, " ").trim();
  if (!normalized) return ["A clear visual explanation"];
  const sentences = normalized.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
  if (sentences.length > 1) return sentences.slice(0, limit);
  const words = normalized.split(" ");
  if (words.length < 15 || limit === 1) return [normalized];
  const size = Math.ceil(words.length / Math.min(limit, Math.ceil(words.length / 10)));
  const lines: string[] = [];
  for (let index = 0; index < words.length && lines.length < limit; index += size) {
    lines.push(words.slice(index, index + size).join(" "));
  }
  return lines;
};

const fitTitle = (text: string, maximum = 94) => Math.max(52, Math.min(maximum, 118 - text.length * 0.55));
const fitBody = (text: string, maximum = 36) => Math.max(25, Math.min(maximum, 47 - text.length * 0.08));

const PaperBackground: React.FC<{palette: Palette}> = ({palette}) => (
  <AbsoluteFill style={{backgroundColor: palette.background || PAPER, overflow: "hidden"}}>
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundImage: [
          "linear-gradient(rgba(23,23,23,.035) 1px, transparent 1px)",
          "linear-gradient(90deg, rgba(23,23,23,.035) 1px, transparent 1px)",
          "radial-gradient(circle, rgba(23,23,23,.06) 0 1px, transparent 1.5px)",
        ].join(","),
        backgroundSize: "48px 48px, 48px 48px, 19px 23px",
        opacity: 0.88,
      }}
    />
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `radial-gradient(circle at 16% 10%, ${palette.accents[1]}1f, transparent 26%), radial-gradient(circle at 86% 74%, ${palette.accents[2]}18, transparent 30%)`,
      }}
    />
  </AbsoluteFill>
);

const InkPath: React.FC<{
  d: string;
  draw?: number;
  stroke?: string;
  width?: number;
  fill?: string;
  opacity?: number;
  dashed?: boolean;
}> = ({d, draw = 1, stroke = INK, width = 5, fill = "none", opacity = 1, dashed = false}) => (
  <>
    <path
      d={d}
      pathLength={1}
      stroke={INK}
      strokeWidth={width + 2}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={dashed ? "0.024 0.03" : "1"}
      strokeDashoffset={1 - draw}
      fill={fill}
      opacity={opacity * 0.12}
      transform="translate(2 2)"
    />
    <path
      d={d}
      pathLength={1}
      stroke={stroke}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={dashed ? "0.024 0.03" : "1"}
      strokeDashoffset={1 - draw}
      fill={fill}
      opacity={opacity}
    />
  </>
);

const BulbDoodle: React.FC<{draw: number; colors: string[]}> = ({draw, colors}) => (
  <svg viewBox="0 0 180 210" width="180" height="210">
    <path
      d="M58 126 C25 91 39 32 91 28 C142 24 164 81 129 121 C117 134 111 144 109 156 L70 156 C68 144 66 136 58 126 Z"
      fill={colors[1]}
      opacity={0.62 * draw}
    />
    <InkPath d="M58 126 C25 91 39 32 91 28 C142 24 164 81 129 121 C117 134 111 144 109 156 L70 156 C68 144 66 136 58 126 Z" draw={draw} />
    <InkPath d="M75 158 L108 158 M76 171 L105 171 M82 184 L99 184" draw={draw} />
    <InkPath d="M73 104 C79 87 99 86 106 101 C99 111 94 124 91 153 M83 102 C90 112 92 130 92 153" draw={draw} width={4} />
    <InkPath d="M0 72 L24 76 M31 19 L47 39 M89 0 L90 21 M143 16 L129 40 M168 65 L145 72" draw={draw} width={4} />
  </svg>
);

const ChartDoodle: React.FC<{draw: number; colors: string[]}> = ({draw, colors}) => (
  <svg viewBox="0 0 250 190" width="250" height="190">
    <InkPath d="M28 25 L28 158 L227 158" draw={draw} />
    {[45, 76, 108, 132].map((height, index) => (
      <g key={height} opacity={draw}>
        <rect x={50 + index * 43} y={158 - height * draw} width="29" height={height * draw} fill={colors[index % colors.length]} opacity="0.72" />
        <rect x={50 + index * 43} y={158 - height * draw} width="29" height={height * draw} fill="none" stroke={INK} strokeWidth="4" />
      </g>
    ))}
    <InkPath d="M46 128 C88 119 104 98 136 91 C168 83 184 54 221 35 M203 33 L222 34 L217 53" draw={draw} />
  </svg>
);

const domainFromScene = (scene: Scene): string => {
  if (scene.domain) return scene.domain;
  const text = `${scene.title} ${scene.body}`.toLowerCase();
  const profiles: Array<[string, RegExp]> = [
    ["food", /recipe|cook|kitchen|ingredient|food/],
    ["business", /business|market|revenue|customer|sales|finance/],
    ["gaming", /game|player|level|quest|gaming/],
    ["science", /science|research|experiment|cell|molecule|laboratory/],
    ["technology", /software|technology|data|network|code|api|ai/],
    ["health", /health|medical|patient|doctor|therapy/],
    ["nature", /climate|nature|environment|plant|wildlife/],
    ["security", /security|privacy|legal|audit|threat|risk/],
    ["study", /study|lesson|education|book|history|guide/],
  ];
  return profiles.find(([, pattern]) => pattern.test(text))?.[0] ?? "general";
};

const DomainDoodle: React.FC<{scene: Scene; draw: number; colors: string[]; size?: number}> = ({
  scene,
  draw,
  colors,
  size = 250,
}) => {
  const domain = domainFromScene(scene);
  const common = {draw, stroke: INK, width: 6};
  return (
    <svg viewBox="0 0 260 240" width={size} height={size * 0.92}>
      {domain === "study" ? (
        <>
          <path d="M28 50 Q82 31 126 58 L126 197 Q80 170 28 188 Z M126 58 Q178 30 232 50 L232 188 Q177 170 126 197 Z" fill={colors[1]} opacity={draw * 0.42} />
          <InkPath d="M28 50 Q82 31 126 58 L126 197 Q80 170 28 188 Z M126 58 Q178 30 232 50 L232 188 Q177 170 126 197 Z M126 58 L126 197" {...common} />
          <InkPath d="M48 79 Q84 69 108 80 M48 108 Q83 98 108 109 M151 79 Q187 67 214 79 M151 108 Q188 96 214 108" {...common} width={4} />
        </>
      ) : null}
      {domain === "gaming" ? (
        <>
          <path d="M45 88 Q70 47 112 69 L148 69 Q191 48 215 88 L230 159 Q235 198 202 203 Q179 206 157 164 L103 164 Q82 205 58 203 Q25 199 31 160 Z" fill={colors[2]} opacity={draw * 0.5} />
          <InkPath d="M45 88 Q70 47 112 69 L148 69 Q191 48 215 88 L230 159 Q235 198 202 203 Q179 206 157 164 L103 164 Q82 205 58 203 Q25 199 31 160 Z M73 116 L73 154 M54 135 L92 135" {...common} />
          <circle cx="181" cy="120" r="10" fill={colors[0]} opacity={draw} />
          <circle cx="203" cy="145" r="10" fill={colors[3]} opacity={draw} />
        </>
      ) : null}
      {domain === "science" ? (
        <>
          <path d="M102 31 L158 31 M115 31 L115 98 L61 190 Q50 210 76 215 L184 215 Q210 210 199 190 L145 98 L145 31" fill={colors[2]} opacity={draw * 0.38} />
          <InkPath d="M102 31 L158 31 M115 31 L115 98 L61 190 Q50 210 76 215 L184 215 Q210 210 199 190 L145 98 L145 31 M83 169 Q129 143 177 169" {...common} />
          <circle cx="111" cy="177" r="9" fill={colors[0]} opacity={draw} />
          <circle cx="149" cy="188" r="7" fill={colors[3]} opacity={draw} />
        </>
      ) : null}
      {domain === "technology" ? (
        <>
          <rect x="65" y="45" width="130" height="130" rx="22" fill={colors[2]} opacity={draw * 0.38} />
          <InkPath d="M65 45 L195 45 L195 175 L65 175 Z M95 76 L165 76 L165 145 L95 145 Z M33 75 L65 75 M33 110 L65 110 M33 145 L65 145 M195 75 L227 75 M195 110 L227 110 M195 145 L227 145 M96 20 L96 45 M130 20 L130 45 M164 20 L164 45 M96 175 L96 207 M130 175 L130 207 M164 175 L164 207" {...common} width={5} />
        </>
      ) : null}
      {domain === "health" ? (
        <>
          <path d="M130 207 C38 157 40 78 85 65 Q119 55 130 89 Q143 55 178 65 C224 79 222 158 130 207 Z" fill={colors[4]} opacity={draw * 0.4} />
          <InkPath d="M130 207 C38 157 40 78 85 65 Q119 55 130 89 Q143 55 178 65 C224 79 222 158 130 207 Z" {...common} />
          <InkPath d="M55 131 L96 131 L113 102 L137 164 L157 130 L207 130" {...common} stroke={colors[0]} />
        </>
      ) : null}
      {domain === "food" ? (
        <>
          <path d="M45 112 Q130 158 215 112 Q201 201 130 208 Q59 201 45 112 Z" fill={colors[1]} opacity={draw * 0.48} />
          <InkPath d="M45 112 Q130 158 215 112 Q201 201 130 208 Q59 201 45 112 Z M84 88 Q65 61 87 35 M130 86 Q108 53 132 27 M174 89 Q156 62 178 39" {...common} />
        </>
      ) : null}
      {domain === "nature" ? (
        <>
          <path d="M45 181 Q45 62 210 43 Q207 184 75 198 Z" fill={colors[3]} opacity={draw * 0.44} />
          <InkPath d="M45 181 Q45 62 210 43 Q207 184 75 198 Z M61 181 Q118 127 190 67 M104 143 L93 94 M142 111 L164 139" {...common} />
        </>
      ) : null}
      {domain === "security" ? (
        <>
          <path d="M130 24 Q174 51 213 54 L205 139 Q196 190 130 218 Q64 190 55 139 L47 54 Q88 50 130 24 Z" fill={colors[2]} opacity={draw * 0.4} />
          <InkPath d="M130 24 Q174 51 213 54 L205 139 Q196 190 130 218 Q64 190 55 139 L47 54 Q88 50 130 24 Z M91 124 L118 151 L171 92" {...common} />
        </>
      ) : null}
      {domain === "business" ? <ChartDoodle draw={draw} colors={colors} /> : null}
      {domain === "general" ? <BulbDoodle draw={draw} colors={colors} /> : null}
    </svg>
  );
};

const SceneShell: React.FC<{
  scene: Scene;
  duration: number;
  palette: Palette;
  children: React.ReactNode;
}> = ({scene, duration, palette, children}) => {
  const frame = useCurrentFrame();
  const enter = reveal(frame, 0, at(duration, 0.08));
  const exit = interpolate(frame, [Math.max(1, duration - at(duration, 0.06)), duration], [1, 0], clamp);
  const drift = Math.sin(frame / Math.max(36, duration / 5)) * 1.5;
  return (
    <AbsoluteFill
      style={{
        color: palette.text,
        fontFamily: '"Segoe UI", Arial, sans-serif',
        opacity: enter * exit,
        transform: `translateY(${(1 - enter) * 10 + drift}px)`,
      }}
    >
      <PaperBackground palette={palette} />
      {children}
      {scene.audioFile ? <Audio src={staticFile(scene.audioFile)} /> : null}
    </AbsoluteFill>
  );
};

const HookScene: React.FC<{
  scene: Scene;
  palette: Palette;
  duration: number;
  closing?: boolean;
}> = ({scene, palette, duration, closing}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const titleIn = reveal(frame, at(duration, 0.04), at(duration, 0.17));
  const draw = reveal(frame, at(duration, 0.12), at(duration, 0.45));
  const pop = spring({frame: frame - at(duration, 0.1), fps, config: {damping: 14, stiffness: 115}});
  const body = textLines(scene.body, 2).join(" ");
  return (
    <div style={{position: "absolute", inset: "120px 105px 85px", display: "flex", alignItems: "center", justifyContent: "center"}}>
      <div style={{position: "absolute", left: 45, top: 130, transform: `rotate(-8deg) scale(${0.88 + pop * 0.12})`}}>
        <BulbDoodle draw={draw} colors={palette.accents} />
      </div>
      <div style={{position: "absolute", right: 45, bottom: 62, transform: `rotate(5deg) scale(${0.88 + pop * 0.12})`}}>
        <DomainDoodle scene={scene} draw={draw} colors={palette.accents} />
      </div>
      <div style={{textAlign: "center", width: 1320, opacity: titleIn, transform: `scale(${0.96 + titleIn * 0.04})`}}>
        <div style={{fontSize: fitTitle(scene.title, 112), lineHeight: 0.98, fontWeight: 930, letterSpacing: -4}}>
          {scene.title}
        </div>
        <div style={{fontSize: fitBody(body, 35), lineHeight: 1.38, color: palette.muted, margin: "32px auto 0", maxWidth: 1050}}>
          {body}
        </div>
        <svg width="570" height="54" viewBox="0 0 570 54" style={{marginTop: 18}}>
          <InkPath d="M18 31 C121 18 197 34 286 24 C384 13 446 34 552 20" draw={draw} stroke={palette.accents[0]} width={9} />
        </svg>
      </div>
    </div>
  );
};

const ProcessScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const items = textLines(scene.body, 4);
  const {fps} = useVideoConfig();
  const connector = reveal(frame, at(duration, 0.2), at(duration, 0.48));
  return (
    <div style={{position: "absolute", inset: "105px 95px 85px"}}>
      <div style={{fontSize: fitTitle(scene.title, 66), fontWeight: 920, margin: "10px 15px 42px", letterSpacing: -2}}>
        {scene.title}
      </div>
      <svg width="1730" height="530" viewBox="0 0 1730 530" style={{position: "absolute", left: 0, top: 120}}>
        {items.slice(0, -1).map((_, index) => (
          <InkPath
            key={index}
            d={`M${410 + index * 425} 165 C${430 + index * 425} 145 ${450 + index * 425} 145 ${475 + index * 425} 165`}
            draw={connector}
            stroke={palette.accents[0]}
            dashed
          />
        ))}
        <InkPath
          d="M1550 330 C1460 480 1200 425 1040 474 C810 544 590 425 340 475"
          draw={reveal(frame, at(duration, 0.48), at(duration, 0.3))}
          stroke={palette.accents[0]}
          dashed
        />
      </svg>
      <div style={{display: "grid", gridTemplateColumns: `repeat(${items.length}, 1fr)`, gap: 28, marginTop: 70}}>
        {items.map((item, index) => {
          const itemStart = beatAt(scene, duration, index, 0.08 + index * (0.5 / Math.max(1, items.length)));
          const enter = reveal(frame, itemStart, at(duration, 0.14));
          const settle = spring({frame: frame - itemStart, fps, config: {damping: 18, stiffness: 120}});
          return (
            <div
              key={item}
              style={{
                height: 270,
                background: palette.surface,
                border: "2px solid rgba(23,23,23,.13)",
                borderRadius: 25,
                padding: "30px 31px",
                boxSizing: "border-box",
                boxShadow: "0 15px 24px rgba(23,23,23,.07)",
                opacity: enter,
                transform: `translateY(${(1 - settle) * 30}px) rotate(${index % 2 ? 0.8 : -0.8}deg)`,
              }}
            >
              <div style={{width: 52, height: 11, borderRadius: 99, background: palette.accents[index % palette.accents.length], border: `2px solid ${INK}`}} />
              <div style={{fontSize: fitBody(item, 31), lineHeight: 1.27, fontWeight: 760, marginTop: 28}}>{item}</div>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", left: 100, bottom: 30, transform: "scale(.78) rotate(-7deg)"}}>
        <BulbDoodle draw={reveal(frame, at(duration, 0.1), at(duration, 0.48))} colors={palette.accents} />
      </div>
      <div style={{position: "absolute", right: 110, bottom: 22, transform: "scale(.82) rotate(5deg)"}}>
        <DomainDoodle scene={scene} draw={reveal(frame, at(duration, 0.16), at(duration, 0.48))} colors={palette.accents} />
      </div>
    </div>
  );
};

const MetricScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const number = scene.body.match(/\b\d+(?:[.,]\d+)?(?:%|x|×)?\b/i)?.[0] ?? "1 idea";
  const {fps} = useVideoConfig();
  const pop = spring({frame: frame - at(duration, 0.08), fps, config: {damping: 13, stiffness: 105}});
  const draw = reveal(frame, at(duration, 0.14), at(duration, 0.5));
  const copy = textLines(scene.body, 2).join(" ");
  return (
    <div style={{position: "absolute", inset: "120px 100px 90px", textAlign: "center"}}>
      <div style={{fontSize: 29, fontWeight: 850, color: palette.muted, letterSpacing: 3, textTransform: "uppercase", marginTop: 40}}>
        {scene.title}
      </div>
      <div style={{position: "relative", display: "inline-block", marginTop: 14, transform: `scale(${0.88 + pop * 0.12})`}}>
        <div style={{position: "absolute", left: 21, top: 19, fontSize: 270, lineHeight: 1, fontWeight: 950, color: palette.accents[0]}}>
          {number}
        </div>
        <div style={{position: "relative", fontSize: 270, lineHeight: 1, fontWeight: 950, color: PAPER, WebkitTextStroke: `7px ${INK}`}}>
          {number}
        </div>
      </div>
      <div style={{fontSize: fitBody(copy, 40), fontWeight: 720, lineHeight: 1.3, maxWidth: 1160, margin: "12px auto 0"}}>
        {copy}
      </div>
      <div style={{position: "absolute", left: 55, top: 120, transform: "rotate(-7deg)"}}>
        <BulbDoodle draw={draw} colors={palette.accents} />
      </div>
      <div style={{position: "absolute", right: 40, top: 100, transform: "rotate(5deg)"}}>
        <ChartDoodle draw={draw} colors={palette.accents} />
      </div>
      <svg width="900" height="120" viewBox="0 0 900 120" style={{position: "absolute", left: 410, bottom: 45}}>
        <InkPath d="M20 72 C104 37 151 100 226 60 C309 15 374 104 457 61 C535 20 596 98 674 58 C742 24 807 74 878 35" draw={draw} stroke={palette.accents[1]} width={12} />
      </svg>
    </div>
  );
};

const ComparisonScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const lines = textLines(scene.body, 4);
  const midpoint = Math.max(1, Math.ceil(lines.length / 2));
  const groups = [lines.slice(0, midpoint), lines.slice(midpoint)];
  if (!groups[1].length) groups[1] = ["A clearer visual story", "One idea enters. One idea lands."];
  const draw = reveal(frame, at(duration, 0.18), at(duration, 0.52));
  return (
    <div style={{position: "absolute", inset: "112px 86px 85px"}}>
      <div style={{fontSize: fitTitle(scene.title, 64), fontWeight: 920, margin: "0 30px 34px", letterSpacing: -2}}>
        {scene.title}
      </div>
      <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 34}}>
        {groups.map((group, column) => {
          const enter = reveal(frame, at(duration, 0.06 + column * 0.18), at(duration, 0.2));
          return (
            <div
              key={column}
              style={{
                height: 640,
                borderRadius: 34,
                background: column ? palette.surface : "rgba(238,238,238,.72)",
                border: "2px solid rgba(23,23,23,.12)",
                padding: "42px 48px",
                boxSizing: "border-box",
                opacity: enter,
                transform: `translateX(${(1 - enter) * (column ? 45 : -45)}px)`,
              }}
            >
              <div style={{fontSize: 76, lineHeight: 1, color: column ? palette.accents[3] : palette.accents[4], fontWeight: 350}}>
                {column ? "✓" : "×"}
              </div>
              <div style={{position: "absolute", marginLeft: 245, marginTop: -46, transform: "scale(.82)"}}>
                <DomainDoodle scene={scene} draw={draw} colors={palette.accents} />
              </div>
              <div style={{marginTop: 258}}>
                {group.map((line, index) => (
                  <div
                    key={line}
                    style={{
                      fontSize: fitBody(line, 31),
                      lineHeight: 1.28,
                      fontWeight: index ? 560 : 800,
                      color: index ? palette.muted : palette.text,
                      padding: "13px 0",
                      borderBottom: "1px solid rgba(23,23,23,.08)",
                    }}
                  >
                    {line}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const QuoteScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const border = reveal(frame, at(duration, 0.03), at(duration, 0.42));
  const textIn = reveal(frame, at(duration, 0.1), at(duration, 0.2));
  const draw = reveal(frame, at(duration, 0.12), at(duration, 0.5));
  const quote = textLines(scene.body, 2).join(" ");
  const words = quote.split(" ");
  const ranked = [...words].sort((a, b) => b.replace(/\W/g, "").length - a.replace(/\W/g, "").length).slice(0, 2).map((word) => word.replace(/\W/g, "").toLowerCase());
  return (
    <div style={{position: "absolute", inset: 0}}>
      <svg width="1920" height="1080" style={{position: "absolute", inset: 0}}>
        <InkPath d="M250 190 C591 176 929 190 1262 181 C1460 176 1610 192 1666 223 L1668 779 C1614 825 1392 813 1199 818 C812 825 537 810 248 821 Z" draw={border} width={6} />
        <InkPath d="M1658 227 C1694 316 1687 611 1668 779 M250 819 C651 833 1106 817 1451 823" draw={border} stroke={palette.accents[0]} width={10} />
      </svg>
      <div style={{position: "absolute", left: 350, right: 350, top: 300, textAlign: "center", fontSize: fitTitle(quote, 70), lineHeight: 1.28, letterSpacing: -1.5, opacity: textIn}}>
        “
        {words.map((word, index) => {
          const key = word.replace(/\W/g, "").toLowerCase();
          const highlighted = ranked.includes(key);
          return (
            <React.Fragment key={`${word}-${index}`}>
              <span style={{position: "relative", display: "inline-block", zIndex: 1}}>
                {highlighted ? (
                  <span
                    style={{
                      position: "absolute",
                      left: -5,
                      right: -5,
                      bottom: 2,
                      height: "58%",
                      background: palette.accents[1],
                      opacity: 0.62,
                      transformOrigin: "left",
                      transform: `scaleX(${reveal(frame, at(duration, 0.3 + ranked.indexOf(key) * 0.16), at(duration, 0.14))}) rotate(-1deg)`,
                      zIndex: -1,
                    }}
                  />
                ) : null}
                {word}
              </span>
              {index < words.length - 1 ? " " : ""}
            </React.Fragment>
          );
        })}
        ”
      </div>
      <div style={{position: "absolute", left: 165, bottom: 86, transform: "scale(.74) rotate(-5deg)"}}>
        <DomainDoodle scene={scene} draw={draw} colors={palette.accents} />
      </div>
      <div style={{position: "absolute", right: 150, top: 120, transform: "scale(.82) rotate(6deg)"}}>
        <BulbDoodle draw={draw} colors={palette.accents} />
      </div>
    </div>
  );
};

const TimelineScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const items = textLines(scene.body, 5);
  const line = reveal(frame, at(duration, 0.06), at(duration, 0.72));
  return (
    <div style={{position: "absolute", inset: "120px 105px 90px"}}>
      <div style={{fontSize: fitTitle(scene.title, 66), fontWeight: 920, letterSpacing: -2}}>{scene.title}</div>
      <div style={{position: "absolute", left: 60, right: 60, top: 410, height: 8, borderRadius: 9, background: "rgba(23,23,23,.09)"}}>
        <div style={{height: "100%", width: `${line * 100}%`, background: palette.accents[0], borderRadius: 9}} />
      </div>
      <div style={{position: "absolute", left: 30, right: 30, top: 355, display: "flex", justifyContent: "space-between"}}>
        {items.map((item, index) => {
          const enter = reveal(frame, beatAt(scene, duration, index, 0.12 + index * (0.58 / Math.max(1, items.length))), at(duration, 0.16));
          return (
            <div key={item} style={{width: 285, textAlign: "center", opacity: enter, transform: `translateY(${(1 - enter) * 22}px)`}}>
              <div style={{width: 56, height: 56, margin: "0 auto 34px", borderRadius: 99, background: palette.accents[index % palette.accents.length], border: `6px solid ${INK}`, display: "grid", placeItems: "center", fontWeight: 900}}>
                <span style={{width: 16, height: 16, borderRadius: 99, background: PAPER, border: `2px solid ${INK}`}} />
              </div>
              <div style={{fontSize: fitBody(item, 29), lineHeight: 1.27, fontWeight: 720}}>{item}</div>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", right: 60, bottom: 5, transform: "scale(.8) rotate(4deg)"}}>
        <ChartDoodle draw={reveal(frame, at(duration, 0.18), at(duration, 0.5))} colors={palette.accents} />
      </div>
    </div>
  );
};

const GridScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const items = textLines(scene.body, 4);
  const draw = reveal(frame, at(duration, 0.14), at(duration, 0.52));
  return (
    <div style={{position: "absolute", inset: "112px 105px 88px"}}>
      <div style={{fontSize: fitTitle(scene.title, 68), fontWeight: 920, letterSpacing: -2, maxWidth: 1320}}>{scene.title}</div>
      <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, width: 1280, marginTop: 46}}>
        {items.map((item, index) => {
          const enter = reveal(frame, beatAt(scene, duration, index, 0.07 + index * (0.52 / Math.max(1, items.length))), at(duration, 0.16));
          return (
            <div
              key={item}
              style={{
                minHeight: 205,
                padding: "28px 34px",
                boxSizing: "border-box",
                borderRadius: 24,
                background: palette.surface,
                border: "2px solid rgba(23,23,23,.12)",
                boxShadow: "0 14px 22px rgba(23,23,23,.065)",
                opacity: enter,
                transform: `translateY(${(1 - enter) * 25}px) rotate(${index % 2 ? 0.5 : -0.5}deg)`,
              }}
            >
              <div style={{display: "flex", gap: 18, alignItems: "flex-start"}}>
                <span style={{width: 24, height: 24, flex: "0 0 auto", marginTop: 6, borderRadius: 8, background: palette.accents[index % palette.accents.length], border: `3px solid ${INK}`}} />
                <span style={{fontSize: fitBody(item, 31), lineHeight: 1.28, fontWeight: 700}}>{item}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{position: "absolute", right: -5, top: 175, transform: "scale(1.12) rotate(3deg)"}}>
        <DomainDoodle scene={scene} draw={draw} colors={palette.accents} />
      </div>
      <svg width="560" height="80" viewBox="0 0 560 80" style={{position: "absolute", right: 45, bottom: 95}}>
        <InkPath d="M8 50 C112 24 193 66 281 42 C370 18 449 60 550 27" draw={draw} stroke={palette.accents[0]} width={9} />
      </svg>
    </div>
  );
};

const StatementScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const title = reveal(frame, at(duration, 0.05), at(duration, 0.2));
  const copy = reveal(frame, at(duration, 0.22), at(duration, 0.25));
  const draw = reveal(frame, at(duration, 0.12), at(duration, 0.56));
  return (
    <div style={{position: "absolute", inset: "110px 120px 90px", display: "grid", gridTemplateColumns: "1.3fr .7fr", alignItems: "center", gap: 65}}>
      <div>
        <div style={{fontSize: fitTitle(scene.title, 82), lineHeight: 1.05, fontWeight: 930, letterSpacing: -3, opacity: title}}>{scene.title}</div>
        <div style={{fontSize: fitBody(scene.body, 36), lineHeight: 1.42, color: palette.muted, marginTop: 35, opacity: copy}}>{textLines(scene.body, 3).join(" ")}</div>
        <svg width="650" height="70" viewBox="0 0 650 70" style={{marginTop: 28}}>
          <InkPath d="M12 44 C124 23 218 55 322 37 C431 18 532 52 638 27" draw={draw} stroke={palette.accents[0]} width={10} />
        </svg>
      </div>
      <div style={{display: "grid", placeItems: "center", transform: `rotate(${Math.sin(frame / 30) * 2}deg)`}}>
        <DomainDoodle scene={scene} draw={draw} colors={palette.accents} size={390} />
      </div>
    </div>
  );
};

const DiagramScene: React.FC<{scene: Scene; palette: Palette; duration: number}> = ({scene, palette, duration}) => {
  const frame = useCurrentFrame();
  const items = textLines(scene.body, 4);
  const connection = reveal(frame, at(duration, 0.1), at(duration, 0.65));
  return (
    <div style={{position: "absolute", inset: "100px 110px 85px"}}>
      <div style={{fontSize: fitTitle(scene.title, 66), fontWeight: 920, letterSpacing: -2}}>{scene.title}</div>
      <svg width="1700" height="720" viewBox="0 0 1700 720" style={{position: "absolute", left: 0, top: 110}}>
        <InkPath d="M850 345 C650 305 520 205 350 180 M850 345 C1050 300 1180 205 1350 180 M850 345 C650 395 520 525 350 550 M850 345 C1050 400 1180 525 1350 550" draw={connection} stroke={palette.accents[0]} dashed />
      </svg>
      <div style={{position: "absolute", left: 715, top: 300, width: 280, height: 180, borderRadius: 90, background: palette.accents[1], border: `5px solid ${INK}`, display: "grid", placeItems: "center"}}>
        <DomainDoodle scene={scene} draw={connection} colors={palette.accents} size={145} />
      </div>
      {items.map((item, index) => {
        const positions = [[70, 180], [1230, 180], [70, 545], [1230, 545]][index] || [70, 180];
        const enter = reveal(frame, beatAt(scene, duration, index, 0.14 + index * 0.13), at(duration, 0.17));
        return (
          <div
            key={item}
            style={{
              position: "absolute",
              left: positions[0],
              top: positions[1],
              width: 390,
              minHeight: 120,
              padding: "22px 26px",
              boxSizing: "border-box",
              background: palette.surface,
              border: "3px solid rgba(23,23,23,.18)",
              borderRadius: 22,
              fontSize: fitBody(item, 28),
              lineHeight: 1.28,
              fontWeight: 720,
              opacity: enter,
              transform: `scale(${0.94 + enter * 0.06}) rotate(${index % 2 ? 1 : -1}deg)`,
            }}
          >
            {item}
          </div>
        );
      })}
    </div>
  );
};

const SceneVisual: React.FC<{
  scene: Scene;
  index: number;
  total: number;
  mode: string;
  duration: number;
  palette: Palette;
}> = ({scene, index, total, mode, duration, palette}) => {
  const type = scene.type.toLowerCase();
  if (scene.motionPlan) {
    return (
      <SceneShell scene={scene} duration={duration} palette={palette}>
        <ProceduralMotionScene scene={scene as ProceduralScene} palette={palette} duration={duration} />
      </SceneShell>
    );
  }
  let visual: React.ReactNode;
  if (["hook", "chapter"].includes(type)) visual = <HookScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "closing") visual = <HookScene scene={scene} palette={palette} duration={duration} closing />;
  else if (["metric", "chart"].includes(type)) visual = <MetricScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "comparison") visual = <ComparisonScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "quote") visual = <QuoteScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "timeline") visual = <TimelineScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "process") visual = <ProcessScene scene={scene} palette={palette} duration={duration} />;
  else if (["diagram", "code", "image"].includes(type)) visual = <DiagramScene scene={scene} palette={palette} duration={duration} />;
  else if (type === "statement") visual = <StatementScene scene={scene} palette={palette} duration={duration} />;
  else visual = <GridScene scene={scene} palette={palette} duration={duration} />;
  return (
    <SceneShell scene={scene} duration={duration} palette={palette}>
      {visual}
    </SceneShell>
  );
};

export const VideoFlowComposition: React.FC<VideoFlowProps> = (props) => {
  const palette = props.visualLanguage?.palette ?? paletteEditions[props.theme] ?? paletteEditions["voice-flow"];
  let from = 0;
  return (
    <AbsoluteFill style={{background: palette.background}}>
      {props.scenes.map((scene, index) => {
        const durationInFrames = Math.max(1, Math.ceil(scene.durationSeconds * props.fps));
        const sceneFrom = from;
        from += durationInFrames;
        return (
          <Sequence
            key={scene.id}
            from={sceneFrom}
            durationInFrames={durationInFrames}
            premountFor={props.fps}
            name={`Notebook Sketch · ${scene.title}`}
          >
            <SceneVisual
              scene={scene}
              index={index}
              total={props.scenes.length}
              mode={props.mode}
              duration={durationInFrames}
              palette={palette}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const VideoFlowRoot: React.FC = () => (
  <Composition
    id="VideoFlow"
    component={VideoFlowComposition}
    defaultProps={defaultProps}
    durationInFrames={150}
    fps={24}
    width={1920}
    height={1080}
    calculateMetadata={({props}) => {
      const fps = props.fps || 24;
      return {
        durationInFrames: Math.max(
          1,
          Math.ceil(props.scenes.reduce((total, scene) => total + scene.durationSeconds, 0) * fps)
        ),
        fps,
        width: props.width || 1920,
        height: props.height || 1080,
        defaultOutName: `${props.title || "video-flow"}.mp4`,
        props: {
          ...props,
          visualLanguage: {
            system: "notebook-sketch",
            renderer: "notebook-sketch-v1",
            palette: props.visualLanguage?.palette ?? paletteEditions[props.theme] ?? paletteEditions["voice-flow"],
            ...props.visualLanguage,
          },
        },
      };
    }}
  />
);
