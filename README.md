# INQ High Caliber

Standalone **High Caliber / Основний калібр** battle progress indicator for World of Tanks.

The mod is extracted from the old `rajcel.inBattleStatistics` High Caliber logic and rewritten as an independent modern mod in the same general structure as the other INQ mods.

## What it shows

- game High Caliber (`mainGun`) achievement icon;
- damage still required to reach 20% of the enemy team's starting HP;
- `Done!` after the threshold is reached;
- `Wasted!` after a qualifying hit on a living ally.

The progress threshold is:

```text
ceil(total enemy team HP / 5)
```

Enemy damage events reduce the remaining value.

## Runtime dependency

The UI uses the same GameFace/Wulf approach as current INQ HUD mods and requires **OpenWG.Gameface**.

It does **not** depend on the old `rajcel.core`, `inBattleStatistics`, XVM, or the original IBS package.

## Configuration

On first start the mod creates:

```text
mods/configs/highcaliber/settings.json
```

Default options include screen offsets, scale, colors, and Done/Wasted text toggles.

## Source layout

```text
python/gui/mods/mod_highcaliber.py
resources/in/mods/configs/res_map/highcaliber_gameface.json
resources/in/gui/gameface/mods/highcaliber/HighCaliber/
build.py
build.json
.github/workflows/build-wotmod.yml
```

## Build

The GitHub workflow **Build me.inq.highcaliber.wotmod** can be started manually from Actions. It validates JS/JSON, compiles the client Python with Python 2.7 via the builder fallback, creates an uncompressed `.wotmod`, uploads the artifact, and publishes a release.

Local build:

```bash
python build.py --version 0.1.0
```

If Python 2.7 is not installed locally, the builder can fall back to Docker `python:2.7`.

## Notes

This reproduces the recovered old mod's live progress logic. It is an in-battle indicator, not a server-side guarantee that the final medal will be awarded.
