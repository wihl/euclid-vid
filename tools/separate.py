"""Run ClearVoice two-speaker separation locally for comparison.

Run with ``sample`` (20 s) or ``full`` (entire source). The model writes
``_s1.wav`` and ``_s2.wav`` files; selecting a source needs an empirical check.
"""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
os.environ.setdefault("HF_HOME", str(WORK / "hf-home"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORK / "cache"))
os.chdir(WORK)

from clearvoice import ClearVoice  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
if mode not in ("sample", "full"):
    raise SystemExit("Usage: separate.py [sample|full]")
source = WORK / ("audio-samples/original-16k.wav" if mode == "sample" else "audio-original-16k.wav")
target = WORK / ("audio-samples/separated.wav" if mode == "sample" else "audio-separated.wav")
model = ClearVoice(task="speech_separation", model_names=["MossFormer2_SS_16K"])
marker = WORK / "checkpoints/MossFormer2_SS_16K/last_best_checkpoint"
if not marker.exists():
    raise SystemExit("Separation model weights unavailable")
result = model(str(source), online_write=False)
model.write(result, output_path=str(target))
if not target.with_name(target.stem + "_s1.wav").exists():
    raise SystemExit("Missing separated output")
