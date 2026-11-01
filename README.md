# Video Factory

A cloud-only, free-first short-video generator. It runs on GitHub Actions; no Termux, local installation, API key, or paid service is required for the included template-based workflow.

## What it creates
- Vertical 9:16 MP4 shorts (default 30 seconds, configurable up to 60 seconds).
- Scene cards with animated camera movement, readable captions, and a title.
- Hindi narration using the open-source eSpeak NG voice available on the GitHub-hosted runner. Voice quality is synthetic/robotic; it is not a neural cinematic voice.
- An original synthesized ambient audio bed (no copyrighted music).
- Downloadable MP4 as a GitHub Actions artifact.

## Honest capability boundary
The default free-only workflow is a script-to-motion-graphics video factory, not a text-to-video diffusion model. It does not promise AI-generated cinematic footage or a free GPU. Wan/LTX-class video models require substantial GPU resources, and free hosted GPU access is not guaranteed. The architecture is intentionally keyless and uses GitHub-hosted Actions only.

## Create a video
1. Open Actions → Generate Short Video.
2. Select Run workflow.
3. Enter a title, narration, language (hi or en), and duration (15–60 seconds).
4. Run the workflow and wait for it to finish.
5. Open the completed run and download the video-factory-mp4 artifact.

The narration should be a few short sentences. The renderer distributes the text across scenes automatically.

## Run tests
The workflow runs the Python unit tests before rendering. To render a video, use the workflow dispatch form in GitHub Actions.

## Repository layout
- engine/render_video.py — image, narration, audio-bed, and FFmpeg rendering pipeline.
- tests/ — unit tests.
- .github/workflows/generate-video.yml — cloud workflow and artifact upload.
- examples/ — sample Hindi and English inputs.

## Limits
GitHub Actions usage is subject to the account's included minutes, repository settings, runner availability, and GitHub's current quotas. Artifact retention is limited. eSpeak NG is offline and free, but voice naturalness is limited. No upload to YouTube or social platforms is performed.

## License
MIT. Third-party system packages (FFmpeg, eSpeak NG, fonts) retain their own licenses.