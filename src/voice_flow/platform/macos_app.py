"""Set Cocoa identity before GUI initialization, independently of Python's bundle.

The packaged shell launcher execs a nested Python runtime. Consequently the
main NSBundle may describe Python rather than the outer application bundle.
Cocoa clients (including pywebview) read that effective bundle's dictionaries.
These changes are process-local; no installed Info.plist is rewritten.
"""
from __future__ import annotations

import logging
import sys
from typing import Literal

APP_NAME = "AI Productivity Flow"
_identity_configured = False


def configure_macos_app(
    role: Literal["engine", "desktop"], *, apply_policy: bool = True
) -> bool:
    """Brand the process and select a window-capable Cocoa activation policy.

    The engine calls with apply_policy=False before GUI imports so Tk can
    construct its TKApplication subclass. Reapply with the default after Tk
    creates its root: Tk can change activation policy during initialization. Importing this module
    has no Cocoa side effects, and callers importing desktop_launcher for focus
    helpers must not opt the engine into the desktop role.
    """
    global _identity_configured
    if sys.platform != "darwin":
        return False
    if role not in ("engine", "desktop"):
        raise ValueError(f"Unknown macOS application role: {role}")
    try:
        if not _identity_configured:
            from Foundation import NSBundle, NSProcessInfo

            NSProcessInfo.processInfo().setProcessName_(APP_NAME)
            bundle = NSBundle.mainBundle()
            # A localized dictionary can override the base CFBundleName. Update
            # both, rather than relying on the outer .app or only the process name.
            for info in (bundle.infoDictionary(), bundle.localizedInfoDictionary()):
                if info is not None:
                    info["CFBundleName"] = APP_NAME
                    info["CFBundleDisplayName"] = APP_NAME
            _identity_configured = True

        if not apply_policy:
            return True

        # Import only after identity is available: Cocoa backends may create
        # their shared NSApplication as soon as they are imported.
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )

        policy = (NSApplicationActivationPolicyRegular if role == "desktop"
                  else NSApplicationActivationPolicyAccessory)
        return bool(NSApplication.sharedApplication().setActivationPolicy_(policy))
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not configure macOS application identity (%s)", role, exc_info=True
        )
        return False
