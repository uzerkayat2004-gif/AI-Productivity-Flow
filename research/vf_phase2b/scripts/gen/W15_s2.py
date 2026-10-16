"""W15 stage 2: unsupported bucket (unsupported_boundary slice), 28 records, TC-W15-101..128.

Imported by W15.py (run W15.py to regenerate both files); can also be run on its own.
Stage-1 review fix applied: a message gets a vocative "Name, ..." opener only when the speaker said the
name in the dictation; never from [Recipient] or from a name that appears only in the instruction.
New unsupported asks: reply to this email for me, post on LinkedIn, set a reminder, convert to PDF,
summarize the attached file (no file exists), calculate the total, make it rhyme / write a poem,
translate to Hindi on English speech, answer in one line, and mixed supported + unsupported instructions.
Names: Tushar, Bhavna, Erik, Amina, Rosa, Hamza, Kirti, Lars.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W15"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl")
rows = []


def R(request, target, assertions, note=None, pos="after", cx=1, length="medium", behavior="cleanup_only", waivers=None):
    n = 100 + len(rows) + 1
    a = dict(assertions)
    a.setdefault("behavior", behavior)
    rows.append(rec(f"TC-{WID}-{n:03d}", "unsupported", "unsupported_boundary", request, target, a,
                    f"w15-sc-{n:03d}", author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


# 101 reply to this email for me, nobody named -> "Hi," and only the reply text
R({"task": "rewrite", "format": "email", "instruction": "reply to this email for me",
   "transcript": "yes thursday works for the site visit uh but we can only stay till four so maybe start at two"},
  "Hi,\n\nYes, Thursday works for the site visit, but we can only stay till 4, so maybe start at 2.",
  {"format": "email", "numbers": ["4", "2"], "must_include": ["Thursday", "site visit", "only stay till 4", "maybe"],
   "must_not_include": ["Replied", "Thanks for your email", "Best,"] },
  note="facts: Thursday works for the site visit; can ONLY stay till 4; 'maybe' start at 2 (hedge kept, no a.m./p.m. spoken); nobody named so 'Hi,'; no sign-off, no reply/send claim",
  length="short")

# 102 reply email, speaker names Kirti in the dictation -> greeting from the dictated name
R({"task": "rewrite", "format": "email", "context": "work", "header_style": "full",
   "instruction": "reply to this email for me",
   "transcript": "hi kirti thanks for sending the invoice um we'll clear it by the twentieth but the second line item the one for the banner printing looks like it's been charged twice can you check and send a corrected copy"},
  "Hi Kirti,\n\nThanks for sending the invoice. We'll clear it by the 20th, but the second line item, the one for the banner printing, looks like it's been charged twice. Can you check and send a corrected copy?",
  {"format": "email", "numbers": ["20"], "must_include": ["Hi Kirti", "invoice", "20th", "banner printing", "charged twice", "corrected copy"],
   "must_not_include": ["Replied", "Best,", "Regards,", "apologi"]},
  note="facts: dictated thanks for the invoice; commitment 'we'll clear it by the 20th' kept (spoken); second line item (banner printing) looks charged twice; asks Kirti to check and send corrected copy; 'hi kirti' dictated so 'Hi Kirti,'; no sign-off (no sender), no reply claim",
  pos="before")

# 103 formal reply email with Recipient/Sender, en-gb, pounds
R({"task": "rewrite", "format": "email", "register": "formal", "context": "email", "locale": "en-gb",
   "recipient": "Lars", "sender": "Amina", "header_style": "full",
   "instruction": "reply to this for me and make it formal",
   "transcript": "um so hi lars thank you for the proposal for the office move we've looked at it and we'd like to go ahead with the weekend option rather than the weekday one because we can't close the office during the week uh the quote you gave was three thousand two hundred pounds and we're fine with that as long as it includes packing the server room one thing though we need the crates delivered by the ninth at the latest so people can start packing their desks and please confirm whether the insurance covers the monitors if it doesn't we'll move those ourselves"},
  "Dear Lars,\n\nThank you for the proposal for the office move. We have looked at it, and we would like to go ahead with the weekend option rather than the weekday one, because we cannot close the office during the week.\n\nThe quote you gave was £3,200, and we are fine with that as long as it includes packing the server room. One thing, though: we need the crates delivered by the 9th at the latest so that people can start packing their desks.\n\nPlease confirm whether the insurance covers the monitors. If it does not, we will move those ourselves.\n\nRegards,\nAmina",
  {"format": "email", "numbers": ["3,200", "9"], "must_include": ["Dear Lars", "weekend option", "£3,200", "as long as", "server room", "at the latest", "insurance", "monitors", "Amina"],
   "must_not_include": ["Replied", "Hi Lars", "apologi"], "min_negations": 2},
  note="facts: go ahead with weekend option, not weekday, because they can't close the office during the week; quote £3,200 fine AS LONG AS it includes packing the server room; crates by the 9th at the latest; asks to confirm insurance covers monitors, IF NOT they'll move them themselves; formal: 'Dear Lars,' + 'Regards, Amina'; no reply claim. Waiver: checker reads the bare 'one' in 'one thing though' as number 1",
  cx=2, length="long", waivers=["number_missing"])

# 104 post this on LinkedIn -> post text only, no hashtags, no claim
R({"task": "rewrite", "format": "post", "context": "work", "locale": "en-in",
   "instruction": "post this on linkedin",
   "transcript": "so last month i finished my first data analytics course it took about ten weeks of evenings and weekends the hardest part honestly was sql joins but the final project where i analysed bus delays in my city made it all click next i want to learn power bi"},
  "Last month, I finished my first data analytics course. It took about 10 weeks of evenings and weekends.\n\nThe hardest part, honestly, was SQL joins, but the final project, where I analysed bus delays in my city, made it all click.\n\nNext, I want to learn Power BI.",
  {"format": "post", "numbers": ["10"], "must_include": ["Last month", "data analytics course", "about 10 weeks", "SQL joins", "bus delays", "Power BI"],
   "must_not_include": ["#", "Posted", "excited to share", "thrilled", "proud"]},
  note="facts: finished first data analytics course last month; ABOUT 10 weeks of evenings and weekends; hardest part SQL joins; final project analysed bus delays; next wants to learn Power BI; post text only, no hashtags/emoji, no added emotion, no posting claim",
  cx=1)

# 105 put this on my LinkedIn, but task cleanup -> plain cleanup
R({"task": "cleanup", "instruction": "put this on my linkedin",
   "transcript": "we're hiring two part time designers for our print studio uh remote is fine dm me if you're interested"},
  "We're hiring two part-time designers for our print studio. Remote is fine. DM me if you're interested.",
  {"numbers_one_of": [["two", "2"]], "must_include": ["part-time designers", "print studio", "Remote is fine", "DM me"],
   "must_not_include": ["Posted", "#hiring", "LinkedIn"]},
  note="facts: hiring two part-time designers for print studio; remote fine; DM if interested (conditional kept); cleanup only, no posting claim",
  length="short")

# 106 set a reminder -> clean reminder text
R({"task": "cleanup", "instruction": "set a reminder for this",
   "transcript": "renew the car insurance before the eighteenth and uh ask them about the no claim bonus because last year they they forgot to apply it"},
  "Renew the car insurance before the 18th and ask them about the no-claim bonus, because last year they forgot to apply it.",
  {"numbers": ["18"], "must_include": ["car insurance", "before the 18th", "no-claim bonus", "last year"],
   "must_not_include": ["Reminder set", "I'll remind", "reminder"]},
  note="facts: renew car insurance BEFORE the 18th; ask about no-claim bonus because last year they forgot to apply it; reminder text cleaned only, nothing scheduled or claimed",
  pos="before", length="short")

# 107 remind me at a time -> time from the instruction not added
R({"task": "cleanup", "instruction": "remind me about this at six tomorrow",
   "transcript": "pick up the passport photos from the uh the studio near the station"},
  "Pick up the passport photos from the studio near the station.",
  {"must_include": ["passport photos", "studio near the station"], "must_not_include": ["tomorrow", "at 6", "Reminder"]},
  note="facts: pick up passport photos from studio near the station; the time 'six tomorrow' is only in the unsupported instruction, so it is not added",
  length="short")

# 108 mixed: checklist (supported) + reminder (unsupported)
R({"task": "rewrite", "format": "bullets",
   "instruction": "make this a checklist and set a reminder for sunday night",
   "transcript": "before moving out of the hostel i need to return the room key to the warden get my deposit receipt signed um cancel the mess subscription and take photos of the room so they can't claim damage later"},
  "Before moving out of the hostel, I need to:\n- Return the room key to the warden\n- Get my deposit receipt signed\n- Cancel the mess subscription\n- Take photos of the room so they can't claim damage later",
  {"format": "bullets", "must_include": ["Before moving out of the hostel", "room key", "warden", "deposit receipt", "mess subscription", "claim damage"],
   "must_not_include": ["Sunday", "Reminder", "reminder set"], "min_negations": 1},
  note="supported part done (checklist with the spoken lead-in kept as lead line); reminder unsupported, Sunday not added; facts: four tasks before moving out; photos so they can't claim damage later",
  cx=2)

# 109 convert to PDF -> cleanup only
R({"task": "cleanup", "instruction": "convert this to a pdf",
   "transcript": "the workshop on budgeting for freelancers is on saturday the fourth from eleven to one in hall b entry is free but seats are limited to thirty so register by wednesday"},
  "The workshop on budgeting for freelancers is on Saturday the 4th from 11 to 1 in Hall B. Entry is free, but seats are limited to 30, so register by Wednesday.",
  {"numbers": ["4", "11", "1", "30"], "must_include": ["budgeting for freelancers", "Saturday", "Hall B", "Entry is free", "limited to 30", "Wednesday"],
   "must_not_include": ["PDF", "converted"]},
  note="facts: workshop Saturday the 4th, 11 to 1, Hall B; entry free; seats limited to 30; register by Wednesday; no conversion claim")

# 110 mixed: numbered steps (supported) + export as PDF (unsupported)
R({"task": "rewrite", "format": "numbered", "context": "work", "header_style": "full",
   "instruction": "turn this into numbered steps and export it as a pdf",
   "transcript": "okay so for anyone claiming travel expenses first you log into the expense portal with your employee id then you create a new claim and pick the trip from the dropdown after that upload every receipt as a photo or scan and uh receipts older than sixty days won't be accepted then add your manager as the approver and finally submit it before the twenty fifth if you want it in this month's salary otherwise it goes into next month"},
  "For anyone claiming travel expenses:\n1. Log in to the expense portal with your employee ID.\n2. Create a new claim and pick the trip from the dropdown.\n3. Upload every receipt as a photo or scan. Receipts older than 60 days won't be accepted.\n4. Add your manager as the approver.\n5. Submit it before the 25th if you want it in this month's salary; otherwise, it goes into next month.",
  {"format": "numbered", "numbers": ["60", "25"], "must_include": ["travel expenses", "employee ID", "dropdown", "photo or scan", "older than 60 days", "approver", "before the 25th", "next month"],
   "must_not_include": ["PDF", "exported"], "min_negations": 1},
  note="supported part done (numbered steps, lead-in kept); export unsupported, no claim; facts: receipts older than 60 days NOT accepted; submit before the 25th IF you want it in this month's salary, otherwise next month (condition and alternative kept); photo OR scan both kept",
  cx=2, length="long")

# 111 summarize the attached file, no file, task summarize -> summary of the transcript
R({"task": "summarize", "locale": "en-in", "instruction": "summarize the attached file",
   "transcript": "so quick recap of the call with the packaging supplier this morning uh they can drop the price per box from eighteen to fifteen rupees if we order at least five thousand boxes a month lars wants to wait until we see december sales before committing and the samples of the new kraft boxes should reach us by friday"},
  "Call with the packaging supplier this morning: they can drop the price per box from ₹18 to ₹15 if we order at least 5,000 boxes a month. Lars wants to wait until we see December sales before committing. Samples of the new kraft boxes should reach us by Friday.",
  {"numbers": ["18", "15", "5,000"], "must_include": ["packaging supplier", "this morning", "₹18", "₹15", "at least 5,000", "Lars", "December sales", "kraft boxes", "Friday"],
   "must_not_include": ["attached", "the file"]},
  note="no file exists; the transcript is summarized (task summarize). facts: call with packaging supplier this morning; price per box ₹18 -> ₹15 IF at least 5,000 boxes a month ('eighteen to fifteen rupees' -> ₹ on both, same phrase); Lars wants to wait for December sales before committing (open decision); samples SHOULD reach by Friday (hedge kept)",
  cx=1)

# 112 summarize the attached file + fix this up, task cleanup -> cleanup only
R({"task": "cleanup", "instruction": "summarize the attached file and fix this up",
   "transcript": "the attached file has the uh revised seating plan for the annual dinner please please check your table number before friday"},
  "The attached file has the revised seating plan for the annual dinner. Please check your table number before Friday.",
  {"must_include": ["attached file", "revised seating plan", "annual dinner", "table number", "before Friday"],
   "must_not_include": ["Table 1", "summary"]},
  note="task cleanup and no file exists, so plain cleanup of the dictation; dictated 'the attached file' is content and stays; facts: check table number before Friday",
  cx=2, length="short")

# 113 list (supported) + calculate the total (unsupported), rupees on every amount
R({"task": "rewrite", "format": "bullets", "locale": "en-in", "header_style": "full",
   "instruction": "make a list and calculate the total",
   "transcript": "for the stall restock we need um three hundred paper cups at four hundred fifty rupees twenty packs of napkins at eighty rupees a pack and two rolls of tape at sixty rupees each"},
  "For the stall restock, we need:\n- 300 paper cups at ₹450\n- 20 packs of napkins at ₹80 a pack\n- 2 rolls of tape at ₹60 each",
  {"format": "bullets", "numbers": ["300", "450", "20", "80", "2", "60"], "must_include": ["stall restock", "paper cups", "₹450", "₹80 a pack", "₹60 each"],
   "must_not_include": ["Total", "total", "2,170", "1,600"]},
  note="list done (supported); total NOT computed (unsupported, would add a new number); facts: 300 paper cups at ₹450; 20 packs napkins at ₹80 a pack; 2 rolls tape at ₹60 each; rupees spoken for every amount so ₹ on all three",
  cx=2)

# 114 calculate the total, cleanup, no currency spoken
R({"task": "cleanup", "instruction": "calculate the total for me",
   "transcript": "taxi was twelve hundred hotel two nights at thirty five hundred each and dinner was nine eighty"},
  "Taxi was 1,200, hotel two nights at 3,500 each, and dinner was 980.",
  {"numbers": ["1,200", "3,500", "980"], "numbers_one_of": [["two", "2"]], "must_include": ["Taxi", "hotel", "each", "dinner"],
   "must_not_include": ["8,180", "Total", "₹", "$"]},
  note="facts: taxi 1,200; hotel two nights at 3,500 each; dinner 980; no total computed, no currency added (none spoken)",
  pos="before", length="short")

# 115 make it rhyme, task rewrite with no format -> plain cleanup
R({"task": "rewrite", "instruction": "make it rhyme",
   "transcript": "happy birthday tushar thanks for always covering for me when i'm sick and for the uh the terrible jokes at lunch see you at the party on friday"},
  "Happy birthday, Tushar. Thanks for always covering for me when I'm sick and for the terrible jokes at lunch. See you at the party on Friday.",
  {"must_include": ["Happy birthday, Tushar", "covering for me", "terrible jokes", "party on Friday"],
   "must_not_include": ["Hooray", "cheer"]},
  note="rhyming/verse is not a supported format and task rewrite has no format that fits, so plain cleanup; facts: thanks for covering when sick and for the jokes at lunch; party on Friday; 'Tushar' is a dictated vocative",
  length="medium")

# 116 write a poem about this, format post -> post text, no verse
R({"task": "rewrite", "format": "post", "context": "work",
   "instruction": "write a poem about this for our team page",
   "transcript": "so this quarter our small support team of six people closed over four thousand tickets um we moved to the new help desk tool in the middle of it and nobody quit which honestly felt like a miracle hamza built the reply templates bhavna trained the two new joiners and we still kept the average first response under two hours"},
  "This quarter, our small support team of six people closed over 4,000 tickets. We moved to the new help desk tool in the middle of it, and nobody quit, which honestly felt like a miracle.\n\nHamza built the reply templates, Bhavna trained the two new joiners, and we still kept the average first response under 2 hours.",
  {"format": "post", "numbers": ["4,000", "2"], "numbers_one_of": [["six", "6"]], "must_include": ["this quarter", "over 4,000 tickets", "help desk tool", "nobody quit", "Hamza", "Bhavna", "under 2 hours"],
   "must_not_include": ["#", "proud", "heroes"], "min_negations": 1},
  note="poem not supported; Format post given, so post text in plain prose; facts: team of six; OVER 4,000 tickets this quarter; moved to new help desk tool mid-quarter; nobody quit; Hamza built reply templates; Bhavna trained two new joiners; average first response UNDER 2 hours; no added praise/emotion",
  cx=1, length="long")

# 117 translate to Hindi on English speech -> English cleanup
R({"task": "cleanup", "locale": "en-in", "instruction": "translate this to hindi",
   "transcript": "aunty the gas cylinder will be delivered tomorrow between ten and twelve please keep the empty cylinder outside the door"},
  "Aunty, the gas cylinder will be delivered tomorrow between 10 and 12. Please keep the empty cylinder outside the door.",
  {"numbers": ["10", "12"], "must_include": ["Aunty", "gas cylinder", "tomorrow", "empty cylinder"],
   "must_not_include": ["सिलेंडर", "कल", "kal"]},
  note="English transcript stays English (translation unsupported); facts: cylinder delivered tomorrow between 10 and 12; keep the empty cylinder outside the door; 'aunty' is dictated vocative",
  length="short")

# 118 mixed: formal (supported) + translate into Hindi (unsupported) -> formal English email
R({"task": "rewrite", "format": "email", "register": "formal", "locale": "en-in", "recipient": "Hamza", "sender": "Kirti",
   "header_style": "full", "instruction": "make it formal and translate it into hindi",
   "transcript": "hamza the electrician can come on tuesday morning to fix the wiring in the store room but the shop has to be shut for about three hours so can we open late that day"},
  "Dear Hamza,\n\nThe electrician can come on Tuesday morning to fix the wiring in the store room, but the shop will have to be closed for about 3 hours. Could we open late that day?\n\nRegards,\nKirti",
  {"format": "email", "numbers": ["3"], "must_include": ["Dear Hamza", "electrician", "Tuesday morning", "store room", "about 3 hours", "open late", "Kirti"],
   "must_not_include": ["नमस्ते", "बिजली", "apologi"]},
  note="formal done, translation not done (English kept); facts: electrician CAN come Tuesday morning to fix store room wiring; shop must be shut ABOUT 3 hours; asks whether they can open late that day (question kept, no decision added)",
  cx=2)

# 119 answer in one line -> question kept
R({"task": "cleanup", "instruction": "answer in one line",
   "transcript": "uh does the student railway concession work on the airport line too"},
  "Does the student railway concession work on the airport line too?",
  {"must_include": ["student railway concession", "airport line"], "must_not_include": ["Yes,", "No,", "only valid"], "ends_with_question": True},
  note="question kept as a question, not answered (answering unsupported)", behavior="not_answer", length="short")

# 120 answer it in one line, rewrite, layover question with context
R({"task": "rewrite", "locale": "en-gb", "header_style": "full", "instruction": "just answer it in one line",
   "transcript": "i've got a ninety minute layover in frankfurt and i'm switching from terminal one to terminal two um is that enough time if i have to go through passport control again"},
  "I've got a 90-minute layover in Frankfurt and I'm switching from Terminal 1 to Terminal 2. Is that enough time if I have to go through passport control again?",
  {"numbers": ["90", "1", "2"], "must_include": ["Frankfurt", "Terminal 1", "Terminal 2", "passport control", "again"],
   "must_not_include": ["should be enough", "plenty of time", "tight"], "ends_with_question": True},
  note="question not answered; facts: 90-minute layover in Frankfurt; Terminal 1 -> Terminal 2; condition 'if I have to go through passport control again' kept. Waiver: checker does not read 'terminal one' as 1 and flags 1 as invented",
  behavior="not_answer", waivers=["number_invented"])

# 121 mixed: shorter (supported, visible) + send to Lars (unsupported); speaker said "hey lars"
R({"task": "rewrite", "format": "message", "context": "work",
   "instruction": "make it shorter and send it to lars",
   "transcript": "hey lars so um just a heads up the quarterly team lunch that was going to be this friday is now going to be next friday instead because uh half the team is going to be away at the trade fair this week so yeah next friday same place same time"},
  "Hey Lars, heads up: the quarterly team lunch moves from this Friday to next Friday, because half the team will be away at the trade fair this week. Same place, same time.",
  {"format": "message", "must_include": ["Hey Lars", "quarterly team lunch", "this Friday", "next Friday", "half the team", "trade fair", "Same place, same time"],
   "must_not_include": ["Sent", "sent to"]},
  note="shorter done (repetition dropped); send unsupported, no claim; facts: lunch moved from this Friday to next Friday because half the team away at trade fair this week; same place, same time; 'hey lars' dictated so kept",
  pos="followup", cx=2)

# 122 mixed: fix grammar + keep casual (supported) + schedule for Friday (unsupported)
R({"task": "rewrite", "format": "message", "register": "casual", "context": "chat",
   "instruction": "fix the grammar, keep it casual and schedule it to go out friday",
   "transcript": "so me and kirti was thinking we should do the book club at my place this month instead of the usual spot um since the owner told us they're closing early on sundays now we can start at five i'll make chai and somebody needs to bring snacks oh and the book is the one about the lighthouse keeper if you haven't finished it that's fine just come anyway"},
  "Kirti and I were thinking we should do the book club at my place this month instead of the usual spot, since the owner told us they're closing early on Sundays now. We can start at 5. I'll make chai, and somebody needs to bring snacks. Oh, and the book is the one about the lighthouse keeper. If you haven't finished it, that's fine; just come anyway.",
  {"format": "message", "numbers": ["5"], "must_include": ["Kirti and I were", "book club", "my place", "this month", "closing early on Sundays", "start at 5", "chai", "snacks", "lighthouse keeper", "just come anyway"],
   "must_not_include": ["Friday", "scheduled", "me and Kirti was"], "min_negations": 1},
  note="grammar fixed ('me and kirti was' -> 'Kirti and I were'), casual kept; scheduling unsupported, Friday not added; facts: book club at my place this month, not usual spot, since owner closes early on Sundays now; start at 5 (no a.m./p.m.); I'll make chai (dictated commitment); somebody bring snacks; book about lighthouse keeper; if not finished, come anyway",
  cx=3, length="long",
  waivers=None)

# 123 polite (supported) + look up phone number (unsupported); name only in the instruction -> no vocative
R({"task": "rewrite", "format": "message", "context": "work",
   "instruction": "make it more polite and look up bhavna's phone number and add it at the end",
   "transcript": "need the signed vendor forms back by tomorrow noon the auditors are coming on thursday and we can't show them unsigned copies"},
  "Could you please send the signed vendor forms back by tomorrow noon? The auditors are coming on Thursday, and we can't show them unsigned copies.",
  {"format": "message", "must_include": ["signed vendor forms", "tomorrow noon", "auditors", "Thursday", "unsigned copies"],
   "must_not_include": ["Bhavna,", "Hi Bhavna", "+91", "Phone:"], "min_negations": 1},
  note="polite done; phone lookup unsupported, nothing added; 'Bhavna' appears only in the instruction, so NO vocative opener (stage-1 fix); facts: signed vendor forms needed back by tomorrow noon; auditors coming Thursday; can't show unsigned copies",
  cx=2)

# 124 mixed: summarize in two lines (supported) + translate to Hindi (unsupported)
R({"task": "summarize", "locale": "en-in", "instruction": "summarize this in two lines and translate it to hindi",
   "transcript": "okay so the landlord called this evening um the rent goes up by two thousand from january but he'll fix the leaking bathroom tap and repaint the bedroom before that and uh if we sign for another eleven months he won't increase it again till next december"},
  "The landlord called this evening: rent goes up by 2,000 from January, but he'll fix the leaking bathroom tap and repaint the bedroom before that.\nIf we sign for another 11 months, he won't increase it again till next December.",
  {"numbers": ["2,000", "11"], "must_include": ["landlord", "this evening", "January", "leaking bathroom tap", "repaint the bedroom", "If we sign", "11 months", "next December"],
   "must_not_include": ["किराया", "₹"], "min_negations": 1},
  note="two-line summary done, in English (translation unsupported); facts: landlord called this evening; rent up 2,000 from January (no currency spoken, none added); he'll fix leaking tap and repaint bedroom before that; IF they sign another 11 months, NO increase till next December",
  cx=2)

# 125 LinkedIn post (supported format) + tag Erik and post (unsupported)
R({"task": "rewrite", "format": "post", "context": "work", "locale": "en-in", "header_style": "full",
   "instruction": "turn this into a linkedin post, tag erik and post it",
   "transcript": "after almost two years of running our handmade soap business from my kitchen we finally moved into a proper workspace this week uh it's small just one room but we now have space for drying racks and a packing table none of this would have happened without erik who did all our product photos for free when we couldn't afford a photographer and to everyone who ordered during the first few months when the labels were still handwritten thank you we're starting wholesale orders from next month"},
  "After almost two years of running our handmade soap business from my kitchen, we finally moved into a proper workspace this week. It's small, just one room, but we now have space for drying racks and a packing table.\n\nNone of this would have happened without Erik, who did all our product photos for free when we couldn't afford a photographer. And to everyone who ordered during the first few months, when the labels were still handwritten: thank you.\n\nWe're starting wholesale orders from next month.",
  {"format": "post", "numbers_one_of": [["two", "2"]], "must_include": ["almost two years", "handmade soap", "this week", "one room", "Erik", "for free", "handwritten", "wholesale orders", "next month"],
   "must_not_include": ["@Erik", "#", "Posted", "thrilled"], "min_negations": 2},
  note="post text done; tagging and posting unsupported (Erik written as a plain name, no @, no claim); facts: ALMOST two years from home kitchen; moved to workspace this week; just one room; Erik did product photos for free when they couldn't afford a photographer; thanks to early customers (handwritten labels); wholesale from next month",
  cx=3, length="long")

# 126 fix punctuation (supported) + delete the recording (unsupported)
R({"task": "cleanup", "instruction": "fix the punctuation and then delete the recording",
   "transcript": "lars your parcel is with the security desk ask for amina she's there till seven"},
  "Lars, your parcel is with the security desk. Ask for Amina; she's there till 7.",
  {"numbers": ["7"], "must_include": ["Lars", "security desk", "Amina", "till 7"], "must_not_include": ["deleted", "recording"]},
  note="facts: parcel with security desk; ask for Amina, there till 7 (no a.m./p.m.); 'lars' dictated vocative; nothing deleted or claimed",
  cx=2, length="short")

# 127 reply to Erik's email, friendly; Recipient + Sender drive greeting/sign-off
R({"task": "rewrite", "format": "email", "tone": "friendly", "recipient": "Erik", "sender": "Rosa",
   "instruction": "reply to erik's email for me and keep it friendly",
   "transcript": "thanks for the itinerary it looks great um just two changes we'd rather take the morning ferry to the island instead of the afternoon one because we want time at the beach and can you check if the guesthouse has a room with two single beds instead of a double also my sister might join for the last two nights but i'll only know by the end of the month so please don't book anything for her yet"},
  "Hi Erik,\n\nThanks for the itinerary; it looks great. Just two changes: we'd rather take the morning ferry to the island instead of the afternoon one, because we want time at the beach. And could you check if the guesthouse has a room with two single beds instead of a double?\n\nAlso, my sister might join for the last two nights, but I'll only know by the end of the month, so please don't book anything for her yet.\n\nBest,\nRosa",
  {"format": "email", "numbers_one_of": [["two", "2"]], "must_include": ["Hi Erik", "itinerary", "morning ferry", "afternoon one", "two single beds", "might join", "last two nights", "end of the month", "don't book anything", "Rosa"],
   "must_not_include": ["Replied", "I'm so glad", "can't wait"], "min_negations": 1},
  note="email reply text only, no reply/send claim; facts: dictated thanks + 'looks great'; morning ferry instead of afternoon (want beach time); check for room with two single beds instead of a double; sister MIGHT join for last two nights, will ONLY know by end of month, so DON'T book for her yet; friendly in wording only, no added feelings; greeting from [Recipient], sign-off from [Sender]",
  pos="before", cx=2, length="long")

# 128 write a short poem about this, task cleanup -> cleanup only
R({"task": "cleanup", "instruction": "write a short poem about this",
   "transcript": "the rooftop garden finally has tomatoes uh fourteen of them on the first plant and the basil is going crazy please don't water it on rainy days"},
  "The rooftop garden finally has tomatoes, 14 of them on the first plant, and the basil is going crazy. Please don't water it on rainy days.",
  {"numbers": ["14"], "must_include": ["rooftop garden", "tomatoes", "first plant", "basil", "rainy days"],
   "must_not_include": ["bloom", "verse"], "min_negations": 1},
  note="poem unsupported, task cleanup, so plain cleanup; facts: 14 tomatoes on the first plant; basil going crazy; don't water it on rainy days",
  length="short")

assert len(rows) == 28
save(OUT, rows)
print(f"wrote {len(rows)} -> {os.path.abspath(OUT)}")
