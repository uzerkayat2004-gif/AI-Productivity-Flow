"""W11 stage 1: notes_format bucket (smart_formatting + no_markdown).

Teaches formatting decisions: auto -> bullets only with 3+ parallel items and a
list cue; 2 items stay a sentence; explicit order cues -> numbered; no cue ->
prose; note -> terse lines; markdown only where the instruction asks; plain ->
no Markdown; explicit format beats [Rules] preferences.
Re-run to reproduce research/vf_phase2b/data/batches/W11_s1.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W11"
BUCKET = "notes_format"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

rows = []


def R(slice_, request, target, assertions, *, pos=None, cx=0, note=None):
    n = len(rows) + 1
    words = len(request["transcript"].split())
    lc = "short" if words < 20 else ("medium" if words <= 60 else "long")
    if pos is None:
        pos = "before" if request.get("instruction") else "structured"
    rows.append(rec(f"TC-{WID}-{n:03d}", BUCKET, slice_, request, target, assertions, f"w11-sc-{n:03d}",
                    author=WID, note=note, meta={"command_position": pos, "instruction_complexity": cx,
                                                 "length_class": lc}))


SF, NM = "smart_formatting", "no_markdown"

# 1 auto, 3+ items with list cue -> bullets (kitchen)
R(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
       "transcript": "okay so for the dal tonight we need a few things red lentils um two onions a thumb of ginger and like a tin of tomatoes"},
  "For the dal tonight, we need a few things:\n- Red lentils\n- 2 onions\n- A thumb of ginger\n- A tin of tomatoes",
  {"format": "bullets", "numbers": ["2"], "must_include": ["Red lentils", "ginger", "tin of tomatoes"]},
  cx=1, note="facts: 2 onions; four items with list cue 'a few things' -> bullets")

# 2 auto, only 2 items -> sentence (IT)
R(SF, {"task": "rewrite",
       "transcript": "kiran can you grab uh the hdmi adapter and the charger for the new laptop"},
  "Kiran, can you grab the HDMI adapter and the charger for the new laptop?",
  {"format": "prose", "must_include": ["Kiran", "HDMI adapter", "charger"], "must_not_include": ["- "]},
  cx=1)

# 3 auto, explicit order cues -> numbered (IT)
R(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
       "transcript": "to set up the laptop first sign in with your work account then run the updates then install the vpn client and finally restart it before you open outlook"},
  "To set up the laptop:\n1. Sign in with your work account.\n2. Run the updates.\n3. Install the VPN client.\n4. Restart it before you open Outlook.",
  {"format": "numbered", "must_include": ["work account", "updates", "VPN client", "before you open Outlook"]},
  cx=1)

# 4 auto, no list cue -> prose (moving)
R(SF, {"task": "rewrite",
       "transcript": "so the movers come on saturday at eight and um they said they'll wrap the sofa and the piano themselves but we have to have the boxes taped and labelled by friday night and the parking permit sorted with the council oh and the lift in the new building is booked for us from ten till two so they can't start unloading before ten"},
  "The movers come on Saturday at 8. They said they'll wrap the sofa and the piano themselves, but we have to have the boxes taped and labelled by Friday night and the parking permit sorted with the council. Oh, and the lift in the new building is booked for us from 10 till 2, so they can't start unloading before 10.",
  {"format": "prose", "numbers": ["8", "10", "2"], "min_negations": 1, "must_include": ["Saturday", "sofa", "piano", "Friday night", "parking permit", "lift"]},
  cx=1, note="facts: Saturday at 8; movers' commitment 'they'll wrap the sofa and the piano'; boxes by Friday night; permit with the council; lift booked 10 till 2, can't start unloading before 10; no list cue -> prose, no bullets")

# 5 format note (research)
R(NM, {"task": "rewrite", "format": "note",
       "transcript": "note to self the hartmann paper uses a sample of four hundred and twelve participants um effect size is small like zero point two and they didn't preregister so treat the results with caution"},
  "Hartmann paper: sample of 412 participants.\nEffect size is small, about 0.2.\nNot preregistered, so treat the results with caution.",
  {"format": "note", "numbers": ["412", "0.2"], "min_negations": 1, "must_include": ["Hartmann", "caution"]},
  cx=1, note="facts: 412 participants; effect size about 0.2 ('like' = about); not preregistered; caution kept")

# 6 markdown + instruction asks for headings (kitchen recipe)
R(NM, {"task": "rewrite", "markup": "markdown",
       "instruction": "format it as a recipe in markdown with a title heading and headings for ingredients and method",
       "transcript": "this is rhea's lemon rice um you need two cups of cooked rice one lemon a teaspoon of mustard seeds a handful of peanuts and some curry leaves and for the method first heat oil and pop the mustard seeds then add the peanuts and curry leaves then stir in the rice and finally squeeze the lemon over it and salt to taste"},
  "# Rhea's Lemon Rice\n\n## Ingredients\n\n- 2 cups of cooked rice\n- 1 lemon\n- A teaspoon of mustard seeds\n- A handful of peanuts\n- Some curry leaves\n\n## Method\n\n1. Heat oil and pop the mustard seeds.\n2. Add the peanuts and curry leaves.\n3. Stir in the rice.\n4. Squeeze the lemon over it and salt to taste.",
  {"numbers": ["2"], "must_include": ["# Rhea's Lemon Rice", "## Ingredients", "## Method", "mustard seeds", "curry leaves", "salt to taste"]},
  pos="after", cx=3, note="facts: 2 cups cooked rice, 1 lemon, a teaspoon mustard seeds, handful peanuts, curry leaves; 4 steps in spoken order; headings only because the instruction asks (markup markdown)")

# 7 plain, format bullets (moving checklist)
R(NM, {"task": "rewrite", "format": "bullets",
       "transcript": "um things to sort before the move change the address with the bank cancel the broadband uh transfer the electricity account and book a van for the twenty first"},
  "Things to sort before the move:\n- Change the address with the bank\n- Cancel the broadband\n- Transfer the electricity account\n- Book a van for the 21st",
  {"format": "bullets", "numbers": ["21"], "must_include": ["bank", "broadband", "electricity account", "van"], "must_not_include": ["**", "#"]},
  cx=1, note="facts: van for the 21st; four tasks kept")

# 8 [Rules] prefer bullets, but this turn's format is prose -> prose (IT)
R(SF, {"task": "rewrite", "format": "prose", "rules": ["Prefer bullet lists where possible."],
       "transcript": "new laptops need the docking station driver printer profile and shared drive mapping before thursday"},
  "New laptops need the docking station driver, printer profile, and shared drive mapping before Thursday.",
  {"format": "prose", "must_include": ["docking station driver", "printer profile", "shared drive mapping", "Thursday"]},
  cx=2, note="facts: three items before Thursday; explicit Format prose beats the bullet preference in Rules")

# 9 cleanup + bullets (research)
R(SF, {"task": "cleanup", "format": "bullets",
       "transcript": "um the three points from the review were uh sample sizes are too small most studies are from one country and nobody measured long term effects"},
  "The three points from the review were:\n- Sample sizes are too small.\n- Most studies are from one country.\n- Nobody measured long-term effects.",
  {"format": "bullets", "min_negations": 1, "must_include": ["three points", "Sample sizes are too small", "one country", "Nobody measured"]},
  cx=1, note="facts: three points; 'nobody measured' negation kept; cleanup keeps the speaker's words")

# 10 cleanup + numbered (kitchen)
R(SF, {"task": "cleanup", "format": "numbered", "header_style": "full",
       "transcript": "so to make the cold brew um grind the beans coarse really coarse uh mix them with cold water in a jar leave it in the fridge for about eighteen hours twenty max and then strain it through a cloth and you know don't squeeze the cloth or it gets bitter then keep it in the fridge for up to a week"},
  "To make the cold brew:\n1. Grind the beans coarse, really coarse.\n2. Mix them with cold water in a jar.\n3. Leave it in the fridge for about 18 hours, 20 max.\n4. Then strain it through a cloth, and don't squeeze the cloth or it gets bitter.\n5. Then keep it in the fridge for up to a week.",
  {"format": "numbered", "numbers": ["18", "20"], "min_negations": 1, "must_include": ["coarse", "cold water", "about 18 hours", "20 max", "don't squeeze the cloth", "up to a week"]},
  cx=1, note="facts: about 18 hours, 20 max; do NOT squeeze the cloth; keep up to a week; five steps in order")

# 11 auto, 3 items + list cue -> bullets (moving)
R(SF, {"task": "rewrite", "format": "auto",
       "transcript": "hugo at the new flat check a few things the boiler the back door keys and the meter readings"},
  "Hugo, at the new flat, check a few things:\n- The boiler\n- The back door keys\n- The meter readings",
  {"format": "bullets", "must_include": ["Hugo", "boiler", "back door keys", "meter readings"]},
  cx=1)

# 12 auto, 2 items even with "two things" -> sentence (kitchen)
R(SF, {"task": "rewrite",
       "transcript": "we're out of two things basically rice and cumin"},
  "We're out of two things: rice and cumin.",
  {"format": "prose", "must_include": ["rice", "cumin"], "must_not_include": ["- "]},
  cx=1, note="facts: two items, rice and cumin; only 2 items -> stays a sentence")

# 13 format note (IT)
R(NM, {"task": "rewrite", "format": "note", "header_style": "full",
       "transcript": "note for alma laptop for the new intern um needs sixteen gigs of ram the design software license and it should not have admin rights"},
  "For Alma: laptop for the new intern.\nNeeds 16 GB of RAM.\nDesign software license.\nNo admin rights.",
  {"format": "note", "numbers": ["16"], "min_negations": 1, "must_include": ["Alma", "intern", "RAM", "Design software license", "admin rights"]},
  cx=1, note="facts: 16 GB RAM; design software license; must NOT have admin rights")

# 14 plain + instruction asking for sections -> labels, no Markdown (research)
R(NM, {"task": "rewrite",
       "instruction": "split it into a summary part and a limitations part",
       "transcript": "okay so reading notes on the food waste study um the summary is they followed sixty households for two years and shared meal planning cut food waste by about a fifth and the limitations are it was all in one city the households volunteered so they were probably already motivated and uh they didn't track what people ate outside the home"},
  "Summary:\nThe food waste study followed 60 households for two years. Shared meal planning cut food waste by about a fifth.\n\nLimitations:\n- It was all in one city.\n- The households volunteered, so they were probably already motivated.\n- They didn't track what people ate outside the home.",
  {"numbers": ["60"], "min_negations": 1, "must_include": ["Summary:", "Limitations:", "two years", "a fifth", "one city", "probably already motivated", "outside the home"], "must_not_include": ["#", "**"]},
  pos="after", cx=2, note="facts: 60 households, two years, cut by about a fifth; one city; volunteers 'probably' motivated (hedge kept); didn't track eating outside home; plain markup -> label lines, no # headings")

# 15 markdown + instruction to bold the date (moving)
R(NM, {"task": "rewrite", "markup": "markdown",
       "instruction": "bold the key deadline",
       "transcript": "the landlord wants the keys back by the thirtieth at noon and um the deposit gets returned within ten days if the inspection is fine"},
  "The landlord wants the keys back by **the 30th at noon**, and the deposit gets returned within 10 days if the inspection is fine.",
  {"numbers": ["30", "10"], "must_include": ["**the 30th at noon**", "deposit", "if the inspection is fine"]},
  cx=1, note="facts: keys by the 30th at noon; deposit within 10 days IF inspection is fine (condition kept); bold only on the deadline, as instructed")

# 16 markdown markup but nothing asks for emphasis -> plain prose (kitchen)
R(NM, {"task": "rewrite", "markup": "markdown",
       "transcript": "the oven runs hot so drop it to one hundred and eighty degrees for the focaccia"},
  "The oven runs hot, so drop it to 180 degrees for the focaccia.",
  {"numbers": ["180"], "must_include": ["focaccia"], "no_markdown": True},
  cx=1, note="facts: 180 degrees; markdown allowed but nothing calls for it -> no Markdown symbols")

# 17 auto, first/then/finally -> numbered (moving)
R(SF, {"task": "rewrite", "format": "auto",
       "transcript": "right so on moving day first neel takes the kids to his mum's then we load the big furniture uh then the boxes from the garage and finally birgit does the last walk through and locks up um so kiran said he can lend us his trolley for the fridge but he needs it back by sunday evening at the latest"},
  "On moving day:\n1. Neel takes the kids to his mum's.\n2. We load the big furniture.\n3. We load the boxes from the garage.\n4. Birgit does the last walk-through and locks up.\n\nKiran said he can lend us his trolley for the fridge, but he needs it back by Sunday evening at the latest.",
  {"must_include": ["1. Neel", "4. Birgit", "big furniture", "garage", "Birgit", "locks up", "Kiran", "trolley", "Sunday evening"]},
  cx=1, note="facts: four steps in spoken order; Kiran can lend the trolley but needs it back by Sunday evening (stays prose after the list)")

# 18 auto, long reflective research notes, no list cue -> prose
R(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
       "transcript": "i read the second half of the chapter on sleep and memory last night and honestly it was more convincing than the first half um the author separates the lab studies from the field studies which helps and she admits the field data is messy but i still don't buy the claim that naps replace a full night that part felt rushed"},
  "I read the second half of the chapter on sleep and memory last night, and honestly it was more convincing than the first half. The author separates the lab studies from the field studies, which helps, and she admits the field data is messy. But I still don't buy the claim that naps replace a full night; that part felt rushed.",
  {"format": "prose", "min_negations": 1, "must_include": ["second half", "lab studies", "field studies", "messy", "naps replace a full night", "rushed"]},
  cx=1, note="facts: second half more convincing than first; author admits field data messy; speaker still does NOT buy the nap claim; no list cue -> prose")

# 19 auto + instruction "checklist" -> bullets (IT)
R(SF, {"task": "rewrite", "header_style": "full",
       "instruction": "make it a checklist",
       "transcript": "kiran's laptop still needs the antivirus the email signature the wifi profile for the office and two factor on his account"},
  "Kiran's laptop still needs:\n- The antivirus\n- The email signature\n- The Wi-Fi profile for the office\n- Two-factor on his account",
  {"format": "bullets", "must_include": ["Kiran", "antivirus", "email signature", "profile for the office", "his account"]},
  pos="after", cx=1)

# 20 explicit numbered, hedge kept (kitchen shopping)
R(SF, {"task": "rewrite", "format": "numbered",
       "transcript": "for the weekend we need eggs flour butter and maybe some berries if they look good"},
  "For the weekend we need:\n1. Eggs\n2. Flour\n3. Butter\n4. Maybe some berries, if they look good",
  {"format": "numbered", "must_include": ["Eggs", "Flour", "Butter", "Maybe some berries", "if they look good"]},
  cx=1, note="facts: berries hedged 'maybe' and conditional 'if they look good'")

# 21 explicit bullets with only 2 items -> bullets (explicit beats auto rule) (moving/IT)
R(SF, {"task": "rewrite", "format": "bullets", "header_style": "full",
       "transcript": "the router goes in the hallway and the printer goes in the study"},
  "- Router: hallway\n- Printer: study",
  {"format": "bullets", "must_include": ["Router", "hallway", "Printer", "study"]},
  cx=1)

# 22 [Rules] numbered for steps, but this turn asks bullets -> bullets (IT)
R(SF, {"task": "rewrite", "format": "bullets", "rules": ["Always use numbered lists for steps."],
       "transcript": "back up the old laptop then wipe it and then hand it to hugo for recycling"},
  "- Back up the old laptop.\n- Wipe it.\n- Hand it to Hugo for recycling.",
  {"format": "bullets", "must_include": ["Back up the old laptop", "Wipe it", "Hugo", "recycling"]},
  cx=2, note="explicit Format bullets this turn beats the numbered-steps rule; order of steps kept")

# 23 [Rules] numbered for steps, but this turn asks prose, one sentence (IT)
R(SF, {"task": "rewrite", "format": "prose", "header_style": "full", "rules": ["Use numbered lists for any steps."],
       "instruction": "keep it as one sentence",
       "transcript": "to reset the vpn you uh open the client hit disconnect wait about ten seconds and connect again with your new password"},
  "To reset the VPN, open the client, hit Disconnect, wait about 10 seconds, and connect again with your new password.",
  {"format": "prose", "numbers": ["10"], "must_include": ["VPN", "Disconnect", "about 10 seconds", "new password"]},
  pos="after", cx=3, note="facts: wait about 10 seconds; explicit prose + one-sentence instruction beat the numbered-list rule")

# 24 note under markdown markup, nothing asks for Markdown (kitchen)
R(NM, {"task": "rewrite", "format": "note", "markup": "markdown",
       "transcript": "note fridge clear out friday um the yogurt is past date toss the half onion and use up the spinach before it goes"},
  "Fridge clear-out Friday.\nYogurt is past date.\nToss the half onion.\nUse up the spinach before it goes.",
  {"format": "note", "must_include": ["Friday", "Yogurt", "half onion", "spinach"], "no_markdown": True},
  cx=1, note="facts: clear-out on Friday; terse note lines; no Markdown even though markup allows it")

# 25 cleanup + bullets with self-correction (moving)
R(SF, {"task": "cleanup", "format": "bullets",
       "transcript": "so six no wait eight boxes for the books four for the kitchen and two for the bathroom"},
  "- 8 boxes for the books\n- 4 for the kitchen\n- 2 for the bathroom",
  {"format": "bullets", "numbers": ["8", "4", "2"], "must_not_include": ["6"], "must_include": ["books", "kitchen", "bathroom"]},
  cx=1, note="facts: self-correction six -> 8 boxes for books (6 must not appear); 4 kitchen; 2 bathroom")

# 26 cleanup + numbered from "step one/two/three", alternative kept (IT)
R(SF, {"task": "cleanup", "format": "numbered",
       "transcript": "step one plug in the dock step two open settings and pick either extend or duplicate display step three uh set the main screen as primary"},
  "1. Plug in the dock.\n2. Open Settings and pick either Extend or Duplicate display.\n3. Set the main screen as primary.",
  {"format": "numbered", "must_include": ["dock", "either Extend or Duplicate", "primary"]},
  cx=1, note="facts: alternative 'either extend or duplicate' keeps both options; three steps")

# 27 auto, 3 parallel items but no list cue -> prose (kitchen)
R(SF, {"task": "rewrite", "format": "auto",
       "transcript": "so alma's bringing the salad birgit's doing dessert and i'll handle the curry"},
  "Alma's bringing the salad, Birgit's doing dessert, and I'll handle the curry.",
  {"format": "prose", "must_include": ["Alma", "salad", "Birgit", "dessert", "I'll handle the curry"]},
  cx=1, note="facts: speaker commits to the curry ('I'll'); no list cue -> prose, no bullets")

# 28 auto, list cue "reading list" with 4 items -> bullets (research)
R(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
       "transcript": "here's my reading list for the month um the survey on remote work the two papers on attention span neel's thesis chapter on habits and the replication report from the spring and that's it"},
  "My reading list for the month:\n- The survey on remote work\n- The two papers on attention span\n- Neel's thesis chapter on habits\n- The replication report from the spring",
  {"format": "bullets", "must_include": ["remote work", "two papers on attention span", "Neel", "replication report"]},
  cx=1, note="facts: two papers on attention span; four items with list cue 'reading list' -> bullets")

# 29 bullets, long, negation + conditional (IT onboarding)
R(SF, {"task": "rewrite", "format": "bullets",
       "instruction": "keep the condition about the mouse exactly",
       "transcript": "for birgit's new laptop the setup is basically like this she needs the standard image with office installed her account added to the finance group the shared calendar and uh the expense app but not the developer tools those are only for the engineering team and also she's left handed so get the left handed mouse if we have one and if not order one"},
  "Birgit's new laptop setup:\n- Standard image with Office installed\n- Her account added to the finance group\n- The shared calendar\n- The expense app\n- Not the developer tools (those are only for the engineering team)\n- She's left-handed, so get the left-handed mouse if we have one, and if not, order one",
  {"format": "bullets", "min_negations": 2, "must_include": ["Birgit", "Office", "finance group", "shared calendar", "expense app", "developer tools", "engineering team", "if we have one", "if not, order one"]},
  pos="after", cx=2, note="facts: NOT the developer tools (engineering only); get the left-handed mouse if we have one, if not order one (condition kept)")

# 30 markdown + instruction: bullets with bold room names (moving)
R(NM, {"task": "rewrite", "format": "bullets", "markup": "markdown", "header_style": "full",
       "instruction": "bullet points with the room names in bold",
       "transcript": "packing plan by room the kitchen gets done last because we still need to cook the bedroom wardrobes go first and um the study books and files go on wednesday"},
  "- **Kitchen:** done last, because we still need to cook\n- **Bedroom:** wardrobes go first\n- **Study:** books and files go on Wednesday",
  {"format": "bullets", "must_include": ["**Kitchen:**", "**Bedroom:**", "**Study:**", "last", "first", "Wednesday"]},
  pos="after", cx=2, note="facts: kitchen last (still need to cook); bedroom wardrobes first; study books/files on Wednesday; bold only on room names as instructed")

# 31 markdown + instruction: heading on top (research)
R(NM, {"task": "rewrite", "markup": "markdown",
       "instruction": "put a heading that says key finding on top",
       "transcript": "key finding evening reminders got a higher response than morning ones but only for people under thirty"},
  "## Key finding\n\nEvening reminders got a higher response than morning ones, but only for people under 30.",
  {"numbers": ["30"], "must_include": ["## Key finding", "Evening", "morning", "only for people under 30"]},
  cx=1, note="facts: effect only for people under 30 (restriction kept); heading because instruction asks, markup markdown")

# 32 format note, plain, long (moving company call)
R(NM, {"task": "rewrite", "format": "note", "header_style": "full",
       "transcript": "notes from the call with the moving company um quote is eleven hundred and fifty euros including packing materials but not the piano that's an extra two hundred they can do the fourteenth or the sixteenth and uh we have to confirm by monday they also asked if we need storage for a few weeks and i said probably not but i'll let them know"},
  "Call with the moving company.\nQuote: €1,150 including packing materials.\nPiano not included: extra 200.\nThey can do the 14th or the 16th.\nConfirm by Monday.\nThey asked if we need storage for a few weeks: probably not, I'll let them know.",
  {"format": "note", "numbers": ["1,150", "200", "14", "16"], "min_negations": 2, "must_include": ["Monday", "packing materials", "Piano", "storage", "probably not", "let them know"], "must_not_include": ["#", "**"]},
  cx=1, note="facts: €1,150 incl. packing materials; piano NOT included, extra 200 (currency not repeated for it); 14th OR 16th both kept; confirm by Monday; storage: speaker said probably not (hedge) and committed to let them know")

# 33 auto, "number one/two/three" -> numbered (kitchen house rules)
R(SF, {"task": "rewrite", "format": "auto",
       "transcript": "kitchen rules for the flat number one wash your own dishes the same day number two label your food in the fridge number three nobody touches rhea's sourdough starter"},
  "Kitchen rules for the flat:\n1. Wash your own dishes the same day.\n2. Label your food in the fridge.\n3. Nobody touches Rhea's sourdough starter.",
  {"format": "numbered", "min_negations": 1, "must_include": ["own dishes", "Label your food", "Nobody touches Rhea's sourdough starter"]},
  cx=1, note="facts: three rules in spoken order; 'nobody touches' negation kept")

# 34 auto, 2 items with "two takeaways" -> sentence, negation (research)
R(SF, {"task": "rewrite",
       "transcript": "i've got two takeaways from the talk uh the dataset is public and the code isn't released yet"},
  "I've got two takeaways from the talk: the dataset is public, and the code isn't released yet.",
  {"format": "prose", "min_negations": 1, "must_include": ["two takeaways", "dataset is public", "code isn't released yet"], "must_not_include": ["- "]},
  cx=1, note="facts: code NOT released yet; only 2 items -> stays a sentence")

# 35 bullets + shorter + keep quantities, hedges kept (kitchen batch cook)
R(SF, {"task": "rewrite", "format": "bullets", "length": "shorter",
       "instruction": "keep every quantity and keep the banana bread optional",
       "transcript": "so for the sunday batch cook i'm thinking we do the chickpea curry which is like four portions the roast veg which makes about six and um the overnight oats for the week that's five jars and i guess if there's time a banana bread but that's optional oh and neel can't eat peanuts so no satay sauce on anything this time round"},
  "Sunday batch cook, tentative plan:\n- Chickpea curry: about 4 portions\n- Roast veg: about 6\n- Overnight oats for the week: 5 jars\n- Banana bread if there's time (optional)\n- No satay sauce this time round: Neel can't eat peanuts",
  {"format": "bullets", "numbers": ["4", "6", "5"], "must_include": ["Chickpea curry", "Roast veg", "Overnight oats", "Banana bread", "if there's time", "optional", "No satay sauce", "Neel can't eat peanuts"], "min_negations": 2},
  pos="after", cx=3, note="facts: curry about 4 portions ('like' = about), roast veg about 6, oats 5 jars; banana bread only if there's time and optional; plan is tentative ('I'm thinking'); no satay sauce because Neel can't eat peanuts")

save(OUT, rows)
print(f"wrote {len(rows)} -> {OUT}")


# ---------------------------------------------------------------- stage 2
# TC-W11-101..210 -> data/batches/W11_s2.jsonl. Parts live in W11_s2_part*.py and
# append to rows2 through R2. Stage-1 fix applied throughout: a dictated lead-in
# ("packing plan by room") is kept as a lead line before the list.
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
rows2 = []
NL = "nl_instruction"


def R2(slice_, request, target, assertions, *, pos=None, cx=0, note=None, waivers=None):
    n = 101 + len(rows2)
    words = len(request["transcript"].split())
    lc = "short" if words < 20 else ("medium" if words <= 60 else "long")
    if pos is None:
        pos = "before" if request.get("instruction") else "structured"
    rows2.append(rec(f"TC-{WID}-{n:03d}", BUCKET, slice_, request, target, assertions, f"w11-sc-{n:03d}",
                     author=WID, note=note, waivers=waivers,
                     meta={"command_position": pos, "instruction_complexity": cx, "length_class": lc}))


for _part in ("W11_s2_part1.py", "W11_s2_part2.py", "W11_s2_part3.py"):
    _p = os.path.join(HERE, _part)
    if os.path.exists(_p):
        exec(open(_p, encoding="utf-8").read())

save(OUT2, rows2)
print(f"wrote {len(rows2)} -> {OUT2}")
