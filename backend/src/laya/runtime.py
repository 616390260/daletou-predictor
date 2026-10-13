"""Load only independent local Laya models and validate decision scores."""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path

from ..config import MODELS
from .dataset import _issue


def validate_model_cutoff(trained_through_issue: str, target_issue: str) -> None:
    """Reject scoring a target at or before the model's training cutoff."""
    _issue(trained_through_issue)
    _issue(target_issue)
    if trained_through_issue >= target_issue:
        raise ValueError(f"Model cutoff {trained_through_issue} must precede target {target_issue}")


def _score(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("Candidate score must be a finite number between 0 and 1")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Candidate score must be a finite number between 0 and 1") from exc
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Candidate score must be a finite number between 0 and 1")
    return score


def choose_candidate(candidates: list[dict]) -> dict:
    """Select an existing candidate, breaking ties by configured model order."""
    if not candidates:
        raise ValueError("At least one candidate is required")
    ranked = []
    for candidate in candidates:
        model = candidate.get("model")
        if model not in MODELS:
            raise ValueError(f"Unknown candidate model: {model}")
        ranked.append((_score(candidate.get("score")), -MODELS.index(model), candidate))
    return max(ranked, key=lambda item: item[:2])[2]


class LayaScorer:
    """Lazy MPS inference restricted to local daletou model directories."""

    def __init__(self, model_path: Path, trained_through_issue: str):
        _issue(trained_through_issue)
        root = (Path.home() / "laya-lab" / "models").resolve()
        self.model_path = Path(model_path).expanduser().resolve()
        try:
            relative = self.model_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Laya model must be within ~/laya-lab/models/daletou-*") from exc
        if not relative.parts or not relative.parts[0].startswith("daletou-"):
            raise ValueError("Laya model must be within ~/laya-lab/models/daletou-*")
        config = json.loads((self.model_path / "rl_agent_config.json").read_text(encoding="utf-8"))
        task = config.get("task") or {}
        question = task.get("question") or {}
        if (task.get("name") != "daletou-decision" or question.get("type") != "choice"
                or set(question.get("criteria", {})) != {"A", "B"}):
            raise ValueError("Laya config must use daletou-decision with A/B choice criteria")
        self.question = question
        if "trained_through_issue" in config and config["trained_through_issue"] != trained_through_issue:
            raise ValueError("Laya config cutoff differs from the requested checkpoint cutoff")
        self.config = config
        self.base_path = None
        if config.get("adapter_type") not in {None, "head-only"}:
            raise ValueError("Unsupported Laya adapter format")
        if config.get("adapter_type") == "head-only":
            bases = (Path.home() / "laya-lab/hf/hub/models--convaiinnovations--laya-multilingual/snapshots").resolve()
            self.base_path = Path(config.get("base_model_path", "")).expanduser().resolve()
            if self.base_path.parent != bases or not (self.base_path / "model.safetensors").is_file():
                raise ValueError("Laya adapter base must be a cached multilingual snapshot")
        self.trained_through_issue = trained_through_issue
        self._agent = None

    def score(self, state: str, target_issue: str) -> float:
        """Return P(A) as a model score after enforcing the time boundary."""
        validate_model_cutoff(self.trained_through_issue, target_issue)
        if self._agent is None:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["USE_TF"] = "0"
            import laya
            if self.base_path is None:
                self._agent = laya.Agent(str(self.model_path), device="mps")
            else:
                from safetensors.torch import load_file
                from laya.common import clamp_temperature
                digest = hashlib.sha256((self.base_path / "model.safetensors").read_bytes()).hexdigest()
                if digest != self.config.get("base_checkpoint_sha256"):
                    raise ValueError("Laya base checkpoint digest mismatch")
                agent = laya.Agent(str(self.base_path), device="mps")
                head = load_file(str(self.model_path / "model.safetensors"))
                expected = {key for key in agent.model.state_dict() if not key.startswith("encoder.")}
                if set(head) != expected:
                    raise ValueError("Laya adapter must contain exactly the decision head")
                agent.model.load_state_dict(head, strict=False)
                agent.model.eval()
                temperatures = self.config.get("temperature")
                if not isinstance(temperatures, list) or len(temperatures) != 3:
                    raise ValueError("Laya adapter requires three calibration temperatures")
                agent.temperature_raw = temperatures
                agent.temperature = [clamp_temperature(value) for value in temperatures]
                agent.temperature_by_options = {}
                agent.temperature_by_options_raw = {}
                self._agent = agent
        probabilities = self._agent.predict(state, {"s": self.question})["answers"]["s"]["probabilities"]
        if set(probabilities) != {"A", "B"}:
            raise ValueError("Laya answer must provide A/B probabilities")
        positive, negative = _score(probabilities["A"]), _score(probabilities["B"])
        if abs(positive + negative - 1.0) > 1e-4:
            raise ValueError("Laya A/B probabilities must sum to one")
        return positive
