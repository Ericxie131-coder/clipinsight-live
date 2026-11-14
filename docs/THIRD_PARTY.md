# Third-party components

ClipInsight Live integrates the following projects through their public Python or HTTP interfaces. Dependencies and model weights are installed separately; their licenses and model terms remain applicable.

- [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit): streaming audio processing and transcription policies.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): Whisper inference through CTranslate2.
- [RapidOCR](https://github.com/RapidAI/RapidOCR): OCR inference using PP-OCR models and ONNX Runtime.
- [Ollama](https://github.com/ollama/ollama): local generation and embedding HTTP APIs.
- [Qwen](https://github.com/QwenLM/Qwen3): pretrained text and embedding models.
- [Transformers](https://github.com/huggingface/transformers) and [Sentence Transformers](https://github.com/huggingface/sentence-transformers): optional original local model backend.
- [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/encode/uvicorn), and [PyAV](https://github.com/PyAV-Org/PyAV): backend serving and media decoding.

The original local-model wrapper was carried forward from the author's earlier offline prototype. Frame selection adapts its image-change detection approach. This repository's contribution is the browser workflow, streaming/upload integration, OCR evidence handling, cumulative summaries, retrieval, and deployment orchestration.

The cover image is AI-generated and illustrates the product concept. No Frutiger font files are distributed; the UI uses a system font fallback when that font is unavailable.
