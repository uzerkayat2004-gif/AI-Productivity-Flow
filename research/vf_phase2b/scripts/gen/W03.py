"""W03 stage 1 + stage 2 generator: bucket cleanup_facts, locale en-in (Indian English, Hinglish, a few Devanagari words).

Domains: kirana shop, IT services firm in Bengaluru, cricket academy, CA office.
Re-running reproduces research/vf_phase2b/data/batches/W03_s1.jsonl and W03_s2.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W03"
STAGE = "s1"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_{STAGE}.jsonl"))
BUCKET = "cleanup_facts"

CO = "cleanup_ordinary"
FN = "facts_numbers_negation"
CA = "corrections_vs_alternatives"

ROWS = []


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def R(slice_, request, target, assertions, note, pos="structured", cx=None):
    i = len(ROWS) + 1
    req = {"locale": "en-in"}
    req.update(request)
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, assertions, f"w03-sc-{i:03d}",
                    author=WID, note=note, meta=meta))


# 1
R(CO, {"task": "cleanup", "header_style": "full",
       "transcript": "um harsh bhai the atta stock is over so order ten bags from the distributor jaldi"},
  "Harsh bhai, the atta stock is over, so order 10 bags from the distributor jaldi.",
  {"numbers": ["10"], "must_include": ["Harsh bhai", "atta", "jaldi", "distributor"]},
  "facts: order 10 bags of atta from the distributor; Hinglish 'bhai' and 'jaldi' kept as spoken")

# 2
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the client wants to prepone the demo to thursday eleven am not friday"},
  "The client wants to prepone the demo to Thursday 11 a.m., not Friday.",
  {"numbers": ["11"], "must_include": ["prepone", "Thursday", "Friday"], "min_negations": 1},
  "facts: demo moved earlier to Thursday 11 a.m.; negation 'not Friday' kept; Indian English 'prepone' kept")

# 3 (Devanagari)
R(CO, {"task": "cleanup",
       "transcript": "pooja please check the gst return for march uh the client said कल तक data bhej denge so we can file by the twentieth"},
  "Pooja, please check the GST return for March. The client said कल तक data bhej denge, so we can file by the 20th.",
  {"numbers": ["20"], "must_include": ["Pooja", "GST return", "March", "कल तक", "bhej denge"]},
  "facts: GST return for March; client will send data by tomorrow (कल तक, Devanagari kept); filing by the 20th")

# 4
R(FN, {"task": "cleanup",
       "transcript": "so basically this month the sales were around four lakh twenty thousand rupees uh and the udhaar outstanding is thirty eight thousand five hundred mostly from the same five six customers you know lakshmi aunty alone owes nine thousand so i think we should stop giving credit to anyone above five thousand till they clear it otherwise next month will be tight new line also the fridge repair guy said he will come on saturday but he didn't confirm the time"},
  "This month the sales were around ₹4,20,000, and the udhaar outstanding is 38,500, mostly from the same 5-6 customers. Lakshmi aunty alone owes 9,000, so I think we should stop giving credit to anyone above 5,000 till they clear it, otherwise next month will be tight.\n\nAlso, the fridge repair guy said he will come on Saturday, but he didn't confirm the time.",
  {"numbers": ["4,20,000", "38,500", "9,000", "5,000"], "must_include": ["udhaar", "Lakshmi aunty", "I think", "till they clear it", "Saturday"], "min_negations": 1},
  "facts: sales around ₹4,20,000 (rupees spoken only here, so ₹ only here); udhaar 38,500 from 5-6 customers; Lakshmi aunty owes 9,000; hedge 'I think' on stopping credit above 5,000 until cleared; repair guy Saturday, time NOT confirmed; 'new line' -> paragraph")

# 5
R(CA, {"task": "cleanup",
       "transcript": "tell the under fourteen batch that practice is at six thirty no wait seven tomorrow"},
  "Tell the under-14 batch that practice is at 7 tomorrow.",
  {"numbers": ["14", "7"], "must_not_include": ["6:30", "six thirty"], "must_include": ["under-14", "tomorrow"]},
  "facts: self-correction applied, practice at 7 (6:30 corrected away); under-14 batch; tomorrow")

# 6
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "for the migration we can either go with two developers for six weeks or three developers for four weeks uh siddharth will decide by monday which one"},
  "For the migration, we can either go with two developers for 6 weeks or three developers for 4 weeks. Siddharth will decide by Monday which one.",
  {"numbers": ["6", "4"], "must_include": ["two developers", "three developers", "Siddharth", "Monday"]},
  "facts: genuine alternative kept: 2 devs x 6 weeks OR 3 devs x 4 weeks; Siddharth decides by Monday")

# 7
R(CO, {"task": "cleanup", "header_style": "full",
       "transcript": "achha divya the invoice is ready just do the needful and revert back"},
  "Achha Divya, the invoice is ready. Just do the needful and revert back.",
  {"must_include": ["Achha", "Divya", "do the needful", "revert back"]},
  "facts: invoice ready; Indian English 'do the needful' and 'revert back' kept verbatim in cleanup")

# 8 rewrite message
R(FN, {"task": "rewrite", "format": "message", "context": "work",
       "transcript": "uh imran the vpn issue ticket INC-20431 is still open the vendor said patch will come by wednesday evening but no guarantee so keep the workaround running"},
  "Imran, the VPN issue ticket INC-20431 is still open. The vendor said the patch will come by Wednesday evening, but there's no guarantee, so keep the workaround running.",
  {"format": "message", "must_include": ["Imran", "INC-20431", "Wednesday evening", "workaround"], "numbers": ["20431"], "min_negations": 1},
  "facts: ticket INC-20431 still open; vendor's patch by Wednesday evening is NOT guaranteed (hedge kept, not turned into a promise); keep workaround running")

# 9 (Devanagari)
R(CO, {"task": "cleanup",
       "transcript": "gurpreet ji the sugar rate has gone up to forty six rupees per kilo so पुराना rate mat lagao from today"},
  "Gurpreet ji, the sugar rate has gone up to ₹46 per kilo, so पुराना rate mat lagao from today.",
  {"numbers": ["46"], "must_include": ["Gurpreet ji", "पुराना", "mat lagao", "from today"]},
  "facts: sugar now ₹46/kilo; Hindi prohibition 'पुराना rate mat lagao' (don't apply old rate) kept with Devanagari word; from today")

# 10
R(CA, {"task": "cleanup",
       "transcript": "okay so for the weekend tournament we have registered twelve teams sorry fourteen teams uh entry fee is two thousand five hundred per team and the ground booking is from eight am to five pm on both days saturday and sunday anita ma'am will handle the scorebook and umpires um we still need two more umpires because one guy dropped out so if anybody knows someone yaar please tell me by thursday also the trophies have not arrived yet the vendor said maybe friday"},
  "For the weekend tournament, we have registered 14 teams. Entry fee is 2,500 per team, and the ground booking is from 8 a.m. to 5 p.m. on both days, Saturday and Sunday. Anita ma'am will handle the scorebook and umpires. We still need two more umpires because one guy dropped out, so if anybody knows someone, yaar, please tell me by Thursday.\n\nAlso, the trophies have not arrived yet. The vendor said maybe Friday.",
  {"numbers": ["14", "2,500", "8", "5"], "must_not_include": ["12", "twelve"], "must_include": ["Anita ma'am", "two more umpires", "Thursday", "maybe Friday", "yaar"], "min_negations": 1},
  "facts: 14 teams (12 corrected away); fee 2,500 per team (no currency spoken); ground 8 a.m.-5 p.m. Sat and Sun; Anita handles scorebook/umpires; need two more umpires, tell by Thursday (conditional 'if anybody knows'); trophies NOT arrived, vendor hedged 'maybe Friday'")

# 11 question
R(CA, {"task": "cleanup",
       "transcript": "should we file the itr for imran sir before the thirty first or wait for form sixteen question mark"},
  "Should we file the ITR for Imran sir before the 31st or wait for Form 16?",
  {"numbers": ["31", "16"], "must_include": ["ITR", "Imran sir", "Form 16"], "behavior": "not_answer", "ends_with_question": True},
  "facts: question kept as question, not answered; both options kept (file before the 31st OR wait for Form 16)")

# 12
R(FN, {"task": "cleanup",
       "transcript": "the sla for p1 tickets is four hours not twenty four hours please update the runbook before the client audit on the fifth of november uh and also the escalation matrix still has old names pooja left last month so replace her with siddharth for l2 and keep imran as l3 the auditors will check whether every p1 in september was closed within sla so pull that report from servicenow and um don't edit the old tickets just export them as they are"},
  "The SLA for P1 tickets is 4 hours, not 24 hours. Please update the runbook before the client audit on the 5th of November. Also, the escalation matrix still has old names. Pooja left last month, so replace her with Siddharth for L2 and keep Imran as L3. The auditors will check whether every P1 in September was closed within SLA, so pull that report from ServiceNow, and don't edit the old tickets, just export them as they are.",
  {"numbers": ["4", "24", "5"], "must_include": ["SLA", "P1", "runbook", "November", "Siddharth for L2", "Imran as L3", "September", "ServiceNow", "export them as they are"], "min_negations": 2},
  "facts: P1 SLA is 4 hours, NOT 24; update runbook before audit on 5th of November (Indian date order kept); Pooja left, Siddharth replaces her at L2, Imran stays L3; pull September P1 SLA report from ServiceNow; do NOT edit old tickets, export as-is")

# 13 rewrite email formal
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Lakshmi", "recipient": "Siddharth",
       "transcript": "let siddharth know that his advance tax instalment of one lakh fifteen thousand rupees is due on fifteenth december and the challan has not been generated yet we need his PAN and the updated bank statement first"},
  "Dear Siddharth,\n\nYour advance tax instalment of ₹1,15,000 is due on 15th December. The challan has not been generated yet; we need your PAN and the updated bank statement first.\n\nRegards,\nLakshmi",
  {"format": "email", "numbers": ["1,15,000", "15"], "must_include": ["Siddharth", "advance tax", "challan", "PAN", "bank statement", "Lakshmi"], "min_negations": 1},
  "facts: advance tax ₹1,15,000 due 15th December; challan NOT generated yet; PAN and updated bank statement needed first; no added promises")

# 14
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "payment of eight hundred forty rupees came on upi but the name is not showing"},
  "Payment of ₹840 came on UPI, but the name is not showing.",
  {"numbers": ["840"], "must_include": ["UPI"], "min_negations": 1},
  "facts: ₹840 received on UPI; payer name NOT showing")

# 15
R(CA, {"task": "cleanup",
       "transcript": "pooja send the balance sheet to divya i mean to anita because divya is on leave till monday"},
  "Pooja, send the balance sheet to Anita, because Divya is on leave till Monday.",
  {"must_include": ["Pooja", "to Anita", "Divya is on leave", "Monday"], "must_not_include": ["to Divya"]},
  "facts: self-correction: recipient is Anita, not Divya; Divya on leave till Monday (kept as the reason)")

# 16 rewrite email with instruction
R(FN, {"task": "rewrite", "format": "email", "context": "work", "sender": "Divya",
       "instruction": "make it a proper email to the team, keep the dates exactly and the condition about sign-off, don't add anything new",
       "transcript": "hi team so quick update on the payroll module rollout for the client in whitefield uh the uat got delayed by three days because the test data from their hr team came late we are now targeting go live on the twenty second instead of the nineteenth um but only if the sign off comes by the eighteenth evening otherwise it will move to the next sprint also please note no deployments on friday because of the infra freeze and gurpreet will share the updated cutover plan by tomorrow noon thanks"},
  "Hi team,\n\nA quick update on the payroll module rollout for the client in Whitefield. UAT got delayed by 3 days because the test data from their HR team came late. We are now targeting go-live on the 22nd instead of the 19th, but only if the sign-off comes by the 18th evening; otherwise, it will move to the next sprint.\n\nAlso, please note there are no deployments on Friday because of the infra freeze. Gurpreet will share the updated cutover plan by tomorrow noon.\n\nThanks,\nDivya",
  {"format": "email", "numbers": ["3", "22", "19", "18"], "must_include": ["Whitefield", "UAT", "only if", "sign-off", "next sprint", "Friday", "Gurpreet", "tomorrow noon", "Divya"], "min_negations": 1},
  "facts: UAT delayed 3 days (late HR test data); go-live now 22nd instead of 19th ONLY IF sign-off by 18th evening, otherwise next sprint; NO deployments Friday (infra freeze); Gurpreet shares cutover plan by tomorrow noon",
  pos="after", cx=4)

# 17
R(CO, {"task": "cleanup", "header_style": "full",
       "transcript": "siddharth bowled really well today yaar seven overs only eighteen runs"},
  "Siddharth bowled really well today, yaar, 7 overs, only 18 runs.",
  {"numbers": ["7", "18"], "must_include": ["Siddharth", "yaar"]},
  "facts: Siddharth bowled 7 overs for only 18 runs today")

# 18
R(CO, {"task": "cleanup",
       "transcript": "arre the build is failing again on the staging server theek hai i will check after lunch but pehle the hotfix for ticket INC-20877 has to go"},
  "Arre, the build is failing again on the staging server. Theek hai, I will check after lunch, but pehle the hotfix for ticket INC-20877 has to go.",
  {"numbers": ["20877"], "must_include": ["Arre", "staging server", "Theek hai", "pehle", "INC-20877", "after lunch"]},
  "facts: build failing on staging; speaker will check after lunch; hotfix for INC-20877 must go first ('pehle' kept)")

# 19 (Devanagari)
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "anita ji the audit report is ready लेकिन signature abhi baaki hai so don't send it to the client today"},
  "Anita ji, the audit report is ready, लेकिन signature abhi baaki hai, so don't send it to the client today.",
  {"must_include": ["Anita ji", "audit report", "लेकिन", "abhi baaki hai"], "min_negations": 1},
  "facts: audit report ready but signature still pending; do NOT send to the client today; Devanagari 'लेकिन' kept")

# 20
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "order fifteen or twenty packets of the five hundred gram maggi depending on the scheme"},
  "Order 15 or 20 packets of the 500 gram Maggi, depending on the scheme.",
  {"numbers": ["15", "20", "500"], "must_include": ["Maggi", "depending on the scheme"]},
  "facts: genuine alternative 15 OR 20 packets (both kept); 500 gram; conditional on the scheme")

# 21 rewrite message with instruction
R(CO, {"task": "rewrite", "format": "message", "register": "casual",
       "instruction": "short WhatsApp message for the distributor, keep the Hindi words as they are",
       "transcript": "bhaiya the last delivery had three cartons of surf excel damaged so please take them back and kal ki delivery mein replace kar dena the bill amount was six thousand four hundred twenty rupees"},
  "Bhaiya, the last delivery had 3 cartons of Surf Excel damaged, so please take them back and kal ki delivery mein replace kar dena. The bill amount was ₹6,420.",
  {"format": "message", "numbers": ["3", "6,420"], "must_include": ["Bhaiya", "Surf Excel", "kal ki delivery mein replace kar dena"]},
  "facts: 3 damaged cartons of Surf Excel to be taken back and replaced in tomorrow's delivery; bill ₹6,420; Hinglish kept per instruction",
  pos="before", cx=3)

# 22 dictated list
R(FN, {"task": "cleanup",
       "transcript": "notes for tomorrow first item call harsh about the gst notice reply it has to go before the twenty fifth next bullet collect the form sixteen from pooja and lakshmi next bullet the tds return for q2 is pending because the challan numbers don't match fix that first and next bullet do not file anything for the trust client until the audit is done"},
  "Notes for tomorrow:\n- Call Harsh about the GST notice reply. It has to go before the 25th.\n- Collect the Form 16 from Pooja and Lakshmi.\n- The TDS return for Q2 is pending because the challan numbers don't match. Fix that first.\n- Do not file anything for the trust client until the audit is done.",
  {"format": "bullets", "numbers": ["25", "16"], "must_include": ["Harsh", "GST notice", "Form 16", "Pooja", "Lakshmi", "TDS", "Q2", "until the audit is done"], "min_negations": 2},
  "facts: dictated list (first item / next bullet) kept as bullets; GST notice reply before the 25th; Form 16 from Pooja and Lakshmi; Q2 TDS pending, challan numbers don't match; do NOT file for trust client until audit done")

# 23
R(FN, {"task": "cleanup",
       "transcript": "server downtime is from two to four am ist on sunday not saturday so please inform the client spoc and pause the monitoring alerts during that window"},
  "Server downtime is from 2 to 4 a.m. IST on Sunday, not Saturday, so please inform the client SPOC and pause the monitoring alerts during that window.",
  {"numbers": ["2", "4"], "must_include": ["IST", "Sunday", "Saturday"], "min_negations": 1},
  "facts: downtime 2-4 a.m. IST on Sunday, NOT Saturday; inform client SPOC; pause monitoring alerts during the window")

# 24
R(FN, {"task": "cleanup",
       "transcript": "the annual coaching fee is thirty six thousand rupees but for siblings we give ten percent off and the kit is extra it is not included uh the kit costs around four thousand two hundred and parents can buy it from us or outside but the jersey has to be ours because of the logo and um admissions for the summer camp open on the first of march only for kids above eight years"},
  "The annual coaching fee is ₹36,000, but for siblings we give 10% off, and the kit is extra. It is not included. The kit costs around 4,200, and parents can buy it from us or outside, but the jersey has to be ours because of the logo. Admissions for the summer camp open on the 1st of March, only for kids above 8 years.",
  {"numbers": ["36,000", "10", "4,200", "1", "8"], "must_include": ["siblings", "kit is extra", "from us or outside", "jersey has to be ours", "March", "only for kids above"], "min_negations": 1},
  "facts: annual fee ₹36,000; 10% sibling discount; kit extra and NOT included, costs around 4,200 (no currency spoken), buy from academy OR outside; jersey must be the academy's; summer camp admissions open 1st of March, only for kids above 8 years")

# 25 rewrite email, English-only instruction
R(CO, {"task": "rewrite", "format": "email",
       "instruction": "turn this into a polite email to Imran in English only, keep the timeline exactly",
       "transcript": "tell imran bhai his gst registration ho gaya hai the GSTIN will come on mail in two three days and uske baad we will start filing from next month"},
  "Hi Imran,\n\nYour GST registration is done. The GSTIN will come by email in two to three days, and after that we will start filing from next month.",
  {"format": "email", "must_include": ["Imran", "GST registration", "GSTIN", "two to three days", "next month"], "must_not_include": ["ho gaya", "uske baad"]},
  "facts: GST registration done; GSTIN by email in 2-3 days; filing starts next month after that. English-only wording authorised by instruction ('ho gaya hai' -> 'is done', 'uske baad' -> 'after that'); meaning unchanged",
  pos="after", cx=3)

# 26
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "the selection trial is on the twelfth sorry fourteenth at the main ground"},
  "The selection trial is on the 14th at the main ground.",
  {"numbers": ["14"], "must_not_include": ["12"], "must_include": ["selection trial", "main ground"]},
  "facts: self-correction applied: trial on the 14th (12th corrected away)")

# 27
R(FN, {"task": "cleanup",
       "transcript": "the gst on biscuits is eighteen percent and on loose atta it's zero so don't charge gst on the atta bills"},
  "The GST on biscuits is 18%, and on loose atta it's zero, so don't charge GST on the atta bills.",
  {"numbers": ["18"], "must_include": ["biscuits", "loose atta", "zero", "atta bills"], "min_negations": 1},
  "facts: GST 18% on biscuits, zero on loose atta; do NOT charge GST on atta bills")

# 28
R(CO, {"task": "cleanup",
       "transcript": "divya can you share the jira link for the sprint retro question mark"},
  "Divya, can you share the Jira link for the sprint retro?",
  {"must_include": ["Divya", "Jira", "sprint retro"], "behavior": "not_answer", "ends_with_question": True},
  "facts: request phrased as a question, kept as a question; spoken 'question mark' applied")

# 29 rewrite message friendly, long
R(FN, {"task": "rewrite", "format": "message", "tone": "friendly",
       "instruction": "clear message for the parents group, keep all timings and the helmet rule exactly",
       "transcript": "um from next week the morning batch timing is changing from six to six thirty am because of the dark mornings the evening batch stays the same four thirty to six thirty uh fees for november should be paid by the tenth through upi to the academy id which is the same as before and please make sure kids carry their own water bottles we are not providing bottled water anymore and helmets are compulsory for nets no helmet no batting thank you"},
  "From next week, the morning batch timing is changing from 6 to 6:30 a.m. because of the dark mornings. The evening batch stays the same, 4:30 to 6:30.\n\nFees for November should be paid by the 10th through UPI to the academy ID, which is the same as before.\n\nPlease make sure the kids carry their own water bottles, as we are not providing bottled water anymore. Helmets are compulsory for nets: no helmet, no batting.\n\nThank you.",
  {"format": "message", "numbers": ["6", "6:30", "4:30", "10"], "must_include": ["morning batch", "evening batch", "November", "UPI", "water bottles", "Helmets are compulsory", "no helmet, no batting"], "min_negations": 3},
  "facts: morning batch moves from 6 to 6:30 a.m. from next week; evening batch unchanged 4:30-6:30; November fees by the 10th via UPI to same academy ID; kids bring own water, academy NOT providing bottled water; helmets compulsory, no helmet no batting; dictated 'thank you' kept",
  pos="before", cx=4)

# 30 (Devanagari)
R(CO, {"task": "cleanup",
       "transcript": "imran the delivery boy is छुट्टी pe today so home delivery band hai"},
  "Imran, the delivery boy is छुट्टी pe today, so home delivery band hai.",
  {"must_include": ["Imran", "छुट्टी pe", "home delivery band hai"]},
  "facts: delivery boy on leave today (छुट्टी kept in Devanagari); home delivery closed")

# 31 rewrite message confident
R(CA, {"task": "rewrite", "format": "message", "tone": "confident", "recipient": "Harsh",
       "instruction": "keep both payment options and the fact that it's undecided",
       "transcript": "the client can pay either eighteen lakh rupees upfront or two lakh rupees per month for ten months we haven't decided yet"},
  "Harsh, the client can pay either ₹18,00,000 upfront or ₹2,00,000 per month for 10 months. We haven't decided yet.",
  {"format": "message", "numbers": ["18,00,000", "2,00,000", "10"], "must_include": ["Harsh", "upfront", "per month"], "min_negations": 1},
  "facts: genuine alternative kept: ₹18,00,000 upfront OR ₹2,00,000/month for 10 months; still undecided (negation kept)",
  pos="after", cx=4)

# 32
R(FN, {"task": "cleanup", "header_style": "full",
       "transcript": "the penalty is two hundred rupees per day not per month"},
  "The penalty is ₹200 per day, not per month.",
  {"numbers": ["200"], "must_include": ["per day", "per month"], "min_negations": 1},
  "facts: penalty ₹200 per day, NOT per month")

# 33 long kirana
R(CO, {"task": "cleanup",
       "transcript": "achha pooja the new rack for the namkeen will come on thursday till then keep the packets in the godown and haan the price list board also needs updating uh the parle and haldiram rates changed last week so write the new ones clearly and um put the offer stickers only on the items which are actually on offer last time customers were fighting yaar over the wrong sticker"},
  "Achha Pooja, the new rack for the namkeen will come on Thursday. Till then keep the packets in the godown, and haan, the price list board also needs updating. The Parle and Haldiram rates changed last week, so write the new ones clearly and put the offer stickers only on the items which are actually on offer. Last time customers were fighting, yaar, over the wrong sticker.",
  {"must_include": ["Achha Pooja", "namkeen", "Thursday", "godown", "haan", "Parle", "Haldiram", "only on the items which are actually on offer"]},
  "facts: namkeen rack arrives Thursday; packets in godown till then; update price board (Parle and Haldiram rates changed last week); offer stickers ONLY on items actually on offer")

# 34
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "schedule the call with the bengaluru team at three pm make that four pm ist because siddharth is travelling"},
  "Schedule the call with the Bengaluru team at 4 p.m. IST because Siddharth is travelling.",
  {"numbers": ["4"], "must_not_include": ["3"], "must_include": ["Bengaluru team", "IST", "Siddharth is travelling"]},
  "facts: self-correction: call at 4 p.m. IST (3 p.m. corrected away); reason Siddharth travelling. Cleanup keeps the request as dictated text, no action claimed")

# 35 long CA
R(FN, {"task": "cleanup",
       "transcript": "so the client meeting went okay the main thing is they want us to handle their books from april onwards uh for three entities the fee they offered is one lakh eighty thousand per year for all three which is honestly low yaar we were expecting at least two lakh fifty thousand i told them we will revert back by friday harsh please work out the hours estimate before that and don't share our internal rate card with them also they asked if we do payroll we don't but maybe we can tie up with someone"},
  "The client meeting went okay. The main thing is they want us to handle their books from April onwards for three entities. The fee they offered is 1,80,000 per year for all three, which is honestly low, yaar. We were expecting at least 2,50,000. I told them we will revert back by Friday. Harsh, please work out the hours estimate before that, and don't share our internal rate card with them.\n\nAlso, they asked if we do payroll. We don't, but maybe we can tie up with someone.",
  {"numbers": ["1,80,000", "2,50,000"], "must_include": ["April onwards", "three entities", "honestly low", "revert back by Friday", "Harsh", "internal rate card", "maybe"], "min_negations": 2},
  "facts: books from April for three entities; offered 1,80,000/yr for all three (no currency spoken); expected at least 2,50,000; will revert by Friday; Harsh does hours estimate before that; do NOT share rate card; they don't do payroll, 'maybe' tie-up (hedge kept)")

# 36 rewrite email with SKUs
R(FN, {"task": "rewrite", "format": "email",
       "instruction": "polite email to the supplier, keep the SKU codes and invoice number exactly, don't add any deadline",
       "transcript": "please send us twenty cartons of SKU AMB-0412 and ten cartons of SKU AMB-0415 the last invoice INV/2026/0388 still shows the old rate of fifty two rupees per unit so please correct that before dispatch"},
  "Hi,\n\nPlease send us 20 cartons of SKU AMB-0412 and 10 cartons of SKU AMB-0415.\n\nThe last invoice, INV/2026/0388, still shows the old rate of ₹52 per unit, so please correct that before dispatch.",
  {"format": "email", "numbers": ["20", "10", "52"], "must_include": ["AMB-0412", "AMB-0415", "INV/2026/0388", "before dispatch"]},
  "facts: 20 cartons AMB-0412 and 10 cartons AMB-0415; invoice INV/2026/0388 shows old rate ₹52/unit, correct before dispatch; no deadline or sign-off name added",
  pos="before", cx=3)

# 37
R(CO, {"task": "cleanup",
       "transcript": "gurpreet paaji the bowling machine is not working since kal"},
  "Gurpreet paaji, the bowling machine is not working since kal.",
  {"must_include": ["Gurpreet paaji", "bowling machine", "since kal"], "min_negations": 1},
  "facts: bowling machine NOT working since yesterday ('kal' kept as spoken)")

# 38
R(CA, {"task": "cleanup", "header_style": "full",
       "transcript": "imran sir called about his refund basically the refund of twelve thousand four hundred will come to the account ending four four seven one not the old hdfc one he closed that in july the department usually takes three sorry four to five weeks so tell him not to worry if it doesn't show by month end and if it bounces we will file a reissue request with the new ifsc code"},
  "Imran sir called about his refund. The refund of 12,400 will come to the account ending 4471, not the old HDFC one. He closed that in July. The department usually takes 4 to 5 weeks, so tell him not to worry if it doesn't show by month end, and if it bounces, we will file a reissue request with the new IFSC code.",
  {"numbers": ["12,400", "4471", "4", "5"], "must_not_include": ["3"], "must_include": ["Imran sir", "HDFC", "July", "month end", "if it bounces", "reissue request", "IFSC"], "min_negations": 3},
  "facts: refund 12,400 to account ending 4471 (digit sequence), NOT the old HDFC account (closed in July); self-correction: 4 to 5 weeks (3 corrected away); don't worry if not shown by month end; conditional reissue request with new IFSC if it bounces")

# 39
R(CA, {"task": "cleanup",
       "transcript": "keep the shop open till ten tonight or maybe ten thirty if the diwali rush continues"},
  "Keep the shop open till 10 tonight, or maybe 10:30 if the Diwali rush continues.",
  {"numbers": ["10", "10:30"], "must_include": ["tonight", "maybe", "Diwali rush"]},
  "facts: alternative kept: 10 tonight OR maybe 10:30 (hedge) only if the Diwali rush continues (condition)")

# 40 rewrite message with Devanagari
R(FN, {"task": "rewrite", "format": "message", "context": "work",
       "instruction": "a bit more polite, keep the mix of Hindi and English as is",
       "transcript": "lakshmi the laptop for the new joinee is ready but the vpn access is not done yet कृपया ask it to raise the request today"},
  "Lakshmi, the laptop for the new joinee is ready, but the VPN access is not done yet. कृपया ask IT to raise the request today.",
  {"format": "message", "must_include": ["Lakshmi", "new joinee", "VPN", "कृपया", "IT", "today"], "min_negations": 1},
  "facts: laptop ready; VPN access NOT done yet; ask IT to raise the request today; Devanagari 'कृपया' kept; ASR 'it' read as the IT team",
  pos="after", cx=3)

# 41
R(CO, {"task": "cleanup",
       "transcript": "milk delivery is at six am daily except on tuesdays when the dairy is closed so on monday keep some extra packets aside in the fridge for tuesday morning"},
  "Milk delivery is at 6 a.m. daily except on Tuesdays when the dairy is closed, so on Monday keep some extra packets aside in the fridge for Tuesday morning.",
  {"numbers": ["6"], "must_include": ["daily", "except on Tuesdays", "dairy is closed", "Monday", "Tuesday morning"]},
  "facts: milk at 6 a.m. daily, exception Tuesdays (dairy closed); keep extra packets aside on Monday for Tuesday morning")

# 42 (Devanagari)
R(CO, {"task": "cleanup", "header_style": "full",
       "transcript": "divya the jersey sizes are final twenty four small sixteen medium and eight large बाकी sizes ka order next week"},
  "Divya, the jersey sizes are final: 24 small, 16 medium and 8 large. बाकी sizes ka order next week.",
  {"numbers": ["24", "16", "8"], "must_include": ["Divya", "jersey sizes", "बाकी", "next week"]},
  "facts: final jersey sizes 24 small, 16 medium, 8 large; remaining sizes ordered next week (बाकी kept in Devanagari)")

# 43 rewrite email formal
R(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Anita", "header_style": "full",
       "transcript": "we would like to book the ground for the inter academy match on the ninth and tenth of january from seven am to one pm we will pay the deposit of fifteen thousand rupees by cheque and we do not need the floodlights"},
  "Hello,\n\nWe would like to book the ground for the inter-academy match on the 9th and 10th of January, from 7 a.m. to 1 p.m. We will pay the deposit of ₹15,000 by cheque, and we do not need the floodlights.\n\nRegards,\nAnita",
  {"format": "email", "numbers": ["9", "10", "7", "1", "15,000"], "must_include": ["inter-academy match", "January", "cheque", "floodlights", "Anita"], "min_negations": 1},
  "facts: ground booking 9th and 10th of January, 7 a.m.-1 p.m.; deposit ₹15,000 by cheque (speaker's own commitment); floodlights NOT needed")

# 44
R(CO, {"task": "cleanup",
       "transcript": "harsh the pan of the client is AKXPK4417M please double check before filing"},
  "Harsh, the PAN of the client is AKXPK4417M. Please double check before filing.",
  {"must_include": ["Harsh", "PAN", "AKXPK4417M", "before filing"], "numbers": ["4417"]},
  "facts: client PAN AKXPK4417M kept exactly; double-check before filing")

# 45 long standup
R(CA, {"task": "cleanup",
       "transcript": "standup notes uh yesterday i finished the login api for the ecommerce client and raised the PR uh today i'll work on the payment gateway integration with razorpay no wait with cashfree since the client changed it last week blocker is that we still don't have the sandbox keys anita said she'll get them by eleven sorry twelve also the demo is tentatively on wednesday but it might shift if the keys come late"},
  "Standup notes: yesterday I finished the login API for the ecommerce client and raised the PR. Today I'll work on the payment gateway integration with Cashfree, since the client changed it last week. Blocker is that we still don't have the sandbox keys. Anita said she'll get them by 12. Also, the demo is tentatively on Wednesday, but it might shift if the keys come late.",
  {"numbers": ["12"], "must_not_include": ["Razorpay", "11"], "must_include": ["login API", "PR", "Cashfree", "sandbox keys", "Anita", "tentatively on Wednesday", "might shift"], "min_negations": 1},
  "facts: corrections applied: Cashfree (Razorpay corrected away), keys by 12 (11 corrected away); still DON'T have sandbox keys; demo tentatively Wednesday, might shift if keys late (hedge + condition)")


# ---------------------------------------------------------------------------
# Stage 2 (ids TC-W03-101...225). Stage-1 rows above are unchanged.
# New domains: Surat textile trader, coaching institute, housing society maintenance,
# tiffin service, catering for a birthday party, co-operative bank branch.
# ---------------------------------------------------------------------------
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
ROWS2 = []


def R2(slice_, request, target, assertions, note, pos="structured", cx=None, waivers=None):
    i = 100 + len(ROWS2) + 1
    req = {"locale": "en-in"}
    req.update(request)
    if req.get("locale") is None:
        del req["locale"]
    if cx is None:
        cx = sum(1 for k in ("format", "register", "tone", "length", "wording", "context", "sender", "recipient")
                 if k in req) + (1 if "instruction" in req else 0)
        cx = min(cx, 4)
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    ROWS2.append(rec(f"TC-{WID}-{i:03d}", BUCKET, slice_, req, target, assertions, f"w03-sc-{i:03d}",
                     author=WID, note=note, waivers=waivers, meta=meta))


# --- stage 2, chunk 1 (101-142) ---

# 101
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "jignesh bhai kem cho the rayon maal reached the godown this morning saru che"},
   "Jignesh bhai, kem cho? The rayon maal reached the godown this morning. Saru che.",
   {"must_include": ["Jignesh bhai", "kem cho", "rayon maal", "godown", "this morning", "Saru che"]},
   "facts: rayon goods reached the godown this morning; Gujarati 'kem cho', 'maal', 'saru che' kept as spoken (Latin script)")

# 102
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "hetal ben please note the gst on the georgette fabric is five percent but on the stitched kurtis above one thousand rupees it is twelve percent so uh don't put five percent on the kurti bills by mistake"},
   "Hetal ben, please note the GST on the georgette fabric is 5%, but on the stitched kurtis above ₹1,000 it is 12%, so don't put 5% on the kurti bills by mistake.",
   {"numbers": ["5", "1,000", "12"], "must_include": ["Hetal ben", "GST", "georgette", "stitched kurtis", "kurti bills"], "min_negations": 1},
   "facts: GST 5% on georgette fabric; 12% on stitched kurtis above ₹1,000 (rupees spoken); do NOT put 5% on kurti bills; rates are as the speaker stated")

# 103
R2(CA, {"task": "cleanup",
        "transcript": "dispatch the parcel to ahmedabad no wait to rajkot by the evening train"},
   "Dispatch the parcel to Rajkot by the evening train.",
   {"must_include": ["Rajkot", "evening train"], "must_not_include": ["Ahmedabad"]},
   "facts: self-correction applied: destination Rajkot (Ahmedabad corrected away); by the evening train")

# 104
R2(FN, {"task": "cleanup",
        "transcript": "okay so notice for all members of shanti kunj society the maintenance for the october to december quarter is four thousand eight hundred rupees per flat uh due by the tenth of october after that a late fee of fifty rupees per day will be charged um the lift amc renewal is pending because the vendor quoted one lakh twelve thousand which the committee felt was too high so we are getting two more quotations also water tanker charges will not be added this quarter since the borewell is working fine and please don't park two wheelers near the gate from monday"},
   "Notice for all members of Shanti Kunj Society: the maintenance for the October to December quarter is ₹4,800 per flat, due by the 10th of October. After that, a late fee of ₹50 per day will be charged. The lift AMC renewal is pending because the vendor quoted 1,12,000, which the committee felt was too high, so we are getting two more quotations. Also, water tanker charges will not be added this quarter since the borewell is working fine, and please don't park two-wheelers near the gate from Monday.",
   {"numbers": ["4,800", "10", "50", "1,12,000"], "must_include": ["Shanti Kunj Society", "October to December quarter", "per flat", "per day", "lift AMC", "two more quotations", "water tanker", "borewell", "two-wheelers", "Monday"], "min_negations": 2},
   "facts: maintenance ₹4,800/flat for Oct-Dec quarter, due 10th of October; late fee ₹50/day after that; lift AMC quote 1,12,000 (no currency spoken there, so no ₹) felt too high, two more quotations; water tanker charges NOT added this quarter (borewell fine); do NOT park two-wheelers near gate from Monday")

# 105
R2(CO, {"task": "cleanup",
        "transcript": "siddharth sir the physics doubt session for the jee batch is shifted to room number four"},
   "Siddharth sir, the physics doubt session for the JEE batch is shifted to room number 4.",
   {"numbers": ["4"], "must_include": ["Siddharth sir", "physics doubt session", "JEE batch", "room number 4"]},
   "facts: JEE physics doubt session moved to room number 4 (room identifier written as a digit)")

# 106
R2(CA, {"task": "cleanup",
        "transcript": "um announcement for the neet repeaters batch the mock test is on sunday the nineteenth sorry the twentieth from nine thirty to twelve thirty uh reporting time is nine and late comers will not be allowed inside after nine fifteen the syllabus is the full physics and chemistry plus biology chapters one to twelve no wait one to fourteen and results will be on the portal by wednesday probably carry your admit card and a black ball pen only no gel pens"},
   "Announcement for the NEET repeaters batch: the mock test is on Sunday the 20th, from 9:30 to 12:30. Reporting time is 9, and latecomers will not be allowed inside after 9:15. The syllabus is the full physics and chemistry, plus biology chapters 1 to 14, and results will be on the portal by Wednesday, probably. Carry your admit card and a black ball pen only, no gel pens.",
   {"numbers": ["20", "9:30", "12:30", "9", "9:15", "1", "14"], "must_not_include": ["19th", "1 to 12"], "must_include": ["NEET repeaters", "Sunday", "latecomers will not be allowed", "biology chapters 1 to 14", "Wednesday, probably", "admit card", "black ball pen only", "no gel pens"], "min_negations": 2},
   "facts: corrections applied: test on Sunday the 20th (19th corrected away), biology chapters 1 to 14 (1 to 12 corrected away); 9:30-12:30, reporting 9, latecomers NOT allowed after 9:15; results by Wednesday hedged 'probably'; black ball pen only, NO gel pens. Waivers: checker does not apply 'the nineteenth sorry the twentieth' (known gap) and its 'one to twelve no wait one to fourteen' repair drops the first 'one', so it flags the kept 1 as invented; transcript kept natural",
   waivers=["number_missing", "number_invented"])

# 107
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "the fd of two lakh rupees matures on fifteenth aug not sixteenth"},
   "The FD of ₹2,00,000 matures on 15th Aug, not 16th.",
   {"numbers": ["2,00,000", "15", "16"], "must_include": ["FD", "15th Aug"], "min_negations": 1},
   "facts: FD ₹2,00,000 matures 15th Aug (spoken Indian date form kept), NOT 16th")

# 108
R2(FN, {"task": "cleanup",
        "transcript": "aparna tai from tomorrow the tiffin for flat b two zero four should be without onion and garlic and um only two chapatis not four because she has started some diet this is nakki"},
   "Aparna tai, from tomorrow the tiffin for flat B-204 should be without onion and garlic, and only two chapatis, not four, because she has started some diet. This is nakki.",
   {"numbers": ["204"], "must_include": ["Aparna tai", "from tomorrow", "B-204", "without onion and garlic", "only two chapatis", "not four", "nakki"], "min_negations": 2},
   "facts: from tomorrow, flat B-204 tiffin without onion and garlic; only two chapatis, NOT four (diet); Marathi 'tai', 'nakki' (definite) kept")

# 109
R2(FN, {"task": "rewrite", "format": "message", "context": "work",
        "instruction": "more polite please, keep the change number and both times exactly",
        "transcript": "karthik the prod deployment for CHG-55120 is tonight at eleven thirty pm so don't merge anything into main after nine pm and uh tell your team also no one should restart the payment service without telling me first"},
   "Karthik, the prod deployment for CHG-55120 is tonight at 11:30 p.m., so please don't merge anything into main after 9 p.m. Kindly let your team know as well: no one should restart the payment service without checking with me first.",
   {"format": "message", "numbers": ["55120", "11:30", "9"], "must_include": ["Karthik", "CHG-55120", "tonight", "main", "payment service"], "min_negations": 3},
   "facts: prod deployment CHG-55120 tonight 11:30 p.m.; do NOT merge into main after 9 p.m.; team to be told; no one restarts payment service without the speaker first. Politeness visibly added ('please', 'Kindly'); vocative Karthik was spoken",
   pos="after", cx=3)

# 110
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "imran the new leather balls are in the blue cupboard uh top shelf"},
   "Imran, the new leather balls are in the blue cupboard, top shelf.",
   {"must_include": ["Imran", "leather balls", "blue cupboard", "top shelf"]},
   "facts: new leather balls are in the blue cupboard, top shelf")

# 111
R2(FN, {"task": "cleanup",
        "transcript": "lakshmi madam's ticket pnr is four two one five six eight nine zero three two coach b three seat forty one it is still rac so don't book the cab until it gets confirmed"},
   "Lakshmi madam's ticket PNR is 4215689032, coach B3, seat 41. It is still RAC, so don't book the cab until it gets confirmed.",
   {"numbers": ["4215689032", "41"], "must_include": ["Lakshmi madam", "PNR", "4215689032", "B3", "seat 41", "still RAC", "until it gets confirmed"], "min_negations": 1},
   "facts: PNR 4215689032 (spoken digit by digit, written as one 10-digit number), coach B3, seat 41; still RAC; do NOT book the cab until confirmed")

# 112
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "bhaiya send twenty kilo basmati or if the basmati is not there then twenty five kilo sona masoori but not the kolam rice the customers didn't like it last time"},
   "Bhaiya, send 20 kilo basmati, or if the basmati is not there, then 25 kilo Sona Masoori, but not the Kolam rice. The customers didn't like it last time.",
   {"numbers": ["20", "25"], "must_include": ["Bhaiya", "basmati", "if the basmati is not there", "Sona Masoori", "Kolam"], "min_negations": 3},
   "facts: 20 kilo basmati; fallback only if basmati unavailable: 25 kilo Sona Masoori; NOT Kolam rice (customers didn't like it)")

# 113
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Mohsin Shaikh", "recipient": "Karthik",
        "transcript": "inform karthik that his gold loan of one lakh sixty thousand rupees is due for renewal on the twenty eighth of this month the interest rate is nine point five percent and he needs to bring the original receipt and his aadhaar card to the branch we cannot renew it over the phone"},
   "Dear Karthik,\n\nYour gold loan of ₹1,60,000 is due for renewal on the 28th of this month. The interest rate is 9.5%. You will need to bring the original receipt and your Aadhaar card to the branch, as we cannot renew it over the phone.\n\nRegards,\nMohsin Shaikh",
   {"format": "email", "numbers": ["1,60,000", "28", "9.5"], "must_include": ["Karthik", "gold loan", "renewal", "original receipt", "Aadhaar card", "branch", "over the phone", "Mohsin Shaikh"], "min_negations": 1},
   "facts: gold loan ₹1,60,000 due for renewal on the 28th of this month; interest 9.5%; bring original receipt and Aadhaar card to the branch; can NOT renew over the phone; no added offers")

# 114
R2(CO, {"task": "cleanup",
        "transcript": "divya the birthday party catering is for sixty people veg only"},
   "Divya, the birthday party catering is for 60 people, veg only.",
   {"numbers": ["60"], "must_include": ["Divya", "birthday party catering", "veg only"]},
   "facts: birthday party catering for 60 people, veg only")

# 115
R2(FN, {"task": "cleanup",
        "transcript": "pfa the draft computation for mr jignesh patel um the taxable income comes to eleven lakh forty two thousand and the tax payable after rebate is ninety eight thousand three hundred uh kindly note we have not claimed the hra because the rent receipts are not available and the eighty c limit of one point five lakh is fully used please confirm by eod tomorrow so we can file before the thirty first july there is no extension this year"},
   "PFA the draft computation for Mr. Jignesh Patel. The taxable income comes to 11,42,000, and the tax payable after rebate is 98,300. Kindly note we have not claimed the HRA because the rent receipts are not available, and the 80C limit of 1.5 lakh is fully used. Please confirm by EOD tomorrow so we can file before the 31st July. There is no extension this year.",
   {"numbers": ["11,42,000", "98,300", "80", "1.5", "31"], "must_include": ["PFA", "Mr. Jignesh Patel", "HRA", "80C", "1.5 lakh", "EOD tomorrow", "31st July", "no extension"], "min_negations": 3},
   "facts: taxable income 11,42,000; tax after rebate 98,300 (no currency spoken); HRA NOT claimed (rent receipts NOT available); 80C limit 1.5 lakh fully used; confirm by EOD tomorrow to file before 31st July; NO extension; jargon PFA/kindly/EOD kept")

# 116
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the meeting is at four thirty or five whichever suits the auditor"},
   "The meeting is at 4:30 or 5, whichever suits the auditor.",
   {"numbers": ["4:30", "5"], "must_include": ["whichever suits the auditor"]},
   "facts: genuine alternative kept: 4:30 OR 5, whichever suits the auditor")

# 117
R2(CO, {"task": "rewrite", "format": "message", "register": "casual", "tone": "friendly",
        "instruction": "WhatsApp message for my tiffin customers group, keep my Gujarati words",
        "transcript": "from next monday tiffin rates are going up by ten rupees per tiffin because vegetable prices have gone up a lot uh monthly plan will be two thousand six hundred instead of two thousand three hundred and sunday will still be off haa and if anyone wants extra rotli just tell before eleven am"},
   "Quick update: from next Monday, tiffin rates are going up by ₹10 per tiffin because vegetable prices have gone up a lot. The monthly plan will be 2,600 instead of 2,300, and Sunday will still be off, haa. If anyone wants extra rotli, just tell us before 11 a.m.!",
   {"format": "message", "numbers": ["10", "2,600", "2,300", "11"], "must_include": ["next Monday", "per tiffin", "vegetable prices", "monthly plan", "Sunday will still be off", "haa", "rotli"]},
   "facts: from next Monday +₹10 per tiffin (rupees spoken only for this amount, so ₹ only here); monthly plan 2,600 instead of 2,300; Sunday still off; extra rotli if told before 11 a.m.; Gujarati 'haa', 'rotli' kept; no greeting invented",
   pos="before", cx=4)

# 118
R2(FN, {"task": "cleanup",
        "transcript": "the sow says the tat for sev two bugs is two business days not one so please don't escalate to the client unless it crosses forty eight hours"},
   "The SOW says the TAT for Sev 2 bugs is two business days, not one, so please don't escalate to the client unless it crosses 48 hours.",
   {"numbers": ["2", "48"], "must_include": ["SOW", "TAT", "Sev 2", "two business days", "not one", "unless it crosses 48 hours"], "min_negations": 2},
   "facts: TAT for Sev 2 bugs is two business days, NOT one; do NOT escalate unless it crosses 48 hours (condition kept)")

# 119
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the society meeting is on saturday i mean sunday at the clubhouse"},
   "The society meeting is on Sunday at the clubhouse.",
   {"must_include": ["society meeting", "Sunday", "clubhouse"], "must_not_include": ["Saturday"]},
   "facts: self-correction applied: meeting on Sunday (Saturday corrected away)")

# 120
R2(CO, {"task": "cleanup",
        "transcript": "so karthik machan the client call went romba nice actually they liked the dashboard and um they want the same thing for their hyderabad unit also uh i told them we need the data access first seri and aparna akka will send the nda draft by tomorrow ayyo i forgot one thing they asked whether we can support tamil and telugu labels in the ui i said we will check so please look into it no promises yet"},
   "Karthik machan, the client call went romba nice actually. They liked the dashboard, and they want the same thing for their Hyderabad unit also. I told them we need the data access first, seri, and Aparna akka will send the NDA draft by tomorrow. Ayyo, I forgot one thing: they asked whether we can support Tamil and Telugu labels in the UI. I said we will check, so please look into it. No promises yet.",
   {"must_include": ["Karthik machan", "romba nice", "Hyderabad unit", "data access first", "seri", "Aparna akka", "NDA draft by tomorrow", "Ayyo", "Tamil and Telugu labels", "we will check", "No promises yet"], "min_negations": 1},
   "facts: client liked dashboard, wants same for Hyderabad unit; data access needed first; Aparna sends NDA draft by tomorrow; client asked about Tamil and Telugu UI labels, speaker said 'we will check', NO promises yet; Tamil words machan/romba/seri/akka/ayyo kept")

# 121
R2(FN, {"task": "rewrite", "format": "note",
        "instruction": "short note for myself, terse lines are fine, keep every amount",
        "transcript": "note for the hetal ben order she wants three hundred metres of the cotton cambric at eighty five rupees a metre advance paid fifteen thousand balance on delivery and uh no cash she will pay by rtgs only"},
   "Hetal ben order:\n300 metres cotton cambric at ₹85/metre.\nAdvance paid: 15,000. Balance on delivery.\nNo cash; she will pay by RTGS only.",
   {"format": "note", "numbers": ["300", "85", "15,000"], "must_include": ["Hetal ben", "cotton cambric", "Balance on delivery", "RTGS only"], "min_negations": 1},
   "facts: 300 metres cotton cambric at ₹85/metre (₹ only where rupees spoken); advance 15,000 paid; balance on delivery (not computed); NO cash, RTGS only",
   pos="before", cx=2)

# 122
R2(CA, {"task": "cleanup",
        "transcript": "please tell mohsin bhai the locker rent is three thousand five hundred per year for the small locker or six thousand for the medium one and the waiting list for medium is around two months"},
   "Please tell Mohsin bhai the locker rent is 3,500 per year for the small locker or 6,000 for the medium one, and the waiting list for medium is around two months.",
   {"numbers": ["3,500", "6,000"], "must_include": ["Mohsin bhai", "small locker", "medium one", "around two months"]},
   "facts: two options kept: small locker 3,500/year OR medium 6,000; medium waiting list around two months (hedge 'around' kept)")

# 123
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "hetal the batch b timetable is pinned on the notice board check it once"},
   "Hetal, the Batch B timetable is pinned on the notice board. Check it once.",
   {"must_include": ["Hetal", "Batch B timetable", "notice board", "Check it once"]},
   "facts: Batch B timetable pinned on notice board; Indian English 'check it once' kept")

# 124
R2(FN, {"task": "cleanup",
        "transcript": "anita if the courier guy calls from nine eight two five zero one two three four five tell him the office is closed today and he should come tomorrow after ten"},
   "Anita, if the courier guy calls from 9825012345, tell him the office is closed today and he should come tomorrow after 10.",
   {"numbers": ["9825012345", "10"], "must_include": ["Anita", "if the courier guy calls", "closed today", "tomorrow after 10"]},
   "facts: condition kept: if courier calls from 9825012345 (spoken digit by digit; obviously sequential, not a real person's number); office closed today; come tomorrow after 10")

# 125
R2(CO, {"task": "rewrite", "format": "email", "tone": "friendly", "sender": "Aparna", "recipient": "Gurpreet ji",
        "instruction": "email to the parent, friendly, and don't promise any refund",
        "transcript": "gurpreet ji your son missed the last three tests because of the fever uh we can arrange a re test on saturday at four pm if he is fit but the fee for the crash course is non refundable as per policy"},
   "Hi Gurpreet ji,\n\nYour son missed the last three tests because of the fever. We can happily arrange a re-test for him on Saturday at 4 p.m. if he is fit. Just to let you know, the fee for the crash course is non-refundable as per policy.\n\nBest,\nAparna",
   {"format": "email", "numbers": ["4"], "must_include": ["Gurpreet ji", "last three tests", "fever", "re-test", "Saturday", "if he is fit", "non-refundable", "Aparna"], "must_not_include": ["refund will", "we will refund"]},
   "facts: son missed last three tests (fever); re-test possible Saturday 4 p.m. ONLY if he is fit; crash course fee non-refundable as per policy; no refund promised; friendly wording only, no new facts",
   pos="after", cx=4)

# 126
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "the rent agreement is for eleven months not twelve"},
   "The rent agreement is for 11 months, not 12.",
   {"numbers": ["11", "12"], "must_include": ["rent agreement"], "min_negations": 1},
   "facts: rent agreement 11 months, NOT 12")

# 127
R2(CA, {"task": "cleanup",
        "transcript": "diwali order list for the agarwal sweets supplier um kaju katli fifteen kilo sorry eighteen kilo soan papdi forty boxes of the two fifty gram and uh dry fruit gift packs either sixty of the small ones or thirty of the big ones depending on the price he gives tell him delivery should be before the twenty eighth because the rush starts from twenty ninth and no credit this time payment on delivery"},
   "Diwali order list for the Agarwal Sweets supplier: kaju katli 18 kilo, soan papdi 40 boxes of the 250 gram, and dry fruit gift packs, either 60 of the small ones or 30 of the big ones, depending on the price he gives. Tell him delivery should be before the 28th because the rush starts from the 29th, and no credit this time, payment on delivery.",
   {"numbers": ["18", "40", "250", "60", "30", "28", "29"], "must_not_include": ["15 kilo"], "must_include": ["Agarwal Sweets", "kaju katli", "soan papdi", "either 60 of the small ones or 30 of the big ones", "depending on the price", "before the 28th", "no credit", "payment on delivery"], "min_negations": 1},
   "facts: correction applied: kaju katli 18 kilo (15 corrected away); soan papdi 40 boxes of 250 gram; alternative kept: 60 small OR 30 big gift packs depending on price; delivery before the 28th (rush from 29th); NO credit, payment on delivery. Kept as prose: no explicit list cues beyond 'order list'")

# 128
R2(CO, {"task": "cleanup",
        "transcript": "mohsin bhai pachi vaat karie i am in the market right now the sample of the new print will reach you by tomorrow through the angadia"},
   "Mohsin bhai, pachi vaat karie, I am in the market right now. The sample of the new print will reach you by tomorrow through the angadia.",
   {"must_include": ["Mohsin bhai", "pachi vaat karie", "in the market right now", "new print", "by tomorrow", "angadia"]},
   "facts: speaker in the market, will talk later (Gujarati 'pachi vaat karie' kept); new print sample reaches by tomorrow via angadia courier")

# 129
R2(FN, {"task": "rewrite", "format": "message", "context": "work", "length": "shorter",
        "instruction": "keep every date and the don't-call-before rule",
        "transcript": "hi so basically for the housing society audit we need all the maintenance receipts from april to september and the bank statements of both accounts the saving one and the fd one and um the auditor will come on the twenty first but he said please don't call him before eleven because he has another client in the morning"},
   "Hi, for the housing society audit we need all maintenance receipts from April to September and bank statements for both accounts, savings and FD. The auditor comes on the 21st; he asked not to be called before 11, as he has another client in the morning.",
   {"format": "message", "numbers": ["21", "11"], "must_include": ["housing society audit", "maintenance receipts", "April to September", "savings and FD", "21st", "before 11"], "min_negations": 1},
   "facts: audit needs maintenance receipts April-September and statements of both accounts (savings, FD); auditor on the 21st; do NOT call him before 11 (another client in the morning); dictated 'hi' kept",
   pos="after", cx=4)

# 130
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "cheque number zero zero four five one two bounced due to insufficient funds"},
   "Cheque number 004512 bounced due to insufficient funds.",
   {"numbers": ["004512"], "must_include": ["Cheque number 004512", "bounced", "insufficient funds"]},
   "facts: cheque number 004512 (leading zeros kept as spoken) bounced for insufficient funds")

# 131
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "can you move the sprint review from wednesday to thursday or friday afternoon whichever has fewer clashes question mark"},
   "Can you move the sprint review from Wednesday to Thursday or Friday afternoon, whichever has fewer clashes?",
   {"must_include": ["sprint review", "Wednesday", "Thursday or Friday afternoon", "fewer clashes"], "behavior": "not_answer", "ends_with_question": True},
   "facts: question kept as a question; alternative Thursday OR Friday afternoon kept; spoken 'question mark' applied")

# 132
R2(CO, {"task": "cleanup",
        "transcript": "okay boys listen the fitness test is compulsory for everyone in the under sixteen squad um yo yo test plus the thirty metre sprint and uh those who scored below sixteen point one last time have to do extra running three days a week gurpreet sir will maintain the chart and also the new kit sponsor wants a team photo so wear the white jersey on friday no coloured t shirts"},
   "Okay boys, listen. The fitness test is compulsory for everyone in the under-16 squad: yo-yo test plus the 30 metre sprint, and those who scored below 16.1 last time have to do extra running three days a week. Gurpreet sir will maintain the chart. Also, the new kit sponsor wants a team photo, so wear the white jersey on Friday, no coloured T-shirts.",
   {"numbers": ["16", "30", "16.1"], "must_include": ["compulsory", "under-16 squad", "yo-yo test", "30 metre sprint", "below 16.1", "three days a week", "Gurpreet sir", "white jersey on Friday", "no coloured T-shirts"], "min_negations": 1},
   "facts: fitness test compulsory for under-16 squad: yo-yo + 30 metre sprint; those below 16.1 last time do extra running three days a week; Gurpreet sir keeps chart; white jersey Friday for sponsor photo, NO coloured T-shirts")

# 133
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Rupinder Kaur",
        "transcript": "dear members the water supply will be off on thursday from ten am to four pm because the overhead tank cleaning is scheduled kindly store enough water on wednesday night the lift will also be shut for two hours in the afternoon no exceptions"},
   "Dear Members,\n\nThe water supply will be off on Thursday from 10 a.m. to 4 p.m. because the overhead tank cleaning is scheduled. Kindly store enough water on Wednesday night.\n\nThe lift will also be shut for 2 hours in the afternoon, with no exceptions.\n\nRegards,\nRupinder Kaur",
   {"format": "email", "numbers": ["10", "4", "2"], "must_include": ["Dear Members", "Thursday", "overhead tank cleaning", "Wednesday night", "lift", "no exceptions", "Rupinder Kaur"], "min_negations": 1},
   "facts: water off Thursday 10 a.m.-4 p.m. (tank cleaning); store water Wednesday night; lift shut 2 hours in the afternoon, NO exceptions; dictated greeting 'dear members' kept")

# 134
R2(CO, {"task": "cleanup",
        "transcript": "pooja didi the tiffin dabba was left at the uh security cabin"},
   "Pooja didi, the tiffin dabba was left at the security cabin.",
   {"must_include": ["Pooja didi", "tiffin dabba", "security cabin"]},
   "facts: tiffin dabba left at the security cabin")

# 135
R2(FN, {"task": "cleanup",
        "transcript": "um branch update for the week the cash in hand limit is twenty lakh rupees so anything above that has to go to the currency chest the same day no exceptions uh the new kyc rule says re kyc for accounts older than ten years should be done by thirty first march next year and we have around four hundred eighty such accounts pending imran please share the list with the field staff by friday also the atm at the market branch was down for six hours on tuesday so log a complaint with the vendor and don't close it until they send the root cause report"},
   "Branch update for the week: the cash in hand limit is ₹20,00,000, so anything above that has to go to the currency chest the same day, no exceptions. The new KYC rule says re-KYC for accounts older than 10 years should be done by 31st March next year, and we have around 480 such accounts pending. Imran, please share the list with the field staff by Friday.\n\nAlso, the ATM at the market branch was down for 6 hours on Tuesday, so log a complaint with the vendor and don't close it until they send the root cause report.",
   {"numbers": ["20,00,000", "10", "31", "480", "6"], "must_include": ["currency chest", "same day", "no exceptions", "re-KYC", "31st March next year", "around 480", "Imran", "field staff by Friday", "ATM", "Tuesday", "root cause report"], "min_negations": 2},
   "facts: cash-in-hand limit ₹20,00,000, excess to currency chest same day, NO exceptions; re-KYC for accounts older than 10 years by 31st March next year; around 480 pending; Imran shares list with field staff by Friday; market branch ATM down 6 hours Tuesday; log vendor complaint, do NOT close until root cause report")

# 136
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "book two tatkal tickets for friday or saturday whichever is available"},
   "Book two Tatkal tickets for Friday or Saturday, whichever is available.",
   {"must_include": ["two Tatkal tickets", "Friday or Saturday", "whichever is available"]},
   "facts: alternative kept: Friday OR Saturday, whichever is available; two Tatkal tickets; cleanup only, no booking claimed")

# 137
R2(CA, {"task": "rewrite", "format": "message",
        "instruction": "clear message for the caterer, keep both menu options and the price condition",
        "transcript": "for the birthday party on the fifteenth we are expecting around forty guests twenty five adults and fifteen kids for kids we want pav bhaji and for adults either paneer tikka or chole bhature we'll confirm which one by wednesday no paneer at all if the price goes above four hundred per plate"},
   "For the birthday party on the 15th, we are expecting around 40 guests: 25 adults and 15 kids. For the kids, we want pav bhaji. For the adults, either paneer tikka or chole bhature; we'll confirm which one by Wednesday. If the price goes above 400 per plate, no paneer at all.",
   {"format": "message", "numbers": ["15", "40", "25", "400"], "must_include": ["birthday party", "around 40 guests", "pav bhaji", "either paneer tikka or chole bhature", "by Wednesday", "above 400 per plate", "no paneer at all"], "min_negations": 1},
   "facts: party on the 15th; around 40 guests = 25 adults + 15 kids; kids: pav bhaji; adults: paneer tikka OR chole bhature (both kept), confirm by Wednesday; conditional: NO paneer at all IF price above 400/plate (no currency spoken)",
   pos="after", cx=3)

# 138
R2(FN, {"task": "cleanup",
        "transcript": "for the account opening we need aadhaar and pan the aadhaar number she gave is one two three four five six seven eight nine zero one two but the name on it does not match the pan so don't open the account yet"},
   "For the account opening, we need Aadhaar and PAN. The Aadhaar number she gave is 1234 5678 9012, but the name on it does not match the PAN, so don't open the account yet.",
   {"numbers": ["1234 5678 9012"], "must_include": ["Aadhaar", "PAN", "1234 5678 9012", "does not match", "don't open the account yet"], "min_negations": 2},
   "facts: obviously fake placeholder Aadhaar 1234 5678 9012 written in the standard 4-4-4 grouping; name does NOT match PAN; do NOT open the account yet. Waiver: checker reads the 12 spoken digits as one number and the grouped form as three numbers",
   waivers=["number_missing", "number_invented"])

# 139
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "lakshmi ma'am the xerox machine on the second floor is jammed again"},
   "Lakshmi ma'am, the xerox machine on the second floor is jammed again.",
   {"must_include": ["Lakshmi ma'am", "xerox machine", "second floor", "jammed again"]},
   "facts: xerox machine on second floor jammed again ('again' is a fact)")

# 140
R2(CA, {"task": "cleanup",
        "transcript": "jignesh the order from the delhi party is for five hundred sarees of the new zari design uh at four hundred twenty five rupees per piece no wait four hundred fifty because they want the blouse piece also attached and dispatch is in two lots first lot of three hundred by the twentieth and the remaining two hundred by the fifth of next month payment is thirty percent advance and the rest within forty five days and um they said no returns once the lot is opened so pack carefully"},
   "Jignesh, the order from the Delhi party is for 500 sarees of the new zari design at ₹450 per piece, because they want the blouse piece also attached. Dispatch is in two lots: first lot of 300 by the 20th and the remaining 200 by the 5th of next month. Payment is 30% advance and the rest within 45 days, and they said no returns once the lot is opened, so pack carefully.",
   {"numbers": ["500", "450", "300", "20", "200", "5", "30", "45"], "must_not_include": ["425"], "must_include": ["Jignesh", "Delhi party", "zari design", "per piece", "blouse piece", "two lots", "30% advance", "within 45 days", "no returns once the lot is opened"], "min_negations": 1},
   "facts: 500 sarees, correction applied: ₹450/piece (₹425 corrected away; rupees spoken for this price) because blouse piece attached; dispatch 300 by the 20th, remaining 200 by the 5th of next month; 30% advance, rest within 45 days; NO returns once lot opened")

# 141
R2(FN, {"task": "rewrite", "format": "message", "register": "formal",
        "instruction": "formal message to the society committee, keep the amount and the 'not yet started' part",
        "transcript": "the painting contractor has finished only the a and b wings c wing is not yet started and he is asking for the second instalment of two lakh seventy five thousand i think we should hold it until c wing is at least half done"},
   "The painting contractor has completed only the A and B wings; work on C wing has not yet started. He is requesting the second instalment of 2,75,000. I think we should hold it until C wing is at least half done.",
   {"format": "message", "numbers": ["2,75,000"], "must_include": ["painting contractor", "only the A and B wings", "C wing", "not yet started", "second instalment", "I think", "at least half done"], "min_negations": 1},
   "facts: only A and B wings done; C wing NOT yet started; contractor asking second instalment 2,75,000 (no currency spoken); hedge 'I think' on holding payment until C wing at least half done; formal wording visibly changed",
   pos="before", cx=3)

# 142
R2(CO, {"task": "cleanup",
        "transcript": "divya tai the samosa order for the office party is confirmed lavkar pay the advance otherwise he will give the slot to someone else bara"},
   "Divya tai, the samosa order for the office party is confirmed. Lavkar pay the advance, otherwise he will give the slot to someone else, bara.",
   {"must_include": ["Divya tai", "samosa order", "office party", "confirmed", "Lavkar", "advance", "otherwise", "bara"]},
   "facts: samosa order confirmed; pay advance quickly (Marathi 'lavkar') or the slot goes to someone else (condition kept); Marathi 'bara' kept")

# --- stage 2, chunk 2 (143-184) ---

# 143
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "aparna akka the chemistry notes xerox is ready collect it from the front desk seri"},
   "Aparna akka, the chemistry notes xerox is ready. Collect it from the front desk, seri.",
   {"must_include": ["Aparna akka", "chemistry notes", "front desk", "seri"]},
   "facts: chemistry notes photocopy ready at the front desk; Tamil 'akka', 'seri' kept")

# 144
R2(FN, {"task": "rewrite", "format": "email", "sender": "Siddharth", "recipient": "Divya",
        "instruction": "concise email, keep the release version and dates exactly, no new commitments",
        "transcript": "divya just to update you release two point four point one is postponed from the eighteenth to the twenty fifth because the security scan found three high severity issues um two are fixed the third one needs a dependency upgrade which we haven't tested yet so please don't announce the new date to the client until we confirm on monday"},
   "Hi Divya,\n\nRelease 2.4.1 is postponed from the 18th to the 25th because the security scan found three high-severity issues. Two are fixed; the third needs a dependency upgrade that we haven't tested yet. Please don't announce the new date to the client until we confirm on Monday.\n\nBest,\nSiddharth",
   {"format": "email", "numbers": ["2.4.1", "18", "25"], "must_include": ["Divya", "Release 2.4.1", "postponed", "three high-severity issues", "Two are fixed", "dependency upgrade", "haven't tested yet", "until we confirm on Monday", "Siddharth"], "min_negations": 2},
   "facts: release 2.4.1 postponed from the 18th to the 25th; scan found three high-severity issues, two fixed, third needs untested dependency upgrade; do NOT announce new date until confirmed Monday. Waiver: checker splits the spoken version 'two point four point one' and misses the last 1; version kept exactly as 2.4.1",
   pos="after", cx=4, waivers=["number_missing"])

# 145
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the security guard salary is fourteen thousand per month uh plus pf the agency wants sixteen thousand from january but we can offer fifteen thousand max or we look for another agency"},
   "The security guard salary is 14,000 per month plus PF. The agency wants 16,000 from January, but we can offer 15,000 max, or we look for another agency.",
   {"numbers": ["14,000", "16,000", "15,000"], "must_include": ["security guard salary", "plus PF", "from January", "15,000 max", "another agency"]},
   "facts: current salary 14,000/month plus PF; agency wants 16,000 from January; society can offer 15,000 max OR look for another agency (alternative kept); no currency spoken")

# 146
R2(FN, {"task": "cleanup",
        "transcript": "the pin code is three nine five zero zero three not three nine five zero zero seven"},
   "The PIN code is 395003, not 395007.",
   {"numbers": ["395003", "395007"], "must_include": ["PIN code"], "min_negations": 1},
   "facts: PIN code 395003, NOT 395007 (spoken digit by digit)")

# 147
R2(CO, {"task": "cleanup",
        "transcript": "hetal ben su thayu the transport wala didn't pick up the bales yesterday so um today i called him again and he said the truck will come at four uh barabar four o'clock so keep the bills and the e way bill ready and haan the two bales for the bhiwandi party should go separately don't mix them with the local maal last time there was a big confusion and we lost one full day"},
   "Hetal ben, su thayu? The transport wala didn't pick up the bales yesterday, so today I called him again, and he said the truck will come at 4, barabar 4 o'clock, so keep the bills and the e-way bill ready. And haan, the two bales for the Bhiwandi party should go separately. Don't mix them with the local maal. Last time there was a big confusion and we lost one full day.",
   {"numbers": ["4"], "must_include": ["Hetal ben", "su thayu", "transport wala", "yesterday", "again", "barabar 4 o'clock", "e-way bill", "haan", "two bales", "Bhiwandi party", "separately", "local maal", "one full day"], "min_negations": 2},
   "facts: transporter did NOT pick up bales yesterday; called again today, truck at 4 ('barabar' = exactly); keep bills and e-way bill ready; two Bhiwandi bales go separately, do NOT mix with local goods; last time one full day lost; Gujarati 'su thayu', 'barabar', 'maal' kept")

# 148
R2(CA, {"task": "rewrite", "format": "message", "register": "casual",
        "instruction": "casual message for the parents, keep both travel options",
        "transcript": "the inter district tournament is in nashik from the third to the seventh parents can either travel with the team by bus for two thousand two hundred rupees or come on their own but they have to inform anita ma'am by saturday either way"},
   "The inter-district tournament is in Nashik from the 3rd to the 7th. Parents can either travel with the team by bus for ₹2,200 or come on their own, but either way, they need to let Anita ma'am know by Saturday.",
   {"format": "message", "numbers": ["3", "7", "2,200"], "must_include": ["inter-district tournament", "Nashik", "travel with the team by bus", "come on their own", "either way", "Anita ma'am", "Saturday"]},
   "facts: tournament in Nashik from the 3rd to the 7th; parents either travel with team by bus for ₹2,200 OR come on their own (both kept); either way inform Anita ma'am by Saturday",
   pos="before", cx=3)

# 149
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "please note the rd instalment of two thousand rupees did not get debited this month because the savings balance was only one thousand eight hundred so ask the member to deposit before the twenty fifth or there will be a penalty of twenty rupees"},
   "Please note the RD instalment of ₹2,000 did not get debited this month because the savings balance was only 1,800, so ask the member to deposit before the 25th or there will be a penalty of ₹20.",
   {"numbers": ["2,000", "1,800", "25", "20"], "must_include": ["RD instalment", "did not get debited", "savings balance", "before the 25th", "penalty"], "min_negations": 1},
   "facts: RD instalment ₹2,000 NOT debited this month; savings balance only 1,800 (no currency spoken for it, so no ₹; ₹ only on the two amounts said in rupees); deposit before the 25th or ₹20 penalty")

# 150
R2(CA, {"task": "cleanup",
        "transcript": "call the electrician at two make that three thirty"},
   "Call the electrician at 3:30.",
   {"numbers": ["3:30"], "must_not_include": ["2"], "must_include": ["electrician"]},
   "facts: self-correction applied: 3:30 (2 corrected away)")

# 151
R2(CO, {"task": "cleanup",
        "transcript": "um the new delivery boy imran will start from monday he knows the adajan area routes uh but for the vesu side customers please send the old route list on whatsapp to him tonight itself"},
   "The new delivery boy, Imran, will start from Monday. He knows the Adajan area routes, but for the Vesu side customers, please send the old route list on WhatsApp to him tonight itself.",
   {"must_include": ["Imran", "Monday", "Adajan", "Vesu side customers", "old route list", "WhatsApp", "tonight itself"]},
   "facts: new delivery boy Imran starts Monday; knows Adajan routes; send him the old Vesu route list on WhatsApp tonight itself")

# 152
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Anita Desai", "recipient": "Mohsin Shaikh",
        "instruction": "formal email, keep the loan account number exactly and don't soften the deadline",
        "transcript": "this is to inform mohsin shaikh that the emi for loan account number seven seven zero three one two four five is overdue by forty five days the overdue amount is thirty eight thousand four hundred rupees including penal interest he must clear it by the thirtieth of this month otherwise the account will be classified as npa"},
   "Dear Mohsin Shaikh,\n\nThis is to inform you that the EMI for loan account number 77031245 is overdue by 45 days. The overdue amount is ₹38,400, including penal interest. You must clear it by the 30th of this month; otherwise, the account will be classified as NPA.\n\nRegards,\nAnita Desai",
   {"format": "email", "numbers": ["77031245", "45", "38,400", "30"], "must_include": ["Mohsin Shaikh", "EMI", "loan account number 77031245", "overdue by 45 days", "penal interest", "must clear it by the 30th", "otherwise", "NPA", "Anita Desai"]},
   "facts: EMI on loan account 77031245 overdue 45 days; overdue ₹38,400 incl. penal interest; must clear by the 30th of this month, otherwise NPA (firm deadline, not softened); no added offers",
   pos="after", cx=4)

# 153
R2(CA, {"task": "cleanup",
        "transcript": "for the client workshop we need either the big conference room for twenty people or two small rooms of ten each harsh will check availability sorry pooja will check because harsh is on leave"},
   "For the client workshop, we need either the big conference room for 20 people or two small rooms of 10 each. Pooja will check availability because Harsh is on leave.",
   {"numbers": ["20", "10"], "must_include": ["client workshop", "either the big conference room", "two small rooms of 10 each", "Pooja will check", "Harsh is on leave"], "must_not_include": ["Harsh will check"]},
   "facts: alternative kept: big room for 20 OR two small rooms of 10 each; self-correction: Pooja checks availability (not Harsh, who is on leave)")

# 154
R2(FN, {"task": "cleanup",
        "transcript": "the gst invoice should show eighteen percent igst not cgst plus sgst since the buyer is in maharashtra"},
   "The GST invoice should show 18% IGST, not CGST plus SGST, since the buyer is in Maharashtra.",
   {"numbers": ["18"], "must_include": ["GST invoice", "18% IGST", "CGST plus SGST", "Maharashtra"], "min_negations": 1},
   "facts: invoice should show 18% IGST, NOT CGST plus SGST, because buyer is in Maharashtra")

# 155
R2(CO, {"task": "rewrite", "format": "prose", "length": "shorter",
        "instruction": "tighten this up and remove the repetition, keep the Marathi bits",
        "transcript": "so the thing is the thing is aai's tiffin service is getting a lot of orders now from the it park side like forty fifty orders daily and honestly she can't manage alone anymore so we are thinking of hiring one more cook maybe from next month but only if the orders stay like this kay mhanta"},
   "Aai's tiffin service is now getting a lot of orders from the IT park side, like 40-50 daily, and honestly she can't manage alone anymore. So we are thinking of hiring one more cook, maybe from next month, but only if the orders stay like this. Kay mhanta?",
   {"format": "prose", "numbers": ["40", "50"], "must_include": ["Aai's tiffin service", "IT park", "like 40-50", "honestly", "can't manage alone", "one more cook", "maybe from next month", "only if the orders stay like this", "Kay mhanta"], "min_negations": 1},
   "facts: many orders from IT park side, like 40-50 daily ('like' = about, kept); mother can't manage alone; thinking of one more cook, hedged 'maybe from next month', ONLY IF orders stay like this; Marathi 'Aai', 'kay mhanta' (what do you say) kept. Waiver: checker reads 'forty fifty' as one number and flags 50; the range is what was spoken",
   pos="before", cx=3, waivers=["number_invented"])

# 156
R2(CA, {"task": "cleanup",
        "transcript": "for the selection committee meeting tomorrow um the shortlist is final for the batsmen we have siddharth harsh and karthik for the two opening slots and for the spinners it's between mohsin and jignesh we'll decide after the practice match uh the wicketkeeper is imran no wait rupinder because imran has a finger injury and won't be fit for at least three weeks and the captain will be announced only after the board approves so don't tell the boys anything yet"},
   "For the selection committee meeting tomorrow, the shortlist is final. For the batsmen, we have Siddharth, Harsh and Karthik for the two opening slots, and for the spinners, it's between Mohsin and Jignesh; we'll decide after the practice match. The wicketkeeper is Rupinder because Imran has a finger injury and won't be fit for at least three weeks, and the captain will be announced only after the board approves, so don't tell the boys anything yet.",
   {"must_include": ["selection committee", "Siddharth, Harsh and Karthik", "two opening slots", "between Mohsin and Jignesh", "after the practice match", "wicketkeeper is Rupinder", "finger injury", "at least three weeks", "only after the board approves", "don't tell the boys"], "must_not_include": ["wicketkeeper is Imran"], "min_negations": 2},
   "facts: batsmen Siddharth, Harsh, Karthik for two opening slots; spinner Mohsin OR Jignesh, decided after practice match (alternative kept); correction: wicketkeeper Rupinder (Imran corrected away; Imran injured, NOT fit for at least three weeks); captain announced ONLY after board approves; do NOT tell the boys yet")

# 157
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "hetal the passbook printer is working now you can send the uh customers"},
   "Hetal, the passbook printer is working now. You can send the customers.",
   {"must_include": ["Hetal", "passbook printer", "working now", "send the customers"]},
   "facts: passbook printer working now; customers can be sent")

# 158
R2(FN, {"task": "rewrite", "format": "message", "tone": "confident",
        "instruction": "sound confident but keep the 'might' and the condition exactly",
        "transcript": "we might get the export order from the dubai buyer for ten thousand metres of polyester if our sample passes their lab test which should be done by the end of next week"},
   "We might well land the Dubai buyer's export order for 10,000 metres of polyester if our sample passes their lab test, and that test should be done by the end of next week.",
   {"format": "message", "numbers": ["10,000"], "must_include": ["might", "Dubai buyer", "10,000 metres of polyester", "if our sample passes their lab test", "end of next week"]},
   "facts: hedge 'might' kept; export order for 10,000 metres polyester ONLY IF sample passes lab test; test 'should be done' by end of next week (hedged, not a promise); confident wording ('might well land') without removing the hedge",
   pos="after", cx=3)

# 159
R2(FN, {"task": "cleanup",
        "transcript": "the client's uat environment url is uat dot finplus dash demo dot in slash login and the test user id is qa underscore admin zero one don't share the password on email send it on the teams chat only"},
   "The client's UAT environment URL is uat.finplus-demo.in/login and the test user ID is qa_admin01. Don't share the password on email; send it on the Teams chat only.",
   {"numbers": ["01"], "must_include": ["UAT", "uat.finplus-demo.in/login", "qa_admin01", "Teams chat only"], "min_negations": 1},
   "facts: spoken URL rendered literally uat.finplus-demo.in/login; user ID qa_admin01; do NOT share password on email, Teams chat only")

# 160
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the mehendi artist for the birthday party is coming at five or five thirty she'll confirm"},
   "The mehendi artist for the birthday party is coming at 5 or 5:30. She'll confirm.",
   {"numbers": ["5", "5:30"], "must_include": ["mehendi artist", "birthday party", "She'll confirm"]},
   "facts: alternative kept: 5 OR 5:30, still to be confirmed by the artist")

# 161
R2(FN, {"task": "rewrite", "format": "email", "sender": "Karthik",
        "instruction": "email to all faculty, under 90 words, keep every date",
        "transcript": "hi all the half yearly exam schedule is out the eleventh standard exams start on the fourth of december and twelfth standard on the sixth uh papers must be submitted to me by the twentieth of november no late submissions this time and invigilation duties will be shared on friday please check your free periods before that"},
   "Hi all,\n\nThe half-yearly exam schedule is out. The 11th standard exams start on the 4th of December and the 12th standard on the 6th. Papers must be submitted to me by the 20th of November; no late submissions this time.\n\nInvigilation duties will be shared on Friday, so please check your free periods before that.\n\nBest,\nKarthik",
   {"format": "email", "max_words": 90, "numbers": ["11", "4", "12", "6", "20"], "must_include": ["half-yearly exam", "11th standard", "4th of December", "12th standard", "20th of November", "no late submissions", "Friday", "free periods", "Karthik"], "min_negations": 1},
   "facts: 11th standard exams from the 4th of December, 12th standard from the 6th; papers to the speaker by the 20th of November, NO late submissions; invigilation duties shared Friday; check free periods before that; dictated 'hi all' kept as greeting",
   pos="after", cx=3)

# 162
R2(CO, {"task": "cleanup",
        "transcript": "rupinder paaji the langar style lunch for the birthday is fine but uh keep the spice level low because there are lots of small kids coming"},
   "Rupinder paaji, the langar-style lunch for the birthday is fine, but keep the spice level low because there are lots of small kids coming.",
   {"must_include": ["Rupinder paaji", "langar-style lunch", "birthday", "spice level low", "small kids"]},
   "facts: langar-style birthday lunch approved; keep spice low because many small kids are coming")

# 163
R2(FN, {"task": "cleanup",
        "transcript": "so for the march closing um the total sales of the shop this year is around two crore forty lakh and purchases are one crore eighty five lakh the stock in hand as on thirty first march is roughly thirty two lakh but uh don't take that as final the physical stock count is still going on and jignesh said around five six lakh of maal is lying with the job workers in pandesara which is not included yet so the ca will finalise only after we give the job work statement please send it to him by the tenth of april not later"},
   "For the March closing, the total sales of the shop this year is around 2 crore 40 lakh, and purchases are 1 crore 85 lakh. The stock in hand as on 31st March is roughly 32 lakh, but don't take that as final. The physical stock count is still going on, and Jignesh said around 5-6 lakh of maal is lying with the job workers in Pandesara, which is not included yet. So the CA will finalise only after we give the job work statement. Please send it to him by the 10th of April, not later.",
   {"numbers": ["2", "40", "1", "85", "31", "32", "5", "6", "10"], "must_include": ["around 2 crore 40 lakh", "1 crore 85 lakh", "31st March", "roughly 32 lakh", "don't take that as final", "around 5-6 lakh", "Pandesara", "not included yet", "only after", "10th of April, not later"], "min_negations": 3},
   "facts: sales around 2 crore 40 lakh; purchases 1 crore 85 lakh; stock as on 31st March roughly 32 lakh, NOT final (count ongoing); around 5-6 lakh goods with Pandesara job workers NOT included yet; CA finalises ONLY after job work statement; send by 10th of April, not later; hedges 'around'/'roughly' kept; no currency spoken so lakh/crore words without ₹, one style for the whole record. Waivers: checker cannot read 'N crore M lakh' / '5-6 lakh' word forms",
   waivers=["number_missing", "number_invented"])

# 164
R2(CA, {"task": "rewrite", "format": "message",
        "instruction": "quick reminder for the coaching staff, use the corrected time only",
        "transcript": "reminder the parents meeting for the foundation batch is at ten thirty no sorry eleven on sunday in the main hall attendance is compulsory for all batch mentors"},
   "Reminder: the parents meeting for the foundation batch is at 11 on Sunday in the main hall. Attendance is compulsory for all batch mentors.",
   {"format": "message", "numbers": ["11"], "must_not_include": ["10:30"], "must_include": ["Reminder", "parents meeting", "foundation batch", "Sunday", "main hall", "compulsory", "batch mentors"]},
   "facts: correction applied: meeting at 11 (10:30 corrected away), Sunday, main hall; attendance compulsory for all batch mentors. Waiver: the 'no' in 'no sorry' is part of the self-correction, not a negation of content; checker counts it",
   pos="before", cx=2, waivers=["negation_lost"])

# 165
R2(FN, {"task": "cleanup",
        "transcript": "do not give the duplicate key of flat c three zero two to anyone without the owner's written permission"},
   "Do not give the duplicate key of flat C-302 to anyone without the owner's written permission.",
   {"numbers": ["302"], "must_include": ["Do not give", "duplicate key", "C-302", "without the owner's written permission"], "min_negations": 2},
   "facts: do NOT give C-302 duplicate key to anyone WITHOUT owner's written permission")

# 166
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "so pooja the offsite is at the nandi hills resort uh bus leaves from the office at seven am sharp and we'll be back by eight pm carry an id card and some warm clothes it gets cold there"},
   "Pooja, the offsite is at the Nandi Hills resort. Bus leaves from the office at 7 a.m. sharp, and we'll be back by 8 p.m. Carry an ID card and some warm clothes; it gets cold there.",
   {"numbers": ["7", "8"], "must_include": ["Pooja", "offsite", "Nandi Hills resort", "7 a.m. sharp", "back by 8 p.m.", "ID card", "warm clothes"]},
   "facts: offsite at Nandi Hills resort; bus 7 a.m. sharp from office; back by 8 p.m.; carry ID card and warm clothes")

# 167
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Hetal Shah", "recipient": "Imran",
        "instruction": "polite formal email, PFA is fine, keep the section number and amount exactly, no new deadlines",
        "transcript": "pfa the reply to the income tax notice under section one four three one a uh the demand of forty two thousand seven hundred was raised because the tds of the second quarter was not matched we have attached the corrected form twenty six as please check and revert if any changes"},
   "Dear Imran,\n\nPFA the reply to the income tax notice under section 143(1)(a). The demand of 42,700 was raised because the TDS of the second quarter was not matched. We have attached the corrected Form 26AS. Kindly check and revert if any changes are required.\n\nRegards,\nHetal Shah",
   {"format": "email", "numbers": ["42,700", "26"], "must_include": ["Imran", "PFA", "143(1)(a)", "42,700", "TDS of the second quarter", "not matched", "Form 26AS", "revert if any changes", "Hetal Shah"], "min_negations": 1},
   "facts: reply to notice u/s 143(1)(a); demand 42,700 (no currency spoken) because Q2 TDS NOT matched; corrected Form 26AS attached; check and revert if changes; no deadline added. Waiver: checker reads spoken 'one four three one a' as 1431 and cannot see the section notation 143(1)(a)",
   pos="after", cx=4, waivers=["number_missing", "number_invented"])

# 168
R2(CA, {"task": "cleanup",
        "transcript": "keep fifty or sixty plates extra just in case"},
   "Keep 50 or 60 plates extra, just in case.",
   {"numbers": ["50", "60"], "must_include": ["plates extra", "just in case"]},
   "facts: alternative kept: 50 OR 60 extra plates, just in case")

# 169
R2(FN, {"task": "cleanup",
        "transcript": "the cooking oil price list is wrong the one litre fortune pouch is one hundred sixty five not one hundred fifty six and the five litre jar is seven hundred ninety so correct the board before opening"},
   "The cooking oil price list is wrong. The 1 litre Fortune pouch is 165, not 156, and the 5 litre jar is 790, so correct the board before opening.",
   {"numbers": ["1", "165", "156", "5", "790"], "must_include": ["price list is wrong", "Fortune pouch", "5 litre jar", "before opening"], "min_negations": 1},
   "facts: 1 litre Fortune pouch is 165, NOT 156 (digit swap is the point); 5 litre jar 790; correct board before opening; no currency spoken. Waiver: checker ignores a bare spoken 'one' and flags the measurement '1 litre' as invented",
   waivers=["number_invented"])

# 170
R2(CO, {"task": "rewrite", "format": "message", "register": "formal",
        "instruction": "make this a formal message to the branch manager without changing any facts",
        "transcript": "sir the cash counting machine at counter two is giving wrong count since morning uh we have stopped using it and are counting manually so the queue is long please send someone from the vendor today"},
   "Sir, the cash counting machine at Counter 2 has been giving an incorrect count since this morning. We have stopped using it and are counting manually, so the queue is long. Kindly arrange for someone from the vendor to come today.",
   {"format": "message", "numbers": ["2"], "must_include": ["Sir", "cash counting machine", "Counter 2", "since this morning", "stopped using it", "counting manually", "queue is long", "vendor", "today"]},
   "facts: Counter 2 counting machine wrong since morning; stopped using it, counting manually, long queue; request someone from vendor today; formal wording visibly changed; 'Sir' was dictated",
   pos="after", cx=3)

# 171
R2(FN, {"task": "cleanup",
        "transcript": "minutes of the agm um it was decided that the sinking fund contribution will increase from one rupee to one rupee fifty per square foot per month starting april the proposal to install cctv in all three wings was approved with a budget of three lakh sixty thousand uh the solar panel proposal was not approved because only eighteen out of forty two members were in favour it will be discussed again next year and members who have not paid dues for more than six months will not be allowed to vote in the next agm"},
   "Minutes of the AGM: it was decided that the sinking fund contribution will increase from ₹1 to ₹1.50 per square foot per month, starting April. The proposal to install CCTV in all three wings was approved with a budget of ₹3,60,000. The solar panel proposal was not approved because only 18 out of 42 members were in favour; it will be discussed again next year. Members who have not paid dues for more than 6 months will not be allowed to vote in the next AGM.",
   {"numbers": ["1", "1.50", "3,60,000", "18", "42", "6"], "must_include": ["AGM", "sinking fund", "per square foot per month", "starting April", "CCTV in all three wings", "solar panel proposal was not approved", "18 out of 42", "next year", "will not be allowed to vote"], "min_negations": 3},
   "facts: sinking fund up from ₹1 to ₹1.50 per sq ft per month from April; CCTV in all three wings approved, budget ₹3,60,000 (rupee context of the minutes applied to both money amounts; choice noted); solar NOT approved (only 18 of 42 in favour), discussed again next year; members with dues unpaid more than 6 months NOT allowed to vote. Waiver: checker reads 'one rupee fifty' as 1 and 50, not 1.50",
   waivers=["number_missing"])

# 172
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "tell the party the cheque will be ready on thursday sorry friday so come on friday afternoon aavjo"},
   "Tell the party the cheque will be ready on Friday, so come on Friday afternoon, aavjo.",
   {"must_include": ["the party", "cheque", "ready on Friday", "Friday afternoon", "aavjo"], "must_not_include": ["Thursday"]},
   "facts: correction applied: cheque ready Friday (Thursday corrected away); come Friday afternoon; Gujarati 'aavjo' kept")

# 173
R2(FN, {"task": "rewrite", "format": "note",
        "instruction": "quick note with the key numbers, nothing added",
        "transcript": "catering for pooja's daughter's birthday on the twenty second total eighty plates at three hundred fifty rupees a plate advance of ten thousand given balance to be paid on the day itself no non veg and the cake is not from us they are ordering it separately"},
   "Birthday catering, Pooja's daughter, 22nd:\n80 plates at ₹350/plate.\nAdvance 10,000 given; balance to be paid on the day itself.\nNo non-veg.\nCake not from us; they are ordering it separately.",
   {"format": "note", "numbers": ["22", "80", "350", "10,000"], "must_include": ["Pooja's daughter", "22nd", "80 plates", "balance to be paid on the day itself", "No non-veg", "Cake not from us", "separately"], "min_negations": 2},
   "facts: birthday on the 22nd; 80 plates at ₹350/plate (₹ only where rupees spoken); advance 10,000 given, balance on the day (not computed); NO non-veg; cake NOT from caterer, ordered separately",
   pos="before", cx=2)

# 174
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "karthik anna the generator diesel is almost over please refill it today"},
   "Karthik anna, the generator diesel is almost over. Please refill it today.",
   {"must_include": ["Karthik anna", "generator diesel", "almost over", "today"]},
   "facts: generator diesel almost over; refill today; Tamil 'anna' kept")

# 175
R2(CA, {"task": "cleanup",
        "transcript": "the interest on the senior citizen fd is seven point two five percent for one year or seven point five percent for three years and the member can choose monthly payout or cumulative"},
   "The interest on the senior citizen FD is 7.25% for one year or 7.5% for three years, and the member can choose monthly payout or cumulative.",
   {"numbers": ["7.25", "7.5"], "must_include": ["senior citizen FD", "7.25% for one year", "7.5% for three years", "monthly payout or cumulative"]},
   "facts: two rate options kept: 7.25% for one year OR 7.5% for three years; payout choice monthly OR cumulative")

# 176
R2(FN, {"task": "rewrite", "format": "message", "tone": "empathetic",
        "instruction": "she's stressed, make it kind but keep the deadline and the no extension part",
        "transcript": "lakshmi i know the appraisal forms are confusing but the deadline is friday six pm and hr has said there is no extension this time so fill whatever you can and we'll fix the rest together on thursday"},
   "Lakshmi, I know the appraisal forms are confusing, and that's completely understandable. The deadline is Friday 6 p.m., and HR has said there is no extension this time, so just fill in whatever you can, and we'll fix the rest together on Thursday.",
   {"format": "message", "numbers": ["6"], "must_include": ["Lakshmi", "appraisal forms", "Friday 6 p.m.", "no extension this time", "together on Thursday"], "min_negations": 1},
   "facts: appraisal deadline Friday 6 p.m.; NO extension (HR); fill what she can; fix the rest together Thursday (speaker's own offer, dictated); empathetic wording only",
   pos="after", cx=3)

# 177
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "the tuition fee receipt says nine thousand but she paid nineteen thousand"},
   "The tuition fee receipt says 9,000, but she paid 19,000.",
   {"numbers": ["9,000", "19,000"], "must_include": ["tuition fee receipt"]},
   "facts: receipt says 9,000 but she paid 19,000 (mismatch is the point; no currency spoken)")

# 178
R2(CO, {"task": "cleanup",
        "transcript": "aho siddharth dada uh the kirana list for this week is mostly the same as last week but add two kilo poha one kilo sabudana for the fast on thursday and um the pooja samagri kit from the corner shop the small one and nako the big packet of sugar we still have half left from last time and haan check if they have the fresh methi otherwise take palak"},
   "Aho Siddharth dada, the kirana list for this week is mostly the same as last week, but add 2 kilo poha, 1 kilo sabudana for the fast on Thursday, and the pooja samagri kit from the corner shop, the small one. And nako the big packet of sugar; we still have half left from last time. And haan, check if they have the fresh methi, otherwise take palak.",
   {"numbers": ["2", "1"], "must_include": ["Aho Siddharth dada", "kirana list", "2 kilo poha", "1 kilo sabudana", "Thursday", "pooja samagri kit", "the small one", "nako the big packet of sugar", "half left", "haan", "fresh methi", "otherwise take palak"]},
   "facts: add 2 kilo poha, 1 kilo sabudana (fast on Thursday), small pooja samagri kit; do NOT get big sugar packet (Marathi 'nako'), half left; fresh methi if available, otherwise palak; Marathi 'aho', 'dada', 'nako' kept. Waiver: checker ignores a bare spoken 'one' and flags the measurement '1 kilo' as invented",
   waivers=["number_invented"])

# 179
R2(CA, {"task": "cleanup",
        "transcript": "the hotfix can go either tonight after ten or tomorrow early morning before seven but not during business hours because the client is running payroll"},
   "The hotfix can go either tonight after 10 or tomorrow early morning before 7, but not during business hours, because the client is running payroll.",
   {"numbers": ["10", "7"], "must_include": ["tonight after 10", "tomorrow early morning before 7", "not during business hours", "payroll"], "min_negations": 1},
   "facts: alternative kept: tonight after 10 OR tomorrow early morning before 7; NOT during business hours (client running payroll)")

# 180
R2(FN, {"task": "rewrite", "format": "email", "register": "casual", "recipient": "Jignesh bhai",
        "instruction": "casual email, keep both GSTINs and the amount exactly",
        "transcript": "jignesh bhai the purchase bill from your side has the wrong gstin it shows two four a a b c s one two three four f one z five but ours is two four a a b c s one two three four f one z six so please send a revised bill the amount eighty six thousand four hundred is correct only the gstin is wrong"},
   "Hi Jignesh bhai,\n\nThe purchase bill from your side has the wrong GSTIN. It shows 24AABCS1234F1Z5, but ours is 24AABCS1234F1Z6, so please send a revised bill. The amount of 86,400 is correct; only the GSTIN is wrong.",
   {"format": "email", "numbers": ["86,400"], "must_include": ["Jignesh bhai", "wrong GSTIN", "24AABCS1234F1Z5", "24AABCS1234F1Z6", "revised bill", "only the GSTIN is wrong"]},
   "facts: bill shows GSTIN 24AABCS1234F1Z5 (made-up sample format), correct one 24AABCS1234F1Z6; send revised bill; amount 86,400 correct (no currency spoken); no sign-off (no sender, none dictated). Waiver: checker splits the spoken alphanumeric GSTINs into stray numbers",
   pos="after", cx=4, waivers=["number_missing", "number_invented"])

# 181
R2(FN, {"task": "cleanup",
        "transcript": "mohsin the samples are in the brown parcel not the white one"},
   "Mohsin, the samples are in the brown parcel, not the white one.",
   {"must_include": ["Mohsin", "brown parcel", "not the white one"], "min_negations": 1},
   "facts: samples in the brown parcel, NOT the white one")

# 182
R2(CA, {"task": "cleanup",
        "transcript": "for the new crash course batch the fee is twenty two thousand for the full course or eight thousand per month for three months um students who paid for the last crash course get a two thousand discount uh only if they join before the fifteenth and the batch will start on the eighteenth sorry the twenty first if we get at least twenty five students otherwise we will merge it with the regular batch karthik will handle the counselling calls"},
   "For the new crash course batch, the fee is 22,000 for the full course or 8,000 per month for three months. Students who paid for the last crash course get a 2,000 discount, only if they join before the 15th, and the batch will start on the 21st if we get at least 25 students; otherwise, we will merge it with the regular batch. Karthik will handle the counselling calls.",
   {"numbers": ["22,000", "8,000", "2,000", "15", "21", "25"], "must_not_include": ["18th"], "must_include": ["22,000 for the full course or 8,000 per month for three months", "only if they join before the 15th", "the 21st if we get at least 25 students", "otherwise", "merge it with the regular batch", "Karthik"]},
   "facts: fee 22,000 full course OR 8,000/month for three months (both kept, no currency spoken); 2,000 discount for last crash course students ONLY IF they join before the 15th; correction: start on the 21st (18th corrected away) IF at least 25 students, otherwise merged with regular batch; Karthik handles counselling. Waiver: checker gap on 'the eighteenth sorry the twenty first'; transcript kept natural",
   waivers=["number_missing"])

# 183
R2(FN, {"task": "rewrite", "format": "message", "length": "shorter",
        "instruction": "keep the amount, the date and the cash-only rule",
        "transcript": "hello everyone so for the society diwali function the contribution is five hundred rupees per flat and um we are collecting only in cash this year not upi because last year the reconciliation was a big headache so please give it to the wing representative by the twenty fifth"},
   "Hello everyone, the society Diwali function contribution is ₹500 per flat. We're collecting only cash this year, not UPI, since last year's reconciliation was a big headache. Please give it to the wing representative by the 25th.",
   {"format": "message", "numbers": ["500", "25"], "must_include": ["Hello everyone", "Diwali function", "₹500 per flat", "only cash", "not UPI", "wing representative", "25th"], "min_negations": 1},
   "facts: Diwali contribution ₹500/flat; cash only this year, NOT UPI (last year's reconciliation headache); give to wing representative by the 25th; dictated 'hello everyone' kept",
   pos="before", cx=3)

# 184
R2(CO, {"task": "cleanup",
        "transcript": "imran the job worker from pandesara called he needs the thread cones by tomorrow morning otherwise the looms will be idle so send forty cones of the white and twenty of the cream"},
   "Imran, the job worker from Pandesara called. He needs the thread cones by tomorrow morning, otherwise the looms will be idle, so send 40 cones of the white and 20 of the cream.",
   {"numbers": ["40", "20"], "must_include": ["Imran", "Pandesara", "thread cones", "tomorrow morning", "otherwise the looms will be idle", "40 cones of the white", "20 of the cream"]},
   "facts: Pandesara job worker needs thread cones by tomorrow morning, otherwise looms idle; send 40 white and 20 cream cones")

# --- stage 2, chunk 3 (185-225) ---

# 185  [Recipient] header only: no vocative (stage-1 fix for TC-W03-031); politeness must show (fix for TC-W03-040)
R2(CO, {"task": "rewrite", "format": "message", "recipient": "Harsh",
        "instruction": "a bit more polite",
        "transcript": "send me the updated rate list for the linen fabric by evening i need it for the buyer meeting tomorrow"},
   "Could you please send me the updated rate list for the linen fabric by evening? I need it for the buyer meeting tomorrow.",
   {"format": "message", "must_include": ["updated rate list", "linen fabric", "by evening", "buyer meeting tomorrow"], "must_not_include": ["Harsh"]},
   "facts: rate list for linen fabric needed by evening for tomorrow's buyer meeting; politeness visibly added ('Could you please'); no vocative because the speaker never said the name (only [Recipient] has it)",
   pos="after", cx=3)

# 186  'English only' on code-mixed speech = translation: not done; the rest of the instruction is (fix for TC-W03-025)
R2(CO, {"task": "rewrite", "format": "email", "recipient": "Pooja",
        "instruction": "make it a short email to Pooja, English only",
        "transcript": "pooja the coaching centre ka new brochure ready hai i have shared the pdf on drive please check the fee page once aur koi mistake ho toh bata dena by tomorrow"},
   "Hi Pooja,\n\nThe coaching centre ka new brochure ready hai. I have shared the PDF on Drive. Please check the fee page once, aur koi mistake ho toh bata dena by tomorrow.",
   {"format": "email", "must_include": ["Pooja", "ka new brochure ready hai", "PDF on Drive", "fee page once", "aur koi mistake ho toh bata dena", "by tomorrow"]},
   "facts: new brochure ready; PDF shared on Drive; check fee page and report any mistake by tomorrow. 'English only' would be translation (§5, never done): Hinglish words kept exactly, the email/short part is done; no sign-off (no sender)",
   pos="after", cx=3)

# 187
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the courier will come at noon or maybe after lunch he wasn't sure"},
   "The courier will come at noon, or maybe after lunch. He wasn't sure.",
   {"must_include": ["noon", "maybe after lunch", "wasn't sure"], "min_negations": 1},
   "facts: alternative kept: noon OR maybe after lunch; courier was NOT sure (uncertainty kept)")

# 188  AI/code context (spoken tag name, no literal control token: the --tok check rejects '<think>' in targets)
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "divya the support bot is again showing the think tag at the start of replies to customers um karthik said it's because the reasoning mode is on in the config so we need to set enable thinking to false and redeploy uh but don't touch the prod config before the change approval comes through which is probably tomorrow afternoon meanwhile add a filter that strips that tag from the output"},
   "Divya, the support bot is again showing the think tag at the start of replies to customers. Karthik said it's because the reasoning mode is on in the config, so we need to set enable thinking to false and redeploy, but don't touch the prod config before the change approval comes through, which is probably tomorrow afternoon. Meanwhile, add a filter that strips that tag from the output.",
   {"must_include": ["Divya", "again", "the think tag", "Karthik", "reasoning mode", "enable thinking to false", "redeploy", "don't touch the prod config", "change approval", "probably tomorrow afternoon", "filter"], "min_negations": 1},
   "facts: bot again shows the think tag at the start of replies; cause per Karthik: reasoning mode on; set enable thinking false and redeploy; do NOT touch prod config before change approval, hedged 'probably tomorrow afternoon'; meanwhile add a filter stripping the tag")

# 189
R2(FN, {"task": "cleanup",
        "transcript": "the society watchman does not have the terrace key the secretary has it"},
   "The society watchman does not have the terrace key. The secretary has it.",
   {"must_include": ["watchman does not have the terrace key", "secretary has it"], "min_negations": 1},
   "facts: watchman does NOT have terrace key; the secretary has it")

# 190
R2(CA, {"task": "cleanup",
        "transcript": "for next week's tiffin menu monday is dal dhokli tuesday undhiyu no wait sev tameta because undhiyu is too heavy for weekdays wednesday is kadhi khichdi thursday the customers can choose either paneer bhurji or chana masala and friday is the special thali which is fifty rupees extra uh saturday half day only lunch no dinner and sunday closed as usual please put this on the group by saturday evening"},
   "For next week's tiffin menu: Monday is dal dhokli. Tuesday, sev tameta, because undhiyu is too heavy for weekdays. Wednesday is kadhi khichdi. Thursday, the customers can choose either paneer bhurji or chana masala, and Friday is the special thali, which is ₹50 extra. Saturday half day, only lunch, no dinner, and Sunday closed as usual. Please put this on the group by Saturday evening.",
   {"numbers": ["50"], "must_include": ["dal dhokli", "Tuesday, sev tameta", "undhiyu is too heavy for weekdays", "kadhi khichdi", "either paneer bhurji or chana masala", "special thali", "₹50 extra", "only lunch, no dinner", "Sunday closed", "Saturday evening"], "must_not_include": ["Tuesday undhiyu", "Tuesday is undhiyu"], "min_negations": 1},
   "facts: Mon dal dhokli; Tue correction: sev tameta (undhiyu corrected away, reason kept); Wed kadhi khichdi; Thu choice paneer bhurji OR chana masala; Fri special thali ₹50 extra; Sat half day, lunch only, NO dinner; Sun closed; post to group by Saturday evening; kept as prose (no list cues)")

# 191  header fields only
R2(CO, {"task": "rewrite", "format": "message", "register": "casual", "tone": "friendly",
        "transcript": "hey gurpreet congratulations on clearing the ca inter exams yaar that's huge party is on me this weekend"},
   "Hey Gurpreet, congratulations on clearing the CA Inter exams, yaar! That's huge. Party's on me this weekend.",
   {"format": "message", "must_include": ["Hey Gurpreet", "CA Inter", "yaar", "this weekend"]},
   "facts: Gurpreet cleared CA Inter; speaker's own offer: party on the speaker this weekend (dictated); dictated 'hey' kept")

# 192
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "the lift is under maintenance till six pm do not use it"},
   "The lift is under maintenance till 6 p.m. Do not use it.",
   {"numbers": ["6"], "must_include": ["under maintenance", "till 6 p.m.", "Do not use it"], "min_negations": 1},
   "facts: lift under maintenance till 6 p.m.; do NOT use it")

# 193
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the parcel for hetal ben goes by courier sorry by the angadia because courier will take three days and she needs it tomorrow"},
   "The parcel for Hetal ben goes by the angadia, because courier will take three days and she needs it tomorrow.",
   {"must_include": ["Hetal ben", "by the angadia", "three days", "tomorrow"], "must_not_include": ["goes by courier"]},
   "facts: correction applied: parcel goes by angadia (courier corrected away as the method; courier's three days kept as the reason); she needs it tomorrow")

# 194
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Gurpreet Singh", "recipient": "Branch Manager", "header_style": "full",
        "instruction": "keep the cheque numbers and account digits exactly",
        "transcript": "request to stop payment on cheque numbers one four two two one to one four two two five from current account ending three three zero eight as the cheque book was misplaced in transit kindly do not honour any of these five cheques"},
   "Dear Branch Manager,\n\nI request you to stop payment on cheque numbers 14221 to 14225 from current account ending 3308, as the cheque book was misplaced in transit. Kindly do not honour any of these five cheques.\n\nRegards,\nGurpreet Singh",
   {"format": "email", "numbers": ["14221", "14225", "3308"], "must_include": ["Branch Manager", "stop payment", "14221 to 14225", "account ending 3308", "misplaced in transit", "do not honour", "five cheques", "Gurpreet Singh"], "min_negations": 1},
   "facts: stop payment on cheques 14221 to 14225 (five cheques), current account ending 3308; cheque book misplaced in transit; do NOT honour any of them",
   pos="before", cx=4)

# 195  header fields only, excited tone
R2(CO, {"task": "rewrite", "format": "message", "tone": "excited",
        "transcript": "hetal ben the new catalogue photos came out really nice"},
   "Hetal ben, the new catalogue photos came out super nice!",
   {"format": "message", "must_include": ["Hetal ben", "new catalogue photos"]},
   "facts: new catalogue photos came out very nice; excited tone changes wording/punctuation only, nothing added")

# 196
R2(CA, {"task": "cleanup",
        "transcript": "um quick update on the hiring for the data team we had three final candidates siddharth's reference who is from mysore and two from the campus drive uh we've decided to make an offer to the mysore candidate at eighteen lakh no wait eighteen point five lakh fixed because he has a competing offer joining date is either the first of december or the fifteenth depending on his notice period and the other two are on hold not rejected so don't send them any mail yet hr will do the background verification first"},
   "Quick update on the hiring for the data team: we had three final candidates, Siddharth's reference, who is from Mysore, and two from the campus drive. We've decided to make an offer to the Mysore candidate at 18.5 lakh fixed because he has a competing offer. Joining date is either the 1st of December or the 15th, depending on his notice period, and the other two are on hold, not rejected, so don't send them any mail yet. HR will do the background verification first.",
   {"numbers": ["18.5", "1", "15"], "must_not_include": ["18 lakh"], "must_include": ["three final candidates", "Siddharth's reference, who is from Mysore", "two from the campus drive", "18.5 lakh fixed", "competing offer", "either the 1st of December or the 15th", "on hold, not rejected", "don't send them any mail yet", "background verification first"], "min_negations": 2},
   "facts: three finalists (Siddharth's reference from Mysore + two campus); correction: offer 18.5 lakh fixed (18 lakh corrected away; no currency spoken); joining 1st of December OR the 15th depending on notice period; other two on hold, NOT rejected; do NOT mail them yet; HR does background verification first")

# 197  header fields only
R2(FN, {"task": "rewrite", "format": "message", "length": "shorter", "context": "work", "header_style": "full",
        "transcript": "so uh regarding the gst audit i just want to tell you that we are not able to finish the reconciliation by friday because the purchase register from the client has many missing entries like almost sixty to seventy bills are not there so the earliest we can finish is next wednesday and that too only if they send the bills by monday"},
   "We can't finish the GST audit reconciliation by Friday because the client's purchase register has many missing entries; almost 60 to 70 bills are not there. The earliest we can finish is next Wednesday, and only if they send the bills by Monday.",
   {"format": "message", "numbers": ["60", "70"], "must_include": ["GST audit", "by Friday", "purchase register", "almost 60 to 70 bills", "next Wednesday", "only if they send the bills by Monday"], "min_negations": 2},
   "facts: can NOT finish GST reconciliation by Friday; about 60-70 bills missing ('like almost' kept as 'almost'); earliest next Wednesday, ONLY IF bills sent by Monday")

# 198
R2(CO, {"task": "cleanup",
        "transcript": "karthik the wifi password for the guest network is changed check the whiteboard"},
   "Karthik, the Wi-Fi password for the guest network is changed. Check the whiteboard.",
   {"must_include": ["Karthik", "Wi-Fi password", "guest network", "whiteboard"]},
   "facts: guest Wi-Fi password changed; new one on the whiteboard")

# 199
R2(CA, {"task": "cleanup", "header_style": "full",
        "transcript": "the dj for the birthday party wants twelve thousand for three hours or fifteen thousand for four hours we have to tell him by thursday"},
   "The DJ for the birthday party wants 12,000 for 3 hours or 15,000 for 4 hours. We have to tell him by Thursday.",
   {"numbers": ["12,000", "3", "15,000", "4"], "must_include": ["DJ", "birthday party", "by Thursday"]},
   "facts: alternative kept: 12,000 for 3 hours OR 15,000 for 4 hours (no currency spoken); decide by Thursday")

# 200
R2(FN, {"task": "cleanup",
        "transcript": "attention all counter staff there have been two cases this week where customers got calls from people pretending to be from our bank asking for the otp so please tell every customer that the bank never asks for otp or pin on phone uh also the new rule from today any cash withdrawal above fifty thousand from a savings account needs the passbook and an id proof no exceptions even for regular customers and if someone insists send them to mohsin sir don't argue at the counter"},
   "Attention all counter staff: there have been two cases this week where customers got calls from people pretending to be from our bank, asking for the OTP, so please tell every customer that the bank never asks for OTP or PIN on phone. Also, the new rule from today: any cash withdrawal above 50,000 from a savings account needs the passbook and an ID proof, no exceptions, even for regular customers. If someone insists, send them to Mohsin sir; don't argue at the counter.",
   {"numbers": ["50,000"], "must_include": ["two cases this week", "never asks for OTP or PIN", "from today", "above 50,000", "passbook and an ID proof", "no exceptions", "even for regular customers", "Mohsin sir", "don't argue"], "min_negations": 3},
   "facts: two fraud-call cases this week; bank NEVER asks for OTP or PIN on phone; from today, savings cash withdrawal above 50,000 needs passbook + ID proof, NO exceptions even for regulars; if someone insists, send to Mohsin sir, do NOT argue")

# 201  header fields only
R2(CO, {"task": "rewrite", "format": "email", "sender": "Divya", "recipient": "Siddharth", "header_style": "full",
        "transcript": "siddharth sir thank you for taking the extra maths classes last weekend the students really liked your shortcuts for probability uh the feedback forms are on my desk if you want to have a look"},
   "Hi Siddharth sir,\n\nThank you for taking the extra maths classes last weekend. The students really liked your shortcuts for probability. The feedback forms are on my desk if you want to have a look.\n\nBest,\nDivya",
   {"format": "email", "must_include": ["Siddharth sir", "extra maths classes", "last weekend", "shortcuts for probability", "feedback forms", "my desk", "Divya"]},
   "facts: thanks for extra maths classes last weekend; students liked probability shortcuts; feedback forms on the speaker's desk; greeting keeps the dictated 'sir'")

# 202
R2(CA, {"task": "cleanup",
        "transcript": "transfer the amount to the hdfc account i mean the cosmos bank account"},
   "Transfer the amount to the Cosmos Bank account.",
   {"must_include": ["Cosmos Bank account"], "must_not_include": ["HDFC"]},
   "facts: self-correction applied: Cosmos Bank account (HDFC corrected away); cleanup only, no transfer claimed")

# 203
R2(FN, {"task": "cleanup",
        "transcript": "the ration for the old age home donation is ready rice fifty kilo dal twenty kilo oil ten litres but the sugar is not packed yet because the supplier didn't deliver"},
   "The ration for the old age home donation is ready: rice 50 kilo, dal 20 kilo, oil 10 litres, but the sugar is not packed yet because the supplier didn't deliver.",
   {"numbers": ["50", "20", "10"], "must_include": ["old age home donation", "rice 50 kilo", "dal 20 kilo", "oil 10 litres", "sugar is not packed yet", "didn't deliver"], "min_negations": 2},
   "facts: donation ration ready: rice 50 kg, dal 20 kg, oil 10 litres; sugar NOT packed yet because supplier did NOT deliver")

# 204
R2(CA, {"task": "rewrite", "format": "message", "context": "work", "header_style": "full",
        "instruction": "clean message for the team channel, only the corrected names",
        "transcript": "the on call this weekend is anita on saturday and karthik on sunday no wait karthik is on leave so it's aparna on sunday and imran is the backup for both days"},
   "On-call this weekend: Anita on Saturday and Aparna on Sunday, since Karthik is on leave. Imran is the backup for both days.",
   {"format": "message", "must_include": ["On-call this weekend", "Anita on Saturday", "Aparna on Sunday", "Karthik is on leave", "Imran is the backup for both days"], "must_not_include": ["Karthik on Sunday"]},
   "facts: on-call Anita Saturday; correction: Aparna Sunday (Karthik corrected away, on leave, reason kept); Imran backup both days",
   pos="before", cx=3)

# 205
R2(CA, {"task": "cleanup",
        "transcript": "so the summer camp in ooty is confirmed for the under twelve kids we'll leave on the second of may by the nilgiri express no wait by bus because the train tickets are not available and the camp is for six days parents have to pay eighteen thousand which covers stay food and coaching uh but pocket money is extra not more than five hundred rupees please karthik anna will be the in charge and lakshmi akka will travel with the girls"},
   "The summer camp in Ooty is confirmed for the under-12 kids. We'll leave on the 2nd of May by bus because the train tickets are not available, and the camp is for 6 days. Parents have to pay 18,000, which covers stay, food and coaching, but pocket money is extra, not more than ₹500, please. Karthik anna will be the in-charge, and Lakshmi akka will travel with the girls.",
   {"numbers": ["12", "2", "6", "18,000", "500"], "must_not_include": ["Nilgiri Express"], "must_include": ["Ooty", "under-12", "2nd of May", "by bus", "train tickets are not available", "6 days", "stay, food and coaching", "pocket money is extra", "not more than ₹500", "Karthik anna", "Lakshmi akka"], "min_negations": 2},
   "facts: Ooty camp confirmed for under-12; leave 2nd of May, correction: by bus (Nilgiri Express corrected away; train tickets NOT available); camp 6 days; fee 18,000 covers stay, food, coaching (no currency spoken there, so no ₹); pocket money extra, NOT more than ₹500 (rupees spoken); Karthik in charge; Lakshmi travels with the girls")

# 206
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "tds is ten percent on the professional fees not two percent"},
   "TDS is 10% on the professional fees, not 2%.",
   {"numbers": ["10", "2"], "must_include": ["TDS", "professional fees"], "min_negations": 1},
   "facts: TDS 10% on professional fees, NOT 2%")

# 207
R2(CO, {"task": "rewrite", "format": "message", "tone": "warm",
        "instruction": "thank the caterer, warm, but no extra promises",
        "transcript": "rupinder ji the food at my son's birthday was amazing everyone loved the chole and the jalebi i'll send the balance eight thousand today evening"},
   "Rupinder ji, thank you so much! The food at my son's birthday was amazing, and everyone loved the chole and the jalebi. I'll send the balance of 8,000 this evening.",
   {"format": "message", "numbers": ["8,000"], "must_include": ["Rupinder ji", "son's birthday", "chole", "jalebi", "balance of 8,000", "this evening"]},
   "facts: food at son's birthday amazing, everyone loved chole and jalebi; speaker's own commitment: balance 8,000 this evening (dictated); thank-you is for the food the speaker praised, as instructed; nothing else promised",
   pos="after", cx=3)

# 208
R2(CA, {"task": "cleanup",
        "transcript": "please collect the maintenance cheque from flat a one zero one or if they're not home take it from the watchman tomorrow i mean day after tomorrow"},
   "Please collect the maintenance cheque from flat A-101, or if they're not home, take it from the watchman day after tomorrow.",
   {"numbers": ["101"], "must_include": ["maintenance cheque", "A-101", "if they're not home", "watchman", "day after tomorrow"], "must_not_include": ["watchman tomorrow"], "min_negations": 1},
   "facts: collect cheque from A-101, or IF they're NOT home, from the watchman; correction: day after tomorrow (tomorrow corrected away)")

# 209
R2(FN, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Aparna Iyer", "recipient": "Mr. Jignesh Patel",
        "instruction": "formal email, keep the dates, don't add any apology",
        "transcript": "this is to inform that your daughter hetal's fees for the second term of twenty four thousand is pending since the first of october and as per our policy she will not be allowed to appear for the unit test on the twentieth unless the fees is paid or a written request for extension is submitted"},
   "Dear Mr. Jignesh Patel,\n\nThis is to inform you that your daughter Hetal's fees for the second term, amounting to 24,000, have been pending since the 1st of October. As per our policy, she will not be allowed to appear for the unit test on the 20th unless the fees are paid or a written request for an extension is submitted.\n\nRegards,\nAparna Iyer",
   {"format": "email", "numbers": ["24,000", "1", "20"], "must_include": ["Mr. Jignesh Patel", "Hetal", "second term", "24,000", "1st of October", "will not be allowed", "unit test on the 20th", "unless the fees are paid or a written request for an extension is submitted", "Aparna Iyer"], "must_not_include": ["sorry", "apologi"], "min_negations": 1},
   "facts: Hetal's second-term fees 24,000 (no currency spoken) pending since 1st of October; NOT allowed in unit test on the 20th UNLESS fees paid OR written extension request submitted; no apology added",
   pos="after", cx=4)

# 210
R2(CO, {"task": "cleanup",
        "transcript": "lakshmi the dabbawala uniform order is ready pick it up anytime after twelve"},
   "Lakshmi, the dabbawala uniform order is ready. Pick it up anytime after 12.",
   {"numbers": ["12"], "must_include": ["Lakshmi", "dabbawala uniform order", "anytime after 12"]},
   "facts: dabbawala uniform order ready; pick up anytime after 12")

# 211
R2(CA, {"task": "cleanup",
        "transcript": "for the surat textile fair stall we have two options either the corner stall for one lakh twenty thousand or the regular stall for eighty five thousand but the corner one gets more footfall uh jignesh prefers the corner one hetal thinks the regular one is enough we'll decide on monday after we see the exhibitor list and um in either case the booking amount of twenty five thousand has to be paid by the tenth otherwise we lose the slot"},
   "For the Surat textile fair stall, we have two options: either the corner stall for 1,20,000 or the regular stall for 85,000, but the corner one gets more footfall. Jignesh prefers the corner one; Hetal thinks the regular one is enough. We'll decide on Monday after we see the exhibitor list, and in either case, the booking amount of 25,000 has to be paid by the 10th, otherwise we lose the slot.",
   {"numbers": ["1,20,000", "85,000", "25,000", "10"], "must_include": ["Surat textile fair", "either the corner stall", "regular stall", "more footfall", "Jignesh prefers the corner one", "Hetal thinks the regular one is enough", "decide on Monday", "in either case", "by the 10th", "otherwise we lose the slot"]},
   "facts: options corner stall 1,20,000 OR regular 85,000 (both kept, undecided); Jignesh prefers corner, Hetal regular; decide Monday after exhibitor list; either way booking 25,000 by the 10th, otherwise slot lost; no currency spoken")

# 212
R2(FN, {"task": "rewrite", "format": "message", "register": "formal",
        "instruction": "formal wording for the bank's complaint form",
        "transcript": "i didn't get the otp because the registered number is old"},
   "I did not receive the OTP because the registered number is outdated.",
   {"format": "message", "must_include": ["did not receive the OTP", "registered"], "min_negations": 1},
   "facts: OTP NOT received because the registered number is old; formal wording only ('didn't get' -> 'did not receive', 'old' -> 'outdated')",
   pos="before", cx=3)

# 213  header fields only
R2(CO, {"task": "rewrite", "format": "message", "register": "casual",
        "transcript": "machan the team lunch is at the andhra mess near the office at one thirty dont be late ok they don't keep tables for long"},
   "Machan, the team lunch is at the Andhra mess near the office at 1:30. Don't be late, okay? They don't keep tables for long.",
   {"format": "message", "numbers": ["1:30"], "must_include": ["Machan", "Andhra mess", "near the office", "Don't be late", "don't keep tables for long"], "min_negations": 2},
   "facts: team lunch at the Andhra mess near office at 1:30; do NOT be late, they do NOT hold tables long; Tamil 'machan' kept")

# 214
R2(CA, {"task": "rewrite", "format": "email", "sender": "Pooja", "recipient": "Mohsin",
        "instruction": "email, use the corrected price and keep both options",
        "transcript": "mohsin the quotation for the office chairs came in at four thousand two hundred sorry four thousand eight hundred per chair for the mesh back or three thousand six hundred for the plain one we need twenty chairs so let me know which one you prefer before friday"},
   "Hi Mohsin,\n\nThe quotation for the office chairs came in at 4,800 per chair for the mesh back or 3,600 for the plain one. We need 20 chairs, so let me know which one you prefer before Friday.\n\nBest,\nPooja",
   {"format": "email", "numbers": ["4,800", "3,600", "20"], "must_not_include": ["4,200"], "must_include": ["Mohsin", "office chairs", "mesh back", "plain one", "20 chairs", "before Friday", "Pooja"]},
   "facts: correction: mesh back 4,800/chair (4,200 corrected away) OR plain 3,600 (both options kept); need 20 chairs; preference before Friday; no currency spoken",
   pos="after", cx=4)

# 215
R2(CO, {"task": "cleanup",
        "transcript": "aparna the toppers felicitation is on the fifth sunday morning at ten uh call the parents of all the students who scored above ninety five and tell them to come by nine forty five"},
   "Aparna, the toppers' felicitation is on the 5th, Sunday morning at 10. Call the parents of all the students who scored above 95 and tell them to come by 9:45.",
   {"numbers": ["5", "10", "95", "9:45"], "must_include": ["Aparna", "toppers' felicitation", "the 5th", "Sunday morning", "above 95", "by 9:45"]},
   "facts: felicitation on the 5th, Sunday morning at 10; call parents of students above 95; come by 9:45")

# 216  header fields only
R2(FN, {"task": "rewrite", "format": "note", "header_style": "full",
        "transcript": "meeting with the co op bank auditor points the cash book is fine the npa list has three accounts wrongly classified the kyc for twenty two accounts is pending and the locker register is not signed since august"},
   "Meeting with the co-op bank auditor:\nCash book is fine.\nNPA list has three accounts wrongly classified.\nKYC pending for 22 accounts.\nLocker register not signed since August.",
   {"format": "note", "numbers": ["22"], "must_include": ["co-op bank auditor", "Cash book is fine", "three accounts wrongly classified", "22 accounts", "not signed since August"], "min_negations": 1},
   "facts: auditor points: cash book fine; three NPA accounts wrongly classified; KYC pending for 22 accounts; locker register NOT signed since August")

# 217
R2(FN, {"task": "cleanup",
        "transcript": "the dhokla order is for thursday not wednesday and for forty people not thirty"},
   "The dhokla order is for Thursday, not Wednesday, and for 40 people, not 30.",
   {"numbers": ["40", "30"], "must_include": ["dhokla order", "Thursday", "Wednesday"], "min_negations": 2},
   "facts: order for Thursday, NOT Wednesday; 40 people, NOT 30")

# 218
R2(CO, {"task": "rewrite", "format": "message", "tone": "warm",
        "instruction": "more polite and a little warmer, it's for an elderly member",
        "transcript": "uncle your car is parked in the visitor slot again please move it to your own slot by tonight"},
   "Uncle, just a gentle reminder that your car is parked in the visitor slot again. Could you kindly move it to your own slot by tonight?",
   {"format": "message", "must_include": ["Uncle", "visitor slot again", "your own slot", "by tonight"]},
   "facts: car in visitor slot again; move to own slot by tonight; politeness and warmth visibly added; 'Uncle' was dictated",
   pos="after", cx=3)

# 219
R2(CA, {"task": "cleanup",
        "transcript": "bhaiya listen this week's order is a bit different uh toor dal twenty kilo moong dal ten kilo no make that fifteen because the navratri demand is high and chana dal same as last week and for the oil either twelve tins of the groundnut oil or ten tins if the rate is above two thousand five hundred per tin and please don't send the loose masala packets this time send only the sealed ones the customers are complaining"},
   "Bhaiya, listen, this week's order is a bit different. Toor dal 20 kilo, moong dal 15 kilo because the Navratri demand is high, and chana dal same as last week. For the oil, either 12 tins of the groundnut oil, or 10 tins if the rate is above 2,500 per tin. And please don't send the loose masala packets this time; send only the sealed ones. The customers are complaining.",
   {"numbers": ["20", "15", "12", "10", "2,500"], "must_not_include": ["moong dal 10"], "must_include": ["Toor dal 20 kilo", "moong dal 15 kilo", "Navratri", "chana dal same as last week", "either 12 tins", "10 tins if the rate is above 2,500 per tin", "don't send the loose masala", "only the sealed ones"], "min_negations": 1},
   "facts: toor dal 20 kg; correction: moong dal 15 kg (10 corrected away) for Navratri demand; chana dal as last week; oil 12 tins, or 10 tins IF rate above 2,500/tin (condition kept); do NOT send loose masala, sealed only. Waiver: the 'no' in 'no make that' is part of the correction, not a content negation; checker counts it",
   waivers=["negation_lost"])

# 220
R2(FN, {"task": "cleanup", "header_style": "full",
        "transcript": "the client has asked for the source code handover by the thirty first but as per the contract we hand over only after the final payment of six lakh forty thousand is received so please don't share the repo access until finance confirms"},
   "The client has asked for the source code handover by the 31st, but as per the contract, we hand over only after the final payment of 6,40,000 is received, so please don't share the repo access until finance confirms.",
   {"numbers": ["31", "6,40,000"], "must_include": ["source code handover", "by the 31st", "as per the contract", "only after the final payment", "don't share the repo access", "until finance confirms"], "min_negations": 1},
   "facts: client wants handover by the 31st; contract: handover ONLY after final payment 6,40,000 (no currency spoken); do NOT share repo access until finance confirms")

# 221
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "imran bhai salaam the trophy engraving will be done by evening inshallah"},
   "Imran bhai, salaam. The trophy engraving will be done by evening, inshallah.",
   {"must_include": ["Imran bhai", "salaam", "trophy engraving", "by evening", "inshallah"]},
   "facts: trophy engraving done by evening, hedged 'inshallah' (kept)")

# 222
R2(CA, {"task": "rewrite", "format": "message", "header_style": "full",
        "instruction": "message for the society WhatsApp group, keep both slots and the condition",
        "transcript": "the pest control will happen either on saturday morning nine to twelve or sunday afternoon two to five depending on how many flats register by thursday and only flats that register will be covered"},
   "Pest control will happen either on Saturday morning, 9 to 12, or Sunday afternoon, 2 to 5, depending on how many flats register by Thursday. Only flats that register will be covered.",
   {"format": "message", "numbers": ["9", "12", "2", "5"], "must_include": ["either on Saturday morning, 9 to 12", "Sunday afternoon, 2 to 5", "register by Thursday", "Only flats that register will be covered"]},
   "facts: slot Saturday 9-12 OR Sunday 2-5 (both kept), depending on registrations by Thursday; ONLY registered flats covered (standing rule kept as its own sentence)",
   pos="before", cx=2)

# 223
R2(CO, {"task": "cleanup",
        "transcript": "hetal ben aaje branch ma bahu rush che so um the new account forms please keep them ready at counter three uh and the pigmy collection agent jignesh bhai will come at four with the day's collection count it in front of him and give him the receipt and haan the photocopy machine is still not working so send the xerox work to the shop outside"},
   "Hetal ben, aaje branch ma bahu rush che, so the new account forms, please keep them ready at counter 3, and the pigmy collection agent, Jignesh bhai, will come at 4 with the day's collection. Count it in front of him and give him the receipt. And haan, the photocopy machine is still not working, so send the xerox work to the shop outside.",
   {"numbers": ["3", "4"], "must_include": ["Hetal ben", "aaje branch ma bahu rush che", "new account forms", "counter 3", "pigmy collection agent", "Jignesh bhai", "at 4", "in front of him", "receipt", "haan", "still not working", "shop outside"], "min_negations": 1},
   "facts: big rush at branch today (Gujarati kept); keep new account forms ready at counter 3; pigmy agent Jignesh bhai comes at 4, count collection in front of him and give receipt; photocopier STILL NOT working, send xerox work outside")

# 224
R2(FN, {"task": "rewrite", "format": "message", "length": "shorter", "header_style": "full",
        "instruction": "keep the fee amounts and the not-included part exactly",
        "transcript": "so basically parents have been asking about the fees for the new robotics class at the coaching centre it is three thousand five hundred per month and the kit is not included in that the kit is a one time cost of six thousand two hundred which they can pay in two instalments if they want"},
   "Parents have been asking about fees for the new robotics class at the coaching centre: 3,500 per month, kit not included. The kit is a one-time cost of 6,200, payable in two instalments if they want.",
   {"format": "message", "numbers": ["3,500", "6,200"], "must_include": ["Parents have been asking", "robotics class", "3,500 per month", "kit not included", "one-time cost of 6,200", "two instalments if they want"], "min_negations": 1},
   "facts: robotics class 3,500/month, kit NOT included; kit one-time 6,200, optional two instalments; no currency spoken; parents' question kept as framing",
   pos="after", cx=3)

# 225
R2(CO, {"task": "cleanup", "header_style": "full",
        "transcript": "divya the attendance sheet for batch c is missing from the file"},
   "Divya, the attendance sheet for Batch C is missing from the file.",
   {"must_include": ["Divya", "attendance sheet", "Batch C", "missing"]},
   "facts: Batch C attendance sheet missing from the file")


if __name__ == "__main__":
    save(OUT, ROWS)
    print(f"wrote {len(ROWS)} records to {OUT}")
    save(OUT2, ROWS2)
    print(f"wrote {len(ROWS2)} records to {OUT2}")
