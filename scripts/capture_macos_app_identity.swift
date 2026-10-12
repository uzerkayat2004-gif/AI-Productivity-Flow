// Native metadata only: no Accessibility queries, permission requests or GUI.
import AppKit
import CoreGraphics
import Foundation

if CommandLine.arguments.count != 2 {
    FileHandle.standardError.write(Data("Expected APP_PATH\n".utf8))
    exit(2)
}
let appPath = URL(fileURLWithPath: CommandLine.arguments[1]).resolvingSymlinksInPath().path
let workspace = NSWorkspace.shared
let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let nativeWindows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    FileHandle.standardError.write(Data("Native window inventory unavailable\n".utf8))
    exit(1)
}
var applications: [[String: Any]] = []
for app in workspace.runningApplications {
    guard let executable = app.executableURL?.path else { continue }
    let pid = Int(app.processIdentifier)
    var titles: [String] = []
    var windows: [[String: Any]] = []
    if executable.hasPrefix(appPath + "/") {
        for window in nativeWindows {
            guard let owner = (window[kCGWindowOwnerPID as String] as? NSNumber)?.intValue, owner == pid else { continue }
            guard let bounds = window[kCGWindowBounds as String] as? [String: Any],
                  let number = (window[kCGWindowNumber as String] as? NSNumber)?.intValue,
                  let layer = (window[kCGWindowLayer as String] as? NSNumber)?.intValue,
                  let alpha = (window[kCGWindowAlpha as String] as? NSNumber)?.doubleValue,
                  let width = (bounds["Width"] as? NSNumber)?.doubleValue,
                  let height = (bounds["Height"] as? NSNumber)?.doubleValue else { continue }
            // IsOnscreen is optional; the inventory explicitly requests only
            // onscreen windows. Honor the field when supplied by Window Server.
            let visible = (window[kCGWindowIsOnscreen as String] as? NSNumber)?.boolValue ?? true
            // macOS can withhold titles without Screen Recording permission.
            // Retain OS window IDs, ownership and geometry; never invent titles.
            let title = window[kCGWindowName as String] as? String ?? ""
            if !title.isEmpty { titles.append(title) }
            windows.append(["windowNumber": number, "ownerPid": owner, "layer": layer,
                            "onScreen": visible, "alpha": alpha, "width": width,
                            "height": height, "title": title])
        }
    }
    applications.append(["pid": pid, "localizedName": app.localizedName ?? "",
                         "bundleIdentifier": app.bundleIdentifier ?? "",
                         "executablePath": executable, "activationPolicy": app.activationPolicy.rawValue,
                         "windows": titles, "windowMetadata": windows])
}
let front = workspace.frontmostApplication
let report: [String: Any] = ["captureSource": "CGWindowList", "appPath": appPath,
                            "frontmost": ["pid": Int(front?.processIdentifier ?? 0),
                                          "localizedName": front?.localizedName ?? ""],
                            "applications": applications]
do {
    let output = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
    FileHandle.standardOutput.write(output)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    FileHandle.standardError.write(Data("Native identity serialization failed\n".utf8))
    exit(1)
}
