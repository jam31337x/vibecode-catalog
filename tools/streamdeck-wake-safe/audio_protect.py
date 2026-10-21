#!/usr/bin/python3
"""Store XLR mic gain + main output; clamp reconnect + unexpected output jumps."""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_float,
    c_int32,
    c_uint32,
    c_uint8,
    c_void_p,
    cdll,
    create_string_buffer,
    sizeof,
    util,
)
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
SUPPORT = HOME / "Library/Application Support/com.jam.audio-protect"
STATE_PATH = SUPPORT / "state.json"
HOLD_PATH = SUPPORT / "hold-mute"
LOG_PATH = HOME / "Library/Logs/audio-protect.log"
WL_HOST = "127.0.0.1"
WL_PORTS = range(1884, 1894)

# Safe output after reconnect / unexpected hardware jump.
RECONNECT_OUTPUT = 0.20
LEARN_S = 1.75
POLL_S = 0.05
WL_S = 0.25
NOTIFY_S = 12.0
# After dock appears, keep outputs forced to RECONNECT_OUTPUT briefly so a
# late hardware jump cannot bang ears; then release control to the user.
RECONNECT_GUARD_S = 2.5
# Sudden CoreAudio output rise vs last accepted sample. Smaller steps (knob)
# are treated as intentional and only update the baseline.
JUMP_THRESHOLD = 0.10
# Ignore further jump logic after we clamp (avoids feedback / thrash).
JUMP_COOLDOWN_S = 1.5

XLR_NAME = "XLR Dock"
BOOM_UID = "GDAudioDevice_UID"
WL_XLR_ID = "XLR Dock A8A9A41010CS1W"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{now_iso()} {msg}"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    if sys.stderr.isatty():
        print(line, file=sys.stderr, flush=True)


def notify(title: str, body: str) -> None:
    script = (
        f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    )
    subprocess.Popen(
        ["/usr/bin/osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def default_state() -> dict:
    return {
        "saved": {
            "mic_gain": 0.42666668,
            "boom_level": 0.3117361,
            "xlr_hp": 0.16,
            "xlr_ca": 0.3117361,
            "boom_ca": 0.3117361,
            "updated_at": None,
        },
        "learned": True,
    }


def load_state() -> dict:
    base = default_state()
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base.update(data)
                if isinstance(data.get("saved"), dict):
                    base["saved"] = {**default_state()["saved"], **data["saved"]}
        except (OSError, json.JSONDecodeError) as exc:
            log(f"state read failed: {exc}")
    return base


def save_state(state: dict) -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def reconnect_levels(saved: dict) -> dict:
    """Mute-safe output levels after dock/output change; keep mic gain."""
    out = dict(saved)
    out["boom_level"] = RECONNECT_OUTPUT
    out["xlr_hp"] = RECONNECT_OUTPUT
    out["xlr_ca"] = RECONNECT_OUTPUT
    out["boom_ca"] = RECONNECT_OUTPUT
    return out


# --- CoreAudio ---

def _fcc(s: str) -> int:
    return int.from_bytes(s.encode("ascii"), "big")


class _Addr(Structure):
    _fields_ = [("sel", c_uint32), ("scope", c_uint32), ("elem", c_uint32)]


_Listener = CFUNCTYPE(c_int32, c_uint32, c_uint32, c_void_p, c_void_p)

ca = cdll.LoadLibrary(util.find_library("CoreAudio"))
cf = cdll.LoadLibrary(util.find_library("CoreFoundation"))

ca.AudioObjectGetPropertyDataSize.argtypes = [
    c_uint32, POINTER(_Addr), c_uint32, c_void_p, POINTER(c_uint32)
]
ca.AudioObjectGetPropertyDataSize.restype = c_int32
ca.AudioObjectGetPropertyData.argtypes = [
    c_uint32, POINTER(_Addr), c_uint32, c_void_p, POINTER(c_uint32), c_void_p
]
ca.AudioObjectGetPropertyData.restype = c_int32
ca.AudioObjectSetPropertyData.argtypes = [
    c_uint32, POINTER(_Addr), c_uint32, c_void_p, c_uint32, c_void_p
]
ca.AudioObjectSetPropertyData.restype = c_int32
ca.AudioObjectAddPropertyListener.argtypes = [
    c_uint32, POINTER(_Addr), _Listener, c_void_p
]
ca.AudioObjectAddPropertyListener.restype = c_int32
ca.AudioObjectRemovePropertyListener.argtypes = [
    c_uint32, POINTER(_Addr), _Listener, c_void_p
]
ca.AudioObjectRemovePropertyListener.restype = c_int32
cf.CFStringGetLength.argtypes = [c_void_p]
cf.CFStringGetLength.restype = c_int32
cf.CFStringGetCString.argtypes = [c_void_p, c_void_p, c_int32, c_uint32]
cf.CFStringGetCString.restype = c_uint8
cf.CFRelease.argtypes = [c_void_p]

SYS = 1
SCOPE_GLOB = _fcc("glob")
SCOPE_OUT = _fcc("outp")
SCOPE_IN = _fcc("inpt")
PROP_DEV = _fcc("dev#")
PROP_UID = _fcc("uid ")
PROP_NAME = _fcc("lnam")
PROP_VOL = _fcc("volm")
PROP_MUTE = _fcc("mute")
UTF8 = 0x08000100


def _cfstr(ptr: int | None) -> str:
    if not ptr:
        return ""
    n = cf.CFStringGetLength(ptr) + 1
    buf = create_string_buffer(max(16, n * 4))
    ok = cf.CFStringGetCString(ptr, buf, len(buf), UTF8)
    cf.CFRelease(ptr)
    return buf.value.decode() if ok else ""


def _get_cf(oid: int, sel: int) -> str:
    addr = _Addr(sel, SCOPE_GLOB, 0)
    ptr = c_void_p()
    sz = c_uint32(sizeof(c_void_p))
    if ca.AudioObjectGetPropertyData(oid, byref(addr), 0, None, byref(sz), byref(ptr)):
        return ""
    return _cfstr(ptr.value)


def _get_f32(oid: int, sel: int, scope: int, elem: int) -> float | None:
    addr = _Addr(sel, scope, elem)
    v = c_float()
    sz = c_uint32(4)
    if ca.AudioObjectGetPropertyData(oid, byref(addr), 0, None, byref(sz), byref(v)):
        return None
    return float(v.value)


def _get_u32(oid: int, sel: int, scope: int, elem: int) -> int | None:
    addr = _Addr(sel, scope, elem)
    v = c_uint32()
    sz = c_uint32(4)
    if ca.AudioObjectGetPropertyData(oid, byref(addr), 0, None, byref(sz), byref(v)):
        return None
    return int(v.value)


def _set_f32(oid: int, sel: int, scope: int, elem: int, value: float) -> bool:
    addr = _Addr(sel, scope, elem)
    v = c_float(value)
    return ca.AudioObjectSetPropertyData(oid, byref(addr), 0, None, 4, byref(v)) == 0


def _set_u32(oid: int, sel: int, scope: int, elem: int, value: int) -> bool:
    addr = _Addr(sel, scope, elem)
    v = c_uint32(value)
    return ca.AudioObjectSetPropertyData(oid, byref(addr), 0, None, 4, byref(v)) == 0


def list_devices() -> list[tuple[int, str, str]]:
    addr = _Addr(PROP_DEV, SCOPE_GLOB, 0)
    sz = c_uint32(0)
    if ca.AudioObjectGetPropertyDataSize(SYS, byref(addr), 0, None, byref(sz)):
        return []
    n = sz.value // 4
    if n <= 0 or n > 512:
        return []
    ids = (c_uint32 * n)()
    if ca.AudioObjectGetPropertyData(SYS, byref(addr), 0, None, byref(sz), ids):
        return []
    out = []
    for oid in ids:
        out.append((int(oid), _get_cf(oid, PROP_NAME), _get_cf(oid, PROP_UID)))
    return out


def vol_elems(oid: int) -> list[int]:
    found = []
    for elem in range(0, 8):
        if _get_f32(oid, PROP_VOL, SCOPE_OUT, elem) is not None:
            found.append(elem)
    return found


def mute_elems(oid: int) -> list[int]:
    found = []
    for elem in range(0, 8):
        if _get_u32(oid, PROP_MUTE, SCOPE_OUT, elem) is not None:
            found.append(elem)
    return found


def max_volume(oid: int) -> float | None:
    vals = [_get_f32(oid, PROP_VOL, SCOPE_OUT, e) for e in range(0, 8)]
    nums = [v for v in vals if v is not None]
    return max(nums) if nums else None


def any_unmuted(oid: int) -> bool | None:
    flags = [_get_u32(oid, PROP_MUTE, SCOPE_OUT, e) for e in range(0, 8)]
    known = [f for f in flags if f is not None]
    if not known:
        return None
    return any(f == 0 for f in known)


def set_mute(oid: int, muted: bool) -> None:
    for elem in mute_elems(oid):
        _set_u32(oid, PROP_MUTE, SCOPE_OUT, elem, 1 if muted else 0)


def set_volume(oid: int, value: float) -> None:
    value = clamp01(value)
    for elem in vol_elems(oid):
        _set_f32(oid, PROP_VOL, SCOPE_OUT, elem, value)


def find_xlr(devs: list[tuple[int, str, str]] | None = None) -> tuple[int, str, str] | None:
    for oid, name, uid in (devs or list_devices()):
        if XLR_NAME in name and "Wave Link" not in name:
            return oid, name, uid
    return None


def find_boom(devs: list[tuple[int, str, str]] | None = None) -> tuple[int, str, str] | None:
    for oid, name, uid in (devs or list_devices()):
        if uid == BOOM_UID or name == "BoomAudio":
            return oid, name, uid
    return None


# --- Wave Link websocket ---

def _mask(payload: bytes) -> bytes:
    mask = os.urandom(4)
    return mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def ws_send(sock: socket.socket, text: str) -> None:
    data = text.encode()
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", n))
    sock.sendall(bytes(header) + _mask(data))


def ws_recv(sock: socket.socket) -> str | None:
    hdr = _recv_exact(sock, 2)
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    if b2 & 0x80:
        mask = _recv_exact(sock, 4)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(_recv_exact(sock, length)))
    else:
        payload = _recv_exact(sock, length)
    if opcode == 0x8:
        return None
    return payload.decode()


class WaveLink:
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self._id = 1
        self.port = 1884
        self.lock = threading.Lock()

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def connect(self) -> bool:
        self.close()
        ports = [self.port] + [p for p in WL_PORTS if p != self.port]
        last: Exception | None = None
        for port in ports[:3]:
            try:
                sock = socket.create_connection((WL_HOST, port), 0.25)
                key = base64.b64encode(os.urandom(16)).decode()
                req = (
                    "GET / HTTP/1.1\r\n"
                    f"Host: {WL_HOST}:{port}\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key}\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "Origin: streamdeck://\r\n"
                    "\r\n"
                )
                sock.sendall(req.encode())
                header = b""
                sock.settimeout(0.8)
                while b"\r\n\r\n" not in header:
                    chunk = sock.recv(1)
                    if not chunk:
                        break
                    header += chunk
                if b"101" not in header.split(b"\r\n", 1)[0]:
                    sock.close()
                    continue
                self.sock = sock
                self.port = port
                self.rpc("getApplicationInfo")
                self.rpc("setPluginInfo", {"connectedDevices": []})
                return True
            except (OSError, RuntimeError, json.JSONDecodeError, TimeoutError) as exc:
                last = exc
                self.close()
        if last:
            raise last
        return False

    def rpc(self, method: str, params=None, timeout: float = 2.0):
        sock = self.sock
        if sock is None:
            raise ConnectionError("not connected")
        self._id += 1
        req_id = self._id
        msg = {"id": req_id, "jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        sock.settimeout(timeout)
        ws_send(sock, json.dumps(msg))
        while True:
            raw = ws_recv(sock)
            if raw is None:
                raise ConnectionError("ws closed")
            data = json.loads(raw)
            if data.get("id") == req_id:
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data.get("result")

    def snapshot(self) -> dict:
        ins = self.rpc("getInputDevices") or {}
        outs = self.rpc("getOutputDevices") or {}
        snap = {
            "mic_gain": None,
            "xlr_hp": None,
            "boom_level": None,
            "xlr_present": False,
        }
        for dev in ins.get("inputDevices") or []:
            if dev.get("id") == WL_XLR_ID or (
                dev.get("isWaveDevice") and XLR_NAME in (dev.get("name") or "")
            ):
                snap["xlr_present"] = True
                for bus in dev.get("inputs") or []:
                    if bus.get("id") == "mic1":
                        gain = bus.get("gain") or {}
                        if "value" in gain:
                            snap["mic_gain"] = float(gain["value"])
        for dev in outs.get("outputDevices") or []:
            if dev.get("id") == BOOM_UID:
                for bus in dev.get("outputs") or []:
                    if bus.get("id") == "generic" and "level" in bus:
                        snap["boom_level"] = float(bus["level"])
            if XLR_NAME in (dev.get("name") or "") or dev.get("id") == WL_XLR_ID:
                snap["xlr_present"] = True
                for bus in dev.get("outputs") or []:
                    if bus.get("id") == "headphone1" and "level" in bus:
                        snap["xlr_hp"] = float(bus["level"])
        return snap

    def apply(self, saved: dict, mute_outputs: bool | None = None) -> None:
        boom = {
            "id": BOOM_UID,
            "outputs": [{"id": "generic", "level": clamp01(saved["boom_level"])}],
        }
        hp = {
            "id": WL_XLR_ID,
            "outputs": [{"id": "headphone1", "level": clamp01(saved["xlr_hp"])}],
        }
        if mute_outputs is not None:
            boom["outputs"][0]["isMuted"] = mute_outputs
            hp["outputs"][0]["isMuted"] = mute_outputs
        self.rpc("setOutputDevice", {"outputDevice": boom})
        try:
            self.rpc("setOutputDevice", {"outputDevice": hp})
        except RuntimeError:
            pass
        try:
            self.rpc(
                "setInputDevice",
                {
                    "id": WL_XLR_ID,
                    "inputs": [{"id": "mic1", "gain": {"value": clamp01(saved["mic_gain"])}}],
                },
            )
        except RuntimeError:
            pass


def coreaudio_snapshot() -> dict:
    devs = list_devices()
    xlr = find_xlr(devs)
    boom = find_boom(devs)
    return {
        "xlr_id": None if xlr is None else xlr[0],
        "xlr_ca": None if xlr is None else max_volume(xlr[0]),
        "xlr_unmuted": None if xlr is None else any_unmuted(xlr[0]),
        "boom_id": None if boom is None else boom[0],
        "boom_ca": None if boom is None else max_volume(boom[0]),
        "boom_unmuted": None if boom is None else any_unmuted(boom[0]),
    }


def mute_outputs_now() -> None:
    devs = list_devices()
    for finder in (find_xlr, find_boom):
        hit = finder(devs)
        if hit:
            set_mute(hit[0], True)


def ensure_xlr_input_hot(oid: int | None = None) -> None:
    """Keep XLR Dock *input* at full / unmuted. Ear-protect only touches outputs."""
    if oid is None:
        hit = find_xlr()
        if not hit:
            return
        oid = hit[0]
    for elem in range(0, 4):
        if _get_u32(oid, PROP_MUTE, SCOPE_IN, elem) is not None:
            _set_u32(oid, PROP_MUTE, SCOPE_IN, elem, 0)
        if _get_f32(oid, PROP_VOL, SCOPE_IN, elem) is not None:
            _set_f32(oid, PROP_VOL, SCOPE_IN, elem, 1.0)


def apply_coreaudio(saved: dict, muted: bool) -> None:
    devs = list_devices()
    xlr = find_xlr(devs)
    boom = find_boom(devs)
    if xlr:
        ensure_xlr_input_hot(xlr[0])
        set_mute(xlr[0], True)
        set_volume(xlr[0], clamp01(saved.get("xlr_ca", RECONNECT_OUTPUT)))
        if not muted:
            set_mute(xlr[0], False)
    if boom:
        set_mute(boom[0], True)
        set_volume(boom[0], clamp01(saved.get("boom_ca", RECONNECT_OUTPUT)))
        if not muted:
            set_mute(boom[0], False)


def holding() -> bool:
    return HOLD_PATH.exists()


def set_hold(on: bool) -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    if on:
        HOLD_PATH.write_text(now_iso() + "\n", encoding="utf-8")
    elif HOLD_PATH.exists():
        HOLD_PATH.unlink()


class Protector:
    def __init__(self) -> None:
        self.state = load_state()
        self.wl = WaveLink()
        self.lock = threading.Lock()
        self.last_notify = 0.0
        self.xlr_since = 0.0
        self.prev_xlr_id: int | None = None
        self.saw_missing = False
        self.prev_xlr_vol: float | None = None
        self.prev_boom_vol: float | None = None
        self.stable_from = 0.0
        self._jump_cooldown_until = 0.0
        # Keep callback alive for CoreAudio; never call set_volume from it
        # except the existing reconnect mute path (device-list only).
        self._cb = _Listener(self._on_audio)
        self._dev_addr = _Addr(PROP_DEV, SCOPE_GLOB, 0)
        self._vol_addr = _Addr(PROP_VOL, SCOPE_OUT, 0)
        self._mute_addr = _Addr(PROP_MUTE, SCOPE_OUT, 0)
        self._listen_oid: int | None = None
        self._sys_listen = False
        self._wakeup = threading.Event()
        self.wl_snap: dict | None = None
        self._pending_wl: tuple[dict, bool] | None = None

    def _on_audio(self, oid, _n, _addrs, _data):
        # CoreAudio listener: keep shallow. No recursion into restore/jump.
        try:
            oid = int(oid)
            # Device list change only — never fight live volume knobs here.
            if oid == SYS and (holding() or self.saw_missing or self._in_reconnect_guard()):
                xlr = find_xlr()
                if xlr:
                    set_mute(xlr[0], True)
                    set_volume(xlr[0], RECONNECT_OUTPUT)
        except Exception:
            pass
        self._wakeup.set()
        return 0

    def _in_reconnect_guard(self) -> bool:
        return self.xlr_since > 0 and (time.time() - self.xlr_since) < RECONNECT_GUARD_S

    def _in_jump_cooldown(self) -> bool:
        return time.time() < self._jump_cooldown_until

    def _install_listeners(self, xlr_id: int | None) -> None:
        # Only watch device add/remove. Volume jumps are detected on the
        # poll loop so set_volume cannot re-enter the HAL callback stack.
        if not self._sys_listen:
            ca.AudioObjectAddPropertyListener(SYS, byref(self._dev_addr), self._cb, None)
            self._sys_listen = True
        if self._listen_oid is not None:
            ca.AudioObjectRemovePropertyListener(
                self._listen_oid, byref(self._vol_addr), self._cb, None
            )
            ca.AudioObjectRemovePropertyListener(
                self._listen_oid, byref(self._mute_addr), self._cb, None
            )
            self._listen_oid = None

    def _maybe_notify(self, body: str) -> None:
        now = time.time()
        if now - self.last_notify < NOTIFY_S:
            return
        self.last_notify = now
        notify("Audio protect", body)

    def restore(self, reason: str, keep_muted: bool) -> None:
        # Force outputs to 20%, keep mic gain. Safe from poll thread only.
        levels = reconnect_levels(self.state["saved"])
        log(
            f"restore ({reason}) gain={levels['mic_gain']:.3f} "
            f"outputs→{RECONNECT_OUTPUT:.2f} muted={keep_muted}"
        )
        apply_coreaudio(levels, muted=True)
        self._pending_wl = (dict(levels), keep_muted)
        if not keep_muted:
            time.sleep(0.04)
            apply_coreaudio(levels, muted=False)
        self._maybe_notify(f"Output set to 20% ({reason})")

    def _remember_outputs_safe(self) -> None:
        saved = self.state["saved"]
        saved["xlr_ca"] = RECONNECT_OUTPUT
        saved["boom_ca"] = RECONNECT_OUTPUT
        saved["xlr_hp"] = RECONNECT_OUTPUT
        saved["boom_level"] = RECONNECT_OUTPUT
        saved["updated_at"] = now_iso()
        save_state(self.state)

    def _detect_unexpected_jump(self, ca_snap: dict) -> bool:
        """Return True if outputs were clamped to 20% for a ≥+10% spike.

        Detection runs on the poll thread only (not the HAL callback) so
        applying volume cannot recurse into CoreAudio listeners.
        Baseline floats only — no history buffers.
        """
        now = time.time()
        xlr = ca_snap.get("xlr_ca")
        boom = ca_snap.get("boom_ca")

        if self._in_jump_cooldown():
            if xlr is not None:
                self.prev_xlr_vol = xlr
            if boom is not None:
                self.prev_boom_vol = boom
            return False

        reasons: list[str] = []
        if xlr is not None and self.prev_xlr_vol is not None:
            delta = xlr - self.prev_xlr_vol
            if delta >= JUMP_THRESHOLD:
                reasons.append(
                    f"xlr {self.prev_xlr_vol:.0%}→{xlr:.0%} (+{delta:.0%})"
                )
        if boom is not None and self.prev_boom_vol is not None:
            delta = boom - self.prev_boom_vol
            if delta >= JUMP_THRESHOLD:
                reasons.append(
                    f"boom {self.prev_boom_vol:.0%}→{boom:.0%} (+{delta:.0%})"
                )

        if not reasons:
            return False

        self._jump_cooldown_until = now + JUMP_COOLDOWN_S
        self.stable_from = 0.0
        log(f"unexpected output jump ({'; '.join(reasons)}); clamp→{RECONNECT_OUTPUT:.0%}")
        self.restore("unexpected-jump", keep_muted=False)
        self._remember_outputs_safe()
        self.prev_xlr_vol = RECONNECT_OUTPUT
        self.prev_boom_vol = RECONNECT_OUTPUT
        return True

    def _learn(self, ca_snap: dict, wl_snap: dict | None) -> None:
        """Remember mic gain only — never use learned output as a clamp ceiling."""
        if holding() or not self.state.get("learned", True):
            return
        if not ca_snap["xlr_id"]:
            self.stable_from = 0.0
            return
        now = time.time()
        if self.stable_from == 0.0:
            self.stable_from = now
            return
        if now - self.stable_from < LEARN_S:
            return
        saved = self.state["saved"]
        changed = False
        if wl_snap and wl_snap.get("mic_gain") is not None:
            g = clamp01(wl_snap["mic_gain"])
            if abs(g - saved["mic_gain"]) > 0.001:
                saved["mic_gain"] = g
                changed = True
        # Track last output for status only — not enforced while you turn the knob.
        if ca_snap["xlr_ca"] is not None:
            saved["xlr_ca"] = clamp01(ca_snap["xlr_ca"])
            changed = True
        if ca_snap["boom_ca"] is not None:
            saved["boom_ca"] = clamp01(ca_snap["boom_ca"])
            changed = True
        if wl_snap:
            if wl_snap.get("boom_level") is not None:
                saved["boom_level"] = clamp01(wl_snap["boom_level"])
                changed = True
            if wl_snap.get("xlr_hp") is not None:
                saved["xlr_hp"] = clamp01(wl_snap["xlr_hp"])
                changed = True
        if changed:
            saved["updated_at"] = now_iso()
            save_state(self.state)
        self.stable_from = now

    def tick(self, wl_snap: dict | None) -> None:
        with self.lock:
            ca_snap = coreaudio_snapshot()
            xlr_id = ca_snap["xlr_id"]
            self._install_listeners(xlr_id)
            appeared = False
            if xlr_id is None:
                if self.prev_xlr_id is not None:
                    log("XLR Dock output disappeared")
                    self.saw_missing = True
                    self.xlr_since = 0.0
                    self.stable_from = 0.0
            elif self.saw_missing or (
                self.prev_xlr_id is not None and xlr_id != self.prev_xlr_id
            ):
                appeared = True
                self.saw_missing = False
            if appeared:
                log(f"XLR Dock output appeared id={xlr_id} vol={ca_snap['xlr_ca']}")
                self.xlr_since = time.time()
                self.stable_from = 0.0
                ensure_xlr_input_hot(xlr_id)
                self.restore("xlr-appear", keep_muted=holding())
            elif holding():
                apply_coreaudio(reconnect_levels(self.state["saved"]), muted=True)
            elif self._in_reconnect_guard():
                # Hold at ≤20% without mute flicker while hardware settles.
                ensure_xlr_input_hot(xlr_id)
                levels = reconnect_levels(self.state["saved"])
                vol = ca_snap["xlr_ca"]
                boom = ca_snap["boom_ca"]
                if (vol is not None and vol > RECONNECT_OUTPUT + 0.01) or (
                    boom is not None and boom > RECONNECT_OUTPUT + 0.01
                ):
                    apply_coreaudio(levels, muted=False)
                self.prev_xlr_vol = RECONNECT_OUTPUT
                self.prev_boom_vol = RECONNECT_OUTPUT
            else:
                if xlr_id is not None:
                    ensure_xlr_input_hot(xlr_id)
                clamped = self._detect_unexpected_jump(ca_snap)
                if not clamped:
                    self._learn(ca_snap, wl_snap)
                    # Accept gradual moves (< +10%) as the new baseline.
                    if ca_snap["xlr_ca"] is not None:
                        self.prev_xlr_vol = ca_snap["xlr_ca"]
                    if ca_snap["boom_ca"] is not None:
                        self.prev_boom_vol = ca_snap["boom_ca"]
            self.prev_xlr_id = xlr_id

    def _wl_loop(self) -> None:
        while True:
            try:
                if self.wl.sock is None:
                    self.wl.connect()
                    log("wave link connected")
                pending = self._pending_wl
                if pending is not None:
                    saved, keep_muted = pending
                    try:
                        self.wl.apply(saved, mute_outputs=True)
                        if not keep_muted:
                            time.sleep(0.05)
                            self.wl.apply(saved, mute_outputs=False)
                        if self._pending_wl == pending:
                            self._pending_wl = None
                    except Exception as exc:
                        log(f"wave link restore failed: {exc}")
                        self.wl.close()
                        time.sleep(0.4)
                        continue
                self.wl_snap = self.wl.snapshot()
                time.sleep(WL_S)
            except Exception:
                self.wl.close()
                self.wl_snap = None
                time.sleep(1.0)

    def run(self) -> None:
        log("audio-protect listener started")
        threading.Thread(target=self._wl_loop, name="wavelink", daemon=True).start()
        self._install_listeners(None)
        while True:
            try:
                self.tick(self.wl_snap)
            except Exception as exc:
                log(f"tick error: {exc}")
            self._wakeup.wait(POLL_S)
            self._wakeup.clear()


def snapshot_current() -> dict:
    state = load_state()
    saved = state["saved"]
    ca_snap = coreaudio_snapshot()
    wl = WaveLink()
    wl_snap = {}
    try:
        wl.connect()
        wl_snap = wl.snapshot()
    except Exception as exc:
        log(f"wave link snapshot skipped: {exc}")
    finally:
        wl.close()
    if ca_snap["xlr_ca"] is not None:
        saved["xlr_ca"] = clamp01(ca_snap["xlr_ca"])
    if ca_snap["boom_ca"] is not None:
        saved["boom_ca"] = clamp01(ca_snap["boom_ca"])
    if wl_snap.get("mic_gain") is not None:
        saved["mic_gain"] = clamp01(wl_snap["mic_gain"])
    if wl_snap.get("boom_level") is not None:
        saved["boom_level"] = clamp01(wl_snap["boom_level"])
    if wl_snap.get("xlr_hp") is not None:
        saved["xlr_hp"] = clamp01(wl_snap["xlr_hp"])
    saved["updated_at"] = now_iso()
    save_state(state)
    return state


def cmd_status() -> int:
    state = load_state()
    ca_snap = coreaudio_snapshot()
    wl = WaveLink()
    wl_snap = {}
    try:
        wl.connect()
        wl_snap = wl.snapshot()
    except Exception as exc:
        wl_snap = {"error": str(exc)}
    finally:
        wl.close()
    out = {
        "hold_mute": holding(),
        "reconnect_output": RECONNECT_OUTPUT,
        "jump_threshold": JUMP_THRESHOLD,
        "jump_cooldown_s": JUMP_COOLDOWN_S,
        "saved": state["saved"],
        "coreaudio": ca_snap,
        "wavelink": wl_snap,
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_save() -> int:
    state = snapshot_current()
    log(f"saved preset {state['saved']}")
    print(json.dumps(state["saved"], indent=2))
    return 0


def cmd_hold_mute() -> int:
    set_hold(True)
    mute_outputs_now()
    levels = reconnect_levels(load_state()["saved"])
    apply_coreaudio(levels, muted=True)
    wl = WaveLink()
    try:
        wl.connect()
        wl.apply(levels, mute_outputs=True)
    except Exception as exc:
        log(f"wave link hold-mute skipped: {exc}")
    finally:
        wl.close()
    log("hold-mute on")
    return 0


def cmd_restore() -> int:
    set_hold(False)
    levels = reconnect_levels(load_state()["saved"])
    apply_coreaudio(levels, muted=True)
    wl = WaveLink()
    try:
        wl.connect()
        wl.apply(levels, mute_outputs=True)
        time.sleep(0.05)
        wl.apply(levels, mute_outputs=False)
    except Exception as exc:
        log(f"wave link restore skipped: {exc}")
    finally:
        wl.close()
    apply_coreaudio(levels, muted=False)
    log(f"hold-mute off; outputs set to {RECONNECT_OUTPUT:.0%}")
    return 0


def cmd_run() -> int:
    Protector().run()
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd in ("-h", "--help", "help"):
        print(
            "audio-protect [run|save|status|hold-mute|restore]\n"
            "  run         background listener (default)\n"
            "  save        store current mic gain (outputs are not clamped)\n"
            "  status      show saved vs live levels\n"
            "  hold-mute   mute outputs until restore (used before USB reset)\n"
            "  restore     set outputs to 20% and unmute (after USB reset)\n"
            "\n"
            "Listener also clamps unexpected CoreAudio output jumps of +10%\n"
            "or more back to 20% (gradual knob moves are left alone)."
        )
        return 0
    cmds = {
        "run": cmd_run,
        "save": cmd_save,
        "status": cmd_status,
        "hold-mute": cmd_hold_mute,
        "restore": cmd_restore,
        "mute": cmd_hold_mute,
    }
    if cmd not in cmds:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return cmds[cmd]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
