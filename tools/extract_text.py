"""Copy the exact supplied Greek and phrase list from starter.md.

Run only when starter.md is updated; the generated UTF-8 files are checked in.
"""

from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
starter = (root / "starter.md").read_text(encoding="utf-8")
transcript = starter.split("Use this exact text as the authoritative transcript:\n\n", 1)[1].split("\n\nStore this as UTF-8.", 1)[0]
phrases_section = starter.split("Start with these logical units, adjusting only if actual timing/readability strongly suggests a neighboring boundary is better:\n\n", 1)[1].split("\n\nDerive phrase start/end times", 1)[0]
phrases = [match.group(1) for match in re.finditer(r"(?m)^\d+\. (.+)$", phrases_section)]
if len(phrases) != 24:
    raise SystemExit(f"Expected 24 phrases, got {len(phrases)}")
(root / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
(root / "phrases.txt").write_text("\n".join(phrases) + "\n", encoding="utf-8")
