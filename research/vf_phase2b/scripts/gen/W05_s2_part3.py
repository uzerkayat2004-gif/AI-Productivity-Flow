# ---------------------------------------------------------------- stage 2, chunk 3 (181-220)
Q("prompt",
  "draw a cartoon robot watering sunflowers",
  "Draw a cartoon robot watering sunflowers.",
  inc=("cartoon robot", "sunflowers"), notinc=("Pixar", "3D", "vibrant"),
  note="image prompt: cartoon (speaker's style), robot watering sunflowers; nothing added")

Q("prompt",
  "write a haiku about monday mornings",
  "Write a haiku about Monday mornings.",
  inc=("haiku", "Monday mornings"),
  note="writing task; prompt only, no haiku written")

Q("prompt",
  "make a quiz with five true or false questions on the french revolution",
  "Make a quiz with 5 true-or-false questions on the French Revolution.",
  nums=("5",), inc=("true-or-false", "French Revolution"),
  note="e-learning: 5 true/false questions")

Q("prompt",
  "whats the excel shortcut to freeze the top row",
  "Tell me the Excel shortcut to freeze the top row.",
  inc=("Excel", "freeze the top row"), notinc=("Alt", "W, F, R"),
  note="question turned into a prompt; must not answer (no shortcut keys)")

Q("prompt",
  "linkedin headline for a fresher looking for data entry jobs",
  "Write a LinkedIn headline for a fresher looking for data entry jobs.",
  inc=("LinkedIn headline", "fresher", "data entry"), locale="en-in",
  note="job applications: fresher; data entry jobs")

Q("prompt",
  "explain kelvin versus celsius to a ten year old",
  "Explain Kelvin versus Celsius to a 10-year-old.",
  nums=("10",), inc=("Kelvin", "Celsius"), notinc=("273",),
  note="learning prompt; audience age 10; must not answer (no 273 offset)")

Q("prompt",
  "help me name my terraria texture pack it makes everything look autumn themed",
  "Help me name my Terraria texture pack, which makes everything look autumn-themed.",
  inc=("Terraria", "texture pack", "autumn-themed"),
  note="game modding: naming help; autumn theme")

Q("prompt",
  "write a polite follow up email for a job application i sent ten days ago",
  "Write a polite follow-up email for a job application I sent 10 days ago.",
  nums=("10",), inc=("follow-up email", "job application", "polite"),
  note="job applications: sent 10 days ago; polite; no company or role invented")

Q("prompt",
  "create a weekly chore chart for three roommates",
  "Create a weekly chore chart for 3 roommates.",
  nums=("3",), inc=("weekly chore chart", "roommates"),
  note="facts: weekly; 3 roommates")

Q("prompt",
  "write a google apps script that emails me whenever a cell in column f changes",
  "Write a Google Apps Script that emails me whenever a cell in column F changes.",
  inc=("Google Apps Script", "column F"),
  note="facts: trigger on any change in column F; email to me")

# medium
Q("prompt",
  "turn this paragraph about the water cycle into five fill in the blank questions for class six students and put the answers at the end",
  "Turn this paragraph about the water cycle into 5 fill-in-the-blank questions for Class 6 students, with the answers at the end.",
  nums=("5", "6"), inc=("water cycle", "fill-in-the-blank", "Class 6", "answers at the end"), locale="en-in",
  note="e-learning: 5 questions; Class 6; answers at the end")

Q("prompt",
  "write a product description for a handmade leather wallet with six card slots and a coin pocket it only comes in brown and dont mention the price",
  "Write a product description for a handmade leather wallet with 6 card slots and a coin pocket. It only comes in brown. Do not mention the price.",
  nums=("6",), inc=("handmade leather wallet", "card slots", "coin pocket", "only comes in brown", "price"), neg=1,
  note="writing task: 6 card slots; coin pocket; brown only; negation: no price")

Q("prompt",
  "image for my cooking video thumbnail a steaming bowl of ramen with a soft boiled egg and chopsticks resting on top on a dark wooden background",
  "Create an image for my cooking video thumbnail: a steaming bowl of ramen with a soft-boiled egg and chopsticks resting on top, on a dark wooden background.",
  inc=("thumbnail", "steaming bowl of ramen", "soft-boiled egg", "chopsticks", "dark wooden background"), notinc=("text", "4K", "food photography"),
  note="image prompt: every detail kept; no title text or style added")

Q("prompt",
  "excel formula for my savings rate savings in column d divided by income in column b shown as a percentage with one decimal place",
  "Write an Excel formula that calculates my savings rate as savings in column D divided by income in column B, shown as a percentage with one decimal place.",
  inc=("Excel", "savings rate", "column D", "column B", "percentage", "one decimal place"),
  note="personal finance: D / B; percentage; one decimal place")

Q("prompt",
  "explain the difference between let const and var in javascript with one short code example for each",
  "Explain the difference between let, const and var in JavaScript, with one short code example for each.",
  inc=("let", "const", "var", "JavaScript", "one short code example"), notinc=("block-scoped", "hoisting"),
  note="learning prompt; must not answer; one short example each")

Q("prompt",
  "n8n workflow that posts new videos from my youtube channel to a discord channel within ten minutes of upload",
  "Build an n8n workflow that posts new videos from my YouTube channel to a Discord channel within 10 minutes of upload.",
  nums=("10",), inc=("n8n", "YouTube", "Discord", "within 10 minutes"),
  note="automation: YouTube -> Discord; within 10 minutes")

Q("prompt",
  "create a lesson plan for a forty five minute online class on fractions for grade four with one warm up activity and a five minute quiz at the end",
  "Create a lesson plan for a 45-minute online class on fractions for Grade 4, with one warm-up activity and a 5-minute quiz at the end.",
  nums=("45", "4", "5"), inc=("lesson plan", "fractions", "Grade 4", "warm-up activity", "quiz at the end"),
  note="e-learning: 45-minute class; Grade 4; one warm-up; 5-minute quiz at end")

Q("prompt",
  "i want a list of twenty beginner friendly kaggle datasets about personal finance with a one line description and the link for each",
  "List 20 beginner-friendly Kaggle datasets about personal finance, with a one-line description and the link for each.",
  nums=("20",), inc=("Kaggle", "beginner-friendly", "personal finance", "one-line description", "link"),
  note="research prompt: 20 datasets; one-line description + link each; prompt does not list any")

Q("prompt",
  "write a python script that renames all the screenshots in my downloads folder to the date they were taken and skips files that arent png",
  "Write a Python script that renames all the screenshots in my Downloads folder to the date they were taken, skipping files that are not PNG.",
  inc=("Python", "screenshots", "Downloads folder", "date they were taken", "PNG"), neg=1,
  note="facts: rename to date taken; skip non-PNG files (negation kept)")

Q("multi_constraint",
  "um so i need a prompt that writes a short email to go with my job application for the content writer role at greenleaf media saying i've attached my resume and three writing samples and that i can join from the first of next month and uh that's it nothing else",
  "Write a short email for my content writer application at Greenleaf Media saying I've attached my resume and 3 writing samples and can join from the 1st of next month. Add nothing else.",
  nums=("3", "1"), inc=("content writer", "Greenleaf Media", "resume", "writing samples", "1st of next month", "nothing else"), neg=1,
  length="shorter", instr="make it concise and don't add anything I didn't say", cx=3,
  note="concise: ~35-word target vs ~50-word transcript. job application: Greenleaf Media; resume + 3 writing samples attached; can join from the 1st of next month; nothing else added (negation kept)")

Q("multi_constraint",
  "write a research prompt for yara about smart thermostats um she wants to know if they actually save money in a small two bedroom flat in a mild climate um compare at least two independent studies not manufacturer claims and say clearly where the evidence is weak",
  "## Goal\nFind out whether smart thermostats actually save money in a small 2-bedroom flat in a mild climate (research for Yara).\n\n## Method\nCompare at least 2 independent studies, not manufacturer claims.\n\n## Output\nSay clearly where the evidence is weak.",
  nums=("2",), inc=("Yara", "smart thermostats", "2-bedroom flat", "mild climate", "independent studies", "manufacturer claims", "evidence is weak"), neg=1,
  markup="markdown", locale="en-gb", instr="give it headings for goal, method and output", cx=2,
  note="markdown headings requested. research prompt, not answered: 2-bedroom flat; mild climate; at least 2 independent studies; negation: not manufacturer claims; flag weak evidence")

Q("multi_constraint",
  "so i want to pair my aqara zigbee door sensor with home assistant using the sonoff dongle first install the zha integration then put the sensor in pairing mode then rename it to front door sensor and finally make an automation that sends a phone notification when it opens",
  "Walk me through these steps to pair my Aqara Zigbee door sensor with Home Assistant using the Sonoff dongle:\n1. Install the ZHA integration.\n2. Put the sensor in pairing mode.\n3. Rename it to \"Front Door Sensor\".\n4. Create an automation that sends a phone notification when it opens.",
  inc=("Aqara", "Zigbee", "Home Assistant", "Sonoff", "ZHA", "Front Door Sensor", "phone notification"), afmt=None,
  instr="step-by-step prompt please, keep my order", cx=2,
  note="home automation: 4 steps in speaker's order; device name 'Front Door Sensor'; notification on open. Numbered steps because instruction asks (format assertion omitted)")

Q("multi_constraint",
  "i'm making a minecraft resource pack that replaces the diamond sword texture with a katana and um it's for version one point twenty no one point twenty one and the texture has to be sixteen by sixteen pixels to match vanilla dont make it high res",
  "Help me make a Minecraft resource pack that replaces the diamond sword texture with a katana. It's for version 1.21. The texture must be 16 by 16 pixels to match vanilla; do not make it high-res.",
  nums=("1.21", "16"), inc=("Minecraft", "resource pack", "diamond sword", "katana", "16 by 16", "vanilla", "high-res"),
  notinc=("1.20",), neg=1, waivers=["number_missing", "negation_lost"],
  instr="keep the version and the size rule, apply my correction", cx=2,
  note="game modding: correction applied: version 1.21 (not 1.20); 16x16 pixels; negation: not high-res. Waivers: checker reads 'one point twenty one' as separate 1/20/1 values (number_missing) and counts the correction marker 'no' as a negation (negation_lost)")

Q("multi_constraint",
  "write a sql query on the job applications table using the exact column names company role applied on and status that counts applications per status for this year and only includes rows where status isnt withdrawn",
  "Write a SQL query on the job applications table, using the exact column names company, role, applied_on and status, that counts applications per status for this year. Include only rows where status is not 'withdrawn'.",
  inc=("SQL", "applied_on", "status", "per status", "this year", "withdrawn"), neg=1,
  instr="keep my exact column names", cx=1,
  note="job applications SQL: column names as dictated (applied on -> applied_on, spoken with spaces; judgement: joined with underscore as a column identifier); count per status; this year; exclude 'withdrawn' (negation kept)")

Q("multi_constraint",
  "liam wants to practise for a sales development rep interview so play the interviewer at a b2b software company ask him to do a cold call role play where you are a busy it manager push back twice with objections and then give feedback on his opening his questions and his close no more than one hundred fifty words of feedback",
  "Play the interviewer at a B2B software company for Liam's sales development rep interview practice.\nSetup:\n- Ask him to do a cold-call role-play in which you are a busy IT manager.\n- Push back twice with objections.\n- Then give feedback on his opening, his questions and his close.\n- Keep the feedback to no more than 150 words.",
  nums=("150",), inc=("Liam", "sales development rep", "B2B software", "busy IT manager", "twice", "opening", "close"), neg=1, afmt=None,
  instr="role-play prompt, add the constraints as a list", cx=2,
  note="interview role-play: B2B software; cold call; interviewer plays busy IT manager; exactly 2 objections ('twice'); feedback on opening, questions, close; max 150 words (negation 'no more than' kept). List requested (format assertion omitted)")

Q("multi_constraint",
  "so i need a google sheets formula for my credit card tracker that adds up column c for the current billing cycle which starts on the fifteenth of each month and ends on the fourteenth of the next month um it should work in any month without me editing the dates",
  "Write a Google Sheets formula for my credit card tracker: sum column C for the current billing cycle (15th of each month to the 14th of the next). It must work in any month without editing the dates.",
  nums=("15", "14"), inc=("Google Sheets", "credit card tracker", "column C", "15th", "14th", "without editing the dates"), neg=1,
  length="shorter", instr="keep the cycle dates, make it tighter", cx=2,
  note="tighter: ~35-word target vs ~50-word transcript. personal finance: sum column C; billing cycle 15th to 14th of next month; must work any month without editing dates (negation kept)")

Q("multi_constraint",
  "prompt to translate my game mod's readme into brazilian portuguese and keep all the console commands and file paths in english exactly as they are",
  "Translate my game mod's README into Brazilian Portuguese. Keep all console commands and file paths in English, exactly as they are.",
  inc=("README", "Brazilian Portuguese", "console commands", "file paths", "exactly as they are"),
  instr="it's a prompt for another AI, keep the rule about commands and paths", cx=1,
  note="translation PROMPT (nothing translated): Brazilian Portuguese; commands and file paths unchanged")

# long
Q("prompt",
  "okay so shreya's launching her excel for accountants course and she needs landing page copy um the facts are it's twelve video lessons about six hours total it covers pivot tables xlookup power query and basic macros um there's a certificate at the end and lifetime access and the price is two thousand nine hundred ninety nine rupees uh she doesn't want any countdown timers or fake scarcity like only five seats left and no testimonials because she doesn't have any yet",
  "Write landing page copy for Shreya's Excel for Accountants course. The facts are: 12 video lessons, about 6 hours in total, covering pivot tables, XLOOKUP, Power Query and basic macros. There is a certificate at the end and lifetime access. The price is ₹2,999. Do not use countdown timers or fake scarcity (such as \"only 5 seats left\"), and include no testimonials, because she does not have any yet.",
  nums=("12", "6", "2,999", "5"), inc=("Shreya", "Excel for Accountants", "XLOOKUP", "Power Query", "basic macros", "certificate", "lifetime access", "₹2,999", "testimonials"),
  neg=3, locale="en-in",
  note="e-learning copy: 12 lessons; 'about 6 hours' hedge; 4 topics; certificate; lifetime access; ₹2,999 (rupees spoken); 3 negations: doesn't want countdown/fake scarcity ('only 5 seats left' is the speaker's example of what not to write), no testimonials, she doesn't have any")

Q("multi_constraint",
  "this is for the coding agent um i've got a folder of textures for my skyrim mod in textures slash armor and they're all png and i need a python script at tools slash convert underscore textures dot py that converts them to dds with bc7 compression and generates mipmaps um it should not overwrite the original pngs it should write the dds files to output slash textures with the same folder structure um acceptance criteria running it twice doesn't redo files that are already converted and it prints a summary of how many were converted and how many skipped and it uses texconv not any paid tool",
  "## Goal\nWrite a Python script at tools/convert_textures.py that converts the PNG textures for my Skyrim mod in textures/armor to DDS with BC7 compression and generates mipmaps.\n\n## Constraints\nDo not overwrite the original PNGs. Write the DDS files to output/textures with the same folder structure. Use texconv, not any paid tool.\n\n## Acceptance criteria\nRunning it twice does not redo files that are already converted. It prints a summary of how many files were converted and how many were skipped.",
  inc=("tools/convert_textures.py", "textures/armor", "output/textures", "BC7", "mipmaps", "texconv", "same folder structure"), neg=3,
  markup="markdown", context="code",
  instr="agent prompt with headings for goal, constraints and acceptance criteria, keep every path exactly", cx=3,
  note="markdown headings requested. game modding agent prompt: paths tools/convert_textures.py, textures/armor, output/textures verbatim; PNG -> DDS BC7 + mipmaps; negations: don't overwrite PNGs, don't redo converted files, not a paid tool (texconv); summary of converted vs skipped")

Q("multi_constraint",
  "i need an image prompt for a poster for our smart home meetup um the text should say smart home meetup pune and below that saturday the eighteenth at four pm uh at the makers hub and the image is a stylised house outline made of circuit lines glowing teal on a dark navy background and leave the bottom quarter empty for sponsor logos and please spell everything exactly as i said",
  "Create a poster for our smart home meetup. The text should say \"Smart Home Meetup Pune\" and, below that, \"Saturday the 18th at 4 p.m. at the Makers Hub\". The image is a stylised house outline made of circuit lines glowing teal on a dark navy background. Leave the bottom quarter empty for sponsor logos. Spell all text exactly as given.",
  nums=("18", "4"), inc=("Smart Home Meetup Pune", "18th", "4 p.m.", "Makers Hub", "circuit lines", "teal", "dark navy", "bottom quarter"),
  locale="en-gb", instr="keep the poster text and every visual detail exactly, no extra style", cx=2,
  note="home automation image prompt: poster text 'Smart Home Meetup Pune'; Saturday the 18th, 4 p.m., Makers Hub; stylised house of glowing teal circuit lines on dark navy; bottom quarter empty for sponsor logos; no style added")

Q("prompt",
  "so i want to learn machine learning properly but i keep jumping between youtube videos um can you make me a learning roadmap i know python basics and high school maths but no statistics i'd rather learn from free resources and books are fine um i want it split into phases with a small project at the end of each phase and dont include deep learning yet i want the foundations first",
  "Make me a machine learning learning roadmap. I know Python basics and high school maths but no statistics. I'd rather learn from free resources, and books are fine. Split it into phases with a small project at the end of each phase. Do not include deep learning yet; I want the foundations first.",
  inc=("machine learning", "Python basics", "high school maths", "no statistics", "free resources", "books are fine", "deep learning"), neg=2,
  locale="en-gb",
  note="learning prompt: knows Python basics + high school maths, no statistics (negation); prefers free resources ('rather' preference, books fine); phases with project each; negation: no deep learning yet")

Q("multi_constraint",
  "write a prompt to tailor my resume for a junior business analyst job um my facts are b com from mumbai university in twenty twenty four one year as an operations intern at a fintech where i built excel dashboards for the collections team and i've done the sql basics course on coursera uh dont invent any tools i haven't used and dont add a summary section just tailor the bullet points to the job description i'll paste",
  "Tailor my resume bullet points to the junior business analyst job description I'll paste. Facts: B.Com, Mumbai University, 2024; 1 year as an operations intern at a fintech, building Excel dashboards for the collections team; Coursera SQL basics course. Do not invent tools I haven't used, and do not add a summary section.",
  nums=("2024", "1"), inc=("junior business analyst", "B.Com", "Mumbai University", "operations intern", "Excel dashboards", "collections team", "Coursera"), neg=3,
  length="shorter", locale="en-in", instr="keep it short but keep every fact and both restrictions", cx=3,
  waivers=["number_missing", "number_invented"],
  note="shorter: ~50-word target vs ~78-word transcript. job application: B.Com Mumbai University 2024; one-year ops internship at fintech (Excel dashboards for collections team); Coursera SQL basics; negations: no invented tools, no summary section. number keys waived: 'twenty twenty four' read as 20/24 by checker")

Q("multi_constraint",
  "okay home assistant automation um when i leave home so when my phone leaves the home zone turn off all lights and set the ac to off and uh lock the front door but only on weekdays not weekends and um if any window sensor shows open dont lock the door just send me a notification saying which window is open oh and wait twenty minutes sorry ten minutes after i leave before doing anything in case i come back",
  "Write a Home Assistant automation that runs when my phone leaves the home zone, on weekdays only, not weekends. Wait 10 minutes after I leave before doing anything, in case I come back. Then turn off all lights, turn the AC off, and lock the front door. If any window sensor shows open, do not lock the door; instead send me a notification saying which window is open.",
  nums=("10",), inc=("Home Assistant", "home zone", "weekdays only", "AC off", "front door", "window sensor", "which window is open", "in case I come back"),
  notinc=("20 minutes",), neg=2,
  instr="detailed prompt, apply my correction and keep the window condition exactly", cx=3,
  note="home automation: trigger phone leaves home zone; weekdays only, not weekends; delay corrected to 10 minutes (not 20); lights off, AC off, lock door; condition: any window open -> don't lock, notify which window (negation kept)")

Q("prompt",
  "um so i'm going to paste notes from our team meeting and i want the ai to pull out every action item into a table with three columns the task the owner and the due date um and if no owner was mentioned write unassigned and if no date was mentioned leave the date blank dont guess either of them and keep the tasks in the order they appear",
  "Extract every action item from the team meeting notes I paste below into a table with 3 columns: Task, Owner and Due Date. If no owner was mentioned, write \"Unassigned\". If no date was mentioned, leave the date blank. Do not guess either of them. Keep the tasks in the order they appear.",
  nums=("3",), inc=("action item", "Task", "Owner", "Due Date", "Unassigned", "leave the date blank", "order they appear"), neg=3,
  note="extraction prompt: 3 columns; condition: no owner -> 'Unassigned'; no date -> blank; negation: no guessing; keep original order")

Q("multi_constraint",
  "so we sell courses on teachable and i want a zapier zap um whenever someone enrolls in the python for beginners course add them to the mailchimp audience called python students with the tag new enrolment and then wait three days and send them the welcome survey email from mailchimp uh but only for paid enrolments not the free coupon ones and dont add them again if they're already in the audience",
  "Create a Zapier Zap for our Teachable courses. Whenever someone enrolls in the Python for Beginners course, add them to the Mailchimp audience Python Students with the tag \"New Enrolment\", wait 3 days, then send them the welcome survey email from Mailchimp. Only do this for paid enrolments, not free coupon ones. Do not add anyone again if they are already in the audience.",
  nums=("3",), inc=("Teachable", "Python for Beginners", "Mailchimp", "Python Students", "New Enrolment", "welcome survey", "paid enrolments"), neg=2,
  locale="en-gb", instr="keep the course, audience and tag names exactly", cx=2,
  note="e-learning automation: trigger enrolment in Python for Beginners; Mailchimp audience 'Python Students', tag 'New Enrolment'; wait 3 days then welcome survey email; condition: paid only, not free coupon; no duplicates")

Q("multi_constraint",
  "i need a study plan for ielts academic um my test is in eight weeks i'm already at about band six point five and i need a seven point five overall um writing is my weakest so it needs the most time and speaking second uh i can study ninety minutes on weekdays and um three hours on sundays no saturdays sorry saturdays and include two full timed mock tests one in week four and one in week seven",
  "Create an 8-week study plan for IELTS Academic. I'm currently at about band 6.5 and need 7.5 overall. Writing is my weakest skill, so give it the most time, with speaking second. I can study 90 minutes on weekdays and 3 hours on Saturdays. Include 2 full timed mock tests, one in week 4 and one in week 7.",
  nums=("8", "6.5", "7.5", "90", "3", "2", "4", "7"), inc=("IELTS Academic", "about band 6.5", "Writing", "speaking second", "Saturdays", "mock tests"),
  notinc=("Sunday",), instr="turn it into a prompt for a tutor AI, apply my correction about the day", cx=2,
  waivers=["number_missing", "number_invented", "negation_lost"],
  note="study plan: 8 weeks; 'about band 6.5' hedge; target 7.5 overall; writing most time, speaking second; 90 min weekdays; 3 h on Saturdays (corrected from Sundays); 2 mocks in weeks 4 and 7. Waivers: checker reads 'six point five'/'seven point five' as separate digits and counts the correction 'no' as a negation")

Q("prompt",
  "my godot game keeps crashing when i load the mod folder um it's godot four point two and the mods are loaded with a script that uses dir access to read res slash mods at startup uh the error says cannot open file but the folder is definitely there i checked it twice um i dont want to restructure the project i just want to know why it can't find the folder in the exported build when it works fine in the editor",
  "Help me find out why my Godot 4.2 game crashes when it loads the mod folder: in the exported build it can't find the folder, even though it works fine in the editor. The mods are loaded at startup by a script that uses DirAccess to read res://mods. The error says \"Cannot open file\", but the folder is definitely there; I checked it twice. I do not want to restructure the project.",
  nums=("4.2",), inc=("Godot 4.2", "DirAccess", "res://mods", "Cannot open file", "exported build", "editor", "checked it twice"), neg=3,
  context="code", notinc=("user://", "PCK"), waivers=["number_missing", "number_invented"],
  note="game modding debug prompt, must not answer (no user:// or PCK explanation): Godot 4.2 ('four point two', checker reads separate digits: number keys waived); DirAccess; res://mods; error 'Cannot open file' (negation); folder checked twice; negation: no restructuring; works in editor, fails in exported build")

Q("multi_constraint",
  "write a prompt for a blog post outline on how students can track their spending in their first year of college um sections on picking a method like an app or a spreadsheet setting a weekly limit tracking cash and reviewing at month end and uh it's general tips only so no tax advice no legal advice and dont recommend any specific bank or credit card",
  "Outline a blog post on how students can track their spending in their first year of college. Sections: picking a method (app or spreadsheet), setting a weekly limit, tracking cash, reviewing at month end. General tips only: no tax advice, no legal advice, no specific bank or credit card recommendations.",
  inc=("blog post", "first year of college", "app or spreadsheet", "weekly limit", "tracking cash", "month end", "tax advice", "legal advice"), neg=3,
  length="shorter", instr="make it shorter, keep all four sections and every restriction", cx=3,
  note="shorter: ~45-word target vs ~66-word transcript. personal finance writing: 4 sections (method: app or spreadsheet; weekly limit; cash; month-end review); negations: no tax advice, no legal advice, no specific bank or card")
