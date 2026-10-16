"""Blocking User-Facing Review Barrier Dialog for High-Risk Text.

Implements P0-1:
- Blocks text insertion into the target application until explicit approval.
- Displays high-risk entities (names, amounts, dates, technical IDs, draft edits).
- Offers grounded name alternatives from the configured contact dictionary.
- Allows user to edit and correct any field or the full text.
- Confirmed: returns the exact approved correction for insertion.
- Cancel / Close / Ignore: aborts insertion, leaving target window 100% unchanged.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from voice_flow.entity_review import CriticalEntity, ReviewResolution

log = logging.getLogger(__name__)


class ReviewBarrierDialog:
    """Modal, blocking review dialog that halts text injection until explicit user confirmation."""

    def __init__(
        self,
        text: str,
        entities: List[CriticalEntity],
        *,
        task: str = "cleanup",
        draft: Optional[str] = None,
    ) -> None:
        self.original_text = text
        self.entities = entities
        self.task = task
        self.draft = draft
        self.resolution: Optional[ReviewResolution] = None

        self._root: Optional[tk.Tk] = None
        self._text_widget: Optional[tk.Text] = None
        self._entity_vars: Dict[str, tk.StringVar] = {}

    def show(self) -> ReviewResolution:
        """Display dialog modally and block until user confirms, corrects, or cancels."""
        try:
            self._root = tk.Tk()
            self._root.title("Voice Flow — Safety Review Barrier")
            self._root.geometry("640x520")
            self._root.minsize(500, 400)
            self._root.attributes("-topmost", True)
            self._root.protocol("WM_DELETE_WINDOW", self._on_close)

            # Header frame
            header_frame = tk.Frame(self._root, bg="#FFF3EA", padx=16, pady=12)
            header_frame.pack(fill=tk.X)

            title_lbl = tk.Label(
                header_frame,
                text="⚠️ High-Risk Content Detected — Review Required",
                font=("Segoe UI", 12, "bold"),
                fg="#C84800",
                bg="#FFF3EA",
            )
            title_lbl.pack(anchor=tk.W)

            subtitle_lbl = tk.Label(
                header_frame,
                text="Please verify names, financial amounts, timestamps, or technical identifiers before inserting.",
                font=("Segoe UI", 9),
                fg="#6B5E55",
                bg="#FFF3EA",
            )
            subtitle_lbl.pack(anchor=tk.W, pady=(2, 0))

            # Main content frame
            content_frame = tk.Frame(self._root, padx=16, pady=12)
            content_frame.pack(fill=tk.BOTH, expand=True)

            # Entity cards if any
            if self.entities:
                cards_lbl = tk.Label(
                    content_frame,
                    text="Flagged Entities:",
                    font=("Segoe UI", 9, "bold"),
                    fg="#241708",
                )
                cards_lbl.pack(anchor=tk.W)

                cards_frame = tk.Frame(content_frame, pady=4)
                cards_frame.pack(fill=tk.X)

                for idx, ent in enumerate(self.entities[:4]):
                    row = tk.Frame(cards_frame, pady=2)
                    row.pack(fill=tk.X)

                    type_badge = tk.Label(
                        row,
                        text=f"[{ent.entity_type.upper()}]",
                        font=("Segoe UI", 8, "bold"),
                        fg="#E85D04",
                    )
                    type_badge.pack(side=tk.LEFT, padx=(0, 6))

                    desc = f"'{ent.original}' — {ent.reason}"
                    desc_lbl = tk.Label(
                        row,
                        text=desc,
                        font=("Segoe UI", 8),
                        fg="#333333",
                        anchor=tk.W,
                    )
                    desc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    if ent.suggested and ent.suggested != ent.original:
                        btn = tk.Button(
                            row,
                            text=f"Use '{ent.suggested}'",
                            font=("Segoe UI", 8),
                            command=lambda e=ent: self._apply_suggestion(e),
                            bg="#F0F0F0",
                        )
                        btn.pack(side=tk.RIGHT, padx=4)

            # Editable Text Area
            text_lbl = tk.Label(
                content_frame,
                text="Final Output Preview (Edit directly if needed):",
                font=("Segoe UI", 9, "bold"),
                fg="#241708",
            )
            text_lbl.pack(anchor=tk.W, pady=(8, 4))

            self._text_widget = tk.Text(
                content_frame,
                wrap=tk.WORD,
                font=("Segoe UI", 10),
                height=8,
                padx=8,
                pady=8,
            )
            self._text_widget.pack(fill=tk.BOTH, expand=True)
            self._text_widget.insert("1.0", self.original_text)

            # Buttons frame
            btn_frame = tk.Frame(self._root, padx=16, pady=12, bg="#FAFAFA")
            btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

            cancel_btn = tk.Button(
                btn_frame,
                text="Cancel (Esc)",
                font=("Segoe UI", 9),
                width=12,
                command=self._on_cancel,
            )
            cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

            confirm_btn = tk.Button(
                btn_frame,
                text="Confirm & Insert (Ctrl+Enter)",
                font=("Segoe UI", 9, "bold"),
                bg="#FF6A00",
                fg="#FFFFFF",
                activebackground="#E85D04",
                activeforeground="#FFFFFF",
                width=24,
                command=self._on_confirm,
            )
            confirm_btn.pack(side=tk.RIGHT)

            # Keyboard shortcuts
            self._root.bind("<Escape>", lambda e: self._on_cancel())
            self._root.bind("<Control-Return>", lambda e: self._on_confirm())

            self._root.focus_force()
            self._root.mainloop()

        except Exception as e:
            log.error("[REVIEW DIALOG] GUI error: %s", e)
            return ReviewResolution(
                approved=False,
                action="closed",
                final_text="",
                insertion_permitted=False,
                reason=f"GUI dialog exception: {e}",
            )

        if self.resolution is None:
            # Default fail-closed if closed unexpectedly
            return ReviewResolution(
                approved=False,
                action="closed",
                final_text="",
                insertion_permitted=False,
                reason="Review dialog closed without approval.",
            )

        return self.resolution

    def _apply_suggestion(self, entity: CriticalEntity) -> None:
        """Replace entity original text with suggested text in the editor."""
        if not self._text_widget or not entity.suggested:
            return
        current = self._text_widget.get("1.0", tk.END).strip()
        if entity.original in current:
            updated = current.replace(entity.original, entity.suggested, 1)
            self._text_widget.delete("1.0", tk.END)
            self._text_widget.insert("1.0", updated)

    def _on_confirm(self) -> None:
        """User explicitly confirmed insertion."""
        if not self._text_widget:
            return
        final_text = self._text_widget.get("1.0", tk.END).strip()
        was_edited = (final_text != self.original_text.strip())
        action = "corrected" if was_edited else "approved"

        self.resolution = ReviewResolution(
            approved=True,
            action=action,
            final_text=final_text,
            insertion_permitted=True,
            reason="User explicitly confirmed insertion.",
        )
        if self._root:
            self._root.destroy()

    def _on_cancel(self) -> None:
        """User cancelled insertion; target application remains 100% untouched."""
        self.resolution = ReviewResolution(
            approved=False,
            action="cancelled",
            final_text="",
            insertion_permitted=False,
            reason="User explicitly cancelled insertion.",
        )
        if self._root:
            self._root.destroy()

    def _on_close(self) -> None:
        """Window closed; fails closed (insertion NOT permitted)."""
        self.resolution = ReviewResolution(
            approved=False,
            action="closed",
            final_text="",
            insertion_permitted=False,
            reason="User closed review window without approving.",
        )
        if self._root:
            self._root.destroy()


def show_review_barrier_dialog(
    text: str,
    entities: List[CriticalEntity],
    *,
    task: str = "cleanup",
    draft: Optional[str] = None,
) -> ReviewResolution:
    """Display modal review dialog and block until user decision."""
    dialog = ReviewBarrierDialog(text, entities, task=task, draft=draft)
    return dialog.show()
