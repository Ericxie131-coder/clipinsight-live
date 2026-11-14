"""Launch without modifying the original project's environment."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT / "backend"))
_dll_handles = []
if os.name == "nt":
    # CTranslate2 needs the NVIDIA runtime DLLs installed inside this venv.
    for folder in (Path(sys.prefix) / "Lib/site-packages/nvidia").glob("*/bin"):
        _dll_handles.append(os.add_dll_directory(str(folder)))
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / ".runtime/numba"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".runtime/matplotlib"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
if (ROOT / ".deps/certifi/cacert.pem").exists():
    os.environ.setdefault("SSL_CERT_FILE", str(ROOT / ".deps/certifi/cacert.pem"))
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.environ.get("CLIP_PORT", "8765")), log_level="info", access_log=False)
