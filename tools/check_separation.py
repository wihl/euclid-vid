"""Spot-check both separated channels with local Whisper small.

Whisper output is diagnostic and is never used as displayed Greek text.
Requires openai-whisper in the separate ClearVoice environment.
"""

import json
from pathlib import Path

import soundfile as sf
import whisper

root = Path(__file__).resolve().parents[1]
work = root / "work"
model = whisper.load_model("small", download_root=str(work / "whisper-models"), device="cpu")
windows = [("english", 1, 12, "en"), ("early", 38, 58, "el"),
           ("middle", 78, 98, "el"), ("proof", 103, 123, "el"),
           ("ending", 131, 145, "el")]
results = []
for label, start, end, language in windows:
    for channel in (1, 2):
        audio, sr = sf.read(work / f"audio-separated_s{channel}.wav", dtype="float32")
        assert sr == 16000
        clip = audio[round(start*sr):round(end*sr)]
        result = model.transcribe(clip, language=language, fp16=False,
                                  condition_on_previous_text=False, verbose=False)
        item = {"window": label, "start_original": start, "end_original": end,
                "channel": channel, "text": result["text"].strip(),
                "mean_no_speech_probability": (sum(s["no_speech_prob"] for s in result["segments"])/len(result["segments"])
                                               if result["segments"] else None)}
        results.append(item)
        print(item, flush=True)
(work / "separation-check.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
