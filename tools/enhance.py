"""Run ClearVoice MossFormer2 speech enhancement in the separate local env.

Setup: UV_CACHE_DIR=work/uv-cache uv venv work/enhance-venv --python 3.12
       UV_CACHE_DIR=work/uv-cache uv pip install --python work/enhance-venv/bin/python clearvoice==0.1.2
Run:   work/enhance-venv/bin/python tools/enhance.py [sample|full]
"""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
os.environ.setdefault("HF_HOME", str(WORK / "hf-home"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORK / "cache"))
os.chdir(WORK)  # ClearVoice's checkpoint path is relative to the cwd.

from clearvoice import ClearVoice  # noqa: E402


def main() -> None:
    sample = len(sys.argv) > 1 and sys.argv[1] == "sample"
    source = WORK / ("audio-samples/original.wav" if sample else "audio-original.wav")
    target = WORK / ("audio-samples/enhanced.wav" if sample else "audio-enhanced.wav")
    if not source.exists():
        raise SystemExit(f"Missing {source}")
    model = ClearVoice(task="speech_enhancement", model_names=["MossFormer2_SE_48K"])
    checkpoint_marker = WORK / "checkpoints/MossFormer2_SE_48K/last_best_checkpoint"
    if not checkpoint_marker.exists():
        raise SystemExit(f"Model weights unavailable: {checkpoint_marker}")
    result = model(str(source), online_write=False)
    model.write(result, output_path=str(target))
    if not target.exists():
        raise SystemExit(f"ClearVoice did not write {target}")
    print(target)


if __name__ == "__main__":
    main()
