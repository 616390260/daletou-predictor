"""Guard branch-state writers against concurrent or stale-checkout pushes."""

import re
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WRITERS = ("predict", "evaluate", "backtest", "reflect", "laya")
BRANCH = "${{ github.event.workflow_run.head_branch || github.ref_name }}"


class WorkflowWriterTests(unittest.TestCase):
    def test_all_writers_share_a_branch_queue_without_canceling_pending_runs(self):
        for name in WRITERS:
            with self.subTest(workflow=name):
                source = (WORKFLOWS / f"{name}.yml").read_text()
                block = re.search(r"(?m)^concurrency:\n((?:[ \t].*\n|\n)+)", source)
                self.assertIsNotNone(block, f"{name} must serialize branch-state writes")
                settings = dict(re.findall(r"^  ([\w-]+): (.+)$", block[1], re.MULTILINE))
                self.assertEqual(settings.get("group"), f"daletou-state-{BRANCH}")
                self.assertEqual(settings.get("cancel-in-progress"), "false")
                self.assertEqual(settings.get("queue"), "max")

    def test_checkout_reads_the_branch_head_after_waiting_for_the_queue(self):
        for name in WRITERS:
            with self.subTest(workflow=name):
                source = (WORKFLOWS / f"{name}.yml").read_text()
                checkout = re.search(
                    r"(?m)^      - uses: actions/checkout@v4\n((?:        .*\n|\n)*)",
                    source,
                )
                self.assertIsNotNone(checkout)
                expected_ref = BRANCH if name == "reflect" else "${{ github.ref_name }}"
                self.assertRegex(checkout[1], rf"(?m)^          ref: {re.escape(expected_ref)}$")

    def test_predict_and_evaluate_dispatch_laya_after_persisting_original_data(self):
        for name in ('predict', 'evaluate'):
            with self.subTest(workflow=name):
                source = (WORKFLOWS / f'{name}.yml').read_text()
                self.assertRegex(source, r'(?m)^  actions: write')
                dispatch = source.index('gh workflow run laya.yml --ref "$REF_NAME"')
                self.assertGreater(dispatch, source.index('- name: Commit JSON'))
                self.assertIn('REF_NAME: ${{ github.ref_name }}', source)
                self.assertNotIn('|| echo', source[dispatch:])

    def test_laya_settles_before_loading_model_and_always_preserves_progress(self):
        source = (WORKFLOWS / 'laya.yml').read_text()
        self.assertIn('LAYA_DEVICE: cpu', source)
        settle = source.index('python -m backend.src.tasks.laya_sync --settle-only')
        check = source.index('python -m backend.src.tasks.laya_sync --check')
        install = source.index('pip install -r backend/requirements-laya.txt')
        self.assertLess(settle, check)
        self.assertLess(check, install)
        for step in ('Install CPU runtime', 'Cache multilingual base', 'Prepare pinned multilingual base', 'Select next issue'):
            block = source.split(f'- name: {step}\n', 1)[1].split('\n      - ', 1)[0]
            self.assertIn("if: steps.plan.outputs.needs_decision == 'true'", block)
        for step in ('Append RUN_LOG.jsonl', 'Commit Laya decisions and run log'):
            block = source.split(f'- name: {step}\n', 1)[1].split('\n      - ', 1)[0]
            self.assertIn('if: always()', block)
        deploy = (WORKFLOWS / 'deploy-frontend.yml').read_text()
        self.assertIn('Laya Independent Decision', deploy)

    def test_laya_failure_can_publish_already_settled_atomic_report(self):
        deploy = (WORKFLOWS / 'deploy-frontend.yml').read_text()
        self.assertIn("github.event.workflow_run.name == 'Laya Independent Decision'", deploy)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", deploy)


if __name__ == "__main__":
    unittest.main()
