$shell = New-Object -ComObject WScript.Shell
$paths = @(
    "$env:USERPROFILE\OneDrive\Desktop\Voice Flow.lnk",
    "$env:USERPROFILE\Desktop\Voice Flow.lnk"
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        $sc = $shell.CreateShortcut($p)
        Write-Host "Path: $p"
        Write-Host "Target: $($sc.TargetPath)"
        Write-Host "WorkDir: $($sc.WorkingDirectory)"
        Write-Host "Icon: $($sc.IconLocation)"
        Write-Host "---"
    } else {
        Write-Host "NOT FOUND: $p"
    }
}
