# 🎬 Video Flow Architecture: Multimodal Explainer Pipeline

> **Canonical System Documentation**  
> **Package:** `voice_flow.video_flow_engine`  
> **Status:** Production v1.0.0 Architecture  

---

## 1. Core Architectural Pipeline

Video Flow converts articles, technical documentation, or selected text into structured visual explainer videos with synchronized voiceover narration. 

Rather than relying on unconstrained generative video prompting, Video Flow operates through a controlled four-stage pipeline:

```
[1. Source Input]
   Text selection, markdown, PDF, or Google NotebookLM document
         │
         ▼
[2. AI Concept & Pedagogy Planning]
   Extract core thesis, conceptual chunks, key entities, and relationships
   (Gemini, OpenAI, Claude, Groq, or Local Fallback)
         │
         ▼
[3. Creative Director & Scene Authoring]
   Map concepts into pedagogical scene programs (statement, process, diagram, metrics)
   Apply visual hierarchy, pacing, layout solver, and visual signature
         │
         ▼
[4. Controlled Rendering & Audio Synthesis]
   Narova / Code2Video / Canvas-WebGL composition + TTS voiceover synthesis
   (Edge TTS, Cartesia, ElevenLabs, OpenAI TTS)
         │
         ▼
[5. Finished Explainer Video]
   1080p MP4 with synchronized narration and captions, saved to Downloads folder
```

---

## 2. Pipeline Subsystems

### A. Understanding & Scene Authoring (`scene_author.py`, `visual_plan_v2.py`)
- **Intent Extraction**: Ingests unstructured source text and decomposes it into discrete conceptual beats.
- **Pedagogical Archetypes**: Assigns appropriate visual archetypes to each beat:
  - `statement`: Core takeaway or thesis.
  - `process`: Step-by-step sequential or workflow diagrams.
  - `comparison`: Side-by-side contrast of concepts or metrics.
  - `metric`: Quantitative emphasis with highlighted numeric callouts.
  - `diagram`: Structural cards and hierarchical relationships.

### B. Creative Director (`creative_director.py`, `visual_director_v2.py`)
- **Pacing & Rhythm**: Calculates target durations based on narration script length and viewer cognitive load.
- **Visual Diversity**: Ensures consecutive scenes do not repeat identical layouts or color balances.
- **Layout Solver (`layout_solver_v21.py`)**: Computes bounds, text reflow, and element spacing deterministically to avoid collision or overflow across screen resolutions.

### C. Controlled Rendering Engines (`code2video_runner.py`, `narova_runner.py`)
- **Narova / Code2Video Path**: Compiles scene programs into styled DOM elements, CSS transitions, and SVG vectors rendered via headless browser or canvas pipelines.
- **Deterministic Local Fallback**: When external LLM APIs fail, time out, or hit rate limits, Video Flow activates an offline deterministic visual synthesis path that constructs cards and kinetic text locally.

### D. Narration & Voiceover Synchronization (`voice_provider_worker.py`)
- Narration scripts are segmented per scene and rendered via the active audio provider:
  - **Edge TTS**: High quality, zero cost, no API key required.
  - **Cartesia / ElevenLabs**: Low-latency, ultra-expressive neural voices.
  - **OpenAI / Google Cloud TTS**: Standard cloud text-to-speech.
- Audio durations drive precise timeline alignment so visual transitions coincide with spoken phrases.

### E. Google NotebookLM Integration (`notebooklm/`)
- Native Google OAuth pairing allows users to query NotebookLM notebooks and generate audio/visual overviews from curated research collections.

### F. Media Export & Management (`video_flow_service.py`)
- Jobs execute asynchronously via background process workers (`process_manager.py`).
- Rendered MP4 files are validated (header check, duration check, non-zero size), tagged with sanitized metadata, and saved automatically to the user's `Downloads` folder.
- Video status and history are recorded in SQLite (`video_flow_jobs` and `history` tables).

---

## 3. Reliability & Invariants

1. **Guaranteed Completion**: Video generation will never fail silently or hang indefinite workers. Process timeouts and watchdog monitors kill stalled renderers and trigger fallback strategies.
2. **Offline-Capable Fallback**: Core layout and rendering components operate locally without external subscriptions.
3. **Loopback Only**: All inter-process communication between GUI, workers, and API server occurs strictly over `127.0.0.1`.
