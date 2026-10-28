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

"""Process certain macros in UnrealScript files to make
it easier for LSPs to parse the code. This implementation
is extremely naïve and far from a real preprocessor.
"""

import concurrent.futures
import glob
import logging
import re
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from loguru import logger

from unpreprocess import __version__

logger.remove()
logger.add(sys.stderr, level=logging.INFO)

UPP_COMMENT_PREFIX = "///--->"

MACRO_HEADER_RE = re.compile(r"^\s*`(?:if|ifdef|ifndef)\b")
MACRO_EXIT_RE = re.compile(r"^\s*`endif\b")
MACRO_ELSE_RE = re.compile(r"^\s*`else\b")

# TODO: for any macro not defined in this list (or passed to the program by the user),
#   try to parse them as booleans, interpreting str->bool parse errors as falsy values.
MACRO_DEFINITIONS: dict[str, bool | str] = {
    "ShippingPC": True,
    "__TW_WWISE_": True,
    "RO_": True,
    "FINAL_RELEASE": True,
    "FINAL_RELEASE_DEBUGCONSOLE": True,
    "dev_build": False,
}


class UScriptMacroEvaluator:
    def __init__(self, defines: dict[str, Any]):
        self.defines = defines

    @staticmethod
    def _extract_macro(line: str) -> tuple[str, str] | None:
        """Extracts (macro_type, condition_body) handling nested parentheses."""
        line = line.strip()
        match = re.match(r"^`(if|ifdef|ifndef)\s*\(", line)
        if not match:
            return None

        macro_type = match.group(1)
        start_idx = match.end()

        depth = 1
        for i in range(start_idx, len(line)):
            if line[i] == "(":
                depth += 1
            elif line[i] == ")":
                depth -= 1
                if depth == 0:
                    return macro_type, line[start_idx:i]
        return None

    def evaluate_line(self, line: str) -> bool | None:
        """
        Evaluates a macro line to True or False.
        Returns None if the line does not contain a supported macro header.
        """
        extracted = self._extract_macro(line)
        if not extracted:
            return None

        macro_type, cond = extracted[0].strip(), extracted[1].strip()

        # Handle `ifdef(VAR)` and `ifndef(VAR)` shorthand.
        if macro_type == "ifdef":
            return cond in self.defines
        if macro_type == "ifndef":
            return cond not in self.defines

        # 1. Resolve built-in `isdefined(VAR)` and `notdefined(VAR)` calls.
        cond = re.sub(
            r"`isdefined\s*\(\s*([A-Za-z_]\w*)\s*\)",
            lambda m: str(m.group(1) in self.defines),
            cond,
        )
        cond = re.sub(
            r"`notdefined\s*\(\s*([A-Za-z_]\w*)\s*\)",
            lambda m: str(m.group(1) not in self.defines),
            cond,
        )

        # 2. Convert standard C-style boolean operators to Python equivalents.
        cond = cond.replace("||", " or ").replace("&&", " and ")
        cond = re.sub(r"!\s*", " not ", cond)

        # 3. Resolve literals (`true`/`false`) and raw macro names.
        def _resolve_identifier(match: re.Match) -> str:
            word = match.group(1)
            if word in ("or", "and", "not", "True", "False"):
                return word
            if word.lower() == "true":
                return "True"
            if word.lower() == "false":
                return "False"

            # If a raw identifier is passed, evaluate if it exists and is truthy.
            val = self.defines.get(word, False)
            return str(bool(val))

        logger.debug("cond: {}", cond)
        py_expr = re.sub(r"`?([A-Za-z_]\w*)\b", _resolve_identifier, cond)
        logger.debug("py_expr: {}", py_expr)

        # 4. Safely evaluate the boolean expression.
        try:
            return bool(eval(py_expr, {"__builtins__": {}}, {}))
        except Exception as err:
            raise ValueError(
                f"error evaluating expression: '{cond}' (parsed: '{py_expr}')"
            ) from err


@dataclass
class MacroContext:
    name: str
    condition: bool
    parent_enabled: bool
    in_else_branch: bool = False

    @property
    def enabled(self) -> bool:
        branch_enabled = not self.condition if self.in_else_branch else self.condition
        return self.parent_enabled and branch_enabled


def enter_macro(
    line: str,
    evaluator: UScriptMacroEvaluator,
    parent_enabled: bool,
) -> MacroContext | None:
    if not MACRO_HEADER_RE.match(line):
        return None

    # Naive ad-hoc parse.
    condition = evaluator.evaluate_line(line)
    if condition is None:
        raise ValueError(f"unsupported macro: '{line}'")

    return MacroContext(
        name=line.strip(),
        condition=condition,
        parent_enabled=parent_enabled,
    )


def exit_macro(line: str) -> bool:
    return MACRO_EXIT_RE.match(line) is not None


def branch_macro(line: str) -> bool:
    return MACRO_ELSE_RE.match(line) is not None


def comment_out(line: str) -> str:
    separator = "" if not line.rstrip() else " "
    return f"{UPP_COMMENT_PREFIX}{separator}{line}"


def ends_in_block_comment(line: str, in_block_comment: bool) -> bool:
    """Returns whether a `/* ... */` block comment is still open at the end
    of the line, given whether one was open at the start of the line.

    Handles `//` line comments and string/name literals so that comment
    markers inside them do not affect the state.
    """
    i = 0
    n = len(line)
    quote: str | None = None

    while i < n:
        c = line[i]
        pair = line[i : i + 2]

        if in_block_comment:
            if pair == "*/":
                in_block_comment = False
                i += 2
                continue
        elif quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif pair == "//":
            break
        elif pair == "/*":
            in_block_comment = True
            i += 2
            continue
        elif c in ('"', "'"):
            quote = c

        i += 1

    return in_block_comment


def process_source(
    source: str,
    definitions: dict[str, Any],
) -> str:
    evaluator = UScriptMacroEvaluator(definitions)
    macro_stack: list[MacroContext] = []
    processed_lines: list[str] = []  # TODO: type error on purpose!
    in_block_comment = False

    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        pop_after_line = False
        # Macros inside block comments are not real macros, ignore them.
        line_starts_in_comment = in_block_comment
        in_block_comment = ends_in_block_comment(line, in_block_comment)

        if line_starts_in_comment:
            is_macro_line = False
        elif (
            entered_ctx := enter_macro(
                line,
                evaluator,
                macro_stack[-1].enabled if macro_stack else True,
            )
        ) is not None:
            logger.debug("push context: {}", entered_ctx)
            macro_stack.append(entered_ctx)
            is_macro_line = True
        elif branch_macro(line):
            if not macro_stack:
                raise ValueError(
                    f"`else without an opening macro at line {line_number}"
                )
            if macro_stack[-1].in_else_branch:
                raise ValueError(f"duplicate `else at line {line_number}")

            logger.debug("in else branch for: {}", macro_stack[-1].name)
            macro_stack[-1].in_else_branch = True
            is_macro_line = True
        elif exit_macro(line):
            if not macro_stack:
                raise ValueError(
                    f"`endif without an opening macro at line {line_number}"
                )

            logger.debug("pop context: {}", macro_stack[-1])
            is_macro_line = True
            pop_after_line = True
        else:
            is_macro_line = False

        if is_macro_line or (macro_stack and not macro_stack[-1].enabled):
            disabled_line = comment_out(line)
            logger.debug("disabled_line: {}", disabled_line)
            processed_lines.append(disabled_line)
        else:
            processed_lines.append(line)

        if pop_after_line:
            macro_stack.pop()

    if macro_stack:
        raise ValueError("unclosed macro conditional")

    return "".join(processed_lines)


def expand_patterns(patterns: Iterable[Path], recursive: bool) -> list[Path]:
    """Expands the given paths into a de-duplicated list of files.

    Without `recursive`, every path must be an existing file.
    With `recursive`, paths containing glob patterns (`*`, `?`, `[...]`,
    and `**` for recursive directory matching) are expanded to all matching
    files. Paths without patterns are treated as literal file paths.
    """
    expanded: list[Path] = []
    seen: set[Path] = set()

    for pattern in patterns:
        pattern_str = str(pattern)

        if recursive and glob.has_magic(pattern_str):
            matches = sorted(
                Path(m)
                for m in glob.glob(pattern_str, recursive=True)
                if Path(m).is_file()
            )
            if not matches:
                logger.warning("pattern '{}' did not match any files", pattern_str)
        else:
            if not pattern.exists():
                raise click.BadParameter(
                    f"'{pattern_str}' does not exist.", param_hint="FILES"
                )
            if not pattern.is_file():
                raise click.BadParameter(
                    f"'{pattern_str}' is a directory.", param_hint="FILES"
                )
            matches = [pattern]

        for match in matches:
            resolved = match.resolve()
            if resolved not in seen:
                seen.add(resolved)
                expanded.append(match)

    return expanded


# TODO: do we need variants for processing
#  files inplace and with explicit output destination?
def process_file(file: Path, dry_run: bool = False):
    # Naive safety check.
    if file.suffix != ".uc":
        raise RuntimeError(f"unsupported file extension: '{file.suffix}'")

    processed = process_source(
        file.read_text(encoding="utf-8", errors="replace"),
        MACRO_DEFINITIONS,
    )

    if not dry_run:
        logger.info("writing '{}'...", file)
        file.write_text(processed, encoding="utf-8", errors="replace")


@click.command()
@click.version_option(__version__)
@click.argument(
    "files",
    nargs=-1,
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Run the program without writing any output.",
)
@click.option(
    "--define",
    "-d",
    multiple=True,
    help="Define a macro. Can be used multiple times.",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Interpret files as patterns and recursively process matching files.",
)
@click.option(
    "--jobs",
    "-j",
    type=int,
    default=1,
    help="Number of parallel jobs to run. Defaults to 1.",
)
def main(
    files: tuple[Path],
    dry_run: bool,
    define: tuple[str],
    recursive: bool,
    jobs: int,
) -> None:
    begin = time.perf_counter()

    # Do a simple -d KEY=VALUE parse.
    # TODO: maybe also allow clearing the hard-coded global definitions?
    for d in define:
        key, value = d.split("=", maxsplit=1)
        MACRO_DEFINITIONS[key] = value

    # With -r, expand glob patterns (* and **) into all matching files.
    # Existence is validated here, as patterns need not exist as paths.
    all_files = expand_patterns(files, recursive)

    futures: dict[Path, concurrent.futures.Future] = {}
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for file in all_files:
            path = Path(file).resolve()
            logger.info("processing '{}'...", path)
            # TODO: backups?
            futures[path] = executor.submit(process_file, path, dry_run=dry_run)

    concurrent.futures.wait(futures.values())
    for path, future in futures.items():
        # TODO: maybe report total number of exceptions and then raise the first one?
        exc = future.exception()
        if exc is not None:
            logger.error("error processing '{}': {}: {}", path, type(exc).__name__, exc)
            raise exc

    end = time.perf_counter()
    logger.info("processed {} files in {:.2f} seconds", len(futures), end - begin)


if __name__ == "__main__":
    main()
