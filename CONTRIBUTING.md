# 🤝 Contributing to Flow

Thank you for your interest in contributing to **Flow**! We welcome contributions from developers, researchers, designers, and educators.

---

## 🛠️ Development Environment Setup

### 1. Prerequisites
* **Python:** 3.10+ (Python 3.14 supported)
* **Node.js:** 18+ and npm 9+
* **Git**
* **OS:** Windows 10 / 11 (for desktop hooks; core packages run cross-platform)

### 2. Initial Setup
```bash
# Clone the repository
git clone https://github.com/uzerkayat2004-gif/Voice-Flow.git
cd Voice-Flow

# Install Python package in editable mode
pip install -e .

# Install Remotion renderer dependencies
cd video_flow_renderer
npm install
cd ..
```

---

## 🧪 Running Tests

Before submitting a Pull Request, ensure all tests pass:

```bash
# Run all Python tests
python -m pytest tests/test_insights_deep.py tests/test_history_features.py tests/test_dictionary_safety.py tests/test_style_system.py tests/test_provider_management.py tests/test_watchdog_and_startup.py tests/test_hybrid_render_routing.py tests/test_video_flow_benchmarks.py -s

# Run Video Flow engine tests
python -m pytest tests/test_video_flow.py tests/test_video_flow_models.py tests/test_video_flow_motion.py tests/test_video_flow_providers.py tests/test_video_flow_themes.py -s

# Typecheck the Remotion Renderer
cd video_flow_renderer && npm run typecheck
```

---

## 🏗️ Architecture & How to Extend

### 1. Adding a Generative Video Provider
All generative video models must implement the [`GenerativeVideoProvider`](file:///C:/Users/Asus/.gemini/antigravity/scratch/voice-flow/src/voice_flow/video_generation/provider.py) interface in `src/voice_flow/video_generation/`:

```python
from voice_flow.video_generation import (
    GenerativeVideoProvider,
    VideoGenerationRequest,
    GeneratedVideoAsset,
    VideoProviderCapabilities,
    video_provider_registry,
)

class MyCustomVideoProvider(GenerativeVideoProvider):
    @property
    def provider_id(self) -> str:
        return "my_custom_provider"

    @property
    def display_name(self) -> str:
        return "My Custom Generative Video Model"

    def available(self) -> bool:
        # Check credentials or local model availability
        return True

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_id=self.provider_id,
            display_name=self.display_name,
            supports_text_to_video=True,
            supported_aspect_ratios=["16:9"],
        )

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideoAsset:
        # Generate video and return standardized asset
        ...

# Register provider
video_provider_registry.register(MyCustomVideoProvider())
```

### 2. Free-First Architectural Invariant
* **Never make a paid API mandatory.**
* All video scenes must maintain a working deterministic fallback (`procedural_2d`, `procedural_3d`, or `remotion`).

---

## 📋 Pull Request Guidelines

1. **Keep Changes Focused:** One feature or bugfix per PR.
2. **Preserve Existing Functionality:** Do not break existing Voice Flow or Audio Flow features.
3. **Add Tests:** Include unit tests in `tests/` for any new logic or providers.
4. **No Secrets:** Never commit API keys, credentials, or private machine paths.
