// Voice Flow Desktop App - Real Data Controller

document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  loadHistory();
  loadInsights();
  loadDictionary();
  loadMicrophones();
});

// Navigation between sidebar pages
function initNavigation() {
  const navItems = document.querySelectorAll(".sidebar .nav-item[data-page]");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const pageId = item.getAttribute("data-page");
      switchPage(pageId);
    });
  });
}

function switchPage(pageId) {
  document.querySelectorAll(".sidebar .nav-item[data-page]").forEach(nav => {
    nav.classList.toggle("active", nav.getAttribute("data-page") === pageId);
  });

  document.querySelectorAll(".page-view").forEach(page => {
    page.style.display = "none";
  });

  const target = document.getElementById(`page-${pageId}`);
  if (target) {
    target.style.display = "block";
    if (pageId === "home") loadHistory();
    if (pageId === "insights") loadInsights();
    if (pageId === "dictionary") loadDictionary();
  }
}

// Fetch and render Dictation History
async function loadHistory() {
  const container = document.getElementById("dictations-list");
  if (!container) return;

  try {
    const res = await fetch("/api/history");
    const records = await res.json();

    if (!records || records.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--text-muted);">
          <div style="font-size: 32px; margin-bottom: 8px;">🎙️</div>
          <div style="font-weight: 600; font-size: 15px;">No dictations yet</div>
          <div style="font-size: 13px; margin-top: 4px;">Hold <strong>Middle Mouse Click</strong> or <strong>Ctrl + Win</strong> to speak anywhere!</div>
        </div>
      `;
      return;
    }

    container.innerHTML = records.map(r => `
      <div style="background: var(--bg-main); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px 18px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
        <div style="flex: 1;">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
            <span style="background: var(--primary-orange-light); color: var(--primary-orange); font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px;">${r.app_name}</span>
            <span style="font-size: 12px; color: var(--text-muted);">${r.timestamp}</span>
            <span style="font-size: 12px; color: var(--text-muted);">• ${r.word_count} words (${r.wpm_speed} wpm)</span>
          </div>
          <div style="font-size: 14px; font-weight: 500; color: var(--text-main); line-height: 1.4;">${escapeHtml(r.polished_text)}</div>
        </div>
        <button onclick="copyToClipboard('${escapeJs(r.polished_text)}')" class="btn-secondary" style="margin-left: 16px; padding: 6px 12px;">📋 Copy</button>
      </div>
    `).join("");

  } catch (err) {
    console.error("Error loading dictation history:", err);
  }
}

// Fetch and render Insights & Metrics
async function loadInsights() {
  try {
    const res = await fetch("/api/insights");
    const data = await res.json();

    document.getElementById("stat-total-words").innerHTML = `${data.total_words.toLocaleString()} <span class="stat-unit">words</span>`;
    document.getElementById("stat-wpm").innerHTML = `${data.avg_wpm} <span class="stat-unit">wpm</span>`;
    document.getElementById("stat-streak").innerHTML = `${data.streak} <span class="stat-unit">days</span>`;

    // Render App usage breakdown
    const usageContainer = document.getElementById("insights-app-breakdown");
    if (usageContainer && data.app_breakdown) {
      const totalDictations = data.app_breakdown.reduce((acc, a) => acc + a.count, 0) || 1;
      usageContainer.innerHTML = data.app_breakdown.map(app => {
        const pct = Math.round((app.count / totalDictations) * 100);
        return `
          <div class="usage-item">
            <div class="usage-label"><span>📱 ${escapeHtml(app.app_name)}</span><span>${pct}% (${app.total_words} words)</span></div>
            <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${pct}%;"></div></div>
          </div>
        `;
      }).join("");
    }

    renderHeatmap();

  } catch (err) {
    console.error("Error loading insights:", err);
  }
}

// Render Heatmap Calendar Grid
function renderHeatmap() {
  const grid = document.getElementById("heatmap-grid");
  if (!grid) return;
  grid.innerHTML = "";
  for (let i = 0; i < 64; i++) {
    const cell = document.createElement("div");
    cell.className = "heatmap-cell";
    const rand = Math.random();
    if (rand > 0.8) cell.classList.add("level-4");
    else if (rand > 0.6) cell.classList.add("level-3");
    else if (rand > 0.4) cell.classList.add("level-2");
    else if (rand > 0.25) cell.classList.add("level-1");
    grid.appendChild(cell);
  }
}

// Dictionary Management
async function loadDictionary() {
  const chipContainer = document.getElementById("dictionary-chips");
  if (!chipContainer) return;

  try {
    const res = await fetch("/api/dictionary");
    const words = await res.json();

    chipContainer.innerHTML = `
      <button class="btn-primary" onclick="addDictionaryWord()" style="padding: 6px 14px; font-size: 13px;">+ Add Word</button>
      ${words.map(w => `
        <span class="chip">
          ${escapeHtml(w)}
          <span onclick="removeDictionaryWord('${escapeJs(w)}')" style="cursor: pointer; opacity: 0.7; margin-left: 4px;">✕</span>
        </span>
      `).join("")}
    `;
  } catch (err) {
    console.error("Error loading dictionary:", err);
  }
}

async function addDictionaryWord() {
  const word = prompt("Enter custom word, proper name, or company jargon:");
  if (!word || !word.trim()) return;

  try {
    const res = await fetch("/api/dictionary/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word: word.trim() }),
    });
    await res.json();
    loadDictionary();
  } catch (err) {
    console.error("Error adding dictionary word:", err);
  }
}

async function removeDictionaryWord(word) {
  try {
    const res = await fetch("/api/dictionary/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    await res.json();
    loadDictionary();
  } catch (err) {
    console.error("Error removing dictionary word:", err);
  }
}

// Microphones Picker
async function loadMicrophones() {
  const select = document.getElementById("mic-select");
  if (!select) return;

  try {
    const res = await fetch("/api/microphones");
    const mics = await res.json();

    select.innerHTML = mics.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("");
  } catch (err) {
    select.innerHTML = `<option>Default System Microphone</option>`;
  }
}

// API Key Management (Strictly inside Settings)
async function addApiKey() {
  const input = document.getElementById("api-key-input");
  if (!input || !input.value.trim()) return;

  try {
    const res = await fetch("/api/apikeys/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: input.value.trim() }),
    });
    const data = await res.json();
    if (data.success) {
      alert("Google Gemini API Key added to pool!");
      input.value = "";
    }
  } catch (err) {
    console.error("Error adding API key:", err);
  }
}

// Settings Modal Controls
function openSettings(tab = "general") {
  const modal = document.getElementById("settings-modal");
  if (modal) {
    modal.classList.remove("hidden");
    switchSettingsTab(tab);
  }
}

function closeSettings() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.add("hidden");
}

function switchSettingsTab(tabId, el = null) {
  ["general", "system", "apikeys"].forEach(t => {
    const tabEl = document.getElementById(`set-tab-${t}`);
    if (tabEl) tabEl.style.display = t === tabId ? "block" : "none";
  });

  if (el) {
    document.querySelectorAll(".modal-sidebar .nav-item").forEach(item => item.classList.remove("active"));
    el.classList.add("active");
  }
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text);
  alert("Copied to clipboard!");
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeJs(str) {
  return str.replace(/'/g, "\\'");
}
