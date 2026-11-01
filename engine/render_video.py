#!/usr/bin/env python3
"""Cloud-only vertical short video renderer. No API keys or local services."""
from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?।])\s+", text.strip()) if p.strip()]
    return parts or [text.strip() or "Welcome"]


def make_scenes(text: str, max_scenes: int = 7) -> list[str]:
    sentences = split_sentences(text)
    if len(sentences) <= max_scenes:
        return sentences
    groups = [[] for _ in range(max_scenes)]
    for i, sentence in enumerate(sentences):
        groups[min(i * max_scenes // len(sentences), max_scenes - 1)].append(sentence)
    return [" ".join(group) for group in groups if group]


def font_path(language: str, bold: bool = False) -> str:
    candidates = (
        ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if language == "hi" and bold else
        ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        if language == "hi" else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
              max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_scene(title: str, caption: str, index: int, total: int,
               language: str, destination: Path) -> None:
    image = Image.new("RGB", (W, H))
    pixels = image.load()
    palettes = [(13, 25, 48), (22, 35, 65), (25, 30, 55), (15, 42, 58)]
    base = palettes[index % len(palettes)]
    for y in range(H):
        t = y / H
        color = tuple(int(c * (1 - 0.48 * t) + (c + 22) * 0.48 * t) for c in base)
        for x in range(W):
            pixels[x, y] = color

    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((650, -220, 1320, 450), fill=(60, 160, 220, 35))
    draw.ellipse((-280, 1250, 420, 1950), fill=(90, 110, 240, 28))
    draw.rounded_rectangle((70, 110, 1010, 1810), radius=48,
                           outline=(255, 255, 255, 42), width=3)
    draw.rounded_rectangle((100, 145, 980, 158), radius=6,
                           fill=(100, 220, 210, 220))

    title_font = ImageFont.truetype(font_path(language, True), 58) if font_path(language, True) else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path(language), 57) if font_path(language) else ImageFont.load_default()
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 29)

    draw.text((125, 225), title[:70], font=title_font, fill=(255, 255, 255, 255))
    draw.text((125, 390), f"SCENE {index + 1:02d} / {total:02d}",
              font=small_font, fill=(130, 230, 220, 255))

    lines = wrap_text(draw, caption, body_font, 800)
    line_height = 100
    block_height = len(lines) * line_height
    y = max(620, (H - block_height) // 2)
    for line in lines[:9]:
        draw.text((125, y), line, font=body_font, fill=(248, 250, 255, 255),
                  stroke_width=1, stroke_fill=(15, 25, 45, 255))
        y += line_height

    draw.rounded_rectangle((125, 1570, 955, 1579), radius=5,
                           fill=(255, 255, 255, 65))
    draw.rounded_rectangle((125, 1570, 125 + int(830 * (index + 1) / total), 1579),
                           radius=5, fill=(100, 220, 210, 255))
    draw.text((125, 1640), "VIDEO FACTORY  •  SHORTS", font=small_font,
              fill=(195, 210, 230, 220))
    image.save(destination, quality=95)


def make_ambient_audio(path: Path, duration: float, sample_rate: int = 22050) -> None:
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        chunk = bytearray()
        for i in range(frames):
            t = i / sample_rate
            fade = min(1.0, t / 1.5, max(0.0, (duration - t) / 1.5))
            sample = (0.035 * math.sin(2 * math.pi * 110 * t) +
                      0.018 * math.sin(2 * math.pi * 164.81 * t)) * fade
            value = max(-32767, min(32767, int(sample * 32767)))
            chunk.extend(int(value).to_bytes(2, "little", signed=True))
            if len(chunk) >= 8192:
                wav.writeframes(chunk)
                chunk.clear()
        if chunk:
            wav.writeframes(chunk)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def render(title: str, script: str, language: str, duration: int, output: Path) -> None:
    if not 15 <= duration <= 60:
        raise ValueError("duration must be between 15 and 60 seconds")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed on this runner")
    scenes = make_scenes(script)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video-factory-") as temp:
        work = Path(temp)
        concat = work / "scenes.txt"
        scene_duration = duration / len(scenes)
        with concat.open("w", encoding="utf-8") as listing:
            for i, caption in enumerate(scenes):
                frame = work / f"scene_{i:03d}.png"
                draw_scene(title, caption, i, len(scenes), language, frame)
                listing.write(f"file '{frame.as_posix()}'\n")
                listing.write(f"duration {scene_duration:.4f}\n")
            listing.write(f"file '{(work / f'scene_{len(scenes)-1:03d}.png').as_posix()}'\n")

        voice = work / "voice.wav"
        ambient = work / "ambient.wav"
        make_ambient_audio(ambient, duration)
        voice_created = False
        if shutil.which("espeak-ng"):
            voice_name = "hi" if language == "hi" else "en"
            result = subprocess.run(
                ["espeak-ng", "-v", voice_name, "-s", "145", "-w", str(voice), script],
                capture_output=True, text=True
            )
            voice_created = result.returncode == 0 and voice.exists()

        if voice_created:
            audio_filter = (
                f"[1:a]aresample=22050,apad,atrim=0:{duration},volume=1.0[v];"
                f"[2:a]volume=0.20[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]"
            )
            command = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(voice), "-i", str(ambient), "-filter_complex", audio_filter,
                "-map", "0:v:0", "-map", "[a]", "-vf", f"fps={FPS},format=yuv420p",
                "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "24", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str(output)
            ]
        else:
            command = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(ambient), "-map", "0:v:0", "-map", "1:a:0",
                "-vf", f"fps={FPS},format=yuv420p", "-t", str(duration),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output)
            ]
        run(command)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a vertical short video")
    parser.add_argument("--title", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--language", choices=["hi", "en"], default="hi")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("output/video.mp4"))
    args = parser.parse_args()
    render(args.title, args.script, args.language, args.duration, args.output)
    print(f"Created {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
