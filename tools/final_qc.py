"""Verify saved media and intermediates without rerunning any model or render."""

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK, OUTPUT = ROOT / "work", ROOT / "output"
cfg = json.loads((ROOT / "config.json").read_text())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audio(path):
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                             "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4")


def lag_and_correlation(observed, reference):
    observed, reference = observed.astype(float), reference.astype(float)
    observed -= observed.mean()
    reference -= reference.mean()
    nfft = 1 << (2*len(observed)-1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(observed, nfft) * np.conj(np.fft.rfft(reference, nfft)), nfft)
    lags = np.arange(-1600, 1601)
    values = corr[lags % nfft] / (np.linalg.norm(observed)*np.linalg.norm(reference))
    best = int(np.argmax(values))
    return {"lag_ms": float(lags[best]/16), "correlation": float(values[best])}


selected = audio(WORK / cfg["render_audio"])
original = audio(WORK / "audio-original.wav")
cut_start, cut_end = (round(cfg["remove"][k]*16000) for k in ("start", "end"))
expected = np.concatenate((selected[:cut_start], selected[cut_end:]))
words = json.loads((WORK / "word-timings.json").read_text())
transcript = (ROOT / "transcript.txt").read_text()
assert [w["display"] for w in words] == transcript.split()
phrases = json.loads((WORK / "phrase-timings.json").read_text())
visible = [p for p in phrases if p["spoken"]]
ass = (WORK / "euclid-I-12.ass").read_text()
events = [line.split(",", 9) for line in ass.splitlines() if line.startswith("Dialogue:")]
assert [event[9].split(r"\N")[0] for event in events] == [p["display_text"] for p in visible]
assert all(p["display_text"] in p["text"] for p in visible)

fonts = []
for style in ("Regular", "Bold"):
    path = subprocess.check_output(["fc-match", "-f", "%{file}", f"{cfg['font']}:style={style}"], text=True)
    charset = subprocess.check_output(["fc-query", "--format", "%{charset}\n", path], text=True).splitlines()[0]
    covered = set()
    for token in charset.split():
        ends = token.split("-")
        covered.update(range(int(ends[0], 16), int(ends[-1], 16)+1))
    missing = [c for c in set(transcript) if not c.isspace() and ord(c) not in covered]
    assert not missing, (path, missing)
    fonts.append({"style": style, "path": path, "missing_glyphs": []})

result = {"cut_original": cfg["remove"], "greek_start_edited": 14.0,
          "last_greek_end_edited": visible[-1]["end_edited"],
          "authoritative_words": len(words), "visible_phrases": len(visible),
          "omitted_phrase_indices": [p["index"] for p in phrases if not p["spoken"]],
          "font_coverage": fonts, "media": [], "separation_timing": []}
for start in (3, 42, 85, 109, 137):
    region = slice(start*16000, (start+1)*16000)
    timing = lag_and_correlation(selected[region], original[region])
    assert abs(timing["lag_ms"]) <= 30, timing
    result["separation_timing"].append({"start_original": start, **timing})

for name in ("euclid-I-12-preview.mp4", "euclid-I-12-final.mp4"):
    path = OUTPUT / name
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    actual = audio(path)
    timings = []
    for start in (3, 10, 16, 60, 118):
        region = slice(start*16000, (start+1)*16000)
        timing = lag_and_correlation(actual[region], expected[region])
        assert abs(timing["lag_ms"]) <= 2 and timing["correlation"] > .95, timing
        timings.append({"start_edited": start, **timing})
    atoms = []
    with path.open("rb") as stream:
        while stream.tell() < path.stat().st_size:
            start = stream.tell()
            size, kind = struct.unpack(">I4s", stream.read(8))
            if size == 1:
                size = struct.unpack(">Q", stream.read(8))[0]
            if size == 0:
                size = path.stat().st_size - start
            atoms.append(kind.decode("ascii"))
            stream.seek(start+size)
    assert atoms.index("moov") < atoms.index("mdat"), atoms
    result["media"].append({"file": name, "size_bytes": path.stat().st_size,
                            "sha256": digest(path), "full_decode": "passed",
                            "fast_start": True, "audio_timing": timings})

result["source_sha256"] = digest(ROOT / "input/IMG_1100.mov")
result["input_hashes"] = {str(p.relative_to(ROOT)): digest(p) for p in
                           [ROOT / "config.json", ROOT / "transcript.txt", ROOT / "phrase-review.json",
                            WORK / "euclid-I-12.ass", WORK / cfg["render_audio"]]}
(OUTPUT / "qc/verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
