# RELEASE

## Scope
This document defines build/test/publish readiness steps for:
- `sdk-node`
- `sdk-python`

No publish is performed by this document.

## Versioning strategy
- Source of truth: Git tags (`vX.Y.Z`).
- Keep SDK versions in:
  - `sdk-node/package.json` -> `version`
  - `sdk-python/pyproject.toml` -> `project.version`
- Release flow:
  1. bump versions in both SDK metadata files
  2. run SDK tests
  3. create annotated tag `vX.Y.Z`
  4. publish from clean tag checkout

## Pre-release checks (required)
From repo root:
```bash
make test-sdk-node
make test-sdk-python
```

## Node SDK (npm) readiness and commands

Current blocker:
- `sdk-node/package.json` has `"private": true`, which blocks npm publish.

When releasing:
```bash
cd sdk-node
npm ci
npm run build
npm test
npm pack
# npm publish --access public
```

Required npm metadata before first publish:
- `name` (already set)
- `version`
- `license`
- `repository`
- `author`
- `files` whitelist (recommended for publish artifact hygiene)

## Python SDK (PyPI) readiness and commands

From repo root:
```bash
cd sdk-python
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
# python -m twine upload dist/*
```

Current metadata is minimal and should be expanded before first public release:
- `license`
- `authors`
- `readme`
- `project.urls` (homepage/repository/issues)
- classifiers

## Dist artifact policy
- Do not commit generated dist outputs unless the repository explicitly adopts that policy.
- Current convention in this repo: build artifacts are generated in CI/local and not tracked.
