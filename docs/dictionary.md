# How dictionary / custom vocabulary should work in a dictation app

Research for AI Productivity Flow (Voice Flow), 12 Oct 2026.

## What the top apps do

| App | Words (names/terms) | Replacements | Auto-learning | Notes |
|---|---|---|---|---|
| **Wispr Flow** | "Vocabulary words" boost recognition of names and jargon | Optional "Correct a misspelling" per entry: misspelling -> correct spelling. Whole-word, case-insensitive, longest phrase wins, literal, keeps your saved capitalization | Optional "Auto-add": only proper nouns / uncommon words, **common words deliberately excluded**; marked with a sparkle and deletable | Snippets are a **separate tab**. Docs warn replacements are literal, so "avoid mapping phrases you want left alone". 60-char limit per word |
| **Superwhisper** | Vocabulary words are sent with the audio as recognition hints | Replacements run after transcription, deterministically, "no AI interpretation", case-insensitive match, output in your exact case | None | Docs: keep the vocabulary list **short**; too many hint words cause hallucinations |
| **Willow Voice** | Dictionary terms: names, products, acronyms | "Enable term replacement": original -> replacement | Separate "Auto Learning" section, kept apart from "My Terms" | Shortcuts are their own feature |
| **Aqua Voice** | Dictionary of difficult words (up to 800 on Pro), add/remove only | Phrase replacements via CLI | None documented | Simple list UI: type, Add, Remove |
| **MacWhisper** | Whisper "Prompt" field biases recognition | Global Replace: Original/Replacement pairs, options "case sensitive" and "only replace separate words", search bar | None | Import/export as JSON |
| **Dragon** | Vocabulary Editor: written form + optional spoken form | Alternate written forms | Learns from corrections it is told about | The classic written-form vs spoken-form split |
| **Apple / Windows dictation** | No user vocabulary API | Text replacements are an OS keyboard feature, not part of dictation | n/a | Shows that shortcuts/text expansion is a separate concept |

## What the speech APIs offer for biasing

- **Deepgram** `keyterm` (Nova-3, Flux): up to 100 plain terms, exact spelling; no weights. Flux can update mid-stream.
- **AssemblyAI** `keyterms_prompt`: up to 100 terms (streaming); "avoid common words, they dilute the list"; give exact spelling/capitalization.
- **Whisper / faster-whisper**: `initial_prompt` or `hotwords` string. Long prompts can cause hallucinations.
- **NVIDIA NeMo / Nemotron**: phrase boosting / context biasing (CTC-WS, GPU-PB boosting tree). Our Nemotron C ABI already has `speech_contexts` with a boost.

## Key takeaways

1. **Two tools, not one.** Every serious app splits *Words* (recognition bias + exact spelling) from *Replacements* (explicit heard -> correct pairs). A saved word must never become a general search-and-replace.
2. **Bias the recognizer first, post-process second.** The word list goes to the speech engine (keyterms / hotwords / context biasing). Post-processing only fixes the spelling of that same word, or applies a pair the user wrote.
3. **Deterministic and model-independent.** Replacements run the same way whatever the model and whether AI polishing is on or off.
4. **Never learn from AI output.** Wispr's auto-add only learns rare proper nouns from *user* edits and excludes common words. Learning from the difference between raw and polished text (what our old code did) teaches the dictionary to rewrite real speech.
5. **Refuse ordinary words.** AssemblyAI and Wispr both exclude common words; a list entry for "meeting" or "hey" can only damage dictation.
6. **Whole-word, case-insensitive, longest match, one pass.** Keep the user's casing; never match inside a larger word; never cascade.
7. **Keep lists short.** Recognizer hint budgets are about 100 terms; long prompts hurt Whisper.
8. **Simple UI.** List, search, add word, optional "heard as", delete. Shortcuts live in their own place.
9. **Give the LLM polisher the spellings** as preferred spellings, without forcing it to insert them.

## Sources

- Wispr Flow: https://docs.wisprflow.ai/articles/4052411709-teach-flow-your-words-with-the-dictionary ,
  https://docs.wisprflow.ai/articles/5052432796-copy-of-general-article ,
  https://docs.wisprflow.ai/articles/9639977157-view-shared-dictionary-words-and-snippets-in-the-admin-portal
- Superwhisper: https://superwhisper.com/docs/get-started/interface-vocabulary ,
  https://superwhisper.com/docs/common-issues/hallucinations
- Willow Voice: https://help.willowvoice.com/en/articles/13183918-using-personal-dictionary-and-shortcuts ,
  https://help.willowvoice.com/en/articles/12864717-using-dictionary-terms-on-ios
- Aqua Voice: https://aquavoice.com/guide/dictionary , https://aquavoice.com/docs/cli
- MacWhisper: https://docs.macwhisper.com/article/37-find-and-replace-in-transcriptions
- Dragon: https://www.nuance.com/products/help/dragon/dragon-for-mac/enx/content/Accuracy/VocabularyEditor.html
- Deepgram keyterms: https://developers.deepgram.com/docs/keyterm
- AssemblyAI keyterms: https://www.assemblyai.com/docs/streaming/prompting-and-keyterms
- NeMo word boosting: https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/asr_customization/word_boosting.html

## Design chosen for Voice Flow

- **Words**: names and special terms. Sent to the recognizer (Nemotron speech context, faster-whisper `hotwords`, Deepgram `keyterm`, other cloud prompts), listed to the cloud polisher as preferred spellings, and afterwards fix only their own spelling (case-insensitive, whole word, keeps 's / s / es endings).
- **Replacements**: "Heard as" pairs the user writes. Whole phrase only. A single ordinary word ("hey", "here") is refused as a heard phrase; multi-word phrases are allowed.
- **No automatic learning** of any kind. The learning modules are deleted.
- **Same deterministic pass** with polishing on and off (one pass, no cascading, URLs/emails/code protected).
- **Built-in terms** (Voice Flow, Hey Voice Flow) are handled by the wake-phrase repair in the command detector; saving them as Words is refused.
- **Ordinary words** are refused as Words in any casing (a "IT" entry would rewrite every "it").
- **Shortcuts** stay their own table and feature; they still expand in the same pass.
- **Upgrade**: existing dictionary rows, replacements and learning candidates are written to `dictionary-backup-before-rebuild-<time>.json` in the data folder, then cleared once.

## Protection around every polisher (all models, polish on or off)

1. **Before polish**: Words and Replacements are applied to the transcript (shortcuts are not), so every model sees the correct spelling and no model can rewrite a shortcut expansion.
2. **Prompt note (model-agnostic)**: `dictionary_engine.preferred_spellings_note(text)` lists only the user's names present in this dictation ("Keep these names exactly as spelled: ..."). Cloud polishing and LFM append it. **S1 is unchanged**: its trained control line and system prompt are not touched.
3. **After polish** (`TextPolisher.polish`) and **after templates/command rewrites/style** (`VoiceFlowApp._finalize_text`): `guard_polished_output` re-applies Words/Replacements, restores exact spelling, and repairs a re-spelled Word (Kubernetis, Kuber Netes -> Kubernetes) when a span is at least 80% similar. It never inserts a name that was not spoken. Shortcut expansions are shielded and pasted literally.
4. **No chains across passes**: once text has had a dictionary pass, a Replacement whose heard phrase is another rule's output is skipped (first -> second, second -> third runs once).

### Training-data note for S1 / a future fine-tuned Qwen
Add an optional, separate field (not in the legacy control line), e.g. a `names:` line after the control line, listing only the dictionary names present in the input, with targets that keep those names verbatim. Include negatives where the list names a term that is absent and the target does not add it. Until then the post-polish guard is the protection for S1.
