"""QA dispatcher (qa/v1.0.2-final branch only). The phase to run is in PHASE next to this file.
usage (from the workflow): walkthrough.py OUT_DIR NATIVE_HELPER"""
import os
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
phase = (here / "PHASE").read_text().strip() if (here / "PHASE").exists() else "ui"
# qa/int-<phase> branches all share one commit: the branch name picks the phase,
# so several phases can be dispatched in parallel without racing on PHASE.
_ref = os.environ.get("GITHUB_REF_NAME", "")
if _ref.startswith("qa/int-"):
    phase = _ref[len("qa/int-"):]
os.environ["QA_OUT"] = str(Path(sys.argv[1]).resolve())
os.environ["QA_HELPER"] = str(Path(sys.argv[2]).resolve())
sys.path.insert(0, str(here))
print(f"QA phase: {phase}", flush=True)
if phase == "install":
    import qa_install
    qa_install.main()
elif phase in ("voice_a", "voice_b"):
    import qa_voice
    qa_voice.main(phase)
elif phase == "native_diag":
    import qa_native_diag
    qa_native_diag.main()
elif phase == "life":
    import qa_life
    qa_life.main()
elif phase == "af":
    import qa_af
    qa_af.main()
elif phase == "af2":
    import qa_af2
    qa_af2.main()
elif phase == "site":
    import runpy
    runpy.run_path(str(here / "qa_site.py"), run_name="__main__")
else:
    import qa_ui
    qa_ui.main()
sys.exit(0)
