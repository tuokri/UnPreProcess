# MIT License
#
# Copyright (c) 2026 Tuomo Kriikkula
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Smoke test for the PyInstaller-built unpreprocess.exe.

Usage:
    python smoke_test.py <exe_path> [--expected-version X.Y.Z]
"""

import argparse
import difflib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run_command(
    exe: Path,
    args: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the exe with the given arguments and return the result."""
    return subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def check_version(exe: Path, expected_version: str | None) -> None:
    """Check that --version reports a real version."""
    result = run_command(exe, ["--version"])
    if result.returncode != 0:
        raise SystemExit(
            f"--version failed with exit code {result.returncode}: {result.stderr}"
        )

    output = result.stdout.strip()
    if not output:
        raise SystemExit("--version produced no output")

    if "unknown" in output.lower():
        raise SystemExit(f"--version contains 'unknown': {output}")

    if expected_version and output.rsplit(maxsplit=1)[-1] != expected_version:
        raise SystemExit(
            f"--version did not report expected version '{expected_version}': {output}"
        )

    print(f"  [OK] --version: {output}")


def check_help(exe: Path) -> None:
    """Check that --help works."""
    result = run_command(exe, ["--help"])
    if result.returncode != 0:
        raise SystemExit(
            f"--help failed with exit code {result.returncode}: {result.stderr}"
        )

    if "Options" not in result.stdout:
        raise SystemExit("--help output does not contain 'Options'")

    print("  [OK] --help works")


def check_processing(exe: Path, repo_root: Path) -> None:
    """Process a test file and compare with expected output."""
    test_input = repo_root / "tests" / "data" / "SmallClass.uc"
    test_expected = repo_root / "tests" / "data" / "processed" / "SmallClass.uc"

    if not test_input.exists():
        raise SystemExit(f"Test input not found: {test_input}")
    if not test_expected.exists():
        raise SystemExit(f"Expected output not found: {test_expected}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_file = tmp_path / "SmallClass.uc"
        shutil.copy2(test_input, test_file)

        result = run_command(exe, [str(test_file)])
        if result.returncode != 0:
            raise SystemExit(
                f"Processing failed with exit code {result.returncode}: {result.stderr}"
            )

        actual = test_file.read_text(encoding="utf-8")
        expected = test_expected.read_text(encoding="utf-8")

        if actual != expected:
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=str(test_expected),
                tofile=str(test_file),
            )
            raise SystemExit("Output mismatch:\n" + "".join(diff))

    print("  [OK] File processing matches expected output")


def check_scrubbed_env(exe: Path) -> None:
    """Run the exe with a minimal environment to prove it's standalone."""
    system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")

    scrubbed_env = {
        "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
        "PATH": system32,
        "TEMP": tempfile.gettempdir(),
        "TMP": tempfile.gettempdir(),
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = run_command(exe, ["--version"], env=scrubbed_env, cwd=tmp_path)
        if result.returncode != 0:
            raise SystemExit(
                f"--version with scrubbed env failed (exit {result.returncode}): {result.stderr}"
            )

        output = result.stdout.strip()
        if not output or "unknown" in output.lower():
            raise SystemExit(
                f"--version with scrubbed env gave suspicious output: {output!r}"
            )

    print("  [OK] Runs with scrubbed environment (standalone)")


def check_bundle(exe: Path) -> None:
    """Audit the bundle TOC for required DLLs."""
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is required to audit the executable bundle"
        ) from exc

    try:
        reader = CArchiveReader(str(exe))
        toc = list(reader.toc)
    except Exception as exc:
        raise SystemExit(f"Cannot read executable archive: {exc}") from exc

    names_lower = {name.lower() for name in toc}

    required_dlls = ["python314.dll", "vcruntime140.dll"]
    missing = [dll for dll in required_dlls if dll not in names_lower]

    if missing:
        raise SystemExit(f"Bundle is missing required DLLs: {missing}")

    print(f"  [OK] Bundle contains required DLLs ({len(toc)} entries total)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for unpreprocess.exe")
    parser.add_argument("exe", type=Path, help="Path to the built executable")
    parser.add_argument(
        "--expected-version", default=None, help="Expected version string"
    )
    args = parser.parse_args()

    exe = args.exe.resolve()
    if not exe.exists():
        raise SystemExit(f"Executable not found: {exe}")

    repo_root = Path(__file__).resolve().parent.parent

    print(f"Testing {exe.name}...")

    check_version(exe, args.expected_version)
    check_help(exe)
    check_processing(exe, repo_root)
    check_scrubbed_env(exe)
    check_bundle(exe)

    print("All checks passed.")


if __name__ == "__main__":
    main()
