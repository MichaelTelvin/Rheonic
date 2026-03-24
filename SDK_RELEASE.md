# SDK Release

## Source of truth

- Root version file: [`VERSION`](VERSION)
- Sync metadata before building or publishing:

```bash
python3 scripts/sync_version.py
```

Version mapping:
- npm: exact semver from `VERSION`
- Python: semver mapped to PEP 440 prerelease format
  - `0.2.0-beta.1` -> `0.2.0b1`

## Checklist

- Update [`VERSION`](VERSION)
- Run:

```bash
python3 scripts/sync_version.py
make test-sdk-node
make test-sdk-python
```

- Review:
  - [`sdk-node/CHANGELOG.md`](sdk-node/CHANGELOG.md)
  - [`sdk-python/CHANGELOG.md`](sdk-python/CHANGELOG.md)
- Build dry runs:

```bash
cd sdk-node && npm pack
cd sdk-python && python -m build && python -m twine check dist/*
```

## Beta publish commands

Node beta prerelease format:
- `0.2.0-beta.1`

Node beta publish:

```bash
cd sdk-node
npm ci
npm run build
npm test
npm publish --tag next --access public
```

Python beta prerelease format:
- `0.2.0b1`

Python beta publish:

```bash
cd sdk-python
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

## Release notes template

### Summary
- Why this beta build exists:

### Added
- 

### Changed
- 

### Fixed
- 

### Upgrade notes
- 
