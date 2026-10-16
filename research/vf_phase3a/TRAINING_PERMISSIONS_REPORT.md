# VF Phase 3a: training-data permissions assessment

**Question:** Can Uzair fine-tune S1-mini (0.6B) on the 2,561 training targets and reviews written by Hark, (a) privately, (b) then release the model publicly, (c) then release the dataset publicly?

**All sources fetched:** 12 Oct 2026 (IST). Quotes are copied exactly from the live pages. This is a reading of contract terms, not legal advice.

---

## 0. Bottom line

**BLOCKED, including private fine-tuning, until Hark gives written permission.**

Hark's own Acceptable Usage Policy, which its Terms of Service make binding, bans this outright. Under "Do Not Abuse our Platform" it lists: *"Use inputs and outputs to train an AI model (e.g., model scraping or model distillation)"*. Unlike the OpenAI, Anthropic and Google clauses, this ban has no "competing" condition and no exception for private or non-commercial use. A small, non-competing voice-cleanup model is still "an AI model", so it falls inside the ban. The upstream model provider doesn't change this: the Hark ban applies whichever model Hark used.

The S1-mini base licence is **not** the blocker. It allows private fine-tuning and redistribution under Apache-2.0 plus a naming clause.

---

## 1. Which "Hark" this is (identity check)

- The right company is **Hark Labs, Inc.**, 4000 N First St, San Jose, CA 95134, USA. Product: Hark Pro, at **hark.com**. Source: https://hark.com/terms ("These Terms are a contract between you and Hark Labs, Inc. ... of 4000 N First St, San Jose, CA 95134, USA").
- It uses the tagline from the brief. https://hark.com/using-hark says: "Hark is the operating system for your life, built to think ahead, and help you with real, practical things." The same page says: "Hark is the name of our company and the personal intelligence we're building. Hark Pro is the software presentation of Hark on the web along with iOS and Android apps."
- I ruled out these unrelated companies with similar names:
  - gethark.ai: enterprise AI platform (Tracxn listing)
  - harkenai.com: meeting assistant
  - harkai.beyondaigen.com: transcription
  - hark.ie: Irish retailer
- hark.ai is a "Request Access" holding page for the same personal-intelligence company, with no separate terms.
- Hark's Terms version: "Last updated: October 1, 2026". The Privacy Policy has the same date.

## 2. Hark's terms: exact clauses

### 2.1 Usage Policy: flat ban on training (decisive)
URL: https://hark.com/acceptable-usage-policy. It is incorporated by ToS §3: "Your access to and use of our Services is permitted only where you comply with these Terms, including our Usage Policy ...".

The heading reads "Do Not Abuse our Platform". The list under it begins "This includes using our products or services to:" and includes:
> - "Reverse engineer, decompile, or otherwise attempt to obtain the underlying models, algorithms, or source code of our products or services. You may not engage in this or any other activities with regards to our products and services to build products that may be competitive with Hark."
> - **"Use inputs and outputs to train an AI model (e.g., model scraping or model distillation)"**

Note: Anthropic's equivalent line adds "without prior authorization from Anthropic". Hark's line has no such words, so the policy text itself doesn't describe a way to get permission. Asking Hark directly is the only route (see §6).

### 2.2 Terms of Service §3: no competing products, no model training
URL: https://hark.com/terms §3 "Use of our Services", "Acceptable Uses":
> "In addition to complying with our Usage Policy, you cannot access or use our Services, or assist someone to access or use our Services to:
> - Engage in any activities with the intention of creating any products or services that compete with our Services. Such activities include developing or training any artificial intelligence or machine learning algorithms or models or reselling the Services to others.
> - Modify, copy, lease, sell or distribute the Services.
> - Engage in crawling, scraping, or any similar activities that harvest data or information from the Services other than those explicitly permitted under these Terms.
> - ...
> - Unless explicitly permitted by us under these Terms, access our Services through the use of automated measures (including but not limited to bots, scripts or otherwise).
> - ...
> - Make representations that Output is human-generated at times when it is not."

How to read it: on its own, this clause is tied to intent to compete. A 0.6B speech-transcript normaliser arguably doesn't compete with a personal-AI "operating system". But §2.1 removes the need for that argument, because the Usage Policy ban has no competition test. Note also the words "or assist someone": publishing a training dataset could count as assisting others.

### 2.3 Terms of Service §4: who owns the outputs
URL: https://hark.com/terms §4 "Rights and Responsibilities":
> "Any right, title, and interest that you have in the Inputs you submit is yours."
> "Subject to your compliance with these Terms, we, to the greatest extent possible, assign to you any rights, title, and interests we may have in Outputs. Given the novel nature of our Services and AI, the Outputs generated by us for other users may be similar to Outputs received by you. ..."

How to read it: Uzair does own the outputs, but only "subject to your compliance with these Terms". Owning the text doesn't override the usage ban. Training in breach of the Usage Policy could also put the ownership assignment itself at risk.

### 2.4 Terms of Service §4: model providers
URL: https://hark.com/terms §4 "AI Model and Service Providers":
> "The Services are built using artificial intelligence models, infrastructure, and other services provided by third parties, and your Content may be processed by those providers to provide the Services. We require these providers to protect your Content under terms consistent with our Privacy Policy, and we do not permit them to use your Content to train their own models. Our Privacy Policy describes the categories of providers we use."

The Privacy Policy (https://hark.com/privacy-policy §3) names only a category: "AI providers with whom that we have a written agreement prohibiting use of the data for model training". **No provider or model is named anywhere in the public terms.**

Another Privacy Policy line is easy to misread: "Hark does not use your Inputs, Outputs, Memory, connected account data, or sandbox environment data to train AI or machine learning models." This limits what *Hark* does with Uzair's data. It gives Uzair no right to train on outputs.

### 2.5 Content Generation and Publication Policy: publishing outputs
URL: https://hark.com/content-generation-and-publication-policy.

§3 "Content Sharing":
> "Subject to compliance with this Policy, Users may share their Inputs and Outputs via social media platforms and livestream their use of the Services. Such activities are subject to the following mandatory conditions:
> - The User shall manually review and approve each Output prior to public dissemination ...;
> - The User's legal name, pseudonym, or business name, as applicable shall be included on all Content;
> - The User shall ensure that all Content is clearly labeled as AI-generated in a conspicuous manner ..."

§2 "Restrictions on Use":
> "... Content generated through the Services shall not be used to: ... Engage in commercial exploitation, including but not limited to commercial endorsements, advertising campaigns, merchandising, or any revenue-generating activity, without prior written authorization from Hark."

How to read it: these rules let users *share* outputs, for example on social media. They don't grant any right to use outputs as training data. Even a permitted public release would still need AI-generated labelling and per-item manual review. Any revenue use needs Hark's written authorisation.

### 2.6 Terms of Service §15: brand
> "Hark brand usage. You may not use Hark's name, logos, trademarks, or other brand assets without our prior written consent, including any use that suggests affiliation with, endorsement by, or sponsorship from Hark."

Effect: a public model or dataset card that names Hark as the data source ("distilled from Hark") needs Hark's consent.

## 3. Upstream LLM providers Hark might route to

**Contract scope:** Uzair's only contract is with Hark. He isn't a party to the provider terms below. They bind Hark as the provider's customer, and they reach Uzair through Hark's own flow-down clauses, which is very likely what §2.1 is. I can't confirm which, if any, of these providers Hark uses: **Hark doesn't disclose its models.** A business like Hark would normally be on the commercial/API terms (OpenAI Services Agreement, Anthropic Commercial Terms, Gemini API terms), not the consumer terms.

### 3.1 OpenAI
- **Terms of Use** (consumer), https://openai.com/policies/row-terms-of-use/, effective 1 Jan 2026. Under "What you cannot do":
  > "Use Output to develop models that compete with OpenAI."
  > "Automatically or programmatically extract data or Output (defined below)."
  
  Ownership: "you (a) retain your ownership rights in Input and (b) own the Output."
- **Services Agreement** (business/API), https://openai.com/policies/services-agreement/, effective 1 Jan 2026. §3.3:
  > "Customer will not, and will not permit End Users to: ... (e) except for a Permitted Exception, use Output to develop artificial intelligence models that compete with OpenAI's products and services; (f) extract data from the Services other than as permitted through the Services ..."
  
  §17:
  > "'Permitted Exception' means Customer using Output to: (a) develop artificial intelligence models primarily intended to categorize, classify, or organize data (e.g., embeddings or classifiers), if these models are not distributed or made commercially available to third parties; and (b) fine tune or customize models provided as part of OpenAI's fine-tuning or other Services set forth on the Pricing Page."
  
  Note: "End Users" covers anyone "who uses Customer Applications". Hark would have to stop its users from doing what Hark itself may not do.
- **Applied here:** the test is "compete with OpenAI's products and services". A text-normalisation model arguably competes with general text generation in a narrow sense, but that's debatable. It isn't a classifier, so the Permitted Exception doesn't clearly apply. Releasing the model publicly would mean distributing it, which is outside the exception.

### 3.2 Anthropic
- **Commercial Terms**, https://www.anthropic.com/legal/commercial-terms, effective 17 June 2025. §D.4:
  > "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic; (b) reverse engineer or duplicate the Services; or (c) support any third party's attempt at any of the conduct restricted in this sentence."
- **Usage Policy**, https://www.anthropic.com/legal/aup. The page header says "Effective November 12, 2026", a date later than the fetch date, recorded as shown. Under "Do Not Abuse Our Platform":
  > "Use outputs to train an AI model (e.g., 'model scraping' or 'model distillation') without prior authorization from Anthropic"
  
  This Usage Policy applies to "the end users of products or services integrating Claude". **If Hark routes to Claude, this flat ban reaches Uzair directly as an end user, with no competition test.**
- **Consumer Terms**, https://www.anthropic.com/legal/consumer-terms, effective 8 Oct 2025. §3:
  > "To develop any products or services that compete with our Services, including to develop or train any artificial intelligence or machine learning algorithms or models or resell the Services."
- Hark's own ToS §3 and Usage Policy closely mirror Anthropic's wording, but that alone doesn't show Hark uses Anthropic models.

### 3.3 Google Gemini API
- **Gemini API Additional Terms of Service**, https://ai.google.dev/gemini-api/terms, effective 23 Mar 2026. Under "Use Restrictions":
  > "You may not use the Services to develop models that compete with the Services (e.g., Gemini API or Google AI Studio). You also may not attempt to reverse engineer, extract or replicate any component of the Services, including the underlying data or models (e.g., parameter weights)."
  
  Under "Use of Generated Content":
  > "Google won't claim ownership over that content."
- **Applied here:** this is narrower and conditioned on competition. A transcript normaliser is unlikely to "compete with" the Gemini API or AI Studio, but that's a judgment call.

### 3.4 Permissive contrast: Qwen3 (open weights)
- https://huggingface.co/Qwen/Qwen3-0.6B shows "License: apache-2.0". Apache-2.0 restricts copying and redistribution of the Work. It has **no clause on how you may use the model's outputs** and no ban on training competing models.
- If the targets had been generated by a self-hosted Apache-2.0 model such as Qwen3, or another Apache-2.0 open-weights model, there would be no output restriction at all. That's an alternative way to build the dataset (see §7).

### 3.5 Summary table

| Source | Clause type | Competition test? | Covers a private non-competing 0.6B? | Fetched |
|---|---|---|---|---|
| **Hark Usage Policy** | Flat ban: "Use inputs and outputs to train an AI model" | **No** | **Yes, prohibited** | 2026-10-12 |
| Hark ToS §3 | No competing products; "such activities include ... training" models | Yes (intent to compete) | Arguably not, but §2.1 controls | 2026-10-12 |
| OpenAI Services Agreement §3.3(e) | Output for competing models (narrow exception) | Yes | Unclear; exception doesn't fit | 2026-10-12 |
| OpenAI Terms of Use | "Use Output to develop models that compete with OpenAI" | Yes | Unclear | 2026-10-12 |
| Anthropic Usage Policy | "Use outputs to train an AI model ... without prior authorization" | **No** | **Yes, prohibited** (if Claude is upstream) | 2026-10-12 |
| Anthropic Commercial Terms D.4 | No training competing models | Yes | Arguably not | 2026-10-12 |
| Gemini API Additional Terms | No models that compete with the Services | Yes | Probably not | 2026-10-12 |
| Qwen3 (Apache-2.0) | None on outputs | n/a | Allowed | 2026-10-12 |

## 4. Base model: superwhisper/s1-mini licence (exact text)

- **LICENSE**, https://huggingface.co/superwhisper/s1-mini/raw/main/LICENSE. Header:
  > "Copyright 2026 Superwhisper
  > This model is a derivative work of Qwen3-0.6B, Copyright 2024 Alibaba Cloud, licensed under the Apache License, Version 2.0."
- **The naming clause**, from the same file, at the end under "ADDITIONAL TERM":
  > "In addition to the terms of the Apache License, Version 2.0 above: any use, distribution, or integration of this model, whether unmodified or as part of a derivative work or product, must continue to identify it by its original name, "S1-mini" by "Superwhisper", using that exact capitalization, regardless of any other name under which the model or a product incorporating it is marketed or distributed."
- **Apache-2.0 §2** (grant):
  > "... each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works in Source or Object form."
- **Apache-2.0 §4** (redistribution conditions):
  > "(a) You must give any other recipients of the Work or Derivative Works a copy of this License; and
  > (b) You must cause any modified files to carry prominent notices stating that You changed the files; and
  > (c) You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, and attribution notices from the Source form of the Work, excluding those notices that do not pertain to any part of the Derivative Works; and
  > (d) If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute must include a readable copy of the attribution notices contained within such NOTICE file, ..."
  
  The same section continues: "You may add Your own copyright statement to Your modifications and may provide additional or different license terms and conditions for use, reproduction, or distribution of Your modifications, or for any such Derivative Works as a whole, provided Your use, reproduction, and distribution of the Work otherwise complies with the conditions stated in this License."
- **Apache-2.0 §6** (trademarks): "This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor, except as required for reasonable and customary use in describing the origin of the Work and reproducing the content of the NOTICE file."
- **NOTICE**, https://huggingface.co/superwhisper/s1-mini/raw/main/NOTICE:
  > "S1-mini
  > Copyright 2026 Superwhisper
  >
  > This work is a derivative of Qwen3-0.6B, Copyright 2024 Alibaba Cloud,
  > licensed under the Apache License, Version 2.0.
  >
  > Any use, distribution, or integration of this model, whether unmodified or
  > as part of a derivative work or product, must continue to identify it by its
  > original name, "S1-mini" by "Superwhisper", using that exact capitalization.
  > This restates the ADDITIONAL TERM of the LICENSE file, which is the
  > operative text."
- **Model card** (https://huggingface.co/superwhisper/s1-mini) says: "you must retain the license text and the NOTICE file, and state significant changes if you redistribute a modified version. It also carries one additional term: the model must keep its name, "S1-mini" by "Superwhisper", with that exact capitalization, wherever it's used."

**What this means for the fine-tune:**
- Private fine-tuning is allowed under §2. The naming term says "any use", so even private work should keep calling the base "S1-mini" by "Superwhisper".
- A public release of the fine-tuned weights is allowed if all of these hold:
  - include the LICENSE, with the Additional Term;
  - include the NOTICE attribution;
  - mark modified files as changed;
  - identify the model as "S1-mini" by "Superwhisper", exactly capitalised, alongside any new name, e.g. "VF-Clean, a fine-tune of S1-mini by Superwhisper".
- You may add your own licence terms for your changes, but they can't override these conditions.
- The base licence covers the weights only. It says nothing about the rights to the training data, which is where Hark's terms decide the outcome.

## 5. Assessment by scenario

| Scenario | Base-model licence | Hark terms | Upstream provider terms | Verdict |
|---|---|---|---|---|
| **(a) Private fine-tune** of a non-competing 0.6B voice-cleanup model | Allowed (keep the S1-mini naming) | **Prohibited** by the Usage Policy's flat training ban (§2.1). The ToS §3 competition clause is arguable, but the outcome doesn't depend on it. | Unknown provider. If Anthropic: flat ban, also prohibited. If OpenAI or Google: probably fine for a non-competing private model. | **Blocked without Hark's written permission** |
| **(b) Public model release** | Allowed with LICENSE, NOTICE, change notices and naming | Prohibited (same ban). Distribution adds exposure. Naming Hark as the source needs brand consent (§2.6). | Distribution falls outside OpenAI's Permitted Exception. Anthropic: flat ban. Google: competition test only. | **Blocked without Hark's written permission** |
| **(c) Public dataset release** (2,561 targets and reviews) | n/a | Permission to share outputs (§2.5) needs per-item manual review, the user's name and AI-generated labels. But a dataset published *for training* "assist[s] someone" to train (ToS §3), and revenue use needs written permission. Brand clause applies. | Same unknowns; downstream users would inherit them. | **Blocked without Hark's written permission.** This carries the most exposure of the three, because it spreads the outputs to third parties. |

## 6. What is confirmed and what is unknown

**Confirmed:**
1. Hark = Hark Labs, Inc. (hark.com). Its ToS, Usage Policy, Content Policy and Privacy Policy are all dated around 1 Oct 2026, quoted above.
2. Hark's Usage Policy bans "Use inputs and outputs to train an AI model (e.g., model scraping or model distillation)". There's no competition test and no private-use exception. The ToS makes compliance with the Usage Policy a condition of using the service.
3. Uzair's ownership of outputs exists, but only "subject to your compliance with these Terms".
4. Hark doesn't name its model providers in any public policy.
5. S1-mini is Apache-2.0 plus a naming term ("S1-mini" by "Superwhisper", exact capitalisation, on any use). It permits private fine-tuning and redistribution on the conditions listed.
6. Qwen3-0.6B is Apache-2.0. Apache-2.0 places no restriction on outputs.
7. OpenAI, Google and Anthropic's commercial terms restrict training on outputs mainly where the model *competes*. Anthropic's Usage Policy goes further and bans any training on outputs without prior authorisation, and it applies to end users of products built on Claude.

**Unknown:**
1. Which model or models produced the 2,561 targets and reviews. This decides which provider rules flow down, and whether an Anthropic-style flat ban applies twice over.
2. Whether Hark would grant an exception, and in what form: private only, a non-competing model, or a public release.
3. How Hark interprets "train an AI model" for a small, single-task, non-competing model. The text doesn't distinguish model types.
4. How the 2,561 items were produced: interactively, or by scripted or automated access. ToS §3 separately bars "automated measures" and "harvest[ing] data ... from the Services".
5. Whether any inputs contain third parties' personal data, which would matter for a public dataset release. Not assessed here.

## 7. Question for Hark (draft, short)

> **To:** support@hark.com (cc legal@hark.com)
> **Subject:** Permission request: fine-tuning a small open-source model on my own Hark outputs
>
> Hello Hark team,
>
> I used Hark Pro (account: kayatuzair525@gmail.com) to write about 2,561 example outputs and reviews that clean up speech-to-text transcripts. I'd like to fine-tune S1-mini, a 0.6B transcript-normalisation model by Superwhisper, on those outputs. It's a single-task model, not a chat assistant or anything that competes with Hark.
>
> Your Acceptable Usage Policy prohibits "Use inputs and outputs to train an AI model", so I'm asking for written permission first. Could you tell me whether you would allow:
> 1. Fine-tuning the model privately, for my own use only?
> 2. Releasing the fine-tuned model weights publicly under Apache-2.0?
> 3. Releasing the dataset of outputs publicly, clearly labelled as AI-generated?
>
> Could you also say whether any third-party model terms apply that I'd need to follow? And may I name Hark as the data source on the model or dataset card?
>
> Thank you,
> Uzair Kayat

This draft is for the user to review. It hasn't been sent.

## 8. Recommendation

**BLOCKED** for all three scenarios, including private-only fine-tuning, until Hark replies in writing.

- **Why:** Hark's Usage Policy flatly prohibits training an AI model on inputs and outputs. The base licence (S1-mini) isn't the obstacle.
- **If Hark grants private-only permission:** the status becomes "cleared for private only". Then:
  - keep the "S1-mini" by "Superwhisper" naming;
  - keep the data and weights off public hubs;
  - keep Hark's written permission on file.
- **If Hark grants public release:** follow the S1-mini LICENSE, NOTICE, change-notice and naming conditions. Label the data as AI-generated, with per-item review as §2.5 requires. Name Hark only as Hark's consent allows.
- **A way around the block that doesn't depend on Hark:** regenerate the targets with a self-hosted Apache-2.0 open-weights model (e.g. a larger Qwen3), or write them by hand. Then use the existing Hark-written items only as non-training reference material, if at all. Apache-2.0 places no restriction on outputs, so this route is clear for private use and public release, subject only to the S1-mini licence conditions above.
