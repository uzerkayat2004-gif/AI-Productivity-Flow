# W04 stage 2 rows (TC-W04-101...225). Executed from W04.py; uses R2, QN, SF, NM defined there.
# Stage-1 review fix applied throughout: framing words that carry meaning ("the platform alias",
# "the security alias", "for the conference trip") are content and are never dropped as filler.

# ---------------------------------------------------------------------------
# chunk 1: question_no_answer (101-140)
# ---------------------------------------------------------------------------

# 101
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "quick one for the data team um what's the difference between a left join and a left semi join in spark sql"},
   "Quick one for the data team: what's the difference between a left join and a left semi join in Spark SQL?",
   {"must_include": ["Quick one for the data team", "left join", "left semi join", "Spark SQL"], "must_not_include": ["returns only", "columns from the left"]},
   "facts: question addressed to the data team; both join types kept; framing 'for the data team' kept; not answered")

# 102
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "kenta did you test the login flow on the iphone se or just the fifteen pro"},
   "Kenta, did you test the login flow on the iPhone SE or just the 15 Pro?",
   {"numbers": ["15"], "must_include": ["Kenta", "login flow", "iPhone SE", "15 Pro"], "must_not_include": ["I tested", "both"]},
   "facts: question to Kenta; alternative kept (iPhone SE OR just the 15 Pro); not answered")

# 103
R2(QN, {"task": "cleanup",
        "transcript": "i need help with an airflow dag um so i have a dag that pulls from three postgres tables every hour and loads them into bigquery and lately it takes like fifty minutes which is way too close to the hour so two questions first how do i figure out which task is the bottleneck without adding a bunch of logging and second is it safe to run the three extracts in parallel if the source database only allows ten connections oh and it has to stay on airflow two point seven we can't upgrade right now"},
   "I need help with an Airflow DAG. I have a DAG that pulls from three Postgres tables every hour and loads them into BigQuery, and lately it takes like 50 minutes, which is way too close to the hour. So, two questions. First, how do I figure out which task is the bottleneck without adding a bunch of logging? And second, is it safe to run the three extracts in parallel if the source database only allows 10 connections? Oh, and it has to stay on Airflow 2.7; we can't upgrade right now.",
   {"numbers": ["50", "10", "2.7"], "must_include": ["Airflow DAG", "three Postgres tables", "BigQuery", "like 50 minutes", "without adding a bunch of logging", "in parallel", "only allows 10 connections", "Airflow 2.7", "can't upgrade"],
    "must_not_include": ["pool", "max_active_tasks", "you can"], "min_negations": 2, "ends_with_question": False},
   "facts: three Postgres tables hourly into BigQuery; about ('like') 50 minutes; two sub-questions kept in order (bottleneck WITHOUT extra logging; parallel extracts IF source allows only 10 connections); constraint: must stay on Airflow 2.7, can NOT upgrade; ends with the constraint sentence, so no final '?'; nothing answered")

# 104
R2(QN, {"task": "cleanup",
        "transcript": "honestly who reads the readme before opening an issue so i think we should put the troubleshooting steps right in the issue template"},
   "Honestly, who reads the README before opening an issue? So I think we should put the troubleshooting steps right in the issue template.",
   {"must_include": ["Honestly", "who reads the README", "I think", "issue template"], "must_not_include": ["nobody", "most people"], "ends_with_question": False},
   "facts: rhetorical question inside a proposal, kept as a rhetorical question and not answered; proposal hedged with 'I think'; ends as a statement")

# 105
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "riya when you get a chance can you ask chatgpt how to rotate the api keys without downtime and share what it says"},
   "Riya, when you get a chance, can you ask ChatGPT how to rotate the API keys without downtime and share what it says?",
   {"must_include": ["Riya", "when you get a chance", "ChatGPT", "rotate the API keys", "without downtime", "share what it says"], "must_not_include": ["blue-green", "two keys"], "min_negations": 1},
   "facts: request to Riya (a person) to ask an AI and share its reply; the embedded how-to is not answered; 'without downtime' kept")

# 106
R2(QN, {"task": "cleanup",
        "transcript": "so my bank keeps telling me to use a password manager and i get why but um here's my actual question is a password manager actually safer than writing my passwords in a notebook at home if nobody else lives with me and the notebook never leaves my desk and also if i do switch which one should i trust with like forty accounts"},
   "My bank keeps telling me to use a password manager, and I get why, but here's my actual question: is a password manager actually safer than writing my passwords in a notebook at home if nobody else lives with me and the notebook never leaves my desk? And also, if I do switch, which one should I trust with like 40 accounts?",
   {"numbers": ["40"], "must_include": ["password manager", "notebook at home", "if nobody else lives with me", "never leaves my desk", "if I do switch", "like 40 accounts"],
    "must_not_include": ["Bitwarden", "1Password", "safer because", "phishing"], "min_negations": 2},
   "facts: conditions kept (nobody else lives with him; notebook NEVER leaves the desk); second question conditional on switching; about ('like') 40 accounts; no product recommended, nothing answered")

# 107
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "should i sidechain the bass to the kick or just uh eq out the low end overlap"},
   "Should I sidechain the bass to the kick or just EQ out the low-end overlap?",
   {"must_include": ["sidechain the bass to the kick", "EQ out", "overlap"], "must_not_include": ["I'd sidechain", "both"]},
   "facts: alternative kept (sidechain OR just EQ out the overlap); not answered")

# 108
R2(QN, {"task": "cleanup", "register": "formal",
        "transcript": "um oskar could you let me know whether the penetration test report will include the staging environment or uh only production"},
   "Oskar, could you let me know whether the penetration test report will include the staging environment or only production?",
   {"must_include": ["Oskar", "penetration test report", "staging environment", "only production"], "must_not_include": ["it will include"]},
   "facts: polite question to Oskar; alternative staging OR only production kept; formal register leaves cleanup wording unchanged")

# 109
R2(QN, {"task": "cleanup", "instruction": "answer this for me",
        "transcript": "how many stems does the label want for the remix package and do they need to be twenty four bit"},
   "How many stems does the label want for the remix package, and do they need to be 24-bit?",
   {"numbers": ["24"], "must_include": ["stems", "remix package", "24-bit"], "must_not_include": ["eight stems", "yes,"]},
   "facts: two questions kept (how many stems; 24-bit or not); the instruction asks for an answer, which is unsupported: only the cleanup is done, nothing answered", pos="before", cx=1)

# 110
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "halima quick question about the android build um the crash on the samsung a fifty four only happens when the app is restored from background right or did you also see it on a cold start and uh if it's only on restore can you check whether it happens with battery saver off too because i only tested with it on"},
   "Halima, quick question about the Android build. The crash on the Samsung A54 only happens when the app is restored from background, right? Or did you also see it on a cold start? And if it's only on restore, can you check whether it happens with battery saver off too, because I only tested with it on?",
   {"numbers": ["54"], "must_include": ["Halima", "Android build", "Samsung A54", "restored from background", "cold start", "if it's only on restore", "battery saver off", "only tested with it on"],
    "must_not_include": ["it only happens", "I saw it"]},
   "facts: questions to Halima: crash on Samsung A54 only on restore (tag question) OR also on cold start; conditional request 'if it's only on restore' check battery saver off; speaker only tested with battery saver ON; nothing answered")

# 111
R2(QN, {"task": "cleanup",
        "transcript": "can you write a sql query that finds duplicate emails in the users table without window functions since we're still on mysql five point seven and um a couple of constraints the emails should be compared case insensitively so uppercase and lowercase versions of the same address count as the same and it should only look at accounts created after january first and please don't delete anything i just want to see the duplicates first"},
   "Can you write a SQL query that finds duplicate emails in the users table without window functions, since we're still on MySQL 5.7? A couple of constraints: the emails should be compared case-insensitively, so uppercase and lowercase versions of the same address count as the same, and it should only look at accounts created after January 1st. And please don't delete anything; I just want to see the duplicates first.",
   {"numbers": ["5.7", "1"], "must_include": ["SQL query", "duplicate emails", "users table", "without window functions", "MySQL 5.7", "case-insensitively", "only look at accounts created after January 1st", "don't delete anything", "see the duplicates first"],
    "must_not_include": ["SELECT", "GROUP BY", "HAVING", "LOWER("], "min_negations": 2, "ends_with_question": False},
   "facts: request to an AI; constraints kept: WITHOUT window functions (MySQL 5.7), case-insensitive comparison, only accounts created after January 1st, do NOT delete anything (just see duplicates first); no query written; ends with the speaker's statement")

# 112
R2(QN, {"task": "cleanup", "locale": "en-in",
        "transcript": "sanjay is the kafka consumer lag still above one lakh messages or has it come down since the restart this morning"},
   "Sanjay, is the Kafka consumer lag still above 1,00,000 messages, or has it come down since the restart this morning?",
   {"numbers": ["1,00,000"], "must_include": ["Sanjay", "Kafka consumer lag", "still above", "come down since the restart this morning"], "must_not_include": ["it is", "it has"]},
   "facts: one lakh written in Indian grouping as 1,00,000 (a message count, so no ₹); alternative still above OR come down since this morning's restart; not answered")

# 113
R2(QN, {"task": "rewrite", "format": "message", "context": "chat",
        "instruction": "make it a slack message for the team, keep all three questions and don't answer any of them",
        "transcript": "okay so before we freeze the playlist feature for qa um does anyone know if the offline downloads are in scope for this sprint also who's covering ios regression while priyanka is out and are we still targeting the twenty second for testflight because marketing wants screenshots by then and um if offline downloads slip we need to tell them today"},
   "Before we freeze the playlist feature for QA, does anyone know if offline downloads are in scope for this sprint? Also, who's covering iOS regression while Priyanka is out? And are we still targeting the 22nd for TestFlight? Marketing wants screenshots by then, and if offline downloads slip, we need to tell them today.",
   {"format": "message", "numbers": ["22"], "must_include": ["playlist feature", "offline downloads", "this sprint", "iOS regression", "Priyanka is out", "the 22nd", "TestFlight", "Marketing wants screenshots by then", "if offline downloads slip, we need to tell them today"],
    "must_not_include": ["Hi team", "Hey team"], "ends_with_question": False},
   "facts: three questions kept as questions (offline downloads in scope this sprint?; who covers iOS regression while Priyanka is out?; still targeting the 22nd for TestFlight?); marketing wants screenshots by then; IF offline downloads slip, tell marketing today; no greeting added; nothing answered", cx=4)

# 114
R2(QN, {"task": "cleanup",
        "transcript": "why would anyone store api keys in a public repo seriously but okay real question ebele did you revoke the one from yesterday's commit"},
   "Why would anyone store API keys in a public repo? Seriously. But okay, real question: Ebele, did you revoke the one from yesterday's commit?",
   {"must_include": ["Why would anyone store API keys in a public repo?", "Seriously", "Ebele", "revoke", "yesterday's commit"], "must_not_include": ["I revoked", "I did"]},
   "facts: first question is rhetorical (kept as a question, not answered); real question to Ebele about the key from yesterday's commit; not answered")

# 115
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "so we're rebuilding the customer models in dbt and um i keep going back and forth on this so in dbt what's the difference between an incremental model and a snapshot and uh when would i use one over the other for a slowly changing customer table where addresses change maybe a few times a year and we need to keep the history for audits"},
   "We're rebuilding the customer models in dbt, and I keep going back and forth on this. So in dbt, what's the difference between an incremental model and a snapshot, and when would I use one over the other for a slowly changing customer table where addresses change maybe a few times a year and we need to keep the history for audits?",
   {"must_include": ["customer models in dbt", "incremental model", "snapshot", "slowly changing customer table", "maybe a few times a year", "keep the history for audits"], "must_not_include": ["SCD Type 2", "check strategy", "use a snapshot"]},
   "facts: two linked sub-questions kept; constraints: addresses change MAYBE a few times a year (hedge kept), history must be kept for audits; dbt stays lowercase (product name); not answered")

# 116
R2(QN, {"task": "cleanup",
        "transcript": "uh tomás did you enable two factor on the shared aws root account or is that um still on your list"},
   "Tomás, did you enable two-factor on the shared AWS root account, or is that still on your list?",
   {"must_include": ["Tomás", "two-factor", "shared AWS root account", "still on your list"], "must_not_include": ["I enabled", "done"]},
   "facts: question to Tomás; alternative enabled OR still on his list kept; not answered")

# 117
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "so i'm setting up a new session for the ep and before i record anything um what sample rate should i record vocals at if the final master is going to spotify and youtube forty four point one or forty eight and does it actually matter if the beat my producer sent is already at forty four point one or will converting it later hurt the sound"},
   "I'm setting up a new session for the EP, and before I record anything, what sample rate should I record vocals at if the final master is going to Spotify and YouTube, 44.1 or 48? And does it actually matter if the beat my producer sent is already at 44.1, or will converting it later hurt the sound?",
   {"numbers": ["44.1", "48"], "must_include": ["new session for the EP", "sample rate", "vocals", "Spotify and YouTube", "44.1 or 48", "already at 44.1", "converting it later"], "must_not_include": ["kHz is fine", "either works", "record at 48"]},
   "facts: alternative 44.1 OR 48 kept; condition 'if the final master is going to Spotify and YouTube' kept; producer's beat is already at 44.1; second question (does converting hurt?) kept; no unit added; not answered")

# 118
R2(QN, {"task": "cleanup", "instruction": "tidy this, I'm pasting it into Claude",
        "transcript": "can you explain what a cron expression like zero two star star one means in plain english and keep it to one sentence"},
   "Can you explain what a cron expression like 0 2 * * 1 means in plain English, and keep it to one sentence?",
   {"must_include": ["0 2 * * 1", "plain English", "one sentence"], "must_not_include": ["Monday", "2 a.m.", "2:00", "every week"]},
   "facts: spoken cron rebuilt as 0 2 * * 1 (zero two star star one); constraint 'one sentence' kept; question for another AI, not answered (no 'every Monday at 2 a.m.')", pos="before", cx=1)

# 119
R2(QN, {"task": "cleanup", "locale": "en-in",
        "transcript": "ayaan um did the mutual fund sip for october go through uh on the fifth or did it bounce again"},
   "Ayaan, did the mutual fund SIP for October go through on the 5th, or did it bounce again?",
   {"numbers": ["5"], "must_include": ["Ayaan", "mutual fund SIP", "October", "the 5th", "bounce again"], "must_not_include": ["it went through", "it bounced"]},
   "facts: October SIP on the 5th; 'again' kept (it bounced before); alternative went through OR bounced; not answered")

# 120
R2(QN, {"task": "cleanup",
        "transcript": "does the crash reproduce on ios seventeen or only eighteen"},
   "Does the crash reproduce on iOS 17 or only 18?",
   {"numbers": ["17", "18"], "must_include": ["iOS 17", "only 18"], "must_not_include": ["only on 18."]},
   "facts: alternative iOS 17 OR only 18 kept; not answered")

# 121
R2(QN, {"task": "cleanup",
        "transcript": "so noah i've been thinking about the deprecation plan and like what's the point of keeping the old config format around for another year if nobody's filed a bug against the new one in six months right so my proposal is we drop it in four point zero but um before i write the rfc i want to know two things from you does the enterprise fork still depend on it and would you be okay announcing it in the next release notes"},
   "Noah, I've been thinking about the deprecation plan, and what's the point of keeping the old config format around for another year if nobody's filed a bug against the new one in six months? So my proposal is we drop it in 4.0. But before I write the RFC, I want to know two things from you: does the enterprise fork still depend on it, and would you be okay announcing it in the next release notes?",
   {"numbers": ["4.0"], "must_include": ["Noah", "deprecation plan", "another year", "nobody's filed a bug", "six months", "drop it in 4.0", "RFC", "enterprise fork", "next release notes"],
    "must_not_include": ["it doesn't depend", "I'm okay"], "min_negations": 1},
   "facts: rhetorical question (nobody filed a bug against the new format in six months) kept as a question; proposal: drop old format in 4.0; two real questions to Noah (enterprise fork still depends on it?; okay announcing in next release notes?) kept, not answered")

# 122
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "how do i set up a vpn on my router without it slowing down netflix and without paying for a subscription"},
   "How do I set up a VPN on my router without it slowing down Netflix and without paying for a subscription?",
   {"must_include": ["VPN", "router", "without it slowing down Netflix", "without paying for a subscription"], "must_not_include": ["split tunneling", "WireGuard"], "min_negations": 2},
   "facts: two constraints, both 'without' (no Netflix slowdown; no paid subscription); not answered")

# 123
R2(QN, {"task": "cleanup",
        "transcript": "priyanka um which build number did the regression pass on uh was it four eighty two or four eighty three"},
   "Priyanka, which build number did the regression pass on? Was it 482 or 483?",
   {"numbers": ["482", "483"], "must_include": ["Priyanka", "build number", "482 or 483"], "must_not_include": ["it passed on"]},
   "facts: alternative build 482 OR 483 kept; question to Priyanka not answered")

# 124
R2(QN, {"task": "cleanup",
        "transcript": "is parquet or avro better for streaming writes into s3"},
   "Is Parquet or Avro better for streaming writes into S3?",
   {"numbers": ["3"], "must_include": ["Parquet or Avro", "streaming writes", "S3"], "must_not_include": ["Avro is better", "row-based"]},
   "facts: alternative Parquet OR Avro kept; not answered")

# 125
R2(QN, {"task": "cleanup", "register": "formal", "header_style": "full",
        "transcript": "wren would it be possible to schedule the phishing awareness training before the end of the quarter or is the budget already used up"},
   "Wren, would it be possible to schedule the phishing awareness training before the end of the quarter, or is the budget already used up?",
   {"must_include": ["Wren", "phishing awareness training", "before the end of the quarter", "budget already used up"], "must_not_include": ["it is possible", "the budget is"]},
   "facts: alternative (schedule before end of quarter OR budget used up) kept; question to Wren, not answered")

# 126
R2(QN, {"task": "cleanup",
        "transcript": "three questions about the mix question one is the vocal sitting too far back question two should the reverb tail be shorter and question three does the low end translate on phone speakers"},
   "Three questions about the mix. Question one: is the vocal sitting too far back? Question two: should the reverb tail be shorter? And question three: does the low end translate on phone speakers?",
   {"must_include": ["Three questions about the mix", "Question one", "Question two", "question three", "too far back", "reverb tail", "phone speakers"],
    "must_not_include": ["1.", "- ", "yes"]},
   "facts: three questions kept in order with the speaker's own 'question one/two/three' labels; prose kept (no list cue like 'bullet' or 'number one'); nothing answered")

# 127
R2(QN, {"task": "cleanup", "instruction": "clean it up for ChatGPT, don't answer it",
        "transcript": "halima asked me what the difference is between a vulnerability scan and a pen test and uh honestly i don't know either um for context we're a small three person studio and the new client contract mentions both of them so i need to know which one we're actually paying for so can you explain it like i'm new to security"},
   "Halima asked me what the difference is between a vulnerability scan and a pen test, and honestly, I don't know either. For context, we're a small three-person studio, and the new client contract mentions both of them, so I need to know which one we're actually paying for. So can you explain it like I'm new to security?",
   {"must_include": ["Halima asked me", "vulnerability scan", "pen test", "honestly", "I don't know either", "three-person studio", "client contract mentions both", "which one we're actually paying for", "like I'm new to security"],
    "must_not_include": ["automated", "a pen test is"], "min_negations": 1},
   "facts: reported question from Halima stays indirect; speaker doesn't know either (negation kept); context: small three-person studio, new client contract mentions both; 'like I'm new to security' is a meaningful constraint, not filler; question for another AI, not answered", pos="before", cx=1)

# 128
R2(QN, {"task": "cleanup", "locale": "en-gb",
        "transcript": "oskar have you finished the stems for the second chorus or are you still re-amping the guitars"},
   "Oskar, have you finished the stems for the second chorus, or are you still re-amping the guitars?",
   {"must_include": ["Oskar", "stems", "second chorus", "re-amping the guitars"], "must_not_include": ["I've finished", "still working"]},
   "facts: alternative finished stems OR still re-amping kept; question to Oskar, not answered")

# 129
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "kenta um can we push the beta to testflight by thursday or uh do the crash fixes need another day"},
   "Kenta, can we push the beta to TestFlight by Thursday, or do the crash fixes need another day?",
   {"must_include": ["Kenta", "TestFlight", "by Thursday", "another day"], "must_not_include": ["Friday", "we can push"]},
   "facts: alternative (TestFlight beta by Thursday OR crash fixes need another day) kept; no date invented; not answered")

# 130
R2(QN, {"task": "cleanup",
        "transcript": "okay i'm building a little budgeting spreadsheet and i want to know um how do i calculate how much i need to save each month to have twelve thousand by next december if i already have three thousand five hundred saved and the account pays four percent interest compounded monthly and can you show the formula in a way that works in google sheets not excel"},
   "I'm building a little budgeting spreadsheet, and I want to know: how do I calculate how much I need to save each month to have 12,000 by next December if I already have 3,500 saved and the account pays 4% interest compounded monthly? And can you show the formula in a way that works in Google Sheets, not Excel?",
   {"numbers": ["12,000", "3,500", "4"], "must_include": ["budgeting spreadsheet", "save each month", "12,000 by next December", "3,500 saved", "4% interest compounded monthly", "Google Sheets, not Excel"],
    "must_not_include": ["PMT", "FV(", "$"], "min_negations": 1},
   "facts: goal 12,000 by next December; already 3,500 saved; 4% compounded monthly (no currency spoken, so no $); formula must work in Google Sheets, NOT Excel; nothing calculated or answered")

# 131
R2(QN, {"task": "cleanup",
        "transcript": "the pipeline failed again at three am and of course who gets paged me so can we please add a retry before it alerts"},
   "The pipeline failed again at 3 a.m., and of course, who gets paged? Me. So can we please add a retry before it alerts?",
   {"numbers": ["3"], "must_include": ["failed again", "3 a.m.", "who gets paged? Me.", "add a retry before it alerts"], "must_not_include": ["on-call"]},
   "facts: pipeline failed AGAIN at 3 a.m.; rhetorical question answered by the speaker ('Me') is kept as spoken; real request: add a retry before alerting")

# 132
R2(QN, {"task": "cleanup", "locale": "en-gb",
        "transcript": "ingrid which lens did you use for the night market shots and did you shoot them handheld or on the mini tripod"},
   "Ingrid, which lens did you use for the night market shots, and did you shoot them handheld or on the mini tripod?",
   {"must_include": ["Ingrid", "which lens", "night market shots", "handheld or on the mini tripod"], "must_not_include": ["35mm", "I used"]},
   "facts: two questions to Ingrid; alternative handheld OR mini tripod kept; not answered")

# 133
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "is ssh key authentication safer than password authentication answer in one word"},
   "Is SSH key authentication safer than password authentication? Answer in one word.",
   {"must_include": ["SSH key authentication", "password authentication", "Answer in one word."], "must_not_include": ["Yes.", "yes"], "ends_with_question": False},
   "facts: dictated question for another AI plus the speaker's own constraint 'Answer in one word.' (part of the text, not a command to this model); not answered")

# 134
R2(QN, {"task": "cleanup", "locale": "en-in",
        "transcript": "sanjay bhai two things on the upi refund bug that the support team escalated yesterday first is it only failing for amounts above two thousand rupees or did you also see it on smaller refunds like the five hundred rupee ones and second did you check it on both the android and ios apps or only android because the customer who complained was on an iphone"},
   "Sanjay bhai, two things on the UPI refund bug that the support team escalated yesterday. First, is it only failing for amounts above ₹2,000, or did you also see it on smaller refunds, like the ₹500 ones? And second, did you check it on both the Android and iOS apps, or only Android, because the customer who complained was on an iPhone?",
   {"numbers": ["2,000", "500"], "must_include": ["Sanjay bhai", "UPI refund bug", "escalated yesterday", "only failing", "above ₹2,000", "like the ₹500 ones", "both the Android and iOS apps", "or only Android", "on an iPhone"], "must_not_include": ["it fails"]},
   "facts: bug escalated yesterday by support; rupees spoken for both amounts -> ₹2,000 and ₹500 ('like' = for example, kept); two questions in order with their alternatives (above ₹2,000 only OR smaller too; both apps OR only Android); reason: complaining customer was on an iPhone; not answered")

# 135
R2(QN, {"task": "prompt", "instruction": "turn this into a prompt for ChatGPT, don't answer it and don't add anything I didn't say",
        "transcript": "um i want to understand why my android app's cold start time jumped from about one point two seconds to almost three seconds after we added the analytics sdk and what i should measure first to find out"},
   "Explain why my Android app's cold start time jumped from about 1.2 seconds to almost 3 seconds after we added the analytics SDK, and tell me what I should measure first to find out.",
   {"format": "prompt", "numbers": ["1.2", "3"], "must_include": ["Android app", "cold start time", "about 1.2 seconds", "almost 3 seconds", "analytics SDK", "measure first"],
    "must_not_include": ["lazy", "initialization", "Systrace", "Perfetto"], "ends_with_question": False},
   "facts: from ABOUT 1.2 s to ALMOST 3 s (both hedges kept) after adding the analytics SDK; two asks (why; what to measure first); prompt only, no answer, no added requirements", pos="before", cx=1)

# 136
R2(QN, {"task": "cleanup",
        "transcript": "wren is the master at minus fourteen lufs or minus nine"},
   "Wren, is the master at minus 14 LUFS or minus 9?",
   {"numbers": ["14", "9"], "must_include": ["Wren", "master", "minus 14 LUFS", "minus 9"], "must_not_include": ["-14 is"]},
   "facts: alternative minus 14 LUFS OR minus 9 kept (signs kept as spoken words); not answered")

# 137
R2(QN, {"task": "cleanup",
        "transcript": "ebele do we still not have a code owner for the docs folder"},
   "Ebele, do we still not have a code owner for the docs folder?",
   {"must_include": ["Ebele", "still not have", "code owner", "docs folder"], "min_negations": 1, "must_not_include": ["we do", "we don't"]},
   "facts: negative question kept ('still not'); not answered")

# 138
R2(QN, {"task": "cleanup",
        "transcript": "tomás the release checklist says we test on three android versions but we only have devices for two of them so are we supposed to use an emulator for the third and if so does that count for sign off or does qa need a physical device every time i don't want to block the release on this but i also don't want to skip it"},
   "Tomás, the release checklist says we test on three Android versions, but we only have devices for two of them. So are we supposed to use an emulator for the third? And if so, does that count for sign-off, or does QA need a physical device every time? I don't want to block the release on this, but I also don't want to skip it.",
   {"must_include": ["Tomás", "three Android versions", "only have devices for two", "emulator for the third", "if so", "sign-off", "physical device every time", "don't want to block the release", "don't want to skip it"],
    "must_not_include": ["emulators count", "you can use"], "min_negations": 2, "ends_with_question": False},
   "facts: checklist says three Android versions, devices for only two; questions (emulator for the third?; IF so, counts for sign-off OR physical device every time?) not answered; two negated wishes kept (don't block release; don't skip it); ends with a statement")

# 139
R2(QN, {"task": "cleanup", "header_style": "full",
        "transcript": "riya is the snowflake warehouse set to x small no wait small and should we bump it to medium for the backfill"},
   "Riya, is the Snowflake warehouse set to small, and should we bump it to medium for the backfill?",
   {"must_include": ["Riya", "Snowflake warehouse", "set to small", "medium for the backfill"], "must_not_include": ["x-small", "x small", "XS"]},
   "facts: self-correction inside the question applied: 'x small no wait small' -> small; second question (bump to medium for the backfill?) kept; not answered")

# 140
R2(QN, {"task": "cleanup", "locale": "en-gb", "instruction": "keep it as my questions, British spelling",
        "transcript": "we're a small team of five working out of a shared studio and um i'm trying to tidy up our security a bit so how often should we rotate the shared wifi password and is it worth setting up a separate guest network if clients only visit once a month and if we do set one up should the printer stay on the main network or move to the guest one"},
   "We're a small team of five working out of a shared studio, and I'm trying to tidy up our security a bit. So how often should we rotate the shared Wi-Fi password, and is it worth setting up a separate guest network if clients only visit once a month? And if we do set one up, should the printer stay on the main network or move to the guest one?",
   {"must_include": ["team of five", "shared studio", "shared Wi-Fi password", "separate guest network", "if clients only visit once a month", "if we do set one up", "main network or move to the guest one"], "must_not_include": ["every 90 days", "yes"]},
   "facts: team of five in a shared studio; questions kept: rotation frequency; guest network worth it IF clients only visit once a month; IF set up, printer on main OR guest network; not answered", pos="before", cx=1)

# ---------------------------------------------------------------------------
# chunk 2: smart_formatting (141-180)
# ---------------------------------------------------------------------------

# 141
R2(SF, {"task": "cleanup",
        "transcript": "send me the logs from tuesday semicolon monday's are fine period"},
   "Send me the logs from Tuesday; Monday's are fine.",
   {"must_include": ["Tuesday;", "Monday's are fine."], "must_not_include": ["semicolon", "period"]},
   "facts: Tuesday's logs wanted, Monday's are fine; spoken semicolon and period applied")

# 142
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "the free trial period ends on friday so cancel before then if we're not keeping it"},
   "The free trial period ends on Friday, so cancel before then if we're not keeping it.",
   {"must_include": ["free trial period ends on Friday", "if we're not keeping it"], "min_negations": 1},
   "facts: 'period' is a literal word here (trial period), not punctuation; ends Friday; conditional 'if we're not keeping it' kept")

# 143
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "so the export uses a semicolon as the separator um not a comma so excel opens everything in one column"},
   "The export uses a semicolon as the separator, not a comma, so Excel opens everything in one column.",
   {"must_include": ["a semicolon as the separator", "not a comma", "Excel", "one column"], "min_negations": 1},
   "facts: 'semicolon' and 'comma' are literal words (CSV separators), not punctuation commands; separator is a semicolon, NOT a comma")

# 144
R2(SF, {"task": "cleanup",
        "transcript": "so the kick is fine the snare is fine dot dot dot but the hats are way too loud period"},
   "The kick is fine, the snare is fine... but the hats are way too loud.",
   {"must_include": ["kick is fine", "snare is fine...", "hats are way too loud."], "must_not_include": ["dot dot dot", "period"]},
   "facts: spoken ellipsis applied as '...'; kick and snare fine, hats way too loud")

# 145
R2(SF, {"task": "cleanup",
        "transcript": "the backfill job open bracket the one that reprocesses march close bracket is still running so don't touch the staging tables"},
   "The backfill job (the one that reprocesses March) is still running, so don't touch the staging tables.",
   {"must_include": ["(the one that reprocesses March)", "still running", "don't touch the staging tables"], "must_not_include": ["open bracket", "close bracket"], "min_negations": 1},
   "facts: spoken brackets become parentheses; backfill reprocessing March still running; do NOT touch staging tables")

# 146
R2(SF, {"task": "cleanup", "locale": "en-gb", "header_style": "full",
        "transcript": "notes from the client call colon new paragraph they loved the harbour edits but want the shadows lifted a bit on frames twelve to eighteen period the art director said and i quote open quote less moody comma more morning close quote period new paragraph next steps colon i'll redo those seven frames by wednesday and ingrid will check the colour on the print proofs before we send anything period"},
   "Notes from the client call:\n\nThey loved the harbour edits but want the shadows lifted a bit on frames 12 to 18. The art director said, and I quote, \"Less moody, more morning.\"\n\nNext steps: I'll redo those seven frames by Wednesday, and Ingrid will check the colour on the print proofs before we send anything.",
   {"numbers": ["12", "18"], "must_include": ["Notes from the client call:", "frames 12 to 18", "and I quote", "\"Less moody, more morning", "Next steps:", "seven frames by Wednesday", "Ingrid", "print proofs"],
    "must_not_include": ["new paragraph", "open quote", "colon"]},
   "facts: shadows lifted a bit on frames 12 to 18; quoted words kept exactly inside quote marks; speaker redoes seven frames by Wednesday (own commitment); Ingrid checks colour on print proofs before anything is sent; spoken paragraphs, colons and quotes applied; en-gb spelling")

# 147
R2(SF, {"task": "rewrite", "format": "email", "sender": "Riya", "recipient": "Oskar",
        "transcript": "tell oskar the migration checklist for saturday is bullet point freeze writes on the orders database at six am bullet point snapshot the replica bullet point run the schema migration bullet point validate row counts against the snapshot and uh tell him if the counts don't match we roll back no discussion and also that i'll be on the bridge call from five thirty"},
   "Hi Oskar,\n\nThe migration checklist for Saturday is:\n- Freeze writes on the orders database at 6 a.m.\n- Snapshot the replica\n- Run the schema migration\n- Validate row counts against the snapshot\n\nIf the counts don't match, we roll back, no discussion. Also, I'll be on the bridge call from 5:30.\n\nBest,\nRiya",
   {"format": "email", "numbers": ["6", "5:30"], "must_include": ["Hi Oskar,", "Saturday", "- Freeze writes on the orders database at 6 a.m.", "- Snapshot the replica", "- Run the schema migration", "- Validate row counts", "If the counts don't match", "roll back", "no discussion", "bridge call from 5:30", "Riya"],
    "must_not_include": ["bullet point", "Subject:", "5:30 a.m.", "5:30 p.m."], "min_negations": 2},
   "facts: dictated list inside an email kept as four bullets in order (freeze writes at 6 a.m.; snapshot replica; run migration; validate row counts); rule: IF counts don't match, roll back, no discussion; Riya's own commitment: on the bridge call from 5:30 (no a.m./p.m. spoken, none added); sign-off from Sender Riya only")

# 148
R2(SF, {"task": "cleanup",
        "transcript": "test summary for build nine one four colon login passed on all devices semicolon checkout failed twice on the pixel seven semicolon push notifications weren't tested because the sandbox was down period i'll rerun checkout after lunch period new paragraph also the dark mode toggle is still missing on tablets comma but that's a known issue so please don't file it again period"},
   "Test summary for build 914: login passed on all devices; checkout failed twice on the Pixel 7; push notifications weren't tested because the sandbox was down. I'll rerun checkout after lunch.\n\nAlso, the dark mode toggle is still missing on tablets, but that's a known issue, so please don't file it again.",
   {"numbers": ["914", "7"], "must_include": ["build 914:", "login passed on all devices;", "failed twice on the Pixel 7;", "weren't tested", "sandbox was down", "rerun checkout after lunch", "dark mode toggle is still missing on tablets", "known issue", "don't file it again"],
    "must_not_include": ["semicolon", "colon", "new paragraph"], "min_negations": 1},
   "facts: build 914; login passed on all devices; checkout failed TWICE on Pixel 7; push NOT tested (sandbox down); speaker's own commitment to rerun after lunch; dark mode toggle still missing on tablets, known issue, do NOT file again; spoken colon/semicolons/paragraph applied")

# 149
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "the billing period resets on the first so any refunds after that show up next period comma not this one"},
   "The billing period resets on the 1st, so any refunds after that show up next period, not this one.",
   {"numbers": ["1"], "must_include": ["billing period resets on the 1st", "show up next period, not this one"], "must_not_include": ["comma"], "min_negations": 1},
   "facts: both 'period's are literal words (billing period, next period); only the spoken 'comma' is punctuation; resets on the 1st; refunds show up next period, NOT this one")

# 150
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "wait the label approved the remix exclamation mark when did that happen question mark"},
   "Wait, the label approved the remix! When did that happen?",
   {"must_include": ["the label approved the remix!", "When did that happen?"], "must_not_include": ["exclamation mark", "question mark"]},
   "facts: 'wait' is surprise, not a self-correction; spoken exclamation and question marks applied; question not answered")

# 151
R2(SF, {"task": "cleanup",
        "transcript": "release notes for version three point one new line new colon dark mode for the mixer view new line fixed colon audio dropouts when changing buffer size new line removed colon the legacy midi import"},
   "Release notes for version 3.1\nNew: dark mode for the mixer view\nFixed: audio dropouts when changing buffer size\nRemoved: the legacy MIDI import",
   {"numbers": ["3.1"], "must_include": ["version 3.1", "New: dark mode", "Fixed: audio dropouts", "Removed: the legacy MIDI import"], "must_not_include": ["new line", "colon", "- "]},
   "facts: each spoken 'new line' starts a line; the word 'new' before 'colon' is a literal label (New:), not a line command; version 3.1; label lines kept without added sentence periods as dictated; no bullets added")

# 152
R2(SF, {"task": "cleanup", "locale": "en-in",
        "transcript": "my rent is twenty two thousand open bracket including maintenance close bracket and the deposit was three months of that"},
   "My rent is 22,000 (including maintenance), and the deposit was three months of that.",
   {"numbers": ["22,000"], "must_include": ["22,000 (including maintenance)", "three months of that"], "must_not_include": ["₹", "66,000", "open bracket"]},
   "facts: rent 22,000 including maintenance (no currency spoken, so no ₹); deposit = three months of rent, not computed; spoken brackets -> parentheses")

# 153
R2(SF, {"task": "cleanup",
        "transcript": "dear priyanka comma new paragraph thank you for flagging the suspicious login on the finance laptop period we have reset the password comma revoked all active sessions comma and enabled two factor authentication for that account period new paragraph could you please confirm whether you clicked any link in the email from yesterday question mark if you did comma there is no need to worry comma just let us know so we can scan the device period new paragraph regards comma new line halima"},
   "Dear Priyanka,\n\nThank you for flagging the suspicious login on the finance laptop. We have reset the password, revoked all active sessions, and enabled two-factor authentication for that account.\n\nCould you please confirm whether you clicked any link in the email from yesterday? If you did, there is no need to worry, just let us know so we can scan the device.\n\nRegards,\nHalima",
   {"must_include": ["Dear Priyanka,", "suspicious login", "finance laptop", "reset the password, revoked all active sessions, and enabled two-factor authentication", "email from yesterday?", "If you did", "no need to worry", "Regards,\nHalima"],
    "must_not_include": ["new paragraph", "new line", "comma"], "min_negations": 1},
   "facts: dictated email cleaned with its spoken layout (paragraphs, line break before the dictated sign-off Halima); three actions done (password reset, sessions revoked, 2FA enabled); question about clicking a link in yesterday's email kept; conditional reassurance 'if you did, no need to worry' kept")

# 154
R2(SF, {"task": "cleanup",
        "transcript": "for the jam session tonight bring a few things colon your audio interface comma headphones comma a long xlr cable and the usb drive with the stems"},
   "For the jam session tonight, bring a few things: your audio interface, headphones, a long XLR cable and the USB drive with the stems.",
   {"format": "prose", "must_include": ["jam session tonight", "a few things:", "audio interface", "headphones", "long XLR cable", "USB drive with the stems"], "must_not_include": ["- ", "colon"]},
   "facts: four items kept inline with the speaker's own colon and commas; cleanup keeps the dictated prose form (no bullet cue dictated), so no list is made")

# 155
R2(SF, {"task": "rewrite", "format": "email", "sender": "Priyanka", "recipient": "Kenta",
        "transcript": "hi kenta to reproduce the bug number one install build nine two seven from testflight number two log in with the test account number three turn on airplane mode and open the downloads tab number four turn airplane mode off it crashes about two seconds later every time this is on the iphone twelve with ios seventeen point four i haven't tried other devices yet"},
   "Hi Kenta,\n\nTo reproduce the bug:\n1. Install build 927 from TestFlight.\n2. Log in with the test account.\n3. Turn on airplane mode and open the Downloads tab.\n4. Turn airplane mode off.\n\nIt crashes about 2 seconds later, every time. This is on the iPhone 12 with iOS 17.4; I haven't tried other devices yet.\n\nBest,\nPriyanka",
   {"format": "email", "numbers": ["927", "2", "12", "17.4"], "must_include": ["Hi Kenta,", "build 927", "TestFlight", "test account", "airplane mode", "Downloads tab", "about 2 seconds later, every time", "iPhone 12", "iOS 17.4", "haven't tried other devices yet", "Priyanka"],
    "must_not_include": ["number one", "Subject:"], "min_negations": 1},
   "facts: dictated 'number one...four' steps kept as a numbered list inside the email, in order; build 927; crash ABOUT 2 seconds after airplane mode is turned off, every time; seen on iPhone 12 / iOS 17.4, other devices NOT tried yet; sign-off from Sender Priyanka only")

# 156
R2(SF, {"task": "cleanup",
        "transcript": "the error just says open quote permission denied close quote nothing else no error code and nothing in the logs either"},
   "The error just says \"permission denied,\" nothing else, no error code and nothing in the logs either.",
   {"must_include": ["\"permission denied", "nothing else", "no error code", "nothing in the logs either"], "must_not_include": ["open quote", "close quote"], "min_negations": 3},
   "facts: quoted error text kept as spoken inside quote marks; three negations kept (nothing else; no error code; nothing in the logs)")

# 157
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "um the file name has a colon in it which windows doesn't allow so uh rename it before you upload"},
   "The file name has a colon in it, which Windows doesn't allow, so rename it before you upload.",
   {"must_include": ["has a colon in it", "Windows doesn't allow", "rename it before you upload"], "must_not_include": [":"], "min_negations": 1},
   "facts: 'colon' is a literal word (a character in the file name), not punctuation; Windows doesn't allow it; rename before upload")

# 158
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "the link breaks because there's a second question mark in the query string"},
   "The link breaks because there's a second question mark in the query string.",
   {"must_include": ["a second question mark in the query string"], "must_not_include": ["??"]},
   "facts: 'question mark' is a literal word here (a character in the URL), not punctuation, so it is written out and the sentence stays a statement. Waiver: the checker treats any spoken 'question mark' in a cleanup source as a dictated question and flags question_lost",
   waivers=["question_lost"])

# 159
R2(SF, {"task": "cleanup",
        "transcript": "okay idea for the bridge dot dot dot what if we drop everything except the pad and the vocal for eight bars and then bring the drums back with a reverse cymbal question mark new paragraph also note to self colon the vocal take from tuesday is better than the one from yesterday comma keep that one period and remind me to send oskar a rough bounce tonight period"},
   "Idea for the bridge... what if we drop everything except the pad and the vocal for eight bars and then bring the drums back with a reverse cymbal?\n\nAlso, note to self: the vocal take from Tuesday is better than the one from yesterday, keep that one. And remind me to send Oskar a rough bounce tonight.",
   {"must_include": ["Idea for the bridge...", "except the pad and the vocal", "eight bars", "reverse cymbal?", "note to self:", "take from Tuesday is better than the one from yesterday", "keep that one.", "send Oskar a rough bounce tonight"],
    "must_not_include": ["dot dot dot", "new paragraph", "colon"], "ends_with_question": False},
   "facts: suggestion phrased as a question kept as a question; eight bars; Tuesday's take is better than yesterday's, keep Tuesday's; reminder to send Oskar a rough bounce tonight; spoken ellipsis, paragraph, colon and commas applied")

# 160
R2(SF, {"task": "cleanup",
        "transcript": "heads up colon standup moved to nine thirty tomorrow comma same link period"},
   "Heads up: standup moved to 9:30 tomorrow, same link.",
   {"numbers": ["9:30"], "must_include": ["Heads up:", "9:30 tomorrow", "same link."], "must_not_include": ["colon", "comma"]},
   "facts: standup moved to 9:30 tomorrow (no a.m./p.m. spoken, none added); same link")

# 161
R2(SF, {"task": "cleanup", "format": "bullets",
        "transcript": "three things i need before the security review the firewall rules for the staging vpc the list of admin accounts with mfa disabled and the last pen test report"},
   "Three things I need before the security review:\n- The firewall rules for the staging VPC\n- The list of admin accounts with MFA disabled\n- The last pen test report",
   {"format": "bullets", "must_include": ["security review", "firewall rules for the staging VPC", "admin accounts with MFA disabled", "last pen test report"]},
   "facts: Format bullets set by header; exactly three items in spoken order; 'with MFA disabled' kept")

# 162
R2(SF, {"task": "cleanup",
        "transcript": "quick update on the warehouse costs colon last month we spent about four thousand two hundred dollars open bracket up from three thousand one hundred in august close bracket semicolon most of that came from the nightly full refresh of the events table period if we switch it to incremental comma i think we can get back under three thousand five hundred comma but i haven't tested it yet period"},
   "Quick update on the warehouse costs: last month we spent about $4,200 (up from $3,100 in August); most of that came from the nightly full refresh of the events table. If we switch it to incremental, I think we can get back under $3,500, but I haven't tested it yet.",
   {"numbers": ["4,200", "3,100", "3,500"], "must_include": ["warehouse costs:", "last month", "about $4,200", "up from $3,100 in August", "nightly full refresh", "events table", "If we switch it to incremental", "I think", "under $3,500", "haven't tested it yet"],
    "must_not_include": ["semicolon", "open bracket"], "min_negations": 1},
   "facts: about $4,200 last month, up from 3,100 in August; under 3,500 is conditional on switching to incremental and hedged ('I think'), NOT tested yet. Currency choice: dollars were spoken once for this same running cost, so $ is applied to all three amounts in the record")

# 163
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "add a comma after the word however in the second line of the hook and take out the one at the end of the verse"},
   "Add a comma after the word however in the second line of the hook, and take out the one at the end of the verse.",
   {"must_include": ["Add a comma after the word however", "second line of the hook", "take out the one at the end of the verse"], "must_not_include": ["however,"]},
   "facts: 'comma' is a literal word in an editing note, not punctuation; written out; two edits kept (add after 'however' in line two of the hook; remove the one at the end of the verse)")

# 164
R2(SF, {"task": "cleanup", "locale": "en-in",
        "transcript": "ayaan comma the credit card statement shows two charges of four ninety nine on the same day period new line one of them must be the netflix renewal comma but what's the other one question mark new line if it's the gym app again comma cancel it this time comma we agreed last month period and um please screenshot the statement before you call the bank period"},
   "Ayaan, the credit card statement shows two charges of 499 on the same day.\nOne of them must be the Netflix renewal, but what's the other one?\nIf it's the gym app again, cancel it this time, we agreed last month. And please screenshot the statement before you call the bank.",
   {"numbers": ["499"], "must_include": ["Ayaan,", "two charges of 499 on the same day.", "Netflix renewal", "what's the other one?", "If it's the gym app again, cancel it this time", "we agreed last month", "screenshot the statement before you call the bank"], "must_not_include": ["₹", "new line"]},
   "facts: two charges of 499 the same day (no currency spoken, so no ₹); one must be Netflix; question about the other kept, not answered; IF it's the gym app again, cancel it (agreed last month); screenshot the statement before calling the bank; spoken new lines applied")

# 165
R2(SF, {"task": "cleanup", "format": "numbered", "header_style": "full",
        "transcript": "to flash the test build first plug the phone in with usb debugging on then run the install script and finally clear the app data before you open it"},
   "To flash the test build:\n1. Plug the phone in with USB debugging on.\n2. Run the install script.\n3. Clear the app data before you open it.",
   {"format": "numbered", "must_include": ["To flash the test build:", "USB debugging on", "Run the install script", "Clear the app data before you open it"], "must_not_include": ["first", "finally"]},
   "facts: Format numbered set by header; order cue first/then/finally -> three steps in spoken order; ordering words become the numbering")

# 166
R2(SF, {"task": "cleanup", "instruction": "fix the punctuation, but don't turn the fixes into a list",
        "transcript": "okay so monthly money check in colon new paragraph income was the same as last month semicolon spending was up about three hundred mostly because of the car service period new paragraph the savings goal for the trip is at sixty percent dot dot dot which is behind where i wanted to be by now period new paragraph things to fix colon cancel the second streaming plan comma move the gym payment to the first of the month comma and stop buying lunch on weekdays period"},
   "Monthly money check-in:\n\nIncome was the same as last month; spending was up about 300, mostly because of the car service.\n\nThe savings goal for the trip is at 60%... which is behind where I wanted to be by now.\n\nThings to fix: cancel the second streaming plan, move the gym payment to the 1st of the month, and stop buying lunch on weekdays.",
   {"numbers": ["300", "60", "1"], "must_include": ["Monthly money check-in:", "same as last month;", "up about 300", "car service", "savings goal for the trip", "60%...", "behind where I wanted to be", "Things to fix:", "second streaming plan", "1st of the month", "stop buying lunch on weekdays"],
    "must_not_include": ["$", "₹", "- ", "new paragraph"]},
   "facts: instruction: no list; income same; spending up ABOUT 300 (no currency spoken) mostly from car service; trip savings goal at 60%, behind plan; three fixes kept inline as dictated (cancel second streaming plan; gym payment to the 1st; stop weekday lunches); no list made in cleanup", cx=1)

# 167
R2(SF, {"task": "cleanup",
        "transcript": "we just hit ten thousand downloads exclamation mark"},
   "We just hit 10,000 downloads!",
   {"numbers": ["10,000"], "must_include": ["10,000 downloads!"], "must_not_include": ["exclamation mark"]},
   "facts: 10,000 downloads; spoken exclamation mark applied")

# 168
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "halima literally asked open quote is this the final mix question mark close quote and i said not yet"},
   "Halima literally asked, \"Is this the final mix?\" and I said not yet.",
   {"must_include": ["Halima literally asked", "\"Is this the final mix?\"", "not yet"], "must_not_include": ["open quote", "question mark"], "min_negations": 1, "behavior": "transform"},
   "facts: quoted question with its own question mark inside the quotes; the speaker's answer 'not yet' is part of the dictation and kept")

# 169
R2(SF, {"task": "cleanup", "locale": "en-gb",
        "transcript": "tomás for the exhibition prints we need eight at a three open bracket the landscape ones close bracket and four at a four semicolon all on the matte paper not the gloss period can you get them to the framer by the twentieth question mark the frames are already ordered so it's just the prints comma and please keep the receipt for the reimbursement period"},
   "Tomás, for the exhibition prints we need eight at A3 (the landscape ones) and four at A4; all on the matte paper, not the gloss. Can you get them to the framer by the 20th? The frames are already ordered, so it's just the prints, and please keep the receipt for the reimbursement.",
   {"numbers": ["20"], "must_include": ["Tomás", "eight at A3 (the landscape ones)", "four at A4;", "matte paper, not the gloss", "framer by the 20th?", "frames are already ordered", "just the prints", "keep the receipt for the reimbursement"], "must_not_include": ["semicolon", "glossy paper is"], "min_negations": 1},
   "facts: eight prints at A3 (the landscape ones) and four at A4; matte, NOT gloss; to the framer by the 20th (question kept, not answered); frames already ordered, only prints needed; keep the receipt for reimbursement; spoken brackets/semicolon applied")

# 170
R2(SF, {"task": "cleanup",
        "transcript": "noted comma thanks exclamation mark"},
   "Noted, thanks!",
   {"must_include": ["Noted, thanks!"], "must_not_include": ["comma"]},
   "facts: two words with spoken comma and exclamation mark applied; nothing added")

# 171
R2(SF, {"task": "rewrite", "format": "email", "sender": "Ebele",
        "transcript": "hi everyone the call for talks for the maintainers summit is open until the fifteenth we're looking for talks on bullet onboarding new contributors bullet funding and sponsorship bullet security response in small projects submissions are twenty minutes max and we can't cover travel this year if you're not sure whether your idea fits just send a short abstract anyway and the program committee will decide"},
   "Hi everyone,\n\nThe call for talks for the maintainers summit is open until the 15th. We're looking for talks on:\n- Onboarding new contributors\n- Funding and sponsorship\n- Security response in small projects\n\nSubmissions are 20 minutes max, and we can't cover travel this year. If you're not sure whether your idea fits, just send a short abstract anyway, and the program committee will decide.\n\nBest,\nEbele",
   {"format": "email", "numbers": ["15", "20"], "must_include": ["Hi everyone,", "maintainers summit", "until the 15th", "- Onboarding new contributors", "- Funding and sponsorship", "- Security response in small projects", "20 minutes max", "can't cover travel this year", "short abstract anyway", "program committee will decide", "Ebele"],
    "must_not_include": ["bullet", "Subject:"], "min_negations": 2},
   "facts: dictated greeting 'hi everyone' kept; call for talks open until the 15th; three dictated bullets kept in order; talks 20 minutes max; can NOT cover travel this year; if unsure, send a short abstract and the program committee decides; sign-off from Sender Ebele only")

# 172
R2(SF, {"task": "cleanup", "header_style": "full",
        "transcript": "kenta the build is uploading dot dot dot ninety percent dot dot dot okay done"},
   "Kenta, the build is uploading... 90%... okay, done.",
   {"numbers": ["90"], "must_include": ["Kenta", "uploading...", "90%...", "done"], "must_not_include": ["dot dot dot"]},
   "facts: live progress narration; spoken ellipses applied; 90%; 'okay, done' carries meaning (upload finished)")

# 173
R2(SF, {"task": "cleanup",
        "transcript": "so um the export aspect ratio should be four colon five for the instagram feed post and nine colon sixteen for the stories version"},
   "The export aspect ratio should be 4:5 for the Instagram feed post and 9:16 for the stories version.",
   {"must_include": ["4:5", "Instagram feed post", "9:16", "stories version"], "must_not_include": ["colon", "4/5", "16:9"]},
   "facts: spoken 'four colon five' and 'nine colon sixteen' are aspect ratios, written 4:5 (feed) and 9:16 (stories), order kept. Waiver: the checker reads 9:16 as a clock time and cannot find the 16 inside it",
   waivers=["number_missing"])

# 174
R2(SF, {"task": "cleanup", "instruction": "keep my line breaks and labels exactly",
        "transcript": "bug report colon new line title colon app freezes on the payment screen new line steps colon open the app comma go to cart comma tap pay comma then rotate the phone new line expected colon the screen rotates normally new line actual colon the screen freezes for about five seconds and then the app closes open bracket no crash dialog close bracket new line device colon pixel eight on android fifteen"},
   "Bug report:\nTitle: App freezes on the payment screen\nSteps: open the app, go to cart, tap pay, then rotate the phone\nExpected: the screen rotates normally\nActual: the screen freezes for about 5 seconds and then the app closes (no crash dialog)\nDevice: Pixel 8 on Android 15",
   {"numbers": ["5", "8", "15"], "must_include": ["Bug report:", "Title: App freezes on the payment screen", "Steps: open the app, go to cart, tap pay, then rotate the phone", "Expected:", "Actual:", "about 5 seconds", "(no crash dialog)", "Device: Pixel 8 on Android 15"],
    "must_not_include": ["new line", "colon", "- "], "min_negations": 1},
   "facts: field lines kept exactly as dictated (Title/Steps/Expected/Actual/Device); freeze ABOUT 5 seconds then app closes with NO crash dialog; Pixel 8, Android 15; label lines left without added sentence periods", pos="before", cx=1)

# 175
R2(SF, {"task": "cleanup",
        "transcript": "ever notice how every mix sounds better at two am question mark yeah me too period that's why i check everything again in the morning period"},
   "Ever notice how every mix sounds better at 2 a.m.? Yeah, me too. That's why I check everything again in the morning.",
   {"numbers": ["2"], "must_include": ["2 a.m.?", "Yeah, me too.", "check everything again in the morning."], "must_not_include": ["question mark"], "ends_with_question": False},
   "facts: rhetorical question answered by the speaker ('Yeah, me too') kept as dictated; 2 a.m.")

# 176
R2(SF, {"task": "cleanup", "locale": "en-in",
        "transcript": "the cooling off period on the loan app is fourteen days comma so we can still cancel without any fee period"},
   "The cooling-off period on the loan app is 14 days, so we can still cancel without any fee.",
   {"numbers": ["14"], "must_include": ["cooling-off period", "14 days", "without any fee."], "must_not_include": ["comma"], "min_negations": 1},
   "facts: first 'period' is literal (cooling-off period), the last one is punctuation; 14 days; cancel WITHOUT any fee")

# 177
R2(SF, {"task": "cleanup",
        "transcript": "usage terms for the band photos colon web and social use is included semicolon print use needs a separate license semicolon and no edits to the images without my written approval period if anyone asks about exclusivity comma there isn't any comma they're free to license the outtakes elsewhere period credit line colon open quote photo by noah close quote"},
   "Usage terms for the band photos: web and social use is included; print use needs a separate license; and no edits to the images without my written approval. If anyone asks about exclusivity, there isn't any, they're free to license the outtakes elsewhere. Credit line: \"Photo by Noah\"",
   {"must_include": ["Usage terms for the band photos:", "web and social use is included;", "print use needs a separate license;", "no edits to the images without my written approval", "there isn't any", "license the outtakes elsewhere", "Credit line: \"Photo by Noah\""],
    "must_not_include": ["semicolon", "open quote"], "min_negations": 2},
   "facts: web and social included; print needs a separate license; NO edits WITHOUT written approval; NO exclusivity (they may license the outtakes elsewhere); credit line quoted exactly; no period added after the quoted credit line because none was dictated after it")

# 178
R2(SF, {"task": "cleanup",
        "transcript": "we need a follow dash up with the mastering engineer on the twenty fifth"},
   "We need a follow-up with the mastering engineer on the 25th.",
   {"numbers": ["25"], "must_include": ["follow-up", "mastering engineer", "the 25th"], "must_not_include": ["dash"]},
   "facts: spoken dash inside a compound written as a hyphen; on the 25th")

# 179
R2(SF, {"task": "cleanup", "locale": "en-in", "header_style": "full",
        "transcript": "team update new paragraph the gst invoice export is fixed in the web app but not yet in the android app period sanjay is testing the android fix today and if it passes we'll ship it tomorrow morning period new paragraph also comma please stop sharing customer screenshots in the general channel semicolon use the support channel instead period if anyone already shared one comma delete it and tell halima period"},
   "Team update\n\nThe GST invoice export is fixed in the web app but not yet in the Android app. Sanjay is testing the Android fix today, and if it passes, we'll ship it tomorrow morning.\n\nAlso, please stop sharing customer screenshots in the general channel; use the support channel instead. If anyone already shared one, delete it and tell Halima.",
   {"must_include": ["Team update", "GST invoice export", "fixed in the web app but not yet in the Android app", "Sanjay is testing", "today", "if it passes, we'll ship it tomorrow morning", "stop sharing customer screenshots", "general channel;", "support channel instead", "If anyone already shared one, delete it and tell Halima."],
    "must_not_include": ["new paragraph", "semicolon"], "min_negations": 1},
   "facts: export fixed on web, NOT yet on Android; Sanjay tests today; shipping tomorrow morning is conditional on the test passing; stop sharing screenshots in general, use support channel; anyone who already shared one deletes it and tells Halima; heading line kept without added punctuation since none was dictated")

# 180
R2(SF, {"task": "cleanup",
        "transcript": "the button label should say open quote save draft close quote not open quote save close quote"},
   "The button label should say \"save draft\", not \"save\".",
   {"must_include": ["\"save draft\"", "not \"save\""], "must_not_include": ["open quote", "close quote"], "min_negations": 1},
   "facts: two quoted labels kept exactly as spoken (lowercase, no casing invented); label is 'save draft', NOT 'save'; punctuation kept outside the quotes so the literal labels stay exact")

# ---------------------------------------------------------------------------
# chunk 3: no_markdown / protected literals (181-225)
# ---------------------------------------------------------------------------

# 181
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "and uh set the retry underscore count key to three in the config json and leave the timeout key alone it's fine at thirty"},
   "Set the retry_count key to 3 in the config JSON, and leave the timeout key alone; it's fine at 30.",
   {"numbers": ["3", "30"], "must_include": ["retry_count", "config JSON", "leave the timeout key alone", "fine at 30"], "must_not_include": ["`", "underscore", "retryCount"]},
   "facts: JSON key rebuilt from the spoken 'underscore' as retry_count; value 3 (a config value, so a digit); timeout key untouched, stays 30; no code formatting under plain")

# 182
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "the api returns the total in a field called total underscore amount underscore cents comma not just amount period"},
   "The API returns the total in a field called total_amount_cents, not just amount.",
   {"must_include": ["total_amount_cents", "not just amount"], "must_not_include": ["`", "underscore", "totalAmountCents"], "min_negations": 1},
   "facts: field name total_amount_cents rebuilt exactly from spoken underscores; NOT just 'amount'")

# 183
R2(NM, {"task": "cleanup",
        "transcript": "um the username validation uses the regex ^[a-z0-9_-]{3,16}$ so uppercase usernames will fail and uh we should probably document that"},
   "The username validation uses the regex ^[a-z0-9_-]{3,16}$, so uppercase usernames will fail, and we should probably document that.",
   {"must_include": ["^[a-z0-9_-]{3,16}$", "uppercase usernames will fail", "probably document that"], "must_not_include": ["`", "a-zA-Z"]},
   "facts: regex kept byte for byte; uppercase usernames will fail; hedge 'probably' kept")

# 184
R2(NM, {"task": "cleanup",
        "transcript": "can you run SELECT COUNT(*) FROM orders WHERE status = 'failed'; on the replica and tell me the number"},
   "Can you run SELECT COUNT(*) FROM orders WHERE status = 'failed'; on the replica and tell me the number?",
   {"must_include": ["SELECT COUNT(*) FROM orders WHERE status = 'failed';", "on the replica"], "must_not_include": ["`", "primary"]},
   "facts: SQL snippet kept byte for byte (including the trailing semicolon); run on the replica; request stays a question")

# 185
R2(NM, {"task": "cleanup",
        "transcript": "run the suite with pytest -x --maxfail=2 -k 'not slow' so it stops early and skips the slow ones"},
   "Run the suite with pytest -x --maxfail=2 -k 'not slow' so it stops early and skips the slow ones.",
   {"numbers": ["2"], "must_include": ["pytest -x --maxfail=2 -k 'not slow'", "skips the slow ones"], "must_not_include": ["`", "--max-fail"], "min_negations": 1},
   "facts: CLI flags kept exactly (-x, --maxfail=2, -k 'not slow'); the 'not' inside the filter expression is part of the literal")

# 186
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "bump the package from 1.9.3 to 2.0.0-rc.1 but uh don't publish it to npm yet"},
   "Bump the package from 1.9.3 to 2.0.0-rc.1, but don't publish it to npm yet.",
   {"must_include": ["1.9.3", "2.0.0-rc.1", "don't publish it to npm yet"], "must_not_include": ["`", "2.0.0 "], "min_negations": 1},
   "facts: versions kept exactly (from 1.9.3 to 2.0.0-rc.1); do NOT publish to npm yet; npm stays lowercase")

# 187
R2(NM, {"task": "cleanup",
        "transcript": "the vpn gateway is at 192.0.2.10 on port 51820 and the dns server is 198.51.100.53"},
   "The VPN gateway is at 192.0.2.10 on port 51820, and the DNS server is 198.51.100.53.",
   {"numbers": ["51820"], "must_include": ["192.0.2.10", "port 51820", "198.51.100.53"], "must_not_include": ["`", "51,820"]},
   "facts: IPv4 addresses (documentation ranges) and port 51820 kept exactly; port gets no thousands separator")

# 188
R2(NM, {"task": "cleanup",
        "transcript": "ssh into one nine two dot zero dot two dot forty five on port twenty two and check the disk usage"},
   "SSH into 192.0.2.45 on port 22 and check the disk usage.",
   {"numbers": ["22"], "must_include": ["192.0.2.45", "port 22", "disk usage"], "must_not_include": ["`", " dot ", "192.0.2.4.5"]},
   "facts: spoken IPv4 rebuilt as 192.0.2.45 (one nine two dot zero dot two dot forty five); port 22. Waiver: the checker reads the octets as separate numbers (0, 2, 45) and cannot find them inside the dotted address, which is exact",
   waivers=["number_missing"])

# 189
R2(NM, {"task": "cleanup", "header_style": "full", "instruction": "keep every port number exactly",
        "transcript": "okay so on the monitoring box grafana runs on port three thousand and prometheus is on nine zero nine zero and the node exporter is on nine one zero zero so don't open any of them to the internet um if someone needs remote access they go through the vpn and if the vpn is down they wait no exceptions"},
   "On the monitoring box, Grafana runs on port 3000, Prometheus is on 9090, and the node exporter is on 9100, so don't open any of them to the internet. If someone needs remote access, they go through the VPN, and if the VPN is down, they wait, no exceptions.",
   {"numbers": ["3000", "9090", "9100"], "must_include": ["monitoring box", "port 3000", "Prometheus is on 9090", "node exporter is on 9100", "don't open any of them to the internet", "go through the VPN", "if the VPN is down, they wait", "no exceptions"],
    "must_not_include": ["`", "3,000", "9,090", "9,100"], "min_negations": 2},
   "facts: ports 3000, 9090, 9100 written without separators (port numbers are identifiers); do NOT open any to the internet; remote access only via VPN; IF the VPN is down they wait, no exceptions", pos="before", cx=1)

# 190
R2(NM, {"task": "cleanup",
        "transcript": "the cleanup job runs on 30 2 * * 1-5 so weekdays at two thirty am uh please don't change that without asking ingrid because the backups start at three and um the two jobs really can't overlap and if you need it to run on weekends too add a separate entry for saturday instead of editing this one"},
   "The cleanup job runs on 30 2 * * 1-5, so weekdays at 2:30 a.m. Please don't change that without asking Ingrid, because the backups start at 3 and the two jobs really can't overlap. And if you need it to run on weekends too, add a separate entry for Saturday instead of editing this one.",
   {"numbers": ["2:30", "3"], "must_include": ["30 2 * * 1-5", "weekdays at 2:30 a.m.", "don't change that without asking Ingrid", "backups start at 3", "can't overlap", "separate entry for Saturday instead of editing this one"], "must_not_include": ["`", "**", "Sunday"], "min_negations": 2},
   "facts: cron expression kept exactly; speaker's own reading 'weekdays at 2:30 a.m.' kept; do NOT change WITHOUT asking Ingrid; backups start at 3, jobs can NOT overlap; IF weekends are needed, add a separate Saturday entry, do not edit this one (only Saturday was named)")

# 191
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "the installer logs are in C:\\Users\\Oskar\\AppData\\Local\\Temp and the crash dumps go to C:\\ProgramData\\MixDesk\\dumps"},
   "The installer logs are in C:\\Users\\Oskar\\AppData\\Local\\Temp, and the crash dumps go to C:\\ProgramData\\MixDesk\\dumps.",
   {"must_include": ["C:\\Users\\Oskar\\AppData\\Local\\Temp", "C:\\ProgramData\\MixDesk\\dumps"], "must_not_include": ["`", "C:/"]},
   "facts: two Windows paths kept byte for byte with backslashes and original casing")

# 192
R2(NM, {"task": "cleanup",
        "transcript": "new track is out now link in bio hashtag lofi hashtag beatmaker"},
   "New track is out now, link in bio. #lofi #beatmaker",
   {"must_include": ["New track is out now", "link in bio", "#lofi", "#beatmaker"], "must_not_include": ["hashtag", "# lofi", "`"]},
   "facts: spoken 'hashtag X' written as #lofi #beatmaker (single words, lowercase as spoken); no hashtags added")

# 193
R2(NM, {"task": "cleanup",
        "transcript": "um thanks at sign wren underscore audio for the mastering uh and at sign oskar dot beats for the artwork"},
   "Thanks @wren_audio for the mastering and @oskar.beats for the artwork.",
   {"must_include": ["@wren_audio", "@oskar.beats", "mastering", "artwork"], "must_not_include": ["at sign", "`"]},
   "facts: two @mentions rebuilt exactly from spoken 'at sign', 'underscore', 'dot'; credits kept (Wren: mastering; Oskar: artwork)")

# 194
R2(NM, {"task": "cleanup",
        "transcript": "the bug only shows up on iphone with ios eighteen point one and on macos when you use safari not chrome"},
   "The bug only shows up on iPhone with iOS 18.1 and on macOS when you use Safari, not Chrome.",
   {"numbers": ["18.1"], "must_include": ["iPhone", "iOS 18.1", "macOS", "Safari, not Chrome"], "must_not_include": ["`", "but not Safari"], "min_negations": 1},
   "facts: mixed-case product names written in their official casing (iPhone, iOS, macOS); iOS 18.1; Safari, NOT Chrome")

# 195
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "we moved the repo from gitlab to github last week and upgraded postgresql to sixteen"},
   "We moved the repo from GitLab to GitHub last week and upgraded PostgreSQL to 16.",
   {"numbers": ["16"], "must_include": ["GitLab", "GitHub", "last week", "PostgreSQL to 16"], "must_not_include": ["`", "Postgres 16"]},
   "facts: GitLab -> GitHub last week; PostgreSQL upgraded to 16; product casing exact")

# 196
R2(NM, {"task": "cleanup",
        "transcript": "rename the flag to camel case is retry enabled and keep the default as false"},
   "Rename the flag to isRetryEnabled and keep the default as false.",
   {"must_include": ["isRetryEnabled", "default as false"], "must_not_include": ["camel case", "is_retry_enabled", "`"]},
   "facts: the speaker dictated the casing ('camel case is retry enabled'), so the identifier is reassembled as isRetryEnabled; default stays false")

# 197
R2(NM, {"task": "cleanup",
        "transcript": "the user id field is empty for guest checkouts so the export skips those rows"},
   "The user ID field is empty for guest checkouts, so the export skips those rows.",
   {"must_include": ["user ID field", "guest checkouts", "skips those rows"], "must_not_include": ["userId", "user_id", "`"]},
   "facts: no casing or underscore was dictated, so 'user id' stays ordinary words (user ID) and is NOT turned into userId or user_id")

# 198
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "the column is called created underscore at and it's in utc not local time so convert it before you build the daily report"},
   "The column is called created_at, and it's in UTC, not local time, so convert it before you build the daily report.",
   {"must_include": ["created_at", "UTC, not local time", "convert it before you build the daily report"], "must_not_include": ["createdAt", "underscore", "`"], "min_negations": 1},
   "facts: column name created_at rebuilt from spoken underscore; UTC, NOT local time; convert before building the daily report")

# 199
R2(NM, {"task": "cleanup",
        "transcript": "run docker build dash dash no dash cache dash t api colon latest before you push"},
   "Run docker build --no-cache -t api:latest before you push.",
   {"must_include": ["docker build --no-cache -t api:latest", "before you push"], "must_not_include": ["`", " dash ", "colon"]},
   "facts: command rebuilt from spoken dashes and colon: docker build --no-cache -t api:latest; the 'no' is part of the flag --no-cache, not a correction")

# 200
R2(NM, {"task": "cleanup", "markup": "markdown", "instruction": "put the commands in code formatting",
        "transcript": "to reset the local db run make db dash reset and then make seed and uh don't run it against staging"},
   "To reset the local DB, run `make db-reset` and then `make seed`, and don't run it against staging.",
   {"must_include": ["`make db-reset`", "`make seed`", "don't run it against staging"], "must_not_include": ["**", "```"], "min_negations": 1},
   "facts: Markup markdown plus an explicit instruction to code-format commands, so inline backticks are allowed around the two commands only; do NOT run against staging", pos="after", cx=2)

# 201
R2(NM, {"task": "cleanup", "markup": "markdown", "header_style": "full", "instruction": "format the parameter names as code, nothing else",
        "transcript": "in airflow set catchup to false on the dag and max underscore active underscore runs to one"},
   "In Airflow, set `catchup` to false on the DAG and `max_active_runs` to 1.",
   {"numbers": ["1"], "must_include": ["`catchup`", "`max_active_runs`", "to false", "to 1"], "must_not_include": ["`false`", "`1`", "**"]},
   "facts: Markup markdown plus an instruction to code-format only the parameter names: catchup and max_active_runs in backticks, values left plain; catchup false; max_active_runs 1", pos="before", cx=2)

# 202
R2(NM, {"task": "cleanup", "markup": "markdown",
        "transcript": "the env var is NODE_ENV and it should be production on the server not development"},
   "The env var is NODE_ENV, and it should be production on the server, not development.",
   {"must_include": ["NODE_ENV", "production on the server, not development"], "must_not_include": ["`", "**"], "min_negations": 1},
   "facts: Markup markdown only permits formatting where something calls for it; nothing asked for code formatting, so no backticks; NODE_ENV kept exactly; production, NOT development")

# 203
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "only allow ssh from 203.0.113.0/24 and block everything else on port 22"},
   "Only allow SSH from 203.0.113.0/24 and block everything else on port 22.",
   {"numbers": ["22"], "must_include": ["203.0.113.0/24", "block everything else", "port 22"], "must_not_include": ["`", "0.0.0.0"]},
   "facts: CIDR range kept exactly; SSH only from that range; everything else blocked on port 22")

# 204
R2(NM, {"task": "cleanup",
        "transcript": "so the api is on localhost colon eight thousand and uh the frontend on localhost colon five one seven three"},
   "The API is on localhost:8000 and the frontend on localhost:5173.",
   {"must_include": ["localhost:8000", "localhost:5173"], "must_not_include": ["`", "8,000", "colon"]},
   "facts: host:port literals rebuilt from speech (localhost:8000, localhost:5173); no thousands separators in ports")

# 205
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "um the filter should be WHERE deleted_at IS NULL not IS NOT NULL otherwise uh we export the deleted accounts"},
   "The filter should be WHERE deleted_at IS NULL, not IS NOT NULL; otherwise, we export the deleted accounts.",
   {"must_include": ["WHERE deleted_at IS NULL", "not IS NOT NULL", "otherwise, we export the deleted accounts"], "must_not_include": ["`"], "min_negations": 2},
   "facts: SQL fragments kept exactly; correct filter is IS NULL, NOT IS NOT NULL; consequence 'otherwise we export the deleted accounts' kept")

# 206
R2(NM, {"task": "rewrite", "format": "email", "sender": "Kenta", "recipient": "Halima",
        "instruction": "keep the field names and the version exactly, no code formatting",
        "transcript": "uh tell halima that the mobile api now returns lastLoginAt instead of last_login and the old key goes away in v3.0.0 so the ios app has to switch before then um also the avatar url field is now avatarUrl instead of avatar_url but uh that change is already handled on android so it's only the ios app that needs both updates"},
   "Hi Halima,\n\nThe mobile API now returns lastLoginAt instead of last_login, and the old key goes away in v3.0.0, so the iOS app has to switch before then.\n\nAlso, the avatar URL field is now avatarUrl instead of avatar_url, but that change is already handled on Android, so it's only the iOS app that needs both updates.\n\nBest,\nKenta",
   {"format": "email", "must_include": ["Hi Halima,", "lastLoginAt", "instead of last_login", "v3.0.0", "iOS app has to switch before then", "avatarUrl", "instead of avatar_url", "already handled on Android", "only the iOS app that needs both updates", "Kenta"],
    "must_not_include": ["`", "Subject:", "last_login_at"]},
   "facts: lastLoginAt replaces last_login, old key removed in v3.0.0, iOS must switch before then; avatarUrl replaces avatar_url, already handled on Android, so only iOS needs both updates; all identifiers byte for byte; no date invented; sign-off from Sender Kenta only", cx=4)

# 207
R2(NM, {"task": "rewrite", "format": "post",
        "instruction": "make it a short post, keep my hashtags and the mention exactly",
        "transcript": "so we just shipped offline mode in the trail notes app huge thanks to at sign priyanka underscore qa for testing it on like forty devices hashtag mobiledev hashtag qa"},
   "We just shipped offline mode in the trail notes app. Huge thanks to @priyanka_qa for testing it on like 40 devices.\n\n#mobiledev #qa",
   {"format": "post", "numbers": ["40"], "must_include": ["offline mode", "trail notes app", "@priyanka_qa", "like 40 devices", "#mobiledev", "#qa"],
    "must_not_include": ["hashtag", "at sign", "🎉", "#mobile "]},
   "facts: shipped offline mode; @priyanka_qa thanked for testing on ABOUT ('like') 40 devices; only the two dictated hashtags, lowercase; no emoji; app name kept in the speaker's lowercase", cx=2)

# 208
R2(NM, {"task": "cleanup",
        "transcript": "the vst plugins are installed to C:\\Program Files\\Common Files\\VST3 but ableton is still scanning C:\\Program Files\\VSTPlugins"},
   "The VST plugins are installed to C:\\Program Files\\Common Files\\VST3, but Ableton is still scanning C:\\Program Files\\VSTPlugins.",
   {"numbers": ["3"], "must_include": ["C:\\Program Files\\Common Files\\VST3", "Ableton is still scanning", "C:\\Program Files\\VSTPlugins"], "must_not_include": ["`", "VST3\\"]},
   "facts: Windows paths with spaces kept exactly; plugins in VST3 folder but Ableton still scans VSTPlugins")

# 209
R2(NM, {"task": "cleanup", "locale": "en-gb",
        "transcript": "before you run terraform plan export AWS_REGION=eu-west-1 otherwise it picks up the default region"},
   "Before you run terraform plan, export AWS_REGION=eu-west-1; otherwise, it picks up the default region.",
   {"numbers": ["1"], "must_include": ["terraform plan", "export AWS_REGION=eu-west-1", "otherwise, it picks up the default region"], "must_not_include": ["`", "us-east-1"]},
   "facts: shell command export AWS_REGION=eu-west-1 kept byte for byte (lowercase 'export', mid-sentence so no capitalisation touches it); 'terraform plan' is a command so stays lowercase; consequence kept")

# 210
R2(NM, {"task": "cleanup",
        "transcript": "pin requests to >=2.31,<3 in requirements.txt and uh don't touch the other pins until the security scan finishes on friday"},
   "Pin requests to >=2.31,<3 in requirements.txt, and don't touch the other pins until the security scan finishes on Friday.",
   {"must_include": [">=2.31,<3", "requirements.txt", "don't touch the other pins until the security scan finishes on Friday"], "must_not_include": ["`", ">= 2.31"], "min_negations": 1},
   "facts: version specifier >=2.31,<3 kept byte for byte; do NOT touch other pins until the security scan finishes on Friday")

# 211
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "revert commit 4f9c2ab not the one before it"},
   "Revert commit 4f9c2ab, not the one before it.",
   {"must_include": ["4f9c2ab", "not the one before it"], "must_not_include": ["`", "4f9c2a "], "min_negations": 1},
   "facts: commit hash kept exactly in lowercase; revert 4f9c2ab, NOT the previous commit")

# 212
R2(NM, {"task": "cleanup",
        "transcript": "okay so the new ingestion pipeline is live um raw files land in s3 colon slash slash acme dash raw slash events slash and the dbt models are under models slash staging slash stg underscore events dot sql the job runs at quarter past every hour so the cron is 15 * * * * and it writes to analytics dot fct underscore events in snowflake uh if you see duplicate rows don't delete them manually just tag me at sign riya dot k in the data eng channel and i'll rerun the dedupe"},
   "The new ingestion pipeline is live. Raw files land in s3://acme-raw/events/, and the dbt models are under models/staging/stg_events.sql. The job runs at quarter past every hour, so the cron is 15 * * * *, and it writes to analytics.fct_events in Snowflake. If you see duplicate rows, don't delete them manually; just tag me @riya.k in the data eng channel, and I'll rerun the dedupe.",
   {"numbers": ["15"], "must_include": ["s3://acme-raw/events/", "models/staging/stg_events.sql", "quarter past every hour", "15 * * * *", "analytics.fct_events", "Snowflake", "don't delete them manually", "@riya.k", "data eng channel", "rerun the dedupe"],
    "must_not_include": ["`", "underscore", "at sign"], "min_negations": 1},
   "facts: pipeline live; S3 URI, dbt model path, cron 15 * * * *, table analytics.fct_events and handle @riya.k all rebuilt exactly; IF duplicates appear, do NOT delete manually, tag Riya, who commits to rerun the dedupe")

# 213
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "um only scan our own test box with nmap -sV -p 1-1000 192.0.2.20 and uh never against the client network"},
   "Only scan our own test box with nmap -sV -p 1-1000 192.0.2.20, and never against the client network.",
   {"must_include": ["nmap -sV -p 1-1000 192.0.2.20", "never against the client network"], "must_not_include": ["`", "-sS"], "min_negations": 1},
   "facts: nmap command kept byte for byte (flag case -sV matters); scan ONLY own test box, NEVER the client network")

# 214
R2(NM, {"task": "cleanup",
        "transcript": "we're moving password hashing from uh sha one to bcrypt with a cost of twelve and um maybe argon2id later"},
   "We're moving password hashing from SHA-1 to bcrypt with a cost of 12, and maybe Argon2id later.",
   {"numbers": ["12"], "must_include": ["SHA-1", "bcrypt", "cost of 12", "maybe Argon2id later"], "must_not_include": ["`", "SHA-256"]},
   "facts: SHA-1 -> bcrypt with cost 12; Argon2id later is hedged ('maybe'); algorithm names in standard casing (SHA-1, bcrypt, Argon2id). Waiver: the checker skips the spoken 'one' after 'sha' (pronoun rule) and then flags the 1 in SHA-1 as invented; it is the spoken 'sha one'",
   waivers=["number_invented"])

# 215
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "press command shift period in finder to show the hidden files"},
   "Press Command-Shift-Period in Finder to show the hidden files.",
   {"must_include": ["Command-Shift-Period", "Finder", "hidden files"], "must_not_include": ["`", "Command-Shift-."]},
   "facts: 'period' here is the name of a key in a keyboard shortcut, not punctuation, so it is written out (Command-Shift-Period)")

# 216
R2(NM, {"task": "cleanup",
        "transcript": "add qa plus android at example dot com to the testflight group no wait the firebase group"},
   "Add qa+android@example.com to the Firebase group.",
   {"must_include": ["qa+android@example.com", "the Firebase group"], "must_not_include": ["TestFlight", "`", " plus "]},
   "facts: email with plus addressing rebuilt as qa+android@example.com; self-correction applied: Firebase group (TestFlight group corrected away)")

# 217
R2(NM, {"task": "cleanup",
        "transcript": "send the scan results to ops at example dot org no wait the security alias security at example dot org before friday"},
   "Send the scan results to the security alias, security@example.org, before Friday.",
   {"must_include": ["the security alias", "security@example.org", "before Friday"], "must_not_include": ["ops@example.org", "`"]},
   "facts: self-correction applied: security@example.org replaces ops@example.org; the framing words 'the security alias' carry meaning and are kept (stage-1 TC-W04-032 fix); before Friday")

# 218
R2(NM, {"task": "cleanup",
        "transcript": "tag the release as v three point zero point zero dash beta dot two tomorrow morning"},
   "Tag the release as v3.0.0-beta.2 tomorrow morning.",
   {"must_include": ["v3.0.0-beta.2", "tomorrow morning"], "must_not_include": ["`", "v3.0.0 beta 2", " dot "]},
   "facts: spoken version rebuilt as v3.0.0-beta.2; tomorrow morning. Waiver: the checker reads the final 'two' (beta dot two) as a separate number it cannot find inside the dotted version string, which is exact",
   waivers=["number_missing"])

# 219
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "export from logic pro as a wav at forty eight k twenty four bit then upload it to soundcloud as private"},
   "Export from Logic Pro as a WAV at 48k, 24-bit, then upload it to SoundCloud as private.",
   {"numbers": ["48", "24"], "must_include": ["Logic Pro", "WAV", "48k", "24-bit", "SoundCloud", "as private"], "must_not_include": ["`", "MP3", "public"]},
   "facts: Logic Pro, WAV at 48k, 24-bit; upload to SoundCloud as private; product casing exact")

# 220
R2(NM, {"task": "cleanup",
        "transcript": "add type module to package dot json so node treats the files as es modules"},
   "Add type module to package.json so Node treats the files as ES modules.",
   {"must_include": ["type module", "package.json", "ES modules"], "must_not_include": ["`", "\"type\": \"module\"", "\"type\""]},
   "facts: only the file name is a dictated literal (package.json); 'type module' is described in words and is NOT expanded into a JSON snippet that the speaker never dictated")

# 221
R2(NM, {"task": "cleanup", "locale": "en-in", "instruction": "light cleanup, keep every version, URL and ID exactly as I said them",
        "transcript": "um for tomorrow's regression on the payments sdk please use build 3.4.0-rc.2 not rc.1 test on the iphone thirteen with ios 17.5 and the pixel seven with android fourteen and point the app at the staging api https colon slash slash staging dot pay dot example dot com slash v1 uh the test card is the usual one ending four two four two but don't use real cards under any circumstances and log everything in jira under QA-1187"},
   "For tomorrow's regression on the payments SDK, please use build 3.4.0-rc.2, not rc.1. Test on the iPhone 13 with iOS 17.5 and the Pixel 7 with Android 14, and point the app at the staging API https://staging.pay.example.com/v1. The test card is the usual one ending 4242, but don't use real cards under any circumstances, and log everything in Jira under QA-1187.",
   {"numbers": ["13", "17.5", "7", "14", "4242"], "must_include": ["tomorrow's regression", "payments SDK", "3.4.0-rc.2", "not rc.1", "iPhone 13", "iOS 17.5", "Pixel 7", "Android 14", "https://staging.pay.example.com/v1", "ending 4242", "don't use real cards under any circumstances", "QA-1187"],
    "must_not_include": ["`", "4,242", " dot "], "min_negations": 2},
   "facts: build 3.4.0-rc.2, NOT rc.1; devices iPhone 13 / iOS 17.5 and Pixel 7 / Android 14; staging URL rebuilt exactly; test card ending 4242 (an identifier, no separator); do NOT use real cards; log in Jira QA-1187", cx=2)

# 222
R2(NM, {"task": "cleanup",
        "transcript": "the weekly exports go to c colon backslash exports backslash weekly on the reporting machine"},
   "The weekly exports go to C:\\exports\\weekly on the reporting machine.",
   {"must_include": ["C:\\exports\\weekly", "reporting machine"], "must_not_include": ["`", "backslash", "C:/exports"]},
   "facts: spoken Windows path rebuilt with backslashes; only the drive letter is capitalised (C:), the folder names keep the speaker's lowercase because no casing was dictated")

# 223
R2(NM, {"task": "cleanup", "header_style": "full",
        "transcript": "add an index on orders open bracket customer underscore id close bracket before the backfill starts"},
   "Add an index on orders (customer_id) before the backfill starts.",
   {"must_include": ["orders (customer_id)", "before the backfill starts"], "must_not_include": ["`", "CREATE INDEX", "underscore"]},
   "facts: column customer_id rebuilt from spoken underscore and placed in the dictated brackets; no SQL statement invented; before the backfill starts")

# 224
R2(NM, {"task": "cleanup", "locale": "en-in", "header_style": "full",
        "transcript": "set the report job to 30 6 * * 1-5 so it runs at six thirty on weekdays and the timezone has to be Asia/Kolkata not UTC and if the job fails it should email data dash alerts at example dot com not my personal address um also the output goes to the reports slash daily folder on the shared drive uh not the old one"},
   "Set the report job to 30 6 * * 1-5 so it runs at 6:30 on weekdays, and the timezone has to be Asia/Kolkata, not UTC. If the job fails, it should email data-alerts@example.com, not my personal address. Also, the output goes to the reports/daily folder on the shared drive, not the old one.",
   {"numbers": ["6:30"], "must_include": ["30 6 * * 1-5", "6:30 on weekdays", "Asia/Kolkata, not UTC", "If the job fails", "data-alerts@example.com, not my personal address", "reports/daily", "not the old one"], "must_not_include": ["`", "IST", "a.m."], "min_negations": 3},
   "facts: cron 30 6 * * 1-5 kept exactly; 6:30 on weekdays (no a.m./p.m. spoken, none added); timezone Asia/Kolkata, NOT UTC; IF the job fails, email data-alerts@example.com, NOT the personal address; output to reports/daily on the shared drive, NOT the old folder")

# 225
R2(NM, {"task": "cleanup", "locale": "en-gb",
        "transcript": "golden hour at the pier this evening shot on the fuji x one hundred v hashtag streetphotography at sign ingrid dot shoots"},
   "Golden hour at the pier this evening, shot on the Fuji X100V. #streetphotography @ingrid.shoots",
   {"numbers": ["100"], "must_include": ["Golden hour at the pier this evening", "Fuji X100V", "#streetphotography", "@ingrid.shoots"], "must_not_include": ["hashtag", "at sign", "`", "Fujifilm"]},
   "facts: camera model rebuilt as X100V; one dictated hashtag and one dictated mention kept exactly; 'Fuji' kept as spoken (not expanded to Fujifilm)")
