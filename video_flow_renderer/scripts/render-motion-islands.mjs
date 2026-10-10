import {writeFileSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {bundle} from "@remotion/bundler";
import {openBrowser, renderFrames, selectComposition} from "@remotion/renderer";

const [entryPoint, manifestPath, publicDir, outputDir] = process.argv.slice(2);
if (!entryPoint || !manifestPath || !publicDir || !outputDir) {
  throw new Error("Usage: render-motion-islands <entry> <manifest> <public-dir> <output-dir>");
}
const resolvedEntryPoint = path.resolve(entryPoint);
const resolvedManifestPath = path.resolve(manifestPath);
const resolvedPublicDir = path.resolve(publicDir);
const resolvedOutputDir = path.resolve(outputDir);
const manifest = JSON.parse(await readFile(resolvedManifestPath, "utf8"));
if (!manifest || typeof manifest !== "object") throw new Error("Motion-island manifest must be an object.");
const fps = Number.isFinite(Number(manifest.fps)) && Number(manifest.fps) > 0 ? Number(manifest.fps) : 24;
const scenes = Array.isArray(manifest.scenes) ? manifest.scenes : [];
if (!scenes.length) throw new Error("Motion-island manifest requires at least one scene.");
await mkdir(resolvedOutputDir, {recursive: true});

const packedPath = path.join(resolvedOutputDir, "packed-motion.mp4");
const destinationsByFrame = new Map();
const results = [];
let sceneFrom = 0;
let packedFrom = 0;
const addDestination = (globalFrame, destination) => {
  const destinations = destinationsByFrame.get(globalFrame) || [];
  destinations.push(destination);
  destinationsByFrame.set(globalFrame, destinations);
};
for (const [sceneIndex, scene] of scenes.entries()) {
  const sceneFrames = Math.max(1, Number(scene.durationInFrames) || Math.round(Number(scene.durationSeconds || 1) * fps));
  const requested = Array.isArray(scene?.motionPlan?.renderWindows) && scene.motionPlan.renderWindows.length
    ? scene.motionPlan.renderWindows
    : [{startRatio: 0, endRatio: Math.min(.25, 48 / sceneFrames)}];
  const windows = requested.filter((window) => window && typeof window === "object").map((window) => {
    const hasStartFrame = Number.isFinite(Number(window.startFrame));
    const hasEndFrame = Number.isFinite(Number(window.endFrame));
    return {
      startFrame: Math.max(0, Math.min(sceneFrames - 1, hasStartFrame
        ? Math.floor(Number(window.startFrame))
        : Math.floor(Number(window.startRatio || 0) * sceneFrames))),
      endFrame: Math.max(0, Math.min(sceneFrames - 1, hasEndFrame
        ? Math.ceil(Number(window.endFrame))
        : Math.ceil(Number(window.endRatio || .1) * sceneFrames))),
    };
  }).filter((window) => window.endFrame >= window.startFrame);
  const normalized = [];
  for (const window of windows) {
    const previous = normalized.at(-1);
    if (previous && window.startFrame <= previous.endFrame + 1) previous.endFrame = Math.max(previous.endFrame, window.endFrame);
    else normalized.push({...window});
  }
  const sceneDir = path.join(resolvedOutputDir, `scene-${String(sceneIndex + 1).padStart(3, "0")}`);
  await mkdir(sceneDir, {recursive: true});
  const stillFrames = [0, ...normalized.map((window) => window.endFrame)];
  const stills = stillFrames.map((localFrame, stillIndex) => {
    const destination = path.join(sceneDir, `hold-${stillIndex}.jpg`);
    addDestination(sceneFrom + localFrame, destination);
    return {localFrame, path: destination};
  });
  const renderedWindows = normalized.map((window) => {
    const packedStartFrame = packedFrom;
    for (let localFrame = window.startFrame; localFrame <= window.endFrame; localFrame += 1) {
      const destination = path.join(resolvedOutputDir, `packed-${String(packedFrom).padStart(8, "0")}.jpg`);
      addDestination(sceneFrom + localFrame, destination);
      packedFrom += 1;
    }
    return {...window, packedStartFrame, path: packedPath};
  });
  results.push({
    sceneIndex,
    durationSeconds: Number(scene.durationSeconds || 1),
    durationFrames: sceneFrames,
    audioFile: scene.audioFile || null,
    motionPlan: scene.motionPlan || null,
    windows: renderedWindows,
    stills,
  });
  sceneFrom += sceneFrames;
}
if (!packedFrom) throw new Error("No semantic motion frames were planned.");

const serveUrl = await bundle({
  entryPoint: resolvedEntryPoint,
  publicDir: resolvedPublicDir,
  outDir: path.join(resolvedOutputDir, "bundle"),
  enableCaching: true,
  onProgress: () => undefined,
});
const chromiumOptions = {gl: "angle"};
const browser = await openBrowser("chrome", {chromeMode: "headless-shell", logLevel: "error", chromiumOptions});
try {
  const compositionId = manifest.engineVersion === "agentic-visual.v1" ? "AgenticVideoFlow" : "VideoFlow";
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps: manifest,
    puppeteerInstance: browser,
    logLevel: "error",
    chromeMode: "headless-shell",
    chromiumOptions,
  });
  await renderFrames({
    serveUrl,
    composition,
    inputProps: manifest,
    frames: [...destinationsByFrame.keys()].sort((a, b) => a - b),
    outputDir: null,
    imageFormat: "jpeg",
    jpegQuality: 92,
    scale: 2 / 3,
    chromiumOptions,
    muted: true,
    concurrency: "50%",
    puppeteerInstance: browser,
    logLevel: "error",
    chromeMode: "headless-shell",
    onStart: () => undefined,
    onFrameUpdate: () => undefined,
    onFrameBuffer: (buffer, frame) => {
      for (const destination of destinationsByFrame.get(frame) || []) writeFileSync(destination, buffer);
    },
  });
} finally {
  await browser.close({silent: true});
}
const encode = spawnSync("ffmpeg", [
  "-y", "-hide_banner", "-loglevel", "error", "-framerate", String(fps),
  "-i", path.join(resolvedOutputDir, "packed-%08d.jpg"), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
  "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", packedPath,
], {encoding: "utf8"});
if (encode.status !== 0) throw new Error(`Packed motion encoding failed: ${encode.stderr || encode.stdout}`);
await writeFile(path.join(resolvedOutputDir, "motion-islands.json"), JSON.stringify({
  fps,
  packedFps: fps,
  packedMotionFrames: packedFrom,
  equivalentFullFrames: sceneFrom,
  scenes: results,
}, null, 2));

