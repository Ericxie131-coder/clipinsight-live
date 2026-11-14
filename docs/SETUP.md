# Deployment and configuration

## Local models

The launch scripts select Ollama for both text generation and embedding retrieval. Start Ollama, download the two models listed in the README, and keep it running while using ClipInsight.

| Environment variable | Purpose | Launch-script default |
| --- | --- | --- |
| `CLIP_PORT` | Local HTTP and WebSocket port | `8765` |
| `CLIP_OLLAMA_URL` | Ollama endpoint | `http://127.0.0.1:11434` |
| `CLIP_OLLAMA_MODEL` | Summary/Q&A model | `qwen3:1.7b` |
| `CLIP_OLLAMA_EMBED_MODEL` | Retrieval model | `qwen3-embedding:0.6b` |
| `CLIP_ASR_MODEL` | Whisper size | `base` |
| `CLIP_ASR_MODEL_DIR` | Optional existing Whisper model directory | unset |

The scripts read process environment variables, not `.env` files. Use `export NAME=value` in a shell or `$env:NAME='value'` in PowerShell before launching.

## Windows GPU

Install a CUDA-compatible NVIDIA driver and the required CTranslate2 runtime libraries for your machine. The Windows requirements include cuDNN; `run.py` adds NVIDIA DLL folders from the virtual environment to the process search path. GPU setup varies by driver and CUDA runtime, so verify actual GPU usage rather than assuming installation enables acceleration.

Whisper weights and Ollama models are downloaded separately from this repository. Do not commit model directories or virtual environments.

## Mac browser with Windows processing

1. Make the two computers reachable through a trusted private network, such as Tailscale.
2. Configure SSH access to Windows using your own account and key.
3. Start the app on Windows on port `8765` using the Windows launch script.
4. In a Mac terminal, create a local-only forward:

```sh
ssh -N -T -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_WINDOWS_USER@YOUR_WINDOWS_HOST
```

5. Keep that terminal open and visit `http://127.0.0.1:8765` on the Mac.

Use the same port at both ends: the backend validates the WebSocket origin against `CLIP_PORT`. The application and Ollama should remain bound to loopback; public exposure is not part of this setup.

## Troubleshooting

- **Load failed:** check the Python process, then the SSH tunnel and Windows reachability. A successful Tailscale ping does not prove the SSH service is running.
- **Cannot connect to transcription server:** confirm `CLIP_PORT` matches the browser URL, and stop any other active recording. Only one live transcription connection is supported.
- **Notes fail / model not found:** check `ollama list`, `CLIP_OLLAMA_URL`, and the configured model names. Re-run `ollama pull` if model files are missing.
- **Slow first request:** wait for the initial weight download and model load. Later requests can reuse the cache.
- **No screen text:** frame selection and OCR require visible, legible text; camera preview alone does not guarantee usable OCR evidence.

For the optional Transformers backend, unset the provider environment variables and cache `Qwen/Qwen3-1.7B` and `Qwen/Qwen3-Embedding-0.6B` in the Hugging Face hub cache first. `CLIP_MODEL_CACHE` can select an alternative cache root. This path is retained for compatibility; the documented launch scripts use Ollama.
