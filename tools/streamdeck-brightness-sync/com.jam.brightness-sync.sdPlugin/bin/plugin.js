#!/usr/bin/env node
/**
 * Optional status key: shows current Mac brightness %.
 * Actual Deck LED sync is done by LaunchAgent com.jam.streamdeck-brightness-sync
 * (Elgato removed setBrightness; HID is exclusive while Stream Deck.app runs).
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const POLL_MS = 1000;
const HELPER = path.join(__dirname, "mac-brightness");

let websocket = null;
let pluginUUID = null;
let actionContext = null;
let lastTitle = "";
let timer = null;

function log(...args) {
  console.error(new Date().toISOString(), ...args);
}

function readMacBrightness() {
  if (!fs.existsSync(HELPER)) return null;
  const r = spawnSync(HELPER, [], { encoding: "utf8", timeout: 2000 });
  if (r.status !== 0) return null;
  const n = parseInt(String(r.stdout).trim(), 10);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n));
}

function send(event) {
  if (!websocket || websocket.readyState !== 1) return;
  websocket.send(JSON.stringify(event));
}

function syncTitle() {
  const pct = readMacBrightness();
  if (pct === null || !actionContext) return;
  const title = String(pct) + "%";
  if (title === lastTitle) return;
  lastTitle = title;
  send({
    event: "setTitle",
    context: actionContext,
    payload: { title },
  });
}

function startLoop() {
  if (timer) return;
  syncTitle();
  timer = setInterval(syncTitle, POLL_MS);
  if (typeof timer.unref === "function") timer.unref();
}

function connect(port) {
  websocket = new WebSocket("ws://127.0.0.1:" + port);
  websocket.addEventListener("open", () => {
    send({ event: "registerPlugin", uuid: pluginUUID });
    log("registered (status-only)", pluginUUID);
    startLoop();
  });
  websocket.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(String(ev.data));
    } catch (_) {
      return;
    }
    if (msg.event === "willAppear" && msg.context) {
      actionContext = msg.context;
      lastTitle = "";
      syncTitle();
    } else if (msg.event === "willDisappear" && msg.context === actionContext) {
      actionContext = null;
    }
  });
  websocket.addEventListener("close", () => process.exit(0));
  websocket.addEventListener("error", (err) => log("websocket error", err.message || err));
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-port") out.port = argv[++i];
    else if (a === "-pluginUUID") out.uuid = argv[++i];
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
