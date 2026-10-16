"""W02 stage 2 records (TC-W02-101..225), bucket cleanup_facts. Imported and saved by W02.py.

Slices: corrections_vs_alternatives (~80), facts_numbers_negation (~45); task cleanup mostly, ~35 rewrite.
Stage-1 review fixes applied: hedges like "like"/"about" before numbers are kept; standing rules keep
their own sentence (never merged into an "If..." sentence); instructions are followed literally; no
transcript whose correct reading is ambiguous.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec  # noqa: E402

WID = "W02"
BUCKET = "cleanup_facts"
CA = "corrections_vs_alternatives"
FN = "facts_numbers_negation"

ROWS2 = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def R(slice_, request, target, assertions, note, pos=None, cx=None, waivers=None):
    i = 100 + len(ROWS2) + 1
    req = dict(request)
    if pos is None:
        pos = "structured" if "instruction" not in req else "after"
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient", "locale")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS2.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, assertions, f"w02-sc-{i:03d}",
                     author=WID, note=note, meta=meta, waivers=waivers))


# =============================================================== chunk 1 (101-140)

# 101 name correction, concert will-call
R(CA, {"task": "cleanup",
       "transcript": "put the two floor tickets under theo no wait under ravina's name she's the one picking them up at will call"},
  "Put the two floor tickets under Ravina's name. She's the one picking them up at will call.",
  {"must_include": ["two floor tickets", "Ravina's name", "will call"], "must_not_include": ["Theo"]},
  "facts: 'no wait' correction: tickets under Ravina's name (Theo corrected away); two floor tickets; Ravina picks up at will call")

# 102 amount correction 'sorry', used car, en-gb
R(CA, {"task": "cleanup", "locale": "en-gb",
       "transcript": "the dealer's asking nine thousand five hundred sorry nine thousand two hundred for the silver corolla and that's with the new tyres"},
  "The dealer's asking 9,200 for the silver Corolla, and that's with the new tyres.",
  {"numbers_one_of": [["9,200", "9200"]], "must_include": ["silver Corolla", "new tyres"], "must_not_include": ["9,500", "9500"]},
  "facts: 'sorry' is a correction: asking price 9,200 (9,500 corrected away); no currency spoken so no symbol; price includes the new tyres")

# 103 three-way alternative, co-working
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "so for the team offsite we can book the boardroom the loft or the roof terrace um the loft's cheapest but it only seats twelve so check the headcount with mirela first"},
  "For the team offsite, we can book the boardroom, the loft or the roof terrace. The loft's cheapest, but it only seats 12, so check the headcount with Mirela first.",
  {"numbers": ["12"], "must_include": ["boardroom", "the loft or the roof terrace", "cheapest", "only seats 12", "Mirela"]},
  "facts: genuine three-way alternative, ALL kept: boardroom, loft, roof terrace; loft cheapest but ONLY seats 12; check headcount with Mirela first")

# 104 correction of a correction, rewrite message, tuition centre
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "tell bongani the trial lesson is on tuesday no wednesday actually tuesday's fine keep it tuesday at four thirty"},
  "Bongani, the trial lesson is on Tuesday at 4:30.",
  {"format": "message", "numbers": ["4:30"], "must_include": ["Bongani", "trial lesson", "Tuesday"], "must_not_include": ["Wednesday"]},
  "facts: correction of a correction: Tuesday -> Wednesday -> back to Tuesday; final: trial lesson Tuesday at 4:30; Wednesday must not appear; vocative opener because Bongani is addressed")

# 105 apology 'sorry' (not a correction), concert
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "so sorry theo the meet and greet passes are uh sold out"},
  "So sorry, Theo, the meet-and-greet passes are sold out.",
  {"must_include": ["So sorry", "Theo", "meet-and-greet passes", "sold out"]},
  "facts: 'so sorry' is an apology, NOT a correction, so it stays; passes are sold out")

# 106 range, not an alternative, tuition centre
R(CA, {"task": "cleanup",
       "transcript": "um each evening batch takes between twenty and twenty five students so if the waitlist goes past thirty we'll have to open a third batch"},
  "Each evening batch takes between 20 and 25 students, so if the waitlist goes past 30, we'll have to open a third batch.",
  {"numbers": ["20", "25", "30"], "must_include": ["between 20 and 25", "if the waitlist goes past 30", "third batch"]},
  "facts: 'between 20 and 25' is a RANGE (not an alternative, not a correction), both bounds kept; conditional: if waitlist passes 30, open a third batch")

# 107 long fee policy, negations, en-in
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "okay so for parents asking about fees the monthly fee is three thousand two hundred rupees for classes eight to ten and it doesn't include the test series which is separate uh about fifteen hundred for the term we don't give refunds after the first two weeks but you can pause for a month if there's a medical reason and please don't promise any discount on the phone ravina handles all of that"},
  "For parents asking about fees, the monthly fee is ₹3,200 for classes 8 to 10, and it doesn't include the test series, which is separate, about 1,500 for the term. We don't give refunds after the first two weeks, but you can pause for a month if there's a medical reason. Please don't promise any discount on the phone; Ravina handles all of that.",
  {"numbers": ["3,200", "8", "10", "1,500"], "numbers_one_of": [["3,200", "3200"], ["1,500", "1500"]],
   "must_include": ["classes 8 to 10", "test series", "about 1,500", "first two weeks", "if there's a medical reason", "Ravina"], "min_negations": 3},
  "facts: ₹3,200 monthly for classes 8-10 (rupees spoken for this amount only; the separate test-series figure 'about 1,500' gets no symbol, choice kept consistent); fee does NOT include test series; 'about' kept; NO refunds after first two weeks; pause a month only if medical reason; DON'T promise discounts on the phone (standing rule, own sentence); Ravina handles discounts")

# 108 'not X but Y' contrast, used car
R(CA, {"task": "cleanup",
       "transcript": "so the problem the mechanic found is not the clutch but the gearbox mount and he says it's about eight thousand to fix"},
  "The problem the mechanic found is not the clutch but the gearbox mount, and he says it's about 8,000 to fix.",
  {"numbers_one_of": [["8,000", "8000"]], "must_include": ["not the clutch but the gearbox mount", "about 8,000"], "min_negations": 1},
  "facts: 'not the clutch but the gearbox mount' is a stated contrast (NOT a self-correction): both kept; repair about 8,000 (no currency spoken, 'about' kept)")

# 109 long orientation notes, three corrections + either/or
R(CA, {"task": "cleanup",
       "transcript": "okay notes for the new members orientation um the wifi password changes every monday no wait every first monday of the month and it's posted at the front desk the meeting rooms are bookable in thirty minute slots sorry sixty minute slots through the app and you can't book more than two in a row the kitchen closes at nine i mean nine thirty on weekdays and phone calls go in the booths not at the hot desks oh and lockers are either the small ones at fifty a month or the large ones at eighty so ask mirela which is free"},
  "Notes for the new members' orientation: the Wi-Fi password changes every first Monday of the month, and it's posted at the front desk. The meeting rooms are bookable in 60-minute slots through the app, and you can't book more than two in a row. The kitchen closes at 9:30 on weekdays, and phone calls go in the booths, not at the hot desks. Oh, and lockers are either the small ones at 50 a month or the large ones at 80, so ask Mirela which is free.",
  {"numbers": ["60", "9:30", "50", "80"], "must_not_include": ["30-minute", "every Monday"],
   "must_include": ["every first Monday of the month", "front desk", "more than two in a row", "weekdays", "booths, not at the hot desks", "either the small ones", "Mirela"], "min_negations": 2},
  "facts: three corrections applied: password changes every FIRST Monday ('every Monday' corrected away); 60-minute slots (30 corrected away); kitchen closes 9:30 ('nine I mean nine thirty'); can't book more than two in a row; calls in booths NOT at hot desks; genuine either/or: small lockers at 50 a month OR large at 80, both kept (no currency spoken); ask Mirela")

# 110 negation with times, concert
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the gate opens at six but the band doesn't go on before eight forty five"},
  "The gate opens at 6, but the band doesn't go on before 8:45.",
  {"numbers": ["6", "8:45"], "must_include": ["gate opens", "band"], "min_negations": 1},
  "facts: gate opens at 6; band does NOT go on before 8:45")

# 111 alternative days under rewrite email, used car, en-in
R(CA, {"task": "rewrite", "format": "email", "locale": "en-in", "sender": "Aditya",
       "transcript": "hi um i saw your listing for the blue i twenty and i'd like to see it this saturday or sunday morning is the asking price of four lakh twenty thousand rupees negotiable and has it had any accidents"},
  "Hi,\n\nI saw your listing for the blue i20, and I'd like to see it this Saturday or Sunday morning. Is the asking price of ₹4,20,000 negotiable, and has it had any accidents?\n\nBest,\nAditya",
  {"format": "email", "numbers_one_of": [["4,20,000", "4.2 lakh", "420,000"]], "must_include": ["i20", "Saturday or Sunday morning", "negotiable", "accidents", "Aditya"], "must_not_include": ["Monday"]},
  "facts: genuine alternative: viewing this Saturday OR Sunday morning, both kept; asking price ₹4,20,000 (rupees spoken); two questions stay questions (negotiable? any accidents?), not answered; no recipient name -> 'Hi,'; sign-off Best + sender Aditya; no added promises")

# 112 'I mean' correcting a person, concert ushers
R(CA, {"task": "cleanup",
       "transcript": "send the seating chart to odile i mean to yusuf he's doing the ushers this time"},
  "Send the seating chart to Yusuf. He's doing the ushers this time.",
  {"must_include": ["seating chart", "Yusuf", "ushers", "this time"], "must_not_include": ["Odile"]},
  "facts: 'I mean to Yusuf' corrects the recipient: send to Yusuf (Odile corrected away); Yusuf is doing the ushers this time")

# 113 either/or with restriction, co-working
R(CA, {"task": "cleanup",
       "transcript": "members can either pay monthly or prepay for the year and get two months free but the annual plan isn't refundable"},
  "Members can either pay monthly or prepay for the year and get two months free, but the annual plan isn't refundable.",
  {"must_include": ["either pay monthly or prepay for the year", "two months free", "isn't refundable"], "min_negations": 1},
  "facts: genuine either/or kept: pay monthly OR prepay yearly (prepay gets two months free); annual plan is NOT refundable")

# 114 long lab note, standing rule in its own sentence
R(FN, {"task": "cleanup",
       "transcript": "quick note on the sequencing run uh we got about ninety two percent of reads passing filter which is lower than usual so don't merge the lanes yet um ji-woo thinks it might be the adapter dilution and if the rerun on thursday looks the same we'll call the core facility before we touch anything else and nobody should delete the raw files from the server even if it's full"},
  "Quick note on the sequencing run: we got about 92% of reads passing filter, which is lower than usual, so don't merge the lanes yet. Ji-woo thinks it might be the adapter dilution, and if the rerun on Thursday looks the same, we'll call the core facility before we touch anything else. Nobody should delete the raw files from the server, even if it's full.",
  {"numbers": ["92"], "numbers_one_of": [["92%", "92 percent"]],
   "must_include": ["about 92", "lower than usual", "don't merge the lanes yet", "Ji-woo thinks it might be", "if the rerun on Thursday looks the same", "Nobody should delete the raw files"], "min_negations": 2},
  "facts: about 92% passing filter ('about' kept), lower than usual; DON'T merge lanes yet; hedge 'Ji-woo thinks it might be' kept; conditional: only if Thursday rerun looks the same, call core facility; standing unconditional rule in its own sentence: NOBODY deletes raw files even if the server is full")

# 115 two corrections in one sentence, rewrite message casual, concert
R(CA, {"task": "rewrite", "format": "message", "register": "casual",
       "transcript": "tell mateo i got three tickets no four tickets for the saturday show sorry the friday show and they're in row k"},
  "Mateo, I got four tickets for the Friday show, and they're in row K.",
  {"format": "message", "must_include": ["Mateo", "four tickets", "Friday show", "row K"], "must_not_include": ["three", "Saturday"]},
  "facts: two corrections in one utterance: four tickets (three corrected away) and the Friday show (Saturday corrected away by 'sorry'); row K")

# 116 'make that' quantity, co-working
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "we need forty uh make that forty five chairs for the open mic night on friday"},
  "We need 45 chairs for the open mic night on Friday.",
  {"numbers": ["45"], "must_not_include": ["40"], "must_include": ["open mic night", "Friday"]},
  "facts: 'make that' correction: 45 chairs (40 corrected away); open mic night on Friday")

# 117 negation + 'until' + 'unless', used car, en-in
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "don't sign anything until the bank approves the loan and even then don't hand over the deposit unless the rc transfer papers are ready"},
  "Don't sign anything until the bank approves the loan, and even then, don't hand over the deposit unless the RC transfer papers are ready.",
  {"must_include": ["until the bank approves the loan", "even then", "unless the RC transfer papers are ready"], "min_negations": 2},
  "facts: DON'T sign until bank approves loan; even then DON'T hand over deposit unless RC transfer papers ready (condition kept)")

# 118 alternative prices, en-in rupees, tuition recital
R(CA, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "the auditorium for the annual recital costs eight thousand rupees for half a day or fourteen thousand for the full day"},
  "The auditorium for the annual recital costs ₹8,000 for half a day or ₹14,000 for the full day.",
  {"numbers_one_of": [["8,000", "8000"], ["14,000", "14000"]], "must_include": ["annual recital", "half a day", "full day", " or "]},
  "facts: genuine alternative, both kept: ₹8,000 half day OR ₹14,000 full day; ₹ applied to both amounts because rupees were spoken in the same sentence for the same price list")

# 119 'actually no' correction, concert photographer
R(CA, {"task": "cleanup",
       "transcript": "the photographer can shoot from the pit actually no only from the soundboard area"},
  "The photographer can shoot only from the soundboard area.",
  {"must_include": ["only from the soundboard area"], "must_not_include": ["pit"]},
  "facts: 'actually no' correction: photographer shoots ONLY from the soundboard area ('from the pit' corrected away)")

# 120 formal email, lease end, co-working
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Mirela", "recipient": "Mr. Haddad",
       "transcript": "let mr haddad know his company's lease on the two private offices ends on the thirty first of december and we can't extend it at the current rate the new rate would be twelve percent higher if he wants to renew he needs to tell us by november fifteenth"},
  "Dear Mr. Haddad,\n\nYour company's lease on the two private offices ends on December 31, and we cannot extend it at the current rate. The new rate would be 12% higher. If you wish to renew, you need to tell us by November 15.\n\nRegards,\nMirela",
  {"format": "email", "numbers": ["31", "12", "15"], "numbers_one_of": [["12%", "12 percent"]],
   "must_include": ["Mr. Haddad", "two private offices", "December 31", "current rate", "If you wish to renew", "November 15", "Mirela"], "min_negations": 1},
  "facts: lease on two private offices ends December 31; can NOT extend at current rate; new rate 12% higher; conditional: if he wants to renew, tell by November 15; formal -> 'Dear Mr. Haddad,' and 'Regards, Mirela'; no added offers")

# 121 correction of a correction, short, interior design
R(CA, {"task": "cleanup",
       "transcript": "for the backsplash order the green zellige no the white ones actually no green was right"},
  "For the backsplash, order the green zellige.",
  {"must_include": ["green zellige", "backsplash"], "must_not_include": ["white"]},
  "facts: correction of a correction: green -> white -> back to green ('actually no green was right'); final order: green zellige; white must not appear")

# 122 long tiler notes, correction + three-way alternative + standing rule, en-gb
R(CA, {"task": "cleanup", "locale": "en-gb",
       "transcript": "okay notes for the tiler um the backsplash is about six square metres plus ten percent for cuts the grout colour is either white grey or charcoal clara will pick on site the job's booked for the eighteenth sorry nineteenth because the counters arrive on the seventeenth and uh the old tiles have to be off the wall before he comes yusuf is doing that on the sixteenth please don't use the wet saw indoors the client's really strict about the dust"},
  "Notes for the tiler: the backsplash is about 6 square metres, plus 10% for cuts. The grout colour is either white, grey or charcoal; Clara will pick on site. The job's booked for the 19th because the counters arrive on the 17th, and the old tiles have to be off the wall before he comes. Yusuf is doing that on the 16th. Please don't use the wet saw indoors; the client's really strict about the dust.",
  {"numbers": ["6", "10", "19", "17", "16"], "numbers_one_of": [["10%", "10 percent"]], "must_not_include": ["18th"],
   "must_include": ["about 6 square metres", "either white, grey or charcoal", "Clara will pick on site", "off the wall before he comes", "Yusuf", "wet saw indoors"], "min_negations": 1},
  "facts: about 6 m² plus 10% for cuts; grout is a three-way alternative, all kept (white, grey, charcoal), Clara picks on site; job booked for the 19th (18th corrected away by 'sorry'); counters arrive on the 17th; old tiles off before he comes, Yusuf removes them on the 16th; DON'T use wet saw indoors (dust)")

# 123 range of days, concert refunds
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the refund for cancelled shows takes about seven to ten working days"},
  "The refund for cancelled shows takes about 7 to 10 working days.",
  {"numbers": ["7", "10"], "must_include": ["about 7 to 10 working days", "cancelled shows"]},
  "facts: hedge 'about' kept; range 7 to 10 working days (both bounds)")

# 124 correction + conditional alternative under bullets, co-working event
R(CA, {"task": "rewrite", "format": "bullets",
       "instruction": "turn it into a setup checklist and keep the condition about the second mic",
       "transcript": "okay for the event setup we need two projectors no wait three projectors sixty chairs a mic for the panel or two if bongani joins and the welcome banner"},
  "- Three projectors\n- 60 chairs\n- A mic for the panel, or two if Bongani joins\n- The welcome banner",
  {"format": "bullets", "numbers": ["60"], "must_include": ["Three projectors", "60 chairs", "or two if Bongani joins", "welcome banner"], "must_not_include": ["Two projectors"]},
  "facts: three projectors (two corrected away by 'no wait'); 60 chairs; one mic for the panel, or two IF Bongani joins (condition kept); welcome banner",
  pos="after")

# 125 apology sorry + correcting sorry in one utterance, used car, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "sorry i'm late with this the deposit for the car is fifteen thousand sorry twenty thousand rupees and the balance is due on delivery"},
  "Sorry I'm late with this. The deposit for the car is ₹20,000, and the balance is due on delivery.",
  {"numbers_one_of": [["20,000", "20000"]], "must_include": ["Sorry I'm late with this", "deposit", "balance is due on delivery"], "must_not_include": ["15,000", "15000"]},
  "facts: first 'sorry' is an apology and stays; second 'sorry' is a correction: deposit ₹20,000 (15,000 corrected away); balance due on delivery")

# 126 hedges + negation, concert bag policy
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "i'm pretty sure the venue allows small bags but probably not backpacks so tell people to travel light"},
  "I'm pretty sure the venue allows small bags but probably not backpacks, so tell people to travel light.",
  {"must_include": ["I'm pretty sure", "small bags", "probably not backpacks", "travel light"], "min_negations": 1},
  "facts: hedges 'pretty sure' and 'probably' kept; small bags allowed; backpacks probably NOT")

# 127 alternative dates + 'or rather' correction, tuition test
R(CA, {"task": "cleanup",
       "transcript": "the unit test is on the twelfth or the thirteenth i'll confirm tomorrow and the syllabus is chapters four to seven or rather four to six"},
  "The unit test is on the 12th or the 13th; I'll confirm tomorrow. The syllabus is chapters 4 to 6.",
  {"numbers": ["12", "13", "4", "6"], "must_not_include": ["7"], "must_include": ["12th or the 13th", "confirm tomorrow", "chapters 4 to 6"]},
  "facts: genuine alternative 12th OR 13th, both kept, speaker will confirm tomorrow; 'or rather' is a correction: chapters 4 to 6 (4 to 7 corrected away)")

# 128 rewrite message, inspection findings + condition, used car
R(FN, {"task": "rewrite", "format": "message",
       "instruction": "short and clear, keep the condition exactly",
       "transcript": "let parth know the inspection found the brake pads are worn but the engine and transmission are fine and there's no rust underneath so i still want to buy it if they knock off the cost of the pads"},
  "Parth, the inspection found the brake pads are worn, but the engine and transmission are fine, and there's no rust underneath. I still want to buy it if they knock off the cost of the pads.",
  {"format": "message", "must_include": ["Parth", "brake pads are worn", "engine and transmission are fine", "no rust", "if they knock off the cost of the pads"], "min_negations": 1},
  "facts: brake pads worn; engine and transmission fine; NO rust underneath; still wants to buy it only IF they knock off the cost of the pads (condition kept exactly)",
  pos="before")

# 129 'no no' time correction, concert doors
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "doors open at seven no no seven thirty"},
  "Doors open at 7:30.",
  {"numbers": ["7:30"], "must_include": ["Doors open"]},
  "facts: 'no no' correction: doors open at 7:30 (7 corrected away)")

# 130 'wait no' weekday correction, corrected value reappears as reason
R(CA, {"task": "cleanup",
       "transcript": "put the parents meeting on saturday wait no sunday morning at ten because the hall's taken saturday"},
  "Put the parents' meeting on Sunday morning at 10 because the hall's taken Saturday.",
  {"numbers": ["10"], "must_include": ["parents' meeting", "Sunday morning at 10", "hall's taken Saturday"]},
  "facts: 'wait no' correction: meeting on Sunday morning at 10 (Saturday corrected away as the meeting day); Saturday legitimately reappears in the reason (hall taken Saturday)")

# 131 long ops broadcast with two corrections, concert pickup for drivers
R(CA, {"task": "cleanup",
       "transcript": "hi drivers this is theo from ops um for saturday's stadium concert the pickup zone is lot c no wait lot d on the east side and it opens at ten fifteen pm the show ends around ten thirty so don't queue on the main road before then the police will ticket you um if lot d fills up use the overflow area behind the hardware store and surge is capped at two times tonight sorry tomorrow night"},
  "Hi drivers, this is Theo from ops. For Saturday's stadium concert, the pickup zone is Lot D on the east side, and it opens at 10:15 p.m. The show ends around 10:30, so don't queue on the main road before then; the police will ticket you. If Lot D fills up, use the overflow area behind the hardware store, and surge is capped at two times tomorrow night.",
  {"numbers": ["10:15", "10:30"], "must_not_include": ["Lot C", "tonight"],
   "must_include": ["Theo", "Lot D", "east side", "around 10:30", "don't queue on the main road", "If Lot D fills up", "hardware store", "two times tomorrow night"], "min_negations": 1},
  "facts: Lot D (Lot C corrected away by 'no wait'); opens 10:15 p.m.; show ends AROUND 10:30; DON'T queue on main road before then (police ticket); conditional overflow if Lot D fills; surge capped at two times tomorrow night ('tonight' corrected away by 'sorry')")

# 132 double 'no', concert venue rules
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "there's no parking on site and uh no re-entry once you leave"},
  "There's no parking on site and no re-entry once you leave.",
  {"must_include": ["no parking on site", "no re-entry once you leave"], "min_negations": 2},
  "facts: NO parking on site; NO re-entry once you leave")

# 133 alternative evenings under casual email, tuition
R(CA, {"task": "rewrite", "format": "email", "register": "casual", "sender": "Ravina", "recipient": "Mrs. Pillai",
       "transcript": "tell mrs pillai her son can join the physics batch on monday or thursday evenings both are at six and the first class is free"},
  "Hi Mrs. Pillai,\n\nYour son can join the physics batch on Monday or Thursday evenings. Both are at 6, and the first class is free.\n\nThanks,\nRavina",
  {"format": "email", "numbers": ["6"], "must_include": ["Mrs. Pillai", "Monday or Thursday evenings", "first class is free", "Ravina"]},
  "facts: genuine alternative Monday OR Thursday evenings, both kept; both at 6; first class free; casual -> 'Hi Mrs. Pillai,' and 'Thanks, Ravina'; no added offers")

# 134 numbers + negation, lab incubator
R(FN, {"task": "cleanup",
       "transcript": "set the incubator to thirty seven degrees and five percent co two and don't open the door for at least twenty four hours"},
  "Set the incubator to 37 degrees and 5% CO2, and don't open the door for at least 24 hours.",
  {"numbers": ["37", "5", "24"], "numbers_one_of": [["5%", "5 percent"]], "must_include": ["CO2", "at least 24 hours"], "min_negations": 1},
  "facts: 37 degrees; 5% CO2; DON'T open the door for at least 24 hours")

# 135 'actually' as emphasis, not a correction, concert seats
R(CA, {"task": "cleanup",
       "transcript": "honestly the seats are actually better than the ones we had last year"},
  "Honestly, the seats are actually better than the ones we had last year.",
  {"must_include": ["Honestly", "actually better", "last year"]},
  "facts: 'actually' is emphasis, NOT a correction (nothing is replaced), so it stays; 'honestly' carries meaning and stays")

# 136 stated negation of a number, tuition fees sheet
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "the morning batch has eleven students not fifteen so the fee total on the sheet is wrong redo it before friday"},
  "The morning batch has 11 students, not 15, so the fee total on the sheet is wrong. Redo it before Friday.",
  {"numbers": ["11", "15"], "must_include": ["11 students, not 15", "fee total", "before Friday"], "min_negations": 1},
  "facts: 11 students, 'not 15' is a stated negation (both numbers kept, NOT a self-correction); fee total on sheet is wrong; redo before Friday")

# 137 rewrite prose notice, co-working fire drill
R(FN, {"task": "rewrite", "format": "prose", "header_style": "full",
       "instruction": "turn this into a clear notice for the members board, keep the time and every no",
       "transcript": "um so from next week the building's doing fire drills on tuesday at eleven everyone has to leave the floor no exceptions and the lifts won't work during the drill which lasts about twenty minutes and no visitors are allowed in that morning"},
  "From next week, the building is doing fire drills on Tuesday at 11. Everyone has to leave the floor, with no exceptions, and the lifts won't work during the drill, which lasts about 20 minutes. No visitors are allowed in that morning.",
  {"format": "prose", "numbers": ["11", "20"], "must_include": ["next week", "Tuesday at 11", "no exceptions", "lifts won't work", "about 20 minutes", "No visitors"], "min_negations": 3},
  "facts: from next week fire drills on Tuesday at 11; everyone leaves the floor, NO exceptions; lifts WON'T work during the drill; drill lasts ABOUT 20 minutes; NO visitors that morning",
  pos="before")

# 138 'no wait' code correction, co-working
R(CA, {"task": "cleanup",
       "transcript": "the door code for meeting room b is four two seven one no wait four two one seven"},
  "The door code for Meeting Room B is 4217.",
  {"numbers": ["4217"], "must_not_include": ["4271"], "must_include": ["Meeting Room B"]},
  "facts: 'no wait' correction: code 4217 (4271 corrected away)")

# 139 long used-car checklist, numbers + conditions, en-in
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "so before we go see the car tomorrow um check the odometer it should say around sixty eight thousand if it's way more than that walk away the seller said the timing belt was replaced at sixty thousand so ask for the bill uh test drive for at least fifteen minutes including the highway and don't let him do the driving the price we agreed on the phone was five lakh forty thousand but i'm not paying more than five lakh twenty five thousand if the tyres need replacing"},
  "Before we go see the car tomorrow, check the odometer; it should say around 68,000. If it's way more than that, walk away. The seller said the timing belt was replaced at 60,000, so ask for the bill. Test-drive for at least 15 minutes, including the highway, and don't let him do the driving. The price we agreed on the phone was 5,40,000, but I'm not paying more than 5,25,000 if the tyres need replacing.",
  {"numbers": ["68,000", "60,000", "15", "5,40,000", "5,25,000"],
   "must_include": ["tomorrow", "around 68,000", "walk away", "timing belt", "ask for the bill", "at least 15 minutes", "highway", "if the tyres need replacing"], "min_negations": 2},
  "facts: odometer around 68,000, walk away if way more; timing belt replaced at 60,000, ask for bill; test drive at least 15 minutes incl. highway; DON'T let seller drive; agreed price 5,40,000; NOT paying more than 5,25,000 IF tyres need replacing (condition scoped to the 5,25,000 cap); no currency named, so no ₹ symbol")

# 140 three-option question under rewrite message, interior design
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "ask clara if she wants the sofa in velvet or linen or maybe the boucle she mentioned and whether the delivery can be next friday"},
  "Clara, do you want the sofa in velvet, linen, or maybe the boucle you mentioned? And can the delivery be next Friday?",
  {"format": "message", "must_include": ["Clara", "velvet", "linen", "maybe the boucle", "next Friday", "?"]},
  "facts: three-way alternative kept (velvet, linen, maybe the boucle; 'maybe' kept); second question: can delivery be next Friday; questions stay questions, nothing answered or decided")


# =============================================================== chunk 2 (141-180)

# 141 either/or + hedge + condition, research lab poster, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "for the poster session you can either print it on fabric or on regular paper um fabric's about two thousand rupees but it doesn't crease so if you're flying it's probably worth it"},
  "For the poster session, you can either print it on fabric or on regular paper. Fabric's about ₹2,000, but it doesn't crease, so if you're flying, it's probably worth it.",
  {"numbers_one_of": [["2,000", "2000"]], "must_include": ["either print it on fabric or on regular paper", "about ₹2,000", "doesn't crease", "if you're flying", "probably worth it"], "min_negations": 1},
  "facts: genuine either/or kept (fabric OR regular paper); fabric ABOUT ₹2,000; does NOT crease; conditional hedge: if flying, PROBABLY worth it")

# 142 date correction 'I mean' under rewrite message, permits office
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "let ji-woo know the zoning board moved her hearing to the ninth i mean tenth of next month and she doesn't need to bring the drawings again"},
  "Ji-woo, the zoning board moved your hearing to the 10th of next month, and you don't need to bring the drawings again.",
  {"format": "message", "numbers": ["10"], "must_not_include": ["9th"], "must_include": ["Ji-woo", "zoning board", "10th of next month", "drawings again"], "min_negations": 1},
  "facts: 'I mean' corrects the date: hearing moved to the 10th of next month (9th corrected away); she does NOT need to bring the drawings again ('again' is a fact)")

# 143 limit + restriction, concert tickets
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the ticket limit is four per account and resale above face value isn't allowed"},
  "The ticket limit is four per account, and resale above face value isn't allowed.",
  {"must_include": ["four per account", "above face value", "isn't allowed"], "min_negations": 1},
  "facts: limit four tickets per account; resale above face value NOT allowed")

# 144 long voicemail: apology 'sorry' + 'no' correction + condition + question, co-working
R(CA, {"task": "cleanup",
       "transcript": "hi this is bongani from unit twelve um sorry to bother you again but the aircon in our office has been off since monday no since tuesday morning and it's about thirty degrees in there by lunch we've got clients coming in on thursday so if it can't be fixed by wednesday evening could we move into the small boardroom for the day i'm not asking for a discount just a working room"},
  "Hi, this is Bongani from Unit 12. Sorry to bother you again, but the aircon in our office has been off since Tuesday morning, and it's about 30 degrees in there by lunch. We've got clients coming in on Thursday, so if it can't be fixed by Wednesday evening, could we move into the small boardroom for the day? I'm not asking for a discount, just a working room.",
  {"numbers": ["12", "30"], "must_not_include": ["Monday"],
   "must_include": ["Bongani", "Unit 12", "Sorry to bother you again", "since Tuesday morning", "about 30 degrees", "Thursday", "if it can't be fixed by Wednesday evening", "small boardroom", "?", "not asking for a discount"], "min_negations": 2},
  "facts: 'sorry to bother you again' is an apology and stays ('again' is a fact); 'Monday no since Tuesday morning' is a correction: off since Tuesday morning; ABOUT 30 degrees by lunch; clients Thursday; conditional request (if not fixed by Wednesday evening) stays a question; NOT asking for a discount")

# 145 alternative + negation, used car payment, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "the seller wants cash or a bank transfer not a cheque"},
  "The seller wants cash or a bank transfer, not a cheque.",
  {"must_include": ["cash or a bank transfer", "not a cheque"], "min_negations": 1},
  "facts: genuine alternative cash OR bank transfer, both kept; NOT a cheque")

# 146 neutral email, scores + negations + condition, tuition centre
R(FN, {"task": "rewrite", "format": "email", "sender": "Theo", "recipient": "Mr. Banerjee",
       "transcript": "tell mr banerjee that his daughter's mock test score was sixty two out of eighty which is up from forty nine last month she still hasn't submitted the two pending assignments and if she doesn't by friday she can't sit the next mock"},
  "Hi Mr. Banerjee,\n\nYour daughter's mock test score was 62 out of 80, which is up from 49 last month. She still hasn't submitted the two pending assignments, and if she doesn't by Friday, she can't sit the next mock.\n\nBest,\nTheo",
  {"format": "email", "numbers": ["62", "80", "49"], "must_include": ["Mr. Banerjee", "62 out of 80", "up from 49 last month", "still hasn't submitted", "two pending assignments", "by Friday", "can't sit the next mock", "Theo"], "min_negations": 3},
  "facts: score 62 out of 80, up from 49 last month; 'still' kept; has NOT submitted the two pending assignments; conditional: if not by Friday she can NOT sit the next mock; neutral -> 'Hi Mr. Banerjee,' / 'Best, Theo'; no added offers")

# 147 'scratch that' removes a whole clause, concert sound check
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "we'll do the sound check at three scratch that the band's arriving late so sound check is at four thirty and doors stay at six"},
  "The band's arriving late, so sound check is at 4:30, and doors stay at 6.",
  {"numbers": ["4:30", "6"], "must_not_include": ["3"], "must_include": ["band's arriving late", "sound check is at 4:30", "doors stay at 6"]},
  "facts: 'scratch that' retracts the whole first clause (sound check at 3); final: band arriving late, sound check 4:30, doors stay at 6")

# 148 three-way alternative + speaker's own commitment, rewrite message, used car, en-in
R(CA, {"task": "rewrite", "format": "message", "locale": "en-in",
       "transcript": "ask the seller if we can meet at his place the metro station or the petrol pump near the highway whichever's easier and tell him i'll bring the cash"},
  "Can we meet at your place, the metro station, or the petrol pump near the highway, whichever's easier? I'll bring the cash.",
  {"format": "message", "must_include": ["your place", "metro station", "petrol pump near the highway", "whichever's easier", "?", "I'll bring the cash"]},
  "facts: three-way alternative kept (his place, metro station, petrol pump near highway), seller chooses; stays a question; 'I'll bring the cash' is the speaker's own dictated commitment, kept; seller not named so no vocative")

# 149 rate change, numbers, ride-share
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "starting the first the commission drops from twenty five to twenty two percent for drivers with a four point eight rating or above"},
  "Starting the 1st, the commission drops from 25% to 22% for drivers with a 4.8 rating or above.",
  {"numbers": ["1", "25", "22", "4.8"], "must_include": ["Starting the 1st", "4.8 rating or above"]},
  "facts: from the 1st commission drops from 25% to 22%; applies only to drivers rated 4.8 or above ('or above' is a threshold, not an alternative)")

# 150 long travel plan, correction + negations, research lab
R(CA, {"task": "cleanup",
       "transcript": "okay so travel plan for the conference um we fly out on the sixth no wait the seventh in the evening and we're back on the eleventh sneha and parth are presenting posters aditya's giving the talk which is twenty minutes plus five for questions not fifteen like last year the department covers the flights and hotel but not meals so keep your receipts anyway and please don't book anything until odile sends the approved list"},
  "Travel plan for the conference: we fly out on the 7th in the evening, and we're back on the 11th. Sneha and Parth are presenting posters; Aditya's giving the talk, which is 20 minutes plus 5 for questions, not 15 like last year. The department covers the flights and hotel but not meals, so keep your receipts anyway. Please don't book anything until Odile sends the approved list.",
  {"numbers": ["7", "11", "20", "5", "15"], "must_not_include": ["6th"],
   "must_include": ["7th in the evening", "11th", "Sneha and Parth", "Aditya's giving the talk", "not 15 like last year", "but not meals", "keep your receipts anyway", "until Odile sends the approved list"], "min_negations": 3},
  "facts: fly out the 7th in the evening (6th corrected away by 'no wait'); back the 11th; Sneha and Parth posters; Aditya's talk 20 minutes + 5 for questions, NOT 15 like last year (stated contrast); department covers flights and hotel, NOT meals; keep receipts anyway; DON'T book until Odile sends the approved list")

# 151 alternative times in a question, used car test drive
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "do you want the eleven o'clock or the two o'clock test drive"},
  "Do you want the 11 o'clock or the 2 o'clock test drive?",
  {"numbers": ["11", "2"], "must_include": ["11 o'clock or the 2 o'clock", "test drive", "?"], "behavior": "not_answer"},
  "facts: question stays a question, not answered; genuine alternative 11 o'clock OR 2 o'clock, both kept")

# 152 negations + date, interior design, en-gb
R(FN, {"task": "cleanup", "locale": "en-gb",
       "transcript": "the paint's on back order so the decorator can't start before the twenty first and he won't work weekends"},
  "The paint's on back order, so the decorator can't start before the 21st, and he won't work weekends.",
  {"numbers": ["21"], "must_include": ["back order", "can't start before the 21st", "won't work weekends"], "min_negations": 2},
  "facts: paint on back order; decorator can NOT start before the 21st; he WON'T work weekends")

# 153 surname correction under formal email + offer the speaker dictated, permits office
R(CA, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Yusuf",
       "transcript": "write to the applicant mister castellanos no castellano without the s that his sign permit is approved and he can collect the certificate in person or we can post it"},
  "Dear Mr. Castellano,\n\nYour sign permit is approved, and you can collect the certificate in person, or we can post it.\n\nRegards,\nYusuf",
  {"format": "email", "must_include": ["Mr. Castellano", "sign permit is approved", "in person", "post it", "Yusuf"], "must_not_include": ["Castellanos"]},
  "facts: surname corrected to Castellano ('without the s'; Castellanos removed); permit approved; genuine alternative: collect in person OR we post it (offer dictated by speaker, kept); formal -> 'Dear Mr. Castellano,' / 'Regards, Yusuf'; checker waiver: the correcting 'no' and the spelling note 'without the s' are counted as content negations; neither is a negation of a fact",
  waivers=["negation_lost"])

# 154 correcting 'sorry' and apologising 'sorry' in one utterance, concert ticket drop
R(CA, {"task": "cleanup",
       "transcript": "the next drop is friday at noon sorry saturday at noon and it's limited to two per person sorry about the confusion"},
  "The next drop is Saturday at noon, and it's limited to two per person. Sorry about the confusion.",
  {"must_include": ["Saturday at noon", "two per person", "Sorry about the confusion"], "must_not_include": ["Friday"]},
  "facts: first 'sorry' is a correction: drop on Saturday at noon (Friday corrected away); limit two per person; second 'sorry' is an apology and stays")

# 155 short facts, used car history
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "uh the car has one previous owner and no accident history"},
  "The car has one previous owner and no accident history.",
  {"must_include": ["one previous owner", "no accident history"], "min_negations": 1},
  "facts: one previous owner; NO accident history")

# 156 alternative pricing, co-working day passes
R(CA, {"task": "cleanup",
       "transcript": "day passes are fifteen dollars each or you can buy a bundle of ten for a hundred and twenty dollars and the bundle's valid for three months"},
  "Day passes are $15 each, or you can buy a bundle of ten for $120, and the bundle's valid for three months.",
  {"numbers": ["15", "120"], "must_include": ["$15 each", "bundle of ten", "$120", "three months"]},
  "facts: genuine alternative: $15 per day pass OR a bundle of ten for $120; bundle valid three months")

# 157 place correction 'sorry' under rewrite message, research lab
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "tell sneha the reagent order went to the wrong lab sorry the wrong building it's sitting at the chemistry reception and she should pick it up before five"},
  "Sneha, the reagent order went to the wrong building. It's sitting at the chemistry reception, and you should pick it up before 5.",
  {"format": "message", "numbers": ["5"], "must_include": ["Sneha", "wrong building", "chemistry reception", "before 5"], "must_not_include": ["wrong lab"]},
  "facts: 'sorry' corrects 'wrong lab' to 'wrong building'; order at chemistry reception; Sneha should pick it up before 5")

# 158 long incentive rules, conditions + negations, ride-share, en-in
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "okay so the incentive this month works like this if you complete a hundred and twenty trips you get two thousand rupees extra and if you hit a hundred and fifty it's four thousand total not on top but the trips have to be between six am and eleven pm and cancelled trips don't count we're not running the weekend bonus anymore so please don't ask the hub about it"},
  "The incentive this month works like this: if you complete 120 trips, you get ₹2,000 extra, and if you hit 150, it's ₹4,000 total, not on top. But the trips have to be between 6 a.m. and 11 p.m., and cancelled trips don't count. We're not running the weekend bonus anymore, so please don't ask the hub about it.",
  {"numbers": ["120", "150", "6", "11"], "numbers_one_of": [["2,000", "2000"], ["4,000", "4000"]],
   "must_include": ["if you complete 120 trips", "₹2,000 extra", "if you hit 150", "₹4,000 total, not on top", "between 6 a.m. and 11 p.m.", "cancelled trips don't count", "weekend bonus", "don't ask the hub"], "min_negations": 4},
  "facts: conditional tiers: 120 trips -> ₹2,000 extra; 150 trips -> ₹4,000 TOTAL, NOT on top (₹ applied to both amounts, same rupee incentive list); trips must be between 6 a.m. and 11 p.m. (range); cancelled trips DON'T count; NOT running weekend bonus anymore; DON'T ask the hub")

# 159 'actually make that' date, tuition fee deposit
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "move the fee deposit deadline to the fifth actually make that the eighth"},
  "Move the fee deposit deadline to the 8th.",
  {"numbers": ["8"], "must_not_include": ["5th"], "must_include": ["fee deposit deadline"]},
  "facts: 'actually make that' correction: deadline the 8th (5th corrected away)")

# 160 neither/nor + either/or, co-working rooms
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "neither the loft nor the boardroom is free on the twentieth so either we move the workshop or we use the roof terrace"},
  "Neither the loft nor the boardroom is free on the 20th, so either we move the workshop or we use the roof terrace.",
  {"numbers": ["20"], "must_include": ["Neither the loft nor the boardroom", "either we move the workshop or we use the roof terrace"], "min_negations": 2},
  "facts: NEITHER loft NOR boardroom free on the 20th (both negated); genuine either/or: move the workshop OR use the roof terrace, both kept")

# 161 rules to bullets, keep every don't, tuition centre
R(FN, {"task": "rewrite", "format": "bullets",
       "instruction": "bullet the rules for new tutors and keep every don't and no",
       "transcript": "a few rules for new tutors please don't give out your personal number don't keep students past seven thirty without telling the front desk always log attendance before the class starts and no homework help over whatsapp after nine pm"},
  "- Don't give out your personal number.\n- Don't keep students past 7:30 without telling the front desk.\n- Always log attendance before the class starts.\n- No homework help over WhatsApp after 9 p.m.",
  {"format": "bullets", "numbers": ["7:30", "9"], "must_include": ["Don't give out your personal number", "Don't keep students past 7:30 without telling the front desk", "Always log attendance", "No homework help over WhatsApp after 9 p.m."], "min_negations": 4},
  "facts: four rules, both 'don't's and the 'no' kept as prohibitions: DON'T share personal number; DON'T keep students past 7:30 WITHOUT telling front desk; ALWAYS log attendance before class; NO homework help on WhatsApp after 9 p.m.",
  pos="after")

# 162 correction of a correction with amounts, used car offer, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "tell him our final offer is four lakh eighty thousand no four lakh seventy five thousand actually no keep it at four lakh eighty thousand and that includes the transfer fees"},
  "Tell him our final offer is 4,80,000, and that includes the transfer fees.",
  {"numbers": ["4,80,000"], "numbers_one_of": [["4,80,000", "4.8 lakh"]], "must_not_include": ["4,75,000", "4.75"], "must_include": ["final offer", "includes the transfer fees"]},
  "facts: correction of a correction: 4,80,000 -> 4,75,000 -> back to 4,80,000 ('actually no keep it at'); final offer 4,80,000 includes transfer fees; no currency named so no ₹; checker waiver: checker applies the first correction, then only half-applies 'actually no keep it at' and expects a stray 4,00,075; the only correct final figure is 4,80,000",
  waivers=["number_missing"])

# 163 'correction' as a spoken cue, concert shuttle
R(CA, {"task": "cleanup",
       "transcript": "the shuttle to the venue leaves at eight correction eight fifteen from the north gate"},
  "The shuttle to the venue leaves at 8:15 from the north gate.",
  {"numbers": ["8:15"], "must_include": ["shuttle", "north gate"]},
  "facts: 'correction' is a spoken self-correction cue: shuttle leaves at 8:15 (8 corrected away); from the north gate")

# 164 safety rules, negations, research lab
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the new centrifuge is rated for fifteen thousand rpm max never run it above that and don't use the old rotors with it they're not compatible"},
  "The new centrifuge is rated for 15,000 rpm max. Never run it above that, and don't use the old rotors with it; they're not compatible.",
  {"numbers_one_of": [["15,000", "15000"]], "must_include": ["15,000 rpm max", "Never run it above that", "don't use the old rotors", "not compatible"], "min_negations": 3},
  "facts: rated 15,000 rpm max; NEVER run above that; DON'T use old rotors; they're NOT compatible")

# 165 alternative dates + time-of-day correction under email, interior design
R(CA, {"task": "rewrite", "format": "email", "sender": "Odile", "recipient": "Ji-woo",
       "transcript": "tell ji-woo the curtain fitter can come on the third or the fourth in the morning sorry afternoon and it'll take about two hours she needs to clear the window seats before he arrives"},
  "Hi Ji-woo,\n\nThe curtain fitter can come on the 3rd or the 4th in the afternoon, and it'll take about 2 hours. You need to clear the window seats before he arrives.\n\nBest,\nOdile",
  {"format": "email", "numbers": ["3", "4", "2"], "must_include": ["Ji-woo", "3rd or the 4th", "afternoon", "about 2 hours", "window seats", "Odile"], "must_not_include": ["morning"]},
  "facts: genuine alternative 3rd OR 4th, both kept; 'sorry' corrects morning to afternoon; ABOUT 2 hours; Ji-woo must clear the window seats before he arrives; no added offers")

# 166 rupee amount + restriction, concert parking, en-in
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "the parking fee at the venue is two hundred rupees and it's cash only"},
  "The parking fee at the venue is ₹200, and it's cash only.",
  {"numbers": ["200"], "must_include": ["₹200", "cash only"]},
  "facts: parking ₹200 (rupees spoken); cash only (restriction)")

# 167 long handover, correction + alternative + negations, permits office
R(CA, {"task": "cleanup",
       "transcript": "notes for the friday handover um the restaurant patio permit for mirela's place is approved but the signage one isn't she can pick up the certificate monday or tuesday after ten no wait after eleven because the system's down in the mornings this week the fee was two hundred forty dollars and she paid it already so don't charge her again and the food truck application from theo is missing the fire inspection so it's on hold not rejected"},
  "Notes for the Friday handover: the restaurant patio permit for Mirela's place is approved, but the signage one isn't. She can pick up the certificate Monday or Tuesday after 11 because the system's down in the mornings this week. The fee was $240, and she paid it already, so don't charge her again. The food truck application from Theo is missing the fire inspection, so it's on hold, not rejected.",
  {"numbers": ["11", "240"], "must_not_include": ["after 10"],
   "must_include": ["Mirela", "patio permit", "signage one isn't", "Monday or Tuesday after 11", "$240", "paid it already", "don't charge her again", "Theo", "fire inspection", "on hold, not rejected"], "min_negations": 3},
  "facts: patio permit approved, signage NOT; pickup Monday OR Tuesday (both kept) after 11 (10 corrected away by 'no wait'); fee $240 already paid, DON'T charge again; Theo's food truck application missing fire inspection: on hold, NOT rejected")

# 168 answer 'no' + 'I mean' refinement, co-working deposit
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "no the deposit's refundable i mean partly refundable"},
  "No, the deposit's partly refundable.",
  {"must_include": ["No,", "partly refundable"], "min_negations": 1},
  "facts: leading 'no' is an answer and stays; 'I mean partly refundable' corrects 'refundable' to PARTLY refundable")

# 169 casual rewrite message, negations, concert e-tickets
R(FN, {"task": "rewrite", "format": "message", "register": "casual",
       "transcript": "let yusuf know the tickets are e-tickets so there's nothing to print but he can't transfer his to anyone else because they're name locked"},
  "Yusuf, the tickets are e-tickets, so there's nothing to print, but you can't transfer yours to anyone else because they're name-locked.",
  {"format": "message", "must_include": ["Yusuf", "e-tickets", "nothing to print", "can't transfer", "name-locked"], "min_negations": 2},
  "facts: e-tickets, NOTHING to print; Yusuf can NOT transfer his ticket because they're name-locked")

# 170 measurement correction 'no wait', interior design, en-gb
R(CA, {"task": "cleanup", "locale": "en-gb",
       "transcript": "the sofa is two hundred twenty no wait two hundred forty centimetres wide so it won't fit through the hall door we'll have to bring it in through the patio"},
  "The sofa is 240 centimetres wide, so it won't fit through the hall door. We'll have to bring it in through the patio.",
  {"numbers": ["240"], "must_not_include": ["220"], "must_include": ["240 centimetres wide", "won't fit through the hall door", "through the patio"], "min_negations": 1},
  "facts: sofa 240 cm wide (220 corrected away by 'no wait'); WON'T fit through hall door; bring in through the patio")

# 171 'not X but Y' + either/or under rewrite message, tuition centre
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "tell the parents the extra class is not on sunday but on saturday at either nine or eleven depending on the batch"},
  "The extra class is not on Sunday but on Saturday, at either 9 or 11 depending on the batch.",
  {"format": "message", "numbers": ["9", "11"], "must_include": ["not on Sunday but on Saturday", "either 9 or 11", "depending on the batch"], "min_negations": 1},
  "facts: stated contrast NOT Sunday BUT Saturday (both days appear, not a self-correction); genuine either/or 9 OR 11 depending on batch; parents not addressed by name so no vocative")

# 172 numbers + 'without', used car insurance, en-in
R(FN, {"task": "cleanup", "locale": "en-in",
       "transcript": "the insurance quote came in at eighteen thousand a year but that's without zero depreciation cover which adds another three thousand two hundred"},
  "The insurance quote came in at 18,000 a year, but that's without zero depreciation cover, which adds another 3,200.",
  {"numbers": ["18,000", "3,200"], "numbers_one_of": [["18,000", "18000"], ["3,200", "3200"]], "must_include": ["a year", "without zero depreciation cover", "another 3,200"], "min_negations": 1},
  "facts: quote 18,000 a year WITHOUT zero depreciation cover; that cover adds another 3,200; no currency spoken, no symbol")

# 173 either/or, concert rescheduled show
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "you can either swap the ticket for the later show or get a full refund"},
  "You can either swap the ticket for the later show or get a full refund.",
  {"must_include": ["either swap the ticket for the later show or get a full refund"]},
  "facts: genuine either/or: swap for the later show OR full refund, both kept")

# 174 name correction 'sorry', corrected name reappears in another role, co-working
R(CA, {"task": "cleanup",
       "transcript": "the keys for the private office go to aditya sorry to parth aditya's moving to the hot desks next month"},
  "The keys for the private office go to Parth. Aditya's moving to the hot desks next month.",
  {"must_include": ["private office go to Parth", "Aditya's moving to the hot desks", "next month"], "must_not_include": ["go to Aditya"]},
  "facts: 'sorry to Parth' corrects the key holder: keys go to Parth (Aditya corrected away as recipient); Aditya legitimately reappears: he's moving to the hot desks next month")

# 175 long client brief, hedges + alternatives + negations, interior design, en-gb
R(FN, {"task": "cleanup", "locale": "en-gb",
       "transcript": "so the client brief for the nursery um they want it calm so no bright primaries maybe a soft sage or a warm grey they haven't decided the cot has to be at least sixty centimetres from the radiator and nothing can be wall mounted above it um budget's around three thousand pounds including the blackout blind but not the furniture they already bought and they'd like it done before the baby's due which is early march"},
  "The client brief for the nursery: they want it calm, so no bright primaries, maybe a soft sage or a warm grey; they haven't decided. The cot has to be at least 60 centimetres from the radiator, and nothing can be wall-mounted above it. Budget's around £3,000, including the blackout blind but not the furniture they already bought, and they'd like it done before the baby's due, which is early March.",
  {"numbers": ["60", "3,000"], "numbers_one_of": [["3,000", "3000"]],
   "must_include": ["no bright primaries", "maybe a soft sage or a warm grey", "haven't decided", "at least 60 centimetres", "nothing can be wall-mounted", "around £3,000", "but not the furniture", "early March"], "min_negations": 4},
  "facts: NO bright primaries; hedge 'maybe' + alternative soft sage OR warm grey, both kept, NOT decided; cot at least 60 cm from radiator; NOTHING wall-mounted above it; budget AROUND £3,000 incl. blackout blind, NOT the furniture; done before baby's due, early March")

# 176 place correction under rewrite message with range, ride-share
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "tell the night drivers the bonus zone is downtown no wait the airport road between eleven and two"},
  "Night drivers, the bonus zone is the airport road between 11 and 2.",
  {"format": "message", "numbers": ["11", "2"], "must_include": ["Night drivers", "airport road", "between 11 and 2"], "must_not_include": ["downtown"]},
  "facts: 'no wait' correction: bonus zone is the airport road (downtown corrected away); time range between 11 and 2 (a range, not an alternative); vocative allowed because the night drivers are addressed")

# 177 restriction + condition, concert booking fees
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "booking fees aren't refundable even if the show is rescheduled"},
  "Booking fees aren't refundable, even if the show is rescheduled.",
  {"must_include": ["aren't refundable", "even if the show is rescheduled"], "min_negations": 1},
  "facts: booking fees NOT refundable, even if the show is rescheduled")

# 178 'or rather' duration correction + range, tuition crash course, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "the crash course runs for six weeks or rather eight weeks with classes between four and six pm and the fee is twelve thousand rupees for the whole thing"},
  "The crash course runs for 8 weeks, with classes between 4 and 6 p.m., and the fee is ₹12,000 for the whole thing.",
  {"numbers": ["8", "4", "6"], "numbers_one_of": [["12,000", "12000"]], "must_not_include": ["6 weeks"], "must_include": ["8 weeks", "between 4 and 6 p.m.", "₹12,000", "whole thing"]},
  "facts: 'or rather' correction: 8 weeks (6 weeks corrected away); classes between 4 and 6 p.m. (range; this 6 is a time, not the corrected duration); fee ₹12,000 for the whole course")

# 179 date correction under invitation email, co-working
R(CA, {"task": "rewrite", "format": "email", "sender": "Mirela",
       "transcript": "invite the members to the networking evening on the twenty third or rather the twenty fourth from six to eight drinks are on us and they can bring one guest"},
  "Hi,\n\nYou're invited to the networking evening on the 24th from 6 to 8. Drinks are on us, and you can bring one guest.\n\nBest,\nMirela",
  {"format": "email", "numbers": ["24", "6", "8"], "must_not_include": ["23"], "must_include": ["networking evening", "24th from 6 to 8", "Drinks are on us", "one guest", "Mirela"]},
  "facts: 'or rather' correction: 24th (23rd corrected away); 6 to 8; drinks on us (dictated); members may bring one guest; no recipient name -> 'Hi,'; no added RSVP request or offers")

# 180 hedges + numbers + negation, ride-share driver log
R(FN, {"task": "cleanup",
       "transcript": "i think i drove about three hundred and ten kilometres today which is probably a record but i didn't log the last two trips so the app might show less"},
  "I think I drove about 310 kilometres today, which is probably a record, but I didn't log the last two trips, so the app might show less.",
  {"numbers": ["310"], "must_include": ["I think", "about 310 kilometres", "probably a record", "didn't log the last two trips", "might show less"], "min_negations": 1},
  "facts: hedges 'I think', 'about', 'probably', 'might' all kept; 310 km today; did NOT log last two trips")


# =============================================================== chunk 3 (181-225)

# 181 long voicemail: two numeric corrections + alternative + range, concert group tickets
R(CA, {"task": "cleanup",
       "transcript": "hey ravina it's mateo about the festival tickets um so i managed to get six no seven passes for the sunday because theo's cousin is coming too they were fifty nine sorry ninety five dollars each with the fees so the total's six hundred sixty five dollars you can pay me back by bank transfer or cash whatever's easier but not through the app because it charges me a fee uh the gates open at eleven and we should get there between eleven thirty and noon if we want a spot near the stage"},
  "Hey Ravina, it's Mateo about the festival tickets. I managed to get seven passes for the Sunday because Theo's cousin is coming too. They were $95 each with the fees, so the total's $665. You can pay me back by bank transfer or cash, whatever's easier, but not through the app because it charges me a fee. The gates open at 11, and we should get there between 11:30 and noon if we want a spot near the stage.",
  {"numbers": ["95", "665", "11", "11:30"], "must_not_include": ["six passes", "$59"],
   "must_include": ["Ravina", "Mateo", "seven passes", "Theo's cousin", "$95 each with the fees", "$665", "bank transfer or cash", "not through the app", "between 11:30 and noon"], "min_negations": 1},
  "facts: seven passes (six corrected away by 'no'); $95 each with fees ('fifty nine sorry ninety five' is a misspoken-digit correction; 59 removed); total $665 (7 x 95, consistent); genuine alternative bank transfer OR cash, NOT through the app; gates open 11; arrive between 11:30 and noon (range) if they want a spot near the stage")

# 182 short alternative + negation, concert crew van
R(CA, {"task": "cleanup",
       "transcript": "book the van for friday or saturday not sunday"},
  "Book the van for Friday or Saturday, not Sunday.",
  {"must_include": ["Friday or Saturday", "not Sunday"], "min_negations": 1},
  "facts: genuine alternative Friday OR Saturday, both kept; NOT Sunday")

# 183 formal complaint email, date correction, used car, en-in
R(CA, {"task": "rewrite", "format": "email", "register": "formal", "locale": "en-in", "sender": "Clara", "recipient": "Mr. Osei",
       "instruction": "formal and firm, but don't threaten anything and keep both options I'm asking for",
       "transcript": "write to mr osei at the dealership um i bought the grey hatchback from them on the second sorry fourth of september and the service light came on after three days they said the free first service covers it but now they're asking me to pay four thousand five hundred rupees for the sensor i'm not paying that because it's within the thirty day warranty i'd like them to either fix it free or refund the amount i already paid at the workshop which was one thousand two hundred"},
  "Dear Mr. Osei,\n\nI bought the grey hatchback from your dealership on the 4th of September, and the service light came on after three days. I was told the free first service covers it, but I am now being asked to pay ₹4,500 for the sensor. I am not paying that, because it is within the 30-day warranty. I would like you to either fix it free of charge or refund the amount I already paid at the workshop, which was 1,200.\n\nRegards,\nClara",
  {"format": "email", "numbers": ["4", "4,500", "30", "1,200"], "numbers_one_of": [["4,500", "4500"], ["1,200", "1200"]], "must_not_include": ["2nd"],
   "must_include": ["Mr. Osei", "grey hatchback", "4th of September", "after three days", "free first service", "₹4,500", "not paying", "30-day warranty", "either fix it free", "refund", "1,200", "Clara"], "min_negations": 1},
  "facts: bought on the 4th of September (2nd corrected away by 'sorry'); service light after three days; told first service covers it; now asked ₹4,500 for sensor (rupees spoken for this amount; the 1,200 workshop amount gets no symbol, choice noted); NOT paying because within 30-day warranty; genuine either/or: fix free OR refund the 1,200 already paid, both kept; no threats or extra demands added")

# 184 short seat correction, concert
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "the seats are in block c row twelve sorry row fourteen"},
  "The seats are in Block C, Row 14.",
  {"numbers": ["14"], "must_not_include": ["12"], "must_include": ["Block C", "Row 14"]},
  "facts: 'sorry' corrects the row: Row 14 (Row 12 corrected away); Block C")

# 185 long exam-week announcement, standing rules in own sentences, tuition centre, en-in
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "announcement for all batches um the half yearly exams start on the fourteenth and run till the twenty second classes are suspended during that week except the doubt clearing sessions which will run from four to six every day students must carry their id cards and the rule is no id no entry and phones are not allowed in the exam hall at all if a student is absent for medical reasons the parent has to email us the same day otherwise the retest fee is five hundred rupees"},
  "Announcement for all batches: the half-yearly exams start on the 14th and run till the 22nd. Classes are suspended during that week, except the doubt-clearing sessions, which will run from 4 to 6 every day. Students must carry their ID cards, and the rule is no ID, no entry. Phones are not allowed in the exam hall at all. If a student is absent for medical reasons, the parent has to email us the same day; otherwise, the retest fee is ₹500.",
  {"numbers": ["14", "22", "4", "6", "500"],
   "must_include": ["14th", "22nd", "suspended", "except the doubt-clearing sessions", "4 to 6 every day", "the rule is no ID, no entry", "Phones are not allowed in the exam hall at all", "If a student is absent for medical reasons", "same day", "₹500"], "min_negations": 3},
  "facts: exams 14th to 22nd; classes suspended that week EXCEPT doubt-clearing 4 to 6 daily; ID cards mandatory, NO ID NO entry; phones NOT allowed in the hall at all (standing rule, own sentence); conditional: medical absence needs same-day email from parent, otherwise retest fee ₹500")

# 186 short negation of coverage, used car warranty
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the warranty covers the engine for twelve months but not the battery"},
  "The warranty covers the engine for 12 months but not the battery.",
  {"numbers": ["12"], "must_include": ["engine for 12 months", "not the battery"], "min_negations": 1},
  "facts: engine covered 12 months; battery NOT covered")

# 187 long move-in checklist to bullets, weekday + count corrections, co-working
R(CA, {"task": "rewrite", "format": "bullets",
       "instruction": "turn this into a checklist for the front desk, keep both kickoff times",
       "transcript": "okay so for theo's team moving in on monday sorry tuesday we need to set up eight no wait ten desks in the east wing get five access cards printed one of them is for their office manager who starts later um book the big screen in room c for their kickoff at two or three whichever bongani confirms and don't assign them the lockers by the kitchen those are reserved"},
  "- Theo's team moves in on Tuesday.\n- Set up 10 desks in the east wing.\n- Get five access cards printed; one is for their office manager, who starts later.\n- Book the big screen in Room C for their kickoff at 2 or 3, whichever Bongani confirms.\n- Don't assign them the lockers by the kitchen; those are reserved.",
  {"format": "bullets", "numbers": ["10", "2", "3"], "must_not_include": ["Monday", "8 desks", "eight desks"],
   "must_include": ["Theo's team", "Tuesday", "10 desks in the east wing", "five access cards", "office manager", "Room C", "2 or 3, whichever Bongani confirms", "Don't assign them the lockers by the kitchen"], "min_negations": 1},
  "facts: move-in Tuesday (Monday corrected away by 'sorry'); 10 desks (8 corrected away by 'no wait'); five access cards, one of them for the office manager who starts later; kickoff at 2 OR 3, whichever Bongani confirms (both kept); DON'T assign the lockers by the kitchen (reserved)",
  pos="after")

# 188 short negation, co-working hot desks
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "none of the hot desks have monitors so bring your own"},
  "None of the hot desks have monitors, so bring your own.",
  {"must_include": ["None of the hot desks", "bring your own"], "min_negations": 1},
  "facts: NONE of the hot desks have monitors; bring your own")

# 189 long grant notes, amount correction + either/or + standing rule, research lab
R(CA, {"task": "cleanup",
       "transcript": "notes from the meeting with odile about the grant budget um we asked for forty thousand dollars for equipment no wait fifty thousand the forty was last year's number so fifty thousand for equipment and twelve thousand for travel the reviewers might cut travel so we have a backup plan either we share the conference trip with parth's group or we drop one of the two conferences ji-woo will draft the justification by thursday and nothing gets submitted until the dean signs off"},
  "Notes from the meeting with Odile about the grant budget: we asked for $50,000 for equipment. The 40 was last year's number, so $50,000 for equipment and $12,000 for travel. The reviewers might cut travel, so we have a backup plan: either we share the conference trip with Parth's group or we drop one of the two conferences. Ji-woo will draft the justification by Thursday, and nothing gets submitted until the dean signs off.",
  {"numbers": ["50,000", "40", "12,000"], "must_not_include": ["$40,000"],
   "must_include": ["Odile", "$50,000 for equipment", "last year's number", "$12,000 for travel", "might cut travel", "either we share the conference trip with Parth's group or we drop one of the two conferences", "Ji-woo", "by Thursday", "nothing gets submitted until the dean signs off"], "min_negations": 1},
  "facts: equipment request $50,000 ($40,000 corrected away by 'no wait'; 'the 40 was last year's number' is the speaker's explanation and stays); travel $12,000 ($ applied to all three budget figures: dollars spoken for the first, same budget list); hedge 'might' kept; genuine either/or backup: share trip with Parth's group OR drop one of two conferences; Ji-woo drafts justification by Thursday; NOTHING submitted until the dean signs off")

# 190 short range, tuition recital programmes, en-gb
R(CA, {"task": "cleanup", "header_style": "full", "locale": "en-gb",
       "transcript": "order between forty and fifty programmes for the recital"},
  "Order between 40 and 50 programmes for the recital.",
  {"numbers": ["40", "50"], "must_include": ["between 40 and 50 programmes"]},
  "facts: 'between 40 and 50' is a range, not an alternative or correction; both bounds kept")

# 191 long counter-staff notes, correction of a correction + alternative + stated contrast, permits office
R(CA, {"task": "cleanup",
       "transcript": "okay for the counter staff um starting next week the permit office opens at eight thirty no eight actually eight thirty was right we just close earlier on fridays at three instead of four thirty uh walk ins are only until two on fridays and appointments can be booked online or over the phone not by email anymore mateo will update the website and please tell anyone asking about the old fee schedule that it's gone the new fees are on the board"},
  "For the counter staff: starting next week, the permit office opens at 8:30. We just close earlier on Fridays, at 3 instead of 4:30. Walk-ins are only until 2 on Fridays, and appointments can be booked online or over the phone, not by email anymore. Mateo will update the website, and please tell anyone asking about the old fee schedule that it's gone. The new fees are on the board.",
  {"numbers": ["8:30", "3", "4:30", "2"],
   "must_include": ["next week", "opens at 8:30", "Fridays, at 3 instead of 4:30", "only until 2 on Fridays", "online or over the phone, not by email anymore", "Mateo", "old fee schedule", "new fees are on the board"], "min_negations": 1},
  "facts: correction of a correction: opens 8:30 -> 8 -> back to 8:30 ('actually eight thirty was right'); Fridays close at 3 instead of 4:30 (stated contrast, both kept); walk-ins only until 2 on Fridays; appointments online OR by phone (both kept), NOT by email anymore; Mateo updates website; old fee schedule gone, new fees on the board")

# 192 short 'scratch that' name correction, tuition centre
R(CA, {"task": "cleanup",
       "transcript": "the chemistry tutor is ravina scratch that theo"},
  "The chemistry tutor is Theo.",
  {"must_include": ["chemistry tutor is Theo"], "must_not_include": ["Ravina"]},
  "facts: 'scratch that' correction: chemistry tutor is Theo (Ravina corrected away)")

# 193 long sample-shipment email, numbers + condition + warning, research lab
R(FN, {"task": "rewrite", "format": "email", "sender": "Sneha", "recipient": "Dr. Lindqvist",
       "instruction": "make it an email, keep the tracking number exactly and the warning about thawing",
       "transcript": "let dr lindqvist know we shipped the samples on dry ice this morning there are twenty four tubes in two boxes the tracking number is a w b four four seven one nine zero eight three they should arrive within forty eight hours but customs might hold them so if they're not there by friday she should email me and please don't thaw them before checking the labels against the manifest because two tubes have handwritten labels"},
  "Hi Dr. Lindqvist,\n\nWe shipped the samples on dry ice this morning. There are 24 tubes in two boxes, and the tracking number is AWB 44719083. They should arrive within 48 hours, but customs might hold them, so if they're not there by Friday, please email me. Please don't thaw them before checking the labels against the manifest, because two tubes have handwritten labels.\n\nBest,\nSneha",
  {"format": "email", "numbers": ["24", "44719083", "48"],
   "must_include": ["Dr. Lindqvist", "dry ice this morning", "24 tubes in two boxes", "AWB 44719083", "within 48 hours", "customs might hold them", "if they're not there by Friday", "don't thaw them before checking the labels against the manifest", "two tubes have handwritten labels", "Sneha"], "min_negations": 2},
  "facts: shipped on dry ice this morning; 24 tubes in two boxes; tracking AWB 44719083 (spelled out, kept exactly); should arrive within 48 hours, customs MIGHT hold them; conditional: if not there by Friday, email Sneha; DON'T thaw before checking labels against the manifest (two tubes hand-labelled); 'please' added only as polite form of the dictated request, no new request")

# 194 short hedge + negation, used car service history
R(FN, {"task": "cleanup",
       "transcript": "i'm not sure the car's been serviced since march"},
  "I'm not sure the car's been serviced since March.",
  {"must_include": ["I'm not sure", "since March"], "min_negations": 1},
  "facts: speaker is NOT sure (uncertainty kept, not turned into a claim); serviced since March is the uncertain point")

# 195 long incident report, time correction + either/or + negations, ride-share
R(CA, {"task": "cleanup",
       "transcript": "incident report for trip ending in four seven two um i picked up the rider at the mall at nine fifteen no wait nine forty five and the drop was the train station he said he'd left his bag in the back but when i checked there was nothing there i didn't see him take it so either it fell out at the station or he never brought it i'm not sure which i've attached the dashcam clip from nine forty to ten and i won't be driving tomorrow morning because of the police statement"},
  "Incident report for trip ending in 472: I picked up the rider at the mall at 9:45, and the drop was the train station. He said he'd left his bag in the back, but when I checked, there was nothing there. I didn't see him take it, so either it fell out at the station or he never brought it; I'm not sure which. I've attached the dashcam clip from 9:40 to 10, and I won't be driving tomorrow morning because of the police statement.",
  {"numbers": ["472", "9:45", "9:40", "10"], "must_not_include": ["9:15"],
   "must_include": ["trip ending in 472", "mall at 9:45", "train station", "nothing there", "didn't see him take it", "either it fell out at the station or he never brought it", "not sure which", "9:40 to 10", "won't be driving tomorrow morning"], "min_negations": 5},
  "facts: trip ending 472; pickup 9:45 (9:15 corrected away by 'no wait'); drop at train station; bag: NOTHING there when checked; speaker DIDN'T see him take it; genuine either/or (fell out at station OR never brought it), speaker NOT sure which; dashcam clip 9:40 to 10; WON'T drive tomorrow morning (police statement)")

# 196 short alternative under rewrite message, permits handover
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "tell parth either friday or monday works for the handover"},
  "Parth, either Friday or Monday works for the handover.",
  {"format": "message", "must_include": ["Parth", "either Friday or Monday", "handover"]},
  "facts: genuine either/or: Friday OR Monday works for the handover, both kept")

# 197 long client update to prose, date correction + alternative + hedge + condition, interior design
R(CA, {"task": "rewrite", "format": "prose",
       "instruction": "polish this into a short update paragraph for the client, keep both transit estimates and the hedge about the light",
       "transcript": "um update for mr and mrs fenwick the dining table is delayed the workshop says it'll ship on the tenth sorry seventeenth and then it's either two or three days in transit depending on the courier the chairs are already here in our storage and the pendant light might be swapped for the smaller version if the ceiling hook can't take the weight we'll know after the electrician checks on monday nothing's being charged until everything is installed"},
  "Update for Mr. and Mrs. Fenwick: the dining table is delayed. The workshop says it'll ship on the 17th, and then it's either two or three days in transit, depending on the courier. The chairs are already here in our storage. The pendant light might be swapped for the smaller version if the ceiling hook can't take the weight; we'll know after the electrician checks on Monday. Nothing is being charged until everything is installed.",
  {"format": "prose", "numbers": ["17"], "must_not_include": ["10th"],
   "must_include": ["Fenwick", "delayed", "17th", "either two or three days in transit", "depending on the courier", "chairs are already here", "might be swapped for the smaller version if the ceiling hook can't take the weight", "Monday", "Nothing is being charged until everything is installed"], "min_negations": 2},
  "facts: table ships the 17th (10th corrected away by 'sorry'); transit either two OR three days depending on courier, both kept; chairs already in storage; pendant light MIGHT be swapped for smaller version only IF ceiling hook can't take the weight; known after electrician checks Monday; NOTHING charged until everything installed")

# 198 short rupee amount + date, tuition late fee, en-in
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "the late fee is fifty rupees a day after the tenth"},
  "The late fee is ₹50 a day after the 10th.",
  {"numbers": ["50", "10"], "must_include": ["₹50 a day", "after the 10th"]},
  "facts: late fee ₹50 per day (rupees spoken), applies after the 10th")

# 199 long weekend house rules, standing rules + condition + hedge, co-working, en-gb
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-gb",
       "transcript": "quick house rules for the weekend members um the building's open from nine to six on saturdays and closed on sundays the alarm sets automatically at six fifteen so be out by then or it goes off and we get charged for the callout guests have to be signed in at the front desk no exceptions and you can't bring more than two at a time the printer works but colour printing is paused until the new toner arrives probably next week"},
  "Quick house rules for the weekend members: the building's open from 9 to 6 on Saturdays and closed on Sundays. The alarm sets automatically at 6:15, so be out by then, or it goes off and we get charged for the callout. Guests have to be signed in at the front desk, no exceptions, and you can't bring more than two at a time. The printer works, but colour printing is paused until the new toner arrives, probably next week.",
  {"numbers": ["9", "6", "6:15"],
   "must_include": ["9 to 6 on Saturdays", "closed on Sundays", "6:15", "be out by then", "charged for the callout", "no exceptions", "can't bring more than two at a time", "colour printing is paused", "probably next week"], "min_negations": 2},
  "facts: open 9 to 6 Saturdays, closed Sundays; alarm sets 6:15, be out or it goes off and we're charged; guests signed in at front desk, NO exceptions; can NOT bring more than two at a time; colour printing paused until new toner, PROBABLY next week (hedge)")

# 200 short apology 'sorry' + 'I meant', co-working invoice
R(CA, {"task": "cleanup",
       "transcript": "sorry wrong file i meant to send the march invoice"},
  "Sorry, wrong file. I meant to send the March invoice.",
  {"must_include": ["Sorry, wrong file", "meant to send the March invoice"]},
  "facts: 'sorry' is an apology for sending the wrong file (not a spoken self-correction), so it stays; 'I meant to send' is content, kept; March invoice")

# 201 long group-chat message, stated contrast + either/or + negations, concert, en-in
R(CA, {"task": "rewrite", "format": "message", "locale": "en-in",
       "instruction": "group chat message, keep both travel options and the Wednesday deadline",
       "transcript": "tell the group the concert's on the twenty sixth not the twenty fifth i had that wrong earlier we can either take the metro which is about forty minutes or share a cab for around six hundred rupees split four ways and we need to leave by five thirty because security lines are long uh bongani has the tickets so don't go in without him and if anyone can't make it tell me by wednesday so i can resell the ticket"},
  "The concert's on the 26th, not the 25th; I had that wrong earlier. We can either take the metro, which is about 40 minutes, or share a cab for around ₹600, split four ways. We need to leave by 5:30 because security lines are long. Bongani has the tickets, so don't go in without him, and if anyone can't make it, tell me by Wednesday so I can resell the ticket.",
  {"format": "message", "numbers": ["26", "25", "40", "600", "5:30"],
   "must_include": ["26th, not the 25th", "had that wrong earlier", "either take the metro", "about 40 minutes", "share a cab for around ₹600", "split four ways", "leave by 5:30", "Bongani has the tickets", "don't go in without him", "if anyone can't make it", "by Wednesday"], "min_negations": 3},
  "facts: concert on the 26th, NOT the 25th (stated correction of an earlier message, both dates appear); genuine either/or: metro (ABOUT 40 minutes) OR shared cab (AROUND ₹600, split four ways); leave by 5:30; Bongani has tickets, DON'T go in WITHOUT him; conditional: if anyone can't make it, tell by Wednesday so the speaker can resell",
  pos="before")

# 202 short prohibition, co-working loading bay
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "nobody parks in the loading bay not even for five minutes"},
  "Nobody parks in the loading bay, not even for 5 minutes.",
  {"numbers": ["5"], "must_include": ["Nobody parks in the loading bay", "not even for 5 minutes"], "min_negations": 2},
  "facts: unconditional prohibition: NOBODY parks in the loading bay, NOT even for 5 minutes")

# 203 long seller-call notes, three-way alternative + numbers + hedge, used car, en-in
R(CA, {"task": "cleanup", "locale": "en-in",
       "transcript": "notes from the call with the seller um he's got three cars that fit our budget the white swift the red baleno or the grey city the swift is the cheapest at three lakh ninety thousand but it's done ninety thousand kilometres the baleno is four lakh sixty thousand with forty one thousand kilometres and the city is five lakh ten thousand but he said maybe he can come down a bit on that one he can't show them all on the same day so we have to pick two for saturday"},
  "Notes from the call with the seller: he's got three cars that fit our budget, the white Swift, the red Baleno or the grey City. The Swift is the cheapest at 3,90,000, but it's done 90,000 kilometres. The Baleno is 4,60,000 with 41,000 kilometres, and the City is 5,10,000, but he said maybe he can come down a bit on that one. He can't show them all on the same day, so we have to pick two for Saturday.",
  {"numbers": ["3,90,000", "90,000", "4,60,000", "41,000", "5,10,000"],
   "must_include": ["three cars", "white Swift", "red Baleno", "grey City", "cheapest", "maybe he can come down a bit", "can't show them all on the same day", "pick two for Saturday"], "min_negations": 1},
  "facts: three-way alternative, all kept: white Swift (cheapest, 3,90,000, 90,000 km), red Baleno (4,60,000, 41,000 km), grey City (5,10,000, MAYBE negotiable); seller can NOT show all on the same day; pick two for Saturday; no currency named so no ₹")

# 204 short hedged alternative, concert encore
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "the encore might be two songs or three depending on the curfew"},
  "The encore might be two songs or three, depending on the curfew.",
  {"must_include": ["might be two songs or three", "depending on the curfew"]},
  "facts: hedge 'might' kept; genuine alternative two OR three songs, both kept; depends on the curfew")

# 205 long formal fee-revision email, tuition centre, en-in
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "locale": "en-in", "sender": "Ravina",
       "transcript": "inform all parents that from april the monthly fee for classes nine and ten goes up from three thousand to three thousand four hundred rupees the fee for classes six to eight stays the same there's no change to the test series fee and siblings still get ten percent off the second child's fee if anyone has already paid for the full year in advance the old rate applies to them"},
  "Dear Parents,\n\nFrom April, the monthly fee for Classes 9 and 10 will increase from ₹3,000 to ₹3,400. The fee for Classes 6 to 8 remains the same. There is no change to the test series fee, and siblings still receive 10% off the second child's fee. If you have already paid for the full year in advance, the old rate applies to you.\n\nRegards,\nRavina",
  {"format": "email", "numbers": ["9", "10", "3,000", "3,400", "6", "8"], "numbers_one_of": [["3,000", "3000"], ["3,400", "3400"]],
   "must_include": ["Dear Parents", "From April", "Classes 9 and 10", "₹3,000 to ₹3,400", "Classes 6 to 8", "no change to the test series fee", "10% off the second child's fee", "already paid for the full year in advance", "old rate", "Ravina"], "min_negations": 1},
  "facts: from April Classes 9-10 fee rises from ₹3,000 to ₹3,400 (₹ on both, same sentence); Classes 6-8 unchanged; NO change to test series fee; siblings still 10% off the second child's fee; conditional: those who already paid the full year keep the old rate; greeting 'Dear Parents,' because the speaker named the recipients (all parents); formal sign-off with sender")

# 206 short 'I mean' time correction, tuition pick-up
R(CA, {"task": "cleanup",
       "transcript": "pick up's at four i mean four thirty at the side entrance"},
  "Pick-up's at 4:30 at the side entrance.",
  {"numbers": ["4:30"], "must_include": ["4:30", "side entrance"]},
  "facts: 'I mean' corrects the time: pick-up at 4:30 (4 corrected away); side entrance")

# 207 long voicemail, weekday correction + either/or + apology 'sorry' x2, ride-share depot
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "hi yusuf it's odile from the depot sorry i missed your call earlier um your car's service is booked for thursday at nine no wait wednesday at nine and it'll take about three hours so you can either wait in the lounge or take the shuttle to the mall and back the replacement car isn't available this time sorry about that and if you're running late call the front desk not my mobile"},
  "Hi Yusuf, it's Odile from the depot. Sorry I missed your call earlier. Your car's service is booked for Wednesday at 9, and it'll take about 3 hours, so you can either wait in the lounge or take the shuttle to the mall and back. The replacement car isn't available this time, sorry about that. If you're running late, call the front desk, not my mobile.",
  {"numbers": ["9", "3"], "must_not_include": ["Thursday"],
   "must_include": ["Yusuf", "Odile", "Sorry I missed your call earlier", "Wednesday at 9", "about 3 hours", "either wait in the lounge or take the shuttle", "replacement car isn't available", "sorry about that", "front desk, not my mobile"], "min_negations": 2},
  "facts: both 'sorry's are apologies and stay; 'no wait' corrects Thursday to Wednesday: service Wednesday at 9; ABOUT 3 hours; genuine either/or: wait in lounge OR shuttle to the mall and back; replacement car NOT available this time; conditional: if running late call front desk, NOT the mobile")

# 208 short negation under rewrite message, interior design
R(FN, {"task": "rewrite", "format": "message",
       "transcript": "let clara know the tiles didn't arrive and won't until thursday"},
  "Clara, the tiles didn't arrive and won't until Thursday.",
  {"format": "message", "must_include": ["Clara", "didn't arrive", "won't until Thursday"], "min_negations": 2},
  "facts: tiles did NOT arrive; WON'T arrive until Thursday")

# 209 long shopping list to bullets, count correction + alternatives, interior design
R(CA, {"task": "rewrite", "format": "bullets",
       "instruction": "make a shopping list, one item per bullet, keep the alternatives",
       "transcript": "for the bathroom refresh we need a new mirror seventy by ninety centimetres two no three towel rails in brushed brass or chrome whichever's in stock a pack of white grout not the grey and um silicone sealant the clear one oh and the extractor fan either the quiet model or the one with the humidity sensor clara's still deciding"},
  "- New mirror, 70 by 90 centimetres\n- Three towel rails in brushed brass or chrome, whichever's in stock\n- A pack of white grout, not the grey\n- Silicone sealant, the clear one\n- Extractor fan, either the quiet model or the one with the humidity sensor; Clara's still deciding",
  {"format": "bullets", "numbers": ["70", "90"], "must_not_include": ["Two towel rails"],
   "must_include": ["70 by 90 centimetres", "Three towel rails", "brushed brass or chrome, whichever's in stock", "white grout, not the grey", "clear one", "either the quiet model or the one with the humidity sensor", "Clara's still deciding"], "min_negations": 1},
  "facts: mirror 70 by 90 cm; three towel rails (two corrected away by 'no'), brushed brass OR chrome whichever's in stock; white grout, NOT grey; clear silicone sealant; extractor fan: quiet model OR humidity-sensor model, Clara still deciding",
  pos="after")

# 210 short no hot water + ordinal, co-working
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "there's no hot water on the third floor until the boiler's fixed"},
  "There's no hot water on the third floor until the boiler's fixed.",
  {"must_include": ["no hot water", "third floor", "until the boiler's fixed"], "min_negations": 1},
  "facts: NO hot water on the third floor until the boiler is fixed")

# 211 long inspection voicemail, negations + fee + condition, permits office
R(FN, {"task": "cleanup",
       "transcript": "hi this is parth from building inspections um i was at your property this morning for the framing inspection and unfortunately it didn't pass there are two issues the header over the garage door is undersized and the hurricane ties are missing on the north wall you don't need a new permit but you do need a re-inspection which costs seventy five dollars and can't be booked until both items are fixed if you have questions my extension is four one two"},
  "Hi, this is Parth from building inspections. I was at your property this morning for the framing inspection, and unfortunately it didn't pass. There are two issues: the header over the garage door is undersized, and the hurricane ties are missing on the north wall. You don't need a new permit, but you do need a re-inspection, which costs $75 and can't be booked until both items are fixed. If you have questions, my extension is 412.",
  {"numbers": ["75", "412"],
   "must_include": ["Parth", "framing inspection", "didn't pass", "two issues", "header over the garage door is undersized", "hurricane ties are missing on the north wall", "don't need a new permit", "re-inspection", "$75", "can't be booked until both items are fixed", "extension is 412"], "min_negations": 3},
  "facts: framing inspection did NOT pass; two issues (undersized garage-door header; missing hurricane ties on north wall); NO new permit needed, but re-inspection required, $75, can NOT be booked until both fixed; extension 412")

# 212 short 'actually no' recipient correction, co-working
R(CA, {"task": "cleanup",
       "transcript": "send it to the accounts team actually no just to mirela"},
  "Send it just to Mirela.",
  {"must_include": ["just to Mirela"], "must_not_include": ["accounts team"]},
  "facts: 'actually no' correction: send it only to Mirela (accounts team corrected away)")

# 213 long parent update, 'not X but Y' + numeric correction + either/or, tuition centre
R(CA, {"task": "cleanup",
       "transcript": "sorry for the late update um your son's problem isn't algebra but word problems he reads too fast and misses details he scored fourteen sorry sixteen out of twenty on friday's quiz which is better than last week i'd suggest either the saturday practice batch or ten minutes of reading practice at home each day not both he'll burn out"},
  "Sorry for the late update. Your son's problem isn't algebra but word problems; he reads too fast and misses details. He scored 16 out of 20 on Friday's quiz, which is better than last week. I'd suggest either the Saturday practice batch or 10 minutes of reading practice at home each day, not both; he'll burn out.",
  {"numbers": ["16", "20", "10"], "must_not_include": ["14"],
   "must_include": ["Sorry for the late update", "isn't algebra but word problems", "reads too fast", "16 out of 20", "better than last week", "either the Saturday practice batch or 10 minutes of reading practice", "not both"], "min_negations": 2},
  "facts: opening 'sorry' is an apology and stays; stated contrast: problem is NOT algebra BUT word problems; score 16 out of 20 (14 corrected away by 'sorry'); better than last week; either/or suggestion (Saturday practice batch OR 10 minutes reading daily), explicitly NOT both, reason: he'll burn out")

# 214 short negation under casual message, concert autographs
R(FN, {"task": "rewrite", "format": "message", "register": "casual",
       "transcript": "tell theo the band won't sign autographs after the show"},
  "Theo, the band won't sign autographs after the show.",
  {"format": "message", "must_include": ["Theo", "won't sign autographs", "after the show"], "min_negations": 1},
  "facts: band WON'T sign autographs after the show")

# 215 long co-working quote email, alternatives + condition + correction
R(CA, {"task": "rewrite", "format": "email", "sender": "Mirela", "recipient": "Ji-woo",
       "transcript": "reply to ji-woo about the private office um the small office for two people is six hundred fifty a month or the four person one is a thousand and fifty both include wifi and meeting room credits but parking is extra at eighty a month she can move in on the first of november or the fifteenth if she needs more time we ask for one month's deposit and a six sorry three month minimum term"},
  "Hi Ji-woo,\n\nThe small office for two people is 650 a month, or the four-person one is 1,050. Both include Wi-Fi and meeting room credits, but parking is extra at 80 a month. You can move in on November 1, or on November 15 if you need more time. We ask for one month's deposit and a three-month minimum term.\n\nBest,\nMirela",
  {"format": "email", "numbers": ["650", "1,050", "80", "1", "15"], "numbers_one_of": [["1,050", "1050"]], "must_not_include": ["six-month", "6-month"],
   "must_include": ["Ji-woo", "two people is 650 a month", "four-person one is 1,050", "Wi-Fi and meeting room credits", "parking is extra at 80 a month", "November 1", "November 15 if you need more time", "one month's deposit", "three-month minimum term", "Mirela"]},
  "facts: genuine alternative: two-person office 650/month OR four-person 1,050 (no currency spoken); both include Wi-Fi + meeting credits; parking extra 80/month; move-in November 1, or November 15 IF she needs more time (condition scoped to the 15th); one month's deposit; three-month minimum (six corrected away by 'sorry')")

# 216 short count correction, concert matinee tickets
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "for the matinee two adults and one child sorry two children"},
  "For the matinee, two adults and two children.",
  {"must_include": ["matinee", "two adults and two children"], "must_not_include": ["one child"]},
  "facts: 'sorry' corrects the count: two adults and two children (one child corrected away)")

# 217 long crew briefing, capacity + times + negations, concert
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "briefing for tonight's crew um capacity is four thousand two hundred and we stop scanning at that number even if there's still a queue the support act is on at seven forty and the headliner at nine no pyro this time the fire marshal didn't sign off on it so don't let the band's crew set anything up near the stage lip and water is free at the bar for anyone who asks we've got six first aiders on site and two of them are by the mosh pit"},
  "Briefing for tonight's crew: capacity is 4,200, and we stop scanning at that number, even if there's still a queue. The support act is on at 7:40 and the headliner at 9. No pyro this time; the fire marshal didn't sign off on it, so don't let the band's crew set anything up near the stage lip. Water is free at the bar for anyone who asks. We've got six first aiders on site, and two of them are by the mosh pit.",
  {"numbers": ["4,200", "7:40", "9"], "numbers_one_of": [["4,200", "4200"]],
   "must_include": ["capacity is 4,200", "even if there's still a queue", "support act is on at 7:40", "headliner at 9", "No pyro", "didn't sign off", "don't let the band's crew set anything up near the stage lip", "Water is free", "six first aiders", "two of them are by the mosh pit"], "min_negations": 3},
  "facts: capacity 4,200, stop scanning at that number even if a queue remains; support act 7:40, headliner 9; NO pyro (fire marshal DIDN'T sign off), DON'T let band's crew set up near stage lip; free water at bar on request; six first aiders, two by the mosh pit")

# 218 medium formal email, validity + restriction, permits office, en-gb
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "locale": "en-gb", "sender": "Clara",
       "transcript": "inform the applicant that the demolition permit is valid for ninety days only and work cannot start before the neighbour notification period ends on the twelfth"},
  "Hello,\n\nThe demolition permit is valid for 90 days only, and work cannot start before the neighbour notification period ends on the 12th.\n\nRegards,\nClara",
  {"format": "email", "numbers": ["90", "12"], "must_include": ["demolition permit", "90 days only", "cannot start before the neighbour notification period ends on the 12th", "Clara"], "min_negations": 1},
  "facts: permit valid 90 days ONLY; work can NOT start before the neighbour notification period ends on the 12th; formal, no name -> 'Hello,'; no added offers")

# 219 medium bus rules, tuition centre, en-in
R(FN, {"task": "cleanup", "header_style": "full", "locale": "en-in",
       "transcript": "uh the bus pickup for the saturday batch is at eight fifteen sharp the driver won't wait more than five minutes and there's no drop service on saturdays so parents have to collect by one"},
  "The bus pickup for the Saturday batch is at 8:15 sharp. The driver won't wait more than 5 minutes, and there's no drop service on Saturdays, so parents have to collect by 1.",
  {"numbers": ["8:15", "5", "1"], "must_include": ["8:15 sharp", "won't wait more than 5 minutes", "no drop service on Saturdays", "collect by 1"], "min_negations": 2},
  "facts: Saturday pickup 8:15 sharp; driver WON'T wait more than 5 minutes; NO drop service on Saturdays; parents collect by 1")

# 220 medium account hold, negation + hedge under rewrite message, ride-share
R(FN, {"task": "rewrite", "format": "message",
       "instruction": "clear and calm, keep 'on hold, not deactivated' exactly",
       "transcript": "tell mateo his account is on hold not deactivated it's because his licence expired last week once he uploads the new one it should be back within twenty four hours"},
  "Mateo, your account is on hold, not deactivated. It's because your licence expired last week. Once you upload the new one, it should be back within 24 hours.",
  {"format": "message", "numbers": ["24"], "must_include": ["Mateo", "on hold, not deactivated", "licence expired last week", "should be back within 24 hours"], "min_negations": 1},
  "facts: account on hold, NOT deactivated (wording kept exactly as instructed); reason: licence expired last week; hedge 'should' kept: back within 24 hours once the new licence is uploaded",
  pos="before")

# 221 medium merch rules, negations + limit, concert
R(FN, {"task": "cleanup",
       "transcript": "merch is card only no cash and the tour hoodies are limited to one per person while stocks last so don't hold any back for friends"},
  "Merch is card only, no cash, and the tour hoodies are limited to one per person while stocks last, so don't hold any back for friends.",
  {"must_include": ["card only, no cash", "one per person", "while stocks last", "don't hold any back for friends"], "min_negations": 2},
  "facts: card only, NO cash; hoodies limited to one per person while stocks last; DON'T hold any back for friends")

# 222 medium negation vs record, used car history
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the seller says the car's never been in an accident but the report shows a minor claim from two thousand twenty two so we should ask him about that"},
  "The seller says the car's never been in an accident, but the report shows a minor claim from 2022, so we should ask him about that.",
  {"numbers": ["2022"], "must_include": ["never been in an accident", "minor claim from 2022", "ask him about that"], "min_negations": 1},
  "facts: seller claims NEVER in an accident (his claim, kept as reported); report shows a minor claim from 2022; should ask him")

# 223 medium three-way question + weekday correction under rewrite message, co-working
R(CA, {"task": "rewrite", "format": "message",
       "transcript": "ask bongani whether he wants the corner desk the window desk or the one by the plants and remind him his trial ends on thursday sorry on wednesday"},
  "Bongani, do you want the corner desk, the window desk or the one by the plants? Your trial ends on Wednesday.",
  {"format": "message", "must_include": ["Bongani", "corner desk", "window desk", "the one by the plants", "?", "trial ends on Wednesday"], "must_not_include": ["Thursday"]},
  "facts: three-way alternative kept as a question (corner desk, window desk, desk by the plants); trial ends Wednesday (Thursday corrected away by 'sorry on')")

# 224 medium alternative rooms + negation, research lab seminar
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "the seminar is in lecture theatre two or three we'll know tomorrow but it's definitely not in the main hall"},
  "The seminar is in Lecture Theatre 2 or 3; we'll know tomorrow, but it's definitely not in the main hall.",
  {"numbers": ["2", "3"], "must_include": ["Lecture Theatre 2 or 3", "we'll know tomorrow", "definitely not in the main hall"], "min_negations": 1},
  "facts: genuine alternative Lecture Theatre 2 OR 3, both kept, confirmed tomorrow; definitely NOT in the main hall")

# 225 long lab channel message, weekday + shelf corrections + either/or + rule, research lab
R(CA, {"task": "rewrite", "format": "message",
       "instruction": "tidy this for the lab channel as one message and keep only the corrected day and shelf",
       "transcript": "hey everyone the freezer audit is monday no wait tuesday the twenty first um each of you needs to clear out anything unlabelled from shelf two sorry shelf four by friday and update the inventory sheet if you've got boxes older than two years either move them to the long term storage room or bin them clara has the key for that room and please don't touch the boxes on the top shelf those belong to the other group"},
  "Hey everyone, the freezer audit is on Tuesday the 21st. Each of you needs to clear out anything unlabelled from shelf 4 by Friday and update the inventory sheet. If you've got boxes older than two years, either move them to the long-term storage room or bin them; Clara has the key for that room. Please don't touch the boxes on the top shelf; those belong to the other group.",
  {"format": "message", "numbers": ["21", "4"], "must_not_include": ["Monday", "shelf 2"],
   "must_include": ["Hey everyone", "Tuesday the 21st", "unlabelled", "shelf 4 by Friday", "inventory sheet", "older than two years", "either move them to the long-term storage room or bin them", "Clara has the key", "don't touch the boxes on the top shelf"], "min_negations": 1},
  "facts: audit Tuesday the 21st (Monday corrected away by 'no wait'); clear unlabelled items from shelf 4 (shelf 2 corrected away by 'sorry') by Friday and update inventory; conditional either/or for boxes older than two years: move to long-term storage OR bin; Clara has the key; DON'T touch top-shelf boxes (other group's), standing rule in its own sentence; dictated 'hey everyone' kept")
