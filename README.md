# JevPvz

English | [简体中文](README.zh-CN.md)

Read Plants vs. Zombies game state on Windows, inspect it in a local dashboard, and optionally control the game through semantic actions or a TypeSafe JEV decision loop.

> Supports only the x86 Plants vs. Zombies `1.0.0.1051` executable. Its version and SHA-256 must match `configs/pvz_1051.py`. `action` and `jev-loop` **send input to the game**; `probe`, `snapshot`, and `serve` are read-only. The game may run in the background.

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
| `serve` | Start the local, read-only State dashboard and JEV Trace timeline | No | No |
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

- [Detailed usage guide (Chinese)](docs/usage.md): State observation, dashboard, actions, JEV, Python API, and live validation.
- [Architecture](docs/architecture.md): module responsibilities, State contract, and runtime.
- [Memory field evidence](docs/memory-map.md): field sources and evidence levels.
