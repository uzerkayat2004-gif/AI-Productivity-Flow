Add-Type -AssemblyName System.Speech

$wavPath = $args[0]
Write-Host "WavPath parameter received: '$wavPath'"

if ([string]::IsNullOrWhiteSpace($wavPath)) {
    Write-Host "ERROR: WavPath is empty!"
    exit 1
}

if (-not (Test-Path -Path $wavPath)) {
    Write-Host "ERROR: File does not exist at '$wavPath'"
    exit 1
}

Write-Host "File exists. Size: $((Get-Item $wavPath).Length) bytes"

try {
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    Write-Host "Engine created."

    $dictGrammar = New-Object System.Speech.Recognition.DictationGrammar
    $recognizer.LoadGrammar($dictGrammar)
    Write-Host "Grammar loaded."

    $fileStream = [System.IO.File]::OpenRead($wavPath)
    Write-Host "FileStream opened. Length: $($fileStream.Length)"

    $recognizer.SetInputToWaveStream($fileStream)
    Write-Host "SetInputToWaveStream succeeded!"

    $results = @()
    while ($true) {
        $res = $recognizer.Recognize()
        if ($null -eq $res) { break }
        Write-Host "Recognized phrase: '$($res.Text)' (Confidence: $($res.Confidence))"
        $results += $res.Text
    }

    $fileStream.Close()
    $fileStream.Dispose()
    $recognizer.Dispose()

    Write-Host "FINAL RESULT: '$($results -join ' ')'"
} catch {
    Write-Host "EXCEPTION: $_"
    Write-Host $_.ScriptStackTrace
}
