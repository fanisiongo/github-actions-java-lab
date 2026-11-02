#!/usr/bin/env python3
"""Validate declared PR file lists against GitHub's changed-file response."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import PurePosixPath


DELETED_START = "<!-- expected-deleted-files:start -->"
DELETED_END = "<!-- expected-deleted-files:end -->"
UPDATED_START = "<!-- expected-updated-files:start -->"
UPDATED_END = "<!-- expected-updated-files:end -->"


class ValidationError(ValueError):
    """Raised when the PR declaration cannot be parsed safely."""


def extract_paths(body: str, start_marker: str, end_marker: str, label: str) -> set[str]:
    if body.count(start_marker) != 1 or body.count(end_marker) != 1:
        raise ValidationError(f"{label}区域的开始和结束标记必须各保留一个")

    start = body.index(start_marker) + len(start_marker)
    end = body.index(end_marker)
    if start >= end:
        raise ValidationError(f"{label}区域的标记顺序不正确")

    paths: list[str] = []
    for raw_line in body[start:end].splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        paths.append(line)

    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise ValidationError(f"{label}区域存在重复路径: {', '.join(duplicates)}")

    for path in paths:
        validate_path(path, label)

    return set(paths)


def validate_path(path: str, label: str) -> None:
    if path.startswith(("/", "./")):
        raise ValidationError(f"{label}必须填写仓库根目录的相对路径: {path}")
    if "\\" in path:
        raise ValidationError(f"{label}必须使用正斜杠 '/': {path}")
    if path.endswith("/"):
        raise ValidationError(f"{label}不能填写目录，只能填写文件: {path}")
    if any(character in path for character in "*?["):
        raise ValidationError(f"{label}不能使用通配符: {path}")
    if ".." in PurePosixPath(path).parts:
        raise ValidationError(f"{label}不能包含 '..': {path}")


def load_actual_files(path: str) -> tuple[set[str], set[str]]:
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)

    if payload and isinstance(payload[0], list):
        files = [item for page in payload for item in page]
    else:
        files = payload

    deleted: set[str] = set()
    updated: set[str] = set()

    for item in files:
        status = item.get("status", "").lower()
        filename = item.get("filename")
        if not filename:
            raise ValidationError("GitHub返回了缺少文件路径的变更记录")

        if status == "removed":
            deleted.add(filename)
        elif status == "renamed":
            previous_filename = item.get("previous_filename")
            if not previous_filename:
                raise ValidationError(f"重命名文件缺少原路径: {filename}")
            deleted.add(previous_filename)
            updated.add(filename)
        else:
            updated.add(filename)

    return deleted, updated


def difference_lines(title: str, paths: set[str], prefix: str) -> list[str]:
    if not paths:
        return []
    return [f"### {title}", "", *[f"{prefix} `{path}`" for path in sorted(paths)], ""]


def build_report(
    expected_deleted: set[str],
    expected_updated: set[str],
    actual_deleted: set[str],
    actual_updated: set[str],
) -> tuple[bool, str]:
    undeclared_deleted = actual_deleted - expected_deleted
    nonexistent_deleted = expected_deleted - actual_deleted
    undeclared_updated = actual_updated - expected_updated
    nonexistent_updated = expected_updated - actual_updated

    passed = not any(
        (
            undeclared_deleted,
            nonexistent_deleted,
            undeclared_updated,
            nonexistent_updated,
        )
    )

    if passed:
        report = [
            "## 预期文件清单校验通过",
            "",
            f"- 删除文件: {len(actual_deleted)}",
            f"- 更新文件: {len(actual_updated)}",
            "",
        ]
        return True, "\n".join(report)

    report = ["## 预期文件清单校验失败", ""]
    report += difference_lines("实际删除但未申报", undeclared_deleted, "+")
    report += difference_lines("已申报删除但实际未删除", nonexistent_deleted, "-")
    report += difference_lines("实际更新但未申报", undeclared_updated, "+")
    report += difference_lines("已申报更新但实际未更新", nonexistent_updated, "-")
    report += ["请修正PR描述中的预期文件清单，或从PR中移除非预期修改。", ""]
    return False, "\n".join(report)


def write_summary(path: str, report: str) -> None:
    with open(path, "a", encoding="utf-8") as file:
        file.write(report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files-json", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    try:
        body = os.environ.get("PR_BODY", "")
        expected_deleted = extract_paths(body, DELETED_START, DELETED_END, "删除文件")
        expected_updated = extract_paths(body, UPDATED_START, UPDATED_END, "更新文件")

        overlap = expected_deleted & expected_updated
        if overlap:
            raise ValidationError(
                "同一路径不能同时填写在删除文件和更新文件中: "
                + ", ".join(sorted(overlap))
            )

        actual_deleted, actual_updated = load_actual_files(args.files_json)
        passed, report = build_report(
            expected_deleted,
            expected_updated,
            actual_deleted,
            actual_updated,
        )
        write_summary(args.summary, report)
        print(report)

        if not passed:
            print("::error::预期文件清单与PR实际变更不一致，请查看Job Summary")
            return 1
        return 0
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        report = f"## 预期文件清单校验失败\n\n{error}\n"
        write_summary(args.summary, report)
        print(f"::error::{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

