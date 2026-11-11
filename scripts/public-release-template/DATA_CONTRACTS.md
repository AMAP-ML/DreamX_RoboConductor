# Frontend data contracts

The examples in `fixtures/` are synthetic payloads for the interfaces below.

## Demo

`dist/data/demo.json` follows `schemas/demo.schema.json`. The root and each
episode have `synthetic: true`. Episode IDs are unique. Each episode includes
`title`, `summary`, `outcome`, `category`, and a `steps` array of title/detail
pairs. Categories are `arrangement` and `inspection`.

## Showcase homepage

`src/showcase/dist/assets/app.js` loads `data/page-data.json`.

| Object | Fields |
| --- | --- |
| Root | `updatedAt`, `simulation`, `real`, `walkthrough`; optional `media` |
| `simulation` | `taskCount`, `trials`, `successes`, `perfectTasks`, `turns.successMedian`, `tasks`, `featured` |
| Simulation task | `id`, `name`, `trials`, `successes`, `outcomes` |
| Simulation outcome | `id`, `seed`, `turns`, `success` |
| Featured item | `id`, `task`, `title`, `video`, `poster`, `seed`, `turns`, `taskSuccesses`, `taskTrials` |
| `real` | `taskCount`, `plannedTaskCount`, `trials`, `confirmedTrials`, `successes`, `tasks` |
| Real task | `id`, `title`, `instructionEn`, `episodes` |
| Real episode | `id`, `archiveId`, `scene`, `outcome`, `video`, `poster`; optional `turns`, `observations`, `wallClockSeconds`, `videoSeconds` |
| `walkthrough` | `id`, `task`, `seed`, `manual.task` as `[label, value]` pairs, `manual.tips`, `steps` |
| Walkthrough step | `turn`, `event`, `frames.head`, `frames.wrist`, `commands`, `results`; optional `done`, `success` |
| `media` | Original relative path → `{src, thumbnail?}` for web playback assets |

Counters match the component arrays. Each task's result matrix uses its own
trial count. Place video and image files under `media/` and use relative paths.
Scene labels and narrative fields are rendered as text.

## Archive

`src/showcase/dist/archive/catalog.js` registers the catalog:

```js
window.EVALUATION_CATALOG = /* catalog JSON */;
```

Platforms have `id`, `name`, `kind`, `summary`, and `tasks`. Tasks have `id`,
`name`, `backend`, `summary`, and `episodes`. Each episode summary supplies
`id`, `backend`, `task`, `data_file`, and result fields. An episode's local
`episodes/.../data.js` file registers its payload:

```js
window.registerEpisode(/* episode JSON */);
```

Generate these JavaScript registrations with a JSON serializer. The catalog
and episode schemas are in `schemas/archive.schema.json`.

`steps[].images` maps `head_camera`, `left_camera`, and `right_camera` to local
image paths. `manual.text` is plain text with limited Markdown formatting;
`manual.media` contains local asset references. Optional fields include
narration, commands, robot state, token usage, and timing.

## Episode language

The English archive reads per-episode text from
`archive/translations/en/<episode-id>.json`. It contains `id`,
`manualSourceSha256`, translated instruction/summary/manual fields, and one
narration entry per recorded step. The original episode file supplies images,
actions, states, and the Chinese text. Switching languages preserves the
selected replay turn.
