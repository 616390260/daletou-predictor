"""Pinned base preparation tests without downloading model weights."""
import hashlib
import importlib
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REVISION = "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67"
FILES = ("model.safetensors", "rl_agent_config.json", "encoder/config.json",
         "tokenizer/tokenizer_config.json", "tokenizer/tokenizer.json")
RAW_TOKENIZER_CONFIG = b'''{
  "bos_token": "<bos>",
  "clean_up_tokenization_spaces": false,
  "cls_token": "<bos>",
  "eos_token": "<eos>",
  "extra_special_tokens": [
    "<start_of_turn>",
    "<end_of_turn>"
  ],
  "mask_token": "<mask>",
  "model_input_names": [
    "input_ids",
    "attention_mask"
  ],
  "model_max_length": 8192,
  "pad_token": "<pad>",
  "padding_side": "right",
  "sep_token": "<eos>",
  "spaces_between_special_tokens": false,
  "tokenizer_class": "PreTrainedTokenizerFast",
  "unk_token": "<unk>"
}'''


class LayaBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap = importlib.import_module("backend.src.laya.bootstrap")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = (Path(self.temp.name) / "home").resolve()
        self.dataset = Path(self.temp.name) / "dataset"
        self.version = "daletou-decision-v1"
        self.base = self.home / "laya-lab/hf/hub/models--convaiinnovations--laya-multilingual/snapshots" / REVISION
        self.digest = hashlib.sha256(b"base").hexdigest()
        self.config = {"version": self.version, "trained_through_issue": "26116", "source_sha256": "source",
                       "adapter_type": "head-only", "base_model_path": "~/" + str(self.base.relative_to(self.home)),
                       "base_checkpoint_sha256": self.digest}
        self.manifest = {**{k: self.config[k] for k in ("version", "trained_through_issue", "source_sha256")},
                         "base_checkpoint_sha256": self.digest,
                         "checkpoint_sha256": hashlib.sha256(b"head").hexdigest()}
        for subdirectory in ("adapters", "manifests"):
            (self.dataset / subdirectory).mkdir(parents=True)
        (self.dataset / "adapters" / f"{self.version}.safetensors").write_bytes(b"head")
        self.write_metadata()
        self.home_patch = patch("pathlib.Path.home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.digest_patch = patch.object(self.bootstrap, "BASE_SHA256", self.digest)
        self.digest_patch.start()
        self.addCleanup(self.digest_patch.stop)
        self.tokenizer_hashes = self.bootstrap.SUPPORT_SHA256["tokenizer/tokenizer_config.json"]
        self.support_patch = patch.object(self.bootstrap, "SUPPORT_SHA256", {
            filename: (hashlib.sha256(b"{}").hexdigest(),) for filename in FILES[1:]
        })
        self.support_patch.start()
        self.addCleanup(self.support_patch.stop)

    def write_metadata(self):
        (self.dataset / "manifests" / f"{self.version}.json").write_text(json.dumps(self.manifest))
        (self.dataset / "adapters" / f"{self.version}.json").write_text(json.dumps(self.config))

    def cached_base(self):
        for filename in FILES:
            target = self.base / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"base" if filename == "model.safetensors" else b"{}")

    def test_cached_base_is_verified_without_importing_download_client(self):
        self.cached_base()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            self.assertEqual(self.bootstrap.prepare_base(self.dataset, self.version), self.base)
        self.assertTrue((self.home / "laya-lab").is_dir())

    def test_missing_base_downloads_only_pinned_required_files(self):
        calls = []

        def download(**kwargs):
            calls.append(kwargs)
            self.cached_base()
            return str(self.base)

        client = types.SimpleNamespace(snapshot_download=download)
        with patch.dict("sys.modules", {"huggingface_hub": client}):
            self.assertEqual(self.bootstrap.prepare_base(self.dataset, self.version), self.base)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["repo_id"], "convaiinnovations/laya-multilingual")
        self.assertEqual(calls[0]["revision"], REVISION)
        self.assertEqual(set(calls[0]["allow_patterns"]), set(FILES))
        self.assertEqual(Path(calls[0]["cache_dir"]), self.home / "laya-lab/hf/hub")

    def test_incomplete_download_is_rejected(self):
        self.cached_base()
        (self.base / "tokenizer/tokenizer.json").unlink()
        client = types.SimpleNamespace(snapshot_download=lambda **kwargs: str(self.base))
        with patch.dict("sys.modules", {"huggingface_hub": client}):
            with self.assertRaisesRegex(FileNotFoundError, "tokenizer.json"):
                self.bootstrap.prepare_base(self.dataset, self.version)

    def test_corrupt_cached_checkpoint_fails_without_downloading(self):
        self.cached_base()
        (self.base / "model.safetensors").write_bytes(b"corrupt")
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with self.assertRaisesRegex(ValueError, "digest"):
                self.bootstrap.prepare_base(self.dataset, self.version)

    def test_corrupt_cached_support_files_fail_without_downloading(self):
        for filename in FILES[1:]:
            with self.subTest(filename=filename):
                self.cached_base()
                (self.base / filename).write_bytes(b'{"corrupt":true}')
                with patch.dict("sys.modules", {"huggingface_hub": None}):
                    with self.assertRaisesRegex(ValueError, "digest.*" + filename):
                        self.bootstrap.prepare_base(self.dataset, self.version)

    def test_corrupt_downloaded_support_file_is_rejected(self):
        def download(**kwargs):
            self.cached_base()
            (self.base / "tokenizer/tokenizer.json").write_bytes(b'{"corrupt":true}')
            return str(self.base)

        client = types.SimpleNamespace(snapshot_download=download)
        with patch.dict("sys.modules", {"huggingface_hub": client}):
            with self.assertRaisesRegex(ValueError, "digest.*tokenizer/tokenizer.json"):
                self.bootstrap.prepare_base(self.dataset, self.version)

    def test_cold_download_accepts_original_pinned_tokenizer_config(self):
        self.bootstrap.SUPPORT_SHA256["tokenizer/tokenizer_config.json"] = self.tokenizer_hashes
        self.assertEqual(hashlib.sha256(RAW_TOKENIZER_CONFIG).hexdigest(),
                         "424b69444bf7b5809dc2cd2e36d0bd71b8055124dd24274d6db3c655d38205e7")

        def download(**kwargs):
            self.cached_base()
            (self.base / "tokenizer/tokenizer_config.json").write_bytes(RAW_TOKENIZER_CONFIG)
            return str(self.base)

        client = types.SimpleNamespace(snapshot_download=download)
        with patch.dict("sys.modules", {"huggingface_hub": client}):
            self.assertEqual(self.bootstrap.prepare_base(self.dataset, self.version), self.base)

    def test_repeated_cached_load_accepts_laya_normalized_tokenizer_config(self):
        self.cached_base()
        self.bootstrap.SUPPORT_SHA256["tokenizer/tokenizer_config.json"] = self.tokenizer_hashes
        config = json.loads(RAW_TOKENIZER_CONFIG)
        config["extra_special_tokens"] = {f"extra_{i}": token
                                          for i, token in enumerate(config["extra_special_tokens"])}
        normalized = json.dumps(config, indent=2).encode()
        self.assertEqual(hashlib.sha256(normalized).hexdigest(),
                         "6c6b2d8e3c84ce0e671c129cd6b374b235d6f9863042a5836358d00a89bbb5a1")
        (self.base / "tokenizer/tokenizer_config.json").write_bytes(normalized)
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            for _ in range(2):
                self.assertEqual(self.bootstrap.prepare_base(self.dataset, self.version), self.base)

    def test_external_path_and_unpinned_revision_are_rejected(self):
        for path in ("/tmp/other-repo", self.config["base_model_path"].replace(REVISION, "main"),
                     self.config["base_model_path"].replace(REVISION, "../" + REVISION)):
            with self.subTest(path=path):
                self.config["base_model_path"] = path
                self.write_metadata()
                with self.assertRaisesRegex(ValueError, "base.*path|revision"):
                    self.bootstrap.prepare_base(self.dataset, self.version)

    def test_changed_digest_metadata_is_rejected(self):
        self.manifest["base_checkpoint_sha256"] = "wrong"
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "digest"):
            self.bootstrap.prepare_base(self.dataset, self.version)

    def test_changed_head_is_rejected_before_network(self):
        (self.dataset / "adapters" / f"{self.version}.safetensors").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.bootstrap.prepare_base(self.dataset, self.version)

    def test_invalid_version_and_metadata_disagreement_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "version"):
            self.bootstrap.prepare_base(self.dataset, "../daletou-decision-v1")
        self.config["version"] = "daletou-other"
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.bootstrap.prepare_base(self.dataset, self.version)

    def test_cli_passes_dataset_and_version_to_preparation(self):
        import contextlib
        import io
        output = io.StringIO()
        with patch.object(self.bootstrap, "prepare_base", return_value=self.base) as prepare, \
                contextlib.redirect_stdout(output):
            self.bootstrap.main(["--dataset", str(self.dataset), "--version", self.version])
        prepare.assert_called_once_with(self.dataset, self.version)
        self.assertEqual(output.getvalue().strip(), str(self.base))


if __name__ == "__main__":
    unittest.main()
