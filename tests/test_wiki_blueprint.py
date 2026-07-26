from __future__ import annotations

import unittest

from _local_package import load_local_package

load_local_package()
from omh.knowledge_connections import KnowledgeConnectionOptions
from omh.wiki_blueprint import (
    SEED_PAGE_CAP,
    UNKNOWN_AUDIENCE,
    WIKI_BLUEPRINT_SCHEMA_VERSION,
    WikiBlueprintRequest,
    build_wiki_blueprint,
    ecosystem_candidates,
    normalize_audience,
    select_models,
    wiki_ecosystem_coverage,
)
from omh.wiki_patterns import wiki_operation_rules, wiki_patterns


def _blueprint(**kwargs: object) -> dict[str, object]:
    return build_wiki_blueprint(WikiBlueprintRequest(**kwargs))  # type: ignore[arg-type]


class AudienceTests(unittest.TestCase):
    def test_known_aliases_normalize(self) -> None:
        self.assertEqual(normalize_audience("Team"), "team")
        self.assertEqual(normalize_audience("개인"), "personal")
        self.assertEqual(normalize_audience("small group"), "small_group")
        self.assertEqual(normalize_audience("company"), "organization")

    def test_absent_or_unrecognized_audience_stays_unknown(self) -> None:
        self.assertEqual(normalize_audience(""), UNKNOWN_AUDIENCE)
        self.assertEqual(normalize_audience("   "), UNKNOWN_AUDIENCE)
        self.assertEqual(normalize_audience("a handful of robots"), UNKNOWN_AUDIENCE)


class ModelSelectionTests(unittest.TestCase):
    def test_knowledge_type_outranks_audience_default(self) -> None:
        primary, _ = select_models(
            audience="team",
            knowledge_types=("decisions we keep relitigating",),
            destination_kind="notion_knowledge_base",
        )
        self.assertEqual(primary.name, "Decision log (ADR)")

    def test_audience_default_applies_without_knowledge_types(self) -> None:
        personal, _ = select_models(audience="personal", knowledge_types=(), destination_kind="markdown_vault")
        team, _ = select_models(audience="team", knowledge_types=(), destination_kind="notion_knowledge_base")
        self.assertEqual(personal.name, "PARA")
        self.assertEqual(team.name, "Diátaxis")

    def test_repo_destination_pulls_in_docs_as_code(self) -> None:
        _, alternative = select_models(
            audience="team",
            knowledge_types=("onboarding",),
            destination_kind="local_markdown_folder",
        )
        self.assertEqual(alternative.name, "Docs-as-code")

    def test_alternative_is_always_distinct(self) -> None:
        for audience in ("personal", "small_group", "team", "organization", UNKNOWN_AUDIENCE):
            for knowledge_types in ((), ("decision",), ("research", "glossary")):
                primary, alternative = select_models(
                    audience=audience,
                    knowledge_types=knowledge_types,
                    destination_kind="markdown_vault",
                )
                self.assertNotEqual(primary.name, alternative.name, (audience, knowledge_types))

    def test_every_mapped_model_name_exists_in_the_pattern_table(self) -> None:
        names = {pattern.name for pattern in wiki_patterns()}
        for knowledge_types in (("decision",), ("onboarding",), ("code",), ("research",), ("glossary",), ("project",)):
            primary, alternative = select_models(
                audience=UNKNOWN_AUDIENCE,
                knowledge_types=knowledge_types,
                destination_kind="notion_knowledge_base",
            )
            self.assertIn(primary.name, names)
            self.assertIn(alternative.name, names)


class BlueprintTests(unittest.TestCase):
    def test_shared_and_personal_get_different_operating_rules(self) -> None:
        team = _blueprint(text="set up a wiki in Notion", audience_scale="team", maintenance_owner="platform")
        solo = _blueprint(text="organize my Obsidian vault", audience_scale="personal", maintenance_owner="me")

        self.assertTrue(team["shared_audience"])
        self.assertFalse(solo["shared_audience"])
        ownership = {rule.topic: rule for rule in wiki_operation_rules()}["Ownership"]
        team_rules = {row["topic"]: row["rule"] for row in team["maintenance"]["rules"]}
        solo_rules = {row["topic"]: row["rule"] for row in solo["maintenance"]["rules"]}
        self.assertEqual(team_rules["Ownership"], ownership.shared)
        self.assertEqual(solo_rules["Ownership"], ownership.personal)

    def test_destination_classification_is_reused_not_reinvented(self) -> None:
        notion = _blueprint(text="save our onboarding docs into a Notion knowledge base")
        obsidian = _blueprint(
            text="structure my notes",
            connection=KnowledgeConnectionOptions(knowledge_store="my Obsidian vault"),
        )
        self.assertEqual(notion["destination"]["kind"], "notion_knowledge_base")
        self.assertEqual(obsidian["destination"]["vendor_hint"], "obsidian")
        self.assertFalse(notion["destination"]["write_observed"])

    def test_missing_facts_name_what_the_interview_still_needs(self) -> None:
        bare = _blueprint(text="help me build a wiki")
        self.assertIn("audience scale (personal, small group, team, or organization)", bare["missing_facts"])
        self.assertIn("maintenance owner and review cadence", bare["missing_facts"])
        self.assertIn("knowledge types the wiki must hold", bare["missing_facts"])

    def test_unowned_wiki_is_recorded_rather_than_assumed(self) -> None:
        blueprint = _blueprint(text="a wiki for myself", audience_scale="personal")
        self.assertEqual(blueprint["maintenance"]["owner"], "unmaintained")
        self.assertFalse(blueprint["maintenance"]["owner_known"])

    def test_answered_interview_leaves_no_open_questions(self) -> None:
        blueprint = _blueprint(
            text="stand up a team wiki",
            audience_scale="team",
            maintenance_owner="platform team",
            knowledge_types=("decisions", "onboarding"),
            connection=KnowledgeConnectionOptions(knowledge_store="Notion workspace"),
        )
        self.assertEqual(blueprint["missing_facts"], [])

    def test_blueprint_never_claims_the_store_exists(self) -> None:
        blueprint = _blueprint(text="build a wiki in Notion", audience_scale="team")
        self.assertEqual(blueprint["schema_version"], WIKI_BLUEPRINT_SCHEMA_VERSION)
        self.assertEqual(blueprint["status"], "prepared")
        self.assertIn("not evidence that a store was created", blueprint["claim_boundary"])
        self.assertFalse(blueprint["destination"]["query_observed"])

    def test_seed_page_cap_keeps_the_blueprint_startable(self) -> None:
        self.assertEqual(_blueprint(text="wiki")["seed_page_cap"], SEED_PAGE_CAP)
        self.assertLessEqual(SEED_PAGE_CAP, 10)

    def test_model_payload_carries_breaking_conditions_and_an_alternative(self) -> None:
        blueprint = _blueprint(text="team wiki", audience_scale="team", knowledge_types=("decisions",))
        model = blueprint["organization_model"]
        self.assertTrue(model["breaks_when"])
        self.assertTrue(model["fits_when"])
        self.assertNotEqual(blueprint["alternative_model"]["name"], model["name"])


class EcosystemTests(unittest.TestCase):
    def test_candidates_are_knowledge_material_not_storage_backends(self) -> None:
        ids = {coverage.item.id for coverage in wiki_ecosystem_coverage()}
        self.assertIn("hermeswiki", ids)
        # A secrets vault matches "vault" but is not wiki-construction material.
        self.assertNotIn("1claw-hermes", ids)

    def test_candidate_rows_stay_metadata_only(self) -> None:
        for candidate in ecosystem_candidates():
            self.assertEqual(sorted(candidate), ["coverage_status", "id", "name", "url"])

    def test_candidate_order_is_stable(self) -> None:
        ids = [candidate["id"] for candidate in ecosystem_candidates()]
        self.assertEqual(ids, sorted(ids))


if __name__ == "__main__":
    unittest.main()
