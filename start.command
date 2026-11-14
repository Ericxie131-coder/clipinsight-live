#!/bin/zsh
set -eu
cd "${0:A:h}"
export CLIP_LLM_PROVIDER="${CLIP_LLM_PROVIDER:-ollama}"
export CLIP_EMBEDDING_PROVIDER="${CLIP_EMBEDDING_PROVIDER:-ollama}"
export CLIP_OLLAMA_URL="${CLIP_OLLAMA_URL:-http://127.0.0.1:11434}"
export CLIP_OLLAMA_MODEL="${CLIP_OLLAMA_MODEL:-qwen3:1.7b}"
export CLIP_OLLAMA_EMBED_MODEL="${CLIP_OLLAMA_EMBED_MODEL:-qwen3-embedding:0.6b}"
exec .venv/bin/python run.py
