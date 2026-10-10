import React from "react";
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

type Palette = {background: string; surface: string; text: string; muted: string; accents: string[]};
type MotionObject = {id: string; kind: string; label: string; glyph: string; x: number; y: number; scale: number; rotation: number; accent: number; emphasis: string};
type MotionEdge = {id: string; from: string; to: string; style: string; accent: number};
type MotionAction = {id: string; kind: string; targetId: string; cue: string; startRatio: number; endRatio: number; direction: string; intensity: number};
type MotionPlan = {
  signature: string;
  domainGrammar: string;
  semanticMode: string;
  layout: {algorithm: string; seed: number};
  camera: {mode: string; direction: string; strength: number};
  transition: {kind: string; direction: string; durationSeconds: number};
  tempo: string;
  surfaceStyle: "annotation" | "sticky" | "badge" | "cutout" | "label" | "panel";
  titlePlacement: "top-left" | "top-right" | "side-left" | "side-right";
  objects: MotionObject[];
  edges: MotionEdge[];
  actions: MotionAction[];
};
export type ProceduralScene = {title: string; body: string; domain?: string; motionPlan: MotionPlan};

const INK = "#171717";
const PAPER = "#fbfaf5";
const clamp = {extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const};
const ease = Easing.bezier(0.16, 1, 0.3, 1);
const progress = (frame: number, start: number, end: number) => interpolate(frame, [start, Math.max(start + 1, end)], [0, 1], {...clamp, easing: ease});
const hash = (value: string) => [...value].reduce((total, char) => ((total << 5) - total + char.charCodeAt(0)) | 0, 0);

const Glyph: React.FC<{name: string; color: string; draw: number}> = ({name, color, draw}) => {
  const dash = 1 - draw;
  const stroke = {fill: "none", stroke: INK, strokeWidth: 5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, pathLength: 1, strokeDasharray: 1, strokeDashoffset: dash};
  const fill = {fill: color, opacity: 0.25 + draw * 0.45, stroke: INK, strokeWidth: 4};
  const category = (() => {
    if (/book|bookmark|pencil|brain|question|note/.test(name)) return "study";
    if (/shield|lock|warning|key|packet/.test(name)) return "security";
    if (/chip|terminal|network|database|robot/.test(name)) return "technology";
    if (/flask|atom|microscope|molecule|wave/.test(name)) return "science";
    if (/heart|pulse|cross|cell|care/.test(name)) return "health";
    if (/bowl|leaf|timer|flame|ingredient/.test(name)) return "food";
    if (/globe|drop|sun|tree/.test(name)) return "nature";
    if (/controller|trophy|flag|gem|map/.test(name)) return "gaming";
    if (/chart|target|coin|briefcase|arrow-up/.test(name)) return "business";
    return "general";
  })();
  return <svg width="112" height="112" viewBox="0 0 120 120" aria-label={name}>
    {category === "study" ? <><path d="M16 25 Q42 15 60 30 Q82 14 104 25 L104 95 Q82 84 60 101 Q39 84 16 95 Z" {...fill}/><path d="M60 30 L60 101 M27 43 Q43 37 53 43 M68 43 Q84 36 96 43 M27 61 Q43 55 53 61 M68 61 Q84 54 96 61" {...stroke}/></> : null}
    {category === "security" ? <><path d="M60 10 Q82 25 103 26 L99 70 Q94 97 60 110 Q26 97 21 70 L17 26 Q39 24 60 10 Z" {...fill}/><path d="M39 59 L53 73 L84 41" {...stroke}/></> : null}
    {category === "technology" ? <><rect x="27" y="27" width="66" height="66" rx="12" {...fill}/><rect x="43" y="43" width="34" height="34" rx="5" {...stroke}/><path d="M12 43 H27 M12 60 H27 M12 77 H27 M93 43 H108 M93 60 H108 M93 77 H108 M43 12 V27 M60 12 V27 M77 12 V27 M43 93 V108 M60 93 V108 M77 93 V108" {...stroke}/></> : null}
    {category === "science" ? <><path d="M45 12 H75 M51 12 V46 L25 95 Q20 106 34 108 H86 Q100 106 95 95 L69 46 V12 M35 83 Q58 70 86 83" {...fill}/><circle cx="50" cy="89" r="5" fill={INK} opacity={draw}/><circle cx="72" cy="94" r="4" fill={INK} opacity={draw}/></> : null}
    {category === "health" ? <><path d="M60 105 C14 79 18 36 41 31 Q56 27 60 45 Q66 27 82 31 C106 38 105 80 60 105 Z" {...fill}/><path d="M23 66 H43 L51 51 L63 82 L73 65 H99" {...stroke}/></> : null}
    {category === "food" ? <><path d="M18 59 Q60 82 102 59 Q95 103 60 106 Q25 103 18 59 Z" {...fill}/><path d="M38 48 Q28 32 40 17 M60 46 Q48 28 61 12 M83 48 Q73 31 85 19" {...stroke}/></> : null}
    {category === "nature" ? <><path d="M16 94 Q15 31 104 16 Q102 92 32 103 Z" {...fill}/><path d="M23 96 Q57 65 95 29 M49 72 L42 46 M69 54 L82 70" {...stroke}/></> : null}
    {category === "gaming" ? <><path d="M20 48 Q31 25 53 37 H68 Q91 25 102 48 L110 85 Q112 105 96 107 Q83 108 73 87 H47 Q36 108 23 107 Q7 105 10 85 Z" {...fill}/><path d="M31 63 V84 M21 73 H42" {...stroke}/><circle cx="85" cy="64" r="6" fill={INK} opacity={draw}/><circle cx="96" cy="79" r="6" fill={INK} opacity={draw}/></> : null}
    {category === "business" ? <><path d="M18 102 V18 M18 102 H107" {...stroke}/><rect x="31" y={77 - 25 * draw} width="14" height={25 * draw} {...fill}/><rect x="55" y={61 - 41 * draw} width="14" height={41 * draw} {...fill}/><rect x="79" y={40 - 62 * draw} width="14" height={62 * draw} {...fill}/><path d="M28 80 C49 71 58 56 73 48 C87 41 96 25 106 19" {...stroke}/></> : null}
    {category === "general" ? <><path d="M43 71 C24 51 32 18 61 17 C89 16 100 48 81 70 Q73 80 72 91 H49 Q48 80 43 71 Z" {...fill}/><path d="M49 92 H72 M51 102 H70 M47 59 Q60 43 74 58 M60 59 V91" {...stroke}/></> : null}
  </svg>;
};

const actionFamily = (kind: string) => {
  if (/travel|route|flow|race|spread|transfer|reroute|branch/.test(kind)) return "travel";
  if (/orbit|circle|evaporate|gather|scatter/.test(kind)) return "orbit";
  if (/flip|stack|compile|assemble|combine|merge|mix/.test(kind)) return "construct";
  if (/block|intercept|shield|lock|contain|verify|stamp/.test(kind)) return "impact";
  if (/count|measure|score|rank|plot|scan/.test(kind)) return "measure";
  if (/grow|bloom|heal|recover|level-up|charge/.test(kind)) return "grow";
  if (/write|sketch|trace|underline|annotate|label|highlight/.test(kind)) return "draw";
  return "transform";
};

const objectTransform = (action: MotionAction | undefined, amount: number, seed: number) => {
  const family = actionFamily(action?.kind || "reveal");
  const direction = action?.direction || "up";
  const dx = direction === "left" ? -1 : direction === "right" ? 1 : 0;
  const dy = direction === "up" ? -1 : direction === "down" ? 1 : 0;
  const wobble = Math.sin(amount * Math.PI * (2 + Math.abs(seed % 3))) * (1 - amount);
  if (family === "travel") return {x: dx * (1 - amount) * 260, y: dy * (1 - amount) * 190 + wobble * 22, rotate: wobble * 7, scale: .76 + amount * .24};
  if (family === "orbit") return {x: Math.cos(amount * Math.PI * 2) * (1 - amount) * 150, y: Math.sin(amount * Math.PI * 2) * (1 - amount) * 110, rotate: (1 - amount) * 24, scale: .72 + amount * .28};
  if (family === "construct") return {x: dx * (1 - amount) * 80, y: (1 - amount) * -120, rotate: (1 - amount) * (seed % 2 ? 28 : -28), scale: .55 + amount * .45};
  if (family === "impact") return {x: wobble * 16, y: 0, rotate: wobble * 4, scale: .84 + amount * .16 + Math.sin(amount * Math.PI) * .1};
  if (family === "measure") return {x: 0, y: (1 - amount) * 38, rotate: 0, scale: .6 + amount * .4};
  if (family === "grow") return {x: 0, y: (1 - amount) * 70, rotate: wobble * 3, scale: .25 + amount * .75};
  if (family === "draw") return {x: dx * (1 - amount) * 35, y: dy * (1 - amount) * 25, rotate: (1 - amount) * -3, scale: .94 + amount * .06};
  return {x: dx * (1 - amount) * 90, y: dy * (1 - amount) * 70, rotate: wobble * 8, scale: .7 + amount * .3};
};

const cameraTransform = (plan: MotionPlan, frame: number, duration: number) => {
  const actionProgress = plan.actions.length ? plan.actions.reduce((total, action) => {
    return total + progress(frame, action.startRatio * duration, action.endRatio * duration);
  }, 0) / plan.actions.length : 0;
  const t = actionProgress;
  const strength = plan.camera.strength || .05;
  const direction = plan.camera.direction;
  const sign = direction === "left" || direction === "up" || direction === "counterclockwise" ? -1 : 1;
  if (plan.camera.mode === "push") return `translate(${sign * t * 18}px, 0) scale(${1 + t * strength})`;
  if (plan.camera.mode === "pullback") return `translate(0, ${sign * t * 10}px) scale(${1 + strength - t * strength})`;
  if (plan.camera.mode === "pan") return `translateX(${sign * (t - .5) * 70}px) scale(1.035)`;
  if (plan.camera.mode === "tilt") return `translateY(${sign * (t - .5) * 34}px) rotate(${sign * (t - .5) * .8}deg) scale(1.025)`;
  return `translate(${sign * Math.sin(t * Math.PI) * 34}px, ${Math.cos(t * Math.PI) * 12}px) scale(1.03)`;
};

const EdgeLayer: React.FC<{plan: MotionPlan; palette: Palette; duration: number; frameOverride?: number}> = ({plan, palette, duration, frameOverride}) => {
  const timelineFrame = useCurrentFrame();
  const frame = frameOverride ?? timelineFrame;
  const byId = new Map(plan.objects.map((item) => [item.id, item]));
  return <svg viewBox="0 0 1920 1080" width="1920" height="1080" style={{position: "absolute", inset: 0}}>
    {plan.edges.map((edge, index) => {
      const start = byId.get(edge.from); const end = byId.get(edge.to);
      if (!start || !end) return null;
      const edgeAction = plan.actions[Math.min(index + 1, plan.actions.length - 1)];
      const draw = progress(frame, edgeAction.startRatio * duration, edgeAction.endRatio * duration);
      const x1 = start.x * 1920; const y1 = start.y * 1080; const x2 = end.x * 1920; const y2 = end.y * 1080;
      const bend = ((hash(edge.id + plan.signature) % 121) - 60);
      const d = `M${x1} ${y1} Q${(x1 + x2) / 2 + bend} ${(y1 + y2) / 2 - bend} ${x2} ${y2}`;
      return <g key={edge.id}>
        <path d={d} fill="none" stroke={INK} strokeWidth="9" opacity=".1" transform="translate(3 3)"/>
        <path d={d} fill="none" stroke={palette.accents[edge.accent % palette.accents.length]} strokeWidth={edge.style === "marker" ? 10 : 5} strokeLinecap="round" pathLength={1} strokeDasharray={edge.style === "dashed" ? ".025 .035" : "1"} strokeDashoffset={1 - draw}/>
        {edge.style === "double" ? <path d={d} fill="none" stroke={INK} strokeWidth="2" strokeLinecap="round" transform="translate(0 9)" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw}/> : null}
      </g>;
    })}
  </svg>;
};

const ObjectNode: React.FC<{item: MotionObject; action: MotionAction | undefined; palette: Palette; duration: number; plan: MotionPlan; frameOverride?: number}> = ({item, action, palette, duration, plan, frameOverride}) => {
  const timelineFrame = useCurrentFrame();
  const frame = frameOverride ?? timelineFrame;
  const {fps} = useVideoConfig();
  const start = (action?.startRatio ?? .05) * duration;
  const end = (action?.endRatio ?? .18) * duration;
  const linear = progress(frame, start, end);
  const elastic = spring({frame: frame - start, fps, config: {damping: plan.tempo === "elastic" ? 11 : 18, stiffness: plan.tempo === "brisk" ? 150 : 105}});
  const amount = actionFamily(action?.kind || "") === "impact" || plan.tempo === "elastic" ? elastic : linear;
  const movement = objectTransform(action, amount, hash(item.id + plan.signature));
  const accent = palette.accents[item.accent % palette.accents.length];
  const family = actionFamily(action?.kind || "");
  const labelReveal = family === "draw" ? linear : Math.max(0, interpolate(linear, [0, .42, 1], [0, 0, 1], clamp));
  const width = plan.surfaceStyle === "label" ? 250 : item.emphasis === "primary" ? 360 : 300;
  const metric = item.kind === "metric";
  const surface = plan.surfaceStyle || "panel";
  const isBare = surface === "label" || surface === "annotation";
  const radius = surface === "badge" ? 110 : surface === "sticky" ? 8 : surface === "cutout" ? 44 : 25;
  const clipPath = surface === "cutout" ? "polygon(4% 0, 96% 3%, 100% 89%, 91% 100%, 3% 96%, 0 9%)" : undefined;
  return <div style={{position: "absolute", left: item.x * 1920, top: item.y * 1080, width, transform: `translate(-50%, -50%) translate(${movement.x}px, ${movement.y}px) rotate(${item.rotation + movement.rotate}deg) scale(${item.scale * movement.scale})`, opacity: linear}}>
    <div style={{position: "relative", minHeight: isBare ? 118 : metric ? 170 : 205, padding: isBare ? "18px 12px" : "23px 26px 24px", boxSizing: "border-box", borderRadius: plan.layout.algorithm.includes("rings") || surface === "badge" ? 110 : radius, clipPath, background: surface === "annotation" ? `${accent}20` : surface === "label" ? "transparent" : surface === "sticky" ? `${accent}2b` : palette.surface, border: surface === "label" ? "none" : `3px solid ${INK}`, borderBottom: surface === "label" ? `8px solid ${accent}` : undefined, boxShadow: isBare ? "none" : surface === "sticky" ? `12px 15px 0 rgba(23,23,23,.09)` : `9px 11px 0 ${accent}35`}}>
      <div style={{position: "absolute", right: -33, top: -46, transform: "scale(.64) rotate(5deg)"}}><Glyph name={item.glyph} color={accent} draw={linear}/></div>
      <div style={{fontSize: 16, letterSpacing: 2.2, textTransform: "uppercase", color: palette.muted, fontWeight: 850}}>{action?.kind.replaceAll("-", " ") || item.emphasis}</div>
      <div style={{fontSize: metric ? 45 : 28, lineHeight: 1.16, fontWeight: 860, marginTop: 15, opacity: labelReveal}}>{item.label}</div>
      <div style={{height: 9, width: `${linear * 74}%`, marginTop: 17, borderRadius: 9, background: accent, border: `1px solid ${INK}`}}/>
    </div>
  </div>;
};

export const ProceduralMotionScene: React.FC<{scene: ProceduralScene; palette: Palette; duration: number; frameOverride?: number}> = ({scene, palette, duration, frameOverride}) => {
  const timelineFrame = useCurrentFrame();
  const frame = frameOverride ?? timelineFrame;
  const plan = scene.motionPlan;
  const titleIn = progress(frame, duration * .015, duration * .1);
  const actions = new Map(plan.actions.map((action) => [action.targetId, action]));
  const titlePlacement = plan.titlePlacement || (plan.camera.direction === "left" ? "top-right" : "top-left");
  const titleSide = titlePlacement.endsWith("right") ? "right" : "left";
  const titleTop = titlePlacement.startsWith("side") ? 260 : 96;
  const titleWidth = titlePlacement.startsWith("side") ? 520 : 1050;
  const transitionDraw = progress(frame, duration * .02, duration * .12);
  return <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
    <div style={{position: "absolute", inset: -70, transform: cameraTransform(plan, frame, duration), transformOrigin: "center"}}>
      <div style={{position: "absolute", top: titleTop, [titleSide]: 120, maxWidth: titleWidth, textAlign: titleSide as "left" | "right", opacity: titleIn, transform: `translate${titleSide === "left" ? "X" : "X"}(${(1 - titleIn) * (titleSide === "left" ? -35 : 35)}px)`}}>
        <div style={{fontSize: Math.max(48, Math.min(72, 90 - scene.title.length * .38)), lineHeight: 1.02, fontWeight: 930, letterSpacing: -2.5}}>{scene.title}</div>
        <svg width="390" height="35" viewBox="0 0 390 35" style={{marginTop: 9}}><path d="M8 22 C96 6 177 29 257 15 C308 7 348 19 382 9" fill="none" stroke={palette.accents[Math.abs(hash(plan.signature)) % palette.accents.length]} strokeWidth="9" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - transitionDraw}/></svg>
      </div>
      <div style={{position: "absolute", left: "50%", top: "53%", opacity: plan.surfaceStyle === "annotation" ? .05 : .025, transform: `translate(-50%, -50%) scale(5.6) rotate(${hash(plan.signature) % 14}deg)`}}><Glyph name={plan.objects[0]?.glyph || "bulb"} color={palette.accents[2]} draw={1}/></div>
      <EdgeLayer plan={plan} palette={palette} duration={duration} frameOverride={frame}/>
      {plan.objects.map((item) => <ObjectNode key={item.id} item={item} action={actions.get(item.id)} palette={palette} duration={duration} plan={plan} frameOverride={frame}/>)}
      <div style={{position: "absolute", bottom: 74, right: 100, fontSize: 14, color: palette.muted, letterSpacing: 1.8, textTransform: "uppercase", opacity: .72}}>{plan.domainGrammar.split(":")[0]} · {plan.semanticMode.replaceAll("-", " ")}</div>
    </div>
  </div>;
};
