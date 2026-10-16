# ---------------------------------------------------------------- stage 2, chunk 2 (139-180)
# short prompts
Q("prompt",
  "generate an image of a lighthouse on a cliff during a thunderstorm",
  "Generate an image of a lighthouse on a cliff during a thunderstorm.",
  inc=("lighthouse", "cliff", "thunderstorm"), notinc=("cinematic", "4K", "dramatic lighting"),
  note="image prompt: lighthouse, cliff, thunderstorm only; no style added")

Q("prompt",
  "whats the difference between a fixed deposit and a recurring deposit",
  "Explain the difference between a fixed deposit and a recurring deposit.",
  inc=("fixed deposit", "recurring deposit"), notinc=("lump sum", "monthly instalment"), locale="en-in",
  note="question turned into a prompt; must not answer it")

Q("prompt",
  "sql query that finds duplicate emails in the users table",
  "Write a SQL query that finds duplicate emails in the users table.",
  inc=("SQL", "duplicate emails", "users table"), notinc=("GROUP BY", "HAVING"),
  note="prompt only; must not write the query (no GROUP BY/HAVING)")

Q("prompt",
  "summarize this lecture transcript into ten key points for revision",
  "Summarize this lecture transcript into 10 key points for revision.",
  nums=("10",), inc=("lecture transcript", "key points", "revision"),
  note="e-learning: 10 key points; for revision")

Q("prompt",
  "um translate this error message into simple english for my mom",
  "Translate this error message into simple English for my mom.",
  inc=("error message", "simple English", "my mom"),
  note="prompt only; audience 'my mom' kept; no explanation of the error")

Q("prompt",
  "regex that matches indian pin codes six digits not starting with zero",
  "Write a regex that matches Indian PIN codes: 6 digits, not starting with 0.",
  nums=("6", "0"), inc=("regex", "Indian PIN codes"), neg=1, notinc=("[1-9]",),
  note="facts: 6 digits; negation: not starting with 0; must not write the regex")

Q("prompt",
  "give me ten interview questions for a junior qa tester role",
  "Write 10 interview questions for a junior QA tester role.",
  nums=("10",), inc=("interview questions", "junior QA tester"),
  note="job applications: 10 questions; junior QA tester")

Q("prompt",
  "google sheets formula to convert usd in column b to inr using the rate in cell f one",
  "Write a Google Sheets formula that converts USD in column B to INR using the rate in cell F1.",
  inc=("Google Sheets", "USD", "column B", "INR", "F1"), waivers=["number_invented"],
  note="number_invented waived: cell reference 'f one' -> F1; checker skips a bare spoken 'one' after 'cell f', then flags the 1 in F1. facts: USD in column B; INR; rate in cell F1")

Q("prompt",
  "explain recursion using a stack of plates analogy",
  "Explain recursion using a stack-of-plates analogy.",
  inc=("recursion", "stack-of-plates analogy"),
  note="learning prompt; analogy specified by speaker kept; not answered")

Q("prompt",
  "list the steps to mod stardew valley with smapi on a mac",
  "List the steps to mod Stardew Valley with SMAPI on a Mac.",
  inc=("Stardew Valley", "SMAPI", "Mac"),
  note="game modding: SMAPI; Mac; steps not written")

Q("prompt",
  "write a tweet announcing our free python course for beginners no emojis",
  "Write a tweet announcing our free Python course for beginners. Do not use emojis.",
  inc=("tweet", "free Python course", "beginners"), neg=1,
  note="e-learning: course is free; beginners; negation: no emojis")

Q("prompt",
  "zapier zap that saves gmail attachments to dropbox",
  "Create a Zapier Zap that saves Gmail attachments to Dropbox.",
  inc=("Zapier", "Gmail", "attachments", "Dropbox"),
  note="automation: Gmail attachments -> Dropbox; nothing added")

Q("prompt",
  "a minimalist logo of a paper plane inside a circle navy blue on white",
  "Design a minimalist logo of a paper plane inside a circle, navy blue on white.",
  inc=("minimalist", "paper plane", "circle", "navy blue on white"), notinc=("gradient", "3D"),
  note="image prompt: minimalist (speaker's style), paper plane in a circle, navy blue on white; nothing added")

Q("prompt",
  "make flashcards from my biology notes question on the front answer on the back",
  "Make flashcards from my biology notes, with the question on the front and the answer on the back.",
  inc=("flashcards", "biology notes", "front", "back"),
  note="e-learning: question front, answer back")

Q("prompt",
  "how many hours of sleep do teenagers actually need",
  "Explain how many hours of sleep teenagers actually need.",
  inc=("sleep", "teenagers"), notinc=("8 to 10", "8-10", "9 hours"),
  note="question turned into a prompt; must not answer (no hour range)")

Q("prompt",
  "bash script that backs up my home folder to an external drive every night at two am",
  "Write a Bash script that backs up my home folder to an external drive every night at 2 a.m.",
  nums=("2",), inc=("Bash", "home folder", "external drive", "every night"),
  note="facts: nightly at 2 a.m.; home folder to external drive")

Q("prompt",
  "draft a resignation letter giving two weeks notice keep it polite",
  "Draft a polite resignation letter giving 2 weeks' notice.",
  nums=("2",), inc=("resignation letter", "notice", "polite"),
  note="facts: 2 weeks' notice; polite")

Q("prompt",
  "suggest five names for my budgeting app for college students",
  "Suggest 5 names for my budgeting app for college students.",
  nums=("5",), inc=("budgeting app", "college students"),
  note="facts: 5 names; app audience college students")

Q("prompt",
  "alexa routine that turns off all the lights at midnight",
  "Create an Alexa routine that turns off all the lights at midnight.",
  inc=("Alexa routine", "all the lights", "midnight"),
  note="home automation: all lights off; midnight")

Q("prompt",
  "convert this recipe for four people into one for ten",
  "Convert this recipe for 4 people into one for 10.",
  nums=("4", "10"), inc=("recipe",),
  note="facts: from 4 people to 10; not converted by the prompt")

Q("prompt",
  "explain what a pivot table is with a tiny example",
  "Explain what a pivot table is, with a tiny example.",
  inc=("pivot table", "tiny example"),
  note="learning prompt; not answered; 'tiny example' kept")

Q("prompt",
  "write a prompt to translate my portfolio headline into french",
  "Translate my portfolio headline into French.",
  inc=("portfolio headline", "French"),
  note="translation PROMPT only; nothing translated")

# medium
Q("prompt",
  "write a script for a two minute explainer video about phishing for new employees friendly tone no scare tactics and end with three tips",
  "Write a script for a 2-minute explainer video about phishing for new employees. Use a friendly tone, no scare tactics, and end with 3 tips.",
  nums=("2", "3"), inc=("explainer video", "phishing", "new employees", "friendly", "scare tactics"), neg=1,
  note="e-learning: 2-minute video; friendly; negation: no scare tactics; ends with 3 tips")

Q("prompt",
  "explain what each line in this skyrim ini tweak does i dont want any changes just the explanations",
  "Explain what each line in this Skyrim INI tweak does. Do not make any changes; just give the explanations.",
  inc=("Skyrim", "INI", "each line"), neg=1,
  note="game modding: explain each line; negation: no changes")

Q("prompt",
  "a formula in google sheets that returns the last non empty value in column c of the savings tab",
  "Write a Google Sheets formula that returns the last non-empty value in column C of the Savings tab.",
  inc=("Google Sheets", "last non-empty value", "column C", "Savings tab"),
  note="personal finance sheet: last non-empty value; column C; Savings tab")

Q("prompt",
  "sql to find users who signed up in the last thirty days but havent completed a single lesson the tables are users and lesson underscore progress",
  "Write a SQL query that finds users who signed up in the last 30 days but have not completed a single lesson. The tables are users and lesson_progress.",
  nums=("30",), inc=("SQL", "users", "lesson_progress", "last 30 days"), neg=1,
  note="e-learning SQL: signed up in last 30 days; negation: no lesson completed; table names users and lesson_progress")

Q("prompt",
  "rewrite my resume bullet points so each one starts with an action verb and dont change any of the numbers",
  "Rewrite my resume bullet points so each one starts with an action verb. Do not change any of the numbers.",
  inc=("resume bullet points", "action verb", "numbers"), neg=1,
  note="job applications: action verbs; negation: numbers unchanged")

Q("prompt",
  "node red flow that sends me a telegram message when the washing machine power drops below five watts for three minutes",
  "Create a Node-RED flow that sends me a Telegram message when the washing machine's power drops below 5 watts for 3 minutes.",
  nums=("5", "3"), inc=("Node-RED", "Telegram", "washing machine", "watts"),
  note="home automation: below 5 watts; sustained 3 minutes; Telegram message")

Q("prompt",
  "find peer reviewed studies from the last five years on spaced repetition for language learning and give me the citations but dont summarize them yet",
  "Find peer-reviewed studies from the last 5 years on spaced repetition for language learning and give me the citations. Do not summarize them yet.",
  nums=("5",), inc=("peer-reviewed", "spaced repetition", "language learning", "citations"), neg=1,
  note="research prompt: last 5 years; peer-reviewed; citations only; negation: no summaries yet")

Q("prompt",
  "write me a monthly budget template with categories rent groceries transport subscriptions and savings and columns for planned versus actual",
  "Create a monthly budget template with the categories rent, groceries, transport, subscriptions and savings, and columns for planned versus actual.",
  inc=("monthly budget template", "rent", "groceries", "transport", "subscriptions", "savings", "planned versus actual"),
  note="personal finance: exactly 5 categories; planned vs actual columns; nothing added")

# long
Q("multi_constraint",
  "okay so this is for the coding agent um in our e learning app there's a page app slash courses slash id slash page dot tsx that shows the lesson list and i want a progress bar at the top that shows the percentage of lessons completed um the data already comes from the use progress hook in lib slash progress dot ts so dont add a new api call and the bar should be hidden for users who aren't logged in um acceptance criteria the percentage is rounded to a whole number the bar updates when a lesson is marked complete without a page reload and the existing playwright tests still pass",
  "## Goal\nAdd a progress bar to the top of the lesson list page in our e-learning app that shows the percentage of lessons completed.\n\n## Context\nThe page is app/courses/id/page.tsx. The data already comes from the useProgress hook in lib/progress.ts, so do not add a new API call. Hide the bar for users who are not logged in.\n\n## Acceptance criteria\nThe percentage is rounded to a whole number. The bar updates when a lesson is marked complete, without a page reload. The existing Playwright tests still pass.",
  inc=("app/courses/id/page.tsx", "lib/progress.ts", "useProgress", "Playwright", "whole number", "without a page reload"), neg=3,
  markup="markdown", context="code",
  instr="use headings for goal, context and acceptance criteria, keep the file paths exactly", cx=3,
  note="markdown headings requested by instruction. facts: page app/courses/id/page.tsx (written exactly as spoken; no brackets added); data from useProgress in lib/progress.ts; negation: no new API call; hidden for logged-out users; criteria: whole-number rounding, updates without reload, existing Playwright tests pass")

Q("multi_constraint",
  "so rehan is making a stardew valley mod with content patcher and he needs a prompt um the mod changes the colour of the farmhouse roof to dark green in spring and summer and brown in fall and winter it should not touch any other buildings it has to work with stardew one point six and um no custom code just content patcher json and he wants the config to have an option to turn the seasonal change off",
  "Help Rehan build a Stardew Valley mod with Content Patcher.\nRequirements:\n- Change the colour of the farmhouse roof to dark green in spring and summer, and brown in fall and winter.\n- Do not touch any other buildings.\n- It has to work with Stardew 1.6.\n- No custom code; use only Content Patcher JSON.\n- Add a config option to turn the seasonal change off.",
  nums=("1.6",), inc=("Rehan", "Content Patcher", "dark green", "brown", "Stardew 1.6", "config option", "farmhouse roof"), neg=2,
  afmt=None, locale="en-gb", instr="add the constraints as a list, keep the version number", cx=2, waivers=["number_missing"],
  note="game modding: dark green spring+summer, brown fall+winter; negation: no other buildings; Stardew 1.6 ('one point six'; checker reads a separate 1, number_missing waived); no custom code, Content Patcher JSON only; config toggle. Constraints listed because instruction asks (format assertion omitted)")

Q("multi_constraint",
  "um so basically what i want is like an automation for my expense tracking so every time i get a transaction sms from my bank on my phone it gets forwarded uh to an email and then i want n8n to read that email pull out the amount the merchant and the date and add a row in my google sheet called expenses twenty twenty six and uh if the amount is over five thousand rupees it should also send me a telegram alert and um it should skip otp messages completely those aren't transactions",
  "Build an n8n workflow for my expense tracking: read the bank transaction SMS emails forwarded from my phone, extract the amount, merchant and date, and add a row to my Google Sheet Expenses 2026. If the amount is over ₹5,000, also send me a Telegram alert. Skip OTP messages completely; they are not transactions.",
  nums=("2026", "5,000"), inc=("n8n", "Expenses 2026", "Telegram", "OTP", "₹5,000", "amount, merchant and date"), neg=1,
  length="shorter", locale="en-in",
  instr="make it concise, keep every condition and the sheet name", cx=3,
  note="concise fix (cf. TC-W05-044): target ~55 words vs ~90-word transcript, every requirement kept. facts: SMS forwarded to email; n8n extracts amount, merchant, date; sheet Expenses 2026; condition: over ₹5,000 -> Telegram alert; OTP messages skipped (negation kept)")

Q("prompt",
  "okay i have an interview next week for a ux researcher position and i want to practice um so be the hiring manager and ask me behavioral questions the star kind like tell me about a time when uh ask them one by one and after each answer tell me which part of star i missed if any um i'm ngozi by the way and the company does fitness apps so keep the questions around that kind of product",
  "Act as the hiring manager for a UX researcher position and help me practise for my interview. My name is Ngozi, and the company makes fitness apps, so keep the questions around that kind of product. Ask me STAR-style behavioral questions (\"Tell me about a time when...\") one by one. After each answer, tell me which part of STAR I missed, if any.",
  inc=("UX researcher", "Ngozi", "fitness apps", "STAR", "one by one", "if any"), locale="en-gb",
  note="interview role-play: STAR behavioral questions, one by one; after each answer say which STAR part was missed 'if any' (condition kept); Ngozi; fitness apps; 'next week' framing context, no date invented")

Q("multi_constraint",
  "i need an image prompt for the cover of bea's online course on houseplants um a pair of hands repotting a monstera on a wooden table with soil scattered around and a white ceramic pot uh actually make the pot terracotta not white and the background should be a sunny balcony with lots of other plants and leave empty space at the top for the course title but dont put any text in it",
  "Create a cover image for Bea's online course on houseplants: a pair of hands repotting a monstera on a wooden table, with soil scattered around and a terracotta pot (not white). The background is a sunny balcony with lots of other plants. Leave empty space at the top for the course title, but do not put any text in the image.",
  inc=("Bea", "houseplants", "monstera", "wooden table", "terracotta pot", "sunny balcony", "empty space at the top"), notinc=("white ceramic",), neg=1,
  instr="keep every visual detail exactly and apply my correction about the pot", cx=2,
  note="e-learning image prompt: self-correction applied: terracotta pot (not white ceramic); hands repotting monstera; wooden table; soil scattered; sunny balcony with plants; empty space at top; negation: no text")

Q("multi_constraint",
  "so i'm preparing for the gate computer science exam and i need a study plan um i have about five months i'm weakest in theory of computation and compiler design so give those more time um i can do three hours on weekdays and six on weekends no wait five on weekends because i work saturday mornings and i want a full mock test every two weeks and the last three weeks only revision no new topics",
  "Create a study plan for the GATE Computer Science exam. I have about 5 months. I'm weakest in Theory of Computation and Compiler Design, so give those more time. I can study 3 hours on weekdays and 5 hours on weekends, because I work Saturday mornings. Include a full mock test every 2 weeks. The last 3 weeks are revision only, with no new topics.",
  nums=("5", "3", "2"), inc=("GATE", "Theory of Computation", "Compiler Design", "about 5 months", "Saturday mornings", "mock test", "revision only"),
  notinc=("6 hours",), neg=1, locale="en-in",
  instr="turn it into a detailed prompt, apply my correction and keep every number", cx=3,
  note="study plan: about 5 months (hedge); weak areas ToC and Compiler Design get more time; 3 h weekdays; weekends corrected to 5 h (not 6) because of Saturday-morning work; mock test every 2 weeks; last 3 weeks revision only (negation: no new topics)")

Q("prompt",
  "i want to write a blog post about doing home automation on a budget um the angle is that you don't need an expensive hub you can start with like three smart plugs and a cheap motion sensor and uh i want sections on picking an app setting up your first routine and what not to buy um the readers are renters so nothing that needs drilling or rewiring and keep the tone practical not salesy",
  "Write an outline for a blog post about home automation on a budget. The angle is that you do not need an expensive hub: you can start with about 3 smart plugs and a cheap motion sensor. Include sections on picking an app, setting up your first routine, and what not to buy. The readers are renters, so include nothing that needs drilling or rewiring. Keep the tone practical, not salesy.",
  nums=("3",), inc=("home automation", "budget", "smart plugs", "motion sensor", "renters", "drilling or rewiring", "practical"), neg=4,
  note="writing task (outline): 'like three' = about 3 smart plugs; 3 named sections; renters: nothing needing drilling/rewiring; practical not salesy; 4 negations (don't need hub, what not to buy, nothing, not salesy)")

Q("multi_constraint",
  "write a sql query for the course database um i need for each course the number of enrolled students and the completion rate as a percentage only for courses published after january first twenty twenty five sorry after july first twenty twenty five and sort by completion rate descending and uh exclude courses with fewer than twenty enrollments because the rate isn't meaningful there the tables are courses enrollments and completions",
  "Write a SQL query for the course database that shows, for each course, the number of enrolled students and the completion rate as a percentage. Include only courses published after July 1, 2025, and sort by completion rate in descending order. Exclude courses with fewer than 20 enrollments, because the rate is not meaningful there. The tables are courses, enrollments and completions.",
  nums=("1", "2025", "20"), inc=("SQL", "July 1, 2025", "completion rate", "descending", "fewer than 20", "courses, enrollments and completions"),
  notinc=("January",), neg=1,
  instr="keep the table names and apply my date correction", cx=2, waivers=["number_missing", "number_invented"],
  note="number keys waived: checker reads 'twenty twenty five' as 20 and 25, not the year 2025. e-learning SQL: date corrected to after July 1, 2025 (not January 1); per-course enrolled count + completion %; descending by completion rate; exclude fewer than 20 enrollments (negation 'not meaningful' kept); 3 table names")

Q("multi_constraint",
  "so i need a prompt to translate the onboarding emails for our language learning app into hindi um there are four emails and the tone should stay friendly and casual not formal hindi um keep the app name lingoleap in english and keep the button text start lesson in english too because the app ui isn't translated yet and if a phrase doesnt have a natural hindi equivalent keep it in english rather than forcing it",
  "Translate the 4 onboarding emails for our language learning app into Hindi. Keep the tone friendly and casual, not formal Hindi. Keep the app name LingoLeap and the button text \"Start Lesson\" in English, because the app UI is not translated yet. If a phrase does not have a natural Hindi equivalent, keep it in English rather than forcing it.",
  nums=("4",), inc=("Hindi", "LingoLeap", "Start Lesson", "friendly and casual", "natural Hindi equivalent"), neg=3,
  instr="prompt for another AI, keep the product name and button text exactly", cx=2,
  note="translation PROMPT (target stays English; nothing translated): 4 emails; friendly/casual not formal; LingoLeap and 'Start Lesson' stay English (UI not translated); condition: no natural equivalent -> keep English")

Q("prompt",
  "um okay so i'm going to paste a bunch of receipts as text from my email and i need the ai to pull out for each receipt the store name the date the total amount and the payment method and give it back as json uh one object per receipt and if a receipt has no payment method listed set it to null dont make one up and keep the amounts exactly as written with the currency symbol",
  "Extract the store name, date, total amount and payment method from each receipt I paste below (copied as text from my email). Return JSON with one object per receipt. If a receipt has no payment method listed, set it to null; do not make one up. Keep the amounts exactly as written, including the currency symbol.",
  inc=("store name", "date", "total amount", "payment method", "JSON", "one object per receipt", "null", "currency symbol"), neg=2,
  note="personal finance extraction: 4 fields; JSON, one object per receipt; condition: missing payment method -> null (negation: don't invent); amounts verbatim with currency symbol")

Q("multi_constraint",
  "so i'm applying to a lot of jobs and i want a zapier setup um whenever i star an email in gmail that has the label applications it should add a row to my airtable base job tracker with the company name the role and the date i got the email and set the status to applied uh and every friday at six pm it should send me a summary in slack of how many rows were added that week but dont send it if the count is zero",
  "Set up a Zapier automation for my job applications. Whenever I star an email in Gmail that has the label Applications, add a row to my Airtable base Job Tracker with the company name, the role and the date I received the email, and set the status to Applied. Every Friday at 6 p.m., send me a Slack summary of how many rows were added that week, but do not send it if the count is 0.",
  nums=("6", "0"), inc=("Zapier", "Gmail", "Applications", "Airtable", "Job Tracker", "Applied", "Friday", "Slack"), neg=1,
  instr="detailed prompt, keep the labels and names exactly and don't add extra steps", cx=3,
  note="job applications automation: trigger = starred AND label Applications; Airtable Job Tracker row (company, role, received date, status Applied); Friday 6 p.m. Slack weekly count; condition: not sent if count is 0")

Q("multi_constraint",
  "this is for kunal's repo um the coding assistant needs to add a csv export to the transactions page the file is src slash views slash transactions dot py it's flask uh the export button should download only the rows that match the current filters not everything and the file name should be transactions underscore and then the date like year month day dot csv um acceptance criteria are it works with the existing filters there's a unit test for the export function and the amounts keep two decimal places and please dont add pandas we're keeping dependencies minimal",
  "Add a CSV export to the transactions page in Kunal's repo.\nFile: src/views/transactions.py (Flask).\nRequirements:\n- The export button downloads only the rows that match the current filters, not everything.\n- The file name is transactions_YYYYMMDD.csv (the date as year, month, day).\n- Do not add pandas; we're keeping dependencies minimal.\nAcceptance criteria:\n- It works with the existing filters.\n- There is a unit test for the export function.\n- Amounts keep 2 decimal places.",
  nums=("2",), inc=("Kunal", "src/views/transactions.py", "Flask", "current filters", "transactions_YYYYMMDD.csv", "pandas", "unit test", "2 decimal places"), neg=2,
  afmt=None, context="code",
  instr="agent prompt with the constraints and acceptance criteria as lists, keep the file path", cx=3,
  note="agent prompt: file src/views/transactions.py (Flask); export only filtered rows (negation 'not everything'); file name transactions_ + date year-month-day .csv; negation: no pandas; criteria: existing filters, unit test, 2 decimals. Lists requested by instruction (format assertion omitted)")
