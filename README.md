# DreamX-RoboConductor Showcase

A website for robot evaluation results, task summaries, videos, and
step-by-step execution traces, with an English/Chinese interface.

## Quick start

```sh
python3 serve.py --port 18827
```

Open <http://127.0.0.1:18827/>. The server binds to localhost by default and
serves `dist/` with HTTP byte-range support. To share a preview on a local
network, pass `--host 0.0.0.0`.

For a background preview:

```sh
SHOWCASE_PORT=18827 bash scripts/start.sh
bash scripts/stop.sh
```

## Source package

```sh
python3 scripts/build_public_release.py --help
```

The downloadable source package contains the showcase/archive frontend,
local server, three synthetic demo episodes, schemas, and tests. It is
built from `FILE_ALLOWLIST` in `scripts/build_public_release.py`.

This working repository also contains prepared experiment records and
media under `dist/`, plus data-import and deployment tools under `scripts/`.

## Data and assets

```text
dist/
├── assets/             # Homepage UI, playback, localization
├── data/               # Results and page data
├── media/              # Original videos, web previews, figures
└── archive/episodes/
    ├── simulation/     # 500 RoboTwin episodes, grouped by task
    └── real-world/     # 50 Piper episodes, grouped by task
```

Each archive category has an index and README. Episode folders contain
`data.js` and `frames/`; the catalog resolves existing episode bookmarks.

Homepage highlights are fixed to pen insertion, cup hanging, three-bowl
stacking, and cup emptying. Video players stream when byte ranges are
supported and otherwise share a bounded cache. Off-screen players pause and
release resources. `scripts/build_web_media.py` generates lightweight web
previews while original videos remain available in the download bundle.

The RoboTwin comparison figure is generated from
`dist/data/method-comparison.json` by `scripts/build_comparison_figure.py`.

## Build and checks

```sh
python3 scripts/sanitize_public_data.py --check
python3 scripts/prepare_pages.py
python3 scripts/verify_site.py
node scripts/test_video_player.cjs
node scripts/test_i18n.cjs
node scripts/test_content_safety.cjs
python3 scripts/test_public_data_sanitizer.py
python3 scripts/test_release_privacy.py
```

The site uses native browser APIs and a Python standard-library server.
Serve `dist/` on a static host supporting video MIME types and byte ranges.
Preparation dependencies are listed in [DEPENDENCIES.md](DEPENDENCIES.md).

## GitHub Pages

After importing this repository into GitHub, set **Settings → Pages → Source**
to **GitHub Actions**. The [Pages workflow](.github/workflows/pages.yml) prepares
the download bundles, verifies the site, and publishes `dist/` on pushes to
`main`. It can also be started manually from the Actions tab.

## License

[DreamX-RoboConductor Non-Commercial Research and Personal Use License](LICENSE).

For non-commercial academic research, teaching, and personal non-commercial use only.
Commercial use is prohibited without a separate written license.
