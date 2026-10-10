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
default:
    exit(2)
}
