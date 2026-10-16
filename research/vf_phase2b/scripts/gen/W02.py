"""W02 generator (stage 1 + stage 2): bucket cleanup_facts.

Slices: corrections_vs_alternatives (~28), facts_numbers_negation (~17).
Task mostly cleanup; ~10 rewrite (message / email / prose / bullets) so corrections and
alternatives are also learned under rewrite.
Domains: university research lab, interior design studio, municipal permits office, ride-share drivers.
Names: Sneha, Aditya, Clara, Mateo, Yusuf, Ji-woo, Parth, Odile (plus generic ones).
Re-running reproduces research/vf_phase2b/data/batches/W02_s1.jsonl exactly.

Stage 2 (ids TC-W02-101..225) is defined in W02_s2_data.py (imported below) and saved to
research/vf_phase2b/data/batches/W02_s2.jsonl. Stage-2 domains add concert tickets, used-car
purchase, co-working space and a tuition centre; names add Ravina, Theo, Bongani, Mirela.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W02"
STAGE = "s1"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_{STAGE}.jsonl"))
BUCKET = "cleanup_facts"

CA = "corrections_vs_alternatives"
FN = "facts_numbers_negation"

ROWS = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def R(slice_, request, target, assertions, note, pos=None, cx=None, waivers=None):
    i = len(ROWS) + 1
    req = dict(request)
    if pos is None:
        pos = "structured" if "instruction" not in req else "after"
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient", "locale")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, assertions, f"w02-sc-{i:03d}",
                    author=WID, note=note, meta=meta, waivers=waivers))


# ---------------------------------------------------------------- corrections_vs_alternatives

# 1 name correction, short
R(CA, {"task": "cleanup",
       "transcript": "um reserve the fume hood for sneha no wait for aditya on thursday morning"},
  "Reserve the fume hood for Aditya on Thursday morning.",
  {"must_include": ["Aditya", "fume hood", "Thursday morning"], "must_not_include": ["Sneha"]},
  "facts: self-correction applied: fume hood for Aditya (Sneha corrected away); Thursday morning")

# 2 number correction "sorry", short
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "okay so for tomorrow's protein prep uh thaw the cell pellets on ice first then add the lysis buffer about ten mls per pellet the centrifuge run takes forty minutes sorry forty five minutes so start it before lunch and um don't leave the rotor in afterwards because the facility guys complained last time if the supernatant looks cloudy just spin it again and message me"},
  "For tomorrow's protein prep, thaw the cell pellets on ice first, then add the lysis buffer, about 10 mL per pellet. The centrifuge run takes 45 minutes, so start it before lunch, and don't leave the rotor in afterwards because the facility guys complained last time. If the supernatant looks cloudy, just spin it again and message me.",
  {"numbers": ["10", "45"], "must_not_include": ["40"], "must_include": ["cell pellets on ice", "lysis buffer", "about 10", "before lunch", "rotor", "If the supernatant looks cloudy"], "min_negations": 1},
  "facts: about 10 mL lysis buffer per pellet; 'sorry' is a correction here: centrifuge 45 minutes (40 corrected away); start before lunch; DON'T leave the rotor in; conditional: if cloudy, spin again and message")

# 3 genuine alternative, rewrite message
R(CA, {"task": "rewrite", "format": "message", "context": "work",
       "transcript": "uh tell clara we can install the pendant lights tuesday or thursday whichever suits her"},
  "Clara, we can install the pendant lights Tuesday or Thursday, whichever suits you.",
  {"format": "message", "must_include": ["Clara", "pendant lights", "Tuesday", "Thursday", " or "]},
  "facts: genuine alternative, BOTH Tuesday and Thursday kept; Clara chooses; no greeting/sign-off added")

# 4 "sorry" as apology (NOT a correction), short
R(CA, {"task": "cleanup",
       "transcript": "sorry clara the fabric samples um haven't arrived yet"},
  "Sorry, Clara, the fabric samples haven't arrived yet.",
  {"must_include": ["Sorry", "Clara", "fabric samples"], "min_negations": 1},
  "facts: 'sorry' is an apology, NOT a correction, so it stays; samples have NOT arrived yet")

# 5 "or rather" correction, short
R(CA, {"task": "cleanup",
       "transcript": "the site inspection is at eleven or rather at noon on the fourteenth so make sure the trench is uncovered and the inspector can get in through the side gate"},
  "The site inspection is at noon on the 14th, so make sure the trench is uncovered and the inspector can get in through the side gate.",
  {"numbers": ["14"], "must_not_include": ["11", "eleven"], "must_include": ["noon", "trench is uncovered", "side gate"]},
  "facts: 'or rather' is a correction: inspection at noon (11 corrected away); on the 14th; trench uncovered; access via side gate")

# 6 "scratch that" with a time phrase, medium
R(CA, {"task": "cleanup",
       "transcript": "heads up for all drivers the airport pickup surcharge is waived today scratch that it's waived until sunday night so don't add it to any fares this week"},
  "Heads up for all drivers: the airport pickup surcharge is waived until Sunday night, so don't add it to any fares this week.",
  {"must_include": ["airport pickup surcharge", "waived until Sunday night", "this week"], "must_not_include": ["today"], "min_negations": 1},
  "facts: 'scratch that' correction applied: waived until Sunday night ('today' corrected away); don't add it to fares this week")

# 7 "no not Tuesday, Wednesday", medium, full header
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "your appeal hearing at the permits office is on tuesday no not tuesday wednesday the fourteenth at ten in room b"},
  "Your appeal hearing at the permits office is on Wednesday the 14th at 10 in Room B.",
  {"numbers": ["14", "10"], "must_include": ["Wednesday", "Room B", "appeal hearing"], "must_not_include": ["Tuesday"]},
  "facts: 'no not Tuesday, Wednesday' is a self-correction: hearing Wednesday the 14th at 10, Room B; Tuesday removed; checker waiver: checker reads the correcting 'no not Tuesday' as negations; both are correction words, not content negations",
  waivers=['negation_lost'])

# 8 "actually make that" quantity, short
R(CA, {"task": "cleanup",
       "transcript": "order four rolls of the linen wallpaper actually make that six"},
  "Order six rolls of the linen wallpaper.",
  {"must_include": ["six rolls", "linen wallpaper"], "must_not_include": ["four"]},
  "facts: 'actually make that' correction: six rolls (four corrected away); checker waiver: checker does not parse 'actually make that' as a correction; four is correctly dropped, six kept",
  waivers=['number_missing', 'correction_reverted'])

# 9 genuine price alternative, en-in rupees
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "the resident parking permit costs nine hundred ninety nine rupees a month or nine thousand nine hundred ninety nine rupees a year"},
  "The resident parking permit costs ₹999 a month or ₹9,999 a year.",
  {"numbers": ["999", "9,999"], "numbers_one_of": [["9,999", "9999"]], "must_include": ["a month", "a year", " or "]},
  "facts: genuine alternative, BOTH kept: ₹999 a month OR ₹9,999 a year (rupees spoken)")

# 10 alternative with uncertainty, short-medium
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "we need like fifteen or fifty sample tubes i'm honestly not sure which ask yusuf before you order"},
  "We need 15 or 50 sample tubes, I'm honestly not sure which. Ask Yusuf before you order.",
  {"numbers": ["15", "50"], "must_include": ["Yusuf", "honestly", "before you order", " or "], "min_negations": 1},
  "facts: genuine alternative, BOTH 15 and 50 kept (not a correction); speaker NOT sure which; ask Yusuf before ordering")

# 11 recipient correction under rewrite message, with instruction
R(CA, {"task": "rewrite", "format": "message", "context": "work",
       "instruction": "keep it short and direct, only the payout details",
       "transcript": "uh let mateo know sorry i mean ji-woo that her weekly payout went through on friday it's four thousand two hundred and the bonus for the late night trips comes separately next week"},
  "Ji-woo, your weekly payout went through on Friday. It's 4,200, and the bonus for the late-night trips comes separately next week.",
  {"format": "message", "numbers": ["4,200"], "numbers_one_of": [["4,200", "4200"]],
   "must_include": ["Ji-woo", "Friday", "bonus", "next week"], "must_not_include": ["Mateo"]},
  "facts: recipient correction 'sorry I mean' applied: message is for Ji-woo (Mateo removed); payout 4,200 on Friday (no currency spoken); bonus comes separately next week",
  pos="before")

# 12 long walkthrough notes with several corrections and an alternative
R(CA, {"task": "cleanup",
       "transcript": "okay notes from the walkthrough with clara um the sofa goes on the east wall no wait the west wall facing the window the rug is eight by ten sorry nine by twelve and she wants it to sit under the front legs of the sofa uh for lighting she's fine with either the brass floor lamp or the black arc lamp so we'll show her both and she definitely doesn't want anything glass on the coffee table because of the kids"},
  "Notes from the walkthrough with Clara: the sofa goes on the west wall, facing the window. The rug is 9 by 12, and she wants it to sit under the front legs of the sofa. For lighting, she's fine with either the brass floor lamp or the black arc lamp, so we'll show her both, and she definitely doesn't want anything glass on the coffee table because of the kids.",
  {"numbers": ["9", "12"], "must_not_include": ["east", "8", "10"],
   "must_include": ["Clara", "west wall", "brass floor lamp", "black arc lamp", "show her both", "definitely", "glass"], "min_negations": 1},
  "facts: west wall (east corrected away); rug 9 by 12 (8 by 10 corrected away); lamp is a genuine alternative, BOTH brass floor lamp and black arc lamp kept; NO glass on the coffee table; checker waiver: checker only partly parses the 'eight by ten sorry nine by twelve' correction; 8 by 10 is correctly dropped",
  waivers=['number_missing'])

# 13 place correction, en-gb
R(CA, {"task": "cleanup", "locale": "en-gb",
       "transcript": "pick her up at gate three of the convention centre i mean gate five the north side"},
  "Pick her up at Gate 5 of the convention centre, the north side.",
  {"numbers": ["5"], "must_not_include": ["3"], "must_include": ["Gate 5", "convention centre", "north side"]},
  "facts: 'I mean' is a correction here: Gate 5 (Gate 3 corrected away); north side; checker waiver: checker treats 'I mean' as filler; here it corrects Gate 3 to Gate 5, so 3 is correctly dropped",
  waivers=['number_missing'])

# 14 non-correcting "I mean" filler (look-alike)
R(CA, {"task": "cleanup",
       "transcript": "i mean the samples looked fine but i'd rerun the assay just to be sure"},
  "The samples looked fine, but I'd rerun the assay just to be sure.",
  {"must_include": ["samples looked fine", "rerun the assay", "just to be sure"]},
  "facts: leading 'I mean' is a non-correcting filler (nothing is replaced), so it is removed; nothing else changes")

# 15 "actually" carrying contrast, not a correction
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "so i thought we'd be waiting weeks but actually the deck permit got approved yesterday"},
  "I thought we'd be waiting weeks, but actually the deck permit got approved yesterday.",
  {"must_include": ["actually", "deck permit", "approved yesterday", "waiting weeks"]},
  "facts: 'actually' carries contrast, it is NOT a self-correction, so it stays; permit approved yesterday")

# 16 long lab meeting with correction + negation contrast
R(CA, {"task": "cleanup",
       "transcript": "okay so for the lab meeting on friday uh sneha is presenting first then aditya no wait parth goes second because aditya's out um the room is three oh four not three oh two and we'll start at two thirty sorry two fifteen please bring your um your updated plots and if the projector's still broken we'll just share screens on zoom"},
  "For the lab meeting on Friday, Sneha is presenting first, then Parth goes second because Aditya's out. The room is 304, not 302, and we'll start at 2:15. Please bring your updated plots, and if the projector's still broken, we'll just share screens on Zoom.",
  {"numbers": ["304", "302", "2:15"], "must_not_include": ["2:30"],
   "must_include": ["Friday", "Sneha", "Parth goes second", "Aditya's out", "updated plots", "Zoom"], "min_negations": 1},
  "facts: Parth second (Aditya corrected away as presenter but still mentioned as out); room 304 'not 302' is a stated negation, kept; start 2:15 (2:30 corrected away); conditional Zoom fallback if projector broken; checker waiver: checker reads 'three oh four'/'three oh two' as separate digits 3, 0, 4; they are room numbers 304 and 302",
  waivers=['number_missing', 'number_invented'])

# 17 long rewrite email, en-in, correction + alternative + negation
R(CA, {"task": "rewrite", "format": "email", "locale": "en-in", "sender": "Odile", "recipient": "Mr. Okafor",
       "instruction": "keep both install dates and don't promise anything we haven't confirmed",
       "transcript": "hi um so tell mr okafor that the quote for the living room is one point two lakh no sorry one point four lakh rupees including the curtains but not the rug and uh the install could be the twentieth or the twenty second depending on when the sofa ships we can't confirm until the supplier gets back to us"},
  "Hi Mr. Okafor,\n\nThe quote for the living room is ₹1.4 lakh, including the curtains but not the rug. The installation could be on the 20th or the 22nd, depending on when the sofa ships. We can't confirm until the supplier gets back to us.\n\nBest,\nOdile",
  {"format": "email", "numbers": ["1.4", "20", "22"], "must_not_include": ["1.2"],
   "must_include": ["Mr. Okafor", "curtains", "rug", "sofa ships", "supplier", "Odile"], "min_negations": 2},
  "facts: quote ₹1.4 lakh (1.2 corrected away by 'no sorry'); includes curtains, NOT the rug; install 20th OR 22nd (both kept), conditional on sofa shipping; can't confirm until supplier replies; no promise added")

# 18 "or rather" correction vs alternative in same domain
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "hey it's mateo from driver support just so you know we pay out every monday or rather every tuesday now because the bank changed its cutoff um so if you cash out before midnight on monday it lands tuesday afternoon and instant cash out still costs fifteen rupees per transfer that hasn't changed and uh if a payout doesn't show up by wednesday raise a ticket in the app don't call the hotline"},
  "Hey, it's Mateo from driver support. Just so you know, we pay out every Tuesday now because the bank changed its cutoff, so if you cash out before midnight on Monday, it lands Tuesday afternoon. Instant cash-out still costs ₹15 per transfer; that hasn't changed. If a payout doesn't show up by Wednesday, raise a ticket in the app. Don't call the hotline.",
  {"numbers": ["15"], "must_include": ["Mateo", "every Tuesday now", "before midnight on Monday", "Tuesday afternoon", "₹15", "raise a ticket"], "must_not_include": ["every Monday"], "min_negations": 3},
  "facts: 'or rather' is a correction: payout every Tuesday ('every Monday' corrected away; the later 'midnight on Monday' cutoff is a separate fact and stays); instant cash-out ₹15 per transfer, unchanged; if no payout by Wednesday raise an app ticket; DON'T call the hotline")

# 19 hedge + genuine alternative
R(CA, {"task": "cleanup",
       "transcript": "update on the hendricks flat uh the second coat of paint will probably be dry by wednesday or thursday so the furniture delivery should wait till friday at the earliest the electrician came today and moved the switch plate but he couldn't fix the dimmer in the hallway he needs a part um odile wants us to photograph the kitchen before the shelving goes up and nobody should touch the floor in the lounge it's still curing"},
  "Update on the Hendricks flat: the second coat of paint will probably be dry by Wednesday or Thursday, so the furniture delivery should wait till Friday at the earliest. The electrician came today and moved the switch plate, but he couldn't fix the dimmer in the hallway; he needs a part. Odile wants us to photograph the kitchen before the shelving goes up, and nobody should touch the floor in the lounge. It's still curing.",
  {"must_include": ["probably", "Wednesday or Thursday", "Friday at the earliest", "couldn't fix the dimmer", "Odile", "before the shelving goes up", "still curing"], "min_negations": 2},
  "facts: hedge 'probably' kept; genuine alternative Wednesday OR Thursday, both kept; furniture delivery Friday at the earliest; dimmer NOT fixed (needs a part); Odile wants kitchen photographed before shelving; NOBODY touches the lounge floor")

# 20 measurement correction, en-gb
R(CA, {"task": "cleanup", "locale": "en-gb",
       "transcript": "uh the ceiling height in the study is two point eight metres sorry two point six"},
  "The ceiling height in the study is 2.6 metres.",
  {"numbers": ["2.6"], "must_not_include": ["2.8"], "must_include": ["ceiling height", "study", "metres"]},
  "facts: 2.6 metres (2.8 corrected away by 'sorry'); checker waiver: checker mis-parses 'two point eight ... sorry two point six'; 2.8 is correctly dropped, 2.6 kept",
  waivers=['number_missing'])

# 21 name-spelling correction under formal rewrite email
R(CA, {"task": "rewrite", "format": "email", "register": "formal", "header_style": "full",
       "transcript": "let the applicant ms clara reyes no it's reyna r e y n a know that her signage permit needs one more document which is the site plan"},
  "Dear Ms. Reyna,\n\nYour signage permit needs one more document: the site plan.",
  {"format": "email", "must_include": ["Ms. Reyna", "signage permit", "one more document", "site plan"], "must_not_include": ["Reyes"]},
  "facts: surname corrected to Reyna (spelled R-E-Y-N-A; Reyes removed); one more document needed: the site plan; no sign-off (no sender), no added offers; checker waiver: the 'no' in 'no it's Reyna' is a correction word, not a content negation",
  waivers=['negation_lost'])

# 22 "no" as an answer, not a correction (look-alike)
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "no we don't need a second quote the first one's fine"},
  "No, we don't need a second quote. The first one's fine.",
  {"must_include": ["No,", "second quote", "first one's fine"], "min_negations": 2},
  "facts: 'no' is an answer, NOT a correction; we don't need a second quote; first one is fine")

# 23 alternative times with condition
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "the airport waiting zone opens at four or four thirty depending on the first flight"},
  "The airport waiting zone opens at 4 or 4:30, depending on the first flight.",
  {"numbers": ["4", "4:30"], "must_include": ["depending on the first flight", " or "]},
  "facts: genuine alternative 4 OR 4:30, both kept; condition 'depending on the first flight' kept")

# 24 correction followed by alternative
R(CA, {"task": "cleanup",
       "transcript": "so we can meet clara at the studio on monday sorry on tuesday or wednesday afternoon um bring the tile boards and the two lighting options she hasn't seen yet"},
  "We can meet Clara at the studio on Tuesday or Wednesday afternoon. Bring the tile boards and the two lighting options she hasn't seen yet.",
  {"must_include": ["Clara", "Tuesday", "Wednesday afternoon", " or ", "tile boards", "two lighting options"], "must_not_include": ["Monday"], "min_negations": 1},
  "facts: Monday corrected away by 'sorry'; then genuine alternative Tuesday OR Wednesday afternoon, both kept; bring tile boards and the two lighting options she has NOT seen")

# 25 time correction under rewrite message
R(CA, {"task": "rewrite", "format": "message", "header_style": "full",
       "transcript": "tell yusuf his car inspection is at the depot at eight no wait ten tomorrow and he has to bring the registration papers"},
  "Yusuf, your car inspection is at the depot at 10 tomorrow, and you have to bring the registration papers.",
  {"format": "message", "numbers": ["10"], "must_not_include": ["8"], "must_include": ["Yusuf", "depot", "tomorrow", "registration papers"]},
  "facts: inspection at 10 tomorrow (8 corrected away by 'no wait'); at the depot; must bring registration papers")

# 26 long voicemail: alternative + correction + negation + condition, currency spoken
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "hi this is parth from the permits counter um just calling about your fence application you can either pay the four hundred fifty sorry four hundred eighty dollar fee online or come in person the fee went up this month uh if you come in we're open eight to four thirty monday through friday but not on the holiday next monday and you'll need a copy of your property survey otherwise we can't process it"},
  "Hi, this is Parth from the permits counter. Just calling about your fence application. You can either pay the $480 fee online or come in person. The fee went up this month. If you come in, we're open 8 to 4:30, Monday through Friday, but not on the holiday next Monday, and you'll need a copy of your property survey. Otherwise, we can't process it.",
  {"numbers": ["480", "8", "4:30"], "must_not_include": ["450"],
   "must_include": ["Parth", "fence application", "online or come in person", "holiday next Monday", "property survey"], "min_negations": 2},
  "facts: fee $480 (450 corrected away by 'sorry'); genuine alternative pay online OR in person; open 8-4:30 Mon-Fri, NOT on next Monday's holiday; property survey required or they can't process it")

# 27 item correction with scratch that
R(CA, {"task": "cleanup",
       "transcript": "for the kitchen order the brass handles scratch that the matte black ones"},
  "For the kitchen, order the matte black handles.",
  {"must_include": ["matte black handles", "kitchen"], "must_not_include": ["brass"]},
  "facts: 'scratch that' correction: matte black handles (brass corrected away); checker waiver: 'handles' is the noun that the corrected 'the matte black ones' refers to, so it legitimately stays",
  waivers=['correction_reverted'])

# 28 rewrite to bullets with correction + alternative
R(CA, {"task": "rewrite", "format": "bullets",
       "instruction": "make it a supplier order list, keep both ethanol amounts",
       "transcript": "so for the order we need nitrile gloves size medium no wait large two boxes of pipette tips um the two hundred microlitre ones and ethanol five litres or ten if they have the bulk price"},
  "- Nitrile gloves, size large\n- Two boxes of 200-microlitre pipette tips\n- Ethanol, 5 litres, or 10 if they have the bulk price",
  {"format": "bullets", "numbers": ["200", "5", "10"], "must_not_include": ["medium"],
   "must_include": ["Nitrile gloves", "large", "pipette tips", "Ethanol", "bulk price"]},
  "facts: gloves size large (medium corrected away); two boxes of 200-microlitre tips; ethanol 5 litres OR 10 conditional on bulk price, both kept",
  pos="after")

# 29 apology "sorry" + correcting "no" in one sentence
R(CA, {"task": "cleanup",
       "transcript": "sorry for the delay mateo i was on a trip the toll receipt was for seventy no seventeen dollars and the parking was nine dollars so the total should be twenty six dollars um i've attached a photo of both and if finance needs the originals i can drop them at the hub on friday"},
  "Sorry for the delay, Mateo, I was on a trip. The toll receipt was for $17, and the parking was $9, so the total should be $26. I've attached a photo of both, and if finance needs the originals, I can drop them at the hub on Friday.",
  {"numbers": ["17", "9", "26"], "must_not_include": ["70"], "must_include": ["Sorry for the delay", "Mateo", "toll receipt", "if finance needs the originals", "Friday"]},
  "facts: 'sorry for the delay' is an apology and stays; 'seventy no seventeen' is a correction: toll $17 (70 removed); parking $9; total $26; conditional offer to drop originals at the hub on Friday (speaker's own words)")

# ---------------------------------------------------------------- facts_numbers_negation

# 30 negation, short
R(FN, {"task": "cleanup",
       "transcript": "reminder for everyone uh the minus eighty freezer must not be opened during the defrost cycle which runs from six to eight tonight so pull anything you need before then"},
  "Reminder for everyone: the -80 freezer must not be opened during the defrost cycle, which runs from 6 to 8 tonight, so pull anything you need before then.",
  {"numbers": ["80", "6", "8"], "must_include": ["-80 freezer", "defrost cycle", "tonight", "before then"], "min_negations": 1},
  "facts: minus eighty freezer -> -80; must NOT be opened during defrost, 6 to 8 tonight; pull samples before then")

# 31 hedge kept
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "uh i think the grant report is due on the thirtieth but don't quote me on that"},
  "I think the grant report is due on the 30th, but don't quote me on that.",
  {"numbers": ["30"], "must_include": ["I think", "grant report", "don't quote me"], "min_negations": 1},
  "facts: hedge 'I think' kept (not turned into certainty); due on the 30th; 'don't quote me' kept")

# 32 conditional
R(FN, {"task": "cleanup",
       "transcript": "just to be clear the building permit expires after a hundred and eighty days if work hasn't started but you can request one extension in writing before it lapses"},
  "Just to be clear, the building permit expires after 180 days if work hasn't started, but you can request one extension in writing before it lapses.",
  {"numbers": ["180"], "must_include": ["building permit", "if work hasn't started", "one extension in writing", "before it lapses"], "min_negations": 1},
  "facts: conditional: expires after 180 days only if work hasn't started; one written extension may be requested before it lapses")

# 33 en-in lakh with negation
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "the renovation budget is three lakh fifty thousand rupees not four lakh please update the sheet"},
  "The renovation budget is ₹3,50,000, not ₹4,00,000. Please update the sheet.",
  {"numbers_one_of": [["3,50,000", "3.5 lakh"], ["4,00,000", "4 lakh"]], "must_include": ["renovation budget", "update the sheet"], "min_negations": 1},
  "facts: budget ₹3,50,000; 'not ₹4 lakh' is a stated negation (both values appear); please update the sheet")

# 34 negation + measurement, short
R(FN, {"task": "cleanup",
       "transcript": "quick reminder from ops surge pricing doesn't apply on rides under three kilometres and uh it's capped at one point five times on weekdays so short trips will look normal even when it's busy"},
  "Quick reminder from ops: surge pricing doesn't apply on rides under 3 kilometres, and it's capped at 1.5 times on weekdays, so short trips will look normal even when it's busy.",
  {"numbers": ["3", "1.5"], "must_include": ["surge pricing", "kilometres", "capped", "weekdays"], "min_negations": 1},
  "facts: surge does NOT apply under 3 kilometres; capped at 1.5 times on weekdays")

# 35 rewrite message, conditional + restriction
R(FN, {"task": "rewrite", "format": "message", "context": "work",
       "transcript": "um tell aditya he can use the confocal microscope on saturday only if he's done the safety training and he shouldn't book it for more than two hours"},
  "Aditya, you can use the confocal microscope on Saturday only if you've done the safety training, and you shouldn't book it for more than 2 hours.",
  {"format": "message", "numbers": ["2"], "must_include": ["Aditya", "confocal microscope", "Saturday", "only if", "safety training"], "min_negations": 1},
  "facts: condition 'only if' safety training done kept; Saturday; restriction NOT more than 2 hours")

# 36 long driver week log, many numbers + negation
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "so this week i did um sixty two trips and was online for about forty one hours earnings were eighteen thousand four hundred rupees before the commission which is twenty percent and fuel was around three thousand two hundred uh i didn't do any airport runs because the queue was like two hours long and i'm not doing the night shift next week because of my exams"},
  "This week I did 62 trips and was online for about 41 hours. Earnings were ₹18,400 before the commission, which is 20%, and fuel was around 3,200. I didn't do any airport runs because the queue was like 2 hours long, and I'm not doing the night shift next week because of my exams.",
  {"numbers": ["62", "41", "18,400", "20", "3,200", "2"], "numbers_one_of": [["20%", "20 percent"]],
   "must_include": ["about 41 hours", "commission", "around 3,200", "airport runs", "night shift", "exams"], "min_negations": 2},
  "facts: 62 trips; about 41 hours; ₹18,400 before 20% commission (rupees spoken once); fuel around 3,200; NO airport runs (2-hour queue); NOT doing night shift next week due to exams")

# 37 formal rewrite email with negations, sender
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Yusuf",
       "instruction": "formal but plain, no extra offers or apologies",
       "transcript": "let the contractor know the electrical permit wasn't approved because the load calculation is missing they don't need to resubmit the whole application just the calculation and there's no additional fee"},
  "Hello,\n\nThe electrical permit was not approved because the load calculation is missing. You do not need to resubmit the whole application, only the calculation, and there is no additional fee.\n\nRegards,\nYusuf",
  {"format": "email", "must_include": ["electrical permit", "load calculation", "whole application", "additional fee", "Yusuf"], "min_negations": 3},
  "facts: permit NOT approved; reason: missing load calculation; do NOT resubmit whole application, only the calculation; NO additional fee; no added apology/offer",
  pos="before")

# 38 hedge + alternative + negation
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the client might want the accent wall in sage or maybe terracotta she hasn't decided yet"},
  "The client might want the accent wall in sage or maybe terracotta. She hasn't decided yet.",
  {"must_include": ["might", "sage", "maybe terracotta", "hasn't decided"], "min_negations": 1},
  "facts: hedges 'might' and 'maybe' kept; sage OR terracotta both kept; client has NOT decided")

# 39 times + closure negation
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the permit counter closes at three thirty on fridays and it's closed all day on the second saturday of each month"},
  "The permit counter closes at 3:30 on Fridays, and it's closed all day on the second Saturday of each month.",
  {"numbers": ["3:30"], "must_include": ["Fridays", "closed all day", "second Saturday"]},
  "facts: closes 3:30 on Fridays; closed all day on the second Saturday monthly")

# 40 numbers, short lab
R(FN, {"task": "cleanup",
       "transcript": "okay protocol notes for the new students um after you collect the lysate spin it at twelve thousand rpm for ten minutes at four degrees then move the supernatant to a fresh tube don't disturb the pellet uh label every tube with your initials and the date if the balance isn't calibrated ask ji-woo before using it and never leave samples on the bench overnight"},
  "Protocol notes for the new students: after you collect the lysate, spin it at 12,000 rpm for 10 minutes at 4 degrees, then move the supernatant to a fresh tube. Don't disturb the pellet. Label every tube with your initials and the date. If the balance isn't calibrated, ask Ji-woo before using it, and never leave samples on the bench overnight.",
  {"numbers": ["12,000", "10", "4"], "numbers_one_of": [["12,000", "12000"]], "must_include": ["lysate", "rpm", "degrees", "fresh tube", "Ji-woo", "overnight"], "min_negations": 3},
  "facts: 12,000 rpm, 10 minutes, 4 degrees (measurements as digits); DON'T disturb pellet; label tubes with initials and date; conditional: if balance not calibrated ask Ji-woo; NEVER leave samples out overnight")

# 41 rewrite shorter, keep measurements and negations
R(FN, {"task": "rewrite", "length": "shorter",
       "instruction": "tighten this up but keep every measurement and both don'ts",
       "transcript": "so for the bedroom um the window is one hundred forty centimetres wide and the blinds should be a bit wider like one fifty and uh don't order the blackout ones she said no blackout and the rod goes ten centimetres above the frame don't put it on the frame itself"},
  "The bedroom window is 140 centimetres wide; the blinds should be a bit wider, about 150. Don't order blackout blinds, she said no blackout. The rod goes 10 centimetres above the frame, not on the frame itself.",
  {"numbers": ["140", "150", "10"], "must_include": ["bedroom window", "blackout", "above the frame"], "min_negations": 3},
  "facts: window 140 cm; blinds about 150 ('like' = about); do NOT order blackout (client said no blackout); rod 10 cm above frame, NOT on the frame",
  pos="after")

# 42 commitment vs refusal, medium
R(FN, {"task": "cleanup",
       "transcript": "okay so the platform will refund your cancellation fee but it won't cover the toll you paid so keep the receipt in case you want to claim it on your taxes"},
  "The platform will refund your cancellation fee, but it won't cover the toll you paid, so keep the receipt in case you want to claim it on your taxes.",
  {"must_include": ["will refund", "cancellation fee", "toll", "keep the receipt", "in case"], "min_negations": 1},
  "facts: cancellation fee WILL be refunded; toll will NOT be covered; keep receipt in case of a tax claim (conditional)")

# 43 long lab update with hedges, condition, negations
R(FN, {"task": "cleanup",
       "transcript": "quick update on the soil study uh we collected forty eight samples from the north plots but none from the south because the access road was flooded um the nitrogen readings look higher than last year maybe fifteen percent higher but we haven't run the controls yet so i wouldn't share that number with anyone outside the lab if the weather holds we'll go back for the south plots on the nineteenth and sneha will take the second vehicle"},
  "Quick update on the soil study: we collected 48 samples from the north plots but none from the south because the access road was flooded. The nitrogen readings look higher than last year, maybe 15% higher, but we haven't run the controls yet, so I wouldn't share that number with anyone outside the lab. If the weather holds, we'll go back for the south plots on the 19th, and Sneha will take the second vehicle.",
  {"numbers": ["48", "15", "19"], "numbers_one_of": [["15%", "15 percent"]],
   "must_include": ["north plots", "none from the south", "maybe 15", "haven't run the controls", "outside the lab", "If the weather holds", "Sneha"], "min_negations": 3},
  "facts: 48 samples north, NONE south (flooded road); nitrogen maybe 15% higher (hedge); controls NOT run; don't share outside lab; conditional return on the 19th if weather holds; Sneha takes second vehicle")

# 44 rewrite message casual, negations on date and place
R(FN, {"task": "rewrite", "format": "message", "register": "casual",
       "transcript": "tell sneha the drivers meetup isn't this saturday it's next saturday the twenty fifth and it's at the depot not the park"},
  "Sneha, the drivers' meetup isn't this Saturday, it's next Saturday, the 25th, and it's at the depot, not the park.",
  {"format": "message", "numbers": ["25"], "must_include": ["Sneha", "next Saturday", "depot", "park"], "min_negations": 2},
  "facts: meetup NOT this Saturday, next Saturday the 25th; at the depot, NOT the park")

# 45 long permits briefing, unconditional vs conditional, rewrite to prose
R(FN, {"task": "rewrite", "format": "prose", "context": "work", "header_style": "full",
       "instruction": "clean prose for the team channel, keep which rules are conditional and which aren't",
       "transcript": "okay team so starting monday every sidewalk seating application sorry every outdoor seating application needs a site sketch no exceptions um the fee waiver for seniors is not automatic it only applies if they submit the form before june thirtieth and uh clara is handling the walk-ins on wednesdays while odile covers the phones but only until the new hire starts which might be mid july"},
  "Starting Monday, every outdoor seating application needs a site sketch, with no exceptions. The fee waiver for seniors is not automatic; it only applies if they submit the form before June 30. Clara is handling the walk-ins on Wednesdays, while Odile covers the phones, but only until the new hire starts, which might be mid-July.",
  {"numbers": ["30"], "must_include": ["Monday", "outdoor seating application", "site sketch", "no exceptions", "not automatic", "only applies if", "June 30", "Clara", "Odile", "might be mid-July"], "must_not_include": ["sidewalk"],
   "min_negations": 2},
  "facts: from Monday a site sketch is required for every outdoor seating application (unconditional, no exceptions; 'sidewalk' corrected to 'outdoor' by 'sorry'); senior fee waiver NOT automatic, only if form submitted before June 30; Clara walk-ins Wednesdays; Odile phones only until the new hire starts, which MIGHT be mid-July (hedge)",
  pos="before")

if __name__ == "__main__":
    save(OUT, ROWS)
    print(f"wrote {len(ROWS)} -> {OUT}")
    sys.path.insert(0, HERE)
    import W02_s2_data  # noqa: E402
    OUT2 = OUT.replace("_s1.jsonl", "_s2.jsonl")
    save(OUT2, W02_s2_data.ROWS2)
    print(f"wrote {len(W02_s2_data.ROWS2)} -> {OUT2}")
