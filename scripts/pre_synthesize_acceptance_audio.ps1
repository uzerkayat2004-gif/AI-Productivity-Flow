Add-Type -AssemblyName System.Speech

$outDir = "$env:TEMP\voice_flow_accp"
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

$cases = @(
    @{ id = "ACCP-F1-001"; text = "transfer five lakh twenty thousand rupees no wait make that five lakh fifty thousand rupees plus eighteen percent gst to the vendor account" },
    @{ id = "ACCP-F1-002"; text = "do not transfer the seventy five hundred dollars until devon confirms invoice 8821 in writing" },
    @{ id = "ACCP-F2-003"; text = "write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5 pm marcus" },
    @{ id = "ACCP-F2-004"; text = "email to all engineering scheduled maintenance window will begin tonight at 2300 utc and conclude by 0100 utc services will experience brief intermittent connectivity" },
    @{ id = "ACCP-F2-005"; text = "urgent ping to on call engineer latency on payment gateway spiked to 2.4 seconds please investigate redis cache health" },
    @{ id = "ACCP-F3-006"; text = "can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format" },
    @{ id = "ACCP-F4-007"; text = "pre flight deployment checklist verify ssl certificates backup production database notify customer success enable feature flag 14" },
    @{ id = "ACCP-F5-008"; text = "the billing refund bug failed qa testing again on wednesday so the issue remains open alex is continuing root cause investigation and release is postponed to monday" },
    @{ id = "ACCP-F6-009"; text = "your app is totally broken and crashed twice when i was saving my work this is unacceptable" },
    @{ id = "ACCP-F7-010"; text = "let us push the launch to friday at eleven thirty am instead" },
    @{ id = "ACCP-F7-011"; text = "make it sprint 43 and add verify rate limiting" },
    @{ id = "ACCP-F8-012"; text = "play some jazz music and order a pizza" }
)

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($c in $cases) {
    $wavPath = Join-Path $outDir "$($c.id).wav"
    $synth.SetOutputToWaveFile($wavPath)
    $synth.Speak($c.text)
    Write-Output "Synthesized $($c.id): $wavPath"
}
$synth.Dispose()
Write-Output "All 12 acceptance audio files successfully pre-synthesized!"
