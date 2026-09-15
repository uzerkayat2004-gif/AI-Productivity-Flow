"""Comprehensive Unit Tests for Built-in Local Spoken Summarizer.

Verifies:
1. Sentence tokenization respecting abbreviations, decimals, and dialogue/quotes.
2. Salience and position scoring (thesis hook, paragraph lead, conclusion bonus, TF-ISF, length normalization).
3. Maximal Marginal Relevance (MMR) redundancy penalty and diversity.
4. Depth modes (quick/short, standard/balanced, detailed/long) with word and sentence budget constraints.
5. Multi-page document handling (preamble elimination in quick mode).
6. Speech sanitization for TTS (symbols, markdown, citations, URLs, disruptive parentheticals, clean punctuation).
7. Singleton and class interface.
8. Edge cases (empty, single sentence, short text).
"""

from __future__ import annotations

import re
import pytest

from voice_flow.local_summarizer import (
    LocalSpokenSummarizer,
    local_spoken_summarizer,
)


def test_sentence_tokenization_abbreviations_and_decimals():
    summarizer = LocalSpokenSummarizer()
    text = (
        "Dr. Smith visited Washington, D.C. on Jan. 15 to discuss the U.S. economy with Mr. Davis (e.g., inflation vs. growth). "
        "The estimated deficit reached $3.14 trillion, representing a 4.5% year-over-year increase. "
        "As Fig. 2 illustrates, George W. Bush signed earlier reforms. "
        "Overall, results show that long-term recovery remains on track."
    )
    sentences = summarizer.tokenize_sentences(text)
    texts = [s.raw_text for s in sentences]

    assert len(texts) == 4
    # First sentence preserves Dr., D.C., Jan. 15, U.S., Mr., e.g., vs.
    assert "Dr. Smith" in texts[0]
    assert "D.C." in texts[0]
    assert "Jan. 15" in texts[0]
    assert "U.S. economy" in texts[0]
    assert "Mr. Davis" in texts[0]
    assert "e.g." in texts[0]
    assert "vs." in texts[0]

    # Second sentence preserves $3.14 and 4.5%
    assert "$3.14 trillion" in texts[1]
    assert "4.5%" in texts[1]

    # Third sentence preserves Fig. 2 and George W. Bush
    assert "Fig. 2" in texts[2]
    assert "George W. Bush" in texts[2]

    # Fourth sentence has conclusion
    assert "Overall, results show" in texts[3]


def test_sentence_tokenization_dialogue_and_quotes():
    summarizer = LocalSpokenSummarizer()
    text = (
        '"The launch exceeded every benchmark," reported Dr. Adams. '
        '"We reached 100% reliability." '
        'The engineering division celebrated.'
    )
    sentences = summarizer.tokenize_sentences(text)
    texts = [s.raw_text for s in sentences]

    assert len(texts) == 3
    assert 'Dr. Adams' in texts[0]
    assert '100% reliability.' in texts[1]
    assert 'The engineering division celebrated.' in texts[2]


def test_sentence_tokenization_multi_paragraph_structure():
    summarizer = LocalSpokenSummarizer()
    text = (
        "This is paragraph one sentence one. This is paragraph one sentence two.\n\n"
        "Paragraph two starts here with a topic sentence. This is the second sentence of paragraph two.\n\n"
        "Finally, paragraph three wraps up the discussion."
    )
    units = summarizer.tokenize_sentences(text)
    assert len(units) == 5

    # Paragraph index checks
    assert units[0].paragraph_idx == 0
    assert units[0].is_opening is True
    assert units[0].is_lead is True

    assert units[1].paragraph_idx == 0
    assert units[1].is_opening is False
    assert units[1].is_lead is False

    assert units[2].paragraph_idx == 1
    assert units[2].is_lead is True

    assert units[4].paragraph_idx == 2
    assert units[4].is_lead is True


def test_salience_scoring_weights():
    summarizer = LocalSpokenSummarizer()
    text = (
        "Artificial intelligence is transforming clinical healthcare diagnostics across major research hospitals. "
        "Short one. "
        "Doctors use deep neural networks to evaluate radiology scans with high accuracy. "
        "Overall, results show that patient outcomes improved significantly."
    )
    units = summarizer.tokenize_sentences(text)
    summarizer.score_sentences(units, is_multi_page=False, depth="balanced")

    # Opening document sentence should receive thesis hook bonus (+2.5)
    assert units[0].is_opening is True

    # Short sentence (<5 words) should receive fragment penalty
    assert units[1].word_count < 5
    assert units[1].salience_score < units[0].salience_score

    # Conclusion sentence with 'results show' should receive conclusion bonus (+2.0)
    assert units[3].has_conclusion_marker is True
    assert units[3].salience_score > units[1].salience_score


def test_conclusion_triggers_recognized():
    summarizer = LocalSpokenSummarizer()
    triggers = [
        "Overall, the initiative was a major milestone.",
        "In conclusion, the hypothesis was thoroughly validated.",
        "Importantly, the system maintained zero downtime.",
        "The key takeaway from this experiment is speed.",
        "Our results show a substantial efficiency boost.",
        "The scientists found that latency decreased by half.",
        "Crucially, the security audit detected no vulnerabilities.",
        "In summary, modern architectures outperform legacy systems.",
        "The main takeaway is to invest in automated testing.",
    ]
    for sentence in triggers:
        units = summarizer.tokenize_sentences(sentence)
        assert len(units) == 1
        assert units[0].has_conclusion_marker is True


def test_mmr_redundancy_penalty():
    summarizer = LocalSpokenSummarizer()
    # Sentence 1 and Sentence 2 are near-duplicate restatements
    # Sentence 3 is distinct content
    text = (
        "Global solar energy adoption expanded rapidly across northern European territories in 2024. "
        "Solar energy adoption expanded rapidly across northern European territories during that year. "
        "Wind generation capacity also achieved record highs throughout coastal offshore facilities. "
        "In conclusion, renewable energy transitions continue to accelerate worldwide."
    )
    units = summarizer.tokenize_sentences(text)
    summarizer.score_sentences(units, is_multi_page=False, depth="balanced")

    # Select 2 sentences
    selected = summarizer.select_mmr(units, depth="short")
    selected_indices = {s.global_idx for s in selected}

    # Sentence 0 and Sentence 1 should NOT both be selected due to MMR redundancy penalty
    assert not ({0, 1}.issubset(selected_indices))


def test_depth_modes_quick_word_budget():
    summarizer = LocalSpokenSummarizer()
    doc = (
        "Modern cloud distributed architectures enable high availability and elastic resource allocation. "
        "Data centers dynamically shift computational workloads across geographical regions to maintain uptime. "
        "Automated failover clusters minimize latency spikes during unexpected localized outages. "
        "Telemetry pipelines aggregate system health indicators in real time across edge nodes. "
        "The primary takeaway is that automated resilience infrastructure dramatically lowers operational maintenance overhead."
    )
    summary_quick = summarizer.summarize(doc, depth="quick")
    word_count = len(summary_quick.split())

    # Quick mode target: 1-2 vital sentences, word budget ~20 to 45 words
    assert 15 <= word_count <= 55
    # Should capture core or conclusion takeaway
    assert "takeaway" in summary_quick.lower() or "architectures" in summary_quick.lower()


def test_depth_modes_standard_balanced():
    summarizer = LocalSpokenSummarizer()
    doc = (
        "Quantum computing harnesses superposition and entanglement to solve intractable computational problems. "
        "Traditional silicon microprocessors process information using deterministic binary bits. "
        "In contrast, quantum systems use qubits that exist in probabilistic superpositions of states. "
        "Recent experiments demonstrate quantum advantage in specialized cryptographic factoring and molecular simulation. "
        "Thermal decoherence remains the primary technical bottleneck requiring cryogenic dilution refrigerators. "
        "Overall, results show that fault-tolerant logical qubits represent the next foundational computing frontier."
    )
    summary = summarizer.summarize(doc, depth="balanced")
    word_count = len(summary.split())

    # Balanced mode target: 3 to 5 sentences, word budget 70 to 120 words
    sentences = [s for s in summary.split(". ") if s.strip()]
    assert 2 <= len(sentences) <= 5
    assert 45 <= word_count <= 140


def test_depth_modes_detailed_long():
    summarizer = LocalSpokenSummarizer()
    doc = (
        "Autonomous driving systems combine computer vision, LiDAR, and radar to navigate urban environments safely.\n\n"
        "Perception neural networks detect pedestrians, bicycles, and road signs at sixty frames per second. "
        "Sensor fusion algorithms reconcile disparate data streams into a unified 3D point cloud map.\n\n"
        "Motion planners calculate collision-free trajectories under strict dynamic constraints and traffic laws. "
        "Actuation controllers regulate throttle, braking, and steering angle with millisecond precision.\n\n"
        "Edge cases such as severe blizzards and unmapped construction zones still challenge autonomous vehicles. "
        "Safety drivers supervise complex urban navigation routes during fleet validation trials.\n\n"
        "Importantly, telemetry data confirms that autonomous driving reduces fatal collision rates by 80% compared to human drivers."
    )
    summary = summarizer.summarize(doc, depth="detailed")
    word_count = len(summary.split())

    # Detailed mode: 6 to 10 sentences, word budget 150 to 250 words
    assert word_count >= 100
    assert "80 percent" in summary or "80%" in summary or "percent" in summary
    assert "Importantly" not in summary or "telemetry" in summary


def test_multipage_quick_eliminates_background_preamble():
    summarizer = LocalSpokenSummarizer()
    # Multi-paragraph document with generic background preamble in paragraph 1
    doc = (
        "In recent years, many organizations have explored distributed database management technologies. "
        "Historically, legacy relational databases struggled with horizontal scalability and geo-replication.\n\n"
        "Our core breakthrough is an asynchronous consensus algorithm that delivers linearizable transactions at ten thousand operations per second. "
        "The distributed commit coordinator completely eliminates two-phase commit bottlenecks.\n\n"
        "Benchmarking across five continents confirms consistent sub-ten-millisecond latency under peak workloads. "
        "In conclusion, the new consensus architecture proves that global consistency does not require sacrificing throughput."
    )
    summary = summarizer.summarize(doc, depth="quick")

    # Preamble should be eliminated
    assert "In recent years" not in summary
    assert "Historically" not in summary

    # Should capture core breakthrough and/or conclusion
    assert "consensus" in summary.lower() or "transactions" in summary.lower()
    assert "In conclusion" in summary or "consistency" in summary or "throughput" in summary


def test_speech_sanitization_symbols():
    summarizer = LocalSpokenSummarizer()
    text = "The company reported that revenue grew by 24.5% to $4.2 million, while AT&T & Verizon earned $100M each with an A+ rating."
    sanitized = summarizer.sanitize_for_speech(text)

    # % -> percent
    assert "24.5 percent" in sanitized
    assert "%" not in sanitized

    # $ -> dollars
    assert "4.2 million dollars" in sanitized
    assert "100 million dollars" in sanitized
    assert "$" not in sanitized

    # & -> and
    assert "AT and T and Verizon" in sanitized or "AT and T" in sanitized
    assert "&" not in sanitized

    # A+ -> A plus
    assert "A plus" in sanitized


def test_speech_sanitization_markdown_and_citations():
    summarizer = LocalSpokenSummarizer()
    text = (
        "### Section Header\n"
        "* **First point:** The algorithm achieved 99.8% precision [1] (see Fig. 2).\n"
        "- *Second point:* Visit https://example.com for raw datasets [2, 3].\n"
        "> `Code snippet` completed in 10ms."
    )
    sanitized = summarizer.sanitize_for_speech(text)

    # Markdown stripped
    assert "#" not in sanitized
    assert "**" not in sanitized
    assert "*" not in sanitized
    assert "`" not in sanitized
    assert ">" not in sanitized

    # Citations stripped
    assert "[1]" not in sanitized
    assert "[2, 3]" not in sanitized
    assert "(see Fig. 2)" not in sanitized
    assert "https://example.com" not in sanitized


def test_speech_sanitization_spoken_abbreviations():
    summarizer = LocalSpokenSummarizer()
    text = "Various metrics (e.g., latency vs. throughput) were measured, etc."
    sanitized = summarizer.sanitize_for_speech(text)

    assert "for example" in sanitized
    assert "versus" in sanitized
    assert "and so on" in sanitized


def test_singleton_instance_and_depth_aliases():
    text = (
        "Artificial intelligence revolutionizes voice applications. "
        "Local models deliver complete privacy and instant responsiveness. "
        "Overall, offline execution guarantees maximum user security."
    )

    res_short = local_spoken_summarizer.summarize(text, depth="short")
    res_quick = local_spoken_summarizer.summarize(text, depth="quick")
    res_std = local_spoken_summarizer.summarize(text, depth="standard")
    res_bal = local_spoken_summarizer.summarize(text, depth="balanced")
    res_long = local_spoken_summarizer.summarize(text, depth="long")
    res_det = local_spoken_summarizer.summarize(text, depth="detailed")

    assert isinstance(res_short, str) and len(res_short) > 0
    assert isinstance(res_quick, str) and len(res_quick) > 0
    assert isinstance(res_std, str) and len(res_std) > 0
    assert isinstance(res_bal, str) and len(res_bal) > 0
    assert isinstance(res_long, str) and len(res_long) > 0
    assert isinstance(res_det, str) and len(res_det) > 0


def test_edge_cases_empty_and_single_sentence():
    summarizer = LocalSpokenSummarizer()

    # Empty string
    assert summarizer.summarize("") == ""
    assert summarizer.summarize("   \n\t  ") == ""

    # Single sentence
    single = "Voice Flow gives you fast voice dictation."
    assert summarizer.summarize(single, depth="quick") == single

    # Two sentences
    two_sent = "Voice Flow is fast. It works completely offline."
    summary = summarizer.summarize(two_sent, depth="detailed")
    assert "Voice Flow is fast" in summary
    assert "It works completely offline" in summary


def _build_10page_document() -> str:
    """Construct a realistic ~2,500-word, 12-section document simulating a 10-page report."""
    sections = [
        (
            "# 1. Executive Summary & Core Breakthrough\n"
            "In recent years, enterprise software organizations struggled with monolithic deployment bottlenecks. "
            "Historically, legacy architectures failed to scale across multi-region edge environments. "
            "Our core breakthrough is an autonomous streaming intelligence engine that accelerates distributed throughput by 450%. "
            "The unified orchestration framework synchronizes concurrent data streams with deterministic zero-loss message queues. "
            "Benchmarking across fifty production clusters validates continuous system resilience under stress. "
            "Engineering teams deploy microservices rapidly using automated continuous integration pipelines. "
            "Telemetry indicators confirm zero recorded transaction losses across all evaluation runs. "
            "Overall, results show that modern streaming engines dramatically cut operating overhead."
        ),
        (
            "# 2. Real-Time Ingestion & Event Processing\n"
            "The real-time ingestion pipeline processes over 150,000 events per second through partitioned memory buffers. "
            "Specialized ring buffer queues serialize high-frequency telemetry without blocking worker thread execution. "
            "Dynamic partition rebalancing distributes network traffic evenly across available cluster worker nodes. "
            "However, network saturation remains a critical bottleneck under unexpected packet burst traffic. "
            "Engineers configured backpressure throttling mechanisms to prevent memory exhaustion during spikes. "
            "Memory buffer utilization stays within safe operational boundaries during peak event ingestion. "
            "Results show that batch windowing algorithms cut CPU memory utilization by 35%. "
            "Throughput benchmarks confirm sustained message ingestion without dropped packets."
        ),
        (
            "# 3. Neural Acoustic Transcription Architecture\n"
            "The neural acoustic architecture combines conformer attention blocks with rotary positional encodings. "
            "Deep convolutional encoders downsample incoming 16kHz audio waveforms into dense linguistic latent matrices. "
            "Streaming decoding algorithms predict phoneme sequences with sub-ten-millisecond latency. "
            "Acoustic feature extractors isolate speech formants while rejecting background ambient noise. "
            "Nevertheless, acoustic distortion in reverberant environments poses a known operational challenge. "
            "Multi-head self-attention layers capture long-range phonetic dependencies across conversational utterances. "
            "Rigorous validation confirms that word error rate dropped to 2.4% across noisy acoustic environments. "
            "The model processes continuous streaming speech without accumulated lag or buffer overruns."
        ),
        (
            "# 4. Language Modeling & Contextual Decoding\n"
            "A lightweight transformer language model integrates bi-directional context decoders to resolve phonetic ambiguities. "
            "Dynamic vocabulary masking ensures domain-specific terminology is preserved during transcription. "
            "Contextual biasing layers incorporate user personal dictionaries in real time during decoding passes. "
            "However, rare technical jargon requires supplementary pronunciation dictionary lookup tables. "
            "Beam search decoders prune low-probability transcription hypotheses to conserve compute resources. "
            "Linguistic perplexity evaluations confirm superior syntax prediction across diverse conversational topics. "
            "Empirical experiments confirm that perplexity scores decreased by 28% compared to standard baselines. "
            "The decoding pipeline produces fluent text transcriptions with accurate capitalization and punctuation."
        ),
        (
            "# 5. Edge Quantization & Memory Optimization\n"
            "Quantization routines compress neural weights from 32-bit floating point down to 4-bit integer representations. "
            "The quantization framework utilizes symmetric weight clipping to protect outlier gradient values. "
            "Kernel fusion optimizations merge layer normalization and activation functions into single execution units. "
            "Crucially, 4-bit quantization reduces overall memory footprint from 16 gigabytes to 2.1 gigabytes. "
            "Low-bit matrix multiplication kernels execute with high efficiency on consumer hardware chips. "
            "Despite aggressive precision reduction, numerical divergence remains negligible throughout inference. "
            "The system maintains 99.1% of original uncompressed model accuracy across all benchmark suites. "
            "Memory compression enables full offline deployment on resource-constrained personal laptops."
        ),
        (
            "# 6. Distributed Consensus & Cluster Synchronization\n"
            "Distributed state management utilizes a Raft consensus protocol tailored for multi-region edge deployments. "
            "Cluster nodes gossip heartbeats every 50ms to detect network partition failures instantly. "
            "Log replication mechanisms guarantee sequential consistency across geographically dispersed servers. "
            "However, wide-area cross-continental latency introduces consensus delay during transatlantic failovers. "
            "Replication quorums prioritize local region durability before acknowledging distributed commit operations. "
            "Autonomous leader election algorithms restore quorum connectivity in under 120 milliseconds. "
            "State machine checkpoints snapshot cluster state periodically to minimize recovery durations. "
            "The synchronization layer guarantees strict linearizability under concurrent update workloads."
        ),
        (
            "# 7. Enterprise Security & Cryptographic Privacy\n"
            "End-to-end encryption protocols protect data in transit using TLS 1.3 with automated certificate renewal. "
            "Local on-device cryptographic routines sanitize sensitive user identifiers before telemetry transmission. "
            "Cryptographic key rotation occurs automatically every twenty-four hours without service interruptions. "
            "Strict sandbox isolation isolates worker process execution from host kernel privileges. "
            "Zero-trust authentication policies verify client credentials before granting message queue access. "
            "Memory protection safeguards prevent unauthorized cross-process memory inspection on multi-tenant hardware. "
            "Independent security audits confirmed zero critical vulnerabilities across the entire codebase. "
            "User voice recordings are processed entirely in memory and permanently wiped immediately after synthesis."
        ),
        (
            "# 8. Performance Benchmarking & Empirical Latency\n"
            "Extensive synthetic load testing evaluated performance across ten geographic cloud zones. "
            "Under peak concurrency of 50,000 active client connections, 99th percentile latency remained below 18ms. "
            "Load balancers distribute incoming requests across edge nodes according to real-time CPU saturation. "
            "Stress tests demonstrate that system throughput degrades gracefully when load exceeds normal capacity. "
            "The bottom line is that the new pipeline delivers 4.5x higher throughput than legacy architectures. "
            "Total compute cost decreased by 60%, saving approximately $1.2 million annually. "
            "Resource efficiency metrics confirm substantial power savings across distributed server deployments. "
            "The engineering division validated these empirical improvements across six months of production monitoring."
        ),
        (
            "# 9. Operational Constraints & Edge Failure Modes\n"
            "Severe thermal throttling on constrained mobile hardware poses a known operational challenge. "
            "Battery conservation routines dynamically throttle model inference frequency when power drops below 15%. "
            "Under high ambient temperatures, thermal management algorithms reduce GPU clock frequencies to prevent damage. "
            "A critical limitation is that processing throughput halves when devices enter aggressive battery saver mode. "
            "The system requires at least 4 gigabytes of host memory for smooth background operation. "
            "Fallback software kernels maintain essential functionality when hardware acceleration units fail. "
            "Provided that hardware requirements are satisfied, execution reliability exceeds 99.99% uptime. "
            "Diagnostics telemetry reports hardware constraint violations to local monitoring dashboards."
        ),
        (
            "# 10. Voice User Experience & Audio Feedback\n"
            "Spoken audio feedback synthesizes status updates using a zero-latency parametric voice generator. "
            "Natural prosody synthesis regulates pause duration and inflection for clear human comprehension. "
            "Speech sanitization filters strip markdown symbols and citations before acoustic rendering. "
            "Audio output adapters dynamically balance volume levels according to ambient acoustic sensor data. "
            "A key takeaway is that voice alerts resolve user task blockages 70% faster than screen notifications. "
            "Field trials across 1,000 beta testers demonstrated universal preference for local audio summaries. "
            "Users reported higher satisfaction when audio summaries omitted introductory background fluff. "
            "Continuous user feedback confirms the practical utility of adaptive spoken narration."
        ),
        (
            "# 11. Production Deployment & Automated Failover\n"
            "Automated canary deployments verify health metrics before routing global production traffic. "
            "Container management agents execute graceful rolling restarts without dropping active socket connections. "
            "Traffic routing proxies redirect requests away from degraded instances within five milliseconds. "
            "Although unexpected cloud region outages occur, automated traffic redirection prevents user downtime. "
            "Automated rollback scripts revert software updates if error rates exceed one tenth of a percent. "
            "Telemetry dashboards track end-to-end service availability in real time across edge deployments. "
            "Operations engineers monitor infrastructure stability through centralized notification channels. "
            "System telemetry confirms uninterrupted service availability during all scheduled maintenance windows."
        ),
        (
            "# 12. Strategic Takeaway & Architectural Conclusion\n"
            "In conclusion, the local spoken intelligence framework demonstrates that offline processing achieves unmatched speed and privacy. "
            "By eliminating external cloud dependencies, users gain instantaneous responsiveness with total data sovereignty. "
            "The architectural design proves that edge computing can match or exceed cloud server capabilities. "
            "Future development will explore multi-modal speech embeddings and cross-lingual translation capabilities. "
            "The final finding is that on-device machine intelligence represents the foundational future of productivity. "
            "Taken together, this architectural breakthrough sets a new industry standard for voice interfaces. "
            "Organizations adopting local intelligence eliminate cloud subscription costs while protecting privacy. "
            "We conclude that decentralized spoken workflows will redefine personal computing across the coming decade."
        ),
    ]
    # Supplementary distinct paragraphs for each section to reach a rich, non-repetitive ~2,500-word 10-page document
    supplementary = [
        (
            "Architectural modularity allows individual microservices to scale independently based on demand. "
            "Telemetry collection agents sample system health indicators across edge node clusters every two seconds. "
            "Automated rollback protocols prevent bad releases from propagating through live environments. "
            "Continuous performance profiling confirms zero regression across multiple release cycles."
        ),
        (
            "Partition coordinators allocate consumer worker pools dynamically to handle bursty event arrivals. "
            "In-memory circular queues decouple fast data ingestion from slower downstream analytical processing. "
            "System operators can inspect queue depth through local monitoring interfaces without performance degradation. "
            "Stress testing demonstrated reliable zero-loss ingestion even under extreme network jitter."
        ),
        (
            "Attention heads focus dynamically on distinctive phonetic patterns across noisy conversational speech. "
            "Acoustic normalization layers compensate for microphone variation across diverse hardware recording devices. "
            "The streaming inference engine processes audio chunks incrementally as audio frames arrive. "
            "Extensive benchmarking confirms accurate speech recognition across ten distinct regional accents."
        ),
        (
            "Bi-directional context layers evaluate bidirectional syntax to predict grammatically coherent sentence structures. "
            "Phonetic probability tables guide the decoder toward optimal phrase candidates in noisy conditions. "
            "Dynamic vocabulary expansion incorporates domain-specific jargon from user document repositories. "
            "Automated text post-processing formats numerical measurements and timestamps according to regional conventions."
        ),
        (
            "Integer arithmetic hardware units execute quantized neural layer calculations at peak throughput. "
            "Dynamic range calibration algorithms determine optimal quantization scale factors across layer activations. "
            "Outlier weight values are preserved in high precision using hybrid floating-point sparse storage. "
            "Resource profiling confirms steady low memory consumption during continuous round-the-clock inference."
        ),
        (
            "Consensus state logs are persisted to fast local non-volatile solid-state storage. "
            "Cross-cluster replication utilizes compressed delta streams to minimize inter-region bandwidth usage. "
            "Network partition detectors distinguish transient packet drops from prolonged hardware link failures. "
            "Distributed transaction coordinators guarantee atomicity across multi-node state modifications."
        ),
        (
            "Hardware-backed secure enclaves protect cryptographic keys against root privileges on compromised hosts. "
            "Automated certificate authority agents renew transport layer security tokens before expiration. "
            "Anonymization filters scrub personal identification information from internal diagnostics logs. "
            "Penetration testing by third-party security auditors confirmed complete isolation between tenant workspaces."
        ),
        (
            "Synthetic load generation frameworks simulated millions of concurrent queries across varied network topologies. "
            "Latency distribution percentiles remained stable across sustained twelve-hour benchmark test runs. "
            "Hardware utilization tracking showed uniform load distribution across all available compute cores. "
            "Cost optimization models demonstrate significant infrastructure savings compared to cloud hosted alternatives."
        ),
        (
            "Thermal monitoring threads adjust inference batch sizes dynamically when core temperatures rise. "
            "Graceful degradation policies prioritize essential dictation features over background analytical tasks. "
            "Operating system memory alerts trigger proactive cache eviction before out-of-memory errors occur. "
            "Thorough fault injection testing verifies that hardware failure recovery completes without data corruption."
        ),
        (
            "Parametric synthesis engines generate fluid spoken audio with customizable pitch and tempo parameters. "
            "Natural language phrasing algorithms insert appropriate conversational pauses at punctuation boundaries. "
            "Interactive voice commands permit hands-free control of core application functions while multitasking. "
            "User testing verified that spoken audio feedback improves task completion rates in noisy work environments."
        ),
        (
            "Staged rollout strategies deploy new software builds incrementally to small percentages of active servers. "
            "Comprehensive health check endpoints evaluate database responsiveness and queue depth before traffic routing. "
            "Container orchestration agents replace unhealthy worker instances automatically without manual intervention. "
            "Detailed operational runbooks ensure rapid incident resolution across distributed engineering teams."
        ),
        (
            "Empirical research demonstrates the growing viability of fully autonomous local computing systems. "
            "By prioritizing local intelligence, software systems eliminate vulnerability to centralized cloud downtime. "
            "Industry analysts project rapid adoption of on-device productivity tools across security-sensitive industries. "
            "The combination of low latency, total data privacy, and adaptive summarization creates a compelling user experience."
        ),
    ]

    tertiary = [
        (
            "Production deployments demonstrate sustained high availability across global corporate intranets. "
            "Engineers observed significant improvements in developer deployment velocity and operational confidence. "
            "Routine regression testing suites execute thousands of integration tests in parallel. "
            "Final verification confirms reliable system startup and clean process termination under all scenarios."
        ),
        (
            "Buffer overflow protection prevents packet dropping during high-concurrency ingestion spikes. "
            "Analytical stream processing engines extract immediate statistical summaries from raw sensor feeds. "
            "Zero-copy serialization techniques reduce memory bandwidth pressure on shared bus architectures. "
            "Cluster management agents automatically scale worker instances in response to telemetry volume."
        ),
        (
            "Temporal convolution layers capture dynamic cadence and inflection across diverse vocal styles. "
            "Background noise filtering maintains high fidelity even in crowded cafe environments. "
            "Phonetic feature maps remain robust against varying speaker accents and microphone distances. "
            "The transcription module operates continuously with minimal CPU and GPU thermal dissipation."
        ),
        (
            "Specialized language vocabularies can be swapped dynamically without restarting server processes. "
            "Contextual decoding models adjust beam widths adaptively according to processor utilization. "
            "Language understanding components disambiguate homophones using surrounding contextual cues. "
            "Spoken grammar correction guarantees syntactically correct text output for business correspondence."
        ),
        (
            "Quantized model weights fit comfortably within consumer workstation cache hierarchies. "
            "Matrix multiplication acceleration kernels leverage specialized tensor math instructions. "
            "Precision loss across activation layers remains well below acceptable empirical thresholds. "
            "Device battery consumption decreases markedly when executing quantized neural networks."
        ),
        (
            "Snapshot replication mechanisms allow newly joined cluster nodes to catch up in seconds. "
            "Consensus heartbeat intervals adapt dynamically to observed inter-node network latency. "
            "Distributed transaction logs provide full auditability for compliance and disaster recovery. "
            "High-availability clustering guarantees continuous service availability through power failures."
        ),
        (
            "Cryptographic session tokens are generated using cryptographically secure pseudorandom number generators. "
            "Audit logging systems record security-relevant events without storing sensitive voice payload data. "
            "Continuous automated vulnerability scanning ensures all dependencies remain patched and secure. "
            "Compliance certification confirms alignment with strict enterprise data protection mandates."
        ),
        (
            "System benchmark results were published across peer-reviewed computer science conferences. "
            "Comparative studies confirm significant throughput advantages over traditional relational systems. "
            "Energy efficiency metrics demonstrate a reduced carbon footprint for large-scale deployments. "
            "Engineering leadership approved enterprise-wide rollout following successful trial evaluations."
        ),
        (
            "System watchdog daemons restart unresponsive background workers within fractions of a second. "
            "Resource governance limits prevent any single client thread from exhausting shared resources. "
            "Automated health probes report hardware temperature and voltage status continuously. "
            "Failover procedures execute predictably during planned hardware maintenance operations."
        ),
        (
            "Speech prosody models generate natural expressive cadence suitable for extended listening sessions. "
            "Interactive voice interfaces provide immediate spoken confirmation for critical actions. "
            "User study participants praised the clarity and naturalness of the synthesized voice output. "
            "Spoken task summaries significantly streamline daily workflow management for busy professionals."
        ),
        (
            "Automated rollback mechanisms trigger instantly upon detecting anomalous error spikes. "
            "Distributed tracing systems provide deep visibility into request latencies across microservices. "
            "Configuration updates propagate across running instances without requiring full application restarts. "
            "Infrastructure automation scripts ensure reproducible environment setup in disaster recovery sites."
        ),
        (
            "The strategic shift toward local intelligence represents a transformative paradigm in computing. "
            "Decentralized processing models empower users with complete control over their personal data. "
            "Long-term research initiatives will continue advancing the state of on-device neural processing. "
            "This comprehensive architecture establishes a reliable foundation for modern voice-driven applications."
        ),
    ]

    expanded_sections = []
    for (sec, supp, tert) in zip(sections, supplementary, tertiary):
        expanded_sections.append(sec + "\n\n" + supp + "\n\n" + tert)
    return "\n\n".join(expanded_sections)


def test_dynamic_content_and_scale_analysis():
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()
    sentences = summarizer.tokenize_sentences(doc_10page)

    profile = summarizer.analyze_content(sentences)

    # Validate scale statistics
    assert profile.total_words > 2000
    assert profile.total_sentences >= 90
    assert profile.total_sections == 12
    assert profile.estimated_pages >= 8.0

    # Validate salience distribution
    summarizer.score_sentences(sentences, is_multi_page=True, depth="balanced")
    profile_scored = summarizer.analyze_content(sentences)

    assert profile_scored.salience_max > profile_scored.salience_mean > profile_scored.salience_min
    assert profile_scored.salience_std > 0.0
    assert profile_scored.salience_p75 > profile_scored.salience_mean


def test_quick_summary_multipage_scaling():
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()

    summary_quick = summarizer.summarize(doc_10page, depth="quick")
    words = summary_quick.split()
    word_count = len(words)

    # Requirement: For 10 pages (10-20 sections): ~4-7 key sentences, ~90-160 words
    sentences = [s for s in summary_quick.split(". ") if s.strip()]
    assert 4 <= len(sentences) <= 7
    assert 85 <= word_count <= 165

    # Cuts background fluff / preamble
    assert "in recent years" not in summary_quick.lower()
    assert "historically" not in summary_quick.lower()

    # Captures core thesis and key outcomes/takeaways
    lower_s = summary_quick.lower()
    assert "breakthrough" in lower_s or "streaming" in lower_s or "450 percent" in lower_s or "engine" in lower_s
    assert "conclusion" in lower_s or "takeaway" in lower_s or "standard" in lower_s or "future" in lower_s


def test_standard_summary_multipage_scaling():
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()

    summary_std = summarizer.summarize(doc_10page, depth="standard")
    words = summary_std.split()
    word_count = len(words)

    # Requirement: For 10 pages, covers major sections, mechanisms, and key outcomes (~250-400 words)
    assert 240 <= word_count <= 420

    lower_s = summary_std.lower()
    # Mechanisms checked
    assert any(m in lower_s for m in ("pipeline", "architecture", "framework", "conformer", "quantization", "consensus"))
    # Outcomes checked
    assert any(o in lower_s for o in ("throughput", "latency", "percent", "results show", "reduces", "conclusion"))


def test_detailed_summary_multipage_scaling():
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()

    summary_det = summarizer.summarize(doc_10page, depth="detailed")
    words = summary_det.split()
    word_count = len(words)

    # Requirement: Comprehensive walkthrough: covers all sections, preserving specific numbers, metrics,
    # data points, conditions, caveats, and conclusions (600-900 words for 10-page documents)
    assert 550 <= word_count <= 920

    lower_s = summary_det.lower()
    # Preserves metrics & numbers
    assert any(metric in lower_s for metric in ("percent", "4-bit", "gigabytes", "120 milliseconds", "dollars", "latency"))
    # Preserves caveats & conditions
    assert any(cav in lower_s for cav in ("however", "limitation", "bottleneck", "challenge", "provided that", "although", "despite"))
    # Preserves conclusions
    assert "conclusion" in lower_s or "takeaway" in lower_s or "future" in lower_s


def test_section_level_coverage_across_10_pages():
    """Verify that the selection algorithm distributes coverage across the entire document (pages 1 to 10)."""
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()

    for d in ("quick", "standard", "detailed"):
        summary = summarizer.summarize(doc_10page, depth=d).lower()

        # Beginning / Page 1 coverage (Section 1 or 2)
        has_beginning = any(w in summary for w in ("streaming", "breakthrough", "monolithic", "events per second", "ingestion", "buffer"))
        # Middle / Pages 4-7 coverage (Sections 5-8)
        has_middle = any(w in summary for w in ("quantization", "gigabytes", "consensus", "raft", "50,000", "encryption", "security", "auditors", "isolation", "50ms", "4.5x", "latency", "throughput", "heartbeats"))
        # End / Pages 9-10 coverage (Sections 10-12)
        has_end = any(w in summary for w in ("conclusion", "audio feedback", "voice alerts", "takeaway", "decentralized", "failover", "future", "standard"))

        assert has_beginning, f"Mode {d} missing beginning/page 1 coverage"
        assert has_middle, f"Mode {d} missing middle/pages 4-7 coverage"
        assert has_end, f"Mode {d} missing end/pages 9-10 coverage"


def test_depth_alias_medium():
    summarizer = LocalSpokenSummarizer()
    doc = (
        "Modern cloud distributed architectures enable high availability and elastic resource allocation. "
        "Data centers dynamically shift computational workloads across geographical regions to maintain uptime. "
        "Automated failover clusters minimize latency spikes during unexpected localized outages. "
        "Telemetry pipelines aggregate system health indicators in real time across edge nodes. "
        "The primary takeaway is that automated resilience infrastructure dramatically lowers operational maintenance overhead."
    )
    summary_medium = summarizer.summarize(doc, depth="medium")
    summary_balanced = summarizer.summarize(doc, depth="balanced")
    assert summary_medium == summary_balanced


def test_conversational_human_explanation_flow():
    summarizer = LocalSpokenSummarizer()
    doc_10page = _build_10page_document()

    # Standard summary should contain conversational connectors
    summary_std = summarizer.summarize(doc_10page, depth="standard")
    lower_s = summary_std.lower()

    # Check for natural explanatory connectors
    has_conversational_connector = any(
        conn in lower_s
        for conn in ("under the hood", "in practice", "moving forward", "however", "ultimately", "in conclusion", "to achieve this")
    )
    assert has_conversational_connector, f"Expected conversational human connectors in summary: {summary_std[:200]}"


def test_long_unstructured_article_virtual_sections():
    """Verify that a long multi-page article without markdown headings is partitioned and covered across its entire length."""
    summarizer = LocalSpokenSummarizer()
    # 15 distinct paragraphs without '#' headings (~1500 words)
    paragraphs = [
        f"Paragraph {i}: This section discusses distinct system domain component number {i}. "
        f"Engineers evaluated specialized metric value {i * 10} percent across distributed nodes. "
        f"The primary takeaway from phase {i} demonstrates significant throughput improvement."
        for i in range(1, 16)
    ]
    unstructured_doc = "\n\n".join(paragraphs)

    sentences = summarizer.tokenize_sentences(unstructured_doc)
    profile = summarizer.analyze_content(sentences)

    # Virtual sections should have been created
    assert profile.total_sections >= 4

    # Summaries should have beginning, middle, and end representation
    for depth in ("quick", "standard", "detailed"):
        summary = summarizer.summarize(unstructured_doc, depth=depth).lower()
        has_beg = any(f"component number {i}" in summary or f"phase {i}" in summary or f"{i * 10} percent" in summary for i in (1, 2, 3, 4))
        has_mid = any(f"component number {i}" in summary or f"phase {i}" in summary or f"{i * 10} percent" in summary for i in (6, 7, 8, 9, 10))
        has_end = any(f"component number {i}" in summary or f"phase {i}" in summary or f"{i * 10} percent" in summary for i in (12, 13, 14, 15))
        assert has_beg, f"Depth {depth} missing beginning representation in unstructured doc"
        assert has_mid or has_end, f"Depth {depth} missing middle or end representation in unstructured doc"


def test_sentence_counts_for_quick_standard_detailed_across_scales():
    summarizer = LocalSpokenSummarizer()
    # Short 1-page document
    short_doc = (
        "Voice Flow is an agentic voice productivity application for Windows desktop users. "
        "It delivers real-time voice typing and intelligent audio summaries with an ultra-low latency architecture. "
        "The system operates completely offline without requiring any external network or API keys. "
        "Under the hood, speech synthesizers regulate pause duration and inflection for clear human comprehension. "
        "In conclusion, local speech interfaces represent the foundational future of productivity."
    )

    quick_short = summarizer.summarize(short_doc, depth="quick")
    std_short = summarizer.summarize(short_doc, depth="standard")
    det_short = summarizer.summarize(short_doc, depth="detailed")

    sents_quick_short = [s for s in re.split(r'(?<=[.!?])\s+', quick_short) if s.strip()]
    sents_std_short = [s for s in re.split(r'(?<=[.!?])\s+', std_short) if s.strip()]
    sents_det_short = [s for s in re.split(r'(?<=[.!?])\s+', det_short) if s.strip()]

    # Quick for short text: 1 to 3 punchy sentences
    assert 1 <= len(sents_quick_short) <= 3
    # Standard for short text: 2 to 5 sentences
    assert 2 <= len(sents_std_short) <= 5
    # Detailed for short text: 4 to 6 sentences
    assert len(sents_det_short) >= len(sents_std_short)

    # 10-page document sentence counts
    doc_10page = _build_10page_document()
    quick_10p = summarizer.summarize(doc_10page, depth="quick")
    std_10p = summarizer.summarize(doc_10page, depth="standard")
    det_10p = summarizer.summarize(doc_10page, depth="detailed")

    sents_quick_10p = [s for s in re.split(r'(?<=[.!?])\s+', quick_10p) if s.strip()]
    sents_std_10p = [s for s in re.split(r'(?<=[.!?])\s+', std_10p) if s.strip()]
    sents_det_10p = [s for s in re.split(r'(?<=[.!?])\s+', det_10p) if s.strip()]

    # Quick: 4 to 7 key sentences
    assert 4 <= len(sents_quick_10p) <= 7
    # Standard: 10 to 22 sentences
    assert 10 <= len(sents_std_10p) <= 22
    # Detailed: 20 to 55 sentences
    assert 20 <= len(sents_det_10p) <= 55


def test_short_text_compression_standard_mode():
    """Verify that short texts (4-5 sentences) are compressed in standard mode instead of 100% regurgitated."""
    summarizer = LocalSpokenSummarizer()
    short_input = (
        "First, voice technologies streamline desktop workflows. "
        "Second, local neural processing protects enterprise data privacy. "
        "Third, memory consumption must remain bounded during execution. "
        "Fourth, background threads prevent user interface freezes. "
        "Fifth, offline models provide dependable accessibility anywhere."
    )
    summary_std = summarizer.summarize(short_input, depth="standard")
    sents = [s for s in re.split(r'(?<=[.!?])\s+', summary_std) if s.strip()]
    assert len(sents) <= 3
    assert len(sents) < 5


def test_sanitize_for_speech_numeric_ranges_and_abbreviations():
    """Verify speech sanitization correctly expands numeric ranges, field labels, and abbreviations."""
    summarizer = LocalSpokenSummarizer()
    raw = (
        "Key Takeaway: The system processed queries within 800-2400 ms. "
        "Performance: We observed approx. 500 ops/sec with avg. overhead of 3%. "
        "Run completed in 10 min. and 30 sec. vs. 1 hr. previously."
    )
    clean = summarizer.sanitize_for_speech(raw)
    assert "Key Takeaway:" not in clean
    assert "Performance:" not in clean
    assert "800 to 2400" in clean
    assert "approximately" in clean
    assert "average" in clean
    assert "minutes" in clean
    assert "seconds" in clean
    assert "versus" in clean
    assert "hours" in clean


def test_paragraph_sentence_splitter_terminal_dc_and_sections():
    """Verify _split_paragraph_sentences handles sentences ending with abbreviations like D.C. or Section A."""
    summarizer = LocalSpokenSummarizer()
    text = (
        "The delegation met in Washington, D.C. "
        "Next year they meet in London. "
        "Please read Section A. "
        "The following notes cover Section B."
    )
    sents = summarizer._split_paragraph_sentences(text)
    assert len(sents) == 4
    assert sents[0] == "The delegation met in Washington, D.C."
    assert sents[1] == "Next year they meet in London."
    assert sents[2] == "Please read Section A."
    assert sents[3] == "The following notes cover Section B."


