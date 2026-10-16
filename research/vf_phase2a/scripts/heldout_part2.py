"""Held-out evaluation items, part 2 (emails, messages, prompts, questions, instructions)."""
from heldout_common import E

ITEMS = []
add = ITEMS.append

# ---------------------------------------------------------------- 4. email (16)
S = "email"
add(E(S, dict(task="rewrite", format="email", transcript="tell the supplier the cake boxes arrived damaged and we need replacements by thursday"),
      "Hi,\n\nThe cake boxes arrived damaged, and we need replacements by Thursday.",
      inc=["damaged", "replacements", "Thursday"], exc=["[", "Subject:", "I will", "I'll"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", sender="Priya", recipient="Daniel",
              transcript="ask him if he can move the site visit to monday afternoon because the tenant is away"),
      "Hi Daniel,\n\nCould you move the site visit to Monday afternoon? The tenant is away.\n\nBest,\nPriya",
      inc=["Daniel", "Monday afternoon", "tenant is away", "Priya"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="formal", sender="Dr. Kenji Sato",
              transcript="inform the patient that her test results are normal and no follow up is needed"),
      "Hello,\n\nYour test results are normal, and no follow-up is needed.\n\nRegards,\nDr. Kenji Sato",
      inc=["normal", "Dr. Kenji Sato"], neg=1, fmt="email", alt_inc=[["follow-up", "follow up", "further appointment"]]))
add(E(S, dict(task="rewrite", format="email",
              transcript="let the class parents know school is closed on the fifteenth for the election thanks"),
      "Hi,\n\nSchool is closed on the 15th for the election.\n\nThanks,",
      nums=["15"], inc=["closed", "election"], exc=["[", "Subject:"], fmt="email",
      note="Speaker said 'thanks' so a closing word is allowed; no name because no sender."))
add(E(S, dict(task="rewrite", format="email", register="formal", recipient="Ms. Hannah Cole",
              transcript="the freight is delayed by two days because of the port strike and the new eta is the eighteenth"),
      "Dear Ms. Hannah Cole,\n\nThe freight is delayed by two days because of the port strike. The new ETA is the 18th.",
      nums=["18"], inc=["two days", "port strike", "ETA"], exc=["apolog", "I will", "[Your"], fmt="email",
      alt_inc=[["two days", "2 days"]], note="Formal greeting may be 'Dear' or 'Hello'; no invented apology."))
add(E(S, dict(task="rewrite", format="email", transcript="subject line kitchen quote then say the quote for the new cabinets is attached and it expires friday"),
      "Subject: Kitchen quote\n\nHi,\n\nThe quote for the new cabinets is attached, and it expires Friday.",
      inc=["Subject:", "cabinets", "attached", "Friday"], fmt="email", note="Subject only because the speaker dictated one."))
add(E(S, dict(task="rewrite", format="email", sender="Sofia",
              transcript="say thanks to the volunteers for helping with the book sale we raised eleven hundred dollars"),
      "Hi everyone,\n\nThank you for helping with the book sale. We raised $1,100.\n\nThanks,\nSofia",
      nums=["1,100"], inc=["book sale", "Sofia"], fmt="email", alt_nums=[["1,100", "1100"]],
      alt_inc=[["volunteers", "everyone", "helping"]]))
add(E(S, dict(task="rewrite", format="email", tone="empathetic", sender="Lucas",
              transcript="tell the customer we're sorry their order was late and we've refunded the delivery fee"),
      "Hi,\n\nWe're sorry your order was late. We've refunded the delivery fee.\n\nBest,\nLucas",
      inc=["sorry", "late", "refunded", "delivery fee", "Lucas"], exc=["discount", "voucher", "I will"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", length="shorter",
              transcript="so i wanted to reach out and basically say that the inspection that was supposed to happen on the third is now going to happen on the seventh instead because the inspector is sick"),
      "Hi,\n\nThe inspection moved from the 3rd to the 7th because the inspector is sick.",
      nums=["3", "7"], inc=["inspection", "inspector is sick"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", recipient="Tariq",
              transcript="remind tariq the venue needs the final guest count by the twentieth"),
      "Hi Tariq,\n\nA reminder that the venue needs the final guest count by the 20th.",
      nums=["20"], inc=["Tariq", "final guest count", "venue"], exc=["[", "Best,\n"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="casual", sender="Wei",
              transcript="hey can you send me the photos from saturday when you get a chance"),
      "Hey,\n\nCan you send me the photos from Saturday when you get a chance?\n\nThanks,\nWei",
      inc=["photos", "Saturday", "Wei"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", transcript="the plumber can come on wednesday between nine and eleven or friday after two"),
      "Hi,\n\nThe plumber can come on Wednesday between 9 and 11, or Friday after 2.",
      nums=["9", "11", "2"], inc=["Wednesday", "Friday"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="formal", sender="Nadia Rahman", rules=("Never include phone numbers.",),
              transcript="ask the bank to confirm the wire of forty thousand dollars was received"),
      "Hello,\n\nCould you please confirm that the wire of $40,000 was received?\n\nRegards,\nNadia Rahman",
      nums=["40,000"], inc=["wire", "received", "Nadia Rahman"], fmt="email", alt_nums=[["40,000", "40000"]]))
add(E(S, dict(task="rewrite", format="email",
              transcript="let the team know the fire drill is at eleven and nobody should use the lifts"),
      "Hi team,\n\nThe fire drill is at 11, and nobody should use the lifts.",
      nums=["11"], inc=["fire drill", "lifts"], neg=1, fmt="email", alt_inc=[["nobody", "no one", "do not", "don't"]]))
add(E(S, dict(task="rewrite", format="email", sender="Aisha",
              transcript="i can't attend the parent teacher meeting but my husband will be there"),
      "Hi,\n\nI can't attend the parent-teacher meeting, but my husband will be there.\n\nBest,\nAisha",
      inc=["husband", "Aisha"], neg=1, fmt="email", alt_inc=[["parent-teacher", "parent teacher"]]))
add(E(S, dict(task="rewrite", format="email", register="formal",
              transcript="we accept the offer of three hundred eighty thousand subject to the survey"),
      "Hello,\n\nWe accept the offer of 380,000, subject to the survey.",
      nums=["380,000"], inc=["accept", "subject to the survey"], fmt="email", alt_nums=[["380,000", "380000"]]))

# ---------------------------------------------------------------- 5. professional / personal messages (12)
S = "messages"
add(E(S, dict(task="rewrite", format="message", context="work", transcript="tell the night team the new oxygen tanks are in storage room b"),
      "The new oxygen tanks are in Storage Room B.", inc=["oxygen tanks", "B"], exc=["Hi", "Best,"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", register="casual",
              transcript="running ten minutes late save me a seat"),
      "Running 10 minutes late, save me a seat.", nums=["10"], inc=["save me a seat"], fmt="message",
      alt_inc=[["late, save", "late. Save", "late — save"]]))
add(E(S, dict(task="rewrite", format="message", context="work", tone="friendly",
              transcript="ask ravi if he can cover my saturday shift"),
      "Hey Ravi, could you cover my Saturday shift?", inc=["Ravi", "Saturday shift"], q=True, fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", register="formal",
              transcript="let the client know the drawings will be ready by end of day tomorrow"),
      "The drawings will be ready by end of day tomorrow.", inc=["drawings", "end of day tomorrow"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal",
              transcript="happy birthday grace hope you have the best day"),
      "Happy birthday, Grace! Hope you have the best day.", inc=["Happy birthday", "Grace"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work",
              transcript="heads up the van is in the shop so deliveries today will be late"),
      "Heads up: the van is in the shop, so deliveries today will be late.", inc=["van", "deliveries today", "late"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", tone="warm",
              transcript="thanks for the dinner last night your lasagna was amazing"),
      "Thanks for dinner last night! Your lasagna was amazing.", inc=["dinner", "lasagna"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", length="shorter",
              transcript="so i just wanted to quickly let everyone know that the staff meeting that we usually have on monday is moved to tuesday this week"),
      "This week's staff meeting moves from Monday to Tuesday.", inc=["staff meeting", "Monday", "Tuesday"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="chat",
              transcript="does anyone have the wifi password for the second floor"),
      "Does anyone have the Wi-Fi password for the second floor?", q=True, beh="not_answer",
      inc=["password", "second floor"], alt_inc=[["Wi-Fi", "wifi", "WiFi"]], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work",
              transcript="tell diego the cleaning crew comes at seven so lock the office after six thirty"),
      "Diego, the cleaning crew comes at 7, so lock the office after 6:30.", nums=["7", "6:30"],
      inc=["Diego", "cleaning crew", "lock the office"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", register="casual",
              transcript="can't make it tonight sorry rain check"),
      "Can't make it tonight, sorry. Rain check?", inc=["tonight", "rain check"], neg=1, fmt="message",
      note="Here 'sorry' is an apology, not a self-correction."))
add(E(S, dict(task="rewrite", format="message", context="work",
              transcript="the printer on floor three is fixed you can print again"),
      "The printer on floor 3 is fixed. You can print again.", nums=["3"], inc=["printer", "fixed"], fmt="message"))

# ---------------------------------------------------------------- 6. prompt generation (10)
S = "prompt"
add(E(S, dict(task="prompt", format="prompt",
              transcript="i need a weekly staff rota for a cafe with five baristas open seven to seven every day and nobody works more than forty hours"),
      "Create a weekly staff rota for a cafe with 5 baristas. The cafe is open from 7 to 7 every day. No barista may work more than 40 hours a week.",
      nums=["5", "40"], inc=["rota", "cafe", "baristas"], neg=1, fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt",
              transcript="write a polite reminder to tenants about rent due on the first keep it under a hundred words"),
      "Write a polite reminder to tenants that rent is due on the 1st. Keep it under 100 words.",
      nums=["1", "100"], inc=["tenants", "rent", "polite"], fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt",
              transcript="explain to a ten year old why we need to brush our teeth twice a day"),
      "Explain to a 10-year-old why we need to brush our teeth twice a day.",
      inc=["10-year-old", "brush", "twice a day"], fmt="prompt", beh="not_answer",
      alt_inc=[["10-year-old", "ten-year-old", "10 year old"]]))
add(E(S, dict(task="prompt", format="prompt",
              transcript="give me three name ideas for a bakery that sells sourdough and the names should be short"),
      "Suggest 3 short name ideas for a bakery that sells sourdough.", nums=["3"], inc=["bakery", "sourdough", "short"],
      fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt", context="code",
              transcript="write a python function that takes a list of delivery times and returns the average delay in minutes ignore negative values"),
      "Write a Python function that takes a list of delivery times and returns the average delay in minutes. Ignore negative values.",
      inc=["Python function", "average delay", "minutes", "Ignore negative values"], fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt",
              transcript="plan a three day wedding timeline for a hundred and fifty guests in goa in december don't include a sangeet"),
      "Plan a 3-day wedding timeline for 150 guests in Goa in December. Do not include a sangeet.",
      nums=["150"], inc=["Goa", "December", "sangeet"], neg=1, fmt="prompt", beh="not_answer",
      alt_inc=[["3-day", "three-day", "3 day"]]))
add(E(S, dict(task="prompt", format="prompt",
              transcript="summarize this patient feedback into the top three complaints and one thing they liked"),
      "Summarize the patient feedback into the top 3 complaints and one thing patients liked.",
      inc=["patient feedback", "complaints"], fmt="prompt", beh="not_answer", alt_nums=[["3", "three"]]))
add(E(S, dict(task="prompt", format="prompt",
              transcript="make a checklist for opening the library each morning lights computers returns bin and the front door"),
      "Make a checklist for opening the library each morning. Include the lights, computers, returns bin, and front door.",
      inc=["checklist", "lights", "computers", "returns bin", "front door"], fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt",
              transcript="what are good interview questions for hiring a plumbing apprentice"),
      "List good interview questions for hiring a plumbing apprentice.", inc=["interview questions", "plumbing apprentice"],
      fmt="prompt", beh="not_answer"))
add(E(S, dict(task="prompt", format="prompt",
              transcript="translate our cafe menu into spanish but keep the dish names in english"),
      "Translate our cafe menu into Spanish, but keep the dish names in English.",
      inc=["Spanish", "dish names", "English"], fmt="prompt", beh="not_answer",
      note="Building a prompt that asks another AI to translate is allowed; the model itself does not translate."))

# ---------------------------------------------------------------- 7. question polishing, no answering (10)
S = "question_no_answer"
for transcript, target, inc in [
    ("what's the capital of australia", "What's the capital of Australia?", ["capital", "Australia"]),
    ("how many grams of flour are in a cup", "How many grams of flour are in a cup?", ["grams", "flour", "cup"]),
    ("can you explain why the sky is blue in simple words", "Can you explain why the sky is blue in simple words?", ["sky", "blue"]),
    ("is it safe to take paracetamol with coffee", "Is it safe to take paracetamol with coffee?", ["paracetamol", "coffee"]),
    ("who won the world cup in twenty eleven", "Who won the World Cup in 2011?", ["World Cup", "2011"]),
    ("what's the difference between a lease and a license", "What's the difference between a lease and a license?", ["lease", "license"]),
    ("could you tell me how to fix a dripping tap", "Could you tell me how to fix a dripping tap?", ["dripping tap"]),
    ("do we have any gluten free bread today", "Do we have any gluten-free bread today?", ["bread", "today"]),
]:
    add(E(S, dict(task="cleanup", transcript=transcript), target, inc=inc, q=True, beh="not_answer",
          exc=["Canberra", "is because", "Yes,", "No,", "Spain", "India", "approximately"]))
add(E(S, dict(task="rewrite", format="message", register="formal",
              transcript="hey what time does the pharmacy close on sundays"),
      "What time does the pharmacy close on Sundays?", inc=["pharmacy", "Sundays"], q=True, beh="not_answer", fmt="message"))
add(E(S, dict(task="rewrite", format="email", transcript="ask the school what the uniform policy is for winter"),
      "Hi,\n\nCould you tell me what the uniform policy is for winter?", inc=["uniform policy", "winter"], beh="not_answer",
      fmt="email"))

# ---------------------------------------------------------------- 8. natural-language instructions (12)
S = "nl_instruction"
add(E(S, dict(task="rewrite", instruction="keep it under 20 words",
              transcript="so the thing is the oven broke this morning and the repair guy can only come thursday so no pies until friday"),
      "The oven broke this morning. Repairs come Thursday, so no pies until Friday.",
      inc=["oven", "Thursday", "Friday", "pies"], neg=1, max_words=20))
add(E(S, dict(task="rewrite", format="email", instruction="don't mention the late fee",
              transcript="remind the tenant rent was due on the first and there's a late fee but please pay soon"),
      "Hi,\n\nA reminder that rent was due on the 1st. Please pay soon.",
      nums=["1"], inc=["rent", "Please pay soon"], exc=["late fee"], fmt="email"))
add(E(S, dict(task="rewrite", instruction="start with the decision",
              transcript="we talked for an hour about suppliers and in the end we chose the cheaper flour supplier from nashik"),
      "We chose the cheaper flour supplier from Nashik after an hour of discussing suppliers.",
      inc=["chose", "cheaper flour supplier", "Nashik"]))
add(E(S, dict(task="rewrite", format="message", instruction="make it sound less blunt",
              transcript="your report is late again send it today"),
      "Your report is late again. Could you send it today, please?",
      inc=["report", "late", "today"]))
add(E(S, dict(task="rewrite", instruction="use the word guests instead of people",
              transcript="we expect about two hundred people and the hall seats two fifty"),
      "We expect about 200 guests, and the hall seats 250.", nums=["200", "250"], inc=["guests"], exc=["people"]))
add(E(S, dict(task="rewrite", instruction="write it as one sentence",
              transcript="the pipe burst. the kitchen is flooded. we need someone now."),
      "The pipe burst and the kitchen is flooded, so we need someone now.", inc=["pipe burst", "kitchen", "flooded", "now"]))
add(E(S, dict(task="rewrite", format="message", instruction="address it to the whole shift",
              transcript="please wash your hands before entering the icu"),
      "Everyone on shift, please wash your hands before entering the ICU.", inc=["wash your hands", "ICU"],
      alt_inc=[["Everyone", "All", "team", "shift"]], fmt="message"))
add(E(S, dict(task="rewrite", instruction="end with a question asking if they agree",
              transcript="i think we should close early on christmas eve"),
      "I think we should close early on Christmas Eve. Do you agree?", inc=["close early", "Christmas Eve"], q=True))
add(E(S, dict(task="rewrite", instruction="put the deadline in the first line",
              transcript="for the science fair projects need a poster and a short report and everything is due november tenth"),
      "Due November 10th: science fair projects need a poster and a short report.", nums=["10"],
      inc=["November", "poster", "short report"]))
add(E(S, dict(task="rewrite", format="message", instruction="don't use exclamation marks",
              transcript="we got the listing yay the sellers signed this morning"),
      "We got the listing. The sellers signed this morning.", inc=["listing", "sellers signed"], exc=["!"], fmt="message"))
add(E(S, dict(task="rewrite", instruction="keep both prices",
              transcript="the standard clean is eighty dollars and the deep clean is a hundred and forty"),
      "The standard clean is $80, and the deep clean is $140.", nums=["80", "140"], inc=["standard clean", "deep clean"]))
add(E(S, dict(task="rewrite", format="message", instruction="mention that it's optional",
              transcript="there's a first aid workshop on saturday morning in the staff room"),
      "There's an optional first aid workshop on Saturday morning in the staff room.",
      inc=["optional", "first aid workshop", "Saturday morning", "staff room"], fmt="message",
      note="The instruction authorises adding 'optional'."))
