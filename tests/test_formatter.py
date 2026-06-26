import json
import pytest
from transplay_mcp.core.formatter import format_json_files

def test_format_json_files_recursive_and_sorted(tmp_path):
    # Prepare files in a temporary directory
    dir_a = tmp_path / "dir_a"
    dir_a.mkdir()
    dir_b = dir_a / "dir_b"
    dir_b.mkdir()

    # Create unformatted JSON files
    file_1 = tmp_path / "file1.json"
    file_2 = dir_a / "file2.json"
    file_3 = dir_b / "file3.json"
    file_non_json = tmp_path / "text.txt"

    data_1 = {"c": 3, "a": 1, "b": 2}
    data_2 = {"nested": {"y": 2, "x": 1}, "alpha": "beta"}
    data_3 = {"z": 10, "arr": [{"b": 2, "a": 1}]}

    file_1.write_text(json.dumps(data_1))
    file_2.write_text(json.dumps(data_2))
    file_3.write_text(json.dumps(data_3))
    file_non_json.write_text("just some text")

    # Run formatter
    format_json_files(tmp_path)

    # Verify formatting (2-space indentation, keys sorted alphabetically)
    # file_1 verification
    content_1 = file_1.read_text(encoding="utf-8")
    expected_1 = '{\n  "a": 1,\n  "b": 2,\n  "c": 3\n}'
    assert content_1 == expected_1

    # file_2 verification
    content_2 = file_2.read_text(encoding="utf-8")
    # Both top-level and nested dicts must be sorted
    expected_2 = '{\n  "alpha": "beta",\n  "nested": {\n    "x": 1,\n    "y": 2\n  }\n}'
    assert content_2 == expected_2

    # file_3 verification
    content_3 = file_3.read_text(encoding="utf-8")
    # Dicts inside lists should also have keys sorted
    expected_3 = '{\n  "arr": [\n    {\n      "a": 1,\n      "b": 2\n    }\n  ],\n  "z": 10\n}'
    assert content_3 == expected_3

    # Non-json file should not be modified
    assert file_non_json.read_text() == "just some text"

def test_format_json_files_invalid_json(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid json")

    # We expect format_json_files to raise ValueError or JSONDecodeError when encountering malformed JSON
    with pytest.raises((json.JSONDecodeError, ValueError)):
        format_json_files(tmp_path)
