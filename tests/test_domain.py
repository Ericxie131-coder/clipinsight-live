import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from domain import Session, seconds


class TranscriptContractTests(unittest.TestCase):
    def test_replayed_snapshots_do_not_duplicate_transcript(self):
        s = Session()
        payload = {"lines": [{"start": "0:00:01.20", "end": "0:00:03.00", "speaker": 1, "text": "Hello"}], "buffer_transcription": "world"}
        self.assertTrue(s.merge(payload))
        self.assertFalse(s.merge(payload))
        self.assertEqual(len(s.rows()), 1)
        self.assertEqual(s.revision, 1)
        self.assertNotIn("world", s.markdown())

    def test_revision_replaces_same_timestamp_and_ignores_loading_speaker(self):
        s = Session()
        s.merge({"lines": [{"start": 1, "end": 2, "speaker": 1, "text": "hello"}]})
        s.merge({"lines": [{"start": 1, "end": 3, "speaker": 1, "text": "hello world"}, {"start": 4, "end": 5, "speaker": 0, "text": "not ready"}]})
        self.assertEqual([x["text"] for x in s.rows()], ["hello world"])

    def test_sessions_remain_isolated(self):
        a,b=Session(),Session()
        a.merge({"lines": [{"start": 0, "end": 1, "speaker": 1, "text": "private A"}]})
        self.assertNotEqual(a.id,b.id)
        self.assertNotIn("private A",b.markdown())

    def test_invalid_times_rejected(self):
        for value in [float("nan"), float("inf"), -1]:
            with self.assertRaises(ValueError): seconds(value)
        with self.assertRaises(ValueError):
            Session().merge({"lines": [{"start": 2, "end": 1, "speaker": 1, "text": "bad"}]})

if __name__=='__main__':unittest.main()
