import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT/'backend')]
import app
from domain import Session


class SummaryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await asyncio.gather(*list(app.background),return_exceptions=True)
        app.sessions.clear()

    async def test_summary_consumes_every_batch_including_opening(self):
        s = Session(source='upload'); app.sessions[s.id] = s
        for i in range(80):
            s.merge({'lines': [{'start': i, 'end': i + 1, 'speaker': 1, 'text': f'evidence-{i:03d}'}]})
        prompts = []
        async def fake_thread(fn, messages, tokens):
            prompts.append(messages[-1]['content'])
            return json.dumps({'summary': f'cumulative-{len(prompts)}', 'highlights': []})
        with patch.object(app.asyncio, 'to_thread', fake_thread):
            await app.update_summary(s, True)
        self.assertEqual(len(prompts), 3)
        for i in range(80):
            self.assertIn(f'evidence-{i:03d}', '\n'.join(prompts))
        self.assertIn('cumulative-1', prompts[1])
        self.assertEqual(s.summary['covered_until'], 80)

    async def test_stop_queues_tail_after_interim_summary_finishes(self):
        s=Session();app.sessions[s.id]=s
        s.merge({'lines':[{'start':0,'end':2,'speaker':1,'text':'开场内容'}]})
        entered=asyncio.Event();release=asyncio.Event();calls=[]
        async def fake_thread(fn,messages,tokens):
            calls.append(messages[-1]['content'])
            if len(calls)==1:
                entered.set();await release.wait()
            return json.dumps({'summary':f'摘要{len(calls)}','highlights':['重点']})
        with patch.object(app.asyncio,'to_thread',fake_thread):
            first=asyncio.create_task(app.update_summary(s,True))
            await entered.wait()
            s.merge({'lines':[{'start':3,'end':5,'speaker':1,'text':'最后补充的内容'}]})
            s.status='completed'
            await app.update_summary(s,True)
            release.set();await first
            await asyncio.gather(*list(app.background))
        self.assertEqual(s.summary_revision,s.revision)
        self.assertEqual(len(calls),2)
        self.assertIn('最后补充的内容',calls[-1])

    async def test_deleted_session_not_repopulated_by_late_summary(self):
        s=Session();app.sessions[s.id]=s
        s.merge({'lines':[{'start':0,'end':2,'speaker':1,'text':'内容'}]})
        async def fake_thread(*args):
            del app.sessions[s.id]
            return '{"summary":"不会保存","highlights":[]}'
        with patch.object(app.asyncio,'to_thread',fake_thread):
            await app.update_summary(s,True)
        self.assertNotIn(s.id,app.sessions)
        self.assertEqual(s.summary,{})

if __name__=='__main__':unittest.main()
