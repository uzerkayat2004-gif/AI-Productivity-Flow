/**
 * Video Flow V3 Layered WebGL Runtime Player Host.
 *
 * Architecture:
 * - Layer 1 (Bottom): HTML5 Media Element (<video> or <audio>) for audio track & native player controls
 * - Layer 2 (Middle): Three.js WebGL canvas (procedural 3D spatial world / assemblies / meshes)
 * - Layer 3 (Top): PixiJS v8 WebGL canvas (foreground 2D compositors / charts / typography / hud)
 * - Authoritative Master Clock & Media Sync: state = Scene(t) evaluated on every requestAnimationFrame tick
 * - Pointer Events: Both WebGL canvases maintain pointer-events: none so native player controls
 *   (play, pause, scrub, volume, speed) stay 100% interactive and clickable at all times.
 *
 * Scene Graph Lifecycle:
 * - Fixes the "One-Page Animation" bug by cleanly unmounting and disposing previous scene graphs,
 *   retaining continuity objects across scene transitions, creating new scene-specific Pixi and Three.js
 *   structures, and re-binding the camera grammar controller on every scene transition.
 *
 * Global Audio Timeline Seeking:
 * - seek(tSec) maps timeline time to active scene index and scene-local time t_local,
 *   smoothly synchronizing audio offset across both single-master and per-scene audio tracks.
 */

import * as THREE from "three";
import { Application, Container, Graphics, Text } from "pixi.js";
import {
  ArtDirectionGenome,
  DEFAULT_ART_GENOME,
  ExecutableSceneProgram,
  ExecutableElement2D,
  ExecutableNode3D,
  SemanticRepresentationType,
  VideoProgramV3,
} from "../contracts/video-program";
import { compiler2D, createSceneContainer, updateSceneAt } from "../compiler2d/index";
import { compiler3D, createCameraController, CameraGrammarController } from "../compiler3d/index";
import { safeColor, geometryCompiler3D } from "../compiler3d/geometry";
import { AbsoluteTimeClock } from "./clock";

export interface VideoPlayerV3Options {
  bottomPadding?: number;
  syncMediaElement?: HTMLMediaElement | null;
  autoPlay?: boolean;
  onStateUpdate?: ((state: { currentTime: number; sceneIndex: number; scene: ExecutableSceneProgram; sceneTime: number }) => void) | null;
  width?: number;
  height?: number;
}

export interface SeekResult {
  sceneIndex: number;
  sceneLocalTime: number;
  currentScene: ExecutableSceneProgram;
}

export class VideoPlayerV3 {
  private container: HTMLElement;
  private options: VideoPlayerV3Options;
  private clock: AbsoluteTimeClock;
  private program: VideoProgramV3 | null = null;
  private scenes: ExecutableSceneProgram[] = [];
  private genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME;
  private syncMediaElement: HTMLMediaElement | null = null;
  private internalAudio: HTMLAudioElement | null = null;

  // Viewport dimensions
  public width: number = 1280;
  public height: number = 720;

  // Three.js Runtime (Layer 2)
  public threeScene: THREE.Scene | null = null;
  public threeCamera: THREE.PerspectiveCamera | null = null;
  public threeRenderer: THREE.WebGLRenderer | null = null;
  public threeMeshes: THREE.Mesh[] = [];
  public threeGroup: THREE.Group | null = null;
  public threeCanvas: HTMLCanvasElement | null = null;
  private cameraController: CameraGrammarController | null = null;
  private continuityMeshes3D: Map<string, THREE.Object3D> = new Map();

  // PixiJS Runtime (Layer 3)
  public pixiApp: Application | null = null;
  public pixiCanvas: HTMLCanvasElement | null = null;
  public activePixiSceneContainer: Container | null = null;
  private continuityObjects2D: Map<string, Container> = new Map();

  // State Tracking
  public currentRenderedSceneId: string | null = null;
  public activeSceneIndex: number = 0;
  public isReady: boolean = false;
  private initPromise: Promise<void>;
  private isDestroyed: boolean = false;
  private animFrameId: number | null = null;
  private isLoopRunning: boolean = false;
  private boundListeners: Array<{ target: EventTarget; event: string; handler: EventListenerOrEventListenerObject }> = [];
  private resizeObserver: ResizeObserver | null = null;

  constructor(container: HTMLElement, options: VideoPlayerV3Options = {}) {
    this.container = container;
    this.options = options;
    this.width = options.width || container.clientWidth || 1280;
    this.height = options.height || container.clientHeight || 720;
    this.clock = new AbsoluteTimeClock(0);
    this.syncMediaElement = options.syncMediaElement || null;
    this.internalAudio = typeof Audio !== "undefined" ? new Audio() : null;

    this.initPromise = this.initRenderers();

    if (this.syncMediaElement) {
      this.attachMediaSync(this.syncMediaElement);
    }

    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.handleResize());
      this.resizeObserver.observe(this.container);
    }
  }

  /**
   * Initialize both Three.js and PixiJS canvas layers and mount inside container.
   * Both canvases strictly receive pointer-events: none so player controls remain 100% interactive.
   */
  public async initRenderers(): Promise<void> {
    const W = this.width;
    const H = this.height;

    // 1. Initialize Three.js Layer (Layer 2 - zIndex 2)
    try {
      this.threeScene = new THREE.Scene();
      this.threeCamera = new THREE.PerspectiveCamera(45, W / H, 0.1, 1000);
      this.threeCamera.position.set(0, 2, 8);

      // Studio Lighting Rig
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      ambientLight.name = "AmbientLight";
      const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
      keyLight.name = "KeyLight";
      keyLight.position.set(6, 12, 8);
      const rimLight = new THREE.PointLight(0x06cfe5, 1.2, 50);
      rimLight.name = "RimLight";
      rimLight.position.set(-8, -4, -6);

      this.threeScene.add(ambientLight);
      this.threeScene.add(keyLight);
      this.threeScene.add(rimLight);

      this.threeGroup = new THREE.Group();
      this.threeGroup.name = "Scene3DRoot";
      this.threeScene.add(this.threeGroup);

      this.cameraController = createCameraController("HeroFocus", new THREE.Vector3(0, 0, 0));

      if (typeof document !== "undefined") {
        const canvas3D = document.createElement("canvas");
        canvas3D.width = W;
        canvas3D.height = H;
        canvas3D.style.position = "absolute";
        canvas3D.style.top = "0";
        canvas3D.style.left = "0";
        canvas3D.style.width = "100%";
        canvas3D.style.height = "100%";
        canvas3D.style.zIndex = "2";
        canvas3D.style.pointerEvents = "none";
        canvas3D.setAttribute("data-layer", "three-3d");
        this.threeCanvas = canvas3D;
        this.container.appendChild(canvas3D);

        try {
          this.threeRenderer = new THREE.WebGLRenderer({
            canvas: canvas3D,
            alpha: true,
            antialias: true,
            powerPreference: "high-performance",
          });
          this.threeRenderer.setSize(W, H);
          this.threeRenderer.setPixelRatio(Math.min(2, typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1));
        } catch {
          // WebGL fallback for headless/test environments
        }
      }
    } catch (e) {
      console.warn("[VideoPlayerV3] Three.js init warning:", e);
    }

    // 2. Initialize PixiJS Layer (Layer 3 - zIndex 3)
    try {
      if (typeof document !== "undefined") {
        const canvas2D = document.createElement("canvas");
        canvas2D.width = W;
        canvas2D.height = H;
        canvas2D.style.position = "absolute";
        canvas2D.style.top = "0";
        canvas2D.style.left = "0";
        canvas2D.style.width = "100%";
        canvas2D.style.height = "100%";
        canvas2D.style.zIndex = "3";
        canvas2D.style.pointerEvents = "none";
        canvas2D.setAttribute("data-layer", "pixi-2d");
        this.pixiCanvas = canvas2D;
        this.container.appendChild(canvas2D);

        this.pixiApp = new Application();
        try {
          await this.pixiApp.init({
            canvas: canvas2D,
            width: W,
            height: H,
            backgroundAlpha: 0,
            antialias: true,
            resolution: Math.min(2, typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1),
            autoDensity: true,
          });
        } catch {
          // Headless test fallback
        }
      }
    } catch (e) {
      console.warn("[VideoPlayerV3] PixiJS init warning:", e);
    }

    this.isReady = true;

    // Render initial frame if scenes were already loaded
    if (this.scenes.length > 0) {
      this.updateAtTime(0);
    }

    if (this.options.autoPlay) {
      this.play();
    }
  }

  /**
   * Load Video Program, scenes, and optional genome/audio.
   */
  public async loadProgram(
    program: VideoProgramV3,
    scenes: ExecutableSceneProgram[] = [],
    masterAudioUrl?: string,
    genome?: Partial<ArtDirectionGenome>
  ): Promise<void> {
    this.program = program;
    const rawScenes = scenes && scenes.length > 0 ? scenes : (program && (program as any).scenes ? (program as any).scenes : []);
    this.scenes = (rawScenes || []).map((s: any, idx: number) => {
      const dur = s.duration_sec || s.suggested_duration_sec || 5.0;
      const repType = s.representation_type || (s.elements_2d?.[0]?.compositor) || SemanticRepresentationType.PROCESS;
      const elements_2d = s.elements_2d && s.elements_2d.length > 0 ? s.elements_2d : (s.semantic_objects ? s.semantic_objects.map((obj: any, oIdx: number) => ({
        element_id: obj.object_id || `elem_${idx}_${oIdx}`,
        compositor: repType,
        layer: obj.role || "primary",
        style: { label: obj.label, fill: "#0f172a", accent: oIdx === 0 ? "#00e5ff" : "#38bdf8" },
        data: obj.properties || {},
      })) : []);
      return {
        ...s,
        duration_sec: dur,
        representation_type: repType,
        elements_2d,
      };
    });
    if (genome) this.genome = genome;

    const totalDuration = this.scenes.reduce((acc, s) => acc + (s.duration_sec || (s as any).suggested_duration_sec || 5.0), 0);
    this.clock.setDuration(totalDuration);

    if (masterAudioUrl && this.internalAudio && !this.syncMediaElement) {
      this.internalAudio.src = masterAudioUrl;
      this.internalAudio.load();
    }

    await this.initPromise;

    if (this.scenes.length > 0) {
      this.currentRenderedSceneId = null;
      this.activeSceneIndex = 0;
      this.updateAtTime(0);
    }

    if (this.options.autoPlay) {
      this.play();
    }
  }

  /**
   * Attach synchronization to native HTML5 Media Element (<video> or <audio>).
   */
  private attachMediaSync(media: HTMLMediaElement): void {
    const onTimeUpdate = () => {
      if (!this.isLoopRunning) {
        this.updateAtTime(media.currentTime);
      }
    };
    const onPlay = () => {
      this.startLoop();
    };
    const onPause = () => {
      this.stopLoop();
      this.updateAtTime(media.currentTime);
    };
    const onSeeking = () => {
      this.updateAtTime(media.currentTime);
    };
    const onSeeked = () => {
      this.updateAtTime(media.currentTime);
    };
    const onEnded = () => {
      this.stopLoop();
      this.updateAtTime(media.duration || 0);
    };

    media.addEventListener("timeupdate", onTimeUpdate);
    media.addEventListener("play", onPlay);
    media.addEventListener("pause", onPause);
    media.addEventListener("seeking", onSeeking);
    media.addEventListener("seeked", onSeeked);
    media.addEventListener("ended", onEnded);

    this.boundListeners.push(
      { target: media, event: "timeupdate", handler: onTimeUpdate },
      { target: media, event: "play", handler: onPlay },
      { target: media, event: "pause", handler: onPause },
      { target: media, event: "seeking", handler: onSeeking },
      { target: media, event: "seeked", handler: onSeeked },
      { target: media, event: "ended", handler: onEnded }
    );

    if (!media.paused) {
      this.startLoop();
    }
  }

  /**
   * Start requestAnimationFrame animation loop.
   */
  public startLoop(): void {
    if (this.isLoopRunning || this.isDestroyed) return;
    this.isLoopRunning = true;

    const tick = () => {
      if (!this.isLoopRunning || this.isDestroyed) return;

      const currentTime = this.syncMediaElement
        ? this.syncMediaElement.currentTime
        : this.clock.getTime();

      this.updateAtTime(currentTime);

      this.animFrameId = requestAnimationFrame(tick);
    };

    this.animFrameId = requestAnimationFrame(tick);
  }

  /**
   * Stop requestAnimationFrame animation loop.
   */
  public stopLoop(): void {
    this.isLoopRunning = false;
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  public play(): void {
    this.clock.play();
    if (this.syncMediaElement && this.syncMediaElement.paused) {
      this.syncMediaElement.play().catch(() => {});
    } else if (this.internalAudio && this.internalAudio.src && this.internalAudio.paused) {
      this.internalAudio.play().catch(() => {});
    }
    this.startLoop();
  }

  public pause(): void {
    this.clock.pause();
    if (this.syncMediaElement && !this.syncMediaElement.paused) {
      this.syncMediaElement.pause();
    } else if (this.internalAudio && !this.internalAudio.paused) {
      this.internalAudio.pause();
    }
    this.stopLoop();
  }

  /**
   * Global Audio Timeline Seeking:
   * Calculates active scene index, scene-local time t_local, and smoothly synchronizes narration audio offset.
   */
  public seek(timeSec: number): SeekResult | null {
    if (!this.scenes.length) return null;

    const totalDur = this.clock.getDuration();
    const clampedTime = Math.max(0, Math.min(totalDur > 0 ? totalDur : timeSec, timeSec));
    this.clock.seek(clampedTime);

    let accumulatedSec = 0;
    let sceneIndex = 0;
    let currentScene = this.scenes[0];
    let sceneStartSec = 0;

    for (let i = 0; i < this.scenes.length; i++) {
      const s = this.scenes[i];
      const dur = s.duration_sec || (s as any).suggested_duration_sec || 5.0;
      if (clampedTime >= accumulatedSec && clampedTime < accumulatedSec + dur) {
        currentScene = s;
        sceneIndex = i;
        sceneStartSec = accumulatedSec;
        break;
      }
      accumulatedSec += dur;
    }

    if (clampedTime >= accumulatedSec && this.scenes.length > 0) {
      sceneIndex = this.scenes.length - 1;
      currentScene = this.scenes[sceneIndex];
      const lastDur = currentScene.duration_sec || (currentScene as any).suggested_duration_sec || 5.0;
      sceneStartSec = Math.max(0, accumulatedSec - lastDur);
    }

    const sceneLocalTime = Math.max(0, clampedTime - sceneStartSec);
    this.activeSceneIndex = sceneIndex;

    // Synchronize media offset
    if (this.syncMediaElement) {
      this.syncMediaElement.currentTime = clampedTime;
    } else if (this.internalAudio) {
      if (currentScene.audio_segment_url && this.internalAudio.src !== currentScene.audio_segment_url) {
        this.internalAudio.src = currentScene.audio_segment_url;
        this.internalAudio.currentTime = sceneLocalTime;
      } else if (this.internalAudio.src) {
        this.internalAudio.currentTime = clampedTime;
      }
    }

    this.updateAtTime(clampedTime);

    return {
      sceneIndex,
      sceneLocalTime,
      currentScene,
    };
  }

  /**
   * Deterministically evaluate and render the scene state at timeline time t (seconds).
   */
  public updateAtTime(timeSec: number): void {
    if (!this.scenes.length || !this.isReady) return;

    let accumulatedSec = 0;
    let currentScene = this.scenes[0];
    let sceneStartSec = 0;
    let sceneIndex = 0;
    let found = false;

    for (let i = 0; i < this.scenes.length; i++) {
      const s = this.scenes[i];
      const dur = s.duration_sec || (s as any).suggested_duration_sec || 5.0;
      if (timeSec >= accumulatedSec && timeSec < accumulatedSec + dur) {
        currentScene = s;
        sceneIndex = i;
        sceneStartSec = accumulatedSec;
        found = true;
        break;
      }
      accumulatedSec += dur;
    }

    if (!found && this.scenes.length > 0) {
      sceneIndex = this.scenes.length - 1;
      currentScene = this.scenes[sceneIndex];
      const lastDur = currentScene.duration_sec || (currentScene as any).suggested_duration_sec || 5.0;
      sceneStartSec = Math.max(0, accumulatedSec - lastDur);
    }

    this.activeSceneIndex = sceneIndex;
    const sceneTimeSec = Math.max(0, timeSec - sceneStartSec);
    this.renderScene(currentScene, sceneTimeSec);

    if (typeof this.options.onStateUpdate === "function") {
      this.options.onStateUpdate({
        currentTime: timeSec,
        sceneIndex,
        scene: currentScene,
        sceneTime: sceneTimeSec,
      });
    }
  }

  /**
   * Render active scene state: updates PixiJS 2D objects and Three.js 3D meshes.
   * Handles scene unmounting, continuity extraction, and camera re-binding.
   */
  public renderScene(scene: ExecutableSceneProgram, sceneTimeSec: number): void {
    const isNewScene = this.currentRenderedSceneId !== scene.scene_id;
    this.currentRenderedSceneId = scene.scene_id;

    // 1. Update 3D Three.js Layer (Middle)
    this.updateThreeScene(scene, sceneTimeSec, isNewScene);

    // 2. Update 2D PixiJS Layer (Top)
    this.updatePixiScene(scene, sceneTimeSec, isNewScene);
  }

  /**
   * PixiJS 2D Scene Graph Lifecycle:
   * Retains continuity objects, cleanly unmounts and disposes previous scene graph,
   * mounts and lays out the new scene-specific Pixi container.
   */
  private updatePixiScene(scene: ExecutableSceneProgram, sceneTimeSec: number, isNewScene: boolean): void {
    if (!this.pixiApp || !this.pixiApp.stage) return;

    if (isNewScene || !this.activePixiSceneContainer) {
      // 1. Extract and retain continuity objects marked for carry/match
      const preservedContinuity = new Map<string, Container>();
      if (this.activePixiSceneContainer) {
        const nextContinuityKeys = new Set(
          (scene.elements_2d || [])
            .map((e) => e.continuity_key || (e.data && e.data.continuity_key) || (e.style && e.style.continuity_id) || (e.carry_over ? e.element_id : null))
            .filter((k): k is string => Boolean(k))
        );

        if (nextContinuityKeys.size > 0) {
          this.activePixiSceneContainer.children.forEach((child) => {
            const childKey = (child as any).continuityKey || (child as any).name;
            if (childKey && nextContinuityKeys.has(childKey)) {
              preservedContinuity.set(childKey, child as Container);
              this.activePixiSceneContainer?.removeChild(child);
            }
          });
        }

        // 2. Cleanly unmount and dispose previous scene graph
        this.pixiApp.stage.removeChild(this.activePixiSceneContainer);
        this.activePixiSceneContainer.destroy({ children: true });
        this.activePixiSceneContainer = null;
      }

      // 3. Mount and layout the new scene-specific Pixi container
      this.activePixiSceneContainer = createSceneContainer(scene, this.genome, this.width, this.height);

      // Re-inject preserved continuity objects if applicable
      preservedContinuity.forEach((child, key) => {
        (child as any).continuityKey = key;
        this.activePixiSceneContainer?.addChild(child);
      });

      this.pixiApp.stage.addChild(this.activePixiSceneContainer);
    }

    // Smoothly animate display objects over absolute time
    if (this.activePixiSceneContainer) {
      updateSceneAt(this.activePixiSceneContainer, scene, sceneTimeSec, this.width, this.height, this.genome);
    }

    if (this.pixiApp.renderer) {
      this.pixiApp.render();
    }
  }

  private active3DCompiledResult: { dispose: () => void; update: (t: number, dur: number) => void } | null = null;

  /**
   * Three.js 3D Scene Graph Lifecycle:
   * Compiles and animates real procedural 3D assemblies, exploded structures, layer stacks,
   * rotating dotted globes, and mechanisms from geometryCompiler3D with studio lighting & camera grammar.
   */
  private updateThreeScene(scene: ExecutableSceneProgram, sceneTimeSec: number, isNewScene: boolean): void {
    if (!this.threeScene || !this.threeGroup) return;

    if (isNewScene) {
      // 1. Cleanly dispose previous procedural 3D result
      if (this.active3DCompiledResult) {
        try {
          this.active3DCompiledResult.dispose();
        } catch (_) {}
        this.active3DCompiledResult = null;
      }

      while (this.threeGroup.children.length > 0) {
        const obj = this.threeGroup.children[0];
        this.threeGroup.remove(obj);
      }
      this.threeMeshes = [];

      const nodes3D = scene.nodes_3d || [];
      const repType = String(scene.representation_type || "").toUpperCase();

      // 2. Compile real procedural 3D geometry scene
      try {
        let activeNode = nodes3D[0];

        if (!activeNode) {
          let procType = "ASSEMBLY";
          if (repType.includes("EXPLODE") || repType.includes("EXPLODED")) procType = "EXPLODED_ASSEMBLY";
          else if (repType.includes("CUTAWAY")) procType = "CUTAWAY";
          else if (repType.includes("LAYER_STACK") || repType.includes("LAYERSTACK")) procType = "LAYER_STACK_3D";
          else if (repType.includes("FLOW") || repType.includes("PIPE")) procType = "FLOW_PATH";
          else if (repType.includes("TRAJECTORY") || repType.includes("ORBIT")) procType = "TRAJECTORY";
          else if (repType.includes("MECHANISM") || repType.includes("GEAR")) procType = "MECHANISM";
          else if (repType.includes("SPATIAL") || repType.includes("NETWORK") || repType.includes("MAP") || repType.includes("SYSTEM")) procType = "SPATIAL_SYSTEM";

          activeNode = {
            node_id: `proc_${scene.scene_id}`,
            procedural_type: procType,
            transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
            material_spec: {},
            animation_keyframes: [],
          };
        }

        const result = geometryCompiler3D.compileProceduralNode(activeNode, this.genome);
        this.threeGroup.add(result.group);
        this.active3DCompiledResult = result;
      } catch (err) {
        console.warn("[VideoPlayerV3] 3D procedural compiler fallback:", err);
      }

      // 3. Re-bind Camera Grammar Controller & Target
      const shotGrammar = (scene as any).shot_grammar || this.genome?.camera_grammar || "HeroFocus";
      this.cameraController = createCameraController(shotGrammar, new THREE.Vector3(0, 0, 0));
      if (this.threeCamera) {
        this.threeCamera.aspect = this.width / Math.max(1, this.height);
        this.threeCamera.updateProjectionMatrix();
      }
    }

    const dur = scene.duration_sec || 5.0;

    // 4. Smooth Procedural 3D Motion Updates (Explode progress, gear rotations, pulse rings)
    if (this.active3DCompiledResult && typeof this.active3DCompiledResult.update === "function") {
      this.active3DCompiledResult.update(sceneTimeSec, dur);
    }

    // 5. Camera Grammar Updates
    if (this.threeCamera && this.cameraController) {
      this.cameraController.update(this.threeCamera, sceneTimeSec, dur);
    } else if (this.threeCamera) {
      this.threeCamera.position.x = Math.sin(sceneTimeSec * 0.2) * 0.8;
      this.threeCamera.position.y = Math.cos(sceneTimeSec * 0.25) * 0.4 + 2;
      this.threeCamera.lookAt(0, 0, 0);
    }

    if (this.threeRenderer && this.threeCamera) {
      this.threeRenderer.render(this.threeScene, this.threeCamera);
    }
  }


  /**
   * Dynamic Resizing:
   * Handles container bounds resize while keeping bottom player controls interactive.
   */
  private handleResize(): void {
    if (!this.container || this.isDestroyed) return;
    const newW = this.container.clientWidth || 1280;
    const newH = this.container.clientHeight || 720;
    if (newW === this.width && newH === this.height) return;

    this.width = newW;
    this.height = newH;

    if (this.threeRenderer && this.threeCamera) {
      this.threeCamera.aspect = newW / Math.max(1, newH);
      this.threeCamera.updateProjectionMatrix();
      this.threeRenderer.setSize(newW, newH);
    }

    if (this.pixiApp && this.pixiApp.renderer) {
      this.pixiApp.renderer.resize(newW, newH);
      if (this.currentRenderedSceneId) {
        this.currentRenderedSceneId = null; // Re-layout active scene on resize
      }
    }

    const currentTime = this.syncMediaElement ? this.syncMediaElement.currentTime : this.clock.getTime();
    this.updateAtTime(currentTime);
  }

  public getCurrentState(): { currentScene: ExecutableSceneProgram; timeSec: number; elements2D: any[]; nodes3D: any[] } | null {
    if (!this.scenes.length) return null;

    const tSec = this.syncMediaElement ? this.syncMediaElement.currentTime : this.clock.tick();
    let accumulatedSec = 0;
    let currentScene = this.scenes[0];

    for (const s of this.scenes) {
      const dur = s.duration_sec || 5.0;
      if (tSec >= accumulatedSec && tSec <= accumulatedSec + dur) {
        currentScene = s;
        break;
      }
      accumulatedSec += dur;
    }

    const sceneTimeSec = Math.max(0, tSec - accumulatedSec);
    const elements2D = compiler2D.evaluateAt(currentScene, sceneTimeSec);
    const nodes3D = compiler3D.evaluateAt(currentScene, sceneTimeSec);

    this.renderScene(currentScene, sceneTimeSec);

    return {
      currentScene,
      timeSec: tSec,
      elements2D,
      nodes3D,
    };
  }

  /**
   * Destroy player instance, release WebGL contexts, event listeners, and DOM canvases.
   */
  public destroy(): void {
    this.isDestroyed = true;
    this.stopLoop();

    for (const l of this.boundListeners) {
      l.target.removeEventListener(l.event, l.handler);
    }
    this.boundListeners = [];

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }

    if (this.internalAudio) {
      this.internalAudio.pause();
      this.internalAudio.src = "";
      this.internalAudio = null;
    }

    // Dispose Three.js
    if (this.threeScene && this.threeGroup) {
      while (this.threeGroup.children.length > 0) {
        const obj = this.threeGroup.children[0];
        this.threeGroup.remove(obj);
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
        if ((obj as THREE.Mesh).material) {
          const mat = (obj as THREE.Mesh).material;
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else mat.dispose();
        }
      }
    }
    if (this.threeRenderer) {
      this.threeRenderer.dispose();
      this.threeRenderer = null;
    }
    if (this.threeCanvas && this.threeCanvas.parentNode) {
      this.threeCanvas.parentNode.removeChild(this.threeCanvas);
      this.threeCanvas = null;
    }

    // Dispose PixiJS
    if (this.activePixiSceneContainer) {
      this.activePixiSceneContainer.destroy({ children: true });
      this.activePixiSceneContainer = null;
    }
    if (this.pixiApp) {
      this.pixiApp.destroy(true, { children: true, texture: true, textureSource: true });
      this.pixiApp = null;
    }
    if (this.pixiCanvas && this.pixiCanvas.parentNode) {
      this.pixiCanvas.parentNode.removeChild(this.pixiCanvas);
      this.pixiCanvas = null;
    }
  }
}
