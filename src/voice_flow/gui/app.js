// Voice Flow Desktop App - Real Data Controller
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

let allHistoryRecords = [];
let isHandsFreeRecording = false;

// Style Configuration & Scenarios
const STYLE_DATA = {
  personal: {
    heroTitle: "This style applies in personal messengers",
    heroDesc: "Style formatting applies instantly across personal desktop messaging apps.",
    appIcons: `<span class="app-icon-pill">💬 WhatsApp</span><span class="app-icon-pill">✈️ Telegram</span><span class="app-icon-pill">👾 Discord</span><span class="app-icon-pill">📸 Instagram</span>`,
    cards: [
      {
        id: "personal_formal",
        name: "Formal.",
        subtitle: "Caps + Punctuation",
        sample: "Hey, are you free for lunch tomorrow? Let's do 12:30 PM if that works for you.",
        avatar: "J"
      },
      {
        id: "personal_casual",
        name: "Casual",
        subtitle: "Caps + Less punctuation",
        sample: "Hey are you free for lunch tomorrow? Let's do 12:30 if that works for you",
        avatar: "J"
      },
      {
        id: "personal_very_casual",
        name: "very casual",
        subtitle: "No Caps + Less punctuation",
        sample: "hey are you free for lunch tomorrow let's do 12 if that works for you",
        avatar: "J"
      }
    ]
  },
  work: {
    heroTitle: "This style applies in workplace messengers",
    heroDesc: "Style formatting applies instantly across Slack, Microsoft Teams, and LinkedIn.",
    appIcons: `<span class="app-icon-pill">💼 Slack</span><span class="app-icon-pill">🟦 Teams</span><span class="app-icon-pill">💼 LinkedIn</span>`,
    cards: [
      {
        id: "work_formal",
        name: "Formal.",
        subtitle: "Caps + Punctuation",
        sample: "John Doe 9:45 AM\nHey, if you're free, let's chat about the great results.",
        avatar: "J"
      },
      {
        id: "work_casual",
        name: "Casual",
        subtitle: "Caps + Less punctuation",
        sample: "John Doe 9:45 AM\nHey, if you're free let's chat about the great results",
        avatar: "J"
      },
      {
        id: "work_excited",
        name: "Excited!",
        subtitle: "More exclamations",
        sample: "John Doe 9:45 AM\nHey, if you're free, let's chat about the great results!",
        avatar: "J"
      }
    ]
  },
  email: {
    heroTitle: "This style applies in all major email apps",
    heroDesc: "Style formatting applies across Outlook, Gmail, Mailbird, and Windows Mail.",
    appIcons: `<span class="app-icon-pill">✉️ Outlook</span><span class="app-icon-pill">📨 Gmail</span><span class="app-icon-pill">📮 Windows Mail</span>`,
    cards: [
      {
        id: "email_formal",
        name: "Formal.",
        subtitle: "Caps + Punctuation",
        sample: "To: Alex Doe\n\nHi Alex,\n\nIt was great talking with you today. Looking forward to our next chat.\n\nBest,\nMary",
        avatar: "M"
      },
      {
        id: "email_casual",
        name: "Casual",
        subtitle: "Caps + Less punctuation",
        sample: "To: Alex Doe\n\nHi Alex, it was great talking with you today. Looking forward to our next chat.\n\nBest,\nMary",
        avatar: "M"
      },
      {
        id: "email_excited",
        name: "Excited!",
        subtitle: "More exclamations",
        sample: "To: Alex Doe\n\nHi Alex,\n\nIt was great talking with you today! Looking forward to our next chat!\n\nBest,\nMary",
        avatar: "M"
      }
    ]
  },
  other: {
    heroTitle: "This style applies in all other apps",
    heroDesc: "Style formatting applies across Notion, Word, Google Docs, and ChatGPT.",
    appIcons: `<span class="app-icon-pill">📄 Notion</span><span class="app-icon-pill">📝 Word</span><span class="app-icon-pill">🤖 ChatGPT</span>`,
    cards: [
      {
        id: "other_formal",
        name: "Formal.",
        subtitle: "Caps + Punctuation",
        sample: "So far, I am enjoying the new workout routine.\n\nI am excited for tomorrow's workout, especially after a full night of rest.",
        avatar: "A"
      },
      {
        id: "other_casual",
        name: "Casual",
        subtitle: "Caps + Less punctuation",
        sample: "So far I am enjoying the new workout routine.\n\nI am excited for tomorrow's workout especially after a full night of rest.",
        avatar: "A"
      },
      {
        id: "other_excited",
        name: "Excited!",
        subtitle: "More exclamations",
        sample: "So far, I am enjoying the new workout routine!\n\nI am excited for tomorrow's workout, especially after a full night of rest!",
        avatar: "A"
      }
    ]
  },
  autocleanup: {
    heroTitle: "Auto Cleanup applies to all your dictations",
    heroDesc: "Choose the level of cleanup that's automatically applied every time, across all apps.",
    appIcons: `<span class="app-icon-pill">✨ None</span><span class="app-icon-pill">✨ Light</span><span class="app-icon-pill">✨ Medium</span>`,
    cards: [
      {
        id: "cleanup_none",
        name: "None",
        subtitle: "Transcribes exactly what you said, including mistakes",
        sample: "hey joey, we still on for coffee? I think we maybe should leave earlier to make it there in time there might um traffic. What are you thinking?",
        avatar: "V"
      },
      {
        id: "cleanup_light",
        name: "Light",
        subtitle: "Cleans up filler words and grammar",
        sample: "Hey Joey, are we still on for coffee? I think we should leave earlier to make it there in time. There might be traffic. What are you thinking?",
        avatar: "V"
      },
      {
        id: "cleanup_medium",
        name: "Medium",
        subtitle: "Edits for clarity and conciseness",
        sample: "Hey Joey, are we still on for coffee? We should leave earlier; there might be traffic. What do you think?",
        avatar: "V"
      }
    ]
  }
};

let currentStyleCategory = "personal";
let selectedStyles = {
  personal: "personal_very_casual",
  work: "work_casual",
  email: "email_formal",
  other: "other_formal",
  autocleanup: "cleanup_light"
};

document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  loadHistory();
  loadInsights();
  loadDictionary();
  loadSavedApiKeys();
  loadStyleSettings();
  renderStyleCategory("personal");
  startFloatingBarStartupSequence();

  // Real-time auto-refresh polling every 3 seconds
  setInterval(() => {
    loadHistory();
    loadInsights();
  }, 3000);
});

async function loadStyleSettings() {
  try {
    const res = await fetch("/api/styles/get");
    const data = await res.json();
    if (data) {
      selectedStyles = { ...selectedStyles, ...data };
      renderStyleCategory(currentStyleCategory);
    }
  } catch (err) {
    console.error("Error loading style settings:", err);
  }
}

// Load persistent API keys from SQLite storage on startup
async function loadSavedApiKeys() {
  try {
    const res = await fetch("/api/apikeys/list");
    const keysMap = await res.json();
    if (!keysMap) return;

    for (const [provider, keyVal] of Object.entries(keysMap)) {
      const inputEl = document.getElementById(`key-input-${provider}`);
      const badgeContainer = document.getElementById(`status-badge-${provider}`);
      if (inputEl && keyVal) {
        inputEl.value = keyVal;
        if (badgeContainer) {
          badgeContainer.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
        }
      }
    }
  } catch (err) {
    console.error("Error loading saved API keys:", err);
  }
}

// Startup sequence for Wispr Flow Bar Marker
function startFloatingBarStartupSequence() {
  const barText = document.getElementById("flow-bar-text");
  const barDot = document.getElementById("flow-bar-status-dot");
  if (!barText || !barDot) return;

  let countdown = 10;
  barText.textContent = `Starting... ${countdown}s`;
  barDot.className = "pill-indicator-dot";

  const timer = setInterval(() => {
    countdown--;
    if (countdown > 0) {
      barText.textContent = `Starting... ${countdown}s`;
    } else {
      clearInterval(timer);
      barText.textContent = "";
      barDot.className = "pill-indicator-dot ready";
    }
  }, 1000);

  // Wispr Flow hover interaction — show "Click to speak" ONLY on cursor hover
  const bar = document.getElementById("floating-flow-bar");
  if (bar) {
    bar.addEventListener("mouseenter", () => {
      if (!isHandsFreeRecording) {
        barText.textContent = "Click to speak";
        barDot.className = "pill-indicator-dot ready";
      }
    });
    bar.addEventListener("mouseleave", () => {
      if (!isHandsFreeRecording) {
        barText.textContent = "";
        barDot.className = "pill-indicator-dot ready";
      }
    });
  }
}

// Click Floating Bar to Toggle Hands-Free Recording Mode Automatically!
function toggleHandsFreeRecording() {
  const bar = document.getElementById("floating-flow-bar");
  const barText = document.getElementById("flow-bar-text");
  const barDot = document.getElementById("flow-bar-status-dot");
  if (!bar) return;

  isHandsFreeRecording = !isHandsFreeRecording;

  // Notify backend to start/stop recording
  fetch("/api/record/toggle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recording: isHandsFreeRecording }),
  }).catch(err => console.error("Error toggling recording:", err));

  if (isHandsFreeRecording) {
    bar.classList.add("recording-active");
    if (barDot) barDot.className = "pill-indicator-dot recording";
    if (barText) barText.textContent = "🎙️ Dictating... Click to stop";
  } else {
    bar.classList.remove("recording-active");
    if (barDot) barDot.className = "pill-indicator-dot ready";
    if (barText) barText.textContent = "";
    loadHistory();
    loadInsights();
  }
}

// Live Voice Model API Key Testing with Green Checkmarks & Exact Error Badges
async function testVoiceModel(providerKey) {
  const keyInput = document.getElementById(`key-input-${providerKey}`);
  const modelSelect = document.getElementById(`model-select-${providerKey}`);
  const badgeContainer = document.getElementById(`status-badge-${providerKey}`);

  if (!keyInput || !badgeContainer) return;
  const keyVal = keyInput.value.trim();

  if (!keyVal) {
    badgeContainer.innerHTML = `<span class="status-badge status-error">✕ Key is empty</span>`;
    return;
  }

  badgeContainer.innerHTML = `<span class="status-badge" style="background:#f3f4f6; color:#4b5563;">Testing...</span>`;

  try {
    const selectedModel = modelSelect ? modelSelect.value : "";
    const res = await fetch("/api/apikeys/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerKey, key: keyVal, model: selectedModel }),
    });

    const data = await res.json();
    if (data.success) {
      badgeContainer.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
    } else {
      badgeContainer.innerHTML = `<span class="status-badge status-error" title="${escapeHtml(data.error)}">✕ ${escapeHtml(data.error)}</span>`;
    }

  } catch (err) {
    badgeContainer.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message)}</span>`;
  }
}

// System Toggle for Floating Flow Bar Visibility
function toggleFlowBarVisibility(isVisible) {
  const bar = document.getElementById("floating-flow-bar");
  if (bar) {
    if (isVisible) {
      bar.classList.remove("hidden-bar");
    } else {
      bar.classList.add("hidden-bar");
    }
  }
}

function toggleSystemSetting(settingKey, isChecked) {
  console.log(`System setting [${settingKey}] updated to:`, isChecked);
  fetch("/api/settings/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: settingKey, value: isChecked }),
  }).catch(err => console.error("Error saving setting:", err));
}

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
    if (pageId === "style") renderStyleCategory(currentStyleCategory);
    if (pageId === "providers") loadProvidersOverview();
    if (pageId === "audioflow") loadAudioFlowPage();
    if (pageId === "videoflow") {
      if (typeof loadVideoFlow === "function") loadVideoFlow();
      else if (typeof loadVideoCatalog === "function") loadVideoCatalog();
    }
  }
}

// Style Page Category Switcher
function switchStyleTab(categoryKey, el) {
  currentStyleCategory = categoryKey;
  document.querySelectorAll("#style-tabs-nav .tab-btn").forEach(btn => btn.classList.remove("active"));
  if (el) el.classList.add("active");
  renderStyleCategory(categoryKey);
}

function renderStyleCategory(categoryKey) {
  const data = STYLE_DATA[categoryKey];
  if (!data) return;

  // Render Hero Banner
  document.getElementById("style-hero-title").textContent = data.heroTitle;
  document.getElementById("style-hero-desc").textContent = data.heroDesc;
  document.getElementById("style-hero-icons").innerHTML = data.appIcons;

  // Render 3 Cards
  const grid = document.getElementById("style-cards-grid");
  if (!grid) return;

  const currentSelectedId = selectedStyles[categoryKey];

  grid.innerHTML = data.cards.map(card => {
    const isSelected = card.id === currentSelectedId;
    return `
      <div class="style-card ${isSelected ? 'selected active-preset-card' : ''}" onclick="selectStyleCard('${categoryKey}', '${card.id}')">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <div>
            <div class="style-card-name">${escapeHtml(card.name)}</div>
            <div class="style-card-subtitle">${escapeHtml(card.subtitle)}</div>
          </div>
          ${isSelected ? `<span class="selected-preset-badge">✓ Selected</span>` : `<span class="select-preset-action">Select</span>`}
        </div>
        <div class="sample-chat-bubble">${escapeHtml(card.sample)}</div>
        <div class="sample-avatar" style="margin-top: 12px;">
          <div class="avatar-circle">${card.avatar}</div>
          <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Active Preset Pattern</span>
        </div>
      </div>
    `;
  }).join("");
}

async function selectStyleCard(categoryKey, cardId) {
  selectedStyles[categoryKey] = cardId;
  renderStyleCategory(categoryKey);
  try {
    await fetch("/api/styles/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: categoryKey, style_id: cardId }),
    });
  } catch (err) {
    console.error("Error saving style selection:", err);
  }
}

// VizProFlow Perfect Keys Sub-Modals (Shortcuts & Microphone)
function openShortcutDialog() {
  const modal = document.getElementById("shortcuts-sub-modal");
  if (modal) modal.classList.remove("hidden");
}

function openMicrophoneDialog() {
  const modal = document.getElementById("mic-sub-modal");
  if (modal) {
    modal.classList.remove("hidden");
    loadHardwareMicrophones();
  }
}

function closeSubModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("hidden");
}

function selectShortcutMode(modeName, el) {
  if (el) {
    document.querySelectorAll("#shortcuts-sub-modal .shortcut-option-card").forEach(card => card.classList.remove("active-option"));
    el.classList.add("active-option");
  }
}

function changePushToTalkKey() {
  const newKey = prompt("Enter new Push to Talk hotkey combination:", "Ctrl+Win");
  if (newKey && newKey.trim()) {
    document.getElementById("ptt-current-kbd").textContent = newKey.trim();
    document.getElementById("ptt-display-kbd").textContent = newKey.trim();
    fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "push_to_talk_shortcut", value: newKey.trim() }),
    }).catch(err => console.error("Error saving shortcut:", err));
  }
}

// Dynamic Hardware Audio Input Detection & Hardware Routing
async function loadHardwareMicrophones() {
  const container = document.getElementById("mic-devices-list");
  if (!container) return;

  try {
    const res = await fetch("/api/microphones");
    const mics = await res.json();

    if (!mics || mics.length === 0) {
      mics.push({ index: 0, name: "Headset (Max Pro)" });
    }

    container.innerHTML = mics.map((mic, i) => {
      const isFirst = i === 0;
      return `
        <div class="mic-option-card ${isFirst ? 'selected-mic' : ''}" onclick="selectMicrophoneDevice('${escapeJs(mic.name)}', ${mic.index}, this)">
          <div style="font-size: 14px; font-weight: 700; color: var(--text-main);">${escapeHtml(mic.name)}</div>
          ${isFirst ? `
            <div class="audio-signal-bars">
              <span class="bar active"></span><span class="bar active"></span><span class="bar active"></span><span class="bar active"></span><span class="bar active"></span>
            </div>
          ` : ''}
        </div>
      `;
    }).join("");

    document.getElementById("current-mic-desc").textContent = mics[0].name;

  } catch (err) {
    console.error("Error detecting hardware microphones:", err);
  }
}

async function selectMicrophoneDevice(micName, micIndex, el) {
  const desc = document.getElementById("current-mic-desc");
  if (desc) desc.textContent = micName;
  if (el) {
    document.querySelectorAll("#mic-devices-list .mic-option-card").forEach(c => c.classList.remove("selected-mic"));
    el.classList.add("selected-mic");
  }

  try {
    await fetch("/api/microphones/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: micName, index: micIndex }),
    });
  } catch (err) {
    console.error("Error setting active microphone:", err);
  }

  closeSubModal('mic-sub-modal');
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
    } else {
      // Re-filter with current search term so live data updates are visible
      filterHistory();
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
  const resolver = new Date(Date.now() - 86400000).toISOString().split("T")[0];
  if (dateStr === resolver) return "YESTERDAY";
  return dateStr.toUpperCase();
}

// Time Range Filter State
let currentInsightsRange = "all";

function switchInsightsRange(rangeKey, el) {
  currentInsightsRange = rangeKey;
  document.querySelectorAll(".insights-range-switcher .range-btn").forEach(btn => btn.classList.remove("active"));
  if (el) el.classList.add("active");
  loadInsights();
}

// Fetch and render Insights & Metrics from SQLite Database
async function loadInsights() {
  try {
    const res = await fetch(`/api/insights?range=${currentInsightsRange}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const totalWords = data.total_words || 0;
    const avgWpm = data.avg_wpm || 0;
    const streak = data.streak || 0;
    const dictationCount = data.dictation_count || 0;

    // Home Banner Metrics
    const totalWordsFormatted = totalWords >= 1000 ? (totalWords / 1000).toFixed(1) + "K" : totalWords;
    if (document.getElementById("stat-total-words")) document.getElementById("stat-total-words").textContent = totalWordsFormatted;
    if (document.getElementById("stat-wpm")) document.getElementById("stat-wpm").textContent = avgWpm;
    if (document.getElementById("stat-streak")) document.getElementById("stat-streak").textContent = streak;

    // Insights Page Top Metrics
    const insightsWpm = document.getElementById("insights-wpm");
    if (insightsWpm) insightsWpm.textContent = avgWpm;

    const insightsTotalWords = document.getElementById("insights-total-words");
    if (insightsTotalWords) insightsTotalWords.textContent = totalWords.toLocaleString();

    // Time Saved & Multiplier
    const savedHours = data.time_saved_hours !== undefined ? data.time_saved_hours : 0;
    const savedMinutes = data.time_saved_minutes !== undefined ? data.time_saved_minutes : 0;
    const speedMult = data.speed_multiplier !== undefined ? data.speed_multiplier : (avgWpm > 0 ? Number((avgWpm / 40.0).toFixed(1)) : 1.0);
    const aiFixesTotal = data.ai_refinements !== undefined ? data.ai_refinements : (data.words_corrected || 0);
    const wordFixes = data.words_corrected !== undefined ? data.words_corrected : 0;
    const dictFixes = data.dictionary_fixes !== undefined ? data.dictionary_fixes : 0;

    const timeSavedEl = document.getElementById("insights-time-saved");
    const timeSavedUnit = document.getElementById("insights-time-saved-unit");
    if (timeSavedEl && timeSavedUnit) {
      if (savedHours >= 1) {
        timeSavedEl.textContent = savedHours;
        timeSavedUnit.textContent = "hrs";
      } else {
        timeSavedEl.textContent = Math.round(savedMinutes);
        timeSavedUnit.textContent = "mins";
      }
    }

    const multiplierEl = document.getElementById("insights-multiplier");
    if (multiplierEl) multiplierEl.textContent = `${speedMult}x Faster`;

    // Fixes calculation
    if (document.getElementById("insights-fixes-total")) document.getElementById("insights-fixes-total").textContent = aiFixesTotal;
    if (document.getElementById("insights-words-corrected")) document.getElementById("insights-words-corrected").textContent = wordFixes;
    if (document.getElementById("insights-dict-fixes")) document.getElementById("insights-dict-fixes").textContent = dictFixes;

    // Streak & Total Dictations
    if (document.getElementById("insights-longest-streak")) document.getElementById("insights-longest-streak").textContent = streak;
    if (document.getElementById("insights-streak-title")) document.getElementById("insights-streak-title").textContent = `${streak} day streak`;
    if (document.getElementById("insights-dictation-count")) document.getElementById("insights-dictation-count").textContent = dictationCount;

    // Gauge Update
    updateSpeedGauge(avgWpm);

    // Desktop Application Breakdown
    const usageContainer = document.getElementById("insights-app-breakdown");
    if (usageContainer) {
      if (!data.app_breakdown || data.app_breakdown.length === 0) {
        usageContainer.innerHTML = `
          <div style="font-size: 13px; color: var(--text-muted); padding: 24px 0; text-align: center;">
            <div style="font-size: 24px; margin-bottom: 6px;">⚡</div>
            <strong>No application dictations recorded yet</strong>
            <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">Hold Middle Mouse button or Ctrl+Win to dictate in VS Code, Chrome, Slack, or Notion!</div>
          </div>
        `;
      } else {
        const totalDictations = data.app_breakdown.reduce((acc, a) => acc + a.count, 0) || 1;
        usageContainer.innerHTML = data.app_breakdown.map(app => {
          const pct = app.percentage !== undefined ? app.percentage : Math.round((app.count / totalDictations) * 100);
          const icon = getAppIcon(app.app_name);
          const catClass = (app.category || "other").toLowerCase().replace(/[^a-z]/g, "");
          return `
            <div class="usage-item" style="margin-bottom: 14px;">
              <div class="usage-label" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px;">
                <span style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 16px;">${icon}</span>
                  <strong style="color: var(--text-main);">${escapeHtml(app.app_name)}</strong>
                  <span class="app-cat-pill ${catClass}">${escapeHtml(app.category || 'General')}</span>
                </span>
                <span style="font-weight: 600; color: var(--text-muted);">${pct}% <span style="font-size: 11px; opacity: 0.7;">(${app.total_words || 0} words)</span></span>
              </div>
              <div class="progress-bar-bg" style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                <div class="progress-bar-fill" style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, var(--primary-orange), #ff8833); border-radius: 3px; transition: width 0.8s ease;"></div>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    // Render 28-Day Heatmap
    renderHeatmap(data.daily_activity || []);

    // Render Time-of-Day Distribution
    renderTimeOfDayBars(data.time_of_day || []);

    // Voice Profile Archetype
    const vp = data.voice_profile || {};
    if (document.getElementById("insights-archetype-badge")) {
      document.getElementById("insights-archetype-badge").textContent = vp.archetype || (totalWords > 0 ? "The Rapid Thinker" : "Getting Started");
    }
    if (document.getElementById("insights-archetype-desc")) {
      document.getElementById("insights-archetype-desc").textContent = vp.archetype_desc || "Captures raw thoughts, code syntax, and communications at peak throughput.";
    }
    if (document.getElementById("insights-archetype-tag")) {
      document.getElementById("insights-archetype-tag").textContent = vp.archetype_tag || "General Flow";
    }
    if (document.getElementById("insights-archetype-icon")) {
      document.getElementById("insights-archetype-icon").textContent = vp.archetype_icon || "⚡";
    }
    if (document.getElementById("insights-vocab-status")) {
      document.getElementById("insights-vocab-status").textContent = vp.vocabulary_unlocked ? "Unlocked (Active)" : "Active (Learning)";
    }
    if (document.getElementById("insights-peak-hours")) {
      document.getElementById("insights-peak-hours").textContent = vp.peak_hours || "Morning";
    }
    if (document.getElementById("insights-peak-hours-tag")) {
      document.getElementById("insights-peak-hours-tag").textContent = `⚡ Peak: ${vp.peak_hours || 'Active throughout day'}`;
    }

    // Share Card Snippet Preview
    const previewEl = document.getElementById("share-snippet-preview");
    if (previewEl) {
      const timeStr = savedHours >= 1 ? `${savedHours} hrs` : `${Math.round(savedMinutes)} mins`;
      previewEl.textContent = `🚀 I dictated ${totalWords.toLocaleString()} words at ${avgWpm} WPM and saved ${timeStr} with Voice Flow (${speedMult}x faster than typing)! #VoiceFlow`;
    }

  } catch (err) {
    console.error("Error loading insights:", err);
  }
}

function updateSpeedGauge(wpm) {
  const gaugeFill = document.getElementById("gauge-fill");
  const gaugeNeedle = document.getElementById("gauge-needle");
  const badge = document.getElementById("insights-speed-badge");
  if (!gaugeFill) return;

  const maxWpm = 180;
  const clampedWpm = Math.min(Math.max(wpm, 0), maxWpm);
  const totalArcLength = 141.37;
  const pct = clampedWpm / maxWpm;
  const dashOffset = totalArcLength - (totalArcLength * pct);

  gaugeFill.style.strokeDashoffset = dashOffset;
  gaugeFill.style.filter = `drop-shadow(0 0 ${4 + pct * 10}px var(--accent-glow))`;

  if (gaugeNeedle) {
    const rotation = -90 + (180 * pct);
    gaugeNeedle.style.transform = `rotate(${rotation}deg)`;
  }

  if (badge) {
    if (clampedWpm >= 140) {
      badge.textContent = "Top 0.5% Ultra Speed 🏆";
      badge.style.color = "#ff6b00";
    } else if (clampedWpm >= 100) {
      badge.textContent = "Top 5% Rapid 🚀";
      badge.style.color = "#ff8833";
    } else if (clampedWpm >= 60) {
      badge.textContent = "Fast Conversational ⚡";
      badge.style.color = "#10B981";
    } else if (clampedWpm > 0) {
      badge.textContent = "Active Speed";
      badge.style.color = "var(--text-main)";
    } else {
      badge.textContent = "Ready to record";
      badge.style.color = "var(--text-muted)";
    }
  }
}

function renderHeatmap(dailyActivityData) {
  const grid = document.getElementById("heatmap-grid");
  if (!grid) return;

  const activityList = Array.isArray(dailyActivityData) ? dailyActivityData : [];

  let html = `
    <div class="heatmap-wrapper">
      <div class="day-labels">
        <span>Mon</span>
        <span>Wed</span>
        <span>Fri</span>
      </div>
      <div class="heatmap-grid">
  `;

  let miniHeatmapHtml = "";

  for (let i = 27; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split("T")[0];
    const formattedDate = d.toLocaleDateString("en-US", { month: "short", day: "numeric", weekday: "short" });

    const match = activityList.find(a => a.date === dateStr);
    const wordCount = match ? match.words : 0;
    const level = match ? (match.level !== undefined ? match.level : 0) : (wordCount > 500 ? 4 : (wordCount > 250 ? 3 : (wordCount > 100 ? 2 : (wordCount > 0 ? 1 : 0))));
    const savedMins = Math.round((wordCount / 140) * 0.7);

    html += `
      <div class="heatmap-cell level-${level}" style="animation-delay: ${i * 10}ms;">
        <div class="heatmap-tooltip-popup">
          <div style="font-weight: 800; color: var(--primary-orange);">${formattedDate}</div>
          <div><strong>${wordCount.toLocaleString()}</strong> words dictated</div>
          <div style="opacity: 0.8; font-size: 10px; margin-top: 2px;">⚡ Level ${level} • ~${savedMins}m saved</div>
        </div>
      </div>
    `;

    miniHeatmapHtml += `<span class="heatmap-cell level-${level}" style="width:7px;height:7px;border-radius:2px;display:inline-block;"></span>`;
  }

  html += `
      </div>
    </div>
  `;

  grid.innerHTML = html;

  const miniGrid = document.getElementById("share-card-mini-heatmap");
  if (miniGrid) {
    miniGrid.innerHTML = miniHeatmapHtml;
  }
}

function renderTimeOfDayBars(timeOfDayList) {
  const container = document.getElementById("time-of-day-bars");
  if (!container) return;

  const periods = Array.isArray(timeOfDayList) && timeOfDayList.length > 0 ? timeOfDayList : [
    { period: "morning", label: "Morning", time_range: "6 AM - 12 PM", icon: "🌅", words: 0, pct: 25 },
    { period: "afternoon", label: "Afternoon", time_range: "12 PM - 5 PM", icon: "☀️", words: 0, pct: 25 },
    { period: "evening", label: "Evening", time_range: "5 PM - 10 PM", icon: "🌆", words: 0, pct: 25 },
    { period: "night", label: "Night", time_range: "10 PM - 6 AM", icon: "🌙", words: 0, pct: 25 },
  ];

  container.innerHTML = periods.map(p => `
    <div class="tod-bar-item">
      <div class="tod-bar-header">
        <span>${p.icon} <strong>${escapeHtml(p.label)}</strong></span>
        <span>${p.words || 0} w</span>
      </div>
      <div class="tod-bar-bg">
        <div class="tod-bar-fill" style="width: ${Math.max(p.pct || 0, 3)}%;"></div>
      </div>
      <div style="font-size: 10px; color: var(--text-muted); opacity: 0.7;">${escapeHtml(p.time_range)}</div>
    </div>
  `).join("");
}

// Share Productivity Card Handler with inline feedback
function copyProductivityShareCard(btnElement = null) {
  const wordsVal = document.getElementById("insights-total-words") ? document.getElementById("insights-total-words").textContent : "0";
  const timeVal = document.getElementById("insights-time-saved") ? document.getElementById("insights-time-saved").textContent : "0";
  const unitVal = document.getElementById("insights-time-saved-unit") ? document.getElementById("insights-time-saved-unit").textContent : "mins";
  const wpmVal = document.getElementById("insights-wpm") ? document.getElementById("insights-wpm").textContent : "0";
  const multVal = document.getElementById("insights-multiplier") ? document.getElementById("insights-multiplier").textContent : "3x Faster";
  const archVal = document.getElementById("insights-archetype-badge") ? document.getElementById("insights-archetype-badge").textContent : "The Rapid Thinker";

  const shareText = `🚀 Voice Flow Telemetry (${archVal}): I dictated ${wordsVal} words at ${wpmVal} WPM and saved ${timeVal} ${unitVal} with Voice Flow (${multVal} than typing)! #VoiceFlow #AI`;
  
  navigator.clipboard.writeText(shareText).then(() => {
    if (btnElement) {
      const originalHtml = btnElement.innerHTML;
      btnElement.innerHTML = "<span>✅ Copied to Clipboard!</span>";
      btnElement.style.background = "#10B981";
      setTimeout(() => {
        btnElement.innerHTML = originalHtml;
        btnElement.style.background = "";
      }, 2000);
    }
    showToast("Copied Productivity Card to clipboard!", "🚀");
  }).catch(err => {
    console.error("Failed to copy share card:", err);
  });
}

function getAppIcon(appName) {
  const name = (appName || "").toLowerCase();
  if (name.includes("chatgpt") || name.includes("gpt")) return "🧠";
  if (name.includes("claude")) return "🤖";
  if (name.includes("chrome") || name.includes("edge") || name.includes("brave") || name.includes("firefox")) return "🌐";
  if (name.includes("whatsapp") || name.includes("telegram")) return "💬";
  if (name.includes("outlook") || name.includes("gmail") || name.includes("mail")) return "✉️";
  if (name.includes("slack") || name.includes("teams") || name.includes("discord")) return "💼";
  if (name.includes("notion") || name.includes("word") || name.includes("docs") || name.includes("obsidian")) return "📄";
  if (name.includes("terminal") || name.includes("code") || name.includes("powershell") || name.includes("cursor")) return "💻";
  return "⚡";
}

// Dictionary Management (Wispr Flow Gold Standard)
let allDictionaryWords = [];
let activeDictCategory = "all";

async function loadDictionary() {
  const chipContainer = document.getElementById("dictionary-chips");
  if (!chipContainer) return;

  try {
    const res = await fetch("/api/dictionary");
    allDictionaryWords = await res.json();

    const counterBadge = document.getElementById("dict-counter-badge");
    if (counterBadge) counterBadge.textContent = `${allDictionaryWords.length} Term${allDictionaryWords.length === 1 ? '' : 's'}`;

    renderDictionaryFilteredChips();
  } catch (err) {
    console.error("Error loading dictionary:", err);
  }
}

function filterDictionaryChips() {
  renderDictionaryFilteredChips();
}

function filterDictionaryCategory(cat, el) {
  activeDictCategory = cat;
  document.querySelectorAll(".dict-tags-nav .dict-tag-btn").forEach(btn => btn.classList.remove("active"));
  if (el) el.classList.add("active");
  renderDictionaryFilteredChips();
}

function getWordCategoryTag(word) {
  const w = word.trim();
  if (w.includes("->") || w.includes("=>")) return "snippets";
  if (w.toUpperCase() === w && w.length <= 6) return "acronyms";
  if (w.includes(" ") || /^[A-Z][a-z]+ [A-Z][a-z]+/.test(w)) return "names";
  if (["api", "graphql", "sql", "json", "python", "typescript", "react", "whisper", "voiceflow", "vpn", "http", "pro-con"].some(k => w.toLowerCase().includes(k))) return "technical";
  return "brands";
}

function renderDictionaryFilteredChips() {
  const chipContainer = document.getElementById("dictionary-chips");
  if (!chipContainer) return;

  const queryEl = document.getElementById("dictionary-search-input");
  const query = queryEl ? queryEl.value.toLowerCase().trim() : "";

  let filtered = allDictionaryWords;

  if (query) {
    filtered = filtered.filter(w => w.toLowerCase().includes(query));
  }

  if (activeDictCategory !== "all") {
    filtered = filtered.filter(w => getWordCategoryTag(w) === activeDictCategory);
  }

  if (!filtered || filtered.length === 0) {
    chipContainer.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 40px 20px; text-align: center; color: var(--text-muted);">
        <div style="font-size: 32px; margin-bottom: 8px;">📖</div>
        <div style="font-weight: 700; font-size: 15px; color: var(--text-main);">No terms match your search</div>
        <div style="font-size: 12px; margin-top: 4px;">Type a term or snippet above (e.g. "myemail -> me@company.com") and click "+ Add Word".</div>
      </div>
    `;
    return;
  }

  chipContainer.innerHTML = filtered.map(w => {
    const catTag = getWordCategoryTag(w);
    let icon = "⚡";
    if (catTag === "snippets") icon = "🚀";
    if (catTag === "technical") icon = "💻";
    if (catTag === "names") icon = "👤";
    if (catTag === "brands") icon = "🏢";

    return `
      <span class="chip-item">
        <span style="opacity: 0.65; margin-right: 4px; font-size: 11px;">${icon}</span>
        <span class="chip-term-text">${escapeHtml(w)}</span>
        <span onclick="removeDictionaryWord('${escapeJs(w)}')" class="chip-delete-btn" title="Remove term">✕</span>
      </span>
    `;
  }).join("");
}

async function addDictionaryWordFromInput() {
  const inputEl = document.getElementById("dictionary-add-input");
  if (!inputEl) return;
  const word = inputEl.value.trim();
  if (!word) return;

  try {
    const res = await fetch("/api/dictionary/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showToast(data.error || "Failed to add dictionary term.", "⚠️");
      return;
    }
    inputEl.value = "";
    showToast("Dictionary term added.", "✅");
    loadDictionary();
  } catch (err) {
    console.error("Error adding dictionary word:", err);
    showToast("Network error adding term.", "⚠️");
  }
}

async function addDictionaryWord() {
  addDictionaryWordFromInput();
}

async function removeDictionaryWord(word) {
  try {
    const res = await fetch("/api/dictionary/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showToast(data.error || "Failed to remove dictionary term.", "⚠️");
      return;
    }
    showToast("Dictionary term removed.", "✅");
    loadDictionary();
  } catch (err) {
    console.error("Error removing dictionary word:", err);
    showToast("Network error removing term.", "⚠️");
  }
}

// Theme switching (Light cream / Dark matte black)
function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("vf-theme", next); } catch (e) {}
  const icon = document.getElementById("theme-toggle-icon");
  const label = document.getElementById("theme-toggle-label");
  if (icon) icon.textContent = next === "dark" ? "🌙" : "☀️";
  if (label) label.textContent = next === "dark" ? "Dark Mode" : "Light Mode";
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  applyTheme(current === "dark" ? "light" : "dark");
}

applyTheme(document.documentElement.getAttribute("data-theme") || "light");

// Settings Modal Controls
function openSettings(tab = "general") {
  const modal = document.getElementById("settings-modal");
  if (modal) {
    modal.classList.remove("hidden");
    switchSettingsTab(tab);
  }
}

async function closeSettings() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.add("hidden");
}

function switchSettingsTab(tabId, el = null) {
  ["general", "system"].forEach(t => {
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
  return str.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\r/g, "\\r").replace(/\n/g, "\\n").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

let _vfToastTimer = null;
function showToast(message, icon) {
  let el = document.getElementById("vf-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "vf-toast";
    el.className = "vf-toast";
    document.body.appendChild(el);
  }
  el.textContent = (icon ? icon + " " : "") + message;
  if (icon === "⚠️") {
    el.classList.add("error");
    el.style.backgroundColor = "#a92323";
  } else {
    el.classList.remove("error");
    el.style.backgroundColor = "";
  }
  el.classList.add("show");
  clearTimeout(_vfToastTimer);
  _vfToastTimer = setTimeout(() => {
    el.classList.remove("show");
  }, 2400);
}

// =========================================================
// AI PROVIDERS & MULTI-KEY CONNECTION MANAGER CONTROLLER
// =========================================================

const ALL_PROVIDERS_CONFIG = {
  gemini: { name: "Google Gemini", logo: "✨", keyLink: "https://aistudio.google.com/app/apikey" },
  groq: { name: "Groq Audio", logo: "⚡", keyLink: "https://console.groq.com/keys" },
  elevenlabs: { name: "ElevenLabs Voice", logo: "🎙️", keyLink: "https://elevenlabs.io/app/settings/api-keys" },
  deepgram: { name: "Deepgram Speech", logo: "🎧", keyLink: "https://console.deepgram.com/" },
  openai: { name: "OpenAI Voice", logo: "🤖", keyLink: "https://platform.openai.com/api-keys" },
  assemblyai: { name: "AssemblyAI", logo: "🗣️", keyLink: "https://www.assemblyai.com/app/account" },
  huggingface: { name: "Hugging Face", logo: "🤗", keyLink: "https://huggingface.co/settings/tokens" },
  cloudflare: { name: "Cloudflare AI", logo: "☁️", keyLink: "https://dash.cloudflare.com/profile/api-tokens" },
  together: { name: "Together AI", logo: "🤝", keyLink: "https://api.together.ai/settings/api-keys" },
  replicate: { name: "Replicate Voice", logo: "🚀", keyLink: "https://replicate.com/account/api-tokens" }
};

let currentSelectedProvider = null;
let currentProviderData = null;

async function loadProvidersOverview() {
  const container = document.getElementById("providers-grid-container");
  if (!container) return;

  document.getElementById("providers-view-overview").style.display = "block";
  document.getElementById("providers-view-detail").style.display = "none";

  try {
    const res = await fetch("/api/providers/overview");
    const data = await res.json();
    const allConns = data.connections || {};

    container.innerHTML = Object.entries(ALL_PROVIDERS_CONFIG).map(([pid, cfg]) => {
      const conns = allConns[pid] || [];
      const activeConns = conns.filter(c => c.is_active);
      const isConnected = activeConns.length > 0;
      const connCountText = isConnected ? `${activeConns.length} Connected` : "No connections";

      return `
        <div class="provider-card-item" onclick="openProviderDetail('${pid}')">
          <div class="provider-card-left">
            <div class="provider-card-logo">${cfg.logo}</div>
            <div class="provider-card-info">
              <span class="provider-card-name">${escapeHtml(cfg.name)}</span>
              <span class="provider-card-status">
                <span class="status-dot-indicator ${isConnected ? 'connected' : ''}"></span>
                ${connCountText}
              </span>
            </div>
          </div>
          <label class="toggle-switch" onclick="event.stopPropagation()">
            <input type="checkbox" ${isConnected ? 'checked' : ''} onchange="toggleProviderMaster('${pid}', this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
      `;
    }).join("");

    loadExecVoiceFlowPolicy();

  } catch (err) {
    console.error("Error loading providers overview:", err);
  }
}

async function loadExecVoiceFlowPolicy() {
  const selectEl = document.getElementById("exec-policy-model-select");
  if (!selectEl) return;

  try {
    const res = await fetch("/api/policy/get");
    const data = await res.json();
    if (!data.success || !data.policy) return;

    const policy = data.policy;
    const activeModel = policy.active_model || "gemini/gemini-2.5-flash";
    const models = policy.models || [];

    if (models.length === 0) {
      selectEl.innerHTML = `<option value="gemini/gemini-2.5-flash">[Google] Gemini 2.5 Flash (Default)</option>`;
    } else {
      selectEl.innerHTML = models.map(m => `
        <option value="${m.full_id}" ${m.full_id === activeModel ? 'selected' : ''}>
          ${escapeHtml(m.label)}
        </option>
      `).join("");
    }

    const engineEl = document.getElementById("exec-policy-active-engine");
    if (engineEl) {
      const activeObj = models.find(m => m.full_id === activeModel);
      engineEl.textContent = activeObj ? activeObj.label : activeModel;
    }
  } catch (err) {
    console.error("Error loading Exec Voice Flow Policy:", err);
  }
}

async function updateExecVoiceFlowPolicy(modelVal) {
  if (!modelVal) return;
  try {
    const res = await fetch("/api/policy/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelVal }),
    });
    const data = await res.json();
    if (data.success) {
      loadExecVoiceFlowPolicy();
    }
  } catch (err) {
    console.error("Error updating Exec Voice Flow Policy:", err);
  }
}

function filterProvidersList() {
  const q = (document.getElementById("provider-search")?.value || "").toLowerCase();
  document.querySelectorAll(".provider-card-item").forEach(card => {
    const name = card.querySelector(".provider-card-name")?.textContent?.toLowerCase() || "";
    card.style.display = name.includes(q) ? "flex" : "none";
  });
}

async function openProviderDetail(providerId) {
  currentSelectedProvider = providerId;
  const cfg = ALL_PROVIDERS_CONFIG[providerId] || { name: providerId, logo: "🔌", keyLink: "#" };

  document.getElementById("providers-view-overview").style.display = "none";
  document.getElementById("providers-view-detail").style.display = "block";

  document.getElementById("detail-provider-name").textContent = cfg.name;
  document.getElementById("detail-provider-logo").textContent = cfg.logo;
  document.getElementById("detail-get-key-link").href = cfg.keyLink;

  loadProviderDetails(providerId);
}

function closeProviderDetail() {
  currentSelectedProvider = null;
  loadProvidersOverview();
}

async function loadProviderDetails(providerId) {
  try {
    const res = await fetch(`/api/providers/details?provider=${providerId}`);
    const data = await res.json();
    currentProviderData = data;

    const conns = data.connections || [];
    document.getElementById("detail-conn-count").textContent = `${conns.length} connection${conns.length === 1 ? '' : 's'}`;
    const modeSelect = document.getElementById("load-balance-mode-select");
    if (modeSelect) modeSelect.value = data.mode || "priority";

    const connListEl = document.getElementById("detail-connections-list");
    if (connListEl) {
      if (conns.length === 0) {
        connListEl.innerHTML = `
          <div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; border: 1px dashed var(--border-color); border-radius: 8px;">
            No connection keys configured yet. Click <strong>+ Add Connection</strong> above to add your first API key for multi-key failover.
          </div>
        `;
      } else {
        connListEl.innerHTML = conns.map(c => `
          <div class="connection-item-card">
            <div class="conn-left-info">
              <input type="checkbox" ${c.is_active ? 'checked' : ''} onchange="toggleProviderConn(${c.id}, this.checked)">
              <div>
                <div class="conn-name-group">
                  <span class="conn-name">${escapeHtml(c.name)}</span>
                  ${c.is_active ? '<span class="active-pill-badge">+ active</span>' : ''}
                  <span class="priority-pill-badge">Priority #${c.priority}</span>
                </div>
                <div class="conn-key-preview">Key: ${escapeHtml(c.api_key.substring(0, 6))}...${escapeHtml(c.api_key.substring(c.api_key.length - 4))}</div>
                <div class="conn-status-msg ${c.last_tested_status.includes('Connected') ? 'ok' : 'err'}">${escapeHtml(c.last_tested_status)}</div>
              </div>
            </div>
            <div class="conn-actions-right">
              <button class="btn-secondary" style="padding: 4px 10px; font-size: 11px;" onclick="testSingleConn(${c.id}, '${escapeJs(c.api_key)}')">⚡ Test Key</button>
              <button class="btn-secondary" style="padding: 4px 10px; font-size: 11px; color: #ef4444;" onclick="deleteConn(${c.id})">Delete</button>
            </div>
          </div>
        `).join("");
      }
    }

    const models = data.models || [];
    const modelsGridEl = document.getElementById("detail-models-grid");
    if (modelsGridEl) {
      modelsGridEl.innerHTML = models.map(m => `
        <div class="model-card-item">
          <div>
            <div class="model-id-text">${escapeHtml(m.model_id)}</div>
            <div class="model-display-name">${escapeHtml(m.display_name)}</div>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" ${m.is_active ? 'checked' : ''} onchange="toggleModelActive(${m.id}, this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
      `).join("");
    }

  } catch (err) {
    console.error("Error loading provider details:", err);
  }
}

async function changeLoadBalanceMode(mode) {
  if (!currentSelectedProvider) return;
  try {
    await fetch("/api/providers/mode/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider, mode }),
    });
  } catch (err) {
    console.error("Error saving mode:", err);
  }
}

function openAddConnectionModal() {
  document.getElementById("conn-input-name").value = `${(ALL_PROVIDERS_CONFIG[currentSelectedProvider]?.name || "Key")} Key`;
  document.getElementById("conn-input-key").value = "";
  document.getElementById("conn-input-priority").value = (currentProviderData?.connections?.length || 0) + 1;
  document.getElementById("conn-check-badge").innerHTML = "";

  const modal = document.getElementById("modal-add-connection");
  if (modal) modal.classList.remove("hidden");
}

async function testNewConnectionKey() {
  const keyVal = document.getElementById("conn-input-key").value.trim();
  const badgeContainer = document.getElementById("conn-check-badge");
  if (!keyVal || !badgeContainer) return;

  badgeContainer.innerHTML = `<span class="status-badge" style="background:#f3f4f6; color:#4b5563;">Testing key...</span>`;
  try {
    const res = await fetch("/api/providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider, key: keyVal }),
    });
    const data = await res.json();
    if (data.success) {
      badgeContainer.innerHTML = `<span class="status-badge status-connected">✓ Valid & Verified!</span>`;
    } else {
      badgeContainer.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(data.error)}</span>`;
    }
  } catch (err) {
    badgeContainer.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message)}</span>`;
  }
}

async function saveConnectionModal() {
  const name = document.getElementById("conn-input-name").value.trim();
  const key = document.getElementById("conn-input-key").value.trim();
  const priority = parseInt(document.getElementById("conn-input-priority").value) || 1;

  if (!key) {
    alert("Please enter a valid API Key.");
    return;
  }

  try {
    const res = await fetch("/api/providers/connections/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider, name, key, priority }),
    });
    const data = await res.json();
    if (data.success) {
      closeSubModal("modal-add-connection");
      loadProviderDetails(currentSelectedProvider);
    } else {
      alert("Error adding connection: " + data.error);
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function toggleProviderConn(cid, isActive) {
  try {
    await fetch("/api/providers/connections/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, is_active: isActive }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error toggling connection:", err);
  }
}

async function deleteConn(cid) {
  if (!confirm("Are you sure you want to delete this connection key?")) return;
  try {
    await fetch("/api/providers/connections/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error deleting connection:", err);
  }
}

async function testSingleConn(cid, key) {
  try {
    const res = await fetch("/api/providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: currentSelectedProvider, key }),
    });
    const data = await res.json();
    alert(data.success ? "✓ Connection test successful! Status: 200 OK" : "✕ Test failed: " + data.error);
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function testCurrentProviderConnections() {
  if (!currentProviderData || !currentProviderData.connections) return;
  for (const c of currentProviderData.connections) {
    await testSingleConn(c.id, c.api_key);
  }
}

function openAddModelModal() {
  document.getElementById("model-input-id").value = "";
  document.getElementById("model-input-name").value = "";
  const modal = document.getElementById("modal-add-model");
  if (modal) modal.classList.remove("hidden");
}

async function saveCustomModelModal() {
  const modelId = document.getElementById("model-input-id").value.trim();
  const name = document.getElementById("model-input-name").value.trim();
  if (!modelId) {
    alert("Please enter a model ID.");
    return;
  }
  try {
    await fetch("/api/providers/models/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider, model_id: modelId, display_name: name || modelId }),
    });
    closeSubModal("modal-add-model");
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function toggleModelActive(mid, isActive) {
  try {
    await fetch("/api/providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, is_active: isActive }),
    });
  } catch (err) {
    console.error("Error toggling model:", err);
  }
}

function toggleAllModels(isActive) {
  if (!currentProviderData || !currentProviderData.models) return;
  currentProviderData.models.forEach(m => toggleModelActive(m.id, isActive));
  loadProviderDetails(currentSelectedProvider);
}

async function testAllProviders() {
  alert("Testing all configured provider connections...");
  const res = await fetch("/api/providers/overview");
  const data = await res.json();
  const allConns = data.connections || {};
  for (const [pid, list] of Object.entries(allConns)) {
    for (const c of list) {
      await fetch("/api/providers/connections/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: c.id, provider: pid, key: c.api_key }),
      });
    }
  }
  loadProvidersOverview();
}

// =========================================================
// AUDIO FLOW (TTS) — PROVIDER & POLICY CONTROLLER
// =========================================================

const AUDIO_PROVIDERS_CONFIG = {
  edge: { name: "Microsoft Edge Neural", logo: "✨", keyLink: null, free: true },
  offline: { name: "Windows Offline SAPI5", logo: "💻", keyLink: null, free: true },
  google: { name: "Google Cloud TTS", logo: "☁️", keyLink: "https://console.cloud.google.com/apis/credentials" },
  gemini: { name: "Gemini AI TTS", logo: "💎", keyLink: "https://aistudio.google.com/apikey" },
  azure: { name: "Microsoft Azure Speech", logo: "🔷", keyLink: "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices" },
  fish: { name: "Fish Audio", logo: "🐟", keyLink: "https://fish.audio/api" },
  nvidia: { name: "NVIDIA Riva", logo: "🟢", keyLink: "https://build.nvidia.com" },
  elevenlabs: { name: "ElevenLabs", logo: "🎙️", keyLink: "https://elevenlabs.io/api" },
  deepgram: { name: "Deepgram Aura", logo: "🎧", keyLink: "https://console.deepgram.com" },
  openai: { name: "OpenAI TTS", logo: "🤖", keyLink: "https://platform.openai.com/api-keys" }
};

let currentAudioProvider = null;

function loadAudioFlowPage() {
  loadAudioProvidersOverview();
  loadExecAudioFlowPolicy();
}

async function loadExecAudioFlowPolicy() {
  const selectEl = document.getElementById("exec-audio-policy-model-select");
  if (!selectEl) return;

  try {
    const res = await fetch("/api/audio-policy/get");
    const data = await res.json();
    if (!data.success || !data.policy) return;

    const policy = data.policy;
    const activeModel = policy.active_model || "edge/en-US-AvaNeural";
    const models = policy.models || [];
    const grouped = policy.grouped_models || [];

    if (models.length === 0) {
      selectEl.innerHTML = `<option value="edge/en-US-AvaNeural">✨ Microsoft Edge Neural — Ava (Calm Female)</option>`;
    } else if (grouped.length > 0) {
      selectEl.innerHTML = grouped.map(g => `
        <optgroup label="${escapeHtml(`${g.provider_logo} ${g.provider_name}`)}">
          ${g.models.map(m => {
            const specIcons = (m.has_vision ? "👁️ " : "") + (m.has_brain ? "🧠" : "");
            return `
              <option value="${m.full_id}" ${m.full_id === activeModel ? "selected" : ""}>
                ${escapeHtml(m.display_name || m.label)} ${specIcons}
              </option>
            `;
          }).join("")}
        </optgroup>
      `).join("");
    } else {
      selectEl.innerHTML = models.map(m => `
        <option value="${m.full_id}" ${m.full_id === activeModel ? "selected" : ""}>
          ${escapeHtml(m.label)}
        </option>
      `).join("");
    }

    const engineEl = document.getElementById("exec-audio-active-engine");
    const specialtyEl = document.getElementById("exec-audio-model-specialty");
    if (engineEl) {
      const activeObj = models.find(m => m.full_id === activeModel);
      engineEl.textContent = activeObj ? activeObj.display_name : activeModel.split("/").pop();
      if (specialtyEl && activeObj) {
        let tags = [];
        if (activeObj.has_vision) tags.push("👁️ Vision");
        if (activeObj.has_brain) tags.push("🧠 Brain");
        specialtyEl.innerHTML = tags.map(t => `<span style="display:inline-flex;align-items:center;gap:4px;">${t}</span>`).join(" ");
      }
    }

    const failEl = document.getElementById("exec-audio-failover-count");
    if (failEl) {
      const count = policy.failover_count || 0;
      failEl.textContent = count > 0
        ? `${count} connected provider${count === 1 ? "" : "s"} + Edge fallback`
        : "Edge Free Engine";
    }

    const toggle = document.getElementById("toggle-audio-flow");
    if (toggle) toggle.checked = policy.audio_flow_enabled !== false;
    updateAudioFlowStatusBadge(policy.audio_flow_enabled !== false);

    const speed = parseFloat(policy.audio_flow_speed);
    if (!isNaN(speed)) {
      document.querySelectorAll(".speed-pill-btn").forEach(btn => {
        btn.classList.toggle("active", parseFloat(btn.dataset.speed) === speed);
      });
    }
  } catch (err) {
    console.error("Error loading Audio Flow policy:", err);
  }
}

function updateAudioFlowStatusBadge(enabled) {
  const badge = document.getElementById("exec-audio-status-badge");
  if (!badge) return;
  badge.textContent = enabled ? "● Audio Flow Active" : "○ Audio Flow Off";
  badge.classList.toggle("off", !enabled);
  badge.removeAttribute("style");
}

async function updateExecAudioFlowPolicy(modelVal) {
  if (!modelVal) return;
  try {
    await fetch("/api/audio-policy/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelVal }),
    });
    loadExecAudioFlowPolicy();
  } catch (err) {
    console.error("Error updating Audio Flow policy:", err);
  }
}

async function toggleAudioFlowSetting(checked) {
  try {
    await fetch("/api/audio-policy/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !!checked }),
    });
    updateAudioFlowStatusBadge(!!checked);
  } catch (err) {
    console.error("Error toggling Audio Flow:", err);
  }
}

async function setAudioFlowSpeed(x) {
  const speed = parseFloat(x);
  if (isNaN(speed)) return;
  try {
    await fetch("/api/audio-policy/speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed }),
    });
    document.querySelectorAll(".speed-pill-btn").forEach(btn => {
      btn.classList.toggle("active", parseFloat(btn.dataset.speed) === speed);
    });
  } catch (err) {
    console.error("Error setting Audio Flow speed:", err);
  }
}

async function loadAudioProvidersOverview() {
  const container = document.getElementById("audio-providers-grid-container");
  const overview = document.getElementById("audio-providers-view-overview");
  const detail = document.getElementById("audio-providers-view-detail");
  if (!container) return;
  if (overview) overview.style.display = "block";
  if (detail) detail.style.display = "none";

  try {
    const res = await fetch("/api/audio-providers/overview");
    const data = await res.json();
    if (!Array.isArray(data)) {
      container.innerHTML = `<div class="audio-empty-state">${escapeHtml(data.error || "Failed to load providers")}</div>`;
      return;
    }

    const freeProviders = [
      { id: "edge", name: "Microsoft Edge Neural", logo: "✨", key_link: null },
      { id: "offline", name: "Windows Offline SAPI5", logo: "💻", key_link: null },
    ].map(p => ({ ...p, connection_count: 1, is_connected: true }));

    const allProviders = [...freeProviders, ...data];

    container.innerHTML = allProviders.map(p => {
      const cfg = AUDIO_PROVIDERS_CONFIG[p.id] || {};
      const isFree = !!cfg.free;
      const connText = p.is_connected
        ? `${p.connection_count || 1} Connected`
        : "Not connected";
      return `
        <div class="provider-card-item audio-provider-card" onclick="openAudioProviderDetail('${p.id}')">
          <div class="provider-card-left">
            <div class="provider-card-logo audio-card-logo">${p.logo}</div>
            <div class="provider-card-info">
              <span class="provider-card-name" title="${escapeHtml(cfg.name || p.name)}">${escapeHtml(cfg.name || p.name)}</span>
              <span class="provider-card-status">
                <span class="status-dot-indicator ${p.is_connected ? "connected" : ""}"></span>
                ${isFree ? "Free Engine — Always available" : connText}
              </span>
            </div>
          </div>
          <label class="toggle-switch" onclick="event.stopPropagation()">
            <input type="checkbox" ${p.is_connected ? "checked" : ""} onchange="toggleAudioProviderMaster('${p.id}', this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading audio providers overview:", err);
    container.innerHTML = `<div class="audio-empty-state">Failed to load providers — is the Voice Flow backend running?</div>`;
  }
}

async function openAudioProviderDetail(providerId) {
  currentAudioProvider = providerId;
  const cfg = AUDIO_PROVIDERS_CONFIG[providerId] || { name: providerId, logo: "🔊", keyLink: null };

  document.getElementById("audio-providers-view-overview").style.display = "none";
  document.getElementById("audio-providers-view-detail").style.display = "block";

  document.getElementById("audio-detail-provider-name").textContent = cfg.name;
  document.getElementById("audio-detail-provider-logo").textContent = cfg.logo;
  const keyLink = document.getElementById("audio-detail-get-key-link");
  if (keyLink) {
    keyLink.style.display = cfg.keyLink ? "inline-flex" : "none";
    if (cfg.keyLink) keyLink.href = cfg.keyLink;
  }
  loadAudioProviderDetails(providerId);
}

function closeAudioProviderDetail() {
  currentAudioProvider = null;
  loadAudioProvidersOverview();
}

async function loadAudioProviderDetails(providerId) {
  try {
    const res = await fetch(`/api/audio-providers/details?provider=${providerId}`);
    const data = await res.json();
    if (!data || data.error) return;

    const conns = data.connections || [];
    const connCountEl = document.getElementById("audio-detail-conn-count");
    if (connCountEl) {
      connCountEl.textContent = `${conns.length} connection${conns.length === 1 ? "" : "s"}`;
    }

    const connListEl = document.getElementById("audio-detail-connections-list");
    if (connListEl) {
      if (conns.length === 0) {
        connListEl.innerHTML = `
          <div class="audio-empty-state">
            <div class="audio-empty-icon">🎙️</div>
            <p><strong>No API keys configured yet.</strong></p>
            <p class="audio-empty-sub">Add your first key to unlock ${escapeHtml((AUDIO_PROVIDERS_CONFIG[providerId] || {}).name || providerId)} voices.</p>
            <button class="btn-primary" style="margin-top: 12px; padding: 8px 18px; font-size: 12px;" onclick="openAddAudioConnectionModal()">+ Add API Key</button>
          </div>`;
      } else {
        connListEl.innerHTML = conns.map(c => {
          const keyRaw = c.api_key || "";
          const keyPreview = keyRaw.length > 10 ? `${keyRaw.substring(0, 6)}...${keyRaw.substring(keyRaw.length - 4)}` : "Key saved";
          const statusOk = String(c.last_tested_status || "").includes("Connected");
          const validClass = c.is_valid === 0 || c.is_valid === false ? "err" : (statusOk ? "ok" : "neutral");
          return `
          <div class="connection-item-card audio-conn-item ${c.is_active ? "" : "audio-conn-inactive"}">
            <div class="conn-left-info">
              <input type="checkbox" ${c.is_active ? "checked" : ""} onchange="toggleAudioProviderConn(${c.id}, this.checked)">
              <div>
                <div class="conn-name-group">
                  <span class="conn-name">${escapeHtml(c.name)}</span>
                  ${c.is_active ? '<span class="active-pill-badge audio-active-badge">+ active</span>' : '<span class="active-pill-badge audio-muted-badge">off</span>'}
                  <span class="priority-pill-badge audio-priority-badge">Priority #${c.priority}</span>
                </div>
                <div class="conn-key-preview">Key: ${escapeHtml(keyPreview)}</div>
                <div class="conn-status-msg ${validClass}">${escapeHtml(c.last_tested_status || "Not Tested")}</div>
              </div>
            </div>
            <div class="conn-actions-right">
              <button class="btn-secondary audio-action-btn" onclick="testSingleAudioConn(${c.id}, '${escapeJs(keyRaw)}')">⚡ Test</button>
              <button class="btn-secondary audio-action-btn audio-delete-btn" onclick="deleteAudioConn(${c.id})">Delete</button>
            </div>
          </div>`;
        }).join("");
      }
    }

    const models = data.models || [];
    const modelsGridEl = document.getElementById("audio-detail-models-grid");
    if (modelsGridEl) {
      modelsGridEl.innerHTML = models.length > 0
        ? models.map(m => `
          <div class="model-card-item audio-model-card">
            <div>
              <div class="model-id-text">${escapeHtml(m.model_id)}</div>
              <div class="model-display-name">${escapeHtml(m.display_name)}</div>
            </div>
            <label class="toggle-switch">
              <input type="checkbox" ${m.is_active ? "checked" : ""} onchange="toggleAudioTtsModel(${m.id}, this.checked)">
              <span class="toggle-slider"></span>
            </label>
          </div>`).join("")
        : `<div class="audio-empty-state">No voices available for this provider yet.</div>`;
    }
  } catch (err) {
    console.error("Error loading audio provider details:", err);
  }
}

async function toggleAudioProviderConn(cid, isActive) {
  try {
    await fetch("/api/audio-providers/connections/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, is_active: isActive }),
    });
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error toggling audio connection:", err);
  }
}

async function deleteAudioConn(cid) {
  if (!confirm("Delete this API key connection?")) return;
  try {
    await fetch("/api/audio-providers/connections/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid }),
    });
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
    loadExecAudioFlowPolicy();
  } catch (err) {
    console.error("Error deleting audio connection:", err);
  }
}

async function toggleAudioProviderMaster(providerId, isActive) {
  try {
    await fetch("/api/audio-providers/master/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId, is_active: isActive }),
    });
    loadExecAudioFlowPolicy();
  } catch (err) {
    console.error("Error toggling audio provider master:", err);
  }
}

async function toggleAudioTtsModel(mid, isActive) {
  try {
    await fetch("/api/audio-providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, is_active: isActive }),
    });
  } catch (err) {
    console.error("Error toggling TTS model:", err);
  }
}

async function testAllAudioProviders() {
  try {
    const res = await fetch("/api/audio-providers/overview");
    const data = await res.json();
    if (!Array.isArray(data)) return;
    const providers = data.filter(p => p.is_connected);
    for (const p of providers) {
      const detRes = await fetch(`/api/audio-providers/details?provider=${p.id}`);
      const det = await detRes.json();
      for (const c of det.connections || []) {
        await testSingleAudioConn(c.id, c.api_key, p.id);
      }
    }
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error testing all audio providers:", err);
  }
}

async function testAudioProviderConnections() {
  if (!currentAudioProvider) return;
  const res = await fetch(`/api/audio-providers/details?provider=${currentAudioProvider}`);
  const det = await res.json();
  for (const c of det.connections || []) {
    await testSingleAudioConn(c.id, c.api_key, currentAudioProvider);
  }
}

async function testSingleAudioConn(cid, key, provider) {
  const prov = provider || currentAudioProvider || "";
  try {
    const res = await fetch("/api/audio-providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: prov, key: key || "" }),
    });
    const data = await res.json();
    if (prov === currentAudioProvider) loadAudioProviderDetails(prov);
    return data;
  } catch (err) {
    console.error("Error testing audio connection:", err);
    return { valid: false, status: err.message };
  }
}

function openAddAudioConnectionModal() {
  const modal = document.getElementById("modal-add-audio-connection");
  if (!modal) return;

  const nameInput = document.getElementById("audio-conn-input-name");
  const keyInput = document.getElementById("audio-conn-input-key");
  const priorityInput = document.getElementById("audio-conn-input-priority");
  const badge = document.getElementById("audio-conn-check-badge");
  if (nameInput) nameInput.value = "";
  if (keyInput) keyInput.value = "";
  if (priorityInput) priorityInput.value = "1";
  if (badge) badge.innerHTML = "";

  const cfg = AUDIO_PROVIDERS_CONFIG[currentAudioProvider] || {};
  const title = document.getElementById("modal-audio-conn-title");
  if (title) title.textContent = `Add ${cfg.name || "TTS"} API Key`;

  const hint = document.getElementById("audio-conn-provider-hint");
  if (hint) {
    if (cfg.keyLink) {
      hint.innerHTML = `Get your key from <a href="${cfg.keyLink}" target="_blank" class="get-key-pill-link">${escapeHtml(cfg.name || "provider")} →</a>`;
      hint.style.display = "block";
    } else {
      hint.style.display = "none";
    }
  }

  modal.classList.remove("hidden");
}

async function testNewAudioConnectionKey() {
  const key = document.getElementById("audio-conn-input-key").value.trim();
  const badge = document.getElementById("audio-conn-check-badge");
  if (!badge) return;
  if (!key) {
    badge.innerHTML = `<span class="status-badge status-error">✕ Key is empty</span>`;
    return;
  }
  badge.innerHTML = `<span class="status-badge" style="background:#f3f4f6; color:#4b5563;">Testing...</span>`;
  try {
    const res = await fetch("/api/audio-providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentAudioProvider || "", key }),
    });
    const data = await res.json();
    if (data.valid) {
      badge.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
    } else {
      badge.innerHTML = `<span class="status-badge status-error" title="${escapeHtml(data.status || "")}">✕ ${escapeHtml(data.status || "Invalid key")}</span>`;
    }
  } catch (err) {
    badge.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message)}</span>`;
  }
}

async function saveAudioConnectionModal() {
  const name = document.getElementById("audio-conn-input-name").value.trim();
  const key = document.getElementById("audio-conn-input-key").value.trim();
  const priority = parseInt(document.getElementById("audio-conn-input-priority").value, 10) || 1;
  if (!key) {
    alert("Please paste an API key first.");
    return;
  }
  try {
    const res = await fetch("/api/audio-providers/connections/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: currentAudioProvider || "",
        name: name || "Key #1",
        key,
        priority,
      }),
    });
    const data = await res.json();
    closeSubModal("modal-add-audio-connection");
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
    loadExecAudioFlowPolicy();
    loadAudioProvidersOverview();
    if (data.verification && data.verification.valid === false) {
      alert("Key saved, but validation failed: " + (data.verification.status || "Unknown error"));
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}



function downloadProductivityCardImage(btnElement = null) {
  const wordsVal = document.getElementById("insights-total-words") ? document.getElementById("insights-total-words").textContent : "75,195";
  const timeVal = document.getElementById("insights-time-saved") ? document.getElementById("insights-time-saved").textContent : "22.7";
  const unitVal = document.getElementById("insights-time-saved-unit") ? document.getElementById("insights-time-saved-unit").textContent : "hrs";
  const wpmVal = document.getElementById("insights-wpm") ? document.getElementById("insights-wpm").textContent : "145";
  const multVal = document.getElementById("insights-multiplier") ? document.getElementById("insights-multiplier").textContent : "3.6x";

  const canvas = document.createElement("canvas");
  canvas.width = 600;
  canvas.height = 320;
  const ctx = canvas.getContext("2d");

  // Background Gradient
  const grad = ctx.createLinearGradient(0, 0, 600, 320);
  grad.addColorStop(0, "#0f172a");
  grad.addColorStop(0.5, "#1e293b");
  grad.addColorStop(1, "#0b0f19");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 600, 320);

  // Border & Glow
  ctx.strokeStyle = "#ff6020";
  ctx.lineWidth = 3;
  ctx.strokeRect(10, 10, 580, 300);

  // Header Title
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 22px Inter, sans-serif";
  ctx.fillText("🎙️ Voice Flow Productivity Card", 30, 48);

  // Badge
  ctx.fillStyle = "#ff6020";
  ctx.font = "bold 13px Inter, sans-serif";
  ctx.fillText("PRODUCTIVITY ELITE • THE HIGH-VELOCITY ORATOR", 30, 80);

  // Divider
  ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(30, 95);
  ctx.lineTo(570, 95);
  ctx.stroke();

  // Metrics Grid
  ctx.fillStyle = "#94a3b8";
  ctx.font = "12px Inter, sans-serif";
  ctx.fillText("DICTATED WORDS", 30, 125);
  ctx.fillText("SPEAKING SPEED", 180, 125);
  ctx.fillText("TIME SAVED", 330, 125);
  ctx.fillText("VELOCITY MULTIPLIER", 460, 125);

  ctx.fillStyle = "#ff6020";
  ctx.font = "bold 24px Inter, sans-serif";
  ctx.fillText(wordsVal, 30, 160);
  ctx.fillText(wpmVal + " WPM", 180, 160);
  ctx.fillText(timeVal + " " + unitVal, 330, 160);
  ctx.fillText(multVal, 460, 160);

  // Footer Tagline
  ctx.fillStyle = "#cbd5e1";
  ctx.font = "italic 13px Inter, sans-serif";
  ctx.fillText("⚡ Verified by Voice Flow Speech Telemetry • #VoiceFlow", 30, 215);

  // Heatmap Mini Indicator Text
  ctx.fillStyle = "#64748b";
  ctx.font = "11px Inter, sans-serif";
  ctx.fillText("28-DAY CONSISTENCY MATRIX ACTIVE", 30, 275);

  // Convert Canvas to Image Download
  const link = document.createElement("a");
  link.download = "VoiceFlow-Productivity-Card.png";
  link.href = canvas.toDataURL("image/png");
  link.click();

  if (btnElement) {
    showToast("Downloaded Share Productivity Card!", "📥");
  }
}
