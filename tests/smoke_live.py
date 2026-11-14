"""Real local audio integration test. No synthetic transcript injection or microphone use."""
import asyncio
import json
import os
import sys
import time
import urllib.request
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps'))
from websockets.asyncio.client import connect

BASE=os.environ.get('CLIP_TEST_URL','http://127.0.0.1:8765').rstrip('/')
def request(path,data=None,method=None):
    req=urllib.request.Request(BASE+'/api'+path,data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)

async def main():
    with wave.open(sys.argv[1],'rb') as wav:
        assert wav.getframerate()==16000 and wav.getnchannels()==1 and wav.getsampwidth()==2
        pcm=wav.readframes(wav.getnframes())
    s=request('/sessions',{'title':'Audio integration verification','language':'en'})
    sid=s['id'];print('session',sid,flush=True)
    await asyncio.to_thread(request,f'/sessions/{sid}/prepare',{},'POST')
    began=time.monotonic();events=[]
    async def ask_during_recording():
        for _ in range(12):
            await asyncio.sleep(2)
            current=await asyncio.to_thread(request,f'/sessions/{sid}')
            if current['status']=='completed':return None
            if current['segments']:
                print('asking while status=',current['status'],flush=True)
                return await asyncio.to_thread(request,f'/sessions/{sid}/questions',{'question':'这段讲话介绍了什么？'},'POST')
        return None
    async with connect(BASE.replace('http://','ws://').replace('https://','wss://') + f'/api/sessions/{sid}/audio',origin=BASE,max_size=8*1024*1024) as ws:
        hello=json.loads(await ws.recv());assert hello['type']=='ready',hello
        live_query=asyncio.create_task(ask_during_recording())
        async def send():
            for i in range(0,len(pcm),3200):
                await ws.send(pcm[i:i+3200]);await asyncio.sleep(.1)
            await ws.send(json.dumps({'type':'stop'}))
        sender=asyncio.create_task(send())
        async for msg in ws:
            item=json.loads(msg);events.append(item)
            if item['type']=='error':raise AssertionError(item)
            if item['type']=='ready_to_stop':break
        await sender
        live_answer=await live_query
    result=await asyncio.to_thread(request,f'/sessions/{sid}')
    assert result['status']=='completed',result
    assert result['segments'],'ASR returned no confirmed words'
    print('ASR confirmed',len(result['segments']),'segments in',round(time.monotonic()-began,1),'seconds',flush=True)
    print('TEXT:', ' '.join(r['text'] for r in result['segments']),flush=True)
    deadline=time.monotonic()+150
    while result['summary_status'] in ('waiting','generating') and time.monotonic()<deadline:
        await asyncio.sleep(2);result=await asyncio.to_thread(request,f'/sessions/{sid}')
    print('SUMMARY:',result['summary'],result['error'],flush=True)
    assert result['summary_status']=='ready' and result['summary'].get('summary'),result
    assert result['summary_revision']==result['revision'],'Final summary does not cover the latest evidence'
    evidence_result=await asyncio.to_thread(request,f'/sessions/{sid}/questions',{'question':'这段讲话介绍了什么？'},'POST')
    assert evidence_result['evidence']
    print('QA:',evidence_result['answer'],flush=True)
    report={'asr_seconds':round(time.monotonic()-began,1),'session':result,'question':evidence_result,'live_question':live_answer}
    (ROOT/'.runtime/smoke-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('saved .runtime/smoke-result.json',flush=True)
    await asyncio.to_thread(request,f'/sessions/{sid}',None,'DELETE')

if __name__=='__main__':asyncio.run(main())
