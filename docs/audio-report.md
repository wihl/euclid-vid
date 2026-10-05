# Audio selection

Selected: ClearVoice 0.1.2 `MossFormer2_SS_16K`, first separated channel.
The model works on the recorded waveform. Its 16 kHz result was high-pass
filtered at 70 Hz, raised 6 dB and resampled to 48 kHz for the final AAC mix.
The original 48 kHz extraction, 48 kHz MossFormer2 enhancement result, and both
separated channels remain in `work/` for comparison.

On a 20-second Greek sample, a local Whisper small diagnostic recognized
`ευθεία άπειρος` from the first separated channel, versus `ευφία απηρός` from
the original. It found no Greek speech in the second channel. The 48 kHz
enhancement output offered only modest change: its RMS fell 1.8 dB during
40–60 s of speech, and its Greek alignment scores did not improve overall.

Five independent full-recording spot checks (English introduction, early
Greek, middle Greek, proof and ending) detected the speaker in channel one.
Channel two contained little coherent target speech, with some leakage. In 70 of 71
two-second windows, channel one was more correlated with the original mix than
channel two. The selected waveform is 145.876 s long, with a peak of 0.874
before AAC encoding; no sample clipping was detected.

The separation model can introduce artifacts and its 16 kHz output cannot
restore frequencies above 8 kHz. The tests establish the speaker channel and
improved speech recognition on this sample; listening on the intended
presentation speakers remains the best subjective quality check. No
listening-based quality rating was performed in this run.

Source: [ClearVoice](https://github.com/modelscope/ClearerVoice-Studio),
[MossFormer2 separation checkpoint](https://huggingface.co/alibabasglab/MossFormer2_SS_16K).
