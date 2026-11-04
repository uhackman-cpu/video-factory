# Autonomous Hindi Facts Channel — Production Pipeline

## Locked production profile

- Niche: Hindi facts, science, nature, history, geography and technology
- Output target: one Short and one 5–10 minute long-form video per day
- Visual language: hybrid documentary (licensed footage, AI-generated scenes, and original motion graphics)
- Narration: Hindi male neural voice (hi-IN-MadhurNeural)
- Cost profile: balanced; prefer subscription entitlements and free/licensed sources, do not silently create paid API dependencies
- Execution: cloud only; no Termux or phone uptime dependency

## Current implementation in this repository

1. `engine/render_video.py`: existing graphics-first Shorts renderer.
2. `engine/story_animation.py`: existing procedural 2D storyboard renderer.
3. `engine/hybrid_renderer.py`: new manifest-driven renderer for licensed image/video scenes, Hindi male/female neural narration, SRT captions and per-scene attribution.
4. `.github/workflows/render-hybrid-video.yml`: cloud workflow that accepts a project JSON manifest and produces MP4, SRT, credits and the input manifest as a downloadable artifact.
5. `tests/test_hybrid_renderer.py`: validation and subtitle tests.

The hybrid renderer is a media compositor, not an AI research agent or a Google Flow client. It expects each scene's media asset to be supplied as an HTTPS URL with a declared commercially usable license and source page. It rejects non-commercial and no-derivatives license labels. The asset metadata is supplied by the project author and must be checked against the actual source terms; a license label alone is not legal advice.

## Scene manifest

Start from `examples/hybrid-facts-template.json`. Replace all placeholder asset URLs and source-page URLs with actual downloadable HTTPS media URLs and their real creator/license information. Use only assets whose terms permit the intended commercial use. Do not use YouTube downloads, social-media reposts, or media with unclear rights.

Each scene contains:
- `kind`: `image` or `video`
- `url`: direct HTTPS media URL
- `duration`: scene duration in seconds
- `caption`: on-screen subtitle text
- `license`: verified license label
- `credit`: creator/author
- `source_page`: source/attribution page

Short manifests are limited to 90 seconds total. Long manifests are limited to 900 seconds total. Individual scenes are limited to 90 seconds and downloads to 80 MiB each.

## Rendering

GitHub → Actions → **Render Hybrid Facts Video** → Run workflow:
1. Paste the complete JSON from a completed manifest.
2. Select male narration.
3. Run the workflow.
4. Download the `hybrid-facts-video` artifact.

The artifact contains the MP4, SRT captions, credits and project JSON. The workflow is currently manual; it does not publish to YouTube.

## Production architecture — remaining phases

### Phase A — research and editorial agent
- Discover candidate topics and detect duplicates.
- Gather at least two independent sources for factual claims; prefer primary/academic/government sources.
- Store claim-level citations, dates and uncertainty.
- Generate distinct Short and long-form scripts, not just a shortened copy.
- Reject weakly sourced or disputed claims.

### Phase B — visual asset acquisition
- Google Flow is the preferred AI-scene creation interface if an authorized cloud-browser session can be maintained.
- The consumer Flow subscription is not itself a documented unattended API credential. Do not assume that a Gemini/Google AI subscription grants API access or automated Flow control.
- Until a supported authenticated cloud-browser workflow is proven, use properly licensed stock/Commons footage and original motion graphics as the working fallback.
- Store an asset manifest with origin, creator, license, retrieval date and attribution.

### Phase C — production
- Generate Hindi male narration.
- Render scene assets in 9:16 for Shorts and 16:9 for long videos.
- Add original diagrams, labels, maps and visual explanations where useful.
- Add captions, sound design and a consistent but varied editorial identity.
- Run technical checks: duration, resolution, audio presence, clipping, subtitle timing and black-frame detection.

### Phase D — YouTube publishing
- Use YouTube Data API OAuth with the channel owner's explicit authorization.
- Upload as private/unlisted first during pilot; schedule public publication only after QC and owner approval.
- Store refresh tokens only in a secret manager, never in Git.
- Retry resumable uploads safely and record returned video IDs.
- Publishing is not implemented yet.

### Phase E — analytics and improvement
- Pull impressions, CTR, views, average view duration, retention and returning viewers.
- Compare performance by topic, hook, length and visual treatment.
- Adjust future scripts based on observed audience response, not clickbait.
- Send a daily Telegram report and alert on failures.

## Monetization safeguards

YouTube's monetization policy disallows mass-produced/repetitive content that lacks meaningful variation or original value. Every video must have its own researched angle, narrative, explanation and visual treatment. Do not turn this system into a slideshow factory. Preserve research notes and source credits for every upload.

## Security and operating rules

- No API key, OAuth token, cookie or browser profile may be committed to this public repository.
- Never upload automatically if research, rights, rendering or QC checks fail.
- Use private/unlisted pilot uploads before enabling unattended public publishing.
- Treat daily volume as a target, not a reason to publish weak content.
- A failed or unverified asset must be quarantined, not silently replaced with an unlicensed source.
