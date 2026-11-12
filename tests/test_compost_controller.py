"""Chosen journal modes with actual stores and injected, network-blocked HTTP."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.memory.compost import CompostStore
from core.runtime.rehearsal.controller import (
    RehearsalController, _memory_effect, validate_choice, snapshot_profiles,
    LEGACY_CHOICE_INSTRUCTIONS,
)
from core.runtime.rehearsal.continuity import owner_continuity
from core.runtime.rehearsal.provider import AGENT_IDS, CAPABILITIES, OpenRouterTransport
from core.runtime.rehearsal.store import JOURNAL_OPTIONS, RehearsalStore, RehearsalError
from core.runtime.rehearsal.witness import WitnessStore
from tests.test_rehearsal_provider import Response, manifest


class CompostControllerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = RehearsalStore(Path(tmp.name) / "runs")
        raw = manifest()
        raw["limits"]["max_parallelism"] = 1
        self.run_id = self.store.prepare(raw)["run_id"]
        self.path = self.store.run_path(self.run_id)
        self.calls = []
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def compost(self, owner):
        return CompostStore(self.path / "memory" / f"{owner}.sqlite3", owner)

    def controller(self, http):
        return RehearsalController(self.store, self.run_id,
                                   transport=OpenRouterTransport("scripted-offline", http_post=http))

    def current(self, kwargs):
        owner = kwargs["json"]["model"].split("/", 1)[1]
        return next(j for j in self.store.list_jobs(self.run_id)
                    if j["agent_id"] == owner and j["status"] == "running")

    @staticmethod
    def text(kwargs):
        return "\n".join(m["content"] for m in kwargs["json"]["messages"])

    def rest(self, _url, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return Response(model=kwargs["json"]["model"])

    def test_strict_optional_subchoices_no_coercion_guessed_fallback_or_foreign_fields(self):
        valid = [
            {"action": "journal"},
            {"action": "journal", "journal_mode": "note"},
            {"action": "journal", "channels": ["trading", "idea", "orientation"]},
            {"action": "journal", "journal_mode": "compost", "channels": ["unclassified"]},
            {"action": "journal", "journal_mode": "distill", "source_ids": list(range(1, 21)), "release": False},
            {"action": "journal", "journal_mode": "witness"},
        ]
        for choice in valid:
            self.assertEqual(validate_choice(json.dumps(choice)), choice)
        invalid = [
            {"action": "rest", "journal_mode": "note"},
            {"action": "journal", "journal_mode": "digest"},
            {"action": "journal", "journal_mode": True},
            {"action": "journal", "channels": []},
            {"action": "journal", "channels": ["idea", "idea"]},
            {"action": "journal", "channels": ["unclassified", "idea"]},
            {"action": "journal", "channels": "idea"},
            {"action": "journal", "channels": ["siren"]},
            {"action": "journal", "source_ids": [1]},
            {"action": "journal", "journal_mode": "distill", "source_ids": [True]},
            {"action": "journal", "journal_mode": "distill", "source_ids": [1, 1]},
            {"action": "journal", "journal_mode": "distill", "source_ids": ["1"]},
            {"action": "journal", "journal_mode": "distill", "source_ids": []},
            {"action": "journal", "journal_mode": "distill", "source_ids": list(range(1, 22))},
            {"action": "journal", "release": True},
            {"action": "journal", "journal_mode": "distill", "release": "true"},
            {"action": "journal", "journal_mode": "distill", "release": 1},
            {"action": "journal", "journal_mode": "witness", "channels": ["idea"]},
            {"action": "journal", "owner": "siren"},
            {"action": "journal", "path": "../memory/siren.sqlite3"},
        ]
        for choice in invalid:
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                validate_choice(json.dumps(choice))
        for raw in ('{"action":"journal","journal_mode":"note","journal_mode":"compost"}',
                    '```{"action":"journal"}```', '{"action":"journal","release":NaN}'):
            with self.assertRaises(ValueError):
                validate_choice(raw)

    def test_all_seven_chosen_compost_then_distill_one_picker_one_activity_frozen_sources(self):
        sent_sources = {}
        def http(_url, **kwargs):
            job, text = self.current(kwargs), self.text(kwargs)
            self.calls.append((deepcopy(job), deepcopy(kwargs)))
            details = self.store.get_decision_details(self.run_id, job["wake_id"])
            self.assertEqual(details["metadata"]["offered_actions"], list(CAPABILITIES))
            self.assertEqual(details["metadata"]["journal_options"], JOURNAL_OPTIONS)
            self.assertEqual(len(details["metadata"]["action_costs"]), 5)
            self.assertTrue(all(c["max_requests"] == (1 if c["action"] == "rest" else 2)
                                for c in details["metadata"]["action_costs"]))
            if "REHEARSAL CHOICE" in text:
                self.assertIn("Distill is chosen, not automatic", text)
                self.assertNotIn("UNRELATED-SEED-BODY", text)
                mode = "compost" if job["round"] == 1 else "distill"
                choice = {"action": "journal", "journal_mode": mode,
                          "channels": ["idea", "orientation"]}
                if mode == "distill":
                    prior = next(j for j in self.store.list_jobs(self.run_id)
                                 if j["wake_id"] == job["agent_id"] + "-r1")
                    choice.update(source_ids=[prior["record_refs"][0]["id"]], release=True)
                content = json.dumps(choice)
            elif job["round"] == 1:
                content = "FRAGMENT-" + job["agent_id"] + "\nA distinction left open."
            else:
                compost = self.compost(job["agent_id"])
                key = f"rehearsal:{job['wake_id']}:journal:distill"
                chosen = self.store.get_choice(self.run_id, job["wake_id"])["source_ids"]
                prepared = compost.prepare_distillation(key, chosen)
                sent_sources[job["agent_id"]] = prepared
                self.assertIn(json.dumps(prepared, ensure_ascii=False, sort_keys=True), text)
                self.assertEqual(prepared["source_ids"], chosen)
                self.assertFalse(compost.is_released(chosen[0]))
                # A note added during HTTP must not enter the frozen selection.
                compost.append_note("late-seed", "LATE-NOT-SELECTED", note_kind="compost", source_mode="offline")
                for peer in set(AGENT_IDS) - {job["agent_id"]}:
                    self.assertNotIn("FRAGMENT-" + peer, text)
                content = "LITERAL-DISTILLATION-" + job["agent_id"] + "\nNo invented resolution."
            return Response(content=content, model=kwargs["json"]["model"])
        for owner in AGENT_IDS:
            self.compost(owner).append_note("unrelated", "UNRELATED-SEED-BODY", note_kind="compost", source_mode="offline")
        result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_count"], 28)
        for owner in AGENT_IDS:
            compost = self.compost(owner)
            notes = compost.list_notes(channel="idea")["notes"]
            digest = next(n for n in notes if n["note_kind"] == "distillation")
            fragment = next(n for n in notes if n["note_kind"] == "compost")
            self.assertEqual(digest["content"], "LITERAL-DISTILLATION-" + owner + "\nNo invented resolution.")
            self.assertEqual(digest["source_ids"], [fragment["id"]])
            self.assertEqual(digest["channels"], ["idea", "orientation"])
            self.assertEqual(fragment["state"], "released")
            self.assertEqual(compost.get_note(fragment["id"])["content"], "FRAGMENT-" + owner + "\nA distinction left open.")
            self.assertEqual(digest["source_mode"], "offline")
            # Explicit original reads work; routine continuity excludes release.
            context = owner_continuity(self.store, self.run_id, {"agent_id": owner, "round": 2})
            self.assertEqual(context["refs"], [])
            self.assertEqual(context["status"], "empty")
        for job, kwargs in self.calls:
            activity = "choice" if "REHEARSAL CHOICE" in self.text(kwargs) else "journal"
            capture = next(r for r in self.store.get_decision_details(self.run_id, job["wake_id"])["requests"]
                           if r["activity"] == activity)
            self.assertEqual(capture["messages"], kwargs["json"]["messages"])
        witness = WitnessStore(self.path / "witness.sqlite3")
        for owner in AGENT_IDS:
            accounts = witness.list_accounts(owner)["accounts"]
            self.assertEqual(len(accounts), 2)
            self.assertTrue(all(a["method"] == "mechanical" for a in accounts))
            self.assertNotIn("FRAGMENT-", json.dumps(accounts))

    def test_explicit_note_uses_append_and_empty_output_leaves_no_notes(self):
        def http(_url, **kwargs):
            job, text = self.current(kwargs), self.text(kwargs)
            self.calls.append(kwargs)
            if "REHEARSAL CHOICE" in text:
                content = json.dumps({"action": "journal", "journal_mode": "note", "channels": ["unclassified"]})
            else:
                content = "  \n" if job["round"] == 1 else "LITERAL-NOTE-" + job["agent_id"]
            return Response(content=content, model=kwargs["json"]["model"])
        with patch("core.runtime.rehearsal.controller._memory_effect", side_effect=AssertionError("new note uses append")):
            self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertEqual(len(self.calls), 28)
        for owner in AGENT_IDS:
            notes = self.compost(owner).list_notes()["notes"]
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0]["content"], "LITERAL-NOTE-" + owner)
            self.assertEqual(notes[0]["channels"], ["unclassified"])
            self.assertEqual(notes[0]["note_kind"], "note")
            first = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == owner + "-r1")
            self.assertEqual(first["record_refs"], [])

    def test_empty_distillation_releases_nothing_and_source_empty_skips_activity(self):
        def http(_url, **kwargs):
            job, text = self.current(kwargs), self.text(kwargs)
            self.calls.append(kwargs)
            content = json.dumps({"action": "journal", "journal_mode": "distill", "release": True}) if "REHEARSAL CHOICE" in text else "\n"
            return Response(content=content, model=kwargs["json"]["model"])
        for owner in AGENT_IDS[:3]:
            self.compost(owner).append_note("seed", "Kept source", note_kind="compost", source_mode="offline")
        result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.calls), 20)  # Three seeded owners, both rounds.
        for owner in AGENT_IDS[:3]:
            notes = self.compost(owner).list_notes()["notes"]
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0]["state"], "active")
        self.assertTrue(all(j["record_refs"] == [] for j in self.store.list_jobs(self.run_id)))

    def test_witness_reads_only_three_prior_own_accounts_no_second_call_or_memory(self):
        # Preexisting accounts are source-factual, not owner memories.
        witness = WitnessStore(self.path / "witness.sqlite3")
        for owner in AGENT_IDS:
            for index in range(4):
                witness.record(self.store.get_witness_snapshot(self.run_id, owner),
                               scope=owner, operation_key=f"seed:{owner}:{index}")
        prior_ids = {owner: [a["id"] for a in witness.list_accounts(owner)["accounts"]] for owner in AGENT_IDS}
        def http(_url, **kwargs):
            job = self.current(kwargs)
            self.calls.append(kwargs)
            self.assertIn("REHEARSAL CHOICE", self.text(kwargs))
            for ident in prior_ids[job["agent_id"]]:
                self.assertNotIn(ident, self.text(kwargs))  # Not forced into picker.
            return Response(content='{"action":"journal","journal_mode":"witness"}', model=kwargs["json"]["model"])
        seen = []
        original = WitnessStore.list_accounts
        def scoped(obj, scope, limit=3, offset=0):
            self.assertIn(scope, AGENT_IDS)
            self.assertEqual(limit, 3)
            result = original(obj, scope, limit, offset)
            self.assertTrue(all(a["scope"] == scope for a in result["accounts"]))
            seen.append((scope, [a["id"] for a in result["accounts"]]))
            return result
        with patch.object(WitnessStore, "list_accounts", scoped), patch("core.runtime.rehearsal.controller._memory_effect", side_effect=AssertionError("no memory")):
            self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertEqual(len(self.calls), 14)
        self.assertEqual(len(seen), 14)
        self.assertFalse(list((self.path / "memory").glob("*.sqlite3")))
        for job in self.store.list_jobs(self.run_id):
            self.assertEqual(job["journal_mode"], "witness")
            refs = job["record_refs"]
            self.assertEqual(len(refs), 3)
            self.assertTrue(all(r["kind"] == "witness" for r in refs))
            for ref in refs:
                self.assertEqual(witness.get_account(ref["id"], job["agent_id"])["scope"], job["agent_id"])
                self.assertIsNone(witness.get_account(ref["id"], "steward"))
            if job["round"] == 1:
                self.assertEqual([r["id"] for r in refs], prior_ids[job["agent_id"]])

    def test_missing_witness_is_explicit_and_never_writes_agent_memory(self):
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            return Response(content='{"action":"journal","journal_mode":"witness"}', model=kwargs["json"]["model"])
        result = self.controller(http).run()
        self.assertEqual(result["request_count"], 14)
        for owner in AGENT_IDS:
            output = json.loads(self.store.get_output(self.run_id, owner + "-r1"))
            self.assertEqual(output, {"status": "missing" if owner == AGENT_IDS[0] else "ok", "accounts": [], "total": 0})
        self.assertFalse(list((self.path / "memory").glob("*.sqlite3")))

    def test_witness_checkpoint_recovery_never_rereads_or_substitutes_new_accounts(self):
        controller = self.controller(self.rest)
        controller.prepare_profiles()
        witness = WitnessStore(self.path / "witness.sqlite3")
        prior = witness.record(self.store.get_witness_snapshot(self.run_id, "siren"),
                               scope="siren", operation_key="prior")
        token = self.store.begin(self.run_id)
        self.store.claim_job(self.run_id, "siren-r1", token)
        self.store.commit_choice(self.run_id, "siren-r1", token,
                                 {"action": "journal", "journal_mode": "witness"})
        frozen = witness.list_accounts("siren", limit=3)
        self.store.commit_output(self.run_id, "siren-r1", token, json.dumps(frozen))
        witness.record(self.store.get_witness_snapshot(self.run_id, "siren"),
                       scope="siren", operation_key="newer-not-part-of-read")
        self.store.recover(self.run_id)
        with patch.object(WitnessStore, "list_accounts", side_effect=AssertionError("use read checkpoint, not newer accounts")):
            self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "completed")
        first = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertEqual(first["record_refs"], [{"kind": "witness", "id": prior["id"]}])
        self.assertEqual(len(self.calls), 13)
        self.assertFalse(list((self.path / "memory").glob("*.sqlite3")))

    def test_distillation_release_false_keeps_sources_active(self):
        source_id, _ = self.stage_distillation(release=False)
        self.store.recover(self.run_id)
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            content = "KEPT WITH SOURCES ACTIVE" if "REHEARSAL ACTIVITY: journal" in self.text(kwargs) else '{"action":"rest"}'
            return Response(content=content, model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run(resume=True)["status"], "completed")
        self.assertEqual(len(self.calls), 14)
        self.assertFalse(self.compost("siren").is_released(source_id))
        notes = self.compost("siren").list_notes()["notes"]
        digest = next(n for n in notes if n["note_kind"] == "distillation")
        self.assertEqual(digest["source_ids"], [source_id])
        self.assertEqual(digest["content"], "KEPT WITH SOURCES ACTIVE")

    def stage_distillation(self, output=None, apply=False, release=True):
        controller = self.controller(self.rest)
        controller.prepare_profiles()
        token = self.store.begin(self.run_id)
        self.store.claim_job(self.run_id, "siren-r1", token)
        choice = {"action": "journal", "journal_mode": "distill", "release": release}
        self.store.commit_choice(self.run_id, "siren-r1", token, choice)
        compost = self.compost("siren")
        source = compost.append_note("seed", "SOURCE BEFORE REQUEST", note_kind="compost", source_mode="offline")
        key = "rehearsal:siren-r1:journal:distill"
        frozen = compost.prepare_distillation(key)
        if output is not None:
            self.store.commit_output(self.run_id, "siren-r1", token, output)
        if apply:
            compost.apply_distillation(key, output, release=release, source_wake_id="siren-r1", source_mode="offline")
        return source["id"], frozen

    def test_recovery_before_request_uses_frozen_sources_not_late_catalog(self):
        source_id, frozen = self.stage_distillation()
        late = self.compost("siren").append_note("late", "LATE BODY MUST NOT ENTER", note_kind="compost", source_mode="offline")["id"]
        self.store.recover(self.run_id)
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            if "REHEARSAL ACTIVITY: journal" in self.text(kwargs):
                self.assertIn(json.dumps(frozen, ensure_ascii=False, sort_keys=True), self.text(kwargs))
                self.assertNotIn("LATE BODY MUST NOT ENTER", self.text(kwargs))
                content = "RECOVERED LITERAL DISTILLATION"
            else:
                content = '{"action":"rest"}'
            return Response(content=content, model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run(resume=True)["status"], "completed")
        self.assertEqual(len(self.calls), 14)  # Existing choice, one activity +13 pickers.
        self.assertTrue(self.compost("siren").is_released(source_id))
        self.assertFalse(self.compost("siren").is_released(late))

    def test_recovery_after_output_and_after_apply_never_resends_or_duplicates(self):
        for already_applied in (False, True):
            with self.subTest(already_applied=already_applied):
                # Independent actual control/memory stores for each checkpoint.
                if already_applied:
                    raw = manifest(); raw["limits"]["max_parallelism"] = 1
                    self.run_id = self.store.prepare(raw)["run_id"]
                    self.path = self.store.run_path(self.run_id)
                    self.calls.clear()
                source_id, _ = self.stage_distillation("CHECKPOINT LITERAL TEXT", apply=already_applied)
                self.store.recover(self.run_id)
                self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "completed")
                self.assertEqual(len(self.calls), 13)
                notes = self.compost("siren").list_notes()["notes"]
                self.assertEqual(len(notes), 2)
                digest = next(n for n in notes if n["note_kind"] == "distillation")
                self.assertEqual(digest["content"], "CHECKPOINT LITERAL TEXT")
                self.assertEqual(digest["source_ids"], [source_id])
                self.assertTrue(self.compost("siren").is_released(source_id))

    def test_apply_failure_preserves_output_no_release_then_explicit_recovery(self):
        source_id, _ = self.stage_distillation("RETURNED TEXT")
        self.store.recover(self.run_id)
        with patch.object(CompostStore, "apply_distillation", side_effect=RuntimeError("safe simulated apply failure")):
            # end() keeps the established checkpoint-safe pending recovery;
            # only explicit resume applies the returned output, never a resend.
            self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "partial")
        self.assertFalse(self.compost("siren").is_released(source_id))
        self.assertEqual(self.store.get_output(self.run_id, "siren-r1"), "RETURNED TEXT")
        self.assertEqual(len(self.calls), 13)
        self.calls.clear()
        self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "completed")
        self.assertEqual(self.calls, [])
        self.assertTrue(self.compost("siren").is_released(source_id))

    def test_transport_failure_freezes_sources_releases_nothing_no_ambiguous_retry(self):
        source_id, frozen = self.stage_distillation()
        self.store.recover(self.run_id)
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            if "REHEARSAL ACTIVITY: journal" in self.text(kwargs):
                raise ConnectionError("unconfirmed response")
            return Response(model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run(resume=True)["status"], "uncertain")
        self.assertEqual(self.compost("siren").prepare_distillation("rehearsal:siren-r1:journal:distill"), frozen)
        self.assertFalse(self.compost("siren").is_released(source_id))
        self.calls.clear()
        self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "uncertain")
        self.assertEqual(self.calls, [])

    def test_rest_inquiry_library_roam_keep_original_frozen_system_prompts(self):
        controller = self.controller(self.rest)
        marker = controller.prepare_profiles()
        before = {owner: controller._system_prompt(owner) for owner in AGENT_IDS}
        from core.runtime.rehearsal.examples import ScriptedHTTP
        scripted = ScriptedHTTP()
        def http(url, **kwargs):
            self.calls.append(kwargs)
            owner = kwargs["json"]["model"].split("/", 1)[1]
            self.assertEqual(kwargs["json"]["messages"][0]["content"], before[owner])
            return scripted(url, **kwargs)
        with patch("core.runtime.rehearsal.controller._prompt_builder", side_effect=AssertionError("never rebuild prepared prompts")):
            self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertEqual({j["action"] for j in self.store.list_jobs(self.run_id)}, set(CAPABILITIES))
        self.assertEqual(controller.prepare_profiles(), marker)
        self.assertEqual(before, {owner: controller._system_prompt(owner) for owner in AGENT_IDS})

    def test_legacy_plain_journal_checkpoint_is_not_silently_classified(self):
        controller = self.controller(self.rest)
        controller.prepare_profiles()
        token = self.store.begin(self.run_id)
        self.store.claim_job(self.run_id, "siren-r1", token)
        self.store.commit_choice(self.run_id, "siren-r1", token, {"action": "journal"})
        self.store.commit_output(self.run_id, "siren-r1", token, "OLD PLAIN JOURNAL")
        self.store.recover(self.run_id)
        with patch.object(CompostStore, "append_note", side_effect=AssertionError("legacy uses memory effect")):
            self.assertEqual(self.controller(self.rest).run(resume=True)["status"], "completed")
        note = self.compost("siren").list_notes()["notes"][0]
        self.assertEqual(note["channels"], ["unclassified"])
        self.assertIsNone(note["source_mode"])
        with sqlite3.connect(self.path / "memory" / "siren.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rehearsal_effects").fetchone()[0], 1)
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='compost_note_metadata'").fetchone())
        first = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertNotIn("journal_mode", first)
        self.assertIsNone(first["decision_context"])
        self.assertEqual(len(self.calls), 13)
        context = owner_continuity(self.store, self.run_id, {"agent_id": "siren", "round": 2})
        self.assertIn("OLD PLAIN JOURNAL", json.dumps(context))
        legacy_private = {"include_metadata": False, "include_continuity": False}
        self.assertEqual(controller._choice_messages({}, legacy_private)[0]["content"], LEGACY_CHOICE_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
