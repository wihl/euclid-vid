# Euclid I.12 video

This project cuts the 14.000–38.000 s gap from `input/IMG_1100.mov`, keeps the
English introduction, and burns phrase-level polytonic Greek subtitles into a
Slides-compatible H.264/AAC MP4. The source MOV is never modified.

## Run

On Apple Silicon with FFmpeg installed (`brew install ffmpeg` if needed):

```bash
UV_CACHE_DIR=work/uv-cache uv sync --python 3.12
UV_CACHE_DIR=work/uv-cache uv run euclid-video inspect input/IMG_1100.mov
UV_CACHE_DIR=work/uv-cache uv run euclid-video extract input/IMG_1100.mov
```

The chosen audio file is named in `config.json` as `render_audio`. To recreate
the two locally processed alternatives, keep ClearVoice in its own project
environment:

```bash
UV_CACHE_DIR=work/uv-cache uv venv work/enhance-venv --python 3.12
UV_CACHE_DIR=work/uv-cache uv pip install --python work/enhance-venv/bin/python -r requirements-audio.lock
work/enhance-venv/bin/python tools/enhance.py full
ffmpeg -i work/audio-original.wav -ar 16000 -c:a pcm_f32le work/audio-original-16k.wav
work/enhance-venv/bin/python tools/separate.py full
```

The models download on first use and run locally after that. The ClearVoice
checkpoints stay in `work/checkpoints/`; model and package sources are
[ClearVoice](https://github.com/modelscope/ClearerVoice-Studio) and its
[48 kHz enhancement](https://huggingface.co/alibabasglab/MossFormer2_SE_48K)
and [16 kHz separation](https://huggingface.co/alibabasglab/MossFormer2_SS_16K)
weights. The enhancement does not synthesize or clone speech.

For this recording, the first separated channel was selected after a sample
comparison and full-recording checks. Recreate `work/audio-selected.wav` with:

```bash
ffmpeg -i work/audio-separated_s1.wav -af 'highpass=f=70,volume=6dB,aresample=48000:resampler=soxr' -ar 48000 -c:a pcm_f32le work/audio-selected.wav
```

See `docs/audio-report.md` for the empirical comparison.

After the configured audio file exists:

```bash
UV_CACHE_DIR=work/uv-cache uv run euclid-video align input/IMG_1100.mov
UV_CACHE_DIR=work/uv-cache uv run euclid-video prepare input/IMG_1100.mov
UV_CACHE_DIR=work/uv-cache uv run euclid-video preview input/IMG_1100.mov
UV_CACHE_DIR=work/uv-cache uv run euclid-video build input/IMG_1100.mov
```

`build` also runs alignment and subtitle preparation when needed. The lockfile
pins the main Python dependencies; `requirements-audio.lock` records the
separate audio environment, including its older NumPy version. For a fully
fresh rebuild, regenerate the selected audio before `build`.

## Timing and text

Edit `config.json` for the original-timeline Greek anchor and gap. The sole
conversion is `original_to_edited(t)`: before the gap, `t` is unchanged; in
the removed interval there is no edited timestamp; after it, subtract the gap
duration. The 38.000 s Greek anchor therefore becomes 14.000 s in the result.

`transcript.txt` is the authoritative text copied exactly from `starter.md`.
`phrases.txt` contains its 24 clause units. `tools/extract_text.py` reproduces
both files from the starter document. The alignment model uses a separate
uppercase monotonic representation; it never supplies displayed spelling.

The Greek CTC aligner uses the
[wav2vec2 Greek model](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-greek)
in 14-second chunks. It saves raw diagnostics, word timings and a report.
`phrase-review.json` records the independent check against local Whisper
timestamps. Both local recognizers suggest omissions in this recording;
`phrase-review.json` records that model-based inference and the associated
overlay changes. These omissions have not been confirmed by listening.
The complete supplied text remains in `transcript.txt` and is also delivered
in `output/euclid-I-12-transcript.txt`.

Subtitles use the installed Palatino Linotype font, whose glyph map covers
every character in the supplied Greek. This project does not redistribute the
font. The source is a 320×568 HDR portrait recording; FFmpeg tone maps it to
BT.709 and retains its dimensions. `work/euclid-I-12.ass` contains the overlay.
The source probe (`work/source-probe.json`) records 145.870 s, 320×568,
approximately 30 fps HEVC Main 10 video, 48 kHz stereo AAC audio, Dolby
Vision/HLG metadata and no rotation tag.

## Outputs

- `output/euclid-I-12-preview.mp4` — fast encode for inspection.
- `output/euclid-I-12-final.mp4` — H.264/AAC `yuv420p`, fast-start MP4.
- `output/alignment-report.md` — confidence and timing caveats.
- `output/qc-report.md` — completed verification and remaining limitations.
- `output/qc/` — stream probes and representative decoded frames.

All extracted audio, model weights and machine-generated timing files are in
gitignored `work/`; output media is gitignored under `output/`. The final
build probes its streams, checks duration and timestamp monotonicity, and
decodes QC frames.

The source, selected audio, ASS file and MP4 checksums are recorded in
`output/qc/verification.json`; `models.lock.json` records downloaded model
revisions. To check the existing artifacts without rerunning the models:

```bash
UV_CACHE_DIR=work/uv-cache uv run --offline python -m unittest discover -s tests -v
UV_CACHE_DIR=work/uv-cache uv run --offline python tools/final_qc.py
```

The tests include an exhaustive check of the CTC algorithm on small synthetic
examples, timestamp cut boundaries, exact source text, and reproduction of the
saved subtitles. Model comparisons and timing exceptions are specific to this
source clip; using a different recording requires a fresh phrase review.
