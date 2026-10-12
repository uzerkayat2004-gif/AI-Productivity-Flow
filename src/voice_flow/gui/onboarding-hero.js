/* Scene 1 Welcome Hero — native vector stage controller.
   - Scales the fixed 1920x1080 design stage to fit its card (text stays vector-sharp).
   - Draws the silky background ribbons as SVG paths.
   - Keeps the theme button label in sync and runs a caption clock when narration audio is unavailable. */
(() => {
  const NS = "http://www.w3.org/2000/svg";

  function buildRibbons(id = "s1-ribbons") {
    const svg = document.getElementById(id);
    if (!svg || svg.childElementCount) return;
    try {
    const frag = document.createDocumentFragment();
    const add = (d, cls) => {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", d);
      p.setAttribute("class", cls);
      frag.appendChild(p);
    };
    for (let i = 0; i < 18; i++) {
      const o = i * 13;
      const a = Math.max(0.12, 1 - i * 0.05).toFixed(2);
      // Left bundle: right half of tall ellipses (top -> right -> bottom)
      let cx = 160 + o, cy = 580 + i * 4, rx = 380, ry = 470;
      add(`M${cx} ${cy - ry} A${rx} ${ry} 0 0 1 ${cx} ${cy + ry}`, `rl1 a${i}`);
      cx = 120 + o; cy = 620 + i * 3;
      add(`M${cx} ${cy - ry} A${rx} ${ry} 0 0 1 ${cx} ${cy + ry}`, `rl2 a${i}`);
      // Right bundle: left half (bottom -> left -> top)
      cx = 1750 - o; cy = 540 + i * 3; rx = 390;
      add(`M${cx} ${cy + ry} A${rx} ${ry} 0 0 1 ${cx} ${cy - ry}`, `rr1 a${i}`);
      cx = 1800 - o; cy = 580 + i * 4;
      add(`M${cx} ${cy + ry} A${rx} ${ry} 0 0 1 ${cx} ${cy - ry}`, `rr2 a${i}`);
      frag.lastChild.style.opacity = a;
      frag.childNodes[frag.childNodes.length - 2].style.opacity = a;
      frag.childNodes[frag.childNodes.length - 3].style.opacity = a;
      frag.childNodes[frag.childNodes.length - 4].style.opacity = a;
    }
    svg.appendChild(frag);
    } catch (error) {
      // Decorative SVGs must never prevent stage or caption initialization.
    }
  }

  function fitStage() {
    ["s1-stage", "s2-stage", "s3-stage", "s4-stage", "s5-stage"].forEach(id => {
      const stage = document.getElementById(id);
      const vp = stage && stage.parentElement;
      if (!vp) return;
      const w = vp.clientWidth, h = vp.clientHeight;
      if (!w || !h) return;
      const s = Math.min(w / 1920, h / 1080);
      stage.style.transform = `translate(${(w - 1920 * s) / 2}px, ${(h - 1080 * s) / 2}px) scale(${s})`;
    });
  }

  function syncThemeLabel() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    ["scene1-theme-label", "scene2-theme-label", "scene3-theme-label", "scene4-theme-label", "scene5-theme-label"].forEach(id => {
      const label = document.getElementById(id);
      if (label) label.textContent = dark ? "Light Mode" : "Dark Mode";
    });
    ["scene1-theme-icon", "scene2-theme-icon", "scene3-theme-icon", "scene4-theme-icon", "scene5-theme-icon"].forEach(id => {
      const icon = document.getElementById(id);
      if (icon) icon.textContent = dark ? "☀️" : "🌙";
    });
  }

  // app.js owns narration and its timeupdate subtitles. This clock only
  // supplies Scene 1 captions while its narration is unavailable/nonplaying.
  let clockT = 0, lastTick = 0, captionFrame = null, observedPlayer = null;
  const audioEvents = ["playing", "pause", "ended", "error", "waiting", "canplay"];
  function audioPlayer() {
    return typeof onboardingAudioPlayer !== "undefined" ? onboardingAudioPlayer : null;
  }
  function scene1Visible() {
    const overlay = document.getElementById("onboarding-overlay");
    const stage = document.getElementById("s1-stage");
    const slide = stage && stage.closest(".onboarding-slide");
    return !document.hidden && overlay && !overlay.classList.contains("hidden") &&
      overlay.classList.contains("welcome-hero-mode") && slide && slide.classList.contains("active");
  }
  function needsCaptionClock() {
    const player = audioPlayer();
    return scene1Visible() && (!player || player.paused || player.ended || player.error || player.readyState < 3);
  }
  function syncCaptionClock() {
    const player = audioPlayer();
    if (player !== observedPlayer) {
      if (observedPlayer) audioEvents.forEach(event => observedPlayer.removeEventListener(event, syncCaptionClock));
      observedPlayer = player;
      if (player) audioEvents.forEach(event => player.addEventListener(event, syncCaptionClock));
    }
    if (!needsCaptionClock()) {
      if (captionFrame !== null) cancelAnimationFrame(captionFrame);
      captionFrame = null;
      lastTick = 0;
      if (!scene1Visible()) clockT = 0;
      return;
    }
    if (captionFrame === null) {
      // Resume fallback from the narration position after a playback failure.
      if (player && Number.isFinite(player.currentTime)) clockT = player.currentTime;
      captionFrame = requestAnimationFrame(tick);
    }
  }
  function tick(now) {
    captionFrame = null;
    if (!needsCaptionClock()) { syncCaptionClock(); return; }
    const dt = lastTick ? (now - lastTick) / 1000 : 0;
    clockT = (clockT + dt) % 40.5;
    lastTick = now;
    if (typeof updateOnboardingScene1Subtitles === "function") updateOnboardingScene1Subtitles(clockT, false);
    captionFrame = requestAnimationFrame(tick);
  }

  function init() {
    buildRibbons("s1-ribbons");
    buildRibbons("s2-ribbons");
    buildRibbons("s3-ribbons");
    buildRibbons("s4-ribbons");
    buildRibbons("s5-ribbons");
    syncThemeLabel();
    fitStage();
    [".scene1-stage-viewport", ".scene2-stage-viewport", ".scene3-stage-viewport", ".scene4-stage-viewport", ".scene5-stage-viewport"].forEach(sel => {
      const vp = document.querySelector(sel);
      if (vp && "ResizeObserver" in window) new ResizeObserver(fitStage).observe(vp);
    });
    window.addEventListener("resize", fitStage);
    new MutationObserver(syncThemeLabel).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const overlay = document.getElementById("onboarding-overlay");
    if (overlay) new MutationObserver(() => { fitStage(); syncCaptionClock(); }).observe(overlay, { attributes: true, subtree: true, attributeFilter: ["class"] });
    document.addEventListener("visibilitychange", syncCaptionClock);
    syncCaptionClock();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
