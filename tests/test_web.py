import json
import subprocess
import threading
import unittest
from urllib.request import urlopen

from dashboard.server import StatePoller, create_dashboard_server


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
