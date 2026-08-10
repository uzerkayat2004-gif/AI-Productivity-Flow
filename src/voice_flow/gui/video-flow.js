let vfCatalog = {providers: [], models: [], combos: [], active_model: "local/deterministic"};
let vfVideos = [];
let vfPollTimer = null;
let vfDeleteTarget = null;
let vfPreviewVideo = null;

const VF_PERMANENT_CONFIRMATION = "DELETE_VIDEO_FROM_THIS_PC";
const vfProviderIcons = {
  gemini: "✦",
  groq: "⚡",
  openai: "◎",
  huggingface: "HF",
  cloudflare: "☁",
  together: "↔",
  replicate: "R",
  elevenlabs: "11",
  deepgram: "D",
  assemblyai: "A",
};

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
    vfVideos = historyData.videos || [];
    renderVideoHistory();
    renderVideoCatalog();
    scheduleVideoFlowPolling();
  } catch (error) {
    vfToast(error.message || "Could not load Video Flow.", true);
    const status = document.getElementById("vf-engine-status");
    if (status) status.textContent = "○ Renderer unavailable";
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
    const complete = video.status === "completed";
    const failed = video.status === "failed";
    const mode = video.mode === "full" ? "Full explanation" : "Summary";
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
          <div class="vf-video-meta"><span>${vfFormatDate(video.created_at)}</span><span>${vfFormatDuration(video.duration_sec)}</span></div>
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

function renderVideoCatalog() {
  const select = document.getElementById("vf-model-select");
  if (select) {
    const groups = new Map();
    for (const model of vfCatalog.models || []) {
      const name = model.provider_name || model.provider;
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(model);
    }
    select.innerHTML = [...groups.entries()].map(([name, models]) =>
      `<optgroup label="${vfEscape(name)}">${models.map(model =>
        `<option value="${vfEscape(model.full_id)}">${vfEscape(model.display_name)}</option>`
      ).join("")}</optgroup>`
    ).join("") + ((vfCatalog.combos || []).length
      ? `<optgroup label="Model Combos">${vfCatalog.combos.map(combo =>
          `<option value="${vfEscape(combo.ref)}">◈ ${vfEscape(combo.name)} · ${vfEscape(combo.strategy.replace("_", " "))}</option>`
        ).join("")}</optgroup>`
      : "");
    select.value = vfCatalog.active_model || "local/deterministic";
    if (!select.value) select.value = "local/deterministic";
    updateActiveVideoModel(select.value);
  }

  const strip = document.getElementById("vf-combo-strip");
  if (strip) {
    strip.innerHTML = (vfCatalog.combos || []).map(combo =>
      `<span class="vf-combo-pill">◈ ${vfEscape(combo.name)} · ${combo.models.length} models · ${vfEscape(combo.strategy.replace("_", " "))}
        <button title="Delete combo" onclick="deleteVideoCombo(${Number(combo.id)})">×</button>
      </span>`
    ).join("");
  }

  const grid = document.getElementById("vf-provider-grid");
  if (grid) {
    grid.innerHTML = (vfCatalog.providers || []).map(provider => `
      <button class="vf-provider-card ${provider.status === "connected" ? "connected" : ""}" onclick="openVideoProvider('${vfEscape(provider.id)}')">
        <span class="vf-provider-logo">${vfEscape(vfProviderIcons[provider.id] || "AI")}</span>
        <span><strong>${vfEscape(provider.name)}</strong><span>● ${provider.connection_count} connection${provider.connection_count === 1 ? "" : "s"}</span></span>
      </button>
    `).join("");
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

async function generateVideoFlow() {
  const sourceInput = document.getElementById("vf-source-input");
  const titleInput = document.getElementById("vf-title-input");
  const modelSelect = document.getElementById("vf-model-select");
  const themeSelect = document.getElementById("vf-theme-select");
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
  if (!modelRef.startsWith("local/") && !consent) {
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
        theme: themeSelect?.value || "voice-flow",
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Could not start Video Flow.");
    vfVideos.unshift(data.video);
    renderVideoHistory();
    scheduleVideoFlowPolling(true);
    vfToast("Video queued. You can follow its progress in history.");
    if (message) message.textContent = "Generation is running in the background.";
    document.getElementById("vf-history-panel")?.scrollIntoView({behavior: "smooth"});
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
  } catch (error) {
    vfToast(error.message, true);
  }
}

function updateActiveVideoModel(modelRef) {
  const label = document.getElementById("vf-active-model-label");
  const detail = document.getElementById("vf-active-model-detail");
  if (modelRef.startsWith("combo:")) {
    const combo = (vfCatalog.combos || []).find(item => item.ref === modelRef);
    if (label) label.textContent = combo ? "◈ " + combo.name : modelRef;
    if (detail) detail.textContent = combo ? combo.models.length + " models · " + combo.strategy.replace("_", " ") : "Model combo";
  } else {
    const model = (vfCatalog.models || []).find(item => item.full_id === modelRef);
    if (label) label.textContent = model ? model.provider_name + " — " + model.display_name : modelRef;
    if (detail) detail.textContent = modelRef.startsWith("local/") ? "Works without an API key" : "Uses active provider connections and failover settings";
  }
  updateVideoExternalConsent(modelRef);
}

function updateVideoExternalConsent(modelRef) {
  const row = document.getElementById("vf-external-consent-row");
  const checkbox = document.getElementById("vf-external-consent");
  const copy = document.getElementById("vf-external-consent-copy");
  if (!row || !checkbox || !copy) return;
  if (modelRef.startsWith("local/")) {
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
function openVideoProvider(providerId) {
  switchPage("providers");
  window.setTimeout(() => {
    if (typeof openProviderDetail === "function") openProviderDetail(providerId);
  }, 40);
}

function openVideoComboModal() {
  const modal = document.getElementById("vf-combo-modal");
  const list = document.getElementById("vf-combo-model-list");
  const search = document.getElementById("vf-combo-search");
  if (search) search.value = "";
  if (list) {
    list.innerHTML = (vfCatalog.models || []).filter(model => !model.full_id.startsWith("local/")).map(model => `
      <label class="vf-model-option" data-search="${vfEscape(`${model.provider_name} ${model.display_name} ${model.full_id}`.toLowerCase())}">
        <input type="checkbox" value="${vfEscape(model.full_id)}">
        <span><strong>${vfEscape(model.display_name)}</strong><small>${vfEscape(model.provider_name)} · ${vfEscape(model.model_id)}</small></span>
      </label>
    `).join("") || '<div class="vf-empty-state"><strong>No connected provider models</strong><span>Add a provider API key first.</span></div>';
  }
  modal?.classList.remove("hidden");
}

function filterVideoComboModels() {
  const query = (document.getElementById("vf-combo-search")?.value || "").toLowerCase();
  document.querySelectorAll("#vf-combo-model-list .vf-model-option").forEach(item => {
    item.style.display = (item.dataset.search || "").includes(query) ? "flex" : "none";
  });
}

async function createVideoCombo() {
  const name = document.getElementById("vf-combo-name")?.value || "";
  const strategy = document.getElementById("vf-combo-strategy")?.value || "fallback";
  const models = [...document.querySelectorAll("#vf-combo-model-list input:checked")].map(input => input.value);
  try {
    const response = await fetch("/api/video-flow/combos/create", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, strategy, models}),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Could not create combo.");
    closeVideoModal("vf-combo-modal");
    document.getElementById("vf-combo-name").value = "";
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
  const video = vfVideos.find(item => item.id === videoId);
  if (!video || video.status !== "completed") return;
  vfPreviewVideo = video;
  const player = document.getElementById("vf-preview-player");
  const title = document.getElementById("vf-preview-title");
  const download = document.getElementById("vf-preview-download");
  if (player) player.src = video.view_url;
  if (title) title.textContent = video.title;
  if (download) download.href = video.download_url;
  document.getElementById("vf-preview-modal")?.classList.remove("hidden");
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
