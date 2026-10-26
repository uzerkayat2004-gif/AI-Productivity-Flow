window.__e2e = window.__e2e || {};

window.__e2e.sleep = function (ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
};

window.__e2e.closeGuides = function () {
  try { if (typeof stopAudioFlowGuide === "function") stopAudioFlowGuide(false); } catch (err) {}
  try { if (typeof stopVideoFlowGuide === "function") stopVideoFlowGuide(false); } catch (err) {}
  try { if (typeof stopVoiceFlowGuide === "function") stopVoiceFlowGuide(false); } catch (err) {}
  var overlay = document.getElementById("onboarding-overlay");
  if (overlay) {
    overlay.classList.add("hidden");
    overlay.classList.remove("welcome-hero-mode");
  }
  if (typeof closeSettings === "function") {
    try { closeSettings(); } catch (err) {}
  }
};

window.__e2e.sceneState = function () {
  var slide = typeof onboardingSlide === "number" ? onboardingSlide : -1;
  var active = document.querySelector(".onboarding-slide.active");
  var buttons = active
    ? Array.prototype.map.call(active.querySelectorAll("button"), function (button) {
        return (button.innerText || button.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
      }).filter(Boolean)
    : [];
  var captionEl = document.getElementById("scene" + (slide + 1) + "-subtitle-text");
  var overlay = document.getElementById("onboarding-overlay");
  return {
    slide: slide,
    caption: captionEl ? captionEl.textContent : "",
    buttons: buttons,
    hasSkip: buttons.some(function (text) { return /skip tour/i.test(text); }),
    hasAuto: buttons.some(function (text) { return /^(auto|manual)$/i.test(text); }),
    hasBack: buttons.some(function (text) { return /back/i.test(text); }),
    hasNext: buttons.some(function (text) { return /next|get started|begin/i.test(text); }),
    overlayHidden: !overlay || overlay.classList.contains("hidden"),
  };
};

window.__e2e.prepScene = async function (index) {
  var overlay = document.getElementById("onboarding-overlay");
  if (!overlay) return { ok: false, error: "onboarding overlay missing" };
  if (overlay.classList.contains("hidden") && typeof replayOnboarding === "function") {
    replayOnboarding();
    await window.__e2e.sleep(500);
  }
  onboardingAutoMode = false;
  if (typeof updateOnboardingAutoModeUI === "function") updateOnboardingAutoModeUI();
  if (typeof gotoOnboardingSlide === "function") gotoOnboardingSlide(index);
  await window.__e2e.sleep(800);
  var updaters = [
    typeof updateOnboardingScene1Subtitles === "function" ? updateOnboardingScene1Subtitles : null,
    typeof updateOnboardingScene2Subtitles === "function" ? updateOnboardingScene2Subtitles : null,
    typeof updateOnboardingScene3Subtitles === "function" ? updateOnboardingScene3Subtitles : null,
    typeof updateOnboardingScene4Subtitles === "function" ? updateOnboardingScene4Subtitles : null,
    typeof updateOnboardingScene5Subtitles === "function" ? updateOnboardingScene5Subtitles : null,
  ];
  if (updaters[index]) updaters[index](6, true);
  if (typeof onboardingAudioPlayer !== "undefined" && onboardingAudioPlayer) {
    try {
      var duration = onboardingAudioPlayer.duration || 12;
      onboardingAudioPlayer.currentTime = Math.min(6, Math.max(1.2, duration * 0.28));
    } catch (err) {}
    try { onboardingAudioPlayer.pause(); } catch (err) {}
  }
  onboardingNarrationPaused = true;
  await window.__e2e.sleep(300);
  if (updaters[index]) updaters[index](6, true);
  await window.__e2e.sleep(200);
  var state = window.__e2e.sceneState();
  state.ok = state.slide === index && !state.overlayHidden && !!state.caption;
  return state;
};

window.__e2e.guideSpec = function (kind) {
  if (kind === "audio") {
    return {
      overlay: "audioflow-guide-overlay",
      caption: "af-guide-subtitle-text",
      start: function (step) { startAudioFlowGuide({ startStep: step }); },
      go: function (step) { return gotoAudioFlowGuideStep(step); },
      update: typeof updateAudioFlowGuideSubtitles === "function" ? updateAudioFlowGuideSubtitles : null,
    };
  }
  if (kind === "video") {
    return {
      overlay: "videoflow-guide-overlay",
      caption: "vf-guide-subtitle-text",
      start: function (step) { startVideoFlowGuide(step); },
      go: function (step) { return gotoVideoFlowGuideStep(step); },
      update: typeof updateVideoFlowGuideSubtitles === "function" ? updateVideoFlowGuideSubtitles : null,
    };
  }
  return {
    overlay: "voiceflow-guide-overlay",
    caption: "voiceflow-guide-subtitle-text",
    start: function (step) { startVoiceFlowGuide(step); },
    go: function (step) { return gotoVoiceFlowGuideStep(step); },
    update: typeof updateVoiceFlowGuideSubtitles === "function" ? updateVoiceFlowGuideSubtitles : null,
  };
};

window.__e2e.prepGuide = async function (kind, step) {
  window.__e2e.closeGuides();
  await window.__e2e.sleep(200);
  var spec = window.__e2e.guideSpec(kind);
  spec.start(step);
  await window.__e2e.sleep(700);
  var overlay = document.getElementById(spec.overlay);
  if (overlay && overlay.classList.contains("hidden")) {
    try { await spec.go(step); } catch (err) {}
    await window.__e2e.sleep(400);
    overlay = document.getElementById(spec.overlay);
  }
  if (spec.update) spec.update(3.5, step);
  await window.__e2e.sleep(250);
  var captionEl = document.getElementById(spec.caption);
  var visible = !!(overlay && !overlay.classList.contains("hidden"));
  return {
    ok: visible,
    kind: kind,
    step: step,
    caption: captionEl ? captionEl.textContent : "",
    visible: visible,
  };
};

window.__e2e.prepPage = async function (pageId, theme) {
  window.__e2e.closeGuides();
  if (typeof applyTheme === "function") {
    try { await applyTheme(theme, true); } catch (err) {}
  }
  if (typeof paintTheme === "function") paintTheme(theme);
  if (typeof switchPage === "function") switchPage(pageId);
  await window.__e2e.sleep(600);
  var main = document.querySelector(".main-content");
  if (main) main.scrollTop = 0;
  window.scrollTo(0, 0);
  return {
    ok: true,
    page: pageId,
    theme: document.documentElement.getAttribute("data-theme") || "",
  };
};

window.__e2e.prepNotice = async function (theme) {
  await window.__e2e.prepPage("providers", theme);
  if (typeof refreshFirstRunModelBanner === "function") {
    try { await refreshFirstRunModelBanner(); } catch (err) {}
  }
  await window.__e2e.sleep(400);
  var box = document.getElementById("vf-first-run-models");
  var natural = !!(box && !box.hidden && !box.classList.contains("hidden"));
  if (box && !natural) {
    box.classList.remove("hidden");
    box.hidden = false;
  }
  if (box && box.scrollIntoView) box.scrollIntoView({ block: "center" });
  await window.__e2e.sleep(200);
  return {
    ok: !!box,
    natural: natural,
    text: box ? (box.innerText || "").replace(/\s+/g, " ").trim().slice(0, 240) : "",
  };
};

window.__e2e.prepNotebookCard = async function (theme) {
  await window.__e2e.prepPage("videoflow", theme);
  var card = document.getElementById("vf-nlm-account-card");
  if (card && card.scrollIntoView) card.scrollIntoView({ block: "center" });
  await window.__e2e.sleep(300);
  return {
    ok: !!card,
    text: card ? (card.innerText || "").replace(/\s+/g, " ").trim().slice(0, 240) : "",
  };
};

window.__e2e.prepSettings = async function (tab, theme, about) {
  window.__e2e.closeGuides();
  if (typeof applyTheme === "function") {
    try { await applyTheme(theme, true); } catch (err) {}
  }
  if (typeof paintTheme === "function") paintTheme(theme);
  if (typeof openSettings === "function") openSettings(tab);
  await window.__e2e.sleep(500);
  if (about) {
    var row = document.getElementById("privacy-crash-row") || document.querySelector(".about-card");
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "center" });
    await window.__e2e.sleep(250);
  } else {
    var body = document.querySelector("#settings-modal .modal-body");
    if (body) body.scrollTop = 0;
  }
  var version = document.querySelector(".about-version-badge");
  var build = document.querySelector(".about-build-id");
  var modal = document.getElementById("settings-modal");
  return {
    ok: !!(modal && !modal.classList.contains("hidden")),
    tab: tab,
    version: version ? version.textContent.trim() : "",
    build: build ? build.textContent.trim() : "",
  };
};

window.__e2e.visual = function () {
  var issues = [];
  var nodes = document.querySelectorAll("button, h1, h2, h3, h4, .s1-caption-text, .af-guide-caption-text, .setting-title, .nav-label, .about-version-badge, .about-build-id");
  Array.prototype.forEach.call(nodes, function (el) {
    var style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || el.hidden) return;
    var rect = el.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) return;
    var label = (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 48);
    if (!label) return;
    if (el.scrollWidth > el.clientWidth + 14 && (style.overflowX === "hidden" || style.textOverflow === "ellipsis")) {
      issues.push("cut-off: " + label);
    }
  });
  return {
    theme: document.documentElement.getAttribute("data-theme") || "",
    issues: issues.slice(0, 6),
    summary: issues.length ? issues.slice(0, 3).join("; ") : "no clipped text detected",
  };
};
