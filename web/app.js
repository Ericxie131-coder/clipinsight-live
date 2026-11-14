const $ = id => document.getElementById(id);
let session = null,
  socket = null,
  stream = null,
  audio = null,
  node = null,
  source = null,
  started = 0,
  paused = false,
  busy = false,
  finishing = false,
  follow = true,
  questionBusy = false,
  polling = false,
  flushResolve = null,
  mode = 'live',
  selectedFile = null,
  previewURL = null,
  previewSessionId = null,
  uploadXHR = null,
  frameJob = null,
  visualSignature = null;
const labels = {
  idle: 'Ready',
  preparing: 'Preparing',
  recording: 'Recording',
  paused: 'Paused',
  finalizing: 'Finalizing',
  completed: 'Complete',
  failed: 'Interrupted'
};
labels.uploading = 'Uploading';
labels.processing = 'Processing';
function uploadActive() {
  return session?.source === 'upload' && ['uploading', 'processing', 'finalizing'].includes(session.status);
}

function chooseMode(next) {
  if (busy || uploadActive() || socket || finishing) return;
  mode = next;
  $('mode-live').setAttribute('aria-selected', String(mode === 'live'));
  $('mode-upload').setAttribute('aria-selected', String(mode === 'upload'));
  $('upload-panel').hidden = mode !== 'upload';
  $('pause').hidden = mode === 'upload';
  $('stop').hidden = mode === 'upload';
  document.querySelector('.camera-toggle').hidden = mode === 'upload';
  document.querySelector('.stage-bottom').hidden = mode === 'upload';
  $('privacy').textContent = mode === 'upload' ? 'No devices required.' : 'Devices activate when you start.';
  const v = $('video');
  v.srcObject = null;
  v.pause();
  v.controls = mode === 'upload';
  v.muted = mode === 'live';
  v.autoplay = mode === 'live';
  v.style.objectFit = mode === 'upload' ? 'contain' : 'cover';
  v.style.transform = mode === 'upload' ? 'none' : '';
  if (mode === 'upload' && previewURL) {
    v.src = previewURL;
    v.style.display = 'block';
    $('camera-empty').style.display = 'none';
  } else {
    v.removeAttribute('src');
    v.load();
    v.style.display = 'none';
    $('camera-empty').style.display = 'flex';
  }
  $('camera-empty').querySelector('h2').textContent = mode === 'upload' ? 'Video preview' : 'Camera preview';
  $('camera-empty').querySelector('p').textContent = mode === 'upload' ? 'Choose a video to preview.' : 'Start a session to connect.';
  $('stage-label').textContent = mode === 'upload' ? 'VIDEO PREVIEW' : 'CAMERA PREVIEW';
  document.querySelector('.stage').setAttribute('aria-label', mode === 'upload' ? 'Video preview' : 'Camera preview');
  setControls();
}

function resetResults() {
  $('answers').replaceChildren();
  $('summary').textContent = 'No notes yet.';
  $('summary').classList.add('placeholder');
  $('highlights').replaceChildren();
  $('coverage').textContent = '';
  $('transcript').replaceChildren();
  $('ask-status').textContent = '';
  document.querySelector('.highlights-section').hidden = true;
  visualSignature = null;
  renderVisuals({visuals: [], visual_status: 'waiting'});
}

async function uploadVideo() {
  if (busy || uploadActive() || !selectedFile) return;
  if ((session?.segments.length || session?.visuals?.length) && !confirm('Start over? Export this session first if you want to keep it.')) return;
  if (!selectedFile.size || selectedFile.size > 512 * 1024 * 1024) {
    notice('Choose a non-empty video under 512 MB.'); return;
  }
  busy = true; questionBusy = false; notice(); setControls();
  try {
    session = await api('/sessions', {method: 'POST', body: JSON.stringify({
      title: $('title').value, language: $('language').value, source: 'upload', visual_enabled: $('vision-enabled').checked
    })});
    previewSessionId = session.id;
    resetResults();
    $('upload-progress').hidden = false;
    $('upload-stage').textContent = 'Uploading…';
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      uploadXHR = xhr;
      setControls();
      xhr.open('POST', `/api/sessions/${session.id}/upload?filename=${encodeURIComponent(selectedFile.name)}`);
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');
      xhr.upload.onprogress = event => {
        if (event.lengthComputable) {
          $('file-progress').value = event.loaded / event.total * 100;
          $('upload-stage').textContent = `Uploading ${Math.round(event.loaded / event.total * 100)}%`;
        }
      };
      xhr.onload = () => {
        let data;
        try { data = JSON.parse(xhr.responseText); } catch { reject(Error('Invalid upload response.')); return; }
        if (xhr.status >= 200 && xhr.status < 300) { render(data); resolve(); }
        else reject(Error(data.detail || 'Upload failed. Try again.'));
      };
      xhr.onerror = () => reject(Error('Upload interrupted. Check the server connection.'));
      xhr.onabort = () => reject(Error('Upload cancelled.'));
      xhr.send(selectedFile);
    });
  } catch (e) {
    notice(e.message);
    if (session) {
      try { await api(`/sessions/${session.id}`, {method: 'DELETE'}); } catch {}
      session = null;
    }
  } finally { uploadXHR = null; busy = false; setControls(); }
}
const time = seconds => `${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;

function notice(message = '') {
  $('notice').textContent = uiError(message);
  $('notice').hidden = !message;
}
function uiError(message = '') {
  if (!/[\u3400-\u9fff]/.test(message)) return message;
  const errors = [
    ['已有活动会话', 'Another session is active. Stop or delete it first.'],
    ['请先结束当前任务', 'Finish the current session first.'],
    ['会话不存在', 'Session expired. Start a new session.'],
    ['会话已删除', 'This session was deleted.'],
    ['摘要未更新', 'Summary failed. Select Refresh to retry.'],
    ['没有音轨', 'No audio track. Enable screen text or choose another video.'],
    ['没有识别到', 'No speech or readable screen text found.'],
    ['512 MB', 'The video must be under 512 MB.'],
    ['60 分钟', 'The video must be under 60 minutes.'],
    ['还没有', 'Waiting for speech or screen text.'],
    ['问答未完成', 'Could not generate an answer. Try again.'],
    ['画面', 'Screen text recognition failed. Try a clearer frame.'],
    ['上传', 'Upload failed. Check the connection and try again.']
  ];
  return errors.find(([source]) => message.includes(source))?.[1] || 'Processing failed. Check the model server and try again.';
}
async function api(path, options = {}) {
  const r = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  });
  if (!r.ok) {
    let data;
    try {
      data = await r.json();
    } catch {
      throw Error(`Request failed (${r.status}).`)
    }
    throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return r.json();
}

function setControls() {
  const active = !!socket && socket.readyState === WebSocket.OPEN;
  const n = (session?.segments?.length || 0) + (session?.visuals?.filter(r => r.text).length || 0);
  const locked = busy || active || finishing || uploadActive();
  $('start').disabled = locked || (mode === 'upload' && !selectedFile);
  $('start').lastChild.textContent = busy ? ' Preparing…' : mode === 'upload' ? 'Analyze video' : 'Start session';
  $('pause').disabled = !active || finishing;
  $('stop').disabled = !active || finishing;
  $('pause').querySelector('span').textContent = paused ? 'Resume' : 'Pause';
  $('title').disabled = locked;
  $('language').disabled = locked;
  $('camera').disabled = locked;
  $('vision-enabled').disabled = locked;
  $('video-file').disabled = locked;
  $('mode-live').disabled = locked;
  $('mode-upload').disabled = locked;
  $('refresh').disabled = !n || session?.summary_status === 'generating';
  $('ask').disabled = !n || questionBusy;
  $('question').disabled = !n || questionBusy;
  $('export').disabled = !n;
  $('clear').disabled = !session || active || (busy && !uploadXHR) || finishing;
  $('clear').textContent = uploadActive() ? 'Cancel and delete' : 'Delete session';
  document.body.classList.toggle('recording', active && !paused);
}

function render(s) {
  session = s;
  renderVisuals(s);
  $('session-status').textContent = labels[s.status] || s.status;
  if (s.source === 'upload') {
    $('upload-progress').hidden = false;
    const stage = s.progress?.stage;
    const stages = {uploading:'Uploading', decoding:'Reading audio', loading:'Loading model',
      vision:'Reading screen text', transcribing:'Transcribing', summarizing:'Summarizing', done:'Complete',
      summary_error:'Summary failed — refresh to retry', error:'Processing failed'};
    $('upload-stage').textContent = `${s.filename || 'Video'} · ${stages[stage] || 'Waiting'}`;
    const p = $('file-progress');
    if (['transcribing','vision'].includes(stage) && s.progress.duration) {
      p.value = s.progress.processed_seconds / s.progress.duration * 100;
      $('upload-stage').textContent += ` ${time(s.progress.processed_seconds)} / ${time(s.progress.duration)}`;
    } else if (['done','summary_error'].includes(stage)) p.value = 100;
    else p.removeAttribute('value');
  } else $('upload-progress').hidden = true;
  $('segment-count').textContent = `${s.segments.length} ${s.segments.length === 1 ? 'segment' : 'segments'}`;
  if (s.segments.length) {
    const container = $('transcript');
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 70;
    const fragment = document.createDocumentFragment();
    for (const row of s.segments) {
      const div = document.createElement('div');
      div.className = 'segment';
      div.id = `segment-${row.id}`;
      const canSeek = s.source === 'upload' && previewSessionId === s.id && previewURL;
      const t = document.createElement(canSeek ? 'button' : 'time');
      t.textContent = time(row.start);
      if (canSeek) {
        t.className = 'seek-time';
        t.type = 'button';
        t.setAttribute('aria-label', `Seek to ${time(row.start)}`);
        t.addEventListener('click', () => { $('video').currentTime = row.start; $('video').play().catch(() => {}); });
      }
      const p = document.createElement('p');
      p.textContent = row.text;
      div.append(t, p);
      fragment.append(div);
    }
    container.replaceChildren(fragment);
    if (follow || nearBottom) container.scrollTop = container.scrollHeight;
  }
  if (!s.segments.length && s.source === 'upload') {
    const p = document.createElement('p'); p.className = 'placeholder';
    p.textContent = ['completed', 'finalizing'].includes(s.status) ? 'No speech detected. See visual notes.' : 'Waiting for speech…';
    $('transcript').replaceChildren(p);
  }
  $('partial').textContent = s.partial || '';
  $('transcript-status').textContent = s.source === 'upload' ? (s.status === 'processing' ? 'Processing' : 'Video') : s.status === 'recording' ? 'Listening' : s.status === 'paused' ? 'Paused' : 'Confirmed';
  const status = {
    waiting: '',
    generating: 'Updating…',
    ready: 'Updated',
    error: 'Retry needed'
  };
  $('summary-status').textContent = status[s.summary_status] || '';
  if (s.summary?.summary) {
    $('summary').textContent = s.summary.summary;
    $('summary').classList.remove('placeholder');
    $('highlights').replaceChildren(...s.summary.highlights.map(text => {
      const li = document.createElement('li');
      li.textContent = text;
      return li;
    }));
    document.querySelector('.highlights-section').hidden = !s.summary.highlights.length;
    $('coverage').textContent = `Through ${time(s.summary.covered_until)}${s.summary_revision<s.revision?' · Update pending':''}`;
  }
  if (s.error) notice(s.error);
  setControls();
}
async function stopDevices() {
  if (node) {
    node.port.onmessage = null;
    node.disconnect();
    node = null;
  }
  source?.disconnect();
  source = null;
  stream?.getTracks().forEach(t => t.stop());
  stream = null;
  if (audio) {
    await audio.close().catch(() => {});
    audio = null;
  }
  $('video').srcObject = null;
  $('video').style.display = 'none';
  $('camera-empty').style.display = 'flex';
  $('meter').value = 0;
  $('mic-label').textContent = 'Mic off';
}

function waitSocket(ws) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(Error('Connection timed out.')), 20000);
    ws.onopen = () => {};
    ws.onerror = () => {
      clearTimeout(timeout);
      reject(Error('Cannot connect to the transcription server.'));
    };
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'ready') {
        clearTimeout(timeout);
        resolve();
      }
      if (msg.type === 'error') {
        clearTimeout(timeout);
        reject(Error(msg.message));
      }
    };
  });
}
async function start() {
  if (busy) return;
  if ((session?.segments.length || session?.visuals?.length) && !confirm('Start over? Export this session first if you want to keep it.')) return;
  busy = true;
  questionBusy = false;
  finishing = false;
  paused = false;
  notice();
  setControls();
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw Error('Device access requires localhost or HTTPS.');
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true
        },
        video: $('camera').checked ? {
          width: {
            ideal: 1280
          },
          height: {
            ideal: 720
          }
        } : false
      });
    } catch (e) {
      if ($('camera').checked && e.name === 'NotFoundError') {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: false
        });
        notice('No camera found. Using audio only.');
      } else throw e;
    }
    if (stream.getVideoTracks().length) {
      $('video').srcObject = stream;
      $('video').style.display = 'block';
      $('camera-empty').style.display = 'none';
    }
    $('session-status').textContent = 'Loading model…';
    session = await api('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        title: $('title').value,
        language: $('language').value, visual_enabled: $('vision-enabled').checked
      })
    });
    await api(`/sessions/${session.id}/prepare`, {
      method: 'POST'
    });
    audio = new AudioContext({
      sampleRate: 16000
    });
    await audio.resume();
    if (audio.sampleRate !== 16000) throw Error('16 kHz audio is unavailable. Try the latest Chrome.');
    await audio.audioWorklet.addModule('/static/pcm-worklet.js');
    socket = new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/sessions/${session.id}/audio`);
    await waitSocket(socket);
    started = performance.now();
    visualSignature = null;
    $('answers').replaceChildren();
    $('summary').textContent = 'No notes yet.';
    $('summary').classList.add('placeholder');
    $('highlights').replaceChildren();
    document.querySelector('.highlights-section').hidden = true;
    $('coverage').textContent = '';
    $('transcript').replaceChildren();
    socket.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'error') notice(msg.message);
      if (msg.type === 'ready_to_stop') {
        finishing = false;
        session.status = 'completed';
        socket.close();
        $('session-status').textContent = 'Complete';
      }
      if (msg.type === 'transcript' && msg.data.error) notice(msg.data.error);
    };
    socket.onclose = () => {
      flushResolve?.();
      flushResolve = null;
      if (!finishing && session?.status !== 'completed') notice('Disconnected. Export your notes or start a new session.');
      socket = null;
      finishing = false;
      stopDevices();
      setControls();
    };
    node = new AudioWorkletNode(audio, 'pcm-capture');
    source = audio.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    source.connect(node);
    const mute = audio.createGain();
    mute.gain.value = 0;
    node.connect(mute).connect(audio.destination);
    node.port.onmessage = event => {
      if (event.data?.type === 'flushed') {
        flushResolve?.();
        flushResolve = null;
        return;
      }
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      if (socket.bufferedAmount > 640000 && !finishing) {
        notice('Audio connection is too slow. Recording stopped.');
        stop();
        return;
      }
      const packet = event.data;
      if (paused) {
        new Int16Array(packet).fill(0);
      }
      socket.send(packet);
      if (!paused) {
        const values = new Int16Array(packet);
        let sum = 0;
        for (const x of values) sum += x * x;
        $('meter').value = Math.min(1, Math.sqrt(sum / values.length) / 5000);
      }
    };
    $('mic-label').textContent = 'Mic on';
    $('stage-label').textContent = stream.getVideoTracks().length ? 'LIVE CAMERA' : 'AUDIO ONLY';
    session.status = 'recording';
    render(session);
    captureFrame();
  } catch (e) {
    notice(e.name === 'NotAllowedError' ? 'Allow microphone access in your browser, then try again.' : e.message);
    if (socket) {
      socket.close();
      socket = null;
    }
    await stopDevices();
    if (session) {
      try {
        await api(`/sessions/${session.id}`, {
          method: 'DELETE'
        });
      } catch {}
    }
    session = null;
  } finally {
    busy = false;
    setControls();
  }
}

function pause() {
  if (!socket) return;
  paused = !paused;
  stream?.getAudioTracks().forEach(t => t.enabled = !paused);
  socket.send(JSON.stringify({
    type: paused ? 'pause' : 'resume'
  }));
  $('mic-label').textContent = paused ? 'Mic paused' : 'Mic on';
  if (session) session.status = paused ? 'paused' : 'recording';
  setControls();
}
async function stop() {
  if (!socket || finishing) return;
  finishing = true;
  stream?.getTracks().forEach(track => { track.enabled = false; });
  setControls();
  if (node) await new Promise(resolve => {
    flushResolve = resolve;
    node.port.postMessage({
      type: 'flush'
    });
  });
  await stopDevices();
  if (frameJob) await frameJob;
  paused = false;
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({
    type: 'stop'
  }));
  if (session) session.status = 'finalizing';
  setControls();
  $('session-status').textContent = 'Finalizing…';
}
async function poll() {
  if (polling) return;
  polling = true;
  try {
    if (session && !busy) {
      const id = session.id;
      const s = await api(`/sessions/${id}`);
      if (session?.id === id && !busy) render(s);
    }
    const h = await api('/health');
    $('model-names').textContent = `${h.llm_model || 'Qwen3-1.7B'}${h.llm_provider === 'ollama' ? ' · Windows / Ollama' : ''} · Qwen3-Embedding-0.6B · RapidOCR`;
    $('backend-state').textContent = h.asr === 'ready' ? 'Connected' : h.asr === 'error' ? 'Model error' : 'Connected';
    $('model-state').textContent = h.llm === 'error' ? 'Model error. Check the server.' : h.llm === 'loading' ? 'Loading model…' : h.llm === 'generating' ? 'Generating…' : '';
  } catch (e) {
    $('backend-state').textContent = 'Disconnected';
  } finally {
    polling = false;
  }
}

function appendAnswer(result) {
  const box = document.createElement('div');
  box.className = 'answer';
  const q = document.createElement('p');
  q.className = 'question-text';
  q.textContent = result.question;
  const p = document.createElement('p');
  p.textContent = result.answer;
  const small = document.createElement('small');
  small.textContent = `Through ${time(result.covered_until)}`;
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = `Sources (${result.evidence.length})`;
  details.append(summary);
  for (const e of result.evidence) {
    const b = document.createElement('blockquote');
    b.textContent = `[${time(e.start)}–${time(e.end)}] ${e.kind === 'visual' ? 'Screen text' : 'Speech'}: ${e.text}`;
    details.append(b);
  }
  box.append(q, p, small, details);
  $('answers').append(box);
  $('answers').scrollTop = $('answers').scrollHeight;
}
$('start').addEventListener('click', () => mode === 'upload' ? uploadVideo() : start());
$('mode-live').addEventListener('click', () => chooseMode('live'));
$('mode-upload').addEventListener('click', () => chooseMode('upload'));
$('video-file').addEventListener('change', () => {
  const file = $('video-file').files[0];
  if (!file) return;
  if (!/\.(mp4|mov|webm|mkv|m4v)$/i.test(file.name) || !file.size || file.size > 512 * 1024 * 1024) {
    notice('Choose an MP4, MOV, WebM, MKV or M4V video under 512 MB.');
    $('video-file').value = ''; selectedFile = null; previewSessionId = null;
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null; $('file-label').textContent = 'Choose video'; chooseMode('upload'); return;
  }
  const video = $('video'); video.pause();
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = URL.createObjectURL(file); selectedFile = file; previewSessionId = null;
  $('file-label').textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
  if ($('title').value === 'Untitled session') $('title').value = file.name.replace(/\.[^.]+$/, '').slice(0, 100);
  notice(); chooseMode('upload');
});
$('pause').addEventListener('click', pause);
$('stop').addEventListener('click', stop);
$('refresh').addEventListener('click', async () => {
  try {
    await api(`/sessions/${session.id}/summary`, {
      method: 'POST'
    });
    $('summary-status').textContent = 'Updating…';
  } catch (e) {
    notice(e.message);
  }
});
$('follow').addEventListener('click', () => {
  follow = true;
  $('transcript').scrollTop = $('transcript').scrollHeight;
});
$('transcript').addEventListener('scroll', () => {
  const t = $('transcript');
  follow = t.scrollHeight - t.scrollTop - t.clientHeight < 70;
});
$('ask-form').addEventListener('submit', async event => {
  event.preventDefault();
  const q = $('question').value.trim();
  if (!q || !session || questionBusy) return;
  const questionSession = session.id;
  questionBusy = true;
  setControls();
  $('ask-status').textContent = 'Thinking…';
  try {
    const result = await api(`/sessions/${questionSession}/questions`, {
      method: 'POST',
      body: JSON.stringify({
        question: q
      })
    });
    if (session?.id !== questionSession) return;
    appendAnswer(result);
    $('question').value = '';
    $('ask-status').textContent = '';
  } catch (e) {
    if (session?.id === questionSession) $('ask-status').textContent = uiError(e.message);
  } finally {
    if (session?.id === questionSession) {
      questionBusy = false;
      setControls();
    }
  }
});
$('export').addEventListener('click', async () => {
  if (!session) return;
  try {
    const r = await fetch(`/api/sessions/${session.id}/export`);
    if (!r.ok) throw Error('Export failed. Try again.');
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ClipInsight-notes.md';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    notice(e.message);
  }
});
$('clear').addEventListener('click', async () => {
  if (!session || !confirm('Delete this session? Export first to keep a copy.')) return;
  if (uploadXHR) { uploadXHR.abort(); return; }
  try {
    await api(`/sessions/${session.id}`, {
      method: 'DELETE'
    });
    location.reload();
  } catch (e) {
    notice(e.message);
  }
});
window.addEventListener('beforeunload', event => {
  if (stream || session?.segments.length || session?.visuals?.length) {
    event.preventDefault();
    event.returnValue = '';
  }
});
setInterval(() => {
  if (started && (stream || finishing)) $('timer').textContent = time((performance.now() - started) / 1000);
}, 1000);
setInterval(poll, 1800);
poll();

function renderVisuals(s) {
  const rows = s.visuals || [];
  $('visual-count').textContent = `${rows.length} ${rows.length === 1 ? 'frame' : 'frames'}`;
  const status = {waiting:'', processing:'Reading…', ready:'Updated', no_text:'No text found', error:'Retry needed', disabled:'Off'};
  $('visual-status').textContent = s.visual_limit_reached ? '120-frame limit reached' : status[s.visual_status] || '';
  $('visual-error').textContent = uiError(s.visual_error || '');
  $('visual-error').hidden = !s.visual_error;
  $('visual-summary').textContent = s.summary?.visual_summary || 'No screen text yet.';
  $('visual-summary').classList.toggle('placeholder', !s.summary?.visual_summary);
  const signature = rows.map(r => r.id).join(',');
  if (signature === visualSignature) return;
  visualSignature = signature;
  const container = $('visual-frames');
  container.replaceChildren();
  for (const row of rows) {
    const details = document.createElement('details'); details.className = 'visual-frame';
    const summary = document.createElement('summary');
    summary.textContent = `${time(row.start)} · ${row.text ? row.text.replace(/\n/g, ' ').slice(0, 56) : 'No readable text'}`;
    const img = document.createElement('img'); img.src = row.image; img.alt = `Frame at ${time(row.start)}`; img.loading = 'lazy';
    const text = document.createElement('p'); text.textContent = row.text || 'No readable text.';
    details.append(summary, img, text);
    if (s.source === 'upload' && previewSessionId === s.id) {
      const seek = document.createElement('button'); seek.type = 'button'; seek.className = 'text-button';
      seek.textContent = `Play from ${time(row.start)}`;
      seek.addEventListener('click', () => { $('video').currentTime = row.start; $('video').play().catch(() => {}); });
      details.append(seek);
    }
    container.append(details);
  }
}
async function captureFrame() {
  if (frameJob || mode !== 'live' || paused || finishing || !session?.visual_enabled || session.status !== 'recording' || !stream?.getVideoTracks().length || session.visual_limit_reached) return;
  const video = $('video');
  if (!video.videoWidth || !video.videoHeight) return;
  const sid = session.id;
  const at = (performance.now() - started) / 1000;
  frameJob = (async () => {
    const canvas = document.createElement('canvas');
    canvas.width = Math.min(1280, video.videoWidth); canvas.height = Math.round(video.videoHeight * canvas.width / video.videoWidth);
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .8));
    if (!blob) return;
    const response = await fetch(`/api/sessions/${sid}/frame?at=${at.toFixed(2)}`, {method:'POST', headers:{'Content-Type':'image/jpeg'}, body:blob, signal:AbortSignal.timeout(15000)});
    if (!response.ok && response.status !== 429) {
      $('visual-error').textContent = 'Screen text could not be read. Retrying on the next frame.'; $('visual-error').hidden = false;
    }
  })().catch(() => { $('visual-error').textContent = 'Frame upload failed. Retrying on the next frame.'; $('visual-error').hidden = false; }).finally(() => { frameJob = null; });
  await frameJob;
}
setInterval(captureFrame, 12000);
