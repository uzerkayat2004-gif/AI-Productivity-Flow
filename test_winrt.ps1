[Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
$recognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer
Write-Host "WinRT SpeechRecognizer created successfully!"
Write-Host "Language: $($recognizer.CurrentLanguage.LanguageTag)"
$recognizer.Dispose()
