# UnPreProcess

[![Coverage Status](https://tuokri.github.io/UnPreProcess/coverage-badge.svg)](https://tuokri.github.io/UnPreProcess/cov_html/index.html)

---

## Description

Just a simple utility that handles macros in UnrealScript files in a low-effort way to make the
[UnrealScript](https://marketplace.visualstudio.com/items?itemName=EliotVU.uc)
plugin for Visual Studio Code not break on macros.

## Installation

### Windows Executable (no Python required)

Download the latest `unpreprocess-<version>-windows-x64.exe` from the
[Releases](https://github.com/tuokri/UnPreProcess/releases) page.

# TODO: steps for checksum verification?

### From Source

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/tuokri/UnPreProcess.git
cd UnPreProcess
uv sync
uv run python -m unpreprocess.main --help
```

## Usage

TODO

## Development TODOs

- Verify processed files compile successfully?
