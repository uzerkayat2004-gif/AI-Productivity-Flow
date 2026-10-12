"""W09 stage 2: messages bucket (work/chat messages), 130 records, ids TC-W09-101..230.

Domains: SaaS customer support, retail store operations, game studio, newsroom (stage 1)
plus fintech ops, hotel front desk, e-sports team, university lab chat (stage 2).
Names: Abhishek, Swati, Jake, Lena, Musa, Chen, Ritu, Pablo, Neeraj, Sigrid, Kemal, Annika.
Stage-1 file W09_s1.jsonl is produced by W09.py and is left untouched.
Re-run to reproduce research/vf_phase2b/data/batches/W09_s2.jsonl exactly.

Stage-1 review fixes applied: hedges that describe a fact ("kind of", "about", "probably")
and fact words ("again", "still", "third time") survive "more direct / no softening"
instructions; only request-softeners go. Vocative openers only when the speaker said
the name. Style instructions visibly change the text.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W09"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl")
rows = []
START = 101


def R(slice_, request, target, assertions, note=None, pos="structured", cx=0, length="medium", waivers=None):
    n = START + len(rows)
    req = {"task": "rewrite"}
    req.update(request)
    nw = len(req.get("transcript", "").split())
    length = "short" if nw < 20 else ("medium" if nw <= 60 else "long")  # by transcript words, as the brief defines
    a = dict(assertions)
    a.setdefault("format", "message")
    if a["format"] is None:
        del a["format"]
    rows.append(rec(f"TC-{WID}-{n:03d}", "messages", slice_, req, target, a, f"w09-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


MSG_W = {"format": "message", "context": "work"}
MSG_C = {"format": "message", "context": "chat"}
FULL = {"header_style": "full"}
IN = {"locale": "en-in"}

# ---------------------------------------------------------------- chunk 1 (101-143)
# 101 fintech incident update
R("messages", {**MSG_W, **FULL,
               "transcript": "um incident update the payouts api has been returning five hundred errors since two fifteen p m it's tracked under inc dash three zero four one uh about twelve percent of payout requests are failing we've paged the on call and the next update is at three"},
  "Incident update: the payouts API has been returning 500 errors since 2:15 p.m. It's tracked under INC-3041. About 12% of payout requests are failing. We've paged the on-call, and the next update is at 3.",
  {"numbers": ["500", "2:15", "3041", "12", "3"], "must_include": ["INC-3041", "payouts API", "About 12%", "on-call", "next update"]},
  note="facts: payouts API 500 errors since 2:15 p.m.; INC-3041; about 12% failing (approximate kept); on-call paged; next update at 3")
# 102 hotel front desk
R("messages", {**MSG_C, "transcript": "room four twelve is asking for a late checkout till one can we do that"},
  "Room 412 is asking for a late checkout till 1. Can we do that?",
  {"numbers": ["412", "1"], "must_include": ["late checkout"], "ends_with_question": True},
  note="facts: room 412; late checkout till 1 (no a.m./p.m. spoken); question kept", length="short")
# 103 PR review request with branch
R("messages", {**MSG_W,
               "transcript": "hey sigrid could you review my pr when you get a chance it's on the branch feature slash controller dash remap um it changes the default bindings for the gamepad so uh please check the menu navigation still works"},
  "Hey Sigrid, could you review my PR when you get a chance? It's on the branch feature/controller-remap. It changes the default bindings for the gamepad, so please check the menu navigation still works.",
  {"must_include": ["Sigrid", "feature/controller-remap", "default bindings", "gamepad", "menu navigation"]},
  note="facts: branch feature/controller-remap verbatim; changes default gamepad bindings; check menu navigation; 'hey sigrid' dictated so greeting kept")
# 104 esports WhatsApp schedule change
R("nl_instruction", {**MSG_C, "instruction": "WhatsApp message to the team group, as short as possible",
                     "transcript": "okay guys so scrims tomorrow are moved from six to seven thirty because the other team asked uh same discord server and kemal you're starting on the second map instead of the first"},
  "Tomorrow's scrims moved from 6 to 7:30 (the other team asked). Same Discord server. Kemal, you start on the second map, not the first.",
  {"numbers": ["6", "7:30"], "must_include": ["scrims", "Discord", "Kemal", "second map"], "must_not_include": ["Hi", "Hey"]},
  note="facts: scrims tomorrow 6 -> 7:30, other team asked; same Discord server; Kemal starts on second map instead of first",
  pos="before", cx=2)
# 105 university lab
R("messages", {**MSG_W, **FULL,
               "transcript": "the centrifuge in room b two is booked till four thirty so please don't start your run before then"},
  "The centrifuge in room B2 is booked till 4:30, so please don't start your run before then.",
  {"numbers": ["4:30"], "must_include": ["centrifuge", "B2"], "min_negations": 1},
  note="facts: centrifuge in room B2 booked till 4:30; don't start run before then", length="short")
# 106 saying no (retail)
R("messages", {**MSG_W,
               "transcript": "hi abhishek um no i can't approve the extra discount on the display tv we're already at the floor price uh the most i can do is throw in the wall mount at cost"},
  "Hi Abhishek, no, I can't approve the extra discount on the display TV. We're already at the floor price. The most I can do is throw in the wall mount at cost.",
  {"must_include": ["Abhishek", "no", "can't approve", "floor price", "wall mount at cost"], "min_negations": 2},
  note="facts: refusal kept ('no, I can't approve'); already at floor price; most offered = wall mount at cost; greeting dictated")
# 107 polite pushback, keep the no
R("multi_constraint", {**MSG_W, "instruction": "make it polite but firm, keep the no, and don't add any alternative dates",
                       "transcript": "jake i know sales wants the custom sso setup done for the trial account by friday but we can't do that the trial plan doesn't include sso and if we set it up we'd have to do it for every trial so um the answer is no unless they upgrade to the business plan"},
  "Jake, I understand sales wants the custom SSO setup done for the trial account by Friday, but we can't do that. The trial plan doesn't include SSO, and if we set it up, we'd have to do it for every trial. So the answer is no, unless they upgrade to the business plan.",
  {"must_include": ["Jake", "Friday", "can't do that", "doesn't include SSO", "every trial", "the answer is no", "unless they upgrade"], "min_negations": 3},
  note="facts: sales wants SSO for trial by Friday; can't; trial plan has no SSO; would have to do it for every trial; answer is no unless they upgrade to business plan (condition kept); no new dates",
  pos="after", cx=3)
# 108 newsroom self-correction
R("messages", {**MSG_C, "transcript": "musa the headline should say eleven injured sorry fourteen injured the police updated it"},
  "Musa, the headline should say 14 injured. The police updated it.",
  {"numbers": ["14"], "must_include": ["Musa", "headline", "police updated"], "must_not_include": ["11", "eleven"]},
  note="facts: self-correction 11 -> 14 applied; police updated the figure", length="short")
# 109 fintech approval with conditions
R("nl_instruction", {**MSG_W, **IN, "instruction": "ask for approval, keep all the conditions exactly",
                     "transcript": "neeraj can you approve the refund of eighty four thousand rupees for the merchant account m dash two two nine one um only if risk has cleared the chargeback and the merchant signs the settlement form otherwise we hold it"},
  "Neeraj, can you approve the ₹84,000 refund for merchant account M-2291? This is only if risk has cleared the chargeback and the merchant signs the settlement form. Otherwise, we hold it.",
  {"numbers": ["84,000", "2291"], "must_include": ["Neeraj", "M-2291", "only if risk has cleared the chargeback", "settlement form", "Otherwise, we hold it"]},
  note="facts: ₹84,000 refund for M-2291; approve only if risk cleared chargeback AND merchant signs settlement form; otherwise hold",
  pos="before", cx=2)
# 110 hotel handover, several owners
R("messages", {**MSG_W, **FULL,
               "transcript": "okay handover for the night shift um room three oh eight is still waiting on the extra pillows housekeeping said ten minutes that was half an hour ago so kemal can you chase them uh the tour group from the airport lands at eleven forty and annika has the key cards ready in the drawer under the printer don't give out the pool wristbands to them the pool is closed for the night and uh the guest in five fifteen paid in cash so the folio needs to be printed tonight lena's handling that"},
  "Handover for the night shift. Room 308 is still waiting on the extra pillows. Housekeeping said 10 minutes, but that was half an hour ago, so Kemal, can you chase them? The tour group from the airport lands at 11:40, and Annika has the key cards ready in the drawer under the printer. Don't give out the pool wristbands to them; the pool is closed for the night. The guest in 515 paid in cash, so the folio needs to be printed tonight. Lena's handling that.",
  {"numbers": ["308", "10", "11:40", "515"], "must_include": ["Kemal", "Annika", "Lena", "still waiting", "half an hour ago", "key cards", "pool wristbands", "folio"], "min_negations": 1},
  waivers=["number_missing", "number_invented"],
  note="facts: room 308 still waiting on pillows, housekeeping said 10 min half an hour ago, Kemal to chase; tour group lands 11:40, Annika has key cards in drawer under printer; no pool wristbands for them, pool closed; 515 paid cash, folio printed tonight, Lena handling; WAIVER: checker reads 'three oh eight' as 3/0/8 and flags 308 as invented",
  length="long")
# 111 game studio
R("messages", {**MSG_C, "register": "casual", "transcript": "pushing the hotfix to steam in five minutes nobody merge anything"},
  "Pushing the hotfix to Steam in 5 minutes. Nobody merge anything.",
  {"numbers": ["5"], "must_include": ["hotfix", "Steam", "Nobody merge anything"]},
  note="facts: hotfix to Steam in 5 minutes; nobody merge (prohibition kept)", length="short")
# 112 newsroom: no softening, keep fact hedge
R("multi_constraint", {**MSG_W, "instruction": "under 50 words, keep my terminology, no softening",
                       "transcript": "um so i was just wondering if maybe we could get the copy desk to look at the lede on the flood piece before it goes up because the second graf repeats the same quote as the lede and the nut graf is kind of buried down at the bottom"},
  "Can the copy desk look at the lede on the flood piece before it goes up? The second graf repeats the same quote as the lede, and the nut graf is kind of buried at the bottom.",
  {"must_include": ["copy desk", "lede", "flood piece", "second graf", "nut graf", "kind of buried"], "max_words": 50},
  note="facts: copy desk to check lede before it goes up; second graf repeats lede quote; nut graf 'kind of' buried (fact hedge kept; only request-softener 'just wondering if maybe' removed); newsroom terms lede/graf/nut graf kept",
  pos="after", cx=3)
# 113 lab
R("messages", {**MSG_W, **FULL,
               "transcript": "chen the reagent order went in this morning but the antibodies are backordered till the twentieth so the western blots will have to wait probably until the week after"},
  "Chen, the reagent order went in this morning, but the antibodies are backordered till the 20th, so the western blots will have to wait, probably until the week after.",
  {"numbers": ["20"], "must_include": ["Chen", "this morning", "backordered", "western blots", "probably until the week after"]},
  note="facts: order in this morning; antibodies backordered till the 20th; blots wait, 'probably' until week after (hedge kept)")
# 114 esports
R("messages", {**MSG_C, "transcript": "annika we need the jersey sizes by thursday or they won't print in time for the qualifier"},
  "Annika, we need the jersey sizes by Thursday or they won't print in time for the qualifier.",
  {"must_include": ["Annika", "jersey sizes", "Thursday", "qualifier"], "min_negations": 1},
  note="facts: jersey sizes by Thursday, otherwise won't print in time for qualifier", length="short")
# 115 customer-facing support reply
R("nl_instruction", {**MSG_C, "instruction": "turn this into a reply to the customer, friendly, no promises about timing",
                     "transcript": "um thanks for flagging this the duplicate invoice is a known bug on our side uh our engineers are working on it you weren't charged twice only the email was sent twice so you don't need to do anything"},
  "Thanks so much for flagging this. The duplicate invoice is a known bug on our side, and our engineers are working on it. You weren't charged twice; only the email was sent twice, so you don't need to do anything.",
  {"must_include": ["known bug", "engineers are working on it", "weren't charged twice", "don't need to do anything"], "must_not_include": ["hours", "days", "soon", "by tomorrow"], "min_negations": 1},
  note="facts: duplicate invoice is a known bug; engineers working on it; not charged twice, only email sent twice; no action needed; no timeline or promise added",
  pos="after", cx=2)
# 116 en-in retail office chat
R("messages", {**MSG_W, **IN,
               "transcript": "ritu ma'am the stock audit for the andheri branch is done uh shortfall is around eleven thousand rupees mostly in the cosmetics section i've mailed you the sheet please check and revert"},
  "Ritu ma'am, the stock audit for the Andheri branch is done. The shortfall is around ₹11,000, mostly in the cosmetics section. I've mailed you the sheet, please check and revert.",
  {"numbers": ["11,000"], "must_include": ["Ritu ma'am", "Andheri", "around ₹11,000", "cosmetics", "revert"]},
  note="facts: Andheri stock audit done; shortfall around ₹11,000 (approximate), mostly cosmetics; sheet mailed; en-in 'revert' kept")
# 117 bullet the three blockers
R("multi_constraint", {"format": "auto", "context": "work", "instruction": "Slack message, bullet the three blockers, keep the ticket ID",
                       "transcript": "so for the demo build we're blocked on three things the first one is the shader compile crash on older gpus that's g s dash four zero two uh second the localization strings for german haven't come back from the vendor and third we still don't have the final logo from marketing so the splash screen is a placeholder"},
  "We're blocked on three things for the demo build:\n- The shader compile crash on older GPUs (GS-402)\n- The German localization strings haven't come back from the vendor\n- We still don't have the final logo from marketing, so the splash screen is a placeholder",
  {"numbers": ["402"], "must_include": ["three things", "demo build", "GS-402", "German localization", "final logo", "placeholder"], "min_negations": 2, "format": "bullets"},
  waivers=["number_missing", "number_invented"],
  note="facts: 3 blockers: shader compile crash older GPUs GS-402; German strings not back from vendor; no final logo from marketing so splash is placeholder; bullets allowed because instructed; WAIVER: checker reads 'four zero two' digit by digit and 'first one'/'second' as numbers; GS-402 is the spoken ID",
  pos="before", cx=3)
# 118 fintech short
R("messages", {**MSG_W, **FULL, "transcript": "the settlement file for hdfc didn't arrive at six so recon is on hold"},
  "The settlement file for HDFC didn't arrive at 6, so recon is on hold.",
  {"numbers": ["6"], "must_include": ["HDFC", "settlement file", "recon is on hold"], "min_negations": 1},
  note="facts: HDFC settlement file didn't arrive at 6; recon on hold", length="short")
# 119 hotel guest message
R("messages", {**MSG_C,
               "transcript": "hi mr kowalski your airport pickup is confirmed for tomorrow at seven fifteen a m the driver will wait at the lobby entrance uh please call the front desk if your flight changes"},
  "Hi Mr. Kowalski, your airport pickup is confirmed for tomorrow at 7:15 a.m. The driver will wait at the lobby entrance. Please call the front desk if your flight changes.",
  {"numbers": ["7:15"], "must_include": ["Mr. Kowalski", "airport pickup", "tomorrow", "lobby entrance", "if your flight changes"]},
  note="facts: pickup confirmed tomorrow 7:15 a.m.; driver waits at lobby entrance; call front desk if flight changes; greeting dictated")
# 120 newsroom schedule changes old/new
R("messages", {**MSG_W, **FULL,
               "transcript": "quick change to tomorrow's schedule um the morning news meeting moves from nine thirty to nine because the editor has a board call at ten uh the afternoon budget meeting stays at three and the photo desk meeting is cancelled this week pablo will just send the picks over email"},
  "Quick change to tomorrow's schedule: the morning news meeting moves from 9:30 to 9 because the editor has a board call at 10. The afternoon budget meeting stays at 3, and the photo desk meeting is cancelled this week. Pablo will just send the picks over email.",
  {"numbers": ["9:30", "9", "10", "3"], "must_include": ["tomorrow", "morning news meeting", "board call", "stays at 3", "cancelled this week", "Pablo"]},
  note="facts: tomorrow: news meeting 9:30 -> 9 (editor board call at 10); budget meeting stays 3; photo desk meeting cancelled this week; Pablo sends picks by email")
# 121 long ramble -> concise
R("nl_instruction", {**MSG_W, "instruction": "make it concise, two sentences max",
                     "transcript": "so um yeah so basically what i wanted to say is that the uh the export feature the one in the reports tab the csv export it's working again it was broken since like yesterday afternoon because of the uh the timezone change but the fix went out about an hour ago and i tested it a couple times and it works so yeah it's working again"},
  "The CSV export in the Reports tab is working again; it had been broken since about yesterday afternoon because of the timezone change. The fix went out about an hour ago, and I've tested it a couple of times.",
  {"must_include": ["CSV export", "Reports tab", "working again", "about yesterday afternoon", "timezone change", "about an hour ago", "couple of times"]},
  note="facts: CSV export (Reports tab) working again; broken since about ('like') yesterday afternoon due to timezone change; fix out about an hour ago; speaker tested a couple of times; repetition dropped",
  pos="after", cx=2, length="long")
# 122 esports self-correction
R("messages", {**MSG_C, "register": "casual", "transcript": "kemal no wait musa is subbing in for game three"},
  "Musa is subbing in for game 3.",
  {"numbers": ["3"], "must_include": ["Musa", "game 3"], "must_not_include": ["Kemal"]},
  note="facts: self-correction Kemal -> Musa applied; game 3", length="short")
# 123 lab booking
R("messages", {**MSG_C,
               "transcript": "hey lena are you still using the confocal friday afternoon if not i'd like to book it from one to five for the imaging run"},
  "Hey Lena, are you still using the confocal Friday afternoon? If not, I'd like to book it from 1 to 5 for the imaging run.",
  {"numbers": ["1", "5"], "must_include": ["Lena", "confocal", "Friday afternoon", "If not", "imaging run"]},
  note="facts: asks if Lena still using confocal Friday afternoon; conditional booking 1 to 5 if not; greeting dictated")
# 124 fintech polite pushback with cap
R("multi_constraint", {**MSG_W, "instruction": "polite pushback, under 45 words, keep the deadline and the numbers exactly",
                       "transcript": "swati we can't close the q three reconciliation by wednesday there are still three hundred and twelve unmatched transactions and the bank statement for september only came in this morning we need until friday end of day"},
  "Swati, I'm afraid we can't close the Q3 reconciliation by Wednesday. There are still 312 unmatched transactions, and the September bank statement only came in this morning. We need until Friday end of day.",
  {"numbers": ["312"], "must_include": ["Swati", "Q3", "Wednesday", "still 312", "September", "this morning", "Friday end of day"], "min_negations": 1, "max_words": 45},
  note="facts: can't close Q3 recon by Wednesday; still 312 unmatched; September statement only this morning; need until Friday EOD",
  pos="after", cx=3)
# 125 retail short
R("messages", {**MSG_C, "transcript": "the queue at billing is long open counter four"},
  "The queue at billing is long. Open counter 4.",
  {"numbers": ["4"], "must_include": ["billing", "counter 4"]}, note="facts: open counter 4", length="short")
# 126 SaaS incident resolved
R("messages", {**MSG_W, **FULL,
               "transcript": "update on inc dash eight eight two the dashboard latency is back to normal as of four ten p m root cause was a bad cache config we rolled it back we'll post the full write up tomorrow"},
  "Update on INC-882: dashboard latency is back to normal as of 4:10 p.m. The root cause was a bad cache config, and we rolled it back. We'll post the full write-up tomorrow.",
  {"numbers": ["882", "4:10"], "must_include": ["INC-882", "back to normal", "cache config", "rolled it back", "write-up tomorrow"]},
  note="facts: INC-882 latency normal as of 4:10 p.m.; root cause bad cache config, rolled back; dictated commitment: full write-up tomorrow")
# 127 PR review request for channel
R("nl_instruction", {**MSG_W, "instruction": "make it a short PR review request for the team channel, keep the branch name exactly",
                     "transcript": "um can someone look at my changes for the save file migration the branch is fix slash save dash v two dash migration i need two approvals before thursday's cert build and uh the tests pass locally but i haven't run them on the ps five kit yet"},
  "Can someone review my changes for the save file migration? Branch: fix/save-v2-migration. I need two approvals before Thursday's cert build. Tests pass locally, but I haven't run them on the PS5 kit yet.",
  {"must_include": ["fix/save-v2-migration", "two approvals", "Thursday's cert build", "pass locally", "PS5"], "min_negations": 1},
  note="facts: branch fix/save-v2-migration verbatim; two approvals needed before Thursday's cert build; tests pass locally, not yet run on PS5 kit",
  pos="before", cx=2)
# 128 hotel notice
R("messages", {**MSG_W, **FULL,
               "transcript": "the elevator on the east side is out of service until tomorrow noon please direct guests to the west lifts"},
  "The elevator on the east side is out of service until tomorrow noon. Please direct guests to the west lifts.",
  {"must_include": ["east side", "out of service", "tomorrow noon", "west lifts"]},
  note="facts: east elevator out of service until tomorrow noon; guests to west lifts", length="short")
# 129 newsroom shift swap
R("messages", {**MSG_C, "register": "casual",
               "transcript": "swati can you swap your sunday shift with jake's monday he's got a family thing"},
  "Swati, can you swap your Sunday shift with Jake's Monday? He's got a family thing.",
  {"must_include": ["Swati", "Sunday shift", "Jake's Monday", "family thing"]},
  note="facts: Swati's Sunday for Jake's Monday; Jake has a family thing", length="short")
# 130 esports WhatsApp group, drop repetition
R("multi_constraint", {**MSG_C, "register": "casual", "instruction": "WhatsApp group message, keep it casual, drop the repetition, keep every time",
                       "transcript": "hey team so bootcamp details um we meet at the gaming house saturday at ten a m bring your own peripherals bring your own peripherals mouse keyboard headset all of it uh lunch is covered by the org dinner isn't and we're scrimming from two to six then vod review from seven to nine and uh pablo if your visa appointment clashes just tell me and we'll figure it out"},
  "Hey team, bootcamp details: we meet at the gaming house Saturday at 10 a.m. Bring your own peripherals, mouse, keyboard, headset, all of it. Lunch is covered by the org, dinner isn't. We're scrimming from 2 to 6, then VOD review from 7 to 9. Pablo, if your visa appointment clashes, just tell me and we'll figure it out.",
  {"numbers": ["10", "2", "6", "7", "9"], "must_include": ["Hey team", "gaming house", "Saturday", "peripherals", "dinner isn't", "VOD review", "Pablo", "visa appointment"], "min_negations": 1},
  note="facts: Saturday 10 a.m. at gaming house; bring own peripherals (said twice, once kept); lunch covered by org, dinner not; scrims 2-6, VOD review 7-9; Pablo: if visa appointment clashes tell speaker; 'hey team' dictated",
  pos="after", cx=3, length="long")
# 131 lab handover, several owners
R("messages", {**MSG_W, **FULL,
               "transcript": "hi all i'm away at the conference from the fourteenth to the eighteenth um neeraj is in charge of the cell cultures while i'm gone they need feeding every forty eight hours the media is in the second fridge top shelf uh annika is covering the freezer alarm rota and if the minus eighty alarm goes off call facilities first then her and please nobody touch the samples in box seven those are for the grant renewal"},
  "Hi all, I'm away at the conference from the 14th to the 18th. Neeraj is in charge of the cell cultures while I'm gone. They need feeding every 48 hours, and the media is in the second fridge, top shelf. Annika is covering the freezer alarm rota. If the minus 80 alarm goes off, call facilities first, then her. Please, nobody touch the samples in box 7; those are for the grant renewal.",
  {"numbers": ["14", "18", "48", "80", "7"], "must_include": ["Hi all", "conference", "Neeraj", "cell cultures", "second fridge", "Annika", "facilities first", "box 7", "grant renewal"]},
  note="facts: away at conference 14th-18th; Neeraj cell cultures, feed every 48 h, media second fridge top shelf; Annika freezer alarm rota; minus 80 alarm -> facilities first then Annika; nobody touch box 7 (grant renewal); 'hi all' dictated",
  length="long")
# 132 support short
R("messages", {**MSG_W,
               "transcript": "customer from orbit labs says the reset password email never arrives and they already checked spam"},
  "The customer from Orbit Labs says the reset password email never arrives, and they've already checked spam.",
  {"must_include": ["Orbit Labs", "reset password email", "never arrives", "checked spam"], "min_negations": 1},
  note="facts: Orbit Labs reset email never arrives; customer already checked spam", length="short")
# 133 saying no, friendlier
R("nl_instruction", {**MSG_C, "instruction": "keep the no clear but make it friendlier",
                     "transcript": "no we're not doing price matching with online stores it's company policy sorry the best i can offer is the loyalty points"},
  "Sorry, but no, we don't price match with online stores; it's company policy. The best I can offer is the loyalty points.",
  {"must_include": ["no", "online stores", "company policy", "loyalty points"], "min_negations": 2},
  note="facts: refusal kept (no price matching with online stores, company policy); best offer = loyalty points; 'sorry' was dictated",
  pos="after", cx=2, length="short")
# 134 en-in fintech office chat
R("messages", {**MSG_W, **IN, **FULL,
               "transcript": "abhishek sir the upi collection failures spiked to around four percent between one and one thirty the npci side had an issue it's normal now i'll send the rca by tomorrow"},
  "Abhishek sir, UPI collection failures spiked to around 4% between 1 and 1:30. The NPCI side had an issue. It's normal now, and I'll send the RCA by tomorrow.",
  {"numbers": ["4", "1", "1:30"], "must_include": ["Abhishek sir", "UPI", "around 4%", "NPCI", "normal now", "RCA by tomorrow"]},
  waivers=["number_missing"],
  note="facts: UPI collection failures around 4% between 1 and 1:30; NPCI-side issue; normal now; dictated commitment RCA by tomorrow; WAIVER: checker splits 'one thirty' into 1 and 30; written 1:30")
# 135 approval with conditions, formal, cap
R("multi_constraint", {**MSG_W, "instruction": "make it more formal for the managing editor, keep both conditions, and keep it under 60 words",
                       "transcript": "lena i need your ok to run the leaked memo story tonight legal has seen it and they're fine as long as we don't name the junior staffer and we get a second source to confirm the dates if we can't get the second source by nine we hold it till tomorrow"},
  "Lena, I need your approval to run the leaked memo story tonight. Legal has reviewed it and is comfortable, provided we do not name the junior staffer and we obtain a second source to confirm the dates. If we cannot get the second source by 9, we hold it until tomorrow.",
  {"numbers": ["9"], "must_include": ["Lena", "approval", "leaked memo", "tonight", "junior staffer", "second source", "until tomorrow"], "min_negations": 2, "max_words": 60},
  note="facts: needs Lena's approval to run tonight; legal fine on two conditions: don't name junior staffer AND second source confirms dates; if no second source by 9, hold until tomorrow",
  pos="after", cx=3)
# 136 game studio short
R("messages", {**MSG_W, **FULL, "transcript": "art lock is friday at six after that only bug fixes"},
  "Art lock is Friday at 6. After that, only bug fixes.",
  {"numbers": ["6"], "must_include": ["Art lock", "Friday", "only bug fixes"]},
  note="facts: art lock Friday 6; only bug fixes after", length="short")
# 137 hotel, self-correction
R("messages", {**MSG_W,
               "transcript": "annika the conference room for the pharma group is booked for wednesday no thursday from nine to five they want water and notepads on every table"},
  "Annika, the conference room for the pharma group is booked for Thursday from 9 to 5. They want water and notepads on every table.",
  {"numbers": ["9", "5"], "must_include": ["Annika", "pharma group", "Thursday", "water and notepads"], "must_not_include": ["Wednesday"]},
  note="facts: self-correction Wednesday -> Thursday applied; 9 to 5; water and notepads on every table")
# 138 lab, shorter keep condition
R("nl_instruction", {**MSG_W, "instruction": "shorter, keep the condition exactly as I said it",
                     "transcript": "so um the paper draft is with the professor now and she said she'll give feedback by monday uh if she asks for the extra experiment we're probably looking at another two weeks before submission otherwise we submit next friday"},
  "The paper draft is with the professor; she said feedback by Monday. If she asks for the extra experiment, we're probably looking at another two weeks before submission. Otherwise we submit next Friday.",
  {"must_include": ["paper draft", "professor", "Monday", "If she asks for the extra experiment", "probably", "two weeks", "next Friday"]},
  note="facts: draft with professor, feedback by Monday (her word); if extra experiment requested, probably two more weeks; otherwise submit next Friday",
  pos="after", cx=2)
# 139 esports stream time
R("messages", {**MSG_C, "transcript": "stream starts at eight tonight not seven thirty"},
  "Stream starts at 8 tonight, not 7:30.",
  {"numbers": ["8", "7:30"], "must_include": ["tonight"], "min_negations": 1},
  note="facts: stream 8 tonight, not 7:30 (contrast kept)", length="short")
# 140 SaaS polite pushback
R("messages", {**MSG_W, **FULL,
               "transcript": "chen i'd rather not push the pricing page change today it's friday afternoon and if something breaks nobody's around to fix it can we ship it monday morning instead"},
  "Chen, I'd rather not push the pricing page change today. It's Friday afternoon, and if something breaks, nobody's around to fix it. Can we ship it Monday morning instead?",
  {"must_include": ["Chen", "rather not", "pricing page", "Friday afternoon", "Monday morning"], "min_negations": 1, "ends_with_question": True},
  note="facts: rather not push pricing change today (Friday afternoon); if it breaks nobody around; proposes Monday morning (speaker's own alternative)")
# 141 retail festive sale, en-in, terminology + repetition
R("multi_constraint", {**MSG_W, **IN, "instruction": "make it a clear message for the store group, keep my terminology, and drop the repetition",
                       "transcript": "okay so for the festive sale starting saturday um the doors open at nine not ten so everyone needs to be in by eight fifteen eight fifteen latest uh the sale tags go only on the red rack items not the new arrivals the new arrivals stay full price and musa and ritu are on the fitting rooms swati's on the cash desk and if the card machine acts up use the backup one in the manager's cabin don't send customers away"},
  "For the festive sale starting Saturday, the doors open at 9, not 10, so everyone needs to be in by 8:15 latest. The sale tags go only on the red rack items, not the new arrivals; the new arrivals stay full price. Musa and Ritu are on the fitting rooms, and Swati's on the cash desk. If the card machine acts up, use the backup one in the manager's cabin. Don't send customers away.",
  {"numbers": ["9", "10", "8:15"], "must_include": ["festive sale", "Saturday", "red rack", "new arrivals", "full price", "Musa", "Ritu", "Swati", "manager's cabin", "Don't send customers away"], "min_negations": 3},
  waivers=["number_missing"],
  note="facts: festive sale from Saturday; doors 9 not 10; in by 8:15 latest (repeated once); tags only on red rack, not new arrivals (full price); Musa+Ritu fitting rooms, Swati cash desk; card machine issue -> backup in manager's cabin (conditional); standing rule don't send customers away kept separate; WAIVER: repeated 'eight fifteen eight fifteen' read as separate 8/15 literals; written 8:15 once",
  pos="after", cx=3, length="long")
# 142 fintech KYC
R("messages", {**MSG_W,
               "transcript": "sigrid the kyc queue is at two hundred and forty pending can you add one more reviewer for the afternoon"},
  "Sigrid, the KYC queue is at 240 pending. Can you add one more reviewer for the afternoon?",
  {"numbers": ["240"], "must_include": ["Sigrid", "KYC queue", "one more reviewer", "afternoon"], "ends_with_question": True},
  note="facts: KYC queue 240 pending; ask for one more reviewer for the afternoon", length="short")
# 143 newsroom live blog
R("messages", {**MSG_W, **FULL,
               "transcript": "heads up the live blog for the budget speech goes up at ten forty five chen and neeraj are writing it and i'll be editing please send any quotes straight to the shared doc not to my dms"},
  "Heads up: the live blog for the budget speech goes up at 10:45. Chen and Neeraj are writing it, and I'll be editing. Please send any quotes straight to the shared doc, not to my DMs.",
  {"numbers": ["10:45"], "must_include": ["live blog", "budget speech", "Chen", "Neeraj", "shared doc", "not to my DMs"], "min_negations": 1},
  note="facts: live blog goes up 10:45; Chen and Neeraj writing, speaker editing; quotes to shared doc, not DMs")

# ---------------------------------------------------------------- chunk 2 (144-186)
# 144 SaaS incident start
R("messages", {**MSG_W, **FULL,
               "transcript": "heads up we're seeing elevated login errors in the eu region started around nine fifty a m ticket sup dash nine one two zero is the master ticket please link any customer reports to it and don't promise customers an eta"},
  "Heads up: we're seeing elevated login errors in the EU region, starting around 9:50 a.m. SUP-9120 is the master ticket. Please link any customer reports to it, and don't promise customers an ETA.",
  {"numbers": ["9:50", "9120"], "must_include": ["EU region", "around 9:50", "SUP-9120", "master ticket", "don't promise customers an ETA"], "min_negations": 1},
  note="facts: elevated EU login errors since around 9:50 a.m.; SUP-9120 master ticket; link customer reports; don't promise an ETA")
# 145 hotel key card
R("messages", {**MSG_C, "transcript": "kemal the guest in room two fourteen lost her key card again second time today"},
  "Kemal, the guest in room 214 lost her key card again, second time today.",
  {"numbers": ["214"], "must_include": ["Kemal", "room 214", "again", "second time today"]},
  note="facts: room 214 guest lost key card again; second time today ('again' is a fact)", length="short")
# 146 game studio: firmer no
R("nl_instruction", {**MSG_W, "instruction": "make it shorter and a bit firmer, keep the no",
                     "transcript": "pablo thanks for asking but we can't add the photo mode to this patch it's locked uh it could go in the next content update but that's not my call that's lena's"},
  "Pablo, thanks for asking, but photo mode can't go into this patch. It's locked. It could go in the next content update, but that's Lena's call, not mine.",
  {"must_include": ["Pablo", "photo mode", "can't", "locked", "next content update", "Lena's call"], "min_negations": 2},
  note="facts: refusal kept: photo mode can't go in this patch (locked); 'could' go in next content update (hedge); decision is Lena's, not speaker's",
  pos="after", cx=2)
# 147 lab group
R("messages", {**MSG_C, "transcript": "lab meeting tomorrow is cancelled prof is sick journal club still on at three in the seminar room"},
  "Lab meeting tomorrow is cancelled, the prof is sick. Journal club is still on at 3 in the seminar room.",
  {"numbers": ["3"], "must_include": ["Lab meeting tomorrow is cancelled", "Journal club", "still on", "seminar room"]},
  note="facts: lab meeting tomorrow cancelled (prof sick); journal club still on at 3, seminar room", length="short")
# 148 fintech incident update, cap
R("multi_constraint", {**MSG_W, "instruction": "status update for the ops channel, under 70 words, keep every ID and time",
                       "transcript": "okay so update on the card authorization issue um it started at eleven oh five when the processor pushed a config change we raised it with them as case c s eight four four one seven uh declines went up to around nine percent at peak and they rolled back at eleven forty two since then approval rates are normal we're still watching it and i'll post the next update at one"},
  "Update on the card authorization issue: it started at 11:05 when the processor pushed a config change. We raised it with them as case CS-84417. Declines went up to around 9% at peak. They rolled back at 11:42, and approval rates have been normal since. We're still watching it, and I'll post the next update at 1.",
  {"numbers": ["11:05", "84417", "9", "11:42", "1"], "must_include": ["card authorization", "config change", "CS-84417", "around 9%", "rolled back", "still watching", "next update at 1"], "max_words": 70},
  waivers=["number_missing"],
  note="facts: started 11:05 after processor config change; case CS-84417; declines around 9% at peak; rollback 11:42, approvals normal since; still watching; next update at 1; WAIVER: checker reads 'eleven oh five' as 11/0/5; written 11:05",
  pos="after", cx=3, length="long")
# 149 retail price gun
R("messages", {**MSG_C, "register": "casual", "transcript": "who took the price gun from the stockroom bring it back please"},
  "Who took the price gun from the stockroom? Bring it back, please.",
  {"must_include": ["price gun", "stockroom", "Bring it back"]}, length="short")
# 150 esports travel
R("messages", {**MSG_C,
               "transcript": "musa your flight to berlin is on the ninth not the tenth i double checked the booking so please update your visa form"},
  "Musa, your flight to Berlin is on the 9th, not the 10th. I double-checked the booking, so please update your visa form.",
  {"numbers": ["9", "10"], "must_include": ["Musa", "Berlin", "9th", "not the 10th", "visa form"], "min_negations": 1},
  note="facts: flight on the 9th, not the 10th (contrast kept); booking double-checked; update visa form")
# 151 customer-facing support reply
R("nl_instruction", {**MSG_C, "instruction": "make this a customer-facing reply, professional, don't add any timeline or compensation",
                     "transcript": "so the outage yesterday affected scheduled reports between two and four p m uh your reports from that window didn't send we've re run them and they should be in your inbox now if any are missing reply here with the report name"},
  "Yesterday's outage affected scheduled reports between 2 and 4 p.m., so your reports from that window didn't send. We've re-run them, and they should be in your inbox now. If any are missing, please reply here with the report name.",
  {"numbers": ["2", "4"], "must_include": ["Yesterday", "scheduled reports", "re-run", "should be in your inbox", "If any are missing"], "must_not_include": ["credit", "refund", "discount"], "min_negations": 1},
  note="facts: outage yesterday hit scheduled reports 2-4 p.m.; those didn't send; re-run, 'should be' in inbox (hedge kept); if missing reply with report name; no timeline/compensation added",
  pos="before", cx=3)
# 152 newsroom weekend handover
R("messages", {**MSG_W, **FULL,
               "transcript": "um handover for the weekend desk so the court verdict is expected saturday morning abhishek has the pre written versions both guilty and not guilty in the drafts folder do not publish either until the verdict is read out uh swati is handling social and ritu's on the homepage the sports results come in from the wire around ten pm and just slot them in without editing the scores and if anything big breaks call neeraj he's on call this weekend not me"},
  "Handover for the weekend desk. The court verdict is expected Saturday morning. Abhishek has the pre-written versions, both guilty and not guilty, in the drafts folder. Do not publish either until the verdict is read out. Swati is handling social, and Ritu's on the homepage. The sports results come in from the wire around 10 p.m.; just slot them in without editing the scores. If anything big breaks, call Neeraj. He's on call this weekend, not me.",
  {"numbers": ["10"], "must_include": ["weekend desk", "Saturday morning", "Abhishek", "guilty and not guilty", "Do not publish", "Swati", "Ritu", "around 10 p.m.", "without editing the scores", "Neeraj"], "min_negations": 4},
  note="facts: verdict expected Saturday morning; Abhishek has both pre-written versions in drafts; do not publish until verdict read; Swati social, Ritu homepage; wire sports results around 10 p.m., slot in without editing scores; big news -> call Neeraj (on call), not speaker",
  length="long")
# 153 hotel breakfast
R("messages", {**MSG_W, "transcript": "breakfast is extended till eleven today because of the marathon"},
  "Breakfast is extended till 11 today because of the marathon.",
  {"numbers": ["11"], "must_include": ["Breakfast", "today", "marathon"]},
  note="facts: breakfast till 11 today; reason marathon", length="short")
# 154 two PRs with branches
R("multi_constraint", {**MSG_W, "instruction": "tighten it up, keep the branch names and ticket number exactly, no extra asks",
                       "transcript": "so jake i've got two prs up um the first one is on perf slash texture dash streaming that's the big one it cuts load times on the open world map by about a third and the second is on fix slash ui dash scaling for the ultrawide bug g s dash five one eight uh the second one is tiny so maybe do that one first and for the big one please just check the memory numbers on the low end preset i didn't have time to test that"},
  "Jake, I've got two PRs up. The first, on perf/texture-streaming, is the big one: it cuts load times on the open world map by about a third. The second, on fix/ui-scaling, is for the ultrawide bug GS-518. It's tiny, so maybe do it first. For the big one, please check the memory numbers on the low-end preset; I didn't have time to test that.",
  {"numbers": ["518"], "must_include": ["Jake", "two PRs", "perf/texture-streaming", "about a third", "fix/ui-scaling", "GS-518", "maybe do it first", "low-end preset"], "min_negations": 1},
  note="facts: two PRs: perf/texture-streaming (big, cuts open-world load times by about a third) and fix/ui-scaling (ultrawide bug GS-518, tiny, 'maybe' review first); check memory numbers on low-end preset, speaker didn't test it; no added asks",
  pos="before", cx=3, length="long")
# 155 en-in lab
R("messages", {**MSG_W, **IN, "transcript": "neeraj bhai the gel imager is not working since morning i've raised a complaint with the vendor"},
  "Neeraj bhai, the gel imager has not been working since morning. I've raised a complaint with the vendor.",
  {"must_include": ["Neeraj bhai", "gel imager", "since morning", "complaint with the vendor"], "min_negations": 1},
  note="facts: gel imager not working since morning; complaint raised with vendor", length="short")
# 156 fintech conditional approval
R("messages", {**MSG_W, **IN, **FULL,
               "transcript": "annika i'm okay with raising the daily limit for that merchant to five lakh but only for thirty days and only if their chargeback rate stays under one percent"},
  "Annika, I'm okay with raising the daily limit for that merchant to 5 lakh, but only for 30 days and only if their chargeback rate stays under 1%.",
  {"numbers": ["30", "1"], "must_include": ["Annika", "daily limit", "5 lakh", "only for 30 days", "only if", "under 1%"]},
  waivers=["number_missing", "number_invented"],
  note="facts: approve daily limit 5 lakh (no currency spoken, none added) with two conditions: only 30 days AND only if chargeback rate under 1%; WAIVER: checker reads 'five lakh' as 5 x 100000 and mis-tokenises the percent; written '5 lakh' and '1%'")
# 157 short dictation -> message to Swati
R("nl_instruction", {**MSG_C, "instruction": "turn into a quick message to Swati",
                     "transcript": "the shipment of yoga mats came in thirty short"},
  "Swati, the shipment of yoga mats came in 30 short.",
  {"numbers": ["30"], "must_include": ["Swati", "yoga mats", "30 short"]},
  note="facts: yoga mat shipment 30 short; addressee Swati named in the instruction", pos="before", cx=1, length="short")
# 158 esports WhatsApp reminder
R("messages", {**MSG_C,
               "transcript": "reminder guys jersey photoshoot is on sunday at eleven at the studio in sector twenty nine wear black shoes and don't be late the photographer only has the slot till one"},
  "Reminder, guys: the jersey photoshoot is on Sunday at 11 at the studio in Sector 29. Wear black shoes and don't be late; the photographer only has the slot till 1.",
  {"numbers": ["11", "29", "1"], "must_include": ["jersey photoshoot", "Sunday", "Sector 29", "black shoes", "don't be late"], "min_negations": 1},
  note="facts: photoshoot Sunday 11, studio Sector 29; black shoes; don't be late; photographer slot till 1")
# 159 SaaS staging
R("messages", {**MSG_W,
               "transcript": "the stripe webhook secret got rotated so the staging payments are failing ping me before you redeploy"},
  "The Stripe webhook secret got rotated, so the staging payments are failing. Ping me before you redeploy.",
  {"must_include": ["Stripe webhook secret", "rotated", "staging payments", "Ping me before you redeploy"]}, length="short")
# 160 hotel pushback, cap
R("multi_constraint", {**MSG_W, "instruction": "polite but firm, keep it under 55 words, keep the time",
                       "transcript": "lena i can't do another double shift this week i've already done two and i'm on again at seven tomorrow morning can someone else cover tonight"},
  "Lena, I can't take on another double shift this week. I've already done two, and I'm back on at 7 tomorrow morning. Could someone else please cover tonight?",
  {"numbers": ["7"], "must_include": ["Lena", "can't", "double shift", "already done two", "7 tomorrow morning", "cover tonight"], "min_negations": 1, "max_words": 55},
  note="facts: refusal: can't do another double this week; already did two; on again 7 tomorrow morning; asks someone else to cover tonight; no apology added",
  pos="after", cx=3)
# 161 newsroom caption fix
R("messages", {**MSG_C, "transcript": "pablo the photo caption says tuesday it was monday please fix"},
  "Pablo, the photo caption says Tuesday, but it was Monday. Please fix it.",
  {"must_include": ["Pablo", "photo caption", "Tuesday", "Monday"]},
  note="facts: caption says Tuesday (wrong); it was Monday; both days kept as contrast", length="short")
# 162 lab schedule shuffle
R("messages", {**MSG_W, **FULL,
               "transcript": "okay small schedule shuffle for next week um the instrument training moves from tuesday at two to wednesday at ten because the technician can't make tuesday uh group meeting stays thursday at four but it's in room three one two not the usual room and the safety refresher is now friday morning at nine everyone has to attend that one even if you did it last year"},
  "Small schedule shuffle for next week: the instrument training moves from Tuesday at 2 to Wednesday at 10 because the technician can't make Tuesday. Group meeting stays Thursday at 4, but it's in room 312, not the usual room. The safety refresher is now Friday morning at 9. Everyone has to attend that one, even if you did it last year.",
  {"numbers": ["2", "10", "4", "312", "9"], "must_include": ["next week", "instrument training", "Wednesday at 10", "Thursday at 4", "room 312", "Friday morning at 9", "Everyone has to attend", "even if you did it last year"], "min_negations": 2},
  note="facts: next week: training Tue 2 -> Wed 10 (technician can't do Tue); group meeting stays Thu 4 but room 312, not usual; safety refresher now Friday morning at 9; everyone must attend even if done last year",
  length="long")
# 163 fintech word cap
R("nl_instruction", {**MSG_W, "instruction": "keep it under 25 words",
                     "transcript": "so basically the batch payout to vendors which was supposed to go at four is delayed till six because treasury hasn't funded the account yet"},
  "The vendor batch payout planned for 4 is delayed till 6 because treasury hasn't funded the account yet.",
  {"numbers": ["4", "6"], "must_include": ["vendor batch payout", "delayed till 6", "treasury", "hasn't funded"], "min_negations": 1, "max_words": 25},
  note="facts: vendor batch payout due 4, delayed till 6; treasury hasn't funded account yet ('yet' kept)",
  pos="after", cx=1)
# 164 support handoff
R("messages", {**MSG_C,
               "transcript": "musa can you take over the chat with the guy from pinecrest he's asking about bulk licences i've already sent him the pricing page he wants a call with sales"},
  "Musa, can you take over the chat with the guy from Pinecrest? He's asking about bulk licences. I've already sent him the pricing page, and he wants a call with sales.",
  {"must_include": ["Musa", "Pinecrest", "bulk licences", "pricing page", "call with sales"]},
  note="facts: Musa to take over Pinecrest chat; bulk licences; pricing page already sent; customer wants a sales call")
# 165 en-in retail
R("messages", {**MSG_W, **IN,
               "transcript": "kemal bhai please don't open the new carton of shampoos the old stock should be finished first otherwise expiry problem will come"},
  "Kemal bhai, please don't open the new carton of shampoos. The old stock should be finished first, otherwise there will be an expiry problem.",
  {"must_include": ["Kemal bhai", "don't open", "new carton", "old stock", "expiry problem"], "min_negations": 1},
  note="facts: don't open new shampoo carton; finish old stock first, else expiry problem")
# 166 game studio, casual, drop repetition
R("multi_constraint", {**MSG_W, "register": "casual", "instruction": "drop the repetition and keep my terminology",
                       "transcript": "so the boss fight is like way too hard in the playtest builds like way too hard eight out of ten testers quit at phase two um so design wants to nerf the slam attack and add a checkpoint before phase two and kemal said he'll have a build with both changes by wednesday"},
  "The boss fight is way too hard in the playtest builds: 8 out of 10 testers quit at phase 2. Design wants to nerf the slam attack and add a checkpoint before phase 2, and Kemal said he'll have a build with both changes by Wednesday.",
  {"numbers": ["8", "10", "2"], "must_include": ["boss fight", "way too hard", "playtest builds", "8 out of 10", "nerf the slam attack", "checkpoint", "Kemal", "Wednesday"]},
  note="facts: boss too hard (said twice, once kept); 8/10 testers quit at phase 2; design: nerf slam + checkpoint before phase 2; Kemal said build with both by Wednesday; terms nerf/slam/checkpoint kept",
  pos="after", cx=2)
# 167 hotel minibar
R("messages", {**MSG_W, "transcript": "the minibar in suite eleven hasn't been restocked since checkout"},
  "The minibar in Suite 11 hasn't been restocked since checkout.",
  {"numbers": ["11"], "must_include": ["minibar", "Suite 11", "since checkout"], "min_negations": 1},
  note="facts: Suite 11 minibar not restocked since checkout", length="short")
# 168 esports analyst split
R("messages", {**MSG_W,
               "transcript": "hey sigrid so while i'm away for the lan the analyst work splits like this um kemal does the opponent vods for the group stage annika handles the draft notes and you're doing the stat sheets please send everything to the coach by eight p m the night before each match and if the bracket changes the coach decides the priority not us"},
  "Hey Sigrid, while I'm away for the LAN, the analyst work splits like this: Kemal does the opponent VODs for the group stage, Annika handles the draft notes, and you're doing the stat sheets. Please send everything to the coach by 8 p.m. the night before each match. If the bracket changes, the coach decides the priority, not us.",
  {"numbers": ["8"], "must_include": ["Sigrid", "LAN", "Kemal", "opponent VODs", "Annika", "draft notes", "stat sheets", "8 p.m. the night before", "coach decides"], "min_negations": 1},
  note="facts: speaker away for LAN; Kemal opponent VODs (group stage), Annika draft notes, Sigrid stat sheets; send to coach by 8 p.m. night before each match; if bracket changes coach decides priority, not us",
  length="long")
# 169 newsroom approval request
R("nl_instruction", {**MSG_W, "instruction": "turn it into a short approval request, keep the condition",
                     "transcript": "um can we get the go ahead to use the drone footage from the protest the freelancer's fine with it if we credit him by name on every platform"},
  "Requesting the go-ahead to use the protest drone footage. The freelancer is fine with it if we credit him by name on every platform.",
  {"must_include": ["go-ahead", "drone footage", "protest", "freelancer", "if we credit him by name on every platform"]},
  note="facts: asks approval for protest drone footage; freelancer fine on condition of name credit on every platform",
  pos="after", cx=2)
# 170 webinar self-correction
R("messages", {**MSG_W, "transcript": "the webinar is on the twenty first sorry twenty third at five p m ist"},
  "The webinar is on the 23rd at 5 p.m. IST.",
  {"numbers": ["23", "5"], "must_include": ["webinar", "23rd", "IST"], "must_not_include": ["21"]},
  note="facts: self-correction 21st -> 23rd applied; 5 p.m. IST", length="short")
# 171 lab dewar
R("messages", {**MSG_C, "transcript": "who left the liquid nitrogen dewar open in the cold room it was half empty this morning"},
  "Who left the liquid nitrogen dewar open in the cold room? It was half empty this morning.",
  {"must_include": ["liquid nitrogen dewar", "cold room", "half empty", "this morning"]},
  note="facts: dewar left open in cold room; half empty this morning", length="short")
# 172 customer billing reply
R("multi_constraint", {**MSG_C, "instruction": "make it a clear, professional reply to the customer, no promises beyond what I said, keep the ticket number",
                       "transcript": "so there's a double charge on your card two payments of forty nine dollars on the eighth one is a duplicate i passed it to billing ticket b dash seven seven zero three they'll process the refund"},
  "There's a double charge on your card: two payments of $49 on the 8th, one of which is a duplicate. I've passed this to our billing team under ticket B-7703, and they'll process the refund.",
  {"numbers": ["49", "8", "7703"], "must_include": ["double charge", "$49", "8th", "duplicate", "B-7703", "process the refund"], "must_not_include": ["business days", "within", "sorry", "apolog"]},
  waivers=["number_missing"],
  note="facts: two $49 payments on the 8th, one duplicate; passed to billing, ticket B-7703; billing will process refund (dictated); no timeline or apology added; WAIVER: pronoun 'one is a duplicate' counted as the number 1 (known 'one' gap)",
  pos="after", cx=3)
# 173 fintech recon
R("messages", {**MSG_W, **FULL, "transcript": "neeraj the recon for october first is clean zero breaks"},
  "Neeraj, the recon for October 1 is clean, zero breaks.",
  {"numbers": ["1"], "must_include": ["Neeraj", "October 1", "clean", "zero breaks"]},
  note="facts: October 1 recon clean; zero breaks", length="short")
# 174 retail evening staff
R("messages", {**MSG_W,
               "transcript": "let the evening staff know the mall closes at nine thirty tonight instead of ten because of the parking work so start closing the tills by nine fifteen"},
  "Evening staff, the mall closes at 9:30 tonight instead of 10 because of the parking work, so start closing the tills by 9:15.",
  {"numbers": ["9:30", "10", "9:15"], "must_include": ["Evening staff", "tonight", "parking work", "closing the tills"]},
  note="facts: mall closes 9:30 tonight instead of 10 (parking work); start closing tills by 9:15; addressee named by speaker")
# 175 more direct, keep fact hedges
R("nl_instruction", {**MSG_C, "instruction": "more direct, cut the politeness padding but keep the facts",
                     "transcript": "hey so sorry to bother you kemal but would it maybe be okay if you could send me the scrim schedule when you get a minute i think the one on the drive is still the old one from last week"},
  "Kemal, can you send me the scrim schedule? I think the one on the drive is still the old one from last week.",
  {"must_include": ["Kemal", "scrim schedule", "I think", "still the old one", "last week"]},
  note="facts: request for scrim schedule; 'I think' (fact hedge) and 'still' kept; only request softeners removed ('sorry to bother you', 'would it maybe be okay', 'when you get a minute')",
  pos="after", cx=2)
# 176 hotel guest reply
R("messages", {**MSG_C, **FULL,
               "transcript": "hello ms iyer we're sorry about the noise from the renovation on the fifth floor yesterday the work is scheduled between ten a m and four p m only uh if you'd like we can move you to a room on the ninth floor today the front desk can arrange it whenever you're ready"},
  "Hello Ms. Iyer, we're sorry about the noise from the renovation on the fifth floor yesterday. The work is scheduled between 10 a.m. and 4 p.m. only. If you'd like, we can move you to a room on the ninth floor today; the front desk can arrange it whenever you're ready.",
  {"numbers": ["10", "4"], "must_include": ["Ms. Iyer", "sorry", "fifth floor", "yesterday", "10 a.m. and 4 p.m. only", "ninth floor", "whenever you're ready"]},
  note="facts: dictated apology for renovation noise on fifth floor yesterday; work 10 a.m.-4 p.m. only; dictated offer: move to ninth floor today if guest wants; greeting dictated")
# 177 game studio short
R("messages", {**MSG_C, "register": "casual", "transcript": "build server's back up sorry for the noise"},
  "Build server's back up. Sorry for the noise.",
  {"must_include": ["Build server", "back up", "Sorry for the noise"]}, length="short")
# 178 lab inspection, drop repetition
R("multi_constraint", {**MSG_W, "instruction": "message to the lab group, keep it clear, drop the repetition, keep all the dates",
                       "transcript": "hi everyone so the department is doing the fire safety inspection on the twenty seventh um the twenty seventh is a tuesday so please clear the corridors before monday evening no boxes in the corridor no boxes and uh chemicals need to be back in the cabinets labelled with your name and the date if your stuff isn't labelled it'll be thrown out ritu is collecting the sign off sheet by the twenty sixth"},
  "Hi everyone, the department is doing the fire safety inspection on Tuesday the 27th, so please clear the corridors before Monday evening. No boxes in the corridor. Chemicals need to be back in the cabinets, labelled with your name and the date. If your stuff isn't labelled, it'll be thrown out. Ritu is collecting the sign-off sheet by the 26th.",
  {"numbers": ["27", "26"], "must_include": ["Hi everyone", "fire safety inspection", "Tuesday the 27th", "before Monday evening", "No boxes", "labelled with your name and the date", "thrown out", "Ritu", "26th"], "min_negations": 2},
  waivers=["negation_lost"],
  note="facts: inspection Tuesday 27th; clear corridors before Monday evening; no boxes (repeated, kept once); chemicals in cabinets labelled name+date; unlabelled thrown out (condition); Ritu collects sign-off by 26th; WAIVER: 'no boxes' was dictated twice and the instruction asks to drop repetition, so one negation instance remains for it (all distinct negations kept)",
  pos="before", cx=3, length="long")
# 179 newsroom no comment
R("messages", {**MSG_W,
               "transcript": "chen we still haven't heard back from the minister's office on the comment it's been two days i'm running it with a line saying they didn't respond"},
  "Chen, we still haven't heard back from the minister's office on the comment. It's been two days. I'm running it with a line saying they didn't respond.",
  {"must_include": ["Chen", "still haven't heard back", "minister's office", "two days", "didn't respond"], "min_negations": 2},
  note="facts: still no reply from minister's office on comment; two days; running with a 'didn't respond' line")
# 180 en-in fintech GST
R("messages", {**MSG_W, **IN,
               "transcript": "swati ji the gst refund of three lakh twenty thousand rupees got credited today but the interest part is still pending i'll follow up with the ca"},
  "Swati ji, the GST refund of ₹3,20,000 got credited today, but the interest part is still pending. I'll follow up with the CA.",
  {"numbers": ["3,20,000"], "must_include": ["Swati ji", "GST refund", "₹3,20,000", "credited today", "still pending", "CA"]},
  note="facts: GST refund ₹3,20,000 (rupees spoken) credited today; interest still pending; dictated commitment: speaker follows up with CA")
# 181 crisp incident update from long dictation
R("nl_instruction", {**MSG_W, "instruction": "make this a crisp incident update, keep the ticket IDs and times",
                     "transcript": "okay so uh where we are with the email delivery thing um so since about eight this morning some customers on the starter plan aren't getting notification emails uh we think it's the new sending provider rate limiting us but we're not sure yet abhishek opened sup dash four four seven one for tracking and the provider ticket is p r dash two zero nine eight uh we've moved half the traffic back to the old provider as of ten thirty and that seems to be helping next update at noon"},
  "Email delivery update: since about 8 this morning, some starter plan customers aren't getting notification emails. We think the new sending provider is rate limiting us, but we're not sure yet. Abhishek opened SUP-4471 for tracking; the provider ticket is PR-2098. As of 10:30, we've moved half the traffic back to the old provider, which seems to be helping. Next update at noon.",
  {"numbers": ["8", "4471", "2098", "10:30"], "must_include": ["about 8 this morning", "starter plan", "We think", "not sure yet", "Abhishek", "SUP-4471", "PR-2098", "half the traffic", "seems to be helping", "noon"], "min_negations": 2},
  note="facts: since about 8 a.m. some starter-plan customers miss notification emails; suspected (hedged) provider rate limiting, not sure; Abhishek opened SUP-4471; provider ticket PR-2098; half traffic back to old provider as of 10:30, 'seems' to help; next update noon",
  pos="before", cx=2, length="long")
# 182 esports result
R("messages", {**MSG_C, "register": "casual", "transcript": "we won three one gg everyone"},
  "We won 3-1. GG, everyone.",
  {"numbers": ["3", "1"], "must_include": ["We won", "3-1", "GG"]},
  note="facts: won 3-1 (score order kept)", length="short")
# 183 en-in retail
R("messages", {**MSG_C, **IN,
               "transcript": "can someone check if we have the blue kurta in medium a customer is waiting at the trial room"},
  "Can someone check if we have the blue kurta in medium? A customer is waiting at the trial room.",
  {"must_include": ["blue kurta", "medium", "trial room"]}, length="short")
# 184 hotel: keep the no, polite, cap
R("multi_constraint", {**MSG_W, "instruction": "keep the no, make it polite, under 40 words, no extra offers",
                       "transcript": "no we can't give the group a free upgrade the suites are fully booked friday and saturday the only thing we can do is early check in at noon if the rooms are ready"},
  "Unfortunately, no, we can't give the group a free upgrade, as the suites are fully booked on Friday and Saturday. The only thing we can do is early check-in at noon if the rooms are ready.",
  {"must_include": ["no", "can't", "free upgrade", "fully booked", "Friday and Saturday", "early check-in at noon", "if the rooms are ready"], "min_negations": 2, "max_words": 40},
  note="facts: refusal of free upgrade kept; suites full Friday and Saturday; only option: early check-in at noon if rooms are ready (condition kept); no extra offers",
  pos="after", cx=3)
# 185 lab cluster job
R("messages", {**MSG_C,
               "transcript": "abhishek the cluster job crashed again out of memory at epoch forty i'm restarting it with batch size sixteen instead of thirty two"},
  "Abhishek, the cluster job crashed again, out of memory at epoch 40. I'm restarting it with batch size 16 instead of 32.",
  {"numbers": ["40", "16", "32"], "must_include": ["Abhishek", "crashed again", "out of memory", "epoch 40", "batch size 16 instead of 32"]},
  note="facts: crashed again (fact), OOM at epoch 40; restart with batch size 16 instead of 32")
# 186 game studio playtest incident
R("messages", {**MSG_W,
               "transcript": "playtest servers went down at six forty during the session uh about two hundred players got disconnected ops says it was a ddos they've got mitigation on now and we're back up as of seven ten we'll extend the playtest by an hour to make up for it"},
  "Playtest servers went down at 6:40 during the session, and about 200 players got disconnected. Ops says it was a DDoS; they've got mitigation on now, and we're back up as of 7:10. We'll extend the playtest by an hour to make up for it.",
  {"numbers": ["6:40", "200", "7:10"], "must_include": ["Playtest servers", "about 200", "DDoS", "mitigation", "back up as of 7:10", "extend the playtest by an hour"]},
  note="facts: down at 6:40; about 200 disconnected; ops says DDoS, mitigation on; back up as of 7:10; dictated commitment: extend playtest by an hour")

# ---------------------------------------------------------------- chunk 3 (187-230)
# 187 lab: bullet the three blockers for the PI
R("multi_constraint", {"format": "auto", "context": "work", "instruction": "bullet the three blockers with one intro line, nothing else",
                       "transcript": "okay so for the pi's update um the experiment is stuck and it's basically three things holding it up the first is the incubator's co two sensor which has been reading wrong since monday facilities say a technician might come on thursday second the ethics amendment for the new cohort hasn't been approved yet the committee meets on the nineteenth and third the mice from the supplier are delayed to the twenty fourth so even if everything else is fixed we can't start before then"},
  "The experiment is stuck on three things:\n- The incubator's CO2 sensor has been reading wrong since Monday; facilities say a technician might come on Thursday\n- The ethics amendment for the new cohort hasn't been approved yet; the committee meets on the 19th\n- The mice from the supplier are delayed to the 24th, so even if everything else is fixed, we can't start before then",
  {"numbers": ["19", "24"], "must_include": ["three things", "CO2 sensor", "since Monday", "might come on Thursday", "ethics amendment", "hasn't been approved yet", "19th", "24th", "can't start before then"], "min_negations": 2, "format": "bullets"},
  waivers=["number_missing"],
  note="facts: 3 blockers: CO2 sensor wrong since Monday, technician 'might' come Thursday (hedge); ethics amendment not yet approved, committee meets 19th; mice delayed to 24th so can't start before then even if rest fixed; bullets instructed; WAIVER: checker reads 'the first is' as the number 1",
  pos="after", cx=3)
# 188 SaaS PR review
R("messages", {**MSG_W, **FULL,
               "transcript": "abhishek can you look at my pr on hotfix slash billing dash rounding before the four p m deploy it changes how we round invoice totals so finance should probably see it too"},
  "Abhishek, can you look at my PR on hotfix/billing-rounding before the 4 p.m. deploy? It changes how we round invoice totals, so finance should probably see it too.",
  {"numbers": ["4"], "must_include": ["Abhishek", "hotfix/billing-rounding", "4 p.m. deploy", "invoice totals", "probably"]},
  note="facts: branch hotfix/billing-rounding verbatim; review before 4 p.m. deploy; changes invoice rounding; finance 'probably' should see it (hedge)")
# 189 en-in fintech WhatsApp ops group
R("nl_instruction", {**MSG_C, **IN, "instruction": "WhatsApp to the ops group, keep it short and keep every amount",
                     "transcript": "guys today's payout batch is done um total was one crore twelve lakh rupees across four hundred and six merchants three of them failed because of wrong ifsc codes i've already emailed those three merchants to update their bank details and we'll retry them in tomorrow's batch uh the batch also went out forty minutes late because of the bank's maintenance window so please don't panic if merchants call asking"},
  "Today's payout batch is done: ₹1.12 crore across 406 merchants. Three failed due to wrong IFSC codes; I've emailed those merchants to update their bank details, and we'll retry them in tomorrow's batch. The batch went out 40 minutes late because of the bank's maintenance window, so please don't panic if merchants call asking.",
  {"numbers": ["406", "40"], "must_include": ["₹1.12 crore", "406 merchants", "Three failed", "IFSC", "tomorrow's batch", "40 minutes late", "maintenance window", "don't panic"], "min_negations": 1},
  waivers=["number_missing", "number_invented"],
  note="facts: batch done, ₹1.12 crore (= 1 crore 12 lakh rupees) across 406 merchants; 3 failed (wrong IFSC), merchants emailed, retry tomorrow; batch 40 min late (bank maintenance); don't panic if merchants call. WAIVER: checker cannot parse 'one crore twelve lakh' or the crore figure",
  pos="before", cx=2)
# 190 hotel shuttle
R("messages", {**MSG_W, **FULL, "locale": "en-gb", "transcript": "the shuttle to the convention centre leaves every thirty minutes from eight"},
  "The shuttle to the convention centre leaves every 30 minutes from 8.",
  {"numbers": ["30", "8"], "must_include": ["shuttle", "convention centre", "every 30 minutes"]},
  note="facts: shuttle every 30 minutes from 8 (no a.m./p.m. spoken)")
# 191 esports pushback, alternatives kept
R("messages", {**MSG_W,
               "transcript": "neeraj look i get that the sponsor wants a stream on match day and i know they're paying for the bootcamp but the players need to rest the night before the semis so we're not doing a late stream on the twelfth that's final uh what we can do is a stream on the fourteenth after the final or a short q and a on the eleventh in the afternoon if the sponsor is okay with that"},
  "Neeraj, I get that the sponsor wants a stream on match day, and I know they're paying for the bootcamp, but the players need to rest the night before the semis, so we're not doing a late stream on the 12th. That's final. What we can do is a stream on the 14th after the final, or a short Q&A on the 11th in the afternoon, if the sponsor is okay with that.",
  {"numbers": ["12", "14", "11"], "must_include": ["Neeraj", "sponsor", "bootcamp", "rest the night before the semis", "not doing a late stream", "That's final", "14th after the final", "Q&A on the 11th", "if the sponsor is okay"], "min_negations": 1},
  note="facts: refusal: no late stream on the 12th (players rest before semis), final; alternatives both kept: stream 14th after final OR short Q&A 11th afternoon, conditional on sponsor being okay")
# 192 newsroom calmer, cap
R("multi_constraint", {**MSG_W, "instruction": "calmer, under 60 words, keep the time and the name",
                       "transcript": "lena um so the wire photo we used on the homepage for the senate story is the wrong person it's not the senator it's her aide i checked against the official portrait and a reader already emailed about it uh we need to swap it right now it's been up since six fifteen i've got the correct photo from the agency ready in the cms just need you to approve the swap"},
  "Lena, the homepage wire photo for the senate story shows her aide, not the senator. I checked it against the official portrait, and a reader already emailed about it. It's been up since 6:15, so we need to swap it now. The correct agency photo is ready in the CMS; I just need your approval for the swap.",
  {"numbers": ["6:15"], "must_include": ["Lena", "homepage", "senate story", "her aide, not the senator", "official portrait", "reader", "since 6:15", "swap it now", "CMS", "approval"], "min_negations": 1, "max_words": 60},
  note="facts: homepage photo is the aide, not the senator; checked vs official portrait; a reader emailed; up since 6:15; swap needed now (urgency kept); correct agency photo ready in CMS; needs Lena's approval",
  pos="after", cx=3)
# 193 retail escalator
R("messages", {**MSG_W, **FULL, "transcript": "two customers complained the escalator by gate b is making a grinding noise"},
  "Two customers complained the escalator by Gate B is making a grinding noise.",
  {"must_include": ["Two customers", "escalator", "Gate B", "grinding noise"]},
  note="facts: two customers complained; escalator by Gate B grinding")
# 194 lab short
R("messages", {**MSG_C, "transcript": "sigrid did you move the gfp construct it used to be in box four"},
  "Sigrid, did you move the GFP construct? It used to be in box 4.",
  {"numbers": ["4"], "must_include": ["Sigrid", "GFP construct", "box 4"]},
  note="facts: asks Sigrid if she moved GFP construct; used to be in box 4")
# 195 customer reply, keep the no
R("nl_instruction", {**MSG_C, "instruction": "reply to the customer, polite, keep the no, don't suggest anything I didn't mention",
                     "transcript": "so we can't restore deleted workspaces after thirty days that's a hard limit in our retention policy um i checked and your workspace was deleted on august second so it's past that window unfortunately uh the billing for it stopped on the same day so you weren't charged after that i can help you set up a new one though and if you still have the csv exports from before we can import those"},
  "Unfortunately, we can't restore deleted workspaces after 30 days; that's a hard limit in our retention policy. I checked, and your workspace was deleted on August 2, so it's past that window. Billing for it stopped on the same day, so you weren't charged after that. I can help you set up a new one, though, and if you still have the CSV exports from before, we can import those.",
  {"numbers": ["30", "2"], "must_include": ["can't restore", "30 days", "retention policy", "August 2", "past that window", "weren't charged", "set up a new one", "CSV exports"], "min_negations": 1},
  waivers=["number_invented"],
  note="facts: refusal: no restore after 30 days (hard limit); workspace deleted August 2, past window; billing stopped same day, not charged after; dictated offers only: help set up a new one; import CSV exports if customer still has them; WAIVER: 'august second' written 'August 2' is flagged as an invented 2",
  pos="after", cx=3)
# 196 game studio leave handover
R("messages", {**MSG_W, **FULL,
               "transcript": "okay so i'm out from tomorrow for paternity leave um four weeks the netcode refactor goes to chen he's got the design doc and the branch is refactor slash netcode dash v three the console cert questions go to annika and the weekly build email musa can you send that on mondays at ten uh don't merge the netcode branch into main without a full soak test even if it looks green"},
  "I'm out from tomorrow for paternity leave, four weeks. The netcode refactor goes to Chen; he's got the design doc, and the branch is refactor/netcode-v3. Console cert questions go to Annika. Musa, can you send the weekly build email on Mondays at 10? Don't merge the netcode branch into main without a full soak test, even if it looks green.",
  {"numbers": ["10"], "must_include": ["tomorrow", "paternity leave", "four weeks", "Chen", "design doc", "refactor/netcode-v3", "Annika", "Musa", "Mondays at 10", "full soak test", "even if it looks green"], "min_negations": 2},
  note="facts: out from tomorrow, paternity leave, 4 weeks; netcode refactor to Chen (has design doc), branch refactor/netcode-v3; cert questions to Annika; Musa sends weekly build email Mondays at 10; don't merge netcode into main without full soak test even if green")
# 197 fintech fraud rule
R("messages", {**MSG_W, **FULL, "transcript": "fraud rule nineteen is blocking legit transactions from kerala pausing it for an hour"},
  "Fraud rule 19 is blocking legit transactions from Kerala. Pausing it for an hour.",
  {"numbers": ["19"], "must_include": ["Fraud rule 19", "legit transactions", "Kerala", "for an hour"]},
  note="facts: rule 19 blocking legit Kerala transactions; paused for an hour")
# 198 en-in hotel VIP
R("messages", {**MSG_W, **IN, **FULL,
               "transcript": "ritu please inform housekeeping that the vip arriving at four needs the room ready by three and there should be no flowers in the room he's allergic"},
  "Ritu, please inform housekeeping that the VIP arriving at 4 needs the room ready by 3, and there should be no flowers in the room; he's allergic.",
  {"numbers": ["4", "3"], "must_include": ["Ritu", "housekeeping", "VIP", "ready by 3", "no flowers", "allergic"], "min_negations": 1},
  note="facts: VIP arrives 4, room ready by 3; no flowers (VIP allergic)")
# 199 esports scrim WhatsApp, terminology
R("multi_constraint", {**MSG_C, "register": "casual", "instruction": "keep my terminology, drop the repetition, keep it under 80 words",
                       "transcript": "yo team quick one um for tonight's scrim we're running the double support comp on the first two maps and on map three we go back to standard uh jake you're shot calling tonight not kemal and please everyone stay on comms after the scrim for like ten minutes for the review please stay on comms don't just leave"},
  "Yo team, quick one for tonight's scrim: we're running the double support comp on the first two maps, and on map 3 we go back to standard. Jake, you're shot calling tonight, not Kemal. Everyone, please stay on comms for about 10 minutes after the scrim for the review. Don't just leave.",
  {"numbers": ["3", "10"], "must_include": ["Yo team", "double support comp", "first two maps", "map 3", "standard", "Jake", "shot calling", "not Kemal", "stay on comms", "about 10 minutes", "Don't just leave"], "min_negations": 2, "max_words": 80},
  note="facts: double support comp maps 1-2, standard on map 3; Jake shot calls tonight, not Kemal; stay on comms about ('like') 10 min after scrim for review (repeat dropped); don't leave; 'yo team' dictated",
  pos="after", cx=3)
# 200 newsroom embargo
R("messages", {**MSG_W, **FULL, "transcript": "embargo lifts at midnight do not tweet before then"},
  "Embargo lifts at midnight. Do not tweet before then.",
  {"must_include": ["Embargo", "midnight", "Do not tweet"], "min_negations": 1},
  note="facts: embargo until midnight; no tweeting before then")
# 201 retail POS incident
R("messages", {**MSG_W, **FULL,
               "transcript": "so the pos system went down at the main store at twelve twenty and came back at twelve fifty five during that time we billed manually on paper slips there are about forty slips musa please enter them into the system before close and match the cash and if anything doesn't match flag it to me don't adjust it yourself"},
  "The POS system went down at the main store at 12:20 and came back at 12:55. During that time, we billed manually on paper slips; there are about 40. Musa, please enter them into the system before close and match the cash. If anything doesn't match, flag it to me. Don't adjust it yourself.",
  {"numbers": ["12:20", "12:55", "40"], "must_include": ["POS", "main store", "paper slips", "about 40", "Musa", "before close", "match the cash", "flag it to me", "Don't adjust it yourself"], "min_negations": 2},
  note="facts: POS down 12:20-12:55 at main store; manual billing on paper slips, about 40; Musa enters them before close, matches cash; mismatch -> flag to speaker; never adjust personally (separate rule)")
# 202 short dictation, friendly
R("nl_instruction", {**MSG_C, "instruction": "message to Pablo, friendly",
                     "transcript": "your poster got accepted for the symposium"},
  "Good news, Pablo: your poster got accepted for the symposium.",
  {"must_include": ["Pablo", "poster", "accepted", "symposium"]},
  note="facts: Pablo's poster accepted for symposium; addressee from instruction; friendly wording only, no added event", pos="before", cx=2)
# 203 shorter, firm about not confirming
R("nl_instruction", {**MSG_W, "instruction": "make it shorter and firm about not confirming anything",
                     "transcript": "jake so um the enterprise customer the one from northgate no not them the one from tallyrock they asked for an sla credit for last week's outage uh they're saying it was down for more than four hours and their contract says anything over four hours gets a ten percent credit i told them i'd check with you so please don't confirm anything to them yet until we've looked at the uptime logs"},
  "Jake, the Tallyrock enterprise customer asked for an SLA credit for last week's outage. They say it was down for more than four hours, and their contract gives a 10% credit for anything over four hours. I told them I'd check with you. Don't confirm anything to them until we've looked at the uptime logs.",
  {"numbers": ["10"], "must_include": ["Jake", "Tallyrock", "SLA credit", "last week's outage", "They say", "more than four hours", "10% credit", "check with you", "Don't confirm anything", "uptime logs"], "must_not_include": ["Northgate"], "min_negations": 1},
  waivers=["negation_lost"],
  note="facts: self-correction Northgate -> Tallyrock; SLA credit for last week's outage; customer CLAIMS (kept as 'they say') down more than 4 hours; contract: over 4 hours -> 10% credit; speaker said would check; don't confirm until uptime logs checked; WAIVER: 'no not them' belongs to the applied self-correction, so it does not survive; the real negation (don't confirm) is kept",
  pos="after", cx=2)
# 204 hotel spa question
R("messages", {**MSG_C, **FULL, "transcript": "is the spa open on monday or is it still closed for the refurb"},
  "Is the spa open on Monday, or is it still closed for the refurb?",
  {"must_include": ["spa", "Monday", "still closed", "refurb"], "ends_with_question": True},
  note="facts: question with both options kept; not answered")
# 205 fintech formal approval with conditions
R("multi_constraint", {**MSG_W, **IN, "instruction": "formal, under 65 words, keep every condition and amount",
                       "transcript": "kemal sir i need your approval for onboarding the new payment aggregator um their setup fee is two lakh fifty thousand rupees one time and then point four percent per transaction uh we go ahead only if they agree to a ninety day exit clause and their pci certificate is valid past march if either of those is missing we drop them and continue with the current provider the legal review is done already"},
  "Kemal sir, I need your approval to onboard the new payment aggregator. Their setup fee is ₹2,50,000 one-time, then 0.4% per transaction. We proceed only if they agree to a 90-day exit clause and their PCI certificate is valid beyond March. If either is missing, we drop them and continue with the current provider. The legal review is already done.",
  {"numbers": ["2,50,000", "0.4", "90"], "must_include": ["Kemal sir", "approval", "payment aggregator", "₹2,50,000", "0.4%", "only if", "90-day exit clause", "PCI certificate", "March", "If either is missing", "current provider", "legal review"], "max_words": 65},
  waivers=["number_missing", "number_invented"],
  note="facts: approval to onboard aggregator; setup ₹2,50,000 one-time (only this amount was in rupees), 0.4% per transaction; proceed only if 90-day exit clause AND PCI cert valid past March; if either missing drop them, stay with current provider; legal review done. WAIVER: checker misreads 'two lakh fifty thousand' and 'point four'",
  pos="after", cx=3)
# 206 game studio trailer
R("messages", {**MSG_C, "transcript": "jake the new trailer has the old logo at the end can you swap it before the upload at five"},
  "Jake, the new trailer has the old logo at the end. Can you swap it before the upload at 5?",
  {"numbers": ["5"], "must_include": ["Jake", "old logo", "upload at 5"], "ends_with_question": True},
  note="facts: old logo at end of new trailer; swap before upload at 5")
# 207 lab running late
R("messages", {**MSG_C, **FULL,
               "transcript": "hey annika i'm running late the bus broke down i'll be there by ten thirty can you start the pcr without me the master mix is in my drawer"},
  "Hey Annika, I'm running late, the bus broke down. I'll be there by 10:30. Can you start the PCR without me? The master mix is in my drawer.",
  {"numbers": ["10:30"], "must_include": ["Annika", "running late", "bus broke down", "10:30", "PCR", "master mix", "my drawer"]},
  note="facts: late (bus broke down); there by 10:30; asks Annika to start PCR; master mix in speaker's drawer; greeting dictated")
# 208 newsroom jargon kept
R("nl_instruction", {**MSG_W, "instruction": "clean it up for Slack but keep my newsroom jargon",
                     "transcript": "so the a one is locked except the weather box and the jump from the city hall story to a six is broken it's pointing to a five uh fix the jump line before we send pages"},
  "A1 is locked except the weather box. The jump from the city hall story to A6 is broken; it's pointing to A5. Fix the jump line before we send pages.",
  {"must_include": ["A1", "locked", "weather box", "jump", "A6", "A5", "jump line", "send pages"]},
  waivers=["number_invented"],
  note="facts: A1 locked except weather box; city hall jump to A6 broken, points to A5; fix jump line before sending pages; jargon (A1, jump, send pages) kept; WAIVER: spoken page names 'a one'/'a six'/'a five' written A1/A6/A5; checker flags the 1",
  pos="after", cx=2)
# 209 esports lineup
R("messages", {**MSG_C, **FULL, "register": "casual", "transcript": "kemal's wrist is bad he's sitting out tonight sigrid starts"},
  "Kemal's wrist is bad, so he's sitting out tonight. Sigrid starts.",
  {"must_include": ["Kemal", "wrist", "sitting out tonight", "Sigrid starts"]},
  note="facts: Kemal out tonight (wrist); Sigrid starts")
# 210 customer-facing API limits
R("messages", {**MSG_C, **FULL,
               "transcript": "hi there thanks for reaching out about the api rate limits um so on the growth plan you get six hundred requests per minute and the burst limit is a thousand for up to ten seconds if you need more than that the scale plan goes up to three thousand per minute uh you're currently on growth so the errors you're seeing are four twenty nines from hitting the burst limit i've attached the docs link in the previous message"},
  "Hi there, thanks for reaching out about the API rate limits. On the growth plan, you get 600 requests per minute, and the burst limit is 1,000 for up to 10 seconds. If you need more than that, the scale plan goes up to 3,000 per minute. You're currently on growth, so the errors you're seeing are 429s from hitting the burst limit. I've attached the docs link in the previous message.",
  {"numbers": ["600", "1,000", "10", "3,000", "429"], "must_include": ["Hi there", "growth plan", "burst limit", "scale plan", "429s", "docs link"]},
  waivers=["number_missing", "number_invented"],
  note="facts: growth plan 600 req/min, burst 1,000 for up to 10 s; scale plan up to 3,000/min if more needed; customer on growth, errors are 429s from burst limit; docs link in previous message; greeting dictated. WAIVER: checker reads 'four twenty nines' as 4/29")
# 211 hotel team floor, shorter
R("multi_constraint", {**MSG_W, "instruction": "shorter, drop the repetition, keep the room numbers and times",
                       "transcript": "okay for the cricket team arriving tonight um they're on the sixth floor the whole sixth floor rooms six oh one to six twenty and the coach is in the corner suite uh no visitors on that floor after ten no visitors and the team manager wants the breakfast room opened at six instead of seven for them pablo please brief the night security"},
  "The cricket team arriving tonight has the whole sixth floor, rooms 601 to 620, and the coach is in the corner suite. No visitors on that floor after 10. The team manager wants the breakfast room opened at 6 instead of 7 for them. Pablo, please brief the night security.",
  {"numbers": ["601", "620", "10", "6", "7"], "must_include": ["cricket team", "tonight", "sixth floor", "601 to 620", "corner suite", "No visitors", "after 10", "6 instead of 7", "Pablo", "night security"], "min_negations": 1},
  waivers=["number_missing", "number_invented", "negation_lost"],
  note="facts: team arrives tonight, whole sixth floor rooms 601-620; coach corner suite; no visitors after 10 (said twice, kept once); breakfast room at 6 instead of 7; Pablo briefs night security. WAIVER: checker reads 'six oh one' as 6/0/1 and counts the repeated 'no visitors' twice",
  pos="before", cx=3)
# 212 fintech parser incident
R("messages", {**MSG_W, **FULL,
               "transcript": "chen the reconciliation script failed on the axis bank file last night um because they changed the date format from month day year to day month year without telling anyone so about two thousand rows got parsed with the wrong dates we need to patch the parser before tonight's run at eleven and rerun yesterday's file i've already raised it with the bank's integration team ticket a x b dash three three one"},
  "Chen, the reconciliation script failed on the Axis Bank file last night because they changed the date format from month-day-year to day-month-year without telling anyone, so about 2,000 rows got parsed with the wrong dates. We need to patch the parser before tonight's run at 11 and rerun yesterday's file. I've already raised it with the bank's integration team, ticket AXB-331.",
  {"numbers": ["2,000", "11", "331"], "must_include": ["Chen", "Axis Bank", "last night", "month-day-year to day-month-year", "without telling anyone", "about 2,000", "before tonight's run at 11", "rerun yesterday's file", "AXB-331"], "min_negations": 1},
  note="facts: recon failed on Axis Bank file last night; date format changed MDY -> DMY unannounced; about 2,000 rows mis-parsed; patch parser before tonight's 11 run, rerun yesterday's file; raised with bank integration team, ticket AXB-331")
# 213 en-in retail footfall
R("messages", {**MSG_C, **IN, **FULL, "transcript": "today's footfall was around eighteen hundred highest this month"},
  "Today's footfall was around 1,800, the highest this month.",
  {"numbers": ["1,800"], "must_include": ["footfall", "around 1,800", "highest this month"]},
  note="facts: around 1,800 today (approximate); highest this month")
# 214 schedule changes, old/new clear
R("nl_instruction", {**MSG_W, "instruction": "rewrite for the team channel, make the old and new times really clear",
                     "transcript": "um so a few schedule changes for this week the sprint review got moved it was thursday at three now it's friday at eleven same link and the retro after it moves too it was thursday at four it's now friday at twelve uh and the art review with the outsourcing studio stays where it is on wednesday at two but it's going to be on zoom instead of in the big room"},
  "Schedule changes for this week: the sprint review moves from Thursday at 3 to Friday at 11, same link. The retro after it moves from Thursday at 4 to Friday at 12. The art review with the outsourcing studio stays on Wednesday at 2, but it'll be on Zoom instead of in the big room.",
  {"numbers": ["3", "11", "4", "12", "2"], "must_include": ["this week", "sprint review", "Thursday at 3 to Friday at 11", "same link", "Thursday at 4 to Friday at 12", "art review", "Wednesday at 2", "Zoom", "big room"]},
  note="facts: this week: sprint review Thu 3 -> Fri 11 (same link); retro Thu 4 -> Fri 12; art review stays Wed 2 but on Zoom instead of big room",
  pos="after", cx=2)
# 215 lab field trip, conditional
R("messages", {**MSG_W, **FULL,
               "transcript": "so for the field trip on saturday um we're collecting water samples at the three sites along the river the van leaves the department at six thirty a m sharp swati's driving uh bring boots and gloves the sample bottles are already in the van if it rains heavily we postpone to sunday same time and i'll message the group by nine the night before"},
  "For the field trip on Saturday, we're collecting water samples at the three sites along the river. The van leaves the department at 6:30 a.m. sharp, and Swati's driving. Bring boots and gloves; the sample bottles are already in the van. If it rains heavily, we postpone to Sunday, same time. I'll message the group by 9 the night before.",
  {"numbers": ["6:30", "9"], "must_include": ["field trip", "Saturday", "three sites", "6:30 a.m. sharp", "Swati", "boots and gloves", "sample bottles", "If it rains heavily", "Sunday, same time", "by 9 the night before"]},
  note="facts: Saturday field trip, water samples at three river sites; van leaves 6:30 a.m. sharp, Swati drives; bring boots/gloves; bottles in van; if heavy rain postpone to Sunday same time; speaker messages group by 9 the night before")
# 216 newsroom transcript
R("messages", {**MSG_W, **FULL, "transcript": "jake the interview transcript is in the shared folder don't quote the off the record part"},
  "Jake, the interview transcript is in the shared folder. Don't quote the off-the-record part.",
  {"must_include": ["Jake", "interview transcript", "shared folder", "Don't quote", "off-the-record"], "min_negations": 1},
  note="facts: transcript in shared folder; don't quote off-the-record part")
# 217 saying no kindly, cap
R("multi_constraint", {**MSG_W, "instruction": "say no clearly but kindly, under 65 words, keep the reason",
                       "transcript": "ritu so about dark mode for the admin panel i'm going to say no for this quarter um i know a few customers have asked and i get why but we've only got two engineers on that team and the audit logging work has to ship first because of the compliance deadline at the end of november uh maybe next quarter if the audit work lands on time but i can't promise that"},
  "Ritu, it's a no on admin panel dark mode this quarter. I know a few customers have asked, and I get why, but we only have two engineers on that team, and the audit logging work has to ship first for the compliance deadline at the end of November. Maybe next quarter if the audit work lands on time, but I can't promise that.",
  {"must_include": ["Ritu", "no", "admin panel dark mode", "this quarter", "a few customers", "two engineers", "audit logging", "end of November", "Maybe next quarter", "can't promise"], "min_negations": 2, "max_words": 65},
  note="facts: refusal for this quarter kept; a few customers asked; only two engineers; audit logging first for end-of-November compliance deadline; 'maybe' next quarter if audit lands on time, no promise",
  pos="after", cx=3)
# 218 esports reimbursement
R("messages", {**MSG_W, **FULL,
               "transcript": "pablo the travel reimbursement for the qualifier is approved um it's eight hundred euros for the flights and the hotel the taxi receipts weren't included because they were handwritten so finance needs printed ones or card statements you should see the eight hundred in your account by the end of the month and if the taxi ones get approved they'll come separately"},
  "Pablo, the travel reimbursement for the qualifier is approved: €800 for the flights and the hotel. The taxi receipts weren't included because they were handwritten, so finance needs printed ones or card statements. You should see the €800 in your account by the end of the month, and if the taxi ones get approved, they'll come separately.",
  {"numbers": ["800"], "must_include": ["Pablo", "approved", "€800", "flights and the hotel", "taxi receipts", "handwritten", "printed ones or card statements", "end of the month", "if the taxi ones get approved"]},
  note="facts: €800 approved for flights+hotel; taxi receipts excluded (handwritten), finance needs printed receipts OR card statements; €800 'should' arrive by end of month; taxi amounts separate IF approved")
# 219 hotel lost and found
R("messages", {**MSG_W, **FULL, "transcript": "lost and found has a black laptop bag from the gym no name on it"},
  "Lost and found has a black laptop bag from the gym, no name on it.",
  {"must_include": ["Lost and found", "black laptop bag", "gym", "no name"], "min_negations": 1},
  note="facts: black laptop bag from gym; no name on it")
# 220 fintech Slack cap
R("nl_instruction", {**MSG_W, **IN, "instruction": "Slack, max 45 words, keep the ticket ID",
                     "transcript": "okay so just flagging this um the merchant onboarding form is rejecting valid gst numbers if they have lowercase letters in them so like merchants who type it in lowercase get an invalid gst error even though the number is correct we've had about fifteen complaints since yesterday it's logged as ops dash one one five two can someone from the product team pick it up the workaround for now is telling merchants to type it in capitals"},
  "Merchants who enter valid GST numbers in lowercase get an invalid GST error on the merchant onboarding form. About 15 complaints since yesterday; logged as OPS-1152. Can someone from the product team pick it up? Workaround for now: tell merchants to type it in capitals.",
  {"numbers": ["15", "1152"], "must_include": ["merchant onboarding form", "valid GST numbers", "lowercase", "About 15 complaints", "since yesterday", "OPS-1152", "product team", "capitals"], "max_words": 45},
  note="facts: form rejects valid lowercase GST numbers (invalid GST error though correct); about 15 complaints since yesterday; OPS-1152; ask product team to pick up; workaround: type in capitals",
  pos="before", cx=2)
# 221 game studio localisation
R("messages", {**MSG_W, **FULL, "locale": "en-gb", "transcript": "lena the chapter four cutscene audio is out of sync only in the french build"},
  "Lena, the chapter 4 cutscene audio is out of sync, only in the French build.",
  {"numbers": ["4"], "must_include": ["Lena", "chapter 4", "out of sync", "only in the French build"]},
  note="facts: chapter 4 cutscene audio out of sync, French build only")
# 222 SaaS self-correction
R("messages", {**MSG_W, "transcript": "move the customer call with brightfold to three no four thirty"},
  "Move the customer call with Brightfold to 4:30.",
  {"numbers": ["4:30"], "must_include": ["Brightfold", "4:30"], "must_not_include": ["3"]},
  note="facts: self-correction 3 -> 4:30 applied")
# 223 lab rambling -> concise, cap
R("multi_constraint", {**MSG_W, "instruction": "concise message to my supervisor, under 60 words, keep the numbers and the hedges",
                       "transcript": "so um professor i wanted to update you on the simulations uh so basically the simulations so the ones for chapter three they're mostly done i ran eighteen out of twenty configurations the last two keep diverging after about five thousand steps and i think it's the time step being too large so i'm going to try halving it and rerun them over the weekend so hopefully everything's done by monday"},
  "Professor, the chapter 3 simulations are mostly done: I ran 18 of 20 configurations. The last two keep diverging after about 5,000 steps; I think the time step is too large. I'm going to try halving it and rerun them over the weekend, so hopefully everything's done by Monday.",
  {"numbers": ["3", "18", "20", "5,000"], "must_include": ["Professor", "chapter 3", "mostly done", "18 of 20", "last two", "about 5,000 steps", "I think", "try halving", "over the weekend", "hopefully", "Monday"], "max_words": 60},
  note="facts: chapter 3 sims mostly done; 18 of 20 run; last two diverge after about 5,000 steps; 'I think' time step too large; will 'try' halving and rerun over weekend; 'hopefully' done by Monday (hedges kept)",
  pos="after", cx=3)
# 224 retail 'tell pablo'
R("messages", {**MSG_C, "transcript": "tell pablo the window mannequins arrive tomorrow between two and four"},
  "Pablo, the window mannequins arrive tomorrow between 2 and 4.",
  {"numbers": ["2", "4"], "must_include": ["Pablo", "mannequins", "tomorrow"]},
  note="facts: mannequins arrive tomorrow between 2 and 4; Pablo addressed by speaker")
# 225 esports showmatch
R("messages", {**MSG_W, **FULL,
               "transcript": "sigrid we've been invited to the showmatch in dubai on the thirtieth all travel is covered but the prize pool is only exhibition so no money for the players can you decide by friday"},
  "Sigrid, we've been invited to the showmatch in Dubai on the 30th. All travel is covered, but the prize pool is exhibition only, so there's no money for the players. Can you decide by Friday?",
  {"numbers": ["30"], "must_include": ["Sigrid", "showmatch", "Dubai", "30th", "travel is covered", "exhibition only", "no money for the players", "Friday"], "min_negations": 1},
  note="facts: invite to Dubai showmatch on the 30th; travel covered; exhibition-only prize pool, no money for players; decide by Friday")
# 226 hotel guest reply, warm, no extras
R("nl_instruction", {**MSG_C, "instruction": "polish this reply to the guest, keep it warm but don't promise anything extra",
                     "transcript": "thank you for staying with us um so about the charge on your bill the eighteen dollars is the resort fee it's charged per night so for your four nights it comes to seventy two dollars it covers the pool the gym and the wifi and it was listed on the booking page under taxes and fees uh if you have any other questions the front desk is available twenty four hours"},
  "Thank you for staying with us. About the charge on your bill: the $18 is the resort fee, charged per night, so for your four nights it comes to $72. It covers the pool, the gym and the Wi-Fi, and it was listed on the booking page under taxes and fees. If you have any other questions, the front desk is available 24 hours.",
  {"numbers": ["18", "72", "24"], "must_include": ["Thank you for staying with us", "$18", "resort fee", "per night", "four nights", "$72", "Wi-Fi", "taxes and fees", "24 hours"], "must_not_include": ["refund", "waive", "discount"]},
  note="facts: $18 resort fee per night; four nights = $72; covers pool, gym, Wi-Fi; listed on booking page under taxes and fees; front desk 24 hours; no refund/waiver offered",
  pos="after", cx=2)
# 227 fintech chargeback
R("messages", {**MSG_W, "transcript": "the chargeback for txn ending four four nine one was won funds are back in the merchant account"},
  "The chargeback for the transaction ending 4491 was won. Funds are back in the merchant account.",
  {"numbers": ["4491"], "must_include": ["chargeback", "4491", "won", "merchant account"]},
  note="facts: chargeback on txn ending 4491 won; funds back with merchant")
# 228 newsroom sign-off with conditions
R("multi_constraint", {**MSG_W, "instruction": "ask the editor for sign-off, keep the conditions, make it concise",
                       "transcript": "abhishek so um the investigation piece on the water board contracts is ready um i want to run it sunday uh legal cleared it on two conditions we remove the contractor's home address from the documents and we give the water board until friday noon to respond if they respond we add their statement so yeah can you sign off on it"},
  "Abhishek, the investigation piece on the water board contracts is ready, and I want to run it Sunday. Legal cleared it on two conditions: we remove the contractor's home address from the documents, and we give the water board until Friday noon to respond. If they respond, we add their statement. Can you sign off?",
  {"must_include": ["Abhishek", "investigation piece", "water board contracts", "Sunday", "two conditions", "home address", "Friday noon", "If they respond", "statement", "sign off"], "ends_with_question": True},
  note="facts: piece ready, run Sunday; legal cleared on two conditions: remove contractor's home address AND give water board until Friday noon; if they respond, add statement; asks Abhishek's sign-off",
  pos="before", cx=3)
# 229 lab seminar room
R("messages", {**MSG_C, "transcript": "the seminar is in lecture hall two not the usual room"},
  "The seminar is in Lecture Hall 2, not the usual room.",
  {"numbers": ["2"], "must_include": ["seminar", "Lecture Hall 2", "not the usual room"], "min_negations": 1},
  note="facts: Lecture Hall 2, not usual room")
# 230 team WhatsApp, playful
R("nl_instruction", {**MSG_C, "instruction": "WhatsApp to the team group, make it playful",
                     "transcript": "team lunch friday at one musa's birthday don't tell him"},
  "Team lunch Friday at 1! It's Musa's birthday, so shh, don't tell him.",
  {"numbers": ["1"], "must_include": ["Team lunch", "Friday at 1", "Musa's birthday", "don't tell him"], "min_negations": 1},
  note="facts: team lunch Friday at 1; Musa's birthday; don't tell him; playful wording only", pos="before", cx=2)

save(OUT, rows)
print(len(rows), "records ->", os.path.normpath(OUT))
