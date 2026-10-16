"""Held-out evaluation items, part 1. Hand-written Oct 12, 2026 from VF-1 rev 1.2.

Scenario pools reserved for evaluation (never used in training data):
names  Priya Rahul Meera Arjun Sofia Daniel Fatima Kenji Lucas Aisha Grace Tariq Ines Wei Nadia Ravi Hannah Diego
domains dental clinic, bakery, freight/logistics, school/PTA, real estate, hospital shifts, cafe, wedding planning,
        plumbing, public library
"""
from heldout_common import E

ITEMS = []
add = ITEMS.append

# ---------------------------------------------------------------- 1. ordinary cleanup (20)
S = "cleanup_ordinary"
add(E(S, dict(task="cleanup", transcript="um so the clinic opens at nine tomorrow instead of eight"),
      "The clinic opens at 9 tomorrow instead of 8.", inc=["tomorrow", "instead of"], nums=["9", "8"]))
add(E(S, dict(task="cleanup", transcript="i think we should uh order more flour before the weekend rush"),
      "I think we should order more flour before the weekend rush.", inc=["flour", "weekend rush"], exc=["uh"]))
add(E(S, dict(task="cleanup", transcript="the truck left the warehouse at like six thirty and should reach pune by noon"),
      "The truck left the warehouse at like 6:30 and should reach Pune by noon.", inc=["Pune", "noon"], nums=["6:30"],
      note="Here 'like' means approximately: keeping it or writing 'about' are both acceptable"))
add(E(S, dict(task="cleanup", transcript="can you remind the parents that the field trip forms are due friday"),
      "Can you remind the parents that the field trip forms are due Friday?", inc=["field trip forms", "Friday"], q=True,
      beh="not_answer"))
add(E(S, dict(task="cleanup", transcript="so basically the buyers loved the flat but they want the kitchen repainted first"),
      "The buyers loved the flat, but they want the kitchen repainted first.", inc=["kitchen repainted", "buyers"]))
add(E(S, dict(task="cleanup", transcript="my shift got moved to the night slot so i wont make the team lunch"),
      "My shift got moved to the night slot, so I won't make the team lunch.", inc=["night slot", "team lunch"], neg=1))
add(E(S, dict(task="cleanup", transcript="we're out of oat milk again and the espresso machine is making that weird noise"),
      "We're out of oat milk again, and the espresso machine is making that weird noise.", inc=["oat milk", "espresso machine"]))
add(E(S, dict(task="cleanup", transcript="the florist said the peonies might not be in season in march"),
      "The florist said the peonies might not be in season in March.", inc=["peonies", "March"], neg=1))
add(E(S, dict(task="cleanup", transcript="the leak is under the bathroom sink not the kitchen one"),
      "The leak is under the bathroom sink, not the kitchen one.", inc=["bathroom sink", "kitchen"], neg=1))
add(E(S, dict(task="cleanup", transcript="please return the books to the front desk before closing time"),
      "Please return the books to the front desk before closing time.", inc=["front desk", "closing time"]))
add(E(S, dict(task="cleanup", transcript="i was i was going to say that the x ray machine needs servicing"),
      "I was going to say that the X-ray machine needs servicing.", inc=["X-ray", "servicing"]))
add(E(S, dict(task="cleanup", transcript="we sold forty two croissants by ten am which is a record"),
      "We sold 42 croissants by 10 a.m., which is a record.", nums=["42", "10"], inc=["croissants", "record"]))
add(E(S, dict(task="cleanup", transcript="the driver needs the gate code it's four four seven one"),
      "The driver needs the gate code. It's 4471.", nums=["4471"], inc=["gate code"]))
add(E(S, dict(task="cleanup", transcript="honestly the open house went better than i expected"),
      "Honestly, the open house went better than I expected.", inc=["open house", "better than"]))
add(E(S, dict(task="cleanup", transcript="you know the new rota is uh kind of confusing for everyone"),
      "The new rota is kind of confusing for everyone.", inc=["rota", "confusing"], exc=[" uh "]))
add(E(S, dict(task="cleanup", register="casual", transcript="hey just checking if the cake tasting is still on for saturday"),
      "Hey, just checking if the cake tasting is still on for Saturday.", inc=["cake tasting", "Saturday"]))
add(E(S, dict(task="cleanup", register="formal", transcript="the patient in room four has been waiting for over an hour"),
      "The patient in Room 4 has been waiting for over an hour.", nums=["4"], inc=["waiting", "over an hour"]))
add(E(S, dict(task="cleanup", transcript="we need a plumber who can come before the tenants move in on the fifth"),
      "We need a plumber who can come before the tenants move in on the 5th.", nums=["5"], inc=["plumber", "tenants"]))
add(E(S, dict(task="cleanup", transcript="the library will stay open till eight on weekdays starting next month"),
      "The library will stay open till 8 on weekdays starting next month.", nums=["8"], inc=["weekdays", "next month"]))
add(E(S, dict(task="cleanup", locale="en-gb", transcript="the colour of the new menu boards is a bit too dark"),
      "The colour of the new menu boards is a bit too dark.", inc=["colour", "menu boards"]))

# ---------------------------------------------------------------- 2. names, dates, numbers, amounts, negation (18)
S = "facts_numbers_negation"
add(E(S, dict(task="cleanup", transcript="the deposit is two lakh fifty thousand and it's not refundable", locale="en-in"),
      "The deposit is ₹2,50,000 and it's not refundable.", nums=["2,50,000"], neg=1, inc=["deposit", "refundable"],
      alt_nums=[["2,50,000", "250,000", "2.5 lakh"]]))
add(E(S, dict(task="cleanup", transcript="meera's appointment is on the twenty third of november at three fifteen"),
      "Meera's appointment is on the 23rd of November at 3:15.", nums=["23", "3:15"], inc=["Meera", "November"]))
add(E(S, dict(task="cleanup", transcript="do not give the patient ibuprofen she's allergic"),
      "Do not give the patient ibuprofen. She's allergic.", neg=1, inc=["ibuprofen", "allergic"]))
add(E(S, dict(task="cleanup", transcript="the invoice total is eighteen hundred and forty dollars including tax"),
      "The invoice total is $1,840 including tax.", nums=["1,840"], inc=["including tax"], alt_nums=[["1,840", "1840"]]))
add(E(S, dict(task="cleanup", transcript="arjun and sofia will cover the morning shift but daniel won't"),
      "Arjun and Sofia will cover the morning shift, but Daniel won't.", inc=["Arjun", "Sofia", "Daniel", "morning shift"], neg=1))
add(E(S, dict(task="cleanup", transcript="the shipment weighs three point five tonnes so we can't use the small truck"),
      "The shipment weighs 3.5 tonnes, so we can't use the small truck.", nums=["3.5"], neg=1, inc=["tonnes", "small truck"]))
add(E(S, dict(task="rewrite", format="message", context="work",
              transcript="tell fatima the rent goes up by six percent from january unless she signs the two year lease"),
      "Fatima, the rent goes up by 6% from January unless you sign the two-year lease.", nums=["6"],
      inc=["Fatima", "January", "unless", "two-year lease"], alt_inc=[["two-year", "2-year", "two year"]]))
add(E(S, dict(task="cleanup", transcript="kenji's flight lands at eleven forty pm on the ninth"),
      "Kenji's flight lands at 11:40 p.m. on the 9th.", nums=["11:40", "9"], inc=["Kenji"]))
add(E(S, dict(task="cleanup", transcript="we never charge for the first consultation"),
      "We never charge for the first consultation.", neg=1, inc=["never", "first consultation"]))
add(E(S, dict(task="cleanup", transcript="the room fits sixty guests seated or a hundred standing"),
      "The room fits 60 guests seated or 100 standing.", nums=["60", "100"], inc=["seated", "standing"]))
add(E(S, dict(task="rewrite", format="email", register="formal", recipient="Mr. Lucas Ortega", sender="Grace",
              transcript="let him know the quote is twelve thousand four hundred dollars and it's valid for thirty days"),
      "Hello Mr. Lucas Ortega,\n\nThe quote is $12,400, and it is valid for 30 days.\n\nRegards,\nGrace",
      nums=["12,400", "30"], inc=["valid", "Grace"], fmt="email", alt_nums=[["12,400", "12400"]]))
add(E(S, dict(task="cleanup", transcript="the password reset link expires in fifteen minutes not fifteen hours"),
      "The password reset link expires in 15 minutes, not 15 hours.", nums=["15", "15"], neg=1, inc=["minutes", "hours"]))
add(E(S, dict(task="cleanup", transcript="aisha's son is allergic to peanuts but not tree nuts"),
      "Aisha's son is allergic to peanuts but not tree nuts.", neg=1, inc=["Aisha", "peanuts", "tree nuts"]))
add(E(S, dict(task="cleanup", transcript="order number b seven seven four two dash k"),
      "Order number B7742-K.", inc=["B7742-K"]))
add(E(S, dict(task="cleanup", transcript="the meeting is at four pm india time which is ten thirty am in london"),
      "The meeting is at 4 p.m. India time, which is 10:30 a.m. in London.", nums=["4", "10:30"], inc=["India", "London"]))
add(E(S, dict(task="cleanup", transcript="tariq can't sign the contract until legal approves it"),
      "Tariq can't sign the contract until legal approves it.", neg=1, inc=["Tariq", "until legal approves"]))
add(E(S, dict(task="cleanup", transcript="email ines at ines dot moreau at gmail dot com"),
      "Email Ines at ines.moreau@gmail.com.", inc=["ines.moreau@gmail.com"]))
add(E(S, dict(task="cleanup", transcript="the discount applies only if they pay within seven days"),
      "The discount applies only if they pay within 7 days.", nums=["7"], inc=["only if", "within"]))

# ---------------------------------------------------------------- 3. self-corrections vs alternatives (16)
S = "corrections_vs_alternatives"
add(E(S, dict(task="cleanup", transcript="send the x rays to doctor rahul no wait doctor meera"),
      "Send the X-rays to Dr. Meera.", inc=["Meera", "X-rays"], exc=["Rahul"]))
add(E(S, dict(task="cleanup", transcript="we need thirty sorry forty loaves for the event"),
      "We need 40 loaves for the event.", nums=["40"], exc=["30"]))
add(E(S, dict(task="cleanup", transcript="the delivery is on tuesday i mean wednesday morning"),
      "The delivery is on Wednesday morning.", inc=["Wednesday"], exc=["Tuesday"]))
add(E(S, dict(task="cleanup", transcript="you can pay by card or by bank transfer"),
      "You can pay by card or by bank transfer.", inc=["card", "bank transfer", " or "]))
add(E(S, dict(task="cleanup", transcript="the membership is ninety dollars a month or nine hundred dollars a year"),
      "The membership is $90 a month or $900 a year.", nums=["90", "900"], inc=["a month", "a year", " or "]))
add(E(S, dict(task="cleanup", transcript="book the venue for june fourteenth or june twenty first whichever is cheaper"),
      "Book the venue for June 14th or June 21st, whichever is cheaper.", nums=["14", "21"], inc=["whichever is cheaper"]))
add(E(S, dict(task="cleanup", transcript="the call is at three no actually make that four"),
      "The call is at 4.", nums=["4"], exc=["3"]))
add(E(S, dict(task="cleanup", transcript="invite hannah and wei scratch that just hannah"),
      "Invite Hannah.", inc=["Hannah"], exc=["Wei"]))
add(E(S, dict(task="cleanup", transcript="the budget is five or six thousand we haven't decided"),
      "The budget is 5,000 or 6,000. We haven't decided.", nums=["5,000", "6,000"], neg=1,
      alt_nums=[["5,000", "5000", "five"], ["6,000", "6000"]]))
add(E(S, dict(task="cleanup", transcript="put nadia on the front desk sorry i mean the phones"),
      "Put Nadia on the phones.", inc=["Nadia", "phones"], exc=["front desk"]))
add(E(S, dict(task="cleanup", transcript="i'm sorry we ran out of the chocolate cake"),
      "I'm sorry, we ran out of the chocolate cake.", inc=["sorry", "chocolate cake"]))
add(E(S, dict(task="cleanup", transcript="the tenant wants either a new fridge or a rent reduction"),
      "The tenant wants either a new fridge or a rent reduction.", inc=["new fridge", "rent reduction", "either"]))
add(E(S, dict(task="cleanup", transcript="pick up is at gate two no gate three"),
      "Pickup is at Gate 3.", nums=["3"], exc=["2"], alt_inc=[["Pickup", "Pick-up", "Pick up"]]))
add(E(S, dict(task="cleanup", transcript="we can do the tasting at noon or two pm"),
      "We can do the tasting at noon or 2 p.m.", nums=["2"], inc=["noon", " or "]))
add(E(S, dict(task="cleanup", transcript="charge ravi eighty dollars no wait eighty five for the repair"),
      "Charge Ravi $85 for the repair.", nums=["85"], exc=["80"], inc=["Ravi"]))
add(E(S, dict(task="cleanup", transcript="the class is for kids aged eight to twelve or their parents"),
      "The class is for kids aged 8 to 12 or their parents.", nums=["8", "12"], inc=["or their parents"]))
