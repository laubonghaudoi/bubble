"""Command-line entry point for staged schema 2.2.0 publication."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pipeline.release import (
    VALID_GROUPS,
    VALID_MODES,
    build_release,
    promote_stage,
    run,
    write_stage,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--mode", choices=sorted(VALID_MODES), default="incremental")
    command.add_argument("--group", choices=sorted(VALID_GROUPS), default="all")
    command.add_argument("--output", type=Path, default=Path("public/data"))
    command.add_argument("--stage-only", action="store_true")
    command.add_argument("--stage-dir", type=Path)
    command.add_argument("--promote-stage", type=Path)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.promote_stage is not None:
        if args.stage_only or args.stage_dir is not None:
            parser().error("--promote-stage cannot be combined with staging options")
        promote_stage(args.promote_stage, data_dir=args.output)
        return 0
    if args.stage_only and args.stage_dir is None:
        parser().error("--stage-only requires --stage-dir")
    if args.stage_dir is not None and not args.stage_only:
        parser().error("--stage-dir requires --stage-only")
    if args.stage_only:
        publication = build_release(
            mode=args.mode, group=args.group, data_dir=args.output
        )
        write_stage(publication, args.stage_dir)
    else:
        run(args.mode, group=args.group, data_dir=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
