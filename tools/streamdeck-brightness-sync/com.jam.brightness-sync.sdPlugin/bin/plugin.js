#!/usr/bin/env node
/**
 * Mirror MacBook (main display) brightness onto connected Stream Deck devices.
 * Polls DisplayServices via ./mac-brightness; sends setBrightness to Stream Deck.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync, execFileSync } = require("child_process");

const POLL_MS = 400;
const MIN_DELTA = 1;
const HELPER = path.join(__dirname, "mac-brightness");

let websocket = null;
let pluginUUID = null;
let actionContext = null;
let lastSent = -1;
let timer = null;

function log(...args) {
  console.error(new Date().toISOString(), ...args);
}

function readMacBrightness() {
  if (!fs.existsSync(HELPER)) {
    return null;
  }
  const r = spawnSync(HELPER, [], { encoding: "utf8", timeout: 2000 });
  if (r.status !== 0) {
    return null;
  }
  const n = parseInt(String(r.stdout).trim(), 10);
  if (!Number.isFinite(n)) {
    return null;
  }
  return Math.max(0, Math.min(100, n));
}

function send(event) {
  if (!websocket || websocket.readyState !== 1) {
    return;
  }
  websocket.send(JSON.stringify(event));
}

function setDeckBrightness(pct) {
  const payload = { brightness: pct };
  if (actionContext) {
    send({ event: "setBrightness", context: actionContext, payload });
  }
  if (pluginUUID) {
    send({ event: "setBrightness", context: pluginUUID, payload });
  }
  send({ event: "setBrightness", payload });
}

function updatePrefsBrightness(pct) {
  const raw = execFileSync("defaults", ["export", "com.elgato.StreamDeck", "-"]);
  const py = `
import plistlib, sys
d = plistlib.loads(sys.stdin.buffer.read())
devs = d.get("Devices") or {}
changed = False
target = int(sys.argv[1])
for _k, v in list(devs.items()):
    if isinstance(v, dict) and "map_dev_brightness" in v:
        if int(v.get("map_dev_brightness", -1)) != target:
            v["map_dev_brightness"] = target
            changed = True
if changed:
    sys.stdout.buffer.write(plistlib.dumps(d, fmt=plistlib.FMT_BINARY))
`;
  const out = spawnSync("/usr/bin/python3", ["-c", py, String(pct)], {
    input: raw,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (out.status === 0 && out.stdout && out.stdout.length > 0) {
    spawnSync("defaults", ["import", "com.elgato.StreamDeck", "-"], {
      input: out.stdout,
    });
  }
}

function syncOnce() {
  const pct = readMacBrightness();
  if (pct === null) {
    return;
  }
  if (lastSent >= 0 && Math.abs(pct - lastSent) < MIN_DELTA) {
    return;
  }
  setDeckBrightness(pct);
  lastSent = pct;
  try {
    updatePrefsBrightness(pct);
  } catch (err) {
    log("prefs update skipped", err.message || err);
  }
  if (actionContext) {
    send({
      event: "setTitle",
      context: actionContext,
      payload: { title: String(pct) + "%" },
    });
  }
}

function startLoop() {
  if (timer) {
    return;
  }
  syncOnce();
  timer = setInterval(syncOnce, POLL_MS);
  if (typeof timer.unref === "function") {
    timer.unref();
  }
}

function connect(port) {
  if (typeof WebSocket === "undefined") {
    log("fatal: need Node 22+ with global WebSocket (Stream Deck Node 24)");
    process.exit(1);
  }
  websocket = new WebSocket("ws://127.0.0.1:" + port);

  websocket.addEventListener("open", () => {
    send({ event: "registerPlugin", uuid: pluginUUID });
    log("registered", pluginUUID);
    startLoop();
  });

  websocket.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(String(ev.data));
    } catch (_) {
      return;
    }
    const event = msg.event;
    if (event === "willAppear" && msg.context) {
      actionContext = msg.context;
      lastSent = -1;
      syncOnce();
    } else if (event === "willDisappear" && msg.context === actionContext) {
      actionContext = null;
    } else if (event === "deviceDidConnect") {
      lastSent = -1;
      syncOnce();
    } else if (event === "keyDown") {
      lastSent = -1;
      syncOnce();
    }
  });

  websocket.addEventListener("close", () => {
    log("websocket closed");
    process.exit(0);
  });

  websocket.addEventListener("error", (err) => {
    log("websocket error", err.message || err);
  });
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-port") out.port = argv[++i];
    else if (a === "-pluginUUID") out.uuid = argv[++i];
    else if (a === "-registerEvent") out.registerEvent = argv[++i];
    else if (a === "-info") out.info = argv[++i];
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.port || !args.uuid) {
    console.error("usage: plugin.js -port N -pluginUUID UUID ...");
    process.exit(1);
  }
  pluginUUID = args.uuid;
  connect(parseInt(args.port, 10));
}

main();
