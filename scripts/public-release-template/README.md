# DreamX-RoboConductor Showcase

An episode browser with filtering, result cards, video playback, bilingual
navigation, and step-by-step execution traces.

The package contains a runnable demo with three synthetic episodes and the
showcase frontend in `src/showcase/`.

## Run

Requires Python 3.10+ and a modern browser.

```sh
python3 serve.py --port 8098
```

Open <http://127.0.0.1:8098>. The server binds to localhost by default and
supports byte-range requests for video seeking. Use `--host 0.0.0.0` to
serve over a local network. Press Ctrl+C to stop.

## Package layout

- `dist/`: runnable demo, styles, and example data.
- `src/showcase/dist/`: showcase homepage and archive viewer source.
- `fixtures/` and `schemas/`: example payloads and JSON schemas.
- `tests/`: package and HTTP tests.
- `RELEASE_MANIFEST.json`: file sizes and SHA-256 checksums.

## Add your data

1. Edit `dist/data/demo.json` to customize the demo.
2. For the full showcase, provide `src/showcase/dist/data/page-data.json`,
   the archive catalog, episode files, and referenced media.
3. Keep media paths relative to the served directory and generate episode
   registrations from JSON. See [DATA_CONTRACTS.md](DATA_CONTRACTS.md).
4. Update the title, project description, and navigation links.

## Tests

```sh
python3 -m unittest discover -s tests -v
cd src/showcase
node scripts/test_i18n.cjs
node scripts/test_hero_playlist.cjs
node scripts/test_video_player.cjs
node scripts/test_content_safety.cjs
```

Frontend tests use Node.js 18+. The Python tests check package integrity,
local asset references, HTTP byte ranges, and path handling. Regenerate the
manifest after changing packaged files.

## GitHub

See [GITHUB_MIGRATION.md](GITHUB_MIGRATION.md) for repository and Pages setup.

## License

[DreamX-RoboConductor Non-Commercial Research and Personal Use License](LICENSE).

For non-commercial academic research, teaching, and personal non-commercial use only.
Commercial use is prohibited without a separate written license.
