import React from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  interpolate,
  random,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const COLORS = {
  paper: "#fbfaf5",
  ink: "#171717",
  muted: "#696761",
  orange: "#ff8a1f",
  yellow: "#ffd65a",
  blue: "#8bd7e6",
  green: "#89c95d",
  red: "#ef4b43",
  card: "rgba(255,255,255,0.9)",
};

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;
const SCENE_DURATIONS = [110, 140, 110, 140, 130, 100] as const;
const TOTAL_FRAMES = SCENE_DURATIONS.reduce((sum, value) => sum + value, 0);
const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const progress = (frame: number, start: number, duration: number) =>
  interpolate(frame, [start, start + duration], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const PaperBackground: React.FC = () => {
  const flecks = Array.from({length: 44}, (_, index) => ({
    x: random(`paper-x-${index}`) * WIDTH,
    y: random(`paper-y-${index}`) * HEIGHT,
    size: 1 + random(`paper-size-${index}`) * 2.2,
    alpha: 0.03 + random(`paper-alpha-${index}`) * 0.045,
  }));

  return (
    <AbsoluteFill style={{backgroundColor: COLORS.paper, overflow: "hidden"}}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(23,23,23,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(23,23,23,.035) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 18% 12%, rgba(255,214,90,.1), transparent 26%), radial-gradient(circle at 84% 72%, rgba(139,215,230,.09), transparent 30%)",
        }}
      />
      {flecks.map((fleck, index) => (
        <div
          key={index}
          style={{
            position: "absolute",
            left: fleck.x,
            top: fleck.y,
            width: fleck.size,
            height: fleck.size,
            borderRadius: 99,
            background: COLORS.ink,
            opacity: fleck.alpha,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

const SvgDefs: React.FC = () => (
  <defs>
    <filter id="roughInk" x="-15%" y="-15%" width="130%" height="130%">
      <feTurbulence
        type="fractalNoise"
        baseFrequency="0.018"
        numOctaves="2"
        seed="17"
        result="noise"
      />
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.1" />
    </filter>
    <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="12" stdDeviation="12" floodOpacity="0.1" />
    </filter>
  </defs>
);

type InkPathProps = {
  d: string;
  draw?: number;
  stroke?: string;
  width?: number;
  fill?: string;
  opacity?: number;
  dash?: string;
};

const InkPath: React.FC<InkPathProps> = ({
  d,
  draw = 1,
  stroke = COLORS.ink,
  width = 5,
  fill = "none",
  opacity = 1,
  dash,
}) => (
  <path
    d={d}
    pathLength={1}
    stroke={stroke}
    strokeWidth={width}
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeDasharray={dash ?? "1"}
    strokeDashoffset={dash ? 0 : 1 - draw}
    fill={fill}
    opacity={opacity}
    filter="url(#roughInk)"
  />
);

const InkLine: React.FC<{
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  draw?: number;
  color?: string;
  width?: number;
  dashed?: boolean;
}> = ({x1, y1, x2, y2, draw = 1, color = COLORS.ink, width = 5, dashed}) => (
  <line
    x1={x1}
    y1={y1}
    x2={x2}
    y2={y2}
    pathLength={1}
    stroke={color}
    strokeWidth={width}
    strokeLinecap="round"
    strokeDasharray={dashed ? "0.025 0.035" : "1"}
    strokeDashoffset={dashed ? 1 - draw : 1 - draw}
    filter="url(#roughInk)"
  />
);

const SceneShell: React.FC<{
  children: React.ReactNode;
  duration: number;
  label: string;
  index: number;
}> = ({children, duration, label, index}) => {
  const frame = useCurrentFrame();
  const enter = progress(frame, 0, 12);
  const exit = interpolate(frame, [duration - 12, duration], [1, 0], clamp);
  const drift = Math.sin(frame / 42) * 3;

  return (
    <AbsoluteFill
      style={{
        color: COLORS.ink,
        fontFamily: '"Segoe UI", Arial, sans-serif',
        opacity: enter * exit,
        transform: `translateY(${(1 - enter) * 12 + drift}px)`,
      }}
    >
      <PaperBackground />
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 44,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 20,
          fontWeight: 800,
          letterSpacing: 2.5,
          textTransform: "uppercase",
          color: COLORS.muted,
        }}
      >
        <span style={{display: "flex", alignItems: "center", gap: 12}}>
          <span style={{width: 13, height: 13, borderRadius: 99, background: COLORS.orange}} />
          Video Flow Lab · Notebook Sketch
        </span>
        <span>{String(index).padStart(2, "0")} · {label}</span>
      </div>
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          bottom: 40,
          height: 3,
          borderRadius: 9,
          background: "rgba(23,23,23,.08)",
        }}
      >
        <div
          style={{
            width: `${(index / SCENE_DURATIONS.length) * 100}%`,
            height: "100%",
            borderRadius: 9,
            background: COLORS.orange,
          }}
        />
      </div>
      {children}
    </AbsoluteFill>
  );
};

const BulbDoodle: React.FC<{draw: number; color?: string}> = ({draw, color = COLORS.yellow}) => (
  <svg viewBox="0 0 180 210" width="180" height="210">
    <SvgDefs />
    <path d="M58 126 C25 91 39 32 91 28 C142 24 164 81 129 121 C117 134 111 144 109 156 L70 156 C68 144 66 136 58 126 Z" fill={color} opacity={0.64 * draw} />
    <InkPath d="M58 126 C25 91 39 32 91 28 C142 24 164 81 129 121 C117 134 111 144 109 156 L70 156 C68 144 66 136 58 126 Z" draw={draw} />
    <InkPath d="M75 158 L108 158 M76 171 L105 171 M82 184 L99 184" draw={draw} width={5} />
    <InkPath d="M73 104 C79 87 99 86 106 101 C99 111 94 124 91 153 M83 102 C90 112 92 130 92 153" draw={draw} width={4} />
    {[[-3, 72, 24, 76], [31, 19, 47, 39], [89, -2, 90, 21], [143, 16, 129, 40], [168, 65, 145, 72]].map((line, index) => (
      <InkLine key={index} x1={line[0]} y1={line[1]} x2={line[2]} y2={line[3]} draw={draw} width={4} />
    ))}
  </svg>
);

const CameraDoodle: React.FC<{draw: number}> = ({draw}) => (
  <svg viewBox="0 0 220 170" width="220" height="170">
    <SvgDefs />
    <path d="M24 47 L69 47 L80 26 L143 26 L154 47 L197 47 L205 137 L18 137 Z" fill={COLORS.blue} opacity={0.48 * draw} />
    <InkPath d="M24 47 L69 47 L80 26 L143 26 L154 47 L197 47 L205 137 L18 137 Z" draw={draw} />
    <circle cx="112" cy="90" r="38" fill={COLORS.paper} opacity={draw} />
    <circle cx="112" cy="90" r="38" stroke={COLORS.ink} strokeWidth="6" fill="none" strokeDasharray="240" strokeDashoffset={240 * (1 - draw)} filter="url(#roughInk)" />
    <circle cx="112" cy="90" r="20" fill={COLORS.orange} opacity={0.72 * draw} stroke={COLORS.ink} strokeWidth="5" />
    <InkLine x1={32} y1={29} x2={61} y2={29} draw={draw} width={5} />
    <InkLine x1={5} y1={91} x2={-11} y2={91} draw={draw} width={4} />
    <InkLine x1={12} y1={116} x2={-2} y2={125} draw={draw} width={4} />
  </svg>
);

const ChartDoodle: React.FC<{draw: number}> = ({draw}) => (
  <svg viewBox="0 0 250 190" width="250" height="190">
    <SvgDefs />
    <InkLine x1={28} y1={158} x2={227} y2={158} draw={draw} />
    <InkLine x1={28} y1={158} x2={28} y2={25} draw={draw} />
    {[
      {x: 50, h: 45, color: COLORS.orange},
      {x: 93, h: 76, color: COLORS.blue},
      {x: 136, h: 108, color: COLORS.yellow},
      {x: 179, h: 132, color: COLORS.green},
    ].map((bar, index) => (
      <g key={index} opacity={draw}>
        <rect x={bar.x} y={158 - bar.h * draw} width="29" height={bar.h * draw} fill={bar.color} opacity="0.72" />
        <rect x={bar.x} y={158 - bar.h * draw} width="29" height={bar.h * draw} fill="none" stroke={COLORS.ink} strokeWidth="4" filter="url(#roughInk)" />
      </g>
    ))}
    <InkPath d="M46 128 C88 119 104 98 136 91 C168 83 184 54 221 35" draw={draw} width={5} />
    <InkPath d="M203 33 L222 34 L217 53" draw={draw} width={5} />
  </svg>
);

const RobotDoodle: React.FC<{draw: number; happy?: boolean}> = ({draw, happy = true}) => (
  <svg viewBox="0 0 260 280" width="260" height="280">
    <SvgDefs />
    <rect x="50" y="41" width="160" height="109" rx="44" fill={COLORS.card} opacity={draw} />
    <InkPath d="M91 42 C64 42 49 61 49 87 L49 111 C49 135 66 150 90 150 L171 150 C195 150 211 134 211 110 L211 84 C211 59 194 42 170 42 Z" draw={draw} />
    <InkLine x1={85} y1={42} x2={74} y2={19} draw={draw} width={4} />
    <InkLine x1={177} y1={42} x2={187} y2={19} draw={draw} width={4} />
    <circle cx="72" cy="16" r="7" fill={COLORS.blue} stroke={COLORS.ink} strokeWidth="3" opacity={draw} />
    <circle cx="190" cy="16" r="7" fill={COLORS.orange} stroke={COLORS.ink} strokeWidth="3" opacity={draw} />
    <circle cx="96" cy="91" r="10" fill={COLORS.ink} opacity={draw} />
    <circle cx="165" cy="91" r="10" fill={COLORS.ink} opacity={draw} />
    <InkPath d={happy ? "M104 117 C121 133 145 133 159 116" : "M106 128 C123 111 145 111 158 128"} draw={draw} width={5} />
    <path d="M78 158 L181 158 L202 255 L58 255 Z" fill={COLORS.blue} opacity={0.28 * draw} />
    <InkPath d="M78 158 L181 158 L202 255 L58 255 Z" draw={draw} />
    <InkPath d="M57 174 C25 183 25 224 59 229 M202 175 C233 184 235 223 202 230" draw={draw} />
    <circle cx="130" cy="203" r="20" fill={COLORS.orange} opacity={0.65 * draw} stroke={COLORS.ink} strokeWidth="4" />
  </svg>
);

const ShieldDoodle: React.FC<{draw: number}> = ({draw}) => (
  <svg viewBox="0 0 180 220" width="180" height="220">
    <SvgDefs />
    <path d="M90 18 C118 37 143 40 160 42 L156 114 C150 160 123 186 90 201 C57 186 30 160 24 114 L20 42 C42 40 66 35 90 18 Z" fill={COLORS.blue} opacity={0.34 * draw} />
    <InkPath d="M90 18 C118 37 143 40 160 42 L156 114 C150 160 123 186 90 201 C57 186 30 160 24 114 L20 42 C42 40 66 35 90 18 Z" draw={draw} width={6} />
    <InkPath d="M57 109 L78 130 L126 78" draw={draw} stroke={COLORS.green} width={12} />
  </svg>
);

const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const titleIn = progress(frame, 8, 22);
  const ink = progress(frame, 14, 42);
  const pop = spring({frame: frame - 22, fps: FPS, config: {damping: 12, stiffness: 120}});

  return (
    <SceneShell duration={SCENE_DURATIONS[0]} label="The visual language" index={1}>
      <div style={{position: "absolute", inset: "130px 110px 90px", display: "flex", alignItems: "center", justifyContent: "center"}}>
        <div style={{position: "absolute", left: 70, top: 155, transform: `rotate(-8deg) scale(${0.85 + pop * 0.15})`}}>
          <BulbDoodle draw={ink} />
        </div>
        <div style={{position: "absolute", right: 36, bottom: 70, transform: `rotate(7deg) scale(${0.88 + pop * 0.12})`}}>
          <CameraDoodle draw={ink} />
        </div>
        <div style={{textAlign: "center", opacity: titleIn, transform: `scale(${0.96 + titleIn * 0.04})`, width: 1260}}>
          <div style={{fontSize: 28, fontWeight: 900, letterSpacing: 5, color: COLORS.orange, textTransform: "uppercase", marginBottom: 24}}>
            A Remotion proof of concept
          </div>
          <div style={{fontSize: 116, lineHeight: 0.96, fontWeight: 900, letterSpacing: -5}}>
            Ideas that move<br />like ink
          </div>
          <div style={{fontSize: 35, lineHeight: 1.4, color: COLORS.muted, marginTop: 34}}>
            Clean information. Hand-drawn warmth. Purposeful motion.
          </div>
          <svg width="560" height="48" viewBox="0 0 560 48" style={{marginTop: 22}}>
            <SvgDefs />
            <InkPath d="M18 28 C121 18 197 31 286 23 C384 13 441 30 542 19" draw={ink} stroke={COLORS.orange} width={9} />
          </svg>
        </div>
      </div>
    </SceneShell>
  );
};

const WorkflowCard: React.FC<{
  x: number;
  y: number;
  title: string;
  body: string;
  number: string;
  color: string;
  delay: number;
}> = ({x, y, title, body, number, color, delay}) => {
  const frame = useCurrentFrame();
  const enter = progress(frame, delay, 18);
  const settle = spring({frame: frame - delay, fps: FPS, config: {damping: 16, stiffness: 125}});

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: 360,
        height: 210,
        background: COLORS.card,
        border: "2px solid rgba(23,23,23,.12)",
        borderRadius: 24,
        padding: "28px 32px",
        boxSizing: "border-box",
        filter: "drop-shadow(0 14px 18px rgba(23,23,23,.08))",
        opacity: enter,
        transform: `translateY(${(1 - settle) * 34}px) rotate(${(1 - settle) * -2}deg)`,
      }}
    >
      <div style={{display: "flex", alignItems: "center", gap: 16}}>
        <div style={{width: 42, height: 42, borderRadius: 14, background: color, display: "grid", placeItems: "center", fontWeight: 900, fontSize: 18}}>{number}</div>
        <div style={{fontSize: 34, fontWeight: 900}}>{title}</div>
      </div>
      <div style={{fontSize: 24, lineHeight: 1.35, color: COLORS.muted, marginTop: 20}}>{body}</div>
    </div>
  );
};

const WorkflowScene: React.FC = () => {
  const frame = useCurrentFrame();
  const arrowDraw = progress(frame, 24, 68);
  const iconDraw = progress(frame, 8, 48);
  const cards = [
    {x: 120, y: 255, title: "Find", body: "Extract the essential idea from the source.", number: "01", color: COLORS.yellow},
    {x: 540, y: 255, title: "Frame", body: "Choose one visual story for each beat.", number: "02", color: COLORS.blue},
    {x: 960, y: 255, title: "Draw", body: "Build it from cards, ink, charts, and icons.", number: "03", color: COLORS.orange},
    {x: 1380, y: 255, title: "Move", body: "Synchronize every reveal with the narration.", number: "04", color: COLORS.green},
  ];

  return (
    <SceneShell duration={SCENE_DURATIONS[1]} label="Workflow scene" index={2}>
      <div style={{position: "absolute", left: 110, top: 110, fontSize: 58, fontWeight: 900}}>A creator workflow that explains itself</div>
      <svg width={WIDTH} height={HEIGHT} style={{position: "absolute", inset: 0}}>
        <SvgDefs />
        <InkPath d="M480 361 C510 340 520 343 540 361" draw={arrowDraw} stroke={COLORS.orange} width={5} dash="0.025 0.022" />
        <InkPath d="M900 361 C930 340 940 343 960 361" draw={arrowDraw} stroke={COLORS.orange} width={5} dash="0.025 0.022" />
        <InkPath d="M1320 361 C1350 340 1360 343 1380 361" draw={arrowDraw} stroke={COLORS.orange} width={5} dash="0.025 0.022" />
        <InkPath d="M526 349 L541 360 L526 371 M946 349 L961 360 L946 371 M1366 349 L1381 360 L1366 371" draw={arrowDraw} stroke={COLORS.orange} width={5} />
        <InkPath d="M1454 521 C1447 651 1244 650 1137 668 C995 690 941 776 806 774 C643 772 574 666 392 686" draw={progress(frame, 58, 55)} stroke={COLORS.orange} width={5} dash="0.018 0.02" />
      </svg>
      {cards.map((card, index) => <WorkflowCard key={card.title} {...card} delay={10 + index * 9} />)}
      <div style={{position: "absolute", left: 155, top: 520, transform: "rotate(-7deg)"}}><BulbDoodle draw={iconDraw} /></div>
      <div style={{position: "absolute", left: 760, top: 560, transform: "rotate(4deg)"}}><CameraDoodle draw={iconDraw} /></div>
      <div style={{position: "absolute", right: 170, top: 540, transform: "rotate(5deg)"}}><ChartDoodle draw={iconDraw} /></div>
      <div style={{position: "absolute", left: 650, right: 650, bottom: 112, textAlign: "center", fontSize: 27, lineHeight: 1.35, color: COLORS.muted}}>
        The layout is deterministic. The movement is frame-driven. The feeling stays human.
      </div>
    </SceneShell>
  );
};

const HeroMetricScene: React.FC = () => {
  const frame = useCurrentFrame();
  const pop = spring({frame: frame - 10, fps: FPS, config: {damping: 13, stiffness: 105}});
  const draw = progress(frame, 18, 55);
  const accent = progress(frame, 34, 18);

  return (
    <SceneShell duration={SCENE_DURATIONS[2]} label="Hero metric" index={3}>
      <div style={{position: "absolute", left: 0, right: 0, top: 170, textAlign: "center"}}>
        <div style={{fontSize: 31, fontWeight: 850, color: COLORS.muted, letterSpacing: 3, textTransform: "uppercase"}}>Four visual layers</div>
        <div style={{position: "relative", display: "inline-block", marginTop: 18, transform: `scale(${0.88 + pop * 0.12})`}}>
          <div style={{position: "absolute", left: 23, top: 20, fontSize: 290, lineHeight: 1, fontWeight: 950, color: COLORS.orange, zIndex: 0}}>4×</div>
          <div style={{position: "relative", fontSize: 290, lineHeight: 1, fontWeight: 950, color: COLORS.paper, WebkitTextStroke: `7px ${COLORS.ink}`, zIndex: 1}}>4×</div>
        </div>
        <div style={{fontSize: 42, fontWeight: 750, marginTop: 12}}>structure · illustration · motion · narration</div>
      </div>
      <div style={{position: "absolute", left: 140, top: 190, transform: "rotate(-8deg)"}}><CameraDoodle draw={draw} /></div>
      <div style={{position: "absolute", right: 140, top: 145, transform: "rotate(5deg)"}}><ChartDoodle draw={draw} /></div>
      <div style={{position: "absolute", left: 180, bottom: 115, transform: "rotate(6deg)"}}><BulbDoodle draw={draw} color={COLORS.blue} /></div>
      <div style={{position: "absolute", right: 190, bottom: 85, transform: "scale(.8) rotate(-4deg)"}}><RobotDoodle draw={draw} /></div>
      <svg width="900" height="120" viewBox="0 0 900 120" style={{position: "absolute", left: 510, bottom: 130}}>
        <SvgDefs />
        <InkPath d="M20 72 C104 37 151 100 226 60 C309 15 374 104 457 61 C535 20 596 98 674 58 C742 24 807 74 878 35" draw={accent} stroke={COLORS.yellow} width={13} />
      </svg>
    </SceneShell>
  );
};

const ComparisonScene: React.FC = () => {
  const frame = useCurrentFrame();
  const leftIn = progress(frame, 8, 24);
  const rightIn = progress(frame, 20, 24);
  const draw = progress(frame, 20, 60);

  return (
    <SceneShell duration={SCENE_DURATIONS[3]} label="Wrong versus right" index={4}>
      <div style={{position: "absolute", left: 120, top: 118, fontSize: 58, fontWeight: 900}}>From information blocks to guided understanding</div>
      <div style={{position: "absolute", left: 86, top: 220, width: 825, height: 650, borderRadius: 34, background: "rgba(238,238,238,.68)", border: "2px solid rgba(23,23,23,.1)", opacity: leftIn, transform: `translateX(${(1 - leftIn) * -50}px)`}}>
        <div style={{position: "absolute", left: 48, top: 42, fontSize: 82, color: COLORS.red, fontWeight: 300}}>×</div>
        <div style={{position: "absolute", left: 132, top: 76, width: 470, height: 340, background: "#3d3d3d", transform: "rotate(-3deg)", border: `5px solid ${COLORS.ink}`, boxShadow: "inset 0 0 80px rgba(255,255,255,.12)"}}>
          <div style={{display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 13, padding: 50}}>
            {Array.from({length: 20}, (_, index) => <div key={index} style={{height: 18, background: index % 3 ? "#777" : "#aaa", opacity: 0.55}} />)}
          </div>
        </div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 70, textAlign: "center", fontSize: 34, fontWeight: 850}}>A wall of information</div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 32, textAlign: "center", fontSize: 24, color: COLORS.muted}}>Accurate—but difficult to follow.</div>
      </div>
      <div style={{position: "absolute", right: 86, top: 220, width: 825, height: 650, borderRadius: 34, background: COLORS.card, border: "2px solid rgba(23,23,23,.1)", opacity: rightIn, transform: `translateX(${(1 - rightIn) * 50}px)`}}>
        <div style={{position: "absolute", left: 54, top: 40, fontSize: 82, color: COLORS.green, fontWeight: 300}}>✓</div>
        <div style={{position: "absolute", left: 285, top: 75, transform: "scale(1.18)"}}><RobotDoodle draw={draw} /></div>
        <div style={{position: "absolute", left: 145, top: 380, width: 540, height: 10, background: "rgba(23,23,23,.09)", borderRadius: 20}}>
          <div style={{width: `${draw * 100}%`, height: "100%", background: COLORS.orange, borderRadius: 20}} />
        </div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 70, textAlign: "center", fontSize: 34, fontWeight: 850}}>A guided visual story</div>
        <div style={{position: "absolute", left: 0, right: 0, bottom: 32, textAlign: "center", fontSize: 24, color: COLORS.muted}}>One idea enters. One idea lands.</div>
      </div>
    </SceneShell>
  );
};

const QuoteScene: React.FC = () => {
  const frame = useCurrentFrame();
  const border = progress(frame, 4, 50);
  const textIn = progress(frame, 16, 22);
  const highlightOne = progress(frame, 36, 15);
  const highlightTwo = progress(frame, 54, 15);
  const draw = progress(frame, 12, 58);

  const highlighted = (word: string, amount: number) => (
    <span style={{position: "relative", display: "inline-block", zIndex: 1}}>
      <span style={{position: "absolute", left: -8, right: -8, bottom: 4, height: "58%", background: COLORS.yellow, opacity: 0.58, transformOrigin: "left center", transform: `scaleX(${amount}) rotate(-1deg)`, zIndex: -1}} />
      {word}
    </span>
  );

  return (
    <SceneShell duration={SCENE_DURATIONS[4]} label="Quote and emphasis" index={5}>
      <svg width={WIDTH} height={HEIGHT} style={{position: "absolute", inset: 0}}>
        <SvgDefs />
        <InkPath d="M250 190 C591 176 929 190 1262 181 C1460 176 1610 192 1666 223 L1668 779 C1614 825 1392 813 1199 818 C812 825 537 810 248 821 Z" draw={border} width={6} />
        <InkPath d="M1658 227 C1694 316 1687 611 1668 779" draw={border} stroke={COLORS.orange} width={11} />
        <InkPath d="M250 819 C651 833 1106 817 1451 823" draw={border} stroke={COLORS.orange} width={11} />
      </svg>
      <div style={{position: "absolute", left: 365, right: 360, top: 315, textAlign: "center", fontSize: 74, lineHeight: 1.28, letterSpacing: -2, opacity: textIn}}>
        “When a visual {highlighted("explains", highlightOne)},<br />the mind {highlighted("remembers", highlightTwo)}.”
      </div>
      <div style={{position: "absolute", left: 170, bottom: 95, transform: "scale(.76) rotate(-5deg)"}}><RobotDoodle draw={draw} happy /></div>
      <div style={{position: "absolute", right: 170, top: 130, transform: "scale(.9) rotate(6deg)"}}><ShieldDoodle draw={draw} /></div>
      <svg viewBox="0 0 210 150" width="210" height="150" style={{position: "absolute", right: 180, bottom: 100}}>
        <SvgDefs />
        <InkPath d="M15 52 C36 17 79 24 103 55 C130 14 184 24 195 65 C205 107 153 129 105 145 C62 128 9 104 15 52 Z" draw={draw} stroke={COLORS.ink} width={6} fill={COLORS.red} opacity={0.65} />
        <InkPath d="M101 56 C87 75 98 87 112 76 C125 65 122 48 108 46 C94 44 82 57 83 76 C84 97 103 111 123 105" draw={draw} width={4} />
      </svg>
    </SceneShell>
  );
};

const ClosingScene: React.FC = () => {
  const frame = useCurrentFrame();
  const title = progress(frame, 6, 22);
  const draw = progress(frame, 12, 54);
  const chips = ["Scene brain", "Ink system", "Motion grammar", "Consistent output"];

  return (
    <SceneShell duration={SCENE_DURATIONS[5]} label="Prototype verdict" index={6}>
      <div style={{position: "absolute", left: 120, top: 170, width: 1000, opacity: title}}>
        <div style={{fontSize: 30, color: COLORS.orange, fontWeight: 900, letterSpacing: 4, textTransform: "uppercase"}}>The experiment works</div>
        <div style={{fontSize: 92, lineHeight: 1.03, fontWeight: 950, letterSpacing: -4, marginTop: 18}}>A Notebook Sketch engine can live inside Video Flow.</div>
        <div style={{display: "flex", flexWrap: "wrap", gap: 16, marginTop: 46}}>
          {chips.map((chip, index) => {
            const chipIn = progress(frame, 23 + index * 7, 15);
            return <div key={chip} style={{padding: "14px 24px", borderRadius: 18, background: [COLORS.yellow, COLORS.blue, COLORS.orange, COLORS.green][index], fontSize: 24, fontWeight: 850, border: `3px solid ${COLORS.ink}`, opacity: chipIn, transform: `translateY(${(1 - chipIn) * 18}px) rotate(${index % 2 ? 1 : -1}deg)`}}>{chip}</div>;
          })}
        </div>
        <div style={{fontSize: 27, lineHeight: 1.45, color: COLORS.muted, marginTop: 40, maxWidth: 900}}>This render uses deterministic React, SVG, seeded texture, and frame-based animation—without generating a new image for every scene.</div>
      </div>
      <div style={{position: "absolute", right: 170, top: 210, transform: `scale(${0.85 + draw * 0.15}) rotate(2deg)`}}><RobotDoodle draw={draw} /></div>
      <div style={{position: "absolute", right: 100, bottom: 90, transform: "scale(.82) rotate(-7deg)"}}><ChartDoodle draw={draw} /></div>
      <svg width="620" height="90" viewBox="0 0 620 90" style={{position: "absolute", left: 120, bottom: 105}}>
        <SvgDefs />
        <InkPath d="M10 56 C107 39 178 63 264 50 C347 38 438 64 610 38" draw={draw} stroke={COLORS.orange} width={10} />
      </svg>
    </SceneShell>
  );
};

const NotebookSketchComposition: React.FC = () => {
  const scenes = [
    <IntroScene key="intro" />,
    <WorkflowScene key="workflow" />,
    <HeroMetricScene key="metric" />,
    <ComparisonScene key="comparison" />,
    <QuoteScene key="quote" />,
    <ClosingScene key="closing" />,
  ];
  let from = 0;

  return (
    <AbsoluteFill style={{background: COLORS.paper}}>
      {scenes.map((scene, index) => {
        const duration = SCENE_DURATIONS[index];
        const sceneFrom = from;
        from += duration;
        return (
          <Sequence
            key={index}
            from={sceneFrom}
            durationInFrames={duration}
            premountFor={FPS}
            name={`Notebook Sketch ${index + 1}`}
          >
            {scene}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const NotebookSketchRoot: React.FC = () => (
  <Composition
    id="NotebookSketchPoC"
    component={NotebookSketchComposition}
    durationInFrames={TOTAL_FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);
