"""W08 stage 1 + 2: email bucket (email + multi_constraint slices). Re-run to reproduce W08_s1.jsonl and W08_s2.jsonl exactly.
Stage-2 records live in W08_s2_part*.py (exec'd in order)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W08"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

# Each item: slice, request, target, assertions, note, complexity, [pos], [waivers]
ITEMS = [
    # 1
    dict(slice="email",
         request=dict(task="rewrite", format="email",
                      transcript="let the policyholder know their claim number is four zero two one seven and the assessor visits on thursday"),
         target="Hi,\n\nYour claim number is 40217, and the assessor visits on Thursday.",
         a=dict(numbers=["40217"], must_include=["assessor", "Thursday"], format="email"),
         note="facts: claim number 40217; assessor visits Thursday; no sign-off (no sender)", cx=0),
    # 2
    dict(slice="email",
         request=dict(task="rewrite", format="email", recipient="Meenal", sender="Uma", header_style="full",
                      transcript="ask meenal if she can lead the saturday beach cleanup shift from seven to ten"),
         target="Hi Meenal,\n\nCould you lead the Saturday beach cleanup shift from 7 to 10?\n\nThanks,\nUma",
         a=dict(numbers=["7", "10"], must_include=["Meenal", "Saturday", "beach cleanup", "Uma"], format="email"),
         note="facts: request (question) to lead Saturday beach cleanup shift 7 to 10", cx=0),
    # 3
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", sender="Andre",
                      instruction="formal email, keep the condition exactly as it is, and don't add any apology",
                      transcript="so tell the customer we can send an engineer on friday but only if they confirm someone over eighteen will be at home uh between nine and one and if nobody's there the visit gets cancelled"),
         target="Hello,\n\nWe can send an engineer on Friday, but only if you confirm that someone over 18 will be at home between 9 and 1. If nobody is there, the visit will be cancelled.\n\nRegards,\nAndre",
         a=dict(numbers=["18", "9", "1"], must_include=["Friday", "only if", "engineer", "Andre"], must_not_include=["sorry", "apolog"],
                min_negations=1, format="email"),
         note="facts: Friday visit is conditional ('only if' someone over 18 at home 9 to 1); nobody there -> cancelled; no apology", cx=3, pos="before"),
    # 4
    dict(slice="email",
         request=dict(task="rewrite", format="email", tone="empathetic", sender="Farah",
                      transcript="um write to the residents of green park sector four we're really sorry about the power cut on tuesday night it was caused by a transformer fault and supply was restored by two thirty am"),
         target="Dear residents of Green Park Sector 4,\n\nWe're really sorry about the power cut on Tuesday night. It was caused by a transformer fault, and supply was restored by 2:30 a.m.\n\nRegards,\nFarah",
         a=dict(numbers=["4", "2:30"], must_include=["sorry", "Tuesday night", "transformer fault", "Farah"],
                must_not_include=["compensation", "will not happen again"], format="email"),
         note="facts: dictated apology kept (only that one); power cut Tuesday night; transformer fault; restored by 2:30 a.m.; Sector 4", cx=0),
    # 5
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="confident", recipient="Sophie", sender="Joaquín",
                      instruction="sound sure of ourselves but keep the probably",
                      transcript="the draft market sizing deck will probably be ready by wednesday evening"),
         target="Hi Sophie,\n\nThe draft market sizing deck will probably be ready by Wednesday evening.\n\nBest,\nJoaquín",
         a=dict(must_include=["probably", "market sizing deck", "Wednesday evening", "Sophie", "Joaquín"], format="email"),
         note="facts: Wednesday evening is hedged 'probably' and must stay hedged despite confident tone", cx=2, pos="after"),
    # 6
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", locale="en-in", sender="Lerato Naidoo", header_style="full",
                      transcript="hi so this is for mr gaurav sethi regarding his motor claim uh the surveyor has approved one lakh twenty thousand rupees for the bumper and headlight repair the remaining eighteen thousand five hundred rupees is not covered because it's for the paint upgrade which was not part of the original policy uh the amount will be credited to his account within seven working days once he signs the discharge voucher and please also tell him he has to keep the original bills"),
         target="Dear Mr. Gaurav Sethi,\n\nRegarding your motor claim, the surveyor has approved ₹1,20,000 for the bumper and headlight repair. The remaining ₹18,500 is not covered because it is for the paint upgrade, which was not part of the original policy.\n\nThe amount will be credited to your account within 7 working days once you sign the discharge voucher. You also have to keep the original bills.\n\nRegards,\nLerato Naidoo",
         a=dict(numbers=["1,20,000", "18,500", "7"], must_include=["Gaurav Sethi", "surveyor", "paint upgrade", "discharge voucher", "original bills", "Lerato Naidoo"],
                min_negations=2, format="email"),
         note="facts: ₹1,20,000 approved (bumper+headlight); ₹18,500 not covered (paint upgrade, not in policy); credit within 7 working days ONCE he signs voucher (condition); must keep original bills", cx=0),
    # 7
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", recipient="Andre", sender="Uma",
                      rules=["Always sign off with 'Warm regards'.", "Use British spelling."],
                      instruction="just sign off with Thanks this time and keep it short",
                      length="shorter",
                      transcript="andre the volunteer orientation is moved to the community centre hall on the twelfth starting at ten thirty please bring your id card and wear comfortable shoes we'll organize lunch for everyone"),
         target="Hi Andre,\n\nThe volunteer orientation has moved to the community centre hall on the 12th, starting at 10:30. Please bring your ID card and wear comfortable shoes. We'll organise lunch for everyone.\n\nThanks,\nUma",
         a=dict(numbers=["12", "10:30"], must_include=["Andre", "centre", "organise", "ID card", "Thanks", "Uma"], must_not_include=["Warm regards", "organize"], format="email"),
         note="facts: orientation moved to community centre hall, 12th, 10:30; bring ID, comfortable shoes; lunch organised. Instruction 'Thanks' overrides sign-off rule; British spelling rule still applies", cx=2, pos="after"),
    # 8
    dict(slice="email",
         request=dict(task="rewrite", format="email", header_style="full",
                      transcript="subject line planned maintenance then say broadband service in your area will be down from midnight to four am on sunday"),
         target="Subject: Planned maintenance\n\nHi,\n\nBroadband service in your area will be down from midnight to 4 a.m. on Sunday.",
         a=dict(numbers=["4"], must_include=["Subject: Planned maintenance", "midnight", "Sunday"], format="email"),
         note="facts: dictated subject 'planned maintenance'; outage midnight to 4 a.m. Sunday", cx=0),
    # 9
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", tone="friendly", sender="Sophie Laurent",
                      instruction="keep every not in there and add a subject line about the steering committee",
                      transcript="um so for thursday's steering committee we are not presenting the cost model yet uh the client hasn't shared the payroll data and we don't want to show numbers we can't stand behind the agenda is just the interview findings and the next steps"),
         target="Subject: Thursday's steering committee\n\nHello,\n\nFor Thursday's steering committee, we are not presenting the cost model yet. The client hasn't shared the payroll data, and we don't want to show numbers we can't stand behind. The agenda is just the interview findings and the next steps.\n\nKind regards,\nSophie Laurent",
         a=dict(must_include=["Subject:", "steering committee", "cost model", "payroll data", "interview findings", "next steps", "Sophie Laurent"],
                min_negations=4, format="email"),
         waivers=["invented_subject"],
         note="facts: 4 negations (not presenting, hasn't shared, don't want, can't stand behind); agenda = interview findings + next steps. Subject line requested by the instruction (contract 7.3), checker only sees transcript so invented_subject waived", cx=3, pos="before"),
    # 10
    dict(slice="email",
         request=dict(task="rewrite", format="email",
                      transcript="hi team the signed claim forms for the warehouse fire should go to farah no wait they should go to joaquín in underwriting not to the branch office"),
         target="Hi team,\n\nThe signed claim forms for the warehouse fire should go to Joaquín in underwriting, not to the branch office.",
         a=dict(must_include=["Joaquín", "underwriting", "warehouse fire"], must_not_include=["Farah"], min_negations=1, format="email"),
         note="facts: self-correction Farah -> Joaquín (underwriting); negation 'not to the branch office' kept", cx=0),
    # 11
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", tone="warm", locale="en-in", sender="Gaurav",
                      instruction="polite but warm, keep the rupee amount and dates exactly, and don't promise a refund",
                      transcript="okay so reply to mrs meenal joshi about her electricity bill uh her september bill came to four thousand eight hundred and sixty rupees which is higher because the meter reading for august was estimated not actual so the september reading includes the units from both months um there's no error in the bill as such but if she still wants we can do a free meter test the request has to be raised before the thirtieth of october and the technician usually visits within three to four days"),
         target="Dear Mrs. Meenal Joshi,\n\nYour September electricity bill came to ₹4,860. It is higher because the meter reading for August was estimated, not actual, so the September reading includes the units from both months.\n\nThere is no error in the bill as such, but if you would still like, we can do a free meter test. The request has to be raised before October 30, and the technician usually visits within 3 to 4 days.\n\nKind regards,\nGaurav",
         a=dict(numbers=["4,860", "30", "3", "4"], must_include=["Meenal Joshi", "estimated", "free meter test", "usually", "Gaurav"],
                must_not_include=["refund"], min_negations=2, format="email"),
         note="facts: ₹4,860; August reading estimated not actual; no error; meter test only 'if she still wants'; raise before Oct 30; technician 'usually' within 3 to 4 days; no refund promise", cx=3, pos="before"),
    # 12
    dict(slice="email",
         request=dict(task="rewrite", format="email", sender="Meenal", header_style="full",
                      transcript="tell andre the client call moved to three pm"),
         target="Hi Andre,\n\nThe client call has moved to 3 p.m.\n\nBest,\nMeenal",
         a=dict(numbers=["3"], must_include=["Andre", "client call", "Meenal"], format="email"),
         note="facts: recipient Andre named in transcript; call moved to 3 p.m.", cx=0),
    # 13
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", recipient="Lerato", sender="Joaquín Ortega", header_style="full",
                      instruction="keep it brief and don't make the start date sound guaranteed",
                      transcript="we can start the fieldwork on monday only if the signed sow comes back by friday otherwise it slips to the week after"),
         target="Dear Lerato,\n\nWe can start the fieldwork on Monday only if the signed SOW comes back by Friday. Otherwise, it slips to the week after.\n\nRegards,\nJoaquín Ortega",
         a=dict(must_include=["Monday", "only if", "SOW", "Friday", "Otherwise", "week after", "Joaquín Ortega"], must_not_include=["guarantee", "will start"], format="email"),
         note="facts: Monday start is conditional on signed SOW by Friday; otherwise slips to the week after", cx=2, pos="after"),
    # 14
    dict(slice="email",
         request=dict(task="rewrite", format="email", sender="Farah",
                      transcript="hey so this is to all the weekend tutors um thank you for showing up last saturday we had forty two kids which is our biggest turnout so far uh two things for next week the session starts at nine thirty not nine because the hall is booked before us and we need at least six sorry eight volunteers for the maths corner since two people dropped out uh also if anyone has old notebooks or pencils bring them we're running low oh and parking is not allowed in the lane behind the hall"),
         target="Hi everyone,\n\nThank you for showing up last Saturday. We had 42 kids, which is our biggest turnout so far.\n\nTwo things for next week: the session starts at 9:30, not 9, because the hall is booked before us, and we need at least 8 volunteers for the maths corner since two people dropped out.\n\nAlso, if anyone has old notebooks or pencils, please bring them, as we're running low. Parking is not allowed in the lane behind the hall.\n\nThanks,\nFarah",
         a=dict(numbers=["42", "9:30", "8"], must_include=["maths corner", "notebooks", "pencils", "lane behind the hall", "Farah"],
                must_not_include=["6"], min_negations=2, format="email"),
         note="facts: 42 kids last Saturday; session 9:30 not 9; volunteers corrected six -> 8 (two dropped out); bring notebooks/pencils if anyone has them; no parking in lane behind hall", cx=0),
    # 15
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", sender="Sophie",
                      rules=["Use British spelling.", "Always sign off with 'Kind regards'."],
                      instruction="a bit friendlier",
                      transcript="your new fibre router has been dispatched and should arrive in two to three days"),
         target="Hi,\n\nJust a quick note to let you know that your new fibre router has been dispatched and should arrive in 2 to 3 days.\n\nKind regards,\nSophie",
         a=dict(numbers=["2", "3"], must_include=["fibre router", "dispatched", "should arrive", "Kind regards", "Sophie"], format="email"),
         note="facts: router dispatched; 'should arrive' (hedged) in 2 to 3 days; rules: British spelling + 'Kind regards' both apply", cx=1, pos="after"),
    # 16
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", recipient="Mr. Andre Costa", sender="Uma Iyer",
                      transcript="the claim for water damage to the basement has been declined because the policy excludes gradual seepage uh the customer can appeal within thirty days by writing to the grievance cell"),
         target="Dear Mr. Andre Costa,\n\nYour claim for water damage to the basement has been declined because the policy excludes gradual seepage. You can appeal within 30 days by writing to the grievance cell.\n\nRegards,\nUma Iyer",
         a=dict(numbers=["30"], must_include=["Andre Costa", "declined", "gradual seepage", "grievance cell", "Uma Iyer"],
                must_not_include=["sorry", "apolog", "regret"], format="email"),
         note="facts: claim declined (gradual seepage exclusion); appeal within 30 days via grievance cell; no apology was dictated so none added", cx=0),
    # 17
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", length="shorter", recipient="Gaurav", sender="Sophie",
                      instruction="keep my hedges and don't make it sound final",
                      transcript="um i think the interviews with the plant managers might slip to next week i'm not sure yet because two of them are travelling so don't block the calendar for the workshop just yet"),
         target="Hi Gaurav,\n\nI think the plant manager interviews might slip to next week. I'm not sure yet, as two of them are travelling, so don't block the calendar for the workshop just yet.\n\nBest,\nSophie",
         a=dict(must_include=["I think", "might", "next week", "not sure", "workshop", "Gaurav", "Sophie"], min_negations=2, format="email"),
         note="facts: hedged 'I think' + 'might slip to next week'; not sure yet; two managers travelling; don't block workshop calendar yet", cx=3, pos="before"),
    # 18
    dict(slice="email",
         request=dict(task="rewrite", format="email", locale="en-in", header_style="full",
                      transcript="inform the customer their broadband plan has been upgraded to two hundred mbps at the same price of nine ninety nine rupees per month"),
         target="Hi,\n\nYour broadband plan has been upgraded to 200 Mbps at the same price of ₹999 per month.",
         a=dict(numbers=["200", "999"], must_include=["Mbps", "same price", "per month"], format="email"),
         note="facts: upgraded to 200 Mbps; same price ₹999 per month", cx=0),
    # 19
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", tone="friendly", locale="en-in", sender="Meenal Rao", header_style="full",
                      instruction="formal but friendly, keep the apology, and keep the timings exactly",
                      transcript="hi so this goes to the residents welfare association of lake view towers um we apologise for the meter replacement drive getting postponed the new date is the eighteenth no wait the nineteenth sunday our team will be there from eight am to five pm each flat takes about twenty minutes and power will be off only during that time residents don't need to be home if they leave the meter cabinet key with the security desk"),
         target="Dear members of the Lake View Towers Residents' Welfare Association,\n\nWe apologise for the meter replacement drive being postponed. The new date is Sunday the 19th, and our team will be there from 8 a.m. to 5 p.m.\n\nEach flat takes about 20 minutes, and power will be off only during that time. Residents don't need to be home if they leave the meter cabinet key with the security desk.\n\nKind regards,\nMeenal Rao",
         a=dict(numbers=["19", "8", "5", "20"], must_include=["apologise", "Lake View Towers", "Sunday", "security desk", "Meenal Rao"],
                must_not_include=["18th"], min_negations=1, format="email"),
         note="facts: dictated apology kept; date corrected 18th -> 19th (Sunday); 8 a.m. to 5 p.m.; about 20 min per flat; power off only then; residents needn't be home IF key left at security desk", cx=3, pos="after"),
    # 20
    dict(slice="email",
         request=dict(task="rewrite", format="email", recipient="Lerato",
                      transcript="can you check with joaquín whether the donated laptops have been wiped we can't hand them to the trainees until that's done"),
         target="Hi Lerato,\n\nCould you check with Joaquín whether the donated laptops have been wiped? We can't hand them to the trainees until that's done.",
         a=dict(must_include=["Lerato", "Joaquín", "donated laptops", "wiped", "trainees"], min_negations=1, format="email"),
         note="facts: recipient is Lerato (field); Joaquín is a third party named in transcript; can't hand laptops over until wiped", cx=0),
    # 21
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="friendly", sender="Andre",
                      instruction="friendly, under 40 words, no extra offers",
                      transcript="your travel insurance claim for the delayed baggage has been approved for three hundred and twenty dollars"),
         target="Hi,\n\nGood news: your travel insurance claim for the delayed baggage has been approved for $320.\n\nBest,\nAndre",
         a=dict(numbers=["320"], must_include=["delayed baggage", "approved", "Andre"], must_not_include=["happy to help", "let me know"], max_words=40, format="email"),
         note="facts: travel insurance delayed-baggage claim approved for $320; no offers", cx=3, pos="before"),
    # 22
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", sender="Joaquín",
                      instruction="use bullets for the three workstreams, keep the risk as its own line after them, and keep it professional",
                      transcript="okay update for the client team on the retail project uh three workstreams pricing is done and the final recommendations went out on monday the store footprint analysis is about seventy percent complete we're waiting on rent data for twelve stores and the customer survey closes on the twenty fifth we have around eleven hundred responses so far the only risk is the rent data if it doesn't come by friday the footprint piece moves to next month"),
         target="Hi,\n\nHere is an update on the retail project across the three workstreams:\n\n- Pricing: done, and the final recommendations went out on Monday.\n- Store footprint analysis: about 70% complete. We're waiting on rent data for 12 stores.\n- Customer survey: closes on the 25th, with around 1,100 responses so far.\n\nThe only risk is the rent data: if it doesn't come by Friday, the footprint piece moves to next month.\n\nBest,\nJoaquín",
         a=dict(numbers=["70", "12", "25", "1,100"], must_include=["- Pricing", "Monday", "rent data", "Friday", "next month", "Joaquín"], min_negations=1, format="email"),
         note="facts: pricing done, recs out Monday; footprint about 70%, waiting on rent data for 12 stores; survey closes 25th, around 1,100 responses; risk conditional: if rent data not by Friday -> footprint moves to next month", cx=3, pos="after"),
    # 23
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="warm", recipient="Meenal", sender="Gaurav",
                      rules=["Always open with 'Dear <name>'.", "Sign off with 'Warm regards'."],
                      instruction="start with Hi instead of Dear this time",
                      transcript="the food drive collected three hundred and forty kilos of rice and dal this weekend which is double last year thank you to everyone who sorted packets till late"),
         target="Hi Meenal,\n\nThe food drive collected 340 kilos of rice and dal this weekend, which is double last year. Thank you to everyone who sorted packets till late.\n\nWarm regards,\nGaurav",
         a=dict(numbers=["340"], must_include=["Hi Meenal", "rice and dal", "double last year", "Warm regards", "Gaurav"], must_not_include=["Dear"], format="email"),
         note="facts: 340 kilos rice and dal, double last year; instruction 'Hi' overrides the 'Dear' rule, 'Warm regards' rule still applies", cx=1, pos="after"),
    # 24
    dict(slice="email",
         request=dict(task="rewrite", format="email",
                      transcript="let the customer know the duplicate charge of fifteen dollars has been reversed thanks"),
         target="Hi,\n\nThe duplicate charge of $15 has been reversed.\n\nThanks,",
         a=dict(numbers=["15"], must_include=["duplicate charge", "reversed", "Thanks"], format="email"),
         note="facts: duplicate $15 charge reversed; dictated closing 'thanks' kept without a name (no sender)", cx=0),
    # 25
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="friendly", sender="Farah", header_style="full",
                      instruction="friendly email, keep both restrictions, and sign it from me",
                      transcript="tell sophie the hail damage claim on her car is approved but the windscreen is under a separate policy so that part isn't included and she shouldn't book the repair until the surveyor's report is uploaded"),
         target="Hi Sophie,\n\nThe hail damage claim on your car is approved. The windscreen is under a separate policy, so that part isn't included, and you shouldn't book the repair until the surveyor's report is uploaded.\n\nBest,\nFarah",
         a=dict(must_include=["Sophie", "hail damage", "windscreen", "separate policy", "surveyor's report", "Farah"], min_negations=2, format="email"),
         note="facts: hail claim approved; windscreen separate policy, not included; shouldn't book repair until surveyor's report uploaded", cx=3, pos="before"),
    # 26
    dict(slice="email",
         request=dict(task="rewrite", format="email", locale="en-in", sender="Uma",
                      transcript="hello everyone so the blood donation camp at the rotary hall is confirmed for sunday the ninth from ten am to four pm uh donors should be between eighteen and sixty five years and weigh at least fifty kgs um please do not come if you have had a tattoo in the last six months we are expecting around one fifty donors so we need twelve volunteers for registration and refreshments kindly reply by thursday if you can make it"),
         target="Hello everyone,\n\nThe blood donation camp at the Rotary Hall is confirmed for Sunday the 9th, from 10 a.m. to 4 p.m. Donors should be between 18 and 65 years old and weigh at least 50 kg. Please do not come if you have had a tattoo in the last 6 months.\n\nWe are expecting around 150 donors, so we need 12 volunteers for registration and refreshments. Kindly reply by Thursday if you can make it.\n\nThanks,\nUma",
         a=dict(numbers=["9", "10", "4", "18", "65", "50", "6", "150", "12"], must_include=["Rotary Hall", "tattoo", "Kindly reply by Thursday", "Uma"],
                min_negations=1, format="email"),
         note="facts: Sunday 9th, 10 a.m.-4 p.m.; donors 18-65 yrs, min 50 kg; do not come if tattoo in last 6 months; around 150 donors; need 12 volunteers; reply by Thursday if available", cx=0),
    # 27
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", length="longer", locale="en-in", recipient="Meenal", sender="Lerato Dube",
                      instruction="don't change the fee and keep phase two optional",
                      transcript="proposal for the cement client is attached fees are fourteen lakh rupees plus gst phase two is optional"),
         target="Dear Meenal,\n\nPlease find attached the proposal for the cement client. The proposed fees are ₹14,00,000 plus GST. Please note that phase two is optional.\n\nRegards,\nLerato Dube",
         a=dict(numbers=["14,00,000"], must_include=["cement client", "GST", "phase two is optional", "Lerato Dube"], format="email"),
         note="facts: proposal attached; fees ₹14,00,000 (14 lakh) plus GST; phase two optional; longer = fuller sentences only", cx=2, pos="after"),
    # 28
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", header_style="full",
                      transcript="confirm receipt of the policy renewal premium for policy number eight eight one two"),
         target="Hello,\n\nWe confirm receipt of the policy renewal premium for policy number 8812.",
         a=dict(numbers=["8812"], must_include=["renewal premium", "policy number"], format="email"),
         note="facts: renewal premium received for policy 8812", cx=0),
    # 29
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="warm", sender="Joaquín",
                      instruction="warm but professional, and don't add anything we didn't commit to",
                      transcript="hi farah thanks for signing up for the mentoring programme you've been matched with two mentees from the commerce batch um the kickoff call is on the fourteenth at six pm on zoom we'll send the link a day before uh we'll reimburse your travel scratch that there's no travel since it's all online sessions are an hour every alternate week and we ask mentors to commit for at least four months"),
         target="Hi Farah,\n\nThanks for signing up for the mentoring programme. You've been matched with two mentees from the commerce batch.\n\nThe kickoff call is on the 14th at 6 p.m. on Zoom, and we'll send the link a day before. There's no travel, since it's all online. Sessions are an hour every alternate week, and we ask mentors to commit for at least four months.\n\nWarm regards,\nJoaquín",
         a=dict(numbers=["14", "6"], must_include=["Farah", "two mentees", "Zoom", "no travel", "four months", "Joaquín"],
                must_not_include=["reimburse"], min_negations=1, format="email"),
         note="facts: travel reimbursement retracted ('scratch that') -> no travel, all online; 2 mentees; kickoff 14th 6 p.m. Zoom; link a day before; sessions an hour, alternate weeks; commit at least 4 months", cx=2, pos="before"),
    # 30
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", locale="en-in", sender="Accounts Team", header_style="full",
                      transcript="subject line final reminder your connection will be suspended on the fifth unless the outstanding amount of two thousand one hundred and forty rupees is paid"),
         target="Subject: Final reminder\n\nHello,\n\nYour connection will be suspended on the 5th unless the outstanding amount of ₹2,140 is paid.\n\nRegards,\nAccounts Team",
         a=dict(numbers=["5", "2,140"], must_include=["Subject: Final reminder", "unless", "suspended", "Accounts Team"], format="email"),
         note="facts: dictated subject 'final reminder'; suspension on the 5th is conditional ('unless' ₹2,140 paid)", cx=0),
    # 31
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="casual",
                      instruction="email to Uma, no sign-off",
                      transcript="the deck's in the shared drive and slide nine still needs the benchmark numbers"),
         target="Hi Uma,\n\nThe deck's in the shared drive, and slide 9 still needs the benchmark numbers.",
         a=dict(numbers=["9"], must_include=["Hi Uma", "shared drive", "benchmark numbers"], format="email"),
         note="facts: deck in shared drive; slide 9 still needs benchmark numbers; recipient from instruction; no sign-off", cx=2, pos="before"),
    # 32
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", locale="en-gb", recipient="Ms. Uma Krishnan", sender="Sophie Martin",
                      rules=["Use British spelling.", "Sign off with 'Yours sincerely'."],
                      transcript="regarding the inpatient claim for your knee surgery uh we've received the discharge summary and the final bill but we're still missing the pharmacy receipts and the surgeon's prescription without these we can't process the claim the deadline to submit them is the twenty eighth of november if they're not received by then the claim will be closed and you'd have to file a fresh one please note the room rent is capped at five thousand per day under your plan so the amount above that won't be reimbursed"),
         target="Dear Ms. Uma Krishnan,\n\nRegarding the inpatient claim for your knee surgery, we have received the discharge summary and the final bill, but we are still missing the pharmacy receipts and the surgeon's prescription. Without these, we cannot process the claim.\n\nThe deadline to submit them is 28 November. If they are not received by then, the claim will be closed and you would have to file a fresh one.\n\nPlease note that room rent is capped at 5,000 per day under your plan, so the amount above that will not be reimbursed.\n\nYours sincerely,\nSophie Martin",
         a=dict(numbers=["28", "5,000"], must_include=["Uma Krishnan", "pharmacy receipts", "surgeon's prescription", "November", "Yours sincerely", "Sophie Martin"],
                min_negations=4, format="email"),
         note="facts: received discharge summary + final bill; missing pharmacy receipts + prescription; can't process without; deadline 28 November; if not received -> closed, file fresh; room rent capped 5,000/day (no currency spoken), excess not reimbursed", cx=0),
    # 33
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", tone="friendly",
                      instruction="add a short subject line, keep it friendly, and keep the speed numbers exactly",
                      transcript="hey joaquín your speed test results came back at forty mbps download and eight upload which is below the hundred mbps on your plan uh we've reset the port remotely can you run the test again tonight and send us the screenshot"),
         target="Subject: Your speed test results\n\nHi Joaquín,\n\nYour speed test results came back at 40 Mbps download and 8 upload, which is below the 100 Mbps on your plan. We've reset the port remotely. Could you run the test again tonight and send us the screenshot?",
         a=dict(numbers=["40", "8", "100"], must_include=["Subject:", "Joaquín", "reset the port", "tonight", "screenshot"], format="email"),
         waivers=["invented_subject"],
         note="facts: 40 Mbps down, 8 up, below 100 Mbps plan; port reset remotely; asks to rerun tonight and send screenshot. Subject requested by instruction (contract 7.3), checker only sees transcript so invented_subject waived", cx=3, pos="after"),
    # 34
    dict(slice="email",
         request=dict(task="rewrite", format="email", tone="warm", sender="Andre", header_style="full",
                      transcript="thanks meenal for pulling the benchmark data together over the weekend"),
         target="Hi Meenal,\n\nThank you for pulling the benchmark data together over the weekend.\n\nBest,\nAndre",
         a=dict(must_include=["Meenal", "benchmark data", "weekend", "Andre"], format="email"),
         note="facts: thanks Meenal for benchmark data over the weekend; nothing added", cx=0),
    # 35
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", tone="friendly", locale="en-in", sender="Uma", header_style="full",
                      rules=["Always sign off with 'Warm regards'."],
                      instruction="formal and friendly, keep every amount, and don't promise the timeline",
                      transcript="hi lerato quick update on the cost reduction study for the textile mill uh we've identified savings of around eighty lakh sorry ninety lakh rupees a year mainly from energy and procurement energy is about thirty five lakh rupees and the rest is procurement the numbers are still preliminary we'll only be able to confirm them after the plant visit next week so please don't share them with the board yet"),
         target="Dear Lerato,\n\nHere is a quick update on the cost reduction study for the textile mill. We have identified savings of around ₹90,00,000 a year, mainly from energy and procurement. Energy accounts for about ₹35,00,000, and the rest is procurement.\n\nThe numbers are still preliminary. We will only be able to confirm them after the plant visit next week, so please don't share them with the board yet.\n\nWarm regards,\nUma",
         a=dict(numbers=["90,00,000", "35,00,000"], must_include=["Lerato", "textile mill", "preliminary", "plant visit", "board", "Warm regards", "Uma"],
                must_not_include=["80"], min_negations=1, format="email"),
         note="facts: savings corrected 80 lakh -> ₹90,00,000/yr; energy about ₹35,00,000, rest procurement; preliminary, confirm only after plant visit next week; don't share with board yet", cx=3, pos="before"),
    # 36
    dict(slice="email",
         request=dict(task="rewrite", format="email", recipient="Andre", sender="Meenal",
                      transcript="sorry we couldn't send the volunteer certificates last week the printer broke we'll probably have them ready by the end of this month"),
         target="Hi Andre,\n\nSorry we couldn't send the volunteer certificates last week; the printer broke. We'll probably have them ready by the end of this month.\n\nBest,\nMeenal",
         a=dict(must_include=["Sorry", "volunteer certificates", "printer broke", "probably", "end of this month", "Meenal"], min_negations=1, format="email"),
         note="facts: dictated apology kept; certificates not sent last week (printer broke); 'probably' ready by end of this month (hedged)", cx=0),
    # 37
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", wording="keep",
                      instruction="make it an email to Gaurav but keep my exact words, just add the greeting",
                      transcript="uh the policy lapsed on the third because the auto debit failed twice it can be revived within sixty days without a fresh medical check"),
         target="Hi Gaurav,\n\nThe policy lapsed on the 3rd because the auto debit failed twice. It can be revived within 60 days without a fresh medical check.",
         a=dict(numbers=["3", "60"], must_include=["Hi Gaurav", "auto debit failed twice", "revived within 60 days", "without a fresh medical check"], min_negations=1, format="email"),
         note="facts: lapsed on the 3rd, auto debit failed twice; revivable within 60 days without fresh medical check; wording kept", cx=2, pos="after"),
    # 38
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="formal", recipient="Ms. Farah Haddad", sender="Joaquín Ruiz",
                      transcript="the partner review is scheduled for nine am on monday the sixth please send the revised model by friday"),
         target="Dear Ms. Farah Haddad,\n\nThe partner review is scheduled for 9 a.m. on Monday the 6th. Please send the revised model by Friday.\n\nRegards,\nJoaquín Ruiz",
         a=dict(numbers=["9", "6"], must_include=["Farah Haddad", "partner review", "Monday", "revised model", "Friday", "Joaquín Ruiz"], format="email"),
         note="facts: partner review 9 a.m. Monday the 6th; revised model due Friday", cx=0),
    # 39
    dict(slice="multi_constraint",
         request=dict(task="rewrite", format="email", register="formal", tone="empathetic", locale="en-in", sender="Uma",
                      instruction="empathetic but formal, keep both credit options and the default, and don't apologise",
                      transcript="okay reply to mr andre pinto about the broadband outage complaint um his area had an outage from the eleventh to the thirteenth because of a cut fibre cable during road work by the municipality we can give him a credit of either three days or a flat two hundred rupees on the next bill whichever he prefers he needs to reply to choose otherwise we'll apply the three day credit by default we cannot waive the full month's rental since the outage was not for the whole month"),
         target="Dear Mr. Andre Pinto,\n\nRegarding your broadband outage complaint, your area had an outage from the 11th to the 13th because a fibre cable was cut during road work by the municipality.\n\nWe can give you a credit of either three days or a flat ₹200 on your next bill, whichever you prefer. Please reply to choose; otherwise, we will apply the three-day credit by default.\n\nWe cannot waive the full month's rental, since the outage was not for the whole month.\n\nRegards,\nUma",
         a=dict(numbers=["11", "13", "200"], must_include=["Andre Pinto", "either three days", "whichever you prefer", "by default", "municipality", "Uma"],
                must_not_include=["sorry", "apolog"], min_negations=2, format="email"),
         note="facts: outage 11th-13th (cut fibre, municipal road work); alternative kept: 3-day credit OR flat ₹200; must reply to choose, otherwise 3-day default; cannot waive full month (outage not whole month); no apology", cx=3, pos="after"),
    # 40
    dict(slice="email",
         request=dict(task="rewrite", format="email", register="casual",
                      transcript="hey meenal no wait this is for uma can you bring the banner and the registration sheets to the park tomorrow by eight thirty"),
         target="Hi Uma,\n\nCan you bring the banner and the registration sheets to the park tomorrow by 8:30?",
         a=dict(numbers=["8:30"], must_include=["Hi Uma", "banner", "registration sheets", "tomorrow"], must_not_include=["Meenal"], format="email"),
         note="facts: recipient self-corrected Meenal -> Uma; bring banner + registration sheets to park tomorrow by 8:30", cx=0),
]


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def build():
    rows = []
    for i, it in enumerate(ITEMS, 1):
        req = it["request"]
        pos = it.get("pos", "structured" if not req.get("instruction") else "before")
        meta = {"command_position": pos, "instruction_complexity": it["cx"], "length_class": length_class(req["transcript"])}
        rows.append(rec(f"TC-{WID}-{i:03d}", "email", it["slice"], req, it["target"], it["a"], f"{WID.lower()}-sc-{i:03d}",
                        author=WID, note=it.get("note"), waivers=it.get("waivers"), meta=meta))
    return rows


# ---------------------------------------------------------------- stage 2 (TC-W08-101...)
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
S2 = []


def E(sl, transcript, target, *, note=None, cx=0, pos=None, waivers=None, nums=None, inc=None, notinc=None,
      neg=None, one_of=None, maxw=None, full=None, **req):
    """Queue one stage-2 record (task rewrite, format email unless overridden)."""
    S2.append(dict(sl=sl, transcript=transcript, target=target, note=note, cx=cx, pos=pos, waivers=waivers, nums=nums,
                   inc=inc, notinc=notinc, neg=neg, one_of=one_of, maxw=maxw, full=full, req=req))


def build_s2():
    for part in sorted(f for f in os.listdir(HERE) if f.startswith("W08_s2_part") and f.endswith(".py")):
        exec(open(os.path.join(HERE, part), encoding="utf-8").read(), {"E": E})
    rows = []
    for i, it in enumerate(S2):
        n = 101 + i
        request = {"task": "rewrite", "format": "email"}
        request.update(it["req"])
        full = it["full"] if it["full"] is not None else (n % 10 in (1, 4, 7))
        if full:
            request["header_style"] = "full"
        request["transcript"] = it["transcript"]
        a = {"format": "email"}
        for k, src in (("numbers", "nums"), ("must_include", "inc"), ("must_not_include", "notinc")):
            if it[src]:
                a[k] = list(it[src])
        if it["one_of"]:
            a["numbers_one_of"] = [list(g) for g in it["one_of"]]
        if it["neg"]:
            a["min_negations"] = it["neg"]
        if it["maxw"]:
            a["max_words"] = it["maxw"]
        pos = it["pos"] or ("after" if request.get("instruction") else "structured")
        meta = {"command_position": pos, "instruction_complexity": it["cx"], "length_class": length_class(it["transcript"])}
        rows.append(rec(f"TC-{WID}-{n:03d}", "email", it["sl"], request, it["target"], a, f"{WID.lower()}-sc-{n:03d}",
                        author=WID, note=it["note"], waivers=it["waivers"], meta=meta))
    return rows


if __name__ == "__main__":
    rows = build()
    save(OUT, rows)
    print(OUT, len(rows))
    rows2 = build_s2()
    save(OUT2, rows2)
    print(OUT2, len(rows2))
