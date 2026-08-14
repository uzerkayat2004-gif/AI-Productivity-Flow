import {writeFileSync} from "node:fs";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {bundle} from "@remotion/bundler";
import {openBrowser, renderFrames, selectComposition} from "@remotion/renderer";

const [entryPoint, manifestPath, publicDir, outputDir] = process.argv.slice(2);
if (!entryPoint || !manifestPath || !publicDir || !outputDir) {
  throw new Error("Usage: render-keyframes <entry> <manifest> <public-dir> <output-dir>");
}

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const fps = Number(manifest.fps || 24);
const frameRecords = [];
let sceneFrom = 0;

for (const [sceneIndex, scene] of manifest.scenes.entries()) {
  const sceneFrames = Math.max(1, Math.ceil(Number(scene.durationSeconds || 1) * fps));
  const ratios = [0.12];
  for (const beat of scene.visualBeats || []) {
    ratios.push(Math.min(0.9, Math.max(0.12, Number(beat.endRatio ?? beat.startRatio ?? 0.5))));
  }
  ratios.push(0.9);
  const uniqueFrames = [...new Set(ratios.map((ratio) => Math.min(sceneFrames - 1, Math.max(0, Math.round((sceneFrames - 1) * ratio)))))].sort((a, b) => a - b);
  for (const localFrame of uniqueFrames) {
    frameRecords.push({
      sceneIndex,
      localFrame,
      globalFrame: sceneFrom + localFrame,
      timeSeconds: localFrame / fps,
    });
  }
  sceneFrom += sceneFrames;
}

await mkdir(outputDir, {recursive: true});
const serveUrl = await bundle({
  entryPoint: path.resolve(entryPoint),
  publicDir: path.resolve(publicDir),
  outDir: path.join(outputDir, "bundle"),
  enableCaching: true,
  onProgress: () => undefined,
});
const chromiumOptions = {gl: "angle"};
const browser = await openBrowser("chrome", {chromeMode: "headless-shell", logLevel: "error", chromiumOptions});

try {
  const composition = await selectComposition({
    serveUrl,
    id: "VideoFlow",
    inputProps: manifest,
    puppeteerInstance: browser,
    logLevel: "error",
    chromeMode: "headless-shell",
    chromiumOptions,
  });
  const byFrame = new Map(frameRecords.map((record) => [record.globalFrame, record]));
  await renderFrames({
    chromiumOptions,
    serveUrl,
    composition,
    inputProps: manifest,
    frames: frameRecords.map((record) => record.globalFrame),
    outputDir: null,
    imageFormat: "jpeg",
    jpegQuality: 95,
    scale: 2 / 3,
    muted: true,
    concurrency: "50%",
    puppeteerInstance: browser,
    logLevel: "error",
    chromeMode: "headless-shell",
    onStart: () => undefined,
    onFrameUpdate: () => undefined,
    onFrameBuffer: (buffer, frame) => {
      const record = byFrame.get(frame);
      const filename = `scene-${String(record.sceneIndex + 1).padStart(3, "0")}-${String(record.localFrame).padStart(6, "0")}.jpg`;
      record.filename = filename;
      writeFileSync(path.join(outputDir, filename), buffer);
    },
  });
} finally {
  await browser.close({silent: true});
}

const scenes = manifest.scenes.map((scene, sceneIndex) => ({
  sceneIndex,
  durationSeconds: Number(scene.durationSeconds || 1),
  audioFile: scene.audioFile || null,
  frames: frameRecords.filter((record) => record.sceneIndex === sceneIndex),
}));
await writeFile(path.join(outputDir, "keyframes.json"), JSON.stringify({fps, scenes}, null, 2));
