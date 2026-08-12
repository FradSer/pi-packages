# Utils Pi Package

Utility skills for keeping project READMEs and changelogs accurate.

## Installation

```bash
# published
pi install npm:@fradser/utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

Skills are invoked as `/skill:<name>`.

## Skills

### `update-readme`

Keeps `README.md` and `README.zh-CN.md` synchronized with the project's current state. Run `/skill:update-readme` manually when adding, removing, or renaming project components.

### `update-changelog`

Creates or updates `CHANGELOG.md` in Keep a Changelog 1.1.0 format from tags and commit history. Run `/skill:update-changelog` manually before a release or when documenting changes.

## License

MIT
