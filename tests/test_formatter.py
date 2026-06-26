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

def test_format_json_files_bom_handling(tmp_path):
    # 写入带 UTF-8 BOM 的 JSON 文件
    bom_file = tmp_path / "bom.json"
    content = '{"b": 2, "a": 1}'
    # UTF-8 BOM: \xef\xbb\xbf
    bom_file.write_bytes(b'\xef\xbb\xbf' + content.encode('utf-8'))

    # 执行格式化，应该兼容读取并正确写入（不带 BOM，但已格式化）
    format_json_files(tmp_path)
    
    # 验证是否格式化成功
    expected = '{\n  "a": 1,\n  "b": 2\n}'
    assert bom_file.read_text(encoding="utf-8") == expected

def test_format_json_files_skips_hidden_dirs(tmp_path):
    # 创建隐藏目录 .git
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    
    # 写入一个未格式化的 JSON 文件
    json_file = git_dir / "config.json"
    original = '{"b": 2, "a": 1}'
    json_file.write_text(original)
    
    # 执行格式化，它应该跳过隐藏目录，保持文件不变
    format_json_files(tmp_path)
    assert json_file.read_text() == original
