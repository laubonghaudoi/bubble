from pathlib import Path

import pytest

from pipeline.io import PublicationError, promote_data_directory, staged_data_directory


def test_whole_directory_promotion_removes_old_files(tmp_path):
    public = tmp_path / "public"
    target = public / "data"
    target.mkdir(parents=True)
    (target / "old-v1.json").write_text("old")
    stage = staged_data_directory(public)
    (stage / "snapshot.json").write_text("v2")

    promote_data_directory(stage, target)

    assert (target / "snapshot.json").read_text() == "v2"
    assert not (target / "old-v1.json").exists()
    assert not list(public.glob(".data-*"))


def test_empty_stage_cannot_replace_last_good(tmp_path):
    public = tmp_path / "public"
    target = public / "data"
    target.mkdir(parents=True)
    (target / "snapshot.json").write_text("last-good")
    stage = staged_data_directory(public)

    with pytest.raises(PublicationError, match="missing or empty"):
        promote_data_directory(stage, target)

    assert (target / "snapshot.json").read_text() == "last-good"
