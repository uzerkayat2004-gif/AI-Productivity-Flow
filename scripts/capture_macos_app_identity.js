// Run outside the app: osascript -l JavaScript this-file APP_PATH
ObjC.import('AppKit');

function optionalString(value) {
    // ObjC nil can unwrap to undefined; JSON.stringify drops undefined keys.
    var unwrapped = value ? ObjC.unwrap(value) : null;
    return typeof unwrapped === 'string' ? unwrapped : '';
}

function run(argv) {
    if (argv.length !== 1) throw new Error('Expected APP_PATH');
    var system = Application('System Events');
    var workspace = $.NSWorkspace.sharedWorkspace;
    var running = workspace.runningApplications;
    var applications = [];
    for (var i = 0; i < running.count; i++) {
        var app = running.objectAtIndex(i);
        if (!app.executableURL) continue;
        var pid = Number(app.processIdentifier);
        var windows = [];
        var windowMetadata = [];
        // Accessibility failures must fail capture instead of hiding missing windows.
        var processes = system.applicationProcesses.whose({unixId: pid})();
        if (processes.length) {
            windows = processes[0].windows.name();
            var nativeWindows = processes[0].windows();
            for (var j = 0; j < nativeWindows.length; j++) {
                var metadata = {title: windows[j], modal: null};
                try {
                    metadata.role = nativeWindows[j].role();
                    metadata.subrole = nativeWindows[j].subrole();
                    metadata.modal = nativeWindows[j].attributes.byName('AXModal').value();
                } catch (error) {
                    // AXModal is not supported by every system/window provider.
                    metadata.metadataError = String(error);
                }
                windowMetadata.push(metadata);
            }
        }
        applications.push({
            pid: pid,
            localizedName: optionalString(app.localizedName),
            bundleIdentifier: optionalString(app.bundleIdentifier),
            executablePath: ObjC.unwrap(app.executableURL.path),
            activationPolicy: Number(app.activationPolicy),
            windows: windows,
            windowMetadata: windowMetadata
        });
    }
    var front = workspace.frontmostApplication;
    return JSON.stringify({
        appPath: argv[0],
        frontmost: {pid: front ? Number(front.processIdentifier) : 0, localizedName: front ? optionalString(front.localizedName) : ''},
        applications: applications
    }, null, 2);
}
