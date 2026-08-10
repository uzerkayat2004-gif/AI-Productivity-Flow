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

type Scene = {
  id: string;
  type: string;
  title: string;
  body: string;
  narration: string;
  accent?: number;
  durationSeconds: number;
  audioFile?: string | null;
};

type VideoFlowProps = {
  title: string;
  mode: "summary" | "full";
  fps: number;
  width: number;
  height: number;
  theme: string;
  scenes: Scene[];
};

const defaultProps: VideoFlowProps = {
  title: "Video Flow",
  mode: "summary",
  fps: 30,
  width: 1920,
  height: 1080,
  theme: "voice-flow",
  scenes: [
    {
      id: "scene-001",
      type: "hook",
      title: "Video Flow",
      body: "Turn selected text and documents into clear visual explanations.",
      narration: "Turn selected text and documents into clear visual explanations.",
      durationSeconds: 5,
    },
  ],
};

const themes: Record<string, {bg: string; surface: string; text: string; muted: string; accents: string[]}> = {
  "voice-flow": {bg: "#07111d", surface: "#122132", text: "#f7fbff", muted: "#9bb0c6", accents: ["#ff6b19", "#00dff5", "#8b7bff", "#52dc90"]},
  midnight: {bg: "#080815", surface: "#17172c", text: "#f8f4ff", muted: "#aaa4c2", accents: ["#a78bfa", "#38bdf8", "#f472b6", "#fbbf24"]},
  paper: {bg: "#f5f0e5", surface: "#fffaf0", text: "#27221b", muted: "#71695e", accents: ["#e85d2a", "#218f8d", "#7157c8", "#d79d23"]},
  neon: {bg: "#05070a", surface: "#10151c", text: "#f6ffff", muted: "#8aa5ad", accents: ["#00ffd5", "#ff3ac8", "#7c4dff", "#faff00"]},
  ocean: {bg: "#041b2d", surface: "#0b3047", text: "#f2fbff", muted: "#9ac6d5", accents: ["#21d4fd", "#2af598", "#7a89ff", "#f6c85f"]},
  forest: {bg: "#0b1a14", surface: "#173025", text: "#f2fff8", muted: "#9ebcac", accents: ["#68d391", "#f6ad55", "#4fd1c5", "#d6bcfa"]},
  sunset: {bg: "#211019", surface: "#3a1f29", text: "#fff8f5", muted: "#d5aaa4", accents: ["#ff7a59", "#fbbf77", "#ef70a5", "#8fa8ff"]},
  mono: {bg: "#0d0d0d", surface: "#222", text: "#fafafa", muted: "#aaa", accents: ["#fff", "#bdbdbd", "#858585", "#5c5c5c"]},
};

const clamp = {extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const};

const textLines = (body: string, limit = 5) => {
  const parts = body.split(/(?<=[.!?])\s+|\n+/).map((part) => part.trim()).filter(Boolean);
  return (parts.length ? parts : [body]).slice(0, limit);
};

const useEntrance = (delay = 0) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({frame: frame - delay, fps, config: {damping: 18, stiffness: 115, mass: 0.85}});
  return {
    opacity: interpolate(frame, [delay, delay + 12], [0, 1], clamp),
    transform: `translateY(${interpolate(progress, [0, 1], [54, 0])}px) scale(${interpolate(progress, [0, 1], [0.96, 1])})`,
  };
};

const Ambient: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 34) * 36;
  return (
    <>
      <div style={{position: "absolute", width: 620, height: 620, left: -160 + drift, top: -260, borderRadius: "50%", background: accent, opacity: 0.13, filter: "blur(95px)"}} />
      <div style={{position: "absolute", width: 500, height: 500, right: -130 - drift, bottom: -240, borderRadius: "50%", background: accent, opacity: 0.1, filter: "blur(110px)"}} />
      <div style={{position: "absolute", inset: 0, opacity: 0.06, backgroundImage: "linear-gradient(rgba(255,255,255,.35) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.35) 1px, transparent 1px)", backgroundSize: "72px 72px"}} />
    </>
  );
};

const Eyebrow: React.FC<{index: number; total: number; mode: string; accent: string}> = ({index, total, mode, accent}) => (
  <div style={{position: "absolute", left: 108, right: 108, top: 62, display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 24, letterSpacing: 3, textTransform: "uppercase"}}>
    <div style={{display: "flex", gap: 16, alignItems: "center"}}>
      <span style={{width: 12, height: 12, borderRadius: 99, background: accent, boxShadow: `0 0 28px ${accent}`}} />
      <span>Video Flow · {mode === "full" ? "Full explanation" : "Summary"}</span>
    </div>
    <span style={{fontVariantNumeric: "tabular-nums"}}>{String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}</span>
  </div>
);

const HookVisual: React.FC<{scene: Scene; accent: string}> = ({scene, accent}) => {
  const entrance = useEntrance(2);
  return (
    <div style={{...entrance, maxWidth: 1450}}>
      <div style={{fontSize: 34, color: accent, fontWeight: 800, marginBottom: 30, letterSpacing: 4, textTransform: "uppercase"}}>The idea</div>
      <div style={{fontSize: 112, lineHeight: 1.02, letterSpacing: -5, fontWeight: 900}}>{scene.title}</div>
      <div style={{width: 220, height: 10, borderRadius: 8, background: accent, marginTop: 42}} />
    </div>
  );
};

const QuoteVisual: React.FC<{scene: Scene; accent: string; muted: string}> = ({scene, accent, muted}) => {
  const entrance = useEntrance(3);
  return (
    <div style={{...entrance, width: 1450, borderLeft: `12px solid ${accent}`, padding: "36px 70px"}}>
      <div style={{fontSize: 150, lineHeight: 0.6, color: accent, fontFamily: "Georgia, serif"}}>“</div>
      <div style={{fontSize: 69, lineHeight: 1.22, fontWeight: 650}}>{textLines(scene.body, 2).join(" ")}</div>
      <div style={{fontSize: 26, color: muted, marginTop: 35}}>From the source material</div>
    </div>
  );
};

const CardsVisual: React.FC<{scene: Scene; accent: string; surface: string; muted: string; kind: string}> = ({scene, accent, surface, muted, kind}) => {
  const lines = textLines(scene.body, kind === "grid" ? 6 : 4);
  const frame = useCurrentFrame();
  return (
    <div style={{width: 1500}}>
      <div style={{fontSize: 76, fontWeight: 900, letterSpacing: -2, marginBottom: 54}}>{scene.title}</div>
      <div style={{display: "grid", gridTemplateColumns: kind === "process" ? `repeat(${Math.min(lines.length, 4)}, 1fr)` : "repeat(2, 1fr)", gap: 24}}>
        {lines.map((line, index) => {
          const opacity = interpolate(frame, [8 + index * 7, 18 + index * 7], [0, 1], clamp);
          const x = interpolate(frame, [8 + index * 7, 20 + index * 7], [40, 0], {...clamp, easing: Easing.out(Easing.cubic)});
          return (
            <div key={line + index} style={{opacity, transform: `translateX(${x}px)`, minHeight: kind === "process" ? 280 : 190, background: surface, border: "1px solid rgba(255,255,255,.11)", borderRadius: 28, padding: 38, boxShadow: "0 24px 80px rgba(0,0,0,.22)"}}>
              <div style={{fontSize: 25, fontWeight: 900, color: accent, marginBottom: 18}}>{kind === "process" ? String(index + 1).padStart(2, "0") : "●"}</div>
              <div style={{fontSize: kind === "process" ? 34 : 31, lineHeight: 1.28, fontWeight: 650}}>{line}</div>
              {kind === "process" && index < lines.length - 1 ? <div style={{fontSize: 30, color: muted, position: "absolute"}}>→</div> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ComparisonColumn: React.FC<{lines: string[]; column: number; accent: string; surface: string; muted: string}> = ({lines, column, accent, surface, muted}) => {
  const entrance = useEntrance(5 + column * 7);
  return (
    <div style={{...entrance, background: surface, borderRadius: 32, padding: 44, borderTop: "8px solid " + accent}}>
      <div style={{fontSize: 26, color: accent, fontWeight: 850, textTransform: "uppercase", letterSpacing: 3, marginBottom: 28}}>{column === 0 ? "What changes" : "Why it matters"}</div>
      {lines.map((line, index) => <div key={line + index} style={{fontSize: 34, lineHeight: 1.3, padding: "18px 0", color: index ? muted : undefined, borderBottom: "1px solid rgba(255,255,255,.08)"}}>{line}</div>)}
    </div>
  );
};

const ComparisonVisual: React.FC<{scene: Scene; accents: string[]; surface: string; muted: string}> = ({scene, accents, surface, muted}) => {
  const lines = textLines(scene.body, 4);
  const columns = [
    lines.filter((_, index) => index % 2 === 0),
    lines.filter((_, index) => index % 2 === 1),
  ];
  return (
    <div style={{width: 1500}}>
      <div style={{fontSize: 76, fontWeight: 900, marginBottom: 52}}>{scene.title}</div>
      <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28}}>
        {columns.map((group, column) => (
          <ComparisonColumn key={column} lines={group} column={column} accent={accents[column]} surface={surface} muted={muted} />
        ))}
      </div>
    </div>
  );
};
const TimelineVisual: React.FC<{scene: Scene; accent: string; muted: string}> = ({scene, accent, muted}) => {
  const frame = useCurrentFrame();
  const lines = textLines(scene.body, 5);
  const lineWidth = interpolate(frame, [5, 45], [0, 100], clamp);
  return (
    <div style={{width: 1500}}>
      <div style={{fontSize: 76, fontWeight: 900, marginBottom: 110}}>{scene.title}</div>
      <div style={{height: 8, borderRadius: 8, background: "rgba(255,255,255,.16)", position: "relative"}}>
        <div style={{height: "100%", width: `${lineWidth}%`, background: accent, borderRadius: 8}} />
        <div style={{position: "absolute", left: 0, right: 0, top: -22, display: "flex", justifyContent: "space-between"}}>
          {lines.map((line, index) => {
            const opacity = interpolate(frame, [12 + index * 8, 20 + index * 8], [0, 1], clamp);
            return <div key={line + index} style={{width: 250, opacity, textAlign: "center"}}>
              <div style={{width: 48, height: 48, margin: "0 auto 28px", borderRadius: 99, background: accent, border: "10px solid rgba(255,255,255,.2)"}} />
              <div style={{fontSize: 28, lineHeight: 1.25, fontWeight: 720}}>{line}</div>
              <div style={{fontSize: 21, color: muted, marginTop: 12}}>Step {index + 1}</div>
            </div>;
          })}
        </div>
      </div>
    </div>
  );
};

const MetricVisual: React.FC<{scene: Scene; accent: string; muted: string}> = ({scene, accent, muted}) => {
  const frame = useCurrentFrame();
  const match = scene.body.match(/\b\d+(?:\.\d+)?%?\b/);
  const value = match?.[0] ?? "1 idea";
  const scale = spring({frame: frame - 4, fps: 30, config: {damping: 14, stiffness: 100}});
  return (
    <div style={{textAlign: "center", maxWidth: 1450}}>
      <div style={{fontSize: 34, textTransform: "uppercase", letterSpacing: 5, color: muted, marginBottom: 24}}>{scene.title}</div>
      <div style={{fontSize: 220, lineHeight: 1, fontWeight: 950, color: accent, transform: `scale(${scale})`, textShadow: `0 0 70px ${accent}55`}}>{value}</div>
      <div style={{fontSize: 48, lineHeight: 1.25, marginTop: 38}}>{textLines(scene.body, 2).join(" ")}</div>
    </div>
  );
};

const StatementVisual: React.FC<{scene: Scene; accent: string; muted: string}> = ({scene, accent, muted}) => {
  const entrance = useEntrance(3);
  return (
    <div style={{...entrance, maxWidth: 1480}}>
      <div style={{fontSize: 78, lineHeight: 1.08, fontWeight: 900, letterSpacing: -2}}>{scene.title}</div>
      <div style={{fontSize: 38, lineHeight: 1.42, color: muted, marginTop: 42, maxWidth: 1320}}>{textLines(scene.body, 3).join(" ")}</div>
      <div style={{display: "flex", alignItems: "center", gap: 18, marginTop: 52, fontSize: 25, color: accent, textTransform: "uppercase", letterSpacing: 3}}>
        <span style={{width: 70, height: 5, background: accent, borderRadius: 5}} /> Key explanation
      </div>
    </div>
  );
};

const SceneVisual: React.FC<{scene: Scene; index: number; total: number; mode: string; themeName: string}> = ({scene, index, total, mode, themeName}) => {
  const palette = themes[themeName] ?? themes["voice-flow"];
  const accent = palette.accents[(scene.accent ?? index) % palette.accents.length];
  const type = scene.type.toLowerCase();
  let visual: React.ReactNode;
  if (type === "hook" || type === "chapter" || type === "closing") visual = <HookVisual scene={scene} accent={accent} />;
  else if (type === "quote") visual = <QuoteVisual scene={scene} accent={accent} muted={palette.muted} />;
  else if (type === "metric" || type === "chart") visual = <MetricVisual scene={scene} accent={accent} muted={palette.muted} />;
  else if (type === "comparison") visual = <ComparisonVisual scene={scene} accents={palette.accents} surface={palette.surface} muted={palette.muted} />;
  else if (type === "timeline") visual = <TimelineVisual scene={scene} accent={accent} muted={palette.muted} />;
  else if (["process", "grid", "list", "diagram", "code", "image"].includes(type)) visual = <CardsVisual scene={scene} accent={accent} surface={palette.surface} muted={palette.muted} kind={type === "process" ? "process" : "grid"} />;
  else visual = <StatementVisual scene={scene} accent={accent} muted={palette.muted} />;

  return (
    <AbsoluteFill style={{background: palette.bg, color: palette.text, fontFamily: "Inter, Segoe UI, Arial, sans-serif", overflow: "hidden"}}>
      <Ambient accent={accent} />
      <Eyebrow index={index} total={total} mode={mode} accent={accent} />
      <div style={{position: "absolute", inset: "150px 108px 105px", display: "flex", alignItems: "center", justifyContent: "center"}}>{visual}</div>
      <div style={{position: "absolute", left: 108, right: 108, bottom: 50, height: 3, background: "rgba(255,255,255,.1)"}}>
        <div style={{height: "100%", width: `${((index + 1) / total) * 100}%`, background: accent}} />
      </div>
      {scene.audioFile ? <Audio src={staticFile(scene.audioFile)} /> : null}
    </AbsoluteFill>
  );
};

const VideoFlowComposition: React.FC<VideoFlowProps> = (props) => {
  let from = 0;
  return (
    <AbsoluteFill>
      {props.scenes.map((scene, index) => {
        const durationInFrames = Math.max(1, Math.ceil(scene.durationSeconds * props.fps));
        const sceneFrom = from;
        from += durationInFrames;
        return (
          <Sequence key={scene.id} from={sceneFrom} durationInFrames={durationInFrames} name={scene.title}>
            <SceneVisual scene={scene} index={index} total={props.scenes.length} mode={props.mode} themeName={props.theme} />
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
    fps={30}
    width={1920}
    height={1080}
    calculateMetadata={({props}) => {
      const fps = props.fps || 30;
      const durationInFrames = Math.max(1, Math.ceil(props.scenes.reduce((total, scene) => total + scene.durationSeconds, 0) * fps));
      return {
        durationInFrames,
        fps,
        width: props.width || 1920,
        height: props.height || 1080,
      };
    }}
  />
);
