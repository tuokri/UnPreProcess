# UnPreProcess

[![Coverage Status](https://tuokri.github.io/UnPreProcess/coverage-badge.svg)](https://tuokri.github.io/UnPreProcess/cov_html/index.html)

---

## Description

Just a simple utility that handles macros in UnrealScript files in a low-effort way to make the
[UnrealScript](https://marketplace.visualstudio.com/items?itemName=EliotVU.uc)
plugin for Visual Studio Code not break on macros.

## Installation

### Windows executable (no Python required)

Download the latest `unpreprocess-<version>-windows-x64.exe` from the
[Releases](https://github.com/tuokri/UnPreProcess/releases) page.

Download the matching `.sha256` file as well. On Windows, compare the hash at
the start of that file with the `Hash` value from:

```powershell
Get-FileHash .\unpreprocess-*.exe -Algorithm SHA256
```

### From source

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/tuokri/UnPreProcess.git
cd UnPreProcess
uv sync
uv run python -m unpreprocess.main --help
```

## Usage

Windows usage example using the release executable.

```PowerShell
# Display help.
.\unpreprocess-0.3.3-windows-x64.exe --help

# Process all Rising Storm 2: Vietnam SDK UScript files.
# The --jobs argument is optional and can be set to the number
# of your CPU cores to speed up processing in parallel.
.\unpreprocess-0.3.3-windows-x64.exe --jobs 8 --recursive "C:\Program Files (x86)\Steam\steamapps\common\Rising Storm 2\Development\Src\**\*.uc"
```

## Development

### Run verification and build

```bash
uv sync
uv run ruff check .
uv run --group build ty check .
uv run ty check src tests
uv run ruff format --check .
uv run pytest -v
uv build
```

### TODOs

- Verify processed files compile successfully?
