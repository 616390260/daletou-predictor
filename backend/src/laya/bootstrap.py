"""Prepare the pinned multilingual base before offline Laya inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


BASE_REPO = "convaiinnovations/laya-multilingual"
BASE_REVISION = "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67"
BASE_SHA256 = "9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204"
SUPPORT_SHA256 = {
    "rl_agent_config.json": ("25061739243b617ad88d1219ba6f8a9c86c5881ca28df024fa2d9b3b2fcc30c6",),
    "encoder/config.json": ("83f6916d13ef0f556ac461f28308dc2bffa7ebeadee8ec9e2db5812020ea5bb4",),
    "tokenizer/tokenizer_config.json": (
        "424b69444bf7b5809dc2cd2e36d0bd71b8055124dd24274d6db3c655d38205e7",
        "6c6b2d8e3c84ce0e671c129cd6b374b235d6f9863042a5836358d00a89bbb5a1",
    ),
    "tokenizer/tokenizer.json": ("609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f",),
}
BASE_FILES = ("model.safetensors", "rl_agent_config.json", "encoder/config.json",
              "tokenizer/tokenizer_config.json", "tokenizer/tokenizer.json")


def _digest(path: Path) -> str:
    """@returns Streaming SHA256 without loading a full base checkpoint into RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_base(dataset: Path, version: str) -> Path:
    """Verify committed metadata and cache the one permitted base revision.

    @param dataset Directory containing committed manifests and adapters.
    @param version Existing daletou checkpoint version; no training is performed.
    @returns Verified local multilingual snapshot, ready for offline inference.
    """
    if not re.fullmatch(r"daletou-[a-z0-9-]{1,60}", version):
        raise ValueError("Invalid checkpoint version")
    dataset = Path(dataset)
    manifest = json.loads((dataset / "manifests" / f"{version}.json").read_text())
    adapter = dataset / "adapters" / f"{version}.json"
    config = json.loads(adapter.read_text())
    if manifest.get("version") != version:
        raise ValueError("Checkpoint metadata mismatch: version")
    for key in ("version", "trained_through_issue", "source_sha256"):
        if not manifest.get(key) or config.get(key) != manifest[key]:
            raise ValueError(f"Checkpoint metadata mismatch: {key}")
    if config.get("adapter_type") != "head-only":
        raise ValueError("Bootstrap requires a head-only adapter")
    if (config.get("base_checkpoint_sha256") != BASE_SHA256
            or manifest.get("base_checkpoint_sha256") != BASE_SHA256):
        raise ValueError("Pinned Laya base checkpoint digest metadata mismatch")
    head = dataset / "adapters" / f"{version}.safetensors"
    if _digest(head) != manifest.get("checkpoint_sha256"):
        raise ValueError("Committed checkpoint digest mismatch")

    home = Path.home() / "laya-lab"
    cache = home / "hf/hub"
    relative = Path("laya-lab/hf/hub/models--convaiinnovations--laya-multilingual/snapshots") / BASE_REVISION
    expected = Path.home() / relative
    if config.get("base_model_path") not in {"~/" + relative.as_posix(), str(expected)}:
        raise ValueError("Laya base path must use the pinned multilingual revision")
    if expected.resolve() != expected:
        raise ValueError("Laya base path must not redirect outside the pinned cache")
    home.mkdir(parents=True, exist_ok=True)
    missing = [filename for filename in BASE_FILES if not (expected / filename).is_file()]
    if missing:
        from huggingface_hub import snapshot_download
        downloaded = snapshot_download(repo_id=BASE_REPO, revision=BASE_REVISION,
                                       cache_dir=str(cache), allow_patterns=list(BASE_FILES))
        if Path(downloaded).resolve() != expected:
            raise ValueError("Downloaded Laya base path differs from the pinned cache")
        missing = [filename for filename in BASE_FILES if not (expected / filename).is_file()]
        if missing:
            raise FileNotFoundError(f"Incomplete Laya base snapshot: {', '.join(missing)}")
    if _digest(expected / "model.safetensors") != BASE_SHA256:
        raise ValueError("Laya base checkpoint digest mismatch")
    for filename, digests in SUPPORT_SHA256.items():
        if _digest(expected / filename) not in digests:
            raise ValueError(f"Laya base support file digest mismatch: {filename}")
    return expected


def main(argv: list[str] | None = None) -> None:
    """@param argv Optional CLI arguments; prints the verified snapshot path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/laya"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    print(prepare_base(args.dataset, args.version))


if __name__ == "__main__":
    main()
