import fs from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import sharp from "sharp";
import {icons} from "@phosphor-icons/core";

const [, , manifestArg, publicArg] = process.argv;
if (!manifestArg || !publicArg) {
  throw new Error("Usage: prepare-illustration-assets <manifest> <public-dir>");
}

const manifestPath = path.resolve(manifestArg);
const publicDir = path.resolve(publicArg);
const outputDir = path.join(publicDir, "illustrations");
const here = path.dirname(fileURLToPath(import.meta.url));
const iconRoot = path.resolve(here, "..", "node_modules", "@phosphor-icons", "core", "assets");
await fs.mkdir(outputDir, {recursive: true});

const plan = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const art = plan.artDirection || {};
const palette = art.palette || plan.visualLanguage?.palette || {};
const ink = palette.text || "#171612";
const muted = palette.muted || "#69665f";
const accents = palette.accents || ["#e9812d", "#efc84b", "#5598b4", "#cb6256", "#77916a"];
const domain = plan.illustrationBible?.domain || plan.visualLanguage?.domain || "general";
const treatment = art.assetTreatment || "engraved";

const alias = {
  "email": "envelope-simple", "credential": "identification-card", "request": "paper-plane-tilt",
  "cursor": "cursor-click", "clock": "clock", "timer": "timer", "fingerprint": "fingerprint-simple",
  "laptop": "laptop", "terminal": "terminal-window", "server": "hard-drives", "database": "database",
  "service": "circles-three-plus", "queue": "queue", "packet": "package", "chip": "cpu",
  "cloud": "cloud", "lock": "lock-key", "gate": "door-open", "shield": "shield-check", "key": "key",
  "book": "book-open-text", "page": "file-text", "pencil": "pencil-line", "brain": "brain",
  "question": "question", "annotation": "note-pencil", "memory-path": "path", "example": "lightbulb-filament",
  "ledger": "notebook", "coin": "coins", "bar-chart": "chart-bar", "scale": "scales",
  "target": "target", "market-arrow": "trend-up", "risk-meter": "gauge", "customer": "user-circle",
  "player": "person-simple-run", "controller": "game-controller", "level-map": "map-trifold",
  "trophy": "trophy", "health-bar": "battery-high", "skill-tree": "tree-structure", "boss": "skull",
  "flask": "flask", "molecule": "atom", "atom": "atom", "microscope": "microscope",
  "specimen": "bug", "cell": "circles-three", "wave": "wave-sine", "gauge": "gauge",
  "heart": "heart", "pulse": "heartbeat", "body": "person-arms-spread", "care-team": "users-three",
  "medicine": "pill", "recovery-path": "path", "scan": "scan",
  "ingredient": "carrot", "bowl": "bowl-food", "flame": "fire", "knife": "knife",
  "pan": "cooking-pot", "plate": "bowl-steam", "steam": "steam-logo",
  "tree": "tree-evergreen", "leaf": "leaf", "river": "waves", "sun": "sun",
  "root": "plant", "animal": "paw-print", "water-drop": "drop",
  "document": "file-text", "idea": "lightbulb-filament", "person": "person-simple",
  "path": "path", "tool": "wrench", "signal": "broadcast", "result": "check-circle"
};

const domainSatellites = {
  study: ["bookmark-simple", "pencil-simple-line", "brain", "graduation-cap", "magnifying-glass"],
  business: ["coins", "briefcase", "chart-line-up", "target", "handshake"],
  gaming: ["game-controller", "map-trifold", "trophy", "sword", "flag-checkered"],
  science: ["atom", "flask", "microscope", "wave-sine", "magnifying-glass"],
  technology: ["cpu", "code", "database", "cloud", "circuitry"],
  health: ["heartbeat", "first-aid", "pill", "stethoscope", "person-arms-spread"],
  food: ["fork-knife", "bowl-food", "fire", "timer", "leaf"],
  nature: ["leaf", "drop", "sun", "cloud", "plant"],
  security: ["shield-check", "lock-key", "warning-octagon", "fingerprint-simple", "key"],
  general: ["lightbulb-filament", "arrow-right", "magnifying-glass", "check-circle", "sparkle"]
};

const clean = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const tokens = (value) => clean(value).split(/\s+/).filter((item) => item.length > 1);
const hasIcon = (name, weight = "duotone") => fs.access(path.join(iconRoot, weight, `${name}-${weight}.svg`)).then(() => true).catch(() => false);
const catalog = icons.filter((item) => !String(item.categories || []).toLowerCase().includes("brand"));

function stableSeed(value) {
  let hash = 2166136261;
  for (const char of String(value)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

async function chooseIcon(kind, label, salt = 0) {
  const direct = alias[clean(kind).replace(/ /g, "-")];
  if (direct && await hasIcon(direct)) return direct;
  const query = new Set([...tokens(kind), ...tokens(label)]);
  const ranked = catalog.map((item) => {
    const nameTokens = new Set(tokens(item.name));
    const tagTokens = new Set((item.tags || []).flatMap(tokens));
    const categoryTokens = new Set((item.categories || []).flatMap(tokens));
    let score = 0;
    for (const token of query) {
      if (nameTokens.has(token)) score += 9;
      if (tagTokens.has(token)) score += 5;
      if (categoryTokens.has(token)) score += 1;
      if (item.name.includes(token)) score += 2;
    }
    return {name: item.name, score, tie: stableSeed(`${item.name}|${salt}`)};
  }).filter((item) => item.score > 0).sort((a, b) => b.score - a.score || a.tie - b.tie);
  for (const item of ranked.slice(0, 12)) {
    if (await hasIcon(item.name)) return item.name;
  }
  return "lightbulb-filament";
}

async function iconBody(name, weight, color, accent) {
  const suffix = weight === "regular" ? "" : `-${weight}`;
  let file = path.join(iconRoot, weight, `${name}${suffix}.svg`);
  try { await fs.access(file); } catch { file = path.join(iconRoot, weight, `lightbulb-filament${suffix}.svg`); }
  let svg = await fs.readFile(file, "utf8");
  const open = svg.indexOf(">");
  svg = svg.slice(open + 1).replace(/<\/svg>\s*$/i, "");
  svg = svg.replace(/currentColor/g, color);
  if (weight === "duotone") {
    svg = svg.replace(/<path([^>]*?)\sopacity="0\.2"/i, `<path$1 fill="${accent}" opacity="0.24"`);
  }
  return svg;
}

function wobblePath(seed, width = 320, height = 260) {
  const points = [];
  for (let index = 0; index < 7; index += 1) {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / 7;
    const radiusX = width * (0.42 + ((seed >> (index % 12)) & 7) / 170);
    const radiusY = height * (0.42 + ((seed >> ((index + 5) % 12)) & 7) / 170);
    points.push([180 + Math.cos(angle) * radiusX, 180 + Math.sin(angle) * radiusY]);
  }
  return `M ${points.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L ")} Z`;
}

async function buildVignette(prop, scene, sceneIndex, propIndex, destination) {
  const signature = `${scene.motionPlan?.illustrationPlan?.signature || "scene"}|${prop.id}|${prop.label}|${treatment}`;
  const seed = stableSeed(signature);
  const accent = accents[Number(prop.accent || propIndex) % accents.length];
  const iconName = await chooseIcon(prop.kind, prop.label, seed);
  const satellites = domainSatellites[domain] || domainSatellites.general;
  const satelliteA = satellites[(seed + propIndex) % satellites.length];
  const satelliteB = satellites[(Math.floor(seed / 17) + sceneIndex + 2) % satellites.length];
  const weight = treatment === "cutout" || treatment === "marker-wash" ? "duotone" : treatment === "technical" ? "regular" : "thin";
  const [main, smallA, smallB] = await Promise.all([
    iconBody(iconName, weight, ink, accent),
    iconBody(satelliteA, treatment === "cutout" ? "duotone" : "thin", ink, accent),
    iconBody(satelliteB, "thin", ink, accent),
  ]);
  const rotate = ((seed % 9) - 4) * 0.55;
  const hatchX = 26 + (seed % 24);
  const blob = wobblePath(seed, 265, 235);
  const rough = treatment === "technical" || treatment === "cutout" ? "" : `filter="url(#rough)"`;
  const satelliteMarkup = treatment === "technical"
    ? `<g transform="translate(12 22) scale(.18)" opacity=".52">${smallA}</g><g transform="translate(296 286) scale(.16)" opacity=".45">${smallB}</g>`
    : treatment === "cutout"
      ? `<g transform="translate(286 270) scale(.24)" opacity=".78">${smallA}</g><rect x="28" y="38" width="72" height="21" rx="2" fill="#e8d49f" opacity=".72" transform="rotate(-7 64 48)"/>`
      : treatment === "marker-wash"
        ? `<g transform="translate(286 270) scale(.2)" opacity=".58" ${rough}>${smallA}</g>`
        : `<g transform="translate(10 18) scale(.22)" opacity=".58" ${rough}>${smallA}</g><g transform="translate(288 274) scale(.22)" opacity=".58" ${rough}>${smallB}</g>`;
  const decoration = treatment === "technical"
    ? `<rect x="18" y="18" width="324" height="324" fill="none" stroke="${accent}" stroke-width="1.3" opacity=".26"/><path d="M18 72H342 M72 18V342 M288 18V342 M18 288H342" fill="none" stroke="${ink}" stroke-width=".8" opacity=".10"/><path d="M28 118h22 M39 107v22 M310 238h22 M321 227v22" stroke="${accent}" stroke-width="2" opacity=".62"/>`
    : treatment === "cutout"
      ? `<path d="${blob}" fill="${accent}" opacity=".20" transform="translate(8 11) rotate(${rotate} 180 180)"/><path d="${blob}" fill="#ffffff" stroke="${ink}" stroke-width="1.5" opacity=".88"/><path d="M44 309 C 116 321, 212 302, 326 315" fill="none" stroke="${accent}" stroke-width="9" stroke-linecap="round" opacity=".78"/>`
      : treatment === "marker-wash"
        ? `<path d="${blob}" fill="${accent}" opacity=".13"/><path d="M ${hatchX} 308 C 88 319, 142 307, 196 318 S 294 313, 334 296" fill="none" stroke="${accent}" stroke-width="8" stroke-linecap="round" opacity=".62"/><circle cx="312" cy="185" r="18" fill="none" stroke="${accent}" stroke-width="5" opacity=".38"/>`
        : treatment === "archive"
          ? `<rect x="18" y="18" width="324" height="324" fill="none" stroke="${ink}" stroke-width="2" opacity=".42"/><rect x="31" y="31" width="298" height="298" fill="url(#hatch)" opacity=".20"/><circle cx="296" cy="72" r="37" fill="none" stroke="${accent}" stroke-width="5" opacity=".48"/><path d="M273 72h46 M296 49v46" stroke="${accent}" stroke-width="2" opacity=".48"/>`
          : `<path d="${blob}" fill="url(#hatch)" opacity=".45"/><path d="${blob}" fill="none" stroke="${accent}" stroke-width="1.4" stroke-dasharray="3 13" opacity=".45" transform="rotate(${rotate} 180 180)"/><path d="M286 48 C318 67 321 99 296 118" fill="none" stroke="${ink}" stroke-width="1.7" opacity=".44"/>`;
  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
    <defs>
      <filter id="rough" x="-8%" y="-8%" width="116%" height="116%">
        <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2" seed="${seed % 97}" result="noise"/>
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="0.75" xChannelSelector="R" yChannelSelector="G"/>
      </filter>
      <filter id="shadow" x="-12%" y="-12%" width="130%" height="130%"><feDropShadow dx="7" dy="8" stdDeviation="0" flood-color="${accent}" flood-opacity=".34"/></filter>
      <pattern id="hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(21)"><line x1="0" y1="0" x2="0" y2="9" stroke="${ink}" stroke-width="1" opacity="0.22"/></pattern>
    </defs>
    ${decoration}
    <g transform="translate(52 45)" ${rough} ${treatment === "cutout" ? 'filter="url(#shadow)"' : ""} opacity=".98">${main}</g>
    ${satelliteMarkup}
  </svg>`;
  await sharp(Buffer.from(svg)).png({compressionLevel: 8}).toFile(destination);
  return {iconName, satelliteA, satelliteB, treatment};
}
const jobs = [];
const resolved = [];
for (const [sceneIndex, scene] of (plan.scenes || []).entries()) {
  const illustration = scene.motionPlan?.illustrationPlan;
  if (!illustration) continue;
  for (const [propIndex, prop] of (illustration.props || []).entries()) {
    const filename = `scene-${String(sceneIndex + 1).padStart(3, "0")}-${prop.id}.png`;
    const destination = path.join(outputDir, filename);
    jobs.push(buildVignette(prop, scene, sceneIndex, propIndex, destination).then((meta) => {
      prop.assetFile = `illustrations/${filename}`;
      prop.assetKind = `phosphor-${treatment}-vignette`;
      prop.resolvedIcon = meta.iconName;
      resolved.push(meta.iconName);
    }));
  }
  illustration.assetRenderer = "editorial-storyboard-v5";
}
await Promise.all(jobs);
plan.illustrationAssets = {
  version: 1,
  renderer: "editorial-storyboard-v5",
  library: "Phosphor Icons 2.1.1",
  license: "MIT",
  generatedAssets: jobs.length,
  uniqueIcons: [...new Set(resolved)].length,
  domain,
};
if (plan.motionSystem) {
  plan.motionSystem.name = "notebook-explanation-director-v5";
  plan.motionSystem.version = 5;
  plan.motionSystem.renderer = "editorial-storyboard-v5";
}
if (plan.visualLanguage) plan.visualLanguage.renderer = "editorial-storyboard-v5";
await fs.writeFile(manifestPath, JSON.stringify(plan, null, 2), "utf8");
process.stdout.write(JSON.stringify(plan.illustrationAssets));
