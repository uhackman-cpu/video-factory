# Video Factory

A cloud-only, free-first vertical short-video generator. Runs on GitHub Actions; no Termux or local installation required.

## Visual genres (separate styles)

Choose one genre in Actions → Generate Short Video:

- **Animated** — colorful motion-graphic scenes with glowing orbs, layered shapes and moving camera drift.
- **Cinematic** — dark film-like composition, letterbox bars, dramatic title treatment and slow camera movement.
- **Cartoon** — bright illustrated cartoon mascot, playful speech-panel layout and bold colors.

These are three separate visual genres, not an educational-card template. The default is **Animated**. The previous generic Educational template has been removed from the workflow choices.

The renderer outputs vertical 9:16 MP4 (1080 × 1920), 30 fps, with narration, scene captions, SRT subtitles and an original ambient audio bed.

## Narration

Hindi female/male and English female/male neural voices are attempted through the open-source \`edge-tts\` package. The online voice service may be rate-limited or unavailable; the renderer then falls back to offline eSpeak NG, which sounds robotic. No paid API key is required.

## Background visuals

The three genres use original graphics drawn by the renderer. Optionally enter a Wikimedia Commons search phrase to use a compatible, attribution-checked source image. Only Public Domain, CC0, CC BY and CC BY-SA-style licenses are accepted; NonCommercial and NoDerivatives licenses are rejected. Image attribution and source are written to \`credits.txt\`.

**Honest limitation:** these styles are motion graphics and illustrated artwork, not AI-generated full-motion cartoon characters, 3D animation, or text-to-video footage. They run on a free CPU cloud runner; no paid AI video API or GPU is used.

## Create a video

1. Open the repository **Actions** tab.
2. Select **Generate Short Video** → **Run workflow**.
3. Enter a title and narration.
4. Select **Animated**, **Cinematic**, or **Cartoon**.
5. Choose language, voice gender and duration; optionally provide a Commons image search.
6. Run the workflow and download the **video-factory-output** artifact.

The artifact includes MP4, SRT subtitles and \`credits.txt\`. The workflow runs unit tests and checks the output video frame count before upload.

## Limits

GitHub Actions is subject to account quotas and runner availability. Artifacts are retained for seven days. Neural TTS and Commons image search depend on external services. This is not a diffusion-model video generator and does not promise AI-generated cinematic footage or automatic social publishing.

## License

MIT for this repository. Third-party tools, fonts, voices and source images retain their own licenses and terms.
