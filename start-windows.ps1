$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
if (-not $env:CLIP_PORT) { $env:CLIP_PORT = '8765' }
$env:CLIP_LLM_PROVIDER = 'ollama'
$env:CLIP_EMBEDDING_PROVIDER = 'ollama'
if (-not $env:CLIP_OLLAMA_URL) { $env:CLIP_OLLAMA_URL = 'http://127.0.0.1:11434' }
if (-not $env:CLIP_OLLAMA_MODEL) { $env:CLIP_OLLAMA_MODEL = 'qwen3:1.7b' }
if (-not $env:CLIP_OLLAMA_EMBED_MODEL) { $env:CLIP_OLLAMA_EMBED_MODEL = 'qwen3-embedding:0.6b' }
Invoke-RestMethod "$env:CLIP_OLLAMA_URL/api/version" -TimeoutSec 5 | Out-Null
& '.\.venv\Scripts\python.exe' run.py
