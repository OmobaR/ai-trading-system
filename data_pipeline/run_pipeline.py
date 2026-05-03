#!/usr/bin/env python3
"""
Phase 1 Data Pipeline Entry Point
"""
import argparse
import sys

from data_pipeline.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Phase 1 Trading Data Pipeline")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process")
    parser.add_argument("--timeframes", nargs="+", help="Specific timeframes (M1, H1, etc)")
    parser.add_argument("--skip-ingestion", action="store_true", help="Skip CSV/DB ingestion")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation")
    parser.add_argument("--skip-export", action="store_true", help="Skip Parquet export")
    parser.add_argument("--csv-dir", help="Override CSV input directory")
    parser.add_argument("--db-uri", help="Override database URI")

    args = parser.parse_args()

    kwargs = {}
    if args.csv_dir or args.db_uri:
        from data_pipeline.config.settings import override_config
        override_config(
            csv_input_dir=args.csv_dir,
            db_uri=args.db_uri
        )

    if args.symbols:
        kwargs["symbols"] = args.symbols
    if args.timeframes:
        from data_pipeline.config.timeframes import Timeframe
        kwargs["timeframes"] = [Timeframe(tf) for tf in args.timeframes]
    kwargs["skip_ingestion"] = args.skip_ingestion
    kwargs["skip_validation"] = args.skip_validation
    kwargs["skip_export"] = args.skip_export

    try:
        report = run_pipeline(**kwargs)

        print("\n" + "=" * 60)
        print("PIPELINE SUMMARY")
        print("=" * 60)
        print(f"Total Symbols: {report.total_symbols}")
        print(f"Total Timeframes: {report.total_timeframes}")
        print(f"Passed: {report.passed_symbols}")
        print(f"Failed: {report.failed_symbols}")

        if report.failed_symbols > 0:
            print("\nFailed Symbols:")
            for sym, summary in report.symbols.items():
                if not summary.overall_passed:
                    print(f"  - {sym}: score={summary.overall_integrity_score:.3f}")
                    for tf, r in summary.timeframes.items():
                        if not r.passed:
                            print(f"      {tf}: {r.errors}")

        sys.exit(0 if report.failed_symbols == 0 else 1)

    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
