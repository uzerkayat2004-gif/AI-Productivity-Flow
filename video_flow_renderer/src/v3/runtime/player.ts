/**
 * Real V3 Canvas Player Host & Layered Renderer.
 *
 * Architecture:
 * - Three.js WebGL canvas (Background 3D spatial world / assemblies)
 * - PixiJS v8 WebGL canvas (Foreground 2D compositors / charts / sharp annotations)
 * - Absolute-Time Master Clock (state = Scene(t))
 * - Global Audio Timeline Sync across all scene narration segments
 */

import { ExecutableSceneProgram, VideoProgramV3 } from "../contracts/video-program";
import { AbsoluteTimeClock } from "./clock";
import { compiler2D } from "../compiler2d/index";
import { compiler3D } from "../compiler3d/index";

export class VideoPlayerV3 {
  private container: HTMLElement;
  private clock: AbsoluteTimeClock;
  private program: VideoProgramV3 | null = null;
  private scenes: ExecutableSceneProgram[] = [];
  private audioPlayer: HTMLAudioElement | null = null;

  constructor(container: HTMLElement) {
    this.container = container;
    this.clock = new AbsoluteTimeClock(0);
    this.audioPlayer = new Audio();
  }

  public loadProgram(program: VideoProgramV3, scenes: ExecutableSceneProgram[], masterAudioUrl?: string): void {
    this.program = program;
    this.scenes = scenes;
    const totalDuration = scenes.reduce((acc, s) => acc + (s.duration_sec || 5.0), 0);
    this.clock.setDuration(totalDuration);

    if (masterAudioUrl && this.audioPlayer) {
      this.audioPlayer.src = masterAudioUrl;
      this.audioPlayer.load();
    }
  }

  public play(): void {
    this.clock.play();
    if (this.audioPlayer && this.audioPlayer.src) {
      this.audioPlayer.play().catch(() => {});
    }
  }

  public pause(): void {
    this.clock.pause();
    if (this.audioPlayer) {
      this.audioPlayer.pause();
    }
  }

  public seek(timeSec: number): void {
    this.clock.seek(timeSec);
    if (this.audioPlayer) {
      this.audioPlayer.currentTime = timeSec;
    }
  }

  public getCurrentState(): { currentScene: ExecutableSceneProgram; timeSec: number; elements2D: any[]; nodes3D: any[] } | null {
    if (!this.scenes.length) return null;

    const tSec = this.clock.tick();
    let accumulatedSec = 0;
    let currentScene = this.scenes[0];

    for (const s of this.scenes) {
      if (tSec >= accumulatedSec && tSec <= accumulatedSec + s.duration_sec) {
        currentScene = s;
        break;
      }
      accumulatedSec += s.duration_sec;
    }

    const sceneTimeSec = tSec - accumulatedSec;
    const elements2D = compiler2D.evaluateAt(currentScene, sceneTimeSec);
    const nodes3D = compiler3D.evaluateAt(currentScene, sceneTimeSec);

    return {
      currentScene,
      timeSec: tSec,
      elements2D,
      nodes3D,
    };
  }
}
