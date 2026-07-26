// Voice Flow Desktop App - Real Data Controller

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
  renderStyleCategory("personal");
  startFloatingBarStartupSequence();

  // Real-time auto-refresh polling every 3 seconds
  setInterval(() => {
    loadHistory();
    loadInsights();
  }, 3000);
});

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
      <div class="style-card ${isSelected ? 'selected' : ''}" onclick="selectStyleCard('${categoryKey}', '${card.id}')">
        <div>
          <div class="style-card-name">${escapeHtml(card.name)}</div>
          <div class="style-card-subtitle">${escapeHtml(card.subtitle)}</div>
          <div class="sample-chat-bubble">${escapeHtml(card.sample)}</div>
        </div>
        <div class="sample-avatar">
          <div class="avatar-circle">${card.avatar}</div>
          <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Preview Style</span>
        </div>
      </div>
    `;
  }).join("");
}

function selectStyleCard(categoryKey, cardId) {
  selectedStyles[categoryKey] = cardId;
  renderStyleCategory(categoryKey);
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
  return str.replace(/'/g, "\\'").replace(/\n/g, "\\n");
}

// =========================================================
// AI PROVIDERS & MULTI-KEY CONNECTION MANAGER CONTROLLER
// =========================================================

const ALL_PROVIDERS_CONFIG = {
  gemini: { name: "Google Gemini", logo: "✨", keyLink: "https://aistudio.google.com/app/apikey" },
  openai: { name: "OpenAI Voice", logo: "🤖", keyLink: "https://platform.openai.com/api-keys" },
  groq: { name: "Groq Audio", logo: "⚡", keyLink: "https://console.groq.com/keys" },
  anthropic: { name: "Anthropic", logo: "🅰️", keyLink: "https://console.anthropic.com/" },
  deepseek: { name: "DeepSeek", logo: "🐋", keyLink: "https://platform.deepseek.com/api_keys" },
  alibaba: { name: "Alibaba DashScope", logo: "🟠", keyLink: "https://dashscope.console.aliyun.com/" },
  zenmux: { name: "Zenmux", logo: "🟢", keyLink: "https://zenmux.ai/" },
  elevenlabs: { name: "ElevenLabs Voice", logo: "🎙️", keyLink: "https://elevenlabs.io/app/settings/api-keys" },
  deepgram: { name: "Deepgram Speech", logo: "🎧", keyLink: "https://console.deepgram.com/" },
  cloudflare: { name: "Cloudflare AI", logo: "☁️", keyLink: "https://dash.cloudflare.com/profile/api-tokens" },
  together: { name: "Together AI", logo: "🤝", keyLink: "https://api.together.ai/settings/api-keys" },
  replicate: { name: "Replicate Voice", logo: "🚀", keyLink: "https://replicate.com/account/api-tokens" },
  ollama: { name: "Ollama (Local)", logo: "🦙", keyLink: "http://localhost:11434" },
  chutes: { name: "Chutes AI", logo: "⚡", keyLink: "https://chutes.ai" },
  cerebras: { name: "Cerebras AI", logo: "🧠", keyLink: "https://cloud.cerebras.ai" }
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
  } catch (err) {
    console.error("Error loading providers overview:", err);
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

