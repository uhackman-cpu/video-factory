# Video Factory

A cloud-only, free-first vertical video generator. It runs on GitHub Actions; no Termux, local installation or paid API key is required.

## Two rendering paths

### 1. Scene-based Cartoon Story (new)

The storyboard renderer creates a continuous 2D cartoon world with original procedural characters, animated actions, moving props, camera motion, scene cross-fades, kinetic typography, captions, narration and an MP4 export. Characters can persist across scenes so the result plays as a story rather than a stack of title cards.

Supported character actions: `idle`, `walk`, `run`, `jump`, `wave`, `talk`, `think`, `cheer`, `sad`.

Supported emotions: `happy`, `curious`, `worried`, `sad`, `surprised`, `neutral`.

Backgrounds: `meadow`, `forest`, `night_forest`, `sunset`, `room`, `city`, `beach`, `space`.

Camera moves: `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`.

The complete Hindi example is `examples/cartoon-storyboard.json`. To render it:

1. Open Actions → **Generate Short Video** → **Run workflow**.
2. Paste the complete contents of `examples/cartoon-storyboard.json` into **storyboard_json**.
3. Choose a narration voice and run the workflow.
4. Download the `video-factory-output` artifact. It contains MP4, SRT and credits.

When `storyboard_json` is provided, scene durations and narration/captions come from the storyboard. The title, language and actions are defined in that JSON. Leave this field empty to use the original short-video renderer.

### Storyboard format

A project contains a `characters` dictionary and an ordered `scenes` array. A scene defines its duration, background, camera move, caption/narration, props, optional animated text overlays and the characters visible in it. Character IDs are reused across scenes to preserve identity.

```json
{
  "title": "Milo and the Lost Star",
  "language": "en",
  "fps": 24,
  "characters": {
    "milo": {
      "shape": "box",
      "color": "#f28a62",
      "accent": "#fff0c9",
      "scale": 1
    }
  },
  "scenes": [
    {
      "duration": 4,
      "background": "night_forest",
      "camera": "push_in",
      "caption": "A tiny star has fallen.",
      "narration": "One quiet night, Milo finds a fallen star.",
      "kinetic_text": [
        {"text": "A NEW ADVENTURE", "x": 0.5, "y": 0.28, "size": 42, "motion": "rise"}
      ],
      "props": [{"type": "star", "x": 0.72, "y": 0.65}],
      "characters": [
        {
          "id": "milo",
          "start_x": 0.2,
          "end_x": 0.55,
          "y": 0.77,
          "action": "walk",
          "emotion": "curious"
        }
      ]
    }
  ]
}
```

Limits: 1–12 scenes, 1–20 seconds per scene, 60 seconds total, up to 8 character definitions and 12/24/30 fps. Coordinates are normalized from 0 to 1. Character definitions support `round`, `box`, `robot` and `cat` shapes, a hex color, accent color and scale.

### 2. Original short-video renderer

Choose one visual genre in Actions → Generate Short Video:

- **Animated** — layered motion-graphic scenes and moving camera drift.
- **Cinematic** — dark film-like composition, letterbox bars and dramatic titles.
- **Cartoon** — a simple illustrated mascot with playful composition.

The renderer outputs vertical 9:16 MP4 (1080 × 1920), with neural narration where available, scene captions, SRT subtitles and an ambient audio bed.

## Narration

Hindi and English neural voices are attempted through `edge-tts`. If the online service is unavailable, the renderer falls back to offline eSpeak NG. The offline voice is more robotic. No paid API key is required.

## Tests and rendering

Every Actions run executes unit tests and a smoke render of the included cartoon storyboard before rendering the requested video. The final MP4, subtitle file and credits are verified before upload. Artifacts are retained for seven days.

## Honest capability limits

The cartoon engine is an original **procedural 2D animation system**: it draws its own character rigs and props, animates their basic actions, and applies camera movement and scene transitions. It is not a diffusion video model, not a full 3D character-animation studio, and it does not yet offer AI-generated character art or complex facial motion capture. The original Animated/Cinematic/Cartoon modes remain graphics-based.

Bang Motion and the Cartoon Animation Kit are architectural inspiration only; their third-party source code and artwork are not copied into this repository. The optional Qwen 3D Coder shown in the reference post is a separate model for generating Three.js scenes, not a runtime dependency of this cloud renderer.

## License

MIT for this repository. Third-party tools, voices, fonts and source images retain their own licenses and terms.
