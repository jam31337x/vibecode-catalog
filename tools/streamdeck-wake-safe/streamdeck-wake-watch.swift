import AppKit
import Foundation

/// Restarts Elgato Stream Deck after display/system wake or screen unlock
/// only when the Stream Deck log shows a failed HID reopen.
final class Watcher: NSObject {
    private var pending: DispatchWorkItem?
    private var retrying = false
    private let settleDelay: TimeInterval = 6
    private let retryDelay: TimeInterval = 12
    private let ownLog: URL
    private let deckLog = NSHomeDirectory() + "/Library/Logs/ElgatoStreamDeck/StreamDeck.log"

    override init() {
        ownLog = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/streamdeck-wake-reset.log")
        super.init()
    }

    func log(_ message: String) {
        let line = "\(Self.stamp()) \(message)\n"
        fputs(line, stderr)
        guard let data = line.data(using: .utf8) else { return }
        if FileManager.default.fileExists(atPath: ownLog.path),
           let handle = try? FileHandle(forWritingTo: ownLog) {
            _ = try? handle.seekToEnd()
            handle.write(data)
            try? handle.close()
        } else {
            try? data.write(to: ownLog)
        }
    }

    func schedule(reason: String) {
        log("event: \(reason) — wait \(Int(settleDelay))s for HID reopen")
        pending?.cancel()
        retrying = false
        let item = DispatchWorkItem { [weak self] in
            self?.evaluate()
        }
        pending = item
        DispatchQueue.main.asyncAfter(deadline: .now() + settleDelay, execute: item)
    }

    func evaluate() {
        guard streamDeckRunning() else {
            log("skip: Stream Deck is not running")
            return
        }
        let tail = recentDeckLog()
        let hidGone = !hidPresent()
        if isStuck(tail) || hidGone {
            log(hidGone
                ? "Stream Deck HID missing — USB power-cycle"
                : "HID reopen failed — USB power-cycle")
            restartDeck()
            if !retrying {
                retrying = true
                DispatchQueue.main.asyncAfter(deadline: .now() + retryDelay) { [weak self] in
                    self?.evaluate()
                }
            }
        } else {
            log("ok: Stream Deck HID looks healthy")
            retrying = false
        }
    }

    func restartDeck() {
        let reset = Process()
        reset.executableURL = URL(fileURLWithPath: "$HOME/.local/bin/streamdeck-reset")
        reset.standardOutput = FileHandle.nullDevice
        try? reset.run()
        reset.waitUntilExit()
        log("streamdeck-reset exit \(reset.terminationStatus)")
    }

    private func streamDeckRunning() -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        p.arguments = ["-x", "Stream Deck"]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
        p.waitUntilExit()
        return p.terminationStatus == 0
    }

    private func recentDeckLog() -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/tail")
        p.arguments = ["-n", "80", deckLog]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        try? p.run()
        p.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8) ?? ""
    }

    private func hidPresent() -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/hidutil")
        p.arguments = ["list"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        try? p.run()
        p.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let text = String(data: data, encoding: .utf8) ?? ""
        return text.contains("Stream Deck Plus")
    }

    private func isStuck(_ text: String) -> Bool {
        for line in text.split(whereSeparator: \.isNewline) {
            if line.contains("Read FW version: FAILED") { return true }
            if line.contains("Problem with connecting HID") { return true }
            if line.contains("SetFullRGB") && line.contains("FAILED") { return true }
        }
        return false
    }

    private static func stamp() -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: Date())
    }
}

let watcher = Watcher()
let args = CommandLine.arguments

if args.contains("--reset-now") {
    watcher.log("manual --reset-now")
    watcher.restartDeck()
    exit(0)
}

_ = NSApplication.shared
NSApp.setActivationPolicy(.prohibited)

let workspace = NSWorkspace.shared.notificationCenter
workspace.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { _ in
    watcher.schedule(reason: "screensDidWake")
}
workspace.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
    watcher.schedule(reason: "systemDidWake")
}

let distributed = DistributedNotificationCenter.default()
distributed.addObserver(forName: Notification.Name("com.apple.screenIsUnlocked"), object: nil, queue: .main) { _ in
    watcher.schedule(reason: "screenIsUnlocked")
}

watcher.log("watcher started pid=\(ProcessInfo.processInfo.processIdentifier)")
RunLoop.main.run()
