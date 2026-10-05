import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import euclid_video as pipeline


def collapse(path):
    return [value for i, value in enumerate(path)
            if value != 0 and (i == 0 or value != path[i-1])]


class TimingTests(unittest.TestCase):
    def test_cut_boundaries(self):
        cfg = {"remove": {"start": 14.0, "end": 38.0}}
        self.assertEqual(pipeline.original_to_edited(13.999, cfg), 13.999)
        self.assertIsNone(pipeline.original_to_edited(14.0, cfg))
        self.assertIsNone(pipeline.original_to_edited(37.999, cfg))
        self.assertEqual(pipeline.original_to_edited(38.0, cfg), 14.0)
        self.assertAlmostEqual(pipeline.original_to_edited(145.87, cfg), 121.87)

    def test_invalid_cut_rejected(self):
        for start, end in [(None, None), (38, 14), (14, 14), (-1, 14)]:
            with self.assertRaises(ValueError):
                pipeline.original_to_edited(38, {"remove": {"start": start, "end": end}})

    def test_ctc_matches_exhaustive_search_including_repeated_tokens(self):
        rng = np.random.default_rng(81)
        for tokens in ([1, 2], [1, 1], [2, 1, 2]):
            for _ in range(4):
                probabilities = rng.dirichlet([1, 1, 1], size=5)
                logp = np.log(probabilities).astype(np.float32)
                possibilities = [seq for seq in itertools.product(range(3), repeat=5)
                                 if collapse(seq) == list(tokens)]
                best = max(sum(logp[t, token] for t, token in enumerate(seq))
                           for seq in possibilities)
                path, states = pipeline._ctc_viterbi(logp, list(tokens), 0)
                decoded = states[path].tolist()
                self.assertEqual(collapse(decoded), list(tokens))
                self.assertAlmostEqual(sum(logp[t, token] for t, token in enumerate(decoded)), best, places=5)

    def test_ctc_cannot_skip_first_token(self):
        with self.assertRaises(ValueError):
            pipeline._ctc_viterbi(np.log(np.array([[.01, .01, .98]], dtype=np.float32)), [1, 2], 0)


class ArtifactTests(unittest.TestCase):
    def test_authoritative_text_is_byte_exact(self):
        starter = (pipeline.ROOT / "starter.md").read_text(encoding="utf-8")
        supplied = starter.split("Use this exact text as the authoritative transcript:\n\n", 1)[1].split("\n\nStore this as UTF-8.", 1)[0] + "\n"
        self.assertEqual((pipeline.ROOT / "transcript.txt").read_bytes(), supplied.encode("utf-8"))
        self.assertEqual(supplied.split(), (pipeline.ROOT / "phrases.txt").read_text().split())

    def test_polytonic_normalization_for_model_vocabulary(self):
        self.assertEqual(pipeline.normalize_greek("῎Εστω"), "ΈΣΤΩ")
        self.assertEqual(pipeline.normalize_greek("δοθεῖσα"), "ΔΟΘΕΊΣΑ")
        self.assertEqual(pipeline.normalize_greek("ΓΘ·"), "ΓΘ")
        self.assertEqual(pipeline.normalize_greek("τῇ"), "ΤΉ")
        self.assertEqual(pipeline.normalize_greek("ἐπ᾿"), "ΕΠ")

    def test_reviewed_cues_reproduce_existing_render_input(self):
        words = json.loads((pipeline.WORK / "word-timings.json").read_text())
        expected = (pipeline.WORK / "euclid-I-12.ass").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(pipeline, "WORK", Path(directory)):
                phrases = pipeline.phrase_timings(pipeline.read_config(), words)
                self.assertEqual([p["index"] for p in phrases if not p["spoken"]], [16, 17])
                pipeline.generate_ass(pipeline.read_config(), phrases, 320, 568)
                self.assertEqual((Path(directory) / "euclid-I-12.ass").read_bytes(), expected)

    def test_corrected_ctc_initialization_preserves_recorded_alignment(self):
        raw = json.loads((pipeline.WORK / "alignment-raw.json").read_text())
        emissions = np.load(pipeline.WORK / "alignment-emissions.npz")["logp"]
        path, _ = pipeline._ctc_viterbi(emissions, raw["token_ids"], 0)
        np.testing.assert_array_equal(path, raw["viterbi_state_path"])


if __name__ == "__main__":
    unittest.main()
