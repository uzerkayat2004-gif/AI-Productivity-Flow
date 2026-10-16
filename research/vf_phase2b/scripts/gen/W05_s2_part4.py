# ---------------------------------------------------------------- stage 2, chunk 4 (219-255)
Q("prompt",
  "photo of an old bicycle leaning against a blue door in a narrow street",
  "Create a photo of an old bicycle leaning against a blue door in a narrow street.",
  inc=("old bicycle", "blue door", "narrow street"), notinc=("golden hour", "bokeh", "4K"),
  note="image prompt: old bicycle, blue door, narrow street; photo (speaker's medium); nothing added")

Q("prompt",
  "sql to get the average session length per day from the sessions table",
  "Write a SQL query that gets the average session length per day from the sessions table.",
  inc=("SQL", "average session length", "per day", "sessions table"),
  note="facts: average session length; grouped per day; sessions table")

Q("prompt",
  "explain git rebase versus merge in two sentences",
  "Explain git rebase versus merge in 2 sentences.",
  nums=("2",), inc=("git rebase", "merge"),
  note="learning prompt; 2 sentences; not answered")

Q("prompt",
  "what should i put in my portfolio as a beginner ui designer",
  "Tell me what to put in my portfolio as a beginner UI designer.",
  inc=("portfolio", "beginner UI designer"), notinc=("case studies",),
  note="question turned into a prompt; must not answer")

Q("prompt",
  "tagline for a home security camera brand",
  "Write a tagline for a home security camera brand.",
  inc=("tagline", "home security camera"),
  note="writing task; prompt only")

Q("prompt",
  "turn my notes into a study timetable for my finals",
  "Turn my notes into a study timetable for my finals.",
  inc=("study timetable", "finals"),
  note="study plan prompt; nothing added")

Q("prompt",
  "zapier zap that texts me when the bank balance email arrives",
  "Create a Zapier Zap that texts me when the bank balance email arrives.",
  inc=("Zapier", "texts me", "bank balance email"),
  note="automation: trigger = bank balance email; action = text to me")

Q("prompt",
  "list mods that improve fallout four performance on low end pcs",
  "List mods that improve Fallout 4 performance on low-end PCs.",
  nums=("4",), inc=("Fallout 4", "performance", "low-end PCs"),
  note="game modding research prompt; Fallout 4; low-end PCs; no mods named")

# medium
Q("prompt",
  "excel formula that counts how many job applications in column d have the status interview scheduled",
  "Write an Excel formula that counts how many job applications in column D have the status \"Interview Scheduled\".",
  inc=("Excel", "column D", "Interview Scheduled"),
  note="job applications tracker: count in column D where status = 'Interview Scheduled'")

Q("prompt",
  "be my tutor for spanish verbs through short conversations and correct my mistakes gently but dont switch to english unless i ask you to",
  "Act as my tutor for Spanish verbs, teaching through short conversations. Correct my mistakes gently, and do not switch to English unless I ask you to.",
  inc=("tutor", "Spanish verbs", "short conversations", "gently", "unless I ask"), neg=1,
  note="e-learning role setup: short conversations; gentle corrections; negation + condition: no English unless asked")

Q("prompt",
  "an isometric illustration of a tiny smart home with solar panels on the roof a robot vacuum inside and a cat asleep on the sofa in pastel colours",
  "Create an isometric illustration of a tiny smart home with solar panels on the roof, a robot vacuum inside and a cat asleep on the sofa, in pastel colours.",
  inc=("isometric illustration", "tiny smart home", "solar panels", "robot vacuum", "cat asleep on the sofa", "pastel colours"),
  notinc=("4K", "3D render", "octane"), locale="en-gb",
  note="home automation image prompt: every detail kept (isometric, tiny smart home, solar panels on roof, robot vacuum inside, cat asleep on sofa, pastel colours); nothing added")

Q("prompt",
  "write a description for my modpack on curseforge it has forty two mods focused on exploration and you need at least eight gigs of ram",
  "Write a description for my modpack on CurseForge. It has 42 mods focused on exploration and needs at least 8 GB of RAM.",
  nums=("42", "8"), inc=("modpack", "CurseForge", "exploration", "at least 8 GB"),
  note="game modding: 42 mods; exploration focus; at least 8 GB RAM ('gigs' = GB)")

Q("prompt",
  "summarize this ten page pdf on index funds into a one page cheat sheet for beginners and dont recommend any specific fund",
  "Summarize this 10-page PDF on index funds into a one-page cheat sheet for beginners. Do not recommend any specific fund.",
  nums=("10",), inc=("index funds", "one-page cheat sheet", "beginners", "specific fund"), neg=1,
  note="personal finance learning: 10-page PDF -> one-page cheat sheet; beginners; negation: no specific fund recommended")

Q("prompt",
  "write a vba macro that copies every row with the status paid from the invoices sheet to the paid sheet and keeps the formatting",
  "Write a VBA macro that copies every row with the status \"Paid\" from the Invoices sheet to the Paid sheet, keeping the formatting.",
  inc=("VBA macro", "Paid", "Invoices sheet", "Paid sheet", "formatting"),
  note="facts: copy (not move) rows with status Paid; Invoices -> Paid sheet; keep formatting")

Q("prompt",
  "ask me the ten most common hr interview questions for freshers one by one so i can practise my answers",
  "Ask me the 10 most common HR interview questions for freshers, one by one, so I can practise my answers.",
  nums=("10",), inc=("HR interview questions", "freshers", "one by one", "practise"), locale="en-in",
  note="interview practice: 10 questions; freshers; one by one; questions not listed in the prompt")

Q("prompt",
  "python script using requests that checks the price on a product page every six hours and emails me if it drops below fifteen hundred rupees",
  "Write a Python script using requests that checks the price on a product page every 6 hours and emails me if it drops below ₹1,500.",
  nums=("6", "1,500"), inc=("Python", "requests", "every 6 hours", "₹1,500"), locale="en-in",
  note="facts: every 6 hours; condition: email only if price drops below ₹1,500 ('fifteen hundred rupees')")

Q("prompt",
  "cover letter opening paragraph for a teaching assistant role at an online coding bootcamp mention that i mentored twenty students in my college coding club",
  "Write the opening paragraph of a cover letter for a teaching assistant role at an online coding bootcamp. Mention that I mentored 20 students in my college coding club.",
  nums=("20",), inc=("opening paragraph", "teaching assistant", "online coding bootcamp", "mentored 20 students", "college coding club"),
  note="job application + e-learning: opening paragraph only; 20 students mentored in college coding club")

Q("prompt",
  "how do i make my smart bulbs turn on gradually at six thirty every morning like a sunrise alarm",
  "Explain how to make my smart bulbs turn on gradually at 6:30 every morning, like a sunrise alarm.",
  nums=("6:30",), inc=("smart bulbs", "gradually", "every morning", "sunrise alarm"),
  note="home automation question turned into a prompt; 6:30 every morning; not answered")

Q("prompt",
  "draft an email to my professor asking for a recommendation letter for my masters application the deadline is november thirtieth",
  "Draft an email to my professor requesting a recommendation letter for my master's application. The deadline is November 30.",
  nums=("30",), inc=("professor", "recommendation letter", "master's application", "November 30"), register="formal",
  note="header-only (register formal): prompt for a formal email; deadline November 30; no professor name invented")

Q("multi_constraint",
  "write a python script that renames the photos in the folder trip underscore goa to goa underscore one goa underscore two and so on in the order they were taken and saves a log to rename underscore log dot txt",
  "Write a Python script that renames the photos in the folder trip_goa to goa_1, goa_2 and so on, in the order they were taken, and saves a log to rename_log.txt.",
  nums=("1", "2"), inc=("trip_goa", "goa_1", "goa_2", "rename_log.txt", "order they were taken"),
  instr="keep my exact file names", cx=1, waivers=["number_invented"],
  note="number_invented waived: checker skips the bare 'one' in 'goa underscore one' and then flags the 1 in goa_1. file and folder names kept verbatim (trip_goa, goa_1, goa_2..., rename_log.txt); order by date taken; log file")

Q("multi_constraint",
  "i need a google sheets formula for my fitness challenge sheet the e learning team is running um it should give a badge that says gold if someone logged at least twenty sessions silver for ten to nineteen and nothing for fewer than ten and the sessions are in column e",
  "Write a Google Sheets formula for the e-learning team's fitness challenge sheet.\nConditions:\n- \"Gold\" if someone logged at least 20 sessions.\n- \"Silver\" for 10 to 19 sessions.\n- Nothing for fewer than 10 sessions.\n- The sessions are in column E.",
  nums=("20", "10", "19"), inc=("Google Sheets", "Gold", "Silver", "at least 20", "10 to 19", "fewer than 10", "column E"), neg=1, afmt=None,
  instr="add the constraints as a list", cx=1,
  note="tiers: Gold >= 20; Silver 10-19; nothing below 10 (negation 'nothing' kept); column E. List requested (format assertion omitted)")

Q("multi_constraint",
  "so tanuj wants to know if an electric scooter is actually cheaper than his petrol scooter over five years um he rides about thirty kilometres a day and electricity is about eight rupees a unit at his place compare running cost and maintenance only not the purchase price",
  "Compare whether an electric scooter is cheaper than Tanuj's petrol scooter over 5 years. He rides about 30 km a day; electricity is about ₹8 a unit where he lives. Compare running cost and maintenance only, not the purchase price.",
  nums=("5", "30", "8"), inc=("Tanuj", "electric scooter", "petrol scooter", "about 30 km", "about ₹8", "running cost", "purchase price"), neg=1,
  length="shorter", locale="en-in", instr="make it a tighter research prompt, keep all the numbers", cx=3,
  note="tighter (~40 vs ~50 words). research prompt, not answered: 5 years; 'about 30 km/day' and 'about ₹8 a unit' hedges; only running cost + maintenance; negation: not purchase price")

Q("multi_constraint",
  "make a lesson plan prompt for a sixty minute workshop on budgeting for first jobbers um ten minutes intro thirty minutes building a budget in google sheets together fifteen minutes q and a and five minutes wrap up no slides just live demo",
  "## Goal\nCreate a lesson plan for a 60-minute workshop on budgeting for first jobbers.\n\n## Structure\n10 minutes intro, 30 minutes building a budget together in Google Sheets, 15 minutes Q&A, 5 minutes wrap-up.\n\n## Constraints\nNo slides; live demo only.",
  nums=("60", "10", "30", "15", "5"), inc=("lesson plan", "60-minute workshop", "first jobbers", "Google Sheets", "Q&A", "No slides", "live demo"), neg=1,
  markup="markdown", instr="use headings for goal, structure and constraints", cx=2,
  note="markdown headings requested. e-learning/personal finance: 60 min total = 10 + 30 + 15 + 5 (speaker's order kept); negation: no slides, live demo only")

Q("multi_constraint",
  "write a prompt to translate our home automation app's settings screen labels into japanese use this glossary scene stays scene not a translation and keep the word hub in english and keep every label under twelve characters if possible",
  "Translate our home automation app's settings screen labels into Japanese. Use this glossary: \"Scene\" stays \"Scene\" (do not translate it), and keep the word \"Hub\" in English. Keep every label under 12 characters if possible.",
  nums=("12",), inc=("Japanese", "glossary", "Scene", "Hub", "under 12 characters", "if possible"), neg=1,
  instr="it's a prompt for a translator AI, keep the glossary rules exactly", cx=2,
  note="translation PROMPT (target English): glossary 'Scene' untranslated, 'Hub' stays English; under 12 characters is hedged 'if possible'")

Q("multi_constraint",
  "help me tweak fallout four's ini for better fps um i'm on a gtx ten fifty no a gtx sixteen fifty with eight gigs of ram and i want to lower shadow distance and god rays but i dont want to lose the view distance",
  "Help me tweak Fallout 4's INI for better FPS. I'm on a GTX 1650 with 8 GB of RAM. Lower the shadow distance and god rays, but do not reduce the view distance.",
  nums=("4", "1650", "8"), inc=("Fallout 4", "INI", "GTX 1650", "8 GB", "shadow distance", "god rays", "view distance"), notinc=("1050",), neg=1,
  instr="apply my correction on the GPU and keep the view distance rule", cx=2, waivers=["number_missing", "number_invented", "negation_lost"],
  note="game modding: correction applied: GTX 1650 (not 1050); 8 GB RAM; lower shadows + god rays; negation: keep view distance. Waivers: 'ten fifty'/'sixteen fifty' parsed as times by checker; correction marker 'no' counted as negation")

Q("multi_constraint",
  "sql query on the expenses table that shows total spend per category either monthly or weekly depending on a parameter called period and only for the current year",
  "Write a SQL query on the expenses table that shows total spend per category, either monthly or weekly depending on a parameter called period, only for the current year.",
  inc=("SQL", "expenses table", "per category", "monthly or weekly", "period", "current year"),
  instr="make it a prompt, keep both options and the parameter name", cx=2,
  note="genuine alternative kept: monthly OR weekly, chosen by parameter 'period'; current year only")

# long
Q("multi_constraint",
  "okay so for the coding agent we have a quiz module in our e learning platform um the scoring logic lives in src slash quiz slash score dot py and right now partial credit isn't supported for multi select questions i want partial credit where each correct option selected gives equal share of the marks and any wrong option selected makes the score for that question zero um dont change the single choice scoring and the function signature of calculate score has to stay the same um acceptance criteria are new tests in tests slash test underscore score dot py covering all correct some correct one wrong and none selected and all existing tests pass",
  "Add partial credit for multi-select questions to the quiz module of our e-learning platform; right now it is not supported. The scoring logic is in src/quiz/score.py.\nRules:\n- Each correct option selected gives an equal share of the marks.\n- Any wrong option selected makes the score for that question 0.\n- Do not change the single-choice scoring.\n- The function signature of calculate_score must stay the same.\nAcceptance criteria:\n- New tests in tests/test_score.py cover: all correct, some correct, one wrong, and none selected.\n- All existing tests pass.",
  nums=("0",), inc=("src/quiz/score.py", "tests/test_score.py", "calculate_score", "equal share", "single-choice", "none selected"), neg=2,
  afmt=None, context="code",
  instr="agent prompt, rules and acceptance criteria as lists, keep the paths and function name", cx=3,
  note="agent prompt: partial credit currently not supported (context kept as a clause); equal share per correct option; any wrong option -> 0; negation: single-choice scoring unchanged; calculate_score signature unchanged; tests in tests/test_score.py with the 4 named cases; existing tests pass. Lists requested (format assertion omitted)")

Q("prompt",
  "um so i've been tracking my spending in a notes app for like three months and it's a mess and i'm wondering if i should move to a spreadsheet or an app um i mostly pay with upi but i also use cash maybe twice a week and i don't want to link my bank account to anything uh what would be the simplest setup that i'll actually stick with",
  "Help me choose the simplest spending-tracking setup I'll actually stick with: a spreadsheet or an app. I've tracked my spending in a notes app for about 3 months and it's a mess. I mostly pay with UPI, but I also use cash, maybe twice a week. I do not want to link my bank account to anything.",
  nums=("3",), inc=("spreadsheet or an app", "notes app", "about 3 months", "UPI", "maybe twice a week", "bank account"), neg=1,
  locale="en-in",
  note="personal finance question turned into a prompt, not answered: 'like three months' = about 3; mostly UPI; cash 'maybe twice a week' (hedge); negation: won't link bank account; options spreadsheet OR app both kept")

Q("multi_constraint",
  "image prompt for a character portrait for my skyrim follower mod um she's a nord ranger with braided red hair a scar across her left eyebrow wearing a dark green hooded cloak no wait a grey hooded cloak and holding a longbow um she's standing in a snowy pine forest at dawn and it should look like a painted portrait from the waist up",
  "Create a painted portrait, from the waist up, of the character for my Skyrim follower mod: a Nord ranger with braided red hair and a scar across her left eyebrow, wearing a grey hooded cloak and holding a longbow. She is standing in a snowy pine forest at dawn.",
  inc=("Skyrim", "Nord ranger", "braided red hair", "left eyebrow", "grey hooded cloak", "longbow", "snowy pine forest", "dawn", "waist up"),
  notinc=("dark green",), locale="en-gb", instr="keep every visual detail and apply my correction, don't add a style", cx=2,
  note="game modding image prompt: correction applied: grey hooded cloak (not dark green); braided red hair; scar across LEFT eyebrow; longbow; snowy pine forest; dawn; painted portrait waist-up (speaker's style); nothing added")

Q("multi_constraint",
  "so dhruv needs a cover letter prompt um he's applying for an associate product manager role at a health tech startup called caresync he has an engineering degree two years as a qa engineer at a payments company where he wrote the test plan for the upi autopay launch and he led a team of three interns last summer um he wants it under three hundred words confident but not arrogant and he does not want to mention his gpa",
  "Write a cover letter for Dhruv for an associate product manager role at CareSync, a health tech startup. Facts: engineering degree; 2 years as a QA engineer at a payments company, where he wrote the test plan for the UPI Autopay launch; led a team of 3 interns last summer. Under 300 words, confident but not arrogant. Do not mention his GPA.",
  nums=("2", "3", "300"), inc=("Dhruv", "associate product manager", "CareSync", "QA engineer", "UPI Autopay", "3 interns", "last summer", "GPA"), neg=2,
  length="shorter", locale="en-in", instr="concise prompt, keep every fact and the GPA rule", cx=3,
  note="concise: ~60-word target vs ~85-word transcript. job application: CareSync APM; engineering degree; 2 years QA at payments company; UPI Autopay test plan; led 3 interns last summer; under 300 words; confident not arrogant (negation); never mention GPA")

Q("multi_constraint",
  "i want an n8n workflow for my home energy um every sunday at nine pm get the week's electricity usage from the home assistant api for the sensor called sensor dot energy underscore total then calculate the cost at seven point five rupees per unit and post a message in my telegram with the total units the cost and the comparison with the previous week and if usage went up by more than twenty percent add a warning line at the top",
  "Build an n8n workflow for my home energy. Every Sunday at 9 p.m., get the week's electricity usage from the Home Assistant API for the sensor sensor.energy_total. Calculate the cost at ₹7.50 per unit, and post a Telegram message with the total units, the cost, and the comparison with the previous week. If usage went up by more than 20%, add a warning line at the top.",
  nums=("9", "7.50", "20"), inc=("n8n", "Home Assistant API", "sensor.energy_total", "₹7.50", "Telegram", "previous week", "more than 20%", "warning line at the top"),
  locale="en-in", instr="keep the sensor id exactly and every number", cx=2, waivers=["number_missing", "number_invented"],
  note="home automation: Sunday 9 p.m.; sensor id sensor.energy_total verbatim; ₹7.50 per unit ('seven point five rupees'; checker reads 7 and 5 separately, number keys waived); message: units, cost, week-over-week; condition: >20% increase -> warning line at top")

Q("prompt",
  "so i'm thirty two and i want to finally learn piano um i have a sixty one key keyboard at home i can practise twenty minutes most evenings and i can read a little bit of music from school but i've forgotten most of it uh i want a three month plan that gets me playing simple songs with both hands and i'd like each week to have one technique goal and one song goal and no expensive apps or paid lessons",
  "Create a 3-month piano learning plan for me. I'm 32, I have a 61-key keyboard at home, and I can practise 20 minutes most evenings. I can read a little music from school but have forgotten most of it. The goal is to play simple songs with both hands. Give each week one technique goal and one song goal. Do not include expensive apps or paid lessons.",
  nums=("32", "61", "20", "3"), inc=("piano", "61-key keyboard", "20 minutes most evenings", "a little music", "both hands", "technique goal", "song goal", "paid lessons"), neg=1,
  locale="en-gb",
  note="study plan: age 32; 61-key keyboard; 20 minutes 'most evenings' (hedge); reads a little music, forgot most; 3 months; both hands; one technique + one song goal per week; negation: no expensive apps or paid lessons")

Q("multi_constraint",
  "okay so ngozi wants to practise a system design interview um be a senior engineer interviewer at a large tech company and give her the problem design a url shortener um let her lead and only ask clarifying questions when she pauses for a while dont give hints in the first ten minutes and at the end score her on requirements gathering high level design scaling and trade offs each out of five",
  "Act as a senior engineer interviewer at a large tech company running a system design interview for Ngozi.\nSetup:\n- Give her the problem: design a URL shortener.\n- Let her lead; only ask clarifying questions when she pauses for a while.\n- Do not give hints in the first 10 minutes.\n- At the end, score her out of 5 on each of: requirements gathering, high-level design, scaling, and trade-offs.",
  nums=("10", "5"), inc=("Ngozi", "senior engineer", "URL shortener", "clarifying questions", "first 10 minutes", "requirements gathering", "scaling", "trade-offs"), neg=1,
  afmt=None, instr="role-play prompt with the rules as a list", cx=2, waivers=["number_invented"],
  note="number_invented waived: checker merges 'first ten' into one value and then flags 10. interview role-play: URL shortener; she leads; clarifying questions only when she pauses; negation: no hints in first 10 minutes; 4 criteria each out of 5. List requested (format assertion omitted)")

Q("multi_constraint",
  "i'm going to paste a bunch of job alert emails from linkedin and naukri and i want the ai to pull out the job title company location salary if mentioned and the apply link into a csv with exactly those column names um if salary isn't mentioned write not listed and skip any job that's not remote or in pune and dont include duplicates if the same job shows up in both",
  "Extract the job title, company, location, salary (if mentioned) and apply link from the LinkedIn and Naukri job alert emails I paste below, into a CSV with exactly those column names. If the salary is not mentioned, write \"Not listed\". Skip any job that is not remote or in Pune. Do not include duplicates if the same job appears in both.",
  inc=("LinkedIn", "Naukri", "job title", "apply link", "CSV", "exactly those column names", "Not listed", "remote or in Pune"), neg=4,
  instr="extraction prompt, keep my column names and every rule", cx=2, locale="en-in",
  note="job applications extraction: 5 columns with exact names; condition: no salary -> 'Not listed'; keep only remote or Pune jobs; no duplicates across sources")

Q("prompt",
  "write a blog post about how i track my money with a simple google sheet um the facts are i started in january twenty twenty six i have four tabs income expenses savings and a dashboard i log every expense the same day and review on sunday evenings um it's a personal story not financial advice so dont tell readers what to invest in and keep it around eight hundred words",
  "Write a blog post about how I track my money with a simple Google Sheet. It's a personal story, not financial advice. Facts: I started in January 2026; the sheet has 4 tabs (Income, Expenses, Savings and a Dashboard); I log every expense the same day and review on Sunday evenings. Do not tell readers what to invest in. Keep it around 800 words.",
  nums=("2026", "4", "800"), inc=("Google Sheet", "January 2026", "Income", "Expenses", "Savings", "Dashboard", "same day", "Sunday evenings", "around 800 words"), neg=2,
  waivers=["number_missing", "number_invented"],
  note="writing task (personal finance): January 2026 (checker reads 'twenty twenty six' as 20/26, number keys waived); 4 tabs named; same-day logging; Sunday evening review; negations: not financial advice, don't tell readers what to invest in; 'around 800 words' hedge")

Q("multi_constraint",
  "um so the e learning team uses a google form for course feedback and i want a zapier zap that takes each new response and adds it to the sheet course feedback twenty twenty six and if the rating is two or lower it posts the comment in the slack channel hash course dash alerts with the course name and um it shouldn't post the student's email in slack because of privacy",
  "Create a Zapier Zap that takes each new Google Form course feedback response and adds it to the sheet Course Feedback 2026. If the rating is 2 or lower, post the comment in the Slack channel #course-alerts with the course name. Do not post the student's email in Slack, for privacy.",
  nums=("2026", "2"), inc=("Zapier", "Google Form", "Course Feedback 2026", "2 or lower", "#course-alerts", "course name", "student's email"), neg=1,
  length="shorter", instr="tighter prompt please, keep the channel and sheet names", cx=3,
  waivers=["number_missing", "number_invented"],
  note="tighter: ~50-word target vs ~70-word transcript. e-learning automation: sheet 'Course Feedback 2026' (checker reads 'twenty twenty six' as 20/26; number keys waived); condition: rating 2 or lower -> Slack #course-alerts with comment + course name; negation: never the student's email")
