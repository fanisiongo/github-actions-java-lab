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
        raise ValidationError(f"{label}領域の開始・終了マーカーは、それぞれ1つずつ残してください")

    start = body.index(start_marker) + len(start_marker)
    end = body.index(end_marker)
    if start >= end:
        raise ValidationError(f"{label}領域のマーカー順序が正しくありません")

    paths: list[str] = []
    for raw_line in body[start:end].splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        paths.append(line)

    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise ValidationError(f"{label}領域に重複したパスがあります: {', '.join(duplicates)}")

    for path in paths:
        validate_path(path, label)

    return set(paths)


def validate_path(path: str, label: str) -> None:
    if path.startswith(("/", "./")):
        raise ValidationError(f"{label}にはリポジトリのルートからの相対パスを入力してください: {path}")
    if "\\" in path:
        raise ValidationError(f"{label}の区切り文字にはスラッシュ '/' を使用してください: {path}")
    if path.endswith("/"):
        raise ValidationError(f"{label}にはディレクトリではなくファイルを入力してください: {path}")
    if any(character in path for character in "*?["):
        raise ValidationError(f"{label}ではワイルドカードを使用できません: {path}")
    if ".." in PurePosixPath(path).parts:
        raise ValidationError(f"{label}に '..' を含めることはできません: {path}")


def load_actual_files(path: str) -> tuple[set[str], set[str]]:
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)

    if payload and isinstance(payload[0], list):
        files = [item for page in payload for item in page]
    else:
        files = payload

    if len(files) >= 3000:
        raise ValidationError(
            "PRに3000件以上のファイルが含まれているため、GitHubのファイル一覧APIで安全に検証できる範囲を超えています"
        )

    deleted: set[str] = set()
    updated: set[str] = set()

    for item in files:
        status = item.get("status", "").lower()
        filename = item.get("filename")
        if not filename:
            raise ValidationError("GitHubからファイルパスのない変更情報が返されました")

        if status == "removed":
            deleted.add(filename)
        elif status == "renamed":
            previous_filename = item.get("previous_filename")
            if not previous_filename:
                raise ValidationError(f"名前変更されたファイルに変更前のパスがありません: {filename}")
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
            "## 変更予定ファイル一覧の検証に成功しました",
            "",
            f"- 削除ファイル: {len(actual_deleted)}",
            f"- 更新ファイル: {len(actual_updated)}",
            "",
        ]
        return True, "\n".join(report)

    report = ["## 変更予定ファイル一覧の検証に失敗しました", ""]
    report += difference_lines("実際に削除されたが申告されていないファイル", undeclared_deleted, "+")
    report += difference_lines("削除予定として申告されたが実際には削除されていないファイル", nonexistent_deleted, "-")
    report += difference_lines("実際に更新されたが申告されていないファイル", undeclared_updated, "+")
    report += difference_lines("更新予定として申告されたが実際には更新されていないファイル", nonexistent_updated, "-")
    report += ["PRの説明にある変更予定ファイル一覧を修正するか、予定外の変更をPRから除外してください。", ""]
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
        expected_deleted = extract_paths(body, DELETED_START, DELETED_END, "削除ファイル")
        expected_updated = extract_paths(body, UPDATED_START, UPDATED_END, "更新ファイル")

        overlap = expected_deleted & expected_updated
        if overlap:
            raise ValidationError(
                "同じパスを削除ファイルと更新ファイルの両方に入力することはできません: "
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
            print("::error::変更予定ファイル一覧とPRの実際の変更内容が一致しません。Job Summaryを確認してください")
            return 1
        return 0
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        report = f"## 変更予定ファイル一覧の検証に失敗しました\n\n{error}\n"
        write_summary(args.summary, report)
        print(f"::error::{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

