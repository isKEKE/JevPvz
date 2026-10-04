import json
import re
import subprocess
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from dashboard.server import OptionMatrixReader, StatePoller, TraceFileReader, create_dashboard_server
from dashboard.runtime_control import RuntimeController
from jev.trace import EVENT_ACTION_RESULT, EVENT_JOB_END, EVENT_REQUEST_RESULT, RUNTIME_EVENT_NAMES, TraceRecorder


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


def trace_lines(events):
    """The exact JSON Lines text a Trace file holds."""
    return "".join(json.dumps(event) + "\n" for event in events)


def write_trace(path, events):
    path.write_text(trace_lines(events), encoding="utf-8")


def append_trace(path, events):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(trace_lines(events))


def request_result_event(sequence, *, run_id, job_id, branch_id, typed_answers):
    """One schema-2 request_result carrying the typed answers under test."""
    return runtime_event(sequence, EVENT_REQUEST_RESULT, run_id=run_id, job_id=job_id, branch_id=branch_id,
                         request_id=f"{job_id}-request-1", typed_answers=typed_answers)


def action_result_event(sequence, *, run_id, job_id, branch_id, target, status="success"):
    """One schema-2 action_result with an explicit Boundary status and target."""
    return runtime_event(sequence, EVENT_ACTION_RESULT, run_id=run_id, job_id=job_id, branch_id=branch_id,
                         execution_id=f"exec-{sequence:06d}",
                         boundary={"status": status, "action": target.get("action")}, target=target)


def options_by_question(payload):
    return {group["question_id"]: group for group in payload["questions"]}


def option_ids(group):
    return [option["option_id"] for option in group["options"]]


def executed_options(group):
    return [option["option_id"] for option in group["options"] if option["executed"]]


DOM_HARNESS = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const htmlWrites = [];
const intervals = [];
const created = [];
function element(tagName, ownerRegistry) {
  const registry = ownerRegistry || {};
  const node = {
    tagName: tagName || "div", className: "", id: "", title: "", type: "", disabled: false, hidden: false,
    children: [], dataset: {}, attributes: {}, handlers: {}, parentNode: null,
    style: {setProperty(name, value) {this[name] = value;}},
    append(...items) {for (const item of items) {item.parentNode = node; node.children.push(item);}},
    replaceChildren(...items) {node.children = []; node.append(...items);},
    replaceWith(replacement) {
      replacement.parentNode = node.parentNode;
      if (node.parentNode) {
        const index = node.parentNode.children.indexOf(node);
        if (index >= 0) node.parentNode.children[index] = replacement;
      }
      if (node.id) {registry[node.id] = replacement; replacement.id = node.id;}
    },
    setAttribute(name, value) {node.attributes[name] = String(value);},
    getAttribute(name) {return name in node.attributes ? node.attributes[name] : null;},
    addEventListener(name, handler) {node.handlers[name] = handler;},
    querySelectorAll(selector) {
      const found = [];
      const visit = (item) => {for (const child of item.children) {if (matches(child, selector)) found.push(child); visit(child);}};
      visit(node);
      return found;
    },
    classList: {
      add(...names) {names.forEach((name) => {if (!node.className.split(" ").includes(name)) node.className = (node.className + " " + name).trim();});},
      contains(name) {return node.className.split(" ").includes(name);},
      toggle() {},
    },
    set textContent(value) {node._text = String(value ?? ""); node.children = [];},
    get textContent() {return (node._text || "") + node.children.map((child) => child.textContent).join("");},
  };
  Object.defineProperty(node, "innerHTML", {set(value) {htmlWrites.push(String(value));}, get() {return "";}});
  created.push(node);
  return node;
}
function matches(node, selector) {
  if (selector.startsWith(".")) return node.className.split(" ").includes(selector.slice(1));
  return node.tagName === selector;
}
const window = {setInterval(fn, ms) {intervals.push({fn, ms}); return intervals.length;}};
function createPage(scriptPath, extra) {
  const registry = {};
  const handlers = {};
  const document = {
    activeElement: null,
    getElementById(id) {if (!registry[id]) {registry[id] = element("div", registry); registry[id].id = id;} return registry[id];},
    createElement(tagName) {return element(tagName, registry);},
    addEventListener(name, handler) {handlers[name] = handler;},
    querySelectorAll() {return [];},
  };
  const context = vm.createContext(Object.assign({document, window, console}, extra || {}));
  vm.runInContext(fs.readFileSync(scriptPath, "utf8"), context);
  return {context, document, registry, handlers};
}
function flatten(node) {return [node, ...node.children.flatMap(flatten)];}
function nodesOf(page, id) {return flatten(page.document.getElementById(id));}
'''


def run_node(script):
    """Run one Node DOM probe and return the JSON value it prints."""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def viewmodel_probe(body, catalog):
    """Run one adapter probe against the real catalog and return the JSON it prints."""
    script = (
        'require("./dashboard/static/viewmodel.js");\n'
        f"JEVViewModel.installCatalog({json.dumps(catalog, ensure_ascii=False)});\n"
        + body
    )
    return run_node(script)


def css_declarations(stylesheet, selector):
    """Every declaration body of one selector, including its media-query override."""
    bodies = []
    for selectors, body in re.findall(r"(?m)^\s*([^{}\n]+?)\s*\{([^{}]*)\}", stylesheet):
        if selector in [part.strip() for part in selectors.split(",")]:
            bodies.append(body)
    return " ".join(bodies)


class DashboardHttpTests(unittest.TestCase):
    def test_runtime_routes_require_same_origin_control_headers(self):
        base = f"http://127.0.0.1:{self.port}"
        with urlopen(base + "/api/jev-runtime") as response:
            self.assertEqual(json.load(response)["state"], "disabled")
        forged = Request(base + "/api/jev-runtime/start", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(forged)
        self.assertEqual(raised.exception.code, 403)
        valid = Request(base + "/api/jev-runtime/start", data=b"{}", method="POST", headers={
            "Origin": base, "Content-Type": "application/json", "X-JEV-Control": "1",
        })
        with self.assertRaises(HTTPError) as raised:
            urlopen(valid)
        self.assertEqual(raised.exception.code, 409)

    def test_runtime_http_start_stop_routes_call_controller(self):
        class Controller:
            def __init__(self):
                self.running = False

            def status(self):
                return {"state": "running" if self.running else "idle", "can_start": not self.running,
                        "can_stop": self.running, "game_ready": True}

            def start(self):
                self.running = True
                return 202, self.status()

            def stop(self):
                self.running = False
                return 200, self.status()

            def close(self):
                pass

        controller = Controller()
        server = create_dashboard_server(self.poller, port=0, runtime_controller=controller)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            for action, expected_code, expected_state in (("start", 202, "running"), ("stop", 200, "idle")):
                request = Request(base + f"/api/jev-runtime/{action}", data=b"{}", method="POST", headers={
                    "Origin": base, "Content-Type": "application/json", "X-JEV-Control": "1",
                })
                with urlopen(request) as response:
                    self.assertEqual(response.status, expected_code)
                    self.assertEqual(json.load(response)["state"], expected_state)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

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
        with urlopen(f"http://127.0.0.1:{self.port}/static/viewmodel.js") as response:
            viewmodel = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/recording.js") as response:
            recording = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        self.assertIn("世界模型", page)
        self.assertIn("/static/style.css", page)
        self.assertIn("/static/viewmodel.js", page)
        self.assertIn("/static/recording.js", page)
        # 名称只有一个真源：后端 catalog。适配层不得再抄一份中英文对照表。
        self.assertNotIn("豌豆射手", viewmodel)
        self.assertNotIn("普通僵尸", viewmodel)
        self.assertIn('localizedType("plant"', viewmodel)
        self.assertIn('localizedType("zombie"', viewmodel)
        self.assertIn('localizedType("item"', viewmodel)
        self.assertIn("/api/catalog", recording)
        # 僵尸几何只来自后端字段，不得由 x 像素反推。
        self.assertNotIn("projectZombieX", viewmodel + recording)
        self.assertNotIn("LAWN_GEOMETRY", viewmodel + recording)
        for source in (viewmodel, recording):
            self.assertNotIn('fetch("http', source)
            self.assertNotIn("innerHTML", source)
        self.assertIn("--observe", stylesheet)
        self.assertIn("--zombie", stylesheet)

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
        self.assertIn('href="/"', page)
        # 录制页刻意不放入口导航：它是录屏场景，不是后台面板。
        self.assertNotIn("<nav", home)
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
                self.assertIn('href="/jev"', state_page)
                self.assertIn('fetch("/api/jev-options"', script)
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

    def test_unconfigured_option_matrix_route_reports_itself(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/jev-options") as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
        self.assertEqual(payload, {"status": "unconfigured", "schema_version": None, "run_id": None,
                               "questions": [], "decision": None, "execution": None})

    def test_option_matrix_route_serves_only_the_configured_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "run.jsonl"
            write_trace(trace_path, [request_result_event(
                1, run_id="run-http", job_id="job-000001", branch_id="collect",
                typed_answers={"should_collect_now": {"noul": 0.8}},
            )])
            poller = StatePoller(50, sampler=lambda: self.sample)
            poller.sample_once()
            server = create_dashboard_server(poller, port=0, jev_trace_file=trace_path)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/jev-options") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertIn("no-store", response.headers["Cache-Control"])
                # No request may name another file, not even through a query string.
                with self.assertRaises(HTTPError) as raised:
                    urlopen(f"http://127.0.0.1:{port}/api/jev-options?path={trace_path}")
                self.assertEqual(raised.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["run_id"], "run-http")
        self.assertEqual(option_ids(options_by_question(payload)["should_collect_now"]), ["true", "false"])

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

    def test_jev_option_matrix_maps_every_summary_option_to_one_dot(self):
        script = DOM_HARNESS + r'''
(async () => {
  const payload = {status: "ok", schema_version: 2, run_id: "run-7f3a", questions: [
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000001", options: [
      {option_id: "potato_mine@r2c3", probability: 0.36, executed: true},
      {option_id: "peashooter@r1c0", probability: 0.31, executed: false},
      {option_id: "none_of_the_above", probability: 0.33, executed: false},
      {option_id: "<img src=x onerror=alert(1)>@r2c3", probability: 0.0001, executed: false}]},
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "true", probability: 0.93, executed: true},
      {option_id: "false", probability: 0.06999999999999995, executed: false}]},
    {question_id: "construction_intent", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "keep", probability: 0.7, executed: false},
      {option_id: "replace", probability: 0.2, executed: false},
      {option_id: "cancel", probability: 0.1, executed: false}]},
    {question_id: "plant_target_lane", branch_id: "plant", job_id: "job-000001", options: [
      {option_id: "lane_0", probability: 0.5, executed: false},
      {option_id: "none_of_the_above", probability: 0.5, executed: false}]}]};
  const expected = [];
  for (const group of payload.questions) {
    for (const option of group.options) expected.push([group.question_id, option.option_id, option.executed === true]);
  }
  const calls = [];
  const page = createPage("dashboard/static/jev-page.js", {fetch: async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => payload};
  }});
  await vm.runInContext("fetchOptionMatrix()", page.context);
  const nodes = nodesOf(page, "jev-timeline");
  console.log(JSON.stringify({
    expected, calls, htmlWrites,
    tags: [...new Set(created.map((node) => node.tagName))],
    badge: page.document.getElementById("trace-event-count").textContent,
    badgeClass: page.document.getElementById("trace-event-count").className,
    statusTitle: page.document.getElementById("trace-status-title").textContent,
    intents: nodes.filter((node) => node.className.split(" ").includes("jev-intent-node")).map((node) => [node.dataset.intent, node.dataset.active, node.getAttribute("aria-label"), node.title]),
    links: nodes.filter((node) => node.className.split(" ").includes("jev-net-link")).map((node) => node.className),
    intentCount: nodes.filter((node) => node.className.split(" ").includes("jev-intent-node")).length,
    groups: nodes.filter((node) => node.getAttribute("role") === "group").map((node) => node.getAttribute("aria-label")),
    dots: nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot")).map((dot) => [
      dot.dataset.questionId, dot.dataset.optionId, dot.dataset.executed === "true", dot.dataset.optionKey,
      dot.className, dot.tagName, dot.getAttribute("aria-label"), dot.title, typeof dot.handlers.click]),
    mesh: nodes.filter((node) => node.className === "jev-mesh").length,
    text: page.document.getElementById("jev-timeline").textContent,
  }));
})();'''
        rendered = run_node(script)
        self.assertEqual(rendered["calls"][0]["url"], "/api/jev-options")
        self.assertEqual(rendered["calls"][0]["options"], {"cache": "no-store"})
        self.assertEqual(len(rendered["calls"]), 1)
        self.assertEqual(rendered["htmlWrites"], [])
        self.assertTrue(set(rendered["tags"]).issubset({"div", "span", "button"}))
        self.assertEqual(rendered["statusTitle"], "本局候选")
        self.assertEqual(rendered["badge"], "4 类问题 / 11 个候选")
        self.assertEqual(rendered["badgeClass"], "state-badge available")
        # 左侧意图层：三个节点，本周期进入的分支点亮。
        self.assertEqual([[item[0], item[1]] for item in rendered["intents"]],
                         [["collect", "true"], ["plant", "true"], ["cancel", "true"]])
        self.assertEqual(rendered["intents"][0][2], "收集：本周期已进入该分支")
        self.assertEqual(rendered["intentCount"], 3)
        # 没有单独的连线列：网格本身提供连线，避免中间留下大片空白。
        self.assertEqual(rendered["text"], "")
        self.assertEqual(rendered["groups"], ["本周期意图", "本局全部候选 option 点阵"])
        self.assertEqual(rendered["mesh"], 1)
        # 密网不再折叠棋盘，每个 option 都是一个点，含无棋盘的 none_of_the_above。
        self.assertEqual([dot[0] for dot in rendered["dots"]],
                         ["plant_target", "plant_target", "plant_target", "plant_target",
                          "should_collect_now", "should_collect_now",
                          "construction_intent", "construction_intent", "construction_intent",
                          "plant_target_lane", "plant_target_lane"])
        self.assertEqual([dot[1] for dot in rendered["dots"]],
                         ["potato_mine@r2c3", "peashooter@r1c0", "none_of_the_above",
                          "<img src=x onerror=alert(1)>@r2c3", "true", "false",
                          "keep", "replace", "cancel", "lane_0", "none_of_the_above"])
        self.assertEqual(rendered["dots"][0][4], "jev-decision-dot jev-dot-plant executed")
        self.assertEqual(rendered["dots"][0][6],
                         "种植 · 种植分支 · 目标植物 · potato_mine · 第 3 行第 4 列 · 模型概率 36% · 已证实执行")
        self.assertEqual(rendered["dots"][4][6],
                         "收集 · 收集分支 · 是否立即收集 · true · 模型概率 93% · 已证实执行")
        self.assertEqual(rendered["dots"][6][4], "jev-decision-dot jev-dot-manage pending")
        self.assertIn("<img src=x onerror=alert(1)>@r2c3", rendered["dots"][3][6])
        self.assertEqual([dot[2] for dot in rendered["dots"]],
                         [True, False, False, False, True, False, False, False, False, False, False])
        self.assertEqual([dot[8] for dot in rendered["dots"]], ["undefined"] * 11)

    def test_jev_option_matrix_keeps_layered_and_hundred_plus_options_complete(self):
        script = DOM_HARNESS + r'''
(async () => {
  const plantOptions = [];
  // Every board cell at least once, plus a duplicate cell and the discard option.
  for (let row = 0; row < 5; row += 1) {
    for (let column = 0; column < 9; column += 1) {
      plantOptions.push({option_id: "peashooter@r" + row + "c" + column, probability: 0.01, executed: false});
    }
  }
  plantOptions.push({option_id: "peashooter@r0c0", probability: 0.02, executed: false});
  plantOptions.push({option_id: "none_of_the_above", probability: 0.02, executed: false});
  const laneOptions = [];
  for (let row = 0; row < 5; row += 1) laneOptions.push({option_id: "lane_" + row, probability: 0.2, executed: false});
  laneOptions.push({option_id: "none_of_the_above", probability: 0.1, executed: false});
  const rowOptions = [];
  for (let column = 0; column < 9; column += 1) {
    rowOptions.push({option_id: "wall_nut@r2c" + column, probability: 0.05, executed: false});
  }
  // Off-board column must not fabricate a 10th column.
  rowOptions.push({option_id: "wall_nut@r9c20", probability: 0.01, executed: false});
  rowOptions.push({option_id: "none_of_the_above", probability: 0.24, executed: false});
  const payload = {status: "ok", schema_version: 2, run_id: "run-long", questions: [
    {question_id: "plant_target_lane", branch_id: "plant", job_id: "job-000001", options: laneOptions},
    {question_id: "plant_target_lane_2", branch_id: "plant", job_id: "job-000002", options: [
      {option_id: "wall_nut@r2c1", probability: 0.5, executed: false},
      {option_id: "sunflower@r2c2", probability: 0.3, executed: false},
      {option_id: "none_of_the_above", probability: 0.2, executed: false}]},
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000003", options: plantOptions},
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000004", options: [
      {option_id: "true", probability: 0.4, executed: false},
      {option_id: "false", probability: 0.6, executed: false}]},
    {question_id: "plant_target_lane_4", branch_id: "plant", job_id: "job-000005", options: rowOptions}]};
  const page = createPage("dashboard/static/jev-page.js", {});
  vm.runInContext("renderOptionMatrix(" + JSON.stringify(payload) + ")", page.context);
  const nodes = nodesOf(page, "jev-timeline");
  const dots = nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot"));
  const expected = [];
  for (const group of payload.questions) {
    for (const option of group.options) expected.push(group.question_id + "|" + option.option_id);
  }
  console.log(JSON.stringify({
    expected,
    rendered: dots.map((dot) => dot.dataset.questionId + "|" + dot.dataset.optionId),
    dotCount: dots.length,
    badge: page.document.getElementById("trace-event-count").textContent,
    text: page.document.getElementById("jev-timeline").textContent,
  }));
})();'''
        rendered = run_node(script)
        # 密网不折叠棋盘：每个 option 恰好一个点，含无棋盘的 none_of_the_above 与 lane_N。
        self.assertEqual(rendered["dotCount"], 69)
        self.assertEqual(sorted(rendered["rendered"]), sorted(rendered["expected"]))
        self.assertEqual(rendered["badge"], "5 类问题 / 69 个候选")
        self.assertEqual(rendered["text"], "")

    def test_jev_option_matrix_lights_only_confirmed_same_job_executions(self):
        script = DOM_HARNESS + r'''
(async () => {
  const payload = {status: "ok", schema_version: 2, run_id: "run-light", questions: [
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "true", probability: 0.01, executed: true},
      {option_id: "false", probability: 0.99, executed: false}]},
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000003", options: [
      {option_id: "wall_nut@r0c1", probability: 0.999, executed: false},
      {option_id: "none_of_the_above", probability: 0.001, executed: false}]},
    {question_id: "construction_intent", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "keep", probability: 0.99, executed: false},
      {option_id: "replace", probability: 0.01, executed: false}]},
    {question_id: "next_construction_type", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "sunflower", probability: 0.99, executed: false}]},
    {question_id: "collect_target", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "item_0", probability: 0.99, executed: false},
      {option_id: "none_of_the_above", probability: 0.01, executed: false}]}]};
  const page = createPage("dashboard/static/jev-page.js", {});
  vm.runInContext("renderOptionMatrix(" + JSON.stringify(payload) + ")", page.context);
  const nodes = nodesOf(page, "jev-timeline");
  const dots = nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot"));
  console.log(JSON.stringify({
    total: dots.length,
    lit: dots.filter((dot) => dot.className.split(" ").includes("executed")).map((dot) => [dot.dataset.questionId, dot.dataset.optionId, dot.dataset.executed]),
    dark: dots.filter((dot) => !dot.className.split(" ").includes("executed")).map((dot) => [dot.className, dot.dataset.executed, dot.getAttribute("aria-label")]),
    source: fs.readFileSync("dashboard/static/jev-page.js", "utf8"),
  }));
})();'''
        rendered = run_node(script)
        self.assertEqual(rendered["total"], 9)
        self.assertEqual(rendered["lit"], [["should_collect_now", "true", "true"]])
        self.assertEqual(len(rendered["dark"]), 8)
        self.assertTrue(all("pending" in item[0] and "executed" not in item[0] for item in rendered["dark"]))
        self.assertTrue(all(item[1] == "false" for item in rendered["dark"]))
        self.assertTrue(all("未证实执行" in item[2] for item in rendered["dark"]))
        self.assertTrue(all("已证实执行" not in item[2] for item in rendered["dark"]))
        self.assertIn("option?.executed === true", rendered["source"])

    def test_jev_option_matrix_resets_on_a_new_run_and_restores_after_refresh(self):
        script = DOM_HARNESS + r'''
(async () => {
  const runA = {status: "ok", schema_version: 2, run_id: "run-a", questions: [
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000001", options: [
      {option_id: "potato_mine@r2c3", probability: 0.6, executed: true},
      {option_id: "none_of_the_above", probability: 0.4, executed: false}]}]};
  const runA2 = {status: "ok", schema_version: 2, run_id: "run-a", questions: [
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000002", options: [
      {option_id: "peashooter@r1c0", probability: 0.5, executed: false},
      {option_id: "none_of_the_above", probability: 0.5, executed: false}]}]};
  const runB = {status: "ok", schema_version: 2, run_id: "run-b", questions: [
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000009", options: [
      {option_id: "true", probability: 0.9, executed: false},
      {option_id: "false", probability: 0.1, executed: false}]}]};
  const page = createPage("dashboard/static/jev-page.js", {});
  const render = (payload) => vm.runInContext("renderOptionMatrix(" + JSON.stringify(payload) + ")", page.context);
  const read = () => {
    const nodes = nodesOf(page, "jev-timeline");
    return {
      dots: nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot")).map((dot) => [dot.dataset.questionId, dot.dataset.optionId, dot.dataset.executed]),
      lit: nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot") && node.className.split(" ").includes("executed")).map((node) => node.dataset.optionId),
      fresh: nodes.filter((node) => node.className.split(" ").includes("fresh")).length,
      text: page.document.getElementById("jev-timeline").textContent};
  };
  render(runA);
  const first = read();
  const firstChild = page.document.getElementById("jev-timeline").children[0];
  render(runA);
  const unchanged = firstChild === page.document.getElementById("jev-timeline").children[0];
  render(runA2);
  const rerequested = read();
  render(runB);
  const second = read();
  const refreshed = createPage("dashboard/static/jev-page.js", {});
  vm.runInContext("renderOptionMatrix(" + JSON.stringify(runA) + ")", refreshed.context);
  const refreshedNodes = nodesOf(refreshed, "jev-timeline");
  const afterRefresh = {
    dots: refreshedNodes.filter((node) => node.className.split(" ").includes("jev-decision-dot")).map((dot) => [dot.dataset.questionId, dot.dataset.optionId, dot.dataset.executed]),
    lit: refreshedNodes.filter((node) => node.className.split(" ").includes("jev-decision-dot") && node.className.split(" ").includes("executed")).map((node) => node.dataset.optionId)};
  console.log(JSON.stringify({first, unchanged, rerequested, second, afterRefresh}));
})();'''
        rendered = run_node(script)
        # run-a：已证实执行的 option 在密网点亮。
        self.assertEqual(rendered["first"]["dots"], [["plant_target", "potato_mine@r2c3", "true"],
                                                      ["plant_target", "none_of_the_above", "false"]])
        self.assertEqual(rendered["first"]["lit"], ["potato_mine@r2c3"])
        self.assertEqual(rendered["first"]["fresh"], 0)
        self.assertTrue(rendered["unchanged"])
        # 同 run 重新提问：旧组被替换，r2c3 不再有候选，亮点随之消失。
        self.assertEqual(rendered["rerequested"]["dots"], [["plant_target", "peashooter@r1c0", "false"],
                                                            ["plant_target", "none_of_the_above", "false"]])
        self.assertEqual(rendered["rerequested"]["lit"], [])
        self.assertEqual(rendered["rerequested"]["fresh"], 1)
        # run-b：旧 run 的点全部清空。
        self.assertEqual(rendered["second"]["lit"], [])
        self.assertEqual(rendered["second"]["dots"], [["should_collect_now", "true", "false"],
                                                       ["should_collect_now", "false", "false"]])
        self.assertNotIn("potato_mine@r2c3", rendered["second"]["text"])
        self.assertNotIn("none_of_the_above", rendered["second"]["text"])
        # 刷新页面后从摘要重建，得到与 run-a 首屏一致的亮灯。
        self.assertEqual(rendered["afterRefresh"]["lit"], ["potato_mine@r2c3"])
        self.assertEqual(rendered["afterRefresh"]["dots"], rendered["first"]["dots"])

    def test_jev_option_matrix_reports_legacy_and_empty_traces_without_dots(self):
        script = DOM_HARNESS + r'''
(async () => {
  const payloads = [
    {status: "legacy", schema_version: 1, run_id: null, questions: []},
    {status: "empty", schema_version: null, run_id: null, questions: []},
    {status: "missing", schema_version: null, run_id: null, questions: []},
    {status: "unconfigured", schema_version: null, run_id: null, questions: []},
    {status: "error", schema_version: null, run_id: null, questions: []}];
  const page = createPage("dashboard/static/jev-page.js", {});
  const read = () => {
    const nodes = nodesOf(page, "jev-timeline");
    return {dots: nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot")).length,
      title: page.document.getElementById("trace-status-title").textContent,
      badge: page.document.getElementById("trace-event-count").textContent,
      badgeClass: page.document.getElementById("trace-event-count").className,
      notice: page.document.getElementById("jev-timeline").textContent,
      noticeClass: (nodes.find((node) => node.className.split(" ").includes("jev-option-notice")) || {className: null}).className};
  };
  const cases = {};
  for (const payload of payloads) {
    vm.runInContext("renderOptionMatrix(" + JSON.stringify(payload) + ")", page.context);
    cases[payload.status] = read();
  }
  vm.runInContext("renderOptionMatrix(" + JSON.stringify({status: "ok", schema_version: 2, run_id: "run-ok", questions: [
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000001", options: [
      {option_id: "true", probability: 0.5, executed: true},
      {option_id: "false", probability: 0.5, executed: false}]}]}) + ")", page.context);
  console.log(JSON.stringify({cases, afterLegacy: read()}));
})();'''
        rendered = run_node(script)
        cases = rendered["cases"]
        self.assertEqual(sorted(cases), ["empty", "error", "legacy", "missing", "unconfigured"])
        self.assertTrue(all(case["dots"] == 0 for case in cases.values()))
        self.assertEqual(cases["legacy"]["title"], "历史 v1 记录")
        self.assertEqual(cases["legacy"]["badge"], "历史 v1 记录")
        self.assertEqual(cases["legacy"]["badgeClass"], "state-badge provisional")
        self.assertIn("v1", cases["legacy"]["notice"])
        self.assertIn("不伪造节点", cases["legacy"]["notice"])
        self.assertEqual(cases["unconfigured"]["title"], "尚未配置记录文件")
        self.assertEqual(cases["missing"]["title"], "等待记录文件")
        self.assertEqual(cases["empty"]["title"], "等待首个完整周期")
        self.assertEqual(cases["error"]["title"], "记录暂时不可读")
        for status, case in cases.items():
            self.assertIn("jev-option-notice", case["noticeClass"], status)
            self.assertTrue(case["notice"].strip(), status)
        self.assertEqual(rendered["afterLegacy"]["dots"], 2)
        self.assertEqual(rendered["afterLegacy"]["title"], "本局候选")

    def test_jev_runtime_polls_the_fixed_route_on_the_one_second_cadence(self):
        script = DOM_HARNESS + r'''
(async () => {
  const calls = [];
  const page = createPage("dashboard/static/jev-page.js", {fetch: async (url) => {
    calls.push(url);
    return {ok: true, json: async () => (url === "/api/jev-options"
      ? {status: "ok", schema_version: 2, run_id: "run-1", questions: []}
      : {state: "idle", can_start: true, can_stop: false})};
  }});
  page.handlers.DOMContentLoaded();
  await new Promise((resolve) => setTimeout(resolve, 20));
  console.log(JSON.stringify({calls, intervals: intervals.map((item) => item.ms),
    notice: page.document.getElementById("jev-timeline").textContent,
    source: fs.readFileSync("dashboard/static/jev-page.js", "utf8")}));
})();'''
        rendered = run_node(script)
        self.assertEqual(rendered["intervals"], [1000, 1000])
        self.assertEqual(rendered["calls"], ["/api/jev-runtime", "/api/jev-options"])
        self.assertTrue(all("?" not in url for url in rendered["calls"]))
        self.assertIn("还没有提出任何问题", rendered["notice"])
        self.assertNotIn("/api/jev-trace", rendered["source"])

    def test_recording_page_reserves_an_exact_game_viewport_and_the_decision_space(self):
        """录制页必须留出精确 800×600 的画面区，并把决策空间放在同一屏。"""
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        self.assertIn('id="game-viewport"', page)
        self.assertIn('data-slot="capture"', page)
        self.assertIn("800 × 600", page)
        self.assertIn('id="runtime-start"', page)
        self.assertIn('id="runtime-stop"', page)
        for element_id in ("lawn", "target", "inv-list", "stage-observe", "stage-intent",
                           "stage-option", "stage-action", "field-grid", "decision-meta"):
            self.assertIn(f'id="{element_id}"', page)
        viewport = css_declarations(stylesheet, ".game-viewport")
        self.assertIn("width: 800px", viewport)
        self.assertIn("height: 600px", viewport)
        self.assertIn("flex: 0 0 800px", viewport)
        # 主区高度是固定 token，游戏窗口 600 + 头部必须装得下。
        self.assertIn("--main-h: 700px", stylesheet)
        self.assertIn("var(--main-h)", css_declarations(stylesheet, ".rt-main"))
        # 2K 是主设计尺寸：顶栏 72px，决策轨迹吃掉剩余纵向空间。
        self.assertIn("--bar-h: 72px", stylesheet)
        # 候选场必须与草坪逐列对齐：两边声明同一种列模板，否则列会错位。
        # (30px 标签列 + 9 等分列；实测两边列 x 完全一致。)
        columns = "30px repeat(9, minmax(0, 1fr))"
        self.assertIn(columns, css_declarations(stylesheet, ".lawn"))
        self.assertIn(columns, css_declarations(stylesheet, ".rt-field-grid"))
        # 一个主控制：运行中只应看到停止，空闲时只应看到运行。
        self.assertIn("display: none", css_declarations(stylesheet, ".rt-btn[hidden]"))
        self.assertIn('id="runtime-stop" class="rt-btn rt-btn-stop" type="button" disabled hidden', page)
        # 目标块与动作块都是紧凑的：
        # 威胁清单必须内部滚动，且不能把世界模型区域顶出工作区高度。
        self.assertIn("flex-direction: column", css_declarations(stylesheet, ".rt-target"))
        self.assertIn("overflow-y: auto", css_declarations(stylesheet, ".threat-rows"))
        # 行必须是 minmax(0,1fr)：隐式 auto 行会被内容顶高。
        self.assertIn("grid-template-rows: minmax(0, 1fr)", css_declarations(stylesheet, ".rt-workspace"))
        # 滚动条要跟主题同源，不用系统默认亮条。
        self.assertIn("scrollbar-width: thin", css_declarations(stylesheet, ".rt-page *"))
        self.assertIn("var(--border-strong)", css_declarations(stylesheet, ".rt-page *::-webkit-scrollbar-thumb"))
        # 动作块是整条链的终点：动作名最大，其余收成对齐的 label/value 列表。
        self.assertIn("grid-template-columns: 92px minmax(0, 1fr)", css_declarations(stylesheet, ".action-row"))
        self.assertIn("font-size: var(--fs-hero)", css_declarations(stylesheet, ".action-name"))
        # 回归保护：草坪必须同时表达“种了什么”和“僵尸在哪”。
        # 这两层曾在重写中被整层删掉，只剩植物，导致一屏只看得见一个“聚焦”角标。
        with urlopen(f"http://127.0.0.1:{self.port}/static/recording.js") as response:
            recording = response.read().decode("utf-8")
        self.assertIn("zombiesByCell", recording)
        self.assertIn("cell-zombie-mark", recording)
        self.assertIn("cell-reticle", recording)
        self.assertIn("vm.threats.list", recording)
        self.assertIn("background: var(--zombie)", css_declarations(stylesheet, ".cell-zombie-mark"))
        self.assertIn("var(--zombie-dim)", css_declarations(stylesheet, ".cell-reticle"))
        self.assertIn("solid var(--zombie)", css_declarations(stylesheet, ".cell-reticle::before"))
        # 录制页不再挂载旧的 JEV HUD：决策轨迹取代了它。
        self.assertNotIn("/static/jev-page.js", page)
        self.assertNotIn('id="jev-timeline"', page)

    def test_jev_runtime_page_drops_the_decision_detail_orders_and_log(self):
        with urlopen(f"http://127.0.0.1:{self.port}/jev") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/jev-page.js") as response:
            source = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        for token in ("决策完成顺序", "实际执行顺序", "运行停止", "点击点查看详情",
                      "每个点代表一个已结束的决策任务", "决策点阵", "任务 "):
            self.assertNotIn(token, page)
        # HUD only: controls plus the decision network, no status prose.
        self.assertIn('id="jev-runtime"', page)
        self.assertIn("jev-hud", page)
        self.assertIn('id="runtime-start"', page)
        self.assertIn('id="runtime-stop"', page)
        self.assertIn('id="jev-timeline"', page)
        for token in ("trace-status-title", "trace-status-detail", "trace-event-count",
                      "runtime-state", "runtime-message", "runtime-meta", "state-badge"):
            self.assertNotIn(token, page)
        for token in ("eyebrow", "READ ONLY", "SEED BANK", "OBSERVATION", "PROCESS CONTROL", "DECISION SIGNALS",
                      "LOCAL CONTROL", "START / ", "STOP / ", "<footer>"):
            self.assertNotIn(token, page)
        for token in ("job_end", "action_result", "proposal_discarded", "runtime_stop", "决策完成顺序", "实际执行顺序",
                      "运行停止", "jev-decision-detail", "jev-runtime-order", "jev-runtime-job", "jev-cycle-card",
                      "selectedDecisionKey", "aria-pressed", "showDecision", "renderRuntimeJob",
                      "decisionCompletionOrderText", "/api/jev-trace"):
            self.assertNotIn(token, source)
        for token in ("jev-decision-detail", "jev-runtime-order", "jev-runtime-event", "jev-runtime-job", "jev-cycle-card",
                      "jev-decision-dot.waiting", "jev-decision-dot.failed", "jev-decision-dot.selected",
                      "jev-decision-dot.newest", "signal-in"):
            self.assertNotIn(token, stylesheet)
        self.assertIn("prefers-reduced-motion", stylesheet)
        # 所有一次性动画都必须在 reduced-motion 下关闭。
        for selector in (".is-fresh", ".fd-node.is-activating", ".fd-node.is-blooming",
                         ".fd-node.is-decaying", ".is-selected .fd-halo"):
            self.assertIn("animation: none", css_declarations(stylesheet, selector))
        script = DOM_HARNESS + r'''
(async () => {
  const payload = {status: "ok", schema_version: 2, run_id: "run-box", questions: [
    {question_id: "plant_target", branch_id: "plant", job_id: "job-000001", options: [
      {option_id: "peashooter@r0c0", probability: 0.5, executed: true},
      {option_id: "none_of_the_above", probability: 0.5, executed: false}]},
    {question_id: "should_collect_now", branch_id: "collect", job_id: "job-000002", options: [
      {option_id: "true", probability: 0.9, executed: true},
      {option_id: "false", probability: 0.1, executed: false}]}]};
  const page = createPage("dashboard/static/jev-page.js", {});
  vm.runInContext("renderOptionMatrix(" + JSON.stringify(payload) + ")", page.context);
  const nodes = nodesOf(page, "jev-timeline");
  const dots = nodes.filter((node) => node.className.split(" ").includes("jev-decision-dot"));
  console.log(JSON.stringify({
    classNames: [...new Set(nodes.map((node) => node.className).filter(Boolean))].sort(),
    tags: [...new Set(nodes.map((node) => node.tagName))].sort(),
    dotHandlers: [...new Set(dots.map((dot) => typeof dot.handlers.click))],
    text: page.document.getElementById("jev-timeline").textContent}));
})();'''
        rendered = run_node(script)
        self.assertEqual(rendered["classNames"], [
            "jev-decision-dot jev-dot-collect executed", "jev-decision-dot jev-dot-collect pending",
            "jev-decision-dot jev-dot-plant executed", "jev-decision-dot jev-dot-plant pending",
            "jev-intent-core",
            "jev-intent-node jev-intent-cancel idle", "jev-intent-node jev-intent-collect active",
            "jev-intent-node jev-intent-plant active",
            "jev-mesh", "jev-net", "jev-net-detail", "jev-net-intent"])
        self.assertEqual(rendered["tags"], ["button", "div", "span"])
        self.assertEqual(rendered["dotHandlers"], ["undefined"])
        for token in ("决策完成顺序", "实际执行顺序", "运行停止", "任务"):
            self.assertNotIn(token, rendered["text"])

    def test_recording_page_keeps_no_debug_chrome_while_the_observer_page_keeps_it(self):
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/state") as response:
            state_page = response.read().decode("utf-8")
        # 录屏场景不放调试控件：原始 JSON、视图开关、观察页签都不在录制页上。
        for token in ('data-state-view="json"', "结构化", "原始 JSON", "data-observation-tab",
                      "复制 JSON", "<nav"):
            self.assertNotIn(token, page)
        # 能力没有消失，而是留在独立观察页上。
        self.assertIn('id="state-json" class="json-tree"', state_page)
        self.assertIn('id="state-copy-button"', state_page)
        self.assertIn('id="state-copy-status"', state_page)
        self.assertIn('data-state-profile="jev"', state_page)

    def test_inventory_items_follow_state_cost_and_cooldown_counters(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/catalog") as response:
            catalog = json.loads(response.read())
        probe = viewmodel_probe("""
const state = {cards: [
  {type_code: 1, cost: 100, cooldown_ready: true},
  {type_code: 1, cost: 50, cooldown_ready: false, cooldown_progress_raw: 1735, cooldown_total_raw: 3000},
  {type_code: 1, cost: null, cooldown_ready: null},
], availability: {cards: "available"}};
const vm = JEVViewModel.buildRuntimeViewModel({state});
console.log(JSON.stringify({
  items: vm.inventory.items.map((i) => ({label: i.label, abbr: i.abbr, cost: i.cost, ready: i.ready, fraction: i.fraction})),
  available: vm.inventory.availableCount, readyKnown: vm.inventory.readyKnown,
  unknown: JEVViewModel.buildRuntimeViewModel({state: {availability: {cards: "unavailable"}}}).inventory.read,
}));
""", catalog)
        ready, cooling, bare = probe["items"]
        self.assertEqual(ready["label"], "向日葵")
        self.assertEqual(ready["abbr"], "SF")
        self.assertEqual(ready["cost"], 100)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["fraction"], 1)
        self.assertEqual(cooling["cost"], 50)
        self.assertAlmostEqual(cooling["fraction"], 1735 / 3000, places=6)
        self.assertFalse(cooling["ready"])
        # 既没有计数也没有标志时必须是未知，不能伪装成冷却完成。
        self.assertIsNone(bare["cost"])
        self.assertIsNone(bare["fraction"])
        self.assertIsNone(bare["ready"])
        self.assertEqual(probe["available"], 1)
        self.assertTrue(probe["readyKnown"])
        # 卡槽未读取时不产出条目，也不假报可数量。
        self.assertFalse(probe["unknown"])

    def test_zombie_facts_stay_readable_and_focus_is_the_nearest_one(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/catalog") as response:
            catalog = json.loads(response.read())
        probe = viewmodel_probe("""
const state = {
  zombies: [
    {row: 1, type_code: 0, hp: 170, total_hp: 170, distance_to_house_px: 338, distance_to_house_cells: 4},
    {row: 0, type_code: 2, hp: 370, total_hp: 370, distance_to_house_px: 120, distance_to_house_cells: 1},
  ],
  availability: {"zombies.distance_to_house_cells": "available"},
};
const vm = JEVViewModel.buildRuntimeViewModel({state});
console.log(JSON.stringify({list: vm.threats.list, focus: vm.currentTarget}));
""", catalog)
        self.assertEqual([zombie["id"] for zombie in probe["list"]], ["Z01", "Z02"])
        self.assertEqual(probe["list"][0]["label"], "普通僵尸")
        self.assertEqual(probe["list"][1]["label"], "路障僵尸")
        self.assertEqual(probe["list"][0]["hp"], 170)
        self.assertEqual(probe["list"][0]["distancePx"], 338)
        self.assertEqual(probe["list"][0]["row"], 1)
        # 聚焦 = 距房屋最近者，只影响“看谁”，不改动任何被展示的数值。
        self.assertEqual(probe["focus"]["id"], "Z02")
        self.assertEqual(probe["focus"]["distancePx"], 120)

        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        # 回归保护（R10）：字段不再被固定窄列挤出逐字换行。
        self.assertIn("white-space: nowrap", css_declarations(stylesheet, ".target-row"))
        self.assertIn("white-space: nowrap", css_declarations(stylesheet, ".target-head"))
        self.assertIn("white-space: nowrap", css_declarations(stylesheet, ".observe-row b"))
        for selector in (".target-rows", ".target-row", ".observe-rows", ".observe-row"):
            self.assertNotIn("56px", css_declarations(stylesheet, selector))
        self.assertNotIn("keep-all", stylesheet)

    def test_inventory_strip_stays_one_line_instead_of_ten_cards(self):
        with urlopen(f"http://127.0.0.1:{self.port}/static/style.css") as response:
            stylesheet = response.read().decode("utf-8")
        strip = css_declarations(stylesheet, ".rt-inventory")
        self.assertIn("display: flex", strip)
        self.assertNotIn("grid-template-columns", strip)
        # 行首的“可用 N”不能被折成两行。
        self.assertIn("white-space: nowrap", css_declarations(stylesheet, ".inv-count"))
        # 卡槽已从十张独立卡片降级为一条清单：卡片外壳必须全部消失。
        for token in (".seed-card", ".seed-cooldown", ".cooldown-fill", ".cards-list", ".seed-cost", ".seed-type"):
            self.assertNotIn(token, stylesheet)
        for token in (".inv-item", ".inv-abbr", ".inv-cost", ".inv-state"):
            self.assertIn(token, stylesheet)

    def test_decision_space_projects_real_options_without_fabricating_fields(self):
        """决策空间只呈现 Trace 真有的字段，且一次决策只点亮一个格点。"""
        with urlopen(f"http://127.0.0.1:{self.port}/api/catalog") as response:
            catalog = json.loads(response.read())
        payload = {
            "status": "ok", "schema_version": 2, "run_id": "run-1",
            "questions": [
                {"question_id": "construction_intent", "branch_id": "plant", "job_id": "job-000900",
                 "choice": "replace", "options": [
                     {"option_id": "replace", "probability": 0.72, "executed": False},
                     {"option_id": "keep", "probability": 0.18, "executed": False},
                     {"option_id": "cancel", "probability": 0.10, "executed": False}]},
                {"question_id": "plant_target_lane", "branch_id": "plant", "job_id": "job-000900",
                 "choice": "lane_1", "options": [
                     {"option_id": "lane_1", "probability": 0.6, "executed": False},
                     {"option_id": "lane_2", "probability": 0.4, "executed": False}]},
                {"question_id": "plant_target_lane_1", "branch_id": "plant", "job_id": "job-000900",
                 "choice": "sunflower@r1c3", "options": [
                     {"option_id": "sunflower@r1c3", "probability": 0.61, "executed": False},
                     {"option_id": "repeater@r1c3", "probability": 0.12, "executed": False}]},
                {"question_id": "plant_target_lane_2", "branch_id": "plant", "job_id": "job-000900",
                 "choice": "wall_nut@r2c4", "options": [
                     {"option_id": "wall_nut@r2c4", "probability": 0.3, "executed": False}]},
            ],
            "decision": {"job_id": "job-000900", "stage_id": "plant-decision", "status": "selected",
                         "intent": "plant", "effective_action": "plant",
                         "target": {"action": "place_plant", "type_name": "sunflower", "row": 1, "col": 3},
                         "target_choice_rule": "argmax", "fallback_reason": None, "latency_ms": 412},
            "execution": {"job_id": "job-000900", "boundary_status": "success", "outcome": "executed",
                          "target": {"action": "place_plant", "type_name": "sunflower", "row": 1, "col": 3},
                          "execution_elapsed_ms": 318},
        }
        probe = viewmodel_probe(
            "const vm = JEVViewModel.buildRuntimeViewModel({options: " + json.dumps(payload) + "});\n"
            "console.log(JSON.stringify({decision: vm.decision}));",
            catalog,
        )
        decision = probe["decision"]
        self.assertEqual([rail["label"] for rail in decision["rails"]], ["营建意图", "目标行"])
        selected = [option for option in decision["rails"][0]["options"] if option["selected"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["label"], "替换种植")
        self.assertEqual(selected[0]["probability"], 0.72)
        # 该 job 里只有选中的那一行才是权威，别的行不得再点亮格点。
        self.assertEqual(decision["field"]["authoritative"], "plant_target_lane_1")
        marked = [cell for cell in decision["field"]["cells"] if cell["selected"]]
        self.assertEqual([(cell["row"], cell["col"]) for cell in marked], [(1, 3)])
        self.assertEqual(marked[0]["typeLabel"], "向日葵")
        self.assertEqual(len(decision["field"]["cells"]), 2)
        self.assertEqual(decision["selected"]["stageLabel"], "种植决策")
        self.assertEqual(decision["selected"]["typeLabel"], "向日葵")
        self.assertEqual(decision["selected"]["cellText"], "R2 C4")
        self.assertEqual(decision["selected"]["rule"], "argmax")
        # 执行目标按动作查植物目录，而不是掉落物目录。
        self.assertEqual(decision["selected"]["executed"]["typeLabel"], "向日葵")
        self.assertEqual(decision["selected"]["executed"]["boundaryStatus"], "success")
        # mockup 里的威胁分、ETA、速度、自然语言理由在 Trace 中并不存在。
        blob = json.dumps(decision, ensure_ascii=False)
        for absent in ("threat", "eta", "speed", "reason", "grade"):
            self.assertNotIn(f'"{absent}"', blob)

    def test_a_confirmed_removal_lights_its_own_cell_and_never_reads_as_planting(self):
        """V20/R16: the lawn cell lights only for a same-job successful shovel_cell."""
        with urlopen(f"http://127.0.0.1:{self.port}/api/catalog") as response:
            catalog = json.loads(response.read())
        payload = {
            "status": "ok", "schema_version": 2, "run_id": "run-shovel",
            "questions": [
                {"question_id": "shovel_target", "branch_id": "plant", "job_id": "job-000004",
                 "choice": "remove@r2c3", "options": [
                     {"option_id": "remove@r2c3", "probability": 0.7, "executed": False},
                     {"option_id": "none_of_the_above", "probability": 0.3, "executed": False}]},
            ],
            "decision": {"job_id": "job-000004", "stage_id": "plant-decision", "status": "selected",
                         "intent": "plant", "effective_action": "shovel",
                         "target": {"action": "shovel_cell", "row": 2, "col": 3},
                         "target_choice_rule": "argmax", "fallback_reason": None, "latency_ms": 210},
            "execution": {"job_id": "job-000004", "boundary_status": "success", "outcome": "executed",
                          "target": {"action": "shovel_cell", "row": 2, "col": 3},
                          "execution_elapsed_ms": 318},
        }
        probe = viewmodel_probe(
            "const base = " + json.dumps(payload, ensure_ascii=False) + ";\n"
            "const variant = (mutate) => {const copy = JSON.parse(JSON.stringify(base)); mutate(copy); return copy;};\n"
            "const cells = (options) => JEVViewModel.buildRuntimeViewModel({options}).decision.field.cells;\n"
            "const selected = (options) => JEVViewModel.buildRuntimeViewModel({options}).decision.selected;\n"
            "console.log(JSON.stringify({\n"
            "  lit: cells(base),\n"
            "  authoritative: JEVViewModel.buildRuntimeViewModel({options: base}).decision.field.authoritative,\n"
            "  unverified: cells(variant((copy) => {copy.execution.boundary_status = 'unverified';})),\n"
            "  otherJob: cells(variant((copy) => {copy.execution.job_id = 'job-000009';})),\n"
            "  planted: cells(variant((copy) => {copy.execution.target.action = 'place_plant';})),\n"
            "  selected: selected(base),\n"
            "}));",
            catalog,
        )
        self.assertEqual(probe["authoritative"], "shovel_target")
        self.assertEqual(len(probe["lit"]), 1)
        lit = probe["lit"][0]
        self.assertEqual((lit["row"], lit["col"]), (2, 3))
        self.assertEqual(lit["optionId"], "remove@r2c3")
        self.assertEqual(lit["typeLabel"], "铲除")
        self.assertIs(lit["executed"], True)
        self.assertIs(lit["selected"], True)
        for absent in ("unverified", "otherJob", "planted"):
            self.assertIs(probe[absent][0]["executed"], False, absent)
        # The action reads as a removal and a cell, never as a planting.
        self.assertEqual(probe["selected"]["actionLabel"], "铲除")
        self.assertIsNone(probe["selected"]["typeLabel"])
        self.assertEqual(probe["selected"]["cellText"], "R3 C4")
        self.assertEqual(probe["selected"]["executed"]["actionLabel"], "铲除")

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

    def test_zombie_geometry_uses_backend_cells_and_never_guesses(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/catalog") as response:
            catalog = json.loads(response.read())
        probe = viewmodel_probe("""
const available = {"zombies.distance_to_house_cells": "available"};
const cases = {
  snapped: {availability: available, zombies: [{row: 2, distance_to_house_cells: 4, x: 999}]},
  unavailable: {availability: {}, zombies: [{row: 2, distance_to_house_cells: 4, x: 999}]},
  out_of_range: {availability: available, zombies: [{row: 2, distance_to_house_cells: 9, x: 10}]},
  negative: {availability: available, zombies: [{row: 2, distance_to_house_cells: -1, x: 10}]},
  bad_row: {availability: available, zombies: [{row: 7, distance_to_house_cells: 2, x: 10}]},
  missing_cells: {availability: available, zombies: [{row: 2, x: 640}]},
};
const out = {};
for (const [name, state] of Object.entries(cases)) {
  out[name] = JEVViewModel.buildRuntimeViewModel({state}).threats.list.map((z) => ({row: z.row, col: z.col}));
}
console.log(JSON.stringify(out));
""", catalog)
        self.assertEqual(probe["snapped"], [{"row": 2, "col": 4}])
        # 几何字段不可用时不能拿 x 像素凑一个格位出来。
        self.assertEqual(probe["unavailable"], [{"row": 2, "col": None}])
        self.assertEqual(probe["out_of_range"], [{"row": 2, "col": None}])
        self.assertEqual(probe["negative"], [{"row": 2, "col": None}])
        self.assertEqual(probe["bad_row"], [{"row": None, "col": 2}])
        self.assertEqual(probe["missing_cells"], [{"row": 2, "col": None}])


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

    def test_second_dashboard_cannot_share_the_same_port(self):
        with self.assertRaises(OSError):
            create_dashboard_server(self.poller, port=self.port)


class OptionMatrixReaderTests(unittest.TestCase):
    def test_projects_every_probability_key_noul_pair_and_none_of_the_above(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.jsonl"
            write_trace(path, [
                runtime_event(1, "job_start", run_id="run-a", job_id="job-000001", branch_id="plant"),
                request_result_event(2, run_id="run-a", job_id="job-000001", branch_id="plant", typed_answers={
                    "plant_target": {"choice": "potato_mine@r2c3", "confidence": 0.36, "level": 1,
                                     "probabilities": {"potato_mine@r2c3": 0.36, "peashooter@r1c0": 0.31,
                                                       "none_of_the_above": 0.33}},
                    "plant_target_lane_2": {"choice": "lane_4", "confidence": 0.4,
                                            "probabilities": {"lane_3": 0.2, "lane_4": 0.4,
                                                              "none_of_the_above": 0.4}},
                }),
                request_result_event(3, run_id="run-a", job_id="job-000002", branch_id="collect", typed_answers={
                    "should_collect_now": {"noul": 0.93},
                    "collect_target": {"choice": "item_0", "confidence": 0.52, "level": 1,
                                       "probabilities": {"item_0": 0.52, "none_of_the_above": 0.48}},
                    "construction_intent": {"choice": "keep", "confidence": 0.7,
                                            "probabilities": {"keep": 0.7, "replace": 0.2, "cancel": 0.1}},
                    "next_construction_type": {"choice": "wall_nut", "confidence": 0.6,
                                               "probabilities": {"sunflower": 0.3, "wall_nut": 0.6,
                                                                 "none_of_the_above": 0.1}},
                }),
            ])
            payload = OptionMatrixReader(path).read()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["run_id"], "run-a")
        groups = options_by_question(payload)
        self.assertEqual(sorted(groups), ["collect_target", "construction_intent", "next_construction_type",
                                          "plant_target", "plant_target_lane_2", "should_collect_now"])
        plant = groups["plant_target"]
        self.assertEqual(plant["branch_id"], "plant")
        self.assertEqual(plant["job_id"], "job-000001")
        self.assertEqual(plant["options"], [
            {"option_id": "potato_mine@r2c3", "probability": 0.36, "executed": False},
            {"option_id": "peashooter@r1c0", "probability": 0.31, "executed": False},
            {"option_id": "none_of_the_above", "probability": 0.33, "executed": False},
        ])
        self.assertEqual(option_ids(groups["plant_target_lane_2"]), ["lane_3", "lane_4", "none_of_the_above"])
        collect = groups["should_collect_now"]
        self.assertEqual(collect["branch_id"], "collect")
        self.assertEqual([option["option_id"] for option in collect["options"]], ["true", "false"])
        self.assertAlmostEqual(collect["options"][0]["probability"], 0.93)
        self.assertAlmostEqual(collect["options"][1]["probability"], 1.0 - 0.93)
        self.assertEqual(option_ids(groups["collect_target"]), ["item_0", "none_of_the_above"])
        self.assertEqual(option_ids(groups["construction_intent"]), ["keep", "replace", "cancel"])
        self.assertEqual(option_ids(groups["next_construction_type"]),
                         ["sunflower", "wall_nut", "none_of_the_above"])

    def test_keeps_the_latest_group_far_beyond_the_100_event_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long.jsonl"
            events = [runtime_event(1, "job_start", run_id="run-a", job_id="job-000001", branch_id="plant")]
            for index in range(120):
                events.append(request_result_event(
                    2 + index, run_id="run-a", job_id=f"job-{index:06d}", branch_id="plant",
                    typed_answers={"plant_target": {"choice": "single", "probabilities": {"single": 1.0}}},
                ))
            events.append(request_result_event(
                200, run_id="run-a", job_id="job-000121", branch_id="plant",
                typed_answers={"plant_target": {"choice": "latest", "probabilities": {
                    "latest": 0.5, "other_option": 0.3, "none_of_the_above": 0.2}}},
            ))
            write_trace(path, events)
            payload = OptionMatrixReader(path).read()
            window = TraceFileReader(path).read()
        # The existing reader keeps its 100-event window; the projection does not use it.
        self.assertEqual(window["status"], "ok")
        self.assertEqual(len(window["events"]), 100)
        self.assertEqual([group["question_id"] for group in payload["questions"]], ["plant_target"])
        self.assertEqual(payload["questions"][0]["job_id"], "job-000121")
        self.assertEqual(option_ids(payload["questions"][0]), ["latest", "other_option", "none_of_the_above"])

    def test_a_proven_execution_stays_lit_when_the_question_is_asked_again(self):
        """Re-asking must not erase what the game actually did earlier in the run."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.jsonl"
            write_trace(path, [
                request_result_event(1, run_id="run-a", job_id="job-000001", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {
                                         "potato_mine@r2c3": 0.6, "none_of_the_above": 0.4}}}),
                action_result_event(2, run_id="run-a", job_id="job-000001", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "potato_mine",
                                            "row": 2, "col": 3}),
            ])
            reader = OptionMatrixReader(path)
            first = reader.read()
            # The same question is asked again with a brand new job: the group is
            # replaced, but the proven option keeps its light.
            append_trace(path, [request_result_event(
                3, run_id="run-a", job_id="job-000002", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {
                    "potato_mine@r2c3": 0.2, "peashooter@r1c0": 0.7, "none_of_the_above": 0.1}}},
            )])
            second = reader.read()
        self.assertEqual(executed_options(options_by_question(first)["plant_target"]), ["potato_mine@r2c3"])
        group = options_by_question(second)["plant_target"]
        self.assertEqual(group["job_id"], "job-000002")
        self.assertEqual(option_ids(group), ["potato_mine@r2c3", "peashooter@r1c0", "none_of_the_above"])
        # Only the previously proven option is lit; the new candidates stay dark.
        self.assertEqual(executed_options(group), ["potato_mine@r2c3"])

    def test_new_run_id_clears_groups_and_lights(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.jsonl"
            write_trace(path, [
                request_result_event(1, run_id="run-a", job_id="job-000001", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {"potato_mine@r2c3": 1.0}}}),
                action_result_event(2, run_id="run-a", job_id="job-000001", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "potato_mine",
                                            "row": 2, "col": 3}),
            ])
            reader = OptionMatrixReader(path)
            first = reader.read()
            append_trace(path, [request_result_event(
                3, run_id="run-b", job_id="job-000002", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {"peashooter@r1c0": 1.0}}},
            )])
            second = reader.read()
        self.assertEqual(first["run_id"], "run-a")
        self.assertEqual(executed_options(first["questions"][0]), ["potato_mine@r2c3"])
        self.assertEqual(second["run_id"], "run-b")
        group = options_by_question(second)["plant_target"]
        self.assertEqual(group["job_id"], "job-000002")
        self.assertEqual(option_ids(group), ["peashooter@r1c0"])
        self.assertEqual(executed_options(group), [])

    def test_restarts_on_truncated_replaced_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "swap.jsonl"
            write_trace(path, [request_result_event(
                1, run_id="run-a", job_id="job-000001", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {"old_option": 1.0}}},
            )])
            reader = OptionMatrixReader(path)
            self.assertEqual(option_ids(reader.read()["questions"][0]), ["old_option"])

            # Same file, truncated in place and rewritten with a longer new run.
            write_trace(path, [
                runtime_event(1, "job_start", run_id="run-b", job_id="job-000002", branch_id="plant"),
                request_result_event(2, run_id="run-b", job_id="job-000002", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {
                                         "new_option": 0.4, "none_of_the_above": 0.6}}}),
                action_result_event(3, run_id="run-b", job_id="job-000002", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "new_option",
                                            "row": 0, "col": 0}),
            ])
            truncated = reader.read()
            self.assertEqual(truncated["run_id"], "run-b")
            self.assertEqual(option_ids(truncated["questions"][0]), ["new_option", "none_of_the_above"])

            # Deleted and recreated: the old groups must not survive either.
            path.unlink()
            write_trace(path, [request_result_event(
                1, run_id="run-c", job_id="job-000003", branch_id="collect",
                typed_answers={"should_collect_now": {"noul": 0.2}},
            )])
            recreated = reader.read()
            self.assertEqual(recreated["run_id"], "run-c")
            self.assertEqual([group["question_id"] for group in recreated["questions"]], ["should_collect_now"])

            path.unlink()
            missing = reader.read()
            self.assertEqual(missing["status"], "missing")
            self.assertEqual(missing["questions"], [])

            write_trace(path, [request_result_event(
                1, run_id="run-d", job_id="job-000004", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {"d_option": 1.0}}},
            )])
            self.assertEqual(option_ids(reader.read()["questions"][0]), ["d_option"])

    def test_waits_for_a_complete_trailing_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            write_trace(path, [request_result_event(
                1, run_id="run-a", job_id="job-000001", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {"old_option": 1.0}}},
            )])
            reader = OptionMatrixReader(path)
            self.assertEqual(option_ids(reader.read()["questions"][0]), ["old_option"])

            second = trace_lines([request_result_event(
                2, run_id="run-a", job_id="job-000002", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {
                    "new_option": 0.4, "none_of_the_above": 0.6}}},
            )])
            with path.open("a", encoding="utf-8") as stream:
                stream.write(second[: len(second) // 2])
            held = reader.read()
            self.assertEqual(held["questions"][0]["job_id"], "job-000001")
            self.assertEqual(option_ids(held["questions"][0]), ["old_option"])

            with path.open("a", encoding="utf-8") as stream:
                stream.write(second[len(second) // 2:])
            completed = reader.read()
            self.assertEqual(completed["questions"][0]["job_id"], "job-000002")
            self.assertEqual(option_ids(completed["questions"][0]), ["new_option", "none_of_the_above"])

    def test_lights_only_the_option_a_successful_same_job_action_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "executed.jsonl"
            write_trace(path, [
                request_result_event(1, run_id="run-a", job_id="job-000001", branch_id="plant", typed_answers={
                    "plant_target": {"probabilities": {"potato_mine@r2c3": 0.36, "peashooter@r1c0": 0.31,
                                                      "none_of_the_above": 0.33}}}),
                action_result_event(2, run_id="run-a", job_id="job-000001", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "potato_mine",
                                            "row": 2, "col": 3}),
                request_result_event(3, run_id="run-a", job_id="job-000002", branch_id="collect", typed_answers={
                    "should_collect_now": {"noul": 0.61},
                    "construction_intent": {"probabilities": {"keep": 0.6, "replace": 0.4}},
                    "next_construction_type": {"probabilities": {"wall_nut": 0.7, "none_of_the_above": 0.3}}}),
                action_result_event(4, run_id="run-a", job_id="job-000002", branch_id="collect",
                                    target={"action": "collect_item", "type_name": "sun",
                                            "row": None, "col": None}),
            ])
            payload = OptionMatrixReader(path).read()
        groups = options_by_question(payload)
        self.assertEqual(executed_options(groups["plant_target"]), ["potato_mine@r2c3"])
        self.assertEqual(executed_options(groups["should_collect_now"]), ["true"])
        # Management choices have no direct game action: they stay dark.
        self.assertEqual(executed_options(groups["construction_intent"]), [])
        self.assertEqual(executed_options(groups["next_construction_type"]), [])

    def test_never_lights_failed_mismatched_or_stale_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejected.jsonl"
            write_trace(path, [request_result_event(
                1, run_id="run-a", job_id="job-000001", branch_id="plant",
                typed_answers={"plant_target": {"probabilities": {"potato_mine@r2c3": 1.0}}},
            )])
            reader = OptionMatrixReader(path)
            # The same job's action did not succeed, so nothing lights.
            append_trace(path, [action_result_event(
                2, run_id="run-a", job_id="job-000001", branch_id="plant", status="unverified",
                target={"action": "place_plant", "type_name": "potato_mine", "row": 2, "col": 3},
            )])
            self.assertEqual(executed_options(reader.read()["questions"][0]), [])

            # A successful action that belongs to another job never lights this group.
            append_trace(path, [
                request_result_event(3, run_id="run-a", job_id="job-000002", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {"peashooter@r1c0": 1.0}}}),
                action_result_event(4, run_id="run-a", job_id="job-000099", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "peashooter",
                                            "row": 1, "col": 0}),
            ])
            self.assertEqual(executed_options(reader.read()["questions"][0]), [])

            # A newer request replaced the group; the older job's late action cannot light it.
            append_trace(path, [
                request_result_event(5, run_id="run-a", job_id="job-000003", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {
                                         "potato_mine@r2c3": 0.5, "none_of_the_above": 0.5}}}),
                action_result_event(6, run_id="run-a", job_id="job-000001", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "potato_mine",
                                            "row": 2, "col": 3}),
            ])
            self.assertEqual(executed_options(reader.read()["questions"][0]), [])

            # A success whose target maps onto no offered option stays dark too.
            append_trace(path, [
                request_result_event(7, run_id="run-a", job_id="job-000004", branch_id="plant",
                                     typed_answers={"plant_target": {"probabilities": {"wall_nut@r0c1": 1.0}}}),
                action_result_event(8, run_id="run-a", job_id="job-000004", branch_id="plant",
                                    target={"action": "place_plant", "type_name": "sunflower",
                                            "row": 4, "col": 4}),
            ])
            final = options_by_question(reader.read())["plant_target"]
            self.assertEqual(final["job_id"], "job-000004")
            self.assertEqual(executed_options(final), [])

    def test_reports_a_legacy_trace_instead_of_fabricating_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.jsonl"
            path.write_text(json.dumps({"schema_version": 1, "run_id": "run-v1", "cycle": 1,
                                        "outcome": "wait"}) + "\n", encoding="utf-8")
            payload = OptionMatrixReader(path).read()
        self.assertEqual(payload["status"], "legacy")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["questions"], [])


class RuntimeControllerTests(unittest.TestCase):
    def test_start_stop_and_restart_one_managed_process(self):
        sample = {"status": "ok", "valid": True, "game": {"phase": "playing", "paused": False}}
        processes = []

        class FakeProcess:
            def __init__(self):
                self.pid = 1000 + len(processes)
                self.code = None

            def poll(self):
                return self.code

            def terminate(self):
                self.code = 1

            def kill(self):
                self.code = 1

            def wait(self, timeout=None):
                return self.code

        def spawn(*_args, **_kwargs):
            process = FakeProcess()
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory:
            with patch("dashboard.runtime_control.PROCESS_LOG", Path(directory) / "process.log"), patch(
                "dashboard.runtime_control.RuntimeProcessLock.occupied", return_value=False
            ):
                controller = RuntimeController(Path(directory) / "run.jsonl", lambda: sample, process_factory=spawn)
                sample["game"]["paused"] = True
                self.assertEqual(controller.start()[0], 409)
                self.assertIn("已暂停", controller.status()["message"])
                sample["game"]["paused"] = False
                self.assertEqual(controller.start()[0], 202)
                self.assertEqual(controller.status()["state"], "running")
                self.assertEqual(controller.start()[0], 409)
                self.assertEqual(len(processes), 1)
                self.assertEqual(controller.stop()[0], 200)
                self.assertEqual(controller.status()["state"], "stopped")
                self.assertEqual(controller.start()[0], 202)
                self.assertEqual(len(processes), 2)
                controller.close()
                self.assertEqual(processes[-1].code, 1)


if __name__ == "__main__":
    unittest.main()
