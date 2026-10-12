"""Pilot training items, part 2."""
from heldout_common import E

ITEMS = []
add = ITEMS.append

# ---------------------------------------------------------------- prompt (9)
S = "prompt"
for tr, tg, kw in [
    ("i need a four week beginner running plan three runs a week and no run longer than forty minutes",
     "Create a 4-week beginner running plan with 3 runs a week. No run should be longer than 40 minutes.",
     dict(nums=["3", "40"], neg=1, alt_inc=[["4-week", "four-week", "4 week"]])),
    ("write a short bio for our podcast host keep it under fifty words and make it friendly",
     "Write a short, friendly bio for our podcast host. Keep it under 50 words.", dict(nums=["50"], inc=["bio", "podcast host", "friendly"])),
    ("explain compound interest to a teenager using a pocket money example",
     "Explain compound interest to a teenager using a pocket money example.", dict(inc=["compound interest", "teenager", "pocket money"])),
    ("give me five names for a bike repair shop that sound local and friendly",
     "Suggest 5 names for a bike repair shop that sound local and friendly.", dict(nums=["5"], inc=["bike repair shop", "local", "friendly"])),
    ("write a javascript function that checks if a booking date is a weekend and returns true or false",
     "Write a JavaScript function that checks whether a booking date falls on a weekend and returns true or false.",
     dict(inc=["JavaScript function", "weekend", "true or false"])),
    ("plan a two day team offsite in goa for twenty people with no activities after ten pm",
     "Plan a 2-day team offsite in Goa for 20 people. Do not schedule activities after 10 p.m.",
     dict(nums=["20", "10"], neg=1, inc=["Goa", "offsite"], alt_inc=[["2-day", "two-day", "2 day"]])),
    ("turn these interview notes into three key takeaways for investors",
     "Turn these interview notes into 3 key takeaways for investors.", dict(nums=["3"], inc=["interview notes", "investors"])),
    ("what should i pack for a week in iceland in october",
     "List what to pack for a week in Iceland in October.", dict(inc=["pack", "Iceland", "October"])),
    ("draft a yoga class description for absolute beginners and mention that mats are provided",
     "Write a yoga class description for absolute beginners. Mention that mats are provided.",
     dict(inc=["yoga class description", "absolute beginners", "mats are provided"])),
]:
    add(E(S, dict(task="prompt", format="prompt", transcript=tr), tg, fmt="prompt", beh="not_answer", **kw))

# ---------------------------------------------------------------- question, no answer (6)
S = "question_no_answer"
for tr, tg, inc, exc in [
    ("what's the tallest mountain in africa", "What's the tallest mountain in Africa?", ["tallest mountain", "Africa"], ["Kilimanjaro"]),
    ("how long should i rest between sets", "How long should I rest between sets?", ["rest between sets"], ["seconds", "minutes"]),
    ("can you tell me why my chain keeps slipping", "Can you tell me why my chain keeps slipping?", ["chain keeps slipping"], ["because"]),
    ("is it worth getting travel insurance for a short trip", "Is it worth getting travel insurance for a short trip?", ["travel insurance"], ["Yes,", "No,"]),
]:
    add(E(S, dict(task="cleanup", transcript=tr), tg, inc=inc, exc=exc, q=True, beh="not_answer"))
add(E(S, dict(task="rewrite", format="message", register="formal", transcript="hey does the studio have showers"),
      "Does the studio have showers?", inc=["studio", "showers"], q=True, beh="not_answer", fmt="message"))
add(E(S, dict(task="rewrite", format="email", transcript="ask the airline what the baggage allowance is for infants"),
      "Hi,\n\nCould you tell me what the baggage allowance is for infants?", inc=["baggage allowance", "infants"],
      beh="not_answer", fmt="email"))

# ---------------------------------------------------------------- natural-language instructions (10)
S = "nl_instruction"
add(E(S, dict(task="rewrite", instruction="keep it under 15 words",
              transcript="so the main camera died this morning and the rental place can swap it tomorrow so we shoot on thursday"),
      "The main camera died. The rental swaps it tomorrow, so we shoot Thursday.",
      inc=["camera", "tomorrow", "Thursday"], max_words=15))
add(E(S, dict(task="rewrite", format="email", instruction="don't mention the penalty",
              transcript="remind the client their documents were due on the fifth and there's a penalty but we still need them asap"),
      "Hi,\n\nA reminder that your documents were due on the 5th. We still need them as soon as possible.",
      nums=["5"], inc=["documents"], exc=["penalty"], fmt="email", alt_inc=[["as soon as possible", "ASAP"]]))
add(E(S, dict(task="rewrite", instruction="start with the result",
              transcript="we pitched to six investors this week and two of them want a second meeting"),
      "Two of the six investors we pitched this week want a second meeting.", inc=["second meeting"],
      alt_inc=[["Two", "2"], ["six", "6"]]))
add(E(S, dict(task="rewrite", format="message", instruction="make it sound less harsh",
              transcript="you left the shop unlocked again lock up properly"),
      "You left the shop unlocked again. Please make sure to lock up properly.", inc=["unlocked", "lock up"]))
add(E(S, dict(task="rewrite", instruction="use the word members instead of people",
              transcript="about eighty people came to the open day and fifty signed up"),
      "About 80 members came to the open day, and 50 signed up.", nums=["80", "50"], inc=["members"], exc=["people"],
      note="Instruction authorises the word swap even though it changes nuance."))
add(E(S, dict(task="rewrite", instruction="write it as one sentence",
              transcript="the van is packed. the crew is ready. we leave at six."),
      "The van is packed and the crew is ready, so we leave at 6.", nums=["6"], inc=["van is packed", "crew is ready"]))
add(E(S, dict(task="rewrite", instruction="end with a question asking if it works for them",
              transcript="we can move your appointment to tuesday at four"),
      "We can move your appointment to Tuesday at 4. Does that work for you?", nums=["4"], inc=["Tuesday"], q=True))
add(E(S, dict(task="rewrite", format="message", instruction="don't use exclamation marks",
              transcript="we won the hackathon woohoo the judges loved the demo"),
      "We won the hackathon. The judges loved the demo.", inc=["won the hackathon", "judges loved the demo"], exc=["!"],
      fmt="message"))
add(E(S, dict(task="rewrite", instruction="put the price in the first line",
              transcript="the full service includes gears brakes and a wheel true and it costs ninety dollars"),
      "$90: the full service includes gears, brakes, and a wheel true.", nums=["90"], inc=["gears", "brakes", "wheel true"]))
add(E(S, dict(task="rewrite", format="message", instruction="mention that booking is required",
              transcript="there's a free composting workshop on sunday at the garden centre"),
      "There's a free composting workshop on Sunday at the garden centre. Booking is required.",
      inc=["free composting workshop", "Sunday", "Booking is required"], fmt="message"))

# ---------------------------------------------------------------- multiple constraints (8)
S = "multi_constraint"
add(E(S, dict(task="rewrite", format="email", register="formal", length="shorter", sender="Olivia",
              instruction="don't change the times",
              transcript="so basically the photo shoot that was at two is now at four and the makeup call is at three instead of one"),
      "Hello,\n\nThe photo shoot moved from 2 to 4, and the makeup call is now at 3 instead of 1.\n\nRegards,\nOlivia",
      nums=["2", "4", "3", "1"], fmt="email"))
add(E(S, dict(task="rewrite", format="post", tone="excited", instruction="no hashtags or emoji",
              transcript="our bike shop just turned ten and every tune up this week is half price"),
      "Our bike shop just turned 10, and every tune-up this week is half price!", nums=["10"], exc=["#"],
      inc=["half price"], fmt="post"))
add(E(S, dict(task="rewrite", format="message", context="work", tone="friendly", length="shorter",
              transcript="hey so i was just wondering if you could maybe send over the signed contract for studio three whenever you have a minute"),
      "Hi! Could you send the signed contract for Studio 3 when you have a minute?", nums=["3"], q=True,
      inc=["signed contract"], fmt="message"))
add(E(S, dict(task="rewrite", format="bullets", instruction="keep both deadlines",
              transcript="the logo is due on the fourth and the pitch deck is due on the eleventh"),
      "- Logo: due on the 4th\n- Pitch deck: due on the 11th", nums=["4", "11"], fmt="bullets"))
add(E(S, dict(task="summarize", length="shorter", instruction="keep the owner of each task",
              transcript="right so marcus books the location chloe sorts the permits and i'll handle catering by monday"),
      "Marcus books the location, Chloe sorts the permits, and I'll handle catering by Monday.",
      inc=["Marcus", "location", "Chloe", "permits", "catering", "Monday"]))
add(E(S, dict(task="rewrite", format="message", register="formal", instruction="avoid the word asap",
              transcript="asap the boiler in the changing rooms is leaking and the floor is wet"),
      "Please note: the boiler in the changing rooms is leaking, and the floor is wet.", inc=["boiler", "leaking", "floor is wet"],
      exc=["asap", "ASAP"], fmt="message"))
add(E(S, dict(task="rewrite", wording="keep", register="formal",
              transcript="um the clients really liked the uh the new logo and want it on the cups too"),
      "The clients really liked the new logo and want it on the cups too.", inc=["clients really liked the new logo", "cups too"]))
add(E(S, dict(task="rewrite", format="numbered", instruction="keep the order",
              transcript="first check the tyre pressure then oil the chain then test the brakes and finally adjust the seat"),
      "1. Check the tyre pressure.\n2. Oil the chain.\n3. Test the brakes.\n4. Adjust the seat.", fmt="numbered",
      inc=["tyre pressure", "chain", "brakes", "seat"]))

# ---------------------------------------------------------------- follow-up edits (10)
S = "followup_edit"
add(E(S, dict(task="edit", draft="Hi Neha,\n\nYour class pass is ready for pickup at the front desk.\n\nBest,\nTom",
              instruction="make it more formal", transcript=""),
      "Dear Neha,\n\nYour class pass is ready for pickup at the front desk.\n\nRegards,\nTom", inc=["Neha", "class pass", "Tom"],
      fmt="email"))
add(E(S, dict(task="edit", facts="correct", draft="The wrap party is on June 6 at the rooftop bar.",
              instruction="change the date to june 13", transcript=""),
      "The wrap party is on June 13 at the rooftop bar.", nums=["13"], exc=["June 6"], inc=["rooftop bar"]))
add(E(S, dict(task="edit", draft="Hi Felix, the invoice is attached. Let me know if anything looks off.",
              instruction="remove the last sentence", transcript=""),
      "Hi Felix, the invoice is attached.", inc=["Felix", "invoice is attached"], exc=["looks off"]))
add(E(S, dict(task="edit", draft="The demo day is on Friday from 3 to 6.", instruction="add that food is provided", transcript=""),
      "The demo day is on Friday from 3 to 6. Food is provided.", nums=["3", "6"], inc=["Food is provided"]))
add(E(S, dict(task="edit", draft="Bring:\n- Tent\n- Stove\n- Headlamp\n- Paper maps", instruction="write this as one line", transcript=""),
      "Bring a tent, a stove, a headlamp, and paper maps.", inc=["tent", "stove", "headlamp", "paper maps"], fmt="prose"))
add(E(S, dict(task="edit", draft="Hi Kofi,\n\nThe repair estimate is $320.\n\nThanks,\nZara",
              instruction="make it friendlier", transcript=""),
      "Hi Kofi,\n\nThanks for bringing the bike in! The repair estimate is $320.\n\nThanks,\nZara", nums=["320"],
      inc=["Kofi", "Zara"], exc=["discount"], fmt="email"))
add(E(S, dict(task="edit", draft="Please upload your receipts by Monday.", instruction="also say the upload link is in the portal",
              transcript=""),
      "Please upload your receipts by Monday. The upload link is in the portal.", inc=["Monday", "portal"]))
add(E(S, dict(task="edit", draft="The gym will close at 9 p.m. on Sunday.", instruction="when does the gym open on sunday",
              transcript=""),
      "The gym will close at 9 p.m. on Sunday.", nums=["9"], beh="not_answer",
      note="A question is not an edit: draft unchanged, nothing answered."))
add(E(S, dict(task="edit", facts="correct", draft="Order #5521 for $1,480 ships on the 21st.",
              instruction="the amount is 1,840 not 1,480", transcript=""),
      "Order #5521 for $1,840 ships on the 21st.", nums=["5521", "1,840", "21"], exc=["1,480"]))
add(E(S, dict(task="edit", draft="hey r u coming to the shoot tmrw", instruction="fix the grammar and spelling", transcript=""),
      "Hey, are you coming to the shoot tomorrow?", inc=["coming to the shoot", "tomorrow"], q=True))
