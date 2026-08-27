from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class SimpleSwarmContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = read("skill/SKILL.md")
        self.simple = read("skill/references/simple-swarm.md")
        self.routing = read("skill/references/routing.md")
        self.package = read("skill/references/work-package.md")
        self.integration = read("integration/AGENTS.dynamic-workflow.md")
        self.readme = read("README.md")

    def test_simple_swarm_is_default_lightweight_mode(self) -> None:
        for content in (self.skill, self.simple, self.readme):
            self.assertIn("Simple Swarm", content)
        self.assertIn("Workflow: simple-swarm", self.skill)
        self.assertIn("not a Workflow IR preset", self.simple)
        self.assertIn("no Workflow IR", self.simple)

    def test_advanced_modes_require_explicit_triggers(self) -> None:
        self.assertIn("Managed Workflow", self.skill)
        self.assertIn("Worktree Writer", self.skill)
        self.assertIn("references/worktree-writer-v1.md", self.skill)
        self.assertIn("explicitly needs checkpoint/resume", self.skill)
        self.assertIn("explicitly requests an isolated write candidate", self.skill)
        self.assertIn("Worktree Writer 仅在明确要求隔离候选时启用", self.integration)

    def test_branch_scope_overlap_and_root_non_duplication_are_locked(self) -> None:
        self.assertIn("one primary question", self.simple)
        self.assertIn("usually no more than three primary files", self.simple)
        self.assertIn("roughly twenty percent", self.simple)
        self.assertIn("must not redo the branch's full investigation", self.simple)
        self.assertIn("模型路线不能弥补错误拆分", self.integration)

    def test_wait_policy_is_bounded(self) -> None:
        self.assertIn("Wait once for normal completion", self.simple)
        self.assertIn("one concise progress or partial result", self.simple)
        self.assertIn("Repeated waits", self.simple)
        self.assertIn("Wait once for normal completion", self.skill)

    def test_compact_read_only_packet_avoids_managed_overhead(self) -> None:
        self.assertIn("## Compact Simple Swarm packet", self.package)
        for field in ("QUESTION", "SCOPE", "DELIVERY", "VERIFY"):
            self.assertIn(field, self.package)
        self.assertIn("Do not attach a Writer authority manifest", self.package)
        self.assertIn("## Full package", self.package)

    def test_routing_cannot_rescue_bad_decomposition(self) -> None:
        self.assertIn("Route selection cannot rescue a badly scoped branch", self.routing)
        self.assertIn("Sol is not a substitute for decomposition", self.routing)
        self.assertIn("Adopted output is the success metric", self.routing)


if __name__ == "__main__":
    unittest.main()
