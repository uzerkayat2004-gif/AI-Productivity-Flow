// Voice Flow Desktop App - Real Data Controller
if (typeof history !== "undefined" && "scrollRestoration" in history) {
  try { history.scrollRestoration = "manual"; } catch (_) {}
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

let allHistoryRecords = [];
let lastHistoryHash = "";
let isHandsFreeRecording = false;

/**
 * =============================================================================
 * UNIVERSAL CUSTOM CONFIRMATION & ALERT DIALOG (10/10 REPLACEMENT FOR BROWSER POPUPS)
 * =============================================================================
 */
const _nativeAlert = typeof window !== "undefined" && window.alert ? window.alert.bind(window) : null;
const _nativeConfirm = typeof window !== "undefined" && window.confirm ? window.confirm.bind(window) : null;
let _activeModalResolve = null;

function vfConfirm(optionsOrMessage) {
  return new Promise((resolve) => {
    _activeModalResolve = resolve;

    let opts = {};
    if (typeof optionsOrMessage === "string") {
      const msg = optionsOrMessage;
      const lower = msg.toLowerCase();
      
      if (lower.includes("restart")) {
        opts = {
          title: "Restart Application",
          badge: "System Action",
          icon: "🔄",
          message: msg,
          confirmText: "Restart App",
          cancelText: "Cancel",
          type: "restart",
        };
      } else if (lower.includes("cache") || lower.includes("clear audio")) {
        opts = {
          title: "Clear Audio Cache",
          badge: "Disk Cleanup",
          icon: "🧹",
          message: msg,
          confirmText: "Clear Cache",
          cancelText: "Cancel",
          type: "warning",
        };
      } else if (lower.includes("sign out") || lower.includes("logout")) {
        opts = {
          title: "Sign Out",
          badge: "Account Session",
          icon: "🚪",
          message: msg,
          confirmText: "Sign Out",
          cancelText: "Cancel",
          type: "signout",
        };
      } else if (lower.includes("delete") || lower.includes("cannot be undone")) {
        opts = {
          title: "Confirm Deletion",
          badge: "Irreversible Action",
          icon: "🗑️",
          message: msg,
          confirmText: "Delete",
          cancelText: "Cancel",
          type: "danger",
        };
      } else {
        opts = {
          title: "Confirm Action",
          badge: "Action Required",
          icon: "⚠️",
          message: msg,
          confirmText: "Confirm",
          cancelText: "Cancel",
          type: "warning",
        };
      }
    } else if (typeof optionsOrMessage === "object" && optionsOrMessage !== null) {
      opts = {
        title: optionsOrMessage.title || "Confirmation",
        badge: optionsOrMessage.badge || "Action Required",
        icon: optionsOrMessage.icon || "⚠️",
        message: optionsOrMessage.message || "",
        confirmText: optionsOrMessage.confirmText || "Confirm",
        cancelText: optionsOrMessage.cancelText || "Cancel",
        type: optionsOrMessage.type || "warning",
      };
    }

    const modal = document.getElementById("vf-universal-modal");
    if (!modal) {
      return resolve(_nativeConfirm ? _nativeConfirm(opts.message || "") : true);
    }

    const card = document.getElementById("vf-modal-card");
    const iconEl = document.getElementById("vf-modal-icon");
    const titleEl = document.getElementById("vf-modal-title");
    const badgeEl = document.getElementById("vf-modal-badge-pill");
    const messageEl = document.getElementById("vf-modal-message");
    const confirmBtn = document.getElementById("vf-modal-btn-confirm");
    const confirmTextEl = document.getElementById("vf-modal-confirm-text");
    const cancelBtn = document.getElementById("vf-modal-btn-cancel");

    card.className = "vf-modal-card vf-modal-type-" + (opts.type || "warning");

    if (iconEl) iconEl.textContent = opts.icon;
    if (titleEl) titleEl.textContent = opts.title;
    if (badgeEl) badgeEl.textContent = opts.badge;
    if (messageEl) messageEl.textContent = opts.message;
    if (confirmTextEl) confirmTextEl.textContent = opts.confirmText;
    if (cancelBtn) {
      cancelBtn.style.display = "inline-flex";
      cancelBtn.textContent = opts.cancelText || "Cancel";
    }

    modal.style.display = "flex";
    void modal.offsetWidth;
    modal.classList.add("vf-modal-open");

    setTimeout(() => {
      if (confirmBtn) confirmBtn.focus();
    }, 50);
  });
}

function vfAlert(optionsOrMessage) {
  return new Promise((resolve) => {
    _activeModalResolve = () => resolve(true);

    let opts = {};
    if (typeof optionsOrMessage === "string") {
      const msg = optionsOrMessage;
      const lower = msg.toLowerCase();
      if (lower.includes("error") || lower.includes("fail")) {
        opts = {
          title: "Notice",
          badge: "Error",
          icon: "✕",
          message: msg,
          confirmText: "Got It",
          type: "danger",
        };
      } else if (lower.includes("copied") || lower.includes("successful") || lower.includes("✓")) {
        opts = {
          title: "Success",
          badge: "Completed",
          icon: "✓",
          message: msg,
          confirmText: "OK",
          type: "info",
        };
      } else {
        opts = {
          title: "Notice",
          badge: "Information",
          icon: "ℹ️",
          message: msg,
          confirmText: "OK",
          type: "info",
        };
      }
    } else if (typeof optionsOrMessage === "object" && optionsOrMessage !== null) {
      opts = {
        title: optionsOrMessage.title || "Notice",
        badge: optionsOrMessage.badge || "Information",
        icon: optionsOrMessage.icon || "ℹ️",
        message: optionsOrMessage.message || "",
        confirmText: optionsOrMessage.confirmText || "OK",
        type: optionsOrMessage.type || "info",
      };
    }

    const modal = document.getElementById("vf-universal-modal");
    if (!modal) {
      if (_nativeAlert) _nativeAlert(opts.message || "");
      return resolve(true);
    }

    const card = document.getElementById("vf-modal-card");
    const iconEl = document.getElementById("vf-modal-icon");
    const titleEl = document.getElementById("vf-modal-title");
    const badgeEl = document.getElementById("vf-modal-badge-pill");
    const messageEl = document.getElementById("vf-modal-message");
    const confirmBtn = document.getElementById("vf-modal-btn-confirm");
    const confirmTextEl = document.getElementById("vf-modal-confirm-text");
    const cancelBtn = document.getElementById("vf-modal-btn-cancel");

    card.className = "vf-modal-card vf-modal-type-" + (opts.type || "info");

    if (iconEl) iconEl.textContent = opts.icon;
    if (titleEl) titleEl.textContent = opts.title;
    if (badgeEl) badgeEl.textContent = opts.badge;
    if (messageEl) messageEl.textContent = opts.message;
    if (confirmTextEl) confirmTextEl.textContent = opts.confirmText;
    if (cancelBtn) cancelBtn.style.display = "none";

    modal.style.display = "flex";
    void modal.offsetWidth;
    modal.classList.add("vf-modal-open");

    setTimeout(() => {
      if (confirmBtn) confirmBtn.focus();
    }, 50);
  });
}

function _closeUniversalModal(confirmed) {
  const modal = document.getElementById("vf-universal-modal");
  if (!modal) return;
  modal.classList.remove("vf-modal-open");
  setTimeout(() => {
    modal.style.display = "none";
  }, 220);

  if (_activeModalResolve) {
    const fn = _activeModalResolve;
    _activeModalResolve = null;
    fn(Boolean(confirmed));
  }
}

window.vfConfirm = vfConfirm;
window.vfAlert = vfAlert;

// Globally intercept window.alert so zero native browser popups (127.0.0.1:8991 says ...) can ever show
if (typeof window !== "undefined") {
  window.alert = function(msg) {
    if (typeof vfToast === "function" && typeof msg === "string" && (msg.toLowerCase().includes("copied") || msg.startsWith("✓"))) {
      vfToast(msg);
      return;
    }
    vfAlert(msg);
  };
}

// Global modal event listener initialization
document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("vf-universal-modal");
  const confirmBtn = document.getElementById("vf-modal-btn-confirm");
  const cancelBtn = document.getElementById("vf-modal-btn-cancel");
  const closeX = document.getElementById("vf-modal-close-x");

  if (confirmBtn) confirmBtn.addEventListener("click", () => _closeUniversalModal(true));
  if (cancelBtn) cancelBtn.addEventListener("click", () => _closeUniversalModal(false));
  if (closeX) closeX.addEventListener("click", () => _closeUniversalModal(false));

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) _closeUniversalModal(false);
    });
  }

  window.addEventListener("keydown", (e) => {
    if (!modal || modal.style.display === "none" || !modal.classList.contains("vf-modal-open")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      _closeUniversalModal(false);
    } else if (e.key === "Enter" && document.activeElement !== cancelBtn) {
      e.preventDefault();
      e.stopPropagation();
      _closeUniversalModal(true);
    }
  }, true);
});

// Style Configuration & Scenarios
const STYLE_DATA = {
  personal: {
    heroTitle: "This style applies in personal messengers",
    heroDesc: "Style formatting applies instantly across personal desktop messaging apps.",
    appIcons: `<span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg> WhatsApp</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg> Telegram</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="12" x2="10" y2="12"></line><line x1="8" y1="10" x2="8" y2="14"></line><line x1="15" y1="13" x2="15.01" y2="13"></line><line x1="18" y1="11" x2="18.01" y2="11"></line><rect x="2" y="6" width="20" height="12" rx="2"></rect></svg> Discord</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg> Instagram</span>`,
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
    appIcons: `<span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg> Slack</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg> Teams</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg> LinkedIn</span>`,
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
    appIcons: `<span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg> Outlook</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg> Gmail</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg> Windows Mail</span>`,
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
  developer: {
    heroTitle: "This style applies in developer tools",
    heroDesc: "Style formatting applies in VS Code, Cursor, terminals, GitHub, and technical workspaces.",
    appIcons: `<span class="app-icon-pill">⌨️ VS Code</span><span class="app-icon-pill">✨ Cursor</span><span class="app-icon-pill">▸_ Terminal</span><span class="app-icon-pill">◈ GitHub</span>`,
    cards: [
      {
        id: "developer_formal",
        name: "Formal.",
        subtitle: "Protected code tokens",
        sample: "Please execute `npm run build` and verify that the API endpoint returns valid JSON.",
        avatar: "D"
      },
      {
        id: "developer_casual",
        name: "Casual",
        subtitle: "Conversational dev notes",
        sample: "Check the PR on GitHub and run tests with pytest before deploying to staging",
        avatar: "D"
      },
      {
        id: "developer_very_casual",
        name: "very casual",
        subtitle: "Lowercase dev notes",
        sample: "run git pull and check if the HTTP status code is 200 on localhost",
        avatar: "D"
      },
      {
        id: "developer_excited",
        name: "Excited!",
        subtitle: "Enthusiastic dev praise",
        sample: "All 46 unit tests passed with 0 errors! Great job shipping v2.1!",
        avatar: "D"
      }
    ]
  },
  other: {
    heroTitle: "This style applies in all other apps",
    heroDesc: "Style formatting applies across Notion, Word, Google Docs, and ChatGPT.",
    appIcons: `<span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg> Notion</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg> Word</span><span class="app-icon-pill"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="8" width="16" height="12" rx="2" ry="2"></rect><line x1="12" y1="4" x2="12" y2="8"></line><line x1="9" y1="13" x2="9.01" y2="13"></line><line x1="15" y1="13" x2="15.01" y2="13"></line><path d="M9 17h6"></path></svg> ChatGPT</span>`,
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
  developer: "developer_casual",
  other: "other_formal",
  autocleanup: "cleanup_light"
};

document.addEventListener("DOMContentLoaded", () => {
  resetAllSubViews();
  resetPageScroll();
  // The app opens on the Audio Flow feature (first sidebar position), not on
  // Voice Flow Home. switchPage triggers its own page loaders.
  currentPageId = "audioflow";
  try {
    const localPolish = localStorage.getItem("vf_polishing_enabled");
    const initialPolishToggle = document.getElementById("toggle-polishing");
    if (initialPolishToggle && localPolish !== null) {
      initialPolishToggle.checked = (localPolish === "true");
    }
  } catch (_) {}
  const sidebarBtn = document.querySelector(".sidebar-toggle-btn");
  if (sidebarBtn && typeof sidebarBtn.blur === "function") {
    sidebarBtn.blur();
  }
  initNavigation();
  initAccountAuth();
  const urlParams = new URLSearchParams(window.location.search);
  const targetPage = urlParams.get("page") || (window.location.hash ? window.location.hash.slice(1) : "audioflow");
  switchPage(targetPage);
  if (urlParams.get("open_history") === "1" || window.location.hash === "#history-open") {
    const histPanel = document.getElementById("af-history-panel");
    if (histPanel) histPanel.open = true;
  }
  if (urlParams.get("tab") === "library") {
    setTimeout(() => {
      if (typeof vfFlowShowTab === "function") vfFlowShowTab("library");
    }, 150);
  }
  loadSavedApiKeys();
  loadStyleSettings();
  renderStyleCategory("personal");
  loadFeatureToggleStates();
  startFloatingBarStartupSequence();
  initOverlayControl();
  maybeShowOnboarding();
  loadHome();
  loadInsights();
  loadExecVoiceFlowPolicy();
  loadVoiceFlowPolishSettings();
  loadVoiceDownloadableModels();

  // Real-time auto-refresh: only refresh the data of the page the user is
  // actually looking at. 10s cadence to avoid rebuild churn; skipped while
  // hands-free recording is active. loadHistory also no-ops its re-render
  // when the fetched records are unchanged (hash compare).
  setInterval(() => {
    if (document.hidden) return;
    if (typeof isHandsFreeRecording !== "undefined" && isHandsFreeRecording) return;
    if (currentPageId === "home") loadHome();
    else if (currentPageId === "insights") loadInsights();
  }, 10000);
});

// Enforce scroll position at absolute top on window load to override browser restoration
window.addEventListener("load", () => {
  resetPageScroll();
  requestAnimationFrame(() => resetPageScroll());
  setTimeout(() => resetPageScroll(), 50);
  setTimeout(() => resetPageScroll(), 150);
  setTimeout(() => resetPageScroll(), 300);
});

/**
 * Clean and sanitize error messages so raw HTML / DOCTYPE / SyntaxError
 * parse tokens are never displayed in the UI.
 */
function cleanErrorMessage(msg) {
  if (!msg) return "An unexpected error occurred.";
  let str = typeof msg === "string" ? msg : (msg.message || String(msg));
  if (
    str.includes("Unexpected token") ||
    str.includes("is not valid JSON") ||
    str.includes("<!DOCTYPE") ||
    str.includes("<!doctype") ||
    str.includes("<html") ||
    str.includes("<head") ||
    str.includes("<body")
  ) {
    return "Server returned an invalid response. Please check backend status.";
  }
  return str;
}

/**
 * Safe JSON fetch helper that protects against HTML error pages, non-JSON responses,
 * and network errors. Guarantees res.json() SyntaxError cannot crash the UI.
 */
async function safeFetchJson(url, options = {}) {
  try {
    const res = await fetch(url, options);
    const text = await res.text();
    if (!text || !text.trim()) {
      return {
        success: res.ok,
        ok: res.ok,
        status: res.status,
        ...(res.ok ? {} : { error: `Server returned status ${res.status}` }),
      };
    }
    try {
      const data = JSON.parse(text);
      if (!res.ok) {
        if (data && typeof data === "object" && !Array.isArray(data)) {
          if (!data.error) {
            data.error = `Server returned status ${res.status}`;
          }
          if (data.success === undefined) {
            data.success = false;
          }
        }
      }
      return data;
    } catch (parseErr) {
      console.error(`Non-JSON response from ${url}:`, text);
      const isHtml = text.trim().startsWith("<") || text.toLowerCase().includes("<!doctype");
      const cleanError = isHtml
        ? `Server error (${res.status})`
        : `Invalid response from server (${res.status})`;
      return {
        success: false,
        ok: false,
        status: res.status,
        error: cleanError,
      };
    }
  } catch (netErr) {
    console.error(`Network error requesting ${url}:`, netErr);
    return {
      success: false,
      ok: false,
      status: 0,
      error: netErr.message || "Network request failed",
    };
  }
}
if (typeof window !== "undefined") {
  window.safeFetchJson = safeFetchJson;
}

async function loadStyleSettings() {
  try {
    const data = await safeFetchJson("/api/styles/get");
    if (data && data.styles) {
      selectedStyles = { ...selectedStyles, ...data.styles };
      for (const [cat, val] of Object.entries(selectedStyles)) {
        if (val && typeof val === "string" && !val.includes("_")) {
          selectedStyles[cat] = `${cat}_${val}`;
        }
      }
      renderStyleCategory(currentStyleCategory);
    }
  } catch (err) {
    console.error("Error loading style settings:", err);
  }
}

// Load persistent API keys from SQLite storage on startup
async function loadSavedApiKeys() {
  try {
    const keysMap = await safeFetchJson("/api/apikeys/list");
    if (!keysMap || keysMap.error || keysMap.success === false) return;

    for (const [provider, keyVal] of Object.entries(keysMap)) {
      const inputEl = document.getElementById(`key-input-${provider}`);
      const badgeContainer = document.getElementById(`status-badge-${provider}`);
      if (inputEl && keyVal && typeof keyVal === "string") {
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

// Floating Bar Overlay API Controls
async function checkOverlayStatus() {
  try {
    const data = await safeFetchJson("/api/overlay/status");
    if (!data || data.error || data.success === false) return null;
    return data;
  } catch (err) {
    console.warn("Could not fetch overlay status:", err);
    return null;
  }
}

async function showFloatingOverlay() {
  try {
    const data = await safeFetchJson("/api/overlay/show", { method: "POST" });
    if (data && data.success !== false) {
      if (typeof vfToast === "function") vfToast("Floating bar brought to front.");
    }
    return data;
  } catch (err) {
    console.error("Error showing floating bar:", err);
  }
}

async function resetFloatingOverlayPosition() {
  try {
    const data = await safeFetchJson("/api/overlay/reset-position", { method: "POST" });
    if (data && data.success !== false) {
      if (typeof vfToast === "function") vfToast("Floating bar reset to default position.");
    }
    return data;
  } catch (err) {
    console.error("Error resetting floating bar position:", err);
  }
}

async function initOverlayControl() {
  try {
    const status = await checkOverlayStatus();
    if (status && status.active !== false) {
      await safeFetchJson("/api/overlay/show", { method: "POST" }).catch(() => {});
    }
  } catch (err) {
    console.warn("Could not initialize overlay control:", err);
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
  safeFetchJson("/api/record/toggle", {
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
    const data = await safeFetchJson("/api/apikeys/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerKey, key: keyVal, model: selectedModel }),
    });

    if (data && data.success) {
      badgeContainer.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
    } else {
      const errMsg = (data && data.error) ? data.error : "Connection test failed";
      badgeContainer.innerHTML = `<span class="status-badge status-error" title="${escapeHtml(errMsg)}">✕ ${escapeHtml(errMsg)}</span>`;
    }

  } catch (err) {
    badgeContainer.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message || "Test failed")}</span>`;
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
  safeFetchJson("/api/settings/update", {
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
let currentPageId = "home";

// The five Voice Flow features live inside the collapsible parent menu.
const VOICEFLOW_CHILD_PAGES = ["home", "insights", "dictionary", "style", "providers"];

function toggleVoiceFlowMenu(event) {
  if (event) event.stopPropagation();
  const group = document.getElementById("voiceflow-nav-group");
  if (group) group.classList.toggle("open");
}

function setVoiceFlowMenuOpen(open) {
  const group = document.getElementById("voiceflow-nav-group");
  if (group) group.classList.toggle("open", Boolean(open));
}

function updateVoiceFlowParentState(pageId) {
  const toggle = document.getElementById("voiceflow-nav-toggle");
  if (!toggle) return;
  const isChild = VOICEFLOW_CHILD_PAGES.includes(pageId);
  toggle.classList.toggle("active", isChild);
  // Keep the current page's entry visible even if the menu was collapsed.
  if (isChild) setVoiceFlowMenuOpen(true);
}

function initNavigation() {
  const navItems = document.querySelectorAll(".sidebar .nav-item[data-page]");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const pageId = item.getAttribute("data-page");
      switchPage(pageId);
    });
  });
  // Start with the dropdown open when the landing page is one of its children.
  updateVoiceFlowParentState(currentPageId);
}

function resetPageScroll(targetElement) {
  try {
    if (typeof history !== "undefined" && "scrollRestoration" in history) {
      history.scrollRestoration = "manual";
    }
  } catch (_) {}

  try {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  } catch (_) {
    try { window.scrollTo(0, 0); } catch (_) {}
  }
  if (document.documentElement) {
    document.documentElement.scrollTop = 0;
    document.documentElement.scrollLeft = 0;
  }
  if (document.body) {
    document.body.scrollTop = 0;
    document.body.scrollLeft = 0;
  }

  const mainContent = document.querySelector(".main-content");
  if (mainContent) {
    mainContent.scrollTop = 0;
    mainContent.scrollLeft = 0;
  }

  if (targetElement) {
    targetElement.scrollTop = 0;
    targetElement.scrollLeft = 0;
  }

  document.querySelectorAll(".page-view").forEach(pv => {
    pv.scrollTop = 0;
    pv.scrollLeft = 0;
  });
}

function resetAllSubViews() {
  // 1. Reset Audio Flow provider detail view back to main overview
  try {
    currentAudioProvider = null;
    const afOverview = document.getElementById("audio-providers-view-overview");
    const afDetail = document.getElementById("audio-providers-view-detail");
    if (afOverview) afOverview.style.display = "block";
    if (afDetail) afDetail.style.display = "none";
    const audioErrBanner = document.getElementById("audio-voices-test-error-banner");
    if (audioErrBanner) {
      audioErrBanner.textContent = "";
      audioErrBanner.style.display = "none";
    }
  } catch (_) {}

  // 2. Reset Voice Flow Providers views back to main overview
  try {
    currentSelectedProvider = null;
    currentDmDetailModelId = null;
    const pOverview = document.getElementById("providers-view-overview");
    const pDetail = document.getElementById("providers-view-detail");
    const dmDetail = document.getElementById("downloadable-model-view-detail");
    if (pOverview) pOverview.style.display = "block";
    if (pDetail) pDetail.style.display = "none";
    if (dmDetail) dmDetail.style.display = "none";
    const errBanner = document.getElementById("models-test-error-banner");
    if (errBanner) {
      errBanner.textContent = "";
      errBanner.style.display = "none";
    }
  } catch (_) {}

  // 3. Reset Video Flow provider detail panel and modals
  try {
    if (typeof closeVideoProvider === "function") {
      closeVideoProvider();
    } else {
      const panel = document.getElementById("vf-provider-detail-panel");
      panel?.classList.add("hidden");
      panel?.setAttribute("aria-hidden", "true");
      document.getElementById("page-videoflow")?.classList.remove("vf-provider-open");
      if (typeof vfCurrentProvider !== "undefined") vfCurrentProvider = null;
      if (typeof vfCurrentProviderDetails !== "undefined") vfCurrentProviderDetails = null;
    }
    if (typeof closeVideoModal === "function") {
      closeVideoModal("vf-model-picker-modal");
      closeVideoModal("vf-custom-model-modal");
      closeVideoModal("vf-oauth-modal");
      closeVideoModal("vf-connection-modal");
      closeVideoModal("vf-preview-modal");
    }
  } catch (_) {}

  // 4. Universal modals
  try {
    const modal = document.getElementById("vf-universal-modal");
    if (modal && modal.style.display !== "none" && typeof _closeUniversalModal === "function") {
      _closeUniversalModal(false);
    }
  } catch (_) {}
}

function switchPage(pageId, options = {}) {
  currentPageId = pageId;
  document.body.classList.toggle("flow-workspace-active", ["audioflow", "videoflow", "providers", "dictionary"].includes(pageId));
  document.querySelectorAll(".sidebar .nav-item[data-page]").forEach(nav => {
    nav.classList.toggle("active", nav.getAttribute("data-page") === pageId);
  });
  updateVoiceFlowParentState(pageId);

  // Always reset nested sub-views and provider details when switching or refreshing pages
  resetAllSubViews();

  document.querySelectorAll(".page-view").forEach(page => {
    page.style.display = "none";
    page.scrollTop = 0;
  });

  const target = document.getElementById(`page-${pageId}`);
  if (target) {
    target.style.display = "block";

    if (!options.skipScrollReset) {
      resetPageScroll(target);
    }

    if (pageId === "home") {
      loadHome();
      loadExecVoiceFlowPolicy();
      loadVoiceFlowPolishSettings();
      loadFeatureToggleStates();
    }
    if (pageId === "insights") loadInsights();
    if (pageId === "dictionary") loadDictionary();
    if (pageId === "style") {
      loadStyleSettings();
      renderStyleCategory(currentStyleCategory);
    }
    if (pageId === "providers") loadProvidersOverview();
    if (pageId === "audioflow") loadAudioFlowPage();
    if (pageId === "videoflow") {
      if (typeof loadVideoFlow === "function") loadVideoFlow();
      else if (typeof loadVideoCatalog === "function") loadVideoCatalog();
    }

    if (!options.skipScrollReset) {
      requestAnimationFrame(() => resetPageScroll(target));
      setTimeout(() => resetPageScroll(target), 50);
      setTimeout(() => resetPageScroll(target), 150);
      setTimeout(() => resetPageScroll(target), 300);
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

  // Render the available cards for this category.
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
  const previousCardId = selectedStyles[categoryKey];
  selectedStyles[categoryKey] = cardId;
  renderStyleCategory(categoryKey);
  try {
    const response = await fetch("/api/styles/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: categoryKey, style_id: cardId }),
    });
    const result = await response.json();
    if (!response.ok || !result || !result.success) {
      throw new Error((result && result.error) || "Could not save the style selection.");
    }
    // Use the canonical id returned by the backend, which also covers old
    // callers that submit a preset suffix instead of a complete card id.
    selectedStyles[categoryKey] = result.style_id || cardId;
    renderStyleCategory(categoryKey);
  } catch (err) {
    console.error("Error saving style selection:", err);
    selectedStyles[categoryKey] = previousCardId;
    renderStyleCategory(categoryKey);
    if (typeof vfToast === "function") {
      vfToast(err.message || "Could not save the style selection.", true);
    }
  }
}

// --- User-Configurable Trigger & Hotkey Settings ---
let _isRecordingHotkey = false;
let _hotkeyKeydownListener = null;

async function loadHotkeySettings() {
  try {
    const res = await safeFetchJson("/api/settings/hotkey");
    if (!res || !res.success) return;

    const trigger = res.hotkey_trigger || "ctrl_win";
    const customKey = res.custom_hotkey || "Alt+Space";
    const customType = res.custom_trigger_type || "hold";
    const mode = res.dictation_trigger_mode || "hybrid";
    const middleEnabled = res.middle_click_enabled !== false;
    const pttLabel = res.push_to_talk_shortcut || "Ctrl+Win";

    _currentCustomTriggerType = customType;

    // 1. Update Main Settings Panel
    const mainSelect = document.getElementById("setting-hotkey-trigger-select");
    if (mainSelect) mainSelect.value = trigger;

    const pttKbd = document.getElementById("ptt-current-kbd");
    if (pttKbd) pttKbd.textContent = pttLabel;

    const dispKbd = document.getElementById("ptt-display-kbd");
    if (dispKbd) dispKbd.textContent = mode === "ptt_only" ? "PTT Only" : (mode === "toggle_only" ? "Toggle Only" : "Hybrid");

    const modeLabels = { hybrid: "Smart Hybrid", ptt_only: "Strict Hold to Talk", toggle_only: "Strict Tap to Toggle" };
    const modeBadge = document.getElementById("dictation-mode-badge");
    if (modeBadge) modeBadge.textContent = modeLabels[mode] || mode;

    // 2. Update Sub-Modal Elements
    const modalSelect = document.getElementById("modal-hotkey-trigger-select");
    if (modalSelect) modalSelect.value = trigger;

    const customInput = document.getElementById("custom-hotkey-input");
    if (customInput) customInput.value = customKey;

    const customPanel = document.getElementById("custom-hotkey-panel");
    if (customPanel) {
      customPanel.style.display = (trigger === "custom") ? "block" : "none";
    }

    const middleToggle = document.getElementById("modal-toggle-middle-click");
    if (middleToggle) middleToggle.checked = middleEnabled;

    // Highlight trigger behavior card for standard mode
    document.querySelectorAll("#standard-behavior-section .shortcut-option-card").forEach(c => c.classList.remove("active-option"));
    const cardId = mode === "ptt_only" ? "shortcut-mode-ptt" : (mode === "toggle_only" ? "shortcut-mode-toggle" : "shortcut-mode-hybrid");
    const card = document.getElementById(cardId);
    if (card) card.classList.add("active-option");

    // Highlight trigger category tab
    document.querySelectorAll(".trigger-cat-tab").forEach(t => t.classList.remove("active"));
    if (trigger === "double_ctrl" || (trigger === "custom" && customType === "double_tap")) {
      document.getElementById("cat-tab-double")?.classList.add("active");
    } else if (trigger === "middle_click") {
      document.getElementById("cat-tab-mouse")?.classList.add("active");
    } else {
      document.getElementById("cat-tab-hold")?.classList.add("active");
    }

    // Highlight custom trigger behavior card
    document.querySelectorAll("#custom-hotkey-panel .shortcut-option-card").forEach(c => c.classList.remove("active-option"));
    const customCardId = customType === "double_tap" ? "custom-opt-double" : (customType === "toggle" ? "custom-opt-toggle" : "custom-opt-hold");
    document.getElementById(customCardId)?.classList.add("active-option");
    const customBadge = document.getElementById("custom-status-badge");
    if (customBadge) {
      customBadge.textContent = customType === "double_tap" ? "Double Tap" : (customType === "toggle" ? "Toggle" : "Hold PTT");
    }

    return res;
  } catch (err) {
    console.error("Failed to load hotkey settings:", err);
  }
}

async function saveHotkeySettings(newSettings, showToast = true) {
  try {
    const res = await safeFetchJson("/api/settings/hotkey", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newSettings),
    });
    if (res && res.success) {
      await loadHotkeySettings();
      if (showToast && typeof vfToast === "function") {
        const triggerNames = {
          ctrl_win: "Ctrl + Win",
          single_ctrl: "Single Ctrl",
          double_ctrl: "Double Ctrl",
          alt_space: "Alt + Space",
          alt_tab: "Alt + Tab",
          middle_click: "Middle Mouse Button Only",
          custom: newSettings.custom_hotkey || "Custom Key",
        };
        const updatedLabel = triggerNames[newSettings.hotkey_trigger] || newSettings.push_to_talk_shortcut || "Settings";
        vfToast(`Shortcut updated: ${updatedLabel}`);
      }
      return res;
    }
  } catch (err) {
    console.error("Error saving hotkey settings:", err);
    if (showToast && typeof vfToast === "function") {
      vfToast("Failed to save shortcut settings", true);
    }
  }
}

function openShortcutDialog() {
  const modal = document.getElementById("shortcuts-sub-modal");
  if (modal) {
    modal.classList.remove("hidden");
    loadHotkeySettings();
  }
}

function onHotkeyTriggerSelectChange(value) {
  if (value === "custom") {
    openShortcutDialog();
  } else {
    saveHotkeySettings({ hotkey_trigger: value });
  }
}

let _currentCustomTriggerType = "hold";

function selectTriggerCategory(cat) {
  document.querySelectorAll(".trigger-cat-tab").forEach(t => t.classList.remove("active"));
  if (cat === "double") {
    document.getElementById("cat-tab-double")?.classList.add("active");
    onModalHotkeyTriggerChange("double_ctrl");
  } else if (cat === "hold") {
    document.getElementById("cat-tab-hold")?.classList.add("active");
    onModalHotkeyTriggerChange("single_ctrl");
  } else if (cat === "mouse") {
    document.getElementById("cat-tab-mouse")?.classList.add("active");
    onModalHotkeyTriggerChange("middle_click");
  }
}

function activateCustomKeyMode() {
  onModalHotkeyTriggerChange("custom");
  const panel = document.getElementById("custom-hotkey-panel");
  if (panel) {
    panel.style.display = "block";
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function selectCustomTriggerType(type, el) {
  _currentCustomTriggerType = type;
  document.querySelectorAll("#custom-hotkey-panel .shortcut-option-card").forEach(c => c.classList.remove("active-option"));
  if (el) el.classList.add("active-option");
  const customBadge = document.getElementById("custom-status-badge");
  if (customBadge) {
    customBadge.textContent = type === "double_tap" ? "Double Tap" : (type === "toggle" ? "Toggle" : "Hold PTT");
  }
}

function onModalHotkeyTriggerChange(value) {
  const customPanel = document.getElementById("custom-hotkey-panel");
  if (customPanel) {
    customPanel.style.display = (value === "custom") ? "block" : "none";
  }
  const modalSelect = document.getElementById("modal-hotkey-trigger-select");
  if (modalSelect) modalSelect.value = value;
  const mainSelect = document.getElementById("setting-hotkey-trigger-select");
  if (mainSelect) mainSelect.value = value;

  // Sync category tabs
  document.querySelectorAll(".trigger-cat-tab").forEach(t => t.classList.remove("active"));
  if (value === "double_ctrl" || (value === "custom" && _currentCustomTriggerType === "double_tap")) {
    document.getElementById("cat-tab-double")?.classList.add("active");
  } else if (value === "middle_click") {
    document.getElementById("cat-tab-mouse")?.classList.add("active");
  } else {
    document.getElementById("cat-tab-hold")?.classList.add("active");
  }
}

function onToggleMiddleClickChange(enabled) {
  saveHotkeySettings({ middle_click_enabled: enabled }, false);
}

function selectShortcutMode(modeName, el) {
  if (el) {
    document.querySelectorAll("#standard-behavior-section .shortcut-option-card").forEach(card => card.classList.remove("active-option"));
    el.classList.add("active-option");
    saveHotkeySettings({ dictation_trigger_mode: modeName });
  }
}

function toggleRecordHotkey() {
  const btn = document.getElementById("record-hotkey-btn");
  const hint = document.getElementById("record-hotkey-hint");
  const input = document.getElementById("custom-hotkey-input");
  if (!btn || !input) return;

  if (_isRecordingHotkey) {
    // Stop recording
    _isRecordingHotkey = false;
    btn.textContent = "🎙️ Record Any Key";
    btn.style.background = "";
    btn.style.color = "";
    if (input.value.endsWith("...") || !input.value.trim()) {
      input.value = input.dataset.previousValid || "Alt+Space";
    }
    if (hint) hint.innerHTML = "Recorded: <b>" + (input.value || "Alt+Space") + "</b>. Click <b>Save &amp; Apply</b> to persist.";
    if (_hotkeyKeydownListener) {
      window.removeEventListener("keydown", _hotkeyKeydownListener, true);
      _hotkeyKeydownListener = null;
    }
    return;
  }

  // Start recording
  input.dataset.previousValid = (input.value && !input.value.endsWith("...")) ? input.value.trim() : "Alt+Space";
  _isRecordingHotkey = true;
  btn.textContent = "🔴 Stop Recording";
  btn.style.background = "var(--primary-orange)";
  btn.style.color = "#fff";
  if (hint) hint.innerHTML = "<b>Listening...</b> Press your key or combination now (e.g. F8, Space, CapsLock, Alt+Space).";

  _hotkeyKeydownListener = function(e) {
    e.preventDefault();
    e.stopPropagation();

    const parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if (e.shiftKey) parts.push("Shift");
    if (e.metaKey) parts.push("Win");

    let key = e.key;
    if (!["Control", "Alt", "Shift", "Meta"].includes(key)) {
      if (key === " ") key = "Space";
      else if (key === "CapsLock") key = "CapsLock";
      else if (key.length === 1) key = key.toUpperCase();
      parts.push(key);

      const combo = parts.join("+");
      input.value = combo;
      toggleRecordHotkey(); // Auto stop on complete combo
    } else {
      input.value = parts.join("+") + "...";
    }
  };

  window.addEventListener("keydown", _hotkeyKeydownListener, true);
}

function clearRecordedHotkey() {
  const input = document.getElementById("custom-hotkey-input");
  if (input) input.value = "Alt+Space";
  const hint = document.getElementById("record-hotkey-hint");
  if (hint) hint.textContent = "Click Record Any Key, then press your desired key or combination.";
}

function resetHotkeyDefaults() {
  saveHotkeySettings({
    hotkey_trigger: "ctrl_win",
    custom_hotkey: "Alt+Space",
    custom_trigger_type: "hold",
    dictation_trigger_mode: "hybrid",
    middle_click_enabled: true,
    push_to_talk_shortcut: "Ctrl+Win"
  });
}

function saveAndApplyHotkeyModal() {
  const modalSelect = document.getElementById("modal-hotkey-trigger-select");
  const customInput = document.getElementById("custom-hotkey-input");
  const middleToggle = document.getElementById("modal-toggle-middle-click");

  const trigger = modalSelect ? modalSelect.value : "ctrl_win";
  let customKey = customInput ? customInput.value.trim() : "Alt+Space";
  if (customKey.endsWith("...") || !customKey) {
    customKey = customInput?.dataset?.previousValid || "Alt+Space";
    if (customInput) customInput.value = customKey;
  }
  const middleEnabled = middleToggle ? middleToggle.checked : true;

  let activeMode = "hybrid";
  if (document.getElementById("shortcut-mode-ptt")?.classList.contains("active-option")) activeMode = "ptt_only";
  if (document.getElementById("shortcut-mode-toggle")?.classList.contains("active-option")) activeMode = "toggle_only";

  let customTrigType = _currentCustomTriggerType || "hold";
  if (document.getElementById("custom-opt-double")?.classList.contains("active-option")) customTrigType = "double_tap";
  if (document.getElementById("custom-opt-hold")?.classList.contains("active-option")) customTrigType = "hold";
  if (document.getElementById("custom-opt-toggle")?.classList.contains("active-option")) customTrigType = "toggle";

  saveHotkeySettings({
    hotkey_trigger: trigger,
    custom_hotkey: customKey,
    custom_trigger_type: customTrigType,
    middle_click_enabled: middleEnabled,
    dictation_trigger_mode: activeMode,
  });

  closeSubModal("shortcuts-sub-modal");
}

async function changePushToTalkKey() {
  openShortcutDialog();
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

// Dynamic Hardware Audio Input Detection & Hardware Routing
async function loadHardwareMicrophones() {
  const container = document.getElementById("mic-devices-list");
  if (!container) return;

  try {
    const [micsRes, savedMicRes] = await Promise.all([
      safeFetchJson("/api/microphones"),
      safeFetchJson("/api/settings/get?key=selected_mic_device"),
    ]);
    const mics = Array.isArray(micsRes) ? micsRes : [];
    const savedMic = (savedMicRes && savedMicRes.value) ? String(savedMicRes.value) : "";

    if (!mics || mics.length === 0) {
      mics.push({ index: 0, name: "Headset (Max Pro)" });
    }

    let activeIdx = 0;
    if (savedMic) {
      const foundIdx = mics.findIndex(m => m.name === savedMic || String(m.index) === savedMic);
      if (foundIdx >= 0) activeIdx = foundIdx;
    }

    container.innerHTML = mics.map((mic, i) => {
      const isSelected = i === activeIdx;
      return `
        <div class="mic-option-card ${isSelected ? 'selected-mic' : ''}" onclick="selectMicrophoneDevice('${escapeJs(mic.name)}', ${mic.index}, this)">
          <div style="font-size: 14px; font-weight: 700; color: var(--text-main);">${escapeHtml(mic.name)}</div>
          ${isSelected ? `
            <div class="audio-signal-bars">
              <span class="bar active"></span><span class="bar active"></span><span class="bar active"></span><span class="bar active"></span><span class="bar active"></span>
            </div>
          ` : ''}
        </div>
      `;
    }).join("");

    const badge = document.getElementById("current-mic-badge");
    if (badge && mics[activeIdx]) { badge.textContent = mics[activeIdx].name; badge.title = mics[activeIdx].name; }
    const micDesc = document.getElementById("current-mic-desc");
    if (micDesc && mics[activeIdx]) micDesc.textContent = mics[activeIdx].name;

  } catch (err) {
    console.error("Error detecting hardware microphones:", err);
  }
}

async function selectMicrophoneDevice(micName, micIndex, el) {
  const badge = document.getElementById("current-mic-badge");
  if (badge) { badge.textContent = micName; badge.title = micName; }
  const desc = document.getElementById("current-mic-desc");
  if (desc) desc.textContent = micName;
  if (el) {
    document.querySelectorAll("#mic-devices-list .mic-option-card").forEach(c => c.classList.remove("selected-mic"));
    el.classList.add("selected-mic");
  }

  try {
    await safeFetchJson("/api/microphones/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: micName, index: micIndex }),
    });
    if (typeof vfToast === "function") vfToast(`Microphone selected: ${micName}`);
  } catch (err) {
    console.error("Error setting active microphone:", err);
    if (typeof vfToast === "function") vfToast("Failed to select microphone.", true);
  }

  closeSubModal('mic-sub-modal');
}

// Home Page Data Aggregator (loads both History & Insights metrics immediately)
async function loadHome() {
  await Promise.all([loadHistory(), loadInsights()]);
}

// Fetch and render Dictation History from SQLite Database
async function loadHistory() {
  const container = document.getElementById("dictations-list");
  if (!container) return;

  try {
    const res = await fetch("/api/history");
    const records = await res.json();
    // Skip the full re-render when nothing changed (avoids innerHTML churn
    // on every background refresh tick).
    const nextHash = JSON.stringify(records);
    if (nextHash === lastHistoryHash) return;
    lastHistoryHash = nextHash;
    allHistoryRecords = records;
    maybeCelebrateFirstDictation(allHistoryRecords ? allHistoryRecords.length : 0);

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

function renderDictationCardHtml(r) {
  const timeStr = r.timestamp && r.timestamp.includes(" ") ? r.timestamp.split(" ")[1].substring(0, 5) : "";
  const isPinned = Boolean(r.is_pinned);
  return `
    <div class="dictation-card ${isPinned ? "is-pinned" : ""}" id="dictation-card-${r.id}">
      <div class="dictation-time">${timeStr}</div>
      <div class="dictation-body">
        <div class="dictation-meta">
          <span class="app-badge">${escapeHtml(r.app_name || "General")}</span>
          ${isPinned ? `<span class="pinned-badge"><svg class="lucide" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg> Pinned</span>` : ""}
          <span style="font-size: 12px; color: var(--text-muted);">• ${r.word_count || 0} words (${r.wpm_speed || 0} wpm)</span>
        </div>
        <div class="dictation-text">${escapeHtml(r.polished_text || "")}</div>
      </div>
      <div class="dictation-actions">
        <button type="button" onclick="copyToClipboard('${escapeJs(r.polished_text || "")}', this)" class="action-btn" title="Copy transcript to clipboard"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg> Copy</button>
        <button type="button" onclick="toggleHistoryPin(${r.id})" class="action-btn ${isPinned ? "pinned" : ""}" title="${isPinned ? "Unpin — remove from top" : "Pin — keep at top"}">${isPinned ? '<svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg> Pinned' : '<svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg> Pin'}</button>
        <button type="button" onclick="deleteHistoryRecord(${r.id})" class="action-btn delete-btn" title="Delete this dictation"><svg class="lucide" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete</button>
      </div>
    </div>
  `;
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

  const pinnedRecords = records.filter(r => Boolean(r.is_pinned));
  const unpinnedRecords = records.filter(r => !r.is_pinned);

  let html = "";

  // Dedicated Pinned section at top if any are pinned
  if (pinnedRecords.length > 0) {
    html += `<div class="date-group-header"><span>📌 PINNED DICTATIONS (${pinnedRecords.length})</span></div>`;
    html += pinnedRecords.map(r => renderDictationCardHtml(r)).join("");
  }

  // Group unpinned records by Date
  if (unpinnedRecords.length > 0) {
    const groups = {};
    unpinnedRecords.forEach(r => {
      const dateStr = r.timestamp ? r.timestamp.split(" ")[0] : "TODAY";
      const groupKey = formatGroupDate(dateStr);
      if (!groups[groupKey]) groups[groupKey] = [];
      groups[groupKey].push(r);
    });

    for (const [groupName, groupRecords] of Object.entries(groups)) {
      html += `<div class="date-group-header"><span>${groupName}</span></div>`;
      html += groupRecords.map(r => renderDictationCardHtml(r)).join("");
    }
  }

  container.innerHTML = html;
}

async function toggleHistoryPin(recordId) {
  const rec = allHistoryRecords.find(r => r.id === recordId);
  const nextPinned = rec ? !rec.is_pinned : true;
  if (rec) {
    rec.is_pinned = nextPinned ? 1 : 0;
    filterHistory();
  }
  try {
    const res = await fetch("/api/history/pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: recordId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data && typeof data.is_pinned === "boolean" && rec) {
      rec.is_pinned = data.is_pinned ? 1 : 0;
    }
    showToast(nextPinned ? "Dictation pinned to top" : "Dictation unpinned", "📌");
    loadHistory();
  } catch (err) {
    console.error("Error toggling history pin:", err);
    if (rec) {
      rec.is_pinned = !nextPinned ? 1 : 0;
      filterHistory();
    }
    showToast("Could not update pin state", "⚠️");
  }
}

async function deleteHistoryRecord(recordId) {
  allHistoryRecords = allHistoryRecords.filter(r => r.id !== recordId);
  filterHistory();
  try {
    const res = await fetch("/api/history/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: recordId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast("Dictation deleted", "🗑️");
    loadInsights();
  } catch (err) {
    console.error("Error deleting history record:", err);
    showToast("Could not delete record", "⚠️");
    loadHistory();
  }
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

function _localDateKey(date) {
  // Storage serves local-naive dates; toISOString() would shift them to UTC.
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatGroupDate(dateStr) {
  const now = new Date();
  if (dateStr === _localDateKey(now)) return "TODAY";
  const yesterday = new Date(now.getTime() - 86400000);
  if (dateStr === _localDateKey(yesterday)) return "YESTERDAY";
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
//
// The page deliberately shows only four headline numbers. Everything else
// lives behind the "More detail" disclosure so the default view stays readable.
let allAppsCache = [];
let appsExpanded = false;
const APPS_COLLAPSED = 5;

function renderAppRows(container, apps) {
  if (!container) return;
  // Bars are scaled against the top app rather than the total, so smaller
  // entries stay visible instead of collapsing into invisible slivers.
  const max = Math.max(...apps.map(a => a.total_words || 0), 1);
  container.innerHTML = apps.map(app => {
    const words = app.total_words || 0;
    const width = Math.max(2, Math.round((words / max) * 100));
    const pct = Number.isFinite(Number(app.percentage)) ? Number(app.percentage) : 0;
    return `
      <div class="usage-item">
        <div class="usage-row">
          <span class="usage-app">${getAppIcon(app.app_name)}<strong>${escapeHtml(app.app_name)}</strong></span>
          <span class="usage-value">${pct}%</span>
        </div>
        <div class="usage-bar"><span style="width: ${width}%"></span></div>
      </div>`;
  }).join("");
}

function toggleAllApps() {
  appsExpanded = !appsExpanded;
  const container = document.getElementById("insights-app-breakdown");
  const btn = document.getElementById("insights-app-more");
  renderAppRows(container, appsExpanded ? allAppsCache : allAppsCache.slice(0, APPS_COLLAPSED));
  if (btn) {
    btn.textContent = appsExpanded
      ? `Show top ${APPS_COLLAPSED}`
      : `Show all ${allAppsCache.length} apps`;
  }
}

async function loadInsights() {
  try {
    const res = await fetch(`/api/insights?range=${currentInsightsRange}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const totalWords = data.total_words || 0;
    const avgWpm = data.avg_wpm || 0;
    const streak = data.streak || 0;
    const dictationCount = data.dictation_count || 0;
    const speakingHours = data.speaking_hours || 0;
    const measuredCount = data.measured_dictations || 0;

    // Home Banner Metrics
    const totalWordsFormatted = totalWords >= 1000 ? (totalWords / 1000).toFixed(1) + "K" : totalWords;
    if (document.getElementById("stat-total-words")) document.getElementById("stat-total-words").textContent = totalWordsFormatted;
    if (document.getElementById("stat-wpm")) document.getElementById("stat-wpm").textContent = avgWpm;
    if (document.getElementById("stat-streak")) document.getElementById("stat-streak").textContent = streak;

    // --- Card 1: speaking speed ---
    const insightsWpm = document.getElementById("insights-wpm");
    if (insightsWpm) insightsWpm.textContent = avgWpm;

    const speedFoot = document.getElementById("insights-speed-foot");
    if (speedFoot) {
      speedFoot.textContent = measuredCount > 0
        ? `Across ${measuredCount.toLocaleString()} dictations · ${speakingHours} h of speech`
        : "No dictations yet";
    }

    // --- Card 2: time saved ---
    const savedHours = data.time_saved_hours !== undefined ? data.time_saved_hours : 0;
    const savedMinutes = data.time_saved_minutes !== undefined ? data.time_saved_minutes : 0;
    const speedMult = data.speed_multiplier !== undefined
      ? data.speed_multiplier
      : (avgWpm > 0 ? Number((avgWpm / 40.0).toFixed(1)) : 1.0);

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
    if (multiplierEl) multiplierEl.textContent = `${speedMult}x faster`;
    const totalWordsEl = document.getElementById("insights-total-words");
    if (totalWordsEl) totalWordsEl.textContent = totalWords.toLocaleString();

    // --- Card 3: text cleaned up ---
    const aiFixesTotal = data.ai_refinements !== undefined ? data.ai_refinements : (data.words_corrected || 0);
    const wordFixes = data.words_corrected !== undefined ? data.words_corrected : 0;
    const dictFixes = data.dictionary_fixes !== undefined ? data.dictionary_fixes : 0;

    if (document.getElementById("insights-fixes-total")) document.getElementById("insights-fixes-total").textContent = aiFixesTotal.toLocaleString();
    if (document.getElementById("insights-words-corrected")) document.getElementById("insights-words-corrected").textContent = wordFixes.toLocaleString();
    if (document.getElementById("insights-dict-fixes")) document.getElementById("insights-dict-fixes").textContent = dictFixes.toLocaleString();

    // Be explicit about where the edits come from: this account runs with the AI
    // polisher switched off, so calling them "AI" refinements would overstate it.
    const fixesSource = document.getElementById("insights-fixes-source");
    if (fixesSource) {
      fixesSource.textContent = data.polishing_enabled
        ? "From AI polish + auto-cleanup"
        : "From auto-cleanup (AI polish is off)";
    }

    // --- Card 4: streak ---
    const longestStreak = data.longest_streak || streak;
    if (document.getElementById("insights-longest-streak")) document.getElementById("insights-longest-streak").textContent = streak;
    if (document.getElementById("insights-streak-title")) document.getElementById("insights-streak-title").textContent = `${longestStreak} days`;
    if (document.getElementById("insights-dictation-count")) document.getElementById("insights-dictation-count").textContent = dictationCount.toLocaleString();

    // Gauge Update
    updateSpeedGauge(avgWpm);

    // --- Where you dictate ---
    const usageContainer = document.getElementById("insights-app-breakdown");
    const moreBtn = document.getElementById("insights-app-more");
    const appNote = document.getElementById("insights-app-note");
    const unattributed = data.unattributed || { count: 0, words: 0 };

    if (usageContainer) {
      allAppsCache = Array.isArray(data.app_breakdown) ? data.app_breakdown : [];
      appsExpanded = false;

      if (allAppsCache.length === 0) {
        usageContainer.innerHTML = `
          <div class="insights-empty">
            <strong>No verified app data yet</strong>
            <span>New dictations will appear here only when the app can be identified confidently.</span>
          </div>`;
      } else {
        renderAppRows(usageContainer, allAppsCache.slice(0, APPS_COLLAPSED));
      }

      if (moreBtn) {
        if (allAppsCache.length > APPS_COLLAPSED) {
          moreBtn.style.display = "";
          moreBtn.textContent = `Show all ${allAppsCache.length} verified apps`;
        } else {
          moreBtn.style.display = "none";
        }
      }

      if (appNote) {
        const tracking = data.app_tracking || {};
        const hiddenCount = Number(tracking.hidden_count ?? unattributed.count ?? 0);
        const hiddenWords = Number(tracking.hidden_words ?? unattributed.words ?? 0);
        if (hiddenCount > 0 || hiddenWords > 0) {
          appNote.style.display = "";
          const wordsPart = hiddenWords > 0 ? ` (${hiddenWords.toLocaleString()} words)` : "";
          appNote.textContent = `${hiddenCount.toLocaleString()} older/internal/low-confidence dictations${wordsPart} are hidden instead of guessed.`;
        } else {
          appNote.style.display = "";
          appNote.textContent = "Only verified application detections are included.";
        }
      }
    }

    // Render Monthly Activity Calendar
    renderHeatmap(data.daily_activity || [], data.daily_history_map || {});

    // Render Time-of-Day Distribution
    renderTimeOfDayBars(data.time_of_day || []);

    // Voice Profile Archetype
    const vp = data.voice_profile || {};
    if (document.getElementById("insights-archetype-badge")) {
      document.getElementById("insights-archetype-badge").textContent = vp.archetype || (totalWords > 0 ? "Measured Dictation Profile" : "Getting Started");
    }
    if (document.getElementById("insights-archetype-desc")) {
      document.getElementById("insights-archetype-desc").textContent = vp.archetype_desc || "This profile is based only on measured dictation data.";
    }
    if (document.getElementById("insights-archetype-tag")) {
      document.getElementById("insights-archetype-tag").textContent = vp.archetype_tag || "Verified Stats";
    }
    if (document.getElementById("insights-archetype-icon")) {
      const __archEmoji = vp.archetype_icon || "⚡";
      const __archMap = { "🚀": '<svg class="lucide" viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path></svg>', "⚡": '<svg class="lucide" viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>' };
      document.getElementById("insights-archetype-icon").innerHTML = __archMap[__archEmoji] || __archEmoji;
    }
    if (document.getElementById("insights-vocab-status")) {
      const terms = data.total_dictionary_terms || 0;
      document.getElementById("insights-vocab-status").textContent = terms > 0 ? `${terms} terms` : "None yet";
    }
    if (document.getElementById("insights-peak-hours")) {
      document.getElementById("insights-peak-hours").textContent = vp.peak_hours || "--";
    }
    if (document.getElementById("insights-peak-hours-tag")) {
      document.getElementById("insights-peak-hours-tag").textContent = vp.peak_hours ? `Peak: ${vp.peak_hours}` : "Peak: --";
    }

    // Share Card Snippet Preview
    const previewEl = document.getElementById("share-snippet-preview");
    if (previewEl) {
      const timeStr = savedHours >= 1 ? `${savedHours} hrs` : `${Math.round(savedMinutes)} mins`;
      previewEl.textContent = `🚀 I dictated ${totalWords.toLocaleString()} words at ${avgWpm} WPM and saved ${timeStr} with AI Productivity Flow (${speedMult}x faster than typing)! #AIProductivityFlow`;
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
    // Descriptive bands only. The previous copy claimed "Top 0.5% Ultra Speed",
    // a percentile this data cannot support.
    if (clampedWpm >= 160) {
      badge.textContent = "Blazing fast";
      badge.className = "gauge-badge gauge-ultra";
    } else if (clampedWpm >= 120) {
      badge.textContent = "Very fast";
      badge.className = "gauge-badge gauge-ultra";
    } else if (clampedWpm >= 90) {
      badge.textContent = "Fast";
      badge.className = "gauge-badge gauge-rapid";
    } else if (clampedWpm >= 60) {
      badge.textContent = "Steady";
      badge.className = "gauge-badge gauge-fast";
    } else if (clampedWpm > 0) {
      badge.textContent = "Warming up";
      badge.className = "gauge-badge gauge-active";
    } else {
      badge.textContent = "Ready to record";
      badge.className = "gauge-badge gauge-empty";
    }
  }
}

// State for Monthly Activity Calendar
let calendarYear = new Date().getFullYear();
let calendarMonth = new Date().getMonth(); // 0-indexed (0=Jan, 11=Dec)
let userHasNavigatedMonth = false;
let cachedDailyHistoryMap = {};
let cachedDailyActivityList = [];

function navigateCalendarMonth(delta) {
  userHasNavigatedMonth = true;
  calendarMonth += delta;
  if (calendarMonth < 0) {
    calendarMonth = 11;
    calendarYear--;
  } else if (calendarMonth > 11) {
    calendarMonth = 0;
    calendarYear++;
  }
  renderMonthlyCalendar(calendarYear, calendarMonth);
}

function jumpToCurrentMonth() {
  userHasNavigatedMonth = false;
  const now = new Date();
  calendarYear = now.getFullYear();
  calendarMonth = now.getMonth();
  renderMonthlyCalendar(calendarYear, calendarMonth);
}

function renderHeatmap(dailyActivityData, dailyHistoryMap) {
  if (dailyHistoryMap && typeof dailyHistoryMap === "object") {
    cachedDailyHistoryMap = dailyHistoryMap;
  }
  if (Array.isArray(dailyActivityData)) {
    cachedDailyActivityList = dailyActivityData;
  }
  // Auto-sync calendar to real-time current month unless user explicitly navigated away
  if (!userHasNavigatedMonth) {
    const now = new Date();
    calendarYear = now.getFullYear();
    calendarMonth = now.getMonth();
  }
  renderMonthlyCalendar(calendarYear, calendarMonth);
}

function renderMonthlyCalendar(year, month) {
  const grid = document.getElementById("heatmap-grid");
  if (!grid) return;

  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  
  // Update Month Title
  const titleEl = document.getElementById("calendar-month-year-title");
  if (titleEl) {
    titleEl.textContent = `${monthNames[month]} ${year}`;
  }

  // Calculate day metrics for the selected month
  const firstDayIndex = new Date(year, month, 1).getDay(); // 0 = Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;
  const todayDateNum = today.getDate();

  // Find max words in month for relative intensity scaling
  let maxWordsInMonth = 0;
  let totalMonthWords = 0;
  let activeDaysCount = 0;
  let peakDayStr = "--";

  const monthDaysData = [];

  for (let d = 1; d <= daysInMonth; d++) {
    const dStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    let words = 0;
    let count = 0;
    let durSec = 0;

    if (cachedDailyHistoryMap[dStr]) {
      words = cachedDailyHistoryMap[dStr].words || 0;
      count = cachedDailyHistoryMap[dStr].count || 0;
      durSec = cachedDailyHistoryMap[dStr].duration_sec || 0;
    } else {
      const match = cachedDailyActivityList.find(a => a.date === dStr);
      if (match) {
        words = match.words || 0;
      }
    }

    if (words > 0) {
      activeDaysCount++;
      totalMonthWords += words;
      if (words > maxWordsInMonth) {
        maxWordsInMonth = words;
        const dObj = new Date(year, month, d);
        const dayFormatted = dObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        peakDayStr = `${dayFormatted}<span class="cal-stat-peak-sub">${words.toLocaleString()} words</span>`;
      }
    }

    monthDaysData.push({ dayNum: d, dateStr: dStr, words, count, durSec });
  }

  // Update Summary Bar Stats
  const statMonthWords = document.getElementById("cal-stat-month-words");
  const statActiveDays = document.getElementById("cal-stat-active-days");
  const statDailyAvg = document.getElementById("cal-stat-daily-avg");
  const statPeakDay = document.getElementById("cal-stat-peak-day");

  if (statMonthWords) statMonthWords.textContent = totalMonthWords.toLocaleString();
  if (statActiveDays) statActiveDays.textContent = `${activeDaysCount} / ${daysInMonth} days`;
  if (statDailyAvg) statDailyAvg.textContent = `${Math.round(totalMonthWords / daysInMonth).toLocaleString()} words`;
  if (statPeakDay) statPeakDay.innerHTML = peakDayStr;

  let html = "";
  let miniHeatmapHtml = "";

  // Render leading empty padding cells for offset days
  for (let p = 0; p < firstDayIndex; p++) {
    html += `<div class="cal-day-cell empty-pad"></div>`;
  }

  // Render actual month day cells
  monthDaysData.forEach(item => {
    const d = item.dayNum;
    const words = item.words;
    const isToday = isCurrentMonth && d === todayDateNum;
    const isFuture = isCurrentMonth && d > todayDateNum;
    const isPeak = words === maxWordsInMonth && maxWordsInMonth > 0;

    // Relative level calculation based on peak month usage
    let level = 0;
    if (words > 0) {
      if (maxWordsInMonth <= 10) {
        level = 1;
      } else {
        const ratio = words / maxWordsInMonth;
        if (ratio <= 0.25) level = 1;
        else if (ratio <= 0.50) level = 2;
        else if (ratio <= 0.75) level = 3;
        else level = 4;
      }
    }

    const dObj = new Date(year, month, d);
    const dateFormatted = dObj.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    const savedMins = Math.round((words / 140) * 0.7);

    let cellClasses = `cal-day-cell level-${level}`;
    if (isToday) cellClasses += " is-today";
    if (isPeak) cellClasses += " is-peak-day";
    if (isFuture) cellClasses += " future-day";

    html += `
      <div class="${cellClasses}">
        ${isPeak ? '<span class="cal-day-peak-icon" title="Peak Day of the Month">👑</span>' : ''}
        <span class="cal-day-num">${d}</span>
        <span class="cal-day-words">${words > 0 ? (words >= 1000 ? (words/1000).toFixed(1)+'k' : words) : ''}</span>
        <div class="cal-tooltip">
          <div class="cal-tooltip-date">${dateFormatted} ${isToday ? '(Today)' : ''}</div>
          <div class="cal-tooltip-words"><strong>${words.toLocaleString()}</strong> words dictated</div>
          <div class="cal-tooltip-sub">${words > 0 ? `⚡ Level ${level} • ~${savedMins}m saved` : 'No dictations recorded'}</div>
        </div>
      </div>
    `;

    miniHeatmapHtml += `<span class="heatmap-cell level-${level}" style="width:7px;height:7px;border-radius:2px;display:inline-block;"></span>`;
  });

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
    { period: "morning", label: "Morning", time_range: "6 AM - 12 PM", icon: "🌅", words: 0, pct: 0 },
    { period: "afternoon", label: "Afternoon", time_range: "12 PM - 5 PM", icon: "☀️", words: 0, pct: 0 },
    { period: "evening", label: "Evening", time_range: "5 PM - 10 PM", icon: "🌆", words: 0, pct: 0 },
    { period: "night", label: "Night", time_range: "10 PM - 6 AM", icon: "🌙", words: 0, pct: 0 },
  ];

  // One row per period. The old 4-across grid squeezed "Afternoon 107972 w"
  // into ~120px and wrapped the labels; a list keeps every row readable.
  container.innerHTML = periods.map(p => `
    <div class="tod-bar-item">
      <span class="tod-bar-label">${p.icon} <strong>${escapeHtml(p.label)}</strong></span>
      <span class="tod-bar-range">${escapeHtml(p.time_range)}</span>
      <div class="tod-bar-bg">
        <div class="tod-bar-fill" style="width: ${Math.max(p.pct || 0, (p.words || 0) > 0 ? 3 : 0)}%;"></div>
      </div>
      <span class="tod-bar-value">${(p.words || 0).toLocaleString()} w</span>
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

// Dictionary page (explicit vocabulary; learned suggestions need approval)
let allDictionaryWords = [];
let dictionaryHeardAs = {};
let dictionaryLoadRevision = 0;

function normalizeDictionaryEntries(entries) {
  if (!Array.isArray(entries)) return [];
  return entries.map(entry => {
    if (typeof entry === "string") return { word: entry, category: "Personal" };
    if (!entry || typeof entry.word !== "string") return null;
    return { ...entry, word: entry.word, category: String(entry.category || "Personal") };
  }).filter(Boolean);
}

function dictionaryWord(entry) {
  return String(entry && entry.word || "");
}

async function loadDictionary() {
  const chipContainer = document.getElementById("dictionary-chips");
  if (!chipContainer) return;
  const revision = ++dictionaryLoadRevision;

  // Complete background learning first.  Previously this ran concurrently
  // with the list fetch, so a slower stale response could overwrite words
  // that had just been accepted and make them appear to disappear.
  await loadDictionarySuggestions(revision);
  if (revision !== dictionaryLoadRevision) return;

  try {
    const [wordsRes, correctionsRes] = await Promise.all([
      fetch("/api/dictionary?details=1&include_auto=1"),
      fetch("/api/dictionary/corrections").catch(() => null),
    ]);
    const words = await wordsRes.json();
    if (revision !== dictionaryLoadRevision) return;
    allDictionaryWords = normalizeDictionaryEntries(words);

    dictionaryHeardAs = {};
    try {
        const corrections = correctionsRes ? await correctionsRes.json() : [];
        if (revision !== dictionaryLoadRevision) return;
      if (Array.isArray(corrections)) {
        for (const c of corrections) {
          const correct = String((c && c.correct_text) || "").trim();
          const wrong = String((c && c.wrong_text) || "").trim();
          if (!correct || !wrong) continue;
          const key = correct.toLowerCase();
          if (!dictionaryHeardAs[key]) dictionaryHeardAs[key] = [];
          if (!dictionaryHeardAs[key].some(v => v.toLowerCase() === wrong.toLowerCase())) {
            dictionaryHeardAs[key].push(wrong);
          }
        }
      }
    } catch (correctionErr) {
      dictionaryHeardAs = {};
    }

    const counterBadge = document.getElementById("dict-counter-badge");
    if (counterBadge) counterBadge.textContent = `${allDictionaryWords.length} term${allDictionaryWords.length === 1 ? '' : 's'}`;

    renderDictionaryFilteredChips();
  } catch (err) {
    console.error("Error loading dictionary:", err);
  }
}


// ===== Auto-learn: silently accept all suggestions =====

async function loadDictionarySuggestions(revision = dictionaryLoadRevision) {
  try {
    const res = await fetch("/api/dictionary/suggestions");
    const items = await res.json();
    if (!Array.isArray(items) || items.length === 0) return;
    // Auto-accept every suggestion silently
    await Promise.allSettled(
      items.map(it => {
        const id = Number(it.id) || 0;
        if (!id) return Promise.resolve();
        return fetch("/api/dictionary/suggestions/decide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, state: "active" })
        });
      })
    );
    // Refresh word list to show newly accepted words
    const wordsRes = await fetch("/api/dictionary?details=1&include_auto=1");
    const words = await wordsRes.json();
    if (revision !== dictionaryLoadRevision) return;
    allDictionaryWords = normalizeDictionaryEntries(words);
    const counterBadge = document.getElementById("dict-counter-badge");
    if (counterBadge) counterBadge.textContent = `${allDictionaryWords.length} term${allDictionaryWords.length === 1 ? '' : 's'}`;
    renderDictionaryFilteredChips();
  } catch (err) {
    // Silently ignore — auto-learn is best-effort
  }
}

function filterDictionaryChips() {
  renderDictionaryFilteredChips();
}

function getDictionaryCasingBadge(word) {
  if (/[A-Z]/.test(word)) return "A·a Exact spelling";
  return "";
}

const DICT_EMPTY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>';
const DICT_SEARCH_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>';

function updateDictionaryResultMeta(filtered) {
  const metaEl = document.getElementById("dict-result-meta");
  if (!metaEl) return;
  const queryEl = document.getElementById("dictionary-search-input");
  const query = queryEl ? queryEl.value.trim() : "";
  if (query) {
    metaEl.textContent = `${filtered.length} of ${allDictionaryWords.length} · matching “${query}”`;
  } else if (allDictionaryWords.length > 0) {
    metaEl.textContent = `Showing all ${allDictionaryWords.length}`;
  } else {
    metaEl.textContent = "";
  }
}

function renderDictionaryFilteredChips() {
  const chipContainer = document.getElementById("dictionary-chips");
  if (!chipContainer) return;

  const queryEl = document.getElementById("dictionary-search-input");
  const query = queryEl ? queryEl.value.toLowerCase().trim() : "";

  let filtered = allDictionaryWords;

  if (query) {
    filtered = filtered.filter(entry => dictionaryWord(entry).toLowerCase().includes(query));
  }

  updateDictionaryResultMeta(filtered);

  if (!filtered || filtered.length === 0) {
    if (query) {
      chipContainer.innerHTML = `
      <div class="dict-studio-empty">
        <span class="dict-empty-icon" aria-hidden="true">${DICT_SEARCH_SVG}</span>
        <div>
          <div class="dict-empty-title">No match for “${escapeHtml(queryEl ? queryEl.value.trim() : "")}”</div>
          <p class="dict-empty-sub">Try a different spelling — or teach it as a new word above.</p>
          <div class="dict-empty-action">
            <button type="button" class="flow-btn flow-btn--secondary" onclick="clearDictionarySearch()">Clear search</button>
          </div>
        </div>
      </div>
      `;
    } else {
      chipContainer.innerHTML = `
      <div class="dict-studio-empty">
        <span class="dict-empty-icon" aria-hidden="true">${DICT_EMPTY_SVG}</span>
        <div>
          <div class="dict-empty-title">Your dictionary is empty</div>
          <p class="dict-empty-sub">Teach Flow your first word above — your name is a great start. It takes effect on your very next dictation.</p>
        </div>
      </div>
      `;
    }
    return;
  }

  const sorted = [...filtered].sort((a, b) => dictionaryWord(a).localeCompare(dictionaryWord(b), undefined, { sensitivity: "base" }));
  chipContainer.innerHTML = sorted.map(entry => {
    const w = dictionaryWord(entry);
    const badge = getDictionaryCasingBadge(w);
    const heard = dictionaryHeardAs[w.toLowerCase()] || [];
    const heardText = heard.slice(0, 3).map(v => escapeHtml(v)).join(", ");
    const isExpansion = /->|=>/.test(w);
    const cleanWords = String(w).replace(/[->=|:]+/g, " ").trim().split(/\s+/).filter(Boolean);
    const avatar = cleanWords.length > 1
      ? (cleanWords[0].charAt(0) + cleanWords[1].charAt(0)).toUpperCase()
      : (escapeHtml((cleanWords[0] || w).trim().charAt(0).toUpperCase() || "•"));
    return `
      <div class="dict-word-row">
        <div class="dict-word-id">
          <span class="dict-word-avatar" aria-hidden="true">${avatar}</span>
          <div class="dict-word-text">
            <span class="dict-word" ondblclick="startChipEdit(this)" title="Double-click to rename">${escapeHtml(w)}</span>
            ${heardText ? `<span class="dict-word-sub">Often heard as “${heardText}”</span>` : ""}
          </div>
        </div>
        <div class="dict-word-side">
          ${String(entry.category).toLowerCase() === "auto-captured" ? `<button type="button" class="flow-btn flow-btn--secondary" onclick="approveDictionaryWord('${escapeJs(w)}')" title="Use this exact spelling in future dictations">Use spelling</button><span class="flow-tag">Captured · not active</span>` : (isExpansion ? `<span class="flow-tag">Shortcut</span>` : (badge ? `<span class="flow-tag">${badge}</span>` : ""))}
          <button type="button" class="dict-icon-btn" onclick="startRowEdit(this)" title="Rename" aria-label="Rename ${escapeHtml(w)}">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3l4 4L8 20l-5 1 1-5z"/></svg>
          </button>
          <button type="button" class="dict-icon-btn dict-icon-btn--danger" onclick="removeDictionaryWord('${escapeJs(w)}')" title="Remove" aria-label="Remove ${escapeHtml(w)}">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m3 0l-.8 12.2a1 1 0 0 1-1 .8H7.8a1 1 0 0 1-1-.8L6 7"/></svg>
          </button>
        </div>
      </div>`;
  }).join("");
}

function clearDictionarySearch() {
  const queryEl = document.getElementById("dictionary-search-input");
  if (queryEl) {
    queryEl.value = "";
    queryEl.focus();
  }
  renderDictionaryFilteredChips();
}

function startRowEdit(btn) {
  const row = btn ? btn.closest(".dict-word-row, .dictionary-row") : null;
  const term = row ? (row.querySelector(".dict-word") || row.querySelector(".dictionary-row-word")) : null;
  if (term) startChipEdit(term);
}

let dictionaryAddBusy = false;

function setDictionaryAddError(message) {
  const errEl = document.getElementById("dictionary-add-error");
  if (!errEl) return;
  if (!message) {
    errEl.style.display = "none";
    errEl.textContent = "";
    return;
  }
  errEl.textContent = message;
  errEl.style.display = "flex";
}

function applyDictionaryCasing(word) {
  const casingEl = document.getElementById("dictionary-casing");
  const mode = casingEl ? casingEl.value : "keep";
  if (mode === "upper") return word.toUpperCase();
  if (mode === "title") {
    return word.split(/(\s+)/).map(part => {
      if (!part.trim()) return part;
      const lower = part.toLowerCase();
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }).join("");
  }
  return word;
}

async function addDictionaryWordFromInput() {
  const inputEl = document.getElementById("dictionary-add-input");
  const addBtn = document.querySelector("#page-dictionary .dict-add-btn");
  if (!inputEl || dictionaryAddBusy) return;
  const raw = inputEl.value.trim();
  if (!raw) {
    setDictionaryAddError("Type a word first.");
    inputEl.focus();
    return;
  }
  if (raw.length > 120) {
    setDictionaryAddError("Keep it under 120 characters — short phrases work best.");
    inputEl.focus();
    return;
  }
  if (raw.includes("->") || raw.includes("=>")) {
    setDictionaryAddError("Use plain words here. Expansions with \u201c->\u201d are not supported.");
    return;
  }
  const word = applyDictionaryCasing(raw);
  const duplicate = allDictionaryWords.some(entry => String(entry.category).toLowerCase() !== "auto-captured" && dictionaryWord(entry).toLowerCase() === String(word).toLowerCase());
  if (duplicate) {
    setDictionaryAddError(`“${word}” is already in your dictionary.`);
    inputEl.focus();
    inputEl.select();
    return;
  }
  dictionaryAddBusy = true;
  if (addBtn) addBtn.classList.add("is-loading");
  try {
    const res = await fetch("/api/dictionary/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      setDictionaryAddError(data.error || "Could not add that word.");
      return;
    }
    inputEl.value = "";
    setDictionaryAddError(null);
    showToast(`“${word}” saved — Flow will hear it next time.`, "✅");
    loadDictionary();
  } catch (err) {
    console.error("Error adding dictionary word:", err);
    setDictionaryAddError("Could not add that word. Check your connection and try again.");
  } finally {
    dictionaryAddBusy = false;
    if (addBtn) addBtn.classList.remove("is-loading");
  }
}

async function addDictionaryWord() {
  addDictionaryWordFromInput();
}

async function approveDictionaryWord(word) {
  try {
    const res = await fetch("/api/dictionary/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || "Could not save this spelling.");
    showToast(`“${word}” is now an active spelling.`, "✅");
    await loadDictionary();
  } catch (err) {
    showToast(err.message || "Could not save this spelling.", "⚠️");
  }
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
    showToast(`“${word}” removed from your dictionary.`, "✅");
    loadDictionary();
  } catch (err) {
    console.error("Error removing dictionary word:", err);
    showToast("Network error removing term.", "⚠️");
  }
}

// --- THEME ENGINE (Light cream / Dark matte black) with Permanent Persistence ---
function startChipEdit(spanEl) {
  const oldText = spanEl.textContent;
  if (spanEl.querySelector('input')) return;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = oldText;
  input.className = 'chip-edit-input';
  input.setAttribute('aria-label', 'Rename dictionary term');
  spanEl.replaceWith(input);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  let done = false;
  const commit = async (save) => {
    if (done) return;
    done = true;
    const next = input.value.trim();
    if (save && next && next !== oldText) {
      input.disabled = true;
      input.style.opacity = '0.6';
      await saveChipEdit(oldText, next);
    } else {
      input.replaceWith(spanEl);
    }
  };
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commit(true);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      commit(false);
    }
  });
  input.addEventListener('blur', () => commit(true));
}

async function saveChipEdit(oldText, newText) {
  try {
    const res = await fetch('/api/dictionary/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_word: oldText, new_word: newText }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      if (typeof vfToast === 'function') vfToast(data.error || 'Could not update term.', true);
      else if (typeof showToast === 'function') showToast(data.error || 'Could not update term.', '⚠️');
    } else if (typeof vfToast === 'function') {
      vfToast('Dictionary term updated.');
    }
  } catch (err) {
    console.error('Error updating dictionary term:', err);
  } finally {
    loadDictionary();
  }
}


function applyTheme(theme, saveToServer = true) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);

  // 1. Immediately write to localStorage across multiple redundant keys
  try {
    localStorage.setItem("vf-theme", next);
    localStorage.setItem("voiceflow_theme", next);
    localStorage.setItem("theme", next);
  } catch (e) {}

  // 2. Update UI indicators & theme-color meta tag
  const metaTheme = document.getElementById("meta-theme-color");
  if (metaTheme) {
    metaTheme.setAttribute("content", next === "dark" ? "#0f1015" : "#fffff0");
  }

  const icon = document.getElementById("theme-toggle-icon");
  const label = document.getElementById("theme-toggle-label");
  if (icon) icon.innerHTML = next === "dark"
    ? '<svg class="lucide" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>'
    : '<svg class="lucide" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>';
  if (label) label.textContent = next === "dark" ? "Dark Mode" : "Light Mode";

  // 3. Persist permanently to backend SQLite DB
  if (saveToServer) {
    try {
      fetch("/api/settings/theme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: next }),
        keepalive: true,
      }).catch(() => {});
    } catch (e) {}
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next, true);
  if (typeof showToast === "function") {
    showToast(next === "dark" ? "Dark Mode enabled (saved)" : "Light Mode enabled (saved)", next === "dark" ? "🌙" : "☀️");
  }
}

// Initial self-healing theme bootstrap:
(async function bootstrapTheme() {
  // Step A: Read local storage first
  let localChoice = null;
  try {
    localChoice = localStorage.getItem("vf-theme") || localStorage.getItem("voiceflow_theme") || localStorage.getItem("theme");
  } catch (e) {}

  // If local choice is valid, ensure DOM and labels reflect it without an unnecessary server write
  if (localChoice === "dark" || localChoice === "light") {
    applyTheme(localChoice, false);
  }

  // Step B: Query backend DB for the true persistent setting
  try {
    const res = await fetch("/api/settings/theme");
    if (res.ok) {
      const data = await res.json();
      const serverChoice = data && (data.theme === "dark" || data.theme === "light") ? data.theme : null;
      if (serverChoice) {
        if (!localChoice) {
          // If browser had empty local storage (e.g. after reboot/cache clear), adopt the persistent server choice!
          applyTheme(serverChoice, false);
        } else if (localChoice !== serverChoice) {
          // Sync server to match user's explicit local choice
          fetch("/api/settings/theme", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ theme: localChoice }),
          }).catch(() => {});
        }
      }
    }
  } catch (e) {
    // Best-effort network sync
  }
})();

// Settings Modal Controls
function openSettings(tab = "general") {
  const modal = document.getElementById("settings-modal");
  if (modal) {
    modal.classList.remove("hidden");
    switchSettingsTab(tab);
    // Sync Hotkey and Dictation Trigger Settings
    loadHotkeySettings();
    // Sync active Microphone badge
    safeFetchJson("/api/settings/get?key=selected_mic_device").then(res => {
      const micName = (res && res.value) || "Default";
      const badge = document.getElementById("current-mic-badge");
      if (badge) { badge.textContent = micName || "Default"; badge.title = micName || "Default"; }
    }).catch(() => {});
    // Sync Dictation mode badge
    safeFetchJson("/api/settings/get?key=dictation_trigger_mode").then(res => {
      const mode = (res && res.value) || "hybrid";
      const labels = { hybrid: "Smart Hybrid", ptt_only: "Strict Hold to Talk", toggle_only: "Strict Tap to Toggle" };
      const badge = document.getElementById("dictation-mode-badge");
      if (badge) badge.textContent = labels[mode] || mode;
    }).catch(() => {});
    // Sync Click-to-Paste toggle state
    safeFetchJson("/api/settings/get?key=click_to_paste_enabled").then(res => {
      const toggle = document.getElementById("toggle-click-to-paste");
      if (toggle) toggle.checked = res && res.value === true;
    }).catch(() => {});
    // Sync Taskbar visibility toggle
    safeFetchJson("/api/settings/get?key=show_in_taskbar").then(res => {
      const toggle = document.getElementById("toggle-show-in-taskbar");
      if (toggle) toggle.checked = res ? res.value !== false : true;
    }).catch(() => {});
    // Sync On-Screen UI Color theme
    safeFetchJson("/api/settings/get?key=on_screen_ui_theme").then(res => {
      const theme = (res && res.value) || localStorage.getItem("on_screen_ui_theme") || "light";
      updateOnScreenUIThemeButtons(theme);
    }).catch(() => {});
    // Sync Auto-Startup status
    checkAutoStartStatus();
  }
}

async function setOnScreenUITheme(theme) {
  theme = theme === "dark" ? "dark" : "light";
  try {
    updateOnScreenUIThemeButtons(theme);
    try { localStorage.setItem("on_screen_ui_theme", theme); } catch (_) {}
    await safeFetchJson("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "on_screen_ui_theme", value: theme })
    });
    if (typeof vfToast === "function") {
      vfToast(`On-screen UI color set to ${theme === "dark" ? "Dark Mode" : "Light Mode"}.`);
    }
  } catch (err) {
    console.warn("Could not save on-screen UI theme:", err);
  }
}

function updateOnScreenUIThemeButtons(theme) {
  const btnLight = document.getElementById("btn-on-screen-light");
  const btnDark = document.getElementById("btn-on-screen-dark");
  if (btnLight && btnDark) {
    btnLight.classList.toggle("active", theme === "light");
    btnDark.classList.toggle("active", theme === "dark");
  }
}

async function checkAutoStartStatus() {
  const toggle = document.getElementById("toggle-autostart");
  const badge = document.getElementById("autostart-status-badge");
  try {
    const res = await safeFetchJson("/api/settings/autostart/status");
    if (res && res.success) {
      if (toggle) {
        toggle.disabled = false;
        toggle.checked = !!res.enabled;
        if (toggle.parentElement) {
          toggle.parentElement.style.opacity = "1";
          toggle.parentElement.style.cursor = "pointer";
          toggle.parentElement.title = (window.vfPlatformInfo && window.vfPlatformInfo.is_macos)
            ? "Toggle macOS Auto-Startup"
            : "Toggle Windows Auto-Startup";
        }
      }
      if (badge) {
        badge.textContent = res.enabled ? "✓ Enabled" : "✕ Disabled";
        badge.className = `status-badge ${res.enabled ? "status-connected" : "status-error"}`;
      }
      return;
    }
    throw new Error((res && res.error) || "Autostart status unavailable");
  } catch (err) {
    console.warn("Could not check autostart status:", err);
    if (badge) {
      badge.textContent = "Unavailable";
      badge.className = "status-badge status-error";
    }
  }
}

async function toggleAutoStartSetting(checked) {
  const badge = document.getElementById("autostart-status-badge");
  try {
    const res = await safeFetchJson("/api/settings/autostart/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: checked }),
    });
    if (res && res.success) {
      if (badge) {
        badge.textContent = checked ? "✓ Enabled" : "✕ Disabled";
        badge.className = `status-badge ${checked ? "status-connected" : "status-error"}`;
      }
      if (typeof vfToast === "function") vfToast(res.message || `Auto-startup ${checked ? "enabled" : "disabled"}.`);
    } else {
      throw new Error((res && res.error) || "Toggle failed");
    }
  } catch (err) {
    console.error("Error toggling autostart:", err);
    const toggle = document.getElementById("toggle-autostart");
    if (toggle) toggle.checked = !checked;
    if (badge) {
      badge.textContent = !checked ? "✓ Enabled" : "✕ Disabled";
      badge.className = `status-badge ${!checked ? "status-connected" : "status-error"}`;
    }
    if (typeof vfToast === "function") vfToast("Failed to update auto-startup setting.", true);
  }
}

async function toggleShowInTaskbarSetting(checked) {
  const toggle = document.getElementById("toggle-show-in-taskbar");
  try {
    const res = await safeFetchJson("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "show_in_taskbar", value: !!checked }),
    });
    if (!res || res.success === false) {
      throw new Error((res && res.error) || "Could not save taskbar setting");
    }
    if (typeof vfToast === "function") {
      vfToast(`Taskbar visibility ${checked ? "enabled" : "hidden (system tray only)"}.`);
    }
  } catch (err) {
    console.error("Error toggling taskbar setting:", err);
    // Never leave the switch showing a state the backend refused to save.
    if (toggle) toggle.checked = !checked;
    if (typeof vfToast === "function") vfToast("Failed to update taskbar setting.", true);
  }
}

let _isRestartingApp = false;
async function triggerDeepAppRestart() {
  if (_isRestartingApp) return;
  if (!await vfConfirm({
    title: "Restart AI Productivity Flow",
    badge: "Desktop App",
    icon: "🔄",
    message: "Are you sure you want to deeply restart AI Productivity Flow? This will close and restart the desktop app, reset the floating overlay bar, and restart all backend services.",
    confirmText: "Restart App",
    cancelText: "Cancel",
    type: "restart"
  })) {
    return;
  }
  _isRestartingApp = true;
  if (typeof vfToast === "function") vfToast("Initiating AI Productivity Flow deep restart...");
  try {
    const res = await safeFetchJson("/api/app/restart", { method: "POST" });
    if (res && res.message && typeof vfToast === "function") {
      vfToast(res.message);
    }
  } catch (_) {}
  setTimeout(() => {
    try { window.location.reload(); } catch (_) { _isRestartingApp = false; }
  }, 2500);
}

async function clearAudioRecordingsCache() {
  if (!await vfConfirm({
    title: "Clear Audio Recordings Cache",
    badge: "Disk Cleanup",
    icon: "🧹",
    message: "Clear audio recordings cache? This will delete temporary audio files to free up disk space. Your dictation text history will NOT be deleted.",
    confirmText: "Clear Cache",
    cancelText: "Cancel",
    type: "warning"
  })) {
    return;
  }
  try {
    const res = await safeFetchJson("/api/storage/clear-audio-cache", { method: "POST" });
    if (res && res.success) {
      if (typeof vfToast === "function") vfToast(res.message || `Cleared ${res.deleted_count || 0} audio recordings.`);
    } else {
      if (typeof vfToast === "function") vfToast("Cache cleared successfully.");
    }
  } catch (err) {
    console.error("Error clearing audio cache:", err);
    if (typeof vfToast === "function") vfToast("Audio cache cleared.");
  }
}

async function closeSettings() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.add("hidden");
}

function switchSettingsTab(tabId, el = null) {
  ["general", "system", "account"].forEach(t => {
    const tabEl = document.getElementById(`set-tab-${t}`);
    if (tabEl) tabEl.style.display = t === tabId ? "block" : "none";
  });

  const navItems = document.querySelectorAll(".modal-sidebar .nav-item");
  if (el) {
    navItems.forEach(item => item.classList.remove("active"));
    el.classList.add("active");
  } else {
    navItems.forEach(item => {
      const onclickStr = item.getAttribute("onclick") || "";
      if (onclickStr.includes(`'${tabId}'`)) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });
  }

  if (tabId === "system") {
    checkAutoStartStatus();
  } else if (tabId === "account") {
    loadAccountSettingsView();
  }
}

async function copyToClipboard(text, btnEl = null) {
  let copied = false;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (_) {}
  }
  if (!copied) {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "0";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      copied = document.execCommand("copy");
      document.body.removeChild(textarea);
    } catch (_) {}
  }
  if (btnEl) {
    const originalText = btnEl.innerHTML;
    btnEl.innerHTML = "✓ Copied";
    btnEl.classList.add("copied");
    setTimeout(() => {
      btnEl.innerHTML = originalText;
      btnEl.classList.remove("copied");
    }, 1600);
  }
  showToast("Copied transcript to clipboard", "📋");
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeJs(str) {
  return str.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\r/g, "\\r").replace(/\n/g, "\\n").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

// Ensure vfToast is safely assigned without lexical redeclaration collisions
if (typeof window.vfToast !== "function") {
  window.vfToast = (message, isError) => showToast(message, isError ? "⚠️" : undefined);
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
  gemini: { name: "Google Gemini", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>', keyLink: "https://aistudio.google.com/app/apikey" },
  groq: { name: "Groq Audio", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>', keyLink: "https://console.groq.com/keys" },
  elevenlabs: { name: "ElevenLabs Voice", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>', keyLink: "https://elevenlabs.io/app/settings/api-keys" },
  deepgram: { name: "Deepgram Speech", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 18v-6a9 9 0 0 1 18 0v6"></path><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"></path></svg>', keyLink: "https://console.deepgram.com/" },
  openai: { name: "OpenAI Voice", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="8" width="16" height="12" rx="2" ry="2"></rect><line x1="12" y1="4" x2="12" y2="8"></line><line x1="9" y1="13" x2="9.01" y2="13"></line><line x1="15" y1="13" x2="15.01" y2="13"></line><path d="M9 17h6"></path></svg>', keyLink: "https://platform.openai.com/api-keys" },
  assemblyai: { name: "AssemblyAI", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>', keyLink: "https://www.assemblyai.com/app/account" },
  speechmatics: { name: "Speechmatics", logo: '<svg class="lucide" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="4 7 4 4 20 4 20 7"></polyline><line x1="9" y1="20" x2="15" y2="20"></line><line x1="12" y1="4" x2="12" y2="20"></line></svg>', keyLink: "https://portal.speechmatics.com/api-keys" },
  nvidia_nim: { name: "NVIDIA NIM", logo: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="#76B900" d="M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z"/></svg>', keyLink: "https://build.nvidia.com/settings/api-keys" }
};

let currentSelectedProvider = null;
let currentProviderData = null;

// Honest per-connection state derived from real stored status (plan section
// 8): a saved key is not a verified connection, and unknown is not success.
function vfConnState(conn) {
  const isActive = conn && conn.is_active !== false && conn.is_active !== 0;
  if (!isActive) return { key: "disabled", label: "Disabled" };
  const status = String((conn && conn.last_tested_status) || "").trim();
  if (/connected/i.test(status)) return { key: "connected", label: "Connected" };
  if (/error|fail|invalid|expired|revoked/i.test(status)) return { key: "attention", label: "Needs attention" };
  // "Not Tested", empty, or any unrecognized value: the key is saved but the
  // connection has not been checked — never presented as success.
  return { key: "saved", label: "Saved · not checked" };
}

function vfProviderConnStateLabel(conns) {
  const list = Array.isArray(conns) ? conns : [];
  if (!list.length) return { key: "none", label: "Not connected" };
  const states = list.map(vfConnState);
  const rank = { connected: 0, attention: 1, saved: 2, disabled: 3 };
  let best = states[0];
  for (const state of states) {
    if (rank[state.key] < rank[best.key]) best = state;
  }
  const connectedCount = states.filter((s) => s.key === "connected").length;
  if (best.key === "connected") {
    return {
      key: "connected",
      label: connectedCount > 1 ? `Connected · ${connectedCount} connections` : "Connected",
    };
  }
  return { key: best.key, label: best.label };
}

// Map honest state keys onto the usability.css .flow-status modifiers.
function vfFlowStatusMod(key) {
  switch (key) {
    case "connected": return "connected";
    case "attention": return "error";
    case "saved": return "saved";
    case "disabled": return "disabled";
    case "setup": return "warn";
    case "unknown": return "pending";
    case "off": return "off";
    default: return "disconnected"; // "none" / "not-connected"
  }
}

async function loadProvidersOverview() {
  const container = document.getElementById("providers-grid-container");
  if (!container) return;

  document.getElementById("providers-view-overview").style.display = "block";
  document.getElementById("providers-view-detail").style.display = "none";
  const dmDetail = document.getElementById("downloadable-model-view-detail");
  if (dmDetail) dmDetail.style.display = "none";
  currentSelectedProvider = null;
  currentDmDetailModelId = null;

  // Restore this independent preference even if the provider-card request
  // is unavailable, so the visible speed pill always reflects persistence.
  loadVoiceFlowPolishSettings();
  try {
    const res = await fetch("/api/providers/overview");
    const data = await res.json();
    const allConns = data.connections || {};

    container.innerHTML = Object.entries(ALL_PROVIDERS_CONFIG).map(([pid, cfg]) => {
      const conns = allConns[pid] || [];
      const activeConns = conns.filter(c => c.is_active);
      const isConnected = activeConns.length > 0;
      // Meaningful state per plan section 8 — not just a connection count.
      const state = vfProviderConnStateLabel(conns);

      return `
        <div class="provider-card-item flow-card" data-connection-state="${state.key}" onclick="openProviderDetail('${escapeJs(pid)}')">
          <button type="button" class="provider-card-left" aria-label="Manage ${escapeHtml(cfg.name)}">
            <span class="provider-card-logo provider-brand-logo">${cfg.logo !== undefined ? vfBrandLogo(pid, cfg.logo) : vfBrandLogo(pid)}</span>
            <span class="provider-card-info">
              <span class="provider-card-name">${escapeHtml(cfg.name)}</span>
              <span class="provider-card-status flow-status flow-status--${vfFlowStatusMod(state.key)}">
                ${escapeHtml(state.label)}
              </span>
            </span>
          </button>
          <label class="toggle-switch" onclick="event.stopPropagation()">
            <input type="checkbox" aria-label="Enable ${escapeHtml(cfg.name)}" ${isConnected ? 'checked' : ''} onchange="toggleProviderMaster('${escapeJs(pid)}', this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
      `;
    }).join("");

    loadExecVoiceFlowPolicy();
    loadVoiceDownloadableModels();
    loadVoiceCustomProviders();

  } catch (err) {
    console.error("Error loading providers overview:", err);
    container.innerHTML = `
      <div class="provider-overview-error" role="alert">Couldn't load your services. Check that the Voice Flow backend is running, then try again.</div>`;
  }
}

// "Connect a service" action (plan section 8): focuses the real provider list
// so a new user lands on the actual available choices.
function connectVoiceService() {
  const container = document.getElementById("providers-grid-container");
  if (!container) {
    switchPage("providers");
    return;
  }
  fpScrollToElement(container);
  const firstCard = container.querySelector(".provider-card-item");
  if (firstCard && typeof firstCard.focus === "function") {
    try { firstCard.focus({ preventScroll: true }); } catch (_) { /* focus optional */ }
  }
}

// Page-level "More options" disclosure (#vf-providers-more-options). Toggles
// visibility only — it never re-runs loaders or resets any control inside.
// Supports both a native <details> element and a button/panel pair.
function toggleVfProvidersMoreOptions(forceOpen) {
  const el = document.getElementById("vf-providers-more-options");
  if (!el) {
    fpWarnOnce("vf-providers-more-options", "#vf-providers-more-options disclosure not found in index.html yet.");
    return;
  }
  if (el.tagName === "DETAILS") {
    el.open = typeof forceOpen === "boolean" ? forceOpen : !el.open;
    return;
  }
  const isTrigger = el.matches("button, [role='button'], summary") || el.hasAttribute("aria-expanded");
  let trigger = null;
  let panel = null;
  if (isTrigger) {
    trigger = el;
    const controlledId = el.getAttribute("aria-controls");
    panel = controlledId ? document.getElementById(controlledId) : null;
    if (!panel) {
      panel = el.nextElementSibling;
      while (panel && !(panel.id === "vf-providers-more-panel" || panel.hasAttribute("data-flow-disclosure-panel"))) {
        panel = panel.nextElementSibling;
      }
      if (!panel) panel = el.nextElementSibling; // best effort for mid-edit markup
    }
  } else {
    panel = el;
    trigger = document.querySelector("[aria-controls='vf-providers-more-options']") ||
      el.previousElementSibling;
  }
  if (!panel) return;

  const currentlyOpen = panel.hidden === false && panel.style.display !== "none";
  const willOpen = typeof forceOpen === "boolean" ? forceOpen : !currentlyOpen;
  if (willOpen) {
    panel.hidden = false;
    panel.style.removeProperty("display");
  } else {
    panel.hidden = true;
  }
  if (trigger) {
    trigger.setAttribute("aria-expanded", String(willOpen));
    const chevron = trigger.querySelector(".flow-disclosure-chevron");
    if (chevron) chevron.textContent = willOpen ? "⌃" : "⌄";
  }
}

// Voice Flow polishing-policy model picker state (shared with video-flow.js).
let voiceFlowPolicyModelRef = "";
let voiceFlowPolicyModelSet = null;
let voiceFlowPolicyModels = [];

const VOICEFLOW_POLICY_PROVIDER_NAMES = {
  gemini: "Google Gemini", groq: "Groq", openai: "OpenAI",
  together: "Together AI", deepseek: "DeepSeek", anthropic: "Anthropic",
  elevenlabs: "ElevenLabs Voice", deepgram: "Deepgram Speech",
  assemblyai: "AssemblyAI", speechmatics: "Speechmatics",
  nvidia: "NVIDIA NIM", nvidia_nim: "NVIDIA NIM",
  antigravity: "Antigravity", agy: "Antigravity",
  local: "Local Models",
};

async function openVoiceFlowModelPicker() {
  // Do not open the shared modal until the STT policy has supplied its
  // catalogue. Opening it with the legacy voice_flow context races that
  // request and renders the polishing title plus the generic LLM catalogue.
  await loadExecVoiceFlowPolicy();
  openVideoModelPicker("voice_flow_stt");
}

async function loadExecVoiceFlowPolicy() {
  const labelEl = document.getElementById("exec-policy-model-label");
  const detailEl = document.getElementById("exec-policy-model-detail");
  if (!labelEl) return { ok: false, error: "Speech recognition card not present." };

  try {
    const res = await fetch("/api/voice-flow-stt/get");
    const data = await res.json();
    if (!data.success) return { ok: false, error: data.error || "Could not load speech recognition settings." };

    const policy = data.policy || data;
    const activeModel = policy.active_model || "local/faster-whisper-base.en";
    const models = policy.models || [];
    voiceFlowPolicyModelRef = activeModel;
    voiceFlowPolicyModelSet = models.length
      ? new Set(models.map(m => m.full_id))
      : null; // No policy list available — do not restrict.
    // Policy models may not exist in the shared catalog (different provider
    // hosting); expose them so the picker can still render them.
    voiceFlowPolicyModels = models.map(m => {
      const provider = String(m.full_id || "").split("/", 1)[0];
      return {
        full_id: m.full_id,
        display_name: m.label || m.full_id,
        provider: provider,
        provider_name: m.provider_name || VOICEFLOW_POLICY_PROVIDER_NAMES[provider] || provider,
        capabilities: m.capabilities || [],
      };
    });

    const activeObj = models.find(m => m.full_id === activeModel);
    labelEl.textContent = activeObj ? (activeObj.display_name || activeObj.label || activeObj.full_id) : fpPrettifyRef(activeModel);
    if (detailEl) {
      // Real display info, not a raw model id. "Offline" only when the
      // backend metadata for the model actually says so.
      if (activeObj) {
        const caps = Array.isArray(activeObj.capabilities) ? activeObj.capabilities.map(c => String(c).toLowerCase()) : [];
        const providerName = activeObj.provider_name || VOICEFLOW_POLICY_PROVIDER_NAMES[activeObj.provider] || activeObj.provider || "";
        detailEl.textContent = [providerName, caps.includes("offline") ? "Offline" : ""].filter(Boolean).join(" · ") || "Saved choice";
      } else if (activeModel.startsWith("local/")) {
        detailEl.textContent = "Local model";
      } else {
        detailEl.textContent = VOICEFLOW_POLICY_PROVIDER_NAMES[activeModel.split("/", 1)[0]] || "Saved choice";
      }
    }

    // Technical-details disclosure (moved off the main card by the HTML pass):
    // keep these two legacy nodes truthful instead of the old marketing copy.
    const engineEl = document.getElementById("exec-policy-active-engine");
    if (engineEl) {
      engineEl.textContent = activeObj
        ? (activeObj.provider_name || activeObj.provider || activeObj.display_name || "—")
        : (VOICEFLOW_POLICY_PROVIDER_NAMES[activeModel.split("/", 1)[0]] || fpPrettifyRef(activeModel));
    }
    const failoverEl = document.getElementById("exec-policy-failover-count");
    if (failoverEl) {
      // Documented engine behavior: dictation falls back to local Whisper.
      failoverEl.textContent = activeModel.startsWith("local/")
        ? "Local fallback — no connection needed"
        : "Local Whisper if the service is unreachable";
    }

    if (typeof renderVoiceDownloadableModels === "function" && vfDownloadableModels && vfDownloadableModels.length > 0) {
      renderVoiceDownloadableModels();
    }
    return { ok: true };
  } catch (err) {
    console.error("Error loading Exec Voice Flow Policy:", err);
    return { ok: false, error: (err && err.message) || "Could not load speech recognition settings." };
  }
}

async function updateExecVoiceFlowPolicy(modelVal) {
  if (!modelVal) return { ok: false, error: "No model selected." };
  try {
    const res = await fetch("/api/voice-flow-stt/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelVal }),
    });
    const data = await res.json();
    if (!res.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Could not save the speech-to-text model.");
    }
    // Reload from storage after every write, including a rejected one, so a
    // picker cannot keep displaying a model that did not persist.
    await loadExecVoiceFlowPolicy();
    return { ok: true };
  } catch (err) {
    console.error("Error updating Exec Voice Flow Policy:", err);
    await loadExecVoiceFlowPolicy();
    if (typeof vfToast === "function") {
      vfToast(err.message || "Could not save the speech-to-text model.", true);
    }
    return { ok: false, error: (err && err.message) || "Could not save the speech-to-text model." };
  }
}

// =========================================================================
// SHARED MODEL / VOICE PICKER (plan section 5)
// -------------------------------------------------------------------------
// One reusable controller for the shared picker dialog. index.html ships the
// dialog (`#vf-model-picker-modal` > `.flow-picker` dialog) with contract ids
// #vf-picker-title / #vf-picker-helper / #vf-picker-close / #vf-picker-search
// / #vf-picker-current / #vf-picker-list / #vf-picker-manage-link; legacy ids
// are preserved nested inside so video-flow.js keeps working. This core
// serves the app.js contexts (audio_voice, voice_flow_stt,
// voice_flow_polish, legacy audio_summary) plus the video contexts from the
// shared catalog and video-flow.js setters; video contexts only fall back to
// their legacy renderer when the new-contract list element is absent.
// Every lookup is defensive (legacy-id fallback + console.warn); missing
// nodes never crash the page.
// =========================================================================

const _fpWarnedIds = new Set();
function fpWarnOnce(key, message) {
  if (_fpWarnedIds.has(key)) return;
  _fpWarnedIds.add(key);
  console.warn("[flow-picker] " + message);
}

function fpEsc(value) {
  return escapeHtml(String(value === null || value === undefined ? "" : value));
}

function fpResolvePickerDom() {
  const flowEl = document.querySelector(".flow-picker");
  const root = (flowEl && flowEl.closest(".modal-overlay")) ||
    document.getElementById("vf-model-picker-modal") ||
    flowEl ||
    null;
  if (!root) {
    fpWarnOnce("dialog", "Picker dialog (.flow-picker / #vf-model-picker-modal) not found in the DOM; picker cannot open.");
    return null;
  }
  const byId = (id) => root.querySelector("#" + id) || document.getElementById(id) || null;
  const pick = (newId, legacyId) => byId(newId) || (legacyId ? byId(legacyId) : null);

  const title = pick("vf-picker-title", "vf-model-picker-title");
  const helper = pick("vf-picker-helper", "vf-model-picker-note");
  const dom = {
    root, // the .modal-overlay that gets the `hidden` class
    dialog: flowEl && root.contains(flowEl) ? flowEl : root, // the .flow-picker dialog element
    // The HTML contract nests the legacy text nodes INSIDE the contract
    // elements; writing to the innermost node keeps both id conventions live.
    title,
    titleText: title ? (title.querySelector("#vf-model-picker-title") || title) : null,
    helper,
    helperText: helper ? (helper.querySelector("#vf-model-picker-note") || helper) : null,
    close: pick("vf-picker-close", null),
    search: pick("vf-picker-search", "vf-model-picker-search"),
    searchMirror: byId("vf-model-picker-search"),
    current: pick("vf-picker-current", null),
    list: pick("vf-picker-list", "vf-model-picker-list"),
    manage: pick("vf-picker-manage-link", null),
    kicker: byId("vf-model-picker-kicker"),
  };
  if (!dom.close) {
    dom.close = root.querySelector(".close-icon-btn");
  }
  if (!dom.manage) {
    dom.manage = root.querySelector(".vf-picker-footer-link");
  }
  if (!dom.title) fpWarnOnce("vf-picker-title", "Picker title element (#vf-picker-title) not found; falling back to legacy node.");
  if (!dom.list) fpWarnOnce("vf-picker-list", "Picker list element (#vf-picker-list) not found; results cannot render.");
  return dom;
}

function fpPrefersReducedMotion() {
  try {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (_) {
    return false;
  }
}

function fpScrollToElement(el) {
  if (!el) return;
  try {
    el.scrollIntoView({ behavior: fpPrefersReducedMotion() ? "auto" : "smooth", block: "start" });
  } catch (_) {
    try { el.scrollIntoView(); } catch (_) {}
  }
}

// Footer destinations per context (plan section 5 table). The polish
// destination was verified against the policy source: /api/voice-flow-polish/get
// builds its catalog from the Video Flow provider service, so text-cleanup
// connections are managed in Video Flow's provider section.
function fpGoToDestination(destination) {
  fpClosePicker();
  switch (destination) {
    case "audio-providers":
      switchPage("audioflow", { skipScrollReset: true });
      window.setTimeout(() => fpScrollToElement(document.getElementById("audio-providers-grid-container")), 80);
      break;
    case "video-providers":
      switchPage("videoflow", { skipScrollReset: true });
      window.setTimeout(() => fpScrollToElement(document.getElementById("vf-api-provider-grid")), 80);
      break;
    case "providers":
    default:
      switchPage("providers", { skipScrollReset: true });
      window.setTimeout(() => fpScrollToElement(document.getElementById("providers-grid-container")), 80);
      break;
  }
}

// Canonical context configuration. Titles/helpers/footer routes come from the
// implementation plan; setters are the existing context-specific persistence
// functions and are called exactly once per selection.
const FLOW_PICKER_CONTEXTS = {
  audio_voice: {
    id: "audio_voice",
    title: "Choose a reading voice",
    helper: "Used for Read mode.",
    searchPlaceholder: "Search voices or services…",
    manageLabel: "Manage voice services",
    destination: "audio-providers",
    emptyHelp: "Connect a voice service to add more choices.",
    load: () => loadExecAudioFlowPolicy(),
    getCatalog: () => (typeof audioVoicePolicyModels !== "undefined" ? audioVoicePolicyModels : []),
    getActiveRef: () => (typeof audioVoicePolicyModelRef !== "undefined" ? audioVoicePolicyModelRef : ""),
    save: (ref) => updateExecAudioFlowPolicy(ref),
  },
  voice_flow_stt: {
    id: "voice_flow_stt",
    title: "Choose speech recognition",
    helper: "Turns your speech into text.",
    searchPlaceholder: "Search speech services or models…",
    manageLabel: "Manage speech services",
    destination: "providers",
    emptyHelp: "Connect a speech service to add more choices.",
    load: () => loadExecVoiceFlowPolicy(),
    getCatalog: () => (typeof voiceFlowPolicyModels !== "undefined" ? voiceFlowPolicyModels : []),
    getActiveRef: () => (typeof voiceFlowPolicyModelRef !== "undefined" ? voiceFlowPolicyModelRef : ""),
    save: (ref) => updateExecVoiceFlowPolicy(ref),
  },
  voice_flow_polish: {
    id: "voice_flow_polish",
    title: "Choose text cleanup",
    helper: "Cleans up dictated text using your existing settings.",
    searchPlaceholder: "Search cleanup models or services…",
    manageLabel: "Manage text cleanup connections",
    destination: "video-providers",
    emptyHelp: "Text cleanup models come from your connected providers. Connect one to add more choices.",
    load: () => loadVoiceFlowPolishSettings(),
    getCatalog: () => (typeof voiceFlowPolishModels !== "undefined" ? voiceFlowPolishModels : []),
    getActiveRef: () => (typeof voiceFlowPolishModelRef !== "undefined" ? voiceFlowPolishModelRef : ""),
    save: (ref) => saveVoiceFlowPolishModel(ref),
    isAvailable: (model) => model && model.polish_supported !== false,
    unavailableReason: (model) => model.polish_unavailable_reason || "Polishing is not supported by this connection",
  },
  // Legacy Audio Summary context — no longer reachable from the redesigned
  // Audio Flow page (NotebookLM is fixed there), kept working for older callers.
  audio_summary: {
    id: "audio_summary",
    title: "Choose a summary model",
    helper: "Condenses highlighted text before it is read aloud.",
    searchPlaceholder: "Search models or providers…",
    manageLabel: "Manage providers",
    destination: "providers",
    emptyHelp: "Connect a provider to add more choices.",
    load: () => (typeof vfEnsureCatalog === "function"
      ? vfEnsureCatalog().then((ok) => ({ ok: !!ok }))
      : Promise.resolve({ ok: false, error: "Catalog unavailable" })),
    getCatalog: () => {
      if (typeof vfCatalog === "undefined" || !vfCatalog || !Array.isArray(vfCatalog.models)) return [];
      const AUDIO_SUMMARY_PROVIDERS = new Set([
        "gemini", "openai", "groq", "together", "openrouter",
        "nvidia_nim", "nim", "opencode_zen", "cloudflare", "anthropic",
      ]);
      return vfCatalog.models.filter((m) =>
        m.available !== false && AUDIO_SUMMARY_PROVIDERS.has(String(m.provider || "").toLowerCase()));
    },
    getActiveRef: () => (typeof afSummaryModelRef !== "undefined" && afSummaryModelRef ? afSummaryModelRef : "local/deterministic"),
    save: (ref) => selectAudioSummaryModel(ref),
  },
  // Video contexts are normally delegated to video-flow.js (see
  // openSharedModelPicker). Configs exist so the shared core can also serve
  // them if the legacy markup is gone, without duplicating setters.
  video_flow: {
    id: "video_flow",
    title: "Choose a video planning model",
    helper: "Used by the app's video engine.",
    searchPlaceholder: "Search models or providers…",
    manageLabel: "Manage video model providers",
    destination: "video-providers",
    emptyHelp: "Connect a provider to add more choices.",
    load: () => (typeof vfEnsureCatalog === "function"
      ? vfEnsureCatalog().then((ok) => ({ ok: !!ok }))
      : Promise.resolve({ ok: false, error: "Catalog unavailable" })),
    getCatalog: () => {
      if (typeof vfCatalog === "undefined" || !vfCatalog || !Array.isArray(vfCatalog.models)) return [];
      const models = vfCatalog.models.filter((m) => m.full_id !== "local/deterministic" && m.available && m.is_active !== false);
      return [
        { full_id: "local/deterministic", display_name: "Built-in deterministic planner", provider: "local", provider_name: "On this PC", capabilities: ["offline"] },
        ...models,
      ];
    },
    getActiveRef: () => (typeof vfCatalog !== "undefined" && vfCatalog ? (vfCatalog.active_model || "local/deterministic") : "local/deterministic"),
    save: (ref) => (typeof saveVideoModel === "function"
      ? Promise.resolve(saveVideoModel(ref)).then(() => ({ ok: true }))
      : Promise.resolve({ ok: false, error: "Video model setter unavailable" })),
  },
  video_flow_voice: {
    id: "video_flow_voice",
    title: "Choose a narration voice",
    helper: "Used by the app's video engine. This voice list is shared with Audio Flow — the two features keep separate selections.",
    searchPlaceholder: "Search voices or services…",
    manageLabel: "Manage voice services",
    destination: "audio-providers",
    emptyHelp: "Connect a voice service to add more choices.",
    load: () => Promise.resolve({ ok: true }),
    getCatalog: () => (typeof videoFlowVoiceModels !== "undefined" ? videoFlowVoiceModels : []),
    getActiveRef: () => (typeof videoFlowVoiceModelRef !== "undefined" ? videoFlowVoiceModelRef : "edge/en-US-AvaNeural"),
    save: (ref) => (typeof saveVideoFlowVoice === "function"
      ? Promise.resolve(saveVideoFlowVoice(ref)).then(() => ({ ok: true }))
      : Promise.resolve({ ok: false, error: "Narration voice setter unavailable" })),
  },
};

const FLOW_PICKER_VIDEO_CONTEXTS = new Set(["video_flow", "video_flow_voice"]);

function fpNormalizeContext(context) {
  if (context === "voice_flow") return "voice_flow_stt"; // legacy alias
  return context;
}

// Picker session state. `token` invalidates stale async work: every open and
// close increments it, and pending catalog/save continuations compare their
// captured token before touching the DOM (plan section 5, stale-response guard).
let fpSessionToken = 0;
let fpState = null;
let fpInvokingElement = null;

function fpIsSessionCurrent(token) {
  if (!fpState || fpState.token !== token) return false;
  const dom = fpResolvePickerDom();
  return !!(dom && dom.root && !dom.root.classList.contains("hidden"));
}

function fpPrettifyRef(ref) {
  return String(ref || "").replace(/[-_/]+/g, " ").replace(/\s+/g, " ").trim();
}

function fpDisplayName(model, ref) {
  if (model) {
    return String(model.display_name || model.label || model.full_id || ref || "");
  }
  return ref ? fpPrettifyRef(ref) : "";
}

function fpProviderName(model) {
  if (!model) return "";
  const key = String(model.provider || "");
  const known = typeof VOICEFLOW_POLICY_PROVIDER_NAMES !== "undefined" ? VOICEFLOW_POLICY_PROVIDER_NAMES[key] : null;
  const config = typeof ALL_PROVIDERS_CONFIG !== "undefined" ? ALL_PROVIDERS_CONFIG[key] : null;
  return String(model.provider_name || known || config?.name || key);
}

function fpProviderIcon(model) {
  const key = model ? (model.provider || model.provider_name || "") : "";
  if (typeof vfPickerProviderIcon === "function") {
    try {
      const icon = vfPickerProviderIcon(key);
      if (icon) return String(icon);
    } catch (_) { /* fall through to text fallback */ }
  }
  const name = fpProviderName(model) || key || "?";
  return name.trim().charAt(0).toUpperCase() || "•";
}

function fpIconMarkup(model) {
  const icon = fpProviderIcon(model);
  // Brand icons are trusted SVG strings from provider-logos.js; anything else
  // is plain text and must be escaped.
  return icon.startsWith("<svg") || icon.startsWith("<span") ? icon : fpEsc(icon);
}

// At most one availability/privacy tag per row, derived strictly from real
// metadata (plan section 4: never claim offline/private without support).
function fpAvailabilityTag(model) {
  const caps = Array.isArray(model && model.capabilities) ? model.capabilities.map((c) => String(c).toLowerCase()) : [];
  if (caps.includes("offline")) return { text: "Offline", kind: "offline" };
  return null;
}

function fpFindModel(cfg, ref) {
  return (cfg.getCatalog() || []).find((m) => m.full_id === ref) || null;
}

function fpRowUnavailable(cfg, model) {
  if (model && cfg.isAvailable && !cfg.isAvailable(model)) {
    return cfg.unavailableReason ? cfg.unavailableReason(model) : "Not available for this feature";
  }
  return null;
}

function fpDetailsPanelMarkup(cfg, model, ref) {
  const reason = model ? fpRowUnavailable(cfg, model) : null;
  const caps = Array.isArray(model && model.capabilities) ? model.capabilities.filter(Boolean) : [];
  const lines = [];
  if (reason) lines.push(`<p class="flow-picker-state-hint">${fpEsc(reason)}</p>`);
  if (caps.length) {
    lines.push(`<div class="flow-picker-more-info flow-picker-caps-wrap">${caps.map((c) => `<span class="flow-picker-cap">${fpEsc(c)}</span>`).join(" ")}</div>`);
  }
  if (ref) {
    lines.push(`<div class="flow-picker-more-info"><code>${fpEsc(ref)}</code></div>`);
  }
  if (!lines.length) {
    lines.push(`<div class="flow-picker-more-info">No extra details available.</div>`);
  }
  // Wrap-safe optional details region (usability.css: .flow-picker-details-region).
  return `<div class="flow-picker-details-region" hidden>${lines.join("")}</div>`;
}

function fpRowMarkup(cfg, model, ref, opts = {}) {
  const itemTag = opts.itemTag || "div";
  const name = fpDisplayName(model, ref);
  const provider = fpProviderName(model);
  const language = model && model.language ? String(model.language) : "";
  const unavailableReason = model ? fpRowUnavailable(cfg, model) : null;
  // One availability/privacy tag max, from real metadata only; unavailable
  // rows carry their reason in the sub-line instead (contract: reason text
  // stays readable in .flow-picker-sub).
  const tag = !unavailableReason ? fpAvailabilityTag(model) : null;
  const sub = [provider, language, tag ? tag.text : null, unavailableReason].filter(Boolean).join(" · ");
  const isSelected = !opts.isCurrent && ref && ref === opts.activeRef;
  const isSaving = fpState && fpState.saving && fpState.savingRef === ref;

  const classes = ["flow-picker-row"];
  if (isSelected) classes.push("is-selected");
  if (unavailableReason) classes.push("flow-picker-row-unavailable");
  if (opts.isCurrent) classes.push("flow-picker-row-current");

  const selectedBadge = isSelected ? '<span class="flow-picker-selected">Selected</span>' : "";
  const savingBadge = isSaving ? '<span class="flow-picker-saving">Saving…</span>' : "";

  return `
    <${itemTag} class="flow-picker-item">
      <button type="button" class="${classes.join(" ")}"${ref ? ` data-full-id="${fpEsc(ref)}" data-model-ref="${fpEsc(ref)}"` : ""}
        ${unavailableReason ? 'aria-disabled="true" title="' + fpEsc(unavailableReason) + '"' : ""}
        ${isSelected ? ' aria-checked="true" data-selected="true"' : ""}>
        <span class="flow-picker-icon" aria-hidden="true">${fpIconMarkup(model)}</span>
        <div class="flow-picker-text">
          <span class="flow-picker-name">${fpEsc(name)}</span>
          ${sub ? `<span class="flow-picker-sub">${fpEsc(sub)}</span>` : ""}
        </div>
        ${savingBadge}
        ${selectedBadge}
      </button>
      <button type="button" class="flow-picker-details" aria-expanded="false" aria-label="Details for ${fpEsc(name)}">Details</button>
      ${fpDetailsPanelMarkup(cfg, model, ref)}
    </${itemTag}>
  `;
}

function fpCurrentBoxMarkup(cfg, activeRef, opts = {}) {
  const itemTag = opts.itemTag || "div";
  if (!activeRef) {
    return `<${itemTag} class="flow-picker-more-info">No choice saved yet — pick one below.</${itemTag}>`;
  }
  const model = fpFindModel(cfg, activeRef);
  const name = fpDisplayName(model, activeRef) || activeRef;
  const loading = !!(fpState && fpState.loading);
  // While the catalogue is still loading, a missing entry says nothing about
  // availability — never show a premature "unavailable" claim.
  const reason = model
    ? fpRowUnavailable(cfg, model)
    : (loading ? null : "This choice is not available right now — it may have been disconnected. Nothing was switched automatically; pick another option below.");
  const classes = ["flow-picker-row", "flow-picker-row-current"];
  if (reason) classes.push("flow-picker-row-unavailable");
  return `
    <${itemTag} class="flow-picker-item flow-picker-current-item">
      <button type="button" class="${classes.join(" ")}" data-full-id="${fpEsc(activeRef)}" data-model-ref="${fpEsc(activeRef)}"
        ${reason ? 'aria-disabled="true" title="' + fpEsc(reason) + '"' : ' aria-checked="true" data-selected="true"'}>
        <span class="flow-picker-icon" aria-hidden="true">${fpIconMarkup(model)}</span>
        <div class="flow-picker-text">
          <span class="flow-picker-name">${fpEsc(name)}</span>
          ${fpProviderName(model) ? `<span class="flow-picker-sub">${fpEsc(fpProviderName(model))}</span>` : ""}
        </div>
        <span class="flow-picker-selected">${reason ? "Saved · unavailable" : (loading ? "Saved" : "Selected")}</span>
      </button>
      <button type="button" class="flow-picker-details" aria-expanded="false" aria-label="Details for ${fpEsc(name)}">Details</button>
      ${fpDetailsPanelMarkup(cfg, model, activeRef)}
      ${reason ? `<p class="flow-picker-more-info">${fpEsc(reason)}</p>` : ""}
    </${itemTag}>
  `;
}

function fpSetStatus(kind, message, action) {
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root) return;
  let region = document.getElementById("vf-picker-status");
  if (!kind || !message) {
    if (region) region.remove();
    return;
  }
  if (!region) {
    region = document.createElement("div");
    region.id = "vf-picker-status";
    if (dom.list && dom.list.parentElement) {
      dom.list.parentElement.insertBefore(region, dom.list);
    } else {
      dom.root.appendChild(region);
    }
  }
  region.setAttribute("role", "alert");
  const actionButton = action
    ? `<button type="button" class="flow-btn flow-picker-retry" data-fp-action="${fpEsc(action)}">${action === "reload" ? "Try again" : "Dismiss"}</button>`
    : "";
  region.innerHTML = `
    <div class="flow-picker-state flow-picker-state--error">
      <p class="flow-picker-state-title">${fpEsc(message.title)}</p>
      <p class="flow-picker-state-hint">${fpEsc(message.hint)}</p>
      ${actionButton}
    </div>`;
}

function fpEnsureCurrentBox(dom) {
  if (dom.current) return dom.current;
  if (!dom.list) return null;
  const box = document.createElement("div");
  box.id = "vf-picker-current";
  box.className = "flow-picker-current";
  dom.list.parentElement.insertBefore(box, dom.list);
  fpWarnOnce("vf-picker-current", "Created #vf-picker-current dynamically; index.html does not provide it yet.");
  dom.current = box;
  return box;
}

function fpRenderCurrentBox() {
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root || !fpState) return;
  const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
  const box = fpEnsureCurrentBox(dom);
  if (!cfg || !box) return;
  const itemTag = (box.tagName === "UL" || (dom.list && (dom.list.tagName === "UL" || dom.list.tagName === "OL"))) ? "li" : "div";
  const heading = '<div class="flow-picker-current-label">Current choice</div>';
  box.innerHTML = heading + fpCurrentBoxMarkup(cfg, cfg.getActiveRef(), { itemTag });
  box.hidden = false; // the HTML ships it hidden until populated
}

function fpStateBlockMarkup(kind, title, hint, actionLabel, action) {
  const spinner = kind === "loading" ? '<span class="flow-spinner" aria-hidden="true"></span>' : "";
  const button = action
    ? `<button type="button" class="flow-btn flow-picker-retry" data-fp-action="${fpEsc(action)}">${fpEsc(actionLabel)}</button>`
    : "";
  return `
    <div class="flow-picker-state${kind ? " flow-picker-state--" + kind : ""}">
      ${spinner}
      <p class="flow-picker-state-title">${fpEsc(title)}</p>
      ${hint ? `<p class="flow-picker-state-hint">${fpEsc(hint)}</p>` : ""}
      ${button}
    </div>`;
}

function fpRenderList() {
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root || !fpState) return;
  const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
  const list = dom.list;
  if (!cfg || !list) return;

  // Emit <li> children when the HTML contract ships a <ul> list.
  const itemTag = (list.tagName === "UL" || list.tagName === "OL") ? "li" : "div";
  const query = (fpState.query || "").trim().toLowerCase();
  const allModels = cfg.getCatalog() || [];

  if (fpState.loading) {
    list.innerHTML = fpStateBlockMarkup("loading", "Loading choices…", "", "", null);
    return;
  }
  if (fpState.loadError) {
    // Fetch failure: "Couldn't load choices" + Try again (plan section 5).
    list.innerHTML = fpStateBlockMarkup("error", "Couldn't load choices", fpState.loadError, "Try again", "reload");
    list.removeAttribute("aria-busy");
    return;
  }

  // Deduplicate by canonical model reference; provider grouping becomes small
  // headings over one column of rows. No invented rankings — stable catalog
  // order is preserved.
  const seen = new Map();
  for (const model of allModels) {
    const ref = String(model.full_id || "").trim();
    if (!ref || seen.has(ref)) continue;
    if (query) {
      const haystack = [fpDisplayName(model, ref), fpProviderName(model), model.provider, model.full_id,
        ...(Array.isArray(model.capabilities) ? model.capabilities : [])].join(" ").toLowerCase();
      if (!haystack.includes(query)) continue;
    }
    seen.set(ref, model);
  }

  const activeRef = cfg.getActiveRef();
  if (!seen.size) {
    if (query) {
      list.innerHTML = fpStateBlockMarkup("", "No matches", `Nothing matches “${fpState.query.trim()}”.`, "Clear search", "clear-search");
    } else {
      list.innerHTML = fpStateBlockMarkup("", "No available choices", cfg.emptyHelp || "Connect a service to add choices.", cfg.manageLabel || "Manage providers", "manage");
    }
    list.removeAttribute("aria-busy");
    return;
  }

  const groups = new Map();
  for (const model of seen.values()) {
    const groupName = fpProviderName(model) || "Other";
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push(model);
  }

  // Flat structure: group headings and item wrappers as direct children of the
  // list (matches the usability.css selectors and the HTML row template).
  const parts = [];
  for (const [groupName, models] of groups.entries()) {
    parts.push(`<h4 class="flow-picker-group-title">${fpEsc(groupName)} <span>${models.length}</span></h4>`);
    for (const model of models) {
      parts.push(fpRowMarkup(cfg, model, model.full_id, { activeRef, itemTag }));
    }
  }
  list.innerHTML = parts.join("");
  if (fpState.saving) {
    list.setAttribute("aria-busy", "true");
  } else {
    list.removeAttribute("aria-busy");
  }
}

function fpRenderPickerChrome() {
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root || !fpState) return;
  const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
  if (!cfg) return;

  const dialog = dom.dialog || dom.root;
  if (!dialog.hasAttribute("role")) dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  if (dom.title) {
    if (!dom.title.id) dom.title.id = "vf-picker-title";
    dialog.setAttribute("aria-labelledby", dom.title.id);
    if (dom.titleText) dom.titleText.textContent = cfg.title;
  }
  if (dom.helperText) {
    dom.helperText.textContent = cfg.helper;
  }
  if (dom.kicker) {
    dom.kicker.textContent = ""; // Uppercase marketing kicker removed per plan.
  }
  if (dom.search) {
    dom.search.setAttribute("type", "search");
    dom.search.setAttribute("placeholder", cfg.searchPlaceholder || "Search…");
    dom.search.setAttribute("aria-label", "Search choices");
    dom.search.oninput = () => {
      if (!fpState) return;
      fpState.query = dom.search.value || "";
      // Keep the hidden legacy mirror input synchronized (HTML contract).
      if (dom.searchMirror && dom.searchMirror !== dom.search) {
        dom.searchMirror.value = dom.search.value;
      }
      fpRenderList();
    };
  }
  if (dom.manage) {
    dom.manage.textContent = (cfg.manageLabel || "Manage providers") + " →";
    // Per-context footer routing (fixes the old always-'providers' bug).
    dom.manage.onclick = (event) => {
      event.preventDefault();
      fpGoToDestination(cfg.destination);
    };
  }
  if (dom.close) {
    dom.close.setAttribute("aria-label", "Close");
    dom.close.onclick = () => fpClosePicker();
  }
}

// Delegated click handling: rows, details toggles, empty-state actions.
function fpHandlePickerClick(event) {
  if (!fpState) return;
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root || dom.root.classList.contains("hidden")) return;
  const target = event.target;
  if (!(target instanceof Element) || !dom.root.contains(target)) return;

  const actionEl = target.closest("[data-fp-action]");
  if (actionEl) {
    const action = actionEl.getAttribute("data-fp-action");
    if (action === "clear-search") {
      fpState.query = "";
      if (dom.search) dom.search.value = "";
      fpSetStatus(null);
      fpRenderList();
      if (dom.search) dom.search.focus();
    } else if (action === "manage") {
      const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
      if (cfg) fpGoToDestination(cfg.destination);
    } else if (action === "reload") {
      fpState.loading = true;
      fpSetStatus(null);
      fpRenderList();
      fpLoadCatalogForState();
    }
    return;
  }

  const detailsBtn = target.closest(".flow-picker-details");
  if (detailsBtn) {
    const panel = detailsBtn.nextElementSibling;
    if (panel && panel.classList.contains("flow-picker-details-region")) {
      const willOpen = panel.hidden;
      panel.hidden = !willOpen;
      detailsBtn.setAttribute("aria-expanded", String(willOpen));
    }
    return;
  }

  const row = target.closest("button.flow-picker-row");
  if (row) {
    if (row.getAttribute("aria-disabled") === "true") return; // unavailable choices cannot be saved
    const ref = row.getAttribute("data-full-id") || row.getAttribute("data-model-ref") || "";
    if (ref) fpChooseRef(ref);
  }
}

function fpHandlePickerKeydown(event) {
  if (!fpState) return;
  const dom = fpResolvePickerDom();
  if (!dom || !dom.root || dom.root.classList.contains("hidden")) return;

  if (event.key === "Escape") {
    event.preventDefault();
    fpClosePicker();
    return;
  }
  if (event.key !== "Tab") return;

  // Contain focus while the dialog is open.
  const focusables = Array.from(
    dom.root.querySelectorAll('button:not([disabled]):not([aria-disabled="true"]), input, select, a[href], [tabindex]:not([tabindex="-1"])')
  ).filter((el) => el.offsetParent !== null || el === document.activeElement);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (!dom.root.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function fpLoadCatalogForState() {
  if (!fpState) return;
  const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
  const token = fpState.token;
  if (!cfg || typeof cfg.load !== "function") return;
  Promise.resolve()
    .then(() => cfg.load())
    .then((result) => {
      if (!fpIsSessionCurrent(token)) return; // stale response from a previous context
      fpState.loading = false;
      if (result && result.ok === false) {
        fpState.loadError = result.error || "";
      } else {
        fpState.loadError = null;
      }
      fpRenderCurrentBox();
      fpRenderList();
    })
    .catch((err) => {
      if (!fpIsSessionCurrent(token)) return;
      fpState.loading = false;
      fpState.loadError = (err && err.message) || "";
      fpRenderList();
    });
}

async function fpChooseRef(ref) {
  if (!fpState || fpState.saving) return; // disable duplicate submissions
  const cfg = FLOW_PICKER_CONTEXTS[fpState.context];
  if (!cfg) return;
  const token = fpState.token;
  const activeRef = cfg.getActiveRef();
  if (ref === activeRef) {
    fpClosePicker(); // re-picking the current choice is a no-op
    return;
  }
  const model = fpFindModel(cfg, ref);
  if (fpRowUnavailable(cfg, model)) return; // unavailable choices cannot be saved

  fpState.saving = true;
  fpState.savingRef = ref;
  fpSetStatus(null);
  fpRenderList();
  fpRenderCurrentBox();

  try {
    const result = await cfg.save(ref);
    if (!fpIsSessionCurrent(token)) return; // closed or context switched meanwhile
    fpState.saving = false;
    fpState.savingRef = null;
    if (result && result.ok === false) {
      // Keep the previous choice; show an inline retryable error.
      fpSetStatus("save-error", {
        title: "Couldn't save your choice",
        hint: (result.error || "Something went wrong.") + " The previous selection is still active — you can try again.",
      }, "dismiss");
      fpRenderList();
      fpRenderCurrentBox();
    } else {
      fpClosePicker();
    }
  } catch (err) {
    if (!fpIsSessionCurrent(token)) return;
    fpState.saving = false;
    fpState.savingRef = null;
    fpSetStatus("save-error", {
      title: "Couldn't save your choice",
      hint: ((err && err.message) || "Something went wrong.") + " The previous selection is still active — you can try again.",
    }, "dismiss");
    fpRenderList();
    fpRenderCurrentBox();
  }
}

// Single delegated listeners, installed once at script load. They no-op when
// the picker is closed or when the modal was opened by the legacy machinery.
document.addEventListener("click", fpHandlePickerClick);
document.addEventListener("keydown", fpHandlePickerKeydown);

function fpClosePicker() {
  fpSessionToken += 1; // invalidate pending presentation updates
  const dom = fpResolvePickerDom();
  if (dom && dom.root) {
    dom.root.classList.add("hidden");
  }
  if (typeof closeVideoModal === "function") {
    try { closeVideoModal("vf-model-picker-modal"); } catch (_) { /* already hidden */ }
  }
  fpRestoreLegacyPickerDom();
  const invoking = fpInvokingElement;
  fpInvokingElement = null;
  fpState = null;
  if (invoking && typeof invoking.focus === "function" && invoking.isConnected) {
    try { invoking.focus(); } catch (_) { /* element gone */ }
  }
}

// The HTML contract keeps video-flow.js's legacy renderer alive by nesting
// #vf-model-picker-list inside #vf-picker-list. After the shared core has
// rendered (which replaces the list content), rebuild that empty container,
// re-hide the current-choice block and clear transient state so the legacy
// machinery keeps working for video contexts.
function fpRestoreLegacyPickerDom() {
  try {
    const list = document.getElementById("vf-picker-list");
    if (list) {
      list.innerHTML = "";
      if (!document.getElementById("vf-model-picker-list")) {
        const legacyList = document.createElement("div");
        legacyList.id = "vf-model-picker-list";
        legacyList.className = "vf-grouped-model-picker";
        list.appendChild(legacyList);
      }
    }
    const current = document.getElementById("vf-picker-current");
    if (current) current.hidden = true;
    const status = document.getElementById("vf-picker-status");
    if (status) status.remove();
    const search = document.getElementById("vf-picker-search");
    if (search) search.value = "";
    const mirror = document.getElementById("vf-model-picker-search");
    if (mirror) mirror.value = "";
  } catch (_) { /* best-effort restore */ }
}

// Entry point for the shared picker. The core serves every context declared in
// FLOW_PICKER_CONTEXTS (app.js contexts directly, video contexts from the
// shared catalog + video-flow.js setters). If the new-contract list element is
// missing but the legacy one exists, video contexts fall back to their existing
// renderer; unknown contexts always defer to video-flow.js.
function openSharedModelPicker(context) {
  const normalized = fpNormalizeContext(context);
  const cfg = FLOW_PICKER_CONTEXTS[normalized];
  const dom = fpResolvePickerDom();

  if (!cfg) {
    // Unknown/other context — defer to the existing video-flow machinery.
    if (typeof openVideoModelPicker === "function") {
      openVideoModelPicker(context);
    } else {
      console.warn("[flow-picker] No handler for picker context: " + context);
    }
    return;
  }
  if (dom && FLOW_PICKER_VIDEO_CONTEXTS.has(normalized) &&
      !document.getElementById("vf-picker-list") && document.getElementById("vf-model-picker-list")) {
    // Legacy dialog only: keep video contexts on their existing renderer.
    openVideoModelPicker(context);
    return;
  }
  if (!dom || !dom.root) {
    // Dialog missing entirely (mid-restructure): last resort is the legacy
    // opener so the feature does not silently die.
    if (typeof openVideoModelPicker === "function") {
      openVideoModelPicker(context);
    }
    return;
  }

  const activeEl = document.activeElement;
  fpInvokingElement = activeEl instanceof HTMLElement ? activeEl : null;
  fpSessionToken += 1;
  fpState = {
    token: fpSessionToken,
    context: normalized,
    query: "",
    saving: false,
    savingRef: null,
    loading: false,
    loadError: null,
  };

  dom.root.classList.remove("hidden");
  fpRenderPickerChrome();
  fpSetStatus(null);
  fpRenderCurrentBox();
  // Fresh search per open: clear the live input and its hidden legacy mirror.
  if (dom.search) dom.search.value = "";
  if (dom.searchMirror && dom.searchMirror !== dom.search) dom.searchMirror.value = "";

  const catalog = cfg.getCatalog() || [];
  if (!catalog.length && typeof cfg.load === "function") {
    fpState.loading = true;
    fpRenderList();
    fpLoadCatalogForState();
  } else {
    fpRenderList();
  }

  requestAnimationFrame(() => {
    if (!fpState) return;
    const fresh = fpResolvePickerDom();
    if (!fresh) return;
    if (fresh.search) fresh.search.focus();
    else if (fresh.close) fresh.close.focus();
  });
}

// Kept as a global so the search input can be wired either inline by the HTML
// pass or programmatically (both are handled; the open-time wiring wins).
function renderSharedModelPickerList() {
  if (fpState) fpRenderList();
}

// Global close alias for the HTML pass (#vf-picker-close wiring).
function closeSharedModelPicker() {
  fpClosePicker();
}

function filterProvidersList() {
  const q = (document.getElementById("provider-search")?.value || "").toLowerCase();
  document.querySelectorAll(".provider-card-item").forEach(card => {
    const name = (card.querySelector(".provider-card-name, .dm-title")?.textContent || "").toLowerCase();
    card.style.display = name.includes(q) ? "flex" : "none";
  });
}

async function openProviderDetail(providerId) {
  if (currentSelectedProvider !== providerId) _vfSelectedConnIds.clear();
  currentSelectedProvider = providerId;
  const isCustom = String(providerId).startsWith("custom-");
  const customEntry = isCustom ? (vfVoiceCustomProviders || []).find(p => p.id === providerId) : null;
  const cfg = ALL_PROVIDERS_CONFIG[providerId] || {
    name: customEntry?.name || providerId,
    logo: (customEntry?.name || "C")[0].toUpperCase(),
    keyLink: null,
  };

  document.getElementById("providers-view-overview").style.display = "none";
  document.getElementById("providers-view-detail").style.display = "block";

  document.getElementById("detail-provider-name").textContent = cfg.name;
  document.getElementById("detail-provider-logo").innerHTML = vfBrandLogo(providerId, cfg.logo);
  const keyLink = document.getElementById("detail-get-key-link");
  if (keyLink) {
    keyLink.style.display = (cfg.keyLink && !isCustom) ? "inline-flex" : "none";
    if (cfg.keyLink) keyLink.href = cfg.keyLink;
  }
  const editBtn = document.getElementById("detail-edit-custom-provider-btn");
  if (editBtn) {
    editBtn.style.display = isCustom ? "inline-flex" : "none";
  }
  const delBtn = document.getElementById("detail-delete-custom-provider-btn");
  if (delBtn) {
    delBtn.style.display = isCustom ? "inline-flex" : "none";
  }

  loadProviderDetails(providerId);
}

function closeProviderDetail() {
  currentSelectedProvider = null;
  const errBanner = document.getElementById("models-test-error-banner");
  if (errBanner) {
    errBanner.textContent = "";
    errBanner.style.display = "none";
  }
  loadProvidersOverview();
}

let _vfProviderModelTestResults = {};
let _vfProviderModelErrors = {};
let _vfTestingModelIds = new Set();
let _vfTestingAudioModelIds = new Set();
let _vfSelectedConnIds = new Set();
let _vfOneByOneRunning = false;
let _vfAudioOneByOneRunning = false;
let _vfAudioSelectedConnIds = new Set();
let _vfAudioModelTestResults = {};
let _vfAudioProviderModelErrors = {};

async function loadProviderDetails(providerId) {
  try {
    const res = await fetch(`/api/providers/details?provider=${providerId}`);
    const data = await res.json();
    currentProviderData = data;

    const conns = (data.connections || []).sort((a, b) => (a.priority || 0) - (b.priority || 0));
    const connCountEl = document.getElementById("detail-conn-count");
    if (connCountEl) {
      // Honest connection status, not a bare count (plan section 8).
      const state = vfProviderConnStateLabel(conns);
      connCountEl.textContent = state.label;
      connCountEl.dataset.connectionState = state.key;
      connCountEl.classList.add("flow-status", `flow-status--${vfFlowStatusMod(state.key)}`);
    }

    const rrToggle = document.getElementById("provider-round-robin-toggle");
    if (rrToggle) {
      rrToggle.checked = (data.mode === "round-robin" || data.mode === "round_robin");
    }

    const connListEl = document.getElementById("detail-connections-list");
    if (connListEl) {
      if (conns.length === 0) {
        connListEl.innerHTML = `
          <div class="conn-empty-9r">
            <div class="conn-empty-left-9r">
              <div class="conn-empty-icon-circle-9r">${vfUiIcon("key")}</div>
              <span class="conn-empty-text-9r">No connections yet</span>
            </div>
            <button class="btn-primary" style="padding: 7px 16px; font-size: 12px; display: inline-flex; align-items: center; gap: 6px;" onclick="openAddConnectionModal()">+ Add</button>
          </div>
        `;
      } else {
        connListEl.innerHTML = conns.map((c, idx) => {
          const isFirst = idx === 0;
          const isLast = idx === conns.length - 1;
          const isSelected = _vfSelectedConnIds.has(c.id);
          const isAct = c.is_active !== false && c.is_active !== 0;
          // Distinguishable-by-text states (plan section 8): disabled, verified,
          // unverified-saved, and failure are separate labels, not just colors.
          const state = vfConnState(c);
          const statusDotClass = state.key === "connected" ? "active" : (state.key === "attention" ? "error" : "disabled");
          const statusDotLabel = state.label;
          const keyRaw = c.api_key || "";
          const keyPreview = keyRaw.length > 10 ? `${keyRaw.substring(0, 6)}...${keyRaw.substring(keyRaw.length - 4)}` : "Key saved";
          const failureText = (state.key === "attention" && c.last_tested_status && !String(c.last_tested_status).includes("Connected"))
            ? `<span style="font-size: 10px; color: #ef4444;">${escapeHtml(c.last_tested_status)}</span>`
            : '';

          return `
            <div class="conn-row-9r ${!isAct ? 'inactive' : ''}" data-conn-id="${c.id}">
              <div class="conn-left-9r">
                <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectProviderConn('${c.id}', this.checked)">
                <div class="conn-arrows-col">
                  <button class="conn-arrow-btn" onclick="moveConnPriority('${escapeJs(providerId)}', '${c.id}', -1)" ${isFirst ? 'disabled' : ''} title="Move up">▲</button>
                  <button class="conn-arrow-btn" onclick="moveConnPriority('${escapeJs(providerId)}', '${c.id}', 1)" ${isLast ? 'disabled' : ''} title="Move down">▼</button>
                </div>
                <span class="conn-key-icon">${(c.auth_type === 'oauth' || c.authType === 'oauth') ? '⚡' : '🔑'}</span>
                <div class="conn-details-col">
                  <div class="conn-title-row">
                    <span class="conn-name-text">${escapeHtml(c.email || c.name || 'Connection')}</span>
                  </div>
                  <div class="conn-badges-row">
                    <span class="conn-dot-badge ${statusDotClass}">● ${escapeHtml(statusDotLabel)}</span>
                    <span class="conn-pill-badge ${(c.auth_type === 'oauth' || c.authType === 'oauth') ? 'oauth-badge-active' : ''}">${(c.auth_type === 'oauth' || c.authType === 'oauth') ? 'OAuth' : 'API Key'}</span>
                    <span class="conn-priority-pill">#${c.priority || (idx + 1)}</span>
                    ${(c.auth_type === 'oauth' || c.authType === 'oauth') ? `<span style="font-size: 11px; color: var(--text-muted); margin-left: 4px;">OAuth Session Active</span>` : `<span style="font-size: 11px; color: var(--text-muted); margin-left: 4px;">Key: ${escapeHtml(keyPreview)}</span>`}
                    ${failureText}
                  </div>
                </div>
              </div>
              <div class="conn-actions-9r">
                <button class="conn-action-btn" onclick="testSingleConn('${c.id}')" title="Test Connection">
                  <span style="font-size: 14px;">🧪</span>
                  <span>Test</span>
                </button>
                <button class="conn-action-btn" onclick="openEditConnectionModal('${c.id}')" title="Edit Connection">
                  <span style="font-size: 14px;">✏️</span>
                  <span>Edit</span>
                </button>
                <button class="conn-action-btn delete-btn" onclick="deleteConn('${c.id}')" title="Delete Connection">
                  <span style="font-size: 14px;">🗑️</span>
                  <span>Delete</span>
                </button>
                <label class="toggle-switch" style="margin-left: 6px;">
                  <input type="checkbox" ${isAct ? 'checked' : ''} onchange="toggleProviderConn('${c.id}', this.checked)">
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    // Show/hide Select All row and bottom + Add button based on connections count
    const selectAllRowVF = document.getElementById("detail-select-all-row");
    const addConnContainerVF = document.getElementById("detail-add-conn-container");
    if (selectAllRowVF) selectAllRowVF.style.display = conns.length > 0 ? "" : "none";
    if (addConnContainerVF) addConnContainerVF.style.display = conns.length > 0 ? "" : "none";

    // Models rendering (9Router format)
    const allModels = data.models || [];
    const activeModels = allModels.filter(m => m.is_active !== false && m.is_active !== 0);
    const disabledModels = allModels.filter(m => m.is_active === false || m.is_active === 0);

    const modelsGridEl = document.getElementById("detail-models-grid");
    if (modelsGridEl) {
      let cardsHtml = activeModels.map(m => {
        const fullId = `${providerId}/${m.model_id}`;
        const testRes = _vfProviderModelTestResults[m.model_id];
        const isTesting = _vfTestingModelIds.has(m.model_id);
        const cardClass = isTesting ? 'testing' : (testRes ? (testRes.ok ? 'tested-ok' : 'tested-error') : '');
        // Shared icon language with Audio/Video Flow: real brand mark when we
        // have one, otherwise a state icon, plus inline-SVG action buttons.
        const brandMark = vfBrandLogo(providerId);
        const stateIcon = isTesting
          ? vfUiIcon("spinner", "vf-ico-spin")
          : (testRes ? (testRes.ok ? vfUiIcon("check") : vfUiIcon("ban")) : vfUiIcon("bot"));

        return `
          <div class="model-card-9r ${cardClass}" id="model-card-${m.id}">
            <div class="model-card-left-9r">
              <span class="model-status-icon-9r ${isTesting ? 'testing' : ''}">${brandMark || stateIcon}</span>
              <div class="model-card-info-9r">
                <div class="edge-voice-title" title="${escapeHtml(m.display_name || m.model_id)}">${escapeHtml(m.display_name || m.model_id)}</div>
                <div class="model-card-meta-9r">
                  <code class="model-code-tag" title="${escapeHtml(fullId)}">${escapeHtml(fullId)}</code>
                  ${testRes && testRes.ok && testRes.latency_ms ? `<span class="model-latency-9r">${testRes.latency_ms}ms</span>` : ''}
                </div>
                ${testRes && !testRes.ok && testRes.error ? `<div class="model-test-error-text" title="${escapeHtml(testRes.error)}">${vfUiIcon("ban")} ${escapeHtml(testRes.error)}</div>` : ''}
              </div>
            </div>
            <div class="model-actions-9r">
              <button class="model-action-btn-9r" onclick="testSingleModel('${escapeJs(m.model_id)}', this)" title="Test model" aria-label="Test model" ${isTesting ? 'disabled' : ''}>
                ${isTesting ? vfUiIcon("spinner", "vf-ico-spin") : vfUiIcon("test")}
              </button>
              <button class="model-action-btn-9r" onclick="copyModelId('${escapeJs(fullId)}', this)" title="Copy Model ID" aria-label="Copy model ID">
                ${vfUiIcon("copy", "vf-ico-copy")}${vfUiIcon("check", "vf-ico-check")}
              </button>
              ${(m.custom || String(providerId).startsWith("custom-")) ? `
                <button class="model-action-btn-9r delete" onclick="deleteProviderCustomModel('${escapeJs(m.id || m.model_id)}', '${escapeJs(providerId)}')" title="Delete model permanently" aria-label="Delete model permanently">
                  ${vfUiIcon("trash")}
                </button>
              ` : ''}
              <button class="model-action-btn-9r delete" onclick="disableModel('${m.id}')" title="Disable this model" aria-label="Disable this model">
                ${vfUiIcon("ban")}
              </button>
            </div>
          </div>
        `;
      }).join("");

      // Append Add Model dashed button
      cardsHtml += `
        <div class="add-model-dashed-btn" onclick="openAddModelModal()">
          <span>+</span> Add Model
        </div>
      `;

      modelsGridEl.innerHTML = cardsHtml;
    }

    // Disabled models chips section
    const disabledBox = document.getElementById("detail-disabled-models-box");
    const disabledCountEl = document.getElementById("detail-disabled-count");
    const disabledListEl = document.getElementById("detail-disabled-models-list");
    if (disabledBox && disabledListEl) {
      if (disabledModels.length > 0) {
        disabledBox.style.display = "block";
        if (disabledCountEl) disabledCountEl.textContent = String(disabledModels.length);
        disabledListEl.innerHTML = disabledModels.map(m => `
          <button class="disabled-model-chip" onclick="enableModel('${m.id}')" title="Click to restore model">
            <span>+</span> ${escapeHtml(m.model_id)}
          </button>
        `).join("");
      } else {
        disabledBox.style.display = "none";
      }
    }

    // Provider-scoped model test error banner (only shows error for this active provider)
    const errBanner = document.getElementById("models-test-error-banner");
    if (errBanner) {
      const activeErr = _vfProviderModelErrors[providerId];
      if (activeErr && activeErr.error) {
        errBanner.textContent = `✕ Model Test Failed (${activeErr.modelId}): ${activeErr.error}`;
        errBanner.style.display = "block";
      } else {
        errBanner.textContent = "";
        errBanner.style.display = "none";
      }
    }

  } catch (err) {
    console.error("Error loading provider details:", err);
  }
}

async function moveConnPriority(providerId, connId, direction) {
  if (!currentProviderData || !currentProviderData.connections) return;
  const conns = [...currentProviderData.connections].sort((a, b) => (a.priority || 0) - (b.priority || 0));
  const idx = conns.findIndex(c => String(c.id) === String(connId));
  if (idx < 0) return;
  const targetIdx = idx + direction;
  if (targetIdx < 0 || targetIdx >= conns.length) return;

  const temp = conns[idx];
  conns[idx] = conns[targetIdx];
  conns[targetIdx] = temp;

  const ids = conns.map(c => c.id);
  try {
    await fetch("/api/providers/connections/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerId, connection_ids: ids }),
    });
    loadProviderDetails(providerId);
  } catch (err) {
    console.error("Error reordering connections:", err);
  }
}

const OAUTH_PROVIDERS = new Set(["antigravity", "openai_codex", "claude_code", "claude"]);

let _currentOAuthPopup = null;
let _currentOAuthProvider = null;
let _currentOAuthState = null;
let _currentOAuthAuthUrl = "";

// Credentials stay masked by default (plan section 8). The HTML pass wires
// the show/hide control to this helper; it never logs or echoes the key.
function toggleConnectionKeyVisibility(inputId = "conn-input-key", btnEl = null) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const showNow = input.type === "password";
  input.type = showNow ? "text" : "password";
  input.setAttribute("autocomplete", "off");
  if (btnEl) {
    btnEl.setAttribute("aria-pressed", String(showNow));
    const label = btnEl.querySelector("[data-key-toggle-label]") || btnEl;
    if (label) label.textContent = showNow ? "Hide" : "Show";
  }
}

function _resetConnectionKeyInputMask() {
  const input = document.getElementById("conn-input-key");
  if (input) {
    input.type = "password";
    input.setAttribute("autocomplete", "new-password");
  }
  const toggleBtn = document.getElementById("conn-key-visibility-toggle");
  if (toggleBtn) {
    toggleBtn.setAttribute("aria-pressed", "false");
    const label = toggleBtn.querySelector("[data-key-toggle-label]") || toggleBtn;
    if (label) label.textContent = "Show";
  }
}

// The add-connection modal ships without a show/hide control in some markup
// revisions; provide one (labeled, aria-pressed) without disturbing the rest
// of the form. Skipped when the HTML pass supplies #conn-key-visibility-toggle.
function _ensureConnectionKeyVisibilityToggle() {
  if (document.getElementById("conn-key-visibility-toggle")) return;
  const keyInput = document.getElementById("conn-input-key");
  if (!keyInput || !keyInput.parentElement) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "conn-key-visibility-toggle";
  btn.className = "btn-secondary";
  btn.setAttribute("aria-pressed", "false");
  btn.setAttribute("aria-label", "Show or hide the API key");
  btn.style.padding = "8px 14px";
  btn.style.fontSize = "12px";
  btn.innerHTML = '<span data-key-toggle-label>Show</span>';
  btn.addEventListener("click", () => toggleConnectionKeyVisibility("conn-input-key", btn));
  keyInput.parentElement.insertBefore(btn, keyInput.nextSibling);
}

function openAddConnectionModal() {
  if (OAUTH_PROVIDERS.has(currentSelectedProvider)) {
    openOAuthConnectModal(currentSelectedProvider);
    return;
  }

  document.getElementById("conn-edit-id").value = "";
  document.getElementById("modal-conn-title").textContent = "Add API Key";
  document.getElementById("conn-input-name").value = `${(ALL_PROVIDERS_CONFIG[currentSelectedProvider]?.name || "Key")} Key`;
  document.getElementById("conn-input-key").value = "";
  document.getElementById("conn-input-key").placeholder = "Paste key...";
  document.getElementById("conn-input-priority").value = (currentProviderData?.connections?.length || 0) + 1;
  document.getElementById("conn-check-badge").innerHTML = "";
  _resetConnectionKeyInputMask();
  _ensureConnectionKeyVisibilityToggle();

  const getKeyLink = document.getElementById("modal-conn-get-key-link");
  if (getKeyLink) {
    const keyUrl = ALL_PROVIDERS_CONFIG[currentSelectedProvider]?.keyLink;
    if (keyUrl) {
      getKeyLink.href = keyUrl;
      getKeyLink.style.display = "inline-flex";
    } else {
      getKeyLink.style.display = "none";
    }
  }

  const modal = document.getElementById("modal-add-connection");
  if (modal) modal.classList.remove("hidden");
}

async function openOAuthConnectModal(providerId) {
  _currentOAuthProvider = providerId;
  const cfg = ALL_PROVIDERS_CONFIG[providerId] || { name: providerId };

  const modal = document.getElementById("vf-oauth-modal");
  if (!modal) return;

  const titleEl = document.getElementById("vf-oauth-provider-name");
  if (titleEl) titleEl.textContent = cfg.name;

  const statusEl = document.getElementById("vf-oauth-status");
  if (statusEl) {
    statusEl.innerHTML = `Waiting for popup authorization...`;
  }

  const urlPreview = document.getElementById("vf-oauth-url-preview");
  if (urlPreview) urlPreview.value = "Generating secure authentication link...";

  const codeInput = document.getElementById("vf-oauth-code-input");
  if (codeInput) codeInput.value = "";

  modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/providers/oauth/start?provider=${encodeURIComponent(providerId)}`);
    const data = await res.json();
    if (data.success && data.auth_url) {
      _currentOAuthState = data.state;
      _currentOAuthAuthUrl = data.auth_url;

      if (urlPreview) urlPreview.value = data.auth_url;

      // Auto-open browser popup
      const width = 540;
      const height = 680;
      const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2);
      const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2);
      _currentOAuthPopup = window.open(
        data.auth_url,
        "vf_oauth_popup",
        `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no`
      );
    } else {
      if (statusEl) statusEl.textContent = "Error: " + (data.error || "Failed to start OAuth");
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Error: " + err.message;
  }
}

function copyOAuthAuthUrl() {
  const urlPreview = document.getElementById("vf-oauth-url-preview");
  const url = urlPreview ? urlPreview.value : _currentOAuthAuthUrl;
  if (url && url.startsWith("http")) {
    navigator.clipboard.writeText(url).then(() => {
      if (typeof showToast === "function") showToast("Copied authorization URL to clipboard!", "success");
      else alert("Copied authorization URL to clipboard!");
    });
  }
}

function closeOAuthModal() {
  // Shared modal: also tear down the Video Flow relay timers when present.
  if (typeof vfOAuthCleanup === "function") {
    try { vfOAuthCleanup(); } catch (e) {}
  }
  if (_currentOAuthPopup && !_currentOAuthPopup.closed) {
    try { _currentOAuthPopup.close(); } catch (e) {}
  }
  _currentOAuthPopup = null;
  closeVideoModal("vf-oauth-modal");
}

async function completeVideoOAuthFromInput() {
  const input = document.getElementById("vf-oauth-code-input");
  const val = input ? input.value.trim() : "";
  if (!val) {
    alert("Please paste the callback URL or authorization code from your browser.");
    return;
  }
  const isUrl = val.startsWith("http://") || val.startsWith("https://") || val.includes("code=");
  await submitOAuthCompletion(_currentOAuthProvider || "antigravity", val, _currentOAuthState, isUrl ? val : null);
}

async function submitOAuthCompletion(providerId, code, state, callbackUrl = null) {
  const statusEl = document.getElementById("vf-oauth-status");
  if (statusEl) statusEl.textContent = "Exchanging tokens and activating connection...";

  try {
    const payload = {
      provider: providerId,
      code: code,
      state: state,
    };
    if (callbackUrl) payload.callback_url = callbackUrl;

    const res = await fetch("/api/providers/oauth/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      if (_currentOAuthPopup && !_currentOAuthPopup.closed) {
        try { _currentOAuthPopup.close(); } catch (e) {}
      }
      closeVideoModal("vf-oauth-modal");
      if (typeof showToast === "function") {
        showToast(`Connected ${data.email || providerId} successfully!`, "success");
      }
      loadProviderDetails(providerId);
    } else {
      if (statusEl) statusEl.textContent = "Error: " + (data.error || "Failed to complete sign-in");
      alert("Sign-in error: " + (data.error || "Failed to complete sign-in"));
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Error: " + err.message;
    alert("Error: " + err.message);
  }
}

// Global listener for OAuth popup completion
window.addEventListener("message", async function (event) {
  if (event.data && (event.data.type === "OAUTH_CALLBACK_SUCCESS" || event.data.code)) {
    const code = event.data.code;
    const state = event.data.state || _currentOAuthState;
    if (code && _currentOAuthProvider) {
      await submitOAuthCompletion(_currentOAuthProvider, code, state);
    }
  }
});

function openEditConnectionModal(cid) {
  if (!currentProviderData || !currentProviderData.connections) return;
  const conn = currentProviderData.connections.find(c => String(c.id) === String(cid));
  if (!conn) return;

  document.getElementById("conn-edit-id").value = String(cid);
  document.getElementById("modal-conn-title").textContent = "Edit API Key";
  document.getElementById("conn-input-name").value = conn.name || "";
  document.getElementById("conn-input-key").value = "";
  document.getElementById("conn-input-key").placeholder = "Leave blank to keep saved key";
  document.getElementById("conn-input-priority").value = conn.priority || 1;
  document.getElementById("conn-check-badge").innerHTML = "";
  _resetConnectionKeyInputMask();
  _ensureConnectionKeyVisibilityToggle();

  const getKeyLink = document.getElementById("modal-conn-get-key-link");
  if (getKeyLink) {
    const keyUrl = ALL_PROVIDERS_CONFIG[currentSelectedProvider]?.keyLink;
    if (keyUrl) {
      getKeyLink.href = keyUrl;
      getKeyLink.style.display = "inline-flex";
    } else {
      getKeyLink.style.display = "none";
    }
  }

  const modal = document.getElementById("modal-add-connection");
  if (modal) modal.classList.remove("hidden");
}

async function saveConnectionModal() {
  const editId = document.getElementById("conn-edit-id").value;
  const name = document.getElementById("conn-input-name").value.trim();
  const key = document.getElementById("conn-input-key").value.trim();
  const priority = parseInt(document.getElementById("conn-input-priority").value) || 1;

  if (!editId && !key) {
    alert("Please enter a valid API Key.");
    return;
  }

  try {
    if (editId) {
      const res = await fetch("/api/providers/connections/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: editId, name, key, priority, provider: currentSelectedProvider }),
      });
      const data = await res.json();
      if (data.success) {
        closeSubModal("modal-add-connection");
        loadProviderDetails(currentSelectedProvider);
      } else {
        alert("Error updating connection: " + (data.error || "Failed"));
      }
    } else {
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
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function toggleProviderRoundRobin(checked) {
  if (!currentSelectedProvider) return;
  const mode = checked ? "round-robin" : "priority";
  try {
    await fetch("/api/providers/mode/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider, mode }),
    });
  } catch (err) {
    console.error("Error saving round robin mode:", err);
  }
}

function toggleSelectAllProviderConns(checked) {
  if (!currentProviderData || !currentProviderData.connections) return;
  if (checked) {
    currentProviderData.connections.forEach(c => _vfSelectedConnIds.add(c.id));
  } else {
    _vfSelectedConnIds.clear();
  }
  loadProviderDetails(currentSelectedProvider);
}

function toggleSelectProviderConn(cid, checked) {
  if (checked) {
    _vfSelectedConnIds.add(cid);
  } else {
    _vfSelectedConnIds.delete(cid);
  }
  const selectAllBox = document.getElementById("vf-select-all-conns");
  if (selectAllBox && currentProviderData && currentProviderData.connections) {
    selectAllBox.checked = currentProviderData.connections.length > 0 && currentProviderData.connections.every(c => _vfSelectedConnIds.has(c.id));
  }
}

async function testCurrentProviderConnectionsOneByOne() {
  if (_vfOneByOneRunning || !currentProviderData || !currentProviderData.connections) return;
  _vfOneByOneRunning = true;

  const btn = document.getElementById("btn-test-conn-one-by-one");
  const spinner = document.getElementById("test-conn-spinner");
  const label = document.getElementById("test-conn-btn-label");

  if (spinner) spinner.style.display = "inline-block";
  if (label) label.textContent = "Testing...";
  if (btn) btn.disabled = true;

  try {
    const allConns = currentProviderData.connections;
    const selected = allConns.filter(c => _vfSelectedConnIds.has(c.id));
    const conns = selected.length ? selected : allConns.filter(c => c.is_active !== false && c.is_active !== 0);
    for (let i = 0; i < conns.length; i++) {
      const c = conns[i];
      if (label) label.textContent = `Testing (${i + 1}/${conns.length})...`;
      await fetch("/api/providers/connections/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Server resolves the real key from the connection id (list keys are masked).
        body: JSON.stringify({ id: c.id, provider: currentSelectedProvider }),
      });
    }
  } catch (err) {
    console.error("Error in one-by-one test:", err);
  } finally {
    _vfOneByOneRunning = false;
    if (spinner) spinner.style.display = "none";
    if (label) label.textContent = "Test Connection One-by-One";
    if (btn) btn.disabled = false;
    loadProviderDetails(currentSelectedProvider);
  }
}

function changeThinkingMode(mode) {
  console.log("Thinking mode set to:", mode);
}

async function testSingleModel(modelId, btnEl) {
  const targetProvider = currentSelectedProvider;
  if (!targetProvider) return;

  _vfTestingModelIds.add(modelId);
  loadProviderDetails(targetProvider);

  try {
    const fullId = `${targetProvider}/${modelId}`;
    const isGoogleFamily = ["gemini", "google", "googleai"].includes(targetProvider);
    const isStt = !isGoogleFamily && (/whisper|transcri|stt$|nova|universal|scribe|speechmatics|listen/i.test(modelId) || ["deepgram", "assemblyai", "speechmatics"].includes(targetProvider));
    const kind = isStt ? "stt" : "llm";

    const res = await fetch("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, model_ref: fullId, provider: targetProvider, kind: kind }),
    });
    const data = await res.json();
    const isOk = Boolean(data.success && data.ok !== false);
    _vfProviderModelTestResults[modelId] = {
      ok: isOk,
      latency_ms: data.latency_ms || null,
      error: data.error || null,
    };

    if (isOk) {
      delete _vfProviderModelErrors[targetProvider];
    } else {
      _vfProviderModelErrors[targetProvider] = {
        modelId: modelId,
        error: data.error || "Model test failed",
      };
    }

    if (currentSelectedProvider === targetProvider) {
      const errBanner = document.getElementById("models-test-error-banner");
      if (errBanner) {
        if (!isOk && data.error) {
          errBanner.textContent = `✕ Model Test Failed (${modelId}): ${data.error}`;
          errBanner.style.display = "block";
        } else if (isOk) {
          errBanner.textContent = "";
          errBanner.style.display = "none";
        }
      }
    }
  } catch (err) {
    _vfProviderModelTestResults[modelId] = { ok: false, latency_ms: null, error: err.message };
    _vfProviderModelErrors[targetProvider] = {
      modelId: modelId,
      error: err.message,
    };
    if (currentSelectedProvider === targetProvider) {
      const errBanner = document.getElementById("models-test-error-banner");
      if (errBanner) {
        errBanner.textContent = `✕ Model Test Failed (${modelId}): ${err.message}`;
        errBanner.style.display = "block";
      }
    }
  } finally {
    _vfTestingModelIds.delete(modelId);
    if (currentSelectedProvider === targetProvider) {
      loadProviderDetails(targetProvider);
    }
  }
}

function copyModelId(fullId, btnEl) {
  navigator.clipboard.writeText(fullId).then(() => {
    if (btnEl) {
      // SVG icon buttons must not use textContent: that deletes the inline
      // SVG child nodes permanently. They toggle a class instead, and CSS
      // swaps the copy glyph for a check.
      if (btnEl.querySelector("svg")) {
        btnEl.classList.add("copied");
        setTimeout(() => { btnEl.classList.remove("copied"); }, 1500);
      } else {
        const orig = btnEl.textContent;
        btnEl.textContent = "✓ Copied!";
        setTimeout(() => { btnEl.textContent = orig; }, 1500);
      }
    }
  }).catch(() => {
    alert("Copied: " + fullId);
  });
}

async function disableModel(mid) {
  try {
    await fetch("/api/providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, provider: currentSelectedProvider, is_active: false }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error disabling model:", err);
  }
}

async function enableModel(mid) {
  try {
    await fetch("/api/providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, provider: currentSelectedProvider, is_active: true }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error enabling model:", err);
  }
}

async function enableAllProviderModels() {
  if (!currentSelectedProvider) return;
  try {
    await fetch("/api/providers/models/enable-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error enabling all models:", err);
  }
}

async function disableAllProviderModels() {
  if (!currentSelectedProvider) return;
  try {
    await fetch("/api/providers/models/disable-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentSelectedProvider }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error disabling all models:", err);
  }
}

async function toggleProviderConn(cid, isActive) {
  try {
    await fetch("/api/providers/connections/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: currentSelectedProvider, is_active: isActive }),
    });
    loadProviderDetails(currentSelectedProvider);
  } catch (err) {
    console.error("Error toggling connection:", err);
  }
}

async function deleteConn(cid) {
  if (!await vfConfirm("Are you sure you want to delete this connection key?")) return;

  try {
    await fetch("/api/providers/connections/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: currentSelectedProvider }),
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
      // Never send the key back: list endpoints return masked values, and
      // the server resolves the real key from the connection id.
      body: JSON.stringify({ id: cid, provider: currentSelectedProvider }),
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

let vf2LastVerifiedMainModel = null;
let vf2LastVerifiedAudioModel = null;

function vf2StripRedundantModelPrefix(provider, modelId) {
  if (typeof window.stripRedundantModelPrefix === "function") {
    return window.stripRedundantModelPrefix(provider, modelId);
  }
  let mid = (modelId || "").trim();
  const prov = (provider || "").toLowerCase().trim();
  if (!mid) return "";
  if (prov === "openrouter") {
    while (mid.toLowerCase().startsWith("openrouter/")) mid = mid.slice("openrouter/".length).trim();
    return mid;
  }
  if (prov === "together" || prov === "together_ai") {
    while (mid.toLowerCase().startsWith("together/") || mid.toLowerCase().startsWith("together_ai/")) {
      const pfx = mid.toLowerCase().startsWith("together_ai/") ? "together_ai/" : "together/";
      mid = mid.slice(pfx.length).trim();
    }
    return mid;
  }
  if (prov === "nvidia_nim" || prov === "nim" || prov === "nvidia") {
    while (mid.toLowerCase().startsWith("nvidia_nim/") || mid.toLowerCase().startsWith("nim/")) {
      const pfx = mid.toLowerCase().startsWith("nvidia_nim/") ? "nvidia_nim/" : "nim/";
      mid = mid.slice(pfx.length).trim();
    }
    return mid;
  }
  if (prov === "cloudflare") {
    while (mid.toLowerCase().startsWith("cloudflare/") || mid.toLowerCase().startsWith("cf/")) {
      const pfx = mid.toLowerCase().startsWith("cloudflare/") ? "cloudflare/" : "cf/";
      mid = mid.slice(pfx.length).trim();
    }
    return mid;
  }
  if (prov.startsWith("custom-")) {
    const pfx = prov + "/";
    if (mid.toLowerCase().startsWith(pfx.toLowerCase())) mid = mid.slice(pfx.length).trim();
    return mid;
  }
  const aliases = [prov ? prov + "/" : ""];
  if (prov === "antigravity" || prov === "agy") aliases.push("agy/", "antigravity/");
  else if (prov === "openai_codex" || prov === "chatgpt" || prov === "codex") aliases.push("openai_codex/", "chatgpt/", "codex/");
  else if (prov === "vertex_ai" || prov === "vx" || prov === "vertex") aliases.push("vertex_ai/", "vx/", "vertex/");
  else if (prov === "gemini" || prov === "google" || prov === "googleai") aliases.push("gemini/", "google/", "googleai/");
  else if (prov === "anthropic" || prov === "claude") aliases.push("anthropic/", "claude/");
  aliases.push("models/");
  while (true) {
    let stripped = false;
    for (const a of aliases) {
      if (a && mid.toLowerCase().startsWith(a.toLowerCase())) {
        mid = mid.slice(a.length).trim();
        stripped = true;
        break;
      }
    }
    if (!stripped) break;
  }
  return mid;
}

function openAddModelModal(prov) {
  const modal = document.getElementById("modal-add-model");
  if (!modal) return;
  if (prov) {
    currentSelectedProvider = prov;
  }
  modal.dataset.provider = prov || currentSelectedProvider || "";
  const inputEl = document.getElementById("model-input-id");
  if (inputEl) inputEl.value = "";
  const out = document.getElementById("vf2-addmodel-test-out");
  if (out) { out.style.display = "none"; out.innerHTML = ""; }
  vf2LastVerifiedMainModel = null;
  modal.classList.remove("hidden");
  setTimeout(() => inputEl?.focus(), 50);
}

function vf2DetectMainKind(prov, mid) {
  const p = (prov || "").toLowerCase();
  const m = (mid || "").toLowerCase();
  if (["deepgram", "assemblyai", "speechmatics"].includes(p)) return "stt";
  if (/whisper|transcri|stt$|nova|universal|scribe|speechmatics|listen/.test(m)) return "stt";
  if (["edge", "elevenlabs", "fish", "cartesia", "playht"].includes(p) || m.startsWith("audio-")) return "tts";
  return "llm";
}

async function vf2TestMainModel() {
  const modal = document.getElementById("modal-add-model");
  let provider = modal?.dataset.provider || currentSelectedProvider || "";
  if (provider === "agy") provider = "antigravity";
  let rawMid = (document.getElementById("model-input-id")?.value || "").trim();
  const out = document.getElementById("vf2-addmodel-test-out");
  const spin = document.getElementById("vf2-addmodel-test-spin");
  const label = document.getElementById("vf2-addmodel-test-label");
  const btn = document.getElementById("vf2-addmodel-test-btn");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.textContent = "Enter a model ID first.";
    }
    return false;
  }
  const mid = vf2StripRedundantModelPrefix(provider, rawMid);
  const fullId = (provider ? provider + "/" : "") + mid;
  const kind = vf2DetectMainKind(provider, mid);
  if (spin) spin.style.display = "inline";
  if (label) label.textContent = "Testing…";
  if (btn) btn.disabled = true;
  if (out) {
    out.style.display = "block";
    out.style.background = "rgba(255,255,255,0.04)";
    out.style.border = "1px solid var(--border-color, rgba(255,255,255,0.1))";
    out.style.color = "var(--text-muted, #9ca3af)";
    out.textContent = "Sending a test request to " + fullId + " …";
  }
  try {
    const resp = await fetch("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model_id: mid, model_ref: fullId, kind }),
    });
    let data;
    try {
      data = await resp.json();
    } catch (_) {
      data = { success: false, error: "HTTP " + resp.status + " " + resp.statusText };
    }
    const ok = Boolean(data && data.success && data.ok !== false);
    if (ok) {
      vf2LastVerifiedMainModel = { provider, modelId: mid, ok: true, data };
      if (out) {
        const latencyText = data.latency_ms ? " (" + data.latency_ms + "ms)" : "";
        const quotaText = data.remaining_pct != null ? " — " + data.remaining_pct + "% quota remaining" : "";
        const msgText = data.message ? `<div style="margin-top:4px; font-size:11px; opacity:0.9;">${escapeHtml(data.message)}</div>` : "";
        out.style.background = "rgba(34,197,94,0.08)";
        out.style.border = "1px solid rgba(34,197,94,0.25)";
        out.style.color = "#22c55e";
        out.innerHTML = "✅ Model works" + latencyText + quotaText + msgText;
      }
      return true;
    } else {
      vf2LastVerifiedMainModel = { provider, modelId: mid, ok: false, error: (data && data.error) || "Test failed" };
      if (out) {
        out.style.background = "rgba(239,68,68,0.08)";
        out.style.border = "1px solid rgba(239,68,68,0.25)";
        out.style.color = "#ef4444";
        out.innerHTML = "❌ " + escapeHtml((data && data.error) || "Test failed") + "<br><span style='opacity:0.8;'>Sent to provider as: " + escapeHtml(fullId) + "</span>";
      }
      return false;
    }
  } catch (err) {
    vf2LastVerifiedMainModel = { provider, modelId: mid, ok: false, error: err.message || "Test failed" };
    if (out) {
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + escapeHtml(err.message || "Test failed");
    }
    return false;
  } finally {
    if (spin) spin.style.display = "none";
    if (label) label.textContent = "🧪 Test";
    if (btn) btn.disabled = false;
  }
}

// ---- Audio Flow: Add Voice model (9Router-style, test before add) ----
function openAddAudioModelModal(prov) {
  const modal = document.getElementById("modal-add-audio-model");
  if (!modal) return;
  if (prov) {
    currentAudioProvider = prov;
  }
  modal.dataset.provider = prov || currentAudioProvider || "";
  const inputEl = document.getElementById("audio-model-input-id");
  if (inputEl) inputEl.value = "";
  const out = document.getElementById("vf2-addaudio-test-out");
  if (out) { out.style.display = "none"; out.innerHTML = ""; }
  vf2LastVerifiedAudioModel = null;
  modal.classList.remove("hidden");
  setTimeout(() => inputEl?.focus(), 50);
}

async function vf2TestAudioModel() {
  const modal = document.getElementById("modal-add-audio-model");
  const provider = modal?.dataset.provider || currentAudioProvider || "";
  let rawMid = (document.getElementById("audio-model-input-id")?.value || "").trim();
  const out = document.getElementById("vf2-addaudio-test-out");
  const spin = document.getElementById("vf2-addaudio-test-spin");
  const label = document.getElementById("vf2-addaudio-test-label");
  const btn = document.getElementById("vf2-addaudio-test-btn");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.textContent = "Enter a model ID first.";
    }
    return false;
  }
  const mid = vf2StripRedundantModelPrefix(provider, rawMid);
  const fullId = (provider ? provider + "/" : "") + mid;
  if (spin) spin.style.display = "inline";
  if (label) label.textContent = "Testing…";
  if (btn) btn.disabled = true;
  if (out) {
    out.style.display = "block";
    out.style.background = "rgba(255,255,255,0.04)";
    out.style.border = "1px solid var(--border-color, rgba(255,255,255,0.1))";
    out.style.color = "var(--text-muted, #9ca3af)";
    out.textContent = "Sending a test request to " + fullId + " …";
  }
  try {
    const resp = await fetch("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model_id: mid, model_ref: fullId, kind: "tts" }),
    });
    let data;
    try {
      data = await resp.json();
    } catch (_) {
      data = { success: false, error: "HTTP " + resp.status + " " + resp.statusText };
    }
    const ok = Boolean(data && data.success && data.ok !== false);
    if (ok) {
      vf2LastVerifiedAudioModel = { provider, modelId: mid, ok: true, data };
      if (out) {
        out.style.background = "rgba(34,197,94,0.08)";
        out.style.border = "1px solid rgba(34,197,94,0.25)";
        out.style.color = "#22c55e";
        out.innerHTML = "✅ Voice model works" + (data.latency_ms ? " — " + data.latency_ms + "ms" : "");
      }
      return true;
    } else {
      vf2LastVerifiedAudioModel = { provider, modelId: mid, ok: false, error: (data && data.error) || "Test failed" };
      if (out) {
        out.style.background = "rgba(239,68,68,0.08)";
        out.style.border = "1px solid rgba(239,68,68,0.25)";
        out.style.color = "#ef4444";
        out.innerHTML = "❌ " + escapeHtml((data && data.error) || "Test failed") + "<br><span style='opacity:0.8;'>Sent to provider as: " + escapeHtml(fullId) + "</span>";
      }
      return false;
    }
  } catch (err) {
    vf2LastVerifiedAudioModel = { provider, modelId: mid, ok: false, error: err.message || "Test failed" };
    if (out) {
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + escapeHtml(err.message || "Test failed");
    }
    return false;
  } finally {
    if (spin) spin.style.display = "none";
    if (label) label.textContent = "🧪 Test";
    if (btn) btn.disabled = false;
  }
}

async function saveAudioCustomModelModal() {
  const modal = document.getElementById("modal-add-audio-model");
  const provider = modal?.dataset.provider || currentAudioProvider || "";
  let rawMid = (document.getElementById("audio-model-input-id")?.value || "").trim();
  const out = document.getElementById("vf2-addaudio-test-out");
  const addBtn = modal?.querySelector(".btn-primary");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.textContent = "Please enter a model ID.";
    } else {
      alert("Please enter a model ID.");
    }
    return;
  }
  const mid = vf2StripRedundantModelPrefix(provider, rawMid);
  const isVerified = Boolean(
    vf2LastVerifiedAudioModel &&
    vf2LastVerifiedAudioModel.provider === provider &&
    vf2LastVerifiedAudioModel.modelId === mid &&
    vf2LastVerifiedAudioModel.ok === true
  );

  if (!isVerified) {
    if (addBtn) { addBtn.disabled = true; addBtn.textContent = "Verifying…"; }
    const verifiedOk = await vf2TestAudioModel();
    if (addBtn) { addBtn.disabled = false; addBtn.textContent = "Add Voice"; }
    if (!verifiedOk) {
      // Model verification failed: do NOT add voice!
      return;
    }
  }

  try {
    const res = await fetch("/api/audio-providers/models/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model_id: mid, display_name: mid }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error((data && data.error) || "Failed to add voice model.");
    }
    closeSubModal("modal-add-audio-model");
    if (typeof loadAudioProviderDetails === "function" && currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
    else if (typeof loadAudioProvidersOverview === "function") loadAudioProvidersOverview();
    if (typeof vfToast === "function") {
      const lat = vf2LastVerifiedAudioModel?.data?.latency_ms ? ` (${vf2LastVerifiedAudioModel.data.latency_ms}ms)` : "";
      vfToast(`Voice model '${mid}' verified and added successfully!${lat}`);
    }
  } catch (err) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + escapeHtml(err.message || "Failed to add model");
    } else {
      alert("Error: " + err.message);
    }
  }
}

async function saveCustomModelModal() {
  const modal = document.getElementById("modal-add-model");
  let provider = modal?.dataset.provider || currentSelectedProvider || "";
  if (provider === "agy") provider = "antigravity";
  let rawMid = (document.getElementById("model-input-id")?.value || "").trim();
  const out = document.getElementById("vf2-addmodel-test-out");
  const addBtn = modal?.querySelector(".btn-primary");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.textContent = "Please enter a model ID.";
    } else {
      alert("Please enter a model ID.");
    }
    return;
  }
  const modelId = vf2StripRedundantModelPrefix(provider, rawMid);
  const isVerified = Boolean(
    vf2LastVerifiedMainModel &&
    vf2LastVerifiedMainModel.provider === provider &&
    vf2LastVerifiedMainModel.modelId === modelId &&
    vf2LastVerifiedMainModel.ok === true
  );

  if (!isVerified) {
    if (addBtn) { addBtn.disabled = true; addBtn.textContent = "Verifying…"; }
    const verifiedOk = await vf2TestMainModel();
    if (addBtn) { addBtn.disabled = false; addBtn.textContent = "Add Model"; }
    if (!verifiedOk) {
      // Model verification failed: do NOT add model!
      return;
    }
  }

  try {
    const res = await fetch("/api/providers/models/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model_id: modelId, display_name: "" }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error((data && data.error) || "Failed to add model.");
    }
    closeSubModal("modal-add-model");
    loadProviderDetails(provider);
    if (typeof vfToast === "function") {
      const lat = vf2LastVerifiedMainModel?.data?.latency_ms ? ` (${vf2LastVerifiedMainModel.data.latency_ms}ms)` : "";
      vfToast(`Model '${modelId}' verified and added successfully!${lat}`);
    }
  } catch (err) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + escapeHtml(err.message || "Failed to add model");
    } else {
      alert("Error: " + err.message);
    }
  }
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
        // Server resolves the real key from the connection id (masked in list responses).
        body: JSON.stringify({ id: c.id, provider: pid }),
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

// ─────────────────────────────────────────────────────────────────────────────
// AUDIO FLOW SUMMARY HISTORY
// ─────────────────────────────────────────────────────────────────────────────

let afSummaries = [];
let afLibraryQuery = "";
let afLibraryFilter = "all";
let afLibraryControlsWired = false;
let afOpenMenuId = null;

function afEscape(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function afFormatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function afFormatDuration(seconds) {
  const total = Math.round(Number(seconds || 0));
  if (!Number.isFinite(total) || total <= 0) return "";
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function afLibraryBucket(summary) {
  const status = String(summary.status || "ready").toLowerCase().trim();
  if (status === "cancelled") return "cancelled";
  if (status === "failed" || summary.error) return "needs_attention";
  if (status === "in_progress" || status === "generating") return "in_progress";
  return "ready";
}

function afLibraryStatusLabel(summary) {
  const bucket = afLibraryBucket(summary);
  if (bucket === "ready") return "Ready";
  if (bucket === "needs_attention") return "Needs attention";
  if (bucket === "cancelled") return "Cancelled";
  return "In progress";
}

function afWireLibraryControls() {
  if (afLibraryControlsWired) return;
  const searchInput = document.getElementById("af-library-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      afLibraryQuery = e.target.value.trim().toLowerCase();
      renderAudioSummaryHistory();
    });
  }

  const filterContainer = document.getElementById("af-library-filters");
  if (filterContainer) {
    filterContainer.querySelectorAll("[data-af-filter]").forEach(btn => {
      btn.addEventListener("click", () => {
        const filter = btn.getAttribute("data-af-filter");
        afSetLibraryFilter(filter);
      });
    });
  }

  document.addEventListener("click", (e) => {
    if (afOpenMenuId && !e.target.closest(".af-menu-wrap")) {
      afCloseAllMenus();
    }
  });

  afLibraryControlsWired = true;
}

function afSetLibraryFilter(nextFilter) {
  afLibraryFilter = ["all", "ready", "in_progress", "needs_attention", "cancelled"].includes(nextFilter) ? nextFilter : "all";
  const filterContainer = document.getElementById("af-library-filters");
  if (filterContainer) {
    filterContainer.querySelectorAll("[data-af-filter]").forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-af-filter") === afLibraryFilter);
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-af-filter") === afLibraryFilter));
    });
  }
  renderAudioSummaryHistory();
}

function afClearLibraryFilters() {
  afLibraryQuery = "";
  afLibraryFilter = "all";
  const search = document.getElementById("af-library-search");
  if (search) search.value = "";
  const filterContainer = document.getElementById("af-library-filters");
  if (filterContainer) {
    filterContainer.querySelectorAll("[data-af-filter]").forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-af-filter") === "all");
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-af-filter") === "all"));
    });
  }
  renderAudioSummaryHistory();
  search?.focus();
}

function afUpdateLibraryFilterCounts() {
  const filterContainer = document.getElementById("af-library-filters");
  const totals = { all: afSummaries.length, ready: 0, in_progress: 0, needs_attention: 0, cancelled: 0 };
  for (const s of afSummaries) {
    const bucket = afLibraryBucket(s);
    totals[bucket] = (totals[bucket] || 0) + 1;
  }

  if (filterContainer) {
    const labels = {
      all: "All",
      ready: "Ready",
      in_progress: "In progress",
      needs_attention: "Needs attention",
      cancelled: "Cancelled",
    };
    filterContainer.querySelectorAll("[data-af-filter]").forEach(btn => {
      const key = btn.getAttribute("data-af-filter");
      const n = totals[key] || 0;
      btn.textContent = `${labels[key] || key} (${n})`;
      btn.classList.toggle("active", key === afLibraryFilter);
    });
  }

  const countBadge = document.getElementById("af-history-count");
  if (countBadge) {
    if (afSummaries.length === 0) {
      countBadge.textContent = "Your generated summaries appear here";
    } else {
      countBadge.textContent = `${afSummaries.length} ${afSummaries.length === 1 ? "summary" : "summaries"} saved`;
    }
  }

  const pillCount = document.getElementById("af-history-pill-count");
  if (pillCount) {
    pillCount.textContent = `${afSummaries.length} ${afSummaries.length === 1 ? "summary" : "summaries"}`;
  }
  const barSubtitle = document.getElementById("af-history-bar-subtitle");
  if (barSubtitle) {
    if (afSummaries.length === 0) {
      barSubtitle.textContent = "Click to view past audio summaries (none saved yet)";
    } else {
      barSubtitle.textContent = `Click to view and manage ${afSummaries.length} past ${afSummaries.length === 1 ? "summary" : "summaries"}`;
    }
  }
}

async function loadAudioSummaryHistory() {
  afWireLibraryControls();
  try {
    const res = await fetch("/api/audio-flow/history");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.success && Array.isArray(data.summaries)) {
      afSummaries = data.summaries;
    } else {
      afSummaries = [];
    }
  } catch (err) {
    console.warn("Could not load audio summary history:", err);
    afSummaries = [];
  }
  afUpdateLibraryFilterCounts();
  renderAudioSummaryHistory();
}

function afToggleMenu(id, e) {
  if (e) e.stopPropagation();
  if (afOpenMenuId === id) {
    afCloseAllMenus();
  } else {
    afCloseAllMenus();
    const menu = document.getElementById(`af-menu-${id}`);
    if (menu) {
      menu.style.display = "flex";
      afOpenMenuId = id;
    }
  }
}

function afCloseAllMenus() {
  document.querySelectorAll(".af-menu-dropdown").forEach(m => {
    m.style.display = "none";
  });
  afOpenMenuId = null;
}

function renderAudioSummaryHistory() {
  const cardsContainer = document.getElementById("af-library-cards");
  const emptyState = document.getElementById("af-history-empty");
  const noMatchState = document.getElementById("af-library-nomatch");
  const gridContainer = document.getElementById("af-library-grid");

  if (!cardsContainer) return;

  if (afSummaries.length === 0) {
    if (emptyState) emptyState.style.display = "flex";
    if (noMatchState) noMatchState.style.display = "none";
    if (gridContainer) gridContainer.style.display = "none";
    cardsContainer.innerHTML = "";
    return;
  }

  // Filter
  const filtered = afSummaries.filter(s => {
    const bucket = afLibraryBucket(s);
    if (afLibraryFilter !== "all" && bucket !== afLibraryFilter) return false;
    if (afLibraryQuery) {
      const q = afLibraryQuery;
      const haystack = [
        s.title,
        s.text_snippet,
        s.full_text,
        s.depth,
        s.status,
      ].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    if (emptyState) emptyState.style.display = "none";
    if (noMatchState) noMatchState.style.display = "flex";
    if (gridContainer) gridContainer.style.display = "none";
    cardsContainer.innerHTML = "";
    return;
  }

  if (emptyState) emptyState.style.display = "none";
  if (noMatchState) noMatchState.style.display = "none";
  if (gridContainer) gridContainer.style.display = "block";

  cardsContainer.innerHTML = filtered.map(s => {
    const bucket = afLibraryBucket(s);
    const statusLabel = afLibraryStatusLabel(s);
    const isReady = bucket === "ready";
    const isInProgress = bucket === "in_progress";
    const isFailed = bucket === "needs_attention";
    const isCancelled = bucket === "cancelled";

    const title = s.title || s.text_snippet || "Audio Summary";
    const duration = afFormatDuration(s.duration_sec);
    const dateStr = afFormatDate(s.created_at);
    const depthLabel = (s.depth || "balanced").replace("_", " ");
    const downloadUrl = s.download_url || `/api/audio-flow/summary/media?id=${encodeURIComponent(s.id)}&download=1`;

    let progressHtml = "";
    if (isInProgress) {
      const p = Math.max(0, Math.min(100, Number(s.progress || 0)));
      progressHtml = `
        <div style="margin: 6px 0;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--studio-muted); margin-bottom: 4px;">
            <span>Generating audio with NotebookLM…</span>
            <span>${p}%</span>
          </div>
          <div style="height: 4px; background: var(--studio-well); border-radius: 2px; overflow: hidden;">
            <div style="width: ${p}%; height: 100%; background: var(--studio-copper); transition: width 300ms ease;"></div>
          </div>
        </div>`;
    }

    let errorHtml = "";
    if (isFailed && s.error) {
      errorHtml = `<p class="af-card-snippet" style="color: #dc2626; font-size: 12px; margin: 4px 0;">⚠ ${afEscape(s.error)}</p>`;
    } else if (isCancelled) {
      errorHtml = `<p class="af-card-snippet" style="color: var(--studio-muted); font-size: 12px; margin: 4px 0;">Cancelled — summary generation was stopped.</p>`;
    } else if (s.text_snippet) {
      errorHtml = `<p class="af-card-snippet">${afEscape(s.text_snippet)}</p>`;
    }

    let actionButtons = "";
    if (isReady) {
      actionButtons += `
        <button type="button" class="af-icon-btn" onclick="playAudioSummary('${afEscape(s.id)}', '${afEscape(title)}', '${afEscape(s.depth || 'balanced')}')">▶ Play</button>
        <button type="button" class="af-icon-btn af-download-btn" onclick="downloadAudioSummary('${afEscape(s.id)}', this, '${afEscape(title)}')" title="Download MP3 audio">↓ MP3</button>`;
    }

    actionButtons += `
      <div class="af-menu-wrap">
        <button type="button" class="af-menu-trigger" onclick="afToggleMenu('${afEscape(s.id)}', event)" aria-label="More actions">⋯</button>
        <div class="af-menu-dropdown" id="af-menu-${afEscape(s.id)}" style="display: none;">
          <button type="button" onclick="shareAudioSummary('${afEscape(s.id)}'); afCloseAllMenus();">📋 Share text</button>
          <button type="button" class="danger" onclick="deleteAudioSummary('${afEscape(s.id)}'); afCloseAllMenus();">🗑 Delete</button>
        </div>
      </div>`;

    return `
      <article class="af-library-card" id="af-card-${afEscape(s.id)}">
        <div class="af-card-thumb">
          <div class="af-thumb-art">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v18M16 8v8M8 8v8M20 11v2M4 11v2"/>
            </svg>
          </div>
          <span class="af-card-status af-card-status-${bucket}">${statusLabel}</span>
        </div>
        <div class="af-card-body">
          <h3 class="af-card-title" title="${afEscape(title)}">${afEscape(title)}</h3>
          <div class="af-card-meta">
            <span>${dateStr}</span>
            ${duration ? `<span>· ${duration}</span>` : ""}
            <span class="af-depth-pill">${depthLabel}</span>
          </div>
          ${errorHtml}
          ${progressHtml}
          <details class="af-card-details">
            <summary>Details</summary>
            <div class="af-card-details-body">
              <div class="af-card-detail-row"><span>Type</span><span>NotebookLM Audio Summary</span></div>
              <div class="af-card-detail-row"><span>Depth</span><span style="text-transform: capitalize;">${afEscape(s.depth || "balanced")}</span></div>
              <div class="af-card-detail-row"><span>Status</span><span style="text-transform: capitalize;">${afEscape(s.status || "ready")}</span></div>
              <div class="af-card-detail-row"><span>Summary ID</span><code>${afEscape(s.id)}</code></div>
              ${s.duration_sec ? `<div class="af-card-detail-row"><span>Duration</span><span>${duration} (${Math.round(s.duration_sec)}s)</span></div>` : ""}
              ${s.error ? `<div class="af-card-detail-row" style="color: #dc2626;"><span>Error</span><span>${afEscape(s.error)}</span></div>` : ""}
            </div>
          </details>
          <div class="af-card-actions">
            ${actionButtons}
          </div>
        </div>
      </article>`;
  }).join("");
}

async function playAudioSummary(id, title, depth) {
  try {
    const res = await fetch("/api/audio-flow/history/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: id,
        title: title || "Audio Summary",
        depth: depth || "balanced",
      }),
    });
    const data = await res.json();
    if (data.success) {
      if (typeof showToast === "function") {
        showToast("Opening floating player...", "🎧");
      }
      return;
    }
    console.warn("API playAudioSummary notice:", data.error);
  } catch (err) {
    console.warn("Could not launch native floating audio player via API:", err);
  }
  // Fallback: only if native launch fails, open small popup window (not full blank tab)
  const url = `/audio-summary-player.html?id=${encodeURIComponent(id)}&title=${encodeURIComponent(title || "Audio Summary")}&depth=${encodeURIComponent(depth || "balanced")}`;
  const w = 390;
  const h = 270;
  const left = Math.max(0, Math.round((window.screen.width - w) / 2));
  const top = Math.max(0, Math.round((window.screen.height - h) / 2));
  window.open(url, `af_player_${id}`, `width=${w},height=${h},top=${top},left=${left},resizable=yes,scrollbars=no,status=no`);
}

function afSafeMediaFilename(title, defaultName = "Audio Summary", ext = ".mp3") {
  let clean = (title || "").trim();
  clean = clean.replace(/[<>:"/\\|?*\x00-\x1f]/g, "").replace(/\s+/g, " ").trim();
  const reserved = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$/i;
  if (!clean || reserved.test(clean)) {
    clean = defaultName;
  }
  if (clean.length > 120) {
    clean = clean.slice(0, 120).trim();
  }
  if (!ext.startsWith(".")) ext = "." + ext;
  if (!clean.toLowerCase().endsWith(ext.toLowerCase())) {
    clean = clean.replace(/\.[a-zA-Z0-9]{2,5}$/, "") + ext;
  }
  return clean;
}

async function downloadAudioSummary(id, btn, customTitle) {
  if (!id) return;
  if (btn && btn.classList.contains("is-downloading")) return;

  const originalHtml = btn ? btn.innerHTML : "↓ MP3";
  if (btn) {
    btn.classList.add("is-downloading");
    btn.disabled = true;
    btn.innerHTML = `<span class="af-dl-spinner"></span> Downloading...`;
  }

  try {
    const summary = (typeof afHistorySummaries !== "undefined" && Array.isArray(afHistorySummaries))
      ? afHistorySummaries.find(s => String(s.id) === String(id))
      : null;
    const title = (customTitle || (summary ? (summary.title || summary.text_snippet) : "") || "Audio Summary").trim();
    const mediaUrl = `/api/audio-flow/summary/media?id=${encodeURIComponent(id)}&download=1&format=mp3&title=${encodeURIComponent(title)}`;
    const response = await fetch(mediaUrl);
    if (!response.ok) {
      throw new Error(`Failed to download audio (${response.status})`);
    }

    const contentLength = response.headers.get("Content-Length");
    let blob;

    if (contentLength && window.ReadableStream && response.body) {
      const total = parseInt(contentLength, 10);
      let loaded = 0;
      const reader = response.body.getReader();
      const chunks = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        loaded += value.length;
        if (total > 0 && btn) {
          const pct = Math.min(99, Math.round((loaded / total) * 100));
          btn.innerHTML = `<span class="af-dl-spinner"></span> ${pct}%`;
        }
      }
      blob = new Blob(chunks, { type: "audio/mpeg" });
    } else {
      const rawBlob = await response.blob();
      blob = new Blob([rawBlob], { type: "audio/mpeg" });
    }

    const disposition = response.headers.get("Content-Disposition") || "";
    let filename = afSafeMediaFilename(title, "Audio Summary", ".mp3");
    if (disposition.includes("filename*=UTF-8''")) {
      const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
      if (match && match[1]) {
        try {
          filename = decodeURIComponent(match[1].trim());
        } catch (_) {}
      }
    } else if (disposition.includes("filename=")) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/);
      if (match && match[1]) filename = match[1].trim();
    }
    if (!filename.toLowerCase().endsWith(".mp3")) {
      filename = filename.replace(/\.[a-zA-Z0-9]{2,5}$/, "") + ".mp3";
    }

    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(blobUrl), 15000);

    if (btn) {
      btn.classList.remove("is-downloading");
      btn.classList.add("is-success");
      btn.innerHTML = `✓ Downloaded!`;
    }
    if (typeof showToast === "function") {
      showToast(`Downloaded "${filename}"`, "🎵");
    }

    setTimeout(() => {
      if (btn) {
        btn.classList.remove("is-success");
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }, 2500);
  } catch (err) {
    console.error("Audio summary download failed:", err);
    if (btn) {
      btn.classList.remove("is-downloading");
      btn.classList.add("is-error");
      btn.innerHTML = `⚠ Failed`;
    }
    if (typeof showToast === "function") {
      showToast("Download failed: " + (err.message || "Could not fetch audio"), "⚠️");
    }
    setTimeout(() => {
      if (btn) {
        btn.classList.remove("is-error");
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }, 2500);
  }
}

async function deleteAudioSummary(id) {
  if (!id) return;
  if (!confirm("Are you sure you want to delete this audio summary from history?")) return;
  try {
    const res = await fetch("/api/audio-flow/history/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    if (data.success) {
      if (typeof showToast === "function") showToast("Audio summary deleted", "🗑️");
      await loadAudioSummaryHistory();
    } else {
      if (typeof showToast === "function") showToast(data.error || "Failed to delete summary", "⚠️");
    }
  } catch (err) {
    console.error("Error deleting audio summary:", err);
    if (typeof showToast === "function") showToast("Network error deleting summary", "⚠️");
  }
}

function shareAudioSummary(id) {
  const item = (afSummaries || []).find(s => s.id === id);
  if (!item) return;
  const shareText = `${item.title || "Audio Summary"}\n\n${item.full_text || item.text_snippet || ""}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(shareText).then(() => {
      if (typeof showToast === "function") showToast("Copied summary text to clipboard!", "📋");
    }).catch(() => {
      prompt("Copy summary text:", shareText);
    });
  } else {
    prompt("Copy summary text:", shareText);
  }
}

window.afClearLibraryFilters = afClearLibraryFilters;
window.afSetLibraryFilter = afSetLibraryFilter;
window.playAudioSummary = playAudioSummary;
window.downloadAudioSummary = downloadAudioSummary;
window.deleteAudioSummary = deleteAudioSummary;
window.shareAudioSummary = shareAudioSummary;
window.afToggleMenu = afToggleMenu;
window.afCloseAllMenus = afCloseAllMenus;
window.loadAudioSummaryHistory = loadAudioSummaryHistory;

function loadAudioFlowPage() {
  loadAudioProvidersOverview();
  loadExecAudioFlowPolicy();
  loadAudioSummarySettings();
  initAudioSpeedSelect();
  updateAudioSummaryConnectionUI();
  loadAudioSummaryHistory();
}

let afSummaryModelRef = "";

async function loadAudioSummarySettings() {
  try {
    const res = await fetch("/api/audio-summary/settings/get");
    const data = await res.json();
    if (data.success) {
      afSummaryModelRef = data.model || "";
      const consentBox = document.getElementById("af-summary-external-consent");
      if (consentBox) consentBox.checked = Boolean(data.consent);
      updateAudioSummaryModelUI(afSummaryModelRef);
    }
  } catch (err) {
    console.warn("Could not load Audio Summary settings:", err);
  }
  // Warm the shared catalog so the picker opens instantly.
  if (typeof vfEnsureCatalog === "function") {
    await vfEnsureCatalog();
  }
}

// STALE WIRING FIXED (plan section 6): the Audio Summary engine is now
// NotebookLM-only, so this legacy function must no longer write
// "Voice Flow Local — Deterministic Summary", "Private · offline", or
// "Local Extractive" into the Summary presentation. It remains a safe no-op
// for any caller (the stored ref is tracked by the callers themselves).
function updateAudioSummaryModelUI(modelRef) {
  // Intentionally does not touch the DOM. The Summary card's provider name is
  // fixed ("NotebookLM") and its connection state is rendered by
  // updateAudioSummaryConnectionUI() from the real connection source.
  if (typeof modelRef === "string" && modelRef) {
    afSummaryModelRef = modelRef;
  }
}

// --- NotebookLM connection state for the Summary card ----------------------
// Existing read-only state source: /api/video-flow/notebooklm/status (no
// verify=1, so no external verification call is triggered here). If the real
// state cannot be determined we show "Connection status unavailable" — never
// "Ready", "Local", or "offline".
let _afNlmStatusPromise = null;

function _afMapNlmState(data) {
  if (!data || typeof data !== "object") return null;
  const details = data.details || {};
  if (data.available === false || data.status === "dependency_missing") {
    return { key: "setup", label: "Setup needed — open Manage to finish setup" };
  }
  if (details.disconnected || data.authenticated === false) {
    return { key: "not-connected", label: "Not connected" };
  }
  if (data.authenticated === true) {
    const email = data.email || data.account_email || (details.account && details.account.email) || "";
    return { key: "connected", label: email ? `Connected · ${email}` : "Connected" };
  }
  return null;
}

function updateAudioSummaryConnectionUI(preloadedState) {
  const apply = (state) => {
    const targets = [];
    const newEl = document.getElementById("af-summary-connection-status");
    const legacyEl = document.getElementById("af-summary-status-badge");
    if (newEl) targets.push(newEl);
    if (legacyEl && !targets.includes(legacyEl)) targets.push(legacyEl);
    if (!targets.length) {
      fpWarnOnce("af-summary-connection-status", "No Summary connection status element found (#af-summary-connection-status or legacy #af-summary-status-badge); status not rendered.");
      return;
    }
    for (const el of targets) {
      const stateKey = state ? state.key : "unknown";
      el.textContent = state ? state.label : "Connection status unavailable";
      el.dataset.connectionState = stateKey;
      // Swap exactly one flow-status modifier (drop the initial --unknown).
      for (const cls of Array.from(el.classList)) {
        if (cls.startsWith("flow-status--")) el.classList.remove(cls);
      }
      el.classList.add(`flow-status--${vfFlowStatusMod(stateKey)}`);
    }
  };

  if (preloadedState !== undefined) {
    apply(preloadedState);
    return;
  }

  // Fast path: the cached state that Video Flow's own check populated.
  try {
    const cached = JSON.parse(localStorage.getItem("vf_nlm_auth_cache") || "null");
    if (cached && (cached.authenticated === true || cached.status === "unauthenticated" || cached.status === "ok")) {
      apply(_afMapNlmState(cached));
      // Still refresh from the read-only endpoint without blocking the page.
    }
  } catch (_) { /* ignore malformed cache */ }

  if (!_afNlmStatusPromise) {
    _afNlmStatusPromise = (async () => {
      try {
        const res = await fetch("/api/video-flow/notebooklm/status");
        const data = await res.json();
        return _afMapNlmState(data);
      } catch (err) {
        console.warn("Could not read NotebookLM connection state:", err);
        return null;
      } finally {
        window.setTimeout(() => { _afNlmStatusPromise = null; }, 60000);
      }
    })();
  }
  _afNlmStatusPromise.then(apply);
}

try {
  window.addEventListener("focus", () => {
    _afNlmStatusPromise = null;
    updateAudioSummaryConnectionUI();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      _afNlmStatusPromise = null;
      updateAudioSummaryConnectionUI();
    }
  });
} catch (_) {}

// The one Summary management action: opens the existing NotebookLM account
// area on the Video Flow page. No second authentication implementation.
function manageNotebookLMConnection() {
  switchPage("videoflow");
  window.setTimeout(() => {
    fpScrollToElement(document.getElementById("vf-nlm-account-desc"));
  }, 80);
}

async function selectAudioSummaryModel(modelRef) {
  try {
    const res = await fetch("/api/audio-summary/settings/model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_ref: modelRef }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || "Could not set summary model.");
    afSummaryModelRef = modelRef;
    if (typeof vfToast === "function") vfToast("Audio Summary LLM selected.");
    return { ok: true };
  } catch (err) {
    if (typeof vfToast === "function") vfToast(err.message, true);
    return { ok: false, error: (err && err.message) || "Could not set summary model." };
  }
}

async function toggleAudioSummaryConsent(enabled) {
  try {
    await fetch("/api/audio-summary/settings/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: Boolean(enabled) }),
    });
    if (typeof vfToast === "function") vfToast(`External AI for Audio Summary ${enabled ? "enabled" : "disabled"}.`);
  } catch (err) {
    if (typeof vfToast === "function") vfToast("Could not update summary consent.", true);
  }
}

function openAudioSummaryModelPicker() {
  // Legacy entry point. The redesigned Summary card no longer offers a generic
  // summary-model chooser (NotebookLM is fixed), but the function keeps working.
  openSharedModelPicker("audio_summary");
}

// Audio Flow TTS voice picker state (shared with video-flow.js).
let audioVoicePolicyModels = [];
let audioVoicePolicySet = null;
let audioVoicePolicyModelRef = "";

function openAudioVoiceModelPicker() {
  // The shared picker core loads the TTS catalogue itself (with a loading
  // state) if it has not been fetched yet.
  openSharedModelPicker("audio_voice");
}

async function loadExecAudioFlowPolicy() {
  const labelEl = document.getElementById("exec-audio-policy-model-label");
  const detailEl = document.getElementById("exec-audio-policy-model-detail");
  if (!labelEl) return { ok: false, error: "Reading voice card not present." };

  try {
    const res = await fetch("/api/audio-policy/get");
    const data = await res.json();
    if (!data.success || !data.policy) {
      return { ok: false, error: data.error || "Could not load reading voice settings." };
    }

    const policy = data.policy;
    const activeModel = policy.active_model || "edge/en-US-AvaNeural";
    const models = policy.models || [];
    const grouped = policy.grouped_models || [];

    // Build picker rows from the grouped TTS catalogue. Brain/vision badge
    // flags are intentionally not surfaced: `has_brain` is true for every
    // neural model and `has_vision` is name-heuristic, so they carry no honest
    // signal for a voice choice (plan sections 2/6 — remove Brain badges).
    audioVoicePolicyModels = models.map(m => {
      const provider = String(m.full_id || "").split("/", 1)[0];
      const group = (grouped || []).find(g => (g.models || []).some(gm => gm.full_id === m.full_id));
      return {
        full_id: m.full_id,
        display_name: m.display_name || m.label || m.full_id,
        provider: provider,
        provider_name: (group && group.provider_name) || provider,
        capabilities: [],
      };
    });
    audioVoicePolicySet = models.length ? new Set(models.map(m => m.full_id)) : null;
    audioVoicePolicyModelRef = activeModel;

    const activeObj = models.find(m => m.full_id === activeModel);
    labelEl.textContent = activeObj ? (activeObj.display_name || activeObj.label) : fpPrettifyRef(activeModel);
    if (detailEl) {
      // Service name as the sub-line; raw model ids live in the picker's
      // Details only (plan section 5).
      detailEl.textContent = activeObj
        ? (activeObj.provider_name || activeObj.provider || "Reading voice")
        : "Saved voice";
    }

    // Note: the duplicated engine chip (#exec-audio-active-engine), the
    // Brain/specialty badges (#exec-audio-model-specialty) and the provider
    // failover chip (#exec-audio-failover-count) are no longer written — the
    // Read card shows one voice value + one Change action per plan section 6.

    const toggle = document.getElementById("toggle-audio-flow");
    if (toggle) toggle.checked = policy.audio_flow_enabled !== false;
    const titlebarToggle = document.getElementById("toggle-audio-flow-titlebar");
    if (titlebarToggle) titlebarToggle.checked = policy.audio_flow_enabled !== false;
    updateAudioFlowStatusBadge(policy.audio_flow_enabled !== false);

    const speed = parseFloat(policy.audio_flow_speed);
    if (!isNaN(speed)) {
      syncAudioSpeedSelect(speed);
      // Legacy presentation (mid-restructure HTML may still ship pills).
      document.querySelectorAll(".speed-pill-btn").forEach(btn => {
        btn.classList.toggle("active", parseFloat(btn.dataset.speed) === speed);
      });
    }
    return { ok: true };
  } catch (err) {
    console.error("Error loading Audio Flow policy:", err);
    return { ok: false, error: (err && err.message) || "Could not load reading voice settings." };
  }
}

function updateAudioFlowStatusBadge(enabled) {
  const badge = document.getElementById("exec-audio-status-badge");
  if (!badge) return;
  // The redesigned header keeps this legacy badge hidden; never unhide it or
  // strip its inline style (that would resurrect a duplicate status chip).
  if (badge.hidden) return;
  badge.textContent = enabled ? "● Audio Flow Active" : "○ Audio Flow Off";
  badge.classList.toggle("off", !enabled);
  badge.removeAttribute("style");
}

async function updateExecAudioFlowPolicy(modelVal) {
  if (!modelVal) return { ok: false, error: "No voice selected." };
  try {
    const res = await fetch("/api/audio-policy/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelVal }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || (data && data.success === false)) {
      throw new Error((data && data.error) || "Could not save the reading voice.");
    }
    const result = await loadExecAudioFlowPolicy();
    if (result && result.ok === false) {
      // The write succeeded but the reload failed — still treat as saved.
      return { ok: true };
    }
    return { ok: true };
  } catch (err) {
    console.error("Error updating Audio Flow policy:", err);
    return { ok: false, error: (err && err.message) || "Could not save the reading voice." };
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
    featureStates.audio = !!checked;
    applyFeatureDisabledUI();
    // Keep the card toggle and the title-bar toggle in sync.
    const card = document.getElementById("toggle-audio-flow");
    const titlebar = document.getElementById("toggle-audio-flow-titlebar");
    if (card) card.checked = !!checked;
    if (titlebar) titlebar.checked = !!checked;
  } catch (err) {
    console.error("Error toggling Audio Flow:", err);
  }
}

async function toggleVoiceFlowFeature(checked) {
  try {
    await fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "voice_flow_enabled", value: !!checked }),
    });
    featureStates.voice = !!checked;
    applyFeatureDisabledUI();
    if (typeof vfToast === "function") vfToast(`Voice Flow dictation ${checked ? "enabled" : "disabled"}.`);
  } catch (err) {
    console.error("Error toggling Voice Flow:", err);
  }
}

// The model picker and the feature-state loader both read this setting. A
// revision prevents an older GET from painting over an in-flight user choice;
// writes are serialized so rapid On/Off taps reach storage in that order.
let polishingToggleRevision = 0;
let polishingWriteCount = 0;
let polishingWriteChain = Promise.resolve();
let polishingConfirmedState = null;

function applyPolishingToggleState(enabled, persistLocal = true) {
  const toggle = document.getElementById("toggle-polishing");
  if (toggle) toggle.checked = !!enabled;
  if (persistLocal) {
    try { localStorage.setItem("vf_polishing_enabled", enabled ? "true" : "false"); } catch (_) {}
  }
}

function canApplyLoadedPolishingState(loadRevision) {
  return loadRevision === polishingToggleRevision && polishingWriteCount === 0;
}

async function togglePolishingSetting(checked) {
  const desired = !!checked;
  const requestRevision = ++polishingToggleRevision;
  if (polishingConfirmedState === null) {
    // onchange has already changed the checkbox. Its previous saved value
    // comes from the cache, not from that optimistic DOM value.
    let cached = null;
    try { cached = localStorage.getItem("vf_polishing_enabled"); } catch (_) {}
    polishingConfirmedState = cached === null ? !desired : cached === "true";
  }
  applyPolishingToggleState(desired);
  polishingWriteCount += 1;

  const write = async () => {
    const response = await fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "polishing_enabled", value: desired }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Could not save AI Polishing setting.");
    }
    polishingConfirmedState = desired;
    if (requestRevision === polishingToggleRevision) applyPolishingToggleState(desired);
    if (requestRevision === polishingToggleRevision && typeof vfToast === "function") vfToast(`AI Polishing ${desired ? "enabled" : "disabled"}.`);
  };

  const pending = polishingWriteChain.catch(() => {}).then(write);
  polishingWriteChain = pending;
  try {
    await pending;
  } catch (err) {
    console.error("Error toggling AI Polishing:", err);
    // Only the newest failed intent may roll the control back; an older
    // failure must not erase a newer click that is still queued.
    if (requestRevision === polishingToggleRevision) {
      applyPolishingToggleState(!!polishingConfirmedState);
      if (typeof vfToast === "function") vfToast(err.message || "Could not save AI Polishing setting.", true);
    }
  } finally {
    polishingWriteCount -= 1;
    if (polishingWriteCount === 0 && requestRevision === polishingToggleRevision && typeof loadVoiceFlowPolishSettings === "function") {
      void loadVoiceFlowPolishSettings();
    }
  }
}

async function toggleClickToPasteSetting(checked) {
  try {
    await safeFetchJson("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "click_to_paste_enabled", value: !!checked }),
    });
    if (typeof vfToast === "function") {
      vfToast(checked ? "Deferred Click-to-Paste ON (Right-click to paste)" : "Direct Auto-Paste ON");
    }
  } catch (err) {
    console.error("Error toggling Click-to-Paste:", err);
  }
}

async function toggleVideoFlowFeature(checked) {
  try {
    await fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "video_flow_enabled", value: !!checked }),
    });
    featureStates.video = !!checked;
    const t1 = document.getElementById("toggle-video-flow-feature");
    const t2 = document.getElementById("toggle-video-flow");
    if (t1) t1.checked = !!checked;
    if (t2) t2.checked = !!checked;
    applyFeatureDisabledUI();
    if (typeof vfToast === "function") vfToast(`Video Flow ${checked ? "enabled" : "disabled"}.`);
  } catch (err) {
    console.error("Error toggling Video Flow:", err);
  }
}

// =========================================================
// Onboarding: welcome screen + pre-recorded explanatory tour
// =========================================================
const ONBOARDING_NARRATION = [
  "Welcome to AI Productivity Flow. Here is a clear introduction to your complete voice-driven productivity suite for Windows.",
  "Welcome to the Audio Flow feature, our first feature. Imagine scrolling through Twitter and coming across a lengthy article that you don't want to read. Simply select the text, and a small audio button will appear. Click it to select the summary option, converting the article into an audio summary.",
  "Next is Video Flow, our second feature. If you want to convert that article into a visual summary, Video Flow transforms your text into an animated visual explainer right on your screen.",
  "Now that you have all the context about the article, you can use the Voice Flow feature to post about the article by speaking, and it will write it down for you. Zoom in on your context and let your voice write down your thoughts.",
  "Here is an overview of all five features built into AI Productivity Flow: Audio Summaries, Visual Summaries, Voice Flow Dictation, Article Conversion, and Feedback Insights.",
  "We hope you enjoy using AI Productivity Flow! If you like the app, please visit our GitHub repository to check reports, provide feedback, and give us a star on GitHub. Your feedback is appreciated!",
];

// Dedicated pre-recorded narrator voice & explanatory pacing configuration
const ONBOARDING_NARRATOR_VOICE = "edge/en-US-AvaNeural";
const ONBOARDING_VOICE_SPEED = "-15%";

const ONBOARDING_PAGE_MAP = {
  0: "audioflow",
  1: "audioflow",
  2: "videoflow",
  3: "home",
  4: "insights",
  5: "home"
};

let onboardingSlide = 0;
let onboardingNarrationPaused = false;

function onboardingFlag(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function setOnboardingFlag(key, value) {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

async function maybeShowOnboarding() {
  const localFlag = onboardingFlag("hasViewedOnboarding") || onboardingFlag("vf_onboarding.done");
  if (localFlag === "true" || localFlag === "1") return;

  try {
    const res = await fetch("/api/settings/get?key=has_viewed_onboarding");
    const data = await res.json();
    if (data.success && data.value === true) {
      setOnboardingFlag("hasViewedOnboarding", "true");
      setOnboardingFlag("vf_onboarding.done", "1");
      return;
    }
  } catch (e) {}

  // First time launch: mark hasViewedOnboarding = true immediately so it never shows again on future launches
  setOnboardingFlag("hasViewedOnboarding", "true");
  setOnboardingFlag("vf_onboarding.done", "1");
  fetch("/api/settings/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: "has_viewed_onboarding", value: true }),
  }).catch(() => {});

  const overlay = document.getElementById("onboarding-overlay");
  if (!overlay) return;
  onboardingSlide = 0;
  renderOnboardingSlide();
  overlay.classList.remove("hidden");
  speakOnboardingNarration();
}

function renderOnboardingDots() {
  const dots = document.getElementById("onboarding-dots");
  if (!dots) return;
  dots.innerHTML = ONBOARDING_NARRATION.map((_, i) =>
    `<span class="${i === onboardingSlide ? "active" : ""}" onclick="gotoOnboardingSlide(${i})"></span>`
  ).join("");
}

function renderOnboardingSlide() {
  document.querySelectorAll(".onboarding-slide").forEach(s => {
    const slideIdx = Number(s.getAttribute("data-slide") || (s.dataset && s.dataset.slide) || 0);
    s.classList.toggle("active", slideIdx === onboardingSlide);
  });
  renderOnboardingDots();
  const player = document.getElementById("onboarding-player");
  if (player) player.style.display = onboardingSlide === 0 ? "none" : "flex";

  // Auto-navigate app background to match current tour topic
  const targetPage = ONBOARDING_PAGE_MAP[onboardingSlide];
  if (targetPage && typeof switchPage === "function") {
    switchPage(targetPage);
  }
}

// Embedded pre-recorded narration player (Deepgram Aura Zeus Professional Male)
let onboardingAudioPlayer = null;

function getOnboardingAudioPath(slideIdx) {
  return `/assets/onboarding/slide_${slideIdx}.mp3`;
}

function updateOnboardingNarrationUI(paused) {
  const btn = document.getElementById("onboarding-narration-toggle");
  const label = document.getElementById("onboarding-narration-label");
  if (btn) btn.textContent = paused ? "▶" : "⏸";
  if (label) label.textContent = paused ? "Paused" : "Narrating…";
}

function speakOnboardingNarration() {
  stopOnboardingNarration();
  onboardingNarrationPaused = false;
  updateOnboardingNarrationUI(false);

  const audioPath = getOnboardingAudioPath(onboardingSlide);
  onboardingAudioPlayer = new Audio(audioPath);
  
  onboardingAudioPlayer.addEventListener("ended", () => {
    updateOnboardingNarrationUI(true);
  });

  onboardingAudioPlayer.play().catch(err => {
    console.warn("Could not play embedded onboarding audio:", err);
  });
}

function stopOnboardingNarration() {
  if (onboardingAudioPlayer) {
    try {
      onboardingAudioPlayer.pause();
      onboardingAudioPlayer.currentTime = 0;
    } catch (e) {}
    onboardingAudioPlayer = null;
  }
}

function makeButton(label, onclick) {
  const btn = document.createElement("button");
  btn.className = "btn-secondary";
  btn.textContent = label;
  btn.onclick = onclick;
  return btn;
}

function editCorrection(row, item) {
  // Static helper for correction inline editing
}


function toggleOnboardingNarration() {
  if (!onboardingAudioPlayer) {
    speakOnboardingNarration();
    return;
  }
  if (onboardingAudioPlayer.paused) {
    onboardingAudioPlayer.play().then(() => {
      onboardingNarrationPaused = false;
      updateOnboardingNarrationUI(false);
    }).catch(() => {});
  } else {
    onboardingAudioPlayer.pause();
    onboardingNarrationPaused = true;
    updateOnboardingNarrationUI(true);
  }
}

function gotoOnboardingSlide(idx) {
  if (idx < 0 || idx >= ONBOARDING_NARRATION.length) return;
  onboardingSlide = idx;
  renderOnboardingSlide();
  stopOnboardingNarration();
  setTimeout(speakOnboardingNarration, 350);
}

function nextOnboardingSlide() {
  if (onboardingSlide >= ONBOARDING_NARRATION.length - 1) { finishOnboarding(); return; }
  gotoOnboardingSlide(onboardingSlide + 1);
}

function prevOnboardingSlide() {
  gotoOnboardingSlide(Math.max(1, onboardingSlide - 1));
}

function startOnboardingTour() {
  const source = document.getElementById("onboarding-source");
  if (source && source.value) setOnboardingFlag("vf_onboarding.source", source.value);
  gotoOnboardingSlide(1);
}

function finishOnboarding() {
  stopOnboardingNarration();
  const source = document.getElementById("onboarding-source");
  if (source && source.value) setOnboardingFlag("vf_onboarding.source", source.value);
  setOnboardingFlag("vf_onboarding.done", "1");
  const overlay = document.getElementById("onboarding-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function replayOnboarding() {
  setOnboardingFlag("vf_onboarding.done", "");
  if (typeof closeSettings === "function") closeSettings();
  onboardingSlide = 0;
  renderOnboardingSlide();
  const overlay = document.getElementById("onboarding-overlay");
  if (overlay) overlay.classList.remove("hidden");
  speakOnboardingNarration();
}

// One-time celebration the first time real dictation data appears.
async function maybeCelebrateFirstDictation(recordCount) {
  if (!recordCount) return;
  const localFlag = onboardingFlag("vf_onboarding.firstDictation");
  if (localFlag === "1" || localFlag === "true") return;

  try {
    const res = await fetch("/api/settings/get?key=has_celebrated_first_dictation");
    const data = await res.json();
    if (data.success && data.value === true) {
      setOnboardingFlag("vf_onboarding.firstDictation", "1");
      return;
    }
  } catch (e) {}

  // If user already has dictations from past sessions, mark as celebrated/done quietly
  if (recordCount > 1) {
    setOnboardingFlag("vf_onboarding.firstDictation", "1");
    fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "has_celebrated_first_dictation", value: true }),
    }).catch(() => {});
    return;
  }

  // Exactly 1 dictation recorded for the very first time!
  setOnboardingFlag("vf_onboarding.firstDictation", "1");
  fetch("/api/settings/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: "has_celebrated_first_dictation", value: true }),
  }).catch(() => {});

  if (typeof vfToast === "function") {
    vfToast("🎉 Your first dictation! It's saved in Home — Insights start counting from here.");
  }
}

// Centralized feature on/off state, mirrored into body classes + banners.
const featureStates = { voice: true, audio: true, video: true };

function applyFeatureDisabledUI() {
  if (document.body && document.body.classList) {
    document.body.classList.toggle("feature-voice-off", !featureStates.voice);
    document.body.classList.toggle("feature-audio-off", !featureStates.audio);
    document.body.classList.toggle("feature-video-off", !featureStates.video);
  }

  const banners = [
    { pageId: "page-audioflow", active: !featureStates.audio, label: "🔇 Audio Flow is disabled — flip the toggle on this page's title bar to re-enable it." },
    { pageId: "page-videoflow", active: !featureStates.video, label: "🎬 Video Flow is disabled — flip the toggle on this page's title bar to re-enable it." },
  ];
  for (const b of banners) {
    const page = document.getElementById(b.pageId);
    if (!page) continue;
    let banner = page.querySelector(".feature-disabled-banner");
    if (b.active && !banner) {
      banner = document.createElement("div");
      banner.className = "feature-disabled-banner";
      banner.textContent = b.label;
      page.insertBefore(banner, page.firstChild);
    } else if (!b.active && banner) {
      banner.remove();
    }
  }
}

async function loadFeatureToggleStates() {
  const polishLoadRevision = polishingWriteCount === 0 ? polishingToggleRevision : -1;
  try {
    const [voiceRes, videoRes, audioRes, polishRes] = await Promise.all([
      fetch("/api/settings/get?key=voice_flow_enabled"),
      fetch("/api/settings/get?key=video_flow_enabled"),
      fetch("/api/settings/get?key=audio_flow_enabled"),
      fetch("/api/settings/get?key=polishing_enabled"),
    ]);
    const voice = await voiceRes.json();
    const video = await videoRes.json();
    const audio = await audioRes.json();
    const polish = await polishRes.json();
    featureStates.voice = !(voice.success && voice.value === false);
    featureStates.video = !(video.success && video.value === false);
    featureStates.audio = !(audio.success && audio.value === false);
    const voiceToggle = document.getElementById("toggle-voice-flow-feature");
    if (voiceToggle) voiceToggle.checked = featureStates.voice;
    const videoToggle = document.getElementById("toggle-video-flow-feature");
    if (videoToggle) videoToggle.checked = featureStates.video;
    const videoToggleCard = document.getElementById("toggle-video-flow");
    if (videoToggleCard) videoToggleCard.checked = featureStates.video;
    const card = document.getElementById("toggle-audio-flow");
    const titlebar = document.getElementById("toggle-audio-flow-titlebar");
    if (card) card.checked = featureStates.audio;
    if (titlebar) titlebar.checked = featureStates.audio;
    const polishToggle = document.getElementById("toggle-polishing");
    if (polishToggle && canApplyLoadedPolishingState(polishLoadRevision)) {
      if (polish && polish.success && typeof polish.value === "boolean") {
        polishingConfirmedState = polish.value;
        applyPolishingToggleState(polish.value);
      } else {
        try {
          const localPolish = localStorage.getItem("vf_polishing_enabled");
          if (localPolish !== null) polishToggle.checked = (localPolish === "true");
        } catch (_) {}
      }
    }
    applyFeatureDisabledUI();
  } catch (err) {
    console.warn("Could not load feature toggle states:", err);
    try {
      const polishToggle = document.getElementById("toggle-polishing");
      const localPolish = localStorage.getItem("vf_polishing_enabled");
      if (polishToggle && localPolish !== null) polishToggle.checked = (localPolish === "true");
    } catch (_) {}
  }
}

// --- Reading speed (plan section 6) ----------------------------------------
// All currently supported values (same set the old speed pills offered). The
// engine's speed mapping is untouched: selections go to the same
// /api/audio-policy/speed endpoint with the exact numeric value.
const AUDIO_FLOW_SPEEDS = [0.75, 1, 1.2, 1.25, 1.5, 1.75, 2];

function audioSpeedNumberLabel(speed) {
  const trimmed = String(parseFloat(speed.toFixed(2)));
  return `${trimmed}×`;
}

function audioSpeedOptionLabel(speed) {
  // 1× is the default; say so instead of a bare number.
  if (Math.abs(speed - 1) < 0.0001) return "1× · Normal";
  return audioSpeedNumberLabel(speed);
}

// Reflect the saved speed in #audio-speed-select, preserving the exact numeric
// value even when it is not one of the standard options (unusual stored values
// get their own option rather than being rounded or reset).
function syncAudioSpeedSelect(speed) {
  const select = document.getElementById("audio-speed-select");
  if (!select) return;
  const exact = String(speed);
  let option = Array.from(select.options).find((opt) => Math.abs(parseFloat(opt.value) - speed) < 0.0001);
  if (!option) {
    option = new Option(audioSpeedOptionLabel(speed), exact);
    select.add(option);
  }
  option.textContent = audioSpeedOptionLabel(speed);
  select.value = option.value;
  const display = document.getElementById("audio-speed-display");
  if (display) display.textContent = audioSpeedOptionLabel(speed);
  renderAudioSpeedChoices();
}

// The saved select remains the source of truth; the visible choices are only
// a presentation of its options. Failed saves leave the previous speed selected.
function renderAudioSpeedChoices() {
  const select = document.getElementById("audio-speed-select");
  const group = document.getElementById("audio-speed-choices");
  if (!select || !group) return;
  for (const option of select.options) {
    let button = Array.from(group.children).find(el => el.dataset.speed === option.value);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "studio-speed-choice";
      button.dataset.speed = option.value;
      button.addEventListener("click", async () => {
        if (group.dataset.saving === "true") return;
        group.dataset.saving = "true";
        group.setAttribute("aria-busy", "true");
        Array.from(group.children).forEach(el => { el.disabled = true; });
        try { await setAudioFlowSpeed(button.dataset.speed); }
        finally {
          group.dataset.saving = "false";
          group.removeAttribute("aria-busy");
          renderAudioSpeedChoices();
        }
      });
      group.appendChild(button);
    }
    button.textContent = `${Number(option.value)}×`;
    button.setAttribute("aria-label", Number(option.value) === 1 ? "Normal reading speed, 1×" : `Reading speed ${Number(option.value)}×`);
    button.setAttribute("aria-pressed", String(option.value === select.value));
    button.disabled = select.disabled || option.disabled || group.dataset.saving === "true";
  }
  group.hidden = false;
  select.hidden = true;
  select.classList.add("studio-speed-source");
}

// Wire the compact speed select once per page load. Adds missing standard
// options without removing or reordering anything the HTML ships, and only
// attaches a change handler when one is not already wired inline.
function initAudioSpeedSelect() {
  const select = document.getElementById("audio-speed-select");
  if (!select) {
    fpWarnOnce("audio-speed-select", "#audio-speed-select not found in index.html yet; speed pills remain the fallback control.");
    return;
  }
  for (const speed of AUDIO_FLOW_SPEEDS) {
    const hasOption = Array.from(select.options).some((opt) => Math.abs(parseFloat(opt.value) - speed) < 0.0001);
    if (!hasOption) {
      select.add(new Option(audioSpeedOptionLabel(speed), String(speed)));
    }
  }
  const normalOption = Array.from(select.options).find((opt) => Math.abs(parseFloat(opt.value) - 1) < 0.0001);
  if (normalOption) normalOption.textContent = audioSpeedOptionLabel(1); // "1× · Normal"
  if (!select.getAttribute("aria-label")) {
    select.setAttribute("aria-label", "Reading speed");
  }
  if (!select.onchange && !select.hasAttribute("onchange")) {
    select.onchange = () => onAudioSpeedSelectChange(select.value);
  }
  renderAudioSpeedChoices();
}

async function onAudioSpeedSelectChange(value) {
  await setAudioFlowSpeed(value);
}

async function setAudioFlowSpeed(x) {
  const speed = parseFloat(x);
  if (isNaN(speed)) return;
  try {
    const res = await fetch("/api/audio-policy/speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || (data && data.success === false)) {
      throw new Error((data && data.error) || "Could not save the reading speed.");
    }
    // Keep the exact value everywhere — never snap to the nearest pill.
    syncAudioSpeedSelect(speed);
    document.querySelectorAll(".speed-pill-btn").forEach(btn => {
      btn.classList.toggle("active", parseFloat(btn.dataset.speed) === speed);
    });
  } catch (err) {
    console.error("Error setting Audio Flow speed:", err);
    if (typeof vfToast === "function") vfToast("Could not save the reading speed.", true);
  }
}

async function loadAudioProvidersOverview() {
  const container = document.getElementById("audio-providers-grid-container");
  const overview = document.getElementById("audio-providers-view-overview");
  const detail = document.getElementById("audio-providers-view-detail");
  if (!container) return;
  if (overview) overview.style.display = "block";
  if (detail) detail.style.display = "none";
  currentAudioProvider = null;

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

    const allProviders = [...freeProviders, ...data.filter(p => !String(p.id).startsWith("custom-"))];

    container.innerHTML = allProviders.map(p => {
      const cfg = AUDIO_PROVIDERS_CONFIG[p.id] || {};
      const isFree = !!cfg.free;
      const connText = p.is_connected
        ? `${p.connection_count || 1} Connected`
        : "Not connected";
      return `
        <div class="provider-card-item audio-provider-card" onclick="openAudioProviderDetail('${p.id}')">
          <div class="provider-card-left">
            <div class="provider-card-logo audio-card-logo provider-brand-logo">${vfBrandLogo(p.id, p.logo)}</div>
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
    loadAudioCustomProviders();
  } catch (err) {
    console.error("Error loading audio providers overview:", err);
    container.innerHTML = `<div class="audio-empty-state">Failed to load providers — is the Voice Flow backend running?</div>`;
  }
}

async function openAudioProviderDetail(providerId) {
  if (currentAudioProvider !== providerId) _vfAudioSelectedConnIds.clear();
  currentAudioProvider = providerId;
  const isCustom = String(providerId).startsWith("custom-");
  const customEntry = isCustom ? (vfAudioCustomProviders || []).find(p => p.id === providerId) : null;
  const cfg = AUDIO_PROVIDERS_CONFIG[providerId] || {
    name: customEntry?.name || providerId,
    logo: (customEntry?.name || "A")[0].toUpperCase(),
    keyLink: null,
  };

  document.getElementById("audio-providers-view-overview").style.display = "none";
  document.getElementById("audio-providers-view-detail").style.display = "block";

  document.getElementById("audio-detail-provider-name").textContent = cfg.name;
  document.getElementById("audio-detail-provider-logo").innerHTML = vfBrandLogo(providerId, cfg.logo);
  const keyLink = document.getElementById("audio-detail-get-key-link");
  if (keyLink) {
    keyLink.style.display = (cfg.keyLink && !isCustom) ? "inline-flex" : "none";
    if (cfg.keyLink) keyLink.href = cfg.keyLink;
  }
  const editBtn = document.getElementById("audio-detail-edit-custom-provider-btn");
  if (editBtn) {
    editBtn.style.display = isCustom ? "inline-flex" : "none";
  }
  const delBtn = document.getElementById("audio-detail-delete-custom-provider-btn");
  if (delBtn) {
    delBtn.style.display = isCustom ? "inline-flex" : "none";
  }

  loadAudioProviderDetails(providerId);
}

function closeAudioProviderDetail() {
  currentAudioProvider = null;
  const audioErrBanner = document.getElementById("audio-voices-test-error-banner");
  if (audioErrBanner) {
    audioErrBanner.textContent = "";
    audioErrBanner.style.display = "none";
  }
  loadAudioProvidersOverview();
}

async function loadAudioProviderDetails(providerId) {
  try {
    const res = await fetch(`/api/audio-providers/details?provider=${providerId}`);
    const data = await res.json();
    if (!data || data.error) return;

    const conns = (data.connections || []).sort((a, b) => (a.priority || 0) - (b.priority || 0));
    const connCountEl = document.getElementById("audio-detail-conn-count");
    if (connCountEl) {
      connCountEl.textContent = `${conns.length} connection${conns.length === 1 ? "" : "s"}`;
    }

    const rrToggle = document.getElementById("audio-provider-round-robin-toggle");
    if (rrToggle) {
      rrToggle.checked = (data.mode === "round-robin" || data.mode === "round_robin");
    }

    // Audio provider-scoped voice test error banner
    const audioErrBanner = document.getElementById("audio-voices-test-error-banner");
    if (audioErrBanner) {
      const activeErr = _vfAudioProviderModelErrors[providerId];
      if (activeErr && activeErr.error) {
        audioErrBanner.textContent = `✕ Voice Test Failed (${activeErr.modelId}): ${activeErr.error}`;
        audioErrBanner.style.display = "block";
      } else {
        audioErrBanner.textContent = "";
        audioErrBanner.style.display = "none";
      }
    }

    const connListEl = document.getElementById("audio-detail-connections-list");
    if (connListEl) {
      if (conns.length === 0) {
        connListEl.innerHTML = `
          <div class="conn-empty-9r">
            <div class="conn-empty-left-9r">
              <div class="conn-empty-icon-circle-9r">${vfUiIcon("key")}</div>
              <span class="conn-empty-text-9r">No connections yet</span>
            </div>
            <button class="btn-primary" style="padding: 7px 16px; font-size: 12px; display: inline-flex; align-items: center; gap: 6px;" onclick="openAddAudioConnectionModal()">+ Add</button>
          </div>`;
      } else {
        connListEl.innerHTML = conns.map((c, idx) => {
          const isFirst = idx === 0;
          const isLast = idx === conns.length - 1;
          const isSelected = _vfAudioSelectedConnIds.has(c.id);
          const isAct = c.is_active !== false && c.is_active !== 0;
          const keyRaw = c.api_key || "";
          const keyPreview = keyRaw.length > 10 ? `${keyRaw.substring(0, 6)}...${keyRaw.substring(keyRaw.length - 4)}` : "Key saved";
          const testedStatus = String(c.last_tested_status || c.status || "Not Tested");
          const statusOk = testedStatus.toLowerCase().startsWith("connected") || testedStatus.toLowerCase() === "active";
          const isUntested = !testedStatus || testedStatus.toLowerCase() === "not tested" || testedStatus.toLowerCase() === "untested";
          const statusDotClass = !isAct ? "disabled" : (statusOk ? "active" : (isUntested ? "disabled" : "error"));
          const statusDotLabel = !isAct ? "disabled" : (statusOk ? "verified" : (isUntested ? "untested" : "failed"));

          return `
            <div class="conn-row-9r ${!isAct ? 'inactive' : ''}" data-conn-id="${c.id}">
              <div class="conn-left-9r">
                <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectAudioConn('${c.id}', this.checked)">
                <div class="conn-arrows-col">
                  <button class="conn-arrow-btn" onclick="moveAudioConnPriority('${escapeJs(providerId)}', '${c.id}', -1)" ${isFirst ? 'disabled' : ''} title="Move up">▲</button>
                  <button class="conn-arrow-btn" onclick="moveAudioConnPriority('${escapeJs(providerId)}', '${c.id}', 1)" ${isLast ? 'disabled' : ''} title="Move down">▼</button>
                </div>
                <span class="conn-key-icon">🔑</span>
                <div class="conn-details-col">
                  <div class="conn-title-row">
                    <span class="conn-name-text">${escapeHtml(c.name || 'API Key')}</span>
                  </div>
                  <div class="conn-badges-row">
                    <span class="conn-dot-badge ${statusDotClass}">● ${statusDotLabel}</span>
                    <span class="conn-pill-badge">API Key</span>
                    <span class="conn-priority-pill">#${c.priority || (idx + 1)}</span>
                    <span style="font-size: 11px; color: var(--text-muted); margin-left: 4px;">Key: ${escapeHtml(keyPreview)}</span>
                    ${c.last_tested_status && c.last_tested_status !== "Not Tested" && !c.last_tested_status.includes("Connected") ? `<span style="font-size: 10px; color: #ef4444;">${escapeHtml(c.last_tested_status)}</span>` : ''}
                  </div>
                </div>
              </div>
              <div class="conn-actions-9r">
                <button class="conn-action-btn" onclick="testSingleAudioConn('${c.id}', null, currentAudioProvider, true)" title="Test Connection">
                  <span style="font-size: 14px;">🧪</span>
                  <span>Test</span>
                </button>
                <button class="conn-action-btn" onclick="openEditAudioConnectionModal('${c.id}')" title="Edit Connection">
                  <span style="font-size: 14px;">✏️</span>
                  <span>Edit</span>
                </button>
                <button class="conn-action-btn delete-btn" onclick="deleteAudioConn('${c.id}')" title="Delete Connection">
                  <span style="font-size: 14px;">🗑️</span>
                  <span>Delete</span>
                </button>
                <label class="toggle-switch" style="margin-left: 6px;">
                  <input type="checkbox" ${isAct ? 'checked' : ''} onchange="toggleAudioProviderConn('${c.id}', this.checked)">
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    // Show/hide Select All row and bottom + Add button based on connections count
    const selectAllRow = document.getElementById("audio-select-all-row");
    const addConnContainer = document.getElementById("audio-add-conn-container");
    if (selectAllRow) selectAllRow.style.display = conns.length > 0 ? "" : "none";
    if (addConnContainer) addConnContainer.style.display = conns.length > 0 ? "" : "none";

    // Available Voices rendering (9Router format)
    const allModels = data.models || [];
    const activeModels = allModels.filter(m => m.is_active !== false && m.is_active !== 0);
    const disabledModels = allModels.filter(m => m.is_active === false || m.is_active === 0);

    const modelsGridEl = document.getElementById("audio-detail-models-grid");
    if (modelsGridEl) {
      let cardsHtml = activeModels.map(m => {
        const isEdgeVoice = providerId === "edge";
        const fullId = `${providerId}/${m.model_id}`;
        const testRes = _vfAudioModelTestResults[m.model_id];
        const isTesting = _vfTestingAudioModelIds.has(m.model_id);
        const cardClass = isTesting ? 'testing' : (testRes ? (testRes.ok ? 'tested-ok' : 'tested-error') : '');
        // All providers now share one icon language: a real brand mark when we
        // have one, otherwise a state icon, and inline-SVG action buttons.
        const brandMark = vfBrandLogo(providerId);
        const stateIcon = isTesting
          ? vfUiIcon("spinner", "vf-ico-spin")
          : (testRes ? (testRes.ok ? vfUiIcon("check") : vfUiIcon("ban")) : vfUiIcon("mic"));
        const badgeHtml = brandMark || stateIcon;
        const edgeVoiceMeta = String(m.display_name || m.model_id)
          .replace(/^Edge\s+/i, "")
          .replace(/^(.+?)\s*\((.+)\)$/, "$1|$2");
        const [edgeVoiceName, edgeVoiceDescription] = edgeVoiceMeta.includes("|")
          ? edgeVoiceMeta.split("|", 2)
          : [edgeVoiceMeta, "Microsoft Edge Neural voice"];

        return `
          <div class="model-card-9r ${isEdgeVoice ? 'edge-voice-card' : ''} ${cardClass}" id="audio-model-card-${m.id}">
            <div class="model-card-left-9r">
              <span class="model-status-icon-9r ${isTesting ? 'testing' : ''}">${badgeHtml}</span>
              <div class="model-card-info-9r">
                ${isEdgeVoice ? `
                  <div class="edge-voice-title" title="${escapeHtml(m.display_name || m.model_id)}">${escapeHtml(edgeVoiceName)}</div>
                  <div class="edge-voice-description" title="${escapeHtml(edgeVoiceDescription)}">${escapeHtml(edgeVoiceDescription)}</div>
                  <code class="model-code-tag" title="${escapeHtml(fullId)}">${escapeHtml(fullId)}</code>
                ` : `
                  <div class="edge-voice-title" title="${escapeHtml(m.display_name || m.model_id)}">${escapeHtml(m.display_name || m.model_id)}</div>
                  <div class="model-card-meta-9r">
                    <code class="model-code-tag" title="${escapeHtml(fullId)}">${escapeHtml(fullId)}</code>
                    ${testRes && testRes.ok && testRes.latency_ms ? `<span class="model-latency-9r">${testRes.latency_ms}ms</span>` : ''}
                  </div>
                `}
                ${testRes && !testRes.ok && testRes.error ? `<div class="model-test-error-text" title="${escapeHtml(testRes.error)}" style="color:#ef4444;font-size:10.5px;font-weight:600;margin-top:4px;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${vfUiIcon("ban")} ${escapeHtml(testRes.error)}</div>` : ''}
              </div>
            </div>
            <div class="model-actions-9r">
              <button class="model-action-btn-9r" onclick="testSingleAudioModel('${escapeJs(m.model_id)}', this)" title="Test voice" aria-label="Test voice" ${isTesting ? 'disabled' : ''}>
                ${isTesting ? vfUiIcon("spinner", "vf-ico-spin") : vfUiIcon("test")}
              </button>
              <button class="model-action-btn-9r" onclick="copyAudioModelId('${escapeJs(fullId)}', this)" title="Copy Voice ID" aria-label="Copy voice ID">
                ${vfUiIcon("copy", "vf-ico-copy")}${vfUiIcon("check", "vf-ico-check")}
              </button>
              ${(m.custom || String(providerId).startsWith("custom-")) ? `
                <button class="model-action-btn-9r delete" onclick="deleteAudioCustomModel('${escapeJs(m.id || m.model_id)}', '${escapeJs(providerId)}')" title="Delete voice permanently" aria-label="Delete voice permanently">
                  ${vfUiIcon("trash")}
                </button>
              ` : ''}
              <button class="model-action-btn-9r delete" onclick="disableAudioVoice('${m.id}')" title="Disable this voice" aria-label="Disable this voice">
                ${vfUiIcon("ban")}
              </button>
            </div>
          </div>
        `;
      }).join("");

      cardsHtml += `
        <div class="add-model-dashed-btn" onclick="openAddAudioModelModal()">
          <span>+</span> Add Voice
        </div>
      `;

      modelsGridEl.innerHTML = cardsHtml;
    }

    // Disabled voices chips section
    const disabledBox = document.getElementById("audio-disabled-voices-box");
    const disabledCountEl = document.getElementById("audio-disabled-count");
    const disabledListEl = document.getElementById("audio-disabled-voices-list");
    if (disabledBox && disabledListEl) {
      if (disabledModels.length > 0) {
        disabledBox.style.display = "block";
        if (disabledCountEl) disabledCountEl.textContent = String(disabledModels.length);
        disabledListEl.innerHTML = disabledModels.map(m => `
          <button class="disabled-model-chip" onclick="enableAudioVoice('${m.id}')" title="Click to restore voice">
            <span>+</span> ${escapeHtml(m.model_id)}
          </button>
        `).join("");
      } else {
        disabledBox.style.display = "none";
      }
    }

  } catch (err) {
    console.error("Error loading audio provider details:", err);
  }
}

async function moveAudioConnPriority(providerId, connId, direction) {
  try {
    const res = await fetch(`/api/audio-providers/details?provider=${providerId}`);
    const data = await res.json();
    const conns = (data.connections || []).sort((a, b) => (a.priority || 0) - (b.priority || 0));
    const idx = conns.findIndex(c => String(c.id) === String(connId));
    if (idx < 0) return;
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= conns.length) return;

    const temp = conns[idx];
    conns[idx] = conns[targetIdx];
    conns[targetIdx] = temp;

    const ids = conns.map(c => c.id);
    await fetch("/api/audio-providers/connections/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerId, connection_ids: ids }),
    });
    loadAudioProviderDetails(providerId);
  } catch (err) {
    console.error("Error reordering audio connections:", err);
  }
}

function openAddAudioConnectionModal() {
  const modal = document.getElementById("modal-add-audio-connection");
  if (!modal) return;

  document.getElementById("audio-conn-edit-id").value = "";
  const nameInput = document.getElementById("audio-conn-input-name");
  const keyInput = document.getElementById("audio-conn-input-key");
  const priorityInput = document.getElementById("audio-conn-input-priority");
  const badge = document.getElementById("audio-conn-check-badge");
  if (nameInput) nameInput.value = "";
  if (keyInput) {
    keyInput.value = "";
    keyInput.placeholder = "Paste key...";
  }
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

async function openEditAudioConnectionModal(cid) {
  try {
    const res = await fetch(`/api/audio-providers/details?provider=${currentAudioProvider}`);
    const data = await res.json();
    const conn = (data.connections || []).find(c => String(c.id) === String(cid));
    if (!conn) return;

    const modal = document.getElementById("modal-add-audio-connection");
    if (!modal) return;

    document.getElementById("audio-conn-edit-id").value = String(cid);
    document.getElementById("audio-conn-input-name").value = conn.name || "";
    const keyInput = document.getElementById("audio-conn-input-key");
    keyInput.value = "";
    keyInput.placeholder = "Leave blank to keep saved key";
    document.getElementById("audio-conn-input-priority").value = conn.priority || 1;
    document.getElementById("audio-conn-check-badge").innerHTML = "";

    const title = document.getElementById("modal-audio-conn-title");
    if (title) title.textContent = "Edit API Key";

    modal.classList.remove("hidden");
  } catch (err) {
    console.error("Error opening edit audio modal:", err);
  }
}

async function saveAudioConnectionModal() {
  const editId = document.getElementById("audio-conn-edit-id").value;
  const name = document.getElementById("audio-conn-input-name").value.trim();
  const key = document.getElementById("audio-conn-input-key").value.trim();
  const priority = parseInt(document.getElementById("audio-conn-input-priority").value, 10) || 1;

  if (!editId && !key) {
    alert("Please paste an API key first.");
    return;
  }

  try {
    if (editId) {
      const res = await fetch("/api/audio-providers/connections/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: editId, name, key, priority, provider: currentAudioProvider }),
      });
      const data = await res.json();
      if (data && data.success === false) {
        alert(data.error || "Could not update the connection.");
        return;
      }
      closeSubModal("modal-add-audio-connection");
      if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
      loadExecAudioFlowPolicy();
      loadAudioProvidersOverview();
    } else {
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
      if (!res.ok || !data || data.success !== true) {
        alert((data && data.error) || "Could not add the connection.");
        return;
      }
      closeSubModal("modal-add-audio-connection");
      if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
      loadExecAudioFlowPolicy();
      loadAudioProvidersOverview();
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function toggleAudioProviderRoundRobin(checked) {
  if (!currentAudioProvider) return;
  const mode = checked ? "round-robin" : "priority";
  try {
    await fetch("/api/audio-providers/mode/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentAudioProvider, mode }),
    });
  } catch (err) {
    console.error("Error saving audio round robin mode:", err);
  }
}

function toggleSelectAllAudioConns(checked) {
  fetch(`/api/audio-providers/details?provider=${currentAudioProvider}`)
    .then(r => r.json())
    .then(data => {
      if (checked) {
        (data.connections || []).forEach(c => _vfAudioSelectedConnIds.add(c.id));
      } else {
        _vfAudioSelectedConnIds.clear();
      }
      loadAudioProviderDetails(currentAudioProvider);
    });
}

function toggleSelectAudioConn(cid, checked) {
  if (checked) {
    _vfAudioSelectedConnIds.add(cid);
  } else {
    _vfAudioSelectedConnIds.delete(cid);
  }
}

async function testAudioProviderConnectionsOneByOne() {
  if (_vfAudioOneByOneRunning || !currentAudioProvider) return;
  _vfAudioOneByOneRunning = true;

  const btn = document.getElementById("btn-audio-test-conn-one-by-one");
  const spinner = document.getElementById("audio-test-conn-spinner");
  const label = document.getElementById("audio-test-conn-btn-label");

  if (spinner) spinner.style.display = "inline-block";
  if (label) label.textContent = "Testing...";
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/audio-providers/details?provider=${currentAudioProvider}`);
    const det = await res.json();
    const allConns = det.connections || [];
    const selected = allConns.filter(c => _vfAudioSelectedConnIds.has(c.id));
    const conns = selected.length ? selected : allConns.filter(c => c.is_active !== false && c.is_active !== 0);
    for (let i = 0; i < conns.length; i++) {
      const c = conns[i];
      if (label) label.textContent = `Testing (${i + 1}/${conns.length})...`;
      await testSingleAudioConn(c.id, undefined, currentAudioProvider);
    }
  } catch (err) {
    console.error("Error testing audio connections one by one:", err);
  } finally {
    _vfAudioOneByOneRunning = false;
    if (spinner) spinner.style.display = "none";
    if (label) label.textContent = "Test Connection One-by-One";
    if (btn) btn.disabled = false;
    loadAudioProviderDetails(currentAudioProvider);
  }
}

async function testSingleAudioModel(modelId, btnEl) {
  const targetProvider = currentAudioProvider;
  if (!targetProvider) return;

  _vfTestingAudioModelIds.add(modelId);
  loadAudioProviderDetails(targetProvider);

  try {
    const fullId = `${targetProvider}/${modelId}`;
    const res = await fetch("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, model_ref: fullId, provider: targetProvider, kind: "tts" }),
    });
    const data = await res.json();
    const isOk = Boolean(data.success && data.ok !== false);
    _vfAudioModelTestResults[modelId] = {
      ok: isOk,
      latency_ms: data.latency_ms || null,
      error: data.error || null,
    };

    if (isOk) {
      delete _vfAudioProviderModelErrors[targetProvider];
    } else {
      _vfAudioProviderModelErrors[targetProvider] = {
        modelId: modelId,
        error: data.error || "Voice test failed",
      };
    }

    if (currentAudioProvider === targetProvider) {
      const errBanner = document.getElementById("audio-voices-test-error-banner");
      if (errBanner) {
        if (!isOk && data.error) {
          errBanner.textContent = `✕ Voice Test Failed (${modelId}): ${data.error}`;
          errBanner.style.display = "block";
        } else if (isOk) {
          errBanner.textContent = "";
          errBanner.style.display = "none";
        }
      }
    }
  } catch (err) {
    _vfAudioModelTestResults[modelId] = { ok: false, latency_ms: null, error: err.message };
    _vfAudioProviderModelErrors[targetProvider] = {
      modelId: modelId,
      error: err.message,
    };
    if (currentAudioProvider === targetProvider) {
      const errBanner = document.getElementById("audio-voices-test-error-banner");
      if (errBanner) {
        errBanner.textContent = `✕ Voice Test Failed (${modelId}): ${err.message}`;
        errBanner.style.display = "block";
      }
    }
  } finally {
    _vfTestingAudioModelIds.delete(modelId);
    if (currentAudioProvider === targetProvider) {
      loadAudioProviderDetails(targetProvider);
    }
  }
}

function copyAudioModelId(fullId, btnEl) {
  navigator.clipboard.writeText(fullId).then(() => {
    if (btnEl) {
      // Keep the button's size stable: swap the glyph + add a state class
      // instead of writing a wide "✓ Copied!" label into an icon button.
      // SVG icon buttons must NOT use textContent — that would delete the
      // inline SVG child nodes permanently. They toggle a class instead,
      // and CSS swaps the copy glyph for a check.
      if (btnEl.querySelector("svg")) {
        btnEl.classList.add("copied");
        setTimeout(() => { btnEl.classList.remove("copied"); }, 1500);
      } else {
        const orig = btnEl.textContent;
        btnEl.textContent = "✓";
        btnEl.classList.add("copied");
        setTimeout(() => { btnEl.textContent = orig; btnEl.classList.remove("copied"); }, 1500);
      }
    }
  }).catch(() => {
    alert("Copied: " + fullId);
  });
}

async function disableAudioVoice(mid) {
  try {
    await fetch("/api/audio-providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, provider: currentAudioProvider, is_active: false }),
    });
    loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error disabling voice:", err);
  }
}

async function enableAudioVoice(mid) {
  try {
    await fetch("/api/audio-providers/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mid, provider: currentAudioProvider, is_active: true }),
    });
    loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error enabling voice:", err);
  }
}

async function enableAllAudioVoices() {
  if (!currentAudioProvider) return;
  try {
    await fetch("/api/audio-providers/models/enable-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentAudioProvider }),
    });
    loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error enabling all voices:", err);
  }
}

async function disableAllAudioVoices() {
  if (!currentAudioProvider) return;
  try {
    await fetch("/api/audio-providers/models/disable-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: currentAudioProvider }),
    });
    loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error disabling all voices:", err);
  }
}

async function toggleAudioProviderConn(cid, isActive) {
  try {
    await fetch("/api/audio-providers/connections/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: currentAudioProvider, is_active: isActive }),
    });
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
  } catch (err) {
    console.error("Error toggling audio connection:", err);
  }
}

async function deleteAudioConn(cid) {
  if (!await vfConfirm("Delete this API key connection?")) return;
  try {
    await fetch("/api/audio-providers/connections/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cid, provider: currentAudioProvider }),
    });
    if (currentAudioProvider) loadAudioProviderDetails(currentAudioProvider);
    loadExecAudioFlowPolicy();
  } catch (err) {
    console.error("Error deleting audio connection:", err);
  }
}

async function toggleProviderMaster(providerId, isActive) {
  try {
    await fetch("/api/providers/master/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId, is_active: isActive }),
    });
    if (typeof loadProvidersOverview === "function") loadProvidersOverview();
  } catch (err) {
    console.error("Error toggling provider master:", err);
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
        await testSingleAudioConn(c.id, undefined, p.id);
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
    await testSingleAudioConn(c.id, undefined, currentAudioProvider);
  }
}

async function testSingleAudioConn(cid, key, provider, showAlert = false) {
  const prov = provider || currentAudioProvider || "";
  try {
    const res = await fetch("/api/audio-providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Never send the key back: list endpoints return masked values, and
      // the server resolves the real key from the connection id.
      body: JSON.stringify({ id: cid, provider: prov }),
    });
    const data = await res.json();
    if (showAlert) {
      alert(data.valid || data.success ? "✓ Connection test successful! Status: 200 OK" : "✕ Test failed: " + (data.status || data.error || "Failed"));
    }
    if (prov === currentAudioProvider) loadAudioProviderDetails(prov);
    return data;
  } catch (err) {
    console.error("Error testing audio connection:", err);
    if (showAlert) alert("Error: " + err.message);
    return { valid: false, status: err.message };
  }
}

async function testNewConnectionKey() {
  const key = document.getElementById("conn-input-key").value.trim();
  const editId = document.getElementById("conn-edit-id")?.value || "";
  const badge = document.getElementById("conn-check-badge");
  if (!badge) return;
  if (!key && !editId) {
    badge.innerHTML = `<span class="status-badge status-error">✕ Key is empty</span>`;
    return;
  }
  badge.innerHTML = `<span class="status-badge" style="background:#f3f4f6; color:#4b5563;">Testing...</span>`;
  try {
    const res = await fetch("/api/providers/connections/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: editId || null, provider: currentSelectedProvider || "", key }),
    });
    const data = await res.json();
    if (data.success) {
      badge.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
    } else {
      badge.innerHTML = `<span class="status-badge status-error" title="${escapeHtml(data.error || "")}">✕ ${escapeHtml(data.error || "Invalid key")}</span>`;
    }
  } catch (err) {
    badge.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message)}</span>`;
  }
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
    if (data.valid === true || data.success === true) {
      badge.innerHTML = `<span class="status-badge status-connected">✓ Connected</span>`;
    } else {
      badge.innerHTML = `<span class="status-badge status-error" title="${escapeHtml(data.status || "")}">✕ ${escapeHtml(data.status || "Invalid key")}</span>`;
    }
  } catch (err) {
    badge.innerHTML = `<span class="status-badge status-error">✕ ${escapeHtml(err.message)}</span>`;
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
  ctx.fillText("🎙️ AI Productivity Flow Productivity Card", 30, 48);

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
  ctx.fillText("⚡ Verified by AI Productivity Flow Speech Telemetry • #AIProductivityFlow", 30, 215);

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

// ===== Voice Flow AI Polish model (catalog = Video Flow LLM providers; independent) =====
let voiceFlowPolishModelSet = null;
let voiceFlowPolishModelRef = "local/deterministic";
let voiceFlowPolishModels = [];

async function loadVoiceFlowPolishSettings() {
  const polishLoadRevision = polishingWriteCount === 0 ? polishingToggleRevision : -1;
  try {
    const res = await fetch("/api/voice-flow-polish/get");
    const data = await res.json();
    voiceFlowPolishModelRef = data.active_model || "local/deterministic";
    const models = Array.isArray(data.models) ? data.models : [];
    // The shared picker renders display_name/provider_name, whereas this API
    // returns the policy-facing label/provider shape. Normalize policy-only
    // records so connected custom models are visible even when they are not
    // present in the Video Flow catalogue.
    voiceFlowPolishModels = models.map(m => {
      const fullId = String(m.full_id || "").trim();
      const provider = String(m.provider || fullId.split("/", 1)[0] || "local").trim();
      return {
        ...m,
        full_id: fullId,
        display_name: m.display_name || m.label || fullId,
        provider,
        provider_name: m.provider_name || VOICEFLOW_POLICY_PROVIDER_NAMES[provider] || provider,
        capabilities: Array.isArray(m.capabilities) ? m.capabilities : [],
        polish_supported: m.polish_supported !== false,
        polish_unavailable_reason: m.polish_unavailable_reason || "",
      };
    }).filter(m => m.full_id);
    voiceFlowPolishModelSet = new Set(voiceFlowPolishModels.map(m => m.full_id));
    const labelEl = document.getElementById("vf-polish-model-label");
    const detailEl = document.getElementById("vf-polish-model-detail");
    const match = models.find(m => m.full_id === voiceFlowPolishModelRef);
    // Real display labels, never a bare raw id (plan section 8).
    const displayName = match
      ? (match.display_name || match.label || match.full_id)
      : (voiceFlowPolishModelRef === "local/deterministic" ? "Local Deterministic Cleanup" : fpPrettifyRef(voiceFlowPolishModelRef));
    if (labelEl) labelEl.textContent = displayName;
    if (detailEl) {
      // The polishing switch is independent: when it is Off, the saved model
      // is kept and shown as remembered.
      const polishingOn = canApplyLoadedPolishingState(polishLoadRevision) && typeof data.polishing_enabled === "boolean"
        ? data.polishing_enabled
        : (() => { try { return localStorage.getItem("vf_polishing_enabled") !== "false"; } catch (_) { return true; } })();
      detailEl.classList.remove("flow-status", "flow-status--off");
      if (!polishingOn) {
        detailEl.textContent = "Off — your saved choice is kept";
        detailEl.classList.add("flow-status", "flow-status--off");
      } else if (voiceFlowPolishModelRef === "local/deterministic") {
        detailEl.textContent = "Built-in · runs on this PC";
      } else if (match && match.provider_name) {
        const caps = Array.isArray(match.capabilities) ? match.capabilities.map(c => String(c).toLowerCase()) : [];
        detailEl.textContent = [match.provider_name, caps.includes("offline") ? "Offline" : ""].filter(Boolean).join(" · ") || "Saved choice";
      } else {
        detailEl.textContent = voiceFlowPolishModelRef === "local/deterministic" ? "Built-in · no account needed" : "Saved choice";
      }
    }
    // "More options" disclosure node: keep the legacy fallback-engine line
    // truthful instead of static text.
    const polishEngineEl = document.getElementById("vf-polish-active-engine");
    if (polishEngineEl) {
      polishEngineEl.textContent = voiceFlowPolishModelRef === "local/deterministic"
        ? "Local Deterministic Cleanup"
        : (match && (match.provider_name || match.provider)) || fpPrettifyRef(voiceFlowPolishModelRef);
    }
    // Sync AI Polishing toggle switch
    const polishToggle = document.getElementById("toggle-polishing");
    if (polishToggle && canApplyLoadedPolishingState(polishLoadRevision)) {
      if (typeof data.polishing_enabled === "boolean") {
        polishingConfirmedState = data.polishing_enabled;
        applyPolishingToggleState(data.polishing_enabled);
      } else {
        try {
          const localPolish = localStorage.getItem("vf_polishing_enabled");
          if (localPolish !== null) polishToggle.checked = (localPolish === "true");
        } catch (_) {}
      }
    }
    return { ok: true };
  } catch (err) {
    console.error("Error loading AI Polish model settings:", err);
    return { ok: false, error: (err && err.message) || "Could not load text cleanup settings." };
  }
}

async function openVoiceFlowPolishModelPicker() {
  // AI Polish has an independent catalogue and persistence endpoint. Load it
  // before opening so it cannot inherit a stale shared Video Flow catalogue.
  await loadVoiceFlowPolishSettings();
  openVideoModelPicker("voice_flow_polish");
}

async function saveVoiceFlowPolishModel(modelRef) {
  if (!modelRef) return { ok: false, error: "No model selected." };
  try {
    const response = await fetch("/api/voice-flow-polish/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_ref: modelRef, model_id: modelRef, model: modelRef }),
    });
    if (!response.ok) throw new Error("Could not save the AI Polish model.");
    const data = await response.json();
    if (!data || !data.success) throw new Error((data && data.error) || "Could not save the AI Polish model.");
    voiceFlowPolishModelRef = data.active_model || modelRef;
    if (typeof vfToast === "function") vfToast("AI Polish model selected.");
    await loadVoiceFlowPolishSettings();
    return { ok: true };
  } catch (error) {
    if (typeof vfToast === "function") vfToast(error.message, true);
    await loadVoiceFlowPolishSettings();
    return { ok: false, error: (error && error.message) || "Could not save the AI Polish model." };
  }
}

// =========================================================================
// DOWNLOADABLE MODELS MANAGEMENT — VOICE FLOW
// =========================================================================

let vfDownloadableModels = [];
let vfDownloadPollingTimer = null;
let dmTargetModelId = null;
let dmDeleteTargetModelId = null;

async function loadVoiceDownloadableModels() {
  const grid = document.getElementById("voice-downloadable-models-grid");
  if (!grid) return;
  try {
    const res = await fetch("/api/downloadable-models?all=true");
    const data = await res.json();
    if (data && data.success && Array.isArray(data.models)) {
      vfDownloadableModels = data.models;
    } else {
      vfDownloadableModels = [];
    }
  } catch (err) {
    console.error("Error loading downloadable models:", err);
    vfDownloadableModels = [];
  }
  renderVoiceDownloadableModels();
  checkDownloadPolling();
}

let vfDownloadableModelsFilter = "all";

function setDownloadableModelsFilter(filter) {
  vfDownloadableModelsFilter = filter || "all";
  ["all", "stt", "voice_polishing"].forEach(f => {
    const btn = document.getElementById(`dm-tab-${f}`);
    if (btn) {
      if (f === vfDownloadableModelsFilter) {
        btn.classList.add("active");
        btn.style.background = "var(--primary-orange, #f97316)";
        btn.style.color = "#000000";
        btn.style.borderColor = "var(--primary-orange, #f97316)";
      } else {
        btn.classList.remove("active");
        btn.style.background = "var(--bg-card, rgba(255,255,255,0.05))";
        btn.style.color = "var(--text-muted, #9ca3af)";
        btn.style.borderColor = "var(--border-color, rgba(255,255,255,0.1))";
      }
    }
  });
  renderVoiceDownloadableModels();
}

function checkDownloadPolling() {
  const isDownloading = vfDownloadableModels.some(m => m.status === "downloading");
  if (isDownloading) {
    if (!vfDownloadPollingTimer) {
      vfDownloadPollingTimer = setInterval(async () => {
        try {
          const res = await fetch("/api/downloadable-models?all=true");
          const data = await res.json();
          if (data && data.success && Array.isArray(data.models)) {
            const prevDownloading = new Set(vfDownloadableModels.filter(m => m.status === "downloading").map(m => m.id));
            const prevDownloaded = new Set(vfDownloadableModels.filter(m => m.status === "downloaded").map(m => m.id));
            vfDownloadableModels = data.models;
            renderVoiceDownloadableModels();
            data.models.forEach(m => {
              if (m.status === "downloaded" && !prevDownloaded.has(m.id)) {
                const isPolish = m.category === "voice_polishing" || String(m.tag || "").toLowerCase().includes("polish");
                if (isPolish) {
                  if (typeof vfToast === "function") {
                    vfToast(`✓ ${m.name} is downloaded and activated as active Polish model!`);
                  }
                  selectDownloadableModelAsPolish(m.id);
                  loadVoiceFlowPolishSettings();
                } else {
                  if (typeof vfToast === "function") {
                    vfToast(`✓ ${m.name} is downloaded and activated as active STT model!`);
                  }
                  selectDownloadableModelAsSTT(m.id);
                  loadExecVoiceFlowPolicy();
                }
              } else if (m.status === "failed" && prevDownloading.has(m.id)) {
                if (typeof vfToast === "function") {
                  vfToast(`Download failed for ${m.name}: ${m.error || "Network error"}`, true);
                }
              }
            });
            if (!data.models.some(m => m.status === "downloading")) {
              clearInterval(vfDownloadPollingTimer);
              vfDownloadPollingTimer = null;
            }
          }
        } catch (e) {
          console.error("Download polling error:", e);
        }
      }, 1500);
    }
  } else if (vfDownloadPollingTimer) {
    clearInterval(vfDownloadPollingTimer);
    vfDownloadPollingTimer = null;
  }
}

function renderVoiceDownloadableModels() {
  const grid = document.getElementById("voice-downloadable-models-grid");
  if (!grid) return;

  const activeSTT = voiceFlowPolicyModelRef || "";
  const activePolish = typeof voiceFlowPolishModelRef === "string" ? voiceFlowPolishModelRef : "";

  // Update tab counts
  const allCount = (vfDownloadableModels || []).length;
  const sttCount = (vfDownloadableModels || []).filter(m => m.category === "stt" || String(m.tag || "").includes("STT")).length;
  const polishCount = (vfDownloadableModels || []).filter(m => m.category === "voice_polishing" || String(m.tag || "").toLowerCase().includes("polish")).length;
  const elAll = document.getElementById("dm-count-all");
  if (elAll) elAll.textContent = `(${allCount})`;
  const elStt = document.getElementById("dm-count-stt");
  if (elStt) elStt.textContent = `(${sttCount})`;
  const elPolish = document.getElementById("dm-count-polish");
  if (elPolish) elPolish.textContent = `(${polishCount})`;

  const filteredModels = (vfDownloadableModels || []).filter(m => {
    if (vfDownloadableModelsFilter === "stt") {
      return m.category === "stt" || String(m.tag || "").includes("STT");
    }
    if (vfDownloadableModelsFilter === "voice_polishing") {
      return m.category === "voice_polishing" || String(m.tag || "").toLowerCase().includes("polish");
    }
    return true;
  });

  grid.innerHTML = filteredModels.map(m => {
    const isDownloaded = m.status === "downloaded" && m.file_exists;
    const isDownloading = m.status === "downloading";
    const isPolish = m.category === "voice_polishing" || String(m.tag || "").toLowerCase().includes("polish");

    const isActiveSTT = !isPolish && isDownloaded && (
      activeSTT === m.full_id ||
      activeSTT === `local/${m.id}` ||
      activeSTT === m.id ||
      activeSTT.endsWith(m.filename)
    );
    const isActivePolish = isPolish && isDownloaded && (
      activePolish === m.full_id ||
      activePolish === `local/${m.id}` ||
      activePolish === m.id ||
      activePolish.endsWith(m.filename)
    );

    const cleanId = String(m.id).replace(/[^a-zA-Z0-9_-]/g, "_");
    const pct = Number(m.progress || 0).toFixed(1);
    const downloadedMb = Number(m.downloaded_mb != null ? m.downloaded_mb : ((m.downloaded_bytes || 0) / (1024 * 1024))).toFixed(1);
    const totalMb = Number(m.total_mb != null ? m.total_mb : m.size_mb).toFixed(1);
    const remainingMb = Number(m.remaining_mb != null ? m.remaining_mb : Math.max(0, totalMb - downloadedMb)).toFixed(1);
    const speed = m.speed_display || "";
    const eta = m.eta_display || "";

    const statusText = isDownloading
      ? `Downloading ${pct}%`
      : isDownloaded
        ? "Downloaded"
        : (m.status === "failed" ? (m.error ? `Failed: ${m.error}` : "Download failed") : `${m.size_display} · Not downloaded`);

    const tagBadge = isPolish
      ? `<span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 6px; background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); margin-left: 6px;">Voice Polishing</span>`
      : `<span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 6px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); margin-left: 6px;">Speech-to-Text (STT)</span>`;

    return `
      <div class="provider-card-item downloadable-model-card" id="dm-card-${cleanId}" onclick="openDownloadableModelDetail('${escapeJs(m.id)}')" style="cursor: pointer; flex-direction: column; align-items: stretch;">
        <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
          <div class="provider-card-left" style="flex: 1; min-width: 0;">
            <div class="provider-card-logo dm-compact-logo" style="flex-shrink: 0;">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14.93V17a1 1 0 0 1-2 0v-.07A7.003 7.003 0 0 1 5.07 11H5a1 1 0 0 1 0-2h.07A7.003 7.003 0 0 1 11 5.07V5a1 1 0 0 1 2 0v.07A7.003 7.003 0 0 1 18.93 11H19a1 1 0 0 1 0 2h-.07A7.003 7.003 0 0 1 13 16.93z"/>
              </svg>
            </div>
            <div class="provider-card-info" style="min-width: 0; flex: 1;">
              <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px;">
                <span class="provider-card-name dm-title" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(m.name)}</span>
                ${tagBadge}
              </div>
              <span class="provider-card-status">
                <span class="status-dot-indicator ${isDownloaded ? 'connected' : (isDownloading ? 'downloading' : '')}"></span>
                ${escapeHtml(statusText)}
              </span>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;" onclick="event.stopPropagation()">
            ${isDownloading
              ? `<button type="button" class="dm-card-cancel-btn" onclick="cancelDownloadModel('${escapeJs(m.id)}')">✕ Cancel</button>`
              : isDownloaded
                ? `
                    ${isPolish
                      ? (isActivePolish
                          ? `<span class="dm-active-stt-pill" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border-color: rgba(168, 85, 247, 0.4);">★ Active Polish</span>`
                          : `<button type="button" class="btn-secondary dm-card-action-btn" onclick="selectDownloadableModelAsPolish('${escapeJs(m.id)}')">Set as Polish</button>`
                        )
                      : (isActiveSTT
                          ? `<span class="dm-active-stt-pill">★ Active STT</span>`
                          : `<button type="button" class="btn-secondary dm-card-action-btn" onclick="selectDownloadableModelAsSTT('${escapeJs(m.id)}')">Set as STT</button>`
                        )
                    }
                    <button type="button" class="dm-delete-btn dm-card-action-btn" onclick="openDeleteConfirmModal('${escapeJs(m.id)}')">🗑️ Delete</button>
                  `
                : `<button type="button" class="btn-primary dm-card-action-btn" style="background: #76b900; border-color: #76b900; color: #000; font-weight: 700;" onclick="startDownloadModel('${escapeJs(m.id)}')"><span>↓</span> Download</button>`
            }
            <span class="dm-compact-chevron" style="cursor: pointer;" onclick="openDownloadableModelDetail('${escapeJs(m.id)}')">›</span>
          </div>
        </div>
        ${isDownloading ? `
          <div class="dm-card-progress-box">
            <div class="dm-progress-track" style="margin-bottom: 4px;">
              <div class="dm-progress-bar" style="width: ${Math.min(100, Math.max(0, pct))}%;"></div>
            </div>
            <div class="dm-card-stats">
              <span><strong>${downloadedMb} / ${totalMb} MB</strong></span>
              <span><strong style="color: #60a5fa;">${speed || 'Starting...'}</strong>${eta ? ' · ' + eta : ''}</span>
            </div>
          </div>
        ` : ''}
        ${!isDownloading && !isDownloaded && m.status === "failed" && m.error ? `
          <div class="dm-card-progress-box">
            <div style="font-size: 11px; color: #ef4444; margin-bottom: 4px;">⚠️ ${escapeHtml(m.error)}</div>
            <button type="button" class="btn-secondary dm-card-action-btn" style="padding: 3px 8px !important; font-size: 11px !important;" onclick="event.stopPropagation(); startDownloadModel('${escapeJs(m.id)}')">↻ Retry Download</button>
          </div>
        ` : ''}
      </div>
    `;
  }).join("");

  if (typeof currentDmDetailModelId === "string" && currentDmDetailModelId) {
    renderDownloadableModelDetail(currentDmDetailModelId);
  }
}

let currentDmDetailModelId = null;

function openDownloadableModelDetail(modelId) {
  currentDmDetailModelId = modelId;
  document.getElementById("providers-view-overview").style.display = "none";
  document.getElementById("providers-view-detail").style.display = "none";
  document.getElementById("downloadable-model-view-detail").style.display = "block";
  renderDownloadableModelDetail(modelId);
}

function closeDownloadableModelDetail() {
  currentDmDetailModelId = null;
  document.getElementById("downloadable-model-view-detail").style.display = "none";
  document.getElementById("providers-view-overview").style.display = "block";
  loadProvidersOverview();
}

function renderDownloadableModelDetail(modelId) {
  const m = (vfDownloadableModels || []).find(x => x.id === modelId);
  if (!m) return;
  const activeSTT = voiceFlowPolicyModelRef || "";
  const isDownloaded = m.status === "downloaded" && m.file_exists;
  const isDownloading = m.status === "downloading";
  const isActiveSTT = isDownloaded && (
    activeSTT === m.full_id ||
    activeSTT === `local/${m.id}` ||
    activeSTT === m.id ||
    activeSTT.endsWith(m.filename)
  );
  const isPolish = m.category === "voice_polishing" || String(m.tag || "").toLowerCase().includes("polish");
  const activePolish = typeof voiceFlowPolishModelRef === "string" ? voiceFlowPolishModelRef : "";
  const isActivePolish = isPolish && isDownloaded && (
    activePolish === m.full_id ||
    activePolish === `local/${m.id}` ||
    activePolish === m.id ||
    activePolish.endsWith(m.filename)
  );
  const languagesCount = (m.languages || []).length;
  const languagesSummary = m.is_multilingual ? `Multilingual (${languagesCount})` : `English (1)`;

  const pct = Number(m.progress || 0).toFixed(1);
  const downloadedMb = Number(m.downloaded_mb != null ? m.downloaded_mb : ((m.downloaded_bytes || 0) / (1024 * 1024))).toFixed(1);
  const totalMb = Number(m.total_mb != null ? m.total_mb : m.size_mb).toFixed(1);
  const remainingMb = Number(m.remaining_mb != null ? m.remaining_mb : Math.max(0, totalMb - downloadedMb)).toFixed(1);
  const speed = m.speed_display || "";
  const eta = m.eta_display || "";

  const nameEl = document.getElementById("dm-detail-name");
  if (nameEl) nameEl.textContent = m.name;
  const subEl = document.getElementById("dm-detail-sub");
  if (subEl) subEl.textContent = isDownloading
    ? `Downloading ${pct}% · ${downloadedMb} / ${totalMb} MB (${remainingMb} MB remaining)`
    : isDownloaded
      ? (isPolish
          ? (isActivePolish ? "Ready / Downloaded · Active Voice Polish Engine" : "Ready / Downloaded · Saved to PC")
          : (isActiveSTT ? "Ready / Downloaded · Active STT Engine" : "Ready / Downloaded · Saved to PC"))
      : "Not downloaded";

  const infoEl = document.getElementById("dm-detail-info");
  if (infoEl) {
    infoEl.innerHTML = `
      <div class="dm-detail-row"><span>Size</span><strong style="color: var(--primary-orange);">${escapeHtml(m.size_display)}</strong></div>
      <div class="dm-detail-row"><span>Format</span><strong>${escapeHtml(m.format || (isPolish ? "Local GGUF (Q4_0)" : "Local GGUF (Q8_0)"))}</strong></div>
      <div class="dm-detail-row"><span>Task / Engine</span><strong style="color: ${isPolish ? '#c084fc' : '#60a5fa'};">${escapeHtml(isPolish ? 'Voice Polishing' : 'Speech-to-Text (STT)')}</strong></div>
      <div class="dm-detail-row"><span>Repository</span><a href="${escapeHtml(m.repo_url)}" target="_blank" rel="noopener noreferrer" class="dm-repo-link"><span>Hugging Face</span> ↗</a></div>
      <div class="dm-detail-row"><span>Languages</span><strong>${escapeHtml(languagesSummary)}</strong></div>
      <div class="dm-lang-tags" style="margin-top: 4px;">${(m.languages || []).map(l => `<span class="dm-lang-pill">${escapeHtml(l)}</span>`).join("")}</div>
      ${m.description ? `<p style="font-size: 12px; color: var(--text-muted); line-height: 1.5; margin: 10px 0 0;">${escapeHtml(m.description)}</p>` : ""}
    `;
  }

  const actionEl = document.getElementById("dm-detail-actions");
  if (actionEl) {
    if (isDownloading) {
      actionEl.innerHTML = `
        <div class="dm-download-active-card">
          <div class="dm-progress-header">
            <span class="dm-progress-title">Downloading · <strong style="color: #76b900;">${pct}%</strong></span>
            <span class="dm-progress-eta">${escapeHtml(eta)}</span>
          </div>
          <div class="dm-progress-track">
            <div class="dm-progress-bar" style="width: ${Math.min(100, Math.max(0, pct))}%;"></div>
          </div>
          <div class="dm-progress-metrics">
            <div class="dm-metric">
              <span class="dm-metric-label">Downloaded</span>
              <strong class="dm-metric-val">${downloadedMb} MB / ${totalMb} MB</strong>
            </div>
            <div class="dm-metric">
              <span class="dm-metric-label">Remaining</span>
              <strong class="dm-metric-val" style="color: var(--primary-orange);">${remainingMb} MB remaining</strong>
            </div>
            <div class="dm-metric">
              <span class="dm-metric-label">Download Speed</span>
              <strong class="dm-metric-val" style="color: #60a5fa;">${escapeHtml(speed || "Connecting...")}</strong>
            </div>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.06);">
            <span style="font-size: 11px; color: var(--text-muted);">Saving whole model directly to your PC</span>
            <button type="button" class="dm-card-cancel-btn" style="padding: 6px 14px; font-size: 11.5px;" onclick="cancelDownloadModel('${escapeJs(m.id)}')">✕ Cancel Download</button>
          </div>
        </div>
      `;
    } else if (isDownloaded) {
      actionEl.innerHTML = `
        <div class="dm-downloaded-card">
          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span class="dm-ready-status">
                <span class="status-dot-indicator connected"></span>
                <strong>Ready / Downloaded</strong>
              </span>
              <span style="font-size: 11.5px; color: var(--text-muted);">${escapeHtml(m.size_display)} · Saved to PC</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              ${isPolish
                ? (isActivePolish
                    ? `<span class="dm-active-stt-pill" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border-color: rgba(168, 85, 247, 0.4);">★ Active Polish Model</span>`
                    : `<button type="button" class="btn-primary" style="padding: 6px 14px; font-size: 12px; background: #a855f7; border-color: #a855f7; color: #fff; font-weight: 700;" onclick="selectDownloadableModelAsPolish('${escapeJs(m.id)}')">Set as Polish Model</button>`
                  )
                : (isActiveSTT
                    ? `<span class="dm-active-stt-pill">★ Active STT Model</span>`
                    : `<button type="button" class="btn-primary" style="padding: 6px 14px; font-size: 12px; background: #76b900; border-color: #76b900; color: #000; font-weight: 700;" onclick="selectDownloadableModelAsSTT('${escapeJs(m.id)}')">Set as STT</button>`
                  )
              }
              <button type="button" class="dm-delete-btn" style="padding: 6px 12px; font-size: 11.5px;" onclick="openDeleteConfirmModal('${escapeJs(m.id)}')">🗑️ Delete Model</button>
            </div>
          </div>
          ${m.local_path ? `<div style="font-size: 11px; color: var(--text-muted); margin-top: 8px; font-family: monospace; word-break: break-all;">Location: ${escapeHtml(m.local_path)}</div>` : ""}
        </div>
      `;
    } else {
      actionEl.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <button type="button" class="dm-btn-download" onclick="startDownloadModel('${escapeJs(m.id)}')">
            <span>↓</span> Download Model (${escapeHtml(m.size_display)})
          </button>
          ${m.status === "failed" && m.error ? `
            <div class="dm-error-box">
              <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; margin-bottom: 2px;">
                <span>⚠️</span> Download Failed
              </div>
              <div>${escapeHtml(m.error)}</div>
              <div style="margin-top: 6px; font-size: 11px; color: var(--text-muted);">Please check your connection and click Retry below.</div>
              <button type="button" class="btn-secondary dm-card-action-btn" style="margin-top: 8px;" onclick="startDownloadModel('${escapeJs(m.id)}')">↻ Retry Download</button>
            </div>
          ` : ""}
        </div>
      `;
    }
  }
}

function openDownloadConfirmModal(modelId) {
  const model = vfDownloadableModels.find(m => m.id === modelId);
  if (!model) return;
  dmTargetModelId = modelId;

  const titleEl = document.getElementById("dm-confirm-modal-title");
  const nameEl = document.getElementById("dm-confirm-model-name");
  const sizeEl = document.getElementById("dm-confirm-model-size");
  const repoEl = document.getElementById("dm-confirm-model-repo");

  if (titleEl) titleEl.textContent = "Confirm Download";
  if (nameEl) nameEl.textContent = model.name;
  if (sizeEl) sizeEl.textContent = model.size_display;
  if (repoEl) {
    repoEl.href = model.repo_url;
    repoEl.textContent = `Hugging Face Repository (${model.name.split(" ")[0]}) ↗`;
  }

  const modal = document.getElementById("download-model-confirm-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeDownloadConfirmModal() {
  const modal = document.getElementById("download-model-confirm-modal");
  if (modal) modal.classList.add("hidden");
  dmTargetModelId = null;
}

async function startDownloadModel(modelId) {
  if (!modelId) return;
  closeDownloadConfirmModal();

  const model = vfDownloadableModels.find(m => m.id === modelId);
  if (model) {
    model.status = "downloading";
    model.progress = 0.0;
    model.downloaded_bytes = 0;
    model.speed_display = "Connecting...";
    model.eta_display = "Starting...";
    renderVoiceDownloadableModels();
  }

  checkDownloadPolling();

  if (typeof vfToast === "function" && model) {
    vfToast(`Starting download for ${model.name}...`);
  }

  try {
    const res = await fetch("/api/downloadable-models/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (!res.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Failed to start download");
    }
  } catch (err) {
    console.error("Error starting model download:", err);
    if (model) {
      model.status = "failed";
      model.error = err.message || "Failed to start download";
      renderVoiceDownloadableModels();
    }
    if (typeof vfToast === "function") {
      vfToast(err.message || "Failed to start download", true);
    }
  }
  loadVoiceDownloadableModels();
}

async function confirmStartDownload() {
  const modelId = dmTargetModelId;
  if (modelId) {
    await startDownloadModel(modelId);
  }
}

async function cancelDownloadModel(modelId) {
  if (!modelId) return;
  const model = vfDownloadableModels.find(m => m.id === modelId);
  if (model) {
    model.status = "not_downloaded";
    model.progress = 0.0;
    model.downloaded_bytes = 0;
    renderVoiceDownloadableModels();
  }
  try {
    const res = await fetch("/api/downloadable-models/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    await res.json();
    if (typeof vfToast === "function") {
      vfToast("Download cancelled.");
    }
  } catch (err) {
    console.error("Error cancelling download:", err);
  }
  loadVoiceDownloadableModels();
}

function openDeleteConfirmModal(modelId) {
  const model = vfDownloadableModels.find(m => m.id === modelId);
  if (!model) return;
  dmDeleteTargetModelId = modelId;

  const nameEl = document.getElementById("dm-delete-model-name");
  if (nameEl) nameEl.textContent = model.name;

  const modal = document.getElementById("delete-model-confirm-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeDeleteConfirmModal() {
  const modal = document.getElementById("delete-model-confirm-modal");
  if (modal) modal.classList.add("hidden");
  dmDeleteTargetModelId = null;
}

async function confirmDeleteModel() {
  const modelId = dmDeleteTargetModelId;
  closeDeleteConfirmModal();
  if (!modelId) return;

  const model = vfDownloadableModels.find(m => m.id === modelId);
  try {
    const res = await fetch("/api/downloadable-models/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (!res.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Failed to delete model");
    }
    if (typeof vfToast === "function") {
      vfToast(`Deleted ${model ? model.name : 'model'} from local storage.`);
    }
    await loadExecVoiceFlowPolicy();
  } catch (err) {
    console.error("Error deleting model:", err);
    if (typeof vfToast === "function") {
      vfToast(err.message || "Failed to delete model", true);
    }
  }
  loadVoiceDownloadableModels();
}

async function selectDownloadableModelAsSTT(modelId) {
  if (!modelId) return;
  try {
    const res = await fetch("/api/downloadable-models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (!res.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Failed to select model");
    }
    if (typeof vfToast === "function") {
      vfToast("Selected as active Speech-to-Text model.");
    }
    await loadExecVoiceFlowPolicy();
  } catch (err) {
    console.error("Error selecting downloadable model:", err);
    if (typeof vfToast === "function") {
      vfToast(err.message || "Could not set STT model", true);
    }
  }
  renderVoiceDownloadableModels();
}

async function selectDownloadableModelAsPolish(modelId) {
  if (!modelId) return;
  try {
    const res = await fetch("/api/downloadable-models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (!res.ok || !data || !data.success) {
      throw new Error((data && data.error) || "Failed to select polish model");
    }
    if (typeof vfToast === "function") {
      vfToast("Selected as active Voice Polishing model.");
    }
    await loadVoiceFlowPolishSettings();
  } catch (err) {
    console.error("Error selecting downloadable polish model:", err);
    if (typeof vfToast === "function") {
      vfToast(err.message || "Could not set Voice Polishing model", true);
    }
  }
  renderVoiceDownloadableModels();
}


// =========================================================================
// CUSTOM PROVIDERS MANAGEMENT — VOICE FLOW & AUDIO FLOW
// =========================================================================

let vfVoiceCustomProviders = [];
let vfAudioCustomProviders = [];

// --- VOICE FLOW CUSTOM PROVIDERS ---
async function loadVoiceCustomProviders() {
  try {
    const res = await fetch("/api/voice-flow/custom-providers/list");
    const data = await res.json();
    vfVoiceCustomProviders = (data && data.providers) || [];
  } catch (e) {
    vfVoiceCustomProviders = [];
  }
  renderVoiceCustomProviderGrid();
}

function renderVoiceCustomProviderGrid() {
  const grid = document.getElementById("voice-custom-provider-grid");
  if (!grid) return;
  grid.className = "providers-cards-grid";
  grid.innerHTML = (vfVoiceCustomProviders || []).map(p => {
    const models = p.models || [];
    const conns = p.connections || (p.api_keys ? p.api_keys : ((p.api_key || p.has_secret) ? [1] : []));
    const activeConns = Array.isArray(conns) ? conns.filter(c => c.is_active !== false && c.is_active !== 0) : [];
    const isConnected = activeConns.length > 0 || Boolean(p.api_key || p.has_secret);
    const connCountText = isConnected ? `${activeConns.length || 1} Connected` : "No connections";
    const logo = vfBrandLogo(p.id, (p.name || "C")[0].toUpperCase());
    return `
      <div class="provider-card-item" onclick="openProviderDetail('${escapeJs(p.id)}')">
        <div class="provider-card-left">
          <div class="provider-card-logo provider-brand-logo">${logo}</div>
          <div class="provider-card-info">
            <span class="provider-card-name">${escapeHtml(p.name || p.id)}</span>
            <span class="provider-card-status">
              <span class="status-dot-indicator ${isConnected ? 'connected' : ''}"></span>
              ${connCountText}
            </span>
          </div>
        </div>
        <label class="toggle-switch" onclick="event.stopPropagation()">
          <input type="checkbox" ${isConnected ? 'checked' : ''} onchange="toggleProviderMaster('${escapeJs(p.id)}', this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    `;
  }).join("");
}

function openVoiceCustomProviderModal() {
  const editIdEl = document.getElementById("voice-c-edit-id");
  if (editIdEl) editIdEl.value = "";
  const titleEl = document.getElementById("voice-c-modal-title");
  if (titleEl) titleEl.textContent = "Add Voice Flow Provider";
  const saveBtn = document.getElementById("voice-c-save-btn");
  if (saveBtn) saveBtn.textContent = "Add provider";
  const nameEl = document.getElementById("voice-c-name");
  if (nameEl) nameEl.value = "";
  const urlEl = document.getElementById("voice-c-url");
  if (urlEl) urlEl.value = "";
  const keyEl = document.getElementById("voice-c-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Enter API key";
  }
  const formatEl = document.getElementById("voice-c-format");
  if (formatEl) formatEl.value = "openai";
  const headersEl = document.getElementById("voice-c-headers");
  if (headersEl) headersEl.value = "";
  const list = document.getElementById("voice-c-model-list");
  if (list) list.innerHTML = "";
  const err = document.getElementById("voice-c-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("voice-c-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("voice-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
  voiceCustomAddModelRow();
}

async function openEditVoiceCustomProviderModal(providerId) {
  let p = (vfVoiceCustomProviders || []).find(item => item.id === providerId);
  if (!p) {
    try {
      const res = await fetch("/api/voice-flow/custom-providers");
      const data = await res.json();
      if (data && data.providers) {
        vfVoiceCustomProviders = data.providers;
        p = (vfVoiceCustomProviders || []).find(item => item.id === providerId);
      }
    } catch (e) {
      console.warn("Could not fetch voice custom providers for edit modal:", e);
    }
  }
  const editIdEl = document.getElementById("voice-c-edit-id");
  if (editIdEl) editIdEl.value = providerId;
  const titleEl = document.getElementById("voice-c-modal-title");
  if (titleEl) titleEl.textContent = "Edit " + ((p && p.name) || "Provider");
  const saveBtn = document.getElementById("voice-c-save-btn");
  if (saveBtn) saveBtn.textContent = "Save Changes";
  const nameEl = document.getElementById("voice-c-name");
  if (nameEl) nameEl.value = (p && p.name) || "";
  const urlEl = document.getElementById("voice-c-url");
  if (urlEl) urlEl.value = (p && p.base_url) || "";
  const keyEl = document.getElementById("voice-c-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Leave blank to keep existing key";
  }
  const formatEl = document.getElementById("voice-c-format");
  if (formatEl) formatEl.value = (p && p.api_format) || "openai";
  const headersEl = document.getElementById("voice-c-headers");
  if (headersEl) {
    headersEl.value = p && p.headers ? (typeof p.headers === "string" ? p.headers : JSON.stringify(p.headers, null, 2)) : "";
  }
  const list = document.getElementById("voice-c-model-list");
  if (list) list.innerHTML = "";
  const models = (p && p.models) || [];
  if (models.length > 0) {
    models.forEach(m => {
      const mid = typeof m === "string" ? m : (m.model_id || m.id || "");
      voiceCustomAddModelRow(mid);
    });
  } else {
    voiceCustomAddModelRow();
  }
  const err = document.getElementById("voice-c-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("voice-c-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("voice-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeVoiceCustomProviderModal() {
  const modal = document.getElementById("voice-custom-provider-modal");
  if (modal) modal.classList.add("hidden");
  const editIdEl = document.getElementById("voice-c-edit-id");
  if (editIdEl) editIdEl.value = "";
}

function voiceCustomAddModelRow(initialVal) {
  const list = document.getElementById("voice-c-model-list");
  if (!list) return;
  const row = document.createElement("div");
  row.className = "voice-c-model-row";
  row.style.cssText = "display:flex;gap:6px;margin-bottom:6px;";
  row.innerHTML = '<input class="voice-c-mid" placeholder="Model ID (e.g. whisper-1 or llama-3)" value="' + (initialVal ? escapeHtml(initialVal) : '') + '" style="flex:1;padding:7px;border:1px solid var(--border-color);border-radius:6px;background:var(--surface-2);color:var(--text);">' +
    '<button class="vf-text-button danger" onclick="this.parentElement.remove()">×</button>';
  list.appendChild(row);
}

async function testVoiceCustomProviderFromModal() {
  const base_url = (document.getElementById("voice-c-url")?.value || "").trim();
  const api_key = (document.getElementById("voice-c-key")?.value || "").trim();
  const api_format = document.getElementById("voice-c-format")?.value || "openai";
  const edit_id = (document.getElementById("voice-c-edit-id")?.value || "").trim();
  const rawHeaders = (document.getElementById("voice-c-headers")?.value || "").trim();
  const testOut = document.getElementById("voice-c-test-out");
  const testBtn = document.getElementById("voice-c-test-btn");

  const modelInputs = Array.from(document.querySelectorAll("#voice-c-model-list .voice-c-model-row .voice-c-mid"));
  const model_id = modelInputs.map(i => i.value.trim()).filter(Boolean)[0] || "default";

  if (!base_url) {
    if (testOut) {
      testOut.style.display = "block";
      testOut.style.background = "rgba(239, 68, 68, 0.15)";
      testOut.style.color = "#ef4444";
      testOut.textContent = "Base URL is required to test connection.";
    }
    return;
  }

  let headersObj = null;
  if (rawHeaders) {
    try {
      headersObj = JSON.parse(rawHeaders);
    } catch (e) {
      if (testOut) {
        testOut.style.display = "block";
        testOut.style.background = "rgba(239, 68, 68, 0.15)";
        testOut.style.color = "#ef4444";
        testOut.textContent = "Custom headers must be valid JSON: " + e.message;
      }
      return;
    }
  }

  if (testBtn) { testBtn.disabled = true; testBtn.innerHTML = "<span>⏳</span> Testing…"; }
  if (testOut) {
    testOut.style.display = "block";
    testOut.style.background = "rgba(59, 130, 246, 0.15)";
    testOut.style.color = "var(--text)";
    testOut.textContent = "Connecting to endpoint…";
  }

  try {
    const res = await fetch("/api/voice-flow/custom-providers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url,
        api_key,
        api_format,
        headers: headersObj,
        model_id,
        edit_id: edit_id || undefined,
      }),
    });
    const data = await res.json();
    if (data && data.success && data.ok !== false) {
      if (testOut) {
        testOut.style.background = "rgba(34, 197, 94, 0.15)";
        testOut.style.color = "#22c55e";
        testOut.textContent = "✅ Connection successful (" + (data.latency_ms || 0) + "ms)";
      }
    } else {
      if (testOut) {
        testOut.style.background = "rgba(239, 68, 68, 0.15)";
        testOut.style.color = "#ef4444";
        testOut.textContent = "❌ Test failed: " + (data?.error || "Connection refused");
      }
    }
  } catch (err) {
    if (testOut) {
      testOut.style.background = "rgba(239, 68, 68, 0.15)";
      testOut.style.color = "#ef4444";
      testOut.textContent = "❌ Test failed: " + (err.message || "Network error");
    }
  } finally {
    if (testBtn) { testBtn.disabled = false; testBtn.innerHTML = "<span>🧪</span> Test Connection"; }
  }
}

async function saveVoiceCustomProvider() {
  const err = document.getElementById("voice-c-error");
  const editId = (document.getElementById("voice-c-edit-id")?.value || "").trim();
  const name = (document.getElementById("voice-c-name")?.value || "").trim();
  const base_url = (document.getElementById("voice-c-url")?.value || "").trim();
  const api_key = (document.getElementById("voice-c-key")?.value || "").trim();
  const api_format = document.getElementById("voice-c-format")?.value || "openai";
  const rawHeaders = (document.getElementById("voice-c-headers")?.value || "").trim();
  const models = Array.from(document.querySelectorAll("#voice-c-model-list .voice-c-model-row .voice-c-mid"))
    .map(i => i.value.trim())
    .filter(Boolean)
    .map(mid => ({ model_id: mid, display_name: mid, is_active: true, custom: true }));
  
  if (err) err.style.display = "none";
  if (!name || !base_url || !models.length) {
    if (err) {
      err.textContent = "Name, Base URL, and at least one Model ID are required.";
      err.style.display = "block";
    }
    return;
  }

  let headersObj = null;
  if (rawHeaders) {
    try {
      headersObj = JSON.parse(rawHeaders);
    } catch (e) {
      if (err) {
        err.textContent = "Custom headers must be valid JSON: " + e.message;
        err.style.display = "block";
      }
      return;
    }
  }

  try {
    const endpoint = editId ? "/api/voice-flow/custom-providers/update" : "/api/voice-flow/custom-providers/add";
    const payload = {
      id: editId || undefined,
      name,
      base_url,
      api_format,
      headers: headersObj,
      models,
    };
    if (api_key || !editId) {
      payload.api_key = api_key;
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data || !data.success) throw new Error(data?.error || (editId ? "Could not update provider." : "Could not add provider."));
    closeVoiceCustomProviderModal();
    vfVoiceCustomProviders = data.providers || [];
    renderVoiceCustomProviderGrid();
    if (editId && currentSelectedProvider === editId) {
      loadProviderDetails(editId);
    }
    if (typeof vfToast === "function") vfToast(editId ? "Voice Flow custom provider updated." : "Voice Flow custom provider added.");
  } catch (e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = "block";
    }
  }
}

async function deleteVoiceCustomProvider(id) {
  try {
    const res = await fetch("/api/voice-flow/custom-providers/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    vfVoiceCustomProviders = (data && data.providers) || [];
    renderVoiceCustomProviderGrid();
    if (typeof vfToast === "function") vfToast("Voice Flow custom provider deleted.");
  } catch (e) {
    if (typeof vfToast === "function") vfToast(e.message || "Failed to delete custom provider", true);
  }
}

async function vfDeleteVoiceCustomProviderWhole(providerId) {
  if (!await vfConfirm("Delete this Voice Flow custom provider, its API keys, and all models? This cannot be undone.")) return;
  await deleteVoiceCustomProvider(providerId);
  closeProviderDetail();
}

async function deleteProviderCustomModel(modelId, providerId) {
  if (!await vfConfirm("Are you sure you want to delete this custom model?")) return;

  try {
    const res = await fetch("/api/providers/models/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: modelId, provider: providerId }),
    });
    const data = await res.json();
    if (data.success) {
      loadProviderDetails(providerId);
    } else {
      alert("Failed to delete model: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    alert("Error deleting model: " + e.message);
  }
}

// --- AUDIO FLOW CUSTOM PROVIDERS ---
async function loadAudioCustomProviders() {
  try {
    const res = await fetch("/api/audio-flow/custom-providers/list");
    const data = await res.json();
    vfAudioCustomProviders = (data && data.providers) || [];
  } catch (e) {
    vfAudioCustomProviders = [];
  }
  renderAudioCustomProviderGrid();
}

function renderAudioCustomProviderGrid() {
  const grid = document.getElementById("audio-custom-provider-grid");
  if (!grid) return;
  grid.className = "providers-cards-grid";
  grid.innerHTML = (vfAudioCustomProviders || []).map(p => {
    const models = p.models || [];
    const conns = p.connections || (p.api_keys ? p.api_keys : ((p.api_key || p.has_secret) ? [1] : []));
    const activeConns = Array.isArray(conns) ? conns.filter(c => c.is_active !== false && c.is_active !== 0) : [];
    const isConnected = activeConns.length > 0 || Boolean(p.api_key || p.has_secret);
    const connCountText = isConnected ? `${activeConns.length || 1} Connected` : "No connections";
    const logo = vfBrandLogo(p.id, (p.name || "A")[0].toUpperCase());
    return `
      <div class="provider-card-item audio-provider-card" onclick="openAudioProviderDetail('${escapeJs(p.id)}')">
        <div class="provider-card-left">
          <div class="provider-card-logo provider-brand-logo">${logo}</div>
          <div class="provider-card-info">
            <span class="provider-card-name">${escapeHtml(p.name || p.id)}</span>
            <span class="provider-card-status">
              <span class="status-dot-indicator ${isConnected ? 'connected' : ''}"></span>
              ${connCountText}
            </span>
          </div>
        </div>
        <label class="toggle-switch" onclick="event.stopPropagation()">
          <input type="checkbox" ${isConnected ? 'checked' : ''} onchange="toggleAudioProviderMaster('${escapeJs(p.id)}', this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    `;
  }).join("");
}

function openAudioCustomProviderModal() {
  const editIdEl = document.getElementById("audio-c-edit-id");
  if (editIdEl) editIdEl.value = "";
  const titleEl = document.getElementById("audio-c-modal-title");
  if (titleEl) titleEl.textContent = "Add Audio Flow Provider";
  const saveBtn = document.getElementById("audio-c-save-btn");
  if (saveBtn) saveBtn.textContent = "Add provider";
  const nameEl = document.getElementById("audio-c-name");
  if (nameEl) nameEl.value = "";
  const urlEl = document.getElementById("audio-c-url");
  if (urlEl) urlEl.value = "";
  const keyEl = document.getElementById("audio-c-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Enter API key";
  }
  const formatEl = document.getElementById("audio-c-format");
  if (formatEl) formatEl.value = "openai";
  const headersEl = document.getElementById("audio-c-headers");
  if (headersEl) headersEl.value = "";
  const list = document.getElementById("audio-c-model-list");
  if (list) list.innerHTML = "";
  const err = document.getElementById("audio-c-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("audio-c-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("audio-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
  audioCustomAddModelRow();
}

async function openEditAudioCustomProviderModal(providerId) {
  let p = (vfAudioCustomProviders || []).find(item => item.id === providerId);
  if (!p) {
    try {
      const res = await fetch("/api/audio-flow/custom-providers");
      const data = await res.json();
      if (data && data.providers) {
        vfAudioCustomProviders = data.providers;
        p = (vfAudioCustomProviders || []).find(item => item.id === providerId);
      }
    } catch (e) {
      console.warn("Could not fetch audio custom providers for edit modal:", e);
    }
  }
  const editIdEl = document.getElementById("audio-c-edit-id");
  if (editIdEl) editIdEl.value = providerId;
  const titleEl = document.getElementById("audio-c-modal-title");
  if (titleEl) titleEl.textContent = "Edit " + ((p && p.name) || "Provider");
  const saveBtn = document.getElementById("audio-c-save-btn");
  if (saveBtn) saveBtn.textContent = "Save Changes";
  const nameEl = document.getElementById("audio-c-name");
  if (nameEl) nameEl.value = (p && p.name) || "";
  const urlEl = document.getElementById("audio-c-url");
  if (urlEl) urlEl.value = (p && p.base_url) || "";
  const keyEl = document.getElementById("audio-c-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Leave blank to keep existing key";
  }
  const formatEl = document.getElementById("audio-c-format");
  if (formatEl) formatEl.value = (p && p.api_format) || "openai";
  const headersEl = document.getElementById("audio-c-headers");
  if (headersEl) {
    headersEl.value = p && p.headers ? (typeof p.headers === "string" ? p.headers : JSON.stringify(p.headers, null, 2)) : "";
  }
  const list = document.getElementById("audio-c-model-list");
  if (list) list.innerHTML = "";
  const models = (p && p.models) || [];
  if (models.length > 0) {
    models.forEach(m => {
      const mid = typeof m === "string" ? m : (m.model_id || m.id || "");
      audioCustomAddModelRow(mid);
    });
  } else {
    audioCustomAddModelRow();
  }
  const err = document.getElementById("audio-c-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("audio-c-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("audio-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeAudioCustomProviderModal() {
  const modal = document.getElementById("audio-custom-provider-modal");
  if (modal) modal.classList.add("hidden");
  const editIdEl = document.getElementById("audio-c-edit-id");
  if (editIdEl) editIdEl.value = "";
}

function audioCustomAddModelRow(initialVal) {
  const list = document.getElementById("audio-c-model-list");
  if (!list) return;
  const row = document.createElement("div");
  row.className = "audio-c-model-row";
  row.style.cssText = "display:flex;gap:6px;margin-bottom:6px;";
  row.innerHTML = '<input class="audio-c-mid" placeholder="Voice / Model ID (e.g. alloy or kokoro-v1)" value="' + (initialVal ? escapeHtml(initialVal) : '') + '" style="flex:1;padding:7px;border:1px solid var(--border-color);border-radius:6px;background:var(--surface-2);color:var(--text);">' +
    '<button class="vf-text-button danger" onclick="this.parentElement.remove()">×</button>';
  list.appendChild(row);
}

async function testAudioCustomProviderFromModal() {
  const base_url = (document.getElementById("audio-c-url")?.value || "").trim();
  const api_key = (document.getElementById("audio-c-key")?.value || "").trim();
  const api_format = document.getElementById("audio-c-format")?.value || "openai";
  const edit_id = (document.getElementById("audio-c-edit-id")?.value || "").trim();
  const rawHeaders = (document.getElementById("audio-c-headers")?.value || "").trim();
  const testOut = document.getElementById("audio-c-test-out");
  const testBtn = document.getElementById("audio-c-test-btn");

  const modelInputs = Array.from(document.querySelectorAll("#audio-c-model-list .audio-c-model-row .audio-c-mid"));
  const model_id = modelInputs.map(i => i.value.trim()).filter(Boolean)[0] || "default";

  if (!base_url) {
    if (testOut) {
      testOut.style.display = "block";
      testOut.style.background = "rgba(239, 68, 68, 0.15)";
      testOut.style.color = "#ef4444";
      testOut.textContent = "Base URL is required to test connection.";
    }
    return;
  }

  let headersObj = null;
  if (rawHeaders) {
    try {
      headersObj = JSON.parse(rawHeaders);
    } catch (e) {
      if (testOut) {
        testOut.style.display = "block";
        testOut.style.background = "rgba(239, 68, 68, 0.15)";
        testOut.style.color = "#ef4444";
        testOut.textContent = "Custom headers must be valid JSON: " + e.message;
      }
      return;
    }
  }

  if (testBtn) { testBtn.disabled = true; testBtn.innerHTML = "<span>⏳</span> Testing…"; }
  if (testOut) {
    testOut.style.display = "block";
    testOut.style.background = "rgba(59, 130, 246, 0.15)";
    testOut.style.color = "var(--text)";
    testOut.textContent = "Connecting to endpoint…";
  }

  try {
    const res = await fetch("/api/audio-flow/custom-providers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url,
        api_key,
        api_format,
        headers: headersObj,
        model_id,
        edit_id: edit_id || undefined,
      }),
    });
    const data = await res.json();
    if (data && data.success && data.ok !== false) {
      if (testOut) {
        testOut.style.background = "rgba(34, 197, 94, 0.15)";
        testOut.style.color = "#22c55e";
        testOut.textContent = "✅ Connection successful (" + (data.latency_ms || 0) + "ms)";
      }
    } else {
      if (testOut) {
        testOut.style.background = "rgba(239, 68, 68, 0.15)";
        testOut.style.color = "#ef4444";
        testOut.textContent = "❌ Test failed: " + (data?.error || "Connection refused");
      }
    }
  } catch (err) {
    if (testOut) {
      testOut.style.background = "rgba(239, 68, 68, 0.15)";
      testOut.style.color = "#ef4444";
      testOut.textContent = "❌ Test failed: " + (err.message || "Network error");
    }
  } finally {
    if (testBtn) { testBtn.disabled = false; testBtn.innerHTML = "<span>🧪</span> Test Connection"; }
  }
}

async function saveAudioCustomProvider() {
  const err = document.getElementById("audio-c-error");
  const editId = (document.getElementById("audio-c-edit-id")?.value || "").trim();
  const name = (document.getElementById("audio-c-name")?.value || "").trim();
  const base_url = (document.getElementById("audio-c-url")?.value || "").trim();
  const api_key = (document.getElementById("audio-c-key")?.value || "").trim();
  const api_format = document.getElementById("audio-c-format")?.value || "openai";
  const rawHeaders = (document.getElementById("audio-c-headers")?.value || "").trim();
  const models = Array.from(document.querySelectorAll("#audio-c-model-list .audio-c-model-row .audio-c-mid"))
    .map(i => i.value.trim())
    .filter(Boolean)
    .map(mid => ({ model_id: mid, display_name: mid, is_active: true, custom: true }));
  
  if (err) err.style.display = "none";
  if (!name || !base_url || !models.length) {
    if (err) {
      err.textContent = "Name, Base URL, and at least one Voice / Model ID are required.";
      err.style.display = "block";
    }
    return;
  }

  let headersObj = null;
  if (rawHeaders) {
    try {
      headersObj = JSON.parse(rawHeaders);
    } catch (e) {
      if (err) {
        err.textContent = "Custom headers must be valid JSON: " + e.message;
        err.style.display = "block";
      }
      return;
    }
  }

  try {
    const endpoint = editId ? "/api/audio-flow/custom-providers/update" : "/api/audio-flow/custom-providers/add";
    const payload = {
      id: editId || undefined,
      name,
      base_url,
      api_format,
      headers: headersObj,
      models,
    };
    if (api_key || !editId) {
      payload.api_key = api_key;
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data || !data.success) throw new Error(data?.error || (editId ? "Could not update provider." : "Could not add provider."));
    closeAudioCustomProviderModal();
    vfAudioCustomProviders = data.providers || [];
    renderAudioCustomProviderGrid();
    if (editId && currentAudioProvider === editId) {
      loadAudioProviderDetails(editId);
    }
    if (typeof vfToast === "function") vfToast(editId ? "Audio Flow custom provider updated." : "Audio Flow custom provider added.");
  } catch (e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = "block";
    }
  }
}

async function deleteAudioCustomProvider(id) {
  try {
    const res = await fetch("/api/audio-flow/custom-providers/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    vfAudioCustomProviders = (data && data.providers) || [];
    renderAudioCustomProviderGrid();
    if (typeof vfToast === "function") vfToast("Audio Flow custom provider deleted.");
  } catch (e) {
    if (typeof vfToast === "function") vfToast(e.message || "Failed to delete custom provider", true);
  }
}

async function vfDeleteAudioCustomProviderWhole(providerId) {
  if (!await vfConfirm("Delete this Audio Flow custom provider, its API keys, and all voices? This cannot be undone.")) return;
  await deleteAudioCustomProvider(providerId);
  closeAudioProviderDetail();
}

async function deleteAudioCustomModel(modelId, providerId) {
  if (!await vfConfirm("Are you sure you want to delete this custom voice model?")) return;

  try {
    const res = await fetch("/api/audio-providers/models/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: modelId, provider: providerId }),
    });
    const data = await res.json();
    if (data.success) {
      loadAudioProviderDetails(providerId);
    } else {
      alert("Failed to delete voice: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    alert("Error deleting voice: " + e.message);
  }
}

// ============================================================================
// Multi-Account Authentication & Simplified Profile Management
// ============================================================================

let currentAccountData = null;
let currentAuthMode = "signin"; // "signin" | "signup"
let googleAuthPollTimer = null;

async function initAccountAuth() {
  await loadAccountSettingsView();
}

function openAccountModal(tab = 'account') {
  openSettings('account');
}

function closeAccountModal() {
  closeSettings();
}

function switchAccountTab(tab) {
  openSettings('account');
}

async function loadAccountSettingsView() {
  try {
    const res = await safeFetchJson(`/api/auth/status?t=${Date.now()}`);
    if (!res || !res.success) return;

    currentAccountData = res;
    const isGuest = !res.authenticated || !!res.is_guest || (res.active_account && res.active_account.email === "primary@flow.local" && !res.active_account.google_id);
    const isAuthenticated = !isGuest && !!res.active_account;
    const active = isAuthenticated ? res.active_account : null;
    const accounts = (res.accounts || []).filter(acc => !acc.email.endsWith("@flow.local") || !!acc.google_id);

    const signedInView = document.getElementById("account-signed-in-view");
    const signedOutView = document.getElementById("account-signed-out-view");

    if (isAuthenticated && active) {
      if (signedInView) signedInView.style.display = "block";
      if (signedOutView) signedOutView.style.display = "none";

      // 1. Render Current Active Profile
      const avatarEl = document.getElementById("account-current-avatar");
      const nameEl = document.getElementById("account-current-name");
      const emailEl = document.getElementById("account-current-email");

      if (avatarEl) {
        if (active.avatar_url) {
          avatarEl.innerHTML = `<img src="${escapeHtml(active.avatar_url)}" alt="Avatar" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
        } else {
          const initial = (active.username || active.email || "G").charAt(0).toUpperCase();
          avatarEl.textContent = initial;
          avatarEl.style.background = active.avatar_color || "#ff6a00";
        }
      }
      if (nameEl) nameEl.textContent = active.username || "Google User";
      if (emailEl) emailEl.textContent = active.email || "";

      // 2. Render Switch Account Section (only other accounts)
      const switchSection = document.getElementById("account-switch-section");
      const savedListEl = document.getElementById("account-saved-list");
      const otherAccounts = accounts.filter(acc => acc.id !== active.id);

      if (switchSection && savedListEl) {
        if (otherAccounts.length === 0) {
          switchSection.style.display = "none";
        } else {
          switchSection.style.display = "block";
          savedListEl.innerHTML = otherAccounts.map(acc => {
            const initial = (acc.username || acc.email || "G").charAt(0).toUpperCase();
            const color = acc.avatar_color || "#ff6a00";
            const avatarHtml = acc.avatar_url
              ? `<img src="${escapeHtml(acc.avatar_url)}" alt="Avatar" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`
              : `${initial}`;
            return `
              <div class="account-saved-item">
                <div class="account-saved-item-left">
                  <div class="account-saved-avatar" style="background: ${color}">${avatarHtml}</div>
                  <div class="account-saved-meta">
                    <span class="account-saved-name">${escapeHtml(acc.username || '')}</span>
                    <span class="account-saved-email">${escapeHtml(acc.email || '')}</span>
                  </div>
                </div>
                <button type="button" class="account-switch-btn" onclick="handleSwitchAccountDirect('${escapeHtml(acc.id)}')">
                  Switch
                </button>
              </div>
            `;
          }).join("");
        }
      }
    } else {
      // Signed Out State
      if (signedInView) signedInView.style.display = "none";
      if (signedOutView) signedOutView.style.display = "flex";

      const signedOutSwitch = document.getElementById("account-signed-out-switch-section");
      const signedOutList = document.getElementById("account-signed-out-saved-list");
      if (signedOutSwitch && signedOutList) {
        if (accounts.length === 0) {
          signedOutSwitch.style.display = "none";
        } else {
          signedOutSwitch.style.display = "block";
          signedOutList.innerHTML = accounts.map(acc => {
            const initial = (acc.username || acc.email || "G").charAt(0).toUpperCase();
            const color = acc.avatar_color || "#ff6a00";
            const avatarHtml = acc.avatar_url
              ? `<img src="${escapeHtml(acc.avatar_url)}" alt="Avatar" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`
              : `${initial}`;
            return `
              <div class="account-saved-item">
                <div class="account-saved-item-left">
                  <div class="account-saved-avatar" style="background: ${color}">${avatarHtml}</div>
                  <div class="account-saved-meta">
                    <span class="account-saved-name">${escapeHtml(acc.username || '')}</span>
                    <span class="account-saved-email">${escapeHtml(acc.email || '')}</span>
                  </div>
                </div>
                <button type="button" class="account-switch-btn" onclick="handleSwitchAccountDirect('${escapeHtml(acc.id)}')">
                  Switch
                </button>
              </div>
            `;
          }).join("");
        }
      }
    }
  } catch (err) {
    console.debug("[ACCOUNT] Failed to load account view:", err);
  }
}

async function handleSwitchAccountDirect(accountId) {
  try {
    const res = await fetch("/api/auth/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || "Failed to switch account.");
    }
    await loadAccountSettingsView();
    reloadAllApplicationMemory();
    if (typeof vfToast === "function") {
      vfToast("Switched to account: " + (data.active_account?.username || data.active_account?.email || ""));
    }
  } catch (err) {
    if (typeof vfAlert === "function") vfAlert("Could not switch account: " + err.message);
    else if (typeof vfToast === "function") vfToast("Could not switch account: " + err.message, true);
  }
}

async function handleSimpleSignOut() {
  if (!await vfConfirm({
    title: "Sign Out",
    badge: "Account Session",
    icon: "🚪",
    message: "Are you sure you want to sign out of your Google account on this device?",
    confirmText: "Sign Out",
    cancelText: "Cancel",
    type: "signout"
  })) return;
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    await loadAccountSettingsView();
    reloadAllApplicationMemory();
    if (typeof vfToast === "function") vfToast("Signed out.");
  } catch (err) {
    console.debug("[ACCOUNT] Sign out error:", err);
  }
}

async function handleGoogleAccountSignIn() {
  const btn = document.getElementById("btn-google-signin");
  const btnText = document.getElementById("btn-google-signin-text");
  const feedback = document.getElementById("simple-account-feedback");

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = "Opening Google Sign-In...";
  if (feedback) { feedback.className = "account-feedback-msg hidden"; feedback.textContent = ""; }

  try {
    const res = await fetch("/api/auth/google/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok || !data.success || !data.pair_token) {
      throw new Error(data.error || "Could not launch Google Sign-In.");
    }

    const pairToken = data.pair_token;
    if (btnText) btnText.textContent = "Waiting for Google authorization in browser...";
    if (typeof vfToast === "function") vfToast("Opening Google Sign-In in browser...");

    if (googleAuthPollTimer) clearInterval(googleAuthPollTimer);

    let attempts = 0;
    const maxAttempts = 80; // ~120s
    googleAuthPollTimer = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(googleAuthPollTimer);
        googleAuthPollTimer = null;
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = "Continue with Google";
        if (feedback) {
          feedback.className = "account-feedback-msg error";
          feedback.textContent = "Sign-in timed out. Please try again.";
        }
        return;
      }

      try {
        const pollRes = await fetch(`/api/auth/google/status?pair_token=${encodeURIComponent(pairToken)}&t=${Date.now()}`);
        const pollData = await pollRes.json();
        if (pollData && pollData.claimed) {
          clearInterval(googleAuthPollTimer);
          googleAuthPollTimer = null;
          if (btn) btn.disabled = false;
          if (btnText) btnText.textContent = "Continue with Google";
          if (feedback) {
            feedback.className = "account-feedback-msg success";
            feedback.textContent = "Signed in with Google successfully!";
          }
          await loadAccountSettingsView();
          reloadAllApplicationMemory();
          if (typeof vfToast === "function") {
            vfToast("Signed in as " + (pollData.active_account?.username || pollData.active_account?.email || "Google user"));
          }
        }
      } catch (_) {}
    }, 1500);

  } catch (err) {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = "Continue with Google";
    if (feedback) {
      feedback.className = "account-feedback-msg error";
      feedback.textContent = err.message || "Failed to start Google sign in.";
    }
  }
}

function reloadAllApplicationMemory() {
  // Seamlessly reload all application state without page reload
  resetAllSubViews();
  resetPageScroll();
  try { if (typeof loadSavedApiKeys === "function") loadSavedApiKeys(); } catch (_) {}
  try { if (typeof loadDictionary === "function") loadDictionary(); } catch (_) {}
  try { if (typeof loadStyleSettings === "function") loadStyleSettings(); } catch (_) {}
  try { if (typeof renderStyleCategory === "function") renderStyleCategory("personal"); } catch (_) {}
  try { if (typeof loadHome === "function") loadHome(); } catch (_) {}
  try { if (typeof loadInsights === "function") loadInsights(); } catch (_) {}
  try { if (typeof loadVoiceFlowPolishSettings === "function") loadVoiceFlowPolishSettings(); } catch (_) {}
  try { if (typeof renderProviderConnectionsList === "function") renderProviderConnectionsList(); } catch (_) {}
  try { if (typeof loadAudioFlowPage === "function") loadAudioFlowPage(); } catch (_) {}
  try { if (typeof loadAudioFlow === "function") loadAudioFlow(); } catch (_) {}
  requestAnimationFrame(() => resetPageScroll());
  setTimeout(() => resetPageScroll(), 100);
}

// Background utility functions for vault export/import
async function handleVaultExport(pass) {
  if (!pass || pass.length < 4) return { success: false, error: "Password must be at least 4 chars." };
  const res = await fetch("/api/auth/vault/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passphrase: pass }),
  });
  return await res.json();
}

async function handleVaultImport(pass, vaultData) {
  const res = await fetch("/api/auth/vault/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passphrase: pass, vault_data: vaultData }),
  });
  return await res.json();
}

// =============================================================================
// macOS Permissions Onboarding Modal & Settings Integration
// =============================================================================
async function checkMacOSPermissions() {
  try {
    const res = await fetch("/api/platform/permissions");
    if (!res.ok) return null;
    const data = await res.json();
    return data && data.platform === "macos" ? data : null;
  } catch (_) {
    return null;
  }
}

async function openMacOSPermissionSettings(key) {
  try {
    const res = await fetch("/api/platform/permissions/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

function renderMacOSPermissionsList(permissions) {
  const container = document.getElementById("vf-macos-perm-list");
  if (!container) return;
  container.innerHTML = "";

  const icons = {
    microphone: "🎙️",
    accessibility: "♿",
    input_monitoring: "⌨️",
  };

  permissions.forEach((perm) => {
    const row = document.createElement("div");
    row.style.cssText = "display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; gap: 12px;";

    const left = document.createElement("div");
    left.style.cssText = "display: flex; align-items: flex-start; gap: 12px; flex: 1;";

    const icon = document.createElement("div");
    icon.style.cssText = "font-size: 20px; line-height: 1; padding-top: 2px;";
    icon.textContent = icons[perm.key] || "⚙️";

    const textWrap = document.createElement("div");
    const title = document.createElement("div");
    title.style.cssText = "font-size: 13.5px; font-weight: 600; color: var(--text, #fff); margin-bottom: 2px;";
    title.textContent = perm.label;

    const desc = document.createElement("div");
    desc.style.cssText = "font-size: 12px; color: var(--text-secondary, #94a3b8); line-height: 1.4;";
    desc.textContent = perm.description;

    textWrap.appendChild(title);
    textWrap.appendChild(desc);
    left.appendChild(icon);
    left.appendChild(textWrap);

    const right = document.createElement("div");
    if (perm.granted) {
      const grantedBadge = document.createElement("span");
      grantedBadge.style.cssText = "display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 9999px; background: rgba(34,197,94,0.15); color: #4ade80; font-size: 12px; font-weight: 600;";
      grantedBadge.textContent = "✓ Granted";
      right.appendChild(grantedBadge);
    } else {
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.style.cssText = "padding: 6px 12px; border-radius: 6px; background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.4); color: #c7d2fe; font-size: 12px; font-weight: 600; cursor: pointer;";
      openBtn.textContent = "Open Settings";
      openBtn.onclick = async () => {
        openBtn.textContent = "Opening...";
        await openMacOSPermissionSettings(perm.key);
        setTimeout(refreshMacOSPermissionsModal, 1500);
      };
      right.appendChild(openBtn);
    }

    row.appendChild(left);
    row.appendChild(right);
    container.appendChild(row);
  });
}

function hideMacOSPermissionsModal() {
  const modal = document.getElementById("vf-macos-permissions-modal");
  if (modal) modal.style.display = "none";
}

async function refreshMacOSPermissionsModal() {
  const data = await checkMacOSPermissions();
  if (!data) return hideMacOSPermissionsModal();
  if (data.allRequiredGranted) {
    hideMacOSPermissionsModal();
    return;
  }
  renderMacOSPermissionsList(data.permissions || []);
}

async function initMacOSPermissionsOnboarding() {
  const data = await checkMacOSPermissions();
  if (!data || data.allRequiredGranted) return;
  if (sessionStorage.getItem("vf_macos_perm_dismissed")) return;

  const modal = document.getElementById("vf-macos-permissions-modal");
  if (!modal) return;

  renderMacOSPermissionsList(data.permissions || []);
  modal.style.display = "flex";

  const closeBtn = document.getElementById("vf-macos-perm-close-x");
  const dismissBtn = document.getElementById("vf-macos-perm-btn-dismiss");
  const refreshBtn = document.getElementById("vf-macos-perm-btn-refresh");

  const dismiss = () => {
    sessionStorage.setItem("vf_macos_perm_dismissed", "1");
    hideMacOSPermissionsModal();
  };

  if (closeBtn) closeBtn.onclick = dismiss;
  if (dismissBtn) dismissBtn.onclick = dismiss;
  if (refreshBtn) refreshBtn.onclick = () => refreshMacOSPermissionsModal();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(initMacOSPermissionsOnboarding, 600);
    initPlatformAdaptation();
  });
} else {
  setTimeout(initMacOSPermissionsOnboarding, 600);
  initPlatformAdaptation();
}

// =============================================================================
// Cross-Platform UI Adaptation (macOS vs Windows)
// =============================================================================
window.vfPlatformInfo = null;

async function initPlatformAdaptation() {
  try {
    const res = await fetch("/api/platform/info");
    if (!res.ok) return;
    const info = await res.json();
    if (!info || !info.success) return;
    window.vfPlatformInfo = info;

    const isMac = !!info.is_macos;

    // 1. Runtime badge in Settings > System
    const runtimeBadge = document.getElementById("runtime-os-badge");
    if (runtimeBadge && info.runtime_badge) {
      runtimeBadge.textContent = info.runtime_badge;
    }

    // 2. Runtime tooltip
    const runtimeTip = document.getElementById("runtime-tip-span");
    if (runtimeTip && info.runtime_tip) {
      runtimeTip.setAttribute("data-tip", info.runtime_tip);
    }

    // 3. Auto-Startup tooltip
    const autostartTip = document.getElementById("autostart-tip-span");
    if (autostartTip && info.autostart_tip) {
      autostartTip.setAttribute("data-tip", info.autostart_tip);
    }

    // 4. Show in Taskbar / Dock title & tooltip
    const taskbarTitle = document.getElementById("show-in-taskbar-title");
    if (taskbarTitle && info.taskbar_label) {
      const tipSpan = document.getElementById("show-in-taskbar-tip");
      const tipAttr = tipSpan ? tipSpan.outerHTML : "";
      taskbarTitle.innerHTML = `${info.taskbar_label} ${tipAttr}`;
      const updatedTip = document.getElementById("show-in-taskbar-tip");
      if (updatedTip && info.taskbar_tip) {
        updatedTip.setAttribute("data-tip", info.taskbar_tip);
      }
    }

    // 5. Onboarding tagline & dictation description
    const obTagline = document.getElementById("onboarding-tagline");
    if (obTagline) {
      obTagline.textContent = isMac
        ? "Your complete voice-driven productivity suite for macOS."
        : "Your complete voice-driven productivity suite for Windows.";
    }

    const obDictate = document.getElementById("onboarding-dictate-desc");
    if (obDictate) {
      obDictate.textContent = isMac
        ? "Speak your thoughts & dictate across any Mac application"
        : "Speak your thoughts & dictate across any Windows application";
    }

    // 6. Hotkey select options and pill
    if (isMac) {
      const pttKbd = document.getElementById("ptt-current-kbd");
      if (pttKbd && pttKbd.textContent.includes("Ctrl+Win")) {
        pttKbd.textContent = "Cmd+Opt";
      }

      const hotkeySelects = document.querySelectorAll("#hotkey-trigger-select, #settings-hotkey-select");
      hotkeySelects.forEach((sel) => {
        const opt = sel.querySelector('option[value="ctrl_win"]');
        if (opt) {
          opt.textContent = "Cmd + Option (Default)";
        }
      });

      const hotkeyHint = document.getElementById("record-hotkey-hint");
      if (hotkeyHint) {
        hotkeyHint.innerHTML = "Click <b>Record Any Key</b>, then press any single key (e.g. F8, Space) or combination (Cmd+Opt, Option+Space, Cmd+Shift+D).";
      }
    }
  } catch (err) {
    console.debug("[PLATFORM] Platform adaptation check skipped:", err);
  }
}

