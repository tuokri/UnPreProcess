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

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

UPP_COMMENT_PREFIX = "///--->"

MACRO_ENTER_PREFIXES = [
    "`if",
]

MACRO_EXIT_PREFIXES = [
    "`endif",
]

# TODO: for any macro not defined in this list (or passed to the program by the user),
#   try to parse them as booleans, interpreting str->bool parse errors as falsy values.
MACRO_DEFINITIONS = {
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
            word = match.group(0)
            if word in ("or", "and", "not", "True", "False"):
                return word
            if word.lower() == "true":
                return "True"
            if word.lower() == "false":
                return "False"

            # If a raw identifier is passed, evaluate if it exists and is truthy.
            val = self.defines.get(word, False)
            return str(bool(val))

        py_expr = re.sub(r"\b[A-Za-z_]\w*\b", _resolve_identifier, cond)

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
    enabled: bool
    in_else_branch: bool = False

    # TODO: can't we just see depth from the length of the macro_stack?
    depth: int = 0


def enter_macro(
        line: str,
        evaluator: UScriptMacroEvaluator,
        current_ctx: MacroContext | None = None,
) -> MacroContext | None:
    # TODO: should this be a case-insensitive check?
    entered = any(line.lstrip().startswith(prefix) for prefix in MACRO_ENTER_PREFIXES)
    if not entered:
        return None

    # Naive ad-hoc parse.
    enabled = evaluator.evaluate_line(line)
    if enabled is None:
        raise ValueError(f"unsupported macro: '{line}'")

    return MacroContext(
        name=line.strip(),
        enabled=enabled,
        in_else_branch=current_ctx.in_else_branch if current_ctx else False,
        depth=current_ctx.depth + 1 if current_ctx else 0,
    )


def exit_macro(line: str) -> bool:
    # TODO: should this be a case-insensitive check?
    return any(line.lstrip().startswith(prefix) for prefix in MACRO_EXIT_PREFIXES)


def branch_macro(line: str) -> bool:
    # TODO: should this be a case-insensitive check?
    return line.lstrip().startswith("`else")


# TODO: do we need variants for processing
#  files inplace and with explicit output destination?
def process_file(file: Path) -> str:
    evaluator = UScriptMacroEvaluator(MACRO_DEFINITIONS)
    macro_stack: list[MacroContext] = []
    lines = file.read_text().splitlines(keepends=True)
    processed_lines: list[str] = []
    current_ctx: MacroContext | None = None
    is_macro_line: bool

    for line in lines:
        if (entered_ctx := enter_macro(line, evaluator, current_ctx)) is not None:
            print(f"push context: {entered_ctx}")
            macro_stack.append(entered_ctx)
            current_ctx = entered_ctx
            is_macro_line = True
        elif macro_stack and exit_macro(line):
            current_ctx = macro_stack.pop()
            print(f"pop context: {current_ctx}")
            is_macro_line = True
        elif current_ctx and branch_macro(line):
            print(f"in else branch for: {current_ctx.name}")
            current_ctx.in_else_branch = True
            is_macro_line = True
        else:
            is_macro_line = False

            # TODO: this feels bad and hacky?
            if current_ctx and not macro_stack:
                print("cleared current_ctx")
                current_ctx = None

        if current_ctx:
            # Always comment out macro lines.
            if is_macro_line:
                line_enabled = False
            else:
                line_enabled = current_ctx.enabled
                if current_ctx.in_else_branch:
                    line_enabled = not line_enabled

            if not line_enabled:
                if not line.rstrip():
                    # Only add whitespace between the prefix and line
                    # content if the line is not empty.
                    # ///--->\n
                    disabled_line = f"{UPP_COMMENT_PREFIX}{line}"
                else:
                    # ///---> LINE_CONTENT_HERE\n
                    disabled_line = f"{UPP_COMMENT_PREFIX} {line}"

                print(f"{disabled_line=}")
                line = disabled_line

        processed_lines.append(line)

    return "".join(processed_lines)


@click.command()
@click.argument(
    "files",
    nargs=-1,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def main(files: tuple[Path]) -> None:
    # TODO: allow taking in a custom list of macro definitions, e.g.;
    #   -d ShippingPC=True
    #   -d DEBUG=ON
    #   --define option=value

    for file in files:
        path = Path(file).resolve()
        print(f"processing '{path}'...")
        process_file(path)


if __name__ == "__main__":
    main()
