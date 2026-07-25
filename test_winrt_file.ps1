[Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null

$wavPath = $args[0]
if (-not $wavPath) {
    Write-Host "No wav file provided."
    exit 1
}

$recognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer
$asyncOperation = $recognizer.CompileConstraintsAsync()
while ($asyncOperation.Status -eq 'Started') { Start-Sleep -Milliseconds 50 }

Write-Host "Recognizer compiled constraint."

# Check available methods on SpeechRecognizer
$recognizer | Get-Member
$recognizer.Dispose()
