from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ashare_evidence.research_artifacts import (
    BacktestArtifactView,
    ManualResearchArtifactView,
    Phase5HoldingPolicyExperimentArtifactView,
    Phase5HoldingPolicyStudyArtifactView,
    Phase5HorizonStudyArtifactView,
    Phase5ProducerContractStudyArtifactView,
    ReplayAlignmentArtifactView,
    ResearchArtifactManifestView,
    ValidationMetricsArtifactView,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
ARTIFACT_FOLDERS = {
    "rolling_validation": "manifests",
    "validation_metrics": "validation",
    "portfolio_backtest": "backtests",
    "replay_alignment": "replays",
    "manual_review": "manual_reviews",
    "phase5_horizon_study": "studies",
    "phase5_holding_policy_study": "studies",
    "phase5_holding_policy_experiment": "studies",
    "phase5_producer_contract_study": "studies",
    "shortpick_lab": "shortpick_lab",
}

ArtifactModel = TypeVar("ArtifactModel", bound=BaseModel)


def _artifact_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("ASHARE_ARTIFACT_ROOT")
    return Path(configured) if configured else DEFAULT_ARTIFACT_ROOT


def artifact_root_from_database_url(database_url: str | None) -> Path:
    if database_url and database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///")).resolve()
        return db_path.parent / "artifacts"
    return _artifact_root()


def artifact_path(artifact_type: str, artifact_id: str, *, root: Path | None = None) -> Path:
    folder = ARTIFACT_FOLDERS[artifact_type]
    return _artifact_root(root) / folder / f"{artifact_id}.json"


def _write_model(model: BaseModel, artifact_type: str, artifact_id: str, *, root: Path | None = None) -> Path:
    target = artifact_path(artifact_type, artifact_id, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _read_model(model_type: type[ArtifactModel], artifact_type: str, artifact_id: str, *, root: Path | None = None) -> ArtifactModel:
    target = artifact_path(artifact_type, artifact_id, root=root)
    payload = json.loads(target.read_text(encoding="utf-8"))
    return model_type.model_validate(payload)


def _read_model_if_exists(
    model_type: type[ArtifactModel],
    artifact_type: str,
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ArtifactModel | None:
    if not artifact_id:
        return None
    target = artifact_path(artifact_type, artifact_id, root=root)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return model_type.model_validate(payload)


def write_shortpick_lab_artifact(
    *,
    artifact_id: str,
    payload: dict,
    root: Path | None = None,
) -> Path:
    target = artifact_path("shortpick_lab", artifact_id, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def read_shortpick_lab_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> dict | None:
    if not artifact_id:
        return None
    target = artifact_path("shortpick_lab", artifact_id, root=root)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def write_manifest(manifest: ResearchArtifactManifestView, *, root: Path | None = None) -> Path:
    return _write_model(manifest, "rolling_validation", manifest.artifact_id, root=root)


def read_manifest(artifact_id: str, *, root: Path | None = None) -> ResearchArtifactManifestView:
    return _read_model(ResearchArtifactManifestView, "rolling_validation", artifact_id, root=root)


def read_manifest_if_exists(artifact_id: str | None, *, root: Path | None = None) -> ResearchArtifactManifestView | None:
    return _read_model_if_exists(ResearchArtifactManifestView, "rolling_validation", artifact_id, root=root)


def write_validation_metrics(
    artifact: ValidationMetricsArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "validation_metrics", artifact.artifact_id, root=root)


def read_validation_metrics(artifact_id: str, *, root: Path | None = None) -> ValidationMetricsArtifactView:
    return _read_model(ValidationMetricsArtifactView, "validation_metrics", artifact_id, root=root)


def read_validation_metrics_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ValidationMetricsArtifactView | None:
    return _read_model_if_exists(ValidationMetricsArtifactView, "validation_metrics", artifact_id, root=root)


def write_backtest_artifact(artifact: BacktestArtifactView, *, root: Path | None = None) -> Path:
    return _write_model(artifact, "portfolio_backtest", artifact.artifact_id, root=root)


def portfolio_backtest_artifact_id(portfolio_key: str | None) -> str | None:
    normalized = str(portfolio_key or "").strip()
    if not normalized:
        return None
    return f"portfolio-backtest:{normalized}"


def read_backtest_artifact(artifact_id: str, *, root: Path | None = None) -> BacktestArtifactView:
    return _read_model(BacktestArtifactView, "portfolio_backtest", artifact_id, root=root)


def read_backtest_artifact_if_exists(artifact_id: str | None, *, root: Path | None = None) -> BacktestArtifactView | None:
    return _read_model_if_exists(BacktestArtifactView, "portfolio_backtest", artifact_id, root=root)


def resolve_backtest_artifact(
    *,
    configured_artifact_id: str | None,
    portfolio_key: str | None,
    root: Path | None = None,
) -> tuple[str | None, BacktestArtifactView | None]:
    normalized_configured = str(configured_artifact_id or "").strip() or None
    canonical_artifact_id = portfolio_backtest_artifact_id(portfolio_key)
    candidate_ids: list[str] = []
    if normalized_configured:
        candidate_ids.append(normalized_configured)
    if canonical_artifact_id and canonical_artifact_id not in candidate_ids:
        candidate_ids.append(canonical_artifact_id)
    for artifact_id in candidate_ids:
        artifact = read_backtest_artifact_if_exists(artifact_id, root=root)
        if artifact is not None:
            return artifact_id, artifact
    if candidate_ids:
        return candidate_ids[0], None
    return None, None


def write_replay_alignment_artifact(
    artifact: ReplayAlignmentArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "replay_alignment", artifact.artifact_id, root=root)


def read_replay_alignment_artifact(artifact_id: str, *, root: Path | None = None) -> ReplayAlignmentArtifactView:
    return _read_model(ReplayAlignmentArtifactView, "replay_alignment", artifact_id, root=root)


def read_replay_alignment_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ReplayAlignmentArtifactView | None:
    return _read_model_if_exists(ReplayAlignmentArtifactView, "replay_alignment", artifact_id, root=root)


def write_manual_research_artifact(
    artifact: ManualResearchArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "manual_review", artifact.artifact_id, root=root)


def read_manual_research_artifact(artifact_id: str, *, root: Path | None = None) -> ManualResearchArtifactView:
    return _read_model(ManualResearchArtifactView, "manual_review", artifact_id, root=root)


def read_manual_research_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ManualResearchArtifactView | None:
    return _read_model_if_exists(ManualResearchArtifactView, "manual_review", artifact_id, root=root)


def write_phase5_horizon_study_artifact(
    artifact: Phase5HorizonStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_horizon_study", artifact.artifact_id, root=root)


def read_phase5_horizon_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HorizonStudyArtifactView:
    return _read_model(Phase5HorizonStudyArtifactView, "phase5_horizon_study", artifact_id, root=root)


def read_phase5_horizon_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HorizonStudyArtifactView | None:
    return _read_model_if_exists(Phase5HorizonStudyArtifactView, "phase5_horizon_study", artifact_id, root=root)


def write_phase5_holding_policy_study_artifact(
    artifact: Phase5HoldingPolicyStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_holding_policy_study", artifact.artifact_id, root=root)


def read_phase5_holding_policy_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyStudyArtifactView:
    return _read_model(Phase5HoldingPolicyStudyArtifactView, "phase5_holding_policy_study", artifact_id, root=root)


def read_phase5_holding_policy_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyStudyArtifactView | None:
    return _read_model_if_exists(
        Phase5HoldingPolicyStudyArtifactView,
        "phase5_holding_policy_study",
        artifact_id,
        root=root,
    )


def write_phase5_holding_policy_experiment_artifact(
    artifact: Phase5HoldingPolicyExperimentArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_holding_policy_experiment", artifact.artifact_id, root=root)


def read_phase5_holding_policy_experiment_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyExperimentArtifactView:
    return _read_model(Phase5HoldingPolicyExperimentArtifactView, "phase5_holding_policy_experiment", artifact_id, root=root)


def read_phase5_holding_policy_experiment_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyExperimentArtifactView | None:
    return _read_model_if_exists(
        Phase5HoldingPolicyExperimentArtifactView,
        "phase5_holding_policy_experiment",
        artifact_id,
        root=root,
    )


def write_phase5_producer_contract_study_artifact(
    artifact: Phase5ProducerContractStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_producer_contract_study", artifact.artifact_id, root=root)


def read_phase5_producer_contract_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5ProducerContractStudyArtifactView:
    return _read_model(Phase5ProducerContractStudyArtifactView, "phase5_producer_contract_study", artifact_id, root=root)


def read_phase5_producer_contract_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5ProducerContractStudyArtifactView | None:
    return _read_model_if_exists(
        Phase5ProducerContractStudyArtifactView,
        "phase5_producer_contract_study",
        artifact_id,
        root=root,
    )
