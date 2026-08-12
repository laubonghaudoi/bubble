from pathlib import Path

import yaml


WORKFLOW_PATH = Path(".github/workflows/update-and-deploy.yml")


def workflow():
    # BaseLoader follows GitHub's string-oriented workflow syntax without
    # YAML 1.1 treating the key `on` as a boolean.
    return yaml.load(WORKFLOW_PATH.read_text(), Loader=yaml.BaseLoader)


def production_job():
    jobs = workflow()["jobs"]
    assert list(jobs) == ["update-test-build-deploy"]
    return jobs["update-test-build-deploy"]


def test_production_workflow_has_all_locked_triggers_and_dispatch_groups():
    triggers = workflow()["on"]
    assert set(triggers) == {"push", "schedule", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    assert {entry["cron"] for entry in triggers["schedule"]} == {
        "0 7 * * 2-6",
        "45 22 * * 4",
        "30 22 * * 5",
        "15 13 2 * *",
        "45 14 3 1,4,7,10 *",
    }
    group = triggers["workflow_dispatch"]["inputs"]["group"]
    assert group["required"] == "true"
    assert group["default"] == "all"
    assert group["options"] == [
        "all",
        "daily",
        "h41",
        "weekly",
        "monthly",
        "quarterly",
        "manual",
    ]


def test_workflow_requires_source_configuration_and_stage_only_update():
    job = production_job()
    assert "env" not in job
    steps = {step.get("name"): step for step in job["steps"] if "name" in step}
    preflight = steps["Require production source configuration"]
    assert preflight["env"] == {
        "FRED_API_KEY": "${{ secrets.FRED_API_KEY }}",
        "SEC_USER_AGENT": "${{ vars.SEC_USER_AGENT }}",
    }
    assert "Repository secret FRED_API_KEY is required." in preflight["run"]
    assert "Repository variable SEC_USER_AGENT is required." in steps[
        "Require production source configuration"
    ]["run"]

    update = steps["Fetch, validate, transform, and write schema v2 stage"]
    assert update["env"]["FRED_API_KEY"] == "${{ secrets.FRED_API_KEY }}"
    assert update["env"]["SEC_USER_AGENT"] == "${{ vars.SEC_USER_AGENT }}"
    assert update["env"]["SEC_FORM4_CACHE_DIR"] == (
        "${{ runner.temp }}/sec-form4-cache"
    )
    assert update["env"]["UPDATE_GROUP"] == "${{ steps.group.outputs.group }}"
    for command_part in (
        "python -m pipeline.update",
        "--mode incremental",
        '--group "$UPDATE_GROUP"',
        "--stage-only",
        '--stage-dir "$DATA_STAGE"',
    ):
        assert command_part in update["run"]

    python_tests = steps["Run Python tests"]
    assert python_tests["env"]["BUBBLE_DATA_DIR"] == "${{ runner.temp }}/bubble-data-stage"
    for step in job["steps"]:
        if step.get("name") not in {
            "Require production source configuration",
            "Fetch, validate, transform, and write schema v2 stage",
        }:
            assert "FRED_API_KEY" not in step.get("env", {})
            assert "SEC_USER_AGENT" not in step.get("env", {})


def test_workflow_orders_gates_before_atomic_promote_push_and_deploy():
    job = production_job()
    labels = [step.get("name") or step.get("uses") for step in job["steps"]]
    ordered = [
        "Require production source configuration",
        "Fetch, validate, transform, and write schema v2 stage",
        "Run Python tests",
        "Test and build against staged schema v2 data",
        "Atomically promote verified schema v2 stage",
        "Commit generated schema v2 data",
        "Deploy to GitHub Pages",
    ]
    assert [labels.index(label) for label in ordered] == sorted(
        labels.index(label) for label in ordered
    )

    steps = {step.get("name"): step for step in job["steps"] if "name" in step}
    frontend_script = steps["Test and build against staged schema v2 data"]["run"]
    assert "git archive HEAD" not in frontend_script
    assert "--exclude='./public/data'" in frontend_script
    assert 'cp -R "$DATA_STAGE" "$FRONTEND_CHECKOUT/public/data"' in frontend_script
    assert 'cd "$FRONTEND_CHECKOUT"' in frontend_script
    assert "npm ci" in frontend_script
    assert "npm test" in frontend_script
    assert "npm run build" in frontend_script
    assert "npm ci --prefix" not in frontend_script

    promote_script = steps["Atomically promote verified schema v2 stage"]["run"]
    assert (
        'python -m pipeline.update --promote-stage "$DATA_STAGE" --output public/data'
        in promote_script
    )

    commit_script = steps["Commit generated schema v2 data"]["run"]
    assert "git add public/data" in commit_script
    assert "git push" in commit_script
    assert "git push || true" not in commit_script


def test_sec_form4_private_cache_is_actions_cache_only():
    job = production_job()
    cache_steps = [
        step for step in job["steps"] if step.get("uses") == "actions/cache@v4"
    ]
    assert len(cache_steps) == 1
    cache = cache_steps[0]["with"]
    assert cache["path"] == "${{ runner.temp }}/sec-form4-cache"
    assert cache["key"].startswith("sec-form4-v1-")
    assert "sec-form4-v1-${{ runner.os }}-" in cache["restore-keys"]
    commit_step = next(
        step for step in job["steps"] if step.get("name") == "Commit generated schema v2 data"
    )
    assert "git add public/data" in commit_step["run"]
    assert "sec-form4-cache" not in commit_step["run"]


def test_only_one_workflow_deploys_pages_and_it_has_concurrency():
    deployers = [
        path
        for path in Path(".github/workflows").glob("*.yml")
        if "actions/deploy-pages" in path.read_text()
    ]
    assert deployers == [WORKFLOW_PATH]
    concurrency = workflow()["concurrency"]
    assert concurrency["group"] == "bubble-production-pages"
    assert concurrency["cancel-in-progress"] == "false"
