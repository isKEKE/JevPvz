import json
import subprocess
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from dashboard.server import StatePoller, TraceFileReader, create_dashboard_server
from jev.trace import EVENT_ACTION_RESULT, EVENT_JOB_END, RUNTIME_EVENT_NAMES, TraceRecorder


def runtime_event(sequence, name, **fields):
    """One schema-2 runtime event with the fixed envelope a reader expects."""
    event = {
        "schema_version": 2,
        "event": name,
        "event_sequence": sequence,
        "run_id": "run-v2",
        "timestamp_utc": "2026-09-27T10:00:00.000Z",
        "job_id": None,
        "branch_id": None,
        "stage_id": None,
        "request_id": None,
        "execution_id": None,
    }
    event.update(fields)
    return event


def runtime_run_events():
    """A two-branch v2 run whose execution order differs from completion order."""
    return [
        runtime_event(1, "job_start", job_id="job-000001", branch_id="plant", stage_id="plant-decision",
                      sample_sequence=12, sample_age_ms=120, strategy={"phase": "economy"}),
        runtime_event(2, "request_result", job_id="job-000001", branch_id="plant", stage_id="plant-decision",
                      request_id="job-000001-request-1", latency_ms=210, target_choice_rule="argmax",
                      typed_answers={"row_needs_response_r2": {"noul": 0.91}},
                      merge={"needed_rows": [2], "chosen_option": "peashooter@r2c4",
                             "selected_option": "peashooter@r1c0", "reranked": True,
                             "rejected_option": "peashooter@r2c4"}),
        runtime_event(3, "job_end", job_id="job-000001", branch_id="plant", stage_id="plant-decision",
                      outcome="selected", reliable=True),
        runtime_event(4, "job_start", job_id="job-000002", branch_id="collect", stage_id="collect-decision",
                      sample_sequence=12),
        runtime_event(5, "job_end", job_id="job-000002", branch_id="collect", stage_id="collect-decision",
                      outcome="selected", reliable=True),
        runtime_event(6, EVENT_ACTION_RESULT, job_id="job-000002", branch_id="collect",
                      execution_id="exec-000001", effective_action="collect", queue_delay_ms=100,
                      boundary={"status": "success", "action": "collect_item", "elapsed_ms": 30}),
        runtime_event(7, EVENT_ACTION_RESULT, job_id="job-000001", branch_id="plant",
                      execution_id="exec-000002", effective_action="plant", queue_delay_ms=900,
                      boundary={"status": "success", "action": "place_plant", "elapsed_ms": 120}),
        runtime_event(8, "job_start", job_id="job-000003", branch_id="plant", stage_id="plant-decision",
                      sample_sequence=13),
        runtime_event(9, "job_end", job_id="job-000003", branch_id="plant", stage_id="plant-decision",
                      outcome="selected", reliable=True),
        runtime_event(10, "proposal_discarded", job_id="job-000003", branch_id="plant",
                      effective_action="plant", discard_reason="proposal_replaced", queue_delay_ms=40),
        runtime_event(11, "runtime_stop", stop_reason="max_cycles", sample_sequence=13,
                      pending_proposals=[]),
    ]


class DashboardHttpTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "schema_version": 1,
            "status": "ok",
            "valid": True,
            "decision_ready": False,
            "observed_at_utc": "2026-09-24T02:00:00Z",
            "availability": {"sun_balance": "provisional", "cards.cost": "unavailable"},
            "sun_balance": 3333,
            "cards": [],
            "collectible_suns": None,
            "zombies": [{"type_code": 0, "type_name": "normal_zombie", "row": 0, "x": 10.0, "y": 50.0,
                         "distance_to_house_px": 10.0, "distance_to_house_cells": 0}],
            "lanes": [{"row": 0, "zombie_count": 1, "nearest_zombie_distance_to_house_px": 10, "nearest_zombie_distance_to_house_cells": 0}],
            "items": [{"type_code": 4, "type_name": "sun", "x": 10.0, "y": 20.0}],
            "errors": [],
        }
        self.poller = StatePoller(50, sampler=lambda: self.sample)
        self.server = create_dashboard_server(self.poller, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.poller.start()
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.poller.stop()
        self.thread.join(timeout=1)

    def test_state_endpoint_returns_shared_json_and_no_store(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as response:
            record = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(record["sun_balance"], 3333)
        self.assertEqual(record["availability"]["cards.cost"], "unavailable")

    def test_jev_endpoint_projects_the_same_latest_sample(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as response:
            all_state = json.loads(response.read())
        with urlopen(f"http://127.0.0.1:{self.port}/api/jev-state") as response:
            jev_state = json.loads(response.read())
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(jev_state["sample_sequence"], all_state.get("sample_sequence"))
        self.assertEqual(jev_state["observed_at_utc"], all_state["observed_at_utc"])
        self.assertNotIn("availability", jev_state)
        self.assertIn("availability", all_state)
        self.assertNotIn("errors", jev_state)
        self.assertNotIn("evidence", jev_state)
        self.assertEqual(jev_state["sun_balance"], all_state["sun_balance"])
        self.assertEqual(jev_state["zombies"][0]["distance_to_house_px"], 10.0)
        self.assertEqual(jev_state["zombies"][0]["distance_to_house_cells"], 0)
        self.assertNotIn("nearest_zombie_distance_to_house_px", jev_state["zombies"][0])
        self.assertEqual(jev_state["lanes"][0], {"row": 0, "zombie_count": 1, "nearest_zombie_distance_to_house_cells": 0})
        self.assertNotIn("collectible_suns", jev_state)
        self.assertIn("collectible_suns", all_state)
        self.assertEqual(jev_state["items"][0]["type_name"], "sun")
        self.assertEqual(jev_state["lanes"][0], {
            "row": 0,
            "zombie_count": 1,
            "nearest_zombie_distance_to_house_cells": 0,
        })
        self.assertIn("nearest_zombie_distance_to_house_px", all_state["lanes"][0])

    def test_both_profiles_read_one_shared_poller_sample(self):
        calls = []
        sample = {**self.sample, "sample_sequence": 17}
        poller = StatePoller(50, sampler=lambda: calls.append(1) or sample)
        poller.sample_once()
        server = create_dashboard_server(poller, port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/state") as response:
                all_state = json.loads(response.read())
            with urlopen(f"http://127.0.0.1:{port}/api/jev-state") as response:
                jev_state = json.loads(response.read())
            self.assertEqual(len(calls), 1)
            self.assertEqual(all_state["sample_sequence"], jev_state["sample_sequence"])
            self.assertEqual(all_state["observed_at_utc"], jev_state["observed_at_utc"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_page_and_static_resources_are_served_without_external_dependencies(self):
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/app.js") as response:
            script = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        self.assertIn("草坪状态", page)
        self.assertIn("/static/style.css", page)
        self.assertNotIn("LAWN_GEOMETRY", script)
        self.assertIn("const positions = zombiePositionsForState(state)", script)
        self.assertIn("if (!position) continue;", script)
        self.assertNotIn("projectZombieX(zombie.x)", script)
        self.assertIn("const PLANT_ZH", script)
        self.assertIn('localizedType("plant"', script)
        self.assertIn('localizedType("zombie"', script)
        self.assertIn('localizedGame("scene"', script)
        self.assertNotIn("fetch(\"http", script)

    def test_state_observer_route_uses_shared_api_and_same_tab_navigation(self):
        with urlopen(f"http://127.0.0.1:{self.port}/state") as response:
            page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
        with urlopen(f"http://127.0.0.1:{self.port}/static/state-page.js") as response:
            script = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            home = response.read().decode("utf-8")
        self.assertIn('href="/state"', home)
        self.assertIn('href="/"', page)
        self.assertIn('profile === "jev" ? "/api/jev-state" : "/api/state"', script)
        self.assertIn('data-state-profile="jev"', page)
        self.assertIn('data-state-profile="all"', page)
        self.assertIn('当前：JEV State', page)
        self.assertIn("setInterval(fetchObservedState", script)
        self.assertIn("旧样本已清除", script)
        self.assertIn("服务不可达", script)
        self.assertNotIn('target="_blank"', home + page)
        self.assertIn('id="state-copy-button"', page)
        self.assertIn('id="state-copy-status"', page)
        self.assertIn('writeText(currentStateJson)', script)
        self.assertIn('stateById("state-copy-button").disabled = currentStateJson === null;', script)
        self.assertIn("复制失败，请检查浏览器剪贴板权限", script)
        self.assertIn('id="state-json" class="json-tree"', page)
        self.assertIn("renderJsonTree", script)
        self.assertIn("expandedPathsByProfile", script)
        self.assertIn("--json-key-width", script)
        self.assertIn("width: var(--json-key-width, auto)", stylesheet)
        self.assertNotIn('<pre id="state-json"', page)

    def test_jev_page_and_explicit_trace_api_share_only_the_configured_file(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "run.jsonl"
            event = {"schema_version": 1, "run_id": "run-v1", "cycle": 1, "sample_sequence": 9, "outcome": "wait"}
            trace_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            poller = StatePoller(50, sampler=lambda: self.sample)
            poller.sample_once()
            server = create_dashboard_server(poller, port=0, jev_trace_file=trace_path)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/jev-trace") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertEqual(payload, {"status": "ok", "events": [event]})

                with urlopen(f"http://127.0.0.1:{port}/jev") as response:
                    page = response.read().decode("utf-8")
                with urlopen(f"http://127.0.0.1:{port}/static/jev-page.js") as response:
                    script = response.read().decode("utf-8")
                with urlopen(f"http://127.0.0.1:{port}/") as response:
                    home = response.read().decode("utf-8")
                with urlopen(f"http://127.0.0.1:{port}/state") as response:
                    state_page = response.read().decode("utf-8")
                self.assertIn('href="/jev"', page)
                self.assertIn('href="/jev"', home)
                self.assertIn('href="/jev"', state_page)
                self.assertIn('fetch("/api/jev-trace"', script)
                self.assertIn("textContent", script)
                self.assertNotIn("innerHTML", script)

                with self.assertRaises(HTTPError) as raised:
                    urlopen(f"http://127.0.0.1:{port}/api/jev-trace?path={trace_path}")
                self.assertEqual(raised.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

    def test_trace_api_reads_v2_runtime_events_and_keeps_the_v1_payload_shape(self):
        v2_events = runtime_run_events()
        with tempfile.TemporaryDirectory() as directory:
            v2_path = Path(directory) / "runtime.jsonl"
            v2_path.write_text("".join(json.dumps(event) + "\n" for event in v2_events), encoding="utf-8")
            v1_event = {"schema_version": 1, "run_id": "run-v1", "cycle": 1, "outcome": "wait"}
            v1_path = Path(directory) / "legacy.jsonl"
            v1_path.write_text(json.dumps(v1_event) + "\n", encoding="utf-8")
            legacy_payload = TraceFileReader(v1_path).read()

            poller = StatePoller(50, sampler=lambda: self.sample)
            poller.sample_once()
            server = create_dashboard_server(poller, port=0, jev_trace_file=v2_path)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/jev-trace") as response:
                    runtime_payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertIn("no-store", response.headers["Cache-Control"])
                # No request may name another file, not even a valid legacy Trace.
                with self.assertRaises(HTTPError) as raised:
                    urlopen(f"http://127.0.0.1:{port}/api/jev-trace?path={v1_path}")
                self.assertEqual(raised.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

        self.assertEqual(runtime_payload["status"], "ok")
        self.assertEqual(runtime_payload["schema_version"], 2)
        self.assertEqual(runtime_payload["events"], v2_events)
        self.assertEqual({event["event"] for event in runtime_payload["events"]}, set(RUNTIME_EVENT_NAMES))
        self.assertEqual([event["event_sequence"] for event in runtime_payload["events"]], list(range(1, 12)))
        completions = [
            event["job_id"] for event in runtime_payload["events"] if event["event"] == EVENT_JOB_END
        ]
        executions = [
            event["job_id"] for event in runtime_payload["events"] if event["event"] == EVENT_ACTION_RESULT
        ]
        self.assertEqual(completions, ["job-000001", "job-000002", "job-000003"])
        self.assertEqual(executions, ["job-000002", "job-000001"])

        # The v1 payload keeps exactly its original shape, so a legacy cycle is
        # never served as a branch event.
        self.assertEqual(legacy_payload, {"status": "ok", "events": [v1_event]})
        self.assertNotIn("schema_version", legacy_payload)

    def test_trace_reader_rejects_mixed_versions_and_unknown_runtime_events(self):
        legacy = {"schema_version": 1, "run_id": "run-v1", "cycle": 1}
        with tempfile.TemporaryDirectory() as directory:
            mixed = Path(directory) / "mixed.jsonl"
            mixed.write_text(json.dumps(legacy) + "\n" + json.dumps(runtime_event(1, "job_end")) + "\n", encoding="utf-8")
            self.assertEqual(TraceFileReader(mixed).read(), {"status": "error", "events": []})

            reversed_mixed = Path(directory) / "reversed.jsonl"
            reversed_mixed.write_text(json.dumps(runtime_event(1, "job_end")) + "\n" + json.dumps(legacy) + "\n", encoding="utf-8")
            self.assertEqual(TraceFileReader(reversed_mixed).read(), {"status": "error", "events": []})

            unknown = Path(directory) / "unknown.jsonl"
            unknown.write_text(json.dumps({**runtime_event(1, "job_end"), "event": "not_an_event"}) + "\n", encoding="utf-8")
            self.assertEqual(TraceFileReader(unknown).read(), {"status": "error", "events": []})

            unsequenced = Path(directory) / "unsequenced.jsonl"
            bad = runtime_event(1, "job_end")
            del bad["event_sequence"]
            unsequenced.write_text(json.dumps(bad) + "\n", encoding="utf-8")
            self.assertEqual(TraceFileReader(unsequenced).read(), {"status": "error", "events": []})

            no_cycle = Path(directory) / "nocycle.jsonl"
            no_cycle.write_text(json.dumps({"schema_version": 1, "run_id": "run-v1"}) + "\n", encoding="utf-8")
            self.assertEqual(TraceFileReader(no_cycle).read(), {"status": "error", "events": []})

    def test_unconfigured_trace_endpoint_returns_explicit_idle_state(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/jev-trace") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload, {"status": "unconfigured", "events": []})

    def test_trace_reader_reports_unconfigured_missing_empty_and_partial_tail(self):
        self.assertEqual(TraceFileReader(None).read(), {"status": "unconfigured", "events": []})
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.jsonl"
            self.assertEqual(TraceFileReader(missing).read(), {"status": "missing", "events": []})
            path = Path(directory) / "partial.jsonl"
            path.write_bytes(b"")
            self.assertEqual(TraceFileReader(path).read(), {"status": "empty", "events": []})
            complete = {"schema_version": 1, "run_id": "run-v1", "cycle": 1}
            partial = {"schema_version": 1, "run_id": "run-v1", "cycle": 2}
            path.write_bytes((json.dumps(complete) + "\n" + json.dumps(partial)[:-1]).encode("utf-8"))
            self.assertEqual(TraceFileReader(path).read(), {"status": "ok", "events": [complete]})

    def test_trace_reader_returns_only_the_latest_hundred_complete_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "many.jsonl"
            events = [{"schema_version": 1, "run_id": "run-v1", "cycle": index} for index in range(1, 106)]
            path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
            payload = TraceFileReader(path).read()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["events"]), 100)
        self.assertEqual(payload["events"][0]["cycle"], 6)
        self.assertEqual(payload["events"][-1]["cycle"], 105)

    def test_trace_reader_reports_invalid_complete_line_and_unreadable_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.jsonl"
            malformed.write_text('{"schema_version":1}\nnot-json\n', encoding="utf-8")
            self.assertEqual(TraceFileReader(malformed).read(), {"status": "error", "events": []})
            self.assertEqual(TraceFileReader(Path(directory)).read(), {"status": "error", "events": []})

    def test_dashboard_reader_can_read_flushed_events_while_loop_writer_is_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "concurrent.jsonl"
            event = {"schema_version": 1, "run_id": "run-v1", "cycle": 1, "sample_sequence": 5}
            with TraceRecorder(path) as recorder:
                recorder.write_event(event)
                payload = TraceFileReader(path).read()
                self.assertEqual(payload, {"status": "ok", "events": [event]})

    def test_jev_timeline_renders_untrusted_values_as_text_and_fetches_fixed_route(self):
        script = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const tags = [];
const htmlWrites = [];
function element(tag) {
  const node = {tagName: tag, children: [], className: "", append(...items) {this.children.push(...items);},
    replaceChildren(...items) {this.children = items;},
    set textContent(value) {this._text = String(value ?? ""); this.children = [];},
    get textContent() {return (this._text || "") + this.children.map((item) => item.textContent).join("");}};
  Object.defineProperty(node, "innerHTML", {set(value) {htmlWrites.push(String(value));}, get() {return "";}});
  return node;
}
const elements = {};
let requestedUrl = "";
const document = {getElementById(id) {return elements[id] ||= element("div");},
  createElement(tag) {tags.push(tag); return element(tag);}, addEventListener() {}};
const context = vm.createContext({document, window: {setInterval() {}}, fetch: async (url) => {
  requestedUrl = url; return {ok: true, json: async () => ({status: "ok", events: [{schema_version: 1, cycle: 1,
    sample_sequence: 8, timestamp_utc: "now", outcome: "action_success", effective_decision: "plant",
    state: {sun_balance: 50, game: {phase: "playing"}},
    router: {response: {candidates: ["plant"], noul_probabilities: {plant: 0.8}, choice: "plant", confidence: 0.8}},
    action: {intent: "plant", status: "selected", target: {action: "place_plant", type_name: "<img src=x onerror=alert(1)>", row: 2, col: 3}},
    boundary: {status: "success", action: "place_plant"}, next_observation: {sample_sequence: 9}},
    {schema_version: 1, cycle: 2, sample_sequence: 9, timestamp_utc: "now", outcome: "action_wait",
     effective_decision: "wait", router: {fallback_reason: "router_confidence_below_threshold",
       response: {candidates: ["plant"], noul_probabilities: {plant: 0.8}, choice: "plant", confidence: 0.55}},
     action: {intent: "plant", status: "low_confidence", fallback_reason: "cell_confidence_below_threshold", target: null},
     boundary: null, next_observation: {sample_sequence: 10}}]})};
}});
vm.runInContext(fs.readFileSync("dashboard/static/jev-page.js", "utf8"), context);
(async () => {await vm.runInContext("fetchJevTrace()", context); const text = elements["jev-timeline"].textContent;
  const statusTitles = [];
  for (const status of ["unconfigured", "missing", "empty", "error"]) {
    vm.runInContext(`renderTrace({status: "${status}", events: []})`, context);
    statusTitles.push(elements["trace-status-title"].textContent);
  }
  console.log(JSON.stringify({requestedUrl, text, statusTitles, htmlWrites, tags}));})();'''
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, encoding="utf-8")
        rendered = json.loads(result.stdout)
        self.assertEqual(rendered["requestedUrl"], "/api/jev-trace")
        self.assertIn("<img src=x onerror=alert(1)>", rendered["text"])
        self.assertIn("Router 回退", rendered["text"])
        self.assertIn("Action：种植", rendered["text"])
        self.assertEqual(rendered["statusTitles"], ["尚未配置 Trace", "等待 Trace 文件", "等待首个完整周期", "Trace 暂时不可读"])
        self.assertEqual(rendered["htmlWrites"], [])
        self.assertTrue(set(rendered["tags"]).issubset({"article", "div", "h3", "time", "p"}))

    def test_jev_page_keeps_decision_completion_and_actual_execution_order_separate(self):
        script = r'''const fs = require("node:fs");
const vm = require("node:vm");
const tags = [];
function element(tag) {
  return {tagName: tag, children: [], className: "", dataset: {},
    append(...items) {this.children.push(...items);},
    replaceChildren(...items) {this.children = items;},
    set textContent(value) {this._text = String(value ?? ""); this.children = [];},
    get textContent() {return (this._text || "") + this.children.map((item) => item.textContent).join("");}};
}
const elements = {};
const document = {getElementById(id) {return elements[id] ||= element("div");},
  createElement(tag) {tags.push(tag); return element(tag);}, addEventListener() {}};
const context = vm.createContext({document});
vm.runInContext(fs.readFileSync("dashboard/static/jev-page.js", "utf8"), context);
const payload = {status: "ok", schema_version: 2, events: [
  {schema_version: 2, event: "job_start", event_sequence: 1, job_id: "job-000001", branch_id: "plant", sample_sequence: 12, sample_age_ms: 120, strategy: {phase: "economy"}},
  {schema_version: 2, event: "request_result", event_sequence: 2, job_id: "job-000001", branch_id: "plant", request_id: "job-000001-request-1", latency_ms: 210, target_choice_rule: "argmax",
    merge: {needed_rows: [2], chosen_option: "peashooter@r2c4", selected_option: "peashooter@r1c0", reranked: true, rejected_option: "peashooter@r2c4"}},
  {schema_version: 2, event: "job_end", event_sequence: 3, job_id: "job-000001", branch_id: "plant", outcome: "selected"},
  {schema_version: 2, event: "job_start", event_sequence: 4, job_id: "job-000002", branch_id: "collect", sample_sequence: 12},
  {schema_version: 2, event: "job_end", event_sequence: 5, job_id: "job-000002", branch_id: "collect", outcome: "selected"},
  {schema_version: 2, event: "action_result", event_sequence: 6, job_id: "job-000002", branch_id: "collect", execution_id: "exec-000001", effective_action: "collect", boundary: {status: "success", action: "collect_item"}},
  {schema_version: 2, event: "action_result", event_sequence: 7, job_id: "job-000001", branch_id: "plant", execution_id: "exec-000002", effective_action: "plant", boundary: {status: "success", action: "place_plant"}},
  {schema_version: 2, event: "runtime_stop", event_sequence: 8, stop_reason: "max_cycles"}]};
vm.runInContext("renderTrace(" + JSON.stringify(payload) + ")", context);
const text = elements["jev-timeline"].textContent;
const badge = elements["trace-event-count"].textContent;
vm.runInContext("renderTrace(" + JSON.stringify({status: "empty", events: []}) + ")", context);
const emptyText = elements["jev-timeline"].textContent;
vm.runInContext("renderTrace(" + JSON.stringify({status: "ok", events: [{schema_version: 1, cycle: 1, sample_sequence: 9, outcome: "wait", state: {}}]}) + ")", context);
const legacyText = elements["jev-timeline"].textContent;
console.log(JSON.stringify({text, badge, emptyText, legacyText, tags}));'''
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, encoding="utf-8")
        rendered = json.loads(result.stdout)
        self.assertIn("决策完成顺序：1.种植分支(job-000001) → 2.收集分支(job-000002)", rendered["text"])
        self.assertIn("实际执行顺序：1.收集分支(exec-000001) → 2.种植分支(exec-000002)", rendered["text"])
        self.assertIn("任务 job-000001 · 种植分支", rendered["text"])
        self.assertIn("决策完成顺序 #1 · 实际执行顺序 #2", rendered["text"])
        self.assertIn("决策完成顺序 #2 · 实际执行顺序 #1", rendered["text"])
        self.assertIn("2 请求结果 · 延迟 210 ms · 目标规则 argmax", rendered["text"])
        self.assertIn("需要响应的行 2 · 选中 peashooter@r2c4 → peashooter@r1c0 · 约束下重排 · 重排前候选 peashooter@r2c4", rendered["text"])
        self.assertIn("动作结果 · 目标 收集 · 边界 success 收集", rendered["text"])
        self.assertIn("运行停止 · 原因 max cycles", rendered["text"])
        self.assertEqual(rendered["badge"], "8 个事件")
        self.assertIn("第一个决策周期完成后", rendered["emptyText"])
        self.assertIn("周期 1", rendered["legacyText"])
        self.assertIn("Router 未调用", rendered["legacyText"])
        self.assertTrue(set(rendered["tags"]).issubset({"article", "div", "h3", "time", "p"}))

    def test_homepage_reduction_has_one_snapshot_and_secondary_observation_views(self):
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/app.js") as response:
            script = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        self.assertIn('data-state-view="structured"', page)
        self.assertIn('data-state-view="json"', page)
        self.assertIn('id="run-state-value"', page)
        self.assertIn('data-observation-tab="coverage"', page)
        self.assertNotIn("FIELD COVERAGE", page)
        self.assertNotIn("plants/", page)
        self.assertIn('fetch("/api/state"', script)
        self.assertIn("JSON.stringify(state, null, 2)", script)
        self.assertIn('href="/state"', page)
        self.assertIn('id="copy-raw-json"', page)
        self.assertIn('id="raw-copy-status"', page)
        self.assertIn('clipboard.writeText(text)', script)
        self.assertIn('byId("copy-raw-json").addEventListener("click", copyRawStateJson)', script)
        self.assertIn('byId("copy-raw-json").disabled = false;', script)
        self.assertIn(".copy-button:disabled", stylesheet)
        self.assertIn('.dashboard-grid[hidden], .raw-panel[hidden] { display: none; }', stylesheet)

    def test_card_labels_follow_state_cost_cooldown_and_usable_values(self):
        script = r'''const { cardDisplayModel, cardGroupStatus } = require("./dashboard/static/app.js");
const available = {"cards.cost": "available", "cards.cooldown_ready": "available", "cards.usable": "available"};
const verified = cardDisplayModel({cost: 100, cooldown_ready: true, usable: true}, available);
const cooling = cardDisplayModel({cost: 50, cooldown_ready: false, usable: false}, available);
const provisional = cardDisplayModel({cost: 350, cooldown_ready: false, usable: null}, {
  "cards.cost": "provisional", "cards.cooldown_ready": "available", "cards.usable": "unavailable"
});
console.log(JSON.stringify({verified, cooling, provisional, group: cardGroupStatus(available), partial: cardGroupStatus({
  "cards.cost": "available", "cards.cooldown_ready": "unavailable", "cards.usable": "unavailable"
})}));'''
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, encoding="utf-8")
        labels = json.loads(result.stdout)
        self.assertEqual(labels["verified"], {
            "costText": "费用：100 阳光",
            "stateText": "冷却：已就绪 · 卡牌可选：是",
        })
        self.assertEqual(labels["cooling"]["stateText"], "冷却：冷却中 · 卡牌可选：否")
        self.assertEqual(labels["provisional"], {
            "costText": "费用（暂定）：350 阳光",
            "stateText": "冷却：冷却中 · 卡牌可选：未知",
        })
        self.assertEqual(labels["group"], "available")
        self.assertEqual(labels["partial"], "partial")

    def test_json_copy_actions_copy_visible_snapshot_and_clear_stale_state_page_data(self):
        script = r'''const fs = require("node:fs");
const vm = require("node:vm");
const createdTags = [];
function element(tagName = "div") {
  return {tagName, children: [], dataset: {}, attributes: {}, handlers: {}, disabled: false, hidden: false,
    style: {setProperty(name, value) {this[name] = value;}},
    classList: {toggle() {}},
    append(...nodes) {this.children.push(...nodes);},
    replaceChildren(...nodes) {this.children = nodes; this._text = "";},
    setAttribute(name, value) {this.attributes[name] = String(value);},
    getAttribute(name) {return this.attributes[name] ?? null;},
    addEventListener(name, fn) {this.handlers[name] = fn;},
    querySelectorAll(selector) {
      const found = [];
      const visit = (node) => {for (const child of node.children || []) {
        if (selector === "details[data-json-path]" && child.tagName === "details" && child.dataset.jsonPath !== undefined) found.push(child);
        visit(child);
      }};
      visit(this); return found;
    },
    get textContent() {return (this._text || "") + this.children.map((child) => child.textContent).join("");},
    set textContent(value) {this._text = String(value ?? ""); this.children = [];}
  };
}
function loadPage(path, writes) {
  const elements = {};
  const document = {
    getElementById(id) { return elements[id] ||= element(); },
    createElement(tagName) {createdTags.push(tagName); return element(tagName);},
    addEventListener() {}
  };
  const navigator = {clipboard: {writeText: async (text) => { writes.push(text); }}};
  const context = vm.createContext({document, navigator});
  vm.runInContext(fs.readFileSync(path, "utf8"), context);
  return {context, elements};
}
(async () => {
  const sample = {status: "ok", valid: true, decision_ready: false,
    observed_at_utc: "2026-09-25T14:00:00Z", sample_sequence: 42, sun_balance: 777,
    nested: {values: ["<script>literal</script>", 8, false, null]}, errors: []};
  const homeWrites = [];
  const home = loadPage("dashboard/static/app.js", homeWrites);
  home.context.document.getElementById("raw-json").textContent = JSON.stringify(sample, null, 2);
  await vm.runInContext("copyRawStateJson()", home.context);
  const stateWrites = [];
  const observer = loadPage("dashboard/static/state-page.js", stateWrites);
  observer.context.sample = sample;
  vm.runInContext("renderObservedState(sample)", observer.context);
  await vm.runInContext("copyObservedStateJson()", observer.context);
  const stateCopyStatus = observer.elements["state-copy-status"].textContent;
  const safeText = observer.elements["state-json"].textContent.includes("<script>literal</script>");
  const onlySafeTags = createdTags.every((tag) => ["div", "details", "summary", "span"].includes(tag));
  observer.context.invalid = {...sample, status: "error", valid: false,
    errors: [{scope: "test", message: "sample failed"}]};
  vm.runInContext("renderObservedState(invalid)", observer.context);
  await vm.runInContext("copyObservedStateJson()", observer.context);
  console.log(JSON.stringify({homeCopied: homeWrites[0], homeStatus: home.elements["raw-copy-status"].textContent,
    stateCopied: stateWrites[0], stateStatus: stateCopyStatus,
    statusAfterError: observer.elements["state-copy-status"].textContent,
    disabledAfterError: observer.elements["state-copy-button"].disabled,
    staleTextCleared: observer.elements["state-json"].textContent.includes("旧样本已清除"),
    safeText, onlySafeTags,
    stateCopyCount: stateWrites.length}));
})();'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        copied = json.loads(result.stdout)
        expected = {
            "status": "ok", "valid": True, "decision_ready": False,
            "observed_at_utc": "2026-09-25T14:00:00Z", "sample_sequence": 42,
            "sun_balance": 777, "nested": {"values": ["<script>literal</script>", 8, False, None]}, "errors": [],
        }
        self.assertEqual(json.loads(copied["homeCopied"]), expected)
        self.assertEqual(json.loads(copied["stateCopied"]), expected)
        self.assertEqual(copied["homeStatus"], "已复制")
        self.assertEqual(copied["stateStatus"], "已复制当前快照")
        self.assertEqual(copied["statusAfterError"], "")
        self.assertTrue(copied["disabledAfterError"])
        self.assertTrue(copied["staleTextCleared"])
        self.assertTrue(copied["safeText"])
        self.assertTrue(copied["onlySafeTags"])
        self.assertEqual(copied["stateCopyCount"], 1)

    def test_state_page_profile_selection_drives_request_label_and_copy_payload(self):
        script = r'''const fs = require("node:fs");
const vm = require("node:vm");
const createdTags = [];
function element(tagName = "div") {
  return {tagName, children: [], dataset: {}, attributes: {}, handlers: {}, disabled: false, hidden: false,
    style: {setProperty(name, value) {this[name] = value;}},
    open: false, classList: {toggle() {}},
    append(...nodes) {this.children.push(...nodes);},
    replaceChildren(...nodes) {this.children = nodes; this._text = "";},
    setAttribute(name, value) {this.attributes[name] = String(value);},
    getAttribute(name) {return this.attributes[name] ?? null;},
    addEventListener(name, fn) {this.handlers[name] = fn;},
    querySelectorAll(selector) {
      const found = [];
      const visit = (node) => {for (const child of node.children || []) {
        if (selector === "details[data-json-path]" && child.tagName === "details" && child.dataset.jsonPath !== undefined) found.push(child);
        visit(child);
      }};
      visit(this); return found;
    },
    get textContent() {return (this._text || "") + this.children.map((child) => child.textContent).join("");},
    set textContent(value) {this._text = String(value ?? ""); this.children = [];}
  };
}
const elements = {};
let ready;
let tick;
let fail = false;
const writes = [];
const buttons = ["jev", "all"].map((profile) => {const button = element("button"); button.dataset.stateProfile = profile; return button;});
const document = {getElementById(id) {return elements[id] ||= element();},
  createElement(tagName) {createdTags.push(tagName); return element(tagName);},
  addEventListener(name, fn) {if (name === "DOMContentLoaded") ready = fn;},
  querySelectorAll() {return buttons;}};
const payload = (profile, sequence = 1) => ({status: "ok", valid: true, decision_ready: false,
  profile, observed_at_utc: "now", sample_sequence: sequence, nested: {values: [{n: 1}, true, null]},
  zombies: [{distance_to_house_px: 10, distance_to_house_cells: 0}],
  ...(profile === "all" ? {availability: {sun_balance: "provisional"}} : {})});
const context = vm.createContext({document, window: {setInterval(fn) {tick = fn;}}, navigator: {clipboard: {writeText: async (text) => writes.push(JSON.parse(text))}},
  fetch: async (url) => fail ? ({ok: false, status: 503}) : ({ok: true, json: async () => payload(url.includes("jev-state") ? "jev" : "all", 1)})});
vm.runInContext(fs.readFileSync("dashboard/static/state-page.js", "utf8"), context);
(async () => {
  ready(); await new Promise((resolve) => setTimeout(resolve, 5));
  const defaultLabel = elements["state-profile-label"].textContent;
  const jevHasAvailability = elements["state-json"].textContent.includes("availability");
  const nestedPath = JSON.stringify([["key", "nested"]]);
  const jevNested = () => elements["state-json"].querySelectorAll("details[data-json-path]").find((node) => node.dataset.jsonPath === nestedPath);
  jevNested().open = true;
  await tick(); await new Promise((resolve) => setTimeout(resolve, 5));
  const expandedAfterPoll = jevNested().open;
  const zombiePath = JSON.stringify([["key", "zombies"], ["index", 0]]);
  const zombieDetails = elements["state-json"].querySelectorAll("details[data-json-path]").find((node) => node.dataset.jsonPath === zombiePath);
  const distancesAligned = zombieDetails.children[1].style["--json-key-width"] === `${JSON.stringify("distance_to_house_cells").length}ch`;
  buttons[1].handlers.click(); await new Promise((resolve) => setTimeout(resolve, 5));
  const allHasAvailability = elements["state-json"].textContent.includes("availability");
  await vm.runInContext("copyObservedStateJson()", context);
  const allLabel = elements["state-profile-label"].textContent;
  fail = true; buttons[0].handlers.click(); await new Promise((resolve) => setTimeout(resolve, 5));
  fail = false; buttons[0].handlers.click(); await new Promise((resolve) => setTimeout(resolve, 5));
  const expandedWhenReturn = jevNested().open;
  fail = true; await tick(); await new Promise((resolve) => setTimeout(resolve, 5));
  console.log(JSON.stringify({defaultLabel, allLabel, copied: writes[0].profile, failedText: elements["state-json"].textContent,
    disabled: elements["state-copy-button"].disabled, failureLabel: elements["state-profile-label"].textContent,
    jevHasAvailability, allHasAvailability, expandedAfterPoll, expandedWhenReturn,
    distancesAligned,
    onlySafeTags: createdTags.every((tag) => ["div", "details", "summary", "span"].includes(tag))}));
})();'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["defaultLabel"], "当前：JEV State")
        self.assertEqual(observed["allLabel"], "当前：All State")
        self.assertEqual(observed["copied"], "all")
        self.assertIn("旧样本已清除", observed["failedText"])
        self.assertTrue(observed["disabled"])
        self.assertEqual(observed["failureLabel"], "当前：JEV State")
        self.assertFalse(observed["jevHasAvailability"])
        self.assertTrue(observed["allHasAvailability"])
        self.assertTrue(observed["expandedAfterPoll"])
        self.assertTrue(observed["expandedWhenReturn"])
        self.assertTrue(observed["distancesAligned"])
        self.assertTrue(observed["onlySafeTags"])

    def test_zombie_grid_markers_snap_to_columns_and_reject_unavailable_values(self):
        script = r'''const { zombieGridPosition } = require("./dashboard/static/app.js");
const available = {"zombies.distance_to_house_cells": "available"};
const at = (cells, row = 3, status = available) => zombieGridPosition({row, distance_to_house_cells: cells}, status);
const actual = [at(0), at(4), at(8)];
const invalid = [
  zombieGridPosition({row: 3, distance_to_house_cells: 4}, {"zombies.distance_to_house_cells": "unavailable"}),
  zombieGridPosition({row: 3}, available),
  at(-1), at(9), at(NaN), at("4"), at(4, -1), at(4, 5), at(4, 1.5)
];
console.log(JSON.stringify({actual, invalid}));'''
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        mapped = json.loads(result.stdout)
        self.assertAlmostEqual(mapped["actual"][0]["left"], (0.5 / 9) * 100)
        self.assertAlmostEqual(mapped["actual"][1]["left"], 50)
        self.assertAlmostEqual(mapped["actual"][2]["left"], (8.5 / 9) * 100)
        self.assertTrue(all(position["top"] == 70 for position in mapped["actual"]))
        self.assertEqual([position["gridIndex"] for position in mapped["actual"]], [0, 4, 8])
        self.assertEqual(mapped["invalid"], [None] * 9)
        with urlopen(f"http://127.0.0.1:{self.port}/static/app.js") as response:
            source = response.read().decode("utf-8")
        self.assertIn('const laneZombies = zombies.filter((zombie) => zombie.row === row)', source)
        self.assertIn('article.append(makeElement("p", "lane-empty", "当前没有"))', source)

    def test_unavailable_grid_distance_does_not_guess_from_raw_x(self):
        script = r'''const { zombiePositionsForState } = require("./dashboard/static/app.js");
const state = {
  status: "ok", valid: true,
  game: {scene: "playing", mode: "survival_normal_stage_1", background: "day"},
  availability: {
    zombies: "provisional", "zombies.distance_to_house_cells": "unavailable"
  },
  zombies: [
    {type_code: 0, row: 1, x: 650, distance_to_house_cells: null},
    {type_code: 0, row: 0, x: 570, distance_to_house_cells: null},
    {type_code: 0, row: 0, x: 550.5028686523438, distance_to_house_cells: null}
  ]
};
const unavailable = zombiePositionsForState(state);
const changed = structuredClone(state);
changed.zombies[2].x = 551;
const stillUnavailable = zombiePositionsForState(changed);
const partialState = structuredClone(state);
partialState.status = "error";
partialState.valid = false;
partialState.availability.sun_balance = "error";
const partialPositions = zombiePositionsForState(partialState);
const calibrated = structuredClone(partialState);
calibrated.availability["zombies.distance_to_house_cells"] = "available";
calibrated.zombies.forEach((zombie, i) => zombie.distance_to_house_cells = [8, 7, 6][i]);
const calibratedPositions = zombiePositionsForState(calibrated);
console.log(JSON.stringify({unavailable, stillUnavailable, partialPositions, calibratedPositions}));'''
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        positions = json.loads(result.stdout)
        self.assertEqual(positions["unavailable"], [None, None, None])
        self.assertEqual(positions["stillUnavailable"], [None, None, None])
        self.assertEqual(positions["partialPositions"], [None, None, None])
        self.assertEqual(positions["calibratedPositions"], [
            {"left": (8.5 / 9) * 100, "top": 30, "gridIndex": 8},
            {"left": (7.5 / 9) * 100, "top": 10, "gridIndex": 7},
            {"left": (6.5 / 9) * 100, "top": 10, "gridIndex": 6},
        ])

    def test_state_endpoint_reflects_successive_shared_samples_and_sampler_error(self):
        self.sample["sample_sequence"] = 1
        self.poller.sample_once()
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as response:
            first = json.loads(response.read())
        self.sample["sample_sequence"] = 2
        self.sample["sun_balance"] = 4444
        self.poller.sample_once()
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as response:
            second = json.loads(response.read())
        self.assertEqual(first["sample_sequence"], 1)
        self.assertEqual(second["sample_sequence"], 2)
        self.assertEqual(second["sun_balance"], 4444)
        self.poller.sampler = lambda: (_ for _ in ()).throw(RuntimeError("sample failed"))
        failed = self.poller.sample_once()
        self.assertEqual(failed["status"], "error")
        self.assertIn("sample failed", failed["errors"][0]["message"])

    def test_non_loopback_binding_is_rejected(self):
        with self.assertRaises(ValueError):
            create_dashboard_server(self.poller, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
