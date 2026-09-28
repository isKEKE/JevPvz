# JevPvz

English | [简体中文](README.zh-CN.md)

Read Plants vs. Zombies game state on Windows, inspect it in a local dashboard, and optionally control the game through semantic actions or a TypeSafe JEV decision loop.

**Start with the [JEV capability report](docs/jev-capability-analysis.en.md).** It explains what the live games showed, where the strategy struggled, and how JEV fits into the larger system. Then use this README for setup and commands.

> Supports only the x86 Plants vs. Zombies `1.0.0.1051` executable. Its version and SHA-256 must match `configs/pvz_1051.py`. `action`, `jev-loop`, and the JEV Runtime START button **send input to the game**; observation pages remain read-only. The game may run in the background.

## Quick start

1. On Windows, install Python 3.12.13 and [uv](https://docs.astral.sh/uv/).
2. Put the game at `.game/PlantsVsZombies.exe` and start it. `.game/` is ignored by Git.
3. Install project dependencies:

   ```powershell
   uv sync
   ```

4. Run the command you need:

   ```powershell
   uv run python main.py snapshot --once   # Print one State JSON sample
   uv run python main.py serve              # Then open http://127.0.0.1:8765/
   uv run python main.py probe              # Check game identity and read once
   ```

Configure `.env` before running `jev-loop`, as described below.

## Commands

| Command | Purpose | Needs `.env` | Sends game input |
|---|---|---|---|
| `probe` | Check the process and executable identity; read raw state once | No | No |
| `snapshot` | Print normalized State JSON; `--profile jev` selects fewer fields | No | No |
| `serve` | Start the local State dashboard and JEV Runtime controls | Only when START is used | **Via JEV Runtime START** |
| `action` | Execute one semantic action | No | **Yes** |
| `jev-loop` | Run the asynchronous JEV decision loop and execute actions | **Yes** | **Yes** |

For all parameters and State fields, see the [detailed usage guide (Chinese)](docs/usage.md). See also the [architecture](docs/architecture.md) and [memory field evidence](docs/memory-map.md).

## Configure and run JEV

Set `TYPESAFE_API_KEY`, `HTTP_PROXY`, and `HTTPS_PROXY` in `.env` at the project root. All three are required; `jev-loop` exits during startup if either proxy is missing.

```powershell
$trace = ".log/jev-run.jsonl"
uv run python main.py jev-loop --trace-file $trace

# In another terminal, show the same Trace in the dashboard
uv run python main.py serve --jev-trace-file $trace
```

`uv run python main.py serve` opens the lawn page, which now **embeds the JEV Runtime HUD** so the controls and the decision network can be recorded next to the game; `/jev` serves the same HUD on its own page. The HUD is a neon sci-fi panel whose only text is its accessibility labels: cyan ▶ starts and magenta ■ stops, with no status prose (the panel state drives which button is lit). Once the game is connected and playing, START launches one `jev-loop` child process; STOP terminates that child. A second Loop, including one launched from the CLI, is rejected while the first is active. Pausing, ending, or leaving the game ends the Loop through its existing stop rules. The page draws the current run as a left-to-right decision network: a derived intent layer (`收集`/`种植`/`取消`, lit for the branch this cycle actually reached), connecting links, then the concrete targets. The collection layer tiles **one point per option** of its latest request; the planting layer is the **fixed 5x9 lawn matrix**, where every board cell exists whether or not it was offered and lights when a proven placement named that cell. There are no visible text labels: every node and cell carries its name for hover and keyboard focus. A point or cell lights only when the summary proves that exact option executed: a same-job `action_result` with `boundary.status == success` whose target maps onto it (a successful plant's type/row/column, or a successful collection's `should_collect_now: true`), and a proven option **stays lit for the rest of the run** even after the question is asked again. Failed, unverified, discarded, model-only, and late older-job actions stay dark, management choices such as `construction_intent` never light, and missing evidence is shown as dark rather than inferred; model probability is never treated as execution. A new run clears the previous points, and a page refresh restores the current run from the summary route. A schema-v1 Trace has no complete option set, so the page only shows a compatibility notice instead of inventing points. On the lawn page the per-lane summary spans the full row and each zombie shows only its name, position, and HP; the seed cards keep the plant name centered over a recharge bar drawn from the card's own cooldown counters (full when ready, partial while recharging, indeterminate when unknown) with the sun cost as a plain number at the bottom right, staying in one row that fits all ten on a wide panel. English eyebrow labels and page footers were removed, so the UI is Chinese-only. A browser START needs the same `.env` JEV configuration as the CLI. Runtime process output is saved in `.log/jev-dashboard-process.log`.

The loop runs until a stop condition occurs, such as level completion, game disconnection, or Ctrl+C. Use `--max-cycles 20` to limit the number of terminated decision jobs, or `--interval-ms 250` to limit observation frequency. `--trace-file` is required on every run. **Starting a new run clears an existing JEV Trace at that path**; choose a new path to keep earlier runs. See the [usage guide (Chinese)](docs/usage.md#jev-决策循环会操作游戏) for configuration, stop conditions, and Trace details.

## Manual actions

Each `action` command executes one request. These examples **send input to the game**:

```powershell
uv run python main.py action --action-json '{"action":"place_plant","card_slot":1,"row":0,"col":0}'
uv run python main.py action --action-json '{"action":"collect_item","item_id":3748399104,"timeout_ms":10000}'
uv run python main.py action --action-json '{"action":"shovel_cell","row":0,"col":0,"timeout_ms":10000}'
```

Replace the example `item_id` with an ID from the current State. The result `status` is `success`, `rejected`, or `unverified`; only a change confirmed by a new State sample counts as `success`. See the [usage guide (Chinese)](docs/usage.md#语义动作会操作游戏) for parameters, validation rules, and exit codes.

## Tests and documentation

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

- [JEV capability report](docs/jev-capability-analysis.en.md): findings and limits of the live-game experiment; recommended first read.
- [Detailed usage guide (Chinese)](docs/usage.md): State observation, dashboard, actions, JEV, Python API, and live validation.
- [Architecture](docs/architecture.md): module responsibilities, State contract, and runtime.
- [Memory field evidence](docs/memory-map.md): field sources and evidence levels.
