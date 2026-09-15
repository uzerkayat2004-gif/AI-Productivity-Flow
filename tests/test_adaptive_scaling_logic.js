const assert = require('assert');
const fs = require('fs');
const path = require('path');

const jsContent = fs.readFileSync(path.join(__dirname, '../src/voice_flow/gui/video-flow.js'), 'utf-8');

// Extract vfDetectContentClassification function
const vfDetectContentClassificationMatch = jsContent.match(/function vfDetectContentClassification\([\s\S]*?\n\}/);
if (!vfDetectContentClassificationMatch) {
  throw new Error("Could not find vfDetectContentClassification in video-flow.js");
}

// Extract calculateDocumentScaling function
const fnMatch = jsContent.match(/function calculateDocumentScaling\([\s\S]*?\n\}/);
if (!fnMatch) {
  throw new Error("Could not find calculateDocumentScaling in video-flow.js");
}

const vfFormatDurationLabelMatch = jsContent.match(/function vfFormatDurationLabel\([\s\S]*?\n\}/);
if (!vfFormatDurationLabelMatch) {
  throw new Error("Could not find vfFormatDurationLabel in video-flow.js");
}

const vfAnalyzeContentValueMatch = jsContent.match(/function vfAnalyzeContentValue\([\s\S]*?\n\}/);
if (!vfAnalyzeContentValueMatch) {
  throw new Error("Could not find vfAnalyzeContentValue in video-flow.js");
}

const sandbox = new Function(`
  ${vfDetectContentClassificationMatch[0]};
  ${vfAnalyzeContentValueMatch[0]};
  ${fnMatch[0]};
  ${vfFormatDurationLabelMatch[0]};
  return { calculateDocumentScaling, vfFormatDurationLabel, vfDetectContentClassification, vfAnalyzeContentValue };
`)();
const { calculateDocumentScaling, vfFormatDurationLabel, vfDetectContentClassification, vfAnalyzeContentValue } = sandbox;

console.log("Testing calculateDocumentScaling...");

// 1. Empty text
const empty = calculateDocumentScaling("");
assert.strictEqual(empty.wordCount, 0);
assert.strictEqual(empty.pageCount, 0);
assert.strictEqual(empty.targetSeconds, 90);

// 2. 1 page document (~270 words)
const onePageWords = Array(270).fill("word").join(" ");
const onePage = calculateDocumentScaling(onePageWords);
assert.strictEqual(onePage.pageCount, 1);
assert.strictEqual(onePage.briefSeconds, 45, "1 page Brief should be 45s");
assert.strictEqual(onePage.cinematicSeconds, 60, "1 page Cinematic should be ~1 min (60s)");
assert.strictEqual(vfFormatDurationLabel(onePage.briefSeconds), "~45s");
assert.strictEqual(vfFormatDurationLabel(onePage.cinematicSeconds), "~1 min");
console.log("✓ 1 page check passed: Brief = ~45s, Cinematic = ~1 min");

// 3. 2 pages document (~540 words)
const twoPageWords = Array(540).fill("test").join(" ");
const twoPage = calculateDocumentScaling(twoPageWords);
assert.strictEqual(twoPage.pageCount, 2);
assert.strictEqual(twoPage.targetSeconds, 90);
assert.strictEqual(twoPage.targetFormatted, "1m 30s");
console.log("✓ 2 pages check passed: 2 pages (~540 words) ➔ Auto-scaled video target: ~1m 30s (Max 5m ceiling)");

// 4. 5 pages document (~1350 words)
const fivePageWords = Array(1350).fill("sample").join(" ");
const fivePage = calculateDocumentScaling(fivePageWords);
assert.strictEqual(fivePage.pageCount, 5);
assert.strictEqual(fivePage.briefSeconds, 120, "5 pages Brief should be ~2 min (120s)");
assert.strictEqual(fivePage.cinematicSeconds, 240, "5 pages Cinematic should be ~4 min (240s)");
assert.strictEqual(vfFormatDurationLabel(fivePage.briefSeconds), "~2 min");
assert.strictEqual(vfFormatDurationLabel(fivePage.cinematicSeconds), "~4 min");
console.log("✓ 5 pages check passed: Brief = ~2 min, Cinematic = ~4 min");

// 5. Large document (> 2500 words) strictly capped at 5 minutes
const largeWords = Array(3500).fill("documentation").join(" ");
const largeDoc = calculateDocumentScaling(largeWords);
assert(largeDoc.pageCount >= 10);
assert.strictEqual(largeDoc.cinematicSeconds, 300, "Cinematic must be capped at 300s (5 minutes)");
assert.strictEqual(vfFormatDurationLabel(largeDoc.cinematicSeconds, true), "~5 min Max");
assert(largeDoc.targetSeconds <= 300, "Target must not exceed 5 minutes (300s)");
console.log("✓ Large doc check passed: strictly capped at 5 minutes Max ceiling");

// 6. Explicit format selection on large document
const largeBrief = calculateDocumentScaling(largeWords, "brief");
assert.strictEqual(largeBrief.targetSeconds, 120, "Explicit brief on large doc should target 120s");
assert.strictEqual(largeBrief.resolvedFormat, "brief", "Resolved format should be brief");

const largeShort = calculateDocumentScaling(largeWords, "short");
assert.strictEqual(largeShort.targetSeconds, 150, "Explicit short on large doc should target 150s");
assert.strictEqual(largeShort.resolvedFormat, "short", "Resolved format should be short");

const largeExplainer = calculateDocumentScaling(largeWords, "explainer");
assert.strictEqual(largeExplainer.targetSeconds, 240, "Explicit explainer on large doc should target 240s");
assert.strictEqual(largeExplainer.resolvedFormat, "explainer", "Resolved format should be explainer");

const largeCinematic = calculateDocumentScaling(largeWords, "cinematic");
assert.strictEqual(largeCinematic.targetSeconds, 300, "Explicit cinematic on large doc should target 300s");
assert.strictEqual(largeCinematic.resolvedFormat, "cinematic", "Resolved format should be cinematic");
console.log("✓ Explicit format selection tests passed!");

// 7. Direct content classification (vfDetectContentClassification)
console.log("Testing vfDetectContentClassification...");
assert.strictEqual(
  vfDetectContentClassification("Here is the API specification with endpoints and parameters.\n```json\n{}\n```"),
  "technical",
  "API docs with code blocks should be technical"
);
assert.strictEqual(
  vfDetectContentClassification("# Course Syllabus: Advanced Machine Learning\nLecture modules, lessons, and homework assignments."),
  "educational",
  "Course syllabus with lessons should be educational"
);
assert.strictEqual(
  vfDetectContentClassification("# Executive Meeting Minutes\n* Agenda items\n* Key decisions recap\n* Action items for Q3"),
  "summary",
  "Meeting minutes with action items should be summary"
);
assert.strictEqual(
  vfDetectContentClassification("An epic chronicle of an ancient empire, recounting historical journeys and legends."),
  "narrative",
  "Historical chronicle should be narrative"
);
assert.strictEqual(
  vfDetectContentClassification("This is a simple generic text with basic neutral sentences."),
  "general",
  "Generic neutral text should be general"
);
console.log("✓ vfDetectContentClassification classification tests passed!");

// 8. Task-Aware Auto-Adaptive on Large Documents (> 2500 words)
console.log("Testing task/content-aware auto-adaptive scaling on large documents...");

// 8a. Large technical document (2800 words) -> auto-selects explainer
const largeTechDocText = "# API Reference & Architecture Guide\n" +
  "```python\ndef get_status(): return 200\n```\n" +
  Array(2800).fill("endpoint payload schema architecture parameters procedure").join(" ");
const techResult = calculateDocumentScaling(largeTechDocText, "auto");
assert.strictEqual(techResult.resolvedFormat, "explainer", "Large technical document should auto-select explainer");
assert.strictEqual(techResult.targetSeconds, 240, "Large technical document explainer should target 240s");
assert.strictEqual(vfDetectContentClassification(largeTechDocText), "technical");

// 8b. Large educational document (2800 words) -> auto-selects explainer
const largeEduDocText = "# Machine Learning Course Curriculum\n" +
  "## Learning Objectives\n" +
  Array(2800).fill("lesson syllabus module lecture quiz homework textbook").join(" ");
const eduResult = calculateDocumentScaling(largeEduDocText, "auto");
assert.strictEqual(eduResult.resolvedFormat, "explainer", "Large educational document should auto-select explainer");
assert.strictEqual(eduResult.targetSeconds, 240, "Large educational document explainer should target 240s");
assert.strictEqual(vfDetectContentClassification(largeEduDocText), "educational");

// 8c. Large meeting minutes / summary document (2800 words) -> auto-selects brief
const largeSumDocText = "# Executive Board Meeting Minutes\n" +
  "## Action Items & Agenda\n" +
  Array(2800).fill("meeting minutes recap action items standup sync attendees").join(" ");
const sumResult = calculateDocumentScaling(largeSumDocText, "auto");
assert.strictEqual(sumResult.resolvedFormat, "brief", "Large meeting summary document should auto-select brief");
assert.strictEqual(sumResult.targetSeconds, 120, "Large meeting summary brief should target 120s");
assert.strictEqual(vfDetectContentClassification(largeSumDocText), "summary");

// 8d. Large narrative / documentary document (3000 words) -> auto-selects cinematic
const largeNarDocText = "# The Fall of Rome: A Historical Chronicle\n" +
  "## Prologue: An Empire's Journey\n" +
  Array(3000).fill("chronicle history narrative story journey epic empire legend biography").join(" ");
const narResult = calculateDocumentScaling(largeNarDocText, "auto");
assert.strictEqual(narResult.resolvedFormat, "cinematic", "Large narrative document should auto-select cinematic");
assert(narResult.targetSeconds >= 240 && narResult.targetSeconds <= 300, "Large narrative cinematic should be 240-300s");
assert.strictEqual(vfDetectContentClassification(largeNarDocText), "narrative");
console.log("✓ Large document content-aware auto-adaptive tests passed!");

// 9. Task Context guiding auto-adaptive selection on neutral text
console.log("Testing context-guided auto-adaptive scaling...");
const neutralLargeWords = Array(3000).fill("content information data text perspective").join(" ");

// Context object with technical focus
const ctxTechResult = calculateDocumentScaling(neutralLargeWords, "auto", { focus: "API SDK Integration & Architecture SOP" });
assert.strictEqual(ctxTechResult.resolvedFormat, "explainer", "Context with tech focus should yield explainer");

// Context object with meeting summary title
const ctxSumResult = calculateDocumentScaling(neutralLargeWords, "auto", { title: "Executive Meeting Minutes and Action Items" });
assert.strictEqual(ctxSumResult.resolvedFormat, "brief", "Context with summary title should yield brief");

// Context object with cinematic narrative visual direction
const ctxNarResult = calculateDocumentScaling(neutralLargeWords, "auto", { visualDirection: "Cinematic historical documentary on Rome" });
assert.strictEqual(ctxNarResult.resolvedFormat, "cinematic", "Context with narrative visual direction should yield cinematic");

// Context string
const ctxStrResult = calculateDocumentScaling(neutralLargeWords, "auto", "API developer documentation guide");
assert.strictEqual(ctxStrResult.resolvedFormat, "explainer", "Context string with tech guide should yield explainer");
console.log("✓ Context-guided auto-adaptive scaling tests passed!");

// 10. Explicit user format selection strictly respected regardless of content
console.log("Testing explicit format override on different content types...");

// User chooses brief on technical text
const overrideBrief = calculateDocumentScaling(largeTechDocText, "brief");
assert.strictEqual(overrideBrief.resolvedFormat, "brief", "Explicit brief on technical doc must be respected");
assert.strictEqual(overrideBrief.targetSeconds, 120);

// User chooses cinematic on technical text
const overrideCinematic = calculateDocumentScaling(largeTechDocText, "cinematic");
assert.strictEqual(overrideCinematic.resolvedFormat, "cinematic", "Explicit cinematic on technical doc must be respected");
assert.strictEqual(overrideCinematic.targetSeconds, 300);

// User chooses explainer on meeting summary
const overrideExplainer = calculateDocumentScaling(largeSumDocText, "explainer");
assert.strictEqual(overrideExplainer.resolvedFormat, "explainer", "Explicit explainer on summary doc must be respected");
assert.strictEqual(overrideExplainer.targetSeconds, 240);

// User chooses short on narrative text
const overrideShort = calculateDocumentScaling(largeNarDocText, "short");
assert.strictEqual(overrideShort.resolvedFormat, "short", "Explicit short on narrative doc must be respected");
assert.strictEqual(overrideShort.targetSeconds, 150);

console.log("✓ Explicit format override tests passed!");

// 11. Mixed content resilience: Tech doc with a "Summary" section must stay technical
console.log("Testing mixed content resilience (tech doc with 'Summary' section)...");
const techDocWithSummary = "# API Reference & System Architecture Guide\n" +
  "## Authentication & Endpoints\n" +
  "```python\ndef auth(): return 'bearer token'\n```\n" +
  "In summary, call POST /token with credentials.\n" +
  "## Summary\n" +
  "Overall system performance is optimal.\n" +
  Array(2800).fill("endpoint payload schema architecture parameters procedure sdk").join(" ");

const mixedTechClassification = vfDetectContentClassification(techDocWithSummary);
assert.strictEqual(mixedTechClassification, "technical", "Technical doc with summary section must not be misclassified as meeting summary");
const mixedTechScaling = calculateDocumentScaling(techDocWithSummary, "auto");
assert.strictEqual(mixedTechScaling.resolvedFormat, "explainer", "Technical doc with summary section must auto-select explainer");
assert.strictEqual(mixedTechScaling.targetSeconds, 240);

const eduDocWithSummary = "# Machine Learning Course Curriculum\n" +
  "## Module 1: Gradient Descent\n" +
  "In summary, learn the loss function and optimization step.\n" +
  Array(2800).fill("lesson syllabus module lecture quiz homework textbook").join(" ");
const mixedEduClassification = vfDetectContentClassification(eduDocWithSummary);
assert.strictEqual(mixedEduClassification, "educational", "Educational doc with summary text must not be misclassified");
const mixedEduScaling = calculateDocumentScaling(eduDocWithSummary, "auto");
assert.strictEqual(mixedEduScaling.resolvedFormat, "explainer");
console.log("✓ Mixed content resilience tests passed!");

// 12. 1-2 Pages density tier boundary check (150-500 words)
console.log("Testing 1-2 pages density tier boundary (150-500 words -> brief 60-90s)...");
const doc450Words = Array(450).fill("content").join(" ");
const scaling450 = calculateDocumentScaling(doc450Words, "auto");
assert.strictEqual(scaling450.resolvedFormat, "brief", "450 words (1-2 pages) must auto-select brief");
assert(scaling450.targetSeconds >= 60 && scaling450.targetSeconds <= 90, "450 words must target 60-90s duration");

const doc200Words = Array(200).fill("note").join(" ");
const scaling200 = calculateDocumentScaling(doc200Words, "auto");
assert.strictEqual(scaling200.resolvedFormat, "brief", "200 words (1-2 pages) must auto-select brief");
assert(scaling200.targetSeconds >= 45 && scaling200.targetSeconds <= 90, "200 words must target brief duration");
console.log("✓ 1-2 pages density tier boundary tests passed!");

// 13. Context object with task, taskType, and intent properties
console.log("Testing context objects with task and intent properties...");
const ctxIntentResult = calculateDocumentScaling(neutralLargeWords, "auto", { intent: "technical" });
assert.strictEqual(ctxIntentResult.resolvedFormat, "explainer", "Context intent technical should yield explainer");

const ctxTaskResult = calculateDocumentScaling(neutralLargeWords, "auto", { task: "Create an educational lesson walkthrough" });
assert.strictEqual(ctxTaskResult.resolvedFormat, "explainer", "Context task educational should yield explainer");

const ctxDigestResult = calculateDocumentScaling(neutralLargeWords, "auto", { intent: "summary" });
assert.strictEqual(ctxDigestResult.resolvedFormat, "brief", "Context intent summary should yield brief");
console.log("✓ Task and intent context object tests passed!");

// 14. Multi-section document scaling across all 4 format targets
console.log("Testing multi-section scaling across all format duration targets...");
const fiveSectionDoc = `
# Section 1: Ingestion
Data is streamed in real time.

# Section 2: Transformation
ETL workers normalize json schemas.

# Section 3: Indexing
Vector embeddings are computed.

# Section 4: Validation
Automated unit tests verify consistency.

# Section 5: Storage
Data is persisted to distributed storage.
`;
const fiveSecScaling = calculateDocumentScaling(fiveSectionDoc, "auto");
assert.strictEqual(fiveSecScaling.sectionCount, 5, "Should detect 5 sections");
assert(fiveSecScaling.shortSeconds >= 60, "5 sections must scale short to >= 60s (5 * 12s)");
assert(fiveSecScaling.briefSeconds >= 70, "5 sections must scale brief to >= 70s (5 * 14s)");
assert(fiveSecScaling.explainerSeconds >= 100, "5 sections must scale explainer to >= 100s (5 * 20s)");
assert(fiveSecScaling.cinematicSeconds >= 125, "5 sections must scale cinematic to >= 125s (5 * 25s)");

const explicitFiveSecShort = calculateDocumentScaling(fiveSectionDoc, "short");
assert.strictEqual(explicitFiveSecShort.targetSeconds, explicitFiveSecShort.shortSeconds, "Explicit short format must match section-scaled shortSeconds");

const explicitFiveSecCinematic = calculateDocumentScaling(fiveSectionDoc, "cinematic");
assert.strictEqual(explicitFiveSecCinematic.targetSeconds, explicitFiveSecCinematic.cinematicSeconds, "Explicit cinematic format must match section-scaled cinematicSeconds");
console.log("✓ Multi-section scaling across all format targets passed!");

// 15. Dense Single-Page Document Scaling (e.g. dense election article ~150-300 words)
console.log("Testing dense single-page document scaling (election article with key concepts)...");
const denseElectionDoc = [
  "The 2026 presidential election hinges on six critical battleground states where turnout among independent voters has surged by 18 percent.",
  "Suburban demographics in Pennsylvania have shifted toward moderate fiscal reform due to economic inflation concerns.",
  "Industrial workforce coalitions in Michigan demand targeted manufacturing tariffs and energy subsidies.",
  "Rapid Sun Belt migration into Arizona introduces substantial polarization across urban and rural voting blocs.",
  "Electoral college modeling indicates that a 2 percent swing in the popular vote triggers a decisive shift in 64 electoral votes.",
  "Voter registration records reveal unprecedented youth registration numbers, fundamentally altering historical turnout paradigms."
].join("\n\n");

const electionScaling = calculateDocumentScaling(denseElectionDoc, "auto");
assert(electionScaling.wordCount >= 70 && electionScaling.wordCount <= 300, `Word count should be ~100 words, got ${electionScaling.wordCount}`);
assert(electionScaling.densityScore >= 1.4, `Density score must be high (>= 1.4), got ${electionScaling.densityScore}`);
assert(electionScaling.conceptCount >= 4, `Concept count must be >= 4, got ${electionScaling.conceptCount}`);
assert.strictEqual(electionScaling.resolvedFormat, "explainer", "Dense single page doc with high concept density must auto-select explainer");
assert(electionScaling.targetSeconds >= 180, `Dense single page doc must scale to at least 180s (3+ minutes), got ${electionScaling.targetSeconds}s`);
assert(electionScaling.targetSeconds <= 240, `Explainer target must not exceed 240s, got ${electionScaling.targetSeconds}s`);
console.log(`✓ Dense single-page election check passed: ${electionScaling.targetSeconds}s (${electionScaling.targetFormatted}) auto-selected explainer`);

// 16. Book summary document scaling (~1000 words with dense chapter breakdown)
console.log("Testing book summary document scaling...");
const bookSummaryDoc = [
  "# Comprehensive Summary of the Book: Principles of Economic Systems",
  "This executive summary of the entire book breaks down the foundational mechanisms of global trade, currency regulation, and monetary policy.",
  "Chapter 1 establishes the causal mechanisms behind credit expansion and debt cycles in modern banking architectures.",
  "Chapter 2 examines historical hyperinflation crises, analyzing how fiscal imbalances trigger systemic asset depreciation.",
  "Chapter 3 investigates labor market automation, showing how robotics influences wage disparity across industrial sectors.",
  "Chapter 4 presents empirical modeling of international supply chains, demonstrating how logistical friction results in aggregate price shifts.",
  "Chapter 5 explores sovereign bond yields and how central bank interest rate decisions regulate capital velocity.",
  "In conclusion, the author's synthesis provides a unified paradigm for macroeconomic stability in the twenty-first century."
].join("\n\n");

const bookSummaryScaling = calculateDocumentScaling(bookSummaryDoc, "auto");
assert(bookSummaryScaling.densityScore >= 1.4, `Book summary density score must be >= 1.4, got ${bookSummaryScaling.densityScore}`);
assert.strictEqual(bookSummaryScaling.resolvedFormat, "cinematic", "Book summary must auto-select cinematic");
assert(bookSummaryScaling.targetSeconds >= 240 && bookSummaryScaling.targetSeconds <= 300, `Book summary should scale to 4-5 minutes (240-300s), got ${bookSummaryScaling.targetSeconds}s`);
console.log(`✓ Book summary check passed: ${bookSummaryScaling.targetSeconds}s (${bookSummaryScaling.targetFormatted}) auto-selected cinematic`);

// 17. 10-Page Redundant Document Compression (~2700 words repeating identical content)
console.log("Testing 10-page redundant document compression (repetition compressed to concise duration)...");
const redundantParagraph = "This introductory overview introduces the fundamental tenets of cloud computing. " +
  "We evaluate serverless functions, container orchestration, distributed datastores, and network latency optimizations. " +
  "The system guarantees high availability and fault tolerance across distributed edge locations.";
// 10 pages with ~270 words per page repeating the same content
const onePageContent = Array(8).fill(redundantParagraph).join(" ");
const tenPageRedundantDoc = Array(10).fill(onePageContent).join("\n\n");

const redundantScaling = calculateDocumentScaling(tenPageRedundantDoc, "auto");
assert(redundantScaling.wordCount >= 2500, `Word count should be > 2500 words, got ${redundantScaling.wordCount}`);
assert(redundantScaling.redundancyScore >= 0.50, `Redundancy score should be >= 0.50, got ${redundantScaling.redundancyScore}`);
assert(redundantScaling.densityScore <= 0.65, `Density score should be low (<= 0.65), got ${redundantScaling.densityScore}`);
assert.strictEqual(redundantScaling.resolvedFormat, "brief", "Redundant 10-page document must compress to brief, not expand to 5m cinematic");
assert(redundantScaling.targetSeconds <= 120, `Target seconds must be compressed to <= 120s, got ${redundantScaling.targetSeconds}s`);
console.log(`✓ Redundant 10-page check passed: ${redundantScaling.wordCount} words compressed to ${redundantScaling.targetSeconds}s brief`);

// 18. Concept Breathing Room check
console.log("Testing concept breathing room...");
const multiConceptDoc = [
  "Core proposition one: Neural decoding enables direct motor control for robotic prosthetics with sub-millisecond latency.",
  "Core proposition two: Spatial frequency filters eliminate ambient electromagnetic interference across sensory recording electrodes.",
  "Core proposition three: Adaptive reinforcement learning algorithms optimize gripper trajectory based on tactile feedback loops.",
  "Core proposition four: Clinical trials demonstrate 94 percent task completion rates in motor restoration benchmarks."
].join("\n\n");
const conceptScaling = calculateDocumentScaling(multiConceptDoc, "auto");
assert(conceptScaling.conceptCount >= 4, `Should detect >= 4 concepts, got ${conceptScaling.conceptCount}`);
assert(conceptScaling.explainerSeconds >= 88, `Explainer seconds must allocate >= 22s per concept (4 * 22 = 88s), got ${conceptScaling.explainerSeconds}s`);
assert(conceptScaling.cinematicSeconds >= 112, `Cinematic seconds must allocate >= 28s per concept (4 * 28 = 112s), got ${conceptScaling.cinematicSeconds}s`);
console.log("✓ Concept breathing room check passed!");

// 19. Direct vfAnalyzeContentValue assertions
console.log("Testing vfAnalyzeContentValue direct function...");
const directVal = vfAnalyzeContentValue(denseElectionDoc);
assert(directVal.contentValueRating === "high" || directVal.contentValueRating === "very_high");
assert(directVal.conceptCount >= 4);
assert(directVal.substantiveConcepts.length >= 4);

const directRedundantVal = vfAnalyzeContentValue(tenPageRedundantDoc);
assert(directRedundantVal.redundancyScore >= 0.50);
assert.strictEqual(directRedundantVal.contentValueRating, "low");
assert(directRedundantVal.effectiveWordCount < directRedundantVal.wordCount || directRedundantVal.effectiveWordCount <= 1000);
console.log("✓ vfAnalyzeContentValue direct assertions passed!");

// 20. Bulleted list concept segmentation
console.log("Testing bulleted list concept segmentation in JS...");
const bulletListDoc = [
  "# Key Campaign Takeaways",
  "- Turnout surged 18 percent in swing counties due to non-partisan ground operations.",
  "- Suburban demographics in Pennsylvania prioritize inflation and moderate fiscal stability.",
  "- Industrial union leadership in Michigan demands manufacturing tariffs and clean energy tax credits.",
  "- Sun Belt voting registrations introduce decisive demographic shifts across congressional districts."
].join("\n");
const bulletVal = vfAnalyzeContentValue(bulletListDoc);
assert(bulletVal.conceptCount >= 4, `Bullet list should extract >= 4 concepts, got ${bulletVal.conceptCount}`);
assert(bulletVal.substantiveConcepts.length >= 4, `Should have >= 4 substantive concepts, got ${bulletVal.substantiveConcepts.length}`);
assert(bulletVal.densityScore >= 1.3, `Density score should be >= 1.3, got ${bulletVal.densityScore}`);
console.log("✓ Bulleted list concept segmentation passed!");

// 21. Dense single-page document scaling to full 5-minute cinematic video
console.log("Testing dense single-page document scaling to full 5 minutes in cinematic...");
const denseCineScaling = calculateDocumentScaling(denseElectionDoc, "cinematic");
assert(denseCineScaling.targetSeconds >= 240 && denseCineScaling.targetSeconds <= 300, `Dense single-page cinematic should scale to 4-5 minutes, got ${denseCineScaling.targetSeconds}s`);
assert.strictEqual(denseCineScaling.resolvedFormat, "cinematic");
console.log(`✓ Dense single-page cinematic check passed: ${denseCineScaling.targetSeconds}s (${denseCineScaling.targetFormatted})`);

console.log("All scaling calculation assertions passed successfully!");


