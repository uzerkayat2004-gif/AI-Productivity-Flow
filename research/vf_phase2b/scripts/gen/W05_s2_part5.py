# ---------------------------------------------------------------- stage 2, chunk 5 (255-290)
Q("prompt",
  "a cozy cabin in the mountains with smoke rising from the chimney as an oil painting",
  "Create an oil painting of a cozy cabin in the mountains with smoke rising from the chimney.",
  inc=("oil painting", "cozy cabin", "mountains", "smoke rising from the chimney"), notinc=("sunset", "snow", "4K"),
  note="image prompt: oil painting (speaker's style); cabin, mountains, chimney smoke; no time of day or weather added")

Q("prompt",
  "excel formula to remove extra spaces from the names in column a",
  "Write an Excel formula that removes extra spaces from the names in column A.",
  inc=("Excel", "extra spaces", "column A"), notinc=("TRIM",),
  note="prompt only; must not give the answer (TRIM)")

Q("prompt",
  "explain how a vpn works in simple words",
  "Explain how a VPN works in simple words.",
  inc=("VPN", "simple words"),
  note="learning prompt; not answered")

Q("prompt",
  "write a two line bio for my github profile",
  "Write a 2-line bio for my GitHub profile.",
  nums=("2",), inc=("bio", "GitHub profile"),
  note="facts: 2 lines; no personal details invented")

Q("prompt",
  "suggest three automations for a smart home with just motion sensors and smart plugs",
  "Suggest 3 automations for a smart home that has just motion sensors and smart plugs.",
  nums=("3",), inc=("automations", "motion sensors", "smart plugs", "just"),
  note="home automation: 3 suggestions; devices limited to motion sensors and smart plugs ('just' kept)")

# medium
Q("prompt",
  "sql query that returns the students who scored above the class average in the maths exam from the results table",
  "Write a SQL query that returns the students who scored above the class average in the maths exam, from the results table.",
  inc=("SQL", "above the class average", "maths exam", "results table"), locale="en-gb",
  note="e-learning SQL: above class average; maths exam only; results table")

Q("prompt",
  "image of a kid's bedroom at night with glow in the dark stars on the ceiling a bunk bed and a telescope by the window",
  "Create an image of a kid's bedroom at night, with glow-in-the-dark stars on the ceiling, a bunk bed and a telescope by the window.",
  inc=("kid's bedroom", "at night", "glow-in-the-dark stars", "ceiling", "bunk bed", "telescope by the window"), notinc=("cozy", "Pixar", "4K"),
  note="image prompt: every detail kept; no style or mood words added")

Q("prompt",
  "short product description for our online typing course for kids aged eight to twelve it has thirty lessons and a game after every lesson",
  "Write a short product description for our online typing course for kids aged 8 to 12. It has 30 lessons and a game after every lesson.",
  nums=("8", "12", "30"), inc=("online typing course", "kids aged 8 to 12", "30 lessons", "game after every lesson"),
  note="e-learning: ages 8-12; 30 lessons; game after every lesson; short")

Q("prompt",
  "an apps script that sends me a reminder email on the twenty fifth of every month to pay my credit card bill",
  "Write an Apps Script that sends me a reminder email on the 25th of every month to pay my credit card bill.",
  nums=("25",), inc=("Apps Script", "reminder email", "25th of every month", "credit card bill"),
  note="personal finance: 25th of every month; reminder only, script does not pay anything")

Q("prompt",
  "explain how a home loan emi is calculated including the formula but dont do the maths for my numbers",
  "Explain how a home loan EMI is calculated, including the formula. Do not do the maths for my numbers.",
  inc=("home loan EMI", "formula", "my numbers"), neg=1, locale="en-in",
  note="personal finance learning prompt: formula included; negation: no calculation for the user's numbers; not answered")

Q("prompt",
  "python script that reads my bank statement pdf and pulls the transactions into a csv using pdfplumber",
  "Write a Python script that reads my bank statement PDF and pulls the transactions into a CSV using pdfplumber.",
  inc=("Python", "bank statement PDF", "transactions", "CSV", "pdfplumber"),
  note="personal finance: PDF -> CSV; pdfplumber required")

Q("prompt",
  "generate twenty multiple choice questions from the chapter i paste and tag each one as easy medium or hard",
  "Generate 20 multiple-choice questions from the chapter I paste, and tag each one as easy, medium or hard.",
  nums=("20",), inc=("multiple-choice", "chapter I paste", "easy, medium or hard"),
  note="e-learning: 20 MCQs; each tagged easy/medium/hard")

Q("prompt",
  "play an angry customer so i can practise for my customer support interview and stay in character until i say stop",
  "Play an angry customer so I can practise for my customer support interview. Stay in character until I say stop.",
  inc=("angry customer", "customer support interview", "stay in character", "until I say stop"), locale="en-gb",
  note="interview role-play: angry customer; stay in character until 'stop'")

Q("prompt",
  "write the config page description for my rimworld mod explaining the three difficulty presets casual normal and brutal",
  "Write the config page description for my RimWorld mod, explaining the 3 difficulty presets: Casual, Normal and Brutal.",
  nums=("3",), inc=("RimWorld", "config page", "Casual", "Normal", "Brutal"),
  note="game modding: 3 presets named exactly; no preset details invented")

Q("prompt",
  "n8n workflow that backs up my home assistant config folder to google drive every sunday at three am and keeps only the last four backups",
  "Build an n8n workflow that backs up my Home Assistant config folder to Google Drive every Sunday at 3 a.m. and keeps only the last 4 backups.",
  nums=("3", "4"), inc=("n8n", "Home Assistant", "config folder", "Google Drive", "Sunday", "last 4 backups"),
  note="home automation: Sunday 3 a.m.; keep only last 4 backups")

Q("prompt",
  "turn the transcript of my zoom lecture into study notes with a heading for each topic and a short recap at the end",
  "Turn the transcript of my Zoom lecture into study notes, with a heading for each topic and a short recap at the end.",
  inc=("Zoom lecture", "study notes", "heading for each topic", "short recap"),
  note="e-learning: the headings are what the other AI should produce; this target stays plain prose")

Q("prompt",
  "help me write a short thank you email after my interview with the hiring manager bea at brightpath i want to mention the onboarding project we talked about",
  "Help me write a short thank-you email to Bea, the hiring manager at BrightPath, after my interview. Mention the onboarding project we talked about.",
  inc=("thank-you email", "Bea", "hiring manager", "BrightPath", "onboarding project"),
  note="job application: recipient Bea, hiring manager at BrightPath; mention the onboarding project discussed; nothing else added")

Q("prompt",
  "find the cheapest way for a student to send money from the uk to india and compare at least three services by fees and exchange rate",
  "Find the cheapest way for a student to send money from the UK to India, and compare at least 3 services by fees and exchange rate.",
  nums=("3",), inc=("student", "UK to India", "at least 3 services", "fees", "exchange rate"), locale="en-gb",
  note="research prompt, not answered: at least 3 services; compare fees + exchange rate; no service named")

Q("prompt",
  "explain what a foreign key is with an example from an e learning database that has students and courses tables",
  "Explain what a foreign key is, with an example from an e-learning database that has students and courses tables.",
  inc=("foreign key", "e-learning database", "students", "courses"),
  note="learning prompt; example context given by speaker; not answered")

Q("prompt",
  "excel formula that shows the number of days left until each application deadline in column c and shows passed if the date is already over",
  "Write an Excel formula that shows the number of days left until each application deadline in column C, and shows \"Passed\" if the date is already over.",
  inc=("Excel", "days left", "application deadline", "column C", "Passed", "already over"),
  note="job applications tracker: days left until deadline in column C; condition: date over -> 'Passed'")

Q("multi_constraint",
  "write a linkedin message to a recruiter at nimbus labs about the junior devops opening say i have the aws cloud practitioner certificate and a homelab with kubernetes and ask if they're still hiring",
  "Write a LinkedIn message to a recruiter at Nimbus Labs about the junior DevOps opening. Say I have the AWS Cloud Practitioner certificate and a homelab with Kubernetes, and ask if they are still hiring.",
  inc=("LinkedIn message", "recruiter", "Nimbus Labs", "junior DevOps", "AWS Cloud Practitioner", "homelab", "Kubernetes", "still hiring"),
  tone="friendly", instr="make it a detailed prompt but don't add any experience I didn't mention", cx=2,
  note="job application: Nimbus Labs junior DevOps; facts only AWS Cloud Practitioner + Kubernetes homelab; asks if still hiring (question kept as an instruction, not answered); tone header friendly adds no facts")

Q("multi_constraint",
  "so um my philips hue lights keep disconnecting from the bridge like every couple of days and i have to power cycle them to get them back um i've already updated the firmware and moved the bridge closer what else could be causing it",
  "Find other possible causes for my Philips Hue lights disconnecting from the bridge about every couple of days; I have to power-cycle them to reconnect. Already tried: updating the firmware, moving the bridge closer.",
  inc=("Philips Hue", "bridge", "couple of days", "power-cycle", "updating the firmware", "moving the bridge closer"), notinc=("Zigbee channel", "interference"),
  length="shorter", instr="make it a tighter prompt", cx=2,
  note="tighter: ~32-word target vs ~44-word transcript. home automation debug, not answered: 'like every couple of days' -> about every couple of days; power cycling; already tried firmware update and moving bridge closer")

Q("multi_constraint",
  "i want an extraction prompt for invoices i forward from my email the ai should pull the vendor name invoice number invoice date due date and total and flag any invoice where the due date is less than seven days away",
  "## Task\nExtract data from the invoices I forward from my email.\n\n## Fields\nVendor name, invoice number, invoice date, due date and total.\n\n## Flag\nFlag any invoice where the due date is less than 7 days away.",
  nums=("7",), inc=("vendor name", "invoice number", "invoice date", "due date", "total", "less than 7 days"),
  markup="markdown", instr="use headings for task, fields and flag", cx=2,
  note="markdown headings requested. personal finance extraction: 5 fields; flag due date less than 7 days away")

Q("multi_constraint",
  "make a two week study plan for revising organic chemistry reactions i can do either thirty or forty five minutes a day depending on college so give me both versions",
  "Make a 2-week study plan for revising organic chemistry reactions. I can study either 30 or 45 minutes a day depending on college, so give me both versions.",
  nums=("2", "30", "45"), inc=("organic chemistry reactions", "30 or 45 minutes", "both versions", "depending on college"),
  instr="keep both time options exactly", cx=1,
  note="genuine alternative kept: 30 OR 45 minutes a day, both versions requested; 2 weeks; condition 'depending on college'")

Q("multi_constraint",
  "image prompt for a youtube banner for my modding channel a dragon made of green code characters flying over a pixel castle um the channel name kunal mods sorry kunal's mod lab in white text on the right side",
  "Create a YouTube banner for my modding channel: a dragon made of green code characters flying over a pixel castle, with the channel name \"Kunal's Mod Lab\" in white text on the right side.",
  inc=("YouTube banner", "dragon", "green code characters", "pixel castle", "Kunal's Mod Lab", "white text", "right side"), notinc=("Kunal Mods",),
  instr="keep every detail and the exact channel name after my correction", cx=2,
  note="game modding image prompt: correction applied: channel name 'Kunal's Mod Lab' (not 'Kunal Mods'); dragon of green code characters; pixel castle; white text on right side")

Q("multi_constraint",
  "coding agent prompt add a dark theme to the settings page in src slash pages slash settings dot vue use the existing colors in src slash styles slash tokens dot css and dont add any new css framework",
  "Add a dark theme to the settings page in src/pages/settings.vue. Use the existing colors in src/styles/tokens.css, and do not add any new CSS framework.",
  inc=("src/pages/settings.vue", "src/styles/tokens.css", "dark theme", "CSS framework"), neg=1, context="code",
  instr="keep my exact file paths", cx=1,
  note="agent prompt: paths verbatim; reuse existing colors in tokens.css; negation: no new CSS framework")

# long
Q("prompt",
  "um okay so i got my first credit card three months ago and i keep hearing about credit scores but honestly i don't really get it um i want to understand what actually affects the score how long it takes to build one and what mistakes to avoid as a beginner and i'd like it explained without jargon and with examples using small amounts like a ten thousand rupee limit um but don't recommend any particular card or bank",
  "Explain credit scores to me as a beginner. I got my first credit card 3 months ago and honestly don't really get it. I want to understand what actually affects the score, how long it takes to build one, and what mistakes to avoid. Explain it without jargon and with examples using small amounts, like a ₹10,000 limit. Do not recommend any particular card or bank.",
  nums=("3", "10,000"), inc=("credit scores", "first credit card", "3 months ago", "how long it takes", "mistakes to avoid", "without jargon", "₹10,000"), neg=3,
  locale="en-in",
  note="personal finance learning prompt, not answered: first card 3 months ago; 3 questions (what affects score, how long, mistakes); no jargon; example ₹10,000 limit; negations: doesn't get it, no jargon ('without'), no card/bank recommendation")

Q("prompt",
  "so for our e learning platform i need a script for a four minute intro video for the new excel course um it should open with the problem of people wasting hours on manual copy paste then introduce the instructor elodie who has ten years as a financial analyst then show what's in the course which is twenty lessons on formulas pivot tables and dashboards and end with a call to enrol um no hard selling no fake stats and keep it conversational",
  "Write a script for a 4-minute intro video for the new Excel course on our e-learning platform. Open with the problem of people wasting hours on manual copy-paste. Then introduce the instructor, Elodie, who has 10 years of experience as a financial analyst. Then show what's in the course: 20 lessons on formulas, pivot tables and dashboards. End with a call to enrol. No hard selling, no fake stats, and keep it conversational.",
  nums=("4", "10", "20"), inc=("4-minute", "Excel course", "manual copy-paste", "Elodie", "financial analyst", "20 lessons", "call to enrol", "fake stats", "conversational"), neg=2,
  locale="en-gb",
  note="e-learning video script prompt: 4 minutes; order kept (problem, Elodie with 10 years as financial analyst, 20 lessons on formulas/pivot tables/dashboards, call to enrol); negations: no hard selling, no fake stats; conversational")

Q("prompt",
  "i'm making my first terraria mod with tmodloader and um i want to add a sword called the ember blade it should do forty five damage set enemies on fire for three seconds and be crafted from twelve hellstone bars at an anvil um i'm not sure how the on hit effect works so explain that part in the comments and um don't use any other mods as dependencies",
  "Help me add a sword to my first Terraria mod with tModLoader. It's called the Ember Blade. It should do 45 damage, set enemies on fire for 3 seconds, and be crafted from 12 Hellstone Bars at an anvil. I'm not sure how the on-hit effect works, so explain that part in the comments. Do not use any other mods as dependencies.",
  nums=("45", "3", "12"), inc=("Terraria", "tModLoader", "Ember Blade", "45 damage", "3 seconds", "12 Hellstone Bars", "anvil", "on-hit effect", "comments"), neg=2,
  context="code",
  note="game modding: Ember Blade; 45 damage; on fire 3 seconds; 12 Hellstone Bars at anvil; explain on-hit in comments (speaker 'not sure' - negation kept); negation: no other mods as dependencies")

Q("prompt",
  "um so i have two job offers and i'm stuck one is a startup in bangalore offering twelve lakh with esops and fully remote and the other is a big company in pune offering ten point five lakh but with a guaranteed bonus and um a two year bond uh help me think through which one makes more sense for someone at my stage like two years experience but don't just tell me which to pick i want the trade offs laid out",
  "Help me think through two job offers for someone at my stage (2 years of experience). Offer 1: a startup in Bangalore offering ₹12 lakh with ESOPs, fully remote. Offer 2: a big company in Pune offering ₹10.5 lakh with a guaranteed bonus and a 2-year bond. Do not just tell me which to pick; lay out the trade-offs.",
  nums=("12", "10.5", "2"), inc=("Bangalore", "₹12 lakh", "ESOPs", "fully remote", "Pune", "₹10.5 lakh", "guaranteed bonus", "2-year bond", "trade-offs"), neg=1,
  locale="en-in", waivers=["number_missing", "number_invented", "invented_commitment"],
  note="invented_commitment waived: 'guaranteed bonus' is the speaker's own fact (checker's source regex misses 'guaranteed'). job applications decision prompt, not answered: offer 1 Bangalore startup ₹12 lakh + ESOPs + fully remote; offer 2 Pune big company ₹10.5 lakh + guaranteed bonus + 2-year bond; 2 years experience; negation: don't pick, lay out trade-offs. ₹ applied to both lakh amounts (rupee context, lakh spoken). Checker reads lakh as 100000 and 'ten point five' as separate digits: number keys waived. 'Offer 1/2' labels are layout, both offers given by speaker")

Q("multi_constraint",
  "okay so for the coding agent i've got an esp32 with a bme280 sensor and i want an esphome config at esphome slash bedroom underscore climate dot yaml that reads temperature humidity and pressure every sixty seconds um it should show up in home assistant as bedroom climate and um i also want a template sensor for the dew point but no display and no deep sleep because it's mains powered and the wifi credentials must come from secrets dot yaml not hard coded",
  "## Goal\nCreate an ESPHome config at esphome/bedroom_climate.yaml for an ESP32 with a BME280 sensor.\n\n## Requirements\nRead temperature, humidity and pressure every 60 seconds. It should appear in Home Assistant as \"Bedroom Climate\". Add a template sensor for the dew point.\n\n## Constraints\nNo display and no deep sleep, because it's mains powered. The Wi-Fi credentials must come from secrets.yaml, not be hard-coded.",
  nums=("32", "280", "60"), inc=("ESP32", "BME280", "esphome/bedroom_climate.yaml", "Bedroom Climate", "dew point", "deep sleep", "mains powered", "secrets.yaml"), neg=3,
  markup="markdown", context="code",
  instr="agent prompt with headings for goal, requirements and constraints, keep the file paths exactly", cx=3,
  note="markdown headings requested. home automation agent prompt: ESP32 + BME280; path esphome/bedroom_climate.yaml; temp/humidity/pressure every 60 s; HA name 'Bedroom Climate'; dew point template sensor; negations: no display, no deep sleep (mains powered), credentials from secrets.yaml not hard-coded")

Q("multi_constraint",
  "so i need a sql query for the job tracker database um the tables are applications and companies applications has company id role status and applied on and companies has id name and city um i want every application from the last sixty days joined with the company name and city where status is either interview or offer and sorted by applied on newest first and um skip companies in cities other than pune or mumbai",
  "Write a SQL query for the job tracker database.\nTables:\n- applications (company_id, role, status, applied_on)\n- companies (id, name, city)\nRequirements:\n- Every application from the last 60 days, joined with the company name and city.\n- Status is either 'interview' or 'offer'.\n- Only companies in Pune or Mumbai; skip other cities.\n- Sort by applied_on, newest first.",
  nums=("60",), inc=("applications", "companies", "company_id", "applied_on", "last 60 days", "interview", "offer", "Pune or Mumbai"),
  afmt=None, instr="keep the table and column names exactly, list the requirements", cx=2,
  note="job applications SQL: tables/columns as dictated (spoken with spaces, written as identifiers); last 60 days; status interview OR offer (both kept); only Pune or Mumbai (the speaker's 'skip other cities' rule); newest first. Lists requested (format assertion omitted)")

Q("multi_constraint",
  "i want an image prompt for the mascot of our kids coding app um it's a small round orange robot with big blue eyes and one antenna no two antennas and it's waving with one hand and holding a tablet in the other um plain white background so we can cut it out and flat vector style and please no text or logo",
  "Create the mascot for our kids' coding app: a small, round orange robot with big blue eyes and two antennas, waving with one hand and holding a tablet in the other. Use a plain white background so we can cut it out, in a flat vector style. Do not include any text or logo.",
  one_of=(("two", "2"),), inc=("small, round orange robot", "big blue eyes", "two antennas", "waving", "tablet", "plain white background", "flat vector"), notinc=("one antenna",), neg=1,
  instr="image prompt, apply my correction, keep every detail", cx=2, waivers=["negation_lost"],
  note="e-learning image prompt: correction applied: two antennas (not one); round orange robot; big blue eyes; waving with one hand, tablet in the other; plain white background for cut-out; flat vector (speaker's style); negation: no text or logo. negation_lost waived: the correction marker 'no' is counted by the checker")

Q("multi_constraint",
  "um so i'm job hunting and i want an n8n workflow uh every morning at eight it should check the rss feeds from three job boards i'll give you the urls filter the posts that mention product analyst or business analyst in the title and are remote and then add them to my notion database job leads with title company link and the date found and um it shouldn't add a post that's already in the database and if nothing new matches it shouldn't send me anything otherwise send one telegram message with the count",
  "Build an n8n job-hunt workflow. Every morning at 8, check the RSS feeds of 3 job boards (I'll give you the URLs). Keep remote posts with \"product analyst\" or \"business analyst\" in the title. Add them to my Notion database Job Leads (title, company, link, date found); do not add posts already there. If nothing new matches, send nothing; otherwise send one Telegram message with the count.",
  nums=("8", "3"), inc=("n8n", "RSS", "product analyst", "business analyst", "remote", "Notion", "Job Leads", "Telegram", "count"), neg=2,
  length="shorter", instr="make it concise, keep every condition", cx=3,
  note="concise: ~63-word target vs ~95-word transcript. job applications automation: daily at 8; 3 job boards (URLs to be given); title has product analyst OR business analyst AND remote; Notion 'Job Leads' (title, company, link, date found); negation: no duplicates; condition: nothing new -> no message, otherwise one Telegram message with the count")

Q("multi_constraint",
  "so shreya has a final round interview for a data analyst role at an ed tech company and wants a mock case interview um you play the interviewer and give her a case about falling course completion rates um give her the data in small pieces only when she asks for it and if she goes off track for more than two questions steer her back gently and at the end give three strengths and three things to improve but dont reveal a model answer",
  "Play the interviewer in a mock case interview for Shreya's final round for a data analyst role at an edtech company. Give her a case about falling course completion rates. Share the data in small pieces, only when she asks for it. If she goes off track for more than 2 questions, gently steer her back. At the end, give 3 strengths and 3 things to improve, but do not reveal a model answer.",
  nums=("2", "3"), inc=("Shreya", "final round", "data analyst", "edtech", "course completion rates", "only when she asks", "more than 2 questions", "3 strengths", "model answer"), neg=1,
  instr="role-play prompt, keep the conditions exactly", cx=2,
  note="interview role-play + e-learning: case on falling completion rates; data only when asked; condition: off track for more than 2 questions -> steer back gently; 3 strengths + 3 improvements; negation: no model answer")

Q("multi_constraint",
  "i need a prompt to translate the help center articles for our smart home app into tamil um there are six articles and the audience is older users so the language should be simple and polite um keep the button names exactly as they appear in the app in english like add device and scenes and keep all the step numbers the same and if a technical term like wi fi or bluetooth has no common tamil word just leave it in english",
  "Translate the 6 help centre articles for our smart home app into Tamil. The audience is older users, so keep the language simple and polite. Keep the button names in English exactly as they appear in the app, such as \"Add Device\" and \"Scenes\". Keep all the step numbers the same. If a technical term such as Wi-Fi or Bluetooth has no common Tamil word, leave it in English.",
  nums=("6",), inc=("Tamil", "older users", "simple and polite", "Add Device", "Scenes", "step numbers", "Wi-Fi", "Bluetooth"), neg=1,
  locale="en-in", instr="prompt for a translator AI, keep the button names and the step number rule", cx=2,
  note="translation PROMPT (target in English; nothing translated): 6 articles; older users; simple, polite; button names 'Add Device', 'Scenes' stay English; step numbers unchanged; condition: no common Tamil word -> keep English (negation kept)")
