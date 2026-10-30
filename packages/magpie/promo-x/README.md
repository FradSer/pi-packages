# Magpie for Pi — X promo

A 27-second, 1920×1080, 30 fps product promo with English on-screen text. Designed to communicate with X autoplay muted. Free bundled sound effects reinforce the cuts; no narration or background music.

## Deliverables

- `magpie-for-pi-x.mp4`: H.264 video + AAC audio.
- `index.html` and `compositions/`: editable HyperFrames source.
- `SPEC.md`, `STORYLINES.md`, `REVIEW.md`: creative decisions and verification.
- `assets/SOURCES.md`: asset provenance.

## Preview and render

```sh
pnpm dlx hyperframes@0.8.214 preview --background
pnpm dlx hyperframes@0.8.214 check --json
pnpm dlx hyperframes@0.8.214 render --quality delivery --output magpie-for-pi-x.mp4
```

The HyperFrames desktop app can edit this project. Preview is local only. Product screenshots are the repository's existing README assets, sequenced editorially; this is not a newly captured service run.

This directory sits outside the package's published `assets` path and is not listed in the npm package's `files` allowlist.
