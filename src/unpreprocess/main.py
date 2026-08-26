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
it easier for LSPs to parse the code.
"""

from dataclasses import dataclass
from pathlib import Path

import click

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
}


@dataclass
class MacroContext:
    name: str
    defined: bool


def enter_macro(line: str) -> MacroContext | None:
    # TODO: return macro context if entering a macro block.
    #   E.g., whether this macro enters a block that
    #   is conditional (`ifdef vs. `ifndef, etc.), and
    #   the conditional and its value.
    entered = any(line.lstrip().startswith(prefix) for prefix in MACRO_ENTER_PREFIXES)
    if not entered:
        return None

    # Assuming X is defined:
    # `if(`isdefined(X))    -> {"X": True}
    # `if(`notdefined(X))   -> {"X": False}
    # `ifdef(X)             -> {"X": True}
    # `ifndef(X)            -> {"X": False}
    # TODO: `if(...

    # Naive ad-hoc parse.
    # TODO

    # TODO: build it!
    return MacroContext("dummy", True)


def exit_macro(line: str) -> bool:
    return any(line.lstrip().startswith(prefix) for prefix in MACRO_EXIT_PREFIXES)


def branch_macro(line: str) -> bool:
    return False


def process_file(file: Path) -> None:
    macro_stack: list[MacroContext] = []

    for line in file.read_text().splitlines():
        if (ctx := enter_macro(line)) is not None:
            # TODO: push context.
            print(f"push context: {ctx}")
            macro_stack.append(ctx)
        elif exit_macro(line):
            # TODO: pop context.
            popped_ctx = macro_stack.pop()
            print(f"pop context: {popped_ctx}")
        elif branch_macro(line):
            # TODO: handle it.
            pass


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
