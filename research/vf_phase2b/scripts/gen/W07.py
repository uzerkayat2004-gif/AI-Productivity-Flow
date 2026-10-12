"""W07 stage 1 generator: bucket=email (slices email, multi_constraint).

Domains: architecture firm, e-commerce seller, HR/recruiting, print shop.
Re-running reproduces research/vf_phase2b/data/batches/W07_s1.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W07"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

rows = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def add(slice_, request, target, assertions, *, pos="structured", cx=0, note=None, waivers=None):
    n = len(rows) + 1
    a = dict(assertions)
    a.setdefault("format", "email")
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(request["transcript"])}
    rows.append(rec(f"TC-{WID}-{n:03d}", "email", slice_, request, target, a, f"w07-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers, meta=meta))


R = dict(task="rewrite", format="email")

# ------------------------------------------------------------------ email slice (30)

add("email", dict(R, recipient="Manish", sender="Kavya",
                  transcript="let manish know the revised floor plans are attached and the only change is uh the kitchen moved to the north side"),
    "Hi Manish,\n\nThe revised floor plans are attached. The only change is that the kitchen has moved to the north side.\n\nBest,\nKavya",
    {"must_include": ["Manish", "revised floor plans", "north side", "Kavya"]},
    note="facts: only change = kitchen moved to north side; floor plans attached")

add("email", dict(R, transcript="um tell the customer their order shipped today and the tracking number is BX4471902"),
    "Hi,\n\nYour order shipped today. The tracking number is BX4471902.",
    {"must_include": ["BX4471902", "today"]},
    note="facts: shipped today; tracking BX4471902 verbatim; no sender so no name")

add("email", dict(R, recipient="Oliver", sender="Rania", tone="warm",
                  transcript="uh let oliver know he made it to the final round and it's on thursday at eleven"),
    "Hi Oliver,\n\nI'm happy to let you know that you've made it to the final round. It will be on Thursday at 11.\n\nBest,\nRania",
    {"must_include": ["final round", "Thursday", "Rania"], "numbers": ["11"], "must_not_include": ["a.m.", "p.m."]},
    note="facts: final round Thursday at 11 (no a.m./p.m. spoken, none added)")

add("email", dict(R, recipient="Camille", register="formal", header_style="full",
                  transcript="so the five hundred brochures are printed but the uh the matte lamination adds two days so pickup is wednesday not monday"),
    "Dear Camille,\n\nThe 500 brochures have been printed. However, the matte lamination adds 2 days, so pickup is on Wednesday, not Monday.",
    {"must_include": ["matte lamination", "Wednesday"], "numbers": ["500", "2"], "min_negations": 1},
    note="facts: 500 brochures printed; lamination adds 2 days; pickup Wednesday NOT Monday; no sender so no sign-off")

add("email", dict(R, recipient="Peter", sender="Sun-hee", header_style="full",
                  transcript="hi peter so quick update on the lakeview house um we went to the site on tuesday and the soil report came back fine so the foundation design doesn't need to change. the bigger thing is the permit, the city wants one more drawing showing the drainage plan and we can't submit until that's done. our structural engineer said she might have it ready by the twentieth but she wasn't sure. on the fees, the extra drawing is billed at eighteen hundred dollars, that's on top of the original quote. and uh can you confirm whether you still want the skylight in the main bedroom because it affects the roof framing"),
    "Hi Peter,\n\nHere's a quick update on the Lakeview house. We visited the site on Tuesday, and the soil report came back fine, so the foundation design doesn't need to change.\n\nThe bigger issue is the permit. The city wants one more drawing showing the drainage plan, and we can't submit until that's done. Our structural engineer said she might have it ready by the 20th, but she wasn't sure.\n\nOn fees, the extra drawing is billed at $1,800, on top of the original quote.\n\nCould you also confirm whether you still want the skylight in the main bedroom? It affects the roof framing.\n\nBest,\nSun-hee",
    {"must_include": ["Lakeview", "drainage plan", "skylight", "original quote", "Sun-hee"], "numbers": ["20", "1,800"], "min_negations": 3,
     "must_not_include": ["will have it"]},
    note="facts: site visit Tuesday; foundation unchanged; can't submit permit until drainage drawing done; engineer MIGHT be ready by 20th, wasn't sure (hedge kept); extra drawing $1,800 on top of quote; open question re skylight")

add("email", dict(R, register="casual",
                  transcript="tell rania the return label's in the attachment and she can drop the parcel at any post office"),
    "Hi Rania,\n\nThe return label's attached, and you can drop the parcel off at any post office.",
    {"must_include": ["Rania", "return label", "any post office"]},
    note="facts: recipient named in transcript (Rania); label attached; any post office")

add("email", dict(R, register="formal", sender="Zubair", locale="en-in",
                  transcript="please inform the candidate, um, that we're offering them the role of operations analyst at a fixed salary of eight lakh rupees per year. the offer is valid until the fifteenth of november. joining is subject to background verification, so uh they shouldn't resign from their current job until we confirm that's cleared. the role is based in our surat office, five days a week, no hybrid option for the first six months"),
    "Hello,\n\nWe are offering you the role of Operations Analyst at a fixed salary of ₹8,00,000 per year. The offer is valid until 15 November.\n\nJoining is subject to background verification, so you should not resign from your current job until we confirm that it has been cleared.\n\nThe role is based in our Surat office, five days a week, with no hybrid option for the first 6 months.\n\nRegards,\nZubair",
    {"must_include": ["Operations Analyst", "background verification", "Surat", "Zubair"], "numbers": ["8,00,000", "15", "6"], "min_negations": 2},
    note="facts: ₹8,00,000 per year (rupees spoken); valid until 15 November; joining conditional on background verification; don't resign until cleared; Surat office 5 days/week; no hybrid for first 6 months")

add("email", dict(R, header_style="full",
                  transcript="can you send the final logo file as a pdf with fonts outlined before we print thanks"),
    "Hi,\n\nCould you send the final logo file as a PDF with the fonts outlined before we print?\n\nThanks,",
    {"must_include": ["logo file", "PDF", "outlined", "Thanks,"]},
    note="facts: request only; closing 'Thanks' was dictated, no name (no sender)")

add("email", dict(R, recipient="Kavya", sender="Manish", tone="confident",
                  transcript="kavya we need to move the restock order from two hundred units to three fifty because the sale week starts on the third and uh we can't run out of the medium size again"),
    "Hi Kavya,\n\nWe need to increase the restock order from 200 units to 350. The sale week starts on the 3rd, and we can't run out of the medium size again.\n\nBest,\nManish",
    {"must_include": ["restock", "medium size"], "numbers": ["200", "350", "3"], "min_negations": 1},
    note="facts: restock 200 -> 350 units; sale week starts on the 3rd; can't run out of medium again")

add("email", dict(R, sender="Rania",
                  transcript="hi everyone so for next week's interviews for the senior designer role we have four candidates, um monday and tuesday, each slot is forty five minutes. please review the portfolios in the shared folder before your slot, they're in the folder called design hiring q4. uh oliver is joining the panel instead of camille, camille's on leave. scoring sheets need to be submitted the same day, not at the end of the week, because we want to make a decision by friday. and please don't discuss salary with candidates, that's handled by hr only"),
    "Hi everyone,\n\nFor next week's interviews for the Senior Designer role, we have four candidates across Monday and Tuesday. Each slot is 45 minutes.\n\nPlease review the portfolios in the shared folder before your slot. They're in the folder called Design Hiring Q4.\n\nOliver is joining the panel instead of Camille, who is on leave.\n\nScoring sheets need to be submitted the same day, not at the end of the week, because we want to make a decision by Friday. Please don't discuss salary with candidates; that's handled by HR only.\n\nBest,\nRania",
    {"must_include": ["Senior Designer", "Design Hiring Q4", "Oliver", "Camille", "Friday", "salary", "HR only"], "numbers": ["45"], "min_negations": 2},
    note="facts: 4 candidates Mon+Tue; 45-min slots; folder 'design hiring q4'; Oliver replaces Camille (on leave); scores same day NOT end of week; decision by Friday; DON'T discuss salary, HR only")

add("email", dict(R, recipient="Zubair", length="shorter",
                  transcript="um just wanted to let you know that uh the meeting with the planning office has been pushed to friday at two thirty"),
    "Hi Zubair,\n\nThe meeting with the planning office has been moved to Friday at 2:30.",
    {"must_include": ["planning office", "Friday"], "numbers": ["2:30"]},
    note="facts: planning office meeting moved to Friday 2:30; no a.m./p.m. added")

add("email", dict(R, tone="empathetic",
                  transcript="tell the customer i understand the mug arrived cracked and we're sending a replacement at no cost, they don't need to return the broken one"),
    "Hi,\n\nI understand that your mug arrived cracked. We're sending you a replacement at no cost, and you don't need to return the broken one.",
    {"must_include": ["cracked", "replacement", "no cost"], "min_negations": 2, "must_not_include": ["sorry", "apolog"]},
    note="facts: replacement at no cost (spoken commitment); no need to return broken mug; no apology was spoken")

add("email", dict(R, recipient="Sun-hee", sender="Peter", tone="persuasive",
                  transcript="sun-hee if you order the business cards together with the letterheads the setup fee is waived, that saves you sixty dollars, but the combined order has to be confirmed by thursday"),
    "Hi Sun-hee,\n\nIf you order the business cards together with the letterheads, the setup fee is waived, which saves you $60. The combined order does need to be confirmed by Thursday.\n\nBest,\nPeter",
    {"must_include": ["business cards", "letterheads", "setup fee", "Thursday"], "numbers": ["60"]},
    note="facts: condition = order cards WITH letterheads -> setup fee waived, saves $60; combined order must be confirmed by Thursday")

add("email", dict(R, register="casual", locale="en-in", header_style="full",
                  transcript="hey can you share your notice period and current ctc when you get a chance"),
    "Hi,\n\nCould you share your notice period and current CTC when you get a chance?",
    {"must_include": ["notice period", "CTC"], "ends_with_question": True})

add("email", dict(R, recipient="Oliver", sender="Camille", register="formal", header_style="full",
                  transcript="so the last shipment of mailer boxes um the twelve by nine ones, about three hundred of them came in with the print smudged. we can't use them for customer orders. we'd like either a replacement batch or a credit on the next invoice, whichever is faster for you. also going forward we need the boxes delivered by the twenty fifth of each month, not the end of the month, because our sale cycle starts on the first. please send photos of the corrected print proof before the next run"),
    "Dear Oliver,\n\nIn the last shipment of mailer boxes, approximately 300 of the 12 by 9 boxes arrived with smudged print. We cannot use them for customer orders. We would like either a replacement batch or a credit on the next invoice, whichever is faster for you.\n\nGoing forward, we need the boxes delivered by the 25th of each month, not the end of the month, because our sale cycle starts on the 1st.\n\nPlease send photos of the corrected print proof before the next run.\n\nRegards,\nCamille",
    {"must_include": ["replacement batch", "credit", "print proof", "Camille"], "numbers": ["300", "12", "9", "25", "1"], "min_negations": 2},
    note="facts: about 300 of the 12x9 boxes smudged; can't use them; replacement OR credit (both kept), whichever faster; deliver by 25th NOT end of month; cycle starts 1st; photos of corrected proof before next run")

add("email", dict(R, transcript="rania the 3d renders for the courtyard are uploaded to the drive cheers"),
    "Hi Rania,\n\nThe 3D renders for the courtyard are uploaded to the drive.\n\nCheers,",
    {"must_include": ["Rania", "3D renders", "courtyard", "Cheers,"]},
    note="facts: closing 'cheers' dictated; no sender so no name")

add("email", dict(R, header_style="full",
                  transcript="subject line banner order update. the two vinyl banners are ready but the large one is uh three by six feet not three by eight like the quote said so we'll reprint it free"),
    "Subject: Banner order update\n\nHi,\n\nThe two vinyl banners are ready, but the large one is 3 by 6 feet, not 3 by 8 as the quote said, so we'll reprint it free of charge.",
    {"must_include": ["Subject: Banner order update", "vinyl banners", "reprint"], "numbers": ["3", "6", "8"], "min_negations": 1},
    note="facts: subject dictated; large banner is 3x6 ft NOT 3x8 per quote; spoken commitment to reprint free")

add("email", dict(R, recipient="Peter", sender="Kavya", tone="empathetic",
                  transcript="peter we've decided not to move forward with your application for the account manager role. honestly it was a close call. the panel really liked your client examples and your presentation, but they're looking for someone with more b2b experience, especially with enterprise accounts. we'll keep your cv on file for six months, and if a similar role opens up in that time we'll reach out to you directly"),
    "Hi Peter,\n\nWe've decided not to move forward with your application for the Account Manager role. Honestly, it was a close call. The panel really liked your client examples and your presentation, but they're looking for someone with more B2B experience, especially with enterprise accounts.\n\nWe'll keep your CV on file for 6 months, and if a similar role opens up in that time, we'll reach out to you directly.\n\nBest,\nKavya",
    {"must_include": ["Account Manager", "B2B", "enterprise accounts", "CV on file"], "numbers": ["6"], "min_negations": 1,
     "must_not_include": ["sorry", "apolog"]},
    note="facts: not moving forward; close call; more B2B/enterprise experience wanted; CV kept 6 months; reach out only IF a similar role opens (condition kept); no apology spoken")

add("email", dict(R, register="formal",
                  transcript="the discount code welcome10 expires at midnight on sunday"),
    "Hello,\n\nThe discount code welcome10 expires at midnight on Sunday.",
    {"must_include": ["welcome10", "midnight", "Sunday"]},
    note="facts: code welcome10 kept verbatim; expires midnight Sunday")

add("email", dict(R, recipient="Camille", sender="Manish", tone="friendly", length="longer", locale="en-gb",
                  transcript="camille the client approved the timber facade so we can order samples, the budget for samples is four hundred pounds"),
    "Hi Camille,\n\nThe client has approved the timber facade, so we can now go ahead and order samples. The budget we have for the samples is £400.\n\nBest,\nManish",
    {"must_include": ["timber facade", "samples"], "numbers": ["400"]},
    note="facts: client approved timber facade; can order samples; samples budget £400 (pounds spoken); longer adds wording only")

add("email", dict(task="rewrite", instruction="write this as a short email to the candidate",
                  transcript="the assessment link is in your inbox and you have forty eight hours to finish it once you open it"),
    "Hi,\n\nThe assessment link is in your inbox. You have 48 hours to finish it once you open it.",
    {"must_include": ["assessment link", "once you open it"], "numbers": ["48"]},
    pos="after", cx=1,
    note="facts: 48 hours counted from when they open it (condition kept)")

add("email", dict(R, sender="Zubair", context="email", locale="en-in",
                  transcript="uh the invoice for the flyer job is attached it's twelve thousand four hundred rupees and payment is due within fifteen days"),
    "Hi,\n\nThe invoice for the flyer job is attached. The amount is ₹12,400, and payment is due within 15 days.\n\nRegards,\nZubair",
    {"must_include": ["invoice", "flyer job"], "numbers": ["12,400", "15"]},
    note="facts: invoice ₹12,400 (rupees spoken); due within 15 days")

add("email", dict(R, sender="Sun-hee", register="casual", tone="friendly",
                  transcript="hey team so a few updates for the store. sales last week were up about eighteen percent, mostly from the linen tote bags. um the supplier for the ceramic planters is raising prices by ten percent from december so we might have to raise ours too, i haven't decided yet. and the photographer can only reshoot the product photos on the ninth or the tenth so let me know which day works. oh and please stop offering free shipping on orders under fifty dollars, that's not working for us"),
    "Hi team,\n\nA few updates for the store.\n\nSales last week were up about 18%, mostly from the linen tote bags.\n\nThe supplier for the ceramic planters is raising prices by 10% from December, so we might have to raise ours too. I haven't decided yet.\n\nThe photographer can only reshoot the product photos on the 9th or the 10th, so let me know which day works.\n\nAlso, please stop offering free shipping on orders under $50. That's not working for us.\n\nThanks,\nSun-hee",
    {"must_include": ["linen tote bags", "ceramic planters", "December", "free shipping", "Sun-hee"], "numbers": ["18", "10", "9", "50"], "min_negations": 2},
    note="facts: sales up ABOUT 18% (tote bags); planter supplier +10% from December; we MIGHT raise, not decided; reshoot 9th OR 10th (both kept); stop free shipping under $50")

add("email", dict(R, recipient="Oliver", header_style="full",
                  transcript="the site meeting tomorrow is cancelled due to rain"),
    "Hi Oliver,\n\nThe site meeting tomorrow is cancelled due to rain.",
    {"must_include": ["site meeting", "tomorrow", "cancelled", "rain"]})

add("email", dict(R, recipient="Zubair", sender="Oliver", tone="confident", header_style="full",
                  transcript="zubair i think we should close the backend role this week, uh we've got two strong finalists and the hiring manager prefers the second one but only if she can start before january"),
    "Hi Zubair,\n\nI think we should close the backend role this week. We have two strong finalists, and the hiring manager prefers the second one, but only if she can start before January.\n\nBest,\nOliver",
    {"must_include": ["I think", "backend role", "two strong finalists", "only if", "January"]},
    note="facts: hedge 'I think' kept despite confident tone; preference for 2nd finalist only IF start before January")

add("email", dict(R, recipient="Kavya", tone="warm",
                  transcript="thanks so much for the repeat order kavya, the calendars are going to print on monday"),
    "Hi Kavya,\n\nThank you so much for the repeat order. The calendars are going to print on Monday.",
    {"must_include": ["repeat order", "calendars", "Monday"]},
    note="facts: calendars print Monday; no sender so no sign-off")

add("email", dict(R, sender="Manish", length="shorter",
                  transcript="hi so um i'm writing because uh we noticed that the the last two payouts from the marketplace were short by like around two hundred and ten dollars in total and we're not sure why, could you could you check whether the commission rate changed"),
    "Hi,\n\nThe last two payouts from the marketplace were short by around $210 in total, and we're not sure why. Could you check whether the commission rate changed?\n\nBest,\nManish",
    {"must_include": ["payouts", "commission rate"], "numbers": ["210"], "min_negations": 1},
    note="facts: last two payouts short by around $210 total; not sure why; question about commission rate")

add("email", dict(R, recipient="Rania", register="formal", locale="en-gb", header_style="full",
                  transcript="the design fee for stage two is fifteen percent of construction cost and is payable in three instalments"),
    "Dear Rania,\n\nThe design fee for Stage 2 is 15% of the construction cost and is payable in three instalments.",
    {"must_include": ["design fee", "construction cost", "three instalments"], "numbers": ["2", "15"]},
    note="facts: Stage 2 fee = 15% of construction cost, three instalments")

add("email", dict(R, sender="Camille", register="formal",
                  transcript="subject proof approval needed for the annual report. hi peter the proofs for the annual report are attached. there are two things we need from you. the cover photo is low resolution so it may print blurry, if you have a higher resolution version please send it. and page fourteen has a chart that runs off the edge, we can shrink it or move it to page fifteen, your choice. we need approval by wednesday at noon to keep the delivery date of the twenty eighth. if approval comes later the delivery moves by at least three working days"),
    "Subject: Proof approval needed for the annual report\n\nDear Peter,\n\nThe proofs for the annual report are attached. There are two things we need from you.\n\nThe cover photo is low resolution, so it may print blurry. If you have a higher-resolution version, please send it.\n\nPage 14 has a chart that runs off the edge. We can shrink it or move it to page 15, whichever you prefer.\n\nWe need your approval by Wednesday at noon to keep the delivery date of the 28th. If approval comes later, delivery moves by at least 3 working days.\n\nRegards,\nCamille",
    {"must_include": ["Subject: Proof approval needed for the annual report", "Peter", "may print blurry", "Wednesday at noon", "Camille"],
     "numbers": ["14", "15", "28", "3"]},
    note="facts: subject dictated; cover photo MAY print blurry; p.14 chart: shrink OR move to p.15 (both kept, client's choice); approval by Wednesday noon keeps 28th delivery; IF later, at least 3 working days delay")

add("email", dict(R, recipient="Sun-hee", sender="Oliver", register="formal",
                  transcript="sun-hee the a three posters for the exhibition are uh delayed by a day because the printer jammed, they'll now be ready on saturday morning instead of friday"),
    "Dear Sun-hee,\n\nThe A3 posters for the exhibition have been delayed by a day because the printer jammed. They will now be ready on Saturday morning instead of Friday.\n\nRegards,\nOliver",
    {"must_include": ["A3 posters", "exhibition", "Saturday morning", "instead of Friday"], "numbers": ["3"],
     "must_not_include": ["sorry", "apolog"]},
    note="facts: A3 posters delayed one day (printer jam); ready Saturday morning instead of Friday; no apology spoken")

# ------------------------------------------------------------------ multi_constraint slice (10)

add("multi_constraint", dict(R, recipient="Peter", tone="friendly", locale="en-in",
                             instruction="make this a professional email but keep it friendly, don't add any promises, and keep the exact deadline",
                             transcript="so we need the signed contract and the first payment of two lakh rupees by the thirtieth before we can start the drawings"),
    "Hi Peter,\n\nTo get started on the drawings, we need the signed contract and the first payment of ₹2,00,000 by the 30th.",
    {"must_include": ["signed contract", "first payment", "drawings"], "numbers": ["2,00,000", "30"], "must_not_include": ["will", "promise"]},
    pos="before", cx=3,
    note="facts: contract + first payment ₹2,00,000 (rupees spoken) needed by the 30th before drawings start; no promises added")

add("multi_constraint", dict(task="rewrite",
                             instruction="turn this into a short formal email and keep both delivery options",
                             transcript="um customers can choose either standard delivery which takes five to seven days or express which is next day for twelve dollars"),
    "Hello,\n\nCustomers may choose either standard delivery, which takes 5 to 7 days, or express delivery, which is next day for $12.",
    {"must_include": ["standard delivery", "express", "next day"], "numbers": ["5", "7", "12"]},
    pos="after", cx=3,
    note="facts: alternative kept: standard 5-7 days OR express next day for $12")

add("multi_constraint", dict(R, recipient="Oliver", sender="Kavya", tone="warm",
                             instruction="leave out the part about the salary band and keep the start date exactly",
                             transcript="oliver we'd love to have you join on the fourth of november, the salary band we discussed is still the same, uh please bring your signed offer letter on the day"),
    "Hi Oliver,\n\nWe'd love to have you join us on November 4. Please bring your signed offer letter on the day.\n\nBest,\nKavya",
    {"must_include": ["November 4", "signed offer letter"], "numbers": ["4"], "must_not_include": ["salary", "band"]},
    pos="before", cx=3,
    note="facts: start date November 4 exact; salary band sentence dropped ONLY because instruction asked; offer letter on the day")

add("multi_constraint", dict(task="rewrite",
                             instruction="make it an email to Zubair, more confident, keep the conditional exactly and don't add a sign-off",
                             transcript="if the paper stock arrives by tuesday we can deliver the menus on thursday otherwise it'll be monday"),
    "Hi Zubair,\n\nIf the paper stock arrives by Tuesday, we can deliver the menus on Thursday. Otherwise, it'll be Monday.",
    {"must_include": ["Zubair", "If the paper stock arrives by Tuesday", "Thursday", "Otherwise", "Monday"], "must_not_include": ["Best,", "Regards,", "Thanks,"]},
    pos="after", cx=4,
    note="facts: condition kept: stock by Tuesday -> Thursday delivery, otherwise Monday; recipient from instruction; no sign-off")

add("multi_constraint", dict(R, register="formal", length="shorter", sender="Rania", locale="en-gb", header_style="full",
                             instruction="keep every measurement exactly as I said",
                             transcript="okay so um regarding the extension, the planners have uh capped the height at six point five metres, so the roof garden idea is out unless we drop the floor level by about thirty centimetres. the side setback has to stay at one point two metres, that's not negotiable. i mean, i'd still like to explore the thirty centimetre option before we give up on it"),
    "Hello,\n\nThe planners have capped the height of the extension at 6.5 metres, so the roof garden idea is out unless we lower the floor level by about 30 centimetres. The side setback must stay at 1.2 metres; that is not negotiable.\n\nI would still like to explore the 30-centimetre option before we give up on it.\n\nRegards,\nRania",
    {"must_include": ["roof garden", "unless", "side setback", "metres"], "numbers": ["6.5", "30", "1.2"], "min_negations": 1},
    pos="before", cx=3,
    note="facts: height cap 6.5 m; roof garden out UNLESS floor lowered by ABOUT 30 cm; setback 1.2 m, not negotiable; speaker still wants to explore 30 cm option")

add("multi_constraint", dict(task="rewrite",
                             instruction="write this as a polite email to the courier, don't apologise for anything and keep the order numbers exactly",
                             transcript="the parcels for orders 1042 and 1058 were marked delivered but the customers never got them, we need you to open an investigation"),
    "Hi,\n\nThe parcels for orders 1042 and 1058 were marked as delivered, but the customers never received them. We need you to open an investigation, please.",
    {"must_include": ["investigation"], "numbers": ["1042", "1058"], "min_negations": 1, "must_not_include": ["sorry", "apolog"]},
    pos="after", cx=3,
    note="facts: orders 1042 and 1058 marked delivered, never received; request investigation; no apology")

add("multi_constraint", dict(R, recipient="Camille", sender="Manish", tone="persuasive", locale="en-in", header_style="full",
                             instruction="pitch the referral bonus but keep the amount and the 90-day condition exact, no exclamation marks",
                             transcript="camille we're running a referral bonus, anyone you refer who gets hired gets you thirty thousand rupees, paid after they complete ninety days"),
    "Hi Camille,\n\nWe're running a referral bonus. Anyone you refer who gets hired earns you ₹30,000, paid after they complete 90 days.\n\nBest,\nManish",
    {"must_include": ["referral bonus", "gets hired"], "numbers": ["30,000", "90"], "must_not_include": ["!"]},
    pos="before", cx=3,
    note="facts: ₹30,000 per hired referral (rupees spoken), paid only after 90 days completed; no exclamation marks")

add("multi_constraint", dict(task="rewrite",
                             instruction="turn this into a short email with the subject line Reprint schedule, keep the quantities exact",
                             transcript="we'll reprint the two hundred and fifty postcards on friday and the forty posters early next week"),
    "Subject: Reprint schedule\n\nHi,\n\nWe'll reprint the 250 postcards on Friday and the 40 posters early next week.",
    {"must_include": ["Subject: Reprint schedule", "Friday", "early next week"], "numbers": ["250", "40"]},
    pos="before", cx=3, waivers=["invented_subject"],
    note="facts: 250 postcards Friday, 40 posters early next week (spoken commitment 'we'll'); Subject requested by the [Instruction]. Waiver: invented_subject because the fact checker only scans the transcript for 'subject', not the instruction that asked for it")

add("multi_constraint", dict(R, recipient="Sun-hee", sender="Peter", tone="warm", length="longer",
                             instruction="don't add anything that wasn't said and keep both dates",
                             transcript="sun-hee the model's ready, can you come see it on the eighth or the eleventh"),
    "Hi Sun-hee,\n\nThe model is now ready for you to see. Would you be able to come and take a look at it on the 8th or the 11th?\n\nBest,\nPeter",
    {"must_include": ["model"], "numbers": ["8", "11"]},
    pos="after", cx=4,
    note="facts: model ready; alternative kept: 8th OR 11th; no times or places added")

add("multi_constraint", dict(R, sender="Kavya", header_style="full",
                             instruction="professional email to the supplier, keep my wording for the product names, keep the hedge about the reorder, and no bullet points",
                             transcript="hi zubair um so the bamboo cutlery set and the cork yoga block both sold out in like four days. we'll probably reorder both but uh the cork yoga block only if the unit price stays under three dollars. and can you send the updated price list for november, we're planning the holiday stock now and want to lock quantities before the end of the month"),
    "Hi Zubair,\n\nThe bamboo cutlery set and the cork yoga block both sold out in about 4 days. We'll probably reorder both, but the cork yoga block only if the unit price stays under $3.\n\nCould you send the updated price list for November? We're planning the holiday stock now and want to lock quantities before the end of the month.\n\nBest,\nKavya",
    {"must_include": ["bamboo cutlery set", "cork yoga block", "probably", "only if", "November", "holiday stock"], "numbers": ["4", "3"]},
    pos="before", cx=4,
    note="facts: both sold out in about 4 days; PROBABLY reorder both; yoga block ONLY IF unit price under $3; ask for November price list; lock quantities before month end")

save(OUT, rows)
print(len(rows), "records ->", OUT)

# ================================================================== STAGE 2 (TC-W07-101..240)
# New domains in addition to stage 1: SaaS onboarding, localization agency (the model never translates),
# university admissions office, gym membership desk. Greeting policy: formal -> "Dear <Name>," / "Hello,";
# neutral/casual -> "Hi <Name>," / "Hi,". Small counts: one-ten in words for plain counts unless the record
# already writes counts as digits (e.g. inside a priced line-item list); amounts/times/measurements digits.

OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
rows2 = []


def add2(slice_, request, target, assertions, *, pos="structured", cx=0, note=None, waivers=None):
    n = 101 + len(rows2)
    a = dict(assertions)
    a.setdefault("format", "email")
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(request["transcript"])}
    rows2.append(rec(f"TC-{WID}-{n:03d}", "email", slice_, request, target, a, f"w07-sc-{n:03d}",
                     author=WID, note=note, waivers=waivers, meta=meta))


F = dict(R, header_style="full")

# ------------------------------------------------------------------ s2 chunk 1 (101-140)

add2("email", dict(R, recipient="Noor", sender="Gustavo",
                   transcript="say yes to noor, the workspace migration can happen this weekend but uh only the projects, not the archived tickets, those come over the following week"),
     "Hi Noor,\n\nYes, the workspace migration can happen this weekend, but only the projects, not the archived tickets. Those come over the following week.\n\nBest,\nGustavo",
     {"must_include": ["Noor", "workspace migration", "this weekend", "only the projects", "archived tickets", "following week", "Gustavo"], "min_negations": 1},
     note="facts: reply content dictated (yes); migration this weekend for projects ONLY, NOT archived tickets; archived tickets the following week")

add2("email", dict(F, recipient="Abhay", sender="Tamsin", register="formal", locale="en-gb",
                   transcript="this is a follow up on invoice PS-2291 for the exhibition banners, it was due on the fourth of september and uh we haven't received payment yet. the amount is six hundred and forty pounds. could you let us know when we can expect it"),
     "Dear Abhay,\n\nI am following up on invoice PS-2291 for the exhibition banners. It was due on 4 September, and we have not yet received payment. The amount is £640.\n\nCould you let us know when we can expect it?\n\nRegards,\nTamsin",
     {"must_include": ["PS-2291", "exhibition banners", "September", "Tamsin"], "numbers": ["4", "640"], "min_negations": 1},
     note="facts: unpaid invoice PS-2291 (verbatim); due 4 September; payment not received; £640 (pounds spoken); question about expected date; no late fee or deadline added")

add2("email", dict(R, recipient="Camille",
                   transcript="camille can we move our onboarding call from wednesday at ten thirty to thursday at three p m, same zoom link"),
     "Hi Camille,\n\nCould we move our onboarding call from Wednesday at 10:30 to Thursday at 3 p.m.? The Zoom link stays the same.",
     {"must_include": ["onboarding call", "Wednesday", "Thursday", "Zoom link"], "numbers": ["10:30", "3"], "must_not_include": ["10:30 a.m."]},
     note="facts: reschedule Wednesday 10:30 -> Thursday 3 p.m.; no a.m. added to 10:30; same Zoom link; it is a request (question)")

add2("email", dict(R, recipient="Oliver", sender="Kavya", register="formal",
                   transcript="oliver thank you for applying to the masters in urban design. after reviewing your application the committee is unable to offer you a place for the september intake. you're welcome to reapply for next year's intake, applications open in january"),
     "Dear Oliver,\n\nThank you for applying to the Master's in Urban Design. After reviewing your application, the committee is unable to offer you a place for the September intake.\n\nYou are welcome to reapply for next year's intake. Applications open in January.\n\nRegards,\nKavya",
     {"must_include": ["Urban Design", "unable to offer you a place", "September intake", "reapply", "January", "Kavya"], "must_not_include": ["sorry", "apolog", "regret"]},
     note="facts: admissions rejection for September intake; may reapply for next year's intake; applications open January; no apology/regret was spoken, none added")

add2("email", dict(R, recipient="Peter", sender="Sun-hee",
                   transcript="peter here's the quote for the conference print job. a few items, so two hundred lanyards at a dollar fifty each that's three hundred dollars, five hundred programs at eighty cents each so four hundred dollars, and twelve pull up banners at forty five dollars each which is five forty. uh total comes to one thousand two hundred and forty dollars before tax. the quote's valid for fourteen days"),
     "Hi Peter,\n\nHere's the quote for the conference print job:\n\n- 200 lanyards at $1.50 each: $300\n- 500 programs at 80 cents each: $400\n- 12 pull-up banners at $45 each: $540\n\nThe total comes to $1,240 before tax. The quote is valid for 14 days.\n\nBest,\nSun-hee",
     {"must_include": ["lanyards", "programs", "pull-up banners", "before tax", "Sun-hee"], "numbers": ["200", "1.50", "300", "500", "80", "400", "12", "45", "540", "1,240", "14"]},
     waivers=["number_missing", "number_invented"],
     note="facts: line items 200 lanyards x $1.50 = $300; 500 programs x 80 cents = $400; 12 banners x $45 = $540 ('five forty' = $540); total $1,240 before tax (arithmetic checks); valid 14 days; 3 items + cue 'a few items' -> bullets. Waivers: checker reads 'a dollar fifty' as 1 and 50 (target $1.50 is correct; all literals pinned in assertions.numbers)")

add2("email", dict(R, locale="en-gb",
                   transcript="hi so order 55103 from your warehouse arrived in the wrong colour, we ordered twenty forest green yoga mats and got grey ones. we need the correct ones before the twenty first"),
     "Hi,\n\nOrder 55103 from your warehouse arrived in the wrong colour. We ordered 20 forest green yoga mats and received grey ones. We need the correct ones before the 21st.",
     {"must_include": ["forest green", "grey", "colour"], "numbers": ["55103", "20", "21"]},
     note="facts: complaint; order 55103 verbatim; 20 forest green mats ordered, grey received; correct ones needed before the 21st; no refund demand or apology added")

add2("email", dict(R, sender="Zubair",
                   transcript="hi all, from monday the front desk opens at six a m instead of six thirty, and uh the towel service is paused for two weeks while the laundry contract is renewed. members can still bring their own towels"),
     "Hi all,\n\nFrom Monday, the front desk opens at 6 a.m. instead of 6:30. The towel service is paused for two weeks while the laundry contract is renewed. Members can still bring their own towels.\n\nBest,\nZubair",
     {"must_include": ["front desk", "towel service", "laundry contract", "bring their own towels", "Zubair"], "numbers": ["6", "6:30"]},
     note="facts: from Monday desk opens 6 a.m. instead of 6:30; towel service paused two weeks (laundry contract renewal); members can bring own towels")

add2("email", dict(R, sender="Tamsin",
                   transcript="i'm out of the office from the eighteenth to the twenty second with no access to email. for anything urgent on localization projects contact noor at noor@lingualane.co"),
     "Hi,\n\nI'm out of the office from the 18th to the 22nd with no access to email. For anything urgent on localization projects, contact Noor at noor@lingualane.co.\n\nBest,\nTamsin",
     {"must_include": ["out of the office", "noor@lingualane.co", "Noor", "Tamsin"], "numbers": ["18", "22"], "min_negations": 1},
     note="facts: out-of-office 18th to 22nd only (dictated dates, no month added); no email access; urgent localization -> Noor at noor@lingualane.co (verbatim)")

add2("email", dict(R, sender="Peter",
                   transcript="i want to introduce rania and gustavo. rania runs the onboarding team at our company and gustavo is the consultant who set up our billing integration. i think you two should talk about the invoice sync issue"),
     "Hi Rania and Gustavo,\n\nI'd like to introduce you to each other. Rania runs the onboarding team at our company, and Gustavo is the consultant who set up our billing integration. I think you two should talk about the invoice sync issue.\n\nBest,\nPeter",
     {"must_include": ["Rania", "Gustavo", "onboarding team", "billing integration", "I think", "invoice sync issue", "Peter"]},
     note="facts: introduction; Rania = runs onboarding team; Gustavo = consultant who set up billing integration; hedge 'I think' kept; no meeting/call proposed")

add2("email", dict(R, recipient="Camille",
                   transcript="thanks for covering the membership desk on saturday camille"),
     "Hi Camille,\n\nThank you for covering the membership desk on Saturday.",
     {"must_include": ["covering the membership desk", "Saturday"], "must_not_include": ["amazing", "great job", "appreciate"]},
     note="facts: thank-you only for covering the desk Saturday; no compliments added; no sender so no sign-off")

add2("email", dict(R, recipient="Oliver", length="shorter",
                   transcript="so um i just wanted to quickly check in and like see if you've had a chance to uh look at the localization quote we sent last week for the app strings, the one for the german and french versions. no pressure but we'd like to book the linguists soon"),
     "Hi Oliver,\n\nHave you had a chance to look at last week's localization quote for the German and French app strings? No pressure, but we'd like to book the linguists soon.",
     {"must_include": ["localization quote", "German", "French", "app strings", "linguists soon"], "min_negations": 1},
     note="facts: quote sent last week for German + French app strings; question whether he looked at it; 'no pressure' kept; want to book linguists soon (no date added)")

add2("email", dict(F, recipient="Abhay", sender="Noor",
                   transcript="abhay couple of updates before the open day on the ninth. the campus tour groups are capped at fifteen people each so we'll need at least six student guides, we've got four confirmed so far. um the engineering department wants their talk moved from eleven to eleven forty five because of a lab booking. the printed prospectuses haven't arrived, the printer says tuesday but i'm not counting on it, so let's have the pdf version ready on the tablets as a backup. oh and separately the scholarship panel still hasn't sent the shortlist, can you chase them"),
     "Hi Abhay,\n\nA couple of updates before the open day on the 9th.\n\nThe campus tour groups are capped at 15 people each, so we'll need at least six student guides. We have four confirmed so far.\n\nThe engineering department wants their talk moved from 11 to 11:45 because of a lab booking.\n\nThe printed prospectuses haven't arrived. The printer says Tuesday, but I'm not counting on it, so let's have the PDF version ready on the tablets as a backup.\n\nSeparately, the scholarship panel still hasn't sent the shortlist. Can you chase them?\n\nBest,\nNoor",
     {"must_include": ["open day", "student guides", "engineering department", "lab booking", "prospectuses", "PDF version", "scholarship panel", "shortlist", "Noor"],
      "numbers": ["9", "15", "11", "11:45"], "min_negations": 2},
     note="facts: open day on the 9th; groups capped at 15; need at least six guides, four confirmed; engineering talk 11 -> 11:45 (lab booking); prospectuses not arrived, printer says Tuesday but speaker doubts it; PDF on tablets as backup; scholarship panel 'still' hasn't sent shortlist; ask Abhay to chase")

add2("email", dict(R, recipient="Manish", sender="Kavya", locale="en-in",
                   transcript="manish your annual membership renewal is due on the fifth, the fee is eighteen thousand rupees, and if you renew before the first you get one month extra free"),
     "Hi Manish,\n\nYour annual membership renewal is due on the 5th. The fee is ₹18,000, and if you renew before the 1st, you get one extra month free.\n\nBest,\nKavya",
     {"must_include": ["annual membership renewal", "extra month free"], "numbers": ["5", "18,000", "1"]},
     note="facts: renewal due on the 5th; fee ₹18,000 (rupees spoken); condition: renew before the 1st -> one extra month free")

add2("email", dict(R,
                   transcript="hi so your trial ends on friday. to keep your data you need to pick a plan at app dot tasknest dot io slash billing before then"),
     "Hi,\n\nYour trial ends on Friday. To keep your data, you need to pick a plan at app.tasknest.io/billing before then.",
     {"must_include": ["trial ends on Friday", "keep your data", "app.tasknest.io/billing"]},
     note="facts: trial ends Friday; must pick plan before then to keep data; spoken URL written as app.tasknest.io/billing")

add2("email", dict(R, recipient="Gustavo", sender="Camille", register="formal", locale="en-gb",
                   transcript="gustavo attached are the revised section drawings, revision c. the stair width is now one point one metres and the handrail stays at nine hundred millimetres"),
     "Dear Gustavo,\n\nAttached are the revised section drawings, Revision C. The stair width is now 1.1 metres, and the handrail stays at 900 millimetres.\n\nRegards,\nCamille",
     {"must_include": ["revised section drawings", "Revision C", "stair width", "handrail", "metres", "millimetres"], "numbers": ["1.1", "900"]},
     note="facts: drawings attached, Revision C; stair width now 1.1 m; handrail unchanged at 900 mm")

add2("email", dict(R, tone="empathetic",
                   transcript="let them know we can't change the engraving once the order's in production, but we can cancel it for a full refund if they want"),
     "Hi,\n\nOnce an order is in production, we unfortunately can't change the engraving. We can, however, cancel it for a full refund if you'd like.",
     {"must_include": ["engraving", "in production", "cancel", "full refund", "if you'd like"], "min_negations": 1, "must_not_include": ["sorry", "apolog"]},
     note="facts: engraving can't change once in production; offer (spoken) = cancel for full refund IF they want; empathetic opener is wording only, no apology")

add2("email", dict(R, recipient="Noor", sender="Rania", tone="warm",
                   transcript="noor we'd like to offer you the localization project coordinator position. the written offer with all the details is attached, and we'd need your answer by next friday"),
     "Hi Noor,\n\nWe're delighted to offer you the Localization Project Coordinator position. The written offer with all the details is attached, and we'd need your answer by next Friday.\n\nBest,\nRania",
     {"must_include": ["Localization Project Coordinator", "written offer", "attached", "next Friday"], "must_not_include": ["salary", "benefits", "₹", "$"]},
     note="facts: job offer; details only in attached written offer (no salary/benefits invented); answer needed by next Friday")

add2("email", dict(R, register="casual",
                   transcript="hey peter the gym's sauna is closed tomorrow for repairs"),
     "Hi Peter,\n\nThe gym's sauna is closed tomorrow for repairs.",
     {"must_include": ["Peter", "sauna", "closed tomorrow", "repairs"]},
     note="facts: sauna closed tomorrow for repairs; casual register -> 'Hi Peter,'; no sender so no sign-off")

add2("email", dict(F, recipient="Sun-hee", sender="Tamsin", register="formal", locale="en-gb",
                   transcript="sun-hee we need to move your admissions interview from the fourteenth at nine fifteen to the sixteenth at two p m, the panel chair has a clash. it'll still be on teams using the same link"),
     "Dear Sun-hee,\n\nWe need to move your admissions interview from the 14th at 9:15 to the 16th at 2 p.m., as the panel chair has a clash. It will still be on Teams, using the same link.\n\nRegards,\nTamsin",
     {"must_include": ["admissions interview", "panel chair", "Teams", "same link"], "numbers": ["14", "9:15", "16", "2"], "must_not_include": ["9:15 a.m.", "sorry", "apolog"]},
     note="facts: interview moved from the 14th at 9:15 (no a.m. added) to the 16th at 2 p.m.; reason panel chair clash; still on Teams, same link; no apology")

add2("email", dict(R, recipient="Manish", sender="Gustavo",
                   transcript="manish the quote for localizing the help center into spanish and portuguese is as follows. spanish is thirty two thousand words at eight cents a word so two thousand five hundred and sixty dollars. portuguese same word count same rate so another two thousand five hundred sixty. plus a one off glossary setup of three hundred dollars. so the total is five thousand four hundred and twenty dollars and turnaround is about three weeks"),
     "Hi Manish,\n\nThe quote for localizing the help center into Spanish and Portuguese is as follows:\n\n- Spanish: 32,000 words at 8 cents a word, $2,560\n- Portuguese: 32,000 words at 8 cents a word, $2,560\n- One-off glossary setup: $300\n\nThe total is $5,420, and turnaround is about three weeks.\n\nBest,\nGustavo",
     {"must_include": ["help center", "Spanish", "Portuguese", "glossary setup", "about three weeks", "Gustavo"], "numbers": ["32,000", "8", "2,560", "300", "5,420"]},
     note="facts: Spanish 32,000 words x 8 cents = $2,560; Portuguese same count/rate = $2,560 ('another' = second $2,560); one-off glossary setup $300; total $5,420 (arithmetic checks); turnaround ABOUT three weeks; 3 items + cue 'as follows' -> bullets")

add2("email", dict(R, recipient="Abhay", sender="Oliver",
                   transcript="abhay thank you for turning the reprint around in one day, the client got the folders before their board meeting"),
     "Hi Abhay,\n\nThank you for turning the reprint around in one day. The client got the folders before their board meeting.\n\nBest,\nOliver",
     {"must_include": ["reprint", "one day", "folders", "board meeting", "Oliver"], "must_not_include": ["amazing", "fantastic", "lifesaver"]},
     note="facts: thanks for one-day reprint; client got folders before board meeting; no compliments added")

add2("email", dict(F, sender="Zubair", register="casual", locale="en-in",
                   transcript="hi this is the third time my payout's been held for verification this quarter. my seller id is SL-40981, i've already uploaded the gst certificate twice, please release the payout or tell me what's actually missing"),
     "Hi,\n\nThis is the third time my payout has been held for verification this quarter. My seller ID is SL-40981, and I've already uploaded the GST certificate twice. Please release the payout or tell me what's actually missing.\n\nThanks,\nZubair",
     {"must_include": ["third time", "SL-40981", "GST certificate", "twice", "release the payout", "Zubair"]},
     note="facts: complaint; third payout hold this quarter ('third time' is a fact); seller ID SL-40981 verbatim; GST certificate uploaded twice; release payout OR say what's missing (both kept)")

add2("email", dict(R, register="formal", locale="en-gb",
                   transcript="the deadline for submitting transcripts has been extended to the thirtieth of june"),
     "Hello,\n\nThe deadline for submitting transcripts has been extended to 30 June.",
     {"must_include": ["deadline", "transcripts", "extended", "June"], "numbers": ["30"]},
     note="facts: transcript deadline extended to 30 June; formal, no name -> 'Hello,'")

add2("email", dict(R, recipient="Rania", sender="Peter", length="longer",
                   transcript="rania the new pricing page is live"),
     "Hi Rania,\n\nI wanted to let you know that the new pricing page is now live.\n\nBest,\nPeter",
     {"must_include": ["new pricing page", "live", "Peter"]},
     note="facts: pricing page live; longer adds wording only, no new facts")

add2("email", dict(R, sender="Camille",
                   transcript="hi everyone the new class timetable starts next week. the changes are, spin moves to seven a m, yoga moves to six thirty p m, and the saturday bootcamp is cancelled. the rest of the timetable stays the same"),
     "Hi everyone,\n\nThe new class timetable starts next week. The changes are:\n\n- Spin moves to 7 a.m.\n- Yoga moves to 6:30 p.m.\n- The Saturday bootcamp is cancelled.\n\nThe rest of the timetable stays the same.\n\nBest,\nCamille",
     {"must_include": ["class timetable", "Spin", "Yoga", "Saturday bootcamp is cancelled", "stays the same", "Camille"], "numbers": ["7", "6:30"]},
     note="facts: timetable starts next week; spin 7 a.m.; yoga 6:30 p.m.; Saturday bootcamp cancelled; rest unchanged; dictated greeting 'hi everyone'; 3 items + cue 'the changes are' -> bullets")

add2("email", dict(R, recipient="Oliver", sender="Noor",
                   transcript="oliver welcome aboard. to get your team set up there are three steps. first invite your teammates from the members page. then connect your google calendar under integrations. finally import your existing tasks using the csv template, it's in the help center under imports. your onboarding call with me is on tuesday at four p m and if that doesn't work just reply with a time that does"),
     "Hi Oliver,\n\nWelcome aboard. To get your team set up, there are three steps:\n\n1. Invite your teammates from the Members page.\n2. Connect your Google Calendar under Integrations.\n3. Import your existing tasks using the CSV template. It's in the help center under Imports.\n\nYour onboarding call with me is on Tuesday at 4 p.m. If that doesn't work, just reply with a time that does.\n\nBest,\nNoor",
     {"must_include": ["Members page", "Google Calendar", "Integrations", "CSV template", "Imports", "Tuesday", "Noor"], "numbers": ["4"], "min_negations": 1},
     note="facts: three ordered steps (first/then/finally -> numbered): invite teammates, connect Google Calendar, import tasks via CSV template in help center; onboarding call Tuesday 4 p.m.; IF it doesn't work, reply with another time")

add2("email", dict(R, sender="Rania", register="formal", locale="en-gb",
                   transcript="regarding job number 7716, the business cards were cut about two millimetres off centre so the logo touches the edge on most of them. we need them reprinted, we're not paying for a second run"),
     "Hello,\n\nRegarding job number 7716, the business cards were cut about 2 millimetres off centre, so the logo touches the edge on most of them. We need them reprinted, and we are not paying for a second run.\n\nRegards,\nRania",
     {"must_include": ["business cards", "off centre", "logo touches the edge", "reprinted", "second run", "Rania"], "numbers": ["7716", "2"], "min_negations": 1},
     note="facts: complaint; job 7716; cut ABOUT 2 mm off centre; logo touches edge on most (not all); need reprint; NOT paying for second run")

# --- multi_constraint (128-140)

add2("multi_constraint", dict(R, recipient="Kavya", register="formal", locale="en-gb",
                              instruction="write this up as a polite email to the student, keep both dates, and don't make it sound like a rejection",
                              transcript="your application is complete but the scholarship decision is delayed, results come out on either the tenth or the seventeenth of march"),
     "Dear Kavya,\n\nYour application is complete. However, the scholarship decision has been delayed, and the results will come out on either 10 or 17 March.",
     {"must_include": ["application is complete", "scholarship decision", "delayed", "March"], "numbers": ["10", "17"], "must_not_include": ["unfortunately", "unable", "regret"]},
     pos="before", cx=3,
     note="facts: application complete; scholarship decision delayed; results on 10 OR 17 March (alternative kept); no rejection wording")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="shorter and more direct, but keep the hedge about the price, and sign it from Abhay",
                              transcript="so um basically the thing is we're probably going to have to raise the monthly membership from forty to forty five dollars starting january, i mean it's not final yet but i wanted to give you a heads up early"),
     "Hi,\n\nWe're probably going to raise the monthly membership from $40 to $45 starting January. It's not final yet, but I wanted to give you an early heads-up.\n\nBest,\nAbhay",
     {"must_include": ["probably", "monthly membership", "January", "not final yet", "Abhay"], "numbers": ["40", "45"], "min_negations": 1},
     pos="after", cx=3,
     note="facts: PROBABLY raising monthly membership $40 -> $45 from January ('dollars' covers both amounts); not final yet; sender name from instruction")

add2("multi_constraint", dict(R, register="formal",
                              instruction="formal email to the vendor, keep every line item and the total exactly, plain text only",
                              transcript="uh we'd like to confirm the order for the equipment. the items are, four rowing machines at nine hundred dollars each, ten kettlebell sets at a hundred and twenty each, and two cable stations at two thousand two hundred each. total nine thousand two hundred dollars. delivery to the north branch please"),
     "Hello,\n\nWe would like to confirm the order for the equipment. The items are:\n\n- 4 rowing machines at $900 each\n- 10 kettlebell sets at $120 each\n- 2 cable stations at $2,200 each\n\nThe total is $9,200. Please deliver to the north branch.",
     {"must_include": ["rowing machines", "kettlebell sets", "cable stations", "north branch"], "numbers": ["4", "900", "10", "120", "2", "2,200", "9,200"]},
     pos="before", cx=3,
     note="facts: 4 x $900, 10 x $120, 2 x $2,200 (dollars spoken once, $ applied to every price in the same list); total $9,200 (arithmetic checks); deliver to north branch; counts as digits throughout the priced list for consistency")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="make it an email to Tamsin, friendly, and keep it under 50 words",
                              transcript="so the french voiceover files came back from the studio and two of them have background noise, uh files fourteen and twenty three, so we've asked for retakes, they should be back thursday"),
     "Hi Tamsin,\n\nThe French voiceover files are back from the studio. Two of them, files 14 and 23, have background noise, so we've asked for retakes. They should be back on Thursday.",
     {"must_include": ["Tamsin", "French voiceover", "background noise", "retakes", "should be back", "Thursday"], "numbers": ["14", "23"], "max_words": 50},
     pos="after", cx=3,
     note="facts: two files (14 and 23) with background noise; retakes requested; SHOULD be back Thursday (hedge kept); under 50 words")

add2("multi_constraint", dict(R, recipient="Peter", sender="Kavya",
                              instruction="decline politely, no apology, and don't offer any alternatives",
                              transcript="we won't be able to sponsor the hackathon this year because our events budget is already committed"),
     "Hi Peter,\n\nUnfortunately, we won't be able to sponsor the hackathon this year, as our events budget is already committed.\n\nBest,\nKavya",
     {"must_include": ["sponsor the hackathon", "this year", "events budget", "already committed"], "min_negations": 1, "must_not_include": ["sorry", "apolog", "next year", "instead"]},
     pos="before", cx=3,
     note="facts: won't sponsor hackathon this year; reason events budget committed; no apology, no alternative offered")

add2("multi_constraint", dict(task="rewrite", format="email", locale="en-in",
                              instruction="professional email to Zubair, keep the rupee amounts and the condition about the advance exact, and add the subject line Payment schedule",
                              transcript="so for the website localization into hindi and tamil the total is one lakh twenty thousand rupees, we take forty thousand as advance and the rest on delivery, and we start only after the advance is received"),
     "Subject: Payment schedule\n\nHi Zubair,\n\nFor the website localization into Hindi and Tamil, the total is ₹1,20,000. We take ₹40,000 as an advance and the rest on delivery.\n\nWe start only after the advance is received.",
     {"must_include": ["Subject: Payment schedule", "Zubair", "Hindi", "Tamil", "advance", "rest on delivery", "only after the advance is received"], "numbers": ["1,20,000", "40,000"]},
     pos="after", cx=4, waivers=["invented_subject"],
     note="facts: total ₹1,20,000; ₹40,000 advance (rupees spoken for the total, ₹ applied to both amounts in the same sentence), rest on delivery; work starts ONLY after advance received (own sentence). Waiver invented_subject: the Subject line is requested by the [Instruction]; model only localizes text, does not translate")

add2("multi_constraint", dict(F, recipient="Gustavo", register="formal", length="shorter",
                              instruction="keep the times exactly as I said them and don't add a.m. or p.m.",
                              transcript="hey gustavo so um the walkthrough with the client got moved, it was going to be at nine on thursday and now it's at one thirty on thursday, same place, the site office on mill road"),
     "Dear Gustavo,\n\nThe client walkthrough on Thursday has been moved from 9 to 1:30. It remains at the site office on Mill Road.",
     {"must_include": ["walkthrough", "Thursday", "site office", "Mill Road"], "numbers": ["9", "1:30"], "must_not_include": ["a.m.", "p.m."]},
     pos="before", cx=3,
     note="facts: walkthrough Thursday moved 9 -> 1:30 (same day); same place, site office on Mill Road; casual dictated 'hey gustavo' adapted to formal 'Dear Gustavo,'; no a.m./p.m.")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="turn this into an email to the hiring panel, bullet the three candidates and keep my notes on each",
                              transcript="okay so for tomorrow's final interviews we've got three candidates. abhay at ten, he's the one with the payments background. camille at eleven thirty, she's coming in person not on zoom. and noor at two, she might be ten minutes late because of a train. same room as last time"),
     "Hi,\n\nFor tomorrow's final interviews, we have three candidates:\n\n- Abhay at 10: he's the one with the payments background.\n- Camille at 11:30: she's coming in person, not on Zoom.\n- Noor at 2: she might be 10 minutes late because of a train.\n\nWe're in the same room as last time.",
     {"must_include": ["Abhay", "payments background", "Camille", "in person", "Noor", "might be", "train", "same room as last time"], "numbers": ["10", "11:30", "2"], "min_negations": 1},
     pos="after", cx=3,
     note="facts: Abhay 10 (payments background); Camille 11:30 in person NOT Zoom; Noor 2, MIGHT be 10 minutes late (train); same room; no a.m./p.m. added; group with no names -> 'Hi,'")

add2("multi_constraint", dict(R, tone="warm",
                              instruction="email to the customer, keep the order number and the refund amount, no exclamation marks",
                              transcript="order 30877, the refund of sixty four dollars ninety has been processed, it can take five to seven business days to show up"),
     "Hi,\n\nI'm glad to let you know that the refund of $64.90 for order 30877 has been processed. It can take 5 to 7 business days to show up.",
     {"must_include": ["refund", "processed", "business days"], "numbers": ["64.90", "30877", "5", "7"], "must_not_include": ["!"]},
     pos="before", cx=3,
     waivers=["number_missing"],
     note="facts: waiver number_missing because the checker reads 'sixty four dollars ninety' as 64 and 90, target $64.90 is correct and pinned; order 30877; refund $64.90 processed; can take 5 to 7 business days; warm wording only, no new facts; no exclamation marks")

add2("multi_constraint", dict(task="rewrite", format="email", register="formal", locale="en-gb",
                              instruction="write it to the admissions team, keep the student ID and both document names, and don't add a sign-off",
                              transcript="hi um i'm following up on my application, student id 2026-UK-0457. i uploaded my personal statement and my reference letter on monday but the portal still shows them as missing"),
     "Hello,\n\nI am following up on my application, student ID 2026-UK-0457. I uploaded my personal statement and my reference letter on Monday, but the portal still shows them as missing.",
     {"must_include": ["2026-UK-0457", "personal statement", "reference letter", "Monday", "still shows them as missing"], "must_not_include": ["Regards", "Best,", "Thanks,"]},
     pos="after", cx=4,
     note="facts: follow-up; student ID 2026-UK-0457 verbatim; personal statement + reference letter uploaded Monday; portal 'still' shows missing; formal dictated 'hi' -> 'Hello,' (no name); no sign-off")

add2("multi_constraint", dict(F, recipient="Camille", sender="Manish", tone="confident",
                              instruction="keep the percentages exactly and don't promise a date",
                              transcript="camille the new onboarding checklist cut setup time by about thirty percent in the beta and activation went from forty one to fifty two percent. we're aiming to roll it out to all accounts soon"),
     "Hi Camille,\n\nThe new onboarding checklist cut setup time by about 30% in the beta, and activation went from 41% to 52%. We're aiming to roll it out to all accounts soon.\n\nBest,\nManish",
     {"must_include": ["onboarding checklist", "about 30%", "beta", "aiming", "all accounts soon"], "numbers": ["30", "41", "52"]},
     pos="before", cx=3,
     note="facts: setup time cut ABOUT 30% in beta; activation 41% -> 52%; 'aiming' to roll out soon (no date, not a promise)")

add2("multi_constraint", dict(task="rewrite", format="email", register="casual",
                              instruction="short and casual, to Noor, keep the room number",
                              transcript="the yoga mats are in room b12 you can grab them anytime"),
     "Hi Noor,\n\nThe yoga mats are in room B12. You can grab them anytime.",
     {"must_include": ["Noor", "yoga mats", "B12", "anytime"]},
     pos="after", cx=3,
     note="facts: mats in room B12; can grab anytime; recipient from instruction")

add2("multi_constraint", dict(R, recipient="Oliver", sender="Tamsin",
                              instruction="professional email to the client, keep all three options with their prices, keep the recommendation as my personal opinion, and no bullet points",
                              transcript="oliver so for the game's localization we've got three ways to go. option one is full localization of text and voice in japanese and korean, that's about forty eight thousand dollars. option two is text only in both languages for around nineteen thousand. option three is text only in japanese first, about eleven thousand, and korean later. um personally i'd go with option two because the voice budget isn't approved yet, but it's your call. we'd need a decision by the end of the month to keep the spring release"),
     "Hi Oliver,\n\nFor the game's localization, there are three ways to go. Option 1 is full localization of text and voice in Japanese and Korean, which is about $48,000. Option 2 is text only in both languages, for around $19,000. Option 3 is text only in Japanese first, for about $11,000, with Korean later.\n\nPersonally, I'd go with option 2 because the voice budget isn't approved yet, but it's your call.\n\nWe'd need a decision by the end of the month to keep the spring release.\n\nBest,\nTamsin",
     {"must_include": ["Japanese", "Korean", "text only", "Personally", "your call", "end of the month", "spring release"], "numbers": ["48,000", "19,000", "11,000"], "min_negations": 1},
     pos="before", cx=4,
     note="facts: option 1 text+voice JA+KO about $48,000; option 2 text only both around $19,000; option 3 JA text first about $11,000, KO later ('dollars' spoken for the first, $ applied to all three prices in the same comparison); speaker personally prefers option 2 (voice budget not approved), client decides; decision by month end for spring release; prose per instruction")

# ------------------------------------------------------------------ s2 chunk 2 (141-190)

add2("email", dict(F, recipient="Peter", sender="Noor",
                   transcript="tell peter yes the sso setup is included in his plan, no extra charge"),
     "Hi Peter,\n\nYes, the SSO setup is included in your plan, at no extra charge.\n\nBest,\nNoor",
     {"must_include": ["Peter", "SSO setup", "included", "no extra charge", "Noor"], "min_negations": 1},
     note="facts: reply content dictated (yes); SSO included in plan; no extra charge")

add2("email", dict(R, register="casual",
                   transcript="just a reminder invoice 2087 for eight hundred and fifty dollars is now two weeks overdue"),
     "Hi,\n\nJust a reminder that invoice 2087 for $850 is now two weeks overdue.",
     {"must_include": ["reminder", "overdue"], "numbers": ["2087", "850"]},
     note="facts: invoice 2087, $850, two weeks overdue; no late fee or new deadline added")

add2("email", dict(F, sender="Kavya", locale="en-gb",
                   transcript="i'm on leave on the third and fourth of november, back on the fifth"),
     "Hi,\n\nI'm on leave on 3 and 4 November and back on 5 November.\n\nBest,\nKavya",
     {"must_include": ["on leave", "November", "back on", "Kavya"], "numbers": ["3", "4", "5"]},
     note="facts: out-of-office only for the dictated dates: leave 3 and 4 November, back 5 November; no cover person added")

add2("email", dict(R,
                   transcript="thank gustavo for the referral, the client signed with us yesterday"),
     "Hi Gustavo,\n\nThank you for the referral. The client signed with us yesterday.",
     {"must_include": ["Gustavo", "referral", "signed with us yesterday"], "must_not_include": ["amazing", "appreciate your"]},
     note="facts: thanks for referral; client signed yesterday; no compliments invented")

add2("email", dict(F, recipient="Sun-hee", register="formal", locale="en-gb",
                   transcript="your membership freeze is approved from the first of december to the thirty first of january"),
     "Dear Sun-hee,\n\nYour membership freeze has been approved from 1 December to 31 January.",
     {"must_include": ["membership freeze", "approved", "December", "January"], "numbers": ["1", "31"]},
     note="facts: freeze approved 1 December to 31 January")

add2("email", dict(R, register="casual",
                   transcript="hey kavya can you upload the new product photos by thursday morning"),
     "Hi Kavya,\n\nCan you upload the new product photos by Thursday morning?",
     {"must_include": ["Kavya", "product photos", "Thursday morning"], "ends_with_question": True},
     note="facts: request to upload photos by Thursday morning; casual 'hey' -> 'Hi Kavya,'")

add2("email", dict(R,
                   transcript="the planning hearing is on the twelfth at ten in committee room b"),
     "Hi,\n\nThe planning hearing is on the 12th at 10 in Committee Room B.",
     {"must_include": ["planning hearing", "Committee Room B"], "numbers": ["12", "10"], "must_not_include": ["a.m."]},
     note="facts: hearing on the 12th at 10 (no a.m. added), Committee Room B")

add2("email", dict(R, recipient="Zubair", register="formal",
                   transcript="your offer is conditional on an ielts score of at least six point five"),
     "Dear Zubair,\n\nYour offer is conditional on an IELTS score of at least 6.5.",
     {"must_include": ["conditional", "IELTS", "at least"], "numbers": ["6.5"]},
     note="facts: offer conditional on IELTS at least 6.5")

add2("email", dict(R, sender="Abhay",
                   transcript="the proofs are ready for you to check, we can't start printing until you sign off"),
     "Hi,\n\nThe proofs are ready for you to check. We can't start printing until you sign off.\n\nBest,\nAbhay",
     {"must_include": ["proofs", "sign off", "Abhay"], "min_negations": 1},
     note="facts: proofs ready; printing can't start until sign-off")

add2("email", dict(R, recipient="Camille",
                   transcript="camille the japanese strings file still has two hundred and eight keys untranslated"),
     "Hi Camille,\n\nThe Japanese strings file still has 208 untranslated keys.",
     {"must_include": ["Japanese strings file", "still", "untranslated keys"], "numbers": ["208"]},
     note="facts: 208 keys still untranslated in the Japanese strings file; English output, nothing translated")

add2("email", dict(R, length="shorter",
                   transcript="so uh the gym's closing early at eight p m on friday because of the uh the floor polishing"),
     "Hi,\n\nThe gym is closing early, at 8 p.m., on Friday for floor polishing.",
     {"must_include": ["closing early", "Friday", "floor polishing"], "numbers": ["8"]},
     note="facts: closing early 8 p.m. Friday; reason floor polishing")

add2("email", dict(F, recipient="Tamsin", sender="Rania", tone="warm",
                   transcript="tamsin welcome to the team, your laptop will be ready at reception on your first day"),
     "Hi Tamsin,\n\nWelcome to the team. Your laptop will be ready for you at reception on your first day.\n\nBest,\nRania",
     {"must_include": ["Welcome to the team", "laptop", "reception", "first day", "Rania"]},
     note="facts: welcome; laptop at reception on first day; warm tone adds no events or thanks")

add2("email", dict(R, sender="Manish", register="formal", locale="en-in",
                   transcript="please share the signed nda and your pan card copy before monday"),
     "Hello,\n\nPlease share the signed NDA and a copy of your PAN card before Monday.\n\nRegards,\nManish",
     {"must_include": ["signed NDA", "PAN card", "before Monday", "Manish"]},
     note="facts: request: signed NDA + PAN card copy before Monday; 'please' was dictated")

add2("email", dict(R,
                   transcript="the gift cards are printed and boxed, pickup anytime after two, cheers"),
     "Hi,\n\nThe gift cards are printed and boxed. You can pick them up anytime after 2.\n\nCheers,",
     {"must_include": ["gift cards", "printed and boxed", "after 2", "Cheers,"]},
     note="facts: pickup anytime after 2 (no a.m./p.m. added); dictated closing 'cheers', no name")

add2("email", dict(R, recipient="Oliver", sender="Camille",
                   transcript="oliver i need to push our one to one from friday at four to monday at nine thirty, i've got a candidate debrief that ran over. if monday doesn't work for you tuesday at the same time is fine too"),
     "Hi Oliver,\n\nI need to push our one-to-one from Friday at 4 to Monday at 9:30, as I have a candidate debrief that ran over. If Monday doesn't work for you, Tuesday at the same time is fine too.\n\nBest,\nCamille",
     {"must_include": ["one-to-one", "Friday", "Monday", "Tuesday at the same time", "candidate debrief", "Camille"], "numbers": ["4", "9:30"], "min_negations": 1},
     waivers=["number_missing"],
     note="waiver number_missing: checker reads 'one to one' (a meeting type, written 'one-to-one') as the number 1. facts: reschedule Friday 4 -> Monday 9:30 (no a.m./p.m. added); reason debrief ran over; IF Monday doesn't work, Tuesday same time (9:30) is fine")

add2("email", dict(R, recipient="Abhay", sender="Zubair", register="formal", locale="en-in",
                   transcript="abhay we're pleased to offer you the gym floor manager role at our andheri branch. the compensation details are in the attached letter. please sign and return it by the twentieth, and your joining date will be confirmed after that"),
     "Dear Abhay,\n\nWe are pleased to offer you the Gym Floor Manager role at our Andheri branch. The compensation details are in the attached letter.\n\nPlease sign and return it by the 20th. Your joining date will be confirmed after that.\n\nRegards,\nZubair",
     {"must_include": ["Gym Floor Manager", "Andheri", "attached letter", "joining date", "Zubair"], "numbers": ["20"], "must_not_include": ["₹", "salary of", "lakh"]},
     note="facts: offer for Gym Floor Manager, Andheri branch; compensation only in attached letter (no figures invented); sign and return by the 20th; joining date confirmed after")

add2("email", dict(R,
                   transcript="hi i returned order 7731-B on the second of october and the courier confirmed pickup but the refund still hasn't come through. it was for a hundred and nineteen dollars. can you check what's holding it up"),
     "Hi,\n\nI returned order 7731-B on October 2, and the courier confirmed pickup, but the refund still hasn't come through. It was for $119.\n\nCan you check what's holding it up?",
     {"must_include": ["7731-B", "October 2", "courier confirmed pickup", "refund still hasn't come through"], "numbers": ["119"], "min_negations": 1},
     note="facts: complaint; order 7731-B returned October 2; pickup confirmed; refund 'still' not received; $119; question kept")

add2("email", dict(R, sender="Tamsin",
                   transcript="i'd like to introduce kavya to manish. kavya's an incoming student in the architecture program and manish is a second year who volunteered as a peer mentor. kavya had questions about the studio workload so manish is the right person"),
     "Hi Kavya and Manish,\n\nI'd like to introduce you to each other. Kavya is an incoming student in the architecture program, and Manish is a second-year student who volunteered as a peer mentor.\n\nKavya, you had questions about the studio workload, so Manish is the right person to ask.\n\nBest,\nTamsin",
     {"must_include": ["Kavya", "Manish", "incoming student", "architecture program", "peer mentor", "studio workload", "Tamsin"]},
     note="facts: introduction; Kavya incoming architecture student; Manish second-year volunteer peer mentor; Kavya had questions on studio workload; no meeting invented")

add2("email", dict(R, sender="Gustavo",
                   transcript="hi team, we're switching the support inbox from zendesk to intercom on the first of next month. existing tickets stay in zendesk until they're closed, new ones go to intercom only. uh training sessions are on the twenty sixth and the twenty seventh, pick one"),
     "Hi team,\n\nWe're switching the support inbox from Zendesk to Intercom on the 1st of next month. Existing tickets stay in Zendesk until they're closed, and new ones go to Intercom only.\n\nTraining sessions are on the 26th and the 27th. Pick one.\n\nBest,\nGustavo",
     {"must_include": ["Zendesk", "Intercom", "next month", "until they're closed", "Intercom only", "Pick one", "Gustavo"], "numbers": ["1", "26", "27"]},
     note="facts: switch on the 1st of next month; existing tickets stay in Zendesk until closed; new ones Intercom only; training 26th and 27th, attend one")

add2("email", dict(F, recipient="Peter", sender="Sun-hee", register="formal", locale="en-gb",
                   transcript="peter this is our second reminder about invoice 4410 for the stage three fees, two thousand eight hundred pounds, which was due on the fifteenth of august. if we don't receive payment by the end of this month we'll have to pause work on the tender drawings"),
     "Dear Peter,\n\nThis is our second reminder about invoice 4410 for the Stage 3 fees of £2,800, which was due on 15 August.\n\nIf we do not receive payment by the end of this month, we will have to pause work on the tender drawings.\n\nRegards,\nSun-hee",
     {"must_include": ["second reminder", "Stage 3", "August", "end of this month", "pause work on the tender drawings", "Sun-hee"], "numbers": ["4410", "2,800", "15"], "min_negations": 1},
     note="facts: second reminder; invoice 4410; Stage 3 fees £2,800 (pounds spoken); due 15 August; condition: IF no payment by end of month -> pause tender drawings")

add2("email", dict(R, recipient="Rania",
                   transcript="rania thanks for the feedback form you filled in, we've moved the water fountain closer to the free weights like you suggested"),
     "Hi Rania,\n\nThank you for filling in the feedback form. We've moved the water fountain closer to the free weights, as you suggested.",
     {"must_include": ["feedback form", "water fountain", "free weights", "as you suggested"]},
     note="facts: thanks for feedback form; fountain moved near free weights per her suggestion; no compliments added")

add2("email", dict(R, recipient="Peter", sender="Noor",
                   transcript="peter the style guide for the arabic project is attached and the term base is on our portal at portal dot lingualane dot co slash projects slash 318. reviewers should use both, not just the style guide"),
     "Hi Peter,\n\nThe style guide for the Arabic project is attached, and the term base is on our portal at portal.lingualane.co/projects/318. Reviewers should use both, not just the style guide.\n\nBest,\nNoor",
     {"must_include": ["style guide", "Arabic project", "attached", "term base", "portal.lingualane.co/projects/318", "use both", "Noor"], "min_negations": 1},
     note="facts: style guide attached; term base at portal.lingualane.co/projects/318 (spoken URL); reviewers use both, NOT just the style guide")

add2("email", dict(R, length="shorter",
                   instruction="two sentences at most",
                   transcript="okay so the print run for the menus is done, we did three hundred copies, they're boxed up and uh sitting at the front counter, you can pick them up whenever, we're open till seven tonight"),
     "Hi,\n\nThe print run of 300 menus is done, and they're boxed up at the front counter. You can pick them up whenever; we're open until 7 tonight.",
     {"must_include": ["menus", "front counter", "pick them up", "tonight"], "numbers": ["300", "7"]},
     pos="after", cx=2,
     note="facts: menu print run done, 300 copies; boxed at front counter; pick up whenever; open until 7 tonight; two sentences max")

add2("email", dict(R, sender="Kavya", locale="en-in",
                   transcript="hi abhay the last batch of cotton kurtas had sizing issues, the large ones are measuring like a medium. we've got about forty returns already. please check the pattern before the next batch of two hundred pieces"),
     "Hi Abhay,\n\nThe last batch of cotton kurtas had sizing issues: the large ones are measuring like a medium. We've had about 40 returns already.\n\nPlease check the pattern before the next batch of 200 pieces.\n\nBest,\nKavya",
     {"must_include": ["Abhay", "cotton kurtas", "sizing issues", "like a medium", "about 40", "pattern", "Kavya"], "numbers": ["40", "200"]},
     note="facts: large kurtas measure like a medium (comparison 'like', not 'about'); ABOUT 40 returns already; check pattern before next 200-piece batch")

add2("email", dict(F, recipient="Gustavo", sender="Rania",
                   transcript="gustavo thanks for taking the time to do the design task. we've decided to go with another candidate whose experience is closer to what the team needs right now. we won't be keeping applications on file for this role"),
     "Hi Gustavo,\n\nThank you for taking the time to do the design task. We've decided to go with another candidate whose experience is closer to what the team needs right now. We won't be keeping applications on file for this role.\n\nBest,\nRania",
     {"must_include": ["design task", "another candidate", "won't be keeping applications on file", "Rania"], "min_negations": 1, "must_not_include": ["sorry", "apolog", "future openings"]},
     note="facts: rejection; went with another candidate; applications NOT kept on file; no apology, no future offer added")

add2("email", dict(R, recipient="Sun-hee", sender="Manish",
                   transcript="hi sun-hee, so a few things from our kickoff call today. on data import, your team can upload the client list as a csv, up to fifty thousand rows per file, anything bigger we'll need to split. on permissions we agreed admins can edit billing but managers can only view it. uh for the go live date you mentioned the fourteenth but said it depends on your it team finishing the sso setup, so let's treat that as tentative. and on training, we'll run two sessions, one for admins and one for everyone else, i'll send times once you confirm the go live"),
     "Hi Sun-hee,\n\nA few things from our kickoff call today.\n\nOn data import, your team can upload the client list as a CSV, up to 50,000 rows per file. Anything bigger, we'll need to split.\n\nOn permissions, we agreed that admins can edit billing, but managers can only view it.\n\nFor the go-live date, you mentioned the 14th but said it depends on your IT team finishing the SSO setup, so let's treat that as tentative.\n\nOn training, we'll run two sessions, one for admins and one for everyone else. I'll send times once you confirm the go-live.\n\nBest,\nManish",
     {"must_include": ["CSV", "per file", "admins can edit billing", "only view", "tentative", "SSO setup", "two sessions", "once you confirm", "Manish"], "numbers": ["50,000", "14"]},
     note="facts: CSV up to 50,000 rows per file, bigger must be split; admins edit billing, managers view only; go-live 14th TENTATIVE, depends on IT finishing SSO; two training sessions (admins / everyone else); times sent only once go-live confirmed")

add2("email", dict(F, sender="Oliver", register="formal", locale="en-gb",
                   transcript="hello i'm writing about my membership number GM-20914. i cancelled my membership on the second of september using the form at the front desk and was told the last payment would be in september. but i was charged again on the first of october, forty two pounds. i'd like that payment refunded and written confirmation that the membership is closed. i've kept a photo of the cancellation form if you need it"),
     "Hello,\n\nI am writing about my membership, number GM-20914. I cancelled my membership on 2 September using the form at the front desk and was told that the last payment would be in September. However, I was charged again on 1 October, for £42.\n\nI would like that payment refunded and written confirmation that the membership is closed. I have kept a photo of the cancellation form if you need it.\n\nRegards,\nOliver",
     {"must_include": ["GM-20914", "September", "front desk", "October", "refunded", "written confirmation", "photo of the cancellation form", "Oliver"], "numbers": ["2", "1", "42"]},
     note="facts: membership GM-20914; cancelled 2 September via front desk form; told last payment in September; charged again 1 October £42 (pounds spoken); wants refund + written confirmation; has photo of form if needed")

add2("email", dict(R, recipient="Zubair", sender="Camille",
                   transcript="zubair here's what we need from you before we start the french canadian localization of the app. the list is, the final english strings export, the brand glossary if you have one, and access to a test build on testflight. also the deadline you gave us, the thirtieth, only works if we get all of that by friday. if anything comes later the delivery moves by the same number of days. and just so it's clear we're doing localization and review only, the strings themselves come from your team"),
     "Hi Zubair,\n\nHere's what we need from you before we start the French Canadian localization of the app:\n\n- The final English strings export\n- The brand glossary, if you have one\n- Access to a test build on TestFlight\n\nThe deadline you gave us, the 30th, only works if we get all of that by Friday. If anything comes later, the delivery moves by the same number of days.\n\nJust so it's clear, we're doing localization and review only. The strings themselves come from your team.\n\nBest,\nCamille",
     {"must_include": ["French Canadian", "strings export", "brand glossary", "TestFlight", "only works if", "Friday", "same number of days", "localization and review only", "Camille"], "numbers": ["30"]},
     note="facts: 3 items with cue 'the list is' -> bullets; glossary only 'if you have one'; deadline 30th ONLY IF all received by Friday; later -> delivery moves same number of days; scope = localization + review only, strings from client")

add2("email", dict(F, recipient="Noor", sender="Abhay", locale="en-in",
                   transcript="noor here's the quote for the college fest. items are, one thousand a five flyers at four rupees each so four thousand rupees, fifty a two posters at sixty each that's three thousand, and two flex banners at one thousand two hundred each so two thousand four hundred. total is nine thousand four hundred rupees plus gst. we need fifty percent advance to start and the rest on delivery"),
     "Hi Noor,\n\nHere's the quote for the college fest:\n\n- 1,000 A5 flyers at ₹4 each: ₹4,000\n- 50 A2 posters at ₹60 each: ₹3,000\n- 2 flex banners at ₹1,200 each: ₹2,400\n\nThe total is ₹9,400 plus GST. We need a 50% advance to start, and the rest on delivery.\n\nBest,\nAbhay",
     {"must_include": ["college fest", "A5 flyers", "A2 posters", "flex banners", "plus GST", "advance", "rest on delivery", "Abhay"],
      "numbers": ["1,000", "4", "4,000", "50", "60", "3,000", "2", "1,200", "2,400", "9,400"]},
     note="facts: 1,000 A5 flyers x ₹4 = ₹4,000; 50 A2 posters x ₹60 = ₹3,000; 2 flex banners x ₹1,200 = ₹2,400; total ₹9,400 plus GST (arithmetic checks); 50% advance to start, rest on delivery. ₹ applied to every price in the list (rupees spoken for the list); counts as digits inside the priced list")

add2("email", dict(R, sender="Peter",
                   transcript="hi everyone the clearing hotline opens on thursday at eight a m and runs until eight p m, then nine to five on friday and saturday. every adviser needs to log into the new call system before wednesday, the login details went out yesterday. we can't make offers over the phone without checking the entry requirements sheet, it's pinned in the shared channel. um and if a caller asks about accommodation pass them to the housing team, don't answer it yourself. lunch will be provided on thursday"),
     "Hi everyone,\n\nThe clearing hotline opens on Thursday at 8 a.m. and runs until 8 p.m., then from 9 to 5 on Friday and Saturday.\n\nEvery adviser needs to log in to the new call system before Wednesday. The login details went out yesterday.\n\nWe can't make offers over the phone without checking the entry requirements sheet, which is pinned in the shared channel.\n\nIf a caller asks about accommodation, pass them to the housing team. Don't answer it yourself.\n\nLunch will be provided on Thursday.\n\nBest,\nPeter",
     {"must_include": ["clearing hotline", "Thursday", "Friday and Saturday", "before Wednesday", "entry requirements sheet", "housing team", "Lunch will be provided", "Peter"],
      "numbers": ["8", "9", "5"], "min_negations": 2},
     note="facts: hotline Thu 8 a.m.-8 p.m., Fri+Sat 9 to 5; advisers log in before Wednesday, details sent yesterday; NO phone offers without checking entry requirements sheet (pinned); accommodation questions -> housing team, DON'T answer yourself; lunch Thursday")

add2("email", dict(R, sender="Rania",
                   transcript="hi team i just want to say thank you for getting the competition entry in on time. we submitted at eleven forty last night with twenty minutes to spare. special thanks to oliver for the model photos and to camille for rewriting the design statement twice. the results come out in march. take friday afternoon off, all of you, it's been a long few weeks"),
     "Hi team,\n\nI just want to say thank you for getting the competition entry in on time. We submitted at 11:40 last night, with 20 minutes to spare.\n\nSpecial thanks to Oliver for the model photos and to Camille for rewriting the design statement twice.\n\nThe results come out in March. Take Friday afternoon off, all of you. It's been a long few weeks.\n\nBest,\nRania",
     {"must_include": ["competition entry", "last night", "Oliver", "model photos", "Camille", "design statement twice", "March", "Friday afternoon off", "Rania"], "numbers": ["11:40", "20"]},
     note="facts: entry submitted 11:40 last night, 20 minutes to spare; thanks to Oliver (model photos) and Camille (rewrote statement twice); results in March; Friday afternoon off for everyone; no compliments beyond dictated")

add2("email", dict(R, recipient="Tamsin", sender="Gustavo",
                   transcript="tamsin yes we do wholesale. the minimum order is a hundred units per design, mixed sizes are fine. wholesale price is fourteen dollars a unit for orders under five hundred and twelve fifty for five hundred and over. we don't do custom prints on wholesale orders though. shipping to the uk takes about ten days and you'd pay the import duties on your side"),
     "Hi Tamsin,\n\nYes, we do wholesale. The minimum order is 100 units per design, and mixed sizes are fine.\n\nThe wholesale price is $14 a unit for orders under 500 units and $12.50 a unit for orders of 500 and over. We don't do custom prints on wholesale orders, though.\n\nShipping to the UK takes about 10 days, and you'd pay the import duties on your side.\n\nBest,\nGustavo",
     {"must_include": ["wholesale", "per design", "mixed sizes", "custom prints", "UK", "import duties", "Gustavo"], "numbers": ["100", "14", "500", "12.50", "10"], "min_negations": 1},
     waivers=["number_missing", "number_invented"],
     note="facts: reply content dictated; min 100 units per design; mixed sizes OK; $14/unit under 500, $12.50/unit for 500+ ('dollars' spoken for $14, same price list); NO custom prints on wholesale; UK shipping ABOUT 10 days; buyer pays import duties. Waivers number_missing/number_invented: checker splits 'twelve fifty' into 12 and 50 and then sees 12 in $12.50 as new; target $12.50 is correct and pinned")

add2("email", dict(F, sender="Kavya", locale="en-in",
                   transcript="hi all, quick note on diwali leave. the office is closed from the thirty first of october to the fourth of november. if you're on a client deployment check with your manager before you plan travel, some clients are working on those days. salaries for october will be credited on the twenty eighth instead of the thirtieth. and the gift hampers will be at reception from the twenty seventh, collect yours by the thirtieth"),
     "Hi all,\n\nA quick note on Diwali leave. The office is closed from 31 October to 4 November.\n\nIf you're on a client deployment, check with your manager before you plan travel, as some clients are working on those days.\n\nSalaries for October will be credited on the 28th instead of the 30th.\n\nThe gift hampers will be at reception from the 27th. Collect yours by the 30th.\n\nBest,\nKavya",
     {"must_include": ["Diwali", "October", "November", "client deployment", "check with your manager", "credited", "gift hampers", "Kavya"], "numbers": ["31", "4", "28", "30", "27"]},
     note="facts: office closed 31 Oct-4 Nov; IF on client deployment, check with manager before travel; October salaries on 28th instead of 30th; hampers at reception from 27th, collect by 30th")

add2("email", dict(R, recipient="Peter", sender="Oliver",
                   transcript="peter two things. first the warehouse move. we're moving stock to the new unit on the eighteenth and nineteenth, so orders placed on those days will ship on the twentieth. i'll put a banner on the site. second, totally separate, the accountant needs the september sales report by monday, can you pull it from shopify, the version with refunds broken out, not the summary one"),
     "Hi Peter,\n\nTwo things.\n\nFirst, the warehouse move. We're moving stock to the new unit on the 18th and 19th, so orders placed on those days will ship on the 20th. I'll put a banner on the site.\n\nSecond, on a separate note, the accountant needs the September sales report by Monday. Can you pull it from Shopify? We need the version with refunds broken out, not the summary one.\n\nBest,\nOliver",
     {"must_include": ["warehouse move", "new unit", "banner", "accountant", "September sales report", "Monday", "Shopify", "refunds broken out", "Oliver"], "numbers": ["18", "19", "20"], "min_negations": 1},
     note="facts: stock move 18th+19th; orders those days ship 20th; speaker will add site banner (spoken commitment); separate topic: September sales report by Monday from Shopify, version with refunds broken out NOT summary; two items -> prose")

# --- multi_constraint (175-190)

add2("multi_constraint", dict(R, register="formal",
                              instruction="polite email, keep it under 25 words",
                              transcript="the parking lot is closed tomorrow so members should use the street entrance"),
     "Hello,\n\nThe parking lot is closed tomorrow, so members are kindly asked to use the street entrance.",
     {"must_include": ["parking lot", "closed tomorrow", "street entrance"], "max_words": 25},
     pos="before", cx=2,
     note="facts: parking closed tomorrow; members should use street entrance; polite wording only")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="make it an email to Rania, formal, and keep the file name exactly",
                              transcript="the final contract is saved as contract_v3_signed.pdf in the shared drive"),
     "Dear Rania,\n\nThe final contract is saved as contract_v3_signed.pdf in the shared drive.",
     {"must_include": ["Rania", "contract_v3_signed.pdf", "shared drive"]},
     pos="after", cx=3,
     note="facts: file name contract_v3_signed.pdf verbatim; in shared drive; recipient from instruction")

add2("multi_constraint", dict(R, sender="Sun-hee", tone="warm",
                              instruction="don't add a thank-you",
                              transcript="your class pack of ten sessions is now active"),
     "Hi,\n\nI'm happy to let you know that your class pack of ten sessions is now active.\n\nBest,\nSun-hee",
     {"must_include": ["class pack", "ten sessions", "now active", "Sun-hee"], "must_not_include": ["thank"]},
     pos="before", cx=2,
     note="facts: ten-session class pack active; warm wording only; no thank-you")

add2("multi_constraint", dict(task="rewrite", format="email", register="casual", header_style="full",
                              instruction="casual email to Oliver, keep both colour options",
                              transcript="we can do the logo in navy or forest green your pick"),
     "Hi Oliver,\n\nWe can do the logo in navy or forest green. Your pick.",
     {"must_include": ["Oliver", "navy", "forest green", "Your pick"]},
     pos="after", cx=2,
     note="facts: alternative kept: navy OR forest green; Oliver chooses")

add2("multi_constraint", dict(R, register="formal", locale="en-gb",
                              instruction="no contractions and keep the date",
                              transcript="we can't process your application without a copy of your passport, please send it by the ninth"),
     "Hello,\n\nWe cannot process your application without a copy of your passport. Please send it by the 9th.",
     {"must_include": ["cannot process", "copy of your passport", "Please send it"], "numbers": ["9"], "min_negations": 1, "must_not_include": ["can't"]},
     pos="before", cx=3,
     note="facts: application can't be processed without passport copy; send by the 9th; 'please' dictated; no contractions")

add2("multi_constraint", dict(task="rewrite", format="email", length="shorter",
                              instruction="keep the tracking link exactly",
                              transcript="uh so your replacement charger shipped this morning and um you can track it at track dot parcelpoint dot com slash RX22019"),
     "Hi,\n\nYour replacement charger shipped this morning. Track it at track.parcelpoint.com/RX22019.",
     {"must_include": ["replacement charger", "this morning", "track.parcelpoint.com/RX22019"]},
     pos="after", cx=2,
     note="facts: shipped this morning; spoken tracking URL written as track.parcelpoint.com/RX22019")

add2("multi_constraint", dict(F, recipient="Manish", sender="Noor", tone="confident",
                              instruction="cut the extra hedging but keep that it's only a maybe",
                              transcript="um manish so i think uh we might maybe be able to deliver the dutch subtitles a day early, not sure though"),
     "Hi Manish,\n\nWe might be able to deliver the Dutch subtitles a day early, though I'm not sure yet.\n\nBest,\nNoor",
     {"must_include": ["might", "Dutch subtitles", "a day early", "not sure"], "min_negations": 1, "must_not_include": ["will deliver"]},
     pos="before", cx=2,
     note="facts: early delivery (one day) is uncertain: 'might' + 'not sure' kept; stacked hedges 'I think/maybe' trimmed per instruction")

add2("multi_constraint", dict(task="rewrite", format="email", tone="friendly",
                              instruction="email to the gym members, bullet the three new rules, no emoji",
                              transcript="so starting next month a few new rules. towels are required on all benches. bags have to go in the lockers not on the floor. and the free weights area is closed for cleaning every day from two to two thirty"),
     "Hi,\n\nStarting next month, there are a few new rules:\n\n- Towels are required on all benches.\n- Bags have to go in the lockers, not on the floor.\n- The free weights area is closed for cleaning every day from 2 to 2:30.",
     {"must_include": ["next month", "Towels are required", "lockers", "free weights area", "every day"], "numbers": ["2", "2:30"], "min_negations": 1},
     pos="after", cx=3,
     note="facts: from next month: towels on all benches; bags in lockers NOT floor; free weights closed daily 2 to 2:30 (no a.m./p.m. added); no sign-off (no sender)")

add2("multi_constraint", dict(R, recipient="Camille", sender="Peter",
                              instruction="professional email to the client, keep the fee numbers, and don't add any discount",
                              transcript="so the fee for the feasibility study is four thousand five hundred dollars and if you go ahead with the full design we'd credit two thousand of that against the design fee. the study takes about six weeks"),
     "Hi Camille,\n\nThe fee for the feasibility study is $4,500. If you go ahead with the full design, we would credit $2,000 of that against the design fee.\n\nThe study takes about six weeks.\n\nBest,\nPeter",
     {"must_include": ["feasibility study", "If you go ahead with the full design", "credit", "design fee", "about six weeks"], "numbers": ["4,500", "2,000"], "must_not_include": ["discount", "%"]},
     pos="before", cx=3,
     note="facts: study fee $4,500; credit $2,000 of it ONLY IF client goes ahead with full design ('of that' = dollars); study about six weeks; no discount added")

add2("multi_constraint", dict(task="rewrite", format="email", locale="en-in",
                              instruction="formal email to the candidate from Rania, keep the date and time exactly, and don't mention salary",
                              transcript="abhay you've been shortlisted for the final round, it's in person at our pune office on the twenty third at eleven a m, uh bring two copies of your resume and a photo id"),
     "Dear Abhay,\n\nYou have been shortlisted for the final round. It will be held in person at our Pune office on the 23rd at 11 a.m.\n\nPlease bring two copies of your resume and a photo ID.\n\nRegards,\nRania",
     {"must_include": ["Abhay", "shortlisted", "final round", "in person", "Pune office", "photo ID", "Rania"], "numbers": ["23", "11"], "must_not_include": ["salary", "CTC"]},
     pos="after", cx=4,
     note="facts: shortlisted; final round in person, Pune office, 23rd at 11 a.m.; bring two resume copies + photo ID; formal 'please' added to the dictated instruction, no new request; no salary")

add2("multi_constraint", dict(R, register="formal",
                              instruction="firm but polite, keep the order numbers and amounts exact, no apology",
                              transcript="three of our parcels were returned to us as undeliverable even though the addresses were correct, orders 6120, 6134 and 6151. we paid return shipping of nine dollars each so twenty seven dollars total and we want that credited back"),
     "Hello,\n\nThree of our parcels, for orders 6120, 6134 and 6151, were returned to us as undeliverable even though the addresses were correct. We paid return shipping of $9 each, $27 in total, and we expect that amount to be credited back to us.",
     {"must_include": ["undeliverable", "addresses were correct", "return shipping", "credited back"], "numbers": ["6120", "6134", "6151", "9", "27"], "must_not_include": ["sorry", "apolog"]},
     pos="before", cx=3,
     note="facts: 3 parcels (orders 6120, 6134, 6151) returned as undeliverable though addresses correct; $9 each, $27 total; want credit; no apology")

add2("multi_constraint", dict(task="rewrite", format="email", length="longer", tone="warm",
                              instruction="it's to Kavya from Gustavo, and don't add anything new",
                              transcript="kavya your portfolio review is booked for monday at three with the admissions tutor"),
     "Hi Kavya,\n\nI'm pleased to let you know that your portfolio review has been booked. It will take place on Monday at 3 with the admissions tutor.\n\nBest,\nGustavo",
     {"must_include": ["Kavya", "portfolio review", "Monday", "admissions tutor", "Gustavo"], "numbers": ["3"], "must_not_include": ["p.m.", "a.m.", "room"]},
     pos="after", cx=3,
     note="facts: portfolio review booked Monday at 3 (no a.m./p.m.) with admissions tutor; longer + warm = wording only")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="professional email to Tamsin, keep every deadline and owner, no bullet points",
                              transcript="tamsin update on the onboarding revamp. peter owns the new welcome email sequence and he's aiming to have the drafts ready by the tenth. zubair is rebuilding the setup checklist in the app, that's due on the seventeenth but he flagged it might slip because of the api changes. i'm handling the help center articles, all twelve by the end of the month. we still haven't decided whether the product tour is in scope for this phase, that's on the agenda for thursday"),
     "Hi Tamsin,\n\nHere is an update on the onboarding revamp.\n\nPeter owns the new welcome email sequence and is aiming to have the drafts ready by the 10th. Zubair is rebuilding the setup checklist in the app. That is due on the 17th, but he has flagged that it might slip because of the API changes. I'm handling the help center articles, all 12 of them, by the end of the month.\n\nWe still haven't decided whether the product tour is in scope for this phase. That's on the agenda for Thursday.",
     {"must_include": ["Peter", "welcome email sequence", "aiming", "Zubair", "setup checklist", "might slip", "API changes", "help center articles", "end of the month", "product tour", "Thursday"],
      "numbers": ["10", "17", "12"], "min_negations": 1},
     pos="before", cx=3,
     note="facts: Peter = welcome emails, AIMING for drafts by 10th; Zubair = setup checklist due 17th, MIGHT slip (API changes); speaker = 12 help articles by month end; product tour scope undecided (open question), agenda Thursday")

add2("multi_constraint", dict(task="rewrite", format="email", register="formal", locale="en-gb", sender="Noor",
                              instruction="email to the admissions committee, keep all the numbers, and add the subject line Intake numbers for autumn",
                              transcript="so for the autumn intake we received six hundred and forty applications for the design programmes, which is up from five hundred and ten last year. we've made two hundred and twenty offers so far and about ninety have been accepted. the studio space only fits a hundred and twenty students so we need to stop making offers once acceptances reach that number. i'd recommend we close the application portal on the fifteenth rather than the end of the month"),
     "Subject: Intake numbers for autumn\n\nHello,\n\nFor the autumn intake, we received 640 applications for the design programmes, up from 510 last year. We have made 220 offers so far, and about 90 have been accepted.\n\nThe studio space only fits 120 students, so we need to stop making offers once acceptances reach that number.\n\nI would recommend that we close the application portal on the 15th rather than at the end of the month.\n\nRegards,\nNoor",
     {"must_include": ["Subject: Intake numbers for autumn", "design programmes", "last year", "so far", "about 90", "studio space", "stop making offers", "recommend", "Noor"],
      "numbers": ["640", "510", "220", "90", "120", "15"]},
     pos="after", cx=3, waivers=["invented_subject"],
     note="facts: 640 applications (up from 510); 220 offers so far; ABOUT 90 accepted; studio fits 120 -> stop offers once acceptances reach 120; speaker recommends (not decides) closing portal on 15th instead of month end. Waiver invented_subject: Subject requested by the [Instruction]")

add2("multi_constraint", dict(F, sender="Camille", tone="friendly",
                              instruction="email to Peter, keep the line items and the total, and keep my question at the end",
                              transcript="peter the costs for the store opening materials are in. a few items, the window decals are three hundred and twenty dollars, the a frame sign is one eighty, and the five hundred loyalty cards are ninety five. that's five hundred ninety five dollars in total. delivery is free because it's over five hundred. do you want us to install the decals too or will your team do that"),
     "Hi Peter,\n\nThe costs for the store opening materials are in:\n\n- Window decals: $320\n- A-frame sign: $180\n- 500 loyalty cards: $95\n\nThat's $595 in total. Delivery is free because it's over $500.\n\nDo you want us to install the decals too, or will your team do that?\n\nBest,\nCamille",
     {"must_include": ["Peter", "Window decals", "A-frame sign", "loyalty cards", "Delivery is free", "install the decals", "Camille"], "numbers": ["320", "180", "500", "95", "595"]},
     pos="before", cx=3,
     note="facts: decals $320, A-frame $180 ('one eighty'), 500 loyalty cards $95; total $595 (arithmetic checks); free delivery because over $500 ('dollars' spoken, $ applied to all prices in the list); open question: us install decals OR client's team")

add2("multi_constraint", dict(F, sender="Zubair", locale="en-in", length="shorter",
                              instruction="make this professional, keep both conditions exactly and the head count",
                              transcript="hi manish so about the corporate membership for your company. we can do fifteen percent off for groups of twenty or more members, and if you sign up for twelve months instead of six we'll waive the joining fee for everyone. the current list you sent has eighteen names, so you'd need two more to get the discount. we'd need the final list and payment by the end of november for the december start"),
     "Hi Manish,\n\nFor your company's corporate membership, we can offer 15% off for groups of 20 or more members. If you sign up for 12 months instead of 6, we will waive the joining fee for everyone.\n\nYour current list has 18 names, so you would need 2 more to get the discount. We need the final list and payment by the end of November for the December start.\n\nBest,\nZubair",
     {"must_include": ["corporate membership", "or more", "If you sign up", "joining fee", "end of November", "December start", "Zubair"], "numbers": ["15", "20", "12", "6", "18", "2"]},
     pos="after", cx=3,
     note="facts: 15% off ONLY for groups of 20+; IF 12-month sign-up instead of 6 -> joining fee waived for all; list has 18, needs 2 more; final list + payment by end of November for December start. Counts written as digits throughout this record (mixed with 18/20) for consistency")

# ------------------------------------------------------------------ s2 chunk 3 (191-240)

add2("email", dict(F,
                   transcript="tell zubair the induction is on tuesday no wait wednesday at nine"),
     "Hi Zubair,\n\nThe induction is on Wednesday at 9.",
     {"must_include": ["Zubair", "induction", "Wednesday"], "numbers": ["9"], "must_not_include": ["Tuesday", "a.m."]},
     note="facts: self-correction applied: Tuesday -> Wednesday; at 9 (no a.m. added)")

add2("email", dict(R,
                   transcript="the shuttle to the open day leaves from gate two at eight fifteen"),
     "Hi,\n\nThe shuttle to the open day leaves from Gate 2 at 8:15.",
     {"must_include": ["shuttle", "open day", "Gate 2"], "numbers": ["8:15"], "must_not_include": ["a.m."]},
     note="facts: shuttle from Gate 2 at 8:15; no a.m. added")

add2("email", dict(F, sender="Tamsin", register="formal", locale="en-gb",
                   transcript="your locker rental ends on the thirtieth please empty it by then"),
     "Hello,\n\nYour locker rental ends on the 30th. Please empty it by then.\n\nRegards,\nTamsin",
     {"must_include": ["locker rental", "Please empty it by then", "Tamsin"], "numbers": ["30"]},
     note="facts: locker rental ends 30th; empty it by then ('please' dictated)")

add2("email", dict(R,
                   transcript="no we can't extend the free trial but your data stays for thirty days after it ends"),
     "Hi,\n\nNo, we can't extend the free trial, but your data stays for 30 days after it ends.",
     {"must_include": ["free trial", "data stays", "after it ends"], "numbers": ["30"], "min_negations": 2},
     note="facts: reply content dictated: NO trial extension; data kept 30 days after trial ends")

add2("email", dict(R,
                   transcript="noor thanks for sending the signed consent forms back so quickly"),
     "Hi Noor,\n\nThank you for sending the signed consent forms back so quickly.",
     {"must_include": ["Noor", "signed consent forms", "so quickly"], "must_not_include": ["appreciate", "great"]},
     note="facts: thanks for quick return of signed consent forms; no compliments added")

add2("email", dict(R, sender="Manish", register="casual",
                   transcript="hey rania the restock of the ceramic mugs lands tomorrow, cheers"),
     "Hi Rania,\n\nThe restock of the ceramic mugs lands tomorrow.\n\nCheers,\nManish",
     {"must_include": ["Rania", "ceramic mugs", "tomorrow", "Cheers,", "Manish"]},
     note="facts: mug restock lands tomorrow; dictated closing 'cheers' + sender name")

add2("email", dict(R, locale="en-in",
                   transcript="the security deposit of five thousand rupees is refundable when you return the access card"),
     "Hi,\n\nThe security deposit of ₹5,000 is refundable when you return the access card.",
     {"must_include": ["security deposit", "refundable", "access card"], "numbers": ["5,000"]},
     note="facts: ₹5,000 deposit (rupees spoken) refundable WHEN access card returned (condition kept)")

add2("email", dict(F, recipient="Kavya",
                   transcript="kavya the design crit is moved from two to two thirty today"),
     "Hi Kavya,\n\nThe design crit today has moved from 2 to 2:30.",
     {"must_include": ["design crit", "today"], "numbers": ["2", "2:30"]},
     note="facts: crit today moved 2 -> 2:30; no a.m./p.m. added")

add2("email", dict(R, sender="Camille", register="formal",
                   transcript="attached is the signed statement of work for the portuguese project"),
     "Hello,\n\nAttached is the signed statement of work for the Portuguese project.\n\nRegards,\nCamille",
     {"must_include": ["Attached", "signed statement of work", "Portuguese project", "Camille"]},
     note="facts: signed SOW for Portuguese project attached")

add2("email", dict(F, sender="Gustavo",
                   transcript="out until monday the twenty first, replies will be slow"),
     "Hi,\n\nI'm out until Monday the 21st, so replies will be slow.\n\nBest,\nGustavo",
     {"must_include": ["out until Monday", "replies will be slow", "Gustavo"], "numbers": ["21"]},
     note="facts: out-of-office until Monday the 21st (dictated date only); replies slow; no cover contact invented")

add2("email", dict(F, recipient="Abhay",
                   transcript="abhay your background check has cleared so you can hand in your notice"),
     "Hi Abhay,\n\nYour background check has cleared, so you can hand in your notice.",
     {"must_include": ["background check", "cleared", "hand in your notice"]},
     note="facts: background check cleared; may now resign from current job")

add2("email", dict(R, recipient="Sun-hee",
                   transcript="sun-hee the foil stamping costs an extra forty cents per card"),
     "Hi Sun-hee,\n\nThe foil stamping costs an extra 40 cents per card.",
     {"must_include": ["foil stamping", "per card"], "numbers": ["40"]},
     note="facts: foil stamping +40 cents per card")

add2("email", dict(R, length="shorter",
                   instruction="keep it to one line",
                   transcript="um so just so you know the gym app is down tonight from eleven to midnight for maintenance"),
     "Hi,\n\nThe gym app is down for maintenance tonight from 11 to midnight.",
     {"must_include": ["gym app", "maintenance", "tonight", "midnight"], "numbers": ["11"]},
     pos="before", cx=1,
     note="facts: app down tonight 11 to midnight for maintenance; one-line body")

add2("email", dict(F, recipient="Oliver", register="formal",
                   transcript="hi oliver your deferral request to the january intake has been approved"),
     "Dear Oliver,\n\nYour request to defer to the January intake has been approved.",
     {"must_include": ["Oliver", "defer", "January intake", "approved"]},
     note="facts: deferral to January intake approved; dictated 'hi oliver' adapted to formal 'Dear Oliver,'")

add2("email", dict(R,
                   transcript="your api key was reset at four p m, update it in any integrations that use it"),
     "Hi,\n\nYour API key was reset at 4 p.m. Please update it in any integrations that use it.",
     {"must_include": ["API key", "reset", "integrations"], "numbers": ["4"]},
     note="facts: API key reset at 4 p.m.; update it in integrations that use it ('please' softens the dictated imperative, no new request)")

add2("email", dict(R, recipient="Peter", locale="en-gb",
                   transcript="peter the parcels to ireland are held at customs, there's nothing we can do until thursday"),
     "Hi Peter,\n\nThe parcels to Ireland are being held at customs, and there's nothing we can do until Thursday.",
     {"must_include": ["Ireland", "customs", "nothing we can do until Thursday"], "min_negations": 1},
     note="facts: Ireland parcels held at customs; nothing can be done until Thursday")

add2("email", dict(R, recipient="Camille", sender="Rania",
                   transcript="camille the interview panel for the data role is you me and peter, sorry not peter, oliver. it's on the sixth from ten to one, three candidates back to back"),
     "Hi Camille,\n\nThe interview panel for the data role is you, me and Oliver. It's on the 6th from 10 to 1, with three candidates back to back.\n\nBest,\nRania",
     {"must_include": ["interview panel", "data role", "Oliver", "back to back", "Rania"], "numbers": ["6", "10", "1"], "must_not_include": ["Peter"]},
     waivers=["negation_lost"],
     note="waiver negation_lost: the only 'not' is part of the self-correction 'sorry not peter, oliver', which is applied, so no negation should survive. facts: self-correction applied: panel = Camille, speaker, Oliver (NOT Peter); 6th from 10 to 1; three candidates back to back")

add2("email", dict(F, recipient="Noor", sender="Zubair", locale="en-in",
                   transcript="noor following up again on invoice 1189 for the hindi subtitle work, forty five thousand rupees. it's now over sixty days past due. can you tell me if it's stuck in approval or if something's missing from our side"),
     "Hi Noor,\n\nI'm following up again on invoice 1189 for the Hindi subtitle work, for ₹45,000. It's now over 60 days past due.\n\nCould you tell me whether it's stuck in approval or whether something is missing from our side?\n\nBest,\nZubair",
     {"must_include": ["again", "Hindi subtitle work", "past due", "stuck in approval", "missing from our side", "Zubair"], "numbers": ["1189", "45,000", "60"]},
     note="facts: follow-up 'again' kept; invoice 1189, ₹45,000 (rupees spoken); over 60 days past due; question: stuck in approval OR missing something from our side")

add2("email", dict(R, sender="Kavya", register="formal",
                   transcript="the sauna has been out of order for three weeks now and nobody at the desk can tell me when it'll be fixed. i'm paying for the premium tier specifically for the sauna so i'd like either a date for the repair or a downgrade to the standard rate until it's working"),
     "Hello,\n\nThe sauna has been out of order for three weeks now, and nobody at the desk can tell me when it will be fixed.\n\nI am paying for the premium tier specifically for the sauna, so I would like either a date for the repair or a downgrade to the standard rate until it is working.\n\nRegards,\nKavya",
     {"must_include": ["out of order", "three weeks", "nobody at the desk", "premium tier", "date for the repair", "standard rate", "until it is working", "Kavya"], "min_negations": 1},
     note="facts: complaint; sauna out of order three weeks; desk can't say when fixed; premium tier paid for the sauna; wants repair date OR downgrade until working (both kept)")

add2("email", dict(R, recipient="Tamsin", sender="Oliver", locale="en-gb",
                   transcript="tamsin to answer your questions, yes the export includes deleted users, and no it doesn't include their activity logs. if you need the logs we can pull them separately but it takes about two working days"),
     "Hi Tamsin,\n\nTo answer your questions: yes, the export includes deleted users, and no, it doesn't include their activity logs.\n\nIf you need the logs, we can pull them separately, but it takes about two working days.\n\nBest,\nOliver",
     {"must_include": ["export includes deleted users", "activity logs", "If you need the logs", "about two working days", "Oliver"], "min_negations": 2},
     note="facts: reply content dictated: export INCLUDES deleted users; does NOT include activity logs; logs available separately IF needed, ABOUT two working days")

add2("email", dict(F, sender="Sun-hee", register="formal",
                   transcript="dear camille and abhay, i'm introducing you because abhay's firm is looking for a print partner for their annual reports and camille's studio handles exactly that kind of work. i'll leave it to you two to take it from here"),
     "Dear Camille and Abhay,\n\nI am introducing you because Abhay's firm is looking for a print partner for its annual reports, and Camille's studio handles exactly that kind of work.\n\nI will leave it to you two to take it from here.\n\nRegards,\nSun-hee",
     {"must_include": ["Camille", "Abhay", "print partner", "annual reports", "take it from here", "Sun-hee"]},
     note="facts: introduction; Abhay's firm seeks print partner for annual reports; Camille's studio does that work; speaker leaves it to them (no call/meeting invented)")

add2("email", dict(R, sender="Peter",
                   transcript="hi team from today all returns need a photo before we issue a refund. no photo no refund, even for regular customers. if a customer pushes back send it to me"),
     "Hi team,\n\nFrom today, all returns need a photo before we issue a refund. No photo, no refund, even for regular customers.\n\nIf a customer pushes back, send it to me.\n\nBest,\nPeter",
     {"must_include": ["From today", "photo before we issue a refund", "No photo, no refund", "regular customers", "If a customer pushes back", "Peter"], "min_negations": 2},
     note="facts: from today photo required before refund; no exceptions even for regulars (standing rule, own sentence); IF customer pushes back, escalate to speaker")

add2("email", dict(R, recipient="Gustavo", sender="Noor", locale="en-gb",
                   transcript="gustavo your enrolment pack is attached. you'll need to complete the online registration at enrol dot northbridge dot ac dot uk before the eighth, and bring the printed confirmation to induction"),
     "Hi Gustavo,\n\nYour enrolment pack is attached. You'll need to complete the online registration at enrol.northbridge.ac.uk before the 8th and bring the printed confirmation to induction.\n\nBest,\nNoor",
     {"must_include": ["enrolment pack", "attached", "enrol.northbridge.ac.uk", "printed confirmation", "induction", "Noor"], "numbers": ["8"]},
     note="facts: pack attached; online registration at enrol.northbridge.ac.uk (spoken URL) before the 8th; bring printed confirmation to induction; en-gb 'enrolment'")

add2("email", dict(F, sender="Camille",
                   transcript="hi everyone, change of plan for next week's client sessions. the kickoff with the hotel group moves from monday at ten to tuesday at two thirty, same room. the review with the museum team stays on wednesday at eleven but it's now on zoom not in person, link to follow. and the thursday site walk is cancelled because the scaffolding isn't up yet, we'll pick a new date once the contractor confirms. if any of this clashes with something let me know today"),
     "Hi everyone,\n\nThere's a change of plan for next week's client sessions.\n\nThe kickoff with the hotel group moves from Monday at 10 to Tuesday at 2:30, in the same room.\n\nThe review with the museum team stays on Wednesday at 11, but it's now on Zoom, not in person. The link will follow.\n\nThe Thursday site walk is cancelled because the scaffolding isn't up yet. We'll pick a new date once the contractor confirms.\n\nIf any of this clashes with something, let me know today.\n\nBest,\nCamille",
     {"must_include": ["hotel group", "Monday", "Tuesday", "same room", "museum team", "Wednesday", "Zoom", "site walk is cancelled", "scaffolding", "contractor confirms", "let me know today", "Camille"],
      "numbers": ["10", "2:30", "11"], "min_negations": 2},
     note="facts: kickoff Mon 10 -> Tue 2:30 same room; museum review stays Wed 11, now Zoom NOT in person, link to follow; Thursday site walk cancelled (scaffolding not up), new date once contractor confirms; clashes -> tell speaker today; no a.m./p.m. added")

add2("email", dict(R, recipient="Gustavo", sender="Rania", register="formal", locale="en-gb",
                   transcript="gustavo following your interviews last week we're pleased to offer you the position of senior localization engineer. the start date we discussed, the second of february, works for us. the full terms including the salary we talked about are set out in the attached contract. please read it carefully, sign it and send it back by the sixteenth of january. the offer is subject to two satisfactory references, and we'll contact your referees once you've accepted. if you have any questions about the terms contact noor in hr"),
     "Dear Gustavo,\n\nFollowing your interviews last week, we are pleased to offer you the position of Senior Localization Engineer. The start date we discussed, 2 February, works for us.\n\nThe full terms, including the salary we talked about, are set out in the attached contract. Please read it carefully, sign it and send it back by 16 January.\n\nThe offer is subject to two satisfactory references, and we will contact your referees once you have accepted.\n\nIf you have any questions about the terms, please contact Noor in HR.\n\nRegards,\nRania",
     {"must_include": ["Senior Localization Engineer", "February", "attached contract", "January", "two satisfactory references", "once you have accepted", "Noor in HR", "Rania"], "numbers": ["2", "16"], "must_not_include": ["£", "per annum", "benefits"]},
     note="facts: offer Senior Localization Engineer; start 2 February; salary only referenced, in attached contract (no figure invented); sign and return by 16 January; subject to two satisfactory references; referees contacted after acceptance; questions -> Noor in HR")

add2("email", dict(F, recipient="Oliver", sender="Manish",
                   transcript="oliver here's the breakdown for the onboarding package. it covers, data migration at two thousand four hundred dollars, three admin training sessions at three fifty each so one thousand fifty, and a custom reporting setup at one thousand eight hundred. the total is five thousand two hundred and fifty dollars, billed fifty percent upfront and fifty percent at go live. the price assumes no more than ten thousand records, anything above that is quoted separately"),
     "Hi Oliver,\n\nHere's the breakdown for the onboarding package:\n\n- Data migration: $2,400\n- 3 admin training sessions at $350 each: $1,050\n- Custom reporting setup: $1,800\n\nThe total is $5,250, billed 50% upfront and 50% at go-live. The price assumes no more than 10,000 records; anything above that is quoted separately.\n\nBest,\nManish",
     {"must_include": ["Data migration", "admin training sessions", "Custom reporting setup", "upfront", "go-live", "no more than", "quoted separately", "Manish"],
      "numbers": ["2,400", "350", "1,050", "1,800", "5,250", "50", "10,000"], "min_negations": 1},
     note="facts: migration $2,400; 3 training sessions x $350 = $1,050; reporting $1,800; total $5,250 (arithmetic checks); 50% upfront, 50% at go-live; assumes max 10,000 records, above quoted separately. 'dollars' spoken, $ applied to every price in the list; counts digits inside the priced list")

add2("email", dict(R, sender="Abhay", register="formal", locale="en-in",
                   transcript="hello this is about order PR-6620, the five hundred event invitations we collected on saturday. the gold ink has smudged on about a third of them and the envelopes are the wrong size, they're c6 and we ordered dl. we paid twelve thousand five hundred rupees in full. the event is on the twenty eighth so we need a reprint by the twenty fourth at the latest. if that's not possible we'd like a full refund"),
     "Hello,\n\nI am writing about order PR-6620, the 500 event invitations we collected on Saturday. The gold ink has smudged on about a third of them, and the envelopes are the wrong size: they are C6, and we ordered DL. We paid ₹12,500 in full.\n\nThe event is on the 28th, so we need a reprint by the 24th at the latest. If that is not possible, we would like a full refund.\n\nRegards,\nAbhay",
     {"must_include": ["PR-6620", "event invitations", "Saturday", "about a third", "C6", "DL", "in full", "at the latest", "full refund", "Abhay"],
      "numbers": ["500", "12,500", "28", "24"], "min_negations": 1},
     note="facts: complaint; order PR-6620; 500 invitations collected Saturday; gold ink smudged on ABOUT a third; envelopes C6 but DL ordered; ₹12,500 paid in full (rupees spoken); event 28th; reprint by 24th at latest; IF not possible -> full refund")

add2("email", dict(R, recipient="Manish", sender="Sun-hee", locale="en-gb",
                   transcript="manish a few updates. the structural engineer signed off the steel frame, so we're on track for the tender at the end of the month. on the kitchen, you asked whether the island could be longer. it can go to three point two metres but then the walkway drops to nine hundred millimetres, which is the minimum, so i wouldn't go further. separately the council has asked for a bat survey before any roof work, it's seasonal so it might push the roof works to may. and one admin thing, our new invoicing system sends invoices from accounts at studio north dot com, so please whitelist that address"),
     "Hi Manish,\n\nA few updates.\n\nThe structural engineer has signed off the steel frame, so we're on track for the tender at the end of the month.\n\nOn the kitchen, you asked whether the island could be longer. It can go to 3.2 metres, but then the walkway drops to 900 millimetres, which is the minimum, so I wouldn't go further.\n\nSeparately, the council has asked for a bat survey before any roof work. It's seasonal, so it might push the roof works to May.\n\nOne admin thing: our new invoicing system sends invoices from accounts@studionorth.com, so please whitelist that address.\n\nBest,\nSun-hee",
     {"must_include": ["structural engineer", "steel frame", "on track for the tender", "island", "walkway", "minimum", "bat survey", "might push the roof works to May", "accounts@studionorth.com", "whitelist", "Sun-hee"],
      "numbers": ["3.2", "900"], "min_negations": 1},
     note="facts: steel frame signed off, on track for tender at month end; island max 3.2 m -> walkway 900 mm (minimum), speaker advises no further; council wants bat survey before roof work, MIGHT push roof works to May; invoices from accounts@studionorth.com (spoken email), whitelist it")

add2("email", dict(F, sender="Zubair",
                   transcript="hi everyone thanks to all the trainers who covered extra shifts while the north branch was short staffed in october. between you, you covered forty one extra shifts. the overtime for those will be paid with the november salary. and from next week we've got two new trainers starting, so the rota should go back to normal"),
     "Hi everyone,\n\nThank you to all the trainers who covered extra shifts while the north branch was short-staffed in October. Between you, you covered 41 extra shifts.\n\nThe overtime for those will be paid with the November salary.\n\nFrom next week, we have two new trainers starting, so the rota should go back to normal.\n\nBest,\nZubair",
     {"must_include": ["extra shifts", "north branch", "October", "overtime", "November salary", "two new trainers", "should go back to normal", "Zubair"], "numbers": ["41"]},
     note="facts: thanks for covering shifts in October (north branch short-staffed); 41 extra shifts; overtime paid with November salary; two new trainers from next week; rota SHOULD normalise (hedge kept); no compliments added")

add2("email", dict(R, recipient="Peter", sender="Tamsin", locale="en-gb",
                   transcript="peter to get the localization connector working with your repo follow these steps. first install the github app from the integrations page. second pick the repository and the branch, use main not develop. third set the source file path to locales slash en slash messages dot json. and last run a test sync, it should create a pull request within five minutes. if it doesn't, send me the error from the sync log"),
     "Hi Peter,\n\nTo get the localization connector working with your repo, follow these steps:\n\n1. Install the GitHub app from the Integrations page.\n2. Pick the repository and the branch. Use main, not develop.\n3. Set the source file path to locales/en/messages.json.\n4. Run a test sync. It should create a pull request within 5 minutes.\n\nIf it doesn't, send me the error from the sync log.\n\nBest,\nTamsin",
     {"must_include": ["GitHub app", "Integrations page", "main, not develop", "locales/en/messages.json", "test sync", "pull request", "sync log", "Tamsin"], "numbers": ["5"], "min_negations": 2},
     note="facts: 4 ordered steps (first/second/third/last -> numbered): install GitHub app; pick repo + branch main NOT develop; source path locales/en/messages.json (spoken path); test sync SHOULD create PR within 5 minutes; IF not, send sync log error")

add2("email", dict(R, recipient="Zubair", sender="Kavya", register="formal", locale="en-gb",
                   transcript="zubair thank you for your application to the ma in translation studies. the committee has decided not to offer you a place this year. the main reason is that the programme requires a second language at c1 level and your application shows b2. if you reach c1 within the next twelve months you're welcome to apply again and your portfolio wouldn't need to be resubmitted. the application fee isn't refundable"),
     "Dear Zubair,\n\nThank you for your application to the MA in Translation Studies. The committee has decided not to offer you a place this year. The main reason is that the programme requires a second language at C1 level, and your application shows B2.\n\nIf you reach C1 within the next 12 months, you are welcome to apply again, and your portfolio would not need to be resubmitted.\n\nThe application fee is not refundable.\n\nRegards,\nKavya",
     {"must_include": ["MA in Translation Studies", "not to offer you a place", "C1", "B2", "If you reach C1", "portfolio", "not refundable", "Kavya"], "numbers": ["12"], "min_negations": 3, "must_not_include": ["sorry", "regret", "apolog"]},
     note="facts: rejection this year; reason: C1 second language required, applicant B2; IF C1 within 12 months -> may reapply and portfolio NOT needed again; fee NOT refundable (standing rule, own sentence); no apology/regret added")

add2("email", dict(F, recipient="Gustavo", sender="Noor", locale="en-gb",
                   transcript="gustavo for the spring order we'd like the following, three hundred linen shirts in white, two hundred in sand, and a hundred and fifty in olive. sizes split evenly from small to extra large. we need them packed in individual recycled bags, no plastic. and could you confirm whether the olive is the same dye lot as last season because customers noticed a colour difference"),
     "Hi Gustavo,\n\nFor the spring order, we'd like the following:\n\n- 300 linen shirts in white\n- 200 in sand\n- 150 in olive\n\nSizes should be split evenly from small to extra large. We need them packed in individual recycled bags, with no plastic.\n\nCould you also confirm whether the olive is the same dye lot as last season? Customers noticed a colour difference.\n\nBest,\nNoor",
     {"must_include": ["spring order", "linen shirts", "white", "sand", "olive", "split evenly", "recycled bags", "no plastic", "dye lot", "colour difference", "Noor"],
      "numbers": ["300", "200", "150"], "min_negations": 1},
     note="facts: 300 white, 200 sand, 150 olive linen shirts (3 items + cue 'the following' -> bullets); sizes split evenly S-XL; individual recycled bags, NO plastic; question: is olive same dye lot as last season (customers noticed colour difference)")

add2("email", dict(R, sender="Oliver",
                   transcript="hi all, two changes to how we handle late applications this cycle. first, anything that comes in after the deadline goes to the late queue in the portal, don't process it from your inbox. second, late applications can only be approved by camille or me, not by individual advisers. we're doing this because last year three late files got offers before anyone checked the references. this applies from monday"),
     "Hi all,\n\nThere are two changes to how we handle late applications this cycle.\n\nFirst, anything that comes in after the deadline goes to the late queue in the portal. Don't process it from your inbox.\n\nSecond, late applications can only be approved by Camille or me, not by individual advisers.\n\nWe're doing this because last year three late files got offers before anyone checked the references. This applies from Monday.\n\nBest,\nOliver",
     {"must_include": ["late applications", "late queue", "portal", "inbox", "Camille or me", "individual advisers", "references", "from Monday", "Oliver"], "min_negations": 2},
     note="facts: two changes from Monday: late items -> late queue, DON'T process from inbox; only Camille or speaker approve, NOT advisers; reason: last year three late files got offers before references checked; two items -> prose paragraphs")

add2("email", dict(R, recipient="Manish", sender="Kavya", locale="en-in",
                   transcript="manish replying to your question about the bulk order. yes we can do two hundred custom printed tote bags by the fifteenth, but only if you approve the artwork by this friday. the price is a hundred and eighty rupees per bag, so thirty six thousand rupees total, plus shipping. we'll need a fifty percent advance before printing. if you want a different bag colour than natural, add three days"),
     "Hi Manish,\n\nOn your question about the bulk order: yes, we can do 200 custom printed tote bags by the 15th, but only if you approve the artwork by this Friday.\n\nThe price is ₹180 per bag, so ₹36,000 in total, plus shipping. We'll need a 50% advance before printing.\n\nIf you want a bag colour other than natural, add three days.\n\nBest,\nKavya",
     {"must_include": ["bulk order", "tote bags", "only if you approve the artwork", "this Friday", "plus shipping", "advance before printing", "natural", "add three days", "Kavya"],
      "numbers": ["200", "15", "180", "36,000", "50"]},
     note="facts: reply content dictated; 200 tote bags by 15th ONLY IF artwork approved by this Friday; ₹180/bag, ₹36,000 total (arithmetic checks) plus shipping; 50% advance before printing; IF colour other than natural, +3 days")

# --- multi_constraint (225-240)

add2("multi_constraint", dict(R, register="formal", length="shorter",
                              instruction="keep the code exactly",
                              transcript="so your discount code for the membership renewal is RENEW25 and uh it works until sunday"),
     "Hello,\n\nYour membership renewal discount code is RENEW25, valid until Sunday.",
     {"must_include": ["RENEW25", "membership renewal", "until Sunday"]},
     pos="before", cx=2,
     note="facts: code RENEW25 verbatim; valid until Sunday")

add2("multi_constraint", dict(task="rewrite", format="email", tone="warm", header_style="full",
                              instruction="email to Peter and keep the times as they are",
                              transcript="your trial class is saturday at nine thirty, come ten minutes early"),
     "Hi Peter,\n\nYour trial class is on Saturday at 9:30. It would be great if you could come 10 minutes early.",
     {"must_include": ["Peter", "trial class", "Saturday", "early"], "numbers": ["9:30", "10"], "must_not_include": ["a.m."]},
     pos="after", cx=2,
     note="facts: trial class Saturday 9:30 (no a.m. added); come 10 minutes early; warm wording only")

add2("multi_constraint", dict(task="rewrite", format="email",
                              instruction="short email to Camille, no sign-off, and get the amount right",
                              transcript="camille the refund is forty two dollars no sorry forty eight dollars, it's gone back to your card"),
     "Hi Camille,\n\nThe refund is $48, and it has gone back to your card.",
     {"must_include": ["Camille", "refund", "back to your card"], "numbers": ["48"], "must_not_include": ["42", "Best,", "Thanks,"]},
     pos="before", cx=3,
     note="facts: self-correction applied: $42 -> $48 (42 must not appear); refund back to card; no sign-off")

add2("multi_constraint", dict(F, locale="en-gb",
                              instruction="professional, and keep the reference exactly",
                              transcript="your booking reference for the studio tour is ST-4471, please arrive at the main reception"),
     "Hi,\n\nYour booking reference for the studio tour is ST-4471. Please arrive at the main reception.",
     {"must_include": ["ST-4471", "studio tour", "main reception"]},
     pos="after", cx=2,
     note="facts: reference ST-4471 verbatim; arrive at main reception ('please' dictated); no time invented")

add2("multi_constraint", dict(R, sender="Abhay", tone="confident",
                              instruction="keep it under 20 words",
                              transcript="i think uh we can probably get the menus printed by thursday if the paper arrives"),
     "Hi,\n\nWe can probably get the menus printed by Thursday if the paper arrives.\n\nBest,\nAbhay",
     {"must_include": ["probably", "menus", "Thursday", "if the paper arrives", "Abhay"], "max_words": 20},
     pos="before", cx=2,
     note="facts: PROBABLY printed by Thursday (fact hedge kept under confident tone); condition IF paper arrives kept; stacked 'I think' dropped")

add2("multi_constraint", dict(task="rewrite", format="email", register="formal", header_style="full",
                              instruction="email to Sun-hee and keep both dates",
                              transcript="the graduation photos can be collected on the twelfth or the thirteenth"),
     "Dear Sun-hee,\n\nThe graduation photos can be collected on the 12th or the 13th.",
     {"must_include": ["Sun-hee", "graduation photos", "collected"], "numbers": ["12", "13"]},
     pos="after", cx=3,
     note="facts: collection 12th OR 13th (alternative kept)")

add2("multi_constraint", dict(R, sender="Rania", tone="friendly",
                              instruction="don't add anything that wasn't said",
                              transcript="the team lunch is on thursday at one at the usual place"),
     "Hi,\n\nJust a heads-up: the team lunch is on Thursday at 1 at the usual place.\n\nBest,\nRania",
     {"must_include": ["team lunch", "Thursday", "usual place", "Rania"], "numbers": ["1"], "must_not_include": ["p.m.", "see you"]},
     pos="before", cx=2,
     note="facts: team lunch Thursday at 1 (no p.m. added), usual place; friendly wording only, no 'see you there'")

add2("multi_constraint", dict(R, recipient="Oliver", sender="Tamsin", register="formal",
                              instruction="keep the hedge and the condition exactly, and no subject line",
                              transcript="so the medical device manual is about two hundred pages and if the regulatory glossary is ready by the tenth we should be able to deliver the reviewed german version by the end of next month, but i can't guarantee that until we see the glossary"),
     "Dear Oliver,\n\nThe medical device manual is about 200 pages. If the regulatory glossary is ready by the 10th, we should be able to deliver the reviewed German version by the end of next month. However, I cannot guarantee that until we see the glossary.\n\nRegards,\nTamsin",
     {"must_include": ["about 200", "If the regulatory glossary is ready", "should be able to", "German version", "end of next month", "cannot guarantee"], "numbers": ["200", "10"], "min_negations": 1, "must_not_include": ["Subject:"]},
     pos="after", cx=3,
     note="facts: manual ABOUT 200 pages; IF glossary ready by 10th -> SHOULD deliver reviewed German version by end of next month; can't guarantee until glossary seen; model doesn't translate, it reports the delivery")

add2("multi_constraint", dict(F, recipient="Noor", locale="en-gb",
                              instruction="polite email, keep the old and new times exactly, and don't add an apology",
                              transcript="noor your campus tour on friday is moving from ten a m to twelve thirty p m because the main hall is booked for an exam. the meeting point is still the visitor centre"),
     "Hi Noor,\n\nYour campus tour on Friday is moving from 10 a.m. to 12:30 p.m., as the main hall is booked for an exam. The meeting point is still the visitor centre.",
     {"must_include": ["campus tour", "Friday", "main hall", "exam", "still the visitor centre"], "numbers": ["10", "12:30"], "must_not_include": ["sorry", "apolog", "inconvenience"]},
     pos="before", cx=3,
     note="facts: tour Friday moved 10 a.m. -> 12:30 p.m.; reason main hall booked for exam; meeting point still visitor centre; no apology")

add2("multi_constraint", dict(task="rewrite", format="email", sender="Gustavo", locale="en-gb",
                              instruction="make this an email to the whole studio, keep the list of three tools, plain text",
                              transcript="so starting monday we're standardising on a few tools. figma for all design files, notion for meeting notes, and linear for tracking bugs. don't start new files in the old tools, existing ones can stay where they are"),
     "Hi everyone,\n\nStarting Monday, we're standardising on a few tools:\n\n- Figma for all design files\n- Notion for meeting notes\n- Linear for tracking bugs\n\nDon't start new files in the old tools. Existing ones can stay where they are.\n\nBest,\nGustavo",
     {"must_include": ["Starting Monday", "Figma", "Notion", "Linear", "old tools", "Existing ones can stay", "Gustavo"], "min_negations": 1},
     pos="after", cx=3,
     note="facts: from Monday: Figma design, Notion notes, Linear bugs (3 items + cue 'a few tools' -> bullets); NO new files in old tools; existing can stay; whole studio -> 'Hi everyone,'")

add2("multi_constraint", dict(task="rewrite", format="email", sender="Kavya",
                              instruction="professional email to the supplier, keep every quantity and both deadlines, and no bullet points",
                              transcript="hi peter we want to confirm the reorder. it's six hundred units of the recycled notebooks, split four hundred lined and two hundred dotted, and three hundred of the kraft gift boxes. the notebooks need to reach our warehouse by the twentieth for the holiday campaign, and the gift boxes can come later, as long as they're here by the fifth of next month. if the dotted ones are going to be late, ship the lined ones first rather than holding the whole order"),
     "Hi Peter,\n\nWe want to confirm the reorder: 600 units of the recycled notebooks, split into 400 lined and 200 dotted, and 300 of the kraft gift boxes.\n\nThe notebooks need to reach our warehouse by the 20th for the holiday campaign. The gift boxes can come later, as long as they're here by the 5th of next month.\n\nIf the dotted ones are going to be late, ship the lined ones first rather than holding the whole order.\n\nBest,\nKavya",
     {"must_include": ["recycled notebooks", "lined", "dotted", "kraft gift boxes", "holiday campaign", "as long as", "next month", "ship the lined ones first", "Kavya"],
      "numbers": ["600", "400", "200", "300", "20", "5"]},
     pos="before", cx=3,
     note="facts: 600 notebooks = 400 lined + 200 dotted; 300 kraft gift boxes; notebooks by 20th (holiday campaign); boxes later, as long as they arrive by 5th of next month (condition kept); IF dotted late -> ship lined first, don't hold order; prose per instruction")

add2("multi_constraint", dict(task="rewrite", format="email", register="formal", locale="en-gb", sender="Camille",
                              instruction="formal email to the dean, keep every figure, keep my recommendation as a recommendation, and add the subject Scholarship budget",
                              transcript="so the scholarship budget for next year is two hundred and fifty thousand pounds, down from three hundred thousand. at the current award of five thousand per student that's fifty scholarships instead of sixty. one option is to keep the award the same and fund fewer students, the other is to reduce each award to four thousand and keep around sixty two. my recommendation is the second option because applicant numbers are up, but the committee should decide"),
     "Subject: Scholarship budget\n\nHello,\n\nThe scholarship budget for next year is £250,000, down from £300,000. At the current award of £5,000 per student, that is 50 scholarships instead of 60.\n\nOne option is to keep the award the same and fund fewer students. The other is to reduce each award to £4,000 and keep around 62.\n\nMy recommendation is the second option because applicant numbers are up, but the committee should decide.\n\nRegards,\nCamille",
     {"must_include": ["Subject: Scholarship budget", "next year", "fewer students", "around 62", "recommendation", "committee should decide", "Camille"],
      "numbers": ["250,000", "300,000", "5,000", "50", "60", "4,000", "62"]},
     pos="after", cx=4, waivers=["invented_subject"],
     note="facts: budget £250,000 down from £300,000 ('pounds' spoken once, £ applied to every money figure in the record); £5,000 award -> 50 not 60 scholarships; option A same award fewer students; option B £4,000 award, AROUND 62; speaker recommends B, committee decides; dean not named -> formal 'Hello,'. Waiver invented_subject: Subject requested by the [Instruction]")

add2("multi_constraint", dict(R, recipient="Tamsin", sender="Zubair", tone="warm", locale="en-gb",
                              instruction="keep both options and the deadline, and don't promise anything I didn't say",
                              transcript="tamsin about your question on the family plan. there are two ways to do it. you can add your partner to your current membership for twenty five pounds a month extra, or you can both move to the family plan which is seventy pounds a month and includes the kids' swim classes. either way the change starts from the first of the next billing month. if you want to switch before the december billing let the desk know by the twenty fifth"),
     "Hi Tamsin,\n\nOn your question about the family plan, there are two ways to do it.\n\nYou can add your partner to your current membership for an extra £25 a month, or you can both move to the family plan, which is £70 a month and includes the kids' swim classes.\n\nEither way, the change starts from the 1st of the next billing month. If you want to switch before the December billing, just let the desk know by the 25th.\n\nBest,\nZubair",
     {"must_include": ["family plan", "add your partner", "kids' swim classes", "Either way", "next billing month", "December billing", "by the 25th", "Zubair"], "numbers": ["25", "70", "1"]},
     pos="before", cx=3,
     note="facts: option A add partner +£25/month; option B family plan £70/month incl. kids' swim classes (both kept; 'pounds' spoken for both); change starts 1st of next billing month either way; IF switching before December billing -> tell desk by 25th; warm wording only, no thank-you invented")

add2("multi_constraint", dict(task="rewrite", format="email", length="shorter", sender="Oliver", header_style="full",
                              instruction="email to Abhay, keep all the steps in order and the file names",
                              transcript="abhay so to reset the onboarding demo before the client call, uh, first log in as the demo admin. then go to settings, then data, and click reset sample data. it takes a couple of minutes. after that upload demo_clients_v2.csv from the shared folder, not the old v1 file because that has the wrong currency. and finally check that the dashboard shows twelve active projects, if it shows fewer the import failed"),
     "Hi Abhay,\n\nTo reset the onboarding demo before the client call:\n\n1. Log in as the demo admin.\n2. Go to Settings, then Data, and click Reset sample data. It takes a couple of minutes.\n3. Upload demo_clients_v2.csv from the shared folder, not the old v1 file, which has the wrong currency.\n4. Check that the dashboard shows 12 active projects. If it shows fewer, the import failed.\n\nBest,\nOliver",
     {"must_include": ["demo admin", "Reset sample data", "couple of minutes", "demo_clients_v2.csv", "not the old v1 file", "wrong currency", "If it shows fewer, the import failed", "Oliver"], "numbers": ["12"], "min_negations": 1},
     pos="after", cx=3,
     note="facts: ordered steps (first/then/after that/finally -> numbered): log in as demo admin; Settings > Data > reset sample data (couple of minutes); upload demo_clients_v2.csv NOT v1 (wrong currency); dashboard must show 12 active projects, fewer = import failed")

add2("multi_constraint", dict(task="rewrite", format="email", locale="en-in", register="formal", sender="Manish",
                              instruction="email to the candidate, keep all dates and the condition, and don't mention salary or benefits",
                              transcript="camille we're happy to confirm your internship with our onboarding team from the sixth of january to the fourth of april. the stipend details are in the attached letter. you'll need to bring your college no objection certificate on the first day. if your college exams overlap with any of those dates tell us by the twentieth of december so we can adjust the schedule"),
     "Dear Camille,\n\nWe are happy to confirm your internship with our onboarding team from 6 January to 4 April. The stipend details are in the attached letter.\n\nYou will need to bring your college no objection certificate on the first day.\n\nIf your college exams overlap with any of those dates, please tell us by 20 December so that we can adjust the schedule.\n\nRegards,\nManish",
     {"must_include": ["Camille", "internship", "onboarding team", "January", "April", "attached letter", "no objection certificate", "first day", "December", "adjust the schedule", "Manish"],
      "numbers": ["6", "4", "20"], "must_not_include": ["salary", "benefits", "₹"]},
     pos="before", cx=4,
     note="facts: internship 6 January to 4 April; stipend only referenced (in attached letter, no figure invented); bring college NOC on first day; IF exams overlap -> tell by 20 December so schedule can be adjusted")

add2("multi_constraint", dict(task="rewrite", format="email", sender="Peter", locale="en-gb",
                              instruction="write it as an email to Rania, plain and direct, keep the three issues as a numbered list since they're in priority order, and keep my question",
                              transcript="rania a few problems with this week's catalogue run, in order of priority. number one, the colour on the cover is off, the red is printing closer to orange. number two, pages forty to forty eight are bound in the wrong order in about fifty copies. number three, the delivery boxes aren't labelled. can we reprint the affected copies before monday or do we need to push the mailing date"),
     "Hi Rania,\n\nThere are a few problems with this week's catalogue run, in order of priority:\n\n1. The colour on the cover is off. The red is printing closer to orange.\n2. Pages 40 to 48 are bound in the wrong order in about 50 copies.\n3. The delivery boxes aren't labelled.\n\nCan we reprint the affected copies before Monday, or do we need to push the mailing date?\n\nBest,\nPeter",
     {"must_include": ["catalogue run", "priority", "cover", "closer to orange", "wrong order", "about 50", "aren't labelled", "before Monday", "mailing date", "Peter"],
      "numbers": ["40", "48", "50"], "min_negations": 1},
     pos="after", cx=4,
     note="facts: 3 issues in priority order (numbered per instruction + 'number one' cues): cover red prints closer to orange; pages 40-48 misbound in ABOUT 50 copies; boxes not labelled; question: reprint before Monday OR push mailing date (both kept)")


save(OUT2, rows2)
print(len(rows2), "records ->", OUT2)
