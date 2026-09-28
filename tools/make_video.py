"""Assemble the demo video: screen recording + synthetic narration + captions + quiet, ducked background music.

Inputs (from `python tools/capture_demo.py`): .cache/video/raw.webm, segments.json, nar_*.wav.
Music: .cache/music/Airport Lounge.mp3 — refuses any file whose sha256 differs from the verified one
(docs/media-licenses.md).
Outputs: site/media/demo.mp4 (captions burned into a separate band below the app, so they never cover the document),
site/media/demo.en.vtt, site/media/demo-poster.png, site/media/demo.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
V = ROOT / ".cache" / "video"
OUT = ROOT / "site" / "media"
MUSIC = ROOT / ".cache" / "music" / "Airport Lounge.mp3"
MUSIC_SHA = "e20d316b541c72690a3b0311c9f3d40fd00717359ab7567d7df82a9316c1dec4"
MUSIC_GAIN = 0.20          # background level before ducking; measured result is recorded in demo.json
RATE = 48000
DELAY = 0.15               # narration starts just after the on-screen action
W, H, BAND = 1280, 720, 96  # caption band height below the recorded page


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    t = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", p.stderr)[-1]
    return int(t[0]) * 3600 + int(t[1]) * 60 + float(t[2])


def read_wav(path: Path) -> np.ndarray:
    """Mono float32 at RATE; ffmpeg resamples (no SciPy dependency)."""
    out = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def chunks(text: str, limit: int = 80) -> list[str]:
    """Caption lines at sentence/clause boundaries, at most `limit` characters (one line each)."""
    parts = re.split(r"(?<=[.!?:;])\s+|(?<=,)\s+(?=\S)", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > limit:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    final = []
    for c in out:
        while len(c) > limit:
            cut = c.rfind(" ", 0, limit)
            final.append(c[:cut])
            c = c[cut + 1:]
        final.append(c)
    return final


# Captions use readable spellings where the narration spells words out for the voice.
CAPTION_FIXES = {"Qwen three V L": "Qwen3-VL", "Rapid OCR": "RapidOCR", "R X, dash, capital I, zero seven six one eight": "RX-I07618",
                 "one hundred and seventy of one hundred and eighty": "170 of 180", "one hundred and sixty seven": "167",
                 "vision language model": "vision-language model"}


def caption_text(t: str) -> str:
    for a, b in CAPTION_FIXES.items():
        t = t.replace(a, b)
    return t


def ts(t: float, sep: str = ".") -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)):03d}"


def level_db(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0
    return round(20 * np.log10(rms), 1) if rms > 0 else -120.0


def main() -> int:
    if not MUSIC.exists() or hashlib.sha256(MUSIC.read_bytes()).hexdigest() != MUSIC_SHA:
        raise SystemExit("music file missing or not the verified recording (see docs/media-licenses.md)")
    meta = json.loads((V / "segments.json").read_text(encoding="utf-8"))
    raw = V / "raw.webm"
    dur = duration(raw)
    n = int(dur * RATE) + RATE
    voice = np.zeros(n, np.float32)
    cues = []
    for seg in meta["segments"]:
        key = seg["key"]
        x = read_wav(V / f"nar_{key}.wav")
        start = seg["start"] + DELAY
        s = int(start * RATE)
        voice[s:s + len(x)] += x[: max(0, n - s)]
        lines = chunks(caption_text(meta["texts"][key]))
        tot = sum(len(line) for line in lines)
        t = start
        for line in lines:
            d = (len(x) / RATE) * len(line) / tot
            cues.append((t, t + d, line))
            t += d
    # Long silent stretches are the live extraction running; say so for muted viewers.
    cues.sort()
    for (a0, a1, _), (b0, _, _) in zip(cues, cues[1:]):
        if b0 - a1 > 6:
            cues.append((a1 + 0.3, b0 - 0.2, "[Live extraction running on this laptop. The wait is not cut.]"))
    cues.sort()
    peak = float(np.abs(voice).max())
    voice = (voice / peak * 0.89).astype(np.float32)
    import soundfile as sf

    sf.write(str(V / "voice.wav"), voice[: int(dur * RATE)], RATE, subtype="PCM_16")

    OUT.mkdir(parents=True, exist_ok=True)
    vtt, srt = ["WEBVTT", ""], []
    for i, (a, b, text) in enumerate(cues, 1):
        vtt += [str(i), f"{ts(a)} --> {ts(b)}", text, ""]
        srt += [str(i), f"{ts(a, ',')} --> {ts(b, ',')}", text, ""]
    (OUT / "demo.en.vtt").write_text("\n".join(vtt), encoding="utf-8")
    (V / "captions.srt").write_text("\n".join(srt), encoding="utf-8")

    fade_out = max(0.0, dur - 4.0)
    # libass scales SRT styles from a 288-px-high script: FontSize 8.5 ≈ 26 px at 816 px; the band is 96 px tall.
    style = ("FontName=Segoe UI,FontSize=8.5,PrimaryColour=&H00FFFFFF,BorderStyle=1,Outline=0,Shadow=0,"
             "MarginV=11,Alignment=2")
    filt = (
        f"[0:v]pad={W}:{H + BAND}:0:0:color=0x08111F,subtitles=captions.srt:force_style='{style}',format=yuv420p[v];"
        f"[2:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,volume={MUSIC_GAIN},afade=t=in:d=3,afade=t=out:st={fade_out:.2f}:d=4,"
        "aformat=channel_layouts=stereo[m];"
        "[1:a]aformat=channel_layouts=stereo,asplit=2[vo][sc];"
        "[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=700[duck];"
        "[vo][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
    )
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", "raw.webm", "-i", "voice.wav", "-i", str(MUSIC),
                    "-filter_complex", filt, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                    "-r", "25", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{dur:.2f}", str(OUT / "demo.mp4")],
                   cwd=V, check=True)

    # Measure the music under the voice: render the ducked music alone and compare levels while narration plays.
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", "voice.wav", "-i", str(MUSIC), "-filter_complex",
                    f"[1:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,volume={MUSIC_GAIN},aformat=channel_layouts=stereo[m];"
                    "[0:a]aformat=channel_layouts=stereo[sc];[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=700,"
                    "aformat=channel_layouts=mono[o]", "-map", "[o]", "-ar", str(RATE), "music_ducked.wav"], cwd=V, check=True)
    mus, _ = sf.read(str(V / "music_ducked.wav"), dtype="float32")
    m = min(len(mus), int(dur * RATE))
    v = voice[:m]
    speaking = np.abs(v) > 0.02
    win = int(0.25 * RATE)
    c = np.concatenate([[0], np.cumsum(speaking)])  # moving window via cumulative sum (O(n))
    idx = np.arange(m)
    mask = (c[np.minimum(idx + win // 2, m)] - c[np.maximum(idx - win // 2, 0)]) > 0
    levels = {"voice_dbfs_while_speaking": level_db(v[mask]), "music_dbfs_under_voice": level_db(mus[:m][mask]),
              "music_dbfs_without_voice": level_db(mus[:m][~mask])}
    levels["music_below_voice_db"] = round(levels["voice_dbfs_while_speaking"] - levels["music_dbfs_under_voice"], 1)

    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-ss", "1.5", "-i", str(OUT / "demo.mp4"),
                    "-frames:v", "1", str(OUT / "demo-poster.png")], check=True)
    info = {
        "file": "site/media/demo.mp4", "duration_s": round(duration(OUT / "demo.mp4"), 2),
        "sha256": hashlib.sha256((OUT / "demo.mp4").read_bytes()).hexdigest(), "captions": len(cues),
        "source": "screen recording of the local application (Playwright, Chromium) during one live run on sample r30",
        "live_run": meta.get("live_run"),
        "reviewer_actions": "scripted (Playwright); extraction is live local inference",
        "narration": "synthetic, Kokoro-82M v1.0 (Apache-2.0) via kokoro-onnx, voice af_heart",
        "audio_levels": levels,
        "music": {"track": "Airport Lounge", "creator": "Kevin MacLeod",
                  "source": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Airport%20Lounge.mp3",
                  "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "sha256_of_source": MUSIC_SHA,
                  "changes": f"excerpt from the start trimmed to the video length, volume x{MUSIC_GAIN}, side-chain ducked under the "
                             "narration, 3 s fade-in, 4 s fade-out, re-encoded to AAC and mixed with the narration"},
    }
    (OUT / "demo.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
