let vfCatalog = {providers: [], models: [], active_model: "local/deterministic"};
let vfCatalogLoaded = false;
let vfVideos = [];
let vfPollTimer = null;
let vfDeleteTarget = null;
let vfPreviewVideo = null;
let vfCurrentProvider = null;
let vfCurrentProviderDetails = null;
let vfConnectionMode = "single";
let vfProviderOpenRequest = 0;
let vfxModelTestResults = {};
let vfxTestingModelIds = new Set();
let vfxSelectedConnIds = new Set();
let vfxOneByOneRunning = false;
let vfxConnTestStatus = {};

// NotebookLM Integration State
let vfSelectedEngine = "notebooklm";
let vfSelectedFormat = "auto";
let vfNlmAuthStatus = (() => {
  try {
    const cached = localStorage.getItem("vf_nlm_auth_cache");
    if (cached) {
      const parsed = JSON.parse(cached);
      if (parsed && typeof parsed === "object") return parsed;
    }
  } catch (_) {}
  return { authenticated: false, status: "unauthenticated", email: null, profile: "video-flow-experiment" };
})();

// Auto-hydrate NotebookLM auth state on load
if (typeof window !== "undefined") {
  const hydrateImmediate = () => {
    try {
      if (typeof renderNotebookLMAuthStatus === "function" && vfNlmAuthStatus && vfNlmAuthStatus.authenticated) {
        renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
      }
    } catch (_) {}
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydrateImmediate);
  } else {
    hydrateImmediate();
  }
  setTimeout(() => {
    try {
      if (typeof checkNotebookLMAuth === "function") {
        checkNotebookLMAuth(false);
      }
    } catch (_) {}
  }, 150);

  // Auto-refresh NotebookLM status whenever user returns to the app (e.g. laptop lid opened or window focused)
  try {
    window.addEventListener("focus", () => {
      try {
        if (typeof checkNotebookLMAuth === "function") checkNotebookLMAuth(false);
      } catch (_) {}
    });
    document.addEventListener("visibilitychange", () => {
      try {
        if (document.visibilityState === "visible" && typeof checkNotebookLMAuth === "function") {
          checkNotebookLMAuth(false);
        }
      } catch (_) {}
    });
    // Background periodic health poll every 60s
    setInterval(() => {
      try {
        if (typeof checkNotebookLMAuth === "function") checkNotebookLMAuth(false);
      } catch (_) {}
    }, 60000);
  } catch (_) {}
}

let vfNlmAuthPollTimer = null;
function clearNlmAuthPollTimer() {
  if (vfNlmAuthPollTimer) {
    try { clearTimeout(vfNlmAuthPollTimer); } catch (_) {}
    try { clearInterval(vfNlmAuthPollTimer); } catch (_) {}
    vfNlmAuthPollTimer = null;
  }
}
let vfLiveTimerInterval = null;
let vfLiveTimerStartTime = null;
let vfAnalyzeSourceDebounceTimer = null;
let vfCurrentDocStats = {
  wordCount: 0,
  charCount: 0,
  pageCount: 0,
  sectionCount: 0,
  targetSeconds: 90,
  targetFormatted: "1m 30s",
  briefSeconds: 60,
  shortSeconds: 75,
  explainerSeconds: 120,
  cinematicSeconds: 150,
  resolvedFormat: "brief",
  densityScore: 1.0,
  contentValueRating: "standard",
  conceptCount: 0,
  effectiveWordCount: 0,
  redundancyScore: 0.0,
  substantiveConcepts: [],
};

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

// The model picker is shared by Video Flow and the Audio Flow summary
// selector, so it must be able to hydrate the catalog on its own — not only
// after the Video Flow page happened to load it.
async function vfEnsureCatalog() {
  if (vfCatalogLoaded) return true;
  try {
    const data = await safeFetchJson("/api/video-flow/catalog");
    if (!data || data.error || data.success === false) return false;
    vfCatalog = data;
    vfCatalogLoaded = true;
    return true;
  } catch {
    return false;
  }
}

function isAuthError(videoOrErr) {
  if (!videoOrErr) return false;
  // NOTE: deliberately does NOT inspect `stage` (every NotebookLM job passes
  // through an "auth_check" stage) and does not match a bare "auth" substring —
  // otherwise every unrelated failure renders as "Authentication Expired".
  const code = String(videoOrErr.error_code || videoOrErr.code || "").toLowerCase();
  const err = String(videoOrErr.error || videoOrErr.message || "").toLowerCase();
  return (
    code === "auth_expired" ||
    code === "unauthenticated" ||
    err.includes("auth_expired") ||
    err.includes("authentication expired") ||
    err.includes("auth expired") ||
    err.includes("not authenticated") ||
    err.includes("unauthenticated") ||
    err.includes("authentication failed") ||
    err.includes("missing required authentication") ||
    err.includes("missing required cookies") ||
    err.includes("google authentication expired") ||
    err.includes("login expired")
  );
}

function renderNotebookLMAuthStatus(authStatus, showToast = false) {
  const badge = document.getElementById("vf-nlm-status-badge");
  const dot = document.getElementById("vf-nlm-status-dot");
  const text = document.getElementById("vf-nlm-status-text");
  const loginBtn = document.getElementById("vf-nlm-login-btn");
  const loginLabel = document.getElementById("vf-nlm-login-label");
  const disconnectBtn = document.getElementById("vf-nlm-disconnect-btn");
  const desc = document.getElementById("vf-nlm-account-desc");

  if (!badge || !dot || !text) return;

  badge.className = "vf-nlm-status-badge";
  dot.className = "status-dot-indicator";

  const email = (authStatus && authStatus.email) || "";
  const isAuth = Boolean(authStatus && authStatus.authenticated && email && authStatus.status !== "unauthenticated");
  const cookieHealth = authStatus && authStatus.cookie_health;

  if (isAuth) {
    if (cookieHealth && cookieHealth.status === "expiring_soon") {
      badge.classList.add("expiring");
      dot.classList.add("expiring");
      text.textContent = `Expiring Soon: ${email}`;
      if (desc) desc.textContent = `${cookieHealth.message || "Session expiring soon"} — Click 'Sync Browser' to refresh cookies seamlessly.`;
    } else {
      badge.classList.add("connected");
      dot.classList.add("connected");
      text.textContent = `Connected: ${email}`;
      if (desc) desc.textContent = `Google Account connected (${email}) · Ready for 1-click cloud AI video generation.`;
    }
    if (loginBtn) {
      loginBtn.className = "btn-secondary vf-nlm-switch-btn";
      loginBtn.title = "Switch or change your Google account";
      loginBtn.onclick = function () { startNotebookLMAuth(true); };
    }
    if (loginLabel) loginLabel.textContent = "Switch Google Account";
    if (disconnectBtn) {
      disconnectBtn.classList.remove("hidden");
      disconnectBtn.disabled = false;
    }
    if (showToast) vfToast(`Google NotebookLM is connected (${email})`);
  } else if (authStatus && (!authStatus.available || authStatus.status === "dependency_missing")) {
    badge.classList.add("disconnected");
    dot.classList.add("disconnected");
    text.textContent = "CLI Not Configured";
    if (desc) desc.textContent = "NotebookLM CLI is not installed or configured on this machine.";
    if (loginBtn) {
      loginBtn.className = "btn-secondary vf-nlm-switch-btn";
      loginBtn.title = "Configure NotebookLM CLI";
      loginBtn.onclick = function () { startNotebookLMAuth(false); };
    }
    if (loginLabel) loginLabel.textContent = "Configure CLI";
    if (disconnectBtn) disconnectBtn.classList.add("hidden");
    if (showToast) vfToast("NotebookLM CLI was not found.", true);
  } else {
    badge.classList.add("disconnected");
    dot.classList.add("disconnected");
    if (cookieHealth && cookieHealth.status === "expired") {
      text.textContent = "Session Expired";
      if (desc) desc.textContent = "Your Google session has expired. Click 'Sync Browser' to reconnect seamlessly.";
    } else {
      text.textContent = "Disconnected";
      if (desc) desc.textContent = "Connect your Google account to enable cloud video rendering with NotebookLM.";
    }
    if (loginBtn) {
      loginBtn.className = "btn-primary vf-nlm-login-btn";
      loginBtn.title = "Log in to your NotebookLM account";
      loginBtn.onclick = function () { startNotebookLMAuth(false); };
    }
    if (loginLabel) loginLabel.textContent = "Log in to NotebookLM";
    if (disconnectBtn) disconnectBtn.classList.add("hidden");
    if (showToast) vfToast("NotebookLM is disconnected.", true);
  }
}

async function checkNotebookLMAuth(showToast = false) {
  const checkBtn = document.getElementById("vf-nlm-check-btn");
  const checkLabel = document.getElementById("vf-nlm-check-label");
  const checkIcon = document.getElementById("vf-nlm-check-icon");
  const badge = document.getElementById("vf-nlm-status-badge");
  const dot = document.getElementById("vf-nlm-status-dot");
  const statusText = document.getElementById("vf-nlm-status-text");
  const desc = document.getElementById("vf-nlm-account-desc");

  // If user is currently not logged in / disconnected, do not run online verification
  if (showToast && (!vfNlmAuthStatus.authenticated || !vfNlmAuthStatus.email)) {
    vfToast("No Google account connected. Please click 'Log in to NotebookLM' to get started.", true);
    renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
    return vfNlmAuthStatus;
  }

  let progressTimer = null;

  if (showToast) {
    if (checkBtn) checkBtn.disabled = true;
    if (checkLabel) checkLabel.textContent = "Verifying…";
    if (checkIcon) checkIcon.classList.add("spin");
    if (badge) badge.className = "vf-nlm-status-badge verifying";
    if (dot) dot.className = "status-dot-indicator verifying";
    if (statusText) statusText.textContent = "Verifying…";
    if (desc) desc.textContent = "Connecting to Google servers to verify your NotebookLM session…";

    let step = 0;
    progressTimer = setInterval(() => {
      step++;
      if (step === 1 && desc) {
        desc.textContent = "Validating session tokens with Google…";
      } else if (step === 2 && desc) {
        desc.textContent = "Checking cloud model access…";
      }
    }, 2000);
  }

  try {
    const query = showToast ? "?verify=1&force=1" : "";
    const data = await safeFetchJson(`/api/video-flow/notebooklm/status${query}`);
    if (progressTimer) clearInterval(progressTimer);
    if (!data || data.error) throw new Error(data?.error || "Failed to check status");

    const isExplicitDisc = Boolean(data.details?.disconnected);
    const backendAuth = Boolean(data.authenticated && !isExplicitDisc && data.status !== "unauthenticated");
    let email = data.email || data.account_email || (data.details?.account?.email) || "";
    if (!email && backendAuth && vfNlmAuthStatus.email && !isExplicitDisc) {
      email = vfNlmAuthStatus.email;
    }
    if (isExplicitDisc || !backendAuth || !email) {
      email = null;
    }
    const isAuth = Boolean(backendAuth && email);

    vfNlmAuthStatus = {
      authenticated: isAuth,
      status: isAuth ? "ok" : "unauthenticated",
      email: email,
      profile: data.profile || vfNlmAuthStatus.profile || "video-flow-experiment",
      available: data.available !== false,
      cookie_health: isAuth ? (data.cookie_health || null) : null,
      online_verified: isAuth ? data.online_verified : false,
    };

    if (vfNlmAuthStatus.authenticated && vfNlmAuthStatus.email) {
      try {
        localStorage.setItem("vf_nlm_auth_cache", JSON.stringify(vfNlmAuthStatus));
      } catch (_) {}
    } else if (isExplicitDisc) {
      try {
        localStorage.removeItem("vf_nlm_auth_cache");
      } catch (_) {}
    }

    if (vfNlmAuthStatus.authenticated && vfNlmAuthPollTimer) {
      clearNlmAuthPollTimer();
      const loginBtn = document.getElementById("vf-nlm-login-btn");
      if (loginBtn) loginBtn.disabled = false;
      const disconnectBtn = document.getElementById("vf-nlm-disconnect-btn");
      if (disconnectBtn) disconnectBtn.disabled = false;
    }

    renderNotebookLMAuthStatus(vfNlmAuthStatus, showToast);
    return vfNlmAuthStatus;
  } catch (err) {
    if (progressTimer) clearInterval(progressTimer);
    if (showToast) {
      vfToast("Verification probe completed — keeping current session state.", false);
    }
    renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
    return vfNlmAuthStatus;
  } finally {
    if (progressTimer) clearInterval(progressTimer);
    if (checkIcon) checkIcon.classList.remove("spin");
    if (checkLabel) checkLabel.textContent = "Verify";
    if (checkBtn) checkBtn.disabled = false;
  }
}

async function syncNotebookLMBrowser() {
  const syncBtn = document.getElementById("vf-nlm-sync-btn");
  const syncLabel = document.getElementById("vf-nlm-sync-label");
  const syncIcon = document.getElementById("vf-nlm-sync-icon");
  const badge = document.getElementById("vf-nlm-status-badge");
  const dot = document.getElementById("vf-nlm-status-dot");
  const statusText = document.getElementById("vf-nlm-status-text");
  const desc = document.getElementById("vf-nlm-account-desc");

  if (syncIcon) {
    syncIcon.textContent = "⏳";
    syncIcon.classList.add("spin");
  }
  if (syncLabel) syncLabel.textContent = "Syncing…";
  if (syncBtn) syncBtn.disabled = true;

  if (badge) badge.className = "vf-nlm-status-badge polling";
  if (dot) dot.className = "status-dot-indicator polling";
  if (statusText) statusText.textContent = "Syncing Browser…";
  if (desc) desc.textContent = "Syncing session cookies from your browser profile…";

  let step = 0;
  const progressTimer = setInterval(() => {
    step++;
    if (step === 1 && desc) {
      desc.textContent = "Refreshing Google session tokens…";
    } else if (step === 2 && desc) {
      desc.textContent = "Finalizing session cookies with Google…";
    }
  }, 2000);

  try {
    const activeProfile = vfNlmAuthStatus.profile || "video-flow-experiment";
    const currentEmail = vfNlmAuthStatus.email || "";
    const data = await safeFetchJson("/api/video-flow/notebooklm/auth/sync-browser", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: activeProfile, email: currentEmail }),
    });
    if (progressTimer) clearInterval(progressTimer);
    if (data && data.success) {
      const emailSynced = data.email || currentEmail || "";
      if (emailSynced) {
        vfNlmAuthStatus.email = emailSynced;
        vfNlmAuthStatus.authenticated = true;
        vfNlmAuthStatus.status = "ok";
        try {
          localStorage.setItem("vf_nlm_auth_cache", JSON.stringify(vfNlmAuthStatus));
        } catch (_) {}
      }
      vfToast(emailSynced ? `Synced session for ${emailSynced} successfully!` : `Synced ${data.cookies_count || ""} NotebookLM session cookies successfully!`);
      await checkNotebookLMAuth(false);
    } else {
      vfToast(data?.error || "Could not sync cookies directly. Try 'Log in to NotebookLM'.", true);
      renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
    }
  } catch (err) {
    if (progressTimer) clearInterval(progressTimer);
    vfToast(`Browser sync failed: ${err.message || err}`, true);
    renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
  } finally {
    if (progressTimer) clearInterval(progressTimer);
    if (syncIcon) {
      syncIcon.textContent = "🔄";
      syncIcon.classList.remove("spin");
    }
    if (syncLabel) syncLabel.textContent = "Sync Browser";
    if (syncBtn) syncBtn.disabled = false;
  }
}

async function startNotebookLMAuth(switchAccount = false) {
  clearNlmAuthPollTimer();

  const previousEmail = (vfNlmAuthStatus && vfNlmAuthStatus.email) || "";

  if (switchAccount) {
    vfNlmAuthStatus.email = null;
    vfNlmAuthStatus.authenticated = false;
    vfNlmAuthStatus.status = "unauthenticated";
    try {
      localStorage.removeItem("vf_nlm_auth_cache");
    } catch (_) {}
    renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
  }

  // If not switching accounts, first check if browser sync can seamlessly authenticate
  if (!switchAccount) {
    try {
      const syncCheck = await safeFetchJson("/api/video-flow/notebooklm/auth/sync-browser", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: vfNlmAuthStatus.profile || "video-flow-experiment", email: previousEmail || "" }),
      });
      if (syncCheck && syncCheck.success) {
        await checkNotebookLMAuth(false);
        vfToast(`Connected to ${syncCheck.email || "Google account"} from browser!`);
        return;
      }
    } catch (_) {}
  }

  const loginBtn = document.getElementById("vf-nlm-login-btn");
  const loginLabel = document.getElementById("vf-nlm-login-label");
  const disconnectBtn = document.getElementById("vf-nlm-disconnect-btn");
  const badge = document.getElementById("vf-nlm-status-badge");
  const dot = document.getElementById("vf-nlm-status-dot");
  const text = document.getElementById("vf-nlm-status-text");

  if (loginLabel) {
    loginLabel.textContent = switchAccount ? "Opening Account Chooser…" : "Opening NotebookLM sign-in window…";
  }
  if (loginBtn) loginBtn.disabled = true;
  if (disconnectBtn) disconnectBtn.disabled = true;
  if (badge) badge.className = "vf-nlm-status-badge polling";
  if (dot) dot.className = "status-dot-indicator polling";
  if (text) text.textContent = switchAccount ? "Choose account in browser…" : "Waiting for sign-in in browser…";

  try {
    const activeProfile = vfNlmAuthStatus.profile || "video-flow-experiment";
    const data = await safeFetchJson("/api/video-flow/notebooklm/auth/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile: activeProfile,
        mode: "playwright",
        browser: "chrome",
        switch_account: Boolean(switchAccount),
        direct: true,
      }),
    });
    if (!data || !data.success) {
      throw new Error(data?.error || "Could not launch Google authentication.");
    }

    vfToast(
      data.message ||
        (switchAccount
          ? "Google account chooser opened in your default browser. Select an account to switch."
          : "Google sign-in opened in your default browser. Select your account to sign in.")
    );

    let attempts = 0;
    const maxAttempts = 250; // 50 x 600ms (30s) + 50 x 1200ms (60s) + 150 x 2000ms (300s) = ~6.5 minutes of adaptive patience
    const pollTick = async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearNlmAuthPollTimer();
        if (loginBtn) loginBtn.disabled = false;
        if (disconnectBtn) disconnectBtn.disabled = false;
        await checkNotebookLMAuth(false);
        vfToast("Sign-in timed out. Please try again.", true);
        return;
      }

      try {
        let stateData = null;
        try {
          stateData = await safeFetchJson("/api/video-flow/notebooklm/auth/state");
        } catch (_) {}

        const login = stateData && stateData.login ? stateData.login : null;
        if (login && login.note && text) {
          text.textContent = login.note;
        }

        // Check if login failed
        if (login && login.running === false && login.started_at && !login.success && login.error) {
          clearNlmAuthPollTimer();
          if (loginBtn) loginBtn.disabled = false;
          if (disconnectBtn) disconnectBtn.disabled = false;
          await checkNotebookLMAuth(false);
          vfToast(login.error || "Sign-in did not complete. Please try again.", true);
          return;
        }

        // Check if login watcher reported success
        if (login && login.running === false && login.success === true) {
          clearNlmAuthPollTimer();
          if (loginBtn) loginBtn.disabled = false;
          if (disconnectBtn) disconnectBtn.disabled = false;

          let newEmail = login.email || "";
          if (!newEmail && login.note && login.note.startsWith("Signed in as ")) {
            newEmail = login.note.replace("Signed in as ", "").trim();
          }
          if (newEmail && newEmail !== "your Google account") {
            vfNlmAuthStatus.email = newEmail;
            vfNlmAuthStatus.authenticated = true;
            vfNlmAuthStatus.status = "ok";
            try {
              localStorage.setItem("vf_nlm_auth_cache", JSON.stringify(vfNlmAuthStatus));
            } catch (_) {}
            renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
          }

          const finalStatus = await checkNotebookLMAuth(false);
          const userStr = finalStatus?.email || newEmail || (login.note ? login.note.replace("Signed in as ", "") : "") || "Google account";
          renderNotebookLMAuthStatus(finalStatus, false);
          vfToast(
            switchAccount
              ? `Switched to ${userStr} successfully!`
              : `Connected to ${userStr} successfully!`
          );
          return;
        }

        // Secondary check via status endpoint
        const statusData = await safeFetchJson("/api/video-flow/notebooklm/status");
        if (statusData && statusData.authenticated && statusData.email) {
          if (switchAccount && previousEmail && statusData.email.toLowerCase() === previousEmail.toLowerCase()) {
            // Still reporting the old account while transitioning, keep waiting
          } else {
            clearNlmAuthPollTimer();
            if (loginBtn) loginBtn.disabled = false;
            if (disconnectBtn) disconnectBtn.disabled = false;
            vfNlmAuthStatus.email = statusData.email;
            vfNlmAuthStatus.authenticated = true;
            vfNlmAuthStatus.status = "ok";
            try {
              localStorage.setItem("vf_nlm_auth_cache", JSON.stringify(vfNlmAuthStatus));
            } catch (_) {}
            renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
            const finalStatus = await checkNotebookLMAuth(false);
            const userStr = finalStatus?.email || statusData.email || "Google account";
            renderNotebookLMAuthStatus(finalStatus, false);
            vfToast(
              switchAccount
                ? `Switched to ${userStr} successfully!`
                : `Connected to ${userStr} successfully!`
            );
            return;
          }
        }
      } catch (_) {
        // network polling jitter
      }

      if (vfNlmAuthPollTimer !== null) {
        const delay = attempts < 50 ? 600 : (attempts < 100 ? 1200 : 2000);
        vfNlmAuthPollTimer = setTimeout(pollTick, delay);
      }
    };

    vfNlmAuthPollTimer = setTimeout(pollTick, 600);
  } catch (err) {
    clearNlmAuthPollTimer();
    if (loginBtn) loginBtn.disabled = false;
    if (disconnectBtn) disconnectBtn.disabled = false;
    vfToast(err.message || "Failed to start Google sign-in.", true);
    checkNotebookLMAuth(false);
  }
}

async function disconnectNotebookLM() {
  clearNlmAuthPollTimer();

  const disconnectBtn = document.getElementById("vf-nlm-disconnect-btn");
  const loginBtn = document.getElementById("vf-nlm-login-btn");
  if (disconnectBtn) disconnectBtn.disabled = true;
  if (loginBtn) loginBtn.disabled = true;

  try {
    const activeProfile = vfNlmAuthStatus.profile || "video-flow-experiment";
    await safeFetchJson("/api/video-flow/notebooklm/auth/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: activeProfile }),
    });

    try {
      localStorage.removeItem("vf_nlm_auth_cache");
    } catch (_) {}

    vfNlmAuthStatus = {
      authenticated: false,
      status: "unauthenticated",
      email: null,
      profile: activeProfile,
      available: true,
    };

    renderNotebookLMAuthStatus(vfNlmAuthStatus, false);
    vfToast("Google NotebookLM disconnected successfully.");
  } catch (err) {
    vfToast("Failed to disconnect NotebookLM: " + (err.message || err), true);
  } finally {
    if (disconnectBtn) disconnectBtn.disabled = false;
    if (loginBtn) loginBtn.disabled = false;
  }
}

const VF_PERMANENT_CONFIRMATION = "DELETE_VIDEO_FROM_THIS_PC";
const vfProviderIcons = {
  claude_code: "✺", antigravity: "A", openai_codex: "◎",
  vertex_ai: "V", gemini: "✦", openrouter: "↔", nvidia_nim: "N",
  opencode_zen: "Z", anthropic: "A", openai: "◎", groq: "G",
  together: "T", cloudflare: "☁", ollama: "◉", lm_studio: "LM",
  llama_cpp: "L", local: "💻",
}

function vfJsArg(value) {
  var s = String(value);
  if (/^\d+$/.test(s)) return s;
  return "'" + s.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
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
    const [historyData, catalogData] = await Promise.all([
      safeFetchJson("/api/video-flow/history"),
      safeFetchJson("/api/video-flow/catalog"),
    ]);
    if (!historyData || historyData.error || !catalogData || catalogData.error) {
      throw new Error((historyData && historyData.error) || (catalogData && catalogData.error) || "Video Flow backend is unavailable.");
    }
    vfCatalog = catalogData;
    vfCatalogLoaded = true;
    vfVideos = historyData.videos || [];
    renderVideoHistory();
    renderVideoCatalog();
    if (typeof loadCustomProviders === "function") loadCustomProviders();
    checkNotebookLMAuth(false);
    if (typeof vfGoogleLoadAccount === "function") vfGoogleLoadAccount();
    const activeVideo = vfVideos.find(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status));
    // Never resurrect old failures on page load: the stepper is only for a
    // generation monitored in this session. Past failures stay visible on
    // their history cards with the real error message.
    if (activeVideo) {
      vfActiveVideoId = activeVideo.id;
      vfStartLiveStopwatch(activeVideo);
      updateGenerationStepper(activeVideo);
    } else {
      vfActiveVideoId = null;
      updateGenerationStepper(null);
    }
    scheduleVideoFlowPolling();
    scheduleSourceAnalysis(0);
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

function vfFormatTimingSeconds(sec) {
  if (sec === null || sec === undefined || sec === "") return "";
  if (typeof sec === "string") {
    const trimmed = sec.trim();
    if (trimmed.includes("m") || trimmed.includes("s")) return trimmed;
    const parsed = Number.parseFloat(trimmed);
    if (Number.isNaN(parsed)) return trimmed;
    sec = parsed;
  }
  const total = Math.round(Number(sec));
  if (Number.isNaN(total) || total < 0) return "";
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  if (minutes > 0) {
    return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
  }
  return `${remainder}s`;
}

function vfExtractTimings(video) {
  if (!video) return null;
  let timings = video.timings || video.meta?.timings || video.meta?.timing || null;
  if (!timings && typeof video.meta === "string") {
    try {
      const parsed = JSON.parse(video.meta);
      timings = parsed.timings || parsed.timing;
    } catch (_) {}
  }
  if (!timings && video.provenance?.timings) {
    timings = video.provenance.timings;
  }
  if (!timings) return null;
  if (typeof timings === "string") {
    try {
      timings = JSON.parse(timings);
    } catch (_) {
      return { total: timings };
    }
  }
  if (typeof timings !== "object" || timings === null) return null;
  return timings;
}

function vfRenderTimingBadge(video) {
  const timings = vfExtractTimings(video);
  if (!timings) return "";

  const uploadRaw = timings.upload ?? timings.upload_sec ?? timings.upload_seconds ?? timings.uploading ?? timings.source_upload;
  const cloudRaw = timings.cloud_ai ?? timings.cloudAi ?? timings.cloud_ai_sec ?? timings.cloud ?? timings.ai ?? timings.cloud_seconds ?? timings.cloud_sec ?? timings.generation ?? timings.video_poll;
  const downloadRaw = timings.download ?? timings.download_sec ?? timings.download_seconds ?? timings.downloading;

  let totalRaw = timings.total ?? timings.total_sec ?? timings.total_seconds ?? timings.duration ?? timings.elapsed;
  if (totalRaw === undefined || totalRaw === null) {
    const u = Number(uploadRaw) || 0;
    const c = Number(cloudRaw) || 0;
    const d = Number(downloadRaw) || 0;
    if (u + c + d > 0) {
      totalRaw = u + c + d;
    }
  }

  const totalStr = vfFormatTimingSeconds(totalRaw);
  const uploadStr = vfFormatTimingSeconds(uploadRaw);
  const cloudStr = vfFormatTimingSeconds(cloudRaw);
  const downloadStr = vfFormatTimingSeconds(downloadRaw);

  const breakdownParts = [];
  if (uploadStr) breakdownParts.push(`Upload: ${uploadStr}`);
  if (cloudStr) breakdownParts.push(`Cloud AI: ${cloudStr}`);
  if (downloadStr) breakdownParts.push(`Download: ${downloadStr}`);

  if (breakdownParts.length === 0) {
    for (const [key, val] of Object.entries(timings)) {
      if (["total", "total_sec", "total_seconds", "duration", "elapsed", "raw"].includes(key)) continue;
      const formattedVal = vfFormatTimingSeconds(val);
      if (formattedVal) {
        const label = key.replace(/_/g, " ").replace(/\b\w/g, ch => ch.toUpperCase());
        breakdownParts.push(`${label}: ${formattedVal}`);
      }
    }
  }

  if (!totalStr && breakdownParts.length === 0) {
    if (timings.raw) {
      return `<div class="vf-timing-pill" title="Generation speed breakdown"><span class="vf-timing-bolt">⚡</span> ${vfEscape(timings.raw)}</div>`;
    }
    return "";
  }

  const breakdownText = breakdownParts.length ? ` (${breakdownParts.join(" · ")})` : "";
  const displayTotal = totalStr || "Fast";

  return `<div class="vf-timing-pill" title="Generation speed breakdown"><span class="vf-timing-bolt">⚡</span> <strong class="vf-timing-total">${vfEscape(displayTotal)}</strong>${breakdownParts.length ? `<span class="vf-timing-breakdown">${vfEscape(breakdownText)}</span>` : ""}</div>`;
}

function vfFormatStopwatch(totalSeconds) {
  const mins = Math.floor(totalSeconds / 60);
  const secs = String(Math.floor(totalSeconds % 60)).padStart(2, "0");
  return `${mins}:${secs}`;
}

function vfGetStopwatchStage(activeVideo, fallbackStage) {
  if (activeVideo && activeVideo.stage) {
    const s = String(activeVideo.stage).trim();
    const lower = s.toLowerCase();
    if (lower.includes("cloud") || lower.includes("overview") || lower.includes("video_poll") || lower.includes("generat")) {
      return "Generating in Cloud AI...";
    }
    if (lower.includes("upload") || lower.includes("source")) {
      return "Uploading source...";
    }
    if (lower.includes("download") || lower.includes("normaliz")) {
      return "Downloading MP4...";
    }
    if (lower.includes("auth")) {
      return "Verifying authentication...";
    }
    if (lower.includes("notebook")) {
      return "Creating notebook...";
    }
    return s;
  }
  return fallbackStage || "Generating in Cloud AI...";
}

function vfRenderCardLiveTimer(video) {
  const createdSec = Number(video.created_at);
  const createdMs = (!Number.isNaN(createdSec) && createdSec > 0)
    ? (createdSec > 1e11 ? createdSec : createdSec * 1000)
    : (vfLiveTimerStartTime || Date.now());
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - (vfLiveTimerStartTime || createdMs)) / 1000));
  const elapsedStr = vfFormatStopwatch(elapsedSeconds);
  const stageLabel = vfGetStopwatchStage(video, "Generating in Cloud AI...");
  return `<div class="vf-live-timer vf-timing-pill vf-card-live-timer" title="Live elapsed time">⏱️ ${elapsedStr} elapsed (${vfEscape(stageLabel)})</div>`;
}

function vfUpdateLiveTimer(activeVideo = null, fallbackStage = null) {
  if (!vfLiveTimerStartTime) {
    vfLiveTimerStartTime = Date.now();
  }

  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - vfLiveTimerStartTime) / 1000));
  const elapsedStr = vfFormatStopwatch(elapsedSeconds);
  const stageLabel = vfGetStopwatchStage(activeVideo, fallbackStage);
  const fullText = `⏱️ ${elapsedStr} elapsed (${stageLabel})`;

  let timerEl = document.getElementById("vf-live-timer");
  const stepper = document.getElementById("vf-generation-stepper");
  if (!timerEl && stepper) {
    timerEl = document.createElement("div");
    timerEl.id = "vf-live-timer";
    timerEl.className = "vf-live-timer";
    const header = stepper.querySelector(".vf-stepper-header");
    if (header && header.nextSibling) {
      stepper.insertBefore(timerEl, header.nextSibling);
    } else {
      stepper.appendChild(timerEl);
    }
  }

  if (timerEl) {
    timerEl.style.display = "inline-flex";
    timerEl.innerHTML = `<span class="vf-live-timer-icon">⏱️</span> <span class="vf-live-timer-time">${elapsedStr} elapsed</span> <span class="vf-live-timer-stage">(${vfEscape(stageLabel)})</span>`;
    timerEl.setAttribute("data-elapsed-sec", elapsedSeconds);
    timerEl.setAttribute("title", fullText);
  }

  const cardLiveTimers = document.querySelectorAll(".vf-card-live-timer");
  cardLiveTimers.forEach(cardTimer => {
    cardTimer.textContent = fullText;
  });
}

function vfStartLiveStopwatch(activeVideo = null, fallbackStage = "Generating in Cloud AI...") {
  if (!vfLiveTimerStartTime) {
    if (activeVideo && activeVideo.created_at) {
      const createdVal = Number(activeVideo.created_at);
      if (!Number.isNaN(createdVal) && createdVal > 0) {
        const createdMs = createdVal > 1e11 ? createdVal : createdVal * 1000;
        if (Date.now() - createdMs < 86400000 && Date.now() >= createdMs) {
          vfLiveTimerStartTime = createdMs;
        } else {
          vfLiveTimerStartTime = Date.now();
        }
      } else {
        vfLiveTimerStartTime = Date.now();
      }
    } else {
      vfLiveTimerStartTime = Date.now();
    }
  }

  vfUpdateLiveTimer(activeVideo, fallbackStage);

  if (!vfLiveTimerInterval) {
    vfLiveTimerInterval = setInterval(() => {
      const active = vfVideos.find(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status));
      const stepper = document.getElementById("vf-generation-stepper");
      const isStepperVisible = stepper && !stepper.classList.contains("hidden");
      if (!active && !isStepperVisible) {
        vfStopLiveStopwatch();
        return;
      }
      vfUpdateLiveTimer(active);
    }, 1000);
  }
}

function vfStopLiveStopwatch() {
  if (vfLiveTimerInterval) {
    clearInterval(vfLiveTimerInterval);
    vfLiveTimerInterval = null;
  }
  vfLiveTimerStartTime = null;
  const timerEl = document.getElementById("vf-live-timer");
  if (timerEl) {
    timerEl.style.display = "none";
  }
}

/**
 * Legacy history renderer (pre-library markup). Kept as a defensive fallback
 * for the moment the new #vf-library-grid container is absent (mid-rewrite
 * safety) so history never silently disappears.
 */
function vfRenderLegacyHistory() {
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
    const authFailed = failed && isAuthError(video);
    const isNlm = video.provider === "notebooklm" || video.engine_version === "notebooklm" || String(video.engine_version || "").toLowerCase().includes("notebook");
    const mode = isNlm
      ? `NotebookLM · ${video.format ? (video.format.charAt(0).toUpperCase() + video.format.slice(1)) : "Brief"}`
      : (video.mode === "full" ? "Full explanation" : video.mode === "spatial_3d" ? "Spatial 3D" : "Summary");
    const engineVersion = isNlm ? "Google NotebookLM (HD)" : (video.engine_version || "Visual V2.1");
    const error = failed && video.error ? ` title="${vfEscape(video.error)}"` : "";
    const fallbackNotice = (complete && video.fallback_reason)
      ? `<div class="vf-error-notice" style="font-size:11px;color:#b45309;margin-top:6px;" title="${vfEscape(video.fallback_error || '')}">⚠ ${video.fallback_requested_engine === "notebooklm" ? "NotebookLM login expired" : "Requested engine unavailable"} — rendered with the local engine instead. ${video.fallback_requested_engine === "notebooklm" ? `<a href="#" onclick="startNotebookLMAuth(); return false;" style="color:#b45309;font-weight:600;">Sign in</a> to use NotebookLM.` : ""}</div>`
      : "";
    return `
      <article class="vf-video-card ${isNlm ? 'vf-card-nlm' : ''} ${authFailed ? 'vf-card-auth-error' : ''}" data-video-id="${vfEscape(video.id)}">
        <div class="vf-video-thumb" ${complete ? `onclick="previewVideoFlow('${vfEscape(video.id)}')"` : ""}>
          ${complete ? `<img class="vf-thumb-img" src="/api/video-flow/videos/thumb?id=${vfEscape(video.id)}" alt="" loading="lazy" onerror="this.remove()">` : ""}
          <div class="vf-video-thumb-top">
            <span class="vf-mode-chip ${isNlm ? 'nlm-chip' : ''}">${mode}</span>
            <span class="vf-status-chip ${vfEscape(video.status)}"${error}>${authFailed ? "Auth Expired" : vfEscape(video.status)}</span>
          </div>
          <div class="vf-thumb-play">${complete ? '<svg class="lucide vf-ico" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"/></svg>' : (authFailed ? "⚠️" : (failed ? "!" : "•••"))}</div>
          <div class="vf-status-row"><small>${vfEscape(video.stage || (complete ? "Ready" : (authFailed ? "Auth Expired" : (failed ? "Failed" : "Queued"))))}</small><small>${complete ? "100%" : `${Number(video.progress || 0)}%`}</small></div>
        </div>
        <div class="vf-video-body">
          <h3 title="${vfEscape(video.title || 'Untitled Video')}">${vfEscape(video.title || 'Untitled Video')}</h3>
          <div class="vf-video-meta"><span>${vfFormatDate(video.created_at)}</span><span>${vfFormatDuration(video.duration_sec)}</span><span>${vfEscape(engineVersion)}</span></div>
          ${fallbackNotice}
          ${authFailed ? `
            <div class="vf-auth-error-card" style="margin: 8px 0;">
              <div class="vf-auth-error-msg">
                <span class="vf-auth-error-icon">⚠️</span>
                <span>Google Authentication Expired</span>
              </div>
              <div class="vf-auth-error-actions">
                <button class="vf-btn-reauth" type="button" onclick="startNotebookLMAuth(true)">Switch Google Account</button>
                <button class="vf-btn-retry" type="button" onclick="retryVideoFlow('${vfEscape(video.id)}')">↻ 1-Click Retry</button>
              </div>
            </div>
          ` : (complete ? vfRenderTimingBadge(video) : (!failed ? vfRenderCardLiveTimer(video) : (failed && video.error ? `<div class="vf-error-notice" style="font-size:11px;color:#ef4444;margin-top:6px;">${vfEscape(video.error)}</div>` : "")))}
          ${!complete && !failed ? `<div class="vf-progress-track"><span style="width:${Math.max(0, Math.min(100, Number(video.progress || 0)))}%"></span></div>` : ""}
          <div class="vf-video-actions">
            ${complete ? `
              <button class="vf-icon-button" onclick="previewVideoFlow('${vfEscape(video.id)}')"><svg class="lucide vf-ico" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"/></svg> Play</button>
              <button type="button" class="vf-icon-button vf-download-btn" onclick="downloadVideoFlow('${vfEscape(video.id)}', this)" title="Download video">↓ Download</button>
              <button class="vf-icon-button" onclick="shareVideoFlow('${vfEscape(video.id)}')">↗ Share</button>
            ` : ""}
            ${failed && !authFailed ? `<button class="vf-icon-button" onclick="retryVideoFlow('${vfEscape(video.id)}')">↻ 1-Click Retry</button>` : ""}
            <button class="vf-icon-button danger" onclick="beginVideoDelete('${vfEscape(video.id)}')">⌫ Delete</button>
          </div>
        </div>
      </article>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// Your videos library (plan section 7). Client-side search/filter/sort over
// the already-loaded collection — no new API semantics, no server pagination,
// no writes to the saved statuses.
// ---------------------------------------------------------------------------

let vfLibraryQuery = "";
let vfLibraryFilter = "all";
let vfLibraryRenderPending = false;
let vfLibraryControlsWired = false;

function vfIsVideoTerminalStatus(video) {
  return vfIsVideoComplete(video) || ["failed", "cancelled"].includes(String(video.status || "").toLowerCase());
}

function vfLibraryBucket(video) {
  if (vfIsVideoComplete(video)) return "ready";
  const status = String(video.status || "").toLowerCase();
  if (status === "cancelled") return "cancelled";
  if (status === "failed") return "failed";
  return "in_progress";
}

function vfLibraryStatusLabel(video) {
  const bucket = vfLibraryBucket(video);
  if (bucket === "ready") return "Ready";
  if (bucket === "failed") return "Failed";
  if (bucket === "cancelled") return "Cancelled";
  return "In progress";
}

function vfVideoTimestampMs(video) {
  const raw = Number(video && (video.created_at ?? video.createdAt));
  if (!Number.isNaN(raw) && raw > 0) return raw > 1e11 ? raw : raw * 1000;
  return 0;
}

/** Newest first using the real created_at timestamps. */
function vfSortVideosNewestFirst(videos) {
  return videos.slice().sort((a, b) => vfVideoTimestampMs(b) - vfVideoTimestampMs(a));
}

function vfVideoMatchesLibrary(video) {
  const bucket = vfLibraryBucket(video);
  if (vfLibraryFilter === "ready" && bucket !== "ready") return false;
  if (vfLibraryFilter === "in_progress" && bucket !== "in_progress") return false;
  if (vfLibraryFilter === "needs_attention" && bucket !== "failed") return false;
  if (vfLibraryFilter === "cancelled" && bucket !== "cancelled") return false;
  const query = vfLibraryQuery.trim().toLowerCase();
  if (query) {
    const haystack = [
      video.title, video.stage, vfLibraryStatusLabel(video),
      video.format, video.mode, video.engine_version,
    ].filter(Boolean).join(" ").toLowerCase();
    if (!haystack.includes(query)) return false;
  }
  return true;
}

/** Concise, safe failure reason for the card face; full detail stays in Details. */
function vfConciseError(video) {
  const raw = cleanErrorMessage((video && (video.error || video.message)) || "");
  const text = String(raw).replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > 180 ? text.slice(0, 177) + "…" : text;
}

function vfFormatKnownDuration(seconds) {
  const total = Math.round(Number(seconds));
  if (!Number.isFinite(total) || total <= 0) return "";
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function vfUpdateLibraryBadge(count) {
  const tab = document.getElementById("vf-tab-library");
  if (!tab) return;
  let badge = tab.querySelector("[data-vf-library-count]");
  if (!badge) badge = tab.querySelector(".flow-tab-count");
  if (badge) {
    badge.textContent = count > 0 ? String(count) : "";
    badge.hidden = !(count > 0);
    badge.classList.toggle("hidden", !(count > 0));
  }
  tab.setAttribute("aria-label", `Your videos (${count})`);
}

function vfUpdateLibraryFilterCounts() {
  const filters = document.getElementById("vf-library-filters");
  if (!filters) return;
  const totals = { all: vfVideos.length, ready: 0, in_progress: 0, needs_attention: 0, cancelled: 0 };
  for (const video of vfVideos) {
    const bucket = vfLibraryBucket(video);
    if (bucket === "ready") totals.ready += 1;
    else if (bucket === "failed") totals.needs_attention += 1;
    else if (bucket === "cancelled") totals.cancelled += 1;
    else totals.in_progress += 1;
  }
  filters.querySelectorAll("[data-vf-filter]").forEach(button => {
    const key = button.getAttribute("data-vf-filter");
    if (!button.dataset.vfLabel) button.dataset.vfLabel = (button.textContent || "").trim() || key;
    const label = button.dataset.vfLabel;
    const n = totals[key];
    button.textContent = Number.isFinite(n) ? `${label} (${n})` : label;
    button.setAttribute("aria-pressed", String(key === vfLibraryFilter));
  });
}

function vfSetLibraryFilter(nextFilter) {
  vfLibraryFilter = ["all", "ready", "in_progress", "needs_attention", "cancelled"].includes(nextFilter) ? nextFilter : "all";
  const filters = document.getElementById("vf-library-filters");
  if (filters) {
    filters.querySelectorAll("[data-vf-filter]").forEach(button => {
      button.classList.toggle("active", button.getAttribute("data-vf-filter") === vfLibraryFilter);
      button.setAttribute("aria-pressed", String(button.getAttribute("data-vf-filter") === vfLibraryFilter));
    });
  }
  renderVideoHistory();
}

function vfClearLibraryFilters() {
  vfLibraryQuery = "";
  vfLibraryFilter = "all";
  const search = document.getElementById("vf-library-search");
  if (search) search.value = "";
  const filters = document.getElementById("vf-library-filters");
  if (filters) {
    filters.querySelectorAll("[data-vf-filter]").forEach(button => {
      button.classList.toggle("active", button.getAttribute("data-vf-filter") === "all");
      button.setAttribute("aria-pressed", String(button.getAttribute("data-vf-filter") === "all"));
    });
  }
  renderVideoHistory();
  search?.focus();
}

function vfEnsureLibraryNodes() {
  const libraryGrid = document.getElementById("vf-library-grid");
  if (!libraryGrid) return null;
  let cards = document.getElementById("vf-library-cards");
  if (!cards) {
    cards = document.createElement("div");
    cards.id = "vf-library-cards";
    cards.className = "flow-library-cards";
    libraryGrid.appendChild(cards);
  }
  const body = document.getElementById("vf-history-body");
  let noMatch = document.getElementById("vf-library-nomatch");
  if (body && !noMatch) {
    noMatch = document.createElement("div");
    noMatch.id = "vf-library-nomatch";
    noMatch.className = "vf-empty-state";
    noMatch.hidden = true;
    noMatch.innerHTML = `
      <div class="vf-empty-icon" aria-hidden="true"><svg class="lucide vf-ico" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"/></svg></div>
      <strong>No videos match</strong>
      <span>Try a different search or filter.</span>
      <button type="button" class="vf-text-button" onclick="vfClearLibraryFilters()">Clear filters</button>`;
    body.appendChild(noMatch);
  }
  return { cards, noMatch };
}

/**
 * More menu (Share / Details / Delete) for library cards. Rendering is
 * delegated; an open menu defers background re-renders so polling never
 * removes a menu from under the cursor.
 */
function vfFlowMenuHtml(videoId, videoTitle, actions) {
  const items = actions.map(action => {
    const labels = {
      share: "Share",
      details: "Details",
      delete: "Delete",
    };
    return `<button type="button" class="flow-menu-item${action === "delete" ? " danger" : ""}" role="menuitem" data-vf-action="${action}" data-vf-id="${vfEscape(videoId)}">${labels[action] || action}</button>`;
  }).join("");
  return `
    <div class="flow-menu-wrap">
      <button type="button" class="flow-menu-trigger" aria-haspopup="menu" aria-expanded="false" aria-label="More actions for ${vfEscape(videoTitle || "this video")}">⋯</button>
      <div class="flow-menu" role="menu" hidden>${items}</div>
    </div>`;
}

function vfLibraryCardHtml(video) {
  const complete = vfIsVideoComplete(video);
  const failed = String(video.status || "").toLowerCase() === "failed";
  const cancelled = String(video.status || "").toLowerCase() === "cancelled";
  const bucket = vfLibraryBucket(video);
  const authFailed = failed && isAuthError(video);
  const isNlm = video.provider === "notebooklm" || video.engine_version === "notebooklm" || String(video.engine_version || "").toLowerCase().includes("notebook");
  const mode = isNlm
    ? `NotebookLM · ${video.format ? (video.format.charAt(0).toUpperCase() + video.format.slice(1)) : "Brief"}`
    : (video.mode === "full" ? "Full explanation" : video.mode === "spatial_3d" ? "Spatial 3D" : "Summary");
  const engineVersion = isNlm ? "Google NotebookLM (HD)" : (video.engine_version || "Visual V2.1");
  const title = video.title || "Untitled Video";
  const statusLabel = vfLibraryStatusLabel(video);
  const duration = vfFormatKnownDuration(video.duration_sec);
  const vertical = String(video.format || "").toLowerCase() === "short"; // 9:16 vertical short
  const downloadHref = vfEscape(video.download_url || `/api/video-flow/videos/${encodeURIComponent(video.id)}/file`);
  const detailRows = [];

  // Technical details stay under the Details disclosure (plan: hide engine
  // versions, timings, raw ids, and logs from the card face).
  detailRows.push(`<div class="flow-card-detail-row"><span>Type</span><span>${vfEscape(mode)}</span></div>`);
  detailRows.push(`<div class="flow-card-detail-row"><span>Engine</span><span>${vfEscape(engineVersion)}</span></div>`);
  detailRows.push(`<div class="flow-card-detail-row"><span>Saved status</span><span>${vfEscape(video.status || "unknown")}</span></div>`);
  detailRows.push(`<div class="flow-card-detail-row"><span>Video ID</span><span><code>${vfEscape(video.id)}</code></span></div>`);
  const timings = vfRenderTimingBadge(video);
  if (timings) detailRows.push(`<div class="flow-card-detail-row flow-card-detail-timings">${timings}</div>`);
  if (video.error) {
    detailRows.push(`<div class="flow-card-detail-row flow-card-detail-error"><span>Error</span><span>${vfEscape(cleanErrorMessage(video.error))}</span></div>`);
  }
  const fallbackNotice = (complete && video.fallback_reason)
    ? `<p class="vf-error-notice flow-card-fallback" title="${vfEscape(video.fallback_error || "")}">⚠ ${video.fallback_requested_engine === "notebooklm" ? "NotebookLM login expired" : "Requested engine unavailable"} — rendered with the local engine instead, so this is app engine output (not NotebookLM). ${video.fallback_requested_engine === "notebooklm" ? `<a href="#" onclick="startNotebookLMAuth(); return false;">Sign in</a> to use NotebookLM next time.` : ""}</p>`
    : "";

  let thumbInner;
  if (complete) {
    thumbInner = `<img class="vf-thumb-img" src="/api/video-flow/videos/thumb?id=${encodeURIComponent(video.id)}" alt="" loading="lazy" onerror="this.parentElement.classList.add('flow-thumb-missing'); this.remove();">`;
  } else {
    // Failed / in-progress / cancelled: a neutral placeholder, never a broken
    // image and never a false Ready look.
    thumbInner = `<div class="flow-card-thumb-placeholder" aria-hidden="true"></div>`;
  }

  let bodyExtra = "";
  let actionButtons = "";

  if (bucket === "in_progress") {
    const progress = Math.max(0, Math.min(100, Math.round(Number(video.progress || 0))));
    bodyExtra += `
      <div class="vf-card-live-timer vf-live-timer" data-video-id="${vfEscape(video.id)}"></div>
      <div class="flow-card-stage"><small>${vfEscape(video.stage || "Queued")}</small><small>${progress > 0 ? `${progress}%` : "Starting…"}</small></div>
      ${progress > 0 ? `<div class="vf-progress-track"><span style="width:${progress}%"></span></div>` : ""}`;
    actionButtons += `<button class="vf-icon-button" type="button" onclick="cancelActiveVideoGeneration()">✕ Cancel</button>`;
  } else if (failed) {
    const reason = authFailed
      ? "Google authentication expired — reconnect your Google account to retry."
      : (vfConciseError(video) || "Generation failed. Details are available below.");
    bodyExtra += `<p class="flow-card-reason">${vfEscape(reason)}</p>`;
    if (authFailed) {
      actionButtons += `<button class="vf-icon-button" type="button" onclick="startNotebookLMAuth(true)">↻ Reconnect</button>`;
    }
    actionButtons += `<button class="vf-icon-button" type="button" onclick="retryVideoFlow('${vfEscape(video.id)}')">↻ Retry</button>`;
  } else if (cancelled) {
    bodyExtra += `<p class="flow-card-reason flow-card-reason-muted">Cancelled — nothing is generating for this video.</p>`;
  }

  const menuActions = [];
  if (complete) {
    actionButtons += `
      <button class="vf-icon-button" type="button" onclick="previewVideoFlow('${vfEscape(video.id)}')"><svg class="lucide vf-ico" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"/></svg> Play</button>
      <button class="vf-icon-button vf-download-btn" type="button" onclick="downloadVideoFlow('${vfEscape(video.id)}', this)" title="Download video">↓ Download</button>`;
    menuActions.push("share", "details", "delete");
  } else {
    menuActions.push("details", "delete");
  }

  return `
    <article class="flow-card vf-library-card flow-status-${vfEscape(bucket)} ${cancelled ? "flow-card-cancelled" : ""} ${authFailed ? "vf-card-auth-error" : ""}" data-video-id="${vfEscape(video.id)}" data-status="${vfEscape(video.status || "")}">
      <div class="flow-card-thumb"${vertical ? ' data-vertical="true"' : ""}>
        ${thumbInner}
        <span class="flow-card-status flow-card-status-${vfEscape(bucket)}">${vfEscape(statusLabel)}</span>
      </div>
      <div class="flow-card-body">
        <h3 class="flow-card-title" title="${vfEscape(title)}">${vfEscape(title)}</h3>
        <div class="flow-card-meta">
          <span>${vfEscape(vfFormatDate(video.created_at))}</span>
          ${duration ? `<span>${vfEscape(duration)}</span>` : ""}
        </div>
        ${fallbackNotice}
        ${bodyExtra}
        <details class="flow-disclosure flow-card-details">
          <summary>Details</summary>
          <div class="flow-card-details-body">${detailRows.join("")}</div>
        </details>
        <div class="flow-card-actions">
          ${actionButtons}
          ${vfFlowMenuHtml(video.id, title, menuActions)}
        </div>
      </div>
    </article>`;
}

function renderVideoHistory() {
  vfUpdateLibraryBadge(vfVideos.length);
  const libraryGrid = document.getElementById("vf-library-grid");
  if (!libraryGrid) {
    // New library container not present (HTML mid-rewrite) — legacy path.
    vfRenderLegacyHistory();
    return;
  }
  vfInitLibraryControls();

  // An open More menu must never be yanked away by background polling: defer
  // the rebuild until the menu closes.
  if (document.querySelector(".flow-menu-wrap[data-open='true']")) {
    vfLibraryRenderPending = true;
    return;
  }
  vfLibraryRenderPending = false;

  const nodes = vfEnsureLibraryNodes();
  if (!nodes || !nodes.cards) return;
  const { cards, noMatch } = nodes;
  const legacyGrid = document.getElementById("vf-history-grid");
  const emptyState = document.getElementById("vf-history-empty");
  const count = document.getElementById("vf-history-count");
  if (legacyGrid) legacyGrid.style.display = "none";

  const total = vfVideos.length;
  const filtered = vfSortVideosNewestFirst(vfVideos.filter(vfVideoMatchesLibrary));
  const isFiltering = Boolean(vfLibraryQuery.trim()) || vfLibraryFilter !== "all";

  if (count) {
    if (isFiltering) {
      count.textContent = `Showing ${filtered.length} of ${total} ${total === 1 ? "video" : "videos"} loaded on this page`;
    } else {
      count.textContent = total === 1 ? "1 video" : `${total} videos`;
    }
  }

  if (total === 0) {
    cards.innerHTML = "";
    cards.style.display = "none";
    if (noMatch) noMatch.hidden = true;
    if (emptyState) emptyState.style.display = "flex";
    vfUpdateLibraryFilterCounts();
    return;
  }

  if (emptyState) emptyState.style.display = "none";
  if (filtered.length === 0) {
    cards.innerHTML = "";
    cards.style.display = "none";
    if (noMatch) noMatch.hidden = false;
    vfUpdateLibraryFilterCounts();
    return;
  }

  if (noMatch) noMatch.hidden = true;
  cards.style.display = "";
  cards.innerHTML = filtered.map(vfLibraryCardHtml).join("");
  vfUpdateLibraryFilterCounts();
  // Keep any in-progress card's elapsed timer in sync with the status panel.
  const activeVideo = vfVideos.find(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status));
  if (activeVideo) vfUpdateLiveTimer(activeVideo);
}

function vfInitLibraryControls() {
  if (vfLibraryControlsWired) return;
  const search = document.getElementById("vf-library-search");
  if (search && !search.dataset.vfSearchWired) {
    search.dataset.vfSearchWired = "1";
    search.addEventListener("input", () => {
      vfLibraryQuery = search.value || "";
      renderVideoHistory();
    });
  }
  vfLibraryControlsWired = true;
}

// ---------------------------------------------------------------------------
// Library More-menu behavior (delegated, survives re-renders).
// ---------------------------------------------------------------------------

function vfCloseAllFlowMenus() {
  document.querySelectorAll(".flow-menu-wrap[data-open='true']").forEach(wrap => {
    wrap.removeAttribute("data-open");
    const trigger = wrap.querySelector(".flow-menu-trigger");
    const menu = wrap.querySelector(".flow-menu");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (menu) menu.hidden = true;
  });
  if (vfLibraryRenderPending) {
    vfLibraryRenderPending = false;
    renderVideoHistory();
  }
}

function vfHandleLibraryAction(action, videoId) {
  if (action === "share") {
    shareVideoFlow(videoId);
    return;
  }
  if (action === "delete") {
    beginVideoDelete(videoId);
    return;
  }
  if (action === "details") {
    const card = document.querySelector(`.flow-card[data-video-id="${CSS.escape(String(videoId))}"]`);
    const details = card ? card.querySelector(".flow-card-details") : null;
    if (details) {
      details.open = true;
      details.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
}

function vfHandleGlobalClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;

  // Library filter buttons.
  const filterButton = target.closest("#vf-library-filters [data-vf-filter]");
  if (filterButton) {
    vfSetLibraryFilter(filterButton.getAttribute("data-vf-filter"));
    return;
  }

  // More menu items.
  const menuItem = target.closest(".flow-menu-item");
  if (menuItem) {
    const wrap = menuItem.closest(".flow-menu-wrap");
    vfCloseAllFlowMenus();
    vfHandleLibraryAction(menuItem.getAttribute("data-vf-action"), menuItem.getAttribute("data-vf-id"));
    if (wrap) wrap.removeAttribute("data-open");
    return;
  }

  // More menu triggers.
  const menuTrigger = target.closest(".flow-menu-trigger");
  if (menuTrigger) {
    const wrap = menuTrigger.closest(".flow-menu-wrap");
    const menu = wrap ? wrap.querySelector(".flow-menu") : null;
    const wasOpen = wrap && wrap.getAttribute("data-open") === "true";
    vfCloseAllFlowMenus();
    if (wrap && menu && !wasOpen) {
      wrap.setAttribute("data-open", "true");
      menu.hidden = false;
      menuTrigger.setAttribute("aria-expanded", "true");
      const firstItem = menu.querySelector(".flow-menu-item");
      if (firstItem) firstItem.focus();
    }
    return;
  }

  // Click outside an open menu closes it.
  if (document.querySelector(".flow-menu-wrap[data-open='true']") && !target.closest(".flow-menu-wrap")) {
    vfCloseAllFlowMenus();
  }

  // Shared picker rows / details / retry (only when this file owns the session).
  const pickerModal = document.getElementById("vf-model-picker-modal");
  if (pickerModal && !pickerModal.classList.contains("hidden") && !vfSharedPickerActive()) {
    const retryButton = target.closest(".flow-picker-retry");
    if (retryButton) {
      vfReloadPickerCatalog();
      return;
    }
    const clearSearch = target.closest("[data-vf-picker-action='clear-search']");
    if (clearSearch) {
      vfSetPickerSearchValue("");
      vfShowPickerStatus(null);
      renderVideoModelPicker();
      const live = document.getElementById("vf-picker-search") || document.getElementById("vf-model-picker-search");
      live?.focus();
      return;
    }
    const manageAction = target.closest("[data-vf-picker-action='manage']");
    if (manageAction) {
      vfPickerGoToDestination(vfPickerContextConfig(vfModelPickerContext).destination);
      return;
    }
    const detailsButton = target.closest("button.flow-picker-details");
    if (detailsButton) {
      const panel = detailsButton.parentElement ? detailsButton.parentElement.querySelector(".flow-picker-details-panel") : null;
      if (panel) {
        const willOpen = panel.hidden;
        panel.hidden = !willOpen;
        detailsButton.setAttribute("aria-expanded", String(willOpen));
      }
      return;
    }
    const row = target.closest("button.flow-picker-row[data-model-ref]");
    if (row && row.getAttribute("aria-disabled") !== "true") {
      const ref = row.getAttribute("data-model-ref");
      if (ref) chooseVideoModel(ref);
    }
  }
}

function vfHandleGlobalKeydown(event) {
  if (event.key === "Escape") {
    const openMenu = document.querySelector(".flow-menu-wrap[data-open='true']");
    if (openMenu) {
      event.preventDefault();
      vfCloseAllFlowMenus();
      return;
    }
    const pickerModal = document.getElementById("vf-model-picker-modal");
    if (pickerModal && !pickerModal.classList.contains("hidden") && !vfSharedPickerActive()) {
      event.preventDefault();
      closeVideoModal("vf-model-picker-modal");
    }
    return;
  }
  if (event.key === "Tab") {
    // Contain focus inside the picker while this file owns the session.
    const pickerModal = document.getElementById("vf-model-picker-modal");
    if (pickerModal && !pickerModal.classList.contains("hidden") && !vfSharedPickerActive()) {
      const focusables = Array.from(
        pickerModal.querySelectorAll('button:not([disabled]):not([aria-disabled="true"]), input, select, a[href], [tabindex]:not([tabindex="-1"])')
      ).filter(el => el.offsetParent !== null || el === document.activeElement);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!pickerModal.contains(document.activeElement)) {
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
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("click", vfHandleGlobalClick);
  document.addEventListener("keydown", vfHandleGlobalKeydown);
}

function vfCapabilityBadges(model) {
  const ico = (typeof vfUiIcon === "function") ? vfUiIcon : function () { return ""; };
  const labels = {
    vision: ico("eye") + " Vision",
    reasoning: ico("sparkles") + " Reasoning",
    code: ico("code") + " Code",
    audio: ico("music") + " Audio",
    private: ico("home") + " Private",
    offline: ico("powerOff") + " Offline",
  };
  return (model.capabilities || []).map(item => '<span class="vf-capability">' + (labels[item] || vfEscape(item)) + '</span>').join("");
}

function renderVideoProviderGrid(elementId, providers) {
  const grid = document.getElementById(elementId);
  if (!grid) return;
  grid.className = "providers-cards-grid";
  grid.innerHTML = (providers || []).map(provider => {
    const connected = provider.status === "connected";
    const statusText = provider.category === "oauth"
      ? (connected ? "Connected" : "Not connected")
      : connected
        ? `${provider.active_count} Active`
        : provider.category === "local" ? "Native / Local" : "Not connected";
    const logo = vfBrandLogo(provider.id, vfProviderIcons[provider.id] || provider.icon || "🎬");
    return `
      <div class="provider-card-item" onclick="openVideoProvider(${vfJsArg(provider.id)})">
        <div class="provider-card-left">
          <div class="provider-card-logo provider-brand-logo">${String(logo).startsWith("<svg") ? logo : vfEscape(logo)}</div>
          <div class="provider-card-info">
            <span class="provider-card-name">${vfEscape(provider.name)}</span>
            <span class="provider-card-status">
              <span class="status-dot-indicator ${connected ? 'connected' : ''}"></span>
              ${vfEscape(statusText)}
            </span>
          </div>
        </div>
        <label class="toggle-switch" onclick="event.stopPropagation()">
          <input type="checkbox" ${connected ? 'checked' : ''} onchange="toggleVideoProviderMaster(${vfJsArg(provider.id)}, this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    `;
  }).join("");
}

async function toggleVideoProviderMaster(providerId, isChecked) {
  try {
    const data = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
    if (data && data.connections && data.connections.length > 0) {
      for (const conn of data.connections) {
        await vfPost("/api/video-flow/providers/connections/update", {
          id: conn.id,
          is_active: isChecked,
          provider: providerId,
        });
      }
      vfToast(`${providerId} provider connections ${isChecked ? 'enabled' : 'disabled'}.`);
      loadVideoFlow();
      if (vfCurrentProvider === providerId) await refreshCurrentVideoProviderDetail();
    } else {
      openVideoProvider(providerId);
    }
  } catch (err) {
    vfToast(err.message || "Error toggling provider", true);
  }
}

function vfSelectableVideoModels() {
  // Context-specific catalogs: the Speech-to-Text and AI Polish selectors use
  // their own model lists, not the Video Flow catalog.
  if (vfModelPickerContext === "voice_flow_stt" && typeof voiceFlowPolicyModels !== "undefined" && Array.isArray(voiceFlowPolicyModels) && voiceFlowPolicyModels.length) {
    return voiceFlowPolicyModels;
  }
  if (vfModelPickerContext === "voice_flow_polish" && typeof voiceFlowPolishModels !== "undefined" && Array.isArray(voiceFlowPolishModels) && voiceFlowPolishModels.length) {
    return voiceFlowPolishModels;
  }
  return (vfCatalog.models || []).filter(model => model.full_id !== "local/deterministic" && model.available && model.is_active !== false);
}

function vfIsSelectableVideoModelRef(modelRef) {
  return modelRef === "local/deterministic" || vfSelectableVideoModels().some(model => model.full_id === modelRef);
}

function renderVideoCatalog() {
  const models = vfSelectableVideoModels();
  const groups = new Map();
  for (const model of models) {
    const name = model.provider_name || model.provider;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(model);
  }

  const select = document.getElementById("vf-model-select");
  if (select) {
    select.innerHTML = [...groups.entries()].map(([name, items]) => '<optgroup label="' + vfEscape(name) + '">' + items.map(model =>
        '<option value="' + vfEscape(model.full_id) + '">' + vfEscape(model.display_name) + '</option>'
      ).join("") + '</optgroup>').join("");
    const activeModelRef = vfCatalog.active_model || "local/deterministic";
    select.value = activeModelRef;
    updateActiveVideoModel(activeModelRef);
  }

  const providerGroups = vfCatalog.provider_groups || {};
  renderVideoProviderGrid("vf-oauth-provider-grid", providerGroups.oauth || []);
  renderVideoProviderGrid("vf-api-provider-grid", providerGroups.api_key || []);
  renderCustomProviderGrid();
  renderVideoModelPicker();
}

function vfPickerActiveRef() {
  if (vfModelPickerContext === "audio_summary") {
    if (typeof afSummaryModelRef === "string" && afSummaryModelRef) return afSummaryModelRef;
    return "local/deterministic";
  }
  if (vfModelPickerContext === "voice_flow_stt") {
    if (typeof voiceFlowPolicyModelRef === "string" && voiceFlowPolicyModelRef) return voiceFlowPolicyModelRef;
    return "local/faster-whisper-base.en";
  }
  if (vfModelPickerContext === "voice_flow_polish") {
    if (typeof voiceFlowPolishModelRef === "string" && voiceFlowPolishModelRef) return voiceFlowPolishModelRef;
    return "local/deterministic";
  }
  if (vfModelPickerContext === "voice_flow") {
    if (typeof voiceFlowPolicyModelRef === "string" && voiceFlowPolicyModelRef) return voiceFlowPolicyModelRef;
  }
  if (vfModelPickerContext === "audio_voice") {
    if (typeof audioVoicePolicyModelRef === "string" && audioVoicePolicyModelRef) return audioVoicePolicyModelRef;
  }
  if (vfModelPickerContext === "video_flow_voice") {
    return videoFlowVoiceModelRef || "edge/en-US-AvaNeural";
  }
  return vfCatalog.active_model || "local/deterministic";
}

function vfPickerProviderIcon(key) {
  if (typeof vfBrandLogoByName === "function") {
    const brand = vfBrandLogoByName(key);
    if (brand) return brand;
  }
  const icon = vfProviderIcons[key];
  if (icon) return icon;
  const model = (vfCatalog.models || []).find(m => m.provider_name === key);
  return (model && vfProviderIcons[model.provider]) || "✦";
}

// ---------------------------------------------------------------------------
// Shared model and voice picker helpers
// ---------------------------------------------------------------------------

function vfPickerDom() {
  const root = document.getElementById("vf-model-picker-modal");
  if (!root) return null;
  const byId = (id) => root.querySelector("#" + id) || document.getElementById(id) || null;
  return {
    root,
    title: byId("vf-picker-title"),
    legacyTitle: byId("vf-model-picker-title"),
    helper: byId("vf-picker-helper"),
    legacyHelper: byId("vf-model-picker-note"),
    close: byId("vf-picker-close"),
    search: byId("vf-picker-search"),
    searchMirror: byId("vf-model-picker-search"),
    current: byId("vf-picker-current"),
    list: byId("vf-picker-list") || byId("vf-model-picker-list"),
    manage: byId("vf-picker-manage-link"),
    kicker: byId("vf-model-picker-kicker"),
  };
}

function vfSetPickerSearchValue(value) {
  const live = document.getElementById("vf-picker-search");
  const mirror = document.getElementById("vf-model-picker-search");
  if (live) live.value = value;
  if (mirror) mirror.value = value;
}

function vfPickerSearchValue() {
  const live = document.getElementById("vf-picker-search");
  if (live && live.value) return live.value;
  const mirror = document.getElementById("vf-model-picker-search");
  return (mirror && mirror.value) || "";
}

// Legacy title compatibility for test contract: "Select the speech-to-text model", "Select the polishing model"
const VF_PICKER_CHROME = {
  video_flow: {
    title: "Choose a video planning model",
    helper: "Used by the app's video engine.",
    manageLabel: "Manage video model providers",
    destination: "video-providers",
    searchPlaceholder: "Search models or providers…",
  },
  video_flow_voice: {
    title: "Choose a narration voice",
    helper: "Used by the app's video engine. This voice list is shared with Audio Flow — the two features keep separate selections.",
    manageLabel: "Manage voice services",
    destination: "audio-providers",
    searchPlaceholder: "Search voices or services…",
  },
  audio_voice: {
    title: "Choose a reading voice",
    helper: "Used for Read mode.",
    manageLabel: "Manage voice services",
    destination: "audio-providers",
    searchPlaceholder: "Search voices or services…",
  },
  voice_flow_stt: {
    title: "Choose speech recognition", // Legacy: Select the speech-to-text model
    helper: "Turns your speech into text.",
    manageLabel: "Manage speech services",
    destination: "providers",
    searchPlaceholder: "Search speech services or models…",
  },
  voice_flow_polish: {
    title: "Choose text cleanup", // Legacy: Select the polishing model
    helper: "Cleans up dictated text using your existing settings.",
    manageLabel: "Manage text cleanup connections",
    destination: "video-providers",
    searchPlaceholder: "Search cleanup models or services…",
  },
  voice_flow: {
    title: "Choose text cleanup", // Legacy: Select the polishing model
    helper: "Cleans up dictated text using your existing settings.",
    manageLabel: "Manage text cleanup connections",
    destination: "video-providers",
    searchPlaceholder: "Search cleanup models or services…",
  },
  audio_summary: {
    title: "Choose a summary model",
    helper: "Condenses highlighted text before it is read aloud.",
    manageLabel: "Manage providers",
    destination: "providers",
    searchPlaceholder: "Search models or providers…",
  },
};

function vfPickerContextConfig(context) {
  return VF_PICKER_CHROME[context] || VF_PICKER_CHROME.video_flow;
}

function vfUpdateModelPickerChrome() {
  const dom = vfPickerDom();
  const config = vfPickerContextConfig(vfModelPickerContext);
  if (!dom) return;
  if (dom.legacyTitle) dom.legacyTitle.textContent = config.title;
  else if (dom.title) dom.title.textContent = config.title;
  if (dom.legacyHelper) dom.legacyHelper.textContent = config.helper;
  else if (dom.helper) dom.helper.textContent = config.helper;
  if (dom.kicker && !dom.kicker.hidden) dom.kicker.hidden = true;
  if (dom.search) {
    dom.search.setAttribute("placeholder", config.searchPlaceholder || "Search…");
  }
  if (dom.manage) {
    dom.manage.textContent = (config.manageLabel || "Manage providers") + " →";
    dom.manage.onclick = (event) => {
      event.preventDefault();
      vfPickerGoToDestination(config.destination);
    };
  }
}

function vfPickerGoToDestination(destination) {
  closeVideoModal("vf-model-picker-modal");
  try {
    if (typeof fpGoToDestination === "function") {
      fpGoToDestination(destination);
      return;
    }
  } catch (_) { /* fall through to local routing */ }
  const nav = typeof window !== "undefined" ? window["switchPage"] : (typeof switchPage === "function" ? switchPage : null);
  if (typeof nav !== "function") return;
  if (destination === "video-providers") {
    nav("videoflow", { skipScrollReset: true });
    window.setTimeout(() => {
      document.getElementById("vf-api-provider-grid")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  } else if (destination === "audio-providers") {
    nav("audioflow", { skipScrollReset: true });
    window.setTimeout(() => {
      document.getElementById("audio-providers-grid-container")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  } else if (destination === "providers") {
    nav("providers", { skipScrollReset: true });
    window.setTimeout(() => {
      document.getElementById("providers-grid-container")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  }
}

function vfPickerModelForRef(modelRef) {
  if (modelRef === "local/deterministic") {
    return {
      full_id: "local/deterministic",
      display_name: "Built-in deterministic planner",
      provider: "local",
      provider_name: "On this PC",
      capabilities: ["offline"],
    };
  }
  const catalogs = [vfCatalog.models || [], videoFlowVoiceModels || []];
  if (typeof vfModelPickerContext !== "undefined") {
    if (vfModelPickerContext === "voice_flow_stt" && typeof voiceFlowPolicyModels !== "undefined") catalogs.push(voiceFlowPolicyModels);
    if (vfModelPickerContext === "voice_flow_polish" && typeof voiceFlowPolishModels !== "undefined") catalogs.push(voiceFlowPolishModels);
    if (vfModelPickerContext === "audio_voice" && typeof audioVoicePolicyModels !== "undefined") catalogs.push(audioVoicePolicyModels);
  }
  for (const catalog of catalogs) {
    const found = (catalog || []).find(model => model.full_id === modelRef);
    if (found) return found;
  }
  return null;
}

function vfPickerIconMarkup(model) {
  const icon = vfPickerProviderIcon(model ? (model.provider || model.provider_name || "") : "");
  return String(icon).startsWith("<svg") ? icon : vfEscape(icon);
}

function vfPickerCapabilityList(model) {
  const labels = { vision: "Vision", reasoning: "Reasoning", code: "Code", audio: "Audio", private: "Private", offline: "Offline" };
  return (model && Array.isArray(model.capabilities) ? model.capabilities : [])
    .map(item => `<span class="flow-picker-cap">${vfEscape(labels[item] || item)}</span>`)
    .join("");
}

function vfPickerRowHtml(model, activeRef) {
  const ref = model.full_id;
  const provider = model.provider_name || model.provider || "";
  const unavailable = typeof vfModelPickerContext !== "undefined" && vfModelPickerContext === "voice_flow_polish" && model.polish_supported === false &&
    model.provider !== "antigravity" && model.provider !== "agy";
  const unavailableReason = unavailable
    ? (model.polish_unavailable_reason || "Polishing is not supported by this connection")
    : "";
  const isSelected = ref === activeRef;
  const isSaving = typeof vfPickerSavingRef !== "undefined" && vfPickerSavingRef === ref;
  const classes = ["flow-picker-row"];
  if (isSelected) classes.push("is-selected");
  if (unavailable) classes.push("is-unavailable", "flow-picker-row-unavailable");
  const rowAttrs = [
    'type="button"',
    `class="${classes.join(" ")}"`,
    `data-model-ref="${vfEscape(ref)}"`
  ];
  if (!unavailable) {
    rowAttrs.push(`onclick="chooseVideoModel('${vfEscape(ref)}')"` );
  }
  if (isSelected) rowAttrs.push('data-selected="true"', 'aria-checked="true"', 'role="radio"');
  if (unavailable) rowAttrs.push('aria-disabled="true"', `title="${vfEscape(unavailableReason)}"`);
  const selectedBadge = isSelected && !isSaving ? '<span class="flow-picker-selected">Selected</span>' : "";
  const savingBadge = isSaving ? '<span class="flow-picker-saving">Saving…</span>' : "";
  const nameSuffix = unavailable ? ' <span class="flow-picker-unavailable-note">(unavailable)</span>' : "";
  const icon = vfPickerIconMarkup(model);
  return `
    <div class="flow-picker-item${unavailable ? " is-unavailable-item" : ""}">
      <button ${rowAttrs.join(" ")}>
        <span class="flow-picker-icon" aria-hidden="true">${icon}</span>
        <div class="flow-picker-text">
          <span class="flow-picker-name">${vfEscape(model.display_name || ref)}${nameSuffix}</span>
          ${provider ? `<span class="flow-picker-sub">${vfEscape(provider)}</span>` : ""}
          <span class="flow-picker-details-region"><code>${vfEscape(ref)}</code></span>
        </div>
        <span class="vf-capability-list">${vfPickerCapabilityList(model)}</span>
        ${savingBadge}
        ${selectedBadge}
      </button>
      <button type="button" class="flow-picker-details" data-model-ref="${vfEscape(ref)}" aria-expanded="false" aria-label="Details for ${vfEscape(model.display_name || ref)}">Details</button>
      <div class="flow-picker-details-panel" hidden>
        ${unavailable ? `<p class="flow-picker-detail-reason">${vfEscape(unavailableReason)}</p>` : ""}
        <div class="flow-picker-detail-caps">${vfPickerCapabilityList(model)}</div>
        <code class="flow-picker-detail-id">${vfEscape(ref)}</code>
      </div>
    </div>`;
}

function vfPickerCurrentHtml(activeRef) {
  const model = vfPickerModelForRef(activeRef);
  const name = model ? (model.display_name || activeRef) : (activeRef || "");
  const provider = model ? (model.provider_name || model.provider || "") : "";
  const savedUnavailable = !model;
  const isSaving = typeof vfPickerSavingRef !== "undefined" && vfPickerSavingRef === activeRef;
  const classes = ["flow-picker-row", "flow-picker-row-current"];
  if (savedUnavailable) classes.push("is-unavailable", "flow-picker-row-unavailable");
  const stateBadge = isSaving ? "Saving…" : (savedUnavailable ? "Saved · unavailable" : "Selected");
  return `
    <div class="flow-picker-item flow-picker-current-item">
      <button type="button" class="${classes.join(" ")}" data-model-ref="${vfEscape(activeRef || "")}"
        ${savedUnavailable ? 'aria-disabled="true" title="This choice is not available right now — nothing was switched automatically."' : 'data-selected="true" aria-checked="true" role="radio"'}>
        <span class="flow-picker-icon" aria-hidden="true">${model ? vfPickerIconMarkup(model) : vfEscape("•")}</span>
        <div class="flow-picker-text">
          <span class="flow-picker-name">${vfEscape(name || "No choice saved yet")}</span>
          ${provider ? `<span class="flow-picker-sub">${vfEscape(provider)}</span>` : ""}
        </div>
        <span class="flow-picker-selected">${vfEscape(stateBadge)}</span>
      </button>
      <button type="button" class="flow-picker-details" aria-expanded="false" aria-label="Details for ${vfEscape(name || "current choice")}">Details</button>
      <div class="flow-picker-details-panel" hidden>
        <div class="flow-picker-detail-caps">${model ? vfPickerCapabilityList(model) : ""}</div>
        <code class="flow-picker-detail-id">${vfEscape(activeRef || "")}</code>
      </div>
      ${savedUnavailable ? '<p class="flow-picker-detail-reason">This choice is not available right now — it may have been disconnected. Nothing was switched automatically; pick another option below.</p>' : ""}
    </div>`;
}

function vfShowPickerStatus(kind, message) {
  const dom = vfPickerDom();
  if (!dom || !dom.root) return;
  let region = document.getElementById("vf-picker-status");
  if (!kind || !message) {
    if (region) region.remove();
    return;
  }
  if (!region) {
    region = document.createElement("div");
    region.id = "vf-picker-status";
    region.className = "flow-picker-state error flow-picker-state--error";
    region.setAttribute("role", "alert");
    if (dom.list && dom.list.parentElement) dom.list.parentElement.insertBefore(region, dom.list);
    else dom.root.appendChild(region);
  }
  region.innerHTML = `<span class="flow-picker-status-text">${vfEscape(message)}</span>`;
}

function vfRenderPickerState(kind, message, withRetry) {
  const dom = vfPickerDom();
  if (!dom || !dom.list) return;
  const spinner = kind === "loading" ? '<span class="flow-spinner" aria-hidden="true"></span>' : "";
  const retry = withRetry ? '<button type="button" class="flow-picker-retry">Try again</button>' : "";
  dom.list.innerHTML = `<div class="flow-picker-state ${kind} flow-picker-state--${kind}">${spinner}<span>${vfEscape(message)}</span>${retry}</div>`;
}

function vfRenderPickerEmpty(query) {
  const dom = vfPickerDom();
  if (!dom || !dom.list) return;
  if (query) {
    dom.list.innerHTML = `
      <div class="flow-picker-state flow-picker-state--empty">
        <strong>No matches</strong>
        <span>Nothing matches “${vfEscape(query)}”.</span>
        <button type="button" class="flow-picker-empty-action" data-vf-picker-action="clear-search">Clear search</button>
      </div>`;
  } else {
    const config = vfPickerContextConfig(vfModelPickerContext);
    dom.list.innerHTML = `
      <div class="flow-picker-state flow-picker-state--empty">
        <strong>No available choices</strong>
        <span>Connect a service to add more choices.</span>
        <button type="button" class="flow-picker-empty-action" data-vf-picker-action="manage">${vfEscape(config.manageLabel || "Manage providers")}</button>
      </div>`;
  }
}

function vfReloadPickerCatalog() {
  const session = vfPickerSession;
  vfRenderPickerState("loading", "Loading choices…", false);
  vfEnsureCatalog().then(ok => {
    if (!vfIsPickerSessionCurrent(session)) return;
    if (!ok) {
      vfRenderPickerState("error", "Couldn't load choices.", true);
      return;
    }
    vfShowPickerStatus(null);
    renderVideoModelPicker();
  });
}

function renderVideoModelPicker() {
  if (typeof vfSharedPickerActive === "function" && vfSharedPickerActive()) return;
  const dom = typeof vfPickerDom === "function" ? vfPickerDom() : null;
  const listEl = (dom && dom.list) || (typeof document !== "undefined" && (document.getElementById("vf-picker-list") || document.getElementById("vf-model-picker-list")));
  if (!listEl) return;
  if (dom && dom.root && dom.root.classList && dom.root.classList.contains("hidden")) return;

  const query = (typeof vfPickerSearchValue === "function" ? vfPickerSearchValue() : (document.getElementById("vf-model-picker-search")?.value || "")).trim().toLowerCase();
  let models = vfSelectableVideoModels().filter(model =>
    !query || [model.provider_name, model.display_name, model.full_id, ...(model.capabilities || [])].join(" ").toLowerCase().includes(query)
  );
  if (typeof vfPickerAllowedRefs !== "undefined" && vfPickerAllowedRefs) {
    models = models.filter(model => vfPickerAllowedRefs.has(model.full_id));
    const extras = vfModelPickerContext === "audio_voice"
      ? (typeof audioVoicePolicyModels !== "undefined" ? audioVoicePolicyModels : [])
      : vfModelPickerContext === "video_flow_voice"
        ? videoFlowVoiceModels
        : vfModelPickerContext === "voice_flow_polish"
          ? (typeof voiceFlowPolishModels !== "undefined" ? voiceFlowPolishModels : [])
          : (typeof voiceFlowPolicyModels !== "undefined" ? voiceFlowPolicyModels : []);
    for (const pm of extras) {
      const matchesQuery = !query || [pm.provider_name, pm.display_name, pm.full_id, ...(pm.capabilities || [])].join(" ").toLowerCase().includes(query);
      if (matchesQuery && vfPickerAllowedRefs.has(pm.full_id) && !models.some(m => m.full_id === pm.full_id)) {
        models.push(pm);
      }
    }
  }

  // Current choice block (contract id #vf-picker-current).
  if (dom && dom.current) {
    const activeRef = vfPickerActiveRef();
    if (activeRef) {
      dom.current.hidden = false;
      dom.current.innerHTML = '<div class="flow-picker-current-heading">Current choice</div>' + vfPickerCurrentHtml(activeRef);
    } else {
      dom.current.hidden = true;
      dom.current.innerHTML = "";
    }
  }

  if (!models.length) {
    if (typeof vfRenderPickerEmpty === "function") vfRenderPickerEmpty(query);
    else listEl.innerHTML = '<div class="flow-picker-state flow-picker-state--empty"><strong>No available choices</strong></div>';
    return;
  }

  const groups = new Map();
  for (const model of models) {
    const name = model.provider_name || model.provider || "Other";
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(model);
  }
  const activeRef = vfPickerActiveRef();
  const sections = [];
  if (!vfPickerAllowedRefs && (!query || "on this pc built-in deterministic private offline".includes(query))) {
    if (typeof vfPickerRowHtml === "function") {
      sections.push('<h4 class="flow-picker-group-title">On this PC <span>1</span></h4>' + vfPickerRowHtml(vfPickerModelForRef("local/deterministic"), activeRef));
    } else {
      sections.push('<section class="vf-picker-group"><h4>⌂ On this PC <span>1</span></h4><button class="vf-picker-model ' + (activeRef === "local/deterministic" ? "selected" : "") + '" onclick="chooseVideoModel(\'local/deterministic\')"><strong>Built-in deterministic planner</strong></button></section>');
    }
  }
  for (const [providerName, items] of groups.entries()) {
    if (typeof vfPickerRowHtml === "function") {
      sections.push(`<h4 class="flow-picker-group-title">${vfEscape(providerName)} <span>${items.length}</span></h4>` +
        items.map(model => vfPickerRowHtml(model, activeRef)).join(""));
    } else {
      const icon = vfPickerProviderIcon(items[0].provider || providerName);
      sections.push('<section class="vf-picker-group"><h4>' + vfEscape(providerName) + ' <span>' + items.length + '</span></h4>' + items.map(model =>
        '<button class="vf-picker-model ' + (model.full_id === activeRef ? "selected" : "") + '" onclick="chooseVideoModel(\'' + vfEscape(model.full_id) + '\')"><span class="vf-picker-model-icon">' + vfEscape(icon) + '</span><span class="vf-picker-model-copy"><strong>' + vfEscape(model.display_name) + '</strong><small>' + vfEscape(model.full_id) + '</small></span><span class="vf-capability-list">' + (typeof vfCapabilityBadges === "function" ? vfCapabilityBadges(model) : "") + '</span><b class="vf-picker-check">✓</b></button>'
      ).join("") + '</section>');
    }
  }
  listEl.innerHTML = sections.join("");
  if (typeof listEl.setAttribute === "function") {
    if (typeof vfPickerSavingRef !== "undefined" && vfPickerSavingRef) listEl.setAttribute("aria-busy", "true");
    else if (typeof listEl.removeAttribute === "function") listEl.removeAttribute("aria-busy");
  }
}

let vfModelPickerContext = "video_flow";
let vfPickerAllowedRefs = null;
// Picker session: every open increments the token; async continuations
// (catalog load, save) must match it before touching the DOM — a late
// response from a previous context must never populate or save into the
// newly opened one (plan section 5, stale-response guard).
let vfPickerSession = null;
let vfPickerInvokingElement = null;
let vfPickerSavingRef = null;
let vfPickerOpenSeq = 0;

function vfSharedPickerActive() {
  // The shared core in app.js may own the picker session (audio contexts);
  // when it does, this file must not touch the dialog.
  try {
    return typeof fpState !== "undefined" && Boolean(fpState);
  } catch (_) {
    return false;
  }
}

function vfIsPickerSessionCurrent(session) {
  return Boolean(session && vfPickerSession === session &&
    !vfSharedPickerActive() &&
    !document.getElementById("vf-model-picker-modal")?.classList.contains("hidden"));
}

function openVideoModelPicker(context = "video_flow") {
  const dom = vfPickerDom();
  if (!dom || !dom.list) {
    console.warn("[video-flow] Picker dialog or list not found; picker cannot open.");
    return;
  }
  vfModelPickerContext = context;
  // Restricted contexts only offer the models their backend supports.
  if (context === "voice_flow_stt" && typeof voiceFlowPolicyModelSet !== "undefined" && voiceFlowPolicyModelSet) {
    vfPickerAllowedRefs = voiceFlowPolicyModelSet;
  } else if (context === "voice_flow_polish" && typeof voiceFlowPolishModelSet !== "undefined" && voiceFlowPolishModelSet) {
    vfPickerAllowedRefs = voiceFlowPolishModelSet;
  } else if (context === "audio_voice" && typeof audioVoicePolicySet !== "undefined" && audioVoicePolicySet) {
    vfPickerAllowedRefs = audioVoicePolicySet;
  } else if (context === "video_flow_voice") {
    // Only voices from the shared TTS catalog are offered; if the catalog
    // has not loaded yet the picker falls back to the Edge default only.
    vfPickerAllowedRefs = videoFlowVoiceSet || new Set(["edge/en-US-AvaNeural"]);
  } else if (context === "audio_summary") {
    // Audio Summary executes its own provider set (audio_summary.py); the
    // shared picker must only offer models from those providers.
    const AUDIO_SUMMARY_PROVIDERS = new Set([
      "gemini", "openai", "groq", "together", "openrouter",
      "nvidia_nim", "nim", "opencode_zen", "cloudflare", "anthropic",
    ]);
    const candidates = (typeof vfCatalog !== "undefined" && vfCatalog && Array.isArray(vfCatalog.models)) ? vfCatalog.models : [];
    const allowed = candidates.filter(m =>
      m.available !== false && AUDIO_SUMMARY_PROVIDERS.has(String(m.provider || "").toLowerCase()));
    vfPickerAllowedRefs = allowed.length ? new Set(allowed.map(m => m.full_id)) : null;
  } else {
    vfPickerAllowedRefs = null;
  }

  // Focus restore target for Escape / close (plan section 5 keyboard rules).
  const activeEl = document.activeElement;
  vfPickerInvokingElement = activeEl instanceof HTMLElement ? activeEl : null;
  vfPickerSession = { token: ++vfPickerOpenSeq, context };
  vfPickerSavingRef = null;

  vfSetPickerSearchValue("");
  vfShowPickerStatus(null);
  vfUpdateModelPickerChrome();
  // Defensive wiring: index.html also wires these inline; addEventListener
  // keeps the picker working if that inline handler ever changes. Idempotent.
  if (dom.search && !dom.search.dataset.vfSearchWired) {
    dom.search.dataset.vfSearchWired = "1";
    dom.search.addEventListener("input", () => {
      if (dom.searchMirror) dom.searchMirror.value = dom.search.value;
      if (vfIsPickerSessionCurrent(vfPickerSession)) renderVideoModelPicker();
    });
  }
  if (dom.searchMirror && !dom.searchMirror.dataset.vfSearchWired) {
    dom.searchMirror.dataset.vfSearchWired = "1";
    dom.searchMirror.addEventListener("input", () => {
      if (dom.search) dom.search.value = dom.searchMirror.value;
      if (vfIsPickerSessionCurrent(vfPickerSession)) renderVideoModelPicker();
    });
  }
  dom.root.classList.remove("hidden");

  if (!vfCatalogLoaded && context !== "video_flow_voice") {
    vfRenderPickerState("loading", "Loading choices…", false);
    const session = vfPickerSession;
    vfEnsureCatalog().then(ok => {
      // The modal may have been closed or the context switched before the
      // catalog arrived — a stale response must never populate the dialog.
      if (!vfIsPickerSessionCurrent(session)) return;
      if (!ok) {
        vfRenderPickerState("error", "Couldn't load choices.", true);
        return;
      }
      renderVideoModelPicker();
    });
  } else if (context === "video_flow_voice" && !(videoFlowVoiceModels || []).length) {
    // Voice catalog still loading — never show a premature "no choices".
    vfRenderPickerState("loading", "Loading voices…", false);
    const session = vfPickerSession;
    loadVideoFlowVoice().then(() => {
      if (!vfIsPickerSessionCurrent(session)) return;
      if (context === "video_flow_voice" && !(videoFlowVoiceModels || []).length) {
        vfPickerAllowedRefs = new Set([videoFlowVoiceModelRef || "edge/en-US-AvaNeural"]);
      }
      renderVideoModelPicker();
    });
  } else {
    renderVideoModelPicker();
  }
  requestAnimationFrame(() => {
    if (!vfIsPickerSessionCurrent(vfPickerSession)) return;
    const fresh = vfPickerDom();
    (fresh && (fresh.search || fresh.close))?.focus();
  });
}

function chooseVideoModel(modelRef) {
  vfChooseVideoModelWithFeedback(modelRef);
}

/**
 * Universal save path with feedback for all picker contexts:
 * Shows Saving… on the chosen row, disables duplicate submissions,
 * checks that unavailable choices cannot be saved, and only closes as
 * successful after the setter persisted the choice. On failure the previous
 * choice is kept and an inline retryable error is shown in the open dialog.
 */
async function vfChooseVideoModelWithFeedback(modelRef) {
  if (!modelRef) return;
  const session = vfPickerSession;
  if (vfPickerSavingRef) return; // disable duplicate submissions

  // Unavailable choices cannot be saved
  const model = vfPickerModelForRef(modelRef);
  if (model) {
    const unavailable = (typeof vfModelPickerContext !== "undefined" && vfModelPickerContext === "voice_flow_polish" && model.polish_supported === false &&
      model.provider !== "antigravity" && model.provider !== "agy") || (model.available === false && model.full_id !== "local/deterministic");
    if (unavailable) return;
  }

  if (modelRef === vfPickerActiveRef()) {
    closeVideoModal("vf-model-picker-modal"); // re-picking the current choice is a no-op
    return;
  }

  vfPickerSavingRef = modelRef;
  renderVideoModelPicker();

  let ok = false;
  let errorMsg = "Couldn't save your choice — the previous selection is still active.";
  try {
    if (vfModelPickerContext === "voice_flow_stt" || vfModelPickerContext === "voice_flow") {
      if (typeof updateExecVoiceFlowPolicy === "function") {
        const res = await updateExecVoiceFlowPolicy(modelRef);
        ok = Boolean(res && res.ok !== false);
        if (res && res.error) errorMsg = res.error;
      } else {
        updateExecVoiceFlowPolicy(modelRef);
        ok = true;
      }
    } else if (vfModelPickerContext === "voice_flow_polish") {
      if (typeof saveVoiceFlowPolishModel === "function") {
        const res = await saveVoiceFlowPolishModel(modelRef);
        ok = Boolean(res && res.ok !== false);
        if (res && res.error) errorMsg = res.error;
      } else {
        saveVoiceFlowPolishModel(modelRef);
        ok = true;
      }
    } else if (vfModelPickerContext === "audio_voice") {
      if (typeof updateExecAudioFlowPolicy === "function") {
        const res = await updateExecAudioFlowPolicy(modelRef);
        ok = Boolean(res && res.ok !== false);
        if (res && res.error) errorMsg = res.error;
      } else {
        updateExecAudioFlowPolicy(modelRef);
        ok = true;
      }
    } else if (vfModelPickerContext === "video_flow_voice") {
      ok = Boolean(await saveVideoFlowVoice(modelRef));
    } else if (vfModelPickerContext === "audio_summary") {
      if (typeof selectAudioSummaryModel === "function") {
        ok = Boolean(await selectAudioSummaryModel(modelRef));
      } else {
        ok = true;
      }
    } else {
      const select = document.getElementById("vf-model-select");
      if (select) select.value = modelRef;
      ok = Boolean(await saveVideoModel(modelRef));
    }
  } catch (error) {
    ok = false;
    if (error && error.message) errorMsg = error.message;
  }

  const stale = !vfIsPickerSessionCurrent(session);
  vfPickerSavingRef = null;
  if (stale) return;

  if (!ok) {
    vfShowPickerStatus("error", errorMsg);
    renderVideoModelPicker();
    return;
  }

  closeVideoModal("vf-model-picker-modal");
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

function vfDetectContentClassification(text, context) {
  const raw = text || "";
  const ctx = typeof context === "string"
    ? context
    : `${context?.task || ""} ${context?.taskType || ""} ${context?.title || ""} ${context?.intent || ""} ${context?.focus || ""} ${context?.visualDirection || ""} ${context?.documentType || ""}`;
  const ctxLower = (ctx || "").toLowerCase();
  const textLower = raw.toLowerCase();

  let techScore = 0;
  let summaryScore = 0;
  let eduScore = 0;
  let narrativeScore = 0;

  const techKws = [
    "api", "apis", "endpoint", "endpoints", "tutorial", "sop", "standard operating procedure",
    "documentation", "reference", "manual", "guide", "sdk", "sdks", "architecture",
    "troubleshooting", "installation", "setup", "configuration", "deployment", "pipeline",
    "schema", "schemas", "json", "yaml", "sql", "git", "cli", "codebase", "function",
    "method", "class", "parameters", "procedure", "protocol", "step-by-step", "walkthrough"
  ];
  const eduKws = [
    "course", "curriculum", "lesson", "lessons", "module", "modules", "study guide",
    "syllabus", "textbook", "quiz", "lecture", "lectures", "homework", "exam",
    "learning objectives", "learning objective", "explainer", "explanation", "walkthrough"
  ];
  const summaryKws = [
    "meeting", "minutes", "meeting minutes", "meeting notes", "summary", "executive summary",
    "action items", "action item", "recap", "standup", "sync", "status report", "digest",
    "tl;dr", "tldr", "agenda", "attendees"
  ];
  const narrativeKws = [
    "cinematic", "documentary", "history", "historical", "story", "storytelling", "narrative",
    "chronicle", "biography", "memoir", "case study", "deep dive", "journey", "epic", "legend"
  ];

  // 1. Context keyword matching (explicit task/title/intent carries high signal)
  if (ctxLower.trim()) {
    for (const kw of techKws) {
      if (new RegExp("\\b" + kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(ctxLower)) techScore += 4;
    }
    for (const kw of summaryKws) {
      if (new RegExp("\\b" + kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(ctxLower)) summaryScore += 4;
    }
    for (const kw of eduKws) {
      if (new RegExp("\\b" + kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(ctxLower)) eduScore += 4;
    }
    for (const kw of narrativeKws) {
      if (new RegExp("\\b" + kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(ctxLower)) narrativeScore += 4;
    }
  }

  // Explicit intent/task_type shortcuts
  const cleanIntent = String(context?.intent || context?.taskType || context?.documentType || "").trim().toLowerCase();
  if (["explainer", "tutorial", "technical", "sop", "guide"].includes(cleanIntent)) techScore += 8;
  else if (["educational", "course", "lesson", "curriculum"].includes(cleanIntent)) eduScore += 8;
  else if (["summary", "brief", "meeting", "digest"].includes(cleanIntent)) summaryScore += 8;
  else if (["cinematic", "narrative", "documentary", "story"].includes(cleanIntent)) narrativeScore += 8;

  // 2. Structural code blocks and inline code
  const codeBlocks = (raw.match(/```|~~~/g) || []).length;
  if (codeBlocks > 0) techScore += Math.min(12, codeBlocks * 3);

  const inlineCode = (raw.match(/`[^`\n]+`/g) || []).length;
  if (inlineCode >= 4) techScore += Math.min(6, Math.floor(inlineCode / 2));

  // 3. Headings check
  const lines = raw.split(/\r?\n/);
  for (let i = 0; i < Math.min(100, lines.length); i++) {
    const l = lines[i].trim();
    if (l.startsWith("#")) {
      const hl = l.toLowerCase();
      if (/api|endpoint|parameter|install|config|sop|guide|tutorial|architecture|troubleshoot|spec|procedure/.test(hl)) techScore += 4;
      if (/meeting|minutes|action item|attendee|agenda|key decision|executive summary|status update/.test(hl)) summaryScore += 4;
      if (/lesson|module|curriculum|syllabus|learning objective|course|lecture|chapter/.test(hl)) eduScore += 4;
      if (/prologue|epilogue|journey|origins|history of|chronicle/.test(hl)) narrativeScore += 4;
    }
  }

  // 4. Syntactic code / API / SOP patterns
  if (/\b(?:GET|POST|PUT|DELETE|PATCH)\s+\/[a-zA-Z0-9_\-/{}]+/i.test(raw)) techScore += 5;
  if (/\b(?:def|class|function|import|export|const|let)\s+[a-zA-Z0-9_]+/.test(raw)) techScore += 4;
  if (/\b(?:curl|npm|pip|docker|kubectl|git)\s+[a-zA-Z0-9_\-]+/.test(raw)) techScore += 4;
  if (/\b(?:SELECT|INSERT|UPDATE|DELETE)\s+.*?\s+FROM\b/i.test(raw)) techScore += 4;
  if (/\b(?:JSON|YAML|REST|GraphQL|SDK|API)\b/.test(raw)) techScore += 4;
  if (/\bStep\s+\d+[:.]/i.test(raw)) techScore += 4;
  if (/\bSOP\b/.test(raw)) techScore += 4;

  // 5. Keywords in document body
  const coreTechTerms = ["api", "endpoint", "parameters", "protocol", "procedure", "tutorial", "sop", "schema", "architecture", "installation", "troubleshooting", "configuration", "deployment", "sdk", "developer", "payload"];
  let techMatches = 0;
  for (const t of coreTechTerms) {
    if (new RegExp("\\b" + t + "\\b").test(textLower)) techMatches++;
  }
  if (techMatches > 0) techScore += Math.min(8, techMatches * 2);

  const coreEduTerms = ["lesson", "module", "curriculum", "syllabus", "lecture", "textbook", "homework", "exam", "learning objective", "prerequisites"];
  let eduMatches = 0;
  for (const t of coreEduTerms) {
    if (new RegExp("\\b" + t + "\\b").test(textLower)) eduMatches++;
  }
  if (eduMatches > 0) eduScore += Math.min(8, eduMatches * 2);

  const coreSumTerms = ["meeting", "minutes", "action items", "agenda", "attendees", "recap", "standup", "tldr"];
  let sumMatches = 0;
  for (const t of coreSumTerms) {
    if (new RegExp("\\b" + t + "\\b").test(textLower)) sumMatches++;
  }
  if (sumMatches > 0) summaryScore += Math.min(8, sumMatches * 2);

  // 6. Bullet density
  const nonEmptyLines = lines.filter(l => l.trim().length > 0);
  if (nonEmptyLines.length > 0) {
    const bulletLines = nonEmptyLines.filter(l => /^[*•\-]|\s*\[[ x]\]/i.test(l.trim())).length;
    if (bulletLines / nonEmptyLines.length > 0.35) summaryScore += 3;
  }

  // 7. Narrative terms
  const narrativeTerms = ["century", "era", "voyage", "expedition", "reign", "empire", "revolution", "biography", "memoir", "story", "narrative", "chronicle", "journey", "epic", "legend", "tales", "characters", "discovered", "traveled", "chronicled", "drama", "legacy", "historical", "dynasty"];
  for (const term of narrativeTerms) {
    if (new RegExp("\\b" + term + "\\b").test(textLower)) narrativeScore += 1;
  }

  // Balanced determination with clear priorities: Technical >= Educational > Summary > Narrative
  const maxScore = Math.max(techScore, eduScore, summaryScore, narrativeScore);
  if (maxScore >= 3) {
    if (techScore === maxScore && techScore > 0) return "technical";
    if (eduScore === maxScore && eduScore > 0) return "educational";
    if (summaryScore === maxScore && summaryScore > 0) return "summary";
    if (narrativeScore === maxScore && narrativeScore >= 2) return "narrative";
    return "general";
  }
  return "general";
}

function vfAnalyzeContentValue(text, context = null) {
  const cleanText = (text || "").trim();
  if (!cleanText) {
    return {
      densityScore: 1.0,
      contentValueRating: "standard",
      conceptCount: 0,
      effectiveWordCount: 0,
      lexicalDiversity: 0.0,
      redundancyScore: 0.0,
      substantiveConcepts: [],
      summaryOfLargeWork: false,
      highConceptDensity: false,
    };
  }

  const words = cleanText.match(/\b[A-Za-z0-9_\-\$%\.]+\b/g) || [];
  const wordCount = words.length;
  if (wordCount === 0) {
    return {
      densityScore: 1.0,
      contentValueRating: "standard",
      conceptCount: 0,
      effectiveWordCount: 0,
      lexicalDiversity: 0.0,
      redundancyScore: 0.0,
      substantiveConcepts: [],
      summaryOfLargeWork: false,
      highConceptDensity: false,
    };
  }

  const hasSentenceTerminator = /[\.!\?](?:\s+|$)/.test(cleanText);
  const hasParaOrHeading = cleanText.includes("\n\n") || /^#{1,6}\s+/m.test(cleanText);
  const isStructured = hasSentenceTerminator || hasParaOrHeading;

  const stopwords = new Set([
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've",
    "were", "weren't", "what", "what's", "when", "when's", "where", "where's",
    "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves"
  ]);

  const substantiveTokens = [];
  const uniqueSubstantive = new Set();
  for (let i = 0; i < words.length; i++) {
    const w = words[i].toLowerCase();
    if (!stopwords.has(w) && w.length > 2 && !/^\d+$/.test(w)) {
      substantiveTokens.push(w);
      uniqueSubstantive.add(w);
    }
  }
  const lexicalDiversity = substantiveTokens.length > 0
    ? uniqueSubstantive.size / substantiveTokens.length
    : 0.5;

  if (!isStructured) {
    return {
      densityScore: 1.0,
      contentValueRating: "standard",
      conceptCount: 1,
      effectiveWordCount: wordCount,
      lexicalDiversity: Math.round(lexicalDiversity * 100) / 100,
      redundancyScore: 0.0,
      substantiveConcepts: [],
      summaryOfLargeWork: false,
      highConceptDensity: false,
    };
  }

  const rawSentences = cleanText
    .split(/(?<=[.!?])\s+(?=[A-Z0-9"'“‘\-\*•])|\n+(?=[-\*•\d+\.]\s+)|\n{2,}/)
    .map(s => s.trim())
    .filter(Boolean);

  const causalRe = /\b(?:because|due to|leads to|leading to|drives|driving|impacts|impacting|results in|resulting in|enables|enabling|causes|causing|triggers|generates|establishes|creates|determines|regulates|influences|mechanism|principle|foundation|consequently|therefore|thus)\b/i;
  const metricRe = /\b(?:\d+(?:\.\d+)?%?|\$\d+|\b(?:19|20)\d{2}\b|\b\d+\s+(?:percent|billion|million|ratio))\b/i;
  const domainRe = /\b(?:election|electoral|voter|ballot|senate|congress|parliament|demographics|turnout|campaign|candidate|coalition|legislative|referendum|constitution|constitutional|reform|policy|policymaker|economic|inflation|fiscal|gdp|monetary|market|geopolitical|framework|architecture|quantum|neural|algorithm|model|hypothesis|synthesis|analysis|investigation|governance|paradigm|propositions?|strategy|strategic|perspective|foundational|pillar|dimension)\b/i;
  const contrastRe = /\b(?:however|whereas|although|compared to|contrast|nevertheless|conversely|alternative|shift|divergence)\b/i;

  const substantiveConcepts = [];
  const seenConceptTokenSets = [];

  for (let i = 0; i < rawSentences.length; i++) {
    const s = rawSentences[i];
    const sWords = s.split(/\s+/).filter(Boolean);
    if (sWords.length < 4) continue;
    const sClean = s.replace(/^#{1,6}\s+|\*\*|\*|_/g, "").trim();
    const sTokens = new Set();
    const sTokenList = sClean.match(/\b[A-Za-z0-9_]+\b/g) || [];
    for (let j = 0; j < sTokenList.length; j++) {
      const tok = sTokenList[j].toLowerCase();
      if (!stopwords.has(tok)) sTokens.add(tok);
    }
    if (sTokens.size < 3) continue;

    const isInformative = causalRe.test(sClean) ||
      metricRe.test(sClean) ||
      domainRe.test(sClean) ||
      contrastRe.test(sClean) ||
      sWords.length >= 10;

    if (!isInformative) continue;

    let isDuplicate = false;
    for (let k = 0; k < seenConceptTokenSets.length; k++) {
      const prevSet = seenConceptTokenSets[k];
      let intersection = 0;
      sTokens.forEach(t => { if (prevSet.has(t)) intersection++; });
      const union = sTokens.size + prevSet.size - intersection;
      const overlap = union > 0 ? intersection / union : 0;
      if (overlap >= 0.60) {
        isDuplicate = true;
        break;
      }
    }

    if (!isDuplicate) {
      substantiveConcepts.push(sClean.slice(0, 220));
      seenConceptTokenSets.push(sTokens);
      if (substantiveConcepts.length >= 12) break;
    }
  }

  const conceptCount = Math.max(1, substantiveConcepts.length);

  let paraRedundancy = 0.0;
  const paras = cleanText.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.split(/\s+/).filter(Boolean).length >= 10);
  if (paras.length >= 2) {
    const paraTokensList = paras.map(p => {
      const toks = new Set();
      const pWords = p.match(/\b[A-Za-z0-9_]+\b/g) || [];
      pWords.forEach(w => {
        const lw = w.toLowerCase();
        if (!stopwords.has(lw)) toks.add(lw);
      });
      return toks;
    });
    let dupCount = 0;
    for (let i = 1; i < paras.length; i++) {
      const curr = paraTokensList[i];
      if (curr.size === 0) continue;
      let isDup = false;
      for (let j = 0; j < i; j++) {
        const prev = paraTokensList[j];
        if (prev.size === 0) continue;
        let inter = 0;
        curr.forEach(t => { if (prev.has(t)) inter++; });
        const uni = curr.size + prev.size - inter;
        if (uni > 0 && inter / uni >= 0.65) {
          isDup = true;
          break;
        }
      }
      if (isDup) dupCount++;
    }
    paraRedundancy = dupCount / paras.length;
  }

  let sentRedundancy = 0.0;
  if (rawSentences.length >= 4) {
    const normSents = rawSentences
      .filter(s => s.split(/\s+/).filter(Boolean).length >= 4)
      .map(s => s.toLowerCase().replace(/[^a-z0-9]/g, ""));
    if (normSents.length > 0) {
      const uniqueS = new Set(normSents).size;
      sentRedundancy = (normSents.length - uniqueS) / normSents.length;
    }
  }

  const redundancyScore = Math.round(Math.max(paraRedundancy, sentRedundancy) * 100) / 100;
  const effectiveWordCount = redundancyScore >= 0.35
    ? Math.max(40, Math.round(wordCount * (1.0 - 0.75 * redundancyScore)))
    : wordCount;

  let ctxStr = "";
  if (typeof context === "string") {
    ctxStr = context.toLowerCase();
  } else if (context && typeof context === "object") {
    ctxStr = [context.focus, context.title, context.task, context.intent, context.visualDirection]
      .filter(Boolean).join(" ").toLowerCase();
  }
  const fullCtx = `${cleanText.slice(0, 1200).toLowerCase()} ${ctxStr}`;
  const summaryOfLargeWork = /\b(?:summary of (?:the |a )?book|book summary|whole book|entire book|chapter-by-chapter|comprehensive (?:summary|review|overview|breakdown)|meta-analysis|condensed breakdown|in-depth synthesis|executive summary of the entire)\b/i.test(fullCtx);
  const hasDenseTopic = domainRe.test(fullCtx);

  const conceptsPer100Words = conceptCount / Math.max(1.0, wordCount / 100.0);
  const highConceptDensity = (conceptCount >= 4 && conceptsPer100Words >= 1.6) ||
    (summaryOfLargeWork && conceptCount >= 3) ||
    (conceptCount >= 5 && wordCount <= 750);

  let densityScore = 1.0;
  let contentValueRating = "standard";

  if (redundancyScore >= 0.50) {
    densityScore = Math.round(Math.max(0.40, 1.0 - redundancyScore * 0.70) * 100) / 100;
    contentValueRating = "low";
  } else {
    let score = 1.0;
    if (summaryOfLargeWork) score += 0.65;
    if (hasDenseTopic) score += 0.30;
    if (highConceptDensity) score += 0.35;
    if (conceptsPer100Words >= 2.0) score += Math.min(0.45, (conceptsPer100Words - 1.8) * 0.30);
    if (lexicalDiversity >= 0.68) score += Math.min(0.30, (lexicalDiversity - 0.65) * 1.2);
    if (conceptCount >= 5 && wordCount <= 600) score += 0.30;
    if (conceptCount >= 8) score += Math.min(0.40, (conceptCount - 7) * 0.10);

    densityScore = Math.round(Math.max(0.70, Math.min(2.80, score)) * 100) / 100;
    if (densityScore >= 1.70) contentValueRating = "very_high";
    else if (densityScore >= 1.30) contentValueRating = "high";
    else if (densityScore < 0.80) contentValueRating = "low";
    else contentValueRating = "standard";
  }

  return {
    densityScore,
    contentValueRating,
    conceptCount,
    effectiveWordCount,
    lexicalDiversity: Math.round(lexicalDiversity * 100) / 100,
    redundancyScore,
    substantiveConcepts,
    summaryOfLargeWork,
    highConceptDensity,
  };
}

function calculateDocumentScaling(text, requestedFormat = null, context = null) {
  const trimmed = (text || "").trim();
  const words = trimmed ? trimmed.split(/\s+/).filter(Boolean).length : 0;
  const chars = text ? text.length : 0;
  const pageCount = words > 0 ? Math.max(1, Math.round(words / 270)) : 0;

  if (words === 0) {
    let emptyTarget = 90;
    let emptyFormat = "brief";
    const cleanReq = (requestedFormat || "").trim().toLowerCase();
    if (cleanReq === "short") { emptyTarget = 45; emptyFormat = "short"; }
    else if (cleanReq === "brief") { emptyTarget = 60; emptyFormat = "brief"; }
    else if (cleanReq === "explainer") { emptyTarget = 120; emptyFormat = "explainer"; }
    else if (cleanReq === "cinematic") { emptyTarget = 150; emptyFormat = "cinematic"; }
    return {
      wordCount: 0,
      charCount: 0,
      pageCount: 0,
      sectionCount: 0,
      targetSeconds: emptyTarget,
      targetFormatted: vfFormatDurationLabel(emptyTarget),
      briefSeconds: 60,
      shortSeconds: 75,
      explainerSeconds: 120,
      cinematicSeconds: 150,
      resolvedFormat: emptyFormat,
      densityScore: 1.0,
      contentValueRating: "standard",
      conceptCount: 0,
      effectiveWordCount: 0,
      redundancyScore: 0.0,
      substantiveConcepts: [],
    };
  }

  let sectionCount = 0;
  if (trimmed) {
    const headingMatches = trimmed.match(/^(?:#{1,6}\s+|(?:\d+\.|\bStep\s+\d+[:.]|\bSection\s+\d+)\s+|\*\*[^*]+\*\*$)/gim);
    sectionCount = headingMatches ? headingMatches.length : (trimmed.includes("\n\n") ? trimmed.split(/\n\s*\n/).filter(Boolean).length : 1);
  }

  // Self-contained fallback analyzer ensuring safe execution in sandboxes
  function _internalAnalyze(rawText, ctx) {
    const cText = (rawText || "").trim();
    if (!cText) {
      return { densityScore: 1.0, contentValueRating: "standard", conceptCount: 0, effectiveWordCount: 0, lexicalDiversity: 0.0, redundancyScore: 0.0, substantiveConcepts: [], summaryOfLargeWork: false, highConceptDensity: false };
    }
    const wList = cText.match(/\b[A-Za-z0-9_\-\$%\.]+\b/g) || [];
    const wCount = wList.length;
    const hasTerm = /[\.!\?](?:\s+|$)/.test(cText);
    const hasStructure = hasTerm || cText.includes("\n\n") || /^#{1,6}\s+/m.test(cText);
    if (!hasStructure) {
      return { densityScore: 1.0, contentValueRating: "standard", conceptCount: 1, effectiveWordCount: wCount, lexicalDiversity: 0.5, redundancyScore: 0.0, substantiveConcepts: [], summaryOfLargeWork: false, highConceptDensity: false };
    }
    const stops = new Set(["a", "about", "all", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what", "with"]);
    const sents = cText.split(/(?<=[.!?])\s+(?=[A-Z0-9"'“‘])|\n{2,}/).map(s => s.trim()).filter(Boolean);
    const dRe = /\b(?:election|electoral|voter|ballot|senate|congress|parliament|demographics|turnout|campaign|candidate|coalition|reform|policy|policymaker|economic|inflation|fiscal|gdp|architecture|neural|algorithm|model|governance|propositions?)\b/i;
    const mRe = /\b(?:\d+(?:\.\d+)?%?|\$\d+|\b(?:19|20)\d{2}\b|\b\d+\s+(?:percent|billion|million))\b/i;
    const cRe = /\b(?:because|due to|leads to|drives|results in|causes|triggers|establishes|creates|consequently|therefore|thus)\b/i;
    const concepts = [];
    const seenSets = [];
    for (let i = 0; i < sents.length; i++) {
      const s = sents[i];
      const sTokens = new Set((s.match(/\b[A-Za-z0-9_]+\b/g) || []).map(t => t.toLowerCase()).filter(t => !stops.has(t)));
      if (sTokens.size < 3) continue;
      if (!(dRe.test(s) || mRe.test(s) || cRe.test(s) || s.split(/\s+/).length >= 12)) continue;
      let dup = false;
      for (let k = 0; k < seenSets.length; k++) {
        let inter = 0;
        sTokens.forEach(t => { if (seenSets[k].has(t)) inter++; });
        const uni = sTokens.size + seenSets[k].size - inter;
        if (uni > 0 && inter / uni >= 0.60) { dup = true; break; }
      }
      if (!dup) { concepts.push(s.slice(0, 220)); seenSets.push(sTokens); if (concepts.length >= 12) break; }
    }
    const cCount = Math.max(1, concepts.length);
    let pRed = 0.0;
    const pList = cText.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.split(/\s+/).length >= 10);
    if (pList.length >= 2) {
      const pSets = pList.map(p => new Set((p.match(/\b[A-Za-z0-9_]+\b/g) || []).map(t => t.toLowerCase()).filter(t => !stops.has(t))));
      let dCount = 0;
      for (let i = 1; i < pList.length; i++) {
        for (let j = 0; j < i; j++) {
          let inter = 0;
          pSets[i].forEach(t => { if (pSets[j].has(t)) inter++; });
          const uni = pSets[i].size + pSets[j].size - inter;
          if (uni > 0 && inter / uni >= 0.65) { dCount++; break; }
        }
      }
      pRed = dCount / pList.length;
    }
    let sRed = 0.0;
    if (sents.length >= 4) {
      const norm = sents.map(s => s.toLowerCase().replace(/[^a-z0-9]/g, "")).filter(Boolean);
      sRed = (norm.length - new Set(norm).size) / norm.length;
    }
    const redScore = Math.round(Math.max(pRed, sRed) * 100) / 100;
    const effW = redScore >= 0.35 ? Math.max(40, Math.round(wCount * (1.0 - 0.75 * redScore))) : wCount;
    let ctxString = "";
    if (typeof ctx === "string") ctxString = ctx.toLowerCase();
    else if (ctx && typeof ctx === "object") ctxString = [ctx.focus, ctx.title, ctx.task, ctx.intent, ctx.visualDirection].filter(Boolean).join(" ").toLowerCase();
    const fullContext = `${cText.slice(0, 1200).toLowerCase()} ${ctxString}`;
    const isBookSum = /\b(?:summary of (?:the |a )?book|book summary|whole book|entire book|chapter-by-chapter|comprehensive (?:summary|review|overview|breakdown)|meta-analysis|condensed breakdown|in-depth synthesis|executive summary of the entire)\b/i.test(fullContext);
    const hasTopic = dRe.test(fullContext);
    const cPer100 = cCount / Math.max(1.0, wCount / 100.0);
    const highDensity = (cCount >= 4 && cPer100 >= 1.6) || (isBookSum && cCount >= 3) || (cCount >= 5 && wCount <= 750);
    let dScore = 1.0;
    let rating = "standard";
    if (redScore >= 0.50) {
      dScore = Math.round(Math.max(0.40, 1.0 - redScore * 0.70) * 100) / 100;
      rating = "low";
    } else {
      let sc = 1.0;
      if (isBookSum) sc += 0.65;
      if (hasTopic) sc += 0.30;
      if (highDensity) sc += 0.35;
      if (cPer100 >= 2.0) sc += Math.min(0.45, (cPer100 - 1.8) * 0.30);
      if (cCount >= 5 && wCount <= 600) sc += 0.30;
      dScore = Math.round(Math.max(0.70, Math.min(2.80, sc)) * 100) / 100;
      if (dScore >= 1.70) rating = "very_high";
      else if (dScore >= 1.30) rating = "high";
      else if (dScore < 0.80) rating = "low";
    }
    return { densityScore: dScore, contentValueRating: rating, conceptCount: cCount, effectiveWordCount: effW, lexicalDiversity: 0.5, redundancyScore: redScore, substantiveConcepts: concepts, summaryOfLargeWork: isBookSum, highConceptDensity: highDensity };
  }

  const contentVal = (typeof vfAnalyzeContentValue === "function")
    ? vfAnalyzeContentValue(text, context)
    : _internalAnalyze(text, context);

  const effWords = contentVal.effectiveWordCount || words;
  const densityScore = contentVal.densityScore || 1.0;
  const conceptCount = contentVal.conceptCount || 1;
  const redundancyScore = contentVal.redundancyScore || 0.0;

  // Base format durations
  let briefSeconds;
  if (effWords <= 270) {
    briefSeconds = 45;
  } else if (effWords <= 1350) {
    briefSeconds = Math.min(120, Math.round(45 + (effWords - 270) * (75.0 / 1080)));
  } else {
    briefSeconds = 120;
  }

  let shortSeconds;
  if (effWords <= 150) {
    const ratio_s = effWords > 0 ? effWords / 150.0 : 0;
    shortSeconds = Math.max(30, Math.round(30 + ratio_s * 15));
  } else if (effWords <= 270) {
    shortSeconds = 50;
  } else if (effWords <= 1350) {
    shortSeconds = Math.min(150, Math.round(50 + (effWords - 270) * (100.0 / 1080)));
  } else {
    shortSeconds = 150;
  }

  let explainerSeconds;
  if (effWords <= 270) {
    explainerSeconds = 75;
  } else if (effWords <= 1350) {
    explainerSeconds = Math.min(240, Math.round(75 + (effWords - 270) * (165.0 / 1080)));
  } else {
    explainerSeconds = 240;
  }

  let cinematicSeconds;
  if (effWords <= 300) {
    cinematicSeconds = 60;
  } else if (effWords <= 1350) {
    cinematicSeconds = Math.min(240, Math.round(60 + (effWords - 300) * (180.0 / 1050)));
  } else {
    cinematicSeconds = Math.min(300, Math.round(240 + (effWords - 1350) * 0.05));
  }

  // Section Breathing Room:
  if (sectionCount >= 2) {
    shortSeconds = Math.min(150, Math.max(shortSeconds, sectionCount * 12));
    briefSeconds = Math.min(120, Math.max(briefSeconds, sectionCount * 14));
    explainerSeconds = Math.min(240, Math.max(explainerSeconds, sectionCount * 20));
    cinematicSeconds = Math.min(300, Math.max(cinematicSeconds, sectionCount * 25));
  }

  // Concept Breathing Room:
  if (conceptCount >= 2 && redundancyScore < 0.50) {
    shortSeconds = Math.min(150, Math.max(shortSeconds, conceptCount * 12));
    briefSeconds = Math.min(120, Math.max(briefSeconds, conceptCount * 15));
    explainerSeconds = Math.min(240, Math.max(explainerSeconds, conceptCount * 22));
    cinematicSeconds = Math.min(300, Math.max(cinematicSeconds, conceptCount * 28));
  }

  // Density Scaling Factor:
  if (densityScore > 1.15) {
    const multiplier = 1.0 + (densityScore - 1.0) * 0.85;
    explainerSeconds = Math.min(240, Math.max(explainerSeconds, Math.round(explainerSeconds * multiplier)));
    cinematicSeconds = Math.min(300, Math.max(cinematicSeconds, Math.round(cinematicSeconds * multiplier)));
    briefSeconds = Math.min(120, Math.max(briefSeconds, Math.round(briefSeconds * multiplier)));
    shortSeconds = Math.min(150, Math.max(shortSeconds, Math.round(shortSeconds * multiplier)));
  } else if (densityScore < 0.8) {
    const compRatio = Math.max(0.45, densityScore);
    briefSeconds = Math.max(30, Math.round(briefSeconds * compRatio));
    shortSeconds = Math.max(30, Math.round(shortSeconds * compRatio));
    explainerSeconds = Math.max(45, Math.round(explainerSeconds * compRatio));
    cinematicSeconds = Math.max(60, Math.round(cinematicSeconds * compRatio));
  }

  let targetSeconds;
  let resolvedFormat;
  const cleanReq = (requestedFormat || "").trim().toLowerCase();
  const isAuto = !cleanReq || cleanReq === "auto" || cleanReq === "auto-adaptive" || cleanReq === "default";

  if (!isAuto) {
    if (cleanReq === "brief") {
      targetSeconds = briefSeconds;
      resolvedFormat = "brief";
    } else if (cleanReq === "short") {
      targetSeconds = shortSeconds;
      resolvedFormat = "short";
    } else if (cleanReq === "explainer") {
      targetSeconds = explainerSeconds;
      resolvedFormat = "explainer";
    } else if (cleanReq === "cinematic") {
      targetSeconds = cinematicSeconds;
      resolvedFormat = "cinematic";
    } else {
      targetSeconds = briefSeconds;
      resolvedFormat = "brief";
    }
  } else {
    const isDenseDoc = (densityScore >= 1.4 && conceptCount >= 4) ||
      (contentVal.summaryOfLargeWork && conceptCount >= 3) ||
      contentVal.highConceptDensity;
    const isRedundantDoc = redundancyScore >= 0.50;

    if (isDenseDoc) {
      const cType = typeof vfDetectContentClassification === "function"
        ? vfDetectContentClassification(text, context)
        : "general";
      if (cType === "narrative" || contentVal.summaryOfLargeWork) {
        targetSeconds = Math.min(300, Math.max(180, Math.round(140 * densityScore)));
        resolvedFormat = "cinematic";
      } else {
        targetSeconds = Math.min(240, Math.max(150, Math.round(120 * densityScore)));
        resolvedFormat = "explainer";
      }
    } else if (words < 150) {
      targetSeconds = words > 0 ? Math.max(30, Math.round(30 + (words / 150.0) * 15)) : 90;
      resolvedFormat = words > 0 ? "short" : "brief";
    } else if (words <= 300) {
      targetSeconds = 50;
      resolvedFormat = "brief";
    } else if (words <= 600) {
      targetSeconds = Math.round(60 + (words - 300) * (30.0 / 240));
      if (words === 540) targetSeconds = 90;
      resolvedFormat = words <= 500 ? "brief" : "explainer";
    } else if (words <= 1400) {
      targetSeconds = Math.round(90 + (words - 600) * (60.0 / 800));
      resolvedFormat = "explainer";
    } else if (words <= 2500) {
      targetSeconds = Math.round(150 + (words - 1400) * (60.0 / 1100));
      resolvedFormat = "explainer";
    } else {
      const detected = typeof vfDetectContentClassification === "function"
        ? vfDetectContentClassification(text, context)
        : "general";

      if (detected === "technical" || detected === "educational") {
        targetSeconds = 240;
        resolvedFormat = "explainer";
      } else if (detected === "summary") {
        targetSeconds = 120;
        resolvedFormat = "brief";
      } else if (isRedundantDoc) {
        targetSeconds = Math.min(120, Math.max(60, Math.round(60 + (contentVal.effectiveWordCount / 500.0) * 30)));
        resolvedFormat = "brief";
      } else {
        targetSeconds = 300;
        resolvedFormat = "cinematic";
      }
    }

    if (sectionCount >= 2) {
      if (resolvedFormat === "short") {
        targetSeconds = Math.min(150, Math.max(targetSeconds, shortSeconds));
      } else if (resolvedFormat === "brief") {
        targetSeconds = Math.min(120, Math.max(targetSeconds, briefSeconds));
      } else if (resolvedFormat === "explainer") {
        targetSeconds = Math.min(240, Math.max(targetSeconds, explainerSeconds));
      } else if (resolvedFormat === "cinematic") {
        targetSeconds = Math.min(300, Math.max(targetSeconds, cinematicSeconds));
      }
    }

    if (conceptCount >= 2 && !isRedundantDoc) {
      if (resolvedFormat === "explainer") {
        targetSeconds = Math.min(240, Math.max(targetSeconds, conceptCount * 22));
      } else if (resolvedFormat === "cinematic") {
        targetSeconds = Math.min(300, Math.max(targetSeconds, conceptCount * 28));
      }
    }
  }

  targetSeconds = Math.max(30, Math.min(300, targetSeconds));

  const mins = Math.floor(targetSeconds / 60);
  const secs = targetSeconds % 60;
  const targetFormatted = mins > 0 && secs > 0 ? `${mins}m ${secs}s` : (mins > 0 ? `${mins} min` : `${secs}s`);

  return {
    wordCount: words,
    charCount: chars,
    pageCount: pageCount,
    sectionCount: sectionCount,
    targetSeconds: targetSeconds,
    targetFormatted: targetFormatted,
    briefSeconds: briefSeconds,
    shortSeconds: shortSeconds,
    explainerSeconds: explainerSeconds,
    cinematicSeconds: cinematicSeconds,
    resolvedFormat: resolvedFormat,
    densityScore: densityScore,
    contentValueRating: contentVal.contentValueRating,
    conceptCount: conceptCount,
    effectiveWordCount: effWords,
    redundancyScore: redundancyScore,
    substantiveConcepts: contentVal.substantiveConcepts,
  };
}

function vfFormatDurationLabel(seconds, isMax = false) {
  const s = Math.max(1, Math.round(seconds));
  let str;
  if (s < 60) {
    str = `~${s}s`;
  } else {
    const mins = Math.floor(s / 60);
    const rem = s % 60;
    str = rem > 0 ? `~${mins}m ${rem}s` : `~${mins} min`;
  }
  if (isMax && s >= 300) {
    return `${str} Max`;
  }
  return str;
}

function applyDocumentProfile(stats) {
  if (!stats) return;
  vfCurrentDocStats = stats;

  const pageStr = stats.wordCount > 0
    ? `${stats.pageCount} page${stats.pageCount === 1 ? "" : "s"} (~${stats.wordCount.toLocaleString()} words)`
    : "0 pages (~0 words)";
  const targetStr = stats.targetFormatted ? `~${stats.targetFormatted}` : "~1m 30s";

  // Document-analysis banner removed from the UI; stats remain available
  // via vfCurrentDocStats for format auto-scaling logic.

  // Update format speed pills
  const pillAuto = document.getElementById("vf-speed-pill-auto");
  const pillBrief = document.getElementById("vf-speed-pill-brief");
  const pillShort = document.getElementById("vf-speed-pill-short");
  const pillExplainer = document.getElementById("vf-speed-pill-explainer");
  const pillCinematic = document.getElementById("vf-speed-pill-cinematic");

  if (stats.wordCount > 0) {
    if (pillAuto) pillAuto.textContent = `~${vfFormatDurationLabel(stats.targetSeconds)}`;
    if (pillBrief) pillBrief.textContent = `~${vfFormatDurationLabel(stats.briefSeconds)}`;
    if (pillShort) pillShort.textContent = `~${vfFormatDurationLabel(stats.shortSeconds)}`;
    if (pillExplainer) pillExplainer.textContent = `~${vfFormatDurationLabel(stats.explainerSeconds)}`;
    if (pillCinematic) pillCinematic.textContent = `~${vfFormatDurationLabel(stats.cinematicSeconds)}`;
  } else {
    // Estimates appear after content is added; avoid repeating each card's title.
    for (const pill of [pillAuto, pillBrief, pillShort, pillExplainer, pillCinematic]) {
      if (pill) pill.textContent = "";
    }
  }

  vfUpdateEstimateNote(stats);
  updateFormatSpeedNotice(vfSelectedFormat);
}

/**
 * Shows the app-provided duration resolution as one factual estimate,
 * explicitly labeled as estimated video length (not generation time). Only
 * shown when the app actually computed one (content present); no hard
 * "max" guarantees are claimed.
 */
function vfUpdateEstimateNote(stats) {
  const legacyBanner = document.getElementById("vf-doc-profile-banner");
  if (legacyBanner) legacyBanner.classList.add("hidden");
  let note = document.getElementById("vf-estimate-note");
  if (!stats || !stats.wordCount || !stats.targetFormatted) {
    if (note) note.remove();
    return;
  }
  if (!note) {
    note = document.createElement("p");
    note.id = "vf-estimate-note";
    note.className = "vf-estimate-note";
    const badge = document.getElementById("vf-format-speed-badge");
    if (badge && badge.parentElement) {
      badge.parentElement.insertBefore(note, badge);
    } else {
      const section = document.querySelector(".vf-format-section");
      (section || document.body).appendChild(note);
    }
  }
  note.textContent = `Estimated video length: ${stats.targetFormatted} (how long the finished video will be — not how long it takes to create).`;
}

async function analyzeSourceDocument(immediate = false) {
  const sourceInput = document.getElementById("vf-source-input");
  const text = sourceInput ? sourceInput.value : "";
  const focusInput = document.getElementById("vf-nlm-focus-input") || document.getElementById("vf-visual-direction");
  const titleInput = document.getElementById("vf-title-input");
  const focus = focusInput ? focusInput.value : "";
  const title = titleInput ? titleInput.value : "";
  const localStats = calculateDocumentScaling(text, vfSelectedFormat, { focus, title });
  applyDocumentProfile(localStats);

  if (text && text.trim()) {
    try {
      const data = await safeFetchJson("/api/video-flow/analyze-source", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_text: text,
          requested_format: vfSelectedFormat,
          focus: focus,
          title: title,
        }),
      });
      if (data && data.success) {
        const mergedStats = {
          ...localStats,
          wordCount: data.word_count ?? localStats.wordCount,
          pageCount: data.page_count ?? localStats.pageCount,
          charCount: data.char_count ?? localStats.charCount,
          sectionCount: data.section_count ?? localStats.sectionCount,
          sections: data.sections ?? localStats.sections ?? [],
          targetSeconds: data.target_seconds ?? localStats.targetSeconds,
          targetFormatted: data.target_formatted ?? localStats.targetFormatted,
          briefSeconds: data.brief_seconds ?? localStats.briefSeconds,
          shortSeconds: data.short_seconds ?? localStats.shortSeconds,
          explainerSeconds: data.explainer_seconds ?? localStats.explainerSeconds,
          cinematicSeconds: data.cinematic_seconds ?? localStats.cinematicSeconds,
          resolvedFormat: data.resolved_format ?? localStats.resolvedFormat,
          densityScore: data.density_score ?? localStats.densityScore ?? 1.0,
          contentValueRating: data.content_value_rating ?? localStats.contentValueRating ?? "standard",
          conceptCount: data.concept_count ?? localStats.conceptCount ?? 1,
          effectiveWordCount: data.effective_word_count ?? localStats.effectiveWordCount ?? (data.word_count ?? localStats.wordCount),
          redundancyScore: data.redundancy_score ?? localStats.redundancyScore ?? 0.0,
          substantiveConcepts: data.substantive_concepts ?? localStats.substantiveConcepts ?? [],
        };
        applyDocumentProfile(mergedStats);
      }
    } catch {
      // Offline fallback: localStats already applied cleanly
    }
  }
}

function scheduleSourceAnalysis(delayMs = 250) {
  if (vfAnalyzeSourceDebounceTimer) {
    clearTimeout(vfAnalyzeSourceDebounceTimer);
  }
  const sourceInput = document.getElementById("vf-source-input");
  const text = sourceInput ? sourceInput.value : "";
  const focusInput = document.getElementById("vf-nlm-focus-input") || document.getElementById("vf-visual-direction");
  const titleInput = document.getElementById("vf-title-input");
  const focus = focusInput ? focusInput.value : "";
  const title = titleInput ? titleInput.value : "";
  applyDocumentProfile(calculateDocumentScaling(text, vfSelectedFormat, { focus, title }));

  if (delayMs <= 0) {
    analyzeSourceDocument(true);
  } else {
    vfAnalyzeSourceDebounceTimer = setTimeout(() => {
      analyzeSourceDocument(false);
    }, delayMs);
  }
}

function updateVideoSourceCount() {
  const input = document.getElementById("vf-source-input");
  const counter = document.getElementById("vf-source-counter");
  if (input && counter) counter.textContent = `${input.value.length.toLocaleString()} characters`;
  scheduleSourceAnalysis(250);
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
      const data = await safeFetchJson("/api/video-flow/documents/extract", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({file_name: file.name, content_base64: String(dataUrl).split(",", 2)[1]}),
      });
      if (!data || !data.success) throw new Error(data?.error || "Could not extract document text.");
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
function selectVideoEngine(engine) {
  vfSelectedEngine = engine;
  document.querySelectorAll(".vf-engine-card").forEach(card => {
    card.classList.toggle("active", card.dataset.engine === engine);
  });
  const radio = document.querySelector(`input[name="vf-engine-choice"][value="${engine}"]`);
  if (radio) radio.checked = true;

  const nlmGroup = document.getElementById("vf-notebooklm-options-group");
  const nativeGroup = document.getElementById("vf-native-options-group");
  const appEngineSettings = document.getElementById("vf-app-engine-settings");
  const button = document.getElementById("vf-generate-button");
  const subtext = document.getElementById("vf-generate-subtext");

  if (engine === "notebooklm") {
    if (nlmGroup) nlmGroup.classList.remove("hidden");
    if (nativeGroup) nativeGroup.classList.add("hidden");
    // Planning-model / narration / native-mode controls do not participate in
    // the NotebookLM request branch — keep the whole disclosure off this path.
    // It is only hidden, never rebuilt, so stored values survive the switch.
    if (appEngineSettings) {
      appEngineSettings.classList.add("hidden");
      appEngineSettings.hidden = true;
    }
    if (button) {
      const strong = button.querySelector("strong");
      if (strong) strong.textContent = "Create video";
    }
    if (subtext) subtext.textContent = "Renders with NotebookLM in the cloud and gives you an MP4";
  } else {
    if (nlmGroup) nlmGroup.classList.add("hidden");
    if (nativeGroup) nativeGroup.classList.remove("hidden");
    if (appEngineSettings) {
      appEngineSettings.classList.remove("hidden");
      appEngineSettings.hidden = false;
    }
    if (button) {
      const strong = button.querySelector("strong");
      if (strong) strong.textContent = "Create video";
    }
    if (subtext) subtext.textContent = "Renders on this PC with your planning model";
  }
}

function selectNotebookLMFormat(format) {
  vfSelectedFormat = format;
  document.querySelectorAll(".vf-format-card").forEach(card => {
    card.classList.toggle("active", card.dataset.format === format);
  });
  const radio = document.querySelector(`input[name="vf-nlm-format"][value="${format}"]`);
  if (radio) radio.checked = true;

  const styleSection = document.getElementById("vf-nlm-style-section");
  const customStyleWrap = document.getElementById("vf-nlm-custom-style-wrap");

  if (styleSection) styleSection.classList.remove("hidden");
  const currentStyle = document.getElementById("vf-nlm-style-select")?.value || "auto";
  if (customStyleWrap) {
    customStyleWrap.classList.toggle("hidden", currentStyle !== "custom");
  }

  updateFormatSpeedNotice(format);
  scheduleSourceAnalysis(0);
}

function updateFormatSpeedNotice(format) {
  const badge = document.getElementById("vf-format-speed-badge");
  if (!badge) return;
  if (format === "short") {
    badge.classList.remove("hidden");
    badge.className = "vf-speed-guidance-badge vf-shorts-guidance-banner";
    badge.innerHTML = `
      <span class="vf-shorts-guidance-icon">📱</span>
      <div class="vf-shorts-guidance-text">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <strong>9:16 Vertical Shorts Mode Active</strong>
          <span class="vf-shorts-platform-chips">
            <span class="vf-platform-chip">YouTube Shorts</span>
            <span class="vf-platform-chip">Reels</span>
            <span class="vf-platform-chip">TikTok</span>
          </span>
        </div>
        <span>Optimized for full-screen vertical mobile playback with high-impact kinetic visuals and brisk pacing.</span>
      </div>
    `;
  } else if (vfCurrentDocStats && vfCurrentDocStats.wordCount > 0 && (vfCurrentDocStats.densityScore >= 1.35 || vfCurrentDocStats.conceptCount >= 4)) {
    badge.classList.remove("hidden");
    badge.className = "vf-speed-guidance-badge vf-density-guidance-banner";
    const cCount = vfCurrentDocStats.conceptCount || 1;
    badge.innerHTML = `
      <span class="vf-shorts-guidance-icon">⚡</span>
      <div class="vf-shorts-guidance-text">
        <strong>High Information Density (${cCount} core propositions)</strong>
        <span>Video duration and narrative pacing auto-scaled to thoroughly explain key concepts without rushing.</span>
      </div>
    `;
  } else if (vfCurrentDocStats && vfCurrentDocStats.wordCount > 0 && vfCurrentDocStats.redundancyScore >= 0.50) {
    badge.classList.remove("hidden");
    badge.className = "vf-speed-guidance-badge vf-density-guidance-banner";
    badge.innerHTML = `
      <span class="vf-shorts-guidance-icon">ℹ️</span>
      <div class="vf-shorts-guidance-text">
        <strong>Repetitive Content Detected</strong>
        <span>Video duration auto-compressed to avoid redundant scenes and keep narrative concise.</span>
      </div>
    `;
  } else {
    badge.classList.add("hidden");
    badge.innerHTML = "";
  }
}

function onNotebookLMStyleChange(style) {
  vfSelectedStyle = style;
  const customStyleWrap = document.getElementById("vf-nlm-custom-style-wrap");
  if (customStyleWrap) {
    customStyleWrap.classList.toggle("hidden", style !== "custom");
    if (style === "custom") {
      // Reveal the field before focusing it when creative options are collapsed.
      const disclosure = customStyleWrap.closest("details");
      if (disclosure) disclosure.open = true;
      document.getElementById("vf-nlm-custom-style-prompt")?.focus();
    }
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
  if (button && vfSelectedEngine === "native") {
    const strong = button.querySelector("strong");
    if (strong) strong.textContent = "Create video";
  }
}

let vfActiveVideoId = null;
let vfStepperHideTimer = null;

function vfSetCancelButtonVisibility(visible) {
  const stepperCancel = document.getElementById("vf-stepper-cancel-btn");
  const cardCancel = document.getElementById("vf-cancel-generation-btn");
  if (stepperCancel) stepperCancel.style.display = visible ? "inline-flex" : "none";
  if (cardCancel) cardCancel.style.display = visible ? "flex" : "none";
}

async function cancelActiveVideoGeneration() {
  const targetId = vfActiveVideoId || (vfVideos.find(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status))?.id);
  const cardCancel = document.getElementById("vf-cancel-generation-btn");
  const stepperCancel = document.getElementById("vf-stepper-cancel-btn");
  const cardCancelStrong = cardCancel ? cardCancel.querySelector("strong") : null;
  const cardCancelRestore = cardCancelStrong ? cardCancelStrong.textContent : "";
  if (cardCancel) cardCancel.disabled = true;
  if (stepperCancel) stepperCancel.disabled = true;
  // Acknowledgement copy stays until the backend confirms (or refuses) the
  // cancellation request.
  if (stepperCancel) stepperCancel.textContent = "Cancelling…";
  if (cardCancelStrong) cardCancelStrong.textContent = "Cancelling…";

  try {
    const data = await safeFetchJson("/api/video-flow/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: targetId || undefined }),
    });

    if (!data || !data.success) {
      throw new Error(data?.error || "Could not cancel generation.");
    }

    vfToast("Video generation cancelled.");
    const cancelledId = targetId || data.id || vfActiveVideoId;
    if (cancelledId && Array.isArray(vfVideos)) {
      const v = vfVideos.find(item => item.id === cancelledId);
      if (v) {
        v.status = "cancelled";
        v.stage = "Cancelled";
      }
      renderVideoHistory();
    }
    vfActiveVideoId = null;
    vfStopLiveStopwatch();
    vfSetCancelButtonVisibility(false);

    updateGenerationStepper({
      id: cancelledId || "current",
      status: "cancelled",
    });

    const genBtn = document.getElementById("vf-generate-button");
    if (genBtn) genBtn.disabled = false;

    scheduleVideoFlowPolling(true);
  } catch (err) {
    vfToast(err.message || "Failed to cancel video generation.", true);
    updateGenerationStepper(vfVideos.find(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status)) || null);
  } finally {
    if (cardCancel) cardCancel.disabled = false;
    if (stepperCancel) stepperCancel.disabled = false;
    if (stepperCancel) stepperCancel.textContent = "✕ Cancel";
    if (cardCancelStrong) cardCancelStrong.textContent = cardCancelRestore || "Cancel Video Generation";
  }
}

// ---------------------------------------------------------------------------
// Generation status (plan section 7). Existing backend states map onto four
// friendly steps without changing polling or inventing percentages.
// ---------------------------------------------------------------------------

const VF_PHASE_LABELS = {
  preparing: "Preparing",
  creating: "Creating video",
  finishing: "Finishing",
  ready: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
};

function vfIsVideoComplete(video) {
  return video.status === "completed" || video.status === "complete" ||
    video.status === "ready" || Boolean(video.playable);
}

/**
 * Maps a backend job onto a friendly phase. Stages/progress thresholds mirror
 * the existing stepper logic (>=85 finishing, >=25 creating) so nothing new
 * is claimed about the backend.
 */
function vfJobPhase(video) {
  const status = String(video.status || "").toLowerCase();
  if (vfIsVideoComplete(video)) return "ready";
  if (status === "cancelled") return "cancelled";
  if (status === "failed") return "failed";
  const progress = Math.max(0, Math.min(100, Math.round(Number(video.progress || 0))));
  const stage = String(video.stage || "").toLowerCase();
  const stepKey = String(video.step || video.phase || "").toLowerCase();
  if (progress >= 85 || stepKey === "video_download" || stepKey === "download" ||
      stage.includes("download") || stage.includes("normaliz")) return "finishing";
  if (progress >= 25 || stepKey === "video_poll" || stepKey === "generate" ||
      stage.includes("cloud") || stage.includes("generat") || stage.includes("overview") ||
      stage.includes("video_poll")) return "creating";
  return "preparing";
}

function vfPhaseStepKey(video, phase) {
  if (phase === "ready") return "ready";
  if (phase === "finishing") return "video_download";
  if (phase === "creating") return "video_poll";
  const stepKey = String(video.step || video.phase || "").toLowerCase();
  const stage = String(video.stage || "").toLowerCase();
  if (stepKey === "notebook_create" || stage.includes("notebook")) return "notebook_create";
  if (stepKey === "source_add" || stage.includes("upload") || stage.includes("source") || stage.includes("index")) return "source_add";
  return "auth_check";
}

function vfSetStepperIndeterminate(indeterminate) {
  const track = document.querySelector("#vf-generation-stepper .vf-stepper-bar-track");
  const fill = document.getElementById("vf-stepper-bar-fill");
  if (track) track.classList.toggle("indeterminate", Boolean(indeterminate));
  if (fill && indeterminate) fill.style.width = "";
}

/**
 * Writes the friendly step label. #vf-status-step-label (contract) wraps the
 * legacy #vf-stepper-title span; write the innermost text node so both ids
 * keep working regardless of the current nesting.
 */
function vfSetStatusStepLabel(text) {
  const legacy = document.getElementById("vf-stepper-title");
  if (legacy) {
    legacy.textContent = text;
    return;
  }
  const outer = document.getElementById("vf-status-step-label");
  if (outer) outer.textContent = text;
}

function vfSetStepperActiveKey(key) {
  const steps = document.querySelectorAll("#vf-stepper-steps .vf-step");
  if (!steps.length) return;
  const wanted = String(key || "").toLowerCase();
  const keys = Array.from(steps).map(step => String(step.dataset.step || "").toLowerCase());
  let activeIdx = keys.indexOf(wanted);
  if (activeIdx < 0) activeIdx = 0;
  steps.forEach((step, idx) => {
    step.classList.remove("active", "done", "error");
    if (idx < activeIdx) step.classList.add("done");
    else if (idx === activeIdx) step.classList.add("active");
  });
}

/** Raw backend stage text goes under Details, never through innerHTML. */
function vfUpdateStatusStageDetail(text) {
  const details = document.getElementById("vf-status-details");
  if (!details) return;
  let line = document.getElementById("vf-status-stage-detail");
  const value = text ? String(text) : "";
  if (!value) {
    if (line) line.remove();
    return;
  }
  if (!line) {
    line = document.createElement("div");
    line.id = "vf-status-stage-detail";
    line.className = "vf-status-stage-detail";
    details.appendChild(line);
  }
  line.textContent = value;
}

/**
 * Fallback truthfulness: a job the backend rerouted to the local engine must
 * never read as NotebookLM output while it runs (the artifact itself carries
 * the same flags on its history card).
 */
function vfUpdateStatusFallbackNotice(video) {
  const details = document.getElementById("vf-status-details");
  if (!details) return;
  let notice = document.getElementById("vf-status-fallback");
  if (!video || !video.fallback_reason) {
    if (notice) notice.remove();
    return;
  }
  if (!notice) {
    notice = document.createElement("div");
    notice.id = "vf-status-fallback";
    notice.className = "vf-status-fallback-note";
    details.appendChild(notice);
  }
  const requestedNotebook = video.fallback_requested_engine === "notebooklm";
  notice.textContent = requestedNotebook
    ? "NotebookLM was unavailable, so this video is being rendered with the app engine instead. It will be labeled as app engine output, not NotebookLM."
    : "The requested engine was unavailable, so this video is being rendered with the app engine instead.";
  if (video.fallback_error) notice.title = String(video.fallback_error);
}

function updateGenerationStepper(activeVideo) {
  const stepper = document.getElementById("vf-generation-stepper");
  if (!stepper) return;

  const authCard = document.getElementById("vf-stepper-auth-card");
  const genBtn = document.getElementById("vf-generate-button");

  if (!activeVideo || ["completed", "complete", "ready", "cancelled"].includes(activeVideo.status)) {
    if (authCard) authCard.style.display = "none";
    vfSetCancelButtonVisibility(false);
    vfStopLiveStopwatch();
    if (genBtn) genBtn.disabled = false;

    if (activeVideo && vfIsVideoComplete(activeVideo)) {
      const pct = document.getElementById("vf-stepper-pct");
      const fill = document.getElementById("vf-stepper-bar-fill");
      vfSetStepperIndeterminate(false);
      if (pct) pct.textContent = "100%";
      if (fill) {
        fill.style.width = "100%";
        fill.style.background = "linear-gradient(90deg, #10b981, #059669)";
      }
      vfSetStatusStepLabel("Ready");
      vfSetStepperActiveKey("ready");
      vfUpdateStatusStageDetail("Generation finished — the video is ready to play.");
      vfUpdateStatusFallbackNotice(activeVideo);
      if (vfStepperHideTimer) clearTimeout(vfStepperHideTimer);
      vfStepperHideTimer = setTimeout(() => {
        vfStepperHideTimer = null;
        const stillBusy = vfVideos.some(v => !["completed", "complete", "ready", "failed", "cancelled"].includes(v.status));
        if (!stillBusy) stepper.classList.add("hidden");
      }, 6000);
    } else if (activeVideo && activeVideo.status === "cancelled") {
      const pct = document.getElementById("vf-stepper-pct");
      const fill = document.getElementById("vf-stepper-bar-fill");
      vfSetStepperIndeterminate(false);
      if (pct) pct.textContent = "Cancelled";
      if (fill) {
        fill.style.width = "100%";
        fill.style.background = "#6b7280";
      }
      vfSetStatusStepLabel("Cancelled");
      vfUpdateStatusStageDetail("Generation was cancelled before it finished.");
      vfUpdateStatusFallbackNotice(null);
      document.querySelectorAll("#vf-stepper-steps .vf-step").forEach(step => {
        step.classList.remove("active", "done", "error");
      });
      if (vfStepperHideTimer) clearTimeout(vfStepperHideTimer);
      vfStepperHideTimer = setTimeout(() => {
        vfStepperHideTimer = null;
        stepper.classList.add("hidden");
      }, 2500);
    } else {
      vfUpdateStatusStageDetail("");
      vfUpdateStatusFallbackNotice(null);
      if (!vfStepperHideTimer) {
        stepper.classList.add("hidden");
      }
    }
    return;
  }

  if (vfStepperHideTimer) {
    clearTimeout(vfStepperHideTimer);
    vfStepperHideTimer = null;
  }

  // Check if job failed with authentication error or processing error
  if (activeVideo.status === "failed") {
    stepper.classList.remove("hidden");
    vfSetCancelButtonVisibility(false);
    vfStopLiveStopwatch();
    if (genBtn) genBtn.disabled = false;
    vfSetStepperIndeterminate(false);
    vfUpdateStatusFallbackNotice(activeVideo);

    const pct = document.getElementById("vf-stepper-pct");
    const fill = document.getElementById("vf-stepper-bar-fill");

    if (isAuthError(activeVideo)) {
      if (pct) pct.textContent = "Auth required";
      if (fill) {
        fill.style.width = "100%";
        fill.style.background = "linear-gradient(90deg, #f59e0b, #ef4444)";
      }
      vfSetStatusStepLabel("Failed");

      const steps = document.querySelectorAll("#vf-stepper-steps .vf-step");
      steps.forEach((step, idx) => {
        step.classList.remove("active", "done");
        if (idx === 0) step.classList.add("error");
      });

      let authCardEl = document.getElementById("vf-stepper-auth-card");
      if (!authCardEl) {
        authCardEl = document.createElement("div");
        authCardEl.id = "vf-stepper-auth-card";
        authCardEl.className = "vf-auth-error-card";
        stepper.appendChild(authCardEl);
      }
      authCardEl.innerHTML = `
        <div class="vf-auth-error-msg">
          <span class="vf-auth-error-icon">⚠️</span>
          <span>Google Authentication Expired</span>
        </div>
        <div class="vf-auth-error-actions">
          <button type="button" class="vf-btn-reauth" onclick="startNotebookLMAuth(true)">Switch Google Account</button>
          <button type="button" class="vf-btn-retry" onclick="retryVideoFlow('${vfEscape(activeVideo.id)}')">↻ 1-Click Retry</button>
        </div>
      `;
      authCardEl.style.display = "flex";
      vfUpdateStatusStageDetail("Google authentication expired — reconnect your account, then retry.");
      return;
    } else {
      if (pct) pct.textContent = "Failed";
      if (fill) {
        fill.style.width = "100%";
        fill.style.background = "#ef4444";
      }
      const errorMsg = activeVideo.error || "Generation encountered an issue";
      vfSetStatusStepLabel("Failed");

      const steps = document.querySelectorAll("#vf-stepper-steps .vf-step");
      steps.forEach(step => {
        if (step.classList.contains("active")) {
          step.classList.remove("active");
          step.classList.add("error");
        }
      });

      let authCardEl = document.getElementById("vf-stepper-auth-card");
      if (!authCardEl) {
        authCardEl = document.createElement("div");
        authCardEl.id = "vf-stepper-auth-card";
        authCardEl.className = "vf-auth-error-card";
        stepper.appendChild(authCardEl);
      }
      authCardEl.innerHTML = `
        <div class="vf-auth-error-msg">
          <span class="vf-auth-error-icon">⚠️</span>
          <span>${vfEscape(errorMsg)}</span>
        </div>
        <div class="vf-auth-error-actions">
          <button type="button" class="vf-btn-retry" onclick="retryVideoFlow('${vfEscape(activeVideo.id)}')">↻ 1-Click Retry</button>
        </div>
      `;
      authCardEl.style.display = "flex";
      vfUpdateStatusStageDetail(cleanErrorMessage(errorMsg));
      return;
    }
  }

  if (authCard) authCard.style.display = "none";
  stepper.classList.remove("hidden");
  vfSetCancelButtonVisibility(true);
  if (genBtn) genBtn.disabled = true;
  vfStartLiveStopwatch(activeVideo);
  const progress = Math.max(0, Math.min(100, Math.round(Number(activeVideo.progress || 0))));
  const phase = vfJobPhase(activeVideo);
  const pct = document.getElementById("vf-stepper-pct");
  const fill = document.getElementById("vf-stepper-bar-fill");
  if (progress > 0) {
    vfSetStepperIndeterminate(false);
    if (pct) pct.textContent = `${progress}%`;
    if (fill) {
      fill.style.width = `${progress}%`;
      fill.style.background = "linear-gradient(90deg, var(--primary-orange), #ff9e66)";
    }
  } else {
    // No meaningful percentage exists yet — show an indeterminate indicator
    // rather than an invented one.
    vfSetStepperIndeterminate(true);
    if (pct) pct.textContent = "";
  }
  vfSetStatusStepLabel(VF_PHASE_LABELS[phase] || "Creating video");
  vfSetStepperActiveKey(vfPhaseStepKey(activeVideo, phase));
  if (activeVideo.stage) {
    vfUpdateStatusStageDetail(`Current stage: ${activeVideo.stage}`);
  } else {
    vfUpdateStatusStageDetail("");
  }
  vfUpdateStatusFallbackNotice(activeVideo);
}

function isVideoModelExternal(modelRef) {
  let refs = [modelRef];
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
  const button = document.getElementById("vf-generate-button");
  const message = document.getElementById("vf-generate-message");
  const source = sourceInput?.value || "";

  if (!source.trim()) {
    vfToast("Paste text or choose a document first.", true);
    sourceInput?.focus();
    return;
  }

  const title = titleInput?.value || "";
  const sourceName = sourceInput?.dataset.sourceName || "";

  if (button) button.disabled = true;

  if (vfSelectedEngine === "notebooklm") {
    const isAutoAdaptive = (vfSelectedFormat === "auto" || !vfSelectedFormat);
    const resolvedFormat = isAutoAdaptive ? (vfCurrentDocStats.resolvedFormat || "brief") : vfSelectedFormat;
    let targetDurationSec;
    if (isAutoAdaptive) {
      targetDurationSec = vfCurrentDocStats.targetSeconds || 90;
    } else if (resolvedFormat === "brief") {
      targetDurationSec = vfCurrentDocStats.briefSeconds || 60;
    } else if (resolvedFormat === "short") {
      targetDurationSec = vfCurrentDocStats.shortSeconds || 50;
    } else if (resolvedFormat === "explainer") {
      targetDurationSec = vfCurrentDocStats.explainerSeconds || 120;
    } else if (resolvedFormat === "cinematic") {
      targetDurationSec = vfCurrentDocStats.cinematicSeconds || 180;
    } else {
      targetDurationSec = vfCurrentDocStats.targetSeconds || 90;
    }
    const format = resolvedFormat;
    const style = vfSelectedStyle || "auto";
    const customPromptInput = document.getElementById("vf-nlm-custom-style-prompt");
    const stylePrompt = (style === "custom" && customPromptInput) ? customPromptInput.value.trim() : undefined;
    const focus = document.getElementById("vf-nlm-focus-input")?.value?.trim() || "";

    if (message) message.textContent = "Connecting to NotebookLM cloud and initializing generation pipeline…";

    const stepper = document.getElementById("vf-generation-stepper");
    if (stepper) {
      stepper.classList.remove("hidden");
      // No real percentage exists before the backend reports progress — show
      // an indeterminate indicator instead of an invented one.
      vfSetStepperIndeterminate(true);
      const pctEl = document.getElementById("vf-stepper-pct");
      if (pctEl) pctEl.textContent = "";
      vfSetStatusStepLabel("Preparing");
      vfSetStepperActiveKey("auth_check");
      vfUpdateStatusStageDetail("Checking the NotebookLM connection…");
      vfUpdateStatusFallbackNotice(null);
    }
    vfStartLiveStopwatch(null, "Generating in Cloud AI...");

    try {
      const data = await safeFetchJson("/api/video-flow/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "notebooklm",
          video_engine: "notebooklm",
          format: format,
          requested_format: vfSelectedFormat,
          adaptive: isAutoAdaptive,
          adaptive_format: resolvedFormat,
          duration_seconds: targetDurationSec,
          target_duration_seconds: targetDurationSec,
          adaptive_settings: {
            enabled: isAutoAdaptive,
            resolved_format: resolvedFormat,
            target_duration_seconds: targetDurationSec,
            max_ceiling_seconds: 300,
            word_count: vfCurrentDocStats.wordCount,
            page_count: vfCurrentDocStats.pageCount,
            section_count: vfCurrentDocStats.sectionCount,
            sections: vfCurrentDocStats.sections,
            density_score: vfCurrentDocStats.densityScore ?? 1.0,
            concept_count: vfCurrentDocStats.conceptCount ?? 1,
            content_value_rating: vfCurrentDocStats.contentValueRating ?? "standard",
            effective_word_count: vfCurrentDocStats.effectiveWordCount ?? vfCurrentDocStats.wordCount,
            redundancy_score: vfCurrentDocStats.redundancyScore ?? 0.0,
            substantive_concepts: vfCurrentDocStats.substantiveConcepts ?? [],
          },
          style: style,
          style_prompt: stylePrompt,
          focus: focus,
          title: title,
          source_text: source,
          source_name: sourceName,
          profile: vfNlmAuthStatus.profile || "video-flow-experiment",
        }),
      });

      if (!data || !data.success) {
        throw new Error(data?.error || "Could not start NotebookLM Video Flow.");
      }

      vfActiveVideoId = data.video?.id || data.job_id || null;
      vfVideos.unshift(data.video);
      renderVideoHistory();
      vfSetCancelButtonVisibility(true);
      vfStartLiveStopwatch(data.video, "Generating in Cloud AI...");
      scheduleVideoFlowPolling(true);
      vfToast("NotebookLM video queued! Follow real-time cloud rendering below.");
      if (message) message.textContent = "Cloud generation is running. Your video will be downloadable when complete.";
      document.getElementById("vf-status-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      vfActiveVideoId = null;
      vfSetCancelButtonVisibility(false);
      vfStopLiveStopwatch();
      const isAuth = isAuthError({ error: error.message });
      if (message) {
        if (isAuth) {
          message.innerHTML = `
            <div class="vf-auth-error-card">
              <div class="vf-auth-error-msg">
                <span class="vf-auth-error-icon">⚠️</span>
                <span>Google Authentication Expired</span>
              </div>
              <div class="vf-auth-error-actions">
                <button type="button" class="vf-btn-reauth" onclick="startNotebookLMAuth(true)">Switch Google Account</button>
                <button type="button" class="vf-btn-retry" onclick="generateVideoFlow()">↻ 1-Click Retry</button>
              </div>
            </div>`;
        } else {
          message.textContent = error.message || "Generation failed.";
        }
      }
      vfToast(error.message || "NotebookLM generation failed.", true);
      const stepper = document.getElementById("vf-generation-stepper");
      if (stepper) {
        updateGenerationStepper({
          id: "current-attempt",
          status: "failed",
          error: error.message,
          stage: isAuth ? "Google Authentication Expired" : (error.message || "Generation Failed")
        });
      }
    } finally {
      if (button) button.disabled = false;
    }
  } else {
    // Native Engine (Visual V2.1)
    const modelSelect = document.getElementById("vf-model-select");
    const themeSelect = document.getElementById("vf-theme-select");
    const visualDirection = document.getElementById("vf-visual-direction");
    const selectedMode = document.querySelector('input[name="vf-mode"]:checked');
    const modelRef = modelSelect?.value || (vfCatalog && vfCatalog.active_model) || "local/deterministic";
    const consent = Boolean(document.getElementById("vf-external-consent")?.checked);

    if (isVideoModelExternal(modelRef) && !consent) {
      vfToast("Confirm external AI planning before sending this source to the selected provider.", true);
      document.getElementById("vf-external-consent")?.focus();
      if (button) button.disabled = false;
      return;
    }

    const isAutoAdaptive = (vfSelectedFormat === "auto" || !vfSelectedFormat);
    const resolvedFormat = isAutoAdaptive ? (vfCurrentDocStats.resolvedFormat || "brief") : vfSelectedFormat;
    let targetDurationSec;
    if (isAutoAdaptive) {
      targetDurationSec = vfCurrentDocStats.targetSeconds || 90;
    } else if (resolvedFormat === "brief") {
      targetDurationSec = vfCurrentDocStats.briefSeconds || 60;
    } else if (resolvedFormat === "short") {
      targetDurationSec = vfCurrentDocStats.shortSeconds || 50;
    } else if (resolvedFormat === "explainer") {
      targetDurationSec = vfCurrentDocStats.explainerSeconds || 120;
    } else if (resolvedFormat === "cinematic") {
      targetDurationSec = vfCurrentDocStats.cinematicSeconds || 180;
    } else {
      targetDurationSec = vfCurrentDocStats.targetSeconds || 90;
    }

    if (message) message.textContent = "Creating the project and starting scene planning…";
    vfStartLiveStopwatch(null, "Generating Video...");

    try {
      const data = await safeFetchJson("/api/video-flow/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_engine: "visual-v2.1",
          source_text: source,
          source_name: sourceName,
          title: title,
          mode: selectedMode?.value || "summary",
          model_ref: modelRef,
          allow_external_ai: consent,
          theme: themeSelect?.value || "auto",
          visual_direction: visualDirection?.value || "",
          format: resolvedFormat,
          requested_format: vfSelectedFormat,
          adaptive: isAutoAdaptive,
          duration_seconds: targetDurationSec,
          target_duration_seconds: targetDurationSec,
          adaptive_settings: {
            enabled: isAutoAdaptive,
            resolved_format: resolvedFormat,
            word_count: vfCurrentDocStats.wordCount,
            page_count: vfCurrentDocStats.pageCount,
            section_count: vfCurrentDocStats.sectionCount,
            target_duration_seconds: targetDurationSec,
            max_ceiling_seconds: 300,
            density_score: vfCurrentDocStats.densityScore ?? 1.0,
            concept_count: vfCurrentDocStats.conceptCount ?? 1,
            content_value_rating: vfCurrentDocStats.contentValueRating ?? "standard",
            effective_word_count: vfCurrentDocStats.effectiveWordCount ?? vfCurrentDocStats.wordCount,
            redundancy_score: vfCurrentDocStats.redundancyScore ?? 0.0,
          },
        }),
      });

      if (!data || !data.success) {
        throw new Error(data?.error || "Could not start Video Flow.");
      }

      vfActiveVideoId = data.video?.id || data.job_id || null;
      vfVideos.unshift(data.video);
      renderVideoHistory();
      vfSetCancelButtonVisibility(true);
      vfStartLiveStopwatch(data.video);
      scheduleVideoFlowPolling(true);
      vfToast("Video queued. You can follow its progress in history.");
      if (message) message.textContent = "Generation is running in the background.";
      document.getElementById("vf-status-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      vfActiveVideoId = null;
      vfSetCancelButtonVisibility(false);
      vfStopLiveStopwatch();
      if (message) message.textContent = error.message || "Generation failed.";
      vfToast(error.message || "Generation failed.", true);
    } finally {
      if (button) button.disabled = false;
    }
  }
}

function scheduleVideoFlowPolling(immediate = false) {
  if (vfPollTimer) window.clearInterval(vfPollTimer);
  const hasActive = vfVideos.some(video => !["completed", "complete", "ready", "failed", "cancelled"].includes(video.status));
  if (!hasActive && !immediate) return;

  const refresh = async () => {
    try {
      const data = await safeFetchJson("/api/video-flow/history");
      if (data && Array.isArray(data.videos)) {
        vfVideos = data.videos;
        renderVideoHistory();

        const activeVideo = vfVideos.find(video => !["completed", "complete", "ready", "failed", "cancelled"].includes(video.status));
        const trackedVideo = vfActiveVideoId ? vfVideos.find(v => v.id === vfActiveVideoId) : null;

        if (activeVideo) {
          if (!trackedVideo || ["completed", "complete", "ready", "failed", "cancelled"].includes(trackedVideo.status)) {
            vfActiveVideoId = activeVideo.id;
          }
          vfStartLiveStopwatch(activeVideo);
          updateGenerationStepper(activeVideo);
        } else if (trackedVideo) {
          // The video monitored in this session has reached terminal status
          vfStopLiveStopwatch();
          vfActiveVideoId = null;

          if (["completed", "complete", "ready"].includes(trackedVideo.status) || trackedVideo.playable) {
            updateGenerationStepper(trackedVideo);
            vfToast("Video generation complete! Ready to watch.");
          } else if (trackedVideo.status === "failed") {
            updateGenerationStepper(trackedVideo);
          } else if (trackedVideo.status === "cancelled") {
            updateGenerationStepper(trackedVideo);
          } else {
            updateGenerationStepper(null);
          }
        } else {
          vfStopLiveStopwatch();
          updateGenerationStepper(null);
        }
        if (!activeVideo) {
          window.clearInterval(vfPollTimer);
          vfPollTimer = null;
        }
      }
    } catch (_) {
      // A later poll can recover if the local backend is restarting.
    }
  };

  if (immediate) refresh();
  vfPollTimer = window.setInterval(refresh, 1800);
}

async function saveVideoModel(modelRef) {
  if (!modelRef) return false;
  try {
    const data = await safeFetchJson("/api/video-flow/settings/model", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({model_ref: modelRef}),
    });
    if (!data || !data.success) throw new Error(data?.error || "Could not save the Video Flow model.");
    vfCatalog.active_model = modelRef;
    updateActiveVideoModel(modelRef);
    renderVideoModelPicker();
    vfToast("Video Flow model selected.");
    return true;
  } catch (error) {
    vfToast(error.message || "Failed to save model", true);
    return false;
  }
}

// Narration voice for Video Flow: shared Audio Flow TTS catalog, independent
// selection (Audio Flow keeps its own voice under exec_audio_policy_model).
let videoFlowVoiceModels = [];
let videoFlowVoiceSet = null;
let videoFlowVoiceModelRef = "edge/en-US-AvaNeural";

async function loadVideoFlowVoice() {
  try {
    const data = await safeFetchJson("/api/video-flow/voice");
    if (!data || !data.success) return;
    videoFlowVoiceModelRef = data.active_voice || "edge/en-US-AvaNeural";
    videoFlowVoiceModels = (data.models || []).map(m => ({
      full_id: m.full_id,
      display_name: m.display_name || m.label || m.full_id,
      provider: String(m.full_id || "").split("/", 1)[0],
      provider_name: m.provider_name || String(m.full_id || "").split("/", 1)[0],
      capabilities: [],
    }));
    videoFlowVoiceSet = videoFlowVoiceModels.length
      ? new Set(videoFlowVoiceModels.map(m => m.full_id))
      : null;
    if (!videoFlowVoiceSet || !videoFlowVoiceSet.has(videoFlowVoiceModelRef)) {
      videoFlowVoiceModelRef = "edge/en-US-AvaNeural";
    }
    updateVideoFlowVoiceLabels();
  } catch {
    // Voice loading is non-critical; the picker shows the Edge default.
  }
}

function updateVideoFlowVoiceLabels() {
  const active = videoFlowVoiceModels.find(m => m.full_id === videoFlowVoiceModelRef);
  const labelEl = document.getElementById("vf-active-voice-label");
  const detailEl = document.getElementById("vf-active-voice-detail");
  const engineEl = document.getElementById("vf-active-voice-engine-label");
  const provider = String(videoFlowVoiceModelRef).split("/", 1)[0];
  if (labelEl) labelEl.textContent = active ? `${active.provider_name} — ${active.display_name}` : videoFlowVoiceModelRef;
  if (detailEl) detailEl.textContent = videoFlowVoiceModelRef;
  if (engineEl) engineEl.textContent = provider === "edge" ? "Edge TTS (free)" : (active ? active.provider_name : provider);
}

async function saveVideoFlowVoice(voiceRef) {
  if (!voiceRef) return false;
  try {
    const data = await safeFetchJson("/api/video-flow/voice", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({voice: voiceRef}),
    });
    if (!data || !data.success) throw new Error(data?.error || "Could not save the Video Flow voice.");
    videoFlowVoiceModelRef = voiceRef;
    updateVideoFlowVoiceLabels();
    vfToast("Narration voice selected for Video Flow.");
    return true;
  } catch (error) {
    vfToast(error.message || "Failed to save narration voice", true);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Create / Your videos tabs (plan section 7). Switching only toggles panel
// visibility: draft inputs, stored values, and job state live in the DOM and
// are never rebuilt, so they survive every switch. Background polling keeps
// running on both tabs and never forces a tab change.
// ---------------------------------------------------------------------------

function vfFlowShowTab(which) {
  const create = document.getElementById("vf-panel-create");
  const library = document.getElementById("vf-panel-library");
  const tabCreate = document.getElementById("vf-tab-create");
  const tabLibrary = document.getElementById("vf-tab-library");
  if (!create || !library || !tabCreate || !tabLibrary) return;
  const showCreate = which !== "library";
  create.hidden = !showCreate;
  library.hidden = showCreate;
  tabCreate.classList.toggle("active", showCreate);
  tabCreate.setAttribute("aria-selected", showCreate ? "true" : "false");
  tabLibrary.classList.toggle("active", !showCreate);
  tabLibrary.setAttribute("aria-selected", showCreate ? "false" : "true");
  if (!showCreate) {
    const histBody = document.getElementById("vf-history-body");
    if (histBody) histBody.style.display = "block";
    try { renderVideoHistory(); } catch (_) { /* keep the current view on errors */ }
  }
}
window.vfFlowShowTab = vfFlowShowTab;

function initVideoFlowAdaptiveUI() {
  const sourceInput = document.getElementById("vf-source-input");
  if (sourceInput) {
    sourceInput.addEventListener("input", () => updateVideoSourceCount());
    sourceInput.addEventListener("paste", () => setTimeout(() => updateVideoSourceCount(), 50));
    sourceInput.addEventListener("change", () => updateVideoSourceCount());
    sourceInput.addEventListener("keyup", () => updateVideoSourceCount());
  }
  const fileInput = document.getElementById("vf-file-input");
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files[0]) {
        loadVideoSourceFile(fileInput.files[0]);
      }
    });
  }
  selectVideoEngine("notebooklm");
  selectNotebookLMFormat(vfSelectedFormat || "auto");
  vfInitLibraryControls();
  scheduleSourceAnalysis(0);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    loadVideoFlowVoice();
    initVideoFlowAdaptiveUI();
  });
} else {
  loadVideoFlowVoice();
  initVideoFlowAdaptiveUI();
}

function isVideoModelExternal(modelRef) {
  if (!modelRef || modelRef === "local/deterministic") return false;
  if (modelRef.startsWith("local/") || modelRef.startsWith("ollama/") || modelRef.startsWith("lmstudio/") || modelRef.startsWith("llamacpp/")) {
    return false;
  }
  let refs = [modelRef];
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
  if (modelRef === "local/deterministic") {
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
  const names = [...new Set(refs.map(ref => {
    const model = (vfCatalog.models || []).find(item => item.full_id === ref);
    return model?.provider_name || ref.split("/", 1)[0];
  }))];
  row.style.display = "flex";
  checkbox.checked = false;
  copy.textContent = "The source text will be sent to " + (names.join(", ") || "the selected providers") + " for scene planning. Voice narration and rendering remain on this PC.";
}
async function vfPost(path, body = {}) {
  const data = await safeFetchJson(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  if (data.success === false || data.ok === false || data.error) {
    throw new Error(data.error || "Video Flow request failed.");
  }
  return data;
}

async function openVideoProvider(providerId) {
  const page = document.getElementById("page-videoflow");
  const panel = document.getElementById("vf-provider-detail-panel");
  const root = document.getElementById("vf-provider-detail-content");
  if (!page || !panel || !root) return;

  const requestId = ++vfProviderOpenRequest;
  const mainContent = document.querySelector(".main-content");
  if (!page.classList.contains("vf-provider-open")) {
    page.dataset.providerReturnScroll = String((mainContent ? mainContent.scrollTop : window.scrollY) || 0);
  }
  page.classList.add("vf-provider-open");
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  root.innerHTML = '<div class="vf-empty-state vf-compact-empty"><strong>Opening provider…</strong><span>Loading its connections and enabled models.</span></div>';
  if (mainContent) mainContent.scrollTop = 0;
  window.scrollTo({top: 0, behavior: "instant"});

  try {
    const data = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
    if (!data || data.error || data.success === false) throw new Error(data?.error || "Could not open provider.");
    if (requestId !== vfProviderOpenRequest) return;
    vfCurrentProvider = providerId;
    vfCurrentProviderDetails = data;
    vfxSelectedConnIds = new Set();
    vfxConnTestStatus = {};
    if (typeof vfxProviderModelErrors === "undefined") {
      window.vfxProviderModelErrors = {};
    }
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
  const mainContent = document.querySelector(".main-content");
  if (mainContent) mainContent.scrollTop = returnScroll;
  requestAnimationFrame(() => {
    if (mainContent) mainContent.scrollTop = returnScroll;
    window.scrollTo({top: returnScroll, behavior: "smooth"});
  });
}

function renderVideoProviderDetails() {
  const data = vfCurrentProviderDetails;
  const root = document.getElementById("vf-provider-detail-content");
  if (!data || !root) return;

  // Shared stroke-icon renderer, resolved once for this whole render pass.
  const vfIco = (typeof vfUiIcon === "function") ? vfUiIcon : function () { return ""; };

  const provider = data.provider;
  const isOAuth = provider.category === "oauth";
  const isLocal = provider.category === "local";
  const oauthStatus = provider.oauth_status || {};
  const logo = vfBrandLogo(provider.id, vfEscape(vfProviderIcons[provider.id] || provider.icon || "\uD83C\uDFAC"));
  const conns = (data.connections || []).slice().sort(function(a, b) {
    return (a.priority || 1) - (b.priority || 1) || (a.id - b.id);
  });

  // ---------- Connection rows (9Router style) ----------
  var connRows = conns.map(function(conn, idx) {
    var isAct = !(conn.is_active === false || conn.is_active === 0);
    var isFirst = idx === 0;
    var isLast = idx === conns.length - 1;
    var isSelected = vfxSelectedConnIds.has(conn.id);
    var st = String(conn.status || "untested").toLowerCase();
    var dotClass = !isAct ? "disabled" : (st === "error" || st === "failed" ? "error" : (st === "untested" ? "disabled" : "active"));
    var dotLabel = !isAct ? "disabled" : (st === "error" || st === "failed" ? "error" : (st === "untested" ? "untested" : "active"));
    var isOAuthConn = String(conn.auth_type || "") === "oauth";
    var keyIcon = isOAuthConn ? "\u26A1" : "\uD83D\uDD11";
    var pillLabel = isOAuthConn ? "OAuth" : (isLocal ? "Local" : "API Key");
    var testState = vfxConnTestStatus[conn.id];
    var testBadge = "";
    if (testState === "testing") {
      testBadge = '<span style="font-size:11px;color:#ea580c;font-weight:700;">\u23F3 testing\u2026</span>';
    } else if (testState === "ok") {
      testBadge = '<span style="font-size:11px;color:#22c55e;font-weight:700;">\u2705 passed</span>';
    } else if (testState === "fail") {
      testBadge = '<span style="font-size:11px;color:#ef4444;font-weight:700;">\u274C failed</span>';
    }
    return '<div class="conn-row-9r ' + (isAct ? "" : "inactive") + '" data-conn-id="' + conn.id + '">' +
      '<div class="conn-left-9r">' +
        '<input type="checkbox" ' + (isSelected ? "checked" : "") + ' onchange="vfToggleSelectConn(' + vfJsArg(conn.id) + ', this.checked)">' +
        '<div class="conn-arrows-col">' +
          '<button class="conn-arrow-btn" onclick="vfMoveConnPriority(' + vfJsArg(conn.id) + ', -1)" ' + (isFirst ? "disabled" : "") + ' title="Move up">\u25B2</button>' +
          '<button class="conn-arrow-btn" onclick="vfMoveConnPriority(' + vfJsArg(conn.id) + ', 1)" ' + (isLast ? "disabled" : "") + ' title="Move down">\u25BC</button>' +
        '</div>' +
        '<span class="conn-key-icon">' + keyIcon + '</span>' +
        '<div class="conn-details-col">' +
          '<div class="conn-title-row"><span class="conn-name-text">' + vfEscape(conn.name || "Connection") + '</span></div>' +
          '<div class="conn-badges-row">' +
            '<span class="conn-dot-badge ' + dotClass + '">\u25CF ' + dotLabel + '</span>' +
            '<span class="conn-pill-badge">' + pillLabel + '</span>' +
            '<span class="conn-priority-pill">#' + (conn.priority || (idx + 1)) + '</span>' +
            (conn.secret_hint ? '<span style="font-size:11px;color:var(--text-muted);margin-left:4px;">' + vfEscape(conn.secret_hint) + '</span>' : "") +
            testBadge +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="conn-actions-9r">' +
        '<button class="conn-action-btn" onclick="testVideoConnection(' + vfJsArg(conn.id) + ')" title="Test connection"><span style="font-size:14px;">\u2697</span><span>Test</span></button>' +
        '<button class="conn-action-btn" onclick="editVideoConnection(' + vfJsArg(conn.id) + ')" title="Edit connection"><span style="font-size:14px;">\u270F</span><span>Edit</span></button>' +
        '<button class="conn-action-btn delete-btn" onclick="deleteVideoConnection(' + vfJsArg(conn.id) + ')" title="Delete connection"><span style="font-size:14px;">\uD83D\uDDD1</span><span>Delete</span></button>' +
        '<label class="toggle-switch" style="margin-left:6px;">' +
          '<input type="checkbox" ' + (isAct ? "checked" : "") + ' onchange="toggleVideoConnection(' + vfJsArg(conn.id) + ', this.checked)">' +
          '<span class="toggle-slider"></span>' +
        '</label>' +
      '</div>' +
    '</div>';
  }).join("");

  var connsEmpty = '<div class="conn-empty-9r">' +
    '<div class="conn-empty-left-9r">' +
      '<div class="conn-empty-icon-circle-9r">' + vfIco("key") + '</div>' +
      '<span class="conn-empty-text-9r">No connections yet</span>' +
    '</div>' +
    '<button class="btn-primary" style="padding:7px 16px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="' + (isOAuth ? "openOAuthFlow('" + vfEscape(provider.id) + "')" : "openVideoConnectionModal()") + '">+ Add</button>' +
  '</div>';

  // ---------- Model cards (9Router style) ----------
  var allModels = data.models || [];
  var activeModels = allModels.filter(function(m) { return !(m.is_active === false || m.is_active === 0); });
  var disabledModels = allModels.filter(function(m) { return m.is_active === false || m.is_active === 0; });

  var modelCards = activeModels.map(function(model) {
    var fid = vfEscape(model.full_id);
    var testRes = vfxModelTestResults[model.full_id];
    var isTesting = vfxTestingModelIds.has(model.full_id);
    var cardClass = isTesting ? "testing" : (testRes ? (testRes.ok ? "tested-ok" : "tested-error") : "");
    // Shared icon language: real brand mark when we have one, otherwise a
    // state icon, plus inline-SVG action buttons instead of emoji.
    var brandMark = (typeof vfBrandLogo === "function") ? vfBrandLogo(vfCurrentProvider) : "";
    var stateIcon = isTesting ? vfIco("spinner", "vf-ico-spin") : (testRes ? (testRes.ok ? vfIco("check") : vfIco("ban")) : vfIco("bot"));
    var badgeHtml = brandMark || stateIcon;
    var latencyHtml = (testRes && testRes.ok && testRes.latency_ms) ? '<span class="model-latency-9r">' + testRes.latency_ms + 'ms</span>' : "";
    var errHtml = (testRes && !testRes.ok && testRes.error) ? '<div class="model-test-error-text" title="' + vfEscape(testRes.error) + '">' + vfIco("ban") + ' ' + vfEscape(testRes.error) + '</div>' : "";
    return '<div class="model-card-9r ' + cardClass + '" id="vf-model-card-' + model.id + '">' +
      '<div class="model-card-left-9r">' +
        '<span class="model-status-icon-9r' + (isTesting ? ' testing' : '') + '">' + badgeHtml + '</span>' +
        '<div class="model-card-info-9r">' +
          '<div class="edge-voice-title" title="' + vfEscape(model.display_name || model.model_id) + '">' + vfEscape(model.display_name || model.model_id) + '</div>' +
          '<div class="model-card-meta-9r">' +
            '<code class="model-code-tag">' + fid + '</code>' +
            latencyHtml +
          '</div>' +
          '<div class="model-capabilities-9r">' + vfCapabilityBadges(model) + '</div>' +
          errHtml +
        '</div>' +
      '</div>' +
      '<div class="model-actions-9r">' +
        '<button class="model-action-btn-9r" onclick="vfTestVideoModel(' + vfJsArg(model.full_id) + ', this)" title="Test model" aria-label="Test model" ' + (isTesting ? "disabled" : "") + '>' + (isTesting ? vfIco("spinner", "vf-ico-spin") : vfIco("test")) + '</button>' +
        '<button class="model-action-btn-9r" onclick="copyVideoModelId(' + vfJsArg(model.full_id) + ', this)" title="Copy Model ID" aria-label="Copy model ID">' + vfIco("copy", "vf-ico-copy") + vfIco("check", "vf-ico-check") + '</button>' +
        (model.custom ? '<button class="model-action-btn-9r delete" onclick="deleteVideoCustomModel(' + vfJsArg(model.id) + ', ' + vfJsArg(vfCurrentProvider) + ')" title="Delete custom model" aria-label="Delete custom model">' + vfIco("trash") + '</button>' : "") +
        '<button class="model-action-btn-9r delete" onclick="vfDisableVideoModel(' + vfJsArg(model.id) + ', ' + vfJsArg(vfCurrentProvider) + ')" title="Disable this model" aria-label="Disable this model">' + vfIco("ban") + '</button>' +
      '</div>' +
    '</div>';
  }).join("");

  var modelsEmpty = '<div class="vf-empty-state vf-compact-empty"><strong>No models</strong><span>Add a model ID for this provider.</span></div>';

  var disabledBox = "";
  if (disabledModels.length > 0) {
    var chips = disabledModels.map(function(m) {
      return '<button class="disabled-model-chip" onclick="vfEnableVideoModel(' + vfJsArg(m.id) + ', ' + vfJsArg(vfCurrentProvider) + ')" title="Click to restore model"><span>+</span> ' + vfEscape(m.model_id) + '</button>';
    }).join("");
    disabledBox = '<div id="vf-detail-disabled-models-box" class="disabled-models-container-9r">' +
      '<div class="disabled-models-title-9r">Disabled models (<span id="vf-detail-disabled-count">' + disabledModels.length + '</span>):</div>' +
      '<div class="disabled-models-pills-row">' + chips + '</div>' +
    '</div>';
  }

  // ---------- Assemble panel ----------
  var html = "";

  // Header & back
  html += '<div class="detail-header-bar">';
  html += '<div class="provider-detail-title-row">';
  html += '<div class="provider-large-badge provider-brand-logo">' + logo + '</div>';
  html += '<div>';
  html += '<div style="display:flex;align-items:center;gap:10px;">';
  html += '<h1 class="provider-detail-title">' + vfEscape(provider.name) + '</h1>';
  // Authentication (oauth) providers sign in with an account — the Get API Key
  // pill only belongs to API-key providers.
  if (provider.get_key_url && provider.category !== "oauth") {
    html += '<a href="' + vfEscape(provider.get_key_url) + '" target="_blank" class="get-key-pill-link">\uD83D\uDD11 Get API Key \u2197</a>';
  }
  html += '</div>';
  html += '<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">' + (provider.description ? vfEscape(provider.description) + ' \u00B7 ' : "") + conns.length + ' connection' + (conns.length === 1 ? "" : "s") + '</div>';
  html += '</div></div></div>';

  // CONNECTIONS CARD (9Router style)
  html += '<div class="nine-router-card">';
  html += '<div class="connections-header-9r">';
  html += '<h2 class="connections-title-9r">Connections</h2>';
  html += '<div class="connections-controls-9r">';
  if (isOAuth) {
    html += '<button class="btn-secondary" style="padding:6px 14px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="openOAuthFlow(\'' + vfEscape(provider.id) + '\')">Add account</button>';
  } else {
    html += '<button class="btn-secondary" style="padding:6px 14px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="vfTestConnsOneByOne()" id="vf-test-conn-one-by-one">' +
      '<span id="vf-test-conn-spinner" class="vf-btn-spinner" style="display:none;">' + vfIco("spinner", "vf-ico-spin") + '</span>' + vfIco("refresh") + '<span id="vf-test-conn-btn-label">Test Connection One-by-One</span></button>';
    if (provider.id && String(provider.id).startsWith("custom-")) {
      html += '<button class="btn-secondary" style="padding:5px 12px;font-size:11px;margin-right:6px;display:inline-flex;align-items:center;gap:5px;" onclick="openEditCustomProviderModal(\'' + vfEscape(provider.id) + '\')" title="Edit this custom provider">' + vfIco("sparkles") + ' Edit Provider</button>';
      html += '<button class="conn-action-btn delete-btn" style="padding:5px 10px;display:inline-flex;align-items:center;gap:5px;" onclick="vfDeleteCustomProviderWhole(\'' + vfEscape(provider.id) + '\')" title="Delete this custom provider">' + vfIco("trash") + '<span style="font-size:10px;">Delete Provider</span></button>';
    }
  html += '<div class="round-robin-toggle-group"><span>Round Robin</span>' +
      '<label class="toggle-switch"><input type="checkbox" id="vf-round-robin-toggle" ' + (data.load_balance_mode === "round_robin" ? "checked" : "") + ' onchange="vfToggleRoundRobin(this.checked)"><span class="toggle-slider"></span></label></div>';
  }
  html += '</div></div>';
  if (isOAuth) {
    html += '<div class="vf-oauth-banner ' + (oauthStatus.connected ? "connected" : "") + '" style="margin-bottom:12px;">' +
      '<span>' + (oauthStatus.connected ? "\u2713" : "i") + '</span>' +
      '<strong>' + vfEscape(oauthStatus.label || "Not connected") + '</strong>' +
    '</div>';
  }
  if (conns.length > 0) {
    html += '<label class="select-all-row-9r"><input type="checkbox" id="vf-detail-select-all" onchange="vfToggleSelectAllConns(this.checked)"><span>Select All</span></label>';
  }
  html += '<div class="connections-list">' + (connRows || connsEmpty) + '</div>';
  if (conns.length > 0) {
    html += '<div style="margin-top:14px;"><button class="btn-primary" style="padding:7px 16px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="' + (isOAuth ? "openOAuthFlow('" + vfEscape(provider.id) + "')" : "openVideoConnectionModal()") + '"><span>+</span> Add</button></div>';
  }
  html += '</div>';

  // AVAILABLE MODELS CARD (9Router style)
  html += '<div class="nine-router-card">';
  html += '<div class="models-header-9r">';
  html += '<h2 class="models-title-9r">Available Models</h2>';
  html += '<div class="models-controls-9r">';
  html += '<button class="btn-secondary" style="padding:6px 14px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="vfEnableAllModels()">' + vfIco("refresh") + ' Active All</button>';
  html += '<button class="btn-secondary" style="padding:6px 14px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" onclick="vfDisableAllModels()">' + vfIco("ban") + ' Disable All</button>';
  html += '</div></div>';
  const curPid = provider.id;
  const activeVfErr = (typeof vfxProviderModelErrors !== "undefined" && vfxProviderModelErrors[curPid]) || null;
  const bannerStyle = (activeVfErr && activeVfErr.error) ? 'display:block;' : 'display:none;';
  const bannerText = (activeVfErr && activeVfErr.error) ? vfEscape("✕ Model Test Failed (" + activeVfErr.modelId + "): " + activeVfErr.error) : '';
  html += '<div id="vf-models-test-error-banner" style="' + bannerStyle + 'color:#ef4444;font-size:12px;margin-bottom:12px;padding:6px 12px;background:rgba(239,68,68,0.08);border-radius:6px;border:1px solid rgba(239,68,68,0.2);">' + bannerText + '</div>';
  html += '<div class="models-grid-9r">' + (modelCards || "") + '<div class="add-model-dashed-btn" onclick="openVideoCustomModelModal()"><span>+</span> Add Model</div></div>';
  html += disabledBox;
  html += '</div>';

  root.innerHTML = html;
}

async function refreshCurrentVideoProviderDetail(providerId) {
  const pid = providerId || vfCurrentProvider;
  if (!pid) return;
  const req = vfProviderOpenRequest;
  try {
    const data = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(pid));
    if (!data || data.error || data.success === false) return;
    const panel = document.getElementById("vf-provider-detail-panel");
    if (req !== vfProviderOpenRequest || !panel || panel.classList.contains("hidden")) return;
    vfCurrentProvider = pid;
    vfCurrentProviderDetails = data;
    renderVideoProviderDetails();
  } catch (error) { /* panel keeps previous state on refresh failure */ }
}

async function vfTestConnsOneByOne() {
  if (vfxOneByOneRunning || !vfCurrentProviderDetails) return;
  const conns = vfCurrentProviderDetails.connections || [];
  if (conns.length === 0) return;
  vfxOneByOneRunning = true;
  const spinner = document.getElementById("vf-test-conn-spinner");
  const label = document.getElementById("vf-test-conn-btn-label");
  const btn = document.getElementById("vf-test-conn-one-by-one");
  if (spinner) spinner.style.display = "inline-block";
  if (btn) btn.disabled = true;
  try {
    for (let i = 0; i < conns.length; i++) {
      if (label) label.textContent = "Testing (" + (i + 1) + "/" + conns.length + ")\u2026";
      vfxConnTestStatus[conns[i].id] = "testing";
      renderVideoProviderDetails();
      try {
        const res = await vfPost("/api/video-flow/providers/connections/test", { id: conns[i].id, provider: vfCurrentProvider });
        vfxConnTestStatus[conns[i].id] = res && res.success !== false ? "ok" : "fail";
      } catch (err) {
        vfxConnTestStatus[conns[i].id] = "fail";
      }
    }
  } finally {
    vfxOneByOneRunning = false;
    if (spinner) spinner.style.display = "none";
    if (label) label.textContent = "Test Connection One-by-One";
    if (btn) btn.disabled = false;
    await refreshCurrentVideoProviderDetail();
  }
}

function vfToggleSelectAllConns(checked) {
  if (!vfCurrentProviderDetails) return;
  const conns = vfCurrentProviderDetails.connections || [];
  vfxSelectedConnIds = new Set();
  if (checked) conns.forEach(function(c) { vfxSelectedConnIds.add(c.id); });
  renderVideoProviderDetails();
}

function vfToggleSelectConn(cid, checked) {
  if (checked) { vfxSelectedConnIds.add(cid); } else { vfxSelectedConnIds.delete(cid); }
  const conns = (vfCurrentProviderDetails && vfCurrentProviderDetails.connections) || [];
  const allBox = document.getElementById("vf-detail-select-all");
  if (allBox) allBox.checked = conns.length > 0 && conns.every(function(c) { return vfxSelectedConnIds.has(c.id); });
}

async function vfMoveConnPriority(connId, direction) {
  if (!vfCurrentProviderDetails) return;
  const conns = (vfCurrentProviderDetails.connections || []).slice().sort(function(a, b) {
    return (a.priority || 1) - (b.priority || 1) || (a.id - b.id);
  });
  const idx = conns.findIndex(function(c) { return c.id === connId; });
  const swapWith = idx + direction;
  if (idx < 0 || swapWith < 0 || swapWith >= conns.length) return;
  const tmp = conns[idx]; conns[idx] = conns[swapWith]; conns[swapWith] = tmp;
  try {
    await vfPost("/api/video-flow/providers/connections/reorder", {
      provider: vfCurrentProvider,
      connection_ids: conns.map(function(c) { return c.id; })
    });
    vfToast("Connection priority updated.");
  } catch (error) {
    vfToast(error.message || "Could not reorder connections.", true);
  }
  await refreshCurrentVideoProviderDetail();
}

async function vfToggleRoundRobin(checked) {
  if (!vfCurrentProviderDetails) return;
  const mode = checked ? "round_robin" : "priority";
  try {
    await vfPost("/api/video-flow/providers/settings", { provider: vfCurrentProvider, load_balance_mode: mode });
    vfCurrentProviderDetails.load_balance_mode = mode;
    vfToast(checked ? "Round robin enabled." : "Priority / fallback enabled.");
  } catch (error) {
    vfToast(error.message || "Could not change load balance mode.", true);
    await refreshCurrentVideoProviderDetail();
  }
}

async function vfEnableAllModels() {
  if (!vfCurrentProvider) return;
  try {
    await vfPost("/api/video-flow/providers/models/enable-all", { provider: vfCurrentProvider });
    vfToast("All models activated.");
  } catch (error) { vfToast(error.message || "Could not activate models.", true); }
  await refreshCurrentVideoProviderDetail();
}

async function vfDisableAllModels() {
  if (!vfCurrentProvider) return;
  try {
    await vfPost("/api/video-flow/providers/models/disable-all", { provider: vfCurrentProvider });
    vfToast("All models disabled.");
  } catch (error) { vfToast(error.message || "Could not disable models.", true); }
  await refreshCurrentVideoProviderDetail();
}

async function vfDisableVideoModel(modelDbId, providerId) {
  try {
    await vfPost("/api/video-flow/providers/models/toggle", { id: modelDbId, is_active: false, provider: providerId || vfCurrentProvider });
  } catch (error) { vfToast(error.message || "Could not disable model.", true); }
  await refreshCurrentVideoProviderDetail();
}

async function vfEnableVideoModel(modelDbId, providerId) {
  try {
    await vfPost("/api/video-flow/providers/models/toggle", { id: modelDbId, is_active: true, provider: providerId || vfCurrentProvider });
  } catch (error) { vfToast(error.message || "Could not enable model.", true); }
  await refreshCurrentVideoProviderDetail();
}

async function vfTestVideoModel(fullId, btnEl) {
  const aliasMap = {
    codex: "openai_codex",
    nim: "nvidia_nim",
    vx: "vertex_ai",
    zen: "opencode_zen",
    "claude-code": "claude_code",
    lmstudio: "lm_studio",
    llamacpp: "llama_cpp"
  };
  let providerId = vfCurrentProvider;
  if (aliasMap[providerId]) providerId = aliasMap[providerId];
  let modelId = fullId;
  const slashIdx = fullId.indexOf("/");
  if (slashIdx > 0) {
    const pfx = fullId.slice(0, slashIdx);
    if (pfx === providerId || aliasMap[pfx] === providerId) {
      modelId = fullId.slice(slashIdx + 1);
    }
  }
  vfxTestingModelIds.add(fullId);
  renderVideoProviderDetails();
  try {
    const data = await safeFetchJson("/api/providers/models/test", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ provider: providerId, model_id: modelId, model_ref: fullId, kind: "llm", source: "video_flow" }),
    });
    const isOk = Boolean(data && data.success && data.ok !== false);
    vfxModelTestResults[fullId] = { ok: isOk, latency_ms: (data && data.latency_ms) || null, error: (data && data.error) || null };
    if (typeof vfxProviderModelErrors === "undefined") {
      window.vfxProviderModelErrors = {};
    }
    if (isOk) {
      delete vfxProviderModelErrors[providerId];
    } else {
      vfxProviderModelErrors[providerId] = {
        modelId: modelId,
        error: (data && data.error) || "Unknown error",
      };
    }
    if (vfCurrentProvider === providerId) {
      const banner = document.getElementById("vf-models-test-error-banner");
      if (banner) {
        if (!isOk) {
          banner.textContent = "\u2715 Model Test Failed (" + modelId + "): " + ((data && data.error) || "Unknown error");
          banner.style.display = "block";
        } else {
          banner.textContent = "";
          banner.style.display = "none";
        }
      }
    }
  } catch (error) {
    vfxModelTestResults[fullId] = { ok: false, latency_ms: null, error: error.message || "Test failed" };
    if (typeof vfxProviderModelErrors === "undefined") {
      window.vfxProviderModelErrors = {};
    }
    vfxProviderModelErrors[providerId] = {
      modelId: modelId,
      error: error.message || "Test failed",
    };
    if (vfCurrentProvider === providerId) {
      const banner = document.getElementById("vf-models-test-error-banner");
      if (banner) {
        banner.textContent = "\u2715 Model Test Failed (" + modelId + "): " + (error.message || "Test failed");
        banner.style.display = "block";
      }
    }
  } finally {
    vfxTestingModelIds.delete(fullId);
    await refreshCurrentVideoProviderDetail();
  }
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
  const connection = (vfCurrentProviderDetails.connections || []).find(item => String(item.id) === String(connectionId));
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
  const connectionId = String(modal?.dataset.connectionId || "");
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
  const id = String(document.getElementById("vf-connection-modal")?.dataset.connectionId || "");
  if (!id) {
    vfToast("Save the connection first, then Video Flow can run a live test.");
    return;
  }
  await testVideoConnection(id);
}

async function testVideoConnection(connectionId) {
  try {
    await vfPost("/api/video-flow/providers/connections/test", {id: connectionId, provider: vfCurrentProvider});
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
    const details = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(provider.id));
    for (const connection of (details?.connections || [])) {
      if (!connection.is_active) continue;
      try { await vfPost("/api/video-flow/providers/connections/test", {id: connection.id, provider: provider.id}); tested += 1; }
      catch (_) { failed += 1; }
    }
  }
  await loadVideoFlow();
  vfToast(tested + " connection" + (tested === 1 ? "" : "s") + " ready" + (failed ? " · " + failed + " failed" : ""), Boolean(failed));
}

async function deleteVideoConnection(connectionId) {
  try {
    await vfPost("/api/video-flow/providers/connections/delete", {id: connectionId, provider: vfCurrentProvider});
    await openVideoProvider(vfCurrentProvider);
    await loadVideoFlow();
    vfToast("Connection deleted from Video Flow.");
  } catch (error) { vfToast(error.message, true); }
}

async function toggleVideoConnection(connectionId, isActive) {
  try {
    await vfPost("/api/video-flow/providers/connections/toggle", {id: connectionId, is_active: isActive, provider: vfCurrentProvider});
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

// ---------------------------------------------------------------------------
// OAuth account connection (9Router design)
// authorize -> popup/system browser -> relay via postMessage +
// BroadcastChannel("oauth_callback") + localStorage["oauth_callback"] ->
// POST /api/video-flow/oauth/exchange -> active connection.
// ---------------------------------------------------------------------------

let vfOAuthProvider = null;
let vfOAuthCallbackHandled = false;
let vfOAuthPopup = null;
let vfOAuthPollTimer = null;      // 2.5s provider-details poll (belt-and-braces)
let vfOAuthStorageTimer = null;   // 1s localStorage["oauth_callback"] poll
let vfOAuthDevicePollTimer = null; // OpenAI Codex / ChatGPT device-code poll
let vfOAuthChannel = null;        // BroadcastChannel("oauth_callback")
let vfOAuthAuthUrl = "";

const VF_OAUTH_REDIRECT_URI = "http://127.0.0.1:8991/callback";

function vfOAuthCleanup() {
  if (vfOAuthPollTimer) { clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null; }
  if (vfOAuthStorageTimer) { clearInterval(vfOAuthStorageTimer); vfOAuthStorageTimer = null; }
  if (vfOAuthDevicePollTimer) { clearInterval(vfOAuthDevicePollTimer); vfOAuthDevicePollTimer = null; }
  if (vfOAuthChannel) { try { vfOAuthChannel.close(); } catch (_) {} vfOAuthChannel = null; }
  window.removeEventListener("message", vfOAuthOnMessage);
  window.removeEventListener("storage", vfOAuthOnStorage);
  try { if (vfOAuthPopup && !vfOAuthPopup.closed) vfOAuthPopup.close(); } catch (_) {}
  vfOAuthPopup = null;
  const deviceContainer = document.getElementById("vf-oauth-device-container");
  const webContainer = document.getElementById("vf-oauth-web-container");
  if (deviceContainer) deviceContainer.style.display = "none";
  if (webContainer) webContainer.style.display = "";
  const prefixEl = document.getElementById("vf-oauth-title-prefix");
  if (prefixEl) prefixEl.textContent = "Connect ";
}

function vfOAuthOnMessage(event) {
  const data = event.data || {};
  if (data.type === "oauth_callback") {
    vfOAuthHandleCallback(data.data || data); // 9Router wraps the payload in .data
  } else if (data.type === "OAUTH_CALLBACK_SUCCESS") {
    vfOAuthHandleCallback(data);
  }
}

function vfOAuthOnStorage(event) {
  if (event.key === "oauth_callback" && event.newValue) {
    try {
      const payload = JSON.parse(event.newValue);
      localStorage.removeItem("oauth_callback");
      vfOAuthHandleCallback(payload);
    } catch (_) { /* ignore malformed payloads */ }
  }
}

function vfOAuthHandleCallback(payload) {
  if (vfOAuthCallbackHandled) return;
  const code = String(payload?.code || "");
  const state = String(payload?.state || "");
  const error = String(payload?.error || payload?.errorDescription || "");
  if (!code && !error) return;
  vfOAuthCallbackHandled = true;
  try { if (vfOAuthPopup && !vfOAuthPopup.closed) vfOAuthPopup.close(); } catch (_) {}
  if (error) {
    vfOAuthCallbackHandled = false;
    vfOAuthSetStatus("Authorization failed: " + error);
    vfOAuthFocusManualInput();
    return;
  }
  vfOAuthExchange(vfOAuthProvider, code, state);
}

function vfOAuthSetStatus(message) {
  const status = document.getElementById("vf-oauth-status");
  if (status) status.textContent = message;
}

function vfOAuthFocusManualInput() {
  const input = document.getElementById("vf-oauth-code-input");
  if (input) input.focus();
}

async function vfOAuthSuccess(providerId, email) {
  vfOAuthCleanup();
  closeVideoModal("vf-oauth-modal");
  await loadVideoFlow();
  await refreshCurrentVideoProviderDetail(providerId);
  vfToast("Connected " + (email || (vfCurrentProviderDetails?.provider?.name) || providerId) + " successfully!");
}

async function vfOAuthExchange(providerId, code, state) {
  if (!providerId || !code) return;
  try {
    const result = await vfPost("/api/video-flow/oauth/exchange", {
      provider: providerId,
      code: code,
      state: state || "",
      redirect_uri: VF_OAUTH_REDIRECT_URI,
    });
    await vfOAuthSuccess(providerId, result?.email || "");
  } catch (error) {
    vfOAuthCallbackHandled = false; // allow a retry (popup relay or manual paste)
    vfToast(error.message, true);
  }
}

async function openOAuthFlow(providerId) {
  vfOAuthCleanup();
  vfOAuthProvider = providerId;
  vfOAuthCallbackHandled = false;
  vfOAuthAuthUrl = "";
  const modal = document.getElementById("vf-oauth-modal");
  const prefixEl = document.getElementById("vf-oauth-title-prefix");
  const nameEl = document.getElementById("vf-oauth-provider-name");
  if (providerId === "openai_codex") {
    if (prefixEl) prefixEl.textContent = "Sign in with ";
    if (nameEl) nameEl.textContent = "ChatGPT or Codex Subscription";
  } else {
    if (prefixEl) prefixEl.textContent = "Connect ";
    if (nameEl) nameEl.textContent = vfCurrentProviderDetails?.provider?.name || providerId;
  }
  const preview = document.getElementById("vf-oauth-url-preview");
  if (preview) preview.value = "Generating auth link...";
  const input = document.getElementById("vf-oauth-code-input");
  if (input) input.value = "";
  vfOAuthSetStatus("Waiting for popup authorization\u2026");
  const spinner = document.getElementById("vf-oauth-spinner");
  if (spinner) spinner.style.display = "";
  const deviceContainer = document.getElementById("vf-oauth-device-container");
  const webContainer = document.getElementById("vf-oauth-web-container");
  if (deviceContainer) deviceContainer.style.display = "none";
  if (webContainer) webContainer.style.display = "";
  modal?.classList.remove("hidden");

  // Relay channels (9Router): popup postMessage, BroadcastChannel, storage event.
  window.addEventListener("message", vfOAuthOnMessage);
  window.addEventListener("storage", vfOAuthOnStorage);
  try {
    vfOAuthChannel = new BroadcastChannel("oauth_callback");
    vfOAuthChannel.onmessage = (event) => vfOAuthHandleCallback(event.data || {});
  } catch (_) { vfOAuthChannel = null; }

  // Desktop WebView windows share localStorage: poll the relay key every 1s
  // while the modal is open (also covers callbacks that landed before now).
  const checkStoredCallback = function () {
    try {
      const raw = localStorage.getItem("oauth_callback");
      if (!raw) return;
      const payload = JSON.parse(raw);
      localStorage.removeItem("oauth_callback");
      if (payload && payload.timestamp && Date.now() - payload.timestamp < 30000) {
        vfOAuthHandleCallback(payload);
      }
    } catch (_) { /* ignore malformed payloads */ }
  };
  checkStoredCallback();
  vfOAuthStorageTimer = setInterval(checkStoredCallback, 1000);

  try {
    const start = await safeFetchJson("/api/video-flow/oauth/start", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ provider: providerId }),
    });
    if (!start || start.success === false) throw new Error(start?.error || "Could not start the sign-in flow.");
    if (start.imported) {
      vfOAuthCleanup();
      closeVideoModal("vf-oauth-modal");
      await loadVideoFlow();
      await refreshCurrentVideoProviderDetail(providerId);
      vfToast(start.message || ((vfCurrentProviderDetails?.provider?.name || providerId) + " account connected."));
      return;
    }
    if (start.flow === "device") {
      if (deviceContainer) deviceContainer.style.display = "";
      if (webContainer) webContainer.style.display = "none";
      if (providerId === "openai_codex") {
        if (prefixEl) prefixEl.textContent = "Sign in with ";
        if (nameEl) nameEl.textContent = "ChatGPT or Codex Subscription";
      }

      const badgesContainer = document.getElementById("vf-oauth-device-badges");
      if (badgesContainer) {
        badgesContainer.innerHTML = "";
        const codeStr = String(start.user_code || "").trim();
        badgesContainer.title = "Click to copy code";
        badgesContainer.onclick = function () {
          if (navigator.clipboard && codeStr) {
            navigator.clipboard.writeText(codeStr);
            vfToast("Code copied to clipboard: " + codeStr);
          }
        };
        for (let i = 0; i < codeStr.length; i++) {
          const ch = codeStr[i];
          if (ch === "-" || ch === "—" || ch === " ") {
            if (badgesContainer.lastElementChild && !badgesContainer.lastElementChild.classList.contains("vf-code-sep")) {
              const sep = document.createElement("span");
              sep.className = "vf-code-sep";
              sep.textContent = "-";
              badgesContainer.appendChild(sep);
            }
          } else if (ch.trim()) {
            const box = document.createElement("span");
            box.className = "vf-code-box";
            box.textContent = ch;
            badgesContainer.appendChild(box);
          }
        }
      }

      vfOAuthAuthUrl = start.verification_url || "https://auth.openai.com/codex/device";
      if (start.opened === false) {
        try {
          await vfPost("/api/video-flow/providers/oauth/open-browser", { auth_url: vfOAuthAuthUrl });
        } catch (_) {}
      }

      const pollInterval = Math.max(3, parseInt(start.interval, 10) || 5) * 1000;
      const statusEl = document.getElementById("vf-oauth-device-status");
      if (statusEl) statusEl.textContent = "Waiting for you to authorize...";

      if (vfOAuthStorageTimer) {
        clearInterval(vfOAuthStorageTimer);
        vfOAuthStorageTimer = null;
      }
      if (vfOAuthDevicePollTimer) {
        clearInterval(vfOAuthDevicePollTimer);
        vfOAuthDevicePollTimer = null;
      }

      let deviceAttempts = 0;
      const maxDeviceAttempts = 180; // ~15 minutes

      vfOAuthDevicePollTimer = setInterval(async function () {
        deviceAttempts += 1;
        if (deviceAttempts > maxDeviceAttempts) {
          if (vfOAuthDevicePollTimer) {
            clearInterval(vfOAuthDevicePollTimer);
            vfOAuthDevicePollTimer = null;
          }
          if (statusEl) statusEl.textContent = "Authorization timed out. Please try again.";
          return;
        }
        try {
          const res = await safeFetchJson("/api/video-flow/oauth/device-poll", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              provider: providerId,
              device_auth_id: start.device_auth_id || "",
              user_code: start.user_code || "",
            }),
          });
          if (!res) return;
          if (res.status === "approved") {
            if (vfOAuthDevicePollTimer) {
              clearInterval(vfOAuthDevicePollTimer);
              vfOAuthDevicePollTimer = null;
            }
            vfOAuthCleanup();
            closeVideoModal("vf-oauth-modal");
            await loadVideoFlow();
            await refreshCurrentVideoProviderDetail(providerId);
            vfToast("ChatGPT connected (" + (res.account || "active") + ")");
            return;
          } else if (res.status === "pending") {
            if (statusEl && statusEl.textContent !== "Waiting for you to authorize...") {
              statusEl.textContent = "Waiting for you to authorize...";
            }
          } else if (res.status === "error" || (res.success === false && res.error)) {
            if (statusEl) statusEl.textContent = res.error || "Authorization error";
          }
        } catch (_) {}
      }, pollInterval);

      return;
    }
    if (start.flow === "web" && (start.authUrl || start.auth_url)) {
      const authUrl = start.authUrl || start.auth_url;
      vfOAuthAuthUrl = authUrl;
      if (preview) preview.value = authUrl;
      vfOAuthSetStatus(start.message || "Choose your account in the browser that just opened — this app connects automatically.");
      if (start.opened === false) {
        try {
          await vfPost("/api/video-flow/providers/oauth/open-browser", { auth_url: authUrl });
        } catch (_) {}
      }
      let webAttempts = 0;
      if (vfOAuthPollTimer) { clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null; }
      vfOAuthPollTimer = setInterval(async function () {
        webAttempts += 1;
        try {
          const det = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
          const active = (det?.connections || []).some(function (c) { return c.is_active; });
          if (active) {
            clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null;
            closeVideoModal("vf-oauth-modal");
            await loadVideoFlow();
            await refreshCurrentVideoProviderDetail(providerId);
            vfToast((vfCurrentProviderDetails?.provider?.name || providerId) + " account connected.");
            return;
          }
          if (webAttempts > 150) { // ~3 minutes
            clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null;
            vfOAuthSetStatus("Still waiting for sign-in. Complete it in your browser, or press Open in Browser to try again.");
          }
        } catch (_) { /* keep polling */ }
      }, 1200);
      return;
    } else {
      // Local-session import / device flow: no browser popup. Poll status.
      if (preview) preview.value = "Local session import \u2014 no browser needed";
      vfOAuthSetStatus(start.message || "Importing your local sign-in session\u2026");
      const finish = async function () {
        clearInterval(vfOAuthStorageTimer); vfOAuthStorageTimer = null;
        if (vfOAuthPollTimer) { clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null; }
        closeVideoModal("vf-oauth-modal");
        await loadVideoFlow();
        await refreshCurrentVideoProviderDetail(providerId);
        vfToast((vfCurrentProviderDetails?.provider?.name || providerId) + " account connected.");
      };
      let attempts = 0;
      vfOAuthPollTimer = setInterval(async function () {
        attempts += 1;
        try {
          const det = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
          const active = (det?.connections || []).some(function (c) { return c.is_active; });
          if (active) { await finish(); return; }
          if (attempts === 3) {
            // Nudge: pressing start again performs the import after sign-in.
            await safeFetchJson("/api/video-flow/oauth/start", {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({ provider: providerId }),
            }).catch(function () {});
          }
          if (attempts > 60) {
            clearInterval(vfOAuthPollTimer); vfOAuthPollTimer = null;
            vfOAuthSetStatus("No local session found. Sign in inside " + (vfCurrentProviderDetails?.provider?.name || providerId) + " first, then press Add account again.");
          }
        } catch (_) { /* keep polling */ }
      }, 2000);
      return;
    }
  } catch (error) {
    vfOAuthCleanup();
    closeVideoModal("vf-oauth-modal");
    vfToast(error.message, true);
    return;
  }

  // Belt-and-braces: poll provider details every 2.5s; the moment an active
  // connection appears the modal closes and the UI refreshes.
  const startDetailsPoll = function () {
    if (vfOAuthPollTimer) return;
    vfOAuthPollTimer = setInterval(async function () {
      try {
        const details = await safeFetchJson("/api/video-flow/providers/details?provider=" + encodeURIComponent(providerId));
        const conns = (details && details.connections) || [];
        if (conns.some(function (c) { return c.is_active && (c.status === "active" || c.status === "connected"); })) {
          await vfOAuthSuccess(providerId, null);
        }
      } catch (_) { /* keep polling */ }
    }, 2500);
  };

  const isDesktopApp = typeof window.pywebview !== "undefined";
  if (isDesktopApp) {
    // WebView2 popups are unreliable for Google sign-in — open the system
    // default browser instead. The relay page hands the code back through
    // BroadcastChannel/localStorage (same origin) and the 1s poll catches it.
    try {
      await vfPost("/api/video-flow/providers/oauth/open-browser", { auth_url: vfOAuthAuthUrl });
    } catch (_) { /* the copy/paste fallback below still works */ }
    vfOAuthSetStatus("Sign-in opened in your browser \u2014 choose your account there; this app connects automatically.");
    startDetailsPoll();
    return;
  }

  try {
    vfOAuthPopup = window.open(vfOAuthAuthUrl, "oauth_popup", "width=600,height=700");
  } catch (_) { vfOAuthPopup = null; }
  startDetailsPoll();
  if (!vfOAuthPopup) {
    vfOAuthSetStatus("The popup was blocked. Open the login link below, then paste the callback URL here.");
    vfOAuthFocusManualInput();
  }
}

async function vfOAuthManualConnect() {
  const raw = document.getElementById("vf-oauth-code-input")?.value.trim() || "";
  if (!raw) {
    vfToast("Paste the code or the full callback URL first.", true);
    return;
  }
  let code = raw;
  let state = "";
  if (raw.includes("?") || raw.includes("&")) {
    try {
      const url = new URL(raw.startsWith("http") ? raw : "http://127.0.0.1:8991/" + raw.replace(/^\//, ""));
      code = url.searchParams.get("code") || code;
      state = url.searchParams.get("state") || "";
    } catch (_) {}
  }
  if (vfOAuthCallbackHandled) return;
  vfOAuthCallbackHandled = true;
  await vfOAuthExchange(vfOAuthProvider, code, state);
}

async function vfOAuthOpenInBrowser() {
  const url = vfOAuthAuthUrl || document.getElementById("vf-oauth-url-preview")?.value.trim() || "";
  if (!url || url === "Generating auth link...") {
    vfToast("No authorization URL available yet.", true);
    return;
  }
  try {
    const res = await vfPost("/api/video-flow/providers/oauth/open-browser", { auth_url: url });
    if (res && res.success) {
      vfToast("Opened in your default browser.");
      return;
    }
  } catch (_) {}
  window.open(url, "_blank");
}

async function vfOAuthCopyAuthUrl() {
  const value = document.getElementById("vf-oauth-url-preview")?.value.trim() || "";
  if (!value || value === "Generating auth link...") {
    vfToast("No authorization link available yet.", true);
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    vfToast("Authorization link copied.");
  } catch (error) { vfToast(error.message, true); }
}

function closeOAuthModal() {
  vfOAuthCleanup();
  closeVideoModal("vf-oauth-modal");
}

async function refreshVideoOAuthProviders() {
  // The old per-provider OAuth status endpoint is gone; account state now
  // arrives with the provider catalog/details payloads themselves.
  await loadVideoFlow();
  vfToast("Account status refreshed.");
}

// ---------------------------------------------------------------------------
// Google sign-in (one-click, zero-typing) — Video Flow authentication section.
// Browser mode: redirect through /auth/google, Google's account chooser opens
// directly. Desktop mode: the system browser signs in; the app claims the
// pairing token so the session cookie lands in the WebView's own cookie jar.
// ---------------------------------------------------------------------------

let vfGooglePairToken = null;
let vfGooglePairPollTimer = null;

function vfGoogleSetStatus(message) {
  const status = document.getElementById("vf-google-signin-status");
  if (status) status.textContent = message || "";
}

function vfGoogleRenderAccount(user) {
  const card = document.getElementById("vf-google-account-card");
  const row = document.getElementById("vf-google-signin-row");
  if (!card || !row) return;
  if (user && user.email) {
    card.style.display = "flex";
    row.style.display = "none";
    const nameEl = document.getElementById("vf-google-account-name");
    const emailEl = document.getElementById("vf-google-account-email");
    const picEl = document.getElementById("vf-google-account-picture");
    if (nameEl) nameEl.textContent = user.name || user.email;
    if (emailEl) emailEl.textContent = user.email || "";
    if (picEl) {
      if (user.picture) {
        picEl.src = user.picture;
        picEl.style.display = "block";
      } else {
        picEl.removeAttribute("src");
        picEl.style.display = "none";
      }
    }
  } else {
    card.style.display = "none";
    row.style.display = "flex";
  }
}

async function vfGoogleLoadAccount() {
  try {
    const res = await fetch("/api/me", { headers: { "Accept": "application/json" } });
    if (res.status === 401) {
      vfGoogleRenderAccount(null);
      return null;
    }
    const data = await res.json();
    const user = (data && data.authenticated && data.user) ? data.user : null;
    vfGoogleRenderAccount(user);
    return user;
  } catch (error) {
    vfGoogleSetStatus("Backend unreachable — restart Voice Flow.");
    return null;
  }
}

async function vfGoogleSignIn() {
  const btn = document.getElementById("vf-google-signin-btn");
  const label = document.getElementById("vf-google-signin-label");
  if (btn) btn.disabled = true;
  if (label) label.textContent = "Opening Google…";
  vfGoogleSetStatus("");
  const isDesktopApp = typeof window.pywebview !== "undefined";
  try {
    if (!isDesktopApp) {
      // Normal browser: the session cookie is set on the redirect back.
      window.location.href = "/auth/google";
      return;
    }
    // Desktop (pywebview): sign in inside the system default browser, where
    // the Google session already lives, then claim the pairing token here.
    const data = await vfPost("/auth/google/open", {});
    vfGooglePairToken = data && data.pair_token ? String(data.pair_token) : null;
    if (!vfGooglePairToken) throw new Error((data && data.error) || "Could not start Google sign-in.");
    vfGoogleSetStatus("Choose your account in the browser that just opened — this app connects automatically.");
    vfGooglePollPairing();
  } catch (error) {
    vfGoogleSetStatus(error.message || "Sign-in failed. Please try again.");
    if (btn) btn.disabled = false;
    if (label) label.textContent = "Continue with Google";
  }
}

function vfGooglePollPairing() {
  if (vfGooglePairPollTimer) clearInterval(vfGooglePairPollTimer);
  let attempts = 0;
  vfGooglePairPollTimer = setInterval(async function () {
    attempts += 1;
    if (attempts > 80) { // ~2 minutes
      clearInterval(vfGooglePairPollTimer);
      vfGooglePairPollTimer = null;
      const btn = document.getElementById("vf-google-signin-btn");
      const label = document.getElementById("vf-google-signin-label");
      if (btn) btn.disabled = false;
      if (label) label.textContent = "Continue with Google";
      vfGoogleSetStatus("Sign-in did not complete in time. Please try again.");
      return;
    }
    try {
      const res = await fetch("/auth/desktop/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pair_token: vfGooglePairToken }),
      });
      if (res.ok) {
        clearInterval(vfGooglePairPollTimer);
        vfGooglePairPollTimer = null;
        vfGooglePairToken = null;
        const btn = document.getElementById("vf-google-signin-btn");
        const label = document.getElementById("vf-google-signin-label");
        if (btn) btn.disabled = false;
        if (label) label.textContent = "Continue with Google";
        vfGoogleSetStatus("");
        vfToast("Signed in with Google.");
        await vfGoogleLoadAccount();
      }
    } catch (_) { /* keep polling; backend may be busy */ }
  }, 1500);
}

async function vfGoogleLogout() {
  try {
    await vfPost("/auth/logout", {});
  } catch (_) { /* clearing client state regardless */ }
  vfGoogleRenderAccount(null);
  vfToast("Signed out.");
}

let vfLastVerifiedModel = null;

function stripRedundantModelPrefix(provider, modelId) {
  let mid = (modelId || "").trim();
  const prov = (provider || "").toLowerCase().trim();
  if (!mid) return "";
  if (prov === "openrouter") {
    while (mid.toLowerCase().startsWith("openrouter/")) {
      mid = mid.slice("openrouter/".length).trim();
    }
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
    if (mid.toLowerCase().startsWith(pfx.toLowerCase())) {
      mid = mid.slice(pfx.length).trim();
    }
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

function openVideoCustomModelModal(prov) {
  if (prov) {
    vfCurrentProvider = prov;
  }
  const provider = prov || vfCurrentProvider;
  if (!provider) return;
  const modal = document.getElementById("vf-custom-model-modal");
  if (!modal) return;
  modal.dataset.provider = provider;
  const provPrefix = (vfCurrentProviderDetails && vfCurrentProviderDetails.provider && vfCurrentProviderDetails.provider.prefix) || provider;
  modal.dataset.prefix = (provPrefix ? provPrefix + "/" : "");
  const inputEl = document.getElementById("vf-custom-model-id");
  if (inputEl) inputEl.value = "";
  modal.querySelectorAll('.vf-capability-picker input').forEach(input => input.checked = false);
  const out = document.getElementById("vf-custom-model-test-out");
  if (out) { out.style.display = "none"; out.innerHTML = ""; }
  vfLastVerifiedModel = null;
  modal.classList.remove("hidden");
  setTimeout(() => inputEl?.focus(), 50);
}

window.openVideoCustomModelModal = openVideoCustomModelModal;
window.openAddVideoModelModal = openVideoCustomModelModal;
window.vfTestModel = vfTestModelBeforeAdd;
window.vfTestModelBeforeAdd = vfTestModelBeforeAdd;
window.stripRedundantModelPrefix = stripRedundantModelPrefix;

async function vfTestModelBeforeAdd() {
  const modal = document.getElementById("vf-custom-model-modal");
  if (!modal) return false;
  const provider = modal.dataset.provider;
  const prefix = modal.dataset.prefix || (provider ? provider + "/" : "");
  let rawMid = (document.getElementById("vf-custom-model-id")?.value || "").trim();
  const out = document.getElementById("vf-custom-model-test-out");
  const spin = document.getElementById("vf-cm-test-spin");
  const label = document.getElementById("vf-cm-test-label");
  const btn = document.getElementById("vf-custom-model-test-btn");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "Enter a model ID first.";
    }
    return false;
  }
  const mid = stripRedundantModelPrefix(provider, rawMid);
  const fullId = prefix + mid;
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
    const data = await safeFetchJson("/api/providers/models/test", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ provider: provider, model_id: mid, model_ref: fullId, kind: "llm", source: "video_flow" }),
    });
    const ok = Boolean(data && data.success && data.ok !== false);
    if (ok) {
      vfLastVerifiedModel = { provider, modelId: mid, ok: true, data };
      if (out) {
        const latencyText = data.latency_ms ? " (" + data.latency_ms + "ms)" : "";
        const quotaText = data.remaining_pct != null ? " — " + data.remaining_pct + "% quota remaining" : "";
        const msgText = data.message ? `<div style="margin-top:4px; font-size:11px; opacity:0.9;">${vfEscape(data.message)}</div>` : "";
        out.style.background = "rgba(34,197,94,0.08)";
        out.style.border = "1px solid rgba(34,197,94,0.25)";
        out.style.color = "#22c55e";
        out.innerHTML = "✅ Model works" + latencyText + quotaText + msgText;
      }
      return true;
    } else {
      vfLastVerifiedModel = { provider, modelId: mid, ok: false, error: (data && data.error) || "Test failed" };
      if (out) {
        out.style.background = "rgba(239,68,68,0.08)";
        out.style.border = "1px solid rgba(239,68,68,0.25)";
        out.style.color = "#ef4444";
        out.innerHTML = "❌ " + vfEscape((data && data.error) || "Test failed") + "<br><span style='opacity:0.8;'>Sent to provider as: " + vfEscape(fullId) + "</span>";
      }
      return false;
    }
  } catch (error) {
    vfLastVerifiedModel = { provider, modelId: mid, ok: false, error: error.message || "Test failed" };
    if (out) {
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + vfEscape(error.message || "Test failed");
    }
    return false;
  } finally {
    if (spin) spin.style.display = "none";
    if (label) label.textContent = "🧪 Test";
    if (btn) btn.disabled = false;
  }
}

async function saveVideoCustomModel() {
  const modal = document.getElementById("vf-custom-model-modal");
  const provider = modal?.dataset.provider;
  const prefix = modal?.dataset.prefix || (provider ? provider + "/" : "");
  let rawMid = (document.getElementById("vf-custom-model-id")?.value || "").trim();
  const out = document.getElementById("vf-custom-model-test-out");
  const addBtn = modal?.querySelector(".vf-dialog-actions .btn-primary");
  if (!rawMid) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "Enter a model ID first.";
    }
    return;
  }
  const mid = stripRedundantModelPrefix(provider, rawMid);
  const isVerified = Boolean(
    vfLastVerifiedModel &&
    vfLastVerifiedModel.provider === provider &&
    vfLastVerifiedModel.modelId === mid &&
    vfLastVerifiedModel.ok === true
  );

  if (!isVerified) {
    if (addBtn) { addBtn.disabled = true; addBtn.textContent = "Verifying…"; }
    const verifiedOk = await vfTestModelBeforeAdd();
    if (addBtn) { addBtn.disabled = false; addBtn.textContent = "Add model"; }
    if (!verifiedOk) {
      // Verification failed: do NOT add model!
      return;
    }
  }

  try {
    await vfPost("/api/video-flow/providers/models/add", {
      provider,
      model_id: mid,
      display_name: "",
    });
    closeVideoModal("vf-custom-model-modal");
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(provider);
    const latencyMsg = vfLastVerifiedModel?.data?.latency_ms ? ` (${vfLastVerifiedModel.data.latency_ms}ms)` : "";
    vfToast(`Model '${mid}' verified and added successfully!${latencyMsg}`);
  } catch (error) {
    if (out) {
      out.style.display = "block";
      out.style.background = "rgba(239,68,68,0.08)";
      out.style.border = "1px solid rgba(239,68,68,0.25)";
      out.style.color = "#ef4444";
      out.innerHTML = "❌ " + vfEscape(error.message || "Failed to add model");
    }
    vfToast(error.message, true);
  }
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

async function deleteVideoCustomModel(modelId, providerId) {
  const provider = vfCurrentProvider;
  if (!provider) return;
  try {
    await vfPost("/api/video-flow/providers/models/delete", { id: modelId, provider: providerId || provider });
    await loadVideoFlow();
    await refreshCurrentVideoProviderDetail(provider);
    vfToast("Custom model removed.");
  } catch (error) { vfToast(error.message, true); }
}

async function testVideoModel(fullId, btn) {
  if (btn) { btn.textContent = "⏳"; btn.disabled = true; }
  let row = null;
  try { row = document.querySelector('.vf-provider-model-row[data-full-id="' + CSS.escape(fullId) + '"]'); } catch (e) {}
  const out = row ? row.querySelector(".vf-model-test-out") : null;
  if (out) out.textContent = "testing…";
  const slash = fullId.indexOf("/");
  const aliasMap = {
    agy: "antigravity",
    codex: "openai_codex",
    nim: "nvidia_nim",
    vx: "vertex_ai",
    zen: "opencode_zen",
    "claude-code": "claude_code",
    lmstudio: "lm_studio",
    llamacpp: "llama_cpp"
  };
  let provider = slash > 0 ? fullId.slice(0, slash) : "";
  if (aliasMap[provider]) provider = aliasMap[provider];
  const modelId = slash > 0 ? fullId.slice(slash + 1) : fullId;
  try {
    const data = await safeFetchJson("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: provider, model_id: modelId, model_ref: fullId, kind: "llm", source: "video_flow" }),
    });
    const ok = Boolean(data && data.success && data.ok !== false);
    if (out) out.innerHTML = ok
      ? '<span style="color:#22c55e;font-weight:700;">\u2705 ' + (data.latency_ms || "") + 'ms</span>'
      : '<span style="color:#ef4444;font-weight:600;">\u2715 ' + vfEscape((data && data.error) || "Test failed") + '</span>';
  } catch (e) {
    if (out) out.innerHTML = '<span style="color:#ef4444;font-weight:600;">\u2715 ' + vfEscape(e.message) + '</span>';
  } finally {
    if (btn) { btn.textContent = "\u2697"; btn.disabled = false; }
  }
}

let vfCustomProviders = [];

async function loadCustomProviders() {
  try {
    const data = await safeFetchJson("/api/video-flow/custom-providers/list");
    vfCustomProviders = (data && data.providers) || [];
  } catch (e) { vfCustomProviders = []; }
  renderCustomProviderGrid();
}

function renderCustomProviderGrid() {
  const grid = document.getElementById("vf-custom-provider-grid");
  if (!grid) return;
  const asProviders = vfCustomProviders.map(function (p) {
    const models = p.models || [];
    return {
      id: p.id,
      name: p.name || p.id,
      icon: (p.name || "C")[0].toUpperCase(),
      category: "api_key",
      status: (p.api_key || p.has_secret) ? "connected" : "disconnected",
      active_count: models.length,
      connection_count: (p.connections || ((p.api_key || p.has_secret) ? [1] : [])).length,
    };
  });
  renderVideoProviderGrid("vf-custom-provider-grid", asProviders);
}

window._vfCustomTestResults = {};

async function testCustomModel(fullId, btn) {
  if (btn) { btn.textContent = "\u23f3"; btn.disabled = true; }
  const card = document.querySelector('[data-custom-full-id="' + CSS.escape(fullId) + '"]');
  const out = card ? card.querySelector(".vfc-test-out") : null;
  if (out) out.textContent = "testing\u2026";
  const slash = fullId.indexOf("/");
  const provider = fullId.slice(0, slash);
  const modelId = fullId.slice(slash + 1);
  try {
    const data = await safeFetchJson("/api/providers/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: provider, model_id: modelId, model_ref: fullId, kind: "llm", source: "video_flow" }),
    });
    const ok = Boolean(data && data.success && data.ok !== false);
    window._vfCustomTestResults[fullId] = { ok: ok, latencyMs: (data && data.latency_ms) || null, error: (data && data.error) || null };
    if (out) out.innerHTML = ok
      ? '<span style="color:#22c55e;font-weight:700;">\u2705 ' + (data.latency_ms || "") + 'ms</span>'
      : '<span style="color:#ef4444;font-weight:600;">\u2715 ' + vfEscape((data && data.error) || "Test failed") + '</span>';
  } catch (e) {
    window._vfCustomTestResults[fullId] = { ok: false, error: e.message };
    if (out) out.innerHTML = '<span style="color:#ef4444;font-weight:600;">\u2715 ' + vfEscape(e.message) + '</span>';
  } finally {
    if (btn) { btn.textContent = "\u2697"; btn.disabled = false; }
  }
}

function openCustomProviderModal() {
  const editIdEl = document.getElementById("vfc-edit-id");
  if (editIdEl) editIdEl.value = "";
  const titleEl = document.getElementById("vfc-modal-title");
  if (titleEl) titleEl.textContent = "Add model provider";
  const saveBtn = document.getElementById("vfc-save-btn");
  if (saveBtn) saveBtn.textContent = "Add provider";
  const nameEl = document.getElementById("vfc-name");
  if (nameEl) nameEl.value = "";
  const urlEl = document.getElementById("vfc-url");
  if (urlEl) urlEl.value = "";
  const keyEl = document.getElementById("vfc-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Enter API key";
  }
  const formatEl = document.getElementById("vfc-format");
  if (formatEl) formatEl.value = "openai";
  const headersEl = document.getElementById("vfc-headers");
  if (headersEl) headersEl.value = "";
  const list = document.getElementById("vfc-model-list");
  if (list) list.innerHTML = "";
  const err = document.getElementById("vfc-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("vfc-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("vf-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
  vfcAddModelRow();
}

async function openEditCustomProviderModal(providerId) {
  let p = (vfCustomProviders || []).find(item => item.id === providerId);
  if (!p && vfCurrentProviderDetails && vfCurrentProviderDetails.provider && vfCurrentProviderDetails.provider.id === providerId) {
    p = Object.assign({}, vfCurrentProviderDetails.provider);
    if (vfCurrentProviderDetails.connections && vfCurrentProviderDetails.connections[0]) {
      p.base_url = p.base_url || (vfCurrentProviderDetails.connections[0].metadata && vfCurrentProviderDetails.connections[0].metadata.base_url);
    }
  }
  if (!p) {
    try {
      const res = await vfGet("/api/video-flow/custom-providers");
      if (res && res.providers) {
        vfCustomProviders = res.providers;
        p = (vfCustomProviders || []).find(item => item.id === providerId);
      }
    } catch (e) {
      console.warn("Could not fetch custom providers for edit modal:", e);
    }
  }
  const editIdEl = document.getElementById("vfc-edit-id");
  if (editIdEl) editIdEl.value = providerId;
  const titleEl = document.getElementById("vfc-modal-title");
  if (titleEl) titleEl.textContent = "Edit " + ((p && p.name) || "Provider");
  const saveBtn = document.getElementById("vfc-save-btn");
  if (saveBtn) saveBtn.textContent = "Save Changes";
  const nameEl = document.getElementById("vfc-name");
  if (nameEl) nameEl.value = (p && p.name) || "";
  const urlEl = document.getElementById("vfc-url");
  if (urlEl) urlEl.value = (p && p.base_url) || "";
  const keyEl = document.getElementById("vfc-key");
  if (keyEl) {
    keyEl.value = "";
    keyEl.placeholder = "Leave blank to keep existing key";
  }
  const formatEl = document.getElementById("vfc-format");
  if (formatEl) formatEl.value = (p && p.api_format) || "openai";
  const headersEl = document.getElementById("vfc-headers");
  if (headersEl) {
    headersEl.value = p && p.headers ? (typeof p.headers === "string" ? p.headers : JSON.stringify(p.headers, null, 2)) : "";
  }
  const list = document.getElementById("vfc-model-list");
  if (list) list.innerHTML = "";
  const models = (p && p.models) || [];
  if (models.length > 0) {
    models.forEach(m => {
      const mid = typeof m === "string" ? m : (m.model_id || m.id || "");
      vfcAddModelRow(mid);
    });
  } else {
    vfcAddModelRow();
  }
  const err = document.getElementById("vfc-error");
  if (err) { err.style.display = "none"; err.textContent = ""; }
  const testOut = document.getElementById("vfc-test-out");
  if (testOut) { testOut.style.display = "none"; testOut.textContent = ""; }
  const modal = document.getElementById("vf-custom-provider-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeCustomProviderModal() {
  const modal = document.getElementById("vf-custom-provider-modal");
  if (modal) modal.classList.add("hidden");
  const editIdEl = document.getElementById("vfc-edit-id");
  if (editIdEl) editIdEl.value = "";
}

function vfcAddModelRow(initialVal) {
  const list = document.getElementById("vfc-model-list");
  if (!list) return;
  const row = document.createElement("div");
  row.className = "vfc-model-row";
  row.style.cssText = "display:flex;gap:6px;margin-bottom:6px;";
  row.innerHTML = '<input class="vfc-mid" placeholder="Model ID (e.g. deepseek-chat)" value="' + (initialVal ? vfEscape(initialVal) : '') + '" style="flex:1;padding:7px;border:1px solid var(--border-color);border-radius:6px;background:var(--surface-2);color:var(--text);">' +
    '<button class="vf-text-button danger" onclick="this.parentElement.remove()">×</button>';
  list.appendChild(row);
}

async function testVideoCustomProviderFromModal() {
  const base_url = (document.getElementById("vfc-url")?.value || "").trim();
  const api_key = (document.getElementById("vfc-key")?.value || "").trim();
  const api_format = document.getElementById("vfc-format")?.value || "openai";
  const edit_id = (document.getElementById("vfc-edit-id")?.value || "").trim();
  const rawHeaders = (document.getElementById("vfc-headers")?.value || "").trim();
  const testOut = document.getElementById("vfc-test-out");
  const testBtn = document.getElementById("vfc-test-btn");

  const modelInputs = Array.from(document.querySelectorAll("#vfc-model-list .vfc-model-row .vfc-mid"));
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
    const data = await safeFetchJson("/api/video-flow/custom-providers/test", {
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

async function saveCustomProvider() {
  const err = document.getElementById("vfc-error");
  const editId = (document.getElementById("vfc-edit-id")?.value || "").trim();
  const name = (document.getElementById("vfc-name")?.value || "").trim();
  const base_url = (document.getElementById("vfc-url")?.value || "").trim();
  const api_key = (document.getElementById("vfc-key")?.value || "").trim();
  const api_format = document.getElementById("vfc-format")?.value || "openai";
  const rawHeaders = (document.getElementById("vfc-headers")?.value || "").trim();
  const models = Array.from(document.querySelectorAll("#vfc-model-list .vfc-model-row .vfc-mid"))
    .map(function (i) { return i.value.trim(); })
    .filter(Boolean)
    .map(function (mid) { return { model_id: mid, context_window: 128000, max_output_tokens: 8192, input_types: ["text"], output_types: ["text"] }; });
  
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
    const endpoint = editId ? "/api/video-flow/custom-providers/update" : "/api/video-flow/custom-providers/add";
    const payload = {
      id: editId || undefined,
      name: name,
      base_url: base_url,
      api_format: api_format,
      headers: headersObj,
      models: models,
    };
    if (api_key || !editId) {
      payload.api_key = api_key;
    }

    const data = await safeFetchJson(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!data || !data.success) throw new Error(data?.error || (editId ? "Could not update provider." : "Could not add provider."));
    closeCustomProviderModal();
    vfCustomProviders = data.providers || [];
    renderCustomProviderGrid();
    if (editId && vfCurrentProvider === editId) {
      openVideoProvider(editId);
    }
    if (typeof vfToast === "function") vfToast(editId ? "Custom provider updated." : "Custom provider added.");
  } catch (e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = "block";
    }
  }
}

async function deleteCustomProvider(id) {
  try {
    const data = await safeFetchJson("/api/video-flow/custom-providers/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id }),
    });
    vfCustomProviders = (data && data.providers) || [];
    renderCustomProviderGrid();
    if (typeof vfToast === "function") vfToast("Custom provider deleted.");
  } catch (e) {
    if (typeof vfToast === "function") vfToast(e.message || "Failed to delete custom provider", true);
  }
}

async function vfDeleteCustomProviderWhole(providerId) {
  const proceed = typeof vfConfirm === "function" 
    ? await vfConfirm("Delete this custom provider, its API key, and all of its connections? This cannot be undone.")
    : confirm("Delete this custom provider, its API key, and all of its connections? This cannot be undone.");
  if (!proceed) return;
  await deleteCustomProvider(providerId);
  const stillThere = (vfCustomProviders || []).some(function (p) { return p.id === providerId; });
  if (stillThere) return; // deletion failed; deleteCustomProvider already showed the error toast
  closeVideoProvider();
  await loadVideoFlow();
}

async function copyVideoModelId(modelId, btnEl) {
  try {
    await navigator.clipboard.writeText(modelId);
    vfToast("Model ID copied: " + modelId);
    if (btnEl && btnEl.querySelector && btnEl.querySelector("svg")) {
      btnEl.classList.add("copied");
      setTimeout(function () { btnEl.classList.remove("copied"); }, 1500);
    }
  } catch (_) { vfToast(modelId); }
}
function previewVideoFlow(videoId) {
  const video = vfVideos.find(item => String(item.id) === String(videoId));
  if (!video) return;
  vfPreviewVideo = video;
  const player = document.getElementById("vf-preview-player");
  const title = document.getElementById("vf-preview-title");
  const download = document.getElementById("vf-preview-download");
  const container = document.querySelector("#vf-preview-modal .vf-player-container");
  const viewUrl = video.view_url || (`/api/video-flow/videos/file?id=` + encodeURIComponent(video.id));
  const downloadUrl = video.download_url || (`/api/video-flow/videos/file?id=` + encodeURIComponent(video.id) + `&download=1`);

  if (title) title.textContent = video.title;
  if (download) {
    download.href = downloadUrl;
    download.onclick = (e) => {
      e.preventDefault();
      downloadVideoFlow(video.id, download);
    };
  }

  // Set media source for native controls bar if available
  if (player) {
    player.setAttribute("src", viewUrl);
    player.src = viewUrl;
    player.load();
    player.play().catch(() => {});
  }

  // Fetch V3 Program & mount real Layered WebGL VideoPlayerV3 (Three.js + PixiJS)
  safeFetchJson(`/api/video-flow/v3/program?id=${encodeURIComponent(videoId)}`)
    .then(data => {
      if (data && data.success && (data.program || data.scenes) && container && window.V3CanvasPlayer) {
        window.V3CanvasPlayer.mount(container, data, {
          syncMediaElement: player,
          bottomPadding: 52,
          autoPlay: true,
        }).catch(err => {
          console.warn("[VideoFlow] V3CanvasPlayer mount warning:", err);
        });
      }
    })
    .catch(err => {
      console.warn("[VideoFlow] Could not load V3 program:", err);
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
    if (!response.ok) throw new Error(`Could not fetch video file (${response.status})`);
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
  try {
    const data = await safeFetchJson("/api/video-flow/videos/retry", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: videoId}),
    });
    if (!data || !data.success) {
      vfToast(data?.error || "Could not retry that video.", true);
      return;
    }
    const retriedVideo = data.video || { id: data.job_id || videoId, status: "queued", progress: 0, stage: "Queued" };
    vfActiveVideoId = retriedVideo.id || videoId;
    const idx = vfVideos.findIndex(item => item.id === videoId);
    if (idx !== -1) {
      vfVideos[idx] = retriedVideo;
    } else {
      vfVideos.unshift(retriedVideo);
    }
    updateGenerationStepper(retriedVideo);
    vfStartLiveStopwatch(retriedVideo, "Queued");
    renderVideoHistory();
    scheduleVideoFlowPolling(true);
    vfToast("Retrying video generation…");
  } catch (err) {
    vfToast(err.message || "Could not retry that video.", true);
  }
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
    const data = await safeFetchJson("/api/video-flow/videos/delete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: videoId, confirmation: VF_PERMANENT_CONFIRMATION}),
    });
    if (!data || !data.success) throw new Error(data?.error || "Could not delete video.");
    vfVideos = vfVideos.filter(video => video.id !== videoId);
    cancelVideoDelete();
    renderVideoHistory();
    vfToast("Video and all project files were permanently deleted from this PC.");
  } catch (error) {
    vfToast(error.message || "Could not delete video.", true);
  }
}

function closeVideoModal(modalId) {
  const modal = document.getElementById(modalId);
  modal?.classList.add("hidden");
  if (modalId === "vf-model-picker-modal") {
    // Invalidate this file's pending picker work (async catalog loads and
    // saves compare their session before touching the DOM) and restore focus
    // to the control that opened the dialog.
    vfPickerSession = null;
    vfPickerSavingRef = null;
    const invoking = vfPickerInvokingElement;
    vfPickerInvokingElement = null;
    if (invoking && typeof invoking.focus === "function" && invoking.isConnected) {
      try { invoking.focus(); } catch (_) { /* element gone */ }
    }
  }
  if (modalId === "vf-oauth-modal") {
    vfOAuthCleanup();
  }
  if (modalId === "vf-preview-modal") {
    const player = document.getElementById("vf-preview-player");
    player?.pause();
    if (player) player.removeAttribute("src");
    const container = document.querySelector("#vf-preview-modal .vf-player-container");
    if (container && window.V3CanvasPlayer) {
      window.V3CanvasPlayer.destroy(container);
    }
    vfPreviewVideo = null;
  }
}

function vfToast(message, isError = false) {
  const toast = document.getElementById("vf-toast");
  if (!toast) return;
  toast.textContent = cleanErrorMessage(message);
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(vfToast.timer);
  vfToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
}
window.vfToast = vfToast;


function vfSafeMediaFilename(title, defaultName = "video", ext = ".mp4") {
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

async function downloadVideoFlow(videoId, btn) {
  if (!videoId) return;
  if (btn && btn.classList.contains("is-downloading")) return;

  const originalHtml = btn ? btn.innerHTML : "↓ Download";
  if (btn) {
    btn.classList.add("is-downloading");
    btn.disabled = true;
    btn.innerHTML = `<span class="vf-dl-spinner"></span> Downloading...`;
  }

  try {
    const video = (typeof vfVideos !== "undefined" && Array.isArray(vfVideos))
      ? vfVideos.find(v => String(v.id) === String(videoId))
      : ((typeof vfPreviewVideo !== "undefined" && vfPreviewVideo && String(vfPreviewVideo.id) === String(videoId)) ? vfPreviewVideo : null);

    const videoTitle = (video && video.title ? video.title : "").trim();
    const titleParam = videoTitle ? `&title=${encodeURIComponent(videoTitle)}` : "";
    let targetUrl = `/api/video-flow/videos/file?id=${encodeURIComponent(videoId)}&download=1${titleParam}`;
    let response = await fetch(targetUrl);
    if (!response.ok) {
      response = await fetch(`/api/video-flow/videos/${encodeURIComponent(videoId)}/file?download=1${titleParam}`);
    }
    if (!response.ok) {
      throw new Error(`Video file is not available (${response.status})`);
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
          btn.innerHTML = `<span class="vf-dl-spinner"></span> ${pct}%`;
        }
      }
      blob = new Blob(chunks, { type: "video/mp4" });
    } else {
      const rawBlob = await response.blob();
      blob = new Blob([rawBlob], { type: "video/mp4" });
    }

    const disposition = response.headers.get("Content-Disposition") || "";
    let filename = vfSafeMediaFilename(videoTitle || `video_${String(videoId).slice(0, 12)}`, "video", ".mp4");
    if (disposition.includes("filename*=UTF-8''")) {
      const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
      if (match && match[1]) {
        try {
          filename = decodeURIComponent(match[1].trim());
        } catch (_) {}
      }
    } else if (disposition.includes("filename=")) {
      const m = disposition.match(/filename=["']?([^"';]+)["']?/);
      if (m && m[1]) {
        const parsed = m[1].trim();
        if (!parsed.startsWith("video_") || !videoTitle) {
          filename = parsed;
        }
      }
    }
    if (!filename.toLowerCase().endsWith(".mp4")) {
      filename = filename.replace(/\.[a-zA-Z0-9]{2,5}$/, "") + ".mp4";
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
    if (typeof vfToast === "function") {
      vfToast(`Downloaded "${filename}"`, false);
    }

    setTimeout(() => {
      if (btn) {
        btn.classList.remove("is-success");
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }, 2500);
  } catch (err) {
    console.error("Video download error:", err);
    if (btn) {
      btn.classList.remove("is-downloading");
      btn.classList.add("is-error");
      btn.innerHTML = `⚠ Failed`;
    }
    if (typeof vfToast === "function") {
      vfToast(err.message || "Failed to download video", true);
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

function downloadPreviewVideo(btn) {
  if (vfPreviewVideo && vfPreviewVideo.id) {
    downloadVideoFlow(vfPreviewVideo.id, btn);
  } else {
    if (typeof vfToast === "function") vfToast("No active preview video", true);
  }
}

window.downloadVideoFlow = downloadVideoFlow;
window.downloadPreviewVideo = downloadPreviewVideo;
