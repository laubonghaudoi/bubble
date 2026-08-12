import json
import os
from pathlib import Path

from pipeline.contracts import SCHEMA_VERSION, validate_publication


DATA_DIR = Path(os.environ.get("BUBBLE_DATA_DIR", "public/data"))


def payload(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def test_published_artifact_is_one_complete_v2_contract():
    snapshot = payload("snapshot.json")
    manifest = payload("manifest.json")
    series_by_id = {
        item["metric_id"]: payload(item["series_path"].removeprefix("data/"))
        for item in manifest["metrics"]
    }

    validate_publication(snapshot, manifest, series_by_id)
    assert snapshot["schema_version"] == SCHEMA_VERSION
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert len(series_by_id) == len(snapshot["metrics"])


def test_missing_is_null_real_zero_is_preserved_and_aliases_are_removed():
    snapshot = payload("snapshot.json")
    for metric in snapshot["metrics"].values():
        if metric["availability"] in {"MANUAL_READY", "UNAVAILABLE_FREE"}:
            assert metric["value"] is None

    srf = snapshot["metrics"]["srf_accepted"]
    if srf["quality"]["status"] == "OK" and srf["observation_date"] is not None:
        assert srf["value"] is not None

    assert not (DATA_DIR / "series" / "sofr_iorb_spread.json").exists()
    assert not (DATA_DIR / "series" / "on_rrp.json").exists()
    assert not (DATA_DIR / "series" / "srf_usage.json").exists()


def test_alerts_events_and_every_series_are_versioned_v2():
    alerts = payload("alerts.json")
    events = payload("events.json")
    assert alerts["schema_version"] == SCHEMA_VERSION
    assert isinstance(alerts["alerts"], list)
    assert events["schema_version"] == SCHEMA_VERSION
    assert isinstance(events["events"], list)

    manifest = payload("manifest.json")
    expected = {item["metric_id"] for item in manifest["metrics"]}
    actual = {path.stem for path in (DATA_DIR / "series").glob("*.json")}
    assert actual == expected
