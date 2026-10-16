# ---------------------------------------------------------------- stage 2, chunk 1 (101-140)
Q("prompt",
  "a watercolor painting of a red fox curled up asleep under a pine tree in the snow at dusk",
  "Create a watercolor painting of a red fox curled up asleep under a pine tree in the snow at dusk.",
  inc=("watercolor", "red fox", "pine tree", "snow", "dusk"), notinc=("4K", "photorealistic", "cinematic"),
  note="image prompt: every visual detail kept (watercolor, red fox curled up asleep, pine tree, snow, dusk); no style or quality tags added")

Q("prompt",
  "sql query for the top ten customers by total order value from the orders table for twenty twenty five",
  "Write a SQL query that returns the top 10 customers by total order value from the orders table for 2025.",
  nums=("10", "2025"), inc=("SQL", "orders table", "total order value"),
  note="facts: top 10; by total order value; orders table; year 2025")

Q("prompt",
  "why does my n8n webhook node return a four oh four in production but not in test mode",
  "Explain why my n8n Webhook node returns a 404 in production but not in test mode.",
  nums=("404",), inc=("n8n", "Webhook", "production", "test mode"), neg=1, waivers=["number_missing", "number_invented"],
  note="question turned into a prompt, not answered; error 404 spoken as 'four oh four' (checker reads 4 and 4, so number_missing/number_invented waived; 404 is the spoken value); negation 'but not in test mode' kept")

Q("prompt",
  "write me a cover letter for a junior data analyst role at a fintech startup using only these facts my name is tanuj i have two years of sql and power bi experience and i finished the google data analytics certificate in march dont make up any other experience",
  "Write a cover letter for a junior data analyst role at a fintech startup, using only these facts: my name is Tanuj, I have 2 years of SQL and Power BI experience, and I finished the Google Data Analytics Certificate in March. Do not make up any other experience.",
  nums=("2",), inc=("Tanuj", "junior data analyst", "fintech", "SQL", "Power BI", "Google Data Analytics", "March"), neg=1,
  context="work",
  note="job application: only the given facts (Tanuj; 2 years SQL and Power BI; certificate finished in March); negation: no invented experience")

Q("prompt",
  "write a prompt that asks for our refund policy paragraph to be translated into spanish and keep it formal",
  "Translate our refund policy paragraph into Spanish. Keep the translation formal.",
  inc=("refund policy", "Spanish", "formal"),
  note="the speaker wants a PROMPT asking another AI to translate; the target is only that prompt (no translation done); formal kept")

Q("prompt",
  "make me a six week study plan for the aws solutions architect associate exam i can study about an hour on weekdays and three hours on saturdays sundays are off",
  "Make a 6-week study plan for the AWS Solutions Architect Associate exam. I can study about an hour on weekdays and 3 hours on Saturdays. Sundays are off.",
  nums=("6", "3"), inc=("AWS Solutions Architect Associate", "about an hour", "Saturdays", "Sundays are off"),
  note="study plan: 6 weeks; 'about an hour' on weekdays (hedge kept); 3 hours Saturdays; Sundays off; plan not written")

Q("prompt",
  "pull out every date and amount from the bank sms messages i paste below and put them in a table with columns date amount and merchant dont guess the merchant if it isnt in the message just leave it empty",
  "Extract every date and amount from the bank SMS messages I paste below and put them in a table with the columns Date, Amount and Merchant. Do not guess the merchant: if it is not in the message, leave it empty.",
  inc=("bank SMS", "Date", "Amount", "Merchant", "leave it empty"), neg=2,
  note="personal finance extraction: 3 columns Date/Amount/Merchant; negation: do not guess merchant; condition: if not in message, leave empty")

Q("prompt",
  "um so i need a zapier zap that when a new row is added to my google sheet called leads it sends a slack message to the sales channel with the name and phone number",
  "Create a Zapier Zap that sends a Slack message to the sales channel with the name and phone number whenever a new row is added to my Google Sheet called Leads.",
  inc=("Zapier", "Slack", "Google Sheet", "Leads", "sales channel", "phone number"),
  note="automation: trigger = new row in Google Sheet 'Leads'; action = Slack message to sales channel with name and phone number only")

Q("prompt",
  "role play as an interviewer for a product manager internship ask me one question at a time and wait for my answer before the next one",
  "Role-play as an interviewer for a product manager internship. Ask me one question at a time and wait for my answer before asking the next one.",
  inc=("interviewer", "product manager internship", "one question at a time", "wait for my answer"),
  note="interview practice setup: one question at a time; wait for answer before next; no questions written by the prompt itself")

Q("prompt",
  "excel formula that adds up column e only for rows where column b says groceries and the date in column a is in the current month",
  "Write an Excel formula that adds up column E only for rows where column B says \"Groceries\" and the date in column A is in the current month.",
  inc=("Excel", "column E", "column B", "Groceries", "column A", "current month"),
  note="personal finance sheet: sum column E; both conditions kept (column B = Groceries AND column A date in current month)")

Q("prompt",
  "write a blog post outline about switching from spreadsheets to a budgeting app for students five sections max",
  "Write a blog post outline about switching from spreadsheets to a budgeting app, aimed at students. Use 5 sections at most.",
  nums=("5",), inc=("blog post outline", "budgeting app", "students"),
  note="writing task: outline only; audience students; 5 sections max")

Q("prompt",
  "explain how compound interest works like i'm fifteen with one example using ten thousand rupees at eight percent for five years",
  "Explain how compound interest works as if I'm 15, with one example using ₹10,000 at 8% for 5 years.",
  nums=("15", "10,000", "8", "5"), inc=("compound interest", "₹10,000"), notinc=("14,693", "14693"), locale="en-in",
  note="learning prompt, must not compute the example (no 14,693 result); age 15; ₹10,000 (rupees spoken), 8%, 5 years; 'one example' kept")

Q("prompt",
  "i want a home assistant automation that turns on the hallway light at thirty percent when motion is detected after eleven pm and turns it off after two minutes with no motion",
  "Write a Home Assistant automation that turns on the hallway light at 30% when motion is detected after 11 p.m., and turns it off after 2 minutes with no motion.",
  nums=("30", "11", "2"), inc=("Home Assistant", "hallway light", "motion", "after 11 p.m."), neg=1,
  note="home automation: light at 30%; only after 11 p.m. (condition); off after 2 minutes with no motion (negation kept)")

Q("prompt",
  "write a skyrim mod description for nexus mods it adds twelve new fishing spots around riften and doesnt need any other mods",
  "Write a Nexus Mods description for my Skyrim mod. It adds 12 new fishing spots around Riften and does not need any other mods.",
  nums=("12",), inc=("Skyrim", "Nexus Mods", "fishing spots", "Riften"), neg=1,
  note="game modding: 12 new fishing spots; around Riften; negation: requires no other mods")

Q("prompt",
  "how do i stop my laptop from going to sleep while a long python script is running on windows eleven",
  "Explain how to stop my laptop from going to sleep while a long Python script is running on Windows 11.",
  nums=("11",), inc=("sleep", "Python script", "Windows 11"), notinc=("powercfg", "Power & sleep"),
  note="question turned into a prompt; must not answer (no powercfg / settings path); Windows 11")

Q("prompt",
  "create an image of a cozy reading nook by a rainy window with a grey cat on a mustard yellow armchair and a cup of chai on the side table",
  "Create an image of a cozy reading nook by a rainy window, with a grey cat on a mustard-yellow armchair and a cup of chai on the side table.",
  inc=("reading nook", "rainy window", "grey cat", "mustard-yellow armchair", "chai", "side table"),
  notinc=("watercolor", "4K", "cinematic", "photorealistic"),
  note="image prompt: every detail kept (reading nook, rainy window, grey cat, mustard-yellow armchair, cup of chai, side table); no style invented")

Q("prompt",
  "write a product description for my notion template for tracking freelance invoices it has a monthly dashboard overdue reminders and a tax estimate page keep it under eighty words",
  "Write a product description for my Notion template for tracking freelance invoices. It has a monthly dashboard, overdue reminders and a tax estimate page. Keep it under 80 words.",
  nums=("80",), inc=("Notion template", "freelance invoices", "monthly dashboard", "overdue reminders", "tax estimate page"),
  note="writing task: 3 listed features only; under 80 words")

Q("prompt",
  "find out what changed between python three eleven and three twelve that could break my type hints",
  "Find out what changed between Python 3.11 and 3.12 that could break my type hints.",
  nums=("3.11", "3.12"), inc=("Python", "type hints"), waivers=["number_missing", "number_invented"],
  note="research prompt, not answered; versions 3.11 and 3.12 (spoken 'three eleven'/'three twelve'; checker reads them as times/separate numbers, so number_missing/number_invented waived)")

# ---------------------------------------------------------------- chunk 1, multi_constraint
Q("multi_constraint",
  "so i'm building a course on canva for small business owners and i need a prompt to write the module outline um eight modules each with a title a one line goal and two practice tasks and uh the audience has never used design software so no jargon and dont include anything about canva pro features because the course is only for the free plan",
  "Write a module outline for my Canva course for small business owners. Include 8 modules, each with a title, a one-line goal and 2 practice tasks. The audience has never used design software, so use no jargon. Do not include anything about Canva Pro features, because the course covers only the free plan.",
  nums=("8", "2"), inc=("Canva", "small business owners", "one-line goal", "Canva Pro", "free plan", "jargon"), neg=2,
  instr="turn my description into a detailed AI prompt, don't change the requirements and don't invent features",
  cx=2,
  note="e-learning: 8 modules; each = title, one-line goal, 2 practice tasks; audience never used design software (negation kept), no jargon; no Canva Pro features (free plan only)")

Q("multi_constraint",
  "i need a python script that reads expenses dot csv and groups spending by category for each month and saves a chart as monthly underscore spend dot png uh use pandas and matplotlib only and dont touch the original csv",
  "Write a Python script that reads expenses.csv, groups spending by category for each month, and saves a chart as monthly_spend.png. Use only pandas and matplotlib, and do not modify the original CSV.",
  inc=("expenses.csv", "monthly_spend.png", "pandas", "matplotlib", "category"), neg=1,
  instr="keep my exact file names", cx=1,
  note="personal finance tracking: expenses.csv in; monthly_spend.png out; group by category per month; only pandas and matplotlib; negation: original CSV untouched")

Q("multi_constraint",
  "okay so this is for the coding agent um in the repo there's src slash budget slash parser dot ts and it fails on bank statements where the amount has a minus sign at the end like one twenty point five oh minus i need it fixed so those parse as negative numbers um acceptance criteria are the existing tests in tests slash parser dot test dot ts still pass and you add at least three new test cases for the trailing minus and uh dont change the public function names because the dashboard imports them",
  "Fix src/budget/parser.ts so that bank statement amounts with a trailing minus sign (for example 120.50-) are parsed as negative numbers.\n\nAcceptance criteria: the existing tests in tests/parser.test.ts still pass, and you add at least 3 new test cases for the trailing minus.\n\nConstraint: do not change the public function names, because the dashboard imports them.",
  nums=("120.50", "3"), inc=("src/budget/parser.ts", "tests/parser.test.ts", "trailing minus", "negative", "public function names", "dashboard"),
  neg=1, context="code", instr="coding agent prompt, keep the file paths exactly and put the acceptance criteria on their own line",
  cx=2, waivers=["number_missing", "number_invented"],
  note="agent prompt: file paths kept verbatim; trailing-minus example 'one twenty point five oh minus' = 120.50- (checker cannot parse it, number_missing/number_invented waived); existing tests must pass; at least 3 new tests; negation: public function names unchanged (dashboard imports them)")

Q("multi_constraint",
  "write a prompt for an image of a pixel art game title screen for my farming mod it should say harvest moon valley no wait it should say willow creek farm in big letters with a sunrise behind a red barn and three chickens in front sixteen bit style",
  "Create a 16-bit pixel art title screen for my farming mod. It should say \"Willow Creek Farm\" in big letters, with a sunrise behind a red barn and 3 chickens in front.",
  nums=("16", "3"), inc=("pixel art", "Willow Creek Farm", "sunrise", "red barn", "chickens"), notinc=("Harvest Moon",),
  instr="image prompt, keep every detail I gave and don't add a style I didn't mention", cx=2,
  note="game modding image prompt: self-correction applied: title text 'Willow Creek Farm' (not Harvest Moon Valley); 16-bit pixel art (speaker's style); big letters; sunrise behind red barn; 3 chickens in front; nothing added")

Q("multi_constraint",
  "um help me write a cover letter for a remote customer success role at a saas company called helpdeskly i have three years of support experience at an ed tech startup i handled about forty tickets a day and i speak english hindi and gujarati keep it under two fifty words and dont say i'm a fast learner",
  "Write a cover letter for a remote customer success role at a SaaS company called Helpdeskly. Facts to use: I have 3 years of support experience at an edtech startup, I handled about 40 tickets a day, and I speak English, Hindi and Gujarati. Keep it under 250 words, and do not say I'm a fast learner.",
  nums=("3", "40", "250"), inc=("Helpdeskly", "remote customer success", "about 40", "English, Hindi and Gujarati", "fast learner"), neg=1,
  instr="make it a clear prompt, keep my facts exactly and don't add skills", cx=3, locale="en-in",
  note="job application: 3 years support at edtech startup; 'about 40 tickets a day' hedge kept; 3 languages; under 250 words; negation: never 'fast learner'; no skills added")

Q("multi_constraint",
  "write a sql query on the transactions table that shows total spend per category for last month sorted from highest to lowest and leave out transfers between my own accounts those have type equal to internal",
  "Write a SQL query on the transactions table that shows total spend per category for last month, sorted from highest to lowest. Leave out transfers between my own accounts, which have type = 'internal'.",
  inc=("SQL", "transactions table", "per category", "last month", "highest to lowest", "internal"),
  instr="make it a prompt and keep the exclusion rule exactly", cx=2,
  note="personal finance SQL: total spend per category; last month; highest to lowest; exclude type = 'internal' (own-account transfers)")

Q("multi_constraint",
  "so i want an n8n workflow that checks my gmail every fifteen minutes for emails from my bank with the word statement in the subject saves the pdf attachment to a google drive folder called statements twenty twenty six and then marks the email as read but only if the upload worked",
  "Build an n8n workflow that checks my Gmail every 15 minutes for emails from my bank with the word \"statement\" in the subject. Save the PDF attachment to a Google Drive folder called Statements 2026, then mark the email as read, but only if the upload succeeded.",
  nums=("15", "2026"), inc=("n8n", "Gmail", "statement", "PDF", "Google Drive", "Statements 2026", "only if the upload"),
  instr="detailed prompt, keep the folder name and the order of steps", cx=2, waivers=["invented_subject"],
  note="automation: every 15 minutes; from bank AND 'statement' in subject; save PDF to 'Statements 2026'; mark read only if upload succeeded (condition kept, order kept). 'subject' here is the email subject field, not an invented Subject line")

Q("multi_constraint",
  "um i want to set up a raspberry pi as a pi hole ad blocker first flash the os then set a static ip of one nine two dot one six eight dot one dot fifty then install pi hole and finally point my router dns to it i dont want to use docker",
  "Guide me step by step through setting up a Raspberry Pi as a Pi-hole ad blocker:\n1. Flash the OS.\n2. Set a static IP of 192.168.1.50.\n3. Install Pi-hole.\n4. Point my router's DNS to it.\nDo not use Docker.",
  inc=("Raspberry Pi", "Pi-hole", "192.168.1.50", "static IP", "router", "DNS", "Docker"), neg=1, afmt=None,
  instr="make it a step-by-step prompt", cx=1, pos="before", waivers=["number_missing", "number_invented"],
  note="home automation: 4 steps in the speaker's order (flash OS, static IP 192.168.1.50, install Pi-hole, router DNS); negation: no Docker. Numbered list because the instruction asks for step-by-step (format assertion omitted). IP spoken digit-by-digit: checker can't map it, number keys waived")

Q("multi_constraint",
  "i need a study plan for learning sql for data analysis in four weeks i already know excel well i can do forty five minutes a day and i want a small project at the end of each week using a free dataset",
  "Create a 4-week study plan for learning SQL for data analysis. I already know Excel well. I can study 45 minutes a day, and I want a small project at the end of each week using a free dataset.",
  nums=("4", "45"), inc=("SQL", "data analysis", "Excel", "free dataset", "end of each week"),
  instr="turn it into a prompt for a tutor AI, keep my time limits exactly", cx=2,
  note="study plan: 4 weeks; already knows Excel; 45 minutes a day; small project at end of each week; free dataset")

Q("multi_constraint",
  "um write a product description for our smart plug it works with alexa and google home tracks energy use in real time and has a schedule feature but it does not work with apple homekit so dont imply that and keep it under a hundred words",
  "Write a product description for our smart plug. It works with Alexa and Google Home, tracks energy use in real time, and has a schedule feature. It does not work with Apple HomeKit, so do not imply that it does. Keep it under 100 words.",
  nums=("100",), inc=("smart plug", "Alexa", "Google Home", "energy use", "Apple HomeKit"), neg=2,
  instr="make it a prompt, don't add features or compatibility I didn't mention", cx=2, tone="persuasive",
  note="home automation product: works with Alexa and Google Home; real-time energy tracking; schedule; negation: not HomeKit, must not imply it; under 100 words; tone header persuasive does not add facts")

Q("multi_constraint",
  "okay so i want a mock interview setup for a frontend developer role you be the interviewer from a mid size company ask five questions mix of react and javascript fundamentals one at a time and after i answer each one give me a score out of ten and one tip but dont give me the ideal answer unless i ask for it",
  "Act as an interviewer from a mid-size company for a frontend developer role. Ask me 5 questions, a mix of React and JavaScript fundamentals, one at a time. After I answer each one, give me a score out of 10 and one tip. Do not give me the ideal answer unless I ask for it.",
  nums=("5", "10"), inc=("frontend developer", "mid-size company", "React", "JavaScript", "one tip", "unless I ask"), neg=1,
  instr="make it a role-play prompt, keep the scoring rule and the condition", cx=2, waivers=["number_missing"],
  note="number_missing waived: checker reads 'ten and one tip' as a number run needing a digit 1; 'one tip' is kept in words. interview role-play: 5 questions; React + JavaScript fundamentals; one at a time; score out of 10 + one tip after each; ideal answer withheld unless asked (negation + condition kept)")

Q("multi_constraint",
  "so i'm making a minecraft data pack and i need help writing a function that gives every player a golden apple when they first join the world but only once per player um i'm on java edition one point twenty one no commands blocks just the data pack",
  "Help me write a function for my Minecraft data pack that gives every player a golden apple when they first join the world, only once per player. I'm on Java Edition 1.21. Use only the data pack, no command blocks.",
  nums=("1.21",), inc=("Minecraft", "data pack", "golden apple", "once per player", "Java Edition", "command blocks"), neg=1,
  instr="keep the version and the no command blocks rule", cx=2, waivers=["number_missing"],
  note="game modding: golden apple on first join; only once per player; Java Edition 1.21 (spoken 'one point twenty one'; checker reads a separate 1, so number_missing waived); negation: no command blocks, data pack only")

Q("multi_constraint",
  "write a prompt to translate my cover letter into german for a job in berlin um it should stay formal keep the company name techwerk and my name dhruv exactly as they are and dont translate the job title data engineer leave it in english",
  "Translate my cover letter into German for a job in Berlin. Keep it formal. Keep the company name TechWerk and my name, Dhruv, exactly as they are. Do not translate the job title \"Data Engineer\"; leave it in English.",
  inc=("German", "Berlin", "TechWerk", "Dhruv", "Data Engineer", "formal"), neg=1,
  instr="I want a prompt for another AI, keep the names and the job title rule", cx=2,
  note="translation PROMPT (model does not translate): formal; TechWerk and Dhruv unchanged; negation: job title 'Data Engineer' stays in English")

Q("multi_constraint",
  "um so the e learning platform needs quiz questions for the lesson on photosynthesis ten multiple choice questions four options each only one correct answer mark the correct one and um the level is grade seven so keep the language simple and dont use any trick questions",
  "Write 10 multiple-choice quiz questions for the lesson on photosynthesis on our e-learning platform. Give each question 4 options with only one correct answer, and mark the correct one. The level is grade 7, so keep the language simple. Do not use trick questions.",
  nums=("10", "4", "7"), inc=("photosynthesis", "multiple-choice", "grade 7", "only one correct answer", "trick questions"), neg=1,
  instr="detailed prompt please, keep all the numbers", cx=2,
  note="e-learning: 10 MCQs; 4 options each; only one correct, marked; grade 7; simple language; negation: no trick questions")

Q("multi_constraint",
  "write a prompt that turns my bullet notes into a linkedin about section for job hunting i'm a self taught ui designer with two years of freelance work for about fifteen clients mostly restaurants and salons keep it first person under one twenty words no buzzwords like passionate or synergy",
  "Turn my notes into a LinkedIn About section for job hunting. Facts: self-taught UI designer; 2 years of freelance work for about 15 clients, mostly restaurants and salons. First person, under 120 words, no buzzwords like \"passionate\" or \"synergy\".",
  nums=("2", "15", "120"), inc=("LinkedIn About", "self-taught UI designer", "about 15", "mostly restaurants and salons", "passionate", "synergy"), neg=1,
  instr="keep my facts and limits, make it concise", length="shorter", cx=3,
  note="job application: 2 years freelance; 'about 15 clients' and 'mostly' hedges kept; restaurants and salons; first person; under 120 words; banned buzzwords kept as literals. Concise (cf. TC-W05-044): ~35-word target vs 50-word transcript, every fact and limit kept")

Q("multi_constraint",
  "okay this is a long one so i want a prompt for a coding assistant to build a home dashboard page in my home assistant setup um the file is dashboards slash main dot yaml and it should have three sections lights climate and cameras the lights section has the living room kitchen and bedroom lights as toggle cards the climate section shows the bedroom ac with the target temperature and um the cameras section shows the front door camera only no the front door and the garage camera um and it has to work on my phone so a single column layout and please dont install any custom cards from hacs i only want built in cards",
  "Build a home dashboard in my Home Assistant setup, in the file dashboards/main.yaml. It should have 3 sections: Lights, Climate and Cameras. The Lights section shows the living room, kitchen and bedroom lights as toggle cards. The Climate section shows the bedroom AC with its target temperature. The Cameras section shows the front door camera and the garage camera. It has to work on my phone, so use a single-column layout. Do not install any custom cards from HACS; use only built-in cards.",
  nums=("3",), inc=("Home Assistant", "dashboards/main.yaml", "front door camera and the garage camera", "single-column", "HACS", "built-in cards"),
  notinc=("front door camera only",), neg=1, context="code",
  instr="turn my description into a detailed AI prompt, keep the file path, apply my correction about the cameras",
  cx=3, waivers=["negation_lost"],
  note="negation_lost waived: the source 'no' is the self-correction marker in 'front door camera only no the front door and the garage', not a requirement. home automation: file dashboards/main.yaml; 3 sections; lights = living room, kitchen, bedroom toggles; climate = bedroom AC target temp; correction applied: cameras = front door AND garage (not front door only); single column for phone; negation: no HACS custom cards, built-in only")

Q("multi_constraint",
  "i want a prompt for an ai to extract all the job requirements from a job description i'll paste and sort them into must have and nice to have um if the description doesnt say which one it is put it under unclear instead of guessing and keep the original wording of each requirement",
  "Extract all the job requirements from the job description I'll paste and sort them into Must Have and Nice to Have. If the description does not say which one a requirement is, put it under Unclear instead of guessing. Keep the original wording of each requirement.",
  inc=("job description", "Must Have", "Nice to Have", "Unclear", "instead of guessing", "original wording"), neg=1,
  instr="make it a clean extraction prompt, keep the unclear rule", cx=1,
  note="job applications extraction: 2 categories + Unclear; condition: if not stated -> Unclear, no guessing (negation kept); keep original wording")

Q("multi_constraint",
  "write an excel formula for my budget sheet that shows over budget in red text no sorry just the words over budget if actual spend in column d is more than the budget in column c otherwise show the remaining amount",
  "Write an Excel formula for my budget sheet that shows the words \"Over budget\" if actual spend in column D is more than the budget in column C, and otherwise shows the remaining amount.",
  inc=("Excel", "Over budget", "column D", "column C", "remaining amount"), notinc=("red",),
  instr="make it a prompt and apply my correction", cx=2, waivers=["negation_lost"],
  note="negation_lost waived: the only source 'no' is the correction marker 'no sorry'. personal finance: self-correction applied: just the words 'Over budget' (not red text); condition D > C; otherwise remaining amount")

Q("multi_constraint",
  "so for the elodie project we need a hero image for the landing page of her french lessons app a young woman studying at a wooden desk with a laptop and a small eiffel tower figurine soft morning light um no text in the image and keep the colors warm",
  "Create a hero image for the landing page of Elodie's French lessons app: a young woman studying at a wooden desk with a laptop and a small Eiffel Tower figurine, in soft morning light. Keep the colors warm, and do not include any text in the image.",
  inc=("Elodie", "French lessons app", "wooden desk", "laptop", "Eiffel Tower figurine", "soft morning light", "warm"), neg=1,
  notinc=("photorealistic", "4K", "cinematic"),
  instr="image prompt, keep every visual detail and don't add any style", cx=2,
  note="e-learning image prompt: young woman, wooden desk, laptop, small Eiffel Tower figurine, soft morning light, warm colors; negation: no text in image; no style added")

Q("multi_constraint",
  "write a prompt for a research assistant to compare three budgeting apps ynab goodbudget and money manager for an indian student um compare price in rupees if available offline support and whether they can import bank csv files and if any info isnt available say so instead of guessing",
  "Compare 3 budgeting apps, YNAB, Goodbudget and Money Manager, for an Indian student. Compare price in rupees (if available), offline support, and whether they can import bank CSV files. If any information is not available, say so instead of guessing.",
  nums=("3",), inc=("YNAB", "Goodbudget", "Money Manager", "Indian student", "rupees", "offline support", "CSV", "instead of guessing"), neg=1,
  instr="make it a research prompt, keep the three apps and the comparison points exactly", cx=2, locale="en-in",
  note="research prompt, not answered: exactly 3 apps; 3 comparison points (price in rupees if available, offline support, bank CSV import); condition: if unavailable, say so, no guessing")
