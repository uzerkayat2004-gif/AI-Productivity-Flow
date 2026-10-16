"""W10 stage 1: messages bucket (personal messages, saved user style rules, developer house rules), 40 records.

Domains: family trip planning, apartment residents' society, chess club, hiking group, pet care.
Names: Aarav, Ishita, Zoe, Karim, Nora, Dev, Simran, Callum.
Re-run to reproduce research/vf_phase2b/data/batches/W10_s1.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W10"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl")
rows = []


def R(slice_, request, target, assertions, note=None, pos="structured", cx=0, length="medium", waivers=None):
    n = len(rows) + 1
    req = {"task": "rewrite"}
    req.update(request)
    a = dict(assertions)
    a.setdefault("format", "message")
    rows.append(rec(f"TC-{WID}-{n:03d}", "messages", slice_, req, target, a, f"w10-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


P = {"format": "message", "context": "personal"}
CH = {"format": "message", "context": "chat"}

# ---------------------------------------------------------------- messages (22)
# 1
R("messages", {**CH, "register": "casual", "locale": "en-in",
               "transcript": "hey ishita did you book the train tickets for goa yet question mark"},
  "Hey Ishita, did you book the train tickets for Goa yet?",
  {"must_include": ["Ishita", "train tickets", "Goa"], "ends_with_question": True},
  length="short")
# 2
R("messages", {**CH, "locale": "en-in", "header_style": "full",
               "transcript": "so the maintenance for october is uh two thousand four hundred rupees and it's due by the tenth not the fifteenth like last time"},
  "The maintenance for October is ₹2,400 and it's due by the 10th, not the 15th like last time.",
  {"numbers": ["2,400", "10", "15"], "must_include": ["October", "₹"], "min_negations": 1},
  note="facts: October maintenance ₹2,400 (rupees spoken); due by the 10th, NOT the 15th like last time", length="medium")
# 3
R("messages", {**P, "tone": "warm",
               "transcript": "aww nora give biscuit a cuddle from me hope his paw heals fast"},
  "Aww, Nora, give Biscuit a cuddle from me. Hope his paw heals fast.",
  {"must_include": ["Nora", "Biscuit", "paw"]}, length="short")
# 4
R("messages", {**CH, "tone": "friendly",
               "instruction": "make it a clear group message, keep it friendly, and keep all the timings exactly as I said them",
               "transcript": "okay so for sunday's hike we're meeting at the forest gate parking at six fifteen sharp um not six thirty because callum says the trail gets really hot after ten so we wanna be off the ridge by then uh bring at least two litres of water each and like proper shoes no sandals please dev is bringing the first aid kit and simran has the map if it rains on saturday night we'll probably push it to the next sunday i'll confirm by saturday evening"},
  "For Sunday's hike, we're meeting at the forest gate parking at 6:15 sharp, not 6:30, because Callum says the trail gets really hot after 10 and we want to be off the ridge by then. Please bring at least 2 litres of water each and proper shoes, no sandals. Dev is bringing the first aid kit and Simran has the map. If it rains on Saturday night, we'll probably push it to the next Sunday. I'll confirm by Saturday evening.",
  {"numbers": ["6:15", "6:30", "10", "2"], "must_include": ["Callum", "Dev", "Simran", "first aid kit", "map", "probably"], "min_negations": 2},
  note="facts: meet Sunday 6:15 sharp at forest gate parking, NOT 6:30; hot after 10 (Callum); at least 2 litres each; proper shoes, no sandals; Dev first aid kit, Simran map; condition: if rain Saturday night, probably push to next Sunday (hedge kept); speaker's own commitment to confirm by Saturday evening kept",
  pos="after", cx=3, length="long")
# 5
R("messages", {**P, "tone": "empathetic",
               "transcript": "zoe so sorry about your grandma we're all thinking of you take all the time you need"},
  "Zoe, so sorry about your grandma. We're all thinking of you. Take all the time you need.",
  {"must_include": ["Zoe", "grandma", "thinking of you", "all the time you need"]}, length="short")
# 6
R("messages", {**CH, "tone": "playful", "register": "casual",
               "transcript": "karim you absolute legend you beat the club champion in twenty two moves i'm never playing you again without a handicap"},
  "Karim, you absolute legend! You beat the club champion in 22 moves. I'm never playing you again without a handicap.",
  {"numbers": ["22"], "must_include": ["Karim", "club champion", "handicap"], "min_negations": 2},
  note="facts: Karim beat the club champion in 22 moves; 'never ... without a handicap' both negations kept", length="medium")
# 7
R("messages", {**CH, "header_style": "full",
               "transcript": "reminder for everyone the blitz night is on thursday no wait friday this week at seven in the community hall uh bring your own clock if you have one"},
  "Reminder for everyone: blitz night is on Friday this week at 7 in the community hall. Bring your own clock if you have one.",
  {"numbers": ["7"], "must_include": ["Friday", "community hall", "if you have one"], "must_not_include": ["Thursday"]},
  note="facts: self-correction Thursday -> Friday applied; at 7 (no a.m./p.m. spoken); bring own clock only if you have one", length="medium")
# 8
R("messages", {**CH, "register": "casual", "locale": "en-in",
               "transcript": "aarav reached home safe just now will call you tomorrow"},
  "Aarav, reached home safe just now. Will call you tomorrow.",
  {"must_include": ["Aarav", "reached home", "tomorrow"]},
  note="facts: speaker's own commitment 'will call you tomorrow' kept, nothing added", length="short")
# 9
R("messages", {**CH, "register": "casual", "locale": "en-in",
               "transcript": "so for the manali trip we can either take the overnight bus for like twelve hundred each or fly to chandigarh for around four thousand five hundred and then drive up let me know which one you guys prefer"},
  "For the Manali trip, we can either take the overnight bus for about 1,200 each or fly to Chandigarh for around 4,500 and then drive up. Let me know which one you guys prefer.",
  {"numbers_one_of": [["1,200", "1200"], ["4,500", "4500"]], "must_include": ["Manali", "overnight bus", "Chandigarh", "drive up"], "must_not_include": ["₹"]},
  note="facts: genuine alternative kept: overnight bus ~1,200 each OR fly to Chandigarh ~4,500 then drive; no currency spoken so no ₹; 'like' -> 'about' (approximate)", length="medium")
# 10
R("messages", {**CH, "length": "shorter", "locale": "en-in",
               "instruction": "shorter, no greeting, and keep every date and time exactly",
               "transcript": "hi everyone so um just a quick update from the committee the lift in tower b is going to be under maintenance from monday the twentieth to wednesday the twenty second so please use the tower a lift or the stairs during that time also the water tank cleaning has been moved to saturday morning so there'll be no water supply from nine to one and uh the diwali get together is still on for the twenty sixth in the clubhouse we need volunteers for decoration so if you can help please message simran"},
  "Committee update: the Tower B lift will be under maintenance from Monday the 20th to Wednesday the 22nd, so please use the Tower A lift or the stairs then. Water tank cleaning has moved to Saturday morning, so no water supply from 9 to 1. The Diwali get-together is still on for the 26th in the clubhouse. We need volunteers for decoration; if you can help, please message Simran.",
  {"numbers": ["20", "22", "9", "1", "26"], "must_include": ["Tower B", "Tower A", "stairs", "Saturday morning", "Diwali", "clubhouse", "Simran"], "must_not_include": ["Hi everyone"], "min_negations": 1},
  note="facts: Tower B lift maintenance Mon 20th to Wed 22nd, use Tower A lift or stairs; tank cleaning moved to Saturday morning, no water 9 to 1; Diwali get-together still on 26th in clubhouse; volunteers for decoration, conditional 'if you can help' message Simran; dictated greeting dropped because the instruction says no greeting",
  pos="before", cx=3, length="long")
# 11
R("messages", {**CH, "register": "casual",
               "transcript": "can you feed mochi at eight tonight she gets half a cup not a full one"},
  "Can you feed Mochi at 8 tonight? She gets half a cup, not a full one.",
  {"numbers": ["8"], "must_include": ["Mochi", "half a cup"], "min_negations": 1, "must_not_include": ["full cup"]},
  note="facts: feed Mochi at 8 tonight; half a cup, NOT a full one", length="short")
# 12
R("messages", {**CH, "tone": "friendly", "header_style": "full",
               "transcript": "ask callum if the permit for the lake trail is still valid or if we need to renew it before the fourteenth"},
  "Callum, is the permit for the Lake Trail still valid, or do we need to renew it before the 14th?",
  {"numbers": ["14"], "must_include": ["Callum", "permit", "Lake Trail", "renew"], "ends_with_question": True},
  note="facts: question kept as question (not answered): permit still valid OR renew before the 14th; no greeting added", length="medium")
# 13
R("messages", {**P, "tone": "warm", "header_style": "full",
               "transcript": "nora i just wanted to say thank you so much for planning the whole kerala trip honestly it was the best holiday we've had in years the houseboat was amazing and the kids still won't stop talking about the elephants um we owe you a proper dinner when you're back in pune maybe the weekend after next if that works for you"},
  "Nora, I just wanted to say thank you so much for planning the whole Kerala trip. Honestly, it was the best holiday we've had in years. The houseboat was amazing, and the kids still won't stop talking about the elephants. We owe you a proper dinner when you're back in Pune, maybe the weekend after next if that works for you.",
  {"must_include": ["Nora", "Kerala", "houseboat", "elephants", "Pune", "maybe", "if that works for you"], "min_negations": 1},
  note="facts: thanks for planning Kerala trip; houseboat, kids and elephants; dinner when back in Pune, hedged 'maybe the weekend after next' and conditional 'if that works for you' kept, no firm date added",
  length="long")
# 14
R("messages", {**CH,
               "transcript": "dev comma can you bring the spare boards tomorrow question mark"},
  "Dev, can you bring the spare boards tomorrow?",
  {"must_include": ["Dev", "spare boards", "tomorrow"], "ends_with_question": True}, length="short")
# 15
R("messages", {**CH, "register": "casual",
               "transcript": "so the vet said give bruno the tablet twice a day for five days sorry seven days and no long walks till then"},
  "The vet said to give Bruno the tablet twice a day for 7 days, and no long walks till then.",
  {"numbers": ["7"], "must_include": ["Bruno", "twice a day", "long walks"], "must_not_include": ["5 days", "five days"], "min_negations": 1},
  note="facts: self-correction 5 days -> 7 days applied; tablet twice a day; no long walks until then", length="medium")
# 16
R("messages", {**CH, "tone": "playful", "locale": "en-in",
               "transcript": "guys whoever parked the red scooter in front of gate two please move it the milk van has been honking for ten minutes and uncle on the ground floor is about to lose it"},
  "Guys, whoever parked the red scooter in front of Gate 2, please move it. The milk van has been honking for 10 minutes and uncle on the ground floor is about to lose it.",
  {"numbers": ["2", "10"], "must_include": ["red scooter", "milk van", "ground floor"]},
  note="facts: red scooter at Gate 2; milk van honking for 10 minutes", length="medium")
# 17
R("messages", {**CH, "register": "casual", "header_style": "full",
               "transcript": "uh made it to the summit all good heading down now"},
  "Made it to the summit, all good. Heading down now.",
  {"must_include": ["summit", "Heading down"]}, length="short")
# 18
R("messages", {**P, "tone": "empathetic",
               "transcript": "simran don't be too hard on yourself about the final you played really well for most of the game it was just that one knight move in the endgame honestly even the arbiter said it was close um we're doing analysis on wednesday at six thirty if you want to go through it together no pressure though"},
  "Simran, don't be too hard on yourself about the final. You played really well for most of the game; it was just that one knight move in the endgame. Honestly, even the arbiter said it was close. We're doing analysis on Wednesday at 6:30 if you want to go through it together. No pressure, though.",
  {"numbers": ["6:30"], "must_include": ["Simran", "knight move", "endgame", "arbiter", "Wednesday", "if you want"], "min_negations": 2},
  note="facts: analysis Wednesday 6:30, offered conditionally 'if you want'; 'don't be too hard' and 'no pressure' negations kept",
  length="long")
# 19
R("messages", {**CH, "locale": "en-in", "header_style": "full",
               "transcript": "ishita the homestay in coorg is three thousand five hundred rupees a night and they need fifty percent advance i've paid it already so you can transfer your half whenever"},
  "Ishita, the homestay in Coorg is ₹3,500 a night and they need a 50% advance. I've paid it already, so you can transfer your half whenever.",
  {"numbers": ["3,500", "50"], "must_include": ["Ishita", "Coorg", "advance", "your half", "whenever"]},
  note="facts: Coorg homestay ₹3,500 a night (rupees spoken); 50% advance already paid by speaker; Ishita transfers her half whenever (no deadline added)", length="medium")
# 20
R("messages", {**P, "tone": "excited",
               "transcript": "we're adopting the puppy we're picking her up on saturday"},
  "We're adopting the puppy! We're picking her up on Saturday!",
  {"must_include": ["adopting the puppy", "Saturday"]}, length="short")
# 21
R("messages", {**CH, "register": "casual",
               "instruction": "make it sound more casual and keep the question at the end",
               "transcript": "hello all so after last weekend a few people asked for an easier route for beginners zoe suggested the waterfall loop which is about eight kilometres would everyone be okay starting at nine"},
  "Hello all, after last weekend a few people asked for an easier route for beginners. Zoe suggested the waterfall loop, which is about 8 km. Would everyone be okay starting at 9?",
  {"numbers": ["8", "9"], "must_include": ["Hello all", "Zoe", "waterfall loop", "beginners"], "ends_with_question": True},
  note="facts: easier beginners' route requested; Zoe suggested waterfall loop, about 8 km (hedge kept); question about a 9 start kept as the final question; greeting was dictated",
  pos="before", cx=2, length="medium")
# 22
R("messages", {**CH, "tone": "friendly", "locale": "en-in", "header_style": "full",
               "transcript": "hi karim this is from flat four oh two um so i know you've got the renovation going on and that's totally fine but the drilling has been starting at like seven thirty in the morning and the society rules say no work before ten on weekdays my mum's not been well so she's been resting in the mornings could you please ask the workers to start after ten thanks a lot"},
  "Hi Karim, this is from flat 402. I know you've got the renovation going on, and that's totally fine, but the drilling has been starting at around 7:30 in the morning, and the society rules say no work before 10 on weekdays. My mum hasn't been well, so she's been resting in the mornings. Could you please ask the workers to start after 10? Thanks a lot.",
  {"numbers": ["402", "7:30", "10"], "must_include": ["Hi Karim", "renovation", "weekdays", "Thanks a lot"], "min_negations": 2},
  note="facts: flat 402; drilling starting around 7:30 a.m.; society rule no work before 10 on weekdays; mum not well; request start after 10; greeting and 'thanks a lot' dictated, no other sign-off or name added; waiver: checker reads spoken flat number 'four oh two' as 4 and 2, so it flags 402 as invented and 4/2 as missing",
  waivers=["number_missing", "number_invented"], length="long")

# ---------------------------------------------------------------- style_rules (9)
# 23
R("style_rules", {**CH, "tone": "playful", "rules": ["Never use emoji."],
                  "transcript": "happy birthday to the goodest boy pepper turns three today"},
  "Happy birthday to the goodest boy! Pepper turns three today.",
  {"must_include": ["Pepper", "goodest boy"], "numbers_one_of": [["three", "3"]]},
  note="facts: Pepper turns three today; saved rule: no emoji even with playful tone", length="short")
# 24
R("style_rules", {**CH, "rules": ["Use British spelling."], "header_style": "full",
                  "transcript": "we finalized the color for the hiking group t-shirts it's gray and callum's organizing the order so send him your sizes by friday"},
  "We finalised the colour for the hiking group T-shirts: it's grey, and Callum's organising the order, so send him your sizes by Friday.",
  {"must_include": ["finalised", "colour", "grey", "organising", "Callum", "Friday"], "must_not_include": ["color", "gray", "organizing"]},
  note="facts: shirt colour grey; Callum organising order; sizes to him by Friday; saved rule British spelling", length="medium")
# 25
R("style_rules", {**CH, "tone": "friendly", "rules": ["Write numbers as digits."],
                  "transcript": "so we need four more players for the team event anyone interested each player gets three games on the first day"},
  "We need 4 more players for the team event. Anyone interested? Each player gets 3 games on the first day.",
  {"numbers": ["4", "3"], "must_include": ["team event", "first day"], "must_not_include": ["four", "three"]},
  note="facts: 4 more players needed; 3 games each on day one; saved rule digits applied to small numbers", length="medium")
# 26
R("style_rules", {**P, "tone": "warm", "rules": ["No exclamation marks."],
                  "transcript": "congrats dev on getting your first rating points so proud"},
  "Congrats on getting your first rating points, Dev. So proud of you.",
  {"must_include": ["Dev", "rating points", "proud"], "must_not_include": ["!"]},
  note="saved rule: no exclamation marks even for congratulations", length="short")
# 27
R("style_rules", {**CH, "locale": "en-in", "rules": ["Never use emoji.", "Write numbers as digits."],
                  "transcript": "we land in jaipur at two forty and the hotel check in is from three so we'll have maybe an hour to kill"},
  "We land in Jaipur at 2:40 and hotel check-in is from 3, so we'll have maybe an hour to kill.",
  {"numbers": ["2:40", "3"], "must_include": ["Jaipur", "check-in", "maybe an hour"]},
  note="facts: land 2:40; check-in from 3; hedge 'maybe an hour' kept", length="medium")
# 28
R("style_rules", {**P, "tone": "warm", "rules": ["Use British spelling.", "No exclamation marks."],
                  "instruction": "make it warmer",
                  "transcript": "thank you zoe for looking after luna last week she clearly had a great time and we'll definitely return the favor whenever you travel"},
  "Thank you so much, Zoe, for looking after Luna last week. She clearly had a wonderful time, and we'll definitely return the favour whenever you travel.",
  {"must_include": ["Zoe", "Luna", "last week", "favour", "whenever you travel"], "must_not_include": ["favor", "!"]},
  note="facts: Zoe looked after Luna last week; dictated commitment to return the favour whenever Zoe travels kept, no date added; saved rules British spelling, no exclamation marks",
  pos="after", cx=1, length="medium")
# 29
R("style_rules", {**CH, "rules": ["Never use emoji."],
                  "instruction": "add a thumbs up emoji at the end",
                  "transcript": "route's confirmed for sunday see you all at the trailhead"},
  "Route's confirmed for Sunday. See you all at the trailhead 👍",
  {"must_include": ["Sunday", "trailhead", "👍"]},
  note="this turn's instruction (thumbs up emoji) overrides the saved 'never use emoji' rule; exactly one emoji at the end",
  pos="after", cx=1, length="short")
# 30
R("style_rules", {**CH, "locale": "en-in", "rules": ["Write numbers as digits."], "header_style": "full",
                  "transcript": "okay so the agm is on sunday the ninth at eleven in the clubhouse um there are three things on the agenda first the parking stickers second the security guard contract and third the solar panel quote which came to four lakh twenty thousand so please come with your questions and uh if you can't make it you can send a proxy form to the secretary by friday"},
  "The AGM is on Sunday the 9th at 11 in the clubhouse. There are 3 things on the agenda: first, the parking stickers; second, the security guard contract; and third, the solar panel quote, which came to 4,20,000. Please come with your questions, and if you can't make it, you can send a proxy form to the secretary by Friday.",
  {"numbers": ["9", "11", "3", "4,20,000"], "must_include": ["AGM", "clubhouse", "parking stickers", "security guard contract", "solar panel quote", "proxy form", "secretary", "Friday"], "must_not_include": ["₹"], "min_negations": 1},
  note="facts: AGM Sunday the 9th at 11, clubhouse; 3 agenda items in order (parking stickers, security guard contract, solar panel quote 4,20,000 = four lakh twenty thousand, no currency spoken so no ₹); conditional proxy form to secretary by Friday if you can't make it; format message so items stay in a sentence", length="long")
# 31
R("style_rules", {**CH, "tone": "playful", "length": "shorter", "rules": ["Never use emoji.", "No exclamation marks."],
                  "instruction": "make it playful and a bit shorter",
                  "transcript": "so i went to the open tournament today and um got completely destroyed by a ten year old in the second round like he didn't even look at the board half the time and i still lost in under thirty moves anyway i'm going back next month for revenge"},
  "Went to the open tournament today and got completely destroyed by a 10-year-old in round 2. He didn't even look at the board half the time and I still lost in under 30 moves. Going back next month for revenge.",
  {"numbers": ["10", "2", "30"], "must_include": ["open tournament", "next month", "revenge"], "must_not_include": ["!"], "min_negations": 1},
  note="facts: lost to a 10-year-old in round 2, in under 30 moves; he didn't even look at the board half the time; going back next month; saved rules: no emoji, no exclamation marks",
  pos="after", cx=2, length="medium")

# ---------------------------------------------------------------- dev_custom_style (9)
# 32
R("dev_custom_style", {**CH, "rules": ["House style: sentence case.", "Refer to the product as 'Kiteboard', never 'kite board'."],
                       "transcript": "hey nora i posted the parking notice on kite board can you pin it"},
  "Hey Nora, I posted the parking notice on Kiteboard. Can you pin it?",
  {"must_include": ["Nora", "Kiteboard", "parking notice"], "must_not_include": ["kite board"], "ends_with_question": True},
  length="short")
# 33
R("dev_custom_style", {"format": "message", "context": "work", "rules": ["Use 'customers', not 'users'."], "header_style": "full",
                       "transcript": "dev three users have asked about weekend boarding for their cats can you reply to them by tonight"},
  "Dev, three customers have asked about weekend boarding for their cats. Can you reply to them by tonight?",
  {"numbers_one_of": [["three", "3"]], "must_include": ["Dev", "customers", "weekend boarding", "tonight"], "must_not_include": ["users"]},
  note="facts: three customers asked about weekend cat boarding; request to reply by tonight; developer term rule applied", length="medium")
# 34
R("dev_custom_style", {"format": "message", "context": "work", "rules": ["Use 'customers', not 'users'."],
                       "transcript": "callum the export from the users table is missing the phone column for the pet boarding sign ups"},
  "Callum, the export from the users table is missing the phone column for the pet boarding sign-ups.",
  {"must_include": ["Callum", "users table", "phone column"]},
  note="'users table' is a database table name (a protected literal); renaming it to 'customers' would change a fact, so the house rule does not apply here", length="medium")
# 35
R("dev_custom_style", {**CH, "rules": ["House style: sentence case."],
                       "transcript": "new route alert misty ridge loop opens this weekend"},
  "New route alert: Misty Ridge loop opens this weekend.",
  {"must_include": ["Misty Ridge", "this weekend"]},
  note="sentence case keeps the proper name Misty Ridge capitalised; it never lowercases names", length="short")
# 36
R("dev_custom_style", {**CH, "locale": "en-in", "header_style": "full", "rules": ["Refer to the product as 'Kiteboard', never 'kite board'.", "Use 'members', not 'residents'."],
                       "transcript": "so all residents can now book the clubhouse through kite board um bookings open on the first of every month"},
  "All members can now book the clubhouse through Kiteboard. Bookings open on the 1st of every month.",
  {"numbers": ["1"], "must_include": ["members", "Kiteboard", "clubhouse"], "must_not_include": ["residents", "kite board"]},
  note="facts: clubhouse bookable through Kiteboard; bookings open on the 1st of every month; both house terms applied", length="medium")
# 37
R("dev_custom_style", {**CH, "rules": ["Write all times in 24-hour format."],
                       "transcript": "the rapid tournament starts at seven pm and the last round should finish around ten thirty pm"},
  "The rapid tournament starts at 19:00 and the last round should finish around 22:30.",
  {"numbers": ["19:00", "22:30"], "must_include": ["rapid tournament", "last round", "around"]},
  note="facts: start 7 p.m. = 19:00; last round should finish around 10:30 p.m. = 22:30 (hedges 'should' and 'around' kept); developer 24-hour rule is formatting, not a fact change; waiver: checker reads 'seven pm'/'ten thirty pm' as 7 and 10 and does not map them to 19:00/22:30",
  waivers=["number_missing"], length="medium")
# 38
R("dev_custom_style", {**CH, "rules": ["Say 'pet parent' instead of 'owner'."], "header_style": "full",
                       "transcript": "karim the dog walker said the owner of the building won't allow pets in the lift so take biscuit down the stairs"},
  "Karim, the dog walker said the owner of the building won't allow pets in the lift, so take Biscuit down the stairs.",
  {"must_include": ["Karim", "owner of the building", "lift", "Biscuit", "stairs"], "must_not_include": ["pet parent"], "min_negations": 1},
  note="'owner of the building' is the building's owner, not a pet owner; applying the house term would change who the person is, so it stays; negation 'won't allow pets in the lift' kept",
  length="medium")
# 39
R("dev_custom_style", {"format": "message", "context": "work", "tone": "warm",
                       "rules": ["Use 'customers', not 'users'.", "House style: sentence case.", "Refer to the product as 'Kiteboard', never 'kite board'."],
                       "instruction": "make it a bit warmer but keep the Android and iOS details exactly",
                       "transcript": "so um quick update for the team the new kite board trip planner went live this morning around forty users have already made shared itineraries uh two of them reported that the date picker shows the wrong month on android ishita's looking into it and we're not rolling it out to ios until that's fixed"},
  "Quick update for the team: the new Kiteboard trip planner went live this morning, and around 40 customers have already made shared itineraries. Two of them reported that the date picker shows the wrong month on Android. Ishita's looking into it, and we're not rolling it out to iOS until that's fixed.",
  {"numbers": ["40"], "numbers_one_of": [["two", "Two", "2"]], "must_include": ["Kiteboard", "trip planner", "customers", "date picker", "Android", "Ishita", "iOS"], "must_not_include": ["users", "kite board"], "min_negations": 1},
  note="facts: trip planner live this morning; around 40 customers made shared itineraries (hedge kept); 2 reported wrong month in date picker on Android; Ishita looking into it; NOT rolling out to iOS until fixed (condition kept)",
  pos="after", cx=2, length="long")
# 40
R("dev_custom_style", {**CH, "locale": "en-gb", "rules": ["Use British spelling.", "Refer to the product as 'Kiteboard', never 'kite board'."],
                       "transcript": "uh the kite board meetup for the hiking group is at the community center at six and dont forget your headlamps"},
  "The Kiteboard meetup for the hiking group is at the community centre at 6, and don't forget your headlamps.",
  {"numbers": ["6"], "must_include": ["Kiteboard", "community centre", "headlamps"], "must_not_include": ["kite board", "center"], "min_negations": 1},
  note="facts: meetup at the community centre at 6; don't forget headlamps; British spelling 'centre'", length="short")

save(OUT, rows)
print(len(rows), "records ->", os.path.normpath(OUT))

# Stage 2 (TC-W10-101..230 -> W10_s2.jsonl) lives in W10_s2.py (+ W10_s2_part1..3.py); run it too.
import runpy  # noqa: E402
runpy.run_path(os.path.join(HERE, "W10_s2.py"), run_name="__main__")
