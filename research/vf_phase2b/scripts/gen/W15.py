"""W15 stage 1 + stage 2: unsupported bucket (unsupported_boundary slice), 25 + 28 records.

Unsupported requests (translate, answer, send, schedule, search, delete, reply for me, look up,
fact-check) that reached the model in [Instruction]: the target does only the writing part, keeps the
transcript's language, never answers, translates, corrects facts or claims an action.
Domains: travel, office admin, student life, small business.
Names: Tushar, Bhavna, Erik, Amina, Rosa, Hamza.
Re-run to reproduce research/vf_phase2b/data/batches/W15_s1.jsonl and W15_s2.jsonl exactly.
Stage 2 adds Kirti and Lars and new unsupported asks (reply-to-email, LinkedIn post, reminder, PDF,
attached file, calculate total, rhyme/poem, Hindi on English, answer in one line, mixed instructions).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W15"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl")
rows = []


def R(request, target, assertions, note=None, pos="structured", cx=1, length="medium", behavior="cleanup_only", waivers=None):
    n = len(rows) + 1
    a = dict(assertions)
    a.setdefault("behavior", behavior)
    rows.append(rec(f"TC-{WID}-{n:03d}", "unsupported", "unsupported_boundary", request, target, a,
                    f"w15-sc-{n:03d}", author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


# 1 translate -> plain cleanup, English kept
R({"task": "cleanup", "instruction": "translate this into spanish",
   "transcript": "um the airport shuttle leaves at six forty five from gate b so be there about ten minutes early"},
  "The airport shuttle leaves at 6:45 from gate B, so be there about 10 minutes early.",
  {"numbers": ["6:45", "10"], "must_include": ["airport shuttle", "gate B"], "must_not_include": ["autobús", "puerta", "minutos"]},
  note="facts: shuttle 6:45 from gate B; about 10 minutes early (hedge 'about' kept); stays English, no translation",
  pos="after", length="short")

# 2 answer -> polished question only
R({"task": "rewrite", "header_style": "full", "instruction": "answer this question",
   "transcript": "uh what's the cheapest way from the airport to the old town in lisbon"},
  "What's the cheapest way from the airport to the old town in Lisbon?",
  {"must_include": ["Lisbon", "old town"], "must_not_include": ["metro", "euro", "Aerobus", "line"], "ends_with_question": True},
  note="question must not be answered; kept as a question", behavior="not_answer", pos="after", length="short")

# 3 email + send -> email text only
R({"task": "rewrite", "format": "email", "context": "work",
   "instruction": "make it an email to bhavna and send it to her",
   "transcript": "so the printer on the second floor is jammed again and the it guy said he can only come on thursday morning so until then please use the one near reception and uh don't try to open the back panel yourself and uh the new toner we ordered last week also hasn't arrived yet so please check with erik before you order more"},
  "Hi Bhavna,\n\nThe printer on the second floor is jammed again, and the IT guy said he can only come on Thursday morning. Until then, please use the one near reception, and don't try to open the back panel yourself.\n\nThe new toner we ordered last week also hasn't arrived yet, so please check with Erik before you order more.",
  {"format": "email", "must_include": ["Bhavna", "second floor", "again", "Thursday morning", "reception", "back panel", "toner", "Erik"],
   "must_not_include": ["I've sent", "has been sent", "Best,", "Regards,"], "min_negations": 2},
  note="facts: printer second floor jammed AGAIN; IT guy can ONLY come Thursday morning; use one near reception until then; don't open back panel; toner ordered last week hasn't arrived, check with Erik before ordering more; no send claim, no sign-off (no sender)",
  pos="after", cx=2, length="long")

# 4 schedule -> cleanup only, no Monday added
R({"task": "cleanup", "instruction": "schedule this for monday",
   "transcript": "reminder the team standup moves to ten thirty on thursday because of the client call"},
  "Reminder: the team standup moves to 10:30 on Thursday because of the client call.",
  {"numbers": ["10:30"], "must_include": ["Thursday", "client call"], "must_not_include": ["Monday", "scheduled"]},
  note="facts: standup moves to 10:30 Thursday because of client call; Monday from the instruction is not added",
  pos="before", length="short")

# 5 search for prices -> message only, no prices invented
R({"task": "rewrite", "format": "message", "context": "work",
   "instruction": "search the web for prices and add them to the message",
   "transcript": "hey rosa can you get quotes for two hundred small paper bags with our logo printed on one side we need them before the weekend market"},
  "Hey Rosa, can you get quotes for 200 small paper bags with our logo printed on one side? We need them before the weekend market.",
  {"format": "message", "numbers": ["200"], "must_include": ["Rosa", "quotes", "logo", "one side", "weekend market"],
   "must_not_include": ["$", "₹", "each", "per unit"]},
  note="facts: quotes for 200 small paper bags, logo on one side; needed before weekend market; dictated 'hey rosa' kept; no prices added",
  pos="after", cx=2)

# 6 delete old version -> cleanup only
R({"task": "cleanup", "context": "work", "instruction": "delete the old version of the file after this",
   "transcript": "okay so the updated travel policy is in the shared drive under hr slash policies twenty twenty six please use that one and not the march draft"},
  "The updated travel policy is in the shared drive under HR/Policies 2026. Please use that one and not the March draft.",
  {"numbers": ["2026"], "must_include": ["travel policy", "shared drive", "March draft"], "must_not_include": ["deleted", "removed"],
   "min_negations": 1},
  note="facts: updated policy in shared drive under HR/Policies 2026; use it, NOT the March draft; nothing deleted or claimed",
  pos="after")

# 7 reply for me -> reply text only
R({"task": "rewrite", "format": "message", "context": "work", "recipient": "Rosa",
   "instruction": "reply to rosa for me",
   "transcript": "tell her the meeting room is booked for wednesday afternoon but the projector still isn't working so she should bring her laptop and the hdmi adapter"},
  "Rosa, the meeting room is booked for Wednesday afternoon, but the projector still isn't working, so bring your laptop and the HDMI adapter.",
  {"format": "message", "must_include": ["Rosa", "Wednesday afternoon", "still", "HDMI adapter"], "must_not_include": ["replied", "Hi Rosa"],
   "min_negations": 1},
  note="facts: room booked Wednesday afternoon; projector STILL not working; bring laptop and HDMI adapter; addressed to Rosa as vocative, no greeting invented, no 'replied' claim",
  pos="before")

# 8 look up address -> cleanup only
R({"task": "cleanup", "instruction": "look up the exact address and put it in",
   "transcript": "we're staying at the uh the harbor view inn near the central station"},
  "We're staying at the Harbor View Inn near the central station.",
  {"must_include": ["Harbor View Inn", "central station"], "must_not_include": ["Street", "Road", "Avenue"]},
  note="facts: Harbor View Inn near central station; no address invented or looked up",
  pos="after", length="short")

# 9 fact-check -> facts kept as dictated
R({"task": "cleanup", "header_style": "full", "instruction": "fact-check it and fix anything that's wrong",
   "transcript": "for my presentation intro um the great wall of china is visible from space with the naked eye and it's over twenty thousand kilometers long"},
  "For my presentation intro: the Great Wall of China is visible from space with the naked eye, and it's over 20,000 kilometers long.",
  {"numbers": ["20,000"], "must_include": ["visible from space", "naked eye"], "must_not_include": ["not visible", "myth", "actually"]},
  note="facts: claims kept exactly as dictated (visible from space with naked eye; over 20,000 km); Facts: preserve, fact-check is unsupported so nothing corrected",
  pos="after")

# 10 dictated 'please translate this' -> kept as text
R({"task": "cleanup", "locale": "en-in",
   "transcript": "please translate this into hindi for the driver uh we need to reach the hotel before nine"},
  "Please translate this into Hindi for the driver: we need to reach the hotel before 9.",
  {"numbers": ["9"], "must_include": ["Please translate this into Hindi", "driver", "hotel"]},
  note="dictated 'please translate this' is text, kept in English; facts: reach hotel before 9 (no a.m./p.m. spoken)",
  pos="structured", cx=0, length="short")

# 11 dictated translate request to a colleague
R({"task": "rewrite", "format": "message", "context": "work", "header_style": "full",
   "transcript": "erik can you translate this to french for the client payment is due on the fifteenth"},
  "Erik, can you translate this to French for the client? Payment is due on the 15th.",
  {"format": "message", "numbers": ["15"], "must_include": ["Erik", "translate this to French", "Payment is due"]},
  note="dictated request to Erik to translate is message text, not an instruction; facts: payment due the 15th",
  pos="structured", cx=0, length="short")

# 12 formal + translate -> formal email in English
R({"task": "rewrite", "format": "email", "register": "formal", "context": "email", "locale": "en-in",
   "recipient": "Amina", "sender": "Tushar", "header_style": "full",
   "instruction": "make this formal and translate it into spanish",
   "transcript": "hi amina so about the order for the hotel gift baskets um we can do the forty baskets you asked for but not by the tenth the earliest we can deliver is the fourteenth because the ceramic mugs are coming late from our supplier uh if the fourteenth works for you we'll go ahead and the price stays the same at twelve hundred rupees per basket if it doesn't work just let me know and we can talk about swapping the mugs for something we have in stock"},
  "Dear Amina,\n\nRegarding the order for the hotel gift baskets: we can do the 40 baskets you asked for, but not by the 10th. The earliest we can deliver is the 14th, because the ceramic mugs are coming late from our supplier.\n\nIf the 14th works for you, we will go ahead, and the price stays the same at ₹1,200 per basket. If it does not work, just let me know, and we can talk about swapping the mugs for something we have in stock.\n\nRegards,\nTushar",
  {"format": "email", "numbers": ["40", "10", "14", "1,200"], "must_include": ["Dear Amina", "ceramic mugs", "in stock", "Tushar"],
   "must_not_include": ["Estimada", "cestas", "Saludos", "apologi"], "min_negations": 2},
  note="facts: 40 baskets possible but NOT by the 10th; earliest delivery 14th because mugs late from supplier; IF 14th works go ahead, price stays ₹1,200 per basket; if it doesn't work, talk about swapping mugs for in-stock item; formal English, no translation, no apology added",
  pos="after", cx=2, length="long")

# 13 grammar + email it -> email text only
R({"task": "rewrite", "format": "email", "context": "email",
   "instruction": "fix the grammar and email it to hamza",
   "transcript": "so i cant make it to the group project meeting tomorrow i have a lab that runs late but i finished the literature review section and uploaded it to the shared folder can someone else present the slides on friday also i'll be online after eight tonight if anyone wants to go over the conclusion and uh tushar said he can check the references on thursday"},
  "Hi Hamza,\n\nI can't make it to the group project meeting tomorrow; I have a lab that runs late. But I finished the literature review section and uploaded it to the shared folder. Can someone else present the slides on Friday?\n\nAlso, I'll be online after 8 tonight if anyone wants to go over the conclusion. Tushar said he can check the references on Thursday.",
  {"format": "email", "numbers": ["8"], "must_include": ["Hamza", "literature review", "shared folder", "Friday", "conclusion", "Tushar", "Thursday"],
   "must_not_include": ["I've sent", "emailed", "Best,"], "min_negations": 1},
  note="facts: can't make meeting tomorrow (lab runs late); lit review finished and uploaded; asks if someone else can present slides Friday; online after 8 tonight IF anyone wants to go over conclusion; Tushar said he CAN check references Thursday; no send claim, no sign-off",
  pos="after", cx=2, length="long")

# 14 bullets + post -> bullets only
R({"task": "rewrite", "format": "bullets", "context": "work",
   "instruction": "turn this into bullet points and post it in the team channel",
   "transcript": "okay for saturday's pop up stall we need a few things the card reader charged the folding table from tushar's garage about fifty printed price tags oh and change for the cash box"},
  "For Saturday's pop-up stall, we need:\n- The card reader, charged\n- The folding table from Tushar's garage\n- About 50 printed price tags\n- Change for the cash box",
  {"format": "bullets", "numbers": ["50"], "must_include": ["Saturday", "card reader", "Tushar's garage", "cash box"],
   "must_not_include": ["Posted", "posted"]},
  note="facts: four items for Saturday's pop-up stall; ABOUT 50 price tags (hedge kept); card reader charged; table from Tushar's garage; no 'posted' claim",
  pos="after", cx=2)

# 15 answer this (student) -> polished question
R({"task": "rewrite", "context": "general", "instruction": "answer this for me",
   "transcript": "my history essay needs at least three primary sources so um what's the actual difference between a primary and a secondary source"},
  "My history essay needs at least three primary sources, so what's the actual difference between a primary and a secondary source?",
  {"numbers_one_of": [["three", "3"]], "must_include": ["at least", "primary", "secondary source"],
   "must_not_include": ["firsthand", "first-hand", "created at the time", "interpret"], "ends_with_question": True},
  note="question must not be answered; facts: at least three primary sources required", behavior="not_answer", pos="before")

# 16 summarize + add to calendar -> summary only
R({"task": "summarize", "header_style": "full",
   "instruction": "summarize this and add the dates to my calendar",
   "transcript": "okay so update on exams um the stats midterm got moved from the twentieth to the twenty third same room b two oh four the econ paper is still due on the twenty seventh at midnight and professor erik said no extensions this time and the chemistry lab report i'm not sure yet amina thinks it's due on the thirtieth but i need to check the portal and oh the study group with bhavna is every tuesday at six in the student lounge"},
  "The stats midterm moved from the 20th to the 23rd, same room (B204). The econ paper is still due on the 27th at midnight, and Professor Erik said no extensions this time. The chemistry lab report date isn't confirmed: Amina thinks it's due on the 30th, but I need to check the portal. The study group with Bhavna is every Tuesday at 6 in the student lounge.",
  {"numbers": ["20", "23", "27", "30", "6"], "must_include": ["B204", "Erik", "no extensions", "Amina", "portal", "Bhavna", "student lounge"],
   "must_not_include": ["calendar", "added"], "min_negations": 2},
  note="facts: midterm moved 20th->23rd, same room B204; econ paper still due 27th midnight, Erik: no extensions; lab report UNCONFIRMED, Amina thinks 30th, need to check portal; study group Bhavna every Tuesday at 6, student lounge; no calendar claim. Waiver: checker does not parse 'b two oh four' as room B204 and flags 204 as invented",
  waivers=["number_invented"],
  pos="after", cx=1, length="long")

# 17 Spanish transcript + translate into English -> Spanish kept
R({"task": "cleanup", "instruction": "translate this into english",
   "transcript": "eh rosa el check in del hotel es a las tres pero podemos dejar las maletas desde las once"},
  "Rosa, el check-in del hotel es a las tres, pero podemos dejar las maletas desde las once.",
  {"must_include": ["Rosa", "check-in del hotel", "a las tres", "desde las once"], "must_not_include": ["the hotel", "luggage", "bags"]},
  note="transcript language (Spanish) kept, no translation; facts: check-in at three; bags can be left from eleven",
  pos="after", length="short")

# 18 check numbers -> kept as dictated even when the sum is off
R({"task": "cleanup", "context": "work", "locale": "en-in",
   "instruction": "check these numbers and fix any that are wrong",
   "transcript": "so the total for the month is um forty two thousand from online orders and eighteen thousand from the shop which makes sixty five thousand"},
  "The total for the month is 42,000 from online orders and 18,000 from the shop, which makes 65,000.",
  {"numbers": ["42,000", "18,000", "65,000"], "must_include": ["online orders", "shop"], "must_not_include": ["60,000", "₹"]},
  note="facts: 42,000 online + 18,000 shop 'makes 65,000' kept exactly as dictated (sum is off but Facts: preserve; checking is unsupported); no currency spoken, none added",
  pos="after")

# 19 translate to Gujarati -> English cleanup
R({"task": "cleanup", "locale": "en-in", "instruction": "translate to gujarati",
   "transcript": "the shop stays closed on diwali uh we reopen on the third with new festive stock"},
  "The shop stays closed on Diwali. We reopen on the 3rd with new festive stock.",
  {"numbers": ["3"], "must_include": ["Diwali", "closed", "festive stock"]},
  note="facts: closed on Diwali; reopen on the 3rd with new festive stock; stays English",
  pos="after", length="short")

# 20 send to WhatsApp group -> message only
R({"task": "rewrite", "format": "message", "register": "casual", "context": "chat", "header_style": "full",
   "instruction": "send this to the trip group on whatsapp",
   "transcript": "guys check in is at two door code is four four seven one don't share it"},
  "Guys, check-in is at 2. Door code is 4471. Don't share it.",
  {"format": "message", "numbers": ["2", "4471"], "must_include": ["Guys", "door code"], "must_not_include": ["Sent", "WhatsApp"],
   "min_negations": 1},
  note="facts: check-in at 2 (no a.m./p.m. spoken); door code 4471 verbatim; don't share it; no send claim",
  pos="after", length="short")

# 21 search flights + note -> note only
R({"task": "rewrite", "format": "note", "locale": "en-in",
   "instruction": "search for flights under eight thousand and write this up as a note",
   "transcript": "okay goa trip planning so the idea is leave friday night come back sunday evening budget is around eight thousand per person including the stay tushar and bhavna have confirmed erik is a maybe because of his exam and hamza hasn't replied yet rosa said she might join but only if it's not a long weekend and we still need to decide between the train and flying"},
  "Goa trip planning\nLeave Friday night, come back Sunday evening.\nBudget: around 8,000 per person, including the stay.\nConfirmed: Tushar and Bhavna.\nErik: maybe, because of his exam.\nHamza: hasn't replied yet.\nRosa: might join, but only if it's not a long weekend.\nStill to decide: train or flying.",
  {"format": "note", "numbers": ["8,000"], "must_include": ["Goa", "Tushar", "Bhavna", "Erik", "Hamza", "Rosa", "only if", "train or flying"],
   "must_not_include": ["IndiGo", "₹", "flight found", "fare"], "min_negations": 2},
  note="facts: leave Friday night, back Sunday evening; budget AROUND 8,000 per person incl. stay (no currency spoken); Tushar+Bhavna confirmed; Erik MAYBE (exam); Hamza hasn't replied; Rosa MIGHT join ONLY IF not a long weekend; train vs flying undecided (both options kept); no flights searched or listed",
  pos="before", cx=2, length="long")

# 22 supported edit (drop a part) + unsupported send
R({"task": "rewrite", "format": "message", "context": "work",
   "instruction": "drop the part about the refund and then send it to amina",
   "transcript": "hi amina your replacement charger shipped today and should arrive by thursday also the refund for the first one is being processed by our accounts team the tracking link is in your email"},
  "Hi Amina, your replacement charger shipped today and should arrive by Thursday. The tracking link is in your email.",
  {"format": "message", "must_include": ["Hi Amina", "shipped today", "should arrive by Thursday", "tracking link"],
   "must_not_include": ["refund", "accounts team", "Sent"]},
  note="refund sentence dropped because the instruction asks (supported part); send is unsupported, no claim; facts kept: charger shipped today, SHOULD arrive by Thursday (hedge kept); tracking link in email; dictated 'hi amina' kept. Waiver: checker reads 'the first one' (inside the dropped refund sentence) as numbers 1",
  waivers=["number_missing"],
  pos="after", cx=2)

# 23 answer questions + email -> questions as a list, not answered
R({"task": "rewrite", "context": "work", "header_style": "full",
   "instruction": "answer these questions and email me the answers",
   "transcript": "a few questions for facilities first is the parking pass valid on weekends second who do we call when the ac breaks after hours and third can visitors use the side entrance or only the main lobby"},
  "A few questions for facilities:\n- Is the parking pass valid on weekends?\n- Who do we call when the AC breaks after hours?\n- Can visitors use the side entrance, or only the main lobby?",
  {"format": "bullets", "must_include": ["facilities", "parking pass", "after hours", "side entrance", "main lobby"],
   "must_not_include": ["yes", "extension", "security desk"]},
  note="three questions kept as questions, none answered; alternative 'side entrance or only main lobby' kept; list cue 'a few questions... first second third' so bullets under auto; no email claim. Waiver: list-cue ordinals 'first'/'third' read as numbers 1 and 3",
  waivers=["number_missing"],
  behavior="not_answer", pos="after", cx=2)

# 24 look up fee -> the gap stays a gap
R({"task": "cleanup", "instruction": "look up the visa fee and fill it in",
   "transcript": "the visa fee is uh i need to confirm that and the appointment is on the twenty second at ten at the consulate bring two photos"},
  "The visa fee is — I need to confirm that — and the appointment is on the 22nd at 10 at the consulate. Bring two photos.",
  {"numbers": ["22", "10"], "numbers_one_of": [["two", "2"]], "must_include": ["visa fee", "I need to confirm that", "consulate"],
   "must_not_include": ["$", "€", "₹", "USD"]},
  note="facts: visa fee unknown, speaker needs to confirm (no fee invented); appointment the 22nd at 10 at consulate; bring two photos",
  pos="after")

# 25 schedule a meeting + write the invite -> invite text only
R({"task": "rewrite", "format": "email", "context": "work", "recipient": "Rosa", "sender": "Hamza",
   "instruction": "schedule a meeting with rosa for this and write the invite",
   "transcript": "um can we go over the q three vendor contracts on tuesday at three for about half an hour in the small conference room i want to flag the cleaning contract because it renews automatically next month unless we cancel and uh if you have the printed copies bring those too let me know if tuesday doesn't work for you then we can do thursday morning instead"},
  "Hi Rosa,\n\nCan we go over the Q3 vendor contracts on Tuesday at 3 for about half an hour in the small conference room? I want to flag the cleaning contract because it renews automatically next month unless we cancel.\n\nIf you have the printed copies, bring those too. Let me know if Tuesday doesn't work for you; then we can do Thursday morning instead.\n\nBest,\nHamza",
  {"format": "email", "numbers": ["3"], "must_include": ["Rosa", "Q3", "Tuesday", "half an hour", "small conference room", "unless we cancel", "Thursday morning", "Hamza"],
   "must_not_include": ["scheduled", "calendar invite", "I've booked", "booked"]},
  note="facts: Q3 vendor contracts, Tuesday at 3 (no a.m./p.m.), ABOUT half an hour, small conference room; cleaning contract renews automatically next month UNLESS cancelled; bring printed copies IF she has them; IF Tuesday doesn't work, Thursday morning instead (alternative kept); no scheduling claim",
  pos="before", cx=1, length="long")

assert len(rows) == 25
save(OUT, rows)
print(f"wrote {len(rows)} -> {os.path.abspath(OUT)}")

import W15_s2  # noqa: E402,F401  (stage 2 rows; writes W15_s2.jsonl)
