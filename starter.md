# Project: Euclid I.12 synchronized Ancient Greek video

Build and run a small, reproducible macOS project that takes a short restaurant video containing:

1. a brief English introduction,
2. a gap that should be removed,
3. a reading of Euclid, *Elements* I.12 in Ancient Greek,

and produces a single polished MP4 suitable for embedding in Google Slides.

The final video should:

- retain the English introduction;
- remove a user-specified gap;
- substantially reduce restaurant/background noise while preserving the speaker's voice and Ancient Greek pronunciation;
- retain the original video;
- synchronize the supplied, authoritative Ancient Greek text to the spoken Greek;
- display the Greek text in a readable karaoke-style overlay, highlighting the phrase currently being spoken;
- preserve the original Greek text exactly rather than replacing it with speech-recognition output;
- encode the final result in a Google-Slides-friendly format.

This is a small project/spike. Prefer simple, inspectable tools and intermediate artifacts over application architecture or unnecessary abstractions.

## Environment

Target machine:

- Apple Silicon Mac, M5 generation
- current macOS
- Homebrew available
- `uv` preferred for Python dependency/environment management
- FFmpeg may be installed through Homebrew if needed
- no NVIDIA/CUDA
- Internet access is available for downloading packages/models

Do not modify the user's global Python environment.

Use an appropriate Python version supported by all required dependencies. Create a project-local `uv` environment.

The source video will be copied into the project as:

`input/IMG_1100.mov`

The source is approximately 2 minutes 26 seconds long.

Do not modify the original source file.

## Known timing

The Ancient Greek reading begins in the original video at:

`00:38.000`

The user will provide the exact start and end timestamps of the unwanted gap separately.

Put these values in a human-editable configuration file rather than hardcoding them throughout the implementation.

For example:

```yaml
greek_start_original: 38.000

remove:
  start: USER_SUPPLIED
  end: USER_SUPPLIED
```

Be careful about the distinction between:

- timestamps in the original video;
- timestamps after the gap has been removed;
- timestamps in extracted Greek-only audio.

Implement timestamp conversion explicitly so that removing the gap cannot silently shift the Greek synchronization.

## Authoritative Ancient Greek text

This is Euclid I.12.

Use this exact text as the authoritative transcript:

῎Εστω ἡ μὲν δοθεῖσα εὐθεῖα ἄπειρος ἡ ΑΒ τὸ δὲ δοθὲν σημεῖον, ὃ μή ἐστιν ἐπ᾿ αὐτῆς, τὸ Γ· δεῖ δὴ ἐπὶ
τὴν δοθεῖσαν εὐθεῖαν ἄπειρον τὴν ΑΒ ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς, κάθετον
εὐθεῖαν γραμμὴν ἀγαγεῖν. Εἰλήφθω γὰρ ἐπὶ τὰ ἕτερα μέρη τῆς ΑΒ εὐθείας τυχὸν σημεῖον τὸ Δ, καὶ
κέντρῳ μὲν τῷ Γ διαστήματι δὲ τῷ ΓΔ κύκλος γεγράφθω ὁ ΕΖΗ, καὶ τετμήσθω ἡ ΕΗ εὐθεῖα δίχα κατὰ
τὸ Θ, καὶ ἐπεζεύχθωσαν αἱ ΓΗ, ΓΘ, ΓΕ εὐθεῖαι· λέγω, ὅτι ἐπὶ τὴν δοθεῖσαν εὐθεῖαν ἄπειρον τὴν ΑΒ
ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς, κάθετος ἦκται ἡ ΓΘ. ᾿Επεὶ γὰρ ἴση ἐστὶν ἡ ΗΘ
τῇ ΘΕ, κοινὴ δὲ ἡ ΘΓ, δύο δὴ αἱ ΗΘ, ΘΓ δύο ταῖς ΕΘ, ΘΓ ἴσαι εἱσὶν ἑκατέρα ἑκατέρᾳ· καὶ βάσις ἡ ΓΗ
βάσει τῇ ΓΕ ἐστιν ἴση· γωνία ἄρα ἡ ὑπὸ ΓΘΗ γωνίᾳ τῇ ὑπὸ ΕΘΓ ἐστιν ἴση. καί εἰσιν ἐφεξῆς. ὅταν δὲ
εὐθεῖα ἐπ᾿ εὐθεῖαν σταθεῖσα τὰς ἐφεξῆς γωνίας ἴσας ἀλλήλαις ποιῇ, ὀρθὴ ἑκατέρα τῶν ἴσων γωνιῶν
ἐστιν, καὶ ἡ ἐφεστηκυῖα εὐθεῖα κάθετος καλεῖται ἐφ᾿ ἣν ἐφέστηκεν. ᾿Επὶ τὴν δοθεῖσαν ἄρα εὐθεῖαν
ἄπειρον τὴν ΑΒ ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς, κάθετος ἦκται ἡ ΓΘ· ὅπερ ἔδει
ποιῆσαι.

Store this as UTF-8.

### Critical text requirement

Do **not** use ASR output as the displayed transcript.

The supplied text is authoritative.

Speech recognition/alignment exists only to determine *when* the known words are spoken.

Preserve:

- polytonic Greek;
- accents;
- breathings;
- punctuation;
- elision/apostrophe characters;
- Greek geometrical labels such as ΑΒ, Γ, Δ, ΕΖΗ, etc.

Be aware that Unicode normalization and tokenizer normalization may differ between the authoritative text and an alignment model. Any normalized representation used internally for alignment must remain separate from the original display text.

## Overall pipeline

Implement approximately:

```text
source MOV
   |
   +--> inspect source
   |
   +--> extract audio
   |
   +--> speech enhancement / foreground voice isolation
   |
   +--> alignment experiment
   |       known Greek text
   |             |
   |             +--> word timings
   |
   +--> phrase grouping
   |
   +--> ASS subtitle generation
   |
   +--> remove specified video gap
   |
   +--> combine edited video
   |       + enhanced audio
   |       + synchronized Greek overlay
   |
   +--> final MP4
```

Intermediate artifacts should go under `work/` and be gitignored.

Final deliverables should go under `output/`.

## Phase 1 — inspect the source

Before implementing assumptions, inspect the source with `ffprobe`.

Record:

- duration;
- dimensions;
- frame rate;
- video codec;
- audio codec;
- audio sample rate;
- channel layout;
- rotation/orientation metadata if present.

Save useful machine-readable metadata under `work/`.

Confirm that the 38-second Greek-start anchor is plausible.

## Phase 2 — audio enhancement

The recording was made in a restaurant.

The principal problem is not stationary hiss. It may contain:

- other people's voices;
- dishes and impacts;
- restaurant ambience;
- reverberation;
- possibly music.

Therefore generic spectral noise reduction alone is unlikely to be sufficient.

Investigate a practical local AI speech-enhancement / voice-isolation solution that runs on Apple Silicon.

Requirements:

- no CUDA dependency;
- local processing after model download;
- preserve intelligibility and pronunciation;
- do not assume English;
- Ancient Greek phonetics must not be deliberately normalized or regenerated;
- avoid voice cloning or speech resynthesis.

Prefer separation/enhancement of the actual recorded waveform.

Keep:

`work/audio-original.wav`

and produce something such as:

`work/audio-enhanced.wav`

Do not overwrite the original.

If more than one reasonable local model/tool is readily available, make a short empirical comparison rather than spending hours benchmarking models.

The objective is intelligibility, not studio-quality audio.

Produce short comparison samples if useful:

`work/audio-samples/original.wav`

`work/audio-samples/enhanced.wav`

Document exactly which enhancement model/tool was selected and why.

If local AI enhancement proves clearly ineffective, retain the original audio and report that result rather than damaging the speech.

## Phase 3 — forced alignment

This is the most experimental part of the project.

The exact transcript is already known.

We need **forced alignment**, not transcription.

Start from the known fact that the Greek begins at 38.000 seconds in the original video.

Investigate WhisperX and its Greek wav2vec2 alignment support, or another suitable CTC forced-alignment approach.

Do not assume that a model trained on Modern Greek will perfectly align Ancient Greek.

Test it.

The first alignment attempt should produce word-level timings and confidence information where available.

Save the raw result, for example:

`work/alignment-raw.json`

and a normalized useful representation:

`work/word-timings.json`

Each useful word timing should include approximately:

```json
{
  "display": "δοθεῖσα",
  "start_original": 40.123,
  "end_original": 40.481,
  "confidence": 0.91
}
```

The `display` field must ultimately come from the authoritative transcript, not ASR spelling.

### Alignment validation

Do not blindly accept model output.

Implement sanity checks.

At minimum examine:

- percentage of transcript words receiving timings;
- monotonically increasing timestamps;
- implausibly long gaps;
- implausibly short/long words;
- low-confidence regions;
- alignment of the beginning;
- alignment of the end;
- treatment of ΑΒ/Γ/Δ/etc.;
- punctuation and Unicode normalization;
- whether repeated phrases have been mapped to the correct occurrence.

Produce a concise alignment report such as:

`output/alignment-report.md`

It should identify questionable regions.

If forced alignment is substantially successful, continue.

If it fails badly, stop the fully automatic path and leave enough diagnostics to determine why. Do not fabricate timings.

## Phase 4 — phrase segmentation

The display should operate at the **phrase/clause level**, not bounce word-by-word.

Start with these logical units, adjusting only if actual timing/readability strongly suggests a neighboring boundary is better:

1. ῎Εστω ἡ μὲν δοθεῖσα εὐθεῖα ἄπειρος ἡ ΑΒ
2. τὸ δὲ δοθὲν σημεῖον, ὃ μή ἐστιν ἐπ᾿ αὐτῆς, τὸ Γ·
3. δεῖ δὴ ἐπὶ τὴν δοθεῖσαν εὐθεῖαν ἄπειρον τὴν ΑΒ
4. ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς,
5. κάθετον εὐθεῖαν γραμμὴν ἀγαγεῖν.
6. Εἰλήφθω γὰρ ἐπὶ τὰ ἕτερα μέρη τῆς ΑΒ εὐθείας τυχὸν σημεῖον τὸ Δ,
7. καὶ κέντρῳ μὲν τῷ Γ διαστήματι δὲ τῷ ΓΔ κύκλος γεγράφθω ὁ ΕΖΗ,
8. καὶ τετμήσθω ἡ ΕΗ εὐθεῖα δίχα κατὰ τὸ Θ,
9. καὶ ἐπεζεύχθωσαν αἱ ΓΗ, ΓΘ, ΓΕ εὐθεῖαι·
10. λέγω, ὅτι ἐπὶ τὴν δοθεῖσαν εὐθεῖαν ἄπειρον τὴν ΑΒ
11. ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς,
12. κάθετος ἦκται ἡ ΓΘ.
13. ᾿Επεὶ γὰρ ἴση ἐστὶν ἡ ΗΘ τῇ ΘΕ, κοινὴ δὲ ἡ ΘΓ,
14. δύο δὴ αἱ ΗΘ, ΘΓ δύο ταῖς ΕΘ, ΘΓ ἴσαι εἱσὶν ἑκατέρα ἑκατέρᾳ·
15. καὶ βάσις ἡ ΓΗ βάσει τῇ ΓΕ ἐστιν ἴση·
16. γωνία ἄρα ἡ ὑπὸ ΓΘΗ γωνίᾳ τῇ ὑπὸ ΕΘΓ ἐστιν ἴση.
17. καί εἰσιν ἐφεξῆς.
18. ὅταν δὲ εὐθεῖα ἐπ᾿ εὐθεῖαν σταθεῖσα τὰς ἐφεξῆς γωνίας ἴσας ἀλλήλαις ποιῇ,
19. ὀρθὴ ἑκατέρα τῶν ἴσων γωνιῶν ἐστιν,
20. καὶ ἡ ἐφεστηκυῖα εὐθεῖα κάθετος καλεῖται ἐφ᾿ ἣν ἐφέστηκεν.
21. ᾿Επὶ τὴν δοθεῖσαν ἄρα εὐθεῖαν ἄπειρον τὴν ΑΒ
22. ἀπὸ τοῦ δοθέντος σημείου τοῦ Γ, ὃ μή ἐστιν ἐπ᾿ αὐτῆς,
23. κάθετος ἦκται ἡ ΓΘ·
24. ὅπερ ἔδει ποιῆσαι.

Derive phrase start/end times from aligned word timings.

Save:

`work/phrase-timings.json`

Include original-video and edited-video timestamps.

## Phase 5 — visual design

The finished video will be embedded in a Google Slides presentation and may be projected.

The speaker should remain visible.

Do not cover most of the video with text.

Create a readable lower-third/lower-panel treatment.

Preferred behavior:

- no Greek overlay during the English introduction;
- Greek overlay begins when the Greek reading begins;
- show approximately 2–3 lines of Greek at a time;
- current phrase is visually emphasized;
- surrounding nearby Greek remains visible but subdued;
- advance the text window as necessary;
- phrase transitions should be immediate or subtle, not flashy;
- no bouncing karaoke ball or decorative animation;
- optimize for legibility and comprehension.

Use a font with excellent polytonic Ancient Greek coverage.

Prefer an installed suitable font if available; otherwise use a freely redistributable font with strong polytonic Greek support and document it.

Do not silently substitute missing glyphs.

Generate ASS subtitles because they provide better typography, positioning and highlighting control than SRT.

Save:

`work/euclid-I-12.ass`

Make the style configurable where practical:

- font;
- font size;
- panel opacity;
- margins;
- active/inactive emphasis.

The source video is relatively low resolution, so design for its actual dimensions rather than assuming 1080p.

## Phase 6 — gap removal

The user will provide:

```text
GAP_START = ...
GAP_END   = ...
```

These refer to the **original source video's timeline** unless explicitly stated otherwise.

Remove exactly that interval.

Retain:

- the English introduction before it;
- the Greek reading after it.

Audio and video must remain synchronized.

All subtitle/alignment timestamps must be transformed correctly from original time to edited time.

Do not manually bake arbitrary offsets into multiple scripts.

Implement a single documented timestamp transformation.

## Phase 7 — final render

Use FFmpeg for deterministic cutting, audio replacement/muxing and final rendering.

Final output:

`output/euclid-I-12-final.mp4`

Target compatibility:

- Google Drive;
- Google Slides embedded video;
- H.264 video;
- AAC audio;
- broadly compatible MP4 pixel format such as `yuv420p`;
- preserve source dimensions unless there is a concrete reason to change them.

Do not upscale merely to claim 1080p.

Avoid unnecessary generations/re-encodes during intermediate processing.

## Preview output

Before considering the project complete, produce:

`output/euclid-I-12-preview.mp4`

This can use a faster encode if useful.

Actually open/probe/test the resulting media.

At minimum verify programmatically:

- playable MP4 container;
- expected duration after gap removal;
- audio stream present;
- video stream present;
- H.264/AAC final codecs;
- timestamps monotonically valid;
- Greek overlay begins at the correctly transformed equivalent of original 00:38;
- no overlay during English introduction;
- final phrase ends near the end of the Greek reading.

Where practical, extract representative frames showing:

1. English introduction with no overlay;
2. early Greek overlay;
3. middle Greek overlay;
4. final Greek overlay.

Put them under:

`output/qc/`

Inspect them for obvious clipping, missing glyphs or unreadable text.

## Project interface

Keep the user interface simple.

Ideal final invocation:

```bash
uv run euclid-video build input/IMG_1100.mov
```

or, if a Python module is simpler:

```bash
uv run python -m euclid_video build input/IMG
