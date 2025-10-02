import os
import shutil
import subprocess
from typing import Optional

FFMPEG = shutil.which("ffmpeg")


def have_ffmpeg() -> bool:
    return FFMPEG is not None


def _detect_hw_encoder() -> tuple[str, list[str]]:
    """Return (codec, extra_args) picking best available HW encoder.
    Preference: NVENC > QSV > VAAPI > CPU (libx264)
    """
    # Allow override via env
    override = os.getenv("JVA_FFMPEG_CODEC")
    if override:
        return override, []

    # Windows/NVIDIA
    if shutil.which("nvidia-smi"):
        return "h264_nvenc", ["-preset", "p4", "-tune", "hq"]

    # Intel QuickSync
    if os.name == "nt" or os.path.exists("/dev/dri/renderD128"):
        # Try to assume QSV is available on Windows with Intel or Linux with iGPU
        return "h264_qsv", ["-global_quality", "22"]

    # VAAPI (Linux)
    if shutil.which("vainfo"):
        return "h264_vaapi", ["-vaapi_device", "/dev/dri/renderD128", "-vf", "format=nv12,hwupload"]

    # Fallback CPU
    return "libx264", ["-preset", "medium"]


def encode_hw(in_path: str, out_path: str, crf_or_bitrate: str = "6M") -> bool:
    """Transcode MP4 using best available HW encoder.
    crf_or_bitrate: if endswith 'M' or 'k' use as bitrate; else treat as CRF/qp.
    """
    if not have_ffmpeg():
        return False

    codec, extra = _detect_hw_encoder()

    # Decide rate control args
    rate_args: list[str]
    if crf_or_bitrate.lower().endswith(("m", "k")):
        rate_args = ["-b:v", crf_or_bitrate]
    else:
        # CRF/QP-like, try to map to reasonable flags per codec
        if codec in ("h264_nvenc", "h264_qsv"):
            rate_args = ["-cq", crf_or_bitrate]
        elif codec == "libx264":
            rate_args = ["-crf", crf_or_bitrate]
        else:
            rate_args = []

    cmd = [
        FFMPEG,
        "-y",
        "-i", in_path,
        "-c:v", codec,
        *extra,
        *rate_args,
        "-c:a", "copy",
        out_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        # Fallback to CPU if HW fails
        if codec != "libx264":
            try:
                subprocess.run([
                    FFMPEG, "-y", "-i", in_path,
                    "-c:v", "libx264", "-preset", "medium",
                    "-c:a", "copy", out_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True
            except subprocess.CalledProcessError:
                return False
        return False
