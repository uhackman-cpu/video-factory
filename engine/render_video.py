#!/usr/bin/env python3
"""Cloud-only short-video renderer with free online neural TTS and Commons images."""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

W, H, FPS = 1080, 1920, 30
TEMPLATES = ("animated", "cinematic", "cartoon")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?।])\s+", text.strip()) if p.strip()]
    return parts or [text.strip() or "Welcome"]


def make_scenes(text: str, max_scenes: int = 7) -> list[str]:
    if max_scenes < 1:
        raise ValueError("max_scenes must be at least 1")
    sentences = split_sentences(text)
    if len(sentences) <= max_scenes:
        return sentences
    groups = [[] for _ in range(max_scenes)]
    for i, sentence in enumerate(sentences):
        groups[min(i * max_scenes // len(sentences), max_scenes - 1)].append(sentence)
    return [" ".join(group) for group in groups if group]


def font_path(language: str, bold: bool = False) -> str:
    if language == "hi":
        candidates = (
            ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if bold else
            ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
    return next((candidate for candidate in candidates if Path(candidate).exists()), "")


def load_font(language: str, size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = font_path(language, bold)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
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
    return lines or [""]


def clean_metadata(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value or ""))).strip()


def license_is_commercially_usable(label: str) -> bool:
    normalized = label.lower()
    if any(term in normalized for term in ("noncommercial", "non-commercial", "non commercial", "no derivatives", "no-derivatives", "sampling")):
        return False
    if re.search(r"(^|[\s-])(nc|nd)(?=[\s-]|$)", normalized):
        return False
    return (
        normalized.startswith("cc0")
        or normalized.startswith("public domain")
        or normalized.startswith("pd ")
        or normalized.startswith("cc by")
        or normalized.startswith("creative commons attribution")
    )


def download_commons_background(query: str, destination: Path) -> dict[str, str] | None:
    """Find a Commons image with PD/CC0/CC BY/CC BY-SA terms and save a thumbnail."""
    if not query.strip():
        return None
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query.strip(),
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "1440",
        "format": "json",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "VideoFactory/1.0 (educational short-video builder)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read(2_000_000).decode("utf-8"))

    pages = payload.get("query", {}).get("pages", {})
    for page in sorted(pages.values(), key=lambda item: item.get("title", "")):
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata", {})
        license_label = clean_metadata((metadata.get("LicenseShortName") or {}).get("value", ""))
        if not license_is_commercially_usable(license_label):
            continue
        image_url = info.get("thumburl") or info.get("url")
        mime = info.get("thumbmime") or info.get("mime", "")
        if not image_url or mime not in ("image/jpeg", "image/png", "image/webp"):
            continue
        try:
            image_request = urllib.request.Request(
                image_url, headers={"User-Agent": "VideoFactory/1.0 (educational short-video builder)"}
            )
            with urllib.request.urlopen(image_request, timeout=25) as image_response:
                data = image_response.read(15 * 1024 * 1024 + 1)
            if len(data) > 15 * 1024 * 1024:
                continue
            destination.write_bytes(data)
            with Image.open(destination) as check:
                check.verify()
            title = page.get("title", "Wikimedia Commons image")
            author = clean_metadata((metadata.get("Artist") or {}).get("value", "")) or "Author not listed"
            description_url = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            credit = f"{title.removeprefix('File:')} | {author} | {license_label}"
            return {"credit": credit, "license": license_label, "url": description_url}
        except Exception:
            destination.unlink(missing_ok=True)
            continue
    return None


def draw_scene(title: str, caption: str, index: int, total: int,
               language: str, destination: Path, template: str = "animated",
               background_image: Path | None = None,
               image_credit: str = "") -> None:
    if template not in TEMPLATES:
        raise ValueError(f"Unsupported template: {template}")

    palettes = {
        "animated": ((13, 25, 75), (88, 30, 130)),
        "cinematic": ((3, 8, 20), (38, 18, 32)),
        "cartoon": ((25, 105, 150), (80, 38, 125)),
    }
    top, bottom = palettes[template]
    if background_image and background_image.exists():
        with Image.open(background_image) as source:
            image = ImageOps.fit(source.convert("RGB"), (W, H), method=Image.Resampling.LANCZOS)
        image = ImageEnhance.Brightness(image).enhance(0.42 if template == "cinematic" else 0.62)
    else:
        image = Image.new("RGB", (W, H))
        bg = ImageDraw.Draw(image)
        for y in range(0, H, 8):
            t = y / H
            color = tuple(int(a * (1-t) + b*t) for a,b in zip(top,bottom))
            bg.rectangle((0,y,W,min(H,y+8)),fill=color)

    draw = ImageDraw.Draw(image, "RGBA")
    accents = {"animated":(70,235,255,255),"cinematic":(239,196,112,255),"cartoon":(255,221,70,255)}
    accent=accents[template]

    if template == "animated":
        # Layered motion-graphic orbs and a glowing central stage.
        for x,y,r,color in [(150,330,150,(40,210,255,42)),(900,560,230,(255,70,190,38)),
                            (820,1450,190,(100,255,180,35)),(180,1530,120,(255,190,50,40))]:
            draw.ellipse((x-r,y-r,x+r,y+r),fill=color,outline=(*accent[:3],100),width=5)
        draw.rounded_rectangle((62,90,1018,1825),radius=65,outline=(*accent[:3],180),width=5)
        draw.text((100,145),"MOTION STORY",font=load_font("en",28,True),fill=accent)
        title_y=270

    elif template == "cinematic":
        # Film-frame composition, letterbox bars and dramatic title treatment.
        draw.rectangle((0,0,W,190),fill=(0,0,0,220))
        draw.rectangle((0,H-210,W,H),fill=(0,0,0,225))
        draw.rectangle((0,0,W,H),outline=(*accent[:3],65),width=7)
        draw.text((90,245),"A CINEMATIC STORY",font=load_font("en",28,True),fill=accent)
        title_y=370

    else:
        # Original simple cartoon mascot, drawn from shapes (not a stock character).
        draw.ellipse((650,180,1000,530),fill=(255,205,80,255),outline=(30,20,50,255),width=12)
        draw.ellipse((735,300,790,365),fill=(255,255,255,255),outline=(25,20,40,255),width=7)
        draw.ellipse((855,300,910,365),fill=(255,255,255,255),outline=(25,20,40,255),width=7)
        draw.ellipse((755,320,780,355),fill=(20,20,35,255))
        draw.ellipse((875,320,900,355),fill=(20,20,35,255))
        draw.arc((760,340,900,455),start=10,end=170,fill=(100,25,35,255),width=12)
        draw.rounded_rectangle((690,500,960,850),radius=105,fill=(255,95,105,255),outline=(30,20,50,255),width=12)
        draw.line((710,590,570,760),fill=(255,205,80,255),width=42)
        draw.line((935,590,1040,745),fill=(255,205,80,255),width=42)
        draw.rounded_rectangle((55,95,1025,1825),radius=70,fill=(255,255,255,24),outline=(255,255,255,170),width=7)
        draw.text((100,145),"CARTOON TALE",font=load_font("en",28,True),fill=accent)
        title_y=900

    title_font=load_font(language,58,True)
    body_font=load_font(language,58 if template!="cartoon" else 52,True)
    title_lines=wrap_text(draw,title[:100],title_font,850)
    for line in title_lines[:3]:
        draw.text((95,title_y),line,font=title_font,fill=(255,255,255,255),
                  stroke_width=2,stroke_fill=(0,0,0,190))
        title_y+=78
    title_y+=42

    lines=wrap_text(draw,caption,body_font,850)
    line_height=88
    if template=="cartoon":
        panel=(80,1120,1000,1595)
        draw.rounded_rectangle(panel,radius=55,fill=(15,25,50,210),outline=accent,width=6)
        text_x=125
        y=1180
    elif template=="cinematic":
        panel=(80,900,1000,1510)
        draw.rounded_rectangle(panel,radius=20,fill=(0,0,0,150),outline=(*accent[:3],170),width=3)
        text_x=125
        y=970
    else:
        panel=(80,900,1000,1585)
        draw.rounded_rectangle(panel,radius=55,fill=(8,12,42,145),outline=(*accent[:3],150),width=4)
        text_x=125
        y=980
    for line in lines[:6]:
        draw.text((text_x,y),line,font=body_font,fill=(255,255,255,255),
                  stroke_width=1,stroke_fill=(0,0,0,180))
        y+=line_height

    draw.rounded_rectangle((100,1690,980,1704),radius=7,fill=(255,255,255,80))
    draw.rounded_rectangle((100,1690,100+int(880*(index+1)/total),1704),
                           radius=7,fill=accent)
    draw.text((105,1750),f"VIDEO FACTORY  /  {template.upper()}",
              font=load_font("en",25,True),fill=(255,255,255,235))
    if image_credit:
        draw.text((105,1790),f"Image: {image_credit[:90]}",
                  font=load_font("en",18),fill=(255,255,255,220))
    image.save(destination,quality=95)

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


def srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(scenes: list[str], duration: int, path: Path) -> None:
    scene_duration = duration / len(scenes)
    blocks = []
    for index, scene in enumerate(scenes):
        start = index * scene_duration
        end = duration if index == len(scenes) - 1 else (index + 1) * scene_duration
        blocks.append(f"{index + 1}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{scene}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def render(title: str, script: str, language: str, duration: int, output: Path,
           template: str = "animated", visual_query: str = "",
           voice_gender: str = "female") -> None:
    if not 15 <= duration <= 60:
        raise ValueError("duration must be between 15 and 60 seconds")
    if language not in ("hi", "en"):
        raise ValueError("language must be hi or en")
    if template not in TEMPLATES:
        raise ValueError(f"template must be one of: {', '.join(TEMPLATES)}")
    if voice_gender not in ("female", "male"):
        raise ValueError("voice_gender must be female or male")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed on this runner")
    scenes = make_scenes(script)
    output.parent.mkdir(parents=True, exist_ok=True)

    image_info = None
    with tempfile.TemporaryDirectory(prefix="video-factory-") as temp:
        work = Path(temp)
        background = work / "commons-background"
        if visual_query.strip():
            try:
                image_info = download_commons_background(visual_query, background)
            except Exception as error:
                print(f"Commons image lookup unavailable; using generated graphics: {error}")

        credit_for_frame = ""
        if image_info:
            credit_for_frame = image_info["credit"].split("|")[1].strip() + " / " + image_info["license"]

        concat = work / "scenes.txt"
        scene_duration = duration / len(scenes)
        with concat.open("w", encoding="utf-8") as listing:
            for i, caption in enumerate(scenes):
                frame = work / f"scene_{i:03d}.png"
                draw_scene(title, caption, i, len(scenes), language, frame,
                           template, background if image_info else None, credit_for_frame)
                listing.write(f"file '{frame.as_posix()}'\n")
                listing.write(f"duration {scene_duration:.4f}\n")
            listing.write(f"file '{(work / f'scene_{len(scenes)-1:03d}.png').as_posix()}'\n")

        voice = work / "voice.mp3"
        offline_voice = work / "voice.wav"
        ambient = work / "ambient.wav"
        make_ambient_audio(ambient, duration)
        voice_created = False
        voice_label = "ambient only"
        if shutil.which("edge-tts"):
            voice_name = (
                ("hi-IN-SwaraNeural" if voice_gender == "female" else "hi-IN-MadhurNeural")
                if language == "hi" else
                ("en-US-AriaNeural" if voice_gender == "female" else "en-US-GuyNeural")
            )
            try:
                subprocess.run(
                    ["edge-tts", "--voice", voice_name, "--text", script, "--write-media", str(voice)],
                    check=True, capture_output=True, text=True, timeout=120
                )
                voice_created = voice.exists() and voice.stat().st_size > 1000
                if voice_created:
                    voice_label = f"Edge online neural voice ({voice_name})"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
                print(f"Neural TTS unavailable; trying offline voice: {error}")

        if not voice_created and shutil.which("espeak-ng"):
            voice_name = "hi" if language == "hi" else "en"
            result = subprocess.run(
                ["espeak-ng", "-v", voice_name, "-s", "145", "-w", str(offline_voice), script],
                capture_output=True, text=True
            )
            voice_created = result.returncode == 0 and offline_voice.exists()
            if voice_created:
                voice_label = f"eSpeak NG offline voice ({voice_name})"

        zoom_filter = (
            ("fps=30,zoompan=z='min(zoom+0.0012,1.12)':x='iw/2-(iw/zoom/2)+sin(on/24)*18:y='ih/2-(ih/zoom/2)+cos(on/31)*18:d=1:s=1080x1920:fps=30,format=yuv420p" if template == "animated" else "fps=30,zoompan=z='min(zoom+0.00035,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,format=yuv420p")
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={W}x{H}:fps={FPS},format=yuv420p"
        )
        common = [
            "-vf", zoom_filter, "-t", str(duration), "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "24", "-movflags", "+faststart",
        ]
        if voice_created:
            voice_path = voice if voice.exists() else offline_voice
            audio_filter = (
                f"[1:a]aresample=48000,apad,atrim=0:{duration},volume=1.0[v];"
                f"[2:a]volume=0.16[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]"
            )
            command = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(voice_path), "-i", str(ambient), "-filter_complex", audio_filter,
                "-map", "0:v:0", "-map", "[a]", *common, "-c:a", "aac", "-b:a", "128k",
                str(output)
            ]
        else:
            command = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(ambient), "-map", "0:v:0", "-map", "1:a:0",
                *common, "-c:a", "aac", "-b:a", "96k", str(output)
            ]
        run(command)

        write_srt(scenes, duration, output.with_suffix(".srt"))
        credits = [
            "Video Factory — generation details",
            f"Template: {template}",
            f"Narration: {voice_label}",
            "Background: generated graphics",
        ]
        if image_info:
            credits[-1] = "Background: Wikimedia Commons image"
            credits.extend([
                f"Image credit: {image_info['credit']}",
                f"License/source: {image_info['url']}",
            ])
        else:
            credits.append("No external image was used.")
        output.with_name("credits.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a vertical short video")
    parser.add_argument("--title", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--language", choices=["hi", "en"], default="hi")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--template", choices=TEMPLATES, default="educational")
    parser.add_argument("--visual-query", default="")
    parser.add_argument("--voice-gender", choices=["female", "male"], default="female")
    parser.add_argument("--output", type=Path, default=Path("output/video.mp4"))
    args = parser.parse_args()
    render(args.title, args.script, args.language, args.duration, args.output,
           args.template, args.visual_query, args.voice_gender)
    print(f"Created {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
