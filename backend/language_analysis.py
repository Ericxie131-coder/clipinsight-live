from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


DEFAULT_LLM_MODEL = "Qwen/Qwen3-1.7B"
REQUIRED_ANALYSIS_KEYS = {
    "title",
    "summary",
    "key_points",
    "topics",
    "action_items",
    "entities",
    "languages",
    "follow_up_questions",
}
LIST_ANALYSIS_KEYS = {
    "key_points",
    "topics",
    "action_items",
    "entities",
    "languages",
    "follow_up_questions",
}


def select_device(device: str | None = None) -> str:
    if device is not None:
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but no CUDA device is available")
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but no Apple GPU is available")
        return device
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class LocalLLM:
    def __init__(self, model_name: str = DEFAULT_LLM_MODEL, device: str | None = None):
        self.model_name = model_name
        self.device = select_device(device)
        self.tokenizer: Any | None = None
        self.model: Any | None = None

    def load(self) -> None:
        if self.model is not None:
            return
        dtype = torch.float16 if self.device.startswith("cuda") or self.device == "mps" else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        self.model.to(self.device)
        self.model.eval()

    def unload(self) -> None:
        self.model = None
        self.tokenizer = None
        if self.device.startswith("cuda"):
            torch.cuda.empty_cache()
        if self.device == "mps":
            torch.mps.empty_cache()

    def generate(
        self,
        messages: list[dict[str, str]],
        max_new_tokens: int = 512,
    ) -> str:
        self.load()
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated_ids = output_ids[0, inputs["input_ids"].shape[1] :]
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def transcript_to_text(transcript: dict[str, Any] | list[dict[str, Any]]) -> str:
    segments = transcript["segments"] if isinstance(transcript, dict) else transcript
    return "\n".join(
        f"[{float(segment['start']):.2f}-{float(segment['end']):.2f}] {segment['text']}"
        for segment in segments
    )


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The model response did not contain a JSON object")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The model response contained invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TypeError("The model response must be a JSON object")
    return parsed


def validate_analysis(data: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_ANALYSIS_KEYS - data.keys())
    if missing:
        raise ValueError(f"Missing required analysis keys: {', '.join(missing)}")
    if not isinstance(data["title"], str) or not data["title"].strip():
        raise TypeError("title must be a non-empty string")
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        raise TypeError("summary must be a non-empty string")
    for key in LIST_ANALYSIS_KEYS:
        if not isinstance(data[key], list):
            raise TypeError(f"{key} must be a list")
        if not all(isinstance(item, str) and item.strip() for item in data[key]):
            raise TypeError(f"Every item in {key} must be a non-empty string")
    if not 3 <= len(data["key_points"]) <= 6:
        raise ValueError("key_points must contain between 3 and 6 items")
    if not data["topics"]:
        raise ValueError("topics must contain at least one item")
    if not data["languages"]:
        raise ValueError("languages must contain at least one item")
    if not data["follow_up_questions"]:
        raise ValueError("follow_up_questions must contain at least one item")
    return {key: data[key] for key in sorted(REQUIRED_ANALYSIS_KEYS)}


def analyze_transcript(
    transcript_text: str,
    llm: LocalLLM | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        raise ValueError("transcript_text must be a non-empty string")
    runtime = llm or LocalLLM()
    system = (
        "You analyze timestamped media transcripts. Use only information in the transcript. "
        "Do not invent names, decisions, or action items. Return one valid JSON object and no other text."
    )
    schema = {
        "title": "short string",
        "summary": "concise string",
        "key_points": ["3 to 6 strings"],
        "topics": ["strings"],
        "action_items": ["strings or an empty list"],
        "entities": ["important people or organizations as strings"],
        "languages": ["observed languages"],
        "follow_up_questions": ["short questions"],
    }
    user = (
        f"Create the structured report using this exact schema:\n{json.dumps(schema)}\n\n"
        f"Transcript:\n{transcript_text}"
    )
    error: Exception | None = None
    response = ""
    for attempt in range(retries + 1):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if attempt:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The previous response failed validation: {error}. "
                        f"Correct it and return only valid JSON. Previous response:\n{response}"
                    ),
                }
            )
        response = runtime.generate(messages, max_new_tokens=700)
        try:
            return validate_analysis(extract_json_object(response))
        except (ValueError, TypeError) as exc:
            error = exc
    raise RuntimeError(f"Structured analysis failed after {retries + 1} attempts: {error}")


def save_analysis(data: dict[str, Any], output_path: str | Path) -> Path:
    validated = validate_analysis(data)
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
