# 🎬 Video Flow Architecture: Hybrid Rendering Engine

> **Version:** 2.0-hybrid  
> **Status:** Implemented & Verified Baseline  
> **Primary Runtime:** Python 3.10+ Orchestration & Remotion 4 / Canvas / WebGL Production  
> **Canonical Contract:** `src/voice_flow/video_flow_engine/contracts.py` & `src/voice_flow/video_generation/contracts.py`

---

## 1. Core Architectural Philosophy

Video Flow is a source-grounded visual explanation system. Its objective is simple:

> **The viewer should understand the source content without having to read it.**

Rather than treating video generation as a black-box text-to-video prompt, Video Flow separates **Understanding & Pedagogy (The Brain)** from **Visual Production (The Renderers)**:

```text
Source Input (Text, URL, Document, Code)
                    ↓
        Evidence Extraction & Grounding
   (Claims, Entities, Spans, Provenance, Uncertainty)
                    ↓
           Video Flow Brain & Director
      (Pedagogical Planning & Scene Programs)
                    ↓
            Hybrid Render Router
       ↙             ↓             ↘
Procedural 2D    WebGL / 3D    Generative Video
  (Remotion)      (Canvas)       (Veo / Future)
       ↓             ↓             ↓
      ───────────────────────────────
                    ↓
          Narration & Audio Sync
                    ↓
           Automated QA & Repair
                    ↓
           Final Explainer MP4
```

---

## 2. Subsystem Landscape & Status

### ✅ Implemented Components

| Component | Source Path | Description |
| :--- | :--- | :--- |
| **Evidence Assembly** | [`src/voice_flow/video_flow_engine/evidence.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_flow_engine/evidence.py) | Deterministic extraction of claims, entities, relationships, confidence, and provenance from raw sources. |
| **Source Adapters** | [`src/voice_flow/video_flow_engine/sources.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_flow_engine/sources.py) | Normalizes plaintext, markdown, URLs, PDFs, and screenshots with byte limits and chunking. |
| **Visual Director** | [`src/voice_flow/video_flow_engine/director.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_flow_engine/director.py) | Maps pedagogical goals to visual patterns (`statement`, `comparison`, `process`, `metric`, `diagram`). |
| **Diversity Engine** | [`src/voice_flow/video_flow_engine/diversity.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_flow_engine/diversity.py) | Validates scene type distribution, prevents visual repetition, and enforces pacing rules. |
| **Quality & QA** | [`src/voice_flow/video_flow_engine/quality.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_flow_engine/quality.py) | Evaluates factual grounding, readability, duration constraints, and triggers targeted scene repair. |
| **Hybrid Render Router** | [`src/voice_flow/video_generation/router.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_generation/router.py) | Evaluates scene render strategies against user policy, with guaranteed zero-cost fallback. |
| **Generative Contracts** | [`src/voice_flow/video_generation/contracts.py`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_generation/contracts.py) | Provider-neutral request, asset, capability, and routing definitions. |
| **Deterministic Renderer** | [`video_flow_renderer/`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/video_flow_renderer/) | React 18 + Remotion 4 compositor for deterministic 1080p60/1080p30 video output. |
| **Benchmark Harness** | [`tests/benchmarks/`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/tests/benchmarks/) | 12 domain benchmark fixtures scoring fidelity, grounding, diversity, and fallback success. |

### 🧪 Experimental & Prototype Components

| Component | Location | Notes |
| :--- | :--- | :--- |
| **Scene Studio (Three.js)** | `video_flow_renderer/src/scene-studio/` | Experimental 3D spatial scene renderer using Three.js and Canvas. |
| **Notebook Sketch POC** | `video_flow_renderer/src/notebook-sketch-poc/` | Hand-drawn procedural sketch animation prototype. |
| **Procedural Motion Scene** | `video_flow_renderer/src/ProceduralMotionScene.tsx` | Pure SVG/CSS vector motion scene engine without heavy asset dependencies. |

### 🚧 In Progress

* **Generative Video Provider Integrations:** Integrating candidate generative video backends (Google Veo, Hugging Face, Fal.ai) behind the `GenerativeVideoProvider` abstraction.
* **Per-Scene Asset Stitching:** Merging generated video MP4 clips seamlessly into the Remotion audio-synced composition timeline.

### 📋 Planned (Future Roadmap)

* **HyperFrames Renderer Adapter:** High-performance vector animation renderer adapter alternative.
* **Local Diffusion Video:** Support for local quantized text-to-video models for offline premium mode.
* **Sponsored Compute Pools:** Integration with community-sponsored GPU inference clusters.

---

## 3. The Hybrid Rendering Protocol

### The Zero-Cost Fallback Invariant
**Every generative-video scene must have a deterministic fallback.**

```text
Scene Strategy Requested: GENERATIVE_VIDEO
                      ↓
           Check GenerationPolicy
  (FREE_DETERMINISTIC / BALANCED / PREMIUM / LOCAL_ONLY)
                      ↓
           Is Provider Available & Valid?
             ↙                      ↘
          YES                        NO
           ↓                          ↓
   Render Video Clip         Graceful Fallback to:
 (GeneratedVideoAsset)      PROCEDURAL_2D / REMOTION
           ↓                          ↓
           ────────────────────────────
                      ↓
            Timeline Composition
```

### Supported Render Strategies:
1. `procedural_2d`: Fast 2D vector/typography animation (SVG/HTML5 Canvas).
2. `procedural_3d`: WebGL/Three.js spatial geometry and data visualizations.
3. `remotion`: React-based component animations.
4. `generative_video`: AI-generated video clip with grounding prompt metadata.
5. `media`: Static/user-provided images, diagrams, or captured screenshots.

---

## 4. Historical Decisions & Architecture Changelog

* **Decision 2026-08 (Remotion as V1 Foundation):** Kept Remotion as the primary deterministic rendering engine rather than rewriting everything from scratch.
* **Decision 2026-08 (Brain vs Renderer Decoupling):** Established that the Python backend owns evidence, pedagogy, and scene planning, while rendering engines only produce visual output.
* **Decision 2026-08 (Hybrid Router & Free-First Principle):** Mandated that no generative video provider will ever be a hard dependency for Video Flow, guaranteeing 100% free functionality for all users.
