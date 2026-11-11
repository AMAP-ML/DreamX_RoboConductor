# Dependencies

## Runtime and tests

| Operation | Requirement |
| --- | --- |
| View the website | Modern browser with native HTML, CSS, and JavaScript |
| Local static server | Python 3.10+ standard library |
| Source packaging and Python tests | Python standard library |
| Frontend tests | Node.js 18+ built-in modules |

Runtimes are installed separately. Upstream licenses:
[Python](https://docs.python.org/3/license.html) and
[Node.js](https://github.com/nodejs/node/blob/main/LICENSE).

## Asset preparation

The working repository uses these tools to prepare assets. They are outside
the downloadable source package.

| Tool | Use | Upstream license |
| --- | --- | --- |
| Pillow | Posters and image conversion | [MIT-CMU](https://pillow.readthedocs.io/en/stable/about.html#license) |
| Matplotlib | Comparison figures | [Matplotlib license](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE) |
| PyMuPDF / MuPDF | PDF figure extraction | [AGPL or commercial](https://pymupdf.io/licensing) |
| FFmpeg / ffprobe | Video processing | [LGPL baseline; optional GPL components](https://ffmpeg.org/legal.html) |
| x264 | H.264 encoding | [GPL-2.0-or-later](https://ffmpeg.org/general.html#x264) |
| imageio-ffmpeg | FFmpeg executable wrapper | [BSD-2-Clause wrapper](https://github.com/imageio/imageio-ffmpeg/blob/main/LICENSE) |

Preserve upstream license notices when adding dependencies to a distribution.
The source export is defined by `FILE_ALLOWLIST` in
`scripts/build_public_release.py`.
