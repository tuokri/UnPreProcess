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

from unpreprocess.main import process_file
from unpreprocess.main import process_source

_script_dir = Path(__file__).parent.resolve()
_data_dir = _script_dir / "data"


def test_upp(pytestconfig):
    processed = process_file(_data_dir / "SmallClass.uc")
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


def test_unmatched_endif_is_rejected():
    with pytest.raises(ValueError):
        process_source("`endif\n", {})
