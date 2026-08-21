import unittest
from types import SimpleNamespace

from services.planning_service import PlanningService
from state.orchestration_state import OrchestrationState


class PlanningServiceTests(unittest.TestCase):
    def setUp(self):
        self.agents = [
            SimpleNamespace(name="DocIntel"),
            SimpleNamespace(name="RiskAnalyzer"),
        ]

    def test_validates_sequential_nodes_and_declared_file_use(self):
        plan = PlanningService()._validate(
            {
                "requires_plan": True,
                "summary": "Extract then assess risk.",
                "nodes": [
                    {
                        "node_id": "extract",
                        "agent_name": "DocIntel",
                        "query": "Extract invoice records.",
                        "depends_on": [],
                        "use_uploaded_files": True,
                    },
                    {
                        "node_id": "risk",
                        "agent_name": "RiskAnalyzer",
                        "query": "Assess the extracted records.",
                        "depends_on": ["extract"],
                        "use_uploaded_files": False,
                    },
                ],
            },
            self.agents,
            ["https://files.example/invoice.pdf"],
            "Review invoices",
        )

        self.assertEqual(plan["status"], "awaiting_approval")
        self.assertEqual(plan["nodes"][1]["depends_on"], ["extract"])
        self.assertFalse(plan["nodes"][1]["use_uploaded_files"])

    def test_rejects_forward_dependency(self):
        plan = PlanningService()._validate(
            {
                "requires_plan": True,
                "nodes": [
                    {
                        "agent_name": "DocIntel",
                        "query": "Extract.",
                        "depends_on": ["future"],
                    }
                ],
            },
            self.agents,
            [],
            "Review",
        )
        self.assertIsNone(plan)


class OrchestrationStateTests(unittest.TestCase):
    def test_plan_survives_state_round_trip(self):
        state = OrchestrationState({"plan": {"plan_id": "p1", "status": "awaiting_approval"}})
        self.assertEqual(state.to_dict()["plan"]["plan_id"], "p1")
