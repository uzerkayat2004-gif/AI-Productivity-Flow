"""W14 stage 1 generator: bucket followup_style (follow-up edits with task=edit, plus style rewrites).

Domains: event management agency, SaaS sales, landscaping company, podcast production, personal admin.
Names: Yash, Anjali, Martin, Selin, Kwame, Lucía, Prakash, Fen.
Re-running reproduces research/vf_phase2b/data/batches/W14_s1.jsonl and W14_s2.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W14"
STAGE = "s1"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_{STAGE}.jsonl"))
BUCKET = "followup_style"

FE = "followup_edit"
NL = "nl_instruction"
MC = "multi_constraint"

ROWS = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def R(slice_, request, target, assertions, note=None, pos=None, cx=None, waivers=None):
    i = len(ROWS) + 1
    req = dict(request)
    if pos is None:
        pos = "followup" if req["task"] == "edit" else ("after" if "instruction" in req else "structured")
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient", "facts")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    src = req.get("draft") or req.get("transcript", "")
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(src)}
    ROWS.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, assertions, f"w14-sc-{i:03d}",
                    author=WID, note=note, meta=meta, waivers=waivers))


# ============================================================ follow-up edits (task=edit)

# 1 confident tone, keep conditional commitment
R(FE, {"task": "edit", "header_style": "full",
       "draft": "Hi Selin,\n\nSorry if this is a bit early, but I just wanted to let you know that the riverside terrace "
                "is available for your product launch on November 14. If the venue confirms by Friday, we will hold "
                "it for 120 guests. I hope that sounds okay.\n\nBest,\nYash",
       "instruction": "actually, rewrite the previous draft with a more confident tone but keep the conditional commitment unchanged"},
  "Hi Selin,\n\nThe riverside terrace is available for your product launch on November 14. If the venue confirms "
  "by Friday, we will hold it for 120 guests.\n\nBest,\nYash",
  {"format": "email", "numbers": ["14", "120"],
   "must_include": ["Selin", "riverside terrace", "November 14", "If the venue confirms by Friday, we will hold it for 120 guests", "Yash"],
   "must_not_include": ["Sorry", "hope that sounds okay"]},
  "facts: terrace available Nov 14; conditional commitment 'if the venue confirms by Friday, we will hold it for 120 guests' kept word for word; only the apology/softeners removed for confidence")

# 2 make it shorter (3 paragraphs)
R(FE, {"task": "edit",
       "draft": "Hi Martin,\n\nThanks again for taking the time to join the demo yesterday. As we discussed during the "
                "call, the Growth plan is $49 per seat per month, and since your team has 30 seats, the annual total "
                "would come to $17,640. Just a quick reminder that the onboarding package is not included in that price.\n\n"
                "If your finance team approves the budget before the end of the quarter, we can lock in this pricing "
                "for two years.\n\nBest,\nAnjali",
       "instruction": "make it shorter"},
  "Hi Martin,\n\nThanks again for joining the demo yesterday. The Growth plan is $49 per seat per month, so for your 30 seats "
  "the annual total is $17,640. The onboarding package is not included in that price.\n\nIf your finance team approves "
  "the budget before the end of the quarter, we can lock in this pricing for two years.\n\nBest,\nAnjali",
  {"format": "email", "numbers": ["49", "30", "17,640"], "min_negations": 1,
   "must_include": ["Martin", "Growth plan", "onboarding", "If your finance team approves", "two years", "Anjali"]},
  "facts: $49/seat/month, 30 seats, $17,640 annual; onboarding NOT included; conditional: pricing locked for two years only if finance approves before end of quarter")

# 3 change Thursday to Friday (facts correct)
R(FE, {"task": "edit", "facts": "correct",
       "draft": "Hi Kwame, the crew will start laying the turf on Thursday at 8 a.m. Please keep the side gate unlocked "
                "and move the cars off the driveway.",
       "instruction": "change thursday to friday"},
  "Hi Kwame, the crew will start laying the turf on Friday at 8 a.m. Please keep the side gate unlocked and move the "
  "cars off the driveway.",
  {"numbers": ["8"], "must_include": ["Kwame", "Friday", "side gate unlocked", "driveway"], "must_not_include": ["Thursday"]},
  "facts: only Thursday -> Friday changed (authorised); 8 a.m., gate unlocked, cars off driveway unchanged")

# 4 add dictated content
R(FE, {"task": "edit",
       "draft": "The client dinner is on Saturday, March 7 at 7:30 p.m. at Olive Court. Dress code is smart casual.",
       "instruction": "add that the venue has parking"},
  "The client dinner is on Saturday, March 7 at 7:30 p.m. at Olive Court. Dress code is smart casual. The venue has parking.",
  {"numbers": ["7", "7:30"], "must_include": ["Olive Court", "smart casual", "The venue has parking"]},
  "facts: Saturday March 7, 7:30 p.m., Olive Court, smart casual unchanged; only the dictated parking sentence added. "
  "Waiver number_missing: checker parses the draft's digit time '7:30' as separate 7 and 30, but the target keeps '7:30' verbatim",
  waivers=["number_missing"])

# 5 remove the ad-break paragraph (3 paragraphs)
R(FE, {"task": "edit", "header_style": "full",
       "draft": "Hi Lucía,\n\nThe final mix of episode 42 is uploaded to the shared drive. I left the intro music at the "
                "lower level you asked for.\n\nI also tried a version with the ad break moved to the middle, but I don't "
                "think it works as well, so I haven't uploaded it.\n\nWe still need your approval on the show notes "
                "before Wednesday.\n\nThanks,\nFen",
       "instruction": "take out the bit about the ad break version"},
  "Hi Lucía,\n\nThe final mix of episode 42 is uploaded to the shared drive. I left the intro music at the lower level "
  "you asked for.\n\nWe still need your approval on the show notes before Wednesday.\n\nThanks,\nFen",
  {"format": "email", "numbers": ["42"], "must_include": ["Lucía", "shared drive", "intro music", "show notes", "Wednesday", "Fen"],
   "must_not_include": ["ad break"]},
  "facts: ad-break paragraph removed as instructed; episode 42, lower intro music, approval on show notes still needed before Wednesday all unchanged. "
  "Waiver negation_lost: the two negations ('don't think', 'haven't uploaded') were inside the paragraph the instruction removed",
  waivers=["negation_lost"])

# 6 less pushy, keep deadline and negation
R(FE, {"task": "edit",
       "draft": "Martin, I need an answer on the renewal by tomorrow. Your current discount expires on the 31st and we "
                "can't extend it.",
       "instruction": "make it sound less pushy"},
  "Martin, could you let me know about the renewal by tomorrow? Your current discount expires on the 31st, and we "
  "can't extend it.",
  {"numbers": ["31"], "min_negations": 1, "must_include": ["Martin", "renewal", "tomorrow", "discount", "can't extend"]},
  "facts: answer needed by tomorrow; discount expires on the 31st; negation 'can't extend it' kept")

# 7 fix grammar and spelling
R(FE, {"task": "edit",
       "draft": "need to renew the car insurence before 18th and dont forget to carry the pollution certificate their",
       "instruction": "fix the grammar and spelling"},
  "Need to renew the car insurance before the 18th, and don't forget to carry the pollution certificate there.",
  {"numbers": ["18"], "min_negations": 1, "must_include": ["car insurance", "pollution certificate"]},
  "facts: renew car insurance before the 18th; negation 'don't forget' kept; only spelling/grammar fixed")

# 8 more formal (en-in, lakh amount)
R(FE, {"task": "edit", "locale": "en-in",
       "draft": "Hi Prakash,\n\nHere's the quote for the backyard: ₹1,85,000 for the lawn, drip irrigation and two raised "
                "beds. We can't start till the monsoon's over, so probably early November.\n\nThanks,\nKwame",
       "instruction": "make it more formal"},
  "Dear Prakash,\n\nPlease find the quote for the backyard below: ₹1,85,000 for the lawn, drip irrigation and two "
  "raised beds. We cannot start until the monsoon is over, so probably in early November.\n\nRegards,\nKwame",
  {"format": "email", "numbers": ["1,85,000"], "min_negations": 1,
   "must_include": ["Prakash", "drip irrigation", "two raised beds", "monsoon", "probably", "early November", "Kwame"]},
  "facts: ₹1,85,000 for lawn, drip irrigation, two raised beds; cannot start until monsoon is over; start hedged 'probably early November'")

# 9 change the time (facts correct)
R(FE, {"task": "edit", "facts": "correct",
       "draft": "Reminder: Selin's interview recording is on Tuesday at 4 p.m. in Studio B. Please arrive 15 minutes "
                "early for the mic check.",
       "instruction": "make it 4:30 instead of 4"},
  "Reminder: Selin's interview recording is on Tuesday at 4:30 p.m. in Studio B. Please arrive 15 minutes early for "
  "the mic check.",
  {"numbers": ["4:30", "15"], "must_include": ["Selin", "Tuesday", "Studio B", "mic check"], "must_not_include": ["4 p.m."]},
  "facts: only 4 p.m. -> 4:30 p.m. (authorised); Tuesday, Studio B, 15 minutes early unchanged")

# 10 turn items into bullets, keep closing note
R(FE, {"task": "edit",
       "draft": "For Saturday's setup we need the stage riser, two projectors, 40 folding chairs and the welcome banner. "
                "The banner is not ready yet.",
       "instruction": "turn the items into a bullet list and keep the note about the banner at the end"},
  "For Saturday's setup we need:\n- The stage riser\n- Two projectors\n- 40 folding chairs\n- The welcome banner\n\n"
  "The banner is not ready yet.",
  {"numbers": ["40"], "min_negations": 1,
   "must_include": ["- The stage riser", "- Two projectors", "- 40 folding chairs", "- The welcome banner", "not ready yet"]},
  "facts: four items (riser, two projectors, 40 chairs, banner) for Saturday; negation 'banner is not ready yet' kept at the end")

# 11 change name (facts correct)
R(FE, {"task": "edit", "facts": "correct", "header_style": "full",
       "draft": "Yash will run the demo for Northwind on Monday, and Anjali will send the contract once legal signs off.",
       "instruction": "actually prakash is running the demo, not yash"},
  "Prakash will run the demo for Northwind on Monday, and Anjali will send the contract once legal signs off.",
  {"must_include": ["Prakash", "Northwind", "Monday", "Anjali", "once legal signs off"], "must_not_include": ["Yash"]},
  "facts: only owner Yash -> Prakash changed (authorised); Monday demo and Anjali's conditional 'once legal signs off' unchanged")

# 12 add a subject line (asked for in instruction)
R(FE, {"task": "edit",
       "draft": "Hi Fen,\n\nAttached is the invoice for the October maintenance visits. The total is $640, due within "
                "14 days.\n\nThanks,\nKwame",
       "instruction": "add a subject line that says October maintenance invoice"},
  "Subject: October maintenance invoice\n\nHi Fen,\n\nAttached is the invoice for the October maintenance visits. The "
  "total is $640, due within 14 days.\n\nThanks,\nKwame",
  {"format": "email", "numbers": ["640", "14"], "must_include": ["Subject: October maintenance invoice", "Fen", "Kwame"]},
  "facts: $640 due within 14 days unchanged; Subject line added only because the instruction asked for it. "
  "Waiver invented_subject: the Subject line is requested in the instruction (known checker gap)",
  waivers=["invented_subject"])

# 13 make it casual (neighbour)
R(FE, {"task": "edit",
       "draft": "Dear Martin, I would like to inform you that I will not be able to attend the society meeting on "
                "Sunday. Kindly share the minutes afterwards.",
       "instruction": "make this casual, it's just for my neighbour"},
  "Hi Martin, I won't be able to make the society meeting on Sunday. Could you share the minutes afterwards?",
  {"min_negations": 1, "must_include": ["Martin", "society meeting", "Sunday", "minutes"]},
  "facts: will NOT attend the Sunday society meeting; request to share the minutes afterwards kept")

# 14 expand a terse note, add nothing
R(FE, {"task": "edit",
       "draft": "Ep 18 drops Fri. Guest: Kwame. Topic: soil health.",
       "instruction": "write this out as proper sentences for the newsletter, don't add anything"},
  "Episode 18 drops on Friday. Our guest is Kwame, and the topic is soil health.",
  {"numbers": ["18"], "must_include": ["Friday", "Kwame", "soil health"]},
  "facts: episode 18, Friday, guest Kwame, topic soil health; nothing added")

# 15 drop the apology
R(FE, {"task": "edit",
       "draft": "Hi Anjali, so sorry for the delay! The floor plan for the gala is attached. The bar has moved to the "
                "east wall and the photo booth is now next to the entrance.",
       "instruction": "drop the apology"},
  "Hi Anjali, the floor plan for the gala is attached. The bar has moved to the east wall and the photo booth is now "
  "next to the entrance.",
  {"must_include": ["Anjali", "floor plan", "east wall", "photo booth", "entrance"], "must_not_include": ["sorry"]},
  "facts: bar moved to east wall, photo booth next to entrance unchanged; apology removed as instructed")

# 16 correct the headcount (facts correct)
R(FE, {"task": "edit", "facts": "correct",
       "draft": "Final headcount for the offsite is 58, including 6 vegetarian meals. The coach leaves the office at 9:15 a.m.",
       "instruction": "the headcount is 85 not 58"},
  "Final headcount for the offsite is 85, including 6 vegetarian meals. The coach leaves the office at 9:15 a.m.",
  {"numbers": ["85", "6", "9:15"], "must_not_include": ["58"]},
  "facts: only headcount 58 -> 85 (authorised); 6 vegetarian meals and 9:15 a.m. coach unchanged")

# 17 warmer, keep the dates and negation
R(FE, {"task": "edit",
       "draft": "Lucía, the kids won't have their lesson this Thursday. We're travelling. Next lesson is the 23rd as usual.",
       "instruction": "make it warmer and keep the dates"},
  "Lucía, just a quick heads-up that the kids won't have their lesson this Thursday, as we're travelling. The next "
  "lesson is on the 23rd as usual.",
  {"numbers": ["23"], "min_negations": 1, "must_include": ["Lucía", "Thursday", "travelling", "as usual"]},
  "facts: no lesson this Thursday (negation kept) because travelling; next lesson the 23rd as usual; only warmth added, no new facts")

# 18 word swap
R(FE, {"task": "edit",
       "draft": "Three customers asked for SSO this month, and two customers want the Slack integration before renewal.",
       "instruction": "use clients instead of customers"},
  "Three clients asked for SSO this month, and two clients want the Slack integration before renewal.",
  {"must_include": ["Three clients", "two clients", "SSO", "Slack integration", "before renewal"], "must_not_include": ["customers"]},
  "facts: three asked for SSO this month; two want Slack integration before renewal; only the word changed")

# 19 cut to under 30 words, keep both requests
R(FE, {"task": "edit",
       "draft": "Just so everyone on the crew knows, the client at the Green Park job has asked us to please not use the "
                "leaf blower before 9 a.m. on weekdays because their baby naps in the morning, and they'd also like us "
                "to close the back gate every time because of the dog.",
       "instruction": "cut it down to under 30 words, keep both requests"},
  "Green Park job: no leaf blower before 9 a.m. on weekdays, as the baby naps in the morning. Close the back gate every "
  "time because of the dog.",
  {"numbers": ["9"], "min_negations": 1, "max_words": 30,
   "must_include": ["Green Park", "leaf blower", "weekdays", "back gate", "dog"]},
  "facts: no leaf blower before 9 a.m. on weekdays (negation, reason baby naps); close back gate every time (dog); under 30 words")

# 20 unsupported 'send' in instruction: do only the writing part
R(FE, {"task": "edit",
       "draft": "Selin, the guest release form is still not signed. We can't publish without it.",
       "instruction": "make it more polite and send it to selin"},
  "Selin, just a gentle reminder that the guest release form is still not signed. Unfortunately, we can't publish "
  "without it.",
  {"min_negations": 2, "must_include": ["Selin", "guest release form", "still not signed", "can't publish"],
   "must_not_include": ["sent", "I've sent"]},
  "facts: form still not signed; can't publish without it (both negations kept); 'send it' is an unsupported action, so only the politeness edit is done and no sending is claimed")

# 21 put the deadline first
R(FE, {"task": "edit", "header_style": "full",
       "draft": "We need the final guest list for the awards night, with dietary requirements and plus-ones, by October 30.",
       "instruction": "put the deadline first"},
  "By October 30, we need the final guest list for the awards night, with dietary requirements and plus-ones.",
  {"numbers": ["30"], "must_include": ["October 30", "final guest list", "awards night", "dietary requirements", "plus-ones"]},
  "facts: deadline October 30 moved to the front; guest list with dietary requirements and plus-ones unchanged")

# 22 instruction is a question about the draft: do not answer it
R(FE, {"task": "edit",
       "draft": "Your passport renewal appointment is on the 9th at 11:40 a.m.",
       "instruction": "what documents do i need to bring"},
  "Your passport renewal appointment is on the 9th at 11:40 a.m.",
  {"behavior": "not_answer", "numbers": ["9", "11:40"], "must_include": ["passport renewal appointment"],
   "must_not_include": ["documents", "bring"]},
  "facts: appointment on the 9th at 11:40 a.m.; the instruction is a question, so it is not answered and the draft is returned unchanged. "
  "Waiver number_missing: checker parses the draft's digit time '11:40' as separate 11 and 40, but the target keeps '11:40' verbatim",
  waivers=["number_missing"])

# 23 turn a message into an email with given recipient and sender name
R(FE, {"task": "edit",
       "draft": "The Q4 pipeline review is moved to Thursday at 2. Please bring the updated forecast and the list of "
                "stalled deals.",
       "instruction": "turn it into a short email to anjali and sign it from martin"},
  "Hi Anjali,\n\nThe Q4 pipeline review is moved to Thursday at 2. Please bring the updated forecast and the list of "
  "stalled deals.\n\nBest,\nMartin",
  {"format": "email", "numbers": ["2"], "must_include": ["Anjali", "Q4 pipeline review", "Thursday", "updated forecast", "stalled deals", "Martin"]},
  "facts: Q4 review moved to Thursday at 2; bring updated forecast and stalled-deals list; recipient Anjali and sender Martin come from the instruction")

# ============================================================ style rewriting (task=rewrite)

# 24 confident email; hedge 'I think ... could' stays; conditional offer stays
R(MC, {"task": "rewrite", "format": "email", "tone": "confident", "sender": "Anjali", "recipient": "Martin",
       "context": "work",
       "transcript": "um hi martin so i i think our analytics add-on could maybe help your team cut the reporting time "
                     "uh it's twelve dollars per user a month and if you sign before november fifteenth we'll include "
                     "the setup for free"},
  "Hi Martin,\n\nI think our analytics add-on could help your team cut reporting time. It's $12 per user per month, and "
  "if you sign before November 15, we'll include the setup for free.\n\nBest,\nAnjali",
  {"format": "email", "numbers": ["12", "15"], "must_include": ["Martin", "analytics add-on", "I think", "could", "November 15", "setup for free", "Anjali"]},
  "facts: $12 per user per month; free setup only if signed before Nov 15 (condition kept); hedge 'I think ... could' kept under confident tone")

# 25 formal + wording keep (cleanup operations only)
R(MC, {"task": "rewrite", "register": "formal", "wording": "keep",
       "transcript": "uh the hedge along the north boundary needs trimming before the inspection on the twentieth and "
                     "the uh the gutters are blocked again"},
  "The hedge along the north boundary needs trimming before the inspection on the 20th, and the gutters are blocked again.",
  {"numbers": ["20"], "must_include": ["hedge along the north boundary needs trimming", "inspection", "gutters are blocked again"]},
  "facts: hedge trimming before the inspection on the 20th; gutters blocked 'again' (fact kept); wording keep = cleanup only")

# 26 shorter + friendly message (long transcript)
R(MC, {"task": "rewrite", "format": "message", "tone": "friendly", "length": "shorter", "header_style": "full",
       "transcript": "okay so for the guests coming on thursday's episode um can you let them know that we record at "
                     "the studio on park road not the old one on mill lane and uh they should bring headphones if "
                     "they have them we do have spares but only two pairs and the session is about ninety minutes "
                     "including like a ten minute sound check at the start and um there's no parking on site so the "
                     "metro is probably easier"},
  "Quick note for Thursday's guests: we record at the studio on Park Road, not the old one on Mill Lane. Bring "
  "headphones if you have them, as we only have two spare pairs. The session is about 90 minutes, including a "
  "10-minute sound check at the start. There's no parking on site, so the metro is probably easier.",
  {"format": "message", "numbers": ["90", "10"], "min_negations": 2,
   "must_include": ["Thursday", "Park Road", "Mill Lane", "headphones", "two", "no parking", "probably"]},
  "facts: Park Road NOT Mill Lane; headphones if they have them, only two spare pairs; about 90 min incl. 10-min sound check; no parking on site; metro 'probably' easier (hedge kept)")

# 27 casual message
R(MC, {"task": "rewrite", "format": "message", "register": "casual",
       "transcript": "so i was wondering whether you'd be able to return the camping stove you borrowed by saturday "
                     "since we're leaving for the trip on sunday morning"},
  "Could you bring back the camping stove you borrowed by Saturday? We're leaving for the trip on Sunday morning.",
  {"format": "message", "must_include": ["camping stove", "Saturday", "Sunday morning"]},
  "facts: return stove by Saturday; leaving Sunday morning")

# 28 empathetic formal email (event agency), no promises added
R(MC, {"task": "rewrite", "format": "email", "tone": "empathetic", "register": "formal", "recipient": "Selin",
       "sender": "Yash",
       "transcript": "selin i know you were really looking forward to the jazz trio but the band cancelled this morning "
                     "because their drummer is unwell um we have two other bands free on the date and i can send you "
                     "their videos today if you want"},
  "Dear Selin,\n\nI know you were really looking forward to the jazz trio. Unfortunately, the band "
  "cancelled this morning because their drummer is unwell. We have two other bands free on the date, and I can send "
  "you their videos today if you would like.\n\nRegards,\nYash",
  {"format": "email", "must_include": ["Selin", "jazz trio", "cancelled this morning", "drummer is unwell", "two other bands", "if you would like", "Yash"]},
  "facts: jazz trio cancelled this morning (drummer unwell); two other bands free on the date; offer to send videos today is conditional 'if you want' (dictated offer, kept conditional); no apology added; empathy carried by 'Unfortunately'")

# 29 instruction only: more direct, drop softeners, keep 'probably'
R(NL, {"task": "rewrite",
       "instruction": "make it more direct, drop the softeners but keep the probably",
       "transcript": "hey so i was just wondering if maybe when you get a sec you could send me the final run of show "
                     "for the summit because the venue is probably going to ask for it on monday"},
  "Please send me the final run of show for the summit. The venue is probably going to ask for it on Monday.",
  {"must_include": ["final run of show", "summit", "probably", "Monday"], "must_not_include": ["wondering", "when you get a sec"]},
  "facts: request for final run of show; venue 'probably' asks for it Monday (hedge on a fact kept); only request softeners dropped")

# 30 excited post, instruction no hashtags or emoji
R(MC, {"task": "rewrite", "format": "post", "tone": "excited", "locale": "en-in",
       "instruction": "no hashtags or emoji, and keep the ticket price exactly",
       "transcript": "we're running the lantern night market again this year on december sixth at the old mill grounds "
                     "um entry is two hundred rupees and kids under ten get in free"},
  "The lantern night market is back this year! Join us on December 6 at the old mill grounds. Entry is ₹200, and kids "
  "under 10 get in free.",
  {"format": "post", "numbers": ["6", "200", "10"], "must_include": ["lantern night market", "old mill grounds", "free"],
   "must_not_include": ["#"]},
  "facts: December 6 at old mill grounds; entry ₹200 (rupees spoken); kids under 10 free; 'again this year' kept as 'back this year'",
  pos="before")

# 31 formal email en-in, keep amount and alternative
R(MC, {"task": "rewrite", "format": "email", "register": "formal", "recipient": "Prakash", "sender": "Fen",
       "locale": "en-in",
       "transcript": "hi prakash the society maintenance charge of four thousand five hundred rupees for october hasn't "
                     "shown up in my statement can you check if it went through or uh if i should pay again by upi"},
  "Dear Prakash,\n\nThe society maintenance charge of ₹4,500 for October has not shown up in my statement. Could you "
  "please check whether it went through, or whether I should pay again by UPI?\n\nRegards,\nFen",
  {"format": "email", "numbers": ["4,500"], "min_negations": 1,
   "must_include": ["Prakash", "society maintenance charge", "October", "UPI", "Fen"]},
  "facts: ₹4,500 October maintenance not in statement (negation kept); question with both options: went through OR pay again by UPI")

# 32 longer message, no new facts
R(MC, {"task": "rewrite", "format": "message", "length": "longer", "context": "work",
       "transcript": "tell the client the new lawn needs two more weeks before anyone walks on it"},
  "The new lawn needs two more weeks before anyone walks on it, so please keep off it until then.",
  {"format": "message", "must_include": ["new lawn", "two more weeks", "before anyone walks on it"]},
  "facts: two more weeks before anyone walks on the new lawn; 'keep off it until then' restates the same restriction, no new facts")

# 33 warm tone, keep both options
R(NL, {"task": "rewrite", "tone": "warm",
       "instruction": "keep both time options",
       "transcript": "um we can do the onboarding call on tuesday at ten or wednesday at three whichever suits your team"},
  "We'd be glad to do the onboarding call on Tuesday at 10 or Wednesday at 3, whichever suits your team best.",
  {"numbers": ["10", "3"], "must_include": ["onboarding call", "Tuesday", "Wednesday", "whichever suits your team"]},
  "facts: alternative kept: Tuesday at 10 OR Wednesday at 3; team chooses", pos="before")

# 34 playful message, keep the negation
R(MC, {"task": "rewrite", "format": "message", "tone": "playful",
       "transcript": "reminder to everyone the mic stands are not toys please stop spinning them during breaks"},
  "Friendly reminder, everyone: the mic stands are not toys! Please stop spinning them during breaks.",
  {"format": "message", "min_negations": 1, "must_include": ["mic stands are not toys", "spinning them during breaks"]},
  "facts: mic stands are not toys (negation kept); stop spinning them during breaks")

# 35 wording keep + casual, long multi-sentence with a self-correction
R(MC, {"task": "rewrite", "register": "casual", "wording": "keep", "header_style": "full",
       "transcript": "so for the episode notes um we talked to kwame about composting at home and uh he said the "
                     "biggest mistake is adding too much uh too many greens and not enough browns um the giveaway "
                     "winner gets three bags no wait five bags of his compost and we're announcing it on the "
                     "twelfth"},
  "For the episode notes, we talked to Kwame about composting at home, and he said the biggest mistake is adding too "
  "many greens and not enough browns. The giveaway winner gets five bags of his compost, and we're announcing it on "
  "the 12th.",
  {"numbers": ["12"], "min_negations": 1,
   "must_include": ["Kwame", "composting at home", "too many greens and not enough browns", "five bags"],
   "must_not_include": ["three bags"]},
  "facts: self-correction applied: three -> five bags; 'not enough browns' kept; announcement on the 12th; wording keep = cleanup only")


# ============================================================ stage 2 (TC-W14-101...)
# Records live in W14_s2_part*.py (executed here) and use R2. Stage-1 rows above are untouched.
# Extra domains for stage 2: facilities management, party rentals, nonprofit grants, recruitment agency.
# Extra names: Rohit, Elin, Obinna, Margaux.
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
ROWS2 = []


def R2(slice_, request, target, assertions, note=None, pos=None, cx=None, waivers=None):
    n = 101 + len(ROWS2)
    req = dict(request)
    # ~30% full headers overall: every 4th stage-2 record (n % 4 == 2) also gets the full header.
    if n % 4 == 2:
        req.setdefault("header_style", "full")
    if pos is None:
        pos = "followup" if req["task"] == "edit" else ("after" if "instruction" in req else "structured")
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient", "facts")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    src = req.get("draft") or req.get("transcript", "")
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(src)}
    ROWS2.append(rec(f"TC-{WID}-{n:03d}", BUCKET, slice_, req, target, assertions, f"w14-sc-{n:03d}",
                     author=WID, note=note, meta=meta, waivers=waivers))


S2_PARTS = ("W14_s2_part1.py", "W14_s2_part2.py", "W14_s2_part3.py")
for _part in S2_PARTS:
    _pp = os.path.join(HERE, _part)
    if os.path.exists(_pp):
        exec(compile(open(_pp, encoding="utf-8").read(), _pp, "exec"))


if __name__ == "__main__":
    save(OUT, ROWS)
    print(f"wrote {len(ROWS)} records to {OUT}")
    save(OUT2, ROWS2)
    print(f"wrote {len(ROWS2)} records to {OUT2}")
