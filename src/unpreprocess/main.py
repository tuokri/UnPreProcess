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

import logging
import re
import sys
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
            cond
        )
        cond = re.sub(
            r"`notdefined\s*\(\s*([A-Za-z_]\w*)\s*\)",
            lambda m: str(m.group(1) not in self.defines),
            cond
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
        branch_enabled = (
            not self.condition if self.in_else_branch else self.condition
        )
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


def process_source(
        source: str,
        definitions: dict[str, Any],
) -> str:
    evaluator = UScriptMacroEvaluator(definitions)
    macro_stack: list[MacroContext] = []
    processed_lines: list[str] = []

    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        pop_after_line = False

        if (entered_ctx := enter_macro(
                line,
                evaluator,
                macro_stack[-1].enabled if macro_stack else True,
        )) is not None:
            logger.debug("push context: {}", entered_ctx)
            macro_stack.append(entered_ctx)
            is_macro_line = True
        elif branch_macro(line):
            if not macro_stack:
                raise ValueError(f"`else without an opening macro at line {line_number}")
            if macro_stack[-1].in_else_branch:
                raise ValueError(f"duplicate `else at line {line_number}")

            logger.debug("in else branch for: {}", macro_stack[-1].name)
            macro_stack[-1].in_else_branch = True
            is_macro_line = True
        elif exit_macro(line):
            if not macro_stack:
                raise ValueError(f"`endif without an opening macro at line {line_number}")

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


# TODO: do we need variants for processing
#  files inplace and with explicit output destination?
def process_file(file: Path) -> str:
    return process_source(
        file.read_text(),
        MACRO_DEFINITIONS,
    )


@click.command()
@click.version_option(__version__)
@click.argument(
    "files",
    nargs=-1,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
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
def main(
        files: tuple[Path],
        dry_run: bool,
        define: tuple[str],
) -> None:
    # Do a simple -d KEY=VALUE parse.
    # TODO: maybe also allow clearing the hard-coded global definitions?
    for d in define:
        key, value = d.split("=", maxsplit=1)
        MACRO_DEFINITIONS[key] = value

    # TODO: for high file counts, it would perhaps be nice to have
    #   a producer and consumer architecture. Right no we just process
    #   files one by one and overwrite the original.

    for file in files:
        path = Path(file).resolve()
        logger.info("processing '{}'...", path)

        # Naive safety check.
        if not path.suffix == ".uc":
            raise RuntimeError(f"unsupported file extension: '{path.suffix}'")

        # TODO: backups?

        processed_text = process_file(path)
        if not dry_run:
            logger.info("writing '{}'...", path)
            path.write_text(processed_text)


if __name__ == "__main__":
    main()
