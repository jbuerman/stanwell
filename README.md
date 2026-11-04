[![CI](https://github.com/jbuerman/stanwell/actions/workflows/ci.yml/badge.svg)](https://github.com/jbuerman/stanwell/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# Stanwell

*Have enthusiasm. Work sustainably.*

Stanwell analyses working time recorded in Toggl to help you understand how much you work and how that time is distributed across projects, activities and working patterns.

## Quick setup

Initialise Stanwell:

```bash
stanwell init
```

Synchronise historical data. Repeat until all missing data has been downloaded:

```bash
stanwell sync-missing
```

Refresh recent entries when needed:

```bash
stanwell refresh-recent
```

Open the interactive dashboard:

```bash
stanwell dashboard
```

## Development

```bash
uv sync --all-groups
```

Format and lint the project:

```bash
uv run make tidy
```

Run the CI checks locally:

```bash
uv run make ci
```

### Documentation

Build the Sphinx documentation:

```bash
uv run make docs
```

Open `docs/_build/html/index.html` to view the generated documentation.

### Integration tests

Create an environment file containing an API token and workspace ID using `.env.integration.example` as a template.

Then run:

```bash
uv run --env-file .env.integration pytest -m integration
```

## Licence

Stanwell is released under the [MIT Licence](LICENSE).
