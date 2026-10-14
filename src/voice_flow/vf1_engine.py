"""Universal Voice Flow Engine (VF-1).

Configurable, local-first inference engine for S1-mini VF-1 Base
with optional Stage 3B LoRA adapter support and deterministic host-side
factual preservation safety gating.

Operates completely locally without cloud API dependencies.
"""
from __future__ import annotations

import gc
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from voice_flow.safety_gate import SafetyGateDecision, validate_and_gate_output
from voice_flow.vf_contract import (
    CONTRACT_VERSION,
    DEFAULTS,
    HEADER_ORDER,
    SYSTEM_PROMPT_VF1,
    VF1Request,
    render_vf1,
)

log = logging.getLogger(__name__)

DEFAULT_S1_MODEL_ID = "superwhisper/s1-mini"
DEFAULT_S1_REVISION = "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
DEFAULT_CONTEXT_TOKENS = 4096


@dataclass
class VF1EngineConfig:
    """Configuration for local VF-1 inference."""

    model_id: str = DEFAULT_S1_MODEL_ID
    model_revision: str = DEFAULT_S1_REVISION
    use_lora: bool = False
    lora_adapter_path: Optional[str] = None
    backend: str = "auto"  # "auto", "llama_cpp", "transformers", "mock"
    device: str = "auto"   # "auto", "cuda", "cpu"
    timeout_seconds: float = 5.0
    max_new_tokens: int = 256
    temperature: float = 0.0
    repetition_penalty: float = 1.0
    enable_thinking: bool = False


@dataclass
class VF1EngineResult:
    """Result of a VF-1 polish execution."""

    final_text: str
    raw_output: str
    source_preserved: bool
    safety_accepted: bool
    safety_reasons: List[str]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    memory_mb: float
    task: str
    format: str
    model_name: str
    adjudication_notes: List[str] = field(default_factory=list)

    @property
    def passed_safety(self) -> bool:
        return self.safety_accepted


class VF1Engine:
    """Configurable local inference engine for Universal Voice Flow (VF-1)."""

    def __init__(self, config: Optional[VF1EngineConfig] = None):
        self.config = config or VF1EngineConfig()
        self._lock = threading.Lock()
        self._loaded_model: Any = None
        self._loaded_tokenizer: Any = None
        self._mock_generator: Optional[Callable[[str, VF1Request], str]] = None
        self._last_telemetry: Optional[Dict[str, Any]] = None

    def set_mock_generator(self, generator: Optional[Callable[[str, VF1Request], str]]) -> None:
        """Set mock generator for deterministic unit/integration testing without downloading weights."""
        self._mock_generator = generator

    def can_handle(
        self,
        task: str = "cleanup",
        format: Optional[str] = None,
        text: str = "",
        instruction: Optional[str] = None,
    ) -> bool:
        """Check whether the VF-1 engine can process the given input."""
        if not text or not text.strip():
            return False

        # VF-1 supports English speech editing and structuring
        letters = [c for c in text if c.isalpha()]
        if letters:
            non_ascii = [c for c in letters if ord(c) > 127]
            if len(non_ascii) / len(letters) > 0.25:
                return False  # Non-English transcript

        # Supported tasks
        norm_task = (task or "cleanup").strip().lower()
        if norm_task not in ("cleanup", "rewrite", "prompt", "summarize", "edit"):
            return False

        return True

    def build_chatml_prompt(self, request: VF1Request) -> Tuple[str, str, str]:
        """Build rendered system text, user text, and full ChatML prompt."""
        system_text, user_text = render_vf1(request)
        # S1-mini and Qwen3 use ChatML formatting with pre-disabled thinking block
        prompt_text = (
            f"<|im_start|>system\n{system_text}<|im_end|>\n"
            f"<|im_start|>user\n{user_text}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )
        return system_text, user_text, prompt_text

    def _execute_mock(self, prompt_text: str, request: VF1Request) -> str:
        """Execute mock generation when mock generator is registered."""
        if self._mock_generator:
            return self._mock_generator(prompt_text, request)
        # Default fallback stub if no mock generator provided: clean fillers and normalize
        text = request.transcript
        t = re.sub(r"\b(?:um|uh|er|ah|you know|so basically)\b", "", text, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        if request.task == "prompt" and "make this a prompt:" in t.lower():
            t = re.sub(r"^make this a prompt:\s*", "", t, flags=re.I)
        if request.format == "bullets":
            items = [item.strip() for item in re.split(r"[,;]|\band\b", t) if item.strip()]
            return "\n".join(f"- {i.capitalize()}" for i in items)
        if request.format == "email" and "subject" in t.lower():
            return f"Subject: Update\n\n{t}\n\nBest regards,\nSender"
        return t.capitalize()

    def polish_transcript(
        self,
        transcript: str,
        *,
        task: str = "cleanup",
        format: Optional[str] = None,
        instruction: Optional[str] = None,
        rules: tuple[str, ...] = (),
        context: str = "general",
        timeout_seconds: Optional[float] = None,
        allow_fallback: bool = True,
    ) -> VF1EngineResult:
        """Execute local VF-1 transcription polishing guarded by factual safety gate."""
        start_time = time.perf_counter()
        timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds
        deadline = start_time + max(0.1, timeout)

        if not transcript or not transcript.strip():
            return VF1EngineResult(
                final_text=transcript,
                raw_output="",
                source_preserved=True,
                safety_accepted=True,
                safety_reasons=[],
                latency_ms=0.0,
                input_tokens=0,
                output_tokens=0,
                memory_mb=0.0,
                task=task,
                format=format or "auto",
                model_name=self.config.model_id,
            )

        # 1. Build contract request
        req = VF1Request(
            task=task,
            format=format,
            instruction=instruction,
            rules=rules,
            context=context,
            transcript=transcript.strip(),
        )

        _, _, prompt_text = self.build_chatml_prompt(req)

        # 2. Local Model Inference
        raw_output = ""
        input_token_count = len(prompt_text.split())
        output_token_count = 0
        memory_mb = 0.0

        if self.config.backend == "mock" or self._mock_generator is not None:
            raw_output = self._execute_mock(prompt_text, req)
            output_token_count = len(raw_output.split())
        else:
            # Native local inference via llama_cpp or transformers
            raw_output = self._run_native_inference(prompt_text, deadline)
            output_token_count = len(raw_output.split()) if raw_output else 0

        # Post-clean generated tokens
        clean_candidate = self._sanitize_raw_output(raw_output, transcript)

        # 3. Deterministic Factual Preservation Safety Gate
        gate_decision: SafetyGateDecision = validate_and_gate_output(
            transcript=transcript,
            candidate_text=clean_candidate,
            task=task,
            instruction=instruction,
            allow_fallback=allow_fallback,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Telemetry
        model_label = f"{self.config.model_id} (VF-1 LoRA)" if self.config.use_lora else f"{self.config.model_id} (VF-1 Base)"
        telemetry = {
            "model": model_label,
            "task": task,
            "format": format or "auto",
            "latency_ms": elapsed_ms,
            "input_tokens": input_token_count,
            "output_tokens": output_token_count,
            "safety_accepted": gate_decision.accepted,
            "source_preserved": gate_decision.source_preserved,
            "rejection_reasons": gate_decision.rejection_reasons,
        }
        self._last_telemetry = telemetry

        if not gate_decision.accepted:
            log.warning(
                "[VF-1] Output rejected by factual safety gate: %s. Preserved original transcript.",
                gate_decision.rejection_reasons,
            )

        return VF1EngineResult(
            final_text=gate_decision.final_text,
            raw_output=clean_candidate,
            source_preserved=gate_decision.source_preserved,
            safety_accepted=gate_decision.accepted,
            safety_reasons=gate_decision.rejection_reasons,
            latency_ms=elapsed_ms,
            input_tokens=input_token_count,
            output_tokens=output_token_count,
            memory_mb=memory_mb,
            task=task,
            format=format or "auto",
            model_name=model_label,
            adjudication_notes=gate_decision.rejection_reasons,
        )

    def _sanitize_raw_output(self, raw_output: str, source_transcript: str) -> str:
        """Strip control tags, prompt echoes, and thinking blocks."""
        if not raw_output:
            return source_transcript

        out = raw_output.strip()
        # Strip thinking tags if present
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL)
        out = re.sub(r"<think>.*", "", out, flags=re.DOTALL)
        out = out.replace("<|im_end|>", "").replace("<|endoftext|>", "")

        # Strip echoed contract headers or section markers
        out = re.sub(r"^\[(?:VF-1|Task:\s*\w+|Transcript|Rules|Instruction)\]\s*", "", out, flags=re.I)
        out = re.sub(r"^cleanup(?:,\s*task:\s*\w+)?\.?\s*", "", out, flags=re.I)
        out = out.strip().strip('"')
        return out if out else source_transcript

    def _run_native_inference(self, prompt_text: str, deadline: float) -> str:
        """Run native local inference (llama_cpp or transformers)."""
        # If llama_cpp is available and GGUF exists
        from voice_flow import s1_engine

        model_path = s1_engine.get_s1_model_path()
        if model_path and s1_engine.is_s1_runtime_available():
            try:
                from llama_cpp import Llama  # type: ignore

                with self._lock:
                    if self._loaded_model is None:
                        threads = max(1, min(8, os.cpu_count() or 4))
                        gpu_layers = -1 if sys.platform == "darwin" else 0
                        self._loaded_model = Llama(
                            model_path=str(model_path),
                            n_ctx=DEFAULT_CONTEXT_TOKENS,
                            n_threads=threads,
                            n_gpu_layers=gpu_layers,
                            verbose=False,
                        )
                    resp = self._loaded_model(
                        prompt_text,
                        max_tokens=self.config.max_new_tokens,
                        temperature=self.config.temperature,
                        top_k=1,
                        repeat_penalty=self.config.repetition_penalty,
                        stop=["<|im_end|>", "<|endoftext|>"],
                    )
                    choices = resp.get("choices") or []
                    if choices:
                        return str(choices[0].get("text") or "")
            except Exception as exc:
                log.warning("[VF-1] Local llama_cpp execution failed: %s", exc)

        return ""

    def get_last_telemetry(self) -> Optional[Dict[str, Any]]:
        """Return telemetry from last execution."""
        return self._last_telemetry


# Global singleton instance for application use
_default_vf1_engine: Optional[VF1Engine] = None


def get_vf1_engine() -> VF1Engine:
    """Get or initialize the global VF-1 engine instance."""
    global _default_vf1_engine
    if _default_vf1_engine is None:
        _default_vf1_engine = VF1Engine()
    return _default_vf1_engine
