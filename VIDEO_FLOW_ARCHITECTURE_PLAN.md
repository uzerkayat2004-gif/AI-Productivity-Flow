# Video Flow Architecture and Implementation Plan

**Status:** V1 implementation completed and verified on the feature/video-flow branch.
**Repository:** C:\Users\Asus\.gemini\antigravity\scratch\voice-flow
**Primary application:** Voice Flow, with Audio Flow as an existing feature
**Primary renderer:** Remotion
**Planned output:** One-narrator, source-grounded, animated 16:9 educational MP4

This document is the decision-complete architecture baseline for the permanent Video Flow Brain. It reconciles both Video Flow handoffs with the live Voice Flow codebase and the existing remotion_creator_os prototype. Later prompts may refine product requirements, but implementation should not need to rediscover the architecture described here.

Video Flow succeeds when the viewer understands the source without reading it. Producing an MP4 alone is not success.

## 1. Locked architectural decisions

| Decision | Choice | Reason |
|---|---|---|
| Product placement | Add Video Flow inside Voice Flow; do not create another desktop application | Preserves selection, settings, providers, and desktop behavior |
| Orchestration owner | Python backend | Voice Flow, SQLite, credentials, TTS, and Windows process control already live in Python |
| Rendering owner | A contained TypeScript/React Remotion project in this repository | Keeps rendering deterministic without rewriting the HTML dashboard in React |
| AI responsibility | Understand, teach, plan, narrate, select registered visuals, and describe animation intent | The model is a director, not the renderer |
| Renderer responsibility | Convert validated data and intent into deterministic React/SVG/CSS/Canvas animation | Quality must not depend on arbitrary generated code |
| Canonical memory | Versioned JSON artifacts persisted after every stage | No stage relies on hidden conversation memory |
| Schema source | Pydantic models in Python, exported as JSON Schema and generated TypeScript types | Both runtimes consume one contract |
| Scene/animation separation | Scene Plan describes what to communicate; Animation Plan describes how and when | Timing or rendering can change without reinterpreting the source |
| Timing | Semantic anchors and normalized ratios during planning; concrete frames after TTS | Works across voices, providers, and speeds |
| Audio reuse | Add persistent synthesis behind Audio Flow's existing TTS behavior | Reuses provider/voice/speed policy without coupling video to playback temp files |
| Job execution | Persistent local job ledger and one worker process in V1 | Isolates Tkinter, HTTP, AI calls, Node, Remotion, and FFmpeg |
| Model routing | Capability-based, stage-specific routing using existing BYOK credentials | Supports free, weak, strong, and future OpenAI-compatible models |
| Themes | Approved versioned presets selected by ID | Prevents random palettes and makes output reproducible/accessibile |
| Custom scenes | No raw AI-generated React in V1; CUSTOM_REGISTERED may reference a trusted registered implementation only | Preserves extensibility without executing arbitrary code |
| HyperFrames | Future renderer adapter behind the same renderer interface; Remotion is V1 default | Prevents competing planning pipelines |
| Large assets | Files under ~/.voice_flow/video_flow/project-id; SQLite stores indexes and state | Keeps SQLite queryable and media recoverable |
| QA | Preview and QA are mandatory before final render | Enables targeted repair and matches the product quality bar |

## 2. Current relevant Voice Flow architecture

### 2.1 Application shape

- Python 3.10+ package with Tkinter overlays.
- Plain HTML/CSS/JavaScript dashboard served by a loopback ThreadingHTTPServer on port 8991 and wrapped by pywebview.
- SQLite database at ~/.voice_flow/voice_flow.db.
- Selection and hotkeys through pynput, Win32, clipboard capture, and AudioFlowFloatingWidget.
- Audio Flow TTS in src/voice_flow/tts_engine.py.
- Provider connections, model catalogs, and settings in src/voice_flow/storage.py.
- AI polishing and fallback logic in src/voice_flow/polisher.py.

### 2.2 Current Audio Flow path

1. Mouse selection or Alt+S captures selected text.
2. VoiceFlowApp rejects recent Voice Flow dictations.
3. structured_reader.py converts document-like text to spoken prose.
4. TTSEngine chooses a configured provider/model and synthesizes the selection.
5. It writes a temporary MP3, plays it through PowerShell MediaPlayer, and deletes it.
6. The white widget remains visible during playback and stops TTS when clicked.

### 2.3 Existing model routing limitations

The current polisher is useful source material but not a Video Flow model interface:

- It reads provider credentials and priority.
- Provider endpoints and model lists are hardcoded.
- It expects short plain text.
- It uses a 1.8-second timeout.
- It does not validate structured output.
- It has no capability profiles or stage routing.

Video Flow will reuse credential/settings data and compatible request logic behind a new deep ModelGateway module. Dictation polishing and Audio Flow must remain functional during migration.

### 2.4 Persistence and state gaps

Existing tables cover dictation history, dictionary, settings, AI provider connections/models, and audio provider connections/models. There are no Video Flow projects, stages, scenes, artifacts, assets, renders, or repair records.

Current state management is limited to dictation state and a GUI recording-state JSON file. There is no resumable long-running worker pipeline.

### 2.5 Source and authentication boundaries

- Selected and pasted text are available today.
- The live app has no general document upload/parser pipeline.
- The server is loopback-only and checks an Origin allowlist on mutations.
- There is no user login or multi-user authentication.
- JSON request bodies are capped at 64 KiB.

Selected and pasted text are the guaranteed V1 inputs. Other source formats must enter through a future SourceAdapter and cannot be claimed until implemented.

### 2.6 Existing Remotion prototype

remotion_creator_os is a proof of concept, not the production renderer:

- React 18 and Remotion 4 are installed.
- It has 18 hardcoded Creator OS scenes.
- Edge-TTS generates one MP3 per scene.
- FFprobe/mutagen/file-size fallback calculates durations and frames.
- Root.tsx sequences scenes at 30 FPS and 1920x1080.
- Three QA stills exist; no final MP4 is present.
- Scenes are mostly 23–34 seconds, longer than the target atomic range.
- Many scenes animate their entrance and then remain static.
- A CSS transition appears in the layout, which is not deterministic Remotion motion.
- There is no source analysis, teaching plan, typed scene contract, registry, automated QA, repair, or provider-independent brain.

Production may port useful ideas from this prototype but must not import it as the permanent renderer or silently delete it.

### 2.7 Verified local toolchain

- Python 3.14 is installed locally; production remains compatible with declared Python 3.10+.
- Node 24 and npm 11 are installed.
- FFmpeg and FFprobe 8 are installed.
- Pydantic, jsonschema, edge-tts, and pytest are locally available, though production dependencies must be declared.
- Prototype node_modules and package-lock are present.

## 3. Proposed system architecture

    Selection widget / Video Flow dashboard
                     |
              Local HTTP endpoints
                     |
              VideoFlowPipeline
       ______________|________________
      |              |                |
    ArtifactStore  VideoFlowBrain   NarrationAudio
      |              |                |
    SQLite/files   ModelGateway     Audio Flow TTS adapters
                     |
          provider/model adapters
                     |
              Timeline compiler
                     |
               VideoRenderer
              /             \
        Remotion adapter   HyperFrames adapter (future)
              |
        Node + FFmpeg
              |
          VideoQuality
       deterministic + optional vision QA + scoped repair

## 4. Deep modules and interfaces

The external interfaces stay small. Internal adapters remain private unless two real implementations justify a seam.

### 4.1 VideoFlowPipeline

Primary interface for desktop and HTTP callers:

    start(request: CreateVideoRequest) -> ProjectSnapshot
    resume(project_id: str) -> ProjectSnapshot
    cancel(project_id: str) -> ProjectSnapshot
    get(project_id: str) -> ProjectSnapshot
    retry(project_id: str, scope: RetryScope) -> ProjectSnapshot

It hides stage order, caching, invalidation, worker coordination, progress, errors, and repair. The dashboard does not orchestrate individual stages.

### 4.2 VideoFlowBrain

Primary interface for model-driven work:

    run_stage(stage: BrainStage, context: StageContext) -> ValidatedArtifact

It hides prompt assembly, rule selection, examples, routing, validation, schema repair, and provenance.

### 4.3 ModelGateway

Primary interface for configured language/vision models:

    generate(request: StructuredGenerationRequest) -> StructuredGenerationResult

The request declares stage, required capabilities, schema, context budget, and fallback policy. Production adapters cover Gemini, OpenAI-compatible providers, and later local/custom providers. Tests use a scripted in-memory adapter, making this a real seam.

### 4.4 ArtifactStore

Primary durable-memory interface:

    put(artifact: ArtifactEnvelope) -> ArtifactRef
    get(ref: ArtifactRef) -> ArtifactEnvelope
    latest(project_id, kind, scope=None) -> ArtifactRef | None
    invalidate(project_id, change: ChangeSet) -> InvalidationResult

Production uses SQLite metadata and atomic filesystem writes. Tests use a temporary adapter.

### 4.5 NarrationAudio

Persistent audio interface:

    synthesize(request: NarrationAudioRequest) -> AudioAsset
    probe(asset: AudioAsset) -> AudioMeasurement

It reuses Audio Flow provider settings and synthesis adapters but never invokes playback. TTSEngine.speak remains intact.

### 4.6 VideoRenderer

Renderer interface:

    preflight(manifest: RenderManifest) -> RenderPreflight
    preview(manifest: RenderManifest) -> RenderResult
    stills(manifest: RenderManifest, frames: list[int]) -> StillSet
    final(manifest: RenderManifest) -> RenderResult

Remotion is V1 production adapter. A fake renderer supports pipeline tests. HyperFrames becomes a real seam only after its adapter exists.

### 4.7 VideoQuality

QA and repair interface:

    inspect(request: QualityRequest) -> QAReport
    repair(request: RepairRequest) -> RepairPlan

It combines deterministic contract, factual, layout, motion, and synchronization checks with optional multimodal inspection.

## 5. Pipeline stages and logical agent roles

Roles are prompt roles, not permanent processes. One model may perform all roles; different stages may route to different models.

| Order | Stage | Role | Consumes | Produces | Must not do |
|---:|---|---|---|---|---|
| 1 | Normalize source | Deterministic source module | Raw selection/paste | NormalizedSource | Summarize or invent |
| 2 | Analyze source | Source Analyst | Chunks and evidence map | SourceUnderstanding | Choose animation/theme |
| 3 | Teaching strategy | Explanation Director | Source understanding | ExplanationPlan | Mirror headings blindly |
| 4 | Video strategy | Video/Story Director | Understanding, explanation, user config | VideoPlan + theme choice | Write React or exact frames |
| 5 | Scene planning | Scene Director | Approved artifacts + scene registry | ScenePlan | Use unsupported types/claims |
| 6 | Narration | Narration Editor | Scene plan + grounding + level | NarrationPlan | Change objectives/facts silently |
| 7 | Audio | Deterministic TTS module | Narration + audio policy | AudioManifest | Repeat AI research on failure |
| 8 | Timing | Deterministic compiler | Audio + semantic anchors | TimelineManifest | Guess unmeasured duration |
| 9 | Animation planning | Animation Engineer | Scenes, narration, timeline, registries | AnimationPlan | Reinterpret source or emit code |
| 10 | Render compilation | Deterministic compiler | Approved artifacts | RenderManifest | Accept unknown registry IDs |
| 11 | Preview | Remotion adapter | Manifest/assets | Preview + stills/diagnostics | Render final first |
| 12 | QA | QA/Repair role + validators | Artifacts and preview | QAReport | Regenerate unaffected work |
| 13 | Repair | Scoped flow | Failed scope + neighbors + registries | Replacement scoped artifact | Rewrite whole project |
| 14 | Final render | Remotion/FFmpeg | Approved manifest | Final MP4 | Bypass QA |

Execution rules:

- Every stage receives explicit context.
- Model output is validated before persistence.
- One constrained schema-repair request receives exact validation errors.
- If repair fails, the router may try the next eligible model.
- Stage records include input/output hashes, model route, capability profile, prompt/schema versions, attempts, duration, and errors.
- Default automatic limit is two attempts per stage/model route and two targeted repairs per scene.
- Stages are idempotent for identical inputs and versions.

## 6. Provider-independent model routing

### 6.1 Capability profile

Each model has a versioned profile containing:

- provider and model ID
- request style and optional base endpoint
- native, prompted, or unsupported structured output
- context window and maximum output
- vision and tool-calling support
- reasoning and coding tiers
- system-prompt support

Known models use checked-in profiles. Custom OpenAI-compatible endpoints may have explicit safe overrides. Critical capability is never inferred only from a model name.

### 6.2 Routing policy

1. Use a capable per-stage override when configured.
2. Otherwise use the capable Video Flow default.
3. Otherwise rank active BYOK models by requirements, priority, cooldown, and context fit.
4. If a call does not fit, enter constrained/chunked mode rather than truncating.
5. Persist the selected route and capability version.
6. Never place provider keys or irrelevant artifacts in a prompt.

Existing provider_connections and provider_models supply credentials/models. A later additive migration may store nullable endpoint URLs and capability overrides. exec_audio_policy_model remains narrator-only.

### 6.3 Low-capability mode

Weak/free models use the same contracts with tighter execution:

- chunked source analysis plus deterministic merge
- chapter-by-chapter or scene-by-scene planning
- reduced scene taxonomy
- strict enums and length limits
- one or two matched examples
- safe default choreography
- fewer optional fields
- concise validation-repair messages
- deterministic fallback scene selection when necessary

Advanced models receive broader registered choices and richer choreography, not a different artifact contract.

## 7. Artifact memory and persistence

### 7.1 Common envelope

Every artifact records:

- artifactType, schemaVersion, and brainVersion
- projectId, artifactId, scope, and createdAt
- producer stage, prompt version, provider/model, and capability version
- inputHashes and contentHash
- validated payload

Deterministic producers record their compiler/implementation version.

### 7.2 Canonical artifacts

| Artifact | Main content |
|---|---|
| ProjectConfig | Source, length, explanation level, focus, narrator, renderer, output settings |
| NormalizedSource | Clean source, chunks, type, language, evidence spans, hash |
| SourceUnderstanding | Thesis, concepts, facts, numbers, processes, comparisons, dependencies, uncertainty |
| ExplanationPlan | Goal, audience assumptions, difficult concepts, order, examples/analogies, omissions |
| VideoPlan | Hook, arc, chapters, pace, target duration, theme ID/reason, visual rhythm |
| ScenePlan | Atomic scenes, objective, claims, narration draft, visual type/reason, content, semantic beats, neighbors |
| NarrationPlan | Final text, semantic segments, pronunciation, claim classification, source references |
| AudioManifest | Per-scene audio paths/hashes, voice, provider, rate, duration, optional timestamps |
| TimelineManifest | FPS, scene/local/global frames, audio spans, transition overlaps, segment ranges |
| AnimationPlan | Elements, registered actions, anchors, resolved frames, parameters, transitions |
| RenderManifest | Validated scene props, theme, assets, timing, registry versions, diagnostics |
| QAReport | Contract, factual, layout, visual, motion, sync issues and repair scope |

### 7.3 Stable identifiers and grounding

Artifacts reference sourceId, chunkId, sourceRefId, conceptId, factId, numberId, chapterId, sceneId, narrationSegmentId, elementId, animationBeatId, assetId, renderId, and qaIssueId.

Source references include character offsets and a quote hash. Exact spoken or visible numbers require a grounded numberId. Claims are classified as SOURCE_FACT, MODEL_EXPLANATION, ANALOGY, or INFERENCE. Analogies and inferences cannot masquerade as evidence.

### 7.4 Filesystem layout

    ~/.voice_flow/video_flow/project-id/
      project.json
      artifacts/
        normalized-source.v1.json
        source-understanding.v1.json
        explanation-plan.v1.json
        video-plan.v1.json
        scene-plan.v1.json
        narration-plan.v1.json
        audio-manifest.v1.json
        timeline-manifest.v1.json
        animation-plan.v1.json
        render-manifest.v1.json
        qa-report.v1.json
      source/
      audio/scene-id.mp3
      preview/preview.mp4
      preview/stills/
      renders/final.mp4
      diagnostics/

Writes are atomic: temporary sibling, flush, then replace. No provider secrets appear in artifacts.

### 7.5 SQLite index

Additive, idempotent tables:

- video_projects: identity, config, stage/status/progress, versions, timestamps, error
- video_stage_runs: stage and optional scene scope, status, attempts, hashes, route, timings, error
- video_artifacts: type/version/scope/path/hash/provenance
- video_assets: project/scene, media type, path, hash, duration, metadata
- video_renders: preview/final state, manifest, path, renderer version, error
- video_scene_state: order/status, latest artifact/audio/render, repair count, error

Existing Voice Flow tables and queries remain valid.

### 7.6 Cache and invalidation

- Source change invalidates all downstream work.
- Explanation change invalidates video planning onward.
- Video strategy change invalidates scenes onward.
- One scene change invalidates that scene's narration/audio/timing/animation/render/QA and recomputes global timing.
- Narration/voice/speed change invalidates audio and time-dependent artifacts, not source understanding.
- Theme change invalidates animation compilation, render, and visual QA, not audio.
- Renderer/registry version change invalidates render and render QA when contracts remain compatible.
- Repair invalidates only declared scope and dependents.

Cache keys contain input hashes, brain/rule/prompt/schema versions, route configuration, and implementation versions.

## 8. Permanent brain organization

The permanent brain is feature data loaded by Voice Flow, not a separately installed Codex skill.

### 8.1 Planned repository layout

    src/voice_flow/video_flow/
      __init__.py
      contracts.py
      artifacts.py
      source.py
      model_gateway.py
      pipeline.py
      worker.py
      narration.py
      timing.py
      renderers.py
      quality.py
      brain/
        manifest.json
        SKILL.md
        assembler.py
        rules/
          grounding-and-teaching.md
          storytelling-and-narration.md
          scenes-and-visuals.md
          animation-and-synchronization.md
          theme-layout-accessibility.md
          qa-and-repair.md
          remotion.md
          hyperframes.md
        prompts/
          source-analyst.md
          explanation-director.md
          video-director.md
          scene-director.md
          narration-editor.md
          animation-engineer.md
          qa-repair.md
        examples/
          simple-concept.json
          technical-process.json
          research-report.json
          comparison.json
          numerical-analysis.json
        themes/v1/*.json
        schemas/v1/*.schema.json

    video_flow_renderer/
      package.json
      package-lock.json
      remotion.config.ts
      tsconfig.json
      src/
        index.ts
        Root.tsx
        VideoFlowComposition.tsx
        contracts/generated.ts
        registry/scenes.ts
        registry/animations.ts
        registry/themes.ts
        motion/
        layout/
        scenes/
        diagnostics/
      scripts/
        preflight.ts
        render.ts

Initial Python files are deliberately deep modules. Split them only when a clearer interface emerges.

### 8.2 Brain manifest/versioning

brain/manifest.json records brain, rule, prompt, example, schema, theme, scene registry, animation registry, and minimum renderer versions.

- Patch version: wording/clarity with compatible output.
- Minor version: optional compatible fields or choices.
- Major version: contract or interpretation change requiring migration/regeneration.

### 8.3 Master SKILL.md

The compact master manual defines:

- identity and teaching mission
- required analyze → teach → direct → scene → narrate → time → animate → inspect → repair workflow
- prohibitions against hallucination, podcasts, paragraph dumping, decorative motion, arbitrary code, random colors, and premature conclusions
- artifact, registry, and grounding discipline

Role prompts load only relevant rules. The entire brain never enters every request.

### 8.4 Prompt assembly

PromptAssembler receives role, capability/context budget, target schema, upstream artifacts or selected slices, active registries, user config, and matched examples.

It emits:

1. compact identity/invariants
2. role-specific rules
3. exact task and allowed decisions
4. relevant upstream facts/plans
5. registry subset
6. one or two matched examples when budget permits
7. output schema and validation reminder

Assembly is deterministic, versioned, budget-aware, and based on named slots rather than random Markdown concatenation.

## 9. Schema strategy and relationships

Pydantic v2 models are canonical. Tests export JSON Schemas and generate TypeScript types. The renderer validates RenderManifest at runtime with a JSON-Schema validator. Schema/type drift fails verification.

Relationship flow:

    NormalizedSource
      -> SourceUnderstanding
      -> ExplanationPlan
      -> VideoPlan
      -> ScenePlan
      -> NarrationPlan
      -> AudioManifest
      -> TimelineManifest
      -> AnimationPlan
      -> RenderManifest
      -> QAReport

SourceUnderstanding also grounds ScenePlan and QA. ScenePlan and TimelineManifest jointly produce AnimationPlan.

Core invariants:

- unique stable scene IDs and ordered scenes
- one primary learning objective per scene
- grounded factual claims and numbers
- valid scene/theme/action registry IDs
- unique element IDs and valid animation targets
- complete ordered narration segments
- existing positive-duration audio assets
- audio-derived frame counts
- no important reveal before its narration anchor unless marked setup
- text density and safe-area compliance
- QA approval for the exact final manifest hash

### 9.1 Scene Plan versus Animation Plan

Scene Plan describes semantic purpose, objective, references, claims, narration draft, visual choice/reason, visible data, element IDs, normalized beat intents, and neighbor continuity.

Animation Plan describes component variant, resolved props, concrete frames, transitions, camera/focus behavior, and diagnostics.

Models cannot emit raw React, CSS animation, arbitrary SVG code, or raw colors. A deterministic compiler fills safe optional defaults.

## 10. Visual grammar and scene registry

Semantic mapping:

| Information | Scene |
|---|---|
| Opening promise/question | TITLE hook variant |
| Important term | DEFINITION |
| Important source wording | TEXT_HIGHLIGHT or SOURCE_EXCERPT |
| One important number | BIG_NUMBER |
| Several related concepts | CONCEPT_CARDS |
| Directional flow | FLOW_DIAGRAM |
| Ordered process | PROCESS_STEPS |
| A versus B | COMPARISON |
| State change | BEFORE_AFTER |
| Time progression | TIMELINE |
| Cause/consequence | CAUSE_EFFECT |
| Category values | BAR_CHART |
| Non-linear topology | NETWORK_DIAGRAM |
| Recap/verdict | SUMMARY |

The model must explain why the selected visual improves understanding.

### 10.1 V1 implementations

1. TITLE
2. TEXT_HIGHLIGHT
3. DEFINITION
4. BIG_NUMBER
5. CONCEPT_CARDS
6. FLOW_DIAGRAM
7. PROCESS_STEPS
8. COMPARISON
9. BEFORE_AFTER
10. TIMELINE
11. CAUSE_EFFECT
12. BAR_CHART
13. NETWORK_DIAGRAM
14. SOURCE_EXCERPT
15. SUMMARY

HOOK, METRIC_GRID, and FINAL_VERDICT are validated variants, not duplicate shallow modules. Line chart, funnel, cycle, hierarchy, code, equation, table, and sequence diagram are post-V1 registry additions.

Each scene registry entry defines use/anti-use cases, data schema, limits, element pattern, allowed actions, default choreography, transitions, diagnostics, examples, and implementation version.

### 10.2 Layout/text rules

- 1920x1080, 30 FPS, 16:9.
- Keep critical content inside 5% safe margins.
- One dominant focal point.
- Prefer one headline, one main visual, one support group.
- Do not display narration paragraphs.
- Typical simultaneous visible text budget: 18–30 words, with stricter scene-specific caps.
- Headline: two lines maximum by default.
- Charts use readable direct labels or accessible legends.
- Use @remotion/layout-utils after fonts load.
- Overflow is an error, not a reason to shrink indefinitely.

## 11. Animation grammar

Initial actions:

- ENTER, EXIT
- REVEAL, HIGHLIGHT, FOCUS
- DRAW, CONNECT, TRACE
- MOVE, TRANSFORM
- COUNT, GROW
- PULSE
- PAN, ZOOM
- STAGGER, SEQUENCE
- TYPE

MORPH and free rotation wait for deterministic semantic implementations.

Beat intent contains beat ID, action, target ID, semantic narration anchor, fallback start/duration ratios, purpose, and constrained parameters. Semantic anchors are preferred over raw ratios.

Implementation rules:

- use useCurrentFrame, interpolate, spring, and Sequence
- use explicit clamping and deterministic easing
- no CSS transitions/keyframes, Tailwind animation, timers, or wall-clock state
- premount where assets/fonts need readiness
- derive related properties from shared progress
- animate SVG paths, bars, counters, arrows, focus, and camera by frame

Static-scene preflight flags:

- everything important visible at frame zero
- first activity too late
- long unintentional static tail
- only decorative entrances
- multiple narration segments with no visual response
- fully built diagrams/charts at first frame
- missing targets

Normal explanatory scenes need two to four meaningful beats. Intentional stillness requires an accepted stillnessReason.

## 12. Narration, audio, and synchronization

Narration:

- one narrator
- spoken natural sentences
- teach concepts and explain numbers
- preserve uncertainty
- do not read tables/headings/citations/dense lists
- use examples and short transitions
- simple/standard/technical change vocabulary, not facts
- analogies remain labeled

Persistent Audio Flow reuse:

- share provider/model/voice/rate resolution
- preserve TTSEngine.speak
- add synthesis to deterministic file path
- synthesize every scene independently
- content-address assets using text, voice, rate, provider/model, and version
- FFprobe is authoritative duration measurement
- retain word boundaries when a provider supplies them

Without word timestamps:

1. Narration Editor creates semantic segments.
2. Compiler weights words and punctuation.
3. Weights normalize across measured duration.
4. Beats anchor to segment-relative windows.
5. Minimum reveal/hold/transition windows apply.
6. QA rejects premature important reveals.

Frame rules:

- audioFrames = ceiling(durationSeconds × FPS)
- explicit small lead-in/tail-hold fields
- scene duration = lead-in + audio + tail hold before overlap
- transition overlap subtracted exactly once
- local and global frames persisted

## 13. Theme and visual personality

Initial accessible presets:

1. editorial-research
2. technical-grid
3. warm-educational
4. finance-ledger
5. science-spectrum
6. creative-bold
7. monochrome-focus
8. archival-story

Each theme supplies semantic colors, chart/diagram palettes, typography, radius/border/shadow/background treatment, spacing, transition personality, motion energy, and accessibility metadata.

The Video Director returns themeId, reason, and confidence. It never invents colors.

Accessibility:

- body contrast target 4.5:1
- large display target 3:1
- labels/icons/shapes supplement color
- chart series distinguishable beyond hue when practical
- scene-specific minimum font sizes
- reduced-motion-energy option preserves semantic reveals

Typography roles are DISPLAY, TITLE, SECTION, BODY, LABEL, CAPTION, METRIC, and CODE. The renderer resolves sizes; the model selects semantic roles.

## 14. Transitions

Initial vocabulary:

- CUT for deliberate pace/contrast
- CROSSFADE for soft continuation
- PUSH for direction/process
- WIPE for chapter/timeline movement
- ZOOM_THROUGH for entering/leaving detail
- SHARED_OBJECT for registered conceptual continuity
- DIAGRAM_EXPAND for promoting a node/section into the next scene

Both adjacent scenes must support the transition. Remotion TransitionSeries owns deterministic overlap and duration calculation. Random flashy transitions are invalid.

## 15. Remotion integration

### 15.1 Production renderer shape

video_flow_renderer is data-driven:

- Root registers one VideoFlow composition.
- Composition receives a validated render manifest or manifest path.
- A scene registry maps scene type/variant to trusted React implementations.
- Animation registry maps actions to deterministic frame functions.
- Theme registry maps theme IDs to validated tokens.
- Each scene renders narration audio with @remotion/media.
- Series/TransitionSeries handles scene order and transition overlaps.
- Renderer writes structured diagnostics beside output.

The AI never creates a new TSX file for a normal video.

### 15.2 Planned renderer dependencies

- remotion and @remotion/cli
- @remotion/media
- @remotion/transitions
- @remotion/layout-utils
- React/ReactDOM/TypeScript
- a JSON-Schema runtime validator such as Ajv
- generated TypeScript contract types

Add only when implementation begins. The existing prototype dependency versions provide a starting point but are not copied blindly.

### 15.3 Render workflow

1. Python compiles RenderManifest.
2. Node preflight validates schema, registry compatibility, asset existence, text limits, and theme.
3. Fast low-scale preview renders.
4. Representative and beat-aligned stills render.
5. QA runs.
6. Scoped repairs update artifacts/manifests.
7. Preview rerenders only affected scope where practical.
8. Final 1080p MP4 renders.
9. FFprobe verifies codec, duration, dimensions, audio stream, and non-zero file.

Preview prioritizes speed through reduced scale/quality and bounded concurrency. Final render concurrency is configurable and does not block Tkinter.

### 15.4 Diagnostics

Renderer diagnostics include:

- scene/component/registry versions
- element boxes and overflow status
- font readiness
- planned and actual beat frame ranges
- missing assets/targets
- animation activity windows
- still-frame capture list
- render warnings/errors

Diagnostics are machine-readable inputs to QA, not only console logs.

## 16. HyperFrames role

HyperFrames is optional and post-V1 unless the forthcoming material creates a concrete need.

- Content planning remains renderer-independent.
- Scene and Animation Plans use common semantic contracts.
- A HyperFrames adapter must satisfy VideoRenderer.
- Renderer selection occurs after plans are approved.
- A project uses one primary render timeline; no duplicated independent pipelines.
- HyperFrames is chosen only when a registered scene is materially simpler or stronger there.
- No HyperFrames-specific instruction enters Source Analyst, Explanation Director, or Scene Director prompts.

## 17. QA and repair loop

### 17.1 Contract QA

- schema validity
- IDs and ordering
- valid registry IDs/actions/themes
- cross-reference integrity
- limits and text density
- audio/timing sanity
- artifact hash/version compatibility

### 17.2 Factual QA

- spoken and visible numbers match grounded number records
- source facts have references
- uncertainty language is preserved
- analogies/inferences are classified
- visible labels and narration do not contradict each other
- unsupported claims are blocked before render

A model may assist with semantic consistency, but deterministic exact-number/reference checks always run.

### 17.3 Layout and visual QA

- overflow, overlap, clipping, safe margins
- contrast and font size
- chart labels and hierarchy
- empty/overcrowded scenes
- theme consistency
- source excerpt accuracy

Representative frames include project percentages and scene-specific start, beat, midpoint, and ending frames. Optional vision QA receives only the relevant stills, manifest slice, and QA rules.

### 17.4 Motion QA

- meaningful beat count
- beat distribution across narration
- static-tail ratio
- all-elements-visible-at-zero check
- target/property activity metadata
- multi-frame perceptual differences around meaningful windows
- narration segments without visual response

Screenshot QA alone is insufficient; renderer diagnostics and sampled-frame comparison are required.

### 17.5 Synchronization QA

- anchored reveal falls within allowed narration segment window
- conclusion/number not shown prematurely
- audio fits scene span
- transitions do not cut important audio
- final audio/video duration drift stays within tolerance

### 17.6 Repair

Repair request contains:

- failed artifact/scene
- exact issues and renderer errors
- source/learning objective
- neighboring scene summaries
- theme
- allowed registry subset
- current narration/timing

Repair output is a validated replacement for the smallest affected artifact. Pipeline invalidation then recomputes only dependents. After two failed automatic repairs, the project remains resumable and exposes the issue instead of looping.

## 18. Worker, state, progress, and HTTP integration

### 18.1 Worker

- The dashboard enqueues a project and returns immediately.
- A dedicated Python worker process polls/claims local pending jobs.
- V1 processes one heavy project/render at a time by default.
- Stage state and heartbeat persist in SQLite.
- A crashed worker leaves recoverable RUNNING records that become resumable.
- Node/FFmpeg subprocess IDs and logs are tracked.
- Cancel requests terminate only project-owned child processes.

Redis/Celery is unnecessary for the local V1.

### 18.2 Project/stage states

Project stages:

CREATED, NORMALIZING, ANALYZING, TEACHING, VIDEO_PLANNING, SCENE_PLANNING, NARRATING, GENERATING_AUDIO, CALCULATING_TIMING, PLANNING_ANIMATION, COMPILING_RENDER, RENDERING_PREVIEW, CHECKING_OUTPUT, REPAIRING, RENDERING_FINAL, COMPLETED, FAILED, CANCELED.

Each stage run has PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, or CANCELED.

Progress is weighted by historical/default stage cost rather than a fake equal percentage.

### 18.3 Planned HTTP endpoints

- POST /api/video-flow/projects
- GET /api/video-flow/projects
- GET /api/video-flow/projects/project-id
- POST /api/video-flow/projects/project-id/start
- POST /api/video-flow/projects/project-id/resume
- POST /api/video-flow/projects/project-id/cancel
- POST /api/video-flow/projects/project-id/retry
- GET /api/video-flow/projects/project-id/scenes
- POST /api/video-flow/projects/project-id/scenes/scene-id/repair
- GET /api/video-flow/projects/project-id/renders

Route parsing should not continue growing as a giant do_POST conditional. Introduce a small Video Flow route dispatcher while preserving the current local server.

Large source submission gets an endpoint-specific bounded limit or local source-file reference; it must not globally disable body limits. Existing Origin checks remain. A local session token for expensive mutating operations is a hardening option, not a V1 blocker.

### 18.4 UI integration order

Brain and pipeline precede UI.

Later UI:

- selection action surface with Listen and Explain with Video
- preserve no-focus Win32 behavior
- lightweight config: Short/Standard/Deep, Simple/Standard/Technical, optional focus
- Video Flow dashboard page with project list, stage progress, errors, preview, final playback/open-file action
- pasted-text creation flow
- scene-level repair/regeneration controls after core pipeline works

The existing Audio Flow action remains unchanged until the dual-action selection widget is verified.

## 19. Source normalization and grounding

V1 source types:

- selected text
- pasted text

NormalizedSource contains original hash, normalized text, language, chunks, structure hints, and stable evidence spans. Normalization removes transport noise but preserves evidence offsets through a mapping.

Long source strategy:

- structure-aware chunks with controlled overlap
- chunk-level source analysis
- deterministic deduplication/merge
- contradictions and uncertainty preserved
- no silent source truncation

Future SourceAdapters can add plain text/Markdown files, PDF, DOCX, web pages, or source-provided media. They must produce the same NormalizedSource contract. The app currently has no such production adapters.

## 20. Example library

Five compact examples:

1. Simple concept: inflation/purchasing power.
2. Technical process: DNS request flow.
3. Research report: a grounded business/strategy report.
4. Comparison: two approaches with tradeoffs.
5. Numerical analysis: categories, units, uncertainty, and a chart.

Each bundle shows source understanding, teaching plan, video plan, scenes, final narration, visual reason, and beat intents. Examples remain small and demonstrate patterns rather than becoming content-heavy prompt ballast.

Example selection is semantic: domain, source shape, explanation level, and target stage. Weak models receive more explicit examples; strong models receive fewer.

## 21. Contributor extension contracts

### 21.1 New scene

1. Define semantic use/anti-use cases.
2. Add or extend the data schema.
3. Implement the trusted renderer scene.
4. Register supported element roles/actions/default choreography/transitions.
5. Add layout and motion diagnostics.
6. Add a compact brain example.
7. Add schema, visual, timing, and render tests.
8. Bump compatible registry versions.

### 21.2 New theme

1. Add structured tokens/personality.
2. Pass contrast and chart differentiation tests.
3. Register domain-selection guidance.
4. Render the scene matrix across the theme.
5. Add snapshot/reference checks and bump theme version.

### 21.3 New renderer

1. Implement VideoRenderer.
2. Document supported scene/action versions.
3. Pass the canonical manifest conformance suite.
4. Produce equivalent timing/audio behavior.
5. Add fake/error-path tests and renderer-specific visual QA.

## 22. Testing strategy

### 22.1 Python contract tests

- Pydantic schema examples and failures
- schema export drift
- ID/cross-reference invariants
- grounding and number checks
- cache keys and invalidation graph
- artifact atomicity/recovery
- SQLite additive migrations
- state transitions and retry limits

### 22.2 ModelGateway tests

- scripted fake model outputs
- native JSON and prompted JSON extraction
- malformed/truncated/schema-invalid repair
- capability routing and fallback
- context budget/chunking
- rate-limit cooldown
- no secrets in prompts/artifacts/logs

No paid provider is required for normal tests. Live BYOK tests are opt-in.

### 22.3 Brain evaluation fixtures

Run the five example sources through constrained, standard, and advanced simulated profiles. Score:

- schema compliance
- grounding
- teaching coherence
- scene atomicity
- visual selection
- narration quality
- animation-beat quality
- text density

Store evaluation fixtures and rubrics, not provider-specific golden prose.

### 22.4 Audio/timing tests

- persistent synthesis path does not affect Audio Flow playback
- duration probing and frame rounding
- semantic segment allocation
- voice/speed cache invalidation
- transition overlap math
- scene-only retry

Network TTS is mocked in unit tests; one optional Edge-TTS smoke test may run manually.

### 22.5 Renderer tests

- TypeScript compile and schema validation
- registry completeness
- one representative fixture per scene variant
- text overflow and safe-area diagnostics
- frame-driven property tests
- audio placement/timeline
- still renders at scale 0.25
- short preview render smoke test
- FFprobe output verification

### 22.6 End-to-end acceptance matrix

At minimum:

- short simple paragraph
- medium technical process
- data-heavy research report
- weak-model fixture with repair
- TTS failure/resume
- single-scene render failure/repair
- theme/voice change invalidation
- app restart and resume
- Audio Flow regression

## 23. Phased implementation plan

No phase below has started.

### Phase 0 — Baseline protection and extraction map

Goal: protect the working Voice Flow app and identify prototype material worth porting.

- Capture current behavior and working-tree state.
- Add/repair focused tests around Audio Flow selection, TTS playback, provider settings, and local HTTP behavior.
- Document which remotion_creator_os patterns are reference-quality versus one-off.
- Decide Python/Node commands and dependency versions.
- Do not move/delete the prototype.

Exit: current Audio Flow has a repeatable regression baseline.

### Phase 1 — Contracts, artifacts, and job ledger

Goal: establish canonical memory before model calls.

- Implement Pydantic artifact envelope and schemas.
- Export JSON Schema and generated TypeScript types.
- Implement ArtifactStore with atomic files.
- Add additive SQLite Video Flow tables.
- Implement project/stage state machine, hashing, caching, and invalidation.
- Add temporary/fake adapters and tests.

Exit: a synthetic project can advance/resume through mocked stages with persisted artifacts.

### Phase 2 — ModelGateway and permanent brain

Goal: make provider-independent structured intelligence work.

- Implement capability profiles and route policy.
- Reuse existing credential storage safely.
- Add Gemini and OpenAI-compatible adapters.
- Implement structured extraction, validation, repair, fallback, and budget handling.
- Add brain manifest, master skill, modular rules, role prompts, schemas, examples, themes, and PromptAssembler.
- Test with scripted weak/standard/advanced profiles.

Exit: source through ScenePlan/NarrationPlan artifacts can be generated and validated without renderer code generation.

### Phase 3 — Source, teaching, video, scenes, and narration pipeline

Goal: complete the staged planning graph.

- Selected/pasted source normalization and evidence map.
- Source Analyst, Explanation Director, Video Director, Scene Director, Narration Editor.
- Deterministic factual/visual-selection/text-density validators.
- Scene-level repair flow.
- Duration/scene-count policies for Short/Standard/Deep.

Exit: real source produces a fully grounded, atomic, registry-valid plan bundle.

### Phase 4 — Persistent narration and timing

Goal: make audio authoritative without breaking Audio Flow.

- Extract persistent synthesis behind existing TTS logic.
- Per-scene content-addressed MP3 generation.
- FFprobe duration and optional word-boundary capture.
- Semantic fallback timing compiler.
- Audio/Timeline manifests and invalidation.
- Audio Flow regression verification.

Exit: every scene has reusable audio and concrete frame timing.

### Phase 5 — Deterministic Remotion renderer foundation

Goal: render validated manifests, not bespoke model code.

- Create video_flow_renderer.
- Add manifest validator, generated types, composition, registries, theme system, layout/motion primitives.
- Implement first cross-cutting primitives and 15 V1 scene implementations.
- Add transitions, audio placement, overflow diagnostics, and preflight.
- Port only suitable prototype ideas.

Exit: all scene fixtures render stills and a short multi-scene animated preview.

### Phase 6 — Animation planning and renderer compilation

Goal: synchronize semantic intent with audio.

- Implement animation action registry and defaults.
- Add Animation Engineer structured stage.
- Resolve semantic anchors/ratios to concrete frames.
- Compile RenderManifest and diagnostics expectations.
- Add static-scene/synchronization validators.

Exit: animation follows narration and invalid plans fail before expensive render.

### Phase 7 — Worker, HTTP, and progress

Goal: make generation resumable inside the desktop app.

- Dedicated worker/heartbeat/cancellation.
- Video Flow route dispatcher and HTTP endpoints.
- Progress snapshots and log/error surfaces.
- Safe source size handling and output access.
- Crash/restart resume tests.

Exit: dashboard can create and monitor a mocked/real local project without blocking Voice Flow.

### Phase 8 — Preview, QA, repair, and final render

Goal: close the quality loop.

- Fast preview settings.
- Still selection at project and beat levels.
- Contract/factual/layout/motion/sync QA.
- Optional vision QA routing.
- Scoped repair and rerender.
- Final render and FFprobe verification.

Exit: failed scenes repair independently and final MP4 requires approved QA.

### Phase 9 — User experience

Goal: expose Video Flow as a native extension.

- Dual selection actions: Listen and Explain with Video.
- Lightweight configuration.
- Video Flow dashboard project/progress/preview/output UI.
- Pasted source flow and scene repair controls.
- Preserve focus behavior and Audio Flow widget invariants.

Exit: user completes selected-text → preview → final video end-to-end.

### Phase 10 — Hardening and extensibility

Goal: prove the permanent brain across providers and contributors.

- Multi-model stage overrides.
- Weak/free-model evaluation and prompt tuning.
- Theme/scene contribution docs.
- Optional custom endpoint profiles.
- Performance/storage cleanup policy.
- HyperFrames feasibility spike only if justified.

Exit: provider swap does not change pipeline contracts and new registered scenes/themes are additive.

## 24. Verification gates

No phase advances merely because files exist.

- Baseline gate: Audio Flow still selects, speaks, stops, and honors settings.
- Contract gate: every artifact validates and records versions/hashes.
- Brain gate: weak-profile fixtures remain grounded and schema-valid.
- Planning gate: scenes are atomic, semantically chosen, and narration/visuals share one plan.
- Audio gate: real durations control frames and assets resume from cache.
- Renderer gate: all V1 scenes show meaningful frame-driven motion.
- QA gate: factual, visual, motion, and synchronization issues are detectable and scoped.
- Recovery gate: restart resumes without repeating completed expensive stages.
- Product gate: selected/pasted source produces preview and final MP4 without image/video-generation APIs.

## 25. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Weak model fails complex artifact | Smaller calls, tighter schema, matched examples, deterministic merge/defaults, fallback |
| Existing provider router is too polisher-specific | New ModelGateway reuses credentials, not the shallow polisher interface |
| TTS refactor breaks Audio Flow | Preserve speak interface; add synthesis path with regression tests |
| Long jobs freeze desktop | Dedicated worker and subprocess isolation |
| SQLite becomes media store | Metadata only; content-addressed filesystem assets |
| Static slide output | Beat contract, registry defaults, motion diagnostics, sampled-frame QA |
| Premature visual facts | Semantic narration anchors and synchronization checks |
| Theme randomness/poor contrast | Approved presets and contrast tests |
| Schema drift Python/TypeScript | Generated schemas/types and drift verification |
| One broken scene causes total regeneration | Scoped artifacts, invalidation graph, per-scene audio/render/repair |
| Transition duration drift | One timeline compiler owns overlap math |
| Huge source exceeds local request limit | Endpoint-specific bounded source ingestion and chunking |
| Prototype contaminates architecture | Treat as reference; port intentionally into registries |
| Arbitrary AI code creates security/quality risk | No raw generated React; trusted registry only |
| Vision QA unavailable | Deterministic QA remains mandatory; vision is additive |
| Provider cost/rate limits | BYOK, caching, cooldown, stage routing, constrained mode |

## 26. Definition of done for V1

1. Voice Flow dictation and Audio Flow remain functional.
2. User can invoke Video Flow from selected or pasted text.
3. Every intelligence stage produces a persisted versioned artifact.
4. Model routing is provider-independent and capability-aware.
5. Weak/free models use constrained mode without changing contracts.
6. Source claims, numbers, uncertainty, analogies, and inferences are distinguishable.
7. Scene planning is atomic and semantic.
8. One narrator is finalized before audio/timing.
9. Existing Audio Flow policy generates persistent per-scene audio.
10. Real audio duration controls scene frames.
11. Important visual events follow narration anchors.
12. Remotion renders registered programmatic scenes with meaningful motion.
13. At least 15 V1 scene implementations and eight themes pass their fixture matrix.
14. Preview, deterministic QA, scoped repair, and final render work.
15. Failures resume without repeating unaffected expensive stages.
16. Final MP4 is verified for video/audio streams, dimensions, duration, and non-zero output.
17. No image-generation or AI-video provider is required.
18. No arbitrary generated React is required.
19. Provider, prompt, schema, theme, registry, renderer, and brain versions are reproducible.
20. Contributors can add a registered scene/theme without redesigning the brain.

## 27. Decisions deliberately deferred

These do not block brain/contract implementation and can be refined by the forthcoming prompt:

- exact final selection-widget layout and iconography
- final dashboard mockups
- additional source adapters beyond selected/pasted text
- whether captions are V1 or a later accessibility milestone
- exact storage-retention defaults
- exact Remotion package versions at implementation time
- whether a concrete HyperFrames scene justifies an adapter
- optional background music/sound-effects policy
- packaging/distribution of Node/FFmpeg for machines that do not already have them

Defaults remain: 16:9, 1920x1080, 30 FPS, one narrator, Remotion, no AI imagery, and preview-before-final.

## 28. Requirement coverage

This plan covers the requested architecture deliverable:

- A. Current Audio Flow architecture: sections 2 and 3.
- B. Video Flow Brain architecture: sections 3, 4, and 8.
- C. Stage/agent roles: section 5.
- D. Model routing: section 6.
- E. Artifact/memory strategy: section 7.
- F. Skill/prompt structure: section 8.
- G. Schema relationships: section 9.
- H. Scene strategy: section 10.
- I. Visual grammar: section 10.
- J. Animation grammar: section 11.
- K. Theme system: section 13.
- L. Remotion integration: section 15.
- M. HyperFrames role: section 16.
- N. QA/repair loop: section 17.
- O. Low-capability strategy: section 6.3.
- P. Testing: section 22.
- Q. Migration/integration plan: sections 18, 23, and 24.

## 29. Planning handoff

This document is ready to absorb the next prompt without beginning implementation. When implementation authorization arrives, start at Phase 0, preserve unrelated working-tree changes, and do not skip directly to UI or model-generated Remotion code.
