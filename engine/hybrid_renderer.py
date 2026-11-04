#!/usr/bin/env python3
"""Manifest-driven hybrid documentary renderer (images/video + licensed Hindi Kokoro narration)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

FPS = 30
MAX_ASSET_BYTES = 80 * 1024 * 1024
ALLOWED_LICENSES = ("cc0", "public domain", "cc by", "cc-by")


def commercially_usable_license(value: str) -> bool:
    label = re.sub(r"\\s+", " ", value.strip().lower())
    if any(term in label for term in ("noncommercial", "non-commercial", "no derivatives", "no-derivatives", "sampling")):
        return False
    if re.search(r"(^|[\\s-])(nc|nd)(?=[\\s-]|$)", label):
        return False
    return any(label.startswith(item) for item in ALLOWED_LICENSES) or label.startswith(("cc by-sa", "cc-by-sa"))


def validate_project(project: dict) -> None:
    if not isinstance(project, dict):
        raise ValueError("Project must be a JSON object")
    if not str(project.get("title", "")).strip():
        raise ValueError("Project title is required")
    if project.get("format", "short") not in ("short", "long"):
        raise ValueError("format must be short or long")
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("At least one scene is required")
    total = 0.0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} must be an object")
        duration = float(scene.get("duration", 0))
        if duration <= 0 or duration > 90:
            raise ValueError(f"Scene {index} duration must be between 0 and 90 seconds")
        total += duration
        if scene.get("kind") not in ("image", "video"):
            raise ValueError(f"Scene {index} kind must be image or video")
        parsed = urlparse(str(scene.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"Scene {index} requires an HTTPS asset URL")
        license_name = str(scene.get("license", "")).strip().lower()
        if not commercially_usable_license(license_name):
            raise ValueError(f"Scene {index} has an unsupported or non-commercial license")
        if not str(scene.get("source_page", "")).startswith("https://"):
            raise ValueError(f"Scene {index} requires an HTTPS source_page for attribution")
        if not str(scene.get("credit", "")).strip():
            raise ValueError(f"Scene {index} requires creator attribution")
    limit = 90 if project.get("format", "short") == "short" else 900
    if total > limit:
        raise ValueError(f"Total scene duration exceeds {limit} seconds for {project.get('format', 'short')}")
    if not str(project.get("narration", "")).strip():
        raise ValueError("Narration text is required")


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def sentence_parts(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[।!?])\\s+", text.strip()) if part.strip()]


def write_srt(scenes: list[dict], path: Path) -> None:
    cursor = 0.0
    blocks = []
    index = 1
    for scene in scenes:
        duration = float(scene["duration"])
        text = str(scene.get("narration") or scene.get("caption") or "").strip()
        sentences = sentence_parts(text) or ([text] if text else [])
        weights = [max(1, len(sentence.split())) for sentence in sentences]
        weight_total = sum(weights) or 1
        local_cursor = cursor
        for sentence, weight in zip(sentences, weights):
            sentence_duration = duration * weight / weight_total
            end = local_cursor + sentence_duration
            blocks.append(f"{index}\\n{srt_time(local_cursor)} --> {srt_time(end)}\\n{sentence}\\n")
            local_cursor = end
            index += 1
        cursor += duration
    path.write_text("\\n".join(blocks), encoding="utf-8")


def run(command: list[str], timeout: int = 300) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def download_asset(scene: dict, destination: Path) -> None:
    request = urllib.request.Request(
        scene["url"],
        headers={"User-Agent": "VideoFactory/2.1 (hybrid documentary renderer)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        final_url = response.geturl()
        if urlparse(final_url).scheme != "https":
            raise ValueError("Asset redirect left HTTPS")
        data = response.read(MAX_ASSET_BYTES + 1)
        if len(data) > MAX_ASSET_BYTES:
            raise ValueError("Asset exceeds 80 MiB download limit")
        content_type = response.headers.get_content_type()
        expected = "image/" if scene["kind"] == "image" else "video/"
        if not content_type.startswith(expected) and content_type != "application/octet-stream":
            raise ValueError(f"Unexpected asset content type: {content_type}")
    destination.write_bytes(data)
    if not data:
        raise ValueError("Downloaded asset is empty")


def render_segment(scene: dict, source: Path, destination: Path, width: int, height: int) -> None:
    duration = float(scene["duration"])
    scale_crop = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={FPS},format=yuv420p"
    )
    if scene["kind"] == "image":
        command = [
            "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(source),
            "-t", str(duration), "-vf", scale_crop, "-an", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(destination),
        ]
    else:
        command = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source),
            "-t", str(duration), "-vf", scale_crop, "-an", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(destination),
        ]
    run(command, timeout=180)


def synthesize_narration(text: str, destination: Path, voice_gender: str) -> str:
    """Generate Hindi speech locally with Apache-2.0 Kokoro; no external TTS API."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError("Licensed Kokoro TTS dependencies are missing") from exc

    voice_name = "hm_omega" if voice_gender == "male" else "hf_alpha"
    pipeline = KPipeline(lang_code="h")
    chunks = []
    generator = pipeline(
        text,
        voice=voice_name,
        speed=1.0,
        split_pattern=r"(?<=[।!?])\\s+",
    )
    for _, _, audio in generator:
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunk = np.asarray(audio, dtype=np.float32).reshape(-1)
        if chunk.size:
            chunks.append(chunk)
    if not chunks:
        raise RuntimeError("Kokoro returned no Hindi narration audio")
    audio = np.concatenate(chunks)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < 1e-5:
        raise RuntimeError("Kokoro narration is silent")
    if peak > 0.98:
        audio = audio * (0.98 / peak)
    sf.write(str(destination), audio, 24000, subtype="PCM_16")
    if not destination.exists() or destination.stat().st_size < 1000:
        raise RuntimeError("Kokoro Hindi narration generation failed")
    return voice_name


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return float(result.stdout.strip())


def render_project(project: dict, output: Path, voice_gender: str = "male") -> None:
    validate_project(project)
    if voice_gender not in ("male", "female"):
        raise ValueError("voice_gender must be male or female")
    if not shutil_which("ffmpeg") or not shutil_which("ffprobe"):
        raise RuntimeError("FFmpeg and FFprobe are required")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = (1080, 1920) if project.get("format", "short") == "short" else (1920, 1080)

    with tempfile.TemporaryDirectory(prefix="hybrid-facts-") as temp:
        work = Path(temp)
        segments = []
        credits = [
            "Video Factory — Hindi Facts production",
            f"Title: {project['title']}",
            f"Format: {project.get('format', 'short')}",
            f"Project licence: {project.get('project_license', 'Not specified')}",
        ]
        for index, scene in enumerate(project["scenes"], 1):
            extension = ".mp4" if scene["kind"] == "video" else ".img"
            asset = work / f"asset_{index:03d}{extension}"
            segment = work / f"segment_{index:03d}.mp4"
            download_asset(scene, asset)
            render_segment(scene, asset, segment, width, height)
            segments.append(segment)
            credits.append(
                f"Scene {index}: {scene['credit']} | {scene['license']} | "
                f"{scene['source_page']} | {scene.get('visual_note', '')}"
            )

        concat_file = work / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{p.as_posix()}'\\n" for p in segments), encoding="utf-8"
        )
        silent_video = work / "silent.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(silent_video)], timeout=300)

        narration_file = work / "narration.wav"
        voice_name = synthesize_narration(project["narration"], narration_file, voice_gender)
        narration_duration = media_duration(narration_file)
        total_duration = sum(float(s["duration"]) for s in project["scenes"])
        tempo = narration_duration / total_duration
        if not 0.75 <= tempo <= 1.25:
            raise RuntimeError(
                f"Narration duration {narration_duration:.1f}s is outside safe fit range "
                f"for {total_duration:.1f}s video; revise script or timing"
            )
        audio_filter = (
            f"[1:a]aresample=48000,atempo={tempo:.6f},apad,"
            f"atrim=0:{total_duration:.3f},volume=1.0[a]"
        )
        run(["ffmpeg", "-y", "-i", str(silent_video), "-i", str(narration_file),
             "-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
             str(output)], timeout=300)
        write_srt(project["scenes"], output.with_suffix(".srt"))
        credits.append(
            f"Narration: Kokoro-82M Hindi voice {voice_name} | Apache-2.0 | "
            "https://huggingface.co/hexgrad/Kokoro-82M"
        )
        output.with_name("credits.txt").write_text("\\n".join(credits) + "\\n", encoding="utf-8")


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a hybrid documentary from a scene manifest")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/hybrid-facts.mp4"))
    parser.add_argument("--voice-gender", choices=("male", "female"), default="male")
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8"))
    render_project(project, args.output, args.voice_gender)
    print(f"Rendered {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
