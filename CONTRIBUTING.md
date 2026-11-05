# Contributing to pedalpoint

Thanks for helping. This guide covers setup, testing and how changes get merged.
For design decisions and common pitfalls, read the
[developer guide](CLAUDE.md).

## Set up

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/EMSwank/pedalpoint
cd pedalpoint
uv sync --extra dev
```

Without uv, run `pip install -e ".[dev]"` instead.

## Run the tests

Unit tests are fast and need no model:

```sh
pytest tests/unit/ --cov=pedalpoint --cov-fail-under=90
```

Lint and formatting checks run in CI, so run them first:

```sh
ruff check src/ tests/
ruff format --check src/ tests/
```

Installer tests need [bats-core](https://github.com/bats-core/bats-core), from
`brew install bats-core` on macOS or `apt-get install bats` on Linux:

```sh
bats tests/install/
```

Integration tests need a real model server:

```sh
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=mlx pytest tests/integration/test_mlx.py -v
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=ollama pytest tests/integration/test_ollama.py -v
```

The skill has no Python behind it. Its checks are manual scenarios in
`tests/skill/scenarios/`.

## Make a change

1. Create a branch from `main`. Use the prefix that fits: `feat/`, `fix/`,
   `chore/`, `test/` or `docs/`.
2. Write a failing test, confirm it fails, then write the code that passes it.
3. Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
   messages, such as `fix: keep code blocks in doc drafts`.
4. Add a line to `CHANGELOG.md` if people using pedalpoint would notice the change.
5. Open a pull request against `main`. Pull requests are squash merged after
   review and passing checks.

Never commit directly to `main`, even for documentation.

## Coverage

| Module | Required coverage |
|---|---|
| `autostart.py`, `circuit_breaker.py`, `drafting.py`, `error_classifier.py`, `paths.py`, `stats.py` | 100% |
| `server.py` | At least 90% |
| Whole package | At least 90% |

## Documentation style

Documentation should work for everyone, including people using screen readers:

- Use one top-level heading, and do not skip heading levels.
- Give every image useful alt text.
- Make link text say where the link goes. Avoid "click here".
- Use words in prose and tables instead of symbols such as arrows.
- Spell out an abbreviation the first time you use it.
- Give every code block a language, such as `sh` or `text`.
- Use absolute links in `README.md`, because it is also shown on PyPI.

## Release

Maintainers release by updating the version in `pyproject.toml` and the date in
`CHANGELOG.md`, then pushing a `vX.Y.Z` tag from `main`. The tag publishes to
TestPyPI and then PyPI. The installer downloads the skill from that tag.
