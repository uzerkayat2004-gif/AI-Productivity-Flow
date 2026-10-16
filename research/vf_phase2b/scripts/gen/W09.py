"""W09 stage 1: messages bucket (work/chat messages), 40 records.

Domains: SaaS customer support, retail store operations, game studio, newsroom.
Names: Abhishek, Swati, Jake, Lena, Musa, Chen, Ritu, Pablo.
Re-run to reproduce research/vf_phase2b/data/batches/W09_s1.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W09"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl")
rows = []


def R(slice_, request, target, assertions, note=None, pos="structured", cx=0, length="medium"):
    n = len(rows) + 1
    req = {"task": "rewrite"}
    req.update(request)
    a = dict(assertions)
    a.setdefault("format", "message")
    rows.append(rec(f"TC-{WID}-{n:03d}", "messages", slice_, req, target, a, f"w09-sc-{n:03d}",
                    author=WID, note=note,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


MSG_W = {"format": "message", "context": "work"}
MSG_C = {"format": "message", "context": "chat"}

# 1
R("messages", {**MSG_W, "transcript": "um so ticket forty two eighteen is uh fixed the customer confirmed it this morning"},
  "Ticket 4218 is fixed. The customer confirmed it this morning.",
  {"numbers": ["4218"], "must_include": ["fixed", "confirmed"]},
  note="facts: ticket 4218 fixed; customer confirmed this morning", length="short")
# 2
R("messages", {**MSG_C, "register": "casual", "header_style": "full",
               "transcript": "can someone cover register three from two to four i have to step out"},
  "Can someone cover register 3 from 2 to 4? I have to step out.",
  {"numbers": ["3", "2", "4"], "must_include": ["step out"]},
  note="facts: register 3; cover from 2 to 4 (no a.m./p.m. spoken, none added)", length="short")
# 3
R("messages", {**MSG_W, "header_style": "full",
               "transcript": "so yesterday i finished the um the inventory ui bug uh the one where items duplicate when you drag them fast today i'm picking up the save system crash on console no blockers"},
  "Yesterday I finished the inventory UI bug where items duplicate when you drag them fast. Today I'm picking up the save system crash on console. No blockers.",
  {"must_include": ["inventory UI bug", "save system crash", "console", "No blockers"], "min_negations": 1},
  note="facts: yesterday finished inventory UI duplicate bug; today save system crash on console; negation 'no blockers' kept")
# 4
R("nl_instruction", {**MSG_W, "instruction": "make this a shorter Slack message, drop the repetition, and keep my original terminology",
                     "transcript": "okay so for tonight's edition um the council budget story is going to be late because uh lena is still waiting on the finance office to send the final numbers and they said they'd send it by like seven thirty so the story is going to be late basically we're holding the slot on page three for it but if it's not in by eight fifteen we swap in the transit piece instead and uh musa please don't move the photo layout until we know which one is running"},
  "The council budget story for tonight's edition is going to be late. Lena is still waiting on the finance office for the final numbers, which they said they'd send by about 7:30. We're holding the slot on page 3, but if it's not in by 8:15 we swap in the transit piece instead. Musa, please don't move the photo layout until we know which one is running.",
  {"numbers": ["7:30", "8:15", "3"], "must_include": ["Lena", "Musa", "finance office", "slot", "transit piece", "photo layout"], "min_negations": 2},
  note="facts: story late; Lena waiting on finance office, they said by about 7:30 (hedge 'like' -> 'about'); slot on page 3 held; condition: if not in by 8:15 swap in transit piece; Musa don't move photo layout until known",
  pos="after", cx=3, length="long")
# 5
R("messages", {**MSG_C, "transcript": "tell swati the refund for the acme account went through"},
  "Swati, the refund for the Acme account went through.",
  {"must_include": ["Swati", "refund", "Acme"]}, length="short")
# 6
R("messages", {**MSG_W, "tone": "friendly",
               "transcript": "hey chen um would you be able to swap shifts with me on saturday i'm on the morning one seven to three and i could take your sunday closing shift instead"},
  "Hey Chen, would you be able to swap shifts with me on Saturday? I'm on the morning one, 7 to 3, and I could take your Sunday closing shift instead.",
  {"numbers": ["7", "3"], "must_include": ["Chen", "Saturday", "Sunday closing shift"]},
  note="facts: swap Saturday morning shift 7 to 3 for Chen's Sunday closing shift; 'could' kept as offer, greeting 'hey' was dictated")
# 7
R("nl_instruction", {**MSG_W, "instruction": "more direct",
                     "transcript": "i was wondering if maybe it would be possible for someone to take a look at the build pipeline at some point because it's been failing on the android target since this morning and i'm kind of blocked on testing"},
  "Can someone take a look at the build pipeline at some point? It's been failing on the Android target since this morning and I'm kind of blocked on testing.",
  {"must_include": ["build pipeline", "Android", "since this morning", "blocked on testing"]},
  note="facts: pipeline failing on Android target since this morning; 'at some point' (no urgency) and 'kind of blocked' kept",
  pos="after", cx=1)
# 8
R("messages", {**MSG_C, "register": "casual", "transcript": "pablo the photos from the fire are in the shared drive under today's date"},
  "Pablo, the photos from the fire are in the shared drive under today's date.",
  {"must_include": ["Pablo", "shared drive", "today's date"]}, length="short")
# 9
R("messages", {**MSG_W, "length": "shorter", "header_style": "full",
               "transcript": "okay so handing off for the night um there are three open escalations the first one is the login loop for northwind ticket five one zero seven ritu was working on it and uh she thinks it's the sso config but she hasn't confirmed so don't tell the customer it's fixed the second one is the billing export that times out over ten thousand rows engineering knows about it no eta yet and the third one is uh the webhook retries for blue harbor which i already replied to so just keep an eye on that one if they write back"},
  "Handing off for the night. There are three open escalations. First is the login loop for Northwind, ticket 5107. Ritu was working on it and thinks it's the SSO config, but she hasn't confirmed, so don't tell the customer it's fixed. The second is the billing export that times out over 10,000 rows. Engineering knows about it, no ETA yet. The third is the webhook retries for Blue Harbor, which I already replied to, so just keep an eye on that if they write back.",
  {"numbers": ["5107", "10,000"], "must_include": ["three", "Northwind", "Ritu", "SSO", "Blue Harbor", "no ETA"], "min_negations": 3},
  note="facts: 3 escalations; Northwind login loop ticket 5107, Ritu thinks SSO config (hedged, not confirmed), don't tell customer it's fixed; billing export times out over 10,000 rows, no ETA; Blue Harbor webhook retries, already replied, watch if they write back",
  length="long")
# 10
R("messages", {**MSG_W, "header_style": "full",
               "transcript": "the delivery truck is running about forty minutes late so receiving starts at eleven instead"},
  "The delivery truck is running about 40 minutes late, so receiving starts at 11 instead.",
  {"numbers": ["40", "11"], "must_include": ["about", "receiving"]},
  note="facts: about 40 minutes late (approximate kept); receiving at 11", length="short")
# 11
R("messages", {**MSG_C, "register": "casual", "instruction": "casual but clear",
               "transcript": "so jake um the playtest is moved from thursday to friday at four because the qa build won't be ready in time uh same room though"},
  "Jake, the playtest moved from Thursday to Friday at 4 because the QA build won't be ready in time. Same room though.",
  {"numbers": ["4"], "must_include": ["Jake", "Thursday", "Friday", "QA build", "Same room"], "min_negations": 1},
  note="facts: playtest Thursday -> Friday at 4; reason QA build won't be ready; same room", pos="after", cx=1)
# 12
R("nl_instruction", {**MSG_W, "instruction": "keep it under 40 words",
                     "transcript": "um just a heads up the interview with the mayor's office got pushed to tomorrow at nine a m so the profile won't run today we'll run the weather explainer in that spot and abhishek is updating the homepage"},
  "Heads up: the interview with the mayor's office got pushed to tomorrow at 9 a.m., so the profile won't run today. We'll run the weather explainer in that spot, and Abhishek is updating the homepage.",
  {"numbers": ["9"], "must_include": ["mayor's office", "tomorrow", "weather explainer", "Abhishek"], "min_negations": 1, "max_words": 40},
  note="facts: interview moved to tomorrow 9 a.m.; profile won't run today; weather explainer in that spot; Abhishek updating homepage",
  pos="after", cx=1)
# 13
R("messages", {**MSG_W, "header_style": "full",
               "transcript": "jira ticket sup dash eight eight one is a duplicate of sup dash eight seven four closing it"},
  "Jira ticket SUP-881 is a duplicate of SUP-874, closing it.",
  {"numbers": ["881", "874"], "must_include": ["SUP-881", "SUP-874", "duplicate"]},
  note="facts: SUP-881 duplicates SUP-874 (direction kept); closing SUP-881", length="short")
# 14
R("multi_constraint", {**MSG_W, "instruction": "make this a shorter work message, remove repetition, and keep my original terminology",
                       "transcript": "okay so for the weekend um the planogram reset for aisle twelve is happening saturday night after close so after close on saturday uh we need four people to stay back and swati is leading it uh the endcaps stay as they are don't touch the endcaps and the new shelf strips are in the back room on the top rack the old strips go in the recycling not the trash and if we don't finish by midnight we pick it up sunday before open"},
  "The planogram reset for aisle 12 is happening Saturday night after close. We need four people to stay back, and Swati is leading it. The endcaps stay as they are, so don't touch them. The new shelf strips are in the back room on the top rack, and the old strips go in the recycling, not the trash. If we don't finish by midnight, we pick it up Sunday before open.",
  {"numbers": ["12"], "must_include": ["planogram reset", "four people", "Swati", "endcaps", "shelf strips", "back room", "top rack", "recycling", "midnight", "Sunday before open"], "min_negations": 3},
  note="facts: aisle 12 reset Saturday night after close; 4 people stay back; Swati leads; don't touch endcaps; new strips back room top rack; old strips recycling not trash; if not done by midnight, resume Sunday before open",
  pos="after", cx=3, length="long")
# 15
R("messages", {**MSG_W, "transcript": "lena can you review my pull request before lunch it's the audio mixer fix"},
  "Lena, can you review my pull request before lunch? It's the audio mixer fix.",
  {"must_include": ["Lena", "pull request", "before lunch", "audio mixer fix"]}, length="short")
# 16
R("messages", {**MSG_C, "register": "casual",
               "transcript": "ritu i um i can't make the four o'clock edit meeting can you take notes and tell me if the election coverage plan changes"},
  "Ritu, I can't make the 4 o'clock edit meeting. Can you take notes and tell me if the election coverage plan changes?",
  {"numbers": ["4"], "must_include": ["Ritu", "edit meeting", "take notes", "election coverage plan"], "min_negations": 1},
  note="facts: can't make 4 o'clock edit meeting; ask Ritu to take notes and report if plan changes (condition kept)")
# 17
R("nl_instruction", {**MSG_W, "instruction": "tighten it up but keep the condition exactly",
                     "transcript": "um i think we can probably close out the backlog of password reset tickets by end of day if musa takes the overflow queue after two"},
  "I think we can probably close out the password reset ticket backlog by end of day if Musa takes the overflow queue after 2.",
  {"numbers": ["2"], "must_include": ["I think", "probably", "if Musa takes the overflow queue"]},
  note="facts: hedged 'I think'/'probably'; by end of day; condition: if Musa takes overflow queue after 2", pos="before", cx=2)
# 18
R("messages", {**MSG_C, "transcript": "pablo did the price labels for the winter jackets get printed"},
  "Pablo, did the price labels for the winter jackets get printed?",
  {"must_include": ["Pablo", "price labels", "winter jackets"], "ends_with_question": True}, length="short")
# 19
R("multi_constraint", {**MSG_W, "header_style": "full",
                       "instruction": "make it a Slack standup update, one paragraph, and keep the ticket IDs exactly",
                       "transcript": "standup for today um yesterday i got the uh the matchmaking timeout fix merged that was g s dash two one four and i started on the leaderboard caching g s dash two two zero but it's not done yet probably tomorrow uh today i'm continuing on that and also pairing with chen on the crash reporter for like an hour after lunch blocker is i still don't have access to the analytics dashboard abhishek said he'd sort it out but it hasn't happened"},
  "Standup for today: yesterday I got the matchmaking timeout fix merged (GS-214) and started on the leaderboard caching, GS-220, but it's not done yet, probably tomorrow. Today I'm continuing on that and pairing with Chen on the crash reporter for about an hour after lunch. Blocker: I still don't have access to the analytics dashboard. Abhishek said he'd sort it out, but it hasn't happened.",
  {"numbers": ["214", "220"], "must_include": ["GS-214", "GS-220", "Chen", "Abhishek", "analytics dashboard", "probably tomorrow"], "min_negations": 3},
  note="facts: GS-214 merged; GS-220 started, not done, probably tomorrow (hedge); pairing with Chen about an hour after lunch; blocker no analytics access, Abhishek said he'd sort it, hasn't happened",
  pos="after", cx=3, length="long")
# 20
R("messages", {**MSG_W, "transcript": "correction on the earlier message the press conference is at three thirty not three"},
  "Correction on the earlier message: the press conference is at 3:30, not 3.",
  {"numbers": ["3:30", "3"], "must_include": ["Correction", "press conference"], "min_negations": 1},
  note="facts: press conference 3:30, not 3 (both kept as stated contrast)", length="short")
# 21
R("messages", {**MSG_C, "transcript": "jake can you take the chat queue from one to three no wait from two to four i've got the customer call with brightline"},
  "Jake, can you take the chat queue from 2 to 4? I've got the customer call with Brightline.",
  {"numbers": ["2", "4"], "must_include": ["Jake", "chat queue", "Brightline"], "must_not_include": ["1 to 3", "one to three"]},
  note="facts: self-correction applied: 2 to 4 (not 1 to 3); reason: customer call with Brightline")
# 22
R("messages", {**MSG_W, "register": "formal", "header_style": "full",
               "transcript": "please let the evening team know the card machine at till two is down so cash only on that till until the technician comes tomorrow morning"},
  "Evening team, the card machine at till 2 is down. That till is cash only until the technician comes tomorrow morning.",
  {"numbers": ["2"], "must_include": ["Evening team", "card machine", "cash only", "tomorrow morning"]},
  note="facts: till 2 card machine down; cash only on that till until technician tomorrow morning")
# 23
R("multi_constraint", {**MSG_W, "instruction": "tighten it up, keep the names and times exactly, and don't add anything",
                       "transcript": "hey everyone so for election night um here's the plan chen is on the live blog from six p m to midnight swati takes over the results tables uh at nine and stays till they're final um pablo and i are in the field at the counting center and we'll file short updates every hour or so we're not calling any races ourselves we only report what the election commission announces and uh if the feed goes down call me directly don't post anything unverified"},
  "Hey everyone, here's the plan for election night. Chen is on the live blog from 6 p.m. to midnight. Swati takes over the results tables at 9 and stays till they're final. Pablo and I are in the field at the counting center and will file short updates every hour or so. We're not calling any races ourselves; we only report what the election commission announces. If the feed goes down, call me directly. Don't post anything unverified.",
  {"numbers": ["6", "9"], "must_include": ["Chen", "Swati", "Pablo", "midnight", "every hour or so", "election commission"], "min_negations": 2},
  note="facts: Chen live blog 6 p.m.-midnight; Swati results tables at 9 until final; Pablo + speaker in field, updates every hour or so; not calling races; only report commission announcements; if feed down call speaker; don't post unverified",
  pos="before", cx=3, length="long")
# 24
R("messages", {**MSG_C, "register": "casual", "header_style": "full",
               "transcript": "build forty seven is up on the test server go break it"},
  "Build 47 is up on the test server, go break it.",
  {"numbers": ["47"], "must_include": ["test server", "go break it"]}, length="short")
# 25
R("nl_instruction", {"format": "auto", "instruction": "turn this into a quick Teams message for Abhishek",
                     "transcript": "um so the customer at lakeview travel says the csv import is skipping rows that have accents in the name they sent a sample file it's attached to ticket sixty three twenty two can you check if it's an encoding issue before we escalate"},
  "Abhishek, the customer at Lakeview Travel says the CSV import is skipping rows that have accents in the name. They sent a sample file, and it's attached to ticket 6322. Can you check if it's an encoding issue before we escalate?",
  {"numbers": ["6322"], "must_include": ["Abhishek", "Lakeview Travel", "CSV import", "accents", "encoding issue", "before we escalate"]},
  note="facts: Lakeview Travel CSV import skips rows with accents; sample file attached to ticket 6322; ask check encoding before escalating (recipient Abhishek from instruction)",
  pos="before", cx=1)
# 26
R("messages", {**MSG_W, "tone": "friendly",
               "transcript": "thank the morning crew for getting the stockroom sorted it looks great and remind them the inventory count is on wednesday at six a m sharp"},
  "Morning crew, thanks for getting the stockroom sorted, it looks great. A reminder that the inventory count is on Wednesday at 6 a.m. sharp.",
  {"numbers": ["6"], "must_include": ["stockroom", "inventory count", "Wednesday", "sharp"]},
  note="facts: thanks for stockroom; inventory count Wednesday 6 a.m. sharp")
# 27
R("messages", {**MSG_W, "length": "shorter", "header_style": "full",
               "transcript": "so i'm off from monday for two weeks um musa is covering the character rigs while i'm out the files are in the art share under rigs slash v three uh the dragon rig still has the wing clipping issue i haven't fixed it and please don't re export the knight rig because the animators already started on it uh if anything is urgent message lena not me because i won't be checking slack"},
  "I'm off from Monday for two weeks. Musa is covering the character rigs while I'm out; the files are in the art share under rigs/v3. The dragon rig still has the wing clipping issue, which I haven't fixed. Please don't re-export the knight rig because the animators already started on it. If anything is urgent, message Lena, not me, because I won't be checking Slack.",
  {"must_include": ["Monday", "two weeks", "Musa", "rigs/v3", "dragon rig", "knight rig", "Lena"], "min_negations": 4},
  note="facts: off from Monday for 2 weeks; Musa covers rigs; files art share rigs/v3; dragon rig wing clipping not fixed; don't re-export knight rig; urgent -> Lena not speaker; won't check Slack",
  length="long")
# 28
R("messages", {**MSG_C, "transcript": "lena the byline on the housing story is wrong it should be swati not abhishek"},
  "Lena, the byline on the housing story is wrong. It should be Swati, not Abhishek.",
  {"must_include": ["Lena", "byline", "Swati", "not Abhishek"], "min_negations": 1},
  note="facts: byline should be Swati, not Abhishek (Abhishek is the wrong current byline, must stay as the contrast)", length="short")
# 29
R("messages", {**MSG_W, "instruction": "make it sound less frustrated but keep it professional",
               "transcript": "this is the third time this week the status page didn't update during an outage and customers keep finding out from twitter before us we need someone to own the status page updates during incidents"},
  "For the third time this week, the status page didn't update during an outage, and customers are finding out from Twitter before us. We need someone to own status page updates during incidents.",
  {"must_include": ["third time this week", "status page", "Twitter", "own status page updates"], "min_negations": 1},
  note="facts: third time this week status page didn't update during outage; customers learn from Twitter first; need an owner for status page updates during incidents",
  pos="after", cx=2)
# 30
R("messages", {**MSG_W, "header_style": "full", "transcript": "the fitting rooms are closed until two for cleaning"},
  "The fitting rooms are closed until 2 for cleaning.",
  {"numbers": ["2"], "must_include": ["fitting rooms", "cleaning"]}, note="facts: closed until 2 for cleaning", length="short")
# 31
R("messages", {**MSG_C, "transcript": "hey can pablo no wait chen send me the latest trailer cut i need it for the publisher call at five"},
  "Hey, can Chen send me the latest trailer cut? I need it for the publisher call at 5.",
  {"numbers": ["5"], "must_include": ["Chen", "trailer cut", "publisher call"], "must_not_include": ["Pablo"]},
  note="facts: self-correction Pablo -> Chen applied; trailer cut needed for publisher call at 5")
# 32
R("multi_constraint", {**MSG_W, "instruction": "short status update, under 60 words, and keep every number",
                       "transcript": "okay status update on the migration um we moved about eighty percent of the accounts to the new region over the weekend the remaining twenty percent are the enterprise ones and those need a maintenance window so we're not touching them until the customers sign off uh support saw maybe a dozen tickets about slow dashboards most of them closed themselves ritu is tracking the rest"},
  "Migration status: about 80% of accounts moved to the new region over the weekend. The remaining 20% are enterprise accounts that need a maintenance window, so we're not touching them until the customers sign off. Support saw maybe a dozen tickets about slow dashboards; most closed themselves and Ritu is tracking the rest.",
  {"numbers": ["80", "20"], "must_include": ["about 80%", "enterprise", "maintenance window", "sign off", "maybe a dozen", "Ritu"], "min_negations": 1, "max_words": 60},
  note="facts: about 80% moved over weekend; remaining 20% enterprise need maintenance window, not touched until customers sign off; maybe a dozen slow-dashboard tickets (hedge), most closed, Ritu tracking rest",
  pos="after", cx=3, length="long")
# 33
R("messages", {**MSG_W, "header_style": "full", "transcript": "abhishek please hold the obituary until the family confirms the spelling"},
  "Abhishek, please hold the obituary until the family confirms the spelling.",
  {"must_include": ["Abhishek", "hold the obituary", "until the family confirms"]},
  note="facts: condition 'until the family confirms the spelling' kept", length="short")
# 34
R("messages", {**MSG_W, "locale": "en-in",
               "transcript": "musa the shipment of laptop bags is short by thirty pieces so don't put the offer sign up yet the offer price is nineteen ninety nine rupees ritu is calling the vendor"},
  "Musa, the shipment of laptop bags is short by 30 pieces, so don't put the offer sign up yet. The offer price is ₹1,999. Ritu is calling the vendor.",
  {"numbers": ["30", "1,999"], "must_include": ["Musa", "laptop bags", "₹1,999", "Ritu", "vendor"], "min_negations": 1},
  note="facts: short by 30 pieces; don't put offer sign up yet; offer price ₹1,999 (rupees spoken); Ritu calling vendor")
# 35
R("nl_instruction", {"format": "auto", "context": "work", "instruction": "Slack message for the team, keep it under 30 words",
                     "transcript": "um so just letting everyone know the server maintenance is tonight from eleven p m to one a m so the dev builds won't be reachable during that time"},
  "Server maintenance is tonight from 11 p.m. to 1 a.m., so the dev builds won't be reachable during that time.",
  {"numbers": ["11", "1"], "must_include": ["Server maintenance", "tonight", "dev builds"], "min_negations": 1, "max_words": 30},
  note="facts: maintenance tonight 11 p.m. to 1 a.m.; dev builds unreachable then", pos="before", cx=2)
# 36
R("messages", {**MSG_C, "register": "casual",
               "transcript": "swati do you want to do the onboarding call at ten or ten thirty either works for me"},
  "Swati, do you want to do the onboarding call at 10 or 10:30? Either works for me.",
  {"numbers": ["10", "10:30"], "must_include": ["Swati", "onboarding call", "Either works"]},
  note="facts: genuine alternative 10 OR 10:30, both kept; either works", length="short")
# 37
R("multi_constraint", {**MSG_C, "register": "casual", "instruction": "keep it casual and tighter, and keep both deadlines",
                       "transcript": "pablo um so about the feature on the night markets i read your draft it's really good but it's running long like fourteen hundred words and we only have space for nine hundred so can you cut it down uh maybe lose the section on the parking situation and send it back by thursday noon if you can't make thursday tell me by wednesday so i can move it"},
  "Pablo, I read your draft of the night markets feature and it's really good, but it's running long, about 1,400 words, and we only have space for 900. Can you cut it down, maybe lose the parking section, and send it back by Thursday noon? If you can't make Thursday, tell me by Wednesday so I can move it.",
  {"numbers": ["1,400", "900"], "must_include": ["Pablo", "night markets", "parking", "Thursday noon", "Wednesday"], "min_negations": 1},
  note="facts: about 1,400 words vs space for 900; cut it, 'maybe' lose parking section (hedged suggestion); back by Thursday noon; if can't make Thursday tell by Wednesday",
  pos="after", cx=3, length="long")
# 38
R("messages", {**MSG_C, "transcript": "lights in aisle five are flickering again someone log it with facilities"},
  "Lights in aisle 5 are flickering again. Someone please log it with facilities.",
  {"numbers": ["5"], "must_include": ["aisle 5", "flickering again", "facilities"]}, length="short")
# 39
R("messages", {**MSG_W, "tone": "warm", "header_style": "full",
               "transcript": "just want to say thanks to jake and ritu for staying late on friday to get the cert submission out it went through with no issues"},
  "Just want to say thanks to Jake and Ritu for staying late on Friday to get the cert submission out. It went through with no issues.",
  {"must_include": ["Jake", "Ritu", "Friday", "cert submission"], "min_negations": 1},
  note="facts: Jake and Ritu stayed late Friday; cert submission went through with no issues")
# 40
R("multi_constraint", {**MSG_W, "instruction": "more direct, no softening, and keep the ticket number",
                       "transcript": "sorry to bug you again chen but um could you maybe look at ticket eighty nine fifty when you get a sec the customer has been waiting since tuesday and they're kind of upset"},
  "Chen, can you look at ticket 8950? The customer has been waiting since Tuesday and they're upset.",
  {"numbers": ["8950"], "must_include": ["Chen", "8950", "since Tuesday"]},
  note="facts: ticket 8950; customer waiting since Tuesday; softeners ('sorry to bug you', 'maybe', 'when you get a sec', 'kind of') removed as the instruction authorises",
  pos="after", cx=3)

save(OUT, rows)
print(len(rows), "records ->", os.path.normpath(OUT))

# Stage 2 (TC-W09-101..230 -> W09_s2.jsonl) lives in W09_s2.py; running this file also regenerates it.
import runpy  # noqa: E402
runpy.run_path(os.path.join(HERE, "W09_s2.py"), run_name="__main__")
