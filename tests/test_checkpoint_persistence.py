#!/usr/bin/env python3
"""Unit tests for checkpoint persistence, verification, recovery, and optimizer telemetry."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import pytest

from research.vf_phase3a.checkpoint_persistence import (
    CheckpointPersistenceError,
    ChecksumMismatchError,
    MissingSourceArtifactError,
    PersistenceStorageError,
    compute_sha256,
    export_and_verify_checkpoint,
)


@pytest.fixture
def temp_checkpoint_dirs():
    source_dir = tempfile.mkdtemp(prefix="vf_src_")
    target_dir = tempfile.mkdtemp(prefix="vf_tgt_")

    # Create dummy adapter files
    weights_path = os.path.join(source_dir, "adapter_model.safetensors")
    with open(weights_path, "wb") as f:
        f.write(b"SAMPLE_LORA_WEIGHTS_BINARY_TENSORS_DATA_1234567890")

    config_path = os.path.join(source_dir, "adapter_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"peft_type": "LORA", "r": 16, "lora_alpha": 32}, f)

    yield source_dir, target_dir

    shutil.rmtree(source_dir, ignore_errors=True)
    shutil.rmtree(target_dir, ignore_errors=True)


def test_successful_export_and_readback_verification(temp_checkpoint_dirs):
    source_dir, target_dir = temp_checkpoint_dirs

    manifest = export_and_verify_checkpoint(source_dir, target_dir)

    assert manifest["status"] == "VERIFIED_DURABLE"
    assert "adapter_model.safetensors" in manifest["files"]
    assert "adapter_config.json" in manifest["files"]

    tgt_weights = os.path.join(target_dir, "adapter_model.safetensors")
    tgt_config = os.path.join(target_dir, "adapter_config.json")
    assert os.path.exists(tgt_weights)
    assert os.path.exists(tgt_config)

    src_weights_hash = compute_sha256(os.path.join(source_dir, "adapter_model.safetensors"))
    tgt_weights_hash = compute_sha256(tgt_weights)
    assert src_weights_hash == tgt_weights_hash
    assert manifest["files"]["adapter_model.safetensors"]["sha256"] == tgt_weights_hash

    # Verify durable manifest exists in both locations
    assert os.path.exists(os.path.join(source_dir, "durable_checkpoint_manifest.json"))
    assert os.path.exists(os.path.join(target_dir, "durable_checkpoint_manifest.json"))


def test_missing_required_source_artifacts():
    empty_src = tempfile.mkdtemp(prefix="vf_empty_")
    target_dir = tempfile.mkdtemp(prefix="vf_tgt_")
    try:
        with pytest.raises(MissingSourceArtifactError) as exc_info:
            export_and_verify_checkpoint(empty_src, target_dir)
        err = exc_info.value
        assert "missing required checkpoint files" in str(err)
        assert "CRITICAL RECOVERY PROCEDURE" in err.recovery_advice
    finally:
        shutil.rmtree(empty_src, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)


def test_corrupted_copy_detection(temp_checkpoint_dirs, monkeypatch):
    source_dir, target_dir = temp_checkpoint_dirs

    # Monkeypatch shutil.copy2 to simulate silent bit flip / corruption during export
    real_copy2 = shutil.copy2

    def corrupting_copy2(src, dst):
        real_copy2(src, dst)
        if "adapter_model.safetensors" in dst:
            with open(dst, "ab") as f:
                f.write(b"CORRUPTED_EXTRA_BYTES")

    monkeypatch.setattr(shutil, "copy2", corrupting_copy2)

    with pytest.raises(ChecksumMismatchError) as exc_info:
        export_and_verify_checkpoint(source_dir, target_dir)

    err = exc_info.value
    assert "Integrity check failed" in str(err)
    assert "CRITICAL RECOVERY PROCEDURE" in err.recovery_advice
    # Verify temporary corrupted file was cleaned up
    assert not os.path.exists(os.path.join(target_dir, "adapter_model.safetensors.export_tmp"))
    assert not os.path.exists(os.path.join(target_dir, "adapter_model.safetensors"))


def test_missing_or_unwritable_storage_location(temp_checkpoint_dirs, monkeypatch):
    source_dir, target_dir = temp_checkpoint_dirs

    # Simulate an unwritable destination (e.g. unmounted Drive or permission error)
    def failing_makedirs(name, exist_ok=False):
        raise PermissionError(f"Permission denied on {name}")

    monkeypatch.setattr(os, "makedirs", failing_makedirs)

    with pytest.raises(PersistenceStorageError) as exc_info:
        export_and_verify_checkpoint(source_dir, target_dir)

    err = exc_info.value
    assert "unwritable or inaccessible" in str(err)
    assert "CRITICAL RECOVERY PROCEDURE" in err.recovery_advice


def test_interrupted_or_truncated_export(temp_checkpoint_dirs, monkeypatch):
    source_dir, target_dir = temp_checkpoint_dirs

    # Simulate truncated write
    real_copy2 = shutil.copy2

    def truncating_copy2(src, dst):
        real_copy2(src, dst)
        if "adapter_model.safetensors" in dst:
            with open(dst, "r+b") as f:
                f.truncate(10)  # Truncate to 10 bytes

    monkeypatch.setattr(shutil, "copy2", truncating_copy2)

    with pytest.raises(ChecksumMismatchError) as exc_info:
        export_and_verify_checkpoint(source_dir, target_dir)

    err = exc_info.value
    assert "Integrity check failed" in str(err)
    assert "CRITICAL RECOVERY PROCEDURE" in err.recovery_advice


def test_optimizer_telemetry_skip_detection_logic():
    """Verify that simulated AMP overflow increments attempted steps but NOT successful updates."""
    # Simulation of the trainer's step execution logic
    class MockScaler:
        def __init__(self, init_scale=65536.0):
            self.scale = init_scale
            self.overflow_next = False

        def get_scale(self):
            return self.scale

        def unscale_(self, opt):
            pass

        def step(self, opt):
            if self.overflow_next:
                return None
            opt.stepped = True
            return True

        def update(self):
            if self.overflow_next:
                self.scale /= 2.0
                self.overflow_next = False

    class MockOpt:
        def __init__(self):
            self.stepped = False

        def zero_grad(self, set_to_none=True):
            self.stepped = False

    class MockSch:
        def __init__(self):
            self.steps = 0

        def step(self):
            self.steps += 1

    scaler = MockScaler()
    opt = MockOpt()
    sch = MockSch()

    attempted_steps, successful_updates, overflow_steps = 0, 0, 0

    # Iteration 1: Overflow happens
    scaler.overflow_next = True
    scale_before = scaler.get_scale()
    scaler.unscale_(opt)
    scaler.step(opt)
    scaler.update()
    scale_after = scaler.get_scale()

    step_skipped = bool(scale_after < scale_before)
    attempted_steps += 1
    if not step_skipped:
        successful_updates += 1
        sch.step()
    else:
        overflow_steps += 1

    assert attempted_steps == 1
    assert successful_updates == 0
    assert overflow_steps == 1
    assert sch.steps == 0  # Scheduler was NOT advanced

    # Iteration 2: Normal execution
    scale_before = scaler.get_scale()
    scaler.unscale_(opt)
    scaler.step(opt)
    scaler.update()
    scale_after = scaler.get_scale()

    step_skipped = bool(scale_after < scale_before)
    attempted_steps += 1
    if not step_skipped:
        successful_updates += 1
        sch.step()
    else:
        overflow_steps += 1

    assert attempted_steps == 2
    assert successful_updates == 1
    assert overflow_steps == 1
    assert sch.steps == 1  # Scheduler advanced once for the successful update
