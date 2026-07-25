Add-Type -AssemblyName System.Speech

Write-Output "Installed speech recognizers:"
$recognizers = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
if ($recognizers.Count -eq 0) {
    Write-Output "  NONE FOUND - you need to install a speech recognition language pack"
    Write-Output ""
    Write-Output "To install: Settings > Time and Language > Speech > Add languages"
} else {
    foreach ($r in $recognizers) {
        Write-Output "  ID: $($r.Id)"
        Write-Output "  Culture: $($r.Culture)"
        Write-Output "  Description: $($r.Description)"
        Write-Output "  ---"
    }
}

# Also try creating with default (no culture specified)
Write-Output ""
Write-Output "Trying default recognizer (no culture)..."
try {
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    Write-Output "  Default recognizer works!"
    Write-Output "  AudioFormat: $($engine.AudioFormat)"
    $engine.Dispose()
} catch {
    Write-Output "  Default recognizer failed: $($_.Exception.Message)"
}
