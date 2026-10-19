"""Guard branch-state writers against concurrent or stale-checkout pushes."""

import re
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WRITERS = ("predict", "evaluate", "backtest", "reflect")
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


if __name__ == "__main__":
    unittest.main()
