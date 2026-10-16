"""Pilot training items, part 1. Hand-written Oct 12, 2026 from VF-1 rev 1.2.

Scenario pools reserved for TRAINING (disjoint from the held-out pools):
names  Neha Vikram Olivia Marcus Zara Tom Ananya Hiro Elena Omar Chloe Sam Leila Ben Isha Kofi Maya Felix
domains gym, film shoot, accounting firm, bike shop, hackathon, garden centre, yoga studio, startup fundraising,
        podcast, travel agency
"""
from heldout_common import E

ITEMS = []
add = ITEMS.append

# ---------------------------------------------------------------- cleanup (18)
S = "cleanup_ordinary"
for tr, tg, kw in [
    ("um the spin class starts at six fifteen not six", "The spin class starts at 6:15, not 6.", dict(nums=["6:15", "6"], neg=1)),
    ("so we wrapped the shoot early because the light was gone", "We wrapped the shoot early because the light was gone.", dict(inc=["wrapped the shoot"])),
    ("the quarterly vat return is due on the seventh", "The quarterly VAT return is due on the 7th.", dict(nums=["7"], inc=["VAT return"])),
    ("uh the rear brake pads are worn out and need replacing", "The rear brake pads are worn out and need replacing.", dict(inc=["rear brake pads"])),
    ("i think i think our demo crashed because the wifi dropped", "I think our demo crashed because the Wi-Fi dropped.", dict(alt_inc=[["Wi-Fi", "wifi", "WiFi"]])),
    ("the tomato seedlings need watering twice a day in this heat", "The tomato seedlings need watering twice a day in this heat.", dict(inc=["twice a day"])),
    ("please bring your own mat to the sunday session", "Please bring your own mat to the Sunday session.", dict(inc=["own mat", "Sunday"])),
    ("we closed the seed round at one point two million", "We closed the seed round at 1.2 million.", dict(nums=["1.2"], inc=["million", "seed round"])),
    ("the episode runs about forty minutes without ads", "The episode runs about 40 minutes without ads.", dict(nums=["40"], neg=1)),
    ("your flight to lisbon leaves at seven ten am from terminal two", "Your flight to Lisbon leaves at 7:10 a.m. from Terminal 2.", dict(nums=["7:10", "2"], inc=["Lisbon"])),
    ("you know the lockers on the left side don't lock properly", "The lockers on the left side don't lock properly.", dict(neg=1, inc=["lockers"])),
    ("the director wants one more take of the kitchen scene", "The director wants one more take of the kitchen scene.", dict(inc=["one more take", "kitchen scene"])),
    ("basically the client hasn't sent the receipts for march yet", "The client hasn't sent the receipts for March yet.", dict(neg=1, inc=["receipts", "March"])),
    ("we have eleven bikes in stock and three on order", "We have 11 bikes in stock and 3 on order.", dict(nums=["11", "3"])),
    ("judging starts at noon and each team gets five minutes", "Judging starts at noon, and each team gets 5 minutes.", dict(nums=["5"], inc=["noon"])),
    ("hmm the lavender plants are sold out until next week", "The lavender plants are sold out until next week.", dict(inc=["sold out", "next week"])),
    ("the retreat costs four hundred and fifty euros per person", "The retreat costs €450 per person.", dict(nums=["450"], inc=["per person"])),
    ("did you get the visa appointment for thursday", "Did you get the visa appointment for Thursday?", dict(q=True, beh="not_answer", inc=["visa appointment"])),
]:
    add(E(S, dict(task="cleanup", transcript=tr), tg, **kw))

# ---------------------------------------------------------------- facts, numbers, negation (12)
S = "facts_numbers_negation"
add(E(S, dict(task="cleanup", locale="en-in", transcript="the sponsorship is three lakh rupees and it does not include travel"),
      "The sponsorship is ₹3,00,000 and it does not include travel.", nums=["3,00,000"], neg=1,
      alt_nums=[["3,00,000", "300,000", "3 lakh"]]))
add(E(S, dict(task="cleanup", transcript="neha's membership expires on the thirty first of january"),
      "Neha's membership expires on the 31st of January.", nums=["31"], inc=["Neha", "January"]))
add(E(S, dict(task="cleanup", transcript="never lift more than twenty kilos without a spotter"),
      "Never lift more than 20 kilos without a spotter.", nums=["20"], neg=2))
add(E(S, dict(task="cleanup", transcript="the invoice for vikram is two thousand three hundred and seventy five pounds"),
      "The invoice for Vikram is £2,375.", nums=["2,375"], inc=["Vikram"], alt_nums=[["2,375", "2375"]]))
add(E(S, dict(task="cleanup", transcript="olivia and marcus are on camera b but zara isn't"),
      "Olivia and Marcus are on Camera B, but Zara isn't.", inc=["Olivia", "Marcus", "Zara", "Camera B"], neg=1))
add(E(S, dict(task="cleanup", transcript="the frame is fifty six centimetres and weighs eight point two kilos"),
      "The frame is 56 centimetres and weighs 8.2 kilos.", nums=["56", "8.2"]))
add(E(S, dict(task="cleanup", transcript="hiro lands at five forty five am on the second of may"),
      "Hiro lands at 5:45 a.m. on the 2nd of May.", nums=["5:45", "2"], inc=["Hiro", "May"]))
add(E(S, dict(task="cleanup", transcript="the hackathon is free for students but not for professionals"),
      "The hackathon is free for students but not for professionals.", neg=1, inc=["students", "professionals"]))
add(E(S, dict(task="cleanup", transcript="the booking reference is k nine two two x"),
      "The booking reference is K922X.", inc=["K922X"]))
add(E(S, dict(task="cleanup", transcript="email elena at elena dot ruiz at outlook dot com"),
      "Email Elena at elena.ruiz@outlook.com.", inc=["elena.ruiz@outlook.com"]))
add(E(S, dict(task="cleanup", transcript="the refund only applies if they cancel forty eight hours before"),
      "The refund only applies if they cancel 48 hours before.", nums=["48"], inc=["only applies if"]))
add(E(S, dict(task="rewrite", format="message", context="work",
              transcript="tell omar the bike service costs sixty five dollars unless he wants new tyres"),
      "Omar, the bike service costs $65 unless you want new tyres.", nums=["65"], inc=["Omar", "unless", "tyres"],
      fmt="message"))

# ---------------------------------------------------------------- corrections vs alternatives (12)
S = "corrections_vs_alternatives"
add(E(S, dict(task="cleanup", transcript="book the studio for chloe no wait for sam"),
      "Book the studio for Sam.", inc=["Sam", "studio"], exc=["Chloe"]))
add(E(S, dict(task="cleanup", transcript="we need twelve sorry fifteen extras for the crowd scene"),
      "We need 15 extras for the crowd scene.", nums=["15"], exc=["12"]))
add(E(S, dict(task="cleanup", transcript="the class is on thursday i mean friday evening"),
      "The class is on Friday evening.", inc=["Friday"], exc=["Thursday"]))
add(E(S, dict(task="cleanup", transcript="you can rent a road bike or a mountain bike"),
      "You can rent a road bike or a mountain bike.", inc=["road bike", "mountain bike", " or "]))
add(E(S, dict(task="cleanup", transcript="the package is two thousand for one week or thirty five hundred for two weeks"),
      "The package is 2,000 for one week or 3,500 for two weeks.", nums=["2,000", "3,500"],
      alt_nums=[["2,000", "2000"], ["3,500", "3500"]]))
add(E(S, dict(task="cleanup", transcript="send the invoice to leila scratch that send it to ben"),
      "Send the invoice to Ben.", inc=["Ben", "invoice"], exc=["Leila"]))
add(E(S, dict(task="cleanup", transcript="the edit session is at five or rather half past five"),
      "The edit session is at half past five.", inc=["half past five", "edit session"],
      alt_inc=[["half past five", "5:30"]]))
add(E(S, dict(task="cleanup", transcript="we can film at the beach or at the pier depending on the tide"),
      "We can film at the beach or at the pier, depending on the tide.", inc=["beach", "pier", "depending on the tide"]))
add(E(S, dict(task="cleanup", transcript="i'm so sorry the bike won't be ready today"),
      "I'm so sorry, the bike won't be ready today.", inc=["sorry", "won't be ready today"], neg=1))
add(E(S, dict(task="cleanup", transcript="put isha in room one no room two"),
      "Put Isha in Room 2.", nums=["2"], exc=["1"], inc=["Isha"]))
add(E(S, dict(task="cleanup", transcript="the fee is either ten percent or a flat fifty dollars"),
      "The fee is either 10% or a flat $50.", nums=["10", "50"], inc=["either", "flat"]))
add(E(S, dict(task="cleanup", transcript="charge kofi forty no wait forty five for the tune up"),
      "Charge Kofi 45 for the tune-up.", nums=["45"], exc=["40"], inc=["Kofi"],
      alt_inc=[["tune-up", "tune up"]], note="No currency was spoken, so no symbol is added."))

# ---------------------------------------------------------------- email (14)
S = "email"
add(E(S, dict(task="rewrite", format="email", transcript="tell the venue we need the hall from eight am to six pm on the ninth"),
      "Hi,\n\nWe need the hall from 8 a.m. to 6 p.m. on the 9th.", nums=["8", "6", "9"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", sender="Maya", recipient="Felix",
              transcript="ask felix if he can send the edited episode by wednesday"),
      "Hi Felix,\n\nCould you send the edited episode by Wednesday?\n\nThanks,\nMaya", inc=["Felix", "edited episode", "Wednesday", "Maya"],
      fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="formal", sender="Vikram Shah",
              transcript="let the client know their tax return was filed today and no payment is due"),
      "Hello,\n\nYour tax return was filed today, and no payment is due.\n\nRegards,\nVikram Shah", neg=1,
      inc=["tax return", "filed today", "Vikram Shah"], fmt="email"))
add(E(S, dict(task="rewrite", format="email",
              transcript="let the members know the pool is closed for cleaning on monday thanks"),
      "Hi,\n\nThe pool is closed for cleaning on Monday.\n\nThanks,", inc=["pool", "cleaning", "Monday"], exc=["["], fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="formal", recipient="Mr. Tom Hale",
              transcript="the shipment of saddles is delayed by a week because of a supplier problem"),
      "Dear Mr. Tom Hale,\n\nThe shipment of saddles is delayed by a week because of a supplier problem.",
      inc=["saddles", "a week", "supplier problem"], exc=["apolog", "I will"], fmt="email"))
add(E(S, dict(task="rewrite", format="email",
              transcript="subject line itinerary update then say your hotel in kyoto changed to the riverside inn same dates"),
      "Subject: Itinerary update\n\nHi,\n\nYour hotel in Kyoto changed to the Riverside Inn. The dates are the same.",
      inc=["Subject:", "Kyoto", "Riverside Inn", "same"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", sender="Ananya",
              transcript="thank the mentors for judging we had thirty two teams this year"),
      "Hi everyone,\n\nThank you for judging. We had 32 teams this year.\n\nThanks,\nAnanya", nums=["32"],
      inc=["judging", "Ananya"], fmt="email", alt_inc=[["mentors", "everyone"]]))
add(E(S, dict(task="rewrite", format="email", tone="empathetic", sender="Zara",
              transcript="tell the customer we're sorry their bike arrived scratched and we'll replace the frame"),
      "Hi,\n\nWe're sorry your bike arrived scratched. We'll replace the frame.\n\nBest,\nZara",
      inc=["sorry", "scratched", "replace the frame", "Zara"], exc=["discount", "refund"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", length="shorter",
              transcript="i just wanted to let you know that basically the audit meeting that we had planned for the tenth has been pushed to the seventeenth because the partner is travelling"),
      "Hi,\n\nThe audit meeting moved from the 10th to the 17th because the partner is travelling.", nums=["10", "17"],
      inc=["audit meeting", "partner is travelling"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", recipient="Leila",
              transcript="remind leila the class schedule for november needs her sign off by friday"),
      "Hi Leila,\n\nA reminder that the November class schedule needs your sign-off by Friday.",
      inc=["Leila", "November", "Friday"], fmt="email", alt_inc=[["sign-off", "sign off", "approval"]]))
add(E(S, dict(task="rewrite", format="email", register="casual", sender="Ben",
              transcript="hey can you share the rough cut link when it's uploaded"),
      "Hey,\n\nCan you share the rough cut link when it's uploaded?\n\nThanks,\nBen", inc=["rough cut link", "Ben"], fmt="email"))
add(E(S, dict(task="rewrite", format="email",
              transcript="the courier can collect on tuesday between ten and twelve or thursday after three"),
      "Hi,\n\nThe courier can collect on Tuesday between 10 and 12, or Thursday after 3.", nums=["10", "12", "3"], fmt="email"))
add(E(S, dict(task="rewrite", format="email", register="formal", sender="Elena Ruiz",
              transcript="ask the investor to confirm the transfer of two hundred fifty thousand dollars"),
      "Hello,\n\nCould you please confirm the transfer of $250,000?\n\nRegards,\nElena Ruiz", nums=["250,000"],
      alt_nums=[["250,000", "250000"]], fmt="email"))
add(E(S, dict(task="rewrite", format="email", sender="Hiro",
              transcript="i won't be at the trade show but omar will cover our booth"),
      "Hi,\n\nI won't be at the trade show, but Omar will cover our booth.\n\nBest,\nHiro", neg=1,
      inc=["trade show", "Omar", "booth", "Hiro"], fmt="email"))

# ---------------------------------------------------------------- messages (10)
S = "messages"
add(E(S, dict(task="rewrite", format="message", context="work", transcript="tell the crew call time tomorrow is five am at the north gate"),
      "Call time tomorrow is 5 a.m. at the north gate.", nums=["5"], inc=["north gate"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", register="casual", transcript="stuck in traffic start without me"),
      "Stuck in traffic, start without me.", inc=["traffic", "start without me"], neg=1, fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", tone="friendly", transcript="ask maya if she can open the studio on saturday"),
      "Hey Maya, could you open the studio on Saturday?", inc=["Maya", "studio", "Saturday"], q=True, fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", register="formal", transcript="let the client know the books are reconciled up to september"),
      "The books are reconciled up to September.", inc=["reconciled", "September"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", transcript="congrats on the new job tom so proud of you"),
      "Congrats on the new job, Tom! So proud of you.", inc=["new job", "Tom", "proud"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", transcript="heads up the generator is out so no power on set until two"),
      "Heads up: the generator is out, so no power on set until 2.", nums=["2"], neg=1, fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", length="shorter",
              transcript="so i just wanted to let everyone know that the team standup that normally happens at nine is going to be at ten today"),
      "Today's standup moves from 9 to 10.", nums=["9", "10"], inc=["standup"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="chat", transcript="has anyone seen the spare hdmi cable"),
      "Has anyone seen the spare HDMI cable?", q=True, beh="not_answer", inc=["HDMI cable"], fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="personal", register="casual", transcript="cant do lunch sorry next week"),
      "Can't do lunch, sorry. Next week?", inc=["lunch", "Next week"], neg=1, fmt="message"))
add(E(S, dict(task="rewrite", format="message", context="work", transcript="tell isha the projector in studio two is fixed"),
      "Isha, the projector in Studio 2 is fixed.", nums=["2"], inc=["Isha", "projector"], fmt="message"))
