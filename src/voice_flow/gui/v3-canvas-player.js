/**
 * Video Flow V3 Canvas Player Host - Browser Runtime Integration.
 *
 * Mounts the production layered WebGL VideoPlayerV3 engine (Three.js bottom layer + PixiJS top layer)
 * inside .vf-player-container, synchronizing authoritative time with HTML5 video elements and
 * managing multi-scene segmented narration playback.
 */

(function (global) {
  "use strict";

  let v3BundlePromise = null;

  /**
   * Dynamically ensure the V3 runtime bundle is loaded.
   */
  function ensureV3RuntimeBundle() {
    if (global.VideoFlowV3Runtime && global.VideoFlowV3Runtime.VideoPlayerV3) {
      return Promise.resolve(global.VideoFlowV3Runtime);
    }
    if (v3BundlePromise) {
      return v3BundlePromise;
    }

    v3BundlePromise = new Promise((resolve, reject) => {
      // Check if already injected
      const existingScript = document.querySelector('script[src*="v3-renderer.bundle.js"], script[src*="runtime-bundle.js"]');
      if (existingScript) {
        if (global.VideoFlowV3Runtime && global.VideoFlowV3Runtime.VideoPlayerV3) {
          resolve(global.VideoFlowV3Runtime);
          return;
        }
        let resolved = false;
        existingScript.addEventListener("load", () => {
          if (resolved) return;
          resolved = true;
          if (global.VideoFlowV3Runtime) resolve(global.VideoFlowV3Runtime);
          else reject(new Error("VideoFlowV3Runtime bundle loaded but global not found"));
        });
        existingScript.addEventListener("error", (e) => {
          if (resolved) return;
          resolved = true;
          reject(e);
        });
        const poll = setInterval(() => {
          if (global.VideoFlowV3Runtime && global.VideoFlowV3Runtime.VideoPlayerV3) {
            if (!resolved) {
              resolved = true;
              clearInterval(poll);
              resolve(global.VideoFlowV3Runtime);
            }
          }
        }, 20);
        setTimeout(() => {
          clearInterval(poll);
          if (!resolved && global.VideoFlowV3Runtime) {
            resolved = true;
            resolve(global.VideoFlowV3Runtime);
          }
        }, 2500);
        return;
      }

      const script = document.createElement("script");
      script.src = "/api/video-flow/v3/runtime-bundle.js";
      script.async = true;
      script.onload = () => {
        if (global.VideoFlowV3Runtime) {
          resolve(global.VideoFlowV3Runtime);
        } else {
          // Fallback check on direct bundle file
          const fallback = document.createElement("script");
          fallback.src = "v3-renderer.bundle.js";
          fallback.onload = () => resolve(global.VideoFlowV3Runtime);
          fallback.onerror = (err) => reject(err);
          document.head.appendChild(fallback);
        }
      };
      script.onerror = () => {
        const fallback = document.createElement("script");
        fallback.src = "v3-renderer.bundle.js";
        fallback.onload = () => resolve(global.VideoFlowV3Runtime);
        fallback.onerror = (err) => reject(err);
        document.head.appendChild(fallback);
      };
      document.head.appendChild(script);
    });

    return v3BundlePromise;
  }

  // Active player instances map per container
  const activePlayers = new WeakMap();

  /**
   * Mount or update the production Layered WebGL VideoPlayerV3 on a container.
   *
   * @param {HTMLElement} container - The target container element (e.g. .vf-player-container)
   * @param {Object} programData - The V3 Video Program data payload from /api/video-flow/v3/program
   * @param {Object} options - Mount options (syncMediaElement, bottomPadding, onStateUpdate, etc.)
   * @returns {Promise<Object>} The instantiated VideoPlayerV3 instance
   */
  async function mountV3CanvasPlayer(container, programData, options = {}) {
    if (!container) {
      console.warn("[V3CanvasPlayer] Invalid container element.");
      return null;
    }

    // Clean up any existing player on this container
    if (activePlayers.has(container)) {
      try {
        const oldPlayer = activePlayers.get(container);
        if (oldPlayer && typeof oldPlayer.destroy === "function") {
          oldPlayer.destroy();
        }
      } catch (e) {
        console.warn("[V3CanvasPlayer] Error destroying previous player:", e);
      }
      activePlayers.delete(container);
    }

    // Ensure V3 WebGL Runtime bundle is loaded
    const runtime = await ensureV3RuntimeBundle();
    if (!runtime || !runtime.VideoPlayerV3) {
      throw new Error("VideoFlowV3Runtime bundle failed to initialize.");
    }

    const { VideoPlayerV3 } = runtime;
    const playerOptions = {
      bottomPadding: options.bottomPadding ?? 52,
      syncMediaElement: options.syncMediaElement || null,
      autoPlay: options.autoPlay ?? false,
      onStateUpdate: options.onStateUpdate || null,
    };

    const player = new VideoPlayerV3(container, playerOptions);

    if (programData && (programData.program || programData.scenes)) {
      const program = programData.program || programData;
      const scenes = (programData.scenes && programData.scenes.length > 0) ? programData.scenes : (program.scenes || []);
      const masterAudioUrl = programData.master_audio_url || program.master_audio_url || "";
      const artGenome = programData.art_genome || program.art_genome || null;
      await player.loadProgram(program, scenes, masterAudioUrl, artGenome);
    }

    activePlayers.set(container, player);
    return player;
  }

  /**
   * Get active VideoPlayerV3 instance for a container.
   */
  function getV3Player(container) {
    return activePlayers.get(container) || null;
  }

  /**
   * Destroy active VideoPlayerV3 instance on a container.
   */
  function destroyV3Player(container) {
    if (activePlayers.has(container)) {
      const player = activePlayers.get(container);
      if (player && typeof player.destroy === "function") {
        player.destroy();
      }
      activePlayers.delete(container);
    }
  }

  // Export to global scope
  global.V3CanvasPlayer = {
    ensureBundle: ensureV3RuntimeBundle,
    mount: mountV3CanvasPlayer,
    getPlayer: getV3Player,
    destroy: destroyV3Player,
  };

  // Also expose runtime constructor when loaded
  ensureV3RuntimeBundle().then((rt) => {
    if (rt && rt.VideoPlayerV3) {
      global.VideoPlayerV3 = rt.VideoPlayerV3;
    }
  }).catch(() => {});

})(typeof window !== "undefined" ? window : globalThis);
