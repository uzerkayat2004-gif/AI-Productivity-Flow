# Human spot audit — 120 records

Fill `verdict` (PASS / FAIL / UNSURE) in HUMAN_AUDIT_SHEET.csv, or write it under each record here. Use HUMAN_AUDIT_CHECKLIST.md. Status: **NOT STARTED — no human has reviewed these records.**

## 1. TC-W03-154 · cleanup_facts · agent-written
**Settings:** locale=en-in, task=cleanup
**Transcript:**
```
the gst invoice should show eighteen percent igst not cgst plus sgst since the buyer is in maharashtra
```
**Target (what the model will learn):**
```
The GST invoice should show 18% IGST, not CGST plus SGST, since the buyer is in Maharashtra.
```
**Facts that must survive:** facts: invoice should show 18% IGST, NOT CGST plus SGST, because buyer is in Maharashtra

Verdict: ______  Error type: ______  Comment: ______

---

## 2. PT-013 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
basically the client hasn't sent the receipts for march yet
```
**Target (what the model will learn):**
```
The client hasn't sent the receipts for March yet.
```
**Facts that must survive:** —

Verdict: ______  Error type: ______  Comment: ______

---

## 3. TC-W01-022 · cleanup_facts · agent-written
**Settings:** format=numbered, task=cleanup
**Transcript:**
```
first everyone warms up on stage, then we run act one from the top, and finally um notes in the green room
```
**Target (what the model will learn):**
```
1. Everyone warms up on stage.
2. We run Act 1 from the top.
3. Notes in the green room.
```
**Facts that must survive:** facts: order warm-up -> run Act 1 from the top -> notes in green room

Verdict: ______  Error type: ______  Comment: ______

---

## 4. PT-003 · cleanup_facts · agent-written
**Settings:** header_style=full, task=cleanup
**Transcript:**
```
the quarterly vat return is due on the seventh
```
**Target (what the model will learn):**
```
The quarterly VAT return is due on the 7th.
```
**Facts that must survive:** —

Verdict: ______  Error type: ______  Comment: ______

---

## 5. TC-W01-013 · cleanup_facts · agent-written
**Settings:** header_style=full, task=cleanup
**Transcript:**
```
so the co-op meeting is uh is in the community hall this time not the barn, and bilal is bringing tea
```
**Target (what the model will learn):**
```
The co-op meeting is in the community hall this time, not the barn, and Bilal is bringing tea.
```
**Facts that must survive:** facts: meeting in community hall, NOT the barn; Bilal brings tea

Verdict: ______  Error type: ______  Comment: ______

---

## 6. TC-W04-175 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
ever notice how every mix sounds better at two am question mark yeah me too period that's why i check everything again in the morning period
```
**Target (what the model will learn):**
```
Ever notice how every mix sounds better at 2 a.m.? Yeah, me too. That's why I check everything again in the morning.
```
**Facts that must survive:** facts: rhetorical question answered by the speaker ('Yeah, me too') kept as dictated; 2 a.m.

Verdict: ______  Error type: ______  Comment: ______

---

## 7. TC-W04-136 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
wren is the master at minus fourteen lufs or minus nine
```
**Target (what the model will learn):**
```
Wren, is the master at minus 14 LUFS or minus 9?
```
**Facts that must survive:** facts: alternative minus 14 LUFS OR minus 9 kept (signs kept as spoken words); not answered

Verdict: ______  Error type: ______  Comment: ______

---

## 8. TC-W01-045 · cleanup_facts · agent-written
**Settings:** register=formal, task=cleanup
**Transcript:**
```
uh amara and i have reviewed the um the membership applications and we recommend accepting all four of the new families
```
**Target (what the model will learn):**
```
Amara and I have reviewed the membership applications, and we recommend accepting all four of the new families.
```
**Facts that must survive:** facts: recommendation (not a decision) to accept all four new families

Verdict: ______  Error type: ______  Comment: ______

---

## 9. TC-W02-116 · cleanup_facts · agent-written
**Settings:** header_style=full, task=cleanup
**Transcript:**
```
we need forty uh make that forty five chairs for the open mic night on friday
```
**Target (what the model will learn):**
```
We need 45 chairs for the open mic night on Friday.
```
**Facts that must survive:** facts: 'make that' correction: 45 chairs (40 corrected away); open mic night on Friday

Verdict: ______  Error type: ______  Comment: ______

---

## 10. TC-W03-140 · cleanup_facts · agent-written
**Settings:** locale=en-in, task=cleanup
**Transcript:**
```
jignesh the order from the delhi party is for five hundred sarees of the new zari design uh at four hundred twenty five rupees per piece no wait four hundred fifty because they want the blouse piece also attached and dispatch is in two lots first lot of three hundred by the twentieth and the remaining two hundred by the fifth of next month payment is thirty percent advance and the rest within forty five days and um they said no returns once the lot is opened so pack carefully
```
**Target (what the model will learn):**
```
Jignesh, the order from the Delhi party is for 500 sarees of the new zari design at ₹450 per piece, because they want the blouse piece also attached. Dispatch is in two lots: first lot of 300 by the 20th and the remaining 200 by the 5th of next month. Payment is 30% advance and the rest within 45 days, and they said no returns once the lot is opened, so pack carefully.
```
**Facts that must survive:** facts: 500 sarees, correction applied: ₹450/piece (₹425 corrected away; rupees spoken for this price) because blouse piece attached; dispatch 300 by the 20th, remaining 200 by the 5th of next month; 30% advance, rest within 45 days; NO returns once lot opened

Verdict: ______  Error type: ______  Comment: ______

---

## 11. TC-W02-004 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
sorry clara the fabric samples um haven't arrived yet
```
**Target (what the model will learn):**
```
Sorry, Clara, the fabric samples haven't arrived yet.
```
**Facts that must survive:** facts: 'sorry' is an apology, NOT a correction, so it stays; samples have NOT arrived yet

Verdict: ______  Error type: ______  Comment: ______

---

## 12. TC-W02-124 · cleanup_facts · agent-written
**Settings:** format=bullets, task=rewrite
**Instruction:** turn it into a setup checklist and keep the condition about the second mic
**Transcript:**
```
okay for the event setup we need two projectors no wait three projectors sixty chairs a mic for the panel or two if bongani joins and the welcome banner
```
**Target (what the model will learn):**
```
- Three projectors
- 60 chairs
- A mic for the panel, or two if Bongani joins
- The welcome banner
```
**Facts that must survive:** facts: three projectors (two corrected away by 'no wait'); 60 chairs; one mic for the panel, or two IF Bongani joins (condition kept); welcome banner

Verdict: ______  Error type: ______  Comment: ______

---

## 13. TC-W04-168 · cleanup_facts · agent-written
**Settings:** header_style=full, task=cleanup
**Transcript:**
```
halima literally asked open quote is this the final mix question mark close quote and i said not yet
```
**Target (what the model will learn):**
```
Halima literally asked, "Is this the final mix?" and I said not yet.
```
**Facts that must survive:** facts: quoted question with its own question mark inside the quotes; the speaker's answer 'not yet' is part of the dictation and kept

Verdict: ______  Error type: ______  Comment: ______

---

## 14. TC-W04-173 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
so um the export aspect ratio should be four colon five for the instagram feed post and nine colon sixteen for the stories version
```
**Target (what the model will learn):**
```
The export aspect ratio should be 4:5 for the Instagram feed post and 9:16 for the stories version.
```
**Facts that must survive:** facts: spoken 'four colon five' and 'nine colon sixteen' are aspect ratios, written 4:5 (feed) and 9:16 (stories), order kept. Waiver: the checker reads 9:16 as a clock time and cannot find the 16 inside it

Verdict: ______  Error type: ______  Comment: ______

---

## 15. TC-W02-127 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
the unit test is on the twelfth or the thirteenth i'll confirm tomorrow and the syllabus is chapters four to seven or rather four to six
```
**Target (what the model will learn):**
```
The unit test is on the 12th or the 13th; I'll confirm tomorrow. The syllabus is chapters 4 to 6.
```
**Facts that must survive:** facts: genuine alternative 12th OR 13th, both kept, speaker will confirm tomorrow; 'or rather' is a correction: chapters 4 to 6 (4 to 7 corrected away)

Verdict: ______  Error type: ______  Comment: ______

---

## 16. TC-W01-107 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
kabir says the uh the kitchen cabinets arrive tomorrow morning
```
**Target (what the model will learn):**
```
Kabir says the kitchen cabinets arrive tomorrow morning.
```
**Facts that must survive:** facts: cabinets arrive tomorrow morning (reported by Kabir)

Verdict: ______  Error type: ______  Comment: ______

---

## 17. TC-W04-154 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
for the jam session tonight bring a few things colon your audio interface comma headphones comma a long xlr cable and the usb drive with the stems
```
**Target (what the model will learn):**
```
For the jam session tonight, bring a few things: your audio interface, headphones, a long XLR cable and the USB drive with the stems.
```
**Facts that must survive:** facts: four items kept inline with the speaker's own colon and commas; cleanup keeps the dictated prose form (no bullet cue dictated), so no list is made

Verdict: ______  Error type: ______  Comment: ______

---

## 18. TC-W02-217 · cleanup_facts · agent-written
**Settings:** header_style=full, task=cleanup
**Transcript:**
```
briefing for tonight's crew um capacity is four thousand two hundred and we stop scanning at that number even if there's still a queue the support act is on at seven forty and the headliner at nine no pyro this time the fire marshal didn't sign off on it so don't let the band's crew set anything up near the stage lip and water is free at the bar for anyone who asks we've got six first aiders on site and two of them are by the mosh pit
```
**Target (what the model will learn):**
```
Briefing for tonight's crew: capacity is 4,200, and we stop scanning at that number, even if there's still a queue. The support act is on at 7:40 and the headliner at 9. No pyro this time; the fire marshal didn't sign off on it, so don't let the band's crew set anything up near the stage lip. Water is free at the bar for anyone who asks. We've got six first aiders on site, and two of them are by the mosh pit.
```
**Facts that must survive:** facts: capacity 4,200, stop scanning at that number even if a queue remains; support act 7:40, headliner 9; NO pyro (fire marshal DIDN'T sign off), DON'T let band's crew set up near stage lip; free water at bar on request; six first aiders, two by the mosh pit

Verdict: ______  Error type: ______  Comment: ______

---

## 19. TC-W03-190 · cleanup_facts · agent-written
**Settings:** locale=en-in, task=cleanup
**Transcript:**
```
for next week's tiffin menu monday is dal dhokli tuesday undhiyu no wait sev tameta because undhiyu is too heavy for weekdays wednesday is kadhi khichdi thursday the customers can choose either paneer bhurji or chana masala and friday is the special thali which is fifty rupees extra uh saturday half day only lunch no dinner and sunday closed as usual please put this on the group by saturday evening
```
**Target (what the model will learn):**
```
For next week's tiffin menu: Monday is dal dhokli. Tuesday, sev tameta, because undhiyu is too heavy for weekdays. Wednesday is kadhi khichdi. Thursday, the customers can choose either paneer bhurji or chana masala, and Friday is the special thali, which is ₹50 extra. Saturday half day, only lunch, no dinner, and Sunday closed as usual. Please put this on the group by Saturday evening.
```
**Facts that must survive:** facts: Mon dal dhokli; Tue correction: sev tameta (undhiyu corrected away, reason kept); Wed kadhi khichdi; Thu choice paneer bhurji OR chana masala; Fri special thali ₹50 extra; Sat half day, lunch only, NO dinner; Sun closed; post to group by Saturday evening; kept as prose (no list cues)

Verdict: ______  Error type: ______  Comment: ______

---

## 20. TC-W01-155 · cleanup_facts · agent-written
**Settings:** task=cleanup
**Transcript:**
```
i'm pretty sure the mango harvest will be early this year maybe the second week of may but don't book the trucks until we've checked the orchard
```
**Target (what the model will learn):**
```
I'm pretty sure the mango harvest will be early this year, maybe the second week of May, but don't book the trucks until we've checked the orchard.
```
**Facts that must survive:** facts: hedges 'pretty sure' and 'maybe' kept; restriction don't book trucks until orchard checked

Verdict: ______  Error type: ______  Comment: ______

---

## 21. TC-W04-146 · cleanup_facts · agent-written
**Settings:** header_style=full, locale=en-gb, task=cleanup
**Transcript:**
```
notes from the client call colon new paragraph they loved the harbour edits but want the shadows lifted a bit on frames twelve to eighteen period the art director said and i quote open quote less moody comma more morning close quote period new paragraph next steps colon i'll redo those seven frames by wednesday and ingrid will check the colour on the print proofs before we send anything period
```
**Target (what the model will learn):**
```
Notes from the client call:

They loved the harbour edits but want the shadows lifted a bit on frames 12 to 18. The art director said, and I quote, "Less moody, more morning."

Next steps: I'll redo those seven frames by Wednesday, and Ingrid will check the colour on the print proofs before we send anything.
```
**Facts that must survive:** facts: shadows lifted a bit on frames 12 to 18; quoted words kept exactly inside quote marks; speaker redoes seven frames by Wednesday (own commitment); Ingrid checks colour on print proofs before anything is sent; spoken paragraphs, colons and quotes applied; en-gb spelling

Verdict: ______  Error type: ______  Comment: ______

---

## 22. TC-W01-170 · cleanup_facts · agent-written
**Settings:** locale=en-gb, task=cleanup
**Transcript:**
```
the skip's getting collected friday um not thursday
```
**Target (what the model will learn):**
```
The skip's getting collected Friday, not Thursday.
```
**Facts that must survive:** facts: Friday, NOT Thursday (contrast, both days stay)

Verdict: ______  Error type: ______  Comment: ______

---

## 23. TC-W01-119 · cleanup_facts · agent-written
**Settings:** context=code, task=cleanup
**Transcript:**
```
test coverage on the payments module dropped to sixty two percent we need it back above eighty before we release uh and that's not optional
```
**Target (what the model will learn):**
```
Test coverage on the payments module dropped to 62%. We need it back above 80 before we release, and that's not optional.
```
**Facts that must survive:** facts: coverage 62%; requirement above 80 (percent not repeated by speaker, so no % added) before release; 'not optional'

Verdict: ______  Error type: ______  Comment: ______

---

## 24. TC-W03-022 · cleanup_facts · agent-written
**Settings:** locale=en-in, task=cleanup
**Transcript:**
```
notes for tomorrow first item call harsh about the gst notice reply it has to go before the twenty fifth next bullet collect the form sixteen from pooja and lakshmi next bullet the tds return for q2 is pending because the challan numbers don't match fix that first and next bullet do not file anything for the trust client until the audit is done
```
**Target (what the model will learn):**
```
Notes for tomorrow:
- Call Harsh about the GST notice reply. It has to go before the 25th.
- Collect the Form 16 from Pooja and Lakshmi.
- The TDS return for Q2 is pending because the challan numbers don't match. Fix that first.
- Do not file anything for the trust client until the audit is done.
```
**Facts that must survive:** facts: dictated list (first item / next bullet) kept as bullets; GST notice reply before the 25th; Form 16 from Pooja and Lakshmi; Q2 TDS pending, challan numbers don't match; do NOT file for trust client until audit done

Verdict: ______  Error type: ______  Comment: ______

---

## 25. TC-W02-175 · cleanup_facts · agent-written
**Settings:** locale=en-gb, task=cleanup
**Transcript:**
```
so the client brief for the nursery um they want it calm so no bright primaries maybe a soft sage or a warm grey they haven't decided the cot has to be at least sixty centimetres from the radiator and nothing can be wall mounted above it um budget's around three thousand pounds including the blackout blind but not the furniture they already bought and they'd like it done before the baby's due which is early march
```
**Target (what the model will learn):**
```
The client brief for the nursery: they want it calm, so no bright primaries, maybe a soft sage or a warm grey; they haven't decided. The cot has to be at least 60 centimetres from the radiator, and nothing can be wall-mounted above it. Budget's around £3,000, including the blackout blind but not the furniture they already bought, and they'd like it done before the baby's due, which is early March.
```
**Facts that must survive:** facts: NO bright primaries; hedge 'maybe' + alternative soft sage OR warm grey, both kept, NOT decided; cot at least 60 cm from radiator; NOTHING wall-mounted above it; budget AROUND £3,000 incl. blackout blind, NOT the furniture; done before baby's due, early March

Verdict: ______  Error type: ______  Comment: ______

---

## 26. TC-W06-247 · prompt · agent-written
**Settings:** context=ai, header_style=full, locale=en-in, task=cleanup
**Transcript:**
```
so esha's parents gave her one lakh rupees for her birthday and she's twenty two and has never invested before um she's thinking about putting it all in a nifty index fund but her uncle says gold is safer and her friend says crypto so my question is what should a beginner in india actually consider when choosing between these and is it a bad idea to put it all in at once instead of spreading it over a few months and does she have to pay tax if she sells after a year
```
**Target (what the model will learn):**
```
Esha's parents gave her ₹1 lakh for her birthday, and she's 22 and has never invested before. She's thinking about putting it all in a Nifty index fund, but her uncle says gold is safer, and her friend says crypto. So my question is: what should a beginner in India actually consider when choosing between these? Is it a bad idea to put it all in at once instead of spreading it over a few months? And does she have to pay tax if she sells after a year?
```
**Facts that must survive:** facts: Esha, ₹1 lakh (rupees spoken), 22, never invested; considering Nifty index fund; uncle says gold, friend says crypto (opinions kept attributed); three sub-questions kept; condition 'if she sells after a year' kept; no advice. Waiver: checker flags the written '1' in '₹1 lakh' as invented; the target keeps the spoken amount

Verdict: ______  Error type: ______  Comment: ______

---

## 27. TC-W06-235 · prompt · agent-written
**Settings:** context=ai, locale=en-in, task=cleanup
**Transcript:**
```
can i claim hra and home loan interest both if i live in a rented flat in pune and my own flat is in nashik
```
**Target (what the model will learn):**
```
Can I claim HRA and home loan interest both if I live in a rented flat in Pune and my own flat is in Nashik?
```
**Facts that must survive:** facts: tax question; condition (rented flat in Pune, own flat in Nashik) kept; no tax advice

Verdict: ______  Error type: ______  Comment: ______

---

## 28. TC-W06-282 · prompt · agent-written
**Settings:** context=ai, header_style=full, task=cleanup
**Transcript:**
```
my husband snores really loudly like most nights and sometimes he stops breathing for a few seconds and then gasps um he's forty six and a bit overweight and he says he's tired all day even after eight hours of sleep is this sleep apnea and what kind of doctor should he see and is there a test he can do at home first
```
**Target (what the model will learn):**
```
My husband snores really loudly, like most nights, and sometimes he stops breathing for a few seconds and then gasps. He's 46 and a bit overweight, and he says he's tired all day, even after 8 hours of sleep. Is this sleep apnea, and what kind of doctor should he see? And is there a test he can do at home first?
```
**Facts that must survive:** facts: loud snoring most nights; sometimes stops breathing a few seconds then gasps; 46, a bit overweight; tired all day even after 8 hours; three sub-questions kept; no diagnosis or referral

Verdict: ______  Error type: ______  Comment: ______

---

## 29. TC-W06-140 · prompt · agent-written
**Settings:** context=ai, task=cleanup
**Transcript:**
```
uh when i fine tune with lora my model never stops generating and just keeps going past <|im_end|> do i need to add it to the labels or is it an eos token id issue
```
**Target (what the model will learn):**
```
When I fine-tune with LoRA, my model never stops generating and just keeps going past <|im_end|>. Do I need to add it to the labels, or is it an EOS token ID issue?
```
**Facts that must survive:** facts: literal '<|im_end|>' kept verbatim; negation never stops kept; labels OR EOS-ID alternative kept; no diagnosis

Verdict: ______  Error type: ______  Comment: ______

---

## 30. TC-W06-261 · prompt · agent-written
**Settings:** context=ai, header_style=full, locale=en-in, task=cleanup
**Transcript:**
```
how many centimetres make up one inch exactly
```
**Target (what the model will learn):**
```
How many centimetres make up one inch exactly?
```
**Facts that must survive:** facts: tempting fact question; question only

Verdict: ______  Error type: ______  Comment: ______

---

## 31. TC-W05-032 · prompt · agent-written
**Settings:** context=ai, format=prompt, task=prompt
**Instruction:** make it a clear prompt for a coding AI, keep my exact file name, and apply my corrections
**Transcript:**
```
so shreya sent me the survey export and i need a notebook for it um first load the csv it's called survey underscore final underscore v2 dot csv then uh drop the test responses those are the rows where the email ends with at example dot com and then i want the average satisfaction score by region as a horizontal bar chart sorted highest to lowest sorry lowest to highest actually no keep it highest to lowest and um don't show the respondent names anywhere in the output because of privacy and keep it to pandas and matplotlib nothing else
```
**Target (what the model will learn):**
```
Create a notebook for the survey export Shreya sent me. First, load survey_final_v2.csv. Then drop the test responses, which are the rows where the email ends with @example.com. Plot the average satisfaction score by region as a horizontal bar chart sorted from highest to lowest. Do not show respondent names anywhere in the output, for privacy reasons. Use only pandas and matplotlib, nothing else.
```
**Facts that must survive:** facts: final sort order highest to lowest (speaker reverted the 'lowest to highest' correction); survey_final_v2.csv; test rows = emails ending @example.com; no respondent names; only pandas and matplotlib

Verdict: ______  Error type: ______  Comment: ______

---

## 32. TC-W05-259 · prompt · agent-written
**Settings:** format=prompt, task=prompt
**Transcript:**
```
suggest three automations for a smart home with just motion sensors and smart plugs
```
**Target (what the model will learn):**
```
Suggest 3 automations for a smart home that has just motion sensors and smart plugs.
```
**Facts that must survive:** home automation: 3 suggestions; devices limited to motion sensors and smart plugs ('just' kept)

Verdict: ______  Error type: ______  Comment: ______

---

## 33. TC-W05-106 · prompt · agent-written
**Settings:** format=prompt, task=prompt
**Transcript:**
```
make me a six week study plan for the aws solutions architect associate exam i can study about an hour on weekdays and three hours on saturdays sundays are off
```
**Target (what the model will learn):**
```
Make a 6-week study plan for the AWS Solutions Architect Associate exam. I can study about an hour on weekdays and 3 hours on Saturdays. Sundays are off.
```
**Facts that must survive:** study plan: 6 weeks; 'about an hour' on weekdays (hedge kept); 3 hours Saturdays; Sundays off; plan not written

Verdict: ______  Error type: ______  Comment: ______

---

## 34. TC-W05-102 · prompt · agent-written
**Settings:** format=prompt, task=prompt
**Transcript:**
```
sql query for the top ten customers by total order value from the orders table for twenty twenty five
```
**Target (what the model will learn):**
```
Write a SQL query that returns the top 10 customers by total order value from the orders table for 2025.
```
**Facts that must survive:** facts: top 10; by total order value; orders table; year 2025

Verdict: ______  Error type: ______  Comment: ______

---

## 35. TC-W06-102 · prompt · agent-written
**Settings:** context=ai, format=prompt, task=prompt
**Transcript:**
```
capital of new zealand and like why isn't it auckland or christchurch
```
**Target (what the model will learn):**
```
Tell me the capital of New Zealand and explain why it isn't Auckland or Christchurch.
```
**Facts that must survive:** facts: same underlying question as TC-W06-101 as a prompt; negation isn't kept; Auckland OR Christchurch both kept; no answer

Verdict: ______  Error type: ______  Comment: ______

---

## 36. TC-W06-146 · prompt · agent-written
**Settings:** context=ai, format=prompt, locale=en-in, task=prompt
**Instruction:** turn it into a prompt, keep the distance and the 15 minute limit, and don't add checks that need tools
**Transcript:**
```
varun here so i'm driving from ahmedabad to udaipur next saturday it's about two hundred and sixty kilometres in my maruti swift diesel and the car hasn't been serviced in like eight months um i want a pre trip checklist of things i can check myself in the parking lot like tyres coolant oil wipers that sort of thing and tell me which ones i shouldn't skip if i only have fifteen minutes and don't include anything that needs tools because i don't have any
```
**Target (what the model will learn):**
```
Create a pre-trip checklist of things I can check myself in the parking lot, like tyres, coolant, oil and wipers, and tell me which ones I shouldn't skip if I only have 15 minutes. Don't include anything that needs tools, because I don't have any. I'm Varun, and I'm driving from Ahmedabad to Udaipur next Saturday, about 260 km, in my Maruti Swift diesel. The car hasn't been serviced in about eight months.
```
**Facts that must survive:** facts: Varun; Ahmedabad to Udaipur next Saturday; about 260 km; Maruti Swift diesel; not serviced in 'like eight months' = about eight months; examples tyres/coolant/oil/wipers kept as examples ('like'); which not to skip if only 15 minutes (condition kept); negations hasn't/shouldn't/don't include/don't have kept; no checklist written

Verdict: ______  Error type: ______  Comment: ______

---

## 37. TC-W06-211 · prompt · agent-written
**Settings:** context=code, format=prompt, task=prompt
**Instruction:** keep that I'm not sure about the cause, and don't add steps beyond what I asked
**Transcript:**
```
my training script is supposed to compute loss only on the assistant's answer plus the <|im_end|> token but i think it's also including the system prompt i'm not completely sure um write me a debugging checklist and a small python snippet that prints which tokens have labels not equal to minus one hundred so i can confirm it and don't rewrite my whole training loop
```
**Target (what the model will learn):**
```
Write me a debugging checklist and a small Python snippet that prints which tokens have labels not equal to -100, so I can confirm whether my training script computes loss correctly. It's supposed to compute loss only on the assistant's answer plus the <|im_end|> token, but I think it's also including the system prompt; I'm not completely sure. Don't rewrite my whole training loop.
```
**Facts that must survive:** facts: literal '<|im_end|>' kept verbatim; loss should be on answer + <|im_end|> only; suspected system-prompt leak kept as 'I think' and 'I'm not completely sure' (uncertainty kept); labels not equal to -100; negation don't rewrite the whole loop kept; no snippet written

Verdict: ______  Error type: ______  Comment: ______

---

## 38. TC-W06-004 · prompt · agent-written
**Settings:** context=ai, task=rewrite
**Instruction:** tidy this into one clear question for ChatGPT, don't answer it and keep both of my options
**Transcript:**
```
ok so like is it better to do cardio before weights or after weights if i'm trying to build muscle i do like four days a week
```
**Target (what the model will learn):**
```
I train about four days a week and I'm trying to build muscle. Is it better to do cardio before or after weights?
```
**Facts that must survive:** facts: 'like four days' = about four days a week (hedge kept as 'about'); before OR after weights alternative kept; goal build muscle; no answer

Verdict: ______  Error type: ______  Comment: ______

---

## 39. TC-W05-036 · prompt · agent-written
**Settings:** format=prompt, locale=en-gb, task=prompt
**Instruction:** make it a prompt, keep the dates and percentages as I said them, don't add sections
**Transcript:**
```
so elodie wants a newsletter draft for the end of season sale on our linen shirts um it goes out on the twenty eighth sorry twenty seventh and the sale is forty percent off on linen shirts and twenty five percent on everything else um she wants a short intro two product highlights the sand linen shirt and the olive overshirt and a closing line with the shop now button uh don't use the word cheap anywhere and don't mention the sale ending date because we might extend it
```
**Target (what the model will learn):**
```
Write a newsletter draft for Elodie for the end-of-season sale on our linen shirts. It goes out on the 27th. The sale is 40% off linen shirts and 25% off everything else. Include a short intro, 2 product highlights (the Sand Linen Shirt and the Olive Overshirt), and a closing line with a Shop Now button. Do not use the word "cheap" anywhere, and do not mention the sale end date, because we might extend it.
```
**Facts that must survive:** facts: self-correction: goes out on the 27th (not 28th); 40% off linen shirts, 25% off everything else; 2 highlights named; never 'cheap'; no end date because they 'might' extend (hedge kept)

Verdict: ______  Error type: ______  Comment: ______

---

## 40. TC-W06-257 · prompt · agent-written
**Settings:** context=code, format=prompt, task=prompt
**Transcript:**
```
i'm parsing outputs from a reasoning model and sometimes it never closes the thinking block so there's a <think> but no </think> um write a python function that returns the final answer if both tags are there returns everything after <think> with a warning if only the opening tag is there and returns the whole text unchanged if there are no tags at all and add three unit tests
```
**Target (what the model will learn):**
```
Write a Python function for parsing outputs from a reasoning model, plus three unit tests. Sometimes the model never closes the thinking block, so there's a <think> but no </think>. If both tags are there, the function should return the final answer. If only the opening tag is there, it should return everything after <think> with a warning. If there are no tags at all, it should return the whole text unchanged.
```
**Facts that must survive:** facts: literal '<think>' and '</think>' kept verbatim; three conditional behaviours kept, each with its own condition (both tags -> final answer; only opening -> everything after <think> + warning; no tags -> whole text unchanged); three unit tests; negations never / no </think> / no tags kept; no code written

Verdict: ______  Error type: ______  Comment: ______

---

## 41. TC-W05-014 · prompt · agent-written
**Settings:** format=prompt, task=prompt
**Transcript:**
```
write a welcome email for new subscribers of our sneaker brand mention the ten percent off code welcome ten valid for seven days and keep it playful
```
**Target (what the model will learn):**
```
Write a playful welcome email for new subscribers to our sneaker brand. Mention the 10% off code WELCOME10, valid for 7 days.
```
**Facts that must survive:** facts: 10% off; code WELCOME10; valid 7 days; playful tone requested by speaker

Verdict: ______  Error type: ______  Comment: ______

---

## 42. PT-045 · email · agent-written
**Settings:** format=email, header_style=full, register=formal, sender=Vikram Shah, task=rewrite
**Transcript:**
```
let the client know their tax return was filed today and no payment is due
```
**Target (what the model will learn):**
```
Hello,

Your tax return was filed today, and no payment is due.

Regards,
Vikram Shah
```
**Facts that must survive:** —

Verdict: ______  Error type: ______  Comment: ______

---

## 43. TC-W07-214 · email · agent-written
**Settings:** format=email, header_style=full, sender=Camille, task=rewrite
**Transcript:**
```
hi everyone, change of plan for next week's client sessions. the kickoff with the hotel group moves from monday at ten to tuesday at two thirty, same room. the review with the museum team stays on wednesday at eleven but it's now on zoom not in person, link to follow. and the thursday site walk is cancelled because the scaffolding isn't up yet, we'll pick a new date once the contractor confirms. if any of this clashes with something let me know today
```
**Target (what the model will learn):**
```
Hi everyone,

There's a change of plan for next week's client sessions.

The kickoff with the hotel group moves from Monday at 10 to Tuesday at 2:30, in the same room.

The review with the museum team stays on Wednesday at 11, but it's now on Zoom, not in person. The link will follow.

The Thursday site walk is cancelled because the scaffolding isn't up yet. We'll pick a new date once the contractor confirms.

If any of this clashes with something, let me know today.

Best,
Camille
```
**Facts that must survive:** facts: kickoff Mon 10 -> Tue 2:30 same room; museum review stays Wed 11, now Zoom NOT in person, link to follow; Thursday site walk cancelled (scaffolding not up), new date once contractor confirms; clashes -> tell speaker today; no a.m./p.m. added

Verdict: ______  Error type: ______  Comment: ______

---

## 44. TC-W07-114 · email · agent-written
**Settings:** format=email, task=rewrite
**Transcript:**
```
hi so your trial ends on friday. to keep your data you need to pick a plan at app dot tasknest dot io slash billing before then
```
**Target (what the model will learn):**
```
Hi,

Your trial ends on Friday. To keep your data, you need to pick a plan at app.tasknest.io/billing before then.
```
**Facts that must survive:** facts: trial ends Friday; must pick plan before then to keep data; spoken URL written as app.tasknest.io/billing

Verdict: ______  Error type: ______  Comment: ______

---

## 45. TC-W08-037 · email · agent-written
**Settings:** format=email, task=rewrite, wording=keep
**Instruction:** make it an email to Gaurav but keep my exact words, just add the greeting
**Transcript:**
```
uh the policy lapsed on the third because the auto debit failed twice it can be revived within sixty days without a fresh medical check
```
**Target (what the model will learn):**
```
Hi Gaurav,

The policy lapsed on the 3rd because the auto debit failed twice. It can be revived within 60 days without a fresh medical check.
```
**Facts that must survive:** facts: lapsed on the 3rd, auto debit failed twice; revivable within 60 days without fresh medical check; wording kept

Verdict: ______  Error type: ______  Comment: ______

---

## 46. TC-W07-232 · email · agent-written
**Settings:** format=email, recipient=Oliver, register=formal, sender=Tamsin, task=rewrite
**Instruction:** keep the hedge and the condition exactly, and no subject line
**Transcript:**
```
so the medical device manual is about two hundred pages and if the regulatory glossary is ready by the tenth we should be able to deliver the reviewed german version by the end of next month, but i can't guarantee that until we see the glossary
```
**Target (what the model will learn):**
```
Dear Oliver,

The medical device manual is about 200 pages. If the regulatory glossary is ready by the 10th, we should be able to deliver the reviewed German version by the end of next month. However, I cannot guarantee that until we see the glossary.

Regards,
Tamsin
```
**Facts that must survive:** facts: manual ABOUT 200 pages; IF glossary ready by 10th -> SHOULD deliver reviewed German version by end of next month; can't guarantee until glossary seen; model doesn't translate, it reports the delivery

Verdict: ______  Error type: ______  Comment: ______

---

## 47. TC-W08-187 · email · agent-written
**Settings:** format=email, header_style=full, locale=en-in, task=rewrite
**Rules:** Use British spelling.
**Instruction:** keep both names in the greeting, keep it neutral, and don't add any next steps I didn't say
**Transcript:**
```
hi sophie and dimitri um so update from the client meeting this morning they've agreed to extend the project by four weeks but the budget stays at the original eighteen lakh so we need to reduce the number of site visits from twelve to eight uh sophie can you redo the visit plan by thursday and dimitri can you update the resourcing sheet um they also don't want any changes to the final presentation date which is still the ninth of december thanks andre
```
**Target (what the model will learn):**
```
Hi Sophie and Dimitri,

An update from the client meeting this morning: they've agreed to extend the project by four weeks, but the budget stays at the original 18 lakh, so we need to reduce the number of site visits from 12 to 8. Sophie, can you redo the visit plan by Thursday? Dimitri, can you update the resourcing sheet?

They also don't want any changes to the final presentation date, which is still December 9.

Thanks,
Andre
```
**Facts that must survive:** facts: client meeting this morning; project extended four weeks; budget stays at original 18 lakh (no currency spoken, so no ₹); site visits 12 -> 8; Sophie redoes visit plan by Thursday; Dimitri updates resourcing sheet; NO changes to final presentation date, still December 9; speaker dictated own sign-off 'thanks andre'. Waiver: checker reads spoken 'eighteen lakh' as 1800000 while the target writes '18 lakh' as spoken

Verdict: ______  Error type: ______  Comment: ______

---

## 48. TC-W08-164 · email · agent-written
**Settings:** format=email, header_style=full, locale=en-in, recipient=Mr. Vivek Iyer, register=formal, task=rewrite
**Transcript:**
```
your request to shift the connection to your new address in whitefield has been approved the shifting charge is five hundred rupees and the technician will visit on the twenty third between eleven and four
```
**Target (what the model will learn):**
```
Dear Mr. Vivek Iyer,

Your request to shift the connection to your new address in Whitefield has been approved. The shifting charge is ₹500, and the technician will visit on the 23rd between 11 and 4.
```
**Facts that must survive:** facts: shifting request to Whitefield approved; charge ₹500; technician visit on the 23rd between 11 and 4

Verdict: ______  Error type: ______  Comment: ______

---

## 49. TC-W07-130 · email · agent-written
**Settings:** format=email, register=formal, task=rewrite
**Instruction:** formal email to the vendor, keep every line item and the total exactly, plain text only
**Transcript:**
```
uh we'd like to confirm the order for the equipment. the items are, four rowing machines at nine hundred dollars each, ten kettlebell sets at a hundred and twenty each, and two cable stations at two thousand two hundred each. total nine thousand two hundred dollars. delivery to the north branch please
```
**Target (what the model will learn):**
```
Hello,

We would like to confirm the order for the equipment. The items are:

- 4 rowing machines at $900 each
- 10 kettlebell sets at $120 each
- 2 cable stations at $2,200 each

The total is $9,200. Please deliver to the north branch.
```
**Facts that must survive:** facts: 4 x $900, 10 x $120, 2 x $2,200 (dollars spoken once, $ applied to every price in the same list); total $9,200 (arithmetic checks); deliver to north branch; counts as digits throughout the priced list for consistency

Verdict: ______  Error type: ______  Comment: ______

---

## 50. TC-W08-040 · email · agent-written
**Settings:** format=email, register=casual, task=rewrite
**Transcript:**
```
hey meenal no wait this is for uma can you bring the banner and the registration sheets to the park tomorrow by eight thirty
```
**Target (what the model will learn):**
```
Hi Uma,

Can you bring the banner and the registration sheets to the park tomorrow by 8:30?
```
**Facts that must survive:** facts: recipient self-corrected Meenal -> Uma; bring banner + registration sheets to park tomorrow by 8:30

Verdict: ______  Error type: ______  Comment: ______

---

## 51. TC-W08-133 · email · agent-written
**Settings:** format=email, recipient=Meenal, sender=Gaurav, task=rewrite
**Transcript:**
```
your annual multi trip policy renews on the first and covers trips of up to forty five days each
```
**Target (what the model will learn):**
```
Hi Meenal,

Your annual multi-trip policy renews on the 1st and covers trips of up to 45 days each.

Best,
Gaurav
```
**Facts that must survive:** facts: annual multi-trip policy renews on the 1st; covers trips up to 45 days each

Verdict: ______  Error type: ______  Comment: ______

---

## 52. TC-W07-028 · email · agent-written
**Settings:** format=email, header_style=full, locale=en-gb, recipient=Rania, register=formal, task=rewrite
**Transcript:**
```
the design fee for stage two is fifteen percent of construction cost and is payable in three instalments
```
**Target (what the model will learn):**
```
Dear Rania,

The design fee for Stage 2 is 15% of the construction cost and is payable in three instalments.
```
**Facts that must survive:** facts: Stage 2 fee = 15% of construction cost, three instalments

Verdict: ______  Error type: ______  Comment: ______

---

## 53. TC-W07-215 · email · agent-written
**Settings:** format=email, locale=en-gb, recipient=Gustavo, register=formal, sender=Rania, task=rewrite
**Transcript:**
```
gustavo following your interviews last week we're pleased to offer you the position of senior localization engineer. the start date we discussed, the second of february, works for us. the full terms including the salary we talked about are set out in the attached contract. please read it carefully, sign it and send it back by the sixteenth of january. the offer is subject to two satisfactory references, and we'll contact your referees once you've accepted. if you have any questions about the terms contact noor in hr
```
**Target (what the model will learn):**
```
Dear Gustavo,

Following your interviews last week, we are pleased to offer you the position of Senior Localization Engineer. The start date we discussed, 2 February, works for us.

The full terms, including the salary we talked about, are set out in the attached contract. Please read it carefully, sign it and send it back by 16 January.

The offer is subject to two satisfactory references, and we will contact your referees once you have accepted.

If you have any questions about the terms, please contact Noor in HR.

Regards,
Rania
```
**Facts that must survive:** facts: offer Senior Localization Engineer; start 2 February; salary only referenced, in attached contract (no figure invented); sign and return by 16 January; subject to two satisfactory references; referees contacted after acceptance; questions -> Noor in HR

Verdict: ______  Error type: ______  Comment: ______

---

## 54. TC-W08-150 · email · agent-written
**Settings:** format=email, sender=Saanvi, task=rewrite
**Transcript:**
```
hello to all the saturday kitchen volunteers um we served two hundred and sixty meals last weekend uh the kitchen will be closed next saturday for a gas line inspection so please don't come in we'll resume on the twenty sixth
```
**Target (what the model will learn):**
```
Hi Saturday kitchen volunteers,

We served 260 meals last weekend. The kitchen will be closed next Saturday for a gas line inspection, so please don't come in. We'll resume on the 26th.

Best,
Saanvi
```
**Facts that must survive:** facts: named audience kept; 260 meals last weekend; closed next Saturday (gas line inspection), DON'T come in; resume on the 26th

Verdict: ______  Error type: ______  Comment: ______

---

## 55. TC-W07-009 · email · agent-written
**Settings:** format=email, recipient=Kavya, sender=Manish, task=rewrite, tone=confident
**Transcript:**
```
kavya we need to move the restock order from two hundred units to three fifty because the sale week starts on the third and uh we can't run out of the medium size again
```
**Target (what the model will learn):**
```
Hi Kavya,

We need to increase the restock order from 200 units to 350. The sale week starts on the 3rd, and we can't run out of the medium size again.

Best,
Manish
```
**Facts that must survive:** facts: restock 200 -> 350 units; sale week starts on the 3rd; can't run out of medium again

Verdict: ______  Error type: ______  Comment: ______

---

## 56. TC-W10-110 · messages · agent-written
**Settings:** context=chat, format=message, header_style=full, task=rewrite
**Transcript:**
```
can someone ask callum whether the cabin booking includes breakfast or if we have to pay extra for it
```
**Target (what the model will learn):**
```
Can someone ask Callum whether the cabin booking includes breakfast or if we have to pay extra for it?
```
**Facts that must survive:** facts: speaker asks the group to ask Callum; Callum is NOT the addressee, so no vocative and no direct question to him; both alternatives (included OR pay extra) kept; not answered

Verdict: ______  Error type: ______  Comment: ______

---

## 57. TC-W10-181 · messages · agent-written
**Settings:** context=chat, format=message, header_style=full, task=rewrite
**Rules:** Never write 'ASAP'; write 'as soon as possible'.
**Transcript:**
```
can you send the final copy asap the client meeting got moved up to tomorrow morning
```
**Target (what the model will learn):**
```
Can you send the final copy as soon as possible? The client meeting got moved up to tomorrow morning.
```
**Facts that must survive:** facts: urgency kept ('as soon as possible'); client meeting moved up to tomorrow morning

Verdict: ______  Error type: ______  Comment: ______

---

## 58. TC-W09-187 · messages · agent-written
**Settings:** context=work, format=auto, task=rewrite
**Instruction:** bullet the three blockers with one intro line, nothing else
**Transcript:**
```
okay so for the pi's update um the experiment is stuck and it's basically three things holding it up the first is the incubator's co two sensor which has been reading wrong since monday facilities say a technician might come on thursday second the ethics amendment for the new cohort hasn't been approved yet the committee meets on the nineteenth and third the mice from the supplier are delayed to the twenty fourth so even if everything else is fixed we can't start before then
```
**Target (what the model will learn):**
```
The experiment is stuck on three things:
- The incubator's CO2 sensor has been reading wrong since Monday; facilities say a technician might come on Thursday
- The ethics amendment for the new cohort hasn't been approved yet; the committee meets on the 19th
- The mice from the supplier are delayed to the 24th, so even if everything else is fixed, we can't start before then
```
**Facts that must survive:** facts: 3 blockers: CO2 sensor wrong since Monday, technician 'might' come Thursday (hedge); ethics amendment not yet approved, committee meets 19th; mice delayed to 24th so can't start before then even if rest fixed; bullets instructed; WAIVER: checker reads 'the first is' as the number 1

Verdict: ______  Error type: ______  Comment: ______

---

## 59. TC-W09-032 · messages · agent-written
**Settings:** context=work, format=message, task=rewrite
**Instruction:** short status update, under 60 words, and keep every number
**Transcript:**
```
okay status update on the migration um we moved about eighty percent of the accounts to the new region over the weekend the remaining twenty percent are the enterprise ones and those need a maintenance window so we're not touching them until the customers sign off uh support saw maybe a dozen tickets about slow dashboards most of them closed themselves ritu is tracking the rest
```
**Target (what the model will learn):**
```
Migration status: about 80% of accounts moved to the new region over the weekend. The remaining 20% are enterprise accounts that need a maintenance window, so we're not touching them until the customers sign off. Support saw maybe a dozen tickets about slow dashboards; most closed themselves and Ritu is tracking the rest.
```
**Facts that must survive:** facts: about 80% moved over weekend; remaining 20% enterprise need maintenance window, not touched until customers sign off; maybe a dozen slow-dashboard tickets (hedge), most closed, Ritu tracking rest

Verdict: ______  Error type: ______  Comment: ______

---

## 60. TC-W09-172 · messages · agent-written
**Settings:** context=chat, format=message, task=rewrite
**Instruction:** make it a clear, professional reply to the customer, no promises beyond what I said, keep the ticket number
**Transcript:**
```
so there's a double charge on your card two payments of forty nine dollars on the eighth one is a duplicate i passed it to billing ticket b dash seven seven zero three they'll process the refund
```
**Target (what the model will learn):**
```
There's a double charge on your card: two payments of $49 on the 8th, one of which is a duplicate. I've passed this to our billing team under ticket B-7703, and they'll process the refund.
```
**Facts that must survive:** facts: two $49 payments on the 8th, one duplicate; passed to billing, ticket B-7703; billing will process refund (dictated); no timeline or apology added; WAIVER: pronoun 'one is a duplicate' counted as the number 1 (known 'one' gap)

Verdict: ______  Error type: ______  Comment: ______

---

## 61. TC-W09-221 · messages · agent-written
**Settings:** context=work, format=message, header_style=full, locale=en-gb, task=rewrite
**Transcript:**
```
lena the chapter four cutscene audio is out of sync only in the french build
```
**Target (what the model will learn):**
```
Lena, the chapter 4 cutscene audio is out of sync, only in the French build.
```
**Facts that must survive:** facts: chapter 4 cutscene audio out of sync, French build only

Verdict: ______  Error type: ______  Comment: ______

---

## 62. TC-W09-154 · messages · agent-written
**Settings:** context=work, format=message, task=rewrite
**Instruction:** tighten it up, keep the branch names and ticket number exactly, no extra asks
**Transcript:**
```
so jake i've got two prs up um the first one is on perf slash texture dash streaming that's the big one it cuts load times on the open world map by about a third and the second is on fix slash ui dash scaling for the ultrawide bug g s dash five one eight uh the second one is tiny so maybe do that one first and for the big one please just check the memory numbers on the low end preset i didn't have time to test that
```
**Target (what the model will learn):**
```
Jake, I've got two PRs up. The first, on perf/texture-streaming, is the big one: it cuts load times on the open world map by about a third. The second, on fix/ui-scaling, is for the ultrawide bug GS-518. It's tiny, so maybe do it first. For the big one, please check the memory numbers on the low-end preset; I didn't have time to test that.
```
**Facts that must survive:** facts: two PRs: perf/texture-streaming (big, cuts open-world load times by about a third) and fix/ui-scaling (ultrawide bug GS-518, tiny, 'maybe' review first); check memory numbers on low-end preset, speaker didn't test it; no added asks

Verdict: ______  Error type: ______  Comment: ______

---

## 63. TC-W09-023 · messages · agent-written
**Settings:** context=work, format=message, task=rewrite
**Instruction:** tighten it up, keep the names and times exactly, and don't add anything
**Transcript:**
```
hey everyone so for election night um here's the plan chen is on the live blog from six p m to midnight swati takes over the results tables uh at nine and stays till they're final um pablo and i are in the field at the counting center and we'll file short updates every hour or so we're not calling any races ourselves we only report what the election commission announces and uh if the feed goes down call me directly don't post anything unverified
```
**Target (what the model will learn):**
```
Hey everyone, here's the plan for election night. Chen is on the live blog from 6 p.m. to midnight. Swati takes over the results tables at 9 and stays till they're final. Pablo and I are in the field at the counting center and will file short updates every hour or so. We're not calling any races ourselves; we only report what the election commission announces. If the feed goes down, call me directly. Don't post anything unverified.
```
**Facts that must survive:** facts: Chen live blog 6 p.m.-midnight; Swati results tables at 9 until final; Pablo + speaker in field, updates every hour or so; not calling races; only report commission announcements; if feed down call speaker; don't post unverified

Verdict: ______  Error type: ______  Comment: ______

---

## 64. TC-W09-108 · messages · agent-written
**Settings:** context=chat, format=message, task=rewrite
**Transcript:**
```
musa the headline should say eleven injured sorry fourteen injured the police updated it
```
**Target (what the model will learn):**
```
Musa, the headline should say 14 injured. The police updated it.
```
**Facts that must survive:** facts: self-correction 11 -> 14 applied; police updated the figure

Verdict: ______  Error type: ______  Comment: ______

---

## 65. TC-W10-022 · messages · agent-written
**Settings:** context=chat, format=message, header_style=full, locale=en-in, task=rewrite, tone=friendly
**Transcript:**
```
hi karim this is from flat four oh two um so i know you've got the renovation going on and that's totally fine but the drilling has been starting at like seven thirty in the morning and the society rules say no work before ten on weekdays my mum's not been well so she's been resting in the mornings could you please ask the workers to start after ten thanks a lot
```
**Target (what the model will learn):**
```
Hi Karim, this is from flat 402. I know you've got the renovation going on, and that's totally fine, but the drilling has been starting at around 7:30 in the morning, and the society rules say no work before 10 on weekdays. My mum hasn't been well, so she's been resting in the mornings. Could you please ask the workers to start after 10? Thanks a lot.
```
**Facts that must survive:** facts: flat 402; drilling starting around 7:30 a.m.; society rule no work before 10 on weekdays; mum not well; request start after 10; greeting and 'thanks a lot' dictated, no other sign-off or name added; waiver: checker reads spoken flat number 'four oh two' as 4 and 2, so it flags 402 as invented and 4/2 as missing

Verdict: ______  Error type: ______  Comment: ______

---

## 66. TC-W10-129 · messages · agent-written
**Settings:** context=chat, format=message, task=rewrite, tone=playful
**Rules:** Write 'okay', never 'OK'. | No exclamation marks.
**Transcript:**
```
ok so the parrot learned to say good morning but only at like four am
```
**Target (what the model will learn):**
```
Okay, so the parrot learned to say good morning, but only at like 4 a.m.
```
**Facts that must survive:** facts: parrot says good morning only at like 4 a.m. ('like' = about, kept); saved rules: 'okay' spelling, no exclamation marks even with playful tone

Verdict: ______  Error type: ______  Comment: ______

---

## 67. TC-W10-186 · messages · agent-written
**Settings:** context=personal, format=message, header_style=full, locale=en-in, task=rewrite, tone=empathetic
**Transcript:**
```
mrs kapoor we were so sorry to hear that uncle passed away um if you need help with anything at all over the next few days please just knock
```
**Target (what the model will learn):**
```
Mrs. Kapoor, we were so sorry to hear that uncle passed away. If you need help with anything at all over the next few days, please just knock.
```
**Facts that must survive:** facts: condolence; the offer of help over the next few days is dictated and stays conditional ('if you need'); no funeral or other detail added

Verdict: ______  Error type: ______  Comment: ______

---

## 68. TC-W09-010 · messages · agent-written
**Settings:** context=work, format=message, header_style=full, task=rewrite
**Transcript:**
```
the delivery truck is running about forty minutes late so receiving starts at eleven instead
```
**Target (what the model will learn):**
```
The delivery truck is running about 40 minutes late, so receiving starts at 11 instead.
```
**Facts that must survive:** facts: about 40 minutes late (approximate kept); receiving at 11

Verdict: ______  Error type: ______  Comment: ______

---

## 69. TC-W10-155 · messages · agent-written
**Settings:** context=chat, format=message, header_style=full, locale=en-in, task=rewrite
**Transcript:**
```
so for the goa trip in december here's what i've figured out um flights are booked for the twenty third returning on the twenty eighth we're staying at the same place in candolim as last time aarav and ishita share the sea facing room the rest of us are in the two cottages uh car rental is about eighteen hundred a day so i'm thinking we take one car not two and use scooters for short trips if anyone has dietary stuff tell nora she's sorting the christmas dinner
```
**Target (what the model will learn):**
```
For the Goa trip in December, here's what I've figured out. Flights are booked for the 23rd, returning on the 28th. We're staying at the same place in Candolim as last time: Aarav and Ishita share the sea-facing room, and the rest of us are in the two cottages. Car rental is about 1,800 a day, so I'm thinking we take one car, not two, and use scooters for short trips. If anyone has dietary stuff, tell Nora; she's sorting the Christmas dinner.
```
**Facts that must survive:** facts: Goa trip in December; flights 23rd, return 28th; same place in Candolim; Aarav and Ishita sea-facing room, rest in the two cottages; car about 1,800 a day (no currency spoken); hedged proposal 'I'm thinking' one car NOT two plus scooters; if dietary needs, tell Nora (she's sorting Christmas dinner)

Verdict: ______  Error type: ______  Comment: ______

---

## 70. TC-W11-117 · notes_format · agent-written
**Settings:** format=prose, task=rewrite
**Transcript:**
```
first preheat the oven to two hundred then toss the potatoes in oil and salt then roast them for forty minutes turning once halfway
```
**Target (what the model will learn):**
```
First, preheat the oven to 200, then toss the potatoes in oil and salt and roast them for 40 minutes, turning once halfway.
```
**Facts that must survive:** facts: oven to 200 (no unit spoken, none added); roast 40 minutes, turn once halfway; Format prose beats the order cues -> one sentence, no numbering

Verdict: ______  Error type: ______  Comment: ______

---

## 71. TC-W11-163 · notes_format · agent-written
**Settings:** format=email, recipient=Kiran, register=casual, sender=Rhea, task=rewrite
**Transcript:**
```
hey kiran so for saturday's hike could you bring these the first aid kit the map and some snacks for the group we're meeting at the car park at seven
```
**Target (what the model will learn):**
```
Hey Kiran,

For Saturday's hike, could you bring these:
- The first aid kit
- The map
- Some snacks for the group

We're meeting at the car park at 7.

Thanks,
Rhea
```
**Facts that must survive:** facts: three items to bring (cue 'bring these'); meet at the car park at 7; casual register keeps the dictated 'hey'; sign-off from [Sender]

Verdict: ______  Error type: ______  Comment: ______

---

## 72. TC-W12-174 · notes_format · agent-written
**Settings:** format=note, locale=en-gb, task=rewrite
**Transcript:**
```
travel notes for edinburgh train at six forty from kings cross seat booked coach c hotel is a ten minute walk from the venue check in after three expenses go to freya not finance
```
**Target (what the model will learn):**
```
Travel notes for Edinburgh
Train at 6:40 from King's Cross; seat booked in coach C.
Hotel is a 10-minute walk from the venue; check-in after 3.
Expenses go to Freya, not finance.
```
**Facts that must survive:** facts: train 6:40 from King's Cross, seat in coach C; hotel 10-minute walk from venue; check-in after 3; expenses to Freya, NOT finance; framing 'travel notes for Edinburgh' kept; terse lines

Verdict: ______  Error type: ______  Comment: ______

---

## 73. TC-W12-181 · notes_format · agent-written
**Settings:** format=prose, header_style=full, locale=en-in, task=rewrite
**Transcript:**
```
big announcement for our users tallyroom is now available on android um it has everything the ios version has shared bills reminders and the monthly summary. if you were on the beta your data moves over automatically you don't need to do anything. the price is still ninety nine rupees a month per household and the first month is free for everyone who signs up before diwali
```
**Target (what the model will learn):**
```
Big announcement for our users: Tallyroom is now available on Android. It has everything the iOS version has — shared bills, reminders and the monthly summary.

If you were on the beta, your data moves over automatically. You don't need to do anything.

The price is still ₹99 a month per household, and the first month is free for everyone who signs up before Diwali.
```
**Facts that must survive:** facts: now on Android with iOS parity (shared bills, reminders, monthly summary); IF on beta, data moves automatically, no action needed; price still ₹99 a month per household (rupees spoken); first month free only for sign-ups before Diwali (condition); plain paragraphs, features stay inline

Verdict: ______  Error type: ______  Comment: ______

---

## 74. TC-W11-188 · notes_format · agent-written
**Settings:** format=note, header_style=full, task=rewrite
**Transcript:**
```
chem revision note um the three types of bonds are ionic covalent and metallic ionic is between metals and non metals covalent is between non metals and metallic is between metals the test is on the ninth and it's forty minutes long and calculators are allowed but not phones um and the practice questions are on page sixty three
```
**Target (what the model will learn):**
```
Chem revision.
Three types of bonds: ionic, covalent and metallic.
Ionic: between metals and non-metals.
Covalent: between non-metals.
Metallic: between metals.
Test on the 9th, 40 minutes long.
Calculators allowed, but not phones.
Practice questions: page 63.
```
**Facts that must survive:** facts: three bond types with definitions; test on the 9th, 40 minutes; calculators allowed, phones NOT; practice questions page 63; Format note -> terse lines, no '- ' bullets

Verdict: ______  Error type: ______  Comment: ______

---

## 75. TC-W11-113 · notes_format · agent-written
**Settings:** format=note, task=rewrite
**Transcript:**
```
note for the onboarding of taro he starts on the third um badge from reception laptop is ready but the vpn access isn't approved yet so chase alma about that
```
**Target (what the model will learn):**
```
Onboarding for Taro: starts on the 3rd.
Badge from reception.
Laptop is ready.
VPN access not approved yet: chase Alma about that.
```
**Facts that must survive:** facts: Taro starts the 3rd; badge from reception; laptop ready; VPN NOT approved yet -> chase Alma

Verdict: ______  Error type: ______  Comment: ______

---

## 76. TC-W12-133 · notes_format · agent-written
**Settings:** format=note, locale=en-in, task=rewrite
**Transcript:**
```
inventory notes room three so in total we counted forty two items two are missing their labels one brass lamp has a crack on the base do not move it until ilse photographs it
```
**Target (what the model will learn):**
```
Inventory notes, Room 3
Counted 42 items in total.
Two are missing their labels.
One brass lamp has a crack on the base; do not move it until Ilse photographs it.
```
**Facts that must survive:** facts: Room 3; 42 items counted; two missing labels; one brass lamp cracked at base; do NOT move it UNTIL Ilse photographs it; terse lines

Verdict: ______  Error type: ______  Comment: ______

---

## 77. TC-W11-208 · notes_format · agent-written
**Settings:** format=prose, header_style=full, register=formal, task=rewrite
**Transcript:**
```
for the new starters guide the main points are they must complete the security training before getting system access they should book a desk through the app and not just sit anywhere expense claims go through devika's team and have to be submitted within thirty days and the parking permit request goes to hugo at least a week in advance and um lunch on the first day is provided by the team
```
**Target (what the model will learn):**
```
For the new starters' guide, the main points are as follows. New starters must complete the security training before getting system access. They should book a desk through the app and not simply sit anywhere. Expense claims go through Devika's team and must be submitted within 30 days. Parking permit requests go to Hugo at least a week in advance. Lunch on the first day is provided by the team.
```
**Facts that must survive:** facts: security training BEFORE system access; desk via app, NOT anywhere; expenses via Devika's team within 30 days; parking permit to Hugo at least a week ahead; first-day lunch provided by the team; explicit prose beats the 'main points' list cue

Verdict: ______  Error type: ______  Comment: ______

---

## 78. TC-W12-163 · notes_format · agent-written
**Settings:** task=cleanup
**Instruction:** keep this as one paragraph and don't change anything I said, just clean it
**Transcript:**
```
today was quiet at the museum only about fifteen visitors all day but one old man stayed for an hour in the map room and told me his father drew one of the maps on the wall i didn't get his name and i wish i had
```
**Target (what the model will learn):**
```
Today was quiet at the museum, only about 15 visitors all day, but one old man stayed for an hour in the map room and told me his father drew one of the maps on the wall. I didn't get his name, and I wish I had.
```
**Facts that must survive:** facts: only about 15 visitors; old man stayed an hour in map room; his father drew one of the maps; didn't get his name (negation); speaker's own regret kept, nothing added; cleanup, one paragraph

Verdict: ______  Error type: ______  Comment: ______

---

## 79. TC-W11-118 · notes_format · agent-written
**Settings:** format=auto, task=rewrite
**Instruction:** number the steps
**Transcript:**
```
for new starters on day one they get their badge from omkar then they sit with lise for the systems walkthrough and in the afternoon they shadow the support queue
```
**Target (what the model will learn):**
```
For new starters on day one:
1. They get their badge from Omkar.
2. They sit with Lise for the systems walkthrough.
3. In the afternoon, they shadow the support queue.
```
**Facts that must survive:** facts: badge from Omkar, walkthrough with Lise, support queue in the afternoon; numbered because instructed; lead line kept

Verdict: ______  Error type: ______  Comment: ______

---

## 80. TC-W13-213 · summary · agent-written
**Settings:** header_style=full, task=summarize
**Transcript:**
```
write up of friday night's screening failure at the old market hall the projector shut down forty minutes into the feature at about nine ten because it overheated the air conditioning in the booth had been switched off by the venue staff we restarted at nine thirty five after it cooled down and finished at eleven fifteen around a hundred and sixty people were in the room and about twenty left we offered everyone a free ticket to another screening which we'll honour this weekend only elise is getting the venue to put a sign on the ac switch and viktor wants a backup projector on standby for the rest of the festival which costs about three hundred a day we haven't approved that yet
```
**Target (what the model will learn):**
```
Friday night's screening failure at the Old Market Hall: the projector shut down 40 minutes into the feature, at about 9:10, because it overheated; venue staff had switched off the booth's air conditioning. We restarted at 9:35, once it cooled down, and finished at 11:15. Around 160 people were in the room, and about 20 left. We offered everyone a free ticket to another screening, honoured this weekend only. Elise is getting the venue to put a sign on the AC switch. Viktor wants a backup projector on standby for the rest of the festival, at about 300 a day; we haven't approved that yet.
```
**Facts that must survive:** facts: frame = Friday night's screening failure, Old Market Hall; projector off 40 min in (~9:10), overheated, venue staff switched off booth AC; restart 9:35, finished 11:15; ~160 in room, ~20 left; free ticket offered, honoured this weekend only; Elise gets sign on AC switch; Viktor wants backup projector ~300/day, NOT approved yet (no currency spoken)

Verdict: ______  Error type: ______  Comment: ______

---

## 81. TC-W13-015 · summary · agent-written
**Settings:** format=note, task=summarize
**Instruction:** short note style, keep every date and owner
**Transcript:**
```
notes from the tech run meeting viktor's doing projection he tested all the dcp files except two which hadn't arrived and those are due by friday the sound check for the main screen is on the thirteenth at ten a m bashir's bringing the backup projector from his place because the hall's spare one is broken hana is printing the screening schedule two hundred copies and she'll have them by the twelfth we decided no live streaming this year it's too expensive
```
**Target (what the model will learn):**
```
Tech run:
Viktor on projection; all DCP files tested except two that had not arrived, due by Friday.
Main screen sound check: the 13th, 10 a.m.
Bashir bringing the backup projector from his place; the hall's spare is broken.
Hana printing the screening schedule, 200 copies, ready by the 12th.
Decided: no live streaming this year, too expensive.
```
**Facts that must survive:** facts: Viktor projection, two DCPs not arrived, due Friday; sound check 13th 10 a.m.; Bashir brings backup projector (hall spare broken); Hana 200 schedules by 12th; decided NO live streaming (too expensive)

Verdict: ______  Error type: ______  Comment: ______

---

## 82. TC-W13-157 · summary · agent-written
**Settings:** header_style=full, task=summarize
**Transcript:**
```
we put off the decision on the closing night party at tonight's committee meeting elise wants a boat party viktor thinks it's too risky in march weather we'll get two quotes and decide on the twentieth and either way it's capped at six thousand
```
**Target (what the model will learn):**
```
At tonight's committee meeting, we put off deciding on the closing night party: Elise wants a boat party, but Viktor thinks it's too risky in March weather. We'll get two quotes and decide on the 20th; either way, it's capped at 6,000.
```
**Facts that must survive:** facts: frame = tonight's committee meeting; closing party decision deferred; Elise wants boat, Viktor thinks too risky in March; two quotes, decide 20th; capped at 6,000 either way (no currency spoken)

Verdict: ______  Error type: ______  Comment: ______

---

## 83. TC-W13-017 · summary · agent-written
**Settings:** format=bullets, header_style=full, task=summarize
**Transcript:**
```
okay sprint fourteen review smita ran it um we shipped the new onboarding flow and the dark mode toggle the push notification work did not ship because apple rejected the build on wednesday so that rolls into sprint fifteen velocity was thirty one points against a target of thirty six crash rate dropped from one point two percent to point eight percent which is great hana is fixing the rejection issue and resubmitting by tuesday and we agreed to freeze new features for the first three days of next sprint to clear bugs open question is whether we still demo to the client on the twenty seventh if notifications aren't in
```
**Target (what the model will learn):**
```
- Sprint 14 review, run by Smita.
- Shipped: the new onboarding flow and the dark mode toggle.
- Push notifications did not ship because Apple rejected the build on Wednesday; the work rolls into Sprint 15.
- Velocity: 31 points against a target of 36.
- Crash rate dropped from 1.2% to 0.8%.
- Hana is fixing the rejection issue and resubmitting by Tuesday.
- Agreed: freeze new features for the first three days of next sprint to clear bugs.
- Open: do we still demo to the client on the 27th if notifications aren't in?
```
**Facts that must survive:** waiver number_invented: checker misreads 'point eight percent' (0.8) and flags the leading 0. facts: Sprint 14 (Smita); shipped onboarding + dark mode; push notifications NOT shipped (Apple rejected Wed) -> Sprint 15; velocity 31 vs 36; crash 1.2% -> 0.8%; Hana resubmits by Tuesday; feature freeze first three days; open: demo on 27th if notifications aren't in

Verdict: ______  Error type: ______  Comment: ______

---

## 84. TC-W13-207 · summary · agent-written
**Settings:** task=summarize
**Transcript:**
```
summary of today's online lecture on kitchen costing by chef mahima food cost should stay under thirty percent of menu price portion control matters more than supplier prices she said and the assignment is costing three dishes by next friday
```
**Target (what the model will learn):**
```
Today's online lecture on kitchen costing by Chef Mahima: food cost should stay under 30% of menu price, and she said portion control matters more than supplier prices. Assignment: cost three dishes by next Friday.
```
**Facts that must survive:** facts: frame = today's online lecture on kitchen costing by Chef Mahima; food cost under 30% of menu price; portion control > supplier prices (her view, 'she said'); assignment: cost three dishes by next Friday

Verdict: ______  Error type: ______  Comment: ______

---

## 85. TC-W13-189 · summary · agent-written
**Settings:** format=note, task=summarize
**Transcript:**
```
notes from the under fourteens hockey coaches meeting today with faisal training moves indoors from november tuesdays six to seven thirty the tournament on the sixteenth is confirmed we need two more drivers and faisal is sorting the first aid kit
```
**Target (what the model will learn):**
```
Today's under-14s hockey coaches meeting with Faisal:
Training moves indoors from November, Tuesdays 6 to 7:30.
Tournament on the 16th confirmed.
Need two more drivers.
Faisal is sorting the first aid kit.
```
**Facts that must survive:** waiver number_invented: checker does not read 'under fourteens' as 14, so it flags the 14 in 'under-14s'. facts: frame = today's under-14s hockey coaches meeting with Faisal; indoor training from Nov, Tue 6-7:30; tournament 16th confirmed; need two more drivers; Faisal sorts first aid kit

Verdict: ______  Error type: ______  Comment: ______

---

## 86. TC-W13-018 · summary · agent-written
**Settings:** locale=en-in, task=summarize
**Transcript:**
```
so sprint planning for the payments app um we're committing to twenty eight points this sprint the big items are the refund screen which bashir owns no wait gopal owns it bashir's on leave and the upi autopay integration which ottilie is taking the sprint ends on the thirtieth of october and we're not taking on the analytics dashboard this time it's pushed to next sprint also the design for the refund screen isn't final yet elise said she'll have it by monday if the legal copy comes through and nobody knows yet if we need a security review for autopay
```
**Target (what the model will learn):**
```
For the payments app sprint, we're committing to 28 points. The big items are the refund screen, owned by Gopal because Bashir is on leave, and the UPI autopay integration, which Ottilie is taking. The sprint ends on October 30. We're not taking on the analytics dashboard this time; it's pushed to next sprint. The refund screen design isn't final yet: Elise said she'll have it by Monday if the legal copy comes through. Nobody knows yet whether we need a security review for autopay.
```
**Facts that must survive:** facts: 28 points; refund screen owner Gopal (Bashir corrected away as owner; Bashir on leave); UPI autopay Ottilie; ends Oct 30; NOT taking analytics dashboard, next sprint; design not final, Elise by Monday IF legal copy comes through; open: security review for autopay

Verdict: ______  Error type: ______  Comment: ______

---

## 87. PT-150 · summary · agent-written
**Settings:** header_style=full, task=summarize
**Transcript:**
```
so the accountant went through everything and the main points are we owe about two thousand in tax for last year which is due by the thirty first of january we can claim the new laptop and half the phone bill but not the gym membership and she wants the missing receipts from july and august before she files
```
**Target (what the model will learn):**
```
We owe about 2,000 in tax for last year, due by January 31st. We can claim the new laptop and half the phone bill, but not the gym membership. The accountant needs the missing July and August receipts before filing.
```
**Facts that must survive:** —

Verdict: ______  Error type: ______  Comment: ______

---

## 88. TC-W14-136 · followup_style · agent-written
**Settings:** locale=en-in, task=edit
**Instruction:** just fix the punctuation and capitals, don't change any words
**Previous draft:**
```
kal subah 8 baje gas cylinder wala aayega toh ₹1,100 cash ready rakhna aur please gate pe Rohit ko bol dena ki usse andar aane de
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Kal subah 8 baje gas cylinder wala aayega, toh ₹1,100 cash ready rakhna, aur please gate pe Rohit ko bol dena ki usse andar aane de.
```
**Facts that must survive:** facts: gas cylinder delivery tomorrow 8 a.m.; keep ₹1,100 cash ready; tell Rohit at the gate to let him in; only punctuation and the first capital changed, Hindi-English words untouched

Verdict: ______  Error type: ______  Comment: ______

---

## 89. TC-W14-030 · followup_style · agent-written
**Settings:** format=post, locale=en-in, task=rewrite, tone=excited
**Instruction:** no hashtags or emoji, and keep the ticket price exactly
**Transcript:**
```
we're running the lantern night market again this year on december sixth at the old mill grounds um entry is two hundred rupees and kids under ten get in free
```
**Target (what the model will learn):**
```
The lantern night market is back this year! Join us on December 6 at the old mill grounds. Entry is ₹200, and kids under 10 get in free.
```
**Facts that must survive:** facts: December 6 at old mill grounds; entry ₹200 (rupees spoken); kids under 10 free; 'again this year' kept as 'back this year'

Verdict: ______  Error type: ______  Comment: ______

---

## 90. TC-W14-112 · followup_style · agent-written
**Settings:** task=edit
**Instruction:** keep everything but replace 'users' with 'customers'
**Previous draft:**
```
Most users finish onboarding in under ten minutes, but users on the legacy plan still can't import CSV files. We'll ask those users to switch before January.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Most customers finish onboarding in under ten minutes, but customers on the legacy plan still can't import CSV files. We'll ask those customers to switch before January.
```
**Facts that must survive:** facts: under ten minutes onboarding; legacy plan still can't import CSV (negation, 'still'); switch before January; only users -> customers (three times)

Verdict: ______  Error type: ______  Comment: ______

---

## 91. TC-W14-023 · followup_style · agent-written
**Settings:** task=edit
**Instruction:** turn it into a short email to anjali and sign it from martin
**Previous draft:**
```
The Q4 pipeline review is moved to Thursday at 2. Please bring the updated forecast and the list of stalled deals.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Hi Anjali,

The Q4 pipeline review is moved to Thursday at 2. Please bring the updated forecast and the list of stalled deals.

Best,
Martin
```
**Facts that must survive:** facts: Q4 review moved to Thursday at 2; bring updated forecast and stalled-deals list; recipient Anjali and sender Martin come from the instruction

Verdict: ______  Error type: ______  Comment: ______

---

## 92. TC-W14-120 · followup_style · agent-written
**Settings:** task=edit
**Instruction:** take out the parking bit
**Previous draft:**
```
Hi Selin, Yash accepted the offer for the operations lead role and starts on the 4th. He asked about parking, which I said I'd check with facilities. He doesn't want his current employer contacted for a reference until after he has resigned.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Hi Selin, Yash accepted the offer for the operations lead role and starts on the 4th. He doesn't want his current employer contacted for a reference until after he has resigned.
```
**Facts that must survive:** facts: parking sentence (and the 'I'd check with facilities' it contained) removed as instructed; offer accepted, starts the 4th; negation + condition 'doesn't want employer contacted until after he has resigned' kept

Verdict: ______  Error type: ______  Comment: ______

---

## 93. TC-W14-176 · followup_style · agent-written
**Settings:** task=edit
**Instruction:** make it formal and add a subject line saying service contract renewal
**Previous draft:**
```
Hey Margaux, our cleaning contract with you ends on Jan 31. We'd like to renew for another year but at the same rate, not the 8% increase you mentioned.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Subject: Service contract renewal

Dear Margaux,

Our cleaning contract with you ends on January 31. We would like to renew for another year, but at the same rate, not with the 8% increase you mentioned.
```
**Facts that must survive:** facts: contract ends January 31; renew one more year at the same rate, NOT with the 8% increase; dictated 'Hey' adapted to formal 'Dear'; Subject line from the instruction; no sign-off (no sender given). Waiver invented_subject: the Subject line is requested in the instruction (known checker gap)

Verdict: ______  Error type: ______  Comment: ______

---

## 94. TC-W14-172 · followup_style · agent-written
**Settings:** task=edit
**Instruction:** make it shorter
**Previous draft:**
```
Hi everyone, so just to keep you all in the loop, the irrigation system at the Fernhill office park is going to be shut off from Monday to Wednesday next week while we replace the main valve, which means the lawns won't get watered for those three days, so if it's really hot, Martin will come by with the hose cart on Tuesday afternoon to give the flower beds a soak.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Hi everyone, the irrigation system at the Fernhill office park will be shut off from Monday to Wednesday next week while we replace the main valve, so the lawns won't get watered for those three days. If it's really hot, Martin will come by with the hose cart on Tuesday afternoon to soak the flower beds.
```
**Facts that must survive:** facts: irrigation off Monday-Wednesday next week for the main valve; lawns NOT watered those three days; Martin's Tuesday-afternoon hose-cart visit stays conditional on it being really hot

Verdict: ______  Error type: ______  Comment: ______

---

## 95. TC-W14-118 · followup_style · agent-written
**Settings:** header_style=full, task=edit
**Instruction:** shorter please
**Previous draft:**
```
Just a heads-up that because of all the rain we've had this week, the ground is still really soft, so we probably won't be able to bring the mini digger in until next Tuesday at the earliest.
```
**Transcript:**
```

```
**Target (what the model will learn):**
```
Heads-up: after this week's rain, the ground is still very soft, so we probably won't get the mini digger in until next Tuesday at the earliest.
```
**Facts that must survive:** facts: ground still soft because of this week's rain; hedge 'probably' and negation 'won't' kept; mini digger not before next Tuesday 'at the earliest'

Verdict: ______  Error type: ______  Comment: ______

---

## 96. TC-W15-003 · unsupported · agent-written
**Settings:** context=work, format=email, task=rewrite
**Instruction:** make it an email to bhavna and send it to her
**Transcript:**
```
so the printer on the second floor is jammed again and the it guy said he can only come on thursday morning so until then please use the one near reception and uh don't try to open the back panel yourself and uh the new toner we ordered last week also hasn't arrived yet so please check with erik before you order more
```
**Target (what the model will learn):**
```
Hi Bhavna,

The printer on the second floor is jammed again, and the IT guy said he can only come on Thursday morning. Until then, please use the one near reception, and don't try to open the back panel yourself.

The new toner we ordered last week also hasn't arrived yet, so please check with Erik before you order more.
```
**Facts that must survive:** facts: printer second floor jammed AGAIN; IT guy can ONLY come Thursday morning; use one near reception until then; don't open back panel; toner ordered last week hasn't arrived, check with Erik before ordering more; no send claim, no sign-off (no sender)

Verdict: ______  Error type: ______  Comment: ______

---

## 97. TC-W15-013 · unsupported · agent-written
**Settings:** context=email, format=email, task=rewrite
**Instruction:** fix the grammar and email it to hamza
**Transcript:**
```
so i cant make it to the group project meeting tomorrow i have a lab that runs late but i finished the literature review section and uploaded it to the shared folder can someone else present the slides on friday also i'll be online after eight tonight if anyone wants to go over the conclusion and uh tushar said he can check the references on thursday
```
**Target (what the model will learn):**
```
Hi Hamza,

I can't make it to the group project meeting tomorrow; I have a lab that runs late. But I finished the literature review section and uploaded it to the shared folder. Can someone else present the slides on Friday?

Also, I'll be online after 8 tonight if anyone wants to go over the conclusion. Tushar said he can check the references on Thursday.
```
**Facts that must survive:** facts: can't make meeting tomorrow (lab runs late); lit review finished and uploaded; asks if someone else can present slides Friday; online after 8 tonight IF anyone wants to go over conclusion; Tushar said he CAN check references Thursday; no send claim, no sign-off

Verdict: ______  Error type: ______  Comment: ______

---

## 98. TC-W15-020 · unsupported · agent-written
**Settings:** context=chat, format=message, header_style=full, register=casual, task=rewrite
**Instruction:** send this to the trip group on whatsapp
**Transcript:**
```
guys check in is at two door code is four four seven one don't share it
```
**Target (what the model will learn):**
```
Guys, check-in is at 2. Door code is 4471. Don't share it.
```
**Facts that must survive:** facts: check-in at 2 (no a.m./p.m. spoken); door code 4471 verbatim; don't share it; no send claim

Verdict: ______  Error type: ______  Comment: ______

---

## 99. TC-W15-109 · unsupported · agent-written
**Settings:** task=cleanup
**Instruction:** convert this to a pdf
**Transcript:**
```
the workshop on budgeting for freelancers is on saturday the fourth from eleven to one in hall b entry is free but seats are limited to thirty so register by wednesday
```
**Target (what the model will learn):**
```
The workshop on budgeting for freelancers is on Saturday the 4th from 11 to 1 in Hall B. Entry is free, but seats are limited to 30, so register by Wednesday.
```
**Facts that must survive:** facts: workshop Saturday the 4th, 11 to 1, Hall B; entry free; seats limited to 30; register by Wednesday; no conversion claim

Verdict: ______  Error type: ______  Comment: ______

---

## 100. TC-W15-111 · unsupported · agent-written
**Settings:** locale=en-in, task=summarize
**Instruction:** summarize the attached file
**Transcript:**
```
so quick recap of the call with the packaging supplier this morning uh they can drop the price per box from eighteen to fifteen rupees if we order at least five thousand boxes a month lars wants to wait until we see december sales before committing and the samples of the new kraft boxes should reach us by friday
```
**Target (what the model will learn):**
```
Call with the packaging supplier this morning: they can drop the price per box from ₹18 to ₹15 if we order at least 5,000 boxes a month. Lars wants to wait until we see December sales before committing. Samples of the new kraft boxes should reach us by Friday.
```
**Facts that must survive:** no file exists; the transcript is summarized (task summarize). facts: call with packaging supplier this morning; price per box ₹18 -> ₹15 IF at least 5,000 boxes a month ('eighteen to fifteen rupees' -> ₹ on both, same phrase); Lars wants to wait for December sales before committing (open decision); samples SHOULD reach by Friday (hedge kept)

Verdict: ______  Error type: ______  Comment: ______

---

## 101. NR-0304 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
accha so tell him to come by three only
```
**Target (what the model will learn):**
```
Accha, so tell him to come by 3 only.
```
**S1 original output (before correction):**
```
Alright, so tell him to come by 3.
```
**Facts that must survive:** facts: only; 3

Verdict: ______  Error type: ______  Comment: ______

---

## 102. NR-0019 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: semi-formal] [Structure: lists] [Context: general]
**Transcript:**
```
ideas for the newsletter this month, um, maybe a short interview with the new team lead, a roundup of the customer wins, probably a section on the upcoming holidays, and possibly a recipe or something light, if we have space we could also add the volunteer photos from the beach clean up
```
**Target (what the model will learn):**
```
Ideas for the newsletter this month:
- Maybe a short interview with the new team lead
- A roundup of the customer wins
- Probably a section on the upcoming holidays
- Possibly a recipe or something light
- If we have space, we could also add the volunteer photos from the beach clean-up
```
**S1 original output (before correction):**
```
Ideas for the newsletter this month:
- A short interview with the new team lead
- A roundup of the customer wins
- A section on the upcoming holidays
- A recipe or something light
- If we have space, we could also add the volunteer photos from the beach clean-up
```
**Facts that must survive:** hedges per item + condition kept | facts: newsletter; this month; maybe; interview; new team lead; roundup; customer wins; probably; upcoming holidays; possibly; recipe; if; could; volunteer photos; beach clean-up/beach clean up/beach cleanup

Verdict: ______  Error type: ______  Comment: ______

---

## 103. NR-0122 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: email]
**Transcript:**
```
hi chloe the room rate is one hundred thirty nine a night and breakfast costs fifteen extra thanks ethan
```
**Target (what the model will learn):**
```
Hi Chloe,

The room rate is 139 a night and breakfast costs 15 extra.

Thanks,
Ethan
```
**S1 original output (before correction):**
```
Hi Chloe,

The room rate is $139 a night and breakfast costs $15 extra.

Thanks,
Ethan
```
**Facts that must survive:** facts: Chloe; room rate; breakfast; Ethan; 139; 15

Verdict: ______  Error type: ______  Comment: ______

---

## 104. NR-0396 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: formal] [Structure: lists] [Context: general]
**Transcript:**
```
packing list maybe a raincoat definitely sunscreen hats and probably a power bank
```
**Target (what the model will learn):**
```
Packing list:
- Maybe a raincoat
- Definitely sunscreen
- Hats
- Probably a power bank
```
**S1 original output (before correction):**
```
Packing list, maybe a raincoat, definitely sunscreen, hats, and probably a power bank.
```
**Facts that must survive:** hedges per item kept | facts: raincoat; sunscreen; hats; power bank; maybe; probably

Verdict: ______  Error type: ______  Comment: ______

---

## 105. NR-0377 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
the meetup is on the third or the fourth i forget
```
**Target (what the model will learn):**
```
The meetup is on the 3rd or the 4th, I forget.
```
**S1 original output (before correction):**
```
The meetup is on the 4th.
```
**Facts that must survive:** alternative: both dates kept | facts: meetup; forget; 3rd/third; 4th/fourth

Verdict: ______  Error type: ______  Comment: ______

---

## 106. NR-0402 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: formal] [Structure: prose] [Context: general]
**Transcript:**
```
we paid eight hundred fifty for the repairs
```
**Target (what the model will learn):**
```
We paid 850 for the repairs.
```
**S1 original output (before correction):**
```
We paid $850 for the repairs.
```
**Facts that must survive:** facts: repairs; 850

Verdict: ______  Error type: ______  Comment: ______

---

## 107. NR-0067 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: formal] [Structure: lists] [Context: general]
**Transcript:**
```
workout today was three sets of squats ten push ups twenty lunges and a two kilometre run
```
**Target (what the model will learn):**
```
Workout today was:
- Three sets of squats
- 10 push-ups
- 20 lunges
- A 2-kilometer run
```
**S1 original output (before correction):**
```
Workout today was:
- Three sets of squats, 10 push-ups, 20 lunges, and a 2-kilometer run.
```
**Facts that must survive:** facts: squats; push; lunges; run; 20; 3/three; 10/ten; 2/two

Verdict: ______  Error type: ______  Comment: ______

---

## 108. NR-0414 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: formal] [Structure: prose] [Context: general]
**Transcript:**
```
i need to transfer twelve thousand five hundred to the landlord and three thousand to the maid by the first
```
**Target (what the model will learn):**
```
I need to transfer 12,500 to the landlord and 3,000 to the maid by the first.
```
**S1 original output (before correction):**
```
I need to transfer $12,500 to the landlord and $3,000 to the maid by the first.
```
**Facts that must survive:** facts: landlord; maid; 12,500/12500; 3,000/3000; 1st/first

Verdict: ______  Error type: ______  Comment: ______

---

## 109. NR-0045 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: semi-formal] [Structure: lists] [Context: general]
**Transcript:**
```
items colon passport comma visa copy comma hotel booking comma and travel insurance
```
**Target (what the model will learn):**
```
Items: passport, visa copy, hotel booking, and travel insurance.
```
**S1 original output (before correction):**
```
Items: passport, visa copy, hotel booking, travel insurance.
```
**Facts that must survive:** facts: passport; visa copy; hotel booking; travel insurance

Verdict: ______  Error type: ______  Comment: ______

---

## 110. NR-0085 · s1_native_rehearsal · s1_corrected
**Settings:** [Styling: formal] [Structure: lists] [Context: general]
**Transcript:**
```
okay so the list of things to carry for the hostel, uh, the bedsheet and pillow cover, a bucket and mug, the extension board, maggi and some snacks from home, the mosquito repellent, and the documents for admission, the originals plus two sets of photocopies, and papa said keep some cash also for the first week
```
**Target (what the model will learn):**
```
Okay, so the list of things to carry for the hostel:
- Bedsheet and pillow cover
- Bucket and mug
- Extension board
- Maggi and some snacks from home
- Mosquito repellent
- Documents for admission, the originals plus two sets of photocopies

Papa said keep some cash also for the first week.
```
**S1 original output (before correction):**
```
Okay, so the list of things to carry for the hostel:
- Bedsheet and pillow cover
- Bucket and mug
- Extension board
- Maggi and some snacks from home
- Mosquito repellent
- Documents for admission, the originals plus two sets of photocopies
- Cash

Also, Papa said keep some cash also for the first week.
```
**Facts that must survive:** facts: hostel; bedsheet; pillow cover; bucket and mug; extension board; Maggi; snacks; mosquito repellent; documents; admission; originals; photocopies; papa; cash; first week; 2/two

Verdict: ______  Error type: ______  Comment: ______

---

## 111. NR-0009 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
um quick question for the group do we need to bring our own rackets on saturday or will the club have some spare ones
```
**Target (what the model will learn):**
```
Quick question for the group: do we need to bring our own rackets on Saturday, or will the club have some spare ones?
```
**Facts that must survive:** question stays a question; both options in question kept | facts: rackets; Saturday; club; spare

Verdict: ______  Error type: ______  Comment: ______

---

## 112. NR-0101 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
we can paint the room sage or that pale blue, both match the curtains
```
**Target (what the model will learn):**
```
We can paint the room sage or that pale blue, both match the curtains.
```
**Facts that must survive:** alternative kept | facts: sage; pale blue; both; curtains

Verdict: ______  Error type: ______  Comment: ______

---

## 113. NR-0139 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: formal] [Structure: prose] [Context: general]
**Transcript:**
```
the lift is not working on floor nine
```
**Target (what the model will learn):**
```
The lift is not working on floor 9.
```
**Facts that must survive:** facts: lift; floor; 9; 9/nine | negations kept (>= 1)

Verdict: ______  Error type: ______  Comment: ______

---

## 114. NR-0285 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: lists] [Context: general]
**Transcript:**
```
bullet one fix the login bullet two update docs bullet three deploy
```
**Target (what the model will learn):**
```
- Fix the login.
- Update docs.
- Deploy.
```
**Facts that must survive:** spoken bullet cues | facts: login; docs; deploy

Verdict: ______  Error type: ______  Comment: ______

---

## 115. NR-0128 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: formal] [Structure: prose] [Context: general]
**Transcript:**
```
arre the water bill was nine hundred forty rupees this month, last month it was half only
```
**Target (what the model will learn):**
```
The water bill was 940 rupees this month. Last month it was half only.
```
**Facts that must survive:** facts: water bill; this month; last month; half only; 940

Verdict: ______  Error type: ______  Comment: ______

---

## 116. NR-0352 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
so the plan for mama's anniversary dinner, we booked the banquet at the club for saturday, no wait it's sunday the sixteenth, from seven thirty onwards, for about forty people, mummy wants only veg food and no alcohol because some elders are coming, and please don't tell mama anything, it's a surprise yaar, i'll collect the cake on the way
```
**Target (what the model will learn):**
```
So the plan for Mama's anniversary dinner, we booked the banquet at the club for Sunday the 16th, from 7:30 onwards, for about 40 people. Mummy wants only veg food and no alcohol because some elders are coming, and please don't tell Mama anything, it's a surprise yaar. I'll collect the cake on the way.
```
**Facts that must survive:** correction: Sunday the 16th, not Saturday | facts: mama; anniversary dinner; banquet; club; Sunday; onwards; about; mummy; only veg; alcohol; elders; surprise; yaar; cake; 7:30; 16th/sixteenth; 40 | negations kept (>= 2)

Verdict: ______  Error type: ______  Comment: ______

---

## 117. NR-0005 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
the flat is either on the fourth floor or the sixth i honestly don't remember which
```
**Target (what the model will learn):**
```
The flat is either on the 4th floor or the 6th. I honestly don't remember which.
```
**Facts that must survive:** alternative: 4th and 6th both kept | facts: flat; floor; don't remember; 4th/fourth; 6th/sixth | negations kept (>= 1)

Verdict: ______  Error type: ______  Comment: ______

---

## 118. NR-0437 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
the dog hasn't eaten since morning
```
**Target (what the model will learn):**
```
The dog hasn't eaten since morning.
```
**Facts that must survive:** facts: dog; since morning | negations kept (>= 1)

Verdict: ______  Error type: ______  Comment: ______

---

## 119. NR-0386 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: lists] [Context: general]
**Transcript:**
```
garden chores this weekend mow the lawn trim the hedges plant the tulip bulbs and clean the bird bath
```
**Target (what the model will learn):**
```
Garden chores this weekend:
- Mow the lawn
- Trim the hedges
- Plant the tulip bulbs
- Clean the bird bath
```
**Facts that must survive:** facts: mow the lawn; hedges; tulip bulbs; bird bath

Verdict: ______  Error type: ______  Comment: ______

---

## 120. NR-0415 · s1_native_rehearsal · s1_verbatim
**Settings:** [Styling: semi-formal] [Structure: prose] [Context: general]
**Transcript:**
```
we shouldn't reply until legal checks it
```
**Target (what the model will learn):**
```
We shouldn't reply until legal checks it.
```
**Facts that must survive:** facts: legal; until | negations kept (>= 1)

Verdict: ______  Error type: ______  Comment: ______

---
