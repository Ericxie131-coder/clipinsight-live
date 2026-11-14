import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.deps'), str(ROOT / 'backend')]
import ollama_provider


class OllamaTests(unittest.TestCase):
    def test_json_generation_uses_nonstreaming_local_model(self):
        with patch.object(ollama_provider, 'request', return_value={'message': {'content': '{"summary":"ok"}'}}) as call:
            text = ollama_provider.generate([{'role': 'system', 'content': 'Only JSON'}, {'role':'user','content':'evidence'}], 100)
        self.assertEqual(text, '{"summary":"ok"}')
        self.assertEqual(call.call_args.args[0], '/api/chat')
        self.assertEqual(call.call_args.args[1]['format'], 'json')
        self.assertFalse(call.call_args.args[1]['stream'])

    def test_embedding_ranks_source_without_losing_kind(self):
        rows = [{'text': 'speech', 'kind': 'speech'}, {'text': 'board', 'kind': 'visual'}]
        with patch.object(ollama_provider, 'request', side_effect=[{'embeddings': [[0, 1], [1, 0]]}, {'embeddings': [[1, 0]]}]):
            evidence = ollama_provider.retrieve(rows, 'board question')
        self.assertEqual(evidence[0]['kind'], 'visual')
        self.assertAlmostEqual(evidence[0]['similarity'], 1.)
