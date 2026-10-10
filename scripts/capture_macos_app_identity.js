// Run outside the app: osascript -l JavaScript this-file APP_PATH
ObjC.import('AppKit');

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
        // Accessibility failures must fail capture instead of hiding missing windows.
        var processes = system.applicationProcesses.whose({unixId: pid})();
        if (processes.length) windows = processes[0].windows.name();
        applications.push({
            pid: pid,
            localizedName: app.localizedName ? ObjC.unwrap(app.localizedName) : '',
            bundleIdentifier: app.bundleIdentifier ? ObjC.unwrap(app.bundleIdentifier) : '',
            executablePath: ObjC.unwrap(app.executableURL.path),
            activationPolicy: Number(app.activationPolicy),
            windows: windows
        });
    }
    var front = workspace.frontmostApplication;
    return JSON.stringify({
        appPath: argv[0],
        frontmost: {pid: front ? Number(front.processIdentifier) : 0, localizedName: front ? ObjC.unwrap(front.localizedName) : ''},
        applications: applications
    }, null, 2);
}
