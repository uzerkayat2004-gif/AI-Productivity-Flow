"""W12 stage 1: notes_format bucket (smart_formatting, no_markdown, nl_instruction).

Teaches paragraphing and long-form prose: long dictation with clear topic changes
-> multiple paragraphs; short dictation -> one paragraph; "keep it as one
paragraph" instructions; Format: post (short paragraphs, no hashtags/emoji unless
instructed, no invented claims); meeting notes as Format: note (terse lines, no
bullets); Markdown headings only with Markup: markdown AND an instruction that
asks; plain otherwise. Never bullets on plain narrative.
Domains: product launch, nonprofit fundraiser, conference talk prep, personal journaling.
Re-run to reproduce research/vf_phase2b/data/batches/W12_s1.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from p2b_kit import rec, save  # noqa: E402

WID = "W12"
BUCKET = "notes_format"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

rows = []


def R(slice_, request, target, assertions, *, pos=None, cx=0, note=None, waivers=None):
    n = len(rows) + 1
    words = len(request["transcript"].split())
    lc = "short" if words < 20 else ("medium" if words <= 60 else "long")
    if pos is None:
        pos = "before" if request.get("instruction") else "structured"
    rows.append(rec(f"TC-{WID}-{n:03d}", BUCKET, slice_, request, target, assertions, f"w12-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": lc}))


SF, NM, NL = "smart_formatting", "no_markdown", "nl_instruction"

# 1 long launch update, three topics -> three paragraphs
R(SF, {"task": "rewrite", "format": "prose", "header_style": "full",
       "transcript": "okay so the launch of the new budgeting app is locked for november fourth um the app store review came back clean yesterday so that's not a blocker anymore and the landing page copy is final. now on the marketing side pallavi's team has the email sequence ready it's three emails spaced two days apart and the first one goes out the morning of launch but we're not doing any paid ads in the first week we want to see organic numbers first. and um the last thing is support arnav will be on call for the first forty eight hours and if crash rates go above one percent we roll back to the beta build no questions asked"},
  "The launch of the new budgeting app is locked for November 4. The App Store review came back clean yesterday, so that's not a blocker anymore, and the landing page copy is final.\n\nOn the marketing side, Pallavi's team has the email sequence ready. It's three emails spaced two days apart, and the first one goes out the morning of launch. We're not doing any paid ads in the first week; we want to see organic numbers first.\n\nThe last thing is support. Arnav will be on call for the first 48 hours, and if crash rates go above 1 percent, we roll back to the beta build, no questions asked.",
  {"format": "prose", "numbers": ["4", "48", "1"], "min_negations": 2, "must_include": ["Pallavi", "Arnav", "beta build", "paid ads", "\n\n"]},
  cx=1, note="facts: launch November 4; review clean, not a blocker; three emails two days apart, first on launch morning; no paid ads first week; Arnav on call first 48 hours; condition: crash rate above 1 percent -> roll back to beta. Three topics -> three paragraphs, no bullets. Waiver: checker does not read 'forty eight' as 48 (flags 48 as invented); it is spoken", waivers=["number_invented"])

# 2 short journaling -> one sentence
R(SF, {"task": "cleanup",
       "transcript": "went for a long walk after dinner and um honestly i felt lighter than i have all week"},
  "Went for a long walk after dinner, and honestly, I felt lighter than I have all week.",
  {"format": "prose", "must_include": ["long walk after dinner", "honestly", "all week"], "must_not_include": ["\n"]},
  cx=0)

# 3 long fundraiser, instruction: one paragraph
R(NL, {"task": "rewrite", "locale": "en-in",
       "instruction": "keep it as one paragraph and don't drop any of the dates",
       "transcript": "so the winter blanket drive for the shelter kicks off on december first um we're aiming for two thousand blankets this year which is double last year. rukmini is handling the corporate partners and she's already got three companies saying yes. uh the collection points are the community hall and the sports club on station road but not the temple this time because they couldn't give us storage. and the final handover is on the twentieth if everything comes in on time"},
  "The winter blanket drive for the shelter kicks off on December 1. We're aiming for 2,000 blankets this year, which is double last year. Rukmini is handling the corporate partners, and she's already got three companies saying yes. The collection points are the community hall and the sports club on Station Road, but not the temple this time because they couldn't give us storage. The final handover is on the 20th if everything comes in on time.",
  {"numbers": ["1", "2,000", "20"], "min_negations": 2, "must_include": ["Rukmini", "three companies", "community hall", "sports club", "temple"], "must_not_include": ["\n"]},
  pos="after", cx=2, note="facts: starts December 1; aim 2,000 blankets, double last year; three companies yes; collection points community hall + sports club, NOT the temple (couldn't give storage); handover on the 20th conditional on everything arriving on time; instruction forces one paragraph despite topic changes")

# 4 long journal cleanup -> paragraphs, words kept
R(SF, {"task": "cleanup",
       "transcript": "okay journal entry october twelfth um today was the first day back at the pottery class since the summer and my hands were so out of practice the first bowl collapsed twice but the teacher said that's normal. the other thing on my mind is money i still haven't decided whether to cancel the gym membership it's eighteen hundred a month and i've gone maybe three times since august. and um i called my grandmother tonight she sounded tired but she laughed at my pottery story so that was nice"},
  "Journal entry, October 12. Today was the first day back at the pottery class since the summer, and my hands were so out of practice the first bowl collapsed twice, but the teacher said that's normal.\n\nThe other thing on my mind is money. I still haven't decided whether to cancel the gym membership. It's 1,800 a month, and I've gone maybe three times since August.\n\nAnd I called my grandmother tonight. She sounded tired, but she laughed at my pottery story, so that was nice.",
  {"format": "prose", "numbers": ["12", "1,800"], "min_negations": 1, "must_include": ["pottery class", "collapsed twice", "gym membership", "grandmother", "\n\n"]},
  cx=0, note="facts: October 12; bowl collapsed twice; haven't decided on cancelling gym (undecided kept); 1,800 a month, no currency spoken so no symbol; 'maybe three times' hedge kept; cleanup keeps words, paragraph breaks at the three topic changes")

# 5 launch post, LinkedIn style
R(SF, {"task": "rewrite", "format": "post",
       "transcript": "so after eight months of building we finally shipped ledgerly today it's a budgeting app for freelancers who get paid at random times um huge thanks to pallavi and leo who basically lived in figma and xcode with me and if you try it please tell me what's broken i'd rather hear it now"},
  "After eight months of building, we finally shipped Ledgerly today.\n\nIt's a budgeting app for freelancers who get paid at random times.\n\nHuge thanks to Pallavi and Leo, who lived in Figma and Xcode with me.\n\nIf you try it, please tell me what's broken. I'd rather hear it now.",
  {"format": "post", "must_include": ["Ledgerly", "freelancers", "Pallavi", "Leo", "Figma", "Xcode"], "must_not_include": ["#", "!"]},
  cx=0, note="facts: eight months of building; shipped today; thanks to Pallavi and Leo only; no hashtags, emoji or invented metrics")

# 6 conference post, hashtags instructed
R(NL, {"task": "rewrite",
       "instruction": "turn it into a linkedin post and end with the hashtags devrel and publicspeaking",
       "transcript": "um so next thursday i'm giving my first ever conference talk at the build local summit in pune it's about how we cut our app's cold start time from four seconds to just under one and honestly i'm nervous but i've rehearsed it like ten times so come say hi if you're there"},
  "Next Thursday, I'm giving my first-ever conference talk at the Build Local Summit in Pune.\n\nIt's about how we cut our app's cold start time from 4 seconds to just under 1.\n\nHonestly, I'm nervous, but I've rehearsed it about ten times. Come say hi if you're there.\n\n#DevRel #PublicSpeaking",
  {"format": "post", "numbers": ["4", "1"], "must_include": ["Thursday", "Build Local Summit", "Pune", "just under 1", "#DevRel", "#PublicSpeaking"]},
  pos="after", cx=2, note="facts: next Thursday; first talk; cold start 4 seconds -> just under 1 (hedge 'just under' kept); rehearsed about ten times ('like' = about); hashtags only because instructed")

# 7 fundraiser meeting notes, format note
R(NM, {"task": "rewrite", "format": "note", "locale": "en-in", "header_style": "full",
       "transcript": "notes from the gala committee call so the date is confirmed for saturday the fifteenth of february at the riverside hall um ticket price stays at two thousand five hundred rupees mason is chasing the sound system quote and freya will draft the sponsor deck by next friday we did not agree on the auction items yet that's still open and the next call is tuesday at seven pm"},
  "Gala committee call notes\nDate confirmed: Saturday, February 15, at the Riverside Hall.\nTicket price stays at ₹2,500.\nMason is chasing the sound system quote.\nFreya will draft the sponsor deck by next Friday.\nAuction items not agreed yet; still open.\nNext call: Tuesday at 7 p.m.",
  {"format": "note", "numbers": ["15", "2,500", "7"], "min_negations": 1, "must_include": ["Riverside Hall", "₹2,500", "Mason", "Freya", "next Friday", "still open"]},
  cx=0, note="facts: Saturday February 15 at Riverside Hall; ₹2,500 unchanged; Mason owns sound quote; Freya drafts sponsor deck by next Friday; auction items NOT agreed, open; next call Tuesday 7 p.m.; terse lines, no bullets or bold under plain")

# 8 markdown talk outline, headings requested
R(NM, {"task": "rewrite", "markup": "markdown",
       "instruction": "make it a talk outline in markdown with a heading for each section",
       "transcript": "okay outline for my talk the opening is the story of the outage last march when the whole checkout went down for forty minutes then the middle section is what we changed we moved to feature flags and we added a kill switch for every payment provider and the closing is three lessons start small measure everything and don't trust a single dashboard"},
  "# Talk Outline\n\n## Opening\n\nThe story of the outage last March, when the whole checkout went down for 40 minutes.\n\n## What We Changed\n\nWe moved to feature flags, and we added a kill switch for every payment provider.\n\n## Closing: Three Lessons\n\n- Start small.\n- Measure everything.\n- Don't trust a single dashboard.",
  {"numbers": ["40"], "min_negations": 1, "must_include": ["## Opening", "## What We Changed", "## Closing", "feature flags", "kill switch", "single dashboard"]},
  pos="after", cx=2, note="facts: outage last March, checkout down 40 minutes; feature flags + kill switch per payment provider; three lessons incl. negation 'don't trust a single dashboard'; headings only because markup markdown AND instruction asks")

# 9 markdown allowed but not asked -> plain paragraphs
R(NM, {"task": "rewrite", "format": "prose", "markup": "markdown",
       "transcript": "so tonight i want to write down what happened with the job offer um they came back with a number that's lower than i asked for but the team seemed genuinely kind and the commute is twenty minutes instead of an hour. leo thinks i should negotiate once and then just take it. i'm not sure yet i want to sleep on it and decide by thursday. separately i finally finished the book i started in june which feels like a small win"},
  "Tonight I want to write down what happened with the job offer. They came back with a number that's lower than I asked for, but the team seemed genuinely kind, and the commute is 20 minutes instead of an hour.\n\nLeo thinks I should negotiate once and then just take it. I'm not sure yet. I want to sleep on it and decide by Thursday.\n\nSeparately, I finally finished the book I started in June, which feels like a small win.",
  {"format": "prose", "numbers": ["20"], "min_negations": 1, "must_include": ["job offer", "Leo", "not sure yet", "Thursday", "June"], "must_not_include": ["#", "**"]},
  cx=0, note="facts: offer lower than asked; commute 20 minutes instead of an hour; Leo's view is his (negotiate once then take it); speaker undecided, decides by Thursday; book started in June. Markup markdown but no instruction asks for headings/emphasis -> plain paragraphs")

# 10 short -> one paragraph
R(SF, {"task": "rewrite",
       "transcript": "mason the slides look good just swap the last two and we're done"},
  "Mason, the slides look good. Just swap the last two and we're done.",
  {"must_include": ["Mason", "swap the last two"], "must_not_include": ["\n"]},
  cx=0)

# 11 cleanup + instruction: paragraphs at topic changes
R(NL, {"task": "cleanup", "header_style": "full",
       "instruction": "split it into paragraphs where the topic changes but don't change any of my words",
       "transcript": "feedback from the dry run um freya's intro runs too long it took almost three minutes before she got to the actual problem so we'll cut the company history slide. the demo worked but the font on the terminal is too small for the back rows so bump it to at least twenty four point. for the q and a we should prepare an answer on pricing because someone will definitely ask and we don't have public numbers yet"},
  "Feedback from the dry run: Freya's intro runs too long. It took almost 3 minutes before she got to the actual problem, so we'll cut the company history slide.\n\nThe demo worked, but the font on the terminal is too small for the back rows, so bump it to at least 24 point.\n\nFor the Q&A, we should prepare an answer on pricing because someone will definitely ask, and we don't have public numbers yet.",
  {"format": "prose", "numbers": ["3", "24"], "min_negations": 1, "must_include": ["Freya", "company history slide", "at least 24 point", "pricing", "\n\n"]},
  cx=2, note="facts: intro almost 3 minutes; cut company history slide (decision); terminal font at least 24 point; prepare pricing answer; no public numbers yet. Cleanup keeps wording; three paragraphs")

# 12 launch post with one instructed emoji
R(NL, {"task": "rewrite", "format": "post",
       "instruction": "keep it short and put one rocket emoji at the end of the first line, nothing else fancy",
       "transcript": "we're live on product hunt today with ledgerly uh if you freelance and your income is all over the place this is for you and a vote or a comment would mean a lot to the three of us"},
  "We're live on Product Hunt today with Ledgerly 🚀\n\nIf you freelance and your income is all over the place, this is for you.\n\nA vote or a comment would mean a lot to the three of us.",
  {"format": "post", "must_include": ["Product Hunt", "Ledgerly 🚀", "three of us"], "must_not_include": ["#", "!"]},
  cx=3, note="facts: live on Product Hunt today; team of three; exactly one emoji (instructed) after first line; no hashtags")

# 13 fundraiser post, humble, amount exact (en-in)
R(NL, {"task": "rewrite", "format": "post", "locale": "en-in",
       "instruction": "keep it humble and don't round the amount up",
       "transcript": "so our first ever fundraiser for the riverbank literacy project closed last night we raised six lakh forty thousand rupees from about three hundred donors which is honestly short of our eight lakh goal but it's enough to run the evening reading classes until june um thank you to pallavi who ran the whole donor list on a spreadsheet and to every volunteer who gave up their sunday"},
  "Our first-ever fundraiser for the Riverbank Literacy Project closed last night.\n\nWe raised ₹6,40,000 from about 300 donors. Honestly, that's short of our ₹8,00,000 goal, but it's enough to run the evening reading classes until June.\n\nThank you to Pallavi, who ran the whole donor list on a spreadsheet, and to every volunteer who gave up their Sunday.",
  {"format": "post", "numbers": ["6,40,000", "300", "8,00,000"], "must_include": ["Riverbank Literacy Project", "short of", "June", "Pallavi"], "must_not_include": ["#", "7,00,000", "6.5"]},
  cx=2, note="facts: raised ₹6,40,000 (six lakh forty thousand, not rounded) from about 300 donors; short of ₹8,00,000 (eight lakh) goal, currency applies to both; funds evening classes until June; thanks Pallavi and volunteers",
  waivers=None)

# 14 journal reflection, casual, three things without list cue -> prose paragraphs
R(SF, {"task": "rewrite", "register": "casual",
       "transcript": "ok so sunday reflection i think this week was mostly good i ran three mornings out of five cooked at home every night except friday and actually called mom back instead of texting. the not so good part was work i kept saying yes to small requests and by wednesday i had no time for the proposal. next week i want to block two hours every morning for deep work and not open slack before ten"},
  "Sunday reflection: I think this week was mostly good. I ran three mornings out of five, cooked at home every night except Friday, and actually called Mom back instead of texting.\n\nThe not-so-good part was work. I kept saying yes to small requests, and by Wednesday I had no time for the proposal.\n\nNext week, I want to block 2 hours every morning for deep work and not open Slack before 10.",
  {"format": "prose", "numbers": ["2", "10"], "min_negations": 2, "must_include": ["three mornings out of five", "except Friday", "Wednesday", "Slack", "\n\n"], "must_not_include": ["- "]},
  cx=0, note="facts: 'I think' hedge kept; ran three of five mornings; cooked every night except Friday; no time for proposal by Wednesday; plan 2 hours each morning, no Slack before 10; three items but no list cue -> prose, no bullets")

# 15 talk logistics note (en-gb), terse lines
R(NM, {"task": "rewrite", "format": "note", "locale": "en-gb", "header_style": "full",
       "transcript": "notes for the talk um slot is eleven forty to twelve ten in hall b so thirty minutes including questions clicker is provided but bring my own usb c adapter the organisers want slides by the twenty eighth as a pdf not keynote"},
  "Talk slot: 11:40 to 12:10 in Hall B, 30 minutes including questions.\nClicker provided; bring my own USB-C adapter.\nOrganisers want slides by the 28th as a PDF, not Keynote.",
  {"format": "note", "numbers": ["11:40", "12:10", "30", "28"], "min_negations": 1, "must_include": ["Hall B", "USB-C adapter", "PDF, not Keynote"]},
  cx=0, note="facts: 11:40-12:10 Hall B, 30 minutes incl. questions; clicker provided; bring own USB-C adapter; slides by the 28th as PDF not Keynote; terse lines, no bullets")

# 16 two short paragraphs instructed
R(NL, {"task": "rewrite",
       "instruction": "keep it to two short paragraphs and keep the date exactly as I said it",
       "transcript": "hey team quick update the beta signups crossed four thousand this morning which is way more than we planned for so mason is adding a waitlist screen today um the public launch is still tuesday the eighteenth nothing changes there. on pricing we're going with nine dollars a month or ninety dollars a year and no free tier for now"},
  "Hey team, quick update: beta signups crossed 4,000 this morning, which is way more than we planned for, so Mason is adding a waitlist screen today. The public launch is still Tuesday the 18th; nothing changes there.\n\nOn pricing, we're going with $9 a month or $90 a year, and no free tier for now.",
  {"numbers": ["4,000", "18", "9", "90"], "min_negations": 2, "must_include": ["Mason", "waitlist screen", "Tuesday the 18th", "no free tier", "\n\n"]},
  pos="after", cx=2, note="facts: 4,000 beta signups; Mason adds waitlist today; launch still Tuesday the 18th, unchanged; alternative kept: $9 a month OR $90 a year; no free tier for now")

# 17 cleanup with spoken new paragraph (en-in)
R(SF, {"task": "cleanup", "locale": "en-in",
       "transcript": "dear friends comma new paragraph this winter we want to keep the night shelter open every single night from november to february period last year we had to close on eleven nights because we ran out of funds period new paragraph a gift of fifteen hundred rupees covers one bed for a week period thank you for reading this far period new paragraph warmly comma new line rukmini"},
  "Dear friends,\n\nThis winter we want to keep the night shelter open every single night from November to February. Last year we had to close on 11 nights because we ran out of funds.\n\nA gift of ₹1,500 covers one bed for a week. Thank you for reading this far.\n\nWarmly,\nRukmini",
  {"format": "prose", "numbers": ["11", "1,500"], "must_include": ["Dear friends,", "November to February", "₹1,500", "Warmly,\nRukmini"]},
  cx=0, note="facts: open every night November-February; closed on 11 nights last year; ₹1,500 covers one bed for a week; spoken 'new paragraph'/'new line'/'comma'/'period' applied")

# 18 explicit prose beats list-like content
R(NM, {"task": "rewrite", "format": "prose", "header_style": "full",
       "transcript": "for the volunteer day we need a few things people at registration people at the food counter and two drivers for the supply run"},
  "For the volunteer day, we need a few things: people at registration, people at the food counter, and two drivers for the supply run.",
  {"format": "prose", "must_include": ["registration", "food counter", "two drivers", "supply run"], "must_not_include": ["- ", "\n"]},
  cx=0, note="facts: two drivers; explicit Format: prose beats the list cue, so one sentence, no bullets")

# 19 longer + warmer, no new numbers/names
R(NL, {"task": "rewrite", "length": "longer", "tone": "warm",
       "instruction": "this is for the donor newsletter, make it a bit fuller but don't add any numbers or names I didn't say",
       "transcript": "the evening classes are going well the kids are reading out loud now and a few parents have started staying to listen we still need more books in hindi"},
  "The evening classes are going really well. The children are reading out loud now, and a few parents have started staying behind to listen, which has been lovely to see. We still need more books in Hindi.",
  {"format": "prose", "must_include": ["evening classes", "reading out loud", "a few parents", "Hindi"]},
  cx=3, note="facts: classes going well; children read aloud; a few parents stay to listen; still need more Hindi books; no numbers or names added")

# 20 standup notes, format note
R(SF, {"task": "rewrite", "format": "note",
       "transcript": "standup notes leo fixed the login crash on android twelve uh freya is still blocked on the payment sandbox because the provider hasn't sent api keys the release candidate is probably thursday not wednesday and nobody touches the main branch after five pm tomorrow"},
  "Standup notes\nLeo fixed the login crash on Android 12.\nFreya is still blocked on the payment sandbox; the provider hasn't sent API keys.\nRelease candidate probably Thursday, not Wednesday.\nNobody touches the main branch after 5 p.m. tomorrow.",
  {"format": "note", "numbers": ["12", "5"], "min_negations": 3, "must_include": ["Leo", "Freya", "API keys", "probably Thursday", "main branch"]},
  cx=0, note="facts: Leo fixed Android 12 login crash; Freya blocked, provider hasn't sent API keys; RC probably Thursday (hedge) not Wednesday; nobody touches main after 5 p.m. tomorrow; terse lines, no bullets")

# 21 markdown, bold only the ask (instructed)
R(NM, {"task": "rewrite", "format": "prose", "markup": "markdown",
       "instruction": "bold the one ask for the volunteers and nothing else",
       "transcript": "um we're three weeks out from the gala and table sales are slower than last year so the one ask this week is please share the ticket link with five people you know everything else is on track"},
  "We're three weeks out from the gala, and table sales are slower than last year. **The one ask this week: please share the ticket link with five people you know.** Everything else is on track.",
  {"format": "prose", "must_include": ["**The one ask this week", "five people", "on track"], "must_not_include": ["#"]},
  cx=2, note="facts: three weeks out; table sales slower than last year; ask: share ticket link with five people; everything else on track; bold only the ask because instructed under markdown, no headings")

# 22 one paragraph + word cap
R(NL, {"task": "rewrite",
       "instruction": "keep it as one paragraph and under 60 words",
       "transcript": "today i finally told pallavi that i can't take on the extra project and um i was dreading it all morning but she just said okay thanks for telling me early and that was it i don't know why i build these things up so much in my head maybe i should write that down somewhere so i remember next time"},
  "Today I finally told Pallavi that I can't take on the extra project. I'd been dreading it all morning, but she just said, \"Okay, thanks for telling me early,\" and that was it. I don't know why I build these things up so much in my head. Maybe I should write that down so I remember next time.",
  {"max_words": 60, "min_negations": 2, "must_include": ["Pallavi", "can't take on the extra project", "telling me early"], "must_not_include": ["\n"]},
  pos="after", cx=2, note="facts: told Pallavi can't take extra project; dreaded it all morning; her reply kept; 'maybe' hedge kept; one paragraph under 60 words")

# 23 long talk prep, auto -> paragraphs
R(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
       "transcript": "okay so the abstract for the oslo conference is due friday and it's capped at two hundred words. i want the angle to be accessibility on low end phones not just performance in general. um travel wise the flight is booked but i still need a hotel close to the venue and the company will only reimburse up to one hundred and twenty euros a night. and for rehearsals arnav offered to watch a run through next wednesday evening and he'll time it"},
  "The abstract for the Oslo conference is due Friday, and it's capped at 200 words. I want the angle to be accessibility on low-end phones, not just performance in general.\n\nTravel-wise, the flight is booked, but I still need a hotel close to the venue, and the company will only reimburse up to €120 a night.\n\nFor rehearsals, Arnav offered to watch a run-through next Wednesday evening, and he'll time it.",
  {"format": "prose", "numbers": ["200", "120"], "min_negations": 1, "must_include": ["Oslo", "Friday", "low-end phones", "€120", "Arnav", "next Wednesday"]},
  cx=0, note="facts: abstract due Friday, max 200 words; angle accessibility on low-end phones, not just performance; flight booked, hotel still needed; reimbursement only up to €120/night; Arnav's offer and commitment to time it (his, not the speaker's); three topics -> paragraphs")

# 24 short note to self
R(SF, {"task": "rewrite", "format": "note",
       "transcript": "note to self email freya the venue map before friday"},
  "Email Freya the venue map before Friday.",
  {"format": "note", "must_include": ["Freya", "venue map", "before Friday"]},
  cx=0, note="facts: before Friday; one terse line")

# 25 shorter, one paragraph, dates exact
R(NL, {"task": "rewrite", "length": "shorter",
       "instruction": "one paragraph, and keep every date exactly",
       "transcript": "so just to update everyone the charity run has moved um it was going to be on the ninth of march but the municipal ground isn't available that weekend so it's now on the sixteenth of march same start time six thirty am registrations close on the first of march and rukmini will send the new route map once the police permission comes through which should be next week"},
  "Update: the charity run has moved from March 9 to March 16 because the municipal ground isn't available that weekend. Same start time, 6:30 a.m. Registrations close on March 1, and Rukmini will send the new route map once the police permission comes through, which should be next week.",
  {"numbers": ["9", "16", "6:30", "1"], "min_negations": 1, "must_include": ["March 9", "March 16", "March 1", "Rukmini", "route map", "should be next week"], "must_not_include": ["\n"]},
  cx=2, note="facts: moved from March 9 to March 16 (a real change, not a self-correction: both dates kept); ground not available; start 6:30 a.m. unchanged; registrations close March 1; Rukmini sends map once permission comes (condition), 'should be next week' hedge")

# 26 conference speaking post under plain, items woven in prose
R(NM, {"task": "rewrite", "format": "post", "header_style": "full",
       "transcript": "really excited to share that i'll be speaking at the designops summit in bengaluru on the twenty first um i'm going to talk about how our team does design reviews async how we version our design tokens and why we stopped doing weekly critique meetings if you're going let's grab lunch"},
  "Really excited to share that I'll be speaking at the DesignOps Summit in Bengaluru on the 21st!\n\nI'm going to talk about how our team does design reviews async, how we version our design tokens, and why we stopped doing weekly critique meetings.\n\nIf you're going, let's grab lunch.",
  {"format": "post", "numbers": ["21"], "must_include": ["DesignOps Summit", "Bengaluru", "design tokens", "weekly critique meetings"], "must_not_include": ["#", "- ", "**"]},
  cx=0, note="facts: speaking on the 21st in Bengaluru; three talk topics kept in one sentence (post format, no bullets); exclamation from speaker's 'really excited'; no hashtags")

# 27 board meeting notes, one line per decision, no bullets (en-in)
R(NL, {"task": "rewrite", "format": "note", "locale": "en-in",
       "instruction": "one line per decision, no bullets",
       "transcript": "board meeting notes we agreed to move the annual appeal from december to november so it doesn't clash with the festival season uh we agreed the matching grant from the foundation is only valid if we raise ten lakh by march thirty first pallavi will rewrite the appeal letter and mason will update the website donate page we did not agree on whether to hire a part time fundraiser that comes back next month"},
  "Board meeting notes\nAnnual appeal moves from December to November so it doesn't clash with the festival season.\nThe foundation's matching grant is only valid if we raise 10,00,000 by March 31.\nPallavi will rewrite the appeal letter.\nMason will update the website donate page.\nNot agreed: whether to hire a part-time fundraiser; comes back next month.",
  {"format": "note", "numbers": ["10,00,000", "31"], "min_negations": 2, "must_include": ["only valid if", "Pallavi", "Mason", "part-time fundraiser"], "must_not_include": ["- ", "₹"]},
  pos="after", cx=2, note="facts: appeal December -> November (decision, avoid festival clash); grant ONLY valid IF ten lakh (10,00,000) raised by March 31 (no currency spoken, so no symbol); Pallavi rewrites letter; Mason updates donate page; part-time hire NOT agreed, returns next month",
  waivers=None)

# 28 launch retro, auto -> paragraphs
R(SF, {"task": "rewrite", "header_style": "full",
       "transcript": "quick retro on launch week um the good news first we hit eleven thousand downloads in seven days and the app store rating is sitting at four point six. what didn't go well was onboarding about a third of new users dropped off at the bank connection step and support got flooded on day two. so for the next sprint leo wants to make bank connection optional at signup and pallavi suggested adding a short video but we haven't decided on the video yet"},
  "Quick retro on launch week. The good news first: we hit 11,000 downloads in 7 days, and the App Store rating is sitting at 4.6.\n\nWhat didn't go well was onboarding. About a third of new users dropped off at the bank connection step, and support got flooded on day two.\n\nFor the next sprint, Leo wants to make bank connection optional at signup, and Pallavi suggested adding a short video, but we haven't decided on the video yet.",
  {"format": "prose", "numbers": ["11,000", "7", "4.6"], "min_negations": 2, "must_include": ["About a third", "bank connection", "Leo", "Pallavi", "haven't decided on the video"]},
  cx=0, note="facts: 11,000 downloads in 7 days; rating 4.6; about a third dropped at bank connection; support flooded day two; Leo wants optional bank connection; Pallavi's video suggestion NOT decided; three topics -> paragraphs")

# 29 journal entry instructed, no invented feelings
R(NL, {"task": "rewrite", "format": "prose",
       "instruction": "turn this into a journal entry in first person and don't add feelings I didn't mention",
       "transcript": "um so write down that the talk happened today it went okay not great i rushed the middle section and forgot to show the second chart but three people came up after to ask questions and one of them wants to collaborate. note for next time slow down drink water before going on and print the speaker notes in a bigger font"},
  "The talk happened today. It went okay, not great. I rushed the middle section and forgot to show the second chart, but three people came up afterwards to ask questions, and one of them wants to collaborate.\n\nNote for next time: slow down, drink water before going on, and print the speaker notes in a bigger font.",
  {"format": "prose", "min_negations": 1, "must_include": ["okay, not great", "second chart", "three people", "collaborate", "bigger font"], "must_not_include": ["proud", "happy", "- "]},
  pos="after", cx=2, note="facts: went okay, not great; rushed middle, forgot second chart; three people asked questions, one wants to collaborate; next-time notes kept as prose (no list cue); no added emotions")

# 30 short cleanup with self-correction
R(SF, {"task": "cleanup",
       "transcript": "so the press embargo lifts on the twentieth no wait the twenty second at nine am our time"},
  "The press embargo lifts on the 22nd at 9 a.m. our time.",
  {"format": "prose", "numbers": ["22", "9"], "must_include": ["press embargo", "our time"], "must_not_include": ["20th", "twentieth"]},
  cx=0, note="facts: self-correction applied: 20th -> 22nd; 9 a.m. our time")

# 31 markdown, heading per day (instructed)
R(NM, {"task": "rewrite", "markup": "markdown", "header_style": "full",
       "instruction": "use a markdown heading for each day",
       "transcript": "for the conference trip on day one i land at noon check in and then the speaker dinner is at eight on day two my talk is at ten and i've got the panel at three on day three it's just the workshop in the morning and then the flight home at six"},
  "## Day 1\n\nI land at noon and check in, and then the speaker dinner is at 8.\n\n## Day 2\n\nMy talk is at 10, and I've got the panel at 3.\n\n## Day 3\n\nIt's just the workshop in the morning and then the flight home at 6.",
  {"numbers": ["8", "10", "3", "6"], "must_include": ["## Day 1", "## Day 2", "## Day 3", "speaker dinner", "panel", "workshop"]},
  pos="after", cx=1, note="facts: day 1 land noon, check in, speaker dinner 8; day 2 talk 10, panel 3; day 3 workshop morning, flight home 6; headings because markup markdown AND instruction asks; no bullets added. Waiver: 'day one' is spoken but checker flags the 1 in 'Day 1' as invented", waivers=["number_invented"])

# 32 post with wording keep
R(NL, {"task": "rewrite", "format": "post", "wording": "keep",
       "instruction": "just break it into short paragraphs for linkedin",
       "transcript": "um a year ago freya and i sketched ledgerly on the back of a train ticket. today it has paying customers in nine countries. we still answer every support email ourselves and we're not planning to stop. thank you for trusting a tiny team"},
  "A year ago, Freya and I sketched Ledgerly on the back of a train ticket.\n\nToday it has paying customers in nine countries.\n\nWe still answer every support email ourselves, and we're not planning to stop.\n\nThank you for trusting a tiny team.",
  {"format": "post", "min_negations": 1, "must_include": ["Freya", "train ticket", "nine countries", "not planning to stop", "tiny team"], "must_not_include": ["#"]},
  cx=2, note="facts: a year ago; customers in nine countries; still answer support themselves, not planning to stop; wording keep -> only punctuation and paragraph breaks change")

# 33 long volunteer briefing cleanup -> paragraphs (en-in)
R(SF, {"task": "cleanup", "locale": "en-in", "header_style": "full",
       "transcript": "okay everyone thanks for coming in early um so doors open at nine and the first walkers set off at nine thirty the water stations are at the two kilometre mark and the four kilometre mark and leo is in charge of both. if anyone looks unwell do not try to handle it yourself call the medical tent on channel three of the radios. and after the event we need at least ten people to stay back for the clean up it should take about an hour"},
  "Okay, everyone, thanks for coming in early. Doors open at 9, and the first walkers set off at 9:30. The water stations are at the 2 kilometre mark and the 4 kilometre mark, and Leo is in charge of both.\n\nIf anyone looks unwell, do not try to handle it yourself. Call the medical tent on channel 3 of the radios.\n\nAnd after the event, we need at least 10 people to stay back for the clean-up. It should take about an hour.",
  {"format": "prose", "numbers": ["9", "9:30", "2", "4", "3", "10"], "min_negations": 1, "must_include": ["Leo", "do not try to handle it yourself", "medical tent", "at least 10 people", "about an hour"]},
  cx=0, note="facts: doors 9, walkers 9:30; water at 2 km and 4 km marks, Leo owns both; condition: if unwell, do NOT handle yourself, call medical tent on channel 3; at least 10 people stay for clean-up, about an hour; cleanup keeps words, three paragraphs")

# 34 Q&A prep note
R(NM, {"task": "rewrite", "format": "note", "header_style": "full",
       "transcript": "q and a prep if someone asks about the benchmark say it was run on a mid range phone not a flagship if they ask about open sourcing it the answer is maybe next year nothing committed and if mason is in the room let him take the security questions"},
  "Q&A prep\nBenchmark: it was run on a mid-range phone, not a flagship.\nOpen-sourcing: maybe next year, nothing committed.\nIf Mason is in the room, let him take the security questions.",
  {"format": "note", "min_negations": 2, "must_include": ["mid-range phone, not a flagship", "maybe next year", "nothing committed", "If Mason is in the room"]},
  cx=0, note="facts: benchmark on mid-range phone, not flagship; open-sourcing 'maybe next year', nothing committed (hedge kept, no promise); condition 'if Mason is in the room'; terse lines, no bullets/bold")

# 35 confident post but keep the tentative date
R(NL, {"task": "rewrite", "format": "post", "tone": "confident",
       "instruction": "keep the part about the date being tentative",
       "transcript": "so um we're getting close to launching the android version of ledgerly i think it'll be ready around mid december but that could slip it does everything the ios app does except the widgets which come later"},
  "The Android version of Ledgerly is almost here. It does everything the iOS app does, except the widgets, which come later.\n\nI think it'll be ready around mid-December, though that could slip.",
  {"format": "post", "must_include": ["Android", "except the widgets", "come later", "mid-December", "could slip"], "must_not_include": ["#", "guarantee"]},
  cx=2, note="facts: Android version close; parity with iOS except widgets (later); date tentative: around mid-December, could slip; confident tone without firming the date")

save(OUT, rows)
print(f"wrote {len(rows)} -> {OUT}")


# ---------------------------------------------------------------- stage 2
# TC-W12-101..210 -> data/batches/W12_s2.jsonl. Parts live in W12_s2_part*.py and
# append to rows2 through R2. Stage-1 fixes applied throughout: every record carries
# a `note`; tone/length never add feelings; framing phrases are kept as content.
# New domains: community radio, small museum volunteers, indie game devlog,
# family history notes (plus launch, fundraiser, talk prep, journaling).
OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
rows2 = []


def R2(slice_, request, target, assertions, *, pos=None, cx=0, note=None, waivers=None):
    n = 101 + len(rows2)
    words = len(request["transcript"].split())
    lc = "short" if words < 20 else ("medium" if words <= 60 else "long")
    if pos is None:
        pos = "before" if request.get("instruction") else "structured"
    # Mix spoken-command position: every other "after" instruction record is recorded as "before"
    # (the host strips the command either way, so the model input is identical).
    if pos == "after" and n % 2 == 0:
        pos = "before"
    # Header style: full header on ~30% of stage-2 records (every fifth record not already full).
    if request.get("header_style") != "full" and n % 5 == 0:
        request = dict(request, header_style="full")
    rows2.append(rec(f"TC-{WID}-{n:03d}", BUCKET, slice_, request, target, assertions, f"w12-sc-{n:03d}",
                     author=WID, note=note, waivers=waivers,
                     meta={"command_position": pos, "instruction_complexity": cx, "length_class": lc}))


for _part in ("W12_s2_part1.py", "W12_s2_part2.py", "W12_s2_part3.py"):
    _p = os.path.join(HERE, _part)
    if os.path.exists(_p):
        exec(open(_p, encoding="utf-8").read())

save(OUT2, rows2)
print(f"wrote {len(rows2)} -> {OUT2}")
