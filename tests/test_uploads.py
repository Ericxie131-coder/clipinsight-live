import asyncio
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.deps'), str(ROOT / 'backend')]
from uploads import decode_audio, process_upload
from domain import Session


def audio_fixture(path):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 3200)


class DecodeTests(unittest.TestCase):
    def test_pcm_conversion_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            audio_fixture(p / 'source')
            duration = decode_audio(p / 'source', p / 'out.wav')
            self.assertAlmostEqual(duration, .2, places=2)
            with wave.open(str(p / 'out.wav')) as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (16000, 1, 2))

    def test_video_without_audio_has_actionable_error(self):
        import av
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with av.open(str(p / 'silent.mp4'), 'w') as output:
                stream = output.add_stream('mpeg4', rate=1)
                stream.width = stream.height = 32
                frame = av.VideoFrame.from_ndarray(np.zeros((32, 32, 3), dtype=np.uint8), format='rgb24')
                for packet in stream.encode(frame): output.mux(packet)
                for packet in stream.encode(): output.mux(packet)
            with self.assertRaisesRegex(ValueError, '没有音轨'):
                decode_audio(p / 'silent.mp4', p / 'out.wav')

    def test_corrupt_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'source').write_bytes(b'not a video')
            with self.assertRaisesRegex(ValueError, '无法读取'):
                decode_audio(p / 'source', p / 'out.wav')


class UploadLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_finalization_and_temporary_file_cleanup(self):
        directory = Path(tempfile.mkdtemp())
        audio_fixture(directory / 'source')
        s = Session(source='upload')
        def transcribe(audio, **kwargs):
            import numpy as np
            self.assertIsInstance(audio, np.ndarray)
            self.assertEqual(audio.dtype, np.float32)
            self.assertEqual(audio.shape, (3200,))
            return iter([SimpleNamespace(start=0, end=.2, text='confirmed speech')]), None
        model = SimpleNamespace(transcribe=transcribe)
        async def ensure(language):
            return SimpleNamespace(asr=SimpleNamespace(backend_choice='faster-whisper', model=model))
        async def summarize(session, force):
            session.summary_status = 'ready'
            session.summary_revision = session.revision
        await process_upload(s, directory, ensure, lambda x: not x.cancelled, summarize)
        self.assertEqual(s.status, 'completed')
        self.assertEqual(s.progress['stage'], 'done')
        self.assertEqual(s.rows()[0]['text'], 'confirmed speech')
        self.assertFalse(directory.exists())

    async def test_deleted_job_cleans_up_without_loading_model(self):
        directory = Path(tempfile.mkdtemp())
        audio_fixture(directory / 'source')
        s = Session(source='upload', cancelled=True)
        async def not_called(*args):
            self.fail('deleted job must not load a model')
        await process_upload(s, directory, not_called, lambda x: not x.cancelled, not_called)
        self.assertFalse(directory.exists())


if __name__ == '__main__': unittest.main()
