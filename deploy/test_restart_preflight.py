"""Independent unsafe topologies and no-downtime admission checks."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import manage_backup as backup
from restart_preflight import MAX_CONTAINERS, MAX_METADATA_BYTES, plan_restarts
from restart_test_fixtures import endpoint, metadata, record


def plan(*records):
    return plan_restarts([r["id"] for r in records], metadata(records))


class RestartTopologyTests(unittest.TestCase):
    def test_database_reservation_precedes_dynamic_base_even_in_reversed_discovery(self):
        dynamic = record("search", "opensearch", {"mesh": endpoint(address="172.28.0.3")})
        fixed = record("database", "postgres", {"mesh": endpoint(static=True)})
        api = record("application", "api")
        self.assertEqual(plan(dynamic, api, fixed), [["database"], ["search"], ["application"]])

    def test_static_web_and_dynamic_fuseki_is_blocked_instead_of_guessing_a_recovery(self):
        graph = record("graph", "fuseki", {"mesh": endpoint(address="172.28.0.3")})
        api = record("application", "api")
        web = record("edge", "web", {"mesh": endpoint(static=True)})
        with self.assertRaisesRegex(ValueError, "^Unsafe restart plan:"):
            plan(graph, api, web)

    def test_static_api_and_dynamic_dependency_is_blocked(self):
        graph = record("graph", "fuseki", {"mesh": endpoint(address="172.28.0.3")})
        api = record("application", "api", {"mesh": endpoint(static=True)})
        with self.assertRaisesRegex(ValueError, "^Unsafe restart plan:"):
            plan(api, graph)

    def test_all_explicit_addresses_preserve_backing_api_web_dependencies(self):
        roles = [("edge", "web"), ("application", "api"), ("graph", "fuseki"),
                 ("database", "postgres"), ("relay", "provider-relay")]
        records = [record(ident, role, {"mesh": endpoint(address=f"172.28.0.{i}", static=True)})
                   for i, (ident, role) in enumerate(roles, 2)]
        self.assertEqual(plan(*records), [["relay"], ["graph", "database"], ["application"], ["edge"]])

    def test_secondary_network_reservations_are_checked(self):
        db = record("database", "postgres", {"first": endpoint("first", "172.28.0.2", True),
                                              "second": endpoint("second", "172.29.0.2", True)})
        graph = record("graph", "fuseki", {"first": endpoint("first", "172.28.0.3", True),
                                            "second": endpoint("second", "172.29.0.3")})
        self.assertEqual(plan(graph, db), [["database"], ["graph"]])

    def test_network_identity_not_display_name_defines_a_shared_allocator(self):
        fixed = record("database", "postgres", {"display-a": endpoint("same-id", static=True)})
        dynamic = record("search", "opensearch", {"display-b": endpoint("same-id", "172.28.0.3")})
        self.assertEqual(plan(dynamic, fixed), [["database"], ["search"]])

    def test_equal_addresses_on_different_networks_are_not_collapsed(self):
        a = record("database", "postgres", {"first": endpoint("first", static=True)})
        b = record("graph", "fuseki", {"second": endpoint("second", static=True)})
        self.assertEqual(plan(a, b), [["database", "graph"]])

    def test_unshared_network_has_no_extra_allocation_dependency(self):
        a = record("database", "postgres", {"first": endpoint("first", static=True)})
        b = record("graph", "fuseki", {"second": endpoint("second")})
        self.assertEqual(plan(b, a), [["graph", "database"]])

    def test_ipv6_reservation_and_canonical_address_equivalence(self):
        fixed = endpoint(address="", ipv6="fd00:0:0::2", static6=True)
        fixed["IPAMConfig"]["IPv6Address"] = "fd00::2"
        a = record("database", "postgres", {"mesh": fixed})
        b = record("graph", "fuseki", {"mesh": endpoint(address="", ipv6="fd00::3")})
        self.assertEqual(plan(b, a), [["database"], ["graph"]])

    def test_mixed_dual_stack_reservations_can_form_an_unsafe_cycle(self):
        a = record("database", "postgres", {"mesh": endpoint(static=True, ipv6="fd00::2")})
        b = record("graph", "fuseki", {"mesh": endpoint(address="172.28.0.3", ipv6="fd00::3", static6=True)})
        with self.assertRaisesRegex(ValueError, "^Unsafe restart plan:"):
            plan(a, b)

    def test_explicit_request_must_match_the_live_endpoint(self):
        e = endpoint(static=True)
        e["IPAMConfig"]["IPv4Address"] = "172.28.0.99"
        with self.assertRaisesRegex(ValueError, "^Explicit restart address does not match"):
            plan(record("database", "postgres", {"mesh": e}))

    def test_conflicting_static_requests_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "^Conflicting explicit restart"):
            plan(record("database", "postgres", {"mesh": endpoint(static=True)}),
                 record("graph", "fuseki", {"mesh": endpoint(static=True)}))

    def test_malformed_or_unqualified_endpoint_metadata_fails_without_values(self):
        base = record("database", "postgres", {"mesh": endpoint(static=True)})
        mutations = [lambda x: x.update(running=False), lambda x: x.update(role="unknown-publisher"),
                     lambda x: x.update(networks=None),
                     lambda x: x["networks"]["mesh"].update(IPAMConfig=[]),
                     lambda x: x["networks"]["mesh"].update(IPAMConfig={"LinkLocalIPs": ["169.254.1.2"]}),
                     lambda x: x["networks"]["mesh"].update(IPAMConfig={"unknown": "SYNTHETIC_SENSITIVE"}),
                     lambda x: x["networks"]["mesh"].update(IPAddress="SYNTHETIC_SENSITIVE"),
                     lambda x: x["networks"]["mesh"].update(IPAddress="172.28.0.2/24"),
                     lambda x: x["networks"]["mesh"].update(GlobalIPv6Address="172.28.0.3"),
                     lambda x: x["networks"]["mesh"].pop("NetworkID"),
                     lambda x: x["networks"]["mesh"].pop("IPAddress"),
                     lambda x: x["networks"]["mesh"].update(IPAddress=""),
                     lambda x: x["networks"].update(alias=copy.deepcopy(x["networks"]["mesh"]))]
        for change in mutations:
            value = copy.deepcopy(base)
            change(value)
            with self.subTest(change=change), self.assertRaises(ValueError) as error:
                plan(value)
            self.assertNotIn("SYNTHETIC_SENSITIVE", str(error.exception))
            self.assertNotIn("172.28.", str(error.exception))

    def test_duplicate_missing_extra_and_stopped_inventory_is_not_partial_admission(self):
        r = record("database", "postgres")
        for raw in ["", "not json", metadata([r, r]), metadata([record("other", "postgres")]),
                    metadata([{**r, "running": 1}]), '{"id":"database","id":"database"}',
                    metadata([{**r, "environment": "SYNTHETIC_SENSITIVE"}])]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                plan_restarts(["database"], raw)

    def test_metadata_and_inventory_work_are_bounded_before_inspection(self):
        with self.assertRaises(ValueError):
            plan_restarts(["database"], "x" * (MAX_METADATA_BYTES + 1))
        with patch.object(backup, "run") as run, self.assertRaises(ValueError):
            backup.restart_plan([f"container-{i}" for i in range(MAX_CONTAINERS + 1)])
        run.assert_not_called()

    def test_previously_stopped_containers_are_not_added_to_plan(self):
        self.assertEqual(plan(record("only", "postgres")), [["only"]])
        self.assertEqual(plan_restarts([], ""), [])


class PreflightAdmissionTests(unittest.TestCase):
    def invoke(self, argv, records, commands):
        def run(command, **_kwargs):
            commands.append(command)
            if "--status" in command:
                return "\n".join(r["id"] for r in records)
            if command[:2] == ["docker", "inspect"]:
                return metadata(records)
            return ""

        output, errors = io.StringIO(), io.StringIO()
        with (patch("sys.argv", ["manage_backup.py", *argv]),
              patch.object(backup, "compose_command", return_value=["docker", "compose"]),
              patch.object(backup, "inventory", return_value=({}, {})) as inventory,
              patch.object(backup, "helper") as helper, patch.object(backup, "run", side_effect=run),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
            code = backup.main()
        return code, output.getvalue(), errors.getvalue(), inventory, helper

    def test_preflight_only_reads_metadata_without_archive_keys_or_container_changes(self):
        commands = []
        result = self.invoke(["backup", "--preflight-only"], [record("database", "postgres")], commands)
        self.assertEqual(result[0], 0)
        self.assertEqual(json.loads(result[1]), {"schema": "backup-restart-preflight-v1",
                         "restart_order_verified": True, "running_containers": 1, "restart_groups": 1,
                         "backup_qualified": False, "changes_performed": False})
        result[3].assert_not_called()
        result[4].assert_not_called()
        self.assertTrue(all(c[:2] not in (["docker", "stop"], ["docker", "start"]) for c in commands))

    def test_unsafe_preflight_is_read_only_and_cannot_claim_qualification(self):
        commands = []
        rows = [record("edge", "web", {"mesh": endpoint(static=True)}),
                record("graph", "fuseki", {"mesh": endpoint(address="172.28.0.3")})]
        result = self.invoke(["backup", "--preflight-only"], rows, commands)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], "")
        self.assertIn("Unsafe restart plan", result[2])
        self.assertNotIn("172.28.", result[2])
        result[3].assert_not_called()
        result[4].assert_not_called()
        self.assertFalse(any(c[:2] in (["docker", "stop"], ["docker", "start"]) for c in commands))

    def test_regular_backup_blocks_unsafe_plan_before_stop_or_encryption(self):
        commands = []
        rows = [record("database", "postgres", {"mesh": endpoint(address="172.28.0.3")}),
                record("application", "api", {"mesh": endpoint(static=True)})]
        with tempfile.TemporaryDirectory() as directory:
            key, archive = Path(directory) / "recipients", Path(directory) / "sample.age"
            key.write_text("SYNTHETIC")
            result = self.invoke(["backup", str(archive), "--recipients-file", str(key), "--stop-services"],
                                 rows, commands)
            self.assertEqual(result[0], 1)
            self.assertFalse(archive.exists())
            self.assertFalse(archive.with_name("sample.age.partial").exists())
        result[4].assert_not_called()
        self.assertFalse(any(c[:2] in (["docker", "stop"], ["docker", "start"]) for c in commands))

    def test_preflight_rejects_ambiguous_downtime_key_archive_and_restore_options(self):
        for args in [["backup", "sample.age", "--preflight-only"],
                     ["backup", "--preflight-only", "--stop-services"],
                     ["backup", "--preflight-only", "--recipients-file", "not-read"],
                     ["restore", "--preflight-only"]]:
            commands = []
            with self.subTest(args=args):
                result = self.invoke(args, [], commands)
                self.assertEqual(result[0], 1)
                self.assertEqual(commands, [])
                result[4].assert_not_called()


if __name__ == "__main__":
    unittest.main()
