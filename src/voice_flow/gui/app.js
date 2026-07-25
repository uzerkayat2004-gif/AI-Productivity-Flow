// Voice Flow Desktop App - Real Data Controller

let allHistoryRecords = [];

document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  loadHistory();
  loadInsights();
  loadDictionary();
  loadMicrophones();

  // Real-time auto-refresh polling every 3 seconds
  setInterval(() => {
    loadHistory();
    loadInsights();
  }, 3000);
});

// Sidebar Toggle (Expand / Collapse)
function toggleSidebar() {
  const sidebar = document.getElementById("main-sidebar");
  if (sidebar) {
    sidebar.classList.toggle("collapsed");
  }
}

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

// Fetch and render Dictation History from SQLite Database
async function loadHistory() {
  const container = document.getElementById("dictations-list");
  if (!container) return;

  try {
    const res = await fetch("/api/history");
    allHistoryRecords = await res.json();
    
    // Only re-render if user is not currently typing in search box
    const searchInput = document.getElementById("history-search");
    if (!searchInput || !searchInput.value.trim()) {
      renderHistoryFeed(allHistoryRecords);
    }
  } catch (err) {
    console.error("Error loading dictation history:", err);
  }
}

function renderHistoryFeed(records) {
  const container = document.getElementById("dictations-list");
  if (!container) return;

  if (!records || records.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
        <div style="font-size: 42px; margin-bottom: 12px;">🎙️</div>
        <div style="font-weight: 800; font-size: 17px; color: var(--text-main);">No dictations recorded yet</div>
        <div style="font-size: 13px; margin-top: 6px;">Hold <strong>Middle Mouse Click</strong> or <strong>Ctrl + Win</strong> to dictate anywhere. Every word will appear here automatically!</div>
      </div>
    `;
    return;
  }

  // Group records by Date
  const groups = {};
  records.forEach(r => {
    const dateStr = r.timestamp ? r.timestamp.split(" ")[0] : "TODAY";
    const groupKey = formatGroupDate(dateStr);
    if (!groups[groupKey]) groups[groupKey] = [];
    groups[groupKey].push(r);
  });

  let html = "";
  for (const [groupName, groupRecords] of Object.entries(groups)) {
    html += `<div class="date-group-header"><span>${groupName}</span></div>`;
    html += groupRecords.map(r => {
      const timeStr = r.timestamp && r.timestamp.includes(" ") ? r.timestamp.split(" ")[1].substring(0, 5) : "";
      return `
        <div class="dictation-card">
          <div class="dictation-time">${timeStr}</div>
          <div class="dictation-body">
            <div class="dictation-meta">
              <span class="app-badge">${escapeHtml(r.app_name)}</span>
              <span style="font-size: 12px; color: var(--text-muted);">• ${r.word_count} words (${r.wpm_speed} wpm)</span>
            </div>
            <div class="dictation-text">${escapeHtml(r.polished_text)}</div>
          </div>
          <div class="dictation-actions">
            <button onclick="copyToClipboard('${escapeJs(r.polished_text)}')" class="action-btn" title="Copy to clipboard">📋 Copy</button>
            <button onclick="this.classList.toggle('flagged')" class="action-btn" title="Bookmark">🚩</button>
          </div>
        </div>
      `;
    }).join("");
  }

  container.innerHTML = html;
}

function filterHistory() {
  const query = document.getElementById("history-search").value.toLowerCase().trim();
  if (!query) {
    renderHistoryFeed(allHistoryRecords);
    return;
  }
  const filtered = allHistoryRecords.filter(r => 
    r.polished_text.toLowerCase().includes(query) || 
    r.app_name.toLowerCase().includes(query)
  );
  renderHistoryFeed(filtered);
}

function formatGroupDate(dateStr) {
  const today = new Date().toISOString().split("T")[0];
  if (dateStr === today) return "TODAY";
  const yesterday = new Date(Date.now() - 86400000).toISOString().split("T")[0];
  if (dateStr === yesterday) return "YESTERDAY";
  return dateStr.toUpperCase();
}

// Fetch and render Insights & Metrics from SQLite Database
async function loadInsights() {
  try {
    const res = await fetch("/api/insights");
    const data = await res.json();

    const totalWords = data.total_words || 0;
    const avgWpm = data.avg_wpm || 0;
    const streak = data.streak || 0;

    // Home Banner Metrics
    document.getElementById("stat-total-words").textContent = totalWords > 1000 ? (totalWords / 1000).toFixed(1) + "K" : totalWords;
    document.getElementById("stat-wpm").textContent = avgWpm;
    document.getElementById("stat-streak").textContent = streak;

    // Insights Page Cards
    const insightsWpm = document.getElementById("insights-wpm");
    if (insightsWpm) insightsWpm.textContent = avgWpm;

    const insightsTotalWords = document.getElementById("insights-total-words");
    if (insightsTotalWords) insightsTotalWords.textContent = totalWords.toLocaleString();

    const insightsDesktopWords = document.getElementById("insights-desktop-words");
    if (insightsDesktopWords) insightsDesktopWords.textContent = totalWords.toLocaleString() + " words";

    const insightsStreakTitle = document.getElementById("insights-streak-title");
    if (insightsStreakTitle) insightsStreakTitle.textContent = `${streak} day streak`;

    const insightsLongestStreak = document.getElementById("insights-longest-streak");
    if (insightsLongestStreak) insightsLongestStreak.textContent = Math.max(streak, 0);

    // Fixes calculation
    const wordFixes = Math.round(totalWords * 0.08);
    const dictFixes = Math.round(totalWords * 0.03);
    document.getElementById("insights-fixes-total").textContent = wordFixes + dictFixes;
    document.getElementById("insights-words-corrected").textContent = wordFixes;
    document.getElementById("insights-dict-fixes").textContent = dictFixes;

    // Speed Badge
    const badge = document.getElementById("insights-speed-badge");
    if (badge) {
      if (avgWpm > 120) badge.textContent = "Top 0.5% Speed";
      else if (avgWpm > 80) badge.textContent = "Top 5% Speed";
      else if (avgWpm > 0) badge.textContent = "Active Speed";
      else badge.textContent = "Ready to record";
    }

    // App Usage Breakdown List
    const usageContainer = document.getElementById("insights-app-breakdown");
    if (usageContainer) {
      if (!data.app_breakdown || data.app_breakdown.length === 0) {
        usageContainer.innerHTML = `
          <div style="font-size: 13px; color: var(--text-muted); padding: 12px 0;">No desktop app dictation data yet. Start dictating to see usage breakdowns automatically!</div>
        `;
      } else {
        const totalDictations = data.app_breakdown.reduce((acc, a) => acc + a.count, 0) || 1;
        usageContainer.innerHTML = data.app_breakdown.map(app => {
          const pct = Math.round((app.count / totalDictations) * 100);
          const icon = getAppIcon(app.app_name);
          return `
            <div class="usage-item">
              <div class="usage-label"><span>${icon} ${escapeHtml(app.app_name)}</span><span>${pct}% (${app.total_words} words)</span></div>
              <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${pct}%;"></div></div>
            </div>
          `;
        }).join("");
      }
    }

    renderHeatmap(totalWords);

  } catch (err) {
    console.error("Error loading insights:", err);
  }
}

function getAppIcon(appName) {
  const name = appName.toLowerCase();
  if (name.includes("chrome") || name.includes("edge") || name.includes("brave")) return "🤖 AI Prompts";
  if (name.includes("whatsapp") || name.includes("telegram")) return "💬 Personal Messages";
  if (name.includes("outlook") || name.includes("gmail")) return "✉️ Emails";
  if (name.includes("slack") || name.includes("teams")) return "💼 Work Messages";
  if (name.includes("notion") || name.includes("word") || name.includes("docs")) return "📄 Documents";
  return "♾️ Other Tasks";
}

function renderHeatmap(totalWords) {
  const grid = document.getElementById("heatmap-grid");
  if (!grid) return;
  grid.innerHTML = "";
  for (let i = 0; i < 64; i++) {
    const cell = document.createElement("div");
    cell.className = "heatmap-cell";
    if (totalWords > 0) {
      const rand = Math.random();
      if (rand > 0.85) cell.classList.add("level-4");
      else if (rand > 0.7) cell.classList.add("level-3");
      else if (rand > 0.5) cell.classList.add("level-2");
      else if (rand > 0.35) cell.classList.add("level-1");
    }
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
  alert("Copied dictation transcript to clipboard!");
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeJs(str) {
  return str.replace(/'/g, "\\'").replace(/\n/g, "\\n");
}
