"""Small, inspectable Euclid I.12 video pipeline.

All time values in intermediate JSON are seconds. ``original_to_edited`` is the
single conversion used for subtitles and diagnostics after the source gap cut.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUTPUT = ROOT / "output"
os.environ.setdefault("HF_HOME", str(WORK / "hf-home"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORK / "cache"))


def run(*args: str) -> None:
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True)


def read_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def original_to_edited(t: float, cfg: dict) -> float | None:
    """Remove [start,end): return None within the deleted interval."""
    start, end = cfg["remove"]["start"], cfg["remove"]["end"]
    if start is None or end is None or not 0 <= start < end:
        raise ValueError("Set valid remove.start and remove.end in config.json")
    if t < start:
        return t
    if t < end:
        return None
    return t - (end - start)


def inspect(source: Path) -> dict:
    WORK.mkdir(exist_ok=True)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
        check=True, capture_output=True, text=True,
    )
    probe = json.loads(result.stdout)
    write_json(WORK / "source-probe.json", probe)
    return probe


def extract(source: Path, cfg: dict) -> None:
    WORK.mkdir(exist_ok=True)
    if not (WORK / "audio-original.wav").exists():
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source,
            "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-c:a", "pcm_f32le", WORK / "audio-original.wav")
    for variant in ("original", "enhanced"):
        audio = WORK / f"audio-{variant}.wav"
        greek = WORK / f"audio-greek-{variant}-16k.wav"
        if audio.exists() and not greek.exists():
            run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", cfg["greek_start_original"],
                "-i", audio, "-ac", "1", "-ar", "16000", "-c:a", "pcm_f32le", greek)


def normalize_greek(text: str) -> str:
    """Map polytonic spelling to this Modern Greek CTC model's uppercase set.

    Breathings and iota subscripts have no model tokens. Acute, grave and
    circumflex all map to the model's single tonos vowel. The display text is
    never changed by this normalization.
    """
    nfd = unicodedata.normalize("NFD", text)
    chars: list[str] = []
    accent_pending = False
    accented = {"Α": "Ά", "Ε": "Έ", "Η": "Ή", "Ι": "Ί", "Ο": "Ό", "Υ": "Ύ", "Ω": "Ώ"}
    i = 0
    while i < len(nfd):
        ch = nfd[i]
        if "GREEK" in unicodedata.name(ch, "") and unicodedata.category(ch) in ("Ll", "Lu", "Lt"):
            j = i + 1
            marks = []
            while j < len(nfd) and unicodedata.category(nfd[j]).startswith("M"):
                marks.append(nfd[j])
                j += 1
            upper = ch.upper()
            stress = accent_pending or any(m in ("\u0300", "\u0301", "\u0342") for m in marks)
            diaeresis = "\u0308" in marks
            chars.append(accented.get(upper, upper) if stress else ("Ϊ" if diaeresis and upper == "Ι" else "Ϋ" if diaeresis and upper == "Υ" else upper))
            accent_pending = False
            i = j
            continue
        if ch in ("\u0300", "\u0301", "\u0342") and not chars:
            accent_pending = True
        i += 1
    return "".join(chars)


def _ctc_viterbi(logp, tokens: list[int], blank_id: int):
    """Return one optimal CTC state per frame (expanded blank/token trellis)."""
    import numpy as np

    t_count, _ = logp.shape
    if not tokens or t_count == 0:
        raise ValueError("CTC alignment needs audio frames and transcript tokens")
    states = np.full(2 * len(tokens) + 1, blank_id, dtype=np.int32)
    states[1::2] = tokens
    n = len(states)
    prev = np.full(n, -np.inf, dtype=np.float32)
    prev[0] = 0
    back = np.zeros((t_count, n), dtype=np.uint8)
    can_skip = np.zeros(n, dtype=bool)
    can_skip[3::2] = states[3::2] != states[1:-2:2]
    for t in range(t_count):
        stay = prev
        one = np.concatenate((np.full(1, -np.inf, dtype=np.float32), prev[:-1]))
        two = np.concatenate((np.full(2, -np.inf, dtype=np.float32), prev[:-2]))
        two[~can_skip] = -np.inf
        step = np.maximum.reduce((stay, one, two))
        back[t] = np.where(step == two, 2, np.where(step == one, 1, 0))
        prev = step + logp[t, states]
    end_state = n - 1 if prev[-1] > prev[-2] else n - 2
    if not np.isfinite(prev[end_state]):
        raise ValueError("No complete CTC path: insufficient frames or incompatible emissions")
    path = np.empty(t_count, dtype=np.int32)
    s = end_state
    for t in range(t_count - 1, -1, -1):
        path[t] = s
        s -= int(back[t, s])
    return path, states


def align(cfg: dict) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import AutoModelForCTC, AutoProcessor

    audio_variant = cfg.get("alignment_audio", "original")
    alignment_file = WORK / f"audio-greek-{audio_variant}-16k.wav"
    if not alignment_file.exists():
        raise RuntimeError(f"Missing {alignment_file}; run the configured audio enhancement first")
    audio, sr = sf.read(alignment_file, dtype="float32")
    assert sr == 16000 and audio.ndim == 1
    display_words = (ROOT / "transcript.txt").read_text(encoding="utf-8").split()
    processor = AutoProcessor.from_pretrained(cfg["alignment_model"])
    tokenizer = processor.tokenizer
    vocab = tokenizer.get_vocab()
    blank = tokenizer.pad_token_id
    delimiter = tokenizer.word_delimiter_token
    if blank is None:
        raise RuntimeError("Model tokenizer has no CTC blank/pad token")
    normalized = [normalize_greek(w) for w in display_words]
    unknown = sorted({c for word in normalized for c in word if c not in vocab})
    if unknown:
        raise RuntimeError(f"Greek model lacks these normalized characters: {unknown}; inspect tokenizer before alignment")
    tokens: list[int] = []
    token_word: list[int | None] = []
    for i, word in enumerate(normalized):
        for c in word:
            tokens.append(vocab[c])
            token_word.append(i)
        if i + 1 < len(normalized) and delimiter in vocab:
            tokens.append(vocab[delimiter])
            token_word.append(None)
    if not tokens:
        raise RuntimeError("No transcript tokens")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    previous = WORK / "alignment-raw.json"
    cache = WORK / "alignment-emissions.npz"
    can_reuse = (previous.exists() and cache.exists() and
                 all(json.loads(previous.read_text()).get(k) == v for k, v in
                     (("model", cfg["alignment_model"]), ("audio_variant", audio_variant))))
    if can_reuse:
        saved = np.load(cache)
        logp, times = saved["logp"], saved["times"]
        print(f"Reusing {len(times)} CTC emission frames for {audio_variant} audio", flush=True)
    else:
        model = AutoModelForCTC.from_pretrained(cfg["alignment_model"]).to(device).eval()
        print(f"Aligning {len(display_words)} words with {cfg['alignment_model']} on {device}", flush=True)
        # Context padding avoids cutting phonemes at chunk boundaries. Keep only
        # the central non-overlapping part of each chunk's emissions.
        hop_sec, context_sec = 14.0, 0.5
        emissions, frame_times = [], []
        duration = len(audio) / sr
        for start in np.arange(0, duration, hop_sec):
            stop = min(start + hop_sec, duration)
            left, right = max(0., start - context_sec), min(duration, stop + context_sec)
            sample = audio[round(left * sr):round(right * sr)]
            inputs = processor(sample, sampling_rate=sr, return_tensors="pt")
            with torch.inference_mode():
                logits = model(inputs.input_values.to(device)).logits[0].float().cpu()
            chunk = logits.log_softmax(dim=-1).numpy()
            chunk_times = left + np.arange(len(chunk)) * ((right - left) / len(chunk))
            keep = (chunk_times >= start) & (chunk_times < stop)
            emissions.append(chunk[keep])
            frame_times.append(chunk_times[keep])
            print(f"  {start:.1f}–{stop:.1f}s: {keep.sum()} frames", flush=True)
        logp = np.concatenate(emissions)
        times = np.concatenate(frame_times) + cfg["greek_start_original"]
        np.savez_compressed(cache, logp=logp, times=times)
    greedy = tokenizer.batch_decode([logp.argmax(axis=1).tolist()])[0]
    (WORK / "model-greedy.txt").write_text(greedy + "\n", encoding="utf-8")
    path, states = _ctc_viterbi(logp, tokens, blank)
    raw = {"model": cfg["alignment_model"], "audio_variant": audio_variant, "device": device, "sample_rate": sr,
           "greek_start_original": cfg["greek_start_original"], "tokenizer_delimiter": delimiter,
           "normalized_words": normalized, "token_ids": tokens,
           "frame_count": len(times), "frame_interval_approx": float(np.median(np.diff(times))),
           "viterbi_state_path": path.tolist()}
    write_json(WORK / "alignment-raw.json", raw)
    results = []
    for i, display in enumerate(display_words):
        positions = [j for j, owner in enumerate(token_word) if owner == i]
        mask = np.isin(path, [2 * j + 1 for j in positions])
        frames = np.flatnonzero(mask)
        if len(frames):
            scores = logp[frames, states[path[frames]]]
            start = float(times[frames[0]])
            end = float(times[frames[-1]] + np.median(np.diff(times)))
            confidence = float(np.exp(np.mean(scores)))
        else:
            start = end = confidence = None
        results.append({"index": i, "display": display, "alignment_text": normalized[i],
                        "start_original": start, "end_original": end, "confidence": confidence})
    write_json(WORK / "word-timings.json", results)


def validate_alignment(cfg: dict) -> tuple[list[dict], list[str]]:
    words = json.loads((WORK / "word-timings.json").read_text(encoding="utf-8"))
    original = (ROOT / "transcript.txt").read_text(encoding="utf-8").split()
    if [w["display"] for w in words] != original:
        raise RuntimeError("Aligned words do not match authoritative transcript")
    issues = []
    valid = [w for w in words if w["start_original"] is not None]
    if len(valid) / len(words) < .95:
        issues.append(f"Only {len(valid)}/{len(words)} words received timings")
    prior = None
    for w in valid:
        i, start, end = w["index"], w["start_original"], w["end_original"]
        if not start < end:
            issues.append(f"Word {i+1} {w['display']}: nonpositive duration")
        if prior is not None:
            gap = start - prior
            if gap < -.05:
                issues.append(f"Word {i+1}: nonmonotonic time ({gap:.2f}s)")
            if gap > 1.5:
                issues.append(f"Before word {i+1} {w['display']}: {gap:.2f}s gap")
        duration = end - start
        if duration < .055 or duration > 1.8:
            issues.append(f"Word {i+1} {w['display']}: duration {duration:.2f}s")
        if w["confidence"] is not None and w["confidence"] < .1:
            issues.append(f"Word {i+1} {w['display']}: low CTC path confidence {w['confidence']:.2f}")
        prior = end
    if valid and abs(valid[0]["start_original"] - cfg["greek_start_original"]) > 2:
        issues.append(f"First word starts at {valid[0]['start_original']:.2f}s, far from the 38s anchor")
    probe = json.loads((WORK / "source-probe.json").read_text(encoding="utf-8"))
    source_end = float(probe["format"]["duration"])
    if valid and source_end - valid[-1]["end_original"] > 8:
        issues.append(f"Last word ends {source_end - valid[-1]['end_original']:.2f}s before video end")
    write_json(WORK / "alignment-issues.json", issues)
    low = [w for w in valid if w["confidence"] < .1]
    abnormal = [w for w in valid if (w["end_original"]-w["start_original"] < .055 or
                                     w["end_original"]-w["start_original"] > 1.8)]
    report = ["# Alignment report", "", f"Model: `{cfg['alignment_model']}` on `{cfg.get('alignment_audio', 'original')}` audio.",
              f"Timed words: {len(valid)}/{len(words)} ({100*len(valid)/len(words):.1f}%).",
              f"Greek anchor: {cfg['greek_start_original']:.3f}s original → {original_to_edited(cfg['greek_start_original'], cfg):.3f}s edited.",
              f"First/last timed word: {valid[0]['start_original']:.2f}s / {valid[-1]['end_original']:.2f}s original." if valid else "No valid words.",
              "", "## Assessment", "",
              f"{len(low)} words have CTC path confidence below 0.10; {len(abnormal)} have a duration outside 0.055–1.8 seconds. Raw model timings are unsuitable for unattended display in the proof's middle section. Full word diagnostics are in `work/alignment-issues.json`.",
              ""]
    review_file = ROOT / "phrase-review.json"
    if review_file.exists():
        review = json.loads(review_file.read_text(encoding="utf-8"))
        report += ["## Independent phrase review", "", review["source"], "",
                   "Both local decoders suggest the latter part of phrase 15, phrases 16–17, and the opening two words of phrase 18 were skipped. This is a model-based inference, not a listening-confirmed transcription. The overlay omits those portions; every displayed Greek fragment is copied exactly from the authoritative text. The final phrase ends before the detected 'ευχαριστώ' at the end of the video.",
                   "", f"Reviewed overrides: {', '.join(review['overrides'])}."]
    report += ["", "## Remaining cautions", "",
               "The Modern Greek models do not reliably recognize Ancient Greek orthography or spoken geometrical labels. Repeated phrases were cross-checked by position, but individual word timings remain uncertain. CTC path confidence is a diagnostic, not a calibrated probability. Polytonic accents and punctuation were converted only for matching; `display` values are unchanged.", "",
               "Examples of automatic flags:"]
    report += [f"- {issue}" for issue in issues[:12]] if issues else ["- None."]
    if len(issues) > 12:
        report += [f"- …and {len(issues)-12} more in `work/alignment-issues.json`."]
    report += [""]
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "alignment-report.md").write_text("\n".join(report), encoding="utf-8")
    return words, issues


def phrase_timings(cfg: dict, words: list[dict]) -> list[dict]:
    phrases = (ROOT / "phrases.txt").read_text(encoding="utf-8").splitlines()
    flat = [word for phrase in phrases for word in phrase.split()]
    if flat != [w["display"] for w in words]:
        raise RuntimeError("Phrase words differ from authoritative transcript")
    output, offset = [], 0
    review_path = ROOT / "phrase-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))["overrides"] if review_path.exists() else {}
    for i, phrase in enumerate(phrases):
        group = words[offset:offset + len(phrase.split())]
        offset += len(group)
        if any(w["start_original"] is None for w in group):
            raise RuntimeError(f"Phrase {i+1} has unaligned words")
        model_start, model_end = group[0]["start_original"], group[-1]["end_original"]
        correction = review.get(str(i+1), {})
        display = correction.get("text", phrase)
        if display not in phrase:
            raise RuntimeError(f"Phrase {i+1} reviewed text is not an exact substring")
        spoken = correction.get("spoken", True)
        start = correction.get("start_original", model_start) if spoken else None
        end = correction.get("end_original", model_end) if spoken else None
        if spoken and not (cfg["greek_start_original"] <= start < end):
            raise RuntimeError(f"Phrase {i+1} has invalid reviewed timing")
        edited_start = original_to_edited(start, cfg) if spoken else None
        edited_end = original_to_edited(end, cfg) if spoken else None
        if spoken and (edited_start is None or edited_end is None):
            raise RuntimeError(f"Phrase {i+1} intersects removed gap")
        output.append({"index": i+1, "text": phrase, "display_text": display, "spoken": spoken,
                       "model_start_original": model_start, "model_end_original": model_end,
                       "start_original": start, "end_original": end,
                       "start_edited": edited_start, "end_edited": edited_end,
                       "min_confidence": min(w["confidence"] for w in group)})
    spoken_phrases = [p for p in output if p["spoken"]]
    for prior, current in zip(spoken_phrases, spoken_phrases[1:]):
        if current["start_original"] < prior["end_original"]:
            raise RuntimeError(f"Reviewed phrases {prior['index']} and {current['index']} overlap")
    write_json(WORK / "phrase-timings.json", output)
    return output


def ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    return f"{centis // 360000}:{(centis // 6000) % 60:02d}:{(centis // 100) % 60:02d}.{centis % 100:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def generate_ass(cfg: dict, phrases: list[dict], width: int, height: int) -> None:
    # Active clause remains complete; a short preview of the next clause is
    # subdued beneath it. At 320px width this usually takes 2–4 lines.
    alpha = round((1 - cfg["panel_opacity"]) * 255)
    size = cfg["font_size"]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Active,{cfg['font']},{size},&H00FFFFFF,&H00FFFFFF,&H66000000,&H{alpha:02X}101010,1,0,0,0,100,100,0,0,3,2,0,2,12,12,{cfg['margin_bottom']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    visible = [p for p in phrases if p["spoken"]]
    for i, phrase in enumerate(visible):
        start = original_to_edited(cfg["greek_start_original"], cfg) if i == 0 else phrase["start_edited"]
        end = visible[i+1]["start_edited"] if i+1 < len(visible) else phrase["end_edited"]
        if end <= start:
            continue
        cue = ass_escape(phrase["display_text"])
        if i + 1 < len(visible):
            upcoming = " ".join(visible[i+1]["display_text"].split()[:4])
            cue += (r"\N{\fs" + str(max(14, size-3)) + r"\b0\c&HAAAAAA&}"
                    + ass_escape(upcoming))
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Active,,0,0,0,,{cue}\n")
    (WORK / "euclid-I-12.ass").write_text(header + "".join(events), encoding="utf-8")


def render(source: Path, cfg: dict, preview: bool = False) -> Path:
    start, end = cfg["remove"]["start"], cfg["remove"]["end"]
    probe = inspect(source)
    duration = float(probe["format"]["duration"])
    audio = WORK / cfg.get("render_audio", "audio-original.wav")
    if not audio.exists():
        raise RuntimeError(f"Configured render audio is missing: {audio}")
    target = OUTPUT / ("euclid-I-12-preview.mp4" if preview else "euclid-I-12-final.mp4")
    # The ASS cues use edited time. Concatenate first, then burn the overlay.
    # HLG HDR is tonemapped to BT.709 for slides and browser playback.
    ass = str(WORK / "euclid-I-12.ass").replace("'", "'\\''")
    vf = (f"[0:v]split=2[vpre][vpost];"
          f"[vpre]trim=0:{start},setpts=PTS-STARTPTS[v0];"
          f"[vpost]trim=start={end}:end={duration},setpts=PTS-STARTPTS[v1];"
          f"[v0][v1]concat=n=2:v=1:a=0,"
          f"zscale=transfer=linear:npl=100,format=gbrpf32le,"
          f"tonemap=tonemap=hable:desat=0,"
          f"zscale=primaries=bt709:transfer=bt709:matrix=bt709:range=limited,"
          f"format=yuv420p,ass='{ass}'[v];"
          f"[1:a]asplit=2[apre][apost];"
          f"[apre]atrim=0:{start},asetpts=PTS-STARTPTS[a0];"
          f"[apost]atrim=start={end}:end={duration},asetpts=PTS-STARTPTS[a1];"
          f"[a0][a1]concat=n=2:v=0:a=1[a]")
    run("ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", source, "-i", audio,
        "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
        "-preset", "veryfast" if preview else "medium", "-crf", "23" if preview else "18",
        "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-colorspace", "bt709", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", target)
    return target


def qc(path: Path, cfg: dict) -> None:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    streams = {s["codec_type"]: s for s in data["streams"] if s["codec_type"] in ("video", "audio")}
    source = json.loads((WORK / "source-probe.json").read_text(encoding="utf-8"))
    expected = float(source["format"]["duration"]) - (cfg["remove"]["end"] - cfg["remove"]["start"])
    actual = float(data["format"]["duration"])
    assert abs(actual - expected) < .15, (actual, expected)
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    source_video = next(s for s in source["streams"] if s["codec_type"] == "video")
    assert (streams["video"]["width"], streams["video"]["height"]) == (source_video["width"], source_video["height"])
    assert abs(float(streams["audio"]["duration"]) - float(streams["video"]["duration"])) < .15
    ass = (WORK / "euclid-I-12.ass").read_text(encoding="utf-8")
    cues = re.findall(r"(?m)^Dialogue: 0,([^,]+),([^,]+),Active,", ass)
    assert cues, "No Greek cues"
    def parse_ass_time(value: str) -> float:
        h, m, sec = value.split(":")
        return int(h)*3600 + int(m)*60 + float(sec)
    first_cue = parse_ass_time(cues[0][0])
    last_cue = parse_ass_time(cues[-1][1])
    anchor_edited = original_to_edited(cfg["greek_start_original"], cfg)
    assert abs(first_cue - anchor_edited) < .02
    assert all(parse_ass_time(a) >= anchor_edited - .02 for a, _ in cues)
    phrases = json.loads((WORK / "phrase-timings.json").read_text(encoding="utf-8"))
    final_phrase = next(p for p in reversed(phrases) if p["spoken"])
    assert abs(last_cue - final_phrase["end_edited"]) < .03
    packets = subprocess.run(["ffprobe", "-v", "error", "-show_packets", "-show_entries",
                              "packet=stream_index,dts_time", "-of", "json", str(path)],
                             capture_output=True, text=True, check=True)
    prior_dts: dict[int, float] = {}
    for packet in json.loads(packets.stdout)["packets"]:
        if "dts_time" not in packet:
            continue
        stream = packet["stream_index"]
        dts = float(packet["dts_time"])
        assert dts >= prior_dts.get(stream, float("-inf")) - 1e-6, (stream, dts)
        prior_dts[stream] = dts
    write_json(OUTPUT / "qc" / (path.stem + "-probe.json"), data)
    # Four frames make placement and glyph coverage easy to review.
    for name, t in (("english", 8), ("early-greek", 18), ("middle-greek", 65),
                    ("final-greek", (final_phrase["start_edited"]+final_phrase["end_edited"])/2),
                    ("outro", min(expected-.5, last_cue+1))):
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", t, "-i", path,
            "-frames:v", "1", OUTPUT / "qc" / f"{path.stem}-{name}.png")
    print(f"QC passed: {actual:.3f}s, H.264/AAC, {streams['video']['width']}x{streams['video']['height']}; "
          f"Greek overlay {first_cue:.2f}–{last_cue:.2f}s edited; packet DTS monotonic")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "extract", "align", "prepare", "preview", "build", "qc"])
    parser.add_argument("source", nargs="?", default="input/IMG_1100.mov", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    cfg = read_config()
    if args.command == "inspect":
        inspect(source)
    elif args.command == "extract":
        extract(source, cfg)
    elif args.command == "align":
        extract(source, cfg)
        align(cfg)
        validate_alignment(cfg)
    elif args.command == "prepare":
        probe = inspect(source)
        words, issues = validate_alignment(cfg)
        if len(issues) > 30 and not (ROOT / "phrase-review.json").exists():
            raise RuntimeError(f"Alignment has {len(issues)} questionable regions; review report before rendering")
        phrases = phrase_timings(cfg, words)
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        generate_ass(cfg, phrases, video["width"], video["height"])
    elif args.command in ("preview", "build"):
        extract(source, cfg)
        raw = WORK / "alignment-raw.json"
        mismatch = (not raw.exists() or
                    json.loads(raw.read_text()).get("audio_variant") != cfg.get("alignment_audio", "original") or
                    json.loads(raw.read_text()).get("model") != cfg["alignment_model"])
        if mismatch or not (WORK / "word-timings.json").exists():
            align(cfg)
        words, issues = validate_alignment(cfg)
        if len(issues) > 30 and not (ROOT / "phrase-review.json").exists():
            raise RuntimeError(f"Alignment has {len(issues)} questionable regions; review report before rendering")
        probe = inspect(source)
        phrases = phrase_timings(cfg, words)
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        generate_ass(cfg, phrases, video["width"], video["height"])
        target = render(source, cfg, preview=args.command == "preview")
        qc(target, cfg)
    elif args.command == "qc":
        qc(OUTPUT / "euclid-I-12-final.mp4", cfg)


if __name__ == "__main__":
    main()
