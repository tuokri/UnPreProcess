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

from pathlib import Path

import pytest
from click.testing import CliRunner

from unpreprocess.main import MACRO_DEFINITIONS
from unpreprocess.main import main
from unpreprocess.main import process_source

_script_dir = Path(__file__).parent.resolve()
_data_dir = _script_dir / "data"


def test_upp(pytestconfig):
    input_data = (_data_dir / "SmallClass.uc").read_text()
    processed = process_source(input_data, MACRO_DEFINITIONS)
    expected = (_data_dir / "processed/SmallClass.uc").read_text()

    # Check .pytest_cache/ to debug the processed file.
    cache_dir = pytestconfig.cache.mkdir("upp_processed")
    path = cache_dir / "SmallClass.uc"
    path.write_text(processed)

    # Easier to see the diff in case the test fails.
    assert processed.splitlines() == expected.splitlines()
    assert processed == expected


def test_nested_macros_respect_parent_enablement():
    processed = process_source(
        "`if(false)\n"
        "outer disabled\n"
        "`if(true)\n"
        "inner must stay disabled\n"
        "`endif\n"
        "outer remains disabled\n"
        "`endif\n"
        "outside\n",
        {},
    )

    assert processed == (
        "///---> `if(false)\n"
        "///---> outer disabled\n"
        "///---> `if(true)\n"
        "///---> inner must stay disabled\n"
        "///---> `endif\n"
        "///---> outer remains disabled\n"
        "///---> `endif\n"
        "outside\n"
    )


def test_else_after_nested_macro_applies_to_outer_macro():
    processed = process_source(
        "`if(true)\n"
        "outer enabled\n"
        "`if(false)\n"
        "inner disabled\n"
        "`endif\n"
        "`else\n"
        "outer else disabled\n"
        "`endif\n",
        {},
    )

    assert processed == (
        "///---> `if(true)\n"
        "outer enabled\n"
        "///---> `if(false)\n"
        "///---> inner disabled\n"
        "///---> `endif\n"
        "///---> `else\n"
        "///---> outer else disabled\n"
        "///---> `endif\n"
    )


def test_backtick_prefixed_raw_identifier_is_evaluated():
    processed = process_source(
        "`if(`DEFINED && `UNDEFINED)\n"
        "disabled\n"
        "`endif\n",
        {"DEFINED": True},
    )

    assert processed == (
        "///---> `if(`DEFINED && `UNDEFINED)\n"
        "///---> disabled\n"
        "///---> `endif\n"
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        pytest.param(
            "`if true\n", "unsupported macro:",
            id="missing-opening-parenthesis",
        ),
        pytest.param(
            "`if((true)\n", "unsupported macro:",
            id="missing-closing-parenthesis",
        ),
        pytest.param(
            "`if(true &&)\n", "error evaluating expression:",
            id="invalid-expression",
        ),
        pytest.param(
            "`if(1 / 0)\n", "error evaluating expression:",
            id="expression-runtime-error",
        ),
        pytest.param(
            "ordinary line\n`else\n",
            "`else without an opening macro at line 2",
            id="unmatched-else",
        ),
        pytest.param(
            "`if(true)\n`else\n`else\n`endif\n",
            "duplicate `else at line 3",
            id="duplicate-else",
        ),
        pytest.param(
            "`if(false)\n`if(true)\n`else\n`else\n`endif\n`endif\n",
            "duplicate `else at line 4",
            id="duplicate-else-in-disabled-parent",
        ),
        pytest.param(
            "`if(true)\n", "unclosed macro conditional",
            id="unclosed-enabled-conditional",
        ),
        pytest.param(
            "`if(false)\n", "unclosed macro conditional",
            id="unclosed-disabled-conditional",
        ),
        pytest.param(
            "`if(true)\n`if(false)\n`endif\n",
            "unclosed macro conditional",
            id="unclosed-outer-conditional",
        ),
    ],
)
def test_invalid_macro_source_is_rejected(source, message):
    with pytest.raises(ValueError) as exc_info:
        process_source(source, {})

    assert message in str(exc_info.value)


@pytest.mark.parametrize(
    ("filename", "source", "options", "exception_type", "message"),
    [
        pytest.param(
            "input.txt", "ordinary line\n", [],
            RuntimeError, "unsupported file extension: '.txt'",
            id="unsupported-extension",
        ),
        pytest.param(
            "input.uc", "ordinary line\n", ["--define", "BROKEN"],
            ValueError, "not enough values to unpack",
            id="define-without-equals",
        ),
        pytest.param(
            "input.uc", "`if(true &&)\n", [],
            ValueError, "error evaluating expression:",
            id="invalid-expression",
        ),
        pytest.param(
            "input.uc", "`if(true)\n", [],
            ValueError, "unclosed macro conditional",
            id="unclosed-conditional",
        ),
    ],
)
def test_cli_error_preserves_input(
        tmp_path,
        filename,
        source,
        options,
        exception_type,
        message,
):
    path = tmp_path / filename
    path.write_text(source)
    original = path.read_bytes()

    result = CliRunner().invoke(main, [*options, str(path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, exception_type)
    assert message in str(result.exception)
    assert path.read_bytes() == original


def test_cli_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.uc"

    result = CliRunner().invoke(main, [str(path)])

    assert result.exit_code == 2
    assert "does not exist" in result.output
    assert not path.exists()


def test_cli_rejects_directory(tmp_path):
    result = CliRunner().invoke(main, [str(tmp_path)])

    assert result.exit_code == 2
    assert "is a directory" in result.output


def test_cli_recursive_expands_glob_patterns(tmp_path, monkeypatch):
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    top = tmp_path / "top.uc"
    nested = tmp_path / "sub" / "deep" / "nested.uc"
    other = tmp_path / "sub" / "other.txt"
    source = "`if(false)\nhidden\n`endif\n"
    for p in (top, nested, other):
        p.write_text(source)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["-r", "**/*.uc"])

    assert result.exit_code == 0, result.output
    expected = process_source(source, {"dev_build": False})
    assert top.read_text() == expected
    assert nested.read_text() == expected
    assert other.read_text() == source


def test_cli_glob_pattern_without_recursive_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["*.uc"])

    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_unmatched_endif_is_rejected():
    with pytest.raises(ValueError):
        process_source("`endif\n", {})


def test_macros_inside_block_comments_are_ignored():
    source = (
        "if (a)\n"
        "{\n"
        "/*\t`ifndef(ShippingPC)\n"
        "\tfoo();\n"
        "\t`endif*/\n"
        "\tbar();\n"
        "}\n"
        "/*\n"
        "`endif\n"
        "*/\n"
        "// `endif\n"
        "x = \"/*\"; `endif_not_a_comment\n"
    )

    assert process_source(source, {"ShippingPC": True}) == source
