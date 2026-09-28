// Dev-only helper: screenshot a dashboard page and measure real geometry through
// the Chrome DevTools Protocol, using the Edge/Chrome already installed on the
// machine. No npm dependency, no bundled browser.
//
//   node tools/dev-view.mjs [url] [outPng] [probeJs]
//
// probeJs is evaluated in the page and its JSON result is printed, so layout
// questions can be answered with measurements instead of guesses.

import { spawn } from "node:child_process";
import { writeFileSync, rmSync, mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
];

const url = process.argv[2] || "http://127.0.0.1:8765/";
const outPng = process.argv[3] || "dev-view.png";
const probe = process.argv[4] || "";
const port = 9333 + (process.pid % 400);
const width = Number(process.env.VIEW_WIDTH || 1600);
const height = Number(process.env.VIEW_HEIGHT || 1400);
const waitMs = Number(process.env.VIEW_WAIT_MS || 3000);

const browser = BROWSERS.find((candidate) => existsSync(candidate));

if (!browser) {
  console.error("No Edge/Chrome binary found. Set one of:\n  " + BROWSERS.join("\n  "));
  process.exit(2);
}

const profile = mkdtempSync(join(tmpdir(), "dev-view-"));
const child = spawn(browser, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  `--window-size=${width},${height}`,
  "--hide-scrollbars",
  "about:blank",
], { stdio: "ignore" });

async function targetWs() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((entry) => entry.type === "page");
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {
      /* browser still starting */
    }
    await sleep(250);
  }
  throw new Error("devtools endpoint never became ready");
}

function session(ws) {
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
    else entry.resolve(message.result);
  });
  return (method, params) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });
}

let exitCode = 0;
try {
  const ws = new WebSocket(await targetWs());
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  const send = session(ws);
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(waitMs);

  if (probe) {
    const evaluated = await send("Runtime.evaluate", { expression: probe, returnByValue: true, awaitPromise: true });
    if (evaluated.exceptionDetails) {
      const detail = evaluated.exceptionDetails;
      console.error("probe threw:", detail.exception?.description || detail.text || JSON.stringify(detail));
      exitCode = 1;
    } else {
      const value = evaluated.result?.value;
      console.log(typeof value === "string" ? value : JSON.stringify(value, null, 2));
    }
  }

  // 等过渡动画跑完再截图：否则会截到入场动画的第一帧，看上去像页面坏了。
  const settleMs = Number(process.env.VIEW_SETTLE_MS || 600);
  if (settleMs > 0) await sleep(settleMs);

  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(outPng, Buffer.from(shot.data, "base64"));
  console.log(`screenshot -> ${outPng}`);
} catch (error) {
  console.error(`dev-view failed: ${error.message}`);
  exitCode = 1;
} finally {
  child.kill();
  await sleep(300);
  try {
    rmSync(profile, { recursive: true, force: true });
  } catch {
    /* best effort */
  }
}
process.exit(exitCode);
