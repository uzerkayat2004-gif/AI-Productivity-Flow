#!/usr/bin/env python3
"""Checkpoint persistence and verification module for Voice Flow (VF-1).

Guarantees that valuable model checkpoints (adapter_model.safetensors, adapter_config.json)
are safely copied to persistent, access-controlled storage outside the temporary Colab runtime,
read back byte-for-byte to verify cryptographic integrity, and documented in a durable manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_CHECKPOINT_FILES = ("adapter_model.safetensors", "adapter_config.json")
OPTIONAL_CHECKPOINT_FILES = ("README.md", "run_config.json", "metrics.jsonl", "provenance.json")


class CheckpointPersistenceError(Exception):
    """Base exception for checkpoint persistence failures."""
    def __init__(self, message: str, recovery_advice: str):
        super().__init__(message)
        self.message = message
        self.recovery_advice = recovery_advice

    def __str__(self) -> str:
        return f"{self.message}\n\n[EXPLICIT RECOVERY PROCEDURE]:\n{self.recovery_advice}"


class PersistenceStorageError(CheckpointPersistenceError):
    """Raised when destination storage cannot be created or is not writable."""
    pass


class ChecksumMismatchError(CheckpointPersistenceError):
    """Raised when readback hash does not match source file hash."""
    pass


class MissingSourceArtifactError(CheckpointPersistenceError):
    """Raised when required training artifacts are missing from source directory."""
    pass


def compute_sha256(path: str) -> str:
    """Compute SHA-256 checksum of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_recovery_instructions(source_dir: str, target_dir: str) -> str:
    """Provide detailed, actionable recovery instructions in case export fails."""
    return f"""================================================================================
CRITICAL RECOVERY PROCEDURE: DO NOT CLOSE OR TERMINATE THE COLAB RUNTIME!
The trained checkpoint is located in the local runtime directory:
  --> {os.path.abspath(source_dir)}

To manually recover and persist this checkpoint:

Option A: Mount Google Drive and Copy Manually
1. In a new notebook cell, run:
   from google.colab import drive
   drive.mount('/content/drive')
2. Copy the checkpoint files:
   !mkdir -p /content/drive/MyDrive/VoiceFlow_Checkpoints/run_backup
   !cp -r {source_dir}/* /content/drive/MyDrive/VoiceFlow_Checkpoints/run_backup/
3. Verify file hashes in Drive:
   !sha256sum /content/drive/MyDrive/VoiceFlow_Checkpoints/run_backup/*

Option B: Download Directly via Colab CLI (from your local machine)
Run in PowerShell / bash on your host machine:
   colab download "{source_dir}/adapter_model.safetensors" ./adapter_model.safetensors
   colab download "{source_dir}/adapter_config.json" ./adapter_config.json

Option C: Verify and Retry Persistence
Check permissions on target path: '{target_dir}'
Re-run the persistence cell with an accessible directory before shutting down.
================================================================================"""


def export_and_verify_checkpoint(
    source_dir: str,
    target_dir: str,
    extra_files: Optional[List[str]] = None,
    allow_missing_optional: bool = True,
) -> Dict[str, Any]:
    """Export checkpoint files to persistent storage and verify readback integrity.

    Args:
        source_dir: Path to directory containing saved adapter files.
        target_dir: Path to durable storage (e.g., Google Drive mount or local backup).
        extra_files: Additional filenames to copy and verify (e.g., metrics.jsonl).
        allow_missing_optional: If True, optional files won't raise errors if missing.

    Returns:
        Manifest dictionary with verified file checksums and durable status.

    Raises:
        MissingSourceArtifactError: If required adapter files are missing.
        PersistenceStorageError: If target directory cannot be created/written.
        ChecksumMismatchError: If readback hash fails to match source hash.
    """
    recovery = get_recovery_instructions(source_dir, target_dir)

    # 1. Verify source directory exists
    if not os.path.exists(source_dir):
        raise MissingSourceArtifactError(
            f"Source adapter directory does not exist: {source_dir}",
            recovery,
        )

    # 2. Check for required files
    missing_required = [f for f in REQUIRED_CHECKPOINT_FILES if not os.path.exists(os.path.join(source_dir, f))]
    if missing_required:
        raise MissingSourceArtifactError(
            f"Source directory missing required checkpoint files: {missing_required}",
            recovery,
        )

    # 3. Determine list of files to export
    files_to_export = list(REQUIRED_CHECKPOINT_FILES)
    for opt in (extra_files or []) + list(OPTIONAL_CHECKPOINT_FILES):
        if opt not in files_to_export:
            p = os.path.join(source_dir, opt)
            if os.path.exists(p):
                files_to_export.append(opt)
            elif not allow_missing_optional and extra_files and opt in extra_files:
                raise MissingSourceArtifactError(
                    f"Requested extra file not found in source: {opt}",
                    recovery,
                )

    # 4. Prepare target directory
    try:
        os.makedirs(target_dir, exist_ok=True)
        # Test writability with a sentinel probe
        probe_path = os.path.join(target_dir, ".write_probe.tmp")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("probe")
        os.remove(probe_path)
    except Exception as exc:
        raise PersistenceStorageError(
            f"Target persistent directory '{target_dir}' is unwritable or inaccessible: {exc}",
            recovery,
        )

    # 5. Measure source files
    source_stats = {}
    for fname in files_to_export:
        src_file = os.path.join(source_dir, fname)
        size = os.path.getsize(src_file)
        sha = compute_sha256(src_file)
        source_stats[fname] = {"size": size, "sha256": sha}

    # 6. Atomic copy and read-back verification
    verified_files = {}
    for fname, stat in source_stats.items():
        src_file = os.path.join(source_dir, fname)
        tgt_file = os.path.join(target_dir, fname)
        tmp_tgt = tgt_file + ".export_tmp"

        try:
            # Copy to temporary file first
            shutil.copy2(src_file, tmp_tgt)

            # Read back from target storage and compute SHA-256
            readback_size = os.path.getsize(tmp_tgt)
            readback_sha = compute_sha256(tmp_tgt)

            if readback_size != stat["size"] or readback_sha != stat["sha256"]:
                if os.path.exists(tmp_tgt):
                    os.remove(tmp_tgt)
                raise ChecksumMismatchError(
                    f"Integrity check failed for {fname}! Expected SHA-256 {stat['sha256']} "
                    f"({stat['size']} bytes), got {readback_sha} ({readback_size} bytes).",
                    recovery,
                )

            # Commit atomic rename
            if os.path.exists(tgt_file):
                os.remove(tgt_file)
            os.rename(tmp_tgt, tgt_file)

            verified_files[fname] = {
                "size_bytes": readback_size,
                "sha256": readback_sha,
                "verified_readback": True,
            }
        except ChecksumMismatchError:
            raise
        except Exception as exc:
            if os.path.exists(tmp_tgt):
                os.remove(tmp_tgt)
            raise CheckpointPersistenceError(
                f"Failed during export of {fname}: {exc}",
                recovery,
            )

    # 7. Create durable manifest
    manifest = {
        "status": "VERIFIED_DURABLE",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_dir": os.path.abspath(source_dir),
        "target_dir": os.path.abspath(target_dir),
        "files_count": len(verified_files),
        "files": verified_files,
        "note": "All checkpoint files verified byte-for-byte against source before reporting success.",
    }

    # Save manifest in both source and target directories
    src_manifest = os.path.join(source_dir, "durable_checkpoint_manifest.json")
    tgt_manifest = os.path.join(target_dir, "durable_checkpoint_manifest.json")
    with open(src_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(tgt_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest
