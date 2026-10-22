"""Address maintenance must fail before downtime on ambiguity or drift."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import manage_addresses as maintenance


def fixture():
    network_id = "a" * 64
    nodes = []
    members = {}
    for index, role in enumerate(("postgres", "opensearch", "api", "web"), 2):
        ident = str(index) * 64
        address = f"198.19.255.{240 + index}"
        endpoint = {
            "NetworkID": network_id,
            "IPAddress": address,
            "GlobalIPv6Address": "",
            "IPAMConfig": {"IPv4Address": address}
            if role in {"postgres", "api", "web"}
            else None,
            "Aliases": [role],
            "GwPriority": 0,
            "Links": None,
            "DriverOpts": None,
            "MacAddress": "",
        }
        nodes.append(
            {
                "id": ident,
                "role": role,
                "project": "fixture",
                "running": True,
                "posture": "b" * 64,
                "networks": {"fixture-isolated": endpoint},
            }
        )
        members[ident] = {}
    networks = [
        {
            "id": network_id,
            "name": "fixture-isolated",
            "key": "isolated",
            "driver": "bridge",
            "project": "fixture",
            "internal": True,
            "ipam": [{"Subnet": "198.19.255.240/28", "Gateway": "198.19.255.241"}],
            "members": members,
        }
    ]
    return nodes, networks


class AddressMaintenanceTests(unittest.TestCase):
    def test_existing_mixed_cycle_becomes_fully_pinned_dependency_order(self):
        nodes, networks = fixture()
        plan = maintenance.make_plan("fixture", nodes, networks)
        maintenance.validate(plan)
        self.assertEqual(
            plan["groups"],
            [[nodes[0]["id"], nodes[1]["id"]], [nodes[2]["id"]], [nodes[3]["id"]]],
        )
        self.assertEqual(
            [e["address"] for e in plan["endpoints"]],
            [n["networks"]["fixture-isolated"]["IPAddress"] for n in nodes],
        )
        self.assertEqual(sum(not e["was_static"] for e in plan["endpoints"]), 1)
        self.assertEqual(nodes, fixture()[0])  # Planning does not mutate the snapshot.

    def test_rejects_unsupported_or_unowned_metadata_before_any_command(self):
        for kind in (
            "unknown_role",
            "duplicate_role",
            "stopped",
            "foreign_project",
            "duplicate_ip",
            "ipv6",
            "links",
            "driver_options",
            "priority",
            "alias",
            "foreign_network",
            "foreign_member",
            "host_network",
            "mismatched_ip",
            "unknown_ipam",
            "gateway",
            "outside_subnet",
            "extra_network",
        ):
            with self.subTest(kind=kind):
                nodes, networks = fixture()
                e = nodes[1]["networks"]["fixture-isolated"]
                if kind == "unknown_role":
                    nodes[1]["role"] = "unknown"
                elif kind == "duplicate_role":
                    nodes[1]["role"] = "postgres"
                elif kind == "stopped":
                    nodes[1]["running"] = False
                elif kind == "foreign_project":
                    nodes[1]["project"] = "another"
                elif kind == "duplicate_ip":
                    e["IPAddress"] = nodes[0]["networks"]["fixture-isolated"][
                        "IPAddress"
                    ]
                elif kind == "ipv6":
                    e["GlobalIPv6Address"] = "2001:db8::1"
                elif kind == "links":
                    e["Links"] = ["legacy"]
                elif kind == "driver_options":
                    e["DriverOpts"] = {"custom": "yes"}
                elif kind == "priority":
                    e["GwPriority"] = 1
                elif kind == "alias":
                    e["Aliases"] = ["--invalid"]
                elif kind == "foreign_network":
                    networks[0]["project"] = "another"
                elif kind == "foreign_member":
                    networks[0]["members"]["c" * 64] = {}
                elif kind == "host_network":
                    networks[0]["driver"] = "host"
                elif kind == "mismatched_ip":
                    e["IPAMConfig"] = {"IPv4Address": "198.19.255.250"}
                elif kind == "unknown_ipam":
                    e["IPAMConfig"] = {"unknown": "value"}
                elif kind == "gateway":
                    e["IPAddress"] = "198.19.255.241"
                elif kind == "outside_subnet":
                    e["IPAddress"] = "198.19.254.10"
                elif kind == "extra_network":
                    networks.append({**networks[0], "id": "f" * 64})
                with (
                    patch.object(maintenance, "run") as command,
                    self.assertRaises((ValueError, KeyError)),
                ):
                    maintenance.make_plan("fixture", nodes, networks)
                command.assert_not_called()

    def test_plan_rejects_a_rewritten_execution_schedule(self):
        nodes, networks = fixture()
        plan = maintenance.make_plan("fixture", nodes, networks)
        plan["groups"].reverse()
        with self.assertRaises(ValueError):
            maintenance.validate(plan)

    def test_duplicate_aliases_keep_the_same_dns_set_without_duplicate_lock_entries(self):
        nodes, networks = fixture()
        nodes[1]["networks"]["fixture-isolated"]["Aliases"] = ["opensearch", "opensearch"]
        plan = maintenance.make_plan("fixture", nodes, networks)
        self.assertEqual(plan["endpoints"][1]["aliases"], ["opensearch"])
        maintenance.verify_resume_endpoints(plan, nodes)

    def test_resume_accepts_partial_pinning_but_rejects_unknown_network_or_identity(self):
        nodes, networks = fixture()
        plan = maintenance.make_plan("fixture", nodes, networks)
        partial = copy.deepcopy(nodes)
        partial[1]["networks"] = {}  # Disconnect succeeded before an interruption.
        partial[2]["networks"]["fixture-isolated"]["IPAddress"] = ""
        partial[2]["running"] = False
        maintenance.verify_resume_endpoints(plan, partial)
        for kind in ("network", "address", "alias", "request", "priority"):
            with self.subTest(kind=kind):
                changed = copy.deepcopy(nodes)
                endpoint = changed[1]["networks"]["fixture-isolated"]
                if kind == "network":
                    endpoint["NetworkID"] = "f" * 64
                elif kind == "address":
                    endpoint["IPAddress"] = "198.19.255.250"
                elif kind == "alias":
                    endpoint["Aliases"] = ["unreviewed"]
                elif kind == "request":
                    endpoint["IPAMConfig"] = {"IPv4Address": "198.19.255.250"}
                else:
                    endpoint["GwPriority"] = 1
                with self.assertRaises(ValueError):
                    maintenance.verify_resume_endpoints(plan, changed)

    def test_apply_rejects_snapshot_or_network_drift_before_stop_or_checkpoint(self):
        for kind in ("posture", "membership", "address"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                nodes, networks = fixture()
                plan = maintenance.make_plan("fixture", nodes, networks)
                changed_nodes, changed_networks = (
                    copy.deepcopy(nodes),
                    copy.deepcopy(networks),
                )
                if kind == "posture":
                    changed_nodes[0]["posture"] = "c" * 64
                elif kind == "address":
                    changed_nodes[0]["networks"]["fixture-isolated"]["IPAddress"] = (
                        "198.19.255.250"
                    )
                else:
                    changed_networks[0]["members"]["d" * 64] = {}
                journal = Path(temp) / "journal.json"
                with (
                    patch.object(maintenance, "capture", return_value=changed_nodes),
                    patch.object(
                        maintenance, "networks_for", return_value=changed_networks
                    ),
                    patch.object(maintenance, "run") as command,
                    self.assertRaises(ValueError),
                ):
                    maintenance.apply(plan, journal)
                command.assert_not_called()
                self.assertFalse(journal.exists())

    def test_hash_and_downtime_are_required_before_capture_or_mutation(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as temp:
            nodes, networks = fixture()
            plan = maintenance.make_plan("fixture", nodes, networks)
            path = Path(temp) / "plan.json"
            maintenance.private_write(path, plan)
            for flags in (
                [],
                ["--stop-services"],
                ["--stop-services", "--expected-sha256", "wrong"],
            ):
                with (
                    patch(
                        "sys.argv",
                        [
                            "manage_addresses.py",
                            "apply",
                            "--project-name",
                            "fixture",
                            "--plan",
                            str(path),
                            *flags,
                        ],
                    ),
                    patch.object(maintenance, "capture") as capture,
                    patch.object(maintenance, "run") as command,
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(maintenance.main(), 1)
                    capture.assert_not_called()
                    command.assert_not_called()

    def test_private_checkpoint_refuses_overwrite_and_serialization_has_no_service_env(
        self,
    ):
        nodes, networks = fixture()
        plan = maintenance.make_plan("fixture", nodes, networks)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.json"
            maintenance.private_write(path, plan)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                maintenance.private_write(path, {})
            self.assertEqual(json.loads(path.read_text()), plan)
        lock = maintenance.compose_lock(plan)
        self.assertEqual(set(lock), {"services", "networks"})
        for service in lock["services"].values():
            self.assertEqual(set(service), {"networks"})
        self.assertNotIn("environment", json.dumps(lock))
        self.assertNotIn("volumes", json.dumps(lock))
        self.assertNotIn("ports", json.dumps(lock))

    def test_resume_rejects_wrong_or_complete_journal_before_any_mutation(self):
        nodes, networks = fixture()
        plan = maintenance.make_plan("fixture", nodes, networks)
        for journal in (
            {"plan_sha256": "wrong", "phase": "pinning"},
            {"plan_sha256": maintenance.digest(plan), "phase": "complete"},
        ):
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "journal.json"
                maintenance.private_write(path, journal)
                with (
                    patch.object(maintenance, "capture", return_value=nodes),
                    patch.object(maintenance, "run") as command,
                    self.assertRaises(ValueError),
                ):
                    maintenance.apply(plan, path, resume=True)
                command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
