"""Small integration contracts around WhisperLiveKit's full-state messages."""
import math
from dataclasses import dataclass, field
from uuid import uuid4


def seconds(value):
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        parts = str(value).split(":")
        number = sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))
    if not math.isfinite(number) or number < 0:
        raise ValueError("Invalid transcript timestamp")
    return number


def timestamp(value):
    value = int(value)
    return f"{value // 60:02}:{value % 60:02}"


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "新的演讲记录"
    language: str = "zh"
    status: str = "idle"
    source: str = "live"
    filename: str = ""
    progress: dict = field(default_factory=dict)
    cancelled: bool = False
    visual_enabled: bool = True
    visuals: list = field(default_factory=list)
    visual_status: str = "waiting"
    visual_error: str = ""
    visual_limit_reached: bool = False
    last_visual_at: float = -100
    segments: dict = field(default_factory=dict)
    partial: str = ""
    revision: int = 0
    summary: dict = field(default_factory=dict)
    summary_revision: int = -1
    summary_status: str = "waiting"
    final_summary_pending: bool = False
    error: str = ""
    qa: list = field(default_factory=list)

    def merge(self, payload):
        changed = False
        for line in payload.get("lines", []):
            if line.get("speaker") in (0, -2):
                continue
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            start, end = seconds(line["start"]), seconds(line["end"])
            if end < start:
                raise ValueError("Transcript end precedes start")
            key = f"s{round(start * 1000)}"
            row = {"id": key, "start": start, "end": end, "text": text}
            if self.segments.get(key) != row:
                self.segments[key] = row
                changed = True
        self.partial = str(payload.get("buffer_transcription") or "")
        if changed:
            self.revision += 1
        return changed

    def rows(self):
        return sorted(self.segments.values(), key=lambda row: (row["start"], row["end"]))

    def evidence_rows(self):
        speech = [{**r, "kind": "speech"} for r in self.rows()]
        visual = [{k: r[k] for k in ("id", "start", "end", "text", "kind")} for r in self.visuals if r["text"]]
        return sorted(speech + visual, key=lambda r: (r["start"], r["end"]))

    def view(self):
        return {"id": self.id, "title": self.title, "language": self.language,
                "source": self.source, "filename": self.filename, "progress": self.progress,
                "visual_enabled": self.visual_enabled, "visuals": self.visuals, "visual_status": self.visual_status,
                "visual_error": self.visual_error, "visual_limit_reached": self.visual_limit_reached,
                "status": self.status, "segments": self.rows(), "partial": self.partial,
                "revision": self.revision, "summary": self.summary,
                "summary_revision": self.summary_revision, "summary_status": self.summary_status,
                "error": self.error, "qa": self.qa}

    def markdown(self):
        report = f"# {self.title}\n\n## 累计摘要\n{self.summary.get('summary', '尚未生成')}\n\n## 重点\n"
        report += "\n".join(f"- {x}" for x in self.summary.get("highlights", []))
        report += "\n\n## 转录\n" + "\n".join(
            f"[{timestamp(r['start'])}–{timestamp(r['end'])}] {r['text']}" for r in self.rows())
        report += "\n\n## 画面文字（OCR，需核对原图）\n" + "\n".join(
            f"[{timestamp(r['start'])}] {r['text']}" for r in self.visuals if r['text'])
        if self.summary.get('visual_summary'):
            report += "\n\n## 板书与画面总结\n" + self.summary['visual_summary']
        return report
