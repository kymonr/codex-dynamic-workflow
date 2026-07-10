import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def read_skill(relative_path):
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body


class SkillRuntimeCompatTests(unittest.TestCase):
    def test_installed_mirrors_match_canonical_source_bytes(self):
        installed = Path.home() / ".codex/skills"
        pairs = [
            (ROOT / "skills/codex-team-router/SKILL.md", installed / "codex-team-router/SKILL.md"),
            (ROOT / "dynamic-workflow/skill/SKILL.md", installed / "dynamic-workflow/SKILL.md"),
            (ROOT / "dynamic-workflow/src/runner.py", installed / "dynamic-workflow/runner.py"),
        ]
        for source, mirror in pairs:
            with self.subTest(mirror=mirror):
                self.assertEqual(source.read_bytes(), mirror.read_bytes())

    def test_team_router_frontmatter_matches_current_skill_schema(self):
        metadata, _ = read_skill("skills/codex-team-router/SKILL.md")
        self.assertEqual(set(metadata), {"name", "description"})
        self.assertTrue(metadata["description"].startswith("Use when"))

    def test_dynamic_workflow_uses_current_collaboration_tool_names(self):
        metadata, body = read_skill("dynamic-workflow/skill/SKILL.md")
        self.assertEqual(set(metadata), {"name", "description"})
        self.assertTrue(metadata["description"].startswith("Use when"))
        self.assertNotIn("multi_agent_v1", body)
        self.assertIn("`spawn_agent`", body)
        self.assertIn("`wait_agent`", body)

    def test_active_skill_docs_do_not_name_retired_multi_agent_surface(self):
        paths = [
            ROOT / "dynamic-workflow/README.md",
            ROOT / "dynamic-workflow/skill/SKILL.md",
            ROOT / "skills/codex-team-router/SKILL.md",
            *(ROOT / "skills/codex-team-router/references").glob("*.md"),
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("multi_agent_v1", text)

    def test_deep_routes_keep_lifecycle_gates_independent(self):
        router = (ROOT / "skills/codex-team-router/SKILL.md").read_text(encoding="utf-8").lower()
        dynamic = (ROOT / "dynamic-workflow/skill/SKILL.md").read_text(encoding="utf-8").lower()
        for text in (router, dynamic):
            self.assertIn("## lifecycle gates", text)
            for term in ("review-only", "design acceptance", "implementation", "verification", "closeout", "commit", "create task"):
                self.assertIn(term, text)

        manager = (ROOT / "skills/codex-team-router/references/manager-mode.md").read_text(encoding="utf-8").lower()
        taxonomy = (ROOT / "skills/codex-team-router/references/side-effect-taxonomy.md").read_text(encoding="utf-8").lower()
        closeout = (ROOT / "skills/codex-team-router/references/role-closeout.md").read_text(encoding="utf-8").lower()
        self.assertIn("title changes require explicit current-turn authorization", router)
        self.assertNotIn("may authorize the manager to delegate", manager)
        self.assertIn("title changes require explicit current-turn authorization", manager)
        self.assertNotIn("authorize routing only", taxonomy)
        self.assertIn("only through a separately authorized workspace-write gate", closeout)
        self.assertIn("do not automatically dispatch lesson writes", manager)


if __name__ == "__main__":
    unittest.main()
