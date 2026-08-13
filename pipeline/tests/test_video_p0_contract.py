"""Adversarial publication checks for the schema 2.2 video P0 model."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from pipeline.contracts import ContractValidationError, validate_snapshot
from pipeline.release import build_release, load_stage, write_stage
from pipeline.tests.test_release1 import NOW, fixture_collectors


@pytest.fixture()
def publication(tmp_path):
    return build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=fixture_collectors(),
    )


def _model(snapshot):
    return snapshot["decision_models"]["p0_video_liquidity"]


def _clause(snapshot, formula: str, clause_id: str):
    return next(
        item
        for item in _model(snapshot)["formulas"][formula]["clauses"]
        if item["clause_id"] == clause_id
    )


def test_generated_model_is_independent_from_audited_overall_and_alerts(publication):
    snapshot = publication.snapshot
    model = _model(snapshot)
    assert snapshot["schema_version"] == "2.2.0"
    assert model["model_id"] == "henren778_p0_liquidity"
    assert snapshot["overall_assessment"] == snapshot["switches"]["liquidity_fuel"]["assessment"]
    assert publication.alerts["alerts"] == snapshot["alerts"]
    assert all(alert.get("title") != model["label"] for alert in snapshot["alerts"])
    assert snapshot["composite"]["level"] in {
        "NORMAL", "WATCH", "ELEVATED", "STRESS", "UNAVAILABLE"
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda snapshot: snapshot.pop("decision_models"),
            "decision_models",
        ),
        (
            lambda snapshot: _clause(snapshot, "yellow", "sofr_positive_streak").update(
                current_value=True
            ),
            "does not reconcile",
        ),
        (
            lambda snapshot: _clause(snapshot, "yellow", "reserve_below_yellow").update(
                threshold=float("nan")
            ),
            "finite",
        ),
        (
            lambda snapshot: _clause(snapshot, "red", "reserve_below_red").update(
                threshold_unit="USD tn"
            ),
            "does not reconcile",
        ),
        (
            lambda snapshot: _model(snapshot)["source"]["segments"][0].update(
                timestamp_url="https://example.com/tampered"
            ),
            "audited segment",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["red"].update(
                triggered=not _model(snapshot)["formulas"]["red"]["triggered"]
            ),
            "truth values",
        ),
        (
            lambda snapshot: _model(snapshot).update(status="RED"),
            "status does not reconcile",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["yellow"]["clauses"][1].update(
                clause_id="sofr_positive_streak"
            ),
            "ID/order",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["yellow"].pop(
                "display_tex"
            ),
            "display_tex",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["yellow"].update(
                display_tex=r"\operatorname{TAMPERED}"
            ),
            "presentation does not reconcile",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["red"].update(
                plain_language="Tampered but non-empty."
            ),
            "presentation does not reconcile",
        ),
        (
            lambda snapshot: _model(snapshot)["notation"][1].update(
                key=_model(snapshot)["notation"][0]["key"]
            ),
            "duplicate keys",
        ),
        (
            lambda snapshot: _model(snapshot)["notation"][0].update(
                source_kind="VIDEO_SOURCE_RULE"
            ),
            "source_kind",
        ),
        (
            lambda snapshot: _model(snapshot)["notation"][0].update(
                definition="Tampered but non-empty."
            ),
            "notation content does not reconcile",
        ),
        (
            lambda snapshot: _model(snapshot)["formulas"]["red"]["routes"][0].update(
                display_tex="A"
            ),
            "unexpected display_tex",
        ),
    ],
)
def test_snapshot_model_tampering_fails_closed(publication, mutation, message):
    snapshot = deepcopy(publication.snapshot)
    mutation(snapshot)
    with pytest.raises(ContractValidationError, match=message):
        validate_snapshot(snapshot)


def test_schema_2_1_snapshot_is_hard_cut(publication):
    snapshot = deepcopy(publication.snapshot)
    snapshot["schema_version"] = "2.1.0"
    with pytest.raises(ContractValidationError, match="2.2.0"):
        validate_snapshot(snapshot)


def test_load_stage_rechecks_tampered_decision_model(publication, tmp_path):
    stage = write_stage(publication, tmp_path / "stage")
    path = stage / "snapshot.json"
    snapshot = json.loads(path.read_text())
    clause = _model(snapshot)["formulas"]["yellow"]["clauses"][0]
    clause["met"] = not clause["met"]
    path.write_text(json.dumps(snapshot))
    with pytest.raises(ContractValidationError, match="met does not reconcile"):
        load_stage(stage)


def test_srf_full_series_and_snapshot_fallback_keep_classification_metadata(publication):
    fields = {
        "accepted_amount_usd_bn",
        "alert_eligible_accepted_amount_usd_bn",
        "exercise_accepted_amount_usd_bn",
        "has_technical_exercise",
        "technical_exercise",
        "classification_complete",
    }
    full = publication.series_by_id["srf_accepted"]["observations"]
    short = publication.snapshot["metrics"]["srf_accepted"]["short_series"]
    assert full and short
    assert all(fields <= point.keys() for point in full)
    assert short == [
        {"date": point["date"], "value": point["value"], **{
            field: point[field] for field in fields
        }}
        for point in full[-22:]
    ]
