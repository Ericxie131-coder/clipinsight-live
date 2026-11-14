"""Optional local Ollama provider, used by the Windows deployment."""
import json
import os
import urllib.request


def request(path, body):
    base = os.environ.get('CLIP_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    # Local model requests must not inherit a machine's HTTP proxy settings.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=300) as response:
        return json.load(response)


def generate(messages, tokens):
    model = os.environ.get('CLIP_OLLAMA_MODEL', 'qwen3:1.7b')
    body = {'model': model,
            'messages': messages, 'stream': False, 'think': False,
            # Thinking-only Qwen VL builds may ignore think=False. Reserve space
            # for reasoning while only returning the final content to the UI.
            'options': {'num_predict': max(2048, tokens * 4) if 'qwen3-vl' in model else tokens, 'num_ctx': 4096, 'temperature': .1}}
    if 'JSON' in messages[0]['content']:
        body['format'] = 'json'
    result = request('/api/chat', body)
    content = result.get('message', {}).get('content', '').strip()
    if not content:
        raise ValueError('Ollama returned an empty answer')
    return content


def retrieve(rows, question):
    import numpy as np
    model = os.environ.get('CLIP_OLLAMA_EMBED_MODEL', 'qwen3-embedding:0.6b')
    texts = [r['text'] for r in rows]
    vectors = []
    for offset in range(0, len(texts), 16):
        vectors.extend(request('/api/embed', {'model': model, 'input': texts[offset:offset + 16]})['embeddings'])
    query_text = 'Instruct: Given a question, retrieve relevant speech or slide evidence.\nQuery: ' + question
    query = request('/api/embed', {'model': model, 'input': query_text})['embeddings'][0]
    matrix = np.asarray(vectors, dtype=np.float32)
    query = np.asarray(query, dtype=np.float32)
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    query /= max(float(np.linalg.norm(query)), 1e-12)
    scores = matrix @ query
    return [{**rows[int(i)], 'similarity': float(scores[i])} for i in np.argsort(scores)[::-1][:3]]
