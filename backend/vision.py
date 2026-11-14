"""Local board/slide OCR. Change score follows the original vision_extension.py.
Images are evidence for text extraction, not general scene or emotion recognition.
"""
import base64
import threading

_ocr = None
_lock = threading.Lock()
MAX_FRAMES = 120


def video_duration(path):
    import av
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError('这个文件没有可识别的视频画面。')
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else float(container.duration or 0) / av.time_base
        if not 0 < duration <= 3600:
            raise ValueError('无法确认视频长度，或视频超过 60 分钟。')
        return duration


def features(frame):
    import cv2
    small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist, cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def change_score(previous, current):
    import cv2
    import numpy as np
    return .7 * cv2.compareHist(previous[0], current[0], cv2.HISTCMP_BHATTACHARYYA) + .3 * float(np.mean(cv2.absdiff(previous[1], current[1]))) / 255


def recognize(frame, seconds):
    import cv2
    global _ocr
    h, w = frame.shape[:2]
    if max(h, w) > 1600:
        frame = cv2.resize(frame, (round(w * 1600 / max(h, w)), round(h * 1600 / max(h, w))))
    with _lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, text_score=.65)
        result, _ = _ocr(frame)
    lines = [{"text": str(r[1]), "confidence": round(float(r[2]), 3), "box": r[0]} for r in (result or []) if float(r[2]) >= .65]
    h, w = frame.shape[:2]
    thumb = cv2.resize(frame, (480, max(1, round(h * 480 / w))))
    ok, jpeg = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 65])
    return {"id": f"v{round(seconds * 1000)}", "start": round(seconds, 2), "end": round(seconds, 2),
            "text": '\n'.join(line['text'] for line in lines), "lines": lines,
            "image": 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode() if ok else '', "kind": "visual"}


def add_observation(s, row):
    # Repeated slides stay one note; updated board text keeps a new timestamp.
    text = ''.join(row['text'].split()).lower()
    if text:
        for previous in s.visuals[-3:]:
            old = ''.join(previous['text'].split()).lower()
            if old and old == text:
                return False
    elif s.visuals:
        return False
    if len(s.visuals) >= MAX_FRAMES:
        s.visual_limit_reached = True
        return False
    s.visuals.append(row)
    if row['text']:
        s.revision += 1
    return True


def scan_video(path, duration, on_frame, cancelled=lambda: False, on_progress=lambda t: None):
    import av
    interval = max(5., duration / (MAX_FRAMES - 1))
    previous = None
    last_selected = -30.
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError('这个文件没有可识别的视频画面。')
        stream = container.streams.video[0]
        origin = float((stream.start_time or 0) * stream.time_base)
        targets = [i * interval for i in range(min(MAX_FRAMES, int(duration / interval) + 1))]
        for target in targets:
            if cancelled():
                return
            container.seek(int((target + origin) / stream.time_base), stream=stream, backward=True)
            chosen = None
            for frame in container.decode(stream):
                if cancelled():
                    return
                if frame.time is not None and frame.time - origin >= target - .05:
                    chosen = frame
                    break
            if chosen is None:
                continue
            image = chosen.to_ndarray(format='bgr24')
            current = features(image)
            # Sample changed pages and periodically retry subtle board additions.
            if previous is None or change_score(previous, current) > .0008 or target - last_selected >= 20:
                row = recognize(image, max(0., float(chosen.time) - origin))
                if cancelled():
                    return
                on_frame(row)
                last_selected = target
                previous = current
            on_progress(target)
