/**
 * =============================================================================
 * VOICE FLOW — BILLION-DOLLAR COMPANY INTRO (SPLASH CONTROLLER)
 * 3D Spatial Levitation • Volumetric Breathing Glow • Spatial Dust Canvas
 * Tracked Brand Typography • Precision Glowing Progress Filament
 * Interactive 3D Gyroscopic Parallax • Microscopic Spatial Embers
 * =============================================================================
 */

(function () {
  "use strict";

  let isRunning = false;
  let hasSkipped = false;
  let timeouts = [];
  let dismissTimer = null;
  let animFrameId = null;
  let particles = [];

  function clearAllTimers() {
    timeouts.forEach((id) => clearTimeout(id));
    timeouts = [];
    if (dismissTimer) {
      clearTimeout(dismissTimer);
      dismissTimer = null;
    }
  }

  /**
   * Spatial Dust Micro-Embers Canvas System
   */
  function setupParticles(canvas) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function resize() {
      if (!canvas) return;
      canvas.width = window.innerWidth || 1280;
      canvas.height = window.innerHeight || 800;
    }
    resize();
    window.addEventListener("resize", resize);

    particles = [];
    for (let i = 0; i < 48; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        z: Math.random() * 0.8 + 0.2, // depth perspective factor
        radius: Math.random() * 1.6 + 0.6,
        dx: (Math.random() - 0.5) * 0.25,
        dy: -Math.random() * 0.35 - 0.1, // float upward gently
        alpha: Math.random() * 0.45 + 0.15,
        phase: Math.random() * Math.PI * 2
      });
    }

    function renderLoop() {
      if (!canvas || hasSkipped) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.x += p.dx;
        p.y += p.dy;
        p.phase += 0.02;

        if (p.y < -10) {
          p.y = canvas.height + 10;
          p.x = Math.random() * canvas.width;
        }
        if (p.x < -10) p.x = canvas.width + 10;
        if (p.x > canvas.width + 10) p.x = -10;

        const currentAlpha = p.alpha * (0.7 + 0.3 * Math.sin(p.phase));
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius * p.z, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 175, 75, ${(currentAlpha * p.z).toFixed(3)})`;
        ctx.shadowBlur = 6 * p.z;
        ctx.shadowColor = "rgba(255, 120, 0, 0.6)";
        ctx.fill();
      }

      animFrameId = requestAnimationFrame(renderLoop);
    }

    if (animFrameId) cancelAnimationFrame(animFrameId);
    animFrameId = requestAnimationFrame(renderLoop);
  }

  function stopParticles() {
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
  }

  /**
   * Fast-forward / dismiss the splash screen immediately into the app.
   */
  function skipSplashAnimation() {
    if (hasSkipped) return;
    hasSkipped = true;
    isRunning = false;
    clearAllTimers();
    stopParticles();

    const overlay = document.getElementById("vf-splash-overlay");
    const logoMonolith = document.getElementById("vf-logo-monolith");

    if (logoMonolith) {
      logoMonolith.classList.remove("levitating");
      logoMonolith.classList.add("dissolving");
    }

    if (overlay) {
      overlay.classList.add("vf-splash-fadeout");
      dismissTimer = setTimeout(() => {
        overlay.style.display = "none";
        dismissTimer = null;
      }, 350);
    }
  }

  /**
   * Main startup choreography sequencer.
   */
  function launchSplashChoreography() {
    const overlay = document.getElementById("vf-splash-overlay");
    const nebula = document.getElementById("vf-splash-ambient-nebula");
    const core = document.getElementById("vf-splash-ambient-core");
    const logoMonolith = document.getElementById("vf-logo-monolith");
    const meta = document.getElementById("vf-brand-meta");
    const track = document.getElementById("vf-loader-track");
    const filament = document.getElementById("vf-loader-filament");
    const statusText = document.getElementById("vf-status-text");
    const canvas = document.getElementById("vf-splash-particles-canvas");

    if (!overlay || !logoMonolith) return;

    clearAllTimers();
    hasSkipped = false;
    isRunning = true;

    // Reset initial states
    overlay.style.display = "flex";
    overlay.classList.remove("vf-splash-fadeout");
    if (nebula) {
      nebula.classList.remove("active");
      nebula.style.opacity = "";
    }
    if (core) {
      core.classList.remove("active");
      core.style.opacity = "";
    }
    logoMonolith.classList.remove("revealed", "levitating", "dissolving");
    logoMonolith.style.transform = "";
    if (meta) meta.classList.remove("active");
    if (track) track.classList.remove("active");
    if (filament) {
      filament.style.width = "0%";
      filament.style.transition = "";
    }
    if (statusText) {
      statusText.classList.remove("active", "ready");
      statusText.textContent = "INITIALIZING...";
    }

    // Force layout reflow
    void logoMonolith.offsetWidth;

    // Initialize particle canvas
    setupParticles(canvas);

    // Overlay click dismisses intro cleanly
    overlay.onclick = () => skipSplashAnimation();

    const handleKeyDown = (e) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
        skipSplashAnimation();
        window.removeEventListener("keydown", handleKeyDown);
      }
    };
    window.addEventListener("keydown", handleKeyDown);

    // Interactive 3D mouse parallax tracking
    const handleMouseMove = (e) => {
      if (!logoMonolith || !logoMonolith.classList.contains("revealed") || logoMonolith.classList.contains("dissolving")) return;
      const mouseX = e.clientX / window.innerWidth - 0.5;
      const mouseY = e.clientY / window.innerHeight - 0.5;
      const tiltX = -mouseY * 8;
      const tiltY = mouseX * 10;
      logoMonolith.style.transform = `translateY(0px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`;
    };
    window.addEventListener("mousemove", handleMouseMove);

    // Stage 1: Atmospheric Volumetric Nebula & Core Awakening (T = 80ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        if (nebula) nebula.classList.add("active");
        if (core) core.classList.add("active");
      }, 80)
    );

    // Stage 2: 3D Logo Monolith Spatial Emergence from Depth (T = 250ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        logoMonolith.classList.add("revealed");
      }, 250)
    );

    // Stage 3: Natural Levitation & Brand Typography Reveal (T = 1100ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        logoMonolith.classList.add("levitating");
        if (meta) meta.classList.add("active");
      }, 1100)
    );

    // Stage 4: Precision Progress Filament Activation (T = 1450ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        if (track) track.classList.add("active");
        if (statusText) {
          statusText.classList.add("active");
          statusText.textContent = "CALIBRATING WORKSPACE...";
        }
        if (filament) {
          filament.style.transition = "width 1.5s cubic-bezier(0.22, 1, 0.36, 1)";
          filament.style.width = "75%";
        }
      }, 1450)
    );

    // Stage 5: Filament advances to 100% & System Ready (T = 2200ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        if (filament) filament.style.width = "100%";
        if (statusText) {
          statusText.textContent = "READY";
          statusText.classList.add("ready");
        }
      }, 2200)
    );

    // Stage 6: Seamless Dissolve into Active App (T = 2850ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        logoMonolith.classList.remove("levitating");
        logoMonolith.classList.add("dissolving");
        if (nebula) nebula.style.opacity = "0";
        if (core) core.style.opacity = "0";
        if (overlay) overlay.classList.add("vf-splash-fadeout");
      }, 2850)
    );

    // Stage 7: Complete Overlay Cleanup (T = 3450ms)
    timeouts.push(
      setTimeout(() => {
        if (hasSkipped) return;
        if (overlay) overlay.style.display = "none";
        stopParticles();
        isRunning = false;
        window.removeEventListener("keydown", handleKeyDown);
        window.removeEventListener("mousemove", handleMouseMove);
      }, 3450)
    );
  }

  /**
   * Replay function available globally for testing or user inspection.
   */
  window.replaySplashAnimation = function () {
    clearAllTimers();
    stopParticles();
    hasSkipped = false;
    launchSplashChoreography();
  };

  /**
   * Run immediately when DOM is ready.
   */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", launchSplashChoreography);
  } else {
    launchSplashChoreography();
  }
})();
