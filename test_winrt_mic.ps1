[Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.SpeechRecognition.SpeechRecognitionTopicConstraint, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null

$recognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer

# Add Dictation topic constraint (this activates the exact Win+H dictation model!)
$topicConstraint = New-Object Windows.Media.SpeechRecognition.SpeechRecognitionTopicConstraint([Windows.Media.SpeechRecognition.SpeechRecognitionScenario]::Dictation, "dictation")
$recognizer.Constraints.Add($topicConstraint)

Write-Host "Compiling constraints..."
$op = $recognizer.CompileConstraintsAsync()
while ($op.Status -eq 'Started') { Start-Sleep -Milliseconds 50 }

Write-Host "Starting recognition from microphone... SPEAK NOW for 5 seconds!"

$recognizeOp = $recognizer.RecognizeAsync()
$timeout = [System.Diagnostics.Stopwatch]::StartNew()

while ($recognizeOp.Status -eq 'Started' -and $timeout.ElapsedMilliseconds -lt 5000) {
    Start-Sleep -Milliseconds 100
}

if ($recognizeOp.Status -eq 'Completed') {
    $result = $recognizeOp.GetResults()
    Write-Host "STATUS: $($result.Status)"
    Write-Host "TEXT: '$($result.Text)'"
    Write-Host "CONFIDENCE: $($result.Confidence)"
} else {
    Write-Host "Recognition did not complete in 5s. Status: $($recognizeOp.Status)"
}

$recognizer.Dispose()
