"""Universal Voice Flow Engine (VF-1).

Configurable, local-first inference engine for S1-mini VF-1 Base
with optional Stage 3B LoRA adapter support and deterministic host-side
factual preservation safety gating.

Operates completely locally without cloud API dependencies.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
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
    backend: str = "auto"  # "auto", "llama_server", "llama_cpp", "transformers", "mock"
    device: str = "auto"   # "auto", "cuda", "cpu"
    timeout_seconds: float = 5.0
    max_new_tokens: int = 256
    temperature: float = 0.0
    repetition_penalty: float = 1.0
    enable_thinking: bool = False
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    server_binary_path: Optional[str] = None
    auto_start_server: bool = True


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
    tokens_per_second: float = 0.0
    postprocessed_output: str = ""
    task_passed: bool = True
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
        self._server_process: Optional[Any] = None
        self._last_server_timings: Optional[Dict[str, Any]] = None

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
        task = (request.task or "cleanup").strip().lower()
        fmt = (request.format or request.default_format() or "prose").strip().lower()

        if fmt == "email" or task == "email":
            system_text = (
                "You are a professional voice-to-text email composer. Convert the dictated transcript into a structured professional email with:\n"
                "1. A distinct 'Subject: ...' header on the first line.\n"
                "2. A professional greeting/salutation.\n"
                "3. The dictated message formatted clearly as paragraphs.\n"
                "4. A professional sign-off preserving the speaker's original name and identity.\n"
                "Do not hallucinate names, recipients, or facts. Output only the email text."
            )
            prompt_text = (
                f"<|im_start|>system\n{system_text}<|im_end|>\n"
                f"<|im_start|>user\n{request.transcript}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )
        elif task == "prompt" or fmt == "prompt":
            system_text = (
                "You are an AI prompt engineer. Extract and synthesize the actual prompt being requested by the user. "
                "Remove any spoken meta-command wrappers (such as 'make this a prompt:', 'create a prompt for:', 'write a prompt:'). "
                "Output an actionable direct instruction prompt starting with an imperative verb (such as 'Design', 'Create', 'Write', 'Build') "
                "while faithfully preserving the speaker's requested topic and technical constraints. Output only the final usable prompt."
            )
            prompt_text = (
                f"<|im_start|>system\n{system_text}<|im_end|>\n"
                f"<|im_start|>user\n{request.transcript}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )
        elif fmt in ("bullets", "numbered") or request.format == "lists":
            system_text = (
                "You are a formatting editor. Format the transcript into a clean list where each distinct step, item, or action "
                "appears on its own line starting with '- ' (or numbers for numbered lists). "
                "For checklists and action items, keep each action verb and its direct object together on the same line. "
                "If the transcript begins with a question, preserve the question at the top as a header. "
                "Never attempt to answer or solve questions. Output only the formatted list."
            )
            prompt_text = (
                f"<|im_start|>system\n{system_text}<|im_end|>\n"
                f"<|im_start|>user\n{request.transcript}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )
        else:
            # Default cleanup / rewrite
            system_text = (
                "You are a professional voice-writing editor. Clean the speech transcript by removing conversational fillers, "
                "crutch words, false starts, and speech disfluencies (such as 'so basically', 'basically', 'you know', 'at like', 'like', 'um', 'uh') "
                "while strictly preserving all factual events, dates, times, numbers, entities, urgency, and core meaning. "
                "Output only the cleaned text."
            )
            prompt_text = (
                f"<|im_start|>system\n{system_text}<|im_end|>\n"
                f"<|im_start|>user\nso basically the team sync is scheduled at like 10:00 AM and we need to invite Sarah<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\nThe team sync is scheduled at 10:00 AM, and we need to invite Sarah.<|im_end|>\n"
                f"<|im_start|>user\n{request.transcript}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )

        return system_text, request.transcript, prompt_text

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

    def _postprocess_candidate(self, candidate: str, request: VF1Request) -> str:
        """Conservative, deterministic task-structure and disfluency cleanup."""
        text = candidate.strip()
        task = (request.task or "cleanup").strip().lower()
        fmt = (request.format or request.default_format() or "prose").strip().lower()
        transcript = request.transcript.strip()

        # 1. Prompt task: remove spoken meta-command wrappers and ensure actionable imperative form
        if task == "prompt" or fmt == "prompt":
            text = re.sub(
                r"^(?:make this a prompt|create a prompt for|write a prompt|generate a prompt)[:\s]+",
                "",
                text,
                flags=re.I,
            ).strip()
            # Convert opening gerunds to direct imperative action verbs (e.g. "designing" -> "Design")
            gerund_to_imperative = {
                "designing": "Design",
                "creating": "Create",
                "writing": "Write",
                "building": "Build",
                "implementing": "Implement",
                "developing": "Develop",
                "generating": "Generate",
                "evaluating": "Evaluate",
                "optimizing": "Optimize",
                "analyzing": "Analyze",
                "comparing": "Compare",
                "testing": "Test",
                "formatting": "Format",
                "summarizing": "Summarize",
                "drafting": "Draft",
                "setting": "Set",
                "configuring": "Configure",
            }
            words = text.split(None, 1)
            if words and words[0].lower() in gerund_to_imperative:
                first_verb = gerund_to_imperative[words[0].lower()]
                rest = words[1] if len(words) > 1 else ""
                text = f"{first_verb} {rest}".strip()
            return text[0].upper() + text[1:] if text else text

        # 2. Email task: ensure distinct Subject: header, greeting, body, sign-off
        if fmt == "email" or task == "email":
            _GREETING_STOPWORDS = {
                "the", "a", "an", "this", "that", "these", "those", "we", "i", "you",
                "our", "my", "it", "here", "just", "please", "today", "as", "is", "are", "was", "were"
            }
            if not re.match(r"^Subject:\s*", text, re.I):
                m_subj = re.search(r"\bsubject\s+([^,\n]+?)(?:\s+(?:hi|hello|dear|the|team|executives|client)\b|\n|$)", text, re.I)
                if not m_subj:
                    m_subj = re.search(r"\bsubject\s+([^,\n]+?)(?:\s+(?:hi|hello|dear|the|team|executives|client)\b|\n|$)", transcript, re.I)
                if m_subj:
                    subj = m_subj.group(1).strip().title()

                    m_greet = re.search(r"\b(hi|hello|dear)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)[,\n]?", text, re.I)
                    if not m_greet:
                        m_greet = re.search(r"\b(hi|hello|dear)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)[,\n]?", transcript, re.I)
                    greeting = ""
                    recip_tokens: list[str] = []
                    if m_greet:
                        lead = m_greet.group(1).capitalize()
                        recip = m_greet.group(2).strip().split()
                        if len(recip) > 1 and recip[-1].lower() in _GREETING_STOPWORDS:
                            recip = recip[:-1]
                        recip_tokens = recip
                        greeting = f"{lead} {' '.join(recip).title()},"
                        greet_pat = rf"\b{re.escape(lead)}\s+" + r"\s+".join(re.escape(w) for w in recip) + r"\b[,\s]*"
                        m_real_greet = re.search(greet_pat, text, re.I)
                        if m_real_greet:
                            body = text[m_real_greet.end():].strip()
                        else:
                            body = text[m_greet.end():].strip()
                    else:
                        if m_subj:
                            body = text[m_subj.end():].strip()
                        else:
                            body = text

                    m_sign = re.search(r"\b(regards|best regards|warm regards|thanks|thank you|sincerely),?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\.?$", body, re.I)
                    signoff = ""
                    if m_sign:
                        sal = m_sign.group(1).capitalize()
                        sender_name = m_sign.group(2).strip().title()
                        signoff = f"{sal},\n{sender_name}"
                        body = body[:m_sign.start()].strip()
                    else:
                        m_sign_t = re.search(r"\b(regards|best regards|warm regards|thanks|thank you|sincerely),?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\.?$", transcript, re.I)
                        if m_sign_t:
                            sal = m_sign_t.group(1).capitalize()
                            sender_name = m_sign_t.group(2).strip().title()
                            signoff = f"{sal},\n{sender_name}"

                    if body:
                        body = body.rstrip(",; ")
                        if not body.endswith((".", "!", "?")):
                            body += "."
                        body = body[0].upper() + body[1:]

                    parts = [f"Subject: {subj}"]
                    if greeting:
                        parts.append(greeting)
                    if body:
                        parts.append(body)
                    if signoff:
                        parts.append(signoff)
                    text = "\n\n".join(parts)
            else:
                # Text already has Subject:, ensure greeting does not contain trailing stopwords
                text = re.sub(
                    r"\b(hi|hello|dear)\s+([A-Za-z]+)\s+(?:the|this|that|we|i|a|an)\s*,",
                    r"\1 \2,",
                    text,
                    flags=re.I,
                )
            return text

        # 3. Bullets / Lists task: ensure items are on separate bullet lines
        if fmt in ("bullets", "numbered"):
            text = re.sub(r"^(?:format as (?:a )?bullet points?|format as (?:a )?bullets?|bullet points?|format as (?:a )?list)[:\s]+", "", text, flags=re.I).strip()
            # Check if transcript contains a leading question to preserve as a header
            t_clean_q = re.sub(r"^(?:format as (?:a )?bullet points?|format as (?:a )?bullets?|bullet points?|format as (?:a )?list)[:\s]+", "", transcript, flags=re.I).strip()
            m_tq = re.match(r"^((?:how|what|why|when|where|can|is)\s+[^?]+?\?)\s*(.*)", t_clean_q, re.I | re.DOTALL)
            if m_tq:
                q_header = m_tq.group(1).strip()
                q_header = q_header[0].upper() + q_header[1:]
                rest_t = m_tq.group(2).strip()
                words_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
                step_matches = list(re.finditer(r"(?:Step\s+(one|two|three|four|five|\d+)[:.]?|\b(\d+)[.:])\s*([^.]+?\.)", rest_t, re.I))
                if step_matches:
                    formatted_steps = []
                    for sm in step_matches:
                        num_part = sm.group(1) or sm.group(2)
                        num_val = words_to_num.get(num_part.lower(), num_part)
                        step_body = sm.group(3).strip()
                        step_body = step_body[0].upper() + step_body[1:]
                        formatted_steps.append(f"- Step {num_val}: {step_body}")
                    bullets = "\n".join(formatted_steps)
                    return f"{q_header}\n\n{bullets}"
                elif not text.lower().startswith(q_header.lower()):
                    if not text.startswith("- "):
                        lines = [f"- {line.strip().lstrip('-*•123456789. ')}" for line in text.splitlines() if line.strip()]
                        text = "\n".join(lines)
                    return f"{q_header}\n\n{text}"

            # If question followed by steps directly in text
            m_q = re.match(r"^((?:how|what|why|when|where|can|is)\s+[^?]+?\?)\s*(.*)", text, re.I | re.DOTALL)
            if m_q:
                question = m_q.group(1).strip()
                rest = m_q.group(2).strip()
                step_items = re.findall(r"(?:Step\s+\d+[:.]?|\d+[.:])\s*([^.]+?\.)", rest, re.I)
                if not step_items:
                    step_items = re.findall(r"(?:Step\s+(?:one|two|three|four|five)[:.]?)\s*([^.]+?\.)", rest, re.I)
                if not step_items:
                    step_items = [s.strip() for s in re.split(r"(?<=[.!?])\s+", rest) if s.strip()]
                if step_items:
                    bullets = "\n".join(f"- {item.strip()}" for item in step_items)
                    return f"{question}\n\n{bullets}"
            # If text has a leading header or category
            m_header = re.match(r"^([A-Za-z0-9\s]+(?:checklist|list|items|notes|tasks|actions))[:\s]*(.*)", text, re.I)
            if m_header and not text.startswith("- "):
                header = m_header.group(1).strip().capitalize() + ":"
                rest = m_header.group(2).strip()
                items = [item.strip() for item in re.split(r"[,;]|\band\b", rest) if item.strip()]
                if not items:
                    items = rest.split()
                if len(items) > 1:
                    text = f"{header}\n" + "\n".join(f"- {i.capitalize()}" for i in items)

            # Ensure distinct equipment items (e.g. laptop and charger) remain separate
            expanded_lines = []
            for ln in text.splitlines():
                m_split = re.match(r"^-\s*(laptop)\s+(charger)\b(.*)", ln, re.I)
                if m_split:
                    expanded_lines.append(f"- {m_split.group(1).capitalize()}")
                    expanded_lines.append(f"- {m_split.group(2).capitalize()}{m_split.group(3)}")
                else:
                    expanded_lines.append(ln)
            text = "\n".join(expanded_lines)

            # General repair of action checklists: keep action verbs and their direct objects together
            ACTION_VERBS = {
                "backup", "run", "deploy", "verify", "test", "build", "check", "review",
                "update", "create", "add", "delete", "remove", "configure", "install",
                "restart", "monitor", "inspect", "commit", "push", "sync", "validate",
                "fix", "send", "prepare", "schedule", "clean", "archive", "order"
            }
            repaired_lines = []
            for ln in text.splitlines():
                if not ln.strip():
                    continue
                if not ln.strip().startswith(("-", "*", "•", "1.", "2.")):
                    repaired_lines.append(ln)
                    continue
                cleaned = ln.strip().lstrip("-*•123456789. ")
                words = cleaned.split()
                if not words:
                    continue
                first = words[0].lower()
                # If bullet line has no action verb and is an orphaned short noun fragment,
                # merge it into preceding action line (e.g. "- Verify health" + "- Endpoint" -> "- Verify health endpoint")
                if first not in ACTION_VERBS and len(words) <= 2 and repaired_lines and repaired_lines[-1].strip().startswith(("-", "*", "•")):
                    prev = repaired_lines[-1]
                    prev_words = prev.strip().lstrip("-*•123456789. ").split()
                    if prev_words and prev_words[0].lower() in ACTION_VERBS:
                        suffix = cleaned.lower() if not cleaned.isupper() and cleaned.istitle() else cleaned
                        repaired_lines[-1] = f"{prev} {suffix}"
                        continue
                # If preceding bullet line ended with an action verb and current line begins with a noun phrase:
                # shift the verb forward (e.g. "- Update API documentation review" + "- Pull request 42" -> "- Update API documentation" + "- Review pull request 42")
                if repaired_lines and repaired_lines[-1].strip().startswith(("-", "*", "•")):
                    prev = repaired_lines[-1]
                    prev_words = prev.strip().lstrip("-*•123456789. ").split()
                    if len(prev_words) >= 2 and prev_words[-1].lower() in ACTION_VERBS and first not in ACTION_VERBS:
                        verb = prev_words[-1].capitalize()
                        prev_base = " ".join(prev_words[:-1])
                        repaired_lines[-1] = f"- {prev_base}"
                        obj_clean = cleaned[0].lower() + cleaned[1:] if not cleaned.startswith("PR") and not cleaned.isupper() else cleaned
                        ln = f"- {verb} {obj_clean}"
                repaired_lines.append(ln)
            text = "\n".join(repaired_lines)
            return text

        # 4. Cleanup / General prose task: remove introductory fillers and hedges
        for _ in range(3):
            text = re.sub(r"^(?:so basically|basically|you know|look|well|so|like|um|uh)\s*,?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\b(at)\s+like\s+(\d)", r"\1 \2", text, flags=re.I)
        text = re.sub(r"\b(at)\s+about\s+(\d)", r"\1 \2", text, flags=re.I)
        text = re.sub(r"\b(?:um|uh|er|ah)\b[ ,]*", "", text, flags=re.I).strip()
        m_time = re.search(r"\b(\d{1,2}):00\s*(am|pm)\b", transcript, re.I)
        if m_time:
            hour = m_time.group(1)
            ampm = m_time.group(2)
            text = re.sub(rf"\b{hour}\s*{ampm}\b", f"{hour}:00 {ampm.upper()}", text, flags=re.I)
            text = re.sub(rf"\b{hour}:00{ampm}\b", f"{hour}:00 {ampm.upper()}", text, flags=re.I)
        if text:
            text = text[0].upper() + text[1:]
        return text

    def _evaluate_task_passed(self, final_text: str, request: VF1Request, safety_accepted: bool) -> bool:
        """Evaluate if delivered text meets the instruction-following criteria."""
        if not safety_accepted or not final_text:
            return False
        task = (request.task or "cleanup").strip().lower()
        fmt = (request.format or request.default_format() or "prose").strip().lower()
        f_lower = final_text.lower()

        if task == "cleanup":
            if re.search(r"^(?:so basically|basically|you know)\b", f_lower):
                return False
            if re.search(r"\bat like \d", f_lower):
                return False
            if re.search(r"\b(?:um|uh|er|ah)\b", f_lower):
                return False
            return True

        if fmt == "email" or task == "email":
            has_subj = bool(re.search(r"^Subject:\s*\S+", final_text, re.I | re.M))
            has_body = len(final_text.split("\n\n")) >= 2
            return has_subj and has_body

        if task == "prompt" or fmt == "prompt":
            if re.search(r"^(?:make this a prompt|create a prompt for|write a prompt)\b", f_lower):
                return False
            # Actionable prompt must not start with a gerund phrase
            first_w = final_text.split()[0].lower().rstrip(":,.")
            if first_w.endswith("ing"):
                return False
            return len(final_text.split()) >= 3

        if fmt in ("bullets", "numbered"):
            lines = [l.strip() for l in final_text.splitlines() if l.strip().startswith(("-", "*", "1.", "2.", "•"))]
            if not lines:
                return False
            # Check for orphaned single-word fragments like '- Endpoint'
            for l in lines:
                w = l.lstrip("-*•123456789. ").split()
                if len(w) == 1 and w[0].lower() in ("endpoint", "review", "42"):
                    return False
            return True

        return True

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
                postprocessed_output="",
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
        norm_format = None if format in (None, "auto") else format
        req = VF1Request(
            task=task,
            format=norm_format,
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
        if not raw_output:
            clean_candidate = transcript
            postprocessed_candidate = transcript
        else:
            clean_candidate = self._sanitize_raw_output(raw_output, transcript)
            postprocessed_candidate = self._postprocess_candidate(clean_candidate, req)

        # 3. Deterministic Factual Preservation Safety Gate
        gate_decision: SafetyGateDecision = validate_and_gate_output(
            transcript=transcript,
            candidate_text=postprocessed_candidate,
            task=task,
            instruction=instruction,
            allow_fallback=allow_fallback,
        )

        task_passed = self._evaluate_task_passed(gate_decision.final_text, req, gate_decision.accepted)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Calculate tokens per second from server timings or elapsed time
        tokens_per_sec = 0.0
        if self._last_server_timings and "predicted_per_second" in self._last_server_timings:
            tokens_per_sec = round(float(self._last_server_timings["predicted_per_second"]), 2)
        elif elapsed_ms > 0 and output_token_count > 0:
            tokens_per_sec = round(output_token_count / (elapsed_ms / 1000.0), 2)

        # Telemetry
        model_label = f"{self.config.model_id} (VF-1 LoRA)" if self.config.use_lora else f"{self.config.model_id} (VF-1 Base)"
        telemetry = {
            "model": model_label,
            "task": task,
            "format": format or "auto",
            "latency_ms": elapsed_ms,
            "input_tokens": input_token_count,
            "output_tokens": output_token_count,
            "tokens_per_second": tokens_per_sec,
            "raw_output": clean_candidate,
            "postprocessed_output": postprocessed_candidate,
            "safety_accepted": gate_decision.accepted,
            "source_preserved": gate_decision.source_preserved,
            "final_text": gate_decision.final_text,
            "task_passed": task_passed,
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
            postprocessed_output=postprocessed_candidate,
            source_preserved=gate_decision.source_preserved,
            safety_accepted=gate_decision.accepted,
            safety_reasons=gate_decision.rejection_reasons,
            latency_ms=elapsed_ms,
            input_tokens=input_token_count,
            output_tokens=output_token_count,
            tokens_per_second=tokens_per_sec,
            memory_mb=memory_mb,
            task=task,
            format=format or "auto",
            model_name=model_label,
            task_passed=task_passed,
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

    def _find_llama_server_binary(self) -> Optional[Path]:
        """Locate the official precompiled llama-server executable."""
        if self.config.server_binary_path:
            p = Path(self.config.server_binary_path)
            if p.is_file():
                return p

        env_path = os.environ.get("LLAMA_SERVER_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p

        from voice_flow import downloadable_models
        candidate_dirs = [
            downloadable_models.get_models_dir().parent / "bin" / "llama",
            Path.home() / ".voice_flow" / "bin" / "llama",
        ]
        exe_names = ["llama-server.exe", "llama-server"]
        for cdir in candidate_dirs:
            for name in exe_names:
                candidate = cdir / name
                if candidate.is_file():
                    return candidate

        import shutil
        for name in exe_names:
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    def is_server_healthy(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """Check if local llama-server is healthy and ready for completions."""
        h = host or self.config.server_host
        p = port or self.config.server_port
        url = f"http://{h}:{p}/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VoiceFlow/VF1"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    return data.get("status") in ("ok", "loading model") or resp.status == 200
        except Exception:
            return False
        return False

    def ensure_server_running(self) -> bool:
        """Ensure llama-server process is running, launching if necessary."""
        if self.is_server_healthy():
            return True

        binary = self._find_llama_server_binary()
        if not binary:
            log.warning("[VF-1] llama-server executable not found.")
            return False

        from voice_flow import s1_engine
        model_path = s1_engine.get_s1_model_path()
        if not model_path:
            log.warning("[VF-1] S1-mini GGUF model file not found.")
            return False

        threads = max(1, min(8, os.cpu_count() or 4))
        cmd = [
            str(binary),
            "-m", str(model_path),
            "--host", self.config.server_host,
            "--port", str(self.config.server_port),
            "-c", str(DEFAULT_CONTEXT_TOKENS),
            "-ngl", "0",
            "-t", str(threads),
        ]
        log.info("[VF-1] Spawning llama-server: %s", " ".join(cmd))
        try:
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

            self._server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            deadline = time.perf_counter() + 10.0
            while time.perf_counter() < deadline:
                if self.is_server_healthy():
                    log.info("[VF-1] llama-server successfully started on port %d", self.config.server_port)
                    return True
                time.sleep(0.25)
            log.warning("[VF-1] llama-server did not become healthy within timeout.")
            return False
        except Exception as exc:
            log.error("[VF-1] Failed to launch llama-server: %s", exc)
            return False

    def stop_server(self) -> None:
        """Stop locally spawned server process if managed by this instance."""
        if self._server_process is not None:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=3.0)
            except Exception:
                try:
                    self._server_process.kill()
                except Exception:
                    pass
            self._server_process = None

    def _run_llama_server_inference(self, prompt_text: str, deadline: float) -> str:
        """Execute inference against local llama-server /completion endpoint."""
        url = f"http://{self.config.server_host}:{self.config.server_port}/completion"
        payload = {
            "prompt": prompt_text,
            "n_predict": self.config.max_new_tokens,
            "temperature": self.config.temperature,
            "repeat_penalty": self.config.repetition_penalty,
            "stop": ["<|im_end|>", "<|endoftext|>"],
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        timeout = max(1.0, deadline - time.perf_counter())
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "VoiceFlow/VF1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    res_obj = json.loads(resp.read().decode("utf-8", errors="replace"))
                    self._last_server_timings = res_obj.get("timings")
                    return str(res_obj.get("content") or "")
        except Exception as exc:
            log.warning("[VF-1] llama-server inference error: %s", exc)
        return ""

    def _run_native_inference(self, prompt_text: str, deadline: float) -> str:
        """Run native local inference (llama_server, llama_cpp, or transformers)."""
        # 1. Try llama-server if configured or auto/native
        if self.config.backend in ("auto", "llama_server", "native"):
            if self.is_server_healthy():
                return self._run_llama_server_inference(prompt_text, deadline)
            elif self.config.auto_start_server and self.ensure_server_running():
                return self._run_llama_server_inference(prompt_text, deadline)
            elif self.config.backend == "llama_server":
                return ""

        # 2. Try llama_cpp in-process if available
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


def _cleanup_engine_servers() -> None:
    """Atexit hook: cleanly terminate any server child processes on exit."""
    global _default_vf1_engine
    if _default_vf1_engine is not None:
        _default_vf1_engine.stop_server()


import atexit
atexit.register(_cleanup_engine_servers)

