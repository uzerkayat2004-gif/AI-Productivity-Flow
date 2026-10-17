"""Single source of truth for every onboarding voiceover (welcome tour + feature guides).

Each clip is a list of caption lines. The generator speaks the lines as one take,
so the captions, the beat timings and the audio always come from the same words.
"beats" name a word (case-insensitive, first match at or after the given line)
whose spoken start time drives an on-screen highlight.

Claims verified against the app code (Oct 17, 2026):
- Read mode: built-in voices with no API key. Offline voices (Windows SAPI5 /
  macOS system voices, tts_engine._synthesize_sapi) stay on the device; Edge
  voices are online and free (index.html exec-audio-online-hint).
- Summary (Audio Flow) and Video Flow's NotebookLM engine use the user's own
  NotebookLM connection: sign in with Google, no API key (index.html
  vf-nlm-no-key-badge, af-summary-active-model-detail).
- Video Flow formats: Auto-Adaptive, Brief, Vertical short, Explainer,
  Cinematic (index.html vf-format-grid). The App engine (built-in) is optional.
- Voice Flow defaults to local, offline models (index.html exec-policy-model-detail:
  "Local · offline · no API key needed"); Nemotron and S1-mini are local downloads.
- API keys are kept in the local settings database (storage.api_keys); they are
  NOT encrypted, so the narration says "stays on this computer", never "encrypted".
"""

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-4%"          # one fixed rate for every clip
LEAD_IN_S = 0.40      # silence before the first word (matches the earlier pipeline)
TAIL_S = 0.80         # music tail after the last word
TARGET_LUFS = -20.0   # integrated loudness of every *_mixed.mp3 (and *_raw.mp3)
BGM_BELOW_VOICE_DB = 25.0  # music bed level under the voice, identical in every clip

CLIPS = {
    # ---------------- Welcome tour ----------------
    "scene_1": {
        "lines": [
            "Welcome to AI Productivity Flow!",
            "It's free, open source, and private, so your data stays on your device.",
            "Turn text into video, text into audio, and your voice into text, without switching apps.",
        ],
        "beats": {"video": ("video", 2), "audio": ("audio", 2), "voice": ("voice", 2)},
    },
    "scene_2": {
        "lines": [
            "Meet Video Flow!",
            "Paste any text or select an article, and it becomes an animated explainer video with a voiceover.",
            "It uses your own NotebookLM account. Just sign in with Google: no API keys, nothing to pay.",
        ],
    },
    "scene_2_mac": {
        "lines": [
            "Meet Video Flow!",
            "Paste any text or select an article, and it becomes an animated explainer video with a voiceover.",
            "Video Flow is coming to Mac soon. It's available on Windows now.",
        ],
    },
    "scene_3": {
        "lines": [
            "Meet Audio Flow!",
            "Highlight text anywhere, and tap the button that pops up.",
            "Read mode reads it aloud with built-in voices, no API key needed.",
            "Summary uses your NotebookLM account. Just sign in with Google.",
        ],
    },
    "scene_4": {
        "lines": [
            "Meet Voice Flow!",
            "Speak naturally into any app, and your words are typed and polished right where you're working.",
            "It runs locally on built-in models, so there's no API key to set up.",
        ],
    },
    "scene_5": {
        "lines": [
            "Welcome to our community!",
            "Star us on GitHub, and share your feedback to help shape what comes next.",
            "Click Get Started to begin. No API keys needed.",
        ],
        "beats": {"github": ("star", 1), "feedback": ("feedback", 1), "start": ("get", 2)},
    },
    # ---------------- Audio Flow guide ----------------
    "af_guide_step1": {
        "lines": [
            "Welcome to Audio Flow.",
            "Read mode reads any text word for word, with built-in voices and no API key.",
            "Summary mode uses NotebookLM to explain it with one narrator, or as a two-host podcast.",
        ],
    },
    "af_guide_step2": {
        "lines": [
            "Step two is your voices.",
            "Offline voices stay on your device, and Edge voices are online and free.",
            "API keys are optional, only for extra voices like Gemini, and they stay on this computer.",
        ],
    },
    "af_guide_step3": {
        "lines": [
            "Step three is your Audio History.",
            "Every summary is saved on this computer.",
            "Open the history anytime to search, replay, and download the MP3 with one click.",
        ],
    },
    "af_guide_step4": {
        "lines": [
            "Finally, use Audio Flow anywhere, without switching apps.",
            "Highlight text on any page, tap the floating button, and choose Read or Summary.",
            "A small player shows the progress while you keep working.",
        ],
    },
    # ---------------- Video Flow guide (Windows only; no guide on Mac) ----------------
    "vf_guide_step1": {
        "lines": [
            "Welcome to Video Flow.",
            "Drop in a document, or paste your notes.",
            "Then pick a format: Auto-Adaptive, Brief, Vertical Short, Explainer, or Cinematic, the longest, story-style video.",
        ],
    },
    "vf_guide_step2": {
        "lines": [
            "Step two is your video engine.",
            "NotebookLM uses your own Google account. Just sign in: no API keys, nothing to pay.",
            "The built-in App engine is optional, and needs your own API key.",
        ],
    },
    "vf_guide_step3": {
        "lines": [
            "Step three is your Video Library.",
            "Every video is saved on this computer.",
            "Filter by status, search past videos, and download the MP4 with one click.",
        ],
    },
    "vf_guide_step4": {
        "lines": [
            "Finally, Video Flow works anywhere in Windows.",
            "Highlight text on any page, and tap the floating button.",
            "Your video is made in the background while you keep working.",
        ],
    },
    # ---------------- Voice Flow guide ----------------
    "voiceflow_guide_step1": {
        "lines": [
            "Welcome to Voice Flow.",
            "Speak naturally, and your words are typed straight into any app.",
            "Your dashboard tracks your history, your speaking speed, and your daily streak.",
        ],
    },
    "voiceflow_guide_step2": {
        "lines": [
            "Step two is your dictionary and styles.",
            "Add names and jargon so they're always spelled right, with polishing on or off.",
            "Turn polishing on for voice commands, like: Hey Voice Flow, make this an email.",
        ],
    },
    "voiceflow_guide_step3": {
        "lines": [
            "Step three is your AI models.",
            "Voice Flow runs locally on built-in models, so no API key is needed.",
            "We recommend Nemotron for speech, and S1-mini by Superwhisper for polishing. Cloud keys are optional.",
        ],
    },
    "voiceflow_guide_step4": {
        "lines": [
            "Finally, dictate anywhere in Windows.",
            "Hold the middle mouse button, or press Control plus Windows, and speak into any app.",
            "Voice Flow types your words right where your cursor is.",
        ],
    },
    "voiceflow_guide_step4_mac": {
        "lines": [
            "Finally, dictate anywhere on your Mac.",
            "Press Command plus Option, and speak into any app.",
            "Voice Flow types your words right where your cursor is.",
        ],
    },
}
