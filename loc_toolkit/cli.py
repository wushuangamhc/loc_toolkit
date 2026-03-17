from __future__ import annotations

import argparse
import json
from pathlib import Path

from loc_toolkit.artifacts.glossary_builder import build_glossary
from loc_toolkit.artifacts.report_writer import write_csv_rows, write_json
from loc_toolkit.artifacts.tm_builder import build_tm
from loc_toolkit.config import load_project_config
from loc_toolkit.core.validator import compare_protected_tokens
from loc_toolkit.core.vdf_reader import read_vdf_tokens
from loc_toolkit.workflows.full_runner import run_full_translation
from loc_toolkit.workflows.incremental_runner import run_incremental_translation
from loc_toolkit.workflows.single_file_runner import run_file_translation


def _dump_report(report: dict, report_dir: Path | None, basename: str) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report_dir:
        write_json(report_dir / f"{basename}.json", report)
        write_csv_rows(
            report_dir / f"{basename}.csv",
            report["rows"],
            ["file", "locale", "key", "source_text", "candidate_text", "generator_status", "validator_status", "error_codes", "manual_review_reason", "accepted", "model"],
        )


def _common_translate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--config")
    parser.add_argument("--source-locale", default="schinese")
    parser.add_argument("--target-lang", choices=["zh", "en", "ru"], required=True)
    parser.add_argument("--target-locale")
    parser.add_argument("--report-dir")
    parser.add_argument("--generate-tm", action="store_true")
    parser.add_argument("--generate-glossary", action="store_true")
    parser.add_argument("--writeback", action="store_true")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--approval-policy", default="report-only")


def main() -> None:
    parser = argparse.ArgumentParser(prog="loc-toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate_parser = subparsers.add_parser("translate")
    translate_sub = translate_parser.add_subparsers(dest="translate_mode", required=True)

    full_parser = translate_sub.add_parser("full")
    _common_translate_args(full_parser)

    incremental_parser = translate_sub.add_parser("incremental")
    _common_translate_args(incremental_parser)
    incremental_parser.add_argument("--baseline-manifest", required=True)

    file_parser = translate_sub.add_parser("file")
    _common_translate_args(file_parser)
    file_parser.add_argument("--source-file", required=True)

    artifacts_parser = subparsers.add_parser("artifacts")
    artifacts_sub = artifacts_parser.add_subparsers(dest="artifact_mode", required=True)
    tm_parser = artifacts_sub.add_parser("tm")
    tm_parser.add_argument("--report", required=True)
    tm_parser.add_argument("--output-dir", required=True)
    glossary_parser = artifacts_sub.add_parser("glossary")
    glossary_parser.add_argument("--report", required=True)
    glossary_parser.add_argument("--output-dir", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_sub = validate_parser.add_subparsers(dest="validate_mode", required=True)
    validate_file = validate_sub.add_parser("file")
    validate_file.add_argument("--source-file", required=True)
    validate_file.add_argument("--candidate-file", required=True)
    validate_string = validate_sub.add_parser("string")
    validate_string.add_argument("--source", required=True)
    validate_string.add_argument("--candidate", required=True)

    args = parser.parse_args()

    if args.command == "translate":
        config = load_project_config(
            project_root=args.project_root,
            config_path=args.config,
            target_lang=args.target_lang,
            source_locale=args.source_locale,
            target_locale=args.target_locale,
            model=args.model,
            approval_policy=args.approval_policy,
            writeback=args.writeback,
            report_dir=args.report_dir,
            generate_tm=args.generate_tm,
            generate_glossary=args.generate_glossary,
        )
        report_dir = Path(args.report_dir).resolve() if args.report_dir else None
        if args.translate_mode == "full":
            report = run_full_translation(config)
            _dump_report(report, report_dir, "full_translation_report")
            return
        if args.translate_mode == "incremental":
            baseline_manifest = json.loads(Path(args.baseline_manifest).read_text(encoding="utf-8"))
            report = run_incremental_translation(config, baseline_manifest)
            _dump_report(report, report_dir, "incremental_translation_report")
            return
        report = run_file_translation(config, args.source_file)
        _dump_report(report, report_dir, "file_translation_report")
        return

    if args.command == "artifacts":
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        output_dir = Path(args.output_dir).resolve()
        if args.artifact_mode == "tm":
            tm = build_tm(report)
            write_json(output_dir / "tm.json", tm)
            write_csv_rows(output_dir / "tm.csv", tm["rows"], ["source", "target", "file", "key", "locale_pair", "status"])
            print(json.dumps(tm, ensure_ascii=False, indent=2))
            return
        glossary = build_glossary(report)
        write_json(output_dir / "glossary.json", glossary)
        write_csv_rows(output_dir / "glossary.csv", glossary["rows"], ["term", "translation", "file", "key", "locale_pair", "confidence", "confirmed", "source_type"])
        print(json.dumps(glossary, ensure_ascii=False, indent=2))
        return

    if args.validate_mode == "string":
        print(json.dumps(compare_protected_tokens(args.source, args.candidate), ensure_ascii=False, indent=2))
        return

    source_tokens = read_vdf_tokens(Path(args.source_file).resolve())
    candidate_tokens = read_vdf_tokens(Path(args.candidate_file).resolve())
    rows = []
    for key, source_text in source_tokens.items():
        candidate_text = candidate_tokens.get(key)
        if candidate_text is None:
            rows.append({"key": key, "status": "missing", "error_codes": ["TARGET_KEY_MISSING"]})
            continue
        result = compare_protected_tokens(source_text, candidate_text)
        rows.append({"key": key, "status": result["status"], "error_codes": [error["code"] for error in result["errors"]]})
    print(json.dumps({"rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
