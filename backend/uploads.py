"""Local file decoding with PyAV, using the shared faster-whisper model."""
import asyncio
import shutil
import wave
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 3600
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


def decode_audio(source, target, cancelled=lambda: False):
    import av
    count = 0
    try:
        with av.open(str(source)) as container:
            if not container.streams.audio:
                raise ValueError("这个视频没有音轨，请选择包含讲话声音的视频。")
            if container.duration and container.duration / av.time_base > MAX_SECONDS + 1:
                raise ValueError("第一版支持最长 60 分钟的视频。")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            with wave.open(str(target), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16000)
                for frame in container.decode(audio=0):
                    if cancelled():
                        raise ValueError("处理已取消")
                    for converted in resampler.resample(frame):
                        count += converted.samples
                        if count > MAX_SECONDS * 16000:
                            raise ValueError("第一版支持最长 60 分钟的视频。")
                        out.writeframesraw(converted.to_ndarray().tobytes())
                for converted in resampler.resample(None):
                    count += converted.samples
                    if count > MAX_SECONDS * 16000:
                        raise ValueError("第一版支持最长 60 分钟的视频。")
                    out.writeframesraw(converted.to_ndarray().tobytes())
        if not count:
            raise ValueError("视频音轨为空，无法转录。")
        return count / 16000
    except av.error.FFmpegError as exc:
        raise ValueError("无法读取这个视频，请确认文件完整，或转换为 MP4 后重试。") from exc
    except (ValueError, OSError):
        raise
    except Exception as exc:
        raise ValueError("无法读取这个视频，请确认文件完整，或转换为 MP4 后重试。") from exc


async def process_upload(s, directory, ensure_engine, current, update_summary):
    directory = Path(directory)
    try:
        s.status = "processing"
        s.progress = {"stage": "decoding"}
        has_audio = True
        try:
            duration = await asyncio.to_thread(decode_audio, directory / "source", directory / "audio.wav", lambda: s.cancelled)
        except ValueError as exc:
            if "没有音轨" not in str(exc) or not s.visual_enabled:
                raise
            import av
            with av.open(str(directory / "source")) as container:
                duration = float(container.duration or 0) / av.time_base
            if not duration or duration > MAX_SECONDS:
                raise ValueError("无法确认视频长度，或视频超过 60 分钟。")
            has_audio = False
        if s.visual_enabled and current(s):
            from vision import scan_video, add_observation, video_duration
            loop = asyncio.get_running_loop()
            s.visual_status = "processing"
            s.progress = {"stage": "vision", "duration": duration, "processed_seconds": 0}
            def accept(row):
                if current(s):
                    add_observation(s, row)
            def progress(seconds):
                if current(s):
                    s.progress["processed_seconds"] = seconds
            def scan():
                picture_duration = video_duration(directory / "source")
                loop.call_soon_threadsafe(lambda: s.progress.update(duration=picture_duration))
                scan_video(directory / "source", picture_duration,
                           lambda row: loop.call_soon_threadsafe(accept, row),
                           lambda: s.cancelled,
                           lambda seconds: loop.call_soon_threadsafe(progress, seconds))
            scan_job = asyncio.create_task(asyncio.to_thread(scan))
            try:
                await asyncio.shield(scan_job)
                s.visual_status = "ready" if any(r["text"] for r in s.visuals) else "no_text"
            except asyncio.CancelledError:
                s.cancelled = True
                await asyncio.shield(scan_job)
                raise
            except Exception as exc:
                s.visual_status = "error"
                s.visual_error = f"画面文字识别未完成：{exc}；仍可查看语音结果。"
        elif not s.visual_enabled:
            s.visual_status = "disabled"
        if not current(s):
            return
        s.progress = {"stage": "loading", "duration": duration, "processed_seconds": 0}
        if has_audio:
            engine = await ensure_engine(s.language)
            if not current(s):
                return
            if getattr(engine.asr, "backend_choice", None) != "faster-whisper":
                raise ValueError("上传模式目前需要 faster-whisper 后端，请使用默认配置启动。")
            s.progress["stage"] = "transcribing"
            queue = asyncio.Queue(maxsize=8)
            loop = asyncio.get_running_loop()

            def emit(value):
                if s.cancelled:
                    return False
                future = asyncio.run_coroutine_threadsafe(queue.put(value), loop)
                while not s.cancelled:
                    try:
                        future.result(timeout=.2)
                        return True
                    except FutureTimeout:
                        pass
                future.cancel()
                return False

            def transcribe():
                try:
                    # PyAV already decoded/resampled the file above. Pass samples to
                    # faster-whisper to avoid its second, version-sensitive av.open.
                    import numpy as np
                    with wave.open(str(directory / "audio.wav"), "rb") as wav:
                        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
                    segments, _ = engine.asr.model.transcribe(
                        audio, language=s.language,
                        beam_size=5, vad_filter=True, condition_on_previous_text=True,
                    )
                    for segment in segments:
                        if s.cancelled:
                            break
                        item = {"start": segment.start, "end": segment.end, "text": segment.text, "speaker": 1}
                        if not emit(("segment", item)):
                            break
                except Exception as exc:
                    emit(("error", str(exc)))
                finally:
                    emit(("end", None))

            producer = asyncio.create_task(asyncio.to_thread(transcribe))
            error = None
            try:
                while True:
                    try:
                        kind, item = await asyncio.wait_for(queue.get(), .5)
                    except asyncio.TimeoutError:
                        if producer.done():
                            break
                        continue
                    if kind == "end":
                        break
                    if kind == "error":
                        error = item
                    elif current(s):
                        s.merge({"lines": [item]})
                        s.progress["processed_seconds"] = min(duration, item["end"])
                await asyncio.shield(producer)
            finally:
                if not producer.done():
                    s.cancelled = True
                    await asyncio.shield(producer)
            if error:
                raise ValueError(error)
            if not current(s):
                return
        s.progress["processed_seconds"] = duration
        if not s.evidence_rows():
            raise ValueError("没有识别到讲话或画面文字，请确认音量和板书清晰度。")
        s.status = "finalizing"
        s.progress["stage"] = "summarizing"
        await update_summary(s, True)
        # If an interim summary was in progress, wait for its queued tail update.
        while current(s) and (s.summary_status == "generating" or s.final_summary_pending):
            await asyncio.sleep(.1)
        if current(s):
            s.status = "completed"
            s.progress["stage"] = "done" if s.summary_status == "ready" else "summary_error"
    except Exception as exc:
        if current(s):
            s.status = "failed"
            s.error = f"视频处理未完成：{exc}"
            s.progress["stage"] = "error"
    finally:
        await asyncio.to_thread(shutil.rmtree, directory, True)
