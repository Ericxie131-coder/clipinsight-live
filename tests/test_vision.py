import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.deps'), str(ROOT / 'backend')]
from domain import Session
from vision import add_observation, recognize, scan_video, video_duration
import app


def board_image():
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGB', (960, 540), 'white')
    d = ImageDraw.Draw(im)
    font = None
    for name in ('DejaVuSans.ttf', 'Arial.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf', 'C:/Windows/Fonts/arial.ttf'):
        try:
            font = ImageFont.truetype(name, 36)
            break
        except OSError:
            pass
    if font is None:
        font = ImageFont.load_default(size=36)
    d.text((50, 100), 'Waveguide: total internal reflection', fill='black', font=font)
    d.text((50, 220), 'Camera + Microphone + OCR', fill='black', font=font)
    return im


class VisionTests(unittest.TestCase):
    def test_real_ocr_reads_board_text(self):
        import numpy as np
        row = recognize(np.array(board_image())[:, :, ::-1].copy(), 5)
        self.assertIn('Waveguide', row['text'])
        self.assertIn('Microphone', row['text'])
        self.assertTrue(row['image'].startswith('data:image/jpeg;base64,'))
        self.assertTrue(all(line['confidence'] >= .65 for line in row['lines']))

    def test_dedup_and_visual_evidence_export(self):
        s = Session()
        row = {'id':'v0','start':0,'end':0,'text':'Camera and microphone', 'kind':'visual','image':'','lines':[]}
        self.assertTrue(add_observation(s,row))
        self.assertFalse(add_observation(s,{**row,'id':'v5','start':5}))
        self.assertEqual(s.revision,1)
        self.assertEqual(s.evidence_rows()[0]['kind'],'visual')
        self.assertIn('Camera and microphone',s.markdown())
        self.assertTrue(add_observation(s,{**row,'id':'v10','text':'Camera and microphone 90 V','start':10}))
        self.assertTrue(add_observation(s,{**row,'id':'v15','text':'Camera and microphone 10 V','start':15}))

    def test_real_video_sampling_and_cancellation(self):
        import av
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'board.mp4'
            with av.open(str(path),'w') as out:
                stream = out.add_stream('mpeg4',rate=1);stream.width=960;stream.height=540
                frame = np.array(board_image())
                for _ in range(7):
                    for packet in stream.encode(av.VideoFrame.from_ndarray(frame,format='rgb24')):out.mux(packet)
                for packet in stream.encode():out.mux(packet)
            self.assertAlmostEqual(video_duration(path),7)
            rows=[]
            scan_video(path,7,rows.append)
            self.assertTrue(rows)
            self.assertIn('Waveguide',rows[0]['text'])
            cancelled=[];scan_video(path,7,cancelled.append,lambda:True)
            self.assertFalse(cancelled)


class VisionSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_visual_only_summary_and_prompt_source_label(self):
        s=Session();app.sessions[s.id]=s
        add_observation(s,{'id':'v2','start':2,'end':2,'text':'Waveguide uses total internal reflection','kind':'visual','image':'','lines':[]})
        calls=[]
        async def fake_thread(fn,messages,tokens):
            calls.append(messages)
            return json.dumps({'summary':'波导使用全内反射','highlights':['波导原理'],'visual_summary':'板书介绍全内反射'})
        try:
            with patch.object(app.asyncio,'to_thread',fake_thread):await app.update_summary(s,True)
            self.assertIn('[画面OCR]',calls[0][-1]['content'])
            self.assertIn('Waveguide',calls[0][-1]['content'])
            self.assertEqual(s.summary['visual_summary'],'板书介绍全内反射')
        finally:app.sessions.pop(s.id,None)

    async def test_late_frame_refreshes_completed_summary(self):
        from starlette.requests import Request
        s=Session(status='recording');app.sessions[s.id]=s
        async def receive():return {'type':'http.request','body':b'test-jpeg','more_body':False}
        request=Request({'type':'http'},receive)
        row={'id':'v5','start':5,'end':5,'text':'Late board evidence','kind':'visual','image':'','lines':[]}
        async def fake_thread(fn):
            s.status='completed'
            return row
        calls=[]
        async def summary(session,force):calls.append((session.id,force))
        try:
            with patch.object(app.asyncio,'to_thread',fake_thread), patch.object(app,'update_summary',summary):
                result=await app.camera_frame(s.id,request,5)
                await asyncio.gather(*list(app.background))
            self.assertTrue(result['accepted'])
            self.assertEqual(calls,[(s.id,True)])
            self.assertEqual(s.visuals[0]['text'],'Late board evidence')
        finally:app.sessions.pop(s.id,None)

    async def test_live_endpoint_rejects_frame_while_paused(self):
        from fastapi import HTTPException
        s=Session(status='paused');app.sessions[s.id]=s
        try:
            with self.assertRaises(HTTPException) as raised:await app.camera_frame(s.id,None,0)
            self.assertEqual(raised.exception.status_code,409)
        finally:app.sessions.pop(s.id,None)

if __name__=='__main__':unittest.main()
