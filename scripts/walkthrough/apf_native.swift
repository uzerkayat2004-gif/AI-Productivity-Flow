// Tiny CI helper for the macOS walkthrough: list windows, move/click the mouse.
// Synthetic events may be ignored when the runner lacks Accessibility trust;
// the walkthrough records whether they had any visible effect.
import AppKit
import CoreGraphics
import Foundation

let args = CommandLine.arguments
func out(_ obj: Any) {
    if let d = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]) {
        FileHandle.standardOutput.write(d); FileHandle.standardOutput.write(Data("\n".utf8))
    }
}
guard args.count >= 2 else { print("usage: windows | move X Y | click X Y | trusted"); exit(2) }
switch args[1] {
case "windows":
    let list = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]) ?? []
    var rows: [[String: Any]] = []
    for w in list {
        let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
        rows.append([
            "owner": w[kCGWindowOwnerName as String] as? String ?? "",
            "pid": (w[kCGWindowOwnerPID as String] as? NSNumber)?.intValue ?? 0,
            "name": w[kCGWindowName as String] as? String ?? "",
            "layer": (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0,
            "alpha": (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 0,
            "x": (b["X"] as? NSNumber)?.doubleValue ?? 0, "y": (b["Y"] as? NSNumber)?.doubleValue ?? 0,
            "w": (b["Width"] as? NSNumber)?.doubleValue ?? 0, "h": (b["Height"] as? NSNumber)?.doubleValue ?? 0,
        ])
    }
    out(rows)
case "screen":
    // Main screen frame and visible frame (minus Dock + menu bar) in top-left coords.
    let screens = NSScreen.screens
    let primaryH = screens.first?.frame.height ?? 0
    if let m = NSScreen.main {
        let f = m.frame, v = m.visibleFrame
        out(["w": f.width, "h": f.height,
             "visibleTop": primaryH - (v.origin.y + v.height), "visibleBottom": primaryH - v.origin.y,
             "visibleLeft": v.origin.x, "visibleRight": v.origin.x + v.width])
    } else { out([:] as [String: Any]) }
case "trusted":
    print(AXIsProcessTrusted() ? "true" : "false")
case "move", "click":
    guard args.count >= 4, let x = Double(args[2]), let y = Double(args[3]) else { exit(2) }
    let p = CGPoint(x: x, y: y)
    CGWarpMouseCursorPosition(p)
    CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
    if args[1] == "click" {
        usleep(80_000)
        CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
        usleep(60_000)
        CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
    }
    print("ok")
case "rclick":
    guard args.count >= 4, let x = Double(args[2]), let y = Double(args[3]) else { exit(2) }
    let p = CGPoint(x: x, y: y)
    CGWarpMouseCursorPosition(p)
    usleep(80_000)
    CGEvent(mouseEventSource: nil, mouseType: .rightMouseDown, mouseCursorPosition: p, mouseButton: .right)?.post(tap: .cghidEventTap)
    usleep(60_000)
    CGEvent(mouseEventSource: nil, mouseType: .rightMouseUp, mouseCursorPosition: p, mouseButton: .right)?.post(tap: .cghidEventTap)
    print("ok")
case "ctrlclick":
    guard args.count >= 4, let x = Double(args[2]), let y = Double(args[3]) else { exit(2) }
    let p = CGPoint(x: x, y: y)
    CGWarpMouseCursorPosition(p)
    usleep(80_000)
    for t in [CGEventType.leftMouseDown, CGEventType.leftMouseUp] {
        if let e = CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left) {
            e.flags = [.maskControl]
            e.post(tap: .cghidEventTap)
        }
        usleep(60_000)
    }
    print("ok")
case "cmdopt":
    // Hold or release Command+Option as real modifier events (the Voice Flow hotkey on Mac).
    guard args.count >= 3 else { exit(2) }
    let src = CGEventSource(stateID: .hidSystemState)
    func flag(_ key: CGKeyCode, _ down: Bool, _ flags: CGEventFlags) {
        if let e = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: down) {
            e.type = .flagsChanged; e.flags = flags; e.post(tap: .cghidEventTap)
        }
    }
    if args[2] == "down" {
        flag(0x37, true, [.maskCommand]); usleep(40_000)
        flag(0x3A, true, [.maskCommand, .maskAlternate])
    } else {
        flag(0x3A, false, [.maskCommand]); usleep(40_000)
        flag(0x37, false, [])
    }
    print("ok")
case "key":
    // key <keycode> [cmd] : press a key, optionally with Command held.
    guard args.count >= 3, let kc = UInt16(args[2]) else { exit(2) }
    let src = CGEventSource(stateID: .hidSystemState)
    let withCmd = args.count >= 4 && args[3] == "cmd"
    for down in [true, false] {
        if let e = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(kc), keyDown: down) {
            if withCmd { e.flags = [.maskCommand] }
            e.post(tap: .cghidEventTap)
        }
        usleep(50_000)
    }
    print("ok")
case "drag":
    guard args.count >= 6, let x1 = Double(args[2]), let y1 = Double(args[3]), let x2 = Double(args[4]), let y2 = Double(args[5]) else { exit(2) }
    let a = CGPoint(x: x1, y: y1), b = CGPoint(x: x2, y: y2)
    CGWarpMouseCursorPosition(a)
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: a, mouseButton: .left)?.post(tap: .cghidEventTap)
    for i in 1...20 {
        let t = Double(i) / 20.0
        let p = CGPoint(x: x1 + (x2 - x1) * t, y: y1 + (y2 - y1) * t)
        CGEvent(mouseEventSource: nil, mouseType: .leftMouseDragged, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
        usleep(25_000)
    }
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: b, mouseButton: .left)?.post(tap: .cghidEventTap)
    print("ok")
case "axtext":
    // axtext <pid>: text of the focused element (or first text area) of an app, via Accessibility.
    guard args.count >= 3, let pid = Int32(args[2]) else { exit(2) }
    let app = AXUIElementCreateApplication(pid)
    var focused: CFTypeRef?
    var value: CFTypeRef?
    if AXUIElementCopyAttributeValue(app, kAXFocusedUIElementAttribute as CFString, &focused) == .success, let f = focused {
        AXUIElementCopyAttributeValue(f as! AXUIElement, kAXValueAttribute as CFString, &value)
    }
    print((value as? String) ?? "<no AX value>")
default:
    exit(2)
}
