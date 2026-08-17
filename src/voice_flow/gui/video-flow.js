let vfCatalog = {providers: [], models: [], combos: [], active_model: "local/deterministic"};
let vfCatalogLoaded = false;
let vfVideos = [];
let vfPollTimer = null;
let vfDeleteTarget = null;
let vfPreviewVideo = null;
let vfCurrentProvider = null;
let vfCurrentProviderDetails = null;
let vfConnectionMode = "single";
let vfComboDraftModels = [];
let vfProviderOpenRequest = 0;
let vfOAuthProvider = null;

// The model picker is shared by Video Flow and the Audio Flow summary
// selector, so it must be able to hydrate the catalog on its own — not only
// after the Video Flow page happened to load it.
async function vfEnsureCatalog() {
  if (vfCatalogLoaded) return true;
  try {
    const res = await fetch("/api/video-flow/catalog");
    if (!res.ok) return false;
    vfCatalog = await res.json();
    vfCatalogLoaded = true;
    return true;
  } catch {
    return false;
  }
}

const VF_PERMANENT_CONFIRMATION = "DELETE_VIDEO_FROM_THIS_PC";
const vfProviderIcons = {
  claude_code: "✺", antigravity: "A", openai_codex: "◎",
  vertex_ai: "V", gemini: "✦", openrouter: "↔", nvidia_nim: "N",
  opencode_zen: "Z", anthropic: "A", openai: "◎", groq: "G",
  together: "T", cloudflare: "☁", ollama: "◉", lm_studio: "LM",
  llama_cpp: "L",
}

function vfEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function vfFormatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
}

function vfFormatDuration(seconds) {
  if (!seconds) return "Pending";
  const total = Math.round(Number(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

async function loadVideoFlow() {
  try {
    const [historyResponse, catalogResponse] = await Promise.all([
      fetch("/api/video-flow/history"),
      fetch("/api/video-flow/catalog"),
    ]);
    if (!historyResponse.ok || !catalogResponse.ok) throw new Error("Video Flow backend is unavailable.");
    const historyData = await historyResponse.json();
    vfCatalog = await catalogResponse.json();
    vfCatalogLoaded = true;
    vfVideos = historyData.videos || [];
    renderVideoHistory();
    renderVideoCatalog();
    scheduleVideoFlowPolling();
  } catch (error) {
    vfToast(error.message || "Could not load Video Flow.", true);
    renderVideoBackendFailure(error);
    const status = document.getElementById("vf-engine-status");
    if (status) status.textContent = "○ Backend unavailable";
  }
}

function renderVideoBackendFailure(error) {
  const detail = vfEscape(error?.message || "Video Flow backend is unavailable.");
  const message = '<div class="vf-empty-state vf-backend-failure">' +
    '<strong>Providers could not load</strong>' +
    '<span>' + detail + ' Restart Voice Flow to attach this page to the current backend.</span>' +
    '</div>';
  for (const id of ["vf-oauth-provider-grid", "vf-api-provider-grid", "vf-local-provider-grid"]) {
    const grid = document.getElementById(id);
    if (grid) grid.innerHTML = message;
  }
}

function renderVideoHistory() {
  const grid = document.getElementById("vf-history-grid");
  const empty = document.getElementById("vf-history-empty");
  const count = document.getElementById("vf-history-count");
  if (!grid || !empty) return;

  if (count) count.textContent = vfVideos.length === 1 ? "1 generated video" : `${vfVideos.length} generated videos`;
  empty.style.display = vfVideos.length ? "none" : "flex";
  grid.style.display = vfVideos.length ? "grid" : "none";
  grid.innerHTML = vfVideos.map(video => {
    const complete = video.status === "completed" || video.status === "complete" || video.status === "ready" || Boolean(video.playable);
    const failed = video.status === "failed";
    const mode = video.mode === "full" ? "Full explanation" : "Summary";
    const engineVersion = video.engine_version || "legacy";
    const error = failed && video.error ? ` title="${vfEscape(video.error)}"` : "";
    return `
      <article class="vf-video-card" data-video-id="${vfEscape(video.id)}">
        <div class="vf-video-thumb" ${complete ? `onclick="previewVideoFlow('${vfEscape(video.id)}')"` : ""}>
          <div class="vf-video-thumb-top">
            <span class="vf-mode-chip">${mode}</span>
            <span class="vf-status-chip ${vfEscape(video.status)}"${error}>${vfEscape(video.status)}</span>
          </div>
          <div class="vf-thumb-play">${complete ? "▶" : failed ? "!" : "•••"}</div>
          <div class="vf-status-row"><small>${vfEscape(video.stage || "Queued")}</small><small>${Number(video.progress || 0)}%</small></div>
        </div>
        <div class="vf-video-body">
          <h3 title="${vfEscape(video.title)}">${vfEscape(video.title)}</h3>
          <div class="vf-video-meta"><span>${vfFormatDate(video.created_at)}</span><span>${vfFormatDuration(video.duration_sec)}</span><span>${vfEscape(engineVersion)}</span></div>
          ${!complete ? `<div class="vf-progress-track"><span style="width:${Math.max(0, Math.min(100, Number(video.progress || 0)))}%"></span></div>` : ""}
          <div class="vf-video-actions">
            ${complete ? `
              <button class="vf-icon-button" onclick="previewVideoFlow('${vfEscape(video.id)}')">▶ Play</button>
              <a class="vf-icon-button" href="${vfEscape(video.download_url)}" download>↓ Download</a>
              <button class="vf-icon-button" onclick="shareVideoFlow('${vfEscape(video.id)}')">↗ Share</button>
            ` : ""}
            ${failed ? `<button class="vf-icon-button" onclick="retryVideoFlow('${vfEscape(video.id)}')">↻ Retry</button>` : ""}
            <button class="vf-icon-button danger" onclick="beginVideoDelete('${vfEscape(video.id)}')">⌫ Delete</button>
          </div>
        </div>
      </article>`;
  }).join("");
}

function vfCapabilityBadges(model) {
  const labels = {vision: "👁 Vision", reasoning: "🧠 Reasoning", code: "</> Code", audio: "♪ Audio", private: "⌂ Private", offline: "⊘ Offline"};
  return (model.capabilities || []).map(item => '<span class="vf-capability">' + vfEscape(labels[item] || item) + '</span>').join("");
}

function renderVideoProviderGrid(elementId, providers) {
  const grid = document.getElementById(elementId);
  if (!grid) return;
  grid.className = "providers-cards-grid";
  grid.innerHTML = (providers || []).map(provider => {
    const connected = provider.status === "connected";
    const statusText = provider.category === "oauth"
      ? (provider.oauth_status?.label || (connected ? "Connected" : "Not connected"))
      : connected
        ? `${provider.active_count} Active`
        : provider.category === "local" ? "Native / Local" : "Not connected";
    const logo = vfProviderIcons[provider.id] || provider.icon || "🎬";
    return `
      <div class="provider-card-item" onclick="openVideoProvider('${vfEscape(provider.id)}')">
        <div class="provider-card-left">
          <div class="provider-card-logo">${vfEscape(logo)}</div>
          <div class="provider-card-info">
            <span class="provider-card-name">${vfEscape(provider.name)}</span>
            <span class="provider-card-status">
              <span class="status-dot-indicator ${connected ? 'connected' : ''}"></span>
              ${vfEscape(statusText)}
            </span>
          </div>
        </div>
        <label class="toggle-switch" onclick="event.stopPropagation()">
          <input type="checkbox" ${connected ? 'checked' : ''} onchange="toggleVideoProviderMaster('${vfEscape(provider.id)}', this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    `;
  }).join("");
}

async function toggleVideoProviderMaster(providerId, isChecked) {
  try {
    const res = await fetch("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
    const data = await res.json();
    if (data && data.connections && data.connections.length > 0) {
      for (const conn of data.connections) {
        await vfPost("/api/video-flow/providers/connections/update", {
          connection_id: conn.id,
          is_active: isChecked,
        });
      }
      vfToast(`${providerId} provider connections ${isChecked ? 'enabled' : 'disabled'}.`);
      loadVideoFlow();
    } else {
      openVideoProvider(providerId);
    }
  } catch (err) {
    vfToast(err.message || "Error toggling provider", true);
  }
}

function vfSelectableVideoModels() {
  return (vfCatalog.models || []).filter(model => model.full_id !== "local/deterministic" && model.available && model.is_active !== false);
}

function vfIsSelectableVideoModelRef(modelRef) {
  return modelRef === "local/deterministic" || vfSelectableVideoModels().some(model => model.full_id === modelRef);
}

function vfSelectableVideoCombos() {
  const availableRefs = new Set(["local/deterministic", ...vfSelectableVideoModels().map(model => model.full_id)]);
  return (vfCatalog.combos || []).filter(combo => (combo.models || []).length && (combo.models || []).every(ref => availableRefs.has(ref)));
}

function renderVideoCatalog() {
  const models = vfSelectableVideoModels();
  const combos = vfSelectableVideoCombos();
  const groups = new Map();
  for (const model of models) {
    const name = model.provider_name || model.provider;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(model);
  }

  const select = document.getElementById("vf-model-select");
  if (select) {
    select.innerHTML = (combos.length ? '<optgroup label="Model Combos">' + combos.map(combo =>
      '<option value="' + vfEscape(combo.ref) + '">◈ ' + vfEscape(combo.name) + '</option>'
    ).join("") + '</optgroup>' : "") +
      [...groups.entries()].map(([name, items]) => '<optgroup label="' + vfEscape(name) + '">' + items.map(model =>
        '<option value="' + vfEscape(model.full_id) + '">' + vfEscape(model.display_name) + '</option>'
      ).join("") + '</optgroup>').join("");
    const activeModelRef = vfCatalog.active_model || "local/deterministic";
    select.value = activeModelRef;
    updateActiveVideoModel(activeModelRef);
  }

  const strip = document.getElementById("vf-combo-strip");
  const empty = document.getElementById("vf-combo-empty");
  if (strip) {
    strip.innerHTML = (vfCatalog.combos || []).map(combo =>
      '<span class="vf-combo-pill">◈ ' + vfEscape(combo.name) + ' · ' + combo.models.length + ' models · ' + vfEscape(combo.strategy.replace("_", " ")) +
        '<button title="Delete combo" onclick="deleteVideoCombo(' + Number(combo.id) + ')">×</button></span>'
    ).join("");
  }
  if (empty) empty.style.display = (vfCatalog.combos || []).length ? "none" : "flex";

  const providerGroups = vfCatalog.provider_groups || {};
  renderVideoProviderGrid("vf-oauth-provider-grid", providerGroups.oauth || []);
  renderVideoProviderGrid("vf-api-provider-grid", providerGroups.api_key || []);
  renderVideoProviderGrid("vf-local-provider-grid", providerGroups.local || []);
  renderVideoModelPicker();
}

function vfPickerActiveRef() {
  if (vfModelPickerContext === "audio_summary") {
    if (typeof afSummaryModelRef === "string" && afSummaryModelRef) return afSummaryModelRef;
    return "local/deterministic";
  }
  if (vfModelPickerContext === "voice_flow") {
    if (typeof voiceFlowPolicyModelRef === "string" && voiceFlowPolicyModelRef) return voiceFlowPolicyModelRef;
  }
  if (vfModelPickerContext === "audio_voice") {
    if (typeof audioVoicePolicyModelRef === "string" && audioVoicePolicyModelRef) return audioVoicePolicyModelRef;
  }
  return vfCatalog.active_model || "local/deterministic";
}

function vfPickerProviderIcon(key) {
  const icon = vfProviderIcons[key];
  if (icon) return icon;
  const model = (vfCatalog.models || []).find(m => m.provider_name === key);
  return (model && vfProviderIcons[model.provider]) || "✦";
}

function renderVideoModelPicker() {
  const root = document.getElementById("vf-model-picker-list");
  if (!root) return;
  const query = (document.getElementById("vf-model-picker-search")?.value || "").trim().toLowerCase();
  let models = vfSelectableVideoModels().filter(model =>
    !query || [model.provider_name, model.display_name, model.full_id, ...(model.capabilities || [])].join(" ").toLowerCase().includes(query)
  );
  const combos = vfSelectableVideoCombos().filter(combo =>
    !query || [combo.name, combo.strategy, ...(combo.models || [])].join(" ").toLowerCase().includes(query)
  );
  // Restricted contexts (e.g. the Voice Flow polishing policy or the Audio
  // Flow voice catalogue) only offer the models their backend supports.
  if (vfPickerAllowedRefs) {
    models = models.filter(model => vfPickerAllowedRefs.has(model.full_id));
    // Policy-only models absent from the shared catalog (different provider
    // hosting) are injected so they remain selectable.
    const extras = vfModelPickerContext === "audio_voice"
      ? (typeof audioVoicePolicyModels !== "undefined" ? audioVoicePolicyModels : [])
      : (typeof voiceFlowPolicyModels !== "undefined" ? voiceFlowPolicyModels : []);
    for (const pm of extras) {
      const matchesQuery = !query || [pm.provider_name, pm.display_name, pm.full_id, ...(pm.capabilities || [])].join(" ").toLowerCase().includes(query);
      if (matchesQuery && vfPickerAllowedRefs.has(pm.full_id) && !models.some(m => m.full_id === pm.full_id)) {
        models.push(pm);
      }
    }
    combos.length = 0;
  }
  const groups = new Map();
  for (const model of models) {
    const name = model.provider_name || model.provider;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(model);
  }
  const activeRef = vfPickerActiveRef();
  const sections = [];
  if (combos.length) {
    sections.push('<section class="vf-picker-group"><h4>◈ Model Combos <span>' + combos.length + '</span></h4>' + combos.map(combo =>
      '<button class="vf-picker-model ' + (combo.ref === activeRef ? "selected" : "") + '" onclick="chooseVideoModel(\'' + vfEscape(combo.ref) + '\')"><span class="vf-picker-model-icon">◈</span><span class="vf-picker-model-copy"><strong>' + vfEscape(combo.name) + '</strong><small>' + combo.models.length + ' models · ' + vfEscape(combo.strategy.replace("_", " ")) + ' failover</small></span><b class="vf-picker-check">✓</b></button>'
    ).join("") + '</section>');
  }
  if (!vfPickerAllowedRefs && (!query || "on this pc built-in deterministic private offline".includes(query))) {
    sections.push('<section class="vf-picker-group"><h4>⌂ On this PC <span>1</span></h4><button class="vf-picker-model ' + (activeRef === "local/deterministic" ? "selected" : "") + '" onclick="chooseVideoModel(\'local/deterministic\')"><span class="vf-picker-model-icon">⌂</span><span class="vf-picker-model-copy"><strong>Built-in deterministic planner</strong><small>Private · offline · no account required</small></span><b class="vf-picker-check">✓</b></button></section>');
  }
  for (const [providerName, items] of groups.entries()) {
    const icon = vfPickerProviderIcon(items[0].provider || providerName);
    sections.push('<section class="vf-picker-group"><h4>' + vfEscape(providerName) + ' <span>' + items.length + '</span></h4>' + items.map(model =>
      '<button class="vf-picker-model ' + (model.full_id === activeRef ? "selected" : "") + '" onclick="chooseVideoModel(\'' + vfEscape(model.full_id) + '\')"><span class="vf-picker-model-icon">' + vfEscape(icon) + '</span><span class="vf-picker-model-copy"><strong>' + vfEscape(model.display_name) + '</strong><small>' + vfEscape(model.full_id) + '</small></span><span class="vf-capability-list">' + vfCapabilityBadges(model) + '</span><b class="vf-picker-check">✓</b></button>'
    ).join("") + '</section>');
  }
  root.innerHTML = sections.join("") || '<div class="vf-empty-state vf-compact-empty"><strong>No connected models match</strong><span>Connect a provider, enable one of its models, or try another search.</span></div>';
}

let vfModelPickerContext = "video_flow";
let vfPickerAllowedRefs = null;

function vfUpdateModelPickerChrome() {
  const kicker = document.getElementById("vf-model-picker-kicker");
  const title = document.getElementById("vf-model-picker-title");
  const note = document.getElementById("vf-model-picker-note");
  if (vfModelPickerContext === "audio_summary") {
    if (kicker) kicker.textContent = "AUDIO FLOW SUMMARY MODEL";
    if (title) title.textContent = "Select the summary LLM";
    if (note) note.textContent = "The selected LLM condenses highlighted text into a spoken explanation before Text-to-Speech narration.";
  } else if (vfModelPickerContext === "audio_voice") {
    if (kicker) kicker.textContent = "AUDIO FLOW VOICE";
    if (title) title.textContent = "Select the TTS voice";
    if (note) note.textContent = "Neural voices from connected TTS providers plus the free Edge engine. The selected voice reads your highlighted text aloud.";
  } else if (vfModelPickerContext === "voice_flow") {
    if (kicker) kicker.textContent = "VOICE FLOW MODEL";
    if (title) title.textContent = "Select the polishing model";
    if (note) note.textContent = "The selected model polishes every dictation before it is pasted. Only models supported by the polishing policy are listed.";
  } else {
    if (kicker) kicker.textContent = "VIDEO FLOW MODEL";
    if (title) title.textContent = "Select the planning model";
    if (note) note.textContent = "Only enabled models from connected Video Flow providers appear here. Combos are listed first.";
  }
}

function openVideoModelPicker(context = "video_flow") {
  vfModelPickerContext = context;
  // Restricted contexts only offer the models their backend supports.
  if (context === "voice_flow" && typeof voiceFlowPolicyModelSet !== "undefined" && voiceFlowPolicyModelSet) {
    vfPickerAllowedRefs = voiceFlowPolicyModelSet;
  } else if (context === "audio_voice" && typeof audioVoicePolicySet !== "undefined" && audioVoicePolicySet) {
    vfPickerAllowedRefs = audioVoicePolicySet;
  } else {
    vfPickerAllowedRefs = null;
  }
  const search = document.getElementById("vf-model-picker-search");
  if (search) search.value = "";
  vfUpdateModelPickerChrome();
  const list = document.getElementById("vf-model-picker-list");
  document.getElementById("vf-model-picker-modal")?.classList.remove("hidden");
  if (!vfCatalogLoaded && list) {
    list.innerHTML = '<div class="vf-picker-loading"><span class="vf-picker-spinner" aria-hidden="true"></span>Loading connected models…</div>';
    vfEnsureCatalog().then(ok => {
      // The modal may have been closed again before the catalog arrived.
      if (document.getElementById("vf-model-picker-modal")?.classList.contains("hidden")) return;
      renderVideoModelPicker();
      if (!ok && typeof vfToast === "function") vfToast("Could not load the model catalog.", true);
    });
  } else {
    renderVideoModelPicker();
  }
  requestAnimationFrame(() => search?.focus());
}

function chooseVideoModel(modelRef) {
  closeVideoModal("vf-model-picker-modal");
  if (vfModelPickerContext === "audio_summary") {
    if (typeof selectAudioSummaryModel === "function") {
      selectAudioSummaryModel(modelRef);
    }
  } else if (vfModelPickerContext === "audio_voice") {
    if (typeof updateExecAudioFlowPolicy === "function") {
      updateExecAudioFlowPolicy(modelRef);
    }
  } else if (vfModelPickerContext === "voice_flow") {
    if (typeof updateExecVoiceFlowPolicy === "function") {
      updateExecVoiceFlowPolicy(modelRef);
    }
  } else {
    const select = document.getElementById("vf-model-select");
    if (select) select.value = modelRef;
    saveVideoModel(modelRef);
  }
}
function toggleVideoHistory() {
  const body = document.getElementById("vf-history-body");
  const button = document.getElementById("vf-history-toggle");
  if (!body || !button) return;
  const willOpen = body.style.display === "none";
  body.style.display = willOpen ? "block" : "none";
  button.setAttribute("aria-expanded", String(willOpen));
  const chevron = button.querySelector(".vf-chevron");
  if (chevron) chevron.textContent = willOpen ? "⌃" : "⌄";
}

function updateVideoSourceCount() {
  const input = document.getElementById("vf-source-input");
  const counter = document.getElementById("vf-source-counter");
  if (input && counter) counter.textContent = `${input.value.length.toLocaleString()} characters`;
}

async function loadVideoSourceFile(file) {
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    vfToast("That document is larger than 8 MB.", true);
    return;
  }
  const allowed = [".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".rtf", ".docx", ".pdf"];
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!allowed.includes(extension)) {
    vfToast("Choose a TXT, Markdown, CSV, JSON, HTML, XML, RTF, DOCX, or PDF document.", true);
    return;
  }
  const input = document.getElementById("vf-source-input");
  const label = document.getElementById("vf-file-name");
  const title = document.getElementById("vf-title-input");
  try {
    if (extension === ".docx" || extension === ".pdf") {
      if (label) label.textContent = "Extracting " + file.name + "…";
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Could not read the document."));
        reader.readAsDataURL(file);
      });
      const response = await fetch("/api/video-flow/documents/extract", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({file_name: file.name, content_base64: String(dataUrl).split(",", 2)[1]}),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || "Could not extract document text.");
      input.value = data.text;
    } else {
      input.value = await file.text();
    }
    if (label) label.textContent = file.name;
    if (title && !title.value) title.value = file.name.replace(/\.[^.]+$/, "");
    input.dataset.sourceName = file.name;
    updateVideoSourceCount();
  } catch (error) {
    if (label) label.textContent = "";
    vfToast(error.message || "Could not load that document.", true);
  }
}
function selectVideoMode(mode) {
  document.querySelectorAll(".vf-mode-card").forEach(card => card.classList.toggle("active", card.dataset.mode === mode));
  const note = document.getElementById("vf-coverage-note");
  const button = document.getElementById("vf-generate-button");
  if (note) {
    note.innerHTML = mode === "full"
      ? "<strong>Complete-source guarantee</strong><span>The render plan is validated so every source character remains in narration order.</span>"
      : "<strong>Summary mode</strong><span>Video Flow samples the opening, middle, and conclusion to create a shorter explanation.</span>";
  }
  if (button) {
    const strong = button.querySelector("strong");
    if (strong) strong.textContent = mode === "full" ? "Generate Full Explanation" : "Generate Summary Video";
  }
}

function isVideoModelExternal(modelRef) {
  let refs = [modelRef];
  if (modelRef.startsWith("combo:")) {
    refs = (vfCatalog.combos || []).find(item => item.ref === modelRef)?.models || [];
  }
  const localProviders = new Set((vfCatalog.provider_groups?.local || []).map(item => item.id));
  return refs.some(ref => {
    if (ref === "local/deterministic") return false;
    const model = (vfCatalog.models || []).find(item => item.full_id === ref);
    return !model || !localProviders.has(model.provider);
  });
}

async function generateVideoFlow() {
  const sourceInput = document.getElementById("vf-source-input");
  const titleInput = document.getElementById("vf-title-input");
  const modelSelect = document.getElementById("vf-model-select");
  const themeSelect = document.getElementById("vf-theme-select");
  const visualDirection = document.getElementById("vf-visual-direction");
  const selectedMode = document.querySelector('input[name="vf-mode"]:checked');
  const button = document.getElementById("vf-generate-button");
  const message = document.getElementById("vf-generate-message");
  const source = sourceInput?.value || "";
  if (!source.trim()) {
    vfToast("Paste text or choose a document first.", true);
    sourceInput?.focus();
    return;
  }
  const modelRef = modelSelect?.value || "local/deterministic";
  const consent = Boolean(document.getElementById("vf-external-consent")?.checked);
  if (isVideoModelExternal(modelRef) && !consent) {
    vfToast("Confirm external AI planning before sending this source to the selected provider.", true);
    document.getElementById("vf-external-consent")?.focus();
    return;
  }  if (button) button.disabled = true;
  if (message) message.textContent = "Creating the project and starting scene planning…";
  try {
    const response = await fetch("/api/video-flow/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        source_text: source,
        source_name: sourceInput?.dataset.sourceName || "",
        title: titleInput?.value || "",
        mode: selectedMode?.value || "summary",
        model_ref: modelRef,
        allow_external_ai: consent,
        theme: themeSelect?.value || "auto",
        visual_direction: visualDirection?.value || "",
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Could not start Video Flow.");
    vfVideos.unshift(data.video);
    renderVideoHistory();
    scheduleVideoFlowPolling(true);
    vfToast("Video queued. You can follow its progress in history.");
    if (message) message.textContent = "Generation is running in the background.";
    document.getElementById("vf-generate-button")?.scrollIntoView({behavior: "smooth", block: "nearest"});
  } catch (error) {
    if (message) message.textContent = error.message || "Generation failed.";
    vfToast(error.message || "Generation failed.", true);
  } finally {
    if (button) button.disabled = false;
  }
}

function scheduleVideoFlowPolling(immediate = false) {
  if (vfPollTimer) window.clearInterval(vfPollTimer);
  const hasActive = vfVideos.some(video => !["completed", "failed"].includes(video.status));
  if (!hasActive) return;
  const refresh = async () => {
    try {
      const response = await fetch("/api/video-flow/history");
      const data = await response.json();
      vfVideos = data.videos || [];
      renderVideoHistory();
      if (!vfVideos.some(video => !["completed", "failed"].includes(video.status))) {
        window.clearInterval(vfPollTimer);
        vfPollTimer = null;
      }
    } catch (_) {
      // A later poll can recover if the local backend is restarting.
    }
  };
  if (immediate) refresh();
  vfPollTimer = window.setInterval(refresh, 1800);
}

async function saveVideoModel(modelRef) {
  if (!modelRef) return;
  try {
    const response = await fetch("/api/video-flow/settings/model", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({model_ref: modelRef}),
    });
    if (!response.ok) throw new Error("Could not save the Video Flow model.");
    vfCatalog.active_model = modelRef;
    updateActiveVideoModel(modelRef);
    renderVideoModelPicker();
    vfToast("Video Flow model selected.");
  } catch (error) {
    vfToast(error.message, true);
  }
}

function isVideoModelExternal(modelRef) {
  if (!modelRef || modelRef === "local/deterministic") return false;
  if (modelRef.startsWith("local/") || modelRef.startsWith("ollama/") || modelRef.startsWith("lmstudio/") || modelRef.startsWith("llamacpp/")) {
    return false;
  }
  let refs = [modelRef];
  if (modelRef.startsWith("combo:")) {
    refs = (vfCatalog.combos || []).find(item => item.ref === modelRef)?.models || [];
  }
  const localProviders = new Set((vfCatalog.provider_groups?.local || []).map(item => item.id));
  return refs.some(ref => {
    if (ref === "local/deterministic") return false;
    const providerId = ref.split("/", 1)[0];
    return !localProviders.has(providerId);
  });
}

function updateActiveVideoModel(modelRef) {
  const label = document.getElementById("vf-active-model-label");
  const detail = document.getElementById("vf-active-model-detail");
  const engineLabel = document.getElementById("vf-active-engine-label");
  if (modelRef.startsWith("combo:")) {
    const combo = (vfCatalog.combos || []).find(item => item.ref === modelRef);
    if (label) label.textContent = combo ? "◈ " + combo.name : modelRef;
    if (detail) detail.textContent = combo ? combo.models.length + " models · " + combo.strategy.replace("_", " ") : "Model combo";
    if (engineLabel) engineLabel.textContent = combo ? "Combo: " + combo.name : "Model Combo";
  } else if (modelRef === "local/deterministic") {
    if (label) label.textContent = "Voice Flow Local — Deterministic Storyboard";
    if (detail) detail.textContent = "Works without an API key";
    if (engineLabel) engineLabel.textContent = "Local Deterministic";
  } else {
    const model = (vfCatalog.models || []).find(item => item.full_id === modelRef);
    if (label) label.textContent = model ? model.provider_name + " — " + model.display_name : modelRef;
    if (detail) detail.textContent = modelRef.startsWith("local/") ? "Works without an API key" : "Uses active provider connections and failover settings";
    if (engineLabel) engineLabel.textContent = model ? model.provider_name : modelRef.split("/", 1)[0];
  }
  updateVideoExternalConsent(modelRef);
}

function updateVideoExternalConsent(modelRef) {
  const row = document.getElementById("vf-external-consent-row");
  const checkbox = document.getElementById("vf-external-consent");
  const copy = document.getElementById("vf-external-consent-copy");
  if (!row || !checkbox || !copy) return;
  if (!isVideoModelExternal(modelRef)) {
    row.style.display = "none";
    checkbox.checked = false;
    return;
  }
  let refs = [modelRef];
  if (modelRef.startsWith("combo:")) {
    refs = (vfCatalog.combos || []).find(item => item.ref === modelRef)?.models || [];
  }
  const names = [...new Set(refs.map(ref => {
    const model = (vfCatalog.models || []).find(item => item.full_id === ref);
    return model?.provider_name || ref.split("/", 1)[0];
  }))];
  row.style.display = "flex";
  checkbox.checked = false;
  copy.textContent = "The source text will be sent to " + (names.join(", ") || "the selected providers") + " for scene planning. Voice narration and rendering remain on this PC.";
}
async function vfPost(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data.success === false) throw new Error(data.error || "Video Flow request failed.");
  return data;
}

async function openVideoProvider(providerId) {
  const page = document.getElementById("page-videoflow");
  const panel = document.getElementById("vf-provider-detail-panel");
  const root = document.getElementById("vf-provider-detail-content");
  if (!page || !panel || !root) return;

  const requestId = ++vfProviderOpenRequest;
  if (!page.classList.contains("vf-provider-open")) {
    page.dataset.providerReturnScroll = String(window.scrollY || 0);
  }
  page.classList.add("vf-provider-open");
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  root.innerHTML = '<div class="vf-empty-state vf-compact-empty"><strong>Opening provider…</strong><span>Loading its connections and enabled models.</span></div>';
  window.scrollTo({top: 0, behavior: "smooth"});

  try {
    const response = await fetch("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.error || "Could not open provider.");
    if (requestId !== vfProviderOpenRequest) return;
    vfCurrentProvider = providerId;
    vfCurrentProviderDetails = data;
    renderVideoProviderDetails();
  } catch (error) {
    if (requestId !== vfProviderOpenRequest) return;
    root.innerHTML = '<div class="vf-empty-state vf-compact-empty"><strong>Provider could not open</strong><span>' + vfEscape(error.message || "Try again from the provider list.") + '</span></div>';
    vfToast(error.message || "Could not open provider.", true);
  }
}

function closeVideoProvider() {
  vfProviderOpenRequest += 1;
  const page = document.getElementById("page-videoflow");
  const returnScroll = Number(page?.dataset.providerReturnScroll || 0);
  const panel = document.getElementById("vf-provider-detail-panel");
  panel?.classList.add("hidden");
  panel?.setAttribute("aria-hidden", "true");
  page?.classList.remove("vf-provider-open");
  vfCurrentProvider = null;
  vfCurrentProviderDetails = null;
  requestAnimationFrame(() => window.scrollTo({top: returnScroll, behavior: "smooth"}));
}

function renderVideoProviderDetails() {
  const data = vfCurrentProviderDetails;
  const root = document.getElementById("vf-provider-detail-content");
  if (!data || !root) return;

  const provider = data.provider;
  const isOAuth = provider.category === "oauth";
  const isLocal = provider.category === "local";
  const oauthStatus = provider.oauth_status || {};
  const logo = vfEscape(vfProviderIcons[provider.id] || provider.icon || "🎬");

  // Connection rows
  const connectionRows = (data.connections || []).map(function(conn) {
    return '<div class="vf-connection-row">' +
      '<label><input type="checkbox" ' + (conn.is_active ? "checked" : "") + ' onchange="toggleVideoConnection(' + conn.id + ', this.checked)"></label>' +
      '<span class="vf-connection-key">🔑</span>' +
      '<span class="vf-connection-copy">' +
        '<strong>' + vfEscape(conn.name) + '</strong>' +
        '<small><b class="' + vfEscape(conn.status) + '">● ' + vfEscape(conn.status) + '</b> · priority ' + conn.priority + (conn.secret_hint ? ' · ' + vfEscape(conn.secret_hint) : '') + '</small>' +
      '</span>' +
      '<button class="vf-text-button" onclick="testVideoConnection(' + conn.id + ')">⚗ Test</button>' +
      '<button class="vf-text-button" onclick="editVideoConnection(' + conn.id + ')">✎ Edit</button>' +
      '<button class="vf-text-button danger" onclick="deleteVideoConnection(' + conn.id + ')">⌫ Delete</button>' +
    '</div>';
  }).join("");

  // Model rows
  const modelRows = (data.models || []).map(function(model) {
    return '<div class="vf-provider-model-row">' +
      '<span class="vf-provider-model-icon">🤖</span>' +
      '<span><strong>' + vfEscape(model.full_id) + '</strong><small>' + vfEscape(model.display_name) + '</small></span>' +
      '<span class="vf-capability-list">' + vfCapabilityBadges(model) + '</span>' +
      '<button class="vf-text-button" onclick="copyVideoModelId(\'' + vfEscape(model.full_id) + '\')">▣ Copy</button>' +
      '<label class="vf-mini-switch"><input type="checkbox" ' + (model.is_active ? "checked" : "") + ' onchange="toggleVideoModel(' + model.id + ', this.checked)"></label>' +
      (model.custom ? '<button class="vf-text-button danger" onclick="deleteVideoCustomModel(' + model.id + ')">× Remove</button>' : '') +
    '</div>';
  }).join("");

  // Empty-state fallbacks
  var connectionsEmpty = '<div class="vf-empty-state vf-compact-empty"><strong>No connections</strong><span>' + (isLocal ? "Add the local server URL." : "Add an API key to activate these models.") + '</span></div>';
  var modelsEmpty = '<div class="vf-empty-state vf-compact-empty"><strong>No models</strong><span>Add a model ID for this provider.</span></div>';

  // Build the full detail HTML
  var html = '';

  // Provider title row
  html += '<div class="provider-detail-title-row">';
  html += '<div class="provider-large-badge">' + logo + '</div>';
  html += '<div>';
  html += '<div style="display:flex;align-items:center;gap:10px;">';
  html += '<h1 class="provider-detail-title">' + vfEscape(provider.name) + '</h1>';
  if (provider.get_key_url) {
    html += '<a href="' + vfEscape(provider.get_key_url) + '" target="_blank" class="get-key-pill-link">🔑 Get API Key ↗</a>';
  }
  html += '</div>';
  if (provider.description) {
    html += '<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">' + vfEscape(provider.description) + '</div>';
  }
  html += '</div></div>';

  // OAuth status section
  if (isOAuth) {
    html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">';
    html += oauthStatus.connected
      ? '<span class="status-badge status-connected">✓ Account connected</span>'
      : '<span class="status-badge status-error">No account</span>';
    html += '<button class="btn-primary" onclick="startVideoOAuth(\'' + vfEscape(provider.id) + '\')">' + (oauthStatus.connected ? "Reconnect account" : "Add account") + '</button>';
    html += '</div>';
    html += '<div class="vf-oauth-banner ' + (oauthStatus.connected ? "connected" : "") + '">';
    html += '<span>' + (oauthStatus.connected ? "✓" : "i") + '</span>';
    html += '<strong>' + vfEscape(oauthStatus.label || "Not connected") + '</strong>';
    html += '<button class="vf-text-button" onclick="refreshVideoOAuth(\'' + vfEscape(provider.id) + '\')">Refresh</button>';
    html += '</div>';
  }

  // Connections section (non-OAuth)
  if (!isOAuth) {
    html += '<div class="provider-section-box">';
    html += '<div class="section-box-header">';
    html += '<div class="section-title-group"><span class="section-box-title">Connections</span></div>';
    html += '<div class="section-controls-group">';
    html += '<select onchange="setVideoProviderMode(this.value)" class="mode-select-dropdown">';
    html += '<option value="priority"' + (data.load_balance_mode === "priority" ? " selected" : "") + '>Priority / fallback</option>';
    html += '<option value="round_robin"' + (data.load_balance_mode === "round_robin" ? " selected" : "") + '>Round robin</option>';
    html += '</select>';
    html += '<button class="btn-primary" style="padding:6px 14px;font-size:12px;" onclick="openVideoConnectionModal()">+ Add Connection</button>';
    html += '</div></div>';
    html += '<div class="connections-list">' + (connectionRows || connectionsEmpty) + '</div>';
    html += '</div>';
  }

  // Models section
  html += '<div class="provider-section-box" style="margin-top:24px;">';
  html += '<div class="section-box-header">';
  html += '<div class="section-title-group"><span class="section-box-title">Available Models</span></div>';
  html += '<div class="section-controls-group">';
  html += '<button class="btn-secondary" style="padding:6px 12px;font-size:12px;" onclick="openVideoCustomModelModal()">+ Add Model</button>';
  html += '</div></div>';
  html += '<div class="connections-list">' + (modelRows || modelsEmpty) + '</div>';
  html += '</div>';

  root.innerHTML = html;
}

function openVideoConnectionModal(connectionId = null) {
  if (!vfCurrentProviderDetails) return;
  const provider = vfCurrentProviderDetails.provider;
  const modal = document.getElementById("vf-connection-modal");
  modal.dataset.provider = provider.id;
  modal.dataset.connectionId = connectionId || "";
  document.getElementById("vf-connection-modal-title").textContent = (connectionId ? "Edit " : "Add ") + provider.name + (provider.category === "local" ? " endpoint" : " API key");
  document.getElementById("vf-connection-secret-label").textContent = provider.id === "vertex_ai" ? "Service account JSON / API key" : "API key";
  document.querySelectorAll(".vf-local-only").forEach(item => item.style.display = provider.category === "local" ? "flex" : "none");
  document.querySelectorAll(".vf-cloudflare-only").forEach(item => item.style.display = provider.id === "cloudflare" ? "flex" : "none");
  const connection = (vfCurrentProviderDetails.connections || []).find(item => item.id === Number(connectionId));
  document.getElementById("vf-connection-name").value = connection?.name || "";
  document.getElementById("vf-connection-secret").value = "";
  document.getElementById("vf-connection-secret").placeholder = connection?.has_secret ? "Leave blank to keep saved credential" : "Paste credential";
  document.getElementById("vf-connection-priority").value = connection?.priority || 1;
  document.getElementById("vf-connection-base-url").value = connection?.metadata?.base_url || provider.default_base_url || "";
  document.getElementById("vf-connection-account-id").value = connection?.metadata?.account_id || "";
  document.getElementById("vf-connection-bulk").value = "";
  document.getElementById("vf-connection-bulk-tab").style.display = connectionId || provider.category === "local" ? "none" : "inline-flex";
  setVideoConnectionMode("single");
  modal?.classList.remove("hidden");
}

function setVideoConnectionMode(mode) {
  vfConnectionMode = mode;
  document.getElementById("vf-connection-single-fields")?.classList.toggle("hidden", mode !== "single");
  document.getElementById("vf-connection-bulk-fields")?.classList.toggle("hidden", mode !== "bulk");
  document.getElementById("vf-connection-single-tab")?.classList.toggle("active", mode === "single");
  document.getElementById("vf-connection-bulk-tab")?.classList.toggle("active", mode === "bulk");
}

async function saveVideoConnection() {
  const modal = document.getElementById("vf-connection-modal");
  const provider = modal?.dataset.provider;
  const connectionId = Number(modal?.dataset.connectionId || 0);
  if (!provider) return;
  try {
    if (vfConnectionMode === "bulk") {
      const keys = (document.getElementById("vf-connection-bulk")?.value || "").split(/\r?\n/).map(item => item.trim()).filter(Boolean);
      if (!keys.length) throw new Error("Paste at least one API key.");
      await vfPost("/api/video-flow/providers/connections/add", {
        provider,
        keys: keys.map((secret, index) => ({name: "Key " + (index + 1), secret, priority: index + 1})),
      });
    } else {
      const secret = document.getElementById("vf-connection-secret")?.value || "";
      const metadata = {
        base_url: document.getElementById("vf-connection-base-url")?.value || "",
        account_id: document.getElementById("vf-connection-account-id")?.value || "",
      };
      const payload = {
        provider,
        name: document.getElementById("vf-connection-name")?.value || "Connection",
        priority: Number(document.getElementById("vf-connection-priority")?.value || 1),
        metadata,
      };
      if (secret) payload.secret = secret;
      if (connectionId) {
        payload.id = connectionId;
        await vfPost("/api/video-flow/providers/connections/update", payload);
      } else {
        if (vfCurrentProviderDetails.provider.category === "api_key" && !secret) throw new Error("Paste an API key or credential.");
        await vfPost("/api/video-flow/providers/connections/add", payload);
      }
    }
    closeVideoModal("vf-connection-modal");
    await openVideoProvider(provider);
    await loadVideoFlow();
    vfToast("Video Flow connection saved.");
  } catch (error) {
    vfToast(error.message, true);
  }
}

function editVideoConnection(connectionId) {
  openVideoConnectionModal(connectionId);
}

async function checkUnsavedVideoConnection() {
  const id = Number(document.getElementById("vf-connection-modal")?.dataset.connectionId || 0);
  if (!id) {
    vfToast("Save the connection first, then Video Flow can run a live test.");
    return;
  }
  await testVideoConnection(id);
}

async function testVideoConnection(connectionId) {
  try {
    await vfPost("/api/video-flow/providers/connections/test", {id: connectionId});
    vfToast("Connection test passed.");
  } catch (error) {
    vfToast(error.message, true);
  }
  if (vfCurrentProvider) await openVideoProvider(vfCurrentProvider);
}

async function testAllVideoConnections() {
  const groups = vfCatalog.provider_groups || {};
  const providers = [...(groups.api_key || []), ...(groups.local || [])];
  let tested = 0;
  let failed = 0;
  for (const provider of providers) {
    const response = await fetch("/api/video-flow/providers/details?provider=" + encodeURIComponent(provider.id));
    const details = await response.json();
    for (const connection of details.connections || []) {
      if (!connection.is_active) continue;
      try { await vfPost("/api/video-flow/providers/connections/test", {id: connection.id}); tested += 1; }
      catch (_) { failed += 1; }
    }
  }
  await loadVideoFlow();
  vfToast(tested + " connection" + (tested === 1 ? "" : "s") + " ready" + (failed ? " · " + failed + " failed" : ""), Boolean(failed));
}

async function deleteVideoConnection(connectionId) {
  try {
    await vfPost("/api/video-flow/providers/connections/delete", {id: connectionId});
    await openVideoProvider(vfCurrentProvider);
    await loadVideoFlow();
    vfToast("Connection deleted from Video Flow.");
  } catch (error) { vfToast(error.message, true); }
}

async function toggleVideoConnection(connectionId, isActive) {
  try {
    await vfPost("/api/video-flow/providers/connections/toggle", {id: connectionId, is_active: isActive});
    await openVideoProvider(vfCurrentProvider);
    await loadVideoFlow();
  } catch (error) { vfToast(error.message, true); }
}

async function setVideoProviderMode(mode) {
  try {
    await vfPost("/api/video-flow/providers/settings", {provider: vfCurrentProvider, load_balance_mode: mode});
    vfCurrentProviderDetails.load_balance_mode = mode;
    vfToast(mode === "round_robin" ? "Round robin enabled for Video Flow." : "Priority fallback enabled for Video Flow.");
  } catch (error) { vfToast(error.message, true); }
}

async function startVideoOAuth(providerId) {
  try {
    const result = await vfPost("/api/video-flow/providers/oauth/start", {provider: providerId});
    if (result.auth_url) {
      openVideoOAuthModal(providerId, result.auth_url);
    } else {
      vfToast(result.message || "Sign-in opened. Return here and press Refresh when it completes.");
    }
  } catch (error) { vfToast(error.message, true); }
}

function openVideoOAuthModal(providerId, authUrl) {
  vfOAuthProvider = providerId;
  const modal = document.getElementById("vf-oauth-modal");
  const name = vfCurrentProviderDetails?.provider?.name || providerId;
  document.getElementById("vf-oauth-provider-name").textContent = name;
  document.getElementById("vf-oauth-open-link").href = authUrl;
  document.getElementById("vf-oauth-code-input").value = "";
  document.getElementById("vf-oauth-status").textContent = "Sign-in window opening…";
  document.getElementById("vf-oauth-code-card")?.classList.add("hidden");
  modal?.classList.remove("hidden");

  if (!window.__vfOAuthMessageListener) {
    window.__vfOAuthMessageListener = true;
    window.addEventListener("message", async (event) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data || {};
      if (data.type !== "OAUTH_CALLBACK_SUCCESS") return;
      await exchangeVideoOAuthCode(vfOAuthProvider, data.code, data.state);
    });
  }

  let popup = null;
  try {
    popup = window.open(authUrl, "oauth_popup", "width=580,height=700,menubar=no,toolbar=no,location=no,status=no");
  } catch (_) { popup = null; }
  if (!popup) {
    document.getElementById("vf-oauth-status").textContent = "The popup was blocked. Open the login page, then paste the code here.";
    document.getElementById("vf-oauth-code-card")?.classList.remove("hidden");
    document.getElementById("vf-oauth-code-input").focus();
  }
}

async function exchangeVideoOAuthCode(providerId, code, state) {
  if (!providerId || !code) return;
  try {
    await vfPost("/api/video-flow/providers/oauth/exchange", {provider: providerId, code: code, state: state || ""});
    closeVideoModal("vf-oauth-modal");
    await loadVideoFlow();
    if (vfCurrentProvider === providerId) {
      await refreshCurrentVideoProviderDetail(providerId);
    }
    vfToast("Account connected to Video Flow. Models are now available.");
  } catch (error) { vfToast(error.message, true); }
}

async function completeVideoOAuthFromInput() {
  const raw = document.getElementById("vf-oauth-code-input")?.value.trim() || "";
  if (!raw) {
    vfToast("Paste the code or the full callback URL first.", true);
    return;
  }
  let code = raw;
  let state = "";
  if (raw.includes("?") || raw.includes("&")) {
    try {
      const url = new URL(raw.startsWith("http") ? raw : "http://127.0.0.1/" + raw.replace(/^\//, ""));
      code = url.searchParams.get("code") || code;
      state = url.searchParams.get("state") || "";
    } catch (_) {}
  }
  await exchangeVideoOAuthCode(vfOAuthProvider, code, state);
}

async function refreshVideoOAuth(providerId) {
  try {
    await vfPost("/api/video-flow/providers/oauth/status", {provider: providerId});
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(providerId);
    vfToast("Account status refreshed.");
  } catch (error) { vfToast(error.message, true); }
}

async function refreshVideoOAuthProviders() {
  const providers = vfCatalog.provider_groups?.oauth || [];
  for (const provider of providers) {
    try { await vfPost("/api/video-flow/providers/oauth/status", {provider: provider.id}); }
    catch (_) {}
  }
  await loadVideoFlow();
  vfToast("OAuth provider status refreshed.");
}

function openVideoCustomModelModal() {
  if (!vfCurrentProviderDetails) return;
  const modal = document.getElementById("vf-custom-model-modal");
  modal.dataset.provider = vfCurrentProvider;
  document.getElementById("vf-custom-model-prefix").textContent = vfCurrentProviderDetails.provider.prefix + "/";
  document.getElementById("vf-custom-model-id").value = "";
  document.getElementById("vf-custom-model-name").value = "";
  modal.querySelectorAll('.vf-capability-picker input').forEach(input => input.checked = false);
  modal?.classList.remove("hidden");
}

async function saveVideoCustomModel() {
  const modal = document.getElementById("vf-custom-model-modal");
  const provider = modal?.dataset.provider;
  const capabilities = [...modal.querySelectorAll('.vf-capability-picker input:checked')].map(input => input.value);
  try {
    await vfPost("/api/video-flow/providers/models/add", {
      provider,
      model_id: document.getElementById("vf-custom-model-id")?.value || "",
      display_name: document.getElementById("vf-custom-model-name")?.value || "",
      capabilities,
    });
    closeVideoModal("vf-custom-model-modal");
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(provider);
    vfToast("Custom model added with its provider prefix.");
  } catch (error) { vfToast(error.message, true); }
}

async function toggleVideoModel(modelId, isActive) {
  const provider = vfCurrentProvider;
  if (!provider) return;
  try {
    await vfPost("/api/video-flow/providers/models/toggle", {id: modelId, is_active: isActive});
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(provider);
  } catch (error) { vfToast(error.message, true); }
}

async function deleteVideoCustomModel(modelId) {
  const provider = vfCurrentProvider;
  if (!provider) return;
  try {
    await vfPost("/api/video-flow/providers/models/delete", {id: modelId});
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(provider);
    vfToast("Custom model removed.");
  } catch (error) { vfToast(error.message, true); }
}

async function copyVideoModelId(modelId) {
  try {
    await navigator.clipboard.writeText(modelId);
    vfToast("Model ID copied.");
  } catch (_) { vfToast(modelId); }
}
function openVideoComboModal() {
  const modal = document.getElementById("vf-combo-modal");
  vfComboDraftModels = [];
  const name = document.getElementById("vf-combo-name");
  const strategy = document.getElementById("vf-combo-strategy");
  if (name) name.value = "";
  if (strategy) strategy.value = "fallback";
  renderVideoComboDraft();
  modal?.classList.remove("hidden");
}

function vfVideoModelByRef(ref) {
  if (ref === "local/deterministic") {
    return {full_id: ref, display_name: "Built-in deterministic planner", provider_name: "On this PC", capabilities: ["private", "offline"]};
  }
  return (vfCatalog.models || []).find(model => model.full_id === ref);
}

function renderVideoComboDraft() {
  const root = document.getElementById("vf-combo-draft-list");
  if (!root) return;
  root.innerHTML = vfComboDraftModels.map((ref, index) => {
    const model = vfVideoModelByRef(ref) || {display_name: ref, provider_name: "Model", full_id: ref, capabilities: []};
    return '<div class="vf-combo-draft-row"><span class="vf-combo-grip">⠿</span><span class="vf-combo-position">' + (index + 1) + '</span><span class="vf-combo-draft-copy"><strong>' + vfEscape(model.display_name) + '</strong><small>' + vfEscape(model.provider_name) + ' · ' + vfEscape(model.full_id) + '</small></span><span class="vf-capability-list">' + vfCapabilityBadges(model) + '</span><button type="button" title="Move up" onclick="moveVideoComboModel(' + index + ', -1)" ' + (index === 0 ? "disabled" : "") + '>↑</button><button type="button" title="Move down" onclick="moveVideoComboModel(' + index + ', 1)" ' + (index === vfComboDraftModels.length - 1 ? "disabled" : "") + '>↓</button><button type="button" class="danger" title="Remove" onclick="removeVideoComboModel(' + index + ')">×</button></div>';
  }).join("") || '<div class="vf-empty-state vf-combo-draft-empty"><strong>No models added yet</strong><span>Add enabled models from your connected providers.</span></div>';
}

function moveVideoComboModel(index, direction) {
  const next = index + direction;
  if (next < 0 || next >= vfComboDraftModels.length) return;
  [vfComboDraftModels[index], vfComboDraftModels[next]] = [vfComboDraftModels[next], vfComboDraftModels[index]];
  renderVideoComboDraft();
}

function removeVideoComboModel(index) {
  vfComboDraftModels.splice(index, 1);
  renderVideoComboDraft();
  renderVideoComboModelPicker();
}

function openVideoComboModelPicker() {
  const search = document.getElementById("vf-combo-search");
  if (search) search.value = "";
  renderVideoComboModelPicker();
  document.getElementById("vf-combo-model-picker-modal")?.classList.remove("hidden");
  requestAnimationFrame(() => search?.focus());
}

function renderVideoComboModelPicker() {
  const root = document.getElementById("vf-combo-model-list");
  if (!root) return;
  const query = (document.getElementById("vf-combo-search")?.value || "").trim().toLowerCase();
  const models = vfSelectableVideoModels()
    .filter(model => model.full_id !== "local/deterministic")
    .filter(model =>
      !query || [model.provider_name, model.display_name, model.full_id, ...(model.capabilities || [])].join(" ").toLowerCase().includes(query)
    );
  const groups = new Map();
  for (const model of models) {
    const name = model.provider_name || model.provider;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(model);
  }
  const sections = [];
  if (!query || "on this pc built-in deterministic private offline".includes(query)) {
    const selected = vfComboDraftModels.includes("local/deterministic");
    sections.push('<section class="vf-picker-group"><h4>⌂ On this PC <span>1</span></h4><label class="vf-picker-model ' + (selected ? "selected" : "") + '"><input type="checkbox" ' + (selected ? "checked" : "") + ' onchange="toggleVideoComboDraftModel(\'local/deterministic\', this.checked)"><span><strong>Built-in deterministic planner</strong><small>Private · offline</small></span><b>✓</b></label></section>');
  }
  for (const [providerName, items] of groups.entries()) {
    sections.push('<section class="vf-picker-group"><h4>' + vfEscape(providerName) + ' <span>' + items.length + '</span></h4>' + items.map(model => {
      const selected = vfComboDraftModels.includes(model.full_id);
      return '<label class="vf-picker-model ' + (selected ? "selected" : "") + '"><input type="checkbox" ' + (selected ? "checked" : "") + ' onchange="toggleVideoComboDraftModel(\'' + vfEscape(model.full_id) + '\', this.checked)"><span><strong>' + vfEscape(model.display_name) + '</strong><small>' + vfEscape(model.full_id) + '</small></span><span class="vf-capability-list">' + vfCapabilityBadges(model) + '</span><b>✓</b></label>';
    }).join("") + '</section>');
  }
  root.innerHTML = sections.join("") || '<div class="vf-empty-state vf-compact-empty"><strong>No connected models match</strong><span>Connect a provider and enable models before building a combo.</span></div>';
}

function toggleVideoComboDraftModel(modelRef, checked) {
  const index = vfComboDraftModels.indexOf(modelRef);
  if (checked && index === -1) {
    if (!vfIsSelectableVideoModelRef(modelRef)) {
      vfToast("Only connected, enabled models can be added to a combo.", true);
      renderVideoComboModelPicker();
      return;
    }
    vfComboDraftModels.push(modelRef);
  }
  if (!checked && index !== -1) vfComboDraftModels.splice(index, 1);
  renderVideoComboDraft();
  renderVideoComboModelPicker();
}

function filterVideoComboModels() {
  renderVideoComboModelPicker();
}

async function createVideoCombo() {
  const name = (document.getElementById("vf-combo-name")?.value || "").trim();
  const strategy = document.getElementById("vf-combo-strategy")?.value || "fallback";
  const models = [...vfComboDraftModels];
  const unavailableModels = models.filter(modelRef => !vfIsSelectableVideoModelRef(modelRef));
  if (!name) {
    vfToast("Give the combo a name.", true);
    document.getElementById("vf-combo-name")?.focus();
    return;
  }
  if (!models.length) {
    vfToast("Add at least one connected, enabled model.", true);
    return;
  }
  if (unavailableModels.length) {
    vfComboDraftModels = models.filter(modelRef => !unavailableModels.includes(modelRef));
    renderVideoComboDraft();
    renderVideoComboModelPicker();
    vfToast("Unavailable models were removed. Add only connected, enabled models.", true);
    return;
  }
  try {
    const response = await fetch("/api/video-flow/combos/create", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, strategy, models}),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Could not create combo.");
    closeVideoModal("vf-combo-modal");
    vfComboDraftModels = [];
    await loadVideoFlow();
    vfToast("Model combo created.");
  } catch (error) {
    vfToast(error.message, true);
  }
}

async function deleteVideoCombo(comboId) {
  try {
    const response = await fetch("/api/video-flow/combos/delete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: comboId}),
    });
    if (!response.ok) throw new Error("Could not delete combo.");
    await loadVideoFlow();
    vfToast("Combo deleted. Generated videos were not affected.");
  } catch (error) {
    vfToast(error.message, true);
  }
}

function previewVideoFlow(videoId) {
  const video = vfVideos.find(item => String(item.id) === String(videoId));
  if (!video) return;
  vfPreviewVideo = video;
  const player = document.getElementById("vf-preview-player");
  const title = document.getElementById("vf-preview-title");
  const download = document.getElementById("vf-preview-download");
  const stage = document.getElementById("vf-v3-canvas-stage");
  const viewUrl = video.view_url || (`/api/video-flow/videos/file?id=` + encodeURIComponent(video.id));
  const downloadUrl = video.download_url || (`/api/video-flow/videos/file?id=` + encodeURIComponent(video.id) + `&download=1`);

  if (player) {
    player.setAttribute("src", viewUrl);
    player.src = viewUrl;
    player.load();
    player.play().catch(() => {});
  }
  if (title) title.textContent = video.title;
  if (download) download.href = downloadUrl;

  // Load V3 Visual Explanation Program & render live visual stage
  fetch(`/api/video-flow/v3/program?id=${encodeURIComponent(videoId)}`)
    .then(res => res.json())
    .then(data => {
      if (data && data.success && data.program && data.program.scenes && data.program.scenes.length > 0) {
        if (stage) {
          stage.style.opacity = "1";
          const prog = data.program;
          const scenes = prog.scenes;
          const updateStage = () => {
            const currentTime = player ? player.currentTime : 0;
            const dur = player && player.duration ? player.duration : 15;
            const sceneIdx = Math.min(scenes.length - 1, Math.floor((currentTime / dur) * scenes.length));
            const sc = scenes[sceneIdx] || scenes[0];
            const goalEl = document.getElementById("vf-v3-stage-goal");
            const headerEl = document.getElementById("vf-v3-stage-header");
            const cardsEl = document.getElementById("vf-v3-stage-cards");
            if (headerEl) headerEl.textContent = `SCENE ${sceneIdx + 1} OF ${scenes.length} · VISUAL EXPLANATION`;
            if (goalEl) goalEl.textContent = sc.intended_understanding || sc.teaching_goal || video.title;
            if (cardsEl) {
              const objs = sc.semantic_objects || [];
              cardsEl.innerHTML = objs.map(o => `
                <div style="background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; padding: 10px 14px; font-size: 13px; color: #f8fafc; display: flex; align-items: center; gap: 8px;">
                  <span style="color: var(--primary-orange, #ff6b00); font-weight: 800;">✦</span>
                  <strong>${vfEscape(o.label || o.object_id)}</strong>
                </div>
              `).join("") || `<div style="font-size: 13px; color: #94a3b8;">✦ ${vfEscape(sc.narration_text || "")}</div>`;
            }
          };
          updateStage();
          if (player) player.ontimeupdate = updateStage;
        }
      } else {
        if (stage) stage.style.opacity = "0";
      }
    })
    .catch(() => {
      if (stage) stage.style.opacity = "0";
    });

  document.getElementById("vf-preview-modal")?.classList.remove("hidden");
}

function toggleVideoPreviewFullscreen() {
  const player = document.getElementById("vf-preview-player");
  if (!player) return;
  if (document.fullscreenElement) {
    document.exitFullscreen?.();
  } else {
    player.requestFullscreen?.();
  }
}

async function sharePreviewVideo() {
  if (vfPreviewVideo) await shareVideoFlow(vfPreviewVideo.id);
}

async function shareVideoFlow(videoId) {
  const video = vfVideos.find(item => item.id === videoId);
  if (!video || !video.view_url) return;
  try {
    const response = await fetch(video.view_url);
    const blob = await response.blob();
    const file = new File([blob], `${video.title || "video-flow"}.mp4`, {type: "video/mp4"});
    if (navigator.share && (!navigator.canShare || navigator.canShare({files: [file]}))) {
      await navigator.share({title: video.title, text: "Created with Voice Flow Video Flow", files: [file]});
      return;
    }
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(`${location.origin}${video.view_url}`);
      vfToast("Local video link copied. It opens on this PC while Voice Flow is running.");
      return;
    }
    window.location.href = video.download_url;
  } catch (error) {
    if (error?.name !== "AbortError") vfToast("Sharing is unavailable here; use Download instead.", true);
  }
}

async function retryVideoFlow(videoId) {
  const response = await fetch("/api/video-flow/videos/retry", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: videoId}),
  });
  if (!response.ok) {
    vfToast("Could not retry that video.", true);
    return;
  }
  const video = vfVideos.find(item => item.id === videoId);
  if (video) Object.assign(video, {status: "queued", progress: 0, stage: "Queued", error: ""});
  renderVideoHistory();
  scheduleVideoFlowPolling(true);
}

function beginVideoDelete(videoId) {
  vfDeleteTarget = videoId;
  document.getElementById("vf-delete-first-modal")?.classList.remove("hidden");
}

function continueVideoDelete() {
  document.getElementById("vf-delete-first-modal")?.classList.add("hidden");
  const input = document.getElementById("vf-delete-confirm-input");
  if (input) input.value = "";
  updateFinalDeleteButton();
  document.getElementById("vf-delete-final-modal")?.classList.remove("hidden");
  window.setTimeout(() => input?.focus(), 60);
}

function updateFinalDeleteButton() {
  const input = document.getElementById("vf-delete-confirm-input");
  const button = document.getElementById("vf-delete-final-button");
  if (button) button.disabled = input?.value !== "DELETE";
}

function cancelVideoDelete() {
  vfDeleteTarget = null;
  document.getElementById("vf-delete-first-modal")?.classList.add("hidden");
  document.getElementById("vf-delete-final-modal")?.classList.add("hidden");
}

async function permanentlyDeleteVideo() {
  if (!vfDeleteTarget || document.getElementById("vf-delete-confirm-input")?.value !== "DELETE") return;
  const videoId = vfDeleteTarget;
  try {
    const response = await fetch("/api/video-flow/videos/delete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: videoId, confirmation: VF_PERMANENT_CONFIRMATION}),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Could not delete video.");
    vfVideos = vfVideos.filter(video => video.id !== videoId);
    cancelVideoDelete();
    renderVideoHistory();
    vfToast("Video and all project files were permanently deleted from this PC.");
  } catch (error) {
    vfToast(error.message, true);
  }
}

function closeVideoModal(modalId) {
  const modal = document.getElementById(modalId);
  modal?.classList.add("hidden");
  if (modalId === "vf-combo-modal") {
    document.getElementById("vf-combo-model-picker-modal")?.classList.add("hidden");
  }
  if (modalId === "vf-preview-modal") {
    const player = document.getElementById("vf-preview-player");
    player?.pause();
    if (player) player.removeAttribute("src");
    vfPreviewVideo = null;
  }
}

function vfToast(message, isError = false) {
  const toast = document.getElementById("vf-toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(vfToast.timer);
  vfToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
}
