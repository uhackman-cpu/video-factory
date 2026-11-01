"""Scene-based 2D cartoon animation renderer.

The project format is deliberately declarative: scenes define a continuous world,
characters, props, camera motion, dialogue/captions and narration. Frames are
streamed to FFmpeg so the renderer does not keep hundreds of PNGs in memory.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 720, 1280
ALLOWED_ACTIONS = {"idle", "walk", "run", "jump", "wave", "talk", "think", "cheer", "sad"}
ALLOWED_EMOTIONS = {"happy", "curious", "worried", "sad", "surprised", "neutral"}
ALLOWED_BACKGROUNDS = {"meadow", "forest", "night_forest", "sunset", "room", "city", "beach", "space"}
ALLOWED_CAMERAS = {"static", "push_in", "pull_out", "pan_left", "pan_right"}
ALLOWED_PROPS = {"tree", "house", "door", "star", "rock", "flower", "table", "moon", "lamp", "cloud", "chest", "hill"}


def _color(value: str, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"{field} must be a 6-digit hex color")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def validate_storyboard(project: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(project, dict):
        raise ValueError("Storyboard must be a JSON object")
    if not isinstance(project.get("scenes"), list) or not project["scenes"]:
        raise ValueError("Storyboard must contain a non-empty scenes array")
    if len(project["scenes"]) > 12:
        raise ValueError("Storyboard supports at most 12 scenes")
    fps = int(project.get("fps", 24))
    if fps not in (12, 24, 30):
        raise ValueError("fps must be 12, 24 or 30")

    characters = project.get("characters", {})
    if not isinstance(characters, dict) or len(characters) > 8:
        raise ValueError("characters must be an object with at most 8 characters")
    for character_id, character in characters.items():
        if not isinstance(character_id, str) or not isinstance(character, dict):
            raise ValueError("Each character needs an id and an object definition")
        _color(character.get("color", "#ff965f"), f"characters.{character_id}.color")
        _color(character.get("accent", "#fff1c7"), f"characters.{character_id}.accent")
        if character.get("shape", "round") not in ("round", "box", "robot", "cat"):
            raise ValueError(f"Unsupported character shape for {character_id}")

    total_duration = 0.0
    for index, scene in enumerate(project["scenes"]):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index + 1} must be an object")
        duration = float(scene.get("duration", 4))
        if not 1 <= duration <= 20:
            raise ValueError(f"Scene {index + 1} duration must be between 1 and 20 seconds")
        total_duration += duration
        background = scene.get("background", "meadow")
        camera = scene.get("camera", "static")
        if background not in ALLOWED_BACKGROUNDS:
            raise ValueError(f"Unsupported background in scene {index + 1}: {background}")
        if camera not in ALLOWED_CAMERAS:
            raise ValueError(f"Unsupported camera in scene {index + 1}: {camera}")
        for item in scene.get("characters", []):
            if item.get("id") not in characters:
                raise ValueError(f"Unknown character id in scene {index + 1}: {item.get('id')}")
            if item.get("action", "idle") not in ALLOWED_ACTIONS:
                raise ValueError(f"Unsupported character action: {item.get('action')}")
            if item.get("emotion", "happy") not in ALLOWED_EMOTIONS:
                raise ValueError(f"Unsupported character emotion: {item.get('emotion')}")
            for key in ("x", "start_x", "end_x", "y"):
                if key in item and not 0 <= float(item[key]) <= 1:
                    raise ValueError(f"Scene {index + 1} character {key} must be between 0 and 1")
        for prop in scene.get("props", []):
            if prop.get("type") not in ALLOWED_PROPS:
                raise ValueError(f"Unsupported prop in scene {index + 1}: {prop.get('type')}")
            for key in ("x", "y"):
                if key in prop and not 0 <= float(prop[key]) <= 1:
                    raise ValueError(f"Scene {index + 1} prop {key} must be between 0 and 1")
    if total_duration > 60:
        raise ValueError("Total storyboard duration cannot exceed 60 seconds")
    project = dict(project)
    project["fps"] = fps
    project["duration"] = total_duration
    return project


def storyboard_narration(project: dict[str, Any]) -> str:
    parts = [str(scene.get("narration", "")).strip()
             for scene in project.get("scenes", []) if str(scene.get("narration", "")).strip()]
    if not parts:
        parts = [str(scene.get("caption", "")).strip()
                 for scene in project.get("scenes", []) if str(scene.get("caption", "")).strip()]
    return " ".join(parts)


def _font(size: int, bold: bool = False, language: str = "en") -> ImageFont.ImageFont:
    candidates = []
    if language == "hi":
        candidates.append(
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
            if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
        )
    candidates.append(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    result: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), trial, font=font)[2] > width:
            result.append(current)
            current = word
        else:
            current = trial
    if current:
        result.append(current)
    return result or [""]


def _background(scene: dict[str, Any], t: float) -> Image.Image:
    name = scene.get("background", "meadow")
    palettes = {
        "meadow": ((122, 199, 236), (185, 229, 177), (104, 176, 94)),
        "forest": ((93, 166, 187), (83, 151, 108), (49, 107, 69)),
        "night_forest": ((12, 24, 61), (45, 62, 98), (24, 64, 55)),
        "sunset": ((255, 149, 103), (255, 204, 135), (86, 114, 95)),
        "room": ((190, 175, 206), (127, 117, 159), (79, 57, 83)),
        "city": ((119, 168, 206), (169, 188, 195), (84, 100, 111)),
        "beach": ((96, 191, 226), (204, 226, 195), (226, 191, 127)),
        "space": ((8, 12, 38), (24, 28, 72), (16, 22, 55)),
    }
    top, middle, ground = palettes[name]
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    horizon = int(HEIGHT * (0.70 if name not in ("room", "space") else 0.78))
    for y in range(0, HEIGHT, 8):
        if y < horizon:
            p = y / max(1, horizon)
            c = tuple(round(top[i] * (1 - p) + middle[i] * p) for i in range(3))
        else:
            p = (y - horizon) / max(1, HEIGHT - horizon)
            c = tuple(round(middle[i] * (1 - p) + ground[i] * p) for i in range(3))
        draw.rectangle((0, y, WIDTH, min(HEIGHT, y + 8)), fill=c)

    if name == "space":
        for i in range(42):
            x = (i * 167 + 29) % WIDTH
            y = (i * 293 + 61) % (HEIGHT - 150)
            twinkle = 150 + int(90 * abs(math.sin(t * 2 + i)))
            draw.ellipse((x, y, x + 3, y + 3), fill=(255, 255, 220, twinkle))
    else:
        # A few drifting clouds establish depth without turning the scene into a slide.
        cloud_y = int(HEIGHT * 0.20)
        for index, base_x in enumerate((105, 430, 650)):
            x = int((base_x + (t * (9 + index * 3))) % (WIDTH + 130) - 65)
            y = cloud_y + index * 105
            if name not in ("night_forest", "room", "city"):
                draw.ellipse((x - 42, y, x + 42, y + 30), fill=(247, 249, 244))
                draw.ellipse((x - 16, y - 18, x + 35, y + 34), fill=(247, 249, 244))
    if name in ("forest", "night_forest"):
        for x, h in ((35, 260), (650, 320), (560, 225)):
            base = int(HEIGHT * 0.72)
            draw.rectangle((x - 12, base - h // 2, x + 12, base), fill=(87, 62, 48))
            draw.ellipse((x - h // 2, base - h, x + h // 2, base - h // 3),
                         fill=(34, 105, 77) if name == "forest" else (24, 78, 67))
    elif name == "room":
        draw.rectangle((0, int(HEIGHT * 0.48), WIDTH, int(HEIGHT * 0.50)), fill=(74, 65, 94))
        draw.rectangle((70, 220, 250, 560), fill=(102, 76, 61), outline=(48, 37, 44), width=12)
        draw.rectangle((88, 240, 232, 540), fill=(226, 177, 122), outline=(74, 51, 49), width=7)
        draw.rectangle((0, int(HEIGHT * .78), WIDTH, HEIGHT), fill=(102, 63, 76))
    elif name == "city":
        for i, x in enumerate((20, 130, 260, 420, 570, 660)):
            height = 160 + (i * 73) % 230
            draw.rectangle((x, horizon - height, x + 75, horizon),
                           fill=(70 + i * 5, 91 + i * 4, 115 + i * 3))
            for wx in range(x + 12, x + 68, 22):
                for wy in range(horizon - height + 18, horizon - 10, 36):
                    draw.rectangle((wx, wy, wx + 8, wy + 13), fill=(250, 213, 137))
    elif name == "beach":
        draw.rectangle((0, int(HEIGHT * .55), WIDTH, int(HEIGHT * .71)), fill=(65, 170, 202))
    elif name == "space":
        draw.ellipse((WIDTH - 180, 120, WIDTH - 70, 230), fill=(244, 240, 205))
    return image


def _draw_prop(draw: ImageDraw.ImageDraw, prop: dict[str, Any], t: float) -> None:
    x = int(float(prop.get("x", .5)) * WIDTH)
    y = int(float(prop.get("y", .72)) * HEIGHT)
    kind = prop["type"]
    if kind == "tree":
        draw.rectangle((x - 12, y - 125, x + 12, y), fill=(105, 68, 43))
        draw.ellipse((x - 76, y - 205, x + 76, y - 54), fill=(54, 139, 79),
                     outline=(30, 82, 55), width=5)
    elif kind == "house":
        draw.rectangle((x - 76, y - 120, x + 76, y), fill=(244, 190, 119),
                       outline=(84, 57, 49), width=6)
        draw.polygon(((x - 93, y - 115), (x, y - 205), (x + 93, y - 115)),
                     fill=(172, 76, 65), outline=(84, 57, 49))
        draw.rectangle((x - 20, y - 72, x + 20, y), fill=(103, 68, 59))
    elif kind == "door":
        draw.rectangle((x - 47, y - 170, x + 47, y), fill=(151, 87, 54),
                       outline=(61, 39, 35), width=7)
        draw.ellipse((x + 27, y - 88, x + 35, y - 80), fill=(255, 221, 106))
    elif kind == "star":
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 35 if i % 2 == 0 else 15
            points.append((x + math.cos(angle) * radius, y + math.sin(angle) * radius - 30))
        draw.polygon(points, fill=(255, 230, 98), outline=(255, 255, 225))
    elif kind == "rock":
        draw.ellipse((x - 48, y - 48, x + 48, y + 4), fill=(111, 119, 124),
                     outline=(57, 67, 73), width=4)
    elif kind == "flower":
        for ox, oy in ((0, -20), (20, 0), (0, 20), (-20, 0)):
            draw.ellipse((x + ox - 13, y + oy - 13, x + ox + 13, y + oy + 13),
                         fill=(255, 141, 177))
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(255, 213, 87))
        draw.line((x, y + 20, x, y + 68), fill=(48, 119, 73), width=7)
    elif kind == "table":
        draw.rectangle((x - 78, y - 54, x + 78, y - 38), fill=(132, 78, 48))
        draw.rectangle((x - 65, y - 38, x - 52, y + 10), fill=(94, 56, 41))
        draw.rectangle((x + 52, y - 38, x + 65, y + 10), fill=(94, 56, 41))
    elif kind == "moon":
        draw.ellipse((x - 55, y - 55, x + 55, y + 55), fill=(255, 239, 184))
        draw.ellipse((x - 20, y - 65, x + 70, y + 35), fill=(24, 28, 72))
    elif kind == "lamp":
        draw.line((x, y - 130, x, y), fill=(55, 47, 62), width=12)
        draw.polygon(((x - 32, y - 132), (x + 32, y - 132), (x + 23, y - 175), (x - 23, y - 175)),
                     fill=(255, 221, 119), outline=(58, 46, 58))
    elif kind == "cloud":
        draw.ellipse((x - 52, y - 20, x + 52, y + 26), fill=(249, 250, 246))
        draw.ellipse((x - 22, y - 48, x + 35, y + 25), fill=(249, 250, 246))
    elif kind == "chest":
        draw.rounded_rectangle((x - 60, y - 62, x + 60, y), radius=12,
                               fill=(141, 81, 45), outline=(62, 42, 39), width=6)
        draw.rectangle((x - 8, y - 42, x + 8, y - 19), fill=(255, 221, 112))
    elif kind == "hill":
        draw.ellipse((x - 180, y - 130, x + 180, y + 85), fill=(75, 151, 91))


def _draw_character(draw: ImageDraw.ImageDraw, definition: dict[str, Any],
                    actor: dict[str, Any], progress: float, seconds: float) -> None:
    color = _color(definition.get("color", "#ff965f"), "character color")
    accent = _color(definition.get("accent", "#fff1c7"), "character accent")
    scale = max(.55, min(1.5, float(definition.get("scale", 1.0))))
    action = actor.get("action", "idle")
    emotion = actor.get("emotion", "happy")
    start_x = float(actor.get("start_x", actor.get("x", .5)))
    end_x = float(actor.get("end_x", actor.get("x", start_x)))
    x = int((start_x + (end_x - start_x) * progress) * WIDTH)
    feet = int(float(actor.get("y", .76)) * HEIGHT)
    phase_speed = 2.0 if action == "walk" else 4.0 if action == "run" else 1.2
    phase = seconds * phase_speed * math.tau
    bob = math.sin(phase * 2) * 7 * scale if action in ("walk", "run", "cheer") else math.sin(seconds * 2) * 3 * scale
    jump = abs(math.sin(progress * math.pi)) * 82 * scale if action == "jump" else 0
    feet -= int(bob + jump)
    direction = -1 if actor.get("facing") == "left" else 1

    # Soft grounding shadow keeps the character attached to the scene.
    draw.ellipse((x - 62 * scale, feet - 4, x + 62 * scale, feet + 16),
                 fill=(20, 27, 34, 65))
    head_y = feet - int(178 * scale)
    torso_top = feet - int(132 * scale)
    torso_bottom = feet - int(48 * scale)
    head_box = (x - 48 * scale, head_y - 48 * scale, x + 48 * scale, head_y + 48 * scale)
    shape = definition.get("shape", "round")
    if shape == "box":
        draw.rounded_rectangle(head_box, radius=int(12 * scale), fill=color, outline=(38, 32, 42), width=max(3, int(6 * scale)))
    elif shape == "robot":
        draw.rounded_rectangle(head_box, radius=int(20 * scale), fill=color, outline=(35, 43, 58), width=max(3, int(6 * scale)))
        draw.line((x, head_y - 55 * scale, x, head_y - 70 * scale), fill=accent, width=max(3, int(5 * scale)))
        draw.ellipse((x - 7 * scale, head_y - 78 * scale, x + 7 * scale, head_y - 64 * scale), fill=accent)
    else:
        draw.ellipse(head_box, fill=color, outline=(38, 32, 42), width=max(3, int(6 * scale)))
        if shape == "cat":
            draw.polygon(((x - 38 * scale, head_y - 23 * scale), (x - 33 * scale, head_y - 72 * scale),
                          (x - 3 * scale, head_y - 42 * scale)), fill=color, outline=(38, 32, 42))
            draw.polygon(((x + 38 * scale, head_y - 23 * scale), (x + 33 * scale, head_y - 72 * scale),
                          (x + 3 * scale, head_y - 42 * scale)), fill=color, outline=(38, 32, 42))

    eye_y = head_y - 7 * scale
    eye_dx = 18 * scale
    eye_color = (255, 255, 255)
    pupil = (35, 34, 43)
    for side in (-1, 1):
        ex = x + side * eye_dx
        draw.ellipse((ex - 9 * scale, eye_y - 10 * scale, ex + 9 * scale, eye_y + 11 * scale), fill=eye_color)
        px = ex + (3 if direction > 0 else -3) * scale
        draw.ellipse((px - 4 * scale, eye_y - 3 * scale, px + 4 * scale, eye_y + 5 * scale), fill=pupil)
    mouth_y = head_y + 22 * scale
    if action == "talk" and math.sin(seconds * 10) > .05:
        draw.ellipse((x - 10 * scale, mouth_y - 2 * scale, x + 10 * scale, mouth_y + 13 * scale),
                     fill=(89, 37, 48))
    elif emotion == "sad" or action == "sad":
        draw.arc((x - 18 * scale, mouth_y - 1 * scale, x + 18 * scale, mouth_y + 22 * scale),
                 205, 335, fill=(75, 38, 47), width=max(2, int(4 * scale)))
    else:
        draw.arc((x - 18 * scale, mouth_y - 12 * scale, x + 18 * scale, mouth_y + 18 * scale),
                 15, 165, fill=(75, 38, 47), width=max(2, int(4 * scale)))

    draw.rounded_rectangle((x - 37 * scale, torso_top, x + 37 * scale, torso_bottom),
                           radius=int(18 * scale), fill=accent, outline=(38, 32, 42),
                           width=max(3, int(5 * scale)))
    # Animated limbs: the same rig persists across all scenes.
    hip_y = feet - 48 * scale
    shoulder_y = torso_top + 20 * scale
    swing = math.sin(phase) * (30 if action in ("walk", "run") else 8) * scale
    leg_swing = math.sin(phase) * (25 if action in ("walk", "run") else 4) * scale
    left_hand = (x - 67 * scale, shoulder_y + swing)
    right_hand = (x + 67 * scale, shoulder_y - swing)
    if action in ("wave", "cheer"):
        raised = (x + 78 * scale, shoulder_y - 66 * scale + math.sin(seconds * 7) * 10 * scale)
        left_hand = (x - 67 * scale, shoulder_y + 12 * scale)
        right_hand = raised
    elif action == "think":
        right_hand = (x + 45 * scale, head_y + 5 * scale)
    limb_width = max(7, int(13 * scale))
    draw.line((x - 30 * scale, shoulder_y, *left_hand), fill=color, width=limb_width)
    draw.line((x + 30 * scale, shoulder_y, *right_hand), fill=color, width=limb_width)
    draw.ellipse((left_hand[0] - 9 * scale, left_hand[1] - 9 * scale,
                  left_hand[0] + 9 * scale, left_hand[1] + 9 * scale), fill=accent)
    draw.ellipse((right_hand[0] - 9 * scale, right_hand[1] - 9 * scale,
                  right_hand[0] + 9 * scale, right_hand[1] + 9 * scale), fill=accent)
    for side, swing_sign in ((-1, -1), (1, 1)):
        sx = x + side * 18 * scale
        ex = sx + swing_sign * leg_swing
        draw.line((sx, hip_y, ex, feet - 6 * scale), fill=(45, 42, 54), width=limb_width)
        draw.ellipse((ex - 14 * scale, feet - 13 * scale, ex + 14 * scale, feet + 5 * scale),
                     fill=(45, 42, 54))


def draw_story_frame(project: dict[str, Any], scene_index: int, frame_index: int) -> Image.Image:
    """Draw one deterministic frame; exposed for tests and preview tooling."""
    scene = project["scenes"][scene_index]
    fps = int(project.get("fps", 24))
    duration = float(scene.get("duration", 4))
    seconds = frame_index / fps
    progress = min(1.0, max(0.0, seconds / duration))
    image = _background(scene, seconds)
    draw = ImageDraw.Draw(image, "RGBA")
    for prop in scene.get("props", []):
        _draw_prop(draw, prop, seconds)
    definitions = project.get("characters", {})
    for actor in scene.get("characters", []):
        _draw_character(draw, definitions[actor["id"]], actor, progress, seconds)

    # Kinetic lower-third is integrated with the cartoon world, not a full-screen slide.
    caption = str(scene.get("caption", "")).strip()
    if caption:
        accent = _color(project.get("accent", "#ffe16b"), "accent")
        panel_top = HEIGHT - 188
        entrance = min(1.0, max(0.0, seconds / .35))
        y = panel_top + int((1 - entrance) * 28)
        draw.rounded_rectangle((34, y, WIDTH - 34, HEIGHT - 36), radius=28,
                               fill=(15, 25, 48, 205), outline=(*accent, 235), width=3)
        font = _font(27 if project.get("language", "en") == "hi" else 28,
                     bold=True, language=project.get("language", "en"))
        lines = _wrap(draw, caption, font, WIDTH - 100)
        for line_index, line in enumerate(lines[:3]):
            draw.text((58, y + 24 + line_index * 38), line, font=font, fill=(255, 255, 255, 255))
    if scene_index == 0 and seconds < 2.0 and project.get("title"):
        title_font = _font(34, True, project.get("language", "en"))
        title = str(project["title"])
        title_y = 58 + int((1 - min(1, seconds / .5)) * -25)
        draw.rounded_rectangle((34, title_y - 12, WIDTH - 34, title_y + 52),
                               radius=20, fill=(9, 20, 41, 135))
        draw.text((54, title_y), title[:48], font=title_font, fill=(255, 255, 255, 245))
    camera = scene.get("camera", "static")
    if camera != "static":
        if camera == "push_in":
            zoom = 1.0 + .06 * progress
        elif camera == "pull_out":
            zoom = 1.06 - .06 * progress
        else:
            zoom = 1.025
        crop_w, crop_h = int(WIDTH / zoom), int(HEIGHT / zoom)
        cx = WIDTH / 2
        if camera == "pan_left":
            cx += (progress - .5) * WIDTH * .08
        elif camera == "pan_right":
            cx -= (progress - .5) * WIDTH * .08
        left = max(0, min(WIDTH - crop_w, int(cx - crop_w / 2)))
        top = max(0, min(HEIGHT - crop_h, int(HEIGHT / 2 - crop_h / 2)))
        image = image.crop((left, top, left + crop_w, top + crop_h)).resize(
            (WIDTH, HEIGHT), Image.Resampling.LANCZOS
        )
    return image


def _srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def write_storyboard_srt(project: dict[str, Any], path: Path) -> None:
    blocks = []
    cursor = 0.0
    for index, scene in enumerate(project["scenes"], start=1):
        caption = str(scene.get("caption") or scene.get("narration") or "").strip()
        duration = float(scene.get("duration", 4))
        if caption:
            blocks.append(f"{index}\n{_srt_time(cursor)} --> {_srt_time(cursor + duration)}\n{caption}\n")
        cursor += duration
    path.write_text("\n".join(blocks), encoding="utf-8")


def render_storyboard(project: dict[str, Any], output: Path) -> dict[str, Any]:
    """Render a storyboard to a silent H.264 MP4, streaming RGB frames to FFmpeg."""
    project = validate_storyboard(project)
    fps = int(project["fps"])
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(fps),
        "-i", "-", "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE)
    previous: Image.Image | None = None
    try:
        assert process.stdin is not None
        for scene_index, scene in enumerate(project["scenes"]):
            frame_count = max(1, round(float(scene.get("duration", 4)) * fps))
            transition_frames = min(round(.28 * fps), max(1, frame_count // 4)) if previous else 0
            for frame_index in range(frame_count):
                current = draw_story_frame(project, scene_index, frame_index)
                if previous is not None and frame_index < transition_frames:
                    alpha = (frame_index + 1) / transition_frames
                    frame = Image.blend(previous, current, alpha)
                else:
                    frame = current
                process.stdin.write(frame.tobytes())
            previous = draw_story_frame(project, scene_index, frame_count - 1)
        process.stdin.close()
        error_output = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"FFmpeg cartoon render failed: {error_output[-2000:]}")
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    return {"width": WIDTH, "height": HEIGHT, "fps": fps,
            "duration": project["duration"], "scenes": len(project["scenes"])}



def render_storyboard_video(project: dict[str, Any], output: Path,
                            voice_gender: str = "female") -> dict[str, Any]:
    """Render a complete narrated cartoon MP4 plus SRT and credits."""
    import array
    import shutil
    import tempfile
    import wave

    project = validate_storyboard(project)
    if voice_gender not in ("female", "male"):
        raise ValueError("voice_gender must be female or male")
    duration = float(project["duration"])
    script = storyboard_narration(project)
    if not script:
        raise ValueError("Storyboard needs narration or captions for audio")
    output.parent.mkdir(parents=True, exist_ok=True)

    sample_rate = 22050
    sample_count = int(duration * sample_rate)
    samples = array.array("h")
    for index in range(sample_count):
        time = index / sample_rate
        fade = min(1.0, time / 1.2, max(0.0, (duration - time) / 1.2))
        value = (0.035 * math.sin(2 * math.pi * 110 * time)
                 + 0.016 * math.sin(2 * math.pi * 164.81 * time)) * fade
        samples.append(int(value * 32767))
    ambient_data = samples.tobytes()

    with tempfile.TemporaryDirectory(prefix="video-factory-story-") as temp:
        work = Path(temp)
        silent_video = work / "story-silent.mp4"
        ambient = work / "ambient.wav"
        voice = work / "voice.mp3"
        offline_voice = work / "voice.wav"
        render_info = render_storyboard(project, silent_video)
        with wave.open(str(ambient), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(ambient_data)

        voice_created = False
        voice_label = "ambient only"
        language = project.get("language", "en")
        if language not in ("hi", "en"):
            raise ValueError("Storyboard language must be hi or en")
        if shutil.which("edge-tts"):
            if language == "hi":
                voice_name = "hi-IN-SwaraNeural" if voice_gender == "female" else "hi-IN-MadhurNeural"
            else:
                voice_name = "en-US-AriaNeural" if voice_gender == "female" else "en-US-GuyNeural"
            try:
                subprocess.run(
                    ["edge-tts", "--voice", voice_name, "--text", script, "--write-media", str(voice)],
                    check=True, capture_output=True, text=True, timeout=180
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

        common = [
            "-vf", "scale=1080:1920:flags=lanczos", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]
        if voice_created:
            voice_path = voice if voice.exists() else offline_voice
            filter_complex = (
                f"[1:a]aresample=48000,apad,atrim=0:{duration:.3f},volume=1.0[v];"
                f"[2:a]volume=0.13[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]"
            )
            command = [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(silent_video),
                "-i", str(voice_path), "-i", str(ambient), "-filter_complex", filter_complex,
                "-map", "0:v:0", "-map", "[a]", *common, "-c:a", "aac", "-b:a", "128k",
                str(output)
            ]
        else:
            command = [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(silent_video),
                "-i", str(ambient), "-map", "0:v:0", "-map", "1:a:0",
                *common, "-c:a", "aac", "-b:a", "96k", str(output)
            ]
        subprocess.run(command, check=True)
    write_storyboard_srt(project, output.with_suffix(".srt"))
    credits = [
        "Video Factory — scene-based cartoon animation",
        "Renderer: original procedural 2D character rig and scene renderer",
        f"Title: {project.get('title', 'Untitled story')}",
        f"Scenes: {render_info['scenes']}",
        f"Narration: {voice_label}",
        f"Frame rate: {render_info['fps']} fps",
        "Output: 1080x1920 H.264 MP4",
        "No third-party character artwork was copied.",
    ]
    output.with_name("credits.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")
    return render_info
